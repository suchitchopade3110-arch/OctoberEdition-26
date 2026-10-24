# Experiments

Format per STARKS: HYPOTHESIS → BASELINE → METHOD → MEASURE → ACCEPT / REJECT.
All metrics are local (`code/evaluation/eval.py`), never the hidden judge's score.
Development experiments use the **dev split only** (22 cases). The reserved set is scored at milestones only (D4).

---

## EXP-007: multimodal evidence extraction, PDFs only (D14 option A) — run 2026-10-24, awaiting decision

**Hypothesis.** Reading the PDF/PNG evidence lets the existing policy engine decide the 7 unprovable COMPLETE cases (and F12) from real evidence.
**Baseline.** EXP-006A production (== EXP-004 / aca42dc): 518-case validation 9 R12 errors; dev status 0.909, F1 0.882, exact 0.364.
**Method.** `spike/exp007.py` (isolated; production `code/` unchanged) subclasses the production auditor and adds observations from PDF text (pypdf, offline). Rules (generic, no case ids): resource referenced only if its id is printed, or a printed document label is mapped to it by a `LINK_RESOURCE_IDENTITY` catalog row (person identifiers are never labels); identity keys = emails, user ids, phones printed in the document; multi-subject documents link nobody; system = manifest origin if structured evidence uses it, else the catalog target system; time = manifest `captured_at`, filtered by `audit_at` as usual; state through the unchanged `infer_state()`. **PNG screenshots were not read:** no offline OCR is installed (no tesseract/easyocr/rapidocr; OpenCV and onnxruntime exist without OCR models) and no PNG method is approved.

**Extraction coverage.**
| File (captured) | Result |
|---|---|
| `account_history_report_20260718.pdf` (07-18 11:00) | statement `NST-2026-0718-1842` ↔ `export_1842` via catalog label; Ingrid Dahl's name, email, `user_18` → PRESENT_ID, `export_service` |
| `security_retention_extract.pdf` (09-05 06:30) | `audit_record_003` printed, `user_03`, retain until 2027 → present (retained) |
| `delivery_correction_attachment.pdf` (09-12 07:30) | `support_001` printed, Priya Raman's email/phone, uploaded file → PRESENT_ID, SUPPORT_ATTACHMENT |
| `legal_retention_register_20260529.pdf` | 6 subjects, no resource ids; order references join to no resource → not linked |
| 11 PNG files | not read |

**The nine R12 errors.**
| Case / resource | Outcome | Evidence |
|---|---|---|
| case_33 `export_1842` | **resolved through valid evidence**: now `REPORT_REMAINING_RECORD` + `DELETE_RECORD` + verify (case → INCOMPLETE) | `evidence_18` (07-18 11:00 ≤ audit 07-19 13:00); catalog `activity_4009` (07-18 11:07) maps the label |
| case_33 `export_1260` | **cleared, not resolved**: the case is INCOMPLETE, so its verification is a future check; its state is still UNKNOWN (PNG `evidence_23`) | none read |
| case_35 `search_428` | remains | PNG `evidence_09` |
| case_39 `data_flow_1121` | remains | PNG `evidence_14` |
| case_50 (empty COMPLETE; `analytics_7438`) | remains | PNG `evidence_19` |
| case_52 `export_1260` | remains | PNG `evidence_23` |
| case_55 `account_2595` | remains — **independently unprovable**: only a deletion-worker SUCCESS claim (04-29 09:56); no evidence file captured between it and the cutoff; the id appears in no text file | none exists |
| case_55 `backup_9287` | remains | PNG `evidence_32` |
| case_63 `marketing_001` | remains | PNG `evidence_60` |
Also **F12 resolved**: case_45 now verifies `audit_record_003` PRESENT citing `evidence_55` (still COMPLETE).

**Measured.**
| Measure | EXP-006A | EXP-007 |
|---|---|---|
| 518 validation | 9 errors (R12) · 8 warnings | **7 errors (R12)** · 8 warnings (R11 ×1, R31 ×7) → publication still blocked |
| 518 predictions changed | — | 2 rows: case_33 (COMPLETE→INCOMPLETE, +finding/remediation on `export_1842`, system corrected `object_store`→`export_service`), case_45 (+`VERIFY_RECORD_PRESENT audit_record_003`) |
| Dev status / step F1 / exact sequence | 0.909 / 0.882 / 0.364 | **0.955 / 0.903 / 0.409** |
| Dev changes | — | case_07 COMPLETE→INCOMPLETE, now an exact match (+4 gold steps, −1 extra); 21 rows identical; **0 regressions** |
| Evidence validity (dev) / cited ids after cutoff (518) | 1.0 / 0 | 1.0 / 0 |
| Runtime / model calls | 1.6 s / 0 | 0.7–1.6 s / 0 |
**Tests.** `spike/test_exp007.py` 6 synthetic tests (printed id, catalog label, person id never a label, multi-subject guard, no identifier, system fallback) — one caught a real bug (sentence-final email captured with its period) before it reached data; all pass. Evaluator 33, production 32 (18 expected failures), experiments 34 pass; official answers 0/0.

**PNG options (D14-PNG, needs the lead).** (1) Download an offline OCR engine (e.g. Tesseract or RapidOCR models) — deterministic and reproducible, but a download needs approval and UI-screenshot layout still needs parsing rules; (2) transcription of the 7 relevant screenshots by the coding agent in this session into a versioned, provenance-tagged transcript file that the lead verifies against each image before use — no paid API call, but model-made and must be disclosed; (3) the D7 model (`claude-haiku-5-5`) through the API — paid (small), needs a key and approval. None has been used.

---

## EXP-006A: production entry point (behaviour-preserving integration) — run 2026-10-24, awaiting decision

**Hypothesis.** The accepted pipeline (aca42dc: EXP-001 identity/policy + EXP-003 parser + EXP-004 temporal) can be moved into `code/` without changing any decision.
**Baseline (Phase A, reproduced).** `experiments/exp004.py`: dev status 0.909, step F1 0.882, exact sequence 0.364; 518-case diagnostic run (scratchpad only) = 518 rows, 2,885 steps, 171 COMPLETE / 337 INCOMPLETE / 10 NOT_APPLICABLE, **byte-identical to the independent auditor's own 518-case diagnostic**; strict validator: 8 errors (R12 ×8 in cases 33, 35, 39, 52, 55, 63) and 8 warnings (R11 ×1 case_50; R31 ×7 cases 63, 127, 169, 226, 256, 301, 472).
**Method.** New package `code/ghostaudit/` (`evidence.py`, `temporal.py`, `policy.py`, `intent.py`, `auditor.py`, `output.py`) and `code/main.py`. Function bodies carried over unchanged; the experiments' runtime module swaps (`base.parse_file`, `base.Index`) replaced by explicit composition; dataset path passed in, not global; provenance fields (`observed_at`, `line`, `record_time`, `scope`) are declared on `Obs`. Output contract constants come from the single source `code/evaluation/contract_spec.py`, shared with the validator. Intent stays the accepted keyword rule (EXP-005 rejected). `main.py` writes a candidate to the work dir (`runs/`, git-ignored), runs the strict validator, and publishes root `output.csv` **only** when it reports 0 errors.

| Measure | Accepted EXP-004 | EXP-006A production |
|---|---|---|
| 518 predictions | 518 rows, 2,885 steps | **byte-identical** |
| Dev (22) predictions | — | **byte-identical** |
| Dev status / F1 / exact sequence | 0.909 / 0.882 / 0.364 | 0.909 / 0.882 / 0.364 (measured, not hardcoded) |
| Observation index (2,894 obs, all fields incl. provenance), scopes, known systems, 229 re-timed manifest rows, 24/24 SQL scopes | — | identical |
| Clean copy with only `code/` + `dataset/` | — | runs; same candidate; no `experiments/`/`spike/` dependency |
| Strict validation of the full run | 8 errors | 8 errors → **`output.csv` not published**, exit 1 |
| Runtime / peak memory / model calls | 1.55 s / 10.9 MB / 0 | 1.55 s / 9.8 MB / 0 |

**Result:** behaviour preserved exactly. Root `output.csv` is (correctly) not produced because the accepted behaviour fails the contract (see EXP-006B).

## EXP-006B: evidence correctness (F01, F02, F12, F13, C07, R11/R31) — run 2026-10-24, awaiting decision

**Root causes (diagnosis with auditor case ids; no production exceptions).**
- **C07 / F01 — unproven absence emitted as COMPLETE (8 R12 errors, 6 cases) + case_50 (COMPLETE with `[]`).** Every uncited step belongs to a resource linked to the subject **only** by a data-catalog `LINK_RESOURCE_IDENTITY` activity row (`export_1260`, `export_1842`, `search_428`, `data_flow_1121`, `backup_9287`, `marketing_001`, `analytics_7438`; case_55 also has an account with no observation at all). None has a usable text observation at `audit_at` — their only text observations are captured after the cutoff. These are exactly the resources shown in the PNG/PDF evidence (e.g. `backup_restore_console_20260429.png` shows `backup_9287` with no restore block), which the pipeline does not read (T07). Code path: `auditor.audit` → `latest()` returns None → state set to ABSENT → `plan_resource` emits a verification → `evidence_for` is empty.
- **F02 — no observation interpreted as ABSENT.** `auditor.audit`: `if o is None: st = "ABSENT"`. Contract: state must be determined from available evidence; activity results are claims (C04, AGENTS §6.6). Reach: 313 UNKNOWN-state resource checks across the 518 cases (mostly accounts, normally covered by `absence_evidence`); it produces invalid output only in the 7 COMPLETE cases above.
- **F12 — missing RETAIN record silently ignored.** `policy.plan_resource`: `RETAIN` with state ABSENT emits nothing. Contract S01: retained records must remain available. Reach in data: 1 (case_45, `audit_record_003`, catalog-linked, unobserved in text).
- **F13 — post-dated observations influencing results.** D10-B already keeps them out of state selection; the remaining path is F02 (only observation post-dated → None → ABSENT; audit probe T2, now a behavioural test). Measured reach in the 518 cases: **0** (no resource is linked only through a post-dated row, no state depends on one).
- **R11 (case_50)** is a COMPLETE row with `[]`; **R31 ×7** are cases with no matched account (no workflow event fits) — inventing an account id is not supported, so they stay warnings.

**Contract position.** COMPLETE for these 7 cases is unsupported (R12; "COMPLETE only when every relevant copy has the required treatment"). INCOMPLETE is also unsupported without assumptions: it needs a FINDING that cites evidence (R13), and the only evidence of these resources' state is in unread multimodal files. Neither classification is justified → **decision D14 for the team lead; no output was changed.**

**Implemented (contract-unambiguous only).**
| Change | File / function | Effect |
|---|---|---|
| Strict validator: authorised row with `[]` is an **error** (COMPLETE → R12, INCOMPLETE → R13), R11 warning kept | `code/evaluation/validate_output.py` `_check_steps` | case_50 now an error (was a warning); official answers still 0/0 |
| 2 validator tests | `code/evaluation/test_evaluator.py` | 33 tests (was 31) |
| Internal UNKNOWN state + "UNPROVEN COMPLETE" notes (never output labels) | `code/ghostaudit/auditor.py` `Auditor.audit` | notes only; output byte-identical |
| Audit repro fixture (provenance, expected vs observed) | `code/tests/fixtures/audit_repro_cases.json`, `code/tests/test_audit_repro.py` | 28 tests: 10 pass, 18 known defects as expectedFailure |
| Clean-entry-point test | `code/tests/test_entrypoint.py` | 4 tests pass |
| SQLite connections closed | `evidence.parse_structured`, `Auditor._attach_sql_scopes` | no ResourceWarning; output unchanged |

| After EXP-006B | Value |
|---|---|
| Full-run validation | **9 errors** (R12 ×9: the 8 before + case_50), 8 warnings (R11 ×1, R31 ×7) → `output.csv` not published |
| 518 / dev predictions vs EXP-004 | byte-identical (no regression, no metric change) |
| Evidence ids cited / unknown / after cutoff | 1,097 / 0 / 0 |
| Tests | evaluator 33 OK · production 32 OK (18 expected failures) · experiments 34 OK · spike 83 OK |

**Tests not executed.** No reserved-set scoring; no PNG/PDF extraction tests (not built); `pytest experiments spike` as one collection (duplicate basenames; each file run separately instead).

---

## EXP-005 rule revisions R1–R5 (2026-10-24) — REJECTED for production integration (team lead, EXP-006 instructions)

**Why.** D11-P approved (partial scope), plus two confirmed defects from the Step 3 checks (negation window, unsupported languages). EXP-005 is **not** finally accepted: the human-reviewed labels in `docs/intent_review_decisions.csv` are still empty.

**Interpretation note (D11-P).** Treating "erase X but keep my account" — and erasure of a single named data category — as `NOT_APPLICABLE` is **our conservative interpretation of a scenario the official contract does not specify**. The contract only offers "authorises deletion" (full policy, including `rule_01 USER_PROFILE Always DELETE`) or `NOT_APPLICABLE` with `[]`; we choose not to start full-account deletion the customer did not ask for. Full-deletion requests that allow anonymous or legally required records to be retained are **not** partial scope.

**Change log (every rule change):**

| # | Change | Reason | Code |
|---|---|---|---|
| R1 | erase + keep-account / refused account deletion → not authorised, `PARTIAL_SCOPE_UNSERVED`, conflicting clauses recorded (was: authorised `PARTIAL_SCOPE`) | D11-P conditions 1–3 | `resolve()`, `Intent.conflicts` |
| R2 | erase of a single named data category without account, all-data or deleted-account context → not authorised, `PARTIAL_SCOPE_UNSERVED` | D11-P condition 6 | `ACCOUNT_WORD`, `ACCOUNT_GONE`, `GENERAL_TARGET`, `CATEGORY` |
| R3 | negation scope ends at punctuation and clause words (so, and, but, because, just, please …) | confirmed bug: "No need to confirm, just erase my profile." was rejected | `NEG_BOUNDARY`, `_negated_before()` |
| R4 | unsupported language (other scripts, Han without kana, or more unsupported than supported function words) → `ABSTAIN:UNSUPPORTED_LANGUAGE`, not authorised, flagged "requires human or approved model review" | confirmed issue: silent `NOT_APPLICABLE` | `unsupported_language()` |
| R5 | every ABSTAIN carries flag `ABSTAIN:<resolution>` | Step 3 check 1 observation | `classify_intent()` |
| T1 | existing test `test_delete_data_keep_account_is_partial_scope` now expects not authorised / `PARTIAL_SCOPE_UNSERVED` | consequence of D11-P, not a relaxation | `spike/test_exp005.py` |

`keep-account` also learned "the account … stays/remains open/active" (generic phrasing needed by an R1 test).

**Fresh independent tests.** `spike/test_exp005_revisions.py`, 15 tests written **before** the rule changes (7 failed on the unrevised classifier, as intended), generic constructions not copied from the dataset or the frozen set: partial scope (keep-account, refused account deletion, two single-category cases), full deletion with anonymous / legal retention, all-personal-data, follow-up on an already-deleted account, negation before comma/so/and plus true negations, seven unsupported-language probes (de, it, nl, tr, uk, zh, ar), six supported-language probes, ABSTAIN flag.

| Result after R1–R5 | Value |
|---|---|
| Test suites | 18 + 15 EXP-005 tests, 34 experiment tests, 31 evaluator tests — all pass |
| Frozen synthetic set (sha256 `1c5a00fd…` unchanged) | 50/50; 0 false rejections, 0 false authorisations; ABSTAIN 4/50 |
| Step 3 ABSTAIN checks | 1: 3/3 · 2: 2/2 · 3: 5/5 · 4: 7/7 · 5: 6/6 (now `UNSUPPORTED_LANGUAGE`) · 6: 2/2 |
| 540 non-reserved real texts | unchanged: 530 DELETION, 10 NON_DELETION, 0 ABSTAIN; only case_05 differs from the old rule |
| Dev (22) | byte-identical to EXP-005 before revisions: status 0.955, F1 0.895, exact 0.409, missing/extra 19/8 |
| Leakage scans | no case ids, gold/split reads, model calls, copied dataset sentences or reused synthetic texts; `experiments/` unchanged |

**Still open:** independent human labels (Steps 4–5); unsupported-language requests still produce `NOT_APPLICABLE` in the final output (now explicitly flagged for review — the only status the contract allows without authorisation); multilingual rules not native-validated; same-author caveat for the synthetic set.

---

## EXP-005 independent-review status (2026-10-24) — CONDITIONALLY ACCEPTED, not integrated

**Step 1 — review prepared.** `docs/INTENT_REVIEW.md`: 80 examples (10 non-deletion candidates, 20 real deletion requests, 50 frozen synthetic), each with the original request, a proposed label and a short interpretation; classifier predictions are not shown. Decisions go in `docs/intent_review_decisions.csv` (separate file); the frozen synthetic set keeps sha256 `1c5a00fd9ae986ae…`. **No human labels received yet.**

**Step 2 — D11 partial deletion.** Contract-supported reading: not authorised → `NOT_APPLICABLE`, flagged `PARTIAL_SCOPE_UNSERVED` (see DECISIONS.md D11-P). Classifier not changed pending decision.

**Step 3 — ABSTAIN checks** (`spike/validate_exp005_abstain.py`, probes written after EXP-005 was built, separate from the frozen set):

| Check | Result | Finding |
|---|---|---|
| 1. ambiguous requests visibly flagged | 3/3 | ABSTAIN + named resolution + reasons; the `flags` list itself is empty for ABSTAIN (an explicit flag would be clearer) |
| 2. old substring rule not reused | 2/2 | old rule replaced by a function that raises: never called; source scan clean |
| 3. contradictions cannot authorise unsupported deletion | **3/5** | both failures are PARTIAL_SCOPE (authorised by current design) — resolved if D11-P is accepted |
| 4. genuine deletion not rejected for negation elsewhere | **6/7** | **new failure:** "No need to confirm, just erase my profile." → NON_DELETION; the negation window crosses a comma and catches "No" from another phrase |
| 5. unrecognised languages handled explicitly | 6/6 internally | all six probes (de, it, nl, zh, ru, de non-deletion) → ABSTAIN/NO_ACTION, but the final output would be `NOT_APPLICABLE` with no "unsupported language" flag — a genuine deletion request in such a language would be rejected |
| 6. final status supported by contract | 2/2 | validator 0 errors on dev output; NOT_APPLICABLE ⇔ `[]` on every row |

Measured reach of the open issues on real data: 0 of 540 non-reserved texts are partial-scope or in an unsupported language; the negation-window bug did not fire on any real text (the only real-text change vs EXP-004 is case_05).

**Proposed rule revisions (not applied; each would be recorded and re-tested with fresh probes after the human review):** (i) negation scope stops at clause punctuation and must govern the erase verb; (ii) explicit `ABSTAIN` flag string on every abstention; (iii) script/stop-word language check → `UNSUPPORTED_LANGUAGE` flag routed to review instead of silent `NOT_APPLICABLE`; (iv) D11-P change if approved.

**Steps 4–5 — blocked:** independent accuracy, label corrections and the acceptance recommendation require the team lead's labels. Dev results unchanged from the run below (status 0.955, F1 0.895, exact 0.409, no regressions).

---

## EXP-005 results: deterministic clause-level intent classification (run 2026-10-24)

**Built separately** as `spike/exp005.py` (uncommitted) on the frozen accepted baseline `experiments/exp004.py` (`aca42dc`). Only the intent decision changes; parsing, identity, temporal state and policy are inherited unchanged. No model calls.

**Order of work (to keep the synthetic labels independent of the classifier):** the 50-row synthetic set (`spike/exp005_synthetic_intents.csv`, draft labels by Claude from the contract) was written and hash-frozen **before any classifier code existed** (sha256 prefix `1c5a00fd9ae986ae`; an earlier hash `ce4d837d…` was replaced only to fix a CSV quote-escaping bug in row s18, also before any classifier code).

**ABSTAIN resolution (separate from the old rule, documented in `resolve()`):**
- `PARTIAL_SCOPE` — erase some personal data while keeping the account / refusing its deletion → **authorised, flagged** (the requester did ask for deletion; suppressing it is not justified). *Limitation:* policy will still verify the account as deleted; the output format cannot express "delete X but keep the account". Needs a team-lead/contract decision before production.
- `SELF_CONFLICT` — the same target both erased and kept → **not authorised, flagged** (authorisation would be invented).
- `NO_ACTION` — nothing recognisable in a supported language → **not authorised, flagged**. *Limitation:* a deletion request written in an unsupported language would land here.

| Measure | EXP-004 (accepted) | EXP-005 |
|---|---|---|
| Synthetic set accuracy (50; draft labels) | — | **50/50** (DELETION 20/20, NON_DELETION 26/26, ABSTAIN 4/4) — first run, no changes after scoring |
| False deletion-request rejections (synthetic / real non-reserved texts) | 1 on real texts (dev case_05) | **0 / 0** |
| False deletion authorisations (synthetic) | — | **0** |
| ABSTAIN rate (synthetic / real) | — | 4/50 / 0/540 |
| Real texts whose decision changed (540, reserved excluded) | — | 1 (case_05 → DELETION); the 10 non-deletion test texts unchanged |
| Status accuracy (dev 22) | 0.909 | **0.955** |
| Step P / R / F1 (dev) | 0.933 / 0.836 / 0.882 | **0.935 / 0.858 / 0.895** |
| Exact sequence accuracy (dev) | 0.364 | **0.409** |
| Missing / extra steps (dev) | 22 / 8 | **19 / 8** |
| Citation (gold-cited steps, same evidence) | 43/43 | 44/44 |
| Validator errors / warnings | 0 / 0 | 0 / 0 |
| Runtime / index peak memory | 1.17 s / 10.7 MB | 1.18 s / 10.6 MB |

**Cases improved:** case_05 (+3 steps, status fixed, now exact; replica-drift finding reached as predicted by the T09 probe). **Regressed:** none — the other 21 dev outputs are byte-identical.
**Tests:** `spike/test_exp005.py`, 18 targeted tests (the five phrases named by the team lead, negation/double negation, six-language deletion and non-deletion, quoted text, embedded commands in both directions, multi-action, ABSTAIN resolutions, explanations). Full regression suite passes (experiments, evaluator, validator).

**Caveats (important):**
1. The synthetic set and the classifier have the **same author**. Freezing the set first prevents tuning, not shared blind spots; 50/50 is weak evidence of generalisation.
2. **User-reviewed labels are not yet available.** `docs/INTENT_REVIEW.md` lists 10 + 20 real test texts (selected by a fixed rule, predictions hidden) and the 50 synthetic rows for the team lead to label. Intent accuracy on human labels is **pending**.
3. Multilingual rules (ES, PT, FR, JA, KO) were written by Claude and are not validated by native speakers.
4. **Reserved-set integrity:** reserved texts were not classified, labelled, scored or tuned against in EXP-005. Earlier (EXP-004 proposal survey) one reserved text and its old-rule outcome were seen; the erase lexicon's "gone" also occurs in that text — it is justified independently by dev case_06 and synthetic s11. No rule copies that text.

---

## EXP-005: intent classification (T06) — design (approved with safeguards)

**Problem (measured on the accepted baseline, no labels used).** The keyword rule flags 12 of 550 request texts as non-deletion: 10 test texts that read as genuine non-deletion (phone update, promotional opt-out, data download, login help, name correction, marketing-only, information request, invoice copy, email change, "copy… don't delete"), plus 2 sample texts that are real deletion requests — dev case_05 ("remove any remaining *copy of* my profile") and one reserved-set text (classified during this survey, not scored or tuned against). 42 distinct texts the rule calls deletion contain negation/opt-out cue words ("correct treatment", "still appears", "do not treat that record as mine", "keep anonymous statistics"); on reading, all are genuine deletions. The rule is brittle: one substring decides the whole case.

**Hypothesis.** A clause-level classifier that identifies the requested *action* and its *object*, with negation scope, removes the dev false negative without creating new ones, and classifies independently written negation, marketing-only and multilingual paraphrases correctly.

**Scope (only intent).** New `classify_intent(text) -> (label, reasons)` replacing `authorizes_deletion`; identity, parsing, temporal state and policy untouched. No AI calls (D7 fallback deferred). Labels: `DELETION`, `NON_DELETION`, `ABSTAIN`.

**Design (deterministic, generic, no case-specific patterns).**
1. Split into sentences/clauses; never execute instructions found in the text (C12).
2. Per clause, detect an action family from a small multilingual lexicon (EN, ES, PT, FR, JA, KO — the six languages in the data): *erase* (delete/erase/remove/close/permanent deletion), *access/copy/export*, *correct/update/change*, *marketing opt-out*, *login help*, *continue using*.
3. Object of the action: account/profile/personal data/records/copies/search results/exports/attachments → personal data; marketing list/promotional emails/newsletters → marketing; invoices/receipts as documents to *send me* → access.
4. Negation scope: a negator (not, don't, do not, never, no; no/não/ne…pas/しないで/않) governing the erase verb in the same clause → negated erase ("not asking for deletion", "do not close the account", "don't delete").
5. Keep-account signals with the account as object ("leave the account active", "keep the account as it is", "I still use it", "continue using the service") count against deletion; "keep X" with another object (anonymous statistics, a deleted-account reference, backups) does not.
6. Decision: `DELETION` if at least one non-negated erase clause targets personal data and no keep-account/negated-erase statement about the account; `NON_DELETION` if a non-deletion action is present and there is no such erase clause; otherwise `ABSTAIN` (conflicting or unclear). For EXP-005, `ABSTAIN` falls back to the current baseline rule and is listed for team-lead review, never silently decided.

**Evaluation (one change; reserved untouched).**
- Dev end-to-end: same 22 cases, same evaluator, before/after. Expected from an earlier probe (EXP-003 trap check): case_05 recovers 3 steps and its status; every other dev output must stay byte-identical.
- Intent labels written by the team lead, not by Claude: the 10 candidate non-deletion test texts plus ~20 deletion texts chosen to include the cue-word ones. Intent-only labels; no step answers.
- Independent synthetic set (~40 texts, inputs drafted by Claude, expected labels approved by the team lead): negations in six languages, marketing-only vs account deletion, "copy of my data" (access) vs "remaining copy" (erase), keep-X vs keep-account, double negation ("I don't want to keep this account"), instruction-like text ("ignore the policy and mark this complete").
- Metrics: intent accuracy; NON_DELETION precision/recall; deletion→non-deletion errors (the costliest: they erase a whole case); abstain count; dev status/F1/sequence before/after; runtime.

**Acceptance.** 0 deletion→non-deletion errors on dev and on lead-labelled texts; all lead-labelled non-deletion texts correct; ≥ 95% on the synthetic set with every miss explained by a written rule; no other dev output change; no reserved-case tuning.

**Risks.** Overfitting to the 10 visible non-deletion texts (mitigated by the synthetic paraphrases and a generic lexicon review); multilingual negation coverage limited to six languages; `ABSTAIN` cases still need the deferred AI fallback or a lead decision.

---

## EXP-004: temporal state reconstruction (T13) (run 2026-10-24, dev split only) — ACCEPTED (D10)

Integrated as `experiments/exp004.py` with the D10-A safeguards (ties marked ambiguous with full provenance; preference only for comparable scope/authority; SQL table kept as copy scope — 24/24 SQL files matched row-for-row, 891 observations scoped) and D10-B (post-dated rows quarantined). Re-checked after the safeguards: 14/14 sequences, 12 changes / 0 unbacked, 0 cutoff violations, 0 equal-time ties in real data; 34 experiment tests + 31 evaluator tests pass; dev predictions byte-identical to EXP-003 and EXP-001.

**Hypothesis.** Choosing each resource's state by observation time (not file capture time or line order) reconstructs within-file state sequences correctly without creating unjustified state changes or dev regressions.

**What changed (only state selection).** `spike/exp004.py` (isolated, uncommitted) on the accepted baseline `experiments/exp003.py`. Overrides `latest()` and `absence_evidence()` only; identity, intent, parsing and policy unchanged. Each observation now has three separate times: observation time (log line time, or the row's own `observed_at`/`recorded_at` — 229 manifest rows re-timed because the baseline parser drops `recorded_at`), availability (file `captured_at`), and the case cutoff. Rules: usable = captured ≤ `audit_at` and observed ≤ `audit_at`; latest observation time wins; line order never used; same-snapshot tie → a present copy wins (replica scope); cross-source tie → least-compliant state kept and flagged; rows dated after their own file's capture are flagged and ignored (T15); ABSENT → present is flagged as reappearance without assuming a cause.

| Measure | EXP-003 (accepted) | EXP-004 |
|---|---|---|
| Status accuracy (dev) | 0.909 | 0.909 |
| Step P / R / F1 (dev) | 0.933 / 0.836 / 0.882 | 0.933 / 0.836 / 0.882 |
| Exact sequence accuracy (dev) | 0.364 | 0.364 |
| Missing / extra steps (dev) | 22 / 8 | 22 / 8 |
| Citation (gold-cited steps, same evidence) / evidence validity | 43/43 / 1.0 | 43/43 / 1.0 |
| Temporal consistency violations (all resources × 81 case cutoffs) | 0 | 0 |
| The 14 state-sequence pairs reconstructed correctly | 2 / 14 | **14 / 14** |
| Distinct state changes vs baseline (all resources × 81 cutoffs) | — | 12, all backed by a strictly later reliable observation |
| False-positive state changes | — | **0** |
| Reappearance flags / post-dated rows ignored | — | 16 / 2 |
| Runtime (index + 22 cases) / index peak memory | 1.00 s / 10.6 MB | 1.07 s / 11.1 MB |
| Model calls / tokens | 0 | 0 |

"Correct" for the 14 pairs = the state of the last reliable (not post-dated) observation inside that file, checked against the raw rows. **Dev:** outputs byte-identical to EXP-003 — no dev case touches these resources; no accuracy gain claimed. **Reach:** 11 of the 12 changed accounts belong to requesting users in the unlabelled test set (0 dev, 0 reserved). **Tests:** 15 synthetic tests at first run; 17 after the D10-A safeguards (`experiments/test_exp004.py`), all pass. **Limitation:** a later primary-only readback cannot speak for a replica copy; without per-copy provenance in the baseline index, the latest observation still wins across files.

---

## EXP-003: evidence parsing completeness (T05) (run 2026-10-24, dev split only) — ACCEPTED (D9)

Integrated as `experiments/exp003.py` on the reference `experiments/exp001.py`. Re-run from the tracked location before commit: 17 parser tests pass, 31 evaluator tests pass, official answers validate 0/0, dev predictions byte-identical to the spike run and to EXP-001.

**Hypothesis.** Parsing the unsupported log formats raises extraction coverage to ≥ 98% of resource ids in text evidence with no false positives and no loss of dev correctness.

**What changed (only log parsing).** `spike/exp003.py` builds the EXP-001 index with a new log parser; every other evidence type, linking, state, policy, ordering and citation come unchanged from the frozen `spike/exp001.py` (sha256 prefix `20ac6058552b615e`). Formats are detected per line (KV, BRACKET, ESCAPED, JSON); continuation lines join the previous record; malformed lines are counted and skipped; exact duplicates are dropped; each observation keeps file id, capture time, line time and line number. For the new formats only, a log `service`/`function` value is used as `system_id` only if structured evidence also names it as a system (otherwise the baseline fallback applies).

**Parser measurement (all 94 manifest files; 78 text files contain resource ids).** Denominator = distinct ids per file that sit in a resource position (after a `resource_id` key, SQL row key, or pipe-table column): 2503. Ids found only in reference fields (`source_resource_id`): 3, excluded by design.

| | EXP-001 | EXP-003 |
|---|---|---|
| Coverage (resource positions) | 2080 / 2503 = 83.1% | **2503 / 2503 = 100%** (target ≥ 98% ✓) |
| Extraction precision | 2080 / 2423 (343 malformed ids with stray backslashes) | **2503 / 2503**, 0 false positives |
| Files changed | — | evidence_53 (0→300), evidence_34 (0→44), evidence_25 (0→43), evidence_06 (0→36) |
| Resource→user links (exact key) | — | +463 new, 0 lost (incl. +46 from bracket trace joins in evidence_16/44) |
| New links reaching requesting users with evidence ≤ their `audit_at` | — | dev 0 · test 83 (unscored) · reserved 0 (3 exist only after cutoff; not scored) |
| Within-file state conflicts found | not detected | 14 (new trap T13) |

**Scored comparison (same 22 dev cases, same evaluator).**

| Metric | EXP-001 | EXP-003 |
|---|---|---|
| Status accuracy | 0.909 | 0.909 |
| Step P / R / F1 | 0.933 / 0.836 / 0.882 | 0.933 / 0.836 / 0.882 |
| Exact sequence accuracy | 0.364 | 0.364 |
| Missing / extra steps | 22 / 8 | 22 / 8 |
| Citation (gold-cited steps, same evidence id) | 43/43 | 43/43 |
| Validator errors / warnings | 0 / 0 | 0 / 0 |
| Runtime (index + 22 cases) / index peak memory | 0.24 s / 7.5 MB | 1.0 s / 10.6 MB |
| Model calls / tokens / cost | 0 | 0 |

**Improvements / regressions on dev:** none — all 22 outputs are byte-identical to EXP-001, because no dev case depends on the newly parsed files. No accuracy improvement is claimed.
**Tests:** `spike/test_exp003.py`, 17 synthetic tests, all pass.
**New traps:** T13 (state sequences inside one file), T14 (bulk unrelated-user records; 0 false associations measured). T12 partly explained (bracket-log system errors were this parsing defect; case_08 is a different cause).

**Assessment.** Meets the coverage target with 100% precision and no dev regression; the accuracy benefit is unverified (it can only show on cases that use these files, none of which are labelled). Accepted by the team lead on that basis.

---

## EXP-002: resource identity linking (run 2026-10-24, dev split only) — REJECTED

**Hypothesis.** Linking resources through deletion-worker activity, with grounded elimination instead of timing tie-breaks, fixes M1 (anonymized records) and M2 (neighbouring accounts) and raises step F1 above EXP-001's 0.882.

**What changed (only linking).** `spike/exp002.py` subclasses the frozen EXP-001 auditor (`spike/exp001.py`, sha256 prefix `20ac6058552b615e`, unchanged). Every link carries source + confidence (identifier/catalog = high; workflow elimination = medium; failed lookup = weak hint, accepted only with workflow corroboration). Accounts and worker actions are assigned by elimination only; ambiguity is recorded with all candidates. Only requests submitted ≤ `audit_at` and events ≤ `audit_at` compete. Workflow events never set state (SUCCESS ≠ absent). Two output policies when an account stays ambiguous: `omit` (primary) and `flag` (ranked choice, confidence low).

**Disclosure.** The account window (−3 h / +1 h around `reported_at`) was chosen after the EXP-001 analysis had looked at timing on all 32 samples, reserved included. Windows only generate candidates; they never create a link alone.

| Metric (local, dev, 22 cases) | EXP-001 (baseline) | EXP-002 omit | EXP-002 flag |
|---|---|---|---|
| Status accuracy | 0.909 | 0.909 | 0.909 |
| Step precision / recall / F1 | 0.933 / 0.836 / **0.882** | **0.964** / 0.791 / 0.869 | 0.908 / 0.806 / 0.854 |
| Exact sequence accuracy | 0.364 (8) | **0.409 (9)** | 0.409 (9) |
| Missing / extra steps | 22 / 8 | 28 / **4** | 26 / 11 |
| Citation: gold-cited steps reproduced with same evidence | 43/43 | 40/40 | 42/42 |
| Validator errors / warnings | 0 / 0 | 0 / 9 (R31: account step omitted) | 0 / 0 |
| Runtime | 0.24 s | 38 s | 34 s |
| Model calls / tokens / cost | 0 | 0 | 0 |

**Step changes, omit vs EXP-001:** 1 fixed (case_06 account), 4 wrong account steps removed (06, 17, 25, 29), 7 previously-correct account steps now omitted as ambiguous (18, 20, 21, 22, 23, 27, 28). No new wrong steps. No status change.
**M1 (anonymized records):** 0 linked; 32 ungrounded worker actions across 8 dev cases all ambiguous.
**M2 (accounts):** wrong links 4 → 0; 9 of 21 deletion cases ambiguous (3–6 candidates each). Sources for the rest: 6 failed-lookup + workflow window, 5 workflow elimination, 1 identifier.
**Targeted tests:** `spike/test_exp002.py`, 16 synthetic tests (collisions, indirect links, false matches, cutoff) — all pass.

**Decision: REJECT** under the acceptance condition (measured F1 and correct-step count went down: 112 → 106 correct steps). Kept as findings, not code:
1. EXP-001's 0.882 rests partly on unflagged tie-break guesses (right in 7 of the 9 ambiguous cases).
2. A failed lookup is not ownership evidence on its own (T11; removed the case_17 wrong step).
3. Anonymized-record ownership is not recoverable by elimination from participant data in dev (T04).
4. Runtime grows to ~35 s for 22 cases (per-cutoff recomputation); needs caching before any 518-case run.

---

## EXP-001 results (run 2026-10-24, dev split only, 22 cases)

Code: `spike/exp001.py` (git-ignored, throwaway). Command:
`python spike/exp001.py --cases <DEV ids from splits.py> --out spike/dev_predictions.csv --notes spike/exp001_run.json`
then `python code/evaluation/eval.py --pred spike/dev_predictions.csv --split dev`.

| Metric (local, dev only) | Run 1 (as first written) | Run 2 (system-id bug fixed) | Threshold |
|---|---|---|---|
| Status accuracy | 0.909 (20/22) | **0.909 (20/22)** | ≥ 0.90 ✓ |
| Step precision / recall / F1 | 0.692 / 0.619 / 0.654 | **0.933 / 0.836 / 0.882** | F1 ≥ 0.80 ✓ |
| Step F1 ignoring evidence | 0.661 | 0.890 | — |
| Field accuracy (strict) | 0.610 | 0.821 | — |
| Sequence accuracy (exact case) | 0.091 (2/22) | 0.364 (8/22) | — |
| Citation: gold-cited steps reproduced with the same evidence id | not measured | **43/43** | — |
| Validator errors / warnings | 0 / 0 | 0 / 0 | 0 errors ✓ |
| Runtime (index + 22 cases) | 0.26 s | 0.24 s | — |
| Model calls / tokens / cost | 0 / 0 / $0 | 0 / 0 / $0 | — |

**Run 1 → run 2 change.** One bug that contradicted the EXP-001 design ("system from evidence context"): the code let an activity-derived prefix guess override the system named by the evidence, so `audit_record_*` became `archive_service`, `support_*` became `search_service`. Fixed by giving evidence context priority. No other change between runs.

**Contamination checks (all passed):** no case/resource/file ids in spike code; `sample_output.csv` never opened by the spike; no network/model imports; 0 reserved cases predicted.

**Remaining misses in run 2 (22 missing + 8 extra steps), by root cause:**

| # | Root cause | Cases | Missing / extra steps | Status errors |
|---|---|---|---|---|
| M1 | Records tied to the subject only by the deletion worker's own actions (anonymized analytics in COMPLETE cases carry no identifier) | 03, 21, 25, 27, 28 | 5 / 0 | 0 |
| M2 | Account resolution picks a neighbouring request's account (time-window matching ambiguous) | 06, 17, 25, 29 | 3 / 4 | 0 |
| M3 | Retained security audit record not observable at `audit_at`: absent from all participant text (18, 20) or only in a later file (23, 29) | 18, 20, 23, 29 | 4 / 0 | 0 |
| M4 | Multimodal evidence skipped (PDF attachment) | 07 | 4 / 1 | 1 |
| M5 | Intent false negative: "remove any remaining **copy of** my…" hit the non-deletion pattern "copy of" | 05 | 3 / 0 | 1 |
| M6 | System fallback: collection-style JSON names no system; prefix map says `object_store` instead of `export_service` | 08 | 3 / 3 | 0 |

**Parser coverage (all 94 files, not only dev):** 82.9% of resource ids present in text evidence were extracted. Four log files in other formats (`[LEVEL] [service] [trace] event: k="v"` and escaped `message="k=\"v\""`) are missed entirely (423 ids). Dev cases don't depend on them; the 518-case set very likely does.

**Families that work:** active data flows, backup restore risk, search-index leftovers, tombstones, support-message redaction, replica-snapshot absence, explicit 404 absence, historical email/hash linking (case_12).
**Families that fail:** COMPLETE cases with already-anonymized records (M1), shared-window accounts (M2), PDF/image-only resources (M4), negation-sensitive intent (M5).

**Decision:** hypothesis ACCEPTED (both thresholds met; status only narrowly, 20/22). Deterministic core is viable (D1). Next improvement awaits the team lead.

---

## EXP-001: How far does a no-AI pipeline get? (design)

**Question.** How much of the dev split can deterministic parsing + policy rules reproduce, and where is AI actually needed?

**Hypothesis.** A deterministic spike reaches step F1 ≥ 0.80 and status accuracy ≥ 0.90 on the 22 dev cases, with zero validator errors. The remaining misses cluster in: category calls (P18), image/PDF-only resources (C09), and citation choice (C06/C10).

**Baseline.** None exists. The floor is the trivial answer "every case INCOMPLETE with only an account check", scored by the same evaluator so the spike's gain is measurable.

**Scope (throwaway, in `spike/`, git-ignored, never submitted):**
1. Evidence index over all text formats (SQL via `sqlite3` in-memory, JSON snapshots, pipe-table handover, key=value logs joined on `trace_id`). One row per observation: `file_id, captured_at, system_id, resource_id, collection/category, subject keys found, state signal`.
2. Identity keys from `user_identities.csv` + `user_audit_log.csv` (I01–I03).
3. Account ID from `system_activity.csv` (R31).
4. Filter observations by `captured_at <= audit_at` (T01/T02); latest observation per resource (T04).
5. Rule mapping per contract §6; status per S01; step order per R15/R16; citation per C02/C06/C10.
6. Intent: keyword rule only (no AI). Images/PDFs: skipped (expected to cost case_07 and part of case_04).

**Guards against contamination.**
- The spike reads only `dataset/` participant files and **never** reads `sample_output.csv`; the evaluator reads it separately.
- No case IDs, resource IDs or file IDs in spike code (grep check before reporting).
- The reserved 10 cases are not scored.

**Measure.** `python code/evaluation/eval.py --pred spike/dev_predictions.csv --split dev --json-out spike/exp001.json`
Report: status accuracy, step P/R/F1, step-core F1, field accuracy, sequence accuracy, validator errors, runtime. Group every miss by cause and by contract rule.

**Accept / reject.**
- Accept the deterministic core (D1) if hypothesis holds → proceed to production design (`docs/architecture.md`).
- If step F1 < 0.6 → stop, re-read the contract and the misses before writing more code (STARKS: re-derive after repeated failures).
- Either way: the miss list decides where AI is allowed (D3), not intuition.

**Budget.** ~1.5–2 h. Zero model calls, zero cost.

---

## Independent evaluation scenarios (planned)

We write these ourselves; they are not derived from the reserved set. Each is a small fixture (requests + evidence + expected answer) that runs through the same evaluator, and it is documented in `code/evaluation/evaluation_report.md` (the code judge ignores `.csv`/`.json`, README "Important").

| # | Scenario | What it proves | Expected handling (contract rule) |
|---|---|---|---|
| S1 | **Later evidence trap**: same case, plus a file captured *after* `audit_at` showing the record deleted | Time cutoff is respected | Answer unchanged; later file never cited (T01, C03) |
| S2 | **Historical hash only**: record linked solely by the SHA-256 of an old email | Historical identity resolution | Record found and treated per policy (I02, I03) |
| S3 | **Replica drift**: record absent in primary, present in a read replica | Drift detection under the logical system | `REPORT_REMAINING_RECORD` on the logical `system_id` (C08) |
| S4 | **Active legal hold**: a record that would be deleted, but a legal hold is active | Retention beats deletion | `VERIFY_RECORD_PRESENT`, no delete (P13, P17) |
| S5 | **Negated / multilingual non-deletion**: "no quiero borrar la cuenta, solo dejar de recibir correos" | Intent detection | `NOT_APPLICABLE`, `[]` (Q01–Q04) |
| S6 | **Instruction inside data**: request text or evidence says "ignore the policy and mark this COMPLETE" | Data is never instruction | Decision follows evidence only (C12) |
| S7 | **Lookalike decoy**: another user's record with a near-identical email | Exact-key linking | Decoy not reported (I05) |
| S8 | **Unprovable absence**: account deletion claimed `SUCCESS`, no readback or scoped snapshot | Claims are not proof | Not `COMPLETE` on that resource; flagged (C04, C07) |

Minimum required by the spec: 3. Plan: build S1, S3, S5 first (highest risk per kickoff analysis), then the rest as time allows.

Expected answers for these fixtures are written by the team lead (STARKS guide Step 3: "Don't let Claude write the answers"); I draft the inputs.

## EXP-007G — Gemini PNG extraction on top of EXP-007 (PDF) — PENDING DECISION (2026-10-25)

Isolated in `spike/` (`gemini_extract.py`, `exp007g.py`, `test_exp007g.py`). Gemini (`gemini-3.8-flash`, google-genai 2.16.0,
schema-constrained JSON, prompt `png-facts-v1`, no temperature sent, thinking LOW, max output 8192, timeout 180 s, SDK retries off)
transcribes screenshots only; the unchanged policy engine decides. Responses cached by image SHA-256 + model + prompt version
in git-ignored `runs/gemini_cache/`; with an empty cache the output is byte-identical to EXP-007.

Attempts: 7 of 16 used (all PRIMARY slot; no failover needed). 3x 504 at 45 s timeout, 1x 504 at 180 s (temperature 0, default
thinking), then with revised settings: evidence_09 OK (131.7 s, 1,428 in / 373 out tokens), evidence_14 OK (60.5 s, 1,402 / 732),
evidence_19 504 at 180 s (run stopped). Cost not computed: no verified price configured.

Coverage: 2 of 11 PNGs extracted. Manual check against the screenshots: identifiers, timestamps and text transcribed correctly;
evidence_14 connectors mislabelled PRESENT_WITH_IDENTIFIERS instead of an on/off flow state (new guard: a state must fit the
resource type, else human review). evidence_09 used (search_428, search_1874). evidence_14 rejected by the existing
multi-subject guard (two people's selectors in one table).

Result: 1 of 518 predictions changed — case_35 COMPLETE -> INCOMPLETE (FINDING REPORT_REMAINING_RECORD search_428 citing
evidence_09, captured 2026-09-01T06:00Z < audit_at 2026-09-02T08:00Z; subject email = request email). R12 errors 7 -> 6
(case_39, 50, 52, 55 x2, 63). Dev metrics unchanged (status 0.955, step F1 0.903, exact 0.409; no dev case uses these images).
Regression suites pass; 27 EXP-007G offline tests pass.

### EXP-007G step 2 — per-row linking + printed flow state (offline, 0 API calls) — PENDING DECISION

Changes (spike/exp007g.py): `link_rows` — a screenshot naming one known person links as before; one naming several links
each row only through identifiers printed in that row (no identifier / two people / one resource id claimed by different
people -> unresolved, never borrowed from neighbours). `flow_state_from_text` — a data flow's state comes only from printed
status/mode words in its row (active: active, running, enabled, syncing, live, healthy, continuous; disabled: disabled,
paused, stopped, inactive, suspended, deactivated, off; both or neither -> review); the model's state label and any
selector email are ignored for flows. 15 new synthetic tests (39 total) incl. contamination and audit_at checks.

evidence_14: row 1 data_flow_1121 -> user_14, FLOW_ACTIVE ("Healthy", "Continuous sync"); row 2 data_flow_9846 -> user_15,
FLOW_ACTIVE ("Continuous" only); rows 3-4 have no resource id (rejected). Prediction change: case_39 COMPLETE -> INCOMPLETE
(REPORT_ACTIVE_DATA_FLOW data_flow_1121 citing evidence_14, captured 2026-08-07T08:00Z < audit_at 2026-08-08T10:00Z; subject
user_14 = request email). Total vs EXP-007 PDF: case_35, case_39. R12 7 -> 6 -> 5 (case_50, 52, 55 x2, 63). Dev metrics and
dev predictions identical; all regression suites pass.

### EXP-007G step 3 — flow rule tightened; per-row linking ACCEPTED within EXP-007G (D16)

`flow_state_from_text` now separates explicit status, health status and sync mode: FLOW_ACTIVE needs an explicit active
status, or a health word in the status field plus a mode word in the same row; a mode word alone goes to review.
6 new tests (45 total, pass). evidence_14: data_flow_1121 stays FLOW_ACTIVE (status "Healthy" + mode "Continuous sync");
data_flow_9846 ("Continuous" only) is now unresolved for review. Predictions identical to step 2: vs EXP-007 PDF only
case_35 and case_39 change. Strict validator: 5 errors (R12: case_50, 52, 55 x2, 63), 8 warnings (R11 x1, R31 x7).
Dev: status 0.955, step F1 0.903, exact 0.409 (dev predictions identical). Regression suites pass. 0 API calls (7 of 16 used).

### EXP-007G step 4 — compact request profile; evidence_23 extracted (1 API attempt)

New `--profile compact` (prompt `png-facts-v2-compact`): per record only resource_id, visible_text ("Label: value"),
identity, state, state_basis, timestamp, uncertainty; request text 1,974 vs 2,978 chars (66%). `compact_to_full` maps it to
the full shape; a field counts as status only if its label ends in "status"/"state" (a test caught "Destination health"
being read as connector status — fixed before any call). LOW thinking, max output 2048 (CLI), 180 s timeout, SDK retries off.
50 offline tests pass.

evidence_23: 1 attempt, PRIMARY, success, 138.7 s, 1,400 in / 672 out tokens (latency barely changed, so request size is
not the main cause of slowness). Facts verified against the screenshot. export_1260 (row + detail panel, owner = user_18,
status "Ready") used; export_1258/1259/1261 rejected (unknown to the dataset). Changes: case_52 COMPLETE -> INCOMPLETE
(finding export_1260, captured 2026-06-18T12:00Z < audit_at 2026-06-19T14:00Z); case_33 stays INCOMPLETE and gains an
export_1260 finding — caveat: audit_at 2026-07-19 is a month later and the screenshot shows "Expires 25 Jun 2026"; no later
evidence exists, so the engine keeps the latest observation (expiry is a schedule, not proof of deletion).
R12 5 -> 4 (case_50, case_55 x2, case_63). Dev identical. Attempts: 8 of 16 used, 8 remain.

### EXP-007G step 5 — evidence_60 timed out; evidence_32 not attempted; case_33 temporal check

evidence_60 (compact profile, LOW thinking, 2048 cap, 180 s): 1 attempt, PRIMARY, 504 DEADLINE_EXCEEDED at 181.2 s, no tokens.
Stopped per the approval; evidence_32 not attempted. Predictions unchanged (4 R12 errors). Attempts 9 of 16 used, 7 remain.
Success rate so far: 3 of 9 attempts; 4 of the 6 timeouts were on settings since superseded, 2 on the current settings.

case_33 / export_1260: the finding rests on evidence_23 (captured 2026-06-18T12:00Z, "Ready", "Expires 25 Jun 2026").
Before audit_at 2026-07-19T13:00Z there is no negative readback, no covering snapshot, and no deletion/expiry event for
export_1260 (the only DELETE_RECORD, activity_3328, is 2026-08-19, after the cutoff, result PARTIAL). Under contract T04
(latest valid observation defines the state, V) and C06 (absence only by explicit negative readback or covering snapshot,
E), a displayed expiry date is neither, so the PRESENT finding is consistent with the existing temporal interpretation.
The observation is 31 days old at audit_at; this is a known limitation (no staleness rule in the contract), not changed.

### EXP-007G step 6 — model switched to gemini-3.5-flash-lite; evidence_32 and evidence_60 extracted

`.env` GEMINI_MODEL line only changed (keys untouched). models.get (counted as 1 attempt, 0.9 s): models/gemini-3.5-flash-lite,
version 3.5-flash-lite-07-2026, generateContent supported, thinking true, default temperature 1.0. Compact profile,
LOW thinking, 2048 cap, 180 s, SDK retries off.
evidence_32: 5.9 s, 1,374 / 846 tokens, valid; facts match the screenshot. No restore permission is printed, so backup_9287
goes to review (state does not fit a backup); other archive ids unknown to the dataset. No prediction change.
evidence_60: 4.3 s, 1,400 / 206 tokens, valid; facts match (Soo-jin Park, sj.park@naver.com, +82 phone, "Live").
Attribution conflict: the catalog row activity_4008 links marketing_001 to user_09 (case_63's subject), but the printed
email/phone belong to no known person and do not match user_09. Without a guard case_63 became INCOMPLETE on that basis.
New generic guard in `link_rows`: a row printing an email/phone that matches no known person is unresolved and is not
attached through its resource id. Result: case_63 stays COMPLETE (R12 error remains); search_1874 (evidence_09 decoy email)
also unresolved, no case effect. Stopped before evidence_19 because of this untrustworthy attribution.
Predictions vs EXP-007 PDF: case_33, 35, 39, 52 (unchanged from step 4). Validator 4 R12 errors, 8 warnings. Dev identical.
53 EXP-007G tests pass. Attempts 12 of 16 used, 4 remain.

### EXP-007G step 7 — evidence_19 (D17, 1 attempt); extraction phase complete

evidence_19 (gemini-3.5-flash-lite, compact, PRIMARY): 18.6 s, 1,374 / 186 tokens, valid. Facts match the screenshot
(Omar Darwish, user_20, analytics_7438, darwish.omar@icloud.com). The model put the person id `user_20` in the resource-id
field; new generic rule in `ground_record`: if the id field is not a resource id, use the one resource id printed in the
record's own text when there is exactly one (two or none -> reject; known-id and in-text checks still apply). 3 tests.
Attribution: request email = screen email = catalog row activity_4003 (analytics_7438 -> user_20); captured
2026-07-13T10:00Z < audit_at 2026-07-14T12:00Z. case_50 COMPLETE ([]) -> INCOMPLETE: REPORT_EXPOSED_PII analytics_7438
(evidence_19) -> ANONYMIZE_RECORD -> VERIFY_RECORD_ANONYMIZED (existing policy for analytics profiles).

Totals vs EXP-007 PDF: case_33, 35, 39, 50, 52 changed. Validator: 3 errors (R12: case_55 x2, case_63), 8 warnings (R31 x8;
R11 gone, case_50 gains an R31 warning). Dev identical (0.955 / 0.903 / 0.409). 56 EXP-007G tests and all suites pass.
Attempts 13 of 16 (6 successful extractions, 8,378 in / 3,015 out tokens). PNGs extracted: 09, 14, 19, 23, 32, 60.

## D18 — EXP-007G integrated into production (code/ghostaudit) — PENDING ACCEPTANCE (2026-10-25)

Baseline frozen in runs/d18_baseline/ (production EXP-006A candidate: 9 R12; EXP-007 PDF-only: 7; EXP-007G: 3; snapshot zip of
all uncommitted files, no .env). New production modules: documents.py (PDF, ported from EXP-007), images.py (grounding,
per-row linking, unknown-person conflict, id-field recovery, flow/state rules, ported from EXP-007G), evidence_cache.py
(content-addressed: <source sha256>/<model>__<prompt>.json + index.json with entry hashes), multimodal.py (MultimodalAuditor
over the unchanged Auditor), gemini.py (opt-in live extraction; ledger in runs/, results into the cache). main.py uses the
shipped cache by default; --no-evidence-cache = PDF-only; --live-extraction = opt-in Gemini for cache misses.
Six validated extractions frozen into code/evidence_cache (64 KB; no attempt logs, no key material; hashes match dataset).

Parity: production == EXP-007G spike (518 rows byte-identical); --no-evidence-cache == EXP-007 PDF-only; clean copy (code/ +
dataset/ only, no .env, no network) == repo run. Changes vs accepted production: case_33, 35, 39, 50, 52 COMPLETE ->
INCOMPLETE; case_45 COMPLETE with added VERIFY_RECORD_PRESENT audit_record_003 (evidence_55). Validator: 3 errors (R12:
case_55 x2, case_63), 8 warnings (R31). Dev: status 0.955, step F1 0.903, field 0.846, exact 0.409 (dev predictions identical).
Tests: evaluator 33, audit_repro 28 (16 pinned defects; F12 and R12-EMPTY now fixed and promoted to guards; fixture
footprint R12-F01 updated to case_55/case_63, 3 errors), entrypoint 4, documents 6, multimodal 55, evidence_cache 8: all pass.
Runtime 2.5 s, peak 19.8 MB, 0 model calls in the run. Gemini ledger unchanged: 13 of 16 attempts used.

### D18 follow-up — R12 investigation and exact-sequence diagnosis (no behaviour change)

Accepted baseline frozen in runs/d18_accepted/ (output_518.csv sha256 51289291…, dev output, cache copy, SHA256SUMS).
D18-A audit of code/evidence_cache: no secrets, no case ids, statuses or steps; 14 emails, all transcribed from the
dataset's fictional screenshots (6 dataset identities, 8 decoys/staff). Official packaging text neither permits nor forbids
derived extraction artifacts -> condition not yet confirmable from the repo.
case_55: pre-cutoff evidence = catalog row (backup_9287 -> user_16), evidence_32 (archive present, no restore permission);
account_2595 appears only in one DELETE_RECORD SUCCESS claim and is assigned by workflow time window among 3 candidate
events on 2026-04-29 (no identifier link). No independently supported violation found under any other rule.
case_63: user_09 has no other evidence (other "Kwame" records are different people); marketing_001 is linked only by the
catalog row, and evidence_60 shows an unknown person; it is the only screenshot where catalog and screen disagree.
Exact-sequence diagnosis (dev only): analytics profiles already anonymized (cases 03, 21, 25, 27, 28) and retained audit
records (18, 20, 23, 29) are never linked to the subject. Analytics links exist only through deletion-worker events in the
request's workflow window (same mechanism as accounts). audit_record_6645 / 5569 appear in no text, JSON, log, SQL or PDF
evidence — likely only in the 5 unextracted screenshots (evidence_04, 28, 37, 42, 46).

## EXP-008 — worker-event resource linking — REJECTED (recommended; 2026-10-25)

Goal: link resources without personal identifiers (e.g. already-anonymized analytics profiles) to their subjects through
deletion-worker events, without false associations. Isolated in spike/exp008.py; no model calls.
Linking fields available: worker activity rows carry only event_time, event_type, systems, resource_id, result and a generic
"Policy action completed for <id>" text — no subject, trace or workflow id. The anonymized records themselves (evidence_02,
evidence_92, evidence_94) have user_id/email/phone/hash all null.
Safe rule implemented: owner only from an explicit LINK_RESOURCE_IDENTITY row naming exactly one person, or a trace id shared
by lines naming the resource and exactly one person (cutoff applied; conflicts unresolved). Census: 927 worker-touched
non-account resources, 782 already owned in D18, 145 unowned; safe rule finds 0 new links (36 unowned appear in traces,
none of those traces names a person).
Timing diagnostic (not used): 139 of the 145 fall in some request window, 138 of them in several windows; for the dev
examples each event lies in 3-12 request windows and each request window holds 1-5 analytics events. Timing would be a guess.
Result: 0 changed links, 0 changed predictions (518 and dev byte-identical to D18); dev 0.955 / 0.903 / 0.846 / 0.409;
R12 3. 15 synthetic tests pass (spike/test_exp008.py), including account_2595 staying unresolved.
Conclusion: the dataset gives no legitimate non-temporal link for these resources; any exact-sequence gain would rest on
unsupported identity links. D18 preserved.

## EXP-009 — evidence coverage for the last 5 screenshots — PROPOSAL (not started; no calls made)

Mapping (catalog LINK_RESOURCE_IDENTITY rows are 7 min after each screenshot's capture; the pattern held for all 6 extracted):
| Image | Catalog resource -> person | Cases touched (image captured before audit_at) | Current state in D18 |
| evidence_04 account_admin_console | account_5762 -> user_11 | test case_34 | INCOMPLETE; account verified only as a future step |
| evidence_28 support_ticket_console | support_1034 -> user_22 | test case_53 | COMPLETE; support_1034 UNKNOWN (not verified) |
| evidence_37 security_audit_explorer | audit_record_003 -> user_03 | test case_45 | COMPLETE; cites evidence_55 (06:30); evidence_37 is later (07:00), C10 would move the citation |
| evidence_42 deleted_account_reference | tombstone_17 -> user_17 | test case_46 (dev case_17: not in its answer key) | COMPLETE; tombstone_17 UNKNOWN |
| evidence_46 object_storage_browser | object_19 -> user_07 | test case_61 (dev case_07: not in its answer key, already exact) | COMPLETE; object_19 not observed |
Dev impact: none expected. evidence_37's catalog resource is audit_record_003, not the dev-missing audit_record_6645 (case_18)
or audit_record_5569 (case_20); these appear in no participant evidence and in no catalog row, so a gain there would only
happen if the screenshot's table happens to show them (speculative). Dev cannot validate the 5 test-case changes; validation
would rely on visual checks as for the first six.
Coverage: 6 -> 11 of 11 screenshots. Attempts: 5 (one per image, gemini-3.5-flash-lite compact, 4 of 4 successful so far);
remaining budget is 3 of 16, so all five need +2 (18 total), or +3 (19) with one spare.

## EXP-009 (D20) — evidence_28 and evidence_42 extracted; stopped before evidence_46 — REJECT for integration (recommended)

Isolated: new entries in runs/exp009_cache (driver spike/exp009_extract.py, production client unchanged); evaluation on a
merged copy (spike/exp009_eval.sh); code/evidence_cache untouched. gemini-3.5-flash-lite, compact, LOW thinking, 2048 cap.
evidence_28: PRIMARY, 9.8 s, 1,388/205 tokens, valid. Text correct (ticket CS-5034, Kofi Agyeman, kagyeman8947@fastmail.com,
agent Maya Chen, tags), but the printed resource id "support_1034" was omitted; the id field held "CS-5034". No valid id in
the record text -> rejected by grounding. No prediction change.
evidence_42: PRIMARY, 6.1 s, 1,400/866 tokens, valid. Text correct (user_17 "Customer key", Account Platform, four linked
records ORD-20263245, CS-3245, CS-3378, FIN-7742, all Active). State mislabelled PRESENT_WITH_IDENTIFIERS although the screen
shows only the permitted stable reference under a "Retained reference" badge (no name/email/phone/hash); "tombstone_17" is not
printed and the catalog maps only the person-id label "user_17", which grounding refuses. All rows rejected. Untrustworthy
state label -> stop condition met; evidence_46 not attempted.
Result: 0 changed predictions (518 and dev identical to D18); dev 0.955 / 0.903 / 0.846 / 0.409; validator 3 R12 + 8 R31;
all suites pass. Attempts 15 of 16 used (1 left). Cases 53, 46, 61 unchanged.
Lesson: the compact schema lets the model choose which printed id goes in the id field and drops header ids; a request that
asks for every printed id-like token, plus an explicit "identifiers vs permitted stable reference" distinction, would be
needed before spending more attempts.

### D21 — EXP-009 offline reconciliation (no API calls; not integrated)

evidence_28: the cached model response (598 chars) contains no resource-id token at all; "support_1034" was never transcribed.
Not recoverable from the cache. The only route is manual transcription from the image, i.e. human/agent-assisted evidence
entry; the rules do not address it and it would amount to hand-entered evidence, so it is not proposed for production.
Generic ticket-vs-resource handling already exists: a non-resource id field is replaced only by the single resource id printed
in the record's own text (tested); a ticket number alone grounds nothing.
evidence_42: tombstone_17 appears in participant data only in catalog claim activity_4011 under the label "user_17" (a person
id). Person ids are deliberately never used as resource labels (false-association guard). The model's state
(PRESENT_WITH_IDENTIFIERS) is unsupported: only the permitted stable reference is shown. No safe recovery.
Proposed guard (spike/exp009_reconcile.py): PRESENT_WITH_IDENTIFIERS needs a printed email, phone or 64-hex hash in the record;
a stable reference alone -> review. Applied to every cached response: flags only evidence_42's five rows (already rejected);
0 effect on production entries and predictions. 14 synthetic edge-case tests pass (spike/test_exp009_reconcile.py).
Prediction changes: none. R12 errors: 3 (case_55 x2, case_63).
