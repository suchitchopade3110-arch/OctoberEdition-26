# D47 code audit — what changed in code.zip and an honest quality proxy

**OFFICIAL TARGET (code > 25/30): NOT YET VERIFIED.** The proxy below is a self-assessment, not a score.

## Objective 1 investigation: should a live LLM investigate cases?

| Question | Finding |
|---|---|
| Is a model-backed investigator possible here? | No credentials for any provider exist in the cloud container, and separately billed Gemini calls were not approved. A loop that cannot run would be decorative, which the brief forbids. |
| Where does model reasoning add measurable value? | Reading screenshots: 5 of 11 had no usable facts, and the 6 Gemini facts had no independent check. Intent: no measured gap (550/550 texts classified as before; dev 22/22). Attribution: the remaining ambiguity has no evidence for a model to read. |
| What was built | A **local, runtime OCR model** (RapidOCR, ONNX; Apache-2.0): runs offline, no key, deterministic, cached. It is a second, independent reader: it confirms every Gemini fact row (all 6 entries agree) and supplies facts for screenshots without them (2 new grounded facts). |
| What was not built, and why | A Gemini/Claude case-investigation agent (no credentials, no approved budget, and the evidence gaps that remain are not ones a model could close without inventing links). |

## Changes in code-d47.zip

| Component | Change | Runtime use | Tests |
|---|---|---|---|
| `ghostaudit/ocr.py` (new) | OCR reader, line cache keyed by image sha256, cross-check, OCR→fact schema, injection quarantine | every run (cache hits; live OCR on a miss when installed) | test_ocr.py (10) |
| `ghostaudit/multimodal.py` | Gemini facts used only if OCR agrees; OCR facts for uncovered images; same grounding guards | every run | test_multimodal (adapted), test_evidence_cache (+1) |
| `ghostaudit/decisions.py` (new) | `ResourceDecision`, `CaseTrace`, `check_steps_backed` | every run: `case_traces.jsonl`; run fails (exit 2) on an unbacked step | test_decisions.py |
| `ghostaudit/auditor.py` | `audit()` split into `_candidates` / `_decide` / plan; `linked_with_reasons` (never timing); lineage links | every run | test_decisions.py, test_accounts.py |
| `ghostaudit/evidence.py` | explicit restore decisions; backup/flow without a signal = UNKNOWN | every run | test_f1_flags.py (+3) |
| `ghostaudit/evidence_cache.py` | index scans only `<sha256>/` folders | cache tools | existing |
| `main.py` | `--no-ocr`; traces file; trace gate | — | test_entrypoint (existing) |

## Quality proxy (self-assessed; wide uncertainty)

| Criterion | Release | Candidate | Basis |
|---|---|---|---|
| Agent architecture / AI involvement | 4/10 | 6/10 | a model now runs in the default path (OCR) and cross-checks the cached Gemini model; still no LLM reasoning at audit time |
| Evidence grounding and safety | 8/10 | 9/10 | two-reader agreement; UNKNOWN explicit; restore decisions explicit; trace gate |
| Modularity and typed contracts | 6/10 | 7/10 | typed decisions; audit split into stages; auditor.py still holds identity + attribution + planning |
| Observability | 5/10 | 8/10 | per-case typed traces with attribution and cited evidence |
| Tests | 8/10 | 8.5/10 | 156 + 33 tests, scenarios, clean-room |
| Reproducibility and packaging | 8/10 | 8.5/10 | byte-identical clean room without the OCR package |
| Documentation honesty | 8/10 | 8/10 | README and reports state limits and the 3 R12 errors |
| **Proxy** | **~67%** | **~78%** | |

**LOCAL QUALITY GATE (> 83.3% proxy): FAIL.** The largest remaining deduction is the absence of live LLM reasoning in
the audit path; closing it honestly needs approved credentials and a task where a model measurably helps.

## Known risks

- OCR geometry constants (row tolerance, header band) fit these consoles; other layouts may group rows differently —
  in that case facts become UNCLEAR (review), not wrong states.
- `rapidocr_onnxruntime` pulls opencv/onnxruntime (~100 MB) when installed; it is optional because the line cache is
  shipped.
- The trace gate makes a run fail on an internal inconsistency; that is intended.
