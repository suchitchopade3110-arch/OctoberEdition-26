"""One-command evaluation of the deletion-audit agent.

    python code/evaluation/main.py            # samples -> metrics (dev / reserved / all), validator, scenarios

Steps:
  1. run the agent (code/main.py) on the 32 public sample requests into a temporary folder;
  2. score the predictions against dataset/sample_output.csv on the dev, reserved and all splits (eval.py);
  3. run the strict validator on the agent's full 518-case candidate if it exists (runs/output.candidate.csv);
  4. run the synthetic end-to-end scenarios (custom_scenarios.py).
Local metrics on public samples are not the hidden judge's score.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


def run(args: list[str]) -> str:
    return subprocess.run([sys.executable, *args], cwd=REPO, capture_output=True, text=True).stdout


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        pred = Path(tmp) / "samples.csv"
        run([str(REPO / "code" / "main.py"), "--requests", str(REPO / "dataset" / "sample_deletion_requests.csv"),
             "--output", str(pred), "--work-dir", str(Path(tmp) / "work")])
        for split in ("dev", "reserved", "all"):
            report = run([str(HERE / "eval.py"), "--pred", str(pred), "--requests",
                          str(REPO / "dataset" / "sample_deletion_requests.csv"), "--split", split, "--allow-reserved"])
            print("\n".join(report.splitlines()[:16]), "\n")
    candidate = REPO / "runs" / "output.candidate.csv"
    if candidate.exists():
        print("## Strict validator (518-case candidate)\n" + run([str(HERE / "validate_output.py"), "--output", str(candidate),
                                                                   "--max-issues", "10"]))
    print("## Synthetic scenarios\n" + run([str(HERE / "custom_scenarios.py")]).splitlines()[-1])
    return 0


if __name__ == "__main__":
    sys.exit(main())
