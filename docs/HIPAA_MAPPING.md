# Leash and the HIPAA Security and Privacy Rules

This is a design mapping for a hackathon prototype. It shows which Leash controls line up with which rules. It is not a compliance claim, a certification or legal advice. Leash handles synthetic data only.

Verification: each citation below was read on eCFR (45 CFR Part 164, version dated 2025-01-01) through eCFR's read-only API (`https://www.ecfr.gov/api/versioner/v1/full/2025-01-01/title-45.xml?part=164&section=<section>`). The public pages at the URLs shown redirected our fetch tool to a bot-check page, so we did not open them in a browser. The wording is paraphrased here, not quoted at length.

| Citation | Rule heading | Status | Public URL |
|---|---|---|---|
| 45 CFR 164.312(a)(1) | Access control | verified on eCFR | https://www.ecfr.gov/current/title-45/section-164.312 |
| 45 CFR 164.312(b) | Audit controls | verified on eCFR | https://www.ecfr.gov/current/title-45/section-164.312 |
| 45 CFR 164.312(c)(1) | Integrity | verified on eCFR | https://www.ecfr.gov/current/title-45/section-164.312 |
| 45 CFR 164.312(d) | Person or entity authentication | verified on eCFR | https://www.ecfr.gov/current/title-45/section-164.312 |
| 45 CFR 164.312(e)(1) | Transmission security | verified on eCFR | https://www.ecfr.gov/current/title-45/section-164.312 |
| 45 CFR 164.502(b) | Minimum necessary | verified on eCFR | https://www.ecfr.gov/current/title-45/section-164.502 |
| 45 CFR 164.308(a)(1)(ii)(D) | Information system activity review (required) | verified on eCFR | https://www.ecfr.gov/current/title-45/section-164.308 |

Coverage key: **covered** means Leash has a working control aimed at the rule; **partial** means it helps but does not meet the rule alone; **not provided** means Leash does not do this.

## 164.312(a)(1) Access control: partial

The standard asks for technical policies and procedures that allow access to electronic information systems only to authorized persons or software programs.

What Leash has:
- A role policy file (`policies/scheduling_assistant.toml`) that lists the tools, FHIR resource types and email domains the role may use. Anything not listed is blocked (`TOOL_NOT_ALLOWED`, `RESOURCE_NOT_ALLOWED`, `EMAIL_DOMAIN_NOT_ALLOWED`).
- A record rate limit per time window that holds the call for a human (`RECORD_RATE_EXCEEDED`).
- The policy is checked in the Rust core on every call, before the call runs.

What it does not have: unique user identification, emergency access or automatic logoff. Leash controls what an agent may do, not who a person is.

## 164.312(b) Audit controls: covered

The standard asks for mechanisms that record and examine activity in systems that use electronic patient data.

What Leash has: every decision (allow, block, hold) and every human review is appended to a JSONL audit log with the tool, the reason codes, the scores and the latency. Raw arguments and patient data are never written to it; only a SHA-256 hash of the arguments is. The dashboard shows the decision feed and the chain status, and `GET /v1/audit/verify` re-checks the log on demand.

## 164.312(c)(1) Integrity: partial

The standard asks for policies and procedures that protect electronic patient data from improper alteration or destruction.

What Leash has: the audit log is a hash chain. Editing a line, deleting a line, swapping two lines or deleting the last line is detected by `verify()` (the demo edits one line and gets `HASH_MISMATCH`). A small head file detects truncation.

Limits: this detects tampering, it does not prevent it. Someone who can rewrite the whole log and the head file together can forge a consistent chain, and Leash does not anchor the chain outside the machine. Leash protects the audit trail, not the records in the EHR.

## 164.312(d) Person or entity authentication: not provided

The standard asks for procedures to verify that a person or entity seeking access is the one claimed.

Leash does not verify who a caller is. The gateway trusts the role and session id in a tool call, and the reviewer name on an approval is a free-text field. The approve, deny and reset routes do require a shared token (`LEASH_REVIEW_TOKEN`, sent as the `X-Leash-Token` header), so the agent cannot approve its own held calls or reset the audit log. The token is one secret shared by every reviewer: it does not identify a person, and anyone who holds it can still reset the log. A real deployment would put the gateway behind the hospital's identity system. This is the largest gap in the mapping.

## 164.312(e)(1) Transmission security: partial

The standard asks for technical measures that guard against unauthorized access to electronic patient data sent over a network.

What Leash has: it limits where data may go. Email recipients must be on an allowed-domain list, the demo mail goes to a local file sink, and identifiers are replaced with typed placeholders before any request to a Nemotron model. The only off-machine destinations are two NVIDIA hosted endpoints (`https://integrate.api.nvidia.com/v1` and the NemoGuard JailbreakDetect URL on `ai.api.nvidia.com`), with synthetic data.

What it does not have: Leash does not add encryption to traffic between its own services; they run on localhost in the demo. In production the same Nemotron models can run on-premises, so patient data never has to leave the hospital.

## 164.502(b) Minimum necessary: covered, with a stated limit

The standard asks a covered entity or business associate to make reasonable efforts to limit patient information it uses, discloses or requests to the minimum needed for the purpose. The rule lists exceptions, for example disclosures to a provider for treatment and disclosures to the individual. Which exceptions apply to a given agent is a decision for the covered entity, not for Leash.

What Leash has:
- A resource allowlist per role (a scheduling assistant may read Patient, Encounter and DocumentReference, not Condition or MedicationRequest).
- Field minimization: each resource type keeps only the fields listed in the policy (`[minimize]` tables), and the rest are dropped before the agent sees them.
- Identifier redaction in document text (Rust pre-scan, then Presidio), with SSN, MRN, phone, email and date-of-birth kinds. The minimization evaluation scored precision and recall of 1.00 on templated notes, which is likely an easy test.
- A Nemotron content check, written against a HIPAA minimum-necessary policy, on outbound payloads. It can only hold a call for a human, and it still false-alarms on some ordinary calls (see [NEMOTRON.md](NEMOTRON.md)).

## 164.308(a)(1)(ii)(D) Information system activity review: partial

This required implementation specification asks for procedures to regularly review records of information system activity, such as audit logs and access reports.

What Leash has: the dashboard decision feed, the approval queue where a person reviews every held call and every high-severity block (with a Nemotron explanation and recommendation next to Approve and Deny), the audit-chain status, and an anomaly model that scores session behavior against normal scheduling work.

Limit: Leash makes review easy and records who reviewed what. It does not schedule or require reviews; that procedure belongs to the organization.
