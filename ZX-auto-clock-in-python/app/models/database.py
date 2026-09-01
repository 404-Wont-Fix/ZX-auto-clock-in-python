"""
SQLAlchemy 数据库模型定义
"""
from sqlalchemy import Column, String, Boolean, Integer, Text, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.core.database import Base
import uuid
import json
import hashlib


def generate_uuid():
    """生成 UUID"""
    return str(uuid.uuid4())


def utc_now():
    """返回与现有 SQLite DateTime 字段兼容的 UTC naive 时间。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def mask_secret(value):
    """短值完全隐藏，长值只保留少量尾字符。"""
    if not value:
        return ''
    value = str(value)
    if len(value) <= 8:
        return "••••••••"
    return f"••••{value[-4:]}"


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
    created_at = Column(DateTime, default=utc_now)
    last_clockin = Column(DateTime)
    clockin_count = Column(Integer, default=0)

    __table_args__ = (
        Index('idx_users_enabled', 'enabled'),
        Index('idx_users_username', 'username'),
    )

    def to_dict(self):
        """转换为字典（不含密码——密码仅供服务端调用 worker 时读取，不随接口返回）"""
        return {
            'id': self.id,
            'username': self.username,
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
            'password_configured': bool(self.password),
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

    # API 使用信息
    sports_comment_api = Column(String)  # 使用的文字API (poetry_all等)
    daily_comment_api = Column(String)  # 使用的每日打卡文字API
    sports_image_type = Column(String)  # 图片类型 (default/api)
    sports_image_provider = Column(String)  # 图片提供商 (bing等)
    sports_image_category = Column(String)  # 图片分类

    # 执行信息
    duration_ms = Column(Integer)
    triggered_by = Column(String)  # manual/scheduled
    error = Column(String)

    created_at = Column(DateTime, default=utc_now)

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
            'sports_comment_api': self.sports_comment_api,
            'daily_comment_api': self.daily_comment_api,
            'sports_image_type': self.sports_image_type,
            'sports_image_provider': self.sports_image_provider,
            'sports_image_category': self.sports_image_category,
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

    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

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
    status = Column(String, nullable=False, index=True)  # pending/running/completed/failed/interrupted
    scope = Column(String, nullable=False, default='all', index=True)  # all/failed/users
    target_date = Column(String, nullable=False, index=True)
    user_ids_json = Column(Text, default='[]', nullable=False)
    triggered_by = Column(String, default='manual', nullable=False)

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
    created_at = Column(DateTime, default=utc_now, index=True)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)
    started_at = Column(DateTime)
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
        elif self.status == 'completed':
            progress_percent = 100

        return {
            'id': self.id,
            'task_type': self.task_type,
            'status': self.status,
            'scope': self.scope,
            'date': self.target_date,
            'user_ids': self.user_ids,
            'triggered_by': self.triggered_by,
            'progress': {
                'total': self.progress_total,
                'current': self.progress_current,
                'success': self.progress_success,
                'failure': self.progress_failure,
                'percent': progress_percent,
            },
            'result': self.result,
            'error': self.error,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
        }

    @property
    def user_ids(self):
        try:
            value = json.loads(self.user_ids_json or '[]')
            return value if isinstance(value, list) else []
        except (TypeError, json.JSONDecodeError):
            return []

    @property
    def result(self):
        if not self.result_json:
            return None
        try:
            return json.loads(self.result_json)
        except (TypeError, json.JSONDecodeError):
            return None


class Config(Base):
    """配置表"""
    __tablename__ = 'configs'

    key = Column(String, primary_key=True)
    value = Column(String, nullable=False)
    description = Column(String)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

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
    created_at = Column(DateTime, default=utc_now)
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

    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)
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
            'token_configured': bool(self.token),
            'token_masked': mask_secret(self.token),
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


class ContentSource(Base):
    """受控的公网文字或图片内容源。"""
    __tablename__ = 'content_sources'

    id = Column(String, primary_key=True, default=generate_uuid)
    key = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    source_type = Column(String, nullable=False, index=True)  # text/image
    enabled = Column(Boolean, default=False, nullable=False, index=True)
    archived = Column(Boolean, default=False, nullable=False, index=True)
    priority = Column(Integer, default=100, nullable=False, index=True)

    url_template = Column(String, nullable=False)
    query_params_json = Column(Text, default='{}', nullable=False)
    parse_mode = Column(String, nullable=False)
    value_path = Column(String)
    attribution_path = Column(String)
    categories_json = Column(Text, default='[]', nullable=False)
    timeout_seconds = Column(Integer, default=10, nullable=False)
    verified_config_hash = Column(String)

    last_checked_at = Column(DateTime)
    last_success_at = Column(DateTime)
    last_failure_at = Column(DateTime)
    latency_ms = Column(Integer)
    consecutive_failures = Column(Integer, default=0, nullable=False)
    last_error = Column(Text)

    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    __table_args__ = (
        Index('idx_content_source_type_priority', 'source_type', 'priority'),
        Index('idx_content_source_state', 'enabled', 'archived'),
    )

    @property
    def query_params(self):
        try:
            value = json.loads(self.query_params_json or '{}')
            return value if isinstance(value, dict) else {}
        except (TypeError, json.JSONDecodeError):
            return {}

    @property
    def categories(self):
        try:
            value = json.loads(self.categories_json or '[]')
            return value if isinstance(value, list) else []
        except (TypeError, json.JSONDecodeError):
            return []

    @property
    def config_fingerprint(self):
        payload = {
            'source_type': self.source_type,
            'url_template': self.url_template,
            'query_params': self.query_params,
            'parse_mode': self.parse_mode,
            'value_path': self.value_path,
            'attribution_path': self.attribution_path,
            'categories': self.categories,
            'timeout_seconds': self.timeout_seconds,
        }
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(serialized.encode('utf-8')).hexdigest()

    @property
    def config_verified(self):
        return bool(
            self.verified_config_hash
            and self.verified_config_hash == self.config_fingerprint
        )

    @property
    def health_status(self):
        if self.archived:
            return 'archived'
        if not self.enabled:
            return 'disabled'
        if (self.consecutive_failures or 0) >= 3:
            return 'unavailable'
        if (self.consecutive_failures or 0) > 0:
            return 'degraded'
        if self.last_success_at:
            return 'healthy'
        return 'unknown'

    def to_dict(self):
        return {
            'id': self.id,
            'key': self.key,
            'name': self.name,
            'source_type': self.source_type,
            'enabled': self.enabled,
            'archived': self.archived,
            'priority': self.priority,
            'url_template': self.url_template,
            'query_params': self.query_params,
            'parse_mode': self.parse_mode,
            'value_path': self.value_path,
            'attribution_path': self.attribution_path,
            'categories': self.categories,
            'timeout_seconds': self.timeout_seconds,
            'config_verified': self.config_verified,
            'health_status': self.health_status,
            'last_checked_at': self.last_checked_at.isoformat() if self.last_checked_at else None,
            'last_success_at': self.last_success_at.isoformat() if self.last_success_at else None,
            'last_failure_at': self.last_failure_at.isoformat() if self.last_failure_at else None,
            'latency_ms': self.latency_ms,
            'consecutive_failures': self.consecutive_failures or 0,
            'last_error': self.last_error,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
