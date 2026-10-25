# D47 regression report

All commands run on branch `d47-experiments` (Linux, Python 3.13) unless stated. Harness:
`experiments/cloud/compare.py` (518 + samples + validator + per-row diff against a frozen output).

## Per-experiment results

| Exp | Commit | 518 rows changed vs previous | Dev metrics | Validator | Tests | Decision |
|---|---|---|---|---|---|---|
| D1 local OCR second reader | `ebf8413` | 2 (case_34, case_53) | unchanged | unchanged (3 R12) | 146 OK | ACCEPT |
| D2 explicit restore decisions | `cf05ff4` | 0 | unchanged | unchanged | 150 OK | ACCEPT |
| D3 typed decisions + traces + gate | `597abd0` | 0 (byte-identical) | unchanged | unchanged | 153 OK | ACCEPT |
| D4 lineage links | `ba26f87` (+ test fix `2841b66`) | 1 (case_421) | unchanged | unchanged | 156 OK | ACCEPT |
| D5 phone digit normalisation | — | measured 0 new links | — | — | — | not built |

D4 was first committed with 4 test errors (synthetic test worlds lacked the new attribute); fixed in the next commit
with no production change. Since then every commit follows a clean suite run.

## Final suites (candidate `09bcc92`)

| Suite | Result |
|---|---|
| `python3 -m unittest discover -s code/tests -p "test_*.py"` | 156 tests OK, 12 expected failures (pinned known defects; none newly pinned) |
| `python3 code/evaluation/test_evaluator.py` | 33 OK |
| `python3 code/evaluation/custom_scenarios.py` | 5/5 |
| New tests | test_ocr.py (10: facts, cross-check, injection, cache, real engine), test_decisions.py (6: traces, UNKNOWN, gate, lineage x3), test_f1_flags.py +3 (restore decisions), test_evidence_cache.py +1 (OCR fallback never ABSENT) |

## Determinism and reproducibility

| Check | Result |
|---|---|
| OCR live re-read vs cached lines (11 images) | byte-identical |
| `--no-ocr` | differs from the release only in case_421 (lineage), as expected |
| Clean room: unzip code-d47.zip + dataset, empty environment, OCR engine import blocked | output byte-identical (`e03e7a16…`), 11/11 OCR cache hits, 0 model calls, 0 trace problems, tests 156 OK, scenarios 5/5 |
| Fact-cache index integrity (`verify_index`) | no problems |

## Strict validator (candidate)

`valid=False rows=518 steps=2955 errors=3 warnings=8` — R12 case_55 steps 1–2, case_63 step 1; R31 on 8 cases.
Identical to the accepted release.
