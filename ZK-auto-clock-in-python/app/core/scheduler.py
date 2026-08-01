"""
定时任务调度器
"""
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from contextlib import asynccontextmanager
from typing import Optional
import logging
import pytz

from app.config import settings
from app.services.task_service import ActiveTaskConflict, clockin_task_orchestrator

logger = logging.getLogger(__name__)

# 全局调度器实例
scheduler: Optional[AsyncIOScheduler] = None


def parse_cron_expression(cron_expr: str, timezone: str = 'UTC'):
    """
    解析 6 字段的 cron 表达式（秒 分 时 日 月 周）并返回 CronTrigger

    Args:
        cron_expr: cron 表达式，格式 "秒 分 时 日 月 周"
        timezone: 时区，默认 UTC

    Returns:
        CronTrigger 对象
    """
    parts = cron_expr.strip().split()

    # 验证时区
    try:
        tz = pytz.timezone(timezone)
        logger.info(f"使用时区: {timezone} ({tz})")
    except pytz.exceptions.UnknownTimeZoneError:
        logger.warning(f"未知的时区: {timezone}，使用 UTC 作为默认值")
        tz = pytz.UTC

    if len(parts) == 6:
        # 6 字段格式: 秒 分 时 日 月 周
        second, minute, hour, day, month, day_of_week = parts
        return CronTrigger(
            second=second,
            minute=minute,
            hour=hour,
            day=day,
            month=month,
            day_of_week=day_of_week,
            timezone=tz
        )
    elif len(parts) == 5:
        # 5 字段格式: 分 时 日 月 周（传统 Linux cron）
        minute, hour, day, month, day_of_week = parts
        return CronTrigger(
            minute=minute,
            hour=hour,
            day=day,
            month=month,
            day_of_week=day_of_week,
            timezone=tz
        )
    else:
        raise ValueError(f"不支持的 cron 表达式格式: {cron_expr}，期望 5 或 6 个字段")


async def scheduled_clockin_job():
    """定时打卡任务"""
    logger.info("=== 定时打卡任务开始 ===")

    try:
        from app.core.database import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            try:
                task = await clockin_task_orchestrator.enqueue_task(
                    db,
                    scope="all",
                    target_date=None,
                    requested_user_ids=[],
                    triggered_by="scheduled",
                )
                logger.info("定时打卡任务已入队: %s", task.id)
            except ActiveTaskConflict as exc:
                logger.warning("已有任务 %s 正在执行，本次定时任务跳过", exc.task_id)

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
            # 打卡记录的 date 字段用 UTC 写入（见 save_clockin_result 的 datetime.utcnow），
            # 因此清理阈值也用 UTC，避免服务器本地时区非 UTC 时按错日子边界删除
            cutoff_date = (datetime.utcnow() - timedelta(days=settings.retention_days)).strftime('%Y-%m-%d')

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

    # 清理活动任务（防止任务泄漏）
    try:
        from app.services.active_task_service import ActiveTaskService
        stale_count = await ActiveTaskService.cleanup_stale_tasks(max_age_seconds=300)  # 清理5分钟未完成的任务
        if stale_count > 0:
            logger.warning(f"清理了 {stale_count} 个过期的活动任务")
    except Exception as e:
        logger.error(f"清理活动任务失败: {e}")


async def scheduled_content_source_probe_job():
    """每小时用独立数据库会话探测所有未归档内容源。"""
    from app.core.database import AsyncSessionLocal
    from app.services.content_source_service import ContentSourceService

    try:
        async with AsyncSessionLocal() as db:
            results = await ContentSourceService.test_all(db)
        success_count = sum(1 for result in results if result.get('success'))
        logger.info(
            "内容源健康探测完成: 成功 %s, 失败 %s",
            success_count,
            len(results) - success_count,
        )
    except Exception:
        logger.exception("内容源健康探测任务失败")


def add_content_source_probe_job(target_scheduler: AsyncIOScheduler):
    """向调度器注册固定的一小时内容源探测任务。"""
    target_scheduler.add_job(
        scheduled_content_source_probe_job,
        trigger=IntervalTrigger(hours=1),
        id='content-source-probe',
        name='内容源健康探测',
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )


async def start_scheduler():
    """启动调度器（协程：在已运行的事件循环中读取 DB 配置后启动）。

    重要：必须以 await 调用。此前版本用 asyncio.run() 读取 DB 配置，
    但在 FastAPI lifespan 中始终处于事件循环里，asyncio.run() 会失败，
    于是启动时永远读不到 DB 中的 schedule_* 配置（只能用 .env 默认值），
    导致 /admin 修改的 cron/开关/时区直到重启或手动 reload 才生效。
    """
    global scheduler

    if scheduler is not None:
        logger.warning("调度器已经在运行")
        return

    # 默认使用环境变量配置
    schedule_cron = settings.schedule_cron
    schedule_enabled = settings.schedule_enabled
    schedule_timezone = settings.schedule_timezone

    # 尝试从数据库读取配置（启动时也读取，确保 /admin 改动的 cron/开关/时区即时生效）
    try:
        from app.core.database import AsyncSessionLocal
        from sqlalchemy import select
        from app.models.database import Config

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Config).where(
                    Config.key.in_(['schedule_cron', 'schedule_enabled', 'schedule_timezone'])
                )
            )
            configs = {c.key: c.value for c in result.scalars().all()}

        if configs:
            if 'schedule_cron' in configs:
                schedule_cron = configs['schedule_cron']
                logger.info(f"从数据库读取 schedule_cron: {schedule_cron}")
            if 'schedule_enabled' in configs:
                schedule_enabled = configs['schedule_enabled'].lower() == 'true'
                logger.info(f"从数据库读取 schedule_enabled: {schedule_enabled}")
            if 'schedule_timezone' in configs:
                schedule_timezone = configs['schedule_timezone']
                logger.info(f"从数据库读取 schedule_timezone: {schedule_timezone}")
    except Exception as e:
        logger.warning(f"无法从数据库读取调度配置，使用环境变量值: {e}")

    # 创建调度器实例，配置时区
    scheduler = AsyncIOScheduler(timezone=schedule_timezone)

    # 添加定时打卡任务（根据开关决定）
    if schedule_enabled:
        try:
            trigger = parse_cron_expression(schedule_cron, schedule_timezone)
            scheduler.add_job(
                scheduled_clockin_job,
                trigger=trigger,
                id='clockin',
                name='定时打卡任务',
                replace_existing=True
            )
            logger.info(f"定时打卡任务已添加: {schedule_cron} (时区: {schedule_timezone})")
        except Exception as e:
            logger.error(f"添加定时打卡任务失败: {e}", exc_info=True)
    else:
        logger.info("定时打卡任务已禁用")

    # 添加清理任务（每天凌晨 3 点 UTC 执行）
    try:
        cleanup_tz = pytz.UTC
        scheduler.add_job(
            cleanup_job,
            trigger=CronTrigger(hour=3, minute=0, timezone=cleanup_tz),
            id='cleanup',
            name='清理旧数据任务',
            replace_existing=True
        )
        logger.info(f"清理任务已添加: 每天 UTC 3:00")
    except Exception as e:
        logger.error(f"添加清理任务失败: {e}", exc_info=True)

    try:
        add_content_source_probe_job(scheduler)
        logger.info("内容源健康探测任务已添加: 每小时执行")
    except Exception as e:
        logger.error(f"添加内容源健康探测任务失败: {e}", exc_info=True)

    # 启动调度器
    scheduler.start()
    logger.info(f"调度器已启动 (时区: {schedule_timezone})")

    # 启动后，可以访问下次运行时间
    try:
        clockin_job = scheduler.get_job('clockin')
        if clockin_job and clockin_job.next_run_time:
            logger.info(f"定时打卡任务下次执行时间: {clockin_job.next_run_time}")
    except Exception as e:
        logger.warning(f"无法获取下次执行时间: {e}")

    logger.info(f"所有任务状态:\n{scheduler.print_jobs()}")


def stop_scheduler():
    """停止调度器"""
    global scheduler

    if scheduler is not None:
        logger.info("正在停止调度器...")
        # 使用 wait=True 等待正在执行的任务完成
        scheduler.shutdown(wait=True)
        scheduler = None
        logger.info("调度器已安全停止")


async def reload_clockin_job(cron_expression: str, enabled: bool = True, timezone: str = None):
    """重新加载定时打卡任务

    Args:
        cron_expression: cron 表达式
        enabled: 是否启用定时任务
        timezone: 时区，如果为 None 则从 settings 读取
    """
    global scheduler

    if scheduler is None:
        logger.warning("调度器未运行，无法重新加载任务")
        return False

    try:
        # 如果没有指定时区，从数据库读取
        if timezone is None:
            try:
                from app.core.database import AsyncSessionLocal
                from sqlalchemy import select
                from app.models.database import Config

                async with AsyncSessionLocal() as db:
                    result = await db.execute(
                        select(Config).where(Config.key == 'schedule_timezone')
                    )
                    tz_config = result.scalar_one_or_none()
                    timezone = tz_config.value if tz_config else settings.schedule_timezone
            except Exception as e:
                logger.warning(f"无法从数据库读取时区配置，使用默认值: {e}")
                timezone = settings.schedule_timezone

        # 检查任务是否存在
        job = scheduler.get_job('clockin')

        if enabled:
            # 解析 cron 表达式并创建触发器
            trigger = parse_cron_expression(cron_expression, timezone)

            if job:
                # 更新现有任务的触发器
                scheduler.reschedule_job(
                    'clockin',
                    trigger=trigger
                )
                logger.info(f"定时打卡任务已更新: {cron_expression} (时区: {settings.schedule_timezone})")

                # 记录下次执行时间
                job = scheduler.get_job('clockin')
                if job and job.next_run_time:
                    logger.info(f"下次执行时间: {job.next_run_time}")
            else:
                # 添加新任务
                scheduler.add_job(
                    scheduled_clockin_job,
                    trigger=trigger,
                    id='clockin',
                    name='定时打卡任务',
                    replace_existing=True
                )
                logger.info(f"定时打卡任务已添加: {cron_expression} (时区: {settings.schedule_timezone})")

                # 记录下次执行时间
                job = scheduler.get_job('clockin')
                if job and job.next_run_time:
                    logger.info(f"下次执行时间: {job.next_run_time}")
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
        next_run_time = job.next_run_time
        next_run_time_str = next_run_time.isoformat() if next_run_time else None

        # 添加调试日志
        if next_run_time:
            logger.info(f"定时任务下次执行时间 (UTC): {next_run_time}")
            logger.info(f"定时任务下次执行时间 (北京): {next_run_time.astimezone(pytz.timezone('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S %Z')}")

        return {
            'id': job.id,
            'name': job.name,
            'next_run_time': next_run_time_str,
            'next_run_time_beijing': next_run_time.astimezone(pytz.timezone('Asia/Shanghai')).isoformat() if next_run_time else None,
            'trigger': str(job.trigger)
        }
    return None


@asynccontextmanager
async def scheduler_lifespan():
    """调度器生命周期管理"""
    # 启动调度器
    await start_scheduler()
    yield
    # 停止调度器
    stop_scheduler()


# 导入 datetime
from datetime import datetime
