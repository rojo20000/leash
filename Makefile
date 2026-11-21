ifeq ($(OS),Windows_NT)
PY := .venv/Scripts/python.exe
else
PY := .venv/bin/python
endif

.PHONY: preflight check demo dashboard

preflight:
	$(PY) scripts/preflight.py

check:
	@echo not built yet

demo:
	@echo not built yet

dashboard:
	@echo not built yet
