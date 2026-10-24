"""EXP-003 throwaway spike: evidence parsing completeness (T05). No AI calls.

Only log parsing changes. Every other evidence type, plus linking, state,
policy, ordering and citation, comes unchanged from the frozen baseline
spike/exp001.py (imported, never edited).

Log line formats handled (detected per line, not per file name):
  KV        TS level=.. service=.. trace_id=.. event=.. k=v k="v"          (EXP-001 format)
  BRACKET   TS [LEVEL] [service] [trace] event: k="v" ...                 (EXP-001 lost service + trace)
  ESCAPED   TS requestId=<trace> level=.. function=<service> message="k=\\"v\\" ..."
  JSON      TS {"service": .., "trace_id": .., "resource_id": .., ...}
A line that does not start with a timestamp continues the previous record (multiline).
Unparseable lines are counted as malformed and skipped. Each observation keeps
its file_id, the file's captured_at, the line timestamp and the line number.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
import tracemalloc
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import exp001 as base  # noqa: E402  (frozen baseline)

TS = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)\s+(.*)$")
BRACKET = re.compile(r"^\[(?P<level>[A-Z]+)\]\s+\[(?P<service>[^\]]+)\]\s+\[(?P<trace>[^\]]+)\]\s+(?P<event>[\w.-]+):\s*(?P<rest>.*)$")
KV = re.compile(r'(\w+)=("(?:[^"\\]|\\.)*"|\S+)')

PARSE_STATS: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
# Systems that structured (non-log) evidence names as data stores/systems. Filled before logs are parsed.
KNOWN_SYSTEMS: set[str] = set()


def _unquote(v: str) -> str:
    if len(v) >= 2 and v[0] == '"' and v[-1] == '"':
        v = v[1:-1]
    return v.replace('\\"', '"').replace("\\\\", "\\")


def kv_fields(text: str) -> dict:
    return {k: _unquote(v) for k, v in KV.findall(text)}


def records(lines: list[str]) -> list[tuple[int, str, str]]:
    """Group physical lines into records: (first line no, timestamp, body). Continuations join the previous record."""
    out: list[list] = []
    for n, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        m = TS.match(line)
        if m:
            out.append([n, m.group(1), m.group(2)])
        elif out:
            out[-1][2] += "\n" + line.strip()
        else:
            out.append([n, "", line.strip()])  # orphan continuation before any record: malformed
    return [tuple(r) for r in out]


def normalize(ts: str, body: str) -> tuple[str, dict] | None:
    """Return (format, fields) with canonical keys service/trace_id/event, or None if malformed."""
    if not ts:
        return None
    b = body.strip()
    if b.startswith("{"):
        try:
            d = json.loads(b.replace("\n", " "))
        except json.JSONDecodeError:
            return None
        if not isinstance(d, dict):
            return None
        f = {k: v for k, v in d.items() if not isinstance(v, (dict, list))}
        f.setdefault("service", d.get("logger"))
        return "JSON", {k: v for k, v in f.items() if v is not None}
    m = BRACKET.match(b)
    if m:
        f = kv_fields(m.group("rest"))
        f.update(level=m.group("level"), service=m.group("service"), trace_id=m.group("trace"), event=m.group("event"))
        return "BRACKET", f
    outer = kv_fields(b)
    if "message" in outer and ("function" in outer or "requestId" in outer):
        inner = kv_fields(outer["message"])
        f = dict(inner)
        f["service"] = outer.get("function")
        f["trace_id"] = outer.get("requestId")
        f["level"] = outer.get("level")
        return "ESCAPED", f
    if outer:
        return "KV", outer
    return None


DROP = ("level", "instance", "pod", "region", "severity", "logger")


def parse_log(idx: base.Index, ev: dict, text: str) -> None:
    fid, cap = ev["file_id"], ev["captured_at"]
    stats = PARSE_STATS[fid]
    parsed = []
    fmt_of: dict[int, str] = {}
    for n, ts, body in records(text.splitlines()):
        res = normalize(ts, body)
        if res is None:
            stats["malformed"] += 1
            continue
        fmt, f = res
        stats[fmt] += 1
        fmt_of[n] = fmt
        parsed.append((n, ts, f))
    trace_keys: dict[str, set[str]] = defaultdict(set)
    for _, _, f in parsed:
        if f.get("trace_id"):
            trace_keys[f["trace_id"]] |= base.scalars({k: v for k, v in f.items() if k != "trace_id"}, set())
    seen: set[tuple] = set()
    for n, ts, f in parsed:
        rid = f.get("resource_id")
        if not rid:
            continue
        sig = tuple(sorted((k, str(v)) for k, v in f.items() if k not in DROP))
        if sig in seen:  # exact duplicate record in the same file
            stats["duplicate"] += 1
            continue
        seen.add(sig)
        before = len(idx.obs)
        if "record_type" in f:
            base.parse_manifest_row(idx, fid, cap, f.get("system"), rid, f["record_type"], f.get("result", ""), f.get("subject_reference"))
        elif str(f.get("event", "")).endswith("_started"):
            continue
        else:
            cat = base.EVENT_CATEGORY.get(f.get("event", ""))
            hint = f.get("service")
            if fmt_of[n] != "KV" and hint not in KNOWN_SYSTEMS:
                # New formats only: an emitting component (e.g. a lookup function) that no structured
                # evidence uses as a system is not a system id; let the baseline fallback decide.
                stats["emitter_not_system"] += 1
                hint = None
            idx.add(fid, cap, {k: v for k, v in f.items() if k not in DROP}, system=hint, category=cat,
                    extra_keys=trace_keys.get(f.get("trace_id", ""), ()))
        for o in idx.obs[before:]:  # provenance
            o.observed_at, o.line = ts, n


BASE_PARSE_FILE = base.parse_file  # captured before Auditor3 swaps the module attribute


def parse_file(idx: base.Index, ev: dict) -> None:
    path = base.DATA / ev["file_path"]
    if path.suffix.lower() == ".log":
        parse_log(idx, ev, path.read_text(encoding="utf-8"))
    else:
        BASE_PARSE_FILE(idx, ev)


class Auditor3(base.Auditor):
    """EXP-001 auditor whose evidence index is built with the EXP-003 log parser."""

    def __init__(self):
        # Pass 1: learn system names from structured (non-log) evidence only.
        probe = base.Index({})
        for ev in base.read_csv(base.DATA / "evidence_files.csv"):
            if not ev["file_path"].endswith((".log", ".png", ".pdf")):
                BASE_PARSE_FILE(probe, ev)
        KNOWN_SYSTEMS.clear()
        KNOWN_SYSTEMS.update(o.system for o in probe.obs if o.system and o.system != "unknown")
        KNOWN_SYSTEMS.update(s for sc in probe.scopes for s in sc.systems if s and s != "unknown")
        original = base.parse_file
        base.parse_file = parse_file  # swap only for index construction; restored immediately
        try:
            super().__init__()
        finally:
            base.parse_file = original


def conflicts(idx: base.Index) -> list[dict]:
    """Same file + same resource observed with different states (reported, not resolved)."""
    by = defaultdict(set)
    for o in idx.obs:
        by[(o.file_id, o.resource_id)].add(o.state)
    return [{"file_id": f, "resource_id": r, "states": sorted(s)} for (f, r), s in by.items() if len(s) > 1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--requests", type=Path, default=base.DATA / "sample_deletion_requests.csv")
    ap.add_argument("--pool", type=Path, nargs="*", default=[base.DATA / "sample_deletion_requests.csv", base.DATA / "deletion_requests.csv"])
    ap.add_argument("--cases", required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--notes", type=Path)
    args = ap.parse_args()

    tracemalloc.start()
    t0 = time.perf_counter()
    aud = Auditor3()
    t_index = time.perf_counter() - t0
    pool = [q for p in args.pool for q in base.read_csv(p)]
    pool = [q for q in pool if base.authorizes_deletion(q["request_text"])]
    accounts = aud.resolve_accounts(pool)
    wanted = {c.strip() for c in args.cases.split(",")}
    reqs = sorted((q for q in base.read_csv(args.requests) if q["case_id"] in wanted), key=lambda q: base.case_sort_key(q["case_id"]))
    rows, notes = [], {}
    for q in reqs:
        n: list[str] = []
        status, steps = aud.audit(q, accounts.get(q["case_id"]), n)
        rows.append([q["case_id"], status, json.dumps(steps, ensure_ascii=False, separators=(",", ":"))])
        notes[q["case_id"]] = n
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["case_id", "deletion_status", "steps_json"])
        w.writerows(rows)
    _, peak = tracemalloc.get_traced_memory()
    meta = {"runtime_s": round(time.perf_counter() - t0, 3), "index_s": round(t_index, 3), "peak_mem_mb": round(peak / 2**20, 1),
            "observations": len(aud.idx.obs), "cases": len(rows), "model_calls": 0, "input_tokens": 0, "output_tokens": 0,
            "cost_usd": 0.0, "parse_stats": {k: dict(v) for k, v in PARSE_STATS.items()},
            "conflicts": conflicts(aud.idx), "notes": notes}
    if args.notes:
        args.notes.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps({k: meta[k] for k in ("runtime_s", "index_s", "peak_mem_mb", "observations", "cases")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
