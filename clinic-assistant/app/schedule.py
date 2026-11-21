"""Appointments for the made-up clinic: booking, check-in and the day's flow.

Every change goes through one checked path (`change_status`, `book`), so the
screens cannot put an appointment into a state the clinic would not allow:

  booked  --check in-->  arrived  --start visit-->  in_room  --finish-->  done
     |                     |
     |                     +--undo check-in--> booked
     +--cancel (reason required)--> cancelled
     +--no-show (only after the grace period)--> no_show

Callers pass the status they saw ("expected"), so two people clicking at the
same time cannot both win; the second gets a clear "already changed" message.
"""
from __future__ import annotations

import json
import random
import threading
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

from .db import ClinicDB

# (from, to) -> the permission needed for that step
TRANSITIONS = {
    ("booked", "arrived"): "check_in",
    ("arrived", "booked"): "check_in",
    ("booked", "cancelled"): "book",
    ("booked", "no_show"): "check_in",
    ("arrived", "in_room"): "room_patient",
    ("in_room", "done"): "room_patient",
}
ACTIVE = {"booked", "arrived", "in_room"}


class ScheduleError(Exception):
    """A refused change. The message is shown to the person as is."""


def _now() -> datetime:
    return datetime.now().replace(second=0, microsecond=0)


class Schedule:
    """Appointments, stored in the clinic database (data/clinic.db).

    On first start, data/schedule.json (if any) is imported once and then left as it was.
    """

    def __init__(self, path: Path, clinic: dict, patients, now=_now, db: ClinicDB | None = None):
        self.path, self.clinic, self.patients, self.now = path, clinic, patients, now
        self.db = db or getattr(patients, "db", None) or ClinicDB(path.parent / "clinic.db")
        self.lock = threading.RLock()
        with self.lock:
            if self.db.get_meta("schedule_imported") is None:
                if path.exists():
                    items = json.loads(path.read_text())
                    if items:
                        self.db.write_many([("appointment", a, "imported", f"Imported from {path.name}")
                                            for a in items], "system", "system")
                    for d in {a["date"] for a in items}:
                        self.db.mark_seeded(d)
                self.db.set_meta("schedule_imported", path.name if path.exists() else "none")
        today = self.now().date()
        for d in (today, today + timedelta(days=1)):
            self.ensure_day(d)

    # ---- storage ---------------------------------------------------------
    def _save(self, a: dict, by: str, role: str | None, action: str, summary: str) -> dict:
        return self.db.write("appointment", a, action, by, role, summary)

    # ---- slots -----------------------------------------------------------
    def slots(self) -> list[str]:
        start, end = (datetime.strptime(t, "%H:%M") for t in self.clinic["hours"])
        step, out = timedelta(minutes=self.clinic["slot_minutes"]), []
        while start + step <= end:
            out.append(start.strftime("%H:%M"))
            start += step
        return out

    def open_slots(self, day: str, clinician: str) -> list[str]:
        taken = {a["time"] for a in self.db.appointments(day, day, clinician) if a["status"] in ACTIVE}
        now = self.now()
        return [t for t in self.slots() if t not in taken
                and datetime.fromisoformat(f"{day}T{t}") > now]

    # ---- demo data -------------------------------------------------------
    def ensure_day(self, d: date) -> None:
        """Fill a day with demo appointments the first time it is looked at (once per day, ever)."""
        day = d.isoformat()
        if self.db.seeded(day):
            return
        with self.lock:
            if self.db.seeded(day):
                return
            existing = self.db.appointments(day)
            items = self._seed_day(d, existing)
            if items:
                self.db.write_many([("appointment", a, "seeded", "Demo appointment added") for a in items],
                                   "system", "system")
            self.db.mark_seeded(day)

    def _seed_day(self, d: date, existing: list[dict] | None = None) -> list[dict]:
        """A believable day: most slots filled, a few gaps, and one of each kind of case on the first clinician's list.

        Past days come out finished (mostly done, a few no-shows); days with real bookings keep them.
        """
        existing = existing or []
        rng = random.Random(d.toordinal())
        ids = sorted(self.patients)
        first, rest = ids[:13], ids[13:]  # the first 13 records cover every scenario once
        rng.shuffle(first); rng.shuffle(rest)
        busy = {a["patient_id"] for a in existing if a["status"] in ACTIVE}
        taken = {(a["clinician"], a["time"]) for a in existing if a["status"] in ACTIVE}
        pool = [i for i in (first + rest if d == self.now().date() else rest + first) if i not in busy]
        past = d < self.now().date()
        out, slots = [], self.slots()
        for c_i, clinician in enumerate(self.clinic["clinicians"]):
            chosen = [s for s in slots if rng.random() < 0.55][:12]
            for t in chosen:
                if not pool:
                    break
                pid = pool.pop(0) if c_i == 0 else pool.pop(rng.randrange(len(pool)))
                if (clinician, t) in taken:
                    continue
                a = self._new(d.isoformat(), t, clinician, pid, rng.choice(self.clinic["visit_types"]), "system")
                if past:
                    end = "no_show" if rng.random() < 0.1 else "done"
                    a["status"] = end
                    a["history"].append({"at": f"{d.isoformat()}T{t}", "by": "system", "status": end})
                out.append(a)
        return out

    @staticmethod
    def _new(day, time, clinician, pid, visit_type, by) -> dict:
        return {"id": uuid.uuid4().hex[:10], "date": day, "time": time, "clinician": clinician,
                "patient_id": pid, "visit_type": visit_type, "status": "booked", "cancel_reason": None,
                "reminder": None, "history": [{"at": _now().isoformat(timespec="minutes"), "by": by,
                                               "status": "booked"}]}

    # ---- reads -----------------------------------------------------------
    def day(self, day: str) -> list[dict]:
        return self.db.appointments(day)

    def between(self, start: str, end: str, clinician: str | None = None) -> list[dict]:
        return self.db.appointments(start, end, clinician)

    def get(self, appt_id: str) -> dict | None:
        return self.db.appointment(appt_id)

    # ---- the only ways to change anything --------------------------------
    def book(self, by: str, pid: str, day: str, time: str, clinician: str, visit_type: str,
             role: str | None = None) -> dict:
        c = self.clinic
        if pid not in self.patients:
            raise ScheduleError("Pick the patient from the search results.")
        if clinician not in c["clinicians"]:
            raise ScheduleError("Pick a clinician from the list.")
        if visit_type not in c["visit_types"]:
            raise ScheduleError("Pick a visit type from the list.")
        try:
            d = date.fromisoformat(day)
        except ValueError:
            raise ScheduleError("Pick a date from the list.") from None
        today = self.now().date()
        if not today <= d <= today + timedelta(days=c["booking_days_ahead"]):
            raise ScheduleError(f"Appointments can be booked from today up to {c['booking_days_ahead']} days ahead.")
        if time not in self.slots():
            raise ScheduleError("Pick one of the listed times.")
        with self.lock:
            if time not in self.open_slots(day, clinician):
                raise ScheduleError("That time was just taken or has passed. Pick another open time.")
            clash = next((a for a in self.db.appointments(day) if a["patient_id"] == pid
                          and a["status"] in ACTIVE), None)
            if clash:
                raise ScheduleError(f"This patient already has an appointment that day at {clash['time']}. "
                                    "Cancel or move that one first.")
            appt = self._new(day, time, clinician, pid, visit_type, by)
            self._save(appt, by, role, "booked", f"Booked {visit_type} on {day} at {time} with {clinician}")
        return appt

    def change_status(self, by: str, perms: list[str], appt_id: str, expected: str, to: str,
                      checks: dict | None = None, reason: str | None = None, role: str | None = None) -> dict:
        need = TRANSITIONS.get((expected, to))
        if need is None:
            raise ScheduleError("That step isn't possible from here.")
        if need not in perms:
            raise ScheduleError("Your role can't do that step.")
        checks = checks or {}
        with self.lock:
            a = self.db.appointment(appt_id)
            if a is None:
                raise ScheduleError("That appointment no longer exists. The list has been refreshed.")
            if a["status"] != expected:
                raise ScheduleError(f"Someone already changed this appointment (it is now "
                                    f"'{a['status'].replace('_', ' ')}'). The list has been refreshed.")
            now = self.now()
            is_today = a["date"] == now.date().isoformat()
            if to in ("arrived", "in_room", "no_show") and not is_today:
                raise ScheduleError("Only today's appointments can be checked in or marked.")
            if to == "arrived" and not (checks.get("dob") is True and checks.get("insurance") is True):
                raise ScheduleError("Confirm the date of birth and the insurance card before checking in.")
            if to == "no_show":
                due = datetime.fromisoformat(f"{a['date']}T{a['time']}") + timedelta(
                    minutes=self.clinic["no_show_after_minutes"])
                if now < due:
                    raise ScheduleError(f"Too early to mark a no-show. Wait until {due.strftime('%H:%M')}.")
            if to == "cancelled":
                if reason not in self.clinic["cancel_reasons"]:
                    raise ScheduleError("Pick a reason for cancelling.")
                a["cancel_reason"] = reason
            a["status"] = to
            a["history"].append({"at": now.isoformat(timespec="minutes"), "by": by, "status": to})
            action = ("checked_in" if (expected, to) == ("booked", "arrived") else
                      "check_in_undone" if (expected, to) == ("arrived", "booked") else "status_change")
            summary = (f"{expected.replace('_', ' ')} -> {to.replace('_', ' ')}"
                       + (f" ({reason})" if to == "cancelled" else ""))
            self._save(a, by, role, action, summary)
        return a

    def reminder(self, by: str, appt_id: str, action: str, role: str | None = None) -> dict:
        """prepare: fixed wording, no clinical detail. sent: a person confirms they sent it."""
        with self.lock:
            a = self.db.appointment(appt_id)
            if a is None:
                raise ScheduleError("That appointment no longer exists.")
            if a["status"] != "booked":
                raise ScheduleError("Reminders are only for appointments that are still booked.")
            if a["date"] <= self.now().date().isoformat():
                raise ScheduleError("Reminders are for upcoming days, not today.")
            r = a.get("reminder") or {}
            if action == "prepare":
                if r.get("sent_at"):
                    raise ScheduleError(f"Already sent by {r['sent_by']} at {r['sent_at']}.")
                a["reminder"] = {"prepared_by": by, "sent_by": None, "sent_at": None}
            elif action == "sent":
                if not r:
                    raise ScheduleError("Prepare the reminder first.")
                if r.get("sent_at"):
                    raise ScheduleError(f"Already marked sent by {r['sent_by']} at {r['sent_at']}.")
                r.update(sent_by=by, sent_at=self.now().isoformat(timespec="minutes"))
                a["reminder"] = r
            else:
                raise ScheduleError("Unknown reminder step.")
            self._save(a, by, role, "reminder_" + ("prepared" if action == "prepare" else "sent"),
                       "Reminder " + ("prepared" if action == "prepare" else "marked sent"))
        return a

    def reminder_text(self, a: dict) -> str:
        p, c = self.patients[a["patient_id"]], self.clinic
        when = datetime.fromisoformat(f"{a['date']}T{a['time']}")
        return (f"Hello {p['name']['given']}, this is {c['name']} reminding you of your appointment with "
                f"{c['clinicians'][a['clinician']]} on {when:%A} {when.day} {when:%B} at {when.hour % 12 or 12}:{when:%M %p}. "
                f"Please bring your insurance card. Reply YES to confirm, or call {c['phone']} to change it.")
