import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import Lenis from 'lenis';
import { frameAt } from './frame';
import { SCENE_GROUND } from './grounds';
import type { SceneFrame, SceneHandle, SceneModule } from './types';

// Must run before mountScene, which creates a ScrollTrigger per scene.
gsap.registerPlugin(ScrollTrigger);

export interface Rendered {
  mod: SceneModule;
  el: HTMLElement;
  handle: SceneHandle;
  steps: HTMLElement[];
  trigger: ScrollTrigger;
  last: number;      // last progress sent to update, -1 before first call
  copyKey: string;   // last applied copy state
  frame: SceneFrame;
}

export const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
export const isNarrow = () => window.innerWidth <= 767;

export const rendered: Rendered[] = [];
let lenis: Lenis | null = null;
let pending: number | null = null;
const listeners: Array<() => void> = [];

export function onSync(cb: () => void) { listeners.push(cb); }

function buildSection(mod: SceneModule, first: boolean) {
  const steps = mod.steps();
  if (!steps.length) throw new Error('no steps');
  const el = document.createElement('section');
  el.id = mod.id;
  el.className = `scene scene-${mod.id}${reducedMotion ? ' is-reduced' : ''}`;
  el.dataset.scene = mod.id;
  el.dataset.ground = SCENE_GROUND[mod.id];
  el.tabIndex = -1;
  el.setAttribute('aria-labelledby', `${mod.id}-title`);
  el.style.setProperty('--scene-steps', String(steps.length));

  const stage = document.createElement('div');
  stage.className = 'scene__stage';
  const copy = document.createElement('div');
  copy.className = 'scene__copy';
  const title = document.createElement(first ? 'h1' : 'h2');
  title.id = `${mod.id}-title`;
  title.className = 'visually-hidden';
  title.textContent = mod.title;
  const ol = document.createElement('ol');
  ol.className = 'scene__steps';
  const stepEls = steps.map((s, i) => {
    const li = document.createElement('li');
    li.className = 'step';
    li.dataset.step = String(i);
    const h = document.createElement('h3');
    h.className = 'step__headline';
    h.textContent = s.headline;
    const p = document.createElement('p');
    p.className = 'step__sentence';
    p.textContent = s.sentence;
    const ul = document.createElement('ul');
    ul.className = 'step__callouts';
    for (const c of s.callouts) {
      const item = document.createElement('li');
      item.className = `callout callout--${c.kind}${c.verdict ? ` callout--${c.verdict}` : ''}`;
      item.textContent = c.text;
      ul.append(item);
    }
    li.append(h, p, ul);
    ol.append(li);
    return li;
  });
  copy.append(title, ol);
  const plate = document.createElement('div');
  plate.className = 'scene__plate';
  stage.append(copy, plate);
  el.append(stage);
  return { el, plate, stepEls };
}

/** Build and mount one scene; on any failure log and return false. */
export function mountScene(host: HTMLElement, mod: SceneModule, first: boolean): boolean {
  let el: HTMLElement | null = null;
  try {
    const built = buildSection(mod, first);
    el = built.el;
    host.append(el);
    const handle = mod.mount({ root: el, plate: built.plate, reducedMotion, isNarrow });
    const trigger = ScrollTrigger.create({ trigger: el, start: 'top top', end: 'bottom bottom' });
    const r: Rendered = {
      mod, el, handle, steps: built.stepEls, trigger, last: -1, copyKey: '',
      frame: { progress: 0, step: 0, stepProgress: 0 },
    };
    rendered.push(r);
    if (reducedMotion) {
      handle.update({ progress: 1, step: built.stepEls.length - 1, stepProgress: 1 });
      r.last = 1;
    }
    return true;
  } catch (err) {
    console.error(`[leash] scene ${mod.id} failed`, err);
    el?.remove();
    return false;
  }
}

function applyCopy(r: Rendered, f: SceneFrame) {
  const n = r.steps.length;
  const sp = Math.round(f.stepProgress * 100);
  const key = `${f.step}:${sp}`;
  if (key === r.copyKey) return;
  r.copyKey = key;
  r.steps.forEach((li, i) => {
    if (i !== f.step) {
      if (li.style.visibility !== 'hidden') {
        li.style.visibility = 'hidden';
        li.style.opacity = '0';
        li.setAttribute('aria-hidden', 'true');
      }
      return;
    }
    let o = 1;
    if (f.step > 0 && f.stepProgress < 0.12) o = f.stepProgress / 0.12;
    else if (f.step < n - 1 && f.stepProgress > 0.92) o = (1 - f.stepProgress) / 0.08;
    li.style.visibility = 'visible';
    li.style.opacity = String(Math.min(1, Math.max(0, o)));
    li.removeAttribute('aria-hidden');
  });
}

export function currentIndex(): number {
  const y = window.scrollY + 1;
  let idx = 0;
  rendered.forEach((r, i) => { if (r.trigger.start <= y) idx = i; });
  return idx;
}

export function pageProgress(): number {
  const max = document.documentElement.scrollHeight - window.innerHeight;
  return max > 0 ? Math.min(1, Math.max(0, window.scrollY / max)) : 0;
}

export function syncAll(force = false) {
  const y = window.scrollY;
  for (const r of rendered) {
    const f = frameAt(y, r.trigger.start, r.trigger.end, r.steps.length);
    r.frame = f;
    if (reducedMotion) continue;
    applyCopy(r, f);
    if (force || f.progress !== r.last) {
      r.last = f.progress;
      try { r.handle.update(f); } catch (err) { console.error(`[leash] scene ${r.mod.id} update failed`, err); }
    }
  }
  for (const cb of listeners) cb();
}

/**
 * Stops: one per step of each rendered scene, at the step's midpoint, so key content is legible.
 * Under reduced motion there is one stop per scene, at its start.
 */
export interface Stop { scene: number; step: number; y: number }
export const stops: Stop[] = [];
let curStop = 0;
let ready = false;
const STORE_KEY = 'leash.stop';

function computeStops() {
  stops.length = 0;
  rendered.forEach((r, scene) => {
    const n = r.steps.length;
    const s = r.trigger.start;
    const e = r.trigger.end;
    if (reducedMotion) { stops.push({ scene, step: 0, y: Math.round(s) }); return; }
    for (let step = 0; step < n; step++) stops.push({ scene, step, y: Math.round(s + ((step + 0.5) / n) * (e - s)) });
  });
}

function nearestStop(): number {
  const y = window.scrollY;
  let best = 0;
  stops.forEach((st, i) => { if (Math.abs(st.y - y) < Math.abs(stops[best].y - y)) best = i; });
  return best;
}

function remember() {
  try { sessionStorage.setItem(STORE_KEY, String(curStop)); } catch { /* storage unavailable */ }
}

/** Move the playhead to the current stop with no animation. */
function snap() {
  const y = stops[curStop]?.y;
  if (y === undefined) return;
  if (lenis) lenis.scrollTo(y, { immediate: true, force: true });
  else window.scrollTo({ top: y, behavior: 'instant' as ScrollBehavior });
}

/** Go to a stop. Short programmatic tween in normal motion, instant under reduced motion. */
export function goToStop(index: number, immediate = false) {
  if (!stops.length) return;
  const i = Math.min(stops.length - 1, Math.max(0, index));
  const y = stops[i].y;
  curStop = i;
  remember();
  if (reducedMotion || immediate || !lenis) {
    pending = null;
    window.scrollTo({ top: y, behavior: 'instant' as ScrollBehavior });
    return;
  }
  pending = i;
  const dist = Math.abs(y - window.scrollY);
  const duration = 0.7 + Math.min(0.5, dist / (window.innerHeight * 12));
  lenis.scrollTo(y, { duration, force: true, onComplete: () => { if (pending === i) pending = null; } });
}

/** Go to the first stop of a scene (rail and menu links). */
export function goTo(sceneIndex: number, immediate = false) {
  const i = stops.findIndex((s) => s.scene === sceneIndex);
  if (i >= 0) goToStop(i, immediate);
}

/** Key presses advance from the pending target, else from the stop nearest the playhead. */
export function stopIndex(): number { return pending ?? nearestStop(); }
export function stopCount(): number { return stops.length; }
/** First stop of the scene before or after the scene of stop `from`. */
export function sceneNeighbourStop(from: number, dir: 1 | -1): number {
  const scene = (stops[from]?.scene ?? 0) + dir;
  if (scene < 0 || scene >= rendered.length) return from;
  return Math.max(0, stops.findIndex((s) => s.scene === scene));
}

export function focusScene(index: number) {
  rendered[index]?.el.focus({ preventScroll: true });
}

export function startRuntime() {
  ScrollTrigger.config({ ignoreMobileResize: true });

  window.matchMedia('(prefers-reduced-motion: reduce)').addEventListener('change', () => window.location.reload());

  if (reducedMotion) {
    document.documentElement.classList.add('is-reduced');
  } else {
    // Scroll position is the internal playhead and is moved only by code, so the user cannot scroll.
    lenis = new Lenis({ virtualScroll: () => false });
    lenis.on('scroll', () => { ScrollTrigger.update(); syncAll(); });
    gsap.ticker.add((t) => lenis?.raf(t * 1000));
    gsap.ticker.lagSmoothing(0);
    document.documentElement.classList.add('is-locked'); // hides the scrollbar, blocks touch panning
    const block = (e: Event) => e.preventDefault();
    window.addEventListener('wheel', block, { passive: false });
    window.addEventListener('touchmove', block, { passive: false });
    window.addEventListener('mousedown', (e) => { if (e.button === 1) e.preventDefault(); }); // middle-click autoscroll
    window.addEventListener('auxclick', (e) => { if (e.button === 1) e.preventDefault(); });
    try { history.scrollRestoration = 'manual'; } catch { /* ignore */ }
  }

  window.addEventListener('scroll', () => syncAll(), { passive: true });
  ScrollTrigger.addEventListener('refresh', () => {
    computeStops();
    if (ready && !reducedMotion) snap();
    syncAll();
  });

  let lastWidth = window.innerWidth;
  let timer: number | undefined;
  window.addEventListener('resize', () => {
    if (window.innerWidth === lastWidth) return;
    lastWidth = window.innerWidth;
    window.clearTimeout(timer);
    timer = window.setTimeout(() => {
      for (const r of rendered) {
        try { r.handle.resize?.(); } catch (err) { console.error(`[leash] scene ${r.mod.id} resize failed`, err); }
      }
      ScrollTrigger.refresh();
      syncAll(true);
    }, 150);
  });

  ScrollTrigger.refresh();
  computeStops();
  // Land on the first stop, or the first stop of a valid hash's scene. A reload snaps back to the
  // stop it was on. Reduced motion keeps ordinary page scrolling and the browser's own restoration.
  if (!reducedMotion) {
    const nav = performance.getEntriesByType('navigation')[0] as PerformanceNavigationTiming | undefined;
    const id = decodeURIComponent(window.location.hash.slice(1));
    const hashIdx = rendered.findIndex((r) => r.mod.id === id);
    let stored = -1;
    try { stored = Number(sessionStorage.getItem(STORE_KEY) ?? -1); } catch { /* ignore */ }
    if ((nav?.type === 'reload' || nav?.type === 'back_forward') && Number.isInteger(stored) && stored >= 0 && stored < stops.length) {
      curStop = stored;
    } else if (id && hashIdx >= 0) {
      curStop = Math.max(0, stops.findIndex((s) => s.scene === hashIdx));
    } else {
      curStop = 0;
    }
    remember();
    snap();
  }
  ready = true;
  syncAll(true);
}
