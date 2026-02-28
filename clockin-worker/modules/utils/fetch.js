/**
 * 网络请求工具模块
 * 提供带超时和重试机制的 fetch 封装
 */

/**
 * 延迟函数
 */
function delay(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

/**
 * 带超时的 fetch 请求
 * @param {string} url - 请求URL
 * @param {Object} options - fetch 选项
 * @param {number} timeout - 超时时间（毫秒），默认 10000ms
 * @returns {Promise<Response>}
 */
export async function fetchWithTimeout(url, options = {}, timeout = 10000) {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeout);

    try {
        const response = await fetch(url, {
            ...options,
            signal: controller.signal
        });
        clearTimeout(timeoutId);
        return response;
    } catch (error) {
        clearTimeout(timeoutId);
        if (error.name === 'AbortError') {
            throw new Error(`请求超时 (${timeout}ms)`);
        }
        throw error;
    }
}

/**
 * 带重试和超时的 fetch 请求
 * @param {string} url - 请求URL
 * @param {Object} options - fetch 选项
 * @param {Object} retryOptions - 重试选项
 * @param {number} retryOptions.maxRetries - 最大重试次数，默认 2
 * @param {number} retryOptions.timeout - 超时时间（毫秒），默认 10000
 * @param {number} retryOptions.initialDelay - 初始重试延迟（毫秒），默认 1000
 * @param {boolean} retryOptions.retryOnTimeout - 是否在超时时重试，默认 true
 * @param {boolean} retryOptions.retryOn5xx - 是否在 5xx 错误时重试，默认 true
 * @returns {Promise<Response>}
 */
export async function fetchWithRetry(url, options = {}, retryOptions = {}) {
    const {
        maxRetries = 2,
        timeout = 10000,
        initialDelay = 1000,
        retryOnTimeout = true,
        retryOn5xx = true
    } = retryOptions;

    let lastError;

    for (let attempt = 0; attempt <= maxRetries; attempt++) {
        try {
            if (attempt > 0) {
                const delayTime = initialDelay * attempt;
                console.log(`[重试] 第 ${attempt} 次尝试: ${url}，延迟 ${delayTime}ms`);
                await delay(delayTime);
            }

            const response = await fetchWithTimeout(url, options, timeout);

            if (retryOn5xx && response.status >= 500 && attempt < maxRetries) {
                console.log(`[重试] 服务器错误 ${response.status}，将重试...`);
                continue;
            }

            return response;

        } catch (error) {
            lastError = error;
            console.error(`[重试] 第 ${attempt + 1} 次尝试失败:`, error.message);

            const shouldRetry = 
                (retryOnTimeout && error.message.includes('超时')) ||
                (retryOn5xx && error.message.includes('5xx'));

            if (shouldRetry && attempt < maxRetries) {
                console.log(`[重试] 将在 ${initialDelay * (attempt + 1)}ms 后重试...`);
                continue;
            }

            break;
        }
    }

    throw lastError || new Error('请求失败');
}

/**
 * 带超时的 POST 请求（JSON）
 * @param {string} url - 请求URL
 * @param {Object} data - 请求体数据
 * @param {Object} headers - 请求头
 * @param {number} timeout - 超时时间（毫秒）
 * @returns {Promise<Response>}
 */
export async function postJson(url, data, headers = {}, timeout = 10000) {
    return fetchWithTimeout(url, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            ...headers
        },
        body: JSON.stringify(data)
    }, timeout);
}

/**
 * 带超时的 POST 请求（表单）
 * @param {string} url - 请求URL
 * @param {URLSearchParams} data - 表单数据
 * @param {Object} headers - 请求头
 * @param {number} timeout - 超时时间（毫秒）
 * @returns {Promise<Response>}
 */
export async function postForm(url, data, headers = {}, timeout = 10000) {
    return fetchWithTimeout(url, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
            ...headers
        },
        body: data.toString()
    }, timeout);
}

/**
 * 带超时的 GET 请求
 * @param {string} url - 请求URL
 * @param {Object} headers - 请求头
 * @param {number} timeout - 超时时间（毫秒）
 * @returns {Promise<Response>}
 */
export async function get(url, headers = {}, timeout = 10000) {
    return fetchWithTimeout(url, {
        method: 'GET',
        headers
    }, timeout);
}
