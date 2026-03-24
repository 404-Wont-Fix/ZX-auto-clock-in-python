"""
数据库备份脚本
"""
import shutil
import os
from datetime import datetime


def backup_database():
    """备份数据库"""
    # 数据库文件路径
    db_file = "database/zk_admin.db"

    if not os.path.exists(db_file):
        print(f"[错误] 数据库文件不存在: {db_file}")
        return False

    # 创建备份目录
    backup_dir = "backups"
    os.makedirs(backup_dir, exist_ok=True)

    # 备份文件名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = f"{backup_dir}/zk_admin_{timestamp}.db"

    # 复制文件
    try:
        shutil.copy2(db_file, backup_file)
        print(f"[成功] 数据库已备份到: {backup_file}")

        # 获取文件大小
        size_mb = os.path.getsize(backup_file) / (1024 * 1024)
        print(f"[信息] 备份文件大小: {size_mb:.2f} MB")

        return True
    except Exception as e:
        print(f"[错误] 备份失败: {e}")
        return False


if __name__ == '__main__':
    print("====================================")
    print("ZK Admin - 数据库备份")
    print("====================================")
    print()

    success = backup_database()

    print()
    if success:
        print("[完成] 备份成功")
    else:
        print("[失败] 备份失败")
