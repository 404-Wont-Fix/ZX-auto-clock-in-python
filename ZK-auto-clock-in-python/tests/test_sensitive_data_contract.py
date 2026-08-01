import json
import logging
from pathlib import Path

import pytest
from sqlalchemy import select

from app.config import Settings
from app.models.database import Config, ContentSource, User, WorkerApi
from app.models.schemas import UserUpdate, WorkerApiUpdate
from app.services.content_source_service import ContentSourceService
from app.services.user_service import UserService
from app.services.worker_api_service import WorkerApiService


def test_user_and_worker_serialization_never_returns_plaintext_secrets():
    user = User(username="safe_user", password="user-secret")
    worker = WorkerApi(name="safe", url="https://worker.example", token="worker-secret")

    user_data = user.to_dict()
    worker_data = worker.to_dict()

    assert "password" not in user_data
    assert user_data["password_configured"] is True
    assert "token" not in worker_data
    assert worker_data["token_configured"] is True
    assert worker_data["token_masked"] != "worker-secret"
    assert worker_data["token_masked"].startswith("••••")
    assert worker_data["token_masked"].endswith("cret")


@pytest.mark.parametrize("token", ["a", "ab", "abcd", "abcdefgh"])
def test_short_worker_tokens_are_fully_masked(token):
    worker = WorkerApi(name="short", url="https://worker.example", token=token)

    masked = worker.to_dict()["token_masked"]

    assert masked == "••••••••"
    assert token not in masked


@pytest.mark.asyncio
async def test_empty_sensitive_updates_keep_existing_values(db_session):
    user = User(id="keep-user", username="keep_user", password="keep-user-secret")
    worker = WorkerApi(
        id="keep-worker",
        name="keep",
        url="https://keep-worker.example",
        token="keep-worker-secret",
    )
    db_session.add_all([user, worker])
    await db_session.commit()

    await UserService.update_user(db_session, user.id, UserUpdate(password=""))
    await WorkerApiService.update_api(db_session, worker.id, WorkerApiUpdate(token=""))
    await db_session.refresh(user)
    await db_session.refresh(worker)

    assert user.password == "keep-user-secret"
    assert worker.token == "keep-worker-secret"


@pytest.mark.asyncio
async def test_version_2_export_omits_all_passwords_and_tokens(db_session):
    from app.services.config_transfer_service import ConfigTransferService

    db_session.add_all(
        [
            Config(key="schedule_cron", value="0 10 0 * * *"),
            Config(key="clockin_api_token", value="legacy-config-secret"),
            User(username="export_user", password="export-user-secret"),
            WorkerApi(
                name="export-worker",
                url="https://export-worker.example",
                token="export-worker-secret",
            ),
            ContentSource(
                key="export-source",
                name="Export source",
                source_type="text",
                enabled=False,
                archived=False,
                priority=100,
                url_template="https://content.example/text",
                query_params_json="{}",
                parse_mode="plain_text",
                categories_json="[]",
                timeout_seconds=10,
            ),
        ]
    )
    await db_session.commit()

    exported = await ConfigTransferService.export_data(db_session)
    serialized = json.dumps(exported, ensure_ascii=False)

    assert exported["version"] == "2.0"
    assert "password" not in exported["users"][0]
    assert "token" not in exported["worker_apis"][0]
    assert "clockin_api_token" not in exported["config"]
    assert exported["content_sources"][0]["key"] == "export-source"
    assert "export-user-secret" not in serialized
    assert "export-worker-secret" not in serialized
    assert "legacy-config-secret" not in serialized


@pytest.mark.asyncio
async def test_legacy_batch_settings_survive_safe_export(db_session):
    from app.services.config_transfer_service import ConfigTransferService

    legacy_batch_settings = {
        "batch_size": 5,
        "batch_delay": 1500,
        "parallel_tasks": 2,
    }
    payload = {
        "version": "1.0",
        "config": legacy_batch_settings,
        "users": [],
        "worker_apis": [],
    }

    report = await ConfigTransferService.import_data(db_session, payload)
    exported = await ConfigTransferService.export_data(db_session)

    assert report["configs"] == len(legacy_batch_settings)
    assert exported["config"] == {
        key: str(value) for key, value in legacy_batch_settings.items()
    }


@pytest.mark.asyncio
async def test_version_2_import_keeps_existing_user_and_worker_secrets(db_session):
    from app.services.config_transfer_service import ConfigTransferService

    user = User(username="existing_user", password="existing-user-secret")
    worker = WorkerApi(
        name="existing worker",
        url="https://existing-worker.example",
        token="existing-worker-secret",
    )
    db_session.add_all([user, worker])
    await db_session.commit()

    payload = {
        "version": "2.0",
        "config": {},
        "users": [
            {
                "username": "existing_user",
                "nickname": "updated nickname",
                "password_configured": True,
            }
        ],
        "worker_apis": [
            {
                "name": "renamed worker",
                "url": "https://existing-worker.example",
                "enabled": False,
                "token_configured": True,
            }
        ],
        "content_sources": [],
    }

    await ConfigTransferService.import_data(db_session, payload)
    await db_session.refresh(user)
    await db_session.refresh(worker)

    assert user.password == "existing-user-secret"
    assert user.nickname == "updated nickname"
    assert worker.token == "existing-worker-secret"
    assert worker.name == "renamed worker"
    assert worker.enabled is False


@pytest.mark.asyncio
async def test_version_1_import_restores_secrets_maps_legacy_sources_and_logs_no_secret(
    db_session,
    caplog,
):
    from app.services.config_transfer_service import ConfigTransferService

    payload = {
        "version": "1.0",
        "config": {"schedule_enabled": "True"},
        "users": [
            {
                "username": "legacy_yuanmeng",
                "password": "legacy-user-secret-1",
                "sports_comment_api": "yuanmeng_default",
                "daily_comment_api": "cenguigui_default",
                "sports_image_provider": "bing_uhd",
            },
            {
                "username": "legacy_klapi",
                "password": "legacy-user-secret-2",
                "sports_comment_api": "klapi_default",
                "daily_comment_api": "unknown-dead-source",
                "sports_image_provider": "unknown-image-source",
            },
        ],
        "worker_apis": [
            {
                "name": "legacy-worker",
                "url": "https://legacy-worker.example",
                "token": "legacy-worker-secret",
                "enabled": True,
            }
        ],
    }

    with caplog.at_level(logging.INFO):
        report = await ConfigTransferService.import_data(db_session, payload)

    users = list((await db_session.execute(select(User).order_by(User.username))).scalars().all())
    worker = (await db_session.execute(select(WorkerApi))).scalar_one()
    by_username = {user.username: user for user in users}

    assert by_username["legacy_yuanmeng"].password == "legacy-user-secret-1"
    assert by_username["legacy_yuanmeng"].sports_comment_api == "qzqi_yiyan"
    assert by_username["legacy_yuanmeng"].daily_comment_api == "qzqi_yiyan"
    assert by_username["legacy_yuanmeng"].sports_image_provider == "bing_uhd"
    assert by_username["legacy_klapi"].sports_comment_api == "qzqi_yiyan"
    assert by_username["legacy_klapi"].daily_comment_api == "poetry_all"
    assert by_username["legacy_klapi"].sports_image_provider == "bing"
    assert worker.token == "legacy-worker-secret"
    assert report["warnings"]
    assert "legacy-user-secret" not in caplog.text
    assert "legacy-worker-secret" not in caplog.text
    assert "legacy-user-secret" not in json.dumps(report, ensure_ascii=False)
    assert "legacy-worker-secret" not in json.dumps(report, ensure_ascii=False)


@pytest.mark.asyncio
async def test_version_2_import_rolls_back_all_changes_when_a_later_source_crashes(
    db_session,
    monkeypatch,
):
    from app.services.config_transfer_service import ConfigTransferService

    original_create = ContentSourceService.create_source

    async def fail_second_source(db, data, **kwargs):
        if data["key"] == "second-source":
            raise RuntimeError("simulated import crash")
        return await original_create(db, data, **kwargs)

    monkeypatch.setattr(ContentSourceService, "create_source", fail_second_source)
    source_definition = {
        "name": "Imported",
        "source_type": "text",
        "enabled": False,
        "priority": 10,
        "url_template": "https://content.example/text",
        "query_params": {},
        "parse_mode": "plain_text",
        "value_path": None,
        "attribution_path": None,
        "categories": [],
        "timeout_seconds": 10,
    }
    payload = {
        "version": "2.0",
        "config": {"schedule_enabled": "False"},
        "users": [],
        "worker_apis": [],
        "content_sources": [
            {"key": "first-source", **source_definition},
            {"key": "second-source", **source_definition},
        ],
    }

    with pytest.raises(RuntimeError, match="simulated import crash"):
        await ConfigTransferService.import_data(db_session, payload)

    sources = list((await db_session.execute(select(ContentSource))).scalars().all())
    configs = list((await db_session.execute(select(Config))).scalars().all())
    assert sources == []
    assert configs == []


def test_production_rejects_missing_admin_username():
    with pytest.raises(ValueError, match="ADMIN_USERNAME"):
        Settings(
            app_env="production",
            secret_key="a-secure-production-secret",
            admin_username="",
            admin_password="a-secure-admin-password",
        )


def test_repository_contains_no_fixed_worker_token():
    root = Path(__file__).resolve().parents[2]
    sensitive_files = [
        root / "ZK-auto-clock-in-python" / ".env.example",
        root / "ZK-auto-clock-in-python" / "scripts" / "init_db.py",
        root / "clockin-worker" / "wrangler.toml",
    ]
    exposed = "-".join(("35a59c73", "461e", "499d", "8421", "3311c289328e"))

    assert all(exposed not in path.read_text(encoding="utf-8") for path in sensitive_files)
    env_lines = sensitive_files[0].read_text(encoding="utf-8").splitlines()
    assert "CLOCKIN_API_TOKEN=" in env_lines
    init_script = sensitive_files[1].read_text(encoding="utf-8")
    assert "'key': 'clockin_api_token',\n                    'value': ''" in init_script
    assert not (root / "clockin-worker" / ".dev.vars").exists()
    assert "clockin-worker/.dev.vars" in (root / ".gitignore").read_text(encoding="utf-8")


def test_authentication_logs_never_include_session_token_fragments():
    root = Path(__file__).resolve().parents[1]
    auth_source = (root / "app" / "api" / "auth.py").read_text(encoding="utf-8")

    assert "token[:" not in auth_source
