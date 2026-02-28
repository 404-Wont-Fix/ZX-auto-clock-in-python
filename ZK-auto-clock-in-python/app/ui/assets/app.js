/**
 * 主应用脚本
 * ZK 多用户自动打卡系统
 */

let currentUsers = [];
let isClockinRunning = false; // 防止重复打卡标志

/**
 * 统一的 API 请求处理函数
 * 自动处理 401 未授权错误，跳转到登录页面
 */
async function apiRequest(url, options = {}) {
    // 获取 token
    const token = localStorage.getItem('auth_token');

    const defaultOptions = {
        credentials: 'include',
        headers: {
            'Content-Type': 'application/json'
        }
    };

    // 如果有 token，添加到 Authorization header
    if (token) {
        defaultOptions.headers['Authorization'] = `Bearer ${token}`;
    }

    const mergedOptions = { ...defaultOptions, ...options };

    const response = await fetch(url, mergedOptions);

    // 检查 401 未授权
    if (response.status === 401) {
        showToast('登录已过期，请重新登录', 'error');
        setTimeout(() => {
            window.location.href = window.ADMIN_PATH || '/admin';
        }, 1500);
        throw new Error('Unauthorized');
    }

    return response;
}

// 初始化
document.addEventListener('DOMContentLoaded', () => {
    // 检查是否已登录
    const token = localStorage.getItem('auth_token');
    if (!token) {
        console.log('[认证] 未找到 token，跳转到登录页');
        window.location.href = window.ADMIN_PATH || '/admin';
        return;
    }

    loadUsers();
    loadStats();
    loadRecords();
    loadActiveTasks();

    // 定时刷新活动任务
    setInterval(loadActiveTasks, 3000);  // 每3秒刷新一次

    // 监听定时任务配置变化
    const scheduleTimeInput = document.getElementById('configScheduleTime');
    const scheduleTimezoneSelect = document.getElementById('configScheduleTimezone');
    const scheduleEnabledCheckbox = document.getElementById('configScheduleEnabled');

    if (scheduleTimeInput) {
        scheduleTimeInput.addEventListener('change', updateTimePreview);
        scheduleTimeInput.addEventListener('input', updateTimePreview);
    }

    if (scheduleTimezoneSelect) {
        scheduleTimezoneSelect.addEventListener('change', updateTimePreview);
    }

    if (scheduleEnabledCheckbox) {
        scheduleEnabledCheckbox.addEventListener('change', (e) => {
            updateScheduleConfigVisibility(e.target.checked);
        });
    }
});

// 加载用户列表
async function loadUsers() {
    console.log('[数据加载] 开始加载用户列表');
    try {
        const response = await apiRequest('/api/users');
        const data = await response.json();
        currentUsers = data.data;
        console.log('[数据加载] 用户列表加载完成，用户数:', currentUsers.length);
        renderUsers(currentUsers);
    } catch (error) {
        if (error.message !== 'Unauthorized') {
            console.error('[数据加载] 用户列表加载失败:', error);
            showToast('加载用户列表失败', 'error');
        }
    }
}

// 渲染用户列表
function renderUsers(users) {
    const container = document.getElementById('userList');
    if (users.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <div class="empty-icon">👥</div>
                <div>暂无用户，点击"添加用户"按钮添加</div>
            </div>
        `;
        return;
    }

    container.innerHTML = users.map(user => `
        <div class="user-card">
            <div class="user-card-header">
                <div class="user-info">
                    <div class="user-avatar">👤</div>
                    <div>
                        <div class="user-name">${escapeHtml(user.username)}</div>
                        ${user.nickname ? `<div class="user-nickname">📌 ${escapeHtml(user.nickname)}</div>` : ''}
                        <div class="user-status">
                            <span class="status-dot ${user.enabled ? 'enabled' : 'disabled'}"></span>
                            <span>${user.enabled ? '已启用' : '已禁用'}</span>
                        </div>
                    </div>
                </div>
                <div class="user-actions">
                    <button class="btn btn-sm" onclick="triggerUserClockin('${user.id}', event)">▶ 打卡</button>
                    <button class="btn btn-sm" onclick="editUser('${user.id}')">编辑</button>
                    <button class="btn btn-sm" onclick="toggleUser('${user.id}')">${user.enabled ? '禁用' : '启用'}</button>
                    <button class="btn btn-sm btn-danger" onclick="deleteUser('${user.id}')">删除</button>
                </div>
            </div>
            <div class="user-meta">
                <div class="meta-item">
                    <span class="meta-label">上次打卡</span>
                    <span>${user.last_clockin ? formatDate(user.last_clockin) : '从未打卡'}</span>
                </div>
                <div class="meta-item">
                    <span class="meta-label">累计次数</span>
                    <span>${user.clockin_count || 0} 次</span>
                </div>
                <div class="meta-item">
                    <span class="meta-label">运动备注</span>
                    <span>${getSportsCommentDisplay(user)}</span>
                </div>
                <div class="meta-item">
                    <span class="meta-label">每日备注</span>
                    <span>${getDailyCommentDisplay(user)}</span>
                </div>
            </div>
        </div>
    `).join('');
}

// 获取每日备注显示文本
function getDailyCommentDisplay(user) {
    const type = user.daily_comment_type || 'default';
    const displayMap = {
        'default': '默认文案',
        'custom': '自定义',
        'api': 'API 接口'
    };
    let display = displayMap[type] || '默认';

    if (type === 'custom' && user.custom_daily_comment) {
        const preview = user.custom_daily_comment.substring(0, 15);
        display += ' - ' + preview + (user.custom_daily_comment.length > 15 ? '...' : '');
    } else if (type === 'api' && user.daily_comment_api) {
        display += ' - ' + formatApiTypeName(user.daily_comment_api);
    }

    return display;
}

// 将 API 类型代码格式化为可读名称
function formatApiTypeName(apiType) {
    // 根据API类型前缀判断供应商
    if (apiType.startsWith('cenguigui_')) {
        return '随机一言';
    }

    if (apiType.startsWith('yuanmeng_')) {
        return '远梦API';
    }

    if (apiType.startsWith('klapi_')) {
        return 'KLapi';
    }

    if (apiType.startsWith('hitokoto_')) {
        return '一言';
    }

    // 今日诗词（显示分类）
    if (apiType.startsWith('poetry_')) {
        // 移除 'poetry_' 前缀
        const remaining = apiType.replace('poetry_', '');

        // 如果没有子分类（只有主分类）
        if (!remaining.includes('_')) {
            const mainCategories = {
                'all': '全部',
                'shuqing': '抒情',
                'siji': '四季',
                'shanshui': '山水',
                'tianqi': '天气',
                'renwu': '人物',
                'rensheng': '人生',
                'shenghuo': '生活',
                'jieri': '节日',
                'dongwu': '动物',
                'zhiwu': '植物',
                'shiwu': '食物'
            };
            return '今日诗词（' + (mainCategories[remaining] || '全部') + '）';
        }

        // 有子分类，格式如 shuqing_aiqing
        const parts = remaining.split('_');
        const mainCategory = parts[0];
        const subCategory = parts[1];

        const mainNames = {
            'shuqing': '抒情',
            'siji': '四季',
            'shanshui': '山水',
            'tianqi': '天气',
            'renwu': '人物',
            'rensheng': '人生',
            'shenghuo': '生活',
            'jieri': '节日',
            'dongwu': '动物',
            'zhiwu': '植物',
            'shiwu': '食物'
        };

        const subNames = {
            // 抒情
            'aiqing': '爱情',
            'youqing': '友情',
            'libie': '离别',
            'sinian': '思念',
            'sixiang': '思乡',
            'shanggan': '伤感',
            'gudu': '孤独',
            'guiyuan': '闺怨',
            'daowang': '悼亡',
            'huaigu': '怀古',
            'aiguo': '爱国',
            'ganen': '感恩',
            // 四季
            'chuntian': '春天',
            'xiatian': '夏天',
            'qiutian': '秋天',
            'dongtian': '冬天',
            // 山水
            'lushan': '庐山',
            'taishan': '泰山',
            'jianghe': '江河',
            'changjiang': '长江',
            'huanghe': '黄河',
            'xihu': '西湖',
            'pubu': '瀑布',
            // 天气
            'xiefeng': '写风',
            'xieyun': '写云',
            'xieyu': '写雨',
            'xiexue': '写雪',
            'caihong': '彩虹',
            'taiyang': '太阳',
            'yueliang': '月亮',
            'xingxing': '星星',
            // 人物
            'nvzi': '女子',
            'fuqin': '父亲',
            'muqin': '母亲',
            'laoshi': '老师',
            'ertong': '儿童',
            // 人生
            'lizhi': '励志',
            'zheli': '哲理',
            'qingchun': '青春',
            'shiguang': '时光',
            'mengxiang': '梦想',
            'dushu': '读书',
            'zhanzheng': '战争',
            // 生活
            'xiangcun': '乡村',
            'tianyuan': '田园',
            'biansai': '边塞',
            'xieqiao': '写桥',
            // 节日
            'chunjie': '春节',
            'yuanxiaojie': '元宵节',
            'hanshijie': '寒食节',
            'qingmingjie': '清明节',
            'duanwujie': '端午节',
            'qixijie': '七夕节',
            'zhongqiujie': '中秋节',
            'chongyangjie': '重阳节',
            // 动物
            'xieniao': '写鸟',
            'xiema': '写马',
            'xiemao': '写猫',
            // 植物
            'meihua': '梅花',
            'lihua': '梨花',
            'taohua': '桃花',
            'hehua': '荷花',
            'juhua': '菊花',
            'liushu': '柳树',
            'yezi': '叶子',
            'zhuzi': '竹子',
            // 食物
            'xiejiu': '写酒',
            'xiecha': '写茶',
            'lizhi': '荔枝'
        };

        const mainName = mainNames[mainCategory] || mainCategory;
        const subName = subNames[subCategory] || subCategory;

        return '今日诗词（' + mainName + '·' + subName + '）';
    }

    // 默认：今日诗词
    return '今日诗词';
}

// 获取运动备注显示文本
function getSportsCommentDisplay(user) {
    const type = user.sports_comment_type || 'default';
    const displayMap = {
        'default': '默认文案',
        'custom': '自定义',
        'api': 'API 接口'
    };
    let display = displayMap[type] || '默认';

    if (type === 'custom' && user.sports_custom_comment) {
        const preview = user.sports_custom_comment.substring(0, 15);
        display += ' - ' + preview + (user.sports_custom_comment.length > 15 ? '...' : '');
    } else if (type === 'api' && user.sports_comment_api) {
        display += ' - ' + formatApiTypeName(user.sports_comment_api);
    }

    return display;
}

// 每日备注类型切换事件
function onDailyCommentTypeChange() {
    const type = document.getElementById('daily_comment_type').value;
    const customGroup = document.getElementById('custom_content_group');
    const apiGroup = document.getElementById('api_select_group');
    const apiCategoryGroup = document.getElementById('api_category_group');

    // 隐藏所有条件字段
    customGroup.style.display = 'none';
    apiGroup.style.display = 'none';
    apiCategoryGroup.style.display = 'none';

    // 根据选择显示对应字段
    if (type === 'custom') {
        customGroup.style.display = 'block';
    } else if (type === 'api') {
        apiGroup.style.display = 'block';
        // 触发供应商切换以显示/隐藏分类选择
        onApiProviderChange();
    }
}

// 运动备注类型切换事件
function onSportsCommentTypeChange() {
    const type = document.getElementById('sports_comment_type').value;
    const customGroup = document.getElementById('sports_custom_group');
    const apiGroup = document.getElementById('sports_api_group');
    const apiCategoryGroup = document.getElementById('sports_api_category_group');

    // 隐藏所有条件字段
    customGroup.style.display = 'none';
    apiGroup.style.display = 'none';
    apiCategoryGroup.style.display = 'none';

    // 根据选择显示对应字段
    if (type === 'custom') {
        customGroup.style.display = 'block';
    } else if (type === 'api') {
        apiGroup.style.display = 'block';
        // 触发供应商切换以显示/隐藏分类选择
        onSportsApiProviderChange();
    }
}

// API供应商切换事件
function onApiProviderChange() {
    const provider = document.getElementById('api_provider').value;
    const apiCategoryGroup = document.getElementById('api_category_group');

    // 只有今日诗词显示分类选择
    if (provider === 'jinrishici') {
        apiCategoryGroup.style.display = 'block';
    } else {
        apiCategoryGroup.style.display = 'none';
    }
}

// 运动备注API供应商切换事件
function onSportsApiProviderChange() {
    const provider = document.getElementById('sports_api_provider').value;
    const apiCategoryGroup = document.getElementById('sports_api_category_group');

    // 只有今日诗词显示分类选择
    if (provider === 'jinrishici') {
        apiCategoryGroup.style.display = 'block';
    } else {
        apiCategoryGroup.style.display = 'none';
    }
}

// 获取当前选择的API类型值
function getCurrentApiType() {
    const provider = document.getElementById('api_provider').value;

    // 今日诗词需要从分类选择框获取值
    if (provider === 'jinrishici') {
        const select = document.getElementById('daily_comment_api_jinrishici');
        return select ? select.value : 'poetry_all';
    }

    // 其他API使用默认值
    const apiTypes = {
        'cenguigui': 'cenguigui_default',
        'hitokoto': 'hitokoto_all',
        'yuanmeng': 'yuanmeng_default',
        'klapi': 'klapi_default'
    };
    return apiTypes[provider] || 'poetry_all';
}

// 获取当前选择的运动备注API类型值
function getSportsApiType() {
    const provider = document.getElementById('sports_api_provider').value;

    // 今日诗词需要从分类选择框获取值
    if (provider === 'jinrishici') {
        const select = document.getElementById('sports_api_jinrishici');
        return select ? select.value : 'poetry_all';
    }

    // 其他API使用默认值
    const apiTypes = {
        'cenguigui': 'cenguigui_default',
        'hitokoto': 'hitokoto_all',
        'yuanmeng': 'yuanmeng_default',
        'klapi': 'klapi_default'
    };
    return apiTypes[provider] || 'poetry_all';
}

// 运动图片类型切换事件
function onSportsImageTypeChange() {
    const type = document.getElementById('sports_image_type').value;
    const apiGroup = document.getElementById('sports_image_api_group');

    // 隐藏所有条件字段
    apiGroup.style.display = 'none';
    document.getElementById('sports_image_category_group').style.display = 'none';

    // 根据选择显示对应字段
    if (type === 'api') {
        apiGroup.style.display = 'block';
        // 如果选择了API，触发供应商切换以更新分类显示
        onSportsImageProviderChange();
    }
}

// 运动图片API供应商切换事件
function onSportsImageProviderChange() {
    const provider = document.getElementById('sports_image_provider').value;
    const categoryGroup = document.getElementById('sports_image_category_group');

    // 根据供应商决定是否显示分类选择
    // 只有次元API支持分类选择
    if (provider === 'cimuapi') {
        categoryGroup.style.display = 'block';
    } else {
        categoryGroup.style.display = 'none';
    }
}

// 获取当前选择的运动图片供应商配置
function getSportsImageProvider() {
    const type = document.getElementById('sports_image_type').value;
    const provider = document.getElementById('sports_image_provider').value;

    if (type === 'default') {
        return 'bing';
    }

    return provider;
}

// 加载统计数据
async function loadStats() {
    console.log('[数据加载] 开始加载统计数据');
    try {
        const response = await apiRequest('/api/clockin/stats');
        const data = await response.json();
        const stats = data.data;

        document.getElementById('statTotalUsers').textContent = stats.total_users || 0;
        document.getElementById('statEnabledUsers').textContent = stats.enabled_users || 0;

        // 获取今日统计
        const today = new Date().toISOString().split('T')[0];
        const recordsResponse = await apiRequest(`/api/clockin/results?date=${today}`);
        const recordsData = await recordsResponse.json();
        const summary = recordsData.data.summary;

        if (summary) {
            document.getElementById('statTodaySuccess').textContent = summary.success_count || 0;
            document.getElementById('statTodayFailure').textContent = summary.failure_count || 0;
        } else {
            document.getElementById('statTodaySuccess').textContent = '-';
            document.getElementById('statTodayFailure').textContent = '-';
        }
        console.log('[数据加载] 统计数据加载完成');
    } catch (error) {
        if (error.message !== 'Unauthorized') {
            console.error('[数据加载] 加载统计失败:', error);
        }
    }
}

// 加载活动任务
async function loadActiveTasks() {
    console.log('[数据加载] 开始加载活动任务');
    try {
        const response = await apiRequest('/api/clockin/active-tasks');
        const data = await response.json();
        const tasks = data.data.active_tasks || [];
        const count = data.data.count || 0;

        const section = document.getElementById('activeTasksSection');
        const list = document.getElementById('activeTasksList');
        const countBadge = document.getElementById('activeTaskCount');

        // 更新计数
        countBadge.textContent = count;

        // 显示/隐藏部分
        if (count > 0) {
            section.style.display = 'block';
        } else {
            section.style.display = 'none';
            return;
        }

        // 渲染任务列表
        if (tasks.length === 0) {
            list.innerHTML = `
                <div class="active-task-empty">
                    暂无活动任务
                </div>
            `;
        } else {
            list.innerHTML = tasks.map(task => `
                <div class="active-task-card">
                    <div class="active-task-info">
                        <div class="active-task-user">
                            <div class="active-task-username">${escapeHtml(task.username)}</div>
                            ${task.nickname && task.nickname !== task.username ? `<div class="active-task-nickname">${escapeHtml(task.nickname)}</div>` : ''}
                        </div>
                        <div class="active-task-details">
                            ${task.worker_api_name ? `<span class="active-task-api">🔗 ${escapeHtml(task.worker_api_name)}</span>` : '<span class="active-task-api">🔗 后备API</span>'}
                            <span class="active-task-time">⏱ ${task.elapsed_seconds}秒</span>
                        </div>
                    </div>
                    <div class="active-task-status">
                        <div class="active-task-spinner"></div>
                        <span style="font-size: 12px; color: var(--accent-color);">执行中</span>
                    </div>
                </div>
            `).join('');
        }

        console.log('[数据加载] 活动任务加载完成:', count);
    } catch (error) {
        if (error.message !== 'Unauthorized') {
            console.error('[数据加载] 加载活动任务失败:', error);
        }
    }
}

// 加载打卡记录（支持单日或一周）
let currentRecordRange = 'day';  // 'day' 或 'week'

async function loadRecords() {
    console.log('[数据加载] 开始加载打卡记录, 范围:', currentRecordRange);
    try {
        const range = currentRecordRange;
        const url = range === 'week'
            ? `/api/clockin/results?range=week`
            : `/api/clockin/results?date=${new Date().toISOString().split('T')[0]}`;

        const response = await apiRequest(url);
        const data = await response.json();
        const container = document.getElementById('recordList');

        if (range === 'week') {
            // 一周记录视图
            renderWeekRecords(container, data.data);
        } else {
            // 单日记录视图
            const results = data.data.results || [];
            if (results.length === 0) {
                container.innerHTML = `
                    <div class="empty-state">
                        <div class="empty-icon">📊</div>
                        <div>今日暂无打卡记录</div>
                    </div>
                `;
                return;
            }
            renderDayRecords(container, results);
        }
        console.log('[数据加载] 打卡记录加载完成');
    } catch (error) {
        if (error.message !== 'Unauthorized') {
            console.error('[数据加载] 加载记录失败:', error);
        }
    }
}

// 渲染单日打卡记录
function renderDayRecords(container, results) {
    if (!results || results.length === 0) {
        container.innerHTML = `
            <div class="no-records-tip">
                <div class="no-records-icon">📋</div>
                <div class="no-records-text">暂无打卡记录</div>
            </div>
        `;
        return;
    }

    container.innerHTML = results.map((result, index) => {
        // 处理详细信息 - 支持 details 和 details_json 两种格式
        let details = null;
        if (result.details && typeof result.details === 'object') {
            details = result.details;
        } else if (result.details_json && result.details_json !== 'null' && result.details_json !== 'undefined') {
            try {
                details = JSON.parse(result.details_json);
            } catch (e) {
                console.error('解析 details_json 失败:', e, result.details_json);
            }
        }

        const isSuccess = result.success;
        const hasError = result.error;
        
        // 格式化时间
        const timeStr = formatTime(result.timestamp);
        const isScheduled = result.triggered_by === 'scheduled';
        const durationStr = result.duration_ms ? `${Math.round(result.duration_ms / 1000)}s` : null;

        return `
        <div class="record-card ${isSuccess ? 'success' : 'failure'}" data-record-id="${result.id}" onclick="toggleRecordCard(this)">
            <div class="record-card-header">
                <div class="record-card-header-top">
                    <div class="record-user-info">
                        <div class="record-username-row">
                            <span class="record-username">${escapeHtml(result.username)}</span>
                            ${result.nickname ? `<span class="record-nickname-tag">📌 ${escapeHtml(result.nickname)}</span>` : ''}
                        </div>
                        <div class="record-meta-row">
                            <span class="record-meta-item">
                                <span>🕐</span>
                                <span class="record-time">${timeStr}</span>
                            </span>
                            ${durationStr ? `
                            <span class="record-meta-item record-duration-badge">
                                <span>⏱</span>
                                <span>${durationStr}</span>
                            </span>
                            ` : ''}
                            <span class="record-trigger-badge">
                                <span>${isScheduled ? '🤖' : '👤'}</span>
                                <span>${isScheduled ? '定时' : '手动'}</span>
                            </span>
                        </div>
                    </div>
                    
                    <div class="record-card-header-right">
                        <div class="record-status-badge ${isSuccess ? 'success' : 'failure'}">
                            <span class="status-icon">${isSuccess ? '✓' : '✗'}</span>
                            <span>${isSuccess ? '成功' : '失败'}</span>
                        </div>
                        <div class="record-expand-icon">▼</div>
                    </div>
                </div>
                
                ${details && typeof details === 'object' ? `
                <div class="record-types-grid">
                    ${renderRecordTypeItem('home', '首页签到', '🏠', details.home)}
                    ${renderRecordTypeItem('sports', '运动打卡', '🏃', details.sports)}
                    ${renderRecordTypeItem('daily', '每日进度', '📝', details.daily)}
                </div>
                ` : ''}
            </div>
            
            <div class="record-card-body">
                <div class="record-card-content">
                    
                    ${(result.sports_comment || result.daily_comment) ? `
                        <div class="record-comments-section">
                            ${result.sports_comment ? `
                            <div class="comment-row">
                                <span class="comment-type-label">🏃 运动</span>
                                <span class="comment-content" title="${escapeHtml(result.sports_comment)}">${escapeHtml(result.sports_comment)}</span>
                            </div>
                            ` : ''}
                            ${result.daily_comment ? `
                            <div class="comment-row">
                                <span class="comment-type-label">📝 每日</span>
                                <span class="comment-content ${result.daily_comment.length > 50 ? 'truncated' : ''}" title="${escapeHtml(result.daily_comment)}">${escapeHtml(result.daily_comment)}</span>
                            </div>
                            ` : ''}
                        </div>
                    ` : ''}
                    
                    ${hasError ? `
                        <div class="record-error-section">
                            <span class="record-error-icon">❌</span>
                            <span class="record-error-text" title="${escapeHtml(result.error)}">${escapeHtml(result.error)}</span>
                        </div>
                    ` : ''}
                </div>
            </div>
        </div>
    `}).join('');
}

// 渲染单个打卡类型项
function renderRecordTypeItem(key, name, icon, detail) {
    if (!detail) {
        return `
            <div class="record-type-item not-executed">
                <div class="record-type-header">
                    <span class="record-type-icon">${icon}</span>
                    <span>${name}</span>
                    <span class="record-type-status not-executed">未执行</span>
                </div>
            </div>
        `;
    }

    const isSuccess = detail.success;
    let message = '';
    
    if (!isSuccess) {
        message = detail.message || detail.msg || '';
        if (!message) {
            const dataMsg = detail.data?.msg || detail.data?.message || '';
            const code = detail.data?.statusCode || detail.data?.code || '';
            message = code ? `${dataMsg} (${code})` : dataMsg;
        }
    } else {
        message = detail.message || detail.msg || '完成';
    }

    const isLongMessage = message && message.length > 80;

    return `
        <div class="record-type-item ${isSuccess ? 'success' : 'failure'}">
            <div class="record-type-header">
                <span class="record-type-icon">${icon}</span>
                <span>${name}</span>
                <span class="record-type-status ${isSuccess ? 'success' : 'failure'}">${isSuccess ? '✓ 成功' : '✗ 失败'}</span>
            </div>
            ${message ? `
                <div class="record-type-message ${isLongMessage ? 'truncated' : ''}" title="${escapeHtml(message)}">
                    ${escapeHtml(message)}
                </div>
            ` : ''}
        </div>
    `;
}

// 切换卡片展开/收起状态
function toggleRecordCard(cardElement) {
    cardElement.classList.toggle('expanded');
}

// 渲染打卡结果（各类型状态）
function renderClockinResults(details) {
    if (!details || typeof details !== 'object') {
        return '<div class="no-details">暂无详情</div>';
    }

    const types = [
        { key: 'home', name: '首页签到', icon: '🏠' },
        { key: 'sports', name: '运动打卡', icon: '🏃' },
        { key: 'daily', name: '每日进度', icon: '📝' }
    ];

    return types.map(type => {
        const detail = details[type.key];

        // 如果没有这个类型的详情，显示未执行
        if (!detail) {
            return `
                <div class="clockin-result-item not-executed">
                    <span class="result-icon">${type.icon}</span>
                    <span class="result-name">${type.name}</span>
                    <span class="result-status">未执行</span>
                </div>
            `;
        }

        const isSuccess = detail.success;
        const statusClass = isSuccess ? 'success' : 'failure';
        const statusIcon = isSuccess ? '✓' : '✗';

        // 提取错误信息
        let message = '';
        if (!isSuccess) {
            // 优先显示 message/msg
            message = detail.message || detail.msg || '';

            // 如果没有 message，尝试从 data 中提取
            if (!message) {
                const dataMsg = detail.data?.msg || detail.data?.message || '';
                const code = detail.data?.statusCode || detail.data?.code || '';
                message = code ? `${dataMsg} (${code})` : dataMsg;
            }
        } else {
            // 成功时显示简短消息
            message = detail.message || detail.msg || '完成';
        }

        return `
            <div class="clockin-result-item ${statusClass}">
                <span class="result-icon">${statusIcon}</span>
                <span class="result-name">${type.icon} ${type.name}</span>
                ${message ? `<span class="result-message">${escapeHtml(message)}</span>` : ''}
            </div>
        `;
    }).join('');
}

// 渲染一周打卡记录
function renderWeekRecords(container, weekData) {
    if (!weekData.dates || weekData.dates.length === 0) {
        container.innerHTML = `
            <div class="no-records-tip">
                <div class="no-records-icon">📊</div>
                <div class="no-records-text">近 7 天暂无打卡记录</div>
            </div>
        `;
        return;
    }

    container.innerHTML = weekData.dates.map(dayData => {
        const summary = dayData.summary;
        const results = dayData.results || [];
        const dateObj = new Date(dayData.date);
        const dayName = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'][dateObj.getDay()];
        const isToday = dayData.date === new Date().toISOString().split('T')[0];

        return `
            <div class="week-day-item">
                <div class="week-day-header ${isToday ? 'today' : ''}">
                    <div>
                        <span class="week-day-date">${dayData.date}</span>
                        <span class="week-day-date"> ${dayName}</span>
                        ${isToday ? '<span class="today-badge">今天</span>' : ''}
                    </div>
                </div>
                ${summary ? `
                    <div class="week-day-summary">
                        <span class="summary-item">📊 总计：<strong>${summary.total_users}</strong> 用户</span>
                        <span class="summary-item summary-success">✓ 成功 ${summary.success_count}</span>
                        <span class="summary-item summary-failure">✗ 失败 ${summary.failure_count}</span>
                    </div>
                ` : ''}
                <div class="week-day-users">
                    ${results.map(result => `
                        <div class="week-user-item ${result.success ? 'success' : 'failure'}">
                            <div style="display: flex; flex-direction: column; gap: 2px;">
                                <span style="font-weight: 500;">${escapeHtml(result.username)}</span>
                                ${result.nickname ? `<span style="font-size: 11px; color: var(--text-secondary);">📌 ${escapeHtml(result.nickname)}</span>` : ''}
                            </div>
                            <span class="week-user-status">${result.success ? '✓' : '✗'}</span>
                        </div>
                    `).join('')}
                </div>
            </div>
        `;
    }).join('');
}

// 切换记录范围
function toggleRecordRange() {
    currentRecordRange = currentRecordRange === 'day' ? 'week' : 'day';
    const btnText = document.getElementById('rangeToggleText');
    if (btnText) {
        btnText.textContent = currentRecordRange === 'day' ? '📅 切换到一周视图' : '📅 切换到今日视图';
    }
    loadRecords();
}

// 获取备注来源文本
function getCommentSourceText(source) {
    const map = {
        'default': '默认',
        'custom': '自定义',
        'api': 'API接口'
    };
    return map[source] || '默认';
}

// 打开添加用户弹窗
function openAddUserModal() {
    document.getElementById('modalTitle').textContent = '添加用户';
    document.getElementById('userForm').reset();
    document.getElementById('userId').value = '';
    document.getElementById('nickname').value = '';
    document.getElementById('daily_comment_type').value = 'default';
    document.getElementById('custom_daily_comment').value = '';
    document.getElementById('api_provider').value = 'jinrishici';
    document.getElementById('daily_comment_api_jinrishici').value = 'poetry_all';
    document.getElementById('sports_comment_type').value = 'default';
    document.getElementById('sports_custom_comment').value = '';
    document.getElementById('sports_api_provider').value = 'jinrishici';
    document.getElementById('sports_api_jinrishici').value = 'poetry_all';
    document.getElementById('sports_image_type').value = 'default';
    document.getElementById('sports_image_provider').value = 'bing';
    document.getElementById('sports_image_category').value = 'random';
    document.getElementById('enabled').checked = true;
    // 触发显示/隐藏逻辑
    onDailyCommentTypeChange();
    onSportsCommentTypeChange();
    onSportsImageTypeChange();
    document.getElementById('userModal').classList.add('active');

    // 添加用户名输入监听器，自动填充密码为用户名后六位
    const usernameInput = document.getElementById('username');
    usernameInput.addEventListener('input', autoFillPassword);
}

// 编辑用户
function editUser(userId) {
    const user = currentUsers.find(u => u.id === userId);
    if (!user) return;

    console.log('[编辑用户] 用户数据:', user);

    // 移除自动填充密码的监听器（编辑模式不需要）
    const usernameInput = document.getElementById('username');
    usernameInput.removeEventListener('input', autoFillPassword);

    document.getElementById('modalTitle').textContent = '编辑用户';
    document.getElementById('userId').value = user.id;
    document.getElementById('username').value = user.username;
    document.getElementById('nickname').value = user.nickname || '';
    document.getElementById('password').value = user.password;

    // 设置运动备注类型
    const sportsType = user.sports_comment_type || 'default';
    document.getElementById('sports_comment_type').value = sportsType;
    document.getElementById('sports_custom_comment').value = user.sports_custom_comment || '';

    // 解析运动备注API类型
    const sportsApiType = user.sports_comment_api || 'poetry_all';
    console.log('[编辑用户] 运动备注API类型:', sportsApiType);

    let sportsProvider = 'jinrishici';  // 默认
    let sportsCategory = 'poetry_all';  // 默认

    if (sportsApiType.startsWith('cenguigui_')) {
        sportsProvider = 'cenguigui';
    } else if (sportsApiType.startsWith('yuanmeng_')) {
        sportsProvider = 'yuanmeng';
    } else if (sportsApiType.startsWith('klapi_')) {
        sportsProvider = 'klapi';
    } else if (sportsApiType.startsWith('hitokoto_')) {
        sportsProvider = 'hitokoto';
    } else if (sportsApiType.startsWith('poetry_')) {
        sportsProvider = 'jinrishici';
        sportsCategory = sportsApiType;
    } else if (sportsApiType === 'poetry_all' || sportsApiType.startsWith('poetry_')) {
        // 处理 poetry_all 或其他 poetry_ 开头的值
        sportsProvider = 'jinrishici';
        sportsCategory = sportsApiType;
    }

    console.log('[编辑用户] 运动备注 - 供应商:', sportsProvider, '分类:', sportsCategory);

    document.getElementById('sports_api_provider').value = sportsProvider;

    // 设置今日诗词的分类
    if (sportsProvider === 'jinrishici') {
        document.getElementById('sports_api_jinrishici').value = sportsCategory;
    }

    // 设置每日备注类型
    const dailyType = user.daily_comment_type || 'default';
    document.getElementById('daily_comment_type').value = dailyType;
    document.getElementById('custom_daily_comment').value = user.custom_daily_comment || '';

    // 解析每日备注API类型，确定供应商
    const apiType = user.daily_comment_api || 'poetry_all';
    console.log('[编辑用户] 每日备注API类型:', apiType);

    let provider = 'jinrishici';  // 默认
    let category = 'poetry_all';  // 默认

    if (apiType.startsWith('cenguigui_')) {
        provider = 'cenguigui';
    } else if (apiType.startsWith('yuanmeng_')) {
        provider = 'yuanmeng';
    } else if (apiType.startsWith('klapi_')) {
        provider = 'klapi';
    } else if (apiType.startsWith('hitokoto_')) {
        provider = 'hitokoto';
    } else if (apiType.startsWith('poetry_')) {
        provider = 'jinrishici';
        category = apiType;
    } else if (apiType === 'poetry_all' || apiType.startsWith('poetry_')) {
        // 处理 poetry_all 或其他 poetry_ 开头的值
        provider = 'jinrishici';
        category = apiType;
    }

    console.log('[编辑用户] 每日备注 - 供应商:', provider, '分类:', category);

    document.getElementById('api_provider').value = provider;

    // 设置今日诗词的分类
    if (provider === 'jinrishici') {
        document.getElementById('daily_comment_api_jinrishici').value = category;
    }

    // 设置运动图片类型
    const imageType = user.sports_image_type || 'default';
    document.getElementById('sports_image_type').value = imageType;

    // 设置图片供应商
    const imageProvider = user.sports_image_provider || 'bing';
    document.getElementById('sports_image_provider').value = imageProvider;
    document.getElementById('sports_image_category').value = user.sports_image_category || 'random';

    console.log('[编辑用户] 图片 - 类型:', imageType, '供应商:', imageProvider, '分类:', user.sports_image_category || 'random');

    // 触发显示/隐藏逻辑
    onDailyCommentTypeChange();
    onSportsCommentTypeChange();
    onSportsImageTypeChange();

    document.getElementById('enabled').checked = user.enabled;
    document.getElementById('userModal').classList.add('active');
}

// 关闭弹窗
function closeUserModal() {
    document.getElementById('userModal').classList.remove('active');
    // 移除用户名输入监听器
    const usernameInput = document.getElementById('username');
    usernameInput.removeEventListener('input', autoFillPassword);
}

// 保存用户
async function saveUser() {
    const userId = document.getElementById('userId').value;
    const dailyType = document.getElementById('daily_comment_type').value;
    const sportsType = document.getElementById('sports_comment_type').value;

    const userData = {
        username: document.getElementById('username').value,
        nickname: document.getElementById('nickname').value,
        password: document.getElementById('password').value,
        // 运动备注配置
        sports_comment_type: sportsType,
        sports_custom_comment: document.getElementById('sports_custom_comment').value,
        sports_comment_api: getSportsApiType(),
        // 运动图片配置
        sports_image_type: document.getElementById('sports_image_type').value,
        sports_image_provider: getSportsImageProvider(),
        sports_image_category: document.getElementById('sports_image_category').value,
        // 每日备注配置
        daily_comment_type: dailyType,
        custom_daily_comment: document.getElementById('custom_daily_comment').value,
        daily_comment_api: getCurrentApiType(),
        enabled: document.getElementById('enabled').checked
    };

    if (!userData.username || !userData.password) {
        showToast('请填写用户名和密码', 'error');
        return;
    }

    // 检查用户名是否重复（仅添加新用户时检查）
    if (!userId) {
        const duplicateUser = currentUsers.find(u => u.username === userData.username);
        if (duplicateUser) {
            showToast('用户名已存在，请使用其他用户名', 'error');
            return;
        }
    }

    // 验证自定义内容
    if (dailyType === 'custom' && !userData.custom_daily_comment.trim()) {
        showToast('请输入自定义备注内容', 'error');
        return;
    }

    if (sportsType === 'custom' && !userData.sports_custom_comment.trim()) {
        showToast('请输入自定义运动备注内容', 'error');
        return;
    }

    try {
        let response;
        if (userId) {
            response = await apiRequest(`/api/users/${userId}`, {
                method: 'PUT',
                body: JSON.stringify(userData)
            });
        } else {
            response = await apiRequest('/api/users', {
                method: 'POST',
                body: JSON.stringify(userData)
            });
        }

        const data = await response.json();
        if (data.success) {
            showToast(userId ? '用户更新成功' : '用户添加成功', 'success');
            closeUserModal();
            loadUsers();
            loadStats();
        } else {
            showToast(data.error, 'error');
        }
    } catch (error) {
        if (error.message !== 'Unauthorized') {
            showToast('保存失败', 'error');
        }
    }
}

// 切换用户状态
async function toggleUser(userId) {
    const user = currentUsers.find(u => u.id === userId);
    if (!user) return;

    try {
        const response = await apiRequest(`/api/users/${userId}/toggle`, {
            method: 'PATCH',
            body: JSON.stringify({ enabled: !user.enabled })
        });
        const data = await response.json();
        if (data.success) {
            showToast(`用户已${user.enabled ? '禁用' : '启用'}`, 'success');
            loadUsers();
            loadStats();
        } else {
            showToast(data.error, 'error');
        }
    } catch (error) {
        if (error.message !== 'Unauthorized') {
            showToast('操作失败', 'error');
        }
    }
}

// 删除用户
async function deleteUser(userId) {
    if (!confirm('确定要删除该用户吗？')) return;

    try {
        const response = await apiRequest(`/api/users/${userId}`, {
            method: 'DELETE'
        });
        const data = await response.json();
        if (data.success) {
            showToast('用户已删除', 'success');
            loadUsers();
            loadStats();
        } else {
            showToast(data.error, 'error');
        }
    } catch (error) {
        if (error.message !== 'Unauthorized') {
            showToast('删除失败', 'error');
        }
    }
}

// 触发所有用户打卡
async function triggerAllClockin() {
    console.log('[触发批量打卡] 开始');

    // 防止重复点击
    if (isClockinRunning) {
        console.warn('[批量打卡] 跳过：打卡任务正在执行中');
        showToast('打卡任务正在执行中，请稍候...', 'error');
        return;
    }

    if (!confirm('确定要为所有启用的用户执行打卡吗？')) return;

    isClockinRunning = true;
    showToast('正在执行打卡，请稍候...', 'success');

    // 立即刷新活动任务显示
    loadActiveTasks();

    const apiUrl = '/api/clockin/trigger';
    console.log('[批量打卡] 发送请求到:', apiUrl);

    try {
        const startTime = Date.now();
        const response = await apiRequest(apiUrl, {
            method: 'POST'
        });
        const duration = Date.now() - startTime;
        console.log('[批量打卡] 请求完成，耗时:', duration, 'ms, 状态:', response.status);

        const data = await response.json();
        console.log('[批量打卡] 响应数据:', data);

        if (data.success) {
            const result = data.data;
            const message = result.message || `打卡完成: 成功 ${result.success}，失败 ${result.failure}`;
            showToast(message, 'success');

            // 刷新数据显示
            loadUsers();
            loadStats();
            loadRecords();
            loadActiveTasks();  // 清除活动任务显示
        } else {
            console.error('[批量打卡] 失败:', data.error);
            showToast('打卡失败: ' + (data.error || '未知错误'), 'error');
        }
    } catch (error) {
        if (error.message !== 'Unauthorized') {
            console.error('[批量打卡] 请求异常:', error);
            showToast('打卡请求失败: ' + error.message, 'error');
        }
    } finally {
        isClockinRunning = false;
    }
}

/**
 * 轮询任务状态
 */
async function pollTaskStatus(taskId) {
    const maxAttempts = 300; // 最多轮询300次（5分钟，每秒一次）
    let attempts = 0;
    const pollInterval = 2000; // 每2秒轮询一次

    console.log('[轮询任务] 开始轮询任务状态:', taskId);

    const poll = async () => {
        try {
            const response = await apiRequest(`/api/clockin/status/${taskId}`);
            const data = await response.json();

            if (!data.success) {
                console.error('[轮询任务] 获取状态失败:', data.error);
                showToast('获取任务状态失败', 'error');
                isClockinRunning = false;
                return;
            }

            const task = data.data;
            console.log('[轮询任务] 状态:', task.status, '进度:', `${task.progress.current}/${task.progress.total}`);

            // 更新进度提示
            if (task.status === 'running') {
                const progressText = `正在执行打卡... ${task.progress.current}/${task.progress.total} (成功:${task.progress.success}, 失败:${task.progress.failure})`;
                showToast(progressText, 'success', 2000);
            } else if (task.status === 'completed') {
                // 使用 progress 中的数据，这些数据是准确的
                const progress = task.progress || {};
                const total = progress.total || 0;
                const success = progress.success || 0;
                const failure = progress.failure || 0;

                showToast(`打卡完成！共 ${total} 人，成功 ${success}，失败 ${failure}`, 'success', 5000);
                loadStats();
                loadRecords();
                isClockinRunning = false;
                return;
            } else if (task.status === 'failed') {
                console.error('[轮询任务] 任务失败:', task.error);
                showToast(`打卡任务失败: ${task.error}`, 'error', 5000);
                isClockinRunning = false;
                return;
            }

            // 继续轮询
            attempts++;
            if (attempts < maxAttempts) {
                setTimeout(poll, pollInterval);
            } else {
                console.warn('[轮询任务] 达到最大轮询次数');
                showToast('任务执行超时，请稍后查看结果', 'error');
                isClockinRunning = false;
            }
        } catch (error) {
            if (error.message !== 'Unauthorized') {
                console.error('[轮询任务] 请求异常:', error);
                // 出错后重试
                attempts++;
                if (attempts < maxAttempts) {
                    setTimeout(poll, pollInterval);
                } else {
                    showToast('任务状态查询失败', 'error');
                    isClockinRunning = false;
                }
            } else {
                isClockinRunning = false;
            }
        }
    };

    // 开始轮询
    poll();
}

// 触发单个用户打卡
async function triggerUserClockin(userId, event) {
    // 阻止事件冒泡
    if (event) {
        event.preventDefault();
        event.stopPropagation();
    }

    console.log('[触发单用户打卡] userId:', userId);

    // 防止重复点击
    if (isClockinRunning) {
        console.warn('[打卡] 跳过：打卡任务正在执行中');
        showToast('打卡任务正在执行中，请稍候...', 'error');
        return;
    }

    isClockinRunning = true;
    showToast('正在执行打卡...', 'success');

    // 立即刷新活动任务显示
    loadActiveTasks();

    const apiUrl = `/api/clockin/user/${userId}`;
    console.log('[打卡] 发送请求到:', apiUrl);

    try {
        const startTime = Date.now();
        const response = await apiRequest(apiUrl, {
            method: 'POST'
        });
        const duration = Date.now() - startTime;
        console.log('[打卡] 请求完成，耗时:', duration, 'ms, 状态:', response.status);

        const data = await response.json();
        console.log('[打卡] 响应数据:', data);

        if (data.success) {
            showToast('打卡成功', 'success');
            // 只更新当前用户的列表，而不是全部刷新
            loadUsers();
            loadStats();
            loadRecords();
            loadActiveTasks();  // 清除活动任务显示
        } else {
            console.error('[打卡] 失败:', data.error);
            showToast(data.error || '打卡失败', 'error');
        }
    } catch (error) {
        if (error.message !== 'Unauthorized') {
            console.error('[打卡] 请求异常:', error);
            showToast('打卡请求失败: ' + error.message, 'error');
        }
    } finally {
        isClockinRunning = false;
    }
}

// 显示提示消息
function showToast(message, type = 'success', duration = 3000) {
    const toast = document.getElementById('toast');
    toast.textContent = message;
    toast.className = `toast ${type} show`;

    // 清除之前的定时器（如果存在）
    if (toast._timeout) {
        clearTimeout(toast._timeout);
    }

    // 设置新的定时器
    toast._timeout = setTimeout(() => {
        toast.classList.remove('show');
        toast._timeout = null;
    }, duration);
}

// 工具函数
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// 规范化 URL，确保有协议前缀且末尾无斜杠
function normalizeUrl(url) {
    if (!url) return url;
    url = url.trim();
    // 如果没有协议前缀，默认添加 https://
    if (!url.startsWith('http://') && !url.startsWith('https://')) {
        url = 'https://' + url;
    }
    // 去除末尾的斜杠
    url = url.replace(/\/+$/, '');
    return url;
}

// 自动格式化输入框中的 URL
function autoFormatUrl(inputElement) {
    const originalValue = inputElement.value.trim();
    if (!originalValue) return;

    const normalized = normalizeUrl(originalValue);
    if (normalized !== originalValue) {
        inputElement.value = normalized;
        // 显示简短的提示
        showToast('URL 已自动格式化', 'success', 1500);
    }
}

function formatDate(dateStr) {
    const date = new Date(dateStr);
    return date.toLocaleString('zh-CN');
}

function formatTime(dateStr) {
    const date = new Date(dateStr);
    return date.toLocaleTimeString('zh-CN');
}

// 切换密码可见性
function togglePasswordVisibility(inputId) {
    const input = document.getElementById(inputId);
    const button = input.parentElement.querySelector('.password-toggle');
    const eyeIcon = button.querySelector('.eye-icon');

    if (input.type === 'password') {
        input.type = 'text';
        eyeIcon.textContent = '🙈'; // 闭眼睛图标
        button.title = '隐藏密码';
    } else {
        input.type = 'password';
        eyeIcon.textContent = '👁'; // 睁眼睛图标
        button.title = '显示密码';
    }
}

// 系统配置相关函数
async function openConfigModal() {
    try {
        const response = await apiRequest('/api/config');
        const data = await response.json();
        const config = data.data || {};

        // 加载基本配置
        document.getElementById('configApiRequestDelay').value = config.api_request_delay || 500;
        document.getElementById('configClockinTypeDelay').value = config.clockin_type_delay || 2;

        // 加载定时任务开关
        const scheduleEnabled = config.schedule_enabled !== undefined ? config.schedule_enabled : true;
        document.getElementById('configScheduleEnabled').checked = scheduleEnabled;
        updateScheduleConfigVisibility(scheduleEnabled);

        // 加载定时任务配置（解析 cron 表达式）
        if (config.schedule_cron) {
            const cronParts = config.schedule_cron.trim().split(/\s+/);
            if (cronParts.length >= 6) {
                // Cron 格式: 秒 分 时 日 月 周（存储的是 UTC 时间）
                const second = cronParts[0];
                const minute = cronParts[1];
                const hour = parseInt(cronParts[2]);

                // 将 UTC 时间转换为北京时间（UTC + 8）
                let beijingHour = hour + 8;
                if (beijingHour >= 24) {
                    beijingHour -= 24;
                }

                const timeStr = `${beijingHour.toString().padStart(2, '0')}:${minute.padStart(2, '0')}`;
                document.getElementById('configScheduleTime').value = timeStr;

                // 设置为北京时间模式
                document.getElementById('configScheduleTimezone').value = 'beijing';
            }
        } else {
            // 默认值：北京时间 0:10
            document.getElementById('configScheduleTime').value = '00:10';
            document.getElementById('configScheduleTimezone').value = 'beijing';
        }

        // 更新时间预览
        updateTimePreview();

        // 加载 Worker API 列表
        await loadWorkerApis();
    } catch (error) {
        console.error('加载配置失败:', error);
    }
    document.getElementById('configModal').classList.add('active');

    // 默认显示基本设置标签
    showConfigTab('general');
}

// 更新定时任务配置区域显示
function updateScheduleConfigVisibility(enabled) {
    const scheduleConfig = document.getElementById('scheduleConfig');
    if (enabled) {
        scheduleConfig.style.opacity = '1';
        scheduleConfig.style.pointerEvents = 'auto';
    } else {
        scheduleConfig.style.opacity = '0.5';
        scheduleConfig.style.pointerEvents = 'none';
    }
}

// 快捷设置时间
function setQuickTime(time) {
    document.getElementById('configScheduleTime').value = time;
    updateTimePreview();
}

// 更新时间预览
function updateTimePreview() {
    const timeInput = document.getElementById('configScheduleTime').value;
    const timezone = document.getElementById('configScheduleTimezone').value;

    if (!timeInput) return;

    const [hour, minute] = timeInput.split(':').map(v => parseInt(v));

    if (timezone === 'beijing') {
        // 北京时间转 UTC
        let utcHour = hour - 8;
        if (utcHour < 0) utcHour += 24;

        document.getElementById('nextRunTime').textContent = `北京时间 ${timeInput}`;
        document.getElementById('utcTime').textContent = `${utcHour.toString().padStart(2, '0')}:${minute.toString().padStart(2, '0')}`;

        const cronExpr = `0 ${minute} ${utcHour} * * *`;
        document.getElementById('cronExpression').textContent = cronExpr;
    } else {
        // UTC 时间
        document.getElementById('nextRunTime').textContent = `UTC 时间 ${timeInput}`;
        let beijingHour = hour + 8;
        if (beijingHour >= 24) beijingHour -= 24;
        document.getElementById('utcTime').textContent = `北京时间 ${beijingHour.toString().padStart(2, '0')}:${minute.toString().padStart(2, '0')}`;

        const cronExpr = `0 ${minute} ${hour} * * *`;
        document.getElementById('cronExpression').textContent = cronExpr;
    }
}

// 切换配置标签页
function showConfigTab(tabName) {
    // 隐藏所有标签内容
    document.querySelectorAll('.config-tab-content').forEach(tab => {
        tab.style.display = 'none';
    });

    // 移除所有标签的 active 状态
    document.querySelectorAll('.tab').forEach(tab => {
        tab.classList.remove('active');
    });

    // 显示选中的标签内容
    document.getElementById(`config-tab-${tabName}`).style.display = 'block';

    // 激活选中的标签
    document.getElementById(`tab-${tabName}`).classList.add('active');

    // 如果切换到 Worker API 标签，重新加载列表
    if (tabName === 'worker-apis') {
        loadWorkerApis();
    }

    // 根据标签显示/隐藏底部按钮（如果存在）
    const testBtn = document.getElementById('testConfigBtn');
    const saveBtn = document.getElementById('saveConfigBtn');
    if (testBtn && saveBtn) {
        if (tabName === 'worker-apis') {
            testBtn.style.display = 'none';
            saveBtn.style.display = 'none';
        } else {
            testBtn.style.display = 'inline-flex';
            saveBtn.style.display = 'inline-flex';
        }
    }
}

function closeConfigModal() {
    document.getElementById('configModal').classList.remove('active');
}

async function saveConfig() {
    const config = {};

    // 获取基本配置
    const apiRequestDelay = parseInt(document.getElementById('configApiRequestDelay').value);
    const clockinTypeDelay = parseInt(document.getElementById('configClockinTypeDelay').value);

    if (!isNaN(apiRequestDelay)) {
        config.api_request_delay = apiRequestDelay;
    }
    if (!isNaN(clockinTypeDelay)) {
        config.clockin_type_delay = clockinTypeDelay;
    }

    // 获取定时任务开关
    const scheduleEnabled = document.getElementById('configScheduleEnabled').checked;
    config.schedule_enabled = scheduleEnabled;

    // 获取定时任务配置
    const scheduleTime = document.getElementById('configScheduleTime').value;
    const scheduleTimezone = document.getElementById('configScheduleTimezone').value;

    if (scheduleTime) {
        const [hour, minute] = scheduleTime.split(':').map(v => parseInt(v));

        if (scheduleTimezone === 'beijing') {
            // 北京时间转 UTC（减去 8 小时）
            let utcHour = hour - 8;
            if (utcHour < 0) {
                utcHour += 24;
            }
            // Cron 格式: 秒 分 时 日 月 周
            config.schedule_cron = `0 ${minute} ${utcHour} * * *`;
        } else {
            // 直接使用 UTC 时间
            config.schedule_cron = `0 ${minute} ${hour} * * *`;
        }
    }

    try {
        const response = await apiRequest('/api/config', {
            method: 'PUT',
            body: JSON.stringify(config)
        });

        const data = await response.json();
        if (data.success) {
            showToast(data.message || '配置保存成功', 'success');
            closeConfigModal();
        } else {
            showToast(data.error || '保存失败', 'error');
        }
    } catch (error) {
        if (error.message !== 'Unauthorized') {
            showToast('保存失败: ' + error.message, 'error');
        }
    }
}

// 清理旧记录
async function cleanupOldRecords() {
    const days = prompt('请输入要保留的天数（默认7天）:', '7');
    if (days === null) return;

    const daysToKeep = parseInt(days);
    if (isNaN(daysToKeep) || daysToKeep < 1) {
        showToast('请输入有效的天数', 'error');
        return;
    }

    const today = new Date().toISOString().split('T')[0];
    if (!confirm(`确定要清理超过 ${daysToKeep} 天的旧记录吗？\n\n今天: ${today}\n将删除 ${daysToKeep} 天前的所有记录`)) {
        return;
    }

    try {
        showToast('正在清理，请稍候...', 'success');
        const response = await apiRequest('/api/maintenance/cleanup', {
            method: 'POST',
            body: JSON.stringify({ days: daysToKeep })
        });

        const data = await response.json();
        if (data.success) {
            // 显示完整详细结果弹窗
            let message = data.message + '\n\n';
            message += `━━━━━━━━━━━━━━━━━━\n`;
            message += `检查记录: ${data.checked} 条\n`;
            message += `删除记录: ${data.deleted} 条\n`;
            message += `保留记录: ${data.total - data.deleted} 条\n`;
            message += `保留天数: ${data.daysToKeep} 天\n`;
            message += `截止日期: ${data.cutoffDate}\n`;
            message += `今天日期: ${data.today}\n`;
            if (data.errors > 0) {
                message += `错误数量: ${data.errors}\n`;
            }
            message += `━━━━━━━━━━━━━━━━━━`;

            alert(message);

            // 显示简短的 toast 提示
            showToast(data.message, 'success');

            // 刷新数据
            loadStats();
            loadRecords();
        } else {
            showToast(data.error || '清理失败', 'error');
        }
    } catch (error) {
        if (error.message !== 'Unauthorized') {
            showToast('清理失败: ' + error.message, 'error');
        }
    }
}

// 自动填充密码为用户名后六位
function autoFillPassword(event) {
    const username = event.target.value;
    const passwordField = document.getElementById('password');

    // 只在密码字段为空时自动填充
    if (passwordField.value === '' && username.length > 0) {
        // 提取用户名后六位，如果不足六位则取全部
        const password = username.slice(-6);
        passwordField.value = password;
    }
}

// 登出功能
async function logout() {
    try {
        const token = localStorage.getItem("auth_token");
        await fetch("/api/auth/logout", {
            method: "POST",
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            }
        });
    } catch (error) {
        console.error("登出请求失败:", error);
    } finally {
        // 清除本地 token
        localStorage.removeItem("auth_token");
        // 跳转到登录页
        window.location.href = window.ADMIN_PATH || "/admin";
    }
}

// ==================== Worker API 管理相关函数 ====================

// 加载 Worker API 列表
async function loadWorkerApis() {
    try {
        const response = await apiRequest('/api/worker-apis');
        const data = await response.json();

        if (data.success) {
            renderWorkerApisList(data.data || []);
        } else {
            showToast('加载 Worker API 列表失败', 'error');
        }
    } catch (error) {
        if (error.message !== 'Unauthorized') {
            console.error('加载 Worker API 列表失败:', error);
            document.getElementById('workerApisList').innerHTML =
                '<div style="text-align: center; padding: 40px; color: var(--text-secondary);">加载失败</div>';
        }
    }
}

// 渲染 Worker API 列表
function renderWorkerApisList(apis) {
    const container = document.getElementById('workerApisList');

    if (apis.length === 0) {
        container.innerHTML = `
            <div style="text-align: center; padding: 60px 20px; color: var(--text-secondary);">
                <div style="font-size: 48px; margin-bottom: 16px;">📡</div>
                <div style="font-size: 14px; margin-bottom: 8px;">还没有配置 Worker API</div>
                <div style="font-size: 12px; color: var(--text-muted);">点击上方"添加 Worker API"按钮开始配置</div>
            </div>
        `;
        return;
    }

    // 检查是否只有一个 API（最后一个不能删除）
    const isLastOne = apis.length === 1;

    container.innerHTML = apis.map(api => {
        const enabledBadge = api.enabled
            ? '<span class="worker-api-badge enabled">✓ 已启用</span>'
            : '<span class="worker-api-badge disabled">✗ 已禁用</span>';

        const availableBadge = api.available
            ? '<span class="worker-api-badge available">可用</span>'
            : '<span class="worker-api-badge unavailable">不可用</span>';

        const successRate = api.total_requests > 0
            ? Math.round((api.total_success / api.total_requests) * 100)
            : 0;

        const deleteButton = isLastOne
            ? '<button class="btn btn-sm btn-danger" disabled style="opacity: 0.5; cursor: not-allowed;" title="至少需要保留一个 Worker API">删除</button>'
            : `<button class="btn btn-sm btn-danger" onclick="deleteWorkerApi('${api.id}', '${escapeHtml(api.name)}')">删除</button>`;

        return `
            <div class="worker-api-card" data-api-id="${api.id}">
                ${isLastOne ? `
                <div style="background: #fff3cd; border-left: 4px solid #ffc107; padding: 10px; margin: -10px -10px 10px -10px; border-radius: 4px 4px 0 0;">
                    <div style="font-size: 13px; color: #856404; display: flex; align-items: center; gap: 8px;">
                        <span>⚠️</span>
                        <span>这是最后一个 Worker API，无法删除。请先添加新的 API 再删除此 API。</span>
                    </div>
                </div>
                ` : ''}
                <div class="worker-api-header">
                    <div class="worker-api-name">
                        ${escapeHtml(api.name)}
                        ${!api.available ? '<span style="margin-left: 8px; font-size: 12px; color: var(--danger-color);">(已标记为不可用，点击"重置"按钮恢复)</span>' : ''}
                    </div>
                    <div class="worker-api-status">
                        ${enabledBadge}
                        ${availableBadge}
                    </div>
                </div>
                <div class="worker-api-info">
                    <div class="worker-api-info-item">
                        <div class="worker-api-info-label">API 地址</div>
                        <div class="worker-api-info-value">${escapeHtml(api.url)}</div>
                    </div>
                    <div class="worker-api-info-item">
                        <div class="worker-api-info-label">备注</div>
                        <div class="worker-api-info-value">${api.note ? escapeHtml(api.note) : '-'}</div>
                    </div>
                </div>
                <div class="worker-api-stats">
                    <div class="worker-api-stat">
                        <div class="worker-api-stat-label">总请求</div>
                        <div class="worker-api-stat-value">${api.total_requests}</div>
                    </div>
                    <div class="worker-api-stat">
                        <div class="worker-api-stat-label">成功率</div>
                        <div class="worker-api-stat-value">${successRate}%</div>
                    </div>
                    <div class="worker-api-stat">
                        <div class="worker-api-stat-label">连续失败</div>
                        <div class="worker-api-stat-value">${api.failure_count}</div>
                    </div>
                    <div class="worker-api-stat" style="margin-left: auto;">
                        <div class="worker-api-actions">
                            <button class="btn btn-sm" onclick="testWorkerApi('${api.id}')">测试</button>
                            <button class="btn btn-sm" onclick="editWorkerApi('${api.id}')">编辑</button>
                            ${!api.available ? `<button class="btn btn-sm" onclick="resetWorkerApi('${api.id}')" title="将此 API 标记为可用，恢复使用">重置</button>` : ''}
                            ${deleteButton}
                        </div>
                    </div>
                </div>
            </div>
        `;
    }).join('');
}

// 打开添加 Worker API 弹窗
function openAddWorkerApiModal() {
    document.getElementById('workerApiModalTitle').textContent = '添加 Worker API';
    document.getElementById('workerApiId').value = '';
    document.getElementById('workerApiName').value = '';
    document.getElementById('workerApiUrl').value = '';
    document.getElementById('workerApiToken').value = '';
    document.getElementById('workerApiNote').value = '';
    document.getElementById('workerApiEnabled').checked = true;
    document.getElementById('workerApiModal').classList.add('active');
}

// 关闭 Worker API 弹窗
function closeWorkerApiModal() {
    document.getElementById('workerApiModal').classList.remove('active');
}

// 编辑 Worker API
async function editWorkerApi(apiId) {
    try {
        const response = await apiRequest(`/api/worker-apis`);
        const data = await response.json();

        if (data.success) {
            const api = data.data.find(a => a.id === apiId);
            if (api) {
                document.getElementById('workerApiModalTitle').textContent = '编辑 Worker API';
                document.getElementById('workerApiId').value = api.id;
                document.getElementById('workerApiName').value = api.name;
                document.getElementById('workerApiUrl').value = api.url;
                document.getElementById('workerApiToken').value = api.token;
                document.getElementById('workerApiNote').value = api.note || '';
                document.getElementById('workerApiEnabled').checked = api.enabled;
                document.getElementById('workerApiModal').classList.add('active');
            }
        }
    } catch (error) {
        if (error.message !== 'Unauthorized') {
            showToast('加载 Worker API 信息失败', 'error');
        }
    }
}

// 保存 Worker API
async function saveWorkerApi() {
    const apiId = document.getElementById('workerApiId').value;
    const name = document.getElementById('workerApiName').value.trim();
    let url = document.getElementById('workerApiUrl').value.trim();
    const token = document.getElementById('workerApiToken').value.trim();
    const note = document.getElementById('workerApiNote').value.trim();
    const enabled = document.getElementById('workerApiEnabled').checked;

    if (!name || !url || !token) {
        showToast('请填写名称、URL 和 Token', 'error');
        return;
    }

    // 规范化 URL
    url = normalizeUrl(url);

    try {
        const payload = { name, url, token, note, enabled };

        let response;
        if (apiId) {
            // 更新
            response = await apiRequest(`/api/worker-apis/${apiId}`, {
                method: 'PUT',
                body: JSON.stringify(payload)
            });
        } else {
            // 创建
            response = await apiRequest('/api/worker-apis', {
                method: 'POST',
                body: JSON.stringify(payload)
            });
        }

        const data = await response.json();
        if (data.success) {
            showToast(apiId ? 'Worker API 更新成功' : 'Worker API 创建成功', 'success');
            closeWorkerApiModal();
            loadWorkerApis();
        } else {
            showToast(data.error || '操作失败', 'error');
        }
    } catch (error) {
        if (error.message !== 'Unauthorized') {
            showToast('操作失败: ' + error.message, 'error');
        }
    }
}

// 测试 Worker API 连接
async function testWorkerApi(apiId) {
    try {
        showToast('正在测试连接...', 'success');
        const response = await apiRequest(`/api/worker-apis/${apiId}/test`, {
            method: 'POST'
        });

        const data = await response.json();
        if (data.success) {
            showToast(`连接成功！延迟: ${data.latency_ms}ms`, 'success');
        } else {
            showToast(`连接失败: ${data.message}`, 'error');
        }
    } catch (error) {
        if (error.message !== 'Unauthorized') {
            showToast('测试失败: ' + error.message, 'error');
        }
    }
}

// 重置 Worker API 状态
async function resetWorkerApi(apiId) {
    if (!confirm('确定要重置此 Worker API 的状态吗？这将把 API 标记为可用，恢复使用。')) {
        return;
    }

    try {
        const response = await apiRequest(`/api/worker-apis/${apiId}/reset`, {
            method: 'POST'
        });

        const data = await response.json();
        if (data.success) {
            showToast('Worker API 状态已重置，可以继续使用', 'success');
            loadWorkerApis();
        } else {
            showToast(data.error || '操作失败', 'error');
        }
    } catch (error) {
        if (error.message !== 'Unauthorized') {
            showToast('操作失败: ' + error.message, 'error');
        }
    }
}

// 批量测试所有 Worker API
async function testAllWorkerApis() {
    try {
        const response = await apiRequest('/api/worker-apis');
        const data = await response.json();

        if (!data.success) {
            showToast('获取 Worker API 列表失败', 'error');
            return;
        }

        const apis = data.data || [];
        if (apis.length === 0) {
            showToast('没有可测试的 Worker API', 'error');
            return;
        }

        showToast(`开始测试 ${apis.length} 个 Worker API...`, 'success');

        const results = {
            success: 0,
            failed: 0,
            details: []
        };

        // 并发测试所有 API
        const testPromises = apis.map(api =>
            fetch(`/api/worker-apis/${api.id}/test`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${localStorage.getItem('auth_token')}`
                }
            }).then(async res => {
                const result = await res.json();
                return {
                    api: api,
                    success: result.success,
                    message: result.message,
                    latency: result.latency_ms
                };
            }).catch(error => {
                return {
                    api: api,
                    success: false,
                    message: error.message || '测试失败'
                };
            })
        );

        const testResults = await Promise.all(testPromises);

        // 统计结果
        testResults.forEach(result => {
            if (result.success) {
                results.success++;
            } else {
                results.failed++;
            }
            results.details.push(result);
        });

        // 显示结果
        const summary = `测试完成！成功: ${results.success}, 失败: ${results.failed}`;

        // 显示详细的测试结果
        const detailsList = results.details.map(r => {
            const status = r.success ? '✅' : '❌';
            const latency = r.latency ? ` (${r.latency}ms)` : '';
            return `${status} ${r.api.name}: ${r.message}${latency}`;
        }).join('\n');

        if (results.failed === 0) {
            showToast(`🎉 ${summary}\n\n${detailsList}`, 'success', 5000);
        } else if (results.success === 0) {
            showToast(`⚠️ ${summary}\n\n${detailsList}`, 'error', 5000);
        } else {
            showToast(`⚡ ${summary}\n\n${detailsList}`, 'success', 5000);
        }

    } catch (error) {
        if (error.message !== 'Unauthorized') {
            showToast('批量测试失败: ' + error.message, 'error');
        }
    }
}

// 删除 Worker API
async function deleteWorkerApi(apiId, apiName) {
    if (!confirm(`确定要删除 Worker API "${apiName}" 吗？此操作不可恢复。`)) {
        return;
    }

    try {
        const response = await apiRequest(`/api/worker-apis/${apiId}`, {
            method: 'DELETE'
        });

        const data = await response.json();
        if (data.success) {
            showToast('Worker API 删除成功', 'success');
            loadWorkerApis();
        } else {
            showToast(data.detail || data.error || '删除失败', 'error');
        }
    } catch (error) {
        if (error.message !== 'Unauthorized') {
            showToast('删除失败: ' + error.message, 'error');
        }
    }
}
