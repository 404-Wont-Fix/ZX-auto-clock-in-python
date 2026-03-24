"""
数据库迁移脚本：为 clockin_results 表添加 API 使用信息字段
"""
import asyncio
import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.core.database import engine


async def migrate():
    """执行数据库迁移"""
    print("====================================")
    print("数据库迁移：添加 API 使用信息字段")
    print("====================================")
    print()

    async with engine.begin() as conn:
        # 检查字段是否已存在
        result = await conn.execute(text("PRAGMA table_info(clockin_results)"))
        columns = result.fetchall()
        existing_columns = {col[1] for col in columns}

        # 需要添加的字段
        new_fields = [
            ('sports_comment_api', 'VARCHAR'),
            ('daily_comment_api', 'VARCHAR'),
            ('sports_image_type', 'VARCHAR'),
            ('sports_image_provider', 'VARCHAR'),
            ('sports_image_category', 'VARCHAR'),
        ]

        added_count = 0
        for field_name, field_type in new_fields:
            if field_name not in existing_columns:
                sql = f"ALTER TABLE clockin_results ADD COLUMN {field_name} {field_type}"
                print(f"[迁移] 添加字段: {field_name}")
                await conn.execute(text(sql))
                added_count += 1
            else:
                print(f"[跳过] 字段已存在: {field_name}")

        print()
        if added_count > 0:
            print(f"====================================")
            print(f"[完成] 成功添加 {added_count} 个新字段！")
            print(f"====================================")
        else:
            print(f"====================================")
            print(f"[完成] 所有字段已存在，无需迁移")
            print(f"====================================")

    await engine.dispose()


if __name__ == '__main__':
    exit_code = asyncio.run(migrate())
    sys.exit(exit_code)
