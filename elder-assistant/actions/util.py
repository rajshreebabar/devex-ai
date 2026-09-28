"""Helpers shared by actions: time parsing/speaking and contact lookup."""
import re
from datetime import datetime

import db

FMT = "%Y-%m-%d %H:%M"


def parse_now(s):
    dt = parse_dt(s)
    return dt or datetime.now().replace(second=0, microsecond=0)


def parse_dt(s):
    s = (s or "").strip().replace("T", " ")
    for f in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s, f)
        except ValueError:
            pass
    return None


def parse_date(s):
    try:
        return datetime.strptime((s or "").strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def parse_time(s):
    try:
        return datetime.strptime((s or "").strip(), "%H:%M").time()
    except ValueError:
        return None


def spoken_time(dt):
    h = dt.strftime("%I").lstrip("0") or "12"
    m, ap = dt.strftime("%M"), dt.strftime("%p")
    return f"{h} {ap}" if m == "00" else f"{h}:{m} {ap}"


def spoken_date(d, today):
    diff = (d - today).days
    if diff == 0:
        return "today"
    if diff == 1:
        return "tomorrow"
    if 1 < diff < 7:
        return d.strftime("%A")
    return f"{d.strftime('%A')}, {d.day} {d.strftime('%B')}"


def spoken_when(dt, now):
    return f"{spoken_date(dt.date(), now.date())} at {spoken_time(dt)}"


def spoken_number(phone):
    return " ".join(re.sub(r"[^\d+]", "", phone))


def describe_contact(c):
    return f"{c['name']}, your {c['relation']}" if c["relation"] else c["name"]


def match_contacts(query):
    """Find saved contacts by name or relation ('my daughter', 'doctor', 'Priya')."""
    q = re.sub(r"\bmy\b", "", (query or "").lower()).replace("dr.", "dr").strip()
    toks = set(re.findall(r"\w+", q))
    best, out = 0, []
    for c in db.q("SELECT * FROM contacts"):
        name = c["name"].lower().replace("dr.", "dr")
        rel = c["relation"].lower()
        if q and q in (name, rel):
            s = 3
        elif toks & set(re.findall(r"\w+", rel)):
            s = 2
        elif toks & (set(re.findall(r"\w+", name)) - {"dr"}):
            s = 1
        else:
            continue
        if s > best:
            best, out = s, [c]
        elif s == best:
            out.append(c)
    return out


def resolve_contact(query):
    """Return (contact, None) or (None, speak_dict) if missing/ambiguous."""
    found = match_contacts(query)
    if not found:
        return None, {"speak": f"I could not find {query} in your contacts."}
    if len(found) > 1:
        names = " or ".join(c["name"] for c in found[:3])
        return None, {"speak": f"Which one do you mean, {names}?"}
    return found[0], None


def get_contact(contact_id):
    rows = db.q("SELECT * FROM contacts WHERE id=?", (contact_id,))
    return rows[0] if rows else None
