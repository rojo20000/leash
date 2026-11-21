"""Lightning policy reasoner (CONTRACTS.md C10.6).

Design rule: Nemotron output can only add caution, never remove it. The reasoner runs AFTER the decision is final
and is advisory only: its output is never an input to decide, the queue status or the executor.
"""
import copy
import json
import tomllib
from pathlib import Path

import jsonschema

from leash import nemotron

PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "reasoner_system.txt"
TASK = "Process today's new referrals and book follow-ups."

RISK_LEVELS = ["low", "medium", "high", "critical"]
ACTIONS = ["approve", "deny", "needs_more_info"]  # approve/deny = the queue's /approve and /deny endpoints
RULE_IDS = {
    "tools.allowed": "Only the role's listed tools may be called.",
    "tools.require_approval": "These tools always need human approval.",
    "resources.allowed": "Only these FHIR resource types may be read (minimum necessary).",
    "rate.max_records": "At most max_records distinct patients per window_seconds.",
    "email.allowed_domains": "Email may only go to these domains.",
    "minimize.fields": "Only these fields per resource type are returned to the agent.",
    "gateway.injection": "Documents must not carry instructions aimed at the AI.",
    "gateway.content_safety": "Payloads must not disclose identifiers or records beyond the task's need.",
    "gateway.anomaly": "The session's recent behaviour must look like normal scheduling work.",
    "gateway.execution": "The tool call failed to execute.",
}
REASON_TO_RULE = {
    "TOOL_NOT_ALLOWED": "tools.allowed", "TOOL_REQUIRES_APPROVAL": "tools.require_approval",
    "RESOURCE_NOT_ALLOWED": "resources.allowed", "RECORD_RATE_EXCEEDED": "rate.max_records",
    "EMAIL_DOMAIN_NOT_ALLOWED": "email.allowed_domains", "INJECTION_DETECTED": "gateway.injection",
    "INJECTION_SUSPECTED": "gateway.injection", "CONTENT_SAFETY_FLAGGED": "gateway.content_safety",
    "ANOMALY": "gateway.anomaly", "EXECUTION_ERROR": "gateway.execution"}
SCHEMA = {"type": "object", "additionalProperties": False,
          "required": ["risk_level", "explanation", "policy_rule_ids", "recommended_action"],
          "properties": {"risk_level": {"enum": RISK_LEVELS},
                         "explanation": {"type": "string", "minLength": 40, "maxLength": 600},
                         "policy_rule_ids": {"type": "array", "items": {"enum": list(RULE_IDS)}, "minItems": 1,
                                             "maxItems": 4, "uniqueItems": True},
                         "recommended_action": {"enum": ACTIONS}}}

# The API's structured-output grammar rejects "uniqueItems" (HTTP 400), so the wire schema omits it; the full
# SCHEMA is enforced locally on the reply.
WIRE_SCHEMA = copy.deepcopy(SCHEMA)
del WIRE_SCHEMA["properties"]["policy_rule_ids"]["uniqueItems"]

SEVERITY = ["EMAIL_DOMAIN_NOT_ALLOWED", "INJECTION_DETECTED", "CONTENT_SAFETY_FLAGGED", "RESOURCE_NOT_ALLOWED",
            "TOOL_NOT_ALLOWED", "INJECTION_SUSPECTED", "RECORD_RATE_EXCEEDED", "ANOMALY",
            "TOOL_REQUIRES_APPROVAL", "EXECUTION_ERROR"]
# code -> (risk_level, recommended_action, sentence)
TABLE = {
    "EMAIL_DOMAIN_NOT_ALLOWED": ("critical", "deny", "The email was addressed to {recipients}, outside the "
                                 "domains the {role} role may contact, so patient information could leave the clinic."),
    "INJECTION_DETECTED": ("high", "deny", "The document contains text that reads like instructions to the AI "
                           "rather than clinical content (injection score {injection_tfidf})."),
    "CONTENT_SAFETY_FLAGGED": ("high", "deny", "The content check found identifiers or record details beyond "
                               "what scheduling needs ({detail})."),
    "RESOURCE_NOT_ALLOWED": ("high", "deny", "The agent asked for record types the {role} role does not need "
                             "({detail})."),
    "TOOL_NOT_ALLOWED": ("high", "deny", "The {role} role is not allowed to use the {tool} tool."),
    "INJECTION_SUSPECTED": ("medium", "needs_more_info", "A second injection detector flagged this document "
                            "although the main classifier did not; check the document text."),
    "RECORD_RATE_EXCEEDED": ("medium", "needs_more_info", "The agent touched more distinct patients than the "
                             "{role} role allows ({max_records} per {window_seconds} s)."),
    "ANOMALY": ("medium", "needs_more_info", "The session's recent calls do not look like normal scheduling "
                "work (anomaly score {anomaly})."),
    "TOOL_REQUIRES_APPROVAL": ("low", "approve", "This tool always needs a person to approve it."),
    "EXECUTION_ERROR": ("low", "deny", "The tool call failed to run ({detail})."),
}


def _clip(s, n):
    return s if len(s) <= n else s[:n]


def build_context(tool, args, minimized_output, decision, reasons, scores, nemotron_signals, policy_path):
    with open(policy_path, "rb") as f:
        p = tomllib.load(f)
    a = dict(args or {})
    if isinstance(a.get("body"), str):
        a["body"] = a["body"][:1500]
    excerpt = None if minimized_output is None else json.dumps(minimized_output, sort_keys=True)[:1500]
    ns = nemotron_signals or {}
    fmt = lambda v: None if v is None else f"{v:.2f}"  # noqa: E731
    return {"role": p.get("role", "scheduling_assistant"), "task": TASK, "tool": tool, "args": a,
            "output_excerpt": excerpt, "decision": decision,
            "reasons": [{"code": r["code"], "stage": r["stage"], "detail": r.get("detail", "")} for r in reasons],
            "signals": {"injection_tfidf": fmt(scores.get("injection")), "jailbreak": ns.get("jailbreak"),
                        "content_safety": ns.get("content_safety"), "anomaly": fmt(scores.get("anomaly"))},
            "policy": {"allowed_tools": p["tools"]["allowed"], "allowed_resources": p["resources"]["allowed"],
                       "allowed_domains": p["email"]["allowed_domains"], "max_records": p["rate"]["max_records"],
                       "window_seconds": p["rate"]["window_seconds"]},
            "rule_ids": dict(RULE_IDS)}


def _obj(served_by, model, latency_ms, d, error):
    return {"served_by": served_by, "model": model, "latency_ms": round(latency_ms, 1),
            "risk_level": d["risk_level"], "explanation": d["explanation"],
            "policy_rule_ids": d["policy_rule_ids"], "recommended_action": d["recommended_action"],
            "advisory": True, "error": error}


def template(context, *, error=""):
    reasons = context.get("reasons") or []
    codes = [r["code"] for r in reasons if r["code"] in TABLE]
    primary = next((c for c in SEVERITY if c in codes), None)
    rule_ids = []
    for c in codes:
        if REASON_TO_RULE[c] not in rule_ids:
            rule_ids.append(REASON_TO_RULE[c])
    rule_ids = rule_ids[:4] or ["tools.allowed"]
    sig, pol = context.get("signals", {}), context.get("policy", {})
    to = (context.get("args") or {}).get("to") or []
    to = [to] if isinstance(to, str) else to
    detail = next((r.get("detail", "") for r in reasons if r["code"] == primary), "")
    risk, action, sentence = TABLE.get(primary, ("medium", "needs_more_info",
                                                 "This call needs a person to look at it before anything proceeds."))
    sentence = sentence.format(
        recipients=_clip(", ".join(map(str, to)) or "an unknown recipient", 120), role=context.get("role", ""),
        tool=context.get("tool", ""), detail=_clip(detail, 120), injection_tfidf=sig.get("injection_tfidf"),
        anomaly=sig.get("anomaly"), max_records=pol.get("max_records"), window_seconds=pol.get("window_seconds"))
    verb = "blocked" if context.get("decision") == "block" else "held for review"
    text = (f"Leash {verb} this {context.get('tool')} call. {sentence} "
            "The decision comes from fixed policy; a reviewer makes the final call.")
    d = {"risk_level": risk, "explanation": _clip(text, 600), "policy_rule_ids": rule_ids,
         "recommended_action": action}
    return _obj("fallback:template", "", 0.0, d, error)


def explain(context):
    try:
        messages = [{"role": "system", "content": PROMPT_PATH.read_text(encoding="utf-8")},
                    {"role": "user", "content": "Explain this Leash decision for a clinician or compliance "
                                                "reviewer.\n" + json.dumps(context, sort_keys=True)}]
        r = nemotron.chat_json(messages, WIRE_SCHEMA, thinking=False)
        if r.ok:
            try:
                jsonschema.validate(r.data, SCHEMA)
            except jsonschema.ValidationError:
                r = nemotron.Result(False, "unavailable", r.model, None, r.latency_ms, None, "invalid_json")
        if not r.ok:
            t = template(context, error=r.error or "unavailable")
            t["latency_ms"] = round(r.latency_ms, 1)
            return t
        allowed = {REASON_TO_RULE[x["code"]] for x in context.get("reasons", []) if x["code"] in REASON_TO_RULE}
        allowed.add("minimize.fields")
        if not set(r.data["policy_rule_ids"]) <= allowed:
            t = template(context, error="ungrounded")
            t["latency_ms"] = round(r.latency_ms, 1)
            return t
        return _obj(r.served_by, r.model, r.latency_ms, r.data, "")
    except Exception as e:  # noqa: BLE001  explain never raises
        return template(context, error="exception")
