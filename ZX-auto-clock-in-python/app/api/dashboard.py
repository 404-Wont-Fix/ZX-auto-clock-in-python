"""后台总览 API。"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import verify_session
from app.core.database import get_db
from app.models.database import Session as DBSession
from app.services.dashboard_service import DashboardService


router = APIRouter(prefix="/api/dashboard", tags=["后台总览"])


@router.get("/summary")
async def get_dashboard_summary(
    db: AsyncSession = Depends(get_db),
    session: DBSession = Depends(verify_session),
):
    summary = await DashboardService.get_summary(db)
    return {"success": True, "data": summary}
