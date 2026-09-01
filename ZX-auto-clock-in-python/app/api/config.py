"""
配置管理 API
"""
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from app.core.database import get_db
from app.api.auth import verify_session
from app.models.database import Session as DBSession, Config
from app.models.schemas import ConfigUpdateRequest, ConfigResponse, SuccessResponse
from app.config import settings
from app.core.scheduler import get_schedule_info, reload_clockin_job
from app.services.config_transfer_service import ConfigTransferService

router = APIRouter(prefix="/api/config", tags=["配置管理"])
logger = logging.getLogger(__name__)
BEIJING_TIMEZONE = ZoneInfo("Asia/Shanghai")


def build_config_export_filename(now: datetime | None = None) -> str:
    """生成与旧版后台一致、按北京时间标记日期的配置文件名。"""
    current_time = now or datetime.now(BEIJING_TIMEZONE)
    beijing_date = current_time.astimezone(BEIJING_TIMEZONE).date().isoformat()
    return f"zx-admin-config-{beijing_date}.json"


@router.get("", response_model=ConfigResponse)
async def get_config(
    db: AsyncSession = Depends(get_db),
    session: DBSession = Depends(verify_session)
):
    """获取系统配置"""
    # 从数据库获取配置（优先）
    result = await db.execute(select(Config))
    db_configs = result.scalars().all()

    config_dict = {}

    # 默认配置
    default_configs = {
        'clockin_api_url': settings.clockin_api_url,
        'api_request_delay': settings.api_request_delay,
        'clockin_type_delay': settings.clockin_type_delay,
        'clockin_retry_count': settings.clockin_retry_count,
        'clockin_retry_delay': settings.clockin_retry_delay,
        'clockin_timeout': settings.clockin_timeout,
        'clockin_rate_limit_delay': settings.clockin_rate_limit_delay,
        'schedule_cron': settings.schedule_cron,
        'schedule_enabled': settings.schedule_enabled,
        'schedule_timezone': settings.schedule_timezone,
        'schedule_retry_count': settings.schedule_retry_count,
        'schedule_retry_delay': settings.schedule_retry_delay,
        'retention_days': settings.retention_days,
    }

    # 合并数据库配置
    for config in db_configs:
        if config.key in ConfigTransferService.SENSITIVE_CONFIG_KEYS:
            continue
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
    from datetime import datetime

    update_data = {
        key: value
        for key, value in updates.model_dump(exclude_unset=True).items()
        if value is not None
    }

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


@router.get("/export")
async def export_config(
    db: AsyncSession = Depends(get_db),
    session: DBSession = Depends(verify_session)
):
    """导出不包含用户密码或 Worker Token 的 2.0 配置文件。"""
    try:
        export_data = await ConfigTransferService.export_data(db)

        return JSONResponse(
            content=export_data,
            headers={
                'Content-Disposition': (
                    f'attachment; filename="{build_config_export_filename()}"'
                )
            }
        )
    except Exception as e:
        logger.error(f"导出配置失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="导出失败，请查看服务端日志"
        )


@router.post("/import", response_model=SuccessResponse)
async def import_config(
    import_data: dict,
    db: AsyncSession = Depends(get_db),
    session: DBSession = Depends(verify_session)
):
    """导入 2.0 安全配置，或兼容恢复旧版 1.0 明文配置。"""
    try:
        report = await ConfigTransferService.import_data(db, import_data)

        # 如果更新了定时任务配置，重新加载调度器
        config_data = import_data.get('config', {}) if isinstance(import_data, dict) else {}
        if 'schedule_cron' in config_data or 'schedule_enabled' in config_data:
            result = await db.execute(
                select(Config).where(
                    Config.key.in_(['schedule_cron', 'schedule_enabled', 'schedule_timezone'])
                )
            )
            stored = {item.key: item.value for item in result.scalars().all()}
            new_cron = stored.get('schedule_cron', settings.schedule_cron)
            new_enabled = ConfigTransferService._as_bool(
                stored.get('schedule_enabled'),
                default=settings.schedule_enabled,
            )
            timezone = stored.get('schedule_timezone', settings.schedule_timezone)
            await reload_clockin_job(new_cron, new_enabled, timezone)

        return SuccessResponse(
            success=True,
            message=(
                "导入完成。若使用旧版 1.0 明文文件，请立即删除原文件并确认 Worker Token 已轮换。"
            ),
            data=report,
        )

    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        # 导入异常可能携带 SQL bound parameters，其中包含旧版明文密码或 Token。
        # 只记录异常类型，绝不格式化异常对象或 traceback。
        logger.error("导入配置失败（%s）", type(exc).__name__)
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail="导入失败，请查看服务端日志"
        )
