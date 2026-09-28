# Helper — voice-first assistant for elderly people

Speak → speech-to-text → AI picks an action → action runs → spoken reply.

## Run it
```bash
cd elder-assistant
python -m venv venv && source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                  # then put your ANTHROPIC_API_KEY in .env
python app.py                                         # open http://localhost:5000 in Chrome, Edge or Safari
```
The key stays on the server (environment variable). The browser never sees it.

**Using it on a phone:** microphone, location and speech need HTTPS. Either deploy behind HTTPS, use a tunnel
(e.g. `cloudflared tunnel --url http://localhost:5000`), or run `pip install cryptography` and start with `HTTPS=1 HOST=0.0.0.0 python app.py`.

## How it works
| Piece | File | Job |
|---|---|---|
| Voice in/out, screens, ringing reminders | `static/app.js` | Browser speech-to-text and text-to-speech, big-button UI |
| AI understanding | `ai.py` | Sends the sentence to the model with the list of actions as tools; the model picks one |
| Actions | `actions/*.py` | One small function per ability, registered with `@action` |
| Storage | `db.py` | SQLite: contacts, reminders, appointments, notes |
| Routes | `app.py` | `/api/command`, `/api/confirm`, and data for the screens |

Calls, texts, sharing location and deleting are **sensitive**: the assistant asks "Do you want me to…?" and waits for a spoken or tapped Yes.

## Add a new ability (no other file changes)
```python
# actions/weather.py
from . import action

@action("get_weather", "Tell the person today's weather.", {"city": {"type": "string"}})
def get_weather(a, ctx):
    return {"speak": "It is sunny today."}      # optional: "client_actions": [...]
```
Restart — the AI can now use it.

## Honest limits of a web prototype
- **SMS / calls:** browsers cannot send a text or place a call silently. The assistant opens the message (already written) or the dialer; the person taps Send / Call. Silent SMS needs a provider such as Twilio, added inside `actions/tasks.py`.
- **Reminders and alarms ring only while the page is open** (keep it open on the phone). Background alerts need a native app or push notifications.
- **Emergency:** the button counts down 5 seconds (Cancel available), opens a text with the location to emergency contacts, and shows big call buttons. It cannot contact emergency services automatically.
- Speech recognition uses the browser's engine (Chrome/Edge/Safari); set `SPEECH_LANG` (e.g. `hi-IN`) to change language.
- Add family and doctor with the **People** screen (or by voice). Mark emergency contacts there.
