import gsap from 'gsap';
import { fact, quote } from '../shell/content-access';
import { createInspection, verdictBadge } from '../shell/emphasis';
import type { SceneContext, SceneFrame, SceneHandle, SceneModule, StepCopy } from '../shell/types';
import './problem.css';

const STEPS = 4;

function steps(): StepCopy[] {
  return [
    {
      headline: 'A referral arrives',
      sentence: 'A scheduling agent reads a referral PDF as part of its normal work.',
      callouts: [
        { text: fact('problem', 'Patient'), kind: 'code' },
        { text: 'scheduling agent', kind: 'name' },
        { text: fact('problem', 'Data'), kind: 'name' },
      ],
    },
    {
      headline: 'One sentence is hidden inside',
      sentence: fact('problem', 'Hidden sentence'),
      callouts: [
        { text: 'referral PDF', kind: 'name' },
        { text: 'hidden instruction', kind: 'name' },
      ],
    },
    {
      headline: 'The agent follows it',
      sentence: "In our demo, an unprotected agent emails the patient's full record to an outside address.",
      callouts: [
        { text: fact('problem', 'Recipient'), kind: 'code' },
        { text: fact('problem', 'MRN check'), kind: 'code' },
      ],
    },
    {
      headline: 'The full record leaves',
      sentence: 'The email lands in a local file sink, and the patient is synthetic.',
      callouts: [
        { text: fact('problem', 'Leaked size'), kind: 'figure' },
        { text: fact('problem', 'Sink'), kind: 'name' },
        { text: fact('problem', 'Data'), kind: 'name' },
        { text: 'scripted run', kind: 'name' },
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

function envelopeSvg(parent: HTMLElement, cls: string): SVGSVGElement {
  parent.insertAdjacentHTML(
    'beforeend',
    `<svg class="${cls}" viewBox="0 0 120 84" aria-hidden="true"><rect x="1" y="1" width="118" height="82"></rect><polyline points="1,1 60,48 119,1"></polyline></svg>`,
  );
  return parent.lastElementChild as SVGSVGElement;
}

/** Layout offset of el inside ancestor; ignores every transform. */
function offsetWithin(node: HTMLElement, ancestor: HTMLElement): { x: number; y: number } {
  let x = 0;
  let y = 0;
  let n: HTMLElement | null = node;
  while (n && n !== ancestor) {
    x += n.offsetLeft;
    y += n.offsetTop;
    n = n.offsetParent as HTMLElement | null;
  }
  return { x, y };
}

function mount(ctx: SceneContext): SceneHandle {
  const { plate } = ctx;
  const HIDDEN = 4;
  const widths = [54, 92, 86, 94, 90, 84, 93, 72, 46];

  plate.textContent = '';
  const world = el(plate, 'problem-world');
  el(world, 'problem-tag', 'referral PDF');
  ['tl', 'tr', 'bl', 'br'].forEach((p) => el(world, `reg-mark problem-reg problem-reg--${p}`));

  const sheet = el(world, 'problem-sheet');
  const rows: HTMLElement[] = [];
  let base!: HTMLElement;
  let outline!: HTMLElement;
  let bright!: HTMLElement;
  widths.forEach((w, i) => {
    const row = el(sheet, i === 0 ? 'problem-row problem-row--head' : 'problem-row');
    row.style.width = `${w}%`;
    const bar = el(row, 'problem-bar');
    if (i === HIDDEN) {
      base = bar;
      outline = el(row, 'problem-outline');
      bright = el(row, 'problem-bright');
    }
    rows.push(row);
  });
  el(sheet, 'problem-perf perf-x');

  const env = el(world, 'problem-env');
  const shape = el(env, 'problem-env-shape');
  envelopeSvg(shape, 'problem-env-base');
  const envHot = envelopeSvg(shape, 'problem-env-hot');

  const leak = el(world, 'problem-leak');
  leak.appendChild(verdictBadge('alert', 'leaked'));
  el(leak, 'problem-leak-text machine', quote('problem', 'LEAK:'));

  const kit = createInspection({
    ctx,
    world,
    steps: STEPS,
    cues: [
      { step: 0, target: null },
      { step: 1, target: rows[HIDDEN], scale: 3.2, scan: true },
      { step: 2, target: env, scale: 1.8 },
      {
        step: 3,
        target: leak,
        scale: 2.1,
        scan: true,
        stamp: { text: 'leaked', form: 'alert', anchor: 'tr' },
      },
    ],
  });
  const at = kit.at;

  let tl: gsap.core.Timeline | null = null;
  let builtW = -1;
  let builtH = -1;

  function build() {
    if (tl) tl.kill();
    gsap.set([bright, shape], { clearProps: 'transform' });
    builtW = world.offsetWidth;
    builtH = world.offsetHeight;

    const b = offsetWithin(bright, world);
    const e = offsetWithin(shape, world);
    const bw = bright.offsetWidth;
    const bh = bright.offsetHeight;
    const dx = e.x + shape.offsetWidth / 2 - (b.x + bw / 2);
    const dy = e.y + shape.offsetHeight / 2 - (b.y + bh / 2);
    const edgeDx = Math.max(0, env.offsetWidth - shape.offsetWidth);
    const shrink = Math.min(1, (shape.offsetWidth * 0.4) / Math.max(1, bw));

    const t = gsap.timeline({ paused: true, defaults: { ease: 'none' } });
    t.to({}, { duration: STEPS }, 0);
    // Step 2: the hidden bar turns bright red when the reticle locks.
    t.to(bright, { opacity: 1, duration: 0.05 }, at(1, 'lock'));
    // Step 3: detach, fly into the envelope during the dive, arrive on cue, envelope reaches the edge by settle.
    t.to(base, { opacity: 0, duration: 0.04 }, 2.02);
    t.to(outline, { opacity: 1, duration: 0.04 }, 2.02);
    t.to(bright, { x: dx, y: dy, duration: at(2, 'arrive') - 2.02, ease: 'power2.inOut' }, 2.02);
    t.to(bright, { scaleX: shrink, duration: 0.1, ease: 'power2.in' }, at(2, 'arrive') - 0.1);
    t.to(bright, { opacity: 0, duration: 0.03 }, at(2, 'arrive'));
    t.to(envHot, { opacity: 1, duration: 0.04 }, at(2, 'arrive'));
    t.to(shape, { x: edgeDx, duration: at(2, 'settle') - at(2, 'arrive') - 0.02, ease: 'power2.out' }, at(2, 'arrive') + 0.02);
    // Step 4: the leak line is on the label before the scan crosses it.
    t.to(leak, { opacity: 1, duration: 0.14 }, 3.06);
    tl = t;
  }
  build();

  return {
    update(frame: SceneFrame) {
      if (world.offsetWidth !== builtW || world.offsetHeight !== builtH) build();
      tl?.progress(frame.progress);
      kit.update(frame);
    },
    resize() {
      build();
      kit.resize();
    },
  };
}

const scene: SceneModule = { id: 'problem', title: 'The problem', steps, mount };
export default scene;
