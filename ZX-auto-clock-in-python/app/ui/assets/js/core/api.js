export class ApiError extends Error {
  constructor(message, { status = 0, payload = null } = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.payload = payload;
  }
}


const pendingReadControllers = new Set();


export function abortPendingReads() {
  for (const controller of pendingReadControllers) controller.abort();
  pendingReadControllers.clear();
}


function authHeaders() {
  const token = localStorage.getItem("auth_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}


export async function apiRequest(url, options = {}) {
  const headers = { Accept: "application/json", ...authHeaders(), ...(options.headers || {}) };
  let body = options.body;
  if (body !== undefined && body !== null && !(body instanceof FormData) && typeof body !== "string") {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(body);
  }

  const method = String(options.method || "GET").toUpperCase();
  const controller = method === "GET" && !options.signal ? new AbortController() : null;
  if (controller) pendingReadControllers.add(controller);
  let response;
  try {
    response = await fetch(url, {
      credentials: "include",
      ...options,
      headers,
      body,
      signal: options.signal || controller?.signal,
    });
  } finally {
    if (controller) pendingReadControllers.delete(controller);
  }
  const contentType = response.headers.get("content-type") || "";
  let payload = null;
  if (contentType.includes("application/json")) {
    payload = await response.json().catch(() => null);
  } else {
    payload = await response.text().catch(() => "");
  }

  if (response.status === 401) {
    localStorage.removeItem("auth_token");
    window.location.assign(window.ADMIN_PATH || "/admin");
  }
  if (!response.ok) {
    const message = payload?.error || payload?.detail || payload?.message || `请求失败（${response.status}）`;
    throw new ApiError(typeof message === "string" ? message : "请求参数无效", {
      status: response.status,
      payload,
    });
  }
  return payload;
}


export async function downloadExport() {
  const response = await fetch("/api/config/export", {
    headers: { ...authHeaders() },
    credentials: "include",
  });
  if (!response.ok) throw new ApiError("导出失败", { status: response.status });
  const blob = await response.blob();
  const disposition = response.headers.get("content-disposition") || "";
  const match = disposition.match(/filename="?([^";]+)"?/i);
  const filename = match?.[1] || "zx-admin-config.json";
  const anchor = document.createElement("a");
  anchor.href = URL.createObjectURL(blob);
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(anchor.href);
}


export async function logout() {
  try {
    await apiRequest("/api/auth/logout", { method: "POST" });
  } finally {
    localStorage.removeItem("auth_token");
    window.location.assign(window.ADMIN_PATH || "/admin");
  }
}
