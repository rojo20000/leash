// Runs against `vite build && vite preview` (see playwright.config.ts), headless at 1920x1080.
// Measured numbers are written to showcase/metrics.json for SHOWCASE.md.
import { test, expect, type Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { mkdirSync, writeFileSync, readFileSync, existsSync } from "node:fs";
import { STEPS, totalSeconds } from "../src/script.ts";

const N = STEPS.length;
const SAFE = { x0: 96, y0: 54, x1: 1824, y1: 1026 }; // 5% of 1920x1080
const METRICS = "showcase/metrics.json";
const record = (key: string, value: unknown) => {
  const m = existsSync(METRICS) ? JSON.parse(readFileSync(METRICS, "utf8")) : {};
  m[key] = value;
  mkdirSync("showcase", { recursive: true });
  writeFileSync(METRICS, JSON.stringify(m, null, 2));
};

type Deck = { stepIndex: number; stepCount: number; ready: boolean; plan: { id: string; scene: number }[];
  timelines: gsap.core.Timeline[]; goTo(n: number): void; next(): void; prev(): void };
declare global { interface Window { __deck: Deck } }

async function open(page: Page, hash = "") {
  await page.goto("/" + hash);
  await page.waitForFunction(() => window.__deck?.ready);
}
/** Press forward and wait for the step to finish on its own. */
async function stepAndSettle(page: Page, n: number) {
  await page.keyboard.press("ArrowRight");
  await page.waitForFunction((i) => window.__deck.stepIndex === i && window.__deck.timelines[i].progress() === 1, n, { timeout: 5000 });
  await page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));
}
const quiet = (page: Page) => page.addStyleTag({ content: "#grain{display:none!important} video{visibility:hidden!important}" });

test("1+2. every step renders with no console errors, no failed requests, nothing leaves localhost", async ({ page }) => {
  const errors: string[] = [], failed: string[] = [], offsite: string[] = [];
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("requestfailed", (r) => {
    // a <video> cancels its own range requests when it pauses or swaps source; that is not a failure
    if (!(r.failure()?.errorText.includes("ABORTED") && /demo\.(webm|mp4)/.test(r.url()))) failed.push(`${r.url()} ${r.failure()?.errorText}`);
  });
  page.on("response", (r) => { if (r.status() >= 400) failed.push(`${r.url()} ${r.status()}`); });
  page.on("request", (r) => { const h = new URL(r.url()).hostname; if (!["localhost", "127.0.0.1"].includes(h) && !r.url().startsWith("data:")) offsite.push(r.url()); });
  await open(page);
  for (let n = 0; n < N; n++) {
    await stepAndSettle(page, n);
    expect(await page.evaluate(() => window.__deck.stepIndex)).toBe(n);
  }
  record("renders", { steps: N, consoleErrors: errors.length, failedRequests: failed.length, offsiteRequests: offsite.length });
  expect(errors).toEqual([]);
  expect(failed).toEqual([]);
  expect(offsite).toEqual([]);
});

test("3. end states: type size, contrast, safe margin, word count", async ({ page }) => {
  await open(page);
  const per: Record<string, unknown>[] = [];
  const problems: string[] = [];
  for (let n = 0; n < N; n++) {
    await stepAndSettle(page, n);
    const r = await page.evaluate(({ SAFE }) => {
      const parse = (c: string) => { const m = c.match(/[\d.]+/g)!.map(Number); return { r: m[0], g: m[1], b: m[2], a: m[3] ?? 1 }; };
      const lum = (c: { r: number; g: number; b: number }) => {
        const f = (v: number) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; };
        return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b);
      };
      const alpha = (el: Element | null) => {
        let a = 1;
        for (let e = el; e; e = e.parentElement) {
          const cs = getComputedStyle(e);
          if (cs.display === "none" || cs.visibility === "hidden") return 0;
          a *= +cs.opacity;
        }
        return a;
      };
      const bgOf = (el: Element | null) => {
        for (let e = el; e; e = e.parentElement) { const c = parse(getComputedStyle(e).backgroundColor); if (c.a > 0.5) return c; }
        return { r: 7, g: 8, b: 10, a: 1 };
      };
      const out = { minFont: 999, minDisplay: 999, minContrast: 99, words: 0, outside: [] as string[], small: [] as string[], lowContrast: [] as string[] };
      const walker = document.createTreeWalker(document.getElementById("stage")!, NodeFilter.SHOW_TEXT);
      for (let t = walker.nextNode(); t; t = walker.nextNode()) {
        const el = t.parentElement!;
        if (!/\S/.test(t.textContent!) || alpha(el) < 0.05) continue;
        const range = document.createRange(); range.selectNodeContents(t);
        const rect = range.getBoundingClientRect();
        if (rect.width === 0 || rect.height === 0) continue;
        const cs = getComputedStyle(el), size = parseFloat(cs.fontSize), label = t.textContent!.trim().slice(0, 40);
        out.minFont = Math.min(out.minFont, size);
        if (size < 28) out.small.push(`${label} ${size}px`);
        if (el.closest(".display")) out.minDisplay = Math.min(out.minDisplay, size);
        const fg = parse(cs.color), bg = bgOf(el), a = fg.a * alpha(el);
        const mix = { r: fg.r * a + bg.r * (1 - a), g: fg.g * a + bg.g * (1 - a), b: fg.b * a + bg.b * (1 - a) };
        const [l1, l2] = [lum(mix), lum(bg)].sort((x, y) => y - x);
        const ratio = (l1 + 0.05) / (l2 + 0.05);
        out.minContrast = Math.min(out.minContrast, ratio);
        if (ratio < 4.5) out.lowContrast.push(`${label} ${ratio.toFixed(2)}`);
        if (rect.left < SAFE.x0 - 1 || rect.top < SAFE.y0 - 1 || rect.right > SAFE.x1 + 1 || rect.bottom > SAFE.y1 + 1)
          out.outside.push(`${label} [${Math.round(rect.left)},${Math.round(rect.top)},${Math.round(rect.right)},${Math.round(rect.bottom)}]`);
        if (!el.closest("[data-exempt-wordcount]")) out.words += t.textContent!.split(/\s+/).filter((w) => /[A-Za-z0-9]/.test(w)).length;
      }
      document.querySelectorAll("#stage [data-safe]").forEach((el) => {
        if (alpha(el) < 0.05) return;
        const rect = el.getBoundingClientRect();
        if (rect.left < SAFE.x0 - 1 || rect.top < SAFE.y0 - 1 || rect.right > SAFE.x1 + 1 || rect.bottom > SAFE.y1 + 1)
          out.outside.push(`#${el.id || el.className} [${Math.round(rect.left)},${Math.round(rect.top)},${Math.round(rect.right)},${Math.round(rect.bottom)}]`);
      });
      return out;
    }, { SAFE });
    per.push({ step: n, id: STEPS[n].id, ...r, minContrast: +r.minContrast.toFixed(2) });
    if (r.small.length) problems.push(`step ${n}: under 28px: ${r.small.join("; ")}`);
    if (r.minDisplay < 96) problems.push(`step ${n}: display headline ${r.minDisplay}px`);
    if (r.lowContrast.length) problems.push(`step ${n}: contrast: ${r.lowContrast.join("; ")}`);
    if (r.outside.length) problems.push(`step ${n}: outside safe margin: ${r.outside.join("; ")}`);
    if (r.words > 12) problems.push(`step ${n}: ${r.words} words`);
  }
  record("endStates", per);
  expect(problems).toEqual([]);
});

test("4. motion tokens: tweens 0.1-1.5 s, step timelines at most 3 s", async ({ page }) => {
  await open(page);
  const rows = [];
  for (let n = 0; n < N; n++) {
    await page.evaluate(() => window.__deck.next());
    rows.push(await page.evaluate((i) => {
      const tl = window.__deck.timelines[i];
      const ds = tl.getChildren(true, true, false).map((t) => (typeof t.vars.duration === "number" ? t.vars.duration : t.duration()))
        .filter((d) => d > 0);
      const r = { step: i, total: +tl.duration().toFixed(3), shortest: Math.min(...ds), longest: Math.max(...ds), tweens: ds.length };
      tl.progress(1);
      return r;
    }, n));
  }
  record("motion", rows);
  for (const r of rows) {
    expect(r.shortest, `step ${r.step} shortest tween`).toBeGreaterThanOrEqual(0.1);
    expect(r.longest, `step ${r.step} longest tween`).toBeLessThanOrEqual(1.5);
    expect(r.total, `step ${r.step} timeline`).toBeLessThanOrEqual(3);
  }
});

test("5. a second press finishes the step; back shows the previous end state", async ({ page }) => {
  await open(page, "#4");
  await page.keyboard.press("ArrowRight"); // step 5, the dolly
  await page.waitForTimeout(250);
  const mid = await page.evaluate(() => ({ i: window.__deck.stepIndex, p: window.__deck.timelines[5].progress() }));
  expect(mid.i).toBe(5);
  expect(mid.p).toBeLessThan(1);
  await page.keyboard.press("ArrowRight");
  const after = await page.evaluate(() => ({ i: window.__deck.stepIndex, p: window.__deck.timelines[5].progress() }));
  expect(after).toEqual({ i: 5, p: 1 });
  await page.keyboard.press("ArrowLeft");
  const back = await page.evaluate(() => ({ i: window.__deck.stepIndex, p: window.__deck.timelines[4].progress(), hash: location.hash }));
  expect(back).toEqual({ i: 4, p: 1, hash: "#4" });
  record("doublePress", { midProgress: +mid.p.toFixed(3), afterSecondPress: after.p, backTo: back.i });
});

test("6. stepping forward and jumping by hash give the same frame (and save step screenshots)", async ({ page, browser }) => {
  mkdirSync("showcase/steps", { recursive: true });
  await open(page);
  await quiet(page);
  const forward: Buffer[] = [];
  for (let n = 0; n < N; n++) {
    await stepAndSettle(page, n);
    forward.push(await page.screenshot());
    writeFileSync(`showcase/steps/step-${String(n).padStart(2, "0")}-${STEPS[n].id}.png`, forward[n]);
  }
  const diffs: number[] = [];
  const cmp = await browser.newPage();
  for (let n = 0; n < N; n++) {
    const p = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
    await open(p, `#${n}`);
    await quiet(p);
    await p.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));
    const jumped = await p.screenshot();
    await p.close();
    diffs.push(await cmp.evaluate(async ([a, b]) => {
      const load = (s: string) => new Promise<HTMLImageElement>((r) => { const i = new Image(); i.onload = () => r(i); i.src = "data:image/png;base64," + s; });
      const [ia, ib] = await Promise.all([load(a), load(b)]);
      const px = (img: HTMLImageElement) => { const c = document.createElement("canvas"); c.width = img.width; c.height = img.height;
        const x = c.getContext("2d")!; x.drawImage(img, 0, 0); return x.getImageData(0, 0, c.width, c.height).data; };
      const da = px(ia), db = px(ib);
      let bad = 0;
      for (let i = 0; i < da.length; i += 4) if (Math.abs(da[i] - db[i]) + Math.abs(da[i + 1] - db[i + 1]) + Math.abs(da[i + 2] - db[i + 2]) > 24) bad++;
      return bad / (da.length / 4);
    }, [forward[n].toString("base64"), jumped.toString("base64")]));
  }
  record("frameMatch", diffs.map((d, n) => ({ step: n, diffPercent: +(d * 100).toFixed(3) })));
  execFileSync(process.execPath, ["scripts/contact-sheet.mjs"], { stdio: "inherit" });
  diffs.forEach((d, n) => expect(d, `step ${n} pixel diff`).toBeLessThan(0.01));
});

test("7. reduced motion: every step done within 250 ms with its content visible", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await open(page);
  const rows = [];
  for (let n = 0; n < N; n++) {
    const t0 = Date.now();
    await page.keyboard.press("ArrowRight");
    await page.waitForFunction((i) => window.__deck.stepIndex === i && window.__deck.timelines[i].progress() === 1, n, { timeout: 1000 });
    const ms = Date.now() - t0;
    const opacity = await page.evaluate((i) => +getComputedStyle(document.querySelectorAll("section.scene")[window.__deck.plan[i].scene]).opacity, n);
    rows.push({ step: n, ms, opacity });
  }
  record("reducedMotion", rows);
  for (const r of rows) {
    expect(r.ms, `step ${r.step}`).toBeLessThanOrEqual(250);
    expect(r.opacity, `step ${r.step}`).toBe(1);
  }
});

test("8. d swaps Scene 6 to the recorded demo, and it plays", async ({ page }) => {
  await open(page);
  const n = await page.evaluate(() => window.__deck.plan.findIndex((s) => s.id === "demo"));
  await page.evaluate((i) => window.__deck.goTo(i), n);
  await page.keyboard.press("d");
  await page.waitForTimeout(1200);
  const v = await page.evaluate(() => {
    const el = document.querySelector("video")!;
    return { paused: el.paused, t: el.currentTime, opacity: +getComputedStyle(el).opacity, src: el.currentSrc.split("/").pop() };
  });
  record("demoVideo", v);
  expect(v.paused).toBe(false);
  expect(v.t).toBeGreaterThan(0.2);
  expect(v.opacity).toBe(1);
});

test("9. script timing: 220-260 s full, 160-190 s with CUT_TO_3MIN", () => {
  const full = totalSeconds(false), cut = totalSeconds(true);
  record("timing", { full, cut });
  expect(full).toBeGreaterThanOrEqual(220);
  expect(full).toBeLessThanOrEqual(260);
  expect(cut).toBeGreaterThanOrEqual(160);
  expect(cut).toBeLessThanOrEqual(190);
});

test("9b. ?cut=1 builds the short deck and it renders end to end", async ({ page }) => {
  await page.goto("/?cut=1");
  await page.waitForFunction(() => window.__deck?.ready);
  const count = await page.evaluate(() => window.__deck.stepCount);
  for (let n = 0; n < count; n++) await stepAndSettle(page, n);
  expect(count).toBe(STEPS.filter((s) => s.cut > 0).length);
});

test("10. FPS per scene (indicative only: headless has no real GPU)", async ({ page }) => {
  await open(page);
  const perStep = [];
  for (let n = 0; n < N; n++) {
    perStep.push(await page.evaluate(async (i) => {
      const gaps: number[] = [];
      let last = performance.now(), on = true;
      const tick = (t: number) => { gaps.push(t - last); last = t; if (on) requestAnimationFrame(tick); };
      requestAnimationFrame(tick);
      window.__deck.next();
      const tl = window.__deck.timelines[i];
      await new Promise((r) => { const w = () => (tl.progress() < 1 ? setTimeout(w, 50) : r(0)); setTimeout(w, 50); });
      on = false;
      gaps.shift();
      const fps = gaps.map((g) => 1000 / g).sort((a, b) => a - b);
      return { step: i, scene: window.__deck.plan[i].scene, min: fps[0] ?? 0, median: fps[Math.floor(fps.length / 2)] ?? 0 };
    }, n));
  }
  const scenes: Record<number, { min: number; median: number }> = {};
  for (const s of perStep) {
    const prev = scenes[s.scene];
    scenes[s.scene] = { min: Math.round(Math.min(prev?.min ?? 999, s.min)), median: Math.round(Math.min(prev?.median ?? 999, s.median)) };
  }
  record(`fps_${process.env.FPS_LABEL ?? "headless"}`, scenes);
  expect(Object.keys(scenes).length).toBe(9);
});
