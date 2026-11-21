"""Append-only, hash-chained audit log.

Each line is JSON and carries the hash of the line before it, so editing or
deleting any past line breaks the chain and `verify()` reports where.
For real use, also copy the file to write-once storage on a schedule.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path

_lock = threading.Lock()
GENESIS = "0" * 64


class AuditLog:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)

    def _last_hash(self) -> str:
        last = GENESIS
        with self.path.open() as f:
            for line in f:
                if line.strip():
                    last = json.loads(line)["hash"]
        return last

    @staticmethod
    def _digest(prev: str, body: dict) -> str:
        canon = json.dumps(body, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256((prev + canon).encode()).hexdigest()

    def write(self, event: str, user: str | None, **details) -> dict:
        with _lock:
            prev = self._last_hash()
            body = {
                "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "event": event,
                "user": user,
                "details": details,
                "prev": prev,
            }
            entry = {**body, "hash": self._digest(prev, body)}
            with self.path.open("a") as f:
                f.write(json.dumps(entry) + "\n")
            return entry

    def read(self, limit: int = 200) -> list[dict]:
        with self.path.open() as f:
            rows = [json.loads(l) for l in f if l.strip()]
        return rows[-limit:][::-1]

    def verify(self) -> dict:
        prev = GENESIS
        n = 0
        with self.path.open() as f:
            for n, line in enumerate((l for l in f if l.strip()), start=1):
                entry = json.loads(line)
                body = {k: v for k, v in entry.items() if k != "hash"}
                if entry.get("prev") != prev or self._digest(prev, body) != entry.get("hash"):
                    return {"ok": False, "broken_at_line": n}
                prev = entry["hash"]
        return {"ok": True, "entries": n}
