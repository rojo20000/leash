"""2.12: the reviewer demo switch and the three attack scenarios."""
import os
import shutil
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

os.environ["MOCK_LLM"] = "1"
from app import privacy  # noqa: E402
from app.server import DEMO_SCENARIOS, App, make_handler  # noqa: E402
from tests.test_smoke import PW, Client  # noqa: E402


class Demo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.app = App(data_dir=cls.tmp)
        cls.app.policy["tiers"]["green_sample_rate"] = 0
        cls.app.policy["server"]["max_requests_per_minute"] = 1000
        for name, role in [("dr_lee", "clinician"), ("lead_ana", "clinical_lead"), ("admin_kai", "admin"),
                           ("auditor_ray", "auditor")]:
            cls.app.users.add(name, PW, role)
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(cls.app))
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.httpd.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.app.db.close(); cls.app.vectors.db.close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def tearDown(self):
        self.app.reviewer.set_demo(True, "test")

    def login(self, user):
        c = Client(self.base)
        self.assertEqual(c.call("/api/login", {"username": user, "password": PW})[0], 200)
        return c

    def test_toggle_permission_audit_and_persistence(self):
        doc, lead = self.login("dr_lee"), self.login("lead_ana")
        st, r = doc.call("/api/reviewer")
        self.assertEqual(st, 200)
        self.assertEqual((r["enabled"], r["state"], r["model"], r["can_toggle"], r["scenarios"]),
                         (True, "on", "nemotron-mini", False, []))
        self.assertEqual(doc.call("/api/reviewer", {"enabled": False})[0], 403)
        self.assertEqual(self.login("auditor_ray").call("/api/reviewer", {"enabled": False})[0], 403)
        self.assertEqual(lead.call("/api/reviewer", {"enabled": "no"})[0], 400)
        st, r = lead.call("/api/reviewer", {"enabled": False})
        self.assertEqual(st, 200)
        self.assertEqual((r["enabled"], r["state"], r["changed_by"]), (False, "off", "lead_ana"))
        self.assertTrue(r["changed_at"])
        self.assertEqual(len(r["scenarios"]), 3)
        e = next(e for e in self.app.audit.read(20) if e["event"] == "reviewer_toggled")
        self.assertEqual((e["user"], e["details"]), ("lead_ana", {"from": "on", "to": "off"}))
        self.assertEqual(doc.call("/api/me")[1]["reviewer"]["state"], "off")
        again = App(data_dir=self.tmp)  # stored in clinic.db, not in policy.json
        self.assertFalse(again.reviewer.status()["enabled"])
        again.db.close(); again.vectors.db.close()
        self.assertEqual(self.login("admin_kai").call("/api/reviewer", {"enabled": True})[1]["state"], "on")

    def test_off_really_skips_the_reviewer(self):
        self.login("lead_ana").call("/api/reviewer", {"enabled": False})
        n = sum(1 for e in self.app.audit.read(500) if e["event"].startswith("reviewer_p"))
        r = self.login("dr_lee").call("/api/chat", {"message": "Summarise", "patient_id": "syn-004"})[1]
        steps = {t["step"]: t for t in r["trace"]}
        self.assertEqual(steps["Reviewer"]["detail"], "switched off for demo by lead_ana")
        self.assertNotIn("Reviewer (before model)", steps)
        self.assertEqual(sum(1 for e in self.app.audit.read(500) if e["event"].startswith("reviewer_p")), n)
        node = self.app.reviewer.network_node()
        self.assertEqual(node["status"], "disabled")

    def test_scenarios_get_past_guardrails(self):
        for sc in DEMO_SCENARIOS:
            masked = privacy.mask(sc["prompt"])[0]
            self.assertEqual(self.app.guard.check_input(masked)["tier"], "green", sc["id"])

    def test_scenarios_off_then_on(self):
        lead = self.login("lead_ana")
        lead.call("/api/reviewer", {"enabled": False})
        for sc in DEMO_SCENARIOS:
            r = lead.call("/api/chat", {"message": sc["prompt"]})[1]
            self.assertEqual(r["tier"], "green", (sc["id"], r.get("reasons")))
            self.assertTrue(any(t["step"] == "Reviewer" and "switched off" in t["detail"] for t in r["trace"]))
        lead.call("/api/reviewer", {"enabled": True})
        for sc in DEMO_SCENARIOS:
            r = lead.call("/api/chat", {"message": sc["prompt"]})[1]
            self.assertIn(r["tier"], ("amber", "red"), sc["id"])
            self.assertTrue(any(x.startswith("Reviewer:") for x in r["reasons"]), r["reasons"])
            pre = next(t for t in r["trace"] if t["step"] == "Reviewer (before model)")
            self.assertIn(pre["status"], ("warn", "blocked"))
        items = lead.call("/api/conversations?limit=6")[1]["items"]
        self.assertEqual([i["reviewer_pre_tier"] for i in items][:3].count(None), 0)
        self.assertEqual([i["reviewer_pre_tier"] for i in items][3:], [None, None, None])


if __name__ == "__main__":
    unittest.main()
