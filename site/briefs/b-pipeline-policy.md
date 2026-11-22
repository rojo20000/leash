# Brief B: pipeline and policy restyle

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

- `site/src/scenes/pipeline.ts`
- `site/src/scenes/pipeline.css`
- `site/src/scenes/policy.ts`
- `site/src/scenes/policy.css`

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

## Scene `pipeline` (white ground, 10 steps)

**This scene holds the page's signature moment: the attacker's email scanned at full zoom, with a red BLOCK label slamming onto it.**

**World.** Each stage node is a small die-cut label with a perforated edge. `Stage N` sits in a fixed machine register. `Decide` stays an unnumbered diamond in heavy black. Stages 6 and 7 stay **parallel branches** from `Decide`. Replace the port glyphs with `verdictMark`.

**Camera replaces the track pan.** Remove the `track` `xPercent`/`yPercent` pan tweens. Create the kit with `viewport: view` and `world: track`, so a scale 1 or higher cue pans the track. Keep the vertical track at narrow widths. Keep the tracer dot, restyled as a solid red dot with a white keyline. Its tween positions come from layout, so they still work inside the world.

**Measured defect to fix: stage cards are cut by the plate edge during the pan, at 1440 and 390.** Frame each camera stop so the focused stage is whole: every stage cue targets the complete node, including its marker and detail text, with `pad: 20`. Node size must let it fit the view at scale 1 at all three viewports. The camera must be at rest on that framing by `arrive`, well before the midpoint.

**New element, the attacker email label** (`.pipeline-email`), inside `.pipeline-decide__under` below the ports, in the world. It is a `.stock-label` with a `.blank-barcode` strip and exactly two text lines:
- `F[problem/Recipient]` in large machine type
- `Q[pipeline/13 send_email]`

It is at opacity 0 until step 8, must fit the view at scale 1 at all three viewports (at most 320 px wide at 390 px), and keeps the recipient on one line. The stamp text is the third whitespace token of that quote, which is `BLOCK`: `quote('pipeline', '13 send_email').trim().split(/\s+/)[2]`.

| Step | Lead and zoom target | Scale | Support | Decoration | Scan and stamp | Static |
|---|---|---|---|---|---|---|
| 1 Policy | Stage 1 node | 1.7 | tracer arrives at `arrive` | none | scan at `scanStart` | all other nodes |
| 2 Injection | Stage 2 node | 1.7 | tracer and link | prior node keeps its trace mark | scan | others |
| 3 Minimize | Stage 3 node | 1.7 | tracer and link | prior marks | none, reticle only | others |
| 4 Content | Stage 4 node | 1.7 | tracer and link | prior marks | none, reticle only | others |
| 5 Anomaly | Stage 5 node | 1.7 | tracer and link | prior marks | scan | others |
| 6 One decision | `Decide` diamond | 1.5 | three ports fade in together at `lock` | drop line | no stamp | stages |
| 7 Allow | allow port | 2.0 | `Q[pipeline/1 read_document]` log line | none | **stamp `allow`, form `allow`, anchor `tr`** | other ports |
| 8 Block | **`.pipeline-email`** | **3.0** (narrow 1.6) | email fades in during the dive; log lines 9, 12 and 13 stay below the view | block port fill lands with the stamp at `kit.at(7,'land')` | **full scan across the email, then `BLOCK`, form `block`, anchor `br`, slams at `land`** | everything else dims |
| 9 Hold | hold port | 2.0 | `Q[pipeline/totals:]` | hatching on the port | **no stamp.** The port stays untaken, because the scripted run held nothing | others |
| 10 Explained and recorded | Both branches (`.pipeline-group`), whole in frame | 1.15 | branches draw from `Decide`, Stage 6 and Stage 7 **land together** | none | none | full diagram |

Step indexes in `cues` are 0-based, so the signature cue is `step: 7`.

Keep tracer steps from feeling identical: vary each stage's scale by small hand-set amounts between 1.6 and 1.85, and let scan appear only on stages 1, 2 and 5.

**Reduced motion must keep the existing full static layout:** every node, `Decide`, ports, both branches and all log lines visible with no pan. In `.scene-pipeline.is-reduced`, show `.pipeline-email` in normal flow. Stamps go to the kit's key.

## Scene `policy` (white ground, 4 steps)

**World.** A wide white label holding two heavy horizontal bars on a fine ruled scale. Rust is solid `--ink`, Python is hatched `--ink-3`, because neither is a verdict. Values sit in fixed machine registers. Keep the bar ratio exactly as built.

| Step | Lead and zoom target | Scale | Support | Decoration | Scan and stamp | Static |
|---|---|---|---|---|---|---|
| 1 Rules in Rust | The check list (`.policy-checks`) | 1.5 | none | ruled scale | scan once across the list | empty bars |
| 2 3.06 against 12.36 | The end of the Rust bar and its value (`.policy-row--rust .policy-row__head`) | 2.4 | bars draw during the dive; **Python's bar is still running when Rust stops at `arrive`** | none | scan at `scanStart`; no stamp | scale |
| 3 Off-policy | The email reason line, second `.policy-reason` | 2.0 | resource reason beside it | bars recede to low opacity | **stamp `BLOCK`, form `block`, anchor `br`.** Take the text from `quote('pipeline', '13 send_email').trim().split(/\s+/)[2]` | bars |
| 4 Fast part, slow part | The table (`.policy-bench`) | 1.35 | caveat text | none | no stamp, reticle only | bars, reasons |

Final and reduced-motion frame: bars at measured length, both reasons, table and caveat together.

## Check and acceptance

Run this in the Bash tool:

```bash
cd /c/Users/zarek/Downloads/tidalbyte26/site && npm run typecheck
```

It is whole-project and other agents run it concurrently, so it may exit non-zero because of their files. You are responsible only for your own. To list only your errors:

```bash
cd /c/Users/zarek/Downloads/tidalbyte26/site && npm run typecheck 2>&1 | grep -E '^src/scenes/(pipeline|policy)\.' ; echo "own-error scan finished"
```

Pass means `tsc` ran and the scan prints only `own-error scan finished`. If an error names `src/shell/`, `src/main.ts` or `src/content.ts`, or `tsc` cannot start, report it to the overseer and do not fix it.

Then run this self-audit from the site folder. It must print only `audit finished`:

```bash
cd /c/Users/zarek/Downloads/tidalbyte26/site && grep -nE 'ScrollTrigger|lenis|setTimeout|setInterval|requestAnimationFrame|addEventListener|fetch\(|https?://|[✓✕‖◆]' src/scenes/pipeline.ts src/scenes/policy.ts ; grep -nE '^\s*(transition|animation)(-[a-z]+)?:|@keyframes|backdrop-filter|--(film-|bone|silver|tracer|allow\)|block\)|hold\)|line\)|radius-plate)|#[0-9a-fA-F]{3,8}\b' src/scenes/pipeline.css src/scenes/policy.css ; grep -LE 'createInspection' src/scenes/pipeline.ts src/scenes/policy.ts ; echo "audit finished"
```

Report: files changed, the check's last 10 lines, deviations and open questions.
