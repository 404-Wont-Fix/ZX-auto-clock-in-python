import test from "node:test";
import assert from "node:assert/strict";
import { access, readFile } from "node:fs/promises";


const root = new URL("../../", import.meta.url);


test("dashboard uses local modular assets and five top-level routes", async () => {
  const html = await readFile(new URL("app/ui/pages/index.html", root), "utf8");
  const routes = [...html.matchAll(/data-route="([a-z]+)"/g)].map((match) => match[1]);

  assert.deepEqual([...new Set(routes)], ["overview", "users", "records", "sources", "settings"]);
  assert.match(html, /type="module" src="\/assets\/js\/dashboard\.js/);
  assert.doesNotMatch(html, /tailwind|daisyui|cdn\.jsdelivr/i);

  for (const page of ["overview", "users", "records", "sources", "settings"]) {
    await access(new URL(`app/ui/assets/js/pages/${page}.js`, root));
  }
});


test("dashboard and login avoid gradients, glass effects and emoji controls", async () => {
  const files = await Promise.all([
    "app/ui/pages/index.html",
    "app/ui/pages/login.html",
    "app/ui/assets/styles.css",
    "app/ui/assets/login.css",
    "app/ui/assets/login.js",
  ].map((path) => readFile(new URL(path, root), "utf8")));
  const source = files.join("\n");

  assert.doesNotMatch(source, /(?:linear|radial)-gradient|backdrop-filter/i);
  assert.doesNotMatch(source, /[😀-🙏🌀-🫿⚠✓]/u);
});


test("mobile navigation exposes exactly four primary choices", async () => {
  const html = await readFile(new URL("app/ui/pages/index.html", root), "utf8");
  const mobileNav = html.match(/<nav class="mobile-nav"[\s\S]*?<\/nav>/)?.[0] || "";
  const items = [...mobileNav.matchAll(/<(?:a|button)[^>]*>[\s\S]*?<span>([^<]+)<\/span>[\s\S]*?<\/(?:a|button)>/g)]
    .map((match) => match[1]);

  assert.deepEqual(items, ["总览", "用户", "记录", "更多"]);
});


test("settings does not expose a retry control unused by durable tasks", async () => {
  const settings = await readFile(new URL("app/ui/assets/js/pages/settings.js", root), "utf8");

  assert.doesNotMatch(settings, /schedule_retry_count/);
  assert.doesNotMatch(settings, /失败重试轮次/);
});
