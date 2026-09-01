from pathlib import Path
import subprocess

import pytest
from fastapi import HTTPException

from app.main import health_check


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_compose_runs_one_admin_process_with_persistent_data_and_healthcheck():
    compose = (PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    dockerfile = (PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "env_file:" in compose
    assert "APP_ENV: production" in compose
    assert "DEBUG: \"false\"" in compose
    assert "./.env:/app/.env" not in compose
    assert "./database:/app/database" in compose
    assert "./logs:/app/logs" in compose
    assert "http://localhost:8000/health" in compose
    assert '"--workers", "1"' in dockerfile
    assert "--reload" not in dockerfile


def test_deployment_guide_documents_fresh_database_import_and_http_residual_risk():
    guide = (PROJECT_ROOT / "docker-deploy-guide.md").read_text(encoding="utf-8")

    assert "全新 SQLite" in guide
    assert "1.0" in guide and "导入" in guide
    assert "公网 IP + HTTP" in guide
    assert "凭据" in guide and "窃听" in guide
    assert "单个 Uvicorn 进程" in guide
    assert "wrangler secret put API_TOKEN" in guide


def test_secret_env_and_database_backups_are_ignored_by_git():
    repository_root = PROJECT_ROOT.parent
    for relative_path in (
        "ZX-auto-clock-in-python/.env",
        "ZX-auto-clock-in-python/.env.production",
        "ZX-auto-clock-in-python/database/backups/zx_admin_test.db",
    ):
        result = subprocess.run(
            ["git", "check-ignore", "--no-index", "--quiet", relative_path],
            cwd=repository_root,
        )
        assert result.returncode == 0, f"未忽略敏感文件: {relative_path}"

    example = subprocess.run(
        ["git", "check-ignore", "--no-index", "--quiet", "ZX-auto-clock-in-python/.env.example"],
        cwd=repository_root,
    )
    assert example.returncode == 1


def test_readme_describes_the_current_main_based_admin_architecture():
    readme = PROJECT_ROOT.parent.joinpath("README.md").read_text(encoding="utf-8")

    assert "免责声明" in readme
    assert "足下" in readme
    assert all(page in readme for page in ("总览", "用户", "打卡记录", "内容源", "系统设置"))
    assert "原生 HTML/CSS/ES Modules" in readme
    assert "单个 Uvicorn 进程" in readme
    assert "python -m pytest -q" in readme
    assert "docker compose" in readme
    assert "Tailwind" not in readme
    assert "DaisyUI" not in readme
    assert "--workers 4" not in readme


class HealthyDatabase:
    def __init__(self, error=None):
        self.error = error
        self.statements = []

    async def execute(self, statement):
        self.statements.append(str(statement))
        if self.error:
            raise self.error


@pytest.mark.asyncio
async def test_health_endpoint_checks_database_readiness():
    database = HealthyDatabase()

    response = await health_check(db=database)

    assert response["status"] == "healthy"
    assert response["database"] == "ready"
    assert database.statements == ["SELECT 1"]


@pytest.mark.asyncio
async def test_health_endpoint_returns_503_without_leaking_database_error():
    database = HealthyDatabase(RuntimeError("database-secret-detail"))

    with pytest.raises(HTTPException) as exc_info:
        await health_check(db=database)

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "service unavailable"
    assert "database-secret-detail" not in str(exc_info.value.detail)
