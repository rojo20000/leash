"""The only module the gateway imports (CONTRACTS C6.1). Artifacts load lazily."""
import math
import os
import tomllib

import joblib

from gateway.core_loader import load_core
from ml.common import ART, p
from ml.features import decision, window_features

_cache = {}


def _art(name):
    if name not in _cache:
        _cache[name] = joblib.load(os.path.join(ART, name + ".joblib"))
    return _cache[name]


def ready():
    return all(os.path.exists(os.path.join(ART, n + ".joblib")) for n in ("injection", "anomaly"))


def injection_score(text):
    return float(_art("injection")["pipeline"].predict_proba([text])[0, 1])


def anomaly_score(events):
    a = _art("anomaly")
    z = a["k"] * float(decision(a, [window_features(events)])[0])
    return 1.0 / (1.0 + math.exp(max(min(z, 700), -700)))


def minimize(tool, output, keep_fields=None):
    from ml.minimize import minimize as _m
    if keep_fields is None:
        with open(p("policies", "scheduling_assistant.toml"), "rb") as f:
            keep_fields = tomllib.load(f).get("minimize", {})
    return _m(tool, output, keep_fields, load_core())
