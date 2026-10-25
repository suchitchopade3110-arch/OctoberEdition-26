"""Custom end-to-end evaluation scenarios (participant-built; required by AGENTS.md §6.8).

Each scenario builds a tiny synthetic dataset (fictional people, `.test` email domains) in a temporary folder, runs the
production pipeline (`code/main.py` -> `run()`, no evidence cache, no model calls) and compares the result with an expected
row written by hand from the contract (problem_statement.md) before running. Only `deletion_rules.csv` is copied from the
participant dataset, because the policy table is shared input, not case data.

    python code/evaluation/custom_scenarios.py            # prints a table; exit status 1 if any scenario fails
"""
from __future__ import annotations

import csv
import importlib.util
import json
import shutil
import sys
import tempfile
from pathlib import Path

CODE = Path(__file__).resolve().parents[1]
REPO = CODE.parent

PERSON = {"user_id": "user_901", "name": "Tess Person", "email": "t.person@example.test", "phone": "+1 555 010 0901",
          "email_hash": "ab" * 32, "updated_at": "2026-01-01T00:00:00Z"}
DELETE_TEXT = "Please delete my account and all personal data you hold about me."


def search_snapshot(records: list[dict]) -> dict:
    return {"exported_at": "x", "source": "custom", "snapshots": [
        {"data_store": "search_service", "collection": "customer_search_documents", "records": records}]}


def search_doc(email: str, rid: str = "search_9001") -> dict:
    return {"resource_id": rid, "customer_reference": None, "display_name": "Tess Person", "email": email, "phone": None,
            "email_hash": None, "index_name": "customers_v1", "updated_at": "2026-04-30T10:00:00Z"}


def step(n, phase, op, system, rid, state, ev=""):
    return {"step_no": n, "phase": phase, "system_id": system, "resource_id": rid, "operation": op, "state": state, "evidence_id": ev}


REMAINING = [step(1, "FINDING", "REPORT_REMAINING_RECORD", "search_service", "search_9001", "PRESENT", "evidence_901"),
             step(2, "REMEDIATION", "DELETE_RECORD", "search_service", "search_9001", "ABSENT"),
             step(3, "VERIFICATION", "VERIFY_RECORD_ABSENT", "search_service", "search_9001", "ABSENT")]

SCENARIOS = [
    {"id": "S1", "title": "Access request is not a deletion (intent)",
     "request": {"email": PERSON["email"], "text": "Could you send me a copy of the personal data you hold about me?"},
     "evidence": [("evidence_901", "2026-05-01T09:00:00Z", search_snapshot([search_doc(PERSON["email"])]))],
     "audit_log": [], "expect": ("NOT_APPLICABLE", [])},
    {"id": "S2", "title": "Workflow says COMPLETE but a search copy remains",
     "request": {"email": PERSON["email"], "text": DELETE_TEXT},
     "evidence": [("evidence_901", "2026-05-01T09:00:00Z", search_snapshot([search_doc(PERSON["email"])]))],
     "audit_log": [], "expect": ("INCOMPLETE", REMAINING)},
    {"id": "S3", "title": "Evidence captured after audit_at is ignored",
     "request": {"email": PERSON["email"], "text": DELETE_TEXT},
     "evidence": [("evidence_901", "2026-05-01T09:00:00Z", search_snapshot([search_doc(PERSON["email"])])),
                  ("evidence_902", "2026-06-01T09:00:00Z", search_snapshot([]))],          # later snapshot, record gone
     "audit_log": [], "expect": ("INCOMPLETE", REMAINING)},
    # S4 originally expected COMPLETE (our first contract reading: a later snapshot that omits the record proves
    # absence). An experiment implemented that reading and it contradicted two official sample answers: sample case_05 keeps
    # account_005 as a remaining record (evidence_54) although the later evidence_90 omits it, and sample case_24 does
    # the same for account_5334 (evidence_92 vs evidence_51). The official answers decide, so the expectation follows
    # them: omission from a later snapshot is not proof of absence; the copy is still reported as remaining.
    {"id": "S4", "title": "A later snapshot that merely omits a record does not prove absence",
     "request": {"email": PERSON["email"], "text": DELETE_TEXT},
     "evidence": [("evidence_901", "2026-05-01T09:00:00Z", search_snapshot([search_doc(PERSON["email"])])),
                  ("evidence_902", "2026-05-10T09:00:00Z", search_snapshot([]))],          # before audit_at, record omitted
     "audit_log": [],
     "expect": ("INCOMPLETE", REMAINING)},
    {"id": "S5", "title": "Request uses a historical email; the copy is keyed by it",
     "request": {"email": "tess.old@example.test", "text": DELETE_TEXT},
     "evidence": [("evidence_901", "2026-05-01T09:00:00Z", search_snapshot([search_doc("tess.old@example.test")]))],
     "audit_log": [{"audit_id": "audit_901", "user_id": "user_901", "event_time": "2025-06-01T00:00:00Z",
                    "field_name": "email", "old_value": "tess.old@example.test", "new_value": PERSON["email"]}],
     "expect": ("INCOMPLETE", REMAINING)},
]


def write_csv(path: Path, header: list[str], rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=header)
        w.writeheader()
        w.writerows(rows)


def build(sc: dict, root: Path) -> Path:
    d = root / sc["id"]
    (d / "evidence" / "records").mkdir(parents=True)
    shutil.copy(REPO / "dataset" / "deletion_rules.csv", d / "deletion_rules.csv")
    write_csv(d / "user_identities.csv", list(PERSON), [PERSON])
    write_csv(d / "user_audit_log.csv", ["audit_id", "user_id", "event_time", "field_name", "old_value", "new_value"], sc["audit_log"])
    write_csv(d / "system_activity.csv", ["activity_id", "event_time", "event_type", "source_system", "target_system",
                                          "resource_id", "reported_result", "details"], [])
    files = []
    for fid, cap, body in sc["evidence"]:
        rel = f"evidence/records/{fid}.json"
        (d / rel).write_text(json.dumps(body), encoding="utf-8")
        files.append({"file_id": fid, "file_path": rel, "origin": "records_export", "captured_at": cap})
    write_csv(d / "evidence_files.csv", ["file_id", "file_path", "origin", "captured_at"], files)
    hdr = ["case_id", "email", "requested_at", "reported_status", "reported_at", "audit_at", "request_text"]
    write_csv(d / "deletion_requests.csv", hdr, [{"case_id": "case_901", "email": sc["request"]["email"],
                                                  "requested_at": "2026-04-28T09:00:00Z", "reported_status": "COMPLETE",
                                                  "reported_at": "2026-04-30T09:00:00Z", "audit_at": "2026-05-20T09:00:00Z",
                                                  "request_text": sc["request"]["text"]}])
    write_csv(d / "sample_deletion_requests.csv", hdr, [])
    return d


def main() -> int:
    spec = importlib.util.spec_from_file_location("ghost_main", CODE / "main.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    from validate_output import load_evidence_index, validate_text
    from ghostaudit.output import serialise_steps
    failed = 0
    print("| Scenario | Expected | Got | Steps match | Validator | Result |\n|---|---|---|---|---|---|")
    with tempfile.TemporaryDirectory() as tmp:
        for sc in SCENARIOS:
            d = build(sc, Path(tmp))
            rows, _ = m.run(d, d / "deletion_requests.csv", [d / "sample_deletion_requests.csv", d / "deletion_requests.csv"], None, None)
            cid, status, steps_json = rows[0]
            got = json.loads(steps_json)
            exp_status, exp_steps = sc["expect"]
            same = status == exp_status and got == exp_steps
            text = "case_id,deletion_status,steps_json\n" + f'{cid},{status},"{serialise_steps(got).replace(chr(34), chr(34) * 2)}"\n'
            reqs = {q["case_id"]: q for q in csv.DictReader(open(d / "deletion_requests.csv", encoding="utf-8"))}
            v = validate_text(text, reqs, load_evidence_index(d))
            failed += not (same and v.ok)
            print(f"| {sc['id']} {sc['title']} | {exp_status} ({len(exp_steps)}) | {status} ({len(got)}) | {'yes' if same else 'NO'} "
                  f"| {'ok' if v.ok else 'errors ' + str(len(v.errors))} | {'PASS' if same and v.ok else 'FAIL'} |")
            if not same:
                print(f"|  | expected {json.dumps(exp_steps)} | got {json.dumps(got)} |  |  |  |")
    print(f"\n{len(SCENARIOS) - failed}/{len(SCENARIOS)} scenarios pass")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
