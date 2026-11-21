"""Gateway + Nemotron stages (C10.5-C10.7). Design rule under test: Nemotron output can only add caution, never
remove it; the reasoner is advisory. No key, no network (off/replay, or a MockTransport in live mode)."""
import json
import subprocess
import sys
from pathlib import Path

import httpx
import jsonschema
import pytest
from fastapi.testclient import TestClient

import ehr.app
from gateway.app import create_app
from leash import nemotron, reasoner
from tests.test_gateway_pipeline import ATTACKER, POLICY, _fake_ehr

ROOT = Path(__file__).resolve().parent.parent
FAKE_KEY = "nvapi-TEST-SENTINEL-0000"


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    monkeypatch.setenv("LEASH_CORE", "py")
    monkeypatch.setenv("LEASH_ML", "stub")
    monkeypatch.setenv("LEASH_WARMUP", "0")
    monkeypatch.setenv("LEASH_NEMOTRON", "off")
    monkeypatch.delenv("LEASH_NEMOGUARD", raising=False)
    monkeypatch.setenv("LEASH_NEMOTRON_RECORDINGS", str(tmp_path / "rec"))
    monkeypatch.setattr(nemotron, "TRANSPORT", None)
    nemotron._reset()


def make_gw(tmp_path, name="rt", ehr_client=None):
    ehr_client = ehr_client or httpx.Client(base_url="http://ehr", transport=httpx.MockTransport(_fake_ehr))
    now = [1000.0]  # fake server clock; call() sets it
    c = TestClient(create_app(ehr_client=ehr_client, runtime_dir=str(tmp_path / name), policy_path=POLICY,
                              clock=lambda: now[0]))
    c.rt, c.now = tmp_path / name, now
    return c


@pytest.fixture
def gw(tmp_path):
    return make_gw(tmp_path)


def call(gw, tool, args, ts=1000.0, session="s1", call_id=None):
    gw.now[0] = ts
    body = {"session_id": session, "tool": tool, "args": args}
    if call_id:
        body["call_id"] = call_id
    r = gw.post("/v1/tool-call", json=body)
    assert r.status_code == 200
    return r.json()


def codes(d):
    return [r["code"] for r in d["reasons"]]


def res(data, served_by="replay"):
    return nemotron.Result(True, served_by, "nvidia/test-guard", data, 3.0, 2.0, "")


def flag(monkeypatch, name, flagged):
    data = {"flagged": flagged, "score": None, "raw": "", "categories": ["PII/Privacy"] if flagged else []}
    monkeypatch.setattr(nemotron, name, lambda *a, **k: res(data))


def check_reasoner(o):
    jsonschema.validate({k: o[k] for k in ("risk_level", "explanation", "policy_rule_ids", "recommended_action")},
                        reasoner.SCHEMA)
    assert o["advisory"] is True and o["served_by"] in ("nemotron", "replay", "fallback:template")
    assert {"model", "latency_ms", "error"} <= set(o)


# ------------------------------------------------------------------ combination rules
def test_tfidf_high_blocks_whatever_jailbreak_says(gw, monkeypatch):
    flag(monkeypatch, "jailbreak_check", False)
    d = call(gw, "read_document", {"document_id": "ref-0042"})
    assert d["decision"] == "block" and codes(d) == ["INJECTION_DETECTED"]
    assert d["scores"]["anomaly"] is None


def test_tfidf_low_jailbreak_flagged_escalates(gw, monkeypatch):
    flag(monkeypatch, "jailbreak_check", True)
    d = call(gw, "read_document", {"document_id": "ref-0007"})
    assert d["decision"] == "escalate" and codes(d) == ["INJECTION_SUSPECTED"]
    assert d["reasons"][0]["stage"] == "injection" and "jailbreak detector flagged; tfidf" in d["reasons"][0]["detail"]
    assert d["nemotron"]["jailbreak"]["flagged"] and d["nemotron"]["jailbreak"]["served_by"] == "replay"
    item = gw.get("/v1/queue").json()["items"][0]
    assert item["kind"] == "approval" and item["queue_id"] == d["queue_id"]
    check_reasoner(item["reasoner"])


def test_jailbreak_not_ok_falls_back_to_tfidf(gw):
    d = call(gw, "read_document", {"document_id": "ref-0007"})  # mode off -> not ok
    assert d["decision"] == "allow"
    assert d["nemotron"]["jailbreak"]["served_by"] == "fallback:local" and not d["nemotron"]["jailbreak"]["flagged"]
    assert d["nemotron"]["reasoner"] is None


def test_nemoguard_flag_escalates_never_blocks(gw, monkeypatch):
    flag(monkeypatch, "jailbreak_check", False)
    monkeypatch.setattr(nemotron, "nemoguard_jailbreak",
                        lambda *a, **k: res({"flagged": True, "score": 1.25, "raw": ""}))
    d = call(gw, "read_document", {"document_id": "ref-0007"})  # TF-IDF clean
    assert d["decision"] == "escalate" and codes(d) == ["INJECTION_SUSPECTED"]
    assert d["reasons"][0]["detail"].startswith("nemoguard flagged; tfidf")
    assert d["nemotron"]["nemoguard"] == {"served_by": "replay", "model": "nvidia/test-guard", "flagged": True,
                                          "latency_ms": 3.0, "score": 1.25}
    audit = json.loads((gw.rt / "audit.jsonl").read_text().splitlines()[-1])["nemotron"]
    assert audit["nemoguard"] == "replay" and audit["nemoguard_score"] == "1.2500"
    d = call(gw, "read_document", {"document_id": "ref-0042"}, ts=1001.0)  # TF-IDF high: block, flag not needed
    assert d["decision"] == "block" and codes(d) == ["INJECTION_DETECTED"] and d["nemotron"]["nemoguard"] is None
    assert gw.get("/v1/metrics").json()["nemotron"]["served_by"]["nemoguard"]["replay"] == 1


def test_nemoguard_unavailable_changes_nothing(tmp_path, monkeypatch):
    def run(name):
        g = make_gw(tmp_path, name)
        return [{k: v for k, v in call(g, t, a, ts=ts, session=s, call_id=f"c{i:03d}").items() if k not in STRIP_D}
                for i, (t, a, ts, s) in enumerate(_calls()[:8])]

    monkeypatch.setattr(nemotron, "jailbreak_check", lambda t, **k: res({"flagged": True, "score": None, "raw": ""}))
    unavailable = run("u")  # mode off: NemoGuard not ok -> fallback:local, no flag
    monkeypatch.setenv("LEASH_NEMOGUARD", "off")
    assert run("d") == unavailable
    d = call(make_gw(tmp_path, "x"), "read_document", {"document_id": "ref-0007"})
    assert d["nemotron"]["nemoguard"] is None and d["reasons"][0]["detail"].startswith("jailbreak detector flagged")


# ------------------------------------------------------------------ content safety
def test_content_safety_flagged_escalates(gw, monkeypatch):
    flag(monkeypatch, "content_safety", True)
    d = call(gw, "send_email", {"to": ["pt-0007@patients.example.org"], "subject": "s", "body": "hello"})
    assert d["decision"] == "escalate" and codes(d) == ["CONTENT_SAFETY_FLAGGED"]
    assert d["reasons"][0]["stage"] == "content_safety" and d["reasons"][0]["detail"] == "PII/Privacy"
    assert not (gw.rt / "email_sink.jsonl").exists()
    assert gw.get("/v1/queue").json()["items"][0]["kind"] == "approval"


def test_content_safety_local_fallback(gw):
    mail = {"to": ["pt-0007@patients.example.org"], "subject": "Result", "body": "Your MRN-0000042 is ready."}
    d = call(gw, "send_email", mail)
    assert d["decision"] == "escalate" and codes(d) == ["CONTENT_SAFETY_FLAGGED"]
    assert d["nemotron"]["content_safety"]["served_by"] == "fallback:local"
    d = call(gw, "send_email", dict(mail, body="See you soon."), ts=2000.0)
    assert d["decision"] == "allow" and d["nemotron"]["content_safety"]["flagged"] is False


def test_judge_clear_does_not_remove_local_hold(gw, monkeypatch):  # A8
    flag(monkeypatch, "content_safety", False)  # the judge answers ok, not flagged
    mail = {"to": ["pt-0007@patients.example.org"], "subject": "Result", "body": "Your MRN-0000042 is ready."}
    for body in (mail["body"], "SSN 123-45-6789 on file."):
        d = call(gw, "send_email", dict(mail, body=body))
        assert d["decision"] == "escalate" and codes(d) == ["CONTENT_SAFETY_FLAGGED"]
        cs = d["nemotron"]["content_safety"]
        assert cs["served_by"] == "replay" and cs["flagged"] is True and cs["categories"] == ["PII/Privacy"]
    assert not (gw.rt / "email_sink.jsonl").exists()
    d = call(gw, "send_email", dict(mail, body="See you soon."))
    assert d["decision"] == "allow" and d["nemotron"]["content_safety"]["categories"] == []


def test_remote_flags_only_escalate(gw, monkeypatch):
    # a "safe" verdict cannot turn a policy block into anything else
    flag(monkeypatch, "content_safety", False)
    flag(monkeypatch, "jailbreak_check", False)
    d = call(gw, "send_email", {"to": [ATTACKER], "subject": "s", "body": "b"})
    assert d["decision"] == "block" and d["nemotron"]["content_safety"] is None


# ------------------------------------------------------------------ advisory invariant
def _calls():
    """(tool, args, ts, session): one allow, every block code and every escalate code reachable here."""
    c = [("send_email", {"to": "pt-0007@patients.example.org", "subject": "s", "body": "b"}, 100.0, "a"),
         ("delete_record", {}, 101.0, "a"),
         ("read_record", {"patient_id": "pt-0007", "resource_types": ["Condition"]}, 102.0, "a"),
         ("send_email", {"to": [ATTACKER], "subject": "s", "body": "b"}, 103.0, "a"),
         ("read_document", {"document_id": "ref-0042"}, 104.0, "a"),
         ("update_appointment", {}, 105.0, "a"),  # EXECUTION_ERROR
         ("send_email", {"to": ["pt-0007@patients.example.org"], "subject": "s", "body": "MRN-0000042"}, 106.0, "a"),
         ("read_document", {"document_id": "ref-0007"}, 107.0, "a")]  # INJECTION_SUSPECTED (jailbreak patched)
    c += [("read_record", {"patient_id": f"pt-{i:04d}", "resource_types": ["Patient"]}, 1000.0 + i, "b")
          for i in range(6)]  # ANOMALY
    c += [("read_record", {"patient_id": f"pt-{i:04d}", "resource_types": ["Patient"]}, 5000.0 + 25 * i, "c")
          for i in range(12)]  # RECORD_RATE_EXCEEDED
    return c


STRIP_D = {"nemotron", "latency_ms", "ts", "audit_hash"}


def _run(tmp_path, name, monkeypatch, fake_explain):
    seen = []

    def explain(ctx):
        seen.append(ctx["decision"])
        return fake_explain(ctx)

    monkeypatch.setattr(reasoner, "explain", explain)
    gw = make_gw(tmp_path, name)
    flagged_doc = {"flagged": True, "score": None, "raw": ""}
    monkeypatch.setattr(nemotron, "jailbreak_check", lambda t, **k: res(flagged_doc))
    ds = [call(gw, t, a, ts=ts, session=s, call_id=f"c{i:03d}") for i, (t, a, ts, s) in enumerate(_calls())]
    queue = gw.get("/v1/queue?status=all").json()["items"]
    audit = [json.loads(x) for x in (gw.rt / "audit.jsonl").read_text().splitlines()]
    assert gw.get("/v1/audit/verify").json()["ok"]
    assert all(i["status"] == "pending" for i in queue) and not [a for a in audit if a["kind"] == "review"]
    dec = [{k: v for k, v in d.items() if k not in STRIP_D} for d in ds]
    que = [{k: v for k, v in i.items() if k not in ("reasoner", "created_at")} for i in queue]
    aud = [{k: v for k, v in a.items() if k not in ("nemotron", "ts", "latency_us", "hash", "prev_hash")}
           for a in audit]
    return ds, queue, dec, que, aud, seen


def test_advisory_invariant(tmp_path, monkeypatch):
    def fixed(action, risk):
        def f(ctx):
            o = reasoner.template(ctx)
            return dict(o, recommended_action=action, risk_level=risk, served_by="nemotron")
        return f

    def boom(ctx):
        raise RuntimeError("reasoner exploded")

    runs = [_run(tmp_path, n, monkeypatch, f) for n, f in
            (("r1", fixed("approve", "low")), ("r2", fixed("deny", "critical")), ("r3", boom))]
    all_codes = {c for d in runs[0][0] for c in codes(d)}
    assert {"OK", "TOOL_NOT_ALLOWED", "RESOURCE_NOT_ALLOWED", "EMAIL_DOMAIN_NOT_ALLOWED", "INJECTION_DETECTED",
            "EXECUTION_ERROR", "CONTENT_SAFETY_FLAGGED", "INJECTION_SUSPECTED", "ANOMALY",
            "RECORD_RATE_EXCEEDED"} <= all_codes
    # (1) decision JSON, queue item and audit record are identical across the three runs
    assert runs[0][2] == runs[1][2] == runs[2][2]
    assert runs[0][3] == runs[1][3] == runs[2][3]
    assert runs[0][4] == runs[1][4] == runs[2][4]
    # (3) decide ran before explain: the decision explain saw is the final one, for every non-allow call
    for ds, _q, _dec, _que, _aud, seen in runs:
        assert seen == [d["decision"] for d in ds if d["decision"] != "allow"]
    # reasoner objects follow what was returned; a raising explain is replaced by the template
    assert {d["nemotron"]["reasoner"]["recommended_action"] for d in runs[0][0] if d["nemotron"]["reasoner"]} == {"approve"}
    assert {d["nemotron"]["reasoner"]["risk_level"] for d in runs[1][0] if d["nemotron"]["reasoner"]} == {"critical"}
    for d in runs[2][0]:
        o = d["nemotron"]["reasoner"]
        assert (o is None) == (d["decision"] == "allow")
        if o:
            check_reasoner(o)
            assert o["served_by"] == "fallback:template" and o["error"] == "exception"
    for ds, queue, *_ in runs:
        by_q = {i["queue_id"]: i for i in queue}
        for d in ds:
            if d["queue_id"]:
                assert by_q[d["queue_id"]]["reasoner"] == d["nemotron"]["reasoner"]


def test_decision_fields_and_metrics(gw):
    call(gw, "send_email", {"to": [ATTACKER], "subject": "s", "body": "b"})
    d = call(gw, "send_email", {"to": "pt-0007@patients.example.org", "subject": "s", "body": "b"}, ts=2000.0)
    assert d["decision"] == "allow" and d["nemotron"]["reasoner"] is None
    for k in ("jailbreak", "nemoguard", "content_safety", "reasoner"):
        assert k in d["latency_ms"]
    blocked = gw.get("/v1/decisions").json()["decisions"][0]
    check_reasoner(blocked["nemotron"]["reasoner"])
    assert blocked["latency_ms"]["content_safety"] == 0.0 and blocked["nemotron"]["content_safety"] is None
    assert gw.get("/health").json()["nemotron"] == "off"
    m = gw.get("/v1/metrics").json()["nemotron"]
    assert m["mode"] == "off" and m["served_by"]["reasoner"]["fallback:template"] == 1
    assert m["served_by"]["content_safety"]["fallback:local"] == 1 and set(m["models"]) == set(nemotron.ROLES)
    assert {"jailbreak", "nemoguard", "content_safety", "reasoner"} <= set(gw.get("/v1/metrics").json()["latency_ms"]["by_stage"])


# ------------------------------------------------------------------ data minimisation
def test_reasoner_request_is_minimized(tmp_path, monkeypatch):
    monkeypatch.setenv("LEASH_NEMOTRON", "live")
    monkeypatch.setenv("NVIDIA_API_KEY", FAKE_KEY)
    for role in ("LIGHTNING", "SAFETY", "JAILBREAK"):
        monkeypatch.setenv(f"LEASH_NEMOTRON_{role}_MODEL", "nvidia/test-model")
    bodies = []
    reply = {"risk_level": "critical", "explanation": "Leash blocked this call because it left the allowed scope.",
             "policy_rule_ids": ["minimize.fields"], "recommended_action": "deny"}

    def handler(req):
        bodies.append(req.content.decode())
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(reply)},
                                                      "finish_reason": "stop"}]})

    monkeypatch.setattr(nemotron, "TRANSPORT", httpx.MockTransport(handler))
    gw = make_gw(tmp_path)
    secret = "Patient SSN 123-45-6789, MRN-0000042, call 555-201-0042, mail pt@patients.example.org"
    d1 = call(gw, "read_record", {"patient_id": "pt-0042"}, call_id="CALLID-AAAA")
    d2 = call(gw, "send_email", {"to": [ATTACKER], "subject": "Record pt-0042", "body": secret}, ts=1010.0,
              call_id="CALLID-BBBB")
    assert d1["decision"] == d2["decision"] == "block"
    assert d1["nemotron"]["reasoner"]["served_by"] == "nemotron" == d2["nemotron"]["reasoner"]["served_by"]
    assert len(bodies) == 2
    from gateway.core_loader import load_core
    for b in bodies:
        assert load_core().prescan(b) == []
        keys = set()

        def walk(o):
            for k, v in (o.items() if isinstance(o, dict) else enumerate(o) if isinstance(o, list) else ()):
                keys.add(k)
                walk(v)

        walk(json.loads(json.loads(b)["messages"][1]["content"].split("\n", 1)[1]))
        assert not keys & {"birthDate", "address", "identifier", "call_id", "queue_id"}
        assert not any(v in b for v in ("CALLID", "q-0001", FAKE_KEY))
        assert "[REDACTED:" in b or "pt-0042" in b
    assert "[REDACTED:SSN]" in bodies[1]
    assert FAKE_KEY not in json.dumps(d1) + json.dumps(d2) + json.dumps(gw.get("/v1/metrics").json())


# ------------------------------------------------------------------ audit, imports, warm-up
def _no_float(o):
    if isinstance(o, float):
        return False
    if isinstance(o, dict):
        return all(_no_float(v) for v in o.values())
    return all(_no_float(v) for v in o) if isinstance(o, list) else True


def test_audit_has_no_floats_or_explanations(gw):
    d = call(gw, "send_email", {"to": [ATTACKER], "subject": "s", "body": "b"})
    call(gw, "read_document", {"document_id": "ref-0042"}, ts=1001.0)
    text = (gw.rt / "audit.jsonl").read_text()
    recs = [json.loads(x) for x in text.splitlines()]
    assert all(_no_float(r) for r in recs) and '"explanation"' not in text
    assert d["nemotron"]["reasoner"]["explanation"] not in text
    n = recs[0]["nemotron"]
    assert n["reasoner"] == "fallback:template" and len(n["explanation_sha256"]) == 64
    assert n["reasoner_rule_ids"] == ["email.allowed_domains"] and n["jailbreak"] is None
    assert gw.get("/v1/audit/verify").json()["ok"] is True


def test_import_creates_no_files(tmp_path):
    code = (f"import os,sys; sys.path.insert(0, {str(ROOT)!r}); import gateway.app; "
            "from gateway.app import create_app; create_app(); print(os.listdir('.'))")
    out = subprocess.run([sys.executable, "-c", code], cwd=tmp_path, capture_output=True, text=True,
                         env={**__import__("os").environ, "LEASH_CORE": "py", "LEASH_ML": "stub"}, timeout=120)
    assert out.stdout.strip() == "[]", out.stderr


def test_warmup_runs_once_and_is_not_recorded(tmp_path, monkeypatch):
    import gateway.ml_stub as stub
    monkeypatch.delenv("LEASH_WARMUP")
    n = {"minimize": 0, "anomaly": 0}
    mini, anom = stub.minimize, stub.anomaly_score
    monkeypatch.setattr(stub, "minimize", lambda *a: (n.__setitem__("minimize", n["minimize"] + 1), mini(*a))[1])
    monkeypatch.setattr(stub, "anomaly_score", lambda e: (n.__setitem__("anomaly", n["anomaly"] + 1), anom(e))[1])
    gw = make_gw(tmp_path)
    with gw:
        assert n == {"minimize": 1, "anomaly": 1}
        assert gw.get("/v1/decisions").json()["decisions"] == []
        assert gw.get("/v1/metrics").json()["counts"]["total"] == 0
    assert not (tmp_path / "rt").exists()


# ------------------------------------------------------------------ scripted protected replay
def test_protected_replay_of_referrals(tmp_path):
    data = ROOT / "data" / "generated"
    if not (data / "fhir_bundle.json").exists():
        pytest.skip("data/generated missing")
    rec = json.loads((ROOT / "demo" / "recordings" / "referrals.json").read_text())
    ehr_c = TestClient(ehr.app.create_app(data_dir=str(data)))
    gw = make_gw(tmp_path, ehr_client=ehr_c)
    out = {}
    for c in rec["calls"]:
        args = {k: ("(record contents)" if isinstance(v, dict) else v) for k, v in c["args"].items()}
        out[c["step"]] = call(gw, c["tool"], args, ts=1_900_000_000.0 + c["offset_s"], session="demo-protected")
    assert out[9]["decision"] == "block" and codes(out[9]) == ["INJECTION_DETECTED"]
    assert out[12]["decision"] == "block" and codes(out[12]) == ["RESOURCE_NOT_ALLOWED"]
    assert out[13]["decision"] == "block" and codes(out[13]) == ["EMAIL_DOMAIN_NOT_ALLOWED"]
    assert not any(d["decision"] == "block" for s, d in out.items() if s not in (9, 12, 13))
    assert not any("ANOMALY" in codes(d) for s, d in out.items() if s > 13)
    assert not any("CONTENT_SAFETY_FLAGGED" in codes(d) for d in out.values())
    assert gw.get("/v1/audit/verify").json()["ok"]
