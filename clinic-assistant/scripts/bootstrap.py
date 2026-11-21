"""One-command setup for people and agents: accounts, data, checks.

    python3 scripts/bootstrap.py

- Creates the demo accounts if there are none. The password comes from the environment variable
  CLINIC_DEMO_PASSWORD (12+ characters) so agents can run this without a prompt; if it is not set, you
  are asked for one. The password is never written anywhere except as a salted hash in data/users.json,
  which git ignores.
- Makes sure data/clinic.db and data/vectors.sqlite exist (the committed synthetic snapshot, or a fresh
  build if they are missing) and that every hash chain verifies.
- Prints how to start the app.
Safe to run again: it never changes existing accounts or data.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from setup_demo import DEMO, USERS, has_accounts  # noqa: E402
from app.users import UserStore  # noqa: E402


def accounts() -> None:
    if has_accounts(USERS):
        print(f"Accounts: already set up in {USERS.relative_to(ROOT)} (kept).")
        return
    pw = os.environ.get("CLINIC_DEMO_PASSWORD", "")
    if not pw:
        print("No accounts yet and CLINIC_DEMO_PASSWORD is not set; running the interactive setup.")
        subprocess.run([sys.executable, str(ROOT / "setup_demo.py")], cwd=ROOT, check=True)
        return
    if len(pw) < 12:
        sys.exit("CLINIC_DEMO_PASSWORD must be at least 12 characters.")
    policy = json.loads((ROOT / "config" / "policy.json").read_text())
    store = UserStore(USERS, policy["roles"])
    for name, role in DEMO:
        store.add(name, pw, role)
    print("Accounts created (password from CLINIC_DEMO_PASSWORD): " + ", ".join(f"{n} ({r})" for n, r in DEMO))


def data() -> int:
    if not (ROOT / "data" / "clinic.db").exists() or not (ROOT / "data" / "vectors.sqlite").exists():
        return subprocess.run([sys.executable, str(ROOT / "scripts" / "reset_demo_data.py")], cwd=ROOT).returncode
    return subprocess.run([sys.executable, str(ROOT / "scripts" / "reset_demo_data.py"), "--check"], cwd=ROOT).returncode


if __name__ == "__main__":
    accounts()
    rc = data()
    py = "python" if os.name == "nt" else "python3"
    print("\nStart:  " + py + " run.py   (no Ollama? add MOCK_LLM=1)   then open http://127.0.0.1:8642")
    print("Demo PIN for showing protected fields and saving chart changes: 1234 (config/policy.json -> confidential.pin)")
    sys.exit(rc)
