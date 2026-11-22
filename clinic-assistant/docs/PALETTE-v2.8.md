# Clinic Assistant v2.8 palette

## Source sites
I tried to load all six sites with Playwright (Chromium, deviceScaleFactor 1). The agent proxy refused every one of them with
`ERR_TUNNEL_CONNECTION_FAILED` (curl got `CONNECT tunnel failed, 403`). I tried once directly and once through the proxy, then stopped.
That means I have no screenshots and no computed colours. The roles below come from the well-known public look of each site
(used for colour and tone only), and every value was then checked for contrast here.

| Role | Light | Dark | Inspired by |
|---|---|---|---|
| Shell (header/nav) `--shell` | #0b2340 | #08172b | deep hospital and government navy (Mayo Clinic, CMS.gov) |
| Primary action and links `--accent` | #0b5cad | #6fb1f2 | public-health link and button blue (NIH/PMC, CMS.gov) |
| Secondary, "today" `--teal` | #00727a | #4cc5c0 | dental practice software teal (Open Dental, Pearl) |
| Page `--paper` / sheet / shade | #f3f5f8 / #fff / #eaeef3 | #0e1520 / #141d2a / #101824 | cool off-white journal pages (Nature, PMC) |
| Hairlines `--rule`, `--rule-2` | #dbe1e8, #bcc6d2 | #233041, #334459 | blue-grey article rules (Nature, PMC) |
| Ink / 2 / 3 | #15202b / #445263 / #5f6c7b | #e5ebf3 / #aab6c6 / #8b98aa | near-black blue-grey text (Nature, PMC) |
| OK | #1d6b3a | #74cf91 | standard clinical green |
| Check (amber) | #8a5200 | #f0bf62 | standard clinical amber |
| Stop (red) `--red`, now line `--now` | #b0201a, #c4261e | #ff8e84, #ff7a6e | the editorial red alert accent (Nature), used only for stop and now |
| Patient banner `--banner` | #edf2f8 | #162233 | navy tint of the shell |

## Contrast (WCAG AA, computed with scratchpad/contrast.js)
- **Light, on paper / sheet / shade:**
  - ink 15.1 / 16.5 / 14.2
  - ink-2 7.3 / 8.0 / 6.9
  - ink-3 4.9 / 5.4 / 4.6
  - accent 6.1 / 6.7 / 5.7
  - teal 5.2 / 5.7 / 4.9
  - ok 6.0 / 6.5 / 5.6
  - amber 5.9 / 6.4 / 5.5
  - red 6.3 / 6.9 / 5.9
- **Dark:** every text token is between 5.8 and 15.3. ink-3 is the lowest at 5.8.
- **Tint pairs:**
  - Light: accent on accent-tint 5.7; amber on amber-tint 5.7; red on red-tint 5.8; ok on ok-tint 5.6; teal on teal-tint 4.9.
  - Dark: every tint pair is 6.3 or higher.
- **Shell:** nav text (#c3d2e6) on the shell is 10.3; white on the shell is 15.8.

## Rationale
- A navy shell and a blue primary are what hospital and government health sites use to signal trust. They stay calm through long shifts.
- Teal is a second hue for "today". It keeps "today" apart from "selected" (blue) and from "now" (red).
- Status colours are muted and always come with a word and a square marker, so colour is never the only cue.
- Cool-grey surfaces with white sheets give a dense, ruled, tabular reading surface, without stacking cards inside cards.
