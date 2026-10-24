"""Clean-entry-point test: code/main.py runs from a copy that contains only code/ and dataset/.

Checks: no dependency on experiments/ or spike/; 518 rows, sorted, exact header; the strict validator
gates publication (an invalid run must not write output.csv and must exit 1; a valid run must publish).
Run: python -m unittest discover -s code/tests -p "test_entrypoint.py" -v
"""
from __future__ import annotations

import csv
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CODE = Path(__file__).resolve().parents[1]
REPO = CODE.parent


class CleanEntryPoint(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        shutil.copytree(CODE, cls.root / "code", ignore=shutil.ignore_patterns("__pycache__", "tests"))
        shutil.copytree(REPO / "dataset", cls.root / "dataset")
        cls.proc = subprocess.run([sys.executable, "-I", str(cls.root / "code" / "main.py")],
                                  cwd=cls.root, capture_output=True, text=True, timeout=300)
        cls.notes = json.loads((cls.root / "runs" / "run_notes.json").read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_copy_has_no_experiment_code(self):
        self.assertEqual(sorted(p.name for p in self.root.iterdir() if p.name != "runs"), ["code", "dataset"])

    def test_candidate_schema_and_rows(self):
        cand = self.root / "runs" / "output.candidate.csv"
        path = cand if cand.exists() else self.root / "output.csv"
        with path.open(encoding="utf-8", newline="") as fh:
            rows = list(csv.reader(fh))
        self.assertEqual(rows[0], ["case_id", "deletion_status", "steps_json"])
        ids = [r[0] for r in rows[1:]]
        with (self.root / "dataset" / "deletion_requests.csv").open(encoding="utf-8", newline="") as fh:
            requested = [r["case_id"] for r in csv.DictReader(fh)]
        self.assertEqual(len(ids), 518)
        self.assertEqual(sorted(ids, key=lambda c: int(c.split("_")[1])), ids)
        self.assertEqual(set(ids), set(requested))

    def test_validation_gates_publication(self):
        valid = self.notes["validation"]["valid"]
        published = (self.root / "output.csv").exists()
        self.assertEqual(published, valid, "output.csv must exist exactly when the strict validator passed")
        self.assertEqual(self.proc.returncode, 0 if valid else 1)

    def test_no_model_calls(self):
        self.assertEqual((self.notes["model_calls"], self.notes["input_tokens"], self.notes["output_tokens"]), (0, 0, 0))


if __name__ == "__main__":
    unittest.main(verbosity=2)
