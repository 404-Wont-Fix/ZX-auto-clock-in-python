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
        retries: Optional[int] = None,
        worker_api: Optional[WorkerApi] = None
    ) -> Dict:
        """
        调用 clockin-worker API（支持多 API 负载均衡和智能重试）

        Args:
            db: 数据库会话
            user: 用户对象
            triggered_by: 触发方式 (manual/scheduled)
            retries: 重试次数（None 则使用配置中的默认值）
            worker_api: 指定的 Worker API（可选）

        Returns:
            打卡结果字典
        """
        # 获取重试配置
        max_retries = retries if retries is not None else settings.clockin_retry_count
        retry_delay = settings.clockin_retry_delay
        rate_limit_delay = settings.clockin_rate_limit_delay
        timeout = settings.clockin_timeout

        # 获取 Worker API（如果没有指定，则自动选择）
        if worker_api is None:
            worker_api = await WorkerApiService.get_next_api(db)

        # 如果没有可用的 Worker API，返回错误
        if worker_api is None:
            logger.error("没有可用的 Worker API，请先在 Worker API 管理中添加至少一个可用的 API")
            return {
                'success': False,
                'message': '没有可用的 Worker API，请先在 Worker API 管理中添加至少一个可用的 API',
                'details': {}
            }

        api_url = worker_api.url
        api_token = worker_api.token
        # 记录请求统计
        await WorkerApiService.increment_requests(db, worker_api.id)
        logger.info(f"[用户 {user.username}] 使用 Worker API: {worker_api.name} ({api_url})，最大重试次数: {max_retries}")

        last_worker_api_id = worker_api.id
        task_success = False

        # 记录活动任务
        await ActiveTaskService.start_task(
            user_id=user.id,
            username=user.username,
            nickname=user.nickname or user.username,
            worker_api_id=worker_api.id,
            worker_api_name=worker_api.name
        )

        try:
            for attempt in range(max_retries + 1):
                try:
                    if attempt > 0:
                        logger.info(f"[用户 {user.username}] 重试第 {attempt} 次")

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
                    is_timeout = False
                    is_rate_limit = False

                    try:
                        async with httpx.AsyncClient(timeout=timeout) as client:
                            response = await client.post(
                                url,
                                json=request_body,
                                headers={
                                    "Content-Type": "application/json",
                                    "Authorization": f"Bearer {api_token}"
                                }
                            )
                    except httpx.TimeoutException:
                        logger.warning(f"[用户 {user.username}] 请求超时")
                        is_timeout = True
                        # 超时错误，使用默认延迟
                        if attempt < max_retries:
                            await asyncio.sleep(retry_delay)
                            continue
                        else:
                            raise Exception(f"请求超时（超过 {timeout} 秒）")

                    except httpx.ConnectError as e:
                        logger.warning(f"[用户 {user.username}] 连接失败: {e}")
                        # 连接错误，可以立即重试
                        if attempt < max_retries:
                            await asyncio.sleep(1)  # 连接错误使用较短延迟
                            continue
                        else:
                            raise Exception(f"连接失败: {str(e)}")

                    duration = (datetime.now() - start_time).total_seconds() * 1000

                    if not response.is_success:
                        status_code = response.status_code
                        logger.warning(f"[用户 {user.username}] API 请求失败: HTTP {status_code}")

                        # 检查是否是频率限制错误
                        if status_code == 429:
                            is_rate_limit = True
                            logger.warning(f"[用户 {user.username}] 触发频率限制，使用较长延迟")
                            delay = rate_limit_delay
                        # 5xx 服务器错误或 429 频率限制
                        elif status_code >= 500 or status_code == 429:
                            delay = retry_delay
                        else:
                            # 4xx 其他错误不重试
                            delay = None

                        # 标记失败（仅在最后一次失败时）
                        if attempt == max_retries:
                            await WorkerApiService.mark_failure(db, last_worker_api_id)

                            # 不再自动切换 API（避免与队列机制冲突）
                            # 返回错误，让上层决定是否重试
                            error_msg = f"API 请求失败: HTTP {status_code}"
                            try:
                                error_detail = response.json()
                                if 'message' in error_detail:
                                    error_msg = error_detail['message']
                            except:
                                pass
                            raise Exception(error_msg)

                        # 如果需要重试
                        if delay is not None and attempt < max_retries:
                            logger.info(f"[用户 {user.username}] {delay} 秒后重试...")
                            await asyncio.sleep(delay)
                            continue

                        raise Exception(f"API 请求失败: HTTP {status_code}")

                    result = response.json()
                    result['duration'] = duration
                    result['triggered_by'] = triggered_by
                    result['sports_comment'] = sports_comment
                    result['sports_comment_source'] = user.sports_comment_type
                    result['daily_comment'] = daily_comment
                    result['daily_comment_source'] = user.daily_comment_type

                    # API 使用信息
                    result['sports_comment_api'] = user.sports_comment_api if user.sports_comment_type == 'api' else None
                    result['daily_comment_api'] = user.daily_comment_api if user.daily_comment_type == 'api' else None
                    result['sports_image_type'] = user.sports_image_type
                    result['sports_image_provider'] = user.sports_image_provider
                    result['sports_image_category'] = user.sports_image_category

                    # 重新计算整体成功状态（覆盖外部 API 的 success 字段）
                    details = result.get('results', {})

                    # 详细打印各个打卡类型的结果（用于调试）
                    for clockin_type, type_result in details.items():
                        if isinstance(type_result, dict):
                            success = type_result.get('success', False)
                            message = type_result.get('message', '')
                            status = "✓ 成功" if success else "✗ 失败"
                            logger.info(f"[用户 {user.username}] {clockin_type.upper()} 打卡 {status}: {message}")

                            # 如果是 sports 类型失败，打印更详细的调试信息
                            if clockin_type == 'sports' and not success:
                                logger.warning(f"╔══════════════════════════════════════════════════════════════╗")
                                logger.warning(f"║  🖼️  [图片上传失败] 调试信息                                   ║")
                                logger.warning(f"╠══════════════════════════════════════════════════════════════╣")
                                logger.warning(f"║  用户名: {user.username}")
                                logger.warning(f"║  昵称: {user.nickname or '无'}")
                                logger.warning(f"║  图片类型: {user.sports_image_type}")
                                logger.warning(f"║  图片提供商: {user.sports_image_provider}")
                                if user.sports_image_provider != 'bing':
                                    logger.warning(f"║  图片分类: {user.sports_image_category}")
                                if image_data and image_data.get('url'):
                                    logger.warning(f"║  图片 URL: {image_data['url']}")
                                    logger.warning(f"║  图片长度: {len(image_data.get('url', ''))} 字符")
                                else:
                                    logger.warning(f"║  图片 URL: (无)")
                                logger.warning(f"║  错误信息: {message}")
                                logger.warning(f"╚══════════════════════════════════════════════════════════════╝")

                    result['success'] = ClockinService._calculate_overall_success(details)

                    # 标记成功
                    if last_worker_api_id:
                        await WorkerApiService.mark_success(db, last_worker_api_id)

                    task_success = True
                    logger.info(f"[用户 {user.username}] 打卡成功，耗时 {duration:.0f}ms")
                    return result

                except Exception as e:
                    logger.warning(f"[用户 {user.username}] 第 {attempt + 1} 次尝试失败: {e}")

                    # 标记失败（仅在最后一次失败时）
                    if attempt == max_retries:
                        if last_worker_api_id:
                            await WorkerApiService.mark_failure(db, last_worker_api_id)

                        # 不再自动切换 API（避免与队列机制冲突）
                        # 返回错误，让上层决定是否重试
                        return {
                            'success': False,
                            'error': str(e),
                            'triggered_by': triggered_by,
                            'timestamp': datetime.utcnow().isoformat()
                        }

                    if attempt < max_retries:
                        # 根据错误类型决定延迟
                        if '超时' in str(e) or 'timeout' in str(e).lower():
                            # 超时使用标准延迟
                            await asyncio.sleep(retry_delay)
                        elif '频率' in str(e) or 'rate limit' in str(e).lower() or '429' in str(e):
                            # 频率限制使用较长延迟
                            await asyncio.sleep(rate_limit_delay)
                        else:
                            # 其他错误使用较短延迟
                            await asyncio.sleep(max(1, retry_delay // 2))
                        continue
        finally:
            # 确保任务追踪总是被清理（无论成功或失败）
            # 避免任务泄漏到活动任务列表中
            try:
                await ActiveTaskService.complete_task(
                    user_id=user.id,
                    success=task_success
                )
            except Exception as e:
                # 记录错误但不影响主流程
                logger.error(f"清理活动任务失败: {e}")

    @staticmethod
    async def save_clockin_result(
        db: AsyncSession,
        user: User,
        result: Dict
    ) -> ClockinResult:
        """保存打卡结果（带事务处理）"""
        date = datetime.utcnow().strftime('%Y-%m-%d')
        timestamp = result.get('timestamp', datetime.utcnow().isoformat())

        # 构建详情 JSON
        details = result.get('results', {})

        # 注意：result['success'] 已经在 call_clockin_api 中重新计算过了
        # 这里直接使用即可
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
            sports_comment_api=result.get('sports_comment_api'),
            daily_comment_api=result.get('daily_comment_api'),
            sports_image_type=result.get('sports_image_type'),
            sports_image_provider=result.get('sports_image_provider'),
            sports_image_category=result.get('sports_image_category'),
            duration_ms=result.get('duration'),
            triggered_by=result.get('triggered_by'),
            error=result.get('error')
        )

        try:
            db.add(clockin_result)
            await db.flush()  # 先 flush 以获取 ID，但不提交事务

            # 更新每日汇总
            await ClockinService._update_daily_summary(db, date, clockin_result)

            await db.commit()  # 统一提交事务
            return clockin_result
        except Exception as e:
            logger.error(f"保存打卡结果失败，正在回滚: {e}")
            await db.rollback()
            raise

    @staticmethod
    async def _update_daily_summary(
        db: AsyncSession,
        date: str,
        result: ClockinResult
    ):
        """更新每日汇总（不提交事务，由调用者统一提交）"""
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

    @staticmethod
    async def trigger_all_users(
        db: AsyncSession,
        triggered_by: str = 'manual'
    ) -> Dict:
        """触发所有用户打卡（并行动态分配）

        Args:
            db: 数据库会话
            triggered_by: 触发方式 (manual/scheduled)
        """
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

        # 获取可用的 Worker API
        available_apis = await WorkerApiService.get_available_apis(db)

        if not available_apis:
            return {
                'status': 'completed',
                'message': '没有可用的 Worker API',
                'total': len(users),
                'success': 0,
                'failure': len(users)
            }

        max_concurrent = len(available_apis)
        logger.info(f"开始并行处理 {len(users)} 个用户的打卡，最大并发数: {max_concurrent}，可用 API 数量: {max_concurrent}")

        # 创建 API 队列（预先分配 API，避免竞态条件）
        api_queue = asyncio.Queue()
        for api in available_apis:
            await api_queue.put(api)

        # 创建信号量来限制并发数
        semaphore = asyncio.Semaphore(max_concurrent)

        async def process_user(user: User, index: int) -> Dict:
            """处理单个用户的打卡（使用独立的数据库 session）"""
            async with semaphore:
                # 为每个任务创建独立的数据库 session，避免并发冲突
                from app.core.database import AsyncSessionLocal

                async with AsyncSessionLocal() as user_db:
                    try:
                        logger.info(f"[{index + 1}/{len(users)}] 开始处理用户: {user.username}")

                        # 从队列中获取 API（阻塞等待，确保不会重复使用）
                        worker_api = await api_queue.get()

                        try:
                            logger.info(f"[{index + 1}/{len(users)}] 用户 {user.username} 使用 API: {worker_api.name}")

                            # 使用预先分配的 API 调用打卡（使用独立的 session）
                            result = await ClockinService.call_clockin_api(
                                user_db, user, triggered_by, None, worker_api
                            )

                            # 保存结果（使用独立的 session）
                            await ClockinService.save_clockin_result(user_db, user, result)

                            # 更新用户信息（使用独立的 session）
                            await UserService.update_clockin_info(
                                user_db,
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
                        finally:
                            # 无论成功失败，都将 API 放回队列供其他用户使用
                            await api_queue.put(worker_api)

                    except Exception as e:
                        logger.error(f"[{index + 1}/{len(users)}] 用户 {user.username} 打卡异常: {e}", exc_info=True)
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

        # 自动重试失败的用户的逻辑（手动和定时任务都支持）
        failed_users = []
        for result in valid_results:
            # 使用新的判断逻辑：检查是否有打卡类型真正失败（排除"已完成"的情况）
            if ClockinService._needs_retry(result):
                failed_users.append(result['username'])

        if failed_users:
            # 定时任务和手动打卡都会自动重试失败的打卡类型
            logger.info(f"╔══════════════════════════════════════════════════════════════╗")
            logger.info(f"║  🔄 【自动补签】检测到 {len(failed_users)} 个用户有未完成的打卡  ║")
            logger.info(f"║  失败用户列表: {', '.join(failed_users)}                              ║")
            logger.info(f"╚══════════════════════════════════════════════════════════════╝")

            # 获取重试配置
            from app.config import settings
            max_retry_rounds = settings.schedule_retry_count
            retry_delay = settings.schedule_retry_delay

            logger.info(f"开始自动重试（触发方式: {triggered_by}）: 最多 {max_retry_rounds} 轮重试，每轮间隔 {retry_delay} 秒")

            # 多轮重试
            for retry_round in range(1, max_retry_rounds + 1):
                logger.info(f"╔══════════════════════════════════════════════════════════════╗")
                logger.info(f"║  🔄 【第 {retry_round}/{max_retry_rounds} 轮自动补签】开始执行                     ║")
                logger.info(f"╚══════════════════════════════════════════════════════════════╝")
                if not failed_users:
                    break

                logger.info(f"=== 第 {retry_round}/{max_retry_rounds} 轮重试开始 ===")
                logger.info(f"等待 {retry_delay} 秒后开始重试...")
                await asyncio.sleep(retry_delay)

                retry_results = []
                still_failed_users = []

                for username in failed_users:
                    user_query = await db.execute(
                        select(User).where(User.username == username, User.enabled == True)
                    )
                    user = user_query.scalar_one_or_none()

                    if user:
                        logger.info(f"[第 {retry_round} 轮] 开始重试用户: {username}")

                        try:
                            # 调用打卡 API（标记为 retry，表示补签）
                            retry_result = await ClockinService.call_clockin_api(
                                db, user, triggered_by='retry'
                            )

                            # 保存结果
                            await ClockinService.save_clockin_result(db, user, retry_result)

                            # 更新用户信息
                            await UserService.update_clockin_info(
                                db,
                                user.id,
                                retry_result.get('success', False),
                                datetime.utcnow()
                            )

                            success = retry_result.get('success', False)
                            retry_results.append({
                                'username': username,
                                'success': success,
                                'error': retry_result.get('error')
                            })

                            # 检查是否还需要重试（使用统一的判断逻辑）
                            needs_retry = ClockinService._needs_retry(retry_result)
                            if needs_retry:
                                # 记录哪些打卡类型还未完成
                                if retry_result.get('results'):
                                    results_data = retry_result['results']
                                    failed_types = [
                                        f"{name}({r.get('message', '失败')})"
                                        for name, r in results_data.items()
                                        if not r.get('success') and not any(kw in r.get('message', '') for kw in ['今日已完成', '已完成'])
                                    ]
                                    if failed_types:
                                        logger.warning(f"用户 {username} 重试后仍有打卡未完成: {', '.join(failed_types)}")

                            # 如果仍需要重试，加入下一轮重试列表
                            if needs_retry:
                                still_failed_users.append(username)
                            else:
                                logger.info(f"用户 {username} 重试成功")

                            # 每个用户之间间隔5秒，避免频率限制
                            await asyncio.sleep(5)
                        except Exception as e:
                            logger.error(f"[第 {retry_round} 轮] 用户 {username} 重试异常: {e}", exc_info=True)
                            still_failed_users.append(username)

                logger.info(f"[第 {retry_round} 轮] 重试打卡完成: {retry_results}")

                # 更新失败用户列表
                failed_users = still_failed_users

                if not failed_users:
                    logger.info(f"所有用户在第 {retry_round} 轮重试后全部成功")
                    break

            if failed_users:
                logger.warning(f"╔══════════════════════════════════════════════════════════════╗")
                logger.warning(f"║  ❌ 【自动补签结束】仍有 {len(failed_users)} 个用户打卡失败  ║")
                logger.warning(f"║  失败用户: {', '.join(failed_users)}                                 ║")
                logger.warning(f"╚══════════════════════════════════════════════════════════════╝")
            else:
                logger.info(f"╔══════════════════════════════════════════════════════════════╗")
                logger.info(f"║  ✅ 【自动补签结束】所有用户打卡成功                      ║")
                logger.info(f"╚══════════════════════════════════════════════════════════════╝")

        # 重新统计最终结果（确保计数准确）
        final_success_count = sum(1 for r in valid_results if r.get('success'))
        final_failure_count = len(valid_results) - final_success_count

        total_duration = (datetime.now() - start_time).total_seconds()
        logger.info(f"打卡任务全部完成: 成功 {final_success_count}, 失败 {final_failure_count}, 总耗时: {total_duration:.2f}秒")

        return {
            'status': 'completed',
            'message': f'打卡完成: 成功 {final_success_count}, 失败 {final_failure_count}, 耗时: {total_duration:.2f}秒',
            'total': len(users),
            'success': final_success_count,
            'failure': final_failure_count,
            'results': valid_results,
            'duration_seconds': total_duration
        }

    @staticmethod
    async def trigger_user(
        db: AsyncSession,
        user_id: str,
        triggered_by: str = 'manual'
    ) -> Dict:
        """触发指定用户打卡

        Args:
            db: 数据库会话
            user_id: 用户 ID
            triggered_by: 触发方式 (manual/scheduled)
        """
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if not user:
            return {'success': False, 'error': '用户不存在'}

        if not user.enabled:
            return {'success': False, 'error': '用户未启用'}

        try:
            # 调用打卡 API
            result = await ClockinService.call_clockin_api(db, user, triggered_by)

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
        """获取打卡历史

        Args:
            db: 数据库会话
            date: 日期 (YYYY-MM-DD)
            range_type: 范围类型 - day(单日), 3days(3天), week(7天)
        """
        if range_type in ['3days', 'week']:
            # 获取多天数据
            days_count = 3 if range_type == '3days' else 7
            multi_data = []
            today = datetime.utcnow()

            for i in range(days_count):
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
                    multi_data.append({
                        'date': date_str,
                        'summary': summary.to_dict() if summary else None,
                        'results': [r.to_dict() for r in results]
                    })

            return {
                'range': range_type,
                'dates': multi_data,
                'total_days': len(multi_data)
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
    def _calculate_overall_success(details: Dict) -> bool:
        """
        基于打卡类型详情计算整体成功状态

        判断逻辑：
        - 如果所有打卡类型都成功，返回 True
        - 如果有打卡类型失败，但失败消息包含"今日已完成"、"已完成"等关键词（表示已经完成过），也视为成功
        - 如果有任何打卡类型真正失败（非"已完成"原因），返回 False

        Args:
            details: 打卡类型详情字典 (results)

        Returns:
            整体是否成功
        """
        if not details:
            return False

        # 已完成的关键词（视为成功，不需要重试）
        completed_keywords = ['今日已完成', '已完成']

        for clockin_type, type_result in details.items():
            if isinstance(type_result, dict):
                success = type_result.get('success', False)
                message = type_result.get('message', '')

                # 如果这个打卡类型失败
                if not success:
                    # 检查是否因为"已完成"而失败
                    is_completed = any(keyword in message for keyword in completed_keywords)
                    if not is_completed:
                        # 不是因为"已完成"，这是一个真正的失败
                        logger.info(f"打卡类型 {clockin_type} 真正失败: {message}")
                        return False

        # 所有打卡类型都成功（或因为"已完成"而失败），整体视为成功
        return True

    @staticmethod
    def _needs_retry(result: Dict) -> bool:
        """
        判断打卡结果是否需要重试

        排除情况：
        - 整体成功且所有打卡类型都成功
        - 打卡类型失败但消息包含"今日已完成"、"已完成"等（表示已经完成过）

        Args:
            result: 打卡结果字典

        Returns:
            是否需要重试
        """
        # 整体失败肯定需要重试
        if not result.get('success'):
            return True

        # 检查各个打卡类型
        results = result.get('results', {})
        if not results:
            return False

        # 已完成的关键词（不需要重试）
        completed_keywords = ['今日已完成', '已完成']

        for clockin_type, type_result in results.items():
            if isinstance(type_result, dict):
                success = type_result.get('success', False)
                message = type_result.get('message', '')

                # 如果这个打卡类型失败
                if not success:
                    # 检查是否因为"已完成"而失败
                    is_completed = any(keyword in message for keyword in completed_keywords)
                    if not is_completed:
                        # 不是因为"已完成"，需要重试
                        logger.info(f"检测到打卡类型 {clockin_type} 需要重试: {message}")
                        return True

        return False

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
