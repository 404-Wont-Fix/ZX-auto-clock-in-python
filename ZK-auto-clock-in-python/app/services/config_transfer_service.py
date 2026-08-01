"""无密钥导出与旧版配置导入。"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import Config, ContentSource, User, WorkerApi
from app.services.content_source_service import ContentSourceService
from app.services.worker_api_service import WorkerApiService


logger = logging.getLogger(__name__)


class ConfigTransferService:
    ALLOWED_CONFIG_KEYS = {
        "clockin_api_url",
        "clockin_api_token",
        "default_worker_api_id",
        "api_request_delay",
        "clockin_type_delay",
        "batch_size",
        "batch_delay",
        "parallel_tasks",
        "clockin_retry_count",
        "clockin_retry_delay",
        "clockin_timeout",
        "clockin_rate_limit_delay",
        "schedule_cron",
        "schedule_enabled",
        "schedule_timezone",
        "schedule_retry_count",
        "schedule_retry_delay",
        "retention_days",
    }
    SENSITIVE_CONFIG_KEYS = {"clockin_api_token"}
    TEXT_SOURCE_KEYS = {"poetry_all", "hitokoto", "qzqi_yiyan"}
    IMAGE_SOURCE_KEYS = {"bing", "bing_uhd", "komll", "loliapi", "cimuapi"}
    LEGACY_TEXT_PREFIXES = ("yuanmeng", "cenguigui", "klapi")

    USER_FIELDS = {
        "nickname",
        "enabled",
        "sports_comment_type",
        "sports_custom_comment",
        "sports_comment_api",
        "sports_image_type",
        "sports_image_provider",
        "sports_image_category",
        "daily_comment_type",
        "custom_daily_comment",
        "daily_comment_api",
    }

    @staticmethod
    def _as_bool(value: Any, default: bool = True) -> bool:
        if value is None:
            return default
        if isinstance(value, str):
            return value.strip().lower() in {"true", "1", "yes", "on"}
        return bool(value)

    @classmethod
    def _map_text_source(cls, value: Any, *, field: str, username: str, warnings: list[str]) -> str:
        normalized = str(value or "poetry_all").strip().lower()
        if normalized in cls.TEXT_SOURCE_KEYS:
            return normalized
        if normalized.startswith("poetry_"):
            warnings.append(f"用户 {username} 的 {field} 已映射到 poetry_all")
            return "poetry_all"
        if normalized.startswith("hitokoto_"):
            warnings.append(f"用户 {username} 的 {field} 已映射到 hitokoto")
            return "hitokoto"
        if normalized.startswith(cls.LEGACY_TEXT_PREFIXES):
            warnings.append(f"用户 {username} 的旧文字源 {normalized} 已映射到 qzqi_yiyan")
            return "qzqi_yiyan"
        warnings.append(f"用户 {username} 的未知文字源 {normalized} 已回退到 poetry_all")
        return "poetry_all"

    @classmethod
    def _map_image_source(cls, value: Any, *, username: str, warnings: list[str]) -> str:
        normalized = str(value or "bing").strip().lower()
        if normalized == "bing_uhd":
            warnings.append(f"用户 {username} 的旧 bing_uhd 已映射到 Bing 官方 UHD")
            return "bing_uhd"
        if normalized in cls.IMAGE_SOURCE_KEYS:
            return normalized
        warnings.append(f"用户 {username} 的未知图片源 {normalized} 已回退到 bing")
        return "bing"

    @classmethod
    async def export_data(cls, db: AsyncSession) -> dict:
        configs = list((await db.execute(select(Config))).scalars().all())
        users = list((await db.execute(select(User).order_by(User.username))).scalars().all())
        workers = list((await db.execute(select(WorkerApi).order_by(WorkerApi.name))).scalars().all())
        sources = list(
            (
                await db.execute(
                    select(ContentSource)
                    .where(ContentSource.archived.is_(False))
                    .order_by(ContentSource.source_type, ContentSource.priority, ContentSource.name)
                )
            ).scalars().all()
        )

        config_data = {
            config.key: config.value
            for config in configs
            if config.key in cls.ALLOWED_CONFIG_KEYS and config.key not in cls.SENSITIVE_CONFIG_KEYS
        }
        user_data = []
        for user in users:
            serialized = user.to_dict()
            user_data.append(
                {
                    key: serialized.get(key)
                    for key in ("username", *sorted(cls.USER_FIELDS), "password_configured")
                }
            )
        worker_data = [
            {
                "name": worker.name,
                "url": worker.url,
                "enabled": bool(worker.enabled),
                "note": worker.note,
                "token_configured": bool(worker.token),
            }
            for worker in workers
        ]
        source_data = [
            {
                "key": source.key,
                "name": source.name,
                "source_type": source.source_type,
                "enabled": bool(source.enabled),
                "priority": source.priority,
                "url_template": source.url_template,
                "query_params": source.query_params,
                "parse_mode": source.parse_mode,
                "value_path": source.value_path,
                "attribution_path": source.attribution_path,
                "categories": source.categories,
                "timeout_seconds": source.timeout_seconds,
            }
            for source in sources
        ]

        return {
            "version": "2.0",
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "config": config_data,
            "users": user_data,
            "worker_apis": worker_data,
            "content_sources": source_data,
        }

    @classmethod
    async def _import_configs(
        cls,
        db: AsyncSession,
        config_data: Any,
        *,
        legacy: bool,
        report: dict,
    ) -> None:
        if not isinstance(config_data, dict):
            report["warnings"].append("配置数据格式无效，已跳过")
            return
        for key, value in config_data.items():
            if key not in cls.ALLOWED_CONFIG_KEYS:
                report["warnings"].append(f"未知配置键 {key} 已跳过")
                continue
            if key in cls.SENSITIVE_CONFIG_KEYS and not legacy:
                report["warnings"].append(f"2.0 文件中的敏感配置 {key} 已跳过")
                continue
            result = await db.execute(select(Config).where(Config.key == key))
            config = result.scalar_one_or_none()
            if config:
                config.value = str(value)
            else:
                db.add(Config(key=key, value=str(value)))
            report["configs"] += 1

    @classmethod
    async def _import_users(
        cls,
        db: AsyncSession,
        users_data: Any,
        *,
        legacy: bool,
        report: dict,
    ) -> None:
        if not isinstance(users_data, list):
            report["warnings"].append("用户数据格式无效，已跳过")
            return
        for item in users_data:
            if not isinstance(item, dict):
                report["warnings"].append("一条用户数据格式无效，已跳过")
                continue
            username = str(item.get("username") or "").strip()
            if not username:
                report["warnings"].append("一条用户数据缺少用户名，已跳过")
                continue
            result = await db.execute(select(User).where(User.username == username))
            user = result.scalar_one_or_none()
            password = item.get("password") if legacy else None
            if user is None and not password:
                report["warnings"].append(f"用户 {username} 缺少密码，无法在新数据库创建")
                continue
            if user is None:
                user = User(username=username, password=str(password))
                db.add(user)
                report["users_created"] += 1
            else:
                report["users_updated"] += 1
                if password:
                    user.password = str(password)

            for field in cls.USER_FIELDS:
                if field not in item:
                    continue
                value = item[field]
                if field == "enabled":
                    value = cls._as_bool(value, default=True)
                elif field in {"sports_comment_api", "daily_comment_api"}:
                    value = cls._map_text_source(
                        value,
                        field=field,
                        username=username,
                        warnings=report["warnings"],
                    )
                elif field == "sports_image_provider":
                    value = cls._map_image_source(value, username=username, warnings=report["warnings"])
                setattr(user, field, value)

            user.sports_comment_type = user.sports_comment_type or "default"
            user.daily_comment_type = user.daily_comment_type or "default"
            user.sports_comment_api = user.sports_comment_api or "poetry_all"
            user.daily_comment_api = user.daily_comment_api or "poetry_all"
            user.sports_image_type = user.sports_image_type or "default"
            user.sports_image_provider = user.sports_image_provider or "bing"
            user.sports_image_category = user.sports_image_category or "random"

    @classmethod
    async def _import_workers(
        cls,
        db: AsyncSession,
        workers_data: Any,
        *,
        legacy: bool,
        report: dict,
    ) -> None:
        if not isinstance(workers_data, list):
            report["warnings"].append("Worker 数据格式无效，已跳过")
            return
        for item in workers_data:
            if not isinstance(item, dict):
                report["warnings"].append("一条 Worker 数据格式无效，已跳过")
                continue
            name = str(item.get("name") or "").strip()
            url = str(item.get("url") or "").strip()
            token = item.get("token") if legacy else None
            if not name or not url:
                report["warnings"].append("一条 Worker 数据缺少名称或地址，已跳过")
                continue
            url = WorkerApiService._normalize_url(url)
            result = await db.execute(select(WorkerApi).where(WorkerApi.url == url))
            worker = result.scalar_one_or_none()
            if worker is None and not token:
                report["warnings"].append(f"Worker {name} 缺少 Token，无法在新数据库创建")
                continue
            if worker is None:
                worker = WorkerApi(name=name, url=url, token=str(token))
                db.add(worker)
            elif token:
                worker.token = str(token)
            worker.name = name
            worker.enabled = cls._as_bool(item.get("enabled"), default=True)
            worker.note = item.get("note")
            report["workers"] += 1

    @classmethod
    async def _import_sources(cls, db: AsyncSession, sources_data: Any, report: dict) -> None:
        if sources_data is None:
            return
        if not isinstance(sources_data, list):
            report["warnings"].append("内容源数据格式无效，已跳过")
            return
        for item in sources_data:
            if not isinstance(item, dict):
                report["warnings"].append("一条内容源数据格式无效，已跳过")
                continue
            key = str(item.get("key") or "").strip()
            if not key:
                report["warnings"].append("一条内容源数据缺少 key，已跳过")
                continue
            definition = {
                field: item.get(field)
                for field in (
                    "name",
                    "source_type",
                    "priority",
                    "url_template",
                    "query_params",
                    "parse_mode",
                    "value_path",
                    "attribution_path",
                    "categories",
                    "timeout_seconds",
                )
            }
            definition["enabled"] = False
            existing_result = await db.execute(select(ContentSource).where(ContentSource.key == key))
            existing = existing_result.scalar_one_or_none()
            try:
                if existing:
                    await ContentSourceService.update_source(
                        db,
                        existing.id,
                        definition,
                        commit=False,
                    )
                else:
                    await ContentSourceService.create_source(
                        db,
                        {"key": key, **definition},
                        commit=False,
                    )
            except (LookupError, ValueError) as exc:
                report["warnings"].append(f"内容源 {key} 导入失败：{exc}")
                continue
            report["content_sources"] += 1
            if cls._as_bool(item.get("enabled"), default=False):
                report["warnings"].append(f"内容源 {key} 已导入为停用，请测试成功后再启用")

    @classmethod
    async def import_data(cls, db: AsyncSession, payload: Any) -> dict:
        if not isinstance(payload, dict):
            raise ValueError("导入文件必须是 JSON 对象")
        version = str(payload.get("version") or "")
        if version not in {"1.0", "2.0"}:
            raise ValueError("仅支持 1.0 或 2.0 配置文件")
        legacy = version == "1.0"
        report = {
            "version": version,
            "configs": 0,
            "users_created": 0,
            "users_updated": 0,
            "workers": 0,
            "content_sources": 0,
            "warnings": [],
        }
        try:
            await cls._import_configs(db, payload.get("config", {}), legacy=legacy, report=report)
            await cls._import_users(db, payload.get("users", []), legacy=legacy, report=report)
            await cls._import_workers(db, payload.get("worker_apis", []), legacy=legacy, report=report)
            if not legacy:
                await cls._import_sources(db, payload.get("content_sources"), report)
            await db.commit()
        except Exception:
            await db.rollback()
            raise

        logger.info(
            "配置导入完成: version=%s configs=%s users_created=%s users_updated=%s workers=%s sources=%s warnings=%s",
            version,
            report["configs"],
            report["users_created"],
            report["users_updated"],
            report["workers"],
            report["content_sources"],
            len(report["warnings"]),
        )
        return report
