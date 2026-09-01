"""持久化任务存储与统一打卡任务编排。"""

from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, timedelta, timezone
from typing import Iterable, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.models.database import ClockinResult, Task, User, utc_now
from app.services.clockin_service import ClockinService


ACTIVE_TASK_STATUSES = ("pending", "running")


class ActiveTaskConflict(RuntimeError):
    def __init__(self, task_id: str):
        self.task_id = task_id
        super().__init__(f"已有打卡任务正在执行: {task_id}")


class TaskService:
    """Task 表的最小持久化操作。"""

    @staticmethod
    async def create_task(
        db: AsyncSession,
        task_type: str,
        total: int = 0,
        *,
        scope: str = "all",
        target_date: Optional[str] = None,
        user_ids: Optional[Iterable[str]] = None,
        triggered_by: str = "manual",
    ) -> Task:
        task = Task(
            task_type=task_type,
            status="pending",
            scope=scope,
            target_date=target_date or TaskOrchestrator.beijing_today(),
            user_ids_json=json.dumps(list(user_ids or []), ensure_ascii=False),
            triggered_by=triggered_by,
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
        return await db.get(Task, task_id)

    @staticmethod
    async def get_active_task(db: AsyncSession) -> Optional[Task]:
        result = await db.execute(
            select(Task)
            .where(Task.task_type == "clockin", Task.status.in_(ACTIVE_TASK_STATUSES))
            .order_by(Task.created_at.asc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_tasks(
        db: AsyncSession,
        *,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> list[Task]:
        statement = select(Task).where(Task.task_type == "clockin")
        if status == "active":
            statement = statement.where(Task.status.in_(ACTIVE_TASK_STATUSES))
        elif status:
            statement = statement.where(Task.status == status)
        result = await db.execute(statement.order_by(Task.created_at.desc()).limit(limit))
        return list(result.scalars().all())

    @staticmethod
    async def mark_running(db: AsyncSession, task: Task) -> Task:
        task.status = "running"
        task.started_at = utc_now()
        task.updated_at = utc_now()
        await db.commit()
        return task

    @staticmethod
    async def record_progress(
        db: AsyncSession,
        task: Task,
        *,
        success: bool,
    ) -> Task:
        task.progress_current = (task.progress_current or 0) + 1
        if success:
            task.progress_success = (task.progress_success or 0) + 1
        else:
            task.progress_failure = (task.progress_failure or 0) + 1
        task.updated_at = utc_now()
        await db.commit()
        return task

    @staticmethod
    async def increment_progress(db: AsyncSession, task_id: str, *, success: bool) -> None:
        """并发安全的进度累加：在 SQL 层做 +1，避免 read-modify-write 的 lost update。"""
        await db.execute(
            update(Task)
            .where(Task.id == task_id)
            .values(
                progress_current=Task.progress_current + 1,
                progress_success=Task.progress_success + (1 if success else 0),
                progress_failure=Task.progress_failure + (0 if success else 1),
                updated_at=utc_now(),
            )
        )
        await db.commit()

    @staticmethod
    async def complete_task(
        db: AsyncSession,
        task: Task,
        *,
        status: str = "completed",
        result: Optional[dict] = None,
        error: Optional[str] = None,
    ) -> Task:
        task.status = status
        task.completed_at = utc_now()
        task.updated_at = utc_now()
        task.result_json = json.dumps(result, ensure_ascii=False) if result is not None else None
        task.error = error
        await db.commit()
        return task

    @staticmethod
    def calculate_progress_percent(task: Task) -> int:
        if not task.progress_total:
            return 100 if task.status == "completed" else 0
        return int((task.progress_current / task.progress_total) * 100)


class TaskOrchestrator:
    """单进程内的持久打卡任务入口。"""

    _enqueue_lock = asyncio.Lock()

    def __init__(self, session_factory: Optional[async_sessionmaker] = None):
        if session_factory is None:
            from app.core.database import AsyncSessionLocal

            session_factory = AsyncSessionLocal
        self.session_factory = session_factory
        self._background_tasks: set[asyncio.Task] = set()

    @staticmethod
    def beijing_today() -> str:
        return datetime.now(timezone(timedelta(hours=8))).date().isoformat()

    @staticmethod
    def _validate_target_date(target_date: str) -> str:
        try:
            return date.fromisoformat(target_date).isoformat()
        except ValueError as exc:
            raise ValueError("date 必须是 YYYY-MM-DD") from exc

    @staticmethod
    async def latest_results_by_user(
        db: AsyncSession,
        *,
        target_date: str,
        user_ids: Iterable[str],
    ) -> dict[str, ClockinResult]:
        ids = list(user_ids)
        if not ids:
            return {}
        result_rows = await db.execute(
            select(ClockinResult)
            .where(
                ClockinResult.date == target_date,
                ClockinResult.user_id.in_(ids),
            )
            .order_by(ClockinResult.timestamp.desc(), ClockinResult.created_at.desc())
        )
        latest_by_user: dict[str, ClockinResult] = {}
        for clockin_result in result_rows.scalars().all():
            latest_by_user.setdefault(clockin_result.user_id, clockin_result)
        return latest_by_user

    @staticmethod
    async def select_user_ids(
        db: AsyncSession,
        *,
        scope: str,
        target_date: str,
        requested_user_ids: Iterable[str],
    ) -> list[str]:
        if scope not in {"all", "failed", "users"}:
            raise ValueError("scope 必须是 all、failed 或 users")
        TaskOrchestrator._validate_target_date(target_date)

        users_result = await db.execute(
            select(User)
            .where(User.enabled.is_(True))
            .order_by(User.created_at.asc(), User.username.asc())
        )
        enabled_users = list(users_result.scalars().all())
        by_id = {user.id: user for user in enabled_users}

        if scope == "all":
            return [user.id for user in enabled_users]

        if scope == "users":
            requested = list(dict.fromkeys(requested_user_ids))
            if not requested:
                raise ValueError("users 范围必须提供 user_ids")
            missing = [user_id for user_id in requested if user_id not in by_id]
            if missing:
                raise ValueError("user_ids 包含不存在或未启用的用户")
            return requested

        if not enabled_users:
            return []
        latest_by_user = await TaskOrchestrator.latest_results_by_user(
            db,
            target_date=target_date,
            user_ids=by_id,
        )
        return [
            user.id
            for user in enabled_users
            if user.id in latest_by_user and not latest_by_user[user.id].success
        ]

    async def enqueue_task(
        self,
        db: AsyncSession,
        *,
        scope: str,
        target_date: Optional[str],
        requested_user_ids: Iterable[str],
        triggered_by: str,
        launch: bool = True,
    ) -> Task:
        target_date = self._validate_target_date(target_date or self.beijing_today())
        async with self._enqueue_lock:
            active = await TaskService.get_active_task(db)
            if active:
                raise ActiveTaskConflict(active.id)
            user_ids = await self.select_user_ids(
                db,
                scope=scope,
                target_date=target_date,
                requested_user_ids=requested_user_ids,
            )
            task = await TaskService.create_task(
                db,
                "clockin",
                len(user_ids),
                scope=scope,
                target_date=target_date,
                user_ids=user_ids,
                triggered_by=triggered_by,
            )

        if launch:
            self.launch_task(task.id)
        return task

    def launch_task(self, task_id: str) -> asyncio.Task:
        background_task = asyncio.create_task(self.run_task(task_id))
        self._background_tasks.add(background_task)
        background_task.add_done_callback(self._background_tasks.discard)
        return background_task

    async def _available_api_count(self) -> int:
        """当前可用的 Worker API 数量（用于限制并发，避免挤在同一 worker 上触发限流）。"""
        try:
            from app.services.worker_api_service import WorkerApiService

            async with self.session_factory() as db:
                apis = await WorkerApiService.get_available_apis(db)
            return len(apis)
        except Exception:
            return 0

    def _resolve_concurrency(self, n_apis: int) -> int:
        """并发度 = min(parallel_tasks, 可用 API 数)；无 API 时退化为 parallel_tasks。"""
        if n_apis > 0:
            limit = min(settings.parallel_tasks, n_apis)
        else:
            limit = settings.parallel_tasks
        return max(1, limit)

    async def run_task(self, task_id: str) -> None:
        # 1. 标记 running 并读取目标用户列表（独立短 session）
        async with self.session_factory() as db:
            task = await TaskService.get_task(db, task_id)
            if not task or task.status != "pending":
                return
            user_ids = list(task.user_ids)
            triggered_by = task.triggered_by
            await TaskService.mark_running(db, task)

        if not user_ids:
            async with self.session_factory() as db:
                task = await TaskService.get_task(db, task_id)
                if task and task.status == "running":
                    await TaskService.complete_task(db, task, result={"results": []})
            return

        # 2. 有界并行执行；每个用户使用独立 DB session，进度走 SQL 原子 +1
        max_concurrent = self._resolve_concurrency(await self._available_api_count())
        semaphore = asyncio.Semaphore(max_concurrent)

        async def run_one(user_id: str) -> dict:
            async with semaphore:
                try:
                    async with self.session_factory() as udb:
                        outcome = await ClockinService.trigger_user(
                            udb, user_id, triggered_by=triggered_by
                        )
                    succeeded = bool(outcome.get("success"))
                    error = outcome.get("error")
                except Exception as exc:
                    succeeded = False
                    error = str(exc)
                # 并发安全地累加进度（独立短 session）
                try:
                    async with self.session_factory() as pdb:
                        await TaskService.increment_progress(pdb, task_id, success=succeeded)
                except Exception:
                    pass
                return {"user_id": user_id, "success": succeeded, "error": error}

        try:
            # gather 按输入顺序返回结果，保持稳定的结果序列
            results = await asyncio.gather(*(run_one(uid) for uid in user_ids))
            async with self.session_factory() as db:
                task = await TaskService.get_task(db, task_id)
                if task and task.status == "running":
                    await TaskService.complete_task(
                        db, task, result={"results": list(results)}
                    )
        except Exception as exc:
            async with self.session_factory() as db:
                task = await TaskService.get_task(db, task_id)
                if task:
                    await TaskService.complete_task(
                        db,
                        task,
                        status="failed",
                        result={"results": []},
                        error=str(exc)[:500],
                    )

    @staticmethod
    async def interrupt_stale_tasks(db: AsyncSession) -> int:
        result = await db.execute(
            select(Task).where(
                Task.task_type == "clockin",
                Task.status.in_(ACTIVE_TASK_STATUSES),
            )
        )
        tasks = list(result.scalars().all())
        now = utc_now()
        for task in tasks:
            task.status = "interrupted"
            task.error = "服务重启，任务已中断"
            task.completed_at = now
            task.updated_at = now
        if tasks:
            await db.commit()
        return len(tasks)


clockin_task_orchestrator = TaskOrchestrator()
