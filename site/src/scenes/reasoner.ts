import gsap from 'gsap';
import { fact, quote } from '../shell/content-access';
import { createInspection, verdictBadge, verdictMark } from '../shell/emphasis';
import type { SceneContext, SceneFrame, SceneHandle, SceneModule, StepCopy } from '../shell/types';
import './reasoner.css';

const STEPS = 4;

function steps(): StepCopy[] {
  return [
    {
      headline: 'It speaks after the decision',
      sentence: 'The reasoner runs after the decision is final and is advisory.',
      callouts: [
        { text: fact('reasoner', 'Model'), kind: 'code' },
        { text: 'advisory', kind: 'name' },
      ],
    },
    {
      headline: 'A reason a person can read',
      sentence: 'Each blocked or held call gets an explanation for a clinician or compliance reviewer.',
      callouts: [
        { text: 'replay', kind: 'code' },
        { text: 'risk=critical', kind: 'code' },
        { text: 'recommends=deny', kind: 'code' },
      ],
    },
    {
      headline: 'Nemotron can only add caution',
      sentence: 'Nemotron output can only add caution, never remove it, and the reasoner itself changes no decision.',
      callouts: [
        { text: fact('reasoner', 'Cannot unblock'), kind: 'name' },
        { text: fact('reasoner', 'Invariant test'), kind: 'code' },
      ],
    },
    {
      headline: 'Grounded or thrown out',
      sentence: fact('reasoner', 'Grounding'),
      callouts: [
        { text: fact('reasoner', 'Reasoner fallback'), kind: 'name' },
        { text: 'Lightning, last eval round: ' + fact('reasoner', 'Lightning latency'), kind: 'figure' },
        { text: 'replay in make demo', kind: 'name' },
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
  const world = el(plate, 'div', 'reasoner-world');
  const label = el(world, 'div', 'reasoner-label stock-label peel');

  const top = el(label, 'div', 'reasoner-top');
  el(top, 'span', 'reg-mark');
  el(top, 'span', 'micro-rule reasoner-top-rule');
  el(top, 'span', 'reg-mark');

  // Upper zone: layer A (decision, then the reasoner) and layer B (the replay explanation).
  const upper = el(label, 'div', 'reasoner-upper');

  const why = el(upper, 'div', 'reasoner-why');
  const head = el(why, 'div', 'reasoner-why-head');
  el(head, 'span', 'reasoner-tag machine', 'replay');
  const risk = el(why, 'p', 'reasoner-risk machine', quote('reasoner', 'risk=critical'));
  const para = el(why, 'p', 'reasoner-para', quote('reasoner', 'hidden instructions'));

  const layerA = el(upper, 'div', 'reasoner-a');
  const decision = el(layerA, 'div', 'reasoner-node reasoner-node--decision');
  el(decision, 'span', 'reasoner-node-text', 'Decision final');
  el(decision, 'span', 'reasoner-node-sub', 'already set');
  const wireWrap = el(layerA, 'div', 'reasoner-wire-wrap');
  const wire = el(wireWrap, 'div', 'reasoner-wire');
  const reasonerNode = el(layerA, 'div', 'reasoner-node reasoner-node--reasoner');
  el(reasonerNode, 'span', 'reasoner-node-text', 'Reasoner');
  el(reasonerNode, 'span', 'reasoner-node-sub', 'advisory');

  // The one-way valve.
  const valve = el(label, 'div', 'reasoner-valve');
  const seg = el(valve, 'div', 'reasoner-seg');
  const nodes = el(valve, 'div', 'reasoner-valve-nodes');
  const nAllow = el(nodes, 'span', 'reasoner-vn reasoner-vn--allow');
  nAllow.append(verdictBadge('allow', 'allow'));
  const nHold = el(nodes, 'span', 'reasoner-vn reasoner-vn--hold');
  nHold.append(verdictBadge('hold', fact('pipeline', 'Outcome hold')));
  const nBlock = el(nodes, 'span', 'reasoner-vn reasoner-vn--block');
  nBlock.append(verdictBadge('block', 'block'));
  const track = el(valve, 'div', 'reasoner-track');
  el(track, 'div', 'reasoner-track-base');
  const lit = el(track, 'div', 'reasoner-track-lit hatch');
  const litCore = el(track, 'div', 'reasoner-track-core');
  const markerWrap = el(track, 'div', 'reasoner-marker-wrap');
  const marker = el(markerWrap, 'div', 'reasoner-marker');
  marker.innerHTML =
    '<svg viewBox="0 0 16 20" aria-hidden="true"><path d="M3 2 L13 10 L3 18" fill="none" stroke="currentColor" stroke-width="3.5" stroke-linecap="square"/></svg>';
  const esc = el(valve, 'p', 'reasoner-esc', 'Nemotron detectors and judges escalate to a human');
  const back = el(valve, 'div', 'reasoner-back');
  const backLine = el(back, 'div', 'reasoner-back-line');
  const stop = el(back, 'div', 'reasoner-back-stop');
  const closed = el(back, 'p', 'reasoner-back-label');
  closed.append(verdictMark('block'), document.createTextNode('no Nemotron path back to allow from hold or block'));

  // Footer: the PASS line and the replay note, one zoom target.
  const pass = el(label, 'div', 'reasoner-pass');
  const passLine = el(pass, 'p', 'reasoner-pass-line machine', quote('reasoner', 'PASS 5'));
  const replayNote = el(pass, 'p', 'reasoner-note', fact('reasoner', 'Replay'));

  el(label, 'div', 'blank-barcode reasoner-bar');

  const tl = gsap.timeline({ paused: true, defaults: { ease: 'none' } });
  tl.to({}, { duration: STEPS }, 0);

  const kit = createInspection({
    ctx,
    world,
    steps: STEPS,
    cues: [
      { step: 0, target: reasonerNode, scale: 1.6, scan: false },
      { step: 1, target: why, scale: 1.45, scan: true },
      {
        step: 2,
        target: seg,
        scale: 2.0,
        scan: true,
        stamp: { text: fact('pipeline', 'Outcome hold'), form: 'hold', anchor: 'tr' },
      },
      { step: 3, target: pass, scale: 1.5 },
    ],
  });
  const at = kit.at;

  // Step 1 (lead: the reasoner node). The wire draws out of the set decision and arrives with the dive.
  tl.fromTo(wire, { scaleX: 0 }, { scaleX: 1, duration: at(0, 'arrive') - at(0, 'diveStart'), transformOrigin: '0% 50%' }, at(0, 'diveStart'));

  // Step 2 (lead: the explanation). Layer A steps back, the explanation lands as the camera arrives.
  tl.fromTo(why, { opacity: 0 }, { opacity: 1, duration: 0.14 }, at(1, 'diveStart'));
  tl.to(layerA, { opacity: 0.0, duration: 0.14 }, at(1, 'diveStart'));

  // Step 3 (lead: allow to hold). Marker travels during the dive; closed path draws after lock.
  tl.fromTo(valve, { opacity: 0 }, { opacity: 1, duration: 0.12 }, at(2, 'diveStart'));
  tl.fromTo(markerWrap, { xPercent: 0 }, { xPercent: 50, duration: at(2, 'arrive') - at(2, 'diveStart') }, at(2, 'diveStart'));
  tl.fromTo(lit, { scaleX: 0 }, { scaleX: 1, duration: at(2, 'arrive') - at(2, 'diveStart'), transformOrigin: '0% 50%' }, at(2, 'diveStart'));
  tl.fromTo(litCore, { scaleX: 0 }, { scaleX: 1, duration: at(2, 'arrive') - at(2, 'diveStart'), transformOrigin: '0% 50%' }, at(2, 'diveStart'));
  tl.fromTo(esc, { opacity: 0 }, { opacity: 1, duration: 0.1 }, at(2, 'arrive'));
  tl.fromTo(backLine, { scaleX: 0 }, { scaleX: 1, duration: at(2, 'scanEnd') - at(2, 'lock'), transformOrigin: '100% 50%' }, at(2, 'lock'));
  tl.fromTo(stop, { opacity: 0, scaleY: 0.2 }, { opacity: 1, scaleY: 1, duration: at(2, 'land') - at(2, 'scanEnd'), transformOrigin: '50% 100%' }, at(2, 'scanEnd'));
  tl.fromTo(closed, { opacity: 0 }, { opacity: 1, duration: 0.06 }, at(2, 'land'));

  // Step 4 (lead: the PASS line). The replay note follows the lead.
  tl.fromTo(pass, { opacity: 0 }, { opacity: 1, duration: 0.14 }, at(3, 'diveStart'));
  tl.fromTo(replayNote, { opacity: 0 }, { opacity: 1, duration: 0.1 }, at(3, 'arrive'));
  void [head, risk, para, passLine, nAllow, nHold, nBlock, decision];

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

const scene: SceneModule = { id: 'reasoner', title: 'Nemotron reasoner', steps, mount };
export default scene;
