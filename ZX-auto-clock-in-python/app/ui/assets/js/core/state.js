export const ROUTES = Object.freeze(["overview", "users", "records", "sources", "settings"]);


export function resolveRoute(hash = "") {
  const route = String(hash)
    .replace(/^#\/?/, "")
    .split(/[/?]/, 1)[0]
    .trim();
  return ROUTES.includes(route) ? route : "overview";
}


export function filterUsers(users, { query = "", status = "all" } = {}) {
  const needle = query.trim().toLocaleLowerCase("zh-CN");
  return users.filter((user) => {
    const matchesText = !needle || [user.username, user.nickname]
      .some((value) => String(value || "").toLocaleLowerCase("zh-CN").includes(needle));
    const matchesStatus = status === "all"
      || (status === "enabled" && Boolean(user.enabled))
      || (status === "disabled" && !user.enabled);
    return matchesText && matchesStatus;
  });
}


export function filterRecords(records, { status = "all", userId = "all" } = {}) {
  return records.filter((record) => {
    const matchesStatus = status === "all"
      || (status === "success" && Boolean(record.success))
      || (status === "failure" && !record.success);
    const matchesUser = userId === "all" || record.user_id === userId;
    return matchesStatus && matchesUser;
  });
}


export function sourceHealthState(source) {
  const failures = Number(source?.consecutive_failures || 0);
  if (failures >= 3) return "unavailable";
  if (failures > 0) return "degraded";
  if (source?.last_success_at) return "healthy";
  return "unknown";
}


export function sortSources(sources) {
  return [...sources].sort((left, right) => {
    const priority = Number(left.priority || 0) - Number(right.priority || 0);
    return priority || String(left.name || left.key).localeCompare(String(right.name || right.key), "zh-CN");
  });
}


export function taskNeedsPolling(task) {
  return Boolean(task && ["pending", "running"].includes(task.status));
}
