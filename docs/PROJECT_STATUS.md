# Project status — mapped to the architecture diagram

Snapshot: 2026-10-24. Every number below was measured in this session unless it says "from docs" (then it comes from `docs/EXPERIMENTS.md`, `docs/DECISIONS.md` or `docs/TRAP_FINDINGS.md`).
All accuracy figures are **local** (22 dev samples, `code/evaluation/eval.py`), not the hidden judge's score.

Legend: ✅ working · 🟡 working with known gaps · 🔴 missing or blocking

---

## 1. Bottom line

The pipeline in the diagram works end to end, but only as experiment code. The submission isn't ready yet:

| Blocker | Detail |
|---|---|
| 🔴 No submission entry point | `code/main.py` is empty (0 lines). The working pipeline is `experiments/exp004.py` (accepted) + `spike/exp005.py` (not accepted). Neither folder goes into `code.zip`. |
| 🔴 No root `output.csv` | It has never been written. A full 518-case run (scratchpad only) takes 1.5 s. |
| 🔴 The full run fails the validator | 8 R12 errors in 6 COMPLETE cases (33, 35, 39, 52, 55, 63): a `VERIFY_RECORD_ABSENT` step has no `evidence_id`. Dev runs never hit this. |
| 🔴 PDF / image evidence is not read | 4 PDFs + 11 PNGs are skipped. There's no API key, and no model calls have been made (D7). |
| 🔴 Required reports are missing | `code/evaluation/evaluation_report.md` and `usage_report.md` don't exist. 0 of the ≥3 required custom evaluation scenarios have been built. |
| 🟡 Intent classifier undecided | EXP-005 is conditionally accepted, but 0/80 human labels are filled in, and the last audit (log.txt, 16:08Z) recommended rejecting it. |

---

## 2. Diagram stage by stage

```
Deletion Requests CSV ✅ ─► Intent Classifier 🟡 ─► Deletion requested?
        │ No ─► NOT_APPLICABLE [] ✅ (10 rows)
        │ Yes ─► Identity Resolver 🟡 ─► Evidence Retrieval & Linking 🟡 ◄─ CSV/JSON/SQL/Logs ✅
        │                                         ▲
        │                         PDF/Images 🔴 ─► Selective AI/VLM 🔴
        │        ─► Temporal State ✅ ─► Policy Engine ✅ ─► Violations?
        │                 No ─► COMPLETE 🟡 (171)      Yes ─► INCOMPLETE ✅ (337)
        │                                                ─► Findings ─► Remediation ─► Verification ✅
        └──────────────► Deterministic Output Validator ✅ (but full run fails 🔴)
                         ─► output.csv 🔴 ─► Evaluation 🟡 ─► STARKS loop ✅
```

### 2.1 Deletion Requests CSV (518 cases) — ✅
- `dataset/deletion_requests.csv`: 518 requests. Read correctly and one row produced per case.
- Full run: 518 rows, 2,885 steps, 1.5 s, 11 MB peak memory, 0 model calls.

### 2.2 Request Intent Classifier — 🟡
| Version | State | Dev status acc. | Notes |
|---|---|---|---|
| EXP-001 keyword rule | **in the accepted baseline** | 0.909 | false negative on dev case_05 ("remaining *copy of*") |
| EXP-005 clause-level, 6 languages | conditionally accepted (D11), **not integrated** | 0.955 | 50/50 on its own synthetic set (same author); R1–R5 revisions applied |

- On the 518 test requests, EXP-004 and EXP-005 produce **byte-identical output**. The new classifier only changes dev case_05.
- Human review: `docs/intent_review_decisions.csv` has **0 of 80** reviewer decisions filled in. That blocks EXP-005 Steps 4–5.
- The last audit (log.txt) found 15 of 17 independent intent probes misclassified, and recommended rejecting EXP-005 as it stands.
- D11-P (partial-scope request → `NOT_APPLICABLE`) is approved. It's our own interpretation, because the contract doesn't specify this case.

### 2.3 Deletion requested? → NOT_APPLICABLE, `steps_json = []` — ✅
- 10 rows are `NOT_APPLICABLE` with `[]`. They match the 10 non-deletion texts found earlier (T06).
- 1 R11 warning: a row whose status isn't NOT_APPLICABLE has empty steps (from the earlier audit: one COMPLETE row with `[]`).

### 2.4 Identity Resolver (current + historical) — 🟡
- ✅ Current + historical email, email hash and `user_id` key set. Dev case_12 (link through an old email's hash only) is an exact match.
- 🟡 Historical phone links have never been tested (T01).
- 🔴 **T03, account collisions:** 4 dev cases get a neighbour's account. Under strict elimination, 9 of 21 are ambiguous. EXP-002 tried to fix this and was rejected (F1 fell from 0.882 to 0.869).
- 🔴 The full run has 7 R31 warnings: no `account_service VERIFY_RECORD_ABSENT` step (cases 127, 169, 226, 256, 301, 472, and one more).
- Earlier audit: 153 accounts are linked to a user only through negative lookups (T11 risk).

### 2.5 CSV / JSON / SQL / Logs — ✅
- 94 evidence files: 28 JSON, 26 log, 24 SQL, 1 TXT (plus 4 PDF, 11 PNG; see 2.6).
- EXP-003 parser (accepted, D9): resource-id coverage is **2,503 / 2,503 (100%)** with 0 false positives. It reads all 4 log formats. SQL runs through SQLite, replicas included.
- Earlier audit found these parser defects: dedup without timestamps can drop a final ABSENT, and log lines with fractional seconds merge records.

### 2.6 PDF / Images → Selective AI / VLM Extraction — 🔴 not started
- 15 multimodal files are skipped. Dev case_07 fails because of it (status wrong, 4 steps missing). 19 test cases have no text evidence for the subject at all (T07).
- Plan (D7, provisional): pypdf for PDFs; `claude-haiku-5-5` for PNGs, results cached. **No API key is set up and no calls have been made.**

### 2.7 Evidence Retrieval & Resource Linking — 🟡
- Works for active flows, backup restore risk, search-index leftovers, tombstones, support redaction and replica absence (from docs).
- 🔴 **T04:** already-anonymized analytics records can't be linked. 5 dev verification steps are missing, and 0 of 32 ambiguous worker actions could be resolved.
- 🟡 **T12, system attribution:** collection-style export JSON names no system, so it falls back to `object_store` (dev case_08). The full run has 30 `object_store` steps that may have the same problem.
- 🔴 **T08:** retained security audit records that aren't visible at `audit_at` (4 dev steps). This needs a contract decision.

### 2.8 Temporal State Reconstruction (state at `audit_at`) — ✅
- EXP-004 is accepted (D10). It reconstructs 14/14 within-file state sequences (the baseline managed 2/14). 0 cutoff violations, 2 post-dated rows quarantined, 16 reappearance flags.
- Known limit: a later readback of the primary alone can hide a copy still in a replica.

### 2.9 Policy Engine (15 deletion rules) — ✅
- Dev policy compliance 1.0. All 15 operations appear in the full output.
- Full-run step mix: VERIFY_RECORD_ABSENT 803, REPORT_REMAINING_RECORD 351, DELETE_RECORD 351, VERIFY_RECORD_PRESENT 288, REPORT_EXPOSED_PII 212, VERIFY_RECORD_REDACTED 177, VERIFY_DATA_FLOW_DISABLED 143, REDACT_RECORD 140, REPORT/DISABLE_DATA_FLOW 89/89, ANONYMIZE/VERIFY_ANONYMIZED 72/72, VERIFY_RESTORE_BLOCKED 58, REPORT_RESTORE_RISK/BLOCK_RESTORE 20/20.

### 2.10 Policy violations? → COMPLETE / INCOMPLETE — 🟡
- Full run: **337 INCOMPLETE · 171 COMPLETE · 10 NOT_APPLICABLE**.
- 🔴 Six COMPLETE rows claim an absence they can't cite (the R12 errors above). This is open contract item C07, "unprovable absence". These cases may need to be INCOMPLETE, or the absence step needs real evidence.

### 2.11 INCOMPLETE → Findings → Ordered Remediation → Verification — ✅
- 672 findings, 672 remediations, 1,541 verifications across the full run. Findings and remediations pair one-to-one.
- The 14-step multi-system dev cases (11, 18, 29) have correct ordering. Their remaining misses belong to T03 and T08.

### 2.12 Deterministic Output Validator — ✅ built / 🔴 full output fails
- `code/evaluation/validate_output.py`, 31 evaluator tests pass.
- Full 518-case run: **valid = False**, 8 errors (all R12), 8 warnings (7 R31, 1 R11).

### 2.13 output.csv (518 valid predictions) — 🔴
- No root `output.csv`. `dataset/output.csv` is the blank template (header only).

### 2.14 Evaluation (Accuracy / Step F1 / Sequence) — 🟡
| Metric (dev, 22 cases) | EXP-004 (accepted) | EXP-005 (pending) |
|---|---|---|
| Status accuracy | 0.909 | 0.955 |
| Step P / R / F1 | 0.933 / 0.836 / 0.882 | 0.935 / 0.858 / 0.895 |
| Exact sequence accuracy | 0.364 | 0.409 |
| Missing / extra steps | 22 / 8 | 19 / 8 |
| Evidence validity / policy compliance | 1.0 / 1.0 | 1.0 / 1.0 |

- The reserved set (10 cases) has **never been scored**.
- Custom scenarios S1–S8 are planned; **0 built** (README requires at least 3).
- `evaluation_report.md` and `usage_report.md` are missing.

### 2.15 STARKS loop (Measure → Improve → Retest) — ✅ running
| Exp. | Topic | Outcome |
|---|---|---|
| EXP-001 | deterministic baseline | accepted (D1) |
| EXP-002 | identity linking | **rejected** (D8) |
| EXP-003 | log parser | accepted (D9), commit `76b898a` |
| EXP-004 | temporal state | accepted (D10), commit `aca42dc` = current baseline |
| EXP-005 | intent classifier | conditionally accepted (D11), uncommitted, audit says reject |

- Tests: 31 evaluator + 34 experiment + 16 (EXP-002) + 17 (EXP-003 spike) + 33 (EXP-005) — **all pass** when each file is run on its own. Running `pytest experiments spike` together fails at collection because both folders have a `test_exp003.py` and a `test_exp004.py`.
- Uncommitted: `docs/DECISIONS.md`, `docs/EXPERIMENTS.md`, `docs/TRAP_FINDINGS.md`, `log.txt`, `docs/INTENT_REVIEW.md`, `docs/intent_review_decisions.csv`, all of `spike/`.

---

## 3. Open traps (from `docs/TRAP_FINDINGS.md`)

| Trap | Status |
|---|---|
| T01 historical identity | PARTIAL (phone untested) |
| T02 evidence after `audit_at` | PARTIAL (scenario S1 not built) |
| T03 account collisions | **OPEN** |
| T04 anonymized records without identifiers | **OPEN** |
| T05 log formats | FIXED |
| T06 non-deletion / negated intent | PARTIAL |
| T07 PDF / image-only evidence | **OPEN** |
| T08 retained audit records not visible at cutoff | **OPEN** |
| T09 replica drift | PARTIAL |
| T10 multi-system violations | FIXED |
| T11 lookalike identifiers | PARTIAL |
| T12 system / category attribution | PARTIAL |
| T13 state sequences in one file | FIXED |
| T14 bulk unrelated-user records | FIXED |
| T15 post-dated rows | FIXED |

---

## 4. Suggested order to reach a submittable state

1. Move the accepted pipeline (`experiments/exp001 → 003 → 004`) into `code/` and make `python code/main.py` write the root `output.csv`.
2. Fix the 8 R12 errors (decide C07: uncited absence → INCOMPLETE, or cite real evidence), so the full run validates with 0 errors.
3. Decide EXP-005: fill in the 80 reviewer labels, or drop it. It doesn't change any of the 518 test outputs today.
4. Build at least 3 custom scenarios (S1 later-evidence, S3 replica drift, S5 multilingual non-deletion), then write `evaluation_report.md` and `usage_report.md`.
5. If time allows: PDF text via pypdf (no API needed), then image extraction once an API key exists.
6. Package `code.zip` and upload `log.txt`.
