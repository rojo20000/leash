"""Compose the prompt-injection corpus from N4's phrase banks (see graph/briefs/N4.md, CONTRACTS.md C2.4).

    .venv/Scripts/python.exe data/corpus/expand.py            # validate banks, write data/corpus/corpus.jsonl
    .venv/Scripts/python.exe data/corpus/expand.py --validate # validate only

Train/test are split by bank line: injection and benign-imperative lines whose index % 4 == 0 appear only in
test examples, so test precision/recall measure phrasing the classifier never saw. Deterministic (seed 1337).
"""
import argparse
import json
import random
import re
import string
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SEED = 1337
PER_CLASS = 600
MIN_LINES = {"openings": 40, "findings": 60, "plans": 40, "benign_imperatives": 80, "injections": 100}
SLOTS = {
    "name": ["Ana Rivera", "James Okafor", "Mei Chen", "Robert Hale", "Fatima Noor", "Luis Ortega",
             "Grace Kim", "Samuel Price", "Olivia Brandt", "Arjun Mehta", "Nora Lindqvist", "Peter Novak"],
    "age": [str(a) for a in range(19, 91, 3)],
    "sex": ["male", "female"],
    "condition": ["type 2 diabetes", "hypertension", "atrial fibrillation", "asthma", "COPD", "chronic kidney disease",
                  "hypothyroidism", "migraine", "osteoarthritis of the knee", "heart failure", "depression", "GERD"],
    "med": ["metformin 500 mg", "lisinopril 10 mg", "apixaban 5 mg", "albuterol inhaler", "levothyroxine 50 mcg",
            "atorvastatin 20 mg", "sertraline 50 mg", "omeprazole 20 mg", "furosemide 40 mg", "sumatriptan 50 mg"],
    "date": ["2026-11-24", "2026-11-28", "2026-12-02", "2026-12-05", "2026-12-09", "next Tuesday", "next week"],
    "clinic": ["Lakeside Family Medicine", "Northgate Cardiology", "Riverbend Internal Medicine",
               "Westfield Pulmonary Clinic", "Cedar Hill Endocrinology", "Harbor View Orthopedics"],
    "staff": ["Dr. Patel", "Dr. Alvarez", "Nurse Kim", "Dr. Osei", "the front desk", "the care coordinator"],
    "ext_email": ["records-transfer@outside-clinic.example", "intake@records-review.example",
                  "billing.audit@thirdparty.example", "archive@offsite-storage.example", "verify@insure-check.example"],
    "phone": ["555-201-0042", "555-310-7781", "555-422-1934", "555-118-6620"],
}


def load_bank(banks: Path, name: str, minimum: int) -> list[str]:
    path = banks / f"{name}.txt"
    if not path.exists():
        sys.exit(f"FAIL missing bank file {path}")
    lines, errors = [], []
    for n, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if not line.isascii():
            errors.append(f"{path.name}:{n} non-ASCII character")
        if len(line) > 300:
            errors.append(f"{path.name}:{n} longer than 300 characters")
        for _, field, _, _ in string.Formatter().parse(line):
            if field is not None and field not in SLOTS:
                errors.append(f"{path.name}:{n} unknown slot {{{field}}}")
        if line in lines:
            errors.append(f"{path.name}:{n} duplicate line")
        lines.append(line)
    if len(lines) < minimum:
        errors.append(f"{path.name}: {len(lines)} lines, need at least {minimum}")
    if errors:
        sys.exit("FAIL\n" + "\n".join(errors))
    return lines


def fill(line: str, rng: random.Random) -> str:
    return line.format(**{k: rng.choice(v) for k, v in SLOTS.items()})


def compose(rng, banks, special: str | None) -> str:
    """opening + 2-4 body sentences (findings, special inserted at a random spot) + 1-2 plans."""
    body = [fill(rng.choice(banks["findings"]), rng) for _ in range(rng.randint(1, 3))]
    if special is None:
        body.append(fill(rng.choice(banks["findings"]), rng))  # keep length comparable to notes with a special line
    else:
        body.insert(rng.randint(0, len(body)), fill(special, rng))
    plans = [fill(p, rng) for p in rng.sample(banks["plans"], rng.randint(1, 2))]
    sents = [fill(rng.choice(banks["openings"]), rng)] + body + plans
    return re.sub(r"\s+", " ", " ".join(sents)).strip()


def build(banks: dict[str, list[str]]) -> list[dict]:
    rng = random.Random(SEED)
    rows = []

    def pick(kind, prefix, split):
        idx = [i for i in range(len(banks[kind])) if (i % 4 == 0) == (split == "test")]
        i = rng.choice(idx)
        return banks[kind][i], f"{prefix}-{i:03d}"

    for n in range(PER_CLASS):
        split = "test" if n % 4 == 0 else "train"
        line, tid = pick("injections", "inj", split)
        rows.append({"text": compose(rng, banks, line), "label": 1, "label_name": "injected",
                     "split": split, "hard_negative": False, "template": tid})
    for n in range(PER_CLASS):
        split = "test" if n % 4 == 0 else "train"
        if n % 2 == 0:
            line, tid = pick("benign_imperatives", "imp", split)
            rows.append({"text": compose(rng, banks, line), "label": 0, "label_name": "benign",
                         "split": split, "hard_negative": True, "template": tid})
        else:
            rows.append({"text": compose(rng, banks, None), "label": 0, "label_name": "benign",
                         "split": split, "hard_negative": False, "template": "plain"})
    rng.shuffle(rows)
    return [{"id": f"c-{i:05d}", **r} for i, r in enumerate(rows, 1)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--banks", default=str(HERE / "banks"))
    ap.add_argument("--out", default=str(HERE / "corpus.jsonl"))
    ap.add_argument("--validate", action="store_true", help="check the banks only, write nothing")
    ap.add_argument("--min-scale", type=float, default=1.0, help=argparse.SUPPRESS)  # self-test only
    a = ap.parse_args()
    banks = {k: load_bank(Path(a.banks), k, max(1, int(m * a.min_scale))) for k, m in MIN_LINES.items()}
    print("banks ok: " + ", ".join(f"{k}={len(v)}" for k, v in banks.items()))
    if a.validate:
        return
    rows = build(banks)
    # self-check: split by template is clean and class balance holds
    train_t = {r["template"] for r in rows if r["split"] == "train" and r["template"] != "plain"}
    test_t = {r["template"] for r in rows if r["split"] == "test" and r["template"] != "plain"}
    assert not train_t & test_t, "template leaked across splits"
    with open(a.out, "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    count = lambda **kw: sum(all(r[k] == v for k, v in kw.items()) for r in rows)  # noqa: E731
    print(f"wrote {len(rows)} rows to {a.out}: injected={count(label=1)} benign={count(label=0)} "
          f"hard_negative={count(hard_negative=True)} test={count(split='test')} "
          f"unique_texts={len({r['text'] for r in rows})}")


if __name__ == "__main__":
    main()
