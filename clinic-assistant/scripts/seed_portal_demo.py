"""Give the demo patient (pt_lena, linked to syn-002) something to see in the patient portal.

Run from the app folder:  python3 scripts/seed_portal_demo.py  [path/to/data]
Safe to run again: it adds an upcoming appointment only if there is none, and a welcome message only
if there are no messages. Every write goes through the database methods, so the change log stays intact.
Exit code 0 = done and chain intact, 1 = chain broken, 2 = the demo patient is not in the database.
"""
import json
import sys
import uuid
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.db import ClinicDB  # noqa: E402
from app.ehr import EHR  # noqa: E402
from app.schedule import Schedule, ScheduleError  # noqa: E402

PID = "syn-002"
DAYS_AHEAD = 3
SUBJECT = "Welcome to the patient portal"
BODY = ("Hello Lena, your portal account is ready: you can see your appointments and your health summary here, "
        "and send us a message when you have a question. Messages are read on working days, so please call "
        "the clinic if something cannot wait.")

data = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data"
clinic = json.loads((ROOT / "config" / "policy.json").read_text())["clinic"]
db = ClinicDB(data / "clinic.db")
ehr = EHR(data / "patients.json", db)
if PID not in ehr.patients:
    print(f"No patient {PID} in {data / 'clinic.db'}. Nothing changed.")
    sys.exit(2)
schedule = Schedule(data / "schedule.json", clinic, ehr.patients, db=db)  # the same wiring as app/server.py
today = schedule.now().date()


def upcoming():
    return [a for a in db.appointments_for_patient(PID) if a["status"] == "booked" and a["date"] >= today.isoformat()]


if not upcoming():
    day = today + timedelta(days=DAYS_AHEAD)
    schedule.ensure_day(day)  # the demo day may already give this patient an appointment
if upcoming():
    a = upcoming()[0]
    print(f"Appointment:  already has one on {a['date']} at {a['time']}. Nothing added.")
else:
    clinician, visit_type = next(iter(clinic["clinicians"])), clinic["visit_types"][0]
    try:
        times = schedule.open_slots(day.isoformat(), clinician)
        if not times:
            raise ScheduleError(f"{clinician} has no open time on {day}")
        a = schedule.book("desk_sam", PID, day.isoformat(), times[0], clinician, visit_type, role="receptionist")
        print(f"Appointment:  booked {visit_type} on {a['date']} at {a['time']} with {clinician}.")
    except ScheduleError as e:
        print(f"Appointment:  not booked ({e}).")

if db.portal_messages(PID):
    print("Message:      already has portal messages. Nothing added.")
else:
    db.add_portal_message({"id": uuid.uuid4().hex[:10], "patient_id": PID, "direction": "to_patient",
                           "sender": "nurse_kim", "sender_role": "nurse", "subject": SUBJECT, "body": BODY,
                           "source": "staff", "draft_id": None, "approved_by": None, "in_reply_to": None},
                          "nurse_kim", "nurse")
    print(f"Message:      added \"{SUBJECT}\" from nurse_kim.")

ok, checked, bad = db.verify_chain()
print(f"Change log:   {'OK, all ' + str(checked) + ' entries verified' if ok else 'BROKEN at seq ' + str(bad)}")
db.close()
sys.exit(0 if ok else 1)
