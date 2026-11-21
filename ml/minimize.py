"""Data minimization: drop non-allowed FHIR fields, redact identifiers in free text (CONTRACTS C6.1)."""
import copy
import re

_ENGINE = None
_KINDS = {"US_SSN": "SSN", "PHONE_NUMBER": "PHONE", "EMAIL_ADDRESS": "EMAIL",
          "US_DRIVER_LICENSE": "DRIVER_LICENSE", "CREDIT_CARD": "CREDIT_CARD"}
# Pre-scan DOB matches any date, so an appointment date would be redacted; only a date next to a birth label is a DOB.
_DOB_CTX = re.compile(r"(?:dob|d\.o\.b|date of birth|birth ?date|born|birthday)\W{0,3}(?:on\W{0,3})?$", re.I)


def _engine():
    global _ENGINE
    if _ENGINE is None:
        from presidio_analyzer import AnalyzerEngine
        from presidio_analyzer.nlp_engine import NlpEngineProvider
        nlp = NlpEngineProvider(nlp_configuration={
            "nlp_engine_name": "spacy", "models": [{"lang_code": "en", "model_name": "en_core_web_lg"}]}
        ).create_engine()
        _ENGINE = AnalyzerEngine(nlp_engine=nlp, supported_languages=["en"])
    return _ENGINE


def find_spans(text, core):
    """Merged [(kind, start, end, source)], non-overlapping; on overlap the longer span wins."""
    cand = []
    for kind, s, e in core.prescan(text):
        if kind == "DOB" and not _DOB_CTX.search(text[max(0, s - 20):s]):
            continue
        cand.append((kind, s, e, "prescan"))
    for r in _engine().analyze(text=text, language="en", entities=list(_KINDS)):
        cand.append((_KINDS[r.entity_type], r.start, r.end, "presidio"))
    keep = []
    for c in sorted(cand, key=lambda c: (-(c[2] - c[1]), c[1])):
        if all(c[2] <= k[1] or c[1] >= k[2] for k in keep):
            keep.append(c)
    return sorted(keep, key=lambda c: c[1])


def _walk(node, path, keep_fields, reds):
    if isinstance(node, dict):
        rt = node.get("resourceType")
        if isinstance(rt, str) and rt in keep_fields:
            for key in [k for k in node if k not in keep_fields[rt]]:
                del node[key]
                reds.append({"path": f"{path}.{key}", "kind": "FIELD", "source": "policy"})
        for k, v in node.items():
            _walk(v, f"{path}.{k}", keep_fields, reds)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            _walk(v, f"{path}[{i}]", keep_fields, reds)


def minimize(tool, output, keep_fields, core):
    out, reds = copy.deepcopy(output), []
    _walk(out, "$", keep_fields, reds)
    text = out.get("text") if isinstance(out, dict) else None
    if isinstance(text, str) and text:
        pieces, last = [], 0
        for kind, s, e, src in find_spans(text, core):
            pieces += [text[last:s], f"[REDACTED:{kind}]"]
            reds.append({"path": "$.text", "kind": kind, "source": src, "start": s, "end": e})
            last = e
        out["text"] = "".join(pieces) + text[last:]
    return out, reds
