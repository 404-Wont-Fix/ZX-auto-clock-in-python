export function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}


export function initials(user) {
  const label = String(user?.nickname || user?.username || "U").trim();
  return escapeHtml(label.slice(0, 2).toLocaleUpperCase("zh-CN"));
}


export function formatDateTime(value, fallback = "尚无记录") {
  if (!value) return fallback;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return escapeHtml(value);
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}


export function formatFullDateTime(value, fallback = "—") {
  if (!value) return fallback;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return escapeHtml(value);
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(date);
}


export function formatDuration(milliseconds) {
  const value = Number(milliseconds);
  if (!Number.isFinite(value)) return "—";
  return value < 1000 ? `${value} ms` : `${(value / 1000).toFixed(1)} s`;
}


export function beijingToday() {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
}


export function statusLabel(status) {
  return ({
    pending: "等待执行",
    running: "执行中",
    completed: "已完成",
    failed: "失败",
    interrupted: "已中断",
    healthy: "健康",
    degraded: "降级",
    unavailable: "不可用",
    unknown: "未检查",
    disabled: "已停用",
  })[status] || status || "未知";
}


export function categoryResult(record, key) {
  const value = record?.details?.[key];
  if (!value) return "pending";
  return value.success ? "success" : "failure";
}


export function parseJsonInput(value, fallback) {
  const text = String(value || "").trim();
  if (!text) return fallback;
  try {
    return JSON.parse(text);
  } catch {
    throw new Error("JSON 格式无效");
  }
}


export function toBoolean(value) {
  return value === true || String(value).toLocaleLowerCase() === "true";
}
