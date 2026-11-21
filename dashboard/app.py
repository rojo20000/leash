"""Leash dashboard. Design rule: Nemotron explains and recommends; fixed policy and the human reviewer decide."""
import json
import sys
import time
from pathlib import Path

import httpx
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))
import client  # noqa: E402

st.set_page_config(page_title="Leash", layout="wide")
DASH = "-"
COLORS = {"allow": "#1a7f37", "block": "#cf222e", "escalate": "#bf8700"}
RISK = {"low": "#1a7f37", "medium": "#bf8700", "high": "#d1580a", "critical": "#cf222e"}
CAPTION = "Advisory only. The decision above comes from fixed policy; you make the final call."


def fetch(path, params=None):
    try:
        return client.get(path, params), None
    except (httpx.HTTPError, OSError, ValueError) as e:
        return None, f"{path}: {type(e).__name__}"


def fmt(v, nd=2):
    return DASH if v is None else (f"{v:.{nd}f}" if isinstance(v, float) else str(v))


def served_by(d):
    n = d.get("nemotron")
    if not n:
        return DASH
    parts = [f"{s.replace('content_safety', 'safety')}: {n[s].get('served_by', DASH)}"
             for s in ("jailbreak", "content_safety", "reasoner") if n.get(s)]
    return " · ".join(parts) or DASH


def reasoner_panel(rz):
    if not rz:
        st.info("No explanation available")
        return
    risk = rz.get("risk_level")
    if risk in RISK:  # only a fixed enum value is ever put in HTML
        st.markdown(f"<span style='background:{RISK[risk]};color:#fff;padding:2px 8px;border-radius:4px;"
                    f"font-weight:600'>{risk}</span>", unsafe_allow_html=True)
    else:
        st.text(f"risk: {fmt(risk)}")
    st.text(rz.get("explanation") or DASH)  # untrusted model output: plain text only
    st.text("Cited rules: " + (", ".join(rz.get("policy_rule_ids") or []) or DASH))
    st.text(f"Nemotron recommends: {fmt(rz.get('recommended_action'))}")
    st.text(f"served by: {fmt(rz.get('served_by'))} | latency: {fmt(rz.get('latency_ms'), 1)} ms")
    st.caption(CAPTION)


def act(qid, action):
    if client.fixtures_dir():
        st.toast("fixture mode: no action")
        return
    try:
        client.review(qid, action)
        st.toast(f"{qid}: {action} done")
    except (httpx.HTTPError, OSError) as e:
        st.error(f"{qid}: could not {action} ({type(e).__name__})")


# ---- sidebar / controls
auto = st.sidebar.toggle("Auto-refresh every 2 s", value=False)
st.sidebar.button("Refresh")

st.title("Leash")
if client.fixtures_dir():
    st.warning("FIXTURE MODE: synthetic data read from files, not from a gateway.")

health, e1 = fetch("/health")
verify, e2 = fetch("/v1/audit/verify")
decisions, e3 = fetch("/v1/decisions", {"limit": 100})
queue, e4 = fetch("/v1/queue", {"status": "pending"})
metrics, e5 = fetch("/v1/metrics")
errors = [e for e in (e1, e2, e3, e4, e5) if e]
if errors:
    st.error("Gateway unreachable or returned an error: " + "; ".join(errors))

# ---- 1. header
h = health or {}
c = st.columns(4)
c[0].metric("Core", fmt(h.get("core")))
c[1].metric("ML", fmt(h.get("ml")))
c[2].metric("Nemotron", h.get("nemotron", "n/a"))
with c[3]:
    st.caption("Audit chain")
    if verify is None:
        st.text(DASH)
    elif verify.get("ok"):
        st.success(f"chain intact ({verify.get('entries')} entries)")
    else:
        st.error(f"TAMPERED at line {verify.get('first_bad')}: {verify.get('reason')}")

# ---- 2. feed
st.header("Decision feed")
rows = []
for d in reversed((decisions or {}).get("decisions", [])):
    rows.append({"time": d.get("ts"), "session": d.get("session_id"), "tool": d.get("tool"),
                 "decision": d.get("decision"),
                 "reasons": "; ".join(r["code"] + (f" ({r['detail']})" if r.get("detail") else "")
                                      for r in d.get("reasons", [])),
                 "added ms": (d.get("latency_ms") or {}).get("added"), "served by": served_by(d)})
if rows:
    st.dataframe(pd.DataFrame(rows).style.map(lambda v: f"color:{COLORS.get(v, 'inherit')};font-weight:600",
                                              subset=["decision"]), hide_index=True)
else:
    st.text("No decisions yet" if decisions is not None else DASH)

# ---- 3. queue
st.header("Approval queue")
items = (queue or {}).get("items", [])
if not items:
    st.text("Nothing pending" if queue is not None else DASH)
for it in items:
    qid, alert = it.get("queue_id"), it.get("kind") == "alert"
    with st.container(border=True):
        st.subheader(f"{qid} | {it.get('kind')} | {it.get('tool')}")
        left, right = st.columns(2)
        with left:
            st.text("args: " + json.dumps(it.get("args"), sort_keys=True)[:300])
            st.text("reasons: " + "; ".join(f"{r['code']} ({r.get('detail', '')})" for r in it.get("reasons", [])))
            b1, b2 = st.columns(2)
            # The recommendation never pre-selects or clicks either button.
            if b1.button("Dismiss" if alert else "Approve", key=f"approve-{qid}"):
                act(qid, "approve")
            if b2.button("Confirm block" if alert else "Deny", key=f"deny-{qid}"):
                act(qid, "deny")
        with right:
            reasoner_panel(it.get("reasoner"))

# ---- 4. metrics
st.header("Metrics")
m = metrics or {}
rates, lat = m.get("rates") or {}, m.get("latency_ms") or {}
c = st.columns(5)
for col, k, label in zip(c, ("allow", "escalate", "block"), ("Auto-approved", "Escalated", "Blocked")):
    col.metric(label, fmt(rates.get(k), 3))
c[3].metric("Added p50 ms", fmt(lat.get("p50")))
c[4].metric("Added p95 ms", fmt(lat.get("p95")))
stages = lat.get("by_stage") or {}
st.dataframe([{"stage": s, "p50": v.get("p50"), "p95": v.get("p95")} for s, v in stages.items()]
             or [{"stage": DASH, "p50": None, "p95": None}], hide_index=True)

models = m.get("models") or {}
st.subheader("Model quality")
st.dataframe([{"model": k, "precision": (models.get(k) or {}).get("precision"),
               "recall": (models.get(k) or {}).get("recall")} for k in ("injection", "anomaly", "minimization")],
             hide_index=True)
st.subheader("Rust vs Python benchmark")
bench = models.get("bench")
if not bench:
    st.text("not built")
else:
    rust, py, sp = bench.get("rust") or {}, bench.get("python") or {}, bench.get("speedup") or {}
    st.dataframe([{"op": op, "rust us": rust.get(f"{op}_us"), "python us": py.get(f"{op}_us"),
                   "speedup": sp.get(op)} for op in ("policy", "audit_append")], hide_index=True)

st.subheader("Nemotron")
nm = m.get("nemotron") or {}
sb = nm.get("served_by") or {}
st.dataframe([{"step": s, **(sb.get(s) or {})} for s in ("jailbreak", "content_safety", "reasoner")]
             if sb else [{"step": DASH}], hide_index=True)
st.dataframe([{"model": k, "p50": v.get("p50"), "p95": v.get("p95"), "n": v.get("n"), "source": v.get("source")}
              for k, v in (nm.get("latency_ms") or {}).items()] or [{"model": DASH}], hide_index=True)
st.text("Resolved models: " + (", ".join(f"{k}={v}" for k, v in (nm.get("models") or {}).items()) or DASH))
rounds = (((models.get("nemotron") or {}).get("eval") or {}).get("rounds")) or []
if rounds:
    def _h(r):
        return r.get("holdout") or {}
    st.dataframe([{"round": r.get("round"),
                   "holdout injection recall (combined)": ((_h(r).get("injection") or {}).get("combined") or {}).get("recall"),
                   "content safety accuracy": _h(r).get("content_safety_accuracy"),
                   "reasoner action agreement": _h(r).get("reasoner_action_agreement")} for r in rounds],
                 hide_index=True)

if auto:
    time.sleep(2)
    st.rerun()
