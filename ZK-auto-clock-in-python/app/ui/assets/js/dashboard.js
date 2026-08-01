import { abortPendingReads, logout } from "./core/api.js";
import { shell } from "./core/shell.js";
import { resolveRoute } from "./core/state.js";
import { createOverviewPage } from "./pages/overview.js";
import { createRecordsPage } from "./pages/records.js";
import { createSettingsPage } from "./pages/settings.js";
import { createSourcesPage } from "./pages/sources.js";
import { createUsersPage } from "./pages/users.js";


if (!localStorage.getItem("auth_token")) {
  window.location.replace(window.ADMIN_PATH || "/admin");
}

const controllers = {
  overview: createOverviewPage(shell),
  users: createUsersPage(shell),
  records: createRecordsPage(shell),
  sources: createSourcesPage(shell),
  settings: createSettingsPage(shell),
};

let activeRoute = null;
let activeController = null;
let navigationVersion = 0;


async function navigate() {
  const route = resolveRoute(window.location.hash);
  const version = ++navigationVersion;
  abortPendingReads();
  if (activeController?.dispose) activeController.dispose();
  activeRoute = route;
  activeController = controllers[route];
  shell.closeDrawer();
  shell.setRoute(route);
  shell.setPage(activeController.meta);
  await activeController.load();
  if (version !== navigationVersion) return;
  document.querySelector(".workspace")?.scrollTo?.({ top: 0, behavior: "instant" });
}


document.addEventListener("click", async (event) => {
  const routeJump = event.target.closest("[data-route-jump]");
  if (routeJump) {
    window.location.hash = `#/${routeJump.dataset.routeJump}`;
    return;
  }

  const actionTarget = event.target.closest("[data-action]");
  if (!actionTarget) return;
  const action = actionTarget.dataset.action;
  if (action === "close-drawer") return shell.closeDrawer();
  if (action === "toggle-mobile-more") return shell.toggleMobileMore();
  if (action === "refresh") return activeController?.load();
  if (action === "logout") {
    const confirmed = await shell.confirm({ title: "退出控制台", message: "将结束当前管理员会话并返回登录页。", confirmLabel: "退出", danger: false });
    if (confirmed) await logout();
    return;
  }
  await activeController?.handleAction?.(action, actionTarget);
});


document.addEventListener("input", (event) => {
  if (event.target.matches('input[type="search"][data-filter]')) activeController?.handleInput?.(event.target);
});


document.addEventListener("change", (event) => {
  if (event.target.matches("select[data-filter], input[type=date][data-filter]")) {
    activeController?.handleInput?.(event.target);
  }
});


window.addEventListener("hashchange", navigate);
window.addEventListener("pageshow", () => {
  if (!window.location.hash) window.location.hash = "#/overview";
});

if (!window.location.hash) window.location.hash = "#/overview";
else navigate();

export { activeRoute, controllers, navigate };
