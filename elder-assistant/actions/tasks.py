"""Basic digital tasks: SMS, share location, alarm, read aloud, notes, date/time, emergency."""
import db
from . import action, pending
from .reminders import add_reminder
from .util import describe_contact, get_contact, parse_dt, resolve_contact, spoken_time, spoken_when


@action(
    "send_sms",
    "Send a text message to a saved contact, like 'send my son a message saying I reached home'.",
    {
        "contact": {"type": "string", "description": "relation or name"},
        "message": {"type": "string", "description": "the message text, in the first person"},
    },
    ["contact", "message"],
    sensitive=True,
)
def send_sms(a, ctx):
    msg = (a.get("message") or "").strip()
    if ctx.confirmed:
        c = get_contact(a.get("contact_id"))
        if not c:
            return {"speak": "Sorry, I could not find that contact."}
        return {
            "speak": f"I opened your message to {c['name']}. Please press send.",
            "client_actions": [{"type": "sms", "number": c["phone"], "body": msg}],
        }
    if not msg:
        return {"speak": "What should the message say?"}
    c, err = resolve_contact(a.get("contact"))
    if err:
        return err
    return pending(
        "send_sms",
        {"contact_id": c["id"], "message": msg},
        f"I will send this message to {describe_contact(c)}: {msg}. Shall I send it?",
    )


@action(
    "share_location",
    "Share the person's current location with a saved contact by text message.",
    {"contact": {"type": "string", "description": "relation or name"}},
    ["contact"],
    sensitive=True,
)
def share_location(a, ctx):
    if ctx.confirmed:
        c = get_contact(a.get("contact_id"))
        if not c:
            return {"speak": "Sorry, I could not find that contact."}
        return {
            "speak": f"Finding your location to send to {c['name']}.",
            "client_actions": [{"type": "share_location", "number": c["phone"]}],
        }
    c, err = resolve_contact(a.get("contact"))
    if err:
        return err
    return pending("share_location", {"contact_id": c["id"]}, f"Do you want me to share your location with {describe_contact(c)}?")


@action(
    "set_alarm",
    "Set an alarm, like 'set an alarm for 6 AM'.",
    {
        "datetime": {"type": "string", "description": "Local time 'YYYY-MM-DD HH:MM' (24-hour); next occurrence"},
        "label": {"type": "string"},
    },
    ["datetime"],
)
def set_alarm(a, ctx):
    due = parse_dt(a.get("datetime"))
    if not due:
        return {"speak": "What time should I set the alarm for?"}
    if due <= ctx.now:
        return {"speak": "That time has already passed. What other time should I use?"}
    add_reminder((a.get("label") or "Alarm").strip(), "alarm", due)
    return {"speak": f"Okay, your alarm is set for {spoken_when(due, ctx.now)}."}


@action(
    "read_text_aloud",
    "Read text aloud. If the person gives the text, pass it in 'text'. If they say 'read this' "
    "without giving text, leave 'text' empty and the app will open a box to paste it.",
    {"text": {"type": "string"}},
)
def read_text_aloud(a, ctx):
    text = (a.get("text") or "").strip()
    if text:
        return {"speak": text}
    return {"speak": "Okay. Please paste the words in the box, and I will read them.", "client_actions": [{"type": "read_box"}]}


@action("create_note", "Save a simple note.", {"text": {"type": "string"}}, ["text"])
def create_note(a, ctx):
    text = (a.get("text") or "").strip()
    if not text:
        return {"speak": "What should I write in the note?"}
    db.run("INSERT INTO notes(text, created_at) VALUES (?,?)", (text, ctx.now.strftime("%Y-%m-%d %H:%M")))
    return {"speak": "Okay, I saved your note."}


@action("list_notes", "Read the person's saved notes.")
def list_notes(a, ctx):
    rows = db.q("SELECT text FROM notes ORDER BY id DESC LIMIT 5")
    if not rows:
        return {"speak": "You have no notes."}
    return {"speak": "Your notes are: " + ". ".join(r["text"] for r in rows) + "."}


@action("get_datetime", "Tell the person the current date and time.")
def get_datetime(a, ctx):
    n = ctx.now
    return {"speak": f"It is {spoken_time(n)}, {n.strftime('%A')}, {n.day} {n.strftime('%B %Y')}."}


@action(
    "emergency_help",
    "Start emergency help. Use when the person says they need help, are hurt, fell, feel very ill or scared.",
)
def emergency_help(a, ctx):
    return {
        "speak": "I am getting help now. Press the big Cancel button if this was a mistake.",
        "client_actions": [{"type": "emergency"}],
    }
