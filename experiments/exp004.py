"""EXP-004: temporal state reconstruction (T13). Accepted baseline (D10). No AI calls.

Baseline: the accepted EXP-003 (experiments/exp003.py on experiments/exp001.py), imported unchanged.
Only state selection changes: Auditor.latest() and Auditor.absence_evidence().
Identity resolution, intent classification, parsing and policy are untouched.

Three different times are kept apart:
  observation time   when the state was observed: log line timestamp, or the record's own
                     observed_at / recorded_at; otherwise the file capture time. Never later than capture.
  availability time  the evidence file's captured_at (manifest). Evidence is usable only if <= audit_at.
  audit cutoff       the case's audit_at.

State at audit_at = the observation(s) with the latest observation time among usable evidence.
Line order in a file is never used as chronology.
Ties at the same observation time:
  * same file (one snapshot instant): if any copy shows the record (e.g. a replica), it is present;
  * different sources: the least-compliant state wins and the tie is flagged as a conflict
    (compliance cannot be proven when equally-timed evidence disagrees).
Reappearance (ABSENT then later present) is flagged; no cause is assumed.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
import tracemalloc
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))
import exp001 as base  # noqa: E402  (frozen reference)
import exp003 as accepted  # noqa: E402  (accepted baseline)

ISO = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
RECORD_TIME_FIELDS = ("observed_at", "recorded_at")

# Least compliant first: used only to break equal-time conflicts between different sources.
NON_COMPLIANCE = {"PRESENT_ID": 0, "PRESENT": 1, "FLOW_ACTIVE": 0, "RESTORE_OPEN": 0,
                  "PRESENT_CLEAN": 2, "FLOW_DISABLED": 3, "RESTORE_BLOCKED": 3, "ABSENT": 4}
PRESENT_STATES = {"PRESENT_ID", "PRESENT", "PRESENT_CLEAN"}


class TimedIndex(base.Index):
    """Same as the baseline index, but keeps a record-level observation time when the record has one."""

    def add(self, fid, cap, rec, **kw):
        before = len(self.obs)
        super().add(fid, cap, rec, **kw)
        t = next((str(rec[k]) for k in RECORD_TIME_FIELDS if k in rec and ISO.match(str(rec.get(k) or ""))), None)
        for o in self.obs[before:]:
            o.record_time = t


def obs_time(o) -> tuple[str, str]:
    """(observation time, source of that time). A time later than the file's capture is 'post-dated'."""
    t, src = getattr(o, "observed_at", None), "line"
    if not t:
        t, src = getattr(o, "record_time", None), "record"
    if not t:
        return o.captured_at, "capture"
    if t > o.captured_at:
        return t, "post-dated"
    return t, src


def choose(obs: list, audit_at: str) -> tuple[object | None, dict]:
    """Pick the observation that defines state at audit_at. Pure function (unit-tested)."""
    in_time = [o for o in obs if o.captured_at <= audit_at and obs_time(o)[0] <= audit_at]
    # A row dated after its own file was captured cannot be a reliable observation (T15): keep, flag, don't use.
    post = [o for o in obs if o.captured_at <= audit_at and obs_time(o)[1] == "post-dated"]
    usable = [o for o in in_time if obs_time(o)[1] != "post-dated"]
    info: dict = {"usable": len(usable), "excluded_after_cutoff": len([o for o in obs if o.captured_at > audit_at])}
    if post:
        info["post_dated_ignored"] = [{"file_id": o.file_id, "at": obs_time(o)[0], "state": o.state} for o in post]
    if not usable:
        return None, info
    timeline = sorted(usable, key=lambda o: (obs_time(o)[0], o.file_id, getattr(o, "line", 0) or 0))
    # Reappearance: an ABSENT observation followed later by a present one.
    seen_absent = False
    for o in timeline:
        if o.state == "ABSENT":
            seen_absent = True
        elif seen_absent and o.state in PRESENT_STATES:
            info["reappeared"] = {"file_id": o.file_id, "at": obs_time(o)[0]}
            break
    t_max = obs_time(timeline[-1])[0]
    top = [o for o in timeline if obs_time(o)[0] == t_max]
    states = {o.state for o in top}
    if len(states) == 1:
        chosen = max(top, key=lambda o: (o.file_id, getattr(o, "line", 0) or 0))
        return chosen, info
    # D10-A: an equal-time conflict is AMBIGUOUS. Keep every tied observation with its provenance.
    info["ambiguous"] = True
    info["tied_observations"] = [{"file_id": o.file_id, "line": getattr(o, "line", None), "scope": scope_of(o),
                                  "system": o.system, "state": o.state, "at": t_max} for o in top]
    files = {o.file_id for o in top}
    scopes = {scope_of(o) for o in top}
    if len(files) == 1 and len(scopes) > 1:
        # Different copies (e.g. primary vs replica) in one snapshot: states are kept per copy above,
        # not merged. Contract C08: a copy that still holds the record means the record still exists.
        present = [o for o in top if o.state != "ABSENT"]
        info["tie"] = "same snapshot, different copies: a remaining copy means the record exists (C08)"
        chosen = min(present or top, key=lambda o: (NON_COMPLIANCE.get(o.state, 9), o.file_id))
        info["preference_applied"] = True
    elif len(scopes) == 1 and len({o.system for o in top}) == 1:
        # Comparable authority and scope: conservative preference only - a decision aid, not proof (D10-A 3-4).
        info["tie"] = "comparable sources: least-compliant state preferred (not proof)"
        chosen = min(top, key=lambda o: (NON_COMPLIANCE.get(o.state, 9), o.file_id))
        info["preference_applied"] = True
    else:
        # Not comparable: no preference. Deterministic pick, still ambiguous.
        info["tie"] = "incomparable scope or authority: no preference applied"
        chosen = max(top, key=lambda o: (o.file_id, getattr(o, "line", 0) or 0))
        info["preference_applied"] = False
    info["tie_states"] = sorted(states)
    return chosen, info


def scope_of(o) -> str:
    """Copy/scope an observation describes: the SQL table (primary/replica copy) when known, else its logical system."""
    return getattr(o, "scope", None) or o.system


class Auditor4(accepted.Auditor3):
    def __init__(self):
        original = base.Index
        base.Index = TimedIndex  # index construction only; restored immediately
        try:
            super().__init__()
        finally:
            base.Index = original
        self.state_log: dict[str, dict] = {}
        self.attach_manifest_times()
        self.attach_sql_scopes()

    def attach_sql_scopes(self) -> None:
        """Record which SQL table (primary / replica copy) each SQL observation came from, so copies are
        never merged into one state (D10-A 6). Rows are matched in the baseline's own creation order."""
        import sqlite3
        self.sql_scope_files = {"matched": 0, "skipped": 0}
        by_file: dict[str, list] = {}
        for o in self.idx.obs:
            by_file.setdefault(o.file_id, []).append(o)
        for ev in base.read_csv(base.DATA / "evidence_files.csv"):
            if not ev["file_path"].endswith(".sql"):
                continue
            con = sqlite3.connect(":memory:")
            con.executescript((base.DATA / ev["file_path"]).read_text(encoding="utf-8"))
            expected = []
            for (t,) in con.execute("select name from sqlite_master where type='table'"):
                if t == "snapshot_scope":
                    continue
                cur = con.execute(f'select * from "{t}"')
                cols = [c[0] for c in cur.description]
                for row in cur.fetchall():
                    rec = dict(zip(cols, row))
                    rid = json.loads(rec["record_json"]).get("resource_id") if "record_json" in rec else rec.get("resource_id")
                    if rid:
                        expected.append((str(rid), t))
            got = by_file.get(ev["file_id"], [])
            if [o.resource_id for o in got] == [r for r, _ in expected]:
                for o, (_, t) in zip(got, expected):
                    o.scope = f"{ev['file_id']}:{t}"
                self.sql_scope_files["matched"] += 1
            else:
                self.sql_scope_files["skipped"] += 1  # never guess a copy

    def attach_manifest_times(self) -> None:
        """Manifest-style rows (record_type/result) lose their recorded_at inside the baseline parser.
        Re-read those rows in file order and attach recorded_at to the matching observations, in order."""
        queues: dict[tuple[str, str], list[str]] = {}
        for ev in base.read_csv(base.DATA / "evidence_files.csv"):
            if not ev["file_path"].endswith(".json"):
                continue
            d = json.loads((base.DATA / ev["file_path"]).read_text(encoding="utf-8"))
            rows = [r for r in d.get("records", []) if "record_type" in r]
            for sn in d.get("snapshots", []):
                if sn.get("collection") == "operational_record_history":
                    rows += sn["records"]
            for r in rows:
                if r.get("resource_id") and ISO.match(str(r.get("recorded_at") or "")):
                    queues.setdefault((ev["file_id"], r["resource_id"]), []).append(r["recorded_at"])
        self.manifest_times_attached = 0
        for o in self.idx.obs:
            q = queues.get((o.file_id, o.resource_id))
            if q and not getattr(o, "observed_at", None) and not getattr(o, "record_time", None):
                o.record_time = q.pop(0)
                self.manifest_times_attached += 1

    def latest(self, rid: str, audit_at: str):
        chosen, info = choose(self.obs_by_res.get(rid, []), audit_at)
        if info.get("tie") or info.get("reappeared") or info.get("post_dated_ignored"):
            self.state_log[rid] = info  # surfaced in run notes; ambiguity is never reported as proof
        return chosen

    def absence_evidence(self, rid: str, system: str, audit_at: str) -> tuple[str, str]:
        obs = [o for o in self.obs_by_res.get(rid, []) if o.captured_at <= audit_at and obs_time(o)[0] <= audit_at]
        explicit = [o for o in obs if o.explicit_absent]
        last_present = max((obs_time(o)[0] for o in obs if o.state != "ABSENT"), default="")
        if explicit:
            best = max(explicit, key=lambda o: (obs_time(o)[0], o.file_id))
            if obs_time(best)[0] >= last_present:
                return best.file_id, "explicit"
        writes = [a["event_time"] for a in self.activity if a["resource_id"] == rid and a["event_time"] <= audit_at]
        after = max(writes + [last_present]) if writes or last_present else ""
        present_files = {o.file_id for o in obs if o.state != "ABSENT"}
        scoped = [s for s in self.idx.scopes if system in s.systems and s.captured_at <= audit_at
                  and s.captured_at >= after and s.file_id not in present_files]
        if scoped:
            s = max(scoped, key=lambda s: (s.captured_at, s.file_id))
            return s.file_id, "scoped"
        return "", "none"


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
    aud = Auditor4()
    t_index = time.perf_counter() - t0
    pool = [q for p in args.pool for q in base.read_csv(p)]
    pool = [q for q in pool if base.authorizes_deletion(q["request_text"])]
    accounts = aud.resolve_accounts(pool)
    wanted = {c.strip() for c in args.cases.split(",")}
    reqs = sorted((q for q in base.read_csv(args.requests) if q["case_id"] in wanted), key=lambda q: base.case_sort_key(q["case_id"]))
    rows, notes, state_notes = [], {}, {}
    for q in reqs:
        n: list[str] = []
        aud.state_log = {}
        status, steps = aud.audit(q, accounts.get(q["case_id"]), n)
        rows.append([q["case_id"], status, json.dumps(steps, ensure_ascii=False, separators=(",", ":"))])
        notes[q["case_id"]] = n
        state_notes[q["case_id"]] = aud.state_log
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["case_id", "deletion_status", "steps_json"])
        w.writerows(rows)
    _, peak = tracemalloc.get_traced_memory()
    meta = {"runtime_s": round(time.perf_counter() - t0, 3), "index_s": round(t_index, 3), "peak_mem_mb": round(peak / 2**20, 1),
            "cases": len(rows), "model_calls": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0,
            "state_notes": state_notes, "notes": notes}
    if args.notes:
        args.notes.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps({k: meta[k] for k in ("runtime_s", "index_s", "peak_mem_mb", "cases")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
