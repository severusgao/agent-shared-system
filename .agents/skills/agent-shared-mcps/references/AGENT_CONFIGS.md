---
tags: [agents, mcps, configs]
created: 2026-07-07
updated: 2026-07-14
type: reference
status: stable
sources: []
---
# Agent MCP Configs

Use the current agent's native MCP installer when it exists. Only write JSON configs when the schema is known and the write can be deep-merged.

## Preferred Strategies

| Agent | Strategy | Notes |
|---|---|---|
| Codex | CLI | Prefer `codex mcp add`, `codex mcp remove`, `codex mcp list`. |
| Claude Code | CLI | Prefer `claude mcp add --scope user`, `claude mcp remove`, `claude mcp get`. |
| Cursor | JSON merge | Usually `~/.cursor/mcp.json`; verify current machine first. |
| OpenCode | JSON merge | Usually `~/.config/opencode/opencode.json`; verify current machine first. |
| Hermes | Manual unless verified | Profiles may differ; print snippet and ask user before writing. |

## Install Flow

1. Resolve `.agents/mcp/`.
2. Load `catalog/<mcp-id>.json`.
3. Resolve the local launch spec for this machine.
4. Preview the exact command or config diff.
5. Apply only after explicit confirmation.
6. Verify with the agent's own MCP list/get command when available.
7. Record current-machine status in `.agents/mcp/state/mcp_instances.json`.

Preview and apply are separate. The helper must not apply without explicit confirmation, and no background sync updates live Agent configs.

Verification vocabulary:

- `configured`: the config file or installer path was reachable.
- `registered`: the named MCP server appears in the Agent's list or config after apply.
- `operational`: the server was actually exercised; `null` means not checked.

## Do Not Overwrite

Never replace an entire agent MCP file with the shared registry. Only add, update, or remove the one named MCP server entry.

WSL bridge installs must keep live configs local to the target Agent. A bridge may be `native` only after its command exists and is executable in the environment being checked; otherwise it remains `unverified`.
