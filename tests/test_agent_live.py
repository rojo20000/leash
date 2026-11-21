import os

import pytest

pytestmark = [pytest.mark.live,
              pytest.mark.skipif(os.environ.get("LEASH_LIVE_LLM") != "1", reason="set LEASH_LIVE_LLM=1")]


def test_llm_driver_smoke(tmp_path):
    import httpx
    from agent.runner import run_session
    ehr = httpx.Client(base_url=os.environ.get("LEASH_EHR_URL", "http://127.0.0.1:8001"))
    steps = run_session("unprotected", "llm", "live", ehr, None, str(tmp_path / "sink.jsonl"))
    assert 0 < len(steps) <= 25


@pytest.mark.skipif(os.environ.get("LEASH_LIVE_NEMOTRON") != "1", reason="set LEASH_LIVE_NEMOTRON=1")
def test_lightning_protected_session(tmp_path, monkeypatch):
    from pathlib import Path
    from fastapi.testclient import TestClient
    import leash.nemotron as nem
    from agent.runner import run_session
    root = Path(__file__).resolve().parent.parent
    monkeypatch.setenv("LEASH_CORE", "py")
    monkeypatch.setenv("LEASH_NEMOTRON", "live")
    monkeypatch.setenv("LEASH_NEMOTRON_RECORDINGS", str(tmp_path / "rec"))
    nem.load_dotenv()
    if not os.environ.get("NVIDIA_API_KEY"):
        pytest.skip("no NVIDIA_API_KEY")
    import ehr.app
    from gateway.app import create_app
    ehr_c = TestClient(ehr.app.create_app(data_dir=str(root / "data" / "generated")))
    gw = TestClient(create_app(ehr_client=ehr_c, runtime_dir=str(tmp_path / "rt"),
                               policy_path=str(root / "policies" / "scheduling_assistant.toml")))
    steps = run_session("protected", "llm", "live-protected", ehr_c, gw, str(tmp_path / "unused.jsonl"))
    assert any(s["served_by"] == "nemotron" for s in steps)
