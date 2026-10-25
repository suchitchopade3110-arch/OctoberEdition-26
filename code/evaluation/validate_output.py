"""Strict validator for output.csv (rule ids: contract_spec.RULES).

Errors   = break an explicit rule of the problem statement / AGENTS.md. Any error makes the file invalid.
Warnings = break a reading confirmed by the public samples but not stated as a rule. Reported, never fatal.

Usage:
    python code/evaluation/validate_output.py
    python code/evaluation/validate_output.py --output output.csv --requests dataset/deletion_requests.csv
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from contract_spec import (  # noqa: E402
    DATASET_DIR,
    FINDING_TO_REMEDIATION,
    HEADER,
    PHASE_OF,
    PHASE_RANK,
    REMEDIATION_TO_VERIFICATION,
    REPO_ROOT,
    STATE_OF,
    STATUSES,
    STEP_KEYS,
    case_sort_key,
    step_sort_key,
)


@dataclass
class Issue:
    case_id: str
    rule: str
    message: str


@dataclass
class ValidationResult:
    errors: list[Issue] = field(default_factory=list)
    warnings: list[Issue] = field(default_factory=list)
    rows_checked: int = 0
    steps_checked: int = 0

    @property
    def ok(self) -> bool:
        return not self.errors

    def error(self, case_id: str, rule: str, message: str) -> None:
        self.errors.append(Issue(case_id, rule, message))

    def warn(self, case_id: str, rule: str, message: str) -> None:
        self.warnings.append(Issue(case_id, rule, message))

    def summary(self) -> dict:
        return {
            "valid": self.ok,
            "rows_checked": self.rows_checked,
            "steps_checked": self.steps_checked,
            "errors": len(self.errors),
            "warnings": len(self.warnings),
            "errors_by_rule": dict(Counter(i.rule for i in self.errors)),
            "warnings_by_rule": dict(Counter(i.rule for i in self.warnings)),
        }


def _read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def load_evidence_index(dataset_dir: Path = DATASET_DIR) -> dict[str, str]:
    """C01: every citable id -> the time it became available (ISO-8601 UTC)."""
    index: dict[str, str] = {}
    for row in _read_csv(dataset_dir / "evidence_files.csv"):
        index[row["file_id"]] = row["captured_at"]
    for row in _read_csv(dataset_dir / "system_activity.csv"):
        index[row["activity_id"]] = row["event_time"]
    for row in _read_csv(dataset_dir / "user_audit_log.csv"):
        index[row["audit_id"]] = row["event_time"]
    return index


def load_requests(path: Path) -> dict[str, dict]:
    return {row["case_id"]: row for row in _read_csv(path)}


def _check_steps(case_id: str, status: str, steps: list, audit_at: str,
                 evidence: dict[str, str], res: ValidationResult) -> None:
    if status == "NOT_APPLICABLE":
        if steps:
            res.error(case_id, "R11", "NOT_APPLICABLE must have steps_json []")
        return
    if not steps:
        res.warn(case_id, "R11", "authorized deletion with no steps")
        # Explicit rules, not readings: COMPLETE must contain evidence-backed verification steps proving the
        # state (AGENTS.md §6.3, problem_statement "For COMPLETE, include only verification steps proving the
        # current state"); INCOMPLETE must contain findings (R13). [] is the NOT_APPLICABLE form only.
        if status == "COMPLETE":
            res.error(case_id, "R12", "COMPLETE with steps_json [] proves nothing; it needs evidence-backed verification steps")
        else:
            res.error(case_id, "R13", "INCOMPLETE with steps_json [] has no FINDING step")
        return

    valid_steps: list[dict] = []
    for pos, step in enumerate(steps, start=1):
        res.steps_checked += 1
        if not isinstance(step, dict):
            res.error(case_id, "R07", f"step {pos} is not a JSON object")
            continue
        keys = set(step)
        if keys != STEP_KEYS:
            missing, extra = STEP_KEYS - keys, keys - STEP_KEYS
            res.error(case_id, "R07", f"step {pos} keys wrong: missing={sorted(missing)} extra={sorted(extra)}")
            continue
        sn = step["step_no"]
        if not isinstance(sn, int) or isinstance(sn, bool):
            res.error(case_id, "R07", f"step {pos} step_no is not an integer: {sn!r}")
        elif sn != pos:
            res.error(case_id, "R08", f"step at position {pos} has step_no {sn}")
        for k in ("phase", "system_id", "resource_id", "operation", "state", "evidence_id"):
            if not isinstance(step[k], str):
                res.error(case_id, "R07", f"step {pos} field {k} is not a string")
        op, phase = step["operation"], step["phase"]
        if phase not in PHASE_RANK:
            res.error(case_id, "R09", f"step {pos} unknown phase {phase!r}")
            continue
        if PHASE_OF.get(op) != phase or STATE_OF.get(op) != step["state"]:
            res.error(case_id, "R10", f"step {pos} invalid (phase, operation, state)=({phase}, {op}, {step['state']})")
            continue
        if not step["system_id"] or not step["resource_id"]:
            res.error(case_id, "R07", f"step {pos} empty system_id/resource_id")

        ev = step["evidence_id"]
        needs_evidence = phase == "FINDING" or status == "COMPLETE"
        if status == "COMPLETE" and phase != "VERIFICATION":
            res.error(case_id, "R12", f"step {pos} COMPLETE case contains a {phase} step")
        if needs_evidence:
            if not ev:
                res.error(case_id, "R12" if status == "COMPLETE" else "R13", f"step {pos} needs a non-empty evidence_id")
            elif ev not in evidence:
                res.error(case_id, "C01", f"step {pos} evidence_id {ev!r} is not a file_id/activity_id/audit_id")
            elif audit_at and evidence[ev] > audit_at:
                res.error(case_id, "C03", f"step {pos} cites {ev} available {evidence[ev]} after audit_at {audit_at}")
        elif ev:
            res.error(case_id, "R13", f"step {pos} {phase} step of an INCOMPLETE case must have evidence_id \"\"")
        valid_steps.append(step)

    if len(valid_steps) != len(steps):
        return  # ordering/pairing checks need every step to be well formed

    phases = [PHASE_RANK[s["phase"]] for s in steps]
    if phases != sorted(phases):
        res.error(case_id, "R09", "phases are not in FINDING -> REMEDIATION -> VERIFICATION order")
    elif [step_sort_key(s) for s in steps] != sorted(step_sort_key(s) for s in steps):
        res.error(case_id, "R15", "steps inside a phase are not in operation/system_id/resource_id order")

    if status == "INCOMPLETE" and not any(s["phase"] == "FINDING" for s in steps):
        res.error(case_id, "R13", "INCOMPLETE case has no FINDING step")

    content = Counter(tuple(s[k] for k in ("phase", "system_id", "resource_id", "operation")) for s in steps)
    for key, n in content.items():
        if n > 1:
            res.warn(case_id, "DUP", f"step repeated {n} times: {key}")

    # V/U checks -> warnings only.
    if not any(s["system_id"] == "account_service" and s["operation"] == "VERIFY_RECORD_ABSENT" for s in steps):
        res.warn(case_id, "R31", "no account_service VERIFY_RECORD_ABSENT step")
    if status == "INCOMPLETE":
        by_res = lambda ph: {(s["system_id"], s["resource_id"]): s["operation"] for s in steps if s["phase"] == ph}
        found, remed, verif = by_res("FINDING"), by_res("REMEDIATION"), by_res("VERIFICATION")
        for r, op in found.items():
            if remed.get(r) not in FINDING_TO_REMEDIATION[op]:
                res.warn(case_id, "R30", f"finding {op} on {r} has no matching remediation")
        for r, op in remed.items():
            if r not in found:
                res.warn(case_id, "R30", f"remediation {op} on {r} has no finding")
            if verif.get(r) != REMEDIATION_TO_VERIFICATION[op]:
                res.warn(case_id, "R30", f"remediation {op} on {r} is not verified by {REMEDIATION_TO_VERIFICATION[op]}")


def validate_text(text: str, requests: dict[str, dict], evidence: dict[str, str]) -> ValidationResult:
    res = ValidationResult()
    if text.startswith("﻿"):
        res.error("-", "R02", "file starts with a UTF-8 BOM")
        text = text[1:]
    reader = csv.reader(io.StringIO(text, newline=""))
    rows = list(reader)
    if not rows or rows[0] != HEADER:
        res.error("-", "R02", f"header must be {','.join(HEADER)}; got {rows[0] if rows else 'empty file'}")
        return res

    seen: list[str] = []
    for line_no, row in enumerate(rows[1:], start=2):
        if len(row) != 3:
            res.error(f"line {line_no}", "R02", f"expected 3 columns, got {len(row)}")
            continue
        case_id, status, raw = row
        res.rows_checked += 1
        seen.append(case_id)
        if case_id not in requests:
            res.error(case_id, "R03", "case_id is not in the requests file")
        if status not in STATUSES:
            res.error(case_id, "R05", f"invalid deletion_status {status!r}")
            continue
        try:
            steps = json.loads(raw)
        except json.JSONDecodeError as exc:
            res.error(case_id, "R06", f"steps_json is not valid JSON: {exc.msg}")
            continue
        if not isinstance(steps, list):
            res.error(case_id, "R06", "steps_json is not a JSON array")
            continue
        audit_at = requests.get(case_id, {}).get("audit_at", "")
        _check_steps(case_id, status, steps, audit_at, evidence, res)

    counts = Counter(seen)
    for cid, n in counts.items():
        if n > 1:
            res.error(cid, "R03", f"case_id appears {n} times")
    for cid in requests:
        if cid not in counts:
            res.error(cid, "R03", "missing row for requested case_id")
    if seen != sorted(seen, key=case_sort_key):
        if seen == sorted(seen):
            res.warn("-", "R04", "rows are in plain-text order, not numeric case order (validated reading)")
        else:
            res.error("-", "R04", "rows are not sorted by case_id in any order")
    return res


def validate_file(output: Path, requests_path: Path, dataset_dir: Path = DATASET_DIR) -> ValidationResult:
    text = output.read_bytes().decode("utf-8")
    return validate_text(text, load_requests(requests_path), load_evidence_index(dataset_dir))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--output", type=Path, default=REPO_ROOT / "output.csv")
    ap.add_argument("--requests", type=Path, default=DATASET_DIR / "deletion_requests.csv")
    ap.add_argument("--dataset", type=Path, default=DATASET_DIR)
    ap.add_argument("--json", action="store_true", help="print the summary as JSON")
    ap.add_argument("--max-issues", type=int, default=40)
    args = ap.parse_args(argv)

    res = validate_file(args.output, args.requests, args.dataset)
    if args.json:
        print(json.dumps(res.summary(), indent=2))
    else:
        s = res.summary()
        print(f"valid={s['valid']} rows={s['rows_checked']} steps={s['steps_checked']} "
              f"errors={s['errors']} warnings={s['warnings']}")
        for label, items in (("ERROR", res.errors), ("WARN", res.warnings)):
            for issue in items[: args.max_issues]:
                print(f"  {label} [{issue.rule}] {issue.case_id}: {issue.message}")
            if len(items) > args.max_issues:
                print(f"  ... {len(items) - args.max_issues} more {label.lower()}s")
    return 0 if res.ok else 1


if __name__ == "__main__":
    sys.exit(main())
