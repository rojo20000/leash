import gsap from 'gsap';
import { fact, quote } from '../shell/content-access';
import { createInspection, verdictBadge } from '../shell/emphasis';
import type { SceneContext, SceneFrame, SceneHandle, SceneModule, StepCopy } from '../shell/types';
import queueImg from '../assets/img/approval-queue.png';
import './queue.css';

const STEPS = 4;
const IMG_W = 1500;
const IMG_H = 1100;
const WIN_W = 1200; // natural pixels visible at scale 1
const WIN_H = 880;

// Every view stays right of the dashboard sidebar (x 300) and below the Deploy control (y 60).
type View = { s: number; x0: number; y0: number };
const V_BOTH: View = { s: 1, x0: 300, y0: 135 };
const V_FIRST: View = { s: 1.16, x0: 378, y0: 130 };
const V_SECOND: View = { s: 1.16, x0: 378, y0: 245 };
const CARD_1 = { x: 380, y: 146, w: 1030, h: 426 };
const CARD_2 = { x: 380, y: 588, w: 1030, h: 401 };

function pose(v: View) {
  return {
    scale: v.s,
    xPercent: (-v.s * v.x0 / IMG_W) * 100,
    yPercent: (-v.s * v.y0 / IMG_H) * 100,
  };
}

/** Where a card sits in the window (percent) once the image is posed at view v. */
function place(node: HTMLElement, card: { x: number; y: number; w: number; h: number }, v: View) {
  node.style.left = `${(((card.x - v.x0) * v.s) / WIN_W) * 100}%`;
  node.style.top = `${(((card.y - v.y0) * v.s) / WIN_H) * 100}%`;
  node.style.width = `${((card.w * v.s) / WIN_W) * 100}%`;
  node.style.height = `${((card.h * v.s) / WIN_H) * 100}%`;
}

function steps(): StepCopy[] {
  return [
    {
      headline: 'Two alerts reach a person',
      sentence: 'In the scripted run, the injection block and the outside email were queued for review.',
      callouts: [
        { text: fact('queue', 'Queue item 1'), kind: 'code' },
        { text: fact('queue', 'Queue item 2'), kind: 'code' },
      ],
    },
    {
      headline: 'The poisoned read',
      sentence: 'The reviewer sees a plain-language reason beside the blocked call.',
      callouts: [
        { text: fact('policy', 'Reason code injection'), kind: 'code', verdict: 'block' },
        { text: fact('queue', 'Queue item 1'), kind: 'code' },
        { text: 'replay', kind: 'code' },
      ],
    },
    {
      headline: 'The outside email',
      sentence: 'The outside email was queued too, while the blocked Condition read at call 12 was not.',
      callouts: [
        { text: fact('policy', 'Reason code email'), kind: 'code', verdict: 'block' },
        { text: fact('queue', 'Queue item 2'), kind: 'code' },
        { text: 'replay', kind: 'code' },
      ],
    },
    {
      headline: 'A held call gets Approve or Deny',
      sentence: 'A held call waits for a person to choose, and this scripted run held none.',
      callouts: [
        { text: fact('queue', 'Control approve'), kind: 'name', verdict: 'allow' },
        { text: fact('queue', 'Control deny'), kind: 'name', verdict: 'block' },
        { text: fact('queue', 'Escalated in scripted run'), kind: 'code' },
        { text: fact('queue', 'Hold reason injection'), kind: 'code', verdict: 'hold' },
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
  const world = el(plate, 'div', 'queue-world');
  const label = el(world, 'div', 'queue-label stock-label peel');
  const stage = el(label, 'div', 'queue-stage');

  // Slot 1: the dashboard capture.
  const frame = el(stage, 'div', 'queue-frame');
  const win = el(frame, 'div', 'queue-window');
  const img = document.createElement('img');
  img.className = 'queue-img';
  img.src = queueImg;
  img.alt =
    'Leash approval queue showing two alert entries, q-0001 for read_document and q-0002 for send_email, each with a reason and an advisory explanation.';
  img.width = IMG_W;
  img.height = IMG_H;
  img.draggable = false;
  win.appendChild(img);
  const veil1 = el(win, 'div', 'queue-veil');
  const veil2 = el(win, 'div', 'queue-veil');
  // Overlay targets for the kit: where each card sits after its pose.
  const focus1 = el(frame, 'div', 'queue-focus queue-focus-1');
  const focus2 = el(frame, 'div', 'queue-focus queue-focus-2');
  place(focus1, CARD_1, V_FIRST);
  place(focus2, CARD_2, V_SECOND);
  // Veils hide the card that is not in focus.
  place(veil1, CARD_1, V_SECOND);
  place(veil2, CARD_2, V_FIRST);

  // Slot 2: verbatim strips, then the schematic of a held call (separate layout slot, never over the image).
  const info = el(stage, 'div', 'queue-info');
  const stripOne = el(info, 'div', 'queue-strip');
  el(stripOne, 'p', 'queue-line machine', quote('queue', '9 read_document'));
  el(stripOne, 'p', 'queue-line machine', quote('queue', 'q-0001'));
  const stripTwo = el(info, 'div', 'queue-strip');
  el(stripTwo, 'p', 'queue-line machine', quote('queue', '13 send_email'));
  el(stripTwo, 'p', 'queue-line machine', quote('queue', 'q-0002'));

  const sch = el(info, 'div', 'queue-schematic');
  el(sch, 'p', 'queue-sch-title', 'Schematic of a held call');
  const item = el(sch, 'div', 'queue-sch-item');
  const itemHead = el(item, 'div', 'queue-sch-head');
  itemHead.append(verdictBadge('hold', fact('pipeline', 'Outcome hold')));
  el(itemHead, 'span', 'queue-sch-bar queue-sch-bar--grow');
  el(item, 'span', 'queue-sch-bar queue-sch-bar--mid');
  const controls = el(item, 'div', 'queue-sch-controls');
  const approve = verdictBadge('allow', fact('queue', 'Control approve'));
  approve.classList.add('queue-ctl');
  controls.appendChild(approve);
  const deny = verdictBadge('block', fact('queue', 'Control deny'));
  deny.classList.add('queue-ctl');
  controls.appendChild(deny);

  el(stage, 'p', 'queue-caption', 'Dashboard capture from a separate run on synthetic data. Explanation wording can differ between runs.');

  gsap.set(img, { transformOrigin: '0 0', ...pose(V_BOTH) });

  const tl = gsap.timeline({ paused: true, defaults: { ease: 'none' } });
  tl.to({}, { duration: STEPS }, 0);

  const blockWord = (needle: string) => quote('queue', needle).trim().split(/\s+/)[2];
  const kit = createInspection({
    ctx,
    world,
    steps: STEPS,
    cues: [
      { step: 0, target: null },
      {
        step: 1, target: focus1, scale: 1, scan: true, dim: false,
        stamp: { text: blockWord('9 read_document'), form: 'block', anchor: 'br' },
      },
      {
        step: 2, target: focus2, scale: 1, scan: true, dim: false,
        stamp: { text: blockWord('13 send_email'), form: 'block', anchor: 'br' },
      },
      { step: 3, target: item, scale: 1.4 },
    ],
  });
  const at = kit.at;
  const span = (s: number, a: 'diveStart', b: 'arrive') => at(s, b) - at(s, a);

  // Step 2: the film moves to q-0001. The other card steps back under a veil.
  tl.to(img, { ...pose(V_FIRST), duration: span(1, 'diveStart', 'arrive') }, at(1, 'diveStart'));
  tl.fromTo(veil2, { opacity: 0 }, { opacity: 1, duration: span(1, 'diveStart', 'arrive') }, at(1, 'diveStart'));
  tl.fromTo(stripOne, { opacity: 0 }, { opacity: 1, duration: 0.06 }, at(1, 'land'));

  // Step 3: pan to q-0002.
  tl.to(stripOne, { opacity: 0, duration: 0.06 }, at(2, 'diveStart'));
  tl.to(veil2, { opacity: 0, duration: span(2, 'diveStart', 'arrive') }, at(2, 'diveStart'));
  tl.to(img, { ...pose(V_SECOND), duration: span(2, 'diveStart', 'arrive') }, at(2, 'diveStart'));
  tl.fromTo(veil1, { opacity: 0 }, { opacity: 1, duration: span(2, 'diveStart', 'arrive') }, at(2, 'diveStart'));
  tl.fromTo(stripTwo, { opacity: 0 }, { opacity: 1, duration: 0.06 }, at(2, 'land'));

  // Step 4: pull back, dim the image, bring up the schematic in its own slot.
  tl.to(stripTwo, { opacity: 0, duration: 0.06 }, at(3, 'diveStart'));
  tl.to(veil1, { opacity: 0, duration: span(3, 'diveStart', 'arrive') }, at(3, 'diveStart'));
  tl.to(img, { ...pose(V_BOTH), duration: span(3, 'diveStart', 'arrive') }, at(3, 'diveStart'));
  tl.to(img, { opacity: 0.55, duration: span(3, 'diveStart', 'arrive') }, at(3, 'diveStart'));
  tl.fromTo(sch, { opacity: 0 }, { opacity: 1, duration: 0.16 }, at(3, 'diveStart'));

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

const scene: SceneModule = { id: 'queue', title: 'Approval queue', steps, mount };
export default scene;
