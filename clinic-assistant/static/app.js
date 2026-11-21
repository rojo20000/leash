// Plain JavaScript, no libraries. All text is inserted with textContent, never as HTML.
const $ = (id) => document.getElementById(id);
let me = null;
let opts = null;  // pick lists for forms, from the server

const TIER_LABEL = { green: "Ready to read", amber: "Check first", red: "Stopped", error: "Not sent" };
const KIND_LABEL = { chat: "Assistant answer", draft: "Message draft", qa_sample: "Random quality check",
  document: "Suspicious document in a record", access: "Someone opened many records quickly" };
// One plain sentence per card: what the person looking at it should do.
function whatToDo(r) {
  if (!r.can_act) return r.status === "open" ? "Nothing for you to do. Someone else will review this." : null;
  if (r.kind === "qa_sample") return "Read the question and answer. Is the answer safe and sensible?";
  if (r.tier === "amber") return "Read the reasons, then release the answer to see it.";
  if (r.kind === "document") return "A note in this record contains hidden instructions for the AI. It was kept away from the model. Confirm if it's a real problem.";
  if (r.kind === "access") return "Check whether this person had a reason to open so many records.";
  return "Decide whether this request was a real problem or a false alarm.";
}
const STATUS_LABEL = {
  open: "open", released: "reviewed and released", dismissed: "false alarm",
  confirmed: "confirmed problem", checked_ok: "checked, fine", problem_found: "problem found",
};

async function api(path, body) {
  const opts = body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  };
  const r = await fetch(path, { credentials: "same-origin", ...opts });
  const data = await r.json().catch(() => ({}));
  if (r.status === 401 && path !== "/api/login") { showLogin(); throw new Error("Signed out."); }
  if (!r.ok) throw new Error(data.error || `Error ${r.status}`);
  return data;
}

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}
const can = (perms) => perms.split(",").some((p) => me.permissions.includes(p));
const tierChip = (tier) => el("span", `tier ${tier}`, TIER_LABEL[tier] || tier);
// Small drawn icons (one stroke weight), instead of text symbols.
const ICON_PATHS = { ok: "M3.5 8.5l3 3 6-7", warn: "M8 3.5v5.5M8 12v.5", blocked: "M4.5 4.5l7 7M11.5 4.5l-7 7" };
function icon(kind) {
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", "0 0 16 16"); svg.setAttribute("class", `icon ${kind}`); svg.setAttribute("aria-hidden", "true");
  const path = document.createElementNS(ns, "path");
  path.setAttribute("d", ICON_PATHS[kind] || ICON_PATHS.ok);
  svg.append(path); return svg;
}

function reasonList(reasons) {
  const ul = el("ul", "reasons");
  reasons.forEach((r) => ul.append(el("li", null, r)));
  return ul;
}

// ---- sign in / out -------------------------------------------------------
function showLogin() { $("app-view").hidden = true; $("login-view").hidden = false; }
fetch("/api/version").then((r) => r.json()).then((v) => {
  document.querySelectorAll(".app-version").forEach((n) => { n.textContent = `v${v.version}`; });
}).catch(() => {});

async function start() {
  try { me = await api("/api/me"); } catch { return showLogin(); }
  $("login-view").hidden = true; $("app-view").hidden = false;
  $("who-name").textContent = me.user;
  $("who-role").textContent = me.role.replace("_", " ");
  $("who-model").textContent = `Local model: ${me.model}`;
  document.querySelectorAll("[data-perm]").forEach((n) => { n.hidden = !can(n.dataset.perm); });
  if (!(me.leash && me.leash.enabled)) $("tab-btn-leash").hidden = true;
  const group = $("draft-group"); group.replaceChildren();
  Object.entries(me.recipient_groups).forEach(([k, v]) => {
    const o = el("option", null, `${k}: ${v}`); o.value = k; group.append(o);
  });
  $("mock-banner").hidden = !me.mock;
  opts = await api("/api/chart/options").catch(() => null);
  if (opts) regSetup();
  const h = new Date().getHours();
  sched.day = null; sched.clin = null;
  $("home-hello").textContent = `${h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening"}, ${me.user}`;
  showTab("home");
  refreshCount();
}

$("login-form").addEventListener("submit", async (e) => {
  e.preventDefault(); $("login-error").textContent = "";
  try {
    await api("/api/login", { username: $("login-user").value, password: $("login-pass").value });
    $("login-pass").value = ""; // ---- schedule: front desk and the clinic day ------------------------------
const sched = { day: null, clin: null, data: null, open: null };
const STATUS_WORD = { booked: "Booked", arrived: "Checked in", in_room: "With clinician", done: "Done",
  cancelled: "Cancelled", no_show: "No-show" };
const STATUS_TONE = { booked: "", arrived: "amber", in_room: "green", done: "done", cancelled: "off", no_show: "off" };
const fmtDay = (iso, today) => {
  const d = new Date(`${iso}T12:00`);
  const label = d.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" });
  const diff = Math.round((d - new Date(`${today}T12:00`)) / 864e5);
  return diff === 0 ? `Today, ${label}` : diff === 1 ? `Tomorrow, ${label}` : label;
};
const minutes = (hhmm) => { const [h, m] = hhmm.split(":").map(Number); return h * 60 + m; };

// Two presses for anything that can't be taken back. The first press says what will happen.
function confirmStep(btn, prompt, action) {
  const label = btn.textContent; let armed = false, timer;
  btn.addEventListener("click", async () => {
    if (!armed) {
      armed = true; btn.textContent = prompt; btn.classList.add("confirming");
      timer = setTimeout(() => { armed = false; btn.textContent = label; btn.classList.remove("confirming"); }, 5000);
      return;
    }
    clearTimeout(timer); btn.disabled = true;
    try { await action(); } finally { btn.disabled = false; }
  });
}

function fillSelect(sel, entries, value) {
  sel.replaceChildren(...entries.map(([v, t]) => { const o = el("option", null, t); o.value = v; return o; }));
  if (value !== undefined && value !== null) sel.value = value;
}

async function loadSchedule() {
  $("sched-error").textContent = "";
  let d;
  try { d = await api(`/api/schedule${sched.day ? `?date=${sched.day}` : ""}`); }
  catch (err) { $("sched-error").textContent = err.message; return; }
  sched.data = d; sched.day = d.date;
  if (sched.clin === null) sched.clin = d.clinicians[me.user] ? me.user : "";
  fillSelect($("sched-day"), d.days.map((x) => [x, fmtDay(x, d.today)]), d.date);
  fillSelect($("sched-clin"), [["", "All clinicians"], ...Object.entries(d.clinicians)], sched.clin);
  document.querySelectorAll("[data-day]").forEach((b) => b.classList.toggle("on", d.days[+b.dataset.day] === d.date));
  $("sched-title").textContent = fmtDay(d.date, d.today);
  const rows = d.appointments.filter((a) => !sched.clin || a.clinician === sched.clin);
  const n = (st) => rows.filter((a) => a.status === st).length;
  $("sched-counts").textContent = rows.length
    ? [`${rows.length} appointments`, `${n("booked")} booked`, `${n("arrived")} checked in`, `${n("in_room")} with clinician`,
       `${n("done")} done`, n("cancelled") + n("no_show") ? `${n("cancelled") + n("no_show")} cancelled or no-show` : ""].filter(Boolean).join(" · ")
    : "No appointments.";
  const body = $("sched-body"); body.replaceChildren();
  rows.forEach((a) => body.append(...schedRow(a, d)));
  if (!rows.length) { const tr = el("tr"); const td = el("td", "muted", "Nothing booked for this day yet."); td.colSpan = 6; tr.append(td); body.append(tr); }
  if (can("book")) bookDefaults(d);
}

function schedRow(a, d) {
  const isToday = d.date === d.today;
  const tr = el("tr", `appt ${a.status}${sched.open === a.id ? " open" : ""}`);
  const who = el("td");
  if (can("view_patients")) {
    const b = el("button", "linkish", a.patient.name); b.type = "button";
    b.onclick = () => { showTab("patients"); openPatient(a.patient.id); };
    who.append(b, el("div", "muted", `${a.patient.age} ${a.patient.sex}${a.patient.attention ? ` · ${a.patient.attention} to check` : ""}`));
  } else {
    who.append(el("strong", null, a.patient.name), el("div", "muted", `${a.patient.insurance ? a.patient.insurance.plan : ""} · prefers ${(a.patient.preferred_contact || "").toLowerCase()}`));
  }
  const st = el("td"); st.append(el("span", `state ${STATUS_TONE[a.status]}`, STATUS_WORD[a.status] || a.status));
  if (a.reminder && a.reminder.sent_at) st.append(el("div", "muted", "reminder sent"));
  const act = el("td", "act");
  const step = (label, to, cls = "small-btn") => {
    const b = el("button", cls, label); b.type = "button";
    b.onclick = () => move(a, to); return b;
  };
  const toggle = (label) => {
    const b = el("button", `small-btn${sched.open === a.id ? "" : " ghost"}`, sched.open === a.id ? "Close" : label);
    b.type = "button"; b.onclick = () => { sched.open = sched.open === a.id ? null : a.id; loadSchedule(); }; return b;
  };
  if (can("check_in") && isToday && a.status === "booked") act.append(toggle("Check in"));
  else if (can("check_in") && a.status === "arrived") act.append(step("Undo check-in", "booked", "ghost small-btn"));
  else if (can("send_reminder") && !isToday && a.status === "booked") act.append(toggle(a.reminder && a.reminder.sent_at ? "Details" : "Reminder"));
  else if (can("room_patient") && isToday && a.status === "arrived") act.append(step("Start visit", "in_room"));
  else if (can("room_patient") && a.status === "in_room") act.append(step("Finish visit", "done", "ghost small-btn"));
  tr.append(el("td", "time", a.time), who, el("td", null, a.visit_type), el("td", null, a.clinician_name), st, act);
  const out = [tr];
  if (sched.open === a.id) out.push(detailRow(a, d));
  return out;
}

async function move(a, to, extra = {}) {
  $("sched-error").textContent = "";
  try { await api("/api/schedule/status", { id: a.id, expected: a.status, to, ...extra }); sched.open = null; }
  catch (err) { $("sched-error").textContent = err.message; }
  loadSchedule();
}

// The panel under a row: identity checks before check-in, cancel and no-show, or the reminder.
function detailRow(a, d) {
  const tr = el("tr", "detail"); const td = el("td"); td.colSpan = 6; tr.append(td);
  const p = { ...a.patient, insurance: { ...(a.patient.insurance || {}) } };
  const facts = el("div", "facts-wrap");
  let revealed = false; const onReveal = [];
  const drawFacts = () => {
    const dl = el("dl", "facts");
    const hid = (v) => (revealed ? v || "none" : "hidden");
    [["Born", hid(p.birthDate)], ["Phone", hid(p.phone)], ["Address", hid(p.address)],
     ["Insurance", `${p.insurance.plan || "none on file"}${p.insurance.plan && p.insurance.plan !== "Self-pay" ? `, member ${hid(p.insurance.member_id)}` : ""}`],
     ["Prefers", p.preferred_contact], ["Language", p.language]].forEach(([k, v]) => dl.append(el("dt", null, k), el("dd", v === "hidden" ? "locked" : null, v)));
    facts.replaceChildren(dl);
    if (!revealed) {
      facts.append(el("p", "muted", "Birth date, phone, address and member ID stay hidden until you type your PIN."),
        pinBox(p.id, (v) => { Object.assign(p, v); p.insurance.member_id = v.member_id; revealed = true; drawFacts(); onReveal.forEach((f) => f()); }, "Show details"));
    }
  };
  drawFacts();
  const msg = el("p", "error"); msg.setAttribute("role", "alert");
  if (d.date !== d.today) {  // reminder for an upcoming day
    const box = el("div", "detail-grid"); const right = el("div");
    const text = el("textarea", "reminder-text"); text.readOnly = true; text.rows = 4;
    const sent = a.reminder && a.reminder.sent_at;
    const prep = el("button", "small-btn", "Prepare reminder"); prep.type = "button";
    const copy = el("button", "ghost small-btn", "Copy text"); copy.type = "button"; copy.disabled = true;
    const done = el("button", "small-btn", "I've sent it"); done.type = "button"; done.disabled = true;
    const show = (r) => { text.value = r.text; copy.disabled = false; done.disabled = !!r.appointment.reminder.sent_at; };
    prep.onclick = async () => {
      try { show(await api("/api/schedule/reminder", { id: a.id, action: "prepare" })); prep.hidden = true; }
      catch (err) { msg.textContent = err.message; }
    };
    copy.onclick = async () => { text.select(); try { await navigator.clipboard.writeText(text.value); copy.textContent = "Copied"; } catch { document.execCommand("copy"); } };
    confirmStep(done, "Press again to record it as sent", async () => {
      try { await api("/api/schedule/reminder", { id: a.id, action: "sent" }); sched.open = null; loadSchedule(); }
      catch (err) { msg.textContent = err.message; }
    });
    right.append(el("h3", null, sent ? `Reminder sent by ${a.reminder.sent_by} at ${a.reminder.sent_at.slice(11)}` : "Reminder"));
    if (!sent) {
      right.append(el("p", "muted", "Fixed wording with no medical details. The app never sends anything: copy it into your usual texting or portal tool, send it, then record it here."),
        text, (() => { const r = el("div", "actions"); r.append(prep, copy, done); return r; })());
    }
    box.append(facts, right); td.append(box, msg); return tr;
  }
  // Check-in: both identity checks must be ticked before the button works.
  const box = el("div", "detail-grid"); const right = el("div");
  const dob = el("input"); dob.type = "checkbox";
  const ins = el("input"); ins.type = "checkbox";
  dob.disabled = true; ins.disabled = true;
  const t1 = el("span", null, "Show details first, then ask the patient for their date of birth");
  const t2 = el("span", null, "Then check their insurance card");
  const l1 = el("label", "check"); l1.append(dob, t1);
  const l2 = el("label", "check"); l2.append(ins, t2);
  onReveal.push(() => {
    dob.disabled = false; ins.disabled = false;
    t1.textContent = `Patient told me their date of birth and it matches ${p.birthDate}`;
    t2.textContent = p.insurance.plan && p.insurance.plan !== "Self-pay"
      ? `Insurance card matches ${p.insurance.plan}, member ${p.insurance.member_id}` : "Self-pay confirmed with the patient";
  });
  const go = el("button", null, "Check in"); go.type = "button"; go.disabled = true;
  const sync = () => { go.disabled = !(dob.checked && ins.checked); };
  dob.onchange = sync; ins.onchange = sync;
  go.onclick = () => move(a, "arrived", { checks: { dob: dob.checked, insurance: ins.checked } });
  right.append(el("h3", null, `Check in ${p.name}`), l1, l2, go);
  // Other outcomes, kept apart from the main button.
  const other = el("div", "other-actions");
  const reason = el("select"); fillSelect(reason, [["", "Reason for cancelling..."], ...d.cancel_reasons.map((r) => [r, r])]);
  const cancel = el("button", "danger small-btn", "Cancel appointment"); cancel.type = "button"; cancel.disabled = true;
  reason.onchange = () => { cancel.disabled = !reason.value; };
  confirmStep(cancel, "Press again to cancel it", () => move(a, "cancelled", { reason: reason.value }));
  const graceEnds = minutes(a.time) + d.no_show_after_minutes;
  const noShow = el("button", "ghost small-btn", "Mark no-show"); noShow.type = "button";
  if (minutes(d.now) < graceEnds) {
    noShow.disabled = true;
    const hh = String(Math.floor(graceEnds / 60)).padStart(2, "0"), mm = String(graceEnds % 60).padStart(2, "0");
    noShow.title = `Available from ${hh}:${mm}`; noShow.textContent = `No-show (from ${hh}:${mm})`;
  }
  confirmStep(noShow, "Press again to mark no-show", () => move(a, "no_show"));
  other.append(reason, cancel, noShow);
  right.append(el("h3", null, "Not coming?"), other);
  box.append(facts, right); td.append(box, msg); return tr;
}

$("sched-day").addEventListener("change", (e) => { sched.day = e.target.value; sched.open = null; loadSchedule(); });
$("sched-clin").addEventListener("change", (e) => { sched.clin = e.target.value; loadSchedule(); });
document.querySelectorAll("[data-day]").forEach((b) => b.addEventListener("click", () => {
  if (sched.data) { sched.day = sched.data.days[+b.dataset.day]; sched.open = null; loadSchedule(); }
}));

// ---- booking: every field is a pick, never free text, so it can't be mistyped
const book = { patient: null };
function bookDefaults(d) {
  if (!$("book-clin").options.length) {
    fillSelect($("book-clin"), [["", "Pick a clinician..."], ...Object.entries(d.clinicians)]);
    fillSelect($("book-type"), [["", "Pick a visit type..."], ...d.visit_types.map((v) => [v, v])]);
  }
  const keep = $("book-day").value;
  fillSelect($("book-day"), d.days.map((x) => [x, fmtDay(x, d.today)]), keep || d.days[0]);
}
async function loadSlots() {
  const t = $("book-time"), c = $("book-clin").value, day = $("book-day").value;
  if (!c || !day) { fillSelect(t, [["", "Pick a clinician and day first"]]); t.disabled = true; return bookCheck(); }
  const slots = await api(`/api/schedule/slots?date=${day}&clinician=${c}`).catch(() => []);
  fillSelect(t, slots.length ? [["", `${slots.length} open times...`], ...slots.map((s) => [s, s])] : [["", "No open times that day"]]);
  t.disabled = !slots.length; bookCheck();
}
function bookCheck() {
  const c = $("book-clin"), day = $("book-day"), t = $("book-time"), type = $("book-type");
  const ready = book.patient && c.value && day.value && t.value && type.value;
  $("book-btn").disabled = !ready;
  const miss = !book.patient ? "Pick a patient to start." : !c.value ? "Now pick a clinician." : !t.value ? "Now pick an open time."
    : !type.value ? "Last, pick a visit type." : null;
  $("book-summary").textContent = miss || `Book ${book.patient.name} with ${c.selectedOptions[0].textContent}, ${day.selectedOptions[0].textContent} at ${t.value}, ${type.value}.`;
  $("book-summary").classList.toggle("ready", !miss);
}
function pickPatient(p) {
  book.patient = p; $("book-results").replaceChildren(); $("book-q").value = ""; $("book-q").hidden = true;
  const box = $("book-picked"); box.hidden = false;
  const change = el("button", "ghost small-btn", "Change"); change.type = "button";
  change.onclick = () => { book.patient = null; box.hidden = true; $("book-q").hidden = false; $("book-q").focus(); bookCheck(); };
  const txt = el("div"); txt.append(el("strong", null, p.name), el("div", "muted", p.insurance ? p.insurance.plan : ""));
  box.replaceChildren(txt, change); bookCheck();
}
let bookTimer;
$("book-q").addEventListener("input", () => {
  clearTimeout(bookTimer);
  bookTimer = setTimeout(async () => {
    const q = $("book-q").value.trim(); const list = $("book-results");
    if (q.length < 2) { list.replaceChildren(); return; }
    const hits = await api(`/api/frontdesk/patients?q=${encodeURIComponent(q)}`).catch(() => []);
    list.replaceChildren(...(hits.length ? hits.map((p) => {
      const b = el("button", "patient-item"); b.type = "button";
      b.append(el("strong", null, p.name), el("div", "muted", `${p.insurance ? p.insurance.plan : ""} · prefers ${(p.preferred_contact || "").toLowerCase()}`));
      b.onclick = () => pickPatient(p); return b;
    }) : [el("p", "muted", "No match. Check the spelling, or try the birth date.")]));
  }, 200);
});
["book-clin", "book-day"].forEach((id) => $(id).addEventListener("change", loadSlots));
["book-time", "book-type"].forEach((id) => $(id).addEventListener("change", bookCheck));
$("book-form").addEventListener("submit", async (e) => {
  e.preventDefault(); const msg = $("book-msg"); msg.textContent = ""; msg.className = "error";
  const btn = $("book-btn"); btn.disabled = true;
  try {
    const a = await api("/api/schedule/book", { patient_id: book.patient.id, clinician: $("book-clin").value,
      date: $("book-day").value, time: $("book-time").value, visit_type: $("book-type").value });
    msg.className = "ok-line"; msg.textContent = `Booked: ${a.patient.name}, ${a.time} with ${a.clinician_name}.`;
    $("book-picked").hidden = true; $("book-q").hidden = false; book.patient = null; $("book-type").value = "";
    sched.day = a.date; await loadSchedule(); await loadSlots();
  } catch (err) { msg.textContent = err.message; await loadSlots(); }
});

// ---- front desk assistant: schedule only ----------------------------------
const DESK_SUGGESTED = ["Who is still to arrive today?", "What times are open tomorrow with Dr Osei?",
  "Write a polite message for a patient running 20 minutes late"];
$("desk-suggestions").replaceChildren(...DESK_SUGGESTED.map((q) => {
  const b = el("button", "chip", q); b.type = "button"; b.onclick = () => deskAsk(q); return b;
}));
async function deskAsk(text) {
  const log = $("desk-log"), btn = $("desk-form").querySelector("button");
  btn.disabled = true; $("desk-input").value = "";
  const wait = pending(log);
  try {
    const r = await api("/api/frontdesk/ask", { message: text });
    wait.remove();
    addMsg("you", r.masked_input, `The model saw: ${r.model_saw}`, log);
    if (r.tier === "redirect") {
      const { body } = aiMsg("amber", "Not for the front desk", log); body.append(el("p", null, r.reasons[0]));
      addTrace(r.trace, log);
    } else showAnswer(r, log);
  } catch (err) { wait.remove(); const { body } = aiMsg("error", "Not sent", log); body.append(el("p", null, err.message)); }
  btn.disabled = false;
}
$("desk-form").addEventListener("submit", (e) => { e.preventDefault(); const t = $("desk-input").value.trim(); if (t) deskAsk(t); });
enterToSend($("desk-input"), $("desk-form"));

// ---- live: other people's changes show up without a reload -----------------
setInterval(() => {
  if (!me || document.hidden) return;
  const busy = document.activeElement && /INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName);
  const tab = document.querySelector(".tab:not([hidden])");
  if (!tab || busy || $("reg-dialog").open) return;
  if (tab.id === "tab-schedule" && !sched.open) loadSchedule();
  if (tab.id === "tab-home") loadHome();
  if (tab.id === "tab-patients") { loadPatients(); if (currentPatient) loadHistory(currentPatient.id); }
  refreshCount();
}, 15000);

start();
  } catch (err) { $("login-error").textContent = err.message; }
});

$("logout").addEventListener("click", async () => {
  await api("/api/logout", {}).catch(() => {});
  $("chat-log").replaceChildren(); $("pt-chat-log").replaceChildren(); showLogin();
});

// ---- tabs ----------------------------------------------------------------
function showTab(name) {
  document.querySelectorAll(".tab").forEach((t) => { t.hidden = t.id !== `tab-${name}`; });
  document.querySelectorAll("#tabs button").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  if (name === "home") loadHome();
  if (name === "patients") loadPatients();
  if (name === "schedule") loadSchedule();
  if (name === "review") loadReviews();
  if (name === "outbox") loadOutbox();
  if (name === "audit") loadAudit();
}
document.querySelectorAll("#tabs button").forEach((b) => b.addEventListener("click", () => showTab(b.dataset.tab)));

// ---- Leash tab (integrated mode): every record comes through the Leash gateway ----
function leashReasoner(d) {
  const box = el("div", "leash-box");
  if (d.reasons && d.reasons.length) {
    const ul = el("ul", "reasons");
    d.reasons.forEach((r) => ul.append(el("li", null, `${r.code} (${r.stage}): ${r.detail}`)));
    box.append(el("h3", null, "Reasons"), ul);
  }
  const x = d.reasoner;
  if (x) {
    box.append(el("h3", null, "Leash's explanation (advisory: a reviewer makes the final call)"), el("p", null, x.explanation),
      el("p", "muted", `Risk: ${x.risk_level}`), el("p", "muted", `Recommended: ${x.recommended_action}`),
      el("p", "muted", `Rules: ${(x.policy_rule_ids || []).join(", ")}`), el("p", "muted", `Source: ${x.served_by}`));
  }
  return box;
}

function leashShow(d) {
  const out = $("leash-result"); out.replaceChildren();
  out.append(el("p", "muted", `Request id: ${d.call_id}`));
  if (d.state === "allow") {
    out.append(el("span", "tier green", "Allowed by Leash"), el("p", null, d.view === "full" ? "Full chart" : "Scheduling view"));
    Object.entries((d.result && d.result.resources) || {}).forEach(([type, list]) => {
      out.append(el("h3", null, `${type} (${list.length})`), el("pre", "leash-pre", JSON.stringify(list, null, 2)));
    });
    out.append(el("h3", null, "Removed by Leash"));
    if (d.redactions && d.redactions.length) {
      const ul = el("ul", "reasons");
      d.redactions.forEach((r) => ul.append(el("li", null, `${r.path} (${r.kind}, ${r.source})`)));
      out.append(ul);
    } else out.append(el("p", "muted", "Nothing removed"));
    return;
  }
  const wait = d.state === "escalate";
  const box = leashReasoner(d); box.classList.add(wait ? "wait" : "blocked");
  out.append(el("span", `tier ${wait ? "amber" : "red"}`, wait ? "Waiting for review in Leash" : "Blocked by Leash"));
  if (wait) {
    out.append(el("p", null, `Queue id: ${d.queue_id}`));
    const p = el("p", null, "Approve or deny it in the Leash dashboard at ");
    const a = el("a", null, d.dashboard_url); a.href = d.dashboard_url; a.target = "_blank"; a.rel = "noopener";
    p.append(a); out.append(p);
  }
  out.append(box);
}

async function leashCall(path, body) {
  $("leash-error").textContent = "";
  try { return await api(path, body); }
  catch (err) { $("leash-error").textContent = err.message; $("leash-result").replaceChildren(); return null; }
}

async function leashOpen(id, view) {
  $("leash-result").replaceChildren();
  const d = await leashCall("/api/leash/open", { patient_id: id, view });
  if (d) leashShow(d);
}

[["leash-open-sched", "scheduling"], ["leash-open-full", "full"]].forEach(([id, view]) => $(id).addEventListener("click", () => {
  const pid = $("leash-pid").value.trim();
  if (!/^pt-\d{4}$/.test(pid)) {
    $("leash-error").textContent = "Enter a patient id like pt-0042."; $("leash-result").replaceChildren(); return;
  }
  leashOpen(pid, view);
}));

$("leash-search-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const list = $("leash-results"); list.replaceChildren(); $("leash-result").replaceChildren();
  const d = await leashCall("/api/leash/search", { q: $("leash-q").value });
  if (!d) return;
  if (d.state !== "allow") return leashShow(d);
  const pts = (d.result && d.result.patients) || [];
  if (!pts.length) list.append(el("li", "muted", "No patients found."));
  pts.forEach((p) => {
    const n = (p.name && p.name[0]) || null;
    const name = n ? `${(n.given || []).join(" ")} ${n.family || ""}`.trim() : p.id;
    const li = el("li", "row"), t = el("div", "row-text"), btns = el("div", "leash-btns");
    t.append(el("strong", null, name || p.id), el("span", "muted", p.id));
    [["Scheduling view", "scheduling"], ["Full chart (Leash will block)", "full"]].forEach(([label, view]) => {
      const b = el("button", "ghost small-btn", label); b.type = "button"; b.onclick = () => leashOpen(p.id, view); btns.append(b);
    });
    li.append(t, btns); list.append(li);
  });
});

document.querySelectorAll("[data-go]").forEach((b) => b.addEventListener("click", () => showTab(b.dataset.go)));

function todoRow(title, detail, label, onClick, tone) {
  const row = el("div", `row${tone ? ` ${tone}` : ""}`);
  const text = el("div", "row-text"); text.append(el("strong", null, title), el("span", "muted", detail));
  const b = el("button", "ghost small-btn", label); b.onclick = onClick;
  row.append(text, b); return row;
}

async function loadHome() {
  const box = $("home-todo");
  const rows = [], said = [];
  if (can("view_schedule")) {
    const day = await api("/api/schedule").catch(() => null);
    if (day) {
      const mineOnly = day.clinicians[me.user] ? day.appointments.filter((a) => a.clinician === me.user) : day.appointments;
      const live = mineOnly.filter((a) => a.status !== "cancelled");
      const waiting = live.filter((a) => a.status === "arrived");
      const due = live.filter((a) => a.status === "booked");
      const who = day.clinicians[me.user] ? "Your" : "The clinic's";
      if (can("check_in")) {
        if (due.length) {
          said.push(`${due.length} still to arrive today`);
          const n = due[0];
          rows.push(todoRow(`Next due: ${n.time} ${n.patient.name}`, `${n.visit_type} with ${n.clinician_name} · ${due.length} still to arrive`,
            "Schedule", () => showTab("schedule")));
        }
        const tomorrow = await api(`/api/schedule?date=${day.days[1]}`).catch(() => null);
        const toSend = tomorrow ? tomorrow.appointments.filter((a) => a.status === "booked" && !(a.reminder && a.reminder.sent_at)) : [];
        if (toSend.length) {
          said.push(`${toSend.length} reminders to send for tomorrow`);
          rows.push(todoRow(`${toSend.length} reminder${toSend.length > 1 ? "s" : ""} to send for tomorrow`,
            "Prepare each one, send it the usual way, then mark it sent", "Reminders",
            () => { sched.day = day.days[1]; showTab("schedule"); }));
        }
      } else {
        if (waiting.length) {
          said.push(`${waiting.length} checked in and waiting`);
          waiting.forEach((a) => rows.push(todoRow(`Waiting: ${a.patient.name}`,
            `Checked in for ${a.time} · ${a.visit_type}${a.patient.attention ? ` · ${a.patient.attention} to check` : ""}`,
            "Open chart", () => { showTab("patients"); openPatient(a.patient.id); }, "urgent-row")));
        }
        if (due.length) {
          said.push(`${due.length} more booked today`);
          rows.push(todoRow(`${who} day: ${live.length} appointments`, `${due.length} not here yet · next at ${due[0].time}`,
            "Schedule", () => showTab("schedule")));
        }
      }
    }
  }
  const reviews = can("chat,review_red,qa_review") ? await api("/api/reviews").catch(() => []) : [];
  const mine = reviews.filter((i) => i.can_act);
  if (mine.length) {
    said.push(`${mine.length} item${mine.length > 1 ? "s" : ""} to review`);
    rows.push(todoRow(`${mine.length} item${mine.length > 1 ? "s" : ""} to review`,
      "Answers held for you, stopped requests or quality checks", "Review", () => showTab("review"), "urgent-row"));
  }
  if (can("approve_message")) {
    const drafts = (await api("/api/outbox").catch(() => [])).filter((d) => d.status === "awaiting_approval");
    if (drafts.length) {
      said.push(`${drafts.length} message${drafts.length > 1 ? "s" : ""} to approve`);
      rows.push(todoRow(`${drafts.length} message draft${drafts.length > 1 ? "s" : ""} to approve`,
        "Nothing is sent until a clinician approves it", "Messages", () => showTab("outbox")));
    }
  }
  if (can("view_patients")) {
    const all = (await api("/api/patients").catch(() => [])).filter((p) => p.attention);
    if (all.length) said.push(`${all.length} patients with something to check`);
    all.slice(0, 5).forEach((p) => rows.push(todoRow(p.name,
      `${p.attention} to check · ${p.age} ${p.sex} · ${p.conditions.join(", ")}`, "Open",
      () => { showTab("patients"); openPatient(p.id); })));
  }
  if (can("view_patients")) {
    const recent = await api("/api/chart/recent").catch(() => []);
    $("home-recent").replaceChildren(...(recent.length ? recent.slice(0, 8).map((h) => todoRow(
      `${h.patient}: ${h.summary}`, `${h.ts.replace("T", " ").slice(0, 16)} UTC · ${h.user}`, "Open",
      () => { showTab("patients"); openPatient(h.patient_id); })) : [el("p", "muted", "Nothing added yet. New patients, notes and results show up here.")]));
  }
  $("home-summary").textContent = said.length ? `${said.join(", ")}.` : "Nothing is waiting for you.";
  box.replaceChildren(...(rows.length ? rows : [el("p", "muted", "You're all caught up.")]));
}

async function refreshCount() {
  if (!can("chat,review_red,qa_review")) return;
  const items = await api("/api/reviews").catch(() => []);
  const n = items.filter((i) => i.can_act).length;
  $("review-count").hidden = n === 0; $("review-count").textContent = n;
}

// ---- assistant: where answers land ---------------------------------------
const NOTE_SPLIT = "\n\n---\n";

function addMsg(kind, text, meta, log = $("chat-log")) {
  const m = el("div", `msg ${kind}`, text);
  if (meta) m.append(el("span", "meta", meta));
  log.append(m); m.scrollIntoView({ block: "nearest" });
  return m;
}

// An assistant message: a header that says what happened, then the body.
function aiMsg(tier, headText, log) {
  const kind = tier === "amber" ? "held" : (tier === "red" || tier === "error") ? "blocked" : "";
  const m = el("div", `msg ai ${kind}`);
  const head = el("div", "msg-head");
  head.append(tierChip(tier), el("span", null, headText));
  const body = el("div", "msg-body");
  m.append(head, body); log.append(m);
  return { m, body };
}

// Model text arrives with the review note appended; show it as a footer, not as part of the answer.
function fillAnswer(container, text, parent) {
  const [main, note] = text.split(NOTE_SPLIT);
  const urgentAt = main.indexOf("If this is happening now");
  if (urgentAt === 0) {
    const cut = main.indexOf("\n\n");
    container.append(el("div", "urgent", cut > 0 ? main.slice(0, cut) : main));
    container.append(document.createTextNode(cut > 0 ? main.slice(cut + 2) : ""));
  } else container.append(document.createTextNode(main));
  if (note && parent) parent.append(el("div", "msg-foot", note));
}

function pending(log) {
  const m = el("div", "msg ai pending");
  m.append(el("span", "spinner"), el("span", null, "Checking your request and asking the model on this computer. This can take a minute."));
  log.append(m); m.scrollIntoView({ block: "nearest" });
  return m;
}

// The safety steps this request went through, folded into one line.
function addTrace(trace, log = $("chat-log")) {
  const bad = trace.find((t) => t.status === "blocked"), warn = trace.find((t) => t.status === "warn");
  const state = bad ? "blocked" : warn ? "warn" : "ok";
  const d = el("details", `checks ${state}`);
  const sum = el("summary");
  sum.append(icon(state),
    el("span", null, bad ? `Stopped at: ${bad.step}` : warn ? `Flagged at: ${warn.step}` : `${trace.length} safety checks passed`));
  const ol = el("ol", "trace");
  trace.forEach((t) => {
    const li = el("li", `step ${t.status}`);
    li.append(icon(t.status),
              el("span", "name", t.step), el("span", "detail", t.detail));
    ol.append(li);
  });
  d.append(sum, ol); log.append(d);
  d.scrollIntoView({ block: "nearest" });
}

function showAnswer(r, log = $("chat-log")) {
  if (r.tier === "green") {
    const { m, body } = aiMsg("green", "Draft answer", log);
    fillAnswer(body, r.reply, m);
  } else if (r.tier === "amber") {
    const { body } = aiMsg("amber", "Read this before you see the answer", log);
    body.append(reasonList(r.reasons));
    const btn = el("button", null, "I've read this. Show the answer");
    btn.onclick = async () => {
      btn.disabled = true;
      try {
        const done = await api("/api/reviews/decide", { id: r.review_id, action: "release" });
        const box = el("div", "released"); fillAnswer(box, done.answer || "", box);
        btn.replaceWith(box);
        refreshCount();
      } catch (err) { btn.disabled = false; alert(err.message); }
    };
    body.append(btn);
  } else if (r.tier === "red") {
    const { body } = aiMsg("red", "Not shown", log);
    body.append(el("p", null, "A clinical lead or admin will review this request. You don't need to do anything."),
                reasonList(r.reasons));
  } else {
    const { body } = aiMsg("error", "Not sent", log);
    body.append(el("p", null, r.reasons.join(" ")));
  }
  if (r.trace) addTrace(r.trace, log);
  log.lastElementChild.scrollIntoView({ block: "nearest" });
}

// Enter sends, Shift+Enter adds a line.
function enterToSend(textarea, form) {
  textarea.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); form.requestSubmit(); }
  });
}

async function ask(log, input, button, payload) {
  button.disabled = true; input.value = "";
  const wait = pending(log);
  try {
    const r = await api("/api/chat", payload);
    wait.remove();
    addMsg("you", r.masked_input,
           r.masked_tags.length ? `Masked before sending: ${r.masked_tags.join(", ")}` : "Nothing needed masking", log);
    showAnswer(r, log);
    refreshCount();
  } catch (err) {
    wait.remove();
    const { body } = aiMsg("error", "Not sent", log); body.append(el("p", null, err.message));
  }
  button.disabled = false; input.focus();
}

$("chat-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const text = $("chat-input").value.trim(); if (!text) return;
  ask($("chat-log"), $("chat-input"), $("chat-form").querySelector("button"), { message: text });
});
enterToSend($("chat-input"), $("chat-form"));

$("chat-clear").addEventListener("click", async () => {
  await api("/api/chat/clear", {}); $("chat-log").replaceChildren();
});

// ---- patients: browse a record and chat about it -------------------------
let currentPatient = null;
const SUGGESTED = ["What needs attention for this patient?", "Summarise this patient for a handover",
                   "Any medication interactions or allergy conflicts?", "Explain the latest results in plain language"];

async function loadPatients() {
  const q = $("patient-search").value;
  const items = await api(`/api/patients?q=${encodeURIComponent(q)}`);
  const ul = $("patient-items"); ul.replaceChildren();
  items.forEach((p) => {
    const li = el("li"); const b = el("button", `patient-item${currentPatient && currentPatient.id === p.id ? " active" : ""}`);
    const top = el("div", "row-between");
    top.append(el("strong", null, p.name), p.attention ? el("span", "flag-count", `${p.attention} to check`) : el("span", "no-flags", "clear"));
    b.append(top, el("div", "muted", `${p.age} ${p.sex} · ${p.conditions.join(", ")}`));
    b.onclick = () => openPatient(p.id);
    li.append(b); ul.append(li);
  });
}
let searchTimer;
$("patient-search").addEventListener("input", () => { clearTimeout(searchTimer); searchTimer = setTimeout(loadPatients, 200); });

const listInto = (id, items) => $(id).replaceChildren(...items.map((t) => el("li", null, t)));

async function openPatient(id) {
  let p;
  try { p = await api(`/api/patients/${encodeURIComponent(id)}`); }
  catch (err) { alert(err.message); refreshCount(); return; }
  const switched = !currentPatient || currentPatient.id !== p.id;
  $("patient-empty").hidden = true; $("patient-view").hidden = false; $("pt-chat-pane").hidden = false;
  $("pt-chat-name").textContent = p.name.given;
  $("pt-name").textContent = `${p.name.given} ${p.name.family}`;
  $("pt-meta").textContent = `${p.age} years · ${p.sex}`
    + (p.insurance ? ` · ${p.insurance.plan} · prefers ${p.preferred_contact.toLowerCase()}${p.language !== "English" ? ` · ${p.language}` : ""}` : "");
  $("pt-ident").replaceChildren(identBlock(p.id, p.locked || []));
  loadHistory(p.id);
  const att = $("pt-attention"); att.replaceChildren();
  if (p.attention.length) {
    const box = el("div", "attention"); box.append(el("strong", null, `${p.attention.length} thing${p.attention.length > 1 ? "s" : ""} to check`));
    const ul = el("ul"); p.attention.forEach((a) => ul.append(el("li", null, a))); box.append(ul);
    const go = el("button", "ghost small-btn", "Ask what to do about these");
    go.type = "button"; go.onclick = () => askPatient("What needs attention for this patient, and what should I check first?");
    box.append(go); att.append(box);
  }
  listInto("pt-conditions", p.conditions); listInto("pt-meds", p.medications); listInto("pt-allergies", p.allergies);
  $("pt-obs").replaceChildren(...[...p.observations].sort((a, b) => b.date.localeCompare(a.date)).map((o) => {
    const tr = el("tr"); tr.append(el("td", null, o.date), el("td", null, o.name), el("td", null, `${o.value} ${o.unit}`.trim()), el("td", "muted", o.ref));
    return tr;
  }));
  $("pt-notes").replaceChildren(...p.notes.map((n) => {
    const d = el("div", "note"); d.append(el("div", "muted", `${n.date} · ${n.type} · ${n.author}`), el("div", "quote", n.text));
    return d;
  }));
  loadSimilar(p.id);
  if (switched) { $("pt-chat-log").replaceChildren(); api("/api/chat/clear", {}).catch(() => {}); }
  currentPatient = p;
  if (switched) resetEntry(); else entryFields();
  $("pt-suggestions").replaceChildren(...SUGGESTED.map((q) => {
    const b = el("button", "chip", q); b.type = "button"; b.onclick = () => askPatient(q); return b;
  }));
  loadPatients();
}

async function loadSimilar(id) {
  const ul = $("pt-similar"); ul.replaceChildren();
  let items;
  try { items = await api(`/api/patients/${encodeURIComponent(id)}/similar`); } catch (err) { return; }
  items.forEach((o) => {
    const li = el("li"), b = el("button", "patient-item");
    b.type = "button"; b.onclick = () => openPatient(o.id);
    const top = el("div", "row-between");
    top.append(el("strong", null, o.name), el("span", "match", `${Math.round(o.score * 100)}% match`));
    const why = o.shared.length ? `Shares: ${o.shared.join(", ")}` : `Has: ${o.conditions.join(", ")}`;
    b.append(top, el("div", "muted", `${o.age} · ${o.sex} · ${why}`));
    li.append(b); ul.append(li);
  });
}

function askPatient(text) {
  ask($("pt-chat-log"), $("pt-chat-input"), $("pt-chat-form").querySelector("button"),
      { message: text, patient_id: currentPatient.id });
}
$("pt-chat-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const t = $("pt-chat-input").value.trim(); if (t) askPatient(t);
});
enterToSend($("pt-chat-input"), $("pt-chat-form"));
$("pt-chat-clear").addEventListener("click", async () => { await api("/api/chat/clear", {}); $("pt-chat-log").replaceChildren(); });

// ---- confidential details: hidden until the PIN is typed, every time -------
const FIELD_LABEL = { birthDate: "Born", mrn: "MRN", phone: "Phone", address: "Address", member_id: "Insurance ID" };
const digits4 = (v) => /^\d{4}$/.test(v);
function pinBox(pid, onShown, label = "Show") {
  const f = el("form", "pin-inline"); f.noValidate = true;
  const pin = el("input", "pin"); pin.type = "password"; pin.inputMode = "numeric"; pin.maxLength = 4;
  pin.placeholder = "PIN"; pin.autocomplete = "off"; pin.setAttribute("aria-label", "PIN");
  const go = el("button", "small-btn", label); go.type = "submit"; go.disabled = true;
  const msg = el("span", "error");
  pin.oninput = () => { pin.value = pin.value.replace(/\D/g, ""); go.disabled = !digits4(pin.value); msg.textContent = ""; };
  f.onsubmit = async (e) => {
    e.preventDefault(); go.disabled = true;
    try { const v = await api("/api/reveal", { patient_id: pid, pin: pin.value }); onShown(v); }
    catch (err) { msg.textContent = err.message; pin.value = ""; pin.focus(); }
  };
  f.append(pin, go, msg); return f;
}
function identBlock(pid, locked) {
  const box = el("div", "ident-box");
  if (!locked.length) return box;
  const lockedLine = () => {
    box.replaceChildren(el("span", "muted", `${locked.map((k) => FIELD_LABEL[k] || k).join(", ")}: hidden`),
      pinBox(pid, (v) => {
        const dl = el("dl", "facts inline");
        Object.entries(v).forEach(([k, val]) => dl.append(el("dt", null, FIELD_LABEL[k] || k), el("dd", null, val || "none")));
        const hide = el("button", "ghost small-btn", "Hide"); hide.type = "button"; hide.onclick = lockedLine;
        box.replaceChildren(dl, hide);
      }, "Show details"));
  };
  lockedLine(); return box;
}

// ---- chart history and additions ------------------------------------------
async function loadHistory(pid) {
  const ol = $("pt-history");
  const items = await api(`/api/patients/${encodeURIComponent(pid)}/history`).catch(() => []);
  ol.replaceChildren(...(items.length ? items.map((h) => {
    const li = el("li"); li.append(el("span", "when", `${h.ts.replace("T", " ").slice(0, 16)} UTC`), el("span", "who", h.user), el("span", null, h.summary));
    if (h.change && h.change.text && h.change.type) li.append(el("div", "quote", h.change.text));
    return li;
  }) : [el("li", "muted", "Nothing added since this record was created.")]));
}

const ENTRY_TEXT_HINT = { condition: "e.g. Iron deficiency anemia", medication: "e.g. Ferrous sulfate 325 mg daily",
  allergy: "e.g. Latex (rash)", attention: "e.g. Repeat potassium in 1 week" };
function entryInput(id, placeholder, max = 120) {
  const i = el("input"); i.id = id; i.placeholder = placeholder || ""; i.maxLength = max; i.autocomplete = "off"; return i;
}
function labelled(text, control) { const l = el("label", null, text + " "); l.append(control); return l; }
function entryFields() {
  const kind = $("entry-kind").value, box = $("entry-fields"), p = currentPatient;
  box.replaceChildren(); $("entry-allergy").hidden = true;
  if (!kind || !p || !opts) return entryCheck();
  if (kind === "note") {
    const t = el("select"); t.id = "entry-type"; fillSelect(t, [["", "Pick a note type..."], ...opts.note_types.map((x) => [x, x])]);
    const ta = el("textarea"); ta.id = "entry-text"; ta.rows = 4; ta.maxLength = 4000; ta.placeholder = "What happened, what you found, what we learned";
    box.append(labelled("Type", t), labelled("Note", ta));
  } else if (kind === "result") {
    const t = el("select"); t.id = "entry-test"; fillSelect(t, [["", "Pick a test..."], ...Object.keys(opts.results).map((x) => [x, x])]);
    const v = entryInput("entry-value", "", 12); const hint = el("p", "muted"); hint.id = "entry-hint";
    t.onchange = () => {
      const r = opts.results[t.value]; v.value = "";
      v.placeholder = t.value === "Blood pressure" ? "e.g. 128/82" : r ? `number${r.unit ? ` in ${r.unit}` : ""}` : "";
      hint.textContent = r ? `Reference ${r.ref || "n/a"}${r.limits ? ` · must be between ${r.limits[0]} and ${r.limits[1]}` : ""}` : "";
      entryCheck();
    };
    box.append(labelled("Test", t), labelled("Value", v), hint);
  } else if (kind === "stop_medication" || kind === "resolve_attention") {
    const list = kind === "stop_medication" ? p.medications : p.attention;
    const t = el("select"); t.id = "entry-pick";
    fillSelect(t, list.length ? [["", "Pick one..."], ...list.map((x) => [x, x])] : [["", "Nothing to pick"]]);
    box.append(labelled(kind === "stop_medication" ? "Medicine to stop" : "Item to resolve", t),
      labelled(kind === "stop_medication" ? "Why" : "What was done", entryInput("entry-reason", kind === "stop_medication" ? "e.g. Side effects, switched to..." : "e.g. Repeat test normal", 160)));
  } else {
    box.append(labelled("Entry", entryInput("entry-text", ENTRY_TEXT_HINT[kind])));
  }
  box.querySelectorAll("input,select,textarea").forEach((n) => n.addEventListener("input", entryCheck));
  box.querySelectorAll("select").forEach((n) => n.addEventListener("change", entryCheck));
  entryCheck();
}
// Client-side copy of the server's rules, so the button only lights up when the entry would be accepted.
function entryState() {
  const kind = $("entry-kind").value, v = (id) => ($(id) ? $(id).value.trim() : "");
  if (!kind) return { msg: "Pick what you're adding." };
  if (kind === "note") {
    if (!v("entry-type")) return { msg: "Pick a note type." };
    if (v("entry-text").length < 5) return { msg: "Write the note (at least 5 characters)." };
    return { body: { type: v("entry-type"), text: $("entry-text").value }, say: `Add a ${v("entry-type").toLowerCase()}.` };
  }
  if (kind === "result") {
    const name = v("entry-test"), val = v("entry-value"), r = opts.results[name];
    if (!name) return { msg: "Pick a test." };
    if (!val) return { msg: "Type the value." };
    if (name === "Blood pressure") {
      const m = val.match(/^(\d{2,3})\/(\d{2,3})$/);
      if (!m || +m[1] <= +m[2]) return { msg: "Blood pressure looks like 128/82, top number higher." };
    } else {
      const n = Number(val);
      if (val === "" || Number.isNaN(n)) return { msg: `${name} must be a number.` };
      if (r.limits && (n < r.limits[0] || n > r.limits[1])) return { msg: `${name} ${val} isn't possible (allowed ${r.limits[0]} to ${r.limits[1]}). Check for a typo.`, bad: true };
    }
    return { body: { name, value: val }, say: `Add result ${name} ${val} ${r.unit}.` };
  }
  if (kind === "stop_medication" || kind === "resolve_attention") {
    if (!v("entry-pick")) return { msg: "Pick from the list." };
    if (v("entry-reason").length < 3) return { msg: kind === "stop_medication" ? "Say why it's stopped." : "Say what was done." };
    return { body: { text: v("entry-pick"), reason: v("entry-reason") }, say: `${kind === "stop_medication" ? "Stop" : "Resolve"}: ${v("entry-pick")}.` };
  }
  const text = v("entry-text");
  if (text.length < 3) return { msg: "Type the entry (at least 3 characters)." };
  const body = { text };
  if (kind === "medication") {
    const low = text.toLowerCase();
    const clash = currentPatient.allergies.find((a) => Object.entries(opts.allergy_families)
      .some(([fam, words]) => a.toLowerCase().includes(fam) && words.some((w) => low.includes(w))));
    const warn = $("entry-allergy");
    if (clash) {
      if (!warn.dataset.for || warn.dataset.for !== clash) {
        warn.replaceChildren(el("strong", null, `Allergy: ${clash}`));
        const l = el("label", "check"); const cb = el("input"); cb.type = "checkbox"; cb.id = "entry-override";
        cb.onchange = entryCheck; l.append(cb, el("span", null, "I've checked the allergy and still want to add this medicine"));
        warn.append(l); warn.dataset.for = clash;
      }
      warn.hidden = false;
      if (!$("entry-override").checked) return { msg: "This medicine may clash with a recorded allergy. Tick the box only if you mean it.", bad: true };
      body.confirm_allergy = true;
    } else { warn.hidden = true; warn.dataset.for = ""; }
  }
  return { body, say: `Add ${$("entry-kind").selectedOptions[0].textContent.toLowerCase().replace(/^an? /, "")}: ${text}.` };
}
function entryCheck() {
  const st = entryState(), pinOk = digits4($("entry-pin").value);
  $("entry-btn").disabled = !(st.body && pinOk);
  $("entry-summary").textContent = st.body ? (pinOk ? st.say : `${st.say} Type your PIN to save.`) : st.msg;
  $("entry-summary").className = `summary ${st.bad ? "error" : st.body && pinOk ? "ready" : "muted"}`;
}
function resetEntry() { $("entry-kind").value = ""; $("entry-pin").value = ""; $("entry-msg").textContent = ""; entryFields(); }
$("entry-kind").addEventListener("change", () => { $("entry-msg").textContent = ""; entryFields(); });
$("entry-pin").addEventListener("input", () => { $("entry-pin").value = $("entry-pin").value.replace(/\D/g, ""); entryCheck(); });
$("entry-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const st = entryState(); if (!st.body) return;
  const msg = $("entry-msg"); msg.className = "error"; msg.textContent = ""; $("entry-btn").disabled = true;
  try {
    const r = await api(`/api/patients/${encodeURIComponent(currentPatient.id)}/entry`,
      { kind: $("entry-kind").value, pin: $("entry-pin").value, ...st.body });
    const kept = $("entry-kind").value;
    await openPatient(currentPatient.id);
    $("entry-kind").value = kept; $("entry-pin").value = ""; entryFields();
    msg.className = r.warnings.length ? "error" : "ok-line";
    msg.textContent = r.warnings.length ? r.warnings.join(" ") : "Added. It's in the chart and the history below.";
  } catch (err) { msg.textContent = err.message; $("entry-pin").value = ""; entryCheck(); }
});

// ---- register a new patient -------------------------------------------------
function regSetup() {
  fillSelect($("reg-sex"), [["", "Pick..."], ...opts.sexes.map((x) => [x, x])]);
  fillSelect($("reg-plan"), [["", "Pick..."], ...opts.plans.map((x) => [x, x])]);
  fillSelect($("reg-contact"), [["", "Pick..."], ...opts.contact.map((x) => [x, x])]);
  fillSelect($("reg-language"), [["", "Pick..."], ...opts.languages.map((x) => [x, x])]);
  $("reg-birth").max = new Date().toISOString().slice(0, 10);
}
const NAME_OK = /^[A-Za-z][A-Za-z' -]{0,38}[A-Za-z]$/;
function regProblems() {
  const v = (id) => $(id).value.trim(), out = [];
  if (!NAME_OK.test(v("reg-given"))) out.push("First name: letters, spaces, hyphens or apostrophes, 2 or more.");
  if (!NAME_OK.test(v("reg-family"))) out.push("Last name: letters, spaces, hyphens or apostrophes, 2 or more.");
  const b = v("reg-birth");
  if (!b) out.push("Date of birth.");
  else if (b > new Date().toISOString().slice(0, 10)) out.push("Date of birth can't be in the future.");
  else if (+b.slice(0, 4) < new Date().getFullYear() - 120) out.push("Date of birth is over 120 years ago.");
  if (!v("reg-sex")) out.push("Sex.");
  if (!/^(\d{3}-)?\d{3}-\d{4}$/.test(v("reg-phone"))) out.push("Phone like 555-0123.");
  if (v("reg-address").length < 5) out.push("Address.");
  if (!v("reg-plan")) out.push("Insurance plan.");
  else if (v("reg-plan") !== "Self-pay" && !/^[A-Z0-9]{6,12}$/.test(v("reg-member").toUpperCase())) out.push("Member ID: 6 to 12 letters or digits.");
  if (!v("reg-contact")) out.push("Contact preference.");
  if (!v("reg-language")) out.push("Language.");
  return out;
}
function regCheck() {
  const self = $("reg-plan").value === "Self-pay"; $("reg-member").disabled = self; if (self) $("reg-member").value = "";
  const probs = regProblems(), pinOk = digits4($("reg-pin").value);
  $("reg-problems").replaceChildren(...(probs.length ? [el("li", "muted", "Still needed:"), ...probs.map((x) => el("li", null, x))]
    : pinOk ? [] : [el("li", "muted", "All fields look right. Type your PIN to save.")]));
  $("reg-btn").disabled = !!probs.length || !pinOk;
}
document.querySelectorAll("#reg-form input, #reg-form select").forEach((n) => { n.addEventListener("input", regCheck); n.addEventListener("change", regCheck); });
$("reg-pin").addEventListener("input", () => { $("reg-pin").value = $("reg-pin").value.replace(/\D/g, ""); regCheck(); });
document.querySelectorAll("[data-register]").forEach((b) => b.addEventListener("click", () => {
  $("reg-form").reset(); $("reg-msg").textContent = ""; regCheck(); $("reg-dialog").showModal(); $("reg-given").focus();
}));
$("reg-close").addEventListener("click", () => $("reg-dialog").close());
$("reg-form").addEventListener("submit", async (e) => {
  e.preventDefault(); if (regProblems().length) return;
  const v = (id) => $(id).value.trim(); $("reg-btn").disabled = true; $("reg-msg").textContent = "";
  try {
    const r = await api("/api/patients/new", { given: v("reg-given"), family: v("reg-family"), birthDate: v("reg-birth"),
      sex: v("reg-sex"), phone: v("reg-phone"), address: v("reg-address"), plan: v("reg-plan"),
      member_id: v("reg-member").toUpperCase(), preferred_contact: v("reg-contact"), language: v("reg-language"), pin: v("reg-pin") });
    $("reg-dialog").close();
    if (can("book")) { showTab("schedule"); pickPatient({ id: r.id, name: r.name, insurance: { plan: v("reg-plan") } }); }
    else if (can("view_patients")) { showTab("patients"); openPatient(r.id); }
  } catch (err) { $("reg-msg").textContent = err.message; $("reg-pin").value = ""; regCheck(); }
});

// ---- review queue --------------------------------------------------------
const ACTIONS = {
  amber: [["release", "I've read the reasons. Release it", ""]],
  red: [["dismiss", "False alarm", "ghost"], ["confirm", "Confirm problem", "danger"]],
  qa_sample: [["ok", "Looks fine", ""], ["problem", "Problem found", "danger"]],
};

function reviewCard(r) {
  const card = el("div", `review ${r.tier}`);
  const head = el("div", "row-between");
  const left = el("div"); left.append(tierChip(r.tier), el("strong", null, ` ${KIND_LABEL[r.kind] || r.kind}`));
  head.append(left, el("span", "status", STATUS_LABEL[r.status] || r.status));
  card.append(head, el("p", "muted",
    `Asked by ${r.requester}, ${r.created}${r.reviewer ? ` · reviewed by ${r.reviewer}, ${r.decided}` : ""}`));
  const todo = whatToDo(r);
  if (todo) card.append(el("p", r.can_act ? "todo-line" : "muted", todo));
  card.append(el("div", "label", "Why it's here"), reasonList(r.reasons));
  card.append(el("div", "label", "Request (masked)"), el("div", "quote", r.masked_input));
  if (r.answer) card.append(el("div", "label", "Answer"), el("div", "quote", r.answer));
  else if (r.tier === "red" && r.requester === me.user) card.append(el("p", "muted", "Waiting for a second person to review."));
  if (r.can_act) {
    const actions = el("div", "actions");
    (ACTIONS[r.kind === "qa_sample" ? "qa_sample" : r.tier] || []).forEach(([action, label, cls]) => {
      const b = el("button", cls, label);
      b.onclick = async () => {
        try { await api("/api/reviews/decide", { id: r.id, action }); loadReviews(); refreshCount(); }
        catch (err) { alert(err.message); }
      };
      actions.append(b);
    });
    card.append(actions);
  }
  return card;
}

async function loadReviews() {
  const items = await api("/api/reviews");
  const todo = items.filter((i) => i.can_act), done = items.filter((i) => !i.can_act);
  $("todo-n").textContent = todo.length ? `(${todo.length})` : "";
  $("done-n").textContent = done.length ? `(${done.length})` : "";
  $("review-todo").replaceChildren(...(todo.length ? todo.map(reviewCard) : [el("p", "muted", "Nothing needs you right now.")]));
  $("review-done").replaceChildren(...(done.length ? done.map(reviewCard) : [el("p", "muted", "Nothing here yet.")]));
}
$("review-refresh").addEventListener("click", () => { loadReviews(); refreshCount(); });

// ---- messages to other people (draft, approve, copy) ---------------------
async function loadOutbox() {
  const list = $("outbox-list"); list.replaceChildren();
  const items = await api("/api/outbox");
  if (!items.length) list.append(el("p", "muted", "No drafts yet."));
  items.forEach((it) => {
    const box = el("div", `draft review ${it.tier || "green"}`);
    const head = el("div", "row-between");
    const left = el("div"); left.append(tierChip(it.tier || "green"), el("strong", null, ` To: ${it.recipient_group}`));
    head.append(left, el("span", `status ${it.status}`, it.status.replace("_", " ")));
    box.append(head, el("p", "muted", `Drafted by ${it.drafted_by}, ${it.created}${it.decided_by ? ` · decided by ${it.decided_by}` : ""}`));
    if (it.reasons && it.reasons.length) box.append(reasonList(it.reasons));
    const text = el("textarea"); text.value = it.final_text || it.draft;
    text.readOnly = !(it.status === "awaiting_approval" && can("approve_message"));
    box.append(text);
    const actions = el("div", "actions");
    if (it.status === "awaiting_approval" && can("approve_message")) {
      const ok = el("button", null, "Approve (with any edits)");
      const no = el("button", "ghost", "Reject");
      ok.onclick = () => decide(it.id, "approve", text.value);
      no.onclick = () => decide(it.id, "reject");
      actions.append(ok, no);
    }
    if (it.status === "approved") {
      const copy = el("button", "ghost", "Copy approved text");
      copy.onclick = () => navigator.clipboard.writeText(text.value);
      actions.append(copy, el("span", "muted", "Fill in the [TAGS] and send it yourself through the usual channel."));
    }
    box.append(actions); list.append(box);
  });
}

async function decide(id, decision, finalText) {
  try { await api("/api/outbox/decide", { id, decision, final_text: finalText }); loadOutbox(); }
  catch (err) { alert(err.message); }
}

$("draft-form").addEventListener("submit", async (e) => {
  e.preventDefault(); $("draft-error").textContent = "";
  const btn = e.submitter; btn.disabled = true;
  try {
    const r = await api("/api/outbox/draft", {
      recipient_group: $("draft-group").value, instructions: $("draft-instructions").value,
    });
    if (r.tier === "red" || r.tier === "error") {
      $("draft-error").textContent = `${TIER_LABEL[r.tier]}: ${r.reasons.join(" ")}`;
      refreshCount();
    } else { $("draft-instructions").value = ""; loadOutbox(); }
  } catch (err) { $("draft-error").textContent = err.message; }
  btn.disabled = false;
});

// ---- audit log -----------------------------------------------------------
async function loadAudit() {
  const r = await api("/api/audit");
  $("audit-verify").textContent = r.verify.ok
    ? `Log intact: ${r.verify.entries} entries, hash chain verified.`
    : `WARNING: log has been altered (chain breaks at line ${r.verify.broken_at_line}).`;
  $("audit-verify").className = r.verify.ok ? "muted" : "error";
  const v = r.vectors;
  if (v) {
    const counts = Object.entries(v.collections).map(([k, n]) => `${n} ${k.replace("_", " ")}`).join(", ");
    $("vector-verify").textContent = v.ok
      ? `Vector store intact: ${v.rows} rows (${counts}), append-only, hash chain verified. Embedder: ${v.embedder}.`
      : `WARNING: vector store has been altered (chain breaks at row ${v.broken_at_row}).`;
    $("vector-verify").className = v.ok ? "muted" : "error";
  }
  const body = $("audit-body"); body.replaceChildren();
  r.entries.forEach((x) => {
    const tr = el("tr");
    tr.append(el("td", null, x.ts), el("td", null, x.event), el("td", null, x.user || "system"),
              el("td", "details", JSON.stringify(x.details)));
    body.append(tr);
  });
}
$("audit-refresh").addEventListener("click", loadAudit);

start();
