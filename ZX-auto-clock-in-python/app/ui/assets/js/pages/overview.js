import { apiRequest } from "../core/api.js";
import { escapeHtml, formatDateTime, statusLabel } from "../core/format.js";
import { icon } from "../core/icons.js";
import { taskNeedsPolling } from "../core/state.js";


export function createOverviewPage(shell) {
  let summary = null;
  let trackedTask = null;
  let pollTimer = null;
  let pollRetryCount = 0;
  let disposed = false;

  function metric(label, value, foot, tone = "", iconName = "overview") {
    return `<article class="metric-card ${tone}"><header><span>${escapeHtml(label)}</span>${icon(iconName)}</header><strong class="metric-value">${escapeHtml(value)}</strong><span class="metric-foot">${escapeHtml(foot)}</span></article>`;
  }

  function taskHtml(task) {
    if (!task) {
      return `<section class="panel"><header class="panel-header"><div><h2>执行控制</h2><p>高频补救操作集中在这里</p></div></header><div class="panel-body"><div class="inline-fields"><button class="button primary" data-action="task-failed" ${summary.today.failure ? "" : "disabled"}>${icon("refresh")}重试今日失败</button><button class="button secondary" data-action="task-all">${icon("play")}手动全部打卡</button><span class="status healthy">当前没有活动任务</span></div></div></section>`;
    }
    const progress = task.progress || {};
    const percent = Number(progress.percent || 0);
    return `<section class="task-panel" data-task-id="${escapeHtml(task.id)}"><div class="task-head"><div><span class="status ${escapeHtml(task.status)}">${escapeHtml(statusLabel(task.status))}</span><h2>${task.scope === "failed" ? "今日失败重试" : task.scope === "users" ? "指定用户打卡" : "全部用户打卡"}</h2><p>任务 ${escapeHtml(task.id.slice(0, 8))} · ${escapeHtml(task.date || summary.date)}</p></div><div class="task-meta"><strong class="task-percent">${percent}%</strong><p>${Number(progress.current || 0)} / ${Number(progress.total || 0)}</p></div></div><div class="progress-track" style="--progress:${Math.min(100, percent)}%"><span></span></div><div class="task-counts"><span>成功 <strong>${Number(progress.success || 0)}</strong></span><span>失败 <strong>${Number(progress.failure || 0)}</strong></span><span>状态 <strong>${escapeHtml(statusLabel(task.status))}</strong></span></div></section>`;
  }

  function failedUsersHtml() {
    const users = summary.failed_users || [];
    if (!users.length) {
      return `<div class="empty-state"><div>${icon("check")}<h3>今日没有失败用户</h3><p>失败发生时会在这里直接提供补救入口</p></div></div>`;
    }
    return `<div class="desktop-table"><table class="data-table"><thead><tr><th>用户</th><th>失败原因</th><th>操作</th></tr></thead><tbody>${users.map((user) => `<tr><td><div class="identity"><span class="avatar">${escapeHtml((user.nickname || user.username).slice(0, 2))}</span><span><strong>${escapeHtml(user.nickname || user.username)}</strong><small>${escapeHtml(user.username)}</small></span></div></td><td>${escapeHtml(user.error || "未知错误")}</td><td><button class="table-action" data-action="task-user" data-user-id="${escapeHtml(user.id)}" title="重试该用户">${icon("play")}</button></td></tr>`).join("")}</tbody></table></div><div class="mobile-card-list">${users.map((user) => `<article class="mobile-card"><div class="mobile-card-head"><div class="identity"><span class="avatar">${escapeHtml((user.nickname || user.username).slice(0, 2))}</span><span><strong>${escapeHtml(user.nickname || user.username)}</strong><small>${escapeHtml(user.username)}</small></span></div><span class="badge failure">失败</span></div><p class="metric-foot">${escapeHtml(user.error || "未知错误")}</p><div class="mobile-card-actions"><button class="button secondary" data-action="task-user" data-user-id="${escapeHtml(user.id)}">${icon("play")}重试</button></div></article>`).join("")}</div>`;
  }

  function currentTask() {
    return trackedTask || summary?.active_task || null;
  }

  function render() {
    const today = summary.today || {};
    const workers = summary.workers || {};
    const sources = summary.content_sources || {};
    shell.content.innerHTML = `<div class="page-stack"><section class="metric-grid">${metric("今日成功", today.success || 0, `共 ${today.enabled_users || 0} 个启用用户`, "success", "check")}${metric("今日失败", today.failure || 0, today.failure ? "建议立即补救" : "当前无失败", today.failure ? "danger" : "", "alert")}${metric("尚未执行", today.pending || 0, `北京时间 ${summary.date || ""}`, "warning", "records")}${metric("下次计划", summary.next_run_time ? formatDateTime(summary.next_run_time) : "未安排", summary.next_run_time ? "按系统计划自动执行" : "请检查系统设置", "", "settings")}</section>${taskHtml(currentTask())}<div class="overview-grid"><section class="panel"><header class="panel-header"><div><h2>今日失败用户</h2><p>按每位启用用户的最新结果计算</p></div>${summary.failed_users?.length ? `<button class="button secondary" data-action="task-failed">${icon("refresh")}重试全部失败</button>` : ""}</header><div class="panel-body flush">${failedUsersHtml()}</div></section><div class="column-stack"><section class="panel"><header class="panel-header"><div><h2>服务健康</h2><p>Worker 与外部内容链路</p></div></header><div class="panel-body"><div class="health-grid"><article class="health-card"><header><h3>Worker 节点</h3><span class="status ${workers.unavailable ? "failure" : workers.enabled ? "success" : "warning"}">${workers.healthy || 0}/${workers.enabled || 0}</span></header><strong>${workers.healthy || 0}</strong><p>${workers.unavailable || 0} 个节点不可用</p></article><article class="health-card"><header><h3>内容源</h3><span class="status ${sources.unavailable ? "failure" : sources.degraded || sources.unknown ? "warning" : "success"}">${sources.healthy || 0}/${sources.total || 0}</span></header><strong>${sources.healthy || 0}</strong><p>${sources.degraded || 0} 个降级，${sources.unavailable || 0} 个不可用，${sources.unknown || 0} 个未检查</p></article></div></div></section><section class="panel"><header class="panel-header"><div><h2>快捷入口</h2><p>常用观察与管理位置</p></div></header><div class="panel-body"><div class="inline-fields"><button class="button secondary" data-route-jump="records">${icon("records")}查看记录</button><button class="button secondary" data-route-jump="sources">${icon("sources")}管理内容源</button></div></div></section></div></div></div>`;
    shell.ready();
  }

  function schedulePoll() {
    window.clearTimeout(pollTimer);
    if (!disposed && taskNeedsPolling(currentTask())) {
      const delay = Math.min(10000, 2000 * (2 ** pollRetryCount));
      pollTimer = window.setTimeout(pollTask, delay);
    }
  }

  async function pollTask() {
    const task = currentTask();
    if (!taskNeedsPolling(task)) return;
    try {
      const response = await apiRequest(`/api/clockin/tasks/${task.id}`);
      if (!shell.isRouteActive("overview") || disposed) return;
      trackedTask = response.data;
      summary.active_task = trackedTask;
      pollRetryCount = 0;
      render();
      if (!taskNeedsPolling(trackedTask)) {
        const terminalTask = trackedTask;
        const summaryResponse = await apiRequest("/api/dashboard/summary");
        if (!shell.isRouteActive("overview") || disposed) return;
        summary = summaryResponse.data;
        trackedTask = terminalTask;
      }
      render();
      schedulePoll();
    } catch (error) {
      if (disposed || error?.name === "AbortError") return;
      pollRetryCount = Math.min(pollRetryCount + 1, 3);
      shell.toast(`任务进度同步失败，将自动重试：${error.message}`, "error");
      schedulePoll();
    }
  }

  async function load({ silent = false } = {}) {
    if (!shell.isRouteActive("overview")) return;
    disposed = false;
    if (!silent) shell.loading("正在汇总今日执行状态");
    try {
      const response = await apiRequest("/api/dashboard/summary");
      if (!shell.isRouteActive("overview")) return;
      summary = response.data;
      if (summary.active_task) trackedTask = summary.active_task;
      else if (!silent && !taskNeedsPolling(trackedTask)) trackedTask = null;
      render();
      schedulePoll();
    } catch (error) {
      if (!shell.isRouteActive("overview") || error?.name === "AbortError") return;
      if (!silent) shell.error(error);
      else shell.toast(error.message, "error");
    }
  }

  async function createTask(scope, userIds, button) {
    const label = scope === "failed" ? "重试今日所有失败用户" : scope === "users" ? "为该用户立即执行一次打卡" : "为所有启用用户执行一次打卡";
    const confirmed = await shell.confirm({
      title: "确认开始打卡任务",
      message: `${label}。任务开始后可在本页观察实时进度。`,
      confirmLabel: "开始执行",
      danger: false,
    });
    if (!confirmed || !shell.isRouteActive("overview") || disposed) return;
    shell.setButtonBusy(button, true, "正在创建");
    try {
      const response = await apiRequest("/api/clockin/tasks", {
        method: "POST",
        body: { scope, date: summary.date, user_ids: userIds },
      });
      if (!shell.isRouteActive("overview") || disposed) return;
      trackedTask = response.data;
      summary.active_task = trackedTask;
      pollRetryCount = 0;
      shell.toast("任务已创建，可在总览观察进度", "success");
      render();
      schedulePoll();
    } catch (error) {
      if (!shell.isRouteActive("overview") || disposed || error?.name === "AbortError") return;
      if (error.status === 409 && error.payload?.data?.task_id) {
        shell.toast("已有任务正在执行，已切换到当前进度", "info");
        const response = await apiRequest(`/api/clockin/tasks/${error.payload.data.task_id}`);
        if (!shell.isRouteActive("overview") || disposed) return;
        trackedTask = response.data;
        summary.active_task = trackedTask;
        render();
        schedulePoll();
      } else {
        shell.toast(error.message, "error");
      }
    } finally {
      shell.setButtonBusy(button, false);
    }
  }

  return {
    meta: {
      eyebrow: "今日工作台",
      title: "总览",
      subtitle: "监控今日执行状态并处理失败任务",
      primaryAction: { action: "task-all", label: "手动全部打卡", icon: "play" },
    },
    load,
    dispose() {
      disposed = true;
      window.clearTimeout(pollTimer);
    },
    async handleAction(action, element) {
      if (action === "task-all") return createTask("all", [], element);
      if (action === "task-failed") return createTask("failed", [], element);
      if (action === "task-user") return createTask("users", [element.dataset.userId], element);
    },
  };
}
