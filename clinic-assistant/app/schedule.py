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
    def __init__(self, path: Path, clinic: dict, patients: dict, now=_now):
        self.path, self.clinic, self.patients, self.now = path, clinic, patients, now
        self.lock = threading.Lock()
        if not path.exists():
            path.write_text("[]")
        today = self.now().date()
        with self.lock:
            items = self._load()
            seeded = {a["date"] for a in items}
            for d in (today, today + timedelta(days=1)):
                if d.isoformat() not in seeded:
                    items += self._seed_day(d)
            self._save(items)

    # ---- storage ---------------------------------------------------------
    def _load(self) -> list[dict]:
        return json.loads(self.path.read_text())

    def _save(self, items: list[dict]) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(items, indent=1))
        tmp.replace(self.path)  # atomic: a crash never leaves a half-written schedule

    # ---- slots -----------------------------------------------------------
    def slots(self) -> list[str]:
        start, end = (datetime.strptime(t, "%H:%M") for t in self.clinic["hours"])
        step, out = timedelta(minutes=self.clinic["slot_minutes"]), []
        while start + step <= end:
            out.append(start.strftime("%H:%M"))
            start += step
        return out

    def open_slots(self, day: str, clinician: str) -> list[str]:
        taken = {a["time"] for a in self._load()
                 if a["date"] == day and a["clinician"] == clinician and a["status"] in ACTIVE}
        now = self.now()
        return [t for t in self.slots() if t not in taken
                and datetime.fromisoformat(f"{day}T{t}") > now]

    # ---- demo data -------------------------------------------------------
    def _seed_day(self, d: date) -> list[dict]:
        """A believable day: most slots filled, a few gaps, and one of each kind of case on the first clinician's list."""
        rng = random.Random(d.toordinal())
        ids = sorted(self.patients)
        first, rest = ids[:13], ids[13:]  # the first 13 records cover every scenario once
        rng.shuffle(first); rng.shuffle(rest)
        pool = [self.patients[i] for i in (first + rest if d == self.now().date() else rest + first)]
        out, slots = [], self.slots()
        for c_i, clinician in enumerate(self.clinic["clinicians"]):
            chosen = [s for s in slots if rng.random() < 0.55][:12]
            for t in chosen:
                if not pool:
                    break
                p = pool.pop(0) if c_i == 0 else pool.pop(rng.randrange(len(pool)))
                out.append(self._new(d.isoformat(), t, clinician, p["id"],
                                     rng.choice(self.clinic["visit_types"]), "system"))
        return out

    @staticmethod
    def _new(day, time, clinician, pid, visit_type, by) -> dict:
        return {"id": uuid.uuid4().hex[:10], "date": day, "time": time, "clinician": clinician,
                "patient_id": pid, "visit_type": visit_type, "status": "booked", "cancel_reason": None,
                "reminder": None, "history": [{"at": _now().isoformat(timespec="minutes"), "by": by,
                                               "status": "booked"}]}

    # ---- reads -----------------------------------------------------------
    def day(self, day: str) -> list[dict]:
        return sorted((a for a in self._load() if a["date"] == day), key=lambda a: (a["time"], a["clinician"]))

    def get(self, appt_id: str) -> dict | None:
        return next((a for a in self._load() if a["id"] == appt_id), None)

    # ---- the only ways to change anything --------------------------------
    def book(self, by: str, pid: str, day: str, time: str, clinician: str, visit_type: str) -> dict:
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
            items = self._load()
            clash = next((a for a in items if a["date"] == day and a["patient_id"] == pid
                          and a["status"] in ACTIVE), None)
            if clash:
                raise ScheduleError(f"This patient already has an appointment that day at {clash['time']}. "
                                    "Cancel or move that one first.")
            appt = self._new(day, time, clinician, pid, visit_type, by)
            items.append(appt)
            self._save(items)
        return appt

    def change_status(self, by: str, perms: list[str], appt_id: str, expected: str, to: str,
                      checks: dict | None = None, reason: str | None = None) -> dict:
        need = TRANSITIONS.get((expected, to))
        if need is None:
            raise ScheduleError("That step isn't possible from here.")
        if need not in perms:
            raise ScheduleError("Your role can't do that step.")
        checks = checks or {}
        with self.lock:
            items = self._load()
            a = next((x for x in items if x["id"] == appt_id), None)
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
            self._save(items)
        return a

    def reminder(self, by: str, appt_id: str, action: str) -> dict:
        """prepare: fixed wording, no clinical detail. sent: a person confirms they sent it."""
        with self.lock:
            items = self._load()
            a = next((x for x in items if x["id"] == appt_id), None)
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
            else:
                raise ScheduleError("Unknown reminder step.")
            self._save(items)
        return a

    def reminder_text(self, a: dict) -> str:
        p, c = self.patients[a["patient_id"]], self.clinic
        when = datetime.fromisoformat(f"{a['date']}T{a['time']}")
        return (f"Hello {p['name']['given']}, this is {c['name']} reminding you of your appointment with "
                f"{c['clinicians'][a['clinician']]} on {when.strftime('%A %-d %B')} at {when.strftime('%-I:%M %p')}. "
                f"Please bring your insurance card. Reply YES to confirm, or call {c['phone']} to change it.")
