/** Code-based TanStack Router route tree (URL search-params are filter truth). */
import { createRoute, createRouter } from "@tanstack/react-router";
import { rootRoute } from "@/routes/root";
import { DashboardPage } from "@/routes/dashboard";
import { LoginPage } from "@/routes/login";
import { JournalListPage } from "@/routes/journal-list";
import { JournalNewPage } from "@/routes/journal-new";
import { AccountsPage } from "@/routes/accounts";
import { BankImportPage } from "@/routes/bank-import";
import { ReconcilePage } from "@/routes/reconcile";
import { StatementsPage } from "@/routes/statements";
import { PriceCalcPage } from "@/routes/price-calc";
import { ReceiptsPage } from "@/routes/receipts";
import { SettingsPage } from "@/routes/settings";
import { SystemPage } from "@/routes/system";
import { WarehousePage } from "@/routes/warehouse";
import { OrdersPage } from "@/routes/orders";
import { ProductionPage } from "@/routes/production";

export const routes = [
  rootRoute,
  createRoute({ getParentRoute: () => rootRoute, path: "/", component: DashboardPage }),
  createRoute({ getParentRoute: () => rootRoute, path: "/login", component: LoginPage }),
  createRoute({ getParentRoute: () => rootRoute, path: "/journal", component: JournalListPage }),
  createRoute({ getParentRoute: () => rootRoute, path: "/journal/new", component: JournalNewPage }),
  createRoute({ getParentRoute: () => rootRoute, path: "/accounts", component: AccountsPage }),
  createRoute({ getParentRoute: () => rootRoute, path: "/bank-import", component: BankImportPage }),
  createRoute({ getParentRoute: () => rootRoute, path: "/reconcile", component: ReconcilePage }),
  createRoute({ getParentRoute: () => rootRoute, path: "/statements", component: StatementsPage }),
  createRoute({ getParentRoute: () => rootRoute, path: "/price-calc", component: PriceCalcPage }),
  createRoute({ getParentRoute: () => rootRoute, path: "/warehouse", component: WarehousePage }),
  createRoute({ getParentRoute: () => rootRoute, path: "/orders", component: OrdersPage }),
  createRoute({ getParentRoute: () => rootRoute, path: "/production", component: ProductionPage }),
  createRoute({ getParentRoute: () => rootRoute, path: "/receipts", component: ReceiptsPage }),
  createRoute({ getParentRoute: () => rootRoute, path: "/settings", component: SettingsPage }),
  createRoute({ getParentRoute: () => rootRoute, path: "/system", component: SystemPage }),
];

export const routeTree = rootRoute.addChildren(routes.slice(1));

// Re-export for main.tsx (router instance lives there to avoid cycles).
export { createRouter };
