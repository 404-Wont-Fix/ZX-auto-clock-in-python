"""
Pydantic 模型定义（请求/响应验证）
"""
from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime


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

    @validator('username')
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
    password: Optional[str] = Field(None, min_length=6, max_length=100)
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


class UserResponse(UserBase):
    """用户响应"""
    id: str
    password: str
    created_at: Optional[str] = None
    last_clockin: Optional[str] = None
    clockin_count: int = 0

    class Config:
        from_attributes = True


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
    duration_ms: Optional[int] = None
    triggered_by: Optional[str] = None
    error: Optional[str] = None
    created_at: Optional[str] = None

    class Config:
        from_attributes = True


class ClockinTriggerResponse(BaseModel):
    """触发打卡响应"""
    success: bool
    data: Dict[str, Any]


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

    class Config:
        from_attributes = True


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
    batch_size: Optional[int] = None
    batch_delay: Optional[int] = None
    parallel_tasks: Optional[int] = None
    schedule_cron: Optional[str] = None
    retention_days: Optional[int] = None


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
    token: Optional[str] = Field(None, min_length=1)
    enabled: Optional[bool] = None
    available: Optional[bool] = None
    note: Optional[str] = Field(None, max_length=200)


class WorkerApiResponse(BaseModel):
    """Worker API 响应"""
    id: str
    name: str
    url: str
    token: str
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

    class Config:
        from_attributes = True


class WorkerApiListResponse(BaseModel):
    """Worker API 列表响应"""
    success: bool
    data: List[WorkerApiResponse]


class WorkerApiTestResponse(BaseModel):
    """Worker API 测试响应"""
    success: bool
    message: str
    latency_ms: Optional[int] = None


# ==================== 维护相关 ====================

class CleanupRequest(BaseModel):
    """清理请求"""
    days: Optional[int] = 7


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
