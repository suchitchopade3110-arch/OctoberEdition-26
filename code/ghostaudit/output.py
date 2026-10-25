"""Deterministic output.csv serialisation: fixed header, compact JSON, LF line endings."""
from __future__ import annotations

import csv
import json
from pathlib import Path

HEADER = ["case_id", "deletion_status", "steps_json"]


def serialise_steps(steps: list[dict]) -> str:
    return json.dumps(steps, ensure_ascii=False, separators=(",", ":"))


def write_rows(path: Path, rows: list[list]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(HEADER)
        w.writerows(rows)
