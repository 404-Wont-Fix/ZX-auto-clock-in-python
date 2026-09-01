import httpx
import pytest
import sqlite3
from datetime import datetime
from pathlib import Path
from fastapi import FastAPI
from sqlalchemy import func, select

from app.api.auth import verify_session
from app.api.maintenance import router
from app.core.database import get_db
from app.models.database import ClockinResult, DailySummary
from app.config import settings


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
@pytest.mark.parametrize("days", [-1, 0, 3651])
async def test_cleanup_rejects_unsafe_retention_days_without_deleting_data(
    db_session,
    days,
):
    db_session.add_all(
        [
            ClockinResult(
                username="cleanup_guard",
                date="2020-01-01",
                timestamp=datetime(2020, 1, 1),
                success=True,
                clockin_type="all",
            ),
            DailySummary(date="2020-01-01", total_users=1, success_count=1),
        ]
    )
    await db_session.commit()
    app = create_test_app(db_session)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post("/api/maintenance/cleanup", json={"days": days})

    result_count = await db_session.scalar(select(func.count()).select_from(ClockinResult))
    summary_count = await db_session.scalar(select(func.count()).select_from(DailySummary))
    assert response.status_code == 422
    assert result_count == 1
    assert summary_count == 1


@pytest.mark.asyncio
async def test_backup_uses_sqlite_snapshot_in_persistent_database_directory(
    db_session,
    tmp_path,
    monkeypatch,
):
    database_file = tmp_path / "zx_admin.db"
    with sqlite3.connect(database_file) as connection:
        connection.execute("CREATE TABLE backup_probe (value TEXT NOT NULL)")
        connection.execute("INSERT INTO backup_probe VALUES ('consistent')")
        connection.commit()

    monkeypatch.setattr(settings, "database_url", f"sqlite:///{database_file}")
    app = create_test_app(db_session)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post("/api/maintenance/backup")

    assert response.status_code == 200
    backup_file = Path(response.json()["data"]["backup_file"])
    assert backup_file.parent == database_file.parent / "backups"
    with sqlite3.connect(backup_file) as connection:
        value = connection.execute("SELECT value FROM backup_probe").fetchone()[0]
    assert value == "consistent"
