"""EXP-D3: typed per-resource decisions and the trace consistency gate."""
from __future__ import annotations

import sys
import unittest
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ghostaudit import evidence as ev  # noqa: E402
from ghostaudit.auditor import Auditor  # noqa: E402
from ghostaudit.decisions import UNKNOWN, CaseTrace, ResourceDecision, check_steps_backed  # noqa: E402


def world(observations):
    a = Auditor.__new__(Auditor)
    a.rules = {"USER_PROFILE": "DELETE", "SEARCH_INDEX_ENTRY": "DELETE"}
    a.by_email, a.keys = {"s@x.test": "user_1"}, defaultdict(set, {"user_1": {"s@x.test", "user_1"}})
    a.idx = ev.Index({"account": "account_service", "search": "search_service"})
    a.idx.obs = observations
    a.obs_by_res = defaultdict(list)
    for o in observations:
        a.obs_by_res[o.resource_id].append(o)
    a.links, a.activity, a.state_log = [], [], {}
    return a


Q = {"case_id": "c1", "email": "s@x.test", "audit_at": "2026-09-10T00:00:00Z", "request_text": "Please delete my account."}


class Decisions(unittest.TestCase):
    def test_trace_records_intent_attribution_state_and_unknown(self):
        o = ev.Obs("evidence_1", "2026-09-01T00:00:00Z", "search_service", "search_1", "PRESENT_ID", "SEARCH_INDEX_ENTRY",
                   {"s@x.test"})
        a = world([o])
        status, steps = a.audit(Q, ["account_9"], [])
        t = a.last_trace
        self.assertEqual((status, t.intent_rule, t.subject), ("INCOMPLETE", "DELETION", "user_1"))
        by = {d.resource_id: d for d in t.decisions}
        self.assertEqual(by["search_1"].attribution, "identifier in evidence_1")
        self.assertTrue(by["search_1"].finding)
        self.assertEqual(by["account_9"].state, UNKNOWN)          # no observation: explicit UNKNOWN ...
        self.assertFalse(by["account_9"].finding)                 # ... never a finding
        self.assertEqual(check_steps_backed(t, steps), [])

    def test_not_applicable_trace_names_the_rule(self):
        a = world([])
        status, _ = a.audit(dict(Q, request_text="Please send me a copy of my data."), None, [])
        self.assertEqual((status, a.last_trace.intent_rule), ("NOT_APPLICABLE", "NO_DELETION"))

    def test_gate_flags_step_without_decision_and_wrong_citation(self):
        t = CaseTrace("c1", "DELETION", "delete", status="COMPLETE",
                      decisions=[ResourceDecision("account_1", "account_service", "USER_PROFILE", "DELETE", "x",
                                                  "ABSENT", "e1", "ABSENT", cited_evidence="evidence_1")])
        steps = [{"step_no": 1, "resource_id": "account_1", "evidence_id": "evidence_2"},
                 {"step_no": 2, "resource_id": "search_9", "evidence_id": "evidence_1"}]
        problems = check_steps_backed(t, steps)
        self.assertEqual(len(problems), 2)


if __name__ == "__main__":
    unittest.main()
