import { expect, test } from "@playwright/test";


function json(route, payload, status = 200) {
  return route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(payload),
  });
}


async function installAdminMocks(page) {
  const state = {
    activeTask: null,
    users: [
      {
        id: "user-1",
        username: "demo_user",
        nickname: "演示用户",
        enabled: true,
        password_configured: true,
        clockin_count: 12,
        last_clockin: "2026-07-31T01:05:00",
        sports_comment_type: "api",
        sports_comment_api: "poetry_all",
        sports_custom_comment: "",
        sports_image_type: "api",
        sports_image_provider: "bing",
        sports_image_category: "random",
        daily_comment_type: "api",
        daily_comment_api: "hitokoto",
        custom_daily_comment: "",
      },
    ],
    sources: [
      {
        id: "source-text",
        key: "poetry_all",
        name: "今日诗词",
        source_type: "text",
        enabled: true,
        archived: false,
        priority: 10,
        url_template: "https://v1.jinrishici.com/all.json",
        query_params: {},
        parse_mode: "json_text",
        value_path: "content",
        attribution_path: null,
        categories: [],
        timeout_seconds: 10,
        health_status: "healthy",
        latency_ms: 23,
        last_checked_at: "2026-07-31T01:00:00",
        last_error: null,
      },
      {
        id: "source-image",
        key: "bing",
        name: "Bing 每日壁纸",
        source_type: "image",
        enabled: true,
        archived: false,
        priority: 10,
        url_template: "https://www.bing.com/HPImageArchive.aspx",
        query_params: { format: "js" },
        parse_mode: "json_image",
        value_path: "images.0.url",
        attribution_path: null,
        categories: [],
        timeout_seconds: 10,
        health_status: "healthy",
        latency_ms: 31,
        last_checked_at: "2026-07-31T01:00:00",
        last_error: null,
      },
    ],
  };

  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();

    if (path === "/api/auth/login") return route.continue();

    if (path === "/api/dashboard/summary") {
      const enabledSources = state.sources.filter((source) => source.enabled && !source.archived);
      const sourceCount = (status) => enabledSources.filter((source) => source.health_status === status).length;
      return json(route, {
        success: true,
        data: {
          date: "2026-07-31",
          today: { enabled_users: 1, success: 0, failure: 1, pending: 0 },
          failed_users: [
            { id: "user-1", username: "demo_user", nickname: "演示用户", error: "模拟网络失败" },
          ],
          active_task: state.activeTask,
          next_run_time: "2026-08-01T00:10:00+08:00",
          workers: { enabled: 1, healthy: 1, unavailable: 0 },
          content_sources: {
            total: enabledSources.length,
            healthy: sourceCount("healthy"),
            degraded: sourceCount("degraded"),
            unavailable: sourceCount("unavailable"),
            unknown: sourceCount("unknown"),
          },
        },
      });
    }

    if (path === "/api/users" && method === "GET") {
      return json(route, { success: true, data: state.users });
    }
    if (path === "/api/users" && method === "POST") {
      const body = request.postDataJSON();
      const user = { id: `user-${state.users.length + 1}`, password_configured: true, clockin_count: 0, ...body };
      state.users.push(user);
      return json(route, { success: true, data: user });
    }
    if (path.startsWith("/api/users/") && ["PUT", "PATCH"].includes(method)) {
      const user = state.users.find((item) => path.includes(item.id));
      Object.assign(user, request.postDataJSON());
      return json(route, { success: true, data: user });
    }

    if (path === "/api/content-sources" && method === "GET") {
      return json(route, { success: true, data: state.sources });
    }
    if (path === "/api/content-sources" && method === "POST") {
      const body = request.postDataJSON();
      const source = {
        id: `source-${state.sources.length + 1}`,
        archived: false,
        health_status: "disabled",
        latency_ms: null,
        last_checked_at: null,
        last_error: null,
        ...body,
      };
      state.sources.push(source);
      return json(route, { success: true, data: source }, 201);
    }
    if (path === "/api/content-sources/priorities" && method === "PATCH") {
      for (const item of request.postDataJSON().items) {
        const source = state.sources.find((candidate) => candidate.id === item.id);
        if (source) source.priority = item.priority;
      }
      return json(route, { success: true, data: state.sources });
    }
    if (path.match(/^\/api\/content-sources\/[^/]+\/test$/) && method === "POST") {
      const id = path.split("/")[3];
      const source = state.sources.find((item) => item.id === id);
      Object.assign(source, { health_status: "healthy", latency_ms: 18, last_error: null });
      return json(route, { success: true, data: { latency_ms: 18, source } });
    }
    if (path === "/api/content-sources/test-all" && method === "POST") {
      return json(route, { success: true, data: state.sources.map((source) => ({ success: true, source })) });
    }
    if (path.startsWith("/api/content-sources/") && method === "PUT") {
      const id = path.split("/")[3];
      const source = state.sources.find((item) => item.id === id);
      Object.assign(source, request.postDataJSON());
      return json(route, { success: true, data: source });
    }

    if (path === "/api/clockin/results") {
      return json(route, {
        success: true,
        data: {
          summary: {
            total_users: 1,
            success_count: 0,
            failure_count: 1,
            home_success: 1,
            sports_success: 0,
            daily_success: 1,
          },
          results: [
            {
              id: "record-1",
              user_id: "user-1",
              username: "demo_user",
              nickname: "演示用户",
              success: false,
              error: "模拟网络失败",
              timestamp: "2026-07-31T01:05:00",
              duration_ms: 1530,
              triggered_by: "manual",
              details: {
                home: { success: true },
                sports: { success: false },
                daily: { success: true },
              },
              sports_comment: "测试运动文案",
              daily_comment: "测试日精进文案",
              sports_image_provider: "bing",
              sports_image_category: "random",
            },
          ],
        },
      });
    }

    if (path === "/api/clockin/tasks" && method === "POST") {
      state.activeTask = {
        id: "task-e2e-progress",
        scope: request.postDataJSON().scope,
        date: "2026-07-31",
        status: "running",
        progress: { current: 1, total: 4, success: 1, failure: 0, percent: 25 },
      };
      return json(route, { success: true, data: state.activeTask }, 202);
    }
    if (path === "/api/clockin/tasks/task-e2e-progress" && method === "GET") {
      const completed = {
        ...state.activeTask,
        status: "completed",
        progress: { current: 4, total: 4, success: 3, failure: 1, percent: 100 },
      };
      state.activeTask = null;
      return json(route, { success: true, data: completed });
    }

    if (path === "/api/config") {
      return json(route, {
        success: true,
        data: {
          schedule_cron: "0 10 0 * * *",
          schedule_enabled: true,
          schedule_timezone: "Asia/Shanghai",
          schedule_retry_count: 2,
          retention_days: 7,
        },
      });
    }
    if (path === "/api/config/schedule") {
      return json(route, {
        success: true,
        data: {
          scheduler_running: true,
          schedule_enabled: true,
          job_info: { next_run_time: "2026-08-01T00:10:00+08:00" },
        },
      });
    }
    if (path === "/api/worker-apis") {
      return json(route, {
        success: true,
        data: [
          {
            id: "worker-1",
            name: "测试 Worker",
            url: "https://worker.example",
            enabled: true,
            available: true,
            token_configured: true,
            token_masked: "test••••oken",
            total_requests: 8,
            total_success: 8,
            total_failure: 0,
            failure_count: 0,
            last_check: "2026-07-31T01:00:00",
          },
        ],
      });
    }

    return json(route, { success: true, data: null });
  });

  return state;
}


async function login(page) {
  await page.goto("/e2e-admin");
  await page.getByLabel("用户名").fill("e2e-admin");
  await page.getByLabel("密码").fill("e2e-admin-password");
  await page.getByRole("button", { name: "登录" }).click();
  await page.waitForURL("**/dashboard");
  await expect(page.locator("#page-title")).toHaveText("总览");
}


test("桌面五页、抽屉、任务进度和内容源管理保持三层内交互", async ({ page }) => {
  await installAdminMocks(page);
  await login(page);

  await expect(page.locator(".primary-nav a")).toHaveCount(5);
  for (const label of ["总览", "用户", "打卡记录", "内容源", "系统设置"]) {
    await expect(page.locator(".primary-nav").getByText(label, { exact: true })).toBeVisible();
  }

  await page.locator('.primary-nav a[data-route="users"]').click();
  await expect(page.locator("#page-title")).toHaveText("用户");
  await page.locator("#user-search").fill("demo_user");
  await expect(page.locator("#user-count")).toHaveText("1 / 1");
  await page.getByRole("button", { name: "添加用户" }).click();
  await expect(page.locator("#drawer-layer")).toHaveClass(/open/);
  await page.keyboard.press("Escape");
  await expect(page.locator("#drawer-layer")).not.toHaveClass(/open/);

  await page.locator('.primary-nav a[data-route="records"]').click();
  await expect(page.locator("#page-title")).toHaveText("打卡记录");
  await page.locator('[data-action="record-detail"]').first().click();
  await expect(page.locator("#drawer-title")).toHaveText("演示用户");
  await page.keyboard.press("Escape");

  await page.locator('.primary-nav a[data-route="sources"]').click();
  await expect(page.locator("#page-title")).toHaveText("内容源");
  await page.getByRole("button", { name: "添加内容源" }).click();
  const sourceForm = page.locator("#source-form");
  await sourceForm.locator('[name="key"]').fill("e2e-source");
  await sourceForm.locator('[name="name"]').fill("E2E 内容源");
  await sourceForm.locator('[name="url_template"]').fill("https://content.example/quote");
  await sourceForm.locator('[name="value_path"]').fill("quote");
  await sourceForm.getByRole("button", { name: "保存为停用" }).click();
  const createdSourceRow = page.locator(".source-row").filter({ hasText: "E2E 内容源" });
  await expect(createdSourceRow).toBeVisible();
  await expect(createdSourceRow).toContainText("停用");

  await page.locator('.primary-nav a[data-route="settings"]').click();
  await expect(page.locator("#page-title")).toHaveText("系统设置");
  await page.getByRole("button", { name: "添加节点" }).click();
  await expect(page.locator("#worker-form")).toBeVisible();
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "清理旧记录" }).click();
  await expect(page.locator("#confirm-dialog")).toBeVisible();
  await page.locator('#confirm-dialog button[value="cancel"]').click();
  await page.locator("#cleanup-days").fill("-1");
  await page.getByRole("button", { name: "清理旧记录" }).click();
  await expect(page.locator("#confirm-dialog")).not.toBeVisible();
  await expect(page.locator("#toast-region")).toContainText("保留天数必须是 1–3650 的整数");

  await page.locator('.primary-nav a[data-route="overview"]').click();
  await page.locator("#page-primary-action button").click();
  await expect(page.locator("#confirm-dialog")).toBeVisible();
  await page.locator("#confirm-submit").click();
  await expect(page.locator(".task-panel")).toBeVisible();
  await expect(page.locator(".task-percent")).toHaveText("25%");
  await expect(page.locator(".task-percent")).toHaveText("100%", { timeout: 5000 });
  await expect(page.locator(".task-panel")).toContainText("已完成");
});


test("prefers-color-scheme 自动切换系统明暗主题", async ({ page }) => {
  await installAdminMocks(page);
  await page.emulateMedia({ colorScheme: "light" });
  await login(page);
  const canvas = () => page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue("--canvas").trim());
  await expect.poll(canvas).toBe("#f3f5f8");

  await page.emulateMedia({ colorScheme: "dark" });
  await expect.poll(canvas).toBe("#0d0f12");
});


test("快速切换页面时旧请求不会覆盖当前页面", async ({ page }) => {
  await installAdminMocks(page);
  await login(page);
  await page.route("**/api/users", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 500));
    return json(route, { success: true, data: [] });
  });

  await page.locator('.primary-nav a[data-route="users"]').click();
  await page.locator('.primary-nav a[data-route="sources"]').click();
  await expect(page.locator("#page-title")).toHaveText("内容源");
  await page.waitForTimeout(700);

  await expect(page.locator(".source-row")).toHaveCount(2);
  await expect(page.locator("#user-count")).toHaveCount(0);
});


test("旧页面保存完成后不会刷新并覆盖已经切换的新页面", async ({ page }) => {
  await installAdminMocks(page);
  await login(page);

  let markMutationStarted;
  let releaseMutation;
  const mutationStarted = new Promise((resolve) => { markMutationStarted = resolve; });
  const mutationGate = new Promise((resolve) => { releaseMutation = resolve; });
  await page.route("**/api/users/user-1", async (route) => {
    if (route.request().method() !== "PUT") return route.fallback();
    markMutationStarted();
    await mutationGate;
    return json(route, { success: true, data: { id: "user-1" } });
  });

  await page.locator('.primary-nav a[data-route="users"]').click();
  await page.locator('[data-action="edit-user"]').first().click();
  await page.locator("#user-form").getByRole("button", { name: "保存修改" }).click();
  await mutationStarted;

  await page.evaluate(() => { window.location.hash = "#/records"; });
  await expect(page.locator("#page-title")).toHaveText("打卡记录");
  await page.locator('[data-action="record-detail"]').first().click();
  await expect(page.locator("#drawer-layer")).toHaveClass(/open/);
  releaseMutation();
  await page.waitForTimeout(500);

  await expect(page.locator("#records-desktop-body")).toHaveCount(1);
  await expect(page.locator("#user-count")).toHaveCount(0);
  await expect(page.locator("#drawer-layer")).toHaveClass(/open/);
  await expect(page.locator("#drawer-eyebrow")).toHaveText("执行失败");
});


test("离开总览后延迟返回的任务冲突不会污染当前页面", async ({ page }) => {
  await installAdminMocks(page);
  await login(page);

  let markTaskStarted;
  let markTaskResponded;
  let releaseTask;
  const taskStarted = new Promise((resolve) => { markTaskStarted = resolve; });
  const taskResponded = new Promise((resolve) => { markTaskResponded = resolve; });
  const taskGate = new Promise((resolve) => { releaseTask = resolve; });
  await page.route("**/api/clockin/tasks", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    markTaskStarted();
    await taskGate;
    await json(route, { success: false, error: "已有任务正在执行", data: { task_id: "existing-task" } }, 409);
    markTaskResponded();
  });
  await page.route("**/api/clockin/tasks/existing-task", async (route) => {
    return json(route, {
      success: true,
      data: {
        id: "existing-task",
        scope: "all",
        date: "2026-07-31",
        status: "running",
        progress: { current: 1, total: 2, success: 1, failure: 0, percent: 50 },
      },
    });
  });

  await page.locator("#page-primary-action button").click();
  await page.locator("#confirm-submit").click();
  await taskStarted;
  await page.evaluate(() => { window.location.hash = "#/records"; });
  await expect(page.locator("#page-title")).toHaveText("打卡记录");
  releaseTask();
  await taskResponded;
  await page.waitForTimeout(500);

  expect(await page.locator("#toast-region").innerText()).not.toContain("已有任务正在执行");
  await expect(page.locator("#records-desktop-body")).toHaveCount(1);
});


test("内容源列表直接展示优先级和最近错误", async ({ page }) => {
  await installAdminMocks(page);
  await login(page);
  await page.locator('.primary-nav a[data-route="sources"]').click();

  const source = page.locator(".source-row").filter({ hasText: "今日诗词" });
  await expect(source).toContainText("优先级");
  await expect(source).toContainText("10");
  await expect(source).toContainText("最近错误");
  await expect(source).toContainText("无");
  await source.locator("details.row-menu > summary").click();
  await source.getByRole("button", { name: "归档内容源" }).click();
  await expect(page.locator("#confirm-dialog")).toContainText("自动降级");
});


test("未检查的启用内容源计入需要关注", async ({ page }) => {
  const state = await installAdminMocks(page);
  state.sources[0].health_status = "unknown";
  state.sources[0].last_checked_at = null;
  await login(page);

  const overviewHealth = page.locator(".health-card").filter({ hasText: "内容源" });
  await expect(overviewHealth).toContainText("1 个未检查");
  await page.locator('.primary-nav a[data-route="sources"]').click();

  const attention = page.locator(".metric-card").filter({ hasText: "需要关注" });
  await expect(attention.locator(".metric-value")).toHaveText("1");
  await expect(attention).toContainText("含未检查");
});


test("手机用户和 Worker 卡片提供完整维护入口", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await installAdminMocks(page);
  await login(page);

  await page.locator('.mobile-nav a[data-route="users"]').click();
  const userCard = page.locator("#users-mobile-list .mobile-card").first();
  await expect(userCard.locator('[data-action="toggle-user"]')).toBeVisible();
  await userCard.locator("details.row-menu > summary").click();
  await expect(userCard.getByRole("button", { name: "删除用户" })).toBeVisible();

  await page.getByRole("button", { name: "更多" }).click();
  await page.locator('#mobile-more a[href="#/settings"]').click();
  const workerCard = page.locator(".mobile-card-list .mobile-card").first();
  await workerCard.locator("details.row-menu > summary").click();
  await expect(workerCard.getByRole("button", { name: "重置可用状态" })).toBeVisible();
  await expect(workerCard.getByRole("button", { name: "删除节点" })).toBeVisible();
});


test("手机四项 mobile-nav 将内容源和系统设置收进更多", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await installAdminMocks(page);
  await login(page);

  await expect(page.locator(".sidebar")).toBeHidden();
  await expect(page.locator(".mobile-nav")).toBeVisible();
  await expect(page.locator(".mobile-nav > *")).toHaveCount(4);
  await page.getByRole("button", { name: "更多" }).click();
  await expect(page.locator("#mobile-more")).toBeVisible();
  await page.locator('#mobile-more a[href="#/sources"]').click();
  await expect(page.locator("#page-title")).toHaveText("内容源");

  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});
