"""Ghost Data Still Exists — deterministic deletion-audit agent (production package).

A deterministic audit core with two model-based readers at its edges (cached Gemini screenshot facts and a local
OCR model that cross-checks them); every decision is made by inspectable rules and recorded in a typed trace.

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
