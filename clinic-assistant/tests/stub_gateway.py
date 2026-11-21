"""Stub Leash gateway for tests (C12.7). Standard library only; loopback, ephemeral port."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

_PT = {"resourceType": "Patient", "name": [{"given": ["Ana"], "family": "Stubson"}], "telecom": []}


def _reasoner(risk, action, rules):
    return {"served_by": "fallback:template", "model": "", "latency_ms": 0.1, "risk_level": risk,
            "explanation": "STUB-EXPLANATION Leash blocked this call.", "policy_rule_ids": rules,
            "recommended_action": action, "advisory": True, "error": ""}


def _decision(mode, req):
    args = req.get("args") or {}
    d = {"call_id": req.get("call_id"), "session_id": req.get("session_id"), "tool": req.get("tool"),
         "seq": 1, "scores": {"injection": None, "anomaly": None},
         "latency_ms": {"policy": 0.01, "total": 0.1}, "audit_hash": "stub",
         "ts": "2026-11-21T16:30:00.000000Z", "core": "stub", "ml": "stub"}
    nem = {"mode": "replay", "jailbreak": None, "nemoguard": None, "content_safety": None, "reasoner": None}
    if mode == "block":
        d.update(decision="block", result=None, redactions=[], queue_id=None, reasons=[
            {"code": "RESOURCE_NOT_ALLOWED", "stage": "policy", "detail": "resource 'Condition' not allowed"}],
            nemotron=dict(nem, reasoner=_reasoner("high", "deny", ["resources.allowed"])))
    elif mode == "escalate":
        d.update(decision="escalate", result={"status": "pending_approval", "queue_id": "q-0004"},
                 redactions=[], queue_id="q-0004", reasons=[
                     {"code": "RECORD_RATE_EXCEEDED", "stage": "policy",
                      "detail": "11 distinct records in window, max 10"}],
                 nemotron=dict(nem, reasoner=_reasoner("medium", "needs_more_info", ["rate.max_records"])))
    else:  # allow, wrong_call_id
        d.update(decision="allow", reasons=[{"code": "OK", "stage": "policy", "detail": ""}],
                 queue_id=None, nemotron=nem, redactions=[])
        if req.get("tool") == "read_record":
            pid = args.get("patient_id")
            res = {t: [] for t in args.get("resource_types", [])}
            if "Patient" in res:
                res["Patient"] = [dict(_PT, id=pid)]
            d["result"] = {"patient_id": pid, "resources": res}
            d["redactions"] = [{"path": "resources.Patient[0].address", "kind": "FIELD", "source": "policy"}]
        else:
            d["result"] = {"patients": [dict(_PT, id="pt-0001"),
                                        dict(_PT, id="pt-0002", name=[{"given": ["Ben"], "family": "Stubson"}])]}
    if mode == "wrong_call_id":
        d["call_id"] = "0" * 32
    return d


class StubGateway:
    def __init__(self, mode: str = "allow"):
        self.mode = mode
        self.requests = []
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, status, body):
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                self._send(404, b'{"detail":"not found"}')

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(n)
                if self.path != "/v1/tool-call":
                    return self._send(404, b'{"detail":"not found"}')
                req = json.loads(raw.decode("utf-8"))
                outer.requests.append(req)
                mode = outer.mode
                if mode == "http500":
                    return self._send(500, b'{"detail":"stub error"}')
                if mode == "not_json":
                    return self._send(200, b"not json")
                self._send(200, json.dumps(_decision(mode, req)).encode("utf-8"))

        self._srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = "http://127.0.0.1:%d" % self._srv.server_address[1]
        self._stopped = False
        threading.Thread(target=self._srv.serve_forever, daemon=True).start()

    def stop(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        self._srv.shutdown()
        self._srv.server_close()
