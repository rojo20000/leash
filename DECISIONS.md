# Decisions

Record each decision with the date, what was chosen, and why.

## 2026-11-21 — LLM: qwen3.5:9b
Chosen: `qwen3.5:9b` (Q4_K_M, 9.0B) via Ollama 0.40.16. `ollama show` lists `tools` under capabilities, so the `gemma4:12b` fallback was not needed. Runs on the local RTX 5070 Ti (12 GB VRAM). Call it with `think: false` for tool calling (thinking defaults to on).

## 2026-11-21 — spaCy model: en_core_web_lg
`en_core_web_lg` 3.8.0 downloaded and loads; no fallback to `en_core_web_sm` needed.

## 2026-11-21 — Windows toolchain
Rust stable-x86_64-pc-windows-msvc with VS 2022 Build Tools (VC tools). make from ezwinports. No `lsof` on Windows: use `netstat -ano` / `Get-NetTCPConnection` and `taskkill` / `Stop-Process` (allowed in `.claude/settings.json`).
