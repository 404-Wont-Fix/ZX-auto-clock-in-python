/**
 * HTML 页面导出模块
 * 提供各个页面的 HTML 内容
 */

// 导入分离后的静态文件
import indexHtmlSource from './pages/index.html';
import loginHtmlSource from './pages/login.html';
import notFoundHtmlSource from './pages/404.html';

// 获取文件内容（处理 default 导出）
const indexHtml = indexHtmlSource.default || indexHtmlSource;
const loginHtml = loginHtmlSource.default || loginHtmlSource;
const notFoundHtml = notFoundHtmlSource.default || notFoundHtmlSource;

/**
 * 获取管理面板主页
 */
export function getHtmlPage() {
    return indexHtml;
}

/**
 * 获取登录页面
 */
export function getLoginPage() {
    return loginHtml;
}

/**
 * 获取 404 页面
 */
export function getNginx404Page() {
    return notFoundHtml;
}
