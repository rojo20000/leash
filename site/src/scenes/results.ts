import gsap from 'gsap';
import { fact, quote, table } from '../shell/content-access';
import { createInspection, verdictBadge, verdictMark } from '../shell/emphasis';
import type { InspectCue } from '../shell/emphasis';
import type { Table } from '../content';
import type { SceneContext, SceneFrame, SceneHandle, SceneModule, StepCopy } from '../shell/types';
import './results.css';

const BLOCK_CALLS = [9, 12, 13];
const TOTAL_CALLS = 20;
const STEPS = 7;

function steps(): StepCopy[] {
  const rates = table('results', 'gateway-rates');
  const escalate = rates.rows[0][rates.columns.indexOf('escalate')];
  return [
    {
      headline: '17 allowed, 3 blocked',
      sentence: 'In the protected run, the legitimate calls went through and the attack did not.',
      callouts: [
        { text: fact('results', 'Allowed'), kind: 'figure', verdict: 'allow' },
        { text: fact('results', 'Blocked'), kind: 'figure', verdict: 'block' },
        { text: fact('results', 'Escalated'), kind: 'figure' },
      ],
    },
    {
      headline: 'What the gateway adds',
      sentence: 'Added latency was measured with the Nemotron stages on local fallback.',
      callouts: [
        { text: `p50 ${fact('results', 'Added latency p50 (ms)')} ms`, kind: 'figure' },
        { text: `p95 ${fact('results', 'Added latency p95 (ms)')} ms`, kind: 'figure' },
        { text: fact('results', 'Live call cost'), kind: 'name' },
      ],
    },
    {
      headline: 'Live model calls cost more',
      sentence: 'These are measured latencies of live calls to each hosted model.',
      callouts: [
        { text: `Lightning: ${fact('reasoner', 'Lightning latency')}`, kind: 'figure' },
        { text: `NemoGuard ${fact('injection', 'NemoGuard cost')}`, kind: 'name' },
      ],
    },
    {
      headline: 'Injection detector',
      sentence: 'Held-out scores for the TF-IDF classifier.',
      callouts: [
        { text: `precision ${fact('injection', 'Precision')}`, kind: 'figure' },
        { text: `recall ${fact('injection', 'Recall')}`, kind: 'figure' },
        { text: `F1 ${fact('injection', 'F1')}`, kind: 'figure' },
      ],
    },
    {
      headline: 'Anomaly and minimization',
      sentence: 'The minimization evaluation is probably easy, because it uses templated notes.',
      callouts: [
        { text: `anomaly recall ${fact('anomaly', 'Recall')}`, kind: 'figure' },
        { text: `minimization recall ${fact('minimization', 'Recall')}`, kind: 'figure' },
      ],
    },
    {
      headline: 'A wider workload did hold calls',
      sentence: 'Unlike the scripted run, this larger workload includes calls that were held for a person.',
      callouts: [
        { text: `${fact('results', 'Gateway calls')} calls`, kind: 'figure' },
        { text: `${fact('results', 'Gateway sessions')} sessions`, kind: 'figure' },
        { text: `escalate ${escalate}`, kind: 'figure', verdict: 'hold' },
      ],
    },
    {
      headline: 'Five checks passed',
      sentence: 'The scripted demo checks its own claims when it runs.',
      callouts: [
        { text: fact('results', 'Allowed'), kind: 'figure', verdict: 'allow' },
        { text: fact('results', 'Blocked'), kind: 'figure', verdict: 'block' },
        { text: '5 PASS', kind: 'figure' },
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

interface Built { table: HTMLTableElement; rows: HTMLTableRowElement[] }

function renderTable(t: Table, opts: { rows?: string[][]; skipCol?: string; stack?: boolean } = {}): Built {
  const skip = opts.skipCol ? t.columns.indexOf(opts.skipCol) : -1;
  const cols = t.columns.map((c, i) => ({ c, i })).filter((x) => x.i !== skip);
  const tbl = el('table', 'machine results-table' + (opts.stack ? ' results-stack' : ''));
  const head = el('thead');
  const hr = el('tr');
  cols.forEach(({ c }) => hr.appendChild(el('th', '', c)));
  head.appendChild(hr);
  tbl.appendChild(head);
  const body = el('tbody');
  const rows: HTMLTableRowElement[] = [];
  (opts.rows ?? t.rows).forEach((r) => {
    const tr = el('tr');
    cols.forEach(({ c, i }) => {
      const td = el('td', '', r[i]);
      td.dataset.label = c;
      tr.appendChild(td);
    });
    body.appendChild(tr);
    rows.push(tr);
  });
  tbl.appendChild(body);
  return { table: tbl, rows };
}

function caption(text: string): HTMLElement {
  return el('p', 'machine results-caption', text);
}

function mount(ctx: SceneContext): SceneHandle {
  const { plate } = ctx;
  const world = el('div', 'results-world');
  plate.appendChild(world);

  // The strip: twenty calls printed as a perforated tape.
  const tape = el('div', 'results-tape');
  tape.appendChild(el('div', 'perf-x'));
  const film = el('div', 'results-film');
  const allowMarks: HTMLElement[] = [];
  const blockMarks: HTMLElement[] = [];
  for (let n = 1; n <= TOTAL_CALLS; n++) {
    const isBlock = BLOCK_CALLS.includes(n);
    const m = el('div', 'results-mark ' + (isBlock ? 'is-block' : 'is-allow'));
    m.appendChild(verdictMark(isBlock ? 'block' : 'allow'));
    m.appendChild(el('span', 'results-callno', isBlock ? String(n) : ''));
    m.setAttribute('role', 'img');
    m.setAttribute('aria-label', `call ${n}: ${isBlock ? 'block' : 'allow'}`);
    film.appendChild(m);
    (isBlock ? blockMarks : allowMarks).push(m);
  }
  tape.appendChild(film);
  tape.appendChild(el('div', 'perf-x'));
  const legend = el('div', 'results-legend');
  legend.append(verdictBadge('allow', 'allow'), verdictBadge('block', 'block'));
  world.append(tape, legend);

  const stack = el('div', 'results-layers');
  world.appendChild(stack);
  const layers: HTMLElement[] = [];
  const add = (l: HTMLElement) => { stack.appendChild(l); layers.push(l); };
  const newLayer = () => el('div', 'results-layer');

  // 1 protected counts
  const pc = table('results', 'protected-counts');
  let l = newLayer();
  l.append(caption(pc.title), renderTable(pc).table);
  add(l);

  // 2 gateway latency, all rows
  const gl = table('results', 'gateway-latency');
  const glb = renderTable(gl);
  const latencyRow = glb.rows[gl.rows.findIndex((r) => r[0] === 'latency_ms')];
  l = newLayer();
  l.append(caption(gl.title), glb.table);
  add(l);

  // 3 model latency
  const ml = table('results', 'model-latency');
  const mlb = renderTable(ml, { stack: true });
  const lightningRow = mlb.rows[ml.rows.findIndex((r) => r[0].includes('lightning'))];
  l = newLayer();
  l.append(caption(ml.title), mlb.table);
  add(l);

  // 4 injection
  const det = table('results', 'detectors');
  const rowsOf = (name: string) => det.rows.filter((r) => r[0] === name);
  const injRows = rowsOf('injection');
  const injb = renderTable(det, { rows: injRows, skipCol: 'detector' });
  const injRecall = injb.rows[injRows.findIndex((r) => r[1] === 'recall')];
  l = newLayer();
  l.append(caption(`${det.title}: injection`), injb.table);
  add(l);

  // 5 anomaly and minimization, side by side
  const anoRows = rowsOf('anomaly');
  const anob = renderTable(det, { rows: anoRows, skipCol: 'detector' });
  const anoRecall = anob.rows[anoRows.findIndex((r) => r[1] === 'recall')];
  const minb = renderTable(det, { rows: rowsOf('minimization'), skipCol: 'detector' });
  l = newLayer();
  l.classList.add('results-two');
  const g1 = el('div', 'results-group');
  g1.append(caption(`${det.title}: anomaly`), anob.table);
  const g2 = el('div', 'results-group');
  g2.append(caption(`${det.title}: minimization`), minb.table);
  l.append(g1, g2);
  add(l);

  // 6 gateway rates
  const gr = table('results', 'gateway-rates');
  const grb = renderTable(gr);
  const escalateCell = grb.rows[0].children[gr.columns.indexOf('escalate')] as HTMLElement;
  l = newLayer();
  l.append(caption('Separate 245-call workload'), el('p', 'machine results-note', fact('results', 'Workload')), caption(gr.title), grb.table);
  add(l);

  // 7 PASS lines
  l = newLayer();
  const pass = el('ol', 'results-pass');
  const passLines: HTMLElement[] = [];
  [1, 2, 3, 4, 5].forEach((n) => {
    const li = el('li', 'results-passline');
    li.appendChild(verdictMark('allow'));
    li.appendChild(el('span', 'machine results-passtext', quote('results', `PASS ${n}`)));
    pass.appendChild(li);
    passLines.push(li);
  });
  l.appendChild(pass);
  add(l);

  // Print furniture, static.
  world.append(el('span', 'reg-mark results-reg results-reg--bl'), el('span', 'reg-mark results-reg results-reg--br'));

  const tl = gsap.timeline({ paused: true, defaults: { ease: 'none' } });
  tl.to({}, { duration: STEPS }, 0);

  const cues: InspectCue[] = [
    { step: 0, target: film, scale: 1.15, scan: true },
    { step: 1, target: latencyRow, scale: 1.7, scan: true },
    { step: 2, target: lightningRow, scale: 1.5 },
    { step: 3, target: injRecall, scale: 1.6 },
    { step: 4, target: anoRecall, scale: 1.5 },
    {
      step: 5, target: escalateCell, scale: 2.2,
      stamp: { text: fact('pipeline', 'Outcome hold'), form: 'hold', anchor: 'tr' },
    },
    {
      step: 6, target: passLines[1], scale: 1.5, scan: true,
      stamp: { text: quote('results', 'PASS 2').trim().split(/\s+/)[0], form: 'allow', anchor: 'tr' },
    },
  ];
  const kit = createInspection({ ctx, world, steps: STEPS, cues });

  // Step 1: allow marks print quickly and unevenly, the three blocks land last with the stamp beat.
  tl.fromTo(allowMarks, { opacity: 0.15 }, {
    opacity: 1, duration: 0.05,
    stagger: { each: 0.011, ease: 'power2.out', from: 'start' },
  }, kit.at(0, 'diveStart'));
  tl.fromTo(blockMarks, { opacity: 0.15, scale: 1.6 }, {
    opacity: 1, scale: 1, duration: 0.06, transformOrigin: '50% 0%',
  }, kit.at(0, 'land'));

  // Table layers swap as one crossfade at the start of each step.
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

const scene: SceneModule = { id: 'results', title: 'Results', steps, mount };
export default scene;
