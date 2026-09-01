import { escapeHtml } from "./format.js";
import { icon } from "./icons.js";


const content = document.querySelector("#page-content");
const drawerLayer = document.querySelector("#drawer-layer");
const drawerBody = document.querySelector("#drawer-body");
const confirmDialog = document.querySelector("#confirm-dialog");
const mobileMore = document.querySelector("#mobile-more");
let drawerCleanupTimer = null;


export const shell = {
  content,
  activeRoute: null,

  setPage({ eyebrow = "控制台", title, subtitle, primaryAction = null }) {
    document.querySelector("#page-eyebrow").textContent = eyebrow;
    document.querySelector("#page-title").textContent = title;
    document.querySelector("#page-subtitle").textContent = subtitle;
    const target = document.querySelector("#page-primary-action");
    if (!primaryAction) {
      target.replaceChildren();
      return;
    }
    target.innerHTML = `<button class="button primary" data-action="${escapeHtml(primaryAction.action)}" aria-label="${escapeHtml(primaryAction.label)}">${icon(primaryAction.icon || "plus")}<span>${escapeHtml(primaryAction.label)}</span></button>`;
  },

  setRoute(route) {
    this.activeRoute = route;
    document.querySelectorAll("[data-route]").forEach((link) => {
      link.classList.toggle("active", link.dataset.route === route);
      if (link.tagName === "A") {
        link.toggleAttribute("aria-current", link.dataset.route === route);
      }
    });
    const moreButton = document.querySelector('[data-action="toggle-mobile-more"]');
    moreButton.classList.toggle("active", ["sources", "settings"].includes(route));
    this.closeMobileMore();
  },

  isRouteActive(route) {
    return this.activeRoute === route;
  },

  loading(message = "正在加载数据") {
    content.innerHTML = `<div class="loading-state"><span class="spinner"></span><p>${escapeHtml(message)}</p></div>`;
    this.setSyncState("syncing", "正在同步");
  },

  error(error, retryAction = "refresh") {
    if (error?.name === "AbortError") return;
    content.innerHTML = `<div class="error-state"><div><h2>暂时无法加载</h2><p>${escapeHtml(error?.message || "未知错误")}</p><button class="button secondary" data-action="${escapeHtml(retryAction)}">${icon("refresh")}重新加载</button></div></div>`;
    this.setSyncState("error", "同步失败");
  },

  setSyncState(state, label) {
    const indicator = document.querySelector("#live-indicator");
    indicator.className = `live-indicator ${state}`;
    indicator.querySelector("span").textContent = label;
  },

  ready() {
    this.setSyncState("ready", "数据已同步");
  },

  openDrawer({ eyebrow = "详细信息", title, html }) {
    if (drawerCleanupTimer !== null) {
      window.clearTimeout(drawerCleanupTimer);
      drawerCleanupTimer = null;
    }
    document.querySelector("#drawer-eyebrow").textContent = eyebrow;
    document.querySelector("#drawer-title").textContent = title;
    drawerBody.innerHTML = html;
    drawerLayer.classList.add("open");
    drawerLayer.setAttribute("aria-hidden", "false");
    document.body.style.overflow = "hidden";
    requestAnimationFrame(() => drawerBody.querySelector("input, select, textarea, button")?.focus());
    return drawerBody;
  },

  closeDrawer() {
    drawerLayer.classList.remove("open");
    drawerLayer.setAttribute("aria-hidden", "true");
    document.body.style.overflow = "";
    if (drawerCleanupTimer !== null) window.clearTimeout(drawerCleanupTimer);
    drawerCleanupTimer = window.setTimeout(() => {
      drawerBody.replaceChildren();
      drawerCleanupTimer = null;
    }, 180);
  },

  confirm({ title, message, confirmLabel = "确认", danger = true }) {
    document.querySelector("#confirm-title").textContent = title;
    document.querySelector("#confirm-message").textContent = message;
    const submit = document.querySelector("#confirm-submit");
    submit.textContent = confirmLabel;
    submit.className = `button ${danger ? "danger" : "primary"}`;
    confirmDialog.showModal();
    return new Promise((resolve) => {
      confirmDialog.addEventListener("close", () => resolve(confirmDialog.returnValue === "confirm"), { once: true });
    });
  },

  toast(message, type = "info") {
    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    toast.textContent = message;
    document.querySelector("#toast-region").append(toast);
    window.setTimeout(() => toast.remove(), 3400);
  },

  toggleMobileMore() {
    const willOpen = mobileMore.hidden;
    mobileMore.hidden = !willOpen;
    document.querySelector('[data-action="toggle-mobile-more"]').setAttribute("aria-expanded", String(willOpen));
  },

  closeMobileMore() {
    mobileMore.hidden = true;
    document.querySelector('[data-action="toggle-mobile-more"]').setAttribute("aria-expanded", "false");
  },

  setButtonBusy(button, busy, busyLabel = "处理中") {
    if (!button) return;
    if (busy) {
      button.dataset.originalHtml = button.innerHTML;
      button.disabled = true;
      button.innerHTML = `<span class="spinner"></span>${escapeHtml(busyLabel)}`;
    } else {
      button.disabled = false;
      if (button.dataset.originalHtml) button.innerHTML = button.dataset.originalHtml;
      delete button.dataset.originalHtml;
    }
  },
};


document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && drawerLayer.classList.contains("open")) shell.closeDrawer();
});
