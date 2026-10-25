# Ghost Data Still Exists

Ghost Data Still Exists is an AI-assisted deletion auditing system built for HackerRank Orchestrate. It addresses a consequential problem: a system can report that personal data was deleted while copies remain in databases, backups, logs, search indexes, or downstream services.

The project processes 518 deletion requests and evaluates whether each request is supported by the available evidence. Its pipeline starts by determining whether the user actually requested deletion. It then resolves current and historical identities, retrieves records from structured and unstructured sources, reconstructs resource states at the specified audit timestamp, and evaluates obligations across 15 deletion policies.

Evidence comes from CSV, JSON, SQL, event logs, PDFs, and screenshots. Gemini is used selectively to extract structured observations from visual material. These extractions are checked against source identifiers and stored in an integrity-verified cache, enabling reproducible offline execution without new model calls. Deterministic Python components handle temporal filtering, policy interpretation, findings, remediation planning, and output validation.

The system distinguishes deletion claims from independent verification. A worker reporting SUCCESS does not prove that every copy has disappeared. Similarly, the presence of a backup does not automatically establish a violation when legitimate retention may apply. The audit attempts to evaluate ownership, retention conditions, restore permissions, and risks of data recreation before deciding what actions are required.

Results are structured as COMPLETE, INCOMPLETE, or NOT_APPLICABLE, with ordered findings, remediation actions, verification steps, and evidence references. A strict validator checks the output contract and flags unsupported claims.

Engineering priorities include modular architecture, controlled AI usage, regression testing, reproducibility, auditable decisions, and explicit documentation of limitations. Testing includes production unit tests, evaluator checks, synthetic scenarios, and comparisons against available development samples. One investigation identified an integer flag parsing defect affecting 24 predictions; a generic correction was implemented and regression tested.

The system remains a challenge prototype rather than production certified software. Some cases have unresolved evidence validation errors, and identity attribution and temporal edge cases require additional work. Those gaps are documented rather than concealed.

The central principle is straightforward: use AI to interpret difficult evidence, but require grounded, testable reasoning before making deletion compliance claims.

---

## Technical Overview & How It Works

HackerRank Orchestrate, October 2026. The challenge contract is in [`problem_statement.md`](./problem_statement.md) and [`AGENTS.md`](./AGENTS.md).

For each request in `dataset/deletion_requests.csv`, this agent works through four questions:

- Did the person actually ask for deletion?
- Who are they, across current and historical identifiers?
- What did the evidence show at `audit_at`?
- Does every copy meet `deletion_rules.csv`?

It writes `COMPLETE`, `INCOMPLETE` or `NOT_APPLICABLE` with the ordered finding, remediation and verification steps.

The agent is **deterministic first**. No model is called while auditing a request.

| Stage | What it does | Code |
|---|---|---|
| Intent | Keyword/clause rule: access, export, correction and opt-out requests become `NOT_APPLICABLE` with `[]` | `ghostaudit/intent.py` |
| Identity | Current snapshot plus `user_audit_log.csv`, giving all historical emails, phones, hashes and user IDs | `ghostaudit/auditor.py` |
| Evidence | JSON/TXT/SQL (with replicas), four log formats, PDF text (pypdf), and screenshot facts from the evidence cache | `ghostaudit/evidence.py`, `documents.py`, `images.py`, `multimodal.py` |
| Time | Only evidence captured at or before `audit_at`; the latest valid observation wins; post-dated rows are ignored | `ghostaudit/temporal.py` |
| Policy | DELETE / REDACT / ANONYMIZE / RETAIN / tombstone per category; findings, then remediation, then verification | `ghostaudit/policy.py`, `auditor.py` |
| Gate | Strict validator; `output.csv` is published only if it reports 0 errors | `main.py`, `evaluation/validate_output.py` |

**Gemini's role is limited to evidence extraction.** Screenshots were transcribed once, during development, into structured facts with a fixed JSON schema. The facts are stored in `code/evidence_cache/`, keyed by each image's SHA-256, and the deterministic rules decide everything else. Gemini never sees a case or request and never decides a status. A transcribed fact is used only if it passes these checks:

- **The resource ID is grounded.** It must be printed in the record and known to the dataset.
- **The person is grounded.** Rows are linked to a person one by one, through each row's own printed identifiers. A row showing an unknown person is never linked through its resource ID alone.
- **The state is printed.** States shown only by a toggle, colour or icon go to review.

## Requirements

- Python 3.10 or newer (developed and tested on 3.14.3).
- `pip install -r code/requirements.txt`
  - `pypdf` is required.
  - `google-genai` is only needed for optional live extraction.
- The participant `dataset/` folder at the repository root, unchanged. The agent reads `deletion_requests.csv`, `sample_deletion_requests.csv`, `user_identities.csv`, `user_audit_log.csv`, `system_activity.csv`, `deletion_rules.csv`, `evidence_files.csv` and `evidence/`.

## Run

From the repository root:

```bash
python code/main.py
```

The run takes about 3 seconds, makes no network calls and needs no keys. The steps:

1. It writes `runs/output.candidate.csv` and `runs/run_notes.json`.
2. It runs the strict validator.
3. Only if the validator reports 0 errors does it publish `./output.csv`. Otherwise it exits with status 1 and leaves any existing `output.csv` untouched.

Useful options:

| Option | Effect |
|---|---|
| `--cases case_33,case_45` | Audit a subset (work dir only, never published) |
| `--requests PATH` | Another requests file, e.g. `dataset/sample_deletion_requests.csv` |
| `--dataset PATH` / `--output PATH` / `--work-dir PATH` | Other locations |
| `--no-evidence-cache` | Ignore screenshot facts (PDF and structured evidence only) |
| `--evidence-cache PATH` | Use another evidence cache |
| `--live-extraction` | Opt-in: call Gemini for screenshots that have no cache entry (see below) |

### Offline cached execution and reproducibility

The default run uses only `code/` and `dataset/`. A copy of just those two folders, run with an empty environment and no `.env`, reproduces the 518-row output byte for byte (checked 2026-10-25). On a cache miss a screenshot adds no observation: its resources stay UNKNOWN and are never treated as deleted. `code/evidence_cache/index.json` records the SHA-256 of every entry, and `.gitattributes` keeps those bytes unchanged across platforms.

### Optional live extraction

Only needed for new or changed screenshots. Copy `.env.example` to `.env` at the repository root and fill in your own values. Never commit `.env`.

| Variable | Meaning |
|---|---|
| `GEMINI_API_KEY_PRIMARY`, `GEMINI_API_KEY_FALLBACK_1`, `GEMINI_API_KEY_FALLBACK_2` | Keys, tried in this order; failover happens only on credential errors |
| `GEMINI_MODEL` | e.g. `gemini-3.5-flash-lite` |
| `GEMINI_ENABLED` | `true` to allow calls |
| `GEMINI_MAX_TOTAL_ATTEMPTS` | Hard cap on API requests (a persistent ledger in `runs/gemini_cache/`) |
| `GEMINI_REQUEST_TIMEOUT_SECONDS`, `GEMINI_THINKING_LEVEL`, `GEMINI_MAX_OUTPUT_TOKENS` | Request settings |
| `GEMINI_PRICE_INPUT_PER_MTOK`, `GEMINI_PRICE_OUTPUT_PER_MTOK` | Optional, for cost reporting |

```bash
cd code
python -m ghostaudit.gemini --check
```

`--check` prints the configuration and which key slots are set, without showing values or making any call. A real extraction then runs through `python code/main.py --live-extraction`, or `python -m ghostaudit.gemini --only evidence_XX`.

## Output

`output.csv`: header `case_id,deletion_status,steps_json`, one row per request, sorted by `case_id`. `deletion_status` is `COMPLETE`, `INCOMPLETE` or `NOT_APPLICABLE`. `steps_json` is a JSON array of steps, each with exactly these fields: `step_no`, `phase`, `system_id`, `resource_id`, `operation`, `state` and `evidence_id`.

- Phases come in order: FINDING, then REMEDIATION, then VERIFICATION.
- Findings and COMPLETE-case verifications cite participant evidence.
- Planned remediation and post-remediation checks use `""` as `evidence_id`.

## Validate and test

```bash
python code/evaluation/validate_output.py --output runs/output.candidate.csv
python code/main.py --requests dataset/sample_deletion_requests.csv --output runs/dev.csv --work-dir runs/devwork
python code/evaluation/eval.py --pred runs/dev.csv --requests dataset/sample_deletion_requests.csv --split dev
python code/evaluation/custom_scenarios.py
python -m unittest discover -s code/tests -p "test_*.py"
python code/evaluation/test_evaluator.py
```

What each command does:

1. The validator checks a candidate file without publishing it.
2. `main.py` runs the agent on the 32 public samples.
3. `eval.py` scores the 22 development cases against the public answers.
4. `custom_scenarios.py` runs 5 synthetic end-to-end scenarios; it exits with status 1 if any fails.
5. The two test commands run the production suites.

Results are in [`code/evaluation/evaluation_report.md`](code/evaluation/evaluation_report.md). Model usage is in [`code/evaluation/usage_report.md`](code/evaluation/usage_report.md).

## Known limitations

- **3 validator errors (R12) remain** in the 518-case output (case_55, case_63). The evidence can't establish those resources' state, so `output.csv` is not published until they are decided.
- **Scoped-snapshot absence.** A later snapshot that simply omits a record does not yet override an earlier PRESENT observation (custom scenario S4 fails). The agent over-reports remaining copies.
- **Account attribution.** 314 of 500 account steps rely on the deletion-workflow time window, not on an identifier.
- **Screenshots.** 6 of 11 have usable cached facts. The other 5 stay UNKNOWN.
- **Intent.** The rule-based classifier misses some phrasings (one dev case; 9 pinned test probes).

## Repository layout

```text
code/main.py                  entry point
code/ghostaudit/              agent package (identity, evidence, time, policy, multimodal, Gemini client)
code/evidence_cache/          screenshot facts, content-addressed by image SHA-256
code/evaluation/              validator, evaluator, splits, custom scenarios, reports
code/tests/                   production test suites
docs/                         contract, decisions (D1-D23), experiments, trap findings
log.txt                       AI-assistant transcript log (AGENTS.md)
output.csv                    518-row prediction artifact
LICENSE                       Apache 2.0 License
```
