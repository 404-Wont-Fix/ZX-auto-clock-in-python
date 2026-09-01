import json
import logging
from datetime import datetime, timezone

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select

from app.api.auth import verify_session
from app.api.config import router as config_router
from app.api.users import router as users_router
from app.api.worker_api import router as worker_router
from app.core.database import get_db
from app.models.database import Config, ContentSource, User, WorkerApi


def test_export_filename_uses_beijing_calendar_date():
    from app.api.config import build_config_export_filename

    utc_time = datetime(2026, 7, 31, 16, 30, tzinfo=timezone.utc)

    assert build_config_export_filename(utc_time) == "zx-admin-config-2026-08-01.json"


def create_test_app(db_session):
    app = FastAPI()
    app.include_router(users_router)
    app.include_router(worker_router)
    app.include_router(config_router)

    async def override_db():
        yield db_session

    async def override_session():
        return object()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[verify_session] = override_session
    return app


@pytest.mark.asyncio
async def test_admin_api_responses_and_export_never_return_plaintext_secrets(db_session):
    db_session.add_all(
        [
            Config(key="clockin_api_token", value="config-api-secret"),
            User(
                id="safe-api-user",
                username="safe_api_user",
                password="user-api-secret",
            ),
            WorkerApi(
                id="safe-api-worker",
                name="safe api worker",
                url="https://safe-api-worker.example",
                token="worker-api-secret",
            ),
        ]
    )
    await db_session.commit()
    app = create_test_app(db_session)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        users = await client.get("/api/users")
        workers = await client.get("/api/worker-apis")
        config = await client.get("/api/config")
        exported = await client.get("/api/config/export")

    assert users.status_code == 200
    assert users.json()["data"][0]["password_configured"] is True
    assert "password" not in users.json()["data"][0]

    assert workers.status_code == 200
    assert workers.json()["data"][0]["token_configured"] is True
    assert "token" not in workers.json()["data"][0]

    assert config.status_code == 200
    assert "clockin_api_token" not in config.json()["data"]

    assert exported.status_code == 200
    assert exported.json()["version"] == "2.0"
    assert exported.headers["content-disposition"].startswith(
        'attachment; filename="zx-admin-config-'
    )
    assert exported.headers["content-disposition"].endswith('.json"')
    serialized = exported.text
    assert "user-api-secret" not in serialized
    assert "worker-api-secret" not in serialized
    assert "config-api-secret" not in serialized


@pytest.mark.asyncio
async def test_empty_config_token_update_keeps_existing_value(db_session):
    token_config = Config(key="clockin_api_token", value="keep-config-secret")
    db_session.add(token_config)
    await db_session.commit()
    app = create_test_app(db_session)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.put("/api/config", json={"clockin_api_token": ""})

    await db_session.refresh(token_config)
    assert response.status_code == 200
    assert token_config.value == "keep-config-secret"


@pytest.mark.asyncio
async def test_legacy_import_restores_secrets_without_echoing_or_logging_them(
    db_session,
    caplog,
    monkeypatch,
):
    reload_calls = []

    async def fake_reload(cron, enabled, timezone):
        reload_calls.append((cron, enabled, timezone))
        return True

    monkeypatch.setattr("app.api.config.reload_clockin_job", fake_reload)
    app = create_test_app(db_session)
    payload = {
        "version": "1.0",
        "config": {
            "schedule_cron": "0 30 1 * * *",
            "schedule_enabled": "True",
            "schedule_timezone": "Asia/Shanghai",
        },
        "users": [
            {
                "username": "legacy_api_user",
                "password": "legacy-api-user-secret",
            }
        ],
        "worker_apis": [
            {
                "name": "legacy api worker",
                "url": "https://legacy-api-worker.example",
                "token": "legacy-api-worker-secret",
            }
        ],
    }

    with caplog.at_level(logging.INFO):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post("/api/config/import", json=payload)

    assert response.status_code == 200
    response_text = json.dumps(response.json(), ensure_ascii=False)
    assert response.json()["data"]["version"] == "1.0"
    assert response.json()["data"]["users_created"] == 1
    assert response.json()["data"]["workers"] == 1
    assert "legacy-api-user-secret" not in response_text
    assert "legacy-api-worker-secret" not in response_text
    assert "legacy-api-user-secret" not in caplog.text
    assert "legacy-api-worker-secret" not in caplog.text
    assert reload_calls == [("0 30 1 * * *", True, "Asia/Shanghai")]

    user = (
        await db_session.execute(select(User).where(User.username == "legacy_api_user"))
    ).scalar_one()
    worker = (
        await db_session.execute(
            select(WorkerApi).where(WorkerApi.url == "https://legacy-api-worker.example")
        )
    ).scalar_one()
    assert user.password == "legacy-api-user-secret"
    assert worker.token == "legacy-api-worker-secret"


@pytest.mark.asyncio
async def test_failed_legacy_import_does_not_log_bound_password_parameters(
    db_session,
    caplog,
):
    app = create_test_app(db_session)
    password = "TOP-SECRET-IMPORT-PASSWORD"
    payload = {
        "version": "1.0",
        "users": [
            {
                "username": "invalid_legacy_user",
                "password": password,
                "nickname": {"invalid": "sqlite-bound-value"},
            }
        ],
        "worker_apis": [],
    }

    with caplog.at_level(logging.ERROR):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post("/api/config/import", json=payload)

    assert response.status_code == 500
    assert password not in response.text
    assert password not in caplog.text


@pytest.mark.asyncio
async def test_create_user_returns_400_for_an_invalid_content_source_category(db_session):
    db_session.add(
        ContentSource(
            key="category-image",
            name="分类图片源",
            source_type="image",
            enabled=True,
            archived=False,
            priority=10,
            url_template="https://images.example/{category}/",
            query_params_json="{}",
            parse_mode="redirect_image",
            categories_json='["pc", "mobile"]',
            timeout_seconds=10,
        )
    )
    await db_session.commit()
    app = create_test_app(db_session)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/users",
            json={
                "username": "invalid_category_api_user",
                "password": "secret123",
                "sports_image_type": "api",
                "sports_image_provider": "category-image",
                "sports_image_category": "tablet",
            },
        )

    assert response.status_code == 400
    assert "图片分类" in response.json()["detail"]
