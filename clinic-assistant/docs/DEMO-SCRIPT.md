# Clinic Assistant v2.3: a clinic day in 8 minutes

Everything here is made up. All demo accounts share the password you chose on first start.
The demo PIN for showing confidential details or saving changes is **1234** (set in `config/policy.json`, demo only).

Tip: use two browser windows side by side, one normal and one private, so the front desk and the doctor are signed in at the same time. Changes show up in the other window within 15 seconds.

## 1. Front desk (sign in as `desk_sam`), about 3 minutes
1. **Home** says who is due next and how many reminders are waiting for tomorrow. Only Home and Schedule are in the menu: the front desk can't open charts or the clinical assistant (the server refuses, not just the screen).
2. **Schedule**: pick an 08:40 patient with **Dr Lee** and press **Check in**. Birth date, phone, address and member ID say *hidden*, and the two check boxes are greyed out.
3. Type PIN **1234** and press **Show details**. Now confirm the birth date and the insurance card, then press **Check in**. (Try it with a wrong PIN first: it counts down and locks after 5 tries. Every reveal is in the audit log.)
4. **Book an appointment** on the right: type part of a name, pick the patient, Dr Lee, a day and an open time (taken times aren't offered), a visit type. Try booking the same patient twice that day: it's refused with a clear reason.
5. **Register a new patient**: the Save button stays off until every field is valid (try a member ID like `ab1` or a birth date in the future). After saving, the new patient is already picked for booking.
6. **Tomorrow** → press **Reminder** → **Prepare reminder**. Fixed wording, no medical details. Copy it, then **I've sent it** (press twice). The app never sends anything itself.
7. **Front desk assistant**: ask *"Who is still to arrive today?"*. The line under your question shows what the model actually saw: patient names replaced by tags. Then ask *"What medication is the 9am patient on?"*: it is redirected to clinical staff without ever reaching the model.

## 2. Doctor (sign in as `dr_lee`), about 4 minutes
1. **Home** shows *Waiting:* the patient the desk just checked in, then the day, then the latest chart updates.
2. **Schedule** shows Dr Lee's day with how many things each patient needs checked. Press **Start visit**, later **Finish visit**.
3. Open the checked-in patient. Identifiers are hidden; **Show details** with PIN 1234.
4. **Ask about** the patient: tap *What needs attention for this patient?*. Expand the safety checks under the answer to show the record was sent without name, record number, birth date or contact details.
5. **Add to this chart**: add a result, say Potassium `55`. It is refused as impossible before it can be saved. Change it to `5.4`, type the PIN, add it. It appears in Results and in **Chart history** (hash-chained, can't be quietly edited), and the similar-patients index updates.
6. Open the patient with the **penicillin allergy** (search *otitis*). Try adding *Augmentin 875 mg*: the allergy warning blocks it until you tick the override on purpose.
7. Add a **Finding (what we learned)** note. Every finding stays in the history for later review.

## 3. Oversight, about 1 minute
- `lead_ana`: **Needs review** holds anything stopped, including the poisoned referral letter (patient with high INR) that was kept away from the model.
- `auditor_ray`: **Audit log** shows every sign-in, PIN reveal, wrong PIN, check-in, booking and chart addition, with the hash chain verified.

## 4. Patient portal (2 minutes)
Once, before the demo: `python3 setup_demo.py` (adds the patient account `pt_lena`, same password as the others), then `python3 scripts/seed_portal_demo.py` (a welcome message, and an upcoming appointment if she has none). Keep `pt_lena` in the private window and staff in the normal one.

1. Sign in as `pt_lena` at `http://127.0.0.1:8642`. She lands on the patient portal, not the staff app. *Say: this account is linked to one patient, Lena Delacroix, and the server sends it to the portal; every staff route refuses it.*
2. **Appointments** and **My health summary**: her own upcoming and past visits, then conditions, medicines, allergies and results. *Say: only the fields the clinic releases are here. There are no notes and no "things to check", and the page never sends a patient id, so there is no id to change.*
3. **Messages**: the welcome message from the care team is there. Write a short question and send it. *Say: the notice that messages are not for emergencies is always on screen.*
4. Back in **Appointments**, press **Ask to cancel** on tomorrow's appointment, then press it again to confirm. It shows as a request with status open and the visit stays booked. *Say: the portal never changes the schedule; it asks the front desk.*
5. Sign in as `dr_lee`, open **Patient messages**, find Lena's message and reply. Refresh the portal: the reply shows as from "Care team". *Say: clinicians, nurses and leads share this inbox, and every time it is opened is in the audit log.*
6. Still `dr_lee`: **Messages**, pick the group `patient-portal`, pick Lena Delacroix, describe a message and let the assistant draft it. Refresh the portal: nothing new. *Say: she cannot see a draft.*
7. Fill in any [TAGS], press **Approve (with any edits)**, then **Send to patient portal**. Refresh the portal: the message has arrived. *Say: AI text reaches a patient only after a clinician approves it and a person presses send.*
8. Sign in as `desk_sam`, **Schedule**: the cancel request is under **Portal requests**, with the front-desk view of the patient and no messages. Cancel the appointment the usual way, then mark the request done with a note. The portal shows the request as done. *Say: reception keeps control of the schedule.*
9. In the Terminal: `python3 scripts/verify_db.py`. *Say: every portal message and request is in the same hash-chained change log as the rest, and it verifies.*

## If something goes wrong
- **Top bar doesn't say v2.3**: close the black Terminal window and double-click *Start Clinic Assistant.command* again; it stops the old copy first.
- **"Practice mode" banner**: Ollama isn't running. Open the Ollama app, then restart.
- **Slow first answer**: the model loads once when the app starts (the Terminal window says when it's ready). After that it stays loaded for 30 minutes.
