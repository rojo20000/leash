"""Mask patient identifiers before text reaches the model or the logs.

Uses Microsoft Presidio when it is installed (better at names), and always
runs the built-in patterns below as a safety net. Patterns are deliberately
greedy: masking too much is safer than masking too little.
"""
from __future__ import annotations

import re

_PATTERNS = [
    ("EMAIL", r"[\w.+-]+@[\w-]+\.[\w.-]+"),
    ("SSN", r"\b\d{3}-\d{2}-\d{4}\b"),
    ("MRN", r"\b(?:MRN|medical record(?: number)?|record #|chart #)\s*[:#]?\s*[A-Z0-9-]{4,}\b"),
    ("PHONE", r"(?:\+?1[\s.-]?)?\(?\b\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b"),
    ("DATE", r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b"),
    ("DATE", r"\b\d{4}-\d{2}-\d{2}\b"),
    ("DATE", r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.? \d{1,2}(?:st|nd|rd|th)?,? \d{4}\b"),
    ("ADDRESS", r"\b\d{1,6} [A-Z][a-z]+(?: [A-Z][a-z]+)* (?:Street|St|Avenue|Ave|Road|Rd|Lane|Ln|Drive|Dr|Boulevard|Blvd|Court|Ct|Way)\b\.?"),
    ("ZIP", r"\b\d{5}(?:-\d{4})?\b"),
    # Names after a title or a label: "Mr. John Smith", "Patient: Jane Doe"
    ("NAME", r"\b(?:Mr|Mrs|Ms|Miss|Dr|Prof)\.? [A-Z][a-z]+(?: [A-Z][a-z]+)?"),
    ("NAME", r"(?i:\b(?:patient|name|pt)\s*[:\-]\s*)[A-Z][a-z]+(?: [A-Z][a-z]+)?"),
]
_COMPILED = [(tag, re.compile(p)) for tag, p in _PATTERNS]

try:  # optional, much better at free-text names
    from presidio_analyzer import AnalyzerEngine  # type: ignore
    from presidio_anonymizer import AnonymizerEngine  # type: ignore
    _analyzer, _anonymizer = AnalyzerEngine(), AnonymizerEngine()
except Exception:  # not installed: patterns only
    _analyzer = _anonymizer = None


def presidio_available() -> bool:
    return _analyzer is not None


def mask(text: str) -> tuple[str, list[str]]:
    """Return (masked_text, list of tags that were found)."""
    found: list[str] = []
    if _analyzer is not None:
        results = _analyzer.analyze(text=text, language="en")
        if results:
            found += sorted({r.entity_type for r in results})
            text = _anonymizer.anonymize(text=text, analyzer_results=results).text
    for tag, rx in _COMPILED:
        if rx.search(text):
            found.append(tag)
            text = rx.sub(f"[{tag}]", text)
    return text, sorted(set(found))
