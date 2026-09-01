"""
Worker API 管理 API
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from app.core.database import get_db
from app.api.auth import verify_session
from app.models.database import Session as DBSession
from app.models.schemas import (
    WorkerApiCreate,
    WorkerApiUpdate,
    WorkerApiResponse,
    WorkerApiListResponse,
    WorkerApiTestResponse,
    SuccessResponse,
    ErrorResponse
)
from app.services.worker_api_service import WorkerApiService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/worker-apis", tags=["Worker API 管理"])


@router.get("", response_model=WorkerApiListResponse)
async def get_worker_apis(
    db: AsyncSession = Depends(get_db),
    session: DBSession = Depends(verify_session)
):
    """获取所有 Worker API"""
    try:
        apis = await WorkerApiService.get_all_apis(db)

        api_list = []
        for api in apis:
            api_dict = api.to_dict()
            api_list.append(api_dict)

        return WorkerApiListResponse(
            success=True,
            data=api_list
        )
    except Exception as e:
        logger.error(f"获取 Worker API 列表失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="获取 Worker API 列表失败，请查看服务端日志"
        )


@router.post("", response_model=SuccessResponse)
async def create_worker_api(
    api_data: WorkerApiCreate,
    db: AsyncSession = Depends(get_db),
    session: DBSession = Depends(verify_session)
):
    """创建新的 Worker API"""
    try:
        api = await WorkerApiService.create_api(db, api_data)

        return SuccessResponse(
            success=True,
            message=f"Worker API '{api.name}' 创建成功",
            data=api.to_dict()
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"创建 Worker API 失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="创建 Worker API 失败，请查看服务端日志"
        )


@router.put("/{api_id}", response_model=SuccessResponse)
async def update_worker_api(
    api_id: str,
    updates: WorkerApiUpdate,
    db: AsyncSession = Depends(get_db),
    session: DBSession = Depends(verify_session)
):
    """更新 Worker API"""
    try:
        api = await WorkerApiService.update_api(db, api_id, updates)

        if not api:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Worker API 不存在"
            )

        return SuccessResponse(
            success=True,
            message=f"Worker API '{api.name}' 更新成功",
            data=api.to_dict()
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"更新 Worker API 失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="更新 Worker API 失败，请查看服务端日志"
        )


@router.delete("/{api_id}", response_model=SuccessResponse)
async def delete_worker_api(
    api_id: str,
    db: AsyncSession = Depends(get_db),
    session: DBSession = Depends(verify_session)
):
    """删除 Worker API"""
    try:
        result = await WorkerApiService.delete_api(db, api_id)

        if not result['success']:
            # 如果是业务逻辑错误（如删除默认API）
            if 'error' in result:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=result['error']
                )
            # 如果是找不到API
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Worker API 不存在"
            )

        return SuccessResponse(
            success=True,
            message="Worker API 删除成功"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除 Worker API 失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="删除 Worker API 失败，请查看服务端日志"
        )


@router.post("/{api_id}/test", response_model=WorkerApiTestResponse)
async def test_worker_api(
    api_id: str,
    db: AsyncSession = Depends(get_db),
    session: DBSession = Depends(verify_session)
):
    """测试 Worker API 连接"""
    try:
        result = await WorkerApiService.test_connection(db, api_id)

        if not result.get('success') and '不存在' in result.get('message', ''):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Worker API 不存在"
            )

        return WorkerApiTestResponse(**result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"测试 Worker API 失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="测试 Worker API 失败，请查看服务端日志"
        )


@router.post("/{api_id}/reset", response_model=SuccessResponse)
async def reset_worker_api(
    api_id: str,
    db: AsyncSession = Depends(get_db),
    session: DBSession = Depends(verify_session)
):
    """重置 Worker API 可用状态"""
    try:
        api = await WorkerApiService.reset_availability(db, api_id)

        if not api:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Worker API 不存在"
            )

        return SuccessResponse(
            success=True,
            message=f"Worker API '{api.name}' 状态已重置",
            data=api.to_dict()
        )
    except Exception as e:
        logger.error(f"重置 Worker API 状态失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="重置 Worker API 状态失败，请查看服务端日志"
        )
