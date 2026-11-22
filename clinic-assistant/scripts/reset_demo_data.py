"""Reset Clinic Assistant's data to the shared synthetic demo state.

    python3 scripts/reset_demo_data.py            # back up data/, then rebuild it
    python3 scripts/reset_demo_data.py --check    # only report what is there and whether chains verify

What it does:
  1. Moves everything in data/ except users.json into data/backups/<timestamp>/ (nothing is deleted).
  2. Rebuilds data/clinic.db (40 synthetic patients, today's and tomorrow's appointments, empty change
     and conversation logs apart from the seed) and data/vectors.sqlite, exactly as a first start would.
     Patients are generated from a fixed seed, so every teammate gets the same records.
  3. Verifies every hash chain and prints the result.
Accounts (users.json) are kept. Stop the app before running this.
"""
import os
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
sys.path.insert(0, str(ROOT))
os.environ["MOCK_LLM"] = "1"  # building data never needs a model


def check() -> int:
    from app.audit import AuditLog
    from app.db import ClinicDB
    bad = 0
    db = DATA / "clinic.db"
    if db.exists():
        c = ClinicDB(db)
        s = c.status()
        ok, n, at = c.verify_chain()
        cok, cn, cat = c.verify_conversations()
        print(f"clinic.db: {s['patients']} patients, {s['appointments']} appointments, "
              f"change log {'OK' if ok else f'BROKEN at seq {at}'} ({n}), "
              f"conversations {'OK' if cok else f'BROKEN at {cat}'} ({cn})")
        bad += (not ok) + (not cok)
        c.close()
    else:
        print("clinic.db: missing (it is created on first start)")
    vec = DATA / "vectors.sqlite"
    if vec.exists():
        import sqlite3
        from app.vectorstore import VectorStore

        class _NoEmbed:
            mode = "verify-only"
        r = VectorStore(vec, _NoEmbed()).verify()
        print(f"vectors.sqlite: {r}")
        bad += not r["ok"]
    for name in ("audit.jsonl", "chart_history.jsonl"):
        p = DATA / name
        if p.exists():
            r = AuditLog(p).verify()
            print(f"{name}: {r}")
            bad += not r["ok"]
    return 1 if bad else 0


def reset() -> int:
    DATA.mkdir(exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup = DATA / "backups" / stamp
    moved = []
    for p in DATA.iterdir():
        if p.name in ("users.json", "backups") or p.name.startswith("."):
            continue
        backup.mkdir(parents=True, exist_ok=True)
        shutil.move(str(p), str(backup / p.name))
        moved.append(p.name)
    if moved:
        print(f"Backed up {', '.join(sorted(moved))} to {backup.relative_to(ROOT)}")
    from app.server import App
    App(root=ROOT, data_dir=DATA)
    print("Rebuilt the synthetic demo data.")
    return check()


if __name__ == "__main__":
    sys.exit(check() if "--check" in sys.argv else reset())
