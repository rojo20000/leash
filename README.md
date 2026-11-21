# Leash

**A runtime security gateway for clinical AI agents.** Every tool call an agent makes passes through Leash, which checks it against a role policy, strips patient data down to what the task needs, scores it with ML, writes it to a tamper-evident audit log, and then allows it, blocks it or holds it for a human.

Built for Tidal Byte 2026 by Rowan Haber, Salvador Jimenez, Zarek Haleem and Nico Pitre. Entered in the main theme and the NVIDIA "Best Use of Nemotron" track. All patient data is synthetic.

![Leash dashboard overview](docs/img/dashboard-overview.png)

## The problem

Hospitals want AI agents working inside their records systems. An agent with access to patient data can leak it, or take actions nobody approved, and the cause can be as small as one sentence hidden in a referral PDF. In our demo, an unprotected scheduling agent reads a referral that carries a hidden instruction and emails a patient's full record to an outside address. Leash is the layer that stops that, and shows a reviewer why.

The efficiency argument: an agent that is boxed in by a gateway can be given more to do on its own, because the worst case is bounded and every decision is logged.

## What the demo shows

`make demo` runs the same referral task twice, with no key and no network:

1. **Unprotected:** the agent emails the full record for patient `pt-0042` to `records-transfer@outside-clinic.example`. It lands in a local file sink.
2. **Protected:** the poisoned document read is blocked (`INJECTION_DETECTED`), an over-broad read of `Condition` records is blocked (`RESOURCE_NOT_ALLOWED`), and the email to the outside domain is blocked (`EMAIL_DOMAIN_NOT_ALLOWED`). Each block is explained in plain language by Nemotron and queued for a human. The 17 legitimate calls go through.
3. **Tamper test:** one audit line is edited, and `verify()` fails with `HASH_MISMATCH`.

Real output is in [`demo/output/scripted_run.txt`](demo/output/scripted_run.txt).

![Approval queue with Nemotron explanation](docs/img/approval-queue.png)

## How it works

```mermaid
flowchart LR
    A["Clinical agent<br/>Nemotron 3.5 Lightning<br/>(Ollama fallback)"] -->|every tool call| G
    subgraph G["Leash gateway (FastAPI)"]
        direction TB
        P["1 Policy (Rust core)<br/>tools, resources, rate, email domains"] --> I["2 Injection check<br/>TF-IDF + Nemotron judge<br/>+ NemoGuard"]
        I --> M["3 Minimize<br/>Rust pre-scan + Presidio"]
        M --> C["4 Content check<br/>Nemotron judge, HIPAA policy"]
        C --> N["5 Anomaly score<br/>IsolationForest"]
        N --> D{"Decide<br/>allow / block / hold"}
        D --> R["6 Reasoner<br/>Nemotron, advisory"]
        D --> L["7 Audit log<br/>SHA-256 hash chain"]
    end
    G -->|allowed calls| E[("Mock EHR<br/>synthetic FHIR R4")]
    G -->|allowed send_email| S[/"Email sink<br/>local file"/]
    G --> Q["Approval queue"]
    Q --> DB["Dashboard (Streamlit)<br/>feed, queue, audit status, metrics"]
    L --> DB
```

Order of checks: policy, then (for document reads) the three injection detectors, then minimization, then the content check, then the anomaly score, then the decision. The Nemotron reasoner runs only after the decision is final.

**The design rule: AI judgment where it helps humans decide, hard rules where safety requires them.** Nemotron output can only add caution, never remove it. Of the three injection detectors, only TF-IDF can block; the Lightning judge and NVIDIA NemoGuard JailbreakDetect can only escalate to a human. Nothing a model returns can unblock a call. The reasoner is advisory, and [a test](tests/test_gateway_nemotron.py) proves the decision, queue and audit records are identical whatever it returns. Details are in [docs/NEMOTRON.md](docs/NEMOTRON.md).

**NemoGuard, measured.** In eval round 5 NemoGuard JailbreakDetect flagged none of the 17 evaluation documents, including all 8 injected ones (scores between -0.82 and -0.99), so it changed no metric. It is built for direct jailbreak prompts aimed at a chatbot, not for instructions hidden inside clinical documents. It stays on because it covers that different attack class, costs about 364 ms p50 per document read, can only add caution, and `LEASH_NEMOGUARD=off` removes it.

| Piece | What it is |
|---|---|
| `crates/leash_core` | Rust core (PyO3): policy engine, hash-chained audit log, identifier pre-scan. `gateway/core_py.py` is a Python fallback with the same interface. |
| `ml/` | Prompt-injection classifier (TF-IDF + logistic regression), behavior anomaly model (IsolationForest), identifier minimization (Presidio after the Rust pre-scan). Seeded, with held-out evaluation. |
| `leash/` | Nemotron client (timeouts, retries, schema validation, recording and replay) and the reasoner. |
| `gateway/` | The pipeline and approval queue (FastAPI). |
| `agent/`, `ehr/`, `data/` | The scheduling agent, a mock EHR serving 200 synthetic FHIR R4 patients, and the seeded generator. |
| `dashboard/` | Live decision feed, approval queue with approve and deny, audit-chain status, metrics. |

## Setup and run

Prerequisites: `git`, `make`, [`uv`](https://docs.astral.sh/uv/) and a Rust toolchain (`cargo`; on Windows also the MSVC build tools). Tested on Windows 11 with Git Bash. If the Rust build fails, Leash uses the Python core and the test suite still passes.

```bash
git clone https://github.com/rojo20000/leash.git leash
cd leash
make setup      # venv with uv, requirements (incl. spaCy en_core_web_lg), Rust core build
make check      # data, cargo test, pytest, quick benchmark, scripted demo assertions
```

`make check` regenerates `metrics/results.json`; only timestamps and the quick-benchmark timings change, and the numbers in the Results tables come from the committed file. To prove the Python fallback, run `LEASH_CORE=py make check` (Git Bash).

Then:

```bash
make demo       # the narrated attack-versus-defense demo (deterministic; no key, no network)
make dashboard  # EHR :8001, gateway :8000 and Streamlit :8501 together (Ctrl+C stops all)
```

On Windows, if the window was closed or the process was started in the background, find each listener with `netstat -ano | findstr :8000` (and `:8001`, `:8501`) and stop it with `taskkill /PID <pid> /T /F`.

`make help` lists every target. Optional: put `NVIDIA_API_KEY` in a git-ignored `.env` for live Nemotron calls. Without it, `make check` and `make demo` run on recorded Nemotron responses from real API calls. `make record` refreshes the recordings and needs the key. The only off-machine destinations are `https://integrate.api.nvidia.com/v1` and `https://ai.api.nvidia.com/v1/security/nvidia/nemoguard-jailbreak-detect`, both carrying synthetic data only. Nemotron 3.5 Content Safety is not used: NVIDIA's page showed it unavailable and the API returned HTTP 404 for our key (11:28 and 13:58); the path exists behind `LEASH_NEMOTRON_SAFETY_MODEL` but has never had a live response.

## Results

Every number comes from `metrics/results.json`, produced by the seeded scripts in `make data` and `make check`.

<!-- METRICS_TABLE -->

Gateway decisions and added latency. Workload: 10 scripted-recording sessions x 20 calls + 3 bulk-read sessions x 15 read_record. Latency measured with Nemotron stages on local fallback.

| Calls | Sessions | Auto-approved | Escalated | Blocked | Added latency p50 (ms) | Added latency p95 (ms) |
|---|---|---|---|---|---|---|
| 245 | 13 | 71.4% | 16.3% | 12.2% | 7.39 | 17.14 |

Detectors, held-out.

| Detector | Precision | Recall | F1 | Test size / notes |
|---|---|---|---|---|
| injection | 1.0 | 0.853 | 0.921 | n_test 300 |
| anomaly | 0.958 | 0.911 | 0.934 | false_positive_rate_normal 5.7% |
| minimization | 1.0 | 1.0 | n/a | n_notes 240, n_spans 572 |

Anomaly recall by scenario.

| Scenario | n | Recall |
|---|---|---|
| bulk_read | 1013 | 0.85 |
| exfil_email | 63 | 1.0 |
| off_role_resources | 137 | 1.0 |
| rapid_search | 876 | 0.962 |

Rust vs Python, n = 100000 iterations.

| Operation | Rust (us) | Python (us) | Speedup |
|---|---|---|---|
| Policy check | 3.063 | 12.363 | 4.04x |
| Audit append | 241.524 | 490.046 | 2.03x |

![Dashboard metrics](docs/img/metrics.png)

## Limitations

- **Small Nemotron eval.** 40 labelled cases (24 dev, 16 holdout), and only 2 labelled over-disclosure positives. The content-safety judge still false-alarms on 3 clean cases per split and held 3 ordinary calls in the live run. Two of the three injected holdout documents are missed by every detector in the final state (combined holdout recall 0.333). The judge scored 0.667 in round 4 and 0.333 in round 5 with unchanged prompts, which is one document's difference between two live runs.
- **The live agent is not deterministic.** It followed the hidden instruction in 1 of 3 unprotected runs, so the scripted replay is the demo of record.
- **Rate limits.** The NVIDIA key returns HTTP 429 under burst traffic, and the gateway then falls back to local detectors. A lone first call can trip the anomaly model.
- **Anomaly model.** The `exfil_email` and `off_role_resources` recalls come from a deterministic guard on features that were constant in training, not from the IsolationForest itself.
- **Minimization eval is probably easy.** It uses templated notes.
- **Latency and speed-up figures.** Gateway rates and added latency were measured with the Nemotron stages on their local fallbacks; a live Lightning call adds roughly 0.7 s at p50. The audit-append speed-up from Rust varies from run to run because the append is disk-bound.
- **Prototype.** Synthetic data, one role, one policy. [docs/HIPAA_MAPPING.md](docs/HIPAA_MAPPING.md) is a design mapping, not a compliance claim.

## More

- [docs/NEMOTRON.md](docs/NEMOTRON.md): what Nemotron does, the measured revise loop, model swaps, fallbacks
- [docs/HIPAA_MAPPING.md](docs/HIPAA_MAPPING.md): controls mapped to HIPAA rules
- [docs/PITCH.md](docs/PITCH.md) and [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md): slides outline and the 3-minute demo script
- [docs/SUBMISSION.md](docs/SUBMISSION.md): submission text and hand checklist
- [DECISIONS.md](DECISIONS.md): every model choice and swap, with the evidence

## License

MIT. See [LICENSE](LICENSE).
