"""用户文字与图片策略到受控内容源的适配层。"""

from __future__ import annotations

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import User
from app.services.content_source_service import ContentResult, ContentSourceService


DEFAULT_DAILY_COMMENT = "今日学习内容总结，收获满满！"
DEFAULT_SPORTS_COMMENT = "已运动！"


class PoetryService:
    """保留旧类名，内部统一委托给可管理内容源。"""

    LEGACY_TEXT_SOURCE_MAP = {
        "远梦api": "qzqi_yiyan",
        "yuanmeng": "qzqi_yiyan",
        "yuanmeng_default": "qzqi_yiyan",
        "cenguigui": "qzqi_yiyan",
        "cenguigui_default": "qzqi_yiyan",
        "klapi": "qzqi_yiyan",
        "klapi_default": "qzqi_yiyan",
        "qzqi": "qzqi_yiyan",
        "qzqi_yiyan": "qzqi_yiyan",
    }

    @classmethod
    def normalize_text_source_key(cls, source_key: Optional[str]) -> Optional[str]:
        if not source_key:
            return None
        normalized = source_key.strip()
        lowered = normalized.lower()
        if lowered in cls.LEGACY_TEXT_SOURCE_MAP:
            return cls.LEGACY_TEXT_SOURCE_MAP[lowered]
        if lowered.startswith("poetry_"):
            return "poetry_all"
        if lowered.startswith("hitokoto_"):
            return "hitokoto"
        return normalized

    @staticmethod
    def normalize_image_source_key(source_key: Optional[str]) -> Optional[str]:
        if not source_key:
            return None
        normalized = source_key.strip().lower()
        if normalized in {"bing_uhd", "bing_uhd_official"}:
            return "bing_uhd"
        return normalized

    @staticmethod
    async def get_daily_comment_selection(
        db: AsyncSession,
        user: User,
    ) -> ContentResult:
        if user.daily_comment_type == "custom":
            return ContentResult(
                value=user.custom_daily_comment or DEFAULT_DAILY_COMMENT,
                source_key=None,
                fallback=True,
            )
        if user.daily_comment_type != "api":
            return ContentResult(
                value=DEFAULT_DAILY_COMMENT,
                source_key=None,
                fallback=True,
            )
        return await ContentSourceService.fetch_content(
            db,
            source_type="text",
            requested_key=PoetryService.normalize_text_source_key(user.daily_comment_api),
            static_fallback=DEFAULT_DAILY_COMMENT,
        )

    @staticmethod
    async def get_sports_comment_selection(
        db: AsyncSession,
        user: User,
    ) -> ContentResult:
        if user.sports_comment_type == "custom":
            return ContentResult(
                value=user.sports_custom_comment or DEFAULT_SPORTS_COMMENT,
                source_key=None,
                fallback=True,
            )
        if user.sports_comment_type != "api":
            return ContentResult(
                value=DEFAULT_SPORTS_COMMENT,
                source_key=None,
                fallback=True,
            )
        return await ContentSourceService.fetch_content(
            db,
            source_type="text",
            requested_key=PoetryService.normalize_text_source_key(user.sports_comment_api),
            static_fallback=DEFAULT_SPORTS_COMMENT,
        )

    @staticmethod
    async def get_sports_image_selection(
        db: AsyncSession,
        user: User,
    ) -> ContentResult:
        if user.sports_image_type != "api":
            return ContentResult(
                value=None,
                source_key=None,
                fallback=True,
            )
        return await ContentSourceService.fetch_content(
            db,
            source_type="image",
            requested_key=PoetryService.normalize_image_source_key(user.sports_image_provider),
            category=user.sports_image_category or "random",
            static_fallback=None,
        )

    @staticmethod
    async def get_daily_comment(user: User, db: Optional[AsyncSession] = None) -> str:
        """兼容旧调用；生产调用应传入数据库会话。"""
        if db is None:
            if user.daily_comment_type == "custom":
                return user.custom_daily_comment or DEFAULT_DAILY_COMMENT
            return DEFAULT_DAILY_COMMENT
        result = await PoetryService.get_daily_comment_selection(db, user)
        return result.value or DEFAULT_DAILY_COMMENT

    @staticmethod
    async def get_sports_comment(user: User, db: Optional[AsyncSession] = None) -> str:
        """兼容旧调用；生产调用应传入数据库会话。"""
        if db is None:
            if user.sports_comment_type == "custom":
                return user.sports_custom_comment or DEFAULT_SPORTS_COMMENT
            return DEFAULT_SPORTS_COMMENT
        result = await PoetryService.get_sports_comment_selection(db, user)
        return result.value or DEFAULT_SPORTS_COMMENT

    @staticmethod
    async def get_sports_image(user: User, db: Optional[AsyncSession] = None):
        """兼容旧调用并保持 Worker 所需的字典形状。"""
        if db is None or user.sports_image_type != "api":
            return None
        result = await PoetryService.get_sports_image_selection(db, user)
        if not result.value:
            return None
        return {"url": result.value, "use_cw": False}
