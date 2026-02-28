"""
快速检查数据库内容
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import AsyncSessionLocal
from app.models.database import User
from sqlalchemy import select


async def check_database():
    """检查数据库内容"""
    async with AsyncSessionLocal() as db:
        # 检查用户表
        result = await db.execute(select(User))
        users = result.scalars().all()

        print(f"数据库中的用户数: {len(users)}")

        if users:
            for user in users:
                print(f"  - {user.username} ({'启用' if user.enabled else '禁用'})")
        else:
            print("  数据库为空，需要添加用户")

        # 检查表结构
        from app.core.database import Base, engine
        from sqlalchemy import text

        async with engine.begin() as conn:
            result = await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
            tables = result.fetchall()
            print(f"\n数据库表: {[t[0] for t in tables]}")


if __name__ == '__main__':
    asyncio.run(check_database())
