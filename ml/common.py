import datetime
import json
import os
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ART = os.path.join(ROOT, "ml", "artifacts")
SEED = 1337


def p(*parts):
    return os.path.join(ROOT, *parts)


def normalize(text):
    # Same text form for training and scoring: invisible (Cf) and look-alike characters must not hide words.
    text = unicodedata.normalize("NFKC", text or "")
    return "".join(c for c in text if unicodedata.category(c) != "Cf")


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def write_metrics(key, value, path=None):
    path = path or p("metrics", "results.json")
    data = json.load(open(path)) if os.path.exists(path) else {}
    data[key] = value
    tmp = path + f".{key}.tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2, sort_keys=True)
    os.replace(tmp, path)
