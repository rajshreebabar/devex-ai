"""Reminders: medicine, appointments, calls, alarms and general reminders."""
from datetime import timedelta

import db
from . import action
from .util import FMT, parse_dt, spoken_when

KINDS = ["medicine", "appointment", "call", "general", "alarm"]


def due_reminders(now):
    return db.q(
        "SELECT * FROM reminders WHERE done=0 AND due_at<=? ORDER BY due_at",
        (now.strftime(FMT),),
    )


def ack_reminder(rid, now):
    """Called when the person taps OK on a ringing reminder."""
    rows = db.q("SELECT * FROM reminders WHERE id=?", (rid,))
    if not rows:
        return
    r = rows[0]
    if r["repeat"] == "daily":
        due = parse_dt(r["due_at"])
        while due <= now:
            due += timedelta(days=1)
        db.run("UPDATE reminders SET due_at=? WHERE id=?", (due.strftime(FMT), rid))
    else:
        db.run("UPDATE reminders SET done=1 WHERE id=?", (rid,))


def add_reminder(title, kind, due, repeat="none", appt_id=None):
    rid, _ = db.run(
        "INSERT INTO reminders(title, kind, due_at, repeat, appt_id) VALUES (?,?,?,?,?)",
        (title, kind, due.strftime(FMT), repeat, appt_id),
    )
    return rid


@action(
    "create_reminder",
    "Create a reminder (medicine, appointment, call a family member, or general). "
    "Title is short and addressed to the person, like 'Take your medicine'.",
    {
        "title": {"type": "string"},
        "kind": {"type": "string", "enum": KINDS[:4]},
        "datetime": {"type": "string", "description": "Local time 'YYYY-MM-DD HH:MM' (24-hour)"},
        "repeat": {"type": "string", "enum": ["none", "daily"], "description": "daily if they say every day"},
    },
    ["title", "datetime"],
)
def create_reminder(a, ctx):
    due = parse_dt(a.get("datetime"))
    if not due:
        return {"speak": "What time should I remind you?"}
    if due < ctx.now:
        return {"speak": "That time has already passed. What other time should I use?"}
    kind = a.get("kind") if a.get("kind") in KINDS else "general"
    repeat = "daily" if a.get("repeat") == "daily" else "none"
    add_reminder(a.get("title") or "Reminder", kind, due, repeat)
    when = spoken_when(due, ctx.now)
    extra = " I will remind you every day." if repeat == "daily" else ""
    label = "medicine reminder" if kind == "medicine" else "reminder"
    return {"speak": f"Okay, I have set your {label} for {when}.{extra}"}


@action("list_reminders", "Tell the person their upcoming reminders.")
def list_reminders(a, ctx):
    rows = db.q("SELECT * FROM reminders WHERE done=0 ORDER BY due_at LIMIT 5")
    if not rows:
        return {"speak": "You have no reminders."}
    parts = [f"{r['title']}, {spoken_when(parse_dt(r['due_at']), ctx.now)}" for r in rows]
    n = len(rows)
    head = "You have one reminder. " if n == 1 else f"You have {n} reminders. "
    return {"speak": head + ". ".join(parts) + "."}


@action(
    "delete_reminder",
    "Delete a reminder. 'query' is a word from its title, like 'medicine'.",
    {"query": {"type": "string"}},
    ["query"],
)
def delete_reminder(a, ctx):
    words = [w for w in (a.get("query") or "").lower().split() if len(w) > 2]
    rows = db.q("SELECT * FROM reminders WHERE done=0")
    hits = [r for r in rows if any(w in r["title"].lower() or w == r["kind"] for w in words)]
    if not hits:
        return {"speak": "I could not find that reminder."}
    if len(hits) > 1:
        names = ". ".join(f"{r['title']} at {parse_dt(r['due_at']).strftime('%I:%M %p').lstrip('0')}" for r in hits[:3])
        return {"speak": f"I found more than one. {names}. Which one should I delete?"}
    db.run("DELETE FROM reminders WHERE id=?", (hits[0]["id"],))
    return {"speak": f"Okay, I deleted the reminder: {hits[0]['title']}."}
