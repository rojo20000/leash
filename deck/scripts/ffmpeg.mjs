// System ffmpeg if it is on PATH, else the ffmpeg-static package (npm i -D ffmpeg-static).
import { execFileSync } from "node:child_process";
import { createRequire } from "node:module";

export function ffmpegPath() {
  try { execFileSync("ffmpeg", ["-version"], { stdio: "ignore" }); return "ffmpeg"; } catch { /* fall through */ }
  try { return createRequire(import.meta.url)("ffmpeg-static"); } catch { /* fall through */ }
  throw new Error("ffmpeg not found: install it, or run npm i -D ffmpeg-static");
}
