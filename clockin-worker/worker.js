/**
 * clockin-worker - 打卡执行器
 * 提供纯功能的打卡 API 接口
 *
 * 认证方式: Authorization: Bearer <token>
 * 响应格式: { success: boolean, error?: string, ...data }
 */

import { clockInHome, clockInSports, clockInDaily } from './modules/clockin/index.js';
import { getLoginToken } from './modules/auth.js';

// 日志控制（通过环境变量 ENABLE_LOGGING=true 启用）
let enableLogging = false;

const logger = {
    info: (...args) => {
        if (enableLogging) console.log(`[INFO] ${new Date().toISOString()}`, ...args);
    },
    warn: (...args) => {
        if (enableLogging) console.warn(`[WARN] ${new Date().toISOString()}`, ...args);
    },
    error: (...args) => {
        if (enableLogging) console.error(`[ERROR] ${new Date().toISOString()}`, ...args);
    },
    debug: (...args) => {
        if (enableLogging) console.log(`[DEBUG] ${new Date().toISOString()}`, ...args);
    }
};

/**
 * 常量时间字符串比较，避免 token 校验的计时侧信道
 */
function timingSafeTokenMatch(a, b) {
    if (typeof a !== 'string' || typeof b !== 'string') return false;
    if (a.length !== b.length) return false;
    let diff = 0;
    for (let i = 0; i < a.length; i++) {
        diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
    }
    return diff === 0;
}

/**
 * 带超时的 Promise 竞速，并在主 promise 先就绪时清理定时器，避免悬挂的 reject
 * 触发后续重试。
 */
async function raceWithTimeout(promise, timeoutMs, timeoutMsg) {
    let timeoutId;
    const timeoutPromise = new Promise((_, reject) => {
        timeoutId = setTimeout(() => reject(new Error(timeoutMsg)), timeoutMs);
    });
    try {
        return await Promise.race([promise, timeoutPromise]);
    } finally {
        clearTimeout(timeoutId);
    }
}

export default {
    async fetch(request, env, ctx) {
        try {
            enableLogging = env?.ENABLE_LOGGING === "true";

            const url = new URL(request.url);
            const path = url.pathname;

            // CORS 预检请求
            if (request.method === 'OPTIONS') {
                return new Response(null, {
                    status: 204,
                    headers: {
                        'Access-Control-Allow-Origin': '*',
                        'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
                        'Access-Control-Allow-Headers': 'Content-Type, Authorization',
                    },
                });
            }

            // API 认证
            const apiToken = request.headers.get('Authorization')?.replace('Bearer ', '');
            const validToken = env?.API_TOKEN;

            // 未配置 API_TOKEN 时直接报错，避免部署遗漏 secret 时被误以为"任意 token 都无效"
            if (!validToken) {
                logger.error('未配置 API_TOKEN，请通过 wrangler secret put API_TOKEN 设置');
                return jsonResponse({
                    success: false,
                    error: '服务端未配置 API_TOKEN'
                }, 500);
            }

            if (!apiToken || !timingSafeTokenMatch(apiToken, validToken)) {
                return jsonResponse({
                    success: false,
                    error: '未授权：无效的 API Token'
                }, 401);
            }

            // 路由处理
            if (path === '/health') {
                return jsonResponse({
                    status: 'healthy',
                    timestamp: new Date().toISOString(),
                    service: 'clockin-executor'
                });
            }

            if (path === '/status') {
                return jsonResponse({
                    status: 'operational',
                    timestamp: new Date().toISOString(),
                    service: 'clockin-executor',
                    version: '1.0.0',
                    endpoints: [
                        { path: '/health', method: 'GET', description: '健康检查' },
                        { path: '/status', method: 'GET', description: '服务状态' },
                        { path: '/clockin', method: 'POST', description: '执行打卡' }
                    ],
                    note: 'Cloudflare Workers 是无状态的，无法追踪当前正在执行的任务'
                });
            }

            if (path === '/clockin' && request.method === 'POST') {
                return await handleClockin(request, env);
            }

            // 404
            return jsonResponse({
                success: false,
                error: '接口不存在'
            }, 404);
        } catch (error) {
            logger.error('Worker 顶级错误捕获:', error);
            return jsonResponse({
                success: false,
                error: `内部错误: ${error.message}`
            }, 500);
        }
    }
};

/**
 * 处理打卡请求
 */
async function handleClockin(request, env) {
    try {
        const body = await request.json().catch(() => ({}));
        const { username, password, clockin_type = 'all', options = {} } = body;

        // 参数验证
        if (!username || !password) {
            return jsonResponse({
                success: false,
                error: '缺少必要参数：username 和 password'
            }, 400);
        }

        const validTypes = ['all', 'home', 'sports', 'daily'];
        if (!validTypes.includes(clockin_type)) {
            return jsonResponse({
                success: false,
                error: `无效的打卡类型：${clockin_type}，支持的类型：${validTypes.join(', ')}`
            }, 400);
        }

        logger.info(`开始处理用户 ${username} 的 ${clockin_type} 打卡请求`);

        // 获取登录 token（带重试和超时控制）
        const loginResult = await getLoginToken({ username, password }, 3, env);

        // 检查登录结果
        if (!loginResult || typeof loginResult.json !== 'function') {
            return jsonResponse({
                success: false,
                username,
                error: '登录失败：无法连接到服务器',
                details: loginResult
            }, 500);
        }

        const loginData = await loginResult.json().catch((e) => {
            logger.error('解析登录响应失败:', e);
            return { error: e.message };
        });

        if (!loginData.access_token) {
            return jsonResponse({
                success: false,
                username,
                error: '登录失败：无法获取 access_token',
                details: loginData
            }, 401);
        }

        const accessToken = loginData.access_token;
        logger.info(`用户 ${username} 登录成功`);

        // 构造环境变量（用于传递自定义参数）
        const clockinEnv = {
            SPORTS_COMMENT: options.sports_comment || env.SPORTS_COMMENT || '特色',
            DAILY_COMMENT: options.daily_comment || env.DAILY_COMMENT || '今日学习内容总结，收获满满！',
            SPORTS_IMAGE_URL: options.sports_image_url || null  // 如果admin-worker提供了图片URL
        };

        // 执行打卡（带 30s 外层超时控制；超时后中止后续步骤，并按子结果计算整体成功）
        const overallTimeoutMs = 30000;
        const abortController = new AbortController();
        let timedOut = false;
        const overallTimeoutId = setTimeout(() => {
            timedOut = true;
            abortController.abort();
            logger.warn(`打卡整体超过 ${overallTimeoutMs}ms，中止后续步骤`);
        }, overallTimeoutMs);

        let results;
        try {
            results = await performClockIn(accessToken, clockinEnv, clockin_type, abortController.signal);
        } catch (e) {
            logger.error('打卡执行异常:', e);
            results = {
                home: { success: false, message: `打卡异常: ${e.message}`, data: null },
                sports: { success: false, message: `打卡异常: ${e.message}`, data: null },
                daily: { success: false, message: `打卡异常: ${e.message}`, data: null }
            };
        } finally {
            clearTimeout(overallTimeoutId);
        }

        // 整体成功 = 至少一个子任务成功（不再硬编码 success:true）
        const anySuccess = Object.values(results).some(r => r && r.success);

        // 返回结果
        return jsonResponse({
            success: anySuccess,
            username,
            clockin_type,
            timestamp: new Date().toISOString(),
            results,
            timed_out: timedOut
        });

    } catch (error) {
        logger.error('打卡处理异常:', error);
        return jsonResponse({
            success: false,
            error: error.message
        }, 500);
    }
}

/**
 * 执行打卡操作（每个步骤带超时控制）
 * @param signal 可选的外层 AbortSignal，用于在整体超时后中止后续步骤
 */
async function performClockIn(accessToken, env, clockinType, signal) {
    const results = {
        home: { success: false, message: '', data: null },
        sports: { success: false, message: '', data: null },
        daily: { success: false, message: '', data: null }
    };

    const delay = (ms) => new Promise(resolve => setTimeout(resolve, ms));
    const aborted = () => signal?.aborted;

    try {
        // 首页签到（超时10秒）
        if (clockinType === 'all' || clockinType === 'home') {
            if (aborted()) {
                logger.warn('首页签到前已被外层超时中止');
            } else {
                logger.debug('开始首页签到...');
                try {
                    results.home = await raceWithTimeout(clockInHome(accessToken), 10000, '首页签到超时');
                } catch (e) {
                    results.home = { success: false, message: `首页签到异常: ${e.message}`, data: null };
                    logger.error('首页签到失败:', e);
                }
                if (clockinType === 'all' && !aborted()) {
                    logger.debug('首页签到完成，等待2秒后执行运动打卡...');
                    await delay(2000);
                }
            }
        }

        // 运动打卡（超时25秒，带重试机制）
        if ((clockinType === 'all' || clockinType === 'sports') && !aborted()) {
            logger.debug('开始运动打卡...');
            // 给定一个默认失败对象，确保 results.sports 永不为 undefined
            let sportsResult = { success: false, message: '运动打卡未执行', data: null };
            const maxRetries = 1; // 重试次数（总尝试 = maxRetries + 1）
            let attempt = 0;
            // 循环保证终止：成功 -> break；达到最大重试 -> break；被中止 -> break
            while (true) {
                if (aborted()) {
                    sportsResult = { success: false, message: '运动打卡被中止', data: null };
                    break;
                }
                try {
                    sportsResult = await raceWithTimeout(clockInSports(accessToken, env), 25000, '运动打卡超时');
                    break; // 成功，退出
                } catch (e) {
                    if (attempt < maxRetries) {
                        logger.warn(`运动打卡失败，1500ms 后重试 (${attempt + 1}/${maxRetries})...`);
                        await delay(1500);
                        attempt++;
                        continue; // 再次尝试
                    }
                    // 达到最大重试次数：记录最终失败并退出（必须 break，否则死循环）
                    sportsResult = { success: false, message: `运动打卡异常: ${e.message}`, data: null };
                    logger.error('运动打卡失败:', e);
                    break;
                }
            }
            results.sports = sportsResult;

            if (clockinType === 'all' && !aborted()) {
                logger.debug('运动打卡完成，等待2秒后执行日精进打卡...');
                await delay(2000);
            }
        }

        // 日精进打卡（超时8秒）
        if ((clockinType === 'all' || clockinType === 'daily') && !aborted()) {
            logger.debug('开始日精进打卡...');
            try {
                results.daily = await raceWithTimeout(clockInDaily(accessToken, env), 8000, '日精进打卡超时');
            } catch (e) {
                results.daily = { success: false, message: `日精进打卡异常: ${e.message}`, data: null };
                logger.error('日精进打卡失败:', e);
            }
        }
    } catch (error) {
        logger.error('打卡过程中发生错误:', error);
    }

    return results;
}

/**
 * 返回 JSON 响应
 */
function jsonResponse(data, status = 200) {
    return new Response(JSON.stringify(data, null, 2), {
        status,
        headers: {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
        },
    });
}
