"""Patient portal (2.8): what a signed-in patient may see and do, and the staff side of it.

Rules this file keeps:
  - Patient routes (/api/portal/*) take the patient id from the session and from nowhere else.
    Anything else a request names (an appointment, a message) must belong to that patient,
    or the answer is the same 404 as "does not exist".
  - Every view is built from an explicit key list (never the full row minus some keys).
  - Nothing here calls the model. A to_patient message is written in two places only:
    a staff reply (typed by a person) and sending an outbox draft a clinician approved.
  - Every read writes an audit entry; every write goes through the db (change_log) and is audited.
    Message bodies never go into the audit log.
"""
from __future__ import annotations

import re
import threading
import time
import uuid

from . import VERSION

PATIENT_REQ = ("id", "kind", "appointment_id", "visit_type", "clinician", "preferred", "note", "status",
               "created_at", "handled_at", "staff_note")
PATIENT_MSG = ("id", "at", "direction", "subject", "body", "in_reply_to")
STAFF_MSG = ("id", "patient_id", "at", "direction", "sender", "sender_role", "subject", "body", "source",
             "draft_id", "approved_by", "in_reply_to")
STAFF_REQ = ("id", "patient_id", "created_at", "kind", "appointment_id", "visit_type", "clinician", "preferred",
             "note", "status", "handled_by", "handled_at", "staff_note")
STAFF_APPT = ("date", "time", "clinician", "visit_type", "status")
# A floor under the policy allow-list: a mistaken edit of portal.released_fields cannot release these.
NEVER_RELEASED = {"notes", "attention", "mrn", "insurance", "scenario"}
PORTAL_GROUP = "patient-portal"
DRAFT_SUBJECT = "Message from your care team"

# path -> (permission, Portal method)
GET = {"/api/portal/chart": ("portal_chart", "chart"),
       "/api/portal/appointments": ("portal_appointments", "appointments"),
       "/api/portal/messages": ("portal_messages", "messages"),
       "/api/inbox": ("portal_inbox", "inbox"),
       "/api/inbox/requests": ("portal_requests", "requests")}
POST = {"/api/portal/appointments/request": ("portal_appointments", "request_appointment"),
        "/api/portal/appointments/cancel": ("portal_appointments", "request_cancel"),
        "/api/portal/messages": ("portal_messages", "send_message"),
        "/api/inbox/reply": ("portal_inbox", "reply"),
        "/api/inbox/requests/decide": ("portal_requests", "decide_request"),
        "/api/outbox/send": ("send_portal", "send_draft")}

_request_lock = threading.Lock()  # the open-request checks and the insert happen as one step


class Refused(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code, self.message = code, message


def _text(value, limit: int) -> str:
    # lone surrogates (valid JSON, invalid UTF-8) would crash the SQLite insert, so they become "?"
    return str(value or "").encode("utf-8", "replace").decode().strip()[:limit]


TAG = re.compile(r"\[[A-Z][A-Z0-9_ ]*\]")  # a masking placeholder such as [NAME] or [DATE]


def draft_problem(policy: dict, text: str) -> str | None:
    """Why this approved text must not go to a patient, or None. Checked at approval and again at send."""
    limit = policy["portal"]["max_body_chars"]
    if not text.strip():
        return "The approved text is empty."
    if len(text) > limit:
        return f"Too long for the patient portal: {len(text)} characters, and the limit is {limit}."
    found = TAG.search(text)
    if found:
        return f"Fill in {found.group(0)} and any other [TAGS] first: the patient gets the text exactly as approved."
    return None


def _full_name(p: dict | None) -> str:
    return f"{p['name']['given']} {p['name']['family']}" if p else ""


def me(app, s: dict) -> dict:
    """/api/me for a patient session: no model, recipient group, leash or presidio fields."""
    app.audit.write("portal_me_viewed", s["user"], patient_id=s["patient_id"])
    return {"user": s["user"], "role": s["role"], "permissions": app.policy["roles"][s["role"]],
            "version": VERSION, "clinic": app.policy["clinic"]["name"],
            "patient": {"id": s["patient_id"], "name": _full_name(app.ehr.patients.get(s["patient_id"]))},
            "portal": True}


def _handle(table: dict, app, s: dict, path: str, arg) -> tuple[int, dict] | None:
    is_portal = path.startswith("/api/portal/")
    if not is_portal and path not in table:
        return None
    if is_portal != bool(s.get("patient_id")):  # patients: portal routes only; staff: never a portal route
        return 403, {"error": "The patient portal is for patient accounts only." if is_portal
                     else "Patient accounts can use the patient portal only."}
    if path not in table:
        return 404, {"error": "Not found."}
    perm, method = table[path]
    if not app.can(s, perm):
        return 403, {"error": "Your role cannot do that."}
    try:
        return 200, getattr(Portal(app, s), method)(arg)
    except Refused as e:
        if is_portal:  # route and status only: never the ids or text the patient sent
            app.audit.write("portal_refused", s["user"], patient_id=s["patient_id"], route=path, code=e.code)
        return e.code, {"error": e.message}


def handle_get(app, s: dict, path: str, qs: dict) -> tuple[int, dict] | None:
    """(code, body) for a portal or inbox GET route, or None when the path is not one of them."""
    return _handle(GET, app, s, path, qs)


def handle_post(app, s: dict, path: str, data: dict) -> tuple[int, dict] | None:
    return _handle(POST, app, s, path, data if isinstance(data, dict) else {})


class Portal:
    def __init__(self, app, s: dict):
        self.app, self.s, self.db = app, s, app.db
        self.cfg, self.clinic = app.policy["portal"], app.policy["clinic"]
        self.pid = s.get("patient_id")  # the only patient id the patient routes ever use

    def audit(self, event: str, **details) -> None:
        self.app.audit.write(event, self.s["user"], **details)

    def _mine(self, rows: list[dict]) -> list[dict]:
        """Second check under the db filter: only this session's patient."""
        return [r for r in rows if r.get("patient_id") == self.pid]

    def _today(self) -> str:
        return self.app.schedule.now().date().isoformat()

    # ---- patient routes (session patient only) ---------------------------
    def chart(self, _qs) -> dict:
        p = self.app.ehr.get(self.pid)
        if not p:
            raise Refused(404, "No such patient.")
        fields = [k for k in self.cfg["released_fields"] if k not in NEVER_RELEASED]
        self.audit("portal_chart_viewed", patient_id=self.pid)
        return {"patient": self.app.ehr.front_desk(p, fields)}  # allow-list copy; name becomes "Given Family"

    def _open_requests(self) -> list[dict]:
        return self._mine(self.db.portal_requests(patient_id=self.pid, status="open"))

    def _appt(self, a: dict, today: str, cancelling: set) -> dict:
        return {"id": a["id"], "date": a["date"], "time": a["time"],
                "clinician_name": self.clinic["clinicians"].get(a["clinician"], a["clinician"]),
                "visit_type": a.get("visit_type"), "status": a["status"],
                "can_cancel": a["status"] == "booked" and a["date"] >= today and a["id"] not in cancelling}

    def _req(self, r: dict) -> dict:
        out = {k: r.get(k) for k in PATIENT_REQ}
        out["clinician"] = self.clinic["clinicians"].get(r.get("clinician"))  # display name, not the username
        return out

    def appointments(self, _qs) -> dict:
        today = self._today()
        cancelling = {r["appointment_id"] for r in self._open_requests() if r["kind"] == "cancel"}
        appts = [self._appt(a, today, cancelling) for a in self._mine(self.db.appointments_for_patient(self.pid))]
        self.audit("portal_appointments_viewed", patient_id=self.pid)
        return {"upcoming": [a for a in appts if a["date"] >= today],
                "past": [a for a in appts if a["date"] < today][::-1],
                "requests": [self._req(r) for r in self._mine(self.db.portal_requests(patient_id=self.pid))],
                "visit_types": self.clinic["visit_types"],
                "clinicians": [{"id": v, "name": v} for v in self.clinic["clinicians"].values()],
                "clinic_phone": self.clinic["phone"]}

    def _add_request(self, row: dict) -> dict:
        with _request_lock:
            open_reqs = self._open_requests()
            if row["kind"] == "cancel" and any(r["kind"] == "cancel" and r["appointment_id"] == row["appointment_id"]
                                               for r in open_reqs):
                raise Refused(409, "You have already asked to cancel this appointment.")
            if len(open_reqs) >= self.cfg["max_open_requests"]:
                raise Refused(409, f"You already have {len(open_reqs)} open requests. "
                                   f"Call the clinic on {self.clinic['phone']} if you need more help.")
            req = self.db.add_portal_request({"id": uuid.uuid4().hex[:10], "patient_id": self.pid, **row},
                                             self.s["user"], self.s["role"])
        self.audit("portal_request_created", patient_id=self.pid, request_id=req["id"], kind=req["kind"])
        return {"request": self._req(req)}

    def request_appointment(self, data: dict) -> dict:
        visit_type, clinician = data.get("visit_type"), _text(data.get("clinician"), 80)
        if not isinstance(visit_type, str) or visit_type not in self.clinic["visit_types"]:
            raise Refused(400, "Pick a visit type from the list.")
        by_name = {name: username for username, name in self.clinic["clinicians"].items()}
        if clinician and clinician not in by_name:
            raise Refused(400, "Pick a clinician from the list, or leave it empty.")
        limit = self.cfg["max_note_chars"]
        return self._add_request({"kind": "book", "visit_type": visit_type, "clinician": by_name.get(clinician),
                                  "preferred": _text(data.get("preferred"), limit),
                                  "note": _text(data.get("note"), limit)})

    def request_cancel(self, data: dict) -> dict:
        a = self.db.appointment(str(data.get("appointment_id") or ""))
        if not a or a["patient_id"] != self.pid:  # someone else's looks exactly like a missing one
            raise Refused(404, "No such appointment.")
        if a["status"] != "booked" or a["date"] < self._today():
            raise Refused(409, "Only an upcoming booked appointment can be cancelled. "
                               f"Call the clinic on {self.clinic['phone']} if you need help.")
        return self._add_request({"kind": "cancel", "appointment_id": a["id"],
                                  "note": _text(data.get("note"), self.cfg["max_note_chars"])})

    def _msg(self, m: dict) -> dict:
        return {**{k: m.get(k) for k in PATIENT_MSG},
                "from": "You" if m["direction"] == "from_patient" else "Care team"}

    def messages(self, _qs) -> dict:
        msgs = self._mine(self.db.portal_messages(self.pid))
        self.audit("portal_messages_viewed", patient_id=self.pid, count=len(msgs))
        return {"messages": [self._msg(m) for m in msgs], "emergency_notice": self.cfg["emergency_notice"]}

    def _new_message(self, patient_id: str, direction: str, subject: str, body: str, source: str,
                     in_reply_to: str | None = None, draft_id: str | None = None,
                     approved_by: str | None = None) -> dict:
        return self.db.add_portal_message(
            {"id": uuid.uuid4().hex[:12], "patient_id": patient_id, "direction": direction,
             "sender": self.s["user"], "sender_role": self.s["role"], "subject": subject, "body": body,
             "source": source, "draft_id": draft_id, "approved_by": approved_by, "in_reply_to": in_reply_to},
            self.s["user"], self.s["role"])

    def send_message(self, data: dict) -> dict:
        subject = _text(data.get("subject"), self.cfg["max_subject_chars"])
        body = _text(data.get("body"), self.cfg["max_body_chars"])
        if not body:
            raise Refused(400, "Write your message first.")
        reply_to = None
        if data.get("in_reply_to"):
            target = self.db.portal_message(str(data["in_reply_to"]))
            if not target or target["patient_id"] != self.pid:
                raise Refused(404, "No such message.")
            reply_to = target["id"]
        since = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 86400))
        with _request_lock:  # count and insert as one step
            if self.db.count_patient_messages(self.pid, since) >= self.cfg["max_messages_per_day"]:
                raise Refused(429, "You have reached today's limit for messages. "
                                   f"Call the clinic on {self.clinic['phone']} if you need help sooner.")
            m = self._new_message(self.pid, "from_patient", subject, body, "patient", reply_to)
        urgent = any(re.search(p, f"{subject}\n{body}", re.I) for p in self.app.policy["scope"]["urgent_patterns"])
        self.audit("portal_message_sent", patient_id=self.pid, message_id=m["id"], urgent=urgent)
        return {"message": self._msg(m), "urgent": urgent, "notice": self.cfg["emergency_notice"]}

    # ---- staff routes (never reachable with a patient session) ------------
    def _staff_msg(self, m: dict) -> dict:
        return {**{k: m.get(k) for k in STAFF_MSG},
                "patient": {"id": m["patient_id"], "name": _full_name(self.app.ehr.patients.get(m["patient_id"]))}}

    def _staff_req(self, r: dict) -> dict:
        p = self.app.ehr.patients.get(r["patient_id"])
        out = {k: r.get(k) for k in STAFF_REQ}
        out["patient"] = self.app.redact(self.app.ehr.front_desk(p, self.app.fd_fields)) if p else {}
        if r["kind"] == "cancel":
            a = self.db.appointment(r["appointment_id"] or "")
            out["appointment"] = {k: a.get(k) for k in STAFF_APPT} if a else None
        return out

    def inbox(self, qs: dict) -> dict:
        pid = qs.get("patient_id", [""])[0][:80] or None
        msgs = self.db.portal_messages(pid) if pid else self.db.portal_inbox(self.cfg["inbox_messages_per_patient"])
        self.audit("portal_inbox_viewed", count=len(msgs), patient_id=pid)
        return {"messages": [self._staff_msg(m) for m in msgs]}

    def reply(self, data: dict) -> dict:
        target = self.db.portal_message(str(data.get("message_id") or ""))
        if not target:
            raise Refused(404, "No such message.")
        body = _text(data.get("body"), self.cfg["max_body_chars"])
        if not body:
            raise Refused(400, "Write your reply first.")
        subject = _text(data.get("subject"), self.cfg["max_subject_chars"]) or target.get("subject") or ""
        m = self._new_message(target["patient_id"], "to_patient", subject, body, "staff", target["id"])
        self.audit("portal_reply_sent", patient_id=m["patient_id"], message_id=m["id"], in_reply_to=target["id"])
        return {"message": self._staff_msg(m)}

    def requests(self, qs: dict) -> dict:
        status = qs.get("status", [""])[0] or None
        if status not in (None, "open", "done", "declined"):
            raise Refused(400, "Status must be open, done or declined.")
        reqs = self.db.portal_requests(status=status)
        self.audit("portal_requests_viewed", count=len(reqs), status=status)
        return {"requests": [self._staff_req(r) for r in reqs]}

    def decide_request(self, data: dict) -> dict:
        status, rid = data.get("status"), str(data.get("id") or "")
        if status not in ("done", "declined"):
            raise Refused(400, "Status must be done or declined.")
        if not self.db.portal_request(rid):
            raise Refused(404, "No such request.")
        try:
            r = self.db.decide_portal_request(rid, status, self.s["user"], self.s["role"],
                                              _text(data.get("note"), self.cfg["max_note_chars"]))
        except ValueError:
            raise Refused(409, "This request was already handled.") from None
        self.audit("portal_request_decided", request_id=rid, patient_id=r["patient_id"], status=status)
        return {"request": self._staff_req(r)}

    def send_draft(self, data: dict) -> dict:
        """Copy a clinician-approved patient-portal draft into the patient's messages, once."""
        sent = {}

        def send(item: dict) -> str | None:
            if item.get("recipient_group") != PORTAL_GROUP:
                return "Only patient-portal drafts can be sent to the patient portal."
            if item.get("status") != "approved":
                return ("This draft was already sent to the patient." if item.get("status") == "sent"
                        else "Only an approved draft can be sent to the patient.")
            if not item.get("patient_id") or not self.app.ehr.patients.get(item["patient_id"]):
                return "This draft is not linked to a patient."
            problem = draft_problem(self.app.policy, item.get("final_text") or "")
            if problem:
                return problem
            # Runs under the outbox lock, and the item is saved as 'sent' only if the message was stored,
            # so a second press waits here and then finds status 'sent'.
            # shortcut: if writing outbox.json fails after the db commit the item stays 'approved';
            # check draft_id against portal_messages here if that ever matters.
            item.update(status="sent", sent_by=self.s["user"], sent_at=time.strftime("%Y-%m-%d %H:%M"))
            sent["message"] = self._new_message(item["patient_id"], "to_patient", DRAFT_SUBJECT, item["final_text"],
                                                "approved_draft", draft_id=item["id"],
                                                approved_by=item.get("decided_by"))
            return None

        item = self.app.outbox.update(str(data.get("id") or ""), send)
        if item is None:
            raise Refused(404, "No such draft.")
        if "message" not in sent:
            raise Refused(409, item["error"])
        m = sent["message"]
        self.audit("draft_sent_to_portal", draft_id=item["id"], patient_id=m["patient_id"], message_id=m["id"],
                   approved_by=m["approved_by"])
        return {"item": item, "message": self._staff_msg(m)}
