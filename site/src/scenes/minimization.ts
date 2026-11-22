import gsap from 'gsap';
import { createInspection } from '../shell/emphasis';
import { fact, table } from '../shell/content-access';
import type { SceneContext, SceneFrame, SceneHandle, SceneModule, StepCopy } from '../shell/types';
import './minimization.css';

const STEPS = 4;

function steps(): StepCopy[] {
  return [
    {
      headline: 'Only what the task needs',
      sentence: fact('minimization', 'Role scope'),
      callouts: [
        { text: fact('minimization', 'Method'), kind: 'name' },
        { text: 'role scope', kind: 'name' },
      ],
    },
    {
      headline: 'The value goes, the type stays',
      sentence: fact('minimization', 'Redaction'),
      callouts: [
        { text: 'SSN', kind: 'code' },
        { text: 'MRN', kind: 'code' },
        { text: 'DOB', kind: 'code' },
      ],
    },
    {
      headline: 'Presidio follows the pre-scan',
      sentence: 'Presidio runs after the Rust pre-scan, and fields the role does not need are dropped.',
      callouts: [
        { text: 'Rust pre-scan', kind: 'name' },
        { text: 'Presidio', kind: 'name' },
      ],
    },
    {
      headline: 'Perfect on templated notes',
      sentence: 'The evaluation is probably easy, because it uses templated notes.',
      callouts: [
        { text: 'precision ' + fact('minimization', 'Precision'), kind: 'figure' },
        { text: 'recall ' + fact('minimization', 'Recall'), kind: 'figure' },
        { text: fact('minimization', 'n_spans') + ' spans', kind: 'figure' },
        { text: fact('minimization', 'n_notes') + ' notes', kind: 'figure' },
      ],
    },
  ];
}

function el(cls: string, text?: string, tag = 'div'): HTMLElement {
  const n = document.createElement(tag);
  n.className = cls;
  if (text !== undefined) n.textContent = text;
  return n;
}

/** A number is a blank bar (flex weight), a string is a span kind. `drop` rows are non-identifier bars. */
interface Row { segs: (number | string)[]; drop?: boolean; head?: boolean }
const ROWS: Row[] = [
  { segs: [34], head: true },
  { segs: [18, 'SSN', 26] },
  { segs: [60, 20], drop: true },
  { segs: [12, 'MRN', 40] },
  { segs: [70] },
  { segs: ['DOB', 34, 14] },
  { segs: [44, 30], drop: true },
  { segs: [26, 'EMAIL'] },
  { segs: ['PHONE', 40] },
  { segs: [38, 22], drop: true },
];
// Flip order across step 2.
const FLIP = ['SSN', 'MRN', 'DOB', 'EMAIL', 'PHONE'];

function mount(ctx: SceneContext): SceneHandle {
  const { plate } = ctx;
  const kinds = table('minimization', 'minimization-by-kind');
  const known = new Set(kinds.rows.map((r) => r[0]));

  const world = el('minimization-world stock-label peel');

  const noteInner = el('minimization-note-inner');
  const spanEls: Record<string, HTMLElement> = {};
  const dark: Record<string, HTMLElement> = {};
  const tag: Record<string, HTMLElement> = {};
  const dropRows: HTMLElement[] = [];
  ROWS.forEach((row) => {
    const r = el('minimization-row' + (row.head ? ' minimization-row--head' : ''));
    row.segs.forEach((s) => {
      if (typeof s === 'number') {
        const b = el('minimization-bar');
        b.style.flexGrow = String(s);
        r.append(b);
      } else if (known.has(s)) {
        const span = el('minimization-span');
        const bar = el('minimization-span-bar machine', s);
        const out = el('minimization-span-tag machine', s);
        span.append(bar, out);
        spanEls[s] = span;
        dark[s] = bar;
        tag[s] = out;
        r.append(span);
      }
    });
    if (row.drop) dropRows.push(r);
    noteInner.append(r);
  });
  const passWrap = el('minimization-pass');
  passWrap.append(el('minimization-pass-line'));
  noteInner.append(passWrap);

  const stub = el('minimization-stub');
  stub.append(el('minimization-stub-rule micro-rule'), el('minimization-stub-code blank-barcode'), el('minimization-stub-rule micro-rule'));

  const tableWrap = el('minimization-table');
  const tbl = document.createElement('table');
  tbl.className = 'minimization-tbl';
  const head = document.createElement('tr');
  kinds.columns.forEach((c) => {
    const th = document.createElement('th');
    th.textContent = c;
    head.append(th);
  });
  tbl.append(head);
  kinds.rows.forEach((r) => {
    const tr = document.createElement('tr');
    r.forEach((c) => {
      const td = document.createElement('td');
      td.textContent = c;
      td.className = 'machine';
      tr.append(td);
    });
    tbl.append(tr);
  });
  tableWrap.append(tbl);

  const side = el('minimization-side');
  side.append(stub, tableWrap);
  world.append(noteInner, el('minimization-perf perf-y'), side);
  plate.append(world);

  const kit = createInspection({
    ctx,
    world,
    steps: STEPS,
    cues: [
      { step: 0, target: null },
      { step: 1, target: spanEls['SSN'] ?? null, scale: 3.0, scan: true },
      { step: 2, target: noteInner, scale: 1.35 },
      { step: 3, target: tableWrap, scale: 1.3 },
    ],
  });

  if (ctx.reducedMotion) Object.values(dark).forEach((d) => d.remove()); // hidden layer is only a placeholder in the static view
  const flip = FLIP.filter((k) => dark[k] && dark[k].isConnected);

  gsap.set(Object.values(tag), { opacity: 0 });
  gsap.set(passWrap, { yPercent: 0 });
  gsap.set(passWrap.firstElementChild, { scaleX: 0, transformOrigin: '0% 50%' });
  gsap.set(tableWrap, { opacity: 0 });

  const tl = gsap.timeline({ paused: true, defaults: { ease: 'none' } });
  tl.to({}, { duration: STEPS }, 0);
  const fx = (target: gsap.TweenTarget, from: gsap.TweenVars, to: gsap.TweenVars, pos: number, dur: number) =>
    tl.fromTo(target, from, { ...to, duration: dur, immediateRender: false }, pos);
  const at = kit.at;

  // Step 2: SSN flips first at lock, then the other four with shrinking gaps, all done by settle.
  const flipAt = [at(1, 'lock'), 1.33, 1.37, 1.4, 1.42];
  flip.forEach((k, i) => {
    fx(dark[k], { opacity: 1 }, { opacity: 0 }, flipAt[i], 0.06);
    fx(tag[k], { opacity: 0 }, { opacity: 1 }, flipAt[i], 0.06);
  });

  // Step 3: the pass line sweeps; non-identifier rows drop away with shrinking gaps.
  fx(passWrap.firstElementChild, { scaleX: 0 }, { scaleX: 1 }, 2.04, 0.14);
  fx(passWrap, { yPercent: 0 }, { yPercent: 98 }, 2.18, 0.26);
  const dropAt = [2.26, 2.34, 2.4];
  dropRows.forEach((r, i) => fx(r, { opacity: 1, yPercent: 0 }, { opacity: 0, yPercent: 50 }, dropAt[i] ?? 2.4, 0.07));

  // Step 4: table replaces the blank stub beside the finished note.
  fx(stub, { opacity: 1 }, { opacity: 0 }, 3.05, 0.2);
  fx(tableWrap, { opacity: 0 }, { opacity: 1 }, 3.05, 0.2);

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

const scene: SceneModule = { id: 'minimization', title: 'Minimization', steps, mount };
export default scene;
