"""The network view for the network engineer: what talks to what, and whether anything leaves the machine.

No patient data here: only addresses, file health, counts and timings. Model calls come from the
audit log's "model_call" entries, which record where, which endpoint, how long and ok, never content.
"""
from __future__ import annotations

import ipaddress
import os
import re
import socket
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from . import VERSION, llm

_probe_cache: dict = {}


def _local(host: str | None) -> bool:
    if not host:
        return False
    if host in llm.LOCAL_HOSTS:
        return True
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_loopback or ip.is_private
    except ValueError:
        return False


def _tcp(addr: str, timeout: float = 1.0) -> bool | None:
    """True if a TCP connection opens, False if not, None if no address is configured."""
    if not addr:
        return None
    host, _, port = addr.rpartition(":")
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except (OSError, ValueError):
        return False


def _public_probe(addr: str) -> bool | None:
    """Cached for a minute, so the page never waits on it more than once a minute."""
    hit = _probe_cache.get(addr)
    if hit and time.time() - hit[0] < 60:
        return hit[1]
    result = _tcp(addr)
    _probe_cache[addr] = (time.time(), result)
    return result


def _urls(obj) -> list[str]:
    if isinstance(obj, dict):
        return [u for v in obj.values() for u in _urls(v)]
    if isinstance(obj, list):
        return [u for v in obj for u in _urls(v)]
    if isinstance(obj, str):
        return re.findall(r"https?://[^\s\"'<>]+", obj)
    return []


def _ts(s: str) -> datetime | None:
    try:
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _file_node(app, nid: str, label: str, path, chain: tuple[bool, str] | None) -> dict:
    addr = f"{path.parent.name}/{path.name}"
    if not path.exists():
        return {"id": nid, "label": label, "kind": "storage", "address": addr, "status": "down",
                "detail": "File missing."}
    wal = path.with_name(path.name + "-wal")  # SQLite in WAL mode keeps recent writes here
    size = path.stat().st_size + (wal.stat().st_size if wal.exists() else 0)
    writable = os.access(path, os.W_OK)
    ok = writable and (chain is None or chain[0])
    detail = f"{size / 1024:.0f} KB, {'writable' if writable else 'NOT writable'}"
    if chain is not None:
        detail += f", {chain[1]}"
    return {"id": nid, "label": label, "kind": "storage", "address": addr, "status": "up" if ok else "down",
            "detail": detail}


def status(app) -> dict:
    pol = app.policy
    net = pol.get("network", {})
    host, port = pol["server"]["host"], pol["server"]["port"]
    model_url = pol["model"]["ollama_url"]
    model_host = urlparse(model_url).hostname
    now = datetime.now(timezone.utc)
    day_ago = now - timedelta(hours=24)

    entries = app.audit.read(limit=1_000_000)  # newest first
    calls = [e for e in entries if e["event"] == "model_call"]
    ollama_calls = [e for e in calls if str(e["details"].get("to", "")).startswith("ollama")]
    reviewer_calls = [e for e in calls if "reviewer" in str(e["details"].get("to", ""))]
    staff = [e for e in entries if e.get("user")]
    recent = lambda rows: sum(1 for e in rows if (_ts(e["ts"]) or now) >= day_ago)

    # --- nodes ---
    models = llm.installed_models(pol, timeout=1)
    want = pol["model"]["chat_model"]
    if models is None:
        o_status, o_detail = "down", "Not answering (1 second timeout). Open the Ollama app."
    else:
        have = any(m == want or m == want + ":latest" or m.lower() == want.lower() for m in models)
        o_status = "up"
        o_detail = (f"Models installed: {', '.join(models) or 'none'}. Chat model {want}: "
                    + ("installed." if have else "NOT installed."))
    if os.environ.get("MOCK_LLM") == "1":
        o_detail += " The app is using the stand-in model (MOCK_LLM=1)."
    leash = net.get("leash_url", "")
    leash_up = _tcp(urlparse(leash).netloc) if leash else None
    sessions = sum(1 for v in list(app.sessions.values()) if v["expires"] > time.time())
    db_ok, db_n, db_bad = app.db.verify_chain()
    conv_ok = app.db.verify_conversations()[0]
    vec = app.vectors.verify()
    aud = app.audit.verify()
    nodes = [
        {"id": "browsers", "label": "Staff browsers", "kind": "client", "address": f"{host} (same machine)",
         "status": "up" if sessions else "unknown", "detail": f"{sessions} signed-in session(s)"},
        {"id": "app", "label": f"Clinic Assistant {VERSION}", "kind": "server", "address": f"{host}:{port}",
         "status": "up", "detail": "Gatekeeper web app; the only thing that talks to the model and the data files"},
        {"id": "ollama", "label": "Ollama (local model)", "kind": "model", "address": urlparse(model_url).netloc,
         "status": o_status, "detail": o_detail},
        _file_node(app, "clinic_db", "Clinic database (SQLite)", app.db.path,
                   (db_ok and conv_ok, f"change log {'intact' if db_ok else f'BROKEN at #{db_bad}'} ({db_n} entries)"
                    + ("" if conv_ok else ", conversation log BROKEN"))),
        _file_node(app, "vectors", "Vector store (SQLite)", app.vectors.path,
                   (vec["ok"], "hash chain intact" if vec["ok"] else "hash chain BROKEN")),
        _file_node(app, "audit_log", "Audit log", app.audit.path,
                   (aud["ok"], "hash chain intact" if aud["ok"] else "hash chain BROKEN")),
        {"id": "leash", "label": "Leash gateway", "kind": "gateway", "address": urlparse(leash).netloc if leash else "",
         "status": "disabled" if not leash else ("up" if leash_up else "down"),
         "detail": "Not configured (network.leash_url in config/policy.json)." if not leash
         else ("Reachable." if leash_up else "Not reachable (1 second timeout).")},
    ]

    nodes.insert(2, app.reviewer.network_node())  # drawn next to the chat model it checks
    byid = {n["id"]: n for n in nodes}

    # --- edges ---
    def last(rows):
        return rows[0]["ts"] if rows else None
    changes_24h = app.db._q("SELECT COUNT(*), MAX(at) FROM change_log WHERE at >= ?",
                            (day_ago.strftime("%Y-%m-%dT%H:%M:%SZ"),))[0]
    last_change = app.db._q("SELECT MAX(at) FROM change_log")[0][0]
    ollama_last_ok = ollama_calls[0]["details"].get("ok") if ollama_calls else None
    edges = [
        {"from": "browsers", "to": "app", "protocol": "HTTP over loopback", "purpose": "Staff web page and API",
         "status": "up" if sessions else "unknown", "last_seen": last(staff), "calls_24h": recent(staff)},
        {"from": "app", "to": "reviewer", "protocol": "HTTP over loopback (Ollama API)",
         "purpose": "Checks every request before and after the chat model", "status": byid["reviewer"]["status"],
         "last_seen": last(reviewer_calls), "calls_24h": recent(reviewer_calls)},
        {"from": "app", "to": "ollama", "protocol": "HTTP over loopback (Ollama API)",
         "purpose": "Model answers, warm-up and model list", "status": o_status if ollama_last_ok is not False else "down",
         "last_seen": last(ollama_calls), "calls_24h": recent(ollama_calls)},
        {"from": "app", "to": "clinic_db", "protocol": "SQLite file (local disk)",
         "purpose": "Patients, appointments, change log, conversations", "status": byid["clinic_db"]["status"],
         "last_seen": last_change, "calls_24h": changes_24h[0]},
        {"from": "app", "to": "vectors", "protocol": "SQLite file (local disk)",
         "purpose": "Similar cases and injection detection (masked text only)", "status": byid["vectors"]["status"],
         "last_seen": None, "calls_24h": None},
        {"from": "app", "to": "audit_log", "protocol": "Append-only file (local disk)",
         "purpose": "Tamper-evident record of every action", "status": byid["audit_log"]["status"],
         "last_seen": last(entries), "calls_24h": recent(entries)},
        {"from": "app", "to": "leash", "protocol": "HTTP", "purpose": "Optional policy gateway",
         "status": byid["leash"]["status"], "last_seen": None, "calls_24h": None},
    ]

    # --- egress ---
    others = [u for u in _urls(pol) if not _local(urlparse(u).hostname)]
    probe_addr = net.get("public_probe", "")
    reach = _public_probe(probe_addr) if probe_addr else None
    checks = [
        {"name": "Model server is on this machine", "ok": _local(model_host),
         "detail": f"{model_url} ({'loopback/private' if _local(model_host) else 'NOT local: the app refuses to call it'})"},
        {"name": "No other outbound addresses in config", "ok": not others,
         "detail": "Only local addresses in config/policy.json." if not others else "Found: " + ", ".join(others[:5])},
        {"name": "Web app listens only on this machine", "ok": host in llm.LOCAL_HOSTS, "detail": f"{host}:{port}"},
        {"name": f"Public internet from this machine ({probe_addr or 'probe off'})",
         "ok": reach is not True,
         "detail": ("Not checked (network.public_probe is empty)." if reach is None else
                    "Reachable from this machine. The app itself makes no outbound calls, but a firewall rule "
                    "should block this (see README)." if reach else
                    "Blocked or unreachable (1 second timeout). The app itself makes no outbound calls.")},
    ]
    return {"nodes": nodes, "edges": edges,
            "egress": {"outbound_internet": "unknown" if reach is None else "allowed" if reach else "blocked",
                       "checks": checks},
            "recent_calls": [{"at": e["ts"], "from": e["details"].get("from"), "to": e["details"].get("to"),
                              "what": e["details"].get("what"), "ok": e["details"].get("ok"),
                              "ms": e["details"].get("ms")} for e in calls[:20]],
            "checked_at": now.strftime("%Y-%m-%dT%H:%M:%SZ")}
