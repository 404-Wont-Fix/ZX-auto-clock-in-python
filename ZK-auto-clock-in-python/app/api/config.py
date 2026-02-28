"""
配置管理 API
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.auth import verify_session
from app.models.database import Session as DBSession, Config
from app.models.schemas import ConfigUpdateRequest, ConfigResponse, SuccessResponse
from app.config import settings

router = APIRouter(prefix="/api/config", tags=["配置管理"])


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
        'batch_size': settings.batch_size,
        'batch_delay': settings.batch_delay,
        'parallel_tasks': settings.parallel_tasks,
        'schedule_cron': settings.schedule_cron,
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

    update_data = updates.model_dump(exclude_unset=True)

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

        await db.commit()

    return SuccessResponse(success=True, message="配置已更新")
