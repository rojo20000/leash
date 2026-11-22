# Brief E: results and closing restyle

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

- `site/src/scenes/results.ts`
- `site/src/scenes/results.css`
- `site/src/scenes/closing.ts`
- `site/src/scenes/closing.css`

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

## Scene `results` (white ground, 7 steps)

**World.** A wide white label. Across the top, the 20-call strip printed like a perforated tape: 17 blue ring marks and 3 red bar marks with their call numbers, using `verdictMark`. Below it, one table layer per step, set in fixed machine registers. Keep all table values exact, and keep the caption `Separate 245-call workload`.

**Corrected facts that must survive:** latency callouts keep their `Lightning:` and `NemoGuard` prefixes. Do not change `steps()`.

| Step | Lead and zoom target | Scale | Support | Decoration | Scan and stamp | Static |
|---|---|---|---|---|---|---|
| 1 17 allowed, 3 blocked | The film strip (`.results-film`) | 1.15 | marks fill by importance: allow marks quickly, the three block marks last at `land` | legend | scan along the strip; no stamp | table |
| 2 What the gateway adds | `latency_ms` row of the table, tagged `.results-focus` | 1.7 | rest of the table | none | scan the row | strip |
| 3 Live model calls | The Lightning row | 1.5 | other row | none | none, reticle only | strip |
| 4 Injection detector | The `recall` row | 1.6 | other rows | none | none, reticle only | strip |
| 5 Anomaly and minimization | The anomaly `recall` row | 1.5 | minimization group | none | none, reticle only | strip |
| 6 A wider workload | The `escalate` cell of `T[results/gateway-rates]` | 2.2 | workload note and caption | none | **stamp `hold`, form `hold`, anchor `tr`**, text from `F[pipeline/Outcome hold]`. This is the 245-call workload, so the caption must remain visible | strip |
| 7 Five checks passed | The `PASS 2` line | 1.5 | other PASS lines rest | none | scan down the line; **stamp `PASS`, form `allow`, anchor `tr`**, text from `quote('results', 'PASS 2').trim().split(/\s+/)[0]` | strip |

**Measured defect to fix.** At 1021x565, the step 5 layer (anomaly and minimization) pushed the headline (right 609) over the plate (left 563) and ran the table to y 595, past the 565 viewport. The shell's `minmax(0, ...)` tracks fix the column overlap. In this scene, at the compact query in contract section 9: reduce the film strip's height, set tables at 12 px with line height 1.2 and 2 px cell padding, and lay the anomaly and minimization groups **side by side**. Check every layer, since `gateway-latency` has 10 rows and the injection group has 8. Each layer must fit inside the plate at 1024x576, and each must be fully visible by `kit.at(step, 'settle')`.

Mark targets only while their layer is the visible one. Layers stack in the same box, so offsets remain valid while hidden by opacity. Do not use `display: none`.

At 390 px, keep the existing stacked treatment for `model-latency`, and choose targets that fit at scale 1. Final and reduced-motion frame: the strip plus **all** tables and five PASS lines in normal flow, using `.scene-results.is-reduced` to unhide layers.

## Scene `closing` (white ground, 5 steps)

**World.** The quietest scene: one plain white label with large black text and no decoration beyond a perforation and a registration mark. **Limitations stay complete, verbatim and high contrast.** No verdict color and no stamps. Zoom here is a reading aid, not drama.

Do not change `steps()` or the `limit()` text.

| Step | Lead and zoom target | Scale | Support | Decoration | Scan and stamp | Static |
|---|---|---|---|---|---|---|
| 1 Does not prove | The first limitation's lead sentence (`.closing-lead`) | 1.25 | rest of paragraph | none | no scan, no stamp | layer |
| 2 Live system varies | The first paragraph in the layer | 1.2 | second paragraph | none | none | layer |
| 3 Two scores | The first paragraph in the layer | 1.2 | second paragraph | none | none | layer |
| 4 A prototype | The `Limitation: Prototype` paragraph | 1.25 | latency paragraph | none | none | layer |
| 5 Run it yourself | The commands block (`.closing-commands`) | 1.2 | team and prerequisites | blank barcode at the label's foot | one scan down the commands, the page's last | team |

Set `dim: false` on steps 1 to 4, so surrounding limitation text is never dropped back. Only step 5 uses the dim layer. Use a reticle on all five.

The clone URL stays plain text inside `<pre>`, never a link. At 390 px, the longest limitation must fit inside the plate at 13 px or larger, and if a paragraph cannot zoom without leaving the plate, the kit's fit keeps it at scale 1. Final and reduced-motion frame: all limitations, team and commands in normal flow, using `.scene-closing.is-reduced`.

## Check and acceptance

Run this in the Bash tool:

```bash
cd /c/Users/zarek/Downloads/tidalbyte26/site && npm run typecheck
```

It is whole-project and other agents run it concurrently, so it may exit non-zero because of their files. You are responsible only for your own. To list only your errors:

```bash
cd /c/Users/zarek/Downloads/tidalbyte26/site && npm run typecheck 2>&1 | grep -E '^src/scenes/(results|closing)\.' ; echo "own-error scan finished"
```

Pass means `tsc` ran and the scan prints only `own-error scan finished`. If an error names `src/shell/`, `src/main.ts` or `src/content.ts`, or `tsc` cannot start, report it to the overseer and do not fix it.

Then run this self-audit from the site folder. It must print only `audit finished`:

```bash
cd /c/Users/zarek/Downloads/tidalbyte26/site && grep -nE 'ScrollTrigger|lenis|setTimeout|setInterval|requestAnimationFrame|addEventListener|fetch\(|https?://|[✓✕‖◆]' src/scenes/results.ts src/scenes/closing.ts ; grep -nE '^\s*(transition|animation)(-[a-z]+)?:|@keyframes|backdrop-filter|--(film-|bone|silver|tracer|allow\)|block\)|hold\)|line\)|radius-plate)|#[0-9a-fA-F]{3,8}\b' src/scenes/results.css src/scenes/closing.css ; grep -LE 'createInspection' src/scenes/results.ts src/scenes/closing.ts ; echo "audit finished"
```

Report: files changed, the check's last 10 lines, deviations and open questions.
