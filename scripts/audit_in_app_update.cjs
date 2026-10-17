/** Isolated Windows fixture only: actual browser, API, HTTP ZIP and helper. */
const { chromium, expect } = require("../frontend/node_modules/@playwright/test");
async function stepUp(page) {
  // Historical 1.0.9 has no sudo test IDs. Use its real native dialog/form,
  // and observe the UI's authenticated request (sudo token is JS memory, not
  // a cookie that APIRequestContext can attach on our behalf).
  const dialog = page.locator('dialog[open]');
  const status = page.waitForResponse((r) => r.url().endsWith("/api/v1/system/status") && r.status() === 200);
  await dialog.locator('input[type="password"]').fill(process.env.VIRA_NATIVE_PASSWORD);
  await dialog.locator('button[type="submit"]').click();
  await expect(dialog).not.toBeVisible();
  return (await status).json();
}
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
    const legacy = process.env.VIRA_NATIVE_LEGACY === "1";
    if (!legacy) await expect(page.getByTestId("update-badge")).toBeVisible();
    await page.goto(base + "/system");
    const initial = await stepUp(page);
    if (legacy) {
      expect(initial.version).toBe(process.env.VIRA_NATIVE_BASE_VERSION || "1.0.9");
      expect(initial.commit).toBe(process.env.VIRA_NATIVE_BASE_COMMIT || "7d78720");
      await expect(page.getByTestId("system-build-ids").locator("span.num")).toHaveText(Array(3).fill(process.env.VIRA_NATIVE_BASE_COMMIT || "7d78720"));
    }
    const check = page.getByTestId("system-check-updates");
    await check.click();
    await expect(page.getByTestId("update-message")).toContainText(process.env.VIRA_NATIVE_TARGET || "99.0.1");
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
      // A rolled-back historical 1.0.9 API has no durable-result reader.
      // Observe the actual helper file via the fixture, never pretend its UI has
      // the new protocol. Success MUST be visible through the new product API.
      const endpoint = legacy && process.env.VIRA_NATIVE_EXPECTED === "rolled_back"
        ? process.env.VIRA_NATIVE_FEED + "/attempt-result"
        : base + "/api/v1/system/update/status";
      const response = await page.request.get(endpoint, { timeout: 2000 });
      expect(response.status()).toBe(200);
      const result = await response.json();
      expect(result.state).toBe(process.env.VIRA_NATIVE_EXPECTED);
    }).toPass({ timeout: legacy ? 150000 : 90000, intervals: [500, 1000] });
    const intact = await page.request.get(process.env.VIRA_NATIVE_FEED + "/verify-data");
    expect(intact.status(), await intact.text()).toBe(200);
    if (process.env.VIRA_NATIVE_EXPECTED === "committed") {
      await page.getByTestId("update-finish").click();
      // 1.0.9's existing finish button only closes its dialog. Explicit reload
      // is a documented first-hop limitation, not an injected client fix.
      if (legacy) await page.reload();
    } else { await expect(page.getByTestId("update-failed")).toBeVisible(); await page.reload(); }
    const resumed = await stepUp(page);
    if (!(legacy && process.env.VIRA_NATIVE_EXPECTED === "rolled_back"))
      await expect(page.getByTestId("system-last-update")).toBeVisible();
    if (legacy) {
      const status = resumed;
      expect(status.version).toBe(process.env.VIRA_NATIVE_EXPECTED === "committed" ? (process.env.VIRA_NATIVE_TARGET || "1.0.10") : (process.env.VIRA_NATIVE_BASE_VERSION || "1.0.9"));
      const ids = page.getByTestId("system-build-ids").locator("span.num");
      await expect(ids).toHaveCount(3);
      await expect(ids.nth(0)).toHaveText(status.spa_build);
      await expect(ids.nth(1)).toHaveText(status.spa_build);
      await expect(ids.nth(2)).toHaveText(status.spa_build);
      await expect(page.getByTestId("system-stale-ui")).not.toBeVisible();
    }
    counters = await (await page.request.get(process.env.VIRA_NATIVE_FEED + "/counts")).json();
    expect(counters).toEqual({ delta: 1, full: 0 });
    console.log("Native in-app update:", process.env.VIRA_NATIVE_EXPECTED, "— consent, delta-only, SQLite schema/data and receipt integrity verified");
  } finally { await browser.close(); }
})().catch((error) => {
  const raw = String(error.stack || error).split(process.env.VIRA_NATIVE_PASSWORD || "__no_password__").join("[fixture password]")
    .replace(/(cookie|authorization|x-csrf-token|x-sudo-token)\s*:\s*[^\r\n]*/gi, "$1: [REDACTED]");
  const text = raw.length > 2300 ? raw.slice(0, 1100) + "\n...\n" + raw.slice(-1100) : raw;
  console.error("::error title=native browser::" + text.replaceAll("%", "%25").replaceAll("\r", "%0D").replaceAll("\n", "%0A"));
  process.exitCode = 1;
});
