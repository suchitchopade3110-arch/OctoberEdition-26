"""Synthetic tests for EXP-004 temporal state reconstruction (no dataset files needed).

Run: python -m unittest discover -s experiments -p "test_exp004.py" -v
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from exp004 import base, choose, obs_time  # noqa: E402

CUT = "2026-06-30T00:00:00Z"


def ob(state, cap="2026-06-10T00:00:00Z", at=None, rec=None, fid="evidence_a", line=None, explicit=None):
    o = base.Obs(fid, cap, "account_service", "account_1", state, None, set(),
                 state == "ABSENT" if explicit is None else explicit)
    if at:
        o.observed_at = at
    if rec:
        o.record_time = rec
    if line is not None:
        o.line = line
    return o


class TestTransitions(unittest.TestCase):
    def check(self, first, second):
        obs = [ob(first, at="2026-06-01T00:00:00Z", line=1), ob(second, at="2026-06-05T00:00:00Z", line=2)]
        chosen, info = choose(obs, CUT)
        self.assertEqual(chosen.state, second)
        return info

    def test_present_to_absent(self):
        self.check("PRESENT_ID", "ABSENT")

    def test_absent_to_present_is_flagged_as_reappearance(self):
        info = self.check("ABSENT", "PRESENT_ID")
        self.assertIn("reappeared", info)

    def test_present_to_redacted(self):
        self.check("PRESENT_ID", "PRESENT_CLEAN")

    def test_active_to_disabled(self):
        self.check("FLOW_ACTIVE", "FLOW_DISABLED")

    def test_disabled_to_active(self):
        self.check("FLOW_DISABLED", "FLOW_ACTIVE")


class TestTime(unittest.TestCase):
    def test_file_captured_after_cutoff_is_excluded(self):
        obs = [ob("PRESENT_ID", cap="2026-06-10T00:00:00Z", at="2026-06-01T00:00:00Z"),
               ob("ABSENT", cap="2026-07-05T00:00:00Z", at="2026-06-20T00:00:00Z", fid="evidence_late")]
        chosen, info = choose(obs, CUT)
        self.assertEqual((chosen.state, chosen.file_id), ("PRESENT_ID", "evidence_a"))
        self.assertEqual(info["excluded_after_cutoff"], 1)

    def test_out_of_order_lines_use_timestamps_not_line_order(self):
        obs = [ob("ABSENT", at="2026-06-08T00:00:00Z", line=2), ob("PRESENT_ID", at="2026-06-02T00:00:00Z", line=40)]
        chosen, _ = choose(obs, CUT)
        self.assertEqual(chosen.state, "ABSENT")

    def test_missing_timestamp_falls_back_to_capture_time(self):
        snapshot = ob("PRESENT_ID", cap="2026-06-12T00:00:00Z", fid="evidence_snap")  # no line/record time
        log = ob("ABSENT", cap="2026-06-20T00:00:00Z", at="2026-06-03T00:00:00Z", fid="evidence_log")
        chosen, _ = choose([snapshot, log], CUT)
        self.assertEqual(obs_time(snapshot), ("2026-06-12T00:00:00Z", "capture"))
        self.assertEqual(chosen.file_id, "evidence_snap")  # observed later, although captured earlier

    def test_record_time_is_used_when_present(self):
        o = ob("PRESENT_CLEAN", cap="2026-06-12T00:00:00Z", rec="2026-06-11T09:00:00Z")
        self.assertEqual(obs_time(o), ("2026-06-11T09:00:00Z", "record"))

    def test_post_dated_observation_is_flagged_and_not_used(self):
        good = ob("ABSENT", cap="2026-06-12T00:00:00Z", at="2026-06-10T00:00:00Z")
        post = ob("PRESENT_ID", cap="2026-06-12T00:00:00Z", at="2026-06-15T00:00:00Z")  # dated after its own capture
        self.assertEqual(obs_time(post)[1], "post-dated")
        chosen, info = choose([good, post], CUT)
        self.assertEqual(chosen.state, "ABSENT")
        self.assertEqual(len(info["post_dated_ignored"]), 1)

    def test_no_usable_evidence(self):
        chosen, info = choose([ob("PRESENT_ID", cap="2026-07-01T00:00:00Z")], CUT)
        self.assertIsNone(chosen)
        self.assertEqual(info["usable"], 0)


class TestTies(unittest.TestCase):
    def test_equal_time_comparable_sources_prefer_least_compliant_but_stay_ambiguous(self):
        t = "2026-06-05T00:00:00Z"
        obs = [ob("ABSENT", at=t, fid="evidence_a"), ob("PRESENT_ID", at=t, fid="evidence_b")]
        chosen, info = choose(obs, CUT)
        self.assertEqual(chosen.state, "PRESENT_ID")
        self.assertTrue(info["ambiguous"])
        self.assertTrue(info["preference_applied"])
        self.assertIn("not proof", info["tie"])

    def test_tie_keeps_every_observation_with_provenance(self):
        t = "2026-06-05T00:00:00Z"
        _, info = choose([ob("ABSENT", at=t, fid="evidence_a", line=3), ob("PRESENT_ID", at=t, fid="evidence_b", line=9)], CUT)
        self.assertEqual(sorted((x["file_id"], x["line"], x["state"]) for x in info["tied_observations"]),
                         [("evidence_a", 3, "ABSENT"), ("evidence_b", 9, "PRESENT_ID")])

    def test_incomparable_scopes_get_no_preference(self):
        t = "2026-06-05T00:00:00Z"
        a = ob("ABSENT", at=t, fid="evidence_a")
        b = ob("PRESENT_ID", at=t, fid="evidence_b")
        b.system = "search_service"  # different system: authority/scope not comparable
        _, info = choose([a, b], CUT)
        self.assertTrue(info["ambiguous"])
        self.assertFalse(info["preference_applied"])

    def test_primary_vs_replica_copies_are_not_merged(self):
        # One snapshot: primary copy gone, replica copy still holds the record.
        p = ob("ABSENT", cap="2026-06-10T00:00:00Z")
        r = ob("PRESENT_ID", cap="2026-06-10T00:00:00Z", explicit=False)
        p.scope, r.scope = "evidence_a:customer_profiles_primary", "evidence_a:customer_profiles_failover_replica"
        chosen, info = choose([p, r], CUT)
        self.assertEqual(chosen.state, "PRESENT_ID")  # C08: a remaining copy means the record exists
        self.assertEqual({x["scope"]: x["state"] for x in info["tied_observations"]},
                         {"evidence_a:customer_profiles_primary": "ABSENT", "evidence_a:customer_profiles_failover_replica": "PRESENT_ID"})
        self.assertIn("different copies", info["tie"])

    def test_repeated_identical_observations_are_not_a_conflict(self):
        t = "2026-06-05T00:00:00Z"
        chosen, info = choose([ob("FLOW_DISABLED", at=t, fid="evidence_a"), ob("FLOW_DISABLED", at=t, fid="evidence_b")], CUT)
        self.assertEqual(chosen.state, "FLOW_DISABLED")
        self.assertNotIn("tie", info)

    def test_equal_time_disabled_vs_active_keeps_active(self):
        t = "2026-06-05T00:00:00Z"
        chosen, _ = choose([ob("FLOW_DISABLED", at=t, fid="evidence_a"), ob("FLOW_ACTIVE", at=t, fid="evidence_b")], CUT)
        self.assertEqual(chosen.state, "FLOW_ACTIVE")


if __name__ == "__main__":
    unittest.main(verbosity=2)
