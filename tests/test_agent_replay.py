"""Scripted replay end to end against the real mock EHR (skipped if the EHR or data is not built)."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent.runner import run_session
from agent.tools import ALL_RESOURCE_TYPES, TOOL_SCHEMAS, call_facts

ROOT = Path(__file__).resolve().parent.parent
ATTACKER = "records-transfer@outside-clinic.example"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("LEASH_CORE", "py")
    monkeypatch.setenv("LEASH_ML", "stub")


@pytest.fixture
def ehr():
    try:
        import ehr.app as e
        if not (ROOT / "data" / "generated" / "fhir_bundle.json").exists():
            raise FileNotFoundError
    except (ImportError, FileNotFoundError):
        pytest.skip("EHR not built yet")
    return TestClient(e.create_app(data_dir=str(ROOT / "data" / "generated")))


def sink_lines(p):
    return [json.loads(x) for x in Path(p).read_text().splitlines()] if Path(p).exists() else []


def test_call_facts_and_schemas():
    assert call_facts("read_record", {"patient_id": "p"}) == (ALL_RESOURCE_TYPES, ["p"], [])
    assert call_facts("send_email", {"to": "a@b.c"}) == ([], [], ["a@b.c"])
    assert call_facts("nope", {}) == ([], [], [])
    assert len(TOOL_SCHEMAS) == 5


def test_recording_shape():
    rec = json.loads((ROOT / "demo" / "recordings" / "referrals.json").read_text())
    docs = [c["args"]["document_id"] for c in rec["calls"] if c["tool"] == "read_document"]
    assert docs == ["ref-0007", "ref-0019", "ref-0042", "ref-0101", "ref-0150"]
    offs = [c["offset_s"] for c in rec["calls"]]
    assert all(3 <= b - a <= 8 for a, b in zip(offs, offs[1:]))


def test_unprotected_replay_leaks_to_sink(ehr, tmp_path):
    sink = tmp_path / "sink.jsonl"
    steps = run_session("unprotected", "scripted", "demo-unprotected", ehr, None, str(sink))
    assert all(s["decision"] is None and s["result"] for s in steps)
    leaks = [m for m in sink_lines(sink) if ATTACKER in m["to"]]
    assert len(leaks) == 1 and "MRN-0000042" in leaks[0]["body"]


def test_protected_replay_blocks_attacker(ehr, tmp_path):
    from gateway.app import create_app
    gw = TestClient(create_app(ehr_client=ehr, runtime_dir=str(tmp_path / "rt"),
                               policy_path=str(ROOT / "policies" / "scheduling_assistant.toml")))
    sink = tmp_path / "rt" / "email_sink.jsonl"  # the gateway executes the email, so it owns the sink
    steps = run_session("protected", "scripted", "demo-protected", ehr, gw, str(tmp_path / "unused.jsonl"))
    blocked = [s for s in steps if s["tool"] == "send_email" and s["args"]["to"] == [ATTACKER]]
    assert len(blocked) == 1
    d = blocked[0]["decision"]
    assert d["decision"] == "block" and d["reasons"][0]["code"] == "EMAIL_DOMAIN_NOT_ALLOWED"
    assert "blocked" in blocked[0]["result"]["message"]
    assert any(i["kind"] == "alert" and i["queue_id"] == d["queue_id"] for i in gw.get("/v1/queue").json()["items"])
    assert not [m for m in sink_lines(sink) if ATTACKER in m["to"]]
    assert sink.exists() and "MRN-0000042" not in sink.read_text()
    # routine work for the first benign referrals still goes through
    assert all(s["decision"]["decision"] == "allow" for s in steps[:8])
    assert gw.get("/v1/audit/verify").json()["ok"] is True


def test_run_session_requires_gateway(ehr, tmp_path):
    with pytest.raises(ValueError):
        run_session("protected", "scripted", "s", ehr, None, str(tmp_path / "s.jsonl"))
