"""
认证 API
"""
from fastapi import APIRouter, Depends, HTTPException, status, Header, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timedelta
from typing import Optional
import logging
import time
from collections import defaultdict

from app.core.database import get_db
from app.core.security import create_access_token, generate_session_token, decode_access_token
from app.models.database import Session as DBSession
from app.models.schemas import LoginRequest, LoginResponse, ErrorResponse, SuccessResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["认证"])

# 登录速率限制存储（内存）
# 结构: {ip_address: [(timestamp, success), ...]}
login_attempts = defaultdict(list)

# 登录速率限制配置
MAX_ATTEMPTS = 5  # 最大尝试次数
LOCKOUT_DURATION = 900  # 锁定时长（秒）- 15分钟
ATTEMPT_WINDOW = 300  # 尝试时间窗口（秒）- 5分钟


def check_login_rate_limit(ip_address: str) -> tuple[bool, Optional[str]]:
    """检查登录速率限制

    Returns:
        (allowed, error_message): 是否允许登录，以及错误信息
    """
    now = time.time()
    attempts = login_attempts[ip_address]

    # 清理过期的尝试记录
    login_attempts[ip_address] = [
        (timestamp, success) for timestamp, success in attempts
        if now - timestamp < ATTEMPT_WINDOW
    ]
    attempts = login_attempts[ip_address]

    # 计算失败的尝试次数
    failed_attempts = sum(1 for _, success in attempts if not success)

    if failed_attempts >= MAX_ATTEMPTS:
        # 找到第一次失败的时间
        first_failure = next(
            (timestamp for timestamp, success in attempts if not success),
            now
        )
        remaining_time = int(LOCKOUT_DURATION - (now - first_failure))

        if remaining_time > 0:
            minutes = remaining_time // 60
            seconds = remaining_time % 60
            return False, f"登录尝试次数过多，请在 {minutes} 分 {seconds} 秒后重试"

    return True, None


def record_login_attempt(ip_address: str, success: bool):
    """记录登录尝试"""
    login_attempts[ip_address].append((time.time(), success))
    # 如果登录成功，清除该IP的失败记录
    if success:
        login_attempts[ip_address] = [(time.time(), True)]


@router.post("/login", response_model=LoginResponse)
async def login(
    request: LoginRequest,
    http_request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db)
):
    """管理员登录"""
    from app.config import settings

    # 获取客户端 IP
    client_ip = http_request.client.host if http_request.client else "unknown"

    # 检查速率限制
    allowed, error_message = check_login_rate_limit(client_ip)
    if not allowed:
        logger.warning(f"登录被拒绝（速率限制）: IP={client_ip}")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=error_message
        )

    # 验证用户名和密码
    if request.username != settings.admin_username or request.password != settings.admin_password:
        # 记录失败尝试
        record_login_attempt(client_ip, False)
        logger.warning(f"登录失败: IP={client_ip}, username={request.username}")

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误"
        )

    # 记录成功尝试
    record_login_attempt(client_ip, True)
    logger.info(f"登录成功: IP={client_ip}, username={request.username}")

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

    # 同时通过 httpOnly cookie 下发 token，供 /dashboard 等页面路由做服务端鉴权
    # （浏览器导航不会带 Authorization 头，但会带 cookie）
    response.set_cookie(
        key="admin_session",
        value=token,
        max_age=24 * 3600,  # 与 session 过期时间一致（24h）
        httponly=True,
        samesite="lax",
        path="/",
    )

    return LoginResponse(
        success=True,
        token=token,
        username=request.username
    )


@router.post("/logout", response_model=SuccessResponse)
async def logout(
    response: Response,
    db: AsyncSession = Depends(get_db),
    authorization: Optional[str] = Header(None)
):
    """管理员登出"""
    # 从 Authorization header 获取 token
    if authorization and authorization.startswith("Bearer "):
        token = authorization.replace("Bearer ", "")
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 缺失或格式错误"
        )

    # 删除 session
    from sqlalchemy import delete
    await db.execute(
        delete(DBSession).where(DBSession.token == token)
    )
    await db.commit()

    # 清除页面路由鉴权用的 cookie
    response.delete_cookie(key="admin_session", path="/")

    logger.info("用户已登出")
    return SuccessResponse(success=True, message="已登出")


@router.get("/me", response_model=SuccessResponse)
async def get_current_user(
    db: AsyncSession = Depends(get_db),
    authorization: Optional[str] = Header(None)
):
    """获取当前用户信息"""
    # 从 Authorization header 获取 token
    if authorization and authorization.startswith("Bearer "):
        token = authorization.replace("Bearer ", "")
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 缺失或格式错误"
        )

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


# 依赖：验证 token（从 Authorization header 获取）
async def verify_session(
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db)
) -> DBSession:
    """验证会话令牌"""
    # 从 Authorization header 获取 token
    if authorization and authorization.startswith("Bearer "):
        token = authorization.replace("Bearer ", "")
        logger.debug("verify_session 收到 Bearer Token")
    else:
        logger.warning("verify_session called without valid Authorization header")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 缺失或格式错误，需要使用 Authorization: Bearer <token>"
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
        logger.warning("Session 不存在或已过期")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 无效或已过期"
        )

    logger.debug(f"Session verified for user: {session.username}")
    return session
