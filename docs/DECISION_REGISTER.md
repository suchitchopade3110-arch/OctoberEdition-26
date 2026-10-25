# Decision register — cloud refinement session

Historical decisions D1–D37 are in `docs/DECISIONS.md` and are not rewritten. This file records decisions taken in
the cloud session that started 2026-10-25T07:59Z. "Agent" entries are engineering choices made autonomously under the
team lead's goal-driven prompt; they are not user approvals. Entries quoting the team lead say so.

## C0 — scope and authority (team lead prompt, 2026-10-25)

- Autonomous, reversible experiments are authorised on isolated branches/worktrees; keep or revert by measurement.
- Not authorised without explicit approval: new paid model calls, force-push, merge to main, publication of the
  dataset, HackerRank submission.
- The F1 baseline (`6fe50ba`, output sha256 `1503deba…`) is retained as the rollback point.

## C1 — baseline reproduced (agent, measured)

The F1 output, dev and reserved metrics, test counts and validator findings were reproduced exactly in this
container (see `MEASUREMENT_SCORECARD.md`). Development may begin from `6fe50ba` semantics.
