"""Independent audit repro cases (fixture: fixtures/audit_repro_cases.json), run against production code.

Known defects are expectedFailure: they stay visible in every run and turn into "unexpected success"
once fixed. Nothing here is relaxed to make a run pass.
Run: python -m unittest discover -s code/tests -v
"""
from __future__ import annotations

import json
import re
import sys
import unittest
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

CODE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CODE))

from ghostaudit import evidence as ev  # noqa: E402
from ghostaudit.intent import authorizes_deletion  # noqa: E402
from ghostaudit.temporal import choose  # noqa: E402

FIX = json.loads((Path(__file__).parent / "fixtures" / "audit_repro_cases.json").read_text(encoding="utf-8"))
DATA = CODE.parent / "dataset"


def parse(log: str) -> ev.Index:
    idx = ev.Index({})
    ev.parse_log(idx, {"file_id": "fx", "captured_at": "2026-09-30T00:00:00Z"}, log, set(), defaultdict(int))
    return idx


def make_obs(d: dict) -> ev.Obs:
    o = ev.Obs(d["file_id"], d["captured_at"], d["system"], d["resource_id"], d["state"], d.get("category"),
               set(), d.get("explicit_absent", False))
    o.scope, o.record_time = d.get("scope"), d.get("record_time")
    return o


def audit_synthetic(observations: list, cutoff: str) -> tuple[str, list]:
    """Run the production Auditor.audit on a tiny synthetic world (no dataset files)."""
    from ghostaudit.auditor import Auditor
    a = Auditor.__new__(Auditor)
    a.rules = {"USER_PROFILE": "DELETE", "SECURITY_AUDIT_LOG": "RETAIN"}
    a.by_email, a.keys = {"subject@x.io": "user_1"}, {"user_1": {"subject@x.io", "user_1"}}
    a.idx = ev.Index({"account": "account_service"})
    for o in observations:
        o.keys = {"subject@x.io"}
        a.idx.obs.append(o)
    a.obs_by_res = defaultdict(list)
    for o in a.idx.obs:
        a.obs_by_res[o.resource_id].append(o)
    a.links, a.activity, a.state_log = [], [], {}
    q = {"case_id": "synthetic", "email": "subject@x.io", "audit_at": cutoff, "request_text": "Please delete my account."}
    return a.audit(q, None, [])


def _mark(case, fn):
    return unittest.expectedFailure(fn) if case.get("known_defect") else fn


class Parser(unittest.TestCase):
    pass


for _c in FIX["parser"]:
    def _t(self, c=_c):
        idx = parse(c["log"])
        exp = c["expected"]
        if "resources" in exp:
            self.assertEqual(sorted({o.resource_id for o in idx.obs}), exp["resources"])
        if "state_at_cutoff" in exp:
            chosen, _ = choose(idx.obs, c["cutoff"])
            self.assertEqual(chosen.state, exp["state_at_cutoff"])
        if "key_present" in exp:
            self.assertTrue(any(exp["key_present"] in o.keys for o in idx.obs))
    setattr(Parser, f"test_{_c['id']}", _mark(_c, _t))


class Temporal(unittest.TestCase):
    pass


for _c in FIX["temporal"]:
    def _t(self, c=_c):
        chosen, info = choose([make_obs(d) for d in c["observations"]], c["cutoff"])
        exp = c["expected"]
        if "state_not" in exp:
            self.assertNotEqual(chosen.state, exp["state_not"])
        if "chosen" in exp:
            self.assertIsNone(chosen)
        if "auditor_state_not" in exp:
            # Behavioural check through the production auditor (not a source-text check): a resource whose only
            # observation is post-dated must not come out as verified ABSENT in a COMPLETE case (F02/F13).
            status, steps = audit_synthetic([make_obs(d) for d in c["observations"]], c["cutoff"])
            rid = c["observations"][0]["resource_id"]
            self.assertFalse(status == "COMPLETE" and any(s["resource_id"] == rid and s["state"] == "ABSENT" for s in steps),
                             (status, steps))
        if "ambiguous" in exp:
            self.assertEqual(info.get("ambiguous"), exp["ambiguous"])
            self.assertEqual(info.get("preference_applied"), exp["preference_applied"])
    setattr(Temporal, f"test_{_c['id']}", _mark(_c, _t))


class Intent(unittest.TestCase):
    pass


for _c in FIX["intent"]:
    def _t(self, c=_c):
        self.assertEqual(authorizes_deletion(c["text"]), c["expected"], c["text"])
    _c["known_defect"] = _c["expected"] != _c["observed_on_aca42dc"]
    setattr(Intent, f"test_{_c['id']}", _mark(_c, _t))


@lru_cache(maxsize=1)
def full_run() -> dict:
    """Production audit of every request (diagnostic; nothing is written)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("ghost_main", CODE / "main.py")  # not code/evaluation/main.py
    entry = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(entry)
    rows, _ = entry.run(DATA, DATA / "deletion_requests.csv",
                  [DATA / "sample_deletion_requests.csv", DATA / "deletion_requests.csv"], None)
    return {cid: (status, json.loads(steps)) for cid, status, steps in rows}


class DatasetRegressions(unittest.TestCase):
    @unittest.expectedFailure
    def test_R12_F01_no_uncited_complete_verification(self):
        bad = [cid for cid, (st, steps) in full_run().items() if st == "COMPLETE" and any(not s["evidence_id"] for s in steps)]
        self.assertEqual(bad, [])

    def test_R12_EMPTY_no_empty_complete_row(self):  # fixed by D18; now a guard
        bad = [cid for cid, (st, steps) in full_run().items() if st == "COMPLETE" and not steps]
        self.assertEqual(bad, [])

    def test_F12_linked_retained_record_not_silently_dropped(self):  # fixed by D18; now a guard
        case = next(c for c in FIX["dataset_regressions"] if c["id"] == "F12")
        st, steps = full_run()[case["cases_observed"][0]]
        self.assertTrue(st != "COMPLETE" or any(s["resource_id"] == case["resource"] for s in steps))

    def test_observed_counts_still_match_fixture(self):
        """Guards the fixture itself: the recorded defect footprint is what production still produces."""
        run = full_run()
        r12 = sorted({cid for cid, (st, steps) in run.items() if st == "COMPLETE" and any(not s["evidence_id"] for s in steps)})
        case = next(c for c in FIX["dataset_regressions"] if c["id"] == "R12-F01")
        self.assertEqual(r12, case["cases_observed"])
        self.assertEqual(sum(1 for st, steps in run.values() if st == "COMPLETE" for s in steps if not s["evidence_id"]),
                         case["errors_observed"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
