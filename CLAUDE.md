# Leash — project context

**What it is:** Leash is a runtime security gateway for clinical AI agents. It sits between an LLM agent and the tools/EHR it calls, inspects every tool call and response, blocks or redacts PHI and unsafe actions, and logs what happened.

**Team:** Rowan Haber, Salvador Jimenez, Zarek Haleem, Nico Pitre.
**Event:** Tidal Byte 2026. **Submission closes 9:30 pm America/Chicago, 2026-11-21.** Leave time for the demo and README.

## Stack
- Python 3.12 in `.venv` (created with uv). Run Python as `.venv/Scripts/python.exe` (Windows).
- FastAPI + uvicorn (gateway), Streamlit (dashboard), Presidio + spaCy (PHI detection), scikit-learn (ML), pytest (tests).
- Rust crate `crates/leash_core` exposed to Python with PyO3 + maturin. Rebuild with `cd crates/leash_core && ../../.venv/Scripts/maturin.exe develop --release`.
- Local LLM through Ollama: **qwen3.5:9b** (see DECISIONS.md). Call it with `think: false` for tool calling.
- git, make. `make preflight` checks the whole toolchain; `make check`, `make demo`, `make dashboard` are stubs to fill in.

## Environment notes
- Windows 11, RTX 5070 Ti (12 GB VRAM). Shells: PowerShell and Git Bash. No `lsof`: use `netstat -ano` / `Get-NetTCPConnection` and `taskkill` / `Stop-Process`.
- Build Rust from a shell where MSVC is found. Git Bash's `/usr/bin/link.exe` can shadow the MSVC linker; if linking fails, build from PowerShell.

## Rules
- **Synthetic patient data only. Nothing leaves this machine except package downloads and calls to `integrate.api.nvidia.com` (NVIDIA Nemotron models) carrying synthetic data.** No real PHI, no other external APIs, no telemetry. (Updated 2026-11-21 11:23 by the team's Nemotron addendum; see `graph/MISSION.md`.) The key is in `NVIDIA_API_KEY`, loaded from the git-ignored `.env`; never print, log or commit it.
- **Ask before `git push` or any system-level install** (winget, rustup toolchains, Ollama, etc.). Python packages in `.venv` are fine.
- Record decisions in DECISIONS.md and progress in PROGRESS.md as you go.
