"""后台总览聚合服务。"""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import ContentSource, User, WorkerApi
from app.services.task_service import TaskOrchestrator, TaskService


async def get_schedule_info():
    from app.core.scheduler import get_schedule_info as load_schedule_info

    return await load_schedule_info()


class DashboardService:
    @staticmethod
    async def get_summary(db: AsyncSession) -> dict:
        today = TaskOrchestrator.beijing_today()

        users_result = await db.execute(
            select(User)
            .where(User.enabled.is_(True))
            .order_by(User.created_at.asc(), User.username.asc())
        )
        users = list(users_result.scalars().all())
        latest = await TaskOrchestrator.latest_results_by_user(
            db,
            target_date=today,
            user_ids=[user.id for user in users],
        )

        success_count = sum(1 for result in latest.values() if result.success)
        failure_count = sum(1 for result in latest.values() if not result.success)
        failed_users = []
        for user in users:
            result = latest.get(user.id)
            if not result or result.success:
                continue
            serialized = result.to_dict()
            failed_users.append(
                {
                    "id": user.id,
                    "username": user.username,
                    "nickname": user.nickname or "",
                    "error": result.error or "未知错误",
                    "details": serialized.get("details") or {},
                }
            )

        worker_result = await db.execute(
            select(WorkerApi).where(WorkerApi.enabled.is_(True))
        )
        workers = list(worker_result.scalars().all())

        source_result = await db.execute(
            select(ContentSource).where(
                ContentSource.enabled.is_(True),
                ContentSource.archived.is_(False),
            )
        )
        sources = list(source_result.scalars().all())
        source_health = {
            "total": len(sources),
            "healthy": 0,
            "degraded": 0,
            "unavailable": 0,
            "unknown": 0,
        }
        for source in sources:
            state = source.health_status
            if state in source_health:
                source_health[state] += 1

        active_task = await TaskService.get_active_task(db)
        schedule = await get_schedule_info()

        return {
            "date": today,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "today": {
                "enabled_users": len(users),
                "success": success_count,
                "failure": failure_count,
                "pending": len(users) - len(latest),
            },
            "failed_users": failed_users,
            "active_task": active_task.to_dict() if active_task else None,
            "workers": {
                "enabled": len(workers),
                "healthy": sum(1 for worker in workers if worker.available),
                "unavailable": sum(1 for worker in workers if not worker.available),
            },
            "content_sources": source_health,
            "next_run_time": schedule.get("next_run_time_beijing") if schedule else None,
        }
