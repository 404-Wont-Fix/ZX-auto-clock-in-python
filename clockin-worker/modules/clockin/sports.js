/**
 * 运动打卡模块
 */

import { getBingImage } from '../image.js';
import { uploadImage } from '../upload.js';
import { fetchWithTimeout, postJson } from '../utils/fetch.js';

/**
 * 从URL获取图片数据
 * @param {string} imageUrl - 图片URL
 * @returns {Promise<{success: boolean, data?: object, message?: string}>}
 */
async function fetchImageFromUrl(imageUrl) {
    try {
        console.log(`[自定义图片] 从URL获取图片: ${imageUrl}`);

        const response = await fetchWithTimeout(imageUrl, {
            headers: {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
        }, 15000); // 15秒超时

        if (!response.ok) {
            return {
                success: false,
                message: `获取图片失败: ${response.status}`
            };
        }

        const imageBuffer = await response.arrayBuffer();
        const contentType = response.headers.get('content-type') || 'image/jpeg';

        // 从 contentType 确定文件扩展名
        let extension = 'jpg';
        if (contentType.includes('png')) {
            extension = 'png';
        } else if (contentType.includes('gif')) {
            extension = 'gif';
        } else if (contentType.includes('webp')) {
            extension = 'webp';
        } else if (contentType.includes('jpeg')) {
            extension = 'jpg';
        }

        // 生成带时间戳的文件名，确保有扩展名
        const timestamp = Date.now();
        const fileName = `sports_${timestamp}.${extension}`;

        console.log(`[自定义图片] 文件名: ${fileName}, 类型: ${contentType}`);

        return {
            success: true,
            data: {
                buffer: imageBuffer,
                contentType: contentType,
                fileName: fileName
            }
        };
    } catch (error) {
        return {
            success: false,
            message: `获取图片异常: ${error.message}`
        };
    }
}

export async function clockInSports(accessToken, env) {
    try {
        // 1. 获取图片（支持自定义URL或默认必应图片）
        let imageResponse;

        if (env?.SPORTS_IMAGE_URL) {
            // 使用admin-worker提供的图片URL
            imageResponse = await fetchImageFromUrl(env.SPORTS_IMAGE_URL);
            if (!imageResponse.success) {
                return {
                    success: false,
                    message: `获取自定义图片失败: ${imageResponse.message}`,
                    data: null
                };
            }
        } else {
            // 使用默认必应图片
            imageResponse = await getBingImage();
            if (!imageResponse.success) {
                return {
                    success: false,
                    message: `获取图片失败: ${imageResponse.message}`,
                    data: null
                };
            }
        }

        // 2. 上传图片
        const uploadResult = await uploadImage(accessToken, imageResponse.data);
        if (!uploadResult.success) {
            return {
                success: false,
                message: `图片上传失败: ${uploadResult.message}`,
                data: null
            };
        }

        // 3. 提交运动打卡（带超时和重试）
        const sportsContent = env?.SPORTS_COMMENT || '特色';
        const endpoint = 'https://ai.cqzuxia.com/growing/api/StuTask/SaveStuDailyAssignment';

        const imageId = uploadResult.data.id || uploadResult.data.Id;
        const imageJsonArray = JSON.stringify([imageId]);

        const response = await postJson(
            endpoint,
            {
                ASSType: '0',
                Comment: sportsContent,
                ImgJson: imageJsonArray
            },
            {
                'accept': 'application/json, text/plain, */*',
                'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
                'authorization': `Bearer ${accessToken}`,
                'cache-control': 'no-cache',
                'content-type': 'application/json',
                'origin': 'https://ai.cqzuxia.com',
                'referer': 'https://ai.cqzuxia.com/stu-growing/',
                'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36 Edg/142.0.0.0'
            },
            10000 // 10秒超时（缩短以避免整体超时）
        );

        const responseText = await response.text();

        if (!responseText.trim()) {
            return {
                success: false,
                message: `运动打卡失败: 服务器返回空响应`,
                data: null
            };
        }

        let data;
        try {
            data = JSON.parse(responseText);
        } catch (jsonError) {
            return {
                success: false,
                message: `运动打卡失败: 响应不是有效的JSON格式`,
                data: null
            };
        }

        if (response.ok && (data.code === 0 || data.success === true)) {
            return {
                success: true,
                message: '运动打卡成功',
                data: data
            };
        } else {
            return {
                success: false,
                message: data.message || data.msg || `运动打卡失败: ${response.status}`,
                data: data
            };
        }
    } catch (error) {
        return {
            success: false,
            message: `运动打卡异常: ${error.message}`,
            data: null
        };
    }
}
