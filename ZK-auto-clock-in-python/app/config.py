"""
应用配置管理
"""
from pydantic_settings import BaseSettings
from typing import List
import json


class Settings(BaseSettings):
    """应用配置"""

    # 应用基础配置
    app_name: str = "ZK Admin"
    app_env: str = "development"
    debug: bool = True
    secret_key: str = "change-this-secret-key-in-production"

    # 管理员账号
    admin_username: str = "admin"
    admin_password: str = "admin"

    # 管理员路径配置（安全功能：隐藏真实管理路径）
    admin_path: str = "admin"  # 设置为自定义路径，如 "my-secret-admin"

    # 数据库配置
    database_url: str = "sqlite:///database/zk_admin.db"

    # clockin-worker 配置
    clockin_api_url: str = "https://zk-clockin-executor.xxx.workers.dev"
    clockin_api_token: str = "local-dev-token-Tian"

    # 打卡延迟配置
    api_request_delay: int = 500  # API 请求延迟（毫秒）：获取诗词/图片等外部 API 时的延迟
    clockin_type_delay: int = 2  # 打卡类型间延迟（秒）：首页/运动/每日打卡之间的等待时间

    # 批量打卡配置
    batch_size: int = 3  # 每批处理的用户数量
    batch_delay: int = 2000  # 批次间延迟（毫秒）
    parallel_tasks: int = 4  # 并行任务数量

    # 打卡重试配置
    clockin_retry_count: int = 3  # 打卡失败时的重试次数
    clockin_retry_delay: int = 3  # 重试延迟（秒）
    clockin_timeout: int = 60  # 请求超时时间（秒）
    clockin_rate_limit_delay: int = 10  # 频率限制时的额外延迟（秒）

    # 定时任务配置
    schedule_cron: str = "0 10 16 * * *"  # UTC 16:10 (北京时间 0:10)
    schedule_enabled: bool = True  # 定时任务开关
    schedule_timezone: str = "UTC"  # 定时任务时区
    schedule_retry_count: int = 3  # 定时任务失败用户重试次数
    schedule_retry_delay: int = 60  # 定时任务失败用户重试延迟（秒）

    # 数据保留天数
    retention_days: int = 7

    # 日志配置
    log_level: str = "INFO"
    log_dir: str = "logs"

    # CORS 配置
    cors_origins: List[str] = ["http://localhost:8000", "http://localhost:3000"]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

    @property
    def cors_origins_list(self) -> List[str]:
        """解析 CORS origins"""
        if isinstance(self.cors_origins, str):
            try:
                return json.loads(self.cors_origins)
            except:
                return [self.cors_origins]
        return self.cors_origins


# 全局配置实例
settings = Settings()
