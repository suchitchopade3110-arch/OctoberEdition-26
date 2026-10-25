# Decisions

Team lead decides; this file records what was decided, what was rejected, and the evidence.
Entries D1–D6 were approved by the team lead on 2026-10-24 (approval text in `log.txt`, same date). Quotes are the lead's words.
Rule IDs refer to `docs/contract.md`.

---

## Contract clarifications from the team lead (2026-10-24, after Step 2)
- **A4:** samples show INCOMPLETE cases verify already-compliant accounts and retained security records → contract R33 (V). Verifying *every* other already-compliant resource stays unresolved → R34 (U).
- **Ordering:** keep the exact official operation order (R16). Numeric case ordering is a validated interpretation, not a universal rule → R04 (V); validator only errors when rows follow neither numeric nor plain-text order.

## D12: EXP-005 rejected; aca42dc stays the reference; EXP-006 approved (team lead, 2026-10-24)
- **Lead's decisions (quoted):** "REJECT EXP-005 for production integration. RETAIN commit `aca42dc` as the accepted reference baseline. APPROVE EXP-006A for behavior-preserving production integration. CONDITIONALLY APPROVE EXP-006B for evidence-correctness investigation and contract-supported fixes."
- **Evidence behind it:** independent audit (log.txt 2026-10-24T15:49:34Z) — 15 of 17 independent intent probes misclassified by EXP-005. (For comparison, measured in EXP-006: the accepted keyword rule misclassifies 9 of the same 17.)

## D13 (DRAFT, not decided): accept EXP-006A
- **Proposal:** accept `code/main.py` + `code/ghostaudit/` as the production entry point. Evidence: byte-identical 518 and dev predictions, identical observation index, clean-copy run, validation-gated publication.
- **Status:** awaiting team lead (`keep` required before any commit).

## D14: Option A approved with safeguards — extract multimodal evidence first (team lead, 2026-10-24)
- **Lead's decision:** "I select Option A: Extract multimodal evidence first." Safeguards: never fabricate evidence ids or verification steps; never equate missing evidence with ABSENT; no COMPLETE→INCOMPLETE without contract-supported findings; no evidence captured after `audit_at`; no hardcoded case ids; if evidence stays insufficient, keep the case unresolved and block publication. No paid model calls; do not invoke paid AI/VLM APIs without approval.
- **Result so far (EXP-007, PDFs only):** see EXPERIMENTS.md. 1 of the 9 R12 errors resolved through valid evidence (case_33 `export_1842`), 1 cleared only by case_33's status change (`export_1260` still UNKNOWN), 7 remain; F12 (case_45) resolved through evidence. Publication stays blocked.
- **Open sub-decision D14-PNG (needs the lead):** how PNG screenshots may be read — see EXPERIMENTS.md EXP-007 "PNG options".

### D14 options as originally drafted (for the record)
- **Facts:** 7 cases (33, 35, 39, 50, 52, 55, 63) are COMPLETE in the accepted output but cannot cite evidence for at least one relevant resource; case_45 drops a retained record. All unproven resources are catalog-linked and shown only in PNG/PDF evidence.
- **Options:** (A) extract the multimodal evidence first (PDF text via pypdf needs no model; PNG needs the D7 model or manual transcription) and let the evidence decide — recommended; (B) INCOMPLETE with a finding citing the `LINK_RESOURCE_IDENTITY` activity_id — relies on a catalog claim as proof of presence (C04); (C) keep COMPLETE and drop the unprovable steps — hides relevant copies (S01); (D) NOT_APPLICABLE — contradicts a valid deletion request.
- **Until decided:** no output change; root `output.csv` is not published (strict validation fails with 9 R12 errors).
- **Status:** awaiting team lead.

## D15 (DRAFT, not decided): accept EXP-006B's contract-unambiguous changes
- Validator: authorised rows with `[]` become errors (R12/R13); internal UNKNOWN / UNPROVEN notes; audit repro fixture and clean-entry-point tests. Output unchanged.
- **Status:** awaiting team lead.

## D32: F1 accepted and integrated; F1 is the new production baseline (team lead, 2026-10-25)

Decision (team lead): "ACCEPT D31/F1. AUTHORIZE PRODUCTION INTEGRATION AND LOCAL COMMIT." No push.

Background:
- D30 (investigation only) traced the 3 R12 errors to a shared mechanism: no usable observation is planned as
  ABSENT, verification is emitted unconditionally, and status means "no findings". Each resource fails for a
  different reason (runs/d30_rootcause/D30_ROOT_CAUSE_REPORT.md).
- D30 also found a separate defect: SQL inventories store `restore_allowed` / `enabled` as
  `INTEGER CHECK (x IN (0,1))`, and `evidence.truthy()` ignored integers. The policy then verified open restores and
  active flows as blocked/disabled, citing the row that showed the opposite.
- D31 implemented the fix in an isolated worktree (branch `exp/d31-f1`) and recommended ACCEPT
  (runs/d31_f1/D31_F1_DECISION_REPORT.md).

Change (applied exactly as reviewed in runs/d31_f1/f1.patch):
- `code/ghostaudit/evidence.py`: field-scoped `flag()`.
  - Integers 0/1 are read only for `enabled` and `restore_allowed`. Bools and "true"/"false" are read as before.
  - "1"/"0" strings, null, malformed and unexpected numbers are unknown.
  - A present but unreadable flag gives `RESTORE_UNKNOWN` / `FLOW_UNKNOWN`.
  - `eligible` + `deletion_block`: OPEN only for true/false, BLOCKED for not-eligible or blocked, otherwise unknown.
- `code/ghostaudit/auditor.py`: an unknown flag state is never cited as proof.
- `code/tests/test_f1_flags.py`: 25 new tests; 13 of them fail on the pre-F1 code.
- Not changed: the validator, the evidence cache, S4, the R12 handling, and the policy path for backups/flows that
  have no flag field (D30 F3).

Verified on main before commit:
- Production tests: 126 pass (101 + 25; 16 expected failures). Evaluator tests: 33 pass. Custom scenarios: 4/5
  (S4 still fails, known).
- 518 output: sha256 `1503deba33ea51f173e6e11f8da6e538be86c078f8df5cc55f6b38cc017b91eb`, identical to the D31 experiment.
  A clean copy (no .env, minimal env) reproduces it. 0 model calls.
- Exactly 24 rows change against D18:
  - 6 COMPLETE → INCOMPLETE: case_123, 128, 248, 399, 447, 495;
  - 18 INCOMPLETE rows gain a cited `REPORT_ACTIVE_DATA_FLOW` + `DISABLE_DATA_FLOW`: case_68, 176, 181, 182, 217, 296,
    301, 302, 337, 338, 340, 397, 402, 445, 446, 450, 451, 500.
  - Every cited row is pre-cutoff and prints the requester's email. There are no unexpected changes.
- Validator: 3 errors (R12: case_55 ×2, case_63) and 8 warnings (R31), the same as D18.
- Dev metrics are unchanged (0.9545 / 0.9027 / 0.8455 / 0.4091). Reserved status went 0.70 → 0.80 and step F1
  0.769 → 0.830. The reserved split was inspected in D30, so those numbers are not a clean holdout and are reported
  separately.
- The evidence cache is unchanged (index.json sha `d9a69859…`, equal to the frozen D18 copy).

Baselines:
- F1 reference: runs/f1_baseline/ (NOT VALIDATED; SHA256SUMS; per-case CHANGES_vs_D18.md).
- D18 is kept in runs/d18_accepted/ (sha `51289291…`).
- Pre-F1 checkpoint: local tag `pre-f1-checkpoint` = `bc77faf`.

Still open:
- the 3 R12 errors (organizer Q1–Q3);
- D30 F3 (no-flag backups/flows);
- the silent omissions (case_46, case_53);
- time-window account attribution;
- S4.

Root `output.csv` is not published.

## D27: D26 accepted; D25/D26 documentation committed locally (team lead, 2026-10-25)

KEEP the D25/D26 documentation as one local commit (no push): docs/DECISIONS.md, docs/ORGANIZER_QUESTIONS.md,
docs/SUBMISSION_BLOCKERS.md and log.txt. Excluded: runs/ (including the zip candidates), spike/, .env, agent-trace exports
and the four unreviewed docs. No production, validator or evidence-cache change; output.csv not published. The three R12
errors and D18-A stay open pending the organizer questions or an explicit fallback decision.

## D26: organizer clarification and submission contingency — APPROVED (team lead, 2026-10-25); ACCEPTED in D27

D25 accepted. The three R12 errors (case_55 account_2595 and backup_9287; case_63 marketing_001) stay UNRESOLVED and will
not be forced to pass. case_46/tombstone_17 and case_53/support_1034 stay recorded as silent-omission risks. D18 and the
D25 dossier are frozen.

Prepared, with no prediction, validator or cache change:
- docs/ORGANIZER_QUESTIONS.md: shareable questions Q1–Q3 (unestablished state, unblocked retained backup, catalog versus
  printed identity) and Q4 (derived extraction files in code.zip). No personal data. No answer has been received.
- docs/SUBMISSION_BLOCKERS.md: the exact validator output, the open decisions, the smallest compliant change and
  regression test for each possible answer, packaging results and transcript status.
- Candidate packages in runs/package/ (not submitted), built to mirror the official zip command:
  - code_with_cache.zip: 41 files. Its clean copy reproduces D18 byte for byte; 101 tests pass.
  - code_without_cache.zip: 34 files. It falls back to the PDF-only output (7 R12 errors); 4 shipped tests fail.
  Neither contains dataset files, .env, binaries, nested archives, build caches or keys.
- log.txt: 49 well-formed entries, no exposed keys. The separate agent-trace export still holds the pasted keys and must
  be redacted.

Without an organizer answer, there is no fully evidence-grounded, validator-passing 518-row output under the current
interpretation. Any fallback must be an explicit, recorded decision.

## D25: final R12 adjudication — investigation only (team lead, 2026-10-25); result: UNRESOLVED, organizer guidance needed

No code, validator or output change. Candidate rows were checked by substituting them into a scratch copy of the D18
output and running the strict validator. Both requests clearly authorise deletion, so NOT_APPLICABLE is excluded. No public
sample has COMPLETE with [].

case_55 (areed1433@gmail.com, audit_at 2026-04-30T11:00Z)
- account_2595: the only record is activity_1640, a DELETE_RECORD SUCCESS claim (C04). The account was assigned by workflow
  time window among 3 candidates (the D19 risk). Ownership and state are both unproven. No COMPLETE citation exists (C06),
  and there is no presence evidence for a finding (C05/C07).
- backup_9287: evidence_32 (captured 04-29T09:00Z) shows the archive with "Account: areed1433@gmail.com", so ownership is
  established by the evidence content. It also shows checksum verified, last restore drill 29 Mar and retention end 26 Jul,
  but no restore permission or block. There is no BLOCK_RESTORE or CHECK_RESTORE_ACCESS event at any time. Policy: rule_14
  RETAIN + block restore; P14 allows a finding only "if restore allowed".
- Candidates:
  - A: current COMPLETE, uncited (R12 x2).
  - B: INCOMPLETE, REPORT_RESTORE_RISK backup_9287 [evidence_32] -> BLOCK_RESTORE -> VERIFY_RECORD_ABSENT account_2595 ->
    VERIFY_RESTORE_BLOCKED. Validator OK, but it reads "no block shown" as "restorable"; rejected in D18-B.
  - C: COMPLETE citing activity_1640 and evidence_32. Validator OK but FALSE: a claim, and a screenshot that shows no block.
  - D, E: COMPLETE with fewer or no steps (R12).

case_63 (kwame-mensah@proton.me, audit_at 2026-09-17T09:20Z)
- marketing_001: evidence_60 (captured 09-16T07:20Z) shows a live profile for a person who matches no known identity. Only
  the catalog claim activity_4008 links it to user_09, and there is no other evidence for user_09. Policy: rule_10 DELETE.
- Candidates:
  - A: current COMPLETE, uncited (R12).
  - B: INCOMPLETE, REPORT_REMAINING_RECORD [evidence_60]. Validator OK, but ownership is contradicted; rejected in D18-D.
  - C: COMPLETE citing evidence_60 as absence. Validator OK but FALSE: it shows the record present.
  - D: COMPLETE [] (R12).

Related hidden risk, not flagged by the validator: case_46 (tombstone_17) and case_53 (support_1034) are COMPLETE while a
catalog-linked resource has no usable observation and is left out of the steps (F02-style). These are the EXP-009 screenshots.

Organizer questions:
1. How should a resource be reported when the evidence cannot establish its state at audit_at? COMPLETE needs proof, and
   INCOMPLETE needs a cited finding.
2. Does a retained backup with no evidence that restore is blocked count as a restore risk?
3. When catalog identity rows and the identifiers printed in the evidence conflict, which decides ownership?

## D24: D23 documentation accepted; local commit authorised (team lead, 2026-10-25)

KEEP the D23 submission documentation as one local commit (no push). Pre-commit reconciliation found that the D23 draft
overstated the request count: the attempt ledger has 15 API requests (14 image extraction attempts, 8 successful and 6
timed out, plus 1 models.get metadata request), not 16. usage_report.md and the D23 record were corrected; tokens, latency
and cost were already computed from the 8 successful extractions and are unchanged. S4 stays a failing scenario. The
314/500 account time-window attribution risk is documented in the evaluation report and README.

## D23: submission documentation — APPROVED (team lead, 2026-10-25); ACCEPTED in D24

Created code/evaluation/evaluation_report.md, code/evaluation/usage_report.md, code/evaluation/custom_scenarios.py
(5 synthetic end-to-end scenarios, 4 pass; S4 exposes a real defect: a later covering snapshot that omits a record does not
override an earlier PRESENT, contract C06b), code/requirements.txt, and replaced the starter README.md. No prediction logic,
validator or evidence-cache change; 518 output byte-identical to D18. Measured for the report: 314 of 500 account steps in
the 518 output are attributed only by the workflow time window (D19 risk). Usage: 15 Gemini API requests during development
(14 image extraction attempts: 8 successful, 2 of them later rejected by grounding, and 6 timeouts; plus 1 metadata
request), 11,166 input / 4,086 output tokens, $0.0177 at verified paid-tier rates; final run 0 calls.
Claims depending on organizer guidance: shipping code/evidence_cache in code.zip (D18-A); treating the one-time extraction
as development usage in usage_report.md; local dev metrics are not the judge's score.

## D22: secure the D18 baseline in a local commit — APPROVED (team lead, 2026-10-25)

KEEP the verified D18 production baseline as a local commit (no push). Included: production code (code/main.py,
code/ghostaudit/), the EXP-006B validator change (team lead: include; it only makes validation stricter and D18's results
depend on it), production tests and fixture, code/evidence_cache (team lead: include locally only; shipping it in code.zip
remains under D18-A), docs (DECISIONS, EXPERIMENTS, TRAP_FINDINGS), log.txt and .env.example. Excluded: rejected or unreviewed
material (spike/, docs/CHATGPT_HANDOFF_PROMPT.md, docs/INTENT_REVIEW.md, docs/PROJECT_STATUS.md,
docs/intent_review_decisions.csv), runs/, .env. Verified before commit: 134 tests pass; 518 output byte-identical to the frozen
D18 baseline (sha256 51289291…); clean copy with an empty environment reproduces it; secret scan clean.

## D21: EXP-009 — REJECTED for production integration (team lead, 2026-10-25)

D18 stays the production baseline. EXP-009 artifacts kept for provenance: runs/exp009_cache (validated responses incl. raw
model text, source sha256, model, prompt version), spike/exp009_extract.py, spike/exp009_eval.sh, attempt ledger.
Grounding failures: evidence_28 — the model omitted the printed resource id and put the ticket number in the id field;
evidence_42 — the model labelled a tombstone showing only the permitted stable reference as "identifiers present", and the
resource id is not printed. Approved follow-up: one offline reconciliation (no API calls), reported separately.

## D20: EXP-009 screenshot coverage — APPROVED (team lead, 2026-10-25); result: REJECT for integration (recommended)

Approved: 3 attempts (evidence_28, 42, 46), isolated, stop on failure, ambiguity or identity contradiction. The catalog row
7 minutes after capture is a discovery heuristic, not proof of ownership. Executed 2 attempts: both extractions omitted or
mis-slotted the printed resource id and evidence_42's state was mislabelled; grounding rejected every row; 0 prediction
changes. Stopped before evidence_46. 15 of 16 attempts used. Production cache and D18 baseline unchanged.

## D19: EXP-008 worker-event resource linking — REJECTED for production (team lead, 2026-10-25)

Hypothesis: deletion-worker events (ANONYMIZE_RECORD, REDACT_RECORD, ...) could attribute resources that carry no personal
identifiers (e.g. already-anonymized analytics profiles) to the right person, improving exact-sequence accuracy.
Measured: worker rows carry no subject, trace or workflow id; the anonymized records have every identifier null. A safe rule
(explicit catalog link or a trace naming exactly one person) found 0 new links among 145 unowned worker-touched resources.
Timing-only diagnostic: 138 of 139 in-window resources fall in several request windows (dev examples: 3-12 windows each).
0 changed predictions; dev metrics unchanged (0.955 / 0.903 / 0.846 / 0.409); R12 3.
Reason: no legitimate evidence supports the links; any gain would rest on unsupported identity attribution.
Principle (binding): **temporal proximity alone is insufficient for identity attribution.**
Kept: spike/exp008.py and spike/test_exp008.py (15 tests) as the record of the rejected approach. Not integrated. D18 stays
the production baseline.
Known limitations: ~4 dev exact-sequence misses (anonymized analytics profiles) stay unfixable from current evidence.
**Correctness risk flagged:** production's account resolution (Auditor.resolve_accounts) assigns accounts such as
account_2595 (case_55) by workflow time window plus elimination/tie-break, with no identifier link; three account deletions
fall in case_55's window. This conflicts with the principle above and needs a separate investigation.

## D18: EXP-007G production integration — ACCEPTED WITH CONDITIONS (team lead, 2026-10-25)

Decisions (team lead):
- Integration: ACCEPTED. Integrated baseline frozen in runs/d18_accepted/ with its reproducibility tests.
- D18-A: CONDITIONALLY APPROVED — ship code/evidence_cache only after confirming the official rules permit derived
  extraction artifacts and that it holds no secrets, prohibited personal data, golden answers or hardcoded predictions.
- D18-B: OPTION 2 — backup_9287 stays unresolved; its existence does not prove restore eligibility. Look for an
  independently supported violation under another policy.
- D18-D: OPTION 2 — marketing_001 stays unresolved; the screenshot identifiers contradict the catalog identity.
- Final output.csv: NOT APPROVED while R12 errors remain. No behaviour-changing policy interpretation without approval.

### D18 record as drafted (for the record)

Approved: integrate PDF extraction, cached Gemini image facts, per-row linking, cross-user contradiction detection,
resource-id recovery, data-flow state rules and provenance checks into code/ghostaudit, with no new model calls. Not
approved: the final 518-row output or submission. Done as described in EXPERIMENTS.md "D18".

Open decisions for the team lead:
- D18-A: ship code/evidence_cache (derived, fictional, 64 KB) in code.zip so a clean run needs no key (recommended), with
  the one-time extraction calls disclosed in README/usage_report; or ship without it (clean runs then need keys or lose
  image evidence).
- D18-B: case_55 backup_9287 — screenshot shows the user's archive present but no restore permission. Options: (1) report
  a restore risk citing evidence_32 (makes case_55 INCOMPLETE; account_2595 then becomes a future check); (2) leave unresolved.
- D18-C: case_55 account_2595 — only a SUCCESS delete claim (C04). No valid COMPLETE citation exists; resolved only via D18-B(1)
  or by a contract decision.
- D18-D: case_63 marketing_001 — catalog links it to the subject, screenshot shows an unknown person. Options: (1) trust the
  catalog link and report the record present citing evidence_60; (2) keep it unresolved (current guard).

## D17: one gemini-3.5-flash-lite attempt on evidence_19 — APPROVED and executed (team lead, 2026-10-25)

Model switched from gemini-3.8-flash (6 timeouts in 9 attempts) to gemini-3.5-flash-lite (4 of 4 requests OK, 4-19 s).
Result: case_50 resolved by evidence (exposed PII on analytics_7438). Extraction phase stops here; 3 of 16 attempts unused.
Open evidence problems kept unresolved by design: case_55 account_2595 (no evidence), case_55 backup_9287 (screenshot shows
no restore permission), case_63 marketing_001 (screenshot shows a person who matches no known identity, contradicting the
catalog link). Integration of EXP-007G into production is NOT yet approved.

## D16: EXP-007G per-row identity linking — ACCEPTED WITH SAFEGUARDS, isolated only (team lead, 2026-10-25)

Scope: the generic per-row linking and printed flow-state rules inside isolated EXP-007G (`spike/exp007g.py`). This is
**not** acceptance of the EXP-007 multimodal pipeline and **not** production integration. Previous Gemini route decisions:
OCR (Tesseract, Cloud Vision) were dropped; Gemini approved with a 16-attempt budget (7 used, 9 remain).

Safeguards (conditions of acceptance):
1. Per-row linking: a screenshot naming several people links each row only through identifiers printed in that row;
   rows with no identifier, two people, or a resource id shared by different people stay unresolved; identifiers are
   never borrowed from neighbouring rows; single-person screenshots behave as before; row provenance is kept.
2. Flow state only from printed words in the row. FLOW_ACTIVE needs an explicit active status (active, running,
   enabled, syncing, live), or a health status in the status field (healthy, connected) plus a mode word from the
   same row. A sync mode (continuous, scheduled, ...) alone never establishes FLOW_ACTIVE. Contradictions or
   insufficient wording -> unresolved for human review. The model's state label and selector emails are ignored.
3. No new API calls, no credential changes, no case-specific behaviour, no commits or pushes.

Evidence for acceptance: case_39 COMPLETE -> INCOMPLETE on data_flow_1121 (evidence_14 row 1, "Healthy" +
"Continuous sync", row email = request subject, captured before audit_at); with case_35 (evidence_09) the R12
errors go 7 -> 5; dev predictions identical; all regression suites pass.

## D11: EXP-005 intent classification — superseded by D12 (rejected for production integration)
- **Lead's decision:** direction approved; do not integrate or commit until the 80-example independent review, the partial-deletion question and the ABSTAIN checks are resolved. EXP-004 (`aca42dc`) stays the accepted baseline.

### D11-P: partial deletion — APPROVED by the team lead (2026-10-24), implemented in EXP-005 (uncommitted)
- **Lead's conditions:** (1) a request that explicitly preserves the account does not authorise full-account deletion; (2) classify it `NOT_APPLICABLE`, `steps_json=[]`; (3) record `PARTIAL_SCOPE_UNSERVED` internally with the conflicting clauses; (4) document it as **our conservative interpretation of an unspecified scenario, not an explicit rule of the official contract**; (5) do not confuse it with full deletion that allows anonymous or legally required retention; (6) never start account deletion merely because one data category is to be deleted; (7) independent tests, no case-specific phrases.
- **Implemented as:** `resolve()` returns not authorised + `PARTIAL_SCOPE_UNSERVED` for (a) erase + keep-account, (b) erase + refused account deletion, (c) erase of a single named data category with no account, all-data or deleted-account context (condition 6). Conflicting clauses are stored in `Intent.conflicts`. "Keep X" where X is not the account (anonymous statistics, legally required records, a deleted-account reference) remains full deletion.
- **Status:** approved interpretation; EXP-005 itself is not yet finally accepted (human labels pending).

#### Analysis that led to D11-P
- **What the contract says (quoted):** "Use `NOT_APPLICABLE` with `steps_json=[]` when the request does not authorize deletion." (AGENTS.md §6.3); "First determine whether `request_text` authorizes deletion. A request for access, correction, export, marketing opt-out, or another non-deletion action is `NOT_APPLICABLE`" (§6.5); `rule_01,USER_PROFILE,Always,DELETE` (deletion_rules.csv). Every one of the 32 official sample answers contains an `account_service` step.
- **Consequence:** the contract has two outcomes only — authorised (the whole policy applies, including deleting the user profile) or `NOT_APPLICABLE` with `[]`. There is no status for "erase X but keep the account".
- **Contract-supported interpretation (proposed):** a request that explicitly keeps the account (or refuses its deletion) does not authorise the deletion the audit models, so it resolves to **not authorised → `NOT_APPLICABLE`, `[]`**, with an internal flag `PARTIAL_SCOPE_UNSERVED`. This follows the lead's instruction not to authorise full-account deletion against an explicit keep request.
- **Unresolved ambiguity:** the requester *did* ask to erase some data; `NOT_APPLICABLE` leaves that part unaddressed and the contract offers no way to express it. Rejected alternatives: (a) authorise and audit everything — deletes the account against the request; (b) authorise but drop the account step — contradicts `rule_01` and R31 (32/32 samples).
- **Measured reach:** 0 of 540 non-reserved real request texts are partial-scope; affects unseen data only.
- **Applied after approval** (see above); check 3 now passes 5/5.

## D10: EXP-004 temporal reconstruction — ACCEPTED with safeguards (2026-10-24)
- **Rule:** state at `audit_at` = latest *observation* time among evidence available at `audit_at`; line order is never chronology; reappearance is flagged, cause not assumed.
- **D10-A, equal-timestamp conflicts (lead's conditions):** keep every tied observation with provenance (file, line, scope, system, state); mark the result ambiguous; apply the least-compliant preference only when scope and authority are comparable (same copy/system), and never as proof of a violation; no fabricated findings, citations or associations; never merge replica copies — SQL observations carry their table as scope, per-copy states are kept, and C08 (a remaining copy means the record exists) still applies.
- **D10-B, post-dated observations (lead's conditions):** quarantined from state selection; kept and flagged; cannot override a valid earlier observation; reconsidered only if independent evidence shows the time is valid and usable under the cutoff (an independent later file showing that state is simply used on its own merit).
- **Evidence:** 14/14 within-file sequences (baseline 2/14); 12 state changes across 81 cutoffs, all backed by a later reliable observation; 0 cutoff violations; 17 temporal tests; dev predictions byte-identical. No equal-time tie occurs in the current data (safeguards exercised by synthetic tests only).
- **Lives in:** `experiments/exp004.py` (`choose`, `scope_of`, `Auditor4.attach_manifest_times`, `Auditor4.attach_sql_scopes`).

## D9: EXP-003 parser accepted as the new baseline (2026-10-24)
- **Lead's decision:** "EXP-003 — ACCEPTED. Integrate the generalized parser improvements into the accepted deterministic baseline."
- **Evidence:** resource-id coverage 2080/2503 → 2503/2503; extraction precision 2503/2503; 17 synthetic tests pass; dev output byte-identical to EXP-001 (no measured accuracy change, none claimed).
- **Integrity checks before commit:** EXP-002 code excluded; `experiments/exp001.py` byte-identical to the frozen baseline; all 463 new links match on an identifier value (410 email, 53 user_id; 339 from the same record, 124 from a same-trace join); 0 identity keys shaped like resource ids.
- **Lives in:** `experiments/exp003.py` (parser) on `experiments/exp001.py` (reference).

## D8: EXP-002 rejected; EXP-001 stays the baseline (2026-10-24)
- **Lead's decision:** "EXP-002 REJECTED as a replacement for EXP-001. Keep EXP-001 frozen as our performance baseline." The stricter linking research and its synthetic tests stay documented (`docs/EXPERIMENTS.md`, `spike/test_exp002.py`); the regressing implementation is not merged.
- **Evidence:** step F1 0.882 → 0.869; correct steps 112 → 106; wrong account links 4 → 0; 9 of 21 accounts ambiguous.
- **Open:** T03 and T04 remain unresolved identity-linking problems.

## D1: Deterministic core, bounded AI at the edges
- **Chose:** Architecture A. Parsing, identity linking, time filtering, policy and step planning are plain Python. AI is used only "when deterministic extraction cannot reliably resolve request intent, ambiguous data categories, or multimodal evidence", and every AI result is cached.
- **Rejected:** Architecture B (an AI investigator loop per case). Estimated 4–8M tokens per full run against well under 0.2M for A; results would vary between runs; and the model would be deciding things the spec defines exactly (ordering, status rules).
- **Evidence:** 499/518 test cases have exactly one text evidence file mentioning the subject before `audit_at`; evidence is structured (SQL, JSON, key=value logs, a pipe table). The 32 official answers follow fixed rule → step mappings (validator: 0 warnings on R30/R31).
- **Lives in:** to be built (`code/`); guarded by `code/evaluation/validate_output.py`.
- **Still unsure:** how far the hidden set departs from the visible formats.

## D2: Cite the evidence that establishes each resource's state
- **Chose:** per-resource citation (C02). Evidence must be valid at `audit_at` (C03, inclusive per T02). Absence needs authoritative evidence: an explicit negative readback, or a snapshot whose scope covers that system and was captured after the last write (C06). An omitted record in a partial snapshot is not enough.
- **Safeguard from the lead:** "Do not assume exactly one evidence file per case."
- **Rejected:** "one file per case" shortcut (case_04 cites two files).
- **Evidence:** cases 01/02 (absence from a primary+failover snapshot), case_31 (empty `customer_profiles` collection), case_03 (`rows=0 http_status=404` readback), case_04 (two files).
- **Still unsure:** what the grader expects when absence can't be proven (C07).

## D3: Deterministic categories, constrained AI fallback
- **Chose:** category comes from evidence content (explicit label, collection/table, record fields). The AI fallback may only pick one of the 15 `deletion_rules.csv` categories and must quote the supporting evidence. The policy engine, not the model, maps category → action (contract §6).
- **Evidence:** case_12 — an `analytics_platform` record that is a marketing contact (`email_opt_in=true`) is deleted, not anonymized (P18). So category can't be read from `system_id` alone.

## D4: 22 development cases, 10 reserved evaluation cases
- **Chose:** split in `code/evaluation/splits.py`. Reserved: 04, 09, 10, 15, 19, 24, 26, 30, 31, 32.
- **Modification from the lead:** include a complex 14-step multi-system case → case_30 added (replaces case_22, which returns to dev).
- **Wording:** this is a *reserved evaluation set*, not a blind holdout — all samples were inspected during kickoff. "Do not optimize against the reserved set during development." Enforced: `eval.py` refuses `--split reserved` without `--allow-reserved`.
- **Also required:** at least three independent evaluation scenarios we build ourselves (planned in `docs/EXPERIMENTS.md`).

## D5: Contract built from the earlier draft, re-verified
- **Chose:** started from the earlier `docs/contract.md` draft, verified each rule against `problem_statement.md`, `AGENTS.md` and `README.md`, and tagged every rule E (explicit), V (validated by samples) or U (unresolved).
- **Changes vs the draft:** drift reporting decided (C08, from case_05); absence thresholds added (C06, from D2); policy pairs checked against all 32 answers by the validator; open items listed in contract §10.

## D6: `.gitignore` before the first commit
- **Chose:** ignore `.env*` (except `.env.example`), venvs, `__pycache__`/compiled files, `spike/`, `cache/`, `runs/`, `code.zip`, `agent-trace*`.
- **Kept tracked:** `log.txt` — the required transcript. Append-only; earlier entries are never changed.

## D7: Model provider — PROVISIONALLY APPROVED (2026-10-24)
- **Lead's condition:** `claude-haiku-5-5` "for later bounded AI experiments, subject to checking API availability and measuring actual quality and token costs. Do not make paid API calls yet."
- **Status:** no API calls made. EXP-001 needs none.
- **Finding:** no API credential for our solution exists in this environment. The only provider-related variables belong to the Claude Code harness itself (`ANTHROPIC_BASE_URL`, `CLAUDE_CODE_*`), which the solution must not reuse. `anthropic` and `openai` Python SDKs are installed.
- **Recommendation:** Anthropic, `claude-haiku-5-5` ($0.10 input / $0.50 output per 1M tokens, Anthropic list price as of 2026-10-06; lowest-cost current model). Image/PDF input support for this model is to be confirmed with the Models API (`capabilities`) before integration — not yet checked. Escalate a single item to `claude-sonnet-5-5` ($2 / $10) only if Haiku's measured accuracy on our labelled items is not good enough.
- **Rough size (estimate, not measured):** ~375 intent texts + 15 image/PDF extractions ≈ 0.2–0.3M input tokens, cached after the first run → about $0.05 or less per uncached full run.
- **Needs from the lead:** approve the model, and put an `ANTHROPIC_API_KEY` in an uncommitted `.env` (or log in with `ant auth login`). Until then the pipeline runs on its deterministic fallback only.
- **Will record when measured:** exact model, call counts, input/output tokens, cost → `code/evaluation/usage_report.md`.
