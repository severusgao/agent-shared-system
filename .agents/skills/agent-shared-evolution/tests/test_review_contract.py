from __future__ import annotations

import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from review_contract import evidence_identity, proposal_digest, validate_memory_update, validate_revision


class ReviewContractTests(unittest.TestCase):
    def test_exact_content_and_baseline_change_require_new_digest(self):
        c = {"id": "fixture", "proposal_revision": 1, "exact_change": "Only if confirmed; never automatic.", "baseline": {"memories/DECISIONS.md": None}}
        c["proposal_digest"] = proposal_digest(c); validate_revision(c)
        c["baseline"]["memories/DECISIONS.md"] = "0" * 64
        with self.assertRaises(ValueError): validate_revision(c)
        c["proposal_revision"] += 1; c["proposal_digest"] = proposal_digest(c)
        validate_revision(c)
        c["exact_change"] = "Automatic."
        with self.assertRaises(ValueError): validate_revision(c)

    def test_legacy_versions_remain_readable_but_invalid_versions_fail(self):
        validate_revision({"exact_change": "legacy"})
        for revision in (0, -1, True, "2"):
            with self.assertRaises(ValueError): validate_revision({"proposal_revision": revision})

    def test_memory_operations_and_optional_quality_fields(self):
        c = {"owner": "memories", "memory_update": {"operation": "retract", "knowledge_status": "decision",
              "target_refs": ["memories/DECISIONS.md#Fixture"], "basis_refs": ["fixture:user#withdrawal"],
              "affected_refs": ["memories/WORKFLOWS.md#Fixture"], "conditions": ["Only within the approved scope."]}}
        for operation in ("add", "supplement", "correct", "replace", "retract"):
            c["memory_update"]["operation"] = operation; validate_memory_update(c)
        c["memory_update"]["basis_refs"] = []
        with self.assertRaises(ValueError): validate_memory_update(c)

    def test_duplicate_copies_share_event_identity_not_evidence_strength(self):
        a = {"origin_ref": "fixture:original#1", "event_id": "copy-a"}
        b = {"origin_ref": "fixture:original#1", "event_id": "copy-b"}
        self.assertEqual(evidence_identity(a), evidence_identity(b))
        self.assertNotEqual(evidence_identity(a), evidence_identity({"origin_ref": "fixture:original#2"}))


if __name__ == "__main__":
    unittest.main()
