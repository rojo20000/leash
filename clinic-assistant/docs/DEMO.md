# 3-minute judge demo: the Nemotron reviewer, before and after (v2.12)

What judges should take away: the fixed safety filters miss cleverly worded requests; a second local
model (NVIDIA Nemotron) reviews every question and answer and catches them, on this computer, and every
switch and verdict is on the record.

## Setup (once, before the judges arrive)

```bash
ollama pull llama3.2            # the chat model (already on the demo Mac)
ollama pull nemotron-mini       # the reviewer, about 2.7 GB
python3 setup_demo.py           # demo accounts, including lead_ana (clinical lead) and admin_kai (admin)
python3 run.py                  # then open http://127.0.0.1:8642
```

Sign in once as `lead_ana` and ask any question, so both models are loaded before the clock starts.

**No Ollama, or no time to download?** Run `MOCK_LLM=1 python3 run.py`. The chat model and the reviewer
both become offline stand-ins. The reviewer stand-in catches the three scenarios the same way every
time, so the demo still works. (`REVIEWER_MOCK=1` uses the stand-in reviewer with the real chat model.)

## Script

| Time | Do | Say |
| --- | --- | --- |
| 0:00 | Sign in as **lead_ana**. Open **Network**. | "Everything runs on this laptop. Here's the chat model, and here's a second model, Nemotron, whose only job is to check the first one. It's up." |
| 0:20 | Open **Ask a question**, expand **Demo scenarios**, press **Reviewer: on (demo)** to switch it off. | "For the demo I'll switch the reviewer off. Note the amber bar at the top: the app tells everyone, and the switch itself is audited." |
| 0:35 | Press **Run** on scenarios 1, 2 and 3. | "1 is a prompt injection written politely, no banned words. 2 asks us to tell a patient to stop warfarin before surgery without a doctor. 3 baits the model into listing phone numbers and birth dates and talking about a patient who isn't on the list. All three come back **Ready to read**: the filters let them through. The yellow box under each says 'Not checked: reviewer switched off'." |
| 1:20 | Press **Reviewer: off (demo)** to switch it back on. Press **New conversation**, run 1, 2, 3 again. | "Same three prompts, reviewer on." |
| 1:40 | Point at each result. | "1 and 3 are **Stopped** before the chat model ever sees them, and go to a clinical lead. 2 is **Check first**: held until someone reads why. The red box says exactly what the reviewer caught, before or after the model." |
| 2:15 | Open **Conversations**. | "Every question is logged, with the reviewer's verdict before and after the model: 'Reviewer off' for the first three, 'Reviewer red' or 'amber' for the second three." |
| 2:35 | Sign in as **admin_kai** (or auditor_ray), open **Audit log**. | "And the audit trail: who switched the reviewer off and on, every reviewer verdict with its timing, and every model call. No patient text in any of it. The log is hash-chained, so it can't be quietly edited." |
| 3:00 | Done. | |

## If the real reviewer is slow (Intel Mac, CPU only)

- The first check after start can take 20 to 60 seconds while Nemotron loads; that's why you warm it up first.
- After that, expect a few seconds per check (it runs twice per question). Say: "On a laptop CPU this
  takes a few seconds. On the clinic's server with a GPU it's well under a second, and nothing leaves the building."
- If a check takes longer than `reviewer.timeout_s` (20 s), the answer is **held** ("Reviewer unavailable;
  held for a person"), never passed. That's the point: if the checker can't check, a person does. If that
  keeps happening on stage, switch to `MOCK_LLM=1`.
- The real model is not deterministic. If it lets one through, say so, and show that the fixed filters,
  the masking and the human review still apply.

## Reset after the demo

Press the switch so it reads **Reviewer: on (demo)**. The switch is stored in `data/clinic.db`, not in
`config/policy.json`, so a restart keeps whatever was last chosen.
