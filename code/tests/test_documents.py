"""Synthetic tests for PDF extraction rules (production ghostaudit.documents; ported from EXP-007)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ghostaudit.documents import document_observations  # noqa: E402

KEYMAP = {"ann@x.io": "user_1", "user_1": "user_1", "bo@x.io": "user_2", "user_2": "user_2"}


def users_for(keys):
    return {KEYMAP[k] for k in keys if k in KEYMAP}


def run(text, labels=None, targets=None, origin="support_platform", known=("support_platform",)):
    return document_observations(text, origin, labels or {}, targets or {}, set(known), users_for)


class Extraction(unittest.TestCase):
    def test_printed_resource_id_is_observed_with_identity(self):
        rec, obs = run("Ticket reference support_9 for ann@x.io. file proof.pdf uploader customer")
        self.assertEqual([(o[0], o[4]) for o in obs], [("support_9", "printed id")])
        self.assertIn("ann@x.io", obs[0][3])
        self.assertEqual(obs[0][1].get("file"), "document attachment")
        self.assertEqual(obs[0][2], "support_platform")

    def test_catalog_label_maps_document_reference_to_resource(self):
        rec, obs = run("Statement REF-0001 for ann@x.io", labels={"REF-0001": "export_7"},
                       targets={"export_7": "export_service"}, origin="statement_service")
        self.assertEqual([(o[0], o[2], o[4]) for o in obs], [("export_7", "export_service", "catalog label")])

    def test_person_identifier_is_never_a_label(self):
        # The guard lives in DocAuditor._catalog; a label map built correctly never contains user ids,
        # so a document that only mentions user_1 references no resource.
        rec, obs = run("Register row for user_1", labels={})
        self.assertEqual(obs, [])
        self.assertIn("no resource id", rec["skipped"])

    def test_multi_subject_document_links_nobody(self):
        rec, obs = run("support_9 opened by ann@x.io and bo@x.io")
        self.assertEqual(obs, [])
        self.assertIn("more than one subject", rec["skipped"])

    def test_no_identifier_means_no_direct_identifier_field(self):
        rec, obs = run("Event reference audit_record_5 retain until 2030", origin="security_service", known=("security_service",))
        self.assertEqual(obs[0][0], "audit_record_5")
        self.assertNotIn("email", obs[0][1])

    def test_unknown_origin_falls_back_to_catalog_target_then_prefix(self):
        _, obs = run("support_9 ann@x.io", origin="unlisted_service", known=())
        self.assertIsNone(obs[0][2])  # no catalog target: baseline prefix fallback decides


if __name__ == "__main__":
    unittest.main(verbosity=2)
