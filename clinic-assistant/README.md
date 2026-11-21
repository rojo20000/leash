# Clinic Assistant: a restricted local medical AI (prototype)

> **Team setup (Leash repo):** start with [`SETUP.md`](SETUP.md). Agents: read [`AGENTS.md`](AGENTS.md) first. Limits and roadmap: [`NOTES.md`](NOTES.md). `data/clinic.db` and `data/vectors.sqlite` are the shared synthetic snapshot.

A small web app that puts a **gatekeeper** between people and a local AI model.
Nobody talks to the model directly. Every request is signed in, masked, checked,
answered on this computer only, checked again, and written to a tamper-evident log.

**Prototype. Use synthetic (made-up) patient data only.** It is not a medical device
and has not been validated for clinical use.

## New in 2.12: a before-and-after demo of the reviewer

- **Demo switch**: a clinical lead or admin can switch the Nemotron reviewer off and on at runtime (Ask a question > Demo scenarios, or `GET`/`POST /api/reviewer`). It's stored in `data/clinic.db`, never in `config/policy.json`, and every flip is in the audit log (`reviewer_toggled`, who, from, to). While it's off, every screen shows an amber bar "Reviewer is OFF (demo)", and every answer's checks say "Reviewer: switched off for demo by <name>".
- **Three one-click attack prompts** (indirect prompt injection, an unsafe stop-your-blood-thinner instruction, and bait for identifiers and a made-up patient). The fixed filters let all three through; the reviewer catches them. Under each answer a box says what the reviewer caught, before or after the model, or that it wasn't checked. Conversations show the reviewer's verdicts.
- **Judge script**: `docs/DEMO.md` (3 minutes, works offline with `MOCK_LLM=1`). New demo account `admin_kai` (admin); clinical leads can now also see the Network page.

## New in 2.13: assistant actions (approve before anything changes)

- **The assistant can do the chores, not just answer.** Type a command in any assistant box: "Move Desmond F. from Tuesday to Wednesday 10am", "Book syn-007 tomorrow at 9:20 with Dr Osei", "Cancel syn-004's appointment tomorrow", "Fill the 11:00 slot tomorrow with Dr Lee", "Change syn-012's phone to 555-0199", "Remind syn-007 about their appointment", and for clinicians "Draft a handover for syn-004" or "Draft a referral for syn-003 to cardiology for rising INR". "What can the assistant do?" under each box lists the examples for your role.
- **It only proposes.** You get a card with the change (before -> after) and Approve / Edit / Reject. Nothing is written until a person whose role allows it approves (front desk: scheduling and contact details; clinicians: chart and referral drafts; auditors, admins and network engineers: none), with the PIN for confidential fields and chart notes. Approval writes through the normal paths, so `change_log` shows the approver.
- **Checked like answers.** Each proposal goes past the guardrails and the Nemotron reviewer: red blocks it, amber holds it until the approver confirms. Two matching patients or a taken slot gives a "pick one" card with choices; it never guesses. Details, flow chart and the not-yet-built list: `NOTES.md` -> "Assistant actions (v2.13)".

## New in 2.11: a second model reviews every answer (NVIDIA Nemotron)

- **What it does.** Every doctor-assistant and front-desk-assistant turn now goes past a separate local reviewer model twice: **before** the chat model (the masked question plus the minimized record or schedule) and **after** it (the answer). It looks for prompt injection, unsafe clinical advice, identifiers, invented patients and out-of-scope requests, and answers `green`, `amber` or `red`.
- **It can only make things stricter.** The reviewer can raise a tier, never lower one; the fixed guardrails stay in charge. A red before the model means the chat model is never called (the request goes to a second person). Amber or red after the model holds the answer, exactly like today.
- **Fails closed.** If the reviewer is on but unreachable, too slow (`timeout_s`, 20 s) or gives unusable output, the answer is held for a person: "Reviewer unavailable; held for a person."
- **Turn it on on the Mac:** `ollama pull nemotron-mini` (about 2.7 GB, one time). That's all: `reviewer.enabled` is already `true` in `config/policy.json`, and the app starts using the model as soon as it's installed (checked every 30 seconds, no restart needed).
- **Until the model is installed** (`reviewer.when_model_missing: "skip"`, the shipped setting), answers are not held; instead the reviewer is reported as off: a yellow "Reviewer (before model): off: Model not installed: run ollama pull nemotron-mini" line in every answer's safety checks, a **down** Reviewer box on the Network page (so Home shows a service down for network roles), `reviewer.state = "missing"` in `/api/me`, and a line when the app starts. Set it to `"hold"` to hold every answer until the model is there. Set `enabled` to `false` to switch the reviewer off (the trace then says "Reviewer: off").
- **Logged, without content.** Audit events `reviewer_pre` / `reviewer_post` (tier, reasons, ms, ok, model) and a `model_call` per reviewer call; conversation-log rows gain `reviewer_pre_tier`, `reviewer_post_tier`, `reviewer_reasons`, `reviewer_ok` (new columns added safely; old rows still verify). Details and a flow chart: `docs/REVIEWER.md`.

## New in 2.5: grounded answers, conversation log, network view

- **"Ask the assistant" now knows today's clinic.** With no patient open, each question is sent with today's schedule from `data/clinic.db` (a clinician gets their own list, others the whole clinic; at most 25 appointments): time, visit type, status, and for clinical roles the conditions, things to check, abnormal latest results, allergies and latest note. Patients appear only as labels like `Patient A (syn-004)`, never names, record numbers, birth dates or contact details, and the text is masked and scanned for hidden instructions first (a flagged note is withheld). The model is told to use only the listed patients and never invent any; an answer that names a patient who isn't in the list is held (amber). The trace shows "Context: today's schedule (N appointments) from local database".
- **Conversation log**: every doctor-assistant and front-desk-assistant turn is saved in `clinic.db` (`conversations` table, append-only and hash-chained): masked question, checked answer, tier, reasons, model, time taken, what context was used, a link to the audit entry, and what that person changed in records afterwards. `GET /api/conversations`; clinical leads, auditors and admins see everyone's, others only their own.
- **Network engineer role** (`net_ops`, role `network_engineer`): sees only `GET /api/network`, a live map of what talks to what (browsers, the app, Ollama, the database files, an optional Leash gateway), whether anything can leave the machine, and recent model calls. No patient data, no schedule, no assistant. Every call to Ollama is recorded in the audit log with where, how long and whether it worked, never the content. Settings: `network` in `config/policy.json`.

## New in 2.4: a real clinic database

- **`data/clinic.db`** (SQLite, ships with Python) is now the source of truth for registered patients and appointments. The front desk registers patients, books and checks them in; clinicians add clinical details. Reception cannot change clinical details (`edit_chart` is not in its role).
- **Every change is tracked**: each write saves the record and a `change_log` entry (who, role, when, what, before and after) in one transaction. The change log is append-only (SQLite triggers refuse edits and deletes) and hash-chained, so a change made behind the app's back is found. Check it any time with `python3 scripts/verify_db.py`.
- **Calendar**: `GET /api/calendar?from=&to=[&clinician=]` (up to 42 days) for browsing patients by day; `GET /api/patients/<id>/history` shows every change to a patient and their appointments (clinical roles, auditor and admin; not the front desk); `GET /api/db/status` shows counts and the chain check.
- The assistant reads the patient straight from the database on every question, so it always sees the latest chart.

## New in 2.3: a full clinic day

- **Front desk role (`desk_sam`)**: schedule, check-in, booking, reminders and registering patients. The server builds every front-desk view from an allow-list in `config/policy.json` (`frontdesk.allowed_fields`), so clinical data never reaches those screens. Its assistant gets only the schedule, with patient names replaced by tags, and clinical questions are redirected without reaching the model.
- **Doctor side**: today's patients with what needs checking, start and finish visits, full chart, add to the chart.
- **PIN for confidential details**: birth date, phone, address, record number and insurance ID are hidden on every screen until the PIN is typed, every time. Demo PIN 1234 (`confidential.pin`). Five wrong tries lock the account for 5 minutes. Every reveal and wrong PIN is in the audit log.
- **Adding to the database**: register patients and add notes, findings, results, medicines, allergies and things to check. Every field is validated (impossible lab values, allergy clashes and duplicate patients are refused). Nothing is edited or deleted: stopped medicines and resolved items are kept with who, when and why. Each addition goes into the hash-chained change log in `data/clinic.db` (2.4; this replaced `data/chart_history.jsonl`) and refreshes the patient's entry in the vector store.
- **Error-proofed flows**: buttons stay off until inputs are valid, only open times can be booked, check-in needs the identity checks, steps can't be skipped, two people can't change the same appointment at once, and anything that can't be undone needs a second press.
- **Faster answers**: the model is loaded when the app starts and kept loaded for 30 minutes; answers are capped in length.

See `docs/DEMO.md` for the 3-minute reviewer demo for judges, and `docs/DEMO-SCRIPT.md` for an 8-minute walkthrough.

## What it enforces

| Rule | Where |
| --- | --- |
| Model must be on this machine; any non-local model address is refused, and there is no cloud fallback | `app/llm.py` |
| The web app only listens on `127.0.0.1` (not reachable from the network) | `config/policy.json`, `app/server.py` |
| Accounts are created by an admin on the command line; no self sign-up | `manage_users.py` |
| Roles: clinician, nurse, clinical lead, auditor, admin, receptionist, network engineer, each with a fixed permission list | `config/policy.json` → `roles` |
| Names, dates, phone numbers, MRNs, emails, addresses masked before the model or the log sees them | `app/privacy.py` |
| Prompt-injection and off-topic requests blocked; urgent words add an emergency notice | `app/guardrails.py` + `scope` in policy |
| Every answer is marked as a draft for clinician review; overconfident wording is flagged | `app/guardrails.py` |
| **The AI never contacts anyone.** It drafts messages for allow-listed recipient groups only, a clinician approves or rejects, and a person sends the approved text | `communication` in policy, Messages tab |
| Hash-chained audit log; any edited or deleted line is detected | `app/audit.py`, Audit tab |
| Local vector store: append-only (SQLite triggers refuse edits and deletes) and hash-chained, holding masked text only | `app/vectorstore.py`, Audit tab |
| Sessions expire after 30 minutes; 20 requests per minute per user; strict browser security headers | `app/server.py` |

All restrictions are in **`config/policy.json`**, so you can review and change them without touching code.

## Where answers go

Every request and answer is scored **green**, **amber** or **red** (`tiers` in the policy file):

| Tier | When | What the person sees | Who reviews |
| --- | --- | --- | --- |
| Green, "No flags" | All checks clean | The answer, as a draft | 10% randomly copied to an auditor as a quality sample |
| Amber, "Held" | Possible emergency, hidden characters, long pasted text, overconfident wording; every patient-portal draft | The reasons first; the answer after they confirm they read them | The person who asked |
| Red, "Blocked" | Rule-change attempts, off-topic requests, an identifier or dangerous instruction in the answer | Nothing | A clinical lead or admin, never the asker |

Screens: **Patients** (40 synthetic patients; open a record and chat with the assistant about it), **Ask the assistant** (general questions), **Review queue** (held, blocked and sampled items for your role), **Messages** (drafts for other people, clinician approval), **Audit log**.

## Synthetic patients and the database

Patients and appointments live in `data/clinic.db` (tables `patients`, `appointments`, and the append-only, hash-chained `change_log`). On the first start of 2.4 an empty database is filled from `data/patients.json` and `data/schedule.json` if they exist (one `imported` change each, by `system`); the JSON files are left as they were and no longer written. With no JSON, patients are generated as below. Demo appointments are added the first time a day within 14 days of today is looked at (past days come out finished). Delete `data/clinic.db` to start again from the JSON files.

The synthetic patients come from `app/ehr.py`: 40 made-up patients built from 13 scenarios that a clinician would need to act on (rising HbA1c, high potassium after an NSAID in kidney disease, INR 4.3 after ciprofloxacin on warfarin, fluid overload in heart failure, penicillin allergy with amoxicillin prescribed, possible pre-eclampsia, rising PHQ-9, falling hemoglobin on apixaban, and more). One referral letter is deliberately poisoned with hidden instructions.

When someone asks about a patient, the model gets a minimum-necessary copy: no name, record number, birth date, phone or address, and dates turned into "N days ago". Each note is scanned first; a note with hidden instructions is withheld, the answer is held (amber), and the note goes to a clinical lead (red). Every record opened is logged, and opening more than 12 different records in 10 minutes is stopped and reported.

## Local vector store (instead of Pinecone or Snowflake)

`data/vectors.sqlite` is a vector database built on SQLite, which ships with Python, so there is nothing to install and it works offline. Pinecone and Snowflake are cloud services, so patient text would leave the building.

- **Immutable:** SQLite triggers refuse every UPDATE and DELETE; a change is a new row, and the newest row for a document wins.
- **Tamper-evident:** each row stores a SHA-256 hash of the previous row plus its own text and vector. The Audit tab verifies the chain and says which row was changed.
- **No identifiers:** only masked text goes in; names are never searched.
- **Embeddings:** a built-in offline embedder by default. For better matches, run `ollama pull nomic-embed-text`, set `"ollama_embed_model": "nomic-embed-text"` under `vectors` in the policy, and add a calibrated threshold for `ollama:nomic-embed-text`.

Uses: **Similar cases** on each patient record, and catching **reworded prompt injections** in notes that the fixed patterns miss (notes that read like the 12 known attack examples are withheld).

## Quick start on a Mac

Open the Ollama app, then double-click **`Start Clinic Assistant.command`** in this folder (first time: right-click, Open). It stops any older copy, creates demo accounts (or reuses your old ones), and opens the app. See `START-HERE.txt`. The top bar shows the version, so you can confirm you're on the new one.

## Run it on your Mac (manual)

Needs Python 3.8+ (check with `python3 --version`) and Ollama. Nothing else to install.

```bash
# 1. Get a model (one-time). MedGemma 1.5 4B is a community build of Google's model.
ollama pull MedAIBase/MedGemma1.5:4b
# Optional, recommended: the reviewer model that checks every answer (about 2.7 GB)
#   ollama pull nemotron-mini
#    On an Intel Mac this runs on the CPU and is slow. For faster testing try:
#    ollama pull llama3.2:3b   then set "chat_model": "llama3.2:3b" in config/policy.json

# 2. Keep Ollama local-only (it is by default; this makes sure)
launchctl setenv OLLAMA_HOST 127.0.0.1      # then restart the Ollama app

# 3. Create accounts (you'll be asked for a password, 12+ characters)
cd medical-local-ai
python3 manage_users.py add dr_lee clinician
python3 manage_users.py add nurse_kim nurse
python3 manage_users.py add lead_ana clinical_lead
python3 manage_users.py add auditor_ray auditor

# 4. Start it, then open http://127.0.0.1:8642
python3 run.py
```

No model yet? Start with `MOCK_LLM=1 python3 run.py` to click through the app with a stand-in model.

Run the checks: `python3 -m unittest -v` (59 tests, uses the stand-in model and a stand-in reviewer).

Optional upgrades:
- Better name detection: `pip install presidio-analyzer presidio-anonymizer && python3 -m spacy download en_core_web_lg`. The app uses it automatically when installed.
- Safety model: `ollama pull llama-guard3:1b` and set `"safety_model": "llama-guard3:1b"`.

## Not done yet (needed before any real patient data)

- HTTPS and single sign-on with MFA (put it behind the clinic's identity proxy).
- Disk encryption (turn on FileVault) and copy `data/audit.jsonl` to write-once storage regularly.
- Firewall rule blocking outbound internet from the machine that runs the model.
- Accuracy testing against clinician-written answers for the one job you pilot.
- A risk assessment signed off by whoever is responsible for privacy and compliance.

## Files

```
config/policy.json   all rules: scope, roles, communication, logging
app/server.py        the gatekeeper web service
app/privacy.py       identifier masking
app/guardrails.py    input and output checks
app/llm.py           local-only model calls (Ollama)
app/audit.py         hash-chained audit log
app/vectorstore.py   local append-only vector store (SQLite)
app/db.py            clinic database (SQLite): patients, appointments, change log
app/ehr.py           patients (read and written through app/db.py), synthetic generator
app/schedule.py      appointments, booking and check-in rules
app/network.py       network view (no patient data)
app/reviewer.py      the reviewer model (Nemotron via Ollama), before and after the chat model
app/actions.py       assistant actions: chat commands -> proposals -> human approval
scripts/verify_db.py database counts and change-log check
app/users.py         accounts and password hashing
static/              the web page (no external scripts)
data/                clinic.db, users, outbox, audit log (created on first run; keep private)
```
