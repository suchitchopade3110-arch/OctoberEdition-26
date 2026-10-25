"""Evidence cache and no-key behaviour (D18). No network: live extraction is exercised only with keys absent."""
from __future__ import annotations

import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

CODE = Path(__file__).resolve().parents[1]
ROOT = CODE.parent
sys.path.insert(0, str(CODE))
from ghostaudit import evidence_cache  # noqa: E402

SHIPPED = CODE / "evidence_cache"


def entry(sha="ab" * 32, model="m", pv="p", facts=None, errs=None):
    return {"file_id": "evidence_x", "file_path": "evidence/images/x.png", "origin": "o", "captured_at": "2026-01-01T00:00:00Z",
            "sha256": sha, "model": model, "prompt_version": pv, "schema_errors": errs or [],
            "facts": facts if facts is not None else {"records": []}, "attempts": [{"error": "secret-should-not-survive"}]}


class Cache(unittest.TestCase):
    def test_roundtrip_and_index(self):
        with tempfile.TemporaryDirectory() as d:
            evidence_cache.write_entry(Path(d), entry())
            got, notes = evidence_cache.lookup(Path(d), "ab" * 32)
            self.assertEqual(got["model"], "m"); self.assertEqual(evidence_cache.verify_index(Path(d)), [])
            self.assertNotIn("attempts", got)                       # attempt logs are never stored

    def test_miss_and_invalid_entries(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(evidence_cache.lookup(Path(d), "cd" * 32), (None, ["cache miss"]))
            evidence_cache.write_entry(Path(d), entry(errs=["bad"]))
            self.assertIsNone(evidence_cache.lookup(Path(d), "ab" * 32)[0])

    def test_tampered_entry_detected(self):
        with tempfile.TemporaryDirectory() as d:
            p = evidence_cache.write_entry(Path(d), entry())
            p.write_text(p.read_text(encoding="utf-8").replace('"m"', '"m2"'), encoding="utf-8")
            self.assertTrue(any("modified" in x for x in evidence_cache.verify_index(Path(d))))

    def test_deterministic_choice_between_entries(self):
        with tempfile.TemporaryDirectory() as d:
            evidence_cache.write_entry(Path(d), entry(model="a", pv="v1"))
            evidence_cache.write_entry(Path(d), entry(model="b", pv="v2"))
            self.assertEqual(evidence_cache.lookup(Path(d), "ab" * 32)[0]["prompt_version"], "v2")


class Shipped(unittest.TestCase):
    def test_shipped_cache_integrity_and_hygiene(self):
        self.assertEqual(evidence_cache.verify_index(SHIPPED), [])
        blob = "".join(p.read_text(encoding="utf-8") for p in SHIPPED.rglob("*.json"))
        self.assertNotIn('"attempts"', blob)
        self.assertIsNone(re.search(r"AIza[0-9A-Za-z_-]{20,}|AQ\.[0-9A-Za-z_-]{20,}", blob))   # no API-key shapes

    def test_shipped_entries_match_current_dataset_files(self):
        for row in json.loads((SHIPPED / "index.json").read_text(encoding="utf-8")):
            e = json.loads((SHIPPED / row["entry"]).read_text(encoding="utf-8"))
            self.assertEqual(evidence_cache.sha256_file(ROOT / "dataset" / e["file_path"]), e["sha256"])


class NoKey(unittest.TestCase):
    def test_cache_miss_adds_no_observation_and_never_absent(self):
        from ghostaudit.multimodal import MultimodalAuditor
        with tempfile.TemporaryDirectory() as d:
            aud = MultimodalAuditor(ROOT / "dataset", Path(d), use_ocr=False)   # the no-OCR guarantee
            self.assertTrue(all(r.get("status", "").startswith("unresolved") for r in aud.image_report))
            self.assertFalse([o for o in aud.idx.obs if str(getattr(o, "extraction", "")).startswith("image:")])

    def test_ocr_fallback_on_cache_miss_never_produces_absence(self):
        # EXP-D1: with no fact entry, OCR facts may add PRESENT observations, never ABSENT / deleted.
        from ghostaudit.multimodal import MultimodalAuditor
        with tempfile.TemporaryDirectory() as d:
            aud = MultimodalAuditor(ROOT / "dataset", Path(d))
            img = [o for o in aud.idx.obs if str(getattr(o, "extraction", "")).startswith("image:ocr")]
            self.assertTrue(all(o.state != "ABSENT" for o in img))

    def test_live_extraction_without_keys_makes_no_call(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("ghost_main", CODE / "main.py")
        entry_main = importlib.util.module_from_spec(spec); spec.loader.exec_module(entry_main)
        from ghostaudit import gemini
        orig = gemini.load_config
        def no_keys():
            c = orig(); c["keys"] = {s: "" for s in gemini.SLOTS}; return c
        gemini.load_config = no_keys
        try:
            with tempfile.TemporaryDirectory() as d:
                out = entry_main.live_extract(ROOT / "dataset", Path(d))
            self.assertEqual(out["attempted"], []); self.assertIn("no key", out["skipped"])
        finally:
            gemini.load_config = orig


if __name__ == "__main__":
    unittest.main()
