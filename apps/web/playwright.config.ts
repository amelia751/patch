/**
 * Playwright configuration for the apps/web browser smoke suite.
 *
 * Two constraints shape this file:
 *
 * 1. It deliberately does not `import { defineConfig } from "@playwright/test"`.
 *    The dashboard's tsconfig includes every `**\/*.ts` under apps/web, so
 *    `next build` type-checks this file. The Playwright toolchain lives in the
 *    nested `e2e/` package and is not resolvable from apps/web/node_modules,
 *    so an import here would break the dashboard build whenever the e2e
 *    dependencies are not installed. `defineConfig` is an identity function
 *    that only supplies types, so a plain default export is equivalent.
 *
 * 2. The server lifecycle belongs to scripts/verify_apps_web_browser.sh, which
 *    picks a free port and tears the server down. This config therefore has no
 *    `webServer` block and reads the URL the script chose.
 */

const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:3000";

const config = {
  // Relative to this file, so the suite runs the same from any cwd.
  testDir: "./e2e",
  testMatch: "**/*.spec.js",
  outputDir: "./e2e/artifacts/test-results",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: 0,
  reporter: [["list"]],
  timeout: 30_000,
  expect: { timeout: 10_000 },
  use: {
    baseURL,
    browserName: "chromium",
    headless: true,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium" }],
};

export default config;
