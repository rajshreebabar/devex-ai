"""Voice-first assistant for elderly people. Run:  python app.py"""
import logging
import os

from dotenv import load_dotenv

load_dotenv()

from flask import Flask, jsonify, render_template, request  # noqa: E402

import ai  # noqa: E402
import db  # noqa: E402
from actions import Ctx, is_sensitive, run_action  # noqa: E402
from actions.reminders import ack_reminder, due_reminders  # noqa: E402
from actions.util import FMT, parse_now  # noqa: E402

logging.basicConfig(level=logging.INFO)
app = Flask(__name__)
db.init_db()

EMERGENCY_NUMBER = os.environ.get("EMERGENCY_NUMBER", "112")


@app.get("/")
def index():
    return render_template("index.html", lang=os.environ.get("SPEECH_LANG", "en-IN"))


# ---- The AI pipeline: text -> AI -> action -> reply ---------------------------------
@app.post("/api/command")
def command():
    d = request.get_json(force=True, silent=True) or {}
    text = (d.get("text") or "").strip()
    if not text:
        return jsonify(ai._result("I did not catch that. Please try again."))
    return jsonify(ai.handle_command(text, d.get("history"), parse_now(d.get("now"))))


@app.post("/api/confirm")
def confirm():
    """Runs a sensitive action after the person said yes."""
    d = request.get_json(force=True, silent=True) or {}
    name = d.get("action")
    if not is_sensitive(name):
        return jsonify(error="not allowed"), 400
    r = run_action(name, d.get("args") or {}, Ctx(parse_now(d.get("now")), confirmed=True))
    return jsonify(reply=r.get("speak", "Done."), client_actions=r.get("client_actions", []))


# ---- Data for the simple screens ------------------------------------------------------
@app.get("/api/state")
def state():
    now = parse_now(request.args.get("now"))
    return jsonify(
        reminders=db.q("SELECT * FROM reminders WHERE done=0 ORDER BY due_at"),
        contacts=db.q("SELECT * FROM contacts ORDER BY is_emergency DESC, name"),
        appointments=db.q(
            "SELECT * FROM appointments WHERE date || ' ' || time >= ? ORDER BY date, time",
            (now.strftime(FMT),),
        ),
    )


@app.get("/api/emergency")
def emergency():
    contacts = db.q("SELECT name, phone FROM contacts WHERE is_emergency=1 ORDER BY id")
    return jsonify(contacts=contacts, number=EMERGENCY_NUMBER)


@app.get("/api/reminders/due")
def due():
    return jsonify(due=due_reminders(parse_now(request.args.get("now"))))


@app.post("/api/reminders/<int:rid>/ack")
def ack(rid):
    d = request.get_json(force=True, silent=True) or {}
    ack_reminder(rid, parse_now(d.get("now")))
    return jsonify(ok=True)


@app.delete("/api/reminders/<int:rid>")
def delete_reminder(rid):
    db.run("DELETE FROM reminders WHERE id=?", (rid,))
    return jsonify(ok=True)


@app.delete("/api/appointments/<int:aid>")
def delete_appointment(aid):
    db.run("DELETE FROM reminders WHERE appt_id=?", (aid,))
    db.run("DELETE FROM appointments WHERE id=?", (aid,))
    return jsonify(ok=True)


@app.post("/api/contacts")
def add_contact():
    d = request.get_json(force=True, silent=True) or {}
    name, phone = (d.get("name") or "").strip(), (d.get("phone") or "").strip()
    if not name or not phone:
        return jsonify(error="Name and phone are needed"), 400
    db.run(
        "INSERT INTO contacts(name, relation, phone, is_emergency) VALUES (?,?,?,?)",
        (name, (d.get("relation") or "").lower().strip(), phone, 1 if d.get("is_emergency") else 0),
    )
    return jsonify(ok=True)


@app.post("/api/contacts/<int:cid>/emergency")
def toggle_emergency(cid):
    db.run("UPDATE contacts SET is_emergency = 1 - is_emergency WHERE id=?", (cid,))
    return jsonify(ok=True)


@app.delete("/api/contacts/<int:cid>")
def delete_contact(cid):
    db.run("DELETE FROM contacts WHERE id=?", (cid,))
    return jsonify(ok=True)


if __name__ == "__main__":
    ssl = "adhoc" if os.environ.get("HTTPS") == "1" else None  # needs: pip install cryptography
    app.run(
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", 5000)),
        debug=os.environ.get("FLASK_DEBUG") == "1",
        ssl_context=ssl,
    )
