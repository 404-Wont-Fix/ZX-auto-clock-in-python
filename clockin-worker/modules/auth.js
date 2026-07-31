/**
 * 登录认证模块
 */

import { fetchWithRetry, postForm, get } from './utils/fetch.js';

/**
 * 延迟函数
 */
function delay(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

// 日志开关（与 worker.js 一致，由 env.ENABLE_LOGGING 控制）
let authEnableLogging = false;

/**
 * 简单日志工具（与worker.js保持一致的日志风格）
 */
const authLogger = {
    info: (...args) => { if (authEnableLogging) console.log(`[AUTH INFO] ${new Date().toISOString()}`, ...args); },
    warn: (...args) => { if (authEnableLogging) console.warn(`[AUTH WARN] ${new Date().toISOString()}`, ...args); },
    error: (...args) => { if (authEnableLogging) console.error(`[AUTH ERROR] ${new Date().toISOString()}`, ...args); },
    debug: (...args) => { if (authEnableLogging) console.log(`[AUTH DEBUG] ${new Date().toISOString()}`, ...args); }
};

/**
 * 获取登录 token（带重试机制）
 * @param credentials {username, password}
 * @param maxRetries 最大重试次数
 * @param env worker 环境变量（用于读取 CLIENT_ID / CLIENT_SECRET / ENABLE_LOGGING）
 */
export async function getLoginToken(credentials, maxRetries = 3, env = {}) {
    const { username, password } = credentials;
    authEnableLogging = env?.ENABLE_LOGGING === 'true';

    // 上游平台凭据优先从 worker secret 读取，未配置时回退到内置值并告警
    // 建议通过 `wrangler secret put CLIENT_ID` / `wrangler secret put CLIENT_SECRET` 配置
    const clientId = env?.CLIENT_ID || '43215cdff2d5407f8af074d2d7e589ee';
    const clientSecret = env?.CLIENT_SECRET;
    if (!clientSecret) {
        authLogger.warn('未配置 CLIENT_SECRET，使用内置回退值；建议通过 wrangler secret put CLIENT_SECRET 配置');
    }
    const clientSecretValue = clientSecret || 'DBqEL1YfBmKgT9O491J1YnYoq84lYtB/LwMabAS2JEqa8I+r3z1VrDqymjisqJn3';

    for (let attempt = 0; attempt < maxRetries; attempt++) {
        try {
            if (attempt > 0) {
                authLogger.info(`第 ${attempt + 1} 次尝试: ${username}`);
                await delay(1000 * attempt); // 递增延迟：1s, 2s, 3s
            }

            // 获取租户信息（带超时和重试）
            let tenantId = '32'; // 默认租户ID

            try {
                const tenantResponse = await get(
                    'https://ai.cqzuxia.com/api/Tenants/GetAllValidTenant?',
                    {
                        'Accept': 'application/json, text/plain, */*',
                        'Referer': 'https://ai.cqzuxia.com/',
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36'
                    },
                    5000 // 5秒超时
                );

                if (tenantResponse.ok) {
                    const responseText = await tenantResponse.text();
                    if (responseText.trim()) {
                        try {
                            const tenantData = JSON.parse(responseText);
                            tenantId = tenantData[0]?.id || '32';
                        } catch (e) {
                            authLogger.warn(`解析租户信息失败: ${e.message}, 使用默认租户ID`);
                        }
                    }
                } else {
                    authLogger.warn(`获取租户信息失败: ${tenantResponse.status}, 使用默认租户ID`);
                }
            } catch (tenantError) {
                authLogger.warn(`获取租户信息异常: ${tenantError.message}, 使用默认租户ID`);
            }

            // 构建登录请求
            const loginData = new URLSearchParams();
            loginData.append('username', username);
            loginData.append('password', password);
            loginData.append('code', '2341');
            loginData.append('vid', '');
            loginData.append('client_id', clientId);
            loginData.append('client_secret', clientSecretValue);
            loginData.append('grant_type', 'password');
            loginData.append('tenant_id', tenantId);

            // 发送登录请求（带超时和重试）
            const response = await postForm(
                'https://ai.cqzuxia.com/connect/token',
                loginData,
                {
                    'Accept': 'application/json, text/plain, */*',
                    'Referer': 'https://ai.cqzuxia.com/',
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36'
                },
                10000 // 10秒超时
            );

            // 检查响应状态
            if (!response.ok) {
                const errorText = await response.text();
                authLogger.error(`请求失败: ${response.status}, ${errorText}`);

                // 如果是 5xx 错误且还有重试次数，则重试
                if (response.status >= 500 && attempt < maxRetries - 1) {
                    authLogger.info('服务器错误，将重试...');
                    continue;
                }

                return {
                    ok: false,
                    status: response.status,
                    statusText: response.statusText,
                    json: async () => ({
                        error: `HTTP ${response.status}`,
                        error_description: errorText || '登录失败'
                    })
                };
            }

            authLogger.info(`登录成功: ${username}`);
            return response;

        } catch (error) {
            authLogger.error(`第 ${attempt + 1} 次尝试失败:`, error.message);

            // 如果是最后一次尝试，返回错误
            if (attempt === maxRetries - 1) {
                return {
                    ok: false,
                    status: 500,
                    statusText: 'Login Failed',
                    json: async () => ({
                        error: error.message,
                        error_description: '获取登录token失败'
                    })
                };
            }

            // 否则继续重试
            authLogger.info(`将在 ${1000 * (attempt + 1)}ms 后重试...`);
        }
    }
}
