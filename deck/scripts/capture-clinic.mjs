// Capture Clinic Assistant for Scene 6: a 2x screenshot, the chat-input box, the Similar cases panel and a
// short screen recording of one rehearsed query. Runs a throwaway copy of ../leash/clinic-assistant in the OS
// temp folder on port 8653, so the repo copy (and its data/) is never touched. Synthetic patients only.
//   node scripts/capture-clinic.mjs            uses a local Ollama model if one is installed, else MOCK_LLM=1
//   CA_MOCK=1 node scripts/capture-clinic.mjs  forces the stand-in model
import { chromium } from "@playwright/test";
import { spawn, execFileSync } from "node:child_process";
import { cpSync, existsSync, mkdirSync, readFileSync, rmSync, writeFileSync, readdirSync } from "node:fs";
import { randomBytes } from "node:crypto";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { ffmpegPath } from "./ffmpeg.mjs";

const DECK = resolve(import.meta.dirname, "..");
// deck/ inside the Leash repo, or a leash-deck/ folder next to it
const SRC = [resolve(DECK, "../clinic-assistant"), resolve(DECK, "../leash/clinic-assistant")].find((p) => existsSync(p));
if (!SRC) throw new Error("Clinic Assistant not found next to the deck");
// System Python on purpose: Clinic Assistant is stdlib-only, and with Presidio installed (as in the Leash venv)
// its output check flags ordinary answer text as identifiers and withholds every answer.
const PY = process.env.CA_PYTHON || "py";
const WORK = join(tmpdir(), "leash-clinic-capture");
const OUT = join(DECK, "public/clinic");
const PORT = Number(process.env.CA_PORT) || 8653; // not 8642 (the real app) and not 8643 (used by another tool here)
const QUERY = process.env.CA_QUERY || "Any medication interactions or allergy conflicts?";
const MODEL = "qwen3.5:9b"; // stand-in for MedGemma, which is not installed on this machine

if (!WORK.endsWith("leash-clinic-capture")) throw new Error("refusing to clear " + WORK);
rmSync(WORK, { recursive: true, force: true });
cpSync(SRC, WORK, { recursive: true, filter: (p) => !/[\\/]data[\\/](users|audit|outbox|reviews|patients)/.test(p) });

const policyPath = join(WORK, "config/policy.json");
const policy = JSON.parse(readFileSync(policyPath, "utf8"));
policy.server.port = PORT;
let mock = process.env.CA_MOCK === "1";
if (!mock) {
  try { mock = !execFileSync("ollama", ["list"], { encoding: "utf8" }).includes(MODEL); } catch { mock = true; }
}
if (!mock) {
  policy.model.chat_model = MODEL;
  // Qwen 3.5 thinks by default and would spend the token budget on it; this copy turns thinking off.
  const llm = join(WORK, "app/llm.py");
  writeFileSync(llm, readFileSync(llm, "utf8").replace('"stream": False,', '"stream": False, "think": False,'));
}
writeFileSync(policyPath, JSON.stringify(policy, null, 2));

const password = randomBytes(18).toString("base64url"); // throwaway, lives only in this process and the temp copy
execFileSync(PY, ["-c", "import os,json;from app.users import UserStore;p=json.load(open('config/policy.json'));"
  + "UserStore(__import__('pathlib').Path('data/users.json'),p['roles']).add('dr_lee',os.environ['CA_PW'],'clinician')"],
  { cwd: WORK, env: { ...process.env, CA_PW: password } });

const server = spawn(PY, ["run.py"], { cwd: WORK, env: { ...process.env, MOCK_LLM: mock ? "1" : "0" }, stdio: "inherit" });
const base = `http://127.0.0.1:${PORT}`;
const stop = () => { try { execFileSync("taskkill", ["/PID", String(server.pid), "/T", "/F"], { stdio: "ignore" }); } catch { server.kill(); } };
process.on("exit", stop);

for (let i = 0; ; i++) {
  try { if ((await fetch(base + "/api/version")).ok) break; } catch { /* not up yet */ }
  if (i > 120) throw new Error("Clinic Assistant did not start");
  await new Promise((r) => setTimeout(r, 500));
}

async function signIn(page) {
  await page.goto(base);
  await page.fill("#login-user", "dr_lee");
  await page.fill("#login-pass", password);
  await page.press("#login-pass", "Enter");
  await page.waitForSelector("#app-view:not([hidden])");
}
async function openInrPatient(page) {
  const id = await page.evaluate(async () => {
    const list = await (await fetch("/api/patients")).json();
    const hit = list.find((p) => JSON.stringify(p).includes("INR 4.3"));
    return (hit || list[0]).id;
  });
  await page.evaluate(() => document.querySelector('[data-tab="patients"]')?.click());
  await page.locator("#patient-items button").filter({ hasText: /./ }).first().waitFor();
  // app.js keeps openPatient module-local, so click the list entry for this id
  await page.evaluate((pid) => {
    const b = [...document.querySelectorAll("#patient-items button")].find((x) => x.outerHTML.includes(pid));
    (b || document.querySelector("#patient-items button")).click();
  }, id);
  await page.waitForSelector("#patient-view:not([hidden])");
  await page.waitForSelector("#pt-similar li");
  return id;
}

mkdirSync(OUT, { recursive: true });
const browser = await chromium.launch();
const VIEW = { width: 1600, height: 900 };

// 1. Still: 2x screenshot with the patient open, plus where the chat input and Similar cases sit.
{
  const ctx = await browser.newContext({ viewport: VIEW, deviceScaleFactor: 2 });
  const page = await ctx.newPage();
  await signIn(page);
  const id = await openInrPatient(page);
  if (!mock) { // warm the model so the recorded answer is quick
    await page.fill("#pt-chat-input", "Summarise this patient in one line.");
    await page.press("#pt-chat-input", "Enter");
    await page.waitForFunction(() => { const t = document.querySelector("#pt-chat-log")?.textContent || ""; return t.length > 80 && !/can take a minute/i.test(t); }, null, { timeout: 180000 });
    await page.click("#pt-chat-clear").catch(() => {});
    await page.evaluate(() => { document.querySelector("#pt-chat-log").replaceChildren(); });
  }
  await page.locator("#pt-chat-input").scrollIntoViewIfNeeded();
  await page.waitForTimeout(400);
  const response = await page.locator("#pt-chat-log").boundingBox(); // the panel where the answer generates
  await page.screenshot({ path: join(OUT, "ui@2x.png") });
  const rect = (sel) => page.locator(sel).first().boundingBox();
  const similar = await page.$$eval("#pt-similar li", (ls) => ls.map((l) => ({
    name: l.querySelector("strong")?.textContent, match: l.querySelector(".match")?.textContent,
    why: l.querySelector(".muted")?.textContent })));
  const status = await page.evaluate(async () => {
    const a = await (await fetch("/api/audit")).json().catch(() => null);
    return a && (a.vectors || a.vector_status || null);
  });
  writeFileSync(join(OUT, "ui.json"), JSON.stringify({ viewport: VIEW, patient: id, query: QUERY, model: mock ? "stand-in (MOCK_LLM=1)" : MODEL,
    input: await rect("#pt-chat-input"), response, similarBox: await rect("#pt-similar"), similar, vectors: status }, null, 2));
  await ctx.close();
}

// 2. Recording: type the rehearsed query and wait for the answer.
// Back-to-back 2x JPEG screenshots of the normal 1600x900 layout (3200x1800 each), stitched by timestamp, so the
// deck can zoom into the recording and stay sharp. (Playwright's recordVideo at 2x fills only a quarter of the
// frame, Chrome's screencast stays at 1x, and CSS zoom breaks the app's viewport-height layout.)
{
  const fdir = join(WORK, "frames");
  mkdirSync(fdir, { recursive: true });
  const ctx = await browser.newContext({ viewport: VIEW, deviceScaleFactor: 2 });
  const page = await ctx.newPage();
  await signIn(page);
  await openInrPatient(page);
  await page.locator("#pt-chat-input").scrollIntoViewIfNeeded();
  await page.waitForTimeout(600);
  const frames = [];
  let rec = true;
  const grab = (async () => {
    while (rec) { const t = Date.now() / 1000; frames.push({ data: await page.screenshot({ type: "jpeg", quality: 90 }), t }); }
  })();
  await page.waitForTimeout(500);
  await page.click("#pt-chat-input");
  await page.type("#pt-chat-input", QUERY, { delay: 25 }); // quick: the deck holds a zoom on the input while it types
  await page.waitForTimeout(400);
  const before = await page.locator("#pt-chat-log").textContent();
  const sent = Date.now() / 1000;
  await page.press("#pt-chat-input", "Enter");
  await page.waitForFunction((b) => {
    const t = document.querySelector("#pt-chat-log")?.textContent || "";
    return t.length > b.length + 60 && !/can take a minute/i.test(t);
  }, before, { timeout: 180000 });
  const answered = Date.now() / 1000;
  await page.waitForTimeout(4000);
  const end = Date.now() / 1000;
  const reply = await page.locator("#pt-chat-log").textContent();
  rec = false;
  await grab;
  await ctx.close();
  if (frames.length < 2) throw new Error("no frames captured");
  console.log(`frames: ${frames.length} over ${(end - frames[0].t).toFixed(1)} s`);
  // frames arrive only when the page changes: give each one its real duration, then resample to 25 fps
  const lines = [];
  frames.forEach((f, i) => {
    const name = `f${String(i).padStart(5, "0")}.jpg`;
    writeFileSync(join(fdir, name), f.data);
    const next = i + 1 < frames.length ? frames[i + 1].t : end;
    lines.push(`file '${name}'`, `duration ${Math.max(0.001, next - f.t).toFixed(4)}`);
  });
  lines.push(`file 'f${String(frames.length - 1).padStart(5, "0")}.jpg'`);
  writeFileSync(join(fdir, "list.txt"), lines.join("\n"));
  execFileSync(ffmpegPath(), ["-y", "-f", "concat", "-safe", "0", "-i", join(fdir, "list.txt"), "-vf", "fps=25,scale=in_range=pc:out_range=tv,format=yuv420p",
    "-color_range", "tv", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-profile:v", "high", "-level", "5.1", "-movflags", "+faststart", join(DECK, "public/demo.mp4")], { stdio: "ignore" });
  // VP9 copy too: Playwright's Chromium cannot decode H.264, and the deck lists webm first.
  execFileSync(ffmpegPath(), ["-y", "-i", join(DECK, "public/demo.mp4"), "-c:v", "libvpx-vp9", "-pix_fmt", "yuv420p", "-b:v", "0", "-crf", "34", "-row-mt", "1",
    "-deadline", "realtime", "-cpu-used", "8", join(DECK, "public/demo.webm")], { stdio: "ignore" });
  const t0 = frames[0].t;
  const meta = JSON.parse(readFileSync(join(OUT, "ui.json"), "utf8"));
  writeFileSync(join(OUT, "ui.json"), JSON.stringify({ ...meta, videoSend: +(sent - t0).toFixed(2), videoAnswer: +(answered - t0).toFixed(2),
    reply: reply?.slice(0, 1500) }, null, 2));
}

await browser.close();
stop();
console.log("captured:", existsSync(join(DECK, "public/demo.mp4")) ? "public/demo.mp4" : "(no video)", "public/clinic/ui@2x.png", mock ? "(stand-in model)" : `(model ${MODEL})`);
process.exit(0);
