# Nemotron in Leash

What Nemotron is doing. Nemotron 3.5 Lightning (`nvidia/nemotron-3.5-lightning-30b-a3b`) plays three roles in Leash, all through one client module and all with schema-validated structured output. It runs the clinical scheduling agent, choosing tool calls through native function calling. It runs a policy reasoner that reads every blocked or held call, the role policy and the detector signals, and returns a risk level, a two-to-three sentence explanation for a clinician or compliance reviewer, the policy rule ids it relies on, and a recommended action. And, as a judge conditioned on policies we wrote, it acts as a second prompt-injection detector for documents the agent reads and as a HIPAA minimum-necessary check on outbound tool-call payloads, both running beside our local TF-IDF classifier and deterministic policy. A separate NVIDIA classifier, NemoGuard JailbreakDetect, is a third injection detector for direct jailbreak prompts; it is not Lightning.

Why it matters. An agent that can read records and send email is only safe if something outside the agent decides what it may do. Leash gives hard rules the final say and uses Nemotron where judgment helps a person decide: AI judgment where it helps humans decide, hard rules where safety requires them. Nemotron output can only add caution, never remove it. A detector flag can turn an allow into a hold for a human, nothing Nemotron returns can turn a block or a hold into an allow, and the reasoner runs after the decision is final and is advisory. A test (`tests/test_gateway_nemotron.py::test_advisory_invariant`) checks that the decision, the approval queue and the audit record are identical whatever the reasoner returns. The audience is the hospital security and compliance reviewer, who gets a plain-language reason beside every Approve and Deny button instead of a rule code.

How we maximize it. We use Lightning's native tool calling for the agent, and schema-constrained JSON for the reasoner and both judges, with local validation, one retry on invalid output and a template fallback. The reasoner may only cite stable policy rule ids, and an answer that cites a rule the call did not trigger is discarded as ungrounded. Thinking is switched off for latency, and the gateway's detector, content-check and reasoner requests have identifiers replaced by typed placeholders before they leave the machine. We improved it with a measured loop: 40 labelled cases (24 dev, 16 holdout) and five live rounds (1 to 3 the planned loop, 4 the post-review fix, 5 the NemoGuard addition). On the holdout set the second detector's precision rose from 0.60 to 1.00, the reasoner's schema-valid, grounded rate from 0.69 to 1.00 and its agreement with the labelled action from 0.875 to 1.00, and the content check's false alarms fell from 5 of 8 clean cases to 3 of 8. Injection recall on the holdout set is thin evidence: the judge's holdout recall was 0.67 in round 4 and 0.33 in round 5 with unchanged prompts, and with only 3 injected holdout documents that is one document's difference between two live runs; the final-state combined holdout recall (round 5) is 0.33, and 1.00 on dev. NemoGuard JailbreakDetect, added in round 5, flagged none of the 17 evaluation documents, including all 8 injected ones (scores between -0.82 and -0.99), so it changed no metric: it is built for direct jailbreak prompts aimed at a chatbot, not for instructions hidden inside clinical documents. Where a swap measured better we made it and recorded the evidence. Every Nemotron call is recorded, so the demo replays with no network and no key.

## Where Nemotron sits in the pipeline

Every tool call goes through: role policy (Rust), then for document reads three injection detectors (the TF-IDF classifier, the Lightning judge and NemoGuard JailbreakDetect), then identifier minimization, then the content-safety check on the payload (Lightning as judge), then the anomaly score, then the decision. Only then does the reasoner run, and only for blocked or held calls. The audit append follows.

| Role | Model | Used for | Can it change the decision? |
|---|---|---|---|
| Agent | Lightning | picks tool calls for the scheduling task | no, every call it makes goes through the gateway |
| Second injection detector (judge) | Lightning, judge mode with our injection policy | documents the agent reads | can only escalate to a human (`INJECTION_SUSPECTED`); the TF-IDF block stands whatever it says |
| Third injection detector | NVIDIA NemoGuard JailbreakDetect (`nvidia/nemoguard-jailbreak-detect`), a classifier on its own allowed URL | documents the agent reads | can only escalate to a human (`INJECTION_SUSPECTED`); never blocks on its own; `LEASH_NEMOGUARD=off` removes it |
| Content-safety check | Lightning, judge mode with our HIPAA minimum-necessary policy | outbound payloads (email, appointment updates) | can only escalate to a human (`CONTENT_SAFETY_FLAGGED`) |
| Policy reasoner | Lightning, structured output | explains and recommends for blocked and held calls | no, it runs after the decision is final |

The agent's own conversation is sent as is, because it is synthetic data and the agent needs patient emails to write reminders. Everything the gateway sends for detection and explanation is redacted first.

## How we maximize Nemotron

- **Tool calling.** The agent uses Lightning's function calling with the five clinic tools. If Lightning fails, the session continues on the local Ollama model (`qwen3.5:9b`), and each step records which one served it.
- **Schema-validated JSON.** The reasoner and both judges request structured output, and the reply is validated locally against the full schema. On invalid output the client retries once, with the validation error in the message, then falls back.
- **Grounding.** The reasoner picks from a fixed list of rule ids (the policy tables plus the gateway stages). A reply that cites a rule the call did not trigger is thrown out and replaced by a deterministic template. In round 1 the reasoner fell back to the template on 11 of 33 calls; by round 4 it did so on none.
- **Policy-conditioned judges.** The detector and the content check are not generic classifiers. They read policy text we wrote (`leash/prompts/injection_policy.txt`, `leash/prompts/content_safety_policy.txt`) and were revised against failed dev cases only.
- **Thinking off.** Gateway calls use `enable_thinking: false` and temperature 0 for latency and repeatability.
- **Redaction before the request.** The Rust identifier pre-scan replaces SSN, MRN, phone, email and date-of-birth spans with typed placeholders, so a judge sees that an SSN is present, never its value. The reasoner is also never sent unminimized tool output or raw document text.
- **The measured revise loop.** See the next section.

## The measured loop

Cases are in `ml/eval/nemotron_cases.jsonl` (benign calls, over-broad reads, the exfiltration attempt, injected and clean documents). Prompt and policy changes were made from failed dev cases only; the holdout was measured, not tuned on. Per-round numbers are in `metrics/results.json` under `nemotron.eval.rounds` and in full under `ml/eval/rounds/`.

<!-- NEMOTRON_TABLE -->

**Dev (24 cases)**

| Round | TF-IDF precision / recall | Lightning judge (jailbreak) precision / recall | NemoGuard precision / recall | Combined precision / recall | Content safety tn / fp / tp / fn | Reasoner action agreement | Reasoner valid-JSON rate |
|---|---|---|---|---|---|---|---|
| Round 1 | 1.0 / 1.0 | 0.667 / 0.8 | - | 0.714 / 1.0 | 4 / 7 / 1 / 0 | 0.923 | 0.65 |
| Round 2 | 1.0 / 1.0 | 0.0 / 0.0 | - | 1.0 / 1.0 | 11 / 0 / 0 / 1 | 0.923 | 1.0 |
| Round 3 | 1.0 / 1.0 | 1.0 / 1.0 | - | 1.0 / 1.0 | 11 / 0 / 0 / 1 | 0.923 | 1.0 |
| Round 4 | 1.0 / 1.0 | 1.0 / 0.8 | - | 1.0 / 1.0 | 8 / 3 / 1 / 0 | 1.0 | 1.0 |
| Round 5 | 1.0 / 1.0 | 1.0 / 1.0 | 0.0 / 0.0 | 1.0 / 1.0 | 9 / 2 / 1 / 0 | 0.923 | 1.0 |

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

Rounds 1 to 3 are the planned loop, round 4 is the post-review fix, round 5 adds NemoGuard by team decision. For rounds 1 to 4 the combined column is TF-IDF or the Lightning judge; for round 5 it is all three detectors. A dash means NemoGuard was not part of the round.

What changed between rounds, and how to read the table:

- **Round 1 is the unrevised baseline.** The second detector and the content check were both served by the swapped-in safety model with built-in categories. It flagged most clean referrals and record reads, which is why the scripted protected run held 9 calls (8 allow, 3 block, 9 held, from `DECISIONS.md`) where the final configuration gives 17 allow, 3 block, 0 held.
- **Round 2** rewrote the prompts and the policy texts and made the content check count only our own categories. Reasoner schema-valid rate went to 1.00, and false alarms disappeared. The safety model never flagged any document under our injection policy (0 of 5 injected on dev, 0 of 3 on holdout).
- **Round 3** served the second detector with Lightning as a judge. Dev precision and recall reached 1.00 and 1.00 for that detector; holdout 1.00 and 0.67.
- **Round 4 is outside the team's planned three rounds.** Review found that after round 2 the content check had stopped flagging anything: its accuracy rose only because false alarms were removed, and it missed both labelled over-disclosure cases (one dev, one holdout). We added one more measurement with Lightning as the content judge. It catches the over-disclosure case in both splits, at the price of false alarms on 3 clean cases in each split. That is why the content check is reported as counts (tn, fp, tp, fn), not accuracy alone. If the team prefers the strict three-round cap, drop round 4 and the content-check rows with it.
- **Round 5 adds NemoGuard JailbreakDetect by team decision.** All 83 steps were served live by NVIDIA. NemoGuard flagged none of the 17 evaluation documents, including all 8 injected ones (scores between -0.82 and -0.99, all negative), so its precision and recall are reported as 0.0 (precision is undefined with no flags) and it changed no metric. It is built for direct jailbreak prompts aimed at a chatbot, not for instructions hidden inside clinical documents, and we do not claim it detects our attack. We keep it on because it covers that different attack class, costs about 364 ms p50 per document read, can only add caution, and has a one-variable off switch (`LEASH_NEMOGUARD=off`).
- **Run-to-run variation.** The Lightning judge's holdout recall was 0.667 in round 4 and 0.333 in round 5 with unchanged prompts. There are only 3 injected holdout documents, so that is one document's difference between two live runs. The final-state (round 5) combined holdout recall is 0.333 (dev 1.0), the same as the judge alone and as TF-IDF alone.
- **Combined injection detection.** From round 1 to round 5, holdout precision went from 0.60 to 1.00 and combined recall from 1.00 to 0.333, with 0.667 in rounds 3 and 4: two of the three injected holdout documents are missed by every detector in the final state. We took the precision gain knowingly; the TF-IDF classifier and the policy rules still sit in front of it.

## Model swaps and why

The team asked for Nemotron 3.5 Content Safety and NemoGuard JailbreakDetect. Each swap was made on evidence and is recorded in `DECISIONS.md`.

| Role | Asked for | Measured outcome | Used instead |
|---|---|---|---|
| Content check | `nvidia/nemotron-3.5-content-safety` | HTTP 404 "function not found" for our key; its page shows a fixed taxonomy with no custom policy | first `nvidia/llama-3.1-nemotron-safety-guard-8b-v3`, then (round 4) Lightning as a judge |
| Second detector | NemoGuard JailbreakDetect | served from `ai.api.nvidia.com`, which the data rule did not allow at the time, and not in the model list | first the safety guard with our injection policy, then (round 3) Lightning as a judge |
| Third detector (added 14:05) | NemoGuard JailbreakDetect | the team then allowed that one URL and chose to wire it in beside the judge; it is used, in round 5 | used as an extra escalate-only detector, not a swap |
| Safety guard under a custom policy | `nvidia/llama-3.1-nemotron-safety-guard-8b-v3` | ignored our policy: 0 of 5 dev and 0 of 3 holdout injected documents flagged; with only our categories counted it flagged nothing, including the over-disclosure cases | Lightning as a judge |
| Topic control | `nvidia/llama-3.1-nemoguard-8b-topic-control` | HTTP 500 on our test call | not used |

Nemotron 3.5 Content Safety is still not used: NVIDIA's own page showed it as temporarily unavailable ("high levels of interest") and the API returned HTTP 404 for our key at 11:28 and again at 13:58. The path is implemented behind `LEASH_NEMOTRON_SAFETY_MODEL` but has never had a live response. All three Nemotron roles run on `nvidia/nemotron-3.5-lightning-30b-a3b`, with NemoGuard as a separate classifier beside the judge. Each role's model is one environment variable (`LEASH_NEMOTRON_LIGHTNING_MODEL`, `LEASH_NEMOTRON_SAFETY_MODEL`, `LEASH_NEMOTRON_JAILBREAK_MODEL`), and the safety guard stays in the safety role's fallback chain. If the team gets Content Safety access, setting the variable is enough; no code change is needed.

## Latency

- **Lightning, live:** p50 718.5 ms, p95 1399.0 ms over 66 calls in the last eval round (`nemotron.latency_ms` in `metrics/results.json`). In the live demo run the reasoner took 691 to 827 ms per call.
- **NemoGuard, live:** p50 363.8 ms, p95 662.3 ms over 17 document reads in round 5. That is the cost per document read of keeping it on.
- **Gateway overhead:** p50 7.39 ms and p95 17.14 ms added per call, over 245 calls in 13 sessions. This was measured with the Nemotron stages on their local fallbacks, so a live Lightning call adds roughly 0.7 s at p50 on top, on the calls that use one.
- The reasoner runs only on blocked or held calls, after the decision, so allowed calls pay no reasoner latency.

## Fallbacks and `served_by`

Every Nemotron step has a fallback, and every decision records which path served it (`nemotron`, `replay`, `fallback:local`, `fallback:template`, `fallback:ollama`), shown in the dashboard.

| Step | If Nemotron is unavailable |
|---|---|
| Agent | local Ollama model |
| Reasoner | deterministic template built from the policy reason |
| Second detector (judge) | TF-IDF result alone decides |
| NemoGuard | skipped (`LEASH_NEMOGUARD=off`, or unavailable); its own circuit breaker, separate from the chat calls, so an outage cannot affect the agent, reasoner or judges |
| Content check | local rule: hold an email that carries an SSN or MRN |

The client has timeouts, retries with backoff, and a circuit breaker. This matters in practice: the key returns HTTP 429 when several calls arrive in a burst, and the gateway then falls back to the local detectors instead of failing.

## Recording and replay

In live mode the client records every successful request and response under `demo/recordings/nemotron/` (never the key or any header). `make demo` and `make check` run in replay mode: they answer only from those recordings and never open a socket. The recordings cover both the Rust core and the Python fallback, so the demo of record runs on either. `make record` refreshes them and needs `NVIDIA_API_KEY`.

## Limits

- 40 cases, and only 2 labelled over-disclosure positives (one dev, one holdout). The content check's numbers are small-sample.
- The content-safety judge still false-alarms on 3 clean cases in each split, and held 3 ordinary calls in the live demo run. A false alarm costs reviewer time, not safety.
- Two of the three injected holdout documents are missed by every detector in round 5 (combined holdout recall 0.333). The judge scored 0.667 in round 4 and 0.333 in round 5 with unchanged prompts; with 3 injected holdout documents that is one document between two live runs, not a trend.
- The live agent followed the hidden instruction in 1 of 3 unprotected runs, so the scripted replay is the demo of record.
- The key returns HTTP 429 under burst traffic.
- The gateway latency figures were measured without live Nemotron stages.

## Production story

Leash only needs open-weight models behind an OpenAI-compatible interface. The same Nemotron models can run on-premises from their Hugging Face weights, so patient data never has to leave the hospital. The hosted API is used here because the demo data is synthetic and it keeps setup to one key.
