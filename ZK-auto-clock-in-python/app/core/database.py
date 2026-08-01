"""
数据库连接配置
"""
from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
import os
from app.config import settings

# 确保数据库目录存在
os.makedirs("database", exist_ok=True)

# 文件 SQLite 使用 SQLAlchemy/aiosqlite 默认的独立连接池（NullPool）。
# 禁止 StaticPool：它会让多个 AsyncSession 共用一个事务连接。
database_url = settings.database_url.replace("sqlite://", "sqlite+aiosqlite://")
is_sqlite = database_url.startswith("sqlite+aiosqlite:")
engine = create_async_engine(
    database_url,
    connect_args={"check_same_thread": False, "timeout": 30} if is_sqlite else {},
    echo=settings.debug,
    hide_parameters=True,
)


if is_sqlite:
    @event.listens_for(engine.sync_engine, "connect")
    def _configure_sqlite_connection(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()

# 创建会话工厂
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# 创建基类
Base = declarative_base()


async def get_db() -> AsyncSession:
    """获取数据库会话（依赖注入）"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """初始化数据库表"""
    async with engine.begin() as conn:
        # 导入所有模型
        from app.models.database import (
            ClockinResult,
            Config,
            ContentSource,
            DailySummary,
            Session,
            Task,
            User,
            WorkerApi,
        )

        # 创建所有表
        await conn.run_sync(Base.metadata.create_all)
        print("[数据库] 数据表初始化完成")


async def close_db():
    """关闭数据库连接"""
    await engine.dispose()
    print("[数据库] 数据库连接已关闭")
