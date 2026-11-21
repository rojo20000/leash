"""Integrated-mode endpoints (C12.4, C12.6) against the stub gateway.  Run:  MOCK_LLM=1 python -m unittest -v"""
import json
import os
import re
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

os.environ["MOCK_LLM"] = "1"
from app.leash_client import FULL_TYPES, SCHEDULING_TYPES  # noqa: E402
from app.server import App, make_handler  # noqa: E402
from tests.stub_gateway import StubGateway  # noqa: E402
from tests.test_smoke import PW, Client  # noqa: E402
from tests.test_vectorstore import _rm_temp  # noqa: E402


class LeashEndpointTests(unittest.TestCase):
    def build(self, leash=None):
        """Temp App (+ server, clients). leash=None keeps the committed policy."""
        d = tempfile.mkdtemp()
        self.addCleanup(_rm_temp, d)  # runs last
        app = App(data_dir=Path(d))
        self.addCleanup(app.vectors.db.close)
        app.policy["server"]["max_requests_per_minute"] = 1000
        if leash is not None:
            app.policy["leash"] = leash
        app.users.add("dr_lee", PW, "clinician")
        app.users.add("auditor_ray", PW, "auditor")
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app))
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        clients = {}
        for u in ("dr_lee", "auditor_ray"):
            c = Client(f"http://127.0.0.1:{httpd.server_port}")
            self.assertEqual(c.call("/api/login", {"username": u, "password": PW})[0], 200)
            clients[u] = c
        return app, clients

    def on(self, mode="allow"):
        gw = StubGateway(mode)
        self.addCleanup(gw.stop)
        app, cl = self.build({"enabled": True, "gateway_url": gw.url, "timeout_seconds": 5,
                              "dashboard_url": "http://127.0.0.1:8501"})
        return gw, app, cl["dr_lee"], cl

    @staticmethod
    def leash_entries(app):
        return [e for e in app.audit.read(1000) if e["event"] == "leash_tool_call"]

    def open(self, c, view="scheduling", pid="pt-0042"):
        return c.call("/api/leash/open", {"patient_id": pid, "view": view})

    def test_allow_open_scheduling(self):
        gw, app, c, _ = self.on()
        code, b = self.open(c)
        self.assertEqual((code, b["state"], b["view"], b["patient_id"]), (200, "allow", "scheduling", "pt-0042"))
        self.assertEqual(b["result"]["patient_id"], "pt-0042")
        self.assertEqual(b["redactions"][0]["path"], "resources.Patient[0].address")
        self.assertEqual(b["dashboard_url"], "http://127.0.0.1:8501")
        r = gw.requests[0]
        self.assertEqual((r["role"], r["session_id"], r["tool"]), ("scheduling_assistant", "clinic-assistant:dr_lee",
                                                                  "read_record"))
        self.assertEqual(r["args"]["resource_types"], SCHEDULING_TYPES)
        self.assertRegex(r["call_id"], r"^[0-9a-f]{32}$")

    def test_search_allow_and_audit_count(self):
        gw, app, c, _ = self.on()
        code, b = c.call("/api/leash/search", {"q": " smith "})
        self.assertEqual(code, 200)
        self.assertEqual([p["id"] for p in b["result"]["patients"]], ["pt-0001", "pt-0002"])
        self.assertEqual((b["view"], b["patient_id"]), (None, None))
        self.assertEqual(gw.requests[0]["args"], {"name": "smith"})
        self.assertEqual(self.leash_entries(app)[0]["details"]["results"], 2)

    def test_block_full_chart(self):
        gw, app, c, _ = self.on("block")
        code, b = self.open(c, "full")
        self.assertEqual((code, b["state"], b["result"]), (200, "block", None))
        self.assertEqual(gw.requests[0]["args"]["resource_types"], FULL_TYPES)
        self.assertEqual(b["reasons"][0]["code"], "RESOURCE_NOT_ALLOWED")
        self.assertTrue(b["reasoner"]["explanation"].startswith("STUB-EXPLANATION"))
        self.assertEqual(b["reasoner"]["recommended_action"], "deny")

    def test_escalate(self):
        _, _, c, _ = self.on("escalate")
        code, b = self.open(c)
        self.assertEqual((code, b["state"], b["queue_id"]), (200, "escalate", "q-0004"))
        self.assertTrue(b["dashboard_url"])

    def test_unavailable(self):
        gw, app, c, _ = self.on()
        gw.stop()
        code, b = self.open(c)
        self.assertEqual((code, b["state"]), (502, "unavailable"))
        self.assertTrue(b["error"].startswith("Leash gateway unavailable"))
        self.assertNotIn("syn-", json.dumps(b))
        gw2, app2, c2, _ = self.on("http500")
        code, b = self.open(c2)
        self.assertEqual((code, b["state"]), (502, "unavailable"))
        self.assertNotIn("syn-", json.dumps(b))
        self.assertEqual(self.leash_entries(app2)[0]["details"]["error"], "HTTP 500")

    def test_audit_one_entry_per_call(self):
        for mode, reason in (("allow", "OK"), ("block", "RESOURCE_NOT_ALLOWED"),
                             ("escalate", "RECORD_RATE_EXCEEDED"), ("http500", None)):
            with self.subTest(mode=mode):
                gw, app, c, _ = self.on(mode)
                before = len(self.leash_entries(app))
                code, b = self.open(c)
                es = self.leash_entries(app)
                self.assertEqual(len(es), before + 1)
                e = es[0]
                dt = e["details"]
                self.assertEqual(e["user"], "dr_lee")
                self.assertEqual(dt["call_id"], b["call_id"])
                self.assertEqual(dt["decision"], b["state"])
                if reason:
                    self.assertEqual(dt["call_id"], gw.requests[0]["call_id"])
                    self.assertEqual(dt["reasons"], [reason])
                else:
                    self.assertEqual((dt["decision"], dt["reasons"]), ("unavailable", []))
                self.assertEqual(dt["role_sent"], "scheduling_assistant")
                self.assertEqual(dt["session_id"], "clinic-assistant:dr_lee")
                text = json.dumps(e)
                self.assertNotIn("STUB-EXPLANATION", text)
                self.assertNotIn("Stubson", text)

    def test_off_by_default(self):
        gw = StubGateway()
        self.addCleanup(gw.stop)
        with mock.patch.dict(os.environ):
            os.environ.pop("CLINIC_LEASH", None)
            app, cl = self.build()
            c = cl["dr_lee"]
            self.assertEqual(c.call("/api/leash/search", {"q": "smith"}), (404, {"error": "Integrated mode is off."}))
            self.assertEqual(self.open(c)[0], 404)
            self.assertIs(c.call("/api/me")[1]["leash"]["enabled"], False)
        self.assertEqual(gw.requests, [])
        self.assertEqual(self.leash_entries(app), [])

    def test_me_when_on(self):
        _, _, c, _ = self.on()
        self.assertEqual(c.call("/api/me")[1]["leash"], {"enabled": True, "dashboard_url": "http://127.0.0.1:8501"})

    def test_rejections_send_nothing(self):
        gw, app, c, cl = self.on()
        a = cl["auditor_ray"]
        self.assertEqual(a.call("/api/leash/search", {"q": "x"})[0], 403)
        self.assertEqual(self.open(a)[0], 403)
        for pid in ("syn-003", "pt-1", "pt-12345", ""):
            self.assertEqual(self.open(c, pid=pid)[0], 400)
        self.assertEqual(self.open(c, view="all")[0], 400)
        self.assertEqual(c.call("/api/leash/search", {"q": "  "})[0], 400)
        self.assertEqual(c.call("/api/leash/search", {"q": "x" * 81})[0], 400)
        self.assertEqual(c.call("/api/leash/search", {})[0], 400)
        self.assertEqual(gw.requests, [])
        self.assertEqual(self.leash_entries(app), [])

    @unittest.skipUnless(os.environ.get("LEASH_GATEWAY_LIVE") == "1", "needs the running Leash gateway")
    def test_live_gateway(self):
        app, cl = self.build({"enabled": True, "gateway_url": "http://127.0.0.1:8000", "timeout_seconds": 20,
                              "dashboard_url": "http://127.0.0.1:8501"})
        c = cl["dr_lee"]
        code, b = self.open(c, "full", "pt-0001")
        self.assertEqual((code, b["state"]), (200, "block"))
        self.assertIn("RESOURCE_NOT_ALLOWED", [r["code"] for r in b["reasons"]])
        self.assertTrue(b["reasoner"]["explanation"])
        self.assertEqual(self.open(c, "scheduling", "pt-0001")[1]["state"], "allow")


if __name__ == "__main__":
    unittest.main()
