import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { api } from "@/api/client";
import { renderWithPricing } from "./helpers/pricing";
import { CalendarProvider, useCalendar } from "@/lib/calendar-settings";
import { CalendarSettingsCard } from "@/components/calendar-settings";
import { faDate } from "@/lib/fa";
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
const initial = {
  calendar: "jalali",
  version_id: 0,
  timezone: "Asia/Tehran",
  scope: "installation",
} as const;
function ReadDate() {
  const { calendar, ready } = useCalendar();
  return (
    <output data-testid="date">{ready ? faDate("2026-10-17", calendar) : "unavailable"}</output>
  );
}
function App() {
  return (
    <CalendarProvider enabled>
      <CalendarSettingsCard />
      <ReadDate />
    </CalendarProvider>
  );
}
it("saves a versioned server preference and reactively updates formatters, without changing civil date", async () => {
  const saved = { ...initial, calendar: "gregorian", version_id: 1 };
  const put = vi
    .spyOn(api, "PUT")
    .mockResolvedValue({ data: saved, response: new Response() } as never);
  const { client } = renderWithPricing(<App />);
  expect(screen.getByTestId("date")).toHaveTextContent("۱۴۰۵/۰۷/۲۵");
  fireEvent.change(screen.getByTestId("calendar-choice"), { target: { value: "gregorian" } });
  fireEvent.click(screen.getByTestId("save-calendar"));
  await screen.findByText("تقویم ذخیره شد.");
  expect(put).toHaveBeenCalledWith("/api/v1/settings/calendar", {
    body: { calendar: "gregorian", version_id: 0 },
  });
  expect(client.getQueryData(["calendar-settings"])).toEqual(saved);
  expect(screen.getByTestId("date")).toHaveTextContent("۲۰۲۶/۱۰/۱۷");
});
it("does not overwrite settings on a 409 conflict", async () => {
  const problem = {
    title: "Conflict",
    status: 409,
    detail: "تنظیم تغییر کرده است",
    code: "stale_version",
  };
  vi.spyOn(api, "PUT").mockResolvedValue({
    error: problem,
    response: new Response(JSON.stringify(problem), {
      status: 409,
      headers: { "Content-Type": "application/problem+json" },
    }),
  } as never);
  const { client } = renderWithPricing(<App />);
  fireEvent.change(screen.getByTestId("calendar-choice"), { target: { value: "gregorian" } });
  fireEvent.click(screen.getByTestId("save-calendar"));
  await screen.findByRole("alert");
  expect(client.getQueryData(["calendar-settings"])).toEqual(initial);
  expect(screen.getByTestId("date")).toHaveTextContent("۱۴۰۵/۰۷/۲۵");
});
it("retrieves persisted Gregorian state, with no localStorage preference", async () => {
  vi.spyOn(api, "GET").mockResolvedValue({
    data: { ...initial, calendar: "gregorian", version_id: 3 },
    response: new Response(),
  } as never);
  const { client } = renderWithPricing(<App />);
  await client.invalidateQueries({ queryKey: ["calendar-settings"] });
  await waitFor(() => expect(screen.getByTestId("date")).toHaveTextContent("۲۰۲۶/۱۰/۱۷"));
});
it("fails closed when a server response is malformed", async () => {
  vi.spyOn(api, "GET").mockResolvedValue({
    data: { calendar: "gregorian" },
    response: new Response(),
  } as never);
  const { client } = renderWithPricing(<App />);
  await client.invalidateQueries({ queryKey: ["calendar-settings"] });
  await waitFor(() => expect(screen.getByTestId("date")).toHaveTextContent("unavailable"));
});
