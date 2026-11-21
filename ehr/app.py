"""Mock EHR FastAPI service (CONTRACTS C4.1). Synthetic data only."""
import copy
import json
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from pypdf import PdfReader

LINKED = {"Condition", "MedicationRequest", "Encounter", "DocumentReference"}


class NewEncounter(BaseModel):
    patient_id: str
    start: str
    reason: str = ""


def _bundle(resources):
    return {"resourceType": "Bundle", "type": "searchset", "total": len(resources),
            "entry": [{"resource": r} for r in resources]}


def create_app(data_dir: str | None = None) -> FastAPI:
    root = Path(data_dir or os.environ.get("LEASH_DATA_DIR", "data/generated"))
    resources = [e["resource"] for e in json.loads((root / "fhir_bundle.json").read_text())["entry"]]
    patients = [r for r in resources if r["resourceType"] == "Patient"]
    by_id = {r["id"]: r for r in resources}
    created: list[dict] = []
    text_cache: dict[str, str] = {}
    app = FastAPI(title="Leash mock EHR")

    @app.get("/health")
    def health():
        return {"status": "ok", "patients": len(patients)}

    @app.get("/fhir/Patient")
    def search_patients(name: str | None = None, birthdate: str | None = None, _count: int = 20):
        out = []
        for p in patients:
            n = p["name"][0]
            full = " ".join(n["given"] + [n["family"]]).lower()
            if name and name.lower() not in full:
                continue
            if birthdate and p["birthDate"] != birthdate:
                continue
            out.append(p)
        return _bundle(out[:_count])

    @app.get("/fhir/Patient/{pid}")
    def get_patient(pid: str):
        p = by_id.get(pid)
        if not p or p["resourceType"] != "Patient":
            return JSONResponse({"detail": "not found"}, status_code=404)
        return p

    @app.get("/fhir/DocumentReference/{doc_id}/text")
    def doc_text(doc_id: str):
        d = by_id.get(doc_id)
        if not d or d["resourceType"] != "DocumentReference":
            return JSONResponse({"detail": "not found"}, status_code=404)
        if doc_id not in text_cache:
            pdf = root / "referrals" / f"{doc_id}.pdf"
            text_cache[doc_id] = "\n".join(pg.extract_text() or "" for pg in PdfReader(str(pdf)).pages)
        return {"document_id": doc_id, "patient_id": d["subject"]["reference"].split("/")[1],
                "text": text_cache[doc_id]}

    @app.get("/fhir/{rtype}")
    def search_linked(rtype: str, patient: str | None = None, type: str | None = None, date: str | None = None):
        if rtype not in LINKED:
            raise HTTPException(404, "not found")
        out = [r for r in resources + created if r["resourceType"] == rtype]
        if patient:
            out = [r for r in out if r["subject"]["reference"] == f"Patient/{patient}"]
        if type:
            out = [r for r in out if r.get("type", {}).get("text") == type]
        if date:
            out = [r for r in out if r.get("date", "").startswith(date)]
        return _bundle(out)

    @app.post("/fhir/Encounter", status_code=201)
    def create_encounter(body: NewEncounter):
        if body.patient_id not in by_id:
            raise HTTPException(404, "not found")
        enc = {"resourceType": "Encounter", "id": f"enc-new-{len(created) + 1:04d}", "status": "planned",
               "class": {"code": "AMB"}, "subject": {"reference": f"Patient/{body.patient_id}"},
               "period": {"start": body.start}, "reasonCode": [{"text": body.reason}]}
        created.append(enc)
        return copy.deepcopy(enc)

    @app.post("/admin/reset")
    def reset():
        created.clear()
        return {"status": "reset"}

    return app


app = create_app()
