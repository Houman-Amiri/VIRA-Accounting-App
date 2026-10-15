/** Root route: RTL app shell — sidebar nav, command palette, theme toggle. */
import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { Link, Outlet, createRootRoute, useNavigate } from "@tanstack/react-router";
import { CommandPalette } from "@/components/command-palette";
import { SudoProvider } from "@/components/sudo-dialog";
import { api, getCsrfToken, onUnauthorized } from "@/api/client";
import { snapshotDrafts } from "@/lib/drafts";
import { useUiStore } from "@/store/ui";
import { useUpdateCheck } from "@/lib/update";
import { Moon, Sun, Command } from "lucide-react";
import {
  BookOpenText,
  Building2,
  Boxes,
  Factory,
  FileText,
  LayoutDashboard,
  Receipt,
  Scale,
  Settings2,
  ShoppingCart,
  Tag,
  Upload,
  Wallet,
} from "lucide-react";

const NAV = [
  { to: "/", labelKey: "nav.dashboard", icon: LayoutDashboard },
  { to: "/journal/new", labelKey: "nav.journalNew", icon: FileText },
  { to: "/journal", labelKey: "nav.journal", icon: BookOpenText },
  { to: "/accounts", labelKey: "nav.accounts", icon: Building2 },
  { to: "/bank-import", labelKey: "nav.bankImport", icon: Upload },
  { to: "/reconcile", labelKey: "nav.reconcile", icon: Scale },
  { to: "/statements", labelKey: "nav.statements", icon: Wallet },
  { to: "/warehouse", labelKey: "nav.warehouse", icon: Boxes },
  { to: "/orders", labelKey: "nav.orders", icon: ShoppingCart },
  { to: "/production", labelKey: "nav.production", icon: Factory },
  { to: "/price-calc", labelKey: "nav.priceCalc", icon: Tag },
  { to: "/receipts", labelKey: "nav.receipts", icon: Receipt },
  { to: "/settings", labelKey: "nav.settings", icon: Settings2 },
  { to: "/system", labelKey: "nav.system", icon: Settings2 },
] as const;

function RootComponent() {
  const { t } = useTranslation();
  // Phase 8 §4 — non-blocking startup update check; subtle badge only.
  const updateCheck = useUpdateCheck();
  const updateAvailable = updateCheck.data?.update_available === true;
  const { theme, toggleTheme, setCommandPaletteOpen } = useUiStore();
  const navigate = useNavigate();
  // Phase 5 §4: 401 → snapshot unsaved form drafts, redirect to /login.
  useEffect(() => {
    onUnauthorized(() => {
      snapshotDrafts();
      void navigate({ to: "/login" });
    });
    // Silent session refresh on app start (Phase 5 §2) — re-issues the
    // HttpOnly cookie while the session is still valid; fails silently.
    if (getCsrfToken()) {
      void api.POST("/api/v1/auth/refresh", {}).catch(() => undefined);
    }
  }, [navigate]);
  return (
    <SudoProvider>
      <div className="flex min-h-screen">
        <aside className="flex w-56 shrink-0 flex-col gap-1 border-l bg-card/60 p-3">
          <div className="mb-4 flex items-center gap-2 px-2">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary text-primary-foreground font-bold">
              و
            </div>
            <div>
              <div className="font-bold leading-tight">{t("app.title")}</div>
              <div className="text-[10px] text-muted-foreground">{t("app.subtitle")}</div>
            </div>
          </div>
          <nav className="flex flex-col gap-1" aria-label={t("nav.primary")}>
            {NAV.map((item) => (
              <Link
                key={item.to}
                to={item.to}
                activeOptions={{ exact: item.to === "/" }}
                className="flex items-center gap-2 rounded-md px-3 py-2 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
                activeProps={{ className: "bg-accent text-accent-foreground font-medium" }}
              >
                <item.icon className="h-4 w-4" />
                <span className="flex-1 truncate">
                  {t(item.labelKey)}
                  {item.to === "/system" && updateAvailable && (
                    <span
                      className="ms-2 rounded-full bg-primary px-1.5 py-0.5 text-[10px] text-primary-foreground"
                      data-testid="update-badge"
                      title={t("update.startupBadge")}
                    >
                      !
                    </span>
                  )}
                </span>
              </Link>
            ))}
          </nav>
          <div className="mt-auto flex flex-col gap-1">
            <button
              type="button"
              onClick={() => setCommandPaletteOpen(true)}
              className="flex items-center gap-2 rounded-md border px-3 py-2 text-xs text-muted-foreground hover:bg-accent"
            >
              <Command className="h-3.5 w-3.5" />
              {t("palette.open")}
              <kbd className="num ms-auto rounded bg-muted px-1.5 py-0.5 text-[10px]">
                {t("palette.hint")}
              </kbd>
            </button>
            <button
              type="button"
              onClick={toggleTheme}
              className="flex items-center gap-2 rounded-md px-3 py-2 text-xs text-muted-foreground hover:bg-accent"
            >
              {theme === "light" ? (
                <Moon className="h-3.5 w-3.5" />
              ) : (
                <Sun className="h-3.5 w-3.5" />
              )}
              {theme === "light" ? t("theme.dark") : t("theme.light")}
            </button>
          </div>
        </aside>
        <main className="flex-1 overflow-x-hidden p-6">
          <Outlet />
        </main>
        <CommandPalette />
      </div>
    </SudoProvider>
  );
}

export const rootRoute = createRootRoute({ component: RootComponent });
