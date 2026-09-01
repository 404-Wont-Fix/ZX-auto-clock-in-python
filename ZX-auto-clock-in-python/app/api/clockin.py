"""打卡任务与记录 API。"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import verify_session
from app.core.database import get_db
from app.models.database import Session as DBSession
from app.models.schemas import (
    ActiveTasksResponse,
    ClockinResultsResponse,
    ClockinStatsResponse,
    ClockinTaskCreate,
)
from app.services.active_task_service import ActiveTaskService
from app.services.clockin_service import ClockinService
from app.services.task_service import (
    ActiveTaskConflict,
    TaskService,
    clockin_task_orchestrator,
)


router = APIRouter(prefix="/api/clockin", tags=["打卡操作"])


def _error(status_code: int, message: str, data: Optional[dict] = None) -> JSONResponse:
    content = {"success": False, "error": message}
    if data is not None:
        content["data"] = data
    return JSONResponse(status_code=status_code, content=content)


async def _enqueue(
    db: AsyncSession,
    *,
    scope: str,
    target_date: Optional[str],
    user_ids: list[str],
    triggered_by: str,
):
    try:
        task = await clockin_task_orchestrator.enqueue_task(
            db,
            scope=scope,
            target_date=target_date,
            requested_user_ids=user_ids,
            triggered_by=triggered_by,
        )
    except ActiveTaskConflict as exc:
        return _error(
            status.HTTP_409_CONFLICT,
            "已有打卡任务正在执行",
            {"task_id": exc.task_id},
        )
    except ValueError as exc:
        return _error(status.HTTP_400_BAD_REQUEST, str(exc))
    return {"success": True, "data": task.to_dict()}


@router.post("/tasks", status_code=status.HTTP_202_ACCEPTED)
async def create_clockin_task(
    request: ClockinTaskCreate,
    db: AsyncSession = Depends(get_db),
    session: DBSession = Depends(verify_session),
):
    return await _enqueue(
        db,
        scope=request.scope,
        target_date=request.date.isoformat() if request.date else None,
        user_ids=request.user_ids,
        triggered_by="manual",
    )


@router.get("/tasks")
async def list_clockin_tasks(
    status_filter: Optional[str] = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
    session: DBSession = Depends(verify_session),
):
    tasks = await TaskService.list_tasks(db, status=status_filter)
    return {"success": True, "data": [task.to_dict() for task in tasks]}


@router.get("/tasks/{task_id}")
async def get_clockin_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    session: DBSession = Depends(verify_session),
):
    task = await TaskService.get_task(db, task_id)
    if not task:
        return _error(status.HTTP_404_NOT_FOUND, "任务不存在")
    return {"success": True, "data": task.to_dict()}


@router.post("/trigger", status_code=status.HTTP_202_ACCEPTED)
async def trigger_all_users(
    db: AsyncSession = Depends(get_db),
    session: DBSession = Depends(verify_session),
):
    """兼容旧入口，但统一创建持久化任务。"""
    return await _enqueue(
        db,
        scope="all",
        target_date=None,
        user_ids=[],
        triggered_by="manual",
    )


@router.post("/user/{user_id}", status_code=status.HTTP_202_ACCEPTED)
async def trigger_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    session: DBSession = Depends(verify_session),
):
    """兼容旧入口，但统一创建指定用户任务。"""
    return await _enqueue(
        db,
        scope="users",
        target_date=None,
        user_ids=[user_id],
        triggered_by="manual",
    )


@router.get("/results", response_model=ClockinResultsResponse)
async def get_clockin_results(
    date: Optional[str] = Query(None, description="日期 YYYY-MM-DD"),
    range: str = Query("day", description="范围: day, 3days 或 week"),
    db: AsyncSession = Depends(get_db),
    session: DBSession = Depends(verify_session),
):
    if not date:
        date = datetime.now(timezone(timedelta(hours=8))).date().isoformat()
    if range not in {"day", "3days", "week"}:
        return _error(status.HTTP_400_BAD_REQUEST, "range 参数必须是 day、3days 或 week")
    data = await ClockinService.get_clockin_results(db, date, range)
    return ClockinResultsResponse(success=True, data=data)


@router.get("/stats", response_model=ClockinStatsResponse)
async def get_stats(
    db: AsyncSession = Depends(get_db),
    session: DBSession = Depends(verify_session),
):
    data = await ClockinService.get_stats(db)
    return ClockinStatsResponse(success=True, data=data)


@router.get("/active-tasks", response_model=ActiveTasksResponse)
async def get_active_tasks(session: DBSession = Depends(verify_session)):
    """保留每个 Worker 调用的瞬时诊断视图。"""
    tasks = await ActiveTaskService.get_active_tasks()
    return ActiveTasksResponse(
        success=True,
        data={"active_tasks": tasks, "count": len(tasks)},
    )
