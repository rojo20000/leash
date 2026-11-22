import gsap from 'gsap';
import type { SceneContext, SceneFrame, Verdict } from './types';

export type StampForm = Verdict | 'alert';
export type StampAnchor = 'center' | 'br' | 'tr' | 'bl';

export interface StampSpec {
  text: string;          // from content, or a verbatim token of it
  form: StampForm;
  anchor?: StampAnchor;  // preferred side, default 'br'; the stamp lands beside the target, never on its text
  land?: number;         // fraction of the step when it hits; default BEATS.land
}

export interface InspectCue {
  step: number;                // 0-based; at most one cue per step
  target: HTMLElement | null;  // null is the wide shot
  scale?: number;              // requested zoom, default 1.6; never below 1
  narrowScale?: number;        // at width <= 767px; default Math.min(scale, 1.5)
  pad?: number;                // px kept clear around the target, default 16 (10 when narrow)
  dim?: boolean;               // default: true when target is set
  reticle?: boolean;           // default: true when target is set
  scan?: boolean;              // default false
  stamp?: StampSpec;
  mark?: boolean;              // reduced motion: draw a static reticle on this target; default true
}

export interface InspectionOptions {
  ctx: SceneContext;
  world: HTMLElement;      // the content the camera moves; a descendant of viewport
  viewport?: HTMLElement;  // the clipped window; default ctx.plate
  steps: number;           // the scene's step count
  cues: InspectCue[];
}

export interface Inspection {
  update(frame: SceneFrame): void;      // call after tl.progress(frame.progress)
  resize(): void;                       // re-measure and re-render the last frame
  at(step: number, beat: keyof typeof BEATS): number; // timeline time of a beat
}

export const BEATS = {
  diveStart: 0.02, arrive: 0.26, lock: 0.28,
  scanStart: 0.28, scanEnd: 0.40, land: 0.42, settle: 0.48,
} as const;

/** Aria-hidden drawn mark. Shape is drawn in CSS (.v-mark). */
export function verdictMark(form: StampForm): HTMLElement {
  const m = document.createElement('span');
  m.className = `v-mark v-mark--${form}`;
  m.setAttribute('aria-hidden', 'true');
  return m;
}

/** Mark plus text; the text is set with textContent. */
export function verdictBadge(form: StampForm, text: string): HTMLElement {
  const b = document.createElement('span');
  b.className = `v-badge v-badge--${form}`;
  const t = document.createElement('span');
  t.className = 'v-badge__text';
  t.textContent = text;
  b.append(verdictMark(form), t);
  return b;
}

// ---------------------------------------------------------------- helpers

interface R { x: number; y: number; w: number; h: number }
interface Pose { s: number; cx: number; cy: number; tx: number; ty: number }

const ease = (name: string) => gsap.parseEase(name) as (t: number) => number;
const power3InOut = ease('power3.inOut');
const power2Out = ease('power2.out');
const expoOut = ease('expo.out');
const backOut = ease('back.out(2.4)');

const clamp01 = (v: number) => Math.min(1, Math.max(0, v));
const win = (u: number, a: number, b: number) => clamp01((u - a) / (b - a));
const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
const clampAxis = (t: number, view: number, size: number) =>
  size <= view ? (view - size) / 2 : Math.min(0, Math.max(view - size, t));

const CORNER = 22;      // bracket arm length, px
const RET_PAD = 4;      // reticle sits this far outside the target rect
const HOLE_PAD = 6;     // dim hole margin around the target
const STAMP_REST_DEG = -4;
const STAMP_GAP = 8;    // clear space between a stamp and its target

/** Offset of el within ancestor, summed up the offsetParent chain (ignores all transforms). */
function offsetWithin(el: HTMLElement, ancestor: HTMLElement): { x: number; y: number } | null {
  let x = 0;
  let y = 0;
  let n: HTMLElement | null = el;
  while (n && n !== ancestor) {
    x += n.offsetLeft;
    y += n.offsetTop;
    n = n.offsetParent as HTMLElement | null;
  }
  return n === ancestor ? { x, y } : null;
}

function part(cls: string): HTMLElement {
  const d = document.createElement('div');
  d.className = cls;
  return d;
}

interface Item {
  step: number;
  cue: InspectCue | null;
  rect: R | null;        // target in world layout coords
  pose: Pose;
  sr: R;                 // rest screen rect (target under its own pose, or the viewport for a wide cue)
  dim: boolean;
  scan: boolean;
  corners: HTMLElement[];
  scanEl: HTMLElement | null;
  traceEl: HTMLElement | null;
  stamp: HTMLElement | null;
  sw: number;            // stamp layout size
  sh: number;
  sk: number;            // stamp fit scale
}

export function createInspection(options: InspectionOptions): Inspection {
  const { ctx, world, steps } = options;
  const viewport = options.viewport ?? ctx.plate;
  const reduced = ctx.reducedMotion;
  viewport.classList.add('inspect-viewport');
  world.classList.add('inspect-world');

  const overlay = part('inspect-overlay');
  overlay.setAttribute('aria-hidden', 'true');
  viewport.append(overlay);

  const dimGroup = part('inspect-dim-group');
  const panels = [part('inspect-dim'), part('inspect-dim'), part('inspect-dim'), part('inspect-dim')];
  dimGroup.append(...panels);
  if (!reduced) overlay.append(dimGroup);

  const count = Math.max(1, steps);
  const items: Item[] = [];
  for (let i = 0; i < count; i++) {
    const cue = options.cues.find((c) => c.step === i) ?? null;
    const hasTarget = !!cue?.target;
    const item: Item = {
      step: i, cue, rect: null,
      pose: { s: 1, cx: 0, cy: 0, tx: 0, ty: 0 },
      sr: { x: 0, y: 0, w: 0, h: 0 },
      dim: hasTarget && cue!.dim !== false,
      scan: hasTarget && cue!.scan === true,
      corners: [], scanEl: null, traceEl: null, stamp: null, sw: 0, sh: 0, sk: 1,
    };
    if (cue && hasTarget && (reduced ? cue.mark !== false : cue.reticle !== false)) {
      for (const pos of ['tl', 'tr', 'bl', 'br']) {
        const c = part(`inspect-corner inspect-corner--${pos}`);
        item.corners.push(c);
        overlay.append(c);
      }
    }
    if (!reduced && item.scan) {
      item.scanEl = part('inspect-scan');
      item.traceEl = part('inspect-trace');
      overlay.append(item.scanEl, item.traceEl);
    }
    if (!reduced && cue?.stamp) {
      item.stamp = verdictBadge(cue.stamp.form, cue.stamp.text);
      item.stamp.classList.add('inspect-stamp');
      overlay.append(item.stamp);
    }
    items.push(item);
  }

  if (reduced) {
    const stamped = items.filter((it) => it.cue?.stamp);
    if (stamped.length) {
      const key = part('inspect-key');
      for (const it of stamped) key.append(verdictBadge(it.cue!.stamp!.form, it.cue!.stamp!.text));
      world.after(key);
    }
  }

  let vw = 0;
  let vh = 0;
  let W = 0;
  let H = 0;
  let ox = 0;
  let oy = 0;
  let warned = false;
  let last: SceneFrame | null = null;

  function measure() {
    vw = viewport.clientWidth;
    vh = viewport.clientHeight;
    W = world.offsetWidth;
    H = world.offsetHeight;
    const narrow = ctx.isNarrow();
    if (reduced) {
      const o = offsetWithin(world, viewport);
      ox = o?.x ?? 0;
      oy = o?.y ?? 0;
    }
    for (const it of items) {
      const cue = it.cue;
      if (it.stamp) {
        it.sw = it.stamp.offsetWidth;
        it.sh = it.stamp.offsetHeight;
        it.sk = it.sw > 0 ? Math.min(1, (vw - 16) / it.sw) : 1;
      }
      let rect: R | null = null;
      if (cue?.target) {
        const t = cue.target;
        const o = t.offsetParent !== null ? offsetWithin(t, world) : null;
        if (o) rect = { x: o.x, y: o.y, w: t.offsetWidth, h: t.offsetHeight };
        else if (!warned) {
          warned = true;
          console.warn('[leash] inspect target outside world');
        }
      }
      it.rect = rect;
      if (!rect) {
        it.pose = { s: 1, cx: W / 2, cy: H / 2, tx: clampAxis(vw / 2 - W / 2, vw, W), ty: clampAxis(vh / 2 - H / 2, vh, H) };
        it.sr = { x: 0, y: 0, w: vw, h: vh };
        it.dim = false;
        it.scan = false;
      } else {
        const p = cue!.pad ?? (narrow ? 10 : 16);
        const scale = cue!.scale ?? 1.6;
        const req = Math.max(1, narrow ? (cue!.narrowScale ?? Math.min(scale, 1.5)) : scale);
        // A centered target needs room for the stamp on one side, so reserve it on both.
        const clearY = it.stamp ? Math.max(p, stampBox(it).bh + STAMP_GAP) : p;
        const s = Math.max(1, Math.min(req, (vw - 2 * p) / rect.w, (vh - 2 * clearY) / rect.h));
        const cx = rect.x + rect.w / 2;
        const cy = rect.y + rect.h / 2;
        const tx = clampAxis(vw / 2 - s * cx, vw, s * W);
        const ty = clampAxis(vh / 2 - s * cy, vh, s * H);
        it.pose = { s, cx, cy, tx, ty };
        it.sr = { x: tx + s * rect.x, y: ty + s * rect.y, w: s * rect.w, h: s * rect.h };
        it.dim = cue!.dim !== false;
        it.scan = cue!.scan === true && !!it.scanEl;
      }
    }
  }

  function place(el: HTMLElement, x: number, y: number) {
    el.style.transform = `translate(${x}px,${y}px)`;
  }

  function setCorners(it: Item, R: R, f: number, opacity: number) {
    const hw = R.w / 2 + RET_PAD;
    const hh = R.h / 2 + RET_PAD;
    const mx = R.x + R.w / 2;
    const my = R.y + R.h / 2;
    const spec: Array<[number, number]> = [[-1, -1], [1, -1], [-1, 1], [1, 1]];
    it.corners.forEach((c, i) => {
      const [sx, sy] = spec[i];
      const px = mx + sx * hw * f - (sx > 0 ? CORNER : 0);
      const py = my + sy * hh * f - (sy > 0 ? CORNER : 0);
      place(c, px, py);
      c.style.opacity = String(opacity);
      c.style.visibility = opacity > 0.001 ? 'visible' : 'hidden';
    });
  }

  function hide(...els: Array<HTMLElement | null>) {
    for (const el of els) if (el) { el.style.visibility = 'hidden'; el.style.opacity = '0'; }
  }

  function stampBox(it: Item): { bw: number; bh: number } {
    const w = it.sw * it.sk;
    const h = it.sh * it.sk;
    const rad = Math.abs(STAMP_REST_DEG) * Math.PI / 180;
    return { bw: w * Math.cos(rad) + h * Math.sin(rad), bh: w * Math.sin(rad) + h * Math.cos(rad) };
  }

  /** Rest center beside the target: the preferred side first, then the spot covering the least of it. */
  function stampRest(it: Item): { x: number; y: number } {
    const R = it.sr;
    const { bw, bh } = stampBox(it);
    const fitX = (x: number) => Math.min(Math.max(x, bw / 2), Math.max(bw / 2, vw - bw / 2));
    const fitY = (y: number) => Math.min(Math.max(y, bh / 2), Math.max(bh / 2, vh - bh / 2));
    const right = R.x + R.w - bw / 2;
    const left = R.x + bw / 2;
    const below = R.y + R.h + STAMP_GAP + bh / 2;
    const above = R.y - STAMP_GAP - bh / 2;
    const midY = R.y + R.h / 2;
    const sides: Array<[number, number]> = [
      [R.x + R.w + STAMP_GAP + bw / 2, midY],
      [R.x - STAMP_GAP - bw / 2, midY],
    ];
    const anchor = it.cue!.stamp!.anchor ?? 'br';
    const corners: Array<[number, number]> =
      anchor === 'tr' ? [[right, above], [right, below], [left, above], [left, below]]
      : anchor === 'bl' ? [[left, below], [left, above], [right, below], [right, above]]
      : [[right, below], [right, above], [left, below], [left, above]];
    let best = { x: 0, y: 0 };
    let least = Infinity;
    for (const [cx, cy] of [...corners, ...sides]) {
      const x = fitX(cx);
      const y = fitY(cy);
      const covered = Math.max(0, Math.min(x + bw / 2, R.x + R.w) - Math.max(x - bw / 2, R.x))
        * Math.max(0, Math.min(y + bh / 2, R.y + R.h) - Math.max(y - bh / 2, R.y));
      if (covered < least) { least = covered; best = { x, y }; }
    }
    return best;
  }

  // Chosen at the rest pose and carried with the target, so a stamp never hops sides mid-move.
  function stampCenter(it: Item, R: R): { x: number; y: number } {
    const rest = stampRest(it);
    return {
      x: rest.x + (R.x + R.w / 2) - (it.sr.x + it.sr.w / 2),
      y: rest.y + (R.y + R.h / 2) - (it.sr.y + it.sr.h / 2),
    };
  }

  function setStamp(it: Item, R: R, scaleMul: number, rot: number, opacity: number) {
    const el = it.stamp!;
    const c = stampCenter(it, R);
    el.style.transform = `translate(${c.x - it.sw / 2}px,${c.y - it.sh / 2}px) rotate(${rot}deg) scale(${it.sk * scaleMul})`;
    el.style.opacity = String(opacity);
    el.style.visibility = opacity > 0.001 ? 'visible' : 'hidden';
  }

  function render(frame: SceneFrame) {
    if (vw <= 0 || vh <= 0) return;
    const k = Math.min(items.length - 1, Math.max(0, frame.step));
    const u = clamp01(frame.stepProgress);
    const cur = items[k];
    const prev = k > 0 ? items[k - 1] : null;

    // camera
    const p0 = (prev ?? cur).pose;
    const p1 = cur.pose;
    const ce = power3InOut(win(u, BEATS.diveStart, BEATS.arrive));
    const s = Math.exp(lerp(Math.log(p0.s), Math.log(p1.s), ce));
    const cx = lerp(p0.cx, p1.cx, ce);
    const cy = lerp(p0.cy, p1.cy, ce);
    const tx = clampAxis(vw / 2 - s * cx, vw, s * W);
    const ty = clampAxis(vh / 2 - s * cy, vh, s * H);

    // impact on stamped cues, about the viewport center
    let m = 1;
    if (cur.stamp) {
      const land = cur.cue!.stamp!.land ?? BEATS.land;
      if (u > land && u < BEATS.settle) m = 1 + 0.025 * Math.sin(Math.PI * (u - land) / (BEATS.settle - land));
    }
    world.style.transform =
      `translate(${vw / 2 + m * (tx - vw / 2)}px,${vh / 2 + m * (ty - vh / 2)}px) scale(${s * m})`;

    const live = (it: Item): R => {
      const r = it.rect;
      return r ? { x: tx + s * r.x, y: ty + s * r.y, w: s * r.w, h: s * r.h } : it.sr;
    };
    const fadePrev = 1 - win(u, 0, 0.06);

    // dim with a travelling hole
    const dw = power2Out(win(u, BEATS.diveStart, 0.2));
    const hole = (r: R): R => ({ x: r.x - HOLE_PAD, y: r.y - HOLE_PAD, w: r.w + 2 * HOLE_PAD, h: r.h + 2 * HOLE_PAD });
    const prevDim = !!prev && prev.dim;
    let dimOpacity = 0;
    let hr: R | null = null;
    if (cur.dim && prevDim) { dimOpacity = 1; hr = hole(lerpRect(prev!.sr, cur.sr, ce)); }
    else if (cur.dim) { dimOpacity = dw; hr = hole(cur.sr); }
    else if (prevDim) { dimOpacity = 1 - dw; hr = hole(live(prev!)); }
    if (!reduced) {
      dimGroup.style.opacity = String(dimOpacity);
      dimGroup.style.visibility = dimOpacity > 0.001 ? 'visible' : 'hidden';
      if (hr) {
        const x0 = Math.max(0, hr.x);
        const y0 = Math.max(0, hr.y);
        const x1 = Math.min(vw, hr.x + hr.w);
        const y1 = Math.min(vh, hr.y + hr.h);
        const hw = Math.max(0, x1 - x0);
        const hh = Math.max(0, y1 - y0);
        panels[0].style.transform = `translate(0px,0px) scale(1,${y0 / vh})`;
        panels[1].style.transform = `translate(0px,${y0 + hh}px) scale(1,${Math.max(0, vh - y0 - hh) / vh})`;
        panels[2].style.transform = `translate(0px,${y0}px) scale(${x0 / vw},${hh / vh})`;
        panels[3].style.transform = `translate(${x0 + hw}px,${y0}px) scale(${Math.max(0, vw - x0 - hw) / vw},${hh / vh})`;
      }
    }

    // reticles, scan, trace and stamps
    for (const it of items) {
      const role = it === cur ? 'cur' : it === prev ? 'prev' : 'off';
      if (role === 'off') { hide(...it.corners, it.scanEl, it.traceEl, it.stamp); continue; }
      if (role === 'cur') {
        if (it.corners.length && it.rect) {
          const e = expoOut(win(u, BEATS.lock, BEATS.lock + 0.05));
          setCorners(it, it.sr, lerp(1.35, 1, e), e);
        }
        if (it.scanEl && it.traceEl && it.scan) {
          const w = win(u, BEATS.scanStart, BEATS.scanEnd);
          const R = it.sr;
          const on = u > BEATS.scanStart && u < BEATS.scanEnd;
          it.scanEl.style.visibility = on ? 'visible' : 'hidden';
          it.scanEl.style.opacity = on ? '1' : '0';
          it.scanEl.style.transform = `translate(${R.x}px,${R.y + w * R.h}px) scale(${R.w / vw},1)`;
          const tOn = u > BEATS.scanStart;
          it.traceEl.style.visibility = tOn ? 'visible' : 'hidden';
          it.traceEl.style.opacity = tOn ? '1' : '0';
          it.traceEl.style.transform = `translate(${Math.max(2, R.x - 8)}px,${R.y}px) scale(1,${(w * R.h) / vh})`;
        }
        if (it.stamp) {
          const land = it.cue!.stamp!.land ?? BEATS.land;
          const w = win(u, land - 0.06, land);
          const e = backOut(w);
          setStamp(it, it.sr, lerp(2.6, 1, e), lerp(-9, STAMP_REST_DEG, e), u < land - 0.06 ? 0 : Math.min(1, w / 0.4));
        }
      } else {
        const R = live(it);
        if (it.corners.length && it.rect) setCorners(it, R, 1, fadePrev);
        if (it.scanEl && it.traceEl && it.scan) {
          hide(it.scanEl);
          it.traceEl.style.visibility = fadePrev > 0.001 ? 'visible' : 'hidden';
          it.traceEl.style.opacity = String(fadePrev);
          it.traceEl.style.transform = `translate(${Math.max(2, R.x - 8)}px,${R.y}px) scale(1,${R.h / vh})`;
        }
        if (it.stamp) setStamp(it, R, 1, STAMP_REST_DEG, fadePrev);
      }
    }
  }

  function lerpRect(a: R, b: R, t: number): R {
    return { x: lerp(a.x, b.x, t), y: lerp(a.y, b.y, t), w: lerp(a.w, b.w, t), h: lerp(a.h, b.h, t) };
  }

  /** Reduced motion: no camera, one static reticle per marked target. */
  function renderStatic() {
    for (const it of items) {
      if (!it.corners.length || !it.rect) { hide(...it.corners); continue; }
      const r = it.rect;
      setCorners(it, { x: r.x + ox, y: r.y + oy, w: r.w, h: r.h }, 1, 1);
    }
  }

  function remeasure() {
    measure();
    if (reduced) renderStatic();
    else if (last) render(last);
  }

  measure();
  if (reduced) renderStatic();

  const ro = new ResizeObserver(remeasure);
  ro.observe(viewport);
  ro.observe(world);
  void document.fonts.ready.then(remeasure);
  world.querySelectorAll('img').forEach((img) => {
    if (!img.complete) img.decode().then(remeasure, () => {});
  });

  return {
    update(frame) {
      if (reduced) return;
      last = frame;
      render(frame);
    },
    resize: remeasure,
    at(step, beat) { return step + BEATS[beat]; },
  };
}
