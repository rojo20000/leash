"""Reasoner unit tests (C10.6): template table, explain mapping and grounding. No key, no network."""
from pathlib import Path

import jsonschema
import pytest

from leash import nemotron, reasoner

POLICY = str(Path(__file__).resolve().parent.parent / "policies" / "scheduling_assistant.toml")
TABLE = {  # code -> (risk_level, recommended_action)
    "EMAIL_DOMAIN_NOT_ALLOWED": ("critical", "deny"), "INJECTION_DETECTED": ("high", "deny"),
    "CONTENT_SAFETY_FLAGGED": ("high", "deny"), "RESOURCE_NOT_ALLOWED": ("high", "deny"),
    "TOOL_NOT_ALLOWED": ("high", "deny"), "INJECTION_SUSPECTED": ("medium", "needs_more_info"),
    "RECORD_RATE_EXCEEDED": ("medium", "needs_more_info"), "ANOMALY": ("medium", "needs_more_info"),
    "TOOL_REQUIRES_APPROVAL": ("low", "approve"), "EXECUTION_ERROR": ("low", "deny")}


def ctx(codes, decision="block", tool="send_email", args=None):
    reasons = [{"code": c, "stage": "policy", "detail": "d"} for c in codes]
    return reasoner.build_context(tool, args or {"to": ["x@outside-clinic.example"], "subject": "s", "body": "b"},
                                  None, decision, reasons, {"injection": 0.03, "anomaly": 0.7},
                                  {"jailbreak": None, "content_safety": None}, POLICY)


def ok_result(data, served_by="replay"):
    return nemotron.Result(True, served_by, "nvidia/test-model", data, 12.3, 10.0, "")


GOOD = {"risk_level": "critical", "explanation": "The agent tried to email a record outside the clinic; blocked.",
        "policy_rule_ids": ["email.allowed_domains"], "recommended_action": "deny"}


@pytest.mark.parametrize("code", list(TABLE))
def test_template_valid_for_every_code(code):
    t = reasoner.template(ctx([code], decision="escalate" if code in ("ANOMALY", "INJECTION_SUSPECTED") else "block"))
    jsonschema.validate({k: t[k] for k in ("risk_level", "explanation", "policy_rule_ids", "recommended_action")},
                        reasoner.SCHEMA)
    assert (t["risk_level"], t["recommended_action"]) == TABLE[code]
    assert t["policy_rule_ids"] == [reasoner.REASON_TO_RULE[code]]
    assert t["served_by"] == "fallback:template" and t["advisory"] is True and "{" not in t["explanation"]


def test_template_primary_reason_and_rule_ids():
    t = reasoner.template(ctx(["ANOMALY", "EMAIL_DOMAIN_NOT_ALLOWED", "INJECTION_SUSPECTED"]))
    assert t["risk_level"] == "critical" and t["policy_rule_ids"] == [
        "gateway.anomaly", "email.allowed_domains", "gateway.injection"]


def test_explain_maps_ok_result(monkeypatch):
    for served in ("replay", "nemotron"):
        monkeypatch.setattr(nemotron, "chat_json", lambda *a, _s=served, **k: ok_result(dict(GOOD), _s))
        o = reasoner.explain(ctx(["EMAIL_DOMAIN_NOT_ALLOWED"]))
        assert o["served_by"] == served and o["model"] == "nvidia/test-model" and o["error"] == ""
        assert o["risk_level"] == "critical" and o["explanation"] == GOOD["explanation"] and o["advisory"] is True


def test_explain_falls_back_when_not_ok(monkeypatch):
    bad = nemotron.Result(False, "unavailable", "", None, 5.0, None, "timeout")
    monkeypatch.setattr(nemotron, "chat_json", lambda *a, **k: bad)
    o = reasoner.explain(ctx(["EMAIL_DOMAIN_NOT_ALLOWED"]))
    assert o["served_by"] == "fallback:template" and o["error"] == "timeout" and o["model"] == ""


def test_explain_rejects_ungrounded_rule(monkeypatch):
    monkeypatch.setattr(nemotron, "chat_json", lambda *a, **k: ok_result(dict(GOOD, policy_rule_ids=["tools.allowed"])))
    o = reasoner.explain(ctx(["EMAIL_DOMAIN_NOT_ALLOWED"]))
    assert o["served_by"] == "fallback:template" and o["error"] == "ungrounded"
    assert o["policy_rule_ids"] == ["email.allowed_domains"]
    # minimize.fields is always grounded
    monkeypatch.setattr(nemotron, "chat_json",
                        lambda *a, **k: ok_result(dict(GOOD, policy_rule_ids=["minimize.fields"])))
    assert reasoner.explain(ctx(["EMAIL_DOMAIN_NOT_ALLOWED"]))["served_by"] == "replay"


def test_explain_off_mode_uses_template(monkeypatch, tmp_path):
    monkeypatch.setenv("LEASH_NEMOTRON", "off")
    o = reasoner.explain(ctx(["EMAIL_DOMAIN_NOT_ALLOWED"]))
    assert o["served_by"] == "fallback:template" and o["error"] == "mode_off"


def test_context_has_no_ids():
    c = ctx(["EMAIL_DOMAIN_NOT_ALLOWED"])
    assert set(c) == {"role", "task", "tool", "args", "output_excerpt", "decision", "reasons", "signals", "policy",
                      "rule_ids", "triggered_rule_ids", "outcome"}
