"""
打卡操作 API
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.core.database import get_db
from app.api.auth import verify_session
from app.models.database import Session as DBSession
from app.models.schemas import (
    ClockinTriggerResponse,
    ClockinResultsResponse,
    ClockinStatsResponse,
    SuccessResponse,
    ActiveTasksResponse
)
from app.services.clockin_service import ClockinService
from app.services.active_task_service import ActiveTaskService

router = APIRouter(prefix="/api/clockin", tags=["打卡操作"])


@router.post("/trigger", response_model=ClockinTriggerResponse)
async def trigger_all_users(
    db: AsyncSession = Depends(get_db),
    session: DBSession = Depends(verify_session)
):
    """触发所有用户打卡（串行执行）"""
    result = await ClockinService.trigger_all_users(db)
    return ClockinTriggerResponse(success=True, data=result)


@router.post("/user/{user_id}", response_model=SuccessResponse)
async def trigger_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    session: DBSession = Depends(verify_session)
):
    """触发指定用户打卡"""
    result = await ClockinService.trigger_user(db, user_id)
    if not result.get('success'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.get('error', '打卡失败')
        )
    return SuccessResponse(success=True, data=result)


@router.get("/results", response_model=ClockinResultsResponse)
async def get_clockin_results(
    date: Optional[str] = Query(None, description="日期 YYYY-MM-DD"),
    range: str = Query("day", description="范围: day, 3days 或 week"),
    db: AsyncSession = Depends(get_db),
    session: DBSession = Depends(verify_session)
):
    """获取打卡历史"""
    from datetime import datetime

    if not date:
        date = datetime.utcnow().strftime('%Y-%m-%d')

    if range not in ['day', '3days', 'week']:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="range 参数必须是 'day', '3days' 或 'week'"
        )

    data = await ClockinService.get_clockin_results(db, date, range)
    return ClockinResultsResponse(success=True, data=data)


@router.get("/stats", response_model=ClockinStatsResponse)
async def get_stats(
    db: AsyncSession = Depends(get_db),
    session: DBSession = Depends(verify_session)
):
    """获取统计数据"""
    data = await ClockinService.get_stats(db)
    return ClockinStatsResponse(success=True, data=data)


@router.get("/active-tasks", response_model=ActiveTasksResponse)
async def get_active_tasks(
    session: DBSession = Depends(verify_session)
):
    """获取当前活动任务"""
    tasks = await ActiveTaskService.get_active_tasks()
    return ActiveTasksResponse(success=True, data={
        'active_tasks': tasks,
        'count': len(tasks)
    })
