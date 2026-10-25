# Measurement scorecard

All numbers measured in this cloud session unless marked. Dev = 22 public samples (`code/evaluation/splits.py`).
Reserved = 10 public samples, inspected in earlier sessions, **not** a clean holdout.

## Baseline F1 (commit 6fe50ba, reproduced 2026-10-25 on Linux / Python 3.13)

| Metric | F1 baseline | Current | Target | Evidence |
|---|---|---|---|---|
| 518 output sha256 | 1503deba…91eb | — | — | `sha256sum runs/output.candidate.csv` (byte-identical to accepted artifact) |
| Strict validator errors / warnings | 3 (R12) / 8 (R31) | — | 0 / — | `validate_output.py` |
| Status counts C / I / NA | 160 / 348 / 10 | — | — | output |
| Steps | 2,947 | — | — | validator |
| Dev status accuracy | 0.9545 | — | >= 0.95 | `eval.py --split dev` |
| Dev step P / R / F1 | 0.9431 / 0.8657 / 0.9027 | — | F1 >= 0.94 | same |
| Dev field accuracy | 0.8455 | — | improve | same |
| Dev exact sequence | 0.4091 (9/22) | — | >= 0.60 | same |
| Reserved status / F1 / exact | 0.80 / 0.8302 / 0.40 | — | report only | `--split reserved --allow-reserved` |
| Production tests | 126 OK, 16 expected failures | — | no regressions | `unittest discover -s code/tests` (needs google-genai installed; 2 tests error without it) |
| Evaluator tests | 33 OK | — | — | `test_evaluator.py` |
| Custom scenarios | 4/5 (S4 fails) | — | 5/5 | `custom_scenarios.py` |
| Model calls in final run | 0 | — | — | run notes |

## Dev misses at baseline (root-cause classes)

| Class | Dev cases | Recoverable from pre-cutoff evidence? |
|---|---|---|
| Anonymized analytics profile never linked (VERIFY_RECORD_ANONYMIZED missing) | 03, 21, 25, 27, 28 | No: records carry no identifier; only a worker event in a shared time window (D19) |
| Retained audit record missing (VERIFY_RECORD_PRESENT) | 18, 20, 23, 29 | No: 6645/5569 appear in no participant file; 4128/3954 only in a bundle captured after audit_at |
| Wrong account | 06, 17, 25, 29 | 06: yes (account named inside the subject's own search record); 17: yes (two lookup links, only one corroborated by a worker event in the request window); 29: follows 06; 25: no (two identical FAILED candidates) |
| System attribution | 08 | under investigation |
| Intent false NOT_APPLICABLE | 05 | yes (over-specific "copy of" pattern) |

## Release (branch claude/intelligent-sagan-ytlgrk, after EXP-C1, C2, C3; measured 2026-10-25)

| Metric | F1 baseline | Release | Target | Status |
|---|---|---|---|---|
| 518 output sha256 | 1503deba…91eb | 059df995…3246 (1 row differs: case_72) | — | — |
| Strict validator errors / warnings | 3 / 8 | 3 (R12) / 8 (R31) | 0 errors | NOT MET (disclosed, decision C2) |
| Dev status accuracy | 0.9545 | **1.0** | >= 0.95 | MET (dev) |
| Dev step P / R / F1 | 0.943 / 0.866 / 0.903 | 0.984 / 0.918 / **0.950** | F1 >= 0.94 | MET (dev) |
| Dev field accuracy | 0.8455 | 0.9062 | improve | MET |
| Dev exact sequence | 0.409 | **0.591** (13/22) | >= 0.60 | NOT MET (one case short) |
| Reserved status / F1 / exact | 0.80 / 0.830 / 0.40 | unchanged | report only | — |
| Production tests | 126 OK, 16 xfail | 136 OK incl. 12 xfail (4 known defects fixed) | no regression | MET |
| Custom scenarios | 4/5 | 5/5 (S4 expectation corrected to official samples) | — | MET |
| Model calls in final run | 0 | 0 | — | — |
| Hidden-set accuracy | unknown | unknown | — | NOT MEASURABLE |
