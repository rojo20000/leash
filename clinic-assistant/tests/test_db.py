"""The clinic database (data/clinic.db): migration, change tracking, permissions, integrity, new endpoints."""
import json
import os
import shutil
import sqlite3
import tempfile
import threading
import unittest
from datetime import date, timedelta
from http.server import ThreadingHTTPServer
from pathlib import Path

os.environ["MOCK_LLM"] = "1"
from app.db import ClinicDB  # noqa: E402
from app.ehr import EHR, generate  # noqa: E402
from app.schedule import Schedule  # noqa: E402
from app.server import App, make_handler  # noqa: E402
from tests.test_smoke import PW, Client  # noqa: E402

NEW_PATIENT = {"given": "Marigold", "family": "Esterhazy-Vance", "birthDate": "1979-06-14", "sex": "female",
               "phone": "555-0177", "address": "48 Example Street, Testville", "plan": "Commercial HMO",
               "member_id": "SYNM551200", "preferred_contact": "Phone call", "language": "English", "pin": "1234"}


class Migration(unittest.TestCase):
    def test_imports_json_once_and_leaves_files_alone(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            pats = generate(5)
            (tmp / "patients.json").write_text(json.dumps(pats))
            appt = {"id": "a1", "date": "2026-01-05", "time": "09:00", "clinician": "dr_lee", "patient_id": "syn-001",
                    "visit_type": "Follow-up", "status": "done", "cancel_reason": None, "reminder": None,
                    "history": []}
            (tmp / "schedule.json").write_text(json.dumps([appt]))
            before = {f: (tmp / f).read_bytes() for f in ("patients.json", "schedule.json")}
            clinic = json.loads((Path(__file__).parent.parent / "config" / "policy.json").read_text())["clinic"]
            db = ClinicDB(tmp / "clinic.db")
            ehr = EHR(tmp / "patients.json", db)
            Schedule(tmp / "schedule.json", clinic, ehr.patients, db=db)
            self.assertEqual(db.count("patients"), 5)
            self.assertEqual(db.appointment("a1")["status"], "done")
            hist = db.history("syn-001")
            imported = [h for h in hist if h["action"] == "imported"]
            self.assertEqual(len([h for h in imported if h["entity"] == "patient"]), 1)
            self.assertEqual(len([h for h in imported if h["entity"] == "appointment"]), 1)
            self.assertTrue(all(h["by"] == "system" for h in imported))
            n = db.count("change_log")
            # a second start imports nothing again
            db2 = ClinicDB(tmp / "clinic.db")
            ehr2 = EHR(tmp / "patients.json", db2)
            Schedule(tmp / "schedule.json", clinic, ehr2.patients, db=db2)
            self.assertEqual(db2.count("change_log"), n)
            self.assertEqual(before, {f: (tmp / f).read_bytes() for f in before})
            self.assertEqual(db2.verify_chain(), (True, n, None))
            db.close(); db2.close()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_generates_patients_when_no_json(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            ehr = EHR(tmp / "patients.json", ClinicDB(tmp / "clinic.db"))
            self.assertEqual(len(ehr.patients), 40)
            self.assertFalse((tmp / "patients.json").exists())  # the database is the store now
            self.assertIn("insurance", ehr.get("syn-001"))
            ehr.db.close()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class Integrity(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.db = ClinicDB(self.tmp / "clinic.db")
        for i in range(3):
            self.db.write("patient", {"id": f"p{i}", "name": {"given": "A", "family": "B"}}, "registered",
                          "desk_sam", "receptionist", "Registered")

    def tearDown(self):
        self.db.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_change_log_is_append_only(self):
        with self.assertRaises(sqlite3.DatabaseError):
            self.db.conn.execute("UPDATE change_log SET summary = 'nothing happened' WHERE seq = 1")
        with self.assertRaises(sqlite3.DatabaseError):
            self.db.conn.execute("DELETE FROM change_log WHERE seq = 1")
        self.assertEqual(self.db.verify_chain(), (True, 3, None))

    def test_tampering_is_detected(self):
        raw = sqlite3.connect(str(self.tmp / "clinic.db"))
        raw.execute("DROP TRIGGER change_log_no_update")
        raw.execute("UPDATE change_log SET by_user = 'someone_else' WHERE seq = 2")
        raw.commit()
        raw.close()
        self.assertEqual(self.db.verify_chain(), (False, 1, 2))
        self.assertFalse(self.db.status()["chain_ok"])

    def test_failed_write_leaves_nothing(self):
        with self.assertRaises(KeyError):
            self.db.write_many([("patient", {"id": "p9", "name": {}}, "registered", ""),
                                ("appointment", {"id": "x"}, "booked", "")], "dr_lee", "clinician")
        self.assertIsNone(self.db.patient("p9"))
        self.assertEqual(self.db.count("change_log"), 3)


class Api(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.app = App(data_dir=cls.tmp)
        cls.app.policy["tiers"]["green_sample_rate"] = 0
        cls.app.policy["server"]["max_requests_per_minute"] = 1000
        for name, role in [("dr_lee", "clinician"), ("auditor_ray", "auditor"), ("desk_sam", "receptionist")]:
            cls.app.users.add(name, PW, role)
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(cls.app))
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.httpd.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.app.db.close(); cls.app.vectors.db.close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def login(self, user):
        c = Client(self.base)
        st, _ = c.call("/api/login", {"username": user, "password": PW})
        self.assertEqual(st, 200)
        return c

    def test_register_writes_row_and_change(self):
        desk = self.login("desk_sam")
        st, r = desk.call("/api/patients/new", NEW_PATIENT)
        self.assertEqual(st, 200, r)
        row = self.app.db._q("SELECT family, given, birth_date, registered_by FROM patients WHERE id = ?", (r["id"],))
        self.assertEqual(row[0], ("Esterhazy-Vance", "Marigold", "1979-06-14", "desk_sam"))
        h = self.app.db.history(r["id"])[0]
        self.assertEqual((h["action"], h["by"], h["role"], h["entity"]), ("registered", "desk_sam", "receptionist", "patient"))
        self.assertIn(r["id"], self.app.ehr.patients)  # the shared view sees it at once
        # front desk can book and check in the new patient
        today = date.today().isoformat()
        slots = desk.call(f"/api/schedule/slots?date={today}&clinician=dr_osei")[1]
        if slots:  # none left late in the day
            st, a = desk.call("/api/schedule/book", {"patient_id": r["id"], "date": today, "time": slots[0],
                                                     "clinician": "dr_osei", "visit_type": "New problem"})
            self.assertEqual(st, 200, a)
            st, a = desk.call("/api/schedule/status", {"id": a["id"], "expected": "booked", "to": "arrived",
                                                       "checks": {"dob": True, "insurance": True}})
            self.assertEqual(st, 200, a)
            actions = [x["action"] for x in self.app.db.history(r["id"])]
            self.assertEqual(actions[:3], ["checked_in", "booked", "registered"])

    def test_clinician_edit_is_tracked_and_reaches_the_model(self):
        from app import llm
        doc = self.login("dr_lee")
        pid = "syn-004"
        n = self.app.db.count("change_log")
        st, r = doc.call(f"/api/patients/{pid}/entry", {"pin": "1234", "kind": "note", "type": "Visit note",
                                                         "text": "Started a supervised walking program this week."})
        self.assertEqual(st, 200, r)
        self.assertEqual(self.app.db.count("change_log"), n + 1)
        h = self.app.db.history(pid)[0]
        self.assertEqual((h["action"], h["by"], h["role"]), ("chart_entry", "dr_lee", "clinician"))
        seen, real = [], llm.chat
        llm.chat = lambda policy, messages: seen.append(messages[-1]["content"]) or "Noted."
        try:
            st, _ = doc.call("/api/chat", {"message": "Summarise the latest note", "patient_id": pid})
        finally:
            llm.chat = real
        self.assertEqual(st, 200)
        self.assertIn("supervised walking program", seen[0])

    def test_reception_cannot_edit_clinical_details(self):
        desk = self.login("desk_sam")
        n = self.app.db.count("change_log")
        for body in ({"kind": "note", "type": "Visit note", "text": "feels fine today"},
                     {"kind": "medication", "text": "Aspirin 81 mg daily"},
                     {"kind": "allergy", "text": "Latex"}):
            self.assertEqual(desk.call("/api/patients/syn-001/entry", {"pin": "1234", **body})[0], 403)
        self.assertEqual(self.app.db.count("change_log"), n)

    def test_history_endpoint(self):
        desk, doc, aud = self.login("desk_sam"), self.login("dr_lee"), self.login("auditor_ray")
        self.assertEqual(desk.call("/api/patients/syn-002/history")[0], 403)
        self.assertEqual(doc.call("/api/patients/nope/history")[0], 404)
        doc.call("/api/patients/syn-002/entry", {"pin": "1234", "kind": "condition", "text": "Gout"})
        for c in (doc, aud):
            st, hist = c.call("/api/patients/syn-002/history")
            self.assertEqual(st, 200)
            self.assertEqual(set(hist[0]), {"seq", "at", "by", "role", "entity", "entity_id", "action", "summary"})
            self.assertEqual([h["seq"] for h in hist], sorted((h["seq"] for h in hist), reverse=True))
            self.assertEqual(hist[0]["summary"], "Added condition: Gout")
            self.assertIn("imported", [h["action"] for h in hist])
        events = [(e["event"], e["user"]) for e in self.app.audit.read(20)]
        self.assertIn(("patient_history_viewed", "auditor_ray"), events)

    def test_calendar(self):
        doc = self.login("dr_lee")
        today = date.today()
        st, cal = doc.call(f"/api/calendar?from={today - timedelta(days=3)}&to={today + timedelta(days=3)}")
        self.assertEqual(st, 200, cal)
        self.assertEqual((cal["from"], cal["to"], cal["today"]),
                         ((today - timedelta(days=3)).isoformat(), (today + timedelta(days=3)).isoformat(), today.isoformat()))
        self.assertEqual([d["date"] for d in cal["days"]], [(today + timedelta(days=i)).isoformat() for i in range(-3, 4)])
        self.assertIn({"id": "dr_lee", "name": "Dr Lee"}, cal["clinicians"])
        past = cal["days"][0]["appointments"]
        self.assertTrue(past and all(a["status"] in ("done", "no_show") for a in past))
        sched = doc.call(f"/api/schedule?date={today}")[1]["appointments"]
        self.assertEqual(cal["days"][3]["appointments"], sched)  # same objects as /api/schedule
        st, mine = doc.call(f"/api/calendar?from={today}&to={today}&clinician=dr_lee")
        self.assertTrue(all(a["clinician"] == "dr_lee" for a in mine["days"][0]["appointments"]))
        far = today + timedelta(days=30)
        st, empty = doc.call(f"/api/calendar?from={far}&to={far + timedelta(days=2)}")
        self.assertEqual([len(d["appointments"]) for d in empty["days"]], [0, 0, 0])
        self.assertEqual(doc.call(f"/api/calendar?from={today}&to={today + timedelta(days=42)}")[0], 400)
        self.assertEqual(doc.call("/api/calendar?from=bad")[0], 400)
        self.assertEqual(doc.call(f"/api/calendar?from={today}&clinician=dr_who")[0], 400)
        self.assertEqual(self.login("auditor_ray").call("/api/calendar")[0], 403)
        st, desk_cal = self.login("desk_sam").call(f"/api/calendar?from={today}&to={today}")
        self.assertEqual(st, 200)
        allowed = set(self.app.policy["frontdesk"]["allowed_fields"]) | {"locked"}
        for a in desk_cal["days"][0]["appointments"]:
            self.assertTrue(set(a["patient"]) <= allowed, a["patient"])

    def test_db_status(self):
        st, s = self.login("desk_sam").call("/api/db/status")
        self.assertEqual(st, 200)
        self.assertEqual((s["engine"], s["file"], s["chain_ok"]), ("sqlite", f"{self.tmp.name}/clinic.db", True))
        self.assertGreaterEqual(s["patients"], 40)
        self.assertGreater(s["appointments"], 0)
        self.assertGreater(s["changes"], s["patients"])


class Persistence(unittest.TestCase):
    def test_survives_restart(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            app = App(data_dir=tmp)
            sess = {"user": "desk_sam", "role": "receptionist"}
            p = app.register(sess, {k: v for k, v in NEW_PATIENT.items() if k != "pin"})
            pid, n = p["id"], app.db.count("change_log")
            again = App(data_dir=tmp)
            self.assertEqual(again.ehr.get(pid)["name"]["family"], "Esterhazy-Vance")
            self.assertIn(pid, again.ehr.patients)
            self.assertEqual(again.db.count("change_log"), n)  # nothing re-imported or re-seeded
            self.assertEqual(again.db.verify_chain(), (True, n, None))
            for a in (app, again):
                a.db.close(); a.vectors.db.close()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
