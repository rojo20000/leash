"""Time Policy.evaluate and AuditLog.append in the Rust and Python cores; write key `bench` to metrics/results.json."""
import json
import os
import sys
import tempfile
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from gateway import core_py  # noqa: E402

POLICY = "policies/scheduling_assistant.toml"


def write_metrics(key, value, path="metrics/results.json"):
    data = json.load(open(path)) if os.path.exists(path) else {}
    data[key] = value
    tmp = path + f".{key}.tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2, sort_keys=True)
    os.replace(tmp, path)


def time_core(mod, n):
    pol = mod.Policy.from_toml(POLICY)
    t = time.perf_counter()
    for i in range(n):
        pol.evaluate("read_record", ["Patient"], [f"p{i % 8}"], [], float(i))
    policy_us = (time.perf_counter() - t) / n * 1e6
    with tempfile.TemporaryDirectory() as d:
        log = mod.AuditLog(os.path.join(d, "audit.jsonl"))
        rec = '{"tool":"read_record","decision":"allow","score":"0.9731","latency_us":412}'
        t = time.perf_counter()
        for _ in range(n):
            log.append(rec)
        audit_us = (time.perf_counter() - t) / n * 1e6
    return {"policy_us": round(policy_us, 3), "audit_append_us": round(audit_us, 3)}


def main():
    quick = "--quick" in sys.argv
    n = 10_000 if quick else 100_000
    py = time_core(core_py, n)
    try:
        import leash_core
        rs = time_core(leash_core, n)
    except ImportError:
        rs = None
    speed = None if rs is None else {
        "policy": round(py["policy_us"] / rs["policy_us"], 2),
        "audit_append": round(py["audit_append_us"] / rs["audit_append_us"], 2),
    }
    write_metrics("bench", {
        "n": n, "quick": quick, "rust": rs, "python": py, "speedup": speed,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })
    print(f"{'impl':8} {'policy_us':>10} {'audit_append_us':>16}")
    for name, r in (("rust", rs), ("python", py)):
        print(f"{name:8} {r['policy_us']:>10} {r['audit_append_us']:>16}" if r else f"{name:8} unavailable")
    print("speedup", speed)


if __name__ == "__main__":
    main()
