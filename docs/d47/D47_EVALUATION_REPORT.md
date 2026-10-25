# D47 evaluation report — candidate vs accepted release

**OFFICIAL TARGET: NOT YET VERIFIED.** Official scores of the accepted release (as reported by the team lead): output
25.2/30, code 16.8/30. Targets: output > 28, code > 25. Nothing below is an official score.

## Gating facts

| Item | Finding |
|---|---|
| Deadline | Not verifiable from the container (HackerRank and Internshala blocked by the proxy). A third-party listing says the 24-hour build window opened 24 Oct 2026 18:00 IST, i.e. ends **25 Oct 12:30 UTC**. Development was frozen with margin. |
| Resubmission | **Unknown** — no official rule could be read. Confirm on the submission form before relying on this candidate. |
| Budget | This cloud session had spent **$19.81** when D47 started (session cost record); no provider calls were made by the solution. |

## Candidate

| | Accepted release | D47 candidate |
|---|---|---|
| Commit | `4f61906` (tag `release-accepted`) | `09bcc92` on branch `d47-experiments` |
| output sha256 | `059df995…3246` | `e03e7a16442b4547b9a99fc57f9c43d83bd8fa7cbe4ea04339e725c0782e271b` |
| code zip sha256 | `70d00385…8fd52a` | `90ef2490f3c17c28b4501894f2f118d638b1785aa0d9231bc7db6ab1b6e750c3` (68 entries) |
| Status counts C / I / NA | 160 / 348 / 10 | 159 / 349 / 10 |
| Steps | 2,947 | 2,955 |
| Strict validator | 3 R12 errors, 8 R31 warnings | **same** 3 R12 errors, 8 R31 warnings |

## Metrics on the public samples [measured] — identical, because no sample row changed

| Split | Status | Step P / R / F1 | Field | Exact sequence |
|---|---|---|---|---|
| Dev (22) | 1.0 | 0.984 / 0.918 / 0.950 | 0.906 | 0.591 |
| Reserved (10, inspected earlier, not a holdout) | 0.80 | 0.936 / 0.746 / 0.830 | 0.748 | 0.40 |
| All 32 | 0.9375 | 0.971 / 0.865 / 0.915 | 0.858 | 0.531 |

The D47 changes touch only test rows, so the public samples cannot measure them. Their support is the evidence itself
(each row below), not a sample score.

## Every changed output row

| Case | Release | Candidate | Evidence and reason |
|---|---|---|---|
| case_34 | INCOMPLETE | INCOMPLETE + REPORT_REMAINING_RECORD account_5762 [evidence_04], DELETE_RECORD | evidence_04 (account admin console, captured 09-26T11:00, before audit_at 09-27T13:00) prints `user_11 · account_5762`, the subject's email and phone on a live profile; the catalog links it to the subject. Read by local OCR (EXP-D1); previously no extraction existed. |
| case_53 | COMPLETE | **INCOMPLETE**: REPORT_EXPOSED_PII support_1034 [evidence_28] → REDACT → VERIFY_REDACTED; account verification becomes a future check | evidence_28 (support console, captured 05-24T07:00, before audit_at 05-25T09:00) prints `support_1034 – Kofi Agyeman` and the subject's email in the retained conversation; rule_05 requires redaction. Read by OCR (the earlier Gemini extraction had put the ticket number in the id field and was rejected). |
| case_421 | INCOMPLETE | INCOMPLETE + REPORT_REMAINING_RECORD search_3251 [evidence_39], DELETE, VERIFY | activity_754 (02-27, after the request of 02-24) says the subject's connector data_flow_4750 "repopulated downstream resource search_3251"; evidence_39 (03-25T08:59, before audit_at 03-25T09:00) shows search_3251 still returning a hit. Lineage link (EXP-D4). |

No new COMPLETE claims. One COMPLETE → INCOMPLETE (case_53), backed by a cited pre-cutoff screenshot.

## Remaining R12 errors (unchanged, disclosed — decision C2)

case_55 account_2595 and backup_9287, case_63 marketing_001: no authoritative evidence of their state exists. Not
forced; OCR confirms the marketing screenshot shows a different person (Soo-jin Park, sj.park@naver.com).

## Remaining opportunities (honest estimate)

| Gap (from dev analysis) | Share of dev cases | Recoverable? |
|---|---|---|
| Anonymized analytics profiles (no identifier; only a worker event in a shared window) | 5/22 | Not without timing attribution, which is ruled out |
| Retained audit records absent from all pre-cutoff evidence | 4/22 | No |
| Ambiguous primary accounts (145 of 508 in the test set) | 2–3/22 | No non-timing signal found |
| case_61 attachment object_19 (screenshot prints file name, no person) | 1 test case | Would need single-case rules; not built |

Expected effect of D47 on the official output score: small (3 of 518 rows, each strongly evidenced). A gain to >28/30
is **unlikely** from these changes alone; the dominant gaps above are structural.

## Recommendation

Replace the accepted release **only if a resubmission is allowed**: the candidate is a strict superset in evidence use
(3 evidence-backed row changes, no new COMPLETE claim, same validator result, byte-reproducible without the OCR
package) and adds a runtime model component, typed decision traces and a trace consistency gate to the code. If
resubmission is not possible, nothing is lost: the accepted release remains on tag `release-accepted`.
