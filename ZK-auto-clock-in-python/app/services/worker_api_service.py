"""
Worker API 服务模块
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
from typing import List, Optional
from datetime import datetime, timedelta
import asyncio
import httpx
import logging

from app.models.database import WorkerApi
from app.models.schemas import WorkerApiCreate, WorkerApiUpdate

logger = logging.getLogger(__name__)


class WorkerApiService:
    """Worker API 服务类"""

    # 轮询索引和锁
    _round_robin_index = 0
    _round_robin_lock = asyncio.Lock()

    # 被熔断 API 的自动恢复窗口（秒）：距上次失败超过该时长后自动重新可用
    RECOVERY_SECONDS = 300  # 5 分钟
    # 连续失败多少次后熔断（与文档"3+ 次连续失败"保持一致）
    FAILURE_THRESHOLD = 3

    @staticmethod
    def _normalize_url(url: str) -> str:
        """规范化 URL，确保有协议前缀且末尾无斜杠"""
        url = url.strip()
        # 如果没有协议前缀，默认添加 https://
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        # 去除末尾的斜杠
        url = url.rstrip('/')
        return url

    @staticmethod
    async def get_all_apis(db: AsyncSession) -> List[WorkerApi]:
        """获取所有 Worker API"""
        result = await db.execute(
            select(WorkerApi).order_by(WorkerApi.created_at.desc())
        )
        return result.scalars().all()

    @staticmethod
    async def get_enabled_apis(db: AsyncSession) -> List[WorkerApi]:
        """获取所有启用的 Worker API"""
        result = await db.execute(
            select(WorkerApi)
            .where(WorkerApi.enabled == True)
            .order_by(WorkerApi.created_at.desc())
        )
        return result.scalars().all()

    @staticmethod
    async def get_available_apis(db: AsyncSession) -> List[WorkerApi]:
        """获取所有可用的 Worker API（enabled=True 且 available=True）。

        附带时间恢复：被熔断（available=False）的 API 若距上次失败已超过
        RECOVERY_SECONDS 秒，会自动重新标记为可用并清零失败计数，避免一次失败
        就永久下线（原先只能靠一次成功调用才能恢复，而被禁的 API 收不到流量，
        导致永远无法自愈）。
        """
        recovery_cutoff = datetime.utcnow() - timedelta(seconds=WorkerApiService.RECOVERY_SECONDS)
        recovered = await db.execute(
            update(WorkerApi)
            .where(
                WorkerApi.enabled == True,
                WorkerApi.available == False,
                WorkerApi.last_failure < recovery_cutoff,
            )
            .values(available=True, failure_count=0)
        )
        if recovered.rowcount > 0:
            await db.commit()
            logger.info(f"自动恢复了 {recovered.rowcount} 个被熔断的 Worker API（距上次失败超过 {WorkerApiService.RECOVERY_SECONDS} 秒）")

        result = await db.execute(
            select(WorkerApi)
            .where(WorkerApi.enabled == True, WorkerApi.available == True)
            .order_by(WorkerApi.created_at.desc())
        )
        return result.scalars().all()

    @staticmethod
    async def get_api_by_id(db: AsyncSession, api_id: str) -> Optional[WorkerApi]:
        """根据 ID 获取 Worker API"""
        result = await db.execute(select(WorkerApi).where(WorkerApi.id == api_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_api_by_url(db: AsyncSession, url: str) -> Optional[WorkerApi]:
        """根据 URL 获取 Worker API"""
        result = await db.execute(select(WorkerApi).where(WorkerApi.url == url))
        return result.scalar_one_or_none()

    @staticmethod
    async def create_api(db: AsyncSession, api_data: WorkerApiCreate) -> WorkerApi:
        """创建新的 Worker API"""
        # 规范化 URL
        normalized_url = WorkerApiService._normalize_url(api_data.url)

        # 检查 URL 是否已存在
        existing = await WorkerApiService.get_api_by_url(db, normalized_url)
        if existing:
            raise ValueError(f"URL '{normalized_url}' 已存在")

        # 创建 API 对象
        api = WorkerApi(
            name=api_data.name,
            url=normalized_url,
            token=api_data.token,
            note=api_data.note,
        )

        db.add(api)
        await db.commit()
        await db.refresh(api)

        logger.info(f"创建 Worker API: {api.name} ({api.url})")
        return api

    @staticmethod
    async def update_api(
        db: AsyncSession, api_id: str, updates: WorkerApiUpdate
    ) -> Optional[WorkerApi]:
        """更新 Worker API"""
        api = await WorkerApiService.get_api_by_id(db, api_id)
        if not api:
            return None

        # 如果更新 URL，规范化并检查是否冲突
        if updates.url and updates.url != api.url:
            normalized_url = WorkerApiService._normalize_url(updates.url)
            existing = await WorkerApiService.get_api_by_url(db, normalized_url)
            if existing:
                raise ValueError(f"URL '{normalized_url}' 已存在")
            # 使用规范化的 URL
            updates.url = normalized_url

        # 构建更新数据
        update_data = {}
        for field, value in updates.model_dump(exclude_unset=True).items():
            if value is None:
                continue
            setattr(api, field, value)
            update_data[field] = value

        await db.commit()
        await db.refresh(api)

        safe_fields = sorted(field for field in update_data if field != 'token')
        if 'token' in update_data:
            safe_fields.append('token_configured')
        logger.info("更新 Worker API: %s - fields=%s", api.name, safe_fields)
        return api

    @staticmethod
    async def delete_api(db: AsyncSession, api_id: str) -> dict:
        """删除 Worker API"""
        # 检查是否为最后一个 API
        all_apis = await WorkerApiService.get_all_apis(db)
        if len(all_apis) <= 1:
            return {
                'success': False,
                'error': '至少需要保留一个 Worker API，无法删除'
            }

        api = await WorkerApiService.get_api_by_id(db, api_id)
        if not api:
            return {'success': False, 'error': 'Worker API 不存在'}

        api_name = api.name
        await db.delete(api)
        await db.commit()

        logger.info(f"删除 Worker API: {api_name}")
        return {'success': True}

    @staticmethod
    async def test_connection(db: AsyncSession, api_id: str) -> dict:
        """测试 Worker API 连接"""
        api = await WorkerApiService.get_api_by_id(db, api_id)
        if not api:
            return {'success': False, 'message': 'Worker API 不存在'}

        start_time = datetime.now()

        try:
            # 尝试调用 health 端点
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{api.url}/health",
                    headers={"Authorization": f"Bearer {api.token}"}
                )

                latency_ms = int((datetime.now() - start_time).total_seconds() * 1000)

                if response.status_code == 200:
                    # 更新最后检查时间
                    await WorkerApiService._update_check_time(db, api)
                    return {
                        'success': True,
                        'message': '连接成功',
                        'latency_ms': latency_ms
                    }
                else:
                    return {
                        'success': False,
                        'message': f'HTTP {response.status_code}: {response.text[:100]}',
                        'latency_ms': latency_ms
                    }

        except httpx.TimeoutException:
            return {'success': False, 'message': '连接超时'}
        except Exception as e:
            return {'success': False, 'message': str(e)}

    @staticmethod
    async def reset_availability(db: AsyncSession, api_id: str) -> Optional[WorkerApi]:
        """重置 Worker API 可用状态"""
        api = await WorkerApiService.get_api_by_id(db, api_id)
        if not api:
            return None

        api.available = True
        api.failure_count = 0
        await db.commit()
        await db.refresh(api)

        logger.info(f"重置 Worker API 可用状态: {api.name}")
        return api

    @staticmethod
    async def get_next_api(db: AsyncSession) -> Optional[WorkerApi]:
        """轮询获取下一个可用的 Worker API"""
        async with WorkerApiService._round_robin_lock:
            available_apis = await WorkerApiService.get_available_apis(db)

            if not available_apis:
                logger.warning("没有可用的 Worker API")
                return None

            # 轮询选择
            api = available_apis[WorkerApiService._round_robin_index % len(available_apis)]
            WorkerApiService._round_robin_index += 1

            logger.debug(f"选择 Worker API: {api.name} (索引: {WorkerApiService._round_robin_index - 1}, 总数: {len(available_apis)})")
            return api

    @staticmethod
    async def increment_requests(db: AsyncSession, api_id: str) -> bool:
        """增加请求计数"""
        try:
            await db.execute(
                update(WorkerApi)
                .where(WorkerApi.id == api_id)
                .values(total_requests=WorkerApi.total_requests + 1)
            )
            await db.commit()
            return True
        except Exception as e:
            logger.error(f"更新请求计数失败: {e}")
            return False

    @staticmethod
    async def mark_success(db: AsyncSession, api_id: str) -> bool:
        """标记 API 调用成功"""
        try:
            now = datetime.utcnow()
            await db.execute(
                update(WorkerApi)
                .where(WorkerApi.id == api_id)
                .values(
                    last_success=now,
                    last_check=now,
                    failure_count=0,
                    available=True,
                    total_success=WorkerApi.total_success + 1,
                )
            )
            await db.commit()
            return True
        except Exception as e:
            logger.error(f"标记成功失败: {e}")
            return False

    @staticmethod
    async def mark_failure(db: AsyncSession, api_id: str) -> bool:
        """标记 API 调用失败"""
        try:
            now = datetime.utcnow()
            await db.execute(
                update(WorkerApi)
                .where(WorkerApi.id == api_id)
                .values(
                    last_failure=now,
                    last_check=now,
                    failure_count=WorkerApi.failure_count + 1,
                    total_failure=WorkerApi.total_failure + 1,
                )
            )

            # 如果连续失败次数达到阈值，标记为不可用（5 分钟后会被自动恢复）
            api = await WorkerApiService.get_api_by_id(db, api_id)
            if api and api.failure_count >= WorkerApiService.FAILURE_THRESHOLD:
                await db.execute(
                    update(WorkerApi)
                    .where(WorkerApi.id == api_id)
                    .values(available=False)
                )
                logger.warning(f"Worker API {api.name} 连续失败 {api.failure_count} 次，标记为不可用（{WorkerApiService.RECOVERY_SECONDS} 秒后自动恢复）")

            await db.commit()
            return True
        except Exception as e:
            logger.error(f"标记失败失败: {e}")
            return False

    @staticmethod
    async def _update_check_time(db: AsyncSession, api: WorkerApi):
        """更新最后检查时间"""
        try:
            api.last_check = datetime.utcnow()
            await db.commit()
        except Exception as e:
            logger.error(f"更新检查时间失败: {e}")
