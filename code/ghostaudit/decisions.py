"""Typed per-case reasoning records: what the auditor decided for each resource, and why.

Every output step is planned from exactly one ResourceDecision; main.py writes one CaseTrace per case to
case_traces.jsonl and checks that each emitted step is backed by a recorded decision (trace consistency gate).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

UNKNOWN = "UNKNOWN"  # no usable observation at audit_at; internal only, never an output state


@dataclass
class ResourceDecision:
    resource_id: str
    system: str
    category: str | None          # deletion_rules.csv data category
    action: str | None            # DELETE / REDACT / ANONYMIZE / RETAIN / FLOW (policy for the category)
    attribution: str              # why the resource is the subject's (identifier link, catalog link, account basis)
    state: str                    # observed state at audit_at, or UNKNOWN
    state_source: str             # observation that set the state (evidence id, time, extraction) or why unknown
    planned_state: str            # state handed to the planner (UNKNOWN is planned as a future check, never a finding)
    cited_evidence: str = ""      # evidence a COMPLETE verification would cite ("" = cannot be proven)
    state_source_file: str = ""   # evidence id of the observation that set the state (finding citation)
    finding: bool = False         # the resource violates its rule at audit_at
    notes: list[str] = field(default_factory=list)


@dataclass
class CaseTrace:
    case_id: str
    intent_rule: str
    intent_evidence: str
    subject: str | None = None
    status: str = ""
    status_reason: str = ""
    decisions: list[ResourceDecision] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    def to_json(self) -> dict:
        return asdict(self)


def check_steps_backed(trace: CaseTrace, steps: list[dict]) -> list[str]:
    """Problems if an emitted step has no decision for its resource, or a COMPLETE step cites other evidence."""
    by_rid = {d.resource_id: d for d in trace.decisions}
    problems = []
    for s in steps:
        d = by_rid.get(s["resource_id"])
        if d is None:
            problems.append(f"{trace.case_id}: step {s['step_no']} {s['resource_id']} has no recorded decision")
        elif trace.status == "COMPLETE" and s["evidence_id"] != d.cited_evidence:
            problems.append(f"{trace.case_id}: step {s['step_no']} cites {s['evidence_id']!r}, decision says "
                            f"{d.cited_evidence!r}")
    return problems
