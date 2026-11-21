import datetime
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ART = os.path.join(ROOT, "ml", "artifacts")
SEED = 1337


def p(*parts):
    return os.path.join(ROOT, *parts)


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
