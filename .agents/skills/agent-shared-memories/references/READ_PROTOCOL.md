---
tags: [agents, memories, reading]
created: 2026-07-05
updated: 2026-10-05
type: topic
status: stable
sources: []
---
# Read Protocol

Read shared memory only when it can affect the answer or action.

Use `TRIGGER_POLICY.md` first to decide whether shared memory can affect the task. If the Memory Relevance Gate does not match, do not load memory merely because the skill is visible.

## Always Start

1. Resolve `.agents/memories/`.
2. Read `INDEX.md`.
3. Choose the smallest relevant files. If earlier changes, repeated issues or conflicts affect this task, use [QUERY.md](QUERY.md) to locate current entries and reviewed history. Ordinary unrelated work does not query histories.

## File Routing

| Task | Read |
|---|---|
| User background, communication preferences, stable personal context | `USER_PROFILE.md` |
| Machine paths, macOS/Windows differences, iCloud location, Python/CLI setup | `ENVIRONMENT.md` |
| Cross-agent behavior, approvals, write boundaries | `AGENT_RULES.md` |
| Hermes profiles, Codex/Claude Code roles, agent routing | `AGENT_PROFILES.md` |
| Skills, MCPs, CLIs, MinerU, Firecrawl, Obsidian tools | `TOOLS.md` |
| Architecture decisions and long-term choices | `DECISIONS.md` |
| Repeated operating procedures | `WORKFLOWS.md` |
| Shared-system source locations, state semantics, and onboarding boundaries | `DECISIONS.md`, `TOOLS.md`, `WORKFLOWS.md` |
| Self-evolution, repeated workflow review, skill/memory optimization | `WORKFLOWS.md`, `AGENT_RULES.md`, then `references/EVOLUTION_AUDIT.md` |
| Where memories came from | `SOURCES.md` |
| Recent approved memory edits | `CHANGELOG.md` |

## From Retrieval To Use

- Query with the object's names, keywords and Agent-selected synonyms; add a historical time window only when useful. Literal matching is not semantic retrieval. A miss calls for different terms or direct routing to a likely topic file, not a claim that the knowledge is absent.
- The default five results and 500-character previews are navigation, not evidence completeness. Expand relevant sections and parent conditions, paginate when needed, and follow specific source references until the answer's important conditions are accounted for.
- Distinguish user confirmation, actual observations, model inference and formally adopted decisions. Preserve who said or observed it, what was tested and what remains unknown. A formal page or `stable` file status is not per-entry proof of truth.
- `SOURCES.md` contains both current provenance and past batches. Read the relevant dated source section; neither treat the whole file as expired nor convert source commentary into an operative rule. Broad file-level references may need a specific approval, event or verification record.
- Current topic pages hold maintained conclusions. Historical evidence, proposed changes and past verifications are context; inspect version binding, retraction/replacement and current affected entries before acting. Source age alone does not invalidate it, and recency alone does not resolve a conflict.
- Keep applicability separate from tested environments. A shared convention may apply to Windows/WSL while its representative use was verified only on Mac. Verification neither grants instruction authority nor proves other environments work.

When memory materially affects an answer or action, report the relevant conclusion and its source/limits briefly. Carry unresolved evidence or conflicts forward; do not fill them with a guess. Source correction or retraction follows [WRITE_POLICY.md](WRITE_POLICY.md).

## Use Feedback

When an actual task exposes a missing condition, mistaken old decision or useful repeatable method, pass the evidence through the Candidate Gate. Existing evolution records can hold a concise use check: current entry/version used, scenario and environment, applicable condition, actual result/verification and any mistake or extra work. Ordinary tasks do not create compulsory logs. Cross-task effects and independent evidence are reviewed by `agent-shared-evolution`.

## Precedence

Follow the canonical [Authority And Conflict Handling](../../../memories/AGENT_RULES.md#authority-and-conflict-handling) rule. Do not maintain a separate precedence list here. The actual host instruction hierarchy always applies; live inspection verifies current facts and does not create instruction authority.

## Freshness

- Stable identity, confirmed communication preferences, and long-term architectural decisions may be used directly unless the user gives newer instructions.
- Installed versions, executable paths, links, running processes, network state, Agent profiles, current roles, and live tool configuration are discovery hints only. Verify them on the current machine before acting.
- Historical statements remain useful provenance but must not be rewritten as current state without fresh evidence.
