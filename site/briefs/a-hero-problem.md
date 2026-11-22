# Brief A: hero and problem restyle

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

- `site/src/scenes/hero.ts`
- `site/src/scenes/hero.css`
- `site/src/scenes/problem.ts`
- `site/src/scenes/problem.css`

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

## Scene `hero` (white ground, 4 steps)

**World.** One die-cut label fills the stage. `LEASH` from `F[hero/Product]`, set in uppercase with CSS `text-transform`, prints enormous in black on the left (`clamp(5rem, min(17vw, 34svh), 16rem)`, weight 800, so it also fits 1024x576). A vertical `.blank-barcode` runs up the right edge. One static red scan line rests across the label. Keep the existing gate, trunk, forks and three ends, restyled as print inside the right 42% of the label, so they stay clear of the shell's copy at lower left. Add a small hint in the plate: `Scroll, or press Space`, with a drawn key outline. Replace the Unicode end glyphs with `verdictBadge`.

The first frame is already composed and nothing animates on load.

| Step | Lead and zoom target | Scale | Support | Decoration | Scan and stamp | Static |
|---|---|---|---|---|---|---|
| 1 A runtime security gateway | Wide shot: the whole label, `target: null` | 1 | trunk stopped above the gate | resting red line | none | wordmark, barcode, hint |
| 2 Checked before it runs | The gate (`.hero-gate`, a new wrapper around both bars and ticks) | 1.9 | trunk enters; the three ticks light with uneven gaps, the last landing at `lock` | registration marks fade | scan sweeps the gate at `scanStart`; no stamp | wordmark |
| 3 Allowed, blocked or held | The three ends as one group (`.hero-ends`) | 1.7 | forks draw during the dive and reach the ends at `arrive` | none | the block end's fill lands at `land`, with allow and hold already resting; no kit stamp | gate |
| 4 Hard rules | Wide shot, pulled back | 1 | gate darkens to full black | hint stays | none | ends remain marked |

The zoom moment is step 2. Final and reduced-motion frame: wordmark, barcode, gate and all three labeled ends. Mark the gate with `mark: true` and the ends group with `mark: false`.

## Scene `problem` (black ground, 4 steps)

**This scene hits hard.** A white die-cut referral label sits on black. Its lines are blank bars in `--ink` on a white stock layer. The hidden line is one bar. The envelope is a large white shape. **The leak uses the `alert` form and says `leaked`. It never says block, because nothing was blocked here.**

Replace the existing `✕ leaked` glyph text with `verdictBadge('alert', 'leaked')`.

| Step | Lead and zoom target | Scale | Support | Decoration | Scan and stamp | Static |
|---|---|---|---|---|---|---|
| 1 A referral arrives | Wide: the whole label | 1 | none | perforation and registration marks | none | all bars |
| 2 One sentence is hidden | The hidden bar (`.problem-row` at index 4) | 3.2 | the bar's bright red layer fades in at `lock` | surrounding bars dim under the kit | scan crosses the bar at `scanStart`; no stamp, the scan is the reveal | other bars |
| 3 The agent follows it | The envelope (`.problem-env`) | 1.8 | bright bar travels into the envelope during the dive and lands at `arrive`; envelope reaches the edge by `settle` | none | no stamp | page; empty slot stays outlined |
| 4 The full record leaves | The leak line (`.problem-leak`) | 2.1 | envelope already at the edge | none | scan sweeps the leak line; **stamp `leaked`, form `alert`, anchor `tr`, lands at `land`** | page, envelope |

The `leaked` stamp text is the literal `leaked`. The leak line stays `Q[problem/LEAK:]`, verbatim. Do not imply the agent always follows the instruction: this is the scripted run.

Use one kit with `world` wrapping all plate content, and put the label and envelope inside it. Because the current code measures with `getBoundingClientRect` for the bar's travel, build the world first, keep that measurement at identity transforms, and call `kit.resize()` from `resize()`.

Final and reduced-motion frame: page, empty slot, envelope at the edge, leak line, with `leaked` in the kit key.

## Check and acceptance

Run this in the Bash tool:

```bash
cd /c/Users/zarek/Downloads/tidalbyte26/site && npm run typecheck
```

It is whole-project and other agents run it concurrently, so it may exit non-zero because of their files. You are responsible only for your own. To list only your errors:

```bash
cd /c/Users/zarek/Downloads/tidalbyte26/site && npm run typecheck 2>&1 | grep -E '^src/scenes/(hero|problem)\.' ; echo "own-error scan finished"
```

Pass means `tsc` ran and the scan prints only `own-error scan finished`. If an error names `src/shell/`, `src/main.ts` or `src/content.ts`, or `tsc` cannot start, report it to the overseer and do not fix it.

Then run this self-audit from the site folder. It must print only `audit finished`:

```bash
cd /c/Users/zarek/Downloads/tidalbyte26/site && grep -nE 'ScrollTrigger|lenis|setTimeout|setInterval|requestAnimationFrame|addEventListener|fetch\(|https?://|[✓✕‖◆]' src/scenes/hero.ts src/scenes/problem.ts ; grep -nE '^\s*(transition|animation)(-[a-z]+)?:|@keyframes|backdrop-filter|--(film-|bone|silver|tracer|allow\)|block\)|hold\)|line\)|radius-plate)|#[0-9a-fA-F]{3,8}\b' src/scenes/hero.css src/scenes/problem.css ; grep -LE 'createInspection' src/scenes/hero.ts src/scenes/problem.ts ; echo "audit finished"
```

Report: files changed, the check's last 10 lines, deviations and open questions.
