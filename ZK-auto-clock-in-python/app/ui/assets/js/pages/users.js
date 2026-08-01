import { apiRequest } from "../core/api.js";
import { escapeHtml, formatDateTime, initials } from "../core/format.js";
import { icon } from "../core/icons.js";
import { filterUsers } from "../core/state.js";


export function createUsersPage(shell) {
  let users = [];
  let sources = [];
  const filters = { query: "", status: "all" };
  const isActive = () => shell.isRouteActive("users");

  function sourceOptions(type, selected) {
    const available = sources.filter((source) => source.source_type === type && !source.archived);
    const values = available.map((source) => source.key);
    const extra = selected && !values.includes(selected)
      ? `<option value="${escapeHtml(selected)}" selected>${escapeHtml(selected)}（旧配置）</option>`
      : "";
    return `${extra}${available.map((source) => `<option value="${escapeHtml(source.key)}" ${source.key === selected ? "selected" : ""}>${escapeHtml(source.name)}${source.enabled ? "" : "（停用）"}</option>`).join("")}`;
  }

  function desktopRows(list) {
    if (!list.length) return `<tr><td colspan="6"><div class="empty-state"><div>${icon("users")}<h3>没有匹配的用户</h3><p>调整筛选条件或添加新用户</p></div></div></td></tr>`;
    return list.map((user) => `<tr><td><div class="identity"><span class="avatar">${initials(user)}</span><span><strong>${escapeHtml(user.nickname || user.username)}</strong><small>${escapeHtml(user.username)}</small></span></div></td><td><span class="status ${user.enabled ? "success" : ""}">${user.enabled ? "已启用" : "已停用"}</span></td><td>${Number(user.clockin_count || 0)} 次</td><td>${formatDateTime(user.last_clockin)}</td><td><span class="badge">${user.sports_comment_type === "api" || user.daily_comment_type === "api" ? "动态内容" : "默认策略"}</span></td><td><div class="row-actions"><button class="table-action" data-action="clock-user" data-user-id="${escapeHtml(user.id)}" title="立即打卡" ${user.enabled ? "" : "disabled"}>${icon("play")}</button><button class="table-action" data-action="edit-user" data-user-id="${escapeHtml(user.id)}" title="编辑">${icon("edit")}</button><label class="toggle" title="${user.enabled ? "停用" : "启用"}"><input type="checkbox" data-action="toggle-user" data-user-id="${escapeHtml(user.id)}" ${user.enabled ? "checked" : ""}><span></span></label><details class="row-menu"><summary class="table-action" title="更多">${icon("more")}</summary><div class="row-menu-popover"><button class="danger-text" data-action="delete-user" data-user-id="${escapeHtml(user.id)}">删除用户</button></div></details></div></td></tr>`).join("");
  }

  function mobileCards(list) {
    if (!list.length) return `<div class="empty-state"><div>${icon("users")}<h3>没有匹配的用户</h3><p>调整筛选条件或添加新用户</p></div></div>`;
    return list.map((user) => `<article class="mobile-card"><div class="mobile-card-head"><div class="identity"><span class="avatar">${initials(user)}</span><span><strong>${escapeHtml(user.nickname || user.username)}</strong><small>${escapeHtml(user.username)}</small></span></div><span class="badge ${user.enabled ? "success" : ""}">${user.enabled ? "启用" : "停用"}</span></div><div class="mobile-card-body"><div><small>打卡次数</small><span>${Number(user.clockin_count || 0)} 次</span></div><div><small>最近打卡</small><span>${formatDateTime(user.last_clockin)}</span></div></div><div class="mobile-card-actions"><button class="button secondary" data-action="clock-user" data-user-id="${escapeHtml(user.id)}" ${user.enabled ? "" : "disabled"}>${icon("play")}打卡</button><button class="button secondary" data-action="edit-user" data-user-id="${escapeHtml(user.id)}">${icon("edit")}编辑</button><button class="button secondary" data-action="toggle-user" data-user-id="${escapeHtml(user.id)}">${user.enabled ? "停用" : "启用"}</button><details class="row-menu mobile-card-menu"><summary class="table-action" title="更多">${icon("more")}</summary><div class="row-menu-popover"><button class="danger-text" data-action="delete-user" data-user-id="${escapeHtml(user.id)}">删除用户</button></div></details></div></article>`).join("");
  }

  function renderLists() {
    const list = filterUsers(users, filters);
    const count = document.querySelector("#user-count");
    if (count) count.textContent = `${list.length} / ${users.length}`;
    const body = document.querySelector("#users-desktop-body");
    if (body) body.innerHTML = desktopRows(list);
    const mobile = document.querySelector("#users-mobile-list");
    if (mobile) mobile.innerHTML = mobileCards(list);
  }

  function render() {
    shell.content.innerHTML = `<div class="page-stack"><div class="toolbar"><div class="filters"><input class="field" id="user-search" data-filter="user-query" type="search" placeholder="搜索用户名或昵称" value="${escapeHtml(filters.query)}"><select class="select-field" data-filter="user-status"><option value="all">全部状态</option><option value="enabled" ${filters.status === "enabled" ? "selected" : ""}>已启用</option><option value="disabled" ${filters.status === "disabled" ? "selected" : ""}>已停用</option></select></div><span class="badge" id="user-count">0 / 0</span></div><section class="panel"><header class="panel-header"><div><h2>用户列表</h2><p>打卡、编辑和启停都可在当前页面完成</p></div></header><div class="panel-body flush"><div class="desktop-table"><table class="data-table"><thead><tr><th>用户</th><th>状态</th><th>累计打卡</th><th>最近执行</th><th>内容策略</th><th style="text-align:right">操作</th></tr></thead><tbody id="users-desktop-body"></tbody></table></div><div class="mobile-card-list" id="users-mobile-list"></div></div></section></div>`;
    renderLists();
    shell.ready();
  }

  function userForm(user = null) {
    const editing = Boolean(user);
    const value = (key, fallback = "") => escapeHtml(user?.[key] ?? fallback);
    return `<form id="user-form" data-user-id="${editing ? escapeHtml(user.id) : ""}"><section class="form-section"><h3>账号</h3><div class="form-grid"><div class="form-field"><label for="user-username">足下账号</label><input id="user-username" name="username" required minlength="3" maxlength="50" value="${value("username")}"></div><div class="form-field"><label for="user-nickname">显示昵称</label><input id="user-nickname" name="nickname" maxlength="50" value="${value("nickname")}"></div><div class="form-field span-2"><label for="user-password">密码</label><input id="user-password" name="password" type="password" ${editing ? "" : "required"} minlength="6" autocomplete="new-password" placeholder="${editing ? "留空表示保持原密码" : "至少 6 位"}"><small>${editing ? "出于安全原因不会回显现有密码" : "密码仅由服务端用于调用 Worker"}</small></div><div class="form-field span-2"><label class="toggle"><input name="enabled" type="checkbox" ${user?.enabled !== false ? "checked" : ""}><span></span></label><small>启用此用户</small></div></div></section><section class="form-section"><h3>内容策略</h3><div class="form-grid"><div class="form-field"><label>运动文案方式</label><select name="sports_comment_type"><option value="default" ${value("sports_comment_type", "default") === "default" ? "selected" : ""}>平台默认</option><option value="custom" ${value("sports_comment_type") === "custom" ? "selected" : ""}>固定文案</option><option value="api" ${value("sports_comment_type") === "api" ? "selected" : ""}>内容源</option></select></div><div class="form-field"><label>运动文字源</label><select name="sports_comment_api">${sourceOptions("text", user?.sports_comment_api)}</select></div><div class="form-field span-2"><label>运动固定文案</label><textarea name="sports_custom_comment" maxlength="500" placeholder="仅在固定文案模式使用">${value("sports_custom_comment")}</textarea></div><div class="form-field"><label>日精进文案方式</label><select name="daily_comment_type"><option value="default" ${value("daily_comment_type", "default") === "default" ? "selected" : ""}>平台默认</option><option value="custom" ${value("daily_comment_type") === "custom" ? "selected" : ""}>固定文案</option><option value="api" ${value("daily_comment_type") === "api" ? "selected" : ""}>内容源</option></select></div><div class="form-field"><label>日精进文字源</label><select name="daily_comment_api">${sourceOptions("text", user?.daily_comment_api)}</select></div><div class="form-field span-2"><label>日精进固定文案</label><textarea name="custom_daily_comment" maxlength="500" placeholder="仅在固定文案模式使用">${value("custom_daily_comment")}</textarea></div></div></section><section class="form-section"><h3>高级设置</h3><div class="form-grid"><div class="form-field"><label>运动图片方式</label><select name="sports_image_type"><option value="default" ${value("sports_image_type", "default") === "default" ? "selected" : ""}>Worker 默认图片</option><option value="api" ${value("sports_image_type") === "api" ? "selected" : ""}>图片内容源</option></select></div><div class="form-field"><label>运动图片源</label><select name="sports_image_provider">${sourceOptions("image", user?.sports_image_provider)}</select></div><div class="form-field span-2"><label>图片分类</label><input name="sports_image_category" value="${value("sports_image_category", "random")}" placeholder="random"><small>分类必须在所选图片源的允许列表中</small></div></div></section><div class="form-actions"><button type="button" class="button secondary" data-action="close-drawer">取消</button><button type="submit" class="button primary">${editing ? "保存修改" : "添加用户"}</button></div></form>`;
  }

  function openUserDrawer(user = null) {
    const body = shell.openDrawer({
      eyebrow: user ? "用户设置" : "新用户",
      title: user ? `编辑 ${user.nickname || user.username}` : "添加用户",
      html: userForm(user),
    });
    body.querySelector("#user-form").addEventListener("submit", submitUser);
  }

  async function submitUser(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const button = form.querySelector('[type="submit"]');
    const formData = new FormData(form);
    const userId = form.dataset.userId;
    const payload = {
      username: formData.get("username")?.trim(),
      nickname: formData.get("nickname")?.trim() || null,
      enabled: formData.get("enabled") === "on",
      sports_comment_type: formData.get("sports_comment_type"),
      sports_custom_comment: formData.get("sports_custom_comment")?.trim() || null,
      sports_comment_api: formData.get("sports_comment_api"),
      daily_comment_type: formData.get("daily_comment_type"),
      custom_daily_comment: formData.get("custom_daily_comment")?.trim() || null,
      daily_comment_api: formData.get("daily_comment_api"),
      sports_image_type: formData.get("sports_image_type"),
      sports_image_provider: formData.get("sports_image_provider"),
      sports_image_category: formData.get("sports_image_category")?.trim() || "random",
    };
    const password = formData.get("password")?.trim();
    if (password) payload.password = password;
    shell.setButtonBusy(button, true, "保存中");
    try {
      await apiRequest(userId ? `/api/users/${userId}` : "/api/users", {
        method: userId ? "PUT" : "POST",
        body: payload,
      });
      if (!isActive()) return;
      shell.closeDrawer();
      shell.toast(userId ? "用户设置已更新" : "用户已添加", "success");
      await load({ silent: true });
    } catch (error) {
      if (!isActive() || error?.name === "AbortError") return;
      shell.toast(error.message, "error");
      shell.setButtonBusy(button, false);
    }
  }

  async function load({ silent = false } = {}) {
    if (!isActive()) return;
    if (!silent) shell.loading("正在加载用户列表");
    try {
      const [userResponse, sourceResponse] = await Promise.all([
        apiRequest("/api/users"),
        apiRequest("/api/content-sources").catch(() => ({ data: [] })),
      ]);
      if (!isActive()) return;
      users = userResponse.data || [];
      sources = sourceResponse.data || [];
      render();
    } catch (error) {
      if (!isActive() || error?.name === "AbortError") return;
      if (!silent) shell.error(error);
      else shell.toast(error.message, "error");
    }
  }

  async function toggleUser(element) {
    const user = users.find((item) => item.id === element.dataset.userId);
    if (!user) return;
    const enabled = element.matches('input[type="checkbox"]') ? element.checked : !user.enabled;
    try {
      await apiRequest(`/api/users/${user.id}/toggle`, { method: "PATCH", body: { enabled } });
      if (!isActive()) return;
      user.enabled = enabled;
      renderLists();
      shell.toast(enabled ? "用户已启用" : "用户已停用", "success");
    } catch (error) {
      if (!isActive() || error?.name === "AbortError") return;
      if (element.matches('input[type="checkbox"]')) element.checked = user.enabled;
      shell.toast(error.message, "error");
    }
  }

  async function clockUser(element) {
    shell.setButtonBusy(element, true, "创建中");
    try {
      await apiRequest("/api/clockin/tasks", { method: "POST", body: { scope: "users", user_ids: [element.dataset.userId] } });
      if (!isActive()) return;
      shell.toast("打卡任务已创建，可在总览查看进度", "success");
    } catch (error) {
      if (!isActive() || error?.name === "AbortError") return;
      shell.toast(error.status === 409 ? "已有任务正在执行，请先到总览查看" : error.message, "error");
    } finally {
      shell.setButtonBusy(element, false);
    }
  }

  async function deleteUser(element) {
    const user = users.find((item) => item.id === element.dataset.userId);
    if (!user) return;
    const confirmed = await shell.confirm({ title: "删除用户", message: `将永久删除 ${user.nickname || user.username} 的账号配置。历史记录不会自动删除。`, confirmLabel: "删除用户" });
    if (!confirmed || !isActive()) return;
    try {
      await apiRequest(`/api/users/${user.id}`, { method: "DELETE" });
      if (!isActive()) return;
      shell.toast("用户已删除", "success");
      await load({ silent: true });
    } catch (error) {
      if (!isActive() || error?.name === "AbortError") return;
      shell.toast(error.message, "error");
    }
  }

  return {
    meta: {
      eyebrow: "账号与策略",
      title: "用户",
      subtitle: "集中管理账号、内容策略与执行状态",
      primaryAction: { action: "add-user", label: "添加用户", icon: "plus" },
    },
    load,
    handleInput(element) {
      if (element.dataset.filter === "user-query") filters.query = element.value;
      if (element.dataset.filter === "user-status") filters.status = element.value;
      renderLists();
    },
    async handleAction(action, element) {
      if (action === "add-user") openUserDrawer();
      if (action === "edit-user") openUserDrawer(users.find((user) => user.id === element.dataset.userId));
      if (action === "toggle-user") await toggleUser(element);
      if (action === "clock-user") await clockUser(element);
      if (action === "delete-user") await deleteUser(element);
    },
  };
}
