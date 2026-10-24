# Submission blockers (D26) — state at commit 3ebdc49 + D25/D26 docs

## 1. Strict validation of the 518-row output (D18 production, unchanged)

`python code/main.py`, then `python code/evaluation/validate_output.py --output runs/output.candidate.csv`:

```text
valid=False rows=518 steps=2899 errors=3 warnings=8
  ERROR [R12] case_55: step 1 needs a non-empty evidence_id     (account_2595, VERIFY_RECORD_ABSENT)
  ERROR [R12] case_55: step 2 needs a non-empty evidence_id     (backup_9287, VERIFY_RESTORE_BLOCKED)
  ERROR [R12] case_63: step 1 needs a non-empty evidence_id     (marketing_001, VERIFY_RECORD_ABSENT)
  WARN  [R31] no account_service VERIFY_RECORD_ABSENT step: case_50, 63, 127, 169, 226, 256, 301, 472
```

`output.csv` is therefore **not published**: the gate in `main.py` refuses to write it. Under the interpretation
established so far (D18-B, D18-D, D25), no output row for these three resources is both supported by evidence and accepted
by the validator. The three errors are **UNRESOLVED**, not fixed.

Known silent-omission risks that the validator cannot see: case_46 (tombstone_17) and case_53 (support_1034) are COMPLETE
while a resource linked to the person has no usable observation and is left out of the steps.

## 2. Open decisions

| Decision | Blocks | Status |
|---|---|---|
| Q1–Q3 in `docs/ORGANIZER_QUESTIONS.md` (or an explicit team-lead fallback) | publishing `output.csv` | no answer received |
| Q4 / D18-A: ship `code/evidence_cache` in `code.zip` | final `code.zip` | no answer received |

## 3. Smallest compliant change for each possible answer

Each change needs a regression test and a full re-run: 518 cases plus dev, compared with D18, with every changed row
listed.

| Answer | Smallest change | Scope | Regression test |
|---|---|---|---|
| Q1 (a): verify without a citation | none in the agent; the validator's R12 citation check would have to allow it, which is a contract change, not ours to make | — | — |
| Q1 (b): unproven resource makes the case INCOMPLETE | a policy rule: an unproven required treatment yields a finding. But a finding needs evidence, so this only works where presence evidence exists. **account_2595 has none**, so (b) alone cannot fix it | generic | synthetic: an unproven account without presence evidence gives no fabricated finding |
| Q1 (c): leave the resource out | the planner drops resources with no observation; case_55 still needs backup_9287 settled; case_63 would become COMPLETE `[]`, which needs Q1 to say `[]` is acceptable (our R12 reading forbids it) | generic | synthetic: a dropped resource never yields an empty COMPLETE unless allowed |
| Q2 yes: an unblocked retained backup is a restore risk | backup rule: RETAIN backup whose subject is evidenced and with no block evidence ≤ audit_at → REPORT_RESTORE_RISK citing that evidence, then BLOCK_RESTORE, then VERIFY_RESTORE_BLOCKED. case_55 becomes INCOMPLETE; account_2595 becomes a post-remediation check | generic; on current data affects only case_55 (the only backup with unknown restore state) | synthetic: a backup with block evidence stays COMPLETE; one with "restore allowed" stays a risk; one with no restore information becomes a risk |
| Q2 no: report risk only when restore is shown allowed | no change; case_55 stays unresolved | — | — |
| Q3 catalog decides | stop the unknown-person guard from overriding a catalog link; marketing_001 becomes a remaining record citing evidence_60 (case_63 INCOMPLETE) | generic; on current data affects only case_63; reopens a false-link risk | synthetic: a catalog-linked row showing another known person stays unresolved |
| Q3 printed identifiers decide | no change; marketing_001 is not user_09's. case_63 then has no evidenced resource, so it needs the Q1 answer | — | — |
| Q4 cache allowed | ship `code_with_cache` (reproduces D18) | — | clean-copy test (passes) |
| Q4 cache not allowed | ship without it: the output falls back to PDF-only (7 R12 errors), and 4 shipped tests fail unless adjusted. Alternatively, require keys and run `--live-extraction` (re-extraction is not deterministic) | packaging | clean-copy test without cache |

If no answer arrives, there is **no fully evidence-grounded, validator-passing 518-row output** under the interpretation
established so far. Any fallback must be an explicit, recorded team-lead decision, and must never be a COMPLETE that cites
a claim or contradicting evidence.

## 4. Packaging candidates (built, not submitted)

Both mirror the official `zip -r code.zip README.md code -x "*/__pycache__/*" ...` and live in `runs/package/`:

| Candidate | Files | Contents checks | Clean copy (code.zip + dataset/, empty environment) |
|---|---|---|---|
| `code_with_cache.zip` | 41 | README and both reports present; no dataset, `.env`, binaries, archives, caches or keys | output byte-identical to D18; 101 tests OK; scenarios 4/5 |
| `code_without_cache.zip` | 34 | same | output = PDF-only (7 R12 errors); 4 tests fail (they expect the cache) |

## 5. Transcript

- `log.txt`: 49 entries (4 SESSION START, 45 turns), timestamps in order, each with exactly one `tool=` and one `model=`
  line, no key-shaped strings (3 `[REDACTED]`).
- The **session trace export** (agent-trace zip) is separate. It still contains the three API keys pasted in chat and
  must be redacted before upload, as `agent_trace_instructions.md` requires.
