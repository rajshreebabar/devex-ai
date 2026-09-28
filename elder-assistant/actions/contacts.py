"""Important contacts: family, doctor, caregiver, emergency contacts."""
import re

import db
from . import action, pending
from .util import describe_contact, get_contact, match_contacts, resolve_contact, spoken_number


@action(
    "save_contact",
    "Save a person: family member, doctor, caregiver, friend. Needs a name and phone number.",
    {
        "name": {"type": "string"},
        "relation": {"type": "string", "description": "daughter, son, wife, doctor, caregiver, neighbour..."},
        "phone": {"type": "string"},
        "is_emergency": {"type": "boolean", "description": "true if this is an emergency contact"},
    },
    ["name", "phone"],
)
def save_contact(a, ctx):
    phone = re.sub(r"[^\d+]", "", a.get("phone") or "")
    if len(re.sub(r"\D", "", phone)) < 5:
        return {"speak": "That phone number looks too short. Could you say it again?"}
    name = (a.get("name") or "").strip()
    if not name:
        return {"speak": "What is the person's name?"}
    rel = (a.get("relation") or "").lower().strip()
    emer = 1 if a.get("is_emergency") else 0
    same = db.q("SELECT id FROM contacts WHERE lower(name)=lower(?)", (name,))
    if same:
        db.run("UPDATE contacts SET phone=?, relation=?, is_emergency=? WHERE id=?", (phone, rel, emer, same[0]["id"]))
    else:
        db.run("INSERT INTO contacts(name, relation, phone, is_emergency) VALUES (?,?,?,?)", (name, rel, phone, emer))
    who = f"{name}, your {rel}" if rel else name
    tail = " as an emergency contact" if emer else ""
    return {"speak": f"Okay, I saved {who}{tail}."}


@action(
    "find_contact",
    "Answer 'Who is my doctor?' or 'What is my daughter's number?'. Does not call anyone.",
    {"query": {"type": "string", "description": "relation or name, like 'doctor' or 'Priya'"}},
    ["query"],
)
def find_contact(a, ctx):
    found = match_contacts(a.get("query"))
    if not found:
        return {"speak": f"I do not have {a.get('query')} saved yet. Would you like to add them?"}
    lines = [f"Your {c['relation'] or 'contact'} is {c['name']}. The number is {spoken_number(c['phone'])}." for c in found[:2]]
    return {"speak": " ".join(lines)}


@action("list_contacts", "Tell the person which people are saved.")
def list_contacts(a, ctx):
    rows = db.q("SELECT * FROM contacts ORDER BY name LIMIT 6")
    if not rows:
        return {"speak": "You have no contacts saved yet."}
    return {"speak": "You have saved: " + "; ".join(describe_contact(c) for c in rows) + "."}


@action(
    "call_contact",
    "Call a saved contact, like 'call my daughter'.",
    {"contact": {"type": "string", "description": "relation or name"}},
    ["contact"],
    sensitive=True,
)
def call_contact(a, ctx):
    if ctx.confirmed:
        c = get_contact(a.get("contact_id"))
        if not c:
            return {"speak": "Sorry, I could not find that contact."}
        return {"speak": f"Calling {c['name']} now.", "client_actions": [{"type": "call", "number": c["phone"]}]}
    c, err = resolve_contact(a.get("contact"))
    if err:
        return err
    return pending("call_contact", {"contact_id": c["id"]}, f"Do you want me to call {describe_contact(c)}?")


@action(
    "delete_contact",
    "Remove a saved contact.",
    {"contact": {"type": "string"}},
    ["contact"],
    sensitive=True,
)
def delete_contact(a, ctx):
    if ctx.confirmed:
        c = get_contact(a.get("contact_id"))
        if c:
            db.run("DELETE FROM contacts WHERE id=?", (c["id"],))
            return {"speak": f"Okay, I removed {c['name']}."}
        return {"speak": "That contact is already gone."}
    c, err = resolve_contact(a.get("contact"))
    if err:
        return err
    return pending("delete_contact", {"contact_id": c["id"]}, f"Do you want me to remove {describe_contact(c)}?")


@action(
    "set_emergency_contact",
    "Mark or unmark a saved person as an emergency contact.",
    {"contact": {"type": "string"}, "is_emergency": {"type": "boolean"}},
    ["contact"],
)
def set_emergency_contact(a, ctx):
    c, err = resolve_contact(a.get("contact"))
    if err:
        return err
    on = 0 if a.get("is_emergency") is False else 1
    db.run("UPDATE contacts SET is_emergency=? WHERE id=?", (on, c["id"]))
    return {"speak": f"Okay, {c['name']} is {'now' if on else 'no longer'} an emergency contact."}
