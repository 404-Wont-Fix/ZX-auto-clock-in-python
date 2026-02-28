/**
 * 图片上传模块
 */

import { fetchWithTimeout } from './utils/fetch.js';

export async function uploadImage(accessToken, imageData) {
    try {
        const formData = new FormData();
        const date = new Date().toISOString().slice(0, 10).replace(/-/g, '');

        formData.append('bucketName', 'stu-growing');
        formData.append('filePath', `student-pc/${date}`);
        formData.append('FileType', '1');
        formData.append('file', new Blob([imageData.buffer], { type: imageData.contentType }), imageData.fileName);

        const response = await fetchWithTimeout(
            'https://ai.cqzuxia.com/oss/api/SmartFiles/UpLoadFormFile',
            {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${accessToken}`,
                    'Accept': 'application/json, text/plain, */*',
                    'Referer': 'https://ai.cqzuxia.com/',
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36'
                },
                body: formData
            },
            20000 // 20秒超时（图片上传可能较慢）
        );

        const responseText = await response.text();

        if (!responseText.trim()) {
            return {
                success: false,
                message: `图片上传失败: 服务器返回空响应`,
                data: null
            };
        }

        let data;
        try {
            data = JSON.parse(responseText);
        } catch (jsonError) {
            return {
                success: false,
                message: `图片上传失败: 响应不是有效的JSON格式`,
                data: null
            };
        }

        if (response.ok && (data.code === 0 || data.success === true)) {
            return {
                success: true,
                message: '图片上传成功',
                data: data.data || data
            };
        } else {
            return {
                success: false,
                message: data.message || data.msg || '图片上传失败',
                data: data
            };
        }
    } catch (error) {
        return {
            success: false,
            message: `图片上传异常: ${error.message}`,
            data: null
        };
    }
}
