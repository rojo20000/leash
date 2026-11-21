import pytest
from fastapi.testclient import TestClient

from data.generate import ATTACKER_EMAIL, HIDDEN_TEXT, generate
from ehr.app import create_app


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    d = tmp_path_factory.mktemp("ehr")
    generate(42, d)
    return TestClient(create_app(data_dir=str(d)))


def test_health(client):
    assert client.get("/health").json() == {"status": "ok", "patients": 200}


def test_patient_search_and_get(client):
    p = client.get("/fhir/Patient/pt-0042").json()
    fam = p["name"][0]["family"]
    b = client.get("/fhir/Patient", params={"name": fam.upper(), "_count": 5}).json()
    assert b["resourceType"] == "Bundle" and b["type"] == "searchset" and 1 <= b["total"] <= 5
    b = client.get("/fhir/Patient", params={"birthdate": p["birthDate"]}).json()
    assert any(e["resource"]["id"] == "pt-0042" for e in b["entry"])
    r = client.get("/fhir/Patient/pt-9999")
    assert r.status_code == 404 and r.json() == {"detail": "not found"}


@pytest.mark.parametrize("t", ["Condition", "MedicationRequest", "Encounter", "DocumentReference"])
def test_linked(client, t):
    b = client.get(f"/fhir/{t}", params={"patient": "pt-0042"}).json()
    assert all(e["resource"]["subject"]["reference"] == "Patient/pt-0042" for e in b["entry"])
    assert b["total"] == len(b["entry"]) >= (1 if t != "MedicationRequest" else 0)


def test_referrals_and_text(client):
    b = client.get("/fhir/DocumentReference", params={"type": "Referral", "date": "2026-11-21"}).json()
    assert sorted(e["resource"]["id"] for e in b["entry"]) == ["ref-0007", "ref-0019", "ref-0042", "ref-0101", "ref-0150"]
    t = client.get("/fhir/DocumentReference/ref-0042/text").json()
    assert t["patient_id"] == "pt-0042" and HIDDEN_TEXT in " ".join(t["text"].split())
    assert ATTACKER_EMAIL not in client.get("/fhir/DocumentReference/ref-0007/text").json()["text"]
    assert client.get("/fhir/DocumentReference/ref-9999/text").status_code == 404


def test_create_and_reset(client):
    body = {"patient_id": "pt-0007", "start": "2026-11-28T10:00:00", "reason": "Cardiology follow-up"}
    r = client.post("/fhir/Encounter", json=body)
    assert r.status_code == 201 and r.json()["status"] == "planned" and r.json()["id"] == "enc-new-0001"
    n = client.get("/fhir/Encounter", params={"patient": "pt-0007"}).json()["total"]
    assert client.post("/admin/reset").json() == {"status": "reset"}
    assert client.get("/fhir/Encounter", params={"patient": "pt-0007"}).json()["total"] == n - 1
