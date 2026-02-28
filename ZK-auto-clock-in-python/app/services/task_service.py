"""
任务管理服务模块
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from typing import List, Optional
from datetime import datetime
from app.models.database import Task
from app.models.schemas import TaskProgress


class TaskService:
    """任务服务类"""

    @staticmethod
    async def create_task(
        db: AsyncSession,
        task_type: str,
        total: int = 0
    ) -> Task:
        """创建新任务"""
        task = Task(
            task_type=task_type,
            status="pending",
            progress_total=total,
            progress_current=0,
            progress_success=0,
            progress_failure=0,
        )

        db.add(task)
        await db.commit()
        await db.refresh(task)

        return task

    @staticmethod
    async def get_task(db: AsyncSession, task_id: str) -> Optional[Task]:
        """获取任务"""
        result = await db.execute(select(Task).where(Task.id == task_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def update_task(
        db: AsyncSession,
        task_id: str,
        **updates
    ) -> Optional[Task]:
        """更新任务"""
        task = await TaskService.get_task(db, task_id)
        if not task:
            return None

        for field, value in updates.items():
            if hasattr(task, field) and value is not None:
                setattr(task, field, value)

        task.updated_at = datetime.utcnow()

        await db.commit()
        await db.refresh(task)

        return task

    @staticmethod
    async def update_task_progress(
        db: AsyncSession,
        task_id: str,
        progress: dict
    ) -> Optional[Task]:
        """更新任务进度"""
        task = await TaskService.get_task(db, task_id)
        if not task:
            return None

        # 更新进度（累加）
        if 'current' in progress:
            task.progress_current += progress['current']
        if 'success' in progress:
            task.progress_success += progress['success']
        if 'failure' in progress:
            task.progress_failure += progress['failure']

        task.updated_at = datetime.utcnow()

        await db.commit()
        await db.refresh(task)

        return task

    @staticmethod
    async def complete_task(
        db: AsyncSession,
        task_id: str,
        status: str = "completed",
        result: Optional[dict] = None,
        error: Optional[str] = None
    ) -> Optional[Task]:
        """完成任务"""
        task = await TaskService.get_task(db, task_id)
        if not task:
            return None

        task.status = status
        task.completed_at = datetime.utcnow()
        task.updated_at = datetime.utcnow()

        if result:
            import json
            task.result_json = json.dumps(result, ensure_ascii=False)

        if error:
            task.error = error

        await db.commit()
        await db.refresh(task)

        return task

    @staticmethod
    async def list_all_tasks(db: AsyncSession, limit: int = 100) -> List[Task]:
        """列出所有任务"""
        result = await db.execute(
            select(Task)
            .order_by(Task.created_at.desc())
            .limit(limit)
        )
        return result.scalars().all()

    @staticmethod
    def calculate_progress_percent(task: Task) -> int:
        """计算进度百分比"""
        if task.progress_total == 0:
            return 0
        return int((task.progress_current / task.progress_total) * 100)
