"""Talk to the local model through Ollama on this machine only.

Set MOCK_LLM=1 to use a stand-in model (for tests, or before Ollama is set up).
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
import weakref
from urllib.parse import urlparse

LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}

# Every call to the model server is recorded (where to, which endpoint, how long, ok or not; never any
# content) in the audit log of each running app. The network view reads these back.
SINKS: "weakref.WeakSet" = weakref.WeakSet()


def _record(url: str, what: str, ms: int, ok: bool, model: str | None = None, label: str = "ollama") -> None:
    to = urlparse(url).netloc or url
    for sink in list(SINKS):
        try:
            sink.write("model_call", None, **{"from": "app", "to": f"{label} {to}", "what": what,
                                              "model": model, "ms": ms, "ok": ok})
        except Exception:
            pass  # recording must never break an answer


def _assert_local(url: str) -> None:
    # Hard rule: the model endpoint must be on this machine. No cloud fallback.
    if urlparse(url).hostname not in LOCAL_HOSTS:
        raise RuntimeError(f"Refusing non-local model endpoint: {url}")


def _post(url: str, payload: dict, timeout: int, label: str = "ollama") -> dict:
    _assert_local(url)
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    # Bypass any system proxy so the request cannot leave the machine.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    t0, ok = time.time(), False
    try:
        with opener.open(req, timeout=timeout) as r:
            out = json.loads(r.read())
        ok = True
        return out
    finally:
        _record(url, urlparse(url).path, int((time.time() - t0) * 1000), ok, payload.get("model"), label)


def demo_fast(policy: dict) -> dict:
    """The fast-demo preset (policy "demo_fast"), or {} when it is off."""
    d = policy.get("demo_fast") or {}
    return d if d.get("enabled") else {}


def chat_options(policy: dict) -> dict:
    """Ollama options for the chat model. The warm-up uses the same num_ctx, or Ollama would reload the model."""
    m, fast = policy["model"], demo_fast(policy)
    return {"temperature": m.get("temperature", 0.2),
            "num_predict": fast.get("chat_num_predict", m.get("max_answer_tokens", 450)),
            "num_ctx": fast.get("chat_num_ctx", m.get("context_tokens", 4096))}


def chat(policy: dict, messages: list[dict], system: str | None = None) -> str:
    if os.environ.get("MOCK_LLM") == "1":
        last = messages[-1]["content"]
        for sink in list(SINKS):
            try:
                sink.write("model_call", None, **{"from": "app", "to": "stand-in model (MOCK_LLM)",
                                                  "what": "/api/chat", "model": "mock", "ms": 0, "ok": True})
            except Exception:
                pass
        return f"(stand-in model) I received {len(last)} characters. Summary would appear here."
    m = policy["model"]
    body = {
        "model": m["chat_model"],
        "messages": [{"role": "system", "content": system or policy["scope"]["system_prompt"]}] + messages,
        "stream": False,
        "keep_alive": m.get("keep_alive", "30m"),
        "options": chat_options(policy),
    }
    if isinstance(m.get("think"), bool):  # only sent when policy sets it; see model._think
        body["think"] = m["think"]
    out = _post(f"{m['ollama_url']}/api/chat", body, m.get("timeout_seconds", 180))
    return out["message"]["content"]


def installed_models(policy: dict, timeout: float = 3) -> list[str] | None:
    """Model names Ollama has on this machine, or None if Ollama isn't running."""
    url = f"{policy['model']['ollama_url']}/api/tags"
    t0, out = time.time(), None
    try:
        _assert_local(policy["model"]["ollama_url"])
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(url, timeout=timeout) as r:
            out = [x["name"] for x in json.loads(r.read()).get("models", [])]
    except Exception:
        out = None
    _record(url, "/api/tags", int((time.time() - t0) * 1000), out is not None)
    return out


def warm(policy: dict) -> float | None:
    """Load the chat model into memory now, so the first real question doesn't wait for it. Returns seconds."""
    if os.environ.get("MOCK_LLM") == "1":
        return None
    import time
    m, t0 = policy["model"], time.time()
    _post(f"{m['ollama_url']}/api/generate", {"model": m["chat_model"], "prompt": "", "stream": False,
                                               "keep_alive": m.get("keep_alive", "30m"),
                                               "options": {"num_ctx": chat_options(policy)["num_ctx"]}},
          m.get("timeout_seconds", 180))
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
