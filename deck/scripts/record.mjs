// npm run record: plays the built deck with ?autoplay=1 in headless Chromium, records it, and writes
// showcase/leash-fallback.mp4 (H.264). Draft only: Playwright records at a low frame rate; re-record the
// final fallback with OBS or QuickTime at 1080p60 on the presenting laptop.
import { chromium } from "@playwright/test";
import { spawn, execFileSync } from "node:child_process";
import { mkdirSync, mkdtempSync, readdirSync, rmSync, statSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { ffmpegPath } from "./ffmpeg.mjs";

const DECK = resolve(import.meta.dirname, "..");
const OUT = join(DECK, "showcase/leash-fallback.mp4");
const PORT = 4174;
const DIST = "dist-record"; // own build folder, so a running test preview of dist/ is never disturbed
const sh = process.platform === "win32";

execFileSync("npx", ["vite", "build", "--outDir", DIST, "--emptyOutDir"], { cwd: DECK, stdio: "inherit", shell: sh });
const server = spawn("npx", ["vite", "preview", "--outDir", DIST, "--port", String(PORT), "--strictPort"], { cwd: DECK, stdio: "ignore", shell: sh });
const stop = () => {
  try { execFileSync("taskkill", ["/PID", String(server.pid), "/T", "/F"], { stdio: "ignore" }); } catch { server.kill(); }
};
process.on("exit", stop);

const url = `http://localhost:${PORT}/?autoplay=1`;
for (let i = 0; ; i++) {
  try { if ((await fetch(url)).ok) break; } catch { /* not up yet */ }
  if (i > 120) throw new Error("vite preview did not start on port " + PORT);
  await new Promise((r) => setTimeout(r, 500));
}

const vdir = mkdtempSync(join(tmpdir(), "leash-record-"));
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1920, height: 1080 }, recordVideo: { dir: vdir, size: { width: 1920, height: 1080 } } });
const page = await ctx.newPage();
const t0 = Date.now();
await page.goto(url);
await page.waitForFunction(() => window.__deck?.ready);
const loadSec = (Date.now() - t0) / 1000;
await page.waitForFunction(() => window.__deck.done === true, null, { timeout: 300_000, polling: 1000 });
await page.waitForTimeout(2000);
await ctx.close();
await browser.close();
stop();

const webm = join(vdir, readdirSync(vdir).find((f) => f.endsWith(".webm")));
mkdirSync(join(DECK, "showcase"), { recursive: true });
execFileSync(ffmpegPath(), ["-v", "error", "-y", "-ss", Math.max(0, loadSec - 0.2).toFixed(2), "-i", webm, "-an",
  "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-movflags", "+faststart", OUT]);
rmSync(vdir, { recursive: true, force: true });

const probe = (() => { try { execFileSync(ffmpegPath(), ["-i", OUT], { stdio: "pipe" }); } catch (e) { return String(e.stderr); } return ""; })();
const duration = /Duration: ([\d:.]+)/.exec(probe)?.[1] ?? "unknown";
console.log(`recorded ${OUT}\nduration ${duration}, size ${(statSync(OUT).size / 1e6).toFixed(1)} MB (draft: re-record with OBS/QuickTime at 1080p60)`);
process.exit(0);
