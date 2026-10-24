"""Output contract constants shared by the validator and the evaluator.

Every constant points at its rule in docs/contract.md. Nothing here is a
prediction: it only describes what a valid answer looks like.
"""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DATASET_DIR = REPO_ROOT / "dataset"

HEADER = ["case_id", "deletion_status", "steps_json"]  # R02
STATUSES = {"COMPLETE", "INCOMPLETE", "NOT_APPLICABLE"}  # R05
STEP_KEYS = {"step_no", "phase", "system_id", "resource_id", "operation", "state", "evidence_id"}  # R07
PHASES = ["FINDING", "REMEDIATION", "VERIFICATION"]  # R09

# R10 + R16: allowed (phase, operation) -> state, listed in rank order per phase.
OPERATIONS: dict[str, list[tuple[str, str]]] = {
    "FINDING": [
        ("REPORT_REMAINING_RECORD", "PRESENT"),
        ("REPORT_EXPOSED_PII", "PRESENT"),
        ("REPORT_ACTIVE_DATA_FLOW", "ACTIVE"),
        ("REPORT_RESTORE_RISK", "ACTIVE"),
    ],
    "REMEDIATION": [
        ("DISABLE_DATA_FLOW", "DISABLED"),
        ("BLOCK_RESTORE", "BLOCKED"),
        ("DELETE_RECORD", "ABSENT"),
        ("REDACT_RECORD", "REDACTED"),
        ("ANONYMIZE_RECORD", "ANONYMIZED"),
    ],
    "VERIFICATION": [
        ("VERIFY_RECORD_ABSENT", "ABSENT"),
        ("VERIFY_RECORD_PRESENT", "PRESENT"),
        ("VERIFY_RECORD_REDACTED", "REDACTED"),
        ("VERIFY_RECORD_ANONYMIZED", "ANONYMIZED"),
        ("VERIFY_DATA_FLOW_DISABLED", "DISABLED"),
        ("VERIFY_RESTORE_BLOCKED", "BLOCKED"),
    ],
}

STATE_OF = {op: st for ops in OPERATIONS.values() for op, st in ops}
PHASE_OF = {op: ph for ph, ops in OPERATIONS.items() for op, _ in ops}
OP_RANK = {op: i for ops in OPERATIONS.values() for i, (op, _) in enumerate(ops)}
PHASE_RANK = {ph: i for i, ph in enumerate(PHASES)}

# Policy pairing (contract §6, R30). A finding must lead to one of these
# remediations, and a remediation must be checked by exactly this verification.
FINDING_TO_REMEDIATION = {
    "REPORT_REMAINING_RECORD": {"DELETE_RECORD"},
    "REPORT_EXPOSED_PII": {"REDACT_RECORD", "ANONYMIZE_RECORD"},
    "REPORT_ACTIVE_DATA_FLOW": {"DISABLE_DATA_FLOW"},
    "REPORT_RESTORE_RISK": {"BLOCK_RESTORE"},
}
REMEDIATION_TO_VERIFICATION = {
    "DELETE_RECORD": "VERIFY_RECORD_ABSENT",
    "REDACT_RECORD": "VERIFY_RECORD_REDACTED",
    "ANONYMIZE_RECORD": "VERIFY_RECORD_ANONYMIZED",
    "DISABLE_DATA_FLOW": "VERIFY_DATA_FLOW_DISABLED",
    "BLOCK_RESTORE": "VERIFY_RESTORE_BLOCKED",
}


def case_sort_key(case_id: str) -> tuple[int, str]:
    """R04 working reading: numeric suffix order (case_99 < case_100)."""
    prefix, _, num = case_id.rpartition("_")
    return (int(num), prefix) if num.isdigit() else (10**9, case_id)


def step_sort_key(step: dict) -> tuple:
    """R15: phase, operation rank, system_id, resource_id (R17: string order)."""
    return (
        PHASE_RANK.get(step.get("phase"), 99),
        OP_RANK.get(step.get("operation"), 99),
        str(step.get("system_id")),
        str(step.get("resource_id")),
    )
