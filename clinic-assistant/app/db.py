"""The clinic database: one local SQLite file (data/clinic.db), standard library only.

It is the source of truth for registered patients and appointments. Every
change to either goes through `ClinicDB.write`, which saves the row AND an
entry in `change_log` in the same transaction, so there is never a change
without a record of who made it.

change_log is append-only (SQLite triggers refuse UPDATE and DELETE) and
hash-chained: each row stores sha256(prev_hash + canonical JSON of its fields),
so `verify_chain()` finds any row that was edited behind the app's back.

The web server is threaded, so the app uses one connection guarded by a lock.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from pathlib import Path

GENESIS = "0" * 64
HASHED = ("at", "by_user", "role", "entity", "entity_id", "action", "summary", "before_json", "after_json")
MSG_COLS = ("id", "patient_id", "at", "direction", "sender", "sender_role", "subject", "body", "source",
            "draft_id", "approved_by", "in_reply_to")
REQ_COLS = ("id", "patient_id", "created_at", "kind", "appointment_id", "visit_type", "clinician", "preferred",
            "note", "status", "handled_by", "handled_at", "staff_note")
CONV_HASHED = ("id", "at", "user", "role", "kind", "patient_id", "question", "answer", "tier", "reasons",
               "review_id", "model", "duration_ms", "context_summary", "audit_ref", "change_seq")
# Added in 2.11 by ALTER TABLE. Rows written since then have hash_v = 2 and their hash covers these too;
# older rows (hash_v NULL) still verify with the original field list.
REVIEW_FIELDS = ("reviewer_pre_tier", "reviewer_post_tier", "reviewer_reasons", "reviewer_ok")
CONV_HASHED_V2 = CONV_HASHED + REVIEW_FIELDS

SCHEMA = """
CREATE TABLE IF NOT EXISTS patients (
    id TEXT PRIMARY KEY,
    mrn TEXT, family TEXT, given TEXT, birth_date TEXT,
    registered_at TEXT, registered_by TEXT, updated_at TEXT,
    doc TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS patients_name ON patients(family, given);
CREATE INDEX IF NOT EXISTS patients_mrn ON patients(mrn);
CREATE INDEX IF NOT EXISTS patients_birth ON patients(birth_date);

CREATE TABLE IF NOT EXISTS appointments (
    id TEXT PRIMARY KEY,
    date TEXT NOT NULL, time TEXT NOT NULL, clinician TEXT NOT NULL,
    patient_id TEXT NOT NULL, visit_type TEXT, status TEXT NOT NULL,
    doc TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS appts_day ON appointments(date, clinician);
CREATE INDEX IF NOT EXISTS appts_patient ON appointments(patient_id);

CREATE TABLE IF NOT EXISTS change_log (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT NOT NULL, by_user TEXT, role TEXT,
    entity TEXT NOT NULL CHECK (entity IN ('patient', 'appointment')),
    entity_id TEXT NOT NULL, action TEXT NOT NULL, summary TEXT,
    before_json TEXT, after_json TEXT,
    prev_hash TEXT NOT NULL, hash TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS change_entity ON change_log(entity, entity_id);

CREATE TRIGGER IF NOT EXISTS change_log_no_update BEFORE UPDATE ON change_log
BEGIN SELECT RAISE(ABORT, 'change_log is append-only'); END;
CREATE TRIGGER IF NOT EXISTS change_log_no_delete BEFORE DELETE ON change_log
BEGIN SELECT RAISE(ABORT, 'change_log is append-only'); END;

-- One row per assistant turn (doctor chat or front-desk assistant). Masked question, checked answer.
-- Append-only and hash-chained like change_log. change_seq = the last change_log seq when the turn happened.
CREATE TABLE IF NOT EXISTS conversations (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT NOT NULL UNIQUE, at TEXT NOT NULL, user TEXT, role TEXT, kind TEXT NOT NULL,
    patient_id TEXT, question TEXT, answer TEXT, tier TEXT, reasons TEXT, review_id TEXT, model TEXT,
    duration_ms INTEGER, context_summary TEXT, audit_ref TEXT, change_seq INTEGER NOT NULL,
    prev_hash TEXT NOT NULL, hash TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS conv_user ON conversations(user);
CREATE INDEX IF NOT EXISTS conv_patient ON conversations(patient_id);
CREATE TRIGGER IF NOT EXISTS conversations_no_update BEFORE UPDATE ON conversations
BEGIN SELECT RAISE(ABORT, 'conversations is append-only'); END;
CREATE TRIGGER IF NOT EXISTS conversations_no_delete BEFORE DELETE ON conversations
BEGIN SELECT RAISE(ABORT, 'conversations is append-only'); END;

-- Patient portal. Messages between one patient and the care team. Append-only like change_log;
-- every insert also writes a change_log row (entity 'patient'), so the hash chain covers it.
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
CREATE INDEX IF NOT EXISTS portal_messages_patient ON portal_messages(patient_id);
CREATE TRIGGER IF NOT EXISTS portal_messages_no_update BEFORE UPDATE ON portal_messages
BEGIN SELECT RAISE(ABORT, 'portal_messages is append-only'); END;
CREATE TRIGGER IF NOT EXISTS portal_messages_no_delete BEFORE DELETE ON portal_messages
BEGIN SELECT RAISE(ABORT, 'portal_messages is append-only'); END;

-- Appointment requests a patient sends to the front desk. The portal never writes to appointments.
CREATE TABLE IF NOT EXISTS portal_requests (
    id TEXT PRIMARY KEY, patient_id TEXT NOT NULL, created_at TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('book', 'cancel')),
    appointment_id TEXT, visit_type TEXT, clinician TEXT, preferred TEXT, note TEXT,
    status TEXT NOT NULL CHECK (status IN ('open', 'done', 'declined')),
    handled_by TEXT, handled_at TEXT, staff_note TEXT
);
CREATE INDEX IF NOT EXISTS portal_requests_patient ON portal_requests(patient_id);

CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS seeded_days (date TEXT PRIMARY KEY);
"""


def _stamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _digest(prev: str, row: dict, fields=HASHED) -> str:
    canon = json.dumps({k: row[k] for k in fields}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256((prev + canon).encode()).hexdigest()


def _dump(doc) -> str | None:
    return None if doc is None else json.dumps(doc, sort_keys=True, separators=(",", ":"))


class ClinicDB:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.conn = sqlite3.connect(str(self.path), check_same_thread=False, isolation_level=None)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.executescript(SCHEMA)
        have = {r[1] for r in self.conn.execute("PRAGMA table_info(conversations)")}
        for col, kind in [("reviewer_pre_tier", "TEXT"), ("reviewer_post_tier", "TEXT"), ("reviewer_reasons", "TEXT"),
                          ("reviewer_ok", "INTEGER"), ("hash_v", "INTEGER")]:
            if col not in have:  # safe on an append-only table: existing rows get NULL, nothing is rewritten
                self.conn.execute(f"ALTER TABLE conversations ADD COLUMN {col} {kind}")
        self.version = 0  # bumped on every write, so caches know to reload

    def close(self) -> None:
        with self.lock:
            self.conn.close()

    # ---- the one way to change anything ---------------------------------
    def write(self, entity: str, doc: dict, action: str, by: str | None, role: str | None,
              summary: str = "") -> dict:
        """Save one patient or appointment and its change_log entry in a single transaction."""
        return self.write_many([(entity, doc, action, summary)], by, role)[0]

    def write_many(self, items: list[tuple[str, dict, str, str]], by: str | None, role: str | None) -> list[dict]:
        """Several writes in one transaction (all or nothing). items: (entity, doc, action, summary)."""
        with self.lock:
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                for entity, doc, action, summary in items:
                    self._write(entity, doc, action, by, role, summary)
                self.conn.execute("COMMIT")
            except BaseException:
                self.conn.execute("ROLLBACK")
                raise
            self.version += 1
        return [doc for _, doc, _, _ in items]

    def _write(self, entity, doc, action, by, role, summary) -> None:
        at = _stamp()
        table = {"patient": "patients", "appointment": "appointments"}[entity]
        row = self.conn.execute(f"SELECT doc FROM {table} WHERE id = ?", (doc["id"],)).fetchone()
        before = row[0] if row else None
        after = _dump(doc)
        if entity == "patient":
            n = doc.get("name") or {}
            self.conn.execute(
                "INSERT INTO patients (id, mrn, family, given, birth_date, registered_at, registered_by, updated_at, doc)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET mrn = excluded.mrn,"
                " family = excluded.family, given = excluded.given, birth_date = excluded.birth_date,"
                " updated_at = excluded.updated_at, doc = excluded.doc",
                (doc["id"], doc.get("mrn"), n.get("family"), n.get("given"), doc.get("birthDate"),
                 at, by or "system", at, after))
        else:
            self.conn.execute(
                "INSERT INTO appointments (id, date, time, clinician, patient_id, visit_type, status, doc)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET date = excluded.date,"
                " time = excluded.time, clinician = excluded.clinician, patient_id = excluded.patient_id,"
                " visit_type = excluded.visit_type, status = excluded.status, doc = excluded.doc",
                (doc["id"], doc["date"], doc["time"], doc["clinician"], doc["patient_id"], doc.get("visit_type"),
                 doc["status"], after))
        self._log(entity, doc["id"], action, by, role, summary, before, after, at)

    def _log(self, entity, entity_id, action, by, role, summary, before, after, at=None) -> None:
        """Append one change_log row. before/after are JSON text (or None). Call inside a transaction."""
        last = self.conn.execute("SELECT hash FROM change_log ORDER BY seq DESC LIMIT 1").fetchone()
        entry = {"at": at or _stamp(), "by_user": by, "role": role, "entity": entity, "entity_id": entity_id,
                 "action": action, "summary": summary, "before_json": before, "after_json": after}
        prev = last[0] if last else GENESIS
        self.conn.execute(
            "INSERT INTO change_log (at, by_user, role, entity, entity_id, action, summary, before_json,"
            " after_json, prev_hash, hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (*(entry[k] for k in HASHED), prev, _digest(prev, entry)))

    # ---- patient portal ---------------------------------------------------
    # Each write and its change_log row (entity 'patient', entity_id = the patient id) are one transaction.
    # The patients table itself is never touched here.
    def _portal_insert(self, table: str, cols: tuple, row: dict, action: str, by, role, summary: str) -> dict:
        with self.lock:
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                self.conn.execute(f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                                  tuple(row[k] for k in cols))
                self._log("patient", row["patient_id"], action, by, role, summary, None, _dump(row),
                          row.get("at") or row["created_at"])
                self.conn.execute("COMMIT")
            except BaseException:
                self.conn.execute("ROLLBACK")
                raise
            self.version += 1
        return row

    def add_portal_message(self, row: dict, by: str, role: str) -> dict:
        """Append one portal message. Sets `at`. The summary never carries the message text."""
        full = {k: row.get(k) for k in MSG_COLS}
        full["at"] = _stamp()
        summary = "Portal message from patient" if full["direction"] == "from_patient" else "Portal message to patient"
        return self._portal_insert("portal_messages", MSG_COLS, full, "portal_message", by, role, summary)

    def portal_messages(self, patient_id: str | None = None, limit: int = 200) -> list[dict]:
        """Newest first. patient_id None = every patient (staff inbox)."""
        rows = self._q(f"SELECT {', '.join(MSG_COLS)} FROM portal_messages WHERE (? IS NULL OR patient_id = ?)"
                       " ORDER BY seq DESC LIMIT ?", (patient_id, patient_id, limit))
        return [dict(zip(MSG_COLS, r)) for r in rows]

    def portal_inbox(self, per_patient: int) -> list[dict]:
        """Staff inbox: the newest `per_patient` messages of EVERY patient, newest first.

        A global LIMIT would let one busy patient push everyone else's messages out of view.
        """
        rows = self._q(f"SELECT {', '.join(MSG_COLS)} FROM (SELECT *, ROW_NUMBER() OVER"
                       " (PARTITION BY patient_id ORDER BY seq DESC) AS rn FROM portal_messages)"
                       " WHERE rn <= ? ORDER BY seq DESC", (per_patient,))
        return [dict(zip(MSG_COLS, r)) for r in rows]

    def count_patient_messages(self, patient_id: str, since: str) -> int:
        """How many messages this patient has sent at or after `since` (a _stamp()-style UTC string)."""
        return self._q("SELECT COUNT(*) FROM portal_messages WHERE patient_id = ? AND direction = 'from_patient'"
                       " AND at >= ?", (patient_id, since))[0][0]

    def portal_message(self, msg_id: str) -> dict | None:
        rows = self._q(f"SELECT {', '.join(MSG_COLS)} FROM portal_messages WHERE id = ?", (msg_id,))
        return dict(zip(MSG_COLS, rows[0])) if rows else None

    def add_portal_request(self, row: dict, by: str, role: str) -> dict:
        """Save one appointment request for the front desk. Sets created_at and status 'open'."""
        full = {k: row.get(k) for k in REQ_COLS}
        full.update(created_at=_stamp(), status="open", handled_by=None, handled_at=None, staff_note=None)
        return self._portal_insert("portal_requests", REQ_COLS, full, "portal_request", by, role,
                                   f"Portal request ({full['kind']})")

    def decide_portal_request(self, req_id: str, status: str, by: str, role: str, staff_note: str) -> dict:
        """Mark an open request done or declined. ValueError if it is missing or already decided."""
        if status not in ("done", "declined"):
            raise ValueError("status must be done or declined")
        with self.lock:
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                before = self.portal_request(req_id)
                if not before or before["status"] != "open":
                    raise ValueError("No open portal request with that id.")
                after = dict(before, status=status, handled_by=by, handled_at=_stamp(), staff_note=staff_note)
                self.conn.execute("UPDATE portal_requests SET status = ?, handled_by = ?, handled_at = ?,"
                                  " staff_note = ? WHERE id = ?",
                                  (status, by, after["handled_at"], staff_note, req_id))
                self._log("patient", after["patient_id"], f"portal_request_{status}", by, role,
                          f"Portal request {status}", _dump(before), _dump(after), after["handled_at"])
                self.conn.execute("COMMIT")
            except BaseException:
                self.conn.execute("ROLLBACK")
                raise
            self.version += 1
        return after

    def portal_requests(self, patient_id: str | None = None, status: str | None = None,
                        limit: int = 200) -> list[dict]:
        """Newest first."""
        rows = self._q(f"SELECT {', '.join(REQ_COLS)} FROM portal_requests WHERE (? IS NULL OR patient_id = ?)"
                       " AND (? IS NULL OR status = ?) ORDER BY created_at DESC, rowid DESC LIMIT ?",
                       (patient_id, patient_id, status, status, limit))
        return [dict(zip(REQ_COLS, r)) for r in rows]

    def portal_request(self, req_id: str) -> dict | None:
        rows = self._q(f"SELECT {', '.join(REQ_COLS)} FROM portal_requests WHERE id = ?", (req_id,))
        return dict(zip(REQ_COLS, rows[0])) if rows else None

    def appointments_for_patient(self, patient_id: str) -> list[dict]:
        """All of one patient's appointments, sorted by date, time."""
        return [json.loads(r[0]) for r in self._q("SELECT doc FROM appointments WHERE patient_id = ?"
                                                  " ORDER BY date, time", (patient_id,))]

    # ---- reads -----------------------------------------------------------
    def _q(self, sql: str, args=()) -> list[tuple]:
        with self.lock:
            return self.conn.execute(sql, args).fetchall()

    def patient(self, pid: str) -> dict | None:
        rows = self._q("SELECT doc FROM patients WHERE id = ?", (pid,))
        return json.loads(rows[0][0]) if rows else None

    def all_patients(self) -> list[dict]:
        return [json.loads(r[0]) for r in self._q("SELECT doc FROM patients ORDER BY id")]

    def appointment(self, appt_id: str) -> dict | None:
        rows = self._q("SELECT doc FROM appointments WHERE id = ?", (appt_id,))
        return json.loads(rows[0][0]) if rows else None

    def appointments(self, start: str, end: str | None = None, clinician: str | None = None) -> list[dict]:
        """Appointments from start to end (inclusive, YYYY-MM-DD), sorted by date, time, clinician."""
        sql, args = "SELECT doc FROM appointments WHERE date >= ? AND date <= ?", [start, end or start]
        if clinician:
            sql += " AND clinician = ?"
            args.append(clinician)
        return [json.loads(r[0]) for r in self._q(sql + " ORDER BY date, time, clinician", args)]

    def count(self, table: str) -> int:
        assert table in ("patients", "appointments", "change_log", "conversations", "portal_messages",
                         "portal_requests")
        return self._q(f"SELECT COUNT(*) FROM {table}")[0][0]

    def history(self, pid: str | None = None, limit: int = 500, include_system: bool = True) -> list[dict]:
        """change_log rows, newest first: for one patient and their appointments, or for everyone."""
        sql = "SELECT seq, at, by_user, role, entity, entity_id, action, summary FROM change_log"
        where, args = [], []
        if pid is not None:
            where.append("((entity = 'patient' AND entity_id = ?) OR (entity = 'appointment' AND entity_id IN"
                         " (SELECT id FROM appointments WHERE patient_id = ?)))")
            args += [pid, pid]
        if not include_system:
            where.append("COALESCE(by_user, 'system') != 'system'")
        if where:
            sql += " WHERE " + " AND ".join(where)
        rows = self._q(sql + " ORDER BY seq DESC LIMIT ?", (*args, limit))
        return [{"seq": r[0], "at": r[1], "by": r[2], "role": r[3], "entity": r[4], "entity_id": r[5],
                 "action": r[6], "summary": r[7]} for r in rows]

    # ---- conversations ---------------------------------------------------
    def log_conversation(self, row: dict) -> dict:
        """Append one assistant turn. row has the CONV_HASHED fields except at and change_seq."""
        with self.lock:
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                last_change = self.conn.execute("SELECT COALESCE(MAX(seq), 0) FROM change_log").fetchone()[0]
                entry = {k: row.get(k) for k in CONV_HASHED_V2}
                ok = row.get("reviewer_ok")
                entry.update(at=_stamp(), change_seq=last_change, reasons=json.dumps(row.get("reasons") or []),
                             audit_ref=_dump(row.get("audit_ref")),
                             reviewer_reasons=json.dumps(row.get("reviewer_reasons") or []),
                             reviewer_ok=None if ok is None else int(bool(ok)))
                last = self.conn.execute("SELECT hash FROM conversations ORDER BY seq DESC LIMIT 1").fetchone()
                prev = last[0] if last else GENESIS
                self.conn.execute(
                    f"INSERT INTO conversations ({', '.join(CONV_HASHED_V2)}, hash_v, prev_hash, hash) "
                    f"VALUES ({', '.join('?' * (len(CONV_HASHED_V2) + 3))})",
                    (*(entry[k] for k in CONV_HASHED_V2), 2, prev, _digest(prev, entry, CONV_HASHED_V2)))
                self.conn.execute("COMMIT")
            except BaseException:
                self.conn.execute("ROLLBACK")
                raise
        return entry

    def conversations(self, limit: int = 100, user: str | None = None, patient_id: str | None = None) -> list[dict]:
        """Turns newest first. Each has "changes": what the same user changed after it, until their next turn."""
        sql, where, args = f"SELECT seq, {', '.join(CONV_HASHED_V2)} FROM conversations", [], []
        if user:
            where.append("user = ?"); args.append(user)
        if patient_id:
            where.append("patient_id = ?"); args.append(patient_id)
        if where:
            sql += " WHERE " + " AND ".join(where)
        out = []
        for r in self._q(sql + " ORDER BY seq DESC LIMIT ?", (*args, limit)):
            item = dict(zip(("seq",) + CONV_HASHED_V2, r))
            item["reasons"] = json.loads(item["reasons"] or "[]")
            item["reviewer_reasons"] = json.loads(item["reviewer_reasons"] or "[]")
            item["reviewer_ok"] = None if item["reviewer_ok"] is None else bool(item["reviewer_ok"])
            item["audit_ref"] = json.loads(item["audit_ref"]) if item["audit_ref"] else None
            nxt = self._q("SELECT change_seq FROM conversations WHERE user IS ? AND seq > ? ORDER BY seq LIMIT 1",
                          (item["user"], item["seq"]))
            upto = nxt[0][0] if nxt else None
            rows = self._q("SELECT seq, at, by_user, role, entity, entity_id, action, summary FROM change_log"
                           " WHERE by_user IS ? AND seq > ? AND (? IS NULL OR seq <= ?) ORDER BY seq",
                           (item["user"], item.pop("change_seq"), upto, upto))
            item["changes"] = [{"seq": c[0], "at": c[1], "by": c[2], "role": c[3], "entity": c[4],
                                "entity_id": c[5], "action": c[6], "summary": c[7]} for c in rows]
            out.append(item)
        return out

    def verify_conversations(self) -> tuple[bool, int, int | None]:
        prev, n = GENESIS, 0
        with self.lock:
            for r in self.conn.execute(f"SELECT seq, {', '.join(CONV_HASHED_V2)}, hash_v, prev_hash, hash"
                                       " FROM conversations ORDER BY seq"):
                fields = CONV_HASHED_V2 if r[-3] == 2 else CONV_HASHED
                entry = dict(zip(CONV_HASHED_V2, r[1:1 + len(CONV_HASHED_V2)]))
                if r[-2] != prev or _digest(prev, entry, fields) != r[-1]:
                    return False, n, r[0]
                prev, n = r[-1], n + 1
        return True, n, None

    # ---- small bookkeeping -----------------------------------------------
    def get_meta(self, key: str) -> str | None:
        rows = self._q("SELECT value FROM meta WHERE key = ?", (key,))
        return rows[0][0] if rows else None

    def set_meta(self, key: str, value: str) -> None:
        with self.lock:
            self.conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, value))

    def seeded(self, day: str) -> bool:
        return bool(self._q("SELECT 1 FROM seeded_days WHERE date = ?", (day,)))

    def mark_seeded(self, day: str) -> None:
        with self.lock:
            self.conn.execute("INSERT OR IGNORE INTO seeded_days (date) VALUES (?)", (day,))

    # ---- integrity -------------------------------------------------------
    def verify_chain(self) -> tuple[bool, int, int | None]:
        """(ok, rows checked, seq of the first bad row or None)."""
        prev, n = GENESIS, 0
        with self.lock:
            cur = self.conn.execute(f"SELECT seq, {', '.join(HASHED)}, prev_hash, hash FROM change_log ORDER BY seq")
            for r in cur:
                entry = dict(zip(HASHED, r[1:1 + len(HASHED)]))
                if r[-2] != prev or _digest(prev, entry) != r[-1]:
                    return False, n, r[0]
                prev, n = r[-1], n + 1
        return True, n, None

    def verify(self) -> dict:
        """Same shape as AuditLog.verify(), for code that checked the old chart history file."""
        ok, n, bad = self.verify_chain()
        return {"ok": True, "entries": n} if ok else {"ok": False, "broken_at_seq": bad}

    def status(self) -> dict:
        ok, _, bad = self.verify_chain()
        out = {"engine": "sqlite", "file": f"{self.path.parent.name}/{self.path.name}",
               "patients": self.count("patients"), "appointments": self.count("appointments"),
               "changes": self.count("change_log"), "chain_ok": ok,
               "conversations": self.count("conversations"), "conversations_chain_ok": self.verify_conversations()[0]}
        if not ok:
            out["first_bad_seq"] = bad
        return out
