import httpx
import pytest
from fastapi import FastAPI

from app.api.auth import verify_session
from app.api.clockin import router
from app.core.database import get_db
from app.models.database import Task, User
from app.services.task_service import TaskOrchestrator, clockin_task_orchestrator


def create_test_app(db_session):
    app = FastAPI()
    app.include_router(router)

    async def override_db():
        yield db_session

    async def override_session():
        return object()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[verify_session] = override_session
    return app


@pytest.mark.asyncio
async def test_task_api_returns_202_then_409_with_existing_task_id(db_session, monkeypatch):
    user = User(
        id="api-user",
        username="api_user",
        password="secret123",
        enabled=True,
    )
    db_session.add(user)
    await db_session.commit()
    monkeypatch.setattr(clockin_task_orchestrator, "launch_task", lambda task_id: None)
    app = create_test_app(db_session)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        first = await client.post(
            "/api/clockin/tasks",
            json={"scope": "all", "date": "2026-07-31", "user_ids": []},
        )
        assert first.status_code == 202
        task = first.json()["data"]
        assert task["scope"] == "all"
        assert task["status"] == "pending"
        assert task["progress"]["total"] == 1

        duplicate = await client.post(
            "/api/clockin/tasks",
            json={
                "scope": "users",
                "date": "2026-07-31",
                "user_ids": [user.id],
            },
        )
        assert duplicate.status_code == 409
        assert duplicate.json()["data"]["task_id"] == task["id"]

        active = await client.get("/api/clockin/tasks?status=active")
        assert active.status_code == 200
        assert [item["id"] for item in active.json()["data"]] == [task["id"]]

        detail = await client.get(f"/api/clockin/tasks/{task['id']}")
        assert detail.status_code == 200
        assert detail.json()["data"]["progress"]["current"] == 0


@pytest.mark.asyncio
async def test_task_api_validates_user_scope_and_missing_task(db_session, monkeypatch):
    monkeypatch.setattr(clockin_task_orchestrator, "launch_task", lambda task_id: None)
    app = create_test_app(db_session)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        invalid = await client.post(
            "/api/clockin/tasks",
            json={"scope": "users", "date": "2026-07-31", "user_ids": []},
        )
        assert invalid.status_code == 400
        assert "user_ids" in invalid.json()["error"]

        missing = await client.get("/api/clockin/tasks/not-found")
        assert missing.status_code == 404


@pytest.mark.asyncio
async def test_legacy_manual_routes_enqueue_the_same_task_contract(db_session, monkeypatch):
    user = User(
        id="legacy-user",
        username="legacy_user",
        password="secret123",
        enabled=True,
    )
    db_session.add(user)
    await db_session.commit()
    calls = []

    async def fake_enqueue(db, **kwargs):
        calls.append(kwargs)
        return await TaskOrchestrator().enqueue_task(db, launch=False, **kwargs)

    monkeypatch.setattr(clockin_task_orchestrator, "enqueue_task", fake_enqueue)
    app = create_test_app(db_session)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        all_response = await client.post("/api/clockin/trigger")
        assert all_response.status_code == 202
        first_task_id = all_response.json()["data"]["id"]

        await TaskOrchestrator.interrupt_stale_tasks(db_session)

        user_response = await client.post(f"/api/clockin/user/{user.id}")
        assert user_response.status_code == 202

    assert calls[0]["scope"] == "all"
    assert calls[1]["scope"] == "users"
    assert calls[1]["requested_user_ids"] == [user.id]
    assert first_task_id != user_response.json()["data"]["id"]


def test_completed_task_with_no_targets_reports_full_progress():
    task = Task(
        task_type="clockin",
        status="completed",
        scope="all",
        target_date="2026-07-31",
        progress_total=0,
        progress_current=0,
    )

    assert task.to_dict()["progress"]["percent"] == 100
