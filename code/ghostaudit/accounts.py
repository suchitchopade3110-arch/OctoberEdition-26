"""Which account is the request's primary user profile.

Every request has one primary account. It is taken from evidence first:
  CONFIRMED     an account record (or a lookup keyed by the person) carries one of the person's identifiers, or a
                record of the person names the account id;
  CORROBORATED  several identifier links exist and the deletion workflow's own account event names exactly one.
Only when no evidence names an account is the workflow's account event used, and the basis is recorded:
  WORKFLOW_UNIQUE        the only worker event left in the request period once other cases' accounts are removed;
  WORKFLOW_RESULT_MATCH  several remain, exactly one with the result the workflow reported;
  WORKFLOW_AMBIGUOUS     no single event fits (deterministic pick, flagged in the run notes);
  NONE                   no candidate at all.
A worker result is a claim: it only identifies which event a report describes, never the account's state.
"""
from __future__ import annotations

import calendar
import re
import time

ACCOUNT_ID = re.compile(r"account_\d+")
# Worker result that each reported workflow status corresponds to (used only to rank candidates). Accepting SUCCESS for
# PARTIALLY_COMPLETE lowered agreement with identifier-confirmed accounts (106 -> 83 of 162), so the pairing is exact.
RESULT_FOR_STATUS = {"COMPLETE": "SUCCESS", "PARTIALLY_COMPLETE": "PARTIAL", "NOT_STARTED": "FAILED"}


def _secs(ts: str) -> int:
    return calendar.timegm(time.strptime(ts, "%Y-%m-%dT%H:%M:%SZ"))


class AccountResolver:
    """Mixin for Auditor. Expects: activity, keys, idx, and the IdentityLinker methods."""

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
        accounts no evidence names (a worker result is a claim: it only ranks candidates, never proves a state)."""
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
