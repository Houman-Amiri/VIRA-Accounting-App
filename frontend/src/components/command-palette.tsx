/**
 * Command palette — cmdk + react-hotkeys-hook (Cmd/Ctrl+K).
 * Navigation + actions in Persian, RTL dialog — plus the Phase 7 §1 global
 * search: queries /api/v1/search (FTS5 + LIKE fallback) and lists matching
 * entries/accounts as navigable commands.
 */
import * as React from "react";
import { useNavigate } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { Command } from "cmdk";
import { useHotkeys } from "react-hotkeys-hook";
import { useUiStore } from "@/store/ui";
import { api } from "@/api/client";
import {
  BookOpenText,
  Building2,
  FileText,
  LayoutDashboard,
  Moon,
  Receipt,
  Scale,
  Search,
  Sun,
  Tag,
  Upload,
  Wallet,
} from "lucide-react";

// Group headings are muted; interactive labels must not inherit that color,
// especially over the selected background. cmdk supplies the ARIA states.
const COMMAND_ITEM_CLASS =
  "flex cursor-pointer items-center gap-2 rounded-md px-3 py-2 text-sm text-card-foreground aria-selected:bg-accent aria-selected:text-accent-foreground aria-disabled:cursor-not-allowed aria-disabled:text-muted-foreground";

interface CommandItem {
  id: string;
  label: string;
  icon: React.ReactNode;
  action: () => void;
  keywords: string;
}

interface SearchHit {
  entity: string;
  ref_id: string;
  title: string;
  snippet: string;
  score: number;
}

const NAV_ITEMS = (opts: {
  navigate: (to: string) => void;
  toggleTheme: () => void;
  theme: string;
}): CommandItem[] => [
  {
    id: "dashboard",
    label: "داشبورد",
    icon: <LayoutDashboard />,
    keywords: "dashboard خانه",
    action: () => opts.navigate("/"),
  },
  {
    id: "journal-new",
    label: "سند جدید",
    icon: <FileText />,
    keywords: "journal سند حسابداری",
    action: () => opts.navigate("/journal/new"),
  },
  {
    id: "journal",
    label: "دفتر اسناد",
    icon: <BookOpenText />,
    keywords: "journal list اسناد",
    action: () => opts.navigate("/journal"),
  },
  {
    id: "accounts",
    label: "چارت حساب‌ها",
    icon: <Building2 />,
    keywords: "accounts chart",
    action: () => opts.navigate("/accounts"),
  },
  {
    id: "bank-import",
    label: "ورود صورت‌حساب بانکی",
    icon: <Upload />,
    keywords: "bank import csv",
    action: () => opts.navigate("/bank-import"),
  },
  {
    id: "reconcile",
    label: "تطبیق بانکی",
    icon: <Scale />,
    keywords: "reconcile تطبیق",
    action: () => opts.navigate("/reconcile"),
  },
  {
    id: "statements",
    label: "صورت‌های مالی",
    icon: <Wallet />,
    keywords: "reports صورت",
    action: () => opts.navigate("/statements"),
  },
  {
    id: "price-calc",
    label: "ماشین‌حساب قیمت‌گذاری",
    icon: <Tag />,
    keywords: "price قیمت",
    action: () => opts.navigate("/price-calc"),
  },
  {
    id: "receipts",
    label: "اسناد و رسیدها",
    icon: <Receipt />,
    keywords: "receipt رسید",
    action: () => opts.navigate("/receipts"),
  },
  {
    id: "theme",
    label: opts.theme === "light" ? "حالت تاریک" : "حالت روشن",
    icon: opts.theme === "light" ? <Moon /> : <Sun />,
    keywords: "theme تم",
    action: opts.toggleTheme,
  },
];

export function CommandPalette(): React.JSX.Element {
  const navigate = useNavigate();
  const { commandPaletteOpen, setCommandPaletteOpen, toggleTheme, theme } = useUiStore();
  const [query, setQuery] = React.useState("");

  useHotkeys(
    "mod+k",
    (e) => {
      e.preventDefault();
      setCommandPaletteOpen(!commandPaletteOpen);
    },
    { enableOnFormTags: true },
  );

  useHotkeys("esc", () => setCommandPaletteOpen(false), {
    enabled: commandPaletteOpen,
    enableOnFormTags: true,
  });

  // Phase 7 §1 — unified search (debounced by react-query).
  const trimmed = query.trim();
  const searchQuery = useQuery({
    queryKey: ["search", trimmed],
    enabled: commandPaletteOpen && trimmed.length >= 2,
    staleTime: 30_000,
    queryFn: async () => {
      const res = await api.GET("/api/v1/search", {
        params: { query: { q: trimmed, entity: "all", limit: 8 } },
      });
      return (res.data ?? { hits: [] }) as unknown as { hits: SearchHit[] };
    },
  });

  const items = NAV_ITEMS({
    navigate: (to) => navigate({ to }),
    toggleTheme,
    theme,
  });

  const filteredNav =
    trimmed.length === 0
      ? items
      : items.filter((i) => `${i.label} ${i.keywords}`.includes(trimmed));
  const hits = trimmed.length >= 2 ? (searchQuery.data?.hits ?? []) : [];

  const hitAction = (hit: SearchHit): void => {
    if (hit.entity === "account") navigate({ to: "/accounts" });
    else navigate({ to: "/journal" });
    setCommandPaletteOpen(false);
  };

  if (!commandPaletteOpen) return <></>;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/50 pt-[15vh]"
      onClick={() => setCommandPaletteOpen(false)}
      role="presentation"
    >
      <div
        className="w-full max-w-lg overflow-hidden rounded-xl border bg-card text-card-foreground shadow-2xl"
        dir="rtl"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-label="پالت فرمان‌ها"
      >
        <Command loop shouldFilter={false} label="پالت فرمان‌ها">
          <Command.Input
            value={query}
            onValueChange={setQuery}
            placeholder="جستجوی دستورات و اسناد… (Ctrl+K)"
            className="w-full border-b bg-transparent px-4 py-3 text-sm outline-none placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
          />
          <Command.List className="max-h-80 overflow-y-auto p-2">
            <Command.Empty className="p-6 text-center text-sm text-muted-foreground">
              موردی یافت نشد.
            </Command.Empty>

            {hits.length > 0 && (
              <Command.Group heading="جستجوی سراسری" className="text-xs text-muted-foreground">
                {hits.map((hit) => (
                  <Command.Item
                    key={`${hit.entity}:${hit.ref_id}`}
                    value={`${hit.entity}:${hit.ref_id}`}
                    onSelect={() => hitAction(hit)}
                    className={COMMAND_ITEM_CLASS}
                    data-testid="palette-search-hit"
                  >
                    <span className="text-muted-foreground">
                      <Search />
                    </span>
                    <span className="flex-1 truncate">{hit.title}</span>
                    <span className="text-xs text-muted-foreground">
                      {hit.entity === "account" ? "حساب" : "سند"}
                    </span>
                  </Command.Item>
                ))}
              </Command.Group>
            )}

            <Command.Group heading="ناوبری" className="text-xs text-muted-foreground">
              {filteredNav.map((item) => (
                <Command.Item
                  key={item.id}
                  value={`nav:${item.id}`}
                  onSelect={() => {
                    item.action();
                    setCommandPaletteOpen(false);
                  }}
                  className={COMMAND_ITEM_CLASS}
                >
                  <span className="text-muted-foreground">{item.icon}</span>
                  {item.label}
                </Command.Item>
              ))}
            </Command.Group>
          </Command.List>
        </Command>
      </div>
    </div>
  );
}
