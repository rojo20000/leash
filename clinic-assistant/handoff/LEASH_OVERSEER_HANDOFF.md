# Handoff for the Leash overseer: add Clinic Assistant as the human front end

Paste the fenced block into the Leash overseer's chat (the Fable 5.2 session that owns `graph/`). It is written as a scope-add request so the overseer routes it the usual way: `graph/MISSION.md`, then the planner for a contract section, plan entries and briefs, then nodes.

Before pasting, copy the Clinic Assistant folder to the machine that runs Leash, at `<path where the Clinic Assistant folder will live>`, and fill that path in below. The source is `clinic-assistant/` (or `dist/clinic-assistant-v2.zip`). The Mac copy at `<an older local copy>` is out of date.

Run with: the existing overseer session (Fable 5.2, its current effort). No settings change needed.

This replaces `ORCHESTRATOR_HANDOFF.md`, which was written before we had Leash's build overview and proposed a connection that doesn't fit Leash's design.

```text
Scope-add request: add Clinic Assistant, our clinician-facing app, to Leash as an optional human front end whose AI requests go through the Leash gateway. Stage 4 comes first. Treat this as lower priority than N12-N15, and cut it before any Stage 4 work slips.

Please route it the usual way: write the scope into graph/MISSION.md, have the planner add a contract section, plan entries and briefs, then run the nodes. Log the decision in DECISIONS.md. Read this whole message before deciding, and send me back the plan (new node ids, owned paths, checks, and where they sit against the 7:00 PM freeze) before starting any node.

<why>
Leash protects tool calls from an autonomous agent. Clinic Assistant shows the other half of the story judges will ask about: what clinicians see and do when the AI they use is behind Leash. In integrated mode, each time a clinician asks about a patient, Clinic Assistant makes a tool call to Leash's gateway instead of reading its own records, so Leash's policy, injection detection, minimization, anomaly scoring and audit apply to human-initiated AI requests too. Clinic Assistant then shows the clinician the allow, block or escalate result, and its own review queue and outbox handle what Leash doesn't (draft approval, amber holds).
</why>

<what_clinic_assistant_is>
Location: <path where the Clinic Assistant folder will live>. It was built today in a separate Claude project (Opus 5.5 sessions, one thread at a time), not by this graph, so none of it is in graph/plan.yaml yet.

Stack: Python 3.8+ standard library only (http.server, sqlite3, urllib). Vanilla JS in static/ with no external scripts. Local Ollama model (MedAIBase/MedGemma1.5:4b, or llama3.2:3b on the Intel Mac). It makes no off-machine calls at all, and app/llm.py refuses any non-local model URL. It does not call NVIDIA.

How it was built, in order: (1) a gatekeeper web service with sign-in, roles, masking, guardrails and a hash-chained audit log; (2) a Messages outbox where the AI only drafts, a clinician approves and a person sends; (3) 40 synthetic patients from 13 action-needed scenarios, with patient syn-003 carrying a poisoned referral letter as the demo attack; (4) green/amber/red tiers with a Review queue; (5) a local append-only SQLite vector store for similar cases and reworded-injection detection; (6) a UI redesign; (7) packaging as dist/clinic-assistant-v2.zip. 20 tests pass with a stand-in model.

Run and check:
  MOCK_LLM=1 python3 -m unittest -v          (20 tests, no model, no network)
  python3 manage_users.py add dr_lee clinician (password 12+ characters)
  MOCK_LLM=1 python3 run.py                    (serves http://127.0.0.1:8642)

Rules live in config/policy.json (sections: server, model, scope, tiers, roles, access, vectors, communication, logging), each with a _comment.

Request pipeline, App.ask_model in app/server.py: mask identifiers (app/privacy.py), score the input (app/guardrails.py), build a minimum-necessary patient context (app/ehr.py EHR.model_context: no name, MRN, birth date or contact, dates as "N days ago"), scan each note for hidden instructions with regex patterns plus cosine >= 0.33 against 12 injection examples in the vector store, call the local model (app/llm.py), score the output, pick a tier, queue amber/red/sampled items, write audit events.

Tiers: green = no flags, 10% sampled to an auditor; amber = held until the asker reads the reasons (every patient-portal draft is amber); red = blocked, reviewed by a clinical lead or admin, never the asker.
Roles: clinician (view_patients, chat, draft_message, approve_message), nurse (view_patients, chat, draft_message), clinical_lead (those plus review_red), auditor (view_audit, qa_review), admin (view_audit, review_red).
Access anomaly: more than 12 different patients in 10 minutes is refused and sent to a lead (App.record_access).

HTTP API on 127.0.0.1:8642, JSON, session cookie "sid", POSTs same-origin only:
  GET /api/me, /api/reviews, /api/patients?q=, /api/patients/<id>, /api/patients/<id>/similar, /api/outbox, /api/audit
  POST /api/login, /api/logout, /api/chat, /api/chat/clear, /api/reviews/decide, /api/outbox/draft, /api/outbox/decide

Data, all in its data/ folder, created on first start, never committed:
- vectors.sqlite: table vectors(seq, collection, doc_id, text, meta JSON, embedder, embedding float32 BLOB, created, prev_hash, hash UNIQUE); triggers no_update and no_delete abort edits; hash = SHA-256 over prev_hash and every field plus the vector; VectorStore.verify() walks the chain. Collections: injection_examples (12) and patient_profiles (40), masked text only, offline hashing-1024 embedder.
- audit.jsonl: one JSON line per event (ts, event, user, details, prev, hash), hash = SHA-256 of prev plus canonical JSON; AuditLog.verify(). Masked text only.
- patients.json (40 synthetic, FHIR-like, "synthetic": true), users.json (PBKDF2 hashes), reviews.json, outbox.json.
</what_clinic_assistant_is>

<how_it_connects>
Integrated mode, behind a policy flag that is off by default so standalone behavior and its 20 tests stay unchanged:

1. Clinic Assistant becomes a Leash client. When a signed-in user opens a patient record or asks about one, it sends POST /v1/tool-call to the gateway on 127.0.0.1:8000, using the request format in CONTRACTS.md, with the user's role and a request id. In that mode, patient records come from Leash's mock EHR (port 8001, 200 synthetic FHIR R4 patients) through the gateway, not from Clinic Assistant's own patients.json.
2. Leash decides: allow returns the minimized record, which Clinic Assistant then passes through its own masking and note scan before the local model sees it; block shows the clinician a red result with Leash's reasoner explanation; escalate shows "Waiting for review in Leash" and the item goes to Leash's existing approval queue on the dashboard (port 8501), not to a second queue.
3. Each side keeps its own audit chain. Leash logs the tool-call decision; Clinic Assistant logs the human side (sign-in, the question, approvals). Both entries carry the same request id so a reviewer can follow one request across both chains. Neither writes the other's files, so no chain is shared between processes.
4. If the gateway is unreachable, Clinic Assistant fails closed: it shows an error and does not fall back to its own records.

Open questions for the planner to settle in the contract:
- The exact /v1/tool-call request and response fields, and which tool name and FHIR resource types a record read uses.
- How Clinic Assistant's five roles map to Leash's per-role field filter.
- Whether the demo uses one of Leash's own injected documents for the attack beat in integrated mode, since syn-003 exists only in Clinic Assistant's standalone data.
- Whether Clinic Assistant lives in the repo (my suggestion: its own owned path, for example clinic_assistant/) or stays outside it with only a README section.
</how_it_connects>

<suggested_nodes>
Suggestions for the planner, not a plan. Ids are placeholders.
- Contract (planner): one new CONTRACTS.md section for the Clinic Assistant client: request and response, role mapping, request-id linking, fail-closed behavior.
- Client (implementer): inside Clinic Assistant's owned path only, add a "leash" section to config/policy.json with a _comment (enabled false by default, gateway URL 127.0.0.1:8000), a small urllib client, and the three result states in the UI. Check: Clinic Assistant's 20 existing tests plus new tests against an in-process stub gateway on localhost (allow, block, escalate, gateway down), all with MOCK_LLM=1 and no network.
- Docs (transcriber): a short "Human front end" section in README.md and docs/SUBMISSION.md, and one optional beat in docs/DEMO_SCRIPT.md.
Keep these out of make check until they pass twice; give them a separate target such as make clinic-check. Leave the gateway, the Rust core and the existing demo recordings unchanged, so make record is not needed.
</suggested_nodes>

<limits>
- Stage 4 (N12-N15) keeps priority. If N12-N15 are not all on track by 5:30 PM, cut these nodes and log the cut.
- Freeze at 7:00 PM, committed by 8:00 PM, submission closes 9:30 PM (Central).
- Synthetic data only. The only off-machine calls in the whole project stay those to integrate.api.nvidia.com; Clinic Assistant adds none. make check passes with no key and no network.
- Clinic Assistant keeps its own rules: host 127.0.0.1, local model only, masking before the model, log or vector store, stores append-only and hash-chained, new rules in config/policy.json with a _comment.
- Ask me before git push.
</limits>

Done when: you have sent me the routed plan; and, if approved and run, the new nodes are passed in state.json, make check still passes from a clean worktree, Clinic Assistant's tests pass in both modes, and one integrated request shows up in Leash's decision feed and in Clinic Assistant's audit log with the same request id.
```
