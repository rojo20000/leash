"""Repo-wide pytest setup: a plain `pytest` never calls the NVIDIA API.

Unless the caller chose replay or off, force replay (answers only from committed recordings, never opens a
socket), even when `.env` holds a key. Live tests set LEASH_NEMOTRON themselves and are opt-in (pytest.ini marker).
"""
import pytest


@pytest.fixture(autouse=True)
def _nemotron_never_live_by_default(monkeypatch):
    import os
    if os.environ.get("LEASH_NEMOTRON", "").strip().lower() not in ("replay", "off"):
        monkeypatch.setenv("LEASH_NEMOTRON", "replay")
