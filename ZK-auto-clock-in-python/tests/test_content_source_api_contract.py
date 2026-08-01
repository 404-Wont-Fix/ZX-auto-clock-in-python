import importlib.util

import httpx
import pytest
from fastapi import FastAPI

from app.api.auth import verify_session
from app.api.content_sources import router
from app.core.database import get_db
from app.services.content_source_service import ContentSourceService


def test_content_source_router_module_exists():
    assert importlib.util.find_spec("app.api.content_sources") is not None


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


def payload(key="api-source"):
    return {
        "key": key,
        "name": "API 测试源",
        "source_type": "text",
        "enabled": False,
        "priority": 40,
        "url_template": "https://content.example/api",
        "query_params": {},
        "parse_mode": "json_text",
        "value_path": "quote",
        "attribution_path": None,
        "categories": [],
        "timeout_seconds": 10,
    }


@pytest.mark.asyncio
async def test_content_source_crud_test_enable_sort_and_archive_contract(db_session, monkeypatch):
    app = create_test_app(db_session)

    async def fake_test_source(db, source_id, *, fetcher=None):
        source = await ContentSourceService.get_source(db, source_id)
        source.verified_config_hash = source.config_fingerprint
        await ContentSourceService.mark_success(db, source, latency_ms=8)
        return {
            "success": True,
            "value_preview": "测试通过",
            "latency_ms": 8,
            "source": source,
        }

    monkeypatch.setattr(ContentSourceService, "test_source", fake_test_source)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        created = await client.post("/api/content-sources", json=payload())
        assert created.status_code == 201
        source = created.json()["data"]
        assert source["key"] == "api-source"
        assert source["health_status"] == "disabled"

        premature = await client.put(
            f"/api/content-sources/{source['id']}",
            json={"enabled": True},
        )
        assert premature.status_code == 400
        assert "测试成功" in premature.json()["error"]

        tested = await client.post(f"/api/content-sources/{source['id']}/test")
        assert tested.status_code == 200
        assert tested.json()["data"]["latency_ms"] == 8

        enabled = await client.put(
            f"/api/content-sources/{source['id']}",
            json={"enabled": True},
        )
        assert enabled.status_code == 200
        assert enabled.json()["data"]["enabled"] is True

        second = await client.post("/api/content-sources", json=payload("second-source"))
        second_id = second.json()["data"]["id"]
        reordered = await client.patch(
            "/api/content-sources/priorities",
            json={
                "items": [
                    {"id": source["id"], "priority": 90},
                    {"id": second_id, "priority": 5},
                ]
            },
        )
        assert reordered.status_code == 200
        by_id = {item["id"]: item for item in reordered.json()["data"]}
        assert by_id[source["id"]]["priority"] == 90
        assert by_id[second_id]["priority"] == 5

        immutable = await client.put(
            f"/api/content-sources/{source['id']}",
            json={"key": "changed"},
        )
        assert immutable.status_code == 422

        archived = await client.delete(f"/api/content-sources/{source['id']}")
        assert archived.status_code == 200
        assert archived.json()["data"]["archived"] is True

        visible = await client.get("/api/content-sources")
        assert {item["key"] for item in visible.json()["data"]} == {"second-source"}

        all_sources = await client.get("/api/content-sources?include_archived=true")
        assert {item["key"] for item in all_sources.json()["data"]} == {
            "api-source",
            "second-source",
        }


@pytest.mark.asyncio
async def test_test_all_returns_per_source_results(db_session, monkeypatch):
    first = await ContentSourceService.create_source(db_session, payload("first-source"))
    second = await ContentSourceService.create_source(db_session, payload("second-source"))

    async def fake_test_source(db, source_id, *, fetcher=None):
        source = await ContentSourceService.get_source(db, source_id)
        return {
            "success": source.key == "first-source",
            "value_preview": source.key,
            "latency_ms": 3,
            "source": source,
            "error": None if source.key == "first-source" else "模拟失败",
        }

    monkeypatch.setattr(ContentSourceService, "test_source", fake_test_source)
    app = create_test_app(db_session)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post("/api/content-sources/test-all")

    assert response.status_code == 200
    data = response.json()["data"]
    assert {item["source"]["id"] for item in data} == {first.id, second.id}
    assert sum(item["success"] for item in data) == 1
