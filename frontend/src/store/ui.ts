/** UI state: persisted theme preference + ephemeral palette state; never server data. */
import { create } from "zustand";

type Theme = "light" | "dark";
const THEME_KEY = "vira-theme";

interface UiState {
  theme: Theme;
  commandPaletteOpen: boolean;
  setTheme: (t: Theme) => void;
  toggleTheme: () => void;
  setCommandPaletteOpen: (open: boolean) => void;
}

function initialTheme(): Theme {
  try {
    return localStorage.getItem(THEME_KEY) === "dark" ? "dark" : "light";
  } catch {
    return "light";
  }
}

function applyTheme(t: Theme): void {
  if (typeof document !== "undefined") {
    document.documentElement.classList.toggle("dark", t === "dark");
  }
  try {
    localStorage.setItem(THEME_KEY, t);
  } catch {
    // Blocked/full storage must never prevent an in-session theme change.
  }
}

const theme = initialTheme();
// Apply the saved preference before rendering controls on a fresh navigation.
if (typeof document !== "undefined")
  document.documentElement.classList.toggle("dark", theme === "dark");

export const useUiStore = create<UiState>((set, get) => ({
  theme,
  commandPaletteOpen: false,
  setTheme: (t) => {
    applyTheme(t);
    set({ theme: t });
  },
  toggleTheme: () => {
    const next: Theme = get().theme === "light" ? "dark" : "light";
    applyTheme(next);
    set({ theme: next });
  },
  setCommandPaletteOpen: (open) => set({ commandPaletteOpen: open }),
}));
