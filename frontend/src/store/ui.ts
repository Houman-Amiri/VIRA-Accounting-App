/** Minimal UI store (Zustand): theme + ephemeral UI state (never server data). */
import { create } from "zustand";

type Theme = "light" | "dark";

interface UiState {
  theme: Theme;
  commandPaletteOpen: boolean;
  setTheme: (t: Theme) => void;
  toggleTheme: () => void;
  setCommandPaletteOpen: (open: boolean) => void;
}

function applyTheme(t: Theme): void {
  document.documentElement.classList.toggle("dark", t === "dark");
}

export const useUiStore = create<UiState>((set, get) => ({
  theme: "light",
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
