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

## C2 — R12 handling: keep unresolved, publish best effort (team lead, 2026-10-25)

Asked in the session with three options. Team lead's answer (quoted): "DECISION: Select Option 2 — Keep unresolved,
best-effort. Do not reverse D18-B/D18-D solely to eliminate R12 errors. Option 1 is not approved because the evidence
does not conclusively establish restore permission for case_55 or resolve the conflicting resource identity in case_63.
… Clearly disclose any remaining validator errors in the final release report."

Implemented as `python code/main.py --best-effort`: explicit flag, every error printed and recorded in run_notes.json,
exit status 1. The default run still refuses to publish an invalid file.

## C3 — deadline override (team lead, 2026-10-25T08:15Z)

"we now have a maximum of 2 hours available … Stop all new development within 60 minutes … Submission readiness takes
priority." Development closed at about 08:26Z after EXP-C4; the rest of the session was release work.

## Experiment decisions (agent, measured; see docs/EXPERIMENTS.md "Cloud session")

| Experiment | Decision | Evidence |
|---|---|---|
| EXP-C1 identifier-first accounts (C1e) | ACCEPT | dev F1 0.903 -> 0.914, exact 0.409 -> 0.500; 1 test row changes; validator unchanged |
| EXP-C1b strict result + 15-min skew | REJECT | label-free agreement 102/162 vs 106/162 (F1 rules); cascading ambiguous swaps |
| EXP-C1c 120-min lead window | REJECT | dev F1 0.898; removed accounts of the multimodal cases (R12 3 -> 4) |
| EXP-C1d PARTIAL also accepts SUCCESS | REJECT | label-free agreement 83/162; 52 test rows churn |
| EXP-C2 collection file -> manifest origin as system | ACCEPT | dev F1 0.914 -> 0.938, exact 0.500 -> 0.545; 0 test rows change |
| EXP-C3 rule-based intent | ACCEPT | dev status 0.955 -> 1.0, F1 0.950, exact 0.591; only sample case_05 changes among 550 texts |
| EXP-C4 omission from a later snapshot = absence | REJECT | contradicts official samples case_05 and case_24; dev status 1.0 -> 0.955 |
