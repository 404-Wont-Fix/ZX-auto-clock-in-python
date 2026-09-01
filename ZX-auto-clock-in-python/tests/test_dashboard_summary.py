import importlib.util
import json
from datetime import datetime, timedelta

import httpx
import pytest
from fastapi import FastAPI

from app.api.auth import verify_session
from app.core.database import get_db
from app.models.database import ClockinResult, ContentSource, Task, User, WorkerApi
from app.services import dashboard_service as dashboard_module
from app.services.task_service import TaskOrchestrator


def test_dashboard_summary_service_module_exists():
    assert importlib.util.find_spec("app.services.dashboard_service") is not None


def test_dashboard_summary_router_module_exists():
    assert importlib.util.find_spec("app.api.dashboard") is not None


@pytest.mark.asyncio
async def test_dashboard_summary_api_uses_authenticated_service(db_session, monkeypatch):
    from app.api.dashboard import router

    expected = {"date": "2026-07-31", "today": {"success": 2}}

    async def fake_summary(db):
        assert db is db_session
        return expected

    app = FastAPI()
    app.include_router(router)

    async def override_db():
        yield db_session

    async def override_session():
        return object()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[verify_session] = override_session
    monkeypatch.setattr(dashboard_module.DashboardService, "get_summary", fake_summary)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/dashboard/summary")

    assert response.status_code == 200
    assert response.json() == {"success": True, "data": expected}


def managed_source(key, *, source_type="text", enabled=True):
    parse_mode = "json_text" if source_type == "text" else "redirect_image"
    return ContentSource(
        key=key,
        name=key,
        source_type=source_type,
        enabled=enabled,
        archived=False,
        priority=10,
        url_template="https://content.example/api",
        query_params_json="{}",
        parse_mode=parse_mode,
        value_path="quote" if source_type == "text" else None,
        categories_json="[]",
        timeout_seconds=10,
    )


@pytest.mark.asyncio
async def test_summary_uses_each_enabled_users_latest_beijing_result(db_session, monkeypatch):
    today = TaskOrchestrator.beijing_today()
    users = [
        User(id="success", username="success_user", password="secret123", enabled=True),
        User(id="failure", username="failure_user", password="secret123", enabled=True),
        User(id="pending", username="pending_user", password="secret123", enabled=True),
        User(id="disabled", username="disabled_user", password="secret123", enabled=False),
    ]
    db_session.add_all(users)
    now = datetime.now()
    db_session.add_all(
        [
            ClockinResult(
                id="success-old",
                user_id="success",
                username="success_user",
                date=today,
                timestamp=now - timedelta(minutes=2),
                success=False,
                details_json="{}",
            ),
            ClockinResult(
                id="success-latest",
                user_id="success",
                username="success_user",
                date=today,
                timestamp=now,
                success=True,
                details_json=json.dumps({"home": {"success": True}}),
            ),
            ClockinResult(
                id="failure-latest",
                user_id="failure",
                username="failure_user",
                date=today,
                timestamp=now,
                success=False,
                details_json=json.dumps({"sports": {"success": False}}),
                error="图片上传失败",
            ),
            ClockinResult(
                id="disabled-result",
                user_id="disabled",
                username="disabled_user",
                date=today,
                timestamp=now,
                success=False,
                details_json="{}",
            ),
        ]
    )
    db_session.add_all(
        [
            WorkerApi(name="healthy", url="https://worker-1.example", token="one", enabled=True, available=True),
            WorkerApi(name="down", url="https://worker-2.example", token="two", enabled=True, available=False),
            WorkerApi(name="off", url="https://worker-3.example", token="three", enabled=False, available=True),
        ]
    )
    healthy_source = managed_source("healthy-source")
    healthy_source.last_success_at = now
    degraded_source = managed_source("degraded-source", source_type="image")
    degraded_source.consecutive_failures = 1
    unavailable_source = managed_source("unavailable-source")
    unavailable_source.consecutive_failures = 3
    db_session.add_all([healthy_source, degraded_source, unavailable_source])
    active_task = Task(
        task_type="clockin",
        status="running",
        scope="failed",
        target_date=today,
        user_ids_json='["failure"]',
        progress_total=1,
        progress_current=0,
        progress_success=0,
        progress_failure=0,
        triggered_by="manual",
        started_at=now,
    )
    db_session.add(active_task)
    await db_session.commit()

    async def fake_schedule():
        return {"next_run_time_beijing": "2026-08-01T00:10:00+08:00"}

    monkeypatch.setattr(dashboard_module, "get_schedule_info", fake_schedule, raising=False)

    summary = await dashboard_module.DashboardService.get_summary(db_session)

    assert summary["date"] == today
    assert summary["today"] == {
        "enabled_users": 3,
        "success": 1,
        "failure": 1,
        "pending": 1,
    }
    assert summary["failed_users"] == [
        {
            "id": "failure",
            "username": "failure_user",
            "nickname": "",
            "error": "图片上传失败",
            "details": {"sports": {"success": False}},
        }
    ]
    assert summary["active_task"]["id"] == active_task.id
    assert summary["workers"] == {"enabled": 2, "healthy": 1, "unavailable": 1}
    assert summary["content_sources"] == {
        "total": 3,
        "healthy": 1,
        "degraded": 1,
        "unavailable": 1,
        "unknown": 0,
    }
    assert summary["next_run_time"] == "2026-08-01T00:10:00+08:00"
