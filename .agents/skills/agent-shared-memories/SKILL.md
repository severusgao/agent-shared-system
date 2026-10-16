---
name: agent-shared-memories
description: 当任务需要共享的用户偏好、环境约定、长期决定或既往共享体系复盘作为背景，或需收录、补充、纠错、替代、撤回长期记忆时使用。按需查询并核对适用条件，维护有来源的现行结论；无强信号时保持安静，正式写入沿用用户授权。
---

# Agent Shared Memories

运行查询或校验助手前，按 [本机基础运行环境](../agent-shared-skills/references/LOCAL_RUNTIME.md#python-辅助脚本) 检查 Python 3.12+；本技能助手只用标准库，无额外 pip 包。

Use this skill to read or propose updates to the shared long-term memory stored in the independent shared Agent system.

Explicit invocation is the most reliable entry. Automatic selection depends on the current Agent runtime and is not guaranteed across every Agent.

## Start Here

1. Use `references/TRIGGER_POLICY.md` to run the Memory Relevance Gate before resolving or reading shared memory.
2. If the gate does not match, do not resolve or read shared memory.
3. If the gate matches, resolve the memories root. Prefer this skill's real path, the current shared-system directory, `AGENT_SHARED_MEMORIES_ROOT`, `AGENT_SHARED_SYSTEM_ROOT`, then the local stable entry.
4. Read `.agents/memories/INDEX.md` first.
5. Follow [READ_PROTOCOL.md](references/READ_PROTOCOL.md). Read the smallest relevant set; when earlier changes, repeated issues or conflicts matter, proactively use the read-only query helper to locate current memory and reviewed history. Read complete applicable conditions before acting.
6. Before the final response, run the Memory Candidate Gate only when a strong signal exists. If no candidate exists, remain silent.
7. Follow [Approval Required](../../memories/AGENT_RULES.md#approval-required). Agent-initiated updates require a proposal and explicit approval. When the user has already authorized design and implementation within a defined scope, state the concrete changes and proceed within that authorization; preserve any user-reserved preview gate.
8. After approval, re-read every target file. If it changed after the proposal was prepared, stop and propose again instead of merging silently.
9. Follow [WRITE_POLICY.md](references/WRITE_POLICY.md) to classify the update, check source meaning and affected conclusions, and apply only the authorized difference. Refresh dates, provenance and changelog as needed.
10. Run `scripts/lint_memories.py` after every formal write.
11. Use whole-directory local links for shared Memories; never create per-file memory links.
12. Treat `.agents/skills/`, `.agents/memories/`, `.agents/mcp/`, `.agents/scripts/`, and `.agents/state/` as shared-system sources, but do not call `.agents/` the vault.

## References

- `references/PATHS.md`: vault boundary, macOS/Windows discovery, symlink/Junction rules.
- `references/TRIGGER_POLICY.md`: authoritative pre-task relevance signals, post-task candidate signals, silence, deduplication, and concurrency rules.
- `references/READ_PROTOCOL.md`: retrieval, applicability, source interpretation and task use.
- `references/QUERY.md`: read-only query commands, version/status interpretation and expansion.
- `references/WRITE_POLICY.md`: entry quality, evidence-backed synthesis, revisions/retractions and authorized writes.
- `references/EVOLUTION_AUDIT.md`: evidence-driven review for repeated workflows, skill/memory improvements, and self-evolution proposals.

## Helpers

```bash
python3 -B .agents/skills/agent-shared-memories/scripts/resolve_memories_root.py --format json
python3 -B .agents/skills/agent-shared-memories/scripts/query_memories.py --term "共享记忆" --term "Shared Memories" --format json
python3 -B .agents/skills/agent-shared-memories/scripts/lint_memories.py --root .agents/memories --format markdown
```

Use `py -3` instead of `python3` on Windows when needed.

There is no automatic memory write or background sync. Formal shared memory changes require authorization covering the target and kind of change, as defined in [Approval Required](../../memories/AGENT_RULES.md#approval-required). Using a skill or reading memory is not authorization to modify it.
