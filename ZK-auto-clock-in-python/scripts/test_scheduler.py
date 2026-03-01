"""
测试调度器配置和状态
"""
import asyncio
import sys
from pathlib import Path
from datetime import datetime
import pytz

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import settings
from app.core.scheduler import parse_cron_expression, get_schedule_info


def test_timezone_config():
    """测试时区配置"""
    print("=" * 60)
    print("1. Timezone Configuration Test")
    print("=" * 60)

    print(f"Configured Timezone: {settings.schedule_timezone}")
    print(f"Cron Expression: {settings.schedule_cron}")
    print(f"Schedule Enabled: {settings.schedule_enabled}")

    # 验证时区是否有效
    try:
        tz = pytz.timezone(settings.schedule_timezone)
        now_utc = datetime.now(pytz.UTC)
        now_local = now_utc.astimezone(tz)
        print(f"\nCurrent UTC Time: {now_utc.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        print(f"Current Local Time: {now_local.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        print("[OK] Timezone configuration is valid")
    except pytz.exceptions.UnknownTimeZoneError:
        print(f"[ERROR] Unknown timezone: '{settings.schedule_timezone}'")
        return False

    return True


def test_cron_parsing():
    """Test Cron expression parsing"""
    print("\n" + "=" * 60)
    print("2. Cron Expression Parsing Test")
    print("=" * 60)

    try:
        trigger = parse_cron_expression(settings.schedule_cron, settings.schedule_timezone)
        print(f"[OK] Cron expression parsed successfully")
        print(f"  Trigger type: {type(trigger).__name__}")

        # 获取下次几次执行时间
        from datetime import datetime
        now = datetime.now()

        print(f"\nNext 5 execution times:")
        for i in range(5):
            next_time = trigger._get_next_fire_time(now, None)
            if next_time:
                print(f"  {i+1}. {next_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
                now = next_time
            else:
                break

        return True
    except Exception as e:
        print(f"[ERROR] Failed to parse cron expression: {e}")
        return False


async def test_scheduler_status():
    """Test scheduler status"""
    print("\n" + "=" * 60)
    print("3. Scheduler Status Check")
    print("=" * 60)

    # 注意：这需要在应用运行时才能获取到有效信息
    schedule_info = await get_schedule_info()

    if schedule_info:
        print("[OK] Scheduler is running")
        print(f"  Job ID: {schedule_info['id']}")
        print(f"  Job Name: {schedule_info['name']}")
        print(f"  Next Run Time: {schedule_info['next_run_time']}")
        print(f"  Trigger: {schedule_info['trigger']}")
        return True
    else:
        print("[ERROR] Scheduler is not running or job not configured")
        print("\nPossible reasons:")
        print("  1. Application is not started")
        print("  2. schedule_enabled = False")
        print("  3. Scheduler failed to start")
        return False


def print_common_issues():
    """Print common issues"""
    print("\n" + "=" * 60)
    print("4. Common Issues Troubleshooting")
    print("=" * 60)

    print("""
If scheduled tasks are not working, check the following:

1. Check log files (logs/*.log)
   - Look for "Scheduler started" message
   - Look for "Clockin job added" message
   - Look for "Next run time" information

2. Check timezone configuration
   - Current timezone: {tz}
   - For Beijing time, use: Asia/Shanghai
   - For UTC time, use: UTC

3. Check Cron expression
   - Current expression: {cron}
   - Format: second minute hour day month weekday
   - Example for Beijing 0:10:
        UTC: "0 10 16 * * *"
        Asia/Shanghai: "0 10 0 * * *"

4. Check schedule enabled
   - schedule_enabled = {enabled}

5. Check scheduler status (requires app running)
   - API: GET /api/config/schedule
   - Or check in admin dashboard

6. Manual test scheduled task
   - API: POST /api/clockin/trigger-all
   - Verify all users can clock in successfully
    """.format(
        tz=settings.schedule_timezone,
        cron=settings.schedule_cron,
        enabled=settings.schedule_enabled
    ))


def main():
    """Main function"""
    print("\n" + "=" * 60)
    print("ZK Admin Scheduled Task Diagnostic Tool")
    print("=" * 60)

    # 运行测试
    results = []

    results.append(("Timezone Config", test_timezone_config()))
    results.append(("Cron Parsing", test_cron_parsing()))

    # 调度器状态测试（需要异步）
    print("\nNote: Scheduler status check requires the app to be running")

    # 打印常见问题
    print_common_issues()

    # 总结
    print("\n" + "=" * 60)
    print("Diagnostic Summary")
    print("=" * 60)

    for name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"  {name}: {status}")

    print("\n" + "=" * 60)
    print("Recommended Next Steps")
    print("=" * 60)
    print("""
1. Start the application and check startup logs:
   python -m uvicorn app.main:app --reload

2. Look for scheduler information in logs:
   - "Using timezone: ..."
   - "Clockin job added: ..."
   - "Next run time: ..."
   - "Scheduler started"

3. Check scheduler status via API:
   curl http://localhost:8000/api/config/schedule \\
     -H "Authorization: Bearer YOUR_TOKEN"

4. If everything is OK, wait for next scheduled execution or manually trigger test
    """)


if __name__ == "__main__":
    main()
