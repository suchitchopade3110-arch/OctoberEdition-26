"""Per-case deletion audit (accepted baseline: EXP-001 identity/policy + EXP-003 parsing + EXP-004 state).

Reads only participant files under the dataset directory. Never reads sample_output.csv.
"""
from __future__ import annotations

import json
import re
import sqlite3
import time
from collections import Counter, defaultdict
from pathlib import Path

from contract_spec import step_sort_key

from . import evidence as ev
from .intent import authorizes_deletion
from .policy import DEFAULT_BY_PREFIX, load_rules, plan_resource
from .temporal import choose, obs_time


def _secs(ts: str) -> float:
    return time.mktime(time.strptime(ts, "%Y-%m-%dT%H:%M:%SZ"))


class Auditor:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.rules = load_rules(data_dir)
        ids = ev.read_csv(data_dir / "user_identities.csv")
        self.audit_log = ev.read_csv(data_dir / "user_audit_log.csv")
        self.activity = ev.read_csv(data_dir / "system_activity.csv")
        self.evidence = ev.read_csv(data_dir / "evidence_files.csv")
        self.by_email: dict[str, str] = {}
        self.keys: dict[str, set[str]] = defaultdict(set)
        for r in ids:
            self.by_email[ev.norm(r["email"])] = r["user_id"]
            self.keys[r["user_id"]] |= {ev.norm(r["email"]), ev.norm(r["phone"]), ev.norm(r["email_hash"]), ev.norm(r["user_id"])}
        for a in self.audit_log:
            if a["field_name"] == "email":
                self.by_email.setdefault(ev.norm(a["old_value"]), a["user_id"])
            self.keys[a["user_id"]].add(ev.norm(a["old_value"]))
        prefix_counts: dict[str, Counter] = defaultdict(Counter)
        for a in self.activity:
            prefix_counts[re.sub(r"_\d+$", "", a["resource_id"])][a["target_system"]] += 1
        prefix_system = {p: c.most_common(1)[0][0] for p, c in prefix_counts.items()}

        self.known_systems = ev.known_systems_from_structured(self.evidence, data_dir)
        self.parse_stats: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self.idx = ev.Index(prefix_system)
        for e in self.evidence:
            path = data_dir / e["file_path"]
            if path.suffix.lower() == ".log":
                ev.parse_log(self.idx, e, path.read_text(encoding="utf-8"), self.known_systems, self.parse_stats[e["file_id"]])
            else:
                ev.parse_structured(self.idx, e, data_dir)
        self.obs_by_res: dict[str, list[ev.Obs]] = defaultdict(list)
        for o in self.idx.obs:
            self.obs_by_res[o.resource_id].append(o)
        self.links = [a for a in self.activity if a["event_type"] == "LINK_RESOURCE_IDENTITY"]
        self.state_log: dict[str, dict] = {}
        self._attach_manifest_times()
        self._attach_sql_scopes()

    # -- provenance passes (EXP-004)
    def _attach_sql_scopes(self) -> None:
        """Record which SQL table (primary / replica copy) each SQL observation came from (D10-A 6)."""
        self.sql_scope_files = {"matched": 0, "skipped": 0}
        by_file: dict[str, list] = {}
        for o in self.idx.obs:
            by_file.setdefault(o.file_id, []).append(o)
        for e in self.evidence:
            if not e["file_path"].endswith(".sql"):
                continue
            con = sqlite3.connect(":memory:")
            con.executescript((self.data_dir / e["file_path"]).read_text(encoding="utf-8"))
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
            con.close()
            got = by_file.get(e["file_id"], [])
            if [o.resource_id for o in got] == [r for r, _ in expected]:
                for o, (_, t) in zip(got, expected):
                    o.scope = f"{e['file_id']}:{t}"
                self.sql_scope_files["matched"] += 1
            else:
                self.sql_scope_files["skipped"] += 1  # never guess a copy

    def _attach_manifest_times(self) -> None:
        """Manifest rows (record_type/result) carry recorded_at; attach it to the matching observations in order."""
        queues: dict[tuple[str, str], list[str]] = {}
        for e in self.evidence:
            if not e["file_path"].endswith(".json"):
                continue
            d = json.loads((self.data_dir / e["file_path"]).read_text(encoding="utf-8"))
            rows = [r for r in d.get("records", []) if "record_type" in r]
            for sn in d.get("snapshots", []):
                if sn.get("collection") == "operational_record_history":
                    rows += sn["records"]
            for r in rows:
                if r.get("resource_id") and ev.ISO.match(str(r.get("recorded_at") or "")):
                    queues.setdefault((e["file_id"], r["resource_id"]), []).append(r["recorded_at"])
        self.manifest_times_attached = 0
        for o in self.idx.obs:
            q = queues.get((o.file_id, o.resource_id))
            if q and not o.observed_at and not o.record_time:
                o.record_time = q.pop(0)
                self.manifest_times_attached += 1

    # -- identity (I01-I05)
    def subject(self, email: str) -> str | None:
        return self.by_email.get(ev.norm(email))

    def linked_resources(self, uid: str, audit_at: str) -> set[str]:
        keys = self.keys[uid]
        res = {o.resource_id for o in self.idx.obs if o.captured_at <= audit_at and o.keys & keys}
        for a in self.links:
            if a["event_time"] > audit_at:
                continue
            words = set(re.findall(r"[\w.+@-]+", ev.norm(a["details"])))
            if words & keys:
                res.add(a["resource_id"])
        return res

    # -- account resolution (R31): evidence first, then workflow-event matching
    def resolve_accounts(self, requests: list[dict]) -> dict[str, str | None]:
        acct_events = [a for a in self.activity if a["event_type"] == "DELETE_RECORD" and a["target_system"] == "account_service"
                       and a["source_system"] == "deletion_worker"]
        want = {"COMPLETE": "SUCCESS", "PARTIALLY_COMPLETE": "PARTIAL", "NOT_STARTED": "FAILED"}
        assigned: dict[str, str | None] = {}
        owner: dict[str, str] = {}
        for q in requests:
            uid = self.subject(q["email"])
            if not uid:
                continue
            accs = sorted(r for r in self.linked_resources(uid, q["audit_at"]) if r.startswith("account_"))
            if accs:
                assigned[q["case_id"]] = accs[0]
                owner[accs[0]] = q["case_id"]
        pending = [q for q in requests if q["case_id"] not in assigned]
        cands = {}
        for q in pending:
            lo, hi = q["requested_at"], q["reported_at"][:11] + "23:59:59Z"
            c = [a for a in acct_events if lo <= a["event_time"] <= hi and a["event_time"] <= q["audit_at"]]
            cands[q["case_id"]] = (q, c)
        changed = True
        while changed:
            changed = False
            for cid, (q, c) in list(cands.items()):
                live = [a for a in c if a["resource_id"] not in owner]
                if len(live) == 1:
                    assigned[cid] = live[0]["resource_id"]; owner[live[0]["resource_id"]] = cid
                    del cands[cid]; changed = True
        for cid, (q, c) in sorted(cands.items(), key=lambda kv: len(kv[1][1])):
            live = [a for a in c if a["resource_id"] not in owner]
            if not live:
                assigned[cid] = None
                continue
            live.sort(key=lambda a: (a["reported_result"] != want.get(q["reported_status"]), abs(_secs(a["event_time"]) - _secs(q["reported_at"]))))
            assigned[cid] = live[0]["resource_id"]; owner[live[0]["resource_id"]] = cid
        return assigned

    # -- evidence choice (T04, C02, C06, C10; D10)
    def latest(self, rid: str, audit_at: str):
        chosen, info = choose(self.obs_by_res.get(rid, []), audit_at)
        if info.get("tie") or info.get("reappeared") or info.get("post_dated_ignored"):
            self.state_log[rid] = info
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

    # -- one case
    def audit(self, q: dict, account: str | None, notes: list[str]) -> tuple[str, list[dict]]:
        if not authorizes_deletion(q["request_text"]):
            return "NOT_APPLICABLE", []
        uid = self.subject(q["email"])
        audit_at = q["audit_at"]
        if not uid:
            notes.append("no identity match")
            return "INCOMPLETE", []
        rids = self.linked_resources(uid, audit_at)
        if account:
            rids.add(account)
        F, R, V = [], [], []
        evidence_for: dict[tuple, str] = {}
        for rid in sorted(rids):
            prefix = re.sub(r"_\d+$", "", rid)
            o = self.latest(rid, audit_at)
            system = o.system if o else self.idx.system_for(rid)
            cat = (o.category if o and o.category else None) or DEFAULT_BY_PREFIX.get(prefix)
            if o and o.category is None:
                cats = [x.category for x in self.obs_by_res[rid] if x.category and x.captured_at <= audit_at]
                cat = cats[-1] if cats else cat
            if cat is None:
                notes.append(f"unknown category for {prefix}")
                continue
            action = "FLOW" if cat == "DATA_FLOW" else self.rules.get(cat)
            if o is None:
                # Internal evidence state UNKNOWN (no usable observation at audit_at). It is never an output label.
                # The accepted baseline still plans the resource as ABSENT (audit finding F02); how such cases
                # should be output is an open decision (EXP-006B / D12), so behaviour is unchanged here.
                notes.append(f"UNKNOWN state: {rid} has no usable observation at audit_at")
                st = "ABSENT"
            else:
                st = o.state
                if st == "PRESENT" and action in ("REDACT", "ANONYMIZE"):
                    st = "PRESENT_ID"
            if action == "DELETE" and st == "ABSENT":
                fid, strength = self.absence_evidence(rid, system, audit_at)
                if strength == "none":
                    notes.append(f"absence unproven for {prefix}")
                evidence_for[(system, rid)] = fid
            else:
                evidence_for[(system, rid)] = o.file_id if o else ""
            f, r, v = plan_resource(cat, action, st, system, rid, o.file_id if o else "")
            F += f; R += r; V += v
        status = "INCOMPLETE" if F else "COMPLETE"
        if status == "COMPLETE":
            for s in V:
                s["evidence_id"] = evidence_for.get((s["system_id"], s["resource_id"]), "")
            unproven = [s["resource_id"] for s in V if not s["evidence_id"]]
            if unproven or not V:
                notes.append(f"UNPROVEN COMPLETE: no evidence proves {unproven or 'any verification'} (audit F01/C07)")
        steps = sorted(F + R + V, key=step_sort_key)
        for i, s in enumerate(steps, start=1):
            s["step_no"] = i
        return status, steps
