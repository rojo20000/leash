import json
import os
import unittest
import urllib.error
import urllib.request
from unittest import mock

os.environ["MOCK_LLM"] = "1"

from app import leash_client as lc  # noqa: E402
from tests.stub_gateway import StubGateway  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
COMMITTED = json.load(open(os.path.join(HERE, "..", "config", "policy.json"), encoding="utf-8"))
CID = "a" * 32
ARGS = {"patient_id": "pt-0042", "resource_types": lc.SCHEDULING_TYPES}


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.gw = StubGateway()
        self.addCleanup(self.gw.stop)
        self.policy = {"leash": {"enabled": True, "gateway_url": self.gw.url, "timeout_seconds": 5}}

    def call(self, tool="read_record", args=ARGS):
        return lc.tool_call(self.policy, tool, args, "clinic-assistant:dr_lee", CID)

    def test_allow_and_exact_body(self):
        d = self.call()
        self.assertEqual(d["decision"], "allow")
        self.assertEqual(d["result"]["patient_id"], "pt-0042")
        self.assertEqual(self.gw.requests[-1], {
            "session_id": "clinic-assistant:dr_lee", "role": "scheduling_assistant",
            "tool": "read_record", "args": ARGS, "call_id": CID})

    def test_block_and_escalate_pass_through(self):
        self.gw.mode = "block"
        d = self.call()
        self.assertEqual(d["decision"], "block")
        self.assertIn("STUB-EXPLANATION", d["nemotron"]["reasoner"]["explanation"])
        self.gw.mode = "escalate"
        d = self.call()
        self.assertEqual((d["decision"], d["queue_id"]), ("escalate", "q-0004"))

    def test_errors(self):
        for mode, msg in (("http500", "HTTP 500"), ("not_json", "bad response"),
                          ("wrong_call_id", "call_id mismatch")):
            self.gw.mode = mode
            with self.assertRaises(lc.LeashError) as cm:
                self.call()
            self.assertEqual(str(cm.exception), msg)
        self.gw.stop()
        with self.assertRaises(lc.LeashError) as cm:
            self.call()
        self.assertTrue(str(cm.exception).startswith("unreachable ("), str(cm.exception))

    def test_loopback_only(self):
        for url in ("http://10.0.0.5:8000", "http://example.org"):
            with self.assertRaises(lc.LeashError) as cm:
                lc.tool_call({"leash": {"gateway_url": url}}, "search_patients", {"name": "x"}, "s", CID)
            self.assertEqual(str(cm.exception), "Refusing non-local Leash gateway")
        self.assertEqual(self.gw.requests, [])

    def test_redirect_is_an_error(self):
        # NoRedirect makes the opener surface a 3xx as HTTPError rather than following it
        req = urllib.request.Request(self.gw.url + "/x")
        h = lc.NoRedirect()
        self.assertIsNone(h.redirect_request(req, None, 302, "Found", {}, "http://example.org/"))

    def test_enabled(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CLINIC_LEASH", None)
            self.assertFalse(lc.enabled(COMMITTED))
            self.assertFalse(lc.enabled({}))
            self.assertTrue(lc.enabled(self.policy))
            os.environ["CLINIC_LEASH"] = "1"
            self.assertTrue(lc.enabled(COMMITTED))

    def test_committed_section(self):
        s = COMMITTED["leash"]
        self.assertIs(s["enabled"], False)
        self.assertEqual(s["gateway_url"], "http://127.0.0.1:8000")
        for k in ("enabled", "gateway_url", "timeout_seconds", "dashboard_url"):
            self.assertIn("_" + k, s)


class StubTests(unittest.TestCase):
    def test_stop_twice_and_404(self):
        gw = StubGateway()
        self.addCleanup(gw.stop)
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(gw.url + "/nope", timeout=5)
        self.assertEqual(cm.exception.code, 404)
        gw.stop()
        gw.stop()


if __name__ == "__main__":
    unittest.main()
