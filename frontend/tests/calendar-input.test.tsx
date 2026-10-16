import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { CalendarInput } from "@/components/calendar-input";
import { CalendarContext } from "@/lib/calendar-settings";
import type { Calendar } from "@/lib/calendar";
afterEach(cleanup);
function Form() {
  const [value, setValue] = useState("2026-10-17");
  const [calendar, setCalendar] = useState<Calendar>("jalali");
  return (
    <CalendarContext.Provider value={{ calendar, ready: true, error: null }}>
      <CalendarInput id="civil" label="تاریخ" value={value} onChange={setValue} />
      <output data-testid="iso">{value}</output>
      <button onClick={() => setCalendar((c) => (c === "jalali" ? "gregorian" : "jalali"))}>
        switch
      </button>
    </CalendarContext.Provider>
  );
}
it("accepts Persian input, preserves canonical day when the calendar changes", () => {
  render(<Form />);
  expect(screen.getByTestId("civil")).toHaveValue("1405/07/25");
  fireEvent.change(screen.getByTestId("civil"), { target: { value: "۱۴۰۴/۰۱/۰۱" } });
  expect(screen.getByTestId("iso")).toHaveTextContent("2025-03-21");
  fireEvent.click(screen.getByText("switch"));
  expect(screen.getByTestId("civil")).toHaveValue("2025/03/21");
  expect(screen.getByTestId("iso")).toHaveTextContent("2025-03-21");
  fireEvent.click(screen.getByText("switch"));
  expect(screen.getByTestId("civil")).toHaveValue("1404/01/01");
});
it("retains invalid raw input but clears canonical submission value", () => {
  render(<Form />);
  fireEvent.change(screen.getByTestId("civil"), { target: { value: "۱۴۰۴/۱۲/۳۰" } });
  expect(screen.getByTestId("civil")).toHaveValue("۱۴۰۴/۱۲/۳۰");
  expect(screen.getByRole("alert")).toBeVisible();
  expect(screen.getByTestId("iso")).toBeEmptyDOMElement();
});
it("does not fall back to a writable date when server policy is unavailable", () => {
  const change = vi.fn();
  render(
    <CalendarContext.Provider value={{ calendar: "jalali", ready: false, error: "خطای دریافت" }}>
      <CalendarInput id="civil" label="تاریخ" value="2026-10-17" onChange={change} />
    </CalendarContext.Provider>,
  );
  expect(screen.getByTestId("civil")).toBeDisabled();
  expect(screen.getByRole("alert")).toHaveTextContent("خطای دریافت");
  expect(change).not.toHaveBeenCalled();
});
