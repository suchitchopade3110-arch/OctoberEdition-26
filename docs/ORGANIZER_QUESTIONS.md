# Clarification request — Ghost Data Still Exists (October 2026)

We are asking about how the output contract applies where the participant evidence cannot settle a case. We have **not
received any clarification yet**. The examples below cite only case, resource and evidence IDs from the public dataset.

## Q1. A resource whose state at `audit_at` the evidence cannot establish

The contract says a `COMPLETE` row may contain only verification steps that cite evidence proving the state at `audit_at`.
An `INCOMPLETE` row needs at least one finding that cites evidence. Some resources have neither kind of evidence: for
example, the only record of an account deletion is a deletion-worker `SUCCESS` activity row, which the contract treats as a
claim.

**How should such a resource be reported?** Should it:

- (a) be verified on a `COMPLETE` row without a citation;
- (b) make the case `INCOMPLETE` even though no finding can be cited; or
- (c) be left out of the row?

Example: case_55, account_2595 (activity_1640).

## Q2. A retained backup with no evidence of whether restore is blocked

A backup archive is shown holding the requester's data, with its checksum verified and a past restore drill. No restore
permission and no restore block is shown, and no block or check event exists before `audit_at`. The policy for
`BACKUP_ARCHIVE` is RETAIN plus block restore. The problem statement describes a restore risk as a backup that can bring
deleted data back.

**Does a retained backup with no evidence of a restore block count as an active restore risk**
(`REPORT_RESTORE_RISK`)? Or is a restore risk reported only when evidence shows that restore is allowed?

Example: case_55, backup_9287 (evidence_32).

## Q3. Catalog identity rows versus identifiers printed in the evidence

A `data_catalog` activity row links a resource to the requester. The screenshot of that resource shows a different name,
email and phone, which match no known person.

**When a catalog identity row and the identifiers printed in the evidence disagree, which decides ownership?**

Example: case_63, marketing_001 (activity_4008, evidence_60).

## Q4. Derived extraction artifacts in `code.zip`

Our agent reads screenshots through structured facts extracted once with a multimodal model. The facts are stored as small
JSON files, keyed by each image's SHA-256, so a clean run needs no API key or network. The files hold only text transcribed
from the dataset's own screenshots, with no labels, no case decisions and no credentials. The model calls that produced
them are disclosed in `usage_report.md`.

**May these derived files be included in `code.zip`?** Or should the submitted code re-extract the images at run time
instead?
