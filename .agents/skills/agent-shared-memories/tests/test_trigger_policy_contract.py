from __future__ import annotations

import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
POLICY = SKILL_ROOT / "references" / "TRIGGER_POLICY.md"


class TriggerPolicyContractTests(unittest.TestCase):
    def test_policy_defines_both_gates_and_silent_no_candidate(self) -> None:
        text = POLICY.read_text(encoding="utf-8")

        self.assertIn("## Memory Relevance Gate", text)
        self.assertIn("## Memory Candidate Gate", text)
        self.assertIn("## Read Failure", text)
        self.assertIn("do not guess", text)
        self.assertIn("remain silent", text)
        self.assertIn("explicit user approval", text)

    def test_memory_contract_files_reference_trigger_policy(self) -> None:
        paths = [
            SKILL_ROOT / "SKILL.md",
            SKILL_ROOT / "AGENTS.md",
            SKILL_ROOT / "CLAUDE.md",
            SKILL_ROOT / "references" / "READ_PROTOCOL.md",
            SKILL_ROOT / "references" / "WRITE_POLICY.md",
        ]

        for path in paths:
            with self.subTest(path=path.name):
                self.assertIn("TRIGGER_POLICY.md", path.read_text(encoding="utf-8"))

    def test_relevance_gate_precedes_shared_memory_access(self) -> None:
        flows = [
            (
                SKILL_ROOT / "SKILL.md",
                "resolve the memories root",
                "Read `.agents/memories/INDEX.md`",
            ),
            (
                SKILL_ROOT / "AGENTS.md",
                "resolve `.agents/memories/`",
                "Read `INDEX.md`",
            ),
            (
                SKILL_ROOT / "CLAUDE.md",
                "resolve `.agents/memories/`",
                "Read `.agents/memories/INDEX.md`",
            ),
        ]

        for path, resolve, read in flows:
            with self.subTest(path=path.name):
                text = path.read_text(encoding="utf-8")
                gate = text.index("Memory Relevance Gate")
                self.assertLess(gate, text.index(resolve))
                self.assertLess(text.index(resolve), text.index(read))
                self.assertIn(
                    "If the gate does not match, do not resolve or read shared memory.",
                    text,
                )

    def test_write_contract_keeps_reapproval_and_single_proposal_limit(self) -> None:
        text = (SKILL_ROOT / "references" / "WRITE_POLICY.md").read_text(encoding="utf-8")

        self.assertIn("explicit approval", text)
        self.assertIn("re-read", text)
        self.assertIn("one proposal block", text)
        self.assertIn("three related changes", text)


if __name__ == "__main__":
    unittest.main()
