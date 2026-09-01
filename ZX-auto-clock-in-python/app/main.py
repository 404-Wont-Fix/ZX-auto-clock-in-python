"""
FastAPI 应用主入口
"""
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse, Response, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from typing import Optional
from datetime import datetime
import logging

from app.config import settings
from app.core.database import AsyncSessionLocal, close_db, get_db, init_db
from app.core.scheduler import start_scheduler, stop_scheduler
from sqlalchemy import select, text
from app.models.database import Session as DBSession

# 配置日志
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 关闭 SQLAlchemy 的 SQL 语句日志
logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)
logging.getLogger('sqlalchemy.pool').setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动
    logger.info("=== ZX Admin 启动中 ===")
    logger.info(f"环境: {settings.app_env}")
    logger.info(f"调试模式: {settings.debug}")

    # 初始化数据库
    try:
        await init_db()
        from app.services.content_source_service import ContentSourceService
        from app.services.task_service import TaskOrchestrator
        async with AsyncSessionLocal() as db:
            await ContentSourceService.ensure_default_sources(db)
            interrupted = await TaskOrchestrator.interrupt_stale_tasks(db)
            if interrupted:
                logger.warning("已将 %s 个遗留打卡任务标记为中断", interrupted)
        logger.info("数据库初始化完成")
    except Exception as exc:
        logger.error("数据库初始化失败（%s），拒绝启动", type(exc).__name__)
        await close_db()
        raise

    # 启动调度器
    try:
        await start_scheduler()
        logger.info("调度器已启动")
    except Exception as e:
        logger.error(f"调度器启动失败: {e}")

    yield

    # 关闭
    logger.info("=== ZX Admin 关闭中 ===")

    # 清理活动任务（防止任务泄漏）
    try:
        from app.services.active_task_service import ActiveTaskService
        stale_count = await ActiveTaskService.cleanup_stale_tasks(max_age_seconds=0)  # 清理所有
        if stale_count > 0:
            logger.warning(f"清理了 {stale_count} 个未完成的活动任务")
    except Exception as e:
        logger.error(f"清理活动任务失败: {e}")

    stop_scheduler()
    await close_db()
    logger.info("已清理资源")


# 创建 FastAPI 应用
app = FastAPI(
    title="ZX Admin",
    description="ZX 多用户自动打卡管理系统",
    version="2.0.0",
    lifespan=lifespan
)

# 配置 CORS（显式限定方法与头部，避免与 allow_credentials=True 叠加时过松）
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


# ==================== 静态文件路由 ====================

# 挂载静态资源目录
try:
    app.mount("/assets", StaticFiles(directory="app/ui/assets"), name="assets")
except Exception:
    logger.warning("静态资源目录未找到")


# ==================== 页面路由 ====================

@app.get("/", response_class=HTMLResponse)
async def root():
    """根路径返回 nginx 欢迎页（伪装）"""
    html_file = "app/ui/pages/404.html"
    try:
        with open(html_file, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        return "<h1>Welcome to nginx!</h1>"


@app.get(f"/{settings.admin_path}", response_class=HTMLResponse)
async def admin_login():
    """管理面板入口（显示登录页）- 路径可通过环境变量配置"""
    html_file = "app/ui/pages/login.html"
    try:
        with open(html_file, 'r', encoding='utf-8') as f:
            content = f.read()
        # 注入 admin_path 到 HTML
        script = f'<script>window.ADMIN_PATH = "/{settings.admin_path}";</script>'
        return content.replace('</head>', f'{script}</head>')
    except FileNotFoundError:
        return "<h1>Login not found</h1>"


async def _is_valid_page_session(token: Optional[str]) -> bool:
    """校验页面路由鉴权用的 session token（来自 admin_session cookie）"""
    if not token:
        return False
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(DBSession).where(
                    DBSession.token == token,
                    DBSession.expires_at > datetime.utcnow()
                )
            )
            return result.scalar_one_or_none() is not None
    except Exception:
        logger.exception("校验页面 session 失败")
        return False


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    """管理面板（服务端鉴权：校验 admin_session cookie，未登录重定向到登录入口）"""
    token = request.cookies.get("admin_session")
    if not await _is_valid_page_session(token):
        return RedirectResponse(url=f"/{settings.admin_path}", status_code=302)

    html_file = "app/ui/pages/index.html"
    try:
        with open(html_file, 'r', encoding='utf-8') as f:
            content = f.read()
        # 注入 admin_path 到 HTML
        script = f'<script>window.ADMIN_PATH = "/{settings.admin_path}";</script>'
        return content.replace('</head>', f'{script}</head>')
    except FileNotFoundError:
        return "<h1>Dashboard not found</h1>"


# ==================== API 路由 ====================

from app.api import auth, users, clockin, config, content_sources, dashboard, maintenance
from app.api import worker_api

# 认证路由（登录/登出不需要 token 验证）
app.include_router(auth.router)

# 用户管理路由
app.include_router(users.router)

# 打卡操作路由
app.include_router(clockin.router)

# 配置管理路由
app.include_router(config.router)

# 维护路由
app.include_router(maintenance.router)

# Worker API 管理路由
app.include_router(worker_api.router)

# 内容源管理路由
app.include_router(content_sources.router)

# 后台总览路由
app.include_router(dashboard.router)


# ==================== 中间件：Token 验证 ====================

@app.middleware("http")
async def verify_token_middleware(request: Request, call_next):
    """验证 Token 中间件（对于需要认证的页面）"""
    response = await call_next(request)

    # 禁用静态资源缓存
    if request.url.path.startswith("/assets/") or request.url.path.endswith(".html"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"

    return response


# ==================== 健康检查 ====================

@app.get("/health")
async def health_check(db=Depends(get_db)):
    """同时验证进程与 SQLite 可用性的容器健康检查端点。"""
    try:
        await db.execute(text("SELECT 1"))
    except Exception as exc:
        logger.warning("健康检查数据库不可用")
        raise HTTPException(status_code=503, detail="service unavailable") from exc
    return {
        "status": "healthy",
        "service": "zx-admin",
        "version": "2.0.0",
        "database": "ready",
    }


# ==================== 异常处理 ====================

from fastapi.exceptions import RequestValidationError, StarletteHTTPException
from fastapi.responses import JSONResponse


@app.exception_handler(StarletteHTTPException)
async def not_found_exception_handler(request: Request, exc: StarletteHTTPException):
    """处理 404 错误"""
    if exc.status_code == 404:
        # API 路径返回 JSON 错误
        if request.url.path.startswith("/api/"):
            return JSONResponse(
                status_code=404,
                content={"success": False, "error": "API 端点不存在"}
            )
        # 静态资源路径返回 404
        if request.url.path.startswith("/assets/"):
            return JSONResponse(
                status_code=404,
                content={"success": False, "error": "静态资源不存在"}
            )
        # 其他路径返回 nginx 欢迎页（伪装）
        html_file = "app/ui/pages/404.html"
        try:
            with open(html_file, 'r', encoding='utf-8') as f:
                return HTMLResponse(content=f.read(), status_code=200)
        except FileNotFoundError:
            return HTMLResponse(content="<h1>Welcome to nginx!</h1>", status_code=200)
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "error": exc.detail}
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """请求验证异常处理"""
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "error": "请求参数验证失败",
            "detail": exc.errors()
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """通用异常处理"""
    logger.error(f"未处理的异常: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": str(exc) if settings.debug else "服务器内部错误"
        }
    )


# ==================== 启动信息 ====================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
        log_level=settings.log_level.lower()
    )
