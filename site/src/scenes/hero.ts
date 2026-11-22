import gsap from 'gsap';
import { fact } from '../shell/content-access';
import { createInspection, verdictBadge } from '../shell/emphasis';
import type { SceneContext, SceneFrame, SceneHandle, SceneModule, StepCopy, Verdict } from '../shell/types';
import './hero.css';

const STEPS = 4;

function steps(): StepCopy[] {
  const tagline = fact('hero', 'Tagline').replace(/\.$/, '');
  return [
    {
      headline: tagline,
      sentence: 'Every tool call an agent makes passes through Leash.',
      callouts: [
        { text: fact('hero', 'Product'), kind: 'name' },
        { text: fact('hero', 'Event'), kind: 'name' },
        { text: fact('hero', 'Data'), kind: 'name' },
      ],
    },
    {
      headline: 'Checked before it runs',
      sentence:
        'Leash checks each call against a role policy, strips patient data to what the task needs and scores it with ML.',
      callouts: [
        { text: fact('pipeline', 'Stage 1'), kind: 'name' },
        { text: fact('pipeline', 'Stage 3 detail'), kind: 'name' },
        { text: fact('pipeline', 'Stage 5 detail'), kind: 'name' },
      ],
    },
    {
      headline: 'Allowed, blocked or held',
      sentence:
        'Each call is allowed, blocked or held for a human, and written to a tamper-evident audit log.',
      callouts: [
        { text: fact('pipeline', 'Outcome allow'), kind: 'code', verdict: 'allow' },
        { text: fact('pipeline', 'Outcome block'), kind: 'code', verdict: 'block' },
        { text: fact('pipeline', 'Outcome hold'), kind: 'code', verdict: 'hold' },
      ],
    },
    {
      headline: 'Hard rules where safety needs them',
      sentence: fact('hero', 'Design rule'),
      callouts: [
        { text: fact('hero', 'Tracks'), kind: 'name' },
        { text: fact('pipeline', 'Stage 7 detail'), kind: 'name' },
      ],
    },
  ];
}

function el(parent: HTMLElement, cls: string, text?: string): HTMLElement {
  const node = document.createElement('div');
  node.className = cls;
  if (text !== undefined) node.textContent = text;
  parent.appendChild(node);
  return node;
}

function mount(ctx: SceneContext): SceneHandle {
  const { plate } = ctx;
  const ends: Array<{ key: string; verdict: Verdict; x: number }> = [
    { key: 'Outcome allow', verdict: 'allow', x: 16.67 },
    { key: 'Outcome block', verdict: 'block', x: 50 },
    { key: 'Outcome hold', verdict: 'hold', x: 83.33 },
  ];

  plate.textContent = '';
  // The label is static print. Only the view on its right, clear of the step copy, is inspected and dimmed.
  const label = el(plate, 'hero-label peel');
  el(label, 'hero-word', fact('hero', 'Product'));
  el(label, 'hero-restline');
  el(label, 'hero-micro micro-rule');
  const regs = ['tl', 'tr', 'bl', 'br'].map((p) => el(label, `reg-mark hero-reg hero-reg--${p}`));
  el(label, 'blank-barcode hero-barcode');

  const hint = el(label, 'hero-hint');
  el(hint, 'hero-key').setAttribute('aria-hidden', 'true');
  el(hint, 'hero-hint-text', 'Use the arrows, or press Space');

  const view = el(plate, 'hero-view');
  const world = el(view, 'hero-world');
  const print = el(world, 'hero-print');
  const trunk = el(print, 'hero-trunk');

  const gate = el(print, 'hero-gate');
  const bars = ['top', 'bottom'].map((p) => {
    const bar = el(gate, `hero-bar hero-bar--${p}`);
    return el(bar, 'hero-hot');
  });
  const ticks = [22, 41, 74].map((left) => {
    const tick = el(gate, 'hero-tick');
    tick.style.left = `${left}%`;
    return el(tick, 'hero-hot');
  });

  const endsBox = el(print, 'hero-ends');
  const busL = el(endsBox, 'hero-bus hero-bus--l');
  const busR = el(endsBox, 'hero-bus hero-bus--r');
  const drops: HTMLElement[] = [];
  const hots: HTMLElement[] = [];
  const labels: HTMLElement[] = [];
  for (const e of ends) {
    const drop = el(endsBox, 'hero-drop');
    drop.style.left = `${e.x}%`;
    hots.push(el(drop, `hero-hot hero-hot--${e.verdict}`));
    drops.push(drop);
    const label = el(endsBox, 'hero-end');
    label.style.left = `${e.x - 16}%`;
    label.appendChild(verdictBadge(e.verdict, fact('pipeline', e.key)));
    labels.push(label);
  }

  const [allowLabel, blockLabel, holdLabel] = labels;
  const [allowHot, blockHot, holdHot] = hots;

  gsap.set(trunk, { scaleY: 0.26 });
  gsap.set([busL, busR], { scaleX: 0 });
  gsap.set(drops, { scaleY: 0 });

  const tl = gsap.timeline({ paused: true, defaults: { ease: 'none' } });
  tl.to({}, { duration: STEPS }, 0);

  const kit = createInspection({
    ctx,
    world,
    viewport: view,
    steps: STEPS,
    cues: [
      { step: 0, target: null },
      { step: 1, target: gate, scale: 1.9, scan: true, mark: true },
      { step: 2, target: endsBox, scale: 1.7, mark: false },
      { step: 3, target: null },
    ],
  });
  const at = kit.at;

  // Step 2: the trunk enters the gate during the dive; ticks light with uneven gaps, the last at lock.
  tl.to(trunk, { scaleY: 0.56, duration: 0.24, ease: 'power2.inOut' }, 1.02);
  tl.to(regs, { opacity: 0.2, duration: 0.2 }, 1.04);
  tl.to(ticks[0], { opacity: 1, duration: 0.05 }, 1.07);
  tl.to(ticks[1], { opacity: 1, duration: 0.05 }, 1.19);
  tl.to(ticks[2], { opacity: 1, duration: 0.05 }, at(1, 'lock'));

  // Step 3: forks draw during the dive and reach the ends at arrive; block lands with the lead.
  tl.to(trunk, { scaleY: 0.62, duration: 0.08, ease: 'power2.out' }, 2.02);
  tl.to([busL, busR], { scaleX: 1, duration: 0.1, ease: 'power2.out' }, 2.06);
  tl.to(drops, { scaleY: 1, duration: 0.12, ease: 'power2.inOut' }, at(2, 'arrive') - 0.12);
  tl.to([allowHot, allowLabel], { opacity: 1, duration: 0.05 }, at(2, 'arrive') - 0.03);
  tl.to([holdHot, holdLabel], { opacity: 1, duration: 0.05 }, at(2, 'arrive') + 0.02);
  tl.to([blockHot, blockLabel], { opacity: 1, duration: 0.05 }, at(2, 'land') - 0.06);
  tl.fromTo(blockLabel, { scale: 1.35 }, { scale: 1, duration: 0.06, ease: 'back.out(2.4)', immediateRender: false }, at(2, 'land') - 0.06);

  // Step 4: the gate darkens to full black.
  tl.to(bars, { opacity: 1, duration: 0.26, ease: 'power2.out' }, 3.04);

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

const scene: SceneModule = { id: 'hero', title: 'Leash', steps, mount };
export default scene;
