"""Local user accounts. Passwords are stored as salted PBKDF2 hashes.

Accounts are created by an admin on the command line (manage_users.py),
never through the web page, so there is no self sign-up to abuse.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path

ITERATIONS = 310_000


def _hash(password: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS).hex()


class UserStore:
    def __init__(self, path: Path, roles: dict, patient_role: str = "patient"):
        self.path, self.roles, self.patient_role = path, roles, patient_role
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}")

    def _load(self) -> dict:
        return json.loads(self.path.read_text())

    def add(self, username: str, password: str, role: str, patient_id: str | None = None) -> None:
        if role not in self.roles:
            raise ValueError(f"Unknown role {role}. Choose from {sorted(self.roles)}")
        if role == self.patient_role and not patient_id:
            raise ValueError("A patient account must be linked to a patient id.")
        if role != self.patient_role and patient_id:
            raise ValueError("Only a patient account can be linked to a patient id.")
        if len(password) < 12:
            raise ValueError("Password must be at least 12 characters.")
        users = self._load()
        salt = os.urandom(16)
        users[username] = {"role": role, "salt": salt.hex(), "hash": _hash(password, salt), "active": True}
        if patient_id:
            users[username]["patient_id"] = patient_id
        self.path.write_text(json.dumps(users, indent=2))
        os.chmod(self.path, 0o600)

    def patient_id(self, username: str) -> str | None:
        """The patient id a patient account is linked to, else None."""
        return (self._load().get(username) or {}).get("patient_id")

    def account(self, username: str) -> dict | None:
        """Role, active flag and patient link as stored right now (no password material)."""
        u = self._load().get(username)
        return {"role": u["role"], "active": bool(u.get("active")), "patient_id": u.get("patient_id")} if u else None

    def disable(self, username: str) -> None:
        users = self._load()
        users[username]["active"] = False
        self.path.write_text(json.dumps(users, indent=2))

    def check(self, username: str, password: str) -> str | None:
        """Return the user's role if the password is right, else None."""
        u = self._load().get(username)
        if not u or not u.get("active"):
            _hash(password, b"0" * 16)  # same work either way, so timing reveals nothing
            return None
        ok = hmac.compare_digest(_hash(password, bytes.fromhex(u["salt"])), u["hash"])
        return u["role"] if ok else None

    def list(self) -> list[tuple[str, str, bool]]:
        return [(n, u["role"], u["active"]) for n, u in self._load().items()]
