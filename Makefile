ifeq ($(OS),Windows_NT)
PY := .venv/Scripts/python.exe
MATURIN := ../../.venv/Scripts/maturin.exe
else
PY := .venv/bin/python
MATURIN := ../../.venv/bin/maturin
endif

.PHONY: help setup rust data check demo record dashboard preflight

help:
	@echo "make setup      create .venv with uv, install requirements.txt (incl. spaCy en_core_web_lg), build Rust core"
	@echo "make rust       rebuild the Rust core (maturin develop --release); without it Leash uses the Python core"
	@echo "make data       synthetic data, injection corpus, ML models, metrics (rebuilt from scratch, seeded)"
	@echo "make check      data + cargo test + pytest + benchmark + scripted demo assertions (no key, no network)"
	@echo "make demo       data + narrated scripted demo (unprotected vs protected); Nemotron from recordings"
	@echo "make record     re-record Nemotron responses for the scripted demo (needs NVIDIA_API_KEY; calls the API)"
	@echo "make dashboard  EHR :8001 + gateway :8000 + seeded protected session + Streamlit :8501, in one process"
	@echo "                group. Ctrl+C stops all three. If a window was closed instead, stop leftovers with"
	@echo "                'netstat -ano | findstr :8000' (and :8001, :8501) then 'taskkill /PID <pid> /T /F'."

setup:
	uv venv .venv --python 3.12
	uv pip install --python $(PY) -r requirements.txt
	$(MAKE) rust

# Git Bash's /usr/bin/link.exe can shadow the MSVC linker; if linking fails, run the same command from PowerShell:
#   cd crates/leash_core; ..\..\.venv\Scripts\maturin.exe develop --release
rust:
	cd crates/leash_core && $(MATURIN) develop --release

data:
	$(PY) data/generate.py
	$(PY) data/corpus/expand.py
	$(PY) ml/train_injection.py
	$(PY) ml/train_anomaly.py
	$(PY) ml/eval_minimizer.py

# Replay only: never calls the NVIDIA API, even when .env holds a key.
check: export LEASH_NEMOTRON = replay
check: data
	cd crates/leash_core && cargo test
	$(PY) -m pytest
	$(PY) bench/rust_vs_python.py --quick
	$(PY) demo/run_demo.py --scripted --assert

demo: data
	$(PY) demo/run_demo.py --scripted

record:
	LEASH_NEMOTRON=live $(PY) demo/run_demo.py --scripted

dashboard: data
	$(PY) scripts/serve.py

preflight:
	$(PY) scripts/preflight.py
