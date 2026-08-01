import { apiRequest, downloadExport } from "../core/api.js";
import { escapeHtml, formatDateTime, toBoolean } from "../core/format.js";
import { icon } from "../core/icons.js";


export function createSettingsPage(shell) {
  let config = {};
  let schedule = {};
  let workers = [];
  const isActive = () => shell.isRouteActive("settings");

  function workerList() {
    if (!workers.length) return `<div class="empty-state"><div>${icon("settings")}<h3>还没有 Worker 节点</h3><p>至少添加一个节点后才能执行打卡</p></div></div>`;
    return `<div class="desktop-table"><table class="data-table"><thead><tr><th>节点</th><th>状态</th><th>请求统计</th><th>最近检查</th><th></th></tr></thead><tbody>${workers.map((worker) => `<tr><td><div class="identity"><span class="avatar">WK</span><span><strong>${escapeHtml(worker.name)}</strong><small>${escapeHtml(worker.url)}</small></span></div></td><td><span class="status ${worker.enabled && worker.available ? "success" : worker.enabled ? "failure" : ""}">${worker.enabled ? worker.available ? "可用" : "不可用" : "停用"}</span><span class="status ${worker.token_configured ? "success" : "failure"}" title="${worker.token_configured ? ("Token " + (worker.token_masked || "")) : "未配置 Token"}">${worker.token_configured ? "Token 已配置" : "Token 未配置"}</span></td><td>${Number(worker.total_success || 0)} / ${Number(worker.total_requests || 0)} 成功</td><td>${formatDateTime(worker.last_check)}</td><td><div class="row-actions"><button class="table-action" data-action="test-worker" data-worker-id="${escapeHtml(worker.id)}" title="测试连接">${icon("play")}</button><button class="table-action" data-action="edit-worker" data-worker-id="${escapeHtml(worker.id)}" title="编辑">${icon("edit")}</button><details class="row-menu"><summary class="table-action" title="更多">${icon("more")}</summary><div class="row-menu-popover"><button data-action="reset-worker" data-worker-id="${escapeHtml(worker.id)}">重置可用状态</button><button class="danger-text" data-action="delete-worker" data-worker-id="${escapeHtml(worker.id)}">删除节点</button></div></details></div></td></tr>`).join("")}</tbody></table></div><div class="mobile-card-list">${workers.map((worker) => `<article class="mobile-card"><div class="mobile-card-head"><div class="identity"><span class="avatar">WK</span><span><strong>${escapeHtml(worker.name)}</strong><small>${escapeHtml(worker.url)}</small></span></div><span class="badge ${worker.enabled && worker.available ? "success" : "failure"}">${worker.enabled ? worker.available ? "可用" : "不可用" : "停用"}</span><span class="badge ${worker.token_configured ? "success" : "failure"}" title="${worker.token_configured ? ("Token " + (worker.token_masked || "")) : "未配置 Token"}">${worker.token_configured ? "Token 已配置" : "Token 未配置"}</span></div><div class="mobile-card-actions"><button class="button secondary" data-action="test-worker" data-worker-id="${escapeHtml(worker.id)}">${icon("play")}测试</button><button class="button secondary" data-action="edit-worker" data-worker-id="${escapeHtml(worker.id)}">${icon("edit")}编辑</button><details class="row-menu mobile-card-menu"><summary class="table-action" title="更多">${icon("more")}</summary><div class="row-menu-popover"><button data-action="reset-worker" data-worker-id="${escapeHtml(worker.id)}">重置可用状态</button><button class="danger-text" data-action="delete-worker" data-worker-id="${escapeHtml(worker.id)}">删除节点</button></div></details></div></article>`).join("")}</div>`;
  }

  function render() {
    const nextRun = schedule.job_info?.next_run_time_beijing || schedule.job_info?.next_run_time;
    shell.content.innerHTML = `<div class="page-stack"><div class="notice warning">当前部署允许通过公网 IP + HTTP 访问。这意味着传输中的管理员口令、用户凭据和 Token 可能被窃听；仅应在你明确接受此风险的受控环境使用。</div><div class="settings-sections"><section class="setting-block span-2"><header><div><h2>计划任务</h2><p>配置每日自动执行时间；手动任务与计划任务使用同一个持久编排服务。</p></div><span class="status ${schedule.scheduler_running ? "success" : "failure"}">${schedule.scheduler_running ? "调度器运行中" : "调度器未运行"}</span></header><div class="setting-content"><form id="schedule-form"><div class="inline-fields"><div class="form-field grow"><label>CRON 表达式</label><input name="schedule_cron" value="${escapeHtml(config.schedule_cron || schedule.schedule_cron || "10 0 * * *")}" required></div><div class="form-field"><label>时区</label><input name="schedule_timezone" value="${escapeHtml(config.schedule_timezone || schedule.schedule_timezone || "Asia/Shanghai")}" required></div><label class="toggle" title="启用计划任务"><input name="schedule_enabled" type="checkbox" ${toBoolean(config.schedule_enabled ?? schedule.schedule_enabled) ? "checked" : ""}><span></span></label><button class="button primary" type="submit">保存计划</button></div><p class="metric-foot">下次执行：${nextRun ? escapeHtml(formatDateTime(nextRun)) : "未安排"}</p></form></div></section><section class="setting-block"><header><div><h2>打卡重试</h2><p>某类打卡真正失败时（如运动图片上传失败），按此处配置自动重试整次调用。</p></div></header><div class="setting-content"><form id="retry-form"><div class="inline-fields"><div class="form-field"><label>重试次数</label><input name="clockin_retry_count" type="number" min="0" max="10" value="${Number(config.clockin_retry_count ?? 3)}" required></div><div class="form-field"><label>重试间隔（秒）</label><input name="clockin_retry_delay" type="number" min="0" max="300" value="${Number(config.clockin_retry_delay ?? 3)}" required></div><button class="button primary" type="submit">保存</button></div><p class="metric-foot">设为 0 表示失败不重试。“今日已完成”等重复打卡视为成功，不会触发重试。</p></form></div></section><section class="setting-block span-2"><header><div><h2>Worker 节点</h2><p>维护执行节点、连接状态和请求统计。Token 在编辑时留空表示保持原值。</p></div><button class="button secondary" data-action="add-worker">${icon("plus")}添加节点</button></header><div class="setting-content">${workerList()}</div></section><section class="setting-block"><header><div><h2>数据导入导出</h2><p>新版普通导出不包含用户密码和 Worker Token；旧 1.0 文件可用于一次性迁移。</p></div></header><div class="setting-content"><div class="inline-fields"><button class="button secondary" data-action="export-config">${icon("download")}导出配置</button><input id="config-import-file" type="file" accept="application/json,.json" hidden><button class="button secondary" data-action="choose-import">${icon("upload")}导入配置</button><button class="button secondary" data-action="backup-database">创建数据库备份</button></div></div></section><section class="setting-block danger-zone"><header><div><h2>数据维护</h2><p>清理操作不可撤销，执行前会再次确认。</p></div></header><div class="setting-content"><div class="inline-fields"><div class="form-field"><label>保留最近天数</label><input id="cleanup-days" type="number" min="1" max="3650" value="${Number(config.retention_days || 7)}"></div><button class="button danger-quiet" data-action="cleanup-data">清理旧记录</button></div></div></section></div></div>`;
    shell.content.querySelector("#schedule-form").addEventListener("submit", saveSchedule);
    shell.content.querySelector("#retry-form").addEventListener("submit", saveRetry);
    shell.content.querySelector("#config-import-file").addEventListener("change", importConfig);
    shell.ready();
  }

  function workerForm(worker = null) {
    return `<form id="worker-form" data-worker-id="${worker ? escapeHtml(worker.id) : ""}"><section class="form-section"><h3>节点连接</h3><div class="form-grid"><div class="form-field"><label>节点名称</label><input name="name" required maxlength="50" value="${escapeHtml(worker?.name || "")}"></div><div class="form-field"><label>状态</label><select name="enabled"><option value="true" ${worker?.enabled !== false ? "selected" : ""}>启用</option><option value="false" ${worker?.enabled === false ? "selected" : ""}>停用</option></select></div><div class="form-field span-2"><label>Worker 地址</label><input name="url" required value="${escapeHtml(worker?.url || "https://")}"></div><div class="form-field span-2"><label>API Token</label><input name="token" type="password" ${worker ? "" : "required"} autocomplete="new-password" data-original="${worker?.token_configured ? escapeHtml(worker.token_masked || "") : ""}" value="${worker?.token_configured ? escapeHtml(worker.token_masked || "") : ""}" placeholder="${worker ? "已配置；保持原样或留空均不修改，输入新值则替换" : "输入 Worker API Token"}"><small>已用脱敏占位符填充表示已配置；真实 Token 不回显，保持原样保存即不修改</small></div><div class="form-field span-2"><label>备注</label><textarea name="note" maxlength="200">${escapeHtml(worker?.note || "")}</textarea></div></div></section><div class="form-actions"><button type="button" class="button secondary" data-action="close-drawer">取消</button><button type="submit" class="button primary">保存节点</button></div></form>`;
  }

  function openWorker(worker = null) {
    const body = shell.openDrawer({ eyebrow: "执行节点", title: worker ? `编辑 ${worker.name}` : "添加 Worker 节点", html: workerForm(worker) });
    body.querySelector("#worker-form").addEventListener("submit", saveWorker);
  }

  async function saveWorker(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const formData = new FormData(form);
    const workerId = form.dataset.workerId;
    const payload = {
      name: formData.get("name")?.trim(),
      url: formData.get("url")?.trim(),
      enabled: formData.get("enabled") === "true",
      note: formData.get("note")?.trim() || null,
    };
    const token = formData.get("token")?.trim();
    const originalMasked = form.querySelector('[name="token"]')?.dataset.original || "";
    // 只有输入了“与脱敏占位不同”的新值才更新；保持原样/留空都不修改原 Token
    if (token && token !== originalMasked) {
      payload.token = token;
    }
    const button = form.querySelector('[type="submit"]');
    shell.setButtonBusy(button, true, "保存中");
    try {
      const response = await apiRequest(workerId ? `/api/worker-apis/${workerId}` : "/api/worker-apis", { method: workerId ? "PUT" : "POST", body: payload });
      if (!workerId && payload.enabled === false && response.data?.id) {
        await apiRequest(`/api/worker-apis/${response.data.id}`, { method: "PUT", body: { enabled: false } });
      }
      if (!isActive()) return;
      shell.closeDrawer();
      shell.toast(workerId ? "Worker 节点已更新" : "Worker 节点已添加", "success");
      await load({ silent: true });
    } catch (error) {
      if (!isActive() || error?.name === "AbortError") return;
      shell.toast(error.message, "error");
      shell.setButtonBusy(button, false);
    }
  }

  async function saveSchedule(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const button = form.querySelector('[type="submit"]');
    shell.setButtonBusy(button, true, "保存中");
    try {
      const response = await apiRequest("/api/config", {
        method: "PUT",
        body: {
          schedule_cron: data.get("schedule_cron")?.trim(),
          schedule_timezone: data.get("schedule_timezone")?.trim(),
          schedule_enabled: data.get("schedule_enabled") === "on",
        },
      });
      if (!isActive()) return;
      shell.toast(response.message || "计划任务已更新", "success");
      await load({ silent: true });
    } catch (error) {
      if (!isActive() || error?.name === "AbortError") return;
      shell.toast(error.message, "error");
      shell.setButtonBusy(button, false);
    }
  }

  async function saveRetry(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const button = form.querySelector('[type="submit"]');
    shell.setButtonBusy(button, true, "保存中");
    try {
      const response = await apiRequest("/api/config", {
        method: "PUT",
        body: {
          clockin_retry_count: Number(data.get("clockin_retry_count")),
          clockin_retry_delay: Number(data.get("clockin_retry_delay")),
        },
      });
      if (!isActive()) return;
      shell.toast(response.message || "重试配置已更新", "success");
      await load({ silent: true });
    } catch (error) {
      if (!isActive() || error?.name === "AbortError") return;
      shell.toast(error.message, "error");
      shell.setButtonBusy(button, false);
    }
  }

  async function testWorker(element) {
    shell.setButtonBusy(element, true, "测试中");
    try {
      const response = await apiRequest(`/api/worker-apis/${element.dataset.workerId}/test`, { method: "POST" });
      if (!isActive()) return;
      if (!response.success) throw new Error(response.message || "连接失败");
      shell.toast(`${response.message}${response.latency_ms == null ? "" : `，${response.latency_ms} ms`}`, "success");
      await load({ silent: true });
    } catch (error) {
      if (!isActive() || error?.name === "AbortError") return;
      shell.toast(error.message, "error");
    } finally {
      shell.setButtonBusy(element, false);
    }
  }

  async function resetWorker(element) {
    try {
      await apiRequest(`/api/worker-apis/${element.dataset.workerId}/reset`, { method: "POST" });
      if (!isActive()) return;
      shell.toast("Worker 可用状态已重置", "success");
      await load({ silent: true });
    } catch (error) { if (isActive() && error?.name !== "AbortError") shell.toast(error.message, "error"); }
  }

  async function deleteWorker(element) {
    const worker = workers.find((item) => item.id === element.dataset.workerId);
    if (!worker) return;
    const confirmed = await shell.confirm({ title: "删除 Worker 节点", message: `删除 ${worker.name} 后，该节点将不再接收打卡任务。系统至少需要保留一个节点。`, confirmLabel: "删除节点" });
    if (!confirmed || !isActive()) return;
    try {
      await apiRequest(`/api/worker-apis/${worker.id}`, { method: "DELETE" });
      if (!isActive()) return;
      shell.toast("Worker 节点已删除", "success");
      await load({ silent: true });
    } catch (error) { if (isActive() && error?.name !== "AbortError") shell.toast(error.message, "error"); }
  }

  async function importConfig(event) {
    const file = event.currentTarget.files?.[0];
    if (!file) return;
    const confirmed = await shell.confirm({ title: "导入配置文件", message: "旧 1.0 文件可能包含明文密码和 Token。导入过程不会回显密钥；完成后请立即安全删除旧文件。", confirmLabel: "导入", danger: false });
    if (!confirmed) { event.currentTarget.value = ""; return; }
    try {
      const payload = JSON.parse(await file.text());
      const response = await apiRequest("/api/config/import", { method: "POST", body: payload });
      if (!isActive()) return;
      shell.toast(response.message || "配置导入完成", "success");
      event.currentTarget.value = "";
      await load({ silent: true });
    } catch (error) {
      if (!isActive() || error?.name === "AbortError") return;
      shell.toast(error instanceof SyntaxError ? "导入文件不是有效 JSON" : error.message, "error");
      event.currentTarget.value = "";
    }
  }

  async function cleanupData() {
    const input = document.querySelector("#cleanup-days");
    const days = Number(input?.value);
    if (!input?.checkValidity() || !Number.isInteger(days)) {
      shell.toast("保留天数必须是 1–3650 的整数", "error");
      input?.focus();
      return;
    }
    const confirmed = await shell.confirm({ title: "清理旧记录", message: `将永久删除 ${days} 天以前的打卡记录和汇总数据。请先确认已有可用备份。`, confirmLabel: "永久清理" });
    if (!confirmed || !isActive()) return;
    try {
      const response = await apiRequest("/api/maintenance/cleanup", { method: "POST", body: { days } });
      if (!isActive()) return;
      shell.toast(response.message || "清理完成", "success");
    } catch (error) { if (isActive() && error?.name !== "AbortError") shell.toast(error.message, "error"); }
  }

  async function load({ silent = false } = {}) {
    if (!isActive()) return;
    if (!silent) shell.loading("正在加载系统设置");
    try {
      const [configResponse, scheduleResponse, workerResponse] = await Promise.all([
        apiRequest("/api/config"),
        apiRequest("/api/config/schedule"),
        apiRequest("/api/worker-apis"),
      ]);
      if (!isActive()) return;
      config = configResponse.data || {};
      schedule = scheduleResponse.data || {};
      workers = workerResponse.data || [];
      render();
    } catch (error) {
      if (!isActive() || error?.name === "AbortError") return;
      if (!silent) shell.error(error);
      else shell.toast(error.message, "error");
    }
  }

  return {
    meta: { eyebrow: "运行与维护", title: "系统设置", subtitle: "管理计划任务、Worker 节点和数据维护" },
    load,
    async handleAction(action, element) {
      const worker = workers.find((item) => item.id === element.dataset.workerId);
      if (action === "add-worker") openWorker();
      if (action === "edit-worker") openWorker(worker);
      if (action === "test-worker") await testWorker(element);
      if (action === "reset-worker") await resetWorker(element);
      if (action === "delete-worker") await deleteWorker(element);
      if (action === "export-config") {
        try {
          await downloadExport();
          if (isActive()) shell.toast("配置已导出", "success");
        } catch (error) {
          if (isActive() && error?.name !== "AbortError") shell.toast(error.message, "error");
        }
      }
      if (action === "choose-import") document.querySelector("#config-import-file")?.click();
      if (action === "backup-database") {
        try {
          const response = await apiRequest("/api/maintenance/backup", { method: "POST" });
          if (isActive()) shell.toast(response.message || "数据库备份已创建", "success");
        } catch (error) {
          if (isActive() && error?.name !== "AbortError") shell.toast(error.message, "error");
        }
      }
      if (action === "cleanup-data") await cleanupData();
    },
  };
}
