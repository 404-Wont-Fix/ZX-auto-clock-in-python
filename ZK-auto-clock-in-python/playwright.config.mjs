import { defineConfig, devices } from "@playwright/test";
import { existsSync } from "node:fs";


const venvPython = process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python";
const systemPython = process.platform === "win32" ? "python" : "python3";
const python = process.env.PYTHON_BIN || (existsSync(venvPython) ? venvPython : systemPython);


export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 30_000,
  expect: { timeout: 5_000 },
  reporter: "line",
  use: {
    baseURL: "http://127.0.0.1:18033",
    colorScheme: "dark",
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1440, height: 900 },
      },
    },
  ],
  webServer: {
    command: [
      "env",
      "APP_ENV=production",
      "DEBUG=false",
      "SECRET_KEY=playwright-runtime-secret-key",
      "ADMIN_USERNAME=e2e-admin",
      "ADMIN_PASSWORD=e2e-admin-password",
      "ADMIN_PATH=e2e-admin",
      "DATABASE_URL=sqlite:////tmp/zk-admin-playwright.db",
      "SCHEDULE_ENABLED=false",
      python,
      "-m uvicorn app.main:app --host 127.0.0.1 --port 18033 --workers 1",
    ].join(" "),
    url: "http://127.0.0.1:18033/health",
    timeout: 120_000,
    reuseExistingServer: !process.env.CI,
  },
});
