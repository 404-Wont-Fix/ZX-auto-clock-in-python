"""
维护 API
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete, select
from datetime import datetime, timedelta
import os

from app.core.database import get_db
from app.api.auth import verify_session
from app.models.database import Session as DBSession, ClockinResult, DailySummary
from app.models.schemas import CleanupRequest, CleanupResponse, HealthResponse

router = APIRouter(prefix="/api/maintenance", tags=["维护"])


@router.post("/cleanup", response_model=CleanupResponse)
async def cleanup_old_records(
    request: CleanupRequest,
    db: AsyncSession = Depends(get_db),
    session: DBSession = Depends(verify_session)
):
    """清理旧数据"""
    days_to_keep = request.days or 7

    cutoff_date = datetime.utcnow() - timedelta(days=days_to_keep)
    cutoff_date_str = cutoff_date.strftime('%Y-%m-%d')
    today_str = datetime.utcnow().strftime('%Y-%m-%d')

    # 删除旧的打卡记录
    result = await db.execute(
        delete(ClockinResult).where(ClockinResult.date < cutoff_date_str)
    )
    deleted_results = result.rowcount

    # 删除旧的汇总数据
    result = await db.execute(
        delete(DailySummary).where(DailySummary.date < cutoff_date_str)
    )
    deleted_summaries = result.rowcount

    await db.commit()

    total_deleted = deleted_results + deleted_summaries

    return CleanupResponse(
        success=True,
        message=f"清理完成，删除 {total_deleted} 条记录",
        deleted=total_deleted,
        errors=0,
        total=0,
        checked=0,
        cutoff_date=cutoff_date_str,
        today=today_str,
        days_to_keep=days_to_keep
    )


@router.post("/backup")
async def backup_database(
    db: AsyncSession = Depends(get_db),
    session: DBSession = Depends(verify_session)
):
    """备份数据库"""
    import shutil
    from datetime import datetime

    try:
        # 数据库文件路径
        db_file = "database/zk_admin.db"
        backup_dir = "backups"

        # 创建备份目录
        os.makedirs(backup_dir, exist_ok=True)

        # 备份文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = f"{backup_dir}/zk_admin_{timestamp}.db"

        # 复制文件
        if os.path.exists(db_file):
            shutil.copy2(db_file, backup_file)
            return {"success": True, "message": f"备份已创建: {backup_file}"}
        else:
            return {"success": False, "message": "数据库文件不存在"}

    except Exception as e:
        return {"success": False, "message": f"备份失败: {str(e)}"}


@router.get("/health", response_model=HealthResponse)
async def health_check(db: AsyncSession = Depends(get_db)):
    """健康检查"""
    try:
        # 测试数据库连接
        from sqlalchemy import text
        await db.execute(text("SELECT 1"))

        return HealthResponse(
            status="healthy",
            timestamp=datetime.utcnow().isoformat(),
            service="zk-admin",
            database="connected"
        )
    except Exception as e:
        return HealthResponse(
            status="unhealthy",
            timestamp=datetime.utcnow().isoformat(),
            service="zk-admin",
            database=f"error: {str(e)}"
        )
