"""
测试定时任务时区配置
验证前端设置的时间和后端调度器解析的时间是否一致
"""
import sys
import os
from datetime import datetime
import pytz

# 设置输出编码为 UTF-8
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.core.scheduler import parse_cron_expression


def test_timezone_config():
    """测试时区配置"""
    print("=" * 60)
    print("定时任务时区配置测试")
    print("=" * 60)

    # 显示当前配置
    print(f"\n[当前配置]")
    print(f"  Cron 表达式: {settings.schedule_cron}")
    print(f"  时区: {settings.schedule_timezone}")

    # 解析时区
    try:
        tz = pytz.timezone(settings.schedule_timezone)
        print(f"  时区对象: {tz}")
        now = datetime.now(tz)
        print(f"  当前时间（{settings.schedule_timezone}）: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    except Exception as e:
        print(f"  [X] 时区错误: {e}")
        return False

    # 解析 cron 表达式
    print(f"\n[Cron 表达式解析]")
    try:
        trigger = parse_cron_expression(settings.schedule_cron, settings.schedule_timezone)
        print(f"  [OK] Cron 表达式解析成功")
        print(f"  触发器: {trigger}")
    except Exception as e:
        print(f"  [X] Cron 表达式解析失败: {e}")
        return False

    # 测试几个常见时间
    print(f"\n[测试用例]")
    test_cases = [
        ("00:10", "0 10 0 * * *"),   # 北京时间 00:10
        ("08:00", "0 0 8 * * *"),    # 北京时间 08:00
        ("12:30", "0 30 12 * * *"),  # 北京时间 12:30
        ("18:00", "0 0 18 * * *"),   # 北京时间 18:00
        ("23:59", "0 59 23 * * *"),  # 北京时间 23:59
    ]

    for display_time, cron_expr in test_cases:
        print(f"\n  测试: 北京时间 {display_time}")
        print(f"  Cron: {cron_expr}")

        try:
            trigger = parse_cron_expression(cron_expr, settings.schedule_timezone)

            # 获取下次执行时间
            from apscheduler.schedulers.asyncio import AsyncIOScheduler
            scheduler = AsyncIOScheduler(timezone=settings.schedule_timezone)

            # 添加一个测试任务
            scheduler.add_job(
                lambda: None,
                trigger=trigger,
                id='test_job',
                name='测试任务'
            )

            # 启动调度器
            scheduler.start()

            # 获取下次执行时间
            job = scheduler.get_job('test_job')
            if job and job.next_run_time:
                next_run = job.next_run_time
                print(f"  下次执行: {next_run.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            else:
                print(f"  [X] 无法获取下次执行时间")

            # 关闭调度器
            scheduler.shutdown(wait=False)

        except Exception as e:
            print(f"  [X] 测试失败: {e}")

    # 验证前后端一致性
    print(f"\n[前后端一致性验证]")
    print(f"  前端逻辑: 用户输入北京时间 HH:MM -> 生成 cron '0 MM HH * * *'")
    print(f"  后端配置: 时区 = {settings.schedule_timezone}")
    print(f"  后端解析: cron 在 {settings.schedule_timezone} 时区下执行")

    if settings.schedule_timezone == 'Asia/Shanghai':
        print(f"  [OK] 配置正确：前后端一致使用北京时间")
    else:
        print(f"  [!] 配置可能有问题：后端时区不是 Asia/Shanghai")

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)

    return True


if __name__ == '__main__':
    try:
        test_timezone_config()
    except KeyboardInterrupt:
        print("\n\n测试中断")
    except Exception as e:
        print(f"\n[X] 测试失败: {e}")
        import traceback
        traceback.print_exc()
