# Clinic Assistant: a restricted local medical AI (prototype)

> **In the Leash repo:** this folder is a snapshot of Clinic Assistant v2.3 (work in progress), the human-facing front end for Leash. `data/vectors.sqlite` is a committed synthetic snapshot; check it with `python3 scripts/verify_stores.py`. Planning and handoff docs are in `handoff/`. Nothing here changes the Leash code outside this folder.

A small web app that puts a **gatekeeper** between people and a local AI model.
Nobody talks to the model directly. Every request is signed in, masked, checked,
answered on this computer only, checked again, and written to a tamper-evident log.

**Prototype. Use synthetic (made-up) patient data only.** It is not a medical device
and has not been validated for clinical use.

## What it enforces

| Rule | Where |
| --- | --- |
| Model must be on this machine; any non-local model address is refused, and there is no cloud fallback | `app/llm.py` |
| The web app only listens on `127.0.0.1` (not reachable from the network) | `config/policy.json`, `app/server.py` |
| Accounts are created by an admin on the command line; no self sign-up | `manage_users.py` |
| Roles: clinician, nurse, clinical lead, auditor, admin, each with a fixed permission list | `config/policy.json` → `roles` |
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

## Synthetic patients

`data/patients.json` is generated on first run from `app/ehr.py`: 40 made-up patients built from 13 scenarios that a clinician would need to act on (rising HbA1c, high potassium after an NSAID in kidney disease, INR 4.3 after ciprofloxacin on warfarin, fluid overload in heart failure, penicillin allergy with amoxicillin prescribed, possible pre-eclampsia, rising PHQ-9, falling hemoglobin on apixaban, and more). One referral letter is deliberately poisoned with hidden instructions.

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

Run the checks: `python3 -m unittest -v` (20 tests, uses the stand-in model).

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
app/ehr.py           synthetic patient generator
app/users.py         accounts and password hashing
static/              the web page (no external scripts)
data/                users, outbox, audit log (created on first run; keep private)
```
