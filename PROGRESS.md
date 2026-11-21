# Progress

Generated from graph/state.json (updated 2026-11-21T11:48-06:00).

## Summary
passed 6, running 1, rework 1, pending 12

## Gates
| Stage | Status | At | Commit |
|---|---|---|---|
| stage0 | passed | 11:26 | f916a54 |

## Nodes
| Node | Name | Status | Iteration | Last check | Reviewer notes |
|---|---|---|---|---|---|
| N0 | preflight | passed | 1 | make preflight: 13/13 PASS (python 3.12.14, cargo 1.100.0, maturin 1.16.0, ollama 0.40.16, leash_core ok, en_core_web_lg, qwen3.5:9b tool_calls ok); 11:40 added by hand: NVIDIA_API_KEY present in .env, Lightning test call HTTP 200 in 343 ms |  |
| N1 | plan | passed | 1 | plan.yaml loads with 13 nodes; missing briefs: []; duplicate owns across stage-1 nodes: [] | CONTRACTS.md reviewed in full (C1-C9): core interface, hash chain, schemas, ports, gateway API, ML API, ownership all literal. Planner also wrote pytest.ini, policies/scheduling_assistant.toml, data/corpus/expand.py. Follow-ups for N8: .gitignore additions (runtime/, data/generated/, ml/artifacts/, metrics/*.tmp); consider .gitattributes for line endings. |
| N1b | replan_nemotron | running | 2 |  | Iteration 1 returned blocked: the addendum was not yet in graph/MISSION.md (overseer error, fixed). Adds C10, N16, N17, N18; rewrites N7 brief. |
| N2 | rust_core | rework | 2 | cargo test: 10 passed; pytest tests/test_core_*.py: 17 passed (parity not skipped); bench --quick: rust policy 3.05 us vs python 11.66 us (3.82x), audit append 234 us vs 317 us (1.35x) | Overseer re-ran the full check chain: exit 0. Loader returns python with LEASH_CORE=py and rust when unset. Audit append is disk-bound; speedup varies 0.6x-1.35x run to run. Idea not done: keep the audit file handle open in Rust. REWORK (11:45): Policy.evaluate checked only resource_types[0], so a five-type read_record passed policy (both Rust and Python). Cause: ambiguous wording in CONTRACTS.md C1.1 step 2. Routed: implementer fixes both cores and adds tests; planner fixes the wording. |
| N3 | data_ehr | passed | 1 | generate.py wrote data/generated; pytest tests/test_data_*.py tests/test_ehr_*.py: 12 passed | Overseer verified: 200 Patients, 483 Conditions, 495 MedicationRequests, 706 Encounters, 5 DocumentReferences; attacker address only in ref-0042.pdf; normal.jsonl 320 sessions, abnormal.jsonl 100 sessions across all 4 scenarios. |
| N4 | corpus | passed | 1 | banks ok: openings=48, findings=69, plans=44, benign_imperatives=83, injections=100; wrote 1200 rows injected=600 benign=600 hard_negative=300 test=300 unique_texts=1200 | Overseer re-ran expand.py and scanned injections.txt: plain ASCII natural language, no code/markup/URLs. |
| N5 | ml_models | passed | 1 | train_injection, train_anomaly, eval_minimizer exit 0; pytest tests/test_ml_*.py: 4 passed. injection P 1.00 R 0.853 (n_test 300, 0/150 hard negatives flagged); anomaly P 0.958 R 0.911, normal FPR 5.7%; minimization P 1.00 R 1.00 (240 notes, 572 spans) | Overseer re-ran the check: exit 0, ml.api.ready() True. Deviations accepted: extra single-sentence benign negatives in training; anomaly score is forced anomalous when a feature that was constant in training is non-zero (exfil_email and off_role_resources recall 1.0 come from this guard, docs must say so); DOB redacted only next to a birth label; minimize keep_fields optional. Minimization eval is templated and likely easy. |
| N6 | agent_gateway | passed | 1 | LEASH_CORE=py LEASH_ML=stub pytest tests/test_gateway_*.py tests/test_agent_*.py: 13 passed, 1 skipped (live LLM, opt-in). Same result on Rust core + real ML. | Overseer ran the protected scripted replay on Rust core + real ML: injected referral blocked (INJECTION_DETECTED, alert q-0001), attacker email blocked (EMAIL_DOMAIN_NOT_ALLOWED, alert q-0003), 0 sink lines to the attacker, audit verify ok with 20 entries. For N8/N17: (a) after the off-role read the anomaly score stays 0.967 for the rest of the 60 s window, so the two later legitimate referrals are escalated (10 allow / 2 block / 8 escalate); (b) first minimize call takes 5.7 s (lazy Presidio/spaCy load), needs warm-up and exclusion from latency; (c) importing gateway.app creates runtime/ in the repo; (d) decision seq is 1-based. |
| N7 | dashboard | pending | 0 |  | waiting for the Nemotron re-plan (brief is being rewritten) |
| N16 | nemotron_client | pending | 0 |  | added by the team's Nemotron addendum; never cut (N18: at least one round) |
| N17 | nemotron_reasoner | pending | 0 |  | added by the team's Nemotron addendum; never cut (N18: at least one round) |
| N8 | integration | pending | 0 |  |  |
| N9 | metrics | pending | 0 |  |  |
| N10 | live_demo | pending | 0 |  |  |
| N11 | dashboard_polish | pending | 0 |  |  |
| N18 | nemotron_eval | pending | 0 |  | added by the team's Nemotron addendum; never cut (N18: at least one round) |
| N12 | docs | pending | 0 |  |  |
| N13 | tables | pending | 0 |  |  |
| N14 | fresh_eyes | pending | 0 |  |  |
| N15 | final | pending | 0 |  |  |

## Final make check output
(not run yet)
