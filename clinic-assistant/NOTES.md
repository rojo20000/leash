# Notes, known limits and roadmap (V3)

What works today, what doesn't yet, and what would close each gap. Ordered by impact on the demo.

## Known limits

### 1. Leash's own Nemotron calls go to the NVIDIA cloud
Clinic Assistant's reviewer runs Nemotron **locally** (`nemotron-mini` via Ollama). Leash's gateway
detectors and reasoner (`leash/nemotron.py`) call `integrate.api.nvidia.com` and, for NemoGuard,
`ai.api.nvidia.com` when `NVIDIA_API_KEY` is set (otherwise they replay recordings or fall back locally).
That traffic carries synthetic data and is allowed by the team rule, but it is the one path that leaves
the machine, and Clinic Assistant's Network view cannot see it (it lives in another process).

**To close it:** point Leash at a local OpenAI-compatible endpoint. `leash/nemotron.py` already accepts a
loopback base URL: `LEASH_NEMOTRON_BASE_URL=http://127.0.0.1:11434/v1` plus per-role model overrides
(`LEASH_NEMOTRON_LIGHTNING_MODEL`, `LEASH_NEMOTRON_SAFETY_MODEL`, `LEASH_NEMOTRON_JAILBREAK_MODEL`, e.g.
`nemotron-mini`), and `LEASH_NEMOGUARD=off` or a loopback `LEASH_NEMOGUARD_URL`. This is a Leash-side
change for the Leash build to make and measure; nothing in `clinic-assistant/` changes.
Design: https://claude.ai/artifact/Xwta3gMSPoC3bSB2x3gRyw

### 2. The reviewer is only tested with the stand-in
All reviewer tests use the stand-in (`MOCK_LLM=1` / `REVIEWER_MOCK=1`). Before the demo: `ollama pull
nemotron-mini`, run `python3 live_check.py`, and check that answers are not held by timeouts on the
demo machine (`reviewer.timeout_s` is 20 s; an Intel Mac CPU may need more).

### 3. Live updates only through the app
Patients, chart entries and appointments update in real time, each with a `change_log` row, but only
through the UI or its signed-in API. There is no bulk import (CSV/FHIR) and no way for another program
to write without a user session.
**To close it:** a `scripts/import_patients.py` that validates each row with `records.validate_patient`
and writes through `ClinicDB.write_many` as a named system user, so every import is in `change_log`.

### 4. The network audit covers this app only
The Network view reads this app's own `model_call` audit entries and checks its configured addresses.
It does not see other processes (Leash, Ollama's own update checks, the browser) or packets.
**To close it:** an OS-level egress check on the demo machine (macOS: `lsof -i -n -P` / Little Snitch;
Windows: `Get-NetTCPConnection`), or a firewall rule that blocks outbound traffic for Ollama and Python,
then show that the app still works.

### 5. Leash integration limits (from the N23 build)
One role policy for every Clinic Assistant role (`scheduling_assistant`); no behaviour model for a human
front end, so patient searches are often held; approving a held call in the Leash dashboard does not
return the record to Clinic Assistant.

### 6. Prototype security gaps (before any real data)
HTTP only on 127.0.0.1, no SSO/MFA, a shared demo PIN, SQLite single-writer (one app process per data
folder), no disk encryption or off-machine audit copy. See "Not done yet" in `README.md`.

## Done in 2.12

Reviewer on/off demo switch (audited, stored in `clinic.db`), three one-click attack scenarios, `docs/DEMO.md`.

## Roadmap

| Next | Why | Size |
| --- | --- | --- |
| Run Leash's Nemotron stages against local Ollama (limit 1) | Nothing leaves the machine, end to end | Leash-side env change + re-measure |
| Real-model reviewer check and timeout tuning (limit 2) | Demo reliability | Small |
| Bulk import script through `ClinicDB.write_many` (limit 3) | Load more synthetic data with full change history | Small |
| OS-level egress check in the Network view (limit 4) | Prove "nothing leaves" for every process | Medium |
| Per-role Leash policy for human users (limit 5) | Fewer false holds in integrated mode | Leash-side |
