"""Leash gateway (C5, C10): policy -> execute -> injection -> jailbreak + nemoguard -> minimize -> content_safety -> anomaly
-> decide -> reasoner -> audit.

Design rule: Nemotron output can only add caution, never remove it. Detectors may turn an allow into an escalate;
the reasoner runs after the decision is final and never changes decision, reasons, result or queue status."""
import hashlib
import json
import os
import threading
import time
import tomllib
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from agent.tools import ToolExecutor, call_facts
from leash import nemotron, reasoner
from gateway.core_loader import load_core
from gateway.ml_loader import load_ml

READ_TOOLS = {"search_patients", "read_record", "read_document"}
ALERT_CODES = {"EMAIL_DOMAIN_NOT_ALLOWED", "INJECTION_DETECTED"}
HARD_BLOCKS = {"INJECTION_DETECTED", "EXECUTION_ERROR"}
STAGES = ("policy", "execute", "injection", "jailbreak", "nemoguard", "minimize", "content_safety", "anomaly", "reasoner",
          "audit")
SERVED = {"jailbreak": ("nemotron", "replay", "fallback:local"), "nemoguard": ("nemotron", "replay", "fallback:local"),
          "content_safety": ("nemotron", "replay", "fallback:local"),
          "reasoner": ("nemotron", "replay", "fallback:template")}
ROOT = Path(__file__).resolve().parent.parent


class ToolCall(BaseModel):
    session_id: str
    role: str = "scheduling_assistant"
    tool: str
    args: dict = {}
    call_id: Optional[str] = None
    ts: Optional[float] = None


class Review(BaseModel):
    reviewer: str = "reviewer"
    note: str = ""


def _now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def _pct(vals, q):
    if not vals:
        return 0.0
    s = sorted(vals)
    return s[min(len(s) - 1, int(q * len(s)))]


def create_app(ehr_client=None, runtime_dir=None, policy_path=None) -> FastAPI:
    core = load_core()
    ml, ml_name = load_ml()
    rt = Path(runtime_dir or os.environ.get("LEASH_RUNTIME_DIR", "runtime"))  # created on first write
    policy_path = policy_path or os.environ.get("LEASH_POLICY", "policies/scheduling_assistant.toml")
    if not os.path.exists(policy_path):  # importable from any cwd
        policy_path = str(ROOT / policy_path)
    policy = core.Policy.from_toml(policy_path)
    with open(policy_path, "rb") as f:
        keep_fields = tomllib.load(f).get("minimize", {})
    ehr = ehr_client or httpx.Client(base_url=os.environ.get("LEASH_EHR_URL", "http://127.0.0.1:8001"))
    p_audit, p_dec, p_queue, p_sink = (str(rt / n) for n in
                                       ("audit.jsonl", "decisions.jsonl", "queue.json", "email_sink.jsonl"))
    lock = threading.RLock()
    S = {"audit": core.AuditLog(p_audit) if os.path.exists(p_audit) else None, "decisions": [], "queue": [], "history": {}}
    if os.path.exists(p_dec):
        with open(p_dec, encoding="utf-8") as f:
            S["decisions"] = [json.loads(line) for line in f if line.strip()]
    if os.path.exists(p_queue):
        with open(p_queue, encoding="utf-8") as f:
            S["queue"] = json.load(f).get("items", [])

    @asynccontextmanager
    async def lifespan(_app):
        if os.environ.get("LEASH_WARMUP", "1") != "0":  # Presidio/spaCy load lazily; nothing here is recorded
            ml.minimize("read_document", {"document_id": "warmup", "patient_id": "pt-0000",
                                          "text": "Call 555-000-0000 re MRN-0000000."}, keep_fields)
            ml.anomaly_score([{"ts": 0.0, "session_id": "warmup", "tool": "search_patients", "patient_ids": [],
                               "resource_types": ["Patient"], "recipients": []}])
        yield

    app = FastAPI(title="Leash gateway", lifespan=lifespan)

    def save_queue():
        rt.mkdir(parents=True, exist_ok=True)
        with open(p_queue, "w", encoding="utf-8") as f:
            json.dump({"items": S["queue"]}, f)

    def get_audit():
        if S["audit"] is None:
            rt.mkdir(parents=True, exist_ok=True)
            S["audit"] = core.AuditLog(p_audit)
        return S["audit"]

    def run_tool(tool, args, session_id):
        return ToolExecutor(ehr, p_sink, "protected", session_id).execute(tool, args)

    def minimized(tool, out):
        return ml.minimize(tool, out, keep_fields) if tool in READ_TOOLS else (out, [])

    @app.get("/health")
    def health():
        return {"status": "ok", "core": core.IMPLEMENTATION, "ml": ml_name, "nemotron": nemotron.mode()}

    @app.post("/v1/tool-call")
    def tool_call(req: ToolCall):
        with lock:
            return _tool_call(req)

    def _tool_call(req):
        lat = {k: 0.0 for k in STAGES}
        t_start = time.perf_counter()
        call_id = req.call_id or uuid.uuid4().hex
        ts = req.ts if req.ts is not None else time.time()
        tool, args = req.tool, req.args
        reasons, scores, redactions, output = [], {"injection": None, "anomaly": None}, [], None
        nem = {"mode": nemotron.mode(), "jailbreak": None, "nemoguard": None, "content_safety": None, "reasoner": None}
        signals = {"jailbreak": None, "nemoguard": None, "content_safety": None}

        def mark(stage, t0):
            lat[stage] += (time.perf_counter() - t0) * 1000

        def add(code, stage, detail=""):
            reasons.append({"code": code, "stage": stage, "detail": detail})

        # 1 policy
        t0 = time.perf_counter()
        rtypes, pids, recips = call_facts(tool, args)
        pids = [p for p in pids if p]
        dec, code, detail = policy.evaluate(tool, rtypes, pids, recips, ts)
        mark("policy", t0)
        if dec != "allow":
            add(code, "policy", detail)
        policy_blocked = dec == "block"

        # 2 execute (reads only)
        if tool in READ_TOOLS and not policy_blocked:
            t0 = time.perf_counter()
            try:
                output = run_tool(tool, args, req.session_id)
            except Exception as e:
                add("EXECUTION_ERROR", "execute", str(e))
            mark("execute", t0)
        raw = output

        # 3 injection
        if tool == "read_document" and output is not None:
            t0 = time.perf_counter()
            scores["injection"] = float(ml.injection_score(output.get("text", "")))
            if scores["injection"] >= 0.5:
                add("INJECTION_DETECTED", "injection", f"injection score {scores['injection']:.4f}")
            mark("injection", t0)

        # 3b remote detectors (Lightning judge, NemoGuard JailbreakDetect): a model-only signal adds human review,
        # never a hard block; a detector that is not ok is fallback:local and contributes no flag
        if tool == "read_document" and output is not None and not reasons:
            hits = []
            for stage, fn, name in (("jailbreak", nemotron.jailbreak_check, "jailbreak detector"),
                                    ("nemoguard", nemotron.nemoguard_jailbreak, "nemoguard")):
                t0 = time.perf_counter()
                r = fn(output.get("text", ""))
                if r.error == "disabled":  # LEASH_NEMOGUARD=off: the stage is skipped
                    continue
                flagged = bool(r.ok and r.data["flagged"])
                nem[stage] = {"served_by": r.served_by if r.ok else "fallback:local",
                              "model": r.model if r.ok else "", "flagged": flagged,
                              "latency_ms": round(r.latency_ms, 1)}
                if stage == "nemoguard":
                    nem[stage]["score"] = r.data["score"] if r.ok else None
                signals[stage] = "flagged" if flagged else "clear" if r.ok else None
                if flagged:
                    hits.append(name)
                mark(stage, t0)
            if hits:
                add("INJECTION_SUSPECTED", "injection", f"{' + '.join(hits)} flagged; tfidf {scores['injection']:.2f}")

        # 4 minimize
        if output is not None and not any(r["code"] in HARD_BLOCKS for r in reasons):
            t0 = time.perf_counter()
            output, redactions = minimized(tool, output)
            mark("minimize", t0)

        blocked = policy_blocked or any(r["code"] in HARD_BLOCKS for r in reasons)

        # 5 content_safety (only without a block reason)
        if not blocked:
            t0 = time.perf_counter()
            x = args if tool not in READ_TOOLS else output
            text = ("Role: scheduling_assistant. Task: Process today's new referrals and book follow-ups.\n"
                    f"Tool: {tool}\nDestination: {', '.join(recips) or 'none'}\n"
                    f"Content: {json.dumps(x, sort_keys=True)[:4000]}")
            r = nemotron.content_safety(text)
            if r.ok:
                flagged, cats = bool(r.data["flagged"]), list(r.data["categories"])
            else:  # local fallback: identifiers in an outgoing email
                body_text = f"{args.get('subject', '')} {args.get('body', '')}"
                flagged = tool == "send_email" and any(k in ("SSN", "MRN") for k, _, _ in core.prescan(body_text))
                cats = ["PII/Privacy"] if flagged else []
            nem["content_safety"] = {"served_by": r.served_by if r.ok else "fallback:local",
                                     "model": r.model if r.ok else "", "flagged": flagged, "categories": cats,
                                     "latency_ms": round(r.latency_ms, 1)}
            signals["content_safety"] = "flagged" if flagged else "clear"
            if flagged:
                add("CONTENT_SAFETY_FLAGGED", "content_safety", ", ".join(cats))
            mark("content_safety", t0)

        # 6 anomaly (a call that already has a block reason is not part of the session window)
        if not blocked:
            t0 = time.perf_counter()
            ev_pids = list(pids)
            if raw is not None:
                if tool == "search_patients":
                    ev_pids += [p["id"] for p in raw.get("patients", []) if "id" in p]
                elif tool == "read_document" and raw.get("patient_id"):
                    ev_pids.append(raw["patient_id"])
            hist = S["history"].setdefault(req.session_id, [])
            hist.append({"ts": ts, "session_id": req.session_id, "tool": tool, "patient_ids": ev_pids,
                         "resource_types": rtypes, "recipients": recips})
            window = [e for e in hist if e["ts"] > ts - 60]
            scores["anomaly"] = float(ml.anomaly_score(window))
            if scores["anomaly"] >= 0.5:
                add("ANOMALY", "anomaly", f"anomaly score {scores['anomaly']:.4f}")
            mark("anomaly", t0)

        # 7 decide (final: nothing below changes decision, reasons, result, queue_id or queue status)
        decision = "block" if blocked else "escalate" if reasons else "allow"
        result = None
        if decision == "allow":
            if tool not in READ_TOOLS:
                t0 = time.perf_counter()
                try:
                    output = run_tool(tool, args, req.session_id)
                except Exception as e:
                    decision = "block"
                    add("EXECUTION_ERROR", "execute", str(e))
                mark("execute", t0)
            if decision == "allow":
                result = output
                add("OK", "policy")
        if decision != "allow":
            redactions = []

        queue_id = None
        if decision == "escalate" or (decision == "block" and any(r["code"] in ALERT_CODES for r in reasons)):
            queue_id = f"q-{len(S['queue']) + 1:04d}"
        if decision == "escalate":
            result = {"status": "pending_approval", "queue_id": queue_id}

        # 8 reasoner (advisory, block/escalate only)
        reason_obj = None
        if decision != "allow":
            t0 = time.perf_counter()
            if tool == "read_document" and any(r["code"] == "INJECTION_DETECTED" for r in reasons):
                shown = ml.minimize(tool, raw, keep_fields)[0]  # prescan-redacted text for the reviewer
            else:
                shown = output if tool in READ_TOOLS else None
            ctx = reasoner.build_context(tool, args, shown, decision, reasons, scores, signals, policy_path)
            try:
                reason_obj = reasoner.explain(ctx)
            except Exception:  # noqa: BLE001
                reason_obj = reasoner.template(ctx, error="exception")
            nem["reasoner"] = reason_obj
            mark("reasoner", t0)

        # 9 audit
        pre_us = int((time.perf_counter() - t_start) * 1e6)
        t0 = time.perf_counter()
        sha = hashlib.sha256(json.dumps(args, sort_keys=True, separators=(",", ":"),
                                        ensure_ascii=False).encode("utf-8")).hexdigest()
        now = _now_iso()
        body = {"kind": "decision", "ts": now, "call_id": call_id, "session_id": req.session_id,
                "role": req.role, "tool": tool, "args_sha256": sha, "patient_ids": pids, "recipients": recips,
                "decision": decision, "reasons": [r["code"] for r in reasons],
                "scores": {k: (None if v is None else f"{v:.4f}") for k, v in scores.items()},
                "latency_us": pre_us, "queue_id": queue_id,
                "nemotron": {"jailbreak": (nem["jailbreak"] or {}).get("served_by"),
                             "nemoguard": (nem["nemoguard"] or {}).get("served_by"),
                             "nemoguard_score": None if (nem["nemoguard"] or {}).get("score") is None
                             else f"{nem['nemoguard']['score']:.4f}",
                             "content_safety": (nem["content_safety"] or {}).get("served_by"),
                             "reasoner": (reason_obj or {}).get("served_by"),
                             "reasoner_risk": (reason_obj or {}).get("risk_level"),
                             "reasoner_action": (reason_obj or {}).get("recommended_action"),
                             "reasoner_rule_ids": (reason_obj or {}).get("policy_rule_ids", []),
                             "explanation_sha256": hashlib.sha256(reason_obj["explanation"].encode("utf-8")).hexdigest()
                             if reason_obj else None}}
        audit_hash = get_audit().append(json.dumps(body))
        mark("audit", t0)
        total = (time.perf_counter() - t_start) * 1000
        lat["added"] = total - lat["execute"]
        lat["total"] = total
        out = {"seq": len(S["decisions"]) + 1, "call_id": call_id, "session_id": req.session_id, "tool": tool,
               "decision": decision, "reasons": reasons, "result": result, "scores": scores,
               "redactions": redactions, "queue_id": queue_id, "nemotron": nem,
               "latency_ms": {k: round(v, 4) for k, v in lat.items()},
               "audit_hash": audit_hash, "ts": now, "core": core.IMPLEMENTATION, "ml": ml_name}
        S["decisions"].append(out)
        rt.mkdir(parents=True, exist_ok=True)
        with open(p_dec, "a", encoding="utf-8") as f:
            f.write(json.dumps(out) + "\n")
        if queue_id:
            S["queue"].append({
                "queue_id": queue_id, "kind": "approval" if decision == "escalate" else "alert",
                "status": "pending", "created_at": now[:19] + "Z", "call_id": call_id,
                "session_id": req.session_id, "tool": tool, "args": args, "decision": decision,
                "reasons": reasons, "reviewed_by": None, "reviewed_at": None, "note": "",
                "reasoner": reason_obj})
            save_queue()
        return out

    @app.get("/v1/decisions")
    def decisions(limit: int = 100):
        with lock:
            return {"decisions": S["decisions"][-limit:] if limit > 0 else []}

    @app.get("/v1/queue")
    def queue(status: str = "pending"):
        with lock:
            return {"items": [i for i in S["queue"] if status == "all" or i["status"] == status]}

    def review(queue_id, approve, body):
        with lock:
            item = next((i for i in S["queue"] if i["queue_id"] == queue_id), None)
            if item is None:
                raise HTTPException(404, "unknown queue_id")
            if item["status"] != "pending":
                raise HTTPException(409, "not pending")
            result = None
            if approve and item["kind"] == "approval":
                try:
                    result = minimized(item["tool"], run_tool(item["tool"], item["args"], item["session_id"]))[0]
                except Exception as e:
                    result = {"error": str(e)}
            item["status"] = "approved" if approve else "denied"
            item["reviewed_by"], item["reviewed_at"], item["note"] = body.reviewer, _now_iso(), body.note
            save_queue()
            allow = approve and item["kind"] == "approval"
            get_audit().append(json.dumps({
                "kind": "review", "ts": item["reviewed_at"], "call_id": item["call_id"], "queue_id": queue_id,
                "decision": "allow" if allow else "block",
                "reasons": ["HUMAN_APPROVED" if approve else "HUMAN_DENIED"], "reviewer": body.reviewer}))
            return {"queue_id": queue_id, "status": item["status"], "result": result}

    @app.post("/v1/queue/{queue_id}/approve")
    def approve(queue_id: str, body: Review = Review()):
        return review(queue_id, True, body)

    @app.post("/v1/queue/{queue_id}/deny")
    def deny(queue_id: str, body: Review = Review()):
        return review(queue_id, False, body)

    @app.get("/v1/audit/verify")
    def verify():
        with lock:
            if S["audit"] is None:
                return {"ok": True, "first_bad": None, "reason": "", "entries": 0, "core": core.IMPLEMENTATION}
            ok, bad, reason = core.verify_log(p_audit)
            return {"ok": ok, "first_bad": bad, "reason": reason, "entries": S["audit"].entries(),
                    "core": core.IMPLEMENTATION}

    @app.get("/v1/metrics")
    def metrics():
        with lock:
            ds = S["decisions"]
            n = len(ds)
            counts = {k: sum(d["decision"] == k for d in ds) for k in ("allow", "block", "escalate")}
            rates = {k: round(v / n, 4) if n else 0.0 for k, v in counts.items()}
            by = {s: {"p50": _pct([d["latency_ms"].get(s, 0.0) for d in ds], .5),
                      "p95": _pct([d["latency_ms"].get(s, 0.0) for d in ds], .95)}
                  for s in ("policy", "injection", "jailbreak", "nemoguard", "minimize", "content_safety", "anomaly", "reasoner",
                            "audit")}
            served = {st: {k: sum(((d.get("nemotron") or {}).get(st) or {}).get("served_by") == k for d in ds)
                           for k in ks} for st, ks in SERVED.items()}
            added = [d["latency_ms"]["added"] for d in ds]
            try:
                models = json.loads((ROOT / "metrics" / "results.json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                models = {}
            return {"counts": {**counts, "total": n}, "rates": rates,
                    "latency_ms": {"p50": _pct(added, .5), "p95": _pct(added, .95), "by_stage": by},
                    "core": core.IMPLEMENTATION, "ml": ml_name, "models": models,
                    "nemotron": {"mode": nemotron.mode(), "served_by": served,
                                 "latency_ms": nemotron.latency_summary(),
                                 "models": nemotron.config()["models"]}}

    @app.post("/v1/admin/reset")
    def reset():
        with lock:
            for p in (p_audit, p_audit + ".head", p_dec, p_queue):
                if os.path.exists(p):
                    os.remove(p)
            S.update(audit=None, decisions=[], queue=[], history={})
            policy.reset()
            return {"status": "reset"}

    return app


app = create_app()
