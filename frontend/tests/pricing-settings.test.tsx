import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { api } from "@/api/client";
import { renderWithPricing, SETTINGS } from "./helpers/pricing";
import { SettingsPage } from "@/routes/settings";
import { PriceCalcPage } from "@/routes/price-calc";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("shared pricing settings", () => {
  it("saves Persian decimals through the real hook and updates the shared cache", async () => {
    const saved = { ...SETTINGS, filamentPerGram: "4000.2500", version_id: 2 };
    const put = vi
      .spyOn(api, "PUT")
      .mockResolvedValue({ data: saved, response: new Response() } as never);
    const { client } = renderWithPricing(<SettingsPage />);
    fireEvent.change(screen.getByTestId("const-filamentPerGram"), { target: { value: "۴۰۰۰٫۲۵" } });
    fireEvent.click(screen.getByRole("button", { name: "ذخیرهٔ تغییرات" }));
    await screen.findByText("ثابت‌های قیمت‌گذاری ذخیره شدند.");
    const { updated_at: _timestamp, ...values } = SETTINGS;
    expect(put).toHaveBeenCalledWith("/api/v1/settings/pricing", {
      body: { ...values, filamentPerGram: "4000.2500" },
    });
    expect(client.getQueryData(["pricing-settings"])).toEqual(saved);
  });

  it.each(["-1", "abc", "0.12345", "1000000000001"])(
    "rejects invalid constants %s before sending",
    async (value) => {
      const put = vi.spyOn(api, "PUT");
      renderWithPricing(<SettingsPage />);
      fireEvent.change(screen.getByTestId("const-filamentPerGram"), { target: { value } });
      fireEvent.click(screen.getByRole("button", { name: "ذخیرهٔ تغییرات" }));
      await screen.findByRole("alert");
      expect(put).not.toHaveBeenCalled();
    },
  );

  it("preserves the edited draft and shows the server's conflict message", async () => {
    vi.spyOn(api, "PUT").mockResolvedValue({
      error: {},
      response: new Response(
        JSON.stringify({
          code: "stale_version",
          detail: "ثابت‌ها تغییر کرده‌اند؛ دوباره بارگذاری کنید.",
        }),
        { status: 409 },
      ),
    } as never);
    renderWithPricing(<SettingsPage />);
    fireEvent.change(screen.getByTestId("const-filamentPerGram"), { target: { value: "5000" } });
    fireEvent.click(screen.getByRole("button", { name: "ذخیرهٔ تغییرات" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("دوباره بارگذاری کنید");
    expect(screen.getByTestId("const-filamentPerGram")).toHaveValue("5000");
    expect(screen.queryByText("ثابت‌های قیمت‌گذاری ذخیره شدند.")).not.toBeInTheDocument();
  });

  it("does not persist defaults before explicit save", () => {
    const put = vi.spyOn(api, "PUT");
    const { client } = renderWithPricing(<SettingsPage />, { filamentPerGram: "4000.0000" });
    fireEvent.click(screen.getByRole("button", { name: "مقادیر پیش‌فرض" }));
    expect(screen.getByTestId("const-filamentPerGram")).toHaveValue("3000");
    expect(client.getQueryData(["pricing-settings"])).toMatchObject({
      filamentPerGram: "4000.0000",
    });
    expect(put).not.toHaveBeenCalled();
  });

  it("blocks calculation rather than falling back to default prices if settings fail", async () => {
    vi.spyOn(api, "GET").mockResolvedValue({
      error: {},
      response: new Response("offline", { status: 503 }),
    } as never);
    renderWithPricing(<PriceCalcPage />, {}, false);
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("ناموفق"));
    expect(screen.queryByTestId("row-unitFinalPrice")).not.toBeInTheDocument();
  });
});
