# Brief C: injection, minimization and anomaly restyle

This is a **visual restyle of existing, working scene files** for the Leash scroll demo, a page presented live to Tidal Byte 2026 hackathon judges on a projector in a bright room. Leash is a runtime security gateway for clinical AI agents. Keep each scene's facts, structure and step copy. Replace its look and its emphasis.

**Your contract is `site/SITE_CONTRACT.md`, not the repo-root `CONTRACTS.md`.** Read it in full, especially section 4 (Bedside scan) and section 15 (inspection zoom kit). Do not read or edit the root `CONTRACTS.md` or `graph/`.

Repo: `C:\Users\zarek\Downloads\tidalbyte26`, branch `site/scroll-demo` (already checked out). Do not commit or push. Run commands in the **Bash tool**, because PowerShell 5.1 has no `&&`.

## Read and load first

1. Your scene files as they exist now, plus `site/src/shell/emphasis.ts` and `site/src/shell/tokens.css`.
2. `site/.impeccable/surfaces/index-html.md`, the governing direction. **Never copy its text into code, comments or CSS.**
3. `site/PRODUCT.md`.
4. The Impeccable craft floor: read `C:\Users\zarek\.claude\skills\impeccable\reference\craft-floor.md`. Where it suggests animating blur, clip-path, mask or shadow, this project's transform-and-opacity rule wins.
5. Load the `ui-animation:choreograph` skill with the Skill tool, and apply its Lead, Support, Decoration and Static roles.

## Owned paths

- `site/src/scenes/injection.ts`
- `site/src/scenes/injection.css`
- `site/src/scenes/minimization.ts`
- `site/src/scenes/minimization.css`
- `site/src/scenes/anomaly.ts`
- `site/src/scenes/anomaly.css`

Edit nothing else. Never run `npm install`, edit `package.json` or run the build, even if a general instruction tells you to install missing dependencies. If you need a new dependency, a kit change or a contract change, stop and report it to the overseer.

## Rules for every scene here

- **Keep `steps()` exactly as built**, unless this brief names a change. Keep content keys, the scene id, title and step count.
- Key notation: `F[scene/Label]` is `fact('scene', 'Label')`, `Q[scene/needle]` is `quote('scene', 'needle')`, `T[scene/id]` is `table('scene', 'id')`, from `../shell/content-access`.
- Build all plate content inside one `world` element, then call `createInspection`. In `update`, call `tl.progress(frame.progress)` and then `kit.update(frame)`. In `resize`, rebuild anything measured and call `kit.resize()`.
- **The timeline's total duration must equal the step count exactly:** `tl.to({}, { duration: STEPS }, 0)`. Step `n` occupies time `n` to `n + 1`. Cue `step` values are 0-based, while the tables below number steps from 1.
- **Midpoint rule:** presenters stop at each step's midpoint. Everything that step reveals must be at full opacity and in place by `kit.at(step, 'settle')` (0.48 of the step). Never finish a reveal near the end of a step.
- **Three required viewports:** 1440x900, about 1024x576 (the projector) and 390 px. No overlap, clipping or overflow at any of them. Use the compact query in contract section 9.
- Reason codes and other machine tokens stay whole. Never use `overflow-wrap: anywhere` or `word-break: break-all` on them.
- Each table row below is one step and becomes one cue. **One Lead per step.** Land accents with the lead using `kit.at(step, 'arrive' | 'lock' | 'land' | 'settle')`. No uniform stagger. Decoration only fades. Static elements do not animate.
- Every animation is scrubbed by the paused timeline. Animate only `transform` and `opacity`. No timers, listeners, autoplay, ScrollTrigger, Lenis, CSS transitions, CSS animations or animated shadows.
- Zoom targets must be `HTMLElement`s inside the world, not `display: none`, and must fit the plate at scale 1 at 390 px. The kit keeps them inside the plate.
- Every CSS selector starts with `.scene-<id>`. Scene classes are prefixed `<id>-`. Use only semantic tokens from contract section 4, and remove all legacy tokens.
- Verdict form comes first: allow is blue with a ring, block is red with a bar, hold is black with hatching and two bars. Use `verdictMark` and `verdictBadge`. **Replace every Unicode icon glyph.**
- Machine strings use `.machine` in fixed registers. Text stays at 12 px or larger.
- Reduced motion: the shell calls `update` once with the final frame, and the kit leaves a static marked picture. The final frame must show the complete scene, with nothing hidden.
- 390 px: plate above copy, no horizontal page scroll, no scrolling inside the stage.
- Forbidden: cream or off-white, purple-to-blue gradient, `01/02/03` labels, emoji, glass, gradient text, neon glow, hard offset shadows, side-stripe boxes, eyebrow or all-caps labels (verbatim source strings such as `BLOCK` are fine), remote URLs, and anything from the reference sites.
- **Medical imagery is a visual language only.** No drug names, doses, lot numbers, NDC codes, expiry dates, patient labels or anything implying Leash handles medication. Barcodes are blank bars. Microprint is drawn rules with no text.
- Data is synthetic. No invented hashes, timestamps, JSON fields, scores, rule ids or log lines. Never show the NVIDIA key.

## Scene `injection` (black ground, 5 steps)

**World.** Three sensor rails on a dark `--surface` label. The document is a white die-cut label with blank bars. The wiring stays the message: only the TF-IDF wire reaches a heavy red block target; the other two reach one hatched hold target. Replace any glyphs with `verdictBadge`.

| Step | Lead and zoom target | Scale | Support | Decoration | Scan and stamp | Static |
|---|---|---|---|---|---|---|
| 1 Three detectors | Wide: all three lanes | 1 | document label enters | registration marks | none | lanes |
| 2 Only TF-IDF can block | TF-IDF lane and block target (`.injection-target--block`) | 1.8 | TF-IDF wire draws first; the two hold wires land together at `lock` | hold target stays quiet | scan along the block target; no stamp | other lanes |
| 3 Poisoned referral | The document label at the block target (`.injection-doc`) | 2.4 | log lines fully visible by `settle` | block fill lands with the stamp | **scan, then `BLOCK`, form `block`, anchor `br`.** Text from `quote('injection', '9 read_document').trim().split(/\s+/)[2]` | wiring |
| 4 Held-out scores | Recall value (second `.injection-metric`) | 1.8 | other three metrics rest at full opacity | none | no stamp, reticle only | wiring dimmed |
| 5 What it still misses | The `combined` holdout row in the table | 2.0 | rest of table | none | scan the row; no stamp, because this is a limitation and must not look like a win | wiring |

**Measured defects to fix.** (1) Step 5's holdout rows measured 0.22 opacity at the midpoint: the whole table must be at full opacity by `kit.at(4, 'settle')`. (2) At 390 px, reason codes wrap mid-token (`INJECTION_` / `DETECTED`) in steps 1 to 4. Size or lay out the targets so `INJECTION_DETECTED` and `INJECTION_SUSPECTED` each stay on one line, for example by stacking the target word above its code at 12 px or larger with `white-space: nowrap`.

Do not rename table rows, and do not assert that row `jailbreak` is NemoGuard. Remove the uniform stagger on metrics and rows: metrics appear together, and table rows appear together.

Final and reduced-motion frame: wiring and holdout table together.

## Scene `minimization` (white ground, 4 steps)

**World.** A white clinical note label of blank black bars, with five identifier spans as heavy black bars. Each redacted span flips to a white tag with a black keyline holding only its kind: `DOB`, `EMAIL`, `MRN`, `PHONE`, `SSN`. Show no sample values and no bracket placeholder syntax.

| Step | Lead and zoom target | Scale | Support | Decoration | Scan and stamp | Static |
|---|---|---|---|---|---|---|
| 1 Only what's needed | Wide: the note | 1 | none | perforation | none | bars |
| 2 Value goes, type stays | The `SSN` span | 3.0 | SSN flips first at `lock`; the other four flip after it with **shrinking** gaps, ending by `settle` | none | scan crosses the SSN span at `scanStart` | note |
| 3 Presidio follows | The note's middle (`.minimization-note-inner`) | 1.35 | pass line sweeps; non-identifier rows drop away with shrinking gaps | none | no kit scan, because the pass line is the sweep | tags |
| 4 Perfect on templated notes | Table (`.minimization-table`) | 1.3 | note rests beside it | none | no stamp: this result carries a caveat | note |

Final and reduced-motion frame: redacted note and all five table rows.

## Scene `anomaly` (white ground, 4 steps)

**World.** A strip of blank ticks like a printed rule, keeping the visible word `schematic`. The window is a heavy black bracket. Below it, a table with thick recall bars in black. **Do not name any anomaly features.** Scenario names are allowed.

| Step | Lead and zoom target | Scale | Support | Decoration | Scan and stamp | Static |
|---|---|---|---|---|---|---|
| 1 Behavior over time | The bracket at its start (`.anomaly-track`) | 1.4 | ticks at rest | registration marks | none | table hidden |
| 2 Each call gets a score | The track, bracket sliding | 1.25 | bracket slides from `arrive` through `settle` | none | scan once at `scanStart` | ticks |
| 3 Measured by scenario | The table (`.anomaly-table`) | 1.3 | recall bars draw together, with `exfil_email` first by a hand-set offset | none | no stamp | strip |
| 4 Not the forest | The `exfil_email` and `off_role_resources` rows, as a new wrapper `.anomaly-guarded` | 1.8 | both `deterministic guard` tags land together at `land` | other rows stay readable | scan across both rows; no stamp | strip |

The two guarded rows are already adjacent in the source table. Wrap them in `.anomaly-guarded` without changing row order, values or columns.

Final and reduced-motion frame: strip, table and both guard tags.

## Check and acceptance

Run this in the Bash tool:

```bash
cd /c/Users/zarek/Downloads/tidalbyte26/site && npm run typecheck
```

It is whole-project and other agents run it concurrently, so it may exit non-zero because of their files. You are responsible only for your own. To list only your errors:

```bash
cd /c/Users/zarek/Downloads/tidalbyte26/site && npm run typecheck 2>&1 | grep -E '^src/scenes/(injection|minimization|anomaly)\.' ; echo "own-error scan finished"
```

Pass means `tsc` ran and the scan prints only `own-error scan finished`. If an error names `src/shell/`, `src/main.ts` or `src/content.ts`, or `tsc` cannot start, report it to the overseer and do not fix it.

Then run this self-audit from the site folder. It must print only `audit finished`:

```bash
cd /c/Users/zarek/Downloads/tidalbyte26/site && grep -nE 'ScrollTrigger|lenis|setTimeout|setInterval|requestAnimationFrame|addEventListener|fetch\(|https?://|[✓✕‖◆]' src/scenes/injection.ts src/scenes/minimization.ts src/scenes/anomaly.ts ; grep -nE '^\s*(transition|animation)(-[a-z]+)?:|@keyframes|backdrop-filter|--(film-|bone|silver|tracer|allow\)|block\)|hold\)|line\)|radius-plate)|#[0-9a-fA-F]{3,8}\b' src/scenes/injection.css src/scenes/minimization.css src/scenes/anomaly.css ; grep -LE 'createInspection' src/scenes/injection.ts src/scenes/minimization.ts src/scenes/anomaly.ts ; echo "audit finished"
```

Report: files changed, the check's last 10 lines, deviations and open questions.
