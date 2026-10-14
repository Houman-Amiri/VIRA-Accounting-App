import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "node:path";

// Vite config — dev server proxies /api to the FastAPI backend (same-origin in prod).
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "src") },
  },
  // Phase 7 §2 — heavy/worker packages stay out of the dep optimizer so their
  // web workers (react-pdf) and ESM entry graphs resolve natively.
  optimizeDeps: {
    exclude: [
      "react-dropzone",
      "react-pdf",
      "react-zoom-pan-pinch",
      "echarts",
      "@tiptap/react",
      "@tiptap/starter-kit",
    ],
  },
  server: {
    port: 5173,
    host: "0.0.0.0",
    allowedHosts: true,
    proxy: {
      "/api": {
        target: process.env.VIRA_API_URL || "http://127.0.0.1:8787",
        changeOrigin: false,
      },
    },
  },
  preview: {
    port: 5173,
    host: "0.0.0.0",
    allowedHosts: true,
  },
  build: {
    outDir: "dist",
    sourcemap: true,
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["tests/setup.ts"],
    include: ["tests/**/*.test.{ts,tsx}"],
  },
});
