import pytest

from app.models.database import User
from app.models.schemas import UserCreate
from app.services.content_source_service import ContentResult, ContentSourceService
from app.services.poetry_service import PoetryService
from app.services.user_service import UserService


@pytest.mark.asyncio
async def test_sports_and_daily_api_content_use_managed_source_service(db_session, monkeypatch):
    user = User(
        id="user-1",
        username="managed_user",
        password="secret123",
        sports_comment_type="api",
        sports_comment_api="yuanmeng_default",
        daily_comment_type="api",
        daily_comment_api="hitokoto_a",
    )
    calls = []

    async def fake_fetch(db, **kwargs):
        calls.append(kwargs)
        if kwargs["requested_key"] == "qzqi_yiyan":
            return ContentResult("运动文案", "qzqi_yiyan", False, 7)
        return ContentResult("每日文案", "hitokoto", False, 6)

    monkeypatch.setattr(ContentSourceService, "fetch_content", fake_fetch)

    sports = await PoetryService.get_sports_comment_selection(db_session, user)
    daily = await PoetryService.get_daily_comment_selection(db_session, user)

    assert sports.value == "运动文案"
    assert sports.source_key == "qzqi_yiyan"
    assert daily.value == "每日文案"
    assert daily.source_key == "hitokoto"
    assert [call["requested_key"] for call in calls] == ["qzqi_yiyan", "hitokoto"]


@pytest.mark.asyncio
async def test_custom_and_default_comments_do_not_call_external_sources(db_session, monkeypatch):
    user = User(
        id="user-2",
        username="local_user",
        password="secret123",
        sports_comment_type="custom",
        sports_custom_comment="完成五公里",
        daily_comment_type="default",
    )

    async def fail_fetch(*args, **kwargs):
        raise AssertionError("本地文案不应请求外部内容源")

    monkeypatch.setattr(ContentSourceService, "fetch_content", fail_fetch)

    sports = await PoetryService.get_sports_comment_selection(db_session, user)
    daily = await PoetryService.get_daily_comment_selection(db_session, user)

    assert sports.value == "完成五公里"
    assert sports.source_key is None
    assert daily.value == "今日学习内容总结，收获满满！"


@pytest.mark.asyncio
async def test_image_selection_uses_managed_source_and_worker_default_fallback(db_session, monkeypatch):
    user = User(
        id="user-3",
        username="image_user",
        password="secret123",
        sports_image_type="api",
        sports_image_provider="bing_uhd",
        sports_image_category="random",
    )
    captured = {}

    async def fake_fetch(db, **kwargs):
        captured.update(kwargs)
        return ContentResult("https://www.bing.com/image.jpg", "bing_uhd", False, 5)

    monkeypatch.setattr(ContentSourceService, "fetch_content", fake_fetch)

    selected = await PoetryService.get_sports_image_selection(db_session, user)

    assert selected.value == "https://www.bing.com/image.jpg"
    assert captured == {
        "source_type": "image",
        "requested_key": "bing_uhd",
        "category": "random",
        "static_fallback": None,
    }

    user.sports_image_type = "default"
    fallback = await PoetryService.get_sports_image_selection(db_session, user)
    assert fallback.value is None
    assert fallback.fallback is True


@pytest.mark.asyncio
async def test_user_image_category_must_belong_to_selected_source(db_session):
    source = await ContentSourceService.create_source(
        db_session,
        {
            "key": "category-source",
            "name": "分类源",
            "source_type": "image",
            "enabled": False,
            "priority": 10,
            "url_template": "https://images.example/{category}/",
            "query_params": {},
            "parse_mode": "redirect_image",
            "value_path": None,
            "attribution_path": None,
            "categories": ["pc", "mobile"],
            "timeout_seconds": 10,
        },
    )

    with pytest.raises(ValueError, match="图片分类"):
        await UserService.create_user(
            db_session,
            UserCreate(
                username="invalid_category_user",
                password="secret123",
                sports_image_type="api",
                sports_image_provider=source.key,
                sports_image_category="tablet",
            ),
        )
