"""Masking must behave the same with or without Presidio.  Run:  python3 -m unittest -v"""
import json
import os
import unittest
from pathlib import Path
from unittest import mock

os.environ["MOCK_LLM"] = "1"
from app import privacy  # noqa: E402
from app.guardrails import HIDDEN_CHARS, Guardrails  # noqa: E402

POLICY = json.loads((Path(__file__).resolve().parent.parent / "config" / "policy.json").read_text(encoding="utf-8"))
needs_presidio = unittest.skipUnless(privacy.presidio_available(), "Presidio is not installed")


class Hit:
    def __init__(self, entity_type, start, end):
        self.entity_type, self.start, self.end = entity_type, start, end


class FakeAnalyzer:
    """Stands in for Presidio, so the replacement logic is tested on the standard library alone."""
    def __init__(self, hits):
        self.hits, self.asked = hits, None

    def analyze(self, text, language, entities=None):
        self.asked = entities
        return self.hits


class Masking(unittest.TestCase):
    def test_zero_width_word_is_not_swallowed(self):
        text, tags = privacy.mask("Summarise this note​ please")
        self.assertEqual((text, tags), ("Summarise this note​ please", []))

    def test_age_and_days_ago_reach_the_model(self):
        line = "- 3 days ago, Visit note: 67-year-old female, Age 67, review in 1 week"
        self.assertEqual(privacy.mask(line), (line, []))

    def test_answer_with_tomorrow_is_not_a_leak(self):
        out = Guardrails(POLICY).check_output("The next free slot is tomorrow at 9am, or in 1 week.", [])
        self.assertEqual((out["tier"], out["flags"]), ("green", []))

    @needs_presidio
    def test_presidio_names_get_bracket_tags(self):
        text, tags = privacy.mask("Please call John Smith about his results")
        self.assertEqual((text, tags), ("Please call [NAME] about his results", ["NAME"]))

    @needs_presidio
    def test_presidio_keeps_hidden_character_inside_a_name(self):
        text, tags = privacy.mask("Ask Jo​hn Smith in Chicago to call 555-201-3344")
        self.assertNotIn("Smith", text)
        self.assertTrue(HIDDEN_CHARS.search(text))
        self.assertEqual(tags, ["ADDRESS", "NAME", "PHONE"])

    def test_replacement_maps_tags_merges_overlaps_and_keeps_hidden_characters(self):
        raw = "Ask Jo​hn Smith Street today, mail a@b.co"
        fake = FakeAnalyzer([Hit("LOCATION", 10, 22), Hit("PERSON", 4, 15), Hit("EMAIL_ADDRESS", 35, 41)])
        with mock.patch.object(privacy, "_analyzer", fake):
            text, tags = privacy.mask(raw)
        self.assertEqual(text, "Ask [NAME]​ today, mail [EMAIL]")
        self.assertEqual(tags, ["EMAIL", "NAME"])
        self.assertEqual(sorted(fake.asked), ["EMAIL_ADDRESS", "LOCATION", "PERSON", "PHONE_NUMBER", "US_SSN"])


if __name__ == "__main__":
    unittest.main()
