"""The gatekeeper: the only door to the local model.

Standard library only, so it runs on any Mac with Python 3.8+ and no installs.

Where answers go (see config/policy.json -> tiers):
  green  shown to the asker, marked "no flags"; a random sample is copied to QA
  amber  held; the asker sees the reasons and must confirm review to see it
  red    nothing shown; queued for a second person (clinical lead or admin)
"""
from __future__ import annotations

import json
import random
import re
import secrets
import threading
import time
import urllib.parse
import uuid
from datetime import date, timedelta
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import VERSION, llm, privacy
from .audit import AuditLog
from .ehr import EHR
from .guardrails import REVIEW_NOTE, Guardrails, worst
from .schedule import Schedule, ScheduleError
from .users import UserStore
from .records import RecordError, apply_entry, validate_entry, validate_patient
from .vectorstore import Embedder, VectorStore, index_all, reindex

ROOT = Path(__file__).resolve().parent.parent
STATIC = {"/": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"),
          "/app.css": ("app.css", "text/css")}
SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; form-action 'self'",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}
MAX_BODY = 20_000
HISTORY_TURNS = 10


class JsonStore:
    """A list of records in one JSON file, guarded by a lock."""

    def __init__(self, path: Path):
        self.path, self.lock = path, threading.Lock()
        if not path.exists():
            path.write_text("[]")

    def all(self) -> list[dict]:
        return json.loads(self.path.read_text())

    def add(self, item: dict) -> dict:
        with self.lock:
            items = self.all()
            items.append(item)
            self.path.write_text(json.dumps(items, indent=2))
        return item

    def update(self, item_id: str, fn) -> dict | None:
        """Apply fn(item) under the lock; fn returns an error string or None."""
        with self.lock:
            items = self.all()
            item = next((i for i in items if i["id"] == item_id), None)
            if item is None:
                return None
            err = fn(item)
            if err:
                return {"error": err}
            self.path.write_text(json.dumps(items, indent=2))
            return item


def now() -> str:
    return time.strftime("%Y-%m-%d %H:%M")


class App:
    def __init__(self, root: Path = ROOT, data_dir: Path | None = None):
        self.policy = json.loads((root / "config" / "policy.json").read_text())
        data = data_dir or root / "data"
        data.mkdir(parents=True, exist_ok=True)
        self.users = UserStore(data / "users.json", self.policy["roles"])
        self.audit = AuditLog(data / "audit.jsonl")
        self.outbox = JsonStore(data / "outbox.json")
        self.reviews = JsonStore(data / "reviews.json")
        self.ehr = EHR(data / "patients.json")
        self.views: dict[str, list[tuple[float, str]]] = {}
        self.guard = Guardrails(self.policy)
        # Local append-only vector store: similar-case search and reworded-injection detection.
        self.vectors = VectorStore(data / "vectors.sqlite", Embedder(self.policy))
        index_all(self.vectors, list(self.ehr.patients.values()), privacy.mask)
        self.guard.vectors = self.vectors
        self.chart = AuditLog(data / "chart_history.jsonl")  # what was added to each chart, by whom (hash-chained)
        self.schedule = Schedule(data / "schedule.json", self.policy["clinic"], self.ehr.patients)
        fd = self.policy["frontdesk"]
        self.fd_fields = fd["allowed_fields"]
        self.fd_redirect = [re.compile(x, re.I) for x in fd["clinical_redirect_patterns"]]
        self.sessions: dict[str, dict] = {}
        self.hits: dict[str, list[float]] = {}
        self.pin_fails: dict[str, list[float]] = {}
        self.lock = threading.Lock()
        self.rng = random.SystemRandom()

    # ---- helpers -------------------------------------------------------
    def similar_cases(self, sess: dict, pid: str) -> list[dict]:
        """Patients whose (masked) profiles are closest to this one, from the local vector store."""
        p = self.ehr.get(pid)
        if not p:
            return []
        k = self.policy.get("vectors", {}).get("similar_cases", 3)
        mine = {c.lower() for c in p["conditions"]}
        hits = self.vectors.search("patient_profiles", self.vectors.vector_of("patient_profiles", pid) or "",
                                   k=k, exclude={pid})
        out = []
        for h in hits:
            o = self.ehr.get(h["doc_id"])
            if o:
                out.append({"id": o["id"], "name": f"{o['name']['given']} {o['name']['family']}",
                            "age": o["age"], "sex": o["sex"], "score": h["score"],
                            "shared": [c for c in o["conditions"] if c.lower() in mine],
                            "conditions": o["conditions"][:3]})
        self.audit.write("similar_cases", sess["user"], patient=pid, results=[o["id"] for o in out])
        return out

    # ---- confidential fields behind a PIN ----------------------------------
    def redact(self, view: dict) -> dict:
        """Hide identifiers (birth date, phone, address, MRN, insurance member ID) until a PIN reveal."""
        fields = self.policy["confidential"]["fields"]
        out = {k: v for k, v in view.items() if k not in fields}
        out["locked"] = [k for k in fields if k in view]
        if isinstance(view.get("insurance"), dict) and "member_id" in fields:
            out["insurance"] = {k: v for k, v in view["insurance"].items() if k != "member_id"}
            if view["insurance"].get("member_id"):
                out["locked"].append("member_id")
        return out

    def check_pin(self, sess: dict, pin, what: str) -> str | None:
        """None if the PIN is right; otherwise the message to show. Wrong PINs lock the account for a while."""
        conf = self.policy["confidential"]
        t = time.time()
        with self.lock:
            fails = [x for x in self.pin_fails.get(sess["user"], []) if t - x < 60 * conf["lock_minutes"]]
            self.pin_fails[sess["user"]] = fails
        if len(fails) >= conf["max_wrong"]:
            return f"Too many wrong PINs. Try again in {conf['lock_minutes']} minutes."
        if isinstance(pin, str) and secrets.compare_digest(pin.encode(), str(conf["pin"]).encode()):
            return None
        left = conf["max_wrong"] - len(fails) - 1
        with self.lock:
            self.pin_fails.setdefault(sess["user"], []).append(t)
        self.audit.write("pin_failed", sess["user"], action=what)
        return (f"Wrong PIN. {left} {'try' if left == 1 else 'tries'} left." if left
                else f"Wrong PIN. Locked for {conf['lock_minutes']} minutes.")

    def reveal(self, sess: dict, pid: str, pin) -> tuple[int, dict]:
        p = self.ehr.get(pid)
        if not p:
            return 404, {"error": "No such patient."}
        err = self.check_pin(sess, pin, "reveal")
        if err:
            return 403, {"error": err}
        view = self.ehr.front_desk(p, self.fd_fields)
        if self.can(sess, "view_patients"):
            view["mrn"] = p["mrn"]
        fields = self.policy["confidential"]["fields"]
        shown = {k: view[k] for k in fields if k in view}
        if "member_id" in fields and isinstance(view.get("insurance"), dict):
            shown["member_id"] = view["insurance"].get("member_id", "")
        self.audit.write("confidential_revealed", sess["user"], patient_id=pid, fields=sorted(shown))
        return 200, shown

    # ---- adding patients and chart entries ------------------------------
    def register(self, sess: dict, data: dict) -> dict:
        v = validate_patient(data, self.schedule.now().date())
        with self.lock:
            dup = next((p for p in self.ehr.patients.values() if p["birthDate"] == v["birthDate"]
                        and p["name"]["given"].lower() == v["given"].lower()
                        and p["name"]["family"].lower() == v["family"].lower()), None)
            if dup:
                raise RecordError(f"{v['given']} {v['family']} with that birth date is already registered. "
                                  "Search for them instead of adding them again.")
            p = self.ehr.add_patient(v)
        reindex(self.vectors, p, privacy.mask)
        self.chart.write("patient_registered", sess["user"], patient_id=p["id"],
                         summary="Registered as a new patient")
        self.audit.write("patient_registered", sess["user"], patient_id=p["id"])
        return p

    def add_entry(self, sess: dict, pid: str, data: dict) -> tuple[dict, list[str]]:
        warnings = []
        with self.lock:
            p = self.ehr.get(pid)
            if not p:
                raise RecordError("No such patient.")
            summary, change = validate_entry(p, data, self.schedule.now().date())
            if change["kind"] == "note":
                found = self.guard.scan_document(change["text"])
                if found:  # kept in the chart (nothing is dropped), but never shown to the model
                    warnings.append("This note contains text that looks like instructions to an AI. It was saved, "
                                    "and it will be kept away from the assistant.")
                    self.queue("document", "red", sess, privacy.mask(change["text"])[0],
                               [f"{change['type']} in record {pid}"] + found, None)
            apply_entry(p, change, sess["user"])
            self.ehr.save()
        reindex(self.vectors, p, privacy.mask)
        self.chart.write("chart_" + change["kind"], sess["user"], patient_id=pid, summary=summary,
                         change={k: v for k, v in change.items() if k != "kind"})
        self.audit.write("chart_updated", sess["user"], patient_id=pid, kind=change["kind"])
        return p, warnings

    def history(self, pid: str | None, limit: int = 500) -> list[dict]:
        rows = self.chart.read(limit=100000)
        out = []
        for r in rows:
            if pid is None or r["details"].get("patient_id") == pid:
                p = self.ehr.get(r["details"].get("patient_id", ""))
                out.append({"ts": r["ts"], "user": r["user"], "event": r["event"],
                            "patient_id": r["details"].get("patient_id"),
                            "patient": f"{p['name']['given']} {p['name']['family']}" if p else "",
                            "summary": r["details"].get("summary", ""), "change": r["details"].get("change")})
            if len(out) >= limit:
                break
        return out

    # ---- schedule and front desk -----------------------------------------
    def appt_view(self, sess: dict, a: dict) -> dict:
        """One appointment as this role may see it. Front desk gets the allow-listed fields only."""
        p = self.ehr.get(a["patient_id"]) or {}
        out = {k: a[k] for k in ("id", "date", "time", "clinician", "visit_type", "status", "cancel_reason",
                                 "reminder")}
        out["clinician_name"] = self.policy["clinic"]["clinicians"].get(a["clinician"], a["clinician"])
        out["patient"] = self.redact(self.ehr.front_desk(p, self.fd_fields)) if p else {}
        if p and self.can(sess, "view_patients"):
            out["patient"].update(age=p["age"], sex=p["sex"], conditions=p["conditions"][:2],
                                  attention=len(p["attention"]))
        return out

    def schedule_payload(self, sess: dict, day: str) -> dict:
        today = self.schedule.now().date()
        c = self.policy["clinic"]
        return {"date": day, "today": today.isoformat(), "now": self.schedule.now().strftime("%H:%M"),
                "days": [(today + timedelta(days=i)).isoformat() for i in range(c["booking_days_ahead"] + 1)],
                "clinicians": c["clinicians"], "visit_types": c["visit_types"],
                "cancel_reasons": c["cancel_reasons"], "no_show_after_minutes": c["no_show_after_minutes"],
                "appointments": [self.appt_view(sess, a) for a in self.schedule.day(day)]}

    def frontdesk_context(self) -> tuple[str, dict, dict]:
        """Today's and tomorrow's schedule with patients as tags. No names, dates of birth or clinical data."""
        today = self.schedule.now().date()
        tag_of, name_of, lines = {}, {}, []
        for label, d in (("Today", today), ("Tomorrow", today + timedelta(days=1))):
            day = d.isoformat()
            lines.append(f"{label}:")
            for a in self.schedule.day(day):
                if a["patient_id"] not in tag_of:
                    tag = f"[P{len(tag_of) + 1}]"
                    tag_of[a["patient_id"]] = tag
                    p = self.ehr.get(a["patient_id"])
                    name_of[tag] = f"{p['name']['given']} {p['name']['family']}"
                lines.append(f"- {a['time']} {tag_of[a['patient_id']]} with {a['clinician']}, "
                             f"{a['visit_type']}, {a['status'].replace('_', ' ')}"
                             + (", reminder sent" if (a.get("reminder") or {}).get("sent_at") else ""))
            for c in self.policy["clinic"]["clinicians"]:
                free = self.schedule.open_slots(day, c)
                lines.append(f"  Open times for {c}: {', '.join(free) if free else 'none left'}")
        head = (f"Clinic hours {' to '.join(self.policy['clinic']['hours'])}. "
                f"It is now {self.schedule.now().strftime('%H:%M')}.")
        return head + "\n" + "\n".join(lines), tag_of, name_of

    def frontdesk_ask(self, sess: dict, text: str) -> dict:
        context, tag_of, name_of = self.frontdesk_context()
        for c, label in self.policy["clinic"]["clinicians"].items():  # "Dr Lee" -> dr_lee, as in the schedule
            text = re.sub(re.escape(label).replace(r"\ ", r"\.?\s*"), c, text, flags=re.I)
        for tag, name in name_of.items():  # names the desk typed become the same tags the model sees
            text = re.sub(re.escape(name), tag, text, flags=re.I)
            text = re.sub(r"\b" + re.escape(name.split()[1]) + r"\b", tag, text, flags=re.I)
        masked, tags = privacy.mask(text)
        trace = [{"step": "Signed in", "status": "ok", "detail": f"{sess['user']} as {sess['role']}"},
                 {"step": "Front desk view only", "status": "ok",
                  "detail": "schedule and open times; no clinical records, names or birth dates"},
                 {"step": "Identifiers masked", "status": "ok", "detail": ", ".join(tags) if tags else "none found"}]
        unmask = lambda t: re.sub(r"\[P\d+\]", lambda m: name_of.get(m.group(0), m.group(0)), t)
        base = {"masked_input": unmask(masked), "model_saw": masked, "masked_tags": tags, "trace": trace}
        if any(r.search(masked) for r in self.fd_redirect):
            self.audit.write("frontdesk_redirected", sess["user"], text=masked)
            trace.append({"step": "Scope check", "status": "warn", "detail": "clinical question: not for front desk"})
            return {**base, "tier": "redirect",
                    "reasons": ["That's a clinical question. The front desk can't see clinical information, "
                                "so please pass it to a nurse or clinician."]}
        inp = self.guard.check_input(masked)
        trace.append({"step": "Input check", "status": {"green": "ok", "amber": "warn", "red": "blocked"}[inp["tier"]],
                      "detail": "; ".join(inp["reasons"]) or "no flags"})
        if inp["tier"] == "red":
            item = self.queue("frontdesk", "red", sess, masked, inp["reasons"], None)
            self.audit.write("request_blocked", sess["user"], reasons=inp["reasons"], text=masked)
            return {**base, "tier": "red", "reasons": inp["reasons"], "review_id": item["id"]}
        try:
            raw = llm.chat(self.policy, [{"role": "user", "content": f"Schedule:\n{context}\n\nQuestion: {masked}"}],
                           system=self.policy["frontdesk"]["system_prompt"])
        except Exception as e:
            self.audit.write("model_error", sess["user"], error=str(e)[:200])
            trace.append({"step": "Local model", "status": "blocked", "detail": "not reachable"})
            return {**base, "tier": "error", "reasons": ["The local model is not reachable. Is Ollama running?"]}
        trace.append({"step": "Local model", "status": "ok", "detail": f"{self.policy['model']['chat_model']}, on this machine"})
        out = self.guard.check_output(raw, [])
        if out["tier"] == "red" or any(r.search(out["text"].replace(REVIEW_NOTE, "")) for r in self.fd_redirect):
            reasons = out["reasons"] if out["tier"] == "red" else ["The answer strayed into clinical topics."]
            item = self.queue("frontdesk", "red", sess, masked, reasons, out["text"])
            trace.append({"step": "Output check", "status": "blocked", "detail": "; ".join(reasons)})
            self.audit.write("model_answer", sess["user"], tier="red", text=masked, role="frontdesk")
            return {**base, "tier": "red", "reasons": reasons, "review_id": item["id"]}
        trace.append({"step": "Output check", "status": "ok", "detail": "no flags"})
        self.audit.write("model_answer", sess["user"], tier=out["tier"], text=masked, role="frontdesk")
        reply = unmask(out["text"].replace(REVIEW_NOTE, ""))
        for c, label in self.policy["clinic"]["clinicians"].items():
            reply = reply.replace(c, label)
        return {**base, "tier": out["tier"], "reasons": out["reasons"],
                "reply": reply + "\n\n---\nAI draft. Check the schedule before you tell a patient."}

    def can(self, sess: dict, perm: str) -> bool:
        return perm in self.policy["roles"].get(sess["role"], [])

    def rate_ok(self, user: str) -> bool:
        t, limit = time.time(), self.policy["server"]["max_requests_per_minute"]
        with self.lock:
            recent = [x for x in self.hits.get(user, []) if t - x < 60]
            recent.append(t)
            self.hits[user] = recent
        return len(recent) <= limit

    def record_access(self, sess: dict, pid: str) -> bool:
        """Log a record opening; return False if this user's access pattern looks unusual."""
        a = self.policy["access"]
        t, window = time.time(), 60 * a["window_minutes"]
        with self.lock:
            recent = [(x, p) for x, p in self.views.get(sess["user"], []) if t - x < window] + [(t, pid)]
            self.views[sess["user"]] = recent
        distinct = len({p for _, p in recent})
        if distinct > a["max_patients_per_window"]:
            self.audit.write("access_anomaly", sess["user"], patient_id=pid, distinct_patients=distinct,
                             window_minutes=a["window_minutes"])
            if distinct == a["max_patients_per_window"] + 1:  # alert a lead once, not on every click
                self.queue("access", "red", sess, f"Opened {distinct} different patient records in "
                           f"{a['window_minutes']} minutes", ["Unusual record access pattern"], None)
            return False
        self.audit.write("patient_viewed", sess["user"], patient_id=pid)
        return True

    def queue(self, kind: str, tier: str, sess: dict, masked: str, reasons: list[str],
              answer: str | None) -> dict:
        item = self.reviews.add({
            "id": uuid.uuid4().hex[:10], "kind": kind, "tier": tier, "reasons": reasons,
            "requester": sess["user"], "created": now(), "masked_input": masked,
            "answer": answer, "status": "open", "reviewer": None, "decided": None})
        self.audit.write("review_queued", sess["user"], review_id=item["id"], kind=kind, tier=tier,
                         reasons=reasons)
        return item

    def can_act(self, sess: dict, r: dict) -> bool:
        if r["status"] != "open":
            return False
        if r["kind"] == "qa_sample":
            return self.can(sess, "qa_review")
        if r["tier"] == "red":
            return self.can(sess, "review_red") and r["requester"] != sess["user"]
        return r["requester"] == sess["user"]

    def visible_reviews(self, sess: dict) -> list[dict]:
        out = []
        for r in self.reviews.all():
            mine = r["requester"] == sess["user"]
            if r["kind"] == "qa_sample":
                show = self.can(sess, "qa_review")
            elif r["tier"] == "red":
                show = mine or self.can(sess, "review_red")
            else:
                show = mine
            if not show:
                continue
            # The asker of a red item never sees the withheld answer; an amber answer stays
            # hidden until its asker confirms they reviewed the reasons.
            if (r["tier"] == "red" and mine) or (r["tier"] == "amber" and r["status"] == "open"):
                r = {**r, "answer": None}
            out.append({**r, "can_act": self.can_act(sess, r)})
        return out[::-1]

    def ask_model(self, sess: dict, user_text: str, kind: str, patient: dict | None = None) -> dict:
        """mask -> score input -> model -> score output -> route by tier -> log."""
        t0 = time.time()
        masked, tags = privacy.mask(user_text)
        trace = [{"step": "Signed in", "status": "ok", "detail": f"{sess['user']} as {sess['role']}"},
                 {"step": "Identifiers masked", "status": "ok",
                  "detail": ", ".join(tags) if tags else "none found"}]
        log_text = masked if self.policy["logging"]["store_masked_text"] else None
        tier_status = {"green": "ok", "amber": "warn", "red": "blocked"}

        inp = self.guard.check_input(masked)
        trace.append({"step": "Input check", "status": tier_status[inp["tier"]],
                      "detail": "; ".join(inp["reasons"]) or "no flags"})
        base = {"masked_input": masked, "masked_tags": tags, "trace": trace}

        if inp["tier"] == "red":
            item = self.queue(kind, "red", sess, masked, inp["reasons"], None)
            self.audit.write("request_blocked", sess["user"], reasons=inp["reasons"], flags=inp["flags"],
                             masked_tags=tags, text=log_text)
            trace.append({"step": "Routed", "status": "blocked", "detail": "red: sent to a second reviewer"})
            return {**base, "tier": "red", "reasons": inp["reasons"], "review_id": item["id"]}

        model_input, doc_reasons = masked, []
        if patient is not None:
            context, notes = self.ehr.model_context(patient)
            kept = []
            for n in notes:
                found = self.guard.scan_document(n["text"])
                if found:
                    label = f"{n['type']} in record {patient['id']}"
                    already = any(r["kind"] == "document" and r["status"] == "open" and r["reasons"][0] == label
                                  for r in self.reviews.all())
                    doc_reasons.append(f"A {n['type'].lower()} ({n['ago']} days ago) was withheld from the model: "
                                       + " ".join(found))
                    if not already:
                        self.queue("document", "red", sess, privacy.mask(n["text"])[0], [label] + found, None)
                else:
                    kept.append(f"- {n['ago']} days ago, {n['type']}: {n['text']}")
            context = privacy.mask(context + "\nNotes:\n" + ("\n".join(kept) or "- none"))[0]
            model_input = f"Patient record (identifiers removed):\n{context}\n\nQuestion: {masked}"
            trace.append({"step": "Record minimized", "status": "warn" if doc_reasons else "ok",
                          "detail": "name, MRN, birth date, contact removed"
                          + (f"; {len(doc_reasons)} document withheld" if doc_reasons else "")})
            if sess.get("history_pid") != patient["id"]:
                sess["history"], sess["history_pid"] = [], patient["id"]
        elif kind == "chat" and sess.get("history_pid"):
            sess["history"], sess["history_pid"] = [], None
        history = sess["history"] if kind == "chat" else []
        messages = history + [{"role": "user", "content": model_input}]
        try:
            raw = llm.chat(self.policy, messages)
        except Exception as e:  # model down: fail closed, never fall back to a cloud model
            self.audit.write("model_error", sess["user"], error=str(e)[:200])
            trace.append({"step": "Local model", "status": "blocked", "detail": "not reachable"})
            return {**base, "tier": "error", "reasons": ["The local model is not reachable. Is Ollama running?"]}
        trace.append({"step": "Local model", "status": "ok",
                      "detail": f"{self.policy['model']['chat_model']}, {time.time() - t0:.1f}s, on this machine"})

        out = self.guard.check_output(raw, inp["flags"])
        trace.append({"step": "Output check", "status": tier_status[out["tier"]],
                      "detail": "; ".join(out["reasons"]) or "no flags"})
        tier = worst(inp["tier"], out["tier"], "amber" if doc_reasons else "green")
        reasons = doc_reasons + inp["reasons"] + out["reasons"]
        if kind == "chat" and tier != "red":
            sess["history"] = (messages + [{"role": "assistant", "content": raw}])[-2 * HISTORY_TURNS:]
        if patient is not None:
            self.audit.write("patient_context_used", sess["user"], patient_id=patient["id"],
                             documents_withheld=len(doc_reasons))
        self.audit.write("model_answer", sess["user"], model=self.policy["model"]["chat_model"], tier=tier,
                         masked_tags=tags, flags=inp["flags"] + out["flags"], text=log_text)

        if tier == "red":
            item = self.queue(kind, "red", sess, masked, reasons, out["text"])
            trace.append({"step": "Routed", "status": "blocked",
                          "detail": "red: answer withheld, sent to a second reviewer"})
            return {**base, "tier": "red", "reasons": reasons, "review_id": item["id"]}
        if tier == "amber" and kind == "chat":
            item = self.queue(kind, "amber", sess, masked, reasons, out["text"])
            trace.append({"step": "Routed", "status": "warn", "detail": "amber: held for your review"})
            return {**base, "tier": "amber", "reasons": reasons, "review_id": item["id"]}
        sampled = tier == "green" and self.rng.random() < self.policy["tiers"].get("green_sample_rate", 0)
        if sampled:
            self.queue("qa_sample", "green", sess, masked, ["Random quality sample"], out["text"])
        trace.append({"step": "Routed", "status": "warn" if tier == "amber" else "ok",
                      "detail": ("amber: flagged for the approver" if tier == "amber" else "green: no flags")
                      + (", copied to QA sample" if sampled else "")})
        return {**base, "tier": tier, "reasons": reasons, "reply": out["text"]}


def make_handler(app: App):
    class Handler(BaseHTTPRequestHandler):
        server_version = "clinic-gatekeeper"
        sys_version = ""

        def log_message(self, *args):  # keep request lines (and any query text) out of stdout
            pass

        # ---- plumbing --------------------------------------------------
        def send(self, code: int, body, ctype="application/json", extra=None):
            data = body if isinstance(body, bytes) else json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            for k, v in {**SECURITY_HEADERS, **(extra or {})}.items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(data)

        def body(self) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            if n > MAX_BODY:
                raise ValueError("Request too large.")
            return json.loads(self.rfile.read(n) or b"{}")

        def session(self) -> dict | None:
            c = cookies.SimpleCookie(self.headers.get("Cookie", ""))
            tok = c["sid"].value if "sid" in c else None
            s = app.sessions.get(tok or "")
            if not s or s["expires"] < time.time():
                app.sessions.pop(tok or "", None)
                return None
            s["expires"] = time.time() + 60 * app.policy["server"]["session_minutes"]
            return s

        def same_origin(self) -> bool:
            # Cheap CSRF defence: state-changing calls must come from this page.
            origin = self.headers.get("Origin")
            return origin is None or origin == f"http://{self.headers.get('Host')}"

        # ---- routes ----------------------------------------------------
        def do_GET(self):
            path = self.path.split("?")[0]
            if path in STATIC:
                name, ctype = STATIC[path]
                return self.send(200, (ROOT / "static" / name).read_bytes(), ctype + "; charset=utf-8")
            if path == "/api/version":
                return self.send(200, {"version": VERSION})
            s = self.session()
            if not s:
                return self.send(401, {"error": "Not signed in."})
            if path == "/api/me":
                return self.send(200, {"user": s["user"], "role": s["role"],
                                       "permissions": app.policy["roles"][s["role"]],
                                       "recipient_groups": app.policy["communication"]["allowed_recipient_groups"],
                                       "model": app.policy["model"]["chat_model"],
                                       "presidio": privacy.presidio_available(), "version": VERSION,
                                       "clinic": app.policy["clinic"]["name"],
                                       "mock": llm_is_mock()})
            if path == "/api/reviews":
                return self.send(200, app.visible_reviews(s))
            if path == "/api/patients" or path.startswith("/api/patients/"):
                if not app.can(s, "view_patients"):
                    return self.send(403, {"error": "Your role cannot open patient records."})
                if path == "/api/patients":
                    q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("q", [""])[0]
                    return self.send(200, app.ehr.summaries(q[:80]))
                parts = path.split("/")  # ['', 'api', 'patients', id, (similar|history)]
                if len(parts) == 5 and parts[4] == "similar":
                    return self.send(200, app.similar_cases(s, parts[3]))
                if len(parts) == 5 and parts[4] == "history":
                    return self.send(200, app.history(parts[3]))
                p = app.ehr.get(path.rsplit("/", 1)[-1])
                if not p:
                    return self.send(404, {"error": "No such patient."})
                if not app.record_access(s, p["id"]):
                    return self.send(429, {"error": "Unusual access pattern: too many different records opened. "
                                                    "A clinical lead has been notified."})
                return self.send(200, app.redact(p))
            if path == "/api/chart/options":
                from . import records as R
                return self.send(200, {"results": {k: {"unit": u, "ref": r, "limits": l} for k, (u, r, l) in R.RESULTS.items()},
                                       "note_types": R.NOTE_TYPES, "plans": R.PLANS, "contact": R.CONTACT,
                                       "languages": R.LANGUAGES, "sexes": R.SEXES, "allergy_families": R.ALLERGY_FAMILIES})
            if path == "/api/chart/recent":
                if not app.can(s, "view_patients"):
                    return self.send(403, {"error": "Not allowed."})
                return self.send(200, app.history(None, 30))
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            arg = lambda k: qs.get(k, [""])[0][:80]
            if path == "/api/schedule":
                if not app.can(s, "view_schedule"):
                    return self.send(403, {"error": "Your role cannot see the schedule."})
                day = arg("date") or app.schedule.now().date().isoformat()
                try:
                    date.fromisoformat(day)
                except ValueError:
                    return self.send(400, {"error": "Bad date."})
                return self.send(200, app.schedule_payload(s, day))
            if path == "/api/schedule/slots":
                if not app.can(s, "book"):
                    return self.send(403, {"error": "Your role cannot book appointments."})
                if arg("clinician") not in app.policy["clinic"]["clinicians"]:
                    return self.send(400, {"error": "Pick a clinician."})
                try:
                    date.fromisoformat(arg("date"))
                except ValueError:
                    return self.send(400, {"error": "Pick a date."})
                return self.send(200, app.schedule.open_slots(arg("date"), arg("clinician")))
            if path == "/api/frontdesk/patients":
                if not app.can(s, "book"):
                    return self.send(403, {"error": "Your role cannot search patients."})
                found = app.ehr.search(arg("q"))
                app.audit.write("demographics_search", s["user"], results=len(found))
                return self.send(200, [app.redact(app.ehr.front_desk(p, app.fd_fields)) for p in found])
            if path == "/api/outbox":
                if not (app.can(s, "draft_message") or app.can(s, "approve_message")):
                    return self.send(403, {"error": "Not allowed."})
                return self.send(200, app.outbox.all()[::-1])
            if path == "/api/audit":
                if not app.can(s, "view_audit"):
                    return self.send(403, {"error": "Not allowed."})
                app.audit.write("audit_viewed", s["user"])
                return self.send(200, {"entries": app.audit.read(), "verify": app.audit.verify(),
                                       "vectors": app.vectors.status()})
            self.send(404, {"error": "Not found."})

        def do_POST(self):
            path = self.path.split("?")[0]
            if not self.same_origin():
                return self.send(403, {"error": "Cross-site request refused."})
            try:
                data = self.body()
            except Exception as e:
                return self.send(400, {"error": str(e)})

            if path == "/api/login":
                user, pw = str(data.get("username", "")), str(data.get("password", ""))
                if not app.rate_ok("login:" + user):
                    return self.send(429, {"error": "Too many attempts. Wait a minute."})
                role = app.users.check(user, pw)
                if not role:
                    app.audit.write("login_failed", user)
                    return self.send(401, {"error": "Wrong username or password."})
                tok = secrets.token_urlsafe(32)
                app.sessions[tok] = {"user": user, "role": role, "history": [],
                                     "expires": time.time() + 60 * app.policy["server"]["session_minutes"]}
                app.audit.write("login", user, role=role)
                return self.send(200, {"ok": True}, extra={
                    "Set-Cookie": f"sid={tok}; HttpOnly; SameSite=Strict; Path=/"})

            s = self.session()
            if not s:
                return self.send(401, {"error": "Not signed in."})
            if not app.rate_ok(s["user"]):
                app.audit.write("rate_limited", s["user"])
                return self.send(429, {"error": "Too many requests. Wait a minute."})

            if path == "/api/logout":
                app.sessions = {k: v for k, v in app.sessions.items() if v is not s}
                app.audit.write("logout", s["user"])
                return self.send(200, {"ok": True}, extra={"Set-Cookie": "sid=; Max-Age=0; Path=/"})

            if path == "/api/chat":
                if not app.can(s, "chat"):
                    return self.send(403, {"error": "Your role cannot use the assistant."})
                text = str(data.get("message", "")).strip()
                if not text:
                    return self.send(400, {"error": "Empty message."})
                patient = None
                if data.get("patient_id"):
                    if not app.can(s, "view_patients"):
                        return self.send(403, {"error": "Your role cannot open patient records."})
                    patient = app.ehr.get(str(data["patient_id"]))
                    if not patient:
                        return self.send(404, {"error": "No such patient."})
                return self.send(200, app.ask_model(s, text, "chat", patient))

            if path == "/api/reveal":
                if not (app.can(s, "view_patients") or app.can(s, "check_in")):
                    return self.send(403, {"error": "Your role cannot see patient details."})
                code, body = app.reveal(s, str(data.get("patient_id", "")), data.get("pin"))
                return self.send(code, body)

            if path == "/api/patients/new" or (path.startswith("/api/patients/") and path.endswith("/entry")):
                new = path == "/api/patients/new"
                if not app.can(s, "register_patient" if new else "edit_chart"):
                    return self.send(403, {"error": "Your role cannot " + ("register patients." if new else "add to charts.")})
                err = app.check_pin(s, data.get("pin"), "register" if new else "chart_entry")
                if err:
                    return self.send(403, {"error": err, "pin": True})
                try:
                    if new:
                        p = app.register(s, data)
                        return self.send(200, {"id": p["id"], "name": f"{p['name']['given']} {p['name']['family']}"})
                    p, warnings = app.add_entry(s, path.split("/")[3], data)
                    return self.send(200, {"patient": app.redact(p), "warnings": warnings})
                except RecordError as e:
                    app.audit.write("chart_refused", s["user"], reason=str(e)[:200])
                    return self.send(409, {"error": str(e)})

            if path == "/api/frontdesk/ask":
                if not app.can(s, "frontdesk_chat"):
                    return self.send(403, {"error": "Your role cannot use the front desk assistant."})
                text = str(data.get("message", "")).strip()
                if not text:
                    return self.send(400, {"error": "Empty message."})
                return self.send(200, app.frontdesk_ask(s, text[:2000]))

            if path.startswith("/api/schedule/"):
                perms = app.policy["roles"][s["role"]]
                try:
                    if path == "/api/schedule/book":
                        if not app.can(s, "book"):
                            return self.send(403, {"error": "Your role cannot book appointments."})
                        a = app.schedule.book(s["user"], str(data.get("patient_id", "")), str(data.get("date", "")),
                                              str(data.get("time", "")), str(data.get("clinician", "")),
                                              str(data.get("visit_type", "")))
                        app.audit.write("appointment_booked", s["user"], appointment=a["id"], patient_id=a["patient_id"],
                                        date=a["date"], time=a["time"], clinician=a["clinician"])
                        return self.send(200, app.appt_view(s, a))
                    if path == "/api/schedule/status":
                        a = app.schedule.change_status(s["user"], perms, str(data.get("id", "")),
                                                       str(data.get("expected", "")), str(data.get("to", "")),
                                                       data.get("checks") if isinstance(data.get("checks"), dict) else {},
                                                       data.get("reason"))
                        app.audit.write("appointment_" + a["status"], s["user"], appointment=a["id"],
                                        patient_id=a["patient_id"])
                        return self.send(200, app.appt_view(s, a))
                    if path == "/api/schedule/reminder":
                        if not app.can(s, "send_reminder"):
                            return self.send(403, {"error": "Your role cannot send reminders."})
                        a = app.schedule.reminder(s["user"], str(data.get("id", "")), str(data.get("action", "")))
                        app.audit.write("reminder_" + ("sent" if a["reminder"]["sent_at"] else "prepared"),
                                        s["user"], appointment=a["id"])
                        return self.send(200, {"appointment": app.appt_view(s, a),
                                               "text": app.schedule.reminder_text(a)})
                except ScheduleError as e:
                    app.audit.write("schedule_refused", s["user"], path=path, reason=str(e))
                    return self.send(409, {"error": str(e)})
                return self.send(404, {"error": "Not found."})

            if path == "/api/chat/clear":
                s["history"] = []
                return self.send(200, {"ok": True})

            if path == "/api/reviews/decide":
                action = data.get("action")
                if action not in {"release", "dismiss", "confirm", "ok", "problem"}:
                    return self.send(400, {"error": "Unknown action."})

                def decide(r):
                    if not app.can_act(s, r):
                        return "You cannot act on this item."
                    valid = ({"ok", "problem"} if r["kind"] == "qa_sample" else
                             {"dismiss", "confirm"} if r["tier"] == "red" else {"release"})
                    if action not in valid:
                        return "That action does not apply here."
                    r["status"] = {"release": "released", "dismiss": "dismissed", "confirm": "confirmed",
                                   "ok": "checked_ok", "problem": "problem_found"}[action]
                    r["reviewer"], r["decided"] = s["user"], now()
                    return None

                r = app.reviews.update(str(data.get("id", "")), decide)
                if r is None:
                    return self.send(404, {"error": "No such item."})
                if "error" in r:
                    return self.send(403, r)
                app.audit.write("review_" + r["status"], s["user"], review_id=r["id"], tier=r["tier"],
                                kind=r["kind"])
                if r["tier"] == "red" and r["requester"] == s["user"]:
                    r = {**r, "answer": None}
                return self.send(200, r)

            if path == "/api/outbox/draft":
                if not app.can(s, "draft_message"):
                    return self.send(403, {"error": "Your role cannot draft messages."})
                comm = app.policy["communication"]
                group = data.get("recipient_group")
                if group not in comm["allowed_recipient_groups"]:
                    app.audit.write("draft_refused", s["user"], recipient_group=str(group)[:40])
                    return self.send(400, {"error": "That recipient group is not on the allow-list."})
                instructions = str(data.get("instructions", "")).strip()
                if not instructions:
                    return self.send(400, {"error": "Say what the message should cover."})
                prompt = (f"{comm['draft_instructions']}\n\nRecipient group: {group} "
                          f"({comm['allowed_recipient_groups'][group]})\n\nWhat the message should say:\n"
                          f"{instructions}")
                result = app.ask_model(s, prompt, "draft")
                if result["tier"] in ("red", "error"):
                    return self.send(200, result)
                tier, reasons = result["tier"], list(result["reasons"])
                if group in app.policy["tiers"].get("always_amber_recipient_groups", []):
                    tier = "amber"
                    reasons.append("Goes to a patient, so it always gets a careful review.")
                item = app.outbox.add({"id": uuid.uuid4().hex[:10], "recipient_group": group,
                                       "draft": result["reply"], "tier": tier, "reasons": reasons,
                                       "status": "awaiting_approval", "drafted_by": s["user"],
                                       "created": now(), "decided_by": None, "final_text": None})
                app.audit.write("draft_created", s["user"], draft_id=item["id"], recipient_group=group, tier=tier)
                return self.send(200, {**result, "item": item})

            if path == "/api/outbox/decide":
                if not app.can(s, "approve_message"):
                    return self.send(403, {"error": "Only clinicians can approve messages."})
                decision = data.get("decision")
                if decision not in ("approve", "reject"):
                    return self.send(400, {"error": "Decision must be approve or reject."})
                final = data.get("final_text")

                def decide_draft(item):
                    if item["status"] != "awaiting_approval":
                        return "This draft was already decided."
                    if (app.policy["communication"]["approver_must_differ_from_drafter"]
                            and item["drafted_by"] == s["user"]):
                        return "A different clinician must approve this."
                    item["status"] = "approved" if decision == "approve" else "rejected"
                    item["decided_by"] = s["user"]
                    if decision == "approve":
                        item["final_text"] = str(final or item["draft"])[:MAX_BODY]
                    return None

                item = app.outbox.update(str(data.get("id", "")), decide_draft)
                if item is None:
                    return self.send(404, {"error": "No such draft."})
                if "error" in item:
                    return self.send(403, item)
                app.audit.write("draft_" + item["status"], s["user"], draft_id=item["id"],
                                edited=bool(final) and final != item["draft"])
                return self.send(200, {"item": item})

            self.send(404, {"error": "Not found."})

    return Handler


def llm_is_mock() -> bool:
    import os
    return os.environ.get("MOCK_LLM") == "1"


def run(app: App | None = None):
    app = app or App()
    host, port = app.policy["server"]["host"], app.policy["server"]["port"]
    if host not in llm.LOCAL_HOSTS:
        raise SystemExit("Refusing to listen on a non-local address. Put a TLS proxy in front instead.")
    if not app.users.list():
        print("No accounts yet. Run:  python3 setup_demo.py")
    if not llm_is_mock():
        models = llm.installed_models(app.policy)
        want = app.policy["model"]["chat_model"]
        if models is None:
            print("Ollama is not answering at", app.policy["model"]["ollama_url"], "- open the Ollama app.")
        elif not any(x == want or x == want + ":latest" or x.lower() == want.lower() for x in models):
            print(f"Ollama doesn't have the model '{want}'. Installed: {', '.join(models) or 'none'}.")
            print("Set model.chat_model in config/policy.json to one of those, or run:  ollama pull " + want)
        else:
            def _warm():
                try:
                    took = llm.warm(app.policy)
                    print(f"Model {want} loaded and ready ({took:.0f}s).")
                except Exception as e:
                    print("Couldn't preload the model:", e)
            print(f"Loading {want} in the background so the first answer is quicker...")
            threading.Thread(target=_warm, daemon=True).start()
    httpd = ThreadingHTTPServer((host, port), make_handler(app))
    app.audit.write("server_started", None, model=app.policy["model"]["chat_model"],
                    presidio=privacy.presidio_available())
    print(f"Clinic Assistant {VERSION}: open http://{host}:{port} in your browser. Ctrl+C to stop.")
    httpd.serve_forever()
