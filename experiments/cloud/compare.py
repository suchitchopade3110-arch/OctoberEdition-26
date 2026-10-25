"""Experiment harness: run the production agent, score dev, validate, and diff the 518 output against a baseline.

    python3 experiments/cloud/compare.py --tag exp-name [--baseline runs/baseline_f1]

Writes runs/<tag>/{output.candidate.csv,dev.csv,report.md}. Never publishes output.csv. Reserved samples are scored
only with --allow-reserved and reported separately (they are not a clean holdout).
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PY = sys.executable


def rows(path: Path) -> dict[str, tuple[str, list]]:
    with path.open(encoding="utf-8", newline="") as fh:
        return {r["case_id"]: (r["deletion_status"], json.loads(r["steps_json"])) for r in csv.DictReader(fh)}


def key(s: dict) -> tuple:
    return (s["phase"], s["system_id"], s["resource_id"], s["operation"], s["evidence_id"])


def run(cmd: list[str]) -> str:
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True).stdout


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    ap.add_argument("--baseline", type=Path, default=ROOT / "runs" / "baseline_f1")
    ap.add_argument("--allow-reserved", action="store_true")
    args = ap.parse_args()
    out = ROOT / "runs" / args.tag
    out.mkdir(parents=True, exist_ok=True)
    full = out / "full"
    dev = out / "devwork"
    run([PY, "code/main.py", "--output", str(out / "never_published.csv"), "--work-dir", str(full)])
    run([PY, "code/main.py", "--requests", "dataset/sample_deletion_requests.csv", "--output", str(out / "dev.csv"),
         "--work-dir", str(dev)])
    dev_csv = out / "dev.csv" if (out / "dev.csv").exists() else dev / "output.candidate.csv"
    report = [f"# {args.tag}\n"]
    ev = run([PY, "code/evaluation/eval.py", "--pred", str(dev_csv), "--requests", "dataset/sample_deletion_requests.csv", "--split", "dev"])
    report.append("## Dev\n" + "\n".join(ev.splitlines()[4:16]))
    if args.allow_reserved:
        rv = run([PY, "code/evaluation/eval.py", "--pred", str(dev_csv), "--requests", "dataset/sample_deletion_requests.csv",
                  "--split", "reserved", "--allow-reserved"])
        report.append("## Reserved (not a clean holdout)\n" + "\n".join(rv.splitlines()[4:16]))
    cand = full / "output.candidate.csv"
    val = run([PY, "code/evaluation/validate_output.py", "--output", str(cand), "--max-issues", "60"])
    report.append("## Validator (518)\n```\n" + val + "```")
    base, new = rows(args.baseline / "output.csv"), rows(cand)
    st_base, st_new = Counter(v[0] for v in base.values()), Counter(v[0] for v in new.values())
    report.append(f"## Status counts\nbaseline {dict(st_base)}\nnew      {dict(st_new)}\n"
                  f"steps baseline {sum(len(v[1]) for v in base.values())} new {sum(len(v[1]) for v in new.values())}")
    changed = []
    for cid in base:
        (bs, bst), (ns, nst) = base[cid], new[cid]
        if bs == ns and [key(s) for s in bst] == [key(s) for s in nst]:
            continue
        bk, nk = Counter(key(s) for s in bst), Counter(key(s) for s in nst)
        lines = [f"- {cid}: {bs} -> {ns}"]
        lines += [f"    - removed {k}" for k in (bk - nk)]
        lines += [f"    + added   {k}" for k in (nk - bk)]
        if bk == nk:
            lines.append("    (order only)")
        changed.append("\n".join(lines))
    report.append(f"## Changed cases vs baseline: {len(changed)}\n" + "\n".join(changed))
    text = "\n\n".join(report) + "\n"
    (out / "report.md").write_text(text, encoding="utf-8")
    print(text[:20000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
