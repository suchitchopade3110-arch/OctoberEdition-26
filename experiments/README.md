# Accepted deterministic baseline (experiments)

Research code for the Ghost Data Still Exists audit. Not the submission entry point (that will live in `code/`).
No AI calls. Reads only participant files under `dataset/`; never reads `dataset/sample_output.csv`.

| File | Role | Status |
|---|---|---|
| `exp001.py` | EXP-001 reference baseline: evidence index, identity keys, account matching, `audit_at` cutoff, policy table, step ordering, citation | Frozen reference (byte-identical to the run reported in `docs/EXPERIMENTS.md`, sha256 prefix `20ac6058552b615e`) |
| `exp003.py` | EXP-003 log parser on top of EXP-001: four log formats (kv, bracket, escaped message, JSON lines), multiline, malformed/duplicate handling, line provenance | **Accepted baseline** (D9) |
| `test_exp003.py` | 17 synthetic parser tests | — |
| `exp004.py` | EXP-004 temporal state reconstruction on top of EXP-003: observation vs availability vs cutoff times, record/line times, ambiguous-tie handling, per-copy SQL scope, post-dated quarantine | **Accepted baseline** (D10) |
| `test_exp004.py` | 17 synthetic temporal tests | — |

Each version imports the previous one unchanged, so `exp001.py` and `exp003.py` remain runnable on their own for reproduction.

EXP-002 (identity linking) was rejected (D8) and is **not** included here.

## Reproduce

From the repository root:

```bash
python -m unittest discover -s experiments -p "test_*.py"
python experiments/exp004.py --cases <comma-separated dev case ids> --out runs/dev_pred.csv --notes runs/dev_run.json
python code/evaluation/eval.py --pred runs/dev_pred.csv --split dev
```

Dev case ids are listed in `code/evaluation/splits.py` (`DEV`). The reserved split needs `--allow-reserved` and is scored only at milestones.

Measured results (local, dev split, not the hidden judge's score) are in `docs/EXPERIMENTS.md`; traps in `docs/TRAP_FINDINGS.md`.
