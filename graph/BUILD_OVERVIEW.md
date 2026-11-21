# Leash build overview

Snapshot: 1:46 pm America/Chicago, 2026-11-21. Live state is always `graph/state.json`; this file is a
hand-written summary and goes stale.

## 1. The system as it stands

Leash is a runtime security gateway that sits between a clinical AI agent and a hospital records system.
Every tool call the agent makes goes through it. All patient data is synthetic.

```
Clinical agent (scheduling assistant)
  Nemotron 3.5 Lightning; falls back to local Ollama qwen3.5:9b; scripted replay for the demo
        |
        v   POST /v1/tool-call
Leash gateway (FastAPI, port 8000)
  1. policy            Rust core (Python fallback): tools, FHIR resource types, record rate, email domains
  2. injection         TF-IDF + logistic regression (blocks) and a Lightning judge (escalates)
  3. minimization      field filter per role + Rust pre-scan + Presidio
  4. content safety    Lightning judge with our HIPAA minimum-necessary policy (escalates)
  5. anomaly           IsolationForest over a 60 s window of the session
  6. decide            block > escalate > allow. Final here.
  7. reasoner          Lightning explains every block/escalate. Advisory only.
  8. audit             append-only JSONL, SHA-256 hash chain, verify() detects edits
        |
        v
Mock EHR (FastAPI, port 8001): 200 synthetic FHIR R4 patients. Email goes to a local file.

Dashboard (Streamlit, port 8501): decision feed, approval queue with the reasoner's explanation beside
Approve / Deny, audit-chain status, metrics.
```

Design rule: **Nemotron output can only add caution, never remove it.** Deterministic policy and the human
reviewer decide. A test (`test_advisory_invariant`) enforces this.

| Part | Path | Notes |
|---|---|---|
| Rust core | `crates/leash_core/` | policy, audit chain, identifier pre-scan (PyO3 + maturin) |
| Python fallback | `gateway/core_py.py`, `gateway/core_loader.py` | same interface; `LEASH_CORE=py` forces it |
| Gateway | `gateway/app.py` | pipeline, approval queue, metrics |
| Agent | `agent/` | scripted, Lightning and Ollama drivers |
| Nemotron client | `leash/nemotron.py`, `leash/reasoner.py`, `leash/prompts/` | live / replay / off modes, recordings |
| ML | `ml/` | three models, training scripts, `ml/eval/` Nemotron eval |
| Data and EHR | `data/`, `ehr/` | seeded generator, corpus, mock EHR |
| Demo | `demo/run_demo.py`, `demo/recordings/` | `--scripted --assert`, replays recorded Nemotron responses |
| Dashboard | `dashboard/`, `scripts/serve.py` | `make dashboard` |
| Contracts | `CONTRACTS.md` | the interfaces every node builds against (C1-C10) |

Commands: `make setup`, `make check`, `make demo`, `make dashboard`, `make record` (needs the key),
`make preflight`. `make check` needs no key and no network.

Measured numbers (all in `metrics/results.json`):

| Measure | Value |
|---|---|
| Injection classifier (held-out, 300 notes) | precision 1.00, recall 0.853 |
| Anomaly detector | precision 0.958, recall 0.911, 5.7% false positives on normal windows |
| Identifier minimization | 1.00 / 1.00 on templated notes (likely easy) |
| Gateway, 245 calls, Nemotron stages on local fallback | 71.4% auto-approved, 16.3% escalated, 12.2% blocked |
| Added latency per call (same run) | p50 7.4 ms, p95 17.1 ms |
| Rust vs Python, 100k iterations | policy 4.0x; audit append 2.0x (disk-bound, varied 1.3x-2.0x today) |
| Lightning live latency (eval round 4, 67 calls) | p50 704 ms, p95 1,913 ms |
| Nemotron eval, holdout, round 1 -> round 4 | detector precision 0.60 -> 1.00; reasoner valid JSON 0.69 -> 1.00 |
| Scripted demo, protected run | 17 allowed, 3 blocked, 0 escalated |

Known limits: content safety false-alarmed on 3 clean cases per split in the eval; only 2 labelled
over-disclosure cases; one injected holdout document is missed by both detectors; the live agent followed
the hidden instruction in 1 of 3 runs, so the scripted demo is the demo of record; the NVIDIA key returns
HTTP 429 under burst.

## 2. Where we are

Stages 0 to 3 have passed and are committed. Stage 4 (submission package) is next. The plan had Stage 4
starting at 7:00 pm; we are about five hours ahead.

| Stage | What | Gate passed | Commit |
|---|---|---|---|
| 0 | preflight, contracts, plan, briefs | 11:26 | `f916a54` |
| 1 | all components + Nemotron client, reasoner, agent driver | 11:56 | `b09e7cc` |
| 2 | integration, `make check`, scripted demo | 12:13 | `a44574b` |
| 3 | gateway metrics, Nemotron eval (4 rounds), live demo, demo script, dashboard polish | 13:49 | `f7fbb72` |
| 4 | docs, tables, fresh-eyes run, final check | pending | |

Passed nodes: N0-N11, N1b, N16-N19. Pending: N12, N13, N14, N15.

## 3. How the orchestrator runs

One Claude session (Fable 5.2) is the overseer. It does not write product code. It edits only `graph/`,
`PROGRESS.md` and `DECISIONS.md` (plus one rule line in `CLAUDE.md`, recorded in `DECISIONS.md`).

Roles, each started as a subagent:

| Role | Model | Does |
|---|---|---|
| planner | Opus 5.5 | `CONTRACTS.md`, `graph/plan.yaml`, briefs, re-plans, integration (N8) |
| implementer | Sonnet 5.5 | builds one node inside the paths it owns |
| transcriber | Haiku 5.5 | `PROGRESS.md`, tables, corpus text, demo script |

The role types in `.claude/agents/` were not registered in the overseer session, so each role runs as a
general-purpose subagent with the model set and the role text pasted into the prompt.

State lives on disk so the run survives context loss:

| File | Written by | Holds |
|---|---|---|
| `graph/MISSION.md` | overseer | product spec, hard limits, Nemotron addendum |
| `graph/plan.yaml` | planner | per node: stage, agent, depends_on, owns, check, acceptance, max_iterations |
| `graph/briefs/<id>.md` | planner | self-contained brief for each node |
| `graph/state.json` | overseer | per node: status, iteration, last_check, reviewer_notes; gates |
| `DECISIONS.md` | overseer | every routing decision, model swap and cut |
| `PROGRESS.md` | transcriber | regenerated from `state.json` |

The loop for each node:

1. Overseer starts the node's agent with its brief. One agent per node attempt, at most 4 at once.
2. The agent builds, runs the node's check, and reports (files, check output, deviations, questions).
3. Overseer re-runs the check itself, reads the result against each acceptance criterion, and sets the node
   to `passed` or `rework` with notes.
4. Failures are routed: bug in the node -> another implementer pass; contract mismatch -> planner revises
   `CONTRACTS.md`; environment -> overseer diagnoses; time -> cut order.
5. When every node in a stage is passed or cut, the overseer runs the combined check (`make check`),
   commits `stage N: ...`, and advances.

Only the overseer commits. Subagents never push, never ask the team questions, and edit only owned paths.

## 4. What is left

| Node | Agent | Work | Check |
|---|---|---|---|
| N12 docs | implementer | `README.md`, `docs/PITCH.md`, `docs/HIPAA_MAPPING.md`, `docs/SUBMISSION.md`, `docs/NEMOTRON.md`, LICENSE check | all files exist, README has Mermaid + `make demo`, Nemotron text copied into SUBMISSION |
| N13 tables | transcriber | metrics tables in README, PITCH and NEMOTRON from `metrics/results.json`; fix 4 quotes in `docs/DEMO_SCRIPT.md` (Rust-core output) | table numbers appear in `metrics/results.json` |
| N14 fresh_eyes | implementer, no build context | clean `git worktree`, follow README exactly, run setup and `make check`, report friction | report lists each command pass/fail |
| N15 final | overseer | dispatch fixes for N14's findings, final `make check`, `PROGRESS.md`, final commit | `make check` passes from a clean worktree |

Deadlines: feature freeze 7:00 pm, everything committed by 8:00 pm, submission closes 9:30 pm.

Cut order if more than 30 minutes behind: N11 polish (done), N10 live mode (done), depth of N5's anomaly
eval. Never cut: the attack-vs-defense demo, the audit chain, `make check`, the submission package, N16,
N17, at least one round of N18.

By hand, for the team: check the hackathon's submission form against `docs/SUBMISSION.md`, record the demo
from `docs/DEMO_SCRIPT.md`, decide where to push the repo (the overseer will not `git push` without being
asked), rotate the NVIDIA key afterwards.

## 5. How to change the build plan

Tell the overseer session in chat. It is the only writer of `graph/state.json` and the only one who starts
agents, so a change made behind its back is not picked up until it re-reads the files.

| You want to | Say or do |
|---|---|
| Add scope | Describe it in the overseer chat. It writes the text into `graph/MISSION.md`, has the planner add a contract section, plan entries and briefs, then starts the nodes. This is how the Nemotron track was added. |
| Change a node's instructions | Ask the overseer, or edit `graph/briefs/<id>.md` and the node's entry in `graph/plan.yaml`, then tell the overseer to re-run that node. A node that already passed is not re-run on its own. |
| Change an interface | Ask for a contract change. The planner edits `CONTRACTS.md` and re-briefs every node that builds against that section. Do not edit `CONTRACTS.md` and code separately. |
| Re-run a node | "Set N<id> to rework because ..." The overseer starts a new iteration with your notes. |
| Cut a node | "Cut N<id>." The overseer marks it `cut` in `state.json` and logs it in `DECISIONS.md`. |
| Change a model | Set `LEASH_NEMOTRON_LIGHTNING_MODEL`, `LEASH_NEMOTRON_SAFETY_MODEL` or `LEASH_NEMOTRON_JAILBREAK_MODEL` in `.env`, then run `make record` so the demo recordings match, then `make check`. |
| Change policy or prompts | Edit `policies/scheduling_assistant.toml` or `leash/prompts/*.txt`, then `make record` (prompt changes alter the recorded request keys) and `make check`. |
| Change deadlines or the cut order | Tell the overseer; it updates `schedule` in `state.json`. |

Rules that hold whatever you change: synthetic data only; the only off-machine calls are to
`integrate.api.nvidia.com`; the key stays in `.env`; `make check` must pass with no key and no network.

After any change, `make check` is the test that nothing broke.
