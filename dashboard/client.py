"""Gateway client for the dashboard. Fixture mode (LEASH_DASHBOARD_FIXTURES) reads JSON files instead of HTTP."""
import json
import os
from pathlib import Path

import httpx

PATHS = {"/health": "health", "/v1/decisions": "decisions", "/v1/queue": "queue",
         "/v1/audit/verify": "verify", "/v1/metrics": "metrics"}


def fixtures_dir():
    d = os.environ.get("LEASH_DASHBOARD_FIXTURES")
    return Path(d) if d else None


def base_url():
    return os.environ.get("LEASH_GATEWAY_URL", "http://127.0.0.1:8000")


def get(path, params=None):
    """Return parsed JSON. Raises httpx.HTTPError / OSError / ValueError when the source is unavailable."""
    fx = fixtures_dir()
    if fx:
        return json.loads((fx / f"{PATHS[path]}.json").read_text(encoding="utf-8"))
    r = httpx.get(base_url() + path, params=params, timeout=2.0)
    r.raise_for_status()
    return r.json()


def review(queue_id, action, reviewer="dashboard", note=""):
    r = httpx.post(f"{base_url()}/v1/queue/{queue_id}/{action}", json={"reviewer": reviewer, "note": note},
                   headers={"X-Leash-Token": os.environ.get("LEASH_REVIEW_TOKEN", "")}, timeout=2.0)
    r.raise_for_status()
    return r.json()
