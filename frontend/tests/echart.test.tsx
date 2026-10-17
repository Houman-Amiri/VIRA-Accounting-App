import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { act, cleanup, render } from "@testing-library/react";
import { EChart } from "@/components/echart";
import { useUiStore } from "@/store/ui";

const mock = vi.hoisted(() => ({
  setOption: vi.fn(),
  resize: vi.fn(),
  dispose: vi.fn(),
  observe: vi.fn(),
  disconnect: vi.fn(),
}));
vi.mock("echarts", () => ({ init: vi.fn(() => mock) }));
const option = vi.fn(() => ({ tooltip: { trigger: "axis" as const }, series: [] }));
beforeEach(() => {
  useUiStore.setState({ theme: "light" });
  vi.clearAllMocks();
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe = mock.observe;
      disconnect = mock.disconnect;
    },
  );
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it("keeps themed tooltip defaults separate from caller options, and observes container size", () => {
  const { unmount, container } = render(<EChart buildOption={option} />);
  expect(container.firstElementChild).toHaveAttribute("dir", "ltr");
  expect(mock.setOption).toHaveBeenCalledTimes(2);
  expect(mock.setOption.mock.calls[0][0].tooltip).toHaveProperty("backgroundColor");
  expect(mock.setOption.mock.calls[0][0].tooltip.textStyle.fontFamily).toContain("Vazirmatn");
  expect(mock.setOption.mock.calls[0][0].textStyle.fontFamily).toContain("Vazirmatn");
  expect(mock.setOption.mock.calls[1][0].tooltip).toEqual({ trigger: "axis" });
  expect(mock.observe).toHaveBeenCalledTimes(1);
  window.dispatchEvent(new Event("resize"));
  expect(mock.resize).toHaveBeenCalledTimes(1);
  unmount();
  expect(mock.disconnect).toHaveBeenCalledTimes(1);
  expect(mock.dispose).toHaveBeenCalledTimes(1);
  window.dispatchEvent(new Event("resize"));
  expect(mock.resize).toHaveBeenCalledTimes(1);
});

it("rebuilds the chart when theme changes and disposes the old instance", () => {
  render(<EChart buildOption={option} />);
  act(() => useUiStore.setState({ theme: "dark" }));
  expect(mock.dispose).toHaveBeenCalledTimes(1);
  expect(option).toHaveBeenCalledTimes(2);
});
