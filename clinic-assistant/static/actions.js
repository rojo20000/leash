// Assistant actions (2.12): commands typed in the assistant boxes become proposal cards.
// Nothing changes until a person with the right role presses Approve (server: app/actions.py).
// Self-contained: uses only api(), el(), $() and `me` from app.js, and listens to existing forms.
(() => {
  "use strict";
  // Loose client-side check; the server's parser decides. Questions fall through to the normal assistant.
  const HINT = /\b(reschedule|move|push|cancel|book|remind|reminder|fill|waitlist|hand-?over|referr?al|refer)\b|\b(change|update|set|correct|add|remove|stop)\b.{0,60}\b(phone|number|mobile|address|contact|language|insurance|plan|member id|allerg\w*|medication|medicine|meds?|condition|dose|result)\b/i;
  const QUESTION = /^\s*(what|who|when|where|why|how|is|are|does|do|which|should|summari[sz]e|explain)\b/i;
  const FORMS = {
    "chat-form": { input: "chat-input", log: "chat-log" },
    "pt-chat-form": { input: "pt-chat-input", log: "pt-chat-log", patient: true },
    "desk-form": { input: "desk-input", log: "desk-log" },
  };
  const STATUS = {
    pending: ["Waiting for approval", "green"], held: ["Held: check the reasons first", "amber"],
    blocked: ["Blocked by the safety check", "red"], approved: ["Approved and applied", "green"],
    rejected: ["Rejected, nothing changed", "muted"],
  };
  let bypass = false;

  const node = (tag, cls, text) => el(tag, cls, text);
  const chip = (word, tone) => { const s = node("span", `tier ${tone}`, word); return s; };
  const scroll = (n) => n.scrollIntoView && n.scrollIntoView({ block: "nearest" });

  async function propose(log, message, ctx, hints) {
    const wait = node("div", "msg ai pending act-wait");
    wait.append(node("span", "spinner"), node("span", null, "Working out the action and running the safety check…"));
    log.append(wait); scroll(wait);
    try {
      const body = { message, hints: hints || {} };
      if (ctx) body.patient_id = ctx;
      const r = await api("/api/actions/propose", body);
      wait.remove();
      return r;
    } catch (e) {
      wait.remove();
      const m = errorCard(e.message); log.append(m); scroll(m);
      return { is_action: true };
    }
  }

  function shell(kindText, tone) {
    const m = node("div", "msg ai act-card");
    if (tone === "amber") m.classList.add("held");
    if (tone === "red") m.classList.add("blocked");
    const head = node("div", "msg-head");
    head.append(chip("Assistant action", tone === "muted" ? "green" : tone), node("span", null, kindText));
    const body = node("div", "msg-body act-body");
    m.append(head, body);
    return { m, body };
  }

  function errorCard(text) {
    const { m, body } = shell("Can't do that", "amber");
    body.append(node("p", null, text));
    return m;
  }

  function clarifyCard(r, log, message, ctx) {
    const { m, body } = shell("Needs a choice", "amber");
    body.append(node("p", null, r.question));
    if (!r.options || !r.options.length) {
      body.append(node("p", "muted", "Type the command again with more detail."));
      return m;
    }
    const list = node("div", "act-options");
    r.options.forEach((o) => {
      const b = node("button", "ghost small-btn", o.label); b.type = "button";
      b.addEventListener("click", async () => {
        list.querySelectorAll("button").forEach((x) => { x.disabled = true; });
        b.classList.add("act-picked");
        await render(await propose(log, message, ctx, o.hints), log, message, ctx);
      });
      list.append(b);
    });
    body.append(list);
    return m;
  }

  function proposalCard(p, onDone) {
    const [word, tone] = STATUS[p.status] || [p.status, "muted"];
    const { m, body } = shell(p.label, p.tier === "red" ? "red" : p.tier === "amber" ? "amber" : "green");
    m.dataset.proposal = p.id;
    const top = node("p", "act-summary"); top.append(node("strong", null, p.summary));
    body.append(top);
    if (p.changes && p.changes.length) {
      const t = node("table", "act-changes"); const tb = node("tbody");
      p.changes.forEach((c) => {
        const tr = node("tr");
        tr.append(node("th", null, c.field.replace("_", " ")), node("td", "act-before", String(c.before)),
                  node("td", "act-arrow", "→"), node("td", "act-after", String(c.after)));
        tb.append(tr);
      });
      t.append(tb); body.append(t);
    }
    let draftBox = null;
    if (p.draft) {
      draftBox = node("textarea", "act-draft"); draftBox.value = p.draft; draftBox.readOnly = true;
      draftBox.rows = Math.min(10, p.draft.split("\n").length + 1);
      draftBox.setAttribute("aria-label", "Draft text");
      body.append(draftBox);
    }
    if (p.reasons && p.reasons.length) {
      const ul = node("ul", "reasons"); p.reasons.forEach((x) => ul.append(node("li", null, x))); body.append(ul);
    }
    const st = node("p", "act-status");
    st.append(chip(word, tone === "muted" ? "act-muted" : tone));
    const who = p.decided_by ? ` by ${p.decided_by}` : ` · proposed by ${p.proposed_by}`;
    st.append(node("span", "muted", who + (p.result && p.result.message ? ` · ${p.result.message}` : "")));
    body.append(st);
    if (p.result && p.result.text) body.append(node("p", "act-result", p.result.text));
    if (p.status === "pending" || p.status === "held") {
      if (!p.can_approve) body.append(node("p", "muted act-note", `Waiting for someone whose role can ${p.permission.replace("_", " ")}. It is listed for them on Home.`));
      const bar = node("div", "act-bar");
      const msg = node("p", "error act-msg"); msg.setAttribute("role", "alert");
      let pin = null, confirm = null;
      if (p.can_approve && p.needs_pin) {
        const lab = node("label", "act-pin", "PIN ");
        pin = node("input", "pin"); pin.type = "password"; pin.inputMode = "numeric"; pin.maxLength = 4;
        pin.autocomplete = "off"; pin.placeholder = "••••"; lab.append(pin); bar.append(lab);
      }
      if (p.can_approve && p.status === "held") {
        const lab = node("label", "act-confirm");
        confirm = node("input"); confirm.type = "checkbox";
        lab.append(confirm, document.createTextNode(" I read the reasons")); bar.append(lab);
      }
      const decide = async (decision, btn) => {
        btn.disabled = true; msg.textContent = "";
        const body2 = { id: p.id, decision };
        if (pin) body2.pin = pin.value;
        if (confirm) body2.confirm = confirm.checked;
        if (draftBox && !draftBox.readOnly && draftBox.value !== p.draft) body2.edits = { text: draftBox.value };
        try {
          const r = await api("/api/actions/decide", body2);
          const fresh = proposalCard(r.proposal, onDone); m.replaceWith(fresh); scroll(fresh);
          if (onDone) onDone(r.proposal);
          document.dispatchEvent(new CustomEvent("assistant-action", { detail: r.proposal }));
        } catch (e) { msg.textContent = e.message; btn.disabled = false; }
      };
      if (p.can_approve) {
        const ok = node("button", null, "Approve"); ok.type = "button";
        ok.addEventListener("click", () => decide("approve", ok)); bar.append(ok);
      }
      if (draftBox && p.can_approve) {
        const ed = node("button", "ghost", "Edit text"); ed.type = "button";
        ed.addEventListener("click", () => { draftBox.readOnly = false; draftBox.focus(); ed.disabled = true; });
        bar.append(ed);
      }
      if (p.can_reject) {
        const no = node("button", "ghost", "Reject"); no.type = "button";
        no.addEventListener("click", () => decide("reject", no)); bar.append(no);
      }
      body.append(bar, msg);
    }
    const foot = node("div", "msg-foot");
    foot.textContent = p.reviewer ? `Safety check: ${p.reviewer.detail}` : "Safety check done";
    m.append(foot);
    return m;
  }

  async function render(r, log, message, ctx) {
    if (!r || !r.is_action) return false;
    let card = null;
    if (r.card === "proposal") card = proposalCard(r.proposal, () => refreshHome());
    else if (r.card === "clarify") card = clarifyCard(r, log, message, ctx);
    else if (r.card === "error") card = errorCard(r.error);
    if (card) { log.append(card); scroll(card); }
    return true;
  }

  // ---- intercept the existing assistant forms (capture phase, before app.js handlers) ----------
  document.addEventListener("submit", async (e) => {
    const cfg = FORMS[e.target.id];
    if (!cfg || bypass || typeof me === "undefined" || !me) return;
    const input = $(cfg.input), text = input.value.trim();
    if (!text || QUESTION.test(text) || !HINT.test(text)) return;
    e.preventDefault(); e.stopImmediatePropagation();
    const log = $(cfg.log);
    const ctx = cfg.patient && typeof currentPatient !== "undefined" && currentPatient ? currentPatient.id : null;
    const you = node("div", "msg you", text); log.append(you);
    input.value = "";
    const r = await propose(log, text, ctx);
    if (!(await render(r, log, text, ctx))) {
      you.remove(); input.value = text;  // not an action: let the normal assistant answer it
      bypass = true;
      try { e.target.requestSubmit(); } finally { bypass = false; }
    }
  }, true);

  // ---- "What can the assistant do?" ----------------------------------------------------------
  let helpData = null;
  async function loadHelp() {
    if (helpData) return helpData;
    try { helpData = await api("/api/actions/help"); } catch { helpData = { actions: [] }; }
    return helpData;
  }
  function addHelp(formId) {
    const form = $(formId); if (!form || form.dataset.actHelp) return;
    form.dataset.actHelp = "1";
    const wrap = node("div", "act-help");
    const btn = node("button", "ghost small-btn act-help-btn", "What can the assistant do?"); btn.type = "button";
    btn.setAttribute("aria-expanded", "false");
    const pop = node("div", "act-pop"); pop.hidden = true; pop.setAttribute("role", "dialog");
    btn.addEventListener("click", async () => {
      const d = await loadHelp();
      pop.replaceChildren();
      pop.append(node("p", "act-pop-title", "Ask in plain words. The assistant prepares the change; you approve it."));
      if (!d.actions.length) pop.append(node("p", "muted", "Your role has no assistant actions."));
      const ul = node("ul");
      d.actions.forEach((a) => {
        const li = node("li"); const b = node("button", "chip", a.example); b.type = "button";
        b.title = a.can_approve ? "You can approve this" : "Someone else approves this";
        b.addEventListener("click", () => {
          const input = $(FORMS[formId].input); input.value = a.example; input.focus(); pop.hidden = true;
          btn.setAttribute("aria-expanded", "false");
        });
        li.append(node("span", "act-pop-kind", a.label + (a.can_approve ? "" : " (someone else approves)")), b);
        ul.append(li);
      });
      pop.append(ul, node("p", "muted", d.note || ""));
      pop.hidden = !pop.hidden; btn.setAttribute("aria-expanded", String(!pop.hidden));
    });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") { pop.hidden = true; btn.setAttribute("aria-expanded", "false"); } });
    wrap.append(btn, pop);
    form.after(wrap);
  }

  // ---- pending proposals on Home ---------------------------------------------------------------
  async function refreshHome() {
    const home = $("tab-home"); if (!home || !me) return;
    let box = $("act-home");
    if (!box) {
      const anchor = $("home-todo"); if (!anchor) return;
      box = node("div", "act-home"); box.id = "act-home";
      box.append(node("h2", "sub-h", "Assistant proposals waiting"), node("div", "act-home-list"));
      anchor.after(box);
    }
    let items = [];
    try { items = await api("/api/actions"); } catch { box.hidden = true; return; }
    const open = items.filter((p) => (p.status === "pending" || p.status === "held") && (p.can_approve || p.can_reject));
    box.hidden = !open.length;
    const list = box.querySelector(".act-home-list"); list.replaceChildren();
    open.slice(0, 6).forEach((p) => list.append(proposalCard(p, () => setTimeout(refreshHome, 800))));
  }

  function start() {
    if (typeof me === "undefined" || !me) return false;
    helpData = null;
    Object.keys(FORMS).forEach(addHelp);
    refreshHome();
    return true;
  }
  const timer = setInterval(() => { if (start()) clearInterval(timer); }, 400);
  const home = $("tab-home");
  if (home) new MutationObserver(() => { if (!home.hidden) refreshHome(); }).observe(home, { attributes: true, attributeFilter: ["hidden"] });
})();
