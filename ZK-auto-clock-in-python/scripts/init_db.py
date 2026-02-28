"""
数据库初始化脚本
创建数据库表并初始化默认配置
"""
import asyncio
import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import init_db, close_db
from app.models.database import Config, User
from app.core.database import AsyncSessionLocal
from sqlalchemy import select
from datetime import datetime


async def init_default_config():
    """初始化默认配置"""
    async with AsyncSessionLocal() as db:
        # 检查是否已有配置
        result = await db.execute(select(Config))
        existing = result.scalars().all()

        if existing:
            print(f"[配置] 已有 {len(existing)} 条配置，跳过初始化")
            return

        # 默认配置
        default_configs = [
            {
                'key': 'clockin_api_url',
                'value': 'https://zk-clockin-executor.xxx.workers.dev',
                'description': '打卡 API 地址'
            },
            {
                'key': 'clockin_api_token',
                'value': 'local-dev-token-Tian',
                'description': '打卡 API 令牌'
            },
            {
                'key': 'batch_size',
                'value': '3',
                'description': '批处理大小'
            },
            {
                'key': 'batch_delay',
                'value': '2000',
                'description': '批处理延迟(ms)'
            },
            {
                'key': 'parallel_tasks',
                'value': '4',
                'description': '并行任务数'
            },
            {
                'key': 'schedule_cron',
                'value': '0 10 16 * * *',
                'description': '定时任务 Cron 表达式 (UTC 16:10)'
            },
            {
                'key': 'retention_days',
                'value': '7',
                'description': '数据保留天数'
            },
        ]

        for config in default_configs:
            db_config = Config(
                key=config['key'],
                value=config['value'],
                description=config['description']
            )
            db.add(db_config)

        await db.commit()
        print(f"[配置] 已初始化 {len(default_configs)} 条默认配置")


async def main():
    """主函数"""
    print("====================================")
    print("ZK Admin - 数据库初始化")
    print("====================================")
    print()

    try:
        # 1. 初始化数据库表
        print("[1/2] 初始化数据库表...")
        await init_db()

        # 2. 初始化默认配置
        print("[2/2] 初始化默认配置...")
        await init_default_config()

        print()
        print("====================================")
        print("[完成] 数据库初始化成功！")
        print("====================================")
        print()
        print("下一步：")
        print("1. 启动应用: uvicorn app.main:app --reload")
        print("2. 访问: http://localhost:8000/dashboard")
        print("3. 默认账号: admin / admin")
        print()

    except Exception as e:
        print(f"\n[错误] 初始化失败: {e}")
        import traceback
        traceback.print_exc()
        return 1

    finally:
        await close_db()

    return 0


if __name__ == '__main__':
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
