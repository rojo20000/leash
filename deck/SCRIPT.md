# Leash talk track

Generated from `src/script.ts` by `npm run script-md`. Edit the lines there, not here.
Press the clicker once per row. The step number is also the URL hash: `#7` opens step 7's end state.

## Full version: 4:01 (24 steps)

| Step | Scene | Say | Starts | Length |
|---|---|---|---|---|
| 0 | 0 Cold open | (Let the counter run.) We're Leash. | 0:00 | 8s |
| 1 | 1 Problem | Hospitals want AI agents working inside their records systems. But one hidden sentence in a referral can make an agent leak a patient's record. | 0:08 | 13s |
| 2 | 1 Problem | We ran our own scheduling agent with no protection. In one of three live runs, it obeyed the hidden instruction. | 0:21 | 10s |
| 3 | 2 Stakes | Here's a synthetic patient, pt-0042. | 0:31 | 6s |
| 4 | 2 Stakes | The agent read a poisoned referral, then emailed the full record, 3,965 characters, to an outside address. Every one of these fields left the building. | 0:37 | 11s |
| 5 | 3 Leash | So we built Leash, backed by NVIDIA Nemotron: a runtime security gateway for clinical AI agents. | 0:48 | 10s |
| 6 | 4 Architecture | Here's every piece. A Nemotron agent does real work: it reads referrals and books follow-ups. Every tool call crosses the Leash gateway: Rust policy, three injection detectors, minimization, anomaly scoring, a hash-chained audit, and a Nemotron reasoner. Then the mock EHR, or a reviewer's dashboard. | 0:58 | 16s |
| 7 | 4 Architecture | For clinic staff, Clinic Assistant has its own gatekeeper: masking, guardrails, a local model, Sal's vector database and an audit log. | 1:14 | 10s |
| 8 | 5 Guardrail | Let's follow one call: policy first, then the ML and Nemotron checks. | 1:24 | 6s |
| 9 | 5 Guardrail | Updating an appointment for pt-0042 passes every check. In our scripted run, 17 legitimate calls went straight through. | 1:30 | 10s |
| 10 | 5 Guardrail | Now the agent tries to email the record outside the clinic. Policy blocks it: email domain not allowed. Nothing is sent. | 1:40 | 12s |
| 11 | 5 Guardrail | Nemotron 3.5 Lightning explains the block in plain language for the human reviewer, citing the exact rule. It is advisory: its output can only add caution, never unblock a call, and a test proves it. | 1:52 | 14s |
| 12 | 5 Guardrail | Why Nemotron? Open weights, so a hospital can run it on-premises. Fast calls: 718 milliseconds at p50. And we measured it: over five eval rounds, its agreement with the reviewer's decision rose from 0.875 to 1.00. | 2:06 | 13s |
| 13 | 6 Patient data | Leash also controls what a model sees. | 2:19 | 5s |
| 14 | 6 Patient data | Name, record number, birth date, phone and email become tags. The clinical facts stay: INR 4.3 on warfarin. | 2:24 | 9s |
| 15 | 6 Patient data | Every request goes into a hash-chained log. Edit one line and verification fails at that line. | 2:33 | 8s |
| 16 | 7 Clinic Assistant + vector DB | This is Clinic Assistant, running on this machine with a local model. | 2:41 | 6s |
| 17 | 7 Clinic Assistant + vector DB | Nobody talks to the model directly. Every question is masked, checked, answered locally, checked again and logged. | 2:47 | 6s |
| 18 | 7 Clinic Assistant + vector DB | We ask about medication interactions for a synthetic COPD patient. (Watch it follow the answer.) While the local model works, the request has already been checked. The answer arrives as a draft for a clinician, and all seven safety checks passed. | 2:53 | 22s |
| 19 | 7 Clinic Assistant + vector DB | Behind it, Sal's local vector database on SQLite: append-only, hash-chained, masked text only. It finds similar cases and catches reworded prompt injections. | 3:15 | 14s |
| 20 | 8 Close | This sits where medicine, security, machine learning and policy meet. It's for clinicians and the compliance reviewers who approve AI in hospitals. Unlike general agent guardrails, Leash governs clinical actions on patient records. | 3:29 | 12s |
| 21 | 8 Close | Built: the gateway and Clinic Assistant. Tested: 152 automated tests and five scripted demo assertions pass. Next: a pilot with a clinical reviewer. | 3:41 | 12s |
| 22 | 8 Close | We're Rowan, Sal, Zarek and Nico. | 3:53 | 4s |
| 23 | 8 Close | Leash, backed by NVIDIA Nemotron. Thank you. | 3:57 | 4s |

## CUT_TO_3MIN version: 2:58 (22 steps; open the deck with `?cut=1`)

Scene 2 is folded into Scene 1 and Scene 6 runs 45 s. Step numbers differ from the full version.

| Step | Scene | Say | Starts | Length |
|---|---|---|---|---|
| 0 | 0 Cold open | (Let the counter run.) We're Leash. | 0:00 | 6s |
| 1 | 1 Problem | Hospitals want AI agents working inside their records systems. But one hidden sentence in a referral can make an agent leak a patient's record. | 0:06 | 10s |
| 2 | 2 Stakes | In one of three live runs, our unprotected agent obeyed a hidden instruction and emailed this synthetic record, 3,965 characters, to an outside address. | 0:16 | 12s |
| 3 | 3 Leash | So we built Leash, backed by NVIDIA Nemotron: a runtime security gateway for clinical AI agents. | 0:28 | 8s |
| 4 | 4 Architecture | Here's every piece: a Nemotron agent doing real work, the Leash gateway's six stages, the mock EHR and a review dashboard. | 0:36 | 10s |
| 5 | 4 Architecture | And Clinic Assistant, the staff front end, with Sal's vector database. | 0:46 | 6s |
| 6 | 5 Guardrail | Let's follow one call: policy first, then the ML and Nemotron checks. | 0:52 | 5s |
| 7 | 5 Guardrail | Updating an appointment for pt-0042 passes every check. In our scripted run, 17 legitimate calls went straight through. | 0:57 | 8s |
| 8 | 5 Guardrail | Now the agent tries to email the record outside the clinic. Policy blocks it: email domain not allowed. Nothing is sent. | 1:05 | 9s |
| 9 | 5 Guardrail | Nemotron 3.5 Lightning explains the block in plain language for the human reviewer, citing the exact rule. It is advisory: its output can only add caution, never unblock a call, and a test proves it. | 1:14 | 10s |
| 10 | 5 Guardrail | Why Nemotron? Open weights for on-premises use, 718 millisecond calls, and reviewer agreement that rose from 0.875 to 1.00 over five eval rounds. | 1:24 | 9s |
| 11 | 6 Patient data | Leash also controls what a model sees. | 1:33 | 4s |
| 12 | 6 Patient data | Name, record number, birth date, phone and email become tags. The clinical facts stay: INR 4.3 on warfarin. | 1:37 | 7s |
| 13 | 6 Patient data | Every request goes into a hash-chained log. Edit one line and verification fails at that line. | 1:44 | 6s |
| 14 | 7 Clinic Assistant + vector DB | This is Clinic Assistant, running on this machine with a local model. | 1:50 | 6s |
| 15 | 7 Clinic Assistant + vector DB | Nobody talks to the model directly. Every question is masked, checked, answered locally, checked again and logged. | 1:56 | 7s |
| 16 | 7 Clinic Assistant + vector DB | We ask about medication interactions for a synthetic COPD patient. (Watch it follow the answer.) While the local model works, the request has already been checked. The answer arrives as a draft for a clinician, and all seven safety checks passed. | 2:03 | 20s |
| 17 | 7 Clinic Assistant + vector DB | Behind it, Sal's local vector database on SQLite: append-only, hash-chained, masked text only. It finds similar cases and catches reworded prompt injections. | 2:23 | 12s |
| 18 | 8 Close | Medicine, security, ML and policy, built for clinicians and the compliance reviewers who approve AI in hospitals. | 2:35 | 8s |
| 19 | 8 Close | Built, tested with 152 automated tests, and next: a clinical pilot. | 2:43 | 9s |
| 20 | 8 Close | We're Rowan, Sal, Zarek and Nico. | 2:52 | 3s |
| 21 | 8 Close | Leash, backed by NVIDIA Nemotron. Thank you. | 2:55 | 3s |
