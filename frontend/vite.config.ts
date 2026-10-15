import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "node:path";
import { execSync } from "node:child_process";

/**
 * Build id of the SPA bundle. Stamped into index.html («vira-build») and read
 * back by the running UI: «سیستم و عملیات» compares it with the id the
 * installation ships, so a browser stuck on a cached bundle is visible instead
 * of silently hiding every new screen (v1.0.5 incident).
 */
function buildId(): string {
  if (process.env.VIRA_BUILD_ID) return process.env.VIRA_BUILD_ID;
  const sha = process.env.GITHUB_SHA?.slice(0, 7) ?? process.env.VERCEL_GIT_COMMIT_SHA?.slice(0, 7);
  if (sha) return sha;
  try {
    return execSync("git rev-parse --short HEAD", { stdio: ["ignore", "pipe", "ignore"] })
      .toString()
      .trim();
  } catch {
    return `local-${Date.now()}`;
  }
}
const BUILD_ID = buildId();

function viraBuildStamp() {
  return {
    name: "vira-build-stamp",
    transformIndexHtml(html: string) {
      return {
        html,
        tags: [
          {
            tag: "meta",
            attrs: { name: "vira-build", content: BUILD_ID },
            injectTo: "head-prepend" as const,
          },
        ],
      };
    },
  };
}

// Vite config — dev server proxies /api to the FastAPI backend (same-origin in prod).
export default defineConfig({
  plugins: [react(), viraBuildStamp()],
  define: { __VIRA_BUILD_ID__: JSON.stringify(BUILD_ID) },
  resolve: {
    alias: { "@": path.resolve(__dirname, "src") },
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
