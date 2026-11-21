# Leash pitch outline (10 slides)

One line for the whole deck: **AI judgment where it helps humans decide, hard rules where safety requires them.**

## 1. Problem

- Hospitals want AI agents working inside their records systems.
- An agent with access to patient data can leak it, or act without approval. One hidden sentence in a referral PDF is enough.
- Show: the unprotected run, `LEAK: email to records-transfer@outside-clinic.example ... (MRN-0000042 in body: True)`.

## 2. Solution

- Leash sits between any clinical agent and hospital data. Every tool call is checked, minimized, scored, logged, and then allowed, blocked or held for a human.
- Show: the architecture diagram from the README.
- Efficiency argument: an agent in a box can safely be given more to do on its own.

## 3. Live demo

- Follow `docs/DEMO_SCRIPT.md`, `make demo`: unprotected leak, then protected run (poisoned read blocked, over-broad read blocked, outside email blocked), then the Nemotron explanation in the approval queue, then the audit tamper test.
- The demo is deterministic and needs no key or network. Say so if asked.

## 4. How the ML works

- **Injection classifier:** TF-IDF and logistic regression on a corpus of benign notes and notes with embedded instructions, tested on held-out bank lines and 150 hard negatives (benign notes with benign imperatives).
- **Anomaly model:** IsolationForest over sliding 60-second windows of agent actions. Two of its scenario recalls come from a deterministic guard, not the forest; say so.
- **Minimization:** Rust pre-scan plus Presidio, dropping fields the role does not need.
- Show: the injection, anomaly and minimization rows of the results table.

## 5. Why Nemotron

- Lightning runs the agent and a policy reasoner that explains every block and hold to the reviewer, grounded in stable rule ids. A second Lightning call, conditioned on our written policies, is a second injection detector and a HIPAA minimum-necessary check. NVIDIA NemoGuard JailbreakDetect is a third injection detector, wired in by team decision; TF-IDF can block, the other two can only escalate.
- Rule: Nemotron output can only add caution. It never unblocks a call, and the reasoner is advisory. `test_advisory_invariant` proves it.
- We measured and revised: 40 labelled cases, five live rounds, holdout reasoner agreement 0.875 to 1.00, second-detector precision 0.60 to 1.00. We swapped two models on evidence. Final-state combined injection recall is 1.00 on dev and 0.333 on holdout; the judge's holdout recall was 0.667 in round 4 and 0.333 in round 5 with unchanged prompts, which is one of 3 injected documents between two live runs. Say that the round 4 content-check fix came from review, and that the content check still false-alarms. Say that NemoGuard flagged none of the 17 evaluation documents (all 8 injected ones scored -0.82 to -0.99), so it changed no metric: it targets direct jailbreak prompts, not instructions hidden in documents. We keep it on as defence in depth (about 364 ms p50 per document read, escalate-only, `LEASH_NEMOGUARD=off` removes it).
- Production: the same open models run on-premises, so patient data never leaves the hospital.

## 6. How Leash differs from OpenShell and NeMo Guardrails

- Those govern general agent runtimes and conversations. Leash governs clinical actions on patient records.
- What is specific: HIPAA minimum-necessary redaction, a FHIR-aware policy (resource types and fields), and a tamper-evident audit trail mapped to HIPAA rules (see `docs/HIPAA_MAPPING.md`).
- Leash is complementary: it could run beside either. Confirm the wording about the two NVIDIA products against their current documentation before presenting.

## 7. Why Rust

- Lead with the policy check: it runs on every call. Rust 3.06 microseconds against Python 12.36, 4.04 times faster over 100,000 checks.
- One audited implementation on the hot path: the policy engine and the hash-chained audit log are the code a reviewer has to trust, and `cargo test` plus a Rust-versus-Python parity test cover them.
- Audit append: 2.03 times faster in the full run, but disk-bound, and it varied between about 1.3 and 2.0 times across runs. Do not lead with it.
- Be straight: the anomaly model, not the policy check, is the biggest per-call cost in the gateway. A Python fallback with the same interface keeps everything running if Rust cannot build.

## 8. Results

- Show the tables below; every number comes from `metrics/results.json`.
- Gateway: 245 calls in 13 sessions, p50 7.39 ms and p95 17.14 ms added, measured with the Nemotron stages on local fallbacks. A live Lightning call adds roughly 0.7 s at p50.
- Scripted protected run: 17 allow, 3 block, 0 held (baseline before the eval loop: 8 allow, 3 block, 9 held).

<!-- METRICS_TABLE -->

Gateway decisions and added latency. Workload: 10 scripted-recording sessions x 20 calls + 3 bulk-read sessions x 15 read_record. Latency measured with Nemotron stages on local fallback.

| Calls | Sessions | Auto-approved | Escalated | Blocked | Added latency p50 (ms) | Added latency p95 (ms) |
|---|---|---|---|---|---|---|
| 245 | 13 | 71.4% | 16.3% | 12.2% | 7.39 | 17.14 |

Detectors, held-out.

| Detector | Precision | Recall | F1 | Test size / notes |
|---|---|---|---|---|
| injection | 1.0 | 0.853 | 0.921 | n_test 300 |
| anomaly | 0.958 | 0.911 | 0.934 | false_positive_rate_normal 5.7% |
| minimization | 1.0 | 1.0 | n/a | n_notes 240, n_spans 572 |

Anomaly recall by scenario.

| Scenario | n | Recall |
|---|---|---|
| bulk_read | 1013 | 0.85 |
| exfil_email | 63 | 1.0 |
| off_role_resources | 137 | 1.0 |
| rapid_search | 876 | 0.962 |

Rust vs Python, n = 100000 iterations.

| Operation | Rust (us) | Python (us) | Speedup |
|---|---|---|---|
| Policy check | 3.063 | 12.363 | 4.04x |
| Audit append | 241.524 | 490.046 | 2.03x |

<!-- NEMOTRON_TABLE -->

**Holdout (16 cases)**

| Round | TF-IDF precision / recall | Lightning judge (jailbreak) precision / recall | NemoGuard precision / recall | Combined precision / recall | Content safety tn / fp / tp / fn | Reasoner action agreement | Reasoner valid-JSON rate |
|---|---|---|---|---|---|---|---|
| Round 1 | 1.0 / 0.333 | 0.6 / 1.0 | - | 0.6 / 1.0 | 3 / 5 / 1 / 0 | 0.875 | 0.692 |
| Round 2 | 1.0 / 0.333 | 0.0 / 0.0 | - | 1.0 / 0.333 | 8 / 0 / 0 / 1 | 0.625 | 1.0 |
| Round 3 | 1.0 / 0.333 | 1.0 / 0.667 | - | 1.0 / 0.667 | 8 / 0 / 0 / 1 | 0.75 | 1.0 |
| Round 4 | 1.0 / 0.333 | 1.0 / 0.667 | - | 1.0 / 0.667 | 5 / 3 / 1 / 0 | 1.0 | 1.0 |
| Round 5 | 1.0 / 0.333 | 1.0 / 0.333 | 0.0 / 0.0 | 1.0 / 0.333 | 5 / 3 / 1 / 0 | 1.0 | 1.0 |

**Live latency per model**

| Model | p50 ms | p95 ms | n | Source |
|---|---|---|---|---|
| nvidia/nemotron-3.5-lightning-30b-a3b | 718.5 | 1399.0 | 66 | live |
| nvidia/nemoguard-jailbreak-detect | 363.8 | 662.3 | 17 | live |

## 9. Cross-disciplinary impact

- **Medicine:** scheduling and referral work is where agents will arrive first; the reviewer is a clinician or compliance officer, so explanations are in plain language.
- **Security:** least privilege, prompt-injection defense and tamper-evident logging applied to an agent instead of a person.
- **Machine learning:** three small models plus an LLM judge, each evaluated on held-out data, combined so that a model can only add caution.
- **Policy:** HIPAA minimum-necessary and audit controls turned into a policy file and a log a regulator can read.

## 10. What's next

- Real authentication for callers and reviewers (the largest gap in the HIPAA mapping).
- More roles and policies, and a larger labelled set, especially for over-disclosure.
- Content-safety judge with fewer false alarms; run the Nemotron models on-premises.
- Anchor the audit chain outside the machine.
- A pilot against a real EHR sandbox with a clinical reviewer.

## Questions to expect

- "Why not just trust the model?" The agent followed the hidden instruction in 1 of 3 unprotected live runs.
- "What if Nemotron is down?" Every Nemotron step has a local fallback, and the decision never depended on it.
- "Does NemoGuard catch your attack?" No. It flagged 0 of 8 injected documents; it covers direct jailbreak prompts, a different attack class, and TF-IDF is what blocks ours.
- "Is the eval big enough?" No: 40 cases, 2 over-disclosure positives. It is evidence of a loop, not a benchmark.
