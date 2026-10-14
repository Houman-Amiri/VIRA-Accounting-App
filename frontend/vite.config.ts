import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "node:path";

// Vite config — dev server proxies /api to the FastAPI backend (same-origin in prod).
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "src") },
  },
  // react-pdf stays OUT of the dep optimizer so its pdf.worker URL resolves
  // from source (react-pdf + Vite guidance). Everything else prebundles —
  // excluding e.g. react-dropzone breaks dev because its nested CJS dep
  // attr-accept has no default export in raw ESM form (blank page on boot).
  optimizeDeps: {
    exclude: ["react-pdf", "pdfjs-dist"],
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
