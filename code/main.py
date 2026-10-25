"""Ghost Data Still Exists — deletion-audit agent entry point.

    python code/main.py                      # audit all requests, validate, publish ./output.csv
    python code/main.py --cases case_33,...  # subset (written to the work dir only)
    python code/main.py --best-effort        # publish even if validation fails; errors are printed and recorded

Flow: read dataset/ -> audit every request -> write a candidate file in the work dir -> run the strict
validator -> only if it reports 0 errors, publish the candidate as the root output.csv. A failing run
leaves the previous output.csv untouched and exits with status 1.

Evidence: structured files, logs and SQL are parsed directly; PDFs with pypdf; images through structured facts
in the content-addressed cache code/evidence_cache/ (made earlier by Gemini, see ghostaudit/gemini.py). By default
no model is called and no network is used: an image without a cache entry adds no observation (its resources
stay UNKNOWN, never ABSENT). `--live-extraction` extracts missing images with Gemini when keys are configured.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
import tracemalloc
from pathlib import Path

CODE_DIR = Path(__file__).resolve().parent
REPO_ROOT = CODE_DIR.parent
sys.path.insert(0, str(CODE_DIR))

from ghostaudit.decisions import check_steps_backed  # noqa: E402
from ghostaudit.multimodal import MultimodalAuditor  # noqa: E402
from ghostaudit.evidence import read_csv  # noqa: E402
from ghostaudit.intent import authorizes_deletion  # noqa: E402
from ghostaudit.output import serialise_steps, write_rows  # noqa: E402
from contract_spec import case_sort_key  # noqa: E402
from validate_output import load_evidence_index, validate_text  # noqa: E402


def live_extract(data_dir: Path, cache_dir: Path) -> dict:
    """Opt-in: extract images that have no cache entry, within the attempt budget. Failures leave them unresolved."""
    from ghostaudit import evidence_cache, gemini
    cfg = gemini.load_config()
    cfg["cache_dir"] = cache_dir
    out = {"attempted": [], "failed": [], "skipped": None}
    if not (cfg["enabled"] and gemini.usable_slots(cfg)):
        out["skipped"] = "Gemini disabled or no key configured; missing images stay unresolved"
        return out
    ledger = gemini.Ledger(cfg["ledger_dir"], cfg["max_attempts"])
    for row in gemini.png_manifest():
        if evidence_cache.lookup(cache_dir, evidence_cache.sha256_file(data_dir / row["file_path"]))[0]:
            continue
        try:
            r = gemini.extract(row, cfg, ledger)
        except gemini.BudgetExceeded as e:
            out["skipped"] = str(e)
            break
        out["attempted"].append({"file_id": row["file_id"], "ok": not r.get("extraction_failed"), "usage": r.get("usage"),
                                 "attempts": [{k: a.get(k) for k in ("key_slot", "category", "latency_s")} for a in r.get("attempts", [])]})
        if r.get("extraction_failed"):
            out["failed"].append(row["file_id"])
    return out


DEFAULT_CACHE = CODE_DIR / "evidence_cache"


def run(data_dir: Path, requests_path: Path, pool_paths: list[Path], cases: set[str] | None,
        cache_dir: Path | None = DEFAULT_CACHE, use_ocr: bool = True) -> tuple[list[list], dict]:
    """cache_dir=None ignores image facts (PDF + structured evidence only)."""
    t0 = time.perf_counter()
    auditor = MultimodalAuditor(data_dir, cache_dir, use_ocr=use_ocr)
    t_index = time.perf_counter() - t0
    pool = [q for p in pool_paths for q in read_csv(p)]
    pool = [q for q in pool if authorizes_deletion(q["request_text"])]
    accounts = auditor.resolve_accounts(pool)
    reqs = sorted((q for q in read_csv(requests_path) if cases is None or q["case_id"] in cases),
                  key=lambda q: case_sort_key(q["case_id"]))
    rows, notes, state_notes, traces, trace_problems = [], {}, {}, [], []
    for q in reqs:
        n: list[str] = []
        auditor.state_log = {}
        status, steps = auditor.audit(q, accounts.get(q["case_id"]), n)
        rows.append([q["case_id"], status, serialise_steps(steps)])
        notes[q["case_id"]] = n
        state_notes[q["case_id"]] = auditor.state_log
        traces.append(auditor.last_trace.to_json())
        trace_problems += check_steps_backed(auditor.last_trace, steps)  # every step must come from a decision
    meta = {"index_s": round(t_index, 3), "observations": len(auditor.idx.obs), "cases": len(rows),
            "model_calls": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0,
            "images": auditor.image_report, "pdfs": auditor.extraction,
            "notes": notes, "state_notes": state_notes, "traces": traces, "trace_problems": trace_problems}
    return rows, meta


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset", type=Path, default=REPO_ROOT / "dataset")
    ap.add_argument("--requests", type=Path, help="default: <dataset>/deletion_requests.csv")
    ap.add_argument("--pool", type=Path, nargs="*",
                    help="request files that share the workflow activity stream (account matching); "
                         "default: <dataset>/sample_deletion_requests.csv and <dataset>/deletion_requests.csv")
    ap.add_argument("--cases", help="comma-separated case ids (subset run; never published as output.csv)")
    ap.add_argument("--output", type=Path, default=REPO_ROOT / "output.csv", help="published only after validation passes")
    ap.add_argument("--work-dir", type=Path, default=REPO_ROOT / "runs", help="candidate output and run notes")
    ap.add_argument("--evidence-cache", type=Path, default=DEFAULT_CACHE,
                    help="content-addressed image-fact cache (default: code/evidence_cache)")
    ap.add_argument("--no-evidence-cache", action="store_true", help="ignore image facts (PDF + structured evidence only)")
    ap.add_argument("--no-ocr", action="store_true",
                    help="skip the local OCR second reader (no cross-check of image facts, no OCR facts)")
    ap.add_argument("--best-effort", action="store_true",
                    help="publish output.csv even when strict validation reports errors (used for the submitted file, see README); "
                         "every error is printed, recorded in run_notes.json, and the exit status stays 1")
    ap.add_argument("--live-extraction", action="store_true",
                    help="opt-in: call Gemini for images missing from the cache (needs keys; bounded budget)")
    args = ap.parse_args(argv)

    data = args.dataset
    requests_path = args.requests or data / "deletion_requests.csv"
    pool_paths = args.pool if args.pool is not None else [data / "sample_deletion_requests.csv", data / "deletion_requests.csv"]
    cases = {c.strip() for c in args.cases.split(",")} if args.cases else None

    tracemalloc.start()
    t0 = time.perf_counter()
    cache_dir = None if args.no_evidence_cache else args.evidence_cache
    live = live_extract(data, cache_dir) if (args.live_extraction and cache_dir) else None
    rows, meta = run(data, requests_path, pool_paths, cases, cache_dir, use_ocr=not args.no_ocr)
    if live:
        ok = [a for a in live["attempted"] if a["usage"]]
        meta.update(model_calls=sum(len(a["attempts"]) for a in live["attempted"]),
                    input_tokens=sum(a["usage"].get("prompt_token_count") or 0 for a in ok),
                    output_tokens=sum(a["usage"].get("candidates_token_count") or 0 for a in ok), cost_usd=None)
    meta["live_extraction"] = live
    meta["evidence_cache"] = str(cache_dir) if cache_dir else None
    args.work_dir.mkdir(parents=True, exist_ok=True)
    candidate = args.work_dir / "output.candidate.csv"
    write_rows(candidate, rows)
    # Per-case reasoning trace: intent rule, subject, one typed decision per resource (attribution, state, cited
    # evidence), status reason. One JSON object per line.
    with (args.work_dir / "case_traces.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for t in meta.pop("traces"):
            fh.write(json.dumps(t, ensure_ascii=False, sort_keys=True) + "\n")

    all_requests = {q["case_id"]: q for q in read_csv(requests_path)}
    scoped = all_requests if cases is None else {c: all_requests[c] for c in cases if c in all_requests}
    result = validate_text(candidate.read_text(encoding="utf-8"), scoped, load_evidence_index(data))
    _, peak = tracemalloc.get_traced_memory()
    meta.update(runtime_s=round(time.perf_counter() - t0, 3), peak_mem_mb=round(peak / 2**20, 1),
                validation=result.summary(), candidate=str(candidate),
                errors=[vars(i) for i in result.errors], warnings=[vars(i) for i in result.warnings])

    # Trace consistency gate, checked BEFORE anything is published (also under --best-effort): a step that is not
    # backed by a recorded decision, or a COMPLETE step citing other evidence than its decision, is an internal error.
    trace_ok = not meta["trace_problems"]
    published = False
    if cases is None and trace_ok and (result.ok or args.best_effort):
        shutil.copyfile(candidate, args.output)  # the candidate stays in the work dir for audit
        published = True
    meta["published"] = str(args.output) if published else None
    meta["published_despite_validation_errors"] = published and not result.ok
    meta["blocked_by_trace_gate"] = not trace_ok
    (args.work_dir / "run_notes.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    s = result.summary()
    if not trace_ok:
        print("  TRACE CONSISTENCY FAILED:", *meta["trace_problems"][:10], sep="\n    ")
        print(f"  {args.output} was NOT written (trace gate); candidate kept at {candidate}")
        return 2
    print(json.dumps({k: meta[k] for k in ("cases", "runtime_s", "peak_mem_mb", "model_calls")} |
                     {"valid": s["valid"], "errors": s["errors"], "warnings": s["warnings"], "published": meta["published"]}))
    for issue in result.errors[:20]:
        print(f"  ERROR [{issue.rule}] {issue.case_id}: {issue.message}")
    if not result.ok:
        if published:
            print(f"  BEST-EFFORT: {args.output} WAS written although strict validation FAILED "
                  f"({s['errors']} errors listed above); it is not a valid output")
        else:
            print(f"  validation failed: {args.output} was NOT written; candidate kept at {candidate}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
