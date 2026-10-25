"""Local evaluator: scores a predictions file against labelled answers.

These are LOCAL development metrics on the 32 public samples (or our own
scenario fixtures). They are not, and must never be reported as, the hidden
judge's score. Where the official scoring is unstated, the strictest reading
is used and named below.

Metrics:
  status_accuracy     share of cases with the exact deletion_status
  step P / R / F1     multiset match on the full step content
                      (phase, system_id, resource_id, operation, state, evidence_id);
                      step_no is excluded because it follows from order
  step_core P / R / F1  same, ignoring evidence_id (diagnostic only)
  field_accuracy      gold and predicted steps aligned by (phase, system_id, resource_id);
                      correct fields / (7 x max(gold steps, predicted steps)), so missing
                      AND extra steps both cost points (strict reading)
  positional_accuracy steps equal at the same array index / max(len gold, len pred)
  sequence_accuracy   whole case exact: same status and identical steps array
  evidence_validity   cited ids that exist and were available at audit_at
  policy_compliance   cases with no validator errors and no R30/R31 warnings

Usage:
    python code/evaluation/eval.py --pred predictions.csv --split dev
    python code/evaluation/eval.py --pred predictions.csv --split reserved --allow-reserved
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from collections import Counter
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from contract_spec import DATASET_DIR  # noqa: E402
from splits import SPLITS  # noqa: E402
from validate_output import load_evidence_index, load_requests, validate_text  # noqa: E402

FIELDS = ["step_no", "phase", "system_id", "resource_id", "operation", "state", "evidence_id"]
CONTENT = ("phase", "system_id", "resource_id", "operation", "state", "evidence_id")
CORE = ("phase", "system_id", "resource_id", "operation", "state")


def load_answers(path: Path) -> dict[str, tuple[str, list]]:
    """case_id -> (status, steps). Unparseable steps become None."""
    out: dict[str, tuple[str, list]] = {}
    with path.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            try:
                steps = json.loads(row.get("steps_json") or "")
                steps = steps if isinstance(steps, list) else None
            except json.JSONDecodeError:
                steps = None
            out[row["case_id"]] = (row.get("deletion_status", ""), steps)
    return out


def _tuples(steps: list, keys: tuple) -> Counter:
    return Counter(tuple(s.get(k) for k in keys) for s in steps if isinstance(s, dict))


def _align(gold: list[dict], pred: list[dict]) -> list[tuple[dict, dict | None]]:
    """Pair each gold step with one predicted step on (phase, system_id, resource_id),
    preferring the same operation. Unpaired gold steps get None."""
    pool = [p for p in pred if isinstance(p, dict)]
    pairs = []
    for g in gold:
        cands = [p for p in pool if all(p.get(k) == g[k] for k in ("phase", "system_id", "resource_id"))]
        best = next((p for p in cands if p.get("operation") == g["operation"]), cands[0] if cands else None)
        if best is not None:
            pool.remove(best)
        pairs.append((g, best))
    return pairs


def score_case(gold_status: str, gold: list, pred_status: str, pred: list | None) -> dict:
    pred_ok = pred if isinstance(pred, list) else []
    pred_steps = [p for p in pred_ok if isinstance(p, dict)]
    g_full, p_full = _tuples(gold, CONTENT), _tuples(pred_steps, CONTENT)
    g_core, p_core = _tuples(gold, CORE), _tuples(pred_steps, CORE)
    denom_steps = max(len(gold), len(pred_steps))
    field_correct = Counter()
    for g, p in _align(gold, pred_steps):
        if p is not None:
            for f in FIELDS:
                field_correct[f] += int(g.get(f) == p.get(f))
    positional = sum(1 for g, p in zip(gold, pred_steps) if g == p)
    return {
        "status_ok": gold_status == pred_status,
        "gold_status": gold_status,
        "pred_status": pred_status,
        "steps_parsed": pred is not None,
        "n_gold": len(gold),
        "n_pred": len(pred_steps),
        "tp": sum((g_full & p_full).values()),
        "tp_core": sum((g_core & p_core).values()),
        "denom_steps": denom_steps,
        "field_correct": dict(field_correct),
        "positional_ok": positional,
        "sequence_ok": gold_status == pred_status and gold == pred_steps,
        "missing": sorted(map(list, (g_full - p_full).elements())),
        "extra": sorted(map(list, (p_full - g_full).elements())),
    }


def _prf(tp: int, n_pred: int, n_gold: int) -> dict:
    p = tp / n_pred if n_pred else (1.0 if n_gold == 0 else 0.0)
    r = tp / n_gold if n_gold else 1.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return {"precision": round(p, 4), "recall": round(r, 4), "f1": round(f, 4)}


def evaluate(pred_path: Path, gold_path: Path, requests_path: Path, case_ids: list[str],
             dataset_dir: Path = DATASET_DIR, usage: dict | None = None) -> dict:
    gold = load_answers(gold_path)
    pred = load_answers(pred_path)
    requests = load_requests(requests_path)
    case_ids = [c for c in case_ids if c in gold]

    # Structural checks run on the predicted rows for the scored cases only.
    pred_text = pred_path.read_bytes().decode("utf-8")
    scoped_requests = {c: requests[c] for c in case_ids if c in requests}
    val = validate_text(_subset_csv(pred_text, set(case_ids)), scoped_requests, load_evidence_index(dataset_dir))
    err_cases = {i.case_id for i in val.errors}
    warn_cases = {i.case_id for i in val.warnings if i.rule in ("R30", "R31")}
    bad_evidence = sum(1 for i in val.errors if i.rule in ("C01", "C03"))
    cited = sum(1 for c in case_ids for s in (pred.get(c, ("", []))[1] or [])
                if isinstance(s, dict) and s.get("evidence_id"))

    per_case = {}
    for cid in case_ids:
        gs, gsteps = gold[cid]
        ps, psteps = pred.get(cid, ("<missing>", None))
        per_case[cid] = score_case(gs, gsteps, ps, psteps)

    n = len(case_ids)
    tot = lambda k: sum(c[k] for c in per_case.values())
    denom_fields = tot("denom_steps") * len(FIELDS)
    field_sum = Counter()
    for c in per_case.values():
        field_sum.update(c["field_correct"])
    status_conf = Counter((c["gold_status"], c["pred_status"]) for c in per_case.values())

    return {
        "scope": "LOCAL development metrics on labelled samples - not the hidden judge score",
        "cases": n,
        "status_accuracy": round(tot("status_ok") / n, 4) if n else None,
        "status_confusion": {f"{g}->{p}": v for (g, p), v in sorted(status_conf.items())},
        "step": _prf(tot("tp"), tot("n_pred"), tot("n_gold")),
        "step_core": _prf(tot("tp_core"), tot("n_pred"), tot("n_gold")),
        "field_accuracy": round(sum(field_sum.values()) / denom_fields, 4) if denom_fields else None,
        "field_accuracy_by_field": {f: round(field_sum[f] / tot("denom_steps"), 4) if tot("denom_steps") else None
                                    for f in FIELDS},
        "positional_accuracy": round(tot("positional_ok") / tot("denom_steps"), 4) if tot("denom_steps") else None,
        "sequence_accuracy": round(tot("sequence_ok") / n, 4) if n else None,
        "evidence_validity": round(1 - bad_evidence / cited, 4) if cited else None,
        "policy_compliance": round(sum(1 for c in case_ids if c not in err_cases | warn_cases) / n, 4) if n else None,
        "validator": val.summary(),
        "gold_steps": tot("n_gold"),
        "pred_steps": tot("n_pred"),
        "usage": usage or "not measured",
        "per_case": per_case,
    }


def _subset_csv(text: str, keep: set[str]) -> str:
    """Re-emit only the rows for the scored cases, keeping the original header
    (and a BOM, if present) so the validator still sees header problems."""
    bom = "﻿" if text.startswith("﻿") else ""
    rows = list(csv.reader(io.StringIO(text[len(bom):], newline="")))
    if not rows:
        return bom
    buf = io.StringIO(newline="")
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(rows[0])
    for r in rows[1:]:
        if r and r[0] in keep:
            w.writerow(r)
    return bom + buf.getvalue()


def to_markdown(res: dict, title: str) -> str:
    lines = [f"## {title}", "", f"_{res['scope']}._", "",
             "| Metric | Value |", "|---|---|",
             f"| Cases | {res['cases']} |",
             f"| Status accuracy | {res['status_accuracy']} |",
             f"| Step precision / recall / F1 | {res['step']['precision']} / {res['step']['recall']} / {res['step']['f1']} |",
             f"| Step (no evidence) P / R / F1 | {res['step_core']['precision']} / {res['step_core']['recall']} / {res['step_core']['f1']} |",
             f"| Field accuracy (strict) | {res['field_accuracy']} |",
             f"| Positional step accuracy | {res['positional_accuracy']} |",
             f"| Sequence accuracy (exact case) | {res['sequence_accuracy']} |",
             f"| Evidence validity | {res['evidence_validity']} |",
             f"| Policy compliance | {res['policy_compliance']} |",
             f"| Validator errors / warnings | {res['validator']['errors']} / {res['validator']['warnings']} |",
             "", "| Case | Gold | Pred | Steps g/p | Exact | Missing | Extra |", "|---|---|---|---|---|---|---|"]
    for cid, c in res["per_case"].items():
        lines.append(f"| {cid} | {c['gold_status']} | {c['pred_status']} | {c['n_gold']}/{c['n_pred']} | "
                     f"{'yes' if c['sequence_ok'] else 'no'} | {len(c['missing'])} | {len(c['extra'])} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pred", type=Path, required=True)
    ap.add_argument("--gold", type=Path, default=DATASET_DIR / "sample_output.csv")
    ap.add_argument("--requests", type=Path, default=DATASET_DIR / "sample_deletion_requests.csv")
    ap.add_argument("--dataset", type=Path, default=DATASET_DIR)
    ap.add_argument("--split", choices=sorted(SPLITS), default="dev")
    ap.add_argument("--cases", help="comma-separated case ids (overrides --split; for custom fixtures)")
    ap.add_argument("--allow-reserved", action="store_true", help="required to score the reserved split (it is never used for tuning)")
    ap.add_argument("--usage", type=Path, help="optional run-usage JSON (runtime, calls, tokens, cost)")
    ap.add_argument("--json-out", type=Path)
    ap.add_argument("--md-out", type=Path)
    ap.add_argument("--show-mismatches", type=int, default=10)
    args = ap.parse_args(argv)

    if args.cases:
        case_ids = [c.strip() for c in args.cases.split(",") if c.strip()]
    else:
        if args.split in ("reserved", "all") and not args.allow_reserved:
            ap.error("the reserved set is scored only at milestones: add --allow-reserved")
        case_ids = SPLITS[args.split]
    usage = json.loads(args.usage.read_text(encoding="utf-8")) if args.usage else None

    res = evaluate(args.pred, args.gold, args.requests, case_ids, args.dataset, usage)
    title = f"Local evaluation: {args.cases and 'custom cases' or args.split} ({res['cases']} cases)"
    print(to_markdown(res, title))
    shown = 0
    for cid, c in res["per_case"].items():
        if (c["missing"] or c["extra"] or not c["status_ok"]) and shown < args.show_mismatches:
            shown += 1
            print(f"- {cid}: status {c['gold_status']} -> {c['pred_status']}")
            for m in c["missing"]:
                print(f"    missing {m}")
            for e in c["extra"]:
                print(f"    extra   {e}")
    if args.json_out:
        args.json_out.write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    if args.md_out:
        args.md_out.write_text(to_markdown(res, title), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
