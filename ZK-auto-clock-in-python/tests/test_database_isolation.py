import logging
import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.pool import StaticPool

from app.core import database as database_module


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_file_sqlite_engine_does_not_use_static_pool():
    assert not isinstance(database_module.engine.sync_engine.pool, StaticPool)


def test_database_engine_always_hides_bound_parameters():
    assert database_module.engine.sync_engine.hide_parameters is True


@pytest.mark.asyncio
async def test_debug_sql_echo_does_not_log_bound_secret(caplog, capsys):
    secret = "TOP-SECRET-SQL-BOUND-PARAMETER"
    original_echo = database_module.engine.echo
    database_module.engine.echo = True
    try:
        with caplog.at_level(logging.INFO, logger="sqlalchemy.engine.Engine"):
            async with database_module.engine.connect() as connection:
                await connection.execute(text("SELECT :secret"), {"secret": secret})
    finally:
        database_module.engine.echo = original_echo

    captured = capsys.readouterr()
    assert secret not in caplog.text
    assert secret not in captured.out
    assert secret not in captured.err


def test_file_sqlite_sessions_are_transactionally_isolated(tmp_path):
    database_file = tmp_path / "isolation.db"
    script = r'''
import asyncio
from sqlalchemy import select, text

from app.core.database import AsyncSessionLocal, close_db, init_db, engine
from app.models.database import Config


async def main():
    await init_db()
    async with AsyncSessionLocal() as first, AsyncSessionLocal() as second:
        first.add(Config(key="uncommitted-isolation-probe", value="secret"))
        await first.flush()
        visible = await second.scalar(
            select(Config).where(Config.key == "uncommitted-isolation-probe").exists().select()
        )
        assert visible is False, "另一个会话看到了未提交数据"
        await first.rollback()

    async with engine.connect() as connection:
        journal_mode = await connection.scalar(text("PRAGMA journal_mode"))
        busy_timeout = await connection.scalar(text("PRAGMA busy_timeout"))
        assert str(journal_mode).lower() == "wal"
        assert int(busy_timeout) >= 5000
    await close_db()


asyncio.run(main())
'''
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{database_file}"
    env["APP_ENV"] = "development"
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stdout + result.stderr
