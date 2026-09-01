import { apiRequest } from "../core/api.js";
import { escapeHtml, formatDateTime, parseJsonInput, statusLabel } from "../core/format.js";
import { icon } from "../core/icons.js";
import { sortSources } from "../core/state.js";


export function createSourcesPage(shell) {
  let sources = [];
  const isActive = () => shell.isRouteActive("sources");

  function healthClass(source) {
    return ({ healthy: "success", degraded: "warning", unavailable: "failure" })[source.health_status] || "";
  }

  function sourceRows(type) {
    const list = sortSources(sources.filter((source) => source.source_type === type && !source.archived));
    if (!list.length) return `<div class="empty-state"><div>${icon("sources")}<h3>还没有${type === "text" ? "文字" : "图片"}内容源</h3><p>新内容源默认停用，测试成功后再启用</p></div></div>`;
    return `<div class="source-list">${list.map((source, index) => `<article class="source-row"><div class="source-name"><strong>${escapeHtml(source.name)}<span class="badge ${source.enabled ? "accent" : ""}">${source.enabled ? "启用" : "停用"}</span></strong><code>${escapeHtml(source.url_template)}</code></div><div class="source-observability"><div class="source-stat"><small>优先级</small><span>${Number(source.priority)}</span></div><div class="source-stat"><small>健康状态</small><span class="status ${healthClass(source)}">${escapeHtml(statusLabel(source.health_status))}</span></div><div class="source-stat"><small>最近延迟</small><span>${source.latency_ms == null ? "—" : `${Number(source.latency_ms)} ms`}</span></div><div class="source-stat source-error"><small>最近错误</small><span title="${escapeHtml(source.last_error || "无")}">${escapeHtml(source.last_error || "无")}</span><time>${formatDateTime(source.last_checked_at, "尚未检查")}</time></div></div><div class="row-actions"><button class="table-action" data-action="move-source-up" data-source-id="${escapeHtml(source.id)}" title="提高优先级" ${index === 0 ? "disabled" : ""}>↑</button><button class="table-action" data-action="move-source-down" data-source-id="${escapeHtml(source.id)}" title="降低优先级" ${index === list.length - 1 ? "disabled" : ""}>↓</button><button class="table-action" data-action="test-source" data-source-id="${escapeHtml(source.id)}" title="测试">${icon("play")}</button><button class="table-action" data-action="edit-source" data-source-id="${escapeHtml(source.id)}" title="编辑">${icon("edit")}</button><details class="row-menu"><summary class="table-action" title="更多">${icon("more")}</summary><div class="row-menu-popover"><button data-action="copy-source" data-source-id="${escapeHtml(source.id)}">复制内容源</button><button class="danger-text" data-action="archive-source" data-source-id="${escapeHtml(source.id)}">归档内容源</button></div></details></div></article>`).join("")}</div>`;
  }

  function render() {
    const enabled = sources.filter((source) => source.enabled && !source.archived);
    const attention = enabled.filter((source) => ["unknown", "degraded", "unavailable"].includes(source.health_status));
    const unknownCount = enabled.filter((source) => source.health_status === "unknown").length;
    const attentionFoot = unknownCount ? `降级或不可用，含未检查 ${unknownCount} 个` : "降级或不可用";
    shell.content.innerHTML = `<div class="page-stack"><section class="metric-grid"><article class="metric-card"><header><span>可用来源</span>${icon("sources")}</header><strong class="metric-value">${enabled.length}</strong><span class="metric-foot">共 ${sources.filter((source) => !source.archived).length} 个未归档来源</span></article><article class="metric-card ${attention.length ? "warning" : "success"}"><header><span>需要关注</span>${icon(attention.length ? "alert" : "check")}</header><strong class="metric-value">${attention.length}</strong><span class="metric-foot">${attentionFoot}</span></article><article class="metric-card"><header><span>文字来源</span>${icon("records")}</header><strong class="metric-value">${enabled.filter((source) => source.source_type === "text").length}</strong><span class="metric-foot">按优先级自动降级</span></article><article class="metric-card"><header><span>图片来源</span>${icon("overview")}</header><strong class="metric-value">${enabled.filter((source) => source.source_type === "image").length}</strong><span class="metric-foot">仅允许公网 HTTPS</span></article></section><div class="toolbar"><div class="notice">排序会直接决定自动降级顺序；一次失败进入降级，连续三次标记不可用。</div><button class="button secondary" data-action="test-all-sources">${icon("play")}测试全部</button></div><div class="source-groups"><section class="panel"><header class="panel-header"><div><h2>文字内容源</h2><p>用于运动和日精进文案</p></div><span class="badge">${sources.filter((source) => source.source_type === "text" && !source.archived).length} 个</span></header>${sourceRows("text")}</section><section class="panel"><header class="panel-header"><div><h2>图片内容源</h2><p>用于运动打卡配图</p></div><span class="badge">${sources.filter((source) => source.source_type === "image" && !source.archived).length} 个</span></header>${sourceRows("image")}</section></div></div>`;
    shell.ready();
  }

  function uniqueCopyKey(source) {
    const root = `${source.key}-copy`.slice(0, 58);
    let candidate = root;
    let index = 2;
    const keys = new Set(sources.map((item) => item.key));
    while (keys.has(candidate)) candidate = `${root}-${index++}`.slice(0, 64);
    return candidate;
  }

  function sourceForm(source = null, { copy = false } = {}) {
    const editing = Boolean(source && !copy);
    const key = copy ? uniqueCopyKey(source) : source?.key || "";
    const name = copy ? `${source.name} 副本` : source?.name || "";
    const params = JSON.stringify(source?.query_params || {}, null, 2);
    const categories = (source?.categories || []).join("\n");
    return `<form id="source-form" data-source-id="${editing ? escapeHtml(source.id) : ""}"><section class="form-section"><h3>标识与状态</h3><div class="form-grid"><div class="form-field"><label>不可变 Key</label><input name="key" required minlength="2" maxlength="64" pattern="[A-Za-z0-9_-]+" value="${escapeHtml(key)}" ${editing ? "disabled" : ""}><small>仅允许字母、数字、下划线和连字符</small></div><div class="form-field"><label>显示名称</label><input name="name" required maxlength="80" value="${escapeHtml(name)}"></div><div class="form-field"><label>来源类型</label><select name="source_type"><option value="text" ${source?.source_type !== "image" ? "selected" : ""}>文字</option><option value="image" ${source?.source_type === "image" ? "selected" : ""}>图片</option></select></div><div class="form-field"><label>优先级</label><input name="priority" type="number" min="0" max="10000" value="${Number(source?.priority ?? 100)}"></div><div class="form-field span-2"><label class="toggle"><input name="enabled" type="checkbox" ${source?.enabled && !copy ? "checked" : ""}><span></span></label><small>启用前必须完成一次成功测试；配置变化后需要重新测试</small></div></div></section><section class="form-section"><h3>请求配置</h3><div class="form-grid"><div class="form-field span-2"><label>HTTPS 地址模板</label><input name="url_template" type="url" required maxlength="2048" value="${escapeHtml(source?.url_template || "https://")}"><small>只允许公网 HTTPS GET，可使用受控的 {category} 占位符</small></div><div class="form-field span-2"><label>查询参数（JSON 对象）</label><textarea name="query_params" spellcheck="false">${escapeHtml(params)}</textarea></div><div class="form-field"><label>超时秒数</label><input name="timeout_seconds" type="number" min="2" max="30" value="${Number(source?.timeout_seconds ?? 10)}"></div><div class="form-field"><label>允许分类（每行一个）</label><textarea name="categories" placeholder="nature\nanime">${escapeHtml(categories)}</textarea></div></div></section><section class="form-section"><h3>解析规则</h3><div class="form-grid"><div class="form-field span-2"><label>解析模式</label><select name="parse_mode"><optgroup label="文字"><option value="json_text" ${source?.parse_mode === "json_text" ? "selected" : ""}>JSON 文字</option><option value="plain_text" ${source?.parse_mode === "plain_text" ? "selected" : ""}>纯文字</option></optgroup><optgroup label="图片"><option value="json_image" ${source?.parse_mode === "json_image" ? "selected" : ""}>JSON 图片地址</option><option value="redirect_image" ${source?.parse_mode === "redirect_image" ? "selected" : ""}>图片直返 / 重定向</option></optgroup></select></div><div class="form-field"><label>值路径</label><input name="value_path" maxlength="200" value="${escapeHtml(source?.value_path || "")}" placeholder="data.content"></div><div class="form-field"><label>出处路径（可选）</label><input name="attribution_path" maxlength="200" value="${escapeHtml(source?.attribution_path || "")}" placeholder="data.source"></div></div></section>${source?.last_error && editing ? `<div class="notice danger">最近错误：${escapeHtml(source.last_error)}</div>` : ""}<div class="form-actions"><button type="button" class="button secondary" data-action="save-source-disabled">保存为停用</button><button type="submit" class="button primary">${icon("play")}测试并保存</button></div></form>`;
  }

  function openSourceDrawer(source = null, options = {}) {
    const body = shell.openDrawer({
      eyebrow: source && !options.copy ? "内容源设置" : "新内容源",
      title: options.copy ? `复制 ${source.name}` : source ? source.name : "添加内容源",
      html: sourceForm(source, options),
    });
    body.querySelector("#source-form").addEventListener("submit", (event) => saveSource(event, true));
  }

  function payloadFromForm(form, forceDisabled) {
    const data = new FormData(form);
    const categories = String(data.get("categories") || "").split(/[\n,]/).map((item) => item.trim()).filter(Boolean);
    return {
      ...(form.dataset.sourceId ? {} : { key: data.get("key")?.trim() }),
      name: data.get("name")?.trim(),
      source_type: data.get("source_type"),
      enabled: forceDisabled ? false : data.get("enabled") === "on",
      priority: Number(data.get("priority")),
      url_template: data.get("url_template")?.trim(),
      query_params: parseJsonInput(data.get("query_params"), {}),
      parse_mode: data.get("parse_mode"),
      value_path: data.get("value_path")?.trim() || null,
      attribution_path: data.get("attribution_path")?.trim() || null,
      categories,
      timeout_seconds: Number(data.get("timeout_seconds")),
    };
  }

  async function persistSource(form, payload) {
    const sourceId = form.dataset.sourceId;
    const response = await apiRequest(sourceId ? `/api/content-sources/${sourceId}` : "/api/content-sources", {
      method: sourceId ? "PUT" : "POST",
      body: payload,
    });
    form.dataset.sourceId = response.data.id;
    return response.data;
  }

  async function saveSource(event, testBeforeEnable) {
    event?.preventDefault?.();
    const form = event?.currentTarget || event;
    const submit = event?.submitter || form.querySelector('[type="submit"]');
    shell.setButtonBusy(submit, true, testBeforeEnable ? "测试中" : "保存中");
    try {
      const desiredEnabled = testBeforeEnable && new FormData(form).get("enabled") === "on";
      const source = await persistSource(form, payloadFromForm(form, true));
      if (testBeforeEnable) {
        const result = await apiRequest(`/api/content-sources/${source.id}/test`, { method: "POST" });
        if (!result.success) throw new Error(result.data?.error || "内容源测试失败");
        if (desiredEnabled) {
          await apiRequest(`/api/content-sources/${source.id}`, { method: "PUT", body: { enabled: true } });
        }
      }
      if (!isActive()) return;
      shell.closeDrawer();
      shell.toast(testBeforeEnable ? "内容源测试成功并已保存" : "内容源已保存为停用", "success");
      await load({ silent: true });
    } catch (error) {
      if (!isActive() || error?.name === "AbortError") return;
      shell.toast(error.message, "error");
      shell.setButtonBusy(submit, false);
    }
  }

  async function testSource(element) {
    shell.setButtonBusy(element, true, "测试中");
    try {
      const response = await apiRequest(`/api/content-sources/${element.dataset.sourceId}/test`, { method: "POST" });
      if (!isActive()) return;
      if (!response.success) throw new Error(response.data?.error || "测试失败");
      const latency = response.data?.latency_ms;
      shell.toast(`测试成功${latency == null ? "" : `，延迟 ${latency} ms`}`, "success");
      await load({ silent: true });
    } catch (error) {
      if (!isActive() || error?.name === "AbortError") return;
      shell.toast(error.message, "error");
    } finally {
      shell.setButtonBusy(element, false);
    }
  }

  async function testAll(element) {
    shell.setButtonBusy(element, true, "测试中");
    try {
      const response = await apiRequest("/api/content-sources/test-all", { method: "POST" });
      if (!isActive()) return;
      const results = response.data || [];
      const successCount = results.filter((result) => result.success).length;
      shell.toast(`全量测试完成：${successCount}/${results.length} 成功`, successCount === results.length ? "success" : "info");
      await load({ silent: true });
    } catch (error) {
      if (!isActive() || error?.name === "AbortError") return;
      shell.toast(error.message, "error");
    } finally {
      shell.setButtonBusy(element, false);
    }
  }

  async function moveSource(sourceId, direction) {
    const source = sources.find((item) => item.id === sourceId);
    if (!source) return;
    const list = sortSources(sources.filter((item) => item.source_type === source.source_type && !item.archived));
    const index = list.findIndex((item) => item.id === sourceId);
    const target = index + direction;
    if (target < 0 || target >= list.length) return;
    [list[index], list[target]] = [list[target], list[index]];
    try {
      await apiRequest("/api/content-sources/priorities", {
        method: "PATCH",
        body: { items: list.map((item, itemIndex) => ({ id: item.id, priority: (itemIndex + 1) * 10 })) },
      });
      if (!isActive()) return;
      await load({ silent: true });
    } catch (error) {
      if (!isActive() || error?.name === "AbortError") return;
      shell.toast(error.message, "error");
    }
  }

  async function archiveSource(element) {
    const source = sources.find((item) => item.id === element.dataset.sourceId);
    if (!source) return;
    const confirmed = await shell.confirm({ title: "归档内容源", message: `归档 ${source.name} 后，它不会再参与内容选择。现有用户配置会保留该引用，实际使用时将自动降级到其他可用来源。`, confirmLabel: "归档" });
    if (!confirmed || !isActive()) return;
    try {
      await apiRequest(`/api/content-sources/${source.id}`, { method: "DELETE" });
      if (!isActive()) return;
      shell.toast("内容源已归档", "success");
      await load({ silent: true });
    } catch (error) {
      if (!isActive() || error?.name === "AbortError") return;
      shell.toast(error.message, "error");
    }
  }

  async function load({ silent = false } = {}) {
    if (!isActive()) return;
    if (!silent) shell.loading("正在加载内容源健康状态");
    try {
      const response = await apiRequest("/api/content-sources");
      if (!isActive()) return;
      sources = response.data || [];
      render();
    } catch (error) {
      if (!isActive() || error?.name === "AbortError") return;
      if (!silent) shell.error(error);
      else shell.toast(error.message, "error");
    }
  }

  return {
    meta: {
      eyebrow: "内容链路",
      title: "内容源",
      subtitle: "管理文字与图片来源、优先级及健康状态",
      primaryAction: { action: "add-source", label: "添加内容源", icon: "plus" },
    },
    load,
    async handleAction(action, element) {
      const source = sources.find((item) => item.id === element.dataset.sourceId);
      if (action === "add-source") openSourceDrawer();
      if (action === "edit-source") openSourceDrawer(source);
      if (action === "copy-source") openSourceDrawer(source, { copy: true });
      if (action === "test-source") await testSource(element);
      if (action === "test-all-sources") await testAll(element);
      if (action === "move-source-up") await moveSource(element.dataset.sourceId, -1);
      if (action === "move-source-down") await moveSource(element.dataset.sourceId, 1);
      if (action === "archive-source") await archiveSource(element);
      if (action === "save-source-disabled") await saveSource(element.closest("form"), false);
    },
  };
}
