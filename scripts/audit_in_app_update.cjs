/** Isolated Windows fixture only: actual browser, API, HTTP ZIP and helper. */
const { chromium, expect } = require("../frontend/node_modules/@playwright/test");
(async () => {
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage();
    const base = process.env.VIRA_NATIVE_BASE;
    await page.goto(base + "/login");
    await page.getByTestId("login-username").fill("owner");
    await page.getByTestId("login-password").fill(process.env.VIRA_NATIVE_PASSWORD);
    await page.getByTestId("login-submit").click();
    await page.waitForURL((url) => !url.pathname.includes("login"));
    await expect(page.getByTestId("update-badge")).toBeVisible();
    await page.goto(base + "/system");
    await page.getByTestId("sudo-password").fill(process.env.VIRA_NATIVE_PASSWORD);
    await page.getByTestId("sudo-confirm").click();
    await expect(page.getByTestId("sudo-dialog")).not.toBeVisible();
    const check = page.getByTestId("system-check-updates");
    await check.click();
    await expect(page.getByTestId("update-message")).toContainText("99.0.1");
    await page.getByTestId("update-decline").click();
    let counters = await (await page.request.get(process.env.VIRA_NATIVE_FEED + "/counts")).json();
    expect(counters.delta).toBe(0);
    expect(counters.full).toBe(0);
    await check.click();
    const download = page.waitForResponse((r) => r.url().endsWith("/update/download"));
    await page.getByTestId("update-accept").click();
    expect((await download).status()).toBe(200);
    await expect(page.getByTestId("update-apply")).toBeVisible({ timeout: 30000 });
    await page.request.post(process.env.VIRA_NATIVE_FEED + "/checkpoint");
    const apply = page.waitForResponse((r) => r.url().endsWith("/update/apply"));
    await page.getByTestId("update-apply").click();
    expect((await apply).status()).toBe(200);
    // No route interception: temporary disconnects are the real backend restart.
    await expect(async () => {
      const response = await page.request.get(base + "/api/v1/system/update/status", { timeout: 2000 });
      expect(response.status()).toBe(200);
      const result = await response.json();
      expect(result.state).toBe(process.env.VIRA_NATIVE_EXPECTED);
    }).toPass({ timeout: 90000, intervals: [500, 1000] });
    const intact = await page.request.get(process.env.VIRA_NATIVE_FEED + "/verify-data");
    expect(intact.status(), await intact.text()).toBe(200);
    if (process.env.VIRA_NATIVE_EXPECTED === "committed") await page.getByTestId("update-finish").click();
    else { await expect(page.getByTestId("update-failed")).toBeVisible(); await page.reload(); }
    await page.getByTestId("sudo-password").fill(process.env.VIRA_NATIVE_PASSWORD);
    await page.getByTestId("sudo-confirm").click();
    await expect(page.getByTestId("system-last-update")).toBeVisible();
    counters = await (await page.request.get(process.env.VIRA_NATIVE_FEED + "/counts")).json();
    expect(counters).toEqual({ delta: 1, full: 0 });
    console.log("Native in-app update:", process.env.VIRA_NATIVE_EXPECTED, "— consent, delta-only, SQLite and receipt hashes verified");
  } finally { await browser.close(); }
})().catch((error) => { console.error(error); process.exitCode = 1; });
