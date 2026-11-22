import gsap from 'gsap';
import { fact, quote } from '../shell/content-access';
import { createInspection, verdictMark } from '../shell/emphasis';
import type { SceneContext, SceneFrame, SceneHandle, SceneModule, StepCopy } from '../shell/types';
import './pipeline.css';

const STEPS = 10;

function steps(): StepCopy[] {
  const stage = (n: number) => fact('pipeline', `Stage ${n}`);
  const detail = (n: number) => fact('pipeline', `Stage ${n} detail`);
  const out = (o: 'allow' | 'block' | 'hold') => fact('pipeline', `Outcome ${o}`);
  const plain = (n: number, headline: string, sentence: string): StepCopy => ({
    headline,
    sentence,
    callouts: [
      { text: stage(n), kind: 'name' },
      { text: detail(n), kind: 'name' },
    ],
  });
  return [
    plain(1, 'Policy comes first', "Every tool call is checked against the role's policy."),
    plain(2, 'Documents are checked for injection', 'Document reads go through three injection detectors.'),
    plain(3, 'Patient data is minimized', 'Identifiers are stripped down to what the task needs.'),
    plain(4, 'The content is checked', 'A judge reads the call against a HIPAA policy.'),
    plain(5, 'The behavior is scored', 'An anomaly model scores the call.'),
    {
      headline: 'One decision',
      sentence: 'The gateway allows the call, blocks it or holds it for a human.',
      callouts: [
        { text: out('allow'), kind: 'code', verdict: 'allow' },
        { text: out('block'), kind: 'code', verdict: 'block' },
        { text: out('hold'), kind: 'code', verdict: 'hold' },
      ],
    },
    {
      headline: 'Allow',
      sentence: 'Ordinary calls continue to the tool they asked for.',
      callouts: [
        { text: out('allow'), kind: 'code', verdict: 'allow' },
        { text: 'scripted run', kind: 'name' },
      ],
    },
    {
      headline: 'Block',
      sentence: 'The scripted run blocked three calls, each with its own reason code.',
      callouts: [
        { text: fact('policy', 'Reason code injection'), kind: 'code', verdict: 'block' },
        { text: fact('policy', 'Reason code resource'), kind: 'code', verdict: 'block' },
        { text: fact('policy', 'Reason code email'), kind: 'code', verdict: 'block' },
      ],
    },
    {
      headline: 'Hold is the third path',
      sentence: 'A held call waits for a person, and this scripted run did not hold any.',
      callouts: [
        { text: out('hold'), kind: 'code', verdict: 'hold' },
        { text: fact('pipeline', 'Holds in scripted run'), kind: 'code' },
      ],
    },
    {
      headline: 'Explained and recorded',
      sentence: 'The reasoner runs only after the decision is final, and the outcome goes to the audit log.',
      callouts: [
        { text: detail(6), kind: 'name' },
        { text: detail(7), kind: 'name' },
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

/** Layout offset of el inside ancestor, ignoring every transform. */
function off(el: HTMLElement, ancestor: HTMLElement): { x: number; y: number } {
  let x = 0;
  let y = 0;
  let n: HTMLElement | null = el;
  while (n && n !== ancestor) {
    x += n.offsetLeft;
    y += n.offsetTop;
    n = n.offsetParent as HTMLElement | null;
  }
  return { x, y };
}

function mount(ctx: SceneContext): SceneHandle {
  const { plate } = ctx;
  plate.textContent = '';
  plate.classList.add('stock-label', 'peel');

  // header strip: blank print furniture
  const head = h('div', 'pipeline-head');
  head.setAttribute('aria-hidden', 'true');
  head.appendChild(h('span', 'pipeline-head__bars blank-barcode'));
  head.appendChild(h('span', 'pipeline-head__rule micro-rule'));
  head.appendChild(h('span', 'reg-mark'));

  const view = h('div', 'pipeline-view');
  const track = h('div', 'pipeline-track');
  view.appendChild(track);

  const tracer = h('div', 'pipeline-tracer');
  tracer.setAttribute('aria-hidden', 'true');

  const nodes: HTMLElement[] = [];
  const marks: HTMLElement[] = [];
  const lines: HTMLElement[] = [];
  const linkEls: HTMLElement[] = [];

  function makeNode(n: number): HTMLElement {
    const node = h('div', 'pipeline-node stock-label');
    node.appendChild(h('span', 'pipeline-node__perf perf-y'));
    const body = h('div', 'pipeline-node__body');
    body.appendChild(h('span', 'pipeline-node__marker machine', `Stage ${n}`));
    body.appendChild(h('span', 'pipeline-node__name', fact('pipeline', `Stage ${n}`)));
    body.appendChild(h('span', 'pipeline-node__detail', fact('pipeline', `Stage ${n} detail`)));
    node.appendChild(body);
    const mark = h('span', 'pipeline-node__scanned');
    mark.setAttribute('aria-hidden', 'true');
    node.appendChild(mark);
    marks.push(mark);
    return node;
  }
  function makeLink(): HTMLElement {
    const l = h('div', 'pipeline-link');
    l.appendChild(h('span', 'pipeline-line pipeline-line--ghost'));
    const live = h('span', 'pipeline-line pipeline-line--live');
    l.appendChild(live);
    lines.push(live);
    linkEls.push(l);
    return l;
  }

  for (let i = 1; i <= 5; i++) {
    const n = makeNode(i);
    nodes.push(n);
    track.appendChild(n);
    track.appendChild(makeLink());
  }

  // Decide: unnumbered heavy diamond
  const decide = h('div', 'pipeline-decide');
  const shape = h('div', 'pipeline-decide__shape');
  shape.innerHTML =
    '<svg viewBox="0 0 144 96" preserveAspectRatio="none" aria-hidden="true"><polygon points="72,1 143,48 72,95 1,48"/></svg>';
  shape.appendChild(h('span', 'pipeline-decide__word', 'Decide'));
  decide.appendChild(shape);
  const focus = h('div', 'pipeline-decide__focus');
  focus.setAttribute('aria-hidden', 'true');
  decide.appendChild(focus);

  const under = h('div', 'pipeline-decide__under');
  const drop = h('div', 'pipeline-drop');
  drop.appendChild(h('span', 'pipeline-line pipeline-line--live'));
  under.appendChild(drop);
  under.appendChild(h('div', 'pipeline-decide__caption', fact('pipeline', 'Decide node')));
  const ports = h('div', 'pipeline-ports');
  const portEls: Record<string, HTMLElement> = {};
  const fills: Record<string, HTMLElement> = {};
  (['allow', 'block', 'hold'] as const).forEach((o) => {
    const p = h('div', `pipeline-port pipeline-port--${o}`);
    const fill = h('span', 'pipeline-port__fill');
    p.appendChild(fill);
    const mk = verdictMark(o);
    mk.classList.add('pipeline-port__mark');
    p.appendChild(mk);
    p.appendChild(h('span', 'pipeline-port__word', fact('pipeline', `Outcome ${o}`)));
    ports.appendChild(p);
    portEls[o] = p;
    fills[o] = fill;
  });
  under.appendChild(ports);

  // the attacker's email label
  const email = h('div', 'pipeline-email stock-label');
  email.appendChild(h('div', 'pipeline-email__bars blank-barcode'));
  email.appendChild(h('div', 'pipeline-email__to machine', fact('problem', 'Recipient')));
  const emailQuote = quote('pipeline', '13 send_email');
  email.appendChild(h('div', 'pipeline-email__line machine', emailQuote));
  under.appendChild(email);
  decide.appendChild(under);
  track.appendChild(decide);

  // fork and the two parallel branches
  const fork = h('div', 'pipeline-fork');
  const forkParts: Record<string, HTMLElement> = {};
  ['stem', 'spine', 'arm1', 'arm2'].forEach((k) => {
    const part = h('div', `pipeline-fl pipeline-fl--${k}`);
    part.appendChild(h('span', 'pipeline-line pipeline-line--ghost'));
    const live = h('span', 'pipeline-line pipeline-line--live');
    part.appendChild(live);
    fork.appendChild(part);
    forkParts[k] = live;
  });
  track.appendChild(fork);
  const group = h('div', 'pipeline-group');
  const n6 = makeNode(6);
  const n7 = makeNode(7);
  group.appendChild(n6);
  group.appendChild(n7);
  track.appendChild(group);
  track.appendChild(tracer);

  // run log, below the camera window
  const perf = h('div', 'pipeline-perf perf-x');
  perf.setAttribute('aria-hidden', 'true');
  const log = h('div', 'pipeline-log');
  const mkGroup = (verdict: 'allow' | 'block' | 'plain', texts: string[]): HTMLElement => {
    const g = h('div', 'pipeline-log__group');
    texts.forEach((t) => {
      const line = h('div', `pipeline-log__line pipeline-log__line--${verdict} machine`);
      if (verdict !== 'plain') line.appendChild(verdictMark(verdict));
      line.appendChild(h('span', 'pipeline-log__text', t));
      g.appendChild(line);
    });
    log.appendChild(g);
    return g;
  };
  const g0 = mkGroup('allow', [quote('pipeline', '1 read_document')]);
  const g1 = mkGroup('block', [
    quote('pipeline', '9 read_document'),
    quote('pipeline', '12 read_record'),
    emailQuote,
  ]);
  const g2 = mkGroup('plain', [quote('pipeline', 'totals:')]);

  plate.append(head, view, perf, log);

  const blockText = emailQuote.trim().split(/\s+/)[2];

  // the kit: camera over the track
  const scales = [1.7, 1.6, 1.85, 1.65, 1.75];
  const cues = [
    ...nodes.map((n, i) => ({
      step: i,
      target: n,
      scale: scales[i],
      pad: 20,
      scan: i === 0 || i === 1 || i === 4,
    })),
    { step: 5, target: focus, scale: 1.5, pad: 20 },
    {
      step: 6, target: portEls.allow, scale: 2.0, pad: 20,
      stamp: { text: fact('pipeline', 'Outcome allow'), form: 'allow' as const, anchor: 'tr' as const },
    },
    {
      step: 7, target: email, scale: 3.0, narrowScale: 1.6, pad: 20, scan: true,
      stamp: { text: blockText, form: 'block' as const, anchor: 'br' as const },
    },
    { step: 8, target: portEls.hold, scale: 2.0, pad: 20 },
    { step: 9, target: group, scale: 1.15, pad: 20 },
  ];
  const kit = createInspection({ ctx, world: track, viewport: view, steps: STEPS, cues });

  let tl: gsap.core.Timeline = gsap.timeline({ paused: true });
  let last = 0;

  function build(): void {
    tl.kill();
    gsap.set(
      [tracer, ...marks, ...lines, ...Object.values(forkParts), ...Object.values(fills), ports, drop, email, n6, n7, g0, g1, g2],
      { clearProps: 'transform,opacity' },
    );
    const narrow = ctx.isNarrow();
    const along = narrow ? 'scaleY' : 'scaleX';
    const across = narrow ? 'scaleX' : 'scaleY';
    const origin = narrow ? '50% 0%' : '0% 50%';

    const ctr = (el: HTMLElement) => {
      const o = off(el, track);
      return { x: o.x + el.offsetWidth / 2 - 8, y: o.y + el.offsetHeight / 2 - 8 };
    };
    // The tracer rests on connecting lines, never on text.
    const nodeStart = (el: HTMLElement) => {
      const o = off(el, track);
      return narrow ? { x: o.x + el.offsetWidth / 2 - 8, y: o.y - 28 } : { x: o.x - 28, y: o.y + el.offsetHeight / 2 - 8 };
    };
    const stem = forkParts.stem.parentElement as HTMLElement;
    const pts = [
      nodeStart(nodes[0]), ctr(linkEls[0]), ctr(linkEls[1]), ctr(linkEls[2]), ctr(linkEls[3]),
      ctr(linkEls[4]), ctr(drop), ctr(drop), ctr(drop), ctr(stem),
    ];
    const entry = narrow ? { x: pts[0].x, y: pts[0].y - 50 } : { x: pts[0].x - 80, y: pts[0].y };

    tl = gsap.timeline({ paused: true, defaults: { ease: 'none' } });
    const tw = (
      el: gsap.TweenTarget,
      from: gsap.TweenVars,
      to: gsap.TweenVars,
      at: number,
      dur: number,
      firstOfProp: boolean,
    ) => {
      tl.fromTo(el, from, { ...to, duration: dur, ease: 'none', immediateRender: firstOfProp }, at);
    };
    const fade = (el: gsap.TweenTarget, a: number, b: number, at: number, dur: number, firstOfProp: boolean) =>
      tw(el, { opacity: a }, { opacity: b }, at, dur, firstOfProp);

    gsap.set([...lines, ...Object.values(forkParts)], { transformOrigin: origin });
    gsap.set(forkParts.spine, { transformOrigin: '50% 50%' });

    // Support: the tracer lands exactly when the camera arrives
    for (let s = 0; s < STEPS; s++) {
      const f = s === 0 ? entry : pts[s - 1];
      const t = pts[s];
      tw(tracer, { x: f.x, y: f.y }, { x: t.x, y: t.y }, kit.at(s, 'diveStart'), 0.24, s === 0);
      if (s >= 1 && s <= 5) tw(lines[s - 1], { [along]: 0 }, { [along]: 1 }, kit.at(s, 'diveStart'), 0.24, true);
    }
    // Decoration: a scanned stage keeps its mark
    for (let i = 0; i < 5; i++) fade(marks[i], 0, 1, kit.at(i, 'scanEnd'), 0.05, true);

    // step 6: ports lock in together
    fade([ports, drop], 0, 1, kit.at(5, 'lock'), 0.1, true);
    fade(fills.allow, 0, 1, kit.at(6, 'land'), 0.05, true);
    fade(fills.block, 0, 1, kit.at(7, 'land'), 0.05, true);
    fade(fills.hold, 0, 1, kit.at(8, 'lock'), 0.1, true);

    // step 8: the email rides in during the dive
    fade(email, 0, 1, kit.at(7, 'diveStart'), 0.24, true);

    // run log (reduced motion shows every group statically)
    if (!ctx.reducedMotion) {
      fade(g0, 0, 1, kit.at(6, 'lock'), 0.1, true);
      fade(g0, 1, 0, 7.02, 0.06, false);
      fade(g1, 0, 1, kit.at(7, 'lock'), 0.1, true);
      fade(g1, 1, 0, 8.02, 0.06, false);
      fade(g2, 0, 1, kit.at(8, 'lock'), 0.1, true);
    }

    // step 10: branches draw from Decide, Stage 6 and 7 land together
    tw(forkParts.stem, { [along]: 0 }, { [along]: 1 }, 9.02, 0.2, true);
    tw(forkParts.spine, { [across]: 0 }, { [across]: 1 }, 9.22, 0.1, true);
    tw(forkParts.arm1, { [along]: 0 }, { [along]: 1 }, 9.3, 0.1, true);
    tw(forkParts.arm2, { [along]: 0 }, { [along]: 1 }, 9.3, 0.1, true);
    fade([n6, n7], 0, 1, 9.26, 0.14, true);

    tl.to({}, { duration: STEPS }, 0);
    tl.progress(last);
  }

  build();

  return {
    update(frame: SceneFrame) {
      last = frame.progress;
      tl.progress(frame.progress);
      kit.update(frame);
    },
    resize() {
      build();
      kit.resize();
    },
  };
}

const scene: SceneModule = { id: 'pipeline', title: 'The pipeline', steps, mount };
export default scene;
