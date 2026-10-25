# Evaluation report — Ghost Data Still Exists

Output evaluated: `output.csv`, sha256 `e03e7a16442b4547b9a99fc57f9c43d83bd8fa7cbe4ea04339e725c0782e271b`, produced by
`python code/main.py --best-effort` from the code in this archive. Every number below was measured on 2026-10-25 on
Linux / Python 3.13 and is reproduced by one command:

```bash
python code/evaluation/main.py
```

That command runs the agent on the 32 public samples (in a temporary folder), scores the dev, reserved and all splits,
runs the strict validator on the 518-case candidate and runs the synthetic scenarios.

Legend: **[measured]** reproduced by the command above · **[unverified]** depends on information we do not have (the
hidden grader).

## 1. Architecture and methodology

The agent is **deterministic first**: two models read screenshots (section 5), and everything that decides a status is
rule-based, explainable code.

| Stage | What it does | Module |
|---|---|---|
| 1. Intent | Five ordered rules: negated deletion, account kept, marketing-only opt-out, deletion vocabulary (English plus Portuguese, Spanish, French, German, Italian, Dutch, Japanese, Korean, Chinese), otherwise no deletion. Each decision returns the rule and the text span that decided it. | `ghostaudit/intent.py` |
| 2. Identity | Current snapshot plus `user_audit_log.csv` give every current and historical email, phone, hash and `user_id`; the request email can match any of them. Resources are linked only through identifiers, the evidence catalog, or activity lineage, never through timing. | `ghostaudit/identity.py` |
| 3. Primary account | Identifier links first (the account's own record, a keyed lookup, or a subject record naming the account). Only when no evidence names an account does the deletion workflow's own account event decide. Every decision carries its basis. | `ghostaudit/accounts.py` |
| 4. Evidence | JSON, TXT tables, SQL snapshots (primary and replicas), four log formats, PDF text (pypdf), screenshots (cached Gemini facts cross-checked by local OCR; OCR facts for screenshots without Gemini facts). | `evidence.py`, `documents.py`, `images.py`, `ocr.py`, `multimodal.py` |
| 5. Time | Only evidence captured at or before `audit_at`; the latest valid observation sets the state; post-dated rows are ignored; ties are recorded. | `ghostaudit/temporal.py` |
| 6. Policy and plan | `deletion_rules.csv` maps each category to DELETE / REDACT / ANONYMIZE / RETAIN / tombstone; the planner emits findings, then remediation (flows disabled and restores blocked before any record is changed), then verification, in a fixed deterministic order. | `policy.py`, `auditor.py` |
| 7. Decisions and traces | One typed `ResourceDecision` per resource (attribution, category, rule, state including explicit UNKNOWN, cited evidence); `case_traces.jsonl` holds one trace per case. If any emitted step is not backed by a decision, the run stops before publishing, also under `--best-effort`. | `decisions.py`, `main.py` |
| 8. Validation gate | `main.py` writes a candidate, runs the strict validator and publishes `output.csv` only with 0 errors. `--best-effort` publishes anyway, prints every error, records `published_despite_validation_errors` in `run_notes.json` and exits 1. | `main.py`, `evaluation/validate_output.py` |

Methodology: the 32 public samples are split into **22 development** cases (used for tuning) and **10 reserved** cases
(`code/evaluation/splits.py`). All 32 were inspected while building the agent, so the reserved split is **not** a clean
holdout; it was not used for tuning and is reported separately. Account-attribution changes were also checked
**without labels** on the 518 test requests (section 7).

## 2. Dataset size and limitations

- **Development set: 22 cases [measured].** One case is 4.5 percentage points of status accuracy.
- The local metrics are **not** the hidden judge's score **[unverified]**.
- No public sample exercises the screenshot evidence; screenshot-driven test predictions were checked by hand.

## 3. Metrics [measured]

| Metric | Dev, first baseline | **Dev, final** | Reserved (not clean) | All 32 |
|---|---|---|---|---|
| Status accuracy | 0.9545 | **1.0** (22/22) | 0.80 | 0.9375 |
| Step precision | 0.9431 | **0.9840** | 0.9362 | 0.9709 |
| Step recall | 0.8657 | **0.9179** | 0.7458 | 0.8653 |
| Step F1 | 0.9027 | **0.9498** | 0.8302 | 0.9151 |
| Field accuracy (strict) | 0.8455 | **0.9062** | 0.7482 | 0.8579 |
| Positional step accuracy | 0.763 | 0.8358 | 0.678 | 0.7876 |
| Sequence accuracy (exact case) | 0.4091 (9/22) | **0.5909** (13/22) | 0.40 | 0.5312 |
| Evidence validity / policy compliance | 1.0 / 1.0 | 1.0 / 1.0 | 1.0 / 1.0 | 1.0 / 1.0 |

Individual splits: `python code/evaluation/eval.py --pred <file> --requests dataset/sample_deletion_requests.csv
--split dev` (add `--split reserved --allow-reserved` or `--split all --allow-reserved`).

**518-case output [measured]:** 518 rows sorted by `case_id`, 349 INCOMPLETE / 159 COMPLETE / 10 NOT_APPLICABLE,
2,955 steps. Strict validator: **3 errors (R12) and 8 warnings (R31)**, section 10.

## 4. Custom evaluation scenarios [measured]

`code/evaluation/custom_scenarios.py` builds five tiny synthetic datasets (fictional people, `.test` emails), runs the
production pipeline on each and compares with an expected row written by hand from the contract before running.

| Scenario | What it checks | Expected | Result |
|---|---|---|---|
| S1 | An access request is not a deletion | NOT_APPLICABLE, [] | **PASS** |
| S2 | Workflow says COMPLETE, but a search copy remains | INCOMPLETE: finding (evidence_901), delete, verify | **PASS** |
| S3 | A snapshot captured after audit_at must be ignored | INCOMPLETE, as S2 | **PASS** |
| S4 | A later snapshot that merely omits a record does not prove absence | INCOMPLETE, as S2 | **PASS** |
| S5 | The request uses a historical email and the copy is keyed by it | INCOMPLETE, as S2 | **PASS** |

**5/5 pass.** S4 first expected COMPLETE (our first reading of the contract). Implementing that reading contradicted two
official sample answers (case_05 and case_24 keep the record as remaining although a later snapshot omits it), so the
code change was rejected and S4 now follows the official answers.

Further independent tests: `code/tests/test_intent.py` (one family per intent rule, written without dataset text),
`code/tests/test_accounts.py` (identifier, reference and corroboration links; post-cutoff evidence never links),
`code/tests/test_ocr.py` (record-local corroboration, including a real screenshot where an id sits next to another
person's row).

## 5. Evidence-validation checks [measured]

- **Citations.** Validator rules C01 (every cited id is a real file_id, activity_id or audit_id) and C03 (every cited
  item was captured at or before audit_at): the 518-case output has **0 C01 and 0 C03 errors**.
- **Claims are not proof.** A SUCCESS activity never proves absence and a FAILED one never proves presence. An
  unresolved resource is never written as ABSENT.
- **Two readers for screenshots.** Gemini facts were extracted once during development and cached by image sha256.
  At audit time a local OCR model (RapidOCR, ONNX) reads the same image. A Gemini fact is used only if the OCR text
  shows the same resource id and identifiers **inside the same record** (table row, side panel or detail header) and
  no record of that id shows another person. All 6 cached Gemini extractions agree with OCR; 2 more screenshots get
  facts from OCR alone.
- **Grounding guards** (`ghostaudit/images.py`). A resource id must match the id pattern, be known to the dataset and
  be printed in the record's own text. A state shown only by a toggle, colour or icon goes to review. A data flow is
  active only on printed status words. A state must fit the resource type.
- **Mistakes the guards caught** (each covered by a test): a connector mislabelled as "identifiers present"; a person
  id placed in the resource-id field; a screenshot whose person contradicts the catalog; a ticket number used instead
  of the resource id; an id paired with the email printed in the next table row.
- **Prompt injection.** Text in a screenshot addressed to an assistant quarantines the image; nothing in evidence is
  followed as an instruction.
- **Boolean flags.** SQL inventories store `restore_allowed` and `enabled` as `INTEGER CHECK (x IN (0,1))`. These 35
  rows were first not read as flags, and the policy verified open restores and active flows as blocked/disabled while
  citing the row that showed the opposite. Now 0/1 is read for these two schema-declared fields only; a present but
  unreadable flag is an explicit UNKNOWN that is never cited as proof. 25 regression tests
  (`code/tests/test_restore_and_flow_flags.py`); 13 of them fail on the code before the fix; 24 of 518 rows changed.

## 6. Temporal correctness checks [measured]

- S3 (above): post-audit evidence is ignored.
- Unit and repro suites cover post-dated rows, ties that keep provenance, and replica versus primary scope.
- **Pinned known defects.** `code/tests/test_audit_repro.py` keeps 12 expected-failure tests that document known
  defects (16 at first; 4 intent probes were fixed and are recorded with `fixed_in`):
  - P1–P4: log-timestamp and identifier parsing;
  - T1: a later primary 404 hides a replica copy;
  - T2: a post-dated-only resource treated as ABSENT;
  - 5 intent probes ("don't keep any of my data", and field-level removals such as "remove the old phone number" that
    are not account deletion);
  - the remaining uncited COMPLETE steps (R12).

  Equal-time ties are documented, not pinned.
- **Stale screenshot (case_33).** export_1260 was seen "Ready" 31 days before audit_at, with an expiry date in between.
  The contract has no staleness rule, so the latest observation stands.

## 7. Identity-linking reliability [measured]

| Check | Result |
|---|---|
| Per-row linking on screenshots naming several people | tests pass; identifiers are never borrowed from neighbouring rows |
| Unknown person printed on a row | unresolved, never linked by resource id (case_63) |
| Worker-event timing as identity for non-account resources | rejected: 138 of 139 in-window resources fall in several request windows |
| **Primary account basis in the 518 output (508 authorised cases)** | 152 identifier-backed (150 corroborated by the workflow event, 2 identifier only); 203 workflow-matched (21 the only candidate left, 182 the only candidate with the reported result); **145 ambiguous** (deterministic pick, flagged in the run notes); 8 none |
| Label-free check of the workflow fallback | hiding the identifier links of the confirmed cases and re-deriving them from the workflow window alone agrees 106/162 times (kept); two alternatives were measured and rejected: strict result matching with a 15-min skew (102/162), and a 120-min lead window (122/162, but it removed the accounts of the screenshot cases and lowered dev F1 to 0.898) |

The ambiguous accounts are the largest open identity risk: within one reporting batch several workflows delete accounts
with the same result, and nothing but order separates them.

## 8. Experiment history (dev metrics: status / step F1 / exact sequence)

| # | Change | Dev | Decision |
|---|---|---|---|
| 1 | deterministic baseline | 0.909 / 0.882 / 0.364 | accepted |
| 2 | worker-based identity linking | 0.909 / 0.869 / 0.409 | **rejected** (timing is not identity) |
| 3 | complete log parsing; temporal state | 0.909 / 0.882 / 0.364 | accepted |
| 4 | clause-level intent classifier | 0.955 / 0.895 / 0.409 | **rejected** (9 of 17 independent probes failed) |
| 5 | PDF text; cached screenshot facts with grounding guards | 0.955 / 0.903 / 0.409 | accepted |
| 6 | worker-event linking; more screenshots | no change | **rejected** |
| 7 | read SQL integer restore/flow flags | 0.955 / 0.903 / 0.409 | accepted (24 of 518 rows corrected) |
| 8 | identifier-first accounts, reference links, workflow corroboration | 0.955 / 0.914 / 0.500 | **accepted** |
| 9 | stricter account windows (two variants) | 0.955 / 0.910 / 0.500; 0.955 / 0.898 / 0.500 | **rejected** (lower label-free agreement / lost screenshot-case accounts) |
| 10 | a collection file takes its manifest origin as system | 0.955 / 0.938 / 0.545 | **accepted** |
| 11 | rule-based intent with explanations | **1.0 / 0.950 / 0.591** | **accepted** (dev case_05 fixed) |
| 12 | later snapshot omission = absence | 0.955 / 0.934 / 0.545 | **rejected** (contradicts official samples) |
| 13 | local OCR second reader (cross-check + facts for unread screenshots) | dev unchanged | **accepted** (2 test rows; all 6 Gemini entries agree) |
| 14 | explicit restore decisions; flag-less backup/flow = UNKNOWN | dev unchanged | **accepted** (case_264 now proven by its deny log) |
| 15 | typed decisions, case traces, trace consistency gate | output byte-identical | **accepted** |
| 16 | lineage links (a connector or restore repopulated a copy) | dev unchanged | **accepted** (1 test row: case_421) |
| 17 | phone digit normalisation (measured, not built) | 0 new links | not pursued |
| 18 | trace gate before publication; record-local OCR corroboration | output byte-identical | **accepted** (a whole-page check accepted an id paired with another row's email on a real screenshot; the record-local check rejects it) |

## 9. Rejected approaches

- **Timing as identity** (experiments 2, 6, 9): no evidence link, or measured losses.
- **Clause-level intent classifier** (experiment 4): higher dev status but failed independent probes; replaced by
  explainable rules (experiment 11).
- **"Omitted from a later snapshot = absent"** (experiment 12): contradicts official answers.
- **Inventing evidence to clear the 3 validator errors**: declined. The evidence does not establish the restore
  permission (case_55) or resolve the identity conflict (case_63), so those steps stay uncited and the errors are
  disclosed.

## 10. Known failures and unresolved validation errors

1. **3 R12 errors in the 518 output [measured]**, published with `--best-effort` and disclosed:
   - case_55, account_2595 VERIFY_RECORD_ABSENT with no evidence: assigned by the workflow fallback; its worker event
     is ten hours after case_55's report (another batch), and no evidence shows its state.
   - case_55, backup_9287 VERIFY_RESTORE_BLOCKED with no evidence: the screenshot (evidence_32) shows the subject's
     archive but no restore permission or block.
   - case_63, marketing_001 VERIFY_RECORD_ABSENT with no evidence: the catalog links it to the subject, but the
     screenshot (evidence_60) shows a live profile of a person who matches no known identity.
2. **8 R31 warnings**: cases with no primary-account step (no identifier link and no free workflow event).
3. **Dev misses the evidence cannot fix** (9 of 22 dev cases not exact): anonymized analytics profiles with no
   identifier (03, 21, 25, 27, 28; only a shared worker time window links them); retained audit records that appear
   in no participant file (18, 20) or only in a bundle captured after audit_at (23, 29); one ambiguous account pair
   (25/26).
4. **Account attribution**: 145 of 508 primary accounts are ambiguous picks (section 7).
5. **3 of 11 screenshots give no usable fact**: evidence_37 (rows print only a user reference; a state is never
   asserted from absence; its record is covered by PDF evidence_55), evidence_42 (tombstone screen prints no resource
   id), evidence_46 (object listing prints a file name but no person; case_61's attachment object_19 stays UNKNOWN).
6. **Backups and flows with no readable flag** are UNKNOWN: they are never cited as proof of a block, and in a COMPLETE
   case the resulting check stays uncited (case_55 backup_9287 above).

## 11. Separation of claims

- **Measured:** sections 3, 4, 5, 6, 7 and the 518-case validator counts.
- **Unverified:** the hidden-grader score; whether the 518 predictions match the hidden labels; whether shipping the
  derived evidence cache is allowed (no organizer guidance found).
