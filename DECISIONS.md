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

## 2026-11-21 11:12 — Overseer handoff file
`graph/MISSION.md` holds the product spec, limits and graph format so every subagent brief can point at one file.
