"""Contract tests for the patient portal (handoff/PATIENT_PORTAL_PLAN.md, section 2).

Written from the contract, not from the implementation.  Run:
    MOCK_LLM=1 python -m unittest tests.test_portal -v
"""
import http.cookiejar
import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import uuid
from datetime import timedelta
from http.server import ThreadingHTTPServer
from pathlib import Path

os.environ["MOCK_LLM"] = "1"
from app.server import App, make_handler  # noqa: E402

PW = "correct horse battery"
A, B, C = "syn-001", "syn-002", "syn-003"  # pt_a, pt_b, pt_c (pt_c is only used for the open-request limit)
CONFINED = "Patient accounts can use the patient portal only."

PORTAL_GETS = ["/api/portal/chart", "/api/portal/appointments", "/api/portal/messages"]
PORTAL_POSTS = {
    "/api/portal/appointments/request": {"visit_type": "Follow-up", "preferred": "Mornings", "note": "x"},
    "/api/portal/appointments/cancel": {"appointment_id": "nope"},
    "/api/portal/messages": {"subject": "Hello", "body": "A question about my tablets."},
}
NEW_STAFF_GETS = ["/api/inbox", "/api/inbox/requests"]
NEW_STAFF_POSTS = {
    "/api/inbox/reply": {"message_id": "nope", "body": "hi"},
    "/api/inbox/requests/decide": {"id": "nope", "status": "done", "note": "x"},
    "/api/outbox/send": {"id": "nope"},
}
STAFF_GETS = [
    "/api/reviews", "/api/db/status", "/api/patients", "/api/patients?q=Lena", "/api/patients/syn-002",
    "/api/patients/syn-002/history", "/api/patients/syn-002/similar", "/api/chart/options", "/api/chart/recent",
    "/api/schedule", "/api/calendar", "/api/schedule/slots", "/api/schedule/slots?date=2026-11-24&clinician=dr_lee",
    "/api/frontdesk/patients", "/api/frontdesk/patients?q=Lena", "/api/outbox", "/api/conversations",
    "/api/conversations?patient_id=syn-002", "/api/network", "/api/audit", "/api/inbox?patient_id=syn-002",
    "/api/reviewer", "/api/actions", "/api/actions/nope",  # added on main in 2.12 and 2.13
] + NEW_STAFF_GETS
STAFF_POSTS = {
    "/api/chat": {"message": "What needs attention?", "patient_id": B},
    "/api/reveal": {"patient_id": B, "pin": "1234"},
    "/api/patients/new": {"given": "Juniper", "family": "Okafor", "birthDate": "1984-03-09", "pin": "1234"},
    "/api/patients/syn-002/entry": {"pin": "1234", "kind": "note", "type": "Visit note", "text": "hello there"},
    "/api/frontdesk/ask": {"message": "Who is next?"},
    "/api/schedule/book": {"patient_id": B, "date": "2026-11-24", "time": "09:00", "clinician": "dr_lee",
                           "visit_type": "Follow-up"},
    "/api/schedule/status": {"id": "nope", "expected": "booked", "to": "cancelled", "reason": "Patient asked"},
    "/api/schedule/reminder": {"id": "nope", "action": "prepare"},
    "/api/chat/clear": {},
    "/api/reviews/decide": {"id": "nope", "action": "dismiss"},
    "/api/leash/search": {"q": "Lena"},
    "/api/leash/open": {"patient_id": "pt-0001", "view": "full"},
    "/api/outbox/draft": {"recipient_group": "patient-portal", "instructions": "Results normal.", "patient_id": B},
    "/api/outbox/decide": {"id": "nope", "decision": "approve"},
    "/api/reviewer": {"enabled": False},  # 2.12: the reviewer demo switch
    "/api/actions/propose": {"text": "Cancel syn-002's appointment tomorrow"},  # 2.13: assistant actions
    "/api/actions/nope/approve": {"pin": "1234"},
    **NEW_STAFF_POSTS,
}

APPT_KEYS = {"id", "date", "time", "clinician_name", "visit_type", "status", "can_cancel"}
REQ_KEYS = {"id", "kind", "appointment_id", "visit_type", "clinician", "preferred", "note", "status", "created_at",
            "handled_at", "staff_note"}
MSG_KEYS = {"id", "at", "direction", "subject", "body", "from", "in_reply_to"}
MSG_STAFF_ONLY = {"sender", "sender_role", "source", "draft_id", "approved_by", "patient_id", "patient"}


def mark(tag):
    """A unique, harmless string to look for (or to prove absent) later."""
    return f"{tag}-{uuid.uuid4().hex[:8]}"


class Client:
    def __init__(self, base):
        self.base = base
        self.op = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                              urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def call(self, path, body=None):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(self.base + path, data=data, headers={"Content-Type": "application/json"})
        try:
            with self.op.open(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())


class PortalContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.app = App(data_dir=cls.tmp)
        cls.app.policy["tiers"]["green_sample_rate"] = 0
        cls.app.policy["server"]["max_requests_per_minute"] = 100000
        cls.app.policy["communication"]["approver_must_differ_from_drafter"] = False  # dr_lee drafts and approves
        cls.app.policy["portal"]["max_messages_per_day"] = 100000  # the cap has its own test (PortalReviewFixes)
        for name, role in [("dr_lee", "clinician"), ("nurse_kim", "nurse"), ("desk_sam", "receptionist"),
                           ("lead_ana", "clinical_lead"), ("auditor_ray", "auditor")]:
            cls.app.users.add(name, PW, role)
        for name, pid in [("pt_a", A), ("pt_b", B), ("pt_c", C)]:
            cls.app.users.add(name, PW, "patient", patient_id=pid)
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(cls.app))
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.httpd.server_port}"
        cls.clients, cls.appts = {}, {}

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    # ---- helpers ----------------------------------------------------------
    @classmethod
    def c(cls, user):
        """One logged-in client per user, made on first use."""
        if user not in cls.clients:
            client = Client(cls.base)
            st, r = client.call("/api/login", {"username": user, "password": PW})
            assert st == 200, f"login as {user} failed: {st} {r}"
            cls.clients[user] = client
        return cls.clients[user]

    def ok(self, resp, code=200):
        self.assertEqual(resp[0], code, resp[1])
        return resp[1]

    @classmethod
    def booked_appt(cls, pid):
        """Id of one future booked appointment for the patient, booked through the front desk API."""
        if pid not in cls.appts:
            desk, today = cls.c("desk_sam"), cls.app.schedule.now().date()
            for off in range(2, 14):
                day = (today + timedelta(days=off)).isoformat()
                st, slots = desk.call(f"/api/schedule/slots?date={day}&clinician=dr_lee")
                if st != 200 or not slots:
                    continue
                st, r = desk.call("/api/schedule/book", {"patient_id": pid, "date": day, "time": slots[0],
                                                         "clinician": "dr_lee", "visit_type": "Follow-up"})
                if st == 200:  # 409 = the patient already has one that day, or the clinic is closed: try the next
                    cls.appts[pid] = r["id"]
                    break
            else:
                raise AssertionError(f"could not book an appointment for {pid}")
        return cls.appts[pid]

    def appt_status(self, pid, appt_id):
        return next(a["status"] for a in self.app.db.appointments_for_patient(pid) if a["id"] == appt_id)

    def send_msg(self, user, body, **extra):
        return self.ok(self.c(user).call("/api/portal/messages", {"subject": "Question", "body": body, **extra}))

    def messages(self, user):
        return self.ok(self.c(user).call("/api/portal/messages"))["messages"]

    def appointments(self, user):
        return self.ok(self.c(user).call("/api/portal/appointments"))

    def inbox(self, user="dr_lee"):
        return self.ok(self.c(user).call("/api/inbox"))["messages"]

    def desk_requests(self):
        return self.ok(self.c("desk_sam").call("/api/inbox/requests"))["requests"]

    def draft(self, **extra):
        body = {"recipient_group": "patient-portal", "instructions": "Tell the patient their results were normal.",
                "patient_id": A, **extra}
        r = self.ok(self.c("dr_lee").call("/api/outbox/draft", body))
        self.assertIn("item", r, r)
        return r["item"]

    def decide(self, item, decision, final_text=None, user="dr_lee"):
        return self.c(user).call("/api/outbox/decide", {"id": item["id"], "decision": decision,
                                                        "final_text": final_text})

    def send(self, item, user="dr_lee"):
        return self.c(user).call("/api/outbox/send", {"id": item["id"]})

    def audit_events(self, event, user=None):
        rows = [json.loads(l) for l in (self.tmp / "audit.jsonl").read_text().splitlines() if l.strip()]
        return [e for e in rows if e["event"] == event and (user is None or e["user"] == user)]

    def full_name(self, pid):
        n = self.app.ehr.get(pid)["name"]
        return f"{n['given']} {n['family']}"

    # ---- 1. no session ----------------------------------------------------
    def test_unauthenticated_portal_routes_are_401(self):
        anon = Client(self.base)
        for path in PORTAL_GETS + NEW_STAFF_GETS:
            with self.subTest(method="GET", path=path):
                self.assertEqual(anon.call(path)[0], 401)
        for path, body in {**PORTAL_POSTS, **NEW_STAFF_POSTS}.items():
            with self.subTest(method="POST", path=path):
                self.assertEqual(anon.call(path, body)[0], 401)

    # ---- 2. patient A cannot reach patient B ------------------------------
    def _b_data(self):
        """B's own data, made once: an appointment, a message, a staff reply and a request."""
        cls = type(self)
        if not hasattr(cls, "b"):
            body, reply, note = mark("BMSG"), mark("BREPLY"), mark("BNOTE")
            msg = self.send_msg("pt_b", body)["message"]
            rep = self.ok(self.c("dr_lee").call("/api/inbox/reply", {"message_id": msg["id"], "body": reply}))
            req = self.ok(self.c("pt_b").call("/api/portal/appointments/request",
                                              {"visit_type": "Follow-up", "note": note}))["request"]
            cls.b = {"appt": self.booked_appt(B), "msg": msg["id"], "reply": rep["message"]["id"], "req": req["id"],
                     "strings": [body, reply, note]}
        return cls.b

    def assert_nothing_of_b(self, payload):
        b, blob = self._b_data(), json.dumps(payload)
        for secret in [B, self.full_name(B), b["appt"], b["msg"], b["reply"], b["req"], *b["strings"]]:
            self.assertNotIn(secret, blob)

    def test_cross_patient_chart_is_own_record_only(self):
        r = self.ok(self.c("pt_a").call("/api/portal/chart"))
        self.assertEqual(r["patient"]["id"], A)
        self.assertEqual(r["patient"]["name"], self.full_name(A))
        self.assert_nothing_of_b(r)

    def test_cross_patient_appointments_are_own_only(self):
        mine = self.booked_appt(A)
        r = self.appointments("pt_a")
        self.assertIn(mine, [a["id"] for a in r["upcoming"]])
        self.assert_nothing_of_b(r)

    def test_cross_patient_messages_are_own_only(self):
        body = mark("AMSG")
        self.send_msg("pt_a", body)
        msgs = self.messages("pt_a")
        self.assertIn(body, [m["body"] for m in msgs])
        self.assert_nothing_of_b(msgs)
        self.assertNotIn(body, json.dumps(self.messages("pt_b")))

    def test_cross_patient_cancel_of_other_patients_appointment_is_refused(self):
        b = self._b_data()
        st, r = self.c("pt_a").call("/api/portal/appointments/cancel", {"appointment_id": b["appt"]})
        self.assertIn(st, (404, 403), r)
        theirs = self.appointments("pt_b")
        self.assertFalse([q for q in theirs["requests"] if q["kind"] == "cancel"])  # no request was created
        self.assertTrue(next(a for a in theirs["upcoming"] if a["id"] == b["appt"])["can_cancel"])
        self.assertEqual(self.appt_status(B, b["appt"]), "booked")

    def test_cross_patient_reply_to_other_patients_message_is_refused(self):
        b, body = self._b_data(), mark("AREPLY")
        for target in (b["msg"], b["reply"]):
            st, r = self.c("pt_a").call("/api/portal/messages", {"subject": "Re", "body": body, "in_reply_to": target})
            self.assertIn(st, (404, 403), r)
        for user in ("pt_a", "pt_b"):
            self.assertNotIn(body, json.dumps(self.messages(user)))
        self.assertNotIn(body, json.dumps(self.inbox()))

    def test_cross_patient_smuggled_patient_id_in_query_is_ignored(self):
        self._b_data()
        a = self.c("pt_a")
        chart = self.ok(a.call(f"/api/portal/chart?patient_id={B}"))
        self.assertEqual(chart["patient"]["id"], A)
        self.assert_nothing_of_b(chart)
        plain, smuggled = self.appointments("pt_a"), self.ok(a.call(f"/api/portal/appointments?patient_id={B}"))
        ids = lambda r: [x["id"] for k in ("upcoming", "past", "requests") for x in r[k]]
        self.assertEqual(ids(smuggled), ids(plain))
        self.assert_nothing_of_b(smuggled)
        msgs = self.ok(a.call(f"/api/portal/messages?patient_id={B}"))
        self.assertEqual([m["id"] for m in msgs["messages"]], [m["id"] for m in self.messages("pt_a")])
        self.assert_nothing_of_b(msgs)

    def test_cross_patient_smuggled_patient_id_in_message_body_is_stored_under_sender(self):
        self._b_data()
        body = mark("SMUGGLE")
        msg = self.ok(self.c("pt_a").call("/api/portal/messages",
                                          {"subject": "Hi", "body": body, "patient_id": B}))["message"]
        stored = next(m for m in self.inbox() if m["id"] == msg["id"])
        self.assertEqual((stored["patient_id"], stored["patient"]["id"], stored["sender"]), (A, A, "pt_a"))
        self.assertIn(body, [m["body"] for m in self.messages("pt_a")])
        self.assertNotIn(body, json.dumps(self.messages("pt_b")))

    def test_cross_patient_smuggled_patient_id_in_request_bodies_is_ignored(self):
        b, note = self._b_data(), mark("SMUGREQ")
        req = self.ok(self.c("pt_a").call("/api/portal/appointments/request",
                                          {"visit_type": "Follow-up", "note": note, "patient_id": B}))["request"]
        stored = next(q for q in self.desk_requests() if q["id"] == req["id"])
        self.assertEqual((stored["patient_id"], stored["patient"]["id"]), (A, A))
        self.assertIn(req["id"], [q["id"] for q in self.appointments("pt_a")["requests"]])
        self.assertNotIn(req["id"], [q["id"] for q in self.appointments("pt_b")["requests"]])
        st, r = self.c("pt_a").call("/api/portal/appointments/cancel", {"appointment_id": b["appt"], "patient_id": B})
        self.assertIn(st, (404, 403), r)
        self.assertFalse([q for q in self.appointments("pt_b")["requests"] if q["kind"] == "cancel"])

    # ---- 3. confinement, both ways ----------------------------------------
    def test_patient_session_is_refused_on_every_staff_route(self):
        a, appt = self.c("pt_a"), self.booked_appt(B)
        posts = {**STAFF_POSTS, "/api/schedule/status": {**STAFF_POSTS["/api/schedule/status"], "id": appt}}
        for path in STAFF_GETS:
            with self.subTest(method="GET", path=path):
                self.assertEqual(a.call(path), (403, {"error": CONFINED}))
        for path, body in posts.items():
            with self.subTest(method="POST", path=path):
                self.assertEqual(a.call(path, body), (403, {"error": CONFINED}))
        self.assertEqual(self.appt_status(B, appt), "booked")
        self.assertEqual(a.call("/api/me")[0], 200)  # still signed in: the 403s were confinement, not a lost session

    def test_staff_session_is_refused_on_every_portal_route(self):
        for user in ("dr_lee", "nurse_kim", "desk_sam", "lead_ana", "auditor_ray"):
            for path in PORTAL_GETS:
                with self.subTest(user=user, method="GET", path=path):
                    self.assertEqual(self.c(user).call(path)[0], 403)
            for path, body in PORTAL_POSTS.items():
                with self.subTest(user=user, method="POST", path=path):
                    self.assertEqual(self.c(user).call(path, body)[0], 403)

    def test_patient_can_still_log_out(self):
        client = Client(self.base)
        self.ok(client.call("/api/login", {"username": "pt_b", "password": PW}))
        self.ok(client.call("/api/logout", {}))
        self.assertEqual(client.call("/api/portal/chart")[0], 401)

    # ---- 4. chart ---------------------------------------------------------
    def test_chart_returns_only_released_fields(self):
        released = set(self.app.policy["portal"]["released_fields"])
        for user, pid in (("pt_a", A), ("pt_b", B)):
            with self.subTest(user=user):
                r = self.ok(self.c(user).call("/api/portal/chart"))
                self.assertEqual(set(r), {"patient"})
                self.assertTrue(r["patient"])
                self.assertLessEqual(set(r["patient"]), released)
                for key in ("notes", "attention", "mrn", "insurance", "scenario", "phone", "address"):
                    self.assertNotIn(key, r["patient"])

    def test_chart_response_has_no_mrn_or_note_text(self):
        for user, pid in (("pt_a", A), ("pt_b", B)):
            with self.subTest(user=user):
                real, blob = self.app.ehr.get(pid), json.dumps(self.ok(self.c(user).call("/api/portal/chart")))
                self.assertTrue(real["notes"])  # otherwise the note check below proves nothing
                self.assertNotIn(real["mrn"], blob)
                self.assertNotIn(real["insurance"]["member_id"], blob)
                for note in real["notes"]:
                    self.assertNotIn(note["text"], blob)
                    self.assertNotIn(note["text"][:30], blob)

    def test_chart_shows_released_clinical_fields(self):
        real, p = self.app.ehr.get(A), self.ok(self.c("pt_a").call("/api/portal/chart"))["patient"]
        self.assertEqual(p["name"], self.full_name(A))  # a plain "Given Family" string
        for key in ("conditions", "medications", "allergies", "observations", "birthDate"):
            self.assertEqual(p[key], real[key])

    # ---- 4b. appointments view --------------------------------------------
    def test_appointments_payload_shape(self):
        mine = self.booked_appt(A)
        r = self.appointments("pt_a")
        for key in ("upcoming", "past", "requests", "visit_types", "clinicians", "clinic_phone"):
            self.assertIn(key, r)
        self.assertEqual(r["visit_types"], self.app.policy["clinic"]["visit_types"])
        self.assertIn({"id": "Dr Lee", "name": "Dr Lee"}, r["clinicians"])  # display names, never usernames
        self.assertEqual(r["clinic_phone"], self.app.policy["clinic"]["phone"])
        for a in r["upcoming"] + r["past"]:
            self.assertLessEqual(set(a), APPT_KEYS)  # no patient_id, history or reminder internals
        appt = next(a for a in r["upcoming"] if a["id"] == mine)
        self.assertEqual((appt["status"], appt["clinician_name"], appt["visit_type"]), ("booked", "Dr Lee", "Follow-up"))

    # ---- 5. messages ------------------------------------------------------
    def test_patient_message_reaches_staff_inbox(self):
        body = mark("TOSTAFF")
        msg = self.send_msg("pt_a", body)["message"]
        self.assertEqual((msg["from"], msg["direction"], msg["body"]), ("You", "from_patient", body))
        for user in ("dr_lee", "nurse_kim", "lead_ana"):
            with self.subTest(user=user):
                got = next(m for m in self.inbox(user) if m["id"] == msg["id"])
                self.assertEqual((got["patient_id"], got["body"], got["direction"], got["source"]),
                                 (A, body, "from_patient", "patient"))
                self.assertEqual(got["patient"], {"id": A, "name": self.full_name(A)})

    def test_staff_inbox_filter_by_patient(self):
        body = mark("FILTER")
        self.send_msg("pt_a", body)
        self.send_msg("pt_b", mark("FILTERB"))
        got = self.ok(self.c("dr_lee").call(f"/api/inbox?patient_id={A}"))["messages"]
        self.assertIn(body, [m["body"] for m in got])
        self.assertEqual({m["patient_id"] for m in got}, {A})

    def test_staff_reply_reaches_that_patient_only(self):
        body, reply = mark("ASK"), mark("ANSWER")
        msg = self.send_msg("pt_a", body)["message"]
        sent = self.ok(self.c("dr_lee").call("/api/inbox/reply", {"message_id": msg["id"], "body": reply}))["message"]
        self.assertEqual((sent["patient_id"], sent["direction"], sent["source"], sent["in_reply_to"], sent["sender"]),
                         (A, "to_patient", "staff", msg["id"], "dr_lee"))
        got = next(m for m in self.messages("pt_a") if m["id"] == sent["id"])
        self.assertEqual((got["body"], got["from"], got["direction"], got["in_reply_to"]),
                         (reply, "Care team", "to_patient", msg["id"]))
        self.assertNotIn(reply, json.dumps(self.messages("pt_b")))
        # The patient can answer inside their own thread.
        again = self.send_msg("pt_a", mark("THANKS"), in_reply_to=sent["id"])["message"]
        self.assertEqual(again["in_reply_to"], sent["id"])

    def test_staff_reply_to_unknown_message_is_404(self):
        st, r = self.c("dr_lee").call("/api/inbox/reply", {"message_id": "nope", "body": "hi"})
        self.assertEqual(st, 404, r)

    def test_patient_message_objects_hide_staff_internals(self):
        msg = self.send_msg("pt_a", mark("HIDE"))
        self.ok(self.c("dr_lee").call("/api/inbox/reply", {"message_id": msg["message"]["id"], "body": mark("R")}))
        msgs = self.messages("pt_a")
        for m in msgs + [msg["message"]]:
            self.assertLessEqual(set(m), MSG_KEYS)
            self.assertFalse(set(m) & MSG_STAFF_ONLY)
            self.assertIn(m["from"], ("You", "Care team"))
        blob = json.dumps(msgs)
        for name in ("dr_lee", "nurse_kim", "lead_ana", "desk_sam"):
            self.assertNotIn(name, blob)

    def test_receptionist_and_auditor_cannot_read_the_inbox(self):
        for user in ("desk_sam", "auditor_ray"):
            with self.subTest(user=user):
                self.assertEqual(self.c(user).call("/api/inbox")[0], 403)
                self.assertEqual(self.c(user).call("/api/inbox/reply", {"message_id": "nope", "body": "hi"})[0], 403)

    def test_message_body_is_required(self):
        n = len(self.messages("pt_a"))
        for body in ("", "   "):
            st, r = self.c("pt_a").call("/api/portal/messages", {"subject": "Empty", "body": body})
            self.assertEqual(st, 400, r)
        self.assertEqual(len(self.messages("pt_a")), n)

    def test_message_text_is_cut_to_policy_limits(self):
        lim = self.app.policy["portal"]
        msg = self.ok(self.c("pt_b").call("/api/portal/messages", {"subject": "s" * 500, "body": "b" * 5000}))["message"]
        self.assertEqual(len(msg["subject"]), lim["max_subject_chars"])
        self.assertEqual(len(msg["body"]), lim["max_body_chars"])

    def test_messages_payload_carries_emergency_notice(self):
        r = self.ok(self.c("pt_a").call("/api/portal/messages"))
        self.assertEqual(r["emergency_notice"], self.app.policy["portal"]["emergency_notice"])

    # ---- 6. clinician approval gate ---------------------------------------
    def test_gate_draft_reaches_patient_only_after_approval_and_send(self):
        final = mark("Your results were normal. APPROVED")
        n_a, n_b = len(self.messages("pt_a")), len(self.messages("pt_b"))
        item = self.draft()
        self.assertEqual((item["status"], item["patient_id"]), ("awaiting_approval", A))
        self.assertEqual(len(self.messages("pt_a")), n_a)                 # drafted: invisible
        st, r = self.send(item)
        self.assertEqual(st, 409, r)                                      # cannot send before approval
        self.assertEqual(len(self.messages("pt_a")), n_a)
        self.assertEqual(self.decide(item, "approve", final, user="nurse_kim")[0], 403)  # no approve_message
        self.assertEqual(self.send(item)[0], 409)
        r = self.ok(self.decide(item, "approve", final))
        self.assertEqual(r["item"]["status"], "approved")
        self.assertEqual(len(self.messages("pt_a")), n_a)                 # approved: still invisible
        self.assertEqual(self.send(item, user="desk_sam")[0], 403)        # no send_portal
        self.assertEqual(len(self.messages("pt_a")), n_a)
        r = self.ok(self.send(item))
        self.assertEqual((r["item"]["status"], r["item"]["sent_by"]), ("sent", "dr_lee"))
        self.assertEqual((r["message"]["patient_id"], r["message"]["source"], r["message"]["draft_id"],
                          r["message"]["approved_by"], r["message"]["body"], r["message"]["direction"]),
                         (A, "approved_draft", item["id"], "dr_lee", final, "to_patient"))
        mine = self.messages("pt_a")
        self.assertEqual(len(mine), n_a + 1)
        got = next(m for m in mine if m["id"] == r["message"]["id"])
        self.assertEqual((got["body"], got["from"]), (final, "Care team"))
        self.assertLessEqual(set(got), MSG_KEYS)
        self.assertNotIn(item["id"], json.dumps(mine))
        theirs = self.messages("pt_b")
        self.assertEqual(len(theirs), n_b)
        self.assertNotIn(final, json.dumps(theirs))

    def test_gate_sending_twice_delivers_one_copy(self):
        final = mark("ONCE")
        item = self.draft()
        self.ok(self.decide(item, "approve", final))
        self.ok(self.send(item))
        st, r = self.send(item)
        self.assertEqual(st, 409, r)
        self.assertEqual(self.send(item, user="nurse_kim")[0], 409)
        self.assertEqual([m["body"] for m in self.messages("pt_a")].count(final), 1)

    def test_gate_rejected_draft_cannot_be_sent(self):
        n = len(self.messages("pt_a"))
        item = self.draft()
        r = self.ok(self.decide(item, "reject"))
        self.assertEqual(r["item"]["status"], "rejected")
        st, r = self.send(item)
        self.assertEqual(st, 409, r)
        self.assertEqual(len(self.messages("pt_a")), n)

    def test_gate_send_of_unknown_draft_is_404(self):
        st, r = self.c("dr_lee").call("/api/outbox/send", {"id": "nope"})
        self.assertEqual(st, 404, r)

    def test_gate_only_patient_portal_drafts_can_be_sent(self):
        r = self.ok(self.c("dr_lee").call("/api/outbox/draft", {"recipient_group": "care-team",
                                                                "instructions": "Remind the team about the audit."}))
        self.ok(self.decide(r["item"], "approve", "Reminder."))
        st, r = self.send(r["item"])
        self.assertEqual(st, 409, r)

    def test_gate_patient_portal_draft_needs_a_known_patient(self):
        before = len(self.ok(self.c("dr_lee").call("/api/outbox")))
        base = {"recipient_group": "patient-portal", "instructions": "Tell the patient their results were normal."}
        for extra in ({}, {"patient_id": ""}, {"patient_id": "syn-999"}):
            with self.subTest(extra=extra):
                st, r = self.c("dr_lee").call("/api/outbox/draft", {**base, **extra})
                self.assertEqual(st, 400, r)
        self.assertEqual(len(self.ok(self.c("dr_lee").call("/api/outbox"))), before)

    def test_gate_patient_id_is_not_put_in_the_model_prompt(self):
        from app import llm
        seen, real = [], llm.chat
        llm.chat = lambda policy, messages, *a, **k: seen.append(json.dumps([messages, a, k])) or "Your results are normal."
        try:
            self.ok(self.c("dr_lee").call("/api/outbox/draft", {
                "recipient_group": "patient-portal", "instructions": "Tell the patient their results were normal.",
                "patient_id": A}))
        finally:
            llm.chat = real
        self.assertTrue(seen)
        for prompt in seen:
            self.assertNotIn(A, prompt)
            self.assertNotIn(self.app.ehr.get(A)["name"]["family"], prompt)

    def test_portal_routes_never_call_the_model(self):
        from app import llm
        seen, real = [], llm.chat
        llm.chat = lambda *a, **k: seen.append(1) or "x"
        try:
            for path in PORTAL_GETS:
                self.ok(self.c("pt_b").call(path))
            self.send_msg("pt_b", "Can I take my tablets with food?")
            self.ok(self.c("pt_b").call("/api/portal/appointments/request", {"visit_type": "Follow-up"}))
        finally:
            llm.chat = real
        self.assertEqual(seen, [])

    # ---- 7. appointment requests ------------------------------------------
    def test_booking_request_goes_to_front_desk_and_back(self):
        note, body, staff_note = mark("REQNOTE"), mark("PRIVATEBODY"), mark("Booked Tuesday 9am")
        self.send_msg("pt_a", body)
        req = self.ok(self.c("pt_a").call("/api/portal/appointments/request", {
            "visit_type": "Follow-up", "clinician": "Dr Lee", "preferred": "Weekday mornings", "note": note}))["request"]
        self.assertEqual((req["kind"], req["status"], req["visit_type"], req["clinician"], req["note"]),
                         ("book", "open", "Follow-up", "Dr Lee", note))
        self.assertNotIn("handled_by", req)
        self.assertEqual(self.c("dr_lee").call("/api/inbox/requests")[0], 403)   # clinician has no portal_requests
        self.assertEqual(self.c("dr_lee").call("/api/inbox/requests/decide",
                                               {"id": req["id"], "status": "done"})[0], 403)
        queue = self.desk_requests()
        seen = next(q for q in queue if q["id"] == req["id"])
        self.assertEqual((seen["patient_id"], seen["status"], seen["note"], seen["patient"]["id"], seen["clinician"]),
                         (A, "open", note, A, "dr_lee"))  # reception gets the id it books with
        self.assertLessEqual(set(seen["patient"]), set(self.app.policy["frontdesk"]["allowed_fields"]) | {"locked"})
        blob, real = json.dumps(queue), self.app.ehr.get(A)
        for secret in [body, real["mrn"]] + real["conditions"] + real["medications"]:
            self.assertNotIn(secret, blob)                                        # no message bodies, nothing clinical
        self.assertIn(req["id"], [q["id"] for q in self.ok(
            self.c("desk_sam").call("/api/inbox/requests?status=open"))["requests"]])
        done = self.ok(self.c("desk_sam").call("/api/inbox/requests/decide",
                                               {"id": req["id"], "status": "done", "note": staff_note}))["request"]
        self.assertEqual((done["status"], done["handled_by"], done["staff_note"]), ("done", "desk_sam", staff_note))
        mine = next(q for q in self.appointments("pt_a")["requests"] if q["id"] == req["id"])
        self.assertEqual((mine["status"], mine["staff_note"]), ("done", staff_note))
        self.assertTrue(mine["handled_at"])
        self.assertNotIn(req["id"], [q["id"] for q in self.ok(
            self.c("desk_sam").call("/api/inbox/requests?status=open"))["requests"]])
        st, r = self.c("desk_sam").call("/api/inbox/requests/decide", {"id": req["id"], "status": "declined"})
        self.assertIn(st, (409, 404), r)                                          # decided once only

    def test_cancel_request_is_accepted_once_and_never_changes_the_schedule(self):
        appt, note = self.booked_appt(A), mark("CANCELNOTE")
        self.assertTrue(next(a for a in self.appointments("pt_a")["upcoming"] if a["id"] == appt)["can_cancel"])
        req = self.ok(self.c("pt_a").call("/api/portal/appointments/cancel",
                                          {"appointment_id": appt, "note": note}))["request"]
        self.assertEqual((req["kind"], req["appointment_id"], req["status"]), ("cancel", appt, "open"))
        st, r = self.c("pt_a").call("/api/portal/appointments/cancel", {"appointment_id": appt})
        self.assertEqual(st, 409, r)
        self.assertEqual(self.appt_status(A, appt), "booked")                     # the portal never writes the schedule
        view = self.appointments("pt_a")
        shown = next(a for a in view["upcoming"] if a["id"] == appt)
        self.assertEqual((shown["status"], shown["can_cancel"]), ("booked", False))
        self.assertEqual(len([q for q in view["requests"] if q["appointment_id"] == appt]), 1)
        seen = next(q for q in self.desk_requests() if q["id"] == req["id"])
        self.assertEqual((seen["patient"]["id"], seen["appointment"]["status"], seen["appointment"]["visit_type"]),
                         (A, "booked", "Follow-up"))
        for key in ("date", "time", "clinician"):
            self.assertIn(key, seen["appointment"])

    def test_cancel_of_unknown_appointment_is_404(self):
        st, r = self.c("pt_a").call("/api/portal/appointments/cancel", {"appointment_id": "nope"})
        self.assertEqual(st, 404, r)

    def test_patient_request_objects_have_no_handled_by(self):
        req = self.ok(self.c("pt_b").call("/api/portal/appointments/request", {"visit_type": "Follow-up"}))["request"]
        self.ok(self.c("desk_sam").call("/api/inbox/requests/decide",
                                        {"id": req["id"], "status": "declined", "note": "Please call us."}))
        reqs = self.appointments("pt_b")["requests"]
        self.assertEqual(next(q for q in reqs if q["id"] == req["id"])["status"], "declined")
        for q in reqs + [req]:
            self.assertNotIn("handled_by", q)
            self.assertLessEqual(set(q), REQ_KEYS)
        self.assertNotIn("desk_sam", json.dumps(reqs))

    def test_invalid_visit_type_or_clinician_is_400(self):
        n = len(self.appointments("pt_a")["requests"])
        for body in ({"visit_type": "Surgery"}, {}, {"visit_type": "Follow-up", "clinician": "dr_nobody"}):
            with self.subTest(body=body):
                st, r = self.c("pt_a").call("/api/portal/appointments/request", body)
                self.assertEqual(st, 400, r)
        self.assertEqual(len(self.appointments("pt_a")["requests"]), n)

    def test_decide_request_rejects_bad_status(self):
        req = self.ok(self.c("pt_b").call("/api/portal/appointments/request", {"visit_type": "Follow-up"}))["request"]
        st, r = self.c("desk_sam").call("/api/inbox/requests/decide", {"id": req["id"], "status": "open"})
        self.assertEqual(st, 400, r)
        self.ok(self.c("desk_sam").call("/api/inbox/requests/decide", {"id": req["id"], "status": "declined"}))

    def test_open_request_limit(self):
        # "More than max_open_requests open requests -> 409": the first `limit` are accepted, and by limit + 2
        # the portal must be refusing, whichever way the boundary is read.
        limit = self.app.policy["portal"]["max_open_requests"]
        codes = [self.c("pt_c").call("/api/portal/appointments/request", {"visit_type": "Follow-up"})[0]
                 for _ in range(limit + 2)]
        self.assertEqual(codes[:limit], [200] * limit)
        self.assertEqual(codes[-1], 409)

    # ---- 8. logging -------------------------------------------------------
    def test_portal_reads_are_audited(self):
        for path, event in (("/api/portal/chart", "portal_chart_viewed"),
                            ("/api/portal/appointments", "portal_appointments_viewed"),
                            ("/api/portal/messages", "portal_messages_viewed")):
            with self.subTest(event=event):
                before = len(self.audit_events(event, "pt_a"))
                self.ok(self.c("pt_a").call(path))
                self.assertGreater(len(self.audit_events(event, "pt_a")), before)
        self.assertEqual(self.audit_events("portal_chart_viewed", "pt_a")[-1]["details"]["patient_id"], A)

    def test_portal_writes_are_in_change_log_and_audit(self):
        body, note = mark("LOGBODY"), mark("LOGNOTE")
        before = {e: len(self.audit_events(e, "pt_a")) for e in ("portal_message_sent", "portal_request_created")}
        seq = max([h["seq"] for h in self.app.db.history(A)], default=0)
        self.send_msg("pt_a", body)
        self.ok(self.c("pt_a").call("/api/portal/appointments/request", {"visit_type": "Follow-up", "note": note}))
        new = [h for h in self.app.db.history(A) if h["seq"] > seq]
        self.assertEqual(sorted(h["action"] for h in new), ["portal_message", "portal_request"])
        for h in new:
            self.assertEqual((h["entity"], h["entity_id"], h["by"]), ("patient", A, "pt_a"))
            self.assertNotIn(body, h["summary"])
        for event, n in before.items():
            self.assertGreater(len(self.audit_events(event, "pt_a")), n)
        self.assertNotIn(body, (self.tmp / "audit.jsonl").read_text())           # audit never holds message text

    def test_staff_portal_actions_are_logged(self):
        body, reply = mark("STAFFLOG"), mark("STAFFREPLY")
        msg = self.send_msg("pt_a", body)["message"]
        n = len(self.audit_events("portal_inbox_viewed", "dr_lee"))
        self.inbox()
        self.assertGreater(len(self.audit_events("portal_inbox_viewed", "dr_lee")), n)
        seq = max(h["seq"] for h in self.app.db.history(A))
        self.ok(self.c("dr_lee").call("/api/inbox/reply", {"message_id": msg["id"], "body": reply}))
        new = [h for h in self.app.db.history(A) if h["seq"] > seq]
        self.assertEqual([(h["action"], h["by"]) for h in new], [("portal_message", "dr_lee")])
        self.assertTrue(self.audit_events("portal_reply_sent", "dr_lee"))
        log = (self.tmp / "audit.jsonl").read_text()
        self.assertNotIn(body, log)
        self.assertNotIn(reply, log)

    def test_refused_staff_route_is_audited(self):
        before = len(self.audit_events("portal_staff_route_refused", "pt_a"))
        self.assertEqual(self.c("pt_a").call("/api/reviews")[0], 403)
        self.assertEqual(self.c("pt_a").call("/api/chat", {"message": "hi"})[0], 403)
        new = self.audit_events("portal_staff_route_refused", "pt_a")[before:]
        self.assertEqual([e["details"]["path"] for e in new], ["/api/reviews", "/api/chat"])

    def test_zz_audit_and_db_chains_verify_at_the_end(self):
        # Runs last (unittest sorts by name), after the other tests have written to both logs.
        self.send_msg("pt_a", mark("LAST"))
        self.assertTrue(self.app.audit.verify()["ok"])
        self.assertTrue(self.app.db.verify_chain()[0])

    # ---- 9. accounts and login --------------------------------------------
    def test_unlinked_patient_account_cannot_log_in(self):
        self.app.users.add("pt_ghost", PW, "patient", patient_id="syn-999")
        client = Client(self.base)
        st, r = client.call("/api/login", {"username": "pt_ghost", "password": PW})
        self.assertEqual(st, 401, r)
        self.assertEqual(r, Client(self.base).call("/api/login", {"username": "pt_a", "password": "wrong password!"})[1])
        self.assertEqual(client.call("/api/portal/chart")[0], 401)
        self.assertTrue(self.audit_events("login_refused_unlinked", "pt_ghost"))

    def test_me_for_patient_is_the_portal_shape(self):
        me = self.ok(self.c("pt_a").call("/api/me"))
        self.assertIs(me["portal"], True)
        self.assertEqual(me["patient"], {"id": A, "name": self.full_name(A)})
        self.assertEqual((me["user"], me["role"]), ("pt_a", "patient"))
        self.assertEqual(sorted(me["permissions"]), ["portal_appointments", "portal_chart", "portal_messages"])
        for key in ("model", "recipient_groups", "leash", "presidio"):
            self.assertNotIn(key, me)

    def test_me_for_staff_is_not_a_portal_session(self):
        me = self.ok(self.c("dr_lee").call("/api/me"))
        self.assertFalse(me.get("portal"))
        self.assertNotIn("patient", me)

    def test_patient_account_needs_a_patient_id(self):
        with self.assertRaises(ValueError):
            self.app.users.add("x", PW, "patient")
        with self.assertRaises(ValueError):
            self.app.users.add("y", PW, "nurse", patient_id=A)  # only patient accounts carry a link
        names = [u[0] for u in self.app.users.list()]
        self.assertNotIn("x", names)
        self.assertNotIn("y", names)

    def test_users_patient_id_lookup(self):
        self.assertEqual(self.app.users.patient_id("pt_a"), A)
        self.assertIsNone(self.app.users.patient_id("dr_lee"))
        for row in self.app.users.list():
            self.assertEqual(len(row), 3)  # callers unpack (name, role, active)

    # ---- 10. urgent notice ------------------------------------------------
    def test_urgent_words_return_urgent_notice(self):
        notice = self.app.policy["portal"]["emergency_notice"]
        r = self.send_msg("pt_a", "I have had chest pain since this morning.")
        self.assertIs(r["urgent"], True)
        self.assertTrue(r["notice"])
        self.assertEqual(r["notice"], notice)
        r = self.ok(self.c("pt_a").call("/api/portal/messages", {"subject": "CHEST PAIN", "body": "Please advise."}))
        self.assertIs(r["urgent"], True)  # subject counts, case-insensitive

    def test_ordinary_message_is_not_urgent(self):
        r = self.send_msg("pt_a", "Can I book my flu jab at the next visit?")
        self.assertIs(r["urgent"], False)
        self.assertEqual(r["notice"], self.app.policy["portal"]["emergency_notice"])


class PortalReviewFixes(unittest.TestCase):
    """One test per finding of the 2.8 security review. Own app, so caps can be lowered without side effects."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.app = App(data_dir=cls.tmp)
        cls.app.policy["tiers"]["green_sample_rate"] = 0
        cls.app.policy["server"]["max_requests_per_minute"] = 100000
        cls.app.policy["communication"]["approver_must_differ_from_drafter"] = False
        for name, role in [("dr_lee", "clinician"), ("desk_sam", "receptionist")]:
            cls.app.users.add(name, PW, role)
        for name, pid in [("pt_a", A), ("pt_b", B), ("pt_gone", C)]:
            cls.app.users.add(name, PW, "patient", patient_id=pid)
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(cls.app))
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.httpd.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def login(self, user):
        c = Client(self.base)
        self.assertEqual(c.call("/api/login", {"username": user, "password": PW})[0], 200)
        return c

    def audit(self, event):
        rows = [json.loads(line) for line in (self.tmp / "audit.jsonl").read_text().splitlines() if line.strip()]
        return [r for r in rows if r["event"] == event]

    def draft_for(self, doc, pid):
        st, r = doc.call("/api/outbox/draft", {"recipient_group": "patient-portal",
                                               "instructions": "Results are normal.", "patient_id": pid})
        self.assertEqual(st, 200, r)
        return r["item"]["id"]

    # 1. a live session must not outlive a disabled or re-linked account
    def test_session_ends_when_account_is_disabled_or_relinked(self):
        c = self.login("pt_gone")
        self.assertEqual(c.call("/api/portal/chart")[0], 200)
        self.app.users.add("pt_gone", PW, "patient", patient_id=A)  # admin re-links the account
        self.assertEqual(c.call("/api/portal/chart")[0], 401)       # the old session (for syn-003) is gone
        c = self.login("pt_gone")
        self.assertEqual(c.call("/api/portal/chart")[1]["patient"]["id"], A)
        self.app.users.disable("pt_gone")
        self.assertEqual(c.call("/api/portal/chart")[0], 401)
        self.assertEqual(c.call("/api/portal/messages", {"subject": "x", "body": "still here?"})[0], 401)
        self.assertTrue(self.audit("session_ended_account_changed"))

    # 2. one patient cannot flood the care team or hide other patients' messages
    def test_daily_message_cap_and_fair_inbox(self):
        cfg = self.app.policy["portal"]
        old = cfg["max_messages_per_day"], cfg["inbox_messages_per_patient"]
        quiet, loud, doc = self.login("pt_b"), self.login("pt_a"), self.login("dr_lee")
        quiet_body = mark("QUIET")
        self.assertEqual(quiet.call("/api/portal/messages", {"subject": "s", "body": quiet_body})[0], 200)
        try:
            cfg["inbox_messages_per_patient"] = 2
            cfg["max_messages_per_day"] = self.app.db.count_patient_messages(A, "") + 4
            codes = [loud.call("/api/portal/messages", {"subject": "s", "body": f"flood {i}"})[0] for i in range(6)]
            self.assertEqual(codes, [200, 200, 200, 200, 429, 429])
            inbox = doc.call("/api/inbox")[1]["messages"]
            self.assertIn(quiet_body, [m["body"] for m in inbox])                 # still visible
            self.assertEqual(len([m for m in inbox if m["patient_id"] == A]), 2)  # newest two of the loud patient
            self.assertGreaterEqual(len(doc.call(f"/api/inbox?patient_id={A}")[1]["messages"]), 4)  # filter: all
        finally:
            cfg["max_messages_per_day"], cfg["inbox_messages_per_patient"] = old

    # 3. approved text for a patient: not blank, not over the limit, no unfilled [TAGS], and a string
    def test_approved_text_for_a_patient_is_checked(self):
        doc, pat = self.login("dr_lee"), self.login("pt_a")
        did = self.draft_for(doc, A)
        limit = self.app.policy["portal"]["max_body_chars"]
        for bad in ("Dear [NAME], your result is [RESULT].", "   ", "x" * (limit + 1), ["a list"], 7):
            with self.subTest(final_text=str(bad)[:20]):
                st, r = doc.call("/api/outbox/decide", {"id": did, "decision": "approve", "final_text": bad})
                self.assertEqual(st, 400, r)
        item = next(i for i in doc.call("/api/outbox")[1] if i["id"] == did)
        self.assertEqual(item["status"], "awaiting_approval")  # still editable, nothing approved
        good = mark("Your results are normal")
        self.assertEqual(doc.call("/api/outbox/decide", {"id": did, "decision": "approve", "final_text": good})[0], 200)
        # Belt and braces: text that somehow carries a tag after approval is refused again at send.
        self.app.outbox.update(did, lambda i: i.update(final_text="Dear [NAME], " + good))
        st, r = doc.call("/api/outbox/send", {"id": did})
        self.assertEqual(st, 409, r)
        self.assertNotIn(good, json.dumps(pat.call("/api/portal/messages")[1]))
        self.app.outbox.update(did, lambda i: i.update(final_text=good))
        self.assertEqual(doc.call("/api/outbox/send", {"id": did})[0], 200)
        self.assertIn(good, json.dumps(pat.call("/api/portal/messages")[1]))

    # 4. patient GETs are rate-limited, and a refused path is logged without patient-chosen text
    def test_patient_gets_are_rate_limited_and_refused_paths_are_sanitized(self):
        pat = self.login("pt_b")
        self.assertEqual(pat.call("/api/evil%3Cscript%3E!~" + "a" * 300)[0], 403)
        logged = [e["details"]["path"] for e in self.audit("portal_staff_route_refused") if e["user"] == "pt_b"]
        self.assertTrue(logged)
        for path in logged:
            self.assertRegex(path, r"^[A-Za-z0-9/_-]{0,60}$")
        server = self.app.policy["server"]
        old = server["max_requests_per_minute"]
        try:
            server["max_requests_per_minute"] = len(self.app.hits.get("pt_b", [])) + 3
            codes = [pat.call("/api/portal/messages")[0] for _ in range(5)]
            self.assertEqual(codes, [200, 200, 200, 429, 429])
        finally:
            server["max_requests_per_minute"] = old
            self.app.hits.pop("pt_b", None)

    # 5. text that is valid JSON but not valid UTF-8 (a lone surrogate) gets an answer, not a dropped connection
    def test_lone_surrogate_text_is_stored_safely(self):
        pat = self.login("pt_a")
        st, r = pat.call("/api/portal/messages", {"subject": "odd \ud800", "body": "lone \ud800 surrogate"})
        self.assertEqual(st, 200, r)
        self.assertEqual(r["message"]["body"], "lone ? surrogate")
        st, r = pat.call("/api/portal/appointments/request", {"visit_type": "Follow-up", "note": "\udfff"})
        self.assertEqual(st, 200, r)
        self.assertTrue(self.app.db.verify_chain()[0])

    # 6. a JSON body that is not an object is a 400 everywhere, including the sign-in route
    def test_non_object_json_body_is_400(self):
        staff, pat = self.login("dr_lee"), self.login("pt_a")
        for body in ([], "text", 5):
            with self.subTest(body=body):
                self.assertEqual(Client(self.base).call("/api/login", body)[0], 400)
                self.assertEqual(staff.call("/api/chat", body)[0], 400)
                self.assertEqual(pat.call("/api/portal/messages", body)[0], 400)

    # 7. staff usernames (clinician ids are usernames) never reach the patient
    def test_patient_sees_clinician_names_not_usernames(self):
        pat, desk = self.login("pt_a"), self.login("desk_sam")
        usernames = list(self.app.policy["clinic"]["clinicians"])
        self.assertEqual(pat.call("/api/portal/appointments/request",
                                  {"visit_type": "Follow-up", "clinician": usernames[1]})[0], 400)
        st, r = pat.call("/api/portal/appointments/request", {"visit_type": "Lab review", "clinician": "Dr Osei"})
        self.assertEqual((st, r["request"]["clinician"]), (200, "Dr Osei"))
        blob = json.dumps(pat.call("/api/portal/appointments")[1]) + json.dumps(r)
        for name in usernames + ["desk_sam"]:
            self.assertNotIn(name, blob)
        queue = desk.call("/api/inbox/requests?status=open")[1]["requests"]
        self.assertEqual(next(q for q in queue if q["id"] == r["request"]["id"])["clinician"], "dr_osei")

    # 8. a refused portal action and a /api/me read both leave an audit entry (without the probed id)
    def test_refused_probes_and_me_are_audited(self):
        pat, probe = self.login("pt_b"), mark("probe")
        self.assertEqual(pat.call("/api/portal/appointments/cancel", {"appointment_id": probe})[0], 404)
        self.assertEqual(pat.call("/api/portal/messages", {"body": "x", "in_reply_to": probe})[0], 404)
        refused = [e for e in self.audit("portal_refused") if e["user"] == "pt_b"]
        self.assertEqual({(e["details"]["route"], e["details"]["code"]) for e in refused},
                         {("/api/portal/appointments/cancel", 404), ("/api/portal/messages", 404)})
        self.assertNotIn(probe, (self.tmp / "audit.jsonl").read_text())
        self.assertEqual(pat.call("/api/me")[0], 200)
        self.assertTrue([e for e in self.audit("portal_me_viewed") if e["details"]["patient_id"] == B])

    # found while fixing 2: portal traffic stays out of the home screen's "recent chart changes"
    def test_portal_rows_are_not_listed_as_chart_changes(self):
        self.assertEqual(self.login("pt_a").call("/api/portal/messages", {"subject": "s", "body": "hello"})[0], 200)
        recent = self.login("dr_lee").call("/api/chart/recent")[1]
        self.assertFalse([r for r in recent if r["event"].startswith("portal_")])

    def test_zz_chains_verify_after_the_review_tests(self):
        self.assertTrue(self.app.audit.verify()["ok"])
        self.assertTrue(self.app.db.verify_chain()[0])


if __name__ == "__main__":
    unittest.main()
