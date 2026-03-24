"""
用户服务模块
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
from typing import List, Optional
from datetime import datetime
import re

from app.models.database import User
from app.models.schemas import UserCreate, UserUpdate


class UserService:
    """用户服务类"""

    @staticmethod
    async def get_users(db: AsyncSession) -> List[User]:
        """获取所有用户"""
        result = await db.execute(select(User).order_by(User.created_at.desc()))
        return result.scalars().all()

    @staticmethod
    async def get_user(db: AsyncSession, user_id: str) -> Optional[User]:
        """获取指定用户"""
        result = await db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_user_by_username(db: AsyncSession, username: str) -> Optional[User]:
        """根据用户名获取用户"""
        result = await db.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()

    @staticmethod
    async def create_user(db: AsyncSession, user_data: UserCreate) -> User:
        """创建新用户"""
        # 检查用户名是否已存在
        existing = await UserService.get_user_by_username(db, user_data.username)
        if existing:
            raise ValueError(f"用户名 '{user_data.username}' 已存在")

        # 创建用户对象
        user = User(
            username=user_data.username,
            password=user_data.password,
            nickname=user_data.nickname,
            enabled=user_data.enabled,
            # 运动打卡配置
            sports_comment_type=user_data.sports_comment_type,
            sports_custom_comment=user_data.sports_custom_comment,
            sports_comment_api=user_data.sports_comment_api,
            sports_image_type=user_data.sports_image_type,
            sports_image_provider=user_data.sports_image_provider,
            sports_image_category=user_data.sports_image_category,
            # 每日打卡配置
            daily_comment_type=user_data.daily_comment_type,
            custom_daily_comment=user_data.custom_daily_comment,
            daily_comment_api=user_data.daily_comment_api,
        )

        db.add(user)
        await db.commit()
        await db.refresh(user)

        return user

    @staticmethod
    async def update_user(db: AsyncSession, user_id: str, updates: UserUpdate) -> Optional[User]:
        """更新用户信息"""
        user = await UserService.get_user(db, user_id)
        if not user:
            return None

        # 如果更新用户名，检查是否冲突
        if updates.username and updates.username != user.username:
            existing = await UserService.get_user_by_username(db, updates.username)
            if existing:
                raise ValueError(f"用户名 '{updates.username}' 已存在")

        # 构建更新数据
        update_data = {}
        for field, value in updates.model_dump(exclude_unset=True).items():
            if value is not None:
                update_data[field] = value

        if update_data:
            await db.execute(
                update(User)
                .where(User.id == user_id)
                .values(**update_data)
            )
            await db.commit()
            await db.refresh(user)

        return user

    @staticmethod
    async def delete_user(db: AsyncSession, user_id: str) -> bool:
        """删除用户"""
        user = await UserService.get_user(db, user_id)
        if not user:
            return False

        await db.execute(delete(User).where(User.id == user_id))
        await db.commit()
        return True

    @staticmethod
    async def toggle_user(db: AsyncSession, user_id: str, enabled: bool) -> Optional[User]:
        """启用/禁用用户"""
        user = await UserService.get_user(db, user_id)
        if not user:
            return None

        user.enabled = enabled
        await db.commit()
        await db.refresh(user)

        return user

    @staticmethod
    async def get_enabled_users(db: AsyncSession) -> List[User]:
        """获取所有启用的用户"""
        result = await db.execute(
            select(User)
            .where(User.enabled == True)
            .order_by(User.created_at.desc())
        )
        return result.scalars().all()

    @staticmethod
    async def update_clockin_info(
        db: AsyncSession,
        user_id: str,
        success: bool,
        timestamp: datetime
    ) -> Optional[User]:
        """更新用户打卡信息"""
        user = await UserService.get_user(db, user_id)
        if not user:
            return None

        user.last_clockin = timestamp
        if success:
            # 确保 clockin_count 不为 None
            current_count = user.clockin_count if user.clockin_count is not None else 0
            user.clockin_count = current_count + 1

        await db.commit()
        await db.refresh(user)

        return user

    @staticmethod
    def validate_username(username: str) -> tuple[bool, Optional[str]]:
        """验证用户名"""
        if not username or len(username) < 3:
            return False, "用户名长度至少为 3 个字符"

        if len(username) > 50:
            return False, "用户名长度不能超过 50 个字符"

        if not re.match(r'^[\u4e00-\u9fa5a-zA-Z0-9_]+$', username):
            return False, "用户名只能包含中文、字母、数字和下划线"

        return True, None

    @staticmethod
    def validate_password(password: str) -> tuple[bool, Optional[str]]:
        """验证密码"""
        if not password or len(password) < 6:
            return False, "密码长度至少为 6 个字符"

        if len(password) > 100:
            return False, "密码长度不能超过 100 个字符"

        return True, None

    @staticmethod
    def escape_html(text: str) -> str:
        """转义 HTML 特殊字符"""
        if not text:
            return text

        replacements = {
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#039;'
        }

        for char, escaped in replacements.items():
            text = text.replace(char, escaped)

        return text
