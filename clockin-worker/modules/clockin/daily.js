/**
 * 日精进打卡模块
 */

import { postJson } from '../utils/fetch.js';

export async function clockInDaily(accessToken, env) {
    try {
        const dailyContent = env?.DAILY_COMMENT || '今日学习精进，不断提升自我！';
        const endpoint = 'https://ai.cqzuxia.com/growing/api/StuTask/SaveStuDailyAssignment';

        const response = await postJson(
            endpoint,
            {
                ASSType: '1',
                Comment: dailyContent,
                ImgJson: '[]'
            },
            {
                'Authorization': `Bearer ${accessToken}`,
                'Content-Type': 'application/json',
                'Accept': 'application/json, text/plain, */*',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
                'Cache-Control': 'no-cache',
                'Origin': 'https://ai.cqzuxia.com',
                'Referer': 'https://ai.cqzuxia.com/stu-growing/',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36 Edg/142.0.0.0'
            },
            10000 // 10秒超时
        );

        const responseText = await response.text();

        if (!responseText.trim()) {
            return {
                success: false,
                message: `日精进打卡失败: 服务器返回空响应`,
                data: null
            };
        }

        let data;
        try {
            data = JSON.parse(responseText);
        } catch (jsonError) {
            return {
                success: false,
                message: `日精进打卡失败: 响应不是有效的JSON格式`,
                data: null
            };
        }

        if (response.ok && (data.code === 0 || data.success === true)) {
            return {
                success: true,
                message: '日精进打卡成功',
                data: data
            };
        } else {
            return {
                success: false,
                message: data.message || data.msg || `日精进打卡失败: ${response.status}`,
                data: data
            };
        }
    } catch (error) {
        return {
            success: false,
            message: `日精进打卡异常: ${error.message}`,
            data: null
        };
    }
}
