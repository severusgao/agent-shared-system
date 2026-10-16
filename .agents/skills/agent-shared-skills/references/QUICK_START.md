---
tags: [agents, skills, quick-start]
created: 2026-07-07
updated: 2026-10-16
type: reference
status: stable
sources: []
---
# Shared Skills Quick Start

Use this when an agent first encounters the independent shared Agent skill system.

Read `.agents/README.md` for the complete shared-system map. This file is the
short operational entry point; the control skills and their references remain
the detailed sources of truth for each subsystem.

## Core Rules

- The source of truth is `AgentShared/.agents/skills/`.
- The related canonical shared-system sources are `.agents/skills/`, `.agents/memories/`, `.agents/mcp/`, `.agents/scripts/`, and `.agents/state/`; do not call `.agents/` the vault.
- The current shared skill set is dynamic: scan `.agents/skills/*/SKILL.md` on demand or run `scripts/summarize_shared_skills.py`.
- `references/CATALOG.md` is a core-entry and category guide, not a complete fixed inventory.
- macOS uses symlinks and Windows uses Junctions. WSL uses per-skill symlinks to the mounted shared source through the public setup entry, or to the Windows unified root through the legacy wrapper. Link targets are machine-specific.
- Shared Memories and MCP registry use whole-directory links, not per-skill or per-file links.
- Do not copy shared skills unless the user explicitly asks.
- There is no background sync; onboarding/audit helpers preview first and write only after explicit approval.
- Do not update shared skills immediately after noticing an improvement. Prepare a proposal first unless the user already authorized implementation within the relevant scope.

## First Actions

1. Resolve the shared skills root.
2. Scan current skills with `python -B .agents/skills/agent-shared-skills/scripts/summarize_shared_skills.py --root .agents/skills --format markdown` when the current list matters.
3. Run the Memory Relevance Gate through `.agents/skills/agent-shared-memories/references/TRIGGER_POLICY.md` when long-term context may affect the task.
4. Read the candidate skill's own `SKILL.md` before using it. On first use in a new system or Agent, follow the [cross-system installation requirements](LIFECYCLE.md#cross-system-installation) to find its setup instructions and verify local dependencies.
5. Use `agent-shared-skills` for skill choice, sync, audit, lifecycle, and skill update proposals.
6. Use `agent-shared-memories` for shared memory.
7. Use `agent-shared-mcps` for shared MCP registry and Agent MCP setup.
8. Use a separately installed knowledge-base skill for vault-specific work; core installation does not include one.
9. Treat environment IDs as `macos`, `windows`, `wsl`, or `linux`; current Windows usernames such as `Administrator` are machine facts, not templates.

## When Unsure

Read `references/ROUTING.md`, then the candidate skill's own `SKILL.md`. Do not infer purpose from a folder name alone.

The command above runs from the shared root's parent; omit `.agents/` when running inside the shared root. Summary and audit require machine-local PyYAML. Ordinary tasks may directly use a matching skill without running these maintenance steps.
