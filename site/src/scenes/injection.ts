import gsap from 'gsap';
import { createInspection, verdictBadge } from '../shell/emphasis';
import { fact, quote, table } from '../shell/content-access';
import type { SceneContext, SceneFrame, SceneHandle, SceneModule, StepCopy } from '../shell/types';
import './injection.css';

const STEPS = 5;

function combinedHoldoutRecall(): string {
  const t = table('injection', 'injection-round-5');
  const si = t.columns.indexOf('split');
  const di = t.columns.indexOf('detector');
  const ri = t.columns.indexOf('recall');
  const row = t.rows.find((r) => r[si] === 'holdout' && r[di] === 'combined');
  if (!row) throw new Error('injection holdout combined row missing');
  return row[ri];
}

function steps(): StepCopy[] {
  return [
    {
      headline: 'Three detectors read each document',
      sentence: 'Each document read passes three injection detectors.',
      callouts: [
        { text: fact('injection', 'Detector 1'), kind: 'name' },
        { text: fact('injection', 'Detector 2'), kind: 'name' },
        { text: fact('injection', 'Detector 3'), kind: 'name' },
      ],
    },
    {
      headline: 'Only TF-IDF can block',
      sentence: fact('injection', 'Who can block'),
      callouts: [
        { text: fact('injection', 'Block code'), kind: 'code', verdict: 'block' },
        { text: fact('injection', 'Escalate code'), kind: 'code', verdict: 'hold' },
      ],
    },
    {
      headline: 'It stopped the poisoned referral',
      sentence: 'In the protected run, the poisoned document read was blocked at call 9.',
      callouts: [
        { text: fact('injection', 'Poisoned read score'), kind: 'figure' },
        { text: 'threshold ' + fact('injection', 'Threshold'), kind: 'figure' },
        { text: fact('injection', 'Block code'), kind: 'code', verdict: 'block' },
      ],
    },
    {
      headline: 'Measured on held-out text',
      sentence:
        'The classifier raised no false positives on the hard negatives, benign notes with benign imperatives.',
      callouts: [
        { text: 'precision ' + fact('injection', 'Precision'), kind: 'figure' },
        { text: 'recall ' + fact('injection', 'Recall'), kind: 'figure' },
        { text: 'F1 ' + fact('injection', 'F1'), kind: 'figure' },
        {
          text: 'hard-negative false positives ' + fact('injection', 'hard_negative_false_positives'),
          kind: 'figure',
        },
      ],
    },
    {
      headline: 'What it still misses',
      sentence: fact('injection', 'Holdout miss'),
      callouts: [
        { text: 'combined holdout recall ' + combinedHoldoutRecall(), kind: 'figure' },
        { text: 'NemoGuard flagged none of the 17', kind: 'name' },
        { text: fact('injection', 'NemoGuard cost'), kind: 'name' },
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

function mount(ctx: SceneContext): SceneHandle {
  const { plate } = ctx;
  const names = [fact('injection', 'Detector 1'), fact('injection', 'Detector 2'), fact('injection', 'Detector 3')];

  // One die-cut label holds the whole world.
  const world = el('injection-world stock-label');

  // Wiring
  const wiring = el('injection-wiring');
  const sensors: HTMLElement[] = [];
  const wires: HTMLElement[] = [];
  names.forEach((n, i) => {
    const lane = el('injection-lane');
    lane.style.gridRow = String(i + 1);
    const sensor = el('injection-sensor');
    lane.append(el('injection-lane-label', n), sensor);
    sensors.push(sensor);
    const wire = el('injection-wire ' + (i === 0 ? 'injection-wire--block' : 'injection-wire--hold'));
    wire.style.gridRow = String(i + 1);
    wires.push(wire);
    wiring.append(lane, wire);
  });

  const blockTarget = el('injection-target injection-target--block');
  blockTarget.style.gridRow = '1';
  const blockFill = el('injection-block-fill shadow-layer');
  blockTarget.append(
    blockFill,
    verdictBadge('block', 'block'),
    el('injection-target-code machine', fact('injection', 'Block code')),
  );
  const holdTarget = el('injection-target injection-target--hold');
  holdTarget.style.gridRow = '2 / span 2';
  holdTarget.append(
    el('injection-hold-band hatch'),
    verdictBadge('hold', 'hold'),
    el('injection-target-code machine', fact('injection', 'Escalate code')),
  );
  wiring.append(blockTarget, holdTarget);

  const doc = el('injection-doc');
  for (let i = 0; i < 5; i++) doc.append(el('injection-doc-line'));
  doc.append(el('injection-doc-code blank-barcode'));
  wiring.append(doc);

  const marks = [0, 1, 2, 3].map((i) => el(`injection-reg injection-reg--${i} reg-mark`));
  wiring.append(...marks);

  // Readout
  const readout = el('injection-readout');
  readout.append(el('injection-perf perf-x'));
  const log = el('injection-log');
  const logLines = [quote('injection', '9 read_document'), quote('injection', 'reason INJECTION_DETECTED')];
  logLines.forEach((l) => log.append(el('injection-log-line machine', l)));

  const metrics = el('injection-metrics');
  const metricDefs: [string, string][] = [
    ['precision', fact('injection', 'Precision')],
    ['recall', fact('injection', 'Recall')],
    ['F1', fact('injection', 'F1')],
    ['hard-negative false positives', fact('injection', 'hard_negative_false_positives')],
  ];
  const metricEls = metricDefs.map(([k, v]) => {
    const m = el('injection-metric');
    m.append(el('injection-metric-value', v), el('injection-metric-name', k));
    metrics.append(m);
    return m;
  });

  const t = table('injection', 'injection-round-5');
  const si = t.columns.indexOf('split');
  const di = t.columns.indexOf('detector');
  const pi = t.columns.indexOf('precision');
  const ri = t.columns.indexOf('recall');
  const tableWrap = el('injection-table');
  const tbl = document.createElement('table');
  tbl.className = 'injection-tbl';
  const head = document.createElement('tr');
  [t.columns[di], t.columns[pi], t.columns[ri]].forEach((c) => {
    const th = document.createElement('th');
    th.textContent = c;
    head.append(th);
  });
  tbl.append(head);
  t.rows
    .filter((r) => r[si] === 'holdout')
    .forEach((r) => {
      const tr = document.createElement('tr');
      [r[di], r[pi], r[ri]].forEach((c, ci) => {
        const td = document.createElement('td');
        td.textContent = c;
        if (ci === 0) td.className = 'machine';
        tr.append(td);
      });
      if (r[di] === 'combined') {
        tr.className = 'injection-row-combined';
      }
      tbl.append(tr);
    });
  tableWrap.append(el('injection-table-caption', 'holdout'), tbl);

  readout.append(log, metrics, tableWrap);
  world.append(wiring, readout);
  plate.append(world);

  // Rest states (end state of the whole scene is at progress 1).
  const stampText = quote('injection', '9 read_document').trim().split(/\s+/)[2];
  const kit = createInspection({
    ctx,
    world,
    steps: STEPS,
    cues: [
      { step: 0, target: null },
      { step: 1, target: blockTarget, scale: 1.8, scan: true },
      {
        step: 2, target: doc, scale: 2.4, scan: true,
        stamp: { text: stampText, form: 'block', anchor: 'br' },
      },
      { step: 3, target: metricEls[1], scale: 1.8 },
      { step: 4, target: tbl.querySelector<HTMLElement>('.injection-row-combined'), scale: 2.0, scan: true },
    ],
  });

  gsap.set(wires, { scaleX: 0, transformOrigin: '0% 50%' });
  gsap.set([blockTarget, holdTarget], { opacity: 0 });
  gsap.set(doc, { opacity: 0, xPercent: -600 });
  gsap.set(marks, { opacity: 0 });
  gsap.set(blockFill, { opacity: 0 });
  gsap.set([log, metrics, tableWrap], { opacity: 0 });

  const tl = gsap.timeline({ paused: true, defaults: { ease: 'none' } });
  tl.to({}, { duration: STEPS }, 0);
  const fx = (target: gsap.TweenTarget, from: gsap.TweenVars, to: gsap.TweenVars, pos: number, dur: number) =>
    tl.fromTo(target, from, { ...to, duration: dur, immediateRender: false }, pos);
  const at = kit.at;

  // Step 1: the document label enters; registration marks fade in.
  fx(doc, { opacity: 0, xPercent: -600 }, { opacity: 1, xPercent: -300 }, 0.04, 0.38);
  fx(marks, { opacity: 0 }, { opacity: 1 }, 0.1, 0.3);

  // Step 2: TF-IDF wire draws first and reaches the block target; the two hold wires land together at lock.
  fx(blockTarget, { opacity: 0 }, { opacity: 1 }, 1.02, 0.14);
  fx(wires[0], { scaleX: 0 }, { scaleX: 1 }, 1.04, 0.22);
  fx([wires[1], wires[2]], { scaleX: 0 }, { scaleX: 1 }, at(1, 'lock'), 0.16);
  fx(holdTarget, { opacity: 0 }, { opacity: 1 }, at(1, 'lock'), 0.16);

  // Step 3: the document stops at the block target; log lines are legible by settle.
  fx(doc, { xPercent: -300 }, { xPercent: 0 }, 2.03, 0.22);
  fx(log, { opacity: 0 }, { opacity: 1 }, 2.06, 0.24);
  fx(blockFill, { opacity: 0 }, { opacity: 1 }, at(2, 'land'), 0.06);
  // log gives way to the measured values at the start of step 4
  if (!ctx.reducedMotion) fx(log, { opacity: 1 }, { opacity: 0 }, 3.0, 0.12);

  // Step 4: the four measured values appear together.
  fx(metrics, { opacity: 0 }, { opacity: 1 }, 3.04, 0.2);
  if (!ctx.reducedMotion) fx(metrics, { opacity: 1 }, { opacity: 0 }, 4.0, 0.14);

  // Step 5: the whole holdout table at full opacity before settle.
  fx(tableWrap, { opacity: 0 }, { opacity: 1 }, 4.04, 0.24);

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

const scene: SceneModule = { id: 'injection', title: 'Injection defense', steps, mount };
export default scene;
