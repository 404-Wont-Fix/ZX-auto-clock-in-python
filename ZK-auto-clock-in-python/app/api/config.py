"""
配置管理 API
"""
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
import asyncio
import logging

from app.core.database import get_db
from app.api.auth import verify_session
from app.models.database import Session as DBSession, Config
from app.models.schemas import ConfigUpdateRequest, ConfigResponse, SuccessResponse
from app.config import settings
from app.core.scheduler import get_schedule_info

router = APIRouter(prefix="/api/config", tags=["配置管理"])
logger = logging.getLogger(__name__)


@router.get("", response_model=ConfigResponse)
async def get_config(
    db: AsyncSession = Depends(get_db),
    session: DBSession = Depends(verify_session)
):
    """获取系统配置"""
    from sqlalchemy import select

    # 从数据库获取配置（优先）
    result = await db.execute(select(Config))
    db_configs = result.scalars().all()

    config_dict = {}

    # 默认配置
    default_configs = {
        'clockin_api_url': settings.clockin_api_url,
        'clockin_api_token': settings.clockin_api_token,
        'api_request_delay': settings.api_request_delay,
        'clockin_type_delay': settings.clockin_type_delay,
        'clockin_retry_count': settings.clockin_retry_count,
        'clockin_retry_delay': settings.clockin_retry_delay,
        'clockin_timeout': settings.clockin_timeout,
        'clockin_rate_limit_delay': settings.clockin_rate_limit_delay,
        'schedule_cron': settings.schedule_cron,
        'schedule_enabled': settings.schedule_enabled,
        'retention_days': settings.retention_days,
    }

    # 合并数据库配置
    for config in db_configs:
        config_dict[config.key] = config.value

    # 填充默认配置
    for key, value in default_configs.items():
        if key not in config_dict:
            config_dict[key] = value

    return ConfigResponse(success=True, data=config_dict)


@router.put("", response_model=SuccessResponse)
async def update_config(
    updates: ConfigUpdateRequest,
    db: AsyncSession = Depends(get_db),
    session: DBSession = Depends(verify_session)
):
    """更新系统配置"""
    from sqlalchemy import select
    from datetime import datetime
    from app.core.scheduler import reload_clockin_job

    update_data = updates.model_dump(exclude_unset=True)

    # 检查是否更新了定时任务配置
    schedule_cron_updated = 'schedule_cron' in update_data
    schedule_enabled_updated = 'schedule_enabled' in update_data

    for key, value in update_data.items():
        # 查找现有配置
        result = await db.execute(select(Config).where(Config.key == key))
        config = result.scalar_one_or_none()

        if config:
            # 更新
            config.value = str(value)
            config.updated_at = datetime.utcnow()
        else:
            # 创建
            config = Config(key=key, value=str(value))
            db.add(config)

    # 统一提交数据库事务
    await db.commit()

    # 如果更新了定时任务配置，重新加载调度器
    if schedule_cron_updated or schedule_enabled_updated:
        new_cron = update_data.get('schedule_cron', settings.schedule_cron)
        new_enabled = update_data.get('schedule_enabled', True)

        # 从数据库读取时区配置
        timezone = settings.schedule_timezone
        if 'schedule_timezone' in update_data:
            timezone = update_data['schedule_timezone']
        else:
            # 如果本次更新没有包含时区，从数据库读取现有的时区配置
            result = await db.execute(select(Config).where(Config.key == 'schedule_timezone'))
            tz_config = result.scalar_one_or_none()
            if tz_config:
                timezone = tz_config.value

        reload_success = await reload_clockin_job(new_cron, new_enabled, timezone)

        if reload_success:
            if new_enabled:
                return SuccessResponse(success=True, message=f"配置已更新，定时任务已启用: {new_cron}")
            else:
                return SuccessResponse(success=True, message="配置已更新，定时任务已禁用")
        else:
            return SuccessResponse(success=True, message="配置已保存，但定时任务重新加载失败（请查看日志）")

    return SuccessResponse(success=True, message="配置已更新")


@router.get("/schedule", response_model=ConfigResponse)
async def get_schedule_status(
    db: AsyncSession = Depends(get_db),
    session: DBSession = Depends(verify_session)
):
    """获取调度器状态和定时任务信息"""
    schedule_info = await get_schedule_info()

    if schedule_info:
        return ConfigResponse(
            success=True,
            data={
                'scheduler_running': True,
                'schedule_enabled': settings.schedule_enabled,
                'schedule_cron': settings.schedule_cron,
                'schedule_timezone': settings.schedule_timezone,
                'job_info': schedule_info
            }
        )
    else:
        return ConfigResponse(
            success=True,
            data={
                'scheduler_running': False,
                'schedule_enabled': settings.schedule_enabled,
                'schedule_cron': settings.schedule_cron,
                'schedule_timezone': settings.schedule_timezone,
                'job_info': None,
                'message': '调度器未运行或定时任务未配置'
            }
        )


@router.post("/test-schedule", response_model=SuccessResponse)
async def test_schedule_task(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    session: DBSession = Depends(verify_session)
):
    """测试定时任务 - 模拟定时任务执行，3秒后返回结果"""
    from app.services.clockin_service import ClockinService

    logger.info("=== 开始测试定时任务 ===")

    async def run_test_task():
        """异步执行测试任务"""
        try:
            # 等待 3 秒
            await asyncio.sleep(3)

            # 获取调度器状态
            schedule_info = await get_schedule_info()

            if schedule_info:
                logger.info(f"测试成功！调度器状态: {schedule_info}")
                return {
                    'success': True,
                    'message': '定时任务测试成功',
                    'job_info': schedule_info,
                    'next_run_time': schedule_info.get('next_run_time')
                }
            else:
                logger.warning("测试失败：调度器未运行")
                return {
                    'success': False,
                    'error': '调度器未运行或定时任务未配置'
                }
        except Exception as e:
            logger.error(f"测试任务执行失败: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e)
            }

    # 在后台执行测试任务
    result = await run_test_task()

    if result['success']:
        return SuccessResponse(
            success=True,
            message=f"测试成功！调度器正常运行，下次执行: {result.get('next_run_time', '未知')}"
        )
    else:
        raise HTTPException(
            status_code=500,
            detail=result.get('error', '测试失败')
        )
