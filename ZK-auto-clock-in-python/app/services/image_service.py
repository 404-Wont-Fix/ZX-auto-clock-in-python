"""
图片处理服务 - 统一转码为 JPEG 格式
解决"文件内容与扩展名不匹配"的问题
"""
import io
import httpx
from PIL import Image
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class ImageService:
    """图片处理服务类"""

    @staticmethod
    async def convert_image_to_jpeg(image_url: str, quality: int = 85) -> Optional[dict]:
        """
        下载图片并转换为 JPEG 格式

        Args:
            image_url: 原始图片 URL
            quality: JPEG 质量 (1-100, 默认 85)

        Returns:
            {
                'success': bool,
                'url': str,  # 转换后的图片 URL 或 base64
                'format': str,  # 原始格式
                'size': int,  # 转换后大小（字节）
                'error': str  # 错误信息
            }
        """
        try:
            logger.info(f"[ImageService] 开始处理图片: {image_url}")

            # 1. 下载原始图片
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.get(
                    image_url,
                    headers={
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                    }
                )
                response.raise_for_status()

                # 检查是否是图片
                content_type = response.headers.get('content-type', '')
                if 'image/' not in content_type:
                    logger.warning(f"[ImageService] URL 不是图片: {content_type}")
                    return {
                        'success': False,
                        'error': f'URL 不是图片内容: {content_type}'
                    }

                # 2. 转换为 JPEG
                image_bytes = response.content
                original_format = None

                # 尝试检测原始格式
                if 'image/webp' in content_type:
                    original_format = 'webp'
                elif 'image/png' in content_type:
                    original_format = 'png'
                elif 'image/jpeg' in content_type or 'image/jpg' in content_type:
                    original_format = 'jpeg'
                elif 'image/gif' in content_type:
                    original_format = 'gif'

                logger.info(f"[ImageService] 原始格式: {original_format or '未知'} ({content_type})")

                # 如果已经是 JPEG，直接返回
                if original_format == 'jpeg':
                    logger.info(f"[ImageService] 已经是 JPEG 格式，无需转换")
                    return {
                        'success': True,
                        'url': image_url,
                        'format': 'jpeg',
                        'size': len(image_bytes),
                        'converted': False
                    }

                # 3. 使用 PIL 转换图片
                try:
                    image = Image.open(io.BytesIO(image_bytes))

                    # 转换为 RGB 模式（处理 RGBA 等格式）
                    if image.mode in ('RGBA', 'LA', 'P'):
                        # 创建白色背景
                        background = Image.new('RGB', image.size, (255, 255, 255))
                        if image.mode == 'P':
                            image = image.convert('RGBA')
                        background.paste(image, mask=image.split()[-1] if image.mode in ('RGBA', 'LA') else None)
                        image = background
                    elif image.mode != 'RGB':
                        image = image.convert('RGB')

                    # 4. 压缩为 JPEG
                    output_buffer = io.BytesIO()
                    image.save(output_buffer, format='JPEG', quality=quality, optimize=True)
                    jpeg_bytes = output_buffer.getvalue()
                    output_buffer.close()

                    jpeg_size = len(jpeg_bytes)
                    original_size = len(image_bytes)
                    compression_ratio = (1 - jpeg_size / original_size) * 100 if original_size > 0 else 0

                    logger.info(f"[ImageService] 转换成功: {original_format} -> JPEG")
                    logger.info(f"[ImageService] 文件大小: {original_size} -> {jpeg_size} 字节 ({compression_ratio:.1f}% 压缩)")

                    # 5. 转换为 base64（直接嵌入到请求中）
                    import base64
                    jpeg_base64 = base64.b64encode(jpeg_bytes).decode('utf-8')

                    # 限制 base64 大小（精夏平台可能有大小限制）
                    max_size = 2 * 1024 * 1024  # 2MB
                    if jpeg_size > max_size:
                        # 如果太大，降低质量重新压缩
                        logger.warning(f"[ImageService] 图片过大 ({jpeg_size} 字节)，降低质量重新压缩")
                        output_buffer = io.BytesIO()
                        image.save(output_buffer, format='JPEG', quality=60, optimize=True)
                        jpeg_bytes = output_buffer.getvalue()
                        jpeg_base64 = base64.b64encode(jpeg_bytes).decode('utf-8')
                        jpeg_size = len(jpeg_bytes)
                        logger.info(f"[ImageService] 重新压缩后: {jpeg_size} 字节")

                    return {
                        'success': True,
                        'url': f'data:image/jpeg;base64,{jpeg_base64}',
                        'format': original_format or 'unknown',
                        'size': jpeg_size,
                        'original_size': original_size,
                        'converted': True,
                        'data_uri': True  # 标记为 data URI
                    }

                except Exception as e:
                    logger.error(f"[ImageService] PIL 处理图片失败: {e}")
                    return {
                        'success': False,
                        'error': f'图片处理失败: {str(e)}'
                    }

        except httpx.HTTPStatusError as e:
            logger.error(f"[ImageService] 下载图片失败: HTTP {e.response.status_code}")
            return {
                'success': False,
                'error': f'下载失败: HTTP {e.response.status_code}'
            }
        except Exception as e:
            logger.error(f"[ImageService] 处理图片时出错: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    @staticmethod
    async def process_image_url(image_url: str, enable_conversion: bool = True) -> Optional[str]:
        """
        处理图片 URL（可选转码）

        Args:
            image_url: 原始图片 URL
            enable_conversion: 是否启用转码（默认 True）

        Returns:
            处理后的图片 URL（base64 data URI 或原始 URL）
        """
        if not enable_conversion:
            return image_url

        result = await ImageService.convert_image_to_jpeg(image_url)

        if result and result.get('success'):
            return result['url']
        else:
            logger.warning(f"[ImageService] 图片处理失败，使用原始 URL: {result.get('error') if result else 'Unknown error'}")
            return image_url
