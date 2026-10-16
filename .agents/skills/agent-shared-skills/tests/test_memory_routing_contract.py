from __future__ import annotations

import unittest
import re
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
SHARED_SKILLS_ROOT = SKILL_ROOT.parent
VAULT_ROOT = SHARED_SKILLS_ROOT.parents[1]
CANONICAL_TRIGGER_POLICY = ".agents/skills/agent-shared-memories/references/TRIGGER_POLICY.md"
SHORT_TRIGGER_POLICY = "agent-shared-memories/references/TRIGGER_POLICY.md"

POLICY_POINTER_FILES = (
    SKILL_ROOT / "SKILL.md",
    SKILL_ROOT / "AGENTS.md",
    SKILL_ROOT / "CLAUDE.md",
    SKILL_ROOT / "references" / "ROUTING.md",
    SKILL_ROOT / "references" / "QUICK_START.md",
    VAULT_ROOT / ".agents" / "memories" / "WORKFLOWS.md",
    VAULT_ROOT / ".agents" / "README.md",
)


class MemoryRoutingContractTests(unittest.TestCase):
    def _assert_memory_candidate_gate_owner(self, contract: str) -> None:
        self.assertIn("agent-shared-memories owns and runs the Memory Candidate Gate", contract)

    def _assert_post_task_handoff_order(self, handoff: str) -> None:
        normalized_handoff = handoff.replace("`", "")
        self.assertIn("agent-shared-memories", normalized_handoff)
        self.assertIn("Memory Candidate Gate", normalized_handoff)
        memories_index = normalized_handoff.index("agent-shared-memories")
        gate_index = normalized_handoff.index("Memory Candidate Gate")

        self.assertLess(memories_index, gate_index)
        self.assertNotIn("Run the Memory Candidate Gate", normalized_handoff)
        self.assertNotIn("confirmed by Gate", normalized_handoff)
        self.assertNotIn("Memory Candidate Gate -> confirmed", normalized_handoff)

    def test_canonical_trigger_policy_pointer_exists_and_is_used_cross_file(self) -> None:
        canonical_policy = VAULT_ROOT / CANONICAL_TRIGGER_POLICY
        self.assertTrue(canonical_policy.is_file(), canonical_policy)

        for path in POLICY_POINTER_FILES:
            contract = path.read_text(encoding="utf-8")
            self.assertIn(CANONICAL_TRIGGER_POLICY, contract, path)


    def test_router_defines_relevance_gate_and_memory_handoff_boundary(self) -> None:
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")

        selection_gate = "Before finalizing task skill selection, run the Memory Relevance Gate"
        self.assertIn(selection_gate, skill)
        self.assertLess(skill.index(selection_gate), skill.index("## Project Workflow Routing"))
        normalized_skill = skill.replace("`", "")
        self._assert_memory_candidate_gate_owner(normalized_skill)
        self.assertIn("only identifies and hands off potential durable/reusable shared-memory signals", skill)
        self.assertIn("does not directly write formal memories", skill)
        self.assertNotIn("confirmed by the Memory Candidate Gate", skill)

    def test_memory_candidate_gate_owner_contract_rejects_missing_owner(self) -> None:
        missing_owner = "The router hands off potential durable/reusable shared-memory signals."

        with self.assertRaises(AssertionError):
            self._assert_memory_candidate_gate_owner(missing_owner)

    def test_post_task_handoffs_transfer_to_memories_before_its_gate(self) -> None:
        routing = (SKILL_ROOT / "references" / "ROUTING.md").read_text(encoding="utf-8")
        post_task_handoffs = [
            line.strip()
            for line in routing.splitlines()
            if "Memory Candidate Gate" in line
        ]

        self.assertTrue(post_task_handoffs)
        for handoff in post_task_handoffs:
            self._assert_post_task_handoff_order(handoff)

    def test_post_task_handoff_contract_rejects_gate_before_memories(self) -> None:
        gate_before_memories = "selected task skill -> Memory Candidate Gate -> agent-shared-memories"

        with self.assertRaises(AssertionError):
            self._assert_post_task_handoff_order(gate_before_memories)

    def test_both_control_skills_are_model_selectable_and_metadata_mentions_memory(self) -> None:
        router_skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        memory_skill = (SHARED_SKILLS_ROOT / "agent-shared-memories" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        openai = (SKILL_ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8")

        self.assertNotIn("disable-model-invocation: true", router_skill)
        self.assertNotIn("disable-model-invocation: true", memory_skill)
        self.assertIn("共享记忆", openai)
        self.assertIn("任务", openai)


if __name__ == "__main__":
    unittest.main()
