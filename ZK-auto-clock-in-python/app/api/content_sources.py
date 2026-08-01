"""可管理内容源 API。"""

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import verify_session
from app.core.database import get_db
from app.models.database import Session as DBSession
from app.models.schemas import (
    ContentSourceCreate,
    ContentSourcePriorityUpdate,
    ContentSourceUpdate,
)
from app.services.content_source_service import ContentSourceService


router = APIRouter(prefix="/api/content-sources", tags=["内容源管理"])


def _error(status_code: int, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"success": False, "error": message},
    )


def _serialize_test_result(result: dict) -> dict:
    serialized = {key: value for key, value in result.items() if key != "source"}
    source = result.get("source")
    if source is not None:
        serialized["source"] = source.to_dict()
    return serialized


@router.get("")
async def list_content_sources(
    include_archived: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    session: DBSession = Depends(verify_session),
):
    sources = await ContentSourceService.list_sources(db, include_archived=include_archived)
    return {"success": True, "data": [source.to_dict() for source in sources]}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_content_source(
    data: ContentSourceCreate,
    db: AsyncSession = Depends(get_db),
    session: DBSession = Depends(verify_session),
):
    try:
        source = await ContentSourceService.create_source(db, data.model_dump())
    except ValueError as exc:
        return _error(status.HTTP_400_BAD_REQUEST, str(exc))
    return {"success": True, "data": source.to_dict()}


@router.patch("/priorities")
async def update_content_source_priorities(
    data: ContentSourcePriorityUpdate,
    db: AsyncSession = Depends(get_db),
    session: DBSession = Depends(verify_session),
):
    try:
        sources = await ContentSourceService.update_priorities(
            db,
            [item.model_dump() for item in data.items],
        )
    except LookupError as exc:
        return _error(status.HTTP_404_NOT_FOUND, str(exc))
    except ValueError as exc:
        return _error(status.HTTP_400_BAD_REQUEST, str(exc))
    return {"success": True, "data": [source.to_dict() for source in sources]}


@router.post("/test-all")
async def test_all_content_sources(
    db: AsyncSession = Depends(get_db),
    session: DBSession = Depends(verify_session),
):
    results = await ContentSourceService.test_all(db)
    return {
        "success": True,
        "data": [_serialize_test_result(result) for result in results],
    }


@router.put("/{source_id}")
async def update_content_source(
    source_id: str,
    data: ContentSourceUpdate,
    db: AsyncSession = Depends(get_db),
    session: DBSession = Depends(verify_session),
):
    try:
        source = await ContentSourceService.update_source(
            db,
            source_id,
            data.model_dump(exclude_unset=True),
        )
    except LookupError as exc:
        return _error(status.HTTP_404_NOT_FOUND, str(exc))
    except ValueError as exc:
        return _error(status.HTTP_400_BAD_REQUEST, str(exc))
    return {"success": True, "data": source.to_dict()}


@router.delete("/{source_id}")
async def archive_content_source(
    source_id: str,
    db: AsyncSession = Depends(get_db),
    session: DBSession = Depends(verify_session),
):
    try:
        source = await ContentSourceService.archive_source(db, source_id)
    except LookupError as exc:
        return _error(status.HTTP_404_NOT_FOUND, str(exc))
    return {
        "success": True,
        "message": "内容源已归档",
        "data": source.to_dict(),
    }


@router.post("/{source_id}/test")
async def test_content_source(
    source_id: str,
    db: AsyncSession = Depends(get_db),
    session: DBSession = Depends(verify_session),
):
    try:
        result = await ContentSourceService.test_source(db, source_id)
    except LookupError as exc:
        return _error(status.HTTP_404_NOT_FOUND, str(exc))
    serialized = _serialize_test_result(result)
    return {"success": result.get("success", False), "data": serialized}
