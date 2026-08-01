import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";


test("Playwright contract covers the approved admin interaction surfaces", () => {
  const packageJson = JSON.parse(fs.readFileSync("package.json", "utf8"));
  const config = fs.readFileSync("playwright.config.mjs", "utf8");
  const spec = fs.readFileSync("tests/e2e/admin-console.spec.mjs", "utf8");

  assert.equal(packageJson.scripts["test:e2e"], "playwright test");
  assert.match(config, /colorScheme/);
  assert.match(config, /existsSync\(venvPython\)/);
  assert.match(config, /process\.env\.PYTHON_BIN \|\|/);
  for (const surface of ["总览", "用户", "打卡记录", "内容源", "系统设置"]) {
    assert.match(spec, new RegExp(surface));
  }
  for (const behavior of ["Escape", "task-panel", "mobile-nav", "prefers-color-scheme"]) {
    assert.match(spec, new RegExp(behavior));
  }
});
