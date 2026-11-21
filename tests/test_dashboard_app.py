import json
import shutil
from pathlib import Path

import jsonschema
from streamlit.testing.v1 import AppTest

FX = Path("dashboard/fixtures").resolve()
APP = str(Path("dashboard/app.py").resolve())
RISK = ["low", "medium", "high", "critical"]
RULES = ["tools.allowed", "tools.require_approval", "resources.allowed", "rate.max_records", "email.allowed_domains",
         "minimize.fields", "gateway.injection", "gateway.content_safety", "gateway.anomaly", "gateway.execution"]
SCHEMA = {"type": "object", "additionalProperties": False,
          "required": ["risk_level", "explanation", "policy_rule_ids", "recommended_action"],
          "properties": {"risk_level": {"enum": RISK},
                         "explanation": {"type": "string", "minLength": 40, "maxLength": 600},
                         "policy_rule_ids": {"type": "array", "items": {"enum": RULES}, "minItems": 1,
                                             "maxItems": 4, "uniqueItems": True},
                         "recommended_action": {"enum": ["approve", "deny", "needs_more_info"]}}}
EXTRA = {"served_by", "model", "latency_ms", "advisory", "error"}


def run(monkeypatch, fx):
    monkeypatch.setenv("LEASH_DASHBOARD_FIXTURES", str(fx))
    return AppTest.from_file(APP, default_timeout=30).run()


def text(at):
    parts = [e.value for e in at.text] + [e.value for e in at.caption] + [e.value for e in at.success]
    parts += [e.value for e in at.error] + [e.value for e in at.info] + [e.value for e in at.warning]
    parts += [m.value for m in at.metric] + [df.value.to_string() for df in at.dataframe]
    return "\n".join(str(p) for p in parts)


def test_fixtures_valid():
    for n in ("decisions", "queue", "verify", "metrics", "health"):
        json.loads((FX / f"{n}.json").read_text())
    rzs = [i["reasoner"] for i in json.loads((FX / "queue.json").read_text())["items"]]
    rzs += [d["nemotron"]["reasoner"] for d in json.loads((FX / "decisions.json").read_text())["decisions"]
            if d.get("nemotron") and d["nemotron"]["reasoner"]]
    assert len(rzs) >= 5
    for rz in rzs:
        jsonschema.validate({k: v for k, v in rz.items() if k not in EXTRA}, SCHEMA)
        assert EXTRA <= set(rz)


def test_fixture_mode(monkeypatch):
    at = run(monkeypatch, FX)
    assert not at.exception
    t = text(at)
    assert "FIXTURE MODE" in at.warning[0].value
    assert "EMAIL_DOMAIN_NOT_ALLOWED" in t and "send_email" in t
    assert "chain intact (9 entries)" in t
    q = json.loads((FX / "queue.json").read_text())["items"][0]
    assert q["reasoner"]["explanation"] in t
    assert "critical" in "".join(m.value for m in at.markdown)
    assert "email.allowed_domains" in t
    assert "Advisory only. The decision above comes from fixed policy; you make the final call." in t
    assert "jailbreak: replay" in t and "safety: fallback:local" in t and "reasoner: nemotron" not in t
    assert "reasoner: replay" in t
    m = json.loads((FX / "metrics.json").read_text())
    assert f"{m['latency_ms']['p50']:.2f}" in t and f"{m['latency_ms']['p95']:.2f}" in t
    assert "55.6%" in "".join(str(x.value) for x in at.metric)
    assert "not measured yet" in t
    assert "nemotron-jailbreak-detect" not in json.dumps(m) and "nemotron-content-safety\"" not in json.dumps(m)
    feed = at.dataframe[0].value
    legacy = feed[feed["session"] == "legacy-session"].iloc[0]
    assert legacy["served by"] == "-"
    labels = [b.label for b in at.button]
    assert "Dismiss" in labels and "Confirm block" in labels and "Approve" in labels
    at.button(key="approve-q-0001").click().run()
    assert not at.exception


def test_gateway_unreachable(monkeypatch):
    monkeypatch.delenv("LEASH_DASHBOARD_FIXTURES", raising=False)
    monkeypatch.setenv("LEASH_GATEWAY_URL", "http://127.0.0.1:9")
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    assert at.error and "unreachable" in at.error[0].value


def test_missing_reasoner(monkeypatch, tmp_path):
    shutil.copytree(FX, tmp_path / "fx")
    p = tmp_path / "fx" / "queue.json"
    q = json.loads(p.read_text())
    for i in q["items"]:
        i.pop("reasoner")
    p.write_text(json.dumps(q))
    at = run(monkeypatch, tmp_path / "fx")
    assert not at.exception
    assert any("No explanation available" in i.value for i in at.info)
