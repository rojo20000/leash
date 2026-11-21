"""Anomaly window features (CONTRACTS C6.2)."""
import functools
import tomllib

from ml.common import p

NAMES = ["n_calls", "distinct_patients", "frac_search_patients", "frac_read_record", "frac_read_document",
         "frac_update_appointment", "frac_send_email", "off_role_resources", "external_recipients"]
_TOOLS = ["search_patients", "read_record", "read_document", "update_appointment", "send_email"]


@functools.lru_cache(maxsize=None)
def _policy(path):
    with open(path, "rb") as f:
        d = tomllib.load(f)
    return set(d["resources"]["allowed"]), {x.lower() for x in d["email"]["allowed_domains"]}


def window_features(events, policy_path=None):
    allowed_res, domains = _policy(policy_path or p("policies", "scheduling_assistant.toml"))
    n = len(events)
    pats = {x for e in events for x in e.get("patient_ids", [])}
    fr = [sum(e["tool"] == t for e in events) / n if n else 0.0 for t in _TOOLS]
    off = sum(r not in allowed_res for e in events for r in e.get("resource_types", []))
    ext = sum(r.rsplit("@", 1)[-1].lower() not in domains for e in events for r in e.get("recipients", []))
    return [float(n), float(len(pats)), *fr, float(off), float(ext)]


def session_windows(events):
    """Yield (event, window) for each event of one time-ordered session; window = events in (ts-60, ts]."""
    lo = 0
    for i, e in enumerate(events):
        while events[lo]["ts"] <= e["ts"] - 60:
            lo += 1
        yield e, events[lo:i + 1]


def decision(art, X):
    """IsolationForest decision value, forced to -0.1 when a feature that was constant in training changes.
    shortcut: an isolation forest cannot split on a constant feature, so policy-violation counts (7, 8; always 0 in
    normal traffic) would otherwise be invisible; upgrade by training on windows with synthetic violations."""
    import numpy as np
    X = np.atleast_2d(np.asarray(X, dtype=float))
    d = art["model"].decision_function(X)
    const = art["const"]  # {feature index: training value}
    if const:
        idx = list(const)
        bad = (X[:, idx] != np.array([const[i] for i in idx])).any(axis=1)
        d = np.where(bad, np.minimum(d, -0.1), d)
    return d
