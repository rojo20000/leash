"""2.5: the general assistant grounded in today's schedule, the conversation log, and the network view."""
import json
import os
import shutil
import sqlite3
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

os.environ["MOCK_LLM"] = "1"
from app import llm  # noqa: E402
from app.server import App, make_handler  # noqa: E402
from tests.test_smoke import PW, Client  # noqa: E402

USERS = [("dr_lee", "clinician"), ("lead_ana", "clinical_lead"), ("auditor_ray", "auditor"),
         ("desk_sam", "receptionist"), ("net_ops", "network_engineer")]


class FakeModel:
    """Stands in for llm.chat: records what the model was sent and answers with a fixed text."""

    def __init__(self, answer):
        self.answer, self.calls = answer, []

    def __enter__(self):
        self.real, llm.chat = llm.chat, self
        return self

    def __exit__(self, *exc):
        llm.chat = self.real

    def __call__(self, policy, messages, system=None):
        self.calls.append({"messages": messages, "system": system})
        return self.answer


class Round2(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.app = App(data_dir=cls.tmp)
        cls.app.policy["tiers"]["green_sample_rate"] = 0
        cls.app.policy["server"]["max_requests_per_minute"] = 1000
        cls.app.policy["network"]["public_probe"] = ""  # no internet probe in tests
        for name, role in USERS:
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
        self.assertEqual(c.call("/api/login", {"username": user, "password": PW})[0], 200)
        return c

    def todays(self, clinician=None):
        today = self.app.schedule.now().date().isoformat()
        return [a for a in self.app.schedule.day(today) if clinician is None or a["clinician"] == clinician]

    # ---- A. general questions are grounded in today's schedule -------------
    def test_general_chat_gets_todays_schedule_without_identifiers(self):
        doc = self.login("dr_lee")
        doc.call("/api/chat/clear", {})
        with FakeModel("Patient A needs a look first.") as m:
            st, r = doc.call("/api/chat", {"message": "Who needs attention today?"})
        self.assertEqual(st, 200, r)
        self.assertEqual(r["tier"], "green", r)
        sent, system = m.calls[0]["messages"][-1]["content"], m.calls[0]["system"]
        mine = self.todays("dr_lee")
        self.assertTrue(mine)
        self.assertIn(f"Patient A ({mine[0]['patient_id']})", sent)
        for a in mine[:25]:
            self.assertIn(f"({a['patient_id']})", sent)
        self.assertNotIn("dr_osei", sent)  # a clinician sees their own list
        for a in mine:
            p = self.app.ehr.get(a["patient_id"])
            for secret in (p["name"]["given"], p["name"]["family"], p["mrn"], p["birthDate"], p["phone"]):
                self.assertNotIn(secret, sent)
        self.assertIn("Never invent patients", system)
        ctx = [t for t in r["trace"] if t["step"] == "Context"]
        self.assertEqual(ctx[0]["detail"].split(";")[0],
                         f"today's schedule ({min(len(mine), 25)} appointments) from local database")
        # the poisoned referral (syn-003) is withheld here too
        self.assertNotIn("records-export", sent)
        # the next turn keeps only the question in history, and rebuilds the context fresh
        with FakeModel("Noted.") as m:
            doc.call("/api/chat", {"message": "And after lunch?"})
        msgs = m.calls[0]["messages"]
        self.assertEqual(msgs[0]["content"], "Who needs attention today?")
        self.assertIn("Today's schedule", msgs[-1]["content"])

    def test_invented_patient_is_held(self):
        doc = self.login("dr_lee")
        with FakeModel("Patient Q (syn-099) has an INR of 6.") as m:
            st, r = doc.call("/api/chat", {"message": "Anyone with a high INR?"})
        self.assertEqual(r["tier"], "amber", r)
        self.assertTrue(any("not in today's list" in x for x in r["reasons"]))
        known = self.app.today_context({"user": "dr_lee", "role": "clinician"})["labels"]
        self.assertEqual(App.unknown_patients("Patient A and Patient B", known), [])
        self.assertEqual(App.unknown_patients("[Patient Tag 1] is overdue", known), ["Patient Tag 1"])
        self.assertTrue(m.calls)

    def test_context_respects_role(self):
        desk = self.app.today_context({"user": "desk_sam", "role": "receptionist"})
        self.assertIn("Today's schedule (whole clinic)", desk["text"])
        self.assertFalse(desk["clinical"])
        for bad in ("Conditions", "Allergies", "Needs attention", "results", "note"):
            self.assertNotIn(bad, desk["text"])
        for a in self.todays():
            p = self.app.ehr.get(a["patient_id"])
            for c in p["conditions"] + p["medications"] + [p["name"]["family"]]:
                self.assertNotIn(c, desk["text"])
        self.assertIsNone(self.app.today_context({"user": "auditor_ray", "role": "auditor"}))
        self.assertIsNone(self.app.today_context({"user": "net_ops", "role": "network_engineer"}))

    # ---- B. conversation log ----------------------------------------------
    def test_conversation_log(self):
        doc, desk, lead = self.login("dr_lee"), self.login("desk_sam"), self.login("lead_ana")
        st, first = doc.call("/api/chat", {"message": "Summarise this record", "patient_id": "syn-004"})
        self.assertEqual(st, 200)
        doc.call("/api/patients/syn-004/entry", {"pin": "1234", "kind": "condition", "text": "Gout"})
        doc.call("/api/chat", {"message": "Thanks"})
        desk.call("/api/frontdesk/ask", {"message": "How many patients does Dr Lee have today?"})

        st, mine = doc.call("/api/conversations?limit=50")
        self.assertEqual(st, 200)
        self.assertFalse(mine["can_see_all"])
        self.assertEqual({i["user"] for i in mine["items"]}, {"dr_lee"})
        seqs = [i["seq"] for i in mine["items"]]
        self.assertEqual(seqs, sorted(seqs, reverse=True))
        turn = next(i for i in mine["items"] if i["id"] == first["conversation_id"])
        self.assertEqual((turn["kind"], turn["patient_id"], turn["context_summary"]), ("chat", "syn-004", "record syn-004"))
        self.assertEqual(turn["question"], "Summarise this record")
        self.assertIn("Gout", " ".join(c["summary"] for c in turn["changes"]))
        self.assertTrue(turn["answer"])
        self.assertIsInstance(turn["duration_ms"], int)
        ref = turn["audit_ref"]
        self.assertTrue(any(e["ts"] == ref["ts"] and e["hash"] == ref["hash"] for e in self.app.audit.read(500)))
        self.assertEqual(mine["items"][0]["context_summary"].split(",")[0], "today's schedule")

        st, everyone = lead.call("/api/conversations?limit=100")
        self.assertTrue(everyone["can_see_all"])
        fd = [i for i in everyone["items"] if i["kind"] == "frontdesk"]
        self.assertTrue(fd and fd[0]["user"] == "desk_sam")
        self.assertNotIn("Lee", fd[0]["question"] + (fd[0]["answer"] or ""))  # stored masked
        only = lead.call("/api/conversations?user=desk_sam")[1]["items"]
        self.assertEqual({i["user"] for i in only}, {"desk_sam"})
        by_patient = lead.call("/api/conversations?patient_id=syn-004")[1]["items"]
        self.assertTrue(by_patient and all(i["patient_id"] == "syn-004" for i in by_patient))
        self.assertEqual(desk.call("/api/conversations?user=dr_lee")[1]["items"][0]["user"], "desk_sam")
        self.assertEqual(self.login("net_ops").call("/api/conversations")[0], 403)

        with self.assertRaises(sqlite3.DatabaseError):
            self.app.db.conn.execute("UPDATE conversations SET answer = 'x'")
        with self.assertRaises(sqlite3.DatabaseError):
            self.app.db.conn.execute("DELETE FROM conversations")
        ok, n, _ = self.app.db.verify_conversations()
        self.assertTrue(ok); self.assertGreaterEqual(n, 3)

    # ---- C. network engineer ------------------------------------------------
    def test_network_engineer_sees_only_the_network(self):
        net = self.login("net_ops")
        for path in ("/api/patients", "/api/patients/syn-001", "/api/patients/syn-001/history", "/api/schedule",
                     "/api/calendar", "/api/conversations", "/api/audit", "/api/frontdesk/patients?q=ab"):
            self.assertEqual(net.call(path)[0], 403, path)
        self.assertEqual(net.call("/api/chat", {"message": "hi"})[0], 403)
        self.assertEqual(net.call("/api/frontdesk/ask", {"message": "hi"})[0], 403)
        for user in ("dr_lee", "desk_sam", "auditor_ray"):
            self.assertEqual(self.login(user).call("/api/network")[0], 403)

        self.login("dr_lee").call("/api/chat", {"message": "Any tips for a busy clinic?"})  # one model call
        st, n = net.call("/api/network")
        self.assertEqual(st, 200)
        self.assertEqual(set(n), {"nodes", "edges", "egress", "recent_calls", "checked_at"})
        ids = {x["id"] for x in n["nodes"]}
        self.assertTrue({"browsers", "app", "ollama", "clinic_db", "vectors", "audit_log", "leash"} <= ids)
        for x in n["nodes"]:
            self.assertEqual(set(x), {"id", "label", "kind", "address", "status", "detail"})
            self.assertIn(x["status"], ("up", "down", "disabled", "unknown"))
        for e in n["edges"]:
            self.assertEqual(set(e), {"from", "to", "protocol", "purpose", "status", "last_seen", "calls_24h"})
            self.assertTrue({e["from"], e["to"]} <= ids)
        self.assertEqual(next(x for x in n["nodes"] if x["id"] == "leash")["status"], "disabled")
        self.assertEqual(next(x for x in n["nodes"] if x["id"] == "clinic_db")["status"], "up")
        self.assertEqual(n["egress"]["outbound_internet"], "unknown")  # probe off in tests
        self.assertTrue(all(c["ok"] for c in n["egress"]["checks"][:3]))
        self.assertTrue(n["recent_calls"])
        for c in n["recent_calls"]:
            self.assertEqual(set(c), {"at", "from", "to", "what", "ok", "ms"})
        body = json.dumps(n)
        self.assertNotIn("syn-", body)
        for p in self.app.ehr.patients.values():
            self.assertNotIn(p["name"]["family"], body)
        calls = [e for e in self.app.audit.read(500) if e["event"] == "model_call"]
        self.assertTrue(calls)
        self.assertEqual(set(calls[0]["details"]), {"from", "to", "what", "model", "ms", "ok"})  # no content


if __name__ == "__main__":
    unittest.main()
