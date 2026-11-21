"""Tool executor argument checks (audit findings A1, A4, A20)."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent.tools import ToolExecutor

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
