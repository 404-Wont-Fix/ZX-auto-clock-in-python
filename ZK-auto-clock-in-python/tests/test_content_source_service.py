from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.models.database import ContentSource, User
from app.services import content_source_service as content_sources


class StubFetcher:
    def __init__(self, outcomes):
        self.outcomes = outcomes
        self.calls = []

    async def fetch(self, source, category=None):
        self.calls.append((source.key, category))
        outcome = self.outcomes[source.key]
        if isinstance(outcome, Exception):
            raise outcome
        return content_sources.FetchedContent(
            value=outcome,
            final_url=source.url_template,
            latency_ms=12,
            content_type="image/jpeg" if source.source_type == "image" else "application/json",
        )


def source_data(key="custom-text", **overrides):
    data = {
        "key": key,
        "name": "自定义文字源",
        "source_type": "text",
        "enabled": False,
        "priority": 50,
        "url_template": "https://content.example/api",
        "query_params": {},
        "parse_mode": "json_text",
        "value_path": "quote",
        "attribution_path": None,
        "categories": [],
        "timeout_seconds": 10,
    }
    data.update(overrides)
    return data


@pytest.mark.asyncio
async def test_initializes_exact_default_sources_without_removed_providers(db_session):
    assert hasattr(content_sources, "ContentSourceService")

    await content_sources.ContentSourceService.ensure_default_sources(db_session)
    result = await db_session.execute(select(ContentSource).order_by(ContentSource.priority))
    sources = result.scalars().all()
    by_key = {source.key: source for source in sources}

    assert set(by_key) == {
        "poetry_all",
        "hitokoto",
        "qzqi_yiyan",
        "bing",
        "bing_uhd",
        "komll",
        "loliapi",
        "cimuapi",
    }
    assert by_key["qzqi_yiyan"].url_template == "https://api.qzqi.com/api/v1/Yiyan"
    assert by_key["bing_uhd"].query_params["uhd"] == "1"
    assert by_key["bing_uhd"].query_params["uhdwidth"] == "3840"
    assert "bing.img.run" not in by_key["bing_uhd"].url_template
    assert {"cenguigui", "yuanmeng", "klapi"}.isdisjoint(by_key)
    assert all(source.enabled for source in sources)
    assert all(source.config_verified for source in sources)

    await content_sources.ContentSourceService.ensure_default_sources(db_session)
    count = (await db_session.execute(select(ContentSource))).scalars().all()
    assert len(count) == 8


@pytest.mark.asyncio
async def test_new_source_must_test_successfully_before_it_can_be_enabled(db_session):
    service = content_sources.ContentSourceService
    source = await service.create_source(db_session, source_data())

    with pytest.raises(ValueError, match="测试成功"):
        await service.update_source(db_session, source.id, {"enabled": True})

    fetcher = StubFetcher({source.key: "测试文案"})
    tested = await service.test_source(db_session, source.id, fetcher=fetcher)
    assert tested["success"] is True

    enabled = await service.update_source(db_session, source.id, {"enabled": True})
    assert enabled.enabled is True
    assert enabled.health_status == "healthy"


@pytest.mark.asyncio
async def test_address_change_clears_verification_and_disables_source(db_session):
    service = content_sources.ContentSourceService
    source = await service.create_source(db_session, source_data())
    await service.test_source(
        db_session,
        source.id,
        fetcher=StubFetcher({source.key: "测试文案"}),
    )
    await service.update_source(db_session, source.id, {"enabled": True})

    changed = await service.update_source(
        db_session,
        source.id,
        {"url_template": "https://other.example/api"},
    )

    assert changed.enabled is False
    assert changed.verified_config_hash is None
    assert changed.config_verified is False


@pytest.mark.asyncio
async def test_one_failure_degrades_three_failures_disable_and_success_recovers(db_session):
    service = content_sources.ContentSourceService
    source = await service.create_source(db_session, source_data())
    source.enabled = True
    source.verified_config_hash = service.config_fingerprint(source)
    await db_session.commit()

    await service.mark_failure(db_session, source, "第一次失败", latency_ms=30)
    assert source.consecutive_failures == 1
    assert source.health_status == "degraded"
    assert source.last_error == "第一次失败"

    await service.mark_failure(db_session, source, "第二次失败")
    await service.mark_failure(db_session, source, "第三次失败")
    assert source.consecutive_failures == 3
    assert source.health_status == "unavailable"

    await service.mark_success(db_session, source, latency_ms=9)
    assert source.consecutive_failures == 0
    assert source.health_status == "healthy"
    assert source.last_error is None
    assert source.last_success_at is not None


@pytest.mark.asyncio
async def test_requested_degraded_source_is_tried_then_healthy_priority_fallback(db_session):
    service = content_sources.ContentSourceService
    requested = await service.create_source(
        db_session,
        source_data("requested", name="指定源", priority=90),
    )
    healthy = await service.create_source(
        db_session,
        source_data("healthy", name="健康源", priority=20),
    )
    unknown = await service.create_source(
        db_session,
        source_data("unknown", name="未知源", priority=10),
    )
    for source in (requested, healthy, unknown):
        source.enabled = True
        source.verified_config_hash = service.config_fingerprint(source)
    requested.consecutive_failures = 1
    requested.last_failure_at = datetime.now(timezone.utc).replace(tzinfo=None)
    healthy.last_success_at = datetime.now(timezone.utc).replace(tzinfo=None)
    await db_session.commit()

    fetcher = StubFetcher(
        {
            "requested": content_sources.ContentSourceFetchError("指定源失败"),
            "healthy": "健康源文案",
            "unknown": "不应先调用",
        }
    )

    result = await service.fetch_content(
        db_session,
        source_type="text",
        requested_key="requested",
        fetcher=fetcher,
    )

    assert result.value == "健康源文案"
    assert result.source_key == "healthy"
    assert fetcher.calls == [("requested", None), ("healthy", None)]
    assert requested.consecutive_failures == 2
    assert healthy.consecutive_failures == 0


@pytest.mark.asyncio
async def test_invalid_user_category_does_not_degrade_shared_image_source(db_session):
    service = content_sources.ContentSourceService
    requested = await service.create_source(
        db_session,
        source_data(
            "categorized-image",
            name="分类图片源",
            source_type="image",
            parse_mode="redirect_image",
            value_path=None,
            categories=["pc"],
            url_template="https://images.example/{category}/",
            priority=10,
        ),
    )
    fallback = await service.create_source(
        db_session,
        source_data(
            "fallback-image",
            name="备用图片源",
            source_type="image",
            parse_mode="redirect_image",
            value_path=None,
            priority=20,
        ),
    )
    for source in (requested, fallback):
        source.enabled = True
        source.verified_config_hash = service.config_fingerprint(source)
    await db_session.commit()

    request_error_type = getattr(content_sources, "ContentSourceRequestError", None)
    assert request_error_type is not None
    result = await service.fetch_content(
        db_session,
        source_type="image",
        requested_key=requested.key,
        category="mobile",
        fetcher=StubFetcher(
            {
                requested.key: request_error_type("请求分类不在允许列表中"),
                fallback.key: "https://images.example/fallback.jpg",
            }
        ),
    )

    assert result.source_key == fallback.key
    assert requested.consecutive_failures == 0
    assert requested.last_error is None


@pytest.mark.asyncio
async def test_unavailable_requested_source_is_skipped_and_static_fallback_is_last(db_session):
    service = content_sources.ContentSourceService
    unavailable = await service.create_source(db_session, source_data("unavailable"))
    fallback_candidate = await service.create_source(db_session, source_data("candidate"))
    for source in (unavailable, fallback_candidate):
        source.enabled = True
        source.verified_config_hash = service.config_fingerprint(source)
    unavailable.consecutive_failures = 3
    await db_session.commit()

    fetcher = StubFetcher(
        {"candidate": content_sources.ContentSourceFetchError("也失败了")}
    )

    result = await service.fetch_content(
        db_session,
        source_type="text",
        requested_key="unavailable",
        static_fallback="固定回退",
        fetcher=fetcher,
    )

    assert fetcher.calls == [("candidate", None)]
    assert result.value == "固定回退"
    assert result.source_key is None
    assert result.fallback is True


@pytest.mark.asyncio
async def test_archive_keeps_referenced_record_but_excludes_it_from_selection(db_session):
    service = content_sources.ContentSourceService
    source = await service.create_source(db_session, source_data("referenced"))
    source.enabled = True
    source.verified_config_hash = service.config_fingerprint(source)
    user = User(
        username="archive_user",
        password="secret123",
        sports_comment_type="api",
        sports_comment_api="referenced",
    )
    db_session.add(user)
    await db_session.commit()

    archived = await service.archive_source(db_session, source.id)
    stored = await db_session.get(ContentSource, source.id)
    stored_user = await db_session.get(User, user.id)

    assert archived.archived is True
    assert stored is not None
    assert stored_user.sports_comment_api == "referenced"

    result = await service.fetch_content(
        db_session,
        source_type="text",
        requested_key="referenced",
        static_fallback="归档后回退",
        fetcher=StubFetcher({}),
    )
    assert result.value == "归档后回退"


@pytest.mark.asyncio
async def test_priority_updates_are_atomic_and_unique(db_session):
    service = content_sources.ContentSourceService
    first = await service.create_source(db_session, source_data("first", priority=10))
    second = await service.create_source(db_session, source_data("second", priority=20))

    await service.update_priorities(
        db_session,
        [
            {"id": first.id, "priority": 30},
            {"id": second.id, "priority": 5},
        ],
    )
    assert first.priority == 30
    assert second.priority == 5

    with pytest.raises(ValueError, match="重复"):
        await service.update_priorities(
            db_session,
            [
                {"id": first.id, "priority": 10},
                {"id": first.id, "priority": 20},
            ],
        )
