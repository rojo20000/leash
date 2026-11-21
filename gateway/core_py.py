"""Pure-Python Leash core. Same interface and behaviour as the Rust `leash_core` (CONTRACTS.md C1)."""
import hashlib
import json
import os
import re
import tomllib

IMPLEMENTATION = "python"
GENESIS = "0" * 64


def ping() -> str:
    return "leash_core ok"


def _tbl(d, table):
    t = d.get(table)
    return t if isinstance(t, dict) else {}


def _str_list(d, table, key):
    v = _tbl(d, table).get(key)
    if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
        raise ValueError(f"policy: {table}.{key} missing or not a list of strings")
    return v


def _int(d, table, key):
    v = _tbl(d, table).get(key)
    if not isinstance(v, int) or isinstance(v, bool):
        raise ValueError(f"policy: {table}.{key} missing or not an integer")
    return v


# One plain ASCII address; the whole recipient string must match (same pattern in policy.rs).
_ADDR = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)")


class Policy:
    def __init__(self, d):
        role = d.get("role")
        if not isinstance(role, str):
            raise ValueError("policy: role missing or not a string")
        self._role = role
        self._tools = _str_list(d, "tools", "allowed")
        self._approval = _str_list(d, "tools", "require_approval")
        self._resources = _str_list(d, "resources", "allowed")
        self._max = _int(d, "rate", "max_records")
        self._window = _int(d, "rate", "window_seconds")
        self._domains = [x.lower() for x in _str_list(d, "email", "allowed_domains")]
        self._win = []

    @staticmethod
    def from_toml(path):
        with open(path, "r", encoding="utf-8") as f:
            return Policy.from_toml_str(f.read())

    @staticmethod
    def from_toml_str(text):
        try:
            return Policy(tomllib.loads(text))
        except tomllib.TOMLDecodeError as e:
            raise ValueError(f"policy: bad TOML: {e}") from None

    role = property(lambda s: s._role)
    allowed_tools = property(lambda s: list(s._tools))
    allowed_resources = property(lambda s: list(s._resources))
    allowed_domains = property(lambda s: list(s._domains))

    def reset(self):
        self._win = []

    def evaluate(self, tool, resource_types, patient_ids, recipients, ts):
        if tool not in self._tools:
            return ("block", "TOOL_NOT_ALLOWED", f"tool {tool!r} not allowed")
        bad = next((r for r in resource_types if r not in self._resources), None)
        if bad is not None:
            return ("block", "RESOURCE_NOT_ALLOWED", f"resource {bad!r} not allowed")
        for r in recipients:
            m = _ADDR.fullmatch(r)  # no strip: str.strip and Rust trim disagree on some characters
            dom = m.group(1).lower() if m else ""
            if dom not in self._domains:
                return ("block", "EMAIL_DOMAIN_NOT_ALLOWED", f"domain {dom!r} not allowed")
        cutoff = ts - self._window
        self._win = [e for e in self._win if e[0] > cutoff]
        self._win.extend((ts, p) for p in patient_ids)
        n = len({p for _, p in self._win})
        if n > self._max:
            return ("escalate", "RECORD_RATE_EXCEEDED", f"{n} distinct records in window, max {self._max}")
        if tool in self._approval:
            return ("escalate", "TOOL_REQUIRES_APPROVAL", f"tool {tool!r} requires approval")
        return ("allow", "OK", "")


def _canon(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _has_float(v):
    if isinstance(v, float):
        return True
    if isinstance(v, dict):
        return any(_has_float(x) for x in v.values())
    if isinstance(v, list):
        return any(_has_float(x) for x in v)
    return False


def _read_lines(path):
    with open(path, "rb") as f:
        data = f.read().decode("utf-8")
    if data == "":
        return []
    lines = data.split("\n")
    if lines[-1] == "":
        lines.pop()
    return lines


class AuditLog:
    def __init__(self, path):
        self._path = str(path)
        d = os.path.dirname(self._path)
        if d:
            os.makedirs(d, exist_ok=True)
        if not os.path.exists(self._path):
            open(self._path, "wb").close()
        lines = _read_lines(self._path)
        self._n = len(lines)
        self._next = 0
        self._prev = GENESIS
        if lines:
            last = json.loads(lines[-1])
            self._next = last["seq"] + 1
            self._prev = last["hash"]

    path = property(lambda s: s._path)

    def entries(self):
        return self._n

    def append(self, record_json):
        try:
            rec = json.loads(record_json)
        except json.JSONDecodeError as e:
            raise ValueError(f"record is not valid JSON: {e}") from None
        if not isinstance(rec, dict):
            raise ValueError("record must be a JSON object")
        if {"seq", "prev_hash", "hash"} & rec.keys():
            raise ValueError("record must not contain seq, prev_hash or hash")
        if _has_float(rec):
            raise ValueError("record must not contain floats")
        rec["seq"] = self._next
        rec["prev_hash"] = self._prev
        h = hashlib.sha256(_canon(rec)).hexdigest()
        rec["hash"] = h
        with open(self._path, "ab") as f:
            f.write(_canon(rec) + b"\n")
        with open(self._path + ".head", "wb") as f:
            f.write(f"{rec['seq']} {h}\n".encode())
        self._next += 1
        self._n += 1
        self._prev = h
        return h


def verify_log(path):
    path = str(path)
    head = None
    if os.path.exists(path + ".head"):
        with open(path + ".head", "rb") as f:
            head = f.read().decode("utf-8").strip()
    if not os.path.exists(path):
        return (True, None, "") if head is None else (False, 0, "TRUNCATED")
    lines = _read_lines(path)
    prev = GENESIS
    last = ""
    for i, line in enumerate(lines):
        try:
            rec = json.loads(line)
        except ValueError:
            return (False, i, "BAD_JSON")
        if not isinstance(rec, dict):
            return (False, i, "BAD_JSON")
        seq = rec.get("seq")
        if isinstance(seq, bool) or seq != i:
            return (False, i, "SEQ_MISMATCH")
        if rec.get("prev_hash") != prev:
            return (False, i, "PREV_HASH_MISMATCH")
        stored = rec.pop("hash", None)
        if stored != hashlib.sha256(_canon(rec)).hexdigest():
            return (False, i, "HASH_MISMATCH")
        prev = stored
        last = f"{i} {stored}"
    if head is not None and head != last:
        return (False, len(lines), "TRUNCATED")
    return (True, None, "")


_PATTERNS = [
    ("SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("MRN", re.compile(r"\bMRN-\d{7}\b")),
    ("PHONE", re.compile(r"\b\d{3}-\d{3}-\d{4}\b")),
    ("EMAIL", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("DOB", re.compile(r"\b(?:19|20)\d{2}-\d{2}-\d{2}\b")),
    ("DOB", re.compile(r"\b\d{2}/\d{2}/\d{4}\b")),
]


def prescan(text):
    out = [(k, m.start(), m.end()) for k, rx in _PATTERNS for m in rx.finditer(text)]
    out.sort(key=lambda t: (t[1], t[2], t[0]))
    return out
