import pytest
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core import database as database_module
from app.core import scheduler as scheduler_module
from app.services.content_source_service import ContentSourceService
from app.services.task_service import clockin_task_orchestrator


def test_content_source_probe_job_is_hourly():
    scheduler = AsyncIOScheduler()

    scheduler_module.add_content_source_probe_job(scheduler)

    job = scheduler.get_job("content-source-probe")
    assert job is not None
    assert "1:00:00" in str(job.trigger)


@pytest.mark.asyncio
async def test_scheduled_probe_uses_an_independent_database_session(monkeypatch):
    session = object()
    seen = []

    class SessionContext:
        async def __aenter__(self):
            return session

        async def __aexit__(self, exc_type, exc, traceback):
            return False

    async def fake_test_all(db, *, fetcher=None):
        seen.append(db)
        return [{"success": True}]

    monkeypatch.setattr(database_module, "AsyncSessionLocal", lambda: SessionContext())
    monkeypatch.setattr(ContentSourceService, "test_all", fake_test_all)

    await scheduler_module.scheduled_content_source_probe_job()

    assert seen == [session]


@pytest.mark.asyncio
async def test_scheduled_clockin_uses_the_persistent_orchestrator(monkeypatch):
    session = object()
    calls = []

    class SessionContext:
        async def __aenter__(self):
            return session

        async def __aexit__(self, exc_type, exc, traceback):
            return False

    async def fake_enqueue(db, **kwargs):
        calls.append((db, kwargs))

        class EnqueuedTask:
            id = "scheduled-task"

        return EnqueuedTask()

    monkeypatch.setattr(database_module, "AsyncSessionLocal", lambda: SessionContext())
    monkeypatch.setattr(clockin_task_orchestrator, "enqueue_task", fake_enqueue)

    await scheduler_module.scheduled_clockin_job()

    assert calls == [
        (
            session,
            {
                "scope": "all",
                "target_date": None,
                "requested_user_ids": [],
                "triggered_by": "scheduled",
            },
        )
    ]
