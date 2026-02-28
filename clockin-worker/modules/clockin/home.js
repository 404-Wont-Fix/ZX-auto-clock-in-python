/**
 * 首页签到模块
 */

import { get } from '../utils/fetch.js';

export async function clockInHome(accessToken) {
    try {
        const response = await get(
            'https://ai.cqzuxia.com/',
            {
                'Authorization': `Bearer ${accessToken}`,
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
                'Referer': 'https://ai.cqzuxia.com/',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36'
            },
            8000 // 8秒超时
        );

        if (!response.ok) {
            return {
                success: false,
                message: `首页签到失败: HTTP ${response.status} ${response.statusText}`,
                data: null
            };
        }

        const textContent = await response.text();
        return {
            success: true,
            message: '首页签到成功',
            data: { contentLength: textContent.length }
        };
    } catch (error) {
        return {
            success: false,
            message: `首页签到异常: ${error.message}`,
            data: null
        };
    }
}
