/* Helper — voice-first client.
   Flow: listen (speech-to-text) -> /api/command (AI picks + runs action) -> speak reply -> run phone actions. */
(() => {
  const LANG = document.querySelector('meta[name="speech-lang"]').content || "en-IN";
  const $ = (s) => document.querySelector(s);
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  const YES = /\b(yes|yeah|yep|yup|ok|okay|sure|go ahead|please do|correct|haan|ha)\b/i;
  const NO = /\b(no|nope|cancel|stop|don't|do not|nahi|nahin)\b/i;

  const S = { history: [], busy: false, rec: null, confirmOpen: false, pending: null, alertOpen: false };
  let audioCtx = null, alertTimer = null, emTimer = null;

  /* ---------- helpers ---------- */
  const p2 = (n) => String(n).padStart(2, "0");
  const localNow = () => {
    const d = new Date();
    return `${d.getFullYear()}-${p2(d.getMonth() + 1)}-${p2(d.getDate())} ${p2(d.getHours())}:${p2(d.getMinutes())}`;
  };
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  async function api(path, body, method) {
    const opt = { method: method || (body ? "POST" : "GET"), headers: { "Content-Type": "application/json" } };
    if (body) opt.body = JSON.stringify(body);
    const r = await fetch(path, opt);
    if (!r.ok) throw new Error(r.status);
    return r.json();
  }
  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  /* ---------- speech out ---------- */
  function pickVoice() {
    const v = speechSynthesis.getVoices();
    return v.find((x) => x.lang === LANG) || v.find((x) => x.lang.startsWith("en")) || null;
  }
  function say(text) {
    return new Promise((resolve) => {
      if (!("speechSynthesis" in window) || !text) return resolve();
      speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(text);
      u.lang = LANG; u.rate = 0.9;
      const v = pickVoice();
      if (v) u.voice = v;
      u.onend = u.onerror = () => resolve();
      speechSynthesis.speak(u);
    });
  }

  /* ---------- speech in ---------- */
  function listen() {
    return new Promise((resolve) => {
      const r = new SR();
      S.rec = r;
      r.lang = LANG; r.interimResults = true; r.maxAlternatives = 1;
      let finalText = "";
      r.onresult = (e) => {
        let interim = "";
        for (let i = e.resultIndex; i < e.results.length; i++) {
          const t = e.results[i][0].transcript;
          if (e.results[i].isFinal) finalText += t; else interim += t;
        }
        $("#heard").textContent = "You said: " + (finalText || interim);
      };
      r.onerror = (e) => resolve({ error: e.error });
      r.onend = () => resolve({ text: finalText.trim() });
      try { r.start(); } catch (_) { resolve({ error: "start-failed" }); }
    });
  }

  function setMode(mode) {
    const mic = $("#mic");
    mic.classList.remove("listening", "thinking", "speaking");
    if (mode !== "idle") mic.classList.add(mode);
    $("#mic-label").textContent = {
      idle: "Tap and Speak", listening: "I am listening…", thinking: "One moment…", speaking: "Speaking…",
    }[mode];
  }

  function unlockAudio() {
    try {
      if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      if (audioCtx.state === "suspended") audioCtx.resume();
    } catch (_) {}
  }
  function beep() {
    if (!audioCtx) return;
    const o = audioCtx.createOscillator(), g = audioCtx.createGain();
    o.frequency.value = 880; g.gain.value = 0.25;
    o.connect(g); g.connect(audioCtx.destination);
    o.start(); o.stop(audioCtx.currentTime + 0.3);
  }

  /* ---------- main conversation loop ---------- */
  async function talk() {
    if (S.busy) return;
    S.busy = true;
    unlockAudio();
    try {
      if (!SR) { $("#typed").hidden = false; return; }
      setMode("listening");
      let r = await listen();
      while (true) {
        if (r.error && r.error !== "aborted") { await say(errorText(r.error)); break; }
        if (!r.text) { await say("I did not hear you. Please tap and speak again."); break; }
        const res = await turn(r.text);
        if (res && res.expect_reply && !res.pending) {  // the AI asked a question: listen again
          setMode("listening");
          r = await listen();
        } else break;
      }
    } finally {
      S.busy = false;
      setMode("idle");
    }
  }
  function errorText(code) {
    if (code === "not-allowed" || code === "service-not-allowed") return "Please allow the microphone, so I can hear you.";
    if (code === "network") return "I cannot hear you right now. Please check the internet.";
    return "I did not hear you. Please tap and speak again.";
  }

  async function turn(text) {
    setMode("thinking");
    $("#heard").textContent = "You said: " + text;
    let res;
    try {
      res = await api("/api/command", { text, history: S.history, now: localNow() });
    } catch (_) {
      res = { reply: "Sorry, I cannot reach the assistant right now.", client_actions: [], pending: null };
    }
    S.history.push({ role: "user", content: text }, { role: "assistant", content: res.reply });
    S.history = S.history.slice(-10);
    loadState();
    await deliver(res);
    return res;
  }

  async function deliver(res) {
    $("#reply").textContent = res.reply;
    if (res.pending) return askConfirm(res.reply, res.pending);
    if ((res.client_actions || []).some((a) => a.type === "emergency")) return startEmergency();
    setMode("speaking");
    await say(res.reply);
    await runActions(res.client_actions);
  }

  /* ---------- confirmation for sensitive actions ---------- */
  async function askConfirm(question, pending) {
    S.pending = pending; S.confirmOpen = true;
    $("#confirm-text").textContent = question;
    $("#confirm").hidden = false;
    setMode("speaking");
    await say(question);
    if (!S.confirmOpen) return;
    setMode("listening");
    const r = await listen();
    if (!S.confirmOpen) return;
    const t = r.text || "";
    if (YES.test(t) && !NO.test(t)) answer(true);
    else if (NO.test(t)) answer(false);
    // unclear: the big Yes / No buttons stay on screen
  }
  async function answer(yes) {
    if (!S.confirmOpen) return;
    S.confirmOpen = false;
    $("#confirm").hidden = true;
    try { S.rec && S.rec.abort(); } catch (_) {}
    speechSynthesis.cancel();
    const p = S.pending; S.pending = null;
    if (!yes) {
      const msg = "Okay, I will not do that.";
      $("#reply").textContent = msg;
      addAssistant(msg);
      await say(msg);
      return;
    }
    let res;
    try {
      res = await api("/api/confirm", { action: p.action, args: p.args, now: localNow() });
    } catch (_) {
      res = { reply: "Sorry, that did not work.", client_actions: [] };
    }
    addAssistant(res.reply);
    loadState();
    await deliver(res);
  }
  function addAssistant(text) {
    const last = S.history[S.history.length - 1];
    if (last && last.role === "assistant") last.content += " " + text;
    else S.history.push({ role: "assistant", content: text });
  }

  /* ---------- phone actions ---------- */
  async function runActions(list) {
    for (const a of list || []) {
      if (a.type === "call") location.href = "tel:" + a.number;
      else if (a.type === "sms") openSms(a.number, a.body);
      else if (a.type === "share_location") await shareLocation(a.number);
      else if (a.type === "read_box") openReadBox();
    }
  }
  function openSms(number, body) {
    const sep = /iPhone|iPad|iPod/i.test(navigator.userAgent) ? "&" : "?";
    location.href = `sms:${number}${sep}body=${encodeURIComponent(body)}`;
  }
  function getLocation() {
    return new Promise((resolve) => {
      if (!navigator.geolocation) return resolve(null);
      navigator.geolocation.getCurrentPosition(
        (p) => resolve(`https://maps.google.com/?q=${p.coords.latitude},${p.coords.longitude}`),
        () => resolve(null),
        { enableHighAccuracy: true, timeout: 8000 }
      );
    });
  }
  async function shareLocation(number) {
    const link = await getLocation();
    if (!link) return say("I could not find your location. Please turn on location and try again.");
    openSms(number, "This is my location: " + link);
  }

  /* ---------- read text aloud ---------- */
  function openReadBox() { $("#readbox").hidden = false; $("#read-text").focus(); }
  $("#read-paste").onclick = async () => {
    try { $("#read-text").value = await navigator.clipboard.readText(); }
    catch (_) { say("I could not paste. Please long-press in the box and choose paste."); }
  };
  $("#read-go").onclick = () => { unlockAudio(); say($("#read-text").value || "There is nothing to read."); };
  $("#read-close").onclick = () => { speechSynthesis.cancel(); $("#readbox").hidden = true; };

  /* ---------- emergency ---------- */
  async function startEmergency() {
    unlockAudio();
    let data;
    try { data = await api("/api/emergency"); } catch (_) { data = { contacts: [], number: "112" }; }
    $("#emergency").hidden = false;
    $("#em-actions").innerHTML = "";
    $("#em-title").textContent = "Getting help";
    $("#em-cancel").hidden = false; $("#em-close").hidden = true;
    let n = 5;
    $("#em-count").textContent = n;
    say("Emergency. I will send for help in 5 seconds. Press the big Cancel button to stop.");
    clearInterval(emTimer);
    emTimer = setInterval(() => {
      n -= 1;
      $("#em-count").textContent = n;
      if (n <= 0) { clearInterval(emTimer); fireEmergency(data); }
    }, 1000);
  }
  async function fireEmergency(data) {
    $("#em-cancel").hidden = true; $("#em-close").hidden = false;
    $("#em-count").textContent = "";
    $("#em-title").textContent = "Help is being contacted. Press a red button to call.";
    const box = $("#em-actions");
    data.contacts.forEach((c) => {
      const a = el("a", "btn", "Call " + c.name);
      a.href = "tel:" + c.phone; box.append(a);
    });
    const a = el("a", "btn", "Call emergency services " + data.number);
    a.href = "tel:" + data.number; box.append(a);
    if (!data.contacts.length) say("You have no emergency contacts saved. Press the red button to call emergency services.");
    else await Promise.race([say("Press a red button to call. I am also opening a message with your location."), sleep(4500)]);
    if (data.contacts.length) {
      const link = await getLocation();
      const body = "EMERGENCY! I need help." + (link ? " My location: " + link : "");
      openSms(data.contacts.map((c) => c.phone).join(","), body);
    }
  }
  function closeEmergency() {
    clearInterval(emTimer);
    speechSynthesis.cancel();
    $("#emergency").hidden = true;
  }
  $("#em-cancel").onclick = () => { closeEmergency(); say("Okay, help is cancelled."); };
  $("#em-close").onclick = closeEmergency;
  $("#emergency-btn").onclick = startEmergency;

  /* ---------- ringing reminders and alarms ---------- */
  function alertText(r) { return (r.kind === "alarm" ? "Alarm. " : "Reminder. ") + r.title; }
  async function pollDue() {
    if (S.alertOpen) return;
    try {
      const d = await api("/api/reminders/due?now=" + encodeURIComponent(localNow()));
      if (d.due.length) showAlert(d.due[0]);
    } catch (_) {}
  }
  function showAlert(r) {
    S.alertOpen = true;
    $("#alert-text").textContent = r.title;
    $("#alert").hidden = false;
    const ring = () => { beep(); setTimeout(() => say(alertText(r)), 350); };
    ring();
    alertTimer = setInterval(ring, 25000);
    $("#alert-ok").onclick = async () => {
      clearInterval(alertTimer);
      speechSynthesis.cancel();
      try { await api(`/api/reminders/${r.id}/ack`, { now: localNow() }); } catch (_) {}
      $("#alert").hidden = true;
      S.alertOpen = false;
      loadState();
    };
  }

  /* ---------- simple screens ---------- */
  function parseLocal(s) {
    const [d, t] = s.split(" ");
    const [y, m, dd] = d.split("-").map(Number);
    const [h, mi] = (t || "00:00").split(":").map(Number);
    return new Date(y, m - 1, dd, h, mi);
  }
  function fmtWhen(s) {
    const dt = parseLocal(s), now = new Date();
    const day0 = (x) => new Date(x.getFullYear(), x.getMonth(), x.getDate());
    const diff = Math.round((day0(dt) - day0(now)) / 864e5);
    const day = diff === 0 ? "Today" : diff === 1 ? "Tomorrow"
      : dt.toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" });
    return day + " at " + dt.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
  }
  function deleteBtn(label, url) {
    const b = el("button", "btn danger", "Delete");
    b.type = "button";
    b.onclick = async () => {
      if (!confirm(label)) return;
      await api(url, null, "DELETE");
      loadState();
    };
    return b;
  }
  function fill(listId, emptyId, items, build) {
    const box = $(listId);
    box.replaceChildren();
    $(emptyId).hidden = items.length > 0;
    items.forEach((i) => box.append(build(i)));
  }
  async function loadState() {
    let d;
    try { d = await api("/api/state?now=" + encodeURIComponent(localNow())); } catch (_) { return; }
    fill("#list-reminders", "#empty-reminders", d.reminders, (r) => {
      const c = el("div", "item");
      c.append(el("p", "item-title", r.title), el("p", "item-sub", fmtWhen(r.due_at) + (r.repeat === "daily" ? " · every day" : "")));
      const row = el("div", "item-row");
      row.append(deleteBtn("Delete this reminder?", "/api/reminders/" + r.id));
      c.append(row);
      return c;
    });
    fill("#list-people", "#empty-people", d.contacts, (p) => {
      const c = el("div", "item");
      c.append(el("p", "item-title", p.name), el("p", "item-sub", (p.relation ? p.relation + " · " : "") + p.phone));
      if (p.is_emergency) c.append(el("span", "item-tag", "Emergency contact"));
      const row = el("div", "item-row");
      const call = el("a", "btn primary", "Call"); call.href = "tel:" + p.phone;
      const em = el("button", "btn", p.is_emergency ? "Not emergency" : "Make emergency"); em.type = "button";
      em.onclick = async () => { await api(`/api/contacts/${p.id}/emergency`, {}); loadState(); };
      row.append(call, em, deleteBtn("Delete " + p.name + "?", "/api/contacts/" + p.id));
      c.append(row);
      return c;
    });
    fill("#list-appointments", "#empty-appointments", d.appointments, (a) => {
      const c = el("div", "item");
      c.append(el("p", "item-title", a.doctor), el("p", "item-sub", fmtWhen(a.date + " " + a.time)));
      if (a.location) c.append(el("p", "item-sub", "Place: " + a.location));
      if (a.notes) c.append(el("p", "item-sub", "Note: " + a.notes));
      const row = el("div", "item-row");
      row.append(deleteBtn("Delete this appointment?", "/api/appointments/" + a.id));
      c.append(row);
      return c;
    });
  }

  $("#contact-form").onsubmit = async (e) => {
    e.preventDefault();
    const f = e.target;
    await api("/api/contacts", {
      name: f.name.value, relation: f.relation.value, phone: f.phone.value, is_emergency: f.is_emergency.checked,
    });
    f.reset();
    loadState();
    say("Saved.");
  };

  /* ---------- navigation, clock, wiring ---------- */
  function showScreen(name) {
    document.querySelectorAll(".screen").forEach((s) => s.classList.toggle("active", s.id === "screen-" + name));
    document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.dataset.screen === name));
    window.scrollTo(0, 0);
    if (name !== "home") loadState();
  }
  document.querySelectorAll(".tab").forEach((t) => (t.onclick = () => showScreen(t.dataset.screen)));

  function tickClock() {
    const d = new Date();
    $("#time").textContent = d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
    $("#date").textContent = d.toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" });
  }

  $("#mic").onclick = () => {
    if (S.busy) {
      // second tap: stop listening, or stop speaking
      try { S.rec && S.rec.stop(); } catch (_) {}
      speechSynthesis.cancel();
      return;
    }
    talk();
  };
  $("#confirm-yes").onclick = () => answer(true);
  $("#confirm-no").onclick = () => answer(false);
  $("#typed").onsubmit = async (e) => {
    e.preventDefault();
    const t = $("#typed-input").value.trim();
    if (!t) return;
    $("#typed-input").value = "";
    unlockAudio();
    await turn(t);
    setMode("idle");
  };

  if ("speechSynthesis" in window) speechSynthesis.getVoices();
  if (!SR) $("#typed").hidden = false;
  tickClock(); setInterval(tickClock, 20000);
  loadState();
  pollDue(); setInterval(pollDue, 15000);
})();
