"""Offline tests for image grounding, per-row linking, the evidence cache and the opt-in Gemini client
(production ghostaudit; ported from EXP-007G). No network, no real key; synthetic people and ids."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ghostaudit import evidence_cache  # noqa: E402
from ghostaudit import gemini as gx  # noqa: E402
from ghostaudit.images import flow_state_from_text, ground_record, link_rows, usable_state  # noqa: E402


def rec(**kw):
    base = {"resource_id": "", "system_id": "", "subject_identifiers": [], "visible_status_text": "", "state": "UNCLEAR",
            "state_basis": "NONE", "restore_or_flow_detail": "", "supporting_text": [], "uncertainty": ""}
    base.update(kw)
    return base


def facts(records):
    return {"screen_title": "t", "displayed_timestamps": [], "records": records, "embedded_instructions_seen": False,
            "ambiguities": []}


class Schema(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(gx.validate(facts([rec()])), [])

    def test_bad_enum_and_missing(self):
        r = rec(state="DELETED")
        del r["uncertainty"]
        errs = gx.validate(facts([r]))
        self.assertTrue(any("not in enum" in e for e in errs) and any("uncertainty: missing" in e for e in errs))


class Grounding(unittest.TestCase):
    known = {"search_428", "backup_9287"}

    def test_printed_known_id(self):
        r = rec(resource_id="search_428", supporting_text=["Document search_428 not found"])
        self.assertEqual(ground_record(r, self.known, {}), ("search_428", "printed id"))

    def test_hallucinated_unknown_id_rejected(self):
        r = rec(resource_id="search_999", supporting_text=["search_999"])
        self.assertIsNone(ground_record(r, self.known, {})[0])

    def test_id_not_in_own_text_rejected(self):
        r = rec(resource_id="search_428", supporting_text=["No results"])
        self.assertIsNone(ground_record(r, self.known, {})[0])

    def test_misplaced_id_field_recovered_from_own_text(self):
        r = rec(resource_id="user_7", supporting_text=["ID: user_7", "Analytics ID: search_428"])
        rid, how = ground_record(r, self.known, {})
        self.assertEqual(rid, "search_428"); self.assertIn("id field held 'user_7'", how)

    def test_misplaced_id_field_two_candidates_rejected(self):
        r = rec(resource_id="user_7", supporting_text=["search_428", "backup_9287"])
        self.assertIsNone(ground_record(r, self.known, {})[0])

    def test_misplaced_id_field_unknown_candidate_rejected(self):
        r = rec(resource_id="user_7", supporting_text=["search_999"])
        self.assertIsNone(ground_record(r, self.known, {})[0])

    def test_catalog_label(self):
        r = rec(supporting_text=["Archive BK-77 restore window"])
        self.assertEqual(ground_record(r, self.known, {"BK-77": "backup_9287"}), ("backup_9287", "catalog label"))


class States(unittest.TestCase):
    def test_graphic_only_needs_review(self):
        f, why = usable_state(rec(state="FLOW_DISABLED", state_basis="GRAPHICAL_INDICATOR"))
        self.assertIsNone(f)
        self.assertIn("human review", why)

    def test_unclear_never_absent(self):
        self.assertEqual(usable_state(rec(state="UNCLEAR", state_basis="NONE"))[0], None)

    def test_state_must_fit_resource_type(self):
        f, why = usable_state(rec(state="PRESENT_WITH_IDENTIFIERS", state_basis="VISIBLE_TEXT"), "data_flow_7")
        self.assertIsNone(f); self.assertIn("does not fit", why)
        self.assertIsNotNone(usable_state(rec(state="FLOW_ENABLED", state_basis="VISIBLE_TEXT"), "data_flow_7")[0])

    def test_text_not_found(self):
        self.assertEqual(usable_state(rec(state="NOT_FOUND", state_basis="VISIBLE_TEXT"))[0], {"result": "not_found"})


class Safety(unittest.TestCase):
    def test_placeholder_key_detected(self):
        self.assertEqual(gx.key_status({"key": "YOUR_API_KEY_HERE"}), "missing or placeholder")
        self.assertEqual(gx.key_status("x" * 39), "present")

    def test_budget_hard_stop(self):
        with tempfile.TemporaryDirectory() as d:
            led = gx.Ledger(Path(d), 2)
            led.record({}); led.record({})
            with self.assertRaises(gx.BudgetExceeded):
                led.reserve()

    def test_redact(self):
        self.assertNotIn("SECRET123", gx.redact("bad key SECRET123", ["SECRET123", ""]))


# ------------------------------------------------------------------ mocked failover (no network, fake keys)
import json as _json


class FakeErr(Exception):
    def __init__(self, code, status, message, retry_after=None):
        super().__init__(message)
        self.code, self.status, self.message = code, status, message
        self.response = type("R", (), {"headers": {"retry-after": str(retry_after)} if retry_after is not None else {}})()
        self.details = None


GOOD = _json.dumps(facts([rec()]))


class Failover(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = {"keys": {"PRIMARY": "fake-key-A", "FALLBACK_1": "fake-key-B", "FALLBACK_2": "fake-key-C"},
                    "model": "m", "temperature": 0, "timeout_s": 1, "cache_dir": Path(self.tmp.name),
                    "price_in": None, "price_out": None}
        self.row = gx.png_manifest()[0]
        self.sleeps = []

    def tearDown(self):
        self.tmp.cleanup()

    def run_with(self, script, max_attempts=11):
        seq = list(script)
        used = []

        def call(key, cfg, image):
            used.append(key)
            item = seq.pop(0)
            if isinstance(item, Exception):
                raise item
            return item, {"prompt_token_count": 10, "candidates_token_count": 5}, "m-001", None
        led = gx.Ledger(Path(self.tmp.name), max_attempts)
        out = gx.extract(self.row, self.cfg, led, call=call, sleep=self.sleeps.append)
        return out, used, led

    def test_success_primary(self):
        out, used, led = self.run_with([GOOD])
        self.assertFalse(out["extraction_failed"]); self.assertEqual(used, ["fake-key-A"]); self.assertEqual(led.count(), 1)

    def test_invalid_key_fails_over(self):
        out, used, _ = self.run_with([FakeErr(400, "INVALID_ARGUMENT", "API key not valid. Please pass a valid API key."), GOOD])
        self.assertFalse(out["extraction_failed"]); self.assertEqual(used, ["fake-key-A", "fake-key-B"])
        self.assertEqual(out["attempts"][0]["category"], "credential"); self.assertEqual(out["key_slot"], "FALLBACK_1")

    def test_project_restriction_does_not_fail_over(self):
        out, used, _ = self.run_with([FakeErr(403, "PERMISSION_DENIED", "Generative Language API has not been used in project 1 or it is disabled")])
        self.assertTrue(out["extraction_failed"]); self.assertEqual(used, ["fake-key-A"])
        self.assertEqual(out["failure_category"], "project_restriction")

    def test_quota_does_not_rotate_keys(self):
        out, used, _ = self.run_with([FakeErr(429, "RESOURCE_EXHAUSTED", "You exceeded your current quota, please check your plan and billing")])
        self.assertTrue(out["extraction_failed"]); self.assertEqual(used, ["fake-key-A"])

    def test_429_rate_limit_backs_off_with_retry_after(self):
        out, used, _ = self.run_with([FakeErr(429, "RESOURCE_EXHAUSTED", "rate limit per minute", retry_after=7), GOOD])
        self.assertFalse(out["extraction_failed"]); self.assertEqual(used, ["fake-key-A", "fake-key-A"]); self.assertEqual(self.sleeps, [7.0])

    def test_503_exponential_then_gives_up_without_rotating(self):
        e = FakeErr(503, "UNAVAILABLE", "overloaded")
        out, used, led = self.run_with([e, e, e])
        self.assertTrue(out["extraction_failed"]); self.assertEqual(used, ["fake-key-A"] * 3)
        self.assertEqual(self.sleeps, [2.0, 4.0]); self.assertEqual(led.count(), 3)

    def test_malformed_and_policy_not_retried(self):
        out, used, _ = self.run_with([FakeErr(400, "INVALID_ARGUMENT", "Invalid JSON payload received")])
        self.assertEqual((out["failure_category"], used), ("malformed_request", ["fake-key-A"]))
        out, used, _ = self.run_with([FakeErr(400, "INVALID_ARGUMENT", "content blocked for SAFETY")])
        self.assertEqual((out["failure_category"], used), ("content_policy", ["fake-key-A"]))

    def test_all_keys_invalid_structured_failure(self):
        bad = lambda: FakeErr(401, "UNAUTHENTICATED", "API key not valid")  # noqa: E731
        out, used, _ = self.run_with([bad(), bad(), bad()])
        self.assertTrue(out["extraction_failed"]); self.assertEqual(out["failure_category"], "no_usable_key")
        self.assertIsNone(out["facts"]); self.assertEqual(len(used), 3)

    def test_budget_counts_retries_and_stops(self):
        e = FakeErr(503, "UNAVAILABLE", "overloaded")
        with self.assertRaises(gx.BudgetExceeded):
            self.run_with([e, e, e], max_attempts=2)

    def test_schema_invalid_not_cached(self):
        out, _, _ = self.run_with(['{"records": 3}'])
        self.assertTrue(out["extraction_failed"]); self.assertEqual(list(Path(self.tmp.name).glob("*/*.json")), [])

    def test_keys_never_in_ledger_or_cache(self):
        self.run_with([FakeErr(400, "INVALID_ARGUMENT", "API key not valid: fake-key-A"), GOOD])
        blob = "".join(p.read_text(encoding="utf-8") for p in Path(self.tmp.name).rglob("*") if p.is_file())
        for k in self.cfg["keys"].values():
            self.assertNotIn(k, blob)
        self.assertIn("PRIMARY", blob)

    def test_deadline_not_retried_with_same_deadline(self):
        out, used, led = self.run_with([FakeErr(504, "DEADLINE_EXCEEDED", "Deadline expired before operation could complete.")])
        self.assertEqual((out["failure_category"], used, led.count()), ("deadline_exceeded", ["fake-key-A"], 1))

    def test_generation_kwargs_omit_unset(self):
        kw = gx.generation_kwargs({"temperature": None, "max_output_tokens": None, "thinking_level": None})
        self.assertNotIn("temperature", kw); self.assertNotIn("thinking_config", kw)
        kw = gx.generation_kwargs({"temperature": None, "max_output_tokens": 4096, "thinking_level": "LOW"})
        self.assertEqual(kw["max_output_tokens"], 4096); self.assertEqual(str(kw["thinking_config"].thinking_level.value), "LOW")

    def test_duplicate_key_not_a_second_slot(self):
        self.cfg["keys"]["FALLBACK_1"] = "fake-key-A"
        self.assertEqual(gx.usable_slots(self.cfg), ["PRIMARY", "FALLBACK_2"])


# ------------------------------------------------------------------ per-row linking (synthetic people)
PEOPLE = {"ann@x.test": "u_ann", "user_ann": "u_ann", "bob@x.test": "u_bob", "user_bob": "u_bob"}


def users_for(keys):
    return {PEOPLE[k] for k in keys if k in PEOPLE}


class RowLinking(unittest.TestCase):
    def test_1_two_people_separate_rows(self):
        mode, rows = link_rows([rec(resource_id="search_1", subject_identifiers=["ann@x.test"]),
                                rec(resource_id="search_2", subject_identifiers=["bob@x.test"])], users_for)
        self.assertEqual(mode, "per_row")
        self.assertEqual([u for _, u, _ in rows], [{"u_ann"}, {"u_bob"}])

    def test_2_lookalike_email_links_nobody(self):
        mode, rows = link_rows([rec(resource_id="search_1", subject_identifiers=["ann@x.test"]),
                                rec(resource_id="search_2", subject_identifiers=["bob@x.test"]),
                                rec(resource_id="search_3", subject_identifiers=["ann.jr@x.test"])], users_for)
        self.assertEqual(rows[2][1], set()); self.assertIn("no identifier", rows[2][2])

    def test_3_row_without_identity_unresolved(self):
        _, rows = link_rows([rec(resource_id="search_1", subject_identifiers=["ann@x.test"]),
                             rec(resource_id="search_2", subject_identifiers=["bob@x.test"]),
                             rec(resource_id="search_4")], users_for)
        self.assertEqual(rows[2][1], set())

    def test_4_conflicting_identities_in_one_row(self):
        _, rows = link_rows([rec(resource_id="search_1", subject_identifiers=["ann@x.test", "user_bob"]),
                             rec(resource_id="search_2", subject_identifiers=["bob@x.test"])], users_for)
        self.assertEqual(rows[0][1], set()); self.assertIn("2 different people", rows[0][2])
        self.assertEqual(rows[1][1], {"u_bob"})

    def test_8_duplicate_resource_id_different_people(self):
        _, rows = link_rows([rec(resource_id="search_1", subject_identifiers=["ann@x.test"]),
                             rec(resource_id="search_1", subject_identifiers=["bob@x.test"])], users_for)
        self.assertTrue(all(u == set() and "same resource id" in why for _, u, why in rows))

    def test_unknown_person_on_row_is_not_linked_by_resource_id(self):
        # The row shows an email/phone of nobody known: never attach it to the resource's catalog owner.
        mode, rows = link_rows([rec(resource_id="marketing_9", subject_identifiers=["stranger@x.test", "+1 555 010 9999"])], users_for)
        self.assertEqual(mode, "single"); self.assertEqual(rows[0][1], set()); self.assertIn("matches no known person", rows[0][2])

    def test_row_without_any_person_identifier_still_links_by_resource(self):
        mode, rows = link_rows([rec(resource_id="search_1", subject_identifiers=[])], users_for)
        self.assertEqual(rows[0][2], "single-subject screenshot")

    def test_single_person_screenshot_unchanged(self):
        mode, rows = link_rows([rec(resource_id="search_1", subject_identifiers=["ann@x.test"]),
                                rec(resource_id="search_2")], users_for)
        self.assertEqual(mode, "single")


class FlowState(unittest.TestCase):
    def test_5_active_and_disabled(self):
        self.assertEqual(flow_state_from_text(rec(visible_status_text="Running"))[0], {"enabled": True})
        self.assertEqual(flow_state_from_text(rec(visible_status_text="Paused"))[0], {"enabled": False})

    def test_selector_email_is_not_a_flow_state(self):
        r = rec(state="PRESENT_WITH_IDENTIFIERS", state_basis="VISIBLE_TEXT", subject_identifiers=["ann@x.test"],
                supporting_text=["ann@x.test"])
        self.assertIsNone(flow_state_from_text(r)[0])

    def test_mode_alone_is_not_active(self):
        f, why = flow_state_from_text(rec(restore_or_flow_detail="Continuous"))
        self.assertIsNone(f); self.assertIn("only a sync mode", why)
        self.assertIsNone(flow_state_from_text(rec(visible_status_text="Scheduled", restore_or_flow_detail="Continuous sync"))[0])

    def test_health_alone_is_not_active(self):
        self.assertIsNone(flow_state_from_text(rec(visible_status_text="Healthy"))[0])

    def test_health_plus_mode_same_row_is_active(self):
        f, why = flow_state_from_text(rec(visible_status_text="Healthy", restore_or_flow_detail="Continuous sync"))
        self.assertEqual(f, {"enabled": True}); self.assertIn("same row", why)

    def test_health_word_only_counts_in_status_field(self):
        self.assertIsNone(flow_state_from_text(rec(restore_or_flow_detail="Continuous; destination healthy"))[0])

    def test_explicit_status_beats_need_for_mode(self):
        self.assertEqual(flow_state_from_text(rec(visible_status_text="Running"))[0], {"enabled": True})
        self.assertEqual(flow_state_from_text(rec(visible_status_text="Paused", restore_or_flow_detail="Continuous"))[0],
                         {"enabled": False})

    def test_disabled_with_health_conflicts(self):
        self.assertIsNone(flow_state_from_text(rec(visible_status_text="Healthy", restore_or_flow_detail="Disabled"))[0])

    def test_conflicting_words_unresolved(self):
        self.assertIsNone(flow_state_from_text(rec(visible_status_text="Active", restore_or_flow_detail="Paused"))[0])

    def test_6_graphic_only_state_not_used(self):
        r = rec(state="FLOW_DISABLED", state_basis="GRAPHICAL_INDICATOR", visible_status_text="")
        self.assertIsNone(flow_state_from_text(r)[0])                 # toggle drawn, no printed word
        self.assertIsNone(usable_state(r, "search_1")[0])


class Integration(unittest.TestCase):
    """Real dataset + a synthetic cache: identities and resource ids are chosen at run time, not hardcoded."""

    @classmethod
    def setUpClass(cls):
        import csv, json, hashlib
        from ghostaudit.multimodal import MultimodalAuditor
        root = Path(__file__).resolve().parents[2]
        data = root / "dataset"
        with open(data / "user_identities.csv", encoding="utf-8") as fh:
            idents = list(csv.DictReader(fh))
        cls.a, cls.b = idents[0], idents[1]
        row = gx.png_manifest()[0]
        cls.row = row
        cls.tmp = tempfile.TemporaryDirectory()
        probe = MultimodalAuditor(data, Path(cls.tmp.name))
        flows = sorted(r for r in probe.obs_by_res if r.startswith("data_flow_"))
        cls.ra, cls.rb = flows[0], flows[1]
        f = facts([rec(resource_id=cls.ra, subject_identifiers=[cls.a["email"]], visible_status_text="Running",
                       supporting_text=[cls.ra, cls.a["email"]]),
                   rec(resource_id=cls.rb, subject_identifiers=[cls.b["email"]], visible_status_text="Disabled",
                       supporting_text=[cls.rb, cls.b["email"]])])
        sha = hashlib.sha256((data / row["file_path"]).read_bytes()).hexdigest()
        evidence_cache.write_entry(Path(cls.tmp.name), {"file_id": row["file_id"], "file_path": row["file_path"],
                                   "origin": row["origin"], "captured_at": row["captured_at"], "sha256": sha,
                                   "model": "m", "prompt_version": "p", "schema_errors": [], "facts": f})
        cls.aud = MultimodalAuditor(data, Path(cls.tmp.name))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def mine(self, rid):
        return [o for o in self.aud.obs_by_res[rid] if o.file_id == self.row["file_id"]]

    def test_no_cross_user_contamination(self):
        oa, ob = self.mine(self.ra), self.mine(self.rb)
        self.assertEqual(len(oa), 1); self.assertEqual(len(ob), 1)
        self.assertEqual((oa[0].state, ob[0].state), ("FLOW_ACTIVE", "FLOW_DISABLED"))
        self.assertFalse(oa[0].keys & self.aud.keys[self.b["user_id"]])
        self.assertFalse(ob[0].keys & self.aud.keys[self.a["user_id"]])

    def test_7_evidence_after_audit_at_ignored(self):
        cap = self.row["captured_at"]
        before = cap[:4] + "-01-01T00:00:00Z" if cap[5:7] != "01" else str(int(cap[:4]) - 1) + "-12-31T00:00:00Z"
        chosen = self.aud.latest(self.ra, before)
        self.assertTrue(chosen is None or chosen.file_id != self.row["file_id"])
        self.assertEqual(self.aud.latest(self.ra, "2099-01-01T00:00:00Z").file_id, self.row["file_id"])


# ------------------------------------------------------------------ compact profile (offline)
def compact(records):
    return {"records": records, "embedded_instructions_seen": False}


def crec(**kw):
    base = {"resource_id": "", "visible_text": [], "identity": [], "state": "UNCLEAR", "state_basis": "NONE",
            "timestamp": "", "uncertainty": ""}
    base.update(kw)
    return base


class Compact(unittest.TestCase):
    def test_schema_valid_and_invalid(self):
        self.assertEqual(gx.validate(compact([crec()]), gx.COMPACT_SCHEMA), [])
        self.assertTrue(gx.validate({"records": [{"resource_id": "x"}]}, gx.COMPACT_SCHEMA))

    def test_adapter_keeps_status_field_rule(self):
        full = gx.compact_to_full(compact([crec(resource_id="data_flow_7",
                                                visible_text=["ID: data_flow_7", "Status: Healthy", "Mode: Continuous"])]))
        r = full["records"][0]
        self.assertEqual((r["visible_status_text"], r["restore_or_flow_detail"]), ("Healthy", "Continuous"))
        self.assertEqual(gx.validate(full), [])
        self.assertEqual(flow_state_from_text(r)[0], {"enabled": True})
        # "healthy" in a non-status field never counts as status
        r2 = gx.compact_to_full(compact([crec(visible_text=["Destination health note: healthy", "Mode: Continuous"])]))["records"][0]
        self.assertIsNone(flow_state_from_text(r2)[0])
        r3 = gx.compact_to_full(compact([crec(visible_text=["Destination health: Healthy", "Sync mode: Continuous sync"])]))["records"][0]
        self.assertEqual(r3["visible_status_text"], ""); self.assertIsNone(flow_state_from_text(r3)[0])
        r4 = gx.compact_to_full(compact([crec(visible_text=["Connector status: Healthy", "Sync mode: Continuous sync"])]))["records"][0]
        self.assertEqual(flow_state_from_text(r4)[0], {"enabled": True})

    def test_adapter_unlabelled_text_is_support_only(self):
        r = gx.compact_to_full(compact([crec(visible_text=["Running"])]))["records"][0]
        self.assertEqual(r["visible_status_text"], ""); self.assertEqual(r["supporting_text"], ["Running"])

    def test_request_is_smaller_and_sdk_accepts_it(self):
        import json as j
        from google.genai import types
        kw = gx.generation_kwargs({"profile": "compact", "temperature": None, "max_output_tokens": 2048, "thinking_level": "LOW"})
        types.GenerateContentConfig(**kw)                     # pydantic validation, no network
        self.assertLess(len(j.dumps(gx.COMPACT_SCHEMA)) + len(gx.COMPACT_INSTRUCTION),
                        len(j.dumps(gx.SCHEMA)) + len(gx.SYSTEM_INSTRUCTION))
        self.assertEqual(kw["response_json_schema"], gx.COMPACT_SCHEMA); self.assertNotIn("temperature", kw)

    def test_mocked_compact_extract_caches_adapted_facts(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = {"keys": {"PRIMARY": "fake-key-A"}, "model": "m", "timeout_s": 1, "cache_dir": Path(d), "profile": "compact",
                   "price_in": None, "price_out": None}
            body = _json.dumps(compact([crec(resource_id="search_1", visible_text=["ID: search_1"])]))
            out = gx.extract(gx.png_manifest()[0], cfg, gx.Ledger(Path(d), 3),
                             call=lambda k, c, i: (body, {"prompt_token_count": 1}, "m", None), sleep=lambda s: None)
            self.assertFalse(out["extraction_failed"]); self.assertEqual(out["prompt_version"], "png-facts-v2-compact")
            self.assertEqual(out["facts"]["records"][0]["supporting_text"], ["ID: search_1"])
            self.assertTrue(any("png-facts-v2-compact" in p.name for p in Path(d).rglob("*.json")))


if __name__ == "__main__":
    unittest.main()
