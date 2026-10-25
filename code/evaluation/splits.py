"""Evaluation splits over the 32 official samples: 22 for development, 10 reserved.

These ids only choose WHICH labelled samples a metric is computed on.
Production code must never import this module or read sample_output.csv.

The reserved set is NOT a blind holdout: every sample was inspected during the
kickoff analysis. It is reserved in the sense that development changes are
never tuned against it; it is scored only at milestones, with --allow-reserved.
"""

RESERVED = [
    "case_04",  # COMPLETE, two different cited files (per-resource citation)
    "case_09",  # backup restore risk -> block restore
    "case_10",  # historical email, support record remaining
    "case_15",  # active data flow only
    "case_19",  # support message redact + search remaining
    "case_24",  # primary account still present + search
    "case_26",  # COMPLETE with six already-compliant verifications
    "case_30",  # 14-step multi-system INCOMPLETE (search, analytics, support, flow)
    "case_31",  # COMPLETE with clean tombstone
    "case_32",  # tombstone with exposed identifiers
]

DEV = [f"case_{i:02d}" for i in range(1, 33) if f"case_{i:02d}" not in RESERVED]

SPLITS = {"dev": DEV, "reserved": RESERVED, "all": DEV + RESERVED}

assert len(DEV) == 22 and len(RESERVED) == 10 and not set(DEV) & set(RESERVED)
