# Decisions

Record each decision with the date, what was chosen, and why.

## 2026-11-21 — LLM: qwen3.5:9b
Chosen: `qwen3.5:9b` (Q4_K_M, 9.0B) via Ollama 0.40.16. `ollama show` lists `tools` under capabilities, so the `gemma4:12b` fallback was not needed. Runs on the local RTX 5070 Ti (12 GB VRAM). Call it with `think: false` for tool calling (thinking defaults to on).

## 2026-11-21 — spaCy model: en_core_web_lg
`en_core_web_lg` 3.8.0 downloaded and loads; no fallback to `en_core_web_sm` needed.

## 2026-11-21 — Windows toolchain
Rust stable-x86_64-pc-windows-msvc with VS 2022 Build Tools (VC tools). make from ezwinports. No `lsof` on Windows: use `netstat -ano` / `Get-NetTCPConnection` and `taskkill` / `Stop-Process` (allowed in `.claude/settings.json`).

## 2026-11-21 11:12 — Subagent roles run as general-purpose agents with a model override
The `planner`, `implementer` and `transcriber` types in `.claude/agents/` were not registered in the overseer session (it was opened in the parent folder `Tidal Byte/`, so the project agents in `leash/.claude/agents/` were not loaded). Each role is started as a general-purpose subagent with `model` set to the role's model (planner: opus, implementer: sonnet, transcriber: haiku) and the role's agent-file body pasted into the brief.

## 2026-11-21 11:12 — Organizer requirements not supplied
The mission's "Organizer requirements" line was left as a placeholder, so the submission package follows the mission's own list. The team must check the hackathon's submission form against docs/SUBMISSION.md by hand.

## 2026-11-21 11:25 — Nemotron track added; data rule updated
The team added the NVIDIA "Best Use of Nemotron" track at 11:23 (full text in `graph/MISSION.md`, addendum). Calls to `integrate.api.nvidia.com` carrying synthetic data are now allowed; no other off-machine traffic. The overseer updated the matching rule line in `CLAUDE.md` so subagents do not refuse live calls (the only overseer edit outside `graph/`, `PROGRESS.md` and `DECISIONS.md`). Model IDs from `GET /v1/models` (33 models, readable without a key): `nvidia/nemotron-3.5-lightning-30b-a3b` and `nvidia/nemotron-3.5-content-safety` are listed. NemoGuard JailbreakDetect is not in that list; N16 checks its reference page and swaps to the closest listed model if it is not served from `integrate.api.nvidia.com`.

## 2026-11-21 11:25 — NVIDIA_API_KEY missing (blocker raised with the team)
No `NVIDIA_API_KEY` in the environment and no `.env`. Team asked to create `leash/.env`. Until then the Nemotron nodes build and test in replay mode against fixtures.

## 2026-11-21 11:26 — Routing: Nemotron re-plan goes to the planner; N6 keeps its current contract
N6 (agent + gateway) was already running when the addendum arrived. Classified as a contract change, so the planner revises CONTRACTS.md and adds N16, N17, N18. N6 finishes against the contract it started with; the Nemotron stages are added to the gateway after N6 passes, so two agents never edit `gateway/` at once.

## 2026-11-21 11:33 — Planner re-plan attempt 1 returned blocked (overseer error)
The addendum had not been written to `graph/MISSION.md` when the planner started (a shell heredoc failed silently in the same step). The planner correctly stopped without guessing. Addendum now written; planner restarted.

## 2026-11-21 11:40 — NVIDIA key supplied; live model probe
The team supplied the key; it is in the git-ignored `.env`. Probe through `/v1/chat/completions`: `nvidia/nemotron-3.5-lightning-30b-a3b` works (343 ms plain, 612 ms tool call, thinking off). `nvidia/nemotron-3.5-content-safety` returns HTTP 404 "function not found in account" for this key. `nvidia/llama-3.1-nemotron-safety-guard-8b-v3` works (about 560-680 ms, JSON verdict with categories). Pending N16's check of the reference pages, the likely swap is Content Safety → `llama-3.1-nemotron-safety-guard-8b-v3`.

## 2026-11-21 11:47 — Model swaps confirmed by N16 (per the addendum's swap rule)
- Content Safety role: `nvidia/nemotron-3.5-content-safety` → `nvidia/llama-3.1-nemotron-safety-guard-8b-v3`. Evidence: HTTP 404 "function not found in account" for our key on the documented `/chat/completions` path; its page also shows a fixed taxonomy with no custom policy. Safety-guard takes our HIPAA minimum-necessary policy as a category in its prompt.
- Second injection detector: NemoGuard JailbreakDetect → `nvidia/llama-3.1-nemotron-safety-guard-8b-v3` with our injection policy text. Evidence: JailbreakDetect is served from `ai.api.nvidia.com`, which is not an allowed destination, and it is not in `/v1/models`.
- Lightning (`nvidia/nemotron-3.5-lightning-30b-a3b`) is used as specified for the agent and the reasoner.
If the team gets Content Safety access or allows `ai.api.nvidia.com`, set `LEASH_NEMOTRON_SAFETY_MODEL` / `LEASH_NEMOTRON_JAILBREAK_MODEL`; no code change is needed for the safety role.

## 2026-11-21 11:47 — Timestamps before 11:33 in this file run up to 12 minutes fast
They were estimates. Actual clock: key supplied 11:28, N5 and N6 passed 11:30, N2 fix passed 11:33.

## 2026-11-21 11:45 — Failure routing: N2 policy bypass
Review found `Policy.evaluate` checked only the first resource type (both cores). Cause: ambiguous wording in CONTRACTS.md C1.1 step 2. Routed as a contract issue plus a bug inside the node: planner fixed the wording, implementer fixed both cores with tests (N2 iteration 2, passed).

## 2026-11-21 11:12 — Overseer handoff file
`graph/MISSION.md` holds the product spec, limits and graph format so every subagent brief can point at one file.
