# Clinic Assistant v2.6 → v2.7: UI review for first-time clinic staff

⚠️ DEGRADED: single-context. No sub-agent tool was exposed, so the design review and the detector/browser evidence ran in one context. The impeccable launcher was not executable as a binary; it was run via `sh`.

- **Mode:** Operate. Every screen is a work tool.
- **Identity kept:** charting-tool look: paper surface, hairline rules, clinical green #0f6b5c, square status markers, drawn SVG icons, no cards/pills/side stripes.
- **Evidence:**
  - Playwright tour of every role (dr_lee, nurse_kim, lead_ana, auditor_ray, desk_sam, net_ops) at 1280×800, plus a dark-mode shot and a 390px phone. Shots: `shots/v27-before-*.png`.
  - Detector (`impeccable detect`): flat type hierarchy (body 12–15px, h3 13.5, h2 15.5: steps under 1.25×); advisory on repeating stripes (the calendar lunch band, which never renders with current data).

## Ranked issues

### P0: broken or misleading
1. **The "Prototype, made-up patients only" banner is broken everywhere** (regression from the v2.6 calendar). The calendar's `.strip` class collides with the banner's `.strip`.
   - On sign-in the banner floats as a small box at the top left.
   - Inside the app it is positioned absolutely and hidden under the top bar. On a phone its red "Practice mode" text pokes out under the nav.
   - The one safety notice every user must see is effectively gone.
2. **Network says "Outbound internet not confirmed" in amber**, now that the public probe is off by design. It reads as a fault when it is the intended, safe state. It should calmly say it was not tested because the app never calls out.
3. **Home gives auditor_ray the clinician guide** ("Open a patient…", answer labels for chat). The auditor can't open patients. net_ops gets no guide at all, and the sign-in screen doesn't list net_ops.

### P1: first-run guidance and hierarchy
4. **Home has no single obvious "start here" action per role.** The worklist rows are all equal-weight ghost buttons, and the guide sits in a quiet side column. A first-day user can't tell which button is the one to press.
5. **Flat type hierarchy:** page titles ("Today, Sat, Nov 21", "Needs review", "Ask a general question", "Network", "Conversations") are 15.5px, the same as body text. Screens don't announce themselves.
6. **Empty states don't teach:**
   - "Nothing needs you right now." / "Nothing here yet." (Needs review)
   - "No drafts yet." (Messages)
   - "No conversations yet."
   None says what will appear there or how it gets there.
7. **PIN reveal is unlabelled:** "MRN, Born, Phone, Address, Insurance ID: hidden", a dotted box and a disabled "Show details". The word PIN never appears on the patient record.
8. **Phone:** the tab row is cut off ("Ask a ques") with no sign it scrolls, and the active tab can be off-screen.

### P2: consistency and polish
9. Page intros are inconsistent: some screens have a one-line purpose, others none (Calendar, Schedule).
10. The Needs review "Refresh" is a full-size button while other tabs use small ones; header rhythm differs between tabs.
11. The status word for in_room reads "With clinician" in the schedule and "In room now" on the calendar board.
12. The sign-in card's account list is dense monospace and lacks a one-line description of what the app is.

## Per screen (short)

- **Sign in:** banner broken (P0-1). net_ops missing from the account list. No sentence saying what this is.
- **Home:** no primary action (P1-4). Wrong guide for auditor and none for net_ops (P0-3). Guide column is good copy, but quiet.
- **Schedule (front desk):** strong already (step gating, two-press confirms). Title is weak (P1-5). Check-in and booking copy is fine.
- **Calendar:** solid after v2.6. Banner collision fixed under P0-1.
- **Patients:** PIN wording (P1-7). Record and chat layout fine.
- **Ask a question:** clear. Title weight (P1-5).
- **Conversations / Needs review / Messages / Audit:** empty states (P1-6), titles (P1-5).
- **Network:** calm egress wording (P0-2).

## Fix order (time-boxed to about 50 minutes)
P0-1 → P0-2 → P0-3 + P1-4 (role-aware "Start here" on Home) → P1-5 → P1-7 → P1-6 → P1-8 → sign-in copy. P2-10/11 only if time remains.
