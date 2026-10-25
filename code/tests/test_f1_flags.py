"""F1 regression tests: boolean restore/flow flags (D30 finding, D31 approval).

SQL inventory snapshots declare `enabled` and `restore_allowed` as `INTEGER NOT NULL CHECK (x IN (0,1))`, so sqlite
returns them as 0/1 integers. Before F1 those were not read as flags, and the policy then verified open restores and
active flows as blocked/disabled. Expected rows below are written from the contract (problem_statement.md, Allowed
Operations and Rules), not from a run.

Run: python -m unittest discover -s code/tests -p "test_f1_flags.py" -v
"""
from __future__ import annotations

import csv
import importlib.util
import json
import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

CODE = Path(__file__).resolve().parents[1]
REPO = CODE.parent
sys.path.insert(0, str(CODE))

from ghostaudit import evidence as ev  # noqa: E402
from ghostaudit.temporal import choose  # noqa: E402

AUDIT_AT = "2026-05-20T09:00:00Z"
PERSON = {"user_id": "user_951", "name": "Flag Person", "email": "f.person@example.test", "phone": "+1 555 010 0951",
          "email_hash": "cd" * 32, "updated_at": "2026-01-01T00:00:00Z"}

BACKUP_SQL = ("CREATE TABLE backup_restore_entries (resource_id TEXT PRIMARY KEY, customer_reference TEXT, customer_email TEXT, "
              "archive_key TEXT NOT NULL, restore_allowed INTEGER NOT NULL CHECK (restore_allowed IN (0,1)), updated_at TEXT NOT NULL);\n"
              "INSERT INTO backup_restore_entries VALUES ('backup_9501', NULL, '{email}', 'archive/b.tar', '{v}', '2026-04-30T10:00:00Z');\n")
FLOW_SQL = ("CREATE TABLE connector_subscriptions (resource_id TEXT PRIMARY KEY, customer_reference TEXT, customer_email TEXT, "
            "connector_name TEXT NOT NULL, enabled INTEGER NOT NULL CHECK (enabled IN (0,1)), last_delivery_status TEXT NOT NULL, "
            "updated_at TEXT NOT NULL);\n"
            "INSERT INTO connector_subscriptions VALUES ('data_flow_9501', NULL, '{email}', 'crm_sync', {v}, 'delivered', '2026-04-30T10:00:00Z');\n")


def state(rec: dict, category: str | None = None) -> str:
    return ev.infer_state(rec, category)[0]


def step(n, phase, op, system, rid, st, evid=""):
    return {"step_no": n, "phase": phase, "system_id": system, "resource_id": rid, "operation": op, "state": st,
            "evidence_id": evid}


# ---------------------------------------------------------------------------------------------- unit: field reading
class FlagValues(unittest.TestCase):
    def test_1_restore_allowed_int_1_is_open(self):
        self.assertEqual(state({"resource_id": "backup_1", "restore_allowed": 1}), "RESTORE_OPEN")

    def test_2_restore_allowed_int_0_is_blocked(self):
        self.assertEqual(state({"resource_id": "backup_1", "restore_allowed": 0}), "RESTORE_BLOCKED")

    def test_3_enabled_int_1_is_active(self):
        self.assertEqual(state({"resource_id": "data_flow_1", "enabled": 1}), "FLOW_ACTIVE")

    def test_4_enabled_int_0_is_disabled(self):
        self.assertEqual(state({"resource_id": "data_flow_1", "enabled": 0}), "FLOW_DISABLED")

    def test_5_native_booleans_and_text_booleans_unchanged(self):
        self.assertEqual(state({"resource_id": "b", "restore_allowed": True}), "RESTORE_OPEN")
        self.assertEqual(state({"resource_id": "b", "restore_allowed": False}), "RESTORE_BLOCKED")
        self.assertEqual(state({"resource_id": "d", "enabled": True}), "FLOW_ACTIVE")
        self.assertEqual(state({"resource_id": "d", "enabled": False}), "FLOW_DISABLED")
        self.assertEqual(state({"resource_id": "d", "enabled": "true"}), "FLOW_ACTIVE")       # log key=value form
        self.assertEqual(state({"resource_id": "b", "restore_allowed": "False"}), "RESTORE_BLOCKED")
        self.assertEqual(state({"resource_id": "b", "eligible": "true", "deletion_block": "false"}), "RESTORE_OPEN")
        self.assertEqual(state({"resource_id": "b", "eligible": "false", "deletion_block": "false"}), "RESTORE_BLOCKED")
        self.assertEqual(state({"resource_id": "b", "eligible": "true", "deletion_block": "true"}), "RESTORE_BLOCKED")

    def test_6a_null_flag_is_unknown_not_compliant(self):
        self.assertEqual(state({"resource_id": "b", "restore_allowed": None}), "RESTORE_UNKNOWN")
        self.assertEqual(state({"resource_id": "d", "enabled": None}), "FLOW_UNKNOWN")

    def test_6b_missing_flag_keeps_previous_behaviour(self):
        # No flag field at all is not a flag observation; this path (D30 F3, backup_9287) is deliberately untouched.
        self.assertEqual(state({"resource_id": "b", "customer_email": "x@example.test"}), "PRESENT_ID")
        self.assertEqual(state({"resource_id": "b", "archive_key": "k"}), "PRESENT_CLEAN")

    def test_6c_eligible_without_deletion_block_is_unknown(self):
        self.assertEqual(state({"resource_id": "b", "eligible": "true"}), "RESTORE_UNKNOWN")
        self.assertEqual(state({"resource_id": "b", "eligible": "false"}), "RESTORE_BLOCKED")   # explicit not-eligible

    def test_7_unexpected_values_are_unknown_never_false(self):
        for v in (2, -1, 1.0, 0.0, "1", "0", "yes", "", "enabled"):
            with self.subTest(v=v):
                self.assertEqual(state({"resource_id": "b", "restore_allowed": v}), "RESTORE_UNKNOWN")
                self.assertEqual(state({"resource_id": "d", "enabled": v}), "FLOW_UNKNOWN")
        self.assertEqual(state({"resource_id": "b", "eligible": "maybe", "deletion_block": "false"}), "RESTORE_UNKNOWN")

    def test_7b_no_boolean_coercion_outside_schema_flags(self):
        self.assertIsNone(ev.flag("eligible", 1))
        self.assertIsNone(ev.flag("deletion_block", 0))
        self.assertIsNone(ev.flag("rows", 1))
        self.assertEqual(state({"resource_id": "b", "eligible": 1, "deletion_block": 0}), "RESTORE_UNKNOWN")
        # Ordinary numeric fields keep their previous meaning.
        self.assertEqual(state({"resource_id": "analytics_1", "sessions": 1, "email": "x@example.test"}), "PRESENT_ID")
        self.assertEqual(state({"resource_id": "search_1", "rows": 0}), "ABSENT")


# ------------------------------------------------------------------------------------ unit: SQL schema round trip
class SqlSchemaFlags(unittest.TestCase):
    def parse_sql(self, sql: str) -> list:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "inv.sql"
            p.write_text(sql, encoding="utf-8")
            idx = ev.Index({"backup": "backup_service", "data_flow": "integration_service"})
            ev.parse_structured(idx, {"file_id": "evidence_951", "captured_at": "2026-05-01T09:00:00Z",
                                      "file_path": "inv.sql"}, Path(tmp))
            return idx.obs

    def test_sqlite_returns_int_for_check_constrained_columns(self):
        con = sqlite3.connect(":memory:")
        con.executescript(BACKUP_SQL.format(email="a@example.test", v="1"))
        self.assertIs(type(con.execute("select restore_allowed from backup_restore_entries").fetchone()[0]), int)

    def test_sql_restore_flags(self):
        for v, want in (("1", "RESTORE_OPEN"), ("0", "RESTORE_BLOCKED")):
            with self.subTest(v=v):
                obs = self.parse_sql(BACKUP_SQL.format(email="a@example.test", v=v))
                self.assertEqual([(o.resource_id, o.state, o.category) for o in obs], [("backup_9501", want, "BACKUP_ARCHIVE")])

    def test_sql_flow_flags(self):
        for v, want in ((1, "FLOW_ACTIVE"), (0, "FLOW_DISABLED")):
            with self.subTest(v=v):
                obs = self.parse_sql(FLOW_SQL.format(email="a@example.test", v=v))
                self.assertEqual([(o.resource_id, o.state, o.category) for o in obs], [("data_flow_9501", want, "DATA_FLOW")])


# ----------------------------------------------------------------------- unit: contradictory observations (D10-A)
class Contradictions(unittest.TestCase):
    def obs(self, fid, t, st, scope=None):
        o = ev.Obs(fid, t, "backup_service", "backup_1", st, "BACKUP_ARCHIVE")
        o.scope = scope
        return o

    def test_8a_later_observation_wins(self):
        chosen, _ = choose([self.obs("e1", "2026-05-01T00:00:00Z", "RESTORE_OPEN"),
                            self.obs("e2", "2026-05-10T00:00:00Z", "RESTORE_BLOCKED")], AUDIT_AT)
        self.assertEqual((chosen.file_id, chosen.state), ("e2", "RESTORE_BLOCKED"))
        chosen, _ = choose([self.obs("e1", "2026-05-01T00:00:00Z", "RESTORE_BLOCKED"),
                            self.obs("e2", "2026-05-10T00:00:00Z", "RESTORE_OPEN")], AUDIT_AT)
        self.assertEqual((chosen.file_id, chosen.state), ("e2", "RESTORE_OPEN"))

    def test_8b_same_time_comparable_sources_prefer_open_and_flag_ambiguity(self):
        chosen, info = choose([self.obs("e1", "2026-05-01T00:00:00Z", "RESTORE_BLOCKED"),
                               self.obs("e2", "2026-05-01T00:00:00Z", "RESTORE_OPEN")], AUDIT_AT)
        self.assertEqual(chosen.state, "RESTORE_OPEN")
        self.assertTrue(info.get("ambiguous"))

    def test_8c_unknown_does_not_beat_an_explicit_state_at_the_same_time(self):
        chosen, info = choose([self.obs("e1", "2026-05-01T00:00:00Z", "RESTORE_UNKNOWN"),
                               self.obs("e2", "2026-05-01T00:00:00Z", "RESTORE_OPEN")], AUDIT_AT)
        self.assertEqual(chosen.state, "RESTORE_OPEN")
        self.assertTrue(info.get("ambiguous"))

    def test_9a_after_cutoff_is_not_used(self):
        chosen, info = choose([self.obs("e1", "2026-05-01T00:00:00Z", "RESTORE_BLOCKED"),
                               self.obs("e2", "2026-06-01T00:00:00Z", "RESTORE_OPEN")], AUDIT_AT)
        self.assertEqual((chosen.file_id, chosen.state), ("e1", "RESTORE_BLOCKED"))
        self.assertEqual(info["excluded_after_cutoff"], 1)


# ----------------------------------------------------------------------------- end to end through main.run()
def write_csv(path: Path, header: list[str], rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=header)
        w.writeheader()
        w.writerows(rows)


def snapshot(store: str, collection: str, rec: dict) -> str:
    return json.dumps({"exported_at": "x", "source": "f1-test",
                       "snapshots": [{"data_store": store, "collection": collection, "records": [rec]}]})


class EndToEnd(unittest.TestCase):
    """Each case: one person, one request, evidence files written below; account steps are out of scope here."""

    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("ghost_main_f1", CODE / "main.py")
        cls.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.m)
        from validate_output import load_evidence_index, validate_text  # main.py put evaluation/ on sys.path
        cls.load_index, cls.validate = staticmethod(load_evidence_index), staticmethod(validate_text)

    def run_case(self, files: list[tuple[str, str, str, str]]):
        """files: (file_id, captured_at, suffix, content). Returns (status, steps, notes, validation)."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "evidence" / "records").mkdir(parents=True)
            shutil.copy(REPO / "dataset" / "deletion_rules.csv", d / "deletion_rules.csv")
            write_csv(d / "user_identities.csv", list(PERSON), [PERSON])
            write_csv(d / "user_audit_log.csv", ["audit_id", "user_id", "event_time", "field_name", "old_value", "new_value"], [])
            # Unrelated activity rows only teach the prefix -> system map (as the real stream does).
            act = [{"activity_id": f"activity_95{i}", "event_time": "2026-01-01T00:00:00Z", "event_type": "BACKUP_CREATED",
                    "source_system": "scheduler", "target_system": sysid, "resource_id": rid, "reported_result": "SUCCESS",
                    "details": "unrelated"} for i, (sysid, rid) in enumerate((("backup_service", "backup_9999"),
                                                                              ("integration_service", "data_flow_9999")))]
            write_csv(d / "system_activity.csv", ["activity_id", "event_time", "event_type", "source_system", "target_system",
                                                  "resource_id", "reported_result", "details"], act)
            man = []
            for fid, cap, suffix, content in files:
                rel = f"evidence/records/{fid}{suffix}"
                (d / rel).write_text(content, encoding="utf-8")
                man.append({"file_id": fid, "file_path": rel, "origin": "records_export", "captured_at": cap})
            write_csv(d / "evidence_files.csv", ["file_id", "file_path", "origin", "captured_at"], man)
            hdr = ["case_id", "email", "requested_at", "reported_status", "reported_at", "audit_at", "request_text"]
            req = {"case_id": "case_951", "email": PERSON["email"], "requested_at": "2026-04-28T09:00:00Z",
                   "reported_status": "COMPLETE", "reported_at": "2026-04-30T09:00:00Z", "audit_at": AUDIT_AT,
                   "request_text": "Please delete my account and all personal data you hold about me."}
            write_csv(d / "deletion_requests.csv", hdr, [req])
            write_csv(d / "sample_deletion_requests.csv", hdr, [])
            rows, meta = self.m.run(d, d / "deletion_requests.csv", [d / "deletion_requests.csv"], None, None)
            cid, status, sj = rows[0]
            text = "case_id,deletion_status,steps_json\n" + f'{cid},{status},"{sj.replace(chr(34), chr(34) * 2)}"\n'
            v = self.validate(text, {"case_951": req}, self.load_index(d))
            return status, json.loads(sj), meta["notes"]["case_951"], v

    def test_10a_restore_allowed_1_reports_risk_with_citation(self):
        st, steps, _, v = self.run_case([("evidence_951", "2026-05-01T09:00:00Z", ".sql", BACKUP_SQL.format(email=PERSON["email"], v="1"))])
        self.assertEqual(st, "INCOMPLETE")
        self.assertEqual(steps, [step(1, "FINDING", "REPORT_RESTORE_RISK", "backup_service", "backup_9501", "ACTIVE", "evidence_951"),
                                 step(2, "REMEDIATION", "BLOCK_RESTORE", "backup_service", "backup_9501", "BLOCKED"),
                                 step(3, "VERIFICATION", "VERIFY_RESTORE_BLOCKED", "backup_service", "backup_9501", "BLOCKED")])
        self.assertTrue(v.ok, [vars(i) for i in v.errors])

    def test_10b_restore_allowed_0_verifies_blocked_with_citation(self):
        st, steps, _, v = self.run_case([("evidence_951", "2026-05-01T09:00:00Z", ".sql", BACKUP_SQL.format(email=PERSON["email"], v="0"))])
        self.assertEqual((st, steps), ("COMPLETE", [step(1, "VERIFICATION", "VERIFY_RESTORE_BLOCKED", "backup_service",
                                                         "backup_9501", "BLOCKED", "evidence_951")]))
        self.assertTrue(v.ok, [vars(i) for i in v.errors])

    def test_10c_enabled_1_reports_active_flow_with_citation(self):
        st, steps, _, v = self.run_case([("evidence_951", "2026-05-01T09:00:00Z", ".sql", FLOW_SQL.format(email=PERSON["email"], v=1))])
        self.assertEqual(st, "INCOMPLETE")
        self.assertEqual(steps, [step(1, "FINDING", "REPORT_ACTIVE_DATA_FLOW", "integration_service", "data_flow_9501", "ACTIVE", "evidence_951"),
                                 step(2, "REMEDIATION", "DISABLE_DATA_FLOW", "integration_service", "data_flow_9501", "DISABLED"),
                                 step(3, "VERIFICATION", "VERIFY_DATA_FLOW_DISABLED", "integration_service", "data_flow_9501", "DISABLED")])
        self.assertTrue(v.ok, [vars(i) for i in v.errors])

    def test_10d_enabled_0_verifies_disabled_with_citation(self):
        st, steps, _, v = self.run_case([("evidence_951", "2026-05-01T09:00:00Z", ".sql", FLOW_SQL.format(email=PERSON["email"], v=0))])
        self.assertEqual((st, steps), ("COMPLETE", [step(1, "VERIFICATION", "VERIFY_DATA_FLOW_DISABLED", "integration_service",
                                                         "data_flow_9501", "DISABLED", "evidence_951")]))
        self.assertTrue(v.ok, [vars(i) for i in v.errors])

    def test_9b_open_restore_captured_after_audit_at_changes_nothing(self):
        blocked = snapshot("backup_service", "backup_restore_entries",
                           {"resource_id": "backup_9501", "customer_email": PERSON["email"], "restore_allowed": False})
        st, steps, _, v = self.run_case([("evidence_951", "2026-05-01T09:00:00Z", ".json", blocked),
                                         ("evidence_952", "2026-06-01T09:00:00Z", ".sql", BACKUP_SQL.format(email=PERSON["email"], v="1"))])
        self.assertEqual((st, steps), ("COMPLETE", [step(1, "VERIFICATION", "VERIFY_RESTORE_BLOCKED", "backup_service",
                                                         "backup_9501", "BLOCKED", "evidence_951")]))
        self.assertTrue(v.ok, [vars(i) for i in v.errors])

    def test_8d_later_integer_flag_overrides_earlier_boolean(self):
        open_json = snapshot("backup_service", "backup_restore_entries",
                             {"resource_id": "backup_9501", "customer_email": PERSON["email"], "restore_allowed": True})
        st, steps, _, _ = self.run_case([("evidence_951", "2026-05-01T09:00:00Z", ".json", open_json),
                                         ("evidence_952", "2026-05-10T09:00:00Z", ".sql", BACKUP_SQL.format(email=PERSON["email"], v="0"))])
        self.assertEqual((st, steps), ("COMPLETE", [step(1, "VERIFICATION", "VERIFY_RESTORE_BLOCKED", "backup_service",
                                                         "backup_9501", "BLOCKED", "evidence_952")]))

    def test_6d_unreadable_flag_is_never_cited_as_proof(self):
        bad = snapshot("backup_service", "backup_restore_entries",
                       {"resource_id": "backup_9501", "customer_email": PERSON["email"], "restore_allowed": None})
        st, steps, notes, v = self.run_case([("evidence_951", "2026-05-01T09:00:00Z", ".json", bad)])
        self.assertFalse([s for s in steps if s["evidence_id"] == "evidence_951"], steps)
        self.assertFalse([s for s in steps if s["phase"] == "FINDING"], steps)
        self.assertTrue(any(n.startswith("UNKNOWN flag state: backup_9501") for n in notes), notes)
        # How a COMPLETE row with an unproven verification is labelled is the separate open decision (D30 F2 / R12);
        # here the strict validator must flag it instead of accepting a false citation.
        if st == "COMPLETE":
            self.assertIn("R12", {i.rule for i in v.errors})


# ------------------------------------------------------------------------------- participant dataset (fixture)
class DatasetFlags(unittest.TestCase):
    def test_every_integer_flag_row_is_read_as_its_flag(self):
        """Generic: every SQL inventory row whose schema stores a 0/1 flag gets the matching state."""
        data = REPO / "dataset"
        want = {("restore_allowed", 1): "RESTORE_OPEN", ("restore_allowed", 0): "RESTORE_BLOCKED",
                ("enabled", 1): "FLOW_ACTIVE", ("enabled", 0): "FLOW_DISABLED"}
        checked = 0
        for e in ev.read_csv(data / "evidence_files.csv"):
            if not e["file_path"].endswith(".sql"):
                continue
            idx = ev.Index({})
            ev.parse_structured(idx, e, data)
            by_rid = {o.resource_id: o.state for o in idx.obs}
            con = sqlite3.connect(":memory:")
            con.executescript((data / e["file_path"]).read_text(encoding="utf-8"))
            for (t,) in con.execute("select name from sqlite_master where type='table'"):
                cur = con.execute(f'select * from "{t}"')
                cols = [c[0] for c in cur.description]
                for row in cur.fetchall():
                    rec = dict(zip(cols, row))
                    for fl in ("restore_allowed", "enabled"):
                        if type(rec.get(fl)) is int:
                            checked += 1
                            self.assertEqual(by_rid[rec["resource_id"]], want[(fl, rec[fl])], (e["file_id"], rec["resource_id"]))
        self.assertGreater(checked, 0)




class RestoreDecisionAndUnknown(unittest.TestCase):
    """EXP-D2 (D30 F3): explicit restore-authorization decisions; no signal means unknown, never blocked."""

    def test_decision_deny_is_blocked_allow_is_open_other_unknown(self):
        from ghostaudit.evidence import infer_state
        self.assertEqual(infer_state({"resource_id": "backup_1", "decision": "deny"}, None)[0], "RESTORE_BLOCKED")
        self.assertEqual(infer_state({"resource_id": "backup_1", "decision": "allow"}, None)[0], "RESTORE_OPEN")
        self.assertEqual(infer_state({"resource_id": "backup_1", "decision": "pending"}, None)[0], "RESTORE_UNKNOWN")

    def test_backup_or_flow_without_any_signal_is_unknown(self):
        from ghostaudit.evidence import infer_state
        self.assertEqual(infer_state({"resource_id": "backup_1", "tier": "Archive"}, "BACKUP_ARCHIVE")[0], "RESTORE_UNKNOWN")
        self.assertEqual(infer_state({"resource_id": "data_flow_1", "mode": "continuous"}, "DATA_FLOW")[0], "FLOW_UNKNOWN")

    def test_decision_field_on_other_resources_is_not_a_restore_state(self):
        from ghostaudit.evidence import infer_state
        self.assertNotIn(infer_state({"resource_id": "support_1", "decision": "deny", "email": "a@x.test"}, None)[0],
                         ("RESTORE_BLOCKED", "RESTORE_OPEN", "RESTORE_UNKNOWN"))


if __name__ == "__main__":
    unittest.main()
