"""Repo-wide pytest setup: a plain `pytest` never calls the NVIDIA API.

If the caller did not choose a Nemotron mode, force replay (answers only from committed recordings, never opens a
socket), even when `.env` holds a key. Live tests set LEASH_NEMOTRON themselves and are opt-in (pytest.ini marker).
"""
import pytest


@pytest.fixture(autouse=True)
def _nemotron_never_live_by_default(monkeypatch):
    import os
    if not os.environ.get("LEASH_NEMOTRON"):
        monkeypatch.setenv("LEASH_NEMOTRON", "replay")
