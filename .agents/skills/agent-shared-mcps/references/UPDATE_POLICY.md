---
tags: [agents, mcps, update-policy]
created: 2026-07-07
updated: 2026-09-12
type: reference
status: stable
sources: []
---
# MCP Update Policy

Shared MCP registry and skill updates follow the canonical [Approval Required](../../../memories/AGENT_RULES.md#approval-required) rule. Agent-initiated changes need approval; an existing authorization to design and implement within a defined scope continues across necessary steps. Preserve any review step reserved by the user.

Approval is also required for `.agents/mcp/state/` writes and any live Agent config change. There is no background sync.

## Proposal Template

```markdown
## Proposed Shared MCP Update

- Trigger:
- Target MCP:
- Target files:
- Exact behavior or text to add/change/remove:
- Existing coverage:
- Why stable and reusable:
- macOS/Windows/agent impact:
- Validation:
- Rollback:
```

## Approval Gate

Do not update `.agents/mcp/` just because a command failed once. Propose an update when the rule is likely to recur, cross-system, and verifiable.

## Validation

- Run `resolve_mcp_root.py`.
- Run `audit_shared_mcps.py`.
- Dry-run `sync_agent_mcp.py` for at least one relevant agent.
- Confirm no live agent config file was copied into the vault.
- Confirm resolution status and verification fields are reported separately.
- Confirm no secrets were written to `.agents/mcp/`.
