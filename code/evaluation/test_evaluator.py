"""Self-tests for the validator and evaluator.

Strategy: start from the official sample answers (known correct), apply one
known defect at a time, and check that the right rule fires and the right
metric moves by the expected amount.

Run:  python -m unittest discover -s code/evaluation -p "test_*.py" -v
"""
from __future__ import annotations

import csv
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import eval as ev  # noqa: E402
from contract_spec import DATASET_DIR  # noqa: E402
from splits import DEV, RESERVED  # noqa: E402
from validate_output import load_evidence_index, load_requests, validate_text  # noqa: E402

GOLD = DATASET_DIR / "sample_output.csv"
REQ = DATASET_DIR / "sample_deletion_requests.csv"


def read_rows() -> list[list]:
    with GOLD.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.reader(fh))
    return [rows[0]] + [[r[0], r[1], json.loads(r[2])] for r in rows[1:]]


def render(rows: list[list]) -> str:
    buf = io.StringIO(newline="")
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(rows[0])
    for cid, status, steps in rows[1:]:
        w.writerow([cid, status, steps if isinstance(steps, str) else json.dumps(steps, separators=(",", ":"))])
    return buf.getvalue()


def renumber(steps: list[dict]) -> list[dict]:
    for i, s in enumerate(steps, start=1):
        s["step_no"] = i
    return steps


def case(rows: list[list], cid: str) -> list:
    return next(r for r in rows[1:] if r[0] == cid)


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.requests = load_requests(REQ)
        cls.evidence = load_evidence_index(DATASET_DIR)
        cls.tmp = tempfile.TemporaryDirectory()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def validate(self, rows):
        return validate_text(render(rows), self.requests, self.evidence)

    def rules(self, rows):
        return {i.rule for i in self.validate(rows).errors}

    def score(self, rows, cases=DEV):
        p = Path(self.tmp.name) / "pred.csv"
        p.write_text(render(rows), encoding="utf-8", newline="")
        return ev.evaluate(p, GOLD, REQ, cases, DATASET_DIR)


class TestValidator(Base):
    def test_official_answers_are_valid_without_warnings(self):
        res = self.validate(read_rows())
        self.assertEqual(res.errors, [])
        self.assertEqual(res.warnings, [])
        self.assertEqual(res.rows_checked, 32)

    def test_missing_row(self):
        rows = read_rows()
        del rows[5]
        self.assertIn("R03", self.rules(rows))

    def test_duplicate_row(self):
        rows = read_rows()
        rows.insert(3, list(rows[2]))
        self.assertIn("R03", self.rules(rows))

    def test_wrong_header(self):
        rows = read_rows()
        rows[0] = ["case_id", "status", "steps_json"]
        self.assertIn("R02", self.rules(rows))

    def test_bom_rejected(self):
        res = validate_text("﻿" + render(read_rows()), self.requests, self.evidence)
        self.assertIn("R02", {i.rule for i in res.errors})

    def test_unsorted_rows(self):
        rows = read_rows()
        rows[1], rows[2] = rows[2], rows[1]
        self.assertIn("R04", self.rules(rows))

    def test_plain_text_order_is_warning_only(self):
        # Two synthetic ids where numeric and plain-text order differ.
        reqs = {"case_9": {"audit_at": "2026-12-31T00:00:00Z"}, "case_10": {"audit_at": "2026-12-31T00:00:00Z"}}
        text = "case_id,deletion_status,steps_json\ncase_10,NOT_APPLICABLE,[]\ncase_9,NOT_APPLICABLE,[]\n"
        res = validate_text(text, reqs, self.evidence)
        self.assertEqual(res.errors, [])
        self.assertIn("R04", {i.rule for i in res.warnings})

    def test_invalid_status(self):
        rows = read_rows()
        case(rows, "case_05")[1] = "PARTIAL"
        self.assertIn("R05", self.rules(rows))

    def test_steps_not_array(self):
        rows = read_rows()
        case(rows, "case_05")[2] = '{"step_no":1}'
        self.assertIn("R06", self.rules(rows))

    def test_extra_key(self):
        rows = read_rows()
        case(rows, "case_05")[2][0]["note"] = "x"
        self.assertIn("R07", self.rules(rows))

    def test_step_no_gap(self):
        rows = read_rows()
        case(rows, "case_11")[2][3]["step_no"] = 9
        self.assertIn("R08", self.rules(rows))

    def test_invalid_operation_state_pair(self):
        rows = read_rows()
        case(rows, "case_05")[2][0]["state"] = "ACTIVE"
        self.assertIn("R10", self.rules(rows))

    def test_phase_order(self):
        rows = read_rows()
        steps = case(rows, "case_05")[2]
        steps[0], steps[1] = steps[1], steps[0]  # REMEDIATION before FINDING
        renumber(steps)
        self.assertIn("R09", self.rules(rows))

    def test_intra_phase_order(self):
        rows = read_rows()
        steps = case(rows, "case_11")[2]
        steps[8], steps[9] = steps[9], steps[8]  # two VERIFICATION steps
        renumber(steps)
        self.assertIn("R15", self.rules(rows))

    def test_not_applicable_with_steps(self):
        rows = read_rows()
        case(rows, "case_05")[1] = "NOT_APPLICABLE"
        self.assertIn("R11", self.rules(rows))

    def test_complete_with_finding(self):
        rows = read_rows()
        case(rows, "case_01")[2].insert(0, {"step_no": 1, "phase": "FINDING", "system_id": "search_service",
                                            "resource_id": "search_1", "operation": "REPORT_REMAINING_RECORD",
                                            "state": "PRESENT", "evidence_id": "evidence_54"})
        renumber(case(rows, "case_01")[2])
        self.assertIn("R12", self.rules(rows))

    def test_complete_verification_needs_evidence(self):
        rows = read_rows()
        case(rows, "case_01")[2][0]["evidence_id"] = ""
        self.assertIn("R12", self.rules(rows))

    def test_incomplete_remediation_must_have_empty_evidence(self):
        rows = read_rows()
        case(rows, "case_05")[2][1]["evidence_id"] = "evidence_54"
        self.assertIn("R13", self.rules(rows))

    def test_unknown_evidence_id(self):
        rows = read_rows()
        case(rows, "case_05")[2][0]["evidence_id"] = "evidence_999"
        self.assertIn("C01", self.rules(rows))

    def test_evidence_after_audit_at(self):
        rows = read_rows()
        # case_05 audit_at 2026-09-08T13:40Z; evidence_92 is captured 2026-09-15.
        case(rows, "case_05")[2][0]["evidence_id"] = "evidence_92"
        self.assertIn("C03", self.rules(rows))

    def test_activity_and_audit_ids_are_citable(self):
        rows = read_rows()
        case(rows, "case_05")[2][0]["evidence_id"] = "activity_01"  # 2026-01-04, before audit_at
        self.assertEqual(self.rules(rows), set())

    def test_unpaired_finding_is_a_warning_not_error(self):
        rows = read_rows()
        steps = case(rows, "case_05")[2]
        del steps[1]  # drop DELETE_RECORD remediation
        renumber(steps)
        res = self.validate(rows)
        self.assertEqual(res.errors, [])
        self.assertIn("R30", {i.rule for i in res.warnings})


class TestEvaluator(Base):
    def test_gold_scores_perfect(self):
        r = self.score(read_rows())
        self.assertEqual(r["cases"], 22)
        for k in ("status_accuracy", "field_accuracy", "positional_accuracy", "sequence_accuracy",
                  "evidence_validity", "policy_compliance"):
            self.assertEqual(r[k], 1.0, k)
        self.assertEqual(r["step"], {"precision": 1.0, "recall": 1.0, "f1": 1.0})

    def test_dropped_step_lowers_recall_only(self):
        rows = read_rows()
        steps = case(rows, "case_11")[2]  # dev case, 14 steps
        del steps[0]
        renumber(steps)
        r = self.score(rows)
        self.assertEqual(r["step"]["precision"], 1.0)
        self.assertLess(r["step"]["recall"], 1.0)
        self.assertAlmostEqual(r["sequence_accuracy"], 21 / 22, places=4)
        self.assertEqual(len(r["per_case"]["case_11"]["missing"]), 1)

    def test_extra_step_lowers_precision_and_field_accuracy(self):
        rows = read_rows()
        steps = case(rows, "case_05")[2]
        steps.append({"step_no": 4, "phase": "VERIFICATION", "system_id": "zz_service", "resource_id": "zz_1",
                      "operation": "VERIFY_RESTORE_BLOCKED", "state": "BLOCKED", "evidence_id": ""})
        r = self.score(rows)
        self.assertLess(r["step"]["precision"], 1.0)
        self.assertEqual(r["step"]["recall"], 1.0)
        self.assertLess(r["field_accuracy"], 1.0)

    def test_wrong_evidence_hits_step_but_not_core(self):
        rows = read_rows()
        case(rows, "case_03")[2][0]["evidence_id"] = "evidence_54"
        r = self.score(rows)
        self.assertLess(r["step"]["f1"], 1.0)
        self.assertEqual(r["step_core"]["f1"], 1.0)
        self.assertLess(r["field_accuracy_by_field"]["evidence_id"], 1.0)
        self.assertEqual(r["field_accuracy_by_field"]["operation"], 1.0)

    def test_reordered_steps_keep_f1_but_lose_sequence(self):
        rows = read_rows()
        steps = case(rows, "case_11")[2]
        steps[8], steps[9] = steps[9], steps[8]
        renumber(steps)
        r = self.score(rows)
        self.assertEqual(r["step"]["f1"], 1.0)
        self.assertLess(r["positional_accuracy"], 1.0)
        self.assertLess(r["sequence_accuracy"], 1.0)
        self.assertLess(r["policy_compliance"], 1.0)

    def test_wrong_status(self):
        rows = read_rows()
        case(rows, "case_01")[1] = "NOT_APPLICABLE"
        case(rows, "case_01")[2] = []
        r = self.score(rows)
        self.assertAlmostEqual(r["status_accuracy"], 21 / 22, places=4)
        self.assertEqual(r["status_confusion"].get("COMPLETE->NOT_APPLICABLE"), 1)

    def test_missing_prediction_row(self):
        rows = [r for r in read_rows() if r[0] != "case_02"]
        r = self.score(rows)
        self.assertEqual(r["per_case"]["case_02"]["pred_status"], "<missing>")
        self.assertLess(r["status_accuracy"], 1.0)

    def test_reserved_requires_flag(self):
        with self.assertRaises(SystemExit):
            ev.main(["--pred", str(GOLD), "--split", "reserved"])

    def test_splits_cover_all_samples_once(self):
        self.assertEqual(sorted(DEV + RESERVED), [f"case_{i:02d}" for i in range(1, 33)])
        steps = {r[0]: len(r[2]) for r in read_rows()[1:]}
        self.assertTrue(any(steps[c] == 14 for c in RESERVED), "D4: reserved set needs a 14-step case")


if __name__ == "__main__":
    unittest.main(verbosity=2)
