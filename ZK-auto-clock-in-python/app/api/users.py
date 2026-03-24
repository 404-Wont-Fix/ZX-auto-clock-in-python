"""
用户管理 API
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
import logging

from app.core.database import get_db
from app.api.auth import verify_session
from app.models.database import Session as DBSession
from app.models.schemas import (
    UserCreate,
    UserUpdate,
    UserResponse,
    UserListResponse,
    UserToggleRequest,
    SuccessResponse,
    ErrorResponse
)
from app.services.user_service import UserService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/users", tags=["用户管理"])


@router.get("", response_model=UserListResponse)
async def get_users(
    db: AsyncSession = Depends(get_db),
    session: DBSession = Depends(verify_session)
):
    """获取所有用户"""
    try:
        users = await UserService.get_users(db)

        user_list = []
        for user in users:
            user_dict = user.to_dict()
            user_list.append(user_dict)

        return UserListResponse(
            success=True,
            data=user_list
        )
    except Exception as e:
        logger.error(f"获取用户列表失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"获取用户列表失败: {str(e)}"
        )


@router.post("", response_model=SuccessResponse)
async def create_user(
    user_data: UserCreate,
    db: AsyncSession = Depends(get_db),
    session: DBSession = Depends(verify_session)
):
    """添加新用户"""
    # 验证用户名和密码
    valid, error = UserService.validate_username(user_data.username)
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error
        )

    valid, error = UserService.validate_password(user_data.password)
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error
        )

    # 检查用户名是否已存在
    existing = await UserService.get_user_by_username(db, user_data.username)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户名已存在"
        )

    # 创建用户
    user = await UserService.create_user(db, user_data)

    return SuccessResponse(
        success=True,
        data=user.to_dict()
    )


@router.put("/{user_id}", response_model=SuccessResponse)
async def update_user(
    user_id: str,
    updates: UserUpdate,
    db: AsyncSession = Depends(get_db),
    session: DBSession = Depends(verify_session)
):
    """更新用户信息"""
    try:
        user = await UserService.update_user(db, user_id, updates)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="用户不存在"
            )
        return SuccessResponse(success=True, data=user.to_dict())
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.delete("/{user_id}", response_model=SuccessResponse)
async def delete_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    session: DBSession = Depends(verify_session)
):
    """删除用户"""
    success = await UserService.delete_user(db, user_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )
    return SuccessResponse(success=True, message="用户已删除")


@router.patch("/{user_id}/toggle", response_model=SuccessResponse)
async def toggle_user(
    user_id: str,
    request: UserToggleRequest,
    db: AsyncSession = Depends(get_db),
    session: DBSession = Depends(verify_session)
):
    """启用/禁用用户"""
    user = await UserService.toggle_user(db, user_id, request.enabled)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )
    return SuccessResponse(success=True, data=user.to_dict())
