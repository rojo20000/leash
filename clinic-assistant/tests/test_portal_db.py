"""Patient portal data layer (2.8): portal tables in the clinic database, and patient-linked accounts."""
import json
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.db import MSG_COLS, REQ_COLS, ClinicDB
from app.users import UserStore

POLICY = json.loads((Path(__file__).parent.parent / "config" / "policy.json").read_text())
PW = "synthetic-pass-123"


def msg(i, pid="syn-002", **kw):
    row = {"id": f"m{i}", "patient_id": pid, "direction": "from_patient", "sender": "pt_lena",
           "sender_role": "patient", "subject": "Refill", "body": "SECRET-BODY-TEXT", "source": "patient",
           "draft_id": None, "approved_by": None, "in_reply_to": None}
    return {**row, **kw}


def req(i, pid="syn-002", **kw):
    row = {"id": f"r{i}", "patient_id": pid, "kind": "book", "appointment_id": None, "visit_type": "Follow-up",
           "clinician": "dr_lee", "preferred": "Mornings", "note": "Thanks"}
    return {**row, **kw}


class PortalDB(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.db = ClinicDB(self.tmp / "clinic.db")

    def tearDown(self):
        self.db.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def last_change(self):
        return self.db.conn.execute("SELECT entity, entity_id, action, summary, before_json, after_json, by_user, role"
                                    " FROM change_log ORDER BY seq DESC LIMIT 1").fetchone()

    def test_messages_round_trip_and_are_logged(self):
        v, n = self.db.version, self.db.count("change_log")
        m1 = self.db.add_portal_message(msg(1), "pt_lena", "patient")
        self.assertEqual(set(m1), set(MSG_COLS))
        self.assertTrue(m1["at"])
        self.assertEqual((self.db.count("change_log"), self.db.version), (n + 1, v + 1))
        entity, entity_id, action, summary, before, after, by, role = self.last_change()
        self.assertEqual((entity, entity_id, action, by, role), ("patient", "syn-002", "portal_message", "pt_lena",
                                                                 "patient"))
        self.assertEqual(summary, "Portal message from patient")
        self.assertIsNone(before)
        self.assertEqual(json.loads(after), m1)
        m2 = self.db.add_portal_message(msg(2, direction="to_patient", sender="dr_lee", sender_role="clinician",
                                            source="staff", in_reply_to="m1"), "dr_lee", "clinician")
        self.assertEqual(self.last_change()[3], "Portal message to patient")
        self.db.add_portal_message(msg(3, pid="syn-003"), "pt_other", "patient")
        self.assertEqual(self.db.count("change_log"), n + 3)
        self.assertEqual(self.db.count("portal_messages"), 3)
        self.assertEqual([m["id"] for m in self.db.portal_messages("syn-002")], ["m2", "m1"])  # newest first
        self.assertEqual([m["id"] for m in self.db.portal_messages()], ["m3", "m2", "m1"])
        self.assertEqual([m["id"] for m in self.db.portal_messages(limit=1)], ["m3"])
        self.assertEqual(self.db.portal_message("m2"), m2)
        self.assertNotIn("seq", self.db.portal_message("m1"))
        self.assertIsNone(self.db.portal_message("nope"))
        self.assertEqual(self.db.verify_chain(), (True, n + 3, None))
        # the message text is in the row, never in the summary shown in history lists
        self.assertFalse(any("SECRET" in (h["summary"] or "") for h in self.db.history("syn-002")))
        self.assertEqual(len(self.db.history("syn-002")), 2)
        self.assertEqual(self.db.count("patients"), 0)  # portal writes never touch the patients table

    def test_messages_are_append_only(self):
        self.db.add_portal_message(msg(1), "pt_lena", "patient")
        raw = sqlite3.connect(str(self.tmp / "clinic.db"))
        try:
            for sql in ("UPDATE portal_messages SET body = 'x'", "DELETE FROM portal_messages"):
                with self.assertRaises(sqlite3.DatabaseError):
                    raw.execute(sql)
                    raw.commit()
        finally:
            raw.close()
        self.assertEqual(self.db.portal_message("m1")["body"], "SECRET-BODY-TEXT")

    def test_bad_message_writes_nothing(self):
        n, v = self.db.count("change_log"), self.db.version
        for bad in (msg(1, direction="sideways"), msg(1, source="model"), msg(1, body=None)):
            with self.assertRaises(sqlite3.IntegrityError):
                self.db.add_portal_message(bad, "pt_lena", "patient")
        self.db.add_portal_message(msg(1), "pt_lena", "patient")
        with self.assertRaises(sqlite3.IntegrityError):  # same id twice
            self.db.add_portal_message(msg(1), "pt_lena", "patient")
        self.assertEqual((self.db.count("portal_messages"), self.db.count("change_log"), self.db.version),
                         (1, n + 1, v + 1))
        self.assertTrue(self.db.verify_chain()[0])

    def test_requests_round_trip_and_decide(self):
        n = self.db.count("change_log")
        r1 = self.db.add_portal_request(req(1, status="done", handled_by="mallory"), "pt_lena", "patient")
        self.assertEqual(set(r1), set(REQ_COLS))
        self.assertEqual((r1["status"], r1["handled_by"], r1["handled_at"], r1["staff_note"]),
                         ("open", None, None, None))  # a caller cannot pre-decide a request
        self.assertTrue(r1["created_at"])
        entity, entity_id, action, _, before, after, _, _ = self.last_change()
        self.assertEqual((entity, entity_id, action, before), ("patient", "syn-002", "portal_request", None))
        self.assertEqual(json.loads(after), r1)
        self.db.add_portal_request(req(2, kind="cancel", appointment_id="a1"), "pt_lena", "patient")
        self.db.add_portal_request(req(3, pid="syn-003"), "pt_other", "patient")
        self.assertEqual(self.db.count("change_log"), n + 3)
        self.assertEqual(self.db.count("portal_requests"), 3)
        self.assertEqual([r["id"] for r in self.db.portal_requests("syn-002")], ["r2", "r1"])
        self.assertEqual([r["id"] for r in self.db.portal_requests()], ["r3", "r2", "r1"])
        self.assertEqual(self.db.portal_request("r1"), r1)
        self.assertIsNone(self.db.portal_request("nope"))

        v = self.db.version
        done = self.db.decide_portal_request("r1", "done", "frontdesk", "receptionist", "Booked for Tuesday")
        self.assertEqual((done["status"], done["handled_by"], done["staff_note"]),
                         ("done", "frontdesk", "Booked for Tuesday"))
        self.assertTrue(done["handled_at"])
        self.assertEqual(self.db.portal_request("r1"), done)
        self.assertEqual((self.db.count("change_log"), self.db.version), (n + 4, v + 1))
        entity, entity_id, action, _, before, after, by, role = self.last_change()
        self.assertEqual((entity, entity_id, action, by, role),
                         ("patient", "syn-002", "portal_request_done", "frontdesk", "receptionist"))
        self.assertEqual((json.loads(before), json.loads(after)), (r1, done))
        self.db.decide_portal_request("r2", "declined", "frontdesk", "receptionist", "Please call us")
        self.assertEqual(self.last_change()[2], "portal_request_declined")
        self.assertEqual([r["id"] for r in self.db.portal_requests(status="open")], ["r3"])
        self.assertEqual([r["id"] for r in self.db.portal_requests("syn-002", "declined")], ["r2"])

        n = self.db.count("change_log")
        for rid, status in (("r1", "declined"), ("r2", "done"), ("nope", "done"), ("r3", "open"), ("r3", "x")):
            with self.assertRaises(ValueError):
                self.db.decide_portal_request(rid, status, "frontdesk", "receptionist", "")
        self.assertEqual(self.db.count("change_log"), n)
        self.assertEqual(self.db.portal_request("r1")["status"], "done")
        self.assertEqual(self.db.portal_request("r3")["status"], "open")
        self.assertEqual(self.db.verify_chain(), (True, n, None))

    def test_appointments_for_patient(self):
        def appt(i, pid, day, at):
            return {"id": f"a{i}", "date": day, "time": at, "clinician": "dr_lee", "patient_id": pid,
                    "visit_type": "Follow-up", "status": "booked"}
        self.db.write_many([("appointment", appt(1, "syn-002", "2026-12-02", "09:00"), "booked", ""),
                            ("appointment", appt(2, "syn-003", "2026-12-01", "09:00"), "booked", ""),
                            ("appointment", appt(3, "syn-002", "2026-12-01", "10:20"), "booked", ""),
                            ("appointment", appt(4, "syn-002", "2026-12-01", "08:00"), "booked", "")], "system", None)
        mine = self.db.appointments_for_patient("syn-002")
        self.assertEqual([a["id"] for a in mine], ["a4", "a3", "a1"])
        self.assertTrue(all(a["patient_id"] == "syn-002" for a in mine))
        self.assertEqual(self.db.appointments_for_patient("syn-999"), [])

    def test_old_and_new_rows_share_one_chain(self):
        self.db.write("patient", {"id": "syn-002", "name": {"given": "Lena", "family": "Delacroix"}}, "registered",
                      "frontdesk", "receptionist", "Registered")
        self.db.add_portal_message(msg(1), "pt_lena", "patient")
        self.db.write("patient", {"id": "syn-002", "name": {"given": "Lena", "family": "Delacroix"}, "phone": "555-0101"},
                      "updated", "frontdesk", "receptionist", "Phone")
        self.db.add_portal_request(req(1), "pt_lena", "patient")
        self.assertEqual(self.db.verify_chain(), (True, 4, None))
        self.assertEqual(self.db.patient("syn-002")["phone"], "555-0101")  # the chart row is the chart, not a message
        self.assertEqual([h["action"] for h in self.db.history("syn-002")],
                         ["portal_request", "updated", "portal_message", "registered"])
        self.db.close()
        self.db = ClinicDB(self.tmp / "clinic.db")  # reopening keeps the data and the chain
        self.assertEqual(self.db.verify_chain(), (True, 4, None))
        self.assertEqual(self.db.count("portal_messages"), 1)


class PatientAccounts(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.store = UserStore(self.tmp / "users.json", POLICY["roles"], POLICY["portal"]["patient_role"])

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_patient_link(self):
        with self.assertRaises(ValueError):
            self.store.add("pt_lena", PW, "patient")
        with self.assertRaises(ValueError):
            self.store.add("dr_lee", PW, "clinician", "syn-002")
        self.assertEqual(self.store.list(), [])
        self.store.add("pt_lena", PW, "patient", "syn-002")
        self.store.add("dr_lee", PW, "clinician")
        self.assertEqual(self.store.patient_id("pt_lena"), "syn-002")
        self.assertIsNone(self.store.patient_id("dr_lee"))
        self.assertIsNone(self.store.patient_id("nobody"))
        self.assertEqual(self.store.list(), [("pt_lena", "patient", True), ("dr_lee", "clinician", True)])
        self.assertEqual(self.store.check("pt_lena", PW), "patient")
        self.assertEqual(json.loads((self.tmp / "users.json").read_text())["pt_lena"]["patient_id"], "syn-002")

    def test_two_argument_constructor_still_works(self):
        store = UserStore(self.tmp / "u2.json", POLICY["roles"])
        store.add("pt_lena", PW, "patient", "syn-002")
        self.assertEqual(store.patient_id("pt_lena"), "syn-002")

    def test_policy_has_the_portal_block(self):
        roles, portal = POLICY["roles"], POLICY["portal"]
        self.assertEqual(roles[portal["patient_role"]], ["portal_chart", "portal_appointments", "portal_messages"])
        for role in ("clinician", "nurse", "clinical_lead"):
            self.assertLessEqual({"portal_inbox", "send_portal"}, set(roles[role]))
        self.assertIn("portal_requests", roles["receptionist"])
        self.assertNotIn("portal_inbox", roles["receptionist"])  # front desk never reads message bodies
        staff_perms = {p for r, perms in roles.items() if r != portal["patient_role"] for p in perms}
        self.assertFalse(staff_perms & set(roles[portal["patient_role"]]))
        for hidden in ("notes", "attention", "mrn", "insurance", "scenario"):
            self.assertNotIn(hidden, portal["released_fields"])


if __name__ == "__main__":
    unittest.main()
