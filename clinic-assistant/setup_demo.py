"""First-run setup for the demo: makes sure there are accounts to sign in with.

Run by "Start Clinic Assistant.command". Safe to run again; it never changes existing accounts.
"""
import getpass
import json
import shutil
import sys
from pathlib import Path

from app import VERSION
from app.users import UserStore

ROOT = Path(__file__).resolve().parent
USERS = ROOT / "data" / "users.json"
DEMO = [("dr_lee", "clinician"), ("desk_sam", "receptionist"), ("nurse_kim", "nurse"), ("lead_ana", "clinical_lead"),
        ("auditor_ray", "auditor"), ("net_ops", "network_engineer"),
        ("admin_kai", "admin"), ("pt_lena", "patient")]
LINKS = {"pt_lena": "syn-002"}  # patient portal accounts: username -> the one patient record it may see


def has_accounts(path: Path) -> bool:
    try:
        return bool(json.loads(path.read_text()))
    except (OSError, ValueError):
        return False


def fill_missing() -> None:
    """Add demo accounts that are new in this version, with the same password as the existing demo accounts."""
    try:
        users = json.loads(USERS.read_text())
    except (OSError, ValueError):
        return
    base = users.get("dr_lee") or next(iter(users.values()), None)
    added = []
    for name, role in DEMO:
        if name not in users and base:
            users[name] = {"role": role, "salt": base["salt"], "hash": base["hash"], "active": True}
            if name in LINKS:
                users[name]["patient_id"] = LINKS[name]
            added.append(f"{name} ({role.replace('_', ' ')})")
    if added:
        USERS.write_text(json.dumps(users, indent=2))
        USERS.chmod(0o600)
        print("Added new demo account(s), same password as your others: " + ", ".join(added))


def main() -> None:
    print(f"Clinic Assistant {VERSION}, running from {ROOT}")
    if has_accounts(USERS):
        fill_missing()
        return
    # Reuse accounts from an earlier copy, so the same sign-ins keep working.
    home = Path.home()
    found = [*home.glob("Downloads/clinic-assistant*/data/users.json"),
             *home.glob("Downloads/*/clinic-assistant*/data/users.json")]  # shallow: never walks other projects
    for old in sorted(found):
        if old.resolve() != USERS.resolve() and "leash" not in old.parts and has_accounts(old):
            USERS.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(old, USERS)
            print(f"Copied your existing accounts from {old.parent.parent}")
            fill_missing()
            return
    policy = json.loads((ROOT / "config" / "policy.json").read_text())
    store = UserStore(USERS, policy["roles"])
    print("\nFirst run: let's create the demo accounts.")
    print(f"Pick ONE password (12+ characters). All {len(DEMO)} demo accounts will use it.")
    while True:
        pw = getpass.getpass("Password: ")
        if len(pw) < 12:
            print("Needs at least 12 characters. Try again.")
            continue
        if pw != getpass.getpass("Type it again: "):
            print("Those didn't match. Try again.")
            continue
        break
    for name, role in DEMO:
        store.add(name, pw, role, patient_id=LINKS.get(name))
    print("\nSign in with any of these (same password):")
    for name, role in DEMO:
        print(f"  {name:12} {role.replace('_', ' ')}" + (f" (portal for {LINKS[name]})" if name in LINKS else ""))
    print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(1)
