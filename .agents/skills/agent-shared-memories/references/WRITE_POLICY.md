---
tags: [agents, memories, writing]
created: 2026-07-05
updated: 2026-10-05
type: topic
status: stable
sources: []
---
# Write Policy

Shared memory writes require user approval.
Agent-initiated updates require explicit approval before writing.

There is no automatic shared memory write and no background sync. A native Agent memory or local rollout summary can be evidence for a proposal, not authorization to edit formal memory files.

## Candidate Gate

Use `TRIGGER_POLICY.md` before preparing a proposal. If no strong candidate exists, remain silent. One task may emit at most one proposal block containing no more than three related changes.

## Approval Gate

Follow [Approval Required](../../../memories/AGENT_RULES.md#approval-required) as the canonical authorization rule. Keywords alone do not authorize an agent-initiated update. Explicit user authorization to design and implement within a defined scope remains valid across necessary steps; explain the concrete changes and do not require a second approval unless the user reserved it or the scope materially changes. The proposal template below applies to agent-initiated changes and user-requested previews.

## Entry Quality

Compare with the existing entry before proposing. Preserve the conclusion together with conditions, exceptions, negations, actor/speaker, reason and actual outcome whenever these change its meaning. Keep event time separate from when it was recorded or verified. An interrupted/completed conversation does not prove success; an assistant's suggestion is not user confirmation.

Identify the basis as user-confirmed (`confirmed`), actually observed (`observed`), inferred (`inferred`) or formally adopted (`decision`); these are interpretation labels, not compulsory metadata on every sentence. A justified interpretation can be discussed and sourced, but unresolved inferences remain in review material until confirmed or adopted within the user's authorization. Choose the existing thematic page and only the stable, reusable difference. No bulk card conversion or historical rewrite is required.

## Update Kind And Affected Conclusions

| Kind | Required difference |
|---|---|
| `add` / 新增 | New stable information with no equivalent current entry. |
| `supplement` / 补充 | Add missing conditions, reason or evidence without changing the established conclusion. |
| `correct` / 纠错 | Identify the erroneous assertion and evidence that corrects it. |
| `replace` / 替代 | State which prior conclusion is superseded, why and within what scope. |
| `retract` / 撤回 | Remove the actionable assertion or mark the current section explicitly withdrawn/pending; record reason and approval in history. |

Use the existing file plus heading as the entry locator; retain that heading through a revision when practical. If a heading must change, record its predecessor/successor in the change record. Review affected current entries, navigation links and derived conclusions, including known usages in other theme pages. Search the specific assertion, locator and its source reference. A corrected or withdrawn source triggers a review of dependent conclusions; remove unsupported current guidance or mark it pending. If the dependency reach is unknown, record that uncertainty rather than claiming all effects were found.

Current thematic pages retain the current answer. `SOURCES.md`, `CHANGELOG.md` and authorized `.agents/evolution/` records preserve the origin and change trail. Age alone is not expiry. A new source must be assessed for authority, context and evidence rather than automatically overwriting an old one.

## Evidence-Backed Synthesis

Repeated issues may justify a stable method on an existing thematic page. Link the original user confirmation or verified observations and examine relevant counterexamples and conditions. Count independent incidents, not files, batches, repeated excerpts or multiple Agents repeating one suggestion. Several original events can still describe one incident; the query helper deduplicates original-event copies, and the Agent checks incident independence.

A synthesis, imported summary or earlier report can locate its basis, but cannot become an additional independent supporting fact merely by being summarized again. Unconfirmed analyses stay in review material. Update only the parts affected by new evidence, keeping valid conditions and source associations.

## Proposal Template

```markdown
## Proposed Shared Memory Update

- Trigger and update kind (`add` / `supplement` / `correct` / `replace` / `retract`):
- Existing target entry (file + heading), and affected entries/derived conclusions:
- Exact text to add/change/remove, preserving relevant conditions and exceptions:
- Basis references and status (confirmed / observed / inferred / decision):
- Stability rationale:
- macOS/Windows/agent impact:
- Verification:
- Proposal version and baseline (SHA-256 for a review package; equivalent exact snapshot in conversation):
```

Fill only relevant quality fields; precise prose is sufficient for ordinary updates. For structured memory candidates, optional `memory_update` contains `operation`, `knowledge_status`, `target_refs` and `basis_refs`; add `conditions`, `affected_refs`, `independent_event_refs` or `counterevidence_refs` where relevant. This is review metadata, not a new formal-memory schema.

For self-evolution or skill updates, also include:

```markdown
- Evidence reviewed:
- Existing coverage:
- Recommended form:
- Baseline problem:
- Semantic drift risk:
- Rollback path:
```

## Allowed Content

Any topic can be stored if it is stable, reusable, and approved: user preferences, machine paths, agent behavior, tool setup, work context, personal background, and long-term decisions.

## Do Not Store

- API tokens, credentials, cookies, OAuth values, private keys, or `.env` content.
- Complete chat transcripts or temporary debugging logs.
- Unverified guesses.
- One-off troubleshooting conclusions.
- Agent runtime lock files, backups, caches, or internal database files.

## Version And Concurrency

Approval covers the exact text/behavior, target baselines and reserved review boundary. For new `.agents/evolution` candidates, use `proposal_revision` plus `proposal_digest`; the digest covers all candidate fields except status/digest itself. Carry `review_id`, `candidate_id`, revision and digest into each approval/application/verification/retraction record. A content, condition, target or baseline change creates a new version; prior approval is not inherited. After rejection, retraction or supersession, delayed application/verification cannot restore authorization; a new proposal version and approval are required. Legacy packages remain readable, with missing version binding explicitly unknown.

One execution environment applies a batch. Re-read targets after approval and immediately before each write; compare exact baselines, record authored hashes, and preserve the existing temporary-batch lifecycle. Conflict detection is local, not an iCloud distributed lock or cross-file transaction. If a target changes, stop the conflicting write and bring the changed proposal back for approval; independent work within the unchanged authorization may continue.

## After Approval

1. After approval, re-read every target and compare it with the proposal baseline. If any target changed, stop and prepare a new proposal.
2. Apply the authorized update kind to current entries and affected conclusions; preserve source meaning and refresh the target's `updated` date.
3. Update `INDEX.md` only if a new file or section becomes part of the normal read path.
4. Update `SOURCES.md` only when a new durable source or provenance batch was introduced.
5. Append `CHANGELOG.md` with the update kind, entry locator and specific source/approval or review-batch reference. For replacement/retraction, include the predecessor/successor or pending impact.
6. Run `scripts/lint_memories.py`.
7. If an approved import used a temporary staging directory, delete it only after extraction and validation complete.

## Proposal Handling

Proposals remain in the current conversation or a user-authorized `.agents/evolution/` review package. Keep proposal archives, evidence summaries and staging outside formal memory. Approved theme pages remain the single current memory; do not create per-Agent copies.

## Evolution Audits

Evolution audits may recommend memory, skill, script, subagent, automation, extension, or skip decisions. Recommendations are not approval to write.

Do not run automatic prompt optimization, DSPy/GEPA/MIPRO workflows, repository mutation, or PR creation unless the user separately asks for that work.
