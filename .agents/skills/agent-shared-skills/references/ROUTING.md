# Skill Routing

Select by the user's goal, deliverable, and actual available capability.

| Need | Entry |
|---|---|
| Choose, create, install, sync, update or retire a shared skill | agent-shared-skills |
| Relevant stable context, memory lookup or approved memory change | agent-shared-memories |
| MCP catalog, current-machine launch recipe or Agent MCP config | agent-shared-mcps |
| Cross-component retrospective and review package | agent-shared-evolution |

Read each selected SKILL.md. Read its local/ADAPTATION.md if it exists, including when the skill is invoked directly. Optional extensions are listed in [the extension guide](../../../../docs/extensions.md); their absence must not block core functions.

Before task-skill selection, use the Memory Relevance Gate in [TRIGGER_POLICY.md](../../agent-shared-memories/references/TRIGGER_POLICY.md). The router hands potential durable signals to agent-shared-memories, which owns the Memory Candidate Gate. Do not write memory automatically.

Before creating a skill, scan existing names/descriptions and relevant native tools. Reuse first, extend within the same durable responsibility, create only for a distinct reusable capability. A project-specific skill can refer to a shared skill by name and resolve its current path; do not embed duplicate upstream bodies.

Use the current model unless the user asks to select one or a material task constraint requires a choice. Do not assume provider names, accounts, pricing or models are shared across devices.

Canonical policy: `.agents/skills/agent-shared-memories/references/TRIGGER_POLICY.md`.
