"""Create, disable or list accounts.

  python3 manage_users.py add dr_lee clinician
  python3 manage_users.py add pt_lena patient syn-002   (a patient account is linked to one patient id)
  python3 manage_users.py disable dr_lee
  python3 manage_users.py list
"""
import getpass
import json
import sys
from pathlib import Path

from app.db import ClinicDB
from app.users import UserStore

ROOT = Path(__file__).parent
policy = json.loads((ROOT / "config" / "policy.json").read_text())
patient_role = policy["portal"]["patient_role"]
store = UserStore(ROOT / "data" / "users.json", policy["roles"], patient_role)

if len(sys.argv) < 2:
    sys.exit(__doc__)
cmd = sys.argv[1]
if cmd == "add" and len(sys.argv) in (4, 5):
    user, role = sys.argv[2], sys.argv[3]
    pid = sys.argv[4] if len(sys.argv) == 5 else None
    if (role == patient_role) != (pid is not None):
        sys.exit(f"A {patient_role} account needs a patient id, and only a {patient_role} account takes one.")
    if pid is not None:
        db_path = ROOT / "data" / "clinic.db"
        if not db_path.exists():  # ClinicDB would create an empty one
            sys.exit("data/clinic.db not found. Start the app once (or run setup_demo.py) first.")
        db = ClinicDB(db_path)
        found = db.patient(pid)
        db.close()
        if not found:
            sys.exit(f"No patient with id {pid} in data/clinic.db.")
    pw = getpass.getpass("Password (12+ characters): ")
    if pw != getpass.getpass("Repeat password: "):
        sys.exit("Passwords did not match.")
    store.add(user, pw, role, pid)
    print(f"Added {user} as {role}" + (f", linked to patient {pid}." if pid else "."))
elif cmd == "disable" and len(sys.argv) == 3:
    store.disable(sys.argv[2])
    print(f"Disabled {sys.argv[2]}.")
elif cmd == "list":
    for name, role, active in store.list():
        pid = store.patient_id(name)
        print(f"{name:20} {role:10} {'active' if active else 'disabled'}" + (f"  patient {pid}" if pid else ""))
else:
    sys.exit(__doc__)
