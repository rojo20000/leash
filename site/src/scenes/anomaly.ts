import gsap from 'gsap';
import { createInspection } from '../shell/emphasis';
import { fact, table } from '../shell/content-access';
import type { SceneContext, SceneFrame, SceneHandle, SceneModule, StepCopy } from '../shell/types';
import './anomaly.css';

const STEPS = 4;

function steps(): StepCopy[] {
  return [
    {
      headline: 'Behavior over time',
      sentence: fact('anomaly', 'Windows'),
      callouts: [
        { text: fact('anomaly', 'Model'), kind: 'name' },
        { text: '60-second windows', kind: 'name' },
      ],
    },
    {
      headline: 'Each call gets a score',
      sentence: 'The model scores agent activity, and that score feeds the decision.',
      callouts: [
        { text: fact('anomaly', 'Model'), kind: 'name' },
        { text: 'contamination ' + fact('anomaly', 'contamination'), kind: 'figure' },
        { text: 'threshold ' + fact('anomaly', 'threshold'), kind: 'figure' },
      ],
    },
    {
      headline: 'Measured by scenario',
      sentence: 'Recall is reported separately for each abnormal scenario.',
      callouts: [
        { text: 'precision ' + fact('anomaly', 'Precision'), kind: 'figure' },
        { text: 'recall ' + fact('anomaly', 'Recall'), kind: 'figure' },
        { text: 'F1 ' + fact('anomaly', 'F1'), kind: 'figure' },
        {
          text: 'normal false-positive rate ' + fact('anomaly', 'false_positive_rate_normal'),
          kind: 'figure',
        },
      ],
    },
    {
      headline: 'Two of these are not the forest',
      sentence: fact('anomaly', 'Features caveat'),
      callouts: [
        { text: 'exfil_email', kind: 'code' },
        { text: 'off_role_resources', kind: 'code' },
        { text: 'deterministic guard', kind: 'name' },
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

const TICKS = 48; // schematic: evenly spaced, carries no values
const GUARDED = ['exfil_email', 'off_role_resources'];

function mount(ctx: SceneContext): SceneHandle {
  const { plate } = ctx;
  const t = table('anomaly', 'anomaly-by-scenario');
  const si = t.columns.indexOf('scenario');
  const ni = t.columns.indexOf('n');
  const ri = t.columns.indexOf('recall');

  const world = el('anomaly-world stock-label peel');

  // Strip with sliding bracket
  const strip = el('anomaly-strip');
  const stripTag = el('anomaly-strip-tag');
  stripTag.append(el('anomaly-strip-word', 'schematic'), el('anomaly-strip-rule micro-rule'));
  const track = el('anomaly-track');
  const ticks = el('anomaly-ticks');
  for (let i = 0; i < TICKS; i++) ticks.append(el('anomaly-tick'));
  const bracket = el('anomaly-bracket');
  const marks = [el('anomaly-reg anomaly-reg--l reg-mark'), el('anomaly-reg anomaly-reg--r reg-mark')];
  track.append(ticks, bracket, ...marks);
  strip.append(stripTag, track);

  // Side: blank stub, replaced by the table
  const stub = el('anomaly-stub');
  stub.append(el('anomaly-stub-code blank-barcode'), el('anomaly-stub-rule micro-rule'));

  const tableWrap = el('anomaly-table');
  const head = el('anomaly-row anomaly-row--head');
  head.append(el('anomaly-cell-name', t.columns[si]), el('anomaly-cell-n', t.columns[ni]), el('anomaly-cell-val', t.columns[ri]));
  tableWrap.append(head);
  const rows: HTMLElement[] = [];
  const bars: HTMLElement[] = [];
  const scales: number[] = [];
  const tags: HTMLElement[] = [];
  const names: string[] = [];
  const guarded = el('anomaly-guarded');
  t.rows.forEach((r) => {
    const row = el('anomaly-row');
    row.append(
      el('anomaly-cell-name machine', r[si]),
      el('anomaly-cell-n machine', r[ni]),
      el('anomaly-cell-val machine', r[ri]),
    );
    const bt = el('anomaly-bar-track');
    const bar = el('anomaly-bar');
    bt.append(bar);
    row.append(bt);
    const isGuard = GUARDED.includes(r[si]);
    if (isGuard) {
      const tag = el('anomaly-guard', 'deterministic guard');
      row.append(tag);
      tags.push(tag);
    }
    rows.push(row);
    bars.push(bar);
    names.push(r[si]);
    scales.push(Math.min(1, Math.max(0, Number(r[ri]))));
    // adjacent guarded rows share one wrapper, order unchanged
    if (isGuard) {
      guarded.append(row);
      if (!guarded.parentElement) tableWrap.append(guarded);
    } else {
      tableWrap.append(row);
    }
  });

  const side = el('anomaly-side');
  side.append(stub, tableWrap);
  world.append(strip, el('anomaly-perf perf-x'), side);
  plate.append(world);

  const kit = createInspection({
    ctx,
    world,
    steps: STEPS,
    cues: [
      { step: 0, target: track, scale: 1.4 },
      { step: 1, target: track, scale: 1.25, scan: true },
      { step: 2, target: tableWrap, scale: 1.3 },
      { step: 3, target: guarded, scale: 1.8, scan: true },
    ],
  });

  gsap.set(bracket, { opacity: 0, xPercent: 0 });
  gsap.set(marks, { opacity: 0 });
  gsap.set(tableWrap, { opacity: 0 });
  gsap.set(bars, { scaleX: 0, transformOrigin: '0% 50%' });
  gsap.set(tags, { opacity: 0, xPercent: -6 });

  const tl = gsap.timeline({ paused: true, defaults: { ease: 'none' } });
  tl.to({}, { duration: STEPS }, 0);
  const fx = (target: gsap.TweenTarget, from: gsap.TweenVars, to: gsap.TweenVars, pos: number, dur: number) =>
    tl.fromTo(target, from, { ...to, duration: dur, immediateRender: false }, pos);
  const at = kit.at;

  // Step 1: the bracket appears at the strip's left; registration marks fade in.
  fx(bracket, { opacity: 0 }, { opacity: 1 }, 0.08, 0.3);
  fx(marks, { opacity: 0 }, { opacity: 1 }, 0.1, 0.3);

  // Step 2: the bracket slides right from arrive through settle. It is 1/6 of the strip, so 500% reaches the end.
  fx(bracket, { xPercent: 0 }, { xPercent: 500 }, at(1, 'arrive'), at(1, 'settle') - at(1, 'arrive'));

  // Step 3: the table replaces the stub; recall bars draw together, exfil_email first by a set offset.
  fx(stub, { opacity: 1 }, { opacity: 0 }, 2.04, 0.18);
  fx(tableWrap, { opacity: 0 }, { opacity: 1 }, 2.04, 0.18);
  bars.forEach((b, i) => {
    const first = names[i] === 'exfil_email';
    fx(b, { scaleX: 0 }, { scaleX: scales[i] }, first ? 2.14 : 2.2, first ? 0.3 : 0.26);
  });

  // Step 4: both guard tags land together at land.
  fx(tags, { opacity: 0, xPercent: -6 }, { opacity: 1, xPercent: 0 }, at(3, 'land') - 0.06, 0.06);

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

const scene: SceneModule = { id: 'anomaly', title: 'Anomaly scoring', steps, mount };
export default scene;
