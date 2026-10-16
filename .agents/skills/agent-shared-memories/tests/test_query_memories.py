from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import query_memories as q
from review_contract import proposal_digest


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def write_rows(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


class QueryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name)
        self.shared = self.workspace / ".agents"
        self.root = self.shared / "memories"
        self.root.mkdir(parents=True)
        self.history = self.shared / "evolution"
        self.history.mkdir()
        for name in q.REQUIRED_FILES:
            (self.root / name).write_text("---\nupdated: 2026-10-05\nsources:\n  - .agents/memories/SOURCES.md\n---\n# Test\n", encoding="utf-8")
        write_rows(self.history / "decisions.jsonl", [])

    def candidate(self, revision=1, schema=2, **changes):
        c = {"id": "C1", "proposal_key": "memory-example", "status": "proposed",
             "proposal_revision": revision, "problem": "repeat issue", "exact_change": "Use example only when confirmed; never infer user approval.",
             "targets": ["memories/DECISIONS.md"], "baseline": {"memories/DECISIONS.md": "0" * 64}, "evidence_ids": ["E1"],
             "platform_assessment": {p: {"applies": True, "verification_status": "unverified", "impact": "Shared method", "validation": "Actual Agent use"} for p in ("macos", "windows", "wsl")}}
        c.update(changes); c["proposal_digest"] = proposal_digest(c)
        write_json(self.history / "review/review-package.json", {"schema_version": schema, "review_id": "review", "candidates": [c]})
        return c

    def decision(self, c, status, **extra):
        return {"schema_version": 1, "review_id": "review", "candidate_id": c["id"], "decision": status,
                "proposal_revision": c["proposal_revision"], "proposal_digest": c["proposal_digest"],
                "timestamp_utc": "2026-10-05T00:00:00Z", **extra}

    def evidence(self, **extra):
        return {"schema_version": 1, "environment_id": "macos:fixture:user", "agent": "codex", "profile": "default",
                "session_id": "fixture-session", "event_id": "E1", "timestamp_utc": "2026-10-05T00:00:00Z",
                "role": "user", "summary": "Only discuss example; do not write. No successful test was observed.",
                "outcome": "completed_unverified", "origin_ref": "fixture:session#event", **extra}

    def find_candidate(self, **options):
        rows = q.query(self.root, ["example"], scope="history", limit=50, **options)["results"]
        return next(r for r in rows if r["kind"] == "candidate")

    def test_complete_section_keeps_conditions_negation_and_reason(self):
        content = "## Conditional decision\nUse example only for approved tasks because it preserves provenance.\n" + "Context. " * 100 + "\nExcept on the unverified host. Do not install a service.\n"
        (self.root / "DECISIONS.md").write_text(content, encoding="utf-8")
        result = q.query(self.root, ["example"], scope="current", preview_chars=60)
        self.assertTrue(result["results"][0]["truncated"])
        complete = q.query(self.root, ["example"], scope="current", full=True)["results"][0]
        self.assertIn("because", complete["preview"])
        self.assertIn("Except on the unverified host. Do not install", complete["preview"])
        self.assertEqual(complete["source"]["line_end"], 4)

    def test_subheadings_stay_with_parent_applicability_conditions(self):
        (self.root / "DECISIONS.md").write_text("## Scope\nOnly for approved tasks.\n### example method\nUse the current canonical page.\n## Other\nDifferent scope.\n", encoding="utf-8")
        row = q.query(self.root, ["example"], scope="current", full=True)["results"][0]
        self.assertIn("Only for approved tasks", row["preview"])
        self.assertNotIn("Different scope", row["preview"])

    def test_pagination_and_full_expansion_have_no_five_result_ceiling(self):
        (self.root / "DECISIONS.md").write_text("".join(f"## example {i}\nOnly when confirmed.\n" for i in range(9)), encoding="utf-8")
        a = q.query(self.root, ["example"], scope="current")
        b = q.query(self.root, ["example"], scope="current", offset=a["next_offset"], full=True)
        self.assertEqual(a["total_matches"], 9)
        self.assertEqual(len(a["results"]) + len(b["results"]), 9)
        self.assertIsNone(b["next_offset"])

    def test_current_rule_precedes_more_keyword_heavy_historical_proposal(self):
        (self.root / "DECISIONS.md").write_text("## Current example\nUse the maintained rule.\n", encoding="utf-8")
        self.candidate(problem="example example", exact_change="example example")
        row = q.query(self.root, ["example"], limit=1)["results"][0]
        self.assertEqual(row["kind"], "current")

    def test_sources_are_current_provenance_not_obsolete_rules(self):
        (self.root / "SOURCES.md").write_text("## Current basis\nexample user confirmation.\n", encoding="utf-8")
        row = q.query(self.root, ["example"], scope="current")["results"][0]
        self.assertEqual(row["kind"], "provenance")
        self.assertEqual(row["scope"], "current")
        self.assertEqual(row["status"], "context")

    def test_same_original_event_is_deduplicated_across_reviews(self):
        row = self.evidence()
        write_rows(self.history / "a/evidence.jsonl", [row])
        write_rows(self.history / "b/evidence.jsonl", [dict(row, event_id="E2")])
        self.candidate(evidence_ids=["E1", "E2"])
        result = q.query(self.root, ["example"], scope="history", full=True, limit=50)
        events = [r for r in result["results"] if r["kind"] == "evidence"]
        self.assertEqual(len(events), 1)
        self.assertEqual(len(events[0]["copies"]), 2)
        self.assertEqual(self.find_candidate()["located_event_count"], 1)
        self.assertEqual(events[0]["warnings"], [])
        self.assertIn("No successful test was observed", events[0]["preview"])
        self.assertEqual(events[0]["evidence"]["role"], "user")

    def test_revised_proposal_does_not_inherit_previous_approval(self):
        old = self.candidate()
        write_rows(self.history / "decisions.jsonl", [self.decision(old, "approved", approval_ref="fixture:user#approval")])
        self.candidate(revision=2, exact_change="example revised under a new condition")
        row = self.find_candidate()
        self.assertEqual(row["status"], "proposed")
        self.assertEqual(row["approval_binding"], "not_approved")
        self.assertIsNone(row["approval_ref"])

    def test_legacy_schema_one_approval_binding_remains_unknown(self):
        c = self.candidate(schema=1)
        c.pop("proposal_revision"); c.pop("proposal_digest"); c.pop("platform_assessment")
        write_json(self.history / "review/review-package.json", {"schema_version": 1, "review_id": "review", "candidates": [c]})
        write_rows(self.history / "decisions.jsonl", [{"schema_version": 1, "review_id": "review", "candidate_id": "C1", "decision": "approved", "approval_ref": "fixture:user#approval"}])
        row = self.find_candidate()
        self.assertEqual(row["recorded_status"], "approved")
        self.assertEqual(row["status"], "version_unknown")

    def test_retraction_and_unrelated_ledger_event_do_not_restore_approval(self):
        c = self.candidate()
        write_rows(self.history / "decisions.jsonl", [self.decision(c, "approved", approval_ref="fixture:user#approval"),
                    self.decision(c, "retracted"), self.decision(c, "review_completed")])
        row = self.find_candidate()
        self.assertEqual(row["status"], "retracted")
        self.assertEqual(row["authorization_status"], "withdrawn")
        self.assertFalse(row["usable_as_current_rule"])
        (self.root / "DECISIONS.md").write_text("## Current decision\nUse the corrected safe method.\n", encoding="utf-8")
        self.assertEqual(q.query(self.root, ["example"], scope="current")["total_matches"], 0)

    def test_delayed_application_and_verification_cannot_revive_withdrawn_approval(self):
        c = self.candidate()
        events = [self.decision(c, "approved", approval_ref="fixture:user#approval"),
                  self.decision(c, "retracted"), self.decision(c, "applied"),
                  self.decision(c, "verified", verification_ref="fixture:late-check", environment="wsl:fixture:user")]
        write_rows(self.history / "decisions.jsonl", events)
        row = self.find_candidate()
        self.assertEqual(row["status"], "retracted")
        self.assertEqual(row["authorization_status"], "withdrawn")
        self.assertIsNone(row["approval_ref"])
        self.assertFalse(row["applied"])
        self.assertEqual(row["verified_environments"], [])
        events.append(self.decision(c, "approved", approval_ref="fixture:user#late-approval"))
        write_rows(self.history / "decisions.jsonl", events)
        self.assertEqual(self.find_candidate()["status"], "retracted")

    def test_verification_needs_application_and_matching_approval_batch(self):
        c = self.candidate()
        events = [self.decision(c, "approved", approval_ref="fixture:user#approval"),
                  self.decision(c, "verified", verification_ref="fixture:check", environment="windows:fixture:user"),
                  self.decision(c, "applied", approval_ref="fixture:user#different")]
        write_rows(self.history / "decisions.jsonl", events)
        row = self.find_candidate()
        self.assertEqual(row["status"], "approved")
        self.assertFalse(row["applied"])
        self.assertIsNone(row["verification_ref"])
        self.assertEqual(row["verified_environments"], [])

    def test_cross_batch_verification_is_ignored_but_valid_multiple_checks_remain(self):
        c = self.candidate()
        events = [self.decision(c, "approved", approval_ref="fixture:user#approval", batch_id="A"),
                  self.decision(c, "applied", batch_id="A"),
                  self.decision(c, "verified", batch_id="B", verification_ref="fixture:wrong-check", environment="wsl:other:fixture")]
        write_rows(self.history / "decisions.jsonl", events)
        row = self.find_candidate()
        self.assertEqual(row["status"], "applied")
        self.assertEqual(row["verified_environments"], [])
        events.extend([self.decision(c, "verified", batch_id="A", verification_ref="fixture:mac-check", environment="macos:fixture:user"),
                       self.decision(c, "verified", batch_id="A", verification_ref="fixture:windows-check", environment="windows:fixture:user")])
        write_rows(self.history / "decisions.jsonl", events)
        row = self.find_candidate()
        self.assertEqual(row["verified_environments"], ["macos:fixture:user", "windows:fixture:user"])
        self.assertEqual(len(row["accepted_verification_refs"]), 2)

    def test_common_applicability_is_separate_from_mac_verification(self):
        c = self.candidate()
        write_rows(self.history / "decisions.jsonl", [self.decision(c, "approved", approval_ref="fixture:user#approval"),
                    self.decision(c, "applied"), self.decision(c, "verified", verification_ref="fixture:check", environment="macos:fixture:user")])
        row = self.find_candidate()
        self.assertTrue(row["platform_assessment"]["windows"]["applies"])
        self.assertEqual(row["platform_assessment"]["windows"]["verification_status"], "unverified")
        self.assertEqual(row["verified_environments"], ["macos:fixture:user"])

    def test_current_target_hash_change_invalidates_historical_verification(self):
        c = self.candidate()
        name = c["targets"][0]; original = hashlib.sha256((self.shared / name).read_bytes()).hexdigest()
        write_json(self.history / "review/application.json", {"proposal_digests": {"C1": c["proposal_digest"]}, "authored_hashes": {name: original}})
        write_rows(self.history / "decisions.jsonl", [self.decision(c, "approved", approval_ref="fixture:user#approval"),
                    self.decision(c, "applied", application_ref="review/application.json")])
        self.assertTrue(self.find_candidate()["current_target_match"])
        (self.shared / name).write_text("later user edit", encoding="utf-8")
        self.assertFalse(self.find_candidate()["current_target_match"])

    def test_history_time_filter_does_not_filter_current_file_dates(self):
        (self.root / "DECISIONS.md").write_text("## example\nStable confirmed choice.\n", encoding="utf-8")
        write_rows(self.history / "review/evidence.jsonl", [self.evidence()])
        result = q.query(self.root, ["example"], since="2026-10-06T00:00:00Z")
        self.assertEqual(len(result["results"]), 1)
        self.assertEqual(result["results"][0]["scope"], "current")
        with self.assertRaises(ValueError): q.query(self.root, ["example"], since="2026-10-05")

    def test_missing_source_unknown_schema_and_conflicting_copies_are_visible(self):
        self.candidate(evidence_ids=["missing"])
        write_json(self.history / "bad/review-package.json", {"schema_version": 999})
        result = q.query(self.root, ["example"], scope="history")
        self.assertFalse(result["complete"])
        self.assertTrue(result["warnings"])
        self.assertTrue(result["results"][0]["warnings"])
        row = self.evidence()
        write_rows(self.history / "a/evidence.jsonl", [row])
        write_rows(self.history / "b/evidence.jsonl", [dict(row, summary="example conflicting summary")])
        rows = q.query(self.root, ["example"], scope="history", limit=50)["results"]
        self.assertTrue(next(r for r in rows if r["kind"] == "evidence")["warnings"])
        write_rows(self.history / "b/evidence.jsonl", [dict(row, summary="qmd conflicting condition; not yet approved")])
        result = q.query(self.root, ["qmd"], scope="history", full=True)
        self.assertEqual(result["total_matches"], 1)
        self.assertEqual(result["results"][0]["independent_event_count"], 1)
        self.assertEqual(len(result["results"][0]["variants"]), 2)
        self.assertIn("not yet approved", result["results"][0]["preview"])
        self.assertTrue(result["results"][0]["warnings"])

    def test_link_escape_is_not_read_and_query_creates_no_files(self):
        outside = self.workspace / "outside.md"; outside.write_text("example secret fixture", encoding="utf-8")
        (self.root / "DECISIONS.md").unlink(); (self.root / "DECISIONS.md").symlink_to(outside)
        before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.workspace.rglob('*') if p.is_file()}
        result = q.query(self.root, ["example"], scope="current")
        self.assertFalse(result["complete"]); self.assertEqual(result["total_matches"], 0)
        after = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.workspace.rglob('*') if p.is_file()}
        self.assertEqual(before, after)

    def test_multiple_keywords_and_case_normalization(self):
        (self.root / "DECISIONS.md").write_text("## Hindsight\nShared memory recall.\n## 查询\n共享记忆需要来源。\n", encoding="utf-8")
        result = q.query(self.root, ["ＨＩＮＤＳＩＧＨＴ", "共享记忆"], scope="current")
        self.assertEqual(result["total_matches"], 2)


    def test_utf8_query_fixture_survives_gbk_default(self):
        original = Path.write_text
        def default_gbk(path, data, encoding=None, errors=None, newline=None):
            return original(path, data, encoding=encoding or "gbk", errors=errors, newline=newline)
        with patch.object(Path, "write_text", default_gbk):
            self.test_multiple_keywords_and_case_normalization()
        result = q.query(self.root, ["共享记忆"], scope="current")
        self.assertTrue(result["complete"])
        self.assertEqual(result["total_matches"], 1)

if __name__ == "__main__":
    unittest.main()
