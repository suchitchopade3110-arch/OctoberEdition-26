"""EXP-001 throwaway spike: deterministic-only deletion audit (no AI calls).

Reads only participant input files under dataset/. Never reads sample_output.csv.
Contains no case ids, resource ids or file ids. Rule ids refer to docs/contract.md.

Usage:
    python spike/exp001.py --requests dataset/sample_deletion_requests.csv --cases <ids> --out spike/dev_predictions.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "dataset"
sys.path.insert(0, str(ROOT / "code" / "evaluation"))
from contract_spec import STATE_OF, case_sort_key, step_sort_key  # noqa: E402  (spec constants only)

# ---------------------------------------------------------------- inputs

def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def norm(v) -> str:
    return str(v).strip().lower()


NULLS = {"", "none", "null"}


def scalars(obj, out: set[str]) -> set[str]:
    """Every scalar string value inside a record, lower-cased (identifier candidates)."""
    if isinstance(obj, dict):
        for v in obj.values():
            scalars(v, out)
    elif isinstance(obj, list):
        for v in obj:
            scalars(v, out)
    elif obj is not None and not isinstance(obj, bool):
        s = norm(obj)
        if s not in NULLS:
            out.add(s)
    return out


# Fields that carry direct identifiers (P05/P07/P15 "identifiable" test).
DIRECT_ID_FIELDS = {"email", "phone", "email_hash", "name", "full_name", "display_name", "requester_name",
                    "requester_email", "requester_phone", "owner_email", "owner_phone", "customer_email",
                    "matched_value", "correlation_key", "uploaded_by"}


@dataclass
class Obs:
    file_id: str
    captured_at: str
    system: str
    resource_id: str
    state: str            # ABSENT | PRESENT_ID | PRESENT_CLEAN | FLOW_ACTIVE | FLOW_DISABLED | RESTORE_OPEN | RESTORE_BLOCKED | PRESENT
    category: str | None  # deletion_rules category when the evidence states or implies it
    keys: set[str] = field(default_factory=set)
    explicit_absent: bool = False


@dataclass
class Scope:
    file_id: str
    captured_at: str
    systems: set[str]


# ---------------------------------------------------------------- state inference

RESULT_STATE = {"not_found": "ABSENT", "found": "PRESENT", "identifiable": "PRESENT_ID", "anonymized": "PRESENT_CLEAN",
                "redacted": "PRESENT_CLEAN", "disabled": "FLOW_DISABLED", "blocked": "RESTORE_BLOCKED"}


def truthy(v) -> bool | None:
    if isinstance(v, bool):
        return v
    s = norm(v)
    return True if s == "true" else False if s == "false" else None


def infer_state(rec: dict, category: str | None) -> tuple[str, bool]:
    """Return (state, explicit_absent) from one record's fields."""
    r = {k.lower(): v for k, v in rec.items()}
    res = norm(r.get("result", ""))
    if res in ("not_found", "miss"):
        return "ABSENT", True
    if norm(r.get("status_code", "")) == "404" or norm(r.get("http_status", "")) == "404" or norm(r.get("rows", "x")) == "0":
        return "ABSENT", True
    if res == "active":
        return ("RESTORE_OPEN" if category == "BACKUP_ARCHIVE" else "FLOW_ACTIVE"), False
    if res in RESULT_STATE and res != "found":
        return RESULT_STATE[res], False
    if "enabled" in r and truthy(r["enabled"]) is not None:
        return ("FLOW_ACTIVE" if truthy(r["enabled"]) else "FLOW_DISABLED"), False
    if "restore_allowed" in r and truthy(r["restore_allowed"]) is not None:
        return ("RESTORE_OPEN" if truthy(r["restore_allowed"]) else "RESTORE_BLOCKED"), False
    if "eligible" in r:
        open_ = truthy(r.get("eligible")) and not truthy(r.get("deletion_block"))
        return ("RESTORE_OPEN" if open_ else "RESTORE_BLOCKED"), False
    if "direct_identifiers" in r:
        return ("PRESENT_ID" if norm(r["direct_identifiers"]) != "0" else "PRESENT_CLEAN"), False
    ids = [k for k in DIRECT_ID_FIELDS if k in r and norm(r[k]) not in NULLS]
    doc = r.get("document") if isinstance(r.get("document"), dict) else None
    if doc:
        ids += [k for k in DIRECT_ID_FIELDS if norm(doc.get(k, "")) not in NULLS]
    if res == "found" or ids:
        return ("PRESENT_ID" if ids or res == "found" else "PRESENT_CLEAN"), False
    msg = r.get("message_text") or r.get("message_excerpt")
    if msg and re.search(r"[\w.+-]+@[\w-]+\.[\w.]+|\+\d[\d ]{6,}", str(msg)):
        return "PRESENT_ID", False
    return "PRESENT_CLEAN", False


# Category from the evidence's own labels (D3: content first; no AI here).
COLLECTION_CATEGORY = {
    "customer_profiles": "USER_PROFILE", "profile_lookups": "USER_PROFILE",
    "customer_search_documents": "SEARCH_INDEX_ENTRY", "index_queries": "SEARCH_INDEX_ENTRY",
    "customer_analytics_reports": "ANALYTICS_PROFILE", "customer_analytics_profiles": "ANALYTICS_PROFILE", "profiles": "ANALYTICS_PROFILE",
    "customer_export_jobs": "USER_EXPORT", "customer_exports": "USER_EXPORT", "exports": "USER_EXPORT",
    "support_conversations": "SUPPORT_MESSAGE", "tickets": "SUPPORT_MESSAGE", "support_records": "SUPPORT_MESSAGE",
    "ticket_attachments": "SUPPORT_ATTACHMENT",
    "connector_configurations": "DATA_FLOW", "connectors": "DATA_FLOW", "connector_subscriptions": "DATA_FLOW",
    "backup_catalog": "BACKUP_ARCHIVE", "restore_entries": "BACKUP_ARCHIVE", "backup_restore_entries": "BACKUP_ARCHIVE",
    "security_audit_events": "SECURITY_AUDIT_LOG", "audit_records": "SECURITY_AUDIT_LOG", "security_audit_records": "SECURITY_AUDIT_LOG",
    "deleted_customer_references": "ACCOUNT_TOMBSTONE", "retained_order_records": "LEGAL_HOLD_RECORD",
}
EVENT_CATEGORY = {"attachment_pii_scan": "SUPPORT_ATTACHMENT", "contact_lookup_completed": "MARKETING_PROFILE"}


def refine_category(cat: str | None, rec: dict) -> str | None:
    r = {k.lower(): v for k, v in rec.items()}
    if "email_opt_in" in r:                       # P18: a marketing contact record
        return "MARKETING_PROFILE"
    is_support = str(r.get("resource_id", "")).startswith("support_")
    if is_support and cat in (None, "SUPPORT_MESSAGE") and ("file" in r or "file_name" in r):
        return "SUPPORT_ATTACHMENT"
    return cat


# ---------------------------------------------------------------- evidence parsing

class Index:
    def __init__(self, prefix_system: dict[str, str]):
        self.obs: list[Obs] = []
        self.scopes: list[Scope] = []
        self.prefix_system = prefix_system

    def system_for(self, resource_id: str, hint: str | None = None) -> str:
        # Evidence context (data_store / service / system / origin_system) wins; the
        # activity-derived prefix map is only a fallback when the evidence names no system.
        p = re.sub(r"_\d+$", "", resource_id)
        return hint or self.prefix_system.get(p) or "unknown"

    def add(self, fid, cap, rec: dict, *, system=None, category=None, extra_keys=(), rid_key="resource_id"):
        rid = rec.get(rid_key)
        if not rid:
            return
        rid = str(rid)
        cat = refine_category(category, rec)
        st, explicit = infer_state(rec, cat)
        keys = scalars(rec, set()) | {norm(k) for k in extra_keys if k}
        self.obs.append(Obs(fid, cap, self.system_for(rid, system), rid, st, cat, keys, explicit))


def kv(line: str) -> dict:
    return {k: v.strip('"') for k, v in re.findall(r'(\w+)=("[^"]*"|\S+)', line)}


def parse_manifest_row(idx: Index, fid, cap, system, rid, rtype, result, subject):
    rec = {"resource_id": rid, "result": result, "subject_reference": subject}
    idx.add(fid, cap, rec, system=system, category=rtype if rtype != "DATA_FLOW" else "DATA_FLOW")


def parse_file(idx: Index, ev: dict) -> None:
    fid, cap = ev["file_id"], ev["captured_at"]
    path = DATA / ev["file_path"]
    suffix = path.suffix.lower()
    if suffix in (".png", ".pdf"):
        return  # multimodal: out of scope for EXP-001 (needs extraction, D1/D3)
    if suffix == ".txt":
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("- ") and line.count("|") >= 5:
                _, system, rid, rtype, result, subject = [x.strip() for x in line[2:].split("|")][:6]
                parse_manifest_row(idx, fid, cap, system, rid, rtype, result, subject)
        return
    if suffix == ".log":
        lines = path.read_text(encoding="utf-8").splitlines()
        trace_keys: dict[str, set[str]] = defaultdict(set)
        parsed = []
        for line in lines:
            f = kv(line)
            parsed.append(f)
            if f.get("trace_id"):
                trace_keys[f["trace_id"]] |= scalars({k: v for k, v in f.items() if k not in ("trace_id",)}, set())
        for f in parsed:
            if "resource_id" not in f:
                continue
            if "record_type" in f:   # manifest-style log line
                parse_manifest_row(idx, fid, cap, f.get("system"), f["resource_id"], f["record_type"], f.get("result", ""), f.get("subject_reference"))
                continue
            if f.get("event", "").endswith("_started"):
                continue
            cat = EVENT_CATEGORY.get(f.get("event", ""))
            idx.add(fid, cap, {k: v for k, v in f.items() if k not in ("level", "instance", "pod", "region")},
                    system=f.get("service"), category=cat, extra_keys=trace_keys.get(f.get("trace_id", ""), ()))
        return
    if suffix == ".json":
        d = json.loads(path.read_text(encoding="utf-8"))
        for sn in d.get("snapshots", []):
            store, coll = sn["data_store"], sn["collection"]
            if coll == "operational_record_history":
                for r in sn["records"]:
                    parse_manifest_row(idx, fid, cap, r.get("system"), r["resource_id"], r.get("record_type"), r.get("result", ""), r.get("lookup_value"))
                continue
            idx.scopes.append(Scope(fid, cap, {store}))
            for r in sn["records"]:
                idx.add(fid, cap, r, system=store, category=COLLECTION_CATEGORY.get(coll))
        for store, groups in d.get("service_exports", {}).items():
            idx.scopes.append(Scope(fid, cap, {store}))
            for gname, lst in groups.items():
                for r in lst:
                    if gname == "index_queries":
                        docs = (r.get("hits") or {}).get("documents") or []
                        for doc in docs:
                            idx.add(fid, cap, {"document": doc, "resource_id": doc.get("resource_id")}, system=store,
                                    category="SEARCH_INDEX_ENTRY", extra_keys=[r.get("query")])
                        if not docs and r.get("resource_id"):
                            idx.add(fid, cap, {"resource_id": r["resource_id"], "result": "miss", "query": r.get("query")}, system=store)
                    else:
                        idx.add(fid, cap, r, system=store, category=COLLECTION_CATEGORY.get(gname))
        recs = d.get("records", [])
        if recs and "record_type" in recs[0]:
            for r in recs:
                parse_manifest_row(idx, fid, cap, r.get("system"), r["resource_id"], r["record_type"], r.get("result", ""), r.get("subject_reference"))
        elif recs and d.get("collection"):
            store = d.get("source")
            cat = COLLECTION_CATEGORY.get(d["collection"])
            for r in recs:
                idx.add(fid, cap, r, system=None, category=cat)
            idx.scopes.append(Scope(fid, cap, {idx.system_for(recs[0]["resource_id"])}))
        return
    if suffix == ".sql":
        con = sqlite3.connect(":memory:")
        con.executescript(path.read_text(encoding="utf-8"))
        tables = [t for (t,) in con.execute("select name from sqlite_master where type='table'")]
        declared = {s for (s,) in con.execute("select origin_system from snapshot_scope")} if "snapshot_scope" in tables else set()
        seen_systems = set()
        for t in tables:
            if t == "snapshot_scope":
                continue
            cur = con.execute(f'select * from "{t}"')
            cols = [c[0] for c in cur.description]
            base = re.sub(r"_(primary|failover_replica|read_replica|reporting_replica|replica_\w+)$", "", t)
            for row in cur.fetchall():
                rec = dict(zip(cols, row))
                if "record_json" in rec:
                    inner = json.loads(rec["record_json"])
                    seen_systems.add(rec["origin_system"])
                    idx.add(fid, cap, inner, system=rec["origin_system"], category=COLLECTION_CATEGORY.get(rec["collection_name"]))
                else:
                    seen_systems.add(idx.system_for(str(rec["resource_id"])))
                    idx.add(fid, cap, rec, category=COLLECTION_CATEGORY.get(base))
        idx.scopes.append(Scope(fid, cap, declared or seen_systems))


# ---------------------------------------------------------------- policy (contract §6)

def load_rules() -> dict[str, str]:
    return {r["data_category"]: r["required_action"] for r in read_csv(DATA / "deletion_rules.csv")}


DEFAULT_BY_PREFIX = {"account": "USER_PROFILE", "search": "SEARCH_INDEX_ENTRY", "analytics": "ANALYTICS_PROFILE",
                     "support": "SUPPORT_MESSAGE", "export": "USER_EXPORT", "data_flow": "DATA_FLOW",
                     "backup": "BACKUP_ARCHIVE", "audit_record": "SECURITY_AUDIT_LOG", "tombstone": "ACCOUNT_TOMBSTONE",
                     "cache": "CACHE_ENTRY", "marketing": "MARKETING_PROFILE", "legal": "LEGAL_HOLD_RECORD"}


def step(phase, system, rid, op, ev=""):
    return {"step_no": 0, "phase": phase, "system_id": system, "resource_id": rid, "operation": op,
            "state": STATE_OF[op], "evidence_id": ev}


def plan_resource(cat: str, action: str, st: str, system: str, rid: str, fid: str):
    """Return (findings, remediations, verifications); verification evidence filled later."""
    F, R, V = [], [], []
    if cat == "DATA_FLOW":
        if st == "FLOW_ACTIVE":
            F.append(step("FINDING", system, rid, "REPORT_ACTIVE_DATA_FLOW", fid)); R.append(step("REMEDIATION", system, rid, "DISABLE_DATA_FLOW"))
        V.append(step("VERIFICATION", system, rid, "VERIFY_DATA_FLOW_DISABLED"))
    elif cat == "BACKUP_ARCHIVE":
        if st == "RESTORE_OPEN":
            F.append(step("FINDING", system, rid, "REPORT_RESTORE_RISK", fid)); R.append(step("REMEDIATION", system, rid, "BLOCK_RESTORE"))
        V.append(step("VERIFICATION", system, rid, "VERIFY_RESTORE_BLOCKED"))
    elif action == "RETAIN":
        if st != "ABSENT":
            V.append(step("VERIFICATION", system, rid, "VERIFY_RECORD_PRESENT"))
    elif action == "DELETE":
        if st != "ABSENT":
            F.append(step("FINDING", system, rid, "REPORT_REMAINING_RECORD", fid)); R.append(step("REMEDIATION", system, rid, "DELETE_RECORD"))
        V.append(step("VERIFICATION", system, rid, "VERIFY_RECORD_ABSENT"))
    elif action in ("REDACT", "ANONYMIZE"):
        if st == "ABSENT":
            return F, R, V
        if st in ("PRESENT_ID", "PRESENT"):
            F.append(step("FINDING", system, rid, "REPORT_EXPOSED_PII", fid))
            R.append(step("REMEDIATION", system, rid, "REDACT_RECORD" if action == "REDACT" else "ANONYMIZE_RECORD"))
        V.append(step("VERIFICATION", system, rid, "VERIFY_RECORD_REDACTED" if action == "REDACT" else "VERIFY_RECORD_ANONYMIZED"))
    return F, R, V


# ---------------------------------------------------------------- intent (Q01-Q04), keyword only

NON_DELETION = re.compile(r"not (asking|a request) (for|to) (deletion|erase|delete)|do not (close|delete)|don't delete|"
                          r"marketing lists only|stop the promotional|keep the account|leave (my|the) (profile|account)|"
                          r"copy of|download my|change the email|replace it|misspelled|resetting the login|what personal information", re.I)
DELETION = re.compile(r"delet|eras|remov|close|clos|exclus|elimin|suppress|削除|삭제|apag|borr|forget", re.I)


def authorizes_deletion(text: str) -> bool:
    if NON_DELETION.search(text):
        return False
    return bool(DELETION.search(text))


# ---------------------------------------------------------------- audit

class Auditor:
    def __init__(self):
        self.rules = load_rules()
        ids = read_csv(DATA / "user_identities.csv")
        self.audit_log = read_csv(DATA / "user_audit_log.csv")
        self.activity = read_csv(DATA / "system_activity.csv")
        self.by_email: dict[str, str] = {}
        self.keys: dict[str, set[str]] = defaultdict(set)
        for r in ids:
            self.by_email[norm(r["email"])] = r["user_id"]
            self.keys[r["user_id"]] |= {norm(r["email"]), norm(r["phone"]), norm(r["email_hash"]), norm(r["user_id"])}
        for a in self.audit_log:
            if a["field_name"] == "email":
                self.by_email.setdefault(norm(a["old_value"]), a["user_id"])
            self.keys[a["user_id"]].add(norm(a["old_value"]))
        prefix_counts: dict[str, Counter] = defaultdict(Counter)
        for a in self.activity:
            prefix_counts[re.sub(r"_\d+$", "", a["resource_id"])][a["target_system"]] += 1
        prefix_system = {p: c.most_common(1)[0][0] for p, c in prefix_counts.items()}
        self.idx = Index(prefix_system)
        for ev in read_csv(DATA / "evidence_files.csv"):
            parse_file(self.idx, ev)
        self.obs_by_res: dict[str, list[Obs]] = defaultdict(list)
        for o in self.idx.obs:
            self.obs_by_res[o.resource_id].append(o)
        self.links = [a for a in self.activity if a["event_type"] == "LINK_RESOURCE_IDENTITY"]

    # -- identity (I01-I05)
    def subject(self, email: str) -> str | None:
        return self.by_email.get(norm(email))

    def linked_resources(self, uid: str, audit_at: str) -> set[str]:
        keys = self.keys[uid]
        res = {o.resource_id for o in self.idx.obs if o.captured_at <= audit_at and o.keys & keys}
        for a in self.links:
            if a["event_time"] > audit_at:
                continue
            words = set(re.findall(r"[\w.+@-]+", norm(a["details"])))
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
                pick = None
                if len(live) == 1:
                    pick = live[0]
                if pick:
                    assigned[cid] = pick["resource_id"]; owner[pick["resource_id"]] = cid
                    del cands[cid]; changed = True
        for cid, (q, c) in sorted(cands.items(), key=lambda kv: len(kv[1][1])):
            live = [a for a in c if a["resource_id"] not in owner]
            if not live:
                assigned[cid] = None
                continue
            live.sort(key=lambda a: (a["reported_result"] != want.get(q["reported_status"]), abs(_secs(a["event_time"]) - _secs(q["reported_at"]))))
            assigned[cid] = live[0]["resource_id"]; owner[live[0]["resource_id"]] = cid
        return assigned

    # -- evidence choice (T04, C02, C06, C10)
    def latest(self, rid: str, audit_at: str) -> Obs | None:
        valid = [o for o in self.obs_by_res.get(rid, []) if o.captured_at <= audit_at]
        return max(valid, key=lambda o: (o.captured_at, o.file_id)) if valid else None

    def absence_evidence(self, rid: str, system: str, audit_at: str) -> tuple[str, str]:
        """(file_id, strength) proving absence; strength in explicit|scoped|weak|none."""
        obs = [o for o in self.obs_by_res.get(rid, []) if o.captured_at <= audit_at]
        explicit = [o for o in obs if o.explicit_absent]
        last_present = max((o.captured_at for o in obs if o.state != "ABSENT"), default="")
        if explicit and max(o.captured_at for o in explicit) >= last_present:
            o = max(explicit, key=lambda o: (o.captured_at, o.file_id))
            return o.file_id, "explicit"
        writes = [a["event_time"] for a in self.activity if a["resource_id"] == rid and a["event_time"] <= audit_at]
        after = max(writes + [last_present]) if writes or last_present else ""
        present_files = {o.file_id for o in obs if o.state != "ABSENT"}
        scoped = [s for s in self.idx.scopes if system in s.systems and s.captured_at <= audit_at
                  and s.captured_at >= after and s.file_id not in present_files]
        if scoped:
            s = max(scoped, key=lambda s: (s.captured_at, s.file_id))
            return s.file_id, "scoped"
        return "", "none"

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
                st = "ABSENT"  # only known from workflow activity (account)
            else:
                st = o.state
                if st == "PRESENT" and action in ("REDACT", "ANONYMIZE"):
                    st = "PRESENT_ID"
            if action == "DELETE" and st == "ABSENT":
                fid, strength = self.absence_evidence(rid, system, audit_at)
                if strength in ("none",):
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
        steps = sorted(F + R + V, key=step_sort_key)
        for i, s in enumerate(steps, start=1):
            s["step_no"] = i
        return status, steps


def _secs(ts: str) -> float:
    return time.mktime(time.strptime(ts, "%Y-%m-%dT%H:%M:%SZ"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--requests", type=Path, default=DATA / "sample_deletion_requests.csv")
    ap.add_argument("--pool", type=Path, nargs="*", default=[DATA / "sample_deletion_requests.csv", DATA / "deletion_requests.csv"],
                    help="all request files whose workflow events share the activity stream (account matching)")
    ap.add_argument("--cases", required=True, help="comma-separated case ids to predict")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--notes", type=Path)
    args = ap.parse_args()

    t0 = time.perf_counter()
    auditor = Auditor()
    t_index = time.perf_counter() - t0
    pool = [q for p in args.pool for q in read_csv(p)]
    pool = [q for q in pool if authorizes_deletion(q["request_text"])]
    accounts = auditor.resolve_accounts(pool)
    wanted = {c.strip() for c in args.cases.split(",")}
    reqs = sorted((q for q in read_csv(args.requests) if q["case_id"] in wanted), key=lambda q: case_sort_key(q["case_id"]))
    rows, notes = [], {}
    for q in reqs:
        n: list[str] = []
        status, steps = auditor.audit(q, accounts.get(q["case_id"]), n)
        rows.append([q["case_id"], status, json.dumps(steps, ensure_ascii=False, separators=(",", ":"))])
        notes[q["case_id"]] = n
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["case_id", "deletion_status", "steps_json"])
        w.writerows(rows)
    total = time.perf_counter() - t0
    meta = {"runtime_s": round(total, 3), "index_s": round(t_index, 3), "observations": len(auditor.idx.obs),
            "scopes": len(auditor.idx.scopes), "cases": len(rows), "model_calls": 0, "input_tokens": 0, "output_tokens": 0,
            "cost_usd": 0.0, "notes": notes}
    if args.notes:
        args.notes.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in meta.items() if k != "notes"}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
