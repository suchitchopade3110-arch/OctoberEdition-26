"""EXP-C1 regression tests: primary-account attribution (identifier links first, workflow event second).

Synthetic worlds only (fictional ids, no dataset files). Run: python -m unittest discover -s code/tests
"""
from __future__ import annotations

import sys
import unittest
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ghostaudit import evidence as ev  # noqa: E402
from ghostaudit.auditor import Auditor  # noqa: E402


def world(observations: list[ev.Obs], activity: list[dict]) -> Auditor:
    a = Auditor.__new__(Auditor)
    a.by_email = {"subject@x.test": "user_1", "other@x.test": "user_2"}
    a.keys = defaultdict(set, {"user_1": {"subject@x.test", "user_1"}, "user_2": {"other@x.test", "user_2"}})
    a.idx = ev.Index({})
    a.idx.obs = observations
    a.links, a.activity = [], activity
    return a


def obs(rid: str, keys: set[str], cap: str = "2026-09-01T00:00:00Z") -> ev.Obs:
    return ev.Obs("evidence_x", cap, "svc", rid, "PRESENT_ID", None, keys)


def worker(aid: str, rid: str, at: str, result: str) -> dict:
    return {"activity_id": aid, "event_time": at, "event_type": "DELETE_RECORD", "source_system": "deletion_worker",
            "target_system": "account_service", "resource_id": rid, "reported_result": result, "details": ""}


REQ = {"case_id": "c1", "email": "subject@x.test", "requested_at": "2026-09-01T00:00:00Z",
       "reported_status": "NOT_STARTED", "reported_at": "2026-09-03T12:00:00Z", "audit_at": "2026-09-10T00:00:00Z"}


class AccountAttribution(unittest.TestCase):
    def test_account_named_inside_subject_record_is_an_identifier_link(self):
        # A search document carrying the subject's email names account_77: that is an identifier link, so the
        # workflow window (which also offers account_99) is not needed.
        a = world([obs("search_1", {"subject@x.test", "account_77"})],
                  [worker("act_1", "account_99", "2026-09-03T11:00:00Z", "FAILED")])
        got = a.resolve_accounts([REQ])
        self.assertEqual(got["c1"], ["account_77"])
        self.assertTrue(a.account_basis["c1"].startswith("CONFIRMED"))

    def test_record_of_another_person_does_not_link(self):
        a = world([obs("search_1", {"other@x.test", "account_77"})], [])
        self.assertEqual(a.resolve_accounts([REQ])["c1"], [])

    def test_two_linked_accounts_the_workflow_event_decides(self):
        # Both accounts were looked up with the subject's email; only account_2 has the workflow's own FAILED event.
        a = world([obs("account_1", {"subject@x.test"}), obs("account_2", {"subject@x.test"})],
                  [worker("act_2", "account_2", "2026-09-03T11:10:00Z", "FAILED")])
        got = a.resolve_accounts([REQ])
        self.assertEqual(got["c1"], ["account_2"])
        self.assertTrue(a.account_basis["c1"].startswith("CORROBORATED"))

    def test_two_linked_accounts_without_corroboration_are_both_kept(self):
        a = world([obs("account_1", {"subject@x.test"}), obs("account_2", {"subject@x.test"})], [])
        self.assertEqual(a.resolve_accounts([REQ])["c1"], ["account_1", "account_2"])

    def test_evidence_captured_after_audit_at_does_not_link(self):
        a = world([obs("account_1", {"subject@x.test"}, cap="2026-09-20T00:00:00Z")], [])
        self.assertEqual(a.resolve_accounts([REQ])["c1"], [])


if __name__ == "__main__":
    unittest.main()
