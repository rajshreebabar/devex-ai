"""
AI layer: speech text in -> the model picks an action (tool) -> we run it -> simple reply out.

The API key is read from the ANTHROPIC_API_KEY environment variable by the SDK.
It is never sent to the browser.
"""
import logging
import os

import db
from actions import Ctx, run_action, tool_specs

log = logging.getLogger("assistant")

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
MAX_STEPS = 4
_client = None

SYSTEM = """You are "Helper", a kind and patient voice assistant for an elderly person. Everything you write is spoken aloud.

How to talk:
- Very simple words. At most two short sentences. No lists, no markdown, no emojis.
- Understand normal speech, even with mistakes. Never ask the person to use special commands.

How to act:
- When the person wants something done, use the matching tool. Never say something is done unless you used the tool.
- If needed information is missing (for example the time of an appointment), ask ONE simple question and wait for the answer.
- Work out words like tonight, tomorrow, in 2 hours, next Monday from the current date and time below. Tool times are 24-hour. "Tonight at 9" is 21:00. If a time today has already passed, use tomorrow.
- If they say every day, use repeat=daily. Reminder titles are short and addressed to the person, like "Take your medicine".
- Calls, text messages, sharing location and deleting are confirmed by the app itself, so just use the tool.
- If the person says they need help, fell, are hurt, very ill or scared, use emergency_help straight away.
- For everyday questions, answer briefly and kindly. For health questions give only general advice and suggest asking their doctor. Never diagnose.
- If you do not understand, ask one short question.

Current date and time: {now} ({weekday}).
Saved people: {people}."""


def _get_client():
    global _client
    if _client is None:
        from anthropic import Anthropic

        _client = Anthropic()  # reads ANTHROPIC_API_KEY from the environment
    return _client


def _clean_history(history):
    """Keep the last few turns, start with a user turn, merge repeated roles."""
    out = []
    for m in (history or [])[-10:]:
        role, text = m.get("role"), str(m.get("content") or "").strip()
        if role not in ("user", "assistant") or not text:
            continue
        if out and out[-1]["role"] == role:
            out[-1]["content"] += " " + text
        else:
            out.append({"role": role, "content": text})
    while out and out[0]["role"] != "user":
        out.pop(0)
    while out and out[-1]["role"] != "assistant":
        out.pop()  # the new user message will follow
    return out


def _system(now):
    people = "; ".join(
        f"{c['name']} ({c['relation'] or 'contact'})" for c in db.q("SELECT name, relation FROM contacts LIMIT 20")
    ) or "nobody yet"
    return SYSTEM.format(now=now.strftime("%Y-%m-%d %H:%M"), weekday=now.strftime("%A"), people=people)


def _result(reply, actions=None, pending=None):
    reply = (reply or "").strip() or "Sorry, I did not understand. Could you say that again?"
    return {
        "reply": reply,
        "client_actions": actions or [],
        "pending": pending,
        "expect_reply": pending is None and reply.endswith("?"),
    }


def handle_command(text, history, now):
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return _result("I am not set up yet. Please ask your family to add the access key.")

    messages = _clean_history(history) + [{"role": "user", "content": text}]
    system, tools = _system(now), tool_specs()

    try:
        for _ in range(MAX_STEPS):
            resp = _get_client().messages.create(
                model=MODEL, max_tokens=500, system=system, tools=tools, messages=messages
            )
            if resp.stop_reason != "tool_use":
                return _result("".join(b.text for b in resp.content if b.type == "text"))

            messages.append({"role": "assistant", "content": resp.content})
            tool_results, speaks, actions, pending = [], [], [], None
            all_spoken = True
            for block in resp.content:
                if block.type != "tool_use":
                    continue
                r = run_action(block.name, block.input, Ctx(now))
                if r.get("speak"):
                    speaks.append(r["speak"])
                else:
                    all_spoken = False
                actions += r.get("client_actions", [])
                pending = pending or r.get("pending")
                tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": str(r)})

            if all_spoken:  # every action already produced a spoken answer: skip a second model call
                return _result(" ".join(speaks), actions, pending)
            messages.append({"role": "user", "content": tool_results})
    except Exception:
        log.exception("AI request failed")
        return _result("Sorry, I am having trouble right now. Please try again in a moment.")

    return _result("Sorry, I could not finish that. Please try again.")
