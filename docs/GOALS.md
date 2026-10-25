# Goals — cloud refinement session (2026-10-25)

Set by the team lead in the cloud handoff prompt ("STARKS PRIME — autonomous goal-driven refinement").
Targets are engineering goals, not official scores. Local metrics are never the hidden judge's score.

| Goal | Target | How it is measured |
|---|---|---|
| A. code.zip quality | independent proxy >= 80/100 | rubric review of shipped source only |
| B. output.csv | 518 rows, strict validator 0 errors, no unsupported COMPLETE | `validate_output.py`, evidence audit |
| B. dev accuracy (aspirational) | status >= 0.95, step F1 >= 0.94, exact sequence >= 0.60 | `eval.py --split dev` (22 public samples) |
| C. log.txt | authentic, AGENTS.md-compliant, proxy >= 85 | append-only entries per turn |
| D. reproducibility | documented command regenerates output.csv byte for byte | clean-copy run |
| E. interview | every claim backed by shipped code or a measured experiment | `docs/CLOUD_HANDOFF.md` brief |

## Binding principles (carried from earlier decisions)

- Worker SUCCESS is a claim, not proof (C04). Temporal proximity alone does not establish ownership (D19).
- Missing evidence is not proof of absence; UNKNOWN stays distinct from ABSENT internally.
- Evidence captured after `audit_at` never proves an earlier state and is not cited.
- Never invent citations, never fabricate findings to avoid an unsupported COMPLETE, never weaken the validator.
- No artificial LLM calls. No new paid model calls without explicit authorisation (none given in this session).
- The reserved 10 samples were inspected before; they are reported separately and not used for tuning.

## Budget and time

- Claude Code Cloud budget: $90, ceiling $85. Spend is **not observable** from inside the session; the session
  reports a five-hour rate-limit warning. Work is ordered so that a valid submission exists early.
- Official deadline: not configured in the repository (AGENTS.md §3). Not invented.
