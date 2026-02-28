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

    # 数据库配置
    database_url: str = "sqlite:///database/zk_admin.db"

    # clockin-worker 配置
    clockin_api_url: str = "https://zk-clockin-executor.xxx.workers.dev"
    clockin_api_token: str = "local-dev-token-Tian"

    # 批处理配置
    batch_size: int = 3
    batch_delay: int = 2000  # 毫秒
    parallel_tasks: int = 4

    # 定时任务配置
    schedule_cron: str = "0 10 16 * * *"  # UTC 16:10 (北京时间 0:10)

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
