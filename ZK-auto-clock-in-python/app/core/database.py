"""
数据库连接配置
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import StaticPool
import os
from app.config import settings

# 确保数据库目录存在
os.makedirs("database", exist_ok=True)

# 创建异步引擎
# SQLite 需要使用 aiosqlite 驱动
engine = create_async_engine(
    settings.database_url.replace("sqlite://", "sqlite+aiosqlite://"),
    connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {},
    poolclass=StaticPool,  # SQLite 使用静态连接池
    echo=settings.debug,  # 开发模式下打印 SQL
)

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
        from app.models.database import User, ClockinResult, DailySummary, Task, Config, Session

        # 创建所有表
        await conn.run_sync(Base.metadata.create_all)
        print("[数据库] 数据表初始化完成")


async def close_db():
    """关闭数据库连接"""
    await engine.dispose()
    print("[数据库] 数据库连接已关闭")
