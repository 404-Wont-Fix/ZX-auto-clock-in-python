"""
诗词和图片 API 服务
"""
import httpx
import json
from typing import Optional, Dict
from app.models.database import User


class PoetryService:
    """诗词和图片服务类"""

    @staticmethod
    def _decode_unicode(text: str) -> str:
        """解码 Unicode 转义序列（如 \u505a\u4efb\u4f55 -> 做任何一件事）"""
        try:
            # 使用 json.loads 自动解码 Unicode 转义序列
            # 将字符串包裹在引号中作为 JSON 解析
            return json.loads(f'"{text}"')
        except:
            # 如果解码失败，返回原文本
            return text

    # 诗词 API 配置（与原JS项目保持一致）
    POETRY_APIS = {
        'poetry_all': 'https://v1.jinrishici.com/all.json',
        'hitokoto': 'https://v1.hitokoto.cn/',
        'cenguigui': 'https://api-v2.cenguigui.cn/api/yiyan/?code=json',
        'yuanmeng': 'https://api.mmp.cc/api/yiyan?format=json',
        'klapi': 'https://www.klapi.cn/api/yiyan.php?type=json',
    }

    # 图片 API 配置（与原JS项目保持一致）
    IMAGE_APIS = {
        'bing': 'https://www.bing.com/HPImageArchive.aspx?format=js&n=1&mkt=zh-CN',
        'bing_uhd': 'https://bing.img.run/uhd.php',
        'komll': 'https://api.komll.com/images',
        'loliapi': 'https://www.loliapi.com/acg/',
    }

    # 次元 API 分类（与原JS项目保持一致）
    CIMU_API_CATEGORIES = {
        'ycy': '二次元自适应',
        'moez': '萌版自适应',
        'ai': 'AI自适应',
        'ysz': '原神自适应',
        'pc': 'PC横图',
        'moe': '萌版横图',
        'fj': '风景横图',
        'bd': '白底横图',
        'ys': '原神横图',
        'mp': '移动竖图',
        'moemp': '萌版竖图',
        'ysmp': '原神竖图',
        'aimp': 'AI竖图',
        'tx': '头像方图',
        'lai': '七濑胡桃',
        'xhl': '小狐狸',
        'random': '随机',
    }

    @staticmethod
    async def get_daily_comment(user: User) -> str:
        """获取每日打卡备注"""
        # 优先级：自定义 > API > 默认
        if user.daily_comment_type == 'custom':
            return user.custom_daily_comment or "今日学习内容总结，收获满满！"

        if user.daily_comment_type == 'api':
            api_type = user.daily_comment_api or 'poetry_all'  # 默认使用 poetry_all
            print(f"[PoetryService] 用户 {user.username} 配置的每日诗词API: {api_type} (原始值: {user.daily_comment_api})")
            comment = await PoetryService._fetch_poetry(api_type)
            if comment:
                print(f"[PoetryService] 每日诗词API返回内容: {comment[:50]}...")
            else:
                print(f"[PoetryService] 每日诗词API返回为空，使用默认值")
            return comment or "今日学习内容总结，收获满满！"

        return "今日学习内容总结，收获满满！"

    @staticmethod
    async def get_sports_comment(user: User) -> str:
        """获取运动打卡备注"""
        # 优先级：自定义 > API > 默认
        if user.sports_comment_type == 'custom':
            return user.sports_custom_comment or "已运动！"

        if user.sports_comment_type == 'api':
            api_type = user.sports_comment_api or 'poetry_all'  # 默认使用 poetry_all
            print(f"[PoetryService] 用户 {user.username} 配置的诗词API: {api_type} (原始值: {user.sports_comment_api})")
            comment = await PoetryService._fetch_poetry(api_type)
            if comment:
                print(f"[PoetryService] 诗词API返回内容: {comment[:50]}...")
            else:
                print(f"[PoetryService] 诗词API返回为空，使用默认值")
            return comment or "已运动！"

        return "已运动！"

    @staticmethod
    async def get_sports_image(user: User) -> Optional[Dict[str, str]]:
        """获取运动打卡图片"""
        # 如果是 default，返回 None，由 clockin-worker 处理
        if user.sports_image_type == 'default':
            return None

        if user.sports_image_type == 'api':
            provider = user.sports_image_provider or 'bing'
            category = user.sports_image_category or 'random'

            url = await PoetryService._fetch_image_url(provider, category)

            if url:
                return {'url': url, 'use_cw': False}

        # 标记由 clockin-worker 自行获取
        return {'url': None, 'use_cw': True}

    @staticmethod
    async def _fetch_poetry(api_type: str) -> Optional[str]:
        """获取诗词内容"""
        # 如果 api_type 为 None 或空字符串，返回 None
        if not api_type:
            print(f"[PoetryService] API 类型为空: {api_type}")
            return None

        # 处理 admin-worker 的命名格式（如 poetry_tianqi_xiefeng）
        actual_api_type, actual_param = PoetryService._parse_api_type(api_type)

        url = PoetryService.POETRY_APIS.get(actual_api_type)
        if not url:
            print(f"[PoetryService] 未知的 API 类型: {api_type} (解析为: {actual_api_type})，支持的类型: {list(PoetryService.POETRY_APIS.keys())}")
            return None

        try:
            print(f"[PoetryService] 正在请求诗词API: {api_type} (实际: {actual_api_type}), URL: {url}")

            # 构建请求 URL（对于诗词 API 需要添加分类）
            request_url = url
            if actual_api_type == 'poetry_all' and actual_param:
                # 将 poetry_tianqi_xiefeng 转换为 /tianqi/xiefeng.json
                category = actual_param.replace('_', '/')
                request_url = f"https://v1.jinrishici.com/{category}.json"
                print(f"[PoetryService] 诗词分类: {category}, 完整URL: {request_url}")

            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                response = await client.get(request_url)
                response.raise_for_status()
                data = response.json()

                # 根据不同 API 解析
                if actual_api_type == 'poetry_all':
                    result = data.get('content') or data.get('origin', {}).get('content')
                    print(f"[PoetryService] poetry_all 返回: {result[:30] if result else 'None'}...")
                    return result

                elif actual_api_type == 'hitokoto':
                    text = data.get('hitokoto', '')
                    # 如果有出处，附加到后面
                    if data.get('from'):
                        text += f' —— {data["from"]}'
                    print(f"[PoetryService] hitokoto 返回: {text[:30]}...")
                    return text

                elif actual_api_type == 'cenguigui':
                    # 检查返回码，需要解码Unicode
                    if data.get('code') == 200 and data.get('msg'):
                        text = data['msg']
                        result = PoetryService._decode_unicode(text)
                        print(f"[PoetryService] cenguigui 返回: {result[:30]}...")
                        return result
                    print(f"[PoetryService] cenguigui 返回错误: code={data.get('code')}")
                    return None

                elif actual_api_type == 'yuanmeng':
                    # 返回 quote 字段，需要解码Unicode
                    text = data.get('quote')
                    if text:
                        result = PoetryService._decode_unicode(text)
                        print(f"[PoetryService] yuanmeng 返回: {result[:30]}...")
                        return result
                    print(f"[PoetryService] yuanmeng 未找到 quote 字段")
                    return None

                elif actual_api_type == 'klapi':
                    # 返回 data.data.text 字段
                    if data.get('code') == 200 and data.get('data') and data['data'].get('text'):
                        result = data['data']['text']
                        print(f"[PoetryService] klapi 返回: {result[:30]}...")
                        return result
                    print(f"[PoetryService] klapi 返回错误: code={data.get('code')}")
                    return None

        except Exception as e:
            print(f"[PoetryService] 获取诗词失败 ({api_type}): {e}")

        return None

    @staticmethod
    def _parse_api_type(api_type: str) -> tuple:
        """
        解析 API 类型，处理 admin-worker 的命名格式
        返回 (实际 API 类型, 参数)

        例如：
        - poetry_all -> ('poetry_all', None)
        - poetry_tianqi_xiefeng -> ('poetry_all', 'tianqi_xiefeng')
        - hitokoto_all -> ('hitokoto', None)
        - hitokoto_a -> ('hitokoto', 'a')
        - cenguigui_default -> ('cenguigui', None)
        - yuanmeng_default -> ('yuanmeng', None)
        """
        if not api_type:
            return None, None

        # 处理 poetry_xxx 格式
        if api_type.startswith('poetry_'):
            parts = api_type.split('_', 1)
            if len(parts) == 2:
                param = parts[1]
                # 如果是 poetry_all 或 poetry_default，不添加分类
                if param in ['all', 'default']:
                    return 'poetry_all', None
                return 'poetry_all', param
            return 'poetry_all', None

        # 处理 hitokoto_xxx 格式
        if api_type.startswith('hitokoto_'):
            parts = api_type.split('_', 1)
            if len(parts) == 2:
                param = parts[1]
                # 如果是 all 或 default，不添加分类
                if param in ['all', 'default']:
                    return 'hitokoto', None
                return 'hitokoto', param
            return 'hitokoto', None

        # 处理 cenguigui_xxx 格式
        if api_type.startswith('cenguigui_'):
            # 忽略后缀，直接使用基础 API
            return 'cenguigui', None

        # 处理 yuanmeng_xxx 格式
        if api_type.startswith('yuanmeng_'):
            return 'yuanmeng', None

        # 处理 klapi_xxx 格式
        if api_type.startswith('klapi_'):
            return 'klapi', None

        # 直接返回原始类型
        return api_type, None

    @staticmethod
    async def _fetch_image_url(provider: str, category: str) -> Optional[str]:
        """获取图片 URL（自动跟随302重定向）"""
        try:
            if provider == 'bing':
                return await PoetryService._fetch_bing_image()

            elif provider == 'bing_uhd':
                # Bing UHD 第三方 API，通过302重定向获取高清壁纸
                url = PoetryService.IMAGE_APIS['bing_uhd']
                return await PoetryService._fetch_redirect_image(url)

            elif provider == 'komll':
                # Komll 使用固定的 URL，返回的是图片URL（会302重定向）
                url = PoetryService.IMAGE_APIS['komll']
                return await PoetryService._fetch_redirect_image(url)

            elif provider == 'loliapi':
                # LoliAPI 会302重定向到实际图片URL
                url = PoetryService.IMAGE_APIS['loliapi']
                return await PoetryService._fetch_redirect_image(url)

            elif provider == 'cimuapi':
                # 次元API支持多个分类
                return await PoetryService._fetch_cimu_image(category)

        except Exception as e:
            print(f"[PoetryService] 获取图片失败 ({provider}/{category}): {e}")

        return None

    @staticmethod
    async def _fetch_bing_image() -> Optional[str]:
        """获取必应壁纸"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(PoetryService.IMAGE_APIS['bing'])
                response.raise_for_status()

                # 检查响应内容类型（支持多种可能的类型）
                content_type = response.headers.get('content-type', '').lower()
                if 'json' not in content_type:
                    print(f"[PoetryService] 必应API返回非JSON内容: {content_type}")
                    print(f"[PoetryService] 响应内容预览: {response.text[:200]}")
                    return None

                data = response.json()

                images = data.get('images', [])
                if images:
                    image = images[0]
                    url = image.get('url')
                    if url:
                        # Bing API 返回的 url 可能是完整URL或相对路径
                        if url.startswith('http'):
                            # 已经是完整 URL
                            return url
                        elif url.startswith('/'):
                            # 相对路径，需要拼接域名
                            return f"https://www.bing.com{url}"
                        else:
                            # 其他情况，直接返回
                            print(f"[PoetryService] Bing URL 格式异常: {url}")
                            return None

        except json.JSONDecodeError as e:
            print(f"[PoetryService] 必应API返回无效JSON: {e}")
            print(f"[PoetryService] 响应内容: {response.text[:200] if 'response' in locals() else 'N/A'}")
        except Exception as e:
            print(f"[PoetryService] 获取必应图片失败: {e}")

        return None

    @staticmethod
    async def _fetch_redirect_image(url: str) -> Optional[str]:
        """获取重定向后的图片URL（处理302跳转）"""
        try:
            # 使用 follow_redirects=True 自动跟随重定向
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                response = await client.get(
                    url,
                    headers={
                        'Accept': 'image/*, application/json, text/html',
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                    }
                )
                response.raise_for_status()

                # 检查响应内容类型，如果是图片则返回URL
                content_type = response.headers.get('content-type', '')
                if 'image/' in content_type:
                    final_url = str(response.url)
                    print(f"[PoetryService] 重定向图片URL: {final_url}")
                    return final_url
                else:
                    # 如果不是图片，打印响应内容以便调试
                    text_preview = response.text[:100] if response.text else ''
                    print(f"[PoetryService] API返回非图片内容: {content_type}, 预览: {text_preview}")
                    return None

        except httpx.HTTPStatusError as e:
            print(f"[PoetryService] 获取重定向图片HTTP错误 ({url}): {e.response.status_code}")
        except Exception as e:
            print(f"[PoetryService] 获取重定向图片失败 ({url}): {e}")

        return None

    @staticmethod
    async def _fetch_cimu_image(category: str) -> Optional[str]:
        """获取次元API图片（支持多分类，自动302重定向）"""
        try:
            # 次元API的所有分类
            all_categories = [
                'ycy', 'moez', 'ai', 'ysz', 'pc', 'moe', 'fj', 'bd',
                'ys', 'mp', 'moemp', 'ysmp', 'aimp', 'tx', 'lai', 'xhl'
            ]

            # 如果是随机或不存在的分类，随机选择一个
            selected_category = category
            if category == 'random' or category not in all_categories:
                import random
                selected_category = random.choice(all_categories)
                print(f"[PoetryService] 次元API随机选择分类: {selected_category}")

            # 构建API URL（注意末尾斜杠避免301重定向）
            url = f"https://t.alcy.cc/{selected_category}/"

            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                response = await client.get(
                    url,
                    headers={
                        'Accept': 'image/*, application/json, text/html',
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                    }
                )
                response.raise_for_status()

                # 检查响应内容类型，如果是图片则返回URL
                content_type = response.headers.get('content-type', '')
                if 'image/' in content_type:
                    final_url = str(response.url)
                    print(f"[PoetryService] 次元API图片URL: {final_url}")
                    return final_url
                else:
                    # 如果不是图片，打印响应内容以便调试
                    text_preview = response.text[:100] if response.text else ''
                    print(f"[PoetryService] 次元API返回非图片内容: {content_type}, 预览: {text_preview}")
                    return None

        except httpx.HTTPStatusError as e:
            print(f"[PoetryService] 次元API HTTP错误 ({category}): {e.response.status_code}")
        except Exception as e:
            print(f"[PoetryService] 获取次元API图片失败 ({category}): {e}")

        return None
