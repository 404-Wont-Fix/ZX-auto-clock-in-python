"""
定时任务调度器
"""
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from contextlib import asynccontextmanager
from typing import Optional
import logging
import pytz

from app.config import settings
from app.services.clockin_service import ClockinService

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
            # 触发所有用户打卡（标记为 scheduled）
            # 注意：trigger_all_users 内部已经包含自动补签逻辑，不需要在这里重复处理
            result = await ClockinService.trigger_all_users(db, triggered_by='scheduled')

            # 记录结果
            success_count = result.get('success', 0)
            failure_count = result.get('failure', 0)
            total_duration = result.get('duration_seconds', 0)

            logger.info(f"=== 定时打卡任务完成 ===")
            logger.info(f"总计: {result.get('total', 0)} 个用户")
            logger.info(f"成功: {success_count} 个, 失败: {failure_count} 个")
            logger.info(f"总耗时: {total_duration:.2f} 秒")

            if failure_count > 0:
                logger.warning(f"有 {failure_count} 个用户打卡失败，已在 trigger_all_users 中自动执行补签")

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

    # 清理活动任务（防止任务泄漏）
    try:
        from app.services.active_task_service import ActiveTaskService
        stale_count = await ActiveTaskService.cleanup_stale_tasks(max_age_seconds=300)  # 清理5分钟未完成的任务
        if stale_count > 0:
            logger.warning(f"清理了 {stale_count} 个过期的活动任务")
    except Exception as e:
        logger.error(f"清理活动任务失败: {e}")


def start_scheduler():
    """启动调度器"""
    global scheduler

    if scheduler is not None:
        logger.warning("调度器已经在运行")
        return

    # 从数据库读取配置（如果数据库已初始化）
    schedule_cron = settings.schedule_cron
    schedule_enabled = settings.schedule_enabled
    schedule_timezone = settings.schedule_timezone

    try:
        # 尝试从数据库读取配置
        from app.core.database import AsyncSessionLocal
        from sqlalchemy import select
        from app.models.database import Config
        import inspect

        # 检查是否在事件循环中运行
        try:
            import asyncio
            loop = asyncio.get_running_loop()
            # 如果已经在事件循环中，使用 create_task
            in_event_loop = True
        except RuntimeError:
            # 没有运行的事件循环
            in_event_loop = False

        # 使用同步方式读取数据库配置
        async def load_db_config():
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(Config).where(
                        Config.key.in_(['schedule_cron', 'schedule_enabled', 'schedule_timezone'])
                    )
                )
                configs = result.scalars().all()
                return {config.key: config.value for config in configs}

        try:
            if in_event_loop:
                # 在事件循环中，无法使用 asyncio.run()
                # 使用同步方式或者接受使用默认值
                logger.info("检测到运行中的事件循环，将使用环境变量配置（可通过 API 动态修改）")
            else:
                # 不在事件循环中，可以使用 asyncio.run()
                import asyncio
                db_configs = asyncio.run(load_db_config())
                if db_configs:
                    if 'schedule_cron' in db_configs:
                        schedule_cron = db_configs['schedule_cron']
                        logger.info(f"从数据库读取 schedule_cron: {schedule_cron}")
                    if 'schedule_enabled' in db_configs:
                        schedule_enabled = db_configs['schedule_enabled'].lower() == 'true'
                        logger.info(f"从数据库读取 schedule_enabled: {schedule_enabled}")
                    if 'schedule_timezone' in db_configs:
                        schedule_timezone = db_configs['schedule_timezone']
                        logger.info(f"从数据库读取 schedule_timezone: {schedule_timezone}")
        except Exception as e:
            logger.warning(f"无法从数据库读取配置，使用默认值: {e}")

    except Exception as e:
        logger.warning(f"数据库可能尚未初始化，使用环境变量配置: {e}")

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
    start_scheduler()
    yield
    # 停止调度器
    stop_scheduler()


# 导入 datetime
from datetime import datetime
