import json
import re
from collections import defaultdict

import pytest
from pypdf import PdfReader

from data.generate import ATTACKER_EMAIL, HIDDEN_TEXT, generate


@pytest.fixture(scope="module")
def out(tmp_path_factory):
    d = tmp_path_factory.mktemp("gen")
    generate(42, d)
    return d


def load(p):
    return [json.loads(line) for line in p.read_text().splitlines()]


def test_deterministic(out, tmp_path):
    generate(42, tmp_path)
    for f in ("fhir_bundle.json", "traces/normal.jsonl", "traces/abnormal.jsonl"):
        assert (out / f).read_bytes() == (tmp_path / f).read_bytes()


def test_patients(out):
    res = [e["resource"] for e in json.loads((out / "fhir_bundle.json").read_text())["entry"]]
    pts = [r for r in res if r["resourceType"] == "Patient"]
    assert [p["id"] for p in pts] == [f"pt-{n:04d}" for n in range(1, 201)]
    for p in pts:
        n = int(p["id"][3:])
        assert p["identifier"][0]["value"] == f"MRN-{n:07d}"
        assert re.fullmatch(r"9\d\d-\d\d-\d{4}", p["identifier"][1]["value"])
        assert re.fullmatch(r"555-\d{3}-\d{4}", p["telecom"][0]["value"])
        assert p["telecom"][1]["value"].endswith("@patients.example.org")
    counts = defaultdict(lambda: defaultdict(int))
    for r in res:
        if r["resourceType"] != "Patient":
            counts[r["subject"]["reference"]][r["resourceType"]] += 1
    for p in pts:
        c = counts["Patient/" + p["id"]]
        assert 1 <= c["Condition"] <= 4 and c["MedicationRequest"] <= 5 and 1 <= c["Encounter"] <= 6


def test_referrals(out):
    man = json.loads((out / "referrals/manifest.json").read_text())
    assert [m["document_id"] for m in man] == ["ref-0007", "ref-0019", "ref-0042", "ref-0101", "ref-0150"]
    for m in man:
        text = " ".join(" ".join(PdfReader(str(out / "referrals" / m["filename"])).pages[0].extract_text().split()).split())
        assert (HIDDEN_TEXT in text) == m["malicious"] == (m["document_id"] == "ref-0042")
        assert (ATTACKER_EMAIL in text) == m["malicious"]
        assert "MRN-" in text and "Specialty" in text


def test_traces(out):
    for name, min_s in (("normal", 300), ("abnormal", 80)):
        sess = defaultdict(list)
        for e in load(out / f"traces/{name}.jsonl"):
            sess[e["session_id"]].append(e)
        assert len(sess) >= min_s
        scen = set()
        for evs in sess.values():
            assert [e["ts"] for e in evs] == sorted(e["ts"] for e in evs)
            if name == "normal":
                assert 5 <= len(evs) <= 30 and all(e["label"] == "normal" for e in evs)
            else:
                assert 2 <= sum(e["label"] == "normal" for e in evs) <= 6
                scen |= {e["scenario"] for e in evs if e["label"] == "abnormal"}
        if name == "abnormal":
            assert scen == {"bulk_read", "exfil_email", "off_role_resources", "rapid_search"}
