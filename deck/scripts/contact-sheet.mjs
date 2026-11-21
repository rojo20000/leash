// Tiles showcase/steps/*.png into showcase/contact-sheet.png (4 columns, 480 px wide each).
import { execFileSync } from "node:child_process";
import { readdirSync } from "node:fs";
import { ffmpegPath } from "./ffmpeg.mjs";

const files = readdirSync("showcase/steps").filter((f) => f.endsWith(".png")).sort();
const rows = Math.ceil(files.length / 4);
const inputs = files.flatMap((f) => ["-i", `showcase/steps/${f}`]);
const scaled = files.map((_, i) => `[${i}:v]scale=480:270[s${i}]`).join(";");
const layout = files.map((_, i) => `${(i % 4) * 480}_${Math.floor(i / 4) * 270}`).join("|");
const stack = files.map((_, i) => `[s${i}]`).join("");
execFileSync(ffmpegPath(), ["-v", "error", "-y", ...inputs, "-filter_complex",
  `${scaled};${stack}xstack=inputs=${files.length}:layout=${layout}:fill=0x07080A[out]`, "-map", "[out]",
  "-frames:v", "1", "-update", "1", "showcase/contact-sheet.png"]);
console.log(`contact sheet: ${files.length} steps, ${rows} rows`);
