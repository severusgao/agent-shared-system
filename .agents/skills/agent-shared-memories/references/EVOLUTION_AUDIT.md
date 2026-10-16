---
tags: [agents, memories, evolution, audit]
created: 2026-07-06
updated: 2026-10-05
type: topic
status: stable
sources:
  - .agents/memories/SOURCES.md
---
# Evolution Audit Handoff

For conversation/task reviews, periodic reviews or cross-component Agent Shared improvement, read [agent-shared-evolution](../../agent-shared-evolution/SKILL.md). That skill maintains the review workflow and evidence interfaces; this file preserves the memory-side entry.

`agent-shared-memories` retains ownership of the Memory Relevance Gate, Memory Candidate Gate, target deduplication/conflict checks and formal memory writes. For an ordinary stable preference or fact, use those gates directly rather than starting a system review.

Memory candidates discovered in an evolution review still follow [TRIGGER_POLICY](TRIGGER_POLICY.md) and [WRITE_POLICY](WRITE_POLICY.md), including entry quality, independent-evidence synthesis, update/retraction impact, exact-version approval and the maximum three related changes. Honor current authorization and any user-reserved review step. Use [QUERY.md](QUERY.md) to locate existing conclusions, related candidates and actual use checks before proposing a duplicate. Review records and redacted evidence live outside formal Memories; no full transcripts, temporary outputs or automatic optimization enter this directory.
