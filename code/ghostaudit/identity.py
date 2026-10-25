"""Who is the request about, and which resources belong to that person.

A request's email is resolved to a stable user id through the current identity snapshot or the identity change
history (earlier emails, phones and email hashes all count). Resources are linked to that person only through
grounded relationships, never through timing:
  * an evidence record (available at audit_at) that carries one of the person's identifiers;
  * a data-catalog activity that names the person;
  * lineage: a sync or restore event that repopulated a copy from (or into) a resource already linked.
"""
from __future__ import annotations

import re

from . import evidence as ev

LINEAGE = re.compile(r"repopulated downstream resource (\w+_\d+)", re.I)


class IdentityLinker:
    """Mixin for Auditor. Expects: by_email, keys, idx (evidence index), links (catalog events), lineage."""

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
        # Lineage: a copy repopulated from (or into) a resource of the subject holds the subject's data. Only events at
        # or before audit_at; followed until nothing new is added. Discovery only: state still comes from evidence.
        grew = True
        while grew:
            grew = False
            for t, src, dst, aid in self.lineage:
                if t > audit_at:
                    continue
                for a_, b_ in ((src, dst), (dst, src)):
                    if a_ in res and b_ not in res:
                        res[b_] = f"lineage {aid}: {src} repopulated {dst}"
                        grew = True
        return res
