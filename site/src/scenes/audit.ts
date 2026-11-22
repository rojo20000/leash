import gsap from 'gsap';
import { fact, quote } from '../shell/content-access';
import { createInspection, verdictBadge } from '../shell/emphasis';
import type { SceneContext, SceneFrame, SceneHandle, SceneModule, StepCopy } from '../shell/types';
import './audit.css';

const STEPS = 4;
const ROWS = 28;
const EDITED = 12; // zero-indexed: line 12 is the thirteenth row
const W_ROW = 3;
const W_EDITED = 20;
const W_LINK = 2;
const BAR = 0.04; // tracer bar height as a fraction of the chain

function steps(): StepCopy[] {
  const tampered = fact('audit', 'Tampered result').split(' ');
  const firstBad = tampered.find((t) => t.startsWith('first_bad=')) ?? tampered[1];
  const okFalse = tampered.find((t) => t.startsWith('ok=')) ?? tampered[0];
  return [
    {
      headline: 'Every entry is chained',
      sentence: 'Each audit entry is linked to the one before it by a SHA-256 hash.',
      callouts: [
        { text: fact('audit', 'Chain'), kind: 'name' },
        { text: 'Rust core', kind: 'name' },
      ],
    },
    {
      headline: 'The clean log verifies',
      sentence: 'Verification passes on the untouched log.',
      callouts: [
        { text: fact('audit', 'Clean result'), kind: 'code', verdict: 'allow' },
        { text: 'verify_log', kind: 'code' },
      ],
    },
    {
      headline: 'Someone edits one line',
      sentence: 'Line numbers count from zero, so line 12 is the blocked injection read at call 9.',
      callouts: [
        { text: fact('audit', 'Edited line'), kind: 'code' },
        { text: fact('audit', 'Edit made'), kind: 'code' },
        { text: fact('policy', 'Reason code injection'), kind: 'code', verdict: 'block' },
      ],
    },
    {
      headline: 'Verification fails',
      sentence: 'The edited entry no longer matches its hash, so verification fails at line 12.',
      callouts: [
        { text: fact('audit', 'Failure reason'), kind: 'code', verdict: 'block' },
        { text: firstBad, kind: 'code' },
        { text: okFalse, kind: 'code' },
      ],
    },
  ];
}

function el(parent: Element, tag: string, cls: string, text?: string): HTMLElement {
  const n = document.createElement(tag);
  n.className = cls;
  if (text !== undefined) n.textContent = text;
  parent.appendChild(n);
  return n;
}

function mount(ctx: SceneContext): SceneHandle {
  const { plate } = ctx;
  plate.textContent = '';

  // "read_document BLOCK INJECTION_DETECTED" from the pipeline quote, then the edited form.
  const before = quote('pipeline', '9 read_document').replace(/^\s*9\s+/, '').replace(/\s+/g, ' ').trim().split(' ');
  const edit = fact('audit', 'Edit made').split(' -> ');
  const after = before.map((t) => (t === edit[0].toUpperCase() ? edit[1] : t));
  const [tool, , code] = before;
  const beforeWord = before[1];
  const afterWord = after[1];

  const view = el(plate, 'div', 'audit-view');
  const world = el(view, 'div', 'audit-world');
  const wrap = el(world, 'div', 'audit-wrap');
  const chain = el(wrap, 'div', 'audit-chain');
  const rows: HTMLElement[] = [];
  const litLayers: HTMLElement[] = [];
  const linkScale: HTMLElement[] = [];
  const halves: HTMLElement[] = [];
  const badLayers: HTMLElement[] = [];
  let editedRow!: HTMLElement;
  let hi!: HTMLElement;
  let beforeLayer!: HTMLElement;
  let afterLayer!: HTMLElement;
  let scanGlow!: HTMLElement;

  const weights: number[] = [];
  for (let i = 0; i < ROWS; i++) {
    const edited = i === EDITED;
    const entry = el(chain, 'div', 'audit-entry');
    entry.style.flexGrow = String(edited ? W_EDITED : W_ROW);
    const row = el(entry, 'div', edited ? 'audit-row audit-row--edited' : 'audit-row');
    rows.push(row);
    weights.push(edited ? W_EDITED : W_ROW);
    if (edited) {
      editedRow = row;
      hi = el(row, 'span', 'audit-hi');
      scanGlow = el(row, 'span', 'audit-hot');
      const l1 = el(row, 'div', 'audit-line1');
      el(l1, 'span', 'audit-lineno machine', fact('audit', 'Edited line'));
      el(l1, 'span', 'audit-tool machine', tool);
      const l2 = el(row, 'div', 'audit-line2');
      const mk = (layerCls: string, form: 'block' | 'allow', word: string) => {
        const layer = el(l2, 'span', `audit-layer-text ${layerCls}`);
        const reg = el(layer, 'span', 'audit-reg');
        reg.appendChild(verdictBadge(form, word));
        el(layer, 'span', 'audit-code machine', code);
        return layer;
      };
      beforeLayer = mk('audit-layer-text--before', 'block', beforeWord);
      afterLayer = mk('audit-layer-text--after', 'allow', afterWord);
    }
    if (i < ROWS - 1) {
      const link = el(chain, 'div', 'audit-link');
      link.style.flexGrow = String(W_LINK);
      weights.push(W_LINK);
      const scaler = el(link, 'div', 'audit-link-scale');
      for (const half of ['a', 'b']) {
        const h = el(scaler, 'div', `audit-half audit-half--${half}`);
        el(h, 'span', 'audit-layer audit-layer--base');
        const l = el(h, 'span', 'audit-layer audit-layer--lit');
        const b = el(h, 'span', 'audit-layer audit-layer--bad');
        litLayers.push(l);
        if (i === EDITED - 1) { halves.push(h); badLayers.push(b); }
      }
      linkScale.push(scaler);
    }
  }

  // Stamp slot over the blank rows well below line 12.
  const slot = el(chain, 'div', 'audit-slot');
  const tracer = el(chain, 'div', 'audit-tracer');
  el(tracer, 'div', 'audit-tracer-bar');

  const side = el(wrap, 'div', 'audit-side');
  el(side, 'p', 'audit-caption', 'Schematic of the 28-entry log');
  const quotes = el(side, 'div', 'audit-quotes');
  const cleanQ = el(quotes, 'p', 'audit-quote machine', quote('audit', 'clean log'));
  // Fixed strip outside the camera, so the zoom and stamp never push it out of the plate.
  const strip = el(plate, 'div', 'audit-strip');
  const failQ = el(strip, 'p', 'audit-fail machine', quote('audit', 'after editing line 12'));

  // Fractions along the chain, from fixed flex weights (no measurement).
  const total = weights.reduce((a, b) => a + b, 0);
  const centres: number[] = [];
  let acc = 0;
  for (const w of weights) { centres.push((acc + w / 2) / total); acc += w; }
  const rowCentre = (i: number) => centres[i * 2];
  const linkCentre = (j: number) => centres[j * 2 + 1];
  const yPct = (f: number) => ((f - BAR / 2) / (1 - BAR)) * 100;
  const clamp = (v: number) => Math.min(1, Math.max(0, v));

  const tl = gsap.timeline({ paused: true, defaults: { ease: 'none' } });
  tl.to({}, { duration: STEPS }, 0);

  const kit = createInspection({
    ctx,
    world,
    viewport: view,
    steps: STEPS,
    cues: [
      { step: 0, target: null },
      { step: 1, target: slot, scale: 1, dim: false, reticle: false, stamp: { text: fact('audit', 'Clean result'), form: 'allow', anchor: 'tr' } },
      { step: 2, target: editedRow, scale: 2.6, scan: true },
      {
        step: 3, target: editedRow, scale: 2.4, pad: 28, scan: true, dim: false,
        stamp: { text: fact('audit', 'Failure reason'), form: 'alert', anchor: 'br' },
      },
    ],
  });
  const at = kit.at;

  // Step 1 (lead: the chain). It draws down fast, then slows: eased spacing, not an even stagger.
  const drawEnd = at(0, 'settle') - 0.04;
  rows.forEach((r, i) => {
    const t = 0.02 + Math.pow(i / ROWS, 0.62) * (drawEnd - 0.12);
    tl.fromTo(r, { opacity: 0 }, { opacity: 1, duration: 0.07 }, t);
  });
  linkScale.forEach((s, j) => {
    const t = 0.04 + Math.pow(j / ROWS, 0.62) * (drawEnd - 0.12);
    tl.fromTo(s, { scaleY: 0 }, { scaleY: 1, duration: 0.07, transformOrigin: '50% 0%' }, t);
  });

  // Step 2 (lead: the tracer). Links stay lit behind it; the allow stamp lands at the end.
  const t0 = at(1, 'diveStart');
  const tDur = at(1, 'scanEnd') - t0;
  tl.fromTo(tracer, { opacity: 0, yPercent: 0 }, { opacity: 1, yPercent: 0, duration: 0.03 }, t0);
  tl.to(tracer, { yPercent: 100, duration: tDur }, t0);
  const litPairs: HTMLElement[][] = linkScale.map((_, j) => [litLayers[j * 2], litLayers[j * 2 + 1]]);
  litPairs.forEach((pair, j) => {
    const f = clamp(yPct(linkCentre(j)) / 100);
    tl.fromTo(pair, { opacity: 0 }, { opacity: 1, duration: 0.03 }, t0 + tDur * f);
  });
  tl.fromTo(cleanQ, { opacity: 0 }, { opacity: 1, duration: 0.06 }, at(1, 'land'));

  // Step 3 (lead: the edited row). The scan crosses it, then BLOCK crossfades to allow from lock.
  tl.to(tracer, { opacity: 0, duration: 0.08 }, at(2, 'diveStart'));
  tl.fromTo(hi, { opacity: 0 }, { opacity: 1, duration: 0.1 }, at(2, 'arrive'));
  tl.fromTo(afterLayer, { opacity: 0 }, { opacity: 1, duration: at(2, 'settle') - at(2, 'lock') }, at(2, 'lock'));
  tl.to(beforeLayer, { opacity: 0, duration: at(2, 'settle') - at(2, 'lock') }, at(2, 'lock'));

  // Step 4 (lead: the failure). Tracer descends again and stops at line 12; the link splits at the stamp.
  tl.to(cleanQ, { opacity: 0, duration: 0.06 }, at(3, 'diveStart'));
  tl.to(litLayers, { opacity: 0, duration: 0.05 }, at(3, 'diveStart'));
  tl.set(tracer, { yPercent: 0, opacity: 1 }, at(3, 'diveStart'));
  const s0 = at(3, 'diveStart') + 0.04;
  const sDur = at(3, 'lock') - s0;
  const stopY = yPct(rowCentre(EDITED));
  tl.to(tracer, { yPercent: stopY, duration: sDur }, s0);
  for (let j = 0; j < EDITED - 1; j++) {
    const f = clamp(yPct(linkCentre(j)) / stopY);
    tl.to(litPairs[j], { opacity: 1, duration: 0.03 }, s0 + sDur * f);
  }
  const land = at(3, 'land');
  tl.to(halves[0], { xPercent: -300, yPercent: -30, rotation: -34, transformOrigin: '50% 100%', duration: 0.06 }, land);
  tl.to(halves[1], { xPercent: 300, yPercent: 30, rotation: 34, transformOrigin: '50% 0%', duration: 0.06 }, land);
  tl.to(badLayers, { opacity: 1, duration: 0.06 }, land);
  tl.fromTo(scanGlow, { opacity: 0 }, { opacity: 1, duration: 0.06 }, land);
  tl.fromTo(failQ, { opacity: 0 }, { opacity: 1, duration: 0.06 }, at(3, 'diveStart'));
  gsap.set(badLayers, { opacity: 0 });

  return {
    update(f: SceneFrame) {
      tl.progress(f.progress);
      kit.update(f);
    },
    resize() {
      kit.resize();
    },
  };
}

const scene: SceneModule = { id: 'audit', title: 'Audit log', steps, mount };
export default scene;
