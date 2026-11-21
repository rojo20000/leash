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

HIDDEN_CHARS = re.compile("[​-‏‪-‮⁠-⁤﻿\U000e0000-\U000e007f]")
# Presidio type -> the tag the patterns above use. Only these types are requested: asked for
# everything, Presidio masks ages, "3 days ago" and "tomorrow" as DATE_TIME.
_PRESIDIO_TAGS = {"PERSON": "NAME", "PHONE_NUMBER": "PHONE", "EMAIL_ADDRESS": "EMAIL",
                  "US_SSN": "SSN", "LOCATION": "ADDRESS"}

try:  # optional, much better at free-text names
    from presidio_analyzer import AnalyzerEngine  # type: ignore
    _analyzer = AnalyzerEngine()
except Exception:  # not installed: patterns only
    _analyzer = None


def presidio_available() -> bool:
    return _analyzer is not None


def mask(text: str) -> tuple[str, list[str]]:
    """Return (masked_text, list of tags that were found)."""
    found: list[str] = []
    if _analyzer is not None:
        spans: list[list] = []  # [start, end, tag], overlapping results merged
        for r in sorted(_analyzer.analyze(text=text, language="en", entities=list(_PRESIDIO_TAGS)),
                        key=lambda r: (r.start, -r.end)):
            if spans and r.start < spans[-1][1]:
                spans[-1][1] = max(spans[-1][1], r.end)
            else:
                spans.append([r.start, r.end, _PRESIDIO_TAGS[r.entity_type]])
        for start, end, tag in reversed(spans):
            found.append(tag)
            # Hidden characters inside a masked span stay, so the guardrail check still sees them.
            text = text[:start] + f"[{tag}]" + "".join(HIDDEN_CHARS.findall(text[start:end])) + text[end:]
    for tag, rx in _COMPILED:
        if rx.search(text):
            found.append(tag)
            text = rx.sub(f"[{tag}]", text)
    return text, sorted(set(found))
