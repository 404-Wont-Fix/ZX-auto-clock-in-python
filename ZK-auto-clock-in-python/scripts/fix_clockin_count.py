"""
修复数据库中 clockin_count 为 None 的问题
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import AsyncSessionLocal
from app.models.database import User
from sqlalchemy import select, update


async def fix_clockin_count():
    """修复所有用户的 clockin_count"""
    async with AsyncSessionLocal() as db:
        # 查找所有 clockin_count 为 None 的用户
        result = await db.execute(
            select(User).where(User.clockin_count == None)
        )
        users = result.scalars().all()

        print(f"找到 {len(users)} 个 clockin_count 为 None 的用户")

        if users:
            # 批量更新
            for user in users:
                user.clockin_count = 0
                print(f"  修复用户: {user.username}")

            await db.commit()
            print("修复完成!")
        else:
            print("没有需要修复的用户")


if __name__ == '__main__':
    asyncio.run(fix_clockin_count())
