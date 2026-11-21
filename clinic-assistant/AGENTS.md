# Clinic Assistant: instructions for agents

Read this first, then `SETUP.md` (how to run it) and `NOTES.md` (limits and roadmap).
People can read the same files; nothing here is agent-only.

## What this is

Clinic Assistant (V3, app version in `app/__init__.py`, currently 2.11) is the human-facing front end
for Leash. Staff sign in, see synthetic patients and today's schedule, and ask a **local** model
questions. Every request goes through a gatekeeper: role check, identifier masking, guardrails,
a second local reviewer model (NVIDIA Nemotron via Ollama), green / amber / red tiers, and
hash-chained logs. Python standard library only. Listens on `127.0.0.1:8642`.

## Hard rules (do not break these)

1. **Synthetic data only.** Never add real patient data, real names of real people, or real identifiers.
2. **Nothing leaves the machine.** Model and reviewer hosts must be loopback (`app/llm.py` refuses
   anything else). `network.public_probe` stays `""`. Do not add cloud APIs or telemetry.
3. **Never commit** `data/users.json`, `data/audit.jsonl`, `data/chart_history.jsonl`, `data/outbox.json`,
   `data/reviews.json`, `data/backups/`, `.env`, keys or passwords. `.gitignore` only lets through
   `data/clinic.db` and `data/vectors.sqlite` (the shared synthetic snapshot). If you commit those two,
   regenerate them first with `python3 scripts/reset_demo_data.py` so they hold no conversations.
4. **Append-only stores stay append-only.** Do not drop the `no_update` / `no_delete` triggers or
   rewrite rows in `change_log`, `conversations` or `vectors`. A correction is a new row.
5. **Every data change goes through `ClinicDB.write` / `write_many`** (`app/db.py`), so it lands in
   `change_log` in the same transaction. Do not write to `patients` or `appointments` directly.
6. **The reviewer can only raise a tier, never lower it.** Guardrails in `app/guardrails.py` stay in charge.
7. **Leash integration is off by default** (`leash.enabled: false`). Keep it that way in commits.
8. Rules live in `config/policy.json`. Change behaviour there, with a `_comment` / `_<key>` note, not in code.
9. Leash repo rule: the Leash code outside `clinic-assistant/` belongs to the Leash build. Don't edit it from here.

## Commands

Run from `clinic-assistant/`. On Windows use `python` instead of `python3`.

| Task | Command |
| --- | --- |
| One-command setup (accounts, data, checks) | `CLINIC_DEMO_PASSWORD='<12+ chars>' python3 scripts/bootstrap.py` |
| Start with a stand-in model (no Ollama) | `MOCK_LLM=1 python3 run.py` |
| Start with real local models | `python3 run.py` (needs Ollama, see SETUP.md) |
| All tests (stand-in model and reviewer) | `MOCK_LLM=1 python3 -m unittest` (94 tests, 1 skipped) or `make clinic-check` from the repo root |
| Reset data to the shared synthetic state | `python3 scripts/reset_demo_data.py` (backs up first, keeps accounts) |
| Verify every chain | `python3 scripts/reset_demo_data.py --check`, `python3 scripts/verify_db.py`, `python3 scripts/verify_stores.py` |
| Real-model smoke test on a temp copy | `python3 live_check.py` |
| Integrated mode through the Leash gateway | `CLINIC_LEASH=1 MOCK_LLM=1 python3 run.py` (Leash stack running) |

Done means: the tests pass, `reset_demo_data.py --check` reports every chain OK, and the app starts
and answers `GET /api/version`.

## Map

| Path | What |
| --- | --- |
| `app/server.py` | HTTP server, sessions, roles, every `/api/*` route, the request pipeline |
| `app/db.py` | `data/clinic.db`: patients, appointments, `change_log`, `conversations` (hash-chained, append-only) |
| `app/vectorstore.py` | `data/vectors.sqlite`: similar cases + reworded-injection detection (hash-chained, append-only) |
| `app/actions.py` | Assistant actions: chat command -> proposal card -> role/PIN-gated human approval (2.12) |
| `app/reviewer.py` | Nemotron reviewer, before and after the chat model; fail closed. Design: `docs/REVIEWER.md` |
| `app/guardrails.py`, `app/privacy.py` | Input/output checks; identifier masking |
| `app/llm.py` | Local-only Ollama client; `MOCK_LLM=1` stand-in |
| `app/network.py` | Network view: who talks to whom, model calls from the audit log, store health |
| `app/leash_client.py` | Integrated mode client for the Leash gateway (`POST /v1/tool-call`) |
| `app/ehr.py`, `app/records.py`, `app/schedule.py` | Synthetic patient generator (fixed seed), chart entries, calendar and front desk |
| `app/audit.py` | Hash-chained JSONL audit log |
| `config/policy.json` | All rules: roles, tiers, scope, PIN, reviewer, leash, network |
| `static/` | The web UI (no external scripts) |
| `tests/` | unittest suites; `tests/stub_gateway.py` stands in for Leash |
| `scripts/` | `bootstrap.py`, `reset_demo_data.py`, `verify_db.py`, `verify_stores.py` |
| `handoff/` | Planning docs and the Leash overseer handoff |

## Request pipeline (one assistant turn)

sign-in and role → mask identifiers → guardrail input check → minimized context (record or schedule,
notes scanned for injections, vector match) → reviewer PRE → chat model → guardrail output check →
reviewer POST → tier = worst of all checks → green shown as draft / amber held for the asker /
red to a second person → audit log + `conversations` row (no raw text in the audit log).
