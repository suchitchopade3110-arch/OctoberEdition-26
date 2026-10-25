# Release readiness — 2026-10-25 (cloud session)

Branch `claude/intelligent-sagan-ytlgrk`. Rollback: tag `f1-baseline-cloud` -> `6fe50ba` (F1 output sha256 `1503deba…`).
Nothing has been submitted to HackerRank; submission is the team lead's action.

## Submission artifacts

| Slot | File | sha256 | Size | Check |
|---|---|---|---|---|
| `output.csv` | repository root `output.csv` (committed) | `059df99510a0f49244fa8e3460f8b31e873dd5b5102ed32003ab089dd9ff3246` | 587,294 B | 518 unique rows in request order; header exact; validator 3 R12 errors (disclosed) |
| `code.zip` | repository root `code.zip` (gitignored; delivered in the session) | `70d00385dafe0b74df85fd312bd6a3b4eb38f3ad6e4ee8351c089c3d638fd52a` | 109,582 B | official zip command; 52 entries; clean-room run reproduces output.csv byte for byte |
| `chat_transcript` | repository root `log.txt` (committed) | see the final commit (it grows with each logged turn) | ~253 KB | 64 entries, each with one `tool=` and one `model=`; append-only; no keys |

Rebuild `code.zip` from a checkout:
`zip -r code.zip README.md code -x "*/__pycache__/*" "*/.venv/*" "*/venv/*" "*/node_modules/*" "*/.git/*" "*/.DS_Store"`
Regenerate `output.csv`: `python code/main.py --best-effort` (exit status 1 because of the 3 disclosed errors).

## Dashboard

| Target | Result | Status |
|---|---|---|
| 518 rows, schema, ids, order, parseable steps | yes | MET |
| Strict validation, 0 errors | 3 R12 errors (case_55 ×2, case_63), 8 R31 warnings | NOT MET — disclosed best effort (team-lead decision C2) |
| No invented citations / findings / ownership | none added; R12 left unresolved rather than forced | MET |
| Dev status >= 0.95 | 1.0 (22/22) | MET (dev labels) |
| Dev step F1 >= 0.94 | 0.9498 | MET (dev labels) |
| Dev exact sequence >= 0.60 | 0.5909 (13/22) | NOT MET (one case short) |
| Reproducibility | clean room, empty environment: byte-identical output, 136 tests OK, 5/5 scenarios | MET |
| No silent validation bypass | default run refuses; `--best-effort` prints, records and exits 1 | MET |
| Model usage reported | 0 calls in the final run; development Gemini usage carried over | MET |
| Secrets / personal data in code.zip | none found (pattern scan) | MET |
| Code-quality proxy >= 80 | self-assessment ~70 (below); not independently scored | NOT MEASURABLE independently |
| Transcript proxy >= 85 | not independently scored | NOT MEASURABLE |
| Hidden 518-case accuracy | unknown | NOT MEASURABLE |
| Budget | spend not observable from the session; no provider calls made by the solution | NOT MEASURABLE |

## Code-quality self-assessment (honest proxy, not an official score)

Strengths: one source of truth for the output contract shared by agent and validator; explicit evidence provenance
(file, capture time, line, SQL scope); temporal rules with tests; explainable intent and account-basis labels in the run
notes; 136 tests plus 33 evaluator tests and 5 end-to-end scenarios; deterministic, byte-reproducible output; content-
addressed image-fact cache with grounding guards. Weaknesses: the AI component is limited to development-time screenshot
extraction (no model runs in the final pipeline); `auditor.py` mixes identity, account and planning logic; 5 of 11
screenshots unread; 145 ambiguous account picks; 3 unresolved R12 errors. Estimated 65–75/100 with wide uncertainty.

## AI interview brief (each point maps to code or a measurement)

1. **Why deterministic first, where AI sits.** The contract fixes statuses, operations, ordering and policy mapping
   exactly, so these are code (`policy.py`, `contract_spec.py`). Model reasoning is used where text cannot be parsed:
   screenshots were transcribed by Gemini into a fixed JSON schema (`gemini.py`), cached by image sha256
   (`evidence_cache.py`) and accepted only through grounding guards (`images.py`). The final run makes 0 calls.
2. **Claims vs proof.** A worker SUCCESS is never evidence of absence (C04); absence needs an explicit negative readback
   or covering evidence; UNKNOWN is never written as ABSENT in COMPLETE cases — that is why case_55/63 stay R12.
3. **Identity.** Current + historical identifiers from `user_audit_log.csv`; accounts by identifier first (own record,
   keyed lookup, or a subject record naming the account), workflow event only as fallback, with a basis label per case.
   Label-free check: 106/162 agreement of the window method with identifier-confirmed accounts.
4. **Time.** Only evidence captured at or before audit_at; latest observation wins; post-dated rows quarantined;
   an official sample (case_05) shows that omission from a later snapshot is not absence (EXP-C4 rejected).
5. **Backups and flows.** Restore/flow flags read only from schema-declared fields (F1); unreadable flags are UNKNOWN and
   never cited as proof; a backup is a risk only when evidence shows restore allowed (D18-B, upheld in C2).
6. **Prompt injection.** Request text is data; intent is a fixed rule set that cannot be redirected; screenshot facts
   with embedded instructions are quarantined.
7. **Human decisions.** Team lead: D18-B/D18-D (unresolved R12), C2 (publish best effort, disclose), C3 (deadline).
   Agent decisions are labelled as such in `docs/DECISION_REGISTER.md`, with the experiments that justified them.
8. **Known defects.** See `code/evaluation/evaluation_report.md` §10.
