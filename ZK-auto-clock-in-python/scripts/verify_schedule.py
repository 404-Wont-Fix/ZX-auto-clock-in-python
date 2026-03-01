"""
验证定时任务的下次执行时间
"""
import sys
import os
from datetime import datetime
import pytz

# 设置输出编码
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.core.scheduler import scheduler, get_schedule_info


def verify_schedule():
    """验证定时任务配置"""
    print("=" * 70)
    print("定时任务执行时间验证")
    print("=" * 70)

    # 显示当前时间
    beijing_tz = pytz.timezone('Asia/Shanghai')
    utc_tz = pytz.UTC

    now_beijing = datetime.now(beijing_tz)
    now_utc = datetime.now(utc_tz)

    print(f"\n[当前时间]")
    print(f"  北京时间: {now_beijing.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print(f"  UTC 时间: {now_utc.strftime('%Y-%m-%d %H:%M:%S %Z')}")

    # 显示配置
    print(f"\n[系统配置]")
    print(f"  Cron 表达式: {settings.schedule_cron}")
    print(f"  时区: {settings.schedule_timezone}")
    print(f"  定时任务: {'启用' if settings.schedule_enabled else '禁用'}")

    # 获取调度器状态
    print(f"\n[调度器状态]")
    if scheduler is None:
        print("  [!] 调度器未启动")
        print("  提示: 请启动应用后再测试")
        return

    print(f"  [OK] 调度器已启动")

    # 获取任务信息
    job = scheduler.get_job('clockin')
    if not job:
        print("  [!] 未找到定时打卡任务")
        return

    print(f"  [OK] 找到定时打卡任务: {job.name}")
    print(f"  触发器: {job.trigger}")

    if job.next_run_time:
        next_run = job.next_run_time
        print(f"\n[下次执行时间]")
        print(f"  原始时间: {next_run.isoformat()}")
        print(f"  北京时间: {next_run.astimezone(beijing_tz).strftime('%Y-%m-%d %H:%M:%S %Z')}")
        print(f"  UTC 时间: {next_run.astimezone(utc_tz).strftime('%Y-%m-%d %H:%M:%S %Z')}")

        # 计算倒计时
        now = datetime.now(beijing_tz)
        diff = next_run.astimezone(beijing_tz) - now
        days = diff.days
        hours = diff.seconds // 3600
        minutes = (diff.seconds % 3600) // 60
        seconds = diff.seconds % 60

        print(f"\n[倒计时]")
        if days > 0:
            print(f"  距离下次执行: {days} 天 {hours} 时 {minutes} 分")
        elif hours > 0:
            print(f"  距离下次执行: {hours} 时 {minutes} 分 {seconds} 秒")
        elif minutes > 0:
            print(f"  距离下次执行: {minutes} 分 {seconds} 秒")
        else:
            print(f"  距离下次执行: {seconds} 秒")

        # 验证时间是否正确
        print(f"\n[验证结果]")
        cron_parts = settings.schedule_cron.split()
        if len(cron_parts) >= 3:
            cron_hour = int(cron_parts[2])
            cron_minute = int(cron_parts[1])

            next_run_hour_beijing = next_run.astimezone(beijing_tz).hour
            next_run_minute_beijing = next_run.astimezone(beijing_tz).minute

            if next_run_hour_beijing == cron_hour and next_run_minute_beijing == cron_minute:
                print(f"  [OK] 执行时间正确: 北京时间 {cron_hour:02d}:{cron_minute:02d}")
            else:
                print(f"  [!] 时间不匹配!")
                print(f"      Cron 设置: {cron_hour:02d}:{cron_minute:02d}")
                print(f"      实际执行: {next_run_hour_beijing:02d}:{next_run_minute_beijing:02d}")

    print("\n" + "=" * 70)
    print("验证完成")
    print("=" * 70)


if __name__ == '__main__':
    try:
        verify_schedule()
    except Exception as e:
        print(f"\n[X] 验证失败: {e}")
        import traceback
        traceback.print_exc()
