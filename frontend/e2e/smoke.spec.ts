/** E2E smoke — shell, RTL, command palette, journal form balance rules. */
import { expect, test } from "@playwright/test";

test("app shell renders in Persian RTL with sidebar nav", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  await expect(page.locator("html")).toHaveAttribute("lang", "fa");
  await expect(page.getByRole("navigation", { name: "ناوبری اصلی" })).toBeVisible();
  await expect(page.getByText("حسابداری ویرا")).toBeVisible();
});

test("command palette opens with Ctrl+K and navigates", async ({ page }) => {
  await page.goto("/");
  await page.keyboard.press("Control+k");
  await expect(page.getByRole("dialog", { name: "پالت فرمان‌ها" })).toBeVisible();
  await page.getByText("سند جدید").click();
  await expect(page).toHaveURL(/\/journal\/new/);
});

test("journal form enforces zero-balance before submit", async ({ page }) => {
  await page.goto("/journal/new");
  await page.getByTestId("entry-description").fill("سند آزمایشی");
  await page.getByTestId("split-debit-0").fill("100");
  await page.getByTestId("split-credit-1").fill("75");
  await expect(page.getByTestId("balance-error")).toBeVisible();
  await expect(page.getByTestId("submit-entry")).toBeDisabled();
  await page.getByTestId("auto-balance").click();
  await expect(page.getByTestId("balanced-badge")).toBeVisible();
  await expect(page.getByTestId("submit-entry")).toBeEnabled();
});
