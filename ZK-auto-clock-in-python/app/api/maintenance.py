"""
维护 API
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete, select
from sqlalchemy.engine import make_url
from datetime import datetime, timedelta
from pathlib import Path
import asyncio
import logging
import sqlite3

from app.core.database import get_db
from app.api.auth import verify_session
from app.config import settings
from app.models.database import Session as DBSession, ClockinResult, DailySummary
from app.models.schemas import CleanupRequest, CleanupResponse, SuccessResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/maintenance", tags=["维护"])


def _sqlite_backup(source_file: Path, backup_file: Path) -> None:
    """使用 SQLite online backup API 创建一致快照（包括 WAL 中已提交数据）。"""
    with sqlite3.connect(source_file) as source, sqlite3.connect(backup_file) as target:
        source.backup(target)


@router.post("/cleanup", response_model=CleanupResponse)
async def cleanup_old_records(
    request: CleanupRequest,
    db: AsyncSession = Depends(get_db),
    session: DBSession = Depends(verify_session)
):
    """清理旧数据"""
    days_to_keep = request.days

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


@router.post("/backup", response_model=SuccessResponse)
async def backup_database(
    db: AsyncSession = Depends(get_db),
    session: DBSession = Depends(verify_session)
):
    """备份数据库"""
    try:
        database_url = make_url(settings.database_url)
        if not database_url.drivername.startswith("sqlite") or not database_url.database:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="仅支持备份文件 SQLite 数据库",
            )
        db_file = Path(database_url.database)
        backup_dir = db_file.parent / "backups"

        backup_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        backup_file = backup_dir / f"zk_admin_{timestamp}.db"

        if not db_file.is_file():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="数据库文件不存在"
            )

        await asyncio.to_thread(_sqlite_backup, db_file, backup_file)
        logger.info("数据库备份成功: %s", backup_file)

        return SuccessResponse(
            success=True,
            message=f"备份已创建: {backup_file}",
            data={"backup_file": str(backup_file)}
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"数据库备份失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="备份失败，请查看服务端日志"
        )
