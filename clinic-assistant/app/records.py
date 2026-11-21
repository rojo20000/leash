"""Adding patients and chart entries, with strict input checks.

Nothing here edits or deletes what is already in a chart. Every change is an
addition: a new note, a new result, a medicine stopped (kept, with the date and
reason), a flag resolved (kept, with how). Each change is also written to the
hash-chained change log in the clinic database (data/clinic.db), so the record of what was
learned about a patient, and who added it, can be reviewed later and can't be
quietly rewritten.
"""
from __future__ import annotations

import re
from datetime import date, datetime

PLANS = ["Medicare", "Medicaid", "Commercial PPO", "Commercial HMO", "Self-pay"]
CONTACT = ["Text message", "Phone call", "Patient portal"]
LANGUAGES = ["English", "Spanish", "Vietnamese", "Somali", "Other"]
SEXES = ["female", "male", "other"]
NOTE_TYPES = ["Visit note", "Finding (what we learned)", "Phone call", "Addendum"]

# Results staff pick from a list, each with a unit, a reference range and a hard limit on what is physically possible.
RESULTS = {
    "Blood pressure": ("mmHg", "<130/80", None),
    "Heart rate": ("bpm", "60-100", (20, 250)),
    "Temperature": ("C", "36.1-37.2", (30, 44)),
    "Weight": ("kg", "", (1, 350)),
    "SpO2 at rest": ("%", ">94", (50, 100)),
    "HbA1c": ("%", "4.0-5.6", (3, 20)),
    "Potassium": ("mmol/L", "3.5-5.1", (1.5, 9)),
    "Creatinine": ("mg/dL", "0.6-1.2", (0.1, 20)),
    "eGFR": ("mL/min/1.73m2", ">60", (1, 150)),
    "INR": ("", "2.0-3.0 target", (0.5, 12)),
    "Hemoglobin": ("g/dL", "12.0-15.5", (3, 25)),
    "TSH": ("mIU/L", "0.4-4.0", (0.01, 150)),
    "LDL cholesterol": ("mg/dL", "<100", (10, 500)),
    "PHQ-9 score": ("", "0-4 minimal", (0, 27)),
}

# A new medicine that belongs to a family the patient is allergic to must be confirmed on purpose.
ALLERGY_FAMILIES = {
    "penicillin": ["penicillin", "amoxicillin", "ampicillin", "piperacillin", "augmentin", "dicloxacillin"],
    "sulfa": ["sulfamethoxazole", "bactrim", "septra", "sulfasalazine"],
    "codeine": ["codeine", "tylenol #3"],
    "ace inhibitor": ["lisinopril", "enalapril", "ramipril", "benazepril", "captopril"],
    "nsaid": ["ibuprofen", "naproxen", "diclofenac", "aspirin"],
}

NAME = re.compile(r"^[A-Za-z][A-Za-z' -]{0,38}[A-Za-z]$")
PHONE = re.compile(r"^(\d{3}-)?\d{3}-\d{4}$")
MEMBER = re.compile(r"^[A-Z0-9]{6,12}$")
BP = re.compile(r"^(\d{2,3})/(\d{2,3})$")


class RecordError(Exception):
    """A refused entry. The message tells the person exactly what to fix."""


def _text(data: dict, key: str, label: str, lo: int, hi: int) -> str:
    v = str(data.get(key, "")).strip()
    v = re.sub(r"\s+", " ", v) if key != "text" else v
    if not lo <= len(v) <= hi:
        raise RecordError(f"{label} must be {lo} to {hi} characters.")
    return v


def _pick(data: dict, key: str, label: str, options: list[str]) -> str:
    v = data.get(key)
    if v not in options:
        raise RecordError(f"Pick {label} from the list.")
    return v


def validate_patient(data: dict, today: date) -> dict:
    given = _text(data, "given", "First name", 2, 40)
    family = _text(data, "family", "Last name", 2, 40)
    for v, label in ((given, "First name"), (family, "Last name")):
        if not NAME.match(v):
            raise RecordError(f"{label} can only use letters, spaces, hyphens and apostrophes.")
    try:
        born = date.fromisoformat(str(data.get("birthDate", "")))
    except ValueError:
        raise RecordError("Birth date must be a real date.") from None
    if born > today:
        raise RecordError("Birth date can't be in the future.")
    age = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
    if age > 120:
        raise RecordError("Birth date is more than 120 years ago. Check the year.")
    phone = str(data.get("phone", "")).strip()
    if not PHONE.match(phone):
        raise RecordError("Phone must look like 555-0123 or 555-555-0123.")
    address = _text(data, "address", "Address", 5, 80)
    plan = _pick(data, "plan", "an insurance plan", PLANS)
    member = str(data.get("member_id", "")).strip().upper()
    if plan == "Self-pay":
        member = ""
    elif not MEMBER.match(member):
        raise RecordError("Insurance member ID must be 6 to 12 letters or digits, as printed on the card.")
    return {"given": given, "family": family, "birthDate": born.isoformat(), "age": age,
            "sex": _pick(data, "sex", "sex", SEXES), "phone": phone, "address": address,
            "insurance": {"plan": plan, "member_id": member},
            "preferred_contact": _pick(data, "preferred_contact", "a contact preference", CONTACT),
            "language": _pick(data, "language", "a language", LANGUAGES)}


def _num(v: str) -> float | None:
    try:
        return float(v)
    except ValueError:
        return None


def validate_entry(p: dict, data: dict, today: date) -> tuple[str, dict]:
    """Return (summary sentence, change) for one chart addition, or raise RecordError."""
    kind = data.get("kind")
    stamp = today.isoformat()
    if kind == "note":
        ntype = _pick(data, "type", "a note type", NOTE_TYPES)
        text = _text(data, "text", "The note", 5, 4000)
        return f"Added a {ntype.lower()}", {"kind": kind, "type": ntype, "text": text, "date": stamp}
    if kind == "result":
        name = _pick(data, "name", "a test", list(RESULTS))
        unit, ref, limits = RESULTS[name]
        value = str(data.get("value", "")).strip()
        if name == "Blood pressure":
            m = BP.match(value)
            if not m or not (50 <= int(m[1]) <= 260 and 30 <= int(m[2]) <= 160 and int(m[1]) > int(m[2])):
                raise RecordError("Blood pressure must look like 128/82, top number higher than the bottom.")
        else:
            n = _num(value)
            if n is None:
                raise RecordError(f"{name} must be a number.")
            if limits and not limits[0] <= n <= limits[1]:
                raise RecordError(f"{name} {value} {unit} isn't possible. Allowed range is "
                                  f"{limits[0]} to {limits[1]}. Check for a typo.")
            value = int(n) if n == int(n) and name in ("Heart rate", "PHQ-9 score", "eGFR") else n
        return (f"Added result {name} {value} {unit}".strip(),
                {"kind": kind, "name": name, "value": value, "unit": unit, "ref": ref, "date": stamp})
    if kind in ("condition", "allergy", "attention"):
        text = _text(data, "text", "The entry", 3, 120)
        field = {"condition": "conditions", "allergy": "allergies", "attention": "attention"}[kind]
        if text.lower() in (x.lower() for x in p[field]):
            raise RecordError("That's already in the chart.")
        label = {"condition": "condition", "allergy": "allergy", "attention": "thing to check"}[kind]
        return f"Added {label}: {text}", {"kind": kind, "text": text}
    if kind == "medication":
        text = _text(data, "text", "The medicine", 3, 120)
        if text.lower() in (x.lower() for x in p["medications"]):
            raise RecordError("That medicine is already listed.")
        low = text.lower()
        clash = [a for a in p["allergies"] for fam, words in ALLERGY_FAMILIES.items()
                 if fam in a.lower() and any(w in low for w in words)]
        if clash and data.get("confirm_allergy") is not True:
            raise RecordError(f"ALLERGY: this patient has '{clash[0]}'. If you really mean to add it, "
                              "tick the allergy override box and add it again.")
        return (f"Added medicine: {text}" + (" (allergy override)" if clash else ""),
                {"kind": kind, "text": text, "allergy_override": bool(clash)})
    if kind == "stop_medication":
        text = str(data.get("text", ""))
        if text not in p["medications"]:
            raise RecordError("Pick the medicine to stop from the list.")
        reason = _text(data, "reason", "The reason", 3, 120)
        return f"Stopped medicine: {text} ({reason})", {"kind": kind, "text": text, "reason": reason, "date": stamp}
    if kind == "resolve_attention":
        text = str(data.get("text", ""))
        if text not in p["attention"]:
            raise RecordError("Pick the item to resolve from the list.")
        how = _text(data, "reason", "What was done", 3, 160)
        return f"Resolved: {text} ({how})", {"kind": kind, "text": text, "reason": how, "date": stamp}
    raise RecordError("Pick what you're adding.")


def apply_entry(p: dict, change: dict, by: str) -> None:
    kind = change["kind"]
    if kind == "note":
        p["notes"].append({"date": change["date"], "type": change["type"], "author": by, "text": change["text"]})
    elif kind == "result":
        p["observations"].append({k: change[k] for k in ("name", "value", "unit", "ref", "date")})
    elif kind == "condition":
        p["conditions"].append(change["text"])
    elif kind == "allergy":
        if p["allergies"] == ["No known allergies"]:
            p["allergies"] = []
        p["allergies"].append(change["text"])
    elif kind == "attention":
        p["attention"].append(change["text"])
    elif kind == "medication":
        p["medications"].append(change["text"])
    elif kind == "stop_medication":
        p["medications"].remove(change["text"])
        p.setdefault("stopped_medications", []).append(
            {"text": change["text"], "reason": change["reason"], "date": change["date"], "by": by})
    elif kind == "resolve_attention":
        p["attention"].remove(change["text"])
        p.setdefault("resolved", []).append(
            {"text": change["text"], "reason": change["reason"], "date": change["date"], "by": by})


def now_stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")
