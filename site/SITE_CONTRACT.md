# Leash scroll demo: site contract

This file is the contract for the demo website in `site/`. It is **not** the repo-root `CONTRACTS.md`, which belongs to the Python build. Never read that file for site work and never edit it.

Repo: `C:\Users\zarek\Downloads\tidalbyte26`. Branch: `site/scroll-demo` (already checked out). Do not commit or push.

Run every check in the **Bash tool**. The PowerShell tool on this machine is 5.1 and has no `&&`. In Bash the repo is `/c/Users/zarek/Downloads/tidalbyte26`.

## 1. Product

A scroll-driven product page for Leash, presented live at the Tidal Byte 2026 hackathon demo. Each feature is one pinned scene on a long scroll runway, so a presenter can stop and talk. The visitor moves with arrow keys or on-screen arrows, never by scrolling: the scroll position is an internal playhead moved only by code, and the visual changes in steps. Each step shows one short headline, one plain sentence and 2 to 4 small technical callouts. A fixed progress rail lists the features and highlights the current one. Arrow keys, space and page keys step through the page. Nothing autoplays.

Fixed on-screen order:

| Position | Scene id | Rail title | Priority |
|---|---|---|---|
| 1 | `hero` | Leash | must |
| 2 | `problem` | The problem | must |
| 3 | `pipeline` | The pipeline | must |
| 4 | `policy` | Policy engine | next |
| 5 | `injection` | Injection defense | next |
| 6 | `minimization` | Minimization | next |
| 7 | `anomaly` | Anomaly scoring | next |
| 8 | `reasoner` | Nemotron reasoner | next |
| 9 | `queue` | Approval queue | must |
| 10 | `audit` | Audit log | must |
| 11 | `results` | Results | must |
| 12 | `closing` | Limits and team | last |

The site must build and navigate correctly with any subset of these scenes present.

## 2. Folder layout and ownership

```text
site/
  SITE_CONTRACT.md        read-only for implementers
  MOTION_NOTES.md         read-only
  PRODUCT.md              read-only
  .impeccable/            read-only; never shipped or copied into code
  briefs/                 read-only
  .gitignore              shell
  index.html              shell
  package.json            shell only
  package-lock.json       shell only
  tsconfig.json           shell
  vite.config.ts          shell
  src/
    content.ts            READ-ONLY for everyone. Nobody edits it.
    main.ts               shell
    assets/img/approval-queue.png   shell copies it from docs/img
    shell/
      types.ts            shell: the scene interface in section 5
      content-access.ts   shell: fact, quote, table
      frame.ts            shell: frameAt, the pure scroll function
      registry.ts         shell: import.meta.glob and SCENE_ORDER
      runtime.ts          shell: Lenis, ScrollTrigger, scene updates
      rail.ts             shell: progress rail
      keyboard.ts         shell: keyboard navigation
      placeholder.ts      shell: fallback scene, outside the glob
      emphasis.ts         shell: inspection zoom kit (section 15)
      grounds.ts          shell: white or black ground per scene
      tokens.css          shell: design tokens
      base.css            shell: reset, stage, step copy, rail
    scenes/
      <id>.ts             owned by the one brief assigned that id
      <id>.css            owned by the one brief assigned that id
```

Assignment of scene ids to briefs:

| Brief | Scene ids |
|---|---|
| `a-hero-problem.md` | `hero`, `problem` |
| `b-pipeline-policy.md` | `pipeline`, `policy` |
| `c-injection-minimization-anomaly.md` | `injection`, `minimization`, `anomaly` |
| `d-reasoner-queue-audit.md` | `reasoner`, `queue`, `audit` |
| `e-results-closing.md` | `results`, `closing` |

Rules:
- The shell brief runs first and finishes before briefs A to E start. A to E may then run concurrently.
- A scene implementer edits only `site/src/scenes/<id>.ts` and `site/src/scenes/<id>.css` for its assigned ids.
- Only the shell agent runs `npm install` or edits `package.json`. A to E never do, even if a general instruction says to install missing dependencies. A to E never run `npm run build`, because concurrent builds clash.
- If a scene needs a new dependency or a contract change, stop and report it to the overseer. Do not make the change.
- Do not start a long-running dev server from an implementer task.

## 3. Stack

Exact versions for `package.json`, with no ranges:

| Package | Version | Kind |
|---|---|---|
| `vite` | `8.3.8` | dev |
| `typescript` | `5.9.3` | dev |
| `gsap` | `3.15.1` | runtime |
| `lenis` | `1.3.27` | runtime |
| `@fontsource-variable/bricolage-grotesque` | `5.3.0` | runtime |
| `@fontsource-variable/hanken-grotesk` | `5.3.0` | runtime |
| `@fontsource-variable/martian-mono` | `5.3.0` | runtime |

- Vanilla TypeScript. No framework.
- `vite.config.ts` sets `base: './'`.
- The built site makes no request to any outside host and works offline from any static file server. No CDN, remote font, analytics or remote image. Text that shows a URL is plain text, never an `<a>`, `<img>` or fetch.
- Images are imported from `src/assets/img/` so Vite rewrites them to relative paths.

## 4. Visual direction: "Bedside scan"

Leash is the last check before something reaches the patient. Every tool call is a printed label that must pass a scanner. The site is built from white label stock, black thermal print, high-alert red and wristband blue. The audience is hackathon judges watching a projector in a bright room, so **value contrast and large shapes come first and fine detail comes second**.

`site/.impeccable/surfaces/index-html.md` is the governing direction contract. Read it, but never copy its text into browser-delivered code, comments, `index.html` or any file in the build.

Principles:
1. **Label stock.** Each plate is one die-cut label with a soft layered shadow, perforations, a peeled corner, a blank barcode, registration marks and fine rules. One large label per scene. Never a grid of equal cards, and never a card inside a card.
2. **Form carries state before hue.** Allow is blue with a ring. Block is red with a bar. Hold is black with hatching and two bars. On a black ground the hold form inverts to white. The red `alert` form is reserved for the leak and for the failed audit, and it never says block.
3. **The inspection zoom is the signature.** On each highlight the camera dives in, the surroundings drop back, reticle brackets lock on, the red scan line sweeps and a verdict label stamps down with overshoot, all scrubbed by scroll (section 15).
4. **Machine strings sit in fixed registers.** Reason codes, ids, log lines and table values use `--font-machine` with tabular numerals. They never reflow during an animation.
5. **A scanned path stays marked** after the scanner passes.
6. **One lead per step.** Spend the boldness on the lead. Everything around it stays quiet.

Forbidden everywhere: cream or off-white backgrounds; purple-to-blue gradient; numbered `01/02/03` section labels; emoji; Unicode glyphs used as icons (including the check, cross, double-bar and diamond characters), so draw them with CSS or inline SVG; a uniform grid of glass cards; `backdrop-filter`; gradient text; neon or zero-offset colored glow; hard offset shadows; a colored bar down one side of a rounded box; eyebrow labels; all-caps labels, except verbatim source strings such as `BLOCK` and `HASH_MISMATCH`; anything copied from the reference sites in `MOTION_NOTES.md`.

**Medical imagery is a visual language only.** No drug names, doses, lot numbers, NDC codes, expiry dates, patient labels, or anything implying Leash handles medication. Barcodes are blank decorative bars that encode nothing. Microprint is drawn as fine dash rules and contains no text at all, which also keeps every piece of text at 12 px or larger.

### Ground map

The shell sets `data-ground` on each `<section>` from this fixed map. It is a deliberate rhythm: black scenes are the hits.

| Scene | Ground | Why |
|---|---|---|
| `hero` | white | the first label |
| `problem` | **black** | the leak hits hard |
| `pipeline` | white | the long read, and the red BLOCK on white |
| `policy` | white | measured and calm |
| `injection` | **black** | the attack is detected |
| `minimization` | white | clean redaction |
| `anomaly` | white | measured |
| `reasoner` | **black** | the advisory voice, set apart from the rules |
| `queue` | white | the dark screenshot sits on a white label |
| `audit` | **black** | the chain breaks |
| `results` | white | numbers must read from the back of the room |
| `closing` | white | long limitation text stays maximally legible |

### Design tokens (`site/src/shell/tokens.css`)

Scene CSS uses only these variables and must not introduce a new color. Verified contrast: all `--ink*`, `--allow-ink` and `--block-ink` pairs below are at least 4.5:1 on `--ground` and `--surface` of the same ground; white on `--red` is 5.88:1; white on `--blue` is 8.02:1.

```css
:root {
  --white: #ffffff;
  --black: #000000;
  --red: #c8102e;   /* high-alert fill; white text only */
  --blue: #0047bb;  /* wristband fill; white text only */

  --font-display: 'Bricolage Grotesque Variable', 'Trebuchet MS', sans-serif;
  --font-body: 'Hanken Grotesk Variable', 'Segoe UI', sans-serif;
  --font-machine: 'Martian Mono Variable', Consolas, monospace;

  --text-headline: clamp(2.25rem, 1.2rem + 3.8vw, 5rem);
  --text-sentence: clamp(1.125rem, 1.04rem + 0.36vw, 1.375rem);
  --text-callout: 0.9375rem;
  --text-plate: clamp(0.8125rem, 0.75rem + 0.28vw, 1rem);
  --text-machine: clamp(0.75rem, 0.7rem + 0.22vw, 0.9375rem);

  --space-1: 0.25rem; --space-2: 0.5rem; --space-3: 0.75rem;
  --space-4: 1rem; --space-6: 1.5rem; --space-8: 2rem; --space-12: 3rem;

  --rail-w: 184px;
  --topbar-h: 44px;
  --step-runway: 90svh;
  --radius-label: 10px;
  --radius-tag: 4px;

  --shadow-rest:
    0 1px 1px rgb(3 14 46 / 0.10), 0 4px 8px rgb(3 14 46 / 0.10),
    0 14px 28px rgb(3 14 46 / 0.12), 0 36px 72px rgb(3 14 46 / 0.14);
  --shadow-lift:
    0 2px 3px rgb(3 14 46 / 0.16), 0 10px 20px rgb(3 14 46 / 0.18),
    0 28px 56px rgb(3 14 46 / 0.22), 0 64px 120px rgb(3 14 46 / 0.24);
  --shadow-stamp:
    0 2px 2px rgb(3 14 46 / 0.28), 0 8px 16px rgb(3 14 46 / 0.28),
    0 22px 44px rgb(3 14 46 / 0.30);
}
@media (min-width: 768px) and (max-width: 1180px), (min-width: 768px) and (max-height: 680px) {
  :root {
    --rail-w: 148px;
    --text-headline: clamp(1.625rem, 3.1vw, 2.25rem);
    --text-sentence: 1rem;
    --text-callout: 0.8125rem;
    --text-plate: 0.8125rem;
    --text-machine: 0.75rem;
  }
}
@media (max-width: 767px) { :root { --step-runway: 75svh; --rail-w: 0px; } }

[data-ground='white'] {
  --ground: #ffffff; --surface: #ffffff;
  --ink: #000000; --ink-2: #2b3240; --ink-3: #505a6b;
  --rule: #d5dae3; --rule-strong: #6b7588;
  --allow-ink: #0047bb; --block-ink: #c8102e;
  --hold-ink: #000000; --hold-fill: #000000; --hold-on: #ffffff;
  --scan-ink: #c8102e;
  --inspect-dim: rgb(0 8 30 / 0.74);
}
[data-ground='black'] {
  --ground: #000000; --surface: #14171f;
  --ink: #ffffff; --ink-2: #d9dee8; --ink-3: #a7b0c0;
  --rule: #39404d; --rule-strong: #737d90;
  --allow-ink: #7ea6ff; --block-ink: #ff6b7c;
  --hold-ink: #ffffff; --hold-fill: #ffffff; --hold-on: #000000;
  --scan-ink: #ff3048;
  --inspect-dim: rgb(0 0 0 / 0.76);
  --shadow-rest: 0 2px 4px rgb(0 0 0 / 0.6), 0 18px 40px rgb(0 0 0 / 0.7);
  --shadow-lift: 0 4px 8px rgb(0 0 0 / 0.7), 0 32px 72px rgb(0 0 0 / 0.8);
}
```

Fill rule: `--red` and `--blue` are fills that carry white text. For colored text or thin lines use `--block-ink` and `--allow-ink`, which change per ground.

Shadows are static. To vary a shadow, stack a `.shadow-layer` and fade its `opacity`. Never animate `box-shadow`.

### Typography

- Headlines: `--font-display`, weight 800, `font-stretch: 85%`, `font-optical-sizing: auto`, line height 0.98, letter spacing `-0.03em`, `text-wrap: balance`, sentence case.
- Sentences: `--font-body`, weight 450, line height 1.45, `--ink-2`, max width 65ch.
- Callouts: `--font-body` weight 600, or `--font-machine` for `code`.
- Machine strings: `--font-machine`, weight 500, `font-stretch: 75%`, `font-variant-numeric: tabular-nums`, `white-space: pre-wrap`, `overflow-wrap: break-word`. Never use `overflow-wrap: anywhere` or `word-break: break-all` on machine strings: a reason code such as `INJECTION_DETECTED` stays one whole token whenever it fits its container.
- Only the hero wordmark may exceed 6rem, because it acts as the label's printed image.

### Shared print classes (`base.css`, usable in any plate)

| Class | What it draws |
|---|---|
| `.stock-label` | die-cut label: `--surface`, `--radius-label`, `--shadow-rest`, 1px `--rule` border |
| `.peel` | peeled top-right corner, drawn with a static pseudo-element |
| `.perf-x`, `.perf-y` | horizontal or vertical perforation line |
| `.blank-barcode` | blank decorative bars in `--ink`, irregular widths, encoding nothing |
| `.reg-mark` | small registration crosshair, drawn with CSS |
| `.micro-rule` | fine dashed rule standing in for microprint; contains no text |
| `.hatch` | diagonal hatching in `currentColor` |
| `.shadow-layer` | absolutely positioned `--shadow-lift` layer at `opacity: 0`, for fading |
| `.machine` | the machine string style above |
| `.v-mark`, `.v-badge` | verdict mark and badge; create them with `verdictMark` and `verdictBadge` (section 15) |

## 5. Scene module interface

`site/src/shell/types.ts` must export exactly this:

```ts
import type { SceneId } from '../content';

export type Verdict = 'allow' | 'block' | 'hold';
export type CalloutKind = 'code' | 'figure' | 'name';
export interface Callout { text: string; kind: CalloutKind; verdict?: Verdict }
export type Callouts =
  | [Callout, Callout]
  | [Callout, Callout, Callout]
  | [Callout, Callout, Callout, Callout];
export interface StepCopy { headline: string; sentence: string; callouts: Callouts }

/** A pure function of scroll position. See section 6. */
export interface SceneFrame {
  progress: number;     // 0..1 across this scene's runway
  step: number;         // integer, 0..steps-1
  stepProgress: number; // 0..1 within the current step
}

export interface SceneContext {
  root: HTMLElement;   // <section class="scene scene-<id>">
  plate: HTMLElement;  // empty element the scene fills
  reducedMotion: boolean;
  isNarrow(): boolean; // live: viewport width <= 767px
}

export interface SceneHandle {
  update(frame: SceneFrame): void;
  resize?(): void; // rebuild px-based measurements; shell re-applies the frame after
}

export interface SceneModule {
  id: SceneId;
  title: string;            // rail title from section 1
  steps(): StepCopy[];      // number of steps is steps().length, at least 1
  mount(ctx: SceneContext): SceneHandle;
}
```

Every scene file default-exports a `SceneModule` and imports its own CSS:

```ts
import gsap from 'gsap';
import { fact } from '../shell/content-access';
import type { SceneContext, SceneFrame, SceneHandle, SceneModule, StepCopy } from '../shell/types';
import './example.css';

function steps(): StepCopy[] {
  return [{
    headline: 'Short headline',
    sentence: 'One plain sentence.',
    callouts: [
      { text: fact('policy', 'Reason code email'), kind: 'code', verdict: 'block' },
      { text: fact('policy', 'Checks'), kind: 'name' },
    ],
  }];
}

function mount({ plate }: SceneContext): SceneHandle {
  plate.innerHTML = '<div class="example-dot"></div>';
  const tl = gsap.timeline({ paused: true, defaults: { ease: 'none' } });
  tl.fromTo(plate.querySelector('.example-dot'), { xPercent: 0 }, { xPercent: 300, duration: 1 });
  return { update(frame: SceneFrame) { tl.progress(frame.progress); } };
}

const scene: SceneModule = { id: 'policy', title: 'Policy engine', steps, mount };
export default scene;
```

Rules:
- `id` must equal the file name. The shell skips a file whose id differs.
- **No top-level code may read content.** Call accessors only inside `steps()` and `mount()`, so one bad key cannot break the whole page.
- The shell renders all step copy. A scene builds only its plate inside `ctx.plate`.
- A scene never touches anything outside `ctx.root`.
- A scene must not import `ScrollTrigger` or `lenis`, add scroll, wheel, key or resize listeners, or use timers, `requestAnimationFrame`, CSS animations or CSS transitions.
- GSAP in a scene is limited to `gsap.timeline({ paused: true })`, driven only by `tl.progress(...)` inside `update`. Do not use `onComplete` or any tween that plays by time.
- `update` must be idempotent and depend only on its `frame` argument and values fixed at mount.

### How the shell builds a scene

```html
<section id="<id>" class="scene scene-<id>" data-scene="<id>" tabindex="-1"
         aria-labelledby="<id>-title" style="--scene-steps: N">
  <div class="scene__stage">
    <div class="scene__copy">
      <h2 id="<id>-title" class="visually-hidden">Title</h2> <!-- h1 for the first scene -->
      <ol class="scene__steps">
        <li class="step" data-step="0">
          <h3 class="step__headline">...</h3>
          <p class="step__sentence">...</p>
          <ul class="step__callouts">
            <li class="callout callout--code callout--block">...</li>
          </ul>
        </li>
      </ol>
    </div>
    <div class="scene__plate"></div>
  </div>
</section>
```

Step text is set with `textContent`. Scene plates that insert content strings must also use `textContent`, or escape them.

## 6. Runway, sticky stage and scroll state

```css
.scene { position: relative; height: calc(var(--scene-steps) * var(--step-runway) + 100svh); }
.scene__stage { position: sticky; top: 0; height: 100svh; overflow: clip; }
```

- **Do not use ScrollTrigger `pin` or pin spacers.** ScrollTrigger only measures start and end.
- **Sticky breaks when an ancestor is a scroll container.** `html`, `body`, `#app`, `main`, `.scene` and any other ancestor of `.scene__stage` must never use `overflow: hidden`, `auto` or `scroll`. **Use `overflow: clip` instead**, for example `overflow-x: clip` on `body`, because `clip` cuts off overflow without creating a scroll container. `overflow: hidden` is allowed only on elements inside the stage that contain no sticky element.
- Do not put `transform`, `filter`, `perspective` or `contain` on `.scene` or its ancestors.

The shell's only step logic is this pure function in `src/shell/frame.ts`:

```ts
export function frameAt(scrollY: number, start: number, end: number, steps: number): SceneFrame {
  const clamp = (v: number) => Math.min(1, Math.max(0, v));
  const progress = clamp((scrollY - start) / Math.max(1, end - start));
  const scaled = progress * steps;
  const step = Math.min(steps - 1, Math.floor(scaled));
  return { progress, step, stepProgress: clamp(scaled - step) };
}
```

`start` and `end` come from a non-pinned ScrollTrigger with `start: 'top top'` and `end: 'bottom bottom'`. Every sync recomputes every scene's frame from the current `window.scrollY`. Scenes above the viewport therefore sit at progress 1 and scenes below at progress 0. Keyboard jumps, backward scrolling and reloads mid-page all render correctly because no state accumulates. The shell calls `update` only when a scene's progress changed, and always once after mount.

Step copy is also a pure function of the frame. The active step has opacity 1. It fades in during the first 12% of its slice, except step 0, and out during the last 8%, except the last step. Inactive steps get `visibility: hidden` and `aria-hidden="true"`.

## 7. Animation limits

Animate **only `transform` and `opacity`**. Never animate `width`, `height`, `top`, `left`, `right`, `bottom`, `margin`, `padding`, `filter`, `clip-path`, `background-color`, `color`, `box-shadow`, `stroke-dashoffset` or SVG geometry attributes.

- To draw a line, use `scaleX` or `scaleY` from a set transform origin.
- To change color, stack a second layer in the target color and fade its `opacity`.
- To move, prefer `xPercent` and `yPercent`. If a scene needs measured pixels, measure at mount and implement `resize()`.
- A `will-change: transform` is allowed only on the few elements that move.
- Static `box-shadow` is allowed. To vary a shadow, fade a `.shadow-layer`.
- **Midpoint rule:** presenters stop at a step's midpoint, so a step's key content must be fully legible by then. Every reveal in step `n` finishes by timeline time `n + 0.48` (`kit.at(n, 'settle')`). Never finish a reveal near the end of a step.
- Choreography: one lead per step, no uniform stagger, and accents land with the lead through `kit.at(step, beat)`. Use the kit for emphasis (section 15).

## 8. Reduced motion

If `prefers-reduced-motion: reduce` matches:
- The shell does not create Lenis, adds `is-reduced` to `<html>` and to every `.scene` section (scene CSS targets `.scene-<id>.is-reduced`), and reloads the page if the preference changes.
- `.scene` has `height: auto`; `.scene__stage` is `position: static; height: auto`.
- All steps are visible as a static list, with no opacity or transform applied.
- The plate is mounted once and receives one call: `update({ progress: 1, step: steps - 1, stepProgress: 1 })`.
- Keyboard and rail jumps move instantly.

**Every scene's final frame must therefore be a complete, legible picture of the whole scene.** Do not fade out information by the end of a timeline.

## 9. Layout at 1440x900, 1024x576 and 390 px

The hero is the one layout variant: its plate spans the stage as a full label and its copy sits on top at lower left. The shell owns that CSS.

Desktop, width 768 px and up: rail fixed at the left, `--rail-w` wide. The stage is a two-column grid inside the remaining width: copy `5fr`, plate `7fr`. Copy is left aligned and anchored to the lower part of the stage. The plate fills the column height minus padding.

Narrow, width 767 px or less:
- The rail becomes a fixed top bar, `--topbar-h` tall, showing the current title and a thin scene progress line.
- The stage becomes one column: plate on top (`minmax(0, 1fr)`), copy below (`auto`, `max-height: 48svh`).
- No horizontal page scroll. No scrolling inside a stage. All text at least 12 px.
- Tables must fit at 390 px through fewer visible rows per step, wrapped long ids (`overflow-wrap: break-word`) or stacked label and value rows. Machine strings use `white-space: pre-wrap` and reason codes stay whole.
- Prefer CSS for narrow layout. Use `ctx.isNarrow()` only if the DOM must differ, and read it inside `mount` or `resize`.

### Projector viewport: about 1024x576 (required)

The demo runs on a projector, so **1024x576 is a required third viewport**, alongside 1440x900 and 390 px. No overlap, clipping or overflow is allowed there. The compact query, used verbatim by the shell and scenes:

```css
@media (min-width: 768px) and (max-width: 1180px), (min-width: 768px) and (max-height: 680px) { }
```

At compact size:
- The stage grid is `grid-template-columns: minmax(0, 4fr) minmax(0, 6fr)`, column gap `--space-6`, padding `--space-4` plus the rail on the left. **All stage grids use `minmax(0, ...)` tracks at every size**, so long content can never push a column over its neighbor.
- Copy is vertically centered. Headline, sentence and callouts must fit the column height, using the compact type tokens.
- Rail titles are 13 px with tight gaps, so all 12 fit in 576 px.
- Dense tables use 12 px machine text, line height 1.2 and 2 px cell padding. A table that still does not fit splits into **two side-by-side columns or groups**. Never shrink text below 12 px and never let a table pass the plate's bottom edge.
- Plate content that sits beside a chain or diagram stacks or narrows so nothing passes the plate's right edge.

**Measurable pass, at 1440x900, 1024x576 and 390x844, for every step at its midpoint:** the headline's box does not intersect the plate; all plate text lies inside the plate and the viewport; and every element that contains text has `scrollWidth <= clientWidth`.

## 10. Reading content

`site/src/content.ts` is the only content source for scenes. Scenes read it through `src/shell/content-access.ts`:

```ts
export function fact(scene: SceneId, label: string): string;   // exact label; throws if absent
export function quote(scene: SceneId, needle: string): string; // the one quote containing needle, trimmed; throws on 0 or 2+ matches
export function table(scene: SceneId, id: string): Table;      // exact table id; throws if absent
```

A scene may read keys from any scene's content. Key notation in briefs:

- `F[scene/Label]` means `fact('scene', 'Label')`
- `Q[scene/needle]` means `quote('scene', 'needle')`
- `T[scene/id]` means `table('scene', 'id')`

The shell wraps each scene's `steps()` and `mount()` in `try/catch`. On failure it logs `[leash] scene <id> failed` with the error and omits that scene, so the rest of the page still works.

### Content rules

- Every claim, number and reason code comes from `content.ts`. Headlines and sentences may be fresh but must assert nothing the sources do not. Use the copy in your brief.
- Numbers on screen must be read through an accessor, except numbers already written in the brief's supplied copy.
- All data is synthetic, and the site says so.
- Never show the NVIDIA key or any key-like placeholder.
- **No invented data:** no made-up hashes, timestamps, JSON fields, scores, rule ids or log lines. Callouts use reason codes such as `EMAIL_DOMAIN_NOT_ALLOWED`. Do not name anomaly features. Schematic visuals use blank bars, ticks and shapes that cannot be mistaken for real values.
- Do not write out the hidden injection sentence. It is not in `content.ts`. Show it as a masked bar.
- **Speed:** display `3.06 µs` and `12.36 µs`, computed with `Number(value).toFixed(2)`. Results tables keep the exact `3.063`, `12.363` and unit `us`.
- **Stages:** seven numbered stages plus an unnumbered `Decide` between stages 5 and 6. In the README diagram, stages 6 and 7 are parallel branches out of `Decide`. Stage markers read `Stage 1`, never `01`.
- **Hold:** the scripted run has `0 escalate`. Allow and block are shown from that run. Hold is a real pipeline outcome this run did not take. Never imply the scripted run held a call.
- **Wider workload:** `T[results/gateway-rates]` comes from the separate 245-call workload, not the scripted run. Label it that way.
- **Queue:** only calls 9 and 13 were queued (`q-0001`, `q-0002`). Call 12 was blocked but has no queue line. Never claim every block is queued.
- **Queue controls:** the screenshot shows two alerts, whose real buttons are Dismiss and Confirm block (`dashboard/app.py:141,143`). Approve and Deny appear on held calls. Never draw Approve or Deny on top of the screenshot's alert entries.
- **Audit line:** `line 8` is zero-indexed, so it is the ninth entry, call 9, `read_document BLOCK INJECTION_DETECTED`. Keep the label `line 8` exactly and make that row the edited row.
- **Replay:** the scripted run's Nemotron explanations are `replay` mode. Label them that way and never imply a live call.
- **Limitations:** the closing scene states the README's limitations plainly.
- **Leak wording:** in `problem` the leak says `leaked`, never block.
- **Reasoner:** Nemotron can only add caution, the reasoner itself changes no decision, the only open path is allow to hold, and the latency callout reads `Lightning, all roles: ...`.
- **Results latency:** callouts stay prefixed `Lightning:` and `NemoGuard`.
- **Queue caption:** the separate-run caption stays on the screenshot.
- **Medical imagery:** visual language only (section 4). No drug names, doses, lot numbers, NDC codes or patient labels. Barcodes are blank.

## 11. CSS scoping

All CSS is global. In `<id>.css`:

- Every selector starts with `.scene-<id>`.
- Scene-only classes are prefixed `<id>-`, for example `.scene-audit .audit-row`.
- Custom properties are prefixed `--<id>-` and declared under `.scene-<id>`.
- No `@keyframes`, `@font-face`, `@import`, `:root`, `html`, `body` or bare element selectors.
- Do not restyle `.scene`, `.scene__stage`, `.scene__copy`, `.step*`, `.callout*`, `.inspect-*`, `.v-mark`, `.v-badge` or the rail. The plate may be styled as `.scene-<id> .scene__plate`.
- Use only the semantic tokens in section 4. Legacy names (`--film-*`, `--bone`, `--silver`, `--tracer`, `--allow`, `--block`, `--hold`, `--line`, `--radius-plate`) exist only as temporary aliases and must not remain in a restyled scene.
- `@media` blocks are allowed, and selectors inside them follow the same rules.

## 12. Registry and placeholder

`src/shell/registry.ts`:

```ts
export const SCENE_ORDER: SceneId[] = ['hero','problem','pipeline','policy','injection','minimization','anomaly','reasoner','queue','audit','results','closing'];
const modules = import.meta.glob<{ default: SceneModule }>('../scenes/*.ts', { eager: true });
```

- Order comes only from `SCENE_ORDER`. Missing scenes are skipped. Files with unknown ids are ignored with a console warning.
- The placeholder is `src/shell/placeholder.ts`, deliberately outside `src/scenes/`, so it cannot collide with any scene file. It renders **only when no real scene registers or mounts**. Once one real scene mounts, the placeholder is not in the DOM.

## 13. Navigation: stops, keyboard, arrows and rail

The page is moved only by code. Scroll position is the internal playhead; the runway, `frameAt` and the scene interface are unchanged.

**Stops.** The shell builds an ordered list of stops, one per step of each rendered scene, at `start + ((step + 0.5) / steps) * (end - start)`, so key content is legible. It recomputes them on refresh and resize and snaps to the current stop with no animation. On load it lands on the first stop, or the first stop of a valid hash's scene. On reload it snaps back to the stop it was on. Under reduced motion there is one stop per scene, at its start.

| Key | Action |
|---|---|
| `ArrowRight`, `ArrowDown`, `Space` | next stop, continuing into the next scene |
| `ArrowLeft`, `ArrowUp`, `Shift+Space` | previous stop |
| `PageDown` / `PageUp` | first stop of the next / previous scene |
| `Home` / `End` | first / last stop |

- Ignore the event if `event.defaultPrevented`, if Ctrl, Alt or Meta is held, or if the target is text entry (`input, textarea, select, [contenteditable], [role="textbox"]`). Focus on a button or link does **not** block navigation keys. Space or Enter on a focused button uses native activation, exactly once.
- Call `preventDefault` only for keys the shell handles.
- Each move is a short programmatic tween of about 0.7 to 1.2 s, scaled by distance. Rapid presses advance from the pending target and clamp at both ends. Nothing moves without a user action.
- **Normal motion disables user scrolling:** wheel, trackpad, touch drag, scrollbar and middle-click autoscroll do not move the page (Lenis `virtualScroll` returns false, wheel and touchmove are prevented, the scrollbar is hidden). Reduced motion keeps ordinary scrolling.
- **On-screen arrows:** fixed Previous and Next `<button>`s with `aria-label`s and inline SVG arrows, at least 44 px, `disabled` at the ends. They sit in the white rail strip (desktop) or the top bar (narrow), so they never cover step copy or plate content.
- The current scene is the last rendered scene whose `start <= scrollY + 1`.
- **Narrow scene menu:** at 767 px or less the top bar keeps the current title and adds a `<button aria-expanded aria-controls>` labeled `Scenes` that opens the same rail list as a panel. Opening moves focus to the current entry. Choosing an entry goes to that scene's first stop and closes it. `Escape` closes it and returns focus to the button, and a click outside closes it. It opens and closes instantly, with no animation, and every entry is at least 40 px tall.
- Rail entries are `<a href="#<id>">` in an `<ol>` with `aria-current="true"` on the current entry and no numbers. A rail activation goes to the scene's first stop, then moves focus to the target `<section>` with `focus({ preventScroll: true })`.

## 14. Check commands

Shell brief:

```bash
cd /c/Users/zarek/Downloads/tidalbyte26/site && npm install && npm run typecheck && npm run build
```

Briefs A to E:

```bash
cd /c/Users/zarek/Downloads/tidalbyte26/site && npm run typecheck
```

`npm run typecheck` is whole-project, and five agents run it concurrently, so another agent's half-written file can make it exit non-zero. **You are responsible only for errors in your own files.** `tsc` prints each error as `src/scenes/<file>.ts(line,col): error TS...`.

Your check passes when `tsc` actually ran and **no error line starts with `src/scenes/<one of your ids>.`**. Ignore errors that start with another scene's path. If an error starts with `src/shell/`, `src/main.ts` or `src/content.ts`, or `tsc` could not start, report it to the overseer and do not fix it.

To list only your errors, replace the ids below with yours:

```bash
cd /c/Users/zarek/Downloads/tidalbyte26/site && npm run typecheck 2>&1 | grep -E '^src/scenes/(hero|problem)\.' ; echo "own-error scan finished"
```

Pass means the scan prints only `own-error scan finished`.

## 15. Inspection zoom kit (`src/shell/emphasis.ts`)

The shell owns this file. Scenes call it and never reimplement it. It is a pure function of the scene frame, so it is scrubbed, reversible and safe under keyboard jumps and reloads. It writes only `transform` and `opacity`, apart from a discrete `visibility` flip on hidden overlay parts.

### Exact API

```ts
import type { SceneContext, SceneFrame, Verdict } from './types';

export type StampForm = Verdict | 'alert';
export type StampAnchor = 'center' | 'br' | 'tr' | 'bl';

export interface StampSpec {
  text: string;          // from content, or a verbatim token of it
  form: StampForm;
  anchor?: StampAnchor;  // default 'br': overlaps the target's lower right, so its text stays readable
  land?: number;         // fraction of the step when it hits; default BEATS.land
}

export interface InspectCue {
  step: number;                // 0-based; at most one cue per step
  target: HTMLElement | null;  // null is the wide shot
  scale?: number;              // requested zoom, default 1.6; never below 1
  narrowScale?: number;        // at width <= 767px; default Math.min(scale, 1.5)
  pad?: number;                // px kept clear around the target, default 16 (10 when narrow)
  dim?: boolean;               // default: true when target is set
  reticle?: boolean;           // default: true when target is set
  scan?: boolean;              // default false
  stamp?: StampSpec;
  mark?: boolean;              // reduced motion: draw a static reticle on this target; default true
}

export interface InspectionOptions {
  ctx: SceneContext;
  world: HTMLElement;      // the content the camera moves; a descendant of viewport
  viewport?: HTMLElement;  // the clipped window; default ctx.plate
  steps: number;           // the scene's step count
  cues: InspectCue[];
}

export interface Inspection {
  update(frame: SceneFrame): void;      // call after tl.progress(frame.progress)
  resize(): void;                       // re-measure and re-render the last frame
  at(step: number, beat: keyof typeof BEATS): number; // timeline time of a beat
}

export const BEATS: {
  readonly diveStart: 0.02; readonly arrive: 0.26; readonly lock: 0.28;
  readonly scanStart: 0.28; readonly scanEnd: 0.40; readonly land: 0.42; readonly settle: 0.48;
};

export function createInspection(options: InspectionOptions): Inspection;
export function verdictMark(form: StampForm): HTMLElement;              // aria-hidden drawn mark
export function verdictBadge(form: StampForm, text: string): HTMLElement; // mark plus text, sets textContent
```

### How a scene uses it

```ts
const world = document.createElement('div');
world.className = 'audit-world';
plate.append(world);
// ...build all plate content inside world...

const tl = gsap.timeline({ paused: true, defaults: { ease: 'none' } });
tl.to({}, { duration: STEPS }, 0); // exactly one timeline unit per step

const kit = createInspection({
  ctx, world, steps: STEPS,
  cues: [
    { step: 0, target: null },
    { step: 3, target: editedRow, scale: 2.2, scan: true,
      stamp: { text: fact('audit', 'Failure reason'), form: 'alert' } },
  ],
});
// Land a scene accent exactly on the stamp:
tl.to(brokenLink, { opacity: 1, duration: 0.06 }, kit.at(3, 'land'));

return {
  update(f) { tl.progress(f.progress); kit.update(f); },
  resize() { kit.resize(); },
};
```

**Timeline rule (applies to every scene):** every scene timeline has a total duration of exactly its step count, enforced with `tl.to({}, { duration: STEPS }, 0)`. Step `n` occupies time `n` to `n + 1`. Some current scenes end early, so their beats drift from the step copy. Fix that during the restyle.

### Required behavior

**DOM.** The kit adds `inspect-viewport` to the viewport and `inspect-world` to the world, and appends one `.inspect-overlay` to the viewport (`position: absolute; inset: 0; pointer-events: none; z-index: 20; aria-hidden="true"`). The overlay holds the dim panels, four reticle corners, scan line, trace line and one stamp per stamped cue. Overlay parts are not scaled by the camera, so they stay crisp.

```css
.inspect-viewport { position: relative; overflow: clip; }
.inspect-world { position: relative; transform-origin: 0 0; will-change: transform; }
```

The world defaults to `width: 100%; height: 100%`. It may be larger than the viewport, for the pipeline track.

**Measuring.** Measure each target in world layout coordinates by summing `offsetLeft` and `offsetTop` up the `offsetParent` chain to `world`. This ignores all transforms, so the current scroll state cannot corrupt a measurement. A target must be an `HTMLElement` that is not `display: none`. If the chain never reaches `world`, log `[leash] inspect target outside world` and treat the cue as wide. Re-measure on `resize()`, after `document.fonts.ready`, when any image in the world loads, and from one `ResizeObserver` on the viewport and world, then re-render the last frame.

**Pose.** For target rect `r`, viewport `vw x vh`, world `W x H`, and `p = pad`:

```text
s  = max(1, min(requested, (vw - 2p) / r.w, (vh - 2p) / r.h))
tx = clampAxis(vw / 2 - s * (r.x + r.w / 2), vw, s * W)
ty = clampAxis(vh / 2 - s * (r.y + r.h / 2), vh, s * H)
clampAxis(t, view, size) = size <= view ? (view - size) / 2 : min(0, max(view - size, t))
```

A wide shot is `s = 1` with the same clamp around the world's center. If a world is larger than the viewport, a scale 1 cue pans to its target.

**Scrub, for step `k` at local progress `u = frame.stepProgress`:**

| Part | Window in `u` | Motion | Ease |
|---|---|---|---|
| Camera | `diveStart` to `arrive` | from the pose of step `k-1` to step `k`; interpolate `log(s)` and the focus point | `power3.inOut` |
| Dim | `diveStart` to `0.20` | opacity 0 to 1. If both steps are dimmed it stays at 1 and the hole travels | `power2.out` |
| Previous reticle and stamp | `0` to `0.06` | opacity to 0 | linear |
| Reticle | `lock` to `lock + 0.05` | corners close in from 1.35x the rect offset, opacity 0 to 1 | `expo.out` |
| Scan | `scanStart` to `scanEnd` | red line crosses the target top to bottom; visible only in this window | linear |
| Trace | `scanStart` to `scanEnd` | line on the target's left edge grows with `scaleY` and **stays** until the next step | linear |
| Stamp | `land - 0.06` to `land` | scale 2.6 to 1 with overshoot, rotation -9deg to -4deg, opacity reaches 1 within the first 40% | `back.out(2.4)` |
| Impact | `land` to `settle` | world scale multiplied by `1 + 0.025 * sin(pi * v)`, only on stamped cues | none |

Before step 0 the camera rests at the pose of step 0's cue. A step with no cue is a wide shot. Everything has finished by `settle` (0.48), so the step is fully legible at its midpoint and the rest of the step is a still frame for the presenter.

**Dim hole.** Use four solid `--inspect-dim` panels around the target, positioned only with `transform` (translate plus `scaleX`/`scaleY` of a 100%-sized panel). Do not use `clip-path`, `mask`, `filter` or an oversized `box-shadow`.

**Scan and reticle.** The scan line is a full-width 3px element in `--scan-ink`, translated and scaled with `scaleX` to the target's on-screen width. Reticle corners are fixed-size L brackets in `--scan-ink`, each moved by `transform`, never resized.

**Stamp.** A label with `--shadow-stamp`, a double keyline, `--font-display` weight 800, size `clamp(1.75rem, 1rem + 3vw, 4.25rem)`, and the form's mark.

| Form | Fill | Text | Mark |
|---|---|---|---|
| `allow` | `--blue` | white | ring |
| `block` | `--red` | white | bar |
| `hold` | `--hold-fill` with `.hatch` border band | `--hold-on` | two bars |
| `alert` | `--red` | white | drawn warning triangle |

Measure the stamp, scale it down with its resting transform if it is wider than `vw - 16px`, and clamp its center so its resting box stays fully inside the viewport.

**Reduced motion** (`ctx.reducedMotion`): the world has no transform. There is no dim, scan, impact or stamp animation. Each cue with a target and `mark !== false` gets one static reticle at its measured rect. Stamps do not overlap content: every stamp is listed, in step order, in a static `.inspect-key` row placed after the world in normal flow, using `verdictBadge`. Nothing is hidden. In this mode the world uses `height: auto`, and a world wider than the plate must reflow through the scene's `.is-reduced` CSS.

**390 px.** Scale is never below 1, so text set at 12 px or larger stays there. The pose formula keeps the target inside the viewport. A target must fit the viewport at scale 1, so choose a smaller target if it does not.

**Interaction with the runtime.** No listeners on scroll, wheel or keys, no timers and no `requestAnimationFrame`. `update` must be idempotent.
