"""
Action registry.

Every ability of the assistant is a small function registered with @action.
The AI sees the registered actions as tools and picks the right one.
To add a new ability: create a new file in this folder, decorate a function
with @action(...). Nothing else needs to change.

An action receives (args, ctx) and returns a dict:
    speak           text the assistant says out loud (required)
    client_actions  list of things the browser must do (call, sms, ...)
    pending         set for sensitive actions that need a "yes" first
"""
import importlib
import logging
import pkgutil

log = logging.getLogger("assistant")

REGISTRY = {}


class Ctx:
    """Per-request context: the person's local time and whether they confirmed."""

    def __init__(self, now, confirmed=False):
        self.now = now
        self.confirmed = confirmed


def action(name, description, properties=None, required=None, sensitive=False):
    def decorator(fn):
        REGISTRY[name] = {
            "fn": fn,
            "sensitive": sensitive,
            "spec": {
                "name": name,
                "description": description,
                "input_schema": {
                    "type": "object",
                    "properties": properties or {},
                    "required": required or [],
                },
            },
        }
        return fn

    return decorator


def tool_specs():
    return [a["spec"] for a in REGISTRY.values()]


def run_action(name, args, ctx):
    entry = REGISTRY.get(name)
    if not entry:
        return {"speak": "Sorry, I cannot do that yet."}
    try:
        return entry["fn"](args or {}, ctx) or {}
    except Exception:  # never crash the conversation
        log.exception("Action %s failed", name)
        return {"speak": "Sorry, something went wrong. Please try again."}


def is_sensitive(name):
    return bool(REGISTRY.get(name, {}).get("sensitive"))


def pending(name, args, prompt):
    """Return value for a sensitive action that is waiting for confirmation."""
    return {"speak": prompt, "pending": {"action": name, "args": args}}


def _load_all():
    for mod in pkgutil.iter_modules(__path__):
        importlib.import_module(f"{__name__}.{mod.name}")


_load_all()
