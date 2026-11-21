# Patient portal (Clinic Assistant 2.8): plan and contract

Written 2026-11-21 17:30 America/Chicago. Deadline for working, tested, committed code: 20:30.
All paths below are relative to `clinic-assistant/`. Standard library only. Synthetic data only.

## 1. Features

| # | Feature | Tag |
|---|---|---|
| F1 | Patient accounts: admin creates them with `manage_users.py add <user> patient <patient_id>`; each is linked to exactly one patient id. No self sign-up. Login refuses a patient account whose link is missing or points at no patient. | core |
| F2 | Confinement: a session with a linked patient may call only `/api/me`, `/api/logout` and `/api/portal/*`. Every other `/api/*` route returns 403 for it. Portal routes take **no patient id** from URL or body; they use `session["patient_id"]` only. | core |
| F3 | Own chart summary: only the fields in `portal.released_fields` (policy), built from an allow-list. Notes, "things to check" (`attention`), MRN, insurance and scenario never reach the patient. | core |
| F4 | Own appointments: upcoming and past, with clinician name, visit type and status. | core |
| F5 | Appointment requests through the front desk: patient asks for a new appointment (visit type, optional clinician, preferred times as text, note) or asks to cancel one of their own upcoming booked appointments. Requests land in the front desk's queue; reception books or cancels with the existing tools and marks the request done or declined with a note. The patient sees the request status. The portal never writes to the schedule itself. | core |
| F6 | Secure messages: patient writes to the care team; clinicians, nurses and leads see them in a staff inbox and reply. Patient sees the thread. | core |
| F7 | Clinician-approved AI messages: a `patient-portal` draft now carries a `patient_id`. It is invisible to the patient while drafted, approved or rejected. Only after approval can a staff member press "Send to patient portal", which copies the approved `final_text` into the patient's messages (once). | core |
| F8 | Logging: every portal read writes an audit entry; every portal write writes a `change_log` row (and an audit entry). Staff inbox reads are audited too. | core |
| F9 | Urgent-words notice: if a patient message matches `scope.urgent_patterns`, the response carries `urgent: true` and the portal tells them to call the clinic or emergency services now. The portal always shows "messages are not for emergencies". | core (small) |
| F10 | Front desk sees requests with the front-desk allow-list view of the patient only (never message bodies). | core |
| F11 | Unread counts (staff inbox badge). | if time |
| F12 | Refuse sending an approved draft that still contains `[TAG]` placeholders. | if time |

Rejected:
- **Patient self-booking into open slots**: bypasses the front desk the task asked for, and needs slot locking for a second actor. Requests cover it.
- **Patient-facing AI chat**: would let model text reach a patient without clinician approval. Violates the core rule.
- **Self sign-up / password reset by email**: no self sign-up rule; email leaves the machine.
- **Showing clinical notes or lab trends**: notes can carry injected text (the poisoned referral) and are not released by default; results are released as plain rows only.
- **Proxy access (parent/carer)**: needs a many-to-many link and consent model. No time.
- **Attachments**: file uploads are a large new attack surface.
- **Read receipts**: messages are append-only, and an update path is not worth it today.

## 2. Contract

### 2.1 policy.json additions

```json
"roles": {
  "patient": ["portal_chart", "portal_appointments", "portal_messages"],
  "clinician": [... existing ..., "portal_inbox", "send_portal"],
  "nurse": [... existing ..., "portal_inbox", "send_portal"],
  "clinical_lead": [... existing ..., "portal_inbox", "send_portal"],
  "receptionist": [... existing ..., "portal_requests"]
},
"portal": {
  "_comment": "Patient portal (2.8). A patient account is linked to one patient id and sees only that record, through the fields listed here.",
  "patient_role": "patient",
  "released_fields": ["id", "name", "age", "sex", "birthDate", "conditions", "medications", "allergies", "observations", "preferred_contact", "language"],
  "max_subject_chars": 120,
  "max_body_chars": 2000,
  "max_note_chars": 300,
  "max_open_requests": 5,
  "emergency_notice": "Messages are not for emergencies. If this is urgent, call the clinic on 555-0100 or your local emergency number now."
}
```
`name` in the patient view is the string "Given Family". `observations` are passed as stored (date, name, value, unit, ref).

### 2.2 Data layer (`app/db.py`)

New tables (created by `SCHEMA`, `IF NOT EXISTS`, so the committed `data/clinic.db` upgrades on open):

```sql
CREATE TABLE IF NOT EXISTS portal_messages (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT NOT NULL UNIQUE, patient_id TEXT NOT NULL, at TEXT NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('from_patient', 'to_patient')),
    sender TEXT NOT NULL,          -- username of the patient or staff member who sent it
    sender_role TEXT,
    subject TEXT, body TEXT NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('patient', 'staff', 'approved_draft')),
    draft_id TEXT, approved_by TEXT, in_reply_to TEXT
);
-- append-only: triggers refuse UPDATE and DELETE, like change_log
CREATE TABLE IF NOT EXISTS portal_requests (
    id TEXT PRIMARY KEY, patient_id TEXT NOT NULL, created_at TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('book', 'cancel')),
    appointment_id TEXT, visit_type TEXT, clinician TEXT, preferred TEXT, note TEXT,
    status TEXT NOT NULL CHECK (status IN ('open', 'done', 'declined')),
    handled_by TEXT, handled_at TEXT, staff_note TEXT
);
```

`change_log` keeps its `CHECK (entity IN ('patient','appointment'))`: portal writes are logged as
`entity='patient', entity_id=<patient_id>`, actions `portal_message`, `portal_request`, `portal_request_done`,
`portal_request_declined`, with `after_json` = the row. So `verify_chain()`, `verify_db.py` and the
patient's history all keep working with no migration.

New `ClinicDB` methods (each insert/update and its change_log row in ONE transaction, `self.version += 1`):
- `add_portal_message(row: dict, by: str, role: str) -> dict` — row has `id, patient_id, direction, sender, sender_role, subject, body, source, draft_id, approved_by, in_reply_to`; sets `at`. Summary: `"Portal message from patient"` / `"Portal message to patient"` (no body text in the summary).
- `portal_messages(patient_id: str | None = None, limit: int = 200) -> list[dict]` — newest first; `None` = all patients (staff inbox).
- `portal_message(msg_id: str) -> dict | None`
- `add_portal_request(row: dict, by: str, role: str) -> dict` — sets `created_at`, `status='open'`.
- `decide_portal_request(req_id: str, status: str, by: str, role: str, staff_note: str) -> dict` — status `done|declined`; raises `ValueError` if not open or missing.
- `portal_requests(patient_id: str | None = None, status: str | None = None, limit: int = 200) -> list[dict]` — newest first.
- `portal_request(req_id: str) -> dict | None`
- `appointments_for_patient(patient_id: str) -> list[dict]` — all of that patient's appointments, sorted by date, time.
- Refactor: the change_log append inside `_write` becomes `_log(entity, entity_id, action, by, role, summary, before, after)` used by both; the hashed fields and digest are unchanged.

### 2.3 Accounts (`app/users.py`, `manage_users.py`)

- `UserStore.add(username, password, role, patient_id: str | None = None)`. If `role == "patient"` a `patient_id` is required; any other role with a `patient_id` raises `ValueError`. Stored in the user record as `"patient_id"`.
- `UserStore.patient_id(username) -> str | None`.
- `UserStore.list()` stays a list of `(name, role, active)` tuples (callers unpack 3).
- `manage_users.py add <user> patient <patient_id>`: checks the id exists in `data/clinic.db` (read-only `ClinicDB(...).patient(pid)`) before asking for the password. `list` shows the linked id.

### 2.4 Server changes (`app/server.py`) and the portal module (`app/portal.py`)

`app/portal.py` holds `class Portal` (business logic) and `handle_get(app, s, path, qs)` / `handle_post(app, s, path, data)` returning `(code, body)` or `None` for "not mine". `server.py` calls them.

Login: if `role == portal.patient_role`, look up `users.patient_id(user)`; refuse (401, same message as a wrong password, audit `login_refused_unlinked`) if missing or `app.ehr.get(pid)` is None. Session gets `"patient_id": pid`. Staff sessions have no `patient_id` key.

Confinement (in `do_GET` and `do_POST`, right after the session check): if `s.get("patient_id")` and the path is not `/api/me`, `/api/logout` or under `/api/portal/` → `403 {"error": "Patient accounts can use the patient portal only."}`, audit `portal_staff_route_refused` with `path`.
Conversely every `/api/portal/*` route requires `s.get("patient_id")` and the route's permission, else 403.

`/api/me` for a patient session returns only: `{"user", "role", "permissions", "version", "clinic", "patient": {"id", "name"}, "portal": true}` (no model, recipient groups, leash or presidio fields).

Static files: `/portal` → `portal.html`, `/portal.js`, `/portal.css`.

Errors are `{"error": "<sentence>"}`. Not signed in = 401. Wrong role/permission = 403. Not yours or missing = 404 (same message, so ids can't be probed). Bad input = 400. State conflict = 409.

#### Patient routes (session must have `patient_id`)

| Method, path | Perm | Request | Response 200 | Logs |
|---|---|---|---|---|
| GET `/api/portal/chart` | portal_chart | – | `{"patient": {<released_fields only>}}` | audit `portal_chart_viewed` (patient_id) |
| GET `/api/portal/appointments` | portal_appointments | – | `{"upcoming": [Appt], "past": [Appt], "requests": [Req], "visit_types": [...], "clinicians": [{"id","name"}], "clinic_phone": "555-0100"}` | audit `portal_appointments_viewed` |
| POST `/api/portal/appointments/request` | portal_appointments | `{"visit_type", "clinician"?, "preferred"?, "note"?}` | `{"request": Req}` | change_log `portal_request`; audit `portal_request_created` |
| POST `/api/portal/appointments/cancel` | portal_appointments | `{"appointment_id", "note"?}` | `{"request": Req}` | same as above |
| GET `/api/portal/messages` | portal_messages | – | `{"messages": [Msg], "emergency_notice": str}` | audit `portal_messages_viewed` (count) |
| POST `/api/portal/messages` | portal_messages | `{"subject", "body", "in_reply_to"?}` | `{"message": Msg, "urgent": bool, "notice": str}` | change_log `portal_message`; audit `portal_message_sent` |

- `Appt` = `{"id", "date", "time", "clinician_name", "visit_type", "status", "can_cancel": bool}`. No `patient_id`, no history, no reminder internals. `can_cancel` = status `booked`, date today or later, and no open cancel request for it.
- `Req` = `{"id", "kind", "appointment_id", "visit_type", "clinician", "preferred", "note", "status", "created_at", "handled_at", "staff_note"}` (no `handled_by` username for the patient).
- `Msg` = `{"id", "at", "direction", "subject", "body", "from": "You" | "Care team" , "in_reply_to"}` for the patient (no staff usernames, no draft ids).
- Validation: `visit_type` in `clinic.visit_types`; `clinician` empty or in `clinic.clinicians`; text fields stripped and cut to the policy limits; `body` required. `appointment_id` must be one of this patient's appointments (else 404), status `booked`, not in the past (else 409), no open cancel request for it (409). More than `max_open_requests` open requests → 409. `in_reply_to` must be a message of this patient (else 404).
- Urgent: `urgent` = any `scope.urgent_patterns` matches subject+body (case-insensitive); `notice` = `portal.emergency_notice` always.

#### Staff routes (refused for patient sessions by confinement)

| Method, path | Perm | Request | Response 200 | Logs |
|---|---|---|---|---|
| GET `/api/inbox` | portal_inbox | `?patient_id=` optional filter | `{"messages": [StaffMsg]}` newest first | audit `portal_inbox_viewed` (count, patient_id filter) |
| POST `/api/inbox/reply` | portal_inbox | `{"message_id", "body", "subject"?}` | `{"message": StaffMsg}` | change_log `portal_message`; audit `portal_reply_sent` |
| GET `/api/inbox/requests` | portal_requests | `?status=open` optional | `{"requests": [StaffReq]}` | audit `portal_requests_viewed` |
| POST `/api/inbox/requests/decide` | portal_requests | `{"id", "status": "done"\|"declined", "note"?}` | `{"request": StaffReq}` | change_log `portal_request_done/declined`; audit `portal_request_decided` |
| POST `/api/outbox/send` | send_portal | `{"id"}` (outbox draft id) | `{"item": OutboxItem, "message": StaffMsg}` | change_log `portal_message`; audit `draft_sent_to_portal` |

- `StaffMsg` = full row (`id, patient_id, at, direction, sender, sender_role, subject, body, source, draft_id, approved_by, in_reply_to`) plus `"patient": {"id", "name"}`.
- `StaffReq` = full request row plus `"patient": <front-desk allow-list view, redacted like other front-desk views>` and for cancel requests `"appointment": {"date","time","clinician","visit_type","status"}`.
- Reply: target must be an existing message (404); the reply goes to that message's `patient_id`, `direction='to_patient'`, `source='staff'`, `in_reply_to=message_id`.

#### Outbox changes (existing routes)
- `POST /api/outbox/draft`: when `recipient_group == "patient-portal"`, `patient_id` is required and must exist (400 otherwise); it is stored on the outbox item as `"patient_id"` and **never put in the model prompt**. Other groups ignore it.
- `POST /api/outbox/send`: item must exist (404), be `recipient_group == "patient-portal"`, `status == "approved"` (409 otherwise, including `sent`), and have a `patient_id`. Creates the portal message from `final_text` with `source='approved_draft'`, `draft_id`, `approved_by=item["decided_by"]`, `sender=<the sending staff user>`. Sets item `status='sent'`, `sent_by`, `sent_at`.
- No other route ever writes a `to_patient` message. The model is never called from a portal route.

### 2.5 Frontend
- Patient portal: new `static/portal.html`, `static/portal.js`, `static/portal.css` (vanilla, `textContent` only, CSP `'self'`, no inline script or style). Sections: header (patient name, clinic, sign out), Appointments (upcoming, past, request form, cancel button per `can_cancel`, request list with status), My health summary (released fields), Messages (thread list, compose, reply, emergency notice always visible, urgent notice after send). On 401 → `location.href = "/"`. If `/api/me` has no `portal: true` → `location.href = "/"`.
- Staff app (`static/app.js`, `index.html`, `app.css`): on start, if `me.portal` → `location.replace("/portal")`. New "Patient messages" tab (`data-perm="portal_inbox"`): inbox grouped by patient, reply box. Front desk "Portal requests" panel on the Schedule tab (`data-perm="portal_requests"`): open requests with patient view, Done / Decline with note. Messages tab: when group is `patient-portal`, show a patient picker (search via `/api/patients?q=`) and send `patient_id`; approved patient-portal drafts get a "Send to patient portal" button (`can("send_portal")`), sent ones show "Sent to <patient> by <user>".

## 3. Work split (Phase 2)

Each file has exactly one owner. Nobody edits a file outside their list.

| Agent | Owns (only these files) | Implements |
|---|---|---|
| A. Data and accounts | `app/db.py`, `app/users.py`, `manage_users.py`, `config/policy.json`, `tests/test_portal_db.py` | 2.1, 2.2, 2.3 |
| B. Routes | `app/server.py`, `app/portal.py` (new), `app/__init__.py` (VERSION = "2.8") | 2.4 |
| C. Patient frontend | `static/portal.html`, `static/portal.js`, `static/portal.css` (all new) | 2.5 patient portal |
| D. Staff frontend | `static/app.js`, `static/index.html`, `static/app.css` | 2.5 staff app |
| E. Contract tests | `tests/test_portal.py` (new) | tests from this contract only |
| F. Demo seed and docs | `setup_demo.py`, `scripts/seed_portal_demo.py` (new), `docs/DEMO-SCRIPT.md`, `README.md` | demo account `pt_lena` → `syn-002`, seed data, docs drafts |

Phase 3 (orchestrator): integration fixes in any file, repo-root `DECISIONS.md` and `PROGRESS.md`, security review fixes, screenshot `docs/ui-portal.png`.

Demo patient: **`pt_lena`**, linked to `syn-002` (Lena Delacroix), same password as the other demo accounts.
