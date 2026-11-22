import gsap from 'gsap';
import { fact, quote, table } from '../shell/content-access';
import { createInspection } from '../shell/emphasis';
import type { SceneContext, SceneFrame, SceneHandle, SceneModule, StepCopy } from '../shell/types';
import './policy.css';

const STEPS = 4;

function steps(): StepCopy[] {
  const rustRaw = fact('policy', 'Policy check Rust (us)');
  const pyRaw = fact('policy', 'Policy check Python (us)');
  const rust = Number(rustRaw).toFixed(2);
  const py = Number(pyRaw).toFixed(2);
  return [
    {
      headline: 'Rules that run in Rust',
      sentence: 'The policy engine checks tools, resources, rate and email domains.',
      callouts: [
        { text: fact('pipeline', 'Stage 1'), kind: 'name' },
        { text: fact('policy', 'Checks'), kind: 'name' },
      ],
    },
    {
      headline: `${rust} µs against ${py} µs`,
      sentence: fact('policy', 'Pitch wording'),
      callouts: [
        { text: `${rustRaw} us`, kind: 'figure' },
        { text: `${pyRaw} us`, kind: 'figure' },
        { text: `n = ${fact('policy', 'Iterations')}`, kind: 'figure' },
      ],
    },
    {
      headline: 'Off-policy calls stop here',
      sentence: 'A resource outside the role or an email to an outside domain is blocked by policy.',
      callouts: [
        { text: fact('policy', 'Reason code resource'), kind: 'code', verdict: 'block' },
        { text: fact('policy', 'Reason code email'), kind: 'code', verdict: 'block' },
      ],
    },
    {
      headline: 'The fast part is not the slow part',
      sentence: 'The anomaly model, not the policy check, is the biggest per-call cost in the gateway.',
      callouts: [
        { text: 'audit_append', kind: 'name' },
        { text: `${fact('policy', 'Audit append speedup')} times`, kind: 'figure' },
        { text: 'disk-bound', kind: 'name' },
      ],
    },
  ];
}

function h(tag: string, cls: string, text?: string): HTMLElement {
  const e = document.createElement(tag);
  e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}


function mount(ctx: SceneContext): SceneHandle {
  const { plate } = ctx;
  plate.textContent = '';
  plate.classList.add('stock-label', 'peel');
  const rustRaw = fact('policy', 'Policy check Rust (us)');
  const pyRaw = fact('policy', 'Policy check Python (us)');
  const ratio = Number(rustRaw) / Number(pyRaw);

  const world = h('div', 'policy-world');
  world.style.setProperty('--policy-ratio', String(ratio));

  // bars on a fine ruled scale
  const bars = h('div', 'policy-bars');
  const scale = h('div', 'policy-scale');
  scale.setAttribute('aria-hidden', 'true');
  bars.appendChild(scale);
  const mkRow = (kind: 'rust' | 'py', name: string, value: string) => {
    const row = h('div', `policy-row policy-row--${kind}`);
    const head = h('div', 'policy-row__head');
    head.appendChild(h('span', 'policy-row__name', name));
    const val = h('span', 'policy-row__value machine', `${value} µs`);
    head.appendChild(val);
    row.appendChild(head);
    const base = h('div', 'policy-row__base');
    const bar = h('div', 'policy-bar');
    base.appendChild(bar);
    row.appendChild(base);
    const zone = h('div', 'policy-row__zone');
    zone.setAttribute('aria-hidden', 'true');
    row.appendChild(zone);
    bars.appendChild(row);
    return { bar, val, zone };
  };
  const rust = mkRow('rust', 'Rust', Number(rustRaw).toFixed(2));
  const py = mkRow('py', 'Python', Number(pyRaw).toFixed(2));
  world.appendChild(bars);

  const lower = h('div', 'policy-lower');
  const checks = h('ul', 'policy-checks');
  fact('policy', 'Checks')
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean)
    .forEach((c) => checks.appendChild(h('li', 'policy-checks__item', c)));
  lower.appendChild(checks);

  const reasons = h('div', 'policy-reasons');
  const reasonRes = h('p', 'policy-reason machine', quote('policy', 'RESOURCE_NOT_ALLOWED'));
  const reasonMail = h('p', 'policy-reason machine', quote('policy', 'EMAIL_DOMAIN_NOT_ALLOWED'));
  reasons.append(reasonRes, reasonMail);
  lower.appendChild(reasons);

  const bench = table('policy', 'policy-bench');
  const tableBox = h('div', 'policy-bench');
  const grid = h('div', 'policy-table machine');
  bench.columns.forEach((c) => grid.appendChild(h('span', 'policy-table__head', c)));
  bench.rows.forEach((r) => r.forEach((cell) => grid.appendChild(h('span', 'policy-table__cell', cell))));
  tableBox.appendChild(grid);
  lower.appendChild(tableBox);

  const caveat = h('p', 'policy-caveat', fact('policy', 'Audit append caveat'));
  lower.appendChild(caveat);
  world.appendChild(lower);
  plate.appendChild(world);

  const blockText = quote('pipeline', '13 send_email').trim().split(/\s+/)[2];

  const kit = createInspection({
    ctx, world, steps: STEPS,
    cues: [
      { step: 0, target: checks, scale: 1.5, scan: true },
      { step: 1, target: rust.zone, scale: 2.4, scan: true },
      {
        step: 2, target: reasonMail, scale: 2.0,
        stamp: { text: blockText, form: 'block', anchor: 'br' },
      },
      { step: 3, target: tableBox, scale: 1.35 },
    ],
  });

  const tl = gsap.timeline({ paused: true, defaults: { ease: 'none' } });
  const tw = (el: gsap.TweenTarget, from: gsap.TweenVars, to: gsap.TweenVars, at: number, dur: number, firstOfProp = true) =>
    tl.fromTo(el, from, { ...to, duration: dur, ease: 'none', immediateRender: firstOfProp }, at);

  gsap.set([rust.bar, py.bar], { transformOrigin: '0% 50%' });
  // step 1: the ruled scale is decoration, it only fades
  tw(scale, { opacity: 0 }, { opacity: 1 }, kit.at(0, 'diveStart'), 0.24);
  // step 2: Rust stops at arrive, Python is still running
  if (!ctx.reducedMotion) tw(checks, { opacity: 1 }, { opacity: 0 }, kit.at(1, 'diveStart'), 0.24);
  tw(rust.bar, { scaleX: 0 }, { scaleX: ratio }, kit.at(1, 'diveStart'), 0.24);
  tw(py.bar, { scaleX: 0 }, { scaleX: 1 }, kit.at(1, 'diveStart'), 0.4);
  tw(rust.val, { opacity: 0 }, { opacity: 1 }, kit.at(1, 'lock'), 0.1);
  tw(py.val, { opacity: 0 }, { opacity: 1 }, 1.38, 0.1);
  // step 3: bars recede, both reasons arrive
  tw([rust.bar, py.bar], { opacity: 1 }, { opacity: 0.3 }, kit.at(2, 'diveStart'), 0.2, false);
  tw(reasons, { opacity: 0 }, { opacity: 1 }, kit.at(2, 'diveStart'), 0.24);
  // step 4: the table leads, the caveat follows
  tw(tableBox, { opacity: 0 }, { opacity: 1 }, kit.at(3, 'diveStart'), 0.24);
  tw(caveat, { opacity: 0 }, { opacity: 1 }, kit.at(3, 'lock'), 0.1);
  tl.to({}, { duration: STEPS }, 0);

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

const scene: SceneModule = { id: 'policy', title: 'Policy engine', steps, mount };
export default scene;
