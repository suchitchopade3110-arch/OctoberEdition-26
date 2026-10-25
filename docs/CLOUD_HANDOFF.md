# Cloud handoff — read this first after any restart or compaction

## Where things are

- Repository: `suchitchopade3110-arch/OctoberEdition-26`, working branch `claude/intelligent-sagan-ytlgrk`
  (started at `e49607c` = `main`, which contains the F1 production commit `6fe50ba` plus docs and the D36 output).
- Accepted F1 baseline: local tag `f1-baseline-cloud` -> `6fe50ba`; frozen copies in `runs/baseline_f1/`
  (gitignored). Root `output.csv` sha256 `1503deba33ea51f173e6e11f8da6e538be86c078f8df5cc55f6b38cc017b91eb`.
- The desktop-session `runs/` folder (D18/F1 frozen candidates, code.zip candidates, Gemini ledger, agent trace) was
  gitignored and is **not** in this container. The Gemini attempt ledger figures in `usage_report.md` cannot be
  re-checked here.
- Dataset: `dataset/` is the organizer's public starter data (committed upstream). No organizer-only files exist here.
- Environment: Python 3.13, pypdf 6.17. `google-genai` was pip-installed in this container only so that two
  SDK-shape tests can run; the offline audit does not need it. No model API keys are present.

## Commands

```bash
python3 code/main.py                                   # 518 cases -> runs/output.candidate.csv, publish only if valid
python3 code/main.py --requests dataset/sample_deletion_requests.csv --output runs/dev.csv --work-dir runs/devwork
python3 code/evaluation/eval.py --pred runs/dev.csv --requests dataset/sample_deletion_requests.csv --split dev
python3 -m unittest discover -s code/tests -p "test_*.py"
python3 code/evaluation/test_evaluator.py
python3 code/evaluation/custom_scenarios.py
```

## Continuity files

`docs/GOALS.md` (targets), `docs/MEASUREMENT_SCORECARD.md` (numbers), `docs/ACTIVE_EXPERIMENT.md` (what is in flight),
`docs/DECISION_REGISTER.md` (cloud-session decisions; the historical register is `docs/DECISIONS.md`, unchanged).

## Release state (2026-10-25, after the deadline override)

- Development closed after EXP-C3 (accepted) and EXP-C4 (rejected). See `docs/RELEASE_READINESS.md` for artifact
  hashes, the dashboard and the interview brief, and `docs/DECISION_REGISTER.md` for decisions C2 (R12 best effort) and
  C3 (deadline).
- Submitted-candidate output: `python code/main.py --best-effort` -> sha256 `059df995…3246`.
