"""Appointments: create, ask about, cancel. Also adds a reminder one hour before."""
from datetime import datetime, timedelta

import db
from . import action, pending
from .reminders import add_reminder
from .util import FMT, parse_date, parse_dt, parse_time, spoken_when


def _upcoming(now, limit=5):
    return db.q(
        "SELECT * FROM appointments WHERE date || ' ' || time >= ? ORDER BY date, time LIMIT ?",
        (now.strftime(FMT), limit),
    )


def _when(appt, now):
    return spoken_when(parse_dt(f"{appt['date']} {appt['time']}"), now)


@action(
    "create_appointment",
    "Create an appointment. Needs doctor, date and time. If any is missing, do NOT call this: "
    "ask the person one simple question first. Location and notes are optional.",
    {
        "doctor": {"type": "string"},
        "date": {"type": "string", "description": "YYYY-MM-DD"},
        "time": {"type": "string", "description": "HH:MM (24-hour)"},
        "location": {"type": "string"},
        "notes": {"type": "string"},
    },
    ["doctor", "date", "time"],
)
def create_appointment(a, ctx):
    d, t = parse_date(a.get("date")), parse_time(a.get("time"))
    if not d:
        return {"speak": "Which day is the appointment?"}
    if not t:
        return {"speak": "What time is the appointment?"}
    when = datetime.combine(d, t)
    if when < ctx.now:
        return {"speak": "That time has already passed. Which day would you like?"}
    doctor = (a.get("doctor") or "the doctor").strip()
    loc, notes = (a.get("location") or "").strip(), (a.get("notes") or "").strip()
    aid, _ = db.run(
        "INSERT INTO appointments(doctor, date, time, location, notes) VALUES (?,?,?,?,?)",
        (doctor, d.isoformat(), t.strftime("%H:%M"), loc, notes),
    )
    heads_up = when - timedelta(hours=1)
    reminded = heads_up > ctx.now
    if reminded:
        add_reminder(f"Appointment with {doctor} in one hour", "appointment", heads_up, appt_id=aid)
    text = f"Done. Your appointment with {doctor} is {spoken_when(when, ctx.now)}."
    if loc:
        text += f" It is at {loc}."
    if reminded:
        text += " I will remind you one hour before."
    return {"speak": text}


@action("next_appointment", "Tell the person their next appointment ('When is my next appointment?').")
def next_appointment(a, ctx):
    rows = _upcoming(ctx.now, 1)
    if not rows:
        return {"speak": "You have no appointments coming up."}
    r = rows[0]
    text = f"Your next appointment is with {r['doctor']}, {_when(r, ctx.now)}."
    if r["location"]:
        text += f" It is at {r['location']}."
    if r["notes"]:
        text += f" Note: {r['notes']}."
    return {"speak": text}


@action("list_appointments", "Tell the person all their upcoming appointments.")
def list_appointments(a, ctx):
    rows = _upcoming(ctx.now)
    if not rows:
        return {"speak": "You have no appointments coming up."}
    parts = [f"{r['doctor']}, {_when(r, ctx.now)}" for r in rows]
    n = len(rows)
    head = "You have one appointment. " if n == 1 else f"You have {n} appointments. "
    return {"speak": head + ". ".join(parts) + "."}


@action(
    "cancel_appointment",
    "Cancel an appointment by doctor name (and date if there are several).",
    {"doctor": {"type": "string"}, "date": {"type": "string", "description": "YYYY-MM-DD, optional"}},
    ["doctor"],
    sensitive=True,
)
def cancel_appointment(a, ctx):
    if ctx.confirmed:
        aid = a.get("appointment_id")
        db.run("DELETE FROM reminders WHERE appt_id=?", (aid,))
        _, n = db.run("DELETE FROM appointments WHERE id=?", (aid,))
        return {"speak": "Okay, the appointment is cancelled." if n else "That appointment is already gone."}
    word = (a.get("doctor") or "").lower().replace("dr.", "").replace("dr", "").strip()
    hits = [r for r in _upcoming(ctx.now, 50) if word and word in r["doctor"].lower()]
    if a.get("date"):
        hits = [r for r in hits if r["date"] == a["date"]] or hits
    if not hits:
        return {"speak": "I could not find that appointment."}
    if len(hits) > 1:
        options = ". ".join(_when(r, ctx.now) for r in hits[:3])
        return {"speak": f"You have more than one. {options}. Which day should I cancel?"}
    r = hits[0]
    return pending(
        "cancel_appointment",
        {"appointment_id": r["id"]},
        f"Do you want me to cancel your appointment with {r['doctor']}, {_when(r, ctx.now)}?",
    )
