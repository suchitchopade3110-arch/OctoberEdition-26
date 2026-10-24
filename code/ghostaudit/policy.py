"""deletion_rules.csv -> ordered steps (contract §6; accepted EXP-001 behaviour)."""
from __future__ import annotations

from pathlib import Path

from contract_spec import STATE_OF

from .evidence import read_csv

DEFAULT_BY_PREFIX = {"account": "USER_PROFILE", "search": "SEARCH_INDEX_ENTRY", "analytics": "ANALYTICS_PROFILE",
                     "support": "SUPPORT_MESSAGE", "export": "USER_EXPORT", "data_flow": "DATA_FLOW",
                     "backup": "BACKUP_ARCHIVE", "audit_record": "SECURITY_AUDIT_LOG", "tombstone": "ACCOUNT_TOMBSTONE",
                     "cache": "CACHE_ENTRY", "marketing": "MARKETING_PROFILE", "legal": "LEGAL_HOLD_RECORD"}


def load_rules(data_dir: Path) -> dict[str, str]:
    return {r["data_category"]: r["required_action"] for r in read_csv(data_dir / "deletion_rules.csv")}


def step(phase, system, rid, op, ev=""):
    return {"step_no": 0, "phase": phase, "system_id": system, "resource_id": rid, "operation": op,
            "state": STATE_OF[op], "evidence_id": ev}


def plan_resource(cat: str, action: str, st: str, system: str, rid: str, fid: str):
    """Return (findings, remediations, verifications); verification evidence is filled in by the auditor."""
    F, R, V = [], [], []
    if cat == "DATA_FLOW":
        if st == "FLOW_ACTIVE":
            F.append(step("FINDING", system, rid, "REPORT_ACTIVE_DATA_FLOW", fid)); R.append(step("REMEDIATION", system, rid, "DISABLE_DATA_FLOW"))
        V.append(step("VERIFICATION", system, rid, "VERIFY_DATA_FLOW_DISABLED"))
    elif cat == "BACKUP_ARCHIVE":
        if st == "RESTORE_OPEN":
            F.append(step("FINDING", system, rid, "REPORT_RESTORE_RISK", fid)); R.append(step("REMEDIATION", system, rid, "BLOCK_RESTORE"))
        V.append(step("VERIFICATION", system, rid, "VERIFY_RESTORE_BLOCKED"))
    elif action == "RETAIN":
        if st != "ABSENT":
            V.append(step("VERIFICATION", system, rid, "VERIFY_RECORD_PRESENT"))
    elif action == "DELETE":
        if st != "ABSENT":
            F.append(step("FINDING", system, rid, "REPORT_REMAINING_RECORD", fid)); R.append(step("REMEDIATION", system, rid, "DELETE_RECORD"))
        V.append(step("VERIFICATION", system, rid, "VERIFY_RECORD_ABSENT"))
    elif action in ("REDACT", "ANONYMIZE"):
        if st == "ABSENT":
            return F, R, V
        if st in ("PRESENT_ID", "PRESENT"):
            F.append(step("FINDING", system, rid, "REPORT_EXPOSED_PII", fid))
            R.append(step("REMEDIATION", system, rid, "REDACT_RECORD" if action == "REDACT" else "ANONYMIZE_RECORD"))
        V.append(step("VERIFICATION", system, rid, "VERIFY_RECORD_REDACTED" if action == "REDACT" else "VERIFY_RECORD_ANONYMIZED"))
    return F, R, V
