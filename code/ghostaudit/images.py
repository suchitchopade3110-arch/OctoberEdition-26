"""Grounding of structured image facts (EXP-007G, accepted D16/D17). Pure functions; no model calls.

Image facts come from the evidence cache (see evidence_cache.py). Rules (generic, no case ids):
  * a record's resource id must match the id pattern, be known to the dataset and be printed in the record's own
    text; if the id field holds something else, the single valid id printed in the record's text is used;
  * one known person on a screenshot links as before; several people link row by row through each row's own
    identifiers; a row printing an email/phone of nobody known is unresolved (never linked by resource id);
  * a data flow's state comes only from printed status words (explicit status, or health status + mode);
  * other states are used only when stated by visible text and when they fit the resource type.
"""
from __future__ import annotations

from .documents import RID

TEXT_BASES = {"VISIBLE_TEXT", "TEXT_AND_GRAPHIC"}
STATE_FIELDS = {
    "PRESENT_WITH_IDENTIFIERS": {"direct_identifiers": "1"},
    "PRESENT_IDENTIFIERS_REMOVED": {"direct_identifiers": "0"},
    "NOT_FOUND": {"result": "not_found"},
    "FLOW_ENABLED": {"enabled": True},
    "FLOW_DISABLED": {"enabled": False},
    "RESTORE_ALLOWED": {"restore_allowed": True},
    "RESTORE_BLOCKED": {"restore_allowed": False},
}


def ground_record(r: dict, known_rids: set[str], label_to_rid: dict[str, str]) -> tuple[str | None, str]:
    """Return (resource id, how) or (None, rejection reason). Pure; unit-tested."""
    text = " ".join([r.get("visible_status_text", ""), r.get("restore_or_flow_detail", ""), *r.get("supporting_text", [])])
    rid = (r.get("resource_id") or "").strip()
    how = "printed id"
    if rid and not RID.fullmatch(rid):
        # The model put something else (e.g. a person id) in the id field. Recover only if exactly one valid
        # resource id is printed in this record's own text; otherwise reject.
        found = sorted({m.group(0) for m in RID.finditer(text)})
        if len(found) != 1:
            return None, f"resource id {rid!r} does not match the id pattern" + (
                f"; record text has {len(found)} candidate ids" if found else "")
        rid, how = found[0], f"printed id from record text (id field held {rid!r})"
    if rid:
        if rid not in known_rids:
            return None, f"resource id {rid} is unknown to the dataset (unsupported)"
        if rid not in text:
            return None, f"resource id {rid} not in the record's own supporting text"
        return rid, how
    hits = sorted({label_to_rid[l] for l in label_to_rid if l in text})
    if len(hits) == 1:
        return hits[0], "catalog label"
    return None, "no resource id" if not hits else "several catalog labels; ambiguous"


# A state must fit the kind of resource: a connector is on/off, a backup is restorable or not.
STATE_FAMILY = {"data_flow": ("FLOW_",), "backup": ("RESTORE_", "NOT_FOUND")}


def usable_state(r: dict, rid: str | None = None) -> tuple[dict | None, str | None]:
    st, basis = r.get("state"), r.get("state_basis")
    fam = STATE_FAMILY.get(rid.rsplit("_", 1)[0]) if rid else None
    if fam and st and not st.startswith(fam):
        return None, f"state {st} does not fit a {rid.rsplit('_', 1)[0]} resource; needs human review"
    if st == "UNCLEAR" or st not in STATE_FIELDS:
        return None, "state unclear"
    if basis not in TEXT_BASES:
        return None, f"{st} shown only by a graphical indicator; needs human review"
    return STATE_FIELDS[st], None


# Data-flow state comes only from words printed in the row, never from the model's label, and never from an
# identifier shown in a selector. Three word groups:
#   explicit status  - says on its own whether the flow runs (active/running/... or disabled/paused/...);
#   health status    - says the connector is healthy, not that it runs; counts only together with a mode word;
#   sync mode        - says how it would run when on (continuous/scheduled/...); never enough on its own.
# FLOW_ACTIVE needs an explicit active status, or a health status in the row's status field plus a mode word
# from the same row. Contradictory or insufficient wording -> unresolved, for human review.
import re as _re
FLOW_ACTIVE_STATUS = ("active", "running", "enabled", "syncing", "live")
FLOW_DISABLED_STATUS = ("disabled", "paused", "stopped", "inactive", "suspended", "deactivated", "off")
FLOW_HEALTH_STATUS = ("healthy", "connected")
FLOW_MODE = ("continuous", "scheduled", "realtime", "streaming", "hourly", "daily", "batch")


def _words(text: str) -> set[str]:
    return set(_re.findall(r"[a-z]+", (text or "").lower()))


def flow_state_from_text(r: dict) -> tuple[dict | None, str]:
    status = _words(r.get("visible_status_text", ""))
    row = status | _words(r.get("restore_or_flow_detail", ""))
    on = sorted(row & set(FLOW_ACTIVE_STATUS))
    off = sorted(row & set(FLOW_DISABLED_STATUS))
    health = sorted(status & set(FLOW_HEALTH_STATUS))
    mode = sorted(row & set(FLOW_MODE))
    if off and (on or health):
        return None, f"conflicting flow words {on + health} / {off}; needs human review"
    if off:
        return {"enabled": False}, f"disabled per printed status {off}"
    if on:
        return {"enabled": True}, f"active per printed status {on}"
    if health and mode:
        return {"enabled": True}, f"active per printed status {health} + mode {mode} in the same row"
    if mode:
        return None, f"only a sync mode {mode} is printed; operational status unknown; needs human review"
    return None, "no printed status for this flow; needs human review"


_PERSON_ID = _re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+|\+\d[\d ()-]{6,}\d")


def _prints_person(r: dict) -> bool:
    return any(_PERSON_ID.search(x or "") for x in r.get("subject_identifiers", []))


def link_rows(records: list[dict], users_for) -> tuple[str, list[tuple[dict, set[str], str]]]:
    """Decide, per row, which person (if any) the row belongs to. Pure; unit-tested.

    Returns (mode, [(record, user ids, reason)]). mode = "single" when the whole screenshot names at most one
    known person (old behaviour); "per_row" when several people appear. In per_row mode a row is linked only
    through identifiers printed in that row: none of its own -> unresolved; two people -> conflicting; a
    resource id claimed by rows of different people -> unresolved for all of them. Identifiers are never
    borrowed from neighbouring rows.
    """
    row_users = [users_for({s.lower() for s in r.get("subject_identifiers", [])}) for r in records]
    everyone = set().union(*row_users) if row_users else set()
    if len(everyone) <= 1:
        out = []
        for r, u in zip(records, row_users):
            if not u and _prints_person(r):
                # The row shows someone's email/phone, but no known person has it: the row is about someone we
                # cannot identify, so it must not be attached to whoever the resource id is linked to elsewhere.
                out.append((r, set(), "unresolved: row prints a person identifier that matches no known person"))
            else:
                out.append((r, u, "single-subject screenshot"))
        return "single", out
    owners: dict[str, set[str]] = {}
    for r, u in zip(records, row_users):
        rid = (r.get("resource_id") or "").strip()
        if rid and len(u) == 1:
            owners.setdefault(rid, set()).update(u)
    out = []
    for r, u in zip(records, row_users):
        rid = (r.get("resource_id") or "").strip()
        if not u:
            out.append((r, set(), "unresolved: row has no identifier of a known person"))
        elif len(u) > 1:
            out.append((r, set(), f"unresolved: row names {len(u)} different people"))
        elif rid and len(owners.get(rid, set())) > 1:
            out.append((r, set(), "unresolved: same resource id in rows of different people"))
        else:
            out.append((r, u, "row-level identifier"))
    return "per_row", out
