"""Verify Clinic Assistant's local stores without starting the app.

    python3 scripts/verify_stores.py            # checks data/ in this folder
    python3 scripts/verify_stores.py path/to/data

Checks:
  1. vectors.sqlite: every row's SHA-256 hash chain links back to the genesis hash.
  2. vectors.sqlite: the append-only triggers refuse UPDATE and DELETE (tested on a temporary copy).
  3. vectors.sqlite: a tampered row is detected (tested on a temporary copy).
  4. audit.jsonl and chart_history.jsonl, if present: hash chains are intact.
Exit code 0 means every check passed.
"""
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.audit import AuditLog  # noqa: E402
from app.vectorstore import VectorStore  # noqa: E402


class _NoEmbed:  # verification never embeds, so no model is needed
    mode = "verify-only"


def open_store(path: Path) -> VectorStore:
    return VectorStore(path, _NoEmbed())


def main() -> int:
    data = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data"
    failed = False
    vec = data / "vectors.sqlite"
    if not vec.exists():
        print(f"no vector store at {vec}")
        return 1
    store = open_store(vec)
    counts = dict(store.db.execute("SELECT collection, COUNT(*) FROM vectors GROUP BY collection").fetchall())
    result = store.verify()
    print(f"vectors.sqlite chain: {result}  collections: {counts}")
    failed |= not result["ok"]

    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "vectors.sqlite"
        shutil.copy(vec, copy)
        db = sqlite3.connect(copy)
        for sql in ("UPDATE vectors SET text='edited' WHERE seq=1", "DELETE FROM vectors WHERE seq=1"):
            try:
                db.execute(sql)
                print(f"FAIL: append-only trigger let this through: {sql}")
                failed = True
            except sqlite3.DatabaseError as e:
                print(f"refused as expected: {sql.split()[0]} -> {e}")
        # Bypass the triggers the way an attacker with file access could, and check the chain catches it.
        db.execute("DROP TRIGGER no_update")
        db.execute("UPDATE vectors SET text = text || ' (tampered)' WHERE seq = 3")
        db.commit()
        db.close()
        tampered_store = open_store(copy)
        tampered = tampered_store.verify()
        tampered_store.db.close()  # Windows cannot delete the temp copy while it is open
        print(f"tampered copy chain: {tampered}")
        failed |= tampered.get("ok", True)

    for name in ("audit.jsonl", "chart_history.jsonl"):
        p = data / name
        if p.exists():
            r = AuditLog(p).verify()
            print(f"{name} chain: {r}")
            failed |= not r["ok"]

    print("ALL CHECKS PASSED" if not failed else "SOME CHECKS FAILED")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
