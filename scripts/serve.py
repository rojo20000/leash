"""`make dashboard`: start the mock EHR (:8001) and the gateway (:8000), seed one scripted protected session, then
run the Streamlit dashboard (:8501) in the foreground. Ctrl+C (or closing Streamlit) stops all three; the servers are
child processes terminated in `finally`, so nothing is left running. Uses LEASH_NEMOTRON=replay unless set; Streamlit usage stats are off (no telemetry).
Resets the gateway's runtime state (runtime/ audit log, decisions, queue) before seeding.
"""
import os
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


def main():
    os.environ.setdefault("LEASH_NEMOTRON", "replay")
    os.environ.setdefault("LEASH_EHR_URL", EHR)
    os.environ.setdefault("LEASH_GATEWAY_URL", GW)
    uv = [sys.executable, "-m", "uvicorn", "--host", "127.0.0.1", "--log-level", "warning"]
    procs = []
    try:
        ehr = subprocess.Popen(uv + ["ehr.app:app", "--port", "8001"], cwd=ROOT)
        procs.append(ehr)
        wait(EHR, ehr, "EHR")
        gw = subprocess.Popen(uv + ["gateway.app:app", "--port", "8000"], cwd=ROOT)
        procs.append(gw)
        wait(GW, gw, "gateway")

        from agent.runner import run_session
        with httpx.Client(base_url=EHR, timeout=60) as e, httpx.Client(base_url=GW, timeout=120) as g:
            e.post("/admin/reset")
            g.post("/v1/admin/reset")
            steps = run_session("protected", "scripted", "demo-protected", e, g, os.devnull,
                                str(ROOT / "demo" / "recordings" / "referrals.json"))
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
