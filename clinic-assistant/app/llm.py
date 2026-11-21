"""Talk to the local model through Ollama on this machine only.

Set MOCK_LLM=1 to use a stand-in model (for tests, or before Ollama is set up).
"""
from __future__ import annotations

import json
import os
import urllib.request
from urllib.parse import urlparse

LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


def _assert_local(url: str) -> None:
    # Hard rule: the model endpoint must be on this machine. No cloud fallback.
    if urlparse(url).hostname not in LOCAL_HOSTS:
        raise RuntimeError(f"Refusing non-local model endpoint: {url}")


def _post(url: str, payload: dict, timeout: int) -> dict:
    _assert_local(url)
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    # Bypass any system proxy so the request cannot leave the machine.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=timeout) as r:
        return json.loads(r.read())


def chat(policy: dict, messages: list[dict], system: str | None = None) -> str:
    if os.environ.get("MOCK_LLM") == "1":
        last = messages[-1]["content"]
        return f"(stand-in model) I received {len(last)} characters. Summary would appear here."
    m = policy["model"]
    out = _post(f"{m['ollama_url']}/api/chat", {
        "model": m["chat_model"],
        "messages": [{"role": "system", "content": system or policy["scope"]["system_prompt"]}] + messages,
        "stream": False,
        "keep_alive": m.get("keep_alive", "30m"),
        "options": {"temperature": m.get("temperature", 0.2), "num_predict": m.get("max_answer_tokens", 450),
                    "num_ctx": m.get("context_tokens", 4096)},
    }, m.get("timeout_seconds", 180))
    return out["message"]["content"]


def installed_models(policy: dict) -> list[str] | None:
    """Model names Ollama has on this machine, or None if Ollama isn't running."""
    try:
        _assert_local(policy["model"]["ollama_url"])
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(f"{policy['model']['ollama_url']}/api/tags", timeout=3) as r:
            return [x["name"] for x in json.loads(r.read()).get("models", [])]
    except Exception:
        return None


def warm(policy: dict) -> float | None:
    """Load the chat model into memory now, so the first real question doesn't wait for it. Returns seconds."""
    if os.environ.get("MOCK_LLM") == "1":
        return None
    import time
    m, t0 = policy["model"], time.time()
    _post(f"{m['ollama_url']}/api/generate", {"model": m["chat_model"], "prompt": "", "stream": False,
                                               "keep_alive": m.get("keep_alive", "30m")}, m.get("timeout_seconds", 180))
    return time.time() - t0


def safety_check(policy: dict, text: str) -> str:
    """Return 'safe', 'unsafe' or 'skipped' using an optional Llama Guard model."""
    model = policy["model"].get("safety_model")
    if not model or os.environ.get("MOCK_LLM") == "1":
        return "skipped"
    m = policy["model"]
    out = _post(f"{m['ollama_url']}/api/chat", {
        "model": model, "stream": False,
        "messages": [{"role": "user", "content": text}],
    }, m.get("timeout_seconds", 180))
    return "unsafe" if "unsafe" in out["message"]["content"].lower() else "safe"
