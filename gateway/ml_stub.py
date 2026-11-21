"""Rule-based stand-in for ml.api (C6.1 signatures)."""
import copy

from gateway.core_loader import load_core

_PHRASES = ("note to the ai assistant", "ignore previous instructions", "ignore all previous",
            "using the send_email tool", "send this patient's complete", "medical record, including all")


def ready() -> bool:
    return True


def injection_score(text: str) -> float:
    t = (text or "").lower()
    hits = sum(p in t for p in _PHRASES)
    return min(1.0, 0.5 + 0.2 * hits) if hits else 0.0


def anomaly_score(events: list) -> float:
    pids = {p for e in events for p in e.get("patient_ids", [])}
    return min(1.0, max(len(pids) / 10, len(events) / 40))


def _walk(node, path, keep, red):
    if isinstance(node, dict):
        rt = node.get("resourceType")
        if isinstance(rt, str) and rt in keep:
            for k in [k for k in node if k not in keep[rt]]:
                del node[k]
                red.append({"path": f"{path}.{k}" if path else k, "kind": "FIELD", "source": "policy"})
        for k, v in node.items():
            _walk(v, f"{path}.{k}" if path else k, keep, red)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            _walk(v, f"{path}[{i}]", keep, red)


def minimize(tool: str, output: dict, keep_fields: dict):
    out, red = copy.deepcopy(output), []
    _walk(out, "", keep_fields, red)
    text = out.get("text") if isinstance(out, dict) else None
    if isinstance(text, str):
        spans = load_core().prescan(text)
        for kind, s, e in spans:
            red.append({"path": "text", "kind": kind, "start": s, "end": e, "source": "prescan"})
        # replace right to left, skipping spans that overlap one already replaced
        last = len(text) + 1
        for kind, s, e in sorted(spans, key=lambda x: (-x[1], -x[2])):
            if e <= last:
                text = text[:s] + f"[REDACTED:{kind}]" + text[e:]
                last = s
        out["text"] = text
    return out, red
