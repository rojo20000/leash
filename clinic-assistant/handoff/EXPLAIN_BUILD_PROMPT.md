```text
Explain everything in Clinic Assistant, a local medical AI web app I built today (Nov 21, 2026) for the Tidal Byte 2026 hackathon, and how each part works. Read the code; do not change any files.

<context>
The code is in clinic-assistant/ (on my Mac it may be <an older local copy>, which can be an older copy). Start with README.md and config/policy.json, then read every file in app/, static/, tests/, run.py and manage_users.py. If docs/STAFF_GUIDE.md, docs/DEMO_SCRIPT.md or an "actions" section in policy.json exist, a later round added assistant actions and a demo clinic day; explain those too. If they don't exist, say so in one line.

The app is the human-facing front end of our team project "Leash", a runtime security gateway for clinical AI agents (Nemotron track). Leash itself lives in a separate leash/ folder that other agents are building; leave it out of the explanation. All patient data is synthetic.
</context>

<audience>
Me, so I can explain and defend the build to hackathon judges and teammates. I know the idea well but did not write most of the code line by line. Use plain language, and name the file and function whenever you describe a behavior so I can point to it.
</audience>

Write the explanation in this order:
1. What it is, in three sentences: the problem, what the app does, and why it runs only on this machine.
2. The life of one request, step by step: sign-in and session, rate limit, masking (app/privacy.py), input checks (app/guardrails.py), minimum-necessary patient context and the note injection scan, the local model call (app/llm.py), output checks, green/amber/red scoring, and where the result lands (answer, Review queue, Messages outbox, audit log). Include a simple text diagram of this flow.
3. Each component, one short section per file: what it does, the key functions, and which policy.json settings control it.
4. The data layer: every file in data/ (vectors.sqlite, audit.jsonl, patients.json, users.json, reviews.json, outbox.json), how the append-only and hash-chained stores detect tampering, the offline hashing-1024 embedder, and what "Similar cases" and reworded-injection detection do.
5. Roles and tiers: a table of each role (clinician, nurse, clinical_lead, auditor, admin) and what it can see and approve, and a table of green/amber/red with what triggers each and who reviews it.
6. The demo attack: how patient syn-003's poisoned referral letter is caught, by which check, and what each role sees afterward.
7. The screens in static/ (Patients, Ask the assistant, Review queue, Messages, Audit log) and what each one calls on the server.
8. How to run it and test it: the exact commands from the README and tests, what MOCK_LLM=1 does, and what the tests cover.
9. Honest limits: what is not built or not safe yet, taken from the README and from anything you notice in the code. Mark your own observations as yours.
10. Five likely judge questions with a two-sentence answer each, based only on what the code does.

Report only what the code and docs show. Where the code and README disagree, say which file says what. Aim for something I can read in about 15 minutes.
```

Run with: Claude Code opened on the medical-local-ai folder, Opus 5.5, `medium` effort.
