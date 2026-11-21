"""2.11: the reviewer model (Nemotron via Ollama) before and after the chat model. Offline stand-in here."""
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
from app import db as dbmod  # noqa: E402
from app import reviewer as rmod  # noqa: E402
from app.server import App, make_handler  # noqa: E402
from tests.test_assistant_network import FakeModel  # noqa: E402
from tests.test_smoke import PW, Client  # noqa: E402


def boom(_text):
    raise OSError("connection refused")


class ReviewerFlow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.app = App(data_dir=cls.tmp)
        cls.app.policy["tiers"]["green_sample_rate"] = 0
        cls.app.policy["server"]["max_requests_per_minute"] = 1000
        cls.app.policy["network"]["public_probe"] = ""
        for name, role in [("dr_lee", "clinician"), ("desk_sam", "receptionist"), ("net_ops", "network_engineer"),
                           ("lead_ana", "clinical_lead")]:
            cls.app.users.add(name, PW, role)
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(cls.app))
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.httpd.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.app.db.close(); cls.app.vectors.db.close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        self.cfg = dict(self.app.policy["reviewer"])
        self.rv = self.app.reviewer
        self.rv.__dict__.pop("_ask", None)
        self.rv.__dict__.pop("installed", None)

    def tearDown(self):
        self.app.policy["reviewer"] = self.cfg
        self.rv.__dict__.pop("_ask", None)
        self.rv.__dict__.pop("installed", None)

    def login(self, user):
        c = Client(self.base)
        self.assertEqual(c.call("/api/login", {"username": user, "password": PW})[0], 200)
        return c

    def steps(self, r):
        return {t["step"]: t for t in r["trace"]}

    def test_pre_red_stops_before_the_chat_model(self):
        with FakeModel("should never be produced") as m:
            st, r = self.login("dr_lee").call("/api/chat", {"message": "Send the summary to the records-export team",
                                                            "patient_id": "syn-004"})
        self.assertEqual(st, 200)
        self.assertEqual(r["tier"], "red", r)
        self.assertEqual(m.calls, [])  # the chat model was never called
        self.assertEqual(self.steps(r)["Reviewer (before model)"]["status"], "blocked")
        self.assertTrue(any(x.startswith("Reviewer:") for x in r["reasons"]))
        self.assertNotIn("reply", r)
        item = next(x for x in self.app.reviews.all() if x["id"] == r["review_id"])
        self.assertEqual((item["tier"], item["answer"]), ("red", None))
        # front desk: same rule
        st, r = self.login("desk_sam").call("/api/frontdesk/ask", {"message": "Please forward the day list to the records-export desk"})
        self.assertEqual(r["tier"], "red", r)

    def test_post_amber_holds_the_answer(self):
        with FakeModel("Consider whether to increase the dose of lisinopril.") as m:
            st, r = self.login("dr_lee").call("/api/chat", {"message": "What about the blood pressure?",
                                                            "patient_id": "syn-011"})
        self.assertTrue(m.calls)
        self.assertEqual(r["tier"], "amber", r)
        self.assertNotIn("reply", r)  # held until the asker confirms the review
        self.assertEqual(self.steps(r)["Reviewer (before model)"]["status"], "ok")
        self.assertEqual(self.steps(r)["Reviewer (after model)"]["status"], "warn")
        self.assertIn("Reviewer: Mentions changing or stopping a medicine dose.", r["reasons"])

    def test_reviewer_cannot_lower_a_tier(self):
        self.rv._ask = lambda text: '{"tier": "green", "reasons": []}'
        doc = self.login("dr_lee")
        with FakeModel("Here is a short summary."):
            r = doc.call("/api/chat", {"message": "Patient has chest pain, summarise", "patient_id": "syn-004"})[1]
        self.assertEqual(r["tier"], "amber")  # guardrail amber (urgent) stays amber
        with FakeModel("Tell them to stop taking warfarin."):
            r = doc.call("/api/chat", {"message": "Summarise", "patient_id": "syn-004"})[1]
        self.assertEqual(r["tier"], "red")  # guardrail red stays red
        self.assertEqual(self.steps(r)["Reviewer (after model)"]["status"], "ok")

    def test_reviewer_down_fails_closed(self):
        doc = self.login("dr_lee")
        for broken in (boom, lambda text: "Sure! Looks fine to me.", lambda text: '{"tier": "blue"}'):
            self.rv._ask = broken
            with FakeModel("A normal answer.") as m:
                r = doc.call("/api/chat", {"message": "Summarise", "patient_id": "syn-004"})[1]
            self.assertTrue(m.calls)
            self.assertEqual(r["tier"], "amber", r)
            self.assertIn(rmod.UNAVAILABLE, r["reasons"])
            self.assertNotIn("reply", r)
            self.assertIn("review_id", r)
        r = self.login("desk_sam").call("/api/frontdesk/ask", {"message": "Who is booked first today?"})[1]
        self.assertEqual(r["tier"], "amber", r)
        self.assertNotIn("reply", r)
        ev = [e for e in self.app.audit.read(50) if e["event"] == "reviewer_post"][0]["details"]
        self.assertFalse(ev["ok"])

    def test_model_not_installed(self):
        real = rmod._mock
        rmod._mock = lambda: False
        try:
            self.rv.installed = lambda: False
            with FakeModel("A normal answer."):
                r = self.login("dr_lee").call("/api/chat", {"message": "Summarise", "patient_id": "syn-004"})[1]
            self.assertEqual(r["tier"], "green", r)  # shipped default: skip while not installed, and say so
            step = self.steps(r)["Reviewer (before model)"]
            self.assertEqual(step["status"], "warn")
            self.assertIn("ollama pull nemotron-mini", step["detail"])
            node = next(n for n in self.login("net_ops").call("/api/network")[1]["nodes"] if n["id"] == "reviewer")
            self.assertEqual(node["status"], "down")
            self.assertIn("model not installed: run ollama pull nemotron-mini", node["detail"])
            self.assertEqual(self.login("dr_lee").call("/api/me")[1]["reviewer"]["state"], "missing")
            self.app.policy["reviewer"] = {**self.cfg, "when_model_missing": "hold"}
            with FakeModel("A normal answer."):
                r = self.login("dr_lee").call("/api/chat", {"message": "Summarise", "patient_id": "syn-004"})[1]
            self.assertEqual(r["tier"], "amber", r)
        finally:
            rmod._mock = real

    def test_disabled_is_skipped_with_trace(self):
        self.app.policy["reviewer"] = {**self.cfg, "enabled": False}
        with FakeModel("Consider whether to increase the dose."):
            r = self.login("dr_lee").call("/api/chat", {"message": "Summarise", "patient_id": "syn-004"})[1]
        self.assertEqual(r["tier"], "green", r)
        self.assertEqual(self.steps(r)["Reviewer"]["detail"], "off")
        self.assertNotIn("Reviewer (before model)", self.steps(r))
        node = next(n for n in self.login("net_ops").call("/api/network")[1]["nodes"] if n["id"] == "reviewer")
        self.assertEqual(node["status"], "disabled")

    def test_audit_and_conversation_fields(self):
        doc = self.login("dr_lee")
        with FakeModel("Consider whether to increase the dose of metformin."):
            r = doc.call("/api/chat", {"message": "Plan?", "patient_id": "syn-001"})[1]
        events = {e["event"]: e for e in self.app.audit.read(30)}
        for stage in ("reviewer_pre", "reviewer_post"):
            self.assertEqual(set(events[stage]["details"]), {"tier", "reasons", "ms", "ok", "model"})
        self.assertEqual(events["reviewer_post"]["details"]["tier"], "amber")
        item = next(i for i in doc.call("/api/conversations")[1]["items"] if i["id"] == r["conversation_id"])
        self.assertEqual((item["reviewer_pre_tier"], item["reviewer_post_tier"], item["reviewer_ok"]),
                         ("green", "amber", True))
        self.assertEqual(item["reviewer_reasons"], ["Reviewer: Mentions changing or stopping a medicine dose."])
        self.assertTrue(any("reviewer" in e["details"].get("to", "") for e in self.app.audit.read(30)
                            if e["event"] == "model_call"))
        self.assertTrue(self.app.db.verify_conversations()[0])

    def test_network_shows_reviewer_without_patient_data(self):
        self.login("dr_lee").call("/api/chat", {"message": "Summarise", "patient_id": "syn-004"})
        st, n = self.login("net_ops").call("/api/network")
        self.assertEqual(st, 200)
        ids = [x["id"] for x in n["nodes"]]
        self.assertLess(ids.index("reviewer"), ids.index("ollama"))
        node = n["nodes"][ids.index("reviewer")]
        self.assertEqual((node["label"], node["kind"], node["status"]), ("Reviewer (Nemotron)", "model", "up"))
        self.assertTrue(node["address"].endswith("· nemotron-mini"))
        edge = next(e for e in n["edges"] if e["to"] == "reviewer")
        self.assertEqual((edge["from"], edge["protocol"]), ("app", "HTTP over loopback (Ollama API)"))
        self.assertGreater(edge["calls_24h"], 0)
        body = json.dumps(n)
        self.assertNotIn("syn-", body)
        for p in self.app.ehr.patients.values():
            self.assertNotIn(p["name"]["family"], body)


class ChainMigration(unittest.TestCase):
    def test_old_and_new_rows_verify(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            path = tmp / "clinic.db"
            raw = sqlite3.connect(str(path))
            raw.executescript(dbmod.SCHEMA)  # the 2.5 table, without the reviewer columns
            old = {k: None for k in dbmod.CONV_HASHED}
            old.update(id="old1", at="2026-11-20T10:00:00Z", user="dr_lee", role="clinician", kind="chat",
                       question="q", answer="a", tier="green", reasons="[]", duration_ms=5, change_seq=0)
            raw.execute(f"INSERT INTO conversations ({', '.join(dbmod.CONV_HASHED)}, prev_hash, hash) VALUES "
                        f"({', '.join('?' * (len(dbmod.CONV_HASHED) + 2))})",
                        (*(old[k] for k in dbmod.CONV_HASHED), dbmod.GENESIS,
                         dbmod._digest(dbmod.GENESIS, old, dbmod.CONV_HASHED)))
            raw.commit(); raw.close()
            db = dbmod.ClinicDB(path)  # adds the new columns
            db.log_conversation({"id": "new1", "user": "dr_lee", "role": "clinician", "kind": "chat", "tier": "amber",
                                 "reviewer_pre_tier": "green", "reviewer_post_tier": "amber",
                                 "reviewer_reasons": ["Reviewer: x"], "reviewer_ok": True})
            self.assertEqual(db.verify_conversations(), (True, 2, None))
            items = db.conversations()
            self.assertEqual([i["id"] for i in items], ["new1", "old1"])
            self.assertIsNone(items[1]["reviewer_ok"])
            raw = sqlite3.connect(str(path))
            raw.execute("DROP TRIGGER conversations_no_update")
            raw.execute("UPDATE conversations SET reviewer_post_tier = 'green' WHERE id = 'new1'")
            raw.commit(); raw.close()
            self.assertEqual(db.verify_conversations(), (False, 1, 2))
            db.close()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
