/**
 * E2E smoke — login, Persian RTL shell, command palette, journal form balance rules.
 * The e2e job seeds an owner user (VIRA_ADMIN_PASSWORD) before Playwright runs.
 */
import { expect, test, type Page } from "@playwright/test";

const USER = process.env.VIRA_E2E_USER || "owner";
const PASS = process.env.VIRA_E2E_PASSWORD || "e2e-owner-password";

// Debug channel: artifact/log hosts are unreachable from the sandbox, so on
// failure we dump the page state into the job log (surfaced via annotations).
test.afterEach(async ({ page }, testInfo) => {
  if (testInfo.status !== testInfo.expectedStatus) {
    const html = await page.content().catch(() => "<unavailable>");
    console.log("DEBUG URL:", page.url());
    console.log("DEBUG TITLE:", await page.title().catch(() => "?"));
    console.log("DEBUG HTML:", html.replace(/\s+/g, " ").slice(0, 2200));
  }
});
test.beforeEach(async ({ page }) => {
  page.on("console", (msg) => {
    if (msg.type() === "error") console.log("CONSOLE ERROR:", msg.text().slice(0, 400));
  });
  page.on("pageerror", (err) => console.log("PAGE ERROR:", String(err).slice(0, 400)));
});

async function login(page: Page): Promise<void> {
  // Deterministic: the shell is public but any background 401 redirects to
  // /login — so authenticate there first, then continue in the app.
  await page.goto("/login");
  await page.getByTestId("login-username").fill(USER);
  await page.getByTestId("login-password").fill(PASS);
  await page.getByTestId("login-submit").click();
  await page.waitForURL((url) => !url.pathname.includes("/login"), { timeout: 15_000 });
}

test("app shell renders in Persian RTL with sidebar nav", async ({ page }) => {
  await login(page);
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  await expect(page.locator("html")).toHaveAttribute("lang", "fa");
  await expect(page.getByRole("navigation", { name: "ناوبری اصلی" })).toBeVisible();
  await expect(page.getByText("حسابداری ویرا")).toBeVisible();
});

test("command palette opens with Ctrl+K and navigates", async ({ page }) => {
  await login(page);
  await page.keyboard.press("Control+k");
  const dialog = page.getByRole("dialog", { name: "پالت فرمان‌ها" });
  await expect(dialog).toBeVisible();
  await dialog.getByText("سند جدید").click();
  await expect(page).toHaveURL(/\/journal\/new/);
});

test("journal form enforces zero-balance before submit", async ({ page }) => {
  await login(page);
  await page.goto("/journal/new");
  await page.getByTestId("entry-description").fill("سند آزمایشی");
  // pick real accounts (seeded chart) — the balance rule runs only when the
  // per-split schema (account required) passes
  await page.getByTestId("split-account-0").selectOption({ index: 1 });
  await page.getByTestId("split-account-1").selectOption({ index: 2 });
  await page.getByTestId("split-debit-0").fill("100");
  await page.getByTestId("split-credit-1").fill("75");
  await expect(page.getByTestId("balance-error")).toBeVisible();
  await expect(page.getByTestId("submit-entry")).toBeDisabled();
  await page.getByTestId("auto-balance").click();
  await expect(page.getByTestId("balanced-badge")).toBeVisible();
  await expect(page.getByTestId("submit-entry")).toBeEnabled();
});
