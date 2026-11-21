"""LLM driver on Lightning with Ollama fallback (C10.8). No key, no network, no Ollama."""
import json
import socket

import httpx
import pytest

import agent.runner as runner
import leash.nemotron as nem
from agent.runner import run_session


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    monkeypatch.setenv("LEASH_CORE", "py")
    monkeypatch.setenv("LEASH_ML", "stub")
    monkeypatch.setenv("LEASH_NEMOTRON_RECORDINGS", str(tmp_path / "rec"))
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-TEST-SENTINEL-0000")
    monkeypatch.setattr(nem.time, "sleep", lambda s: None)
    nem._reset()
    yield
    monkeypatch.setattr(nem, "TRANSPORT", None)
    nem._reset()


class FakeEhr:
    def get(self, path, params=None):
        class R:
            def json(self):
                return {"entry": [{"resource": {"id": "ref-0007"}}]}
        return R()


def tc(i, name, args):
    return {"id": f"call_{i}", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}


SCRIPT = [("read_document", {"document_id": "ref-0007"}), ("read_record", {"patient_id": "pt-0007"})]


def lightning(requests):
    def handler(req):
        body = json.loads(req.content)
        requests.append(body)
        n = sum(1 for m in body["messages"] if m["role"] == "assistant")
        msg = {"role": "assistant", "content": "done"} if n >= len(SCRIPT) else \
              {"role": "assistant", "content": None, "tool_calls": [tc(n, *SCRIPT[n])]}
        return httpx.Response(200, json={"choices": [{"message": msg, "finish_reason": "stop"}]})
    return httpx.MockTransport(handler)


@pytest.fixture
def stub_calls(monkeypatch):
    seen = []

    class Ex:
        def __init__(self, *a):
            pass

        def execute(self, tool, args):
            seen.append(tool)
            return {"ok": tool}
    monkeypatch.setattr(runner, "ToolExecutor", Ex)
    return seen


def go(tmp_path):
    return run_session("unprotected", "llm", "s", FakeEhr(), None, str(tmp_path / "sink.jsonl"))


def test_lightning_path(monkeypatch, tmp_path, stub_calls):
    monkeypatch.setenv("LEASH_NEMOTRON", "live")
    reqs = []
    monkeypatch.setattr(nem, "TRANSPORT", lightning(reqs))
    steps = go(tmp_path)
    assert [s["tool"] for s in steps] == ["read_document", "read_record"]
    assert {s["served_by"] for s in steps} == {"nemotron"}
    m = reqs[1]["messages"]
    assert m[-2]["tool_calls"][0]["id"] == "call_0" and m[-1] == {
        "role": "tool", "tool_call_id": "call_0", "content": json.dumps({"ok": "read_document"})}


def test_fallback_on_503(monkeypatch, tmp_path, stub_calls, capsys):
    monkeypatch.setenv("LEASH_NEMOTRON", "live")
    monkeypatch.setattr(nem, "TRANSPORT", httpx.MockTransport(lambda r: httpx.Response(503)))
    sent = _patch_ollama(monkeypatch)
    steps = go(tmp_path)
    assert [s["served_by"] for s in steps] == ["fallback:ollama"] * 2
    assert "agent llm: falling back to ollama (http_503)" in capsys.readouterr().out
    last = sent[-1]
    assert last[-2]["tool_calls"][0]["function"]["arguments"] == {"patient_id": "pt-0007"}
    assert last[-1]["role"] == "tool"


def _patch_ollama(monkeypatch):
    sent = []

    def fake(messages):
        sent.append(json.loads(json.dumps(messages)))
        n = sum(1 for m in messages if m["role"] == "assistant")
        if n >= len(SCRIPT):
            return {"role": "assistant", "content": "done"}
        return {"role": "assistant", "content": "", "tool_calls": [
            {"function": {"name": SCRIPT[n][0], "arguments": SCRIPT[n][1]}}]}
    monkeypatch.setattr(runner, "_ollama_chat", fake)
    return sent


def test_off_goes_to_ollama(monkeypatch, tmp_path, stub_calls):
    monkeypatch.setenv("LEASH_NEMOTRON", "off")
    _patch_ollama(monkeypatch)
    assert {s["served_by"] for s in go(tmp_path)} == {"fallback:ollama"}


def test_replay(monkeypatch, tmp_path, stub_calls):
    monkeypatch.setenv("LEASH_NEMOTRON", "live")
    monkeypatch.setattr(nem, "TRANSPORT", lightning([]))
    live = go(tmp_path)
    monkeypatch.setenv("LEASH_NEMOTRON", "replay")
    monkeypatch.setattr(nem, "TRANSPORT", None)

    def no_net(*a, **k):
        raise AssertionError("socket used")
    monkeypatch.setattr(socket.socket, "connect", no_net)
    rep = go(tmp_path)
    assert [s["tool"] for s in rep] == [s["tool"] for s in live]
    assert {s["served_by"] for s in rep} == {"replay"}
