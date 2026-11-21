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
// A tab or block shows when the role has one of data-perm, or is named in data-roles.
const allowed = (n) => (n.dataset.perm ? can(n.dataset.perm) : false) || (n.dataset.roles || "").split(",").includes(me.role);
const canNetwork = () => can("view_network");
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

// An empty state that says what will appear here and how it gets there.
function emptyLine(title, how) {
  const p = el("p", "empty-line"); p.append(el("strong", null, title), document.createTextNode(` ${how}`)); return p;
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
  $("who-role").title = `Local model: ${me.model}`;
  document.querySelectorAll("[data-perm],[data-roles]").forEach((n) => { n.hidden = !allowed(n); });
  const group = $("draft-group"); group.replaceChildren();
  Object.entries(me.recipient_groups).forEach(([k, v]) => {
    const o = el("option", null, `${k}: ${v}`); o.value = k; group.append(o);
  });
  $("mock-banner").hidden = !me.mock;
  opts = await api("/api/chart/options").catch(() => null);
  if (opts) regSetup();
  const h = new Date().getHours();
  sched.day = null; sched.clin = null;
  cal.clin = null; cal.anchor = null; cal.view = null; cal.lastKey = null; closeCalPanel(false);
  $("home-hello").textContent = `${h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening"}, ${me.user}`;
  // A role that only looks after the network starts there.
  showTab(canNetwork() && !can("chat,view_schedule,view_patients,view_audit,frontdesk_chat") ? "network" : "home");
  refreshCount();
}

$("login-form").addEventListener("submit", async (e) => {
  e.preventDefault(); $("login-error").textContent = "";
  try {
    await api("/api/login", { username: $("login-user").value, password: $("login-pass").value });
    $("login-pass").value = ""; start();
  } catch (err) { $("login-error").textContent = err.message; }
});

$("logout").addEventListener("click", async () => {
  await api("/api/logout", {}).catch(() => {});
  $("chat-log").replaceChildren(); $("pt-chat-log").replaceChildren(); showLogin();
});

$("today-date").textContent = new Date().toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });

// ---- tabs ----------------------------------------------------------------
function showTab(name) {
  document.querySelectorAll(".tab").forEach((t) => { t.hidden = t.id !== `tab-${name}`; });
  document.querySelectorAll("#tabs button").forEach((b) => {
    b.classList.toggle("active", b.dataset.tab === name);
    if (b.dataset.tab === name) b.setAttribute("aria-current", "page"); else b.removeAttribute("aria-current");
  });
  const on = document.querySelector("#tabs button.active");
  if (on) {  // only scroll the tab row when the active tab is out of view (phones)
    const nav = $("tabs"), l = on.offsetLeft - nav.offsetLeft, r = l + on.offsetWidth;
    if (l < nav.scrollLeft) nav.scrollLeft = Math.max(0, l - 16);
    else if (r > nav.scrollLeft + nav.clientWidth) nav.scrollLeft = r - nav.clientWidth + 32;
  }
  if (name === "home") loadHome();
  if (name === "patients") loadPatients();
  if (name === "schedule") loadSchedule();
  if (name === "calendar") loadCalendar();
  if (name === "review") loadReviews();
  if (name === "outbox") loadOutbox();
  if (name === "audit") loadAudit();
  if (name === "conversations") loadConversations();
  if (name === "network") loadNetwork();
}
document.querySelectorAll("#tabs button").forEach((b) => b.addEventListener("click", () => showTab(b.dataset.tab)));

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
      `${h.patient ? `${h.patient}: ` : ""}${h.summary}`, `${whenText(h.ts || h.at)} · ${h.user || h.by}`, "Open",
      () => { showTab("patients"); openPatient(h.patient_id); })) : [el("p", "muted", "Nothing added yet. New patients, notes and results show up here.")]));
  }
  if (canNetwork()) {
    const n = await api("/api/network").catch(() => null);
    if (n && Array.isArray(n.nodes)) {
      const down = n.nodes.filter((x) => x.status === "down").length, eg = (n.egress || {}).outbound_internet || "unknown";
      if (down) said.push(`${down} service${down > 1 ? "s" : ""} down`);
      rows.push(todoRow(`Network: ${n.nodes.length - down} of ${n.nodes.length} services up`, (EGRESS_WORD[eg] || `outbound internet ${eg}`).replace(/^./, (c) => c.toUpperCase()),
        "Network", () => showTab("network"), down || eg === "allowed" ? "urgent-row" : ""));
    }
  }
  loadDbStatus();
  homeStart();
  $("home-summary").textContent = said.length ? `${said.join(", ")}.` : "Nothing is waiting for you.";
  box.replaceChildren(...(rows.length ? rows : [el("p", "muted", "You're all caught up.")]));
}

// One sentence and one button per role: where to start.
function homeStart() {
  const box = $("home-start");
  const go = (text, label, tab) => {
    const b = el("button", null, label); b.type = "button"; b.onclick = () => showTab(tab);
    box.replaceChildren(el("p", null, text), b); box.hidden = false;
  };
  if (can("check_in")) go("Start with today's schedule. Check people in as they arrive; booking and reminders are on the same page.", "Open today's schedule", "schedule");
  else if (can("review_red") && can("chat")) go("Start with Needs review: stopped requests wait for a clinical lead to decide.", "Open Needs review", "review");
  else if (can("view_patients") && can("view_schedule")) go("Start with today's calendar. Click any appointment to see the patient's record beside it.", "Open today's calendar", "calendar");
  else if (can("view_audit")) go("Start with the audit log: everything people and the assistant did, in order, tamper-evident.", "Open the audit log", "audit");
  else if (can("view_network")) go("Start with Network: what the app connects to, and the checks that show nothing leaves this computer.", "Open Network", "network");
  else box.hidden = true;
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
  const answer = log.lastElementChild;
  if (r.trace) addTrace(r.trace, log);
  // Show the start of the answer; the log (or the page) scrolls for the rest.
  answer.scrollIntoView({ block: answer.offsetHeight > log.clientHeight ? "start" : "nearest" });
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

const listInto = (node, items) => node.replaceChildren(...items.map((t) => el("li", null, t)));

// One patient record, drawn from <template id="tpl-record">. Used by the Patients tab and the Calendar panel,
// so both show exactly the same chart. onAsk(question) is called by "Ask what to do about these".
function renderRecord(p, root, onAsk) {
  if (!root.firstElementChild) root.append($("tpl-record").content.cloneNode(true));
  const f = (k) => root.querySelector(`[data-f="${k}"]`);
  f("name").textContent = `${String(p.name.family).toUpperCase()}, ${p.name.given}`;  // family name first, in capitals, as on clinical patient banners
  f("meta").replaceChildren(el("strong", null, `${p.age} years · ${p.sex}`),
    p.insurance ? ` · ${p.insurance.plan} · prefers ${p.preferred_contact.toLowerCase()}${p.language !== "English" ? ` · ${p.language}` : ""}` : "");
  const alg = f("alg");
  if (alg) {
    const real = (p.allergies || []).filter((x) => !/^(no known|nka|none)/i.test(String(x).trim()));
    const has = real.length > 0;
    alg.className = `banner-alg${has ? " has" : ""}`;
    alg.replaceChildren(el("span", "banner-k", "Allergies"),
      el("span", "banner-v", has ? real.join(", ") : "No known allergies"));
  }
  f("ident").replaceChildren(identBlock(p.id, p.locked || []));
  const att = f("attention"); att.replaceChildren();
  if (p.attention.length) {
    const box = el("div", "attention"); box.append(el("strong", null, `${p.attention.length} thing${p.attention.length > 1 ? "s" : ""} to check`));
    const ul = el("ul"); p.attention.forEach((a) => ul.append(el("li", null, a))); box.append(ul);
    if (onAsk) {
      const go = el("button", "ghost small-btn", "Ask what to do about these");
      go.type = "button"; go.onclick = () => onAsk("What needs attention for this patient, and what should I check first?");
      box.append(go);
    }
    att.append(box);
  }
  listInto(f("conditions"), p.conditions); listInto(f("meds"), p.medications); listInto(f("allergies"), p.allergies);
  f("obs").replaceChildren(...[...p.observations].sort((a, b) => b.date.localeCompare(a.date)).map((o) => {
    const tr = el("tr"); tr.append(el("td", null, o.date), el("td", null, o.name), el("td", "num", `${o.value} ${o.unit}`.trim()), el("td", "muted", o.ref));
    return tr;
  }));
  f("notes").replaceChildren(...p.notes.map((n) => {
    const d = el("div", "note"); d.append(el("div", "muted", `${n.date} · ${n.type} · ${n.author}`), el("div", "quote", n.text));
    return d;
  }));
}

async function openPatient(id) {
  let p;
  try { p = await api(`/api/patients/${encodeURIComponent(id)}`); }
  catch (err) { alert(err.message); refreshCount(); return; }
  const switched = !currentPatient || currentPatient.id !== p.id;
  $("patient-empty").hidden = true; $("patient-view").hidden = false; $("pt-chat-pane").hidden = false;
  $("pt-chat-name").textContent = p.name.given;
  renderRecord(p, $("pt-core"), askPatient);
  loadHistory(p.id);
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
  pin.placeholder = "••••"; pin.autocomplete = "off"; pin.setAttribute("aria-label", "PIN");
  const go = el("button", "small-btn", label); go.type = "submit"; go.disabled = true;
  const msg = el("span", "error");
  pin.oninput = () => { pin.value = pin.value.replace(/\D/g, ""); go.disabled = !digits4(pin.value); msg.textContent = ""; };
  f.onsubmit = async (e) => {
    e.preventDefault(); go.disabled = true;
    try { const v = await api("/api/reveal", { patient_id: pid, pin: pin.value }); onShown(v); }
    catch (err) { msg.textContent = err.message; pin.value = ""; pin.focus(); }
  };
  f.append(el("span", "pin-label", "PIN"), pin, go, msg); return f;
}
function identBlock(pid, locked) {
  const box = el("div", "ident-box");
  if (!locked.length) return box;
  const lockedLine = () => {
    box.replaceChildren(el("span", "muted", `Hidden until you type your PIN: ${locked.map((k) => FIELD_LABEL[k] || k).join(", ")}`),
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
const whenText = (iso) => {
  if (!iso) return "";
  const utc = /(Z|[+-]00:?00)$/.test(iso) || !/[+-]\d\d:?\d\d$/.test(iso);
  return `${iso.replace("T", " ").slice(0, 16)}${utc ? " UTC" : ""}`;
};
// A history entry, in either the chart-history shape {ts, user, summary, change}
// or the database shape {seq, at, by, role, entity, entity_id, action, summary}.
function historyItem(h) {
  const li = el("li");
  const by = h.by || h.user || "";
  const who = by + (h.role && h.role !== by ? ` · ${h.role.replace("_", " ")}` : "");
  li.append(el("span", "when", whenText(h.at || h.ts)), ...(who ? [el("span", "who", who)] : []), el("span", null, h.summary || `${h.action || "changed"} ${h.entity || ""}`.trim()));
  if (h.change && h.change.text && h.change.type) li.append(el("div", "quote", h.change.text));
  return li;
}
async function loadHistory(pid) {
  const ol = $("pt-history");
  const items = await api(`/api/patients/${encodeURIComponent(pid)}/history`).catch(() => []);
  ol.replaceChildren(...(items.length ? items.map(historyItem) : [el("li", "muted", "Nothing added since this record was created.")]));
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
  $("review-todo").replaceChildren(...(todo.length ? todo.map(reviewCard) : [emptyLine("Nothing needs you right now.", "Answers held for you to read, stopped requests and random quality checks show up here, each with what to do.")]));
  $("review-done").replaceChildren(...(done.length ? done.map(reviewCard) : [emptyLine("Nothing here yet.", "Items move here once they've been reviewed, or while they wait on someone else.")]));
}
$("review-refresh").addEventListener("click", () => { loadReviews(); refreshCount(); });

// ---- messages to other people (draft, approve, copy) ---------------------
async function loadOutbox() {
  const list = $("outbox-list"); list.replaceChildren();
  const items = await api("/api/outbox");
  if (!items.length) list.append(emptyLine("No drafts yet.", can("draft_message") ? "Describe a message above and the assistant drafts it. A clinician approves it, then a person sends it." : "Drafts from nurses and clinicians wait here for your approval."));
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
let auditFocus = null;
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
    if (auditFocus && [x.seq, x.id, x.hash, x.ts].some((v) => v !== undefined && String(v) === auditFocus)) tr.classList.add("focus-row");
    body.append(tr);
  });
  const hit = body.querySelector(".focus-row");
  if (auditFocus) {
    $("audit-verify").after(Object.assign($("audit-focus") || el("p", "muted"), { id: "audit-focus",
      textContent: hit ? "The highlighted entry is the one the conversation points to." : "That entry is older than the entries shown here." }));
    if (hit) hit.scrollIntoView({ block: "center" });
    auditFocus = null;
  } else if ($("audit-focus")) $("audit-focus").remove();
}
$("audit-refresh").addEventListener("click", loadAudit);

// ---- schedule: front desk and the clinic day ------------------------------
const sched = { day: null, clin: null, data: null, open: null };
const STATUS_WORD = { booked: "Booked", arrived: "Checked in", in_room: "In room", done: "Done",
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
    ? [`${rows.length} appointments`, `${n("booked")} booked`, `${n("arrived")} checked in`, `${n("in_room")} in room`,
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
  who.className = "who-c"; st.className = "st";
  tr.append(el("td", "time", a.time), who, el("td", "visit", a.visit_type), el("td", "with", a.clinician_name), st, act);
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

// ---- calendar: browse appointments and open any patient from them ------------
const cal = { view: null, anchor: null, guessed: false, lastKey: null, today: null, clin: null, names: {}, data: null,
  sel: null, opener: null, req: 0, panelReq: 0 };
const pad2 = (n) => String(n).padStart(2, "0");
const isoOf = (d) => `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
const dateOf = (iso) => { const [y, m, d] = iso.split("-").map(Number); return new Date(y, m - 1, d, 12); };
const addDays = (iso, n) => { const d = dateOf(iso); d.setDate(d.getDate() + n); return isoOf(d); };
const mondayOf = (iso) => addDays(iso, -((dateOf(iso).getDay() + 6) % 7));
const fmtD = (iso, o) => dateOf(iso).toLocaleDateString(undefined, o);
const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;
const apptPid = (a) => a.patient_id || (a.patient && a.patient.id);
const CAL_ORDER = ["booked", "arrived", "in_room", "done", "cancelled", "no_show"];

// The days to ask for: one day, Monday to Sunday, or the six weeks that cover a month (42 days).
function calRange() {
  const a = cal.anchor;
  if (cal.view === "day") return [a, a];
  if (cal.view === "week") { const m = mondayOf(a); return [m, addDays(m, 6)]; }
  const m = mondayOf(`${a.slice(0, 8)}01`); return [m, addDays(m, 41)];
}
// The server may send clinicians as {id: name}, ["dr_lee", ...] or [{id, name}, ...].
function clinEntries(c) {
  if (Array.isArray(c)) {
    return c.map((x) => (typeof x === "string" ? [x, cal.names[x] || x]
      : [x.id || x.clinician, x.name || x.label || cal.names[x.id || x.clinician] || x.id || x.clinician]));
  }
  return Object.entries(c || {});
}

// The key shows the same tints as the strips, each with its word.
document.querySelector(".cal-key").replaceChildren(...CAL_ORDER.map((st) => {
  const k = el("span", "key-item"); k.append(el("span", `key-sw s-${st}`), el("span", null, STATUS_WORD[st])); return k;
}));
const calMobile = window.matchMedia("(max-width: 720px)");
calMobile.addEventListener("change", () => { if (!$("tab-calendar").hidden) loadCalendar(); });

async function loadCalendar() {
  if (!cal.anchor) { cal.anchor = isoOf(new Date()); cal.guessed = true; }
  if (!cal.view) cal.view = "day";  // opens on today's board (the demo clinic also runs weekends)
  const [from, to] = calRange(); const req = ++cal.req;
  let d;
  try {
    d = await api(`/api/calendar?from=${from}&to=${to}${cal.clin ? `&clinician=${encodeURIComponent(cal.clin)}` : ""}`);
  } catch (err) {
    if (req !== cal.req) return;
    $("cal-error").textContent = `The calendar couldn't load: ${err.message}`;
    $("cal-body").replaceChildren(); $("cal-counts").textContent = ""; return;
  }
  if (req !== cal.req) return;  // a newer request is on its way
  $("cal-error").textContent = "";
  cal.today = d.today || isoOf(new Date());
  if (cal.guessed) {  // first load: use the clinic's "today", not this browser's
    cal.guessed = false;
    if (cal.today !== cal.anchor) {
      cal.anchor = cal.today;
      return loadCalendar();
    }
  }
  cal.data = d;
  const days = d.days || [];
  days.forEach((x) => (x.appointments || []).forEach((a) => { if (a.clinician_name) cal.names[a.clinician] = a.clinician_name; }));
  const clins = clinEntries(d.clinicians);
  if (cal.clin === null) cal.clin = clins.some(([id]) => id === me.user) ? me.user : "";
  fillSelect($("cal-clin"), [["", "All clinicians"], ...clins], cal.clin);
  document.querySelectorAll("[data-cal-view]").forEach((b) => {
    const on = b.dataset.calView === cal.view; b.classList.toggle("on", on); b.setAttribute("aria-pressed", String(on));
  });
  const byDate = {};
  days.forEach((x) => { byDate[x.date] = (x.appointments || []).filter((a) => !cal.clin || a.clinician === cal.clin)
    .sort((p, q) => p.time.localeCompare(q.time)); });
  const inView = cal.view === "month" ? Object.keys(byDate).filter((k) => k.slice(0, 7) === cal.anchor.slice(0, 7)) : Object.keys(byDate);
  const all = inView.flatMap((k) => byDate[k]);
  const n = (st) => all.filter((a) => a.status === st).length;
  $("cal-counts").textContent = all.length
    ? [plural(all.length, "appointment"), n("booked") && `${n("booked")} booked`, n("arrived") && `${n("arrived")} checked in`,
       n("in_room") && `${n("in_room")} in room`, n("done") && `${n("done")} done`,
       n("cancelled") + n("no_show") && `${n("cancelled") + n("no_show")} cancelled or no-show`].filter(Boolean).join(" · ")
    : "No appointments.";
  const body = $("cal-body");
  const key = `${cal.view}|${from}|${cal.clin}|${calMobile.matches}`, fresh = key !== cal.lastKey;
  const oldScroll = body.querySelector(".board-scroll"), keep = oldScroll ? oldScroll.scrollTop : 0;
  cal.lastKey = key;
  body.classList.toggle("fill", cal.view !== "month" && !(cal.view === "week" && calMobile.matches));
  if (cal.view === "day") {
    $("cal-title").textContent = fmtDay(cal.anchor, cal.today);
    body.replaceChildren(calDayBoard(cal.anchor, byDate[cal.anchor] || [], d));
  } else if (cal.view === "week") {
    const [m, s] = [from, to];
    $("cal-title").textContent = m.slice(0, 7) === s.slice(0, 7)
      ? `${fmtD(m, { month: "long", day: "numeric" })} to ${fmtD(s, { day: "numeric" })}, ${s.slice(0, 4)}`
      : `${fmtD(m, { month: "short", day: "numeric" })} to ${fmtD(s, { month: "short", day: "numeric" })}, ${s.slice(0, 4)}`;
    body.replaceChildren(calMobile.matches ? calWeek(from, byDate) : calWeekBoard(from, byDate, d));
  } else {
    $("cal-title").textContent = fmtD(cal.anchor, { month: "long", year: "numeric" });
    body.replaceChildren(calMonth(from, byDate));
  }
  boardScroll(body, fresh, keep);
}

// One appointment in the week grid: time and name, then a status square, the word and the visit type.
function calAppt(a) {
  const b = el("button", `cal-cell cal-appt ${a.status}${cal.sel === a.id ? " on" : ""}`); b.type = "button"; b.dataset.id = a.id;
  const top = el("span", "cal-appt-top"); top.append(el("span", "cal-time", a.time), el("span", "cal-name", a.patient.name || "Patient"));
  const sub = el("span", "cal-appt-sub");
  sub.append(el("span", `state ${STATUS_TONE[a.status] || ""}`, STATUS_WORD[a.status] || a.status), el("span", "cal-visit", a.visit_type));
  b.append(top, sub);
  if (!cal.clin) b.title = `${a.clinician_name || a.clinician}`;
  b.onclick = () => openCalAppt(a, b);
  return b;
}

function calDayHead(iso, tag = "div") {
  const h = el(tag, `cal-cell cal-col-head${iso === cal.today ? " today" : ""}`);
  h.append(el("span", "cal-dow", fmtD(iso, { weekday: "short" })), el("span", "cal-dnum", fmtD(iso, { day: "numeric" })));
  if (iso === cal.today) h.append(el("span", "sr", " (today)"));
  return h;
}

function calWeek(from, byDate) {
  const grid = el("div", "cal-week");
  for (let i = 0; i < 7; i++) {
    const iso = addDays(from, i), list = byDate[iso] || [];
    const col = el("section", `cal-col${iso === cal.today ? " today" : ""}${i > 4 ? " weekend" : ""}`);
    col.setAttribute("aria-label", `${fmtD(iso, { weekday: "long", day: "numeric", month: "long" })}${iso === cal.today ? ", today" : ""}`);
    const head = calDayHead(iso, "button"); head.type = "button"; head.title = "Open this day";
    head.onclick = () => { cal.view = "day"; cal.anchor = iso; loadCalendar(); };
    head.append(el("span", "cal-n", list.length ? String(list.length) : ""));
    col.append(head);
    const ul = el("div", "cal-list");
    if (list.length) list.forEach((a) => ul.append(calAppt(a)));
    else ul.append(el("p", "cal-none", "Nothing booked"));
    col.append(ul); grid.append(col);
  }
  return grid;
}

function calMonth(from, byDate) {
  const grid = el("div", "cal-month");
  const head = el("div", "cal-month-head"); head.setAttribute("aria-hidden", "true");
  for (let i = 0; i < 7; i++) head.append(el("span", null, fmtD(addDays(from, i), { weekday: "short" })));
  const cells = el("div", "cal-month-grid");
  const month = cal.anchor.slice(0, 7);
  for (let i = 0; i < 42; i++) {
    const iso = addDays(from, i), list = byDate[iso] || [];
    const live = list.filter((a) => a.status !== "cancelled" && a.status !== "no_show").length, off = list.length - live;
    const b = el("button", `cal-cell cal-mday${iso.slice(0, 7) !== month ? " out" : ""}${iso === cal.today ? " today" : ""}`);
    b.type = "button";
    b.setAttribute("aria-label", `${fmtD(iso, { weekday: "long", day: "numeric", month: "long" })}${iso === cal.today ? ", today" : ""}: ${list.length ? plural(live, "appointment") : "nothing booked"}${off ? `, ${off} cancelled or no-show` : ""}`);
    const top = el("span", "cal-mtop"); top.append(el("span", "cal-dnum", fmtD(iso, { day: "numeric" })));
    if (off) top.append(el("span", "cal-off", `${off} cancelled`));
    b.append(top);
    if (live) {
      const n = el("span", "cal-mcount"); n.append(el("span", "cal-count", String(live)), el("span", "cal-count-word", live === 1 ? "appointment" : "appointments"));
      b.append(n);
    }
    b.onclick = () => { cal.view = "day"; cal.anchor = iso; loadCalendar(); };
    cells.append(b);
  }
  grid.append(head, cells);
  return grid;
}

// ---- the board: appointments as strips on a ruled time grid ------------------
// One column per clinician (day) or per day (week). Strips sit at their start time, 2.4px a minute,
// so one 20-minute slot is 48px. Status is a tint AND a word on every strip.
const BOARD_PX = 2.4;
const STRIP_WORD = { ...STATUS_WORD };
const toMin = (hhmm) => { const [h, m] = String(hhmm).split(":").map(Number); return h * 60 + m; };
const hhmm = (m) => `${pad2(Math.floor(m / 60))}:${pad2(m % 60)}`;
const nowMin = () => { const d = new Date(); return d.getHours() * 60 + d.getMinutes(); };
const shortName = (name) => {
  const parts = String(name || "Patient").trim().split(/\s+/);
  return parts.length > 1 ? `${parts[0]} ${parts[parts.length - 1][0]}.` : parts[0];
};
const LIVE = (a) => a.status !== "cancelled" && a.status !== "no_show";
const FLAG_PATHS = { check: "M8 3v6M8 12v.5", allergy: "M8 2.5l5.5 10h-11z" };
function flagIcon(kind) {
  const ns = "http://www.w3.org/2000/svg", svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", "0 0 16 16"); svg.setAttribute("aria-hidden", "true");
  const p = document.createElementNS(ns, "path"); p.setAttribute("d", FLAG_PATHS[kind]); svg.append(p); return svg;
}

// Clinic hours and slot length: from the payload when the server sends them, otherwise the clinic defaults.
function boardFrame(d, appts) {
  const hours = (d && d.hours) || ["08:00", "17:00"], slot = (d && d.slot_minutes) || 20;
  let start = toMin(hours[0]), end = toMin(hours[1]);
  appts.forEach((a) => { const m = toMin(a.time); start = Math.min(start, Math.floor(m / 60) * 60); end = Math.max(end, m + slot); });
  return { start, end, slot, lunch: d && d.lunch ? d.lunch.map(toMin) : null };
}

// Side-by-side lanes for appointments that overlap in one column (e.g. a cancelled slot rebooked).
function packLanes(list, slot) {
  const items = list.map((a) => ({ a, s: toMin(a.time), e: toMin(a.time) + slot })).sort((p, q) => p.s - q.s || LIVE(q.a) - LIVE(p.a));
  let cluster = [], end = -1;
  const flush = () => {
    const lanes = [];
    cluster.forEach((it) => { let i = lanes.findIndex((e) => e <= it.s); if (i < 0) { i = lanes.length; lanes.push(0); } lanes[i] = it.e; it.lane = i; });
    cluster.forEach((it) => { it.n = lanes.length; }); cluster = [];
  };
  items.forEach((it) => { if (cluster.length && it.s >= end) flush(); cluster.push(it); end = Math.max(end, it.e); });
  flush();
  return items;
}

function strip(it, f, withClin) {
  const a = it.a, p = a.patient || {};
  const b = el("button", `cal-cell strip s-${a.status}${it.n > 1 ? " split" : ""}${cal.sel === a.id ? " on" : ""}`);
  b.type = "button"; b.dataset.id = a.id; b.setAttribute("aria-pressed", String(cal.sel === a.id));
  b.style.top = `${(it.s - f.start) * BOARD_PX + 1}px`;
  b.style.height = `${f.slot * BOARD_PX - 3}px`;
  b.style.left = `calc(4px + (100% - 8px) * ${it.lane} / ${it.n})`;
  b.style.width = `calc((100% - 8px) / ${it.n} - ${it.n > 1 ? 3 : 0}px)`;
  const word = STRIP_WORD[a.status] || a.status;
  const flags = [];
  if (p.attention) flags.push(["check", String(p.attention), `${p.attention} thing${p.attention > 1 ? "s" : ""} to check`]);
  if (Array.isArray(p.allergies) && p.allergies.length) flags.push(["allergy", "", `Allergy: ${p.allergies.join(", ")}`]);
  b.setAttribute("aria-label", [`${a.time}, ${p.name || "Patient"}`, a.visit_type, withClin ? `with ${a.clinician_name || a.clinician}` : "",
    word, ...flags.map((x) => x[2])].filter(Boolean).join(", "));
  const body = el("span", "body");
  body.append(el("span", "name", shortName(p.name)), el("span", "meta", `${word} · ${a.visit_type}${withClin ? ` · ${a.clinician_name || a.clinician}` : ""}`));
  b.append(el("span", "t", a.time), body);
  if (flags.length) {
    const fl = el("span", "flags"); fl.setAttribute("aria-hidden", "true");
    flags.forEach(([k, n, title]) => { const s = el("span", `flag ${k}`); s.title = title; s.append(flagIcon(k)); if (n) s.append(el("span", null, n)); fl.append(s); });
    b.append(fl);
  }
  b.onclick = () => (cal.sel === a.id ? closeCalPanel() : openCalAppt(a, b));
  return b;
}

// cols: [{ key, title, today, list, capacity, onHead }]; nowCols: keys of columns that get the now line.
function board(cols, f, opts) {
  const wrap = el("div", `board${opts.narrow ? " narrow" : ""}`); wrap.style.setProperty("--cols", cols.length);
  const head = el("div", "board-head"); head.append(el("span", "board-corner"));
  cols.forEach((c) => {
    const live = c.list.filter(LIVE).length, pct = Math.min(100, Math.round((live / Math.max(1, c.capacity)) * 100));
    const h = el(c.onHead ? "button" : "div", `col-head${c.today ? " today" : ""}${c.onHead ? " cal-cell" : ""}`);
    if (c.onHead) { h.type = "button"; h.onclick = c.onHead; h.title = "Open this day"; }
    const top = el("span", "col-head-top"); top.append(el("span", "col-title", c.title), el("span", "cap", `${plural(live, "visit")} · ${pct}% booked`));
    const g = el("span", `gauge${pct >= 85 ? " full" : ""}`); g.setAttribute("role", "meter");
    g.setAttribute("aria-valuemin", "0"); g.setAttribute("aria-valuemax", "100"); g.setAttribute("aria-valuenow", String(pct));
    g.setAttribute("aria-label", `${c.label || c.title}: ${pct}% of slots booked`);
    const fill = el("i"); fill.style.width = `${pct}%`; g.append(fill);
    h.append(top, g); head.append(h);
  });
  const scroll = el("div", "board-scroll");
  const grid = el("div", "board-grid"); grid.style.height = `${(f.end - f.start) * BOARD_PX + 12}px`;
  const hrs = el("div", "hours"); hrs.setAttribute("aria-hidden", "true");
  for (let m = Math.ceil(f.start / 60) * 60; m <= f.end; m += 60) {
    const s = el("span", "hour-label", hhmm(m)); s.style.top = `${Math.max(8, (m - f.start) * BOARD_PX)}px`; hrs.append(s);
  }
  grid.append(hrs);
  cols.forEach((c) => {
    const lane = el("div", `lane${c.today ? " today" : ""}`); lane.setAttribute("role", "group"); lane.setAttribute("aria-label", `${c.label || c.title} schedule`);
    for (let m = f.start; m < f.end; m += f.slot) {
      const r = el("span", `rule${m % 60 === 0 ? " hour" : ""}`); r.style.top = `${(m - f.start) * BOARD_PX}px`; lane.append(r);
    }
    if (f.lunch) {
      const l = el("div", "lunch"); l.style.top = `${(f.lunch[0] - f.start) * BOARD_PX}px`; l.style.height = `${(f.lunch[1] - f.lunch[0]) * BOARD_PX}px`;
      l.append(el("span", null, "Lunch")); lane.append(l);
    }
    packLanes(c.list, f.slot).forEach((it) => lane.append(strip(it, f, opts.withClin)));
    if (!c.list.length) lane.append(el("span", "lane-empty", "Nothing booked"));
    if (opts.nowCols.includes(c.key) && !opts.span) lane.append(nowLine(f, false));
    grid.append(lane);
  });
  if (opts.span && opts.nowCols.length) grid.append(nowLine(f, true));
  if (!opts.span && opts.nowCols.length) grid.append(nowTag(f));
  scroll.append(grid); wrap.append(head, scroll);
  return wrap;
}
// The red "now" line: across every column (day), or only today's column with the time in the gutter (week).
function nowLine(f, span) {
  const n = el("div", `now-line${span ? " span" : ""}`); n.dataset.start = f.start; n.dataset.end = f.end;
  if (span) n.append(el("span", "now-tag"));
  return n;
}
function nowTag(f) { const t = el("span", "now-tag gutter"); t.dataset.start = f.start; t.dataset.end = f.end; return t; }
function updateNow() {
  const m = nowMin();
  document.querySelectorAll("#cal-body .now-line, #cal-body .now-tag.gutter").forEach((n) => {
    const st = +n.dataset.start, en = +n.dataset.end;
    n.hidden = m < st || m > en;
    n.style.top = `${(Math.min(Math.max(m, st), en) - st) * BOARD_PX}px`;
    if (n.classList.contains("now-line")) n.setAttribute("aria-label", `Now, ${hhmm(m)}`);
  });
  document.querySelectorAll("#cal-body .now-tag").forEach((t) => { t.textContent = hhmm(m); });
  // the hour label under the now tag steps aside
  document.querySelectorAll("#cal-body .board-grid").forEach((g) => {
    const n = g.querySelector(".now-line:not([hidden]), .now-tag.gutter:not([hidden])"), y = n ? parseFloat(n.style.top) : null;
    g.querySelectorAll(".hour-label").forEach((l) => { l.style.visibility = y !== null && Math.abs(parseFloat(l.style.top) - y) < 14 ? "hidden" : ""; });
  });
}
setInterval(() => { if (me && !$("tab-calendar").hidden) updateNow(); }, 30000);

function calDayBoard(iso, list, d) {
  const clins = clinEntries(d.clinicians).filter(([id]) => !cal.clin || id === cal.clin);
  const f = boardFrame(d, list);
  const capacity = Math.floor((f.end - f.start) / f.slot);
  const extra = list.filter((a) => !clins.some(([id]) => id === a.clinician));  // a clinician not in the list
  const cols = clins.map(([id, name]) => ({ key: id, title: name, label: name, list: list.filter((a) => a.clinician === id), capacity }));
  if (extra.length) cols.push({ key: "other", title: "Other", list: extra, capacity });
  return board(cols, f, { nowCols: iso === cal.today ? cols.map((c) => c.key) : [], span: true, withClin: false });
}

function calWeekBoard(from, byDate, d) {
  const days = Array.from({ length: 7 }, (_, i) => addDays(from, i));
  const all = days.flatMap((x) => byDate[x] || []);
  const f = boardFrame(d, all);
  const nClin = cal.clin ? 1 : Math.max(1, clinEntries(d.clinicians).length);
  const capacity = Math.floor((f.end - f.start) / f.slot) * nClin;
  const cols = days.map((iso) => ({ key: iso, today: iso === cal.today, list: byDate[iso] || [], capacity,
    title: `${fmtD(iso, { weekday: "short" })} ${fmtD(iso, { day: "numeric" })}`,
    label: `${fmtD(iso, { weekday: "long", day: "numeric", month: "long" })}${iso === cal.today ? ", today" : ""}`,
    onHead: () => { cal.view = "day"; cal.anchor = iso; loadCalendar(); } }));
  return board(cols, f, { nowCols: days.includes(cal.today) ? [cal.today] : [], span: false, withClin: !cal.clin, narrow: true });
}

// Open at the present moment with a little of the past above it; otherwise at the first visit.
function boardScroll(body, fresh, keep) {
  const sc = body.querySelector(".board-scroll"); if (!sc) return;
  if (!fresh) { sc.scrollTop = keep; return; }
  updateNow();
  const now = body.querySelector(".now-line:not([hidden])");
  const first = body.querySelector(".strip");
  sc.scrollTop = now ? Math.max(0, now.offsetTop - 120) : first ? Math.max(0, first.offsetTop - 24) : 0;
}

// ---- the side panel: appointment, full record and every change -------------
function markCalSel() {
  document.querySelectorAll("#cal-body [data-id]").forEach((b) => {
    b.classList.toggle("on", b.dataset.id === cal.sel);
    if (b.classList.contains("strip")) b.setAttribute("aria-pressed", String(b.dataset.id === cal.sel));
  });
}

async function openCalAppt(a, opener) {
  cal.sel = a.id; cal.opener = opener; markCalSel();
  const req = ++cal.panelReq, pid = apptPid(a), p = a.patient || {};
  $("tab-calendar").classList.add("with-panel"); $("cal-panel").hidden = false;
  $("cal-panel-title").textContent = p.name || "Appointment";
  $("cal-panel-when").textContent = `${fmtD(a.date, { weekday: "long", day: "numeric", month: "long", year: "numeric" })}, ${a.time} to ${hhmm(toMin(a.time) + ((cal.data && cal.data.slot_minutes) || 20))}`;
  const dl = $("cal-appt"); dl.replaceChildren();
  const fact = (k, v) => { if (v === undefined || v === null || v === "") return; const dd = el("dd"); if (v instanceof Node) dd.append(v); else dd.textContent = v; dl.append(el("dt", null, k), dd); };
  fact("Status", el("span", `state ${STATUS_TONE[a.status] || ""}`, STATUS_WORD[a.status] || a.status));
  fact("Visit", a.visit_type);
  fact("With", a.clinician_name || a.clinician);
  if (a.cancel_reason) fact("Reason", a.cancel_reason);
  if (a.reminder && a.reminder.sent_at) fact("Reminder", `sent by ${a.reminder.sent_by} at ${a.reminder.sent_at.replace("T", " ").slice(0, 16)}`);
  const acts = $("cal-actions"); acts.replaceChildren();
  if (pid && can("view_patients")) {
    const open = el("button", "small-btn", "Open in Patients"); open.type = "button";
    open.onclick = () => calToPatients(pid);
    acts.append(open);
    if (can("chat")) {
      const ask = el("button", "ghost small-btn", "Ask the assistant about this patient"); ask.type = "button";
      ask.onclick = () => calToPatients(pid, true);
      acts.append(ask);
    }
  }
  const rec = $("cal-record"), changes = $("cal-changes");
  changes.hidden = true; $("cal-history").replaceChildren();
  $("cal-panel").focus({ preventScroll: true }); $("cal-panel").scrollTop = 0;
  if (!pid) { rec.replaceChildren(); return; }
  if (can("view_patients")) {
    rec.replaceChildren(el("p", "muted cal-loading", "Opening the record..."));
    api(`/api/patients/${encodeURIComponent(pid)}`).then((full) => {
      if (req !== cal.panelReq) return;
      const core = el("div", "record cal-rec"); rec.replaceChildren(core);
      renderRecord(full, core, (q) => calToPatients(pid, true, q));
    }).catch((err) => { if (req === cal.panelReq) rec.replaceChildren(el("p", "error", err.message)); });
  } else {  // front desk: only the allow-listed details that came with the appointment
    const box = el("div", "cal-rec"); const fd = el("dl", "facts");
    [["Insurance", p.insurance && p.insurance.plan], ["Prefers", p.preferred_contact], ["Language", p.language]]
      .forEach(([k, v]) => { if (v) fd.append(el("dt", null, k), el("dd", null, v)); });
    box.append(el("h3", null, "Patient"), fd, el("p", "muted", "Clinical records aren't available to the front desk."));
    rec.replaceChildren(box);
  }
  api(`/api/patients/${encodeURIComponent(pid)}/history`).then((items) => {
    if (req !== cal.panelReq || !Array.isArray(items)) return;
    $("cal-history").replaceChildren(...(items.length ? items.map(historyItem) : [el("li", "muted", "No changes recorded yet.")]));
    changes.hidden = false;
  }).catch(() => { changes.hidden = true; });  // 403 for roles that can't see it: leave the section out
}

function closeCalPanel(restore = true) {
  cal.panelReq++;
  $("cal-panel").hidden = true; $("tab-calendar").classList.remove("with-panel");
  const id = cal.sel; cal.sel = null; markCalSel();
  if (restore) {
    const back = cal.opener && cal.opener.isConnected ? cal.opener : id && document.querySelector(`#cal-body [data-id="${CSS.escape(id)}"]`);
    if (back) back.focus();
  }
  cal.opener = null;
}

// Jump to the Patients tab with this patient open; optionally put the cursor in the chat, or ask straight away.
async function calToPatients(pid, chat = false, question = null) {
  closeCalPanel(false);
  showTab("patients");
  await openPatient(pid);
  if (!currentPatient || currentPatient.id !== pid) return;
  if (question) askPatient(question);
  else if (chat) { $("pt-chat-input").focus(); $("pt-chat-pane").scrollIntoView({ block: "nearest" }); }
}

$("cal-close").addEventListener("click", () => closeCalPanel());
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !$("cal-panel").hidden && !$("tab-calendar").hidden && !$("reg-dialog").open) { e.preventDefault(); closeCalPanel(); }
});
const calStep = (dir) => {
  if (cal.view === "day") cal.anchor = addDays(cal.anchor, dir);
  else if (cal.view === "week") cal.anchor = addDays(cal.anchor, 7 * dir);
  else { const d = dateOf(`${cal.anchor.slice(0, 8)}01`); d.setMonth(d.getMonth() + dir); cal.anchor = isoOf(d); }
  loadCalendar();
};
$("cal-prev").addEventListener("click", () => calStep(-1));
$("cal-next").addEventListener("click", () => calStep(1));
$("cal-today").addEventListener("click", () => { cal.anchor = cal.today || isoOf(new Date()); loadCalendar(); });
document.querySelectorAll("[data-cal-view]").forEach((b) => b.addEventListener("click", () => {
  cal.view = b.dataset.calView; loadCalendar();
}));
$("cal-clin").addEventListener("change", (e) => { cal.clin = e.target.value; loadCalendar(); });

// ---- local database status (Home) --------------------------------------------
async function loadDbStatus() {
  const line = $("db-status");
  let d;
  try { d = await api("/api/db/status"); } catch { line.hidden = true; return; }
  if (!d || typeof d.patients !== "number") { line.hidden = true; return; }
  const ok = d.chain_ok !== false;
  line.replaceChildren(icon(ok ? "ok" : "blocked"), el("span", null,
    `Local database: ${plural(d.patients, "patient")}, ${plural(d.appointments || 0, "appointment")}, ${plural(d.changes || 0, "tracked change")}, ${ok ? "chain verified" : "chain check failed"}`));
  line.classList.toggle("bad", !ok);
  line.title = d.file ? `${d.engine || "database"}: ${d.file}` : "";
  line.hidden = false;
}

// ---- conversations: every question asked of the assistant ---------------------
const conv = { items: [], users: new Set(), patients: new Set(), names: {}, open: null, req: 0 };
const CONV_TIER = { green: "Ready to read", amber: "Check first", red: "Stopped", error: "Not sent", redirect: "Redirected" };
fillSelect($("conv-tier"), [["", "Any result"], ...Object.entries(CONV_TIER)]);
const convTier = (t) => el("span", `tier ${t === "redirect" ? "amber" : t}`, CONV_TIER[t] || t || "unknown");
const shortWhen = (iso) => (iso ? iso.replace("T", " ").slice(0, 16) : "");

async function loadConversations() {
  const user = $("conv-user").value, pid = $("conv-patient").value, req = ++conv.req;
  const q = new URLSearchParams({ limit: "100" });
  if (user) q.set("user", user);
  if (pid) q.set("patient_id", pid);
  let d;
  try { d = await api(`/api/conversations?${q}`); }
  catch (err) { if (req === conv.req) { $("conv-error").textContent = `Conversations couldn't load: ${err.message}`; $("conv-list").replaceChildren(); } return; }
  if (req !== conv.req) return;
  $("conv-error").textContent = "";
  if (can("view_patients") && !Object.keys(conv.names).length) {
    (await api("/api/patients").catch(() => [])).forEach((p) => { conv.names[p.id] = p.name; });
  }
  conv.items = Array.isArray(d.items) ? d.items : [];
  conv.items.forEach((c) => { if (c.user) conv.users.add(c.user); if (c.patient_id) conv.patients.add(c.patient_id); });
  $("conv-sub").textContent = d.can_see_all
    ? "Every question anyone asked the assistant and what it answered, newest first."
    : "Your questions to the assistant and what it answered, newest first.";
  $("conv-user").hidden = !d.can_see_all;
  fillSelect($("conv-user"), [["", "Everyone"], ...[...conv.users].sort().map((u) => [u, u])], user);
  fillSelect($("conv-patient"), [["", "Any patient"], ...[...conv.patients].map((id) => [id, conv.names[id] || id])
    .sort((a, b) => a[1].localeCompare(b[1]))], pid);
  drawConversations();
}

function drawConversations() {
  const tier = $("conv-tier").value;
  const rows = conv.items.filter((c) => !tier || c.tier === tier);
  const list = $("conv-list");
  if (!rows.length) { list.replaceChildren(conv.items.length ? el("p", "muted conv-empty", "Nothing matches these filters.")
    : emptyLine("No conversations yet.", "Every question asked in Ask a question, beside a patient's record or at the front desk is logged here with its answer.")); return; }
  list.replaceChildren(...rows.map((c) => {
    const box = el("div", `conv${conv.open === c.id ? " open" : ""}`);
    const b = el("button", "conv-row"); b.type = "button"; b.setAttribute("aria-expanded", String(conv.open === c.id));
    const pname = c.patient_id ? conv.names[c.patient_id] || c.patient_id : "";
    b.append(el("span", "conv-when", shortWhen(c.at)),
      el("span", "conv-who", `${c.user || "?"}${c.role ? ` · ${c.role.replace("_", " ")}` : ""}`),
      el("span", `conv-pt${pname ? "" : " none"}`, pname || "General"),
      el("span", "conv-q", c.question || ""), convTier(c.tier));
    b.onclick = () => { conv.open = conv.open === c.id ? null : c.id; drawConversations(); };
    box.append(b);
    if (conv.open === c.id) box.append(convDetail(c));
    return box;
  }));
}

function convDetail(c) {
  const d = el("div", "conv-detail");
  d.append(el("div", "label", "Question"), el("div", "quote", c.question || ""));
  d.append(el("div", "label", "Answer"), el("div", "quote", c.answer
    || (c.answer_held ? "Held: shown once the asker has read the warnings in Needs review." : c.tier === "red" ? "Not shown: stopped for review." : "No answer.")));
  if (c.reasons && c.reasons.length) d.append(el("div", "label", "Why it got this label"), reasonList(c.reasons));
  const facts = el("dl", "facts");
  const fact = (k, v) => { if (v !== undefined && v !== null && v !== "") facts.append(el("dt", null, k), el("dd", null, String(v))); };
  fact("Asked by", `${c.user}${c.role ? ` (${c.role.replace("_", " ")})` : ""}, ${shortWhen(c.at)} UTC`);
  fact("Kind", c.kind);
  fact("Model", c.model);
  if (typeof c.duration_ms === "number") fact("Time taken", c.duration_ms >= 1000 ? `${(c.duration_ms / 1000).toFixed(1)} s` : `${c.duration_ms} ms`);
  fact("What the model was given", c.context_summary);
  d.append(el("div", "label", "Details"), facts);
  d.append(el("div", "label", "Changes made after this answer"));
  const ch = c.changes || [];
  d.append(ch.length ? (() => { const ol = el("ol", "history"); ch.forEach((h) => ol.append(historyItem(h))); return ol; })()
    : el("p", "muted", "Nothing was changed after this answer."));
  const acts = el("div", "actions");
  if (c.audit_ref && can("view_audit")) {  // {event, ts, hash} of the audit entry for this answer
    const a = el("button", "ghost small-btn", "Show in the Audit log"); a.type = "button";
    a.onclick = () => { auditFocus = String(typeof c.audit_ref === "object" ? c.audit_ref.hash || c.audit_ref.ts : c.audit_ref); showTab("audit"); };
    acts.append(a);
  }
  if (c.review_id && can("chat,review_red,qa_review")) {
    const r = el("button", "ghost small-btn", "Open in Needs review"); r.type = "button"; r.onclick = () => showTab("review"); acts.append(r);
  }
  if (c.patient_id && can("view_patients")) {
    const p = el("button", "ghost small-btn", "Open patient"); p.type = "button";
    p.onclick = () => { showTab("patients"); openPatient(c.patient_id); }; acts.append(p);
  }
  if (acts.children.length) d.append(acts);
  return d;
}
["conv-user", "conv-patient"].forEach((id) => $(id).addEventListener("change", () => { conv.open = null; loadConversations(); }));
$("conv-tier").addEventListener("change", drawConversations);
$("conv-refresh").addEventListener("click", loadConversations);

// ---- network: what the app talks to, and that it can't reach the internet ------
// Outbound internet in words. "unknown" means the public probe is off by design: the app never calls out.
const EGRESS_WORD = { blocked: "no outbound internet", allowed: "outbound internet ALLOWED", unknown: "outbound internet not tested (the app never calls out)" };
const NET_TONE = { up: "green", down: "red", disabled: "off", unknown: "amber" };
const NET_WORD = { up: "Up", down: "Down", disabled: "Disabled", unknown: "Unknown" };
const netState = (st) => el("span", `state ${NET_TONE[st] || "amber"}`, NET_WORD[st] || st || "Unknown");
document.querySelector(".net-key").replaceChildren(...Object.keys(NET_WORD).map((k) => netState(k)));
let netReq = 0;

async function loadNetwork() {
  const req = ++netReq;
  let d;
  try { d = await api("/api/network"); }
  catch (err) { if (req === netReq) $("net-error").textContent = `Network status couldn't load: ${err.message}`; return; }
  if (req !== netReq) return;
  $("net-error").textContent = "";
  const nodes = d.nodes || [], edges = d.edges || [], label = {};
  nodes.forEach((n) => { label[n.id] = n.label || n.id; });
  const up = nodes.filter((n) => n.status === "up").length;
  const eg = (d.egress || {}).outbound_internet || "unknown";
  $("net-sub").textContent = `${up} of ${plural(nodes.length, "service")} up · ${EGRESS_WORD[eg] || `outbound internet ${eg}`}.`;
  $("net-checked").textContent = d.checked_at ? `Checked ${whenText(d.checked_at)} · refreshes every 10 s` : "Refreshes every 10 s";
  $("net-diagram").replaceChildren(netDiagram(nodes, edges));
  const td = (t, cls) => el("td", cls, t === undefined || t === null ? "" : String(t));
  $("net-nodes").replaceChildren(...nodes.map((n) => {
    const tr = el("tr"); const s = el("td"); s.append(netState(n.status));
    const name = el("td"); name.append(el("strong", null, label[n.id]), el("div", "muted", n.kind || ""));
    tr.append(name, td(n.address, "mono"), s, td(n.detail, "muted")); return tr;
  }));
  $("net-edges").replaceChildren(...(edges.length ? edges.map((e) => {
    const tr = el("tr"); const s = el("td"); s.append(netState(e.status));
    tr.append(td(label[e.from] || e.from), td(label[e.to] || e.to), td(e.protocol, "mono"), td(e.purpose, "muted"), s,
      td(e.last_seen ? whenText(e.last_seen) : "never", "muted"), td(e.calls_24h ?? "", "num")); return tr;
  }) : [(() => { const tr = el("tr"); const c = td("No links reported.", "muted"); c.colSpan = 7; tr.append(c); return tr; })()]));
  // egress
  const box = $("net-egress"); box.className = `net-egress ${eg === "unknown" ? "untested" : eg}`;
  box.replaceChildren(icon(eg === "allowed" ? "blocked" : "ok"), el("span", null,
    eg === "blocked" ? "No outbound internet from the app" : eg === "allowed" ? "Outbound internet is allowed" : "Not tested: the app never calls out"));
  const checks = (d.egress || {}).checks || [];
  $("net-checks").replaceChildren(...(checks.length ? checks.map((c) => {
    const li = el("li"); li.append(icon(c.ok ? "ok" : "blocked"));
    const t = el("div"); t.append(el("strong", null, c.name), el("div", "muted", c.detail || "")); li.append(t); return li;
  }) : [el("li", "muted", "No checks reported.")]));
  const calls = d.recent_calls || [];
  $("net-calls").replaceChildren(...(calls.length ? calls.map((c) => {
    const tr = el("tr"); const r = el("td"); r.append(el("span", `state ${c.ok ? "green" : "red"}`, c.ok ? "OK" : "Failed"));
    tr.append(td(whenText(c.at), "muted nowrap"), td(label[c.from] || c.from), td(label[c.to] || c.to), td(c.what), r, td(c.ms ?? "", "num")); return tr;
  }) : [(() => { const tr = el("tr"); const c = td("No calls yet.", "muted"); c.colSpan = 6; tr.append(c); return tr; })()]));
}

// Columns by distance from the nodes nothing points to (the staff browser first), drawn as boxes and curves.
function netDiagram(nodes, edges) {
  const ns = "http://www.w3.org/2000/svg";
  const mk = (tag, attrs, text) => { const e = document.createElementNS(ns, tag); Object.entries(attrs).forEach(([k, v]) => e.setAttribute(k, v)); if (text !== undefined) e.textContent = text; return e; };
  const ids = nodes.map((n) => n.id), depth = {};
  const incoming = new Set(edges.map((e) => e.to));
  let frontier = ids.filter((id) => !incoming.has(id));
  if (!frontier.length && ids.length) frontier = [ids[0]];
  frontier.forEach((id) => { depth[id] = 0; });
  while (frontier.length) {
    const next = [];
    frontier.forEach((id) => edges.filter((e) => e.from === id).forEach((e) => {
      if (depth[e.to] === undefined && ids.includes(e.to)) { depth[e.to] = depth[id] + 1; next.push(e.to); }
    }));
    frontier = next;
  }
  const maxD = Math.max(0, ...Object.values(depth));
  ids.forEach((id) => { if (depth[id] === undefined) depth[id] = maxD + 1; });
  const cols = []; ids.forEach((id) => { (cols[depth[id]] = cols[depth[id]] || []).push(id); });
  const W = 200, H = 54, GX = 130, GY = 18, PAD = 12;
  const tallest = Math.max(1, ...cols.map((c) => (c || []).length));
  const height = PAD * 2 + tallest * H + (tallest - 1) * GY, width = PAD * 2 + cols.length * W + (cols.length - 1) * GX;
  const pos = {};
  cols.forEach((c, i) => (c || []).forEach((id, j) => {
    const colH = c.length * H + (c.length - 1) * GY;
    pos[id] = { x: PAD + i * (W + GX), y: (height - colH) / 2 + j * (H + GY) };
  }));
  const svg = mk("svg", { viewBox: `0 0 ${width} ${height}`, class: "net-svg", role: "img",
    "aria-label": `Diagram: ${edges.map((e) => `${e.from} to ${e.to} over ${e.protocol || "?"}, ${e.status}`).join("; ")}` });
  svg.style.minWidth = `${Math.min(width, 640)}px`;
  edges.forEach((e) => {
    const a = pos[e.from], b = pos[e.to]; if (!a || !b) return;
    let d, lx, ly;
    if (Math.abs(a.x - b.x) < 1) {  // same column: bow out to the right
      const x = a.x + W, y1 = a.y + H / 2, y2 = b.y + H / 2;
      d = `M${x} ${y1} C${x + 60} ${y1}, ${x + 60} ${y2}, ${x} ${y2}`; lx = x + 50; ly = (y1 + y2) / 2;
    } else {
      const [p, q] = a.x < b.x ? [a, b] : [b, a];
      const x1 = p.x + W, y1 = p.y + H / 2, x2 = q.x, y2 = q.y + H / 2, mx = (x1 + x2) / 2;
      d = `M${x1} ${y1} C${mx} ${y1}, ${mx} ${y2}, ${x2} ${y2}`; lx = x2 - 8; ly = y2 - 6;
    }
    const g = mk("g", { class: `net-edge ${e.status || "unknown"}` });
    g.append(mk("path", { d }), mk("text", { x: lx, y: ly, "text-anchor": "end", class: "net-proto" }, e.protocol || ""));
    const t = mk("title", {}, `${e.from} → ${e.to}: ${e.purpose || ""} (${e.status})`); g.append(t);
    svg.append(g);
  });
  nodes.forEach((n) => {
    const p = pos[n.id]; const g = mk("g", { class: `net-node ${n.status || "unknown"}`, transform: `translate(${p.x} ${p.y})` });
    g.append(mk("rect", { width: W, height: H, rx: 6, class: "box" }), mk("rect", { x: 12, y: 15, width: 8, height: 8, rx: 2, class: "mark" }),
      mk("text", { x: 28, y: 23, class: "net-label" }, (n.label || n.id).slice(0, 26)),
      mk("text", { x: 12, y: 41, class: "net-addr" }, (n.address || n.kind || "").slice(0, 30)),
      mk("title", {}, `${n.label || n.id}: ${NET_WORD[n.status] || n.status}${n.detail ? `. ${n.detail}` : ""}`));
    svg.append(g);
  });
  return svg;
}
$("net-refresh").addEventListener("click", loadNetwork);
setInterval(() => { if (me && !document.hidden && !$("tab-network").hidden) loadNetwork(); }, 10000);

// ---- live: other people's changes show up without a reload -----------------
setInterval(() => {
  if (!me || document.hidden) return;
  const busy = document.activeElement && /INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName);
  const tab = document.querySelector(".tab:not([hidden])");
  if (!tab || busy || $("reg-dialog").open) return;
  if (tab.id === "tab-schedule" && !sched.open) loadSchedule();
  if (tab.id === "tab-calendar" && !$("cal-body").contains(document.activeElement)) loadCalendar();
  if (tab.id === "tab-home") loadHome();
  if (tab.id === "tab-conversations" && !conv.open) loadConversations();
  if (tab.id === "tab-patients") { loadPatients(); if (currentPatient) loadHistory(currentPatient.id); }
  refreshCount();
}, 15000);

start();
