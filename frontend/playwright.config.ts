import { defineConfig, devices } from "@playwright/test";
import path from "node:path";

const root = path.resolve("..");
const python =
  process.env.ATG_PYTHON ||
  path.join(
    root,
    ".venv",
    process.platform === "win32" ? "Scripts/python.exe" : "bin/python",
  );
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 240_000,
  expect: { timeout: 15_000 },
  reporter: [
    ["list"],
    ["json", { outputFile: "../docs/results/browser-tests.json" }],
  ],
  use: {
    ...devices["Desktop Chrome"],
    channel: process.env.PW_CHANNEL || "chrome",
    baseURL: "http://127.0.0.1:5174",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  webServer: [
    {
      command: `"${python}" -m toolguard.cli serve --port 8010`,
      url: "http://127.0.0.1:8010/api/health",
      timeout: 30_000,
      reuseExistingServer: false,
      env: {
        PYTHONPATH: path.join(root, "backend"),
        PYTHONUTF8: "1",
        ATG_DATABASE: `.local/e2e-${Date.now()}.sqlite3`,
        ATG_UI_ORIGIN: "http://127.0.0.1:5174",
        ATG_DEMO_PASSWORD: "Demo-Only-2026!",
      },
    },
    {
      command: "npm run dev -- --port 5174",
      url: "http://127.0.0.1:5174",
      timeout: 30_000,
      reuseExistingServer: false,
      env: { ATG_API_URL: "http://127.0.0.1:8010" },
    },
  ],
});
