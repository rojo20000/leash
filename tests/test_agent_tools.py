"""Tool executor argument checks (audit findings A1, A4, A20)."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent.tools import ALL_RESOURCE_TYPES, ToolExecutor, call_facts

ROOT = Path(__file__).resolve().parents[1]


class Spy:
    """Records every request the executor sends to the EHR."""

    def __init__(self, client):
        self.client, self.urls = client, []

    def get(self, path, **kw):
        self.urls.append(path)
        return self.client.get(path, **kw)

    def post(self, path, **kw):
        self.urls.append(path)
        return self.client.post(path, **kw)


@pytest.fixture
def ehr():
    try:
        import ehr.app as e
        if not (ROOT / "data" / "generated" / "fhir_bundle.json").exists():
            raise FileNotFoundError
    except (ImportError, FileNotFoundError):
        pytest.skip("EHR not built yet")
    return Spy(TestClient(e.create_app(data_dir=str(ROOT / "data" / "generated"))))


@pytest.fixture
def ex(ehr, tmp_path):
    return ToolExecutor(ehr, str(tmp_path / "sink.jsonl"), "unprotected", "s-test")


def sink_lines(ex):
    p = Path(ex.sink_path)
    return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []


# A1: ids go into the EHR URL path, so anything but a plain id must be refused before a request is made
APPT = {"start": "2026-12-01T09:00:00", "reason": "follow-up"}
BAD_ID_CALLS = [
    ("read_document", {"document_id": "../Condition?patient=pt-0042&x="}),
    ("read_document", {"document_id": "../MedicationRequest?patient=pt-0042&x="}),
    ("read_record", {"patient_id": "x/../../Condition?patient=pt-0042&x=", "resource_types": ["Patient"]}),
    ("read_record", {"patient_id": "../DocumentReference/ref-0042/text", "resource_types": ["Patient"]}),
    ("read_record", {"patient_id": "..", "resource_types": ["Patient"]}),
    ("read_document", {"document_id": "."}),
    ("read_document", {"document_id": "ref-0042\n"}),
    ("read_record", {"patient_id": "p" * 65}),
    ("update_appointment", {"patient_id": "../pt-0042", **APPT}),
]


@pytest.mark.parametrize("tool,args", BAD_ID_CALLS)
def test_a1_bad_id_is_refused_before_any_ehr_request(ex, ehr, tool, args):
    with pytest.raises(ValueError):
        ex.execute(tool, args)
    assert ehr.urls == []


def test_a1_valid_ids_still_work(ex, ehr):
    rec = ex.execute("read_record", {"patient_id": "pt-0042", "resource_types": ["Patient", "Condition"]})
    assert rec["patient_id"] == "pt-0042" and rec["resources"]["Patient"][0]["id"] == "pt-0042"
    assert {c["subject"]["reference"] for c in rec["resources"]["Condition"]} <= {"Patient/pt-0042"}
    assert ex.execute("read_document", {"document_id": "ref-0042"})["text"]
    assert ex.execute("update_appointment", {"patient_id": "pt-0042", **APPT})["encounter"]
    assert ehr.urls == ["/fhir/Patient/pt-0042", "/fhir/Condition", "/fhir/DocumentReference/ref-0042/text",
                        "/fhir/Encounter"]


# A4: one plain address per recipient, checked before anything is written to the sink
EMAIL = {"subject": "s", "body": "b"}
BAD_RECIPIENTS = [
    ["attacker@outside-clinic.example, frontdesk@clinic.example.org"],
    ["frontdesk@clinic.example.org", "attacker@outside-clinic.example,frontdesk@clinic.example.org"],
    [" frontdesk@clinic.example.org"],
    ["frontdesk@clinic.example.org\n"],
    ["a@b@clinic.example.org"],
    ["Front Desk <frontdesk@clinic.example.org>"],
    ["frontdesk@localhost"],
]


@pytest.mark.parametrize("to", BAD_RECIPIENTS)
def test_a4_recipient_that_is_not_one_plain_address_is_refused(ex, to):
    with pytest.raises(ValueError, match="bad args for send_email"):
        ex.execute("send_email", {"to": to, **EMAIL})
    assert sink_lines(ex) == []


def test_a4_plain_addresses_still_send(ex):
    assert ex.execute("send_email", {"to": ["frontdesk@clinic.example.org"], **EMAIL})["message_id"] == "m-0001"
    assert ex.execute("send_email", {"to": "a.b+c@d-e.co.uk", **EMAIL})["message_id"] == "m-0002"
    assert [x["to"] for x in sink_lines(ex)] == [["frontdesk@clinic.example.org"], ["a.b+c@d-e.co.uk"]]


def test_a4_recorded_demo_recipients_are_accepted(ex):
    rec = json.loads((ROOT / "demo" / "recordings" / "referrals.json").read_text(encoding="utf-8"))
    tos = [c["args"]["to"] for c in rec["calls"] if c["tool"] == "send_email"]
    for to in tos:
        ex.execute("send_email", {"to": to, **EMAIL})
    assert tos and [x["to"] for x in sink_lines(ex)] == tos


# A20: call_facts never raises and always returns three lists of strings
ODD_ARGS = [
    ("read_record", {"patient_id": 42}, (ALL_RESOURCE_TYPES, ["42"], [])),
    ("read_record", {"patient_id": "pt-0042", "resource_types": [1]}, (["1"], ["pt-0042"], [])),
    ("send_email", {"to": [None]}, ([], [], ["None"])),
    ("send_email", {"to": 5}, ([], [], ["5"])),
    ("read_record", None, (ALL_RESOURCE_TYPES, [], [])),
    ("update_appointment", None, (["Encounter"], [], [])),
    ("send_email", None, ([], [], [])),
    ("read_record", [1], (ALL_RESOURCE_TYPES, [], [])),
    ("send_email", "x", ([], [], [])),
    ("read_record", {"patient_id": ["a", "b"], "resource_types": "Condition"}, (["Condition"], ["['a', 'b']"], [])),
    ("read_record", {"patient_id": None, "resource_types": {"a": 1}}, (["{'a': 1}"], [], [])),
    ("update_appointment", {"patient_id": {"a": 1}}, (["Encounter"], ["{'a': 1}"], [])),
    ("send_email", {"to": {"a": 1}}, ([], [], ["{'a': 1}"])),
    ("send_email", {"to": ["a@b.org", 5, ["c"]]}, ([], [], ["a@b.org", "5", "['c']"])),
]


@pytest.mark.parametrize("tool,args,want", ODD_ARGS)
def test_a20_call_facts_returns_lists_of_strings_for_any_args(tool, args, want):
    got = call_facts(tool, args)
    assert got == want
    assert all(type(part) is list and all(type(x) is str for x in part) for part in got)


def test_a20_call_facts_unchanged_for_valid_calls():
    assert call_facts("search_patients", {"name": "a"}) == (["Patient"], [], [])
    assert call_facts("read_record", {"patient_id": "pt-0007"}) == (ALL_RESOURCE_TYPES, ["pt-0007"], [])
    assert call_facts("read_record", {"patient_id": "pt-0007", "resource_types": ["Patient", "Encounter"]}) == (
        ["Patient", "Encounter"], ["pt-0007"], [])
    assert call_facts("read_document", {"document_id": "ref-0007"}) == (["DocumentReference"], [], [])
    assert call_facts("update_appointment", {"patient_id": "pt-0007"}) == (["Encounter"], ["pt-0007"], [])
    assert call_facts("send_email", {"to": ["a@b.org", "c@d.org"]}) == ([], [], ["a@b.org", "c@d.org"])
    assert call_facts("send_email", {"to": "a@b.org"}) == ([], [], ["a@b.org"])
    assert call_facts("nope", {}) == ([], [], [])
    assert call_facts("read_record", {})[0] is not ALL_RESOURCE_TYPES  # callers get a copy, as before
