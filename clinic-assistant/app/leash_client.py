"""Client for the Leash gateway (integrated mode). Standard library only, loopback only."""
import json
import os
import urllib.error
import urllib.request

from . import llm

LEASH_ROLE = "scheduling_assistant"  # the only policy Leash has
SCHEDULING_TYPES = ["Patient", "Encounter", "DocumentReference"]
FULL_TYPES = ["Patient", "Condition", "MedicationRequest", "Encounter", "DocumentReference"]


class LeashError(Exception):
    """Short message, never any record contents."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **kw):
        return None


def enabled(policy: dict) -> bool:
    return policy.get("leash", {}).get("enabled") is True or os.environ.get("CLINIC_LEASH") == "1"


def tool_call(policy: dict, tool: str, args: dict, session_id: str, call_id: str) -> dict:
    cfg = policy["leash"]
    url = cfg["gateway_url"].rstrip("/") + "/v1/tool-call"
    try:
        llm._assert_local(url)
    except RuntimeError:
        raise LeashError("Refusing non-local Leash gateway") from None
    body = json.dumps({"session_id": session_id, "role": LEASH_ROLE, "tool": tool,
                       "args": args, "call_id": call_id}).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    try:
        with opener.open(req, timeout=cfg.get("timeout_seconds", 10)) as r:
            status, raw = r.status, r.read()
    except urllib.error.HTTPError as e:
        raise LeashError("HTTP %d" % e.code) from None
    except (urllib.error.URLError, OSError) as e:  # includes timeouts
        raise LeashError("unreachable (%s)" % type(e).__name__) from None
    if status != 200:
        raise LeashError("HTTP %d" % status)
    try:
        d = json.loads(raw.decode("utf-8"))
    except ValueError:  # includes UnicodeDecodeError
        raise LeashError("bad response") from None
    if not isinstance(d, dict) or d.get("decision") not in ("allow", "block", "escalate"):
        raise LeashError("bad response")
    if d.get("call_id") != call_id:
        raise LeashError("call_id mismatch")
    return d
