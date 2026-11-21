> Superseded by LEASH_OVERSEER_HANDOFF.md (written after reading Leash's build overview). Kept for the data-layer detail.

# Orchestrator handoff: Clinic Assistant data layer and Leash connection

Paste everything inside the fenced block into the main orchestrator's Claude Code session. Fill the three `<placeholders>` first if you know them; if not, the prompt tells Claude to find them in `leash/` and ask.

Run with: Claude Code, Opus 5.5, `medium` effort. Plan mode first, because this touches two codebases.

```text
Connect Clinic Assistant's local data layer to Leash so both use one set of tamper-evident stores, and bring the Clinic Assistant database up as a documented, testable component. Clinic Assistant is a local medical AI web app built today (Nov 21, 2026) for the Tidal Byte 2026 hackathon. Read this whole brief before planning.

<team_project>
The team project is "Leash": a runtime security gateway for clinical AI agents (Nemotron track). Every tool call an agent makes against patient records is checked, minimized, scored, logged, and then allowed, blocked or escalated to a human. Leash's code is in the team's leash/ folder, which the team's build agents are editing. You are the orchestrator, so coordinate any leash/ change with those agents rather than editing files they are mid-way through.

Clinic Assistant is Leash's human-facing front end and also stands alone as a demo. Nobody talks to the model directly. Every request is signed in, masked, checked, answered by a model on the same machine, checked again, scored green/amber/red, and written to a tamper-evident log. The AI never contacts anyone: it only drafts, a clinician approves, a person sends.

All patient data is synthetic (40 generated patients, every record has "synthetic": true). Keep it that way; the app is not validated for real patient data.

Deadlines today, Central time: 5:30 PM integrated and `make check` passing on the Leash side, 7:00 PM feature freeze, 8:00 PM everything committed, 9:30 PM submission closes.

Unknowns to fill from leash/ (ask me if you can't find them):
- Leash language and entry point: <Leash language / main module>
- How Leash records a tool-call decision today (its event fields): <Leash decision schema>
- Where Leash runs relative to Clinic Assistant (same process, same machine, same repo): <Leash runtime layout>
</team_project>

<build_stage>
Verified by reading the code at 1:40 PM CT.

Done (version 2, packaged as clinic-assistant/dist/ (not in git) clinic-assistant-v2.zip):
- Gatekeeper web service on 127.0.0.1:8642 with sign-in, 30-minute sessions, 20 requests/minute per user, same-origin checks on every POST, HttpOnly SameSite=Strict session cookie, strict security headers.
- Identifier masking, input and output guardrails, note injection scan (fixed patterns plus vector similarity), local-only Ollama calls with no cloud fallback.
- Green/amber/red tiers, Review queue, Messages outbox with clinician approval, access-anomaly limit (12 different patients in 10 minutes).
- Hash-chained audit log and append-only hash-chained SQLite vector store, both verified on the Audit screen.
- 40 synthetic patients from 13 action-needed scenarios; patient syn-003 carries a poisoned referral letter (the demo attack).
- UI: Patients (3-pane list, record, chat), Ask the assistant, Review queue, Messages, Audit log. Screenshots in docs/*.png.
- 20 passing tests in tests/test_smoke.py using a stand-in model (MOCK_LLM=1).

Planned, not started (task in clinic-assistant/handoff/HANDOFF_PROMPT.md): assistant actions (draft_referral, draft_patient_message, propose_follow_up, prepare_handover, propose_lab_check) with an "actions" section in policy.json; a realistic clinic day with today's appointments; a `manage_users.py seed-demo` command; docs/STAFF_GUIDE.md and docs/DEMO_SCRIPT.md; dist/clinic-assistant-v3.zip. None of these files or policy sections exist yet.

Not built, needed before any real data (from README.md): HTTPS and SSO with MFA, disk encryption, write-once copies of the audit log, an outbound firewall rule, accuracy testing, a signed risk assessment.

Copies: the source of truth is clinic-assistant/. The Mac copy at <an older local copy> holds only the first version.
</build_stage>

<how_clinic_assistant_works>
Stack: Python 3.8+ standard library only, vanilla JS in static/ with no external scripts, Ollama for the model (MedAIBase/MedGemma1.5:4b, or llama3.2:3b on the Intel Mac). No pip installs.

All rules live in config/policy.json, each section with a _comment: server (host, port, session_minutes, max_requests_per_minute), model (ollama_url, chat_model, safety_model, temperature, timeout_seconds), scope (system_prompt and the regex lists blocked_input_patterns, out_of_scope_patterns, urgent_patterns, overconfident_output_patterns, dangerous_output_patterns, document_injection_patterns), tiers, roles, access, vectors, communication, logging.

Files:
- app/server.py: class App holds every store and the pipeline; make_handler(app) holds the routes; JsonStore is the locked JSON-list store.
- app/privacy.py: mask() replaces names, dates, MRNs, phones, emails and addresses with tags like [NAME] and [DATE]; uses Presidio if installed.
- app/guardrails.py: Guardrails scores input and output and scans patient notes for hidden instructions (patterns plus vectors).
- app/llm.py: local-only Ollama client; refuses any non-local URL.
- app/audit.py: AuditLog, hash-chained JSON lines.
- app/vectorstore.py: Embedder, VectorStore, INJECTION_EXAMPLES, index_all().
- app/ehr.py: generate() builds the 40 patients (FHIR-like, resourceType "Patient"); EHR loads them; EHR.model_context() builds the minimum-necessary copy for the model.
- app/users.py and manage_users.py: accounts created by an admin on the command line; salted PBKDF2 hashes; no self sign-up.

Life of one request, App.ask_model(sess, user_text, kind, patient): mask the text, score the input (red stops here and goes to the review queue), build a minimum-necessary patient context with dates as "N days ago" and withhold any note that matches an injection pattern or scores cosine >= 0.33 against the injection examples, call the local model, score the output, pick the tier, queue amber/red/sampled items, and write audit events.

Tiers (policy "tiers"): green = no flags, 10% (green_sample_rate 0.1) copied to an auditor; amber = held, the asker reads the reasons before seeing the answer (possible emergency, hidden characters, pastes over 1500 chars, overconfident wording, and every patient-portal draft); red = blocked, goes to a clinical lead or admin, never the asker.

Roles (policy "roles"): clinician = view_patients, chat, draft_message, approve_message; nurse = view_patients, chat, draft_message; clinical_lead = those four plus review_red; auditor = view_audit, qa_review; admin = view_audit, review_red.

HTTP API (JSON, session cookie "sid", POSTs must be same-origin):
GET /api/me, /api/reviews, /api/patients?q=, /api/patients/<id>, /api/patients/<id>/similar, /api/outbox, /api/audit (entries, audit verify result and vector store status).
POST /api/login, /api/logout, /api/chat, /api/chat/clear, /api/reviews/decide, /api/outbox/draft (recipient_group, instructions), /api/outbox/decide (id, decision approve|reject, optional final_text).
</how_clinic_assistant_works>

<database>
There is no hosted database, by design: patient text must not leave the machine. The Supabase account has no projects; do not create one. Everything lives in the app's data/ folder, which App(data_dir=...) creates and fills on first start. data/ is committed as an empty folder; never commit its contents.

1. data/vectors.sqlite, the vector database (SQLite; chosen over Pinecone or Snowflake so nothing goes to the cloud).
   Schema, from app/vectorstore.py SCHEMA:
     CREATE TABLE vectors (
       seq INTEGER PRIMARY KEY AUTOINCREMENT, collection TEXT NOT NULL, doc_id TEXT NOT NULL,
       text TEXT NOT NULL, meta TEXT NOT NULL, embedder TEXT NOT NULL, embedding BLOB NOT NULL,
       created TEXT NOT NULL, prev_hash TEXT NOT NULL, hash TEXT NOT NULL UNIQUE);
     CREATE INDEX by_collection ON vectors(collection, doc_id);
     Triggers no_update and no_delete abort every UPDATE and DELETE.
   - meta is sorted-key JSON; embedding is float32 bytes (array("f")); created is UTC ISO "YYYY-MM-DDTHH:MM:SSZ".
   - hash = SHA-256 over prev_hash, collection, doc_id, text, meta, embedder, created (each followed by a zero byte), then the embedding bytes. The first row's prev_hash is 64 zeros. VectorStore.verify() walks the chain and returns {"ok": true, "rows": n} or {"ok": false, "broken_at_row": n}.
   - A change is a new row; the newest row per doc_id wins at read time. Reads filter by the current embedder, so switching embedders re-indexes beside the old rows.
   - Masked text only: call privacy.mask() before VectorStore.add().
   - After a fresh start: injection_examples (12 synthetic attack phrasings) and patient_profiles (40, one per patient: conditions, meds, attention flags, last 6 labs, notes except referral letters, masked; meta holds age and sex). 52 rows.
   - Embedder: built-in hashing-1024 (word and word-pair hashing, offline). Optional nomic-embed-text through Ollama, set in policy vectors.ollama_embed_model, which also needs its own threshold under vectors.injection_similarity.
   - API: has(), add(), search(collection, query, k, exclude) returning doc_id, score, text, meta; vector_of(); verify(); status(). index_all() is idempotent.

2. data/audit.jsonl, the audit log. One JSON object per line: ts (UTC ISO), event, user, details (object), prev, hash. hash = SHA-256 of prev plus the canonical JSON of the other fields (sort_keys, separators "," and ":"). AuditLog.verify() returns {"ok": true, "entries": n} or {"ok": false, "broken_at_line": n}. Stores masked text only (logging.store_raw_text is false).
   Events written today: server_started, login, login_failed, logout, rate_limited, patient_viewed, access_anomaly, similar_cases, patient_context_used, request_blocked, model_answer, model_error, review_queued, review_<status>, draft_created, draft_refused, draft_approved, draft_rejected, audit_viewed.

3. data/patients.json: the 40 synthetic patients, generated by app/ehr.py if missing.

4. data/users.json: an object keyed by username: role, salt (hex), hash (PBKDF2-SHA256 hex), active.

5. data/reviews.json (JsonStore list): id, kind, tier, reasons, requester, created, masked_input, answer, status (open, then decided), reviewer, decided.

6. data/outbox.json (JsonStore list): id, recipient_group (care-team, patient-portal, pharmacy, referral), draft, tier, reasons, status (awaiting_approval, approved, rejected), drafted_by, created, decided_by, final_text.

Concurrency, from my reading of the code (verify it): AuditLog and JsonStore lock with threading locks, which protect one process only. If Leash and the Clinic Assistant server both write audit.jsonl or the JSON stores from separate processes, the hash chain can fork or a write can be lost. SQLite handles multi-process writes, but VectorStore reads the last hash and inserts in two steps under a thread lock only.
</database>

<task>
1. Find the three unknowns in <team_project> by reading leash/. Write down what you found before planning.
2. Bring the database up on its own and prove it healthy:
   cd clinic-assistant/
   MOCK_LLM=1 python3 -m unittest -v   (expect 20 tests OK)
   MOCK_LLM=1 python3 -c "from pathlib import Path; from app.server import App; a=App(data_dir=Path('/tmp/freshdata')); print(a.vectors.status()); print(a.audit.verify())"
   (expect embedder hashing-1024, injection_examples 12, patient_profiles 40, ok True, rows 52; audit ok True)
3. Decide how Leash connects, and pick one writer per store so the chains can't fork. My recommendation: the Clinic Assistant process stays the only writer, and Leash reaches it through new local-only endpoints under /api/leash/ on 127.0.0.1:8642, authenticated with a service token read from an environment variable (never committed). Suggested endpoints: POST /api/leash/audit (write one Leash decision event, masked), POST /api/leash/scan (run the note injection scan and vector similarity on masked text, return score and matches), GET /api/leash/verify (audit and vector chain status). If Leash runs in the same Python process, importing app.audit.AuditLog and app.vectorstore.VectorStore against the same data_dir is the alternative. Choose based on step 1 and say why.
4. Implement the Clinic Assistant side in clinic-assistant/: the connection code, a "leash" section in config/policy.json with a _comment (enabled flag, token env var name, allowed event types), mapping from Leash's decision fields to audit details, masking before anything is stored, and tests for: a Leash event lands in audit.jsonl and verify() stays ok; a request without the token is refused; unmasked identifiers are masked before storage; a scan of syn-003's referral text scores as an injection.
5. Implement the Leash side so its gateway writes each allow/block/escalate decision through the connection, coordinating with the agents working in leash/.
6. Write docs/DATABASE.md in medical-local-ai: every store, its schema, how verification works, who writes it, how Leash connects, and how to reset safely (use a fresh data_dir).
</task>

<rules>
- Keep everything local: host 127.0.0.1, local Ollama only, no cloud model or hosted database, no external scripts in static/.
- Keep the stores append-only and hash-chained. For a schema change, add columns or a new table and keep verify() covering every stored field.
- Mask before anything reaches the model, the log or the vector store.
- Put new rules in config/policy.json with a _comment, not as constants in code.
- Test on a fresh data_dir. Don't delete files in data/, because it may hold audit history.
- Ask me before pushing code or deleting anything.
- Stop adding features at 7:00 PM Central.
</rules>

Done when: step 2's checks pass, `MOCK_LLM=1 python3 -m unittest -v` is OK including the new tests, the Leash side's `make check` passes, one Leash decision shows on the Clinic Assistant Audit screen with the chain verifying, and you have listed what changed in each codebase and how to see it running.
```
