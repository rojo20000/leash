# Brief D: reasoner, queue and audit restyle

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

- `site/src/scenes/reasoner.ts`
- `site/src/scenes/reasoner.css`
- `site/src/scenes/queue.ts`
- `site/src/scenes/queue.css`
- `site/src/scenes/audit.ts`
- `site/src/scenes/audit.css`

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

## Scene `reasoner` (black ground, 4 steps)

**World.** A dark `--surface` label. The one-way valve is a heavy horizontal scale: allow, hold, block, using `verdictBadge` in place of all existing Unicode glyphs (`✓`, `✕`, `‖`, `◆`). The closed return path uses a drawn stop, not a glyph.

**Corrected facts that must survive.** Nemotron can only add caution. The reasoner itself changes no decision. **The only open path is allow to hold.** Keep the `steps()` copy exactly, including the callout `Lightning, all roles: ...`. Keep every explanation labeled `replay`. Keep the existing text `Nemotron detectors and judges escalate to a human`. Change the closed-path label from `✕ no path back to allow from hold or block` to the same words without the glyph.

| Step | Lead and zoom target | Scale | Support | Decoration | Scan and stamp | Static |
|---|---|---|---|---|---|---|
| 1 After the decision | The reasoner node (`.reasoner-node--reasoner`) | 1.6 | wire draws from the already-set decision and arrives at `arrive` | none | none, reticle only | decision node |
| 2 A readable reason | The explanation (`.reasoner-why`) | 1.45 | risk line and `replay` tag land together | none | scan once down the explanation | valve hidden |
| 3 Only adds caution | The allow-to-hold segment of the valve (`.reasoner-track`) | 2.0 | marker moves to hold during the dive; closed path draws after `lock` and its stop lands at `land` | none | scan the open segment; **stamp `hold`, form `hold`, anchor `tr`**, text from `F[pipeline/Outcome hold]` | nodes |
| 4 Grounded or thrown out | The `PASS 5` line (`.reasoner-pass`) | 1.5 | replay note | none | no stamp | valve stays |

The hold stamp in step 3 illustrates the valve's direction. It must not read as a scripted-run outcome, so keep the `replay` label away from it. The `reasoner-esc` text stays visible beside it.

Final and reduced-motion frame: valve, replay explanation and `PASS 5` line.

## Scene `queue` (white ground, 4 steps)

**World.** The screenshot sits in a white die-cut label with perforations. Keep the existing view math that keeps the sidebar and `Deploy` out of frame. **Keep the caption exactly:** `Dashboard capture from a separate run on synthetic data. Explanation wording can differ between runs.`

The image's pan and zoom stay the scene's own `pose()` tweens, because they keep the `Deploy` control out of frame. Add the kit with `world` wrapping `.queue-stage`, for dim, reticle, scan and stamp around **overlay target elements**: add two empty absolutely positioned `<div>`s inside `.queue-frame`, `.queue-focus-1` and `.queue-focus-2`, sized to where each card sits after its pose. Their cues use `scale: 1`, so the kit does not double-zoom the image.

**Measured defects to fix.**
- **Crop.** Step 3's zoom currently shows a cut-off `Metrics` heading at its bottom edge. Every view must keep the visible natural-pixel region inside x 300 to 1420 and y 130 to 1010. With the current 1200 x 880 window use `V_BOTH { s: 1, x0: 300, y0: 135 }`, `V_FIRST { s: 1.16, x0: 378, y0: 130 }` and `V_SECOND { s: 1.16, x0: 378, y0: 245 }`. These keep each whole card in frame. If you change the window's aspect, recompute them to the same bounds.
- **Overlap.** At 390 px the held-call schematic (y 73 to 195) covers the top of the image (y 156 to 292). Give the image and the schematic **separate layout slots** in `.queue-stage` at every size, so their boxes never intersect at any scroll position, including while the frame scales.
- **Legibility.** The schematic measured 0.17 opacity at step 4's midpoint at both sizes. It must be at full opacity by `kit.at(3, 'settle')`.

**Never draw Approve or Deny on the screenshot.** The two pictured entries are alerts for already-blocked calls.

| Step | Lead and zoom target | Scale | Support | Decoration | Scan and stamp | Static |
|---|---|---|---|---|---|---|
| 1 Two alerts | Wide: both cards | image pose | caption | perforation | none | image |
| 2 The poisoned read | q-0001 card via `.queue-focus-1` | image pose 1.16, kit 1 | verbatim strip lands at `land` | none | scan the card; **stamp `BLOCK`, form `block`, anchor `br`.** Text from `quote('queue', '9 read_document').trim().split(/\s+/)[2]` | caption |
| 3 The outside email | q-0002 card via `.queue-focus-2` | image pose 1.16, kit 1 | verbatim strip | none | scan the card; **stamp `BLOCK`**, text from `quote('queue', '13 send_email').trim().split(/\s+/)[2]` | caption |
| 4 Approve or Deny | The schematic held item (`.queue-sch-item`) | 1.4 | image pulls back and dims | hatch on the `hold` badge | no stamp: this run held none | image |

The schematic's controls stay non-interactive `<span>` elements. Replace its `‖ hold` glyph with `verdictBadge('hold', ...)`, and read the word from `F[pipeline/Outcome hold]`.

Final and reduced-motion frame: readable screenshot, caption and schematic.

## Scene `audit` (black ground, 4 steps)

**The chain break must hit hard.** The 20 rows are white thermal strips on black, joined by small steel links. The ninth row is `line 8`, the only row with text. Keep the caption `Schematic of the 20-entry log`. No invented hashes, timestamps or fields.

Replace the `✕` in the mismatch element with `verdictMark('alert')`.

**Measured defects to fix.** The `line 8` text overruns its outlined row by 81.5 px at 1440 and 1.8 px at 390, where the border cuts the final `D`. At about 1021 px the row reaches x 987, past the plate edge at 958. **The row must contain its text at every viewport**, with `scrollWidth <= clientWidth`. Lay it out in two lines: `line 8` with the tool name on the first, and the verdict and reason code on the second. Raise `W_EDITED` as needed, keep the verdict token in a fixed register so the `BLOCK` to `allow` crossfade cannot reflow, keep `INJECTION_DETECTED` whole, and constrain the chain with `min-width: 0`. At compact size stack or narrow the side panel so the chain stays inside the plate.

| Step | Lead and zoom target | Scale | Support | Decoration | Scan and stamp | Static |
|---|---|---|---|---|---|---|
| 1 Every entry is chained | Wide: the chain | 1 | chain draws down with a fast-then-slow pace, not an even stagger | none | none | side panel |
| 2 Clean log verifies | Wide: the chain | 1 | tracer passes down; links stay lit behind it | none | **stamp `F[audit/Clean result]`, form `allow`, anchor `tr`** at `land` | rows |
| 3 Someone edits one line | The edited row (`.audit-row--edited`) | 2.6 | `BLOCK` crossfades to `allow` starting at `lock` | none | scan across the row before the crossfade | others |
| 4 Verification fails | The edited row (`.audit-row--edited`), with `pad: 28` so the broken link above it stays in frame | 2.4 | link halves split exactly at `kit.at(3,'land')`; verbatim fail line fully visible by `settle` | none | **scan, then `HASH_MISMATCH` from `F[audit/Failure reason]`, form `alert`, anchor `br`, slams at `land`** | rows after line 8 stay neutral, not failed |

Final and reduced-motion frame: edited row, broken link, `HASH_MISMATCH` and the verbatim line.

## Check and acceptance

Run this in the Bash tool:

```bash
cd /c/Users/zarek/Downloads/tidalbyte26/site && npm run typecheck
```

It is whole-project and other agents run it concurrently, so it may exit non-zero because of their files. You are responsible only for your own. To list only your errors:

```bash
cd /c/Users/zarek/Downloads/tidalbyte26/site && npm run typecheck 2>&1 | grep -E '^src/scenes/(reasoner|queue|audit)\.' ; echo "own-error scan finished"
```

Pass means `tsc` ran and the scan prints only `own-error scan finished`. If an error names `src/shell/`, `src/main.ts` or `src/content.ts`, or `tsc` cannot start, report it to the overseer and do not fix it.

Then run this self-audit from the site folder. It must print only `audit finished`:

```bash
cd /c/Users/zarek/Downloads/tidalbyte26/site && grep -nE 'ScrollTrigger|lenis|setTimeout|setInterval|requestAnimationFrame|addEventListener|fetch\(|https?://|[✓✕‖◆]' src/scenes/reasoner.ts src/scenes/queue.ts src/scenes/audit.ts ; grep -nE '^\s*(transition|animation)(-[a-z]+)?:|@keyframes|backdrop-filter|--(film-|bone|silver|tracer|allow\)|block\)|hold\)|line\)|radius-plate)|#[0-9a-fA-F]{3,8}\b' src/scenes/reasoner.css src/scenes/queue.css src/scenes/audit.css ; grep -LE 'createInspection' src/scenes/reasoner.ts src/scenes/queue.ts src/scenes/audit.ts ; echo "audit finished"
```

Report: files changed, the check's last 10 lines, deviations and open questions.
