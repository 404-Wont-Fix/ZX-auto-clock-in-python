"""
检查打卡记录数据
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import AsyncSessionLocal
from app.models.database import ClockinResult
from sqlalchemy import select


async def check_result():
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ClockinResult)
            .order_by(ClockinResult.created_at.desc())
            .limit(1)
        )
        record = result.scalar_one_or_none()
        if record:
            print(f"Username: {record.username}")
            print(f"Success: {record.success}")
            print(f"details_json type: {type(record.details_json)}")
            print(f"details_json length: {len(record.details_json) if record.details_json else 0}")
            if record.details_json:
                print(f"details_json (first 200 chars): {record.details_json[:200]}")
            print(f"sports_comment: {record.sports_comment}")
            print(f"daily_comment: {record.daily_comment}")
        else:
            print("No records found")


if __name__ == '__main__':
    asyncio.run(check_result())
