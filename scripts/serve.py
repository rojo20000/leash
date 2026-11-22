"""`make dashboard`: start the mock EHR (:8001), seed one scripted protected session, start the gateway (:8000), then
run the Streamlit dashboard (:8501) in the foreground. The session is seeded in this process on a simulated clock
BEFORE the gateway starts (the gateway uses its own clock and ignores client timestamps); the gateway then loads the
seeded audit log, decisions and queue from the runtime dir. Ctrl+C (or closing Streamlit) stops all three; the servers are
child processes terminated in `finally`, so nothing is left running. Uses LEASH_NEMOTRON=replay unless set; Streamlit usage stats are off (no telemetry).
Resets the gateway's runtime state (runtime/ decisions, queue) before seeding; the old audit log is kept as runtime/audit-<time>.jsonl.
"""
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
EHR, GW = "http://127.0.0.1:8001", "http://127.0.0.1:8000"


def wait(url, proc, name):
    for _ in range(240):  # up to 60 s (the gateway loads spaCy at startup)
        if proc.poll() is not None:
            sys.exit(f"{name} exited (code {proc.returncode}); is the port in use? netstat -ano | findstr {url[-5:]}")
        try:
            if httpx.get(url + "/health", timeout=1).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.25)
    sys.exit(f"{name} did not become healthy at {url}")


def seed(ehr_client, runtime_dir):
    """Reset the gateway state in runtime_dir and replay the scripted session through an in-process gateway whose
    clock follows the recording's offsets. Returns the run_session steps."""
    from fastapi.testclient import TestClient
    from agent.runner import run_session
    from gateway.app import create_app
    now = [time.time()]
    g = TestClient(create_app(ehr_client=ehr_client, runtime_dir=runtime_dir, clock=lambda: now[0]))
    ehr_client.post("/admin/reset")
    g.post("/v1/admin/reset", headers={"X-Leash-Token": os.environ.get("LEASH_REVIEW_TOKEN", "")}).raise_for_status()
    return run_session("protected", "scripted", "demo-protected", ehr_client, g, os.devnull,
                       str(ROOT / "demo" / "recordings" / "referrals.json"),
                       set_time=lambda t: now.__setitem__(0, t))


def main():
    os.environ.setdefault("LEASH_NEMOTRON", "replay")
    os.environ.setdefault("LEASH_EHR_URL", EHR)
    os.environ.setdefault("LEASH_GATEWAY_URL", GW)
    if not os.environ.get("LEASH_REVIEW_TOKEN"):  # shared by the gateway and the dashboard children; never printed
        os.environ["LEASH_REVIEW_TOKEN"] = secrets.token_hex(16)
    uv = [sys.executable, "-m", "uvicorn", "--host", "127.0.0.1", "--log-level", "warning"]
    procs = []
    try:
        ehr = subprocess.Popen(uv + ["ehr.app:app", "--port", "8001"], cwd=ROOT)
        procs.append(ehr)
        wait(EHR, ehr, "EHR")
        with httpx.Client(base_url=EHR, timeout=60) as e:  # same runtime dir as the gateway child (cwd=ROOT)
            steps = seed(e, str(ROOT / os.environ.get("LEASH_RUNTIME_DIR", "runtime")))
        gw = subprocess.Popen(uv + ["gateway.app:app", "--port", "8000"], cwd=ROOT)
        procs.append(gw)
        wait(GW, gw, "gateway")
        n = {k: sum(s["decision"]["decision"] == k for s in steps) for k in ("allow", "block", "escalate")}
        print(f"seeded protected session: {n}. Dashboard: http://127.0.0.1:8501  (Ctrl+C stops everything)", flush=True)

        st = subprocess.Popen([sys.executable, "-m", "streamlit", "run", "dashboard/app.py", "--server.port", "8501",
                               "--server.address", "127.0.0.1", "--server.headless", "true",
                               "--browser.gatherUsageStats", "false"], cwd=ROOT)
        procs.append(st)
        st.wait()
    except KeyboardInterrupt:
        pass
    finally:
        for p in reversed(procs):
            if p.poll() is None:
                p.terminate()
        for p in procs:
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()


if __name__ == "__main__":
    main()
