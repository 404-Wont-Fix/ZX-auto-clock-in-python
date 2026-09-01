export function icon(name, className = "") {
  const safeName = String(name).replace(/[^a-z-]/g, "");
  const safeClass = String(className).replace(/[^a-zA-Z0-9 _-]/g, "");
  return `<svg${safeClass ? ` class="${safeClass}"` : ""} aria-hidden="true"><use href="#icon-${safeName}"></use></svg>`;
}
