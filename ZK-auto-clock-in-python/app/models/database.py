"""
SQLAlchemy 数据库模型定义
"""
from sqlalchemy import Column, String, Boolean, Integer, Text, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from datetime import datetime
from app.core.database import Base
import uuid
import json


def generate_uuid():
    """生成 UUID"""
    return str(uuid.uuid4())


class User(Base):
    """用户表"""
    __tablename__ = 'users'

    id = Column(String, primary_key=True, default=generate_uuid)
    username = Column(String, unique=True, nullable=False, index=True)
    password = Column(String, nullable=False)
    nickname = Column(String)
    enabled = Column(Boolean, default=True, index=True)

    # 运动打卡配置
    sports_comment_type = Column(String, default='default')  # default/custom/api
    sports_custom_comment = Column(String)
    sports_comment_api = Column(String, default='poetry_all')
    sports_image_type = Column(String, default='default')  # default/api
    sports_image_provider = Column(String, default='bing')
    sports_image_category = Column(String, default='random')

    # 每日打卡配置
    daily_comment_type = Column(String, default='default')  # default/custom/api
    custom_daily_comment = Column(String)
    daily_comment_api = Column(String, default='poetry_all')

    # 统计信息
    created_at = Column(DateTime, default=datetime.utcnow)
    last_clockin = Column(DateTime)
    clockin_count = Column(Integer, default=0)

    __table_args__ = (
        Index('idx_users_enabled', 'enabled'),
        Index('idx_users_username', 'username'),
    )

    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'username': self.username,
            'password': self.password,  # 添加密码字段
            'nickname': self.nickname or '',
            'enabled': self.enabled,
            'sports_comment_type': self.sports_comment_type,
            'sports_custom_comment': self.sports_custom_comment or '',
            'sports_comment_api': self.sports_comment_api,
            'sports_image_type': self.sports_image_type,
            'sports_image_provider': self.sports_image_provider,
            'sports_image_category': self.sports_image_category,
            'daily_comment_type': self.daily_comment_type,
            'custom_daily_comment': self.custom_daily_comment or '',
            'daily_comment_api': self.daily_comment_api,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_clockin': self.last_clockin.isoformat() if self.last_clockin else None,
            'clockin_count': self.clockin_count,
        }


class ClockinResult(Base):
    """打卡记录表"""
    __tablename__ = 'clockin_results'

    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, index=True)
    username = Column(String, nullable=False, index=True)
    nickname = Column(String)
    clockin_count = Column(Integer)

    date = Column(String, nullable=False, index=True)  # YYYY-MM-DD
    timestamp = Column(DateTime, nullable=False)

    success = Column(Boolean, nullable=False, index=True)
    clockin_type = Column(String, default='all')  # all/home/sports/daily

    # 详细结果 (JSON)
    details_json = Column(Text)

    # 备注内容
    sports_comment = Column(String)
    sports_comment_source = Column(String)  # default/custom/api
    daily_comment = Column(String)
    daily_comment_source = Column(String)

    # 执行信息
    duration_ms = Column(Integer)
    triggered_by = Column(String)  # manual/scheduled
    error = Column(String)

    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('idx_clockin_date', 'date'),
        Index('idx_clockin_user', 'user_id'),
        Index('idx_clockin_username', 'username'),
        Index('idx_clockin_success', 'success'),
    )

    def to_dict(self):
        """转换为字典"""
        # 解析 details_json JSON 字符串为字典
        details = None
        if self.details_json:
            try:
                details = json.loads(self.details_json)
            except (json.JSONDecodeError, TypeError):
                details = None

        return {
            'id': self.id,
            'user_id': self.user_id,
            'username': self.username,
            'nickname': self.nickname or '',
            'clockin_count': self.clockin_count,
            'date': self.date,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'success': self.success,
            'clockin_type': self.clockin_type,
            'details': details,
            'details_json': self.details_json,  # 保留原始 JSON 字符串
            'sports_comment': self.sports_comment,
            'sports_comment_source': self.sports_comment_source,
            'daily_comment': self.daily_comment,
            'daily_comment_source': self.daily_comment_source,
            'duration_ms': self.duration_ms,
            'triggered_by': self.triggered_by,
            'error': self.error,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class DailySummary(Base):
    """每日汇总表"""
    __tablename__ = 'daily_summaries'

    date = Column(String, primary_key=True)  # YYYY-MM-DD

    total_users = Column(Integer, default=0)
    success_count = Column(Integer, default=0)
    failure_count = Column(Integer, default=0)

    home_success = Column(Integer, default=0)
    sports_success = Column(Integer, default=0)
    daily_success = Column(Integer, default=0)

    start_time = Column(DateTime)
    end_time = Column(DateTime)

    failed_users_json = Column(Text)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('idx_summaries_date', 'date'),
    )

    def to_dict(self):
        """转换为字典"""
        return {
            'date': self.date,
            'total_users': self.total_users,
            'success_count': self.success_count,
            'failure_count': self.failure_count,
            'home_success': self.home_success,
            'sports_success': self.sports_success,
            'daily_success': self.daily_success,
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'failed_users': self.failed_users_json,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class Task(Base):
    """任务表"""
    __tablename__ = 'tasks'

    id = Column(String, primary_key=True, default=generate_uuid)
    task_type = Column(String, nullable=False, index=True)  # clockin/clockin_sub
    status = Column(String, nullable=False, index=True)  # pending/running/completed/failed

    # 进度信息
    progress_total = Column(Integer, default=0)
    progress_current = Column(Integer, default=0)
    progress_success = Column(Integer, default=0)
    progress_failure = Column(Integer, default=0)

    # 任务结果 (JSON)
    result_json = Column(Text)

    # 错误信息
    error = Column(String)

    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime)

    __table_args__ = (
        Index('idx_tasks_status', 'status'),
        Index('idx_tasks_type', 'task_type'),
        Index('idx_tasks_created', 'created_at'),
    )

    def to_dict(self):
        """转换为字典"""
        progress_percent = 0
        if self.progress_total > 0:
            progress_percent = int((self.progress_current / self.progress_total) * 100)

        return {
            'id': self.id,
            'task_type': self.task_type,
            'status': self.status,
            'progress': {
                'total': self.progress_total,
                'current': self.progress_current,
                'success': self.progress_success,
                'failure': self.progress_failure,
                'percent': progress_percent,
            },
            'result': self.result_json,
            'error': self.error,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
        }


class Config(Base):
    """配置表"""
    __tablename__ = 'configs'

    key = Column(String, primary_key=True)
    value = Column(String, nullable=False)
    description = Column(String)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        """转换为字典"""
        return {
            'key': self.key,
            'value': self.value,
            'description': self.description,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class Session(Base):
    """会话表"""
    __tablename__ = 'sessions'

    token = Column(String, primary_key=True)
    username = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False, index=True)

    __table_args__ = (
        Index('idx_sessions_expires', 'expires_at'),
    )

    def to_dict(self):
        """转换为字典"""
        return {
            'token': self.token,
            'username': self.username,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
        }


class WorkerApi(Base):
    """Worker API 配置表"""
    __tablename__ = 'worker_apis'

    id = Column(String, primary_key=True, default=generate_uuid)
    name = Column(String, nullable=False)  # API 名称
    url = Column(String, nullable=False, unique=True)  # API 地址
    token = Column(String, nullable=False)  # API Token

    # 状态管理
    enabled = Column(Boolean, default=True, index=True)  # 是否启用
    available = Column(Boolean, default=True, index=True)  # 是否可用

    # 统计信息
    last_check = Column(DateTime)  # 最后检查时间
    last_success = Column(DateTime)  # 最后成功时间
    last_failure = Column(DateTime)  # 最后失败时间
    failure_count = Column(Integer, default=0)  # 连续失败次数
    total_requests = Column(Integer, default=0)  # 总请求次数
    total_success = Column(Integer, default=0)  # 总成功次数
    total_failure = Column(Integer, default=0)  # 总失败次数

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    note = Column(String)  # 备注信息

    __table_args__ = (
        Index('idx_worker_enabled', 'enabled'),
        Index('idx_worker_available', 'available'),
    )

    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'name': self.name,
            'url': self.url,
            'token': self.token,
            'enabled': self.enabled,
            'available': self.available,
            'last_check': self.last_check.isoformat() if self.last_check else None,
            'last_success': self.last_success.isoformat() if self.last_success else None,
            'last_failure': self.last_failure.isoformat() if self.last_failure else None,
            'failure_count': self.failure_count,
            'total_requests': self.total_requests,
            'total_success': self.total_success,
            'total_failure': self.total_failure,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'note': self.note,
        }
