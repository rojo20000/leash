# Setting up Clinic Assistant (V3)

For teammates and their agents. Everything runs on your own computer; all patient data is made up.
Agents: read `AGENTS.md` for the rules first.

## 1. Requirements

- Python 3.8 or newer (`python3 --version`; on Windows `python --version`). Nothing to `pip install`.
- Optional, for real answers: [Ollama](https://ollama.com) running locally.

## 2. One-command setup

```bash
cd clinic-assistant
CLINIC_DEMO_PASSWORD='pick-12-or-more-chars' python3 scripts/bootstrap.py
```

Windows PowerShell: `$env:CLINIC_DEMO_PASSWORD='pick-12-or-more-chars'; python scripts/bootstrap.py`.
Without the variable it asks for the password. Mac users can instead double-click
`Start Clinic Assistant.command`, which runs setup and opens the browser.

It creates the demo accounts (all with that one password), checks the shared synthetic database and
vector store, verifies every hash chain, and prints how to start. Safe to run again.

## 3. Start

```bash
MOCK_LLM=1 python3 run.py     # stand-in model and reviewer: no Ollama needed, placeholder answers
python3 run.py                # real local models (section 5)
```

Open http://127.0.0.1:8642. Windows: `set MOCK_LLM=1` (cmd) or `$env:MOCK_LLM=1` (PowerShell), then `python run.py`.

## 4. Logins and the demo PIN

| User | Role | Sees |
| --- | --- | --- |
| `dr_lee` | clinician | Patients, calendar, assistant, chart edits, messages |
| `nurse_kim` | nurse | Same as clinician, cannot approve messages |
| `lead_ana` | clinical_lead | Adds the red review queue and everyone's conversations |
| `desk_sam` | receptionist | Schedule, check-in, booking, front desk assistant (no clinical fields) |
| `auditor_ray` | auditor | Audit log, QA sample, conversation history |
| `net_ops` | network_engineer | Network view only |

`admin` exists as a role (audit, red queue, network) but has no demo account; add one with
`python3 manage_users.py add <name> admin`.

**Demo PIN: `1234`** (`config/policy.json` → `confidential.pin`). Needed to show MRN, birth date, phone,
address and member id, and to save a new patient or chart entry. Each reveal is logged. Demo only.

## 5. Real models (optional)

```bash
ollama pull llama3.2           # chat model (config/policy.json -> model.chat_model = "llama3.2:latest")
ollama pull nemotron-mini      # reviewer model, about 2.7 GB (policy -> reviewer.model)
```

The app notices a newly installed model within 30 seconds; no restart. Until `nemotron-mini` is
installed the reviewer reports itself as off (`reviewer.when_model_missing: "skip"`) instead of holding
every answer. **The reviewer has only been tested with the stand-in so far**; run `python3 live_check.py`
after pulling the models to check it end to end on a temporary copy of the data.
How it works: `docs/REVIEWER.md`. Design write-up: https://claude.ai/artifact/Xwta3gMSPoC3bSB2x3gRyw

## 6. Where the data lives

| Store | File | Committed? | Integrity |
| --- | --- | --- | --- |
| Patients, appointments, change log, conversation log | `data/clinic.db` (SQLite) | Yes, synthetic snapshot | `change_log` and `conversations` append-only + SHA-256 chain |
| Vector store (similar cases, injection examples) | `data/vectors.sqlite` | Yes, synthetic snapshot | Append-only + SHA-256 chain |
| Audit log (every action, no raw text) | `data/audit.jsonl` | No | SHA-256 chain |
| Accounts | `data/users.json` | **Never** | PBKDF2 hashes |
| Message drafts, review queue | `data/outbox.json`, `data/reviews.json` | No | |

Everyone loads the same 40 patients: they come from a fixed seed in `app/ehr.py`, and the committed
`clinic.db` was built from it. Appointments for today and tomorrow are added automatically on start.

- Back to a clean shared state: `python3 scripts/reset_demo_data.py` (moves the old files to
  `data/backups/<time>/`, keeps accounts, rebuilds, verifies).
- Check everything: `python3 scripts/reset_demo_data.py --check` or `python3 scripts/verify_db.py`.

## 7. Adding and updating data live

Every write goes into `clinic.db` immediately, with a `change_log` row (who, role, when, before, after)
in the same transaction. The patient's vectors are re-indexed and an audit entry is written. Visible at once
on every screen, in the record's **Chart history**, and on Home.

| Change | In the app | API (signed in, JSON) |
| --- | --- | --- |
| Register a patient | Patients → New patient (PIN) | `POST /api/patients/new` |
| Add a note, vitals, lab, medicine, allergy | Open a record → Add to chart (PIN) | `POST /api/patients/<id>/entry` |
| Book, check in, room, no-show | Schedule / Calendar | `POST /api/schedule/book`, `POST /api/schedule/status` |
| See a record's change history | Record → Chart history | `GET /api/patients/<id>/history` |
| Database status and chain check | Audit tab | `GET /api/db/status` |

A note that looks like instructions to an AI is saved but kept away from the assistant and sent to the
clinical lead (red). There is no bulk import yet (see `NOTES.md`).

## 8. Auditing the network

Sign in as `net_ops` → **Network** (or `GET /api/network`). It shows the browser, the app, Ollama,
the reviewer, the database files and the optional Leash gateway, whether each is up, whether every
configured address is local, and recent model calls (from `model_call` audit entries: where, how long,
ok; never content). With `network.public_probe` empty (the default) the app makes no outside
connection at all. It audits **this app's** traffic only; see `NOTES.md` for what it can't see.

## 9. Connecting to Leash

Off by default. Start the Leash stack from the repo root (`make dashboard`), then:

```bash
CLINIC_LEASH=1 MOCK_LLM=1 python3 run.py
```

A **Leash** tab appears for clinician, nurse and clinical lead. Searches and record opens go through
`POST /v1/tool-call` on `127.0.0.1:8000`, with one request id in both audit logs. Details and expected
results: "Human front end: Clinic Assistant" in the repo's top-level `README.md`.

## 10. Tests

```bash
MOCK_LLM=1 python3 -m unittest        # or, from the repo root: make clinic-check
```

80 tests (1 skipped), about 30 seconds, no network, no Ollama.
