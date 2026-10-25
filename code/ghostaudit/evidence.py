"""Evidence parsing and the observation index.

Ported unchanged in behaviour from the accepted baseline:
  * structured files (TXT handover, JSON, SQL)  -> experiments/exp001.py parse_file
  * logs (KV, BRACKET, ESCAPED, JSON lines)     -> experiments/exp003.py parse_log
  * record-level observation time (TimedIndex) -> experiments/exp004.py
Every observation keeps its file id, the file's capture time, and (logs) the line time and line number.
"""
from __future__ import annotations

import csv
import json
import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path


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


# Fields that carry direct identifiers: a record holding any of them still identifies a person.
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
    # provenance (None when the source has no such field)
    observed_at: str | None = None   # log line timestamp
    line: int | None = None          # log line number
    record_time: str | None = None   # the record's own observed_at / recorded_at
    scope: str | None = None         # SQL table (primary / replica copy)


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


# Boolean flags stored as SQL `INTEGER NOT NULL CHECK (<field> IN (0,1))` in the inventory snapshots
# (connector_subscriptions.enabled, backup_restore_entries.restore_allowed). Only these fields accept 0/1.
SCHEMA_INT_FLAGS = {"enabled", "restore_allowed"}
# A flag field that is present but cannot be read (null, malformed, unexpected number) is an explicit unknown,
# never "blocked" or "disabled".
UNKNOWN_FLAG_STATES = {"RESTORE_UNKNOWN", "FLOW_UNKNOWN"}
RESTORE_DENIED = {"deny", "denied", "blocked", "rejected"}
RESTORE_ALLOWED = {"allow", "allowed", "approved", "granted", "permit", "permitted"}


def flag(field: str, v) -> bool | None:
    """Read one boolean flag field. True/False, or None when the value is null, malformed or unexpected."""
    if isinstance(v, bool):
        return v
    if isinstance(v, int) and field in SCHEMA_INT_FLAGS:
        return {1: True, 0: False}.get(v)        # 2, -1, ... stay unknown
    if isinstance(v, str):
        return truthy(v)                           # "true"/"false" only; "1"/"0" are not justified by any schema
    return None


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
    if "enabled" in r:
        on = flag("enabled", r["enabled"])
        return ("FLOW_UNKNOWN" if on is None else "FLOW_ACTIVE" if on else "FLOW_DISABLED"), False
    if "restore_allowed" in r:
        allowed = flag("restore_allowed", r["restore_allowed"])
        return ("RESTORE_UNKNOWN" if allowed is None else "RESTORE_OPEN" if allowed else "RESTORE_BLOCKED"), False
    if "eligible" in r:
        eligible, blocked = flag("eligible", r.get("eligible")), flag("deletion_block", r.get("deletion_block"))
        if eligible is False or blocked is True:
            return "RESTORE_BLOCKED", False
        if eligible is True and blocked is False:
            return "RESTORE_OPEN", False
        return "RESTORE_UNKNOWN", False
    if "decision" in r and str(r.get("resource_id", "")).startswith("backup_"):
        # Restore-authorization outcome (e.g. restore_authorization_completed decision="deny"): an explicit
        # decision, read only for backups; any other wording is unknown, never "blocked".
        d = norm(r["decision"])
        return ("RESTORE_BLOCKED" if d in RESTORE_DENIED else "RESTORE_OPEN" if d in RESTORE_ALLOWED
                else "RESTORE_UNKNOWN"), False
    if "direct_identifiers" in r:
        return ("PRESENT_ID" if norm(r["direct_identifiers"]) != "0" else "PRESENT_CLEAN"), False
    rid = str(r.get("resource_id", ""))
    if category == "BACKUP_ARCHIVE" or rid.startswith("backup_"):
        return "RESTORE_UNKNOWN", False   # present, but nothing says whether it can be restored
    if category == "DATA_FLOW" or rid.startswith("data_flow_"):
        return "FLOW_UNKNOWN", False      # present, but nothing says whether it runs
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


# Data category from the evidence's own labels (collection / table names), never from the system alone.
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
    if "email_opt_in" in r:                       # a marketing contact record, wherever it is stored
        return "MARKETING_PROFILE"
    is_support = str(r.get("resource_id", "")).startswith("support_")
    if is_support and cat in (None, "SUPPORT_MESSAGE") and ("file" in r or "file_name" in r):
        return "SUPPORT_ATTACHMENT"
    return cat


# ---------------------------------------------------------------- index

ISO = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
RECORD_TIME_FIELDS = ("observed_at", "recorded_at")


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
        t = next((str(rec[k]) for k in RECORD_TIME_FIELDS if k in rec and ISO.match(str(rec.get(k) or ""))), None)
        self.obs.append(Obs(fid, cap, self.system_for(rid, system), rid, st, cat, keys, explicit, record_time=t))


def parse_manifest_row(idx: Index, fid, cap, system, rid, rtype, result, subject):
    rec = {"resource_id": rid, "result": result, "subject_reference": subject}
    idx.add(fid, cap, rec, system=system, category=rtype if rtype != "DATA_FLOW" else "DATA_FLOW")


# ---------------------------------------------------------------- structured files (TXT, JSON, SQL)

def parse_structured(idx: Index, ev: dict, data_dir: Path, known_systems: set[str] | None = None) -> None:
    """TXT handover tables, JSON snapshots/exports/manifests and SQL snapshots. PNG/PDF are not read.

    known_systems (pass 2 only): system ids that structured evidence uses. A collection file whose records name no
    system takes its manifest origin as the system when the origin is one of them."""
    fid, cap = ev["file_id"], ev["captured_at"]
    path = data_dir / ev["file_path"]
    suffix = path.suffix.lower()
    if suffix in (".png", ".pdf"):
        return  # images and PDFs are read by documents.py / images.py / ocr.py (MultimodalAuditor)
    if suffix == ".txt":
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("- ") and line.count("|") >= 5:
                _, system, rid, rtype, result, subject = [x.strip() for x in line[2:].split("|")][:6]
                parse_manifest_row(idx, fid, cap, system, rid, rtype, result, subject)
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
            cat = COLLECTION_CATEGORY.get(d["collection"])
            hint = ev.get("origin") if known_systems and ev.get("origin") in known_systems else None
            for r in recs:
                idx.add(fid, cap, r, system=hint, category=cat)
            idx.scopes.append(Scope(fid, cap, {idx.system_for(recs[0]["resource_id"], hint)}))
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
        con.close()
        idx.scopes.append(Scope(fid, cap, declared or seen_systems))


# ---------------------------------------------------------------- logs (four line formats)

TS = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)\s+(.*)$")
BRACKET = re.compile(r"^\[(?P<level>[A-Z]+)\]\s+\[(?P<service>[^\]]+)\]\s+\[(?P<trace>[^\]]+)\]\s+(?P<event>[\w.-]+):\s*(?P<rest>.*)$")
KV = re.compile(r'(\w+)=("(?:[^"\\]|\\.)*"|\S+)')
DROP = ("level", "instance", "pod", "region", "severity", "logger")


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


def parse_log(idx: Index, ev: dict, text: str, known_systems: set[str], stats: dict[str, int]) -> None:
    fid, cap = ev["file_id"], ev["captured_at"]
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
            trace_keys[f["trace_id"]] |= scalars({k: v for k, v in f.items() if k != "trace_id"}, set())
    seen: set[tuple] = set()
    for n, ts, f in parsed:
        rid = f.get("resource_id")
        if not rid:
            continue
        sig = tuple(sorted((k, str(v)) for k, v in f.items() if k not in DROP))
        if sig in seen:  # exact duplicate record in the same file (known limit: audit probe P2)
            stats["duplicate"] += 1
            continue
        seen.add(sig)
        before = len(idx.obs)
        if "record_type" in f:
            parse_manifest_row(idx, fid, cap, f.get("system"), rid, f["record_type"], f.get("result", ""), f.get("subject_reference"))
        elif str(f.get("event", "")).endswith("_started"):
            continue
        else:
            cat = EVENT_CATEGORY.get(f.get("event", ""))
            hint = f.get("service")
            if fmt_of[n] != "KV" and hint not in known_systems:
                # New formats only: an emitting component that no structured evidence uses as a system is
                # not a system id; the prefix fallback decides.
                stats["emitter_not_system"] += 1
                hint = None
            idx.add(fid, cap, {k: v for k, v in f.items() if k not in DROP}, system=hint, category=cat,
                    extra_keys=trace_keys.get(f.get("trace_id", ""), ()))
        for o in idx.obs[before:]:  # provenance
            o.observed_at, o.line = ts, n


def known_systems_from_structured(evidence: list[dict], data_dir: Path) -> set[str]:
    """Pass 1: system names that structured (non-log) evidence uses as data stores/systems."""
    probe = Index({})
    for ev in evidence:
        if not ev["file_path"].endswith((".log", ".png", ".pdf")):
            parse_structured(probe, ev, data_dir)
    known = {o.system for o in probe.obs if o.system and o.system != "unknown"}
    known |= {s for sc in probe.scopes for s in sc.systems if s and s != "unknown"}
    return known


def conflicts(idx: Index) -> list[dict]:
    """Same file + same resource observed with different states (reported, not resolved)."""
    by = defaultdict(set)
    for o in idx.obs:
        by[(o.file_id, o.resource_id)].add(o.state)
    return [{"file_id": f, "resource_id": r, "states": sorted(s)} for (f, r), s in by.items() if len(s) > 1]
