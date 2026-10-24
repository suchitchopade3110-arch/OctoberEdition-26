# Trap findings

Traps in the dataset that can produce a wrong `deletion_status` or wrong `steps_json`.
Counts are only given where they were **measured** with a script during this session; anything else says "not counted".
"Dev" = the 22 development samples (`code/evaluation/splits.py`). Reserved cases are not used here.
Status: **FIXED** (handled and verified on at least one real instance) · **PARTIAL** (handled for some forms) · **OPEN** (not handled) · **UNVERIFIED** (handled in code, never exercised).

Last updated: 2026-10-24, after EXP-006 (EXP-005 rejected for production; production = accepted keyword intent rule, which misclassifies 9 of the auditor's 17 intent probes — see `code/tests/fixtures/audit_repro_cases.json`). Reserved-set note: one reserved request text and its old-rule outcome were seen during the EXP-004 proposal survey; it has not been labelled, scored or used to build rules. T03 and T04 remain unresolved identity-linking problems (EXP-002 rejected). T08 stays unresolved until evidence is found or the contract reading is clarified.

---

### T01 — Historical identity mismatches
- **Description:** the request email, or the identifier inside evidence, is an *old* value from `user_audit_log.csv`, not the current snapshot.
- **Observation:** 100 of the 518 test requests match only a historical email (measured at kickoff). In case_12 a record is linked only through `correlation_key` = SHA-256 of the user's old email, which is listed in the audit log as `email_hash` `old_value`.
- **Confirmed count:** 100 test requests with a historical-only email. Evidence-side occurrences: not counted.
- **Detection:** subject key set = current + all historical email/phone/email_hash + `user_id` (contract I01–I03).
- **Impact:** missed records → false COMPLETE or missing findings.
- **Coverage:** EXP-001 key set; case_12 reproduced exactly on dev.
- **Mitigation:** keep exact matching on the full historical key set; add scenario S2 (hash-only link).
- **Tests:** dev case_12 (exact match in EXP-001 run 2). Historical *phone* links: never exercised.
- **Status:** PARTIAL (email and hash verified; phone unverified).

### T02 — Evidence after `audit_at`
- **Description:** files captured after the cutoff mention the subject and may show a different state.
- **Observation:** 196 of 518 test cases have at least one text evidence file mentioning the subject captured after `audit_at` (measured at kickoff).
- **Confirmed count:** 196 test cases (text files only).
- **Detection:** every observation and activity event is filtered by `captured_at`/`event_time <= audit_at` (T01/T02 in contract); validator rule C03 rejects later citations.
- **Impact:** wrong state, wrong status, invalid citation.
- **Coverage:** EXP-001/002 filters; validator C03 (unit test `test_evidence_after_audit_at`); EXP-002 test `test_evidence_after_cutoff_is_ignored`, `test_catalog_link_respects_cutoff`.
- **Mitigation:** build scenario S1 (later file showing deletion must not change the answer).
- **Status:** PARTIAL (enforced and unit-tested; end-to-end scenario S1 not built).

### T03 — Neighbouring workflow / account collisions
- **Description:** the account to verify is often named only in a deletion-worker event with no user identifier. Requests reported in the same batch share the same time window, so several requests compete for the same few account events.
- **Observation:** EXP-001 assigned a neighbour's account in 4 dev cases (06, 17, 25, 29). With EXP-002's elimination-only rule, 9 of 21 dev deletion cases remain ambiguous among 3–6 candidate accounts. EXP-001's unflagged tie-break was right in 7 of those 9.
- **Confirmed count:** 9 ambiguous dev cases under elimination; 4 wrong assignments in EXP-001.
- **Detection:** per-case candidate sets from worker `DELETE_RECORD` events in a window around `reported_at`, minus accounts grounded to other users; ambiguity recorded with all candidates (`spike/exp002_omit_run.json`).
- **Impact:** missing or wrong `VERIFY_RECORD_ABSENT` on `account_service` (R31) — a step every authorized case has.
- **Coverage:** EXP-002 (rejected) removes all 4 wrong links but leaves 9 ambiguous.
- **Mitigation:** team-lead decision needed: omit the account step when ambiguous, or emit a flagged ranked choice. A better ranking signal has not been found yet; EXP-002's result/time ranking was worse than omitting.
- **Tests:** `spike/test_exp002.py` — colliding windows stay ambiguous; grounded neighbour forces the other; chain elimination; no tie-break by time.
- **Status:** OPEN.

### T04 — Already-anonymized resources without direct identifiers
- **Description:** a record that is already compliant (anonymized analytics) carries no identifier; only the deletion worker's anonymize action ties it to a request.
- **Observation:** dev cases 03, 21, 25, 27, 28 each miss one `VERIFY_RECORD_ANONYMIZED` (5 steps). The only link for these records is one `ANONYMIZE_RECORD` activity row; e.g. on 2026-08-30 two such actions for two different requests are 44 s apart. EXP-002 found 32 ungrounded worker actions across 8 dev cases and **all** remained ambiguous; 0 were linked.
- **Confirmed count:** 5 missing dev steps; 32 ambiguous attributions (EXP-002).
- **Detection:** worker actions inside a request's run, with single-cardinality elimination (types observed at most once per user, derived from data).
- **Impact:** COMPLETE cases lose a verification step; status unaffected in dev.
- **Coverage:** none effective.
- **Mitigation:** none found that avoids guessing. Possible inputs not yet used: image evidence (`analytics_profile_view` screenshot), other requests' grounded analytics at later cutoffs (would break T02).
- **Tests:** `spike/test_exp002.py` overlapping runs stay ambiguous; grounded neighbour resolves single-cardinality type.
- **Status:** OPEN.

### T05 — Unparsed log formats
- **Description:** logs come in four line formats: plain `k=v`; `TS [LEVEL] [service] [trace] event: k="v"` (bracket); `requestId=.. function=.. message="k=\"v\""` (escaped); `TS {json}` (JSON lines).
- **Observation (EXP-003):** the escaped format (2 files) and JSON format (2 files) were missed entirely by EXP-001; the bracket format (2 files) was half-parsed — ids found but service and trace lost, so trace joins and system attribution failed. The 3 "missed" ids in `customer_search_primary_20260910.sql` are `source_resource_id` pointers, not resources (correctly not extracted).
- **Confirmed count:** 423 resource-id occurrences in 4 files missed; 46 bracket-format resources missing their user link; 343 malformed ids (with stray backslashes) extracted by EXP-001 from the escaped format.
- **Detection:** per-file count of ids in a resource position (`resource_id` key, SQL row key, pipe column) vs ids extracted; precision = extracted ids that sit in such a position.
- **Measured (EXP-003):** coverage 2080/2503 (83.1%) → **2503/2503 (100%)**, all 78 files with ids; precision 2080/2423 → **2503/2503**, 0 false positives; 463 new resource→user links by exact key, 0 lost.
- **Impact:** missed findings / absence evidence. Dev: **no output change** (no dev case depends on these files). Test set: 83 new links reach requesting users from evidence available at their `audit_at` (unscored).
- **Coverage:** `spike/exp003.py` (format detected per line; multiline continuation; malformed counted and skipped; exact duplicates dropped; provenance: file id, capture time, line time, line number).
- **Tests:** `spike/test_exp003.py` — 17 synthetic tests: each format, multiline, trace join (and no cross-trace join), missing resource id, duplicates, conflicting observations, cutoff, unrelated-user record, malformed lines, false-positive extraction from path/reference fields, non-system emitter.
- **Status:** FIXED for the current inventory (accuracy effect on scored cases: none measurable on dev).

### T06 — Non-deletion and negated deletion requests
- **Description:** requests for access, export, correction, opt-out, or text that mentions deletion only to refuse it.
- **Observation:** 10 test request texts are clearly non-deletion (e.g. "This is an information request, not a request to erase it"); 10 `CLASSIFY_REQUEST` activity rows mark accounts as non-deletion (claims). No official sample is NOT_APPLICABLE. EXP-001's keyword rule misread a real deletion request (case_05: "remove any remaining **copy of** my…").
- **Confirmed count:** 10 non-deletion texts in the test set (keyword scan + read-through); 1 dev false negative.
- **Detection:** keyword classifier (EXP-001).
- **Impact:** whole case wrong: steps lost (case_05: 3 steps + status) or a non-deletion case answered with steps.
- **Coverage:** keyword rule only; no labelled NOT_APPLICABLE case scored.
- **Mitigation:** label the 10 texts (team lead), add negation-aware rules, constrained AI fallback under D7.
- **EXP-005 (not yet accepted):** clause-level classifier (action, target, negation; quoted text and system-addressed clauses set aside; six languages). Dev case_05 fixed (+3 steps, status); 0 false rejections and 0 false authorisations on a 50-row synthetic set written before the classifier; of 540 non-reserved real texts exactly one decision changed (case_05) and the 10 non-deletion texts stay non-deletion; 0 real texts abstain. Open: human-reviewed labels (`docs/INTENT_REVIEW.md`), PARTIAL_SCOPE output limitation, unsupported languages fall to NO_ACTION, multilingual rules not native-validated.
- **EXP-005 validation (Step 3):** new sub-traps found with fresh probes — (a) negation from a neighbouring phrase ("No need to confirm, just erase my profile") rejects a real deletion; (b) deletion requests in unsupported languages (de, it, nl, zh, ru) end as `NOT_APPLICABLE` without an explicit flag; (c) partial-scope requests are currently authorised (D11-P proposes not authorised). None of these occurs in the 540 non-reserved real texts.
- **EXP-005 revisions R1–R5:** (a) negation scope now stops at phrase boundaries — fixed, 7/7 negation probes; (b) unsupported languages → `ABSTAIN:UNSUPPORTED_LANGUAGE`, flagged for review (final output still `NOT_APPLICABLE`, the only non-authorising status); (c) partial scope and single-category erasure → `PARTIAL_SCOPE_UNSERVED`, not authorised (D11-P, our conservative interpretation, not an explicit contract rule). Real texts unaffected (0 of 540 non-reserved change).
- **Status:** PARTIAL (rules revised and tested; not independently validated until the team lead's labels are in).

### T07 — PDF / image-only evidence
- **Description:** facts that exist only in 11 screenshots or 4 PDFs.
- **Observation:** dev case_07's `support_001` is only in `delivery_correction_attachment.pdf` → status and 4 steps missed. 19 test cases have no text evidence mentioning the subject (measured at kickoff); that these are image/PDF cases is inferred, not verified.
- **Confirmed count:** 1 dev case; 15 multimodal files.
- **Detection:** none (parser skips PNG/PDF).
- **Impact:** false COMPLETE, missing findings.
- **Coverage:** none. PDFs have extractable text (pypdf); PNGs need vision.
- **Mitigation:** one-time cached extraction (pypdf for PDFs; `claude-haiku-5-5` for PNGs per D7 after quality check).
- **EXP-007 (not yet accepted):** all 4 PDFs read offline with pypdf; 3 yield linked observations (`export_1842`, `audit_record_003`, `support_001` — dev case_07 now an exact match), the legal register is multi-subject and unlinkable. 11 PNGs still unread (no offline OCR installed; method decision D14-PNG pending).
- **Status:** PARTIAL (PDFs done in an uncommitted experiment; PNGs open).

### T16 — Catalog-linked resources whose state exists only in multimodal evidence (new, EXP-006B)
- **Description:** a resource is tied to the subject only by a data-catalog `LINK_RESOURCE_IDENTITY` activity row; its state at `audit_at` is visible only in a PNG/PDF (text observations exist only after the cutoff).
- **Observation:** 8 of the 9 invalid results of the full run (cases 33, 35, 39, 50, 52, 55, 63; plus case_45's dropped retained record) come from such resources — the 9th is case_55's workflow-matched account `account_2595`, which has no observation at all: `export_1260`, `export_1842`, `search_428`, `data_flow_1121`, `backup_9287`, `marketing_001`, `analytics_7438`, `audit_record_003`.
- **Confirmed count:** 8 resources across 8 test cases.
- **Detection:** production notes `UNKNOWN state` / `UNPROVEN COMPLETE`; strict validator R12; `code/tests/test_audit_repro.py`.
- **Impact:** COMPLETE claimed without proof (F01); retained record silently dropped (F12); wrong system for catalog-only exports (`object_store`, T12).
- **Coverage:** detected and blocked at publication. EXP-007 (PDF text, offline) resolved `export_1842` (case_33) and `audit_record_003` (case_45) through evidence; 6 PNG-only resources and one evidence-free account (case_55 `account_2595`) remain.
- **Mitigation:** PNG extraction method (D14-PNG) pending; case_55's account cannot be proven by any file in the dataset.
- **Status:** PARTIAL.

### T08 — Retained security records with insufficient evidence
- **Description:** official answers verify a retained `audit_record_*` that is not observable at `audit_at`.
- **Observation:** `audit_record_6645` (case_18) and `audit_record_5569` (case_20) appear in **no** participant text file and no activity row; two screenshots checked do not show them. `audit_record_4128` (case_23) and `audit_record_3954` (case_29) appear only in `evidence_02`, captured 2026-09-17, after those cases' `audit_at` (2026-09-15).
- **Confirmed count:** 4 dev steps (2 unobservable anywhere in text, 2 only after cutoff).
- **Detection:** grep of all text evidence and activity; manifest capture times.
- **Impact:** missing `VERIFY_RECORD_PRESENT` steps (uncited in INCOMPLETE cases). Status unaffected.
- **Coverage:** none; using the later file would break T02/contract T01.
- **Mitigation:** contract decision needed (team lead). Remaining 9 images not yet inspected for these ids.
- **Status:** OPEN (UNVERIFIED whether any image contains them).

### T09 — Database replica drift
- **Description:** a record deleted from the primary still exists in a replica.
- **Observation:** `account_005` exists only in `customer_profiles_failover_replica` (evidence_54); official answer reports `account_service REPORT_REMAINING_RECORD` citing evidence_54.
- **Confirmed count:** 1 dev instance (others not counted).
- **Detection:** SQL parser reads every table; replica rows count as presence under the logical system (contract C08).
- **Impact:** false COMPLETE if replicas are ignored.
- **Coverage:** a probe with intent bypassed produced exactly the official 3 steps for case_05; the real run misses it because of T06.
- **Status:** PARTIAL (detection verified on one instance; blocked by T06 in the scored run).

### T10 — Simultaneous cross-system policy violations
- **Description:** one case needs findings across search, analytics, support and integration, with correct remediation order.
- **Observation:** dev 14-step cases 11, 18, 29. In EXP-001 run 2, case_11 is an exact match; case_18 misses only the T08 audit record; case_29 misses the account (T03) and audit record (T08).
- **Confirmed count:** 3 dev cases.
- **Detection:** policy table per resource + R15/R16 ordering; validator R15/R30.
- **Coverage:** all findings, remediations and ordering correct in those cases.
- **Status:** FIXED (dev; remaining misses belong to T03/T08).

### T11 — Similar-looking identifiers belonging to different users
- **Description:** lookalike emails, or lookups that *searched* for a user's email but found nothing.
- **Observation:** case_28's request warns a similar email belongs to someone else; exact matching ignores it. New in EXP-002: a March readback searched `account_6523` with user_17's email and got `404 rows=0`; EXP-001 treated that as ownership and added a wrong account step to case_17 (the account was deleted later for another request).
- **Confirmed count:** 1 decoy lookup causing a wrong dev step; lookalike emails not counted.
- **Detection:** exact key matching; EXP-002 treats failed lookups as weak hints that need workflow corroboration.
- **Coverage:** exact matching (EXP-001); the weak-hint rule exists only in rejected EXP-002.
- **Tests:** `spike/test_exp002.py` — failed lookup is not ownership; failed lookup kept only as weak hint; lookalike does not link; other user's identifier links to them only.
- **Status:** PARTIAL.

### T12 — Incorrect system / category attribution
- **Description:** wrong `system_id` or wrong data category (changes the required action).
- **Observation:** EXP-001 run 1 put `audit_record_*` under `archive_service` and `support_*` under `search_service` (prefix map overrode evidence context) — fixed in run 2. Still open: collection-style export JSON names no system, so `export_001` becomes `object_store` (case_08, 3 missing + 3 extra). Category: case_12's analytics-platform contact record with `email_opt_in` must be MARKETING_PROFILE (DELETE) — handled.
- **Confirmed count:** 1 open dev case (08).
- **Detection:** evidence-context system first, prefix fallback; category from labels, collections and fields (D3).
- **EXP-003 note:** in the two bracket-format logs, wrong systems (`archive_service` for 10 audit records, `search_service` for 3 support records, `object_store` for 1 export, per file) were caused by the lost `[service]` field — a parsing defect, now fixed. Case_08's `object_store` error comes from a collection-style JSON file with no system field — a **different** cause, still open. New sub-form: the escaped format's `function=profile_service` is an emitting component, not a system (300 lines); EXP-003 only uses log service names that structured evidence also uses as systems.
- **Status:** PARTIAL.

### T13 — State sequences inside one file (new, EXP-003; addressed by EXP-004)
- **Description:** one evidence file observes the same resource more than once with different states over time (e.g. absent, then present again two days later — possible recreation).
- **Observation:** 14 (file, resource) pairs, all accounts. 7 are timed by log-line timestamps (logs); 7 by the row's own `recorded_at` in manifest-style records — which the baseline parser drops, making them look like ties. E.g. `account_5284` (evidence_16) ABSENT 07-28 → PRESENT 07-30; `account_945` (evidence_22) FOUND 06-17 → NOT_FOUND 06-23.
- **Confirmed count:** 14 pairs; 12 produce a different state once ordered by observation time (the other 2 contain a post-dated row, T15). 11 of the 12 accounts belong to requesting users — all in the unlabelled test set; 0 dev, 0 reserved.
- **Detection:** `exp003.conflicts()`; EXP-004 attaches line time or record time to every observation (229 manifest rows re-timed).
- **Impact:** baseline keeps the earliest row inside a file → stale state: a recreated account reported absent (false COMPLETE) or a deleted one reported present (false finding).
- **Coverage (EXP-004, not yet accepted):** state = latest reliable observation time ≤ `audit_at`; line order never used. Reconstructs **14/14** (baseline 2/14). Across all 81 case cutoffs: 12 distinct state changes vs baseline, all backed by a strictly later reliable observation (0 false-positive changes); 16 reappearance flags; 0 temporal-consistency violations.
- **Tests:** `experiments/test_exp004.py` (17): each required transition, cutoff, out-of-order lines, equal-time ties (comparable, incomparable, provenance kept), primary-vs-replica copies not merged, missing timestamps, record time, post-dated rows, repeated observations.
- **Status:** FIXED (EXP-004 accepted, D10; commit recorded in `docs/DECISIONS.md`). Dev unaffected; test-set impact unscored.

### T15 — Post-dated rows (new, EXP-004)
- **Description:** a row's own timestamp is later than the moment its file was exported/captured.
- **Observation:** `connector_configurations_20260812.json` (exported 08-12 09:00) holds an `account_1417` FOUND row recorded 08-14; `customer_export_manifest_20260409.json` (exported 04-09 12:00) holds an `account_5043` FOUND row recorded 04-11. In both, the earlier row says NOT_FOUND.
- **Confirmed count:** 2 rows (1 of 39 and 1 of 46 in those files; 0 in `security_audit_ledger_20261001.json`).
- **Detection:** observation time > file `captured_at`.
- **Impact:** trusting the row creates a "still present" state from evidence that could not have existed at capture time.
- **Coverage:** EXP-004 (D10-B) quarantines post-dated rows from state selection, keeps and flags them; they cannot override a valid earlier observation.
- **Status:** FIXED for selection (D10-B). Whether the dataset intends these as decoys is unverified.

### T14 — Bulk records for unrelated users (new, EXP-003)
- **Description:** high-volume background records about real users who never requested deletion.
- **Observation:** `cloud_runtime_export_af_south_20260930.log` holds 300 profile lookups (5-digit account ids, `rows=1`, an email in `correlation_key`). All 300 emails are current identities; 0 belong to any requesting user; the 300 accounts appear in no other file and no activity row.
- **Confirmed count:** 300 records, 0 requesting users affected.
- **Detection:** cross-check of extracted links against all request emails.
- **Impact:** none observed; a parser that linked by fuzzy or partial match could have created false findings.
- **Coverage:** exact-key linking; T11 tests.
- **Status:** FIXED (no false association measured).
