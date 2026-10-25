"""Per-case deletion audit (accepted baseline: EXP-001 identity/policy + EXP-003 parsing + EXP-004 state).

Reads only participant files under the dataset directory. Never reads sample_output.csv.
"""
from __future__ import annotations

import calendar
import json
import re
import sqlite3
import time
from collections import Counter, defaultdict
from pathlib import Path

from contract_spec import step_sort_key

from . import evidence as ev
from .decisions import UNKNOWN, CaseTrace, ResourceDecision
from .intent import classify
from .policy import DEFAULT_BY_PREFIX, load_rules, plan_resource
from .temporal import choose, obs_time


def _secs(ts: str) -> int:
    return calendar.timegm(time.strptime(ts, "%Y-%m-%dT%H:%M:%SZ"))


ACCOUNT_ID = re.compile(r"account_\d+")
# The worker result that a workflow status usually reports. Used only to rank workflow candidates (C04: a result is a
# claim). Allowing SUCCESS for PARTIALLY_COMPLETE (seen in two hand-built samples) lowered agreement with
# identifier-confirmed accounts from 106/162 to 83/162 in the EXP-C1 label-free check, so the exact pairing is kept.
RESULT_FOR_STATUS = {"COMPLETE": "SUCCESS", "PARTIALLY_COMPLETE": "PARTIAL", "NOT_STARTED": "FAILED"}


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
                ev.parse_structured(self.idx, e, data_dir, self.known_systems)
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
        return set(self.linked_with_reasons(uid, audit_at))

    def linked_with_reasons(self, uid: str, audit_at: str) -> dict[str, str]:
        """Resource -> first reason it is linked to the subject: a subject identifier in an observation available at
        audit_at, or a catalog activity naming the subject. Never timing."""
        keys = self.keys[uid]
        res: dict[str, str] = {}
        for o in self.idx.obs:
            if o.captured_at <= audit_at and o.keys & keys:
                res.setdefault(o.resource_id, f"identifier in {o.file_id}")
        for a in self.links:
            if a["event_time"] > audit_at:
                continue
            words = set(re.findall(r"[\w.+@-]+", ev.norm(a["details"])))
            if words & keys:
                res.setdefault(a["resource_id"], f"catalog link {a['activity_id']}")
        return res

    # -- account resolution (R31): identifier links first, then the deletion workflow's own account event
    def account_links(self, uid: str, audit_at: str) -> set[str]:
        """Accounts tied to the subject by an identifier in evidence available at audit_at: the account's own record
        (or a lookup keyed by the subject) carries a subject identifier, or a record carrying a subject identifier names
        the account id (e.g. a search document's account reference)."""
        keys = self.keys[uid]
        out = set()
        for o in self.idx.obs:
            if o.captured_at > audit_at or not (o.keys & keys):
                continue
            if o.resource_id.startswith("account_"):
                out.add(o.resource_id)
            out |= {k for k in o.keys if ACCOUNT_ID.fullmatch(k)}
        return out | {r for r in self.linked_resources(uid, audit_at) if r.startswith("account_")}

    def workflow_candidates(self, q: dict) -> list[dict]:
        """Deletion-worker account events inside the request's workflow period [requested_at, end of the reporting day]
        and not after audit_at. Timing alone never decides ownership when an identifier link exists; it is used only for
        accounts no evidence names (C04: a worker result is a claim, used here only to rank candidates)."""
        hi = min(q["reported_at"][:11] + "23:59:59Z", q["audit_at"])
        return [a for a in self.account_events if q["requested_at"] <= a["event_time"] <= hi]

    def resolve_accounts(self, requests: list[dict]) -> dict[str, list[str]]:
        """case_id -> primary account(s). The basis of every decision is kept in self.account_basis:
        CONFIRMED (identifier link), CORROBORATED (identifier link that the workflow's own event also names),
        WORKFLOW_UNIQUE (no identifier link; the only workflow event left after other cases' links are removed),
        WORKFLOW_RESULT_MATCH (several remain, exactly one with the reported result),
        WORKFLOW_AMBIGUOUS (no single event fits; deterministic pick, flagged), NONE (no candidate)."""
        self.account_events = [a for a in self.activity if a["event_type"] == "DELETE_RECORD"
                               and a["target_system"] == "account_service" and a["source_system"] == "deletion_worker"]
        self.account_basis: dict[str, str] = {}
        assigned: dict[str, list[str]] = {}
        owner: dict[str, str] = {}
        cands: dict[str, tuple[dict, list[dict]]] = {}
        for q in requests:
            uid = self.subject(q["email"])
            if not uid:
                continue
            linked = sorted(self.account_links(uid, q["audit_at"]))
            flow = self.workflow_candidates(q)
            if linked:
                want = RESULT_FOR_STATUS.get(q["reported_status"])
                named = [r for r in linked if any(a["resource_id"] == r and a["reported_result"] == want for a in flow)]
                if len(linked) > 1 and len(named) == 1:
                    linked = named  # several identifier links: the workflow's own event decides (sample case_17)
                assigned[q["case_id"]] = linked
                self.account_basis[q["case_id"]] = ("CORROBORATED" if named else "CONFIRMED") + f" {linked}"
                for r in linked:
                    owner[r] = q["case_id"]
            else:
                cands[q["case_id"]] = (q, flow)
        changed = True
        while changed:
            changed = False
            for cid, (q, c) in list(cands.items()):
                live = [a for a in c if a["resource_id"] not in owner]
                if len(live) == 1:
                    r = live[0]["resource_id"]
                    assigned[cid] = [r]; owner[r] = cid
                    self.account_basis[cid] = f"WORKFLOW_UNIQUE {r} ({live[0]['activity_id']})"
                    del cands[cid]; changed = True
        for cid, (q, c) in sorted(cands.items(), key=lambda kv: len(kv[1][1])):
            live = [a for a in c if a["resource_id"] not in owner]
            if not live:
                assigned[cid] = []
                self.account_basis[cid] = "NONE: no identifier link and no free workflow event"
                continue
            want = RESULT_FOR_STATUS.get(q["reported_status"])
            live.sort(key=lambda a: (a["reported_result"] != want, abs(_secs(a["event_time"]) - _secs(q["reported_at"]))))
            r = live[0]["resource_id"]
            assigned[cid] = [r]; owner[r] = cid
            same = [a["resource_id"] for a in live if a["reported_result"] == want]
            label = "WORKFLOW_RESULT_MATCH" if len(same) == 1 else "WORKFLOW_AMBIGUOUS"
            self.account_basis[cid] = f"{label} {r} among {sorted(a['resource_id'] for a in live)}"
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

    # -- one case: intent -> subject -> candidate resources -> one decision per resource -> plan -> status
    def audit(self, q: dict, accounts: list[str] | None, notes: list[str]) -> tuple[str, list[dict]]:
        intent = classify(q["request_text"])
        trace = CaseTrace(q["case_id"], intent.rule, intent.evidence)
        self.last_trace = trace
        if not intent.authorizes:
            trace.status, trace.status_reason = "NOT_APPLICABLE", f"request does not authorise deletion ({intent.rule})"
            return "NOT_APPLICABLE", []
        uid = self.subject(q["email"])
        trace.subject = uid
        audit_at = q["audit_at"]
        if not uid:
            notes.append("no identity match")
            trace.status, trace.status_reason = "INCOMPLETE", "request email matches no current or historical identity"
            return "INCOMPLETE", []
        if hasattr(self, "account_basis") and q["case_id"] in self.account_basis:
            notes.append(f"account: {self.account_basis[q['case_id']]}")
        F, R, V = [], [], []
        for rid, attribution in sorted(self._candidates(q, uid, accounts).items()):
            d = self._decide(rid, attribution, audit_at, notes)
            if d is None:
                trace.skipped.append(f"{rid}: no data category (no rule applies)")
                continue
            trace.decisions.append(d)
            f, r, v = plan_resource(d.category, d.action, d.planned_state, d.system, rid, d.state_source_file)
            d.finding = bool(f)
            F += f; R += r; V += v
        status = "INCOMPLETE" if F else "COMPLETE"
        if status == "COMPLETE":
            cite = {(d.system, d.resource_id): d.cited_evidence for d in trace.decisions}
            for s in V:
                s["evidence_id"] = cite.get((s["system_id"], s["resource_id"]), "")
            unproven = [s["resource_id"] for s in V if not s["evidence_id"]]
            if unproven or not V:
                notes.append(f"UNPROVEN COMPLETE: no evidence proves {unproven or 'any verification'} (audit F01/C07)")
            trace.status_reason = ("no violation found; every verification cites evidence" if V and not unproven
                                   else f"no violation found, but unproven: {unproven or 'no verification'}")
        else:
            trace.status_reason = "violations: " + ", ".join(d.resource_id for d in trace.decisions if d.finding)
        trace.status = status
        steps = sorted(F + R + V, key=step_sort_key)
        for i, s in enumerate(steps, start=1):
            s["step_no"] = i
        return status, steps

    def _candidates(self, q: dict, uid: str, accounts: list[str] | None) -> dict[str, str]:
        """Resources linked to the subject at audit_at, each with the reason it is the subject's. The primary
        account comes only from resolve_accounts (a second identifier-linked account belongs to another workflow)."""
        out = {r: why for r, why in self.linked_with_reasons(uid, q["audit_at"]).items() if not r.startswith("account_")}
        basis = getattr(self, "account_basis", {}).get(q["case_id"], "passed in by caller")
        for a in accounts or []:
            out[a] = f"primary account: {basis}"
        return out

    def _decide(self, rid: str, attribution: str, audit_at: str, notes: list[str]) -> ResourceDecision | None:
        """Category, rule, state at audit_at and the evidence a verification could cite, for one resource."""
        prefix = re.sub(r"_\d+$", "", rid)
        o = self.latest(rid, audit_at)
        system = o.system if o else self.idx.system_for(rid)
        cat = (o.category if o and o.category else None) or DEFAULT_BY_PREFIX.get(prefix)
        if o and o.category is None:
            cats = [x.category for x in self.obs_by_res[rid] if x.category and x.captured_at <= audit_at]
            cat = cats[-1] if cats else cat
        if cat is None:
            notes.append(f"unknown category for {prefix}")
            return None
        action = "FLOW" if cat == "DATA_FLOW" else self.rules.get(cat)
        if o is None:
            # UNKNOWN: no usable observation at audit_at. Planned as a future check (a verification step without a
            # finding); in a COMPLETE case it can cite nothing, so it surfaces as an unproven step (R12), never as proof.
            notes.append(f"UNKNOWN state: {rid} has no usable observation at audit_at")
            d = ResourceDecision(rid, system, cat, action, attribution, UNKNOWN,
                                 "no usable observation at audit_at", planned_state="ABSENT")
        else:
            st = o.state
            if st == "PRESENT" and action in ("REDACT", "ANONYMIZE"):
                st = "PRESENT_ID"
            src = f"{o.file_id} @ {obs_time(o)[0]}" + (f" ({o.extraction})" if getattr(o, "extraction", None) else "")
            d = ResourceDecision(rid, system, cat, action, attribution, st, src, planned_state=st, cited_evidence=o.file_id)
        d.state_source_file = o.file_id if o else ""
        if action == "DELETE" and d.planned_state == "ABSENT":
            fid, strength = self.absence_evidence(rid, system, audit_at)
            if strength == "none":
                notes.append(f"absence unproven for {prefix}")
            d.cited_evidence = fid
            d.notes.append(f"absence evidence: {strength}" + (f" ({fid})" if fid else ""))
        elif d.state in ev.UNKNOWN_FLAG_STATES:
            # The record has a restore/flow flag nobody can read: it proves neither blocked nor open.
            notes.append(f"UNKNOWN flag state: {rid} {d.state} in {o.file_id}; not cited as proof")
            d.cited_evidence = ""
        elif o is None:
            d.cited_evidence = ""
        return d
