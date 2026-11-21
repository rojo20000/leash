import { defineConfig } from "@playwright/test";

// Always the built deck (vite build, then vite preview), never the dev server.
export default defineConfig({
  testDir: "tests",
  globalSetup: "./tests/global-setup.ts",
  timeout: 120_000,
  workers: 1,
  reporter: [["list"], ["json", { outputFile: "showcase/test-results.json" }]],
  // PW_CHANNEL=msedge (or chrome) uses an installed browser, e.g. for the headed FPS check
  use: { baseURL: "http://localhost:4173", viewport: { width: 1920, height: 1080 }, headless: true, channel: process.env.PW_CHANNEL || undefined },
  // vite runs directly (no npm or shell wrapper), so Playwright can stop it; on Windows a wrapped
  // `npm run preview` left an orphaned server holding port 4173 after every run.
  webServer: { command: "node node_modules/vite/bin/vite.js preview --port 4173 --strictPort", url: "http://localhost:4173", reuseExistingServer: false, timeout: 120_000 },
});
