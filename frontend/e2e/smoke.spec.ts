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

test("pricing reproduces the original Excel cells for single and multiple quantities", async ({
  page,
}) => {
  await login(page);
  await page.goto("/price-calc");
  // Reuse this authenticated journey: a sixth login hits the real auth rate limit.
  const rows = [
    ["productionTotal", "rgb(220, 252, 231)", "rgba(20, 83, 45, 0.4)"],
    ["unitSalePrice", "rgb(219, 234, 254)", "rgba(30, 58, 138, 0.4)"],
    ["unitFinalPrice", "rgb(254, 226, 226)", "rgba(127, 29, 29, 0.4)"],
  ];
  for (const dark of [false, true]) {
    await page.evaluate((value) => document.documentElement.classList.toggle("dark", value), dark);
    for (const [key, lightColor, darkColor] of rows) {
      await expect(page.getByTestId(`row-${key}`)).toHaveCSS(
        "background-color",
        dark ? darkColor : lightColor,
      );
    }
  }
  const final = page.getByTestId("row-unitFinalPrice");
  await expect(final).toContainText("۲٬۷۶۰٬۷۴۸.۵");
  await expect(final).toContainText("۲٬۷۸۰٬۷۴۸.۵");
  await expect(final).toContainText("E35");
  await page.getByTestId("input-qty").fill("۱۰");
  await expect(final).toContainText("۲۹۱٬۱۹۴.۸۵");
  await expect(final).toContainText("۳۱۱٬۱۹۴.۸۵");
  await expect(page.getByTestId("sheet-policy")).toHaveCount(0);
  await expect(page.getByText(/اکسل|xlsx/)).toHaveCount(0);
  await page.getByRole("link", { name: "تغییر ثابت‌ها در تنظیمات" }).click();
  await page.getByTestId("const-filamentPerGram").fill("۹۰۰۰");
  await page.getByRole("button", { name: "ذخیرهٔ تغییرات" }).click();
  await expect(page.getByText("ثابت‌های قیمت‌گذاری ذخیره شدند.")).toBeVisible();
  try {
    await page.reload();
    await expect(page.getByTestId("const-filamentPerGram")).toHaveValue("9000.0000");
    await page.goto("/price-calc");
    await expect(page.getByTestId("row-productionTotal")).toContainText("۲٬۲۷۴٬۰۰۰");
    await page.getByTestId("input-qty").fill("۱۰");
    await page.getByRole("button", { name: "بازنشانی ورودی‌ها" }).click();
    await expect(page.getByTestId("input-qty")).toHaveValue("1");
    await expect(page.getByTestId("row-productionTotal")).toContainText("۲٬۲۷۴٬۰۰۰");
    // A different pricing consumer must use the saved values, too.
    await page.goto("/orders");
    await page.getByTestId("order-channel").selectOption("marketplace");
    const line = page.getByTestId("line-0");
    await line.getByPlaceholder("وزن (گرم)").fill("240");
    await line.getByPlaceholder("زمان (ساعت)").fill("10");
    await line.getByRole("button", { name: "محاسبهٔ قیمت" }).click();
    await expect(line.getByPlaceholder("قیمت واحد")).toHaveValue("7239508.5000");
  } finally {
    await page.goto("/settings");
    await page.getByTestId("const-filamentPerGram").fill("3000");
    await page.getByRole("button", { name: "ذخیرهٔ تغییرات" }).click();
    await expect(page.getByText("ثابت‌های قیمت‌گذاری ذخیره شدند.")).toBeVisible();
  }
  await page.goto("/price-calc");
  await expect(page.getByTestId("row-unitFinalPrice")).toContainText("۲٬۷۸۰٬۷۴۸.۵");
});

// Only the update HTTP boundary is simulated; login, sudo, hooks and dialog are real.
test("update dialog leaves idle/zero bytes and reaches the verified apply step", async ({
  page,
}) => {
  const baseStatus = {
    state: "idle",
    total_bytes: 100,
    downloaded_bytes: 0,
    verified: false,
    staged_path: "",
    log_path: "updates/update.log",
    error_fa: null,
    machine_state: "idle",
  };
  let started = false;
  let polls = 0;
  await page.route("**/api/v1/system/check-updates", (route) =>
    route.fulfill({
      json: {
        current: "1.0.7",
        latest: "1.0.8",
        checked: true,
        update_available: true,
        manual_required: false,
        notes_fa: "آزمون دریافت بسته",
        choice: {
          kind: "delta",
          total_bytes: 100,
          packages: [
            {
              url: "https://github.com/x/y/d.zip",
              sha256: "ab".repeat(32),
              size: 100,
              from_version: "1.0.7",
            },
          ],
        },
      },
    }),
  );
  await page.route("**/api/v1/system/update/status", (route) => {
    if (!started) return route.fulfill({ json: baseStatus });
    polls++;
    return route.fulfill({
      json: {
        ...baseStatus,
        state: polls === 1 ? "downloading" : "staged",
        downloaded_bytes: polls === 1 ? 10 : 100,
        verified: polls > 1,
        staged_path: polls > 1 ? "updates/payload" : "",
      },
    });
  });
  await page.route("**/api/v1/system/update/download", (route) => {
    started = true;
    return route.fulfill({ json: { ...baseStatus, state: "downloading" } });
  });
  await login(page);
  await page.goto("/system");
  const sudo = page.locator("dialog:modal");
  await sudo.locator('input[type="password"]').fill(PASS);
  await sudo.locator('button[type="submit"]').click();
  await page.getByTestId("system-check-updates").click();
  await page.getByTestId("update-accept").click();
  await expect(page.getByTestId("update-progress-text")).toContainText("10 B");
  await expect(page.getByTestId("update-apply")).toBeVisible();
  expect(polls).toBeGreaterThanOrEqual(2);
});
