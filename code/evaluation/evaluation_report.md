# Evaluation report — Ghost Data Still Exists

Candidate evaluated: branch `d47-experiments` — the accepted release (`4f61906`, output sha256 `059df995…`, kept as
rollback) plus D47 experiments EXP-D1 (local OCR second reader), EXP-D2 (explicit restore decisions), EXP-D3 (typed
decisions and case traces) and EXP-D4 (lineage links). Candidate output sha256
`e03e7a16442b4547b9a99fc57f9c43d83bd8fa7cbe4ea04339e725c0782e271b`.
Every number below was measured on 2026-10-25 from the committed code (Linux, Python 3.13) unless marked otherwise.

Legend: **[measured]** reproduced by a command in this report · **[unverified]** depends on information we do not
have (for example the hidden grader).

## 1. Architecture and methodology

The agent is **deterministic first**. No model is called while auditing a request.

1. **Intent** (`ghostaudit/intent.py`). Five ordered, explainable rules: negated deletion, account kept (D11-P),
   marketing-only opt-out, deletion word (English plus Portuguese, Spanish, French, German, Italian, Dutch, Japanese,
   Korean, Chinese account-deletion vocabulary), otherwise no deletion. Each decision returns the rule and the text
   span that decided it.
2. **Identity.** The current snapshot plus `user_audit_log.csv` give every current and historical email, phone, hash
   and `user_id` of a person. The request email can match any of them.
3. **Primary account** (`Auditor.resolve_accounts`). Identifier links first: the account's own record or a lookup keyed
   by a subject identifier, or a subject record that names the account id. Several linked accounts are narrowed to the
   one the deletion workflow's own worker event names. Only accounts no evidence names fall back to the workflow's
   account event (request period, reported result preferred). Every decision is labelled in the run notes.
4. **Evidence.** Structured files (JSON, TXT tables, SQL snapshots with replicas), four log formats, PDFs (pypdf text)
   and screenshots are turned into observations. Screenshots are read by two independent models: structured facts that
   Gemini transcribed during development (content-addressed cache `code/evidence_cache/`), and a local OCR model
   (RapidOCR/ONNX, `ghostaudit/ocr.py`) that runs at audit time. A Gemini fact is used only if the OCR text shows the
   same resource id and identifiers; images without Gemini facts get OCR facts through the same grounding guards.
   Copies repopulated by a subject's connector or restore job (activity lineage) are linked as the subject's data.
5. **Time.** Only evidence captured at or before audit_at is used. The latest valid observation sets a resource's
   state. Post-dated rows are ignored and ties are recorded.
6. **Policy.** `deletion_rules.csv` maps each category to DELETE / REDACT / ANONYMIZE / RETAIN / tombstone. The engine
   builds findings, an ordered remediation plan and verifications.
7. **Traces.** Every resource gets a typed `ResourceDecision` (attribution, category, rule, state incl. explicit
   UNKNOWN, cited evidence); `case_traces.jsonl` holds one trace per case, and the run fails if any emitted step is
   not backed by a decision.
8. **Validation gate.** `main.py` writes a candidate, runs the strict validator and publishes `output.csv` only if there
   are 0 errors. `--best-effort` (team-lead decision C2) publishes anyway, prints every error, records
   `published_despite_validation_errors` in `run_notes.json` and exits 1.

Methodology: the 32 public samples are split into **22 development** cases (tuning) and **10 reserved** cases
(`code/evaluation/splits.py`). All 32 were inspected in earlier sessions, so the reserved split is **not** a clean
holdout; it was not used for tuning in this release and is reported separately. Account-attribution changes were also
checked **without labels** on the 518 test requests (section 7).

## 2. Dataset size and limitations

- **Development set: 22 cases [measured].** One case is 4.5 percentage points of status accuracy.
- The local metrics are **not** the hidden judge's score **[unverified]**.
- No public sample exercises the screenshot evidence; screenshot-driven test predictions were checked by hand.

## 3. Metrics [measured]

Commands: `python code/main.py --requests dataset/sample_deletion_requests.csv --output runs/dev.csv --work-dir runs/devwork`
then `python code/evaluation/eval.py --pred runs/dev.csv --requests dataset/sample_deletion_requests.csv --split dev`
(reserved / all: add `--split reserved --allow-reserved` or `--split all --allow-reserved`).

| Metric | Dev F1 baseline | **Dev release** | Reserved (not clean) | All 32 |
|---|---|---|---|---|
| Status accuracy | 0.9545 | **1.0** (22/22) | 0.80 | 0.9375 |
| Step precision | 0.9431 | **0.9840** | 0.9362 | 0.9709 |
| Step recall | 0.8657 | **0.9179** | 0.7458 | 0.8653 |
| Step F1 | 0.9027 | **0.9498** | 0.8302 | 0.9151 |
| Field accuracy (strict) | 0.8455 | **0.9062** | 0.7482 | 0.8579 |
| Positional step accuracy | 0.763 | 0.8358 | 0.678 | 0.7876 |
| Sequence accuracy (exact case) | 0.4091 (9/22) | **0.5909** (13/22) | 0.40 | 0.5312 |
| Evidence validity / policy compliance | 1.0 / 1.0 | 1.0 / 1.0 | 1.0 / 1.0 | 1.0 / 1.0 |

The reserved split is unchanged by this release (same predictions as F1).

**518-case output [measured]:** 518 rows in request order, 349 INCOMPLETE / 159 COMPLETE / 10 NOT_APPLICABLE,
2,955 steps, sha256 `e03e7a16442b4547b9a99fc57f9c43d83bd8fa7cbe4ea04339e725c0782e271b`. It differs from the accepted
release in **three rows** (D47, all test cases, no public label): case_34 gains REPORT_REMAINING_RECORD account_5762
[evidence_04, OCR]; case_53 COMPLETE -> INCOMPLETE with REPORT_EXPOSED_PII support_1034 [evidence_28, OCR]; case_421
gains REPORT_REMAINING_RECORD search_3251 [evidence_39, lineage]. Public-sample metrics are identical to the release on
every split. Strict validator: **3 errors (R12) and 8 warnings (R31)** — section 10.

## 4. Custom evaluation scenarios [measured]

`code/evaluation/custom_scenarios.py` builds five tiny synthetic datasets (a fictional person, `.test` emails) and runs
the production pipeline on each.

| Scenario | What it checks | Expected | Result |
|---|---|---|---|
| S1 | An access request is not a deletion | NOT_APPLICABLE, [] | **PASS** |
| S2 | Workflow says COMPLETE, but a search copy remains | INCOMPLETE: finding (evidence_901), delete, verify | **PASS** |
| S3 | A snapshot captured after audit_at must be ignored | INCOMPLETE, as S2 | **PASS** |
| S4 | A later snapshot that merely omits a record does not prove absence | INCOMPLETE, as S2 | **PASS** |
| S5 | The request uses a historical email and the copy is keyed by it | INCOMPLETE, as S2 | **PASS** |

**5/5 pass.** S4 previously expected COMPLETE (our reading C06b) and failed. EXP-C4 implemented that reading and it
contradicted two official sample answers (case_05, case_24 keep the record as remaining although a later snapshot
omits it); the code change was rejected and S4's expectation now follows the official answers.

Further independent tests: `code/tests/test_intent.py` (one family per intent rule, written without dataset text) and
`code/tests/test_accounts.py` (identifier, reference and corroboration links; post-cutoff evidence never links;
collection-file system attribution).

## 5. Evidence-validation checks [measured]

- **Validator rules.** C01 (every cited ID is a real file_id, activity_id or audit_id) and C03 (every cited item was
  captured at or before audit_at). The final 518-case output has **0 C01 and 0 C03 errors**.
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
- **Boolean flags (F1).** SQL inventories store `restore_allowed` and `enabled` as `INTEGER CHECK (x IN (0,1))`. Before
  F1, those 35 rows were not read as flags, and the policy verified open restores and active flows as blocked/disabled
  while citing the row that showed the opposite.
  - Now integers 0/1 are read for these two schema-declared fields only.
  - A present but unreadable flag (null, malformed, unexpected number) is an explicit unknown that is never cited as
    proof.
  - 25 regression tests (`code/tests/test_f1_flags.py`) cover the cases; 13 of them fail on the pre-F1 code.

## 6. Temporal correctness checks [measured]

- S3 (above): post-audit evidence is ignored.
- Unit and repro suites cover post-dated rows (D10-B), ties that keep provenance (D10-A), and replica versus primary
  scope.
- **Pinned known defects.** `code/tests/test_audit_repro.py` keeps 12 expected-failure tests documenting known
  defects (16 before this release; I02, I10, I11, I12 were fixed by EXP-C3 and are recorded with `fixed_in`):
  - P1–P4: log-timestamp and identifier parsing;
  - T1: a later primary 404 hides a replica copy;
  - T2: a post-dated-only resource treated as ABSENT;
  - 5 intent probes (I09, I13–I16: "don't keep any of my data", and field-level removals such as "remove the old
    phone number" that are not account deletion);
  - R12-F01: the remaining uncited COMPLETE steps.

  T3 (equal-time ties) is documented, not pinned.
- **Stale screenshot (case_33).** export_1260 was seen "Ready" 31 days before audit_at, with an expiry date
  in between. The contract has no staleness rule, so the latest observation stands.

## 7. Identity-linking reliability [measured]

| Check | Result |
|---|---|
| Per-row linking on screenshots naming several people | synthetic tests pass; identifiers never borrowed from neighbouring rows |
| Unknown person printed on a row | unresolved, never linked by resource ID (case_63) |
| Worker-event timing as identity for non-account resources (EXP-008) | rejected: 138 of 139 in-window resources fall in several request windows |
| **Primary account basis in the 518 output (508 authorised cases)** | 152 identifier-backed (150 corroborated by the workflow event, 2 identifier only); 203 workflow-matched (21 the only candidate left, 182 the only candidate with the reported result); **145 ambiguous** (deterministic pick, flagged in run notes); 8 none |
| Label-free check of the workflow fallback | hiding the identifier links of the confirmed cases and re-deriving them from the workflow window alone agrees 106/162 times (F1 window rules, kept); two alternatives were measured and rejected (strict result matching with a 15-min skew: 102/162; 120-min lead window: 122/162 but it removed the accounts of the multimodal cases and lowered dev F1 to 0.898) |

The ambiguous accounts are the largest open identity risk: within one reporting batch several workflows delete
accounts with the same result, and nothing but order separates them.

## 8. Experiment history (dev metrics: status / step F1 / exact sequence)

| Experiment | Change | Dev | Decision |
|---|---|---|---|
| EXP-001 | deterministic baseline | 0.909 / 0.882 / 0.364 | accepted |
| EXP-002 | worker-based identity linking | 0.909 / 0.869 / 0.409 | **rejected** |
| EXP-003/004 | complete log parsing; temporal state | 0.909 / 0.882 / 0.364 | accepted |
| EXP-005 | clause-level intent classifier | 0.955 / 0.895 / 0.409 | **rejected** (9 of 17 audit probes failed) |
| EXP-007/007G | PDF text; cached screenshot facts with grounding | 0.955 / 0.903 / 0.409 | accepted (D18) |
| EXP-008/009 | worker-event linking; more screenshots | no change | **rejected** |
| F1 | read SQL integer restore/flow flags | 0.955 / 0.903 / 0.409 | accepted (24 of 518 rows corrected) |
| **EXP-C1** | identifier-first accounts, reference links, workflow corroboration | 0.955 / 0.914 / 0.500 | **accepted** (1 test row changes) |
| EXP-C1b/c | strict result + 15-min skew; 120-min lead window | 0.955 / 0.910 / 0.500; 0.955 / 0.898 / 0.500 | **rejected** (label-free agreement lower / multimodal accounts lost) |
| **EXP-C2** | collection file takes its manifest origin as system | 0.955 / 0.938 / 0.545 | **accepted** (0 test rows change) |
| **EXP-C3** | rule-based intent with explanations | **1.0 / 0.950 / 0.591** | **accepted** (0 test rows change; dev case_05 fixed) |
| EXP-C4 | later snapshot omission = absence (S4) | 0.955 / 0.934 / 0.545 | **rejected** (contradicts official samples) |
| **EXP-D1** | local OCR second reader (cross-check + facts for unread screenshots) | dev unchanged | **accepted** (2 test rows; all 6 Gemini entries agree with OCR) |
| **EXP-D2** | explicit restore decisions; flag-less backup/flow = UNKNOWN | dev unchanged | **accepted** (0 rows; case_264 now proven by its deny log) |
| **EXP-D3** | typed decisions, case traces, trace consistency gate | output byte-identical | **accepted** |
| **EXP-D4** | lineage links (connector/restore repopulated a copy) | dev unchanged | **accepted** (1 test row: case_421) |
| EXP-D5 (measured, not built) | phone digit normalisation | 0 new links | not pursued |

## 9. Rejected approaches

- **Timing as identity** for non-account resources (EXP-008) and tighter account windows (EXP-C1c): no evidence link,
  or measured losses.
- **EXP-005 intent**: higher dev status but failed independent probes; EXP-C3 replaced the phrase list instead.
- **EXP-C4**: "omitted from a later snapshot = absent" contradicts official answers.
- **Reversing D18-B/D18-D to clear R12** (restore risk on case_55, catalog link on case_63): declined by the team lead
  (C2) because the evidence does not establish restore permission or resolve the identity conflict.

## 10. Known failures and unresolved validation errors

1. **3 R12 errors in the 518 output [measured]**, published best effort (decision C2):
   - case_55, account_2595 VERIFY_RECORD_ABSENT with no evidence: assigned by the workflow fallback; its worker event is
     ten hours after case_55's report (it belongs to another batch), and no evidence shows its state.
   - case_55, backup_9287 VERIFY_RESTORE_BLOCKED with no evidence: the screenshot (evidence_32) shows the subject's
     archive but no restore permission or block.
   - case_63, marketing_001 VERIFY_RECORD_ABSENT with no evidence: the catalog links it to the subject, the screenshot
     (evidence_60) shows a live profile of a person who matches no known identity.
2. **8 R31 warnings**: cases with no primary-account step (no identifier link and no free workflow event).
3. **Dev misses that the evidence cannot fix** (9 of 22 dev cases not exact): anonymized analytics profiles with no
   identifier (03, 21, 25, 27, 28; only a shared worker time window links them, D19); retained audit records that
   appear in no participant file (18, 20) or only in a bundle captured after audit_at (23, 29); one ambiguous account
   pair (25/26).
4. **Account attribution**: 145 of 508 primary accounts are ambiguous picks (section 7).
5. **3 of 11 screenshots give no usable fact**: evidence_37 (rows print only a user reference; state not asserted from
   absence; its record is covered by PDF evidence_55), evidence_42 (tombstone screen prints no resource id),
   evidence_46 (object listing prints a file name but no person; case_61's attachment object_19 stays UNKNOWN).
   evidence_04 and evidence_28 are now read by OCR (case_34, case_53).
6. **Backups and flows with no flag field** (D30 F3) are still verified as blocked/disabled.

## 11. Separation of claims

- **Measured:** sections 3, 4, 5, 6, 7 and the 518-case validator counts.
- **Unverified:** the hidden-grader score; whether the 518 predictions match the hidden labels; whether shipping the
  derived evidence cache is allowed (organizer guidance pending, D18-A).
