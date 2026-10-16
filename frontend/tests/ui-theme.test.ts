import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

beforeEach(() => {
  vi.resetModules();
  localStorage.clear();
  document.documentElement.className = "rtl-shell";
});
afterEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
  document.documentElement.className = "";
});

async function store() {
  return (await import("@/store/ui")).useUiStore;
}

describe("theme preference and native-control scheme", () => {
  it("defaults to light without changing other root classes", async () => {
    const ui = await store();
    expect(ui.getState().theme).toBe("light");
    expect(document.documentElement).toHaveClass("rtl-shell");
    expect(document.documentElement).not.toHaveClass("dark");
  });
  it("restores dark before rendering a freshly loaded page", async () => {
    localStorage.setItem("vira-theme", "dark");
    const ui = await store();
    expect(ui.getState().theme).toBe("dark");
    expect(document.documentElement).toHaveClass("dark", "rtl-shell");
    expect(ui.getState().commandPaletteOpen).toBe(false);
  });
  it("persists keyboard/UI theme changes, not palette visibility", async () => {
    const ui = await store();
    ui.getState().toggleTheme();
    ui.getState().setCommandPaletteOpen(true);
    expect(localStorage.getItem("vira-theme")).toBe("dark");
    vi.resetModules();
    const reloaded = await store();
    expect(reloaded.getState().theme).toBe("dark");
    expect(reloaded.getState().commandPaletteOpen).toBe(false);
    expect(localStorage.length).toBe(1);
  });
  it("can switch back to light and restore it on reload", async () => {
    localStorage.setItem("vira-theme", "dark");
    const ui = await store();
    ui.getState().setTheme("light");
    expect(document.documentElement).not.toHaveClass("dark");
    expect(localStorage.getItem("vira-theme")).toBe("light");
    vi.resetModules();
    expect((await store()).getState().theme).toBe("light");
  });
  it("ignores invalid saved values", async () => {
    localStorage.setItem("vira-theme", "not-a-theme");
    expect((await store()).getState().theme).toBe("light");
    expect(document.documentElement).not.toHaveClass("dark");
  });
  it("survives blocked storage on startup", async () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("storage blocked");
    });
    expect((await store()).getState().theme).toBe("light");
  });
  it("still updates DOM/store when saving fails", async () => {
    const ui = await store();
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("quota exceeded");
    });
    expect(() => ui.getState().toggleTheme()).not.toThrow();
    expect(ui.getState().theme).toBe("dark");
    expect(document.documentElement).toHaveClass("dark");
  });
});
