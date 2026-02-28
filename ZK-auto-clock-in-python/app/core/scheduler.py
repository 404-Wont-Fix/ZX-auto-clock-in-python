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


def parse_cron_expression(cron_expr: str):
    """
    解析 6 字段的 cron 表达式（秒 分 时 日 月 周）并返回 CronTrigger

    Args:
        cron_expr: cron 表达式，格式 "秒 分 时 日 月 周"

    Returns:
        CronTrigger 对象
    """
    parts = cron_expr.strip().split()

    if len(parts) == 6:
        # 6 字段格式: 秒 分 时 日 月 周
        second, minute, hour, day, month, day_of_week = parts
        return CronTrigger(
            second=second,
            minute=minute,
            hour=hour,
            day=day,
            month=month,
            day_of_week=day_of_week
        )
    elif len(parts) == 5:
        # 5 字段格式: 分 时 日 月 周（传统 Linux cron）
        minute, hour, day, month, day_of_week = parts
        return CronTrigger(
            minute=minute,
            hour=hour,
            day=day,
            month=month,
            day_of_week=day_of_week
        )
    else:
        raise ValueError(f"不支持的 cron 表达式格式: {cron_expr}，期望 5 或 6 个字段")


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

    # 添加定时打卡任务（根据开关决定）
    if settings.schedule_enabled:
        try:
            trigger = parse_cron_expression(settings.schedule_cron)
            scheduler.add_job(
                scheduled_clockin_job,
                trigger=trigger,
                id='clockin',
                name='定时打卡任务',
                replace_existing=True
            )
            logger.info(f"定时打卡任务已添加: {settings.schedule_cron}")
        except Exception as e:
            logger.error(f"添加定时打卡任务失败: {e}")
    else:
        logger.info("定时打卡任务已禁用（schedule_enabled = False）")

    # 添加清理任务（每天凌晨 3 点执行）
    try:
        scheduler.add_job(
            cleanup_job,
            trigger=CronTrigger(hour=3, minute=0),
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


async def reload_clockin_job(cron_expression: str, enabled: bool = True):
    """重新加载定时打卡任务

    Args:
        cron_expression: cron 表达式
        enabled: 是否启用定时任务
    """
    global scheduler

    if scheduler is None:
        logger.warning("调度器未运行，无法重新加载任务")
        return False

    try:
        # 检查任务是否存在
        job = scheduler.get_job('clockin')

        if enabled:
            # 解析 cron 表达式并创建触发器
            trigger = parse_cron_expression(cron_expression)

            if job:
                # 更新现有任务的触发器
                scheduler.reschedule_job(
                    'clockin',
                    trigger=trigger
                )
                logger.info(f"定时打卡任务已更新: {cron_expression}")
            else:
                # 添加新任务
                scheduler.add_job(
                    scheduled_clockin_job,
                    trigger=trigger,
                    id='clockin',
                    name='定时打卡任务',
                    replace_existing=True
                )
                logger.info(f"定时打卡任务已添加: {cron_expression}")
        else:
            # 禁用任务：删除现有任务
            if job:
                scheduler.remove_job('clockin')
                logger.info("定时打卡任务已禁用")
            else:
                logger.info("定时打卡任务未运行，无需禁用")

        return True
    except Exception as e:
        logger.error(f"重新加载定时打卡任务失败: {e}", exc_info=True)
        return False


async def get_schedule_info():
    """获取当前调度任务信息"""
    global scheduler

    if scheduler is None:
        return None

    job = scheduler.get_job('clockin')
    if job:
        return {
            'id': job.id,
            'name': job.name,
            'next_run_time': job.next_run_time.isoformat() if job.next_run_time else None,
            'trigger': str(job.trigger)
        }
    return None


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
