"""Create, disable or list accounts.

  python3 manage_users.py add dr_lee clinician
  python3 manage_users.py disable dr_lee
  python3 manage_users.py list
"""
import getpass
import json
import sys
from pathlib import Path

from app.users import UserStore

ROOT = Path(__file__).parent
policy = json.loads((ROOT / "config" / "policy.json").read_text())
store = UserStore(ROOT / "data" / "users.json", policy["roles"])

if len(sys.argv) < 2:
    sys.exit(__doc__)
cmd = sys.argv[1]
if cmd == "add" and len(sys.argv) == 4:
    pw = getpass.getpass("Password (12+ characters): ")
    if pw != getpass.getpass("Repeat password: "):
        sys.exit("Passwords did not match.")
    store.add(sys.argv[2], pw, sys.argv[3])
    print(f"Added {sys.argv[2]} as {sys.argv[3]}.")
elif cmd == "disable" and len(sys.argv) == 3:
    store.disable(sys.argv[2])
    print(f"Disabled {sys.argv[2]}.")
elif cmd == "list":
    for name, role, active in store.list():
        print(f"{name:20} {role:10} {'active' if active else 'disabled'}")
else:
    sys.exit(__doc__)
