# Leash: submission text

Team: Rowan Haber, Salvador Jimenez, Zarek Haleem, Nico Pitre. Event: Tidal Byte 2026. Theme: apply AI and machine learning to real world problems in ways that create meaningful cross disciplinary impact. Also entered: NVIDIA "Best Use of Nemotron".

One line: Leash is a runtime security gateway that sits between a clinical AI agent and hospital data, and stops a hidden instruction in a referral from leaking a patient record.

## Inspiration

Hospitals want AI agents that read records and send email, but one poisoned document can turn a helpful scheduling agent into a data leak. We wanted to show a layer that makes that safe enough to try, and to measure how well it works instead of only claiming it.

## What it does

Every tool call from the agent goes through Leash. Leash checks it against a role policy, runs injection checks on documents, strips patient data down to what the task needs, scores the session for odd behavior, and writes the decision to a hash-chained audit log. Then it allows the call, blocks it, or holds it for a human. For every block or hold, Nemotron writes a plain-language explanation and a recommendation next to the Approve and Deny buttons. In the demo, an unprotected agent emails a patient's full record to an outside address, and the protected run blocks the poisoned read and the outside email. Editing one audit line makes verification fail.

## Nemotron track: what Nemotron does, why it matters, how we maximize it

What Nemotron is doing. Nemotron 3.5 Lightning (`nvidia/nemotron-3.5-lightning-30b-a3b`) plays three roles in Leash, all through one client module and all with schema-validated structured output. It runs the clinical scheduling agent, choosing tool calls through native function calling. It runs a policy reasoner that reads every blocked or held call, the role policy and the detector signals, and returns a risk level, a two-to-three sentence explanation for a clinician or compliance reviewer, the policy rule ids it relies on, and a recommended action. And, as a judge conditioned on policies we wrote, it acts as a second prompt-injection detector for documents the agent reads and as a HIPAA minimum-necessary check on outbound tool-call payloads, both running beside our local TF-IDF classifier and deterministic policy.

Why it matters. An agent that can read records and send email is only safe if something outside the agent decides what it may do. Leash gives hard rules the final say and uses Nemotron where judgment helps a person decide: AI judgment where it helps humans decide, hard rules where safety requires them. Nemotron output can only add caution, never remove it. A detector flag can turn an allow into a hold for a human, nothing Nemotron returns can turn a block or a hold into an allow, and the reasoner runs after the decision is final and is advisory. A test (`tests/test_gateway_nemotron.py::test_advisory_invariant`) checks that the decision, the approval queue and the audit record are identical whatever the reasoner returns. The audience is the hospital security and compliance reviewer, who gets a plain-language reason beside every Approve and Deny button instead of a rule code.

How we maximize it. We use Lightning's native tool calling for the agent, and schema-constrained JSON for the reasoner and both judges, with local validation, one retry on invalid output and a template fallback. The reasoner may only cite stable policy rule ids, and an answer that cites a rule the call did not trigger is discarded as ungrounded. Thinking is switched off for latency, and the gateway's detector, content-check and reasoner requests have identifiers replaced by typed placeholders before they leave the machine. We improved it with a measured loop: 40 labelled cases (24 dev, 16 holdout) and four live rounds. On the holdout set the second detector's precision rose from 0.60 to 1.00, the reasoner's schema-valid, grounded rate from 0.69 to 1.00 and its agreement with the labelled action from 0.875 to 1.00, and the content check's false alarms fell from 5 of 8 clean cases to 3 of 8. Where a swap measured better we made it and recorded the evidence. Every Nemotron call is recorded, so the demo replays with no network and no key.

Full detail, including every model swap with its evidence, is in `docs/NEMOTRON.md`.

## How we built it

- Rust core (PyO3) for the policy engine, the hash-chained audit log and the identifier pre-scan, with a Python fallback that has the same interface.
- Python gateway (FastAPI) running a fixed pipeline, a Streamlit dashboard, a mock EHR serving synthetic FHIR R4 data, and a scheduling agent.
- Three small ML models: a TF-IDF injection classifier, an IsolationForest anomaly model, and Presidio-based minimization, all seeded and evaluated on held-out data.
- Nemotron 3.5 Lightning for the agent, the policy reasoner, and two policy-conditioned judges, through one client with schema validation, fallbacks, and recording and replay.
- Built with Claude Code as a graph of small tasks, each with a brief, a check command and acceptance criteria.

## Challenges

- The Nemotron models we asked for were not usable as planned: Content Safety returned HTTP 404 for our key, and JailbreakDetect is served from a host our data rule does not allow. The first replacement ignored our custom policy. We measured each option and settled on Lightning as a judge.
- Our first eval round made the demo worse: the swapped-in safety model flagged most clean calls, holding 9 of 20. Fixing that took three revisions of the prompts and policies.
- Review caught that our content check had stopped flagging anything after round 2: its accuracy rose only because false alarms disappeared. We added a fourth measurement and report counts instead of accuracy.
- Live agents are not deterministic and the API rate-limits bursts, so the demo of record replays recorded Nemotron responses.

## Accomplishments

- A working attack and defense demo that needs no key and no network, with five assertions that run in `make check`.
- Measured numbers with sample sizes for every model, and before and after numbers for the Nemotron loop.
- A design rule that is tested, not just stated: Nemotron output can only add caution.
- A HIPAA mapping that says where Leash falls short (no caller authentication).

## What we learned

- Model-served guardrails need a measured eval before they go in a pipeline; the first safety model looked fine on one example and flagged most clean calls.
- Accuracy hides failures when positives are rare. Counts do not.
- Putting the AI after the decision, as an explainer, gave us the benefit of Nemotron's judgment with none of the risk of letting it decide.

## What's next

Real caller and reviewer authentication, more roles and policies, a larger labelled set, a content check with fewer false alarms, on-premises Nemotron, an externally anchored audit chain, and a pilot against an EHR sandbox with a clinical reviewer.

## Limits we state up front

40 Nemotron eval cases with 2 over-disclosure positives; the content check false-alarms on some clean calls; one injected holdout document is missed by both detectors; the live agent followed the hidden instruction in 1 of 3 unprotected runs, so the scripted replay is the demo of record; the NVIDIA key returns HTTP 429 under burst traffic; the minimization eval uses templated notes. See the README "Limitations" section.

## Checklist: what the team still has to do by hand

- [ ] **Check the submission form's required fields against this document.** We were never given the hackathon's submission requirements, so this document follows our own list.
- [ ] Rotate the NVIDIA API key. It was pasted into a chat. Put the new one only in the git-ignored `.env`.
- [ ] Decide where the repository is pushed and whether it is public. Nothing has been pushed. Check that `.env` and `runtime/` are not in what you push, then put the repo URL in the README's clone command.
- [ ] Record the demo video from `docs/DEMO_SCRIPT.md` (3 minutes). Run `make demo` once beforehand.
- [ ] Build slides from `docs/PITCH.md` (10 slides, two of them Nemotron slides).
- [ ] Confirm the metrics and Nemotron tables are filled in the README, `docs/PITCH.md` and `docs/NEMOTRON.md` (look for the `METRICS_TABLE` and `NEMOTRON_TABLE` markers; they should be gone or replaced).
- [ ] Fresh-clone test: follow the README setup on a clean checkout, then `make check`.
- [ ] Submit before 9:30 pm America/Chicago on 2026-11-21. The team's own cutoff for finished work is earlier.
