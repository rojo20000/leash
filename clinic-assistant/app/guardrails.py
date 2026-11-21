"""Score each request and each answer green, amber or red.

green  no flags: the answer goes to the asker as a normal draft (a random
       sample is copied to QA, so nothing is guaranteed to skip a person)
amber  something looks off: the answer is held until the asker reads the
       reasons and confirms they reviewed it
red    blocked: nothing is shown; a second person reviews it
"""
from __future__ import annotations

import re

from . import llm, privacy

REVIEW_NOTE = "\n\n---\nAI draft for clinician review. Not a diagnosis or a treatment decision."
URGENT_NOTE = ("If this is happening now, follow the clinic's emergency protocol "
               "immediately. Do not wait for this tool.")
HIDDEN_CHARS = re.compile("[​-‏‪-‮⁠-⁤﻿\U000e0000-\U000e007f]")
RANK = {"green": 0, "amber": 1, "red": 2}


def worst(*tiers: str) -> str:
    return max(tiers, key=RANK.__getitem__)


class Guardrails:
    def __init__(self, policy: dict):
        s = policy["scope"]
        rx = lambda pats: [re.compile(p, re.I) for p in pats]
        self.blocked = rx(s["blocked_input_patterns"])
        self.off_topic = rx(s["out_of_scope_patterns"])
        self.urgent = rx(s["urgent_patterns"])
        self.overconfident = rx(s["overconfident_output_patterns"])
        self.dangerous = rx(s.get("dangerous_output_patterns", []))
        self.doc_patterns = self.blocked + rx(s.get("document_injection_patterns", []))
        self.tiers = policy.get("tiers", {})
        self.policy = policy
        self.vectors = None  # set by the app: a VectorStore holding known injection examples

    def injection_similarity(self, text: str) -> float | None:
        """Similarity to the closest known injection example, or None if not configured."""
        if self.vectors is None:
            return None
        thr = self.policy.get("vectors", {}).get("injection_similarity", {}).get(self.vectors.embedder.mode)
        if thr is None:
            return None  # no calibrated threshold for this embedder: rely on the fixed patterns
        hits = self.vectors.search("injection_examples", text, k=1)
        return hits[0]["score"] if hits and hits[0]["score"] >= thr else None

    def check_input(self, text: str) -> dict:
        """Return {'tier', 'reasons', 'flags'} for a request (already masked)."""
        if any(r.search(text) for r in self.blocked):
            return {"tier": "red", "reasons": ["Looks like an attempt to change the assistant's rules."],
                    "flags": ["prompt_injection"]}
        if any(r.search(text) for r in self.off_topic):
            return {"tier": "red", "reasons": ["Outside this assistant's clinical scope."], "flags": ["out_of_scope"]}
        if llm.safety_check(self.policy, text) == "unsafe":
            return {"tier": "red", "reasons": ["Blocked by the safety model."], "flags": ["safety_model"]}
        reasons, flags = [], []
        if HIDDEN_CHARS.search(text):
            reasons.append("Hidden characters in the text, a common way to smuggle instructions.")
            flags.append("hidden_characters")
        if len(text) > self.tiers.get("long_paste_chars", 1500):
            reasons.append("Long pasted text; pasted documents can carry hidden instructions.")
            flags.append("long_paste")
        if any(r.search(text) for r in self.urgent):
            reasons.append("Mentions a possible emergency.")
            flags.append("urgent")
        return {"tier": "amber" if reasons else "green", "reasons": reasons, "flags": flags}

    def check_output(self, text: str, input_flags: list[str]) -> dict:
        """Return {'tier', 'reasons', 'flags', 'text'} for a model answer."""
        masked, leaked = privacy.mask(text)
        if leaked:
            return {"tier": "red", "reasons": ["The answer contained a patient identifier."],
                    "flags": ["identifier_in_output"], "text": masked}
        if any(r.search(masked) for r in self.dangerous):
            return {"tier": "red", "reasons": ["The answer contains a dangerous instruction."],
                    "flags": ["dangerous_instruction"], "text": masked}
        reasons, flags = [], []
        if any(r.search(masked) for r in self.overconfident):
            reasons.append("Uses definitive clinical language.")
            flags.append("overconfident_language")
        if "urgent" in input_flags:
            masked = URGENT_NOTE + "\n\n" + masked
        return {"tier": "amber" if reasons else "green", "reasons": reasons, "flags": flags,
                "text": masked + REVIEW_NOTE}

    def scan_document(self, text: str) -> list[str]:
        """Reasons a document must not reach the model (empty list if it is clean)."""
        reasons = []
        if any(r.search(text) for r in self.doc_patterns):
            reasons.append("Contains instructions aimed at the AI (possible prompt injection).")
        else:
            sim = self.injection_similarity(text)
            if sim is not None:
                reasons.append(f"Reads like a known prompt-injection pattern (similarity {sim:.2f}).")
        if HIDDEN_CHARS.search(text):
            reasons.append("Contains hidden characters.")
        return reasons
