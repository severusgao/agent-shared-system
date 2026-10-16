---
tags: [agents, memories, triggers]
created: 2026-07-21
updated: 2026-10-05
type: reference
status: stable
sources: []
---
# Shared Memory Trigger Policy

This file is the single complete trigger matrix for shared-memory reading and update proposals. Other control documents should summarize and link here instead of copying the full matrix.

## Memory Relevance Gate

Route to shared memory before task execution when at least one signal applies:

- The user refers to an earlier agreement, established environment, or known long-term context.
- The task spans macOS, Windows, WSL, iCloud, or multiple agents.
- Stable user preferences, identity, communication style, or work context can change the answer.
- The task depends on a confirmed architecture decision, tool choice, or repeated workflow.
- Current instructions may conflict with an existing shared rule.

When the gate matches:

1. Resolve `.agents/memories/`.
2. Read `INDEX.md`.
3. Follow `READ_PROTOCOL.md`; read the smallest relevant set. When an earlier change, repeated issue or conflicting record can affect the task, proactively query current memory and existing reviewed history. A direct, unambiguous current preference does not require a full history search.
4. Verify live paths, versions, processes, installations, profiles, and network state before acting.

Do not read shared memory for self-contained translation, rewriting, trivial factual questions, small context-free code edits, or tasks whose answer depends only on live state.

## Read Failure

If the shared memories root cannot be resolved, do not guess memory content. State that shared memory was not read. Continue only when memory is not required for the task; otherwise ask for the missing entry or necessary context before acting.

## Memory Candidate Gate

Check for an update candidate only when at least one strong signal exists:

1. The user confirms a durable architecture or working method.
2. The user explicitly states a stable preference.
3. A durable cross-system, cross-agent, shared-skill, or MCP rule changes.
4. A workflow repeats at least twice, or one recurrence has clearly high recovery cost.
5. Existing shared memory is stale, incomplete, or conflicts with confirmed evidence.
6. A new agent, tool, or environment produces a reusable onboarding rule.

A candidate must also be confirmed or evidence-backed, expected to remain useful, reusable across future tasks or agents, and free of secrets or temporary logs. Use `WRITE_POLICY.md` to preserve conditions, negations, actors and outcomes, identify independent evidence and classify additions or revisions.

Do not propose current versions, process or network state, one-off failures, temporary workarounds, unapproved designs, inferred preferences, full transcripts, or credentials.

## Output Behavior

- If no strong candidate exists, remain silent and do not print a no-update message.
- If evidence is ambiguous, ask one necessary clarification question.
- If a candidate exists, finish the requested task first and then show one precise shared-memory proposal block.
- One task may produce at most one proposal block containing no more than three related changes.

## Deduplication And Conflict

Read each target before proposing:

- Skip information already recorded completely.
- Propose only the stale or missing difference.
- Show conflicts instead of overwriting them.
- Do not repeat a rejected proposal without new evidence.

## Approval And Concurrency

Formal memory writes still require explicit user approval covering the scope; existing user-delegated implementation authorization remains valid. Use `WRITE_POLICY.md` for version-bound approval, baseline re-reading and conflict handling. Never merge concurrent iCloud edits silently.
