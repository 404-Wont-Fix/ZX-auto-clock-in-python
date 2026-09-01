"""
Pydantic 模型定义（请求/响应验证）
"""
from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Optional, List, Dict, Any, Literal
from datetime import date as DateValue, datetime


# ==================== 认证相关 ====================

class LoginRequest(BaseModel):
    """登录请求"""
    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=1, max_length=100)


class LoginResponse(BaseModel):
    """登录响应"""
    success: bool
    token: Optional[str] = None
    username: Optional[str] = None
    message: Optional[str] = None


# ==================== 用户相关 ====================

class UserBase(BaseModel):
    """用户基础模型"""
    username: str = Field(..., min_length=3, max_length=50)
    nickname: Optional[str] = Field(None, max_length=50)
    enabled: bool = True

    # 运动打卡配置
    sports_comment_type: str = "default"
    sports_custom_comment: Optional[str] = Field(None, max_length=500)
    sports_comment_api: str = "poetry_all"
    sports_image_type: str = "default"
    sports_image_provider: str = "bing"
    sports_image_category: str = "random"

    # 每日打卡配置
    daily_comment_type: str = "default"
    custom_daily_comment: Optional[str] = Field(None, max_length=500)
    daily_comment_api: str = "poetry_all"

    @field_validator('username')
    @classmethod
    def validate_username(cls, v):
        """验证用户名"""
        import re
        if not re.match(r'^[\u4e00-\u9fa5a-zA-Z0-9_]+$', v):
            raise ValueError('用户名只能包含中文、字母、数字和下划线')
        return v


class UserCreate(UserBase):
    """创建用户请求"""
    password: str = Field(..., min_length=6, max_length=100)


class UserUpdate(BaseModel):
    """更新用户请求"""
    username: Optional[str] = Field(None, min_length=3, max_length=50)
    password: Optional[str] = Field(None, max_length=100)
    nickname: Optional[str] = Field(None, max_length=50)
    enabled: Optional[bool] = None

    # 运动打卡配置
    sports_comment_type: Optional[str] = None
    sports_custom_comment: Optional[str] = Field(None, max_length=500)
    sports_comment_api: Optional[str] = None
    sports_image_type: Optional[str] = None
    sports_image_provider: Optional[str] = None
    sports_image_category: Optional[str] = None

    # 每日打卡配置
    daily_comment_type: Optional[str] = None
    custom_daily_comment: Optional[str] = Field(None, max_length=500)
    daily_comment_api: Optional[str] = None

    @field_validator('username')
    @classmethod
    def validate_username(cls, v):
        """更新时同样校验用户名字符集（与 UserBase 保持一致）"""
        if v is None:
            return v
        import re
        if not re.match(r'^[一-龥a-zA-Z0-9_]+$', v):
            raise ValueError('用户名只能包含中文、字母、数字和下划线')
        return v

    @field_validator('password', mode='before')
    @classmethod
    def normalize_optional_password(cls, value):
        if isinstance(value, str) and not value.strip():
            return None
        if value is not None and len(value) < 6:
            raise ValueError('密码长度至少为 6 个字符')
        return value


class UserResponse(UserBase):
    """用户响应（不含密码——密码仅供服务端调用 worker 时使用，不回传客户端）"""
    id: str
    created_at: Optional[str] = None
    last_clockin: Optional[str] = None
    clockin_count: int = 0
    password_configured: bool

    model_config = ConfigDict(from_attributes=True)


class UserListResponse(BaseModel):
    """用户列表响应"""
    success: bool
    data: List[UserResponse]


class UserToggleRequest(BaseModel):
    """启用/禁用用户请求"""
    enabled: bool


# ==================== 打卡相关 ====================

class ClockinOptions(BaseModel):
    """打卡选项"""
    sports_comment: Optional[str] = None
    daily_comment: Optional[str] = None
    sports_image_url: Optional[str] = None


class ClockinRequest(BaseModel):
    """打卡请求"""
    username: str
    password: str
    clockin_type: str = "all"
    options: Optional[ClockinOptions] = None


class ClockinResultDetails(BaseModel):
    """打卡结果详情"""
    home: Optional[Dict[str, Any]] = None
    sports: Optional[Dict[str, Any]] = None
    daily: Optional[Dict[str, Any]] = None


class ClockinResultResponse(BaseModel):
    """打卡记录响应"""
    id: str
    user_id: Optional[str] = None
    username: str
    nickname: Optional[str] = None
    clockin_count: Optional[int] = None
    date: str
    timestamp: Optional[str] = None
    success: bool
    clockin_type: str
    details: Optional[Dict[str, Any]] = None
    details_json: Optional[str] = None
    sports_comment: Optional[str] = None
    sports_comment_source: Optional[str] = None
    daily_comment: Optional[str] = None
    daily_comment_source: Optional[str] = None
    sports_comment_api: Optional[str] = None
    daily_comment_api: Optional[str] = None
    sports_image_type: Optional[str] = None
    sports_image_provider: Optional[str] = None
    sports_image_category: Optional[str] = None
    duration_ms: Optional[int] = None
    triggered_by: Optional[str] = None
    error: Optional[str] = None
    created_at: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ClockinTriggerResponse(BaseModel):
    """触发打卡响应"""
    success: bool
    data: Dict[str, Any]


class ClockinTaskCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')

    scope: Literal['all', 'failed', 'users']
    date: Optional[DateValue] = None
    user_ids: List[str] = Field(default_factory=list, max_length=50)


class TaskProgress(BaseModel):
    """任务进度"""
    total: int
    current: int
    success: int
    failure: int
    percent: int


class TaskResponse(BaseModel):
    """任务响应"""
    id: str
    task_type: str
    status: str
    progress: TaskProgress
    result: Optional[str] = None
    error: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    completed_at: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ClockinResultsResponse(BaseModel):
    """打卡记录列表响应"""
    success: bool
    data: Dict[str, Any]


class ClockinStatsResponse(BaseModel):
    """统计数据响应"""
    success: bool
    data: Dict[str, Any]


# ==================== 配置相关 ====================

class ConfigUpdateRequest(BaseModel):
    """配置更新请求"""
    clockin_api_url: Optional[str] = None
    clockin_api_token: Optional[str] = None
    default_worker_api_id: Optional[str] = None
    api_request_delay: Optional[int] = Field(None, ge=0)
    clockin_type_delay: Optional[int] = Field(None, ge=0)
    clockin_retry_count: Optional[int] = Field(None, ge=0)
    clockin_retry_delay: Optional[int] = Field(None, ge=0)
    clockin_timeout: Optional[int] = Field(None, ge=1)
    clockin_rate_limit_delay: Optional[int] = Field(None, ge=0)
    schedule_cron: Optional[str] = None
    schedule_enabled: Optional[bool] = None
    schedule_timezone: Optional[str] = None
    schedule_retry_count: Optional[int] = Field(None, ge=0)
    schedule_retry_delay: Optional[int] = Field(None, ge=0)
    # 必须 >=1：retention_days=0 会让清理任务把今天之前的记录全删，叠加时区偏差可能误删当天
    retention_days: Optional[int] = Field(None, ge=1)

    @field_validator('clockin_api_token', mode='before')
    @classmethod
    def normalize_optional_clockin_token(cls, value):
        if isinstance(value, str) and not value.strip():
            return None
        return value


class ConfigResponse(BaseModel):
    """配置响应"""
    success: bool
    data: Dict[str, Any]


# ==================== Worker API 相关 ====================

class WorkerApiCreate(BaseModel):
    """创建 Worker API 请求"""
    name: str = Field(..., min_length=1, max_length=50)
    url: str = Field(..., min_length=1)
    token: str = Field(..., min_length=1)
    note: Optional[str] = Field(None, max_length=200)


class WorkerApiUpdate(BaseModel):
    """更新 Worker API 请求"""
    name: Optional[str] = Field(None, min_length=1, max_length=50)
    url: Optional[str] = Field(None, min_length=1)
    token: Optional[str] = Field(None, max_length=500)
    enabled: Optional[bool] = None
    available: Optional[bool] = None
    note: Optional[str] = Field(None, max_length=200)

    @field_validator('token', mode='before')
    @classmethod
    def normalize_optional_token(cls, value):
        if isinstance(value, str) and not value.strip():
            return None
        return value


class WorkerApiResponse(BaseModel):
    """Worker API 响应"""
    id: str
    name: str
    url: str
    token_configured: bool
    token_masked: str
    enabled: bool
    available: bool
    last_check: Optional[str] = None
    last_success: Optional[str] = None
    last_failure: Optional[str] = None
    failure_count: int
    total_requests: int
    total_success: int
    total_failure: int
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    note: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class WorkerApiListResponse(BaseModel):
    """Worker API 列表响应"""
    success: bool
    data: List[WorkerApiResponse]


class WorkerApiTestResponse(BaseModel):
    """Worker API 测试响应"""
    success: bool
    message: str
    latency_ms: Optional[int] = None


# ==================== 内容源相关 ====================

class ContentSourceCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')

    key: str = Field(..., min_length=2, max_length=64)
    name: str = Field(..., min_length=1, max_length=80)
    source_type: Literal['text', 'image']
    enabled: bool = False
    priority: int = Field(100, ge=0, le=10000)
    url_template: str = Field(..., min_length=9, max_length=2048)
    query_params: Dict[str, Any] = Field(default_factory=dict)
    parse_mode: Literal['json_text', 'plain_text', 'json_image', 'redirect_image']
    value_path: Optional[str] = Field(None, max_length=200)
    attribution_path: Optional[str] = Field(None, max_length=200)
    categories: List[str] = Field(default_factory=list, max_length=100)
    timeout_seconds: int = Field(10, ge=2, le=30)


class ContentSourceUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')

    name: Optional[str] = Field(None, min_length=1, max_length=80)
    source_type: Optional[Literal['text', 'image']] = None
    enabled: Optional[bool] = None
    priority: Optional[int] = Field(None, ge=0, le=10000)
    url_template: Optional[str] = Field(None, min_length=9, max_length=2048)
    query_params: Optional[Dict[str, Any]] = None
    parse_mode: Optional[Literal['json_text', 'plain_text', 'json_image', 'redirect_image']] = None
    value_path: Optional[str] = Field(None, max_length=200)
    attribution_path: Optional[str] = Field(None, max_length=200)
    categories: Optional[List[str]] = Field(None, max_length=100)
    timeout_seconds: Optional[int] = Field(None, ge=2, le=30)


class ContentSourcePriorityItem(BaseModel):
    model_config = ConfigDict(extra='forbid')

    id: str
    priority: int = Field(..., ge=0, le=10000)


class ContentSourcePriorityUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')

    items: List[ContentSourcePriorityItem] = Field(..., min_length=1, max_length=200)


# ==================== 维护相关 ====================

class CleanupRequest(BaseModel):
    """清理请求"""
    days: int = Field(7, ge=1, le=3650)


class CleanupResponse(BaseModel):
    """清理响应"""
    success: bool
    message: str
    deleted: int
    errors: int
    total: int
    checked: int
    cutoff_date: Optional[str] = None
    today: Optional[str] = None
    days_to_keep: Optional[int] = None


class HealthResponse(BaseModel):
    """健康检查响应"""
    status: str
    timestamp: str
    service: str
    database: Optional[str] = None


# ==================== 活动任务相关 ====================

class ActiveTaskInfo(BaseModel):
    """活动任务信息"""
    user_id: str
    username: str
    nickname: str
    worker_api_id: Optional[str] = None
    worker_api_name: Optional[str] = None
    started_at: str
    elapsed_seconds: int
    status: str


class ActiveTasksResponse(BaseModel):
    """活动任务列表响应"""
    success: bool
    data: Dict[str, Any]


# ==================== 通用响应 ====================

class ErrorResponse(BaseModel):
    """错误响应"""
    success: bool = False
    error: str
    detail: Optional[Dict[str, Any]] = None


class SuccessResponse(BaseModel):
    """成功响应"""
    success: bool = True
    message: Optional[str] = None
    data: Optional[Any] = None
