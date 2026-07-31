/**
 * 主应用脚本 v7.0
 * Tailwind + DaisyUI 适配
 */

// ========== 全局状态 ==========
let currentUsers = [];
let currentRecords = [];
let currentWorkerApis = [];
let isClockinRunning = false;
let currentPage = 'dashboard';
let recordRange = 'day';
let userSortField = null;
let userSortAsc = true;
let scheduleCountdownTimer = null;

// ========== API 请求层 ==========
async function apiRequest(url, options = {}) {
    const token = localStorage.getItem('auth_token');
    const defaultOptions = { credentials: 'include', headers: { 'Content-Type': 'application/json' } };
    if (token) defaultOptions.headers['Authorization'] = `Bearer ${token}`;
    const merged = { ...defaultOptions, ...options };
    const response = await fetch(url, merged);
    if (response.status === 401) {
        showToast('登录已过期，请重新登录', 'error');
        setTimeout(() => { window.location.href = window.ADMIN_PATH || '/admin'; }, 1500);
        throw new Error('Unauthorized');
    }
    return response;
}

// ========== 初始化 ==========
document.addEventListener('DOMContentLoaded', () => {
    if (!localStorage.getItem('auth_token')) {
        window.location.href = window.ADMIN_PATH || '/admin';
        return;
    }
    const hash = window.location.hash.replace('#/', '') || 'dashboard';
    navigateTo(hash);
    setInterval(loadActiveTasks, 3000);
    setInterval(updateStatusBar, 30000);
});

// ========== 路由 ==========
function navigateTo(page) {
    const valid = ['dashboard', 'users', 'records', 'apis', 'settings'];
    if (!valid.includes(page)) page = 'dashboard';
    currentPage = page;

    // 侧边栏高亮
    document.querySelectorAll('.nav-link[data-page]').forEach(el => {
        el.classList.toggle('active', el.dataset.page === page);
    });

    // 页面切换
    document.querySelectorAll('.page-section').forEach(el => {
        el.classList.add('hidden');
        el.classList.remove('active');
    });
    const target = document.getElementById(`page-${page}`);
    if (target) {
        target.classList.remove('hidden');
        target.classList.add('active');
    }

    // 标题
    const titles = { dashboard: '概览', users: '用户管理', records: '打卡记录', apis: 'Worker API', settings: '系统设置' };
    document.getElementById('pageTitle').textContent = titles[page] || '概览';
    window.location.hash = `/${page}`;
    loadCurrentPage();

    // 移动端收起侧边栏
    if (window.innerWidth < 1024) {
        document.getElementById('sidebar').classList.remove('open');
    }
}

function loadCurrentPage() {
    const map = { dashboard: loadDashboard, users: loadUsers, records: loadRecords, apis: loadWorkerApis, settings: loadSettings };
    (map[currentPage] || loadDashboard)();
}

window.addEventListener('hashchange', () => {
    const hash = window.location.hash.replace('#/', '') || 'dashboard';
    if (hash !== currentPage) navigateTo(hash);
});

// ========== 侧边栏 ==========
function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    if (window.innerWidth < 1024) {
        sidebar.classList.toggle('open');
    } else {
        sidebar.classList.toggle('collapsed');
    }
}

// ========== 概览页 ==========
async function loadDashboard() {
    await Promise.all([loadStats(), loadActiveTasks(), loadDashboardRecords()]);
    updateStatusBar();
}

async function loadStats() {
    try {
        const res = await apiRequest('/api/clockin/stats');
        const data = await res.json();
        const s = data.data;
        setText('statTotalUsers', s.total_users || 0);
        setText('statEnabledUsers', s.enabled_users || 0);

        const today = new Date().toISOString().split('T')[0];
        const rRes = await apiRequest(`/api/clockin/results?date=${today}`);
        const rData = await rRes.json();
        const sum = rData.data.summary;
        setText('statTodaySuccess', sum?.success_count ?? '-');
        setText('statTodayFailure', sum?.failure_count ?? '-');
    } catch (e) { if (e.message !== 'Unauthorized') console.error('[stats]', e); }
}

async function loadActiveTasks() {
    try {
        const res = await apiRequest('/api/clockin/active-tasks');
        const data = await res.json();
        const tasks = data.data.active_tasks || [];
        const count = data.data.count || 0;

        const panel = document.getElementById('activeTasksPanel');
        const badge = document.getElementById('activeTaskBadge');
        setText('activeTaskCount', count);
        setText('activeTaskBadgeCount', count);

        if (count > 0) {
            panel.classList.remove('hidden');
            badge.classList.remove('hidden');
            badge.classList.add('flex');
        } else {
            panel.classList.add('hidden');
            badge.classList.add('hidden');
            badge.classList.remove('flex');
            return;
        }

        document.getElementById('activeTasksList').innerHTML = tasks.map(t => `
            <div class="py-3 flex items-center justify-between">
                <div class="flex items-center gap-3">
                    <span class="loading loading-spinner loading-sm text-success"></span>
                    <div>
                        <div class="font-semibold text-sm">${esc(t.username)}</div>
                        <div class="text-xs text-base-content/50 flex gap-3">
                            <span>🔗 ${t.worker_api_name ? esc(t.worker_api_name) : '后备API'}</span>
                            <span>⏱ ${t.elapsed_seconds}s</span>
                        </div>
                    </div>
                </div>
                <span class="badge badge-success badge-sm">执行中</span>
            </div>
        `).join('');
    } catch (e) { if (e.message !== 'Unauthorized') console.error('[tasks]', e); }
}

async function loadDashboardRecords() {
    const c = document.getElementById('dashboardRecords');
    try {
        const today = new Date().toISOString().split('T')[0];
        const res = await apiRequest(`/api/clockin/results?date=${today}`);
        const data = await res.json();
        const results = data.data.results || [];
        const sum = data.data.summary;

        if (!results.length) {
            c.innerHTML = '<div class="text-base-content/40 text-center py-8"><div class="text-3xl mb-2 opacity-30">📋</div>今日暂无打卡记录</div>';
            return;
        }

        let html = '';
        if (sum) {
            const total = (sum.success_count || 0) + (sum.failure_count || 0);
            const rate = total ? Math.round((sum.success_count / total) * 100) : 0;
            html += `<div class="mb-3">
                <div class="flex justify-between text-xs mb-1">
                    <span class="font-semibold">成功率 ${rate}%</span>
                    <span class="text-base-content/50">${sum.success_count || 0} 成功 / ${sum.failure_count || 0} 失败</span>
                </div>
                <progress class="progress ${rate >= 80 ? 'progress-success' : rate >= 50 ? 'progress-warning' : 'progress-error'} w-full" value="${rate}" max="100"></progress>
            </div>`;
        }

        html += results.map(r => renderRecordCard(r)).join('');
        c.innerHTML = html;
    } catch (e) {
        if (e.message !== 'Unauthorized') c.innerHTML = '<div class="text-base-content/40 text-center py-8">加载失败</div>';
    }
}

// ========== 用户管理 ==========
async function loadUsers() {
    try {
        const [userRes, todayRes] = await Promise.all([
            apiRequest('/api/users'),
            apiRequest(`/api/clockin/results?date=${new Date().toISOString().split('T')[0]}`)
        ]);
        const userData = await userRes.json();
        const todayData = await todayRes.json();
        currentUsers = userData.data;

        // 建立今日结果索引: username -> details
        const todayResults = {};
        (todayData.data?.results || []).forEach(r => {
            if (r.details) todayResults[r.username] = r.details;
        });

        // 合并今日打卡状态到用户数据
        currentUsers.forEach(u => {
            const d = todayResults[u.username];
            u._today = d || null;
        });

        renderUserTable();
        updateRecordUserFilter();
    } catch (e) {
        if (e.message !== 'Unauthorized') { console.error('[users]', e); showToast('加载用户列表失败', 'error'); }
    }
}

function renderUserTable() {
    const tbody = document.getElementById('userTableBody');
    let users = [...currentUsers];

    // 搜索
    const q = (document.getElementById('userSearch')?.value || '').toLowerCase();
    if (q) users = users.filter(u => (u.username || '').toLowerCase().includes(q) || (u.nickname || '').toLowerCase().includes(q));

    // 状态筛选
    const f = document.getElementById('userFilter')?.value || 'all';
    if (f === 'enabled') users = users.filter(u => u.enabled);
    if (f === 'disabled') users = users.filter(u => !u.enabled);

    // 排序
    if (userSortField) {
        users.sort((a, b) => {
            let va = a[userSortField], vb = b[userSortField];
            if (userSortField === 'enabled') { va = va ? 1 : 0; vb = vb ? 1 : 0; }
            if (userSortField === 'clockin_count') { va = va || 0; vb = vb || 0; }
            if (userSortField === 'last_clockin') { va = va || ''; vb = vb || ''; }
            return userSortAsc ? (va < vb ? -1 : va > vb ? 1 : 0) : (va > vb ? -1 : va < vb ? 1 : 0);
        });
    }

    if (!users.length) {
        tbody.innerHTML = `<tr><td colspan="9" class="text-center py-10 text-base-content/40">
            <div class="text-3xl mb-2 opacity-30">👥</div>${q || f !== 'all' ? '没有匹配的用户' : '暂无用户，点击"添加用户"按钮'}
        </td></tr>`;
        return;
    }

    tbody.innerHTML = users.map(u => {
        const t = u._today || {};
        return `<tr class="hover:bg-base-200/50 transition-colors">
            <td>
                <div class="font-semibold text-sm">${esc(u.username)}</div>
            </td>
            <td class="text-muted text-xs">${u.nickname ? esc(u.nickname) : '<span class="opacity-30">-</span>'}</td>
            <td>
                <span class="badge badge-sm ${u.enabled ? 'badge-success' : 'badge-ghost'} gap-1">
                    <span class="w-1.5 h-1.5 rounded-full ${u.enabled ? 'bg-success-content' : 'bg-base-content/30'}"></span>
                    ${u.enabled ? '启用' : '禁用'}
                </span>
            </td>
            <td class="text-center">${typeIndicator(t.home?.success ?? null, 'H', '首页')}</td>
            <td class="text-center">${typeIndicator(t.sports?.success ?? null, 'S', '运动')}</td>
            <td class="text-center">${typeIndicator(t.daily?.success ?? null, 'D', '每日')}</td>
            <td class="text-xs text-base-content/50 whitespace-nowrap">${u.last_clockin ? fmtDate(u.last_clockin) : '<span class="opacity-30">从未</span>'}</td>
            <td class="text-center"><span class="font-semibold text-sm">${u.clockin_count || 0}</span></td>
            <td>
                <div class="flex gap-1">
                    <button class="btn btn-success btn-xs" onclick="triggerUserClockin('${u.id}', event)" title="打卡">▶</button>
                    <button class="btn btn-ghost btn-xs" onclick="editUser('${u.id}')" title="编辑">✎</button>
                    <button class="btn btn-ghost btn-xs" onclick="toggleUser('${u.id}')" title="${u.enabled ? '禁用' : '启用'}">${u.enabled ? '⏸' : '⏵'}</button>
                    <button class="btn btn-error btn-xs btn-ghost" onclick="deleteUser('${u.id}')" title="删除">✕</button>
                </div>
            </td>
        </tr>`;
    }).join('');
}

function filterUsers() { renderUserTable(); }

function sortUsers(field) {
    if (userSortField === field) { userSortAsc = !userSortAsc; }
    else { userSortField = field; userSortAsc = true; }
    document.querySelectorAll('[id^="sort-"]').forEach(el => el.textContent = '⇅');
    const icon = document.getElementById(`sort-${field}`);
    if (icon) icon.textContent = userSortAsc ? '↑' : '↓';
    renderUserTable();
}

// ========== 3 类型打卡指标 ==========
/**
 * 渲染单个打卡类型指标 (H=首页, S=运动, D=每日)
 * @param {boolean|null} status - true=成功, false=失败, null=未执行/无数据
 * @param {string} letter - 显示字母
 * @param {string} title - 提示文字
 */
function typeIndicator(status, letter, title) {
    if (status === true) return `<span class="type-indicator success" title="${title} - 成功">${letter}</span>`;
    if (status === false) return `<span class="type-indicator failure" title="${title} - 失败">${letter}</span>`;
    return `<span class="type-indicator pending" title="${title} - 未执行">${letter}</span>`;
}

// ========== 用户抽屉 ==========
function openAddUserDrawer() {
    setText('drawerTitle', '添加用户');
    document.getElementById('userId').value = '';
    document.getElementById('userForm').reset();
    document.getElementById('enabled').checked = true;
    hideConditional();
    // 自动填充密码
    const uInput = document.getElementById('username');
    const pInput = document.getElementById('password');
    uInput.oninput = () => { if (uInput.value.length >= 6) pInput.value = uInput.value.slice(-6); };
    openDrawer('userDrawerOverlay');
}

function editUser(uid) {
    const u = currentUsers.find(x => x.id === uid);
    if (!u) return;
    setText('drawerTitle', '编辑用户');
    document.getElementById('userId').value = u.id;
    document.getElementById('username').value = u.username;
    document.getElementById('password').value = u.password || '';
    document.getElementById('nickname').value = u.nickname || '';
    document.getElementById('enabled').checked = u.enabled;

    // 运动备注
    const st = u.sports_comment_type || 'default';
    document.getElementById('sports_comment_type').value = st;
    onSportsCommentTypeChange();
    if (st === 'custom') document.getElementById('sports_custom_comment').value = u.sports_custom_comment || '';
    else if (st === 'api') setApiSelect('sports_api_provider', 'sports_api_jinrishici', 'sports_api_category_group', u.sports_comment_api);

    // 运动图片
    const si = u.sports_image_type || 'default';
    document.getElementById('sports_image_type').value = si;
    onSportsImageTypeChange();
    if (si === 'api') {
        const p = u.sports_image_provider || 'bing';
        document.getElementById('sports_image_provider').value = ['bing', 'bing_uhd', 'komll', 'loliapi', 'cimuapi'].includes(p) ? p : 'cimuapi';
        onSportsImageProviderChange();
        if (p === 'cimuapi' && u.sports_image_category) document.getElementById('sports_image_category').value = u.sports_image_category;
    }

    // 每日备注
    const dt = u.daily_comment_type || 'default';
    document.getElementById('daily_comment_type').value = dt;
    onDailyCommentTypeChange();
    if (dt === 'custom') document.getElementById('custom_daily_comment').value = u.custom_daily_comment || '';
    else if (dt === 'api') setApiSelect('api_provider', 'daily_comment_api_jinrishici', 'api_category_group', u.daily_comment_api);

    document.getElementById('username').oninput = null;
    openDrawer('userDrawerOverlay');
}

function closeUserDrawer() { closeDrawer('userDrawerOverlay'); }

async function saveUser() {
    const uid = document.getElementById('userId').value;
    const username = document.getElementById('username').value.trim();
    const password = document.getElementById('password').value;
    if (!username || !password) { showToast('请填写用户名和密码', 'error'); return; }

    const body = {
        username, password,
        nickname: document.getElementById('nickname').value.trim(),
        enabled: document.getElementById('enabled').checked,
        sports_comment_type: document.getElementById('sports_comment_type').value
    };

    if (body.sports_comment_type === 'custom') body.sports_custom_comment = document.getElementById('sports_custom_comment').value.trim();
    else if (body.sports_comment_type === 'api') body.sports_comment_api = getSportsApiType();

    const siType = document.getElementById('sports_image_type').value;
    body.sports_image_type = siType;
    if (siType === 'api') {
        body.sports_image_provider = getSportsImageProvider();
        if (body.sports_image_provider === 'cimuapi') body.sports_image_category = document.getElementById('sports_image_category').value;
    }

    const dcType = document.getElementById('daily_comment_type').value;
    body.daily_comment_type = dcType;
    if (dcType === 'custom') body.custom_daily_comment = document.getElementById('custom_daily_comment').value.trim();
    else if (dcType === 'api') body.daily_comment_api = getCurrentApiType();

    try {
        const res = await apiRequest(uid ? `/api/users/${uid}` : '/api/users', { method: uid ? 'PUT' : 'POST', body: JSON.stringify(body) });
        const r = await res.json();
        if (r.success) { showToast(uid ? '用户更新成功' : '用户添加成功', 'success'); closeUserDrawer(); loadUsers(); if (currentPage === 'dashboard') loadStats(); }
        else showToast(r.error || '操作失败', 'error');
    } catch (e) { if (e.message !== 'Unauthorized') showToast('网络错误', 'error'); }
}

async function toggleUser(uid) {
    try {
        const res = await apiRequest(`/api/users/${uid}/toggle`, { method: 'PATCH' });
        const r = await res.json();
        if (r.success) { showToast(r.message || '状态已更新', 'success'); loadUsers(); if (currentPage === 'dashboard') loadStats(); }
        else showToast(r.error || '操作失败', 'error');
    } catch (e) { if (e.message !== 'Unauthorized') showToast('网络错误', 'error'); }
}

async function deleteUser(uid) {
    if (!confirm('确定要删除该用户吗？此操作不可恢复。')) return;
    try {
        const res = await apiRequest(`/api/users/${uid}`, { method: 'DELETE' });
        const r = await res.json();
        if (r.success) { showToast('用户已删除', 'success'); loadUsers(); if (currentPage === 'dashboard') loadStats(); }
        else showToast(r.error || '删除失败', 'error');
    } catch (e) { if (e.message !== 'Unauthorized') showToast('网络错误', 'error'); }
}

// ========== 打卡操作 ==========
async function triggerAllClockin() {
    if (isClockinRunning) { showToast('打卡任务正在执行中', 'error'); return; }
    if (!confirm('确定要为所有启用的用户执行打卡吗？')) return;
    isClockinRunning = true;
    showToast('正在执行打卡任务...', 'info');
    try {
        const res = await apiRequest('/api/clockin/trigger', { method: 'POST' });
        const r = await res.json();
        if (r.success) showToast(`打卡完成！成功 ${r.data?.success_count || 0}，失败 ${r.data?.failure_count || 0}`, 'success');
        else showToast(r.error || '打卡失败', 'error');
        loadDashboard();
    } catch (e) { if (e.message !== 'Unauthorized') showToast('打卡请求失败', 'error'); }
    finally { isClockinRunning = false; }
}

async function triggerUserClockin(uid, ev) {
    if (ev) ev.stopPropagation();
    try {
        showToast('正在打卡...', 'info');
        const res = await apiRequest(`/api/clockin/user/${uid}`, { method: 'POST' });
        const r = await res.json();
        if (r.success) { showToast('打卡成功', 'success'); loadUsers(); }
        else showToast(r.error || '打卡失败', 'error');
    } catch (e) { if (e.message !== 'Unauthorized') showToast('打卡请求失败', 'error'); }
}

async function cleanupOldRecords() {
    if (!confirm('确定要清理过期的打卡记录吗？')) return;
    try {
        const res = await apiRequest('/api/maintenance/cleanup', { method: 'POST' });
        const r = await res.json();
        if (r.success) { showToast(r.message || '清理完成', 'success'); if (currentPage === 'dashboard') loadDashboardRecords(); if (currentPage === 'records') loadRecords(); }
        else showToast(r.error || '清理失败', 'error');
    } catch (e) { if (e.message !== 'Unauthorized') showToast('清理失败', 'error'); }
}

// ========== 打卡记录页 ==========
async function loadRecords() {
    const c = document.getElementById('recordsList');
    c.innerHTML = '<div class="text-base-content/40 text-center py-10">加载中...</div>';
    try {
        const res = await apiRequest(`/api/clockin/results?range=${recordRange}`);
        const data = await res.json();
        currentRecords = data.data.results || [];
        renderRecords();
    } catch (e) {
        if (e.message !== 'Unauthorized') c.innerHTML = '<div class="text-base-content/40 text-center py-10">加载失败</div>';
    }
}

function setRecordRange(range, btn) {
    recordRange = range;
    document.querySelectorAll('[data-range]').forEach(b => b.classList.remove('btn-active'));
    if (btn) btn.classList.add('btn-active');
    loadRecords();
}

function filterRecords() { renderRecords(); }

function renderRecords() {
    const c = document.getElementById('recordsList');
    let records = [...currentRecords];

    const uf = document.getElementById('recordUserFilter')?.value || 'all';
    if (uf !== 'all') records = records.filter(r => r.username === uf);
    const sf = document.getElementById('recordStatusFilter')?.value || 'all';
    if (sf === 'success') records = records.filter(r => r.success);
    if (sf === 'failure') records = records.filter(r => !r.success);

    if (!records.length) {
        c.innerHTML = '<div class="text-base-content/40 text-center py-10"><div class="text-3xl mb-2 opacity-30">📋</div>暂无打卡记录</div>';
        return;
    }

    // 按日期分组
    const groups = {};
    records.forEach(r => { const d = fmtDate(r.created_at); (groups[d] ||= []).push(r); });
    const today = fmtDate(new Date().toISOString());

    let html = '';
    Object.entries(groups).forEach(([date, items]) => {
        const ok = items.filter(r => r.success).length;
        html += `<div class="flex items-center gap-3 py-3 mt-2 first:mt-0">
            <span class="font-semibold text-sm">${date}</span>
            ${date === today ? '<span class="badge badge-primary badge-xs">今天</span>' : ''}
            <div class="flex-1 h-px bg-base-300"></div>
            <span class="text-xs text-base-content/50">${ok}/${items.length} 成功</span>
        </div>`;
        html += items.map(r => renderRecordCard(r)).join('');
    });
    c.innerHTML = html;
}

function renderRecordCard(r) {
    const ok = r.success;
    const d = r.details || {};
    return `<div class="collapse collapse-arrow ${ok ? 'border-l-3 border-l-success' : 'border-l-3 border-l-error'} bg-surface border border-subtle/50 mb-2 rounded-xl" style="border-left-width:3px">
        <input type="checkbox" class="peer">
        <div class="collapse-title flex items-center justify-between py-3 pl-4 pr-12 min-h-0">
            <div class="flex items-center gap-3 flex-1 min-w-0">
                <span class="font-semibold text-sm truncate">${esc(r.username)}</span>
                ${r.nickname ? `<span class="text-xs text-muted truncate">(${esc(r.nickname)})</span>` : ''}
                <span class="text-xs text-muted whitespace-nowrap">${fmtTime(r.created_at)}</span>
                <div class="flex gap-1 ml-1">
                    ${typeIndicator(d.home?.success ?? null, 'H', '首页')}
                    ${typeIndicator(d.sports?.success ?? null, 'S', '运动')}
                    ${typeIndicator(d.daily?.success ?? null, 'D', '每日')}
                </div>
            </div>
            <span class="badge badge-sm ${ok ? 'badge-success' : 'badge-error'} shrink-0 ml-2">${ok ? '成功' : '失败'}</span>
        </div>
        <div class="collapse-content px-4 pb-3">
            <div class="grid grid-cols-1 sm:grid-cols-3 gap-2 mt-2">
                <div class="bg-base-200 rounded-lg p-3">
                    <div class="text-[10px] text-muted uppercase tracking-wider mb-1">首页打卡</div>
                    <div class="text-sm">${d.home ? (d.home.success ? '<span class="text-success font-medium">✓ 成功</span>' : '<span class="text-error font-medium">✗ 失败</span>') : '<span class="text-muted">未执行</span>'}</div>
                </div>
                <div class="bg-base-200 rounded-lg p-3">
                    <div class="text-[10px] text-muted uppercase tracking-wider mb-1">运动打卡</div>
                    <div class="text-sm">${d.sports ? (d.sports.success ? '<span class="text-success font-medium">✓ 成功</span>' : '<span class="text-error font-medium">✗ 失败</span>') : '<span class="text-muted">未执行</span>'}</div>
                    ${r.sports_comment ? `<div class="text-[11px] text-muted mt-1">备注: ${esc(r.sports_comment)}</div>` : ''}
                </div>
                <div class="bg-base-200 rounded-lg p-3">
                    <div class="text-[10px] text-muted uppercase tracking-wider mb-1">每日打卡</div>
                    <div class="text-sm">${d.daily ? (d.daily.success ? '<span class="text-success font-medium">✓ 成功</span>' : '<span class="text-error font-medium">✗ 失败</span>') : '<span class="text-muted">未执行</span>'}</div>
                    ${r.daily_comment ? `<div class="text-[11px] text-muted mt-1">备注: ${esc(r.daily_comment)}</div>` : ''}
                </div>
            </div>
            ${r.error ? `<div class="mt-3 p-3 bg-red-50 border border-red-100 rounded-lg text-sm text-error">${esc(r.error)}</div>` : ''}
        </div>
    </div>`;
}

function updateRecordUserFilter() {
    const sel = document.getElementById('recordUserFilter');
    if (!sel) return;
    const cur = sel.value;
    sel.innerHTML = '<option value="all">全部用户</option>' + currentUsers.map(u => `<option value="${esc(u.username)}">${esc(u.username)}</option>`).join('');
    sel.value = cur || 'all';
}

// ========== Worker API 管理 ==========
async function loadWorkerApis() {
    try {
        const res = await apiRequest('/api/worker-apis');
        const data = await res.json();
        currentWorkerApis = data.data || [];
        renderWorkerApis();
    } catch (e) {
        if (e.message !== 'Unauthorized') document.getElementById('workerApisGrid').innerHTML = '<div class="text-base-content/40 text-center py-10 col-span-full">加载失败</div>';
    }
}

function renderWorkerApis() {
    const c = document.getElementById('workerApisGrid');
    if (!currentWorkerApis.length) {
        c.innerHTML = '<div class="text-base-content/40 text-center py-10 col-span-full"><div class="text-3xl mb-2 opacity-30">🔗</div>暂无 Worker API</div>';
        return;
    }
    c.innerHTML = currentWorkerApis.map(api => {
        const total = api.total_requests || 0, ok = api.total_success || 0;
        const rate = total ? Math.round((ok / total) * 100) : 0;
        const isAvailable = api.available !== false;
        const badgeCls = !api.enabled ? 'badge-ghost' : !isAvailable ? 'badge-error' : 'badge-success';
        const statusText = !api.enabled ? '已禁用' : !isAvailable ? '不可用' : '运行中';

        return `<div class="card api-card bg-base-200 border border-base-300 shadow-md">
            <div class="card-body p-5">
                <div class="flex items-center justify-between mb-2">
                    <h4 class="font-bold flex items-center gap-2">${api.enabled ? '<span class="w-2 h-2 rounded-full bg-success inline-block"></span>' : '<span class="w-2 h-2 rounded-full bg-base-content/20 inline-block"></span>'}${esc(api.name || '未命名')}</h4>
                    <span class="badge badge-sm ${badgeCls}">${statusText}</span>
                </div>
                ${api.note ? `<div class="text-xs text-base-content/50 mb-2">📝 ${esc(api.note)}</div>` : ''}
                <div class="text-xs text-base-content/50 font-mono bg-base-300 rounded-lg px-3 py-2 mb-3 truncate">${esc(api.url || '-')}</div>
                <div class="grid grid-cols-3 gap-2 mb-3">
                    <div class="text-center bg-base-300/50 rounded-lg p-2">
                        <div class="font-bold text-lg">${total}</div>
                        <div class="text-[10px] text-base-content/40">请求</div>
                    </div>
                    <div class="text-center bg-base-300/50 rounded-lg p-2">
                        <div class="font-bold text-lg text-success">${ok}</div>
                        <div class="text-[10px] text-base-content/40">成功</div>
                    </div>
                    <div class="text-center bg-base-300/50 rounded-lg p-2">
                        <div class="font-bold text-lg ${rate >= 80 ? 'text-success' : rate >= 50 ? 'text-warning' : 'text-error'}">${rate}%</div>
                        <div class="text-[10px] text-base-content/40">成功率</div>
                    </div>
                </div>
                <progress class="progress ${rate >= 80 ? 'progress-success' : rate >= 50 ? 'progress-warning' : 'progress-error'} w-full mb-3" value="${rate}" max="100"></progress>
                <div class="card-actions flex gap-2">
                    <button class="btn btn-sm btn-outline flex-1" onclick="testWorkerApi('${api.id}')">🔍 测试</button>
                    <button class="btn btn-sm btn-ghost flex-1" onclick="editWorkerApi('${api.id}')">✎ 编辑</button>
                    <button class="btn btn-sm btn-ghost flex-1" onclick="resetWorkerApi('${api.id}')">↻ 重置</button>
                    <button class="btn btn-sm btn-error btn-ghost flex-1" onclick="deleteWorkerApi('${api.id}', '${esc(api.name || '')}')">✕</button>
                </div>
            </div>
        </div>`;
    }).join('');
}

function openAddWorkerApiDrawer() {
    setText('workerApiDrawerTitle', '添加 Worker API');
    document.getElementById('workerApiId').value = '';
    ['workerApiName', 'workerApiUrl', 'workerApiToken', 'workerApiNote'].forEach(id => document.getElementById(id).value = '');
    document.getElementById('workerApiEnabled').checked = true;
    openDrawer('workerApiDrawerOverlay');
}

function editWorkerApi(id) {
    const api = currentWorkerApis.find(a => a.id === id);
    if (!api) return;
    setText('workerApiDrawerTitle', '编辑 Worker API');
    document.getElementById('workerApiId').value = api.id;
    document.getElementById('workerApiName').value = api.name || '';
    document.getElementById('workerApiUrl').value = api.url || '';
    document.getElementById('workerApiToken').value = api.token || '';
    document.getElementById('workerApiNote').value = api.note || '';
    document.getElementById('workerApiEnabled').checked = api.enabled;
    openDrawer('workerApiDrawerOverlay');
}

function closeWorkerApiDrawer() { closeDrawer('workerApiDrawerOverlay'); }

async function saveWorkerApi() {
    const apiId = document.getElementById('workerApiId').value;
    const name = document.getElementById('workerApiName').value.trim();
    const url = document.getElementById('workerApiUrl').value.trim();
    const token = document.getElementById('workerApiToken').value;
    if (!name || !url || !token) { showToast('请填写完整的 API 信息', 'error'); return; }

    const body = { name, url: normalizeUrl(url), token, note: document.getElementById('workerApiNote').value.trim(), enabled: document.getElementById('workerApiEnabled').checked };
    try {
        const res = await apiRequest(apiId ? `/api/worker-apis/${apiId}` : '/api/worker-apis', { method: apiId ? 'PUT' : 'POST', body: JSON.stringify(body) });
        const r = await res.json();
        if (r.success) { showToast(apiId ? 'API 更新成功' : 'API 添加成功', 'success'); closeWorkerApiDrawer(); loadWorkerApis(); }
        else showToast(r.error || '操作失败', 'error');
    } catch (e) { if (e.message !== 'Unauthorized') showToast('网络错误', 'error'); }
}

async function testWorkerApi(id) {
    try {
        showToast('正在测试连接...', 'info');
        const res = await apiRequest(`/api/worker-apis/${id}/test`, { method: 'POST' });
        const r = await res.json();
        showToast(r.success ? `连接成功！延迟: ${r.data?.latency || '-'}ms` : (r.error || '连接失败'), r.success ? 'success' : 'error');
        loadWorkerApis();
    } catch (e) { if (e.message !== 'Unauthorized') showToast('测试失败', 'error'); }
}

async function testAllWorkerApis() {
    showToast('正在测试所有 API...', 'info');
    const results = await Promise.allSettled(currentWorkerApis.map(api => apiRequest(`/api/worker-apis/${api.id}/test`, { method: 'POST' })));
    let ok = 0;
    for (const r of results) { if (r.status === 'fulfilled') { const d = await r.value.json(); if (d.success) ok++; } }
    showToast(`测试完成: ${ok}/${currentWorkerApis.length} 可用`, ok === currentWorkerApis.length ? 'success' : 'error');
    loadWorkerApis();
}

async function resetWorkerApi(id) {
    try {
        const res = await apiRequest(`/api/worker-apis/${id}/reset`, { method: 'POST' });
        const r = await res.json();
        if (r.success) { showToast('API 状态已重置', 'success'); loadWorkerApis(); }
        else showToast(r.error || '重置失败', 'error');
    } catch (e) { if (e.message !== 'Unauthorized') showToast('重置失败', 'error'); }
}

async function deleteWorkerApi(id, name) {
    if (!confirm(`确定要删除 Worker API "${name}" 吗？`)) return;
    try {
        const res = await apiRequest(`/api/worker-apis/${id}`, { method: 'DELETE' });
        const r = await res.json();
        if (r.success) { showToast('API 已删除', 'success'); loadWorkerApis(); }
        else showToast(r.error || '删除失败', 'error');
    } catch (e) { if (e.message !== 'Unauthorized') showToast('删除失败', 'error'); }
}

// ========== 系统设置 ==========
async function loadSettings() {
    try {
        const res = await apiRequest('/api/config');
        const data = await res.json();
        const c = data.data;
        setVal('configApiRequestDelay', c.api_request_delay ?? 500);
        setVal('configClockinTypeDelay', c.clockin_type_delay ?? 2);
        setVal('configClockinRetryCount', c.clockin_retry_count ?? 3);
        setVal('configClockinRetryDelay', c.clockin_retry_delay ?? 3);
        setVal('configClockinTimeout', c.clockin_timeout ?? 60);
        setVal('configClockinRateLimitDelay', c.clockin_rate_limit_delay ?? 10);

        const se = c.schedule_enabled !== false;
        document.getElementById('configScheduleEnabled').checked = se;
        updateScheduleConfigVisibility(se);
        if (c.schedule_time) setVal('configScheduleTime', c.schedule_time);
        setVal('configScheduleRetryCount', c.schedule_retry_count ?? 3);
        setVal('configScheduleRetryDelay', c.schedule_retry_delay ?? 60);
        updateTimePreview();
        startScheduleCountdown();
    } catch (e) { if (e.message !== 'Unauthorized') console.error('[settings]', e); }
}

async function saveConfig() {
    const cfg = {
        api_request_delay: intVal('configApiRequestDelay'),
        clockin_type_delay: intVal('configClockinTypeDelay'),
        clockin_retry_count: intVal('configClockinRetryCount'),
        clockin_retry_delay: intVal('configClockinRetryDelay'),
        clockin_timeout: intVal('configClockinTimeout'),
        clockin_rate_limit_delay: intVal('configClockinRateLimitDelay'),
        schedule_enabled: document.getElementById('configScheduleEnabled').checked,
        schedule_time: document.getElementById('configScheduleTime').value,
        schedule_retry_count: intVal('configScheduleRetryCount'),
        schedule_retry_delay: intVal('configScheduleRetryDelay')
    };
    try {
        const res = await apiRequest('/api/config', { method: 'PUT', body: JSON.stringify(cfg) });
        const r = await res.json();
        if (r.success) { showToast('配置已保存', 'success'); updateStatusBar(); }
        else showToast(r.error || '保存失败', 'error');
    } catch (e) { if (e.message !== 'Unauthorized') showToast('保存失败', 'error'); }
}

function updateScheduleConfigVisibility(en) {
    const el = document.getElementById('scheduleConfig');
    if (el) el.classList.toggle('hidden', !en);
}

function updateTimePreview() {
    const inp = document.getElementById('configScheduleTime');
    if (!inp) return;
    const [h, m] = inp.value.split(':').map(Number);
    setText('nextRunTime', `${pad(h)}:${pad(m)}`);
    let uh = h - 8; if (uh < 0) uh += 24;
    setText('utcTime', `${pad(uh)}:${pad(m)}`);
    setText('cronExpression', `0 ${pad(m)} ${pad(uh)} * * *`);
}

function setQuickTime(t) { document.getElementById('configScheduleTime').value = t; updateTimePreview(); }

async function testScheduleTask() {
    try {
        showToast('正在测试...', 'info');
        const res = await apiRequest('/api/config/test-schedule', { method: 'POST' });
        const r = await res.json();
        showToast(r.success ? '测试任务已触发' : (r.error || '测试失败'), r.success ? 'success' : 'error');
    } catch (e) { if (e.message !== 'Unauthorized') showToast('测试失败', 'error'); }
}

async function refreshScheduleInfo() {
    try { await apiRequest('/api/config/schedule'); showToast('状态已刷新', 'success'); }
    catch (e) { if (e.message !== 'Unauthorized') showToast('刷新失败', 'error'); }
}

function startScheduleCountdown() {
    if (scheduleCountdownTimer) clearInterval(scheduleCountdownTimer);
    scheduleCountdownTimer = setInterval(() => {
        const el = document.getElementById('scheduleCountdown');
        const inp = document.getElementById('configScheduleTime');
        if (!el || !inp) return;
        const [h, m] = inp.value.split(':').map(Number);
        const now = new Date(), tgt = new Date();
        tgt.setHours(h, m, 0, 0);
        if (tgt <= now) tgt.setDate(tgt.getDate() + 1);
        const diff = tgt - now;
        const hh = Math.floor(diff / 3600000), mm = Math.floor((diff % 3600000) / 60000), ss = Math.floor((diff % 60000) / 1000);
        el.textContent = `${pad(hh)}h ${pad(mm)}m ${pad(ss)}s`;
    }, 1000);
}

// ========== 数据导入导出 ==========
async function exportConfig() {
    try {
        const res = await apiRequest('/api/config/export');
        const data = await res.json();
        const blob = new Blob([JSON.stringify(data.data, null, 2)], { type: 'application/json' });
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `zk-config-${new Date().toISOString().split('T')[0]}.json`;
        a.click(); URL.revokeObjectURL(a.href);
        showToast('配置已导出', 'success');
    } catch (e) { if (e.message !== 'Unauthorized') showToast('导出失败', 'error'); }
}

async function importConfig(ev) {
    const file = ev.target.files[0];
    if (!file) return;
    try {
        const data = JSON.parse(await file.text());
        const res = await apiRequest('/api/config/import', { method: 'POST', body: JSON.stringify(data) });
        const r = await res.json();
        if (r.success) { showToast('配置导入成功', 'success'); loadCurrentPage(); }
        else showToast(r.error || '导入失败', 'error');
    } catch (e) { showToast('导入失败：文件格式错误', 'error'); }
    ev.target.value = '';
}

// ========== 状态栏 ==========
async function updateStatusBar() {
    try {
        const res = await apiRequest('/api/config/schedule');
        const data = await res.json();
        if (data.success && data.data?.next_run_time) setText('statusNextRun', `下次打卡: ${fmtTime(data.data.next_run_time)}`);
    } catch {}
    try {
        const res = await apiRequest('/api/worker-apis');
        const data = await res.json();
        const apis = data.data || [];
        const healthy = apis.filter(a => a.enabled).length;
        setText('statusWorkerHealth', `Worker: ${healthy}/${apis.length} 健康`);
    } catch {}
}

// ========== Drawer 通用 ==========
function openDrawer(id) {
    document.getElementById(id)?.classList.add('open');
    document.body.style.overflow = 'hidden';
}

function closeDrawer(id) {
    document.getElementById(id)?.classList.remove('open');
    document.body.style.overflow = '';
}

document.addEventListener('keydown', e => {
    if (e.key === 'Escape') {
        document.querySelectorAll('.drawer-overlay.open').forEach(el => el.classList.remove('open'));
        document.body.style.overflow = '';
    }
});

// ========== 条件字段切换 ==========
function hideConditional() {
    ['sports_custom_group', 'sports_api_group', 'sports_image_api_group', 'custom_content_group', 'api_select_group'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.classList.add('hidden');
    });
}

function onDailyCommentTypeChange() {
    const t = document.getElementById('daily_comment_type').value;
    toggle('custom_content_group', t === 'custom');
    toggle('api_select_group', t === 'api');
    if (t === 'api') onApiProviderChange();
}

function onSportsCommentTypeChange() {
    const t = document.getElementById('sports_comment_type').value;
    toggle('sports_custom_group', t === 'custom');
    toggle('sports_api_group', t === 'api');
    if (t === 'api') onSportsApiProviderChange();
}

function onApiProviderChange() {
    toggle('api_category_group', document.getElementById('api_provider').value === 'jinrishici');
}

function onSportsApiProviderChange() {
    toggle('sports_api_category_group', document.getElementById('sports_api_provider').value === 'jinrishici');
}

function onSportsImageTypeChange() {
    const t = document.getElementById('sports_image_type').value;
    toggle('sports_image_api_group', t === 'api');
    document.getElementById('sports_image_category_group')?.classList.add('hidden');
    if (t === 'api') onSportsImageProviderChange();
}

function onSportsImageProviderChange() {
    toggle('sports_image_category_group', document.getElementById('sports_image_provider').value === 'cimuapi');
}

function getCurrentApiType() {
    const p = document.getElementById('api_provider').value;
    if (p === 'jinrishici') return document.getElementById('daily_comment_api_jinrishici')?.value || 'poetry_all';
    return { hitokoto: 'hitokoto_all', yuanmeng: 'yuanmeng_default', klapi: 'klapi_default' }[p] || 'poetry_all';
}

function getSportsApiType() {
    const p = document.getElementById('sports_api_provider').value;
    if (p === 'jinrishici') return document.getElementById('sports_api_jinrishici')?.value || 'poetry_all';
    return { hitokoto: 'hitokoto_all', yuanmeng: 'yuanmeng_default', klapi: 'klapi_default' }[p] || 'poetry_all';
}

function getSportsImageProvider() {
    return document.getElementById('sports_image_type').value === 'default' ? 'bing' : document.getElementById('sports_image_provider').value;
}

function setApiSelect(pid, jid, gid, apiType) {
    if (!apiType) return;
    if (apiType.startsWith('poetry_')) {
        document.getElementById(pid).value = 'jinrishici';
        document.getElementById(jid).value = apiType;
        document.getElementById(gid).classList.remove('hidden');
    } else {
        const map = { hitokoto_: 'hitokoto', yuanmeng_: 'yuanmeng', klapi_: 'klapi' };
        const provider = Object.entries(map).find(([k]) => apiType.startsWith(k))?.[1] || 'jinrishici';
        document.getElementById(pid).value = provider;
        document.getElementById(gid).classList.add('hidden');
    }
}

// ========== 显示文本 ==========
function formatApiName(apiType) {
    if (!apiType) return '未知';
    if (apiType.startsWith('cenguigui_')) return '随机一言';
    if (apiType.startsWith('yuanmeng_')) return '远梦API';
    if (apiType.startsWith('klapi_')) return 'KLapi';
    if (apiType.startsWith('hitokoto_')) return '一言';
    if (apiType.startsWith('poetry_')) {
        const rem = apiType.replace('poetry_', '');
        if (!rem.includes('_')) {
            const m = { all: '全部', shuqing: '抒情', siji: '四季', shanshui: '山水', tianqi: '天气', renwu: '人物', rensheng: '人生', shenghuo: '生活', jieri: '节日', dongwu: '动物', zhiwu: '植物', shiwu: '食物' };
            return '今日诗词（' + (m[rem] || '全部') + '）';
        }
        const [main, sub] = rem.split('_');
        const mainN = { shuqing: '抒情', siji: '四季', shanshui: '山水', tianqi: '天气', renwu: '人物', rensheng: '人生', shenghuo: '生活', jieri: '节日', dongwu: '动物', zhiwu: '植物', shiwu: '食物' };
        const subN = { aiqing: '爱情', youqing: '友情', libie: '离别', sinian: '思念', sixiang: '思乡', shanggan: '伤感', gudu: '孤独', guiyuan: '闺怨', daowang: '悼亡', huaigu: '怀古', aiguo: '爱国', ganen: '感恩', chuntian: '春天', xiatian: '夏天', qiutian: '秋天', dongtian: '冬天', lushan: '庐山', taishan: '泰山', jianghe: '江河', changjiang: '长江', huanghe: '黄河', xihu: '西湖', pubu: '瀑布', xiefeng: '写风', xieyun: '写云', xieyu: '写雨', xiexue: '写雪', caihong: '彩虹', taiyang: '太阳', yueliang: '月亮', xingxing: '星星', nvzi: '女子', fuqin: '父亲', muqin: '母亲', laoshi: '老师', ertong: '儿童', lizhi: '励志', zheli: '哲理', qingchun: '青春', shiguang: '时光', mengxiang: '梦想', dushu: '读书', zhanzheng: '战争', xiangcun: '乡村', tianyuan: '田园', biansai: '边塞', xieqiao: '写桥', chunjie: '春节', yuanxiaojie: '元宵节', hanshijie: '寒食节', qingmingjie: '清明节', duanwujie: '端午节', qixijie: '七夕节', zhongqiujie: '中秋节', chongyangjie: '重阳节', xieniao: '写鸟', xiema: '写马', xiemao: '写猫', meihua: '梅花', lihua: '梨花', taohua: '桃花', hehua: '荷花', juhua: '菊花', liushu: '柳树', yezi: '叶子', zhuzi: '竹子', xiejiu: '写酒', xiecha: '写茶', lizhi: '荔枝' };
        return '今日诗词（' + (mainN[main] || main) + '·' + (subN[sub] || sub) + '）';
    }
    return '今日诗词';
}

function getDailyCommentDisplay(u) {
    const t = u.daily_comment_type || 'default';
    const m = { default: '默认文案', custom: '自定义', api: 'API 接口' };
    let d = m[t] || '默认';
    if (t === 'custom' && u.custom_daily_comment) d += ' - ' + u.custom_daily_comment.substring(0, 15) + (u.custom_daily_comment.length > 15 ? '...' : '');
    else if (t === 'api' && u.daily_comment_api) d += ' - ' + formatApiName(u.daily_comment_api);
    return d;
}

function getSportsCommentDisplay(u) {
    const t = u.sports_comment_type || 'default';
    const m = { default: '默认文案', custom: '自定义', api: 'API 接口' };
    let d = m[t] || '默认';
    if (t === 'custom' && u.sports_custom_comment) d += ' - ' + u.sports_custom_comment.substring(0, 15) + (u.sports_custom_comment.length > 15 ? '...' : '');
    else if (t === 'api' && u.sports_comment_api) d += ' - ' + formatApiName(u.sports_comment_api);
    return d;
}

// ========== 工具函数 ==========
function esc(t) { if (!t) return ''; const d = document.createElement('div'); d.textContent = t; return d.innerHTML; }
function setText(id, v) { const el = document.getElementById(id); if (el) el.textContent = v; }
function setVal(id, v) { const el = document.getElementById(id); if (el) el.value = v; }
function intVal(id) { return parseInt(document.getElementById(id)?.value || '0'); }
function toggle(id, show) { const el = document.getElementById(id); if (el) el.classList.toggle('hidden', !show); }
function pad(n) { return String(n).padStart(2, '0'); }
function normalizeUrl(u) { if (!u) return ''; u = u.trim(); return u.startsWith('http') ? u : 'https://' + u; }
function autoFormatUrl(inp) { if (inp.value && !inp.value.startsWith('http')) inp.value = 'https://' + inp.value.trim(); }
function fmtDate(d) { try { return new Date(d).toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' }); } catch { return d || ''; } }
function fmtTime(d) { try { return new Date(d).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' }); } catch { return d || ''; } }

function showToast(msg, type = 'info') {
    const t = document.getElementById('toast');
    t.innerHTML = `<div class="toast-content ${type}">${msg}</div>`;
    t.classList.add('show');
    setTimeout(() => t.classList.remove('show'), 3000);
}

function logout() {
    if (!confirm('确定要退出登录吗？')) return;
    apiRequest('/api/auth/logout', { method: 'POST' }).catch(() => {});
    localStorage.removeItem('auth_token');
    window.location.href = window.ADMIN_PATH || '/admin';
}
