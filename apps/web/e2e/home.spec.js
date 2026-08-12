import { fileURLToPath } from "node:url";
import path from "node:path";
import { expect, test } from "@playwright/test";

// Plain JS rather than TS: the dashboard tsconfig includes every `**/*.ts`
// under apps/web, so a .ts spec importing @playwright/test would fail
// `next build` type-checking on a checkout where the nested e2e package's
// dependencies are not installed. See ../playwright.config.ts.

const ARTIFACT_DIR = path.join(path.dirname(fileURLToPath(import.meta.url)), "artifacts");

test("home page loads and renders its brand heading", async ({ page }) => {
  const response = await page.goto("/", { waitUntil: "domcontentloaded" });

  expect(response, "no HTTP response for GET /").not.toBeNull();
  expect(response.status(), "GET / did not return 200").toBe(200);

  // Assert on structure, not on the current copy: the dashboard's home page is
  // still being built, so brand strings would make this smoke test churn.
  await expect(page).toHaveTitle(/\S/);
  const heading = page.getByRole("heading").first();
  await expect(heading).toBeVisible();
  await expect(page.locator("main")).toBeVisible();

  await page.screenshot({
    path: path.join(ARTIFACT_DIR, "home.png"),
    fullPage: true,
  });
});
