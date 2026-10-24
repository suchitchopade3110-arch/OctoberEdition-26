"""Synthetic tests for the EXP-003 log parser (no dataset files needed).

Run: python -m unittest discover -s spike -p "test_exp003.py" -v
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import exp001 as base  # noqa: E402
import exp003 as E  # noqa: E402

EV = {"file_id": "evidence_t", "captured_at": "2026-05-10T00:00:00Z", "file_path": "x.log"}


def run(text: str, known=("account_service", "search_service", "support_platform", "integration_service")):
    E.KNOWN_SYSTEMS.clear()
    E.KNOWN_SYSTEMS.update(known)
    E.PARSE_STATS.clear()
    idx = base.Index({"account": "account_service", "search": "search_service", "support": "support_platform"})
    E.parse_log(idx, EV, text)
    return idx, E.PARSE_STATS["evidence_t"]


class TestFormats(unittest.TestCase):
    def test_escaped_message_format(self):
        idx, st = run('2026-05-01T10:00:00Z requestId=tr-1 level=INFO function=account_service message="instance=\\"a-1\\" '
                      'resource_id=\\"account_42\\" event=\\"profile_lookup_completed\\" rows=\\"0\\" http_status=\\"404\\""\n')
        self.assertEqual(st["ESCAPED"], 1)
        (o,) = idx.obs
        self.assertEqual((o.resource_id, o.system, o.state, o.explicit_absent), ("account_42", "account_service", "ABSENT", True))

    def test_json_line_format(self):
        idx, st = run('2026-05-01T10:00:00Z {"severity":"INFO","service":"search_service","trace_id":"tr-2",'
                      '"resource_id":"search_7","event":"index_query_completed","result":"hit"}\n')
        self.assertEqual(st["JSON"], 1)
        self.assertEqual([(o.resource_id, o.system) for o in idx.obs], [("search_7", "search_service")])

    def test_bracket_format_keeps_service_and_trace(self):
        text = ('2026-05-01T10:00:00Z [DEBUG] [account_service] [tr-3] profile_lookup_started: lookup_key="ann@x.io"\n'
                '2026-05-01T10:00:01Z [INFO] [account_service] [tr-3] profile_lookup_completed: resource_id="account_9" rows="1" http_status="200" email="ann@x.io"\n')
        idx, st = run(text)
        self.assertEqual(st["BRACKET"], 2)
        (o,) = idx.obs
        self.assertEqual(o.system, "account_service")
        self.assertIn("ann@x.io", o.keys)

    def test_plain_kv_unchanged(self):
        idx, st = run("2026-05-01T10:00:00Z level=INFO service=support_platform trace_id=rb-1 event=support_ticket_read_completed "
                      "resource_id=support_5 requester_email=bo@x.io\n")
        self.assertEqual(st["KV"], 1)
        self.assertEqual(idx.obs[0].state, "PRESENT_ID")


class TestStructure(unittest.TestCase):
    def test_multiline_record_is_joined(self):
        text = ('2026-05-01T10:00:00Z {"service":"search_service","trace_id":"tr-4",\n'
                '   "resource_id":"search_8","event":"index_query_completed","result":"hit"}\n')
        idx, st = run(text)
        self.assertEqual(st["JSON"], 1)
        self.assertEqual(idx.obs[0].resource_id, "search_8")
        self.assertEqual(idx.obs[0].line, 1)

    def test_trace_join_brings_subject_key_to_resource_line(self):
        text = ('2026-05-01T10:00:00Z {"service":"account_service","trace_id":"tr-5","event":"profile_lookup_started","lookup_key":"cy@x.io"}\n'
                '2026-05-01T10:00:02Z {"service":"account_service","trace_id":"tr-5","resource_id":"account_3","event":"profile_lookup_completed","rows":"1"}\n')
        idx, _ = run(text)
        self.assertIn("cy@x.io", idx.obs[0].keys)

    def test_trace_join_does_not_cross_traces(self):
        text = ('2026-05-01T10:00:00Z {"service":"account_service","trace_id":"tr-6","event":"profile_lookup_started","lookup_key":"dee@x.io"}\n'
                '2026-05-01T10:00:02Z {"service":"account_service","trace_id":"tr-7","resource_id":"account_4","event":"profile_lookup_completed","rows":"1"}\n')
        idx, _ = run(text)
        self.assertNotIn("dee@x.io", idx.obs[0].keys)

    def test_line_without_resource_id_creates_nothing(self):
        idx, st = run('2026-05-01T10:00:00Z requestId=vault-1 level=INFO function=secret_agent message="event=\\"lease_extended\\" ttl_seconds=\\"9\\""\n')
        self.assertEqual(idx.obs, [])
        self.assertEqual(st["ESCAPED"], 1)

    def test_exact_duplicate_is_counted_once(self):
        line = '2026-05-01T10:00:00Z {"service":"search_service","trace_id":"tr-8","resource_id":"search_9","event":"index_query_completed","result":"hit"}\n'
        idx, st = run(line + line)
        self.assertEqual(len(idx.obs), 1)
        self.assertEqual(st["duplicate"], 1)

    def test_conflicting_observations_are_both_kept_and_reported(self):
        text = ('2026-05-01T10:00:00Z {"service":"account_service","trace_id":"t1","resource_id":"account_5","event":"profile_lookup_completed","rows":"0","http_status":"404"}\n'
                '2026-05-03T10:00:00Z {"service":"account_service","trace_id":"t2","resource_id":"account_5","event":"profile_lookup_completed","rows":"1","http_status":"200","email":"e@x.io"}\n')
        idx, _ = run(text)
        self.assertEqual(sorted(o.state for o in idx.obs), ["ABSENT", "PRESENT_ID"])
        self.assertEqual(E.conflicts(idx), [{"file_id": "evidence_t", "resource_id": "account_5", "states": ["ABSENT", "PRESENT_ID"]}])
        self.assertEqual([o.observed_at for o in idx.obs], ["2026-05-01T10:00:00Z", "2026-05-03T10:00:00Z"])

    def test_provenance_keeps_file_capture_time(self):
        idx, _ = run('2026-05-01T10:00:00Z {"service":"search_service","resource_id":"search_1","event":"x","result":"hit"}\n')
        self.assertEqual((idx.obs[0].file_id, idx.obs[0].captured_at), ("evidence_t", "2026-05-10T00:00:00Z"))


class TestRobustness(unittest.TestCase):
    def test_malformed_lines_are_skipped_and_counted(self):
        text = ('2026-05-01T10:00:00Z {"service":"search_service","resource_id":"search_2",\n'  # broken JSON (never closed)
                'not a log line at all\n'
                '2026-05-01T10:00:05Z {"service":"search_service","resource_id":"search_3","event":"x","result":"hit"}\n')
        idx, st = run(text)
        self.assertEqual([o.resource_id for o in idx.obs], ["search_3"])
        self.assertEqual(st["malformed"], 1)

    def test_orphan_text_before_first_record_is_malformed(self):
        idx, st = run('garbage header\n2026-05-01T10:00:05Z {"service":"search_service","resource_id":"search_4","event":"x","result":"hit"}\n')
        self.assertEqual(st["malformed"], 1)
        self.assertEqual(len(idx.obs), 1)

    def test_id_inside_path_or_reference_field_is_not_a_resource(self):
        # Only the resource_id field creates an observation; ids inside other values do not.
        idx, _ = run('2026-05-01T10:00:00Z level=INFO service=support_platform event=attachment_scan resource_id=support_7 '
                     'archive_key=archive/customer-data/backup_99.tar.zst source_resource_id=account_77\n')
        self.assertEqual([o.resource_id for o in idx.obs], ["support_7"])

    def test_unknown_emitter_is_not_used_as_system(self):
        idx, st = run('2026-05-01T10:00:00Z requestId=tr-9 level=DEBUG function=profile_service message="resource_id=\\"account_8\\" '
                      'event=\\"profile_lookup_completed\\" rows=\\"1\\""\n')
        self.assertEqual(idx.obs[0].system, "account_service")  # baseline prefix fallback, not "profile_service"
        self.assertEqual(st["emitter_not_system"], 1)

    def test_unrelated_user_record_keeps_only_its_own_keys(self):
        idx, _ = run('2026-05-01T10:00:00Z {"service":"support_platform","trace_id":"tr-10","resource_id":"support_9",'
                     '"event":"message_pii_scan","matched_value":"zed@x.io"}\n')
        self.assertEqual(idx.obs[0].keys & {"ann@x.io", "cy@x.io"}, set())
        self.assertIn("zed@x.io", idx.obs[0].keys)


class TestCutoff(unittest.TestCase):
    def test_observation_from_late_file_is_not_used(self):
        idx, _ = run('2026-05-01T10:00:00Z {"service":"search_service","resource_id":"search_5","event":"x","result":"hit"}\n')
        a = base.Auditor.__new__(base.Auditor)
        a.obs_by_res = {"search_5": idx.obs}
        self.assertIsNone(a.latest("search_5", "2026-05-09T23:59:59Z"))  # file captured 2026-05-10
        self.assertIsNotNone(a.latest("search_5", "2026-05-10T00:00:00Z"))  # inclusive boundary


if __name__ == "__main__":
    unittest.main(verbosity=2)
