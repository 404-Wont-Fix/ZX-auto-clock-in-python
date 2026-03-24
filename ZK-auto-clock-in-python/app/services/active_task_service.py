"""
活动任务追踪服务模块
用于追踪当前正在执行的打卡任务
"""
from typing import Dict, List, Optional
from datetime import datetime
from dataclasses import dataclass, asdict
import asyncio
import logging

logger = logging.getLogger(__name__)


@dataclass
class ActiveClockinTask:
    """活动打卡任务"""
    user_id: str
    username: str
    nickname: str
    worker_api_id: Optional[str]
    worker_api_name: Optional[str]
    started_at: datetime
    status: str  # 'running', 'completed', 'failed'

    def to_dict(self):
        """转换为字典"""
        data = asdict(self)
        data['started_at'] = self.started_at.isoformat()
        # 计算已用时间
        elapsed = (datetime.now() - self.started_at).total_seconds()
        data['elapsed_seconds'] = int(elapsed)
        return data


class ActiveTaskService:
    """活动任务服务类（单例模式）"""

    _instance = None
    _lock = asyncio.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._active_tasks: Dict[str, ActiveClockinTask] = {}
        return cls._instance

    @staticmethod
    async def start_task(
        user_id: str,
        username: str,
        nickname: str,
        worker_api_id: Optional[str] = None,
        worker_api_name: Optional[str] = None
    ) -> str:
        """开始一个任务"""
        service = ActiveTaskService()

        task_id = f"{user_id}_{datetime.now().timestamp()}"

        async with ActiveTaskService._lock:
            # 移除该用户之前的任务（如果有）
            if user_id in service._active_tasks:
                logger.info(f"用户 {username} 已有活动任务，将被新任务替换")

            service._active_tasks[user_id] = ActiveClockinTask(
                user_id=user_id,
                username=username,
                nickname=nickname,
                worker_api_id=worker_api_id,
                worker_api_name=worker_api_name,
                started_at=datetime.now(),
                status='running'
            )

            logger.info(f"[活动任务] 开始: {username} -> {worker_api_name or '后备API'}")
            return task_id

    @staticmethod
    async def complete_task(user_id: str, success: bool = True):
        """完成任务"""
        service = ActiveTaskService()

        async with ActiveTaskService._lock:
            task = service._active_tasks.get(user_id)
            if task:
                task.status = 'completed' if success else 'failed'
                # 从活动任务列表中移除
                del service._active_tasks[user_id]
                elapsed = (datetime.now() - task.started_at).total_seconds()
                logger.info(f"[活动任务] 完成: {task.username} ({'成功' if success else '失败'}) - 耗时 {elapsed:.1f}秒")

    @staticmethod
    async def get_active_tasks() -> List[Dict]:
        """获取所有活动任务"""
        service = ActiveTaskService()

        async with ActiveTaskService._lock:
            return [task.to_dict() for task in service._active_tasks.values()]

    @staticmethod
    async def get_active_task_count() -> int:
        """获取活动任务数量"""
        service = ActiveTaskService()

        async with ActiveTaskService._lock:
            return len(service._active_tasks)

    @staticmethod
    async def get_task_by_user(user_id: str) -> Optional[Dict]:
        """根据用户ID获取任务"""
        service = ActiveTaskService()

        async with ActiveTaskService._lock:
            task = service._active_tasks.get(user_id)
            return task.to_dict() if task else None

    @staticmethod
    async def cleanup_stale_tasks(max_age_seconds: int = 300):
        """清理过期任务（5分钟未完成的任务）"""
        service = ActiveTaskService()

        async with ActiveTaskService._lock:
            now = datetime.now()
            stale_users = []

            for user_id, task in service._active_tasks.items():
                elapsed = (now - task.started_at).total_seconds()
                if elapsed > max_age_seconds:
                    stale_users.append(user_id)
                    logger.warning(f"[活动任务] 清理过期任务: {task.username} (运行时间: {elapsed:.1f}秒)")

            for user_id in stale_users:
                del service._active_tasks[user_id]

            return len(stale_users)
