import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider, createRouter } from "@tanstack/react-router";
import { routeTree } from "./routeTree";
import "@fontsource-variable/vazirmatn";
import "@fontsource/jetbrains-mono";
import "./index.css";
import { initAnalytics } from "@/lib/analytics";
import "@/lib/i18n";

const router = createRouter({ routeTree, defaultPreload: "intent" });

// Privacy-first Umami — injected only when VITE_UMAMI_* are configured (Phase 7 §5).
initAnalytics();

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 30_000, retry: 1, refetchOnWindowFocus: false },
    mutations: { retry: 0 },
  },
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </React.StrictMode>,
);
