# Clarifications: assumptions and open questions

Each item states what I assumed. If an assumption is wrong, tell whoever is editing the deck. Every one can be changed in `src/` or `index.html`.

## Locations

| Question | Assumed answer |
|---|---|
| Where should the deck live? | `deck/` in the Leash repo (moved from a `leash-deck/` folder next to it). |
| Where is the Leash source? | `../leash` (README, docs, demo output, policies, `clinic-assistant/`). |
| Is there a running Clinic Assistant to iframe? | No. `CLINIC_ASSISTANT_URL` is empty in `src/config.ts`. Clinic Assistant sends `frame-ancestors 'none'`, so it cannot be framed anyway. Scene 6 plays `public/demo.webm` (with `public/demo.mp4` as the fallback source). The `d` key still forces the video. |

## Facts and numbers

| Item | Assumed answer | Source |
|---|---|---|
| Problem stat "1 in 3" | The unprotected live agent followed the hidden instruction in 1 of 3 runs. This is our own small sample, not an industry figure. **Question:** do you want an external, sourced statistic instead? | `leash/README.md`, Limitations |
| "152 tests pass" | 105 pytest + 11 cargo + 36 Clinic Assistant unittest. I took these from PROGRESS.md and did not re-run them. **Confirm before presenting.** PROGRESS N20 says 103 pytest, while N15 and N21 say 105. | `leash/PROGRESS.md` N15, N20, N21, N22 |
| Safe request | `update_appointment` for `pt-0042`, ALLOW. | `leash/demo/output/scripted_run.txt` |
| Blocked request | `send_email` to `outside-clinic.example`, blocked with `EMAIL_DOMAIN_NOT_ALLOWED`. | same |
| "17 legitimate calls went straight through" | From the totals line: 17 allow, 3 block, 0 escalate. | same |
| MRN-0000042 and 3,965 characters | Real values from the unprotected leak line. | same |
| Name, birth date, phone and email on the pt-0042 card | Invented synthetic values (Dana Whitfield, 03/14/1958, (555) 010-0142, dana.w@example.com). They do not match the generated patient. | invented |
| 52 vectors | 40 patient profiles + 12 injection examples in `data/vectors.sqlite`. | `leash/PROGRESS.md` N22 |

## Scene content

| Item | Assumed answer |
|---|---|
| Scene 4 labels | Agent → Policy → ML checks → EHR / email. These follow the real gateway, not the spec's "request → policy layer → model → output check". |
| Scene 5 redaction | Shows the real Presidio output from `clinic-assistant/app/privacy.py` on the sample note: tags such as `<PERSON>`, not blocks. Presidio labels the MRN as `<LOCATION>`. It is still removed, but a judge may notice the label. |
| Scene 5 audit line | The format illustrates `clinic-assistant/app/audit.py` and shows no real hash. The real `masked_tags` list for this note also includes `URL` and `US_DRIVER_LICENSE`, and the line shows all seven tags. |
| Scene 6 vector field | 52 dots, not the spec's roughly 300, so the count matches the real store. 3 similar cases, not 5, because the policy sets `similar_cases` to 3. The 2-D layout is illustrative and not a real projection. |
| What the vector store does | It powers Similar cases and catches reworded prompt injections. It does **not** supply citations to answers, so the deck makes no RAG or citation claim. |
| Two Similar cases at 100% match | That is the real output. **Question for Sal:** is this expected for the `hashing-1024` embedder (near-identical masked COPD profiles)? |
| Similar-case names | Hidden in the deck; only the match % and the shared condition show. Open item for Sal: the Similar cases API returns full names and bypasses the access count. |
| Presenters | **Open:** who presents which scene, and who answers questions on the guardrail and the vector DB. SCRIPT.md has no speaker column yet. |

## Clinic Assistant capture

| Item | What was done |
|---|---|
| Where | A throwaway copy in the OS temp folder on port 8643. The repo copy and its `data/` were not touched. |
| Model | `qwen3.5:9b` with `think: false`, patched in the temp copy only. It stands in for MedGemma, which is not installed. **Re-record with MedGemma** if the team wants the production model on screen. |
| Patient and question | `syn-036` (synthetic COPD patient), "Any medication interactions or allergy conflicts?". The answer came back green, as a draft, with "7 safety checks passed". |
| Account | A one-off `dr_lee` account with a random password. It exists only in the temp copy and was never printed. |
| **Finding for Sal** | When Presidio is installed (as in the Leash venv), Clinic Assistant's output check flags ordinary answer text as identifiers, so every answer is withheld (red). Two captures with the venv Python both went red. The final capture uses system Python with the standard library only, as the Clinic Assistant README intends. If the clinic installs Presidio, this will block real use. |

## Claims to confirm before judges

- The deck makes no compliance claims. Neither the on-screen text nor the speaker lines say "HIPAA", "secure", "compliant" or "guaranteed".
- The team must confirm every spoken number: 1 in 3, 3,965 characters, 17 calls, 152 tests, five demo assertions, 52 vectors, seven safety checks.
- "Runs entirely on this machine, with a local model" is true for the recording. Say "in our demo setup" if a judge asks about deployment.
- "Catches reworded prompt injections that fixed patterns miss": the README describes it, but there is no measured recall for it. Don't quote a number.

## Nemotron (NVIDIA "Best Use of Nemotron" track)

The track asks teams to explain what Nemotron does, why it matters, and how they get the most out of it (`leash/graph/MISSION.md`, 11:23 addendum; `leash/docs/SUBMISSION.md`). The deck now covers each point.

| Item | What the deck does (assumed answer) | Source |
|---|---|---|
| "Backed by NVIDIA Nemotron" | Shown under "Leash" in Scene 3 and on the closing frame. Plain text in the deck's own colours, with no NVIDIA logo or brand green. **Confirm the team is happy with this wording.** Nemotron runs the agent, the reasoner and two judges, but fixed rules make the final decision. | `leash/README.md` |
| Pipeline node "ML + Nemotron" | The third node holds TF-IDF, IsolationForest and Presidio, plus the Lightning judge and NemoGuard as escalate-only detectors | `leash/README.md` (How it works) |
| Step 9, Nemotron's explanation | The reasoner's real output for the blocked email, quoted verbatim: `risk=critical recommends=deny (advisory)`. The model id is shortened to `nemotron-3.5-lightning`; the full id is `nvidia/nemotron-3.5-lightning-30b-a3b`. | `leash/demo/output/scripted_run.txt`, call 13 |
| "Advisory only: never unblocks" | The design rule: Nemotron output can only add caution, and `test_advisory_invariant` proves it | `leash/docs/SUBMISSION.md`; `tests/test_gateway_nemotron.py` |
| Spoken: "agreement rose from 0.875 to 1.00 over five measured eval rounds" | Holdout reasoner agreement with the labelled action | `leash/docs/SUBMISSION.md`; `leash/docs/PITCH.md` (table) |
| Not on screen | The demo of record replays recorded Nemotron responses. If a judge asks whether the call was live, say "replayed from real recorded API calls". | `leash/docs/DEMO_SCRIPT.md` |
| Not on screen | The thin evidence: 40 labelled cases; combined holdout injection recall 0.333; NemoGuard flagged 0 of 8 injected documents. Have these answers ready for questions. | `leash/docs/PITCH.md` (Questions to expect) |

## Deviations from the spec

| Spec | What the deck does | Why |
|---|---|---|
| One italic or serif accent word | None used. | Geist has no italic, and a faked oblique looks poor on a projector. |
| Oxblood allowed as display text | Oxblood is used only for fills and strokes, never for text. | It measures about 3:1 on the background and would fail the 4.5:1 contrast test. |
| Stroke-dash connector draw; colour tweens | Connectors scale in, and colour changes are opacity crossfades between overlaid elements. | Rule 9: animate only transform, opacity and blur. |
| Boot counter 1.6 s | 1.5 s. | Rule 4 caps any tween at 1.5 s. |
| PHI scrambles to `████` blocks | Scrambles through block characters and lands on the real tags. | Matches what the model actually sees. |
| `#<n>` hash | 0-based (`#0` is the cold open). Step numbers differ between the full deck and `?cut=1`. | Matches `window.__deck.stepIndex`. |
| CUT_TO_3MIN | Drops the stat and record steps (Scene 2's leak step carries the stat in its spoken line) and uses shorter per-step timings, for a total of 171 s. | Merging Scene 2 and trimming Scene 6 alone would not reach 160–190 s. |
| Reduced motion | Each step rebuilds instantly at its end state, with a 0.2 s fade when the scene changes. | Meets the 250 ms limit. |
| Scene 6 live iframe | Recorded video only. | Clinic Assistant forbids framing. |

## Judging documents (TidalBYTE '26 opening slides, NVIDIA track brief)

| Item | What the deck does (assumed answer) | Confirm |
|---|---|---|
| Talk length | Neither document sets a time limit for the in-person judging (8:00–9:30 PM). The deck keeps the brief's 4:00 target (now 4:01) and the 2:58 cut. | Ask the organisers whether judges expect a 2-minute table demo (the MLH pattern); if so, use `?cut=1` and lead with Scene 7. |
| "Build an agent doing real work" | Said aloud in the Architecture scene: the Nemotron scheduling agent reads referrals and books follow-ups | `leash/docs/DEMO_SCRIPT.md` describes this job |
| "Why Nemotron" numbers | "718 ms p50" is Lightning's live latency over 66 calls; "0.875 → 1.00" is holdout reasoner agreement with the labelled action, rounds 1 → 5 (`leash/docs/PITCH.md`) | Confirm before quoting |
| "Open weights: deployable on-premises" | Stated as possible, not done: the production story in `leash/graph/MISSION.md` | Don't say it already runs on-premises; the demo used NVIDIA's hosted API and recorded replays |
| Contrast with general agent guardrails | Spoken only: "Unlike general agent guardrails, Leash governs clinical actions on patient records." NVIDIA OpenShell and NeMo Guardrails aren't named. | `leash/docs/PITCH.md` asks the team to check product wording against NVIDIA's current docs before naming them |
| Architecture scene | The gateway's six stages come from `leash/README.md`. Clinic Assistant is drawn as a separate staff path with its own gatekeeper. Its optional "integrated mode through the Leash gateway" (commit 95c1810, off by default) is not drawn. | Should the deck show Clinic Assistant routing through the gateway? |
| Clinic Assistant version | The deck now shows v2.7 (the merge landed during this session: Calendar and Conversations tabs, "Add to this chart"). The demo was re-captured from v2.7. | — |
| Demo recording | 2× JPEG screenshots stitched at about 12 fps, 3200×1800. The typing (0.5–5.0 s) is played at 3×, so the question appears in about 1.5 s; the rest plays at real speed, so the model's answer time stays honest. Model: qwen3.5:9b stand-in, think off. The question went green with "7 safety checks passed". | Re-capture with MedGemma if it gets installed |
| Port 8643 | Another tool on this machine listens on 8643, so the capture now uses 8653 (`CA_PORT` overrides) | — |
