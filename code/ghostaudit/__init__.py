"""Ghost Data Still Exists — deterministic deletion-audit agent (production package).

Behaviour is the accepted baseline (EXP-001 policy/identity, EXP-003 log parser, EXP-004 temporal
state; commit aca42dc), ported into importable modules. No model calls.

Modules: evidence (parsing + index), temporal (state at audit_at), policy (rules -> steps),
intent (request authorisation), auditor (per-case audit), output (serialisation).

The output contract (operations, states, ordering) has one source of truth, code/evaluation/contract_spec.py,
shared with the validator; this package puts that folder on the import path.
"""
import sys as _sys
from pathlib import Path as _Path

_EVAL = str(_Path(__file__).resolve().parents[1] / "evaluation")
if _EVAL not in _sys.path:
    _sys.path.insert(0, _EVAL)
