import { apiRequest } from "../core/api.js";
import { beijingToday, categoryResult, escapeHtml, formatDuration, formatFullDateTime, initials } from "../core/format.js";
import { icon } from "../core/icons.js";
import { filterRecords } from "../core/state.js";


export function createRecordsPage(shell) {
  let records = [];
  let users = [];
  let summary = null;
  const filters = { date: beijingToday(), status: "all", userId: "all" };

  function resultTypes(record) {
    return `<div class="result-types" aria-label="首页、运动、日精进结果"><span class="result-type ${categoryResult(record, "home")}" title="首页">首</span><span class="result-type ${categoryResult(record, "sports")}" title="运动">运</span><span class="result-type ${categoryResult(record, "daily")}" title="日精进">日</span></div>`;
  }

  function desktopRows(list) {
    if (!list.length) return `<tr><td colspan="6"><div class="empty-state"><div>${icon("records")}<h3>没有打卡记录</h3><p>当前日期和筛选条件下没有结果</p></div></div></td></tr>`;
    return list.map((record) => `<tr><td><div class="identity"><span class="avatar">${initials(record)}</span><span><strong>${escapeHtml(record.nickname || record.username)}</strong><small>${escapeHtml(record.username)}</small></span></div></td><td><span class="badge ${record.success ? "success" : "failure"}">${record.success ? "成功" : "失败"}</span></td><td>${resultTypes(record)}</td><td>${formatFullDateTime(record.timestamp)}</td><td>${formatDuration(record.duration_ms)}</td><td><div class="row-actions"><button class="table-action" data-action="record-detail" data-record-id="${escapeHtml(record.id)}" title="查看详情">${icon("chevron")}</button></div></td></tr>`).join("");
  }

  function mobileCards(list) {
    if (!list.length) return `<div class="empty-state"><div>${icon("records")}<h3>没有打卡记录</h3><p>当前日期和筛选条件下没有结果</p></div></div>`;
    return list.map((record) => `<article class="mobile-card"><div class="mobile-card-head"><div class="identity"><span class="avatar">${initials(record)}</span><span><strong>${escapeHtml(record.nickname || record.username)}</strong><small>${formatFullDateTime(record.timestamp)}</small></span></div><span class="badge ${record.success ? "success" : "failure"}">${record.success ? "成功" : "失败"}</span></div><div class="mobile-card-body"><div><small>分类结果</small>${resultTypes(record)}</div><div><small>耗时</small><span>${formatDuration(record.duration_ms)}</span></div></div><div class="mobile-card-actions"><button class="button secondary" data-action="record-detail" data-record-id="${escapeHtml(record.id)}">查看详情${icon("chevron")}</button></div></article>`).join("");
  }

  function renderLists() {
    const list = filterRecords(records, filters);
    const count = document.querySelector("#record-count");
    if (count) count.textContent = `${list.length} 条`;
    const desktop = document.querySelector("#records-desktop-body");
    if (desktop) desktop.innerHTML = desktopRows(list);
    const mobile = document.querySelector("#records-mobile-list");
    if (mobile) mobile.innerHTML = mobileCards(list);
  }

  function render() {
    shell.content.innerHTML = `<div class="page-stack"><div class="toolbar"><div class="filters"><input class="field" style="width:auto" data-filter="record-date" type="date" value="${escapeHtml(filters.date)}"><select class="select-field" data-filter="record-status"><option value="all">全部结果</option><option value="success" ${filters.status === "success" ? "selected" : ""}>成功</option><option value="failure" ${filters.status === "failure" ? "selected" : ""}>失败</option></select><select class="select-field" data-filter="record-user"><option value="all">全部用户</option>${users.map((user) => `<option value="${escapeHtml(user.id)}" ${filters.userId === user.id ? "selected" : ""}>${escapeHtml(user.nickname || user.username)}</option>`).join("")}</select></div><span class="badge" id="record-count">0 条</span></div>${summary ? `<section class="metric-grid">${["total_users", "success_count", "failure_count"].map((key, index) => `<article class="metric-card ${index === 1 ? "success" : index === 2 ? "danger" : ""}"><header><span>${["执行用户", "成功", "失败"][index]}</span>${icon(index === 1 ? "check" : index === 2 ? "alert" : "users")}</header><strong class="metric-value">${Number(summary[key] || 0)}</strong><span class="metric-foot">${escapeHtml(filters.date)}</span></article>`).join("")}<article class="metric-card"><header><span>分类成功</span>${icon("records")}</header><strong class="metric-value">${Number(summary.home_success || 0)}/${Number(summary.sports_success || 0)}/${Number(summary.daily_success || 0)}</strong><span class="metric-foot">首页 / 运动 / 日精进</span></article></section>` : ""}<section class="panel"><header class="panel-header"><div><h2>执行明细</h2><p>点击任意记录查看三类结果和内容使用详情</p></div></header><div class="panel-body flush"><div class="desktop-table"><table class="data-table"><thead><tr><th>用户</th><th>结果</th><th>分类摘要</th><th>执行时间</th><th>耗时</th><th></th></tr></thead><tbody id="records-desktop-body"></tbody></table></div><div class="mobile-card-list" id="records-mobile-list"></div></div></section></div>`;
    renderLists();
    shell.ready();
  }

  function showDetail(record) {
    if (!record) return;
    const detailJson = JSON.stringify(record.details || {}, null, 2);
    shell.openDrawer({
      eyebrow: record.success ? "执行成功" : "执行失败",
      title: record.nickname || record.username,
      html: `<div class="detail-grid"><div class="detail-item"><small>足下账号</small><strong>${escapeHtml(record.username)}</strong></div><div class="detail-item"><small>执行时间</small><span>${formatFullDateTime(record.timestamp)}</span></div><div class="detail-item"><small>触发方式</small><span>${record.triggered_by === "scheduled" ? "定时任务" : "手动执行"}</span></div><div class="detail-item"><small>总耗时</small><span>${formatDuration(record.duration_ms)}</span></div></div>${record.error ? `<div class="detail-section"><h3>失败原因</h3><div class="notice danger">${escapeHtml(record.error)}</div></div>` : ""}<div class="detail-section"><h3>三类结果</h3>${resultTypes(record)}</div><div class="detail-section"><h3>使用内容</h3><div class="detail-grid"><div class="detail-item"><small>运动文案</small><span>${escapeHtml(record.sports_comment || "—")}</span></div><div class="detail-item"><small>日精进文案</small><span>${escapeHtml(record.daily_comment || "—")}</span></div><div class="detail-item"><small>图片来源</small><span>${escapeHtml(record.sports_image_provider || "Worker 默认")}</span></div><div class="detail-item"><small>图片分类</small><span>${escapeHtml(record.sports_image_category || "—")}</span></div></div></div><div class="detail-section"><h3>原始结果</h3><pre class="detail-json">${escapeHtml(detailJson)}</pre></div>`,
    });
  }

  async function loadRecords({ silent = false } = {}) {
    if (!shell.isRouteActive("records")) return;
    if (!silent) shell.loading("正在加载打卡记录");
    try {
      const response = await apiRequest(`/api/clockin/results?date=${encodeURIComponent(filters.date)}&range=day`);
      if (!shell.isRouteActive("records")) return;
      records = response.data?.results || [];
      summary = response.data?.summary || null;
      render();
    } catch (error) {
      if (!shell.isRouteActive("records") || error?.name === "AbortError") return;
      if (!silent) shell.error(error);
      else shell.toast(error.message, "error");
    }
  }

  async function load({ silent = false } = {}) {
    if (!shell.isRouteActive("records")) return;
    if (!silent) shell.loading("正在加载打卡记录");
    try {
      const [userResponse, resultResponse] = await Promise.all([
        apiRequest("/api/users"),
        apiRequest(`/api/clockin/results?date=${encodeURIComponent(filters.date)}&range=day`),
      ]);
      if (!shell.isRouteActive("records")) return;
      users = userResponse.data || [];
      records = resultResponse.data?.results || [];
      summary = resultResponse.data?.summary || null;
      render();
    } catch (error) {
      if (!shell.isRouteActive("records") || error?.name === "AbortError") return;
      shell.error(error);
    }
  }

  return {
    meta: { eyebrow: "执行审计", title: "打卡记录", subtitle: "按日期、结果和用户定位每次执行" },
    load,
    async handleInput(element) {
      if (element.dataset.filter === "record-date") {
        filters.date = element.value || beijingToday();
        await loadRecords();
        return;
      }
      if (element.dataset.filter === "record-status") filters.status = element.value;
      if (element.dataset.filter === "record-user") filters.userId = element.value;
      renderLists();
    },
    handleAction(action, element) {
      if (action === "record-detail") showDetail(records.find((record) => record.id === element.dataset.recordId));
    },
  };
}
