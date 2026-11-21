// One entry per click. `sec` is the full-length timing; `cut` is the CUT_TO_3MIN timing (0 = step dropped).
// SCRIPT.md is generated from this file: npm run script-md
// Judging (TidalBYTE '26 rubric): ingenuity, technicality, interdisciplinary, real impact, pitch.
// NVIDIA Nemotron track: core model use, technical execution, AI output quality, impact, differentiation.

export interface Step {
  id: string;
  scene: number;
  sceneName: string;
  sec: number;
  cut: number;
  say: string;
  cutSay?: string;
}

export const STEPS: Step[] = [
  { id: "boot", scene: 0, sceneName: "Cold open", sec: 8, cut: 6,
    say: "(Let the counter run.) We're Leash." },
  { id: "headline", scene: 1, sceneName: "Problem", sec: 13, cut: 10,
    say: "Hospitals want AI agents working inside their records systems. But one hidden sentence in a referral can make an agent leak a patient's record." },
  { id: "stat", scene: 1, sceneName: "Problem", sec: 10, cut: 0,
    say: "We ran our own scheduling agent with no protection. In one of three live runs, it obeyed the hidden instruction." },
  { id: "record", scene: 2, sceneName: "Stakes", sec: 6, cut: 0,
    say: "Here's a synthetic patient, pt-0042." },
  { id: "leak", scene: 2, sceneName: "Stakes", sec: 11, cut: 12,
    say: "The agent read a poisoned referral, then emailed the full record, 3,965 characters, to an outside address. Every one of these fields left the building.",
    cutSay: "In one of three live runs, our unprotected agent obeyed a hidden instruction and emailed this synthetic record, 3,965 characters, to an outside address." },
  { id: "reveal", scene: 3, sceneName: "Leash", sec: 10, cut: 8,
    say: "So we built Leash, backed by NVIDIA Nemotron: a runtime security gateway for clinical AI agents." },
  { id: "archAgent", scene: 4, sceneName: "Architecture", sec: 16, cut: 10,
    say: "Here's every piece. A Nemotron agent does real work: it reads referrals and books follow-ups. Every tool call crosses the Leash gateway: Rust policy, three injection detectors, minimization, anomaly scoring, a hash-chained audit, and a Nemotron reasoner. Then the mock EHR, or a reviewer's dashboard.",
    cutSay: "Here's every piece: a Nemotron agent doing real work, the Leash gateway's six stages, the mock EHR and a review dashboard." },
  { id: "archStaff", scene: 4, sceneName: "Architecture", sec: 10, cut: 6,
    say: "For clinic staff, Clinic Assistant has its own gatekeeper: masking, guardrails, a local model, Sal's vector database and an audit log.",
    cutSay: "And Clinic Assistant, the staff front end, with Sal's vector database." },
  { id: "pipeline", scene: 5, sceneName: "Guardrail", sec: 6, cut: 5,
    say: "Let's follow one call: policy first, then the ML and Nemotron checks." },
  { id: "safe", scene: 5, sceneName: "Guardrail", sec: 10, cut: 8,
    say: "Updating an appointment for pt-0042 passes every check. In our scripted run, 17 legitimate calls went straight through." },
  { id: "unsafe", scene: 5, sceneName: "Guardrail", sec: 12, cut: 9,
    say: "Now the agent tries to email the record outside the clinic. Policy blocks it: email domain not allowed. Nothing is sent." },
  { id: "nemotron", scene: 5, sceneName: "Guardrail", sec: 14, cut: 10,
    say: "Nemotron 3.5 Lightning explains the block in plain language for the human reviewer, citing the exact rule. It is advisory: its output can only add caution, never unblock a call, and a test proves it." },
  { id: "whyNemotron", scene: 5, sceneName: "Guardrail", sec: 13, cut: 9,
    say: "Why Nemotron? Open weights, so a hospital can run it on-premises. Fast calls: 718 milliseconds at p50. And we measured it: over five eval rounds, its agreement with the reviewer's decision rose from 0.875 to 1.00.",
    cutSay: "Why Nemotron? Open weights for on-premises use, 718 millisecond calls, and reviewer agreement that rose from 0.875 to 1.00 over five eval rounds." },
  { id: "note", scene: 6, sceneName: "Patient data", sec: 5, cut: 4,
    say: "Leash also controls what a model sees." },
  { id: "redact", scene: 6, sceneName: "Patient data", sec: 9, cut: 7,
    say: "Name, record number, birth date, phone and email become tags. The clinical facts stay: INR 4.3 on warfarin." },
  { id: "audit", scene: 6, sceneName: "Patient data", sec: 8, cut: 6,
    say: "Every request goes into a hash-chained log. Edit one line and verification fails at that line." },
  { id: "ui", scene: 7, sceneName: "Clinic Assistant + vector DB", sec: 6, cut: 6,
    say: "This is Clinic Assistant, running on this machine with a local model." },
  { id: "push", scene: 7, sceneName: "Clinic Assistant + vector DB", sec: 6, cut: 7,
    say: "Nobody talks to the model directly. Every question is masked, checked, answered locally, checked again and logged." },
  { id: "demo", scene: 7, sceneName: "Clinic Assistant + vector DB", sec: 22, cut: 20,
    say: "We ask about medication interactions for a synthetic COPD patient. (Watch it follow the answer.) While the local model works, the request has already been checked. The answer arrives as a draft for a clinician, and all seven safety checks passed." },
  { id: "vectors", scene: 7, sceneName: "Clinic Assistant + vector DB", sec: 14, cut: 12,
    say: "Behind it, Sal's local vector database on SQLite: append-only, hash-chained, masked text only. It finds similar cases and catches reworded prompt injections." },
  { id: "impact", scene: 8, sceneName: "Close", sec: 12, cut: 8,
    say: "This sits where medicine, security, machine learning and policy meet. It's for clinicians and the compliance reviewers who approve AI in hospitals. Unlike general agent guardrails, Leash governs clinical actions on patient records.",
    cutSay: "Medicine, security, ML and policy, built for clinicians and the compliance reviewers who approve AI in hospitals." },
  { id: "proof", scene: 8, sceneName: "Close", sec: 12, cut: 9,
    say: "Built: the gateway and Clinic Assistant. Tested: 152 automated tests and five scripted demo assertions pass. Next: a pilot with a clinical reviewer.",
    cutSay: "Built, tested with 152 automated tests, and next: a clinical pilot." },
  { id: "team", scene: 8, sceneName: "Close", sec: 4, cut: 3,
    say: "We're Rowan, Sal, Zarek and Nico." },
  { id: "hold", scene: 8, sceneName: "Close", sec: 4, cut: 3,
    say: "Leash, backed by NVIDIA Nemotron. Thank you." },
];

export const stepsFor = (cut: boolean): Step[] =>
  cut ? STEPS.filter((s) => s.cut > 0).map((s) => ({ ...s, sec: s.cut, say: s.cutSay ?? s.say })) : STEPS;

export const totalSeconds = (cut: boolean): number => stepsFor(cut).reduce((n, s) => n + s.sec, 0);
