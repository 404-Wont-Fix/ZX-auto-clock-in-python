"""
FastAPI 应用主入口
"""
from fastapi import FastAPI, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging

from app.config import settings
from app.core.database import init_db, close_db
from app.core.scheduler import start_scheduler, stop_scheduler

# 配置日志
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动
    logger.info("=== ZK Admin 启动中 ===")
    logger.info(f"环境: {settings.app_env}")
    logger.info(f"调试模式: {settings.debug}")

    # 初始化数据库
    try:
        await init_db()
        logger.info("数据库初始化完成")
    except Exception as e:
        logger.error(f"数据库初始化失败: {e}")

    # 启动调度器
    try:
        start_scheduler()
        logger.info("调度器已启动")
    except Exception as e:
        logger.error(f"调度器启动失败: {e}")

    yield

    # 关闭
    logger.info("=== ZK Admin 关闭中 ===")
    stop_scheduler()
    await close_db()
    logger.info("已清理资源")


# 创建 FastAPI 应用
app = FastAPI(
    title="ZK Admin",
    description="ZK 多用户自动打卡管理系统",
    version="2.0.0",
    lifespan=lifespan
)

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
    """根路径返回 404"""
    html_file = "app/ui/pages/404.html"
    try:
        with open(html_file, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        return "<h1>404 Not Found</h1>"


@app.get("/admin", response_class=HTMLResponse)
async def admin():
    """管理面板入口（显示登录页）"""
    html_file = "app/ui/pages/login.html"
    try:
        with open(html_file, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        return "<h1>Login not found</h1>"


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    """管理面板"""
    html_file = "app/ui/pages/index.html"
    try:
        with open(html_file, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        return "<h1>Dashboard not found</h1>"


# ==================== API 路由 ====================

from app.api import auth, users, clockin, config, maintenance

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
async def health_check():
    """健康检查端点"""
    return {
        "status": "healthy",
        "service": "zk-admin",
        "version": "2.0.0"
    }


# ==================== 异常处理 ====================

from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


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
