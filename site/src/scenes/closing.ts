import gsap from 'gsap';
import { fact } from '../shell/content-access';
import { createInspection } from '../shell/emphasis';
import type { InspectCue } from '../shell/emphasis';
import type { SceneContext, SceneFrame, SceneHandle, SceneModule, StepCopy } from '../shell/types';
import './closing.css';

const STEPS = 6;

function steps(): StepCopy[] {
  return [
    {
      headline: 'What this does not prove',
      sentence: 'Leash is a prototype, and these are its known limits.',
      callouts: [
        { text: '40 labelled cases', kind: 'figure' },
        { text: 'combined holdout recall 0.333', kind: 'figure' },
      ],
    },
    {
      headline: 'The live system varies',
      sentence: 'The scripted replay is the demo of record.',
      callouts: [
        { text: '1 of 3 unprotected runs', kind: 'figure' },
        { text: 'HTTP 429', kind: 'code' },
      ],
    },
    {
      headline: 'Two scores need context',
      sentence: 'Part of the anomaly result comes from a guard, and the minimization test is probably easy.',
      callouts: [
        { text: 'deterministic guard', kind: 'name' },
        { text: 'templated notes', kind: 'name' },
      ],
    },
    {
      headline: 'A prototype, not a compliance claim',
      sentence: 'It uses synthetic data, one role and one policy.',
      callouts: [
        { text: 'local fallbacks', kind: 'name' },
        { text: 'synthetic data', kind: 'name' },
        { text: 'one role, one policy', kind: 'name' },
      ],
    },
    {
      headline: 'Clinic Assistant integration limits',
      sentence: 'Integrated mode is off by default and outside make check.',
      callouts: [
        { text: 'leash.enabled: false', kind: 'code' },
        { text: 'Clinic Assistant', kind: 'name' },
      ],
    },
    {
      headline: 'Run it yourself',
      sentence: 'make demo runs the same referral task twice, with no key and no network.',
      callouts: [
        { text: 'make demo', kind: 'code' },
        { text: fact('closing', 'Tested on'), kind: 'name' },
        { text: fact('closing', 'Rust fallback'), kind: 'name' },
      ],
    },
  ];
}

function el<K extends keyof HTMLElementTagNameMap>(tag: K, cls?: string, text?: string): HTMLElementTagNameMap[K] {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

/** A limitation paragraph: the full value verbatim, first sentence in heavier weight. */
function limit(label: string): HTMLElement {
  const value = fact('closing', label);
  const p = el('p', 'closing-limit');
  const cut = value.indexOf('. ');
  if (cut > 0) {
    p.appendChild(el('strong', 'closing-lead', value.slice(0, cut + 1)));
    p.appendChild(document.createTextNode(value.slice(cut + 1)));
  } else {
    p.textContent = value;
  }
  return p;
}

function mount(ctx: SceneContext): SceneHandle {
  const { plate } = ctx;
  const world = el('div', 'closing-world');
  plate.appendChild(world);
  world.appendChild(el('div', 'perf-x closing-perf'));
  world.appendChild(el('span', 'reg-mark closing-reg'));

  const board = el('div', 'closing-board');
  world.appendChild(board);
  const layers: HTMLElement[] = [];
  const add = (...children: HTMLElement[]) => {
    const l = el('div', 'closing-layer');
    children.forEach((c) => l.appendChild(c));
    board.appendChild(l);
    layers.push(l);
    return l;
  };

  const p1 = limit('Limitation: Small Nemotron eval');
  add(p1);
  const p2 = limit('Limitation: Live agent');
  add(p2, limit('Limitation: Rate limits'));
  const p3 = limit('Limitation: Anomaly model');
  add(p3, limit('Limitation: Minimization eval'));
  const p4a = limit('Limitation: Latency figures');
  const p4 = limit('Limitation: Prototype');
  add(p4a, p4);

  const c1 = limit('Clinic limit role');
  add(c1, limit('Clinic limit model'), limit('Clinic limit approval'));

  const team = el('p', 'closing-limit');
  team.appendChild(el('strong', 'closing-lead', 'Team. '));
  team.appendChild(document.createTextNode(fact('closing', 'Team')));
  const prereq = el('p', 'closing-limit');
  prereq.appendChild(el('strong', 'closing-lead', 'Prerequisites. '));
  prereq.appendChild(document.createTextNode(fact('closing', 'Prerequisites')));
  const pre = el(
    'pre',
    'machine closing-commands',
    [1, 2, 3, 4, 5].map((n) => fact('closing', `Run step ${n}`)).join('\n'),
  );
  const last = add(team, prereq, pre);
  last.appendChild(el('div', 'blank-barcode closing-barcode'));

  const tl = gsap.timeline({ paused: true, defaults: { ease: 'none' } });
  tl.to({}, { duration: STEPS }, 0);

  // Targets are whole layers, so zoom can never push a limitation past the plate.
  const cues: InspectCue[] = layers.map((target, step) => (
    step === STEPS - 1
      ? { step, target, scale: 1.15, scan: true }
      : { step, target, scale: 1.2, dim: false }
  ));
  const kit = createInspection({ ctx, world, steps: STEPS, cues });

  // The label swaps one layer per step, as a crossfade that is whole before the midpoint.
  layers.forEach((layerEl, i) => {
    if (i === 0) gsap.set(layerEl, { opacity: 1 });
    else tl.fromTo(layerEl, { opacity: 0 }, { opacity: 1, duration: 0.16 }, i + 0.04);
    if (i < layers.length - 1) tl.to(layerEl, { opacity: 0, duration: 0.12 }, i + 1);
  });

  return {
    update(frame: SceneFrame) {
      tl.progress(frame.progress);
      kit.update(frame);
    },
    resize() {
      kit.resize();
    },
  };
}

const scene: SceneModule = { id: 'closing', title: 'Limits and team', steps, mount };
export default scene;
