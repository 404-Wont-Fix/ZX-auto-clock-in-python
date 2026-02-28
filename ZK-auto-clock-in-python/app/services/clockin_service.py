"""
打卡服务模块
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, func
from typing import List, Optional, Dict
from datetime import datetime, timedelta, timezone
import json
import asyncio
import httpx
import logging

from app.models.database import User, ClockinResult, DailySummary, WorkerApi
from app.services.poetry_service import PoetryService
from app.services.user_service import UserService
from app.services.worker_api_service import WorkerApiService
from app.services.active_task_service import ActiveTaskService
from app.config import settings

logger = logging.getLogger(__name__)


class ClockinService:
    """打卡服务类"""

    @staticmethod
    async def call_clockin_api(
        db: AsyncSession,
        user: User,
        triggered_by: str = 'manual',
        retries: int = 1,
        worker_api: Optional[WorkerApi] = None
    ) -> Dict:
        """
        调用 clockin-worker API（支持多 API 负载均衡）

        Args:
            db: 数据库会话
            user: 用户对象
            triggered_by: 触发方式 (manual/scheduled)
            retries: 重试次数
            worker_api: 指定的 Worker API（可选）

        Returns:
            打卡结果字典
        """
        # 获取 Worker API（如果没有指定，则自动选择）
        if worker_api is None:
            worker_api = await WorkerApiService.get_next_api(db)

        # 如果没有可用的 Worker API，使用后备方案
        use_fallback = False
        if worker_api is None:
            logger.warning("没有可用的 Worker API，使用配置文件中的后备 API")
            api_url = settings.clockin_api_url
            api_token = settings.clockin_api_token
            use_fallback = True
            logger.info(f"[用户 {user.username}] 使用后备 API: {api_url}")
        else:
            api_url = worker_api.url
            api_token = worker_api.token
            # 记录请求统计
            await WorkerApiService.increment_requests(db, worker_api.id)
            logger.info(f"[用户 {user.username}] 使用 Worker API: {worker_api.name} ({api_url})")

        max_retries = retries
        last_worker_api_id = worker_api.id if worker_api else None
        task_success = False

        # 记录活动任务
        await ActiveTaskService.start_task(
            user_id=user.id,
            username=user.username,
            nickname=user.nickname or user.username,
            worker_api_id=worker_api.id if worker_api else None,
            worker_api_name=worker_api.name if worker_api else None
        )

        try:
            for attempt in range(max_retries + 1):
                try:
                    if attempt > 0:
                        logger.info(f"重试第 {attempt} 次: {user.username}")

                    # 获取备注内容
                    daily_comment = await PoetryService.get_daily_comment(user)
                    sports_comment = await PoetryService.get_sports_comment(user)

                    # 获取图片
                    image_data = await PoetryService.get_sports_image(user)

                    # 构建请求
                    url = f"{api_url}/clockin"
                    request_body = {
                        "username": user.username,
                        "password": user.password,
                        "clockin_type": "all",
                        "options": {
                            "sports_comment": sports_comment,
                            "daily_comment": daily_comment
                        }
                    }

                    # 如果有图片 URL，添加到请求
                    if image_data and image_data.get('url'):
                        request_body['options']['sports_image_url'] = image_data['url']

                    # 发送请求
                    start_time = datetime.now()
                    async with httpx.AsyncClient(timeout=60.0) as client:
                        response = await client.post(
                            url,
                            json=request_body,
                            headers={
                                "Content-Type": "application/json",
                                "Authorization": f"Bearer {api_token}"
                            }
                        )

                    duration = (datetime.now() - start_time).total_seconds() * 1000

                    if not response.is_success:
                        logger.warning(f"API 请求失败: {response.status_code}")

                        # 标记失败（仅在非后备模式且非重试时）
                        if not use_fallback and attempt == max_retries:
                            await WorkerApiService.mark_failure(db, last_worker_api_id)
                            # 尝试切换到另一个 API
                            next_api = await WorkerApiService.get_next_api(db)
                            if next_api and next_api.id != last_worker_api_id:
                                logger.info(f"切换到另一个 Worker API: {next_api.name}")
                                # 完成当前任务追踪（失败）
                                await ActiveTaskService.complete_task(user.id, success=False)
                                # 递归调用（会创建新的任务追踪）
                                return await ClockinService.call_clockin_api(
                                    db, user, triggered_by, 0, next_api
                                )

                        # 5xx 错误重试
                        if response.status_code >= 500 or response.status_code == 429:
                            if attempt < max_retries:
                                await asyncio.sleep(2)
                                continue

                        raise Exception(f"API 请求失败: {response.status_code}")

                    result = response.json()
                    result['duration'] = duration
                    result['triggered_by'] = triggered_by
                    result['sports_comment'] = sports_comment
                    result['sports_comment_source'] = user.sports_comment_type
                    result['daily_comment'] = daily_comment
                    result['daily_comment_source'] = user.daily_comment_type

                    # 标记成功
                    if not use_fallback and last_worker_api_id:
                        await WorkerApiService.mark_success(db, last_worker_api_id)

                    task_success = True
                    return result

                except Exception as e:
                    logger.warning(f"第 {attempt + 1} 次尝试失败: {e}")

                    # 标记失败并尝试切换（仅在最后一次失败时）
                    if attempt == max_retries:
                        if not use_fallback and last_worker_api_id:
                            await WorkerApiService.mark_failure(db, last_worker_api_id)
                            # 尝试切换到另一个 API
                            next_api = await WorkerApiService.get_next_api(db)
                            if next_api and next_api.id != last_worker_api_id:
                                logger.info(f"切换到另一个 Worker API: {next_api.name}")
                                # 完成当前任务追踪（失败）
                                await ActiveTaskService.complete_task(user.id, success=False)
                                # 递归调用（会创建新的任务追踪）
                                return await ClockinService.call_clockin_api(
                                    db, user, triggered_by, 0, next_api
                                )

                        # 所有 API 都不可用，返回错误
                        return {
                            'success': False,
                            'error': str(e),
                            'triggered_by': triggered_by,
                            'timestamp': datetime.utcnow().isoformat()
                        }

                    if attempt < max_retries:
                        await asyncio.sleep(2)
                        continue
        finally:
            # 完成任务追踪（仅在非递归调用时）
            # 递归调用会自己管理任务追踪
            if retries == 0 or task_success:
                await ActiveTaskService.complete_task(
                    user_id=user.id,
                    success=task_success
                )

    @staticmethod
    async def save_clockin_result(
        db: AsyncSession,
        user: User,
        result: Dict
    ) -> ClockinResult:
        """保存打卡结果"""
        date = datetime.utcnow().strftime('%Y-%m-%d')
        timestamp = result.get('timestamp', datetime.utcnow().isoformat())

        # 构建详情 JSON
        details = result.get('results', {})

        clockin_result = ClockinResult(
            user_id=user.id,
            username=user.username,
            nickname=user.nickname,
            clockin_count=user.clockin_count,
            date=date,
            timestamp=datetime.fromisoformat(timestamp) if isinstance(timestamp, str) else timestamp,
            success=result.get('success', False),
            clockin_type='all',
            details_json=json.dumps(details, ensure_ascii=False),
            sports_comment=result.get('sports_comment'),
            sports_comment_source=result.get('sports_comment_source'),
            daily_comment=result.get('daily_comment'),
            daily_comment_source=result.get('daily_comment_source'),
            duration_ms=result.get('duration'),
            triggered_by=result.get('triggered_by'),
            error=result.get('error')
        )

        db.add(clockin_result)
        await db.commit()

        # 更新每日汇总
        await ClockinService._update_daily_summary(db, date, clockin_result)

        return clockin_result

    @staticmethod
    async def _update_daily_summary(
        db: AsyncSession,
        date: str,
        result: ClockinResult
    ):
        """更新每日汇总"""
        summary = await db.execute(select(DailySummary).where(DailySummary.date == date))
        summary = summary.scalar_one_or_none()

        if not summary:
            # 创建新的汇总对象，确保所有数字字段初始化为 0
            summary = DailySummary(
                date=date,
                total_users=0,
                success_count=0,
                failure_count=0,
                home_success=0,
                sports_success=0,
                daily_success=0
            )
            db.add(summary)
            await db.flush()  # 确保对象被持久化

        summary.total_users += 1

        if result.success:
            summary.success_count += 1
        else:
            summary.failure_count += 1
            # 添加失败用户
            failed_users = []
            if summary.failed_users_json:
                failed_users = json.loads(summary.failed_users_json)
            failed_users.append({
                'username': result.username,
                'error': result.error or '未知错误'
            })
            summary.failed_users_json = json.dumps(failed_users, ensure_ascii=False)

        # 更新分类成功数
        if result.details_json:
            details = json.loads(result.details_json)
            if details.get('home', {}).get('success'):
                summary.home_success += 1
            if details.get('sports', {}).get('success'):
                summary.sports_success += 1
            if details.get('daily', {}).get('success'):
                summary.daily_success += 1

        summary.end_time = datetime.utcnow()
        if not summary.start_time:
            summary.start_time = result.timestamp or datetime.utcnow()

        await db.commit()

    @staticmethod
    async def trigger_all_users(
        db: AsyncSession
    ) -> Dict:
        """触发所有用户打卡（并行动态分配）"""
        # 获取启用的用户
        users = await UserService.get_enabled_users(db)

        if not users:
            return {
                'status': 'completed',
                'message': '没有需要打卡的用户',
                'total': 0,
                'success': 0,
                'failure': 0
            }

        # 获取可用的 Worker API 数量
        available_apis = await WorkerApiService.get_available_apis(db)
        max_concurrent = len(available_apis) if available_apis else 1

        logger.info(f"开始并行处理 {len(users)} 个用户的打卡，最大并发数: {max_concurrent}")

        # 创建信号量来限制并发数
        semaphore = asyncio.Semaphore(max_concurrent)

        async def process_user(user: User, index: int) -> Dict:
            """处理单个用户的打卡"""
            async with semaphore:
                try:
                    logger.info(f"[{index + 1}/{len(users)}] 开始处理用户: {user.username}")

                    # 调用打卡 API（会动态获取可用的 Worker API）
                    result = await ClockinService.call_clockin_api(db, user, 'manual')

                    # 保存结果
                    await ClockinService.save_clockin_result(db, user, result)

                    # 更新用户信息
                    await UserService.update_clockin_info(
                        db,
                        user.id,
                        result.get('success', False),
                        datetime.utcnow()
                    )

                    success = result.get('success', False)
                    logger.info(f"[{index + 1}/{len(users)}] 用户 {user.username} 打卡{'成功' if success else '失败'}")

                    return {
                        'username': user.username,
                        'success': success,
                        'error': result.get('error')
                    }

                except Exception as e:
                    logger.error(f"[{index + 1}/{len(users)}] 用户 {user.username} 打卡异常: {e}")
                    return {
                        'username': user.username,
                        'success': False,
                        'error': str(e)
                    }

        # 创建所有任务
        tasks = [
            process_user(user, i)
            for i, user in enumerate(users)
        ]

        # 并行执行所有任务
        start_time = datetime.now()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        duration = (datetime.now() - start_time).total_seconds()

        # 统计结果
        success_count = 0
        failure_count = 0
        valid_results = []

        for result in results:
            if isinstance(result, Exception):
                logger.error(f"任务异常: {result}")
                failure_count += 1
            else:
                valid_results.append(result)
                if result['success']:
                    success_count += 1
                else:
                    failure_count += 1

        logger.info(f"并行打卡完成: 成功 {success_count}, 失败 {failure_count}, 耗时: {duration:.2f}秒")

        return {
            'status': 'completed',
            'message': f'打卡完成: 成功 {success_count}, 失败 {failure_count}, 耗时 {duration:.2f}秒',
            'total': len(users),
            'success': success_count,
            'failure': failure_count,
            'results': valid_results,
            'duration_seconds': duration
        }

    @staticmethod
    async def trigger_user(db: AsyncSession, user_id: str) -> Dict:
        """触发指定用户打卡"""
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if not user:
            return {'success': False, 'error': '用户不存在'}

        if not user.enabled:
            return {'success': False, 'error': '用户未启用'}

        try:
            # 调用打卡 API
            result = await ClockinService.call_clockin_api(db, user, 'manual')

            # 保存结果
            await ClockinService.save_clockin_result(db, user, result)

            # 重新获取用户对象（确保数据是最新的）
            user = await UserService.get_user(db, user_id)
            if user and user.clockin_count is None:
                user.clockin_count = 0
                await db.commit()

            # 更新用户信息
            await UserService.update_clockin_info(
                db,
                user.id,
                result.get('success', False),
                datetime.utcnow()
            )

            return result

        except Exception as e:
            logger.error(f"trigger_user 失败: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}

    @staticmethod
    async def get_clockin_results(
        db: AsyncSession,
        date: str,
        range_type: str = 'day'
    ) -> Dict:
        """获取打卡历史"""
        if range_type == 'week':
            # 获取一周数据
            week_data = []
            today = datetime.utcnow()

            for i in range(7):
                d = today - timedelta(days=i)
                date_str = d.strftime('%Y-%m-%d')

                results = await db.execute(
                    select(ClockinResult)
                    .where(ClockinResult.date == date_str)
                    .order_by(ClockinResult.timestamp.desc())
                )
                results = results.scalars().all()

                summary = await db.execute(
                    select(DailySummary).where(DailySummary.date == date_str)
                )
                summary = summary.scalar_one_or_none()

                if results or summary:
                    week_data.append({
                        'date': date_str,
                        'summary': summary.to_dict() if summary else None,
                        'results': [r.to_dict() for r in results]
                    })

            return {
                'range': 'week',
                'dates': week_data,
                'total_days': len(week_data)
            }

        # 单日数据
        results = await db.execute(
            select(ClockinResult)
            .where(ClockinResult.date == date)
            .order_by(ClockinResult.timestamp.desc())
        )
        results = results.scalars().all()

        summary = await db.execute(
            select(DailySummary).where(DailySummary.date == date)
        )
        summary = summary.scalar_one_or_none()

        return {
            'range': 'day',
            'date': date,
            'summary': summary.to_dict() if summary else None,
            'results': [r.to_dict() for r in results]
        }

    @staticmethod
    async def get_stats(db: AsyncSession) -> Dict:
        """获取统计数据"""
        # 用户统计
        total_users = await db.execute(select(func.count(User.id)))
        total_users = total_users.scalar() or 0

        enabled_users = await db.execute(
            select(func.count(User.id)).where(User.enabled == True)
        )
        enabled_users = enabled_users.scalar() or 0

        total_clockins = await db.execute(
            select(func.sum(User.clockin_count))
        )
        total_clockins = total_clockins.scalar() or 0

        # 最近打卡记录
        recent_results = []
        for i in range(7):
            date = (datetime.utcnow() - timedelta(days=i)).strftime('%Y-%m-%d')
            summary = await db.execute(
                select(DailySummary).where(DailySummary.date == date)
            )
            summary = summary.scalar_one_or_none()
            if summary:
                recent_results.append(summary.to_dict())

        return {
            'total_users': total_users,
            'enabled_users': enabled_users,
            'total_clockins': total_clockins,
            'recent_results': recent_results
        }
