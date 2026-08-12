/**
 * Playwright latency checks for thread UI responsiveness.
 * Measures time from user action → visible feedback.
 *
 * Run (local): cd apps/web && LATENCY_CHECK_ACCESS_TOKEN=<cookie value> npx tsx tests/latency-check.ts
 * Token: same value as the `access_token` cookie when signed in on localhost.
 */

import { chromium, type Page } from "playwright";

const BASE = "http://localhost:3000";
const API  = "http://localhost:8000";
const TOKEN = process.env.LATENCY_CHECK_ACCESS_TOKEN ?? "";

interface Metric { name: string; ms: number; budget: number; pass: boolean }
const results: Metric[] = [];

function record(name: string, ms: number, budget: number) {
  const pass = ms <= budget;
  results.push({ name, ms: Math.round(ms), budget, pass });
  console.log(`  [${pass ? "PASS" : "FAIL"}] ${name}: ${Math.round(ms)}ms (budget: ${budget}ms)`);
}

async function clickSafe(page: Page, selector: string, timeout = 5000) {
  const el = page.locator(selector).first();
  try {
    await el.click({ timeout });
  } catch {
    await el.click({ force: true, timeout });
  }
}

async function run() {
  if (!TOKEN) {
    console.error("Missing LATENCY_CHECK_ACCESS_TOKEN (access_token cookie value for localhost).");
    process.exit(1);
  }
  console.log("Warming up backend...");
  await fetch(`${API}/api/auth/me`, { headers: { Cookie: `access_token=${TOKEN}` } }).catch(() => {});
  await fetch(`${API}/api/auth/me`, { headers: { Cookie: `access_token=${TOKEN}` } }).catch(() => {});
  console.log("Backend warm.\n");

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  await context.addCookies([
    { name: "access_token", value: TOKEN, domain: "localhost", path: "/", sameSite: "Lax" },
  ]);

  const page = await context.newPage();
  const pageErrors: string[] = [];
  page.on("pageerror", (err) => pageErrors.push(err.message));

  // ── Load & authenticate ──
  console.log("1. Loading app...");
  await page.goto(BASE, { waitUntil: "domcontentloaded", timeout: 20000 });
  await page.evaluate((t) => localStorage.setItem("access_token", t), TOKEN);
  await page.reload({ waitUntil: "networkidle", timeout: 30000 });
  await page.locator(':text("Anh"), :text("inngress")').first()
    .waitFor({ state: "visible", timeout: 15000 })
    .catch(() => console.log("   Auth may not have resolved, continuing..."));

  const signedIn = !(await page.locator('button:has-text("Sign In")').isVisible().catch(() => true));
  console.log(`   Signed in: ${signedIn}`);
  if (!signedIn) {
    await browser.close();
    process.exit(1);
  }

  // ── Test 1: Thread click → detail load ──
  console.log("\n2. Test: Thread click → detail load");
  const threadBtn = page.locator('button:has-text("#")').first();
  if (await threadBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
    const t0 = Date.now();
    await clickSafe(page, 'button:has-text("#")');
    await page.locator('textarea[placeholder*="comment"], textarea[placeholder*="Leave"]')
      .waitFor({ state: "visible", timeout: 5000 }).catch(() => null);
    record("Thread click → detail view", Date.now() - t0, 500);

    // Back to list
    const backBtn = page.locator('span:has-text("Threads")').first();
    if (await backBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
      await clickSafe(page, 'span:has-text("Threads")');
      await page.waitForTimeout(500);
    }
  } else {
    console.log("   No threads to click, skipping");
  }

  // ── Test 2: New thread → send → Thinking visible ──
  console.log("\n3. Test: New thread send → Thinking latency");
  const newBtn = page.locator('button:has-text("New Thread")').first();
  if (await newBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
    await clickSafe(page, 'button:has-text("New Thread")');
    await page.waitForTimeout(500);
  }

  const textarea = page.locator('textarea[placeholder*="comment"], textarea[placeholder*="Leave"]').first();
  const sendBtn = page.locator('button[title="Send comment"]').first();

  if (await textarea.isVisible({ timeout: 3000 }).catch(() => false)) {
    const msg = `Latency test ${Date.now()}`;
    await textarea.fill(msg);
    await page.waitForTimeout(100);

    if (await sendBtn.isEnabled({ timeout: 2000 }).catch(() => false)) {
      const t1 = Date.now();
      await clickSafe(page, 'button[title="Send comment"]');

      // Optimistic user message should appear instantly
      const userMsgSel = `:text("${msg.substring(0, 20)}")`;
      await page.locator(userMsgSel).first()
        .waitFor({ state: "visible", timeout: 5000 }).catch(() => null);
      record("Send (new) → user msg visible", Date.now() - t1, 300);

      // Thinking shimmer
      const shimmer = page.locator('[class*="shimmer"]').first();
      const shimmerOk = await shimmer.waitFor({ state: "visible", timeout: 5000 }).then(() => true).catch(() => false);
      if (shimmerOk) {
        record("Send (new) → Thinking shimmer", Date.now() - t1, 500);
      } else {
        console.log("   Shimmer not found (may have resolved to content)");
      }

      // ── Test 3: Follow-up ──
      console.log("\n4. Test: Follow-up message latency");
      console.log("   Waiting 12s for agent to start responding...");
      await page.waitForTimeout(12000);

      const textarea2 = page.locator('textarea[placeholder*="comment"], textarea[placeholder*="Leave"]').first();
      if (await textarea2.isVisible({ timeout: 3000 }).catch(() => false)) {
        const followUp = `Follow-up ${Date.now()}`;
        await textarea2.fill(followUp);
        await page.waitForTimeout(100);

        const sendBtn2 = page.locator('button[title="Send comment"]').first();
        if (await sendBtn2.isEnabled({ timeout: 2000 }).catch(() => false)) {
          const t2 = Date.now();
          await clickSafe(page, 'button[title="Send comment"]');

          await page.locator(`:text("${followUp.substring(0, 15)}")`).first()
            .waitFor({ state: "visible", timeout: 5000 }).catch(() => null);
          record("Send (follow-up) → msg visible", Date.now() - t2, 300);

          const shimmer2 = page.locator('[class*="shimmer"]').first();
          const s2ok = await shimmer2.waitFor({ state: "visible", timeout: 5000 }).then(() => true).catch(() => false);
          if (s2ok) {
            record("Send (follow-up) → Thinking shimmer", Date.now() - t2, 500);
          } else {
            console.log("   Follow-up shimmer not detected");
          }
        } else {
          console.log("   Send button not enabled for follow-up");
        }
      } else {
        console.log("   Textarea not available for follow-up");
      }
    } else {
      console.log("   Send button not enabled");
    }
  } else {
    console.log("   Textarea not found");
  }

  // ── Page errors ──
  console.log("\n5. Page errors during test:");
  if (pageErrors.length === 0) {
    console.log("   None");
  } else {
    pageErrors.forEach((e, i) => console.log(`   [${i}] ${e.substring(0, 300)}`));
  }

  // ── Summary ──
  console.log("\n========================================");
  console.log("LATENCY TEST SUMMARY");
  console.log("========================================");
  const allPass = results.every((r) => r.pass);
  results.forEach((r) => {
    console.log(`  ${r.pass ? "✓" : "✗"} ${r.name}: ${r.ms}ms / ${r.budget}ms`);
  });
  console.log(`\n  Results: ${results.filter(r => r.pass).length}/${results.length} passed`);
  console.log(`  Page errors: ${pageErrors.length}`);
  console.log("========================================\n");

  await browser.close();
  process.exit(allPass && pageErrors.length === 0 ? 0 : 1);
}

run().catch((e) => {
  console.error("SCRIPT ERROR:", e);
  process.exit(2);
});
