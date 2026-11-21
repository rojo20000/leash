"""Check the clinic database: what is in it, and whether its change log is intact.

Run from the app folder:  python3 scripts/verify_db.py  [path/to/clinic.db]
Read-only: it never changes the database. Exit code 0 = chain intact, 1 = tampering found, 2 = no database.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.db import ClinicDB  # noqa: E402

path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "clinic.db"
if not path.exists():
    print(f"No database at {path}. Start the app once (python3 run.py) to create it.")
    sys.exit(2)
db = ClinicDB(path)
s = db.status()
ok, checked, bad = db.verify_chain()
print(f"Database:      {path}")
print(f"Engine:        {s['engine']}")
print(f"Patients:      {s['patients']}")
print(f"Appointments:  {s['appointments']}")
print(f"Changes:       {s['changes']}")
if ok:
    print(f"Change log:    OK, all {checked} entries verified (hash chain intact, edits and deletes blocked)")
else:
    print(f"Change log:    TAMPERED. First bad entry is seq {bad} ({checked} entries before it are fine)")
cok, cn, cbad = db.verify_conversations()
print(f"Conversations: {s['conversations']} ({'OK, chain intact' if cok else f'TAMPERED at seq {cbad}'})")
ok = ok and cok
print("\nLatest changes:")
for h in db.history(None, 10):
    print(f"  #{h['seq']:<5} {h['at']}  {h['by'] or '-':<12} {h['action']:<14} {h['entity']} {h['entity_id']}: {h['summary']}")
db.close()
sys.exit(0 if ok else 1)
