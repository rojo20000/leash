```text
Take over development of Clinic Assistant, a restricted local medical AI web app built for the Tidal Byte 2026 hackathon (Nov 21, 2026). First get the app running and confirm its data stores are healthy, then do the task at the end of this prompt.

<what_we_are_building>
The team project is "Leash": a runtime security gateway for clinical AI agents (Nemotron track). Every tool call an agent makes against patient records is checked, minimized, scored, logged, and then allowed, blocked or escalated to a human. Leash itself is built by other agents in a separate `leash/` folder. Do not edit `leash/`, because the team's build agents are working in it.

Clinic Assistant is Leash's human-facing front end and stands on its own as a demo. Nobody talks to the model directly. Every request is signed in, masked, checked, answered by a model on the same machine, checked again, scored green/amber/red, and written to a tamper-evident log. The AI never contacts anyone: it only drafts messages, a clinician approves, and a person sends.

Patient data is synthetic only. Keep it that way, because the app is not validated for real patient data.

Deadlines today (Central time): 5:30 PM integrated and `make check` passing (Leash side), 7:00 PM feature freeze, 8:00 PM everything committed, 9:30 PM submission closes.
</what_we_are_building>

<where_the_code_is>
- Source of truth: clinic-assistant/
- Packaged copy: clinic-assistant/dist/ (not in git) clinic-assistant-v2.zip
- The user's Mac copy at <an older local copy> is out of date (first version only). Treat clinic-assistant/ as current.
- Stack: Python 3.8+ standard library only, vanilla JS front end in static/, Ollama for the local model. No pip installs are required.

Files:
- config/policy.json: every rule (scope patterns, roles, tiers, access limits, vector settings, communication rules, logging). Change rules here, not in code.
- app/server.py: the gatekeeper web service (127.0.0.1:8642), sessions, rate limits, review queue, tiers.
- app/privacy.py: identifier masking ([NAME], [DATE], MRN, phone, email, address).
- app/guardrails.py: input and output checks, document-injection scan.
- app/llm.py: local-only Ollama calls; any non-local model URL is refused.
- app/audit.py: hash-chained audit log.
- app/vectorstore.py: append-only SQLite vector store.
- app/ehr.py: synthetic patient generator (40 patients, 13 action-needed scenarios; patient syn-003 has a poisoned referral letter with hidden instructions, which is the demo's attack).
- app/users.py, manage_users.py: accounts (admin-created on the command line, PBKDF2 hashes).
- tests/test_smoke.py: 20 tests using a stand-in model (MOCK_LLM=1).
</where_the_code_is>

<the_database>
There is no hosted database. The Supabase account has no projects, and patient text must not leave the machine. All data lives in the app's data/ folder, which App() creates and fills on first start. data/ is in the repo as an empty folder; never commit its contents.

1. data/vectors.sqlite: the vector database (SQLite, chosen over Pinecone or Snowflake so nothing goes to the cloud).
   - One table, `vectors`: seq (autoincrement PK), collection, doc_id, text, meta (JSON), embedder, embedding (float32 BLOB), created, prev_hash, hash (unique). Index on (collection, doc_id).
   - Append-only: triggers `no_update` and `no_delete` abort every UPDATE and DELETE. A change is a new row, and the newest row for a doc_id wins at read time.
   - Tamper-evident: hash = SHA-256 of prev_hash plus all row fields plus the vector bytes. VectorStore.verify() walks the chain and reports the first broken row. The Audit tab shows this.
   - Holds masked text only. Call privacy.mask() before VectorStore.add(), because the store must never hold raw identifiers.
   - Collections after a fresh start: `injection_examples` (12 synthetic attack phrasings) and `patient_profiles` (40, one per patient: conditions, meds, attention flags, last 6 labs, notes except referral letters, all masked; meta holds age and sex). 52 rows total.
   - Embedder: built-in `hashing-1024` (word and word-pair hashing, offline). Optional: set `vectors.ollama_embed_model` to `nomic-embed-text` in policy.json after `ollama pull nomic-embed-text`, and add a calibrated threshold for `ollama:nomic-embed-text` under `vectors.injection_similarity`. Rows are filtered by embedder, so switching embedders re-indexes alongside the old rows instead of mixing vectors.
   - Uses: "Similar cases" on each patient record (top 3), and catching reworded prompt injections in notes (cosine >= 0.33 to any injection example withholds the note). It is not applied to short chat questions, because it gave too many false positives there.
   - Indexing is idempotent: index_all() skips doc_ids already stored for the current embedder.

2. data/audit.jsonl: one JSON object per line, each carrying the SHA-256 of the previous line plus its own canonical JSON. AuditLog.verify() detects any edited, deleted or reordered line. Stores masked text only (logging.store_raw_text is false).

3. data/patients.json: the 40 synthetic patients, generated from app/ehr.py if missing.

4. data/users.json, data/reviews.json, data/outbox.json: plain JSON lists behind a lock (JsonStore in app/server.py). reviews holds amber/red/sampled items for the Review queue; outbox holds message drafts and their approval state.

Tiers (policy `tiers`): green = no flags, 10% copied to an auditor; amber = held, the asker confirms the reasons first (every patient-portal draft is amber); red = blocked, goes to a clinical lead or admin, never the asker.
Roles: clinician, nurse, clinical_lead, auditor, admin, each with the fixed permission list in policy `roles`.
</the_database>

<setup_and_checks>
cd clinic-assistant/
MOCK_LLM=1 python3 -m unittest -v          # expect: Ran 20 tests ... OK
MOCK_LLM=1 python3 -c "from pathlib import Path; from app.server import App; a=App(data_dir=Path('/tmp/freshdata')); print(a.vectors.status()); print(a.audit.verify())"
# expect: embedder hashing-1024, collections injection_examples 12 and patient_profiles 40, ok True, rows 52; audit ok True

To click through the app: python3 manage_users.py add dr_lee clinician (password 12+ chars), then MOCK_LLM=1 python3 run.py and open http://127.0.0.1:8642. With a real model: ollama pull MedAIBase/MedGemma1.5:4b (or llama3.2:3b on the user's Intel Mac, set as model.chat_model), then python3 run.py.

Use a fresh data_dir for experiments instead of deleting files in data/, because data/ may hold the user's audit history.
</setup_and_checks>

<rules>
- Keep the app local-only: host 127.0.0.1, Ollama URL local, no cloud model fallback, no external scripts in static/.
- Keep the stores append-only and hash-chained. If you need a schema change, add columns or a new table and keep verify() covering every stored field.
- Mask before anything reaches the model, the log or the vector store.
- Put new rules in config/policy.json with a _comment, not as constants in code.
- Ask the user before pushing code, changing anything in `leash/`, or deleting files in data/.
</rules>

<task>
Make the app feel like working with an assistant agent, then make the demo realistic. Do part 1 first, because it is the feature the demo shows. Stop adding features at 7:00 PM Central (feature freeze).

Part 1. Assistant actions (the main feature)
Staff should be able to type what they need in plain words in the existing chat ("Ask the assistant", and the chat on a patient record) and have the assistant set it up for them. The assistant proposes actions. It never carries them out.
- Add an action layer that turns a request into one or more proposed actions of these types: draft_referral, draft_patient_message, propose_follow_up (when and why), prepare_handover (summary of the asker's open items and flagged patients), propose_lab_check (which test and why). Each action is a structured record: type, patient id (or none), masked content, reason, requested_by, status.
- Every proposed action goes through the same path as today's drafts: masked, checked by guardrails, scored green/amber/red, written to the audit log, and placed in the outbox or review queue for a person to approve. Reuse JsonStore, the tier logic in App.ask_model and the /api/outbox/draft and /api/outbox/decide flow in app/server.py instead of building a parallel path.
- Allowed action types, which roles may request and approve each one, and which are always amber go in config/policy.json under a new "actions" section with a _comment. A nurse can request but not approve, matching the existing roles.
- In the UI, show proposed actions as cards under the assistant's reply with Approve and Reject buttons for people allowed to approve, and a "Waiting for approval" label for others. Approved items show "Approved: a person sends this", because the app never sends anything.
- With MOCK_LLM=1, the stand-in model must return believable proposals for a few fixed phrasings, so the demo and the tests run without Ollama.
- Add tests: a request produces the right action type; a nurse cannot approve; the poisoned referral (syn-003) still ends red and produces no action; every action appears in the audit log and audit verify() stays ok.

Part 2. A realistic clinic day (synthetic only)
- Give the demo a believable setting: one fictional primary care clinic, today's appointment list (about 15 of the 40 patients with times and visit reasons, generated in app/ehr.py and stored in data/patients.json), and a "Today" view or filter on the Patients screen.
- Add a demo seeding command (for example `python3 manage_users.py seed-demo`) that creates one account per role with fictional names (clinician, nurse, clinical lead, auditor, admin) and prints their passwords once. Do not hard-code passwords in the repo.
- Keep every name, number and record fictional and marked "synthetic": true.

Part 3. Docs for the people using it
- Write docs/STAFF_GUIDE.md: one page for clinic staff in plain language. What the assistant can and cannot do, example things to ask ("Draft a referral to cardiology for this patient", "Set up a two-week follow-up for her potassium", "Prepare my handover"), what green/amber/red mean for them, and who approves what.
- Write docs/DEMO_SCRIPT.md: a 3-minute scripted walkthrough. A nurse asks for a follow-up and it waits for approval; a clinician approves a referral draft; the clinician opens syn-003, the poisoned referral is withheld and goes red; the clinical lead reviews it; the auditor shows the audit chain and vector store verifying. Include the exact accounts and what to type at each step.
- Update README.md with the new feature and commands.
</task>

Done when: the setup checks above pass, `MOCK_LLM=1 python3 -m unittest -v` reports OK including the new tests, you have clicked through docs/DEMO_SCRIPT.md once with MOCK_LLM=1 python3 run.py on a fresh data folder, and you have listed what changed and how to see it in the running app. Copy the finished folder into clinic-assistant/ and rebuild dist/clinic-assistant-v3.zip.
```

Run with: Claude Code, Opus 5.5, `medium` effort.
