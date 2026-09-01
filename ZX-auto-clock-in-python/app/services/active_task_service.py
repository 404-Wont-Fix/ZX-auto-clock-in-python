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
    task_id: str
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
    """活动任务服务类（单例模式）。

    任务以 task_id 为键存储（不再以 user_id 为键），
    避免同一用户的并发任务互相覆盖、以及 complete_task 删错条目。
    """

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
        """开始一个任务，返回 task_id（调用方需保存并在完成时回传）"""
        service = ActiveTaskService()

        task_id = f"{user_id}_{datetime.now().timestamp()}"

        async with ActiveTaskService._lock:
            # 仅提示同用户已有运行中任务，不再删除/覆盖它（按 task_id 独立跟踪）
            existing = next(
                (t for t in service._active_tasks.values() if t.user_id == user_id),
                None
            )
            if existing:
                logger.info(f"用户 {username} 已有活动任务 ({existing.task_id})，新任务将并行跟踪")

            service._active_tasks[task_id] = ActiveClockinTask(
                task_id=task_id,
                user_id=user_id,
                username=username,
                nickname=nickname,
                worker_api_id=worker_api_id,
                worker_api_name=worker_api_name,
                started_at=datetime.now(),
                status='running'
            )

            logger.info(f"[活动任务] 开始: {username} -> {worker_api_name or '后备API'} (task_id={task_id})")
            return task_id

    @staticmethod
    async def complete_task(task_id: str, success: bool = True):
        """按 task_id 完成任务（只会移除该 task_id 对应的条目，不会误删同用户新任务）"""
        service = ActiveTaskService()

        async with ActiveTaskService._lock:
            task = service._active_tasks.get(task_id)
            if task:
                task.status = 'completed' if success else 'failed'
                # 从活动任务列表中移除
                del service._active_tasks[task_id]
                elapsed = (datetime.now() - task.started_at).total_seconds()
                logger.info(f"[活动任务] 完成: {task.username} ({'成功' if success else '失败'}) - 耗时 {elapsed:.1f}秒 (task_id={task_id})")
            else:
                logger.debug(f"[活动任务] complete_task 未找到 task_id={task_id}（可能已被清理）")

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
        """根据用户ID获取其（首个）运行中任务"""
        service = ActiveTaskService()

        async with ActiveTaskService._lock:
            task = next(
                (t for t in service._active_tasks.values() if t.user_id == user_id),
                None
            )
            return task.to_dict() if task else None

    @staticmethod
    async def cleanup_stale_tasks(max_age_seconds: int = 300):
        """清理过期任务（超过 max_age_seconds 未完成的任务）"""
        service = ActiveTaskService()

        async with ActiveTaskService._lock:
            now = datetime.now()
            stale_ids = []

            for task_id, task in service._active_tasks.items():
                elapsed = (now - task.started_at).total_seconds()
                if elapsed > max_age_seconds:
                    stale_ids.append(task_id)
                    logger.warning(f"[活动任务] 清理过期任务: {task.username} (运行时间: {elapsed:.1f}秒, task_id={task_id})")

            for task_id in stale_ids:
                del service._active_tasks[task_id]

            return len(stale_ids)
