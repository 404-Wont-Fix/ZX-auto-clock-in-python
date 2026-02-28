"""
认证 API
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timedelta
from typing import Optional

from app.core.database import get_db
from app.core.security import create_access_token, generate_session_token, decode_access_token
from app.models.database import Session as DBSession
from app.models.schemas import LoginRequest, LoginResponse, ErrorResponse, SuccessResponse

router = APIRouter(prefix="/api/auth", tags=["认证"])


@router.post("/login", response_model=LoginResponse)
async def login(
    request: LoginRequest,
    db: AsyncSession = Depends(get_db)
):
    """管理员登录"""
    from app.config import settings

    # 验证用户名和密码
    if request.username != settings.admin_username or request.password != settings.admin_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误"
        )

    # 创建 Session Token
    token = generate_session_token()
    expires_at = datetime.utcnow() + timedelta(hours=24)

    # 保存到数据库
    session = DBSession(
        token=token,
        username=request.username,
        expires_at=expires_at
    )
    db.add(session)
    await db.commit()

    return LoginResponse(
        success=True,
        token=token,
        username=request.username
    )


@router.post("/logout", response_model=SuccessResponse)
async def logout(
    db: AsyncSession = Depends(get_db),
    token: Optional[str] = Query(None, alias="token")
):
    """管理员登出"""
    if not token:
        # 尝试从 header 获取
        raise HTTPException(status_code=401, detail="Token 缺失")

    # 删除 session
    from sqlalchemy import delete
    await db.execute(
        delete(DBSession).where(DBSession.token == token)
    )
    await db.commit()

    return SuccessResponse(success=True, message="已登出")


@router.get("/me", response_model=SuccessResponse)
async def get_current_user(
    db: AsyncSession = Depends(get_db),
    token: Optional[str] = Query(None, alias="token")
):
    """获取当前用户信息"""
    if not token:
        raise HTTPException(status_code=401, detail="Token 缺失")

    # 验证 token
    result = await db.execute(
        select(DBSession).where(
            DBSession.token == token,
            DBSession.expires_at > datetime.utcnow()
        )
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 无效或已过期"
        )

    return SuccessResponse(
        success=True,
        data={
            "username": session.username,
            "created_at": session.created_at.isoformat(),
            "expires_at": session.expires_at.isoformat()
        }
    )


# 依赖：验证 token（从查询参数或 header 获取）
async def verify_session(
    token: Optional[str] = Query(None, alias="token"),
    db: AsyncSession = Depends(get_db)
) -> DBSession:
    """验证会话令牌"""
    print(f"[Auth] verify_session called, token: {token[:10] if token else 'None'}...")

    if not token:
        print("[Auth] Token 缺失")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 缺失"
        )

    from sqlalchemy import select

    result = await db.execute(
        select(DBSession).where(
            DBSession.token == token,
            DBSession.expires_at > datetime.utcnow()
        )
    )
    session = result.scalar_one_or_none()

    if not session:
        print(f"[Auth] Session not found or expired for token: {token[:10]}...")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未授权"
        )

    print(f"[Auth] Session found for user: {session.username}")
    return session
