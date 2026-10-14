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
  createRoute({ getParentRoute: () => rootRoute, path: "/receipts", component: ReceiptsPage }),
];

export const routeTree = rootRoute.addChildren(routes.slice(1));

// Re-export for main.tsx (router instance lives there to avoid cycles).
export { createRouter };
