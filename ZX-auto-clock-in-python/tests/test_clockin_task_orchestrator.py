import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import inspect, select

from app.config import settings
from app.models.database import ClockinResult, Task, User
from app.services import task_service as task_module
from app.services.clockin_service import ClockinService


BEIJING_TODAY = datetime.now(timezone(timedelta(hours=8))).date().isoformat()


def enabled_user(user_id, username):
    return User(
        id=user_id,
        username=username,
        password="secret123",
        enabled=True,
    )


def result(user, *, success, minute, date=BEIJING_TODAY):
    return ClockinResult(
        id=f"{user.id}-{minute}-{success}",
        user_id=user.id,
        username=user.username,
        date=date,
        timestamp=datetime(2026, 7, 31, 1, minute),
        success=success,
        details_json=json.dumps({"home": {"success": success}}),
        error=None if success else "模拟失败",
    )


def test_task_model_contains_durable_clockin_request_fields():
    columns = {column.name for column in inspect(Task).columns}

    assert {
        "scope",
        "target_date",
        "user_ids_json",
        "triggered_by",
        "started_at",
    }.issubset(columns)


@pytest.mark.asyncio
async def test_failed_scope_selects_only_latest_failed_enabled_users(db_session):
    assert hasattr(task_module, "TaskOrchestrator")
    users = [
        enabled_user("latest-success", "latest_success"),
        enabled_user("latest-failure", "latest_failure"),
        enabled_user("never-run", "never_run"),
        enabled_user("disabled", "disabled"),
    ]
    users[-1].enabled = False
    db_session.add_all(users)
    db_session.add_all(
        [
            result(users[0], success=False, minute=1),
            result(users[0], success=True, minute=2),
            result(users[1], success=True, minute=1),
            result(users[1], success=False, minute=2),
            result(users[3], success=False, minute=3),
        ]
    )
    await db_session.commit()

    selected = await task_module.TaskOrchestrator.select_user_ids(
        db_session,
        scope="failed",
        target_date=BEIJING_TODAY,
        requested_user_ids=[],
    )

    assert selected == ["latest-failure"]


@pytest.mark.asyncio
async def test_enqueue_rejects_second_active_task_with_existing_id(db_session):
    orchestrator = task_module.TaskOrchestrator()
    user = enabled_user("user-1", "user_one")
    db_session.add(user)
    await db_session.commit()

    first = await orchestrator.enqueue_task(
        db_session,
        scope="all",
        target_date=BEIJING_TODAY,
        requested_user_ids=[],
        triggered_by="manual",
        launch=False,
    )

    with pytest.raises(task_module.ActiveTaskConflict) as conflict:
        await orchestrator.enqueue_task(
            db_session,
            scope="users",
            target_date=BEIJING_TODAY,
            requested_user_ids=[user.id],
            triggered_by="manual",
            launch=False,
        )

    assert conflict.value.task_id == first.id
    assert first.status == "pending"
    assert first.progress_total == 1
    assert first.user_ids == [user.id]


@pytest.mark.asyncio
async def test_runner_uses_independent_session_and_persists_progress(
    db_session,
    db_session_factory,
    monkeypatch,
):
    users = [enabled_user("ok-user", "ok_user"), enabled_user("bad-user", "bad_user")]
    db_session.add_all(users)
    await db_session.commit()
    seen_sessions = []

    async def fake_trigger(db, user_id, triggered_by="manual"):
        seen_sessions.append(db)
        return {
            "success": user_id == "ok-user",
            "error": None if user_id == "ok-user" else "模拟失败",
        }

    monkeypatch.setattr(ClockinService, "trigger_user", fake_trigger)
    orchestrator = task_module.TaskOrchestrator(session_factory=db_session_factory)
    task = await orchestrator.enqueue_task(
        db_session,
        scope="all",
        target_date=BEIJING_TODAY,
        requested_user_ids=[],
        triggered_by="manual",
        launch=False,
    )

    await orchestrator.run_task(task.id)
    await db_session.refresh(task)

    assert all(session is not db_session for session in seen_sessions)
    assert task.status == "completed"
    assert task.progress_current == 2
    assert task.progress_success == 1
    assert task.progress_failure == 1
    assert task.progress_current == task.progress_total
    assert task.started_at is not None
    assert task.completed_at is not None
    # 结果顺序由 select_user_ids 的 created_at/username 排序决定（并/串行一致），
    # 这里只校验每个用户的结果内容，不绑定具体顺序。
    results_by_user = {r["user_id"]: r for r in task.result["results"]}
    assert set(results_by_user) == {"ok-user", "bad-user"}
    assert results_by_user["ok-user"] == {
        "user_id": "ok-user", "success": True, "error": None
    }
    assert results_by_user["bad-user"] == {
        "user_id": "bad-user", "success": False, "error": "模拟失败"
    }


@pytest.mark.asyncio
async def test_runner_executes_users_in_parallel_within_concurrency_limit(
    db_session,
    db_session_factory,
    monkeypatch,
):
    """回归保护：run_task 必须真正并行执行用户，且并发数受信号量约束（C2 修复）。"""
    users = [enabled_user(f"u{i}", f"user{i}") for i in range(6)]
    db_session.add_all(users)
    await db_session.commit()

    in_flight = 0
    peak = 0
    lock = asyncio.Lock()

    async def fake_trigger(db, user_id, triggered_by="manual"):
        nonlocal in_flight, peak
        async with lock:
            in_flight += 1
            peak = max(peak, in_flight)
        await asyncio.sleep(0.05)  # 模拟 IO，让多个用户重叠执行
        async with lock:
            in_flight -= 1
        return {"success": True, "error": None}

    monkeypatch.setattr(ClockinService, "trigger_user", fake_trigger)
    monkeypatch.setattr(settings, "parallel_tasks", 4)

    orchestrator = task_module.TaskOrchestrator(session_factory=db_session_factory)

    async def fake_api_count():
        return 4  # 钉住并发上限 = min(parallel_tasks=4, 4) = 4

    orchestrator._available_api_count = fake_api_count

    task = await orchestrator.enqueue_task(
        db_session,
        scope="all",
        target_date=BEIJING_TODAY,
        requested_user_ids=[],
        triggered_by="manual",
        launch=False,
    )
    await orchestrator.run_task(task.id)
    await db_session.refresh(task)

    assert task.status == "completed"
    # 确实并行（peak > 1），且没有突破信号量上限（peak <= 4）
    assert peak > 1, "用户未并行执行，疑似退回串行"
    assert peak <= 4, f"并发数 {peak} 突破了 parallel_tasks 上限"


@pytest.mark.asyncio
async def test_startup_marks_pending_and_running_tasks_interrupted(db_session):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    tasks = [
        Task(task_type="clockin", status="pending", scope="all", target_date=BEIJING_TODAY),
        Task(task_type="clockin", status="running", scope="all", target_date=BEIJING_TODAY),
        Task(
            task_type="clockin",
            status="completed",
            scope="all",
            target_date=BEIJING_TODAY,
            completed_at=now,
        ),
    ]
    db_session.add_all(tasks)
    await db_session.commit()

    count = await task_module.TaskOrchestrator.interrupt_stale_tasks(db_session)
    await db_session.refresh(tasks[0])
    await db_session.refresh(tasks[1])
    await db_session.refresh(tasks[2])

    assert count == 2
    assert tasks[0].status == "interrupted"
    assert tasks[1].status == "interrupted"
    assert tasks[0].completed_at is not None
    assert tasks[1].error == "服务重启，任务已中断"
    assert tasks[2].status == "completed"


@pytest.mark.asyncio
async def test_application_lifespan_invokes_stale_task_interruption(monkeypatch):
    from app import main as main_module
    from app.services.content_source_service import ContentSourceService

    session = object()
    interrupted_sessions = []

    class SessionContext:
        async def __aenter__(self):
            return session

        async def __aexit__(self, exc_type, exc, traceback):
            return False

    async def noop_async(*args, **kwargs):
        return None

    async def fake_interrupt(db):
        interrupted_sessions.append(db)
        return 0

    monkeypatch.setattr(main_module, "init_db", noop_async)
    monkeypatch.setattr(main_module, "close_db", noop_async)
    monkeypatch.setattr(main_module, "start_scheduler", noop_async)
    monkeypatch.setattr(main_module, "stop_scheduler", lambda: None)
    monkeypatch.setattr(main_module, "AsyncSessionLocal", lambda: SessionContext())
    monkeypatch.setattr(ContentSourceService, "ensure_default_sources", noop_async)
    monkeypatch.setattr(task_module.TaskOrchestrator, "interrupt_stale_tasks", fake_interrupt)

    async with main_module.lifespan(main_module.app):
        pass

    assert interrupted_sessions == [session]


@pytest.mark.asyncio
async def test_application_lifespan_refuses_to_start_when_database_init_fails(monkeypatch):
    from app import main as main_module

    scheduler_calls = []
    close_calls = []

    async def fail_init():
        raise RuntimeError("database unavailable")

    async def fake_start_scheduler():
        scheduler_calls.append("started")

    async def fake_close_db():
        close_calls.append("closed")

    monkeypatch.setattr(main_module, "init_db", fail_init)
    monkeypatch.setattr(main_module, "start_scheduler", fake_start_scheduler)
    monkeypatch.setattr(main_module, "close_db", fake_close_db)

    with pytest.raises(RuntimeError, match="database unavailable"):
        async with main_module.lifespan(main_module.app):
            pass

    assert scheduler_calls == []
    assert close_calls == ["closed"]


@pytest.mark.asyncio
async def test_saved_clockin_date_uses_beijing_calendar_day(db_session, monkeypatch):
    from app.services import clockin_service as clockin_module

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            instant = cls(2026, 7, 31, 17, 0, tzinfo=timezone.utc)
            return instant.astimezone(tz) if tz else instant.replace(tzinfo=None)

        @classmethod
        def utcnow(cls):
            return cls(2026, 7, 31, 17, 0)

    monkeypatch.setattr(clockin_module, "datetime", FixedDateTime)
    user = enabled_user("beijing-user", "beijing_user")
    db_session.add(user)
    await db_session.commit()

    saved = await ClockinService.save_clockin_result(
        db_session,
        user,
        {
            "success": True,
            "timestamp": "2026-07-31T17:00:00",
            "results": {
                "home": {"success": True},
                "sports": {"success": True},
                "daily": {"success": True},
            },
        },
    )

    assert saved.date == "2026-08-01"
