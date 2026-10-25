# Ghost Data Still Exists — deletion-audit agent

HackerRank Orchestrate, October 2026. A workflow can report a deletion as **Complete** while personal data survives in
replicas, logs, search indexes, exports, support attachments or backups, and while a sync job or restore can bring it
back. For each request in `dataset/deletion_requests.csv` this agent answers four questions, from evidence only:

1. **Did the person ask for deletion?** If not: `NOT_APPLICABLE`, `[]`.
2. **Who are they?** Every current and historical email, phone, hash and user id.
3. **What did the evidence show at `audit_at`?** Claims ("worker SUCCESS", "COMPLETE") are not proof.
4. **Does every copy meet `deletion_rules.csv`?** If yes: `COMPLETE` with evidence-backed verifications. If not:
   `INCOMPLETE` with findings, an ordered remediation plan and the checks that must pass afterwards.

The full contract is in [`problem_statement.md`](./problem_statement.md) and [`AGENTS.md`](./AGENTS.md).

## Quick start

```bash
pip install -r code/requirements.txt      # pypdf is the only required package
python code/main.py --best-effort         # audits all 518 requests, writes ./output.csv (seconds, offline)
python code/evaluation/main.py            # metrics on the public samples, validator, synthetic scenarios
python -m unittest discover -s code/tests -p "test_*.py"
```

Python 3.10 or newer. No network, no API key and no `.env` are needed: the run reads only `code/` and `dataset/`.

## Architecture

```text
request ──► 1 Intent ──── no deletion ──────────────────────────► NOT_APPLICABLE, []
               │ deletion
               ▼
            2 Identity     current snapshot + audit log → every current and historical identifier
               ▼
            3 Evidence     JSON · TXT · SQL replicas · logs · PDF · screenshots
               │           (cached Gemini facts, cross-checked record by record by local OCR)
               ▼
            4 Time         only evidence captured ≤ audit_at; the latest valid observation wins
               ▼
            5 Policy       DELETE · REDACT · ANONYMIZE · RETAIN · tombstone → one ResourceDecision each
               ▼
            6 Plan         FINDING → REMEDIATION (flows and restores first) → VERIFICATION
               ▼
            7 Gates        every step backed by a decision → strict validator → publish output.csv
```

| Stage | Module | Key behaviour |
|---|---|---|
| Intent | `ghostaudit/intent.py` | Five ordered rules (negated deletion, account kept, marketing-only opt-out, deletion vocabulary in ten languages, otherwise no deletion). Each decision returns the rule and the text span that decided it. |
| Identity | `ghostaudit/identity.py` | Resources are linked to a person only through printed identifiers, the evidence catalog, or activity lineage (a connector or restore that repopulated a copy). Never through timing alone. |
| Primary account | `ghostaudit/accounts.py` | Identifier links first; only when no evidence names an account does the deletion workflow's own account event decide. Each choice records its basis (confirmed, corroborated, workflow-matched, ambiguous). |
| Evidence | `ghostaudit/evidence.py`, `documents.py` | JSON, TXT tables, SQL snapshots (primary, regional, reporting, failover replicas), four log formats, PDF text (pypdf). Restore and flow flags read only from schema-declared fields; an unreadable flag is UNKNOWN. |
| Screenshots | `ghostaudit/multimodal.py`, `images.py`, `ocr.py`, `gemini.py` | Two independent readers (next section). |
| Time | `ghostaudit/temporal.py` | Evidence after `audit_at` is ignored; the latest valid observation sets the state; ties are recorded. |
| Policy and plan | `ghostaudit/policy.py`, `auditor.py` | Applies `deletion_rules.csv` per category. Remediation always disables flows and blocks restores before any record is changed; steps then follow a fixed order (operation, system, resource), so output is deterministic. |
| Decisions | `ghostaudit/decisions.py` | `ResourceDecision` (attribution, category, rule, state including UNKNOWN, cited evidence) and a `CaseTrace` per case, written to `runs/case_traces.jsonl`. |
| Entry point | `code/main.py` | Candidate → trace gate → strict validator → publish `output.csv`. |

### How AI is used, and how it is kept honest

Screenshots (admin consoles, connector screens, archive listings) need a model to read them. The agent uses two:

- **Gemini (vision LLM), development time.** Each screenshot was transcribed once into structured facts with a fixed
  JSON schema. The prompts are in [`code/prompts/`](code/prompts/). The facts are cached in `code/evidence_cache/`,
  keyed by the image's SHA-256 (each entry records the prompt version), so the audit never needs a key or a network call. Gemini never
  sees a case or a request and never decides a status.
- **RapidOCR (local ONNX OCR model), every run.** It reads the same image offline. Its text lines are cached in
  `code/evidence_cache/ocr/`, so a machine without the OCR package reproduces the output byte for byte.

A Gemini fact is used only if all of these hold:

1. **Both readers agree.** OCR shows the same resource id and every reported identifier inside the same record (table
   row, side panel or detail header), and no record of that id shows another person.
2. **The resource is grounded.** The id matches the id pattern, is known to the dataset and is printed in the record.
3. **The state is printed.** A state shown only by a toggle, colour or icon goes to review.

A screenshot without Gemini facts gets OCR-built facts that pass the same guards. Absence of an identifier is never
read as redaction. Text in an image addressed to an assistant ("ignore previous instructions…") quarantines the image.

Optional live extraction for new screenshots: copy `.env.example` to `.env`, set your own `GEMINI_*` values (never
commit `.env`), check the configuration with `cd code && python -m ghostaudit.gemini --check` (prints which key slots
are set, never their values, and makes no call), then run `python code/main.py --live-extraction`.

### Safety rules built into the code

- A worker's SUCCESS never proves absence; a FAILED one never proves presence.
- A resource with no usable observation is **UNKNOWN**, never ABSENT, and is never cited as proof.
- Every finding and every COMPLETE-case verification cites a participant `file_id`, `activity_id` or `audit_id`
  captured at or before `audit_at`. Planned remediation and post-remediation checks cite nothing.
- Records that policy retains, redacts, anonymizes or keeps as a tombstone are not deleted.
- If any step is not backed by a typed decision, the run stops before publishing (exit 2), even with `--best-effort`.

## Running

```bash
python code/main.py                 # strict: publish ./output.csv only if the validator reports 0 errors
python code/main.py --best-effort   # publish even with validator errors (each printed and recorded; exit 1)
```

Each run writes `runs/output.candidate.csv`, `runs/run_notes.json` (per-case reasoning notes and attribution basis)
and `runs/case_traces.jsonl`, then validates, then publishes.

**The submitted `output.csv` comes from `python code/main.py --best-effort`** (sha256
`e03e7a16442b4547b9a99fc57f9c43d83bd8fa7cbe4ea04339e725c0782e271b`). The validator reports 3 errors (rule R12, see
Limitations): COMPLETE-case checks that no evidence can back. They are disclosed rather than hidden behind an invented
citation.

| Option | Effect |
|---|---|
| `--best-effort` | Publish even if strict validation fails |
| `--cases case_33,case_45` | Audit a subset (written to the work dir, never published) |
| `--requests PATH` | Another requests file, e.g. `dataset/sample_deletion_requests.csv` |
| `--dataset` / `--output` / `--work-dir PATH` | Other locations |
| `--no-evidence-cache` | Ignore screenshot facts (structured and PDF evidence only) |
| `--no-ocr` | Skip the OCR reader (no cross-check, no OCR facts) |
| `--evidence-cache PATH` | Another evidence cache |
| `--live-extraction` | Call Gemini for screenshots without a cache entry (needs keys) |

## Output

`output.csv`: header `case_id,deletion_status,steps_json`, 518 rows sorted by `case_id`. `steps_json` is a JSON array;
each step has exactly `step_no`, `phase`, `system_id`, `resource_id`, `operation`, `state`, `evidence_id`. Phases are
ordered FINDING → REMEDIATION → VERIFICATION and steps are numbered from 1.

## Evaluation

`python code/evaluation/main.py` reproduces every number below. Full report:
[`code/evaluation/evaluation_report.md`](code/evaluation/evaluation_report.md); model usage:
[`code/evaluation/usage_report.md`](code/evaluation/usage_report.md).

| Public samples | Status accuracy | Step F1 | Field accuracy | Exact sequence |
|---|---|---|---|---|
| Dev (22, used for tuning) | 1.0 | 0.950 | 0.906 | 0.591 |
| Reserved (10, inspected; not a clean holdout) | 0.80 | 0.830 | 0.748 | 0.40 |
| All 32 | 0.9375 | 0.915 | 0.858 | 0.531 |

These are local metrics, not the hidden grader's score. Evidence validity and policy compliance are 1.0 on all splits.

| Test suite | Command | Result |
|---|---|---|
| Production unit and regression tests | `python -m unittest discover -s code/tests -p "test_*.py"` | 164 pass, plus 12 expected failures that pin known defects |
| Evaluator and validator tests | `python code/evaluation/test_evaluator.py` | 33 pass |
| Synthetic end-to-end scenarios | `python code/evaluation/custom_scenarios.py` | 5/5 pass |

The validator alone: `python code/evaluation/validate_output.py --output runs/output.candidate.csv`. Each rule id it
reports is explained in `code/evaluation/contract_spec.py`.

## Limitations

- **3 validator errors (R12)**: case_55 (account_2595, backup_9287) and case_63 (marketing_001) are COMPLETE-case checks
  with no evidence of the resource's state. Fixing them would need an invented citation or ownership link.
- **Account attribution**: of 508 authorised cases, 152 primary accounts are identifier-backed, 203 match the
  workflow's own account event, 145 are ambiguous within one reporting batch (flagged in the run notes) and 8 have none.
- **Unlinkable records**: anonymized analytics profiles carry no identifier, and some retained audit records appear only
  in evidence captured after `audit_at`. They are not attributed by timing.
- **Screenshots**: 8 of 11 give usable facts (6 Gemini facts confirmed by OCR, 2 from OCR alone). The other 3 print no
  resource id or no identifier, so their resources stay UNKNOWN.
- **Intent**: 5 pinned probes still fail (e.g. "don't keep any of my data"; field-level removals such as "remove my old
  phone number").

## Repository layout

```text
code/main.py                 entry point
code/ghostaudit/             agent package: intent, identity, accounts, evidence, documents, images, ocr,
                             multimodal, gemini, temporal, policy, decisions, auditor, output
code/prompts/                Gemini extraction prompts (versioned; the cache records the version used)
code/evidence_cache/         screenshot facts and OCR lines, content-addressed by image SHA-256
code/evaluation/             validator, evaluator, splits, synthetic scenarios, one-command runner, reports
code/tests/                  production test suites
log.txt                      AI coding-assistant transcript (AGENTS.md)
output.csv                   518-row predictions
```
