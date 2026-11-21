import "@fontsource-variable/geist";
import "@fontsource-variable/geist-mono";
import "./style.css";
import gsap from "gsap";
import { SplitText } from "gsap/SplitText";
import { CustomEase } from "gsap/CustomEase";
import { ScrambleTextPlugin } from "gsap/ScrambleTextPlugin";
import { MotionPathPlugin } from "gsap/MotionPathPlugin";
import { TextPlugin } from "gsap/TextPlugin";
import { CUT_TO_3MIN, CLINIC_ASSISTANT_URL } from "./config.ts";
import { stepsFor } from "./script.ts";
import ui from "../public/clinic/ui.json";

gsap.registerPlugin(SplitText, CustomEase, ScrambleTextPlugin, MotionPathPlugin, TextPlugin);
CustomEase.create("hero", "0.05,0.7,0.1,1"); // Material 3 emphasized-decelerate

type TL = gsap.core.Timeline;
const $ = <T extends Element = HTMLElement>(s: string) => document.querySelector(s) as T;
const $$ = (s: string) => [...document.querySelectorAll<HTMLElement>(s)];
const params = new URLSearchParams(location.search);
const plan = stepsFor(CUT_TO_3MIN || params.has("cut"));
const stage = $("#stage");
const sections = $$("section.scene");
const video = $<HTMLVideoElement>("#demo-video");
let forceVideo = !CLINIC_ASSISTANT_URL;

// ---- motion helpers (tokens: hero 0.9-1.2 s, secondary 0.4 s, exit 0.25 s, stagger 0.06-0.1 s) --------------
const show = (el: gsap.TweenTarget) => gsap.set(el, { autoAlpha: 1 });
const rise = (el: HTMLElement) => {
  show(el);
  const split = SplitText.create(el, { type: "lines", mask: "lines" });
  return gsap.from(split.lines, { yPercent: 110, duration: 0.95, ease: "hero", stagger: 0.08 });
};
const blurIn = (el: HTMLElement) => {
  show(el);
  const split = SplitText.create(el, { type: "words" });
  return gsap.from(split.words, { filter: "blur(16px)", opacity: 0, y: 12, scale: 1.04, duration: 1.1, ease: "power2.out", stagger: 0.06 });
};
const fadeUp = (el: gsap.TweenTarget, stagger = 0) =>
  gsap.fromTo(el, { autoAlpha: 0, y: 24 }, { autoAlpha: 1, y: 0, duration: 0.4, ease: "power3.out", stagger });
const out = (el: gsap.TweenTarget) => gsap.to(el, { autoAlpha: 0, duration: 0.25, ease: "power2.in" });

// ---- Scene 6 geometry: push in on the chat input of the captured UI -------------------------------------------
const FRAME = { w: 1520, h: 855, x: 200, y: 150 };
const k = FRAME.w / ui.viewport.width;
type Box = { x: number; y: number; width: number; height: number };
/** Transform for #ui-wrap that zooms (at most maxS) onto a box given in capture pixels. */
function focusOn(r: Box, maxS: number) {
  const cx = FRAME.w / 2, cy = FRAME.h / 2;
  const s = Math.min(maxS, (0.92 * FRAME.w) / (r.width * k), (0.92 * FRAME.h) / (r.height * k));
  const px = (r.x + r.width / 2) * k, py = (r.y + r.height / 2) * k;
  // keep the scaled capture covering the frame (no empty edges), so the target may land off-centre
  const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));
  const x = clamp(s * (cx - px), (1 - s) * (FRAME.w - cx), (s - 1) * cx);
  const y = clamp(s * (cy - py), (1 - s) * (FRAME.h - cy), (s - 1) * cy);
  return { s, x, y, sx: cx + s * (px - cx) + x, sy: cy + s * (py - cy) + y };
}
const PUSH = { ...focusOn(ui.input, 2.2), hh: (ui.input.height * k * 2.2) / 2 };
// After the question is sent, follow the chat panel: close on the "checking / asking the model" line while the
// answer generates, then ease out to frame the whole answer card when it lands (times from the capture).
const meta = ui as { response?: Box; videoSend?: number; videoAnswer?: number };
const CHAT = meta.response ?? { x: 1219, y: 177, width: 363, height: 468 };
const STATUS = focusOn({ ...CHAT, height: 150 }, 2.2);
const ANSWER = focusOn(CHAT, 2.2);
const SEND_AT = meta.videoSend ?? 3, ANSWER_AT = meta.videoAnswer ?? 10;

// ---- Scene 6 vector field: 52 rows in the local store (40 patient profiles + 12 injection examples) ------------
// Layout is illustrative 2-D placement; the 3 nearest sit closest to the open patient (the green dot).
const Q = { x: 430, y: 380 };
const NEAR = [{ x: 470, y: 344 }, { x: 392, y: 418 }, { x: 600, y: 470 }];
(() => {
  const field = $("#field");
  let seed = 7;
  const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
  const pts: { x: number; y: number }[] = [];
  while (pts.length < 48) {
    const p = { x: 30 + rnd() * 840, y: 30 + rnd() * 680 };
    if (Math.hypot(p.x - Q.x, p.y - Q.y) > 200 && pts.every((o) => Math.hypot(o.x - p.x, o.y - p.y) > 46)) pts.push(p);
  }
  const dot = (p: { x: number; y: number }, cls = "") => {
    const d = document.createElement("i");
    d.className = "dot " + cls;
    d.style.left = p.x + "px"; d.style.top = p.y + "px";
    field.append(d);
    return d;
  };
  pts.forEach((p) => dot(p));
  NEAR.forEach((p) => dot(p, "near").append(Object.assign(document.createElement("i"), { className: "lit" })));
  dot(Q, "q");
  const rows = $("#sim-rows");
  ui.similar.forEach((r) => {
    const li = document.createElement("li");
    const why = r.why.replace(/^.*?(Shares|Has): /, "").split(",")[0];
    li.innerHTML = `<i></i><span class="pct">${r.match.replace(" match", "")}</span><span>${why}</span>`;
    rows.append(li);
  });
  NEAR.forEach(() => $("#s6").append(Object.assign(document.createElement("i"), { className: "fly h" })));
})();

// ---- beats: one per step; each builds its animation into `tl` -------------------------------------------------
const beats: Record<string, (tl: TL) => void> = {
  boot(tl) {
    const n = { v: 0 }, count = $("#boot-count");
    count.textContent = "0%";
    show("#boot");
    tl.fromTo("#boot-label", { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.4, ease: "power3.out" }, 0)
      .to(n, { v: 100, duration: 1.5, ease: "power2.inOut", onUpdate: () => { count.textContent = `${Math.round(n.v)}%`; } }, 0);
  },
  headline(tl) { tl.add(rise($("#s1-head"))); },
  stat(tl) {
    tl.add(out("#s1-head"), 0).add(blurIn($("#s1-num")), 0.25).add(rise($("#s1-sub")), 0.6);
    show("#s1-stat");
  },
  record(tl) {
    tl.add(gsap.fromTo("#rec", { autoAlpha: 0, y: 40 }, { autoAlpha: 1, y: 0, duration: 0.95, ease: "hero" }), 0)
      .add(fadeUp("#agent"), 0.3);
  },
  leak(tl) {
    show(["#rec", "#agent"]); // CUT_TO_3MIN skips the record beat
    tl.to("#rec", { x: 140, duration: 1.1, ease: "hero" }, 0)
      .to(".leak-fill", { opacity: 1, duration: 0.4, ease: "power3.out", stagger: 0.08 }, 0.4)
      .fromTo("#leak-line", { autoAlpha: 0, scaleY: 0 }, { autoAlpha: 1, scaleY: 1, duration: 0.4, ease: "power3.out" }, 0.9)
      .add(fadeUp("#leak-target"), 1.1)
      .add(fadeUp("#leak-tag"), 1.4);
  },
  reveal(tl) {
    show(".layer");
    tl.to(".layer-front", { scale: 6, duration: 1.4, ease: "power2.inOut" }, 0)
      .to(".layer-front", { autoAlpha: 0, duration: 0.3, ease: "power2.in" }, 1.1)
      .to(".layer-mid", { scale: 3, opacity: 0, duration: 1.4, ease: "power2.inOut" }, 0)
      .fromTo(".layer-back", { scale: 1.25 }, { scale: 1, duration: 1.5, ease: "power2.inOut" }, 0)
      .add(blurIn($("#s3-logo")), 0.9)
      .add(rise($("#s3-sub")), 1.5)
      .add(fadeUp("#s3-nv"), 1.9);
  },
  pipeline(tl) {
    tl.add(fadeUp(".pnode", 0.08), 0)
      .fromTo(".conn", { autoAlpha: 0, scaleX: 0 }, { autoAlpha: 1, scaleX: 1, duration: 0.4, ease: "power3.out", stagger: 0.08 }, 0.3);
  },
  safe(tl) {
    tl.add(fadeUp("#req-safe"), 0)
      .set("#pk-safe", { autoAlpha: 1 }, 0.3)
      .to("#pk-safe", { duration: 1.2, ease: "power1.inOut", motionPath: { path: "#route", start: 0, end: 1 } }, 0.3)
      .to("#n-tool .ring", { opacity: 1, duration: 0.4, ease: "power3.out" }, 1.4)
      .add(fadeUp("#tag-allow"), 1.4)
      .to("#pk-safe", { autoAlpha: 0, duration: 0.25, ease: "power2.in" }, 1.55);
  },
  unsafe(tl) {
    const atGuard = (730 - 270) / (1650 - 270); // policy node centre along the route
    tl.add(out(["#req-safe", "#tag-allow", "#n-tool .ring"]), 0)
      .add(fadeUp("#req-bad"), 0.25)
      .set("#pk-bad", { autoAlpha: 1 }, 0.5)
      .to("#pk-bad", { duration: 0.9, ease: "power1.inOut", motionPath: { path: "#route", start: 0, end: atGuard } }, 0.5)
      .to("#pk-bad-ox", { opacity: 1, duration: 0.2, ease: "power2.out" }, 1.4)
      .to("#pk-bad", { scale: 1.6, duration: 0.2, ease: "power2.out", transformOrigin: "50% 50%" }, 1.4)
      .to("#n-policy .ring", { opacity: 1, duration: 0.2, ease: "power2.out" }, 1.4)
      .add(fadeUp("#tag-block"), 1.5)
      .to("#pk-bad", { autoAlpha: 0, duration: 0.3, ease: "power2.in" }, 1.75);
  },
  nemotron(tl) {
    // the real reasoner output for the blocked email (leash/demo/output/scripted_run.txt, call 13)
    tl.add(out("#req-bad"), 0)
      .add(gsap.fromTo("#nv-card", { autoAlpha: 0, y: 40 }, { autoAlpha: 1, y: 0, duration: 0.95, ease: "hero" }), 0.15)
      .add(fadeUp("#nv-rule"), 0.9);
  },
  note(tl) {
    $$(".phi").forEach((s) => { s.textContent = s.dataset.orig ??= s.textContent ?? ""; s.classList.remove("on"); });
    tl.add(rise($("#s5-head")), 0)
      .add(gsap.fromTo("#note", { autoAlpha: 0, y: 40 }, { autoAlpha: 1, y: 0, duration: 0.95, ease: "hero" }), 0.15);
  },
  redact(tl) {
    $$(".phi").forEach((s, i) => {
      tl.call(() => s.classList.add("on"), [], i * 0.1)
        .to(s, { duration: 0.8, ease: "none", scrambleText: { text: s.dataset.tag!, chars: "█▓▒░", speed: 0.6 } }, i * 0.1);
    });
  },
  audit(tl) {
    const a = $("#audit");
    a.textContent = "";
    show(a);
    tl.to(a, { duration: 1.0, ease: "none", text: { value:
      "audit  model_answer  masked_tags=[DATE_TIME, EMAIL_ADDRESS, LOCATION, PERSON, PHONE_NUMBER, URL, US_DRIVER_LICENSE]  hash=sha256(previous hash + this entry)" } });
  },
  ui(tl) {
    tl.add(fadeUp("#s6-cap"), 0)
      .add(gsap.fromTo("#ui-frame", { autoAlpha: 0, scale: 0.96 }, { autoAlpha: 1, scale: 1, duration: 0.95, ease: "hero" }), 0);
  },
  push(tl) {
    const spot = $("#spotlight");
    spot.style.setProperty("--sx", `${PUSH.sx}px`);
    spot.style.setProperty("--sy", `${PUSH.sy}px`);
    const label = $("#spot-label");
    label.style.left = `${FRAME.x + PUSH.sx}px`;
    gsap.set(label, { xPercent: -50 });
    label.style.top = `${FRAME.y + PUSH.sy + PUSH.hh + 18}px`;
    tl.to("#ui-wrap", { scale: PUSH.s, x: PUSH.x, y: PUSH.y, duration: 1.1, ease: "hero" }, 0)
      .fromTo(spot, { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.4, ease: "power3.out" }, 0.8)
      .add(fadeUp(label), 1.0);
  },
  demo(tl) {
    tl.add(out(["#spotlight", "#spot-label"]), 0).call(startDemo, [], 0.3);
    if (forceVideo) {
      // Stay zoomed on the input while the question is typed; when it is sent, move up to the answer.
      // This follow timeline runs on the video's own clock (see followVideo), not on the step's.
      tl.fromTo(video, { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.4, ease: "power3.out" }, 0.3);
      follow = gsap.timeline({ paused: true })
        .fromTo("#ui-wrap", { scale: PUSH.s, x: PUSH.x, y: PUSH.y },
          { scale: STATUS.s, x: STATUS.x, y: STATUS.y, duration: 1.1, ease: "hero", immediateRender: false }, SEND_AT + 0.2)
        .to("#ui-wrap", { scale: ANSWER.s, x: ANSWER.x, y: ANSWER.y, duration: 1.1, ease: "hero" }, Math.max(ANSWER_AT, SEND_AT + 1.4));
    } else {
      tl.to("#ui-wrap", { scale: 1, x: 0, y: 0, duration: 0.9, ease: "hero" }, 0); // live app: show all of it
    }
  },
  vectors(tl) {
    const lit = $$(".dot.near .lit"), fly = $$(".fly"), rows = $$("#sim-rows li i");
    tl.call(() => video.pause(), [], 0)
      .add(out(["#ui-frame", "#s6-cap"]), 0)
      .add(rise($("#vec-label")), 0.25)
      .fromTo("#field", { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.4, ease: "power3.out" }, 0.25)
      .from(".dot.q", { scale: 0, duration: 0.4, ease: "power3.out" }, 0.5)
      .to(lit, { opacity: 1, duration: 0.4, ease: "power3.out", stagger: 0.08 }, 0.8)
      .add(fadeUp("#sim-card"), 0.9);
    fly.forEach((f, i) => {
      const from = { x: 96 + NEAR[i].x, y: 250 + NEAR[i].y };
      const r = rows[i];
      const to = { x: 1080 + r.offsetLeft + 9, y: 330 + r.offsetTop + r.offsetHeight / 2 };
      gsap.set(f, { left: from.x, top: from.y, x: 0, y: 0 });
      tl.set(f, { autoAlpha: 1 }, 1.1)
        .to(f, { x: to.x - from.x, y: to.y - from.y, duration: 1.0, ease: "hero" }, 1.1 + i * 0.08);
    });
  },
  archAgent(tl) {
    tl.add(fadeUp(".ab.lane-a:not(.gw):not(.right)"), 0)
      .fromTo(".aline.lane-a", { autoAlpha: 0, scaleX: 0 }, { autoAlpha: 1, scaleX: 1, duration: 0.4, ease: "power3.out", stagger: 0.08 }, 0.3)
      .add(gsap.fromTo(".ab.gw.lane-a", { autoAlpha: 0, y: 30 }, { autoAlpha: 1, y: 0, duration: 0.95, ease: "hero" }), 0.2)
      .add(fadeUp(".ab.gw.lane-a .cell", 0.06), 0.6)
      .add(fadeUp(".ab.right", 0.08), 1.0);
  },
  archStaff(tl) {
    tl.add(fadeUp(".ab.lane-b:not(.gw)"), 0)
      .fromTo(".aline.lane-b", { autoAlpha: 0, scaleX: 0 }, { autoAlpha: 1, scaleX: 1, duration: 0.4, ease: "power3.out" }, 0.2)
      .add(gsap.fromTo(".ab.gw.lane-b", { autoAlpha: 0, y: 30 }, { autoAlpha: 1, y: 0, duration: 0.95, ease: "hero" }), 0.3)
      .add(fadeUp(".ab.gw.lane-b .cell", 0.06), 0.7);
  },
  whyNemotron(tl) {
    tl.add(out([".pnode", ".conn", "#nv-card"]), 0).add(rise($("#why")), 0.25);
  },
  impact(tl) {
    show("#impact");
    tl.add(rise($("#imp-row")), 0).add(fadeUp("#imp-sub"), 0.7);
  },
  proof(tl) { tl.add(out("#impact"), 0).add(rise($("#proof")), 0.25); },
  team(tl) { tl.add(out("#proof"), 0).add(rise($("#team")), 0.25); },
  hold(tl) { show("#s7-end"); tl.add(out("#team"), 0).add(blurIn($("#s7-logo")), 0.25).add(fadeUp("#s7-nv"), 1.0); },
};

function startDemo() {
  if (!forceVideo) {
    let f = $<HTMLIFrameElement>("#live-frame");
    if (!f) {
      f = Object.assign(document.createElement("iframe"), { id: "live-frame", src: CLINIC_ASSISTANT_URL });
      $("#ui-wrap").append(f);
    }
    return;
  }
  $("#live-frame")?.remove();
  video.currentTime = 0;
  void video.play().catch(() => {});
}

// ---- engine ----------------------------------------------------------------------------------------------
let ctx = gsap.context(() => {}, stage);
let follow = null as TL | null; // set by the demo beat; "as" stops TS narrowing it to null here
let idx = -1, shown = -1;
let current: TL | null = null;
const timelines: TL[] = [];
(function followVideo() {
  if (follow && plan[idx]?.id === "demo" && forceVideo && !video.paused) follow.seek(video.currentTime);
  requestAnimationFrame(followVideo);
})();
const reduced = () => matchMedia("(prefers-reduced-motion: reduce)").matches;
const firstOfScene = (n: number) => { let i = n; while (i > 0 && plan[i - 1].scene === plan[n].scene) i--; return i; };

function render(n: number, animate: boolean) {
  current?.progress(1);
  video.pause();
  const step = plan[n], sec = sections[step.scene];
  const sequential = animate && n === idx + 1 && !reduced();
  const tl = gsap.timeline();
  if (sequential) {
    ctx.add(() => {
      if (step.scene !== shown) {
        if (shown >= 0) tl.to(sections[shown], { autoAlpha: 0, duration: 0.25, ease: "power2.in" });
        tl.set(sec, { autoAlpha: 1 });
      }
      const inner = gsap.timeline();
      beats[step.id](inner);
      tl.add(inner);
    });
  } else {
    // Jump, back, hash or reduced motion: rebuild the scene from scratch and land on the end state.
    ctx.revert();
    ctx = gsap.context(() => {}, stage);
    ctx.add(() => {
      gsap.set(sec, { autoAlpha: 1 });
      for (let i = firstOfScene(n); i < n; i++) { const t = gsap.timeline(); beats[plan[i].id](t); t.progress(1); }
      beats[step.id](tl);
      tl.progress(1);
      if (animate && reduced() && step.scene !== shown) tl.add(gsap.fromTo(sec, { opacity: 0 }, { opacity: 1, duration: 0.2 }), ">")
        .play(tl.duration() - 0.2);
    });
  }
  timelines[n] = tl;
  current = tl;
  idx = n;
  $("#start-hint").hidden = true;
  shown = step.scene;
  history.replaceState(null, "", `${location.search}#${n}`);
}

function blank() {
  current?.progress(1);
  video.pause();
  ctx.revert();
  ctx = gsap.context(() => {}, stage);
  idx = shown = -1;
  current = null;
  $("#start-hint").hidden = false;
  history.replaceState(null, "", location.search || location.pathname);
}

function next() {
  if (current && current.progress() < 1) { current.progress(1); return; } // second press finishes the step (isActive() is false until the first tick)
  if (idx < plan.length - 1) render(idx + 1, true);
}
function prev() {
  if (idx > 0) render(idx - 1, false);
  else if (idx === 0) blank();
}
const goTo = (n: number) => (n < 0 ? blank() : render(Math.min(n, plan.length - 1), false));

addEventListener("keydown", (e) => {
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  if (["ArrowRight", "ArrowDown", "PageDown", " ", "Enter"].includes(e.key)) { e.preventDefault(); next(); }
  else if (["ArrowLeft", "ArrowUp", "PageUp"].includes(e.key)) { e.preventDefault(); prev(); }
  else if (e.key === "f") { if (document.fullscreenElement) void document.exitFullscreen(); else void document.documentElement.requestFullscreen(); }
  else if (e.key === "d") { forceVideo = true; const n = plan.findIndex((s) => s.id === "demo"); if (idx === n) render(n, false); }
  else if (e.key === "p") toggleFps();
});

// ---- fit the 1920x1080 stage to the window ----------------------------------------------------------------
function fit() {
  const s = Math.min(innerWidth / 1920, innerHeight / 1080);
  stage.style.transform = `translate(${(innerWidth - 1920 * s) / 2}px, ${(innerHeight - 1080 * s) / 2}px) scale(${s})`;
}
addEventListener("resize", fit);
fit();

// ---- FPS meter (p) ----------------------------------------------------------------------------------------
let fpsOn = false;
function toggleFps() {
  const el = $("#fps");
  fpsOn = !fpsOn;
  el.hidden = !fpsOn;
  let frames = 0, t0 = performance.now();
  const tick = (t: number) => {
    if (!fpsOn) return;
    frames++;
    if (t - t0 >= 500) { el.textContent = `${Math.round((frames * 1000) / (t - t0))} fps`; frames = 0; t0 = t; }
    requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}

// ---- start ----------------------------------------------------------------------------------------------
const deck = {
  get stepIndex() { return idx; },
  stepCount: plan.length,
  timelines,
  plan,
  goTo,
  next,
  prev,
  ready: false,
  done: false,
};
(window as unknown as { __deck: typeof deck }).__deck = deck;

await document.fonts.ready; // SplitText must measure the real font
const fromHash = () => { const m = /^#(\d+)$/.exec(location.hash); if (m) goTo(+m[1]); };
addEventListener("hashchange", fromHash);
fromHash();
if (idx === -1 && !params.has("autoplay")) $("#start-hint").hidden = false;
deck.ready = true;

if (params.has("autoplay")) {
  const wait = (s: number) => new Promise((r) => setTimeout(r, s * 1000));
  await wait(1);
  for (const step of plan) { next(); await wait(step.sec); }
  deck.done = true;
}
