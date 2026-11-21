"""Gateway overhead benchmark (CONTRACTS C6.4 key `gateway`). In-process, no servers, no network.

    .venv/Scripts/python.exe bench/gateway_latency.py

Workload: the scripted recording (20 calls) in 10 fresh sessions, plus 3 bulk-read sessions of 15 read_record calls
(patients pt-0001..). Run once with LEASH_NEMOTRON=off (rates and the headline latency) and once with
LEASH_NEMOTRON=replay (latency only). Lifespan warm-up runs before the first measured call; `added` excludes the
tool's own execution time.
"""
import json
import os
import shutil
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
POLICY = str(ROOT / "policies" / "scheduling_assistant.toml")
N_SCRIPTED, N_BULK, BULK_LEN = 10, 3, 15
STAGES = ("policy", "injection", "minimize", "anomaly", "audit", "jailbreak", "content_safety", "reasoner")


def write_metrics(key, value, path=str(ROOT / "metrics" / "results.json")):
    data = json.load(open(path)) if os.path.exists(path) else {}
    data[key] = value
    tmp = path + f".{key}.tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2, sort_keys=True)
    os.replace(tmp, path)


def pct(vals, q):
    s = sorted(vals)
    return round(s[min(len(s) - 1, int(q * len(s)))], 4)


def run(mode):
    os.environ["LEASH_NEMOTRON"] = mode
    from fastapi.testclient import TestClient
    from agent.runner import run_session
    from ehr.app import create_app as create_ehr
    from gateway.app import create_app

    tmp = tempfile.mkdtemp(prefix="leash-bench-")
    try:
        ehr = TestClient(create_ehr(data_dir=str(ROOT / "data" / "generated")))
        app = create_app(ehr_client=ehr, runtime_dir=tmp, policy_path=POLICY)
        with TestClient(app) as gw:  # entering runs the lifespan warm-up before any measured call
            assert gw.get("/health").json()["nemotron"] == mode
            decs = []
            for i in range(N_SCRIPTED):
                decs += [s["decision"] for s in run_session(
                    "protected", "scripted", f"bench-s{i}", ehr, gw, os.path.join(tmp, "sink.jsonl"))]
            t0 = time.time()
            for b in range(N_BULK):
                for k in range(BULK_LEN):
                    r = gw.post("/v1/tool-call", json={
                        "session_id": f"bench-bulk{b}", "role": "scheduling_assistant", "tool": "read_record",
                        "args": {"patient_id": f"pt-{b * BULK_LEN + k + 1:04d}", "resource_types": ["Patient"]},
                        "ts": t0 + 2.0 * k})
                    r.raise_for_status()
                    decs.append(r.json())
        return decs
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    off, rep = run("off"), run("replay")
    n = len(off)
    out = {
        "calls": n, "sessions": N_SCRIPTED + N_BULK,
        "workload": f"{N_SCRIPTED} scripted-recording sessions x 20 calls + {N_BULK} bulk-read sessions x {BULK_LEN} read_record",
        "nemotron_mode": "off", "core": off[0]["core"], "ml": off[0]["ml"],
        "rates": {k: round(sum(d["decision"] == k for d in off) / n, 4) for k in ("allow", "block", "escalate")},
        "latency_ms": {"p50": pct([d["latency_ms"]["added"] for d in off], .5),
                       "p95": pct([d["latency_ms"]["added"] for d in off], .95),
                       "by_stage": {s: {"p50": pct([d["latency_ms"].get(s, 0.0) for d in off], .5),
                                        "p95": pct([d["latency_ms"].get(s, 0.0) for d in off], .95)}
                                    for s in STAGES}},
        "latency_ms_replay": {"p50": pct([d["latency_ms"]["added"] for d in rep], .5),
                              "p95": pct([d["latency_ms"]["added"] for d in rep], .95), "calls": len(rep),
                              "rates": {k: round(sum(d["decision"] == k for d in rep) / len(rep), 4)
                                        for k in ("allow", "block", "escalate")}},
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    assert n >= 200 and out["latency_ms"]["p50"] > 0
    write_metrics("gateway", out)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
