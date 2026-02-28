"""
定时任务调度器
"""
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from contextlib import asynccontextmanager
from typing import Optional
import logging

from app.config import settings
from app.services.clockin_service import ClockinService

logger = logging.getLogger(__name__)

# 全局调度器实例
scheduler: Optional[AsyncIOScheduler] = None


async def scheduled_clockin_job():
    """定时打卡任务"""
    logger.info("=== 定时打卡任务开始 ===")

    try:
        from app.core.database import AsyncSessionLocal
        from fastapi import BackgroundTasks

        async with AsyncSessionLocal() as db:
            # 创建空的 BackgroundTasks（仅用于兼容接口）
            background_tasks = BackgroundTasks()

            # 触发所有用户打卡
            result = await ClockinService.trigger_all_users(db, background_tasks)

            logger.info(f"定时打卡任务完成: {result}")

    except Exception as e:
        logger.error(f"定时打卡任务失败: {e}", exc_info=True)


async def cleanup_job():
    """清理旧数据任务"""
    logger.info("=== 定时清理任务开始 ===")

    try:
        from app.core.database import AsyncSessionLocal
        from sqlalchemy import delete, select
        from datetime import timedelta
        from app.models.database import ClockinResult, DailySummary

        async with AsyncSessionLocal() as db:
            cutoff_date = (datetime.now() - timedelta(days=settings.retention_days)).strftime('%Y-%m-%d')

            # 删除旧的打卡记录
            result = await db.execute(
                delete(ClockinResult).where(ClockinResult.date < cutoff_date)
            )
            deleted_results = result.rowcount

            # 删除旧的汇总数据
            result = await db.execute(
                delete(DailySummary).where(DailySummary.date < cutoff_date)
            )
            deleted_summaries = result.rowcount

            await db.commit()

            logger.info(f"定时清理完成: 删除 {deleted_results + deleted_summaries} 条记录")

    except Exception as e:
        logger.error(f"定时清理任务失败: {e}", exc_info=True)


def start_scheduler():
    """启动调度器"""
    global scheduler

    if scheduler is not None:
        logger.warning("调度器已经在运行")
        return

    scheduler = AsyncIOScheduler()

    # 添加定时打卡任务
    try:
        scheduler.add_job(
            scheduled_clockin_job,
            trigger=CronTrigger.from_crontab(settings.schedule_cron),
            id='clockin',
            name='定时打卡任务',
            replace_existing=True
        )
        logger.info(f"定时打卡任务已添加: {settings.schedule_cron}")
    except Exception as e:
        logger.error(f"添加定时打卡任务失败: {e}")

    # 添加清理任务（每天凌晨 3 点执行）
    try:
        scheduler.add_job(
            cleanup_job,
            trigger=CronTrigger.from_crontab("0 3 * * *"),
            id='cleanup',
            name='清理旧数据任务',
            replace_existing=True
        )
        logger.info("清理任务已添加: 每天 3:00")
    except Exception as e:
        logger.error(f"添加清理任务失败: {e}")

    # 启动调度器
    scheduler.start()
    logger.info("调度器已启动")


def stop_scheduler():
    """停止调度器"""
    global scheduler

    if scheduler is not None:
        scheduler.shutdown(wait=False)
        scheduler = None
        logger.info("调度器已停止")


@asynccontextmanager
async def scheduler_lifespan():
    """调度器生命周期管理"""
    # 启动调度器
    start_scheduler()
    yield
    # 停止调度器
    stop_scheduler()


# 导入 datetime
from datetime import datetime
