"""Assistant actions (2.12): the assistant does front-desk and clinical chores, but never writes on its own.

A chat command ("move Desmond F. to Tuesday 10am", "change syn-004's phone to 555-0199") is parsed by a
deterministic intent parser (no model needed, works with MOCK_LLM=1) into a PROPOSAL: a structured action
{type, patient_id, changes before -> after, reason}. The proposal is checked by the guardrails and the
Nemotron reviewer (app/reviewer.py), shown as a card, and applied only when a signed-in person whose role
has the action's permission approves it (and types the PIN when confidential fields or the chart change).
Approval writes through the existing paths (ClinicDB.write / write_many, Schedule, App.add_entry, the
outbox), so change_log records the approver. Ambiguity (two patients, a taken slot, no time) never guesses:
it returns a clarification card with choices.

Rules (config/policy.json -> assistant_actions):
- each action type names the permission needed to approve it; clinical drafts also need it to propose
- auditors, admins and network engineers can neither propose nor approve
- the audit log gets action_proposed / action_approved / action_rejected / action_blocked with ids only
"""
from __future__ import annotations

import json
import re
import threading
import time
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

from . import privacy
from .guardrails import worst
from .records import CONTACT, LANGUAGES, MEMBER, PHONE, PLANS, RecordError
from .schedule import ACTIVE, ScheduleError

DEFAULTS = {
    "permissions": {"reschedule": "book", "book": "book", "cancel": "book", "fill_slot": "book",
                    "update_contact": "register_patient", "remind": "send_reminder",
                    "handover": "edit_chart", "referral": "draft_message"},
    "clinical": ["handover", "referral"],
    "propose_permissions": ["chat", "frontdesk_chat"],
    "pin_fields": ["phone", "address", "member_id"],
}

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
CLINICAL_WORDS = re.compile(r"\b(medication|medicine|meds?|allerg\w*|condition|diagnos\w*|dose|result|lab|"
                            r"observation|prescri\w*)\b", re.I)
INTENTS = [  # order matters: the first that matches wins
    ("handover", re.compile(r"\b(draft|write|create|prepare|make)\b.{0,40}\bhand-?over\b", re.I)),
    ("referral", re.compile(r"\b(draft|write|create|prepare|make)\b.{0,40}\breferr?al\b|\brefer\b.{0,40}\bto\b", re.I)),
    ("cancel", re.compile(r"\bcancel\b", re.I)),
    ("remind", re.compile(r"\b(remind|reminder)\b", re.I)),
    ("fill_slot", re.compile(r"\b(fill|waitlist|wait list|wait-list)\b", re.I)),
    ("update_contact", re.compile(r"\b(change|update|set|new|correct)\b.{0,60}\b(phone|number|mobile|address|"
                                  r"contact|language|insurance|plan|member id)\b", re.I)),
    ("reschedule", re.compile(r"\b(reschedule|move|push|shift|bring forward)\b", re.I)),
    ("book", re.compile(r"\bbook\b|\bschedule (an? |the )?(appointment|visit|follow-up) for\b|\bschedule syn-\d", re.I)),
]
CLINICAL_EDIT = re.compile(r"^\s*(please\s+)?(change|update|set|add|remove|delete|stop|increase|decrease|edit)\b.{0,60}"
                           r"\b(allerg\w*|medication|medicine|meds?|condition|diagnos\w*|dose|result|lab)\b", re.I)
QUESTION = re.compile(r"^\s*(what|who|when|where|why|how|is|are|does|do|which|should|summari[sz]e|explain)\b", re.I)
EXAMPLES = [
    ("reschedule", "Move Desmond F. to Tuesday 10am"),
    ("book", "Book syn-007 tomorrow at 9:20 with Dr Osei for a lab review"),
    ("cancel", "Cancel syn-004's appointment tomorrow"),
    ("fill_slot", "Fill the 11:00 slot tomorrow with Dr Lee"),
    ("update_contact", "Change syn-012's phone to 555-0199"),
    ("update_contact", "Set syn-012's preferred contact to patient portal"),
    ("remind", "Remind syn-007 about their appointment"),
    ("handover", "Draft a handover for syn-004"),
    ("referral", "Draft a referral for syn-003 to cardiology for rising INR"),
]
LABELS = {"reschedule": "Reschedule", "book": "Book", "cancel": "Cancel", "fill_slot": "Fill a slot",
          "update_contact": "Update contact details", "remind": "Prepare a reminder",
          "handover": "Handover note (chart draft)", "referral": "Referral letter (outbox draft)"}


class ActionError(Exception):
    """A refused action. The message is shown to the person as is."""


class _Store:
    """Proposals in data/proposals.json (runtime data, never committed)."""

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

    def get(self, pid: str) -> dict | None:
        return next((i for i in self.all() if i["id"] == pid), None)

    def put(self, item: dict) -> None:
        with self.lock:
            items = [item if i["id"] == item["id"] else i for i in self.all()]
            self.path.write_text(json.dumps(items, indent=2))


def _stamp() -> str:
    return time.strftime("%Y-%m-%d %H:%M")


class Actions:
    def __init__(self, app):
        self.app = app
        self.store = _Store(app.data / "proposals.json")
        self.lock = threading.RLock()

    # ---- config ----------------------------------------------------------
    @property
    def cfg(self) -> dict:
        return {**DEFAULTS, **{k: v for k, v in self.app.policy.get("assistant_actions", {}).items()
                               if not k.startswith("_")}}

    def perm_for(self, kind: str) -> str:
        return self.cfg["permissions"][kind]

    def can_propose(self, sess: dict) -> bool:
        return any(self.app.can(sess, p) for p in self.cfg["propose_permissions"])

    def help(self, sess: dict) -> dict:
        perms = self.app.policy["roles"][sess["role"]]
        out = []
        for kind, ex in EXAMPLES:
            need = self.perm_for(kind)
            can_approve = need in perms
            if not self.can_propose(sess) or (kind in self.cfg["clinical"] and not can_approve):
                continue
            out.append({"type": kind, "label": LABELS[kind], "example": ex, "can_approve": can_approve})
        return {"role": sess["role"], "actions": out,
                "note": "The assistant only proposes. Nothing changes until a person with the right role approves."}

    # ---- parsing helpers ---------------------------------------------------
    @property
    def today(self) -> date:
        return self.app.schedule.now().date()

    def clinicians(self) -> dict:
        return self.app.policy["clinic"]["clinicians"]

    def parse_clinician(self, text: str) -> str | None:
        for key, name in self.clinicians().items():
            sur = name.split()[-1].lower()
            if re.search(rf"\b(dr\.?\s*_?{sur}|{key}|doctor {sur})\b", text, re.I):
                return key
        return None

    def strip_clinicians(self, text: str) -> str:
        for key, name in self.clinicians().items():
            sur = name.split()[-1]
            text = re.sub(rf"\b(dr\.?\s*_?{sur}|{key}|doctor {sur})\b", " ", text, flags=re.I)
        return text

    def parse_date(self, text: str) -> date | None:
        t, today = text.lower(), self.today
        m = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", t)
        if m:
            try:
                return date.fromisoformat(m.group(1))
            except ValueError:
                return None
        if re.search(r"\btoday\b", t):
            return today
        if re.search(r"\btomorrow\b", t):
            return today + timedelta(days=1)
        m = re.search(r"\bin (\d{1,2}) days?\b", t)
        if m:
            return today + timedelta(days=int(m.group(1)))
        m = re.search(r"\b(" + "|".join(MONTHS) + r")[a-z]*\.?\s+(\d{1,2})\b|\b(\d{1,2})(?:st|nd|rd|th)?\s+("
                      + "|".join(MONTHS) + r")[a-z]*\b", t)
        if m:
            mon = MONTHS.index((m.group(1) or m.group(4))[:3]) + 1
            day = int(m.group(2) or m.group(3))
            for year in (today.year, today.year + 1):
                try:
                    d = date(year, mon, day)
                except ValueError:
                    return None
                if d >= today:
                    return d
        for i, wd in enumerate(WEEKDAYS):
            if re.search(rf"\b{wd[:3]}(?:{wd[3:]})?\b", t):
                ahead = (i - today.weekday()) % 7 or 7
                return today + timedelta(days=ahead)
        return None

    @staticmethod
    def parse_time(text: str) -> str | None:
        t = re.sub(r"\b\d{4}-\d{2}-\d{2}\b|\bsyn-\d+\b|\b(\d{3}-)?\d{3}-\d{4}\b", " ", text.lower())
        if re.search(r"\bnoon\b", t):
            return "12:00"
        m = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)(?![a-z])", t)
        if m:
            h, mi = int(m.group(1)), int(m.group(2) or 0)
            if m.group(3).startswith("p") and h < 12:
                h += 12
            if m.group(3).startswith("a") and h == 12:
                h = 0
        else:
            m = re.search(r"\b(\d{1,2}):(\d{2})\b", t) or re.search(r"\bat (\d{1,2})\b(?!\s*(?:days?|st|nd|rd|th))", t)
            if not m:
                return None
            h, mi = int(m.group(1)), int(m.group(2)) if m.lastindex and m.lastindex >= 2 else 0
            if 1 <= h <= 7:  # "at 2" in a clinic means the afternoon
                h += 12
        if not (0 <= h <= 23 and 0 <= mi <= 59):
            return None
        return f"{h:02d}:{mi:02d}"

    def match_patients(self, text: str, ctx_pid: str | None) -> list[dict]:
        pats = self.app.ehr.patients
        m = re.search(r"\bsyn-\d{3,}\b", text, re.I)
        if m:
            p = pats.get(m.group(0).lower())
            return [p] if p else []
        tokens = re.findall(r"[A-Za-z][A-Za-z'-]*\.?", self.strip_clinicians(text))
        low = [re.sub(r"'s$", "", t.rstrip(".").lower()) for t in tokens]
        best, found = 0, []
        for p in pats.values():
            g, f = p["name"]["given"].lower(), p["name"]["family"].lower()
            score = 0
            for i, w in enumerate(low):
                if w == g:
                    nxt = low[i + 1] if i + 1 < len(low) else ""
                    if nxt == f:
                        score = max(score, 4)
                    elif len(nxt) == 1:
                        score = max(score, 3 if f.startswith(nxt) else -99)
                    else:
                        score = max(score, 2)
                elif w == f and len(w) > 2:
                    score = max(score, 2)
            if score > best:
                best, found = score, [p]
            elif score == best and score > 0:
                found.append(p)
        if not found and ctx_pid and ctx_pid in pats:
            return [pats[ctx_pid]]
        return found

    def name(self, p: dict) -> str:
        return f"{p['name']['given']} {p['name']['family']}"

    def label(self, p: dict) -> str:
        return f"{self.name(p)} ({p['id']})"

    def upcoming(self, pid: str, from_day: date | None = None) -> list[dict]:
        start = from_day or self.today
        end = self.today + timedelta(days=self.app.policy["clinic"]["booking_days_ahead"])
        out = [a for a in self.app.schedule.between(start.isoformat(), end.isoformat())
               if a["patient_id"] == pid and a["status"] == "booked"]
        now = self.app.schedule.now()
        out = [a for a in out if datetime.fromisoformat(f"{a['date']}T{a['time']}") > now]
        return sorted(out, key=lambda a: (a["date"], a["time"]))

    def when(self, day: str, t: str) -> str:
        d = date.fromisoformat(day)
        return f"{d:%a} {d.day} {d:%b} {t}"

    def appt_line(self, a: dict) -> str:
        return f"{self.when(a['date'], a['time'])} with {self.clinicians()[a['clinician']]} ({a['visit_type']})"

    def check_slot(self, day: date, t: str, clinician: str, ignore_id: str | None = None) -> list[str]:
        """[] if the slot is bookable, otherwise up to 4 alternative 'YYYY-MM-DD HH:MM' slots."""
        sched, c = self.app.schedule, self.app.policy["clinic"]
        if not self.today <= day <= self.today + timedelta(days=c["booking_days_ahead"]):
            raise ActionError(f"Appointments can be booked from today up to {c['booking_days_ahead']} days ahead.")
        sched.ensure_day(day)
        open_ = sched.open_slots(day.isoformat(), clinician)
        if t in open_:
            return []
        alts = sorted(open_, key=lambda s: abs(int(s[:2]) * 60 + int(s[3:]) - int(t[:2]) * 60 - int(t[3:])))[:3]
        out = [f"{day.isoformat()} {s}" for s in alts]
        for k in range(1, 4):
            nd = day + timedelta(days=k)
            if nd > self.today + timedelta(days=c["booking_days_ahead"]):
                break
            sched.ensure_day(nd)
            if t in sched.open_slots(nd.isoformat(), clinician):
                out.append(f"{nd.isoformat()} {t}")
                break
        return out or ["none"]

    # ---- cards ---------------------------------------------------------------
    @staticmethod
    def clarify(question: str, options: list[dict], kind: str | None = None) -> dict:
        return {"is_action": True, "card": "clarify", "type": kind, "question": question, "options": options}

    @staticmethod
    def refuse(message: str, kind: str | None = None) -> dict:
        return {"is_action": True, "card": "error", "type": kind, "error": message}

    # ---- propose -------------------------------------------------------------
    def detect(self, text: str) -> str | None:
        if QUESTION.search(text):  # questions go to the normal assistant; commands start with a verb
            return None
        for kind, rx in INTENTS:
            if rx.search(text):
                return kind
        return None

    def propose(self, sess: dict, text: str, ctx_pid: str | None = None, hints: dict | None = None) -> dict:
        """Parse a command into a proposal card (or a clarification). Never writes to the clinic database."""
        hints = hints or {}
        kind = hints.get("intent") or self.detect(text)
        if kind is None and not QUESTION.search(text) and CLINICAL_EDIT.search(text):
            if not self.can_propose(sess):
                raise PermissionError("Your role cannot use the assistant.")
            return self.refuse("The assistant does not change clinical details (medicines, allergies, conditions, "
                               "results). A clinician adds those with Add to chart, with the PIN.", "clinical_edit")
        if kind not in DEFAULTS["permissions"]:
            return {"is_action": False}
        if not self.can_propose(sess):
            raise PermissionError("Your role cannot use the assistant.")
        need = self.perm_for(kind)
        if kind in self.cfg["clinical"] and not self.app.can(sess, need):
            return self.refuse("Clinical drafts are for clinical roles. Ask a clinician.", kind)
        try:
            built = getattr(self, "_p_" + kind)(sess, text, ctx_pid, hints)
        except ActionError as e:
            return self.refuse(str(e), kind)
        if built.get("card") != "proposal":
            return built
        return self._finish(sess, kind, text, built)

    def _need_patient(self, text, ctx_pid, hints, kind, verb):
        if hints.get("patient_id"):
            p = self.app.ehr.patients.get(hints["patient_id"])
            if not p:
                raise ActionError("No such patient.")
            return p, None
        found = self.match_patients(text, ctx_pid)
        if not found:
            return None, self.clarify(f"Which patient should I {verb}? Use their name or record id (syn-…).", [], kind)
        if len(found) > 1:
            return None, self.clarify(f"More than one patient matches. Which one should I {verb}?",
                                      [{"label": self.label(p), "hints": {"patient_id": p["id"]}}
                                       for p in found[:6]], kind)
        return found[0], None

    def _slot_options(self, day: date, clinician: str, kind: str, extra: dict) -> list[dict]:
        self.app.schedule.ensure_day(day)
        return [{"label": f"{self.when(day.isoformat(), s)} with {self.clinicians()[clinician]}",
                 "hints": {**extra, "date": day.isoformat(), "time": s, "clinician": clinician}}
                for s in self.app.schedule.open_slots(day.isoformat(), clinician)[:6]]

    def _alt_options(self, alts: list[str], clinician: str, extra: dict) -> list[dict]:
        return [{"label": f"{self.when(*a.split())} with {self.clinicians()[clinician]}",
                 "hints": {**extra, "date": a.split()[0], "time": a.split()[1], "clinician": clinician}}
                for a in alts if a != "none"]

    def _target(self, text, hints, default_day: date | None):
        day = date.fromisoformat(hints["date"]) if hints.get("date") else (self.parse_date(text) or default_day)
        t = hints.get("time") or self.parse_time(text)
        if t and t not in self.app.schedule.slots():
            raise ActionError(f"{t} is not on the clinic's slot grid ({self.app.policy['clinic']['slot_minutes']}-minute "
                              f"slots from {self.app.policy['clinic']['hours'][0]}). Pick a listed time.")
        return day, t

    def _p_reschedule(self, sess, text, ctx_pid, hints):
        p, card = self._need_patient(text, ctx_pid, hints, "reschedule", "move")
        if card:
            return card
        appts = self.upcoming(p["id"])
        m = re.search(r"\bfrom\b(.*?)\bto\b(.*)$", text, re.I)
        if m:  # "move X from Tuesday 9am to Wednesday 10am": the first part picks the appointment
            sd, st = self.parse_date(m.group(1)), self.parse_time(m.group(1))
            appts = [a for a in appts if (not sd or a["date"] == sd.isoformat()) and (not st or a["time"] == st)]
            text = m.group(2)
        if hints.get("appointment_id"):
            appts = [a for a in self.upcoming(p["id"]) if a["id"] == hints["appointment_id"]]
        if not appts:
            raise ActionError(f"{self.name(p)} has no upcoming booked appointment to move"
                              + (" at that time" if m else "") + ". Book one instead.")
        if len(appts) > 1:
            return self.clarify(f"{self.name(p)} has {len(appts)} upcoming appointments. Which one should I move?",
                                [{"label": self.appt_line(a), "hints": {"patient_id": p["id"], "appointment_id": a["id"]}}
                                 for a in appts], "reschedule")
        src = appts[0]
        clin = hints.get("clinician") or self.parse_clinician(text) or src["clinician"]
        day, t = self._target(text, hints, date.fromisoformat(src["date"]))
        base = {"patient_id": p["id"], "appointment_id": src["id"]}
        if not t:
            return self.clarify(f"What time should {self.name(p)} move to?", self._slot_options(day, clin, "reschedule", base),
                                "reschedule")
        if (day.isoformat(), t, clin) == (src["date"], src["time"], src["clinician"]):
            raise ActionError("That is the time they already have.")
        alts = self.check_slot(day, t, clin)
        if alts:
            return self.clarify(f"{self.when(day.isoformat(), t)} with {self.clinicians()[clin]} is taken or has passed. "
                                "Pick another open time:", self._alt_options(alts, clin, base), "reschedule")
        clash = next((a for a in self.app.schedule.day(day.isoformat()) if a["patient_id"] == p["id"]
                      and a["status"] in ACTIVE and a["id"] != src["id"]), None)
        if clash:
            raise ActionError(f"{self.name(p)} already has another appointment that day at {clash['time']}.")
        return {"card": "proposal", "patient": p,
                "summary": f"Move {self.label(p)} from {self.appt_line(src)} to {self.when(day.isoformat(), t)} "
                           f"with {self.clinicians()[clin]}",
                "changes": [{"field": "appointment", "before": self.appt_line(src),
                             "after": f"{self.when(day.isoformat(), t)} with {self.clinicians()[clin]} ({src['visit_type']})"}],
                "params": {"appointment_id": src["id"], "date": day.isoformat(), "time": t, "clinician": clin}}

    def _p_book(self, sess, text, ctx_pid, hints):
        p, card = self._need_patient(text, ctx_pid, hints, "book", "book")
        if card:
            return card
        vt = next((v for v in self.app.policy["clinic"]["visit_types"] if v.lower() in text.lower()),
                  hints.get("visit_type") or "Follow-up")
        day, t = self._target(text, hints, None)
        base = {"patient_id": p["id"], "intent": "book", "visit_type": vt}
        clin = hints.get("clinician") or self.parse_clinician(text)
        if not day:
            return self.clarify(f"Which day should {self.name(p)} come in?",
                                [{"label": self.when((self.today + timedelta(days=k)).isoformat(), "")[:-1],
                                  "hints": {**base, "date": (self.today + timedelta(days=k)).isoformat()}}
                                 for k in range(1, 6)], "book")
        if not clin and t:
            self.app.schedule.ensure_day(day)
            clin = next((c for c in self.clinicians() if t in self.app.schedule.open_slots(day.isoformat(), c)),
                        next(iter(self.clinicians())))
        clin = clin or next(iter(self.clinicians()))
        if not t:
            return self.clarify(f"What time on {self.when(day.isoformat(), '')[:-1]}?",
                                self._slot_options(day, clin, "book", base), "book")
        alts = self.check_slot(day, t, clin)
        if alts:
            return self.clarify(f"{self.when(day.isoformat(), t)} with {self.clinicians()[clin]} is taken or has passed. "
                                "Pick another open time:", self._alt_options(alts, clin, base), "book")
        clash = next((a for a in self.app.schedule.day(day.isoformat()) if a["patient_id"] == p["id"]
                      and a["status"] in ACTIVE), None)
        if clash:
            raise ActionError(f"{self.name(p)} already has an appointment that day at {clash['time']}. Move that one instead.")
        return {"card": "proposal", "patient": p,
                "summary": f"Book {self.label(p)} on {self.when(day.isoformat(), t)} with {self.clinicians()[clin]} ({vt})",
                "changes": [{"field": "appointment", "before": "none",
                             "after": f"{self.when(day.isoformat(), t)} with {self.clinicians()[clin]} ({vt})"}],
                "params": {"date": day.isoformat(), "time": t, "clinician": clin, "visit_type": vt}}

    def _p_cancel(self, sess, text, ctx_pid, hints):
        p, card = self._need_patient(text, ctx_pid, hints, "cancel", "cancel")
        if card:
            return card
        appts = self.upcoming(p["id"])
        if hints.get("appointment_id"):
            appts = [a for a in appts if a["id"] == hints["appointment_id"]]
        else:
            d, t = self.parse_date(text), self.parse_time(text)
            appts = [a for a in appts if (not d or a["date"] == d.isoformat()) and (not t or a["time"] == t)]
        if not appts:
            raise ActionError(f"No upcoming booked appointment for {self.name(p)} matches that.")
        if len(appts) > 1:
            return self.clarify("Which appointment should I cancel?",
                                [{"label": self.appt_line(a), "hints": {"patient_id": p["id"], "appointment_id": a["id"]}}
                                 for a in appts], "cancel")
        a = appts[0]
        low = text.lower()
        reason = ("Patient asked to reschedule" if "reschedul" in low else "Clinician unavailable" if "unavailable" in low
                  or "sick" in low else "Booked by mistake" if "mistake" in low else "Patient called to cancel")
        return {"card": "proposal", "patient": p,
                "summary": f"Cancel {self.label(p)}'s appointment {self.appt_line(a)} ({reason})",
                "changes": [{"field": "status", "before": "booked", "after": f"cancelled ({reason})"}],
                "params": {"appointment_id": a["id"], "reason": reason}}

    def _p_remind(self, sess, text, ctx_pid, hints):
        p, card = self._need_patient(text, ctx_pid, hints, "remind", "remind")
        if card:
            return card
        appts = [a for a in self.upcoming(p["id"], self.today + timedelta(days=1))
                 if not (a.get("reminder") or {}).get("sent_at")]
        if hints.get("appointment_id"):
            appts = [a for a in appts if a["id"] == hints["appointment_id"]]
        if not appts:
            raise ActionError(f"{self.name(p)} has no upcoming appointment (after today) that still needs a reminder.")
        if len(appts) > 1:
            return self.clarify("Which appointment is the reminder for?",
                                [{"label": self.appt_line(a), "hints": {"patient_id": p["id"], "appointment_id": a["id"]}}
                                 for a in appts], "remind")
        a = appts[0]
        return {"card": "proposal", "patient": p,
                "summary": f"Prepare a reminder for {self.label(p)} about {self.appt_line(a)} (a person sends it)",
                "changes": [{"field": "reminder", "before": "not prepared", "after": "prepared, waiting to be sent"}],
                "draft": self.app.schedule.reminder_text(a),
                "params": {"appointment_id": a["id"]}}

    def _p_fill_slot(self, sess, text, ctx_pid, hints):
        day, t = self._target(text, hints, None)
        clin = hints.get("clinician") or self.parse_clinician(text)
        if not day or not t:
            raise ActionError("Say which slot to fill, for example: fill the 11:00 slot tomorrow with Dr Lee.")
        if not clin:
            self.app.schedule.ensure_day(day)
            clin = next((c for c in self.clinicians() if t in self.app.schedule.open_slots(day.isoformat(), c)), None)
            if not clin:
                raise ActionError(f"{self.when(day.isoformat(), t)} is not open for any clinician.")
        if self.check_slot(day, t, clin):
            raise ActionError(f"{self.when(day.isoformat(), t)} with {self.clinicians()[clin]} is not open.")
        end = self.today + timedelta(days=self.app.policy["clinic"]["booking_days_ahead"])
        booked = {a["patient_id"] for a in self.app.schedule.between(self.today.isoformat(), end.isoformat())
                  if a["status"] in ACTIVE}
        clinical = self.app.can(sess, "view_patients")
        cands = sorted((p for p in self.app.ehr.patients.values() if p["id"] not in booked),
                       key=lambda p: (-len(p.get("attention") or []), p["id"]))[:4]
        if not cands:
            raise ActionError("Everyone already has a visit booked in the next two weeks.")
        opts = []
        for p in cands:
            why = (f"{len(p['attention'])} things to check, no visit booked" if clinical and p.get("attention")
                   else "No visit booked in the next two weeks")
            opts.append({"label": f"{self.label(p)}: {why}",
                         "hints": {"intent": "book", "patient_id": p["id"], "date": day.isoformat(), "time": t,
                                   "clinician": clin}})
        return self.clarify(f"Who should fill {self.when(day.isoformat(), t)} with {self.clinicians()[clin]}? "
                            "Suggested from patients with no visit booked (most follow-up needed first):", opts, "fill_slot")

    def _p_update_contact(self, sess, text, ctx_pid, hints):
        if CLINICAL_WORDS.search(text):
            raise ActionError("Assistant actions only change contact details. Clinical details are added in the chart "
                              "by a clinician (Add to chart).")
        p, card = self._need_patient(text, ctx_pid, hints, "update_contact", "update")
        if card:
            return card
        low, new = text.lower(), {}
        m = re.search(r"\b(?:phone|number|mobile|cell)\b[^0-9]{0,20}((?:\d{3}-)?\d{3}-\d{4})\b", text, re.I)
        if m:
            new["phone"] = m.group(1)
        elif re.search(r"\b(phone|number|mobile|cell)\b", low) and not re.search(r"contact", low):
            raise ActionError("Phone must look like 555-0123 or 555-555-0123.")
        m = re.search(r"\baddress\b\s*(?:to|is|:|=)?\s*(.+)$", text, re.I)
        if m:
            addr = m.group(1).strip().rstrip(".")
            if not 5 <= len(addr) <= 80:
                raise ActionError("Address must be 5 to 80 characters.")
            new["address"] = addr
        if re.search(r"\b(contact|prefer\w*)\b", low):
            pc = ("Patient portal" if "portal" in low else "Text message" if re.search(r"\b(text|sms)\b", low)
                  else "Phone call" if re.search(r"\b(call|phone)\b", low) else None)
            if pc:
                new["preferred_contact"] = pc
                new.pop("phone", None) if "phone" in new and "phone call" in low else None
        if "language" in low or "speaks" in low:
            lang = next((x for x in LANGUAGES if re.search(rf"\b{x.lower()}\b", low)), None)
            if lang:
                new["language"] = lang
        if re.search(r"\b(insurance|plan)\b", low):
            plan = next((x for x in PLANS if x.lower() in low), None)
            if plan:
                new["plan"] = plan
        m = re.search(r"\bmember id\b\s*(?:to|is|:)?\s*([A-Za-z0-9]{6,12})\b", text, re.I)
        if m:
            if not MEMBER.match(m.group(1).upper()):
                raise ActionError("Insurance member ID must be 6 to 12 letters or digits.")
            new["member_id"] = m.group(1).upper()
        if not new:
            raise ActionError("Say the new value, for example: change syn-012's phone to 555-0199, or set the "
                              f"preferred contact to one of: {', '.join(CONTACT)}.")
        if "phone" in new and not PHONE.match(new["phone"]):
            raise ActionError("Phone must look like 555-0123 or 555-555-0123.")
        pin_fields = set(self.cfg["pin_fields"])
        changes = []
        for k, v in new.items():
            before = (p.get("insurance", {}).get(k) if k in ("plan", "member_id") else p.get(k)) or "none"
            if k in pin_fields:
                before = "hidden (confidential)"
            changes.append({"field": k, "before": before, "after": v})
        return {"card": "proposal", "patient": p,
                "summary": f"Update {', '.join(new)} for {self.label(p)}",
                "changes": changes, "params": {"fields": new},
                "needs_pin": bool(pin_fields & set(new))}

    def _clinical_text(self, p: dict, kind: str, text: str) -> str:
        obs = [o for o in p.get("observations", [])]
        latest = {}
        for o in obs:
            latest[o["name"]] = o
        res = "; ".join(f"{o['name']} {o['value']} {o['unit']}".strip() for o in list(latest.values())[-4:])
        lines = [f"Patient {p['id']}, {p['age']}-year-old {p['sex']} (synthetic record).",
                 "Conditions: " + ("; ".join(p["conditions"]) or "none recorded"),
                 "Medications: " + ("; ".join(p["medications"]) or "none recorded"),
                 "Allergies: " + "; ".join(p["allergies"]),
                 "Latest results: " + (res or "none"),
                 "To check: " + ("; ".join(p.get("attention") or []) or "nothing flagged")]
        if kind == "handover":
            return "Handover summary (assistant draft, check before saving).\n" + "\n".join(lines)
        m = re.search(r"\bto ([a-z ]{3,40}?)(?: for | about |$|\.)", text, re.I)
        to = (m.group(1).strip() if m else "the specialist")
        m = re.search(r"\b(?:for|about|re:?)\s+(.{3,160})$", text, re.I)
        why = privacy.mask(m.group(1).strip())[0] if m else "review"
        return (f"Referral letter to {to} (assistant draft, a clinician approves before it is sent).\n"
                f"Reason for referral: {why}\n" + "\n".join(lines))

    def _p_handover(self, sess, text, ctx_pid, hints):
        p, card = self._need_patient(text, ctx_pid, hints, "handover", "draft a handover for")
        if card:
            return card
        draft = self._clinical_text(p, "handover", text)
        return {"card": "proposal", "patient": p, "summary": f"Add a handover note to {p['id']}'s chart",
                "changes": [{"field": "chart", "before": f"{len(p['notes'])} notes", "after": "+1 note (Addendum)"}],
                "draft": draft, "params": {"text": draft}, "needs_pin": True}

    def _p_referral(self, sess, text, ctx_pid, hints):
        p, card = self._need_patient(text, ctx_pid, hints, "referral", "draft a referral for")
        if card:
            return card
        draft = self._clinical_text(p, "referral", text)
        return {"card": "proposal", "patient": p, "summary": f"Put a referral letter for {p['id']} in Messages for approval",
                "changes": [{"field": "outbox", "before": "-", "after": "referral draft, awaiting clinician approval"}],
                "draft": draft, "params": {"text": draft}}

    # ---- safety checks -------------------------------------------------------
    def _screen(self, sess: dict, text: str) -> dict:
        """Guardrails + Nemotron reviewer on the masked command and proposal. Can only raise the tier."""
        masked = privacy.mask(text)[0]
        g = self.app.guard.check_input(masked)
        rv = self.app.reviewer.review("pre", masked, sess["user"])
        tier = worst(g["tier"], rv["tier"])
        reasons = list(g["reasons"]) + [r for r in rv["reasons"] if r not in g["reasons"]]
        return {"tier": tier, "reasons": reasons[:4], "masked": masked, "step": rv["step"]}

    def _finish(self, sess: dict, kind: str, text: str, b: dict) -> dict:
        p = b["patient"]
        chk = self._screen(sess, f"Staff command: {text}\nProposed action ({kind}): {b['summary']}\n{b.get('draft', '')}")
        status = {"green": "pending", "amber": "held", "red": "blocked"}[chk["tier"]]
        item = {"id": uuid.uuid4().hex[:10], "type": kind, "label": LABELS[kind], "status": status,
                "created": _stamp(), "proposed_by": sess["user"], "proposer_role": sess["role"],
                "permission": self.perm_for(kind), "patient_id": p["id"], "patient": self.label(p),
                "summary": b["summary"], "changes": b["changes"], "draft": b.get("draft"),
                "params": b["params"], "needs_pin": bool(b.get("needs_pin")), "tier": chk["tier"],
                "reasons": chk["reasons"], "reviewer": chk["step"], "decided_by": None, "decided": None,
                "result": None, "command_masked": chk["masked"][:300]}
        if status == "blocked":
            item["summary"] = "Blocked before it could be proposed."
            item["changes"], item["draft"], item["params"] = [], None, {}
            self.app.queue("action", "red", sess, chk["masked"][:500], chk["reasons"] or ["Reviewer: red"], None)
        self.store.add(item)
        self.app.audit.write("action_" + ("blocked" if status == "blocked" else "proposed"), sess["user"],
                             proposal_id=item["id"], type=kind, patient_id=p["id"], tier=chk["tier"])
        return {"is_action": True, "card": "proposal", "proposal": self.view(sess, item)}

    # ---- views ---------------------------------------------------------------
    def view(self, sess: dict, item: dict) -> dict:
        out = {k: v for k, v in item.items() if k not in ("params", "command_masked")}
        out["can_approve"] = item["status"] in ("pending", "held") and self.app.can(sess, item["permission"])
        out["can_reject"] = item["status"] in ("pending", "held") and (
            out["can_approve"] or item["proposed_by"] == sess["user"])
        if item["type"] in self.cfg["clinical"] and not self.app.can(sess, item["permission"]):
            out["draft"] = None
        return out

    def listing(self, sess: dict) -> list[dict]:
        out = []
        for i in reversed(self.store.all()):
            mine = i["proposed_by"] == sess["user"]
            if not (mine or self.app.can(sess, i["permission"])):
                continue
            if i["type"] in self.cfg["clinical"] and not self.app.can(sess, i["permission"]):
                continue
            out.append(self.view(sess, i))
            if len(out) >= 40:
                break
        return out

    # ---- decide --------------------------------------------------------------
    def decide(self, sess: dict, pid: str, decision: str, pin=None, confirm: bool = False,
               edits: dict | None = None) -> tuple[int, dict]:
        if decision not in ("approve", "reject"):
            return 400, {"error": "Decision must be approve or reject."}
        with self.lock:
            item = self.store.get(pid)
            if not item:
                return 404, {"error": "No such proposal."}
            if item["type"] in self.cfg["clinical"] and not self.app.can(sess, item["permission"]):
                return 403, {"error": "Only a clinical role can act on a clinical draft."}
            if item["status"] not in ("pending", "held"):
                return 409, {"error": f"This proposal is already {item['status']}."}
            if decision == "reject":
                if not (self.app.can(sess, item["permission"]) or item["proposed_by"] == sess["user"]):
                    return 403, {"error": "You cannot act on this proposal."}
                item.update(status="rejected", decided_by=sess["user"], decided=_stamp())
                self.store.put(item)
                self.app.audit.write("action_rejected", sess["user"], proposal_id=item["id"], type=item["type"],
                                     patient_id=item["patient_id"])
                return 200, {"proposal": self.view(sess, item)}
            if not self.app.can(sess, item["permission"]):
                return 403, {"error": f"Your role can't approve this. It needs a role with '{item['permission']}'."}
            if item["status"] == "held" and not confirm:
                return 409, {"error": "The safety check held this. Read the reasons, then confirm.", "held": True}
            if item["needs_pin"]:
                err = self.app.check_pin(sess, pin, "action_" + item["type"])
                if err:
                    return 403, {"error": err, "pin": True}
            if edits and isinstance(edits.get("text"), str) and item["type"] in self.cfg["clinical"]:
                chk = self._screen(sess, edits["text"][:4000])
                if chk["tier"] == "red":
                    self.app.audit.write("action_blocked", sess["user"], proposal_id=item["id"], type=item["type"],
                                         patient_id=item["patient_id"], tier="red")
                    return 409, {"error": "The edited text was blocked by the safety check.", "reasons": chk["reasons"]}
                item["params"]["text"] = edits["text"][:4000]
            try:
                result = getattr(self, "_a_" + item["type"])(sess, item)
            except (ActionError, ScheduleError, RecordError) as e:
                self.app.audit.write("action_failed", sess["user"], proposal_id=item["id"], type=item["type"],
                                     reason=privacy.mask(str(e))[0][:160])
                return 409, {"error": str(e)}
            item.update(status="approved", decided_by=sess["user"], decided=_stamp(), result=result)
            self.store.put(item)
            self.app.audit.write("action_approved", sess["user"], proposal_id=item["id"], type=item["type"],
                                 patient_id=item["patient_id"], proposed_by=item["proposed_by"])
            return 200, {"proposal": self.view(sess, item)}

    # ---- apply (only ever called from decide, after approval) ---------------
    def _a_reschedule(self, sess, item):
        q, sched = item["params"], self.app.schedule
        with sched.lock:
            src = sched.get(q["appointment_id"])
            if not src or src["status"] != "booked":
                raise ActionError("That appointment changed since the proposal. Ask again.")
            day = date.fromisoformat(q["date"])
            if self.check_slot(day, q["time"], q["clinician"]):
                raise ActionError("That time was just taken. Ask again for another time.")
            now = sched.now().isoformat(timespec="minutes")
            src["status"], src["cancel_reason"] = "cancelled", "Patient asked to reschedule"
            src["history"].append({"at": now, "by": sess["user"], "status": "cancelled"})
            new = sched._new(q["date"], q["time"], q["clinician"], src["patient_id"], src["visit_type"], sess["user"])
            new["rescheduled_from"] = src["id"]
            self.app.db.write_many([
                ("appointment", src, "rescheduled_from", f"Moved to {q['date']} {q['time']} (assistant action {item['id']})"),
                ("appointment", new, "rescheduled_to", f"Moved from {src['date']} {src['time']} (assistant action {item['id']})"),
            ], sess["user"], sess["role"])
        self.app.audit.write("appointment_rescheduled", sess["user"], appointment=new["id"], old=src["id"],
                             patient_id=new["patient_id"], date=new["date"], time=new["time"])
        return {"message": f"Moved to {self.when(new['date'], new['time'])}.", "appointment_id": new["id"]}

    def _a_book(self, sess, item):
        q = item["params"]
        a = self.app.schedule.book(sess["user"], item["patient_id"], q["date"], q["time"], q["clinician"],
                                   q["visit_type"], role=sess["role"])
        self.app.audit.write("appointment_booked", sess["user"], appointment=a["id"], patient_id=a["patient_id"],
                             date=a["date"], time=a["time"], clinician=a["clinician"])
        return {"message": f"Booked {self.when(a['date'], a['time'])}.", "appointment_id": a["id"]}

    def _a_fill_slot(self, sess, item):
        return self._a_book(sess, item)

    def _a_cancel(self, sess, item):
        q = item["params"]
        a = self.app.schedule.change_status(sess["user"], self.app.policy["roles"][sess["role"]], q["appointment_id"],
                                            "booked", "cancelled", reason=q["reason"], role=sess["role"])
        self.app.audit.write("appointment_cancelled", sess["user"], appointment=a["id"], patient_id=a["patient_id"])
        return {"message": "Cancelled.", "appointment_id": a["id"]}

    def _a_remind(self, sess, item):
        a = self.app.schedule.reminder(sess["user"], item["params"]["appointment_id"], "prepare", role=sess["role"])
        self.app.audit.write("reminder_prepared", sess["user"], appointment=a["id"])
        return {"message": "Reminder prepared. Send it, then mark it sent on the Schedule.",
                "text": self.app.schedule.reminder_text(a)}

    def _a_update_contact(self, sess, item):
        new = item["params"]["fields"]
        with self.app.lock:
            p = self.app.ehr.get(item["patient_id"])
            if not p:
                raise ActionError("No such patient.")
            for k, v in new.items():
                if k in ("plan", "member_id"):
                    ins = dict(p.get("insurance") or {})
                    ins[k] = v
                    if ins.get("plan") == "Self-pay":
                        ins["member_id"] = ""
                    p["insurance"] = ins
                else:
                    p[k] = v
            self.app.ehr.save_patient(p, sess["user"], sess["role"], "contact_updated",
                                      f"Updated {', '.join(new)} (assistant action {item['id']})")
        self.app.audit.write("contact_updated", sess["user"], patient_id=p["id"], fields=sorted(new))
        return {"message": f"Updated {', '.join(new)}."}

    def _a_handover(self, sess, item):
        _, warnings = self.app.add_entry(sess, item["patient_id"],
                                         {"kind": "note", "type": "Addendum", "text": item["params"]["text"]})
        return {"message": "Handover note added to the chart.", "warnings": warnings}

    def _a_referral(self, sess, item):
        d = self.app.outbox.add({"id": uuid.uuid4().hex[:10], "recipient_group": "referral",
                                 "draft": item["params"]["text"], "tier": "amber",
                                 "reasons": ["Drafted by an assistant action; check every line."],
                                 "status": "awaiting_approval", "drafted_by": sess["user"], "created": _stamp(),
                                 "decided_by": None, "final_text": None})
        self.app.audit.write("draft_created", sess["user"], draft_id=d["id"], recipient_group="referral", tier="amber")
        return {"message": "Referral draft is in Messages, waiting for a second clinician to approve.",
                "draft_id": d["id"]}

    # ---- HTTP (called from the delimited block in server.py) ----------------
    def handle_get(self, sess: dict, path: str) -> tuple[int, dict]:
        if path == "/api/actions/help":
            return 200, self.help(sess)
        if path == "/api/actions":
            if not self.can_propose(sess) and not any(self.app.can(sess, p) for p in set(self.cfg["permissions"].values())):
                return 403, {"error": "Your role has no assistant actions."}
            return 200, self.listing(sess)
        return 404, {"error": "Not found."}

    def handle_post(self, sess: dict, path: str, data: dict) -> tuple[int, dict]:
        if path == "/api/actions/propose":
            if not self.can_propose(sess):
                return 403, {"error": "Your role cannot use assistant actions."}
            text = str(data.get("message", "")).strip()[:600]
            if not text:
                return 400, {"error": "Empty message."}
            ctx = str(data.get("patient_id") or "") or None
            if ctx and not self.app.can(sess, "view_patients"):
                ctx = None
            hints = data.get("hints") if isinstance(data.get("hints"), dict) else {}
            hints = {k: str(v)[:40] for k, v in hints.items()
                     if k in ("patient_id", "appointment_id", "date", "time", "clinician", "intent", "visit_type")}
            if hints.get("date"):
                try:
                    date.fromisoformat(hints["date"])
                except ValueError:
                    return 400, {"error": "Bad date."}
            if hints.get("clinician") and hints["clinician"] not in self.clinicians():
                return 400, {"error": "Unknown clinician."}
            try:
                return 200, self.propose(sess, text, ctx, hints)
            except PermissionError as e:
                return 403, {"error": str(e)}
        if path == "/api/actions/decide":
            return self.decide(sess, str(data.get("id", "")), str(data.get("decision", "")), data.get("pin"),
                               data.get("confirm") is True, data.get("edits") if isinstance(data.get("edits"), dict) else None)
        return 404, {"error": "Not found."}
