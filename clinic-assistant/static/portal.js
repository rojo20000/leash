// Patient portal. Plain JavaScript, no libraries. All server text is inserted with textContent, never as HTML.
// The server knows who is signed in: no patient id is ever sent from here.
const $ = (id) => document.getElementById(id);

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

async function api(path, body) {
  const opts = body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  };
  let r;
  try { r = await fetch(path, { credentials: "same-origin", ...opts }); }
  catch (e) { throw new Error("Could not reach the clinic. Check your connection and try again."); }
  const data = await r.json().catch(() => ({}));
  if (r.status === 401) { location.href = "/"; throw new Error("You are signed out."); }
  if (!r.ok) throw new Error(data.error || `Something went wrong (error ${r.status}). Please try again.`);
  return data;
}

// "2026-11-21" -> "Sat, 21 Nov 2026". Built from the parts so the day never shifts with the time zone.
function fmtDay(d) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(d || "");
  return m ? new Date(+m[1], m[2] - 1, +m[3]).toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short", year: "numeric" }) : (d || "");
}
function fmtWhen(at) {
  const d = new Date(at);
  return isNaN(d) ? (at || "") : d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}
const has = (v) => v !== undefined && v !== null && v !== "";
function emptyLine(title, how) {
  const p = el("p", "empty-line"); p.append(el("strong", null, title), document.createTextNode(` ${how}`)); return p;
}
function state(map, key) {
  const [label, cls] = map[key] || [String(key || "").replace(/_/g, " "), ""];
  return el("span", `state ${cls}`, label);
}

// ---- appointments --------------------------------------------------------
const APPT_STATE = { booked: ["Booked", "green"], arrived: ["Checked in", "amber"], in_room: ["With the clinician", "amber"],
  done: ["Completed", "done"], cancelled: ["Cancelled", "off"], no_show: ["Missed", "off"] };
const REQ_STATE = { open: ["Open: waiting for the front desk", "amber"], done: ["Done", "green"], declined: ["Declined", "red"] };
let formReady = false;

function apptRow(a, cancelAsked) {
  const row = el("div", "row"), text = el("div", "row-text"), side = el("div", "row-side");
  text.append(el("strong", null, [fmtDay(a.date), a.time].filter(has).join(" at ")),
    el("span", "muted", [a.visit_type, a.clinician_name].filter(has).join(" with ")));
  side.append(state(APPT_STATE, a.status));
  if (cancelAsked) text.append(el("span", "muted", "You asked to cancel this visit. It stays booked until the front desk confirms."));
  if (a.can_cancel) {
    const note = el("span", "muted"), err = el("span", "error");
    note.setAttribute("role", "status"); err.setAttribute("role", "alert");
    text.append(note, err);
    side.append(cancelButton(a, note, err));
  }
  row.append(text, side);
  return row;
}

// Two presses: the first arms the button for a few seconds, the second sends the request.
function cancelButton(a, note, err) {
  const b = el("button", "danger small-btn", "Ask to cancel");
  b.type = "button";
  let armed = null;
  const disarm = () => { clearTimeout(armed); armed = null; b.textContent = "Ask to cancel"; b.classList.remove("confirming"); note.textContent = ""; };
  b.addEventListener("blur", disarm);
  b.addEventListener("click", async () => {
    if (!armed) {
      armed = setTimeout(disarm, 8000);
      b.textContent = "Press again to confirm"; b.classList.add("confirming"); err.textContent = "";
      note.textContent = "Press the button again to ask the front desk to cancel this visit.";
      return;
    }
    disarm(); b.disabled = true;
    try {
      await api("/api/portal/appointments/cancel", { appointment_id: a.id });
      await loadAppointments();
      $("appt-status").textContent = "We asked the front desk to cancel that visit. It stays booked until they confirm.";
    } catch (e) { err.textContent = e.message; b.disabled = false; }
  });
  return b;
}

function reqRow(q, d) {
  const row = el("div", "row"), text = el("div", "row-text"), side = el("div", "row-side");
  let title;
  if (q.kind === "cancel") {
    const a = [...d.upcoming, ...d.past].find((x) => x.id === q.appointment_id);
    title = a ? `Cancel the visit on ${[fmtDay(a.date), a.time].filter(has).join(" at ")}` : "Cancel a visit";
  } else {
    const who = (d.clinicians.find((c) => c.id === q.clinician) || {}).name || q.clinician;
    title = ["New appointment", q.visit_type].filter(has).join(": ") + (has(who) ? ` with ${who}` : "");
  }
  text.append(el("strong", null, title));
  if (has(q.created_at)) text.append(el("span", "muted", `Sent ${fmtWhen(q.created_at)}`));
  if (has(q.preferred)) text.append(el("span", "muted", `Times that suit you: ${q.preferred}`));
  if (has(q.note)) text.append(el("span", "muted", `Your note: ${q.note}`));
  if (has(q.staff_note)) text.append(el("span", "staff-note", `Note from the front desk: ${q.staff_note}`));
  side.append(state(REQ_STATE, q.status));
  row.append(text, side);
  return row;
}

function fillSelect(sel, first, items) {
  const o = el("option", null, first); o.value = "";
  sel.replaceChildren(o, ...items.map(([value, label]) => { const x = el("option", null, label); x.value = value; return x; }));
}

async function loadAppointments() {
  $("appt-error").textContent = "";
  let d;
  try { d = await api("/api/portal/appointments"); } catch (e) { $("appt-error").textContent = e.message; return; }
  d = { ...d, upcoming: d.upcoming || [], past: d.past || [], requests: d.requests || [], clinicians: d.clinicians || [] };
  const asked = new Set(d.requests.filter((q) => q.kind === "cancel" && q.status === "open").map((q) => q.appointment_id));
  $("appt-upcoming").replaceChildren(...(d.upcoming.length ? d.upcoming.map((a) => apptRow(a, asked.has(a.id)))
    : [emptyLine("No visits coming up.", "When the front desk books a visit for you, it appears here.")]));
  $("appt-past").replaceChildren(...(d.past.length ? d.past.map((a) => apptRow(a, false))
    : [emptyLine("No past visits.", "Visits you have had at this clinic appear here.")]));
  $("req-list").replaceChildren(...(d.requests.length ? d.requests.map((q) => reqRow(q, d))
    : [emptyLine("No requests yet.", "Requests you send to the front desk appear here, with their answer.")]));
  $("clinic-phone").hidden = !has(d.clinic_phone);
  if (has(d.clinic_phone)) $("clinic-phone").textContent = `Need help sooner? Call the clinic on ${d.clinic_phone}.`;
  if (!formReady) {  // filled once, so coming back to this section does not wipe a half-written request
    fillSelect($("req-type"), "Choose a type of visit", (d.visit_types || []).map((v) => [v, v]));
    fillSelect($("req-clinician"), "No preference", d.clinicians.map((c) => [c.id, c.name]));
    formReady = true;
  }
}

$("req-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  $("req-error").textContent = ""; $("req-ok").textContent = ""; $("appt-status").textContent = "";
  $("req-send").disabled = true;
  try {
    await api("/api/portal/appointments/request", { visit_type: $("req-type").value, clinician: $("req-clinician").value,
      preferred: $("req-preferred").value.trim(), note: $("req-note").value.trim() });
    $("req-form").reset();
    await loadAppointments();
    $("req-ok").textContent = "Request sent. Nothing is booked yet: the front desk will confirm a time with you.";
  } catch (e) { $("req-error").textContent = e.message; }
  $("req-send").disabled = false;
});

// ---- my health summary ---------------------------------------------------
// Only keys the server sent are shown. A key that is present but empty gets a plain "none" line.
function fillList(key, p, none) {
  $(`chart-${key}-box`).hidden = !(key in p);
  const items = Array.isArray(p[key]) ? p[key] : [];
  $(`chart-${key}`).replaceChildren(...(items.length
    ? items.map((i) => el("li", null, typeof i === "object" && i ? String(i.name || "") : String(i)))
    : [el("li", "muted", none)]));
}

async function loadChart() {
  $("chart-error").textContent = "";
  let p;
  try { p = (await api("/api/portal/chart")).patient || {}; } catch (e) { $("chart-error").textContent = e.message; return; }
  const details = [["Name", p.name], ["Age", p.age], ["Sex", p.sex], ["Date of birth", fmtDay(p.birthDate)],
    ["Preferred contact", p.preferred_contact], ["Language", p.language]].filter(([, v]) => has(v));
  $("chart-details-box").hidden = !details.length;
  $("chart-details").replaceChildren(...details.flatMap(([k, v]) => [el("dt", null, k), el("dd", null, String(v))]));
  fillList("conditions", p, "None on record.");
  fillList("medications", p, "None on record.");
  fillList("allergies", p, "None on record.");
  $("chart-results-box").hidden = !("observations" in p);
  const obs = Array.isArray(p.observations) ? [...p.observations].sort((a, b) => String(b.date).localeCompare(String(a.date))) : [];
  $("chart-results").replaceChildren(...(obs.length ? obs.map((o) => {
    const tr = el("tr");
    tr.append(el("td", null, fmtDay(o.date)), el("td", null, has(o.name) ? String(o.name) : ""),
      el("td", null, [o.value, o.unit].filter(has).join(" ")), el("td", "muted", has(o.ref) ? String(o.ref) : ""));
    return tr;
  }) : [(() => {
    const tr = el("tr"), td = el("td", "muted", "No results yet. They appear here after your clinic records them.");
    td.colSpan = 4; tr.append(td); return tr;
  })()]));
  $("chart-empty").hidden = details.length > 0 || ["conditions", "medications", "allergies", "observations"].some((k) => k in p);
}

// ---- messages ------------------------------------------------------------
let replyTo = null;

function setReply(m) {
  replyTo = m ? m.id : null;
  $("reply-bar").hidden = !m;
  if (!m) return;
  const subject = m.subject || "";
  $("reply-what").textContent = `Replying to the care team's message${subject ? ` "${subject}"` : ""} from ${fmtWhen(m.at)}.`;
  if (!$("msg-subject").value.trim()) $("msg-subject").value = (/^re:/i.test(subject) ? subject : `Re: ${subject}`).trim().slice(0, 120);
  $("msg-body").focus();
}
$("reply-cancel").addEventListener("click", () => setReply(null));

function msgCard(m, all) {
  const mine = m.direction === "from_patient";
  const card = el("article", mine ? "pmsg mine" : "pmsg"), head = el("div", "pmsg-head");
  head.append(el("strong", null, m.from || (mine ? "You" : "Care team")), el("span", null, fmtWhen(m.at)));
  card.append(head, el("h3", null, m.subject || "(no subject)"));
  const parent = m.in_reply_to && all.find((x) => x.id === m.in_reply_to);
  if (parent) card.append(el("p", "muted", `In reply to "${parent.subject || "(no subject)"}"`));
  card.append(el("div", "quote", m.body || ""));
  if (!mine) {
    const actions = el("div", "actions"), b = el("button", "ghost small-btn", "Reply");
    b.type = "button"; b.addEventListener("click", () => setReply(m));
    actions.append(b); card.append(actions);
  }
  return card;
}

async function loadMessages() {
  $("msg-load-error").textContent = "";
  let d;
  try { d = await api("/api/portal/messages"); } catch (e) { $("msg-load-error").textContent = e.message; return; }
  if (has(d.emergency_notice)) $("emergency").textContent = d.emergency_notice;
  const all = d.messages || [];
  $("msg-list").replaceChildren(...(all.length ? all.map((m) => msgCard(m, all))
    : [emptyLine("No messages yet.", "Messages you send, and replies from your care team, appear here with the newest first.")]));
}

$("msg-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  $("msg-error").textContent = ""; $("msg-ok").textContent = "";
  $("msg-send").disabled = true;
  try {
    const body = { subject: $("msg-subject").value.trim(), body: $("msg-body").value.trim() };
    if (replyTo) body.in_reply_to = replyTo;
    const r = await api("/api/portal/messages", body);
    $("msg-form").reset(); setReply(null);
    const urgent = r.urgent === true;
    $("urgent-text").textContent = urgent ? (r.notice || $("emergency").textContent) : "";
    $("urgent-notice").hidden = !urgent;
    $("msg-ok").textContent = urgent ? "Your message was sent to the care team." : "Message sent. Replies from your care team appear on this page.";
    await loadMessages();
    if (urgent) { $("urgent-notice").scrollIntoView({ block: "center" }); $("urgent-notice").focus(); }
  } catch (e) { $("msg-error").textContent = e.message; }
  $("msg-send").disabled = false;
});

// ---- sections, sign out, start -------------------------------------------
// A section loads when it is opened, so the clinic's access log shows what was really looked at.
const TABS = { appointments: loadAppointments, chart: loadChart, messages: loadMessages };
function showTab() {
  const h = location.hash.slice(1), name = Object.hasOwn(TABS, h) ? h : "appointments";
  Object.keys(TABS).forEach((t) => { $(`tab-${t}`).hidden = t !== name; });
  document.querySelectorAll("#tabs button").forEach((b) => {
    const on = b.dataset.tab === name;
    b.classList.toggle("active", on);
    if (on) b.setAttribute("aria-current", "page"); else b.removeAttribute("aria-current");
  });
  TABS[name]();
}
document.querySelectorAll("#tabs button").forEach((b) => b.addEventListener("click", () => { location.hash = b.dataset.tab; }));
window.addEventListener("hashchange", showTab);

$("logout").addEventListener("click", async () => {
  try { await api("/api/logout", {}); } catch (e) { /* leave either way */ }
  location.href = "/";
});

(async () => {
  let me;
  try { me = await api("/api/me"); } catch (e) { $("boot-error").textContent = e.message; return; }
  if (me.portal !== true) { location.replace("/"); return; }  // staff accounts belong in the staff app
  if (has(me.clinic)) { $("clinic-name").textContent = me.clinic; document.title = `Patient portal · ${me.clinic}`; }
  $("patient-name").textContent = (me.patient && me.patient.name) || "";
  $("portal-view").hidden = false;
  showTab();
})();
