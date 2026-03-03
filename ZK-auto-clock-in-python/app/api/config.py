"""
配置管理 API
"""
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime
import asyncio
import logging
import json

from app.core.database import get_db
from app.api.auth import verify_session
from app.models.database import Session as DBSession, Config, User, WorkerApi
from app.models.schemas import ConfigUpdateRequest, ConfigResponse, SuccessResponse
from app.config import settings
from app.core.scheduler import get_schedule_info, reload_clockin_job

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
        'schedule_timezone': settings.schedule_timezone,
        'schedule_retry_count': settings.schedule_retry_count,
        'schedule_retry_delay': settings.schedule_retry_delay,
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


@router.get("/export")
async def export_config(
    db: AsyncSession = Depends(get_db),
    session: DBSession = Depends(verify_session)
):
    """导出系统配置和用户信息为 JSON"""
    try:
        # 获取所有配置
        config_result = await db.execute(select(Config))
        configs = config_result.scalars().all()
        config_dict = {config.key: config.value for config in configs}

        # 获取所有用户信息（不包括密码等敏感信息）
        user_result = await db.execute(select(User))
        users = user_result.scalars().all()

        users_list = []
        for user in users:
            user_dict = {
                'username': user.username,
                'nickname': user.nickname,
                'enabled': user.enabled,
                'sports_comment_type': user.sports_comment_type,
                'daily_comment_type': user.daily_comment_type,
                'sports_comment_api': user.sports_comment_api,
                'daily_comment_api': user.daily_comment_api,
                'sports_image_type': user.sports_image_type,
                'sports_image_provider': user.sports_image_provider,
                'sports_image_category': user.sports_image_category,
                'clockin_count': user.clockin_count,
                'last_clockin': user.last_clockin.isoformat() if user.last_clockin else None,
                'created_at': user.created_at.isoformat() if user.created_at else None,
            }
            users_list.append(user_dict)

        # 获取所有执行器API配置
        worker_api_result = await db.execute(select(WorkerApi))
        worker_apis = worker_api_result.scalars().all()

        worker_apis_list = []
        for api in worker_apis:
            api_dict = {
                'name': api.name,
                'url': api.url,
                'token': api.token,
                'enabled': bool(api.enabled),  # 确保是布尔值
                'note': api.note,
            }
            worker_apis_list.append(api_dict)

        # 构建导出数据
        export_data = {
            'version': '1.0',
            'exported_at': datetime.utcnow().isoformat(),
            'config': config_dict,
            'users': users_list,
            'worker_apis': worker_apis_list
        }

        return JSONResponse(
            content=export_data,
            headers={
                'Content-Disposition': 'attachment; filename="zk-admin-config.json"'
            }
        )
    except Exception as e:
        logger.error(f"导出配置失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"导出失败: {str(e)}"
        )


@router.post("/import", response_model=SuccessResponse)
async def import_config(
    import_data: dict,
    db: AsyncSession = Depends(get_db),
    session: DBSession = Depends(verify_session)
):
    """导入系统配置和用户信息"""
    try:
        # 验证版本
        version = import_data.get('version')
        if not version:
            raise HTTPException(
                status_code=400,
                detail="无效的导入文件：缺少版本信息"
            )

        imported_configs = 0
        imported_users = 0
        updated_users = 0
        imported_worker_apis = 0

        # 导入配置
        config_data = import_data.get('config', {})
        for key, value in config_data.items():
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
            imported_configs += 1

        # 导入用户信息
        users_data = import_data.get('users', [])
        for user_data in users_data:
            username = user_data.get('username')
            if not username:
                continue

            # 查找现有用户
            result = await db.execute(select(User).where(User.username == username))
            user = result.scalar_one_or_none()

            if user:
                # 更新现有用户（不更新密码）
                user.nickname = user_data.get('nickname', user.nickname)
                user.enabled = user_data.get('enabled', user.enabled)
                user.sports_comment_type = user_data.get('sports_comment_type', user.sports_comment_type)
                user.daily_comment_type = user_data.get('daily_comment_type', user.daily_comment_type)
                user.sports_comment_api = user_data.get('sports_comment_api')
                user.daily_comment_api = user_data.get('daily_comment_api')
                user.sports_image_type = user_data.get('sports_image_type', user.sports_image_type)
                user.sports_image_provider = user_data.get('sports_image_provider')
                user.sports_image_category = user_data.get('sports_image_category')
                # 不导入 clockin_count 和 last_clockin，保持原有数据
                updated_users += 1
            else:
                # 新用户需要密码，跳过
                logger.warning(f"用户 {username} 不存在，跳过导入（需要手动添加用户）")
                continue

        # 导入执行器API配置
        worker_apis_data = import_data.get('worker_apis', [])
        if not isinstance(worker_apis_data, list):
            logger.warning(f"worker_apis 数据格式错误，应为列表，实际为: {type(worker_apis_data)}")
            worker_apis_data = []
        for api_data in worker_apis_data:
            url = api_data.get('url')
            if not url:
                logger.warning("跳过缺少url的执行器API配置")
                continue

            # 检查必填字段
            name = api_data.get('name')
            token = api_data.get('token')
            if not name:
                logger.warning(f"跳过缺少name的执行器API: {url}")
                continue
            if not token:
                logger.warning(f"跳过缺少token的执行器API: {name}")
                continue

            try:
                # 查找现有API（通过URL）
                result = await db.execute(select(WorkerApi).where(WorkerApi.url == url))
                api = result.scalar_one_or_none()

                # 处理 enabled 字段 - 可能是字符串、整数或布尔值
                enabled_value = api_data.get('enabled', True)
                if isinstance(enabled_value, str):
                    enabled_value = enabled_value.lower() in ('true', '1', 'yes', 'on')
                elif isinstance(enabled_value, (int, float)):
                    enabled_value = bool(enabled_value)
                # 如果已经是布尔值，直接使用

                if api:
                    # 更新现有API
                    api.name = name
                    api.token = token
                    api.enabled = enabled_value
                    api.note = api_data.get('note')
                    api.updated_at = datetime.utcnow()
                    imported_worker_apis += 1
                else:
                    # 创建新API
                    api = WorkerApi(
                        name=name,
                        url=url,
                        token=token,
                        enabled=enabled_value,
                        note=api_data.get('note')
                    )
                    db.add(api)
                    imported_worker_apis += 1
            except Exception as e:
                logger.error(f"导入执行器API失败 ({url}): {e}")
                continue

        await db.commit()

        # 如果更新了定时任务配置，重新加载调度器
        if 'schedule_cron' in config_data or 'schedule_enabled' in config_data:
            new_cron = config_data.get('schedule_cron', settings.schedule_cron)
            new_enabled = config_data.get('schedule_enabled', True) == 'True'
            await reload_clockin_job(new_cron, new_enabled)

        return SuccessResponse(
            success=True,
            message=f"导入成功：{imported_configs} 条配置，{updated_users} 个用户更新，{imported_worker_apis} 个执行器API"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"导入配置失败: {e}", exc_info=True)
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"导入失败: {str(e)}"
        )
