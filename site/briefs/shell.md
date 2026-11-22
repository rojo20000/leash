# Brief: shell restyle (delta)

The shell is already built and working. This is a **delta**: swap fonts and tokens, restyle `base.css`, the rail and top bar, set scene grounds, and add the inspection zoom kit. Five scene implementers start after you finish and depend on your exports.

**Your contract is `site/SITE_CONTRACT.md`, not the repo-root `CONTRACTS.md`.** Read it in full, especially sections 4 and 15, whose code blocks are normative. Do not read or edit the root `CONTRACTS.md` or `graph/`.

Repo: `C:\Users\zarek\Downloads\tidalbyte26`, branch `site/scroll-demo` (already checked out). Do not commit or push. Run commands in the **Bash tool**, because PowerShell 5.1 has no `&&`.

## Read and load first

1. `site/.impeccable/surfaces/index-html.md`, the governing direction. Never copy its text into any built file or code comment.
2. `site/PRODUCT.md`.
3. `C:\Users\zarek\.claude\skills\impeccable\reference\craft-floor.md`. Apply it. Where it suggests animating blur, clip-path, mask or shadow, this project's transform-and-opacity rule wins.
4. Load `ui-animation:choreograph` and `ui-animation:animate` with the Skill tool.

## Owned paths

Everything in `site/` outside `site/src/scenes/`, except these read-only files: `site/src/content.ts`, `site/SITE_CONTRACT.md`, `site/MOTION_NOTES.md`, `site/PRODUCT.md`, `site/.impeccable/`, `site/briefs/`.

Do not edit any file in `site/src/scenes/`. You are the only agent allowed to run `npm install` or edit `package.json`.

## Keep unchanged

The scene module interface in `types.ts`, `frame.ts`, `registry.ts`, `content-access.ts`, `keyboard.ts`, the runway and sticky stage, jump behavior, rail links and focus handling, and the reduced-motion flow. Do not add pin spacers or change scroll logic.

## Changes

1. **Fonts.** In `package.json` remove `@fontsource-variable/archivo` and `@fontsource/ibm-plex-mono`. Add these exact versions as runtime dependencies:
   - `@fontsource-variable/bricolage-grotesque` `5.3.0`
   - `@fontsource-variable/hanken-grotesk` `5.3.0`
   - `@fontsource-variable/martian-mono` `5.3.0`

   In `src/main.ts` import `@fontsource-variable/bricolage-grotesque/standard.css`, `@fontsource-variable/hanken-grotesk/wght.css` and `@fontsource-variable/martian-mono/standard.css`, replacing the old font imports. After install, confirm each CSS file declares the family named in the token block. If a family name differs, report it rather than guessing.

2. **Tokens.** Replace `src/shell/tokens.css` with the block in contract section 4. Below it, add this **temporary** alias block so scene CSS that has not been restyled yet stays legible:
   ```css
   [data-ground] {
     --film-900: var(--ground); --film-800: var(--surface); --film-700: var(--rule);
     --film-line: var(--rule-strong); --silver: var(--ink-3); --bone: var(--ink);
     --tracer: var(--ink); --allow: var(--allow-ink); --block: var(--block-ink); --hold: var(--hold-ink);
     --line: 1px solid var(--rule); --radius-plate: var(--radius-label);
   }
   ```

3. **Grounds.** Add `src/shell/grounds.ts` exporting `SCENE_GROUND: Record<SceneId, 'white' | 'black'>`, using the contract's ground map. In `buildSection` in `runtime.ts`, set `el.dataset.ground`. The placeholder uses white. Set `data-ground="white"` on `<body>` so the rail and page default resolve tokens.

4. **`base.css` restyle.**
   - `body` background `--white`. Stage background `--ground`, text `--ink`.
   - `.scene__plate`: die-cut label: `--surface`, `--radius-label`, `--shadow-rest`, 1px `--rule` border, `overflow: clip`.
   - Step copy per the typography rules in section 4. Sentence max width 65ch.
   - Callouts: verdict forms per section 4 (blue ring, red bar, hatched two bars), drawn in CSS. Code callouts sit in a thin keylined tag so they read as printed registers. Keep all text at 12 px or larger.
   - Add every shared print class in section 4. `.blank-barcode` must look irregular and encode nothing. `.micro-rule` has no text.
   - Add `.v-mark`, `.v-badge` and all `.inspect-*` styles.
   - Theme browser surfaces: `::selection` (white on `--red`), `caret-color`, a thin custom scrollbar in black on white, and a 3px `--blue` `:focus-visible` ring with a 2px white offset, which must remain visible on black scenes.
   - No CSS transitions or animations anywhere in the shell.

   - **Fix the measured overlap at its root:** every stage grid uses `minmax(0, ...)` tracks. Desktop is `minmax(0, 5fr) minmax(0, 7fr)`.
   - Add the compact projector layout from contract section 9, including the `.scene-hero` variant, so 1024x576 has no overlap, clipping or overflow.
   - `.callout--code` and `.machine` use `overflow-wrap: break-word`, never `anywhere`, so reason codes stay whole at 390 px. The current `.callout` rule sets `anywhere`; remove it.

5. **Hero layout variant, in `base.css`.** The hero's first viewport is one die-cut label filling the space from the rail's right edge to the viewport's right edge.
   - At 768 px and up: `.scene-hero .scene__stage` has `padding: var(--space-3) var(--space-3) var(--space-3) calc(var(--rail-w) + var(--space-3))`. `.scene-hero .scene__plate` spans the full grid (`grid-column: 1 / -1; grid-row: 1`). `.scene-hero .scene__copy` sits above it in `grid-column: 1; grid-row: 1; z-index: 2; align-self: end; padding: var(--space-8)`.
   - `.scene-hero .step__headline` uses `clamp(1.75rem, 1rem + 2vw, 3rem)`, so the printed wordmark stays dominant.
   - Under 768 px use the normal one-column stage.
   - Under `.is-reduced`, use the normal stacked layout with no overlap.

6. **Rail and top bar.** The rail is a fixed white die-cut strip on every ground: `--white`, `--shadow-rest`, a `.perf-y` right edge and black text. Set `data-ground="white"` on the `<nav>` so its tokens never flip. Titles only, no numbers. The current entry is black, weight 700, with a small red registration tick drawn in CSS. Others use `--ink-3`. The progress fill is a 3px `--red` line, driven by the existing `scaleY`. The narrow top bar matches: white, shadow, current title, `scaleX` red progress line.

   **Narrow scene menu (measured gap: at 390 px the top bar offers no way to jump).** Implement the menu in contract section 13 in `rail.ts`: keep the top bar and current title, and add a `Scenes` button with `aria-expanded` and `aria-controls` that opens the existing list as a panel under the bar. Opening moves focus to the current entry, choosing an entry jumps and closes, `Escape` closes and returns focus to the button, and an outside click closes. No animation. Entries are at least 40 px tall. All 12 must fit without an internal scroll container at 390x844; at short heights use two columns.

7. **Add `src/shell/emphasis.ts`** implementing contract section 15 exactly, with those exported names and types. Put its overlay CSS in `base.css`.

8. Update `placeholder.ts` only as needed for the new tokens.

## Acceptance

Run the check. It must exit 0:

```bash
cd /c/Users/zarek/Downloads/tidalbyte26/site && npm install && npm run typecheck && npm run build
```

Then run these. Each must print its `ok` line:

```bash
cd /c/Users/zarek/Downloads/tidalbyte26/site && ! grep -Eq '(src|href)="/' dist/index.html && echo "ok relative paths"
cd /c/Users/zarek/Downloads/tidalbyte26/site && ! grep -rEq 'url\((https?:)?//' dist --include=*.css && echo "ok no remote css urls"
cd /c/Users/zarek/Downloads/tidalbyte26/site && ! grep -rEq 'pin: *true|pinSpacing' src/shell && echo "ok no pin spacers"
cd /c/Users/zarek/Downloads/tidalbyte26/site && ! grep -Eq 'overflow(-[xy])?: *(hidden|auto|scroll)' src/shell/base.css && echo "ok no sticky-breaking overflow"
cd /c/Users/zarek/Downloads/tidalbyte26/site && ! grep -Eq 'archivo|ibm-plex' package.json src/main.ts && echo "ok old fonts removed"
cd /c/Users/zarek/Downloads/tidalbyte26/site && grep -q 'createInspection' src/shell/emphasis.ts && grep -q 'verdictBadge' src/shell/emphasis.ts && echo "ok kit exports"
cd /c/Users/zarek/Downloads/tidalbyte26/site && ! grep -Eq 'transition|@keyframes|backdrop-filter|requestAnimationFrame|setTimeout|addEventListener' src/shell/emphasis.ts && echo "ok kit is scrub-only"
cd /c/Users/zarek/Downloads/tidalbyte26/site && ! grep -Eq 'transition:|@keyframes|backdrop-filter' src/shell/base.css && echo "ok no css motion"
cd /c/Users/zarek/Downloads/tidalbyte26/site && ! grep -Eq 'overflow-wrap: *anywhere' src/shell/base.css && grep -q 'minmax(0, 5fr)' src/shell/base.css && grep -q 'max-height: 680px' src/shell/base.css && echo "ok compact layout and whole tokens"
cd /c/Users/zarek/Downloads/tidalbyte26/site && grep -q 'aria-expanded' src/shell/rail.ts && grep -q 'Escape' src/shell/rail.ts && echo "ok narrow scene menu"
cd /c/Users/zarek/Downloads/tidalbyte26/site && ! grep -rEiq 'bedside|own-world|thesis|seed:' src index.html && echo "ok direction text not shipped"
```

Note on the scrub-only check: the kit must wait for images and fonts without `addEventListener`. Use `document.fonts.ready.then(...)`, `img.decode().then(...)` and a `ResizeObserver`.

Report: files changed, last 10 lines of the check, deviations, open questions. If a pinned package fails to install or a contract detail cannot work, stop and report it to the overseer instead of substituting.
