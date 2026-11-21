"""Span-level precision/recall of ml.minimize on synthetic notes with planted identifiers."""
import sys, os as _o
sys.path.insert(0, _o.path.dirname(_o.path.dirname(_o.path.abspath(__file__))))
import json
import random
from collections import defaultdict

from gateway.core_loader import load_core
from ml.common import SEED, now, p, write_metrics
from ml.minimize import find_spans

N_NOTES = 240
# (text with {slots}); slots are planted identifiers, everything else is literal/distractor text
TEMPLATES = [
    "Referral for {NAME}. DOB: {DOB}. MRN: {MRN}. Phone: {PHONE}. Reason: chest pain, start {DOSE} daily. BP {BP}. Follow-up on {APPT}.",
    "Patient {NAME} (SSN {SSN}) called from {PHONE} about the visit on {APPT}. Last BP {BP}; continue {DOSE}.",
    "Please confirm the appointment on {APPT} for {NAME}, MRN {MRN}. Email {EMAIL} or phone {PHONE}. Dose remains {DOSE}.",
    "{NAME}, born {DOB}, social security number {SSN}. Blood pressure was {BP} at the last visit; next appointment {APPT}.",
    "Discharge note: {NAME} reachable at {EMAIL}. Record {MRN}. Reduce dose to {DOSE} and recheck BP ({BP}) on {APPT}.",
]
KINDS = ["SSN", "MRN", "PHONE", "EMAIL", "DOB"]


def notes():
    rng = random.Random(SEED)
    pats = [e["resource"] for e in json.load(open(p("data", "generated", "fhir_bundle.json")))["entry"]
            if e["resource"]["resourceType"] == "Patient"]
    for i in range(N_NOTES):
        pt = pats[i % len(pats)]
        ids = {i["system"].rsplit("/", 1)[-1].rsplit(":", 1)[-1]: i["value"] for i in pt["identifier"]}
        tel = {t["system"]: t["value"] for t in pt["telecom"]}
        n = pt["name"][0]
        slot = {"NAME": f"{n['given'][0]} {n['family']}", "DOB": pt["birthDate"], "MRN": ids["mrn"], "SSN": ids["us-ssn"],
                "PHONE": tel["phone"], "EMAIL": tel["email"],
                "DOSE": rng.choice(["500 mg", "20 mg", "1000 mg", "2.5 mg", "81 mg"]),
                "BP": f"{rng.randint(105, 160)}/{rng.randint(65, 100)}",
                "APPT": rng.choice([f"2026-12-{rng.randint(1, 28):02d}", f"{rng.randint(1, 12):02d}/{rng.randint(1, 28):02d}/2026",
                                    "December 3rd"])}
        text, planted, pos = "", [], 0
        tpl = TEMPLATES[rng.randrange(len(TEMPLATES))]
        for part in __import__("re").split(r"(\{\w+\})", tpl):
            if part.startswith("{"):
                k = part[1:-1]
                if k in KINDS:
                    planted.append((k, len(text), len(text) + len(slot[k])))
                text += slot[k]
            else:
                text += part
        yield text, planted


def evaluate():
    core = load_core()
    tp_p, n_pred, tp_r, n_true = defaultdict(int), defaultdict(int), defaultdict(int), defaultdict(int)
    n = 0
    for text, planted in notes():
        n += 1
        pred = [(k, s, e) for k, s, e, _ in find_spans(text, core)]
        ov = lambda a, b: a[0] == b[0] and a[1] < b[2] and b[1] < a[2]
        for a in pred:
            n_pred[a[0]] += 1
            tp_p[a[0]] += any(ov(a, b) for b in planted)
        for b in planted:
            n_true[b[0]] += 1
            tp_r[b[0]] += any(ov(a, b) for a in pred)
    f = lambda a, b: round(a / b, 4) if b else None
    by = {k: {"precision": f(tp_p[k], n_pred[k]), "recall": f(tp_r[k], n_true[k]), "n_spans": n_true[k]}
          for k in sorted(set(n_pred) | set(n_true))}
    res = {"precision": f(sum(tp_p.values()), sum(n_pred.values())), "recall": f(sum(tp_r.values()), sum(n_true.values())),
           "n_notes": n, "n_spans": sum(n_true.values()), "by_kind": by, "generated_at": now()}
    write_metrics("minimization", res)
    return res


if __name__ == "__main__":
    print(json.dumps(evaluate(), indent=2))
