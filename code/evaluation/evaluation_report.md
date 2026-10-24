# Evaluation report — Ghost Data Still Exists

Baseline evaluated: **D18**, local commit `6c0533c` (production `code/main.py` + `code/ghostaudit/`).
Every number below was re-measured on 2026-10-25 from the committed code unless marked otherwise.

Legend: **[measured]** reproduced by a command in this report · **[estimate]** a judgement, not measured ·
**[unverified]** depends on information we do not have (for example the hidden grader).

## 1. Architecture and methodology

The agent is **deterministic first**. No model is called while auditing a request.

1. **Intent.** A keyword and clause rule (`ghostaudit/intent.py`) decides whether `request_text` authorises deletion.
   Requests for access, correction, export or opt-out become `NOT_APPLICABLE` with `[]`.
2. **Identity.** The current snapshot plus `user_audit_log.csv` give every current and historical email, phone, hash
   and `user_id` of a person. The request email can match any of them.
3. **Evidence.** Structured files (JSON, TXT tables, SQL snapshots with replicas), four log formats, PDFs (pypdf text)
   and screenshots are turned into observations. Screenshots are read through structured facts that Gemini transcribed
   earlier and that are stored in the content-addressed cache `code/evidence_cache/` (section 7).
4. **Time.** Only evidence captured at or before `audit_at` is used. The latest valid observation sets a resource's
   state. Post-dated rows are ignored and ties are recorded.
5. **Policy.** `deletion_rules.csv` maps each category to DELETE / REDACT / ANONYMIZE / RETAIN / tombstone. The engine
   builds findings, an ordered remediation plan and verifications.
6. **Validation gate.** `main.py` writes a candidate file, runs the strict validator and publishes `output.csv` only
   if there are 0 errors.

Methodology: the 32 public sample cases are split into **22 development** cases (tuning and measurement) and
**10 reserved** cases (`code/evaluation/splits.py`). Reserved cases were never scored during this work. The local
evaluator (`code/evaluation/eval.py`) compares predictions with the public sample answers.

## 2. Dataset size and limitations

- **Development set: 22 cases [measured].** One case is 4.5 percentage points of status accuracy. Small differences
  are noise.
- The local metrics are **not** the hidden judge's score **[unverified]**. Where the official scoring is unstated, the
  evaluator uses the strictest reading.
- **No dev case exercises the screenshot evidence.** All five predictions that screenshots changed are in the
  518-case test set, so they cannot be scored locally. They were checked by hand against the screenshots instead
  (section 5).

## 3. Development metrics (22 dev cases) [measured]

Command: `python code/main.py --requests dataset/sample_deletion_requests.csv --output runs/dev.csv --work-dir runs/devwork`
then `python code/evaluation/eval.py --pred runs/dev.csv --requests dataset/sample_deletion_requests.csv --split dev`.

| Metric | Value |
|---|---|
| Status accuracy | **0.9545** (21/22) |
| Step precision / recall / F1 | 0.9431 / 0.8657 / **0.9027** |
| Field accuracy (strict) | **0.8455** |
| Positional step accuracy | 0.763 |
| Sequence accuracy (exact case) | **0.4091** (9/22) |
| Evidence validity | 1.0 |
| Policy compliance | 1.0 |
| Validator errors / warnings (32 sample rows) | 0 / 0 |

On the full 518-case file the strict validator reports **3 errors (all R12) and 8 warnings (R31)** [measured]
(section 10).

## 4. Custom evaluation scenarios [measured]

`code/evaluation/custom_scenarios.py` builds five tiny synthetic datasets (a fictional person, `.test` emails) and runs
the production pipeline on each. Every expected row was written from the contract before running.

| Scenario | What it checks | Expected | Got | Result |
|---|---|---|---|---|
| S1 | An access request is not a deletion | NOT_APPLICABLE, [] | NOT_APPLICABLE, [] | **PASS** |
| S2 | Workflow says COMPLETE, but a search copy remains | INCOMPLETE: finding (evidence_901), delete, verify | same | **PASS** |
| S3 | A snapshot captured after audit_at must be ignored | INCOMPLETE, as S2 | same | **PASS** |
| S4 | A covering snapshot before audit_at that omits the record proves absence (contract C06b) | COMPLETE: VERIFY_RECORD_ABSENT citing evidence_902 | INCOMPLETE (record reported remaining) | **FAIL** |
| S5 | The request uses a historical email and the copy is keyed by it | INCOMPLETE, as S2 | same | **PASS** |

**4/5 pass.** S4 is a real defect (section 10, item 2). The engine finds scoped-snapshot absence only after a
resource's latest observation is already ABSENT. A later snapshot that simply omits the record does not override an
earlier PRESENT. The error is conservative: it over-reports a remaining copy rather than claiming a false deletion.

## 5. Evidence-validation checks [measured]

- **Validator rules.** C01 (every cited ID is a real file_id, activity_id or audit_id) and C03 (every cited item was
  captured at or before audit_at). The D18 518-case output has **0 C01 and 0 C03 errors**.
- **Claims are not proof.** A SUCCESS activity never proves absence, and a FAILED one never proves presence
  (contract C04). An unresolved resource is never written as ABSENT.
- **Screenshot facts.** Each of the 6 cached extractions was compared field by field with its image. Text,
  identifiers and timestamps were correct in all 6.
- **Grounding guards** (`ghostaudit/images.py`). A resource ID must match the ID pattern, be known to the dataset
  and be printed in the record's own text. A state shown only by a graphical indicator goes to review. A data flow
  is active only on printed status words. A state must fit the resource type.
- **Mistakes the guards caught** (tested):
  - a connector mislabelled as "identifiers present";
  - a person ID placed in the resource-ID field;
  - a screenshot whose person contradicts the catalog;
  - a ticket number used instead of the resource ID.
- **No dev regression.** Dev predictions were byte-identical before and after screenshot integration.

## 6. Temporal correctness checks [measured]

- S3 (above): post-audit evidence is ignored.
- Unit and repro suites cover post-dated rows (D10-B), ties that keep provenance (D10-A), and replica versus primary
  scope.
- **Pinned known defects.** `code/tests/test_audit_repro.py` keeps 16 expected-failure tests documenting known
  defects:
  - P1–P4: log-timestamp and identifier parsing;
  - T1: a later primary 404 hides a replica copy;
  - T2: a post-dated-only resource treated as ABSENT;
  - 9 intent cases (I02, I09–I16);
  - R12-F01: the remaining uncited COMPLETE steps.

  T3 (equal-time ties) is documented, not pinned.
- **Stale screenshot (case_33).** export_1260 was seen "Ready" 31 days before audit_at, with an expiry date
  in between. The contract has no staleness rule, so the latest observation stands.

## 7. Identity-linking reliability [measured]

| Check | Result |
|---|---|
| Per-row linking on screenshots naming several people | synthetic tests pass; identifiers never borrowed from neighbouring rows |
| Cross-user contamination test (real dataset, synthetic cache) | no keys from another person on any observation |
| Unknown person printed on a row | unresolved, never linked by resource ID (protects case_63) |
| Worker-event timing as identity (EXP-008) | 0 legitimate links among 145 unowned resources; timing ambiguous for 138 of 139 → rejected |
| **Account attribution in the 518 output** | **500 account steps: 186 backed by an identifier in evidence, 314 attributed only by the workflow time window** |

The last row is the largest open identity risk. It is recorded in D19 (timing alone is insufficient) and has not
yet been investigated.

## 8. Experiment history (dev metrics)

| Experiment | Change | Status / step F1 / exact | Decision |
|---|---|---|---|
| EXP-001 | deterministic baseline | 0.909 / 0.882 / 0.364 | accepted |
| EXP-002 | worker-based identity linking | 0.909 / 0.869 / 0.409 | **rejected** (lower F1, risky links) |
| EXP-003 | complete log parsing | 0.909 / 0.882 / 0.364 | accepted (D9; 518-case coverage) |
| EXP-004 | temporal state reconstruction | 0.909 / 0.882 / 0.364 | accepted (D10) |
| EXP-005 | clause-level intent classifier | 0.955 / 0.895 / 0.409 | **rejected** for production (D12; failed 9 of 17 independent audit probes) |
| EXP-006A/B | production entry point; stricter R12 | 0.909 / 0.882 / 0.364 | entry point integrated |
| EXP-007 | PDF evidence | **0.955 / 0.903 / 0.409** | integrated in D18 |
| EXP-007G | screenshot facts (Gemini), grounding, per-row linking | same dev; R12 9 → 3 on 518 | integrated in D18 |
| EXP-008 | worker-event resource linking | 0 changes | **rejected** (D19) |
| EXP-009 | last screenshots | 2 extractions failed grounding; 0 changes | **rejected** (D21) |

Measured improvement from EXP-001 to D18 on dev: status +0.045 (one case), step F1 +0.021, exact sequence +0.045 (one
case). On the 518 cases, screenshot evidence turned five COMPLETE predictions into evidence-backed INCOMPLETE ones
(case_33, 35, 39, 50, 52) and added a retained-record verification to case_45. Whether those five are right is
**[unverified]** (no labels), but each was checked against its image.

## 9. Rejected approaches

- **EXP-005 (intent).** Higher dev status, but it failed 9 of 17 independent probes (negation, other languages,
  partial requests). The simpler keyword rule stays.
- **EXP-008 (worker timing).** The dataset gives no non-temporal link. Binding principle: temporal proximity alone is
  insufficient for identity attribution.
- **EXP-009 (more screenshots).** The model omitted printed resource IDs and mislabelled a permitted stable reference
  as personal identifiers. Grounding rejected every row.
- **OCR (Tesseract, Cloud Vision).** Tesseract's installer failed its signature check, and Cloud Vision had no
  credentials. Neither was used.

## 10. Known failures and unresolved validation errors

1. **3 R12 errors in the 518 output [measured].** `output.csv` stays unpublished until they are decided.
   - case_55, account_2595: known only from one SUCCESS claim, assigned by time window.
   - case_55, backup_9287: the screenshot shows no restore permission.
   - case_63, marketing_001: the screenshot shows a person who matches no known identity and contradicts the catalog.

   The output schema cannot express "state unknown", and no valid correction exists without a policy decision.
2. **Scoped-snapshot absence (scenario S4) [measured].** Over-reports remaining copies.
3. **Dev exact-sequence misses [measured]** (13 of 22 cases not exact):
   - anonymized analytics profiles and retained audit records never linked to their person (cases 03, 18, 20, 21, 23,
     25, 27, 28, 29);
   - wrong or extra account (06, 17, 25, 29);
   - system attribution (08);
   - intent (05).
4. **Account time-window attribution** (section 7).
5. **5 of 11 screenshots unread or unusable**; their resources stay UNKNOWN.

## 11. Separation of claims

- **Measured:** sections 3, 4, 5, 6, 7 and the 518-case validator counts.
- **Estimates:** none of the metrics above.
- **Unverified:** the hidden-grader score; whether the five screenshot-driven test predictions match the hidden labels;
  whether shipping the derived evidence cache is allowed (organizer guidance pending, D18-A).
