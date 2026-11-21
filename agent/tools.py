"""Clinical agent tools (C4.2), shared by the unprotected agent and the gateway executor."""
import json
import os
import re
from datetime import datetime, timezone

import httpx

ALL_RESOURCE_TYPES = ["Patient", "Condition", "MedicationRequest", "Encounter", "DocumentReference"]


def _fn(name, desc, props, required):
    return {"type": "function", "function": {"name": name, "description": desc,
            "parameters": {"type": "object", "properties": props, "required": required}}}


TOOL_SCHEMAS = [
    _fn("search_patients", "Search patients by name substring and/or birthdate (YYYY-MM-DD).",
        {"name": {"type": "string"}, "birthdate": {"type": "string"}}, []),
    _fn("read_record", "Read a patient's FHIR resources.",
        {"patient_id": {"type": "string"},
         "resource_types": {"type": "array", "items": {"type": "string", "enum": ALL_RESOURCE_TYPES}}},
        ["patient_id"]),
    _fn("read_document", "Read the text of a referral document.",
        {"document_id": {"type": "string"}}, ["document_id"]),
    _fn("update_appointment", "Book a follow-up appointment.",
        {"patient_id": {"type": "string"}, "start": {"type": "string", "description": "ISO datetime"},
         "reason": {"type": "string"}}, ["patient_id", "start", "reason"]),
    _fn("send_email", "Send an email.",
        {"to": {"type": "array", "items": {"type": "string"}}, "subject": {"type": "string"},
         "body": {"type": "string"}}, ["to", "subject", "body"]),
]


def _strs(v):
    if v is None:
        return []
    return [str(x) for x in v] if isinstance(v, (list, tuple)) else [str(v)]


def call_facts(tool, args):
    """Policy inputs for a call: (resource_types, patient_ids, recipients).

    Never raises; every item is a str whatever JSON the agent sent, so the policy cores never see other types (A20).
    """
    args = args if isinstance(args, dict) else {}
    pid = args.get("patient_id")
    pids = [] if pid is None else [str(pid)]
    if tool == "search_patients":
        return ["Patient"], [], []
    if tool == "read_record":
        return _strs(args.get("resource_types") or ALL_RESOURCE_TYPES), pids, []
    if tool == "read_document":
        return ["DocumentReference"], [], []
    if tool == "update_appointment":
        return ["Encounter"], pids, []
    if tool == "send_email":
        return [], [], _strs(args.get("to"))
    return [], [], []


def _need(args, *keys):
    for k in keys:
        if not isinstance(args.get(k), str) or not args[k]:
            raise ValueError(f"missing or bad arg: {k}")


_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")  # no dot: "." and ".." are URL path segments
# one plain address per recipient, untrimmed; the policy check in both cores uses the same pattern (audit A4)
_ADDR = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)")


def _need_id(args, key):
    """An id that is safe to put in an EHR URL path (audit A1)."""
    v = args.get(key)
    if not isinstance(v, str) or not _ID.fullmatch(v):
        raise ValueError(f"missing or bad arg: {key}")
    return v


class ToolExecutor:
    def __init__(self, ehr: httpx.Client, sink_path: str, mode: str, session_id: str):
        self.ehr, self.sink_path, self.mode, self.session_id = ehr, sink_path, mode, session_id

    def _get(self, path, **params):
        r = self.ehr.get(path, params={k: v for k, v in params.items() if v is not None})
        if r.status_code >= 400:
            raise ValueError(f"EHR {r.status_code} for {path}")
        return r.json()

    def _next_message_id(self):
        n = 0
        if os.path.exists(self.sink_path):
            with open(self.sink_path, encoding="utf-8") as f:
                n = sum(1 for line in f if line.strip())
        return f"m-{n + 1:04d}"

    def execute(self, tool: str, args: dict) -> dict:
        args = args or {}
        if tool == "search_patients":
            b = self._get("/fhir/Patient", name=args.get("name"), birthdate=args.get("birthdate"))
            return {"patients": [e["resource"] for e in b.get("entry", [])]}
        if tool == "read_record":
            pid = _need_id(args, "patient_id")
            types = args.get("resource_types") or ALL_RESOURCE_TYPES
            bad = [t for t in types if t not in ALL_RESOURCE_TYPES]
            if bad:
                raise ValueError(f"unknown resource types: {bad}")
            res = {}
            for t in types:
                if t == "Patient":
                    res[t] = [self._get(f"/fhir/Patient/{pid}")]
                else:
                    res[t] = [e["resource"] for e in self._get(f"/fhir/{t}", patient=pid).get("entry", [])]
            return {"patient_id": pid, "resources": res}
        if tool == "read_document":
            return self._get(f"/fhir/DocumentReference/{_need_id(args, 'document_id')}/text")
        if tool == "update_appointment":
            _need_id(args, "patient_id")
            _need(args, "start", "reason")
            r = self.ehr.post("/fhir/Encounter", json={k: args[k] for k in ("patient_id", "start", "reason")})
            if r.status_code >= 400:
                raise ValueError(f"EHR {r.status_code} creating encounter")
            return {"encounter": r.json()}
        if tool == "send_email":
            _need(args, "subject")
            to = args.get("to")
            to = [to] if isinstance(to, str) else to
            if (not to or not all(isinstance(t, str) and _ADDR.fullmatch(t) for t in to)
                    or not isinstance(args.get("body"), str)):
                raise ValueError("bad args for send_email")
            mid = self._next_message_id()
            line = {"message_id": mid, "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "mode": self.mode, "session_id": self.session_id, "to": to,
                    "subject": args["subject"], "body": args["body"]}
            os.makedirs(os.path.dirname(os.path.abspath(self.sink_path)), exist_ok=True)
            with open(self.sink_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(line) + "\n")
            return {"status": "sent", "message_id": mid}
        raise ValueError(f"unknown tool: {tool}")
