---
tags: [agents, mcps, paths]
created: 2026-07-07
updated: 2026-07-14
type: reference
status: stable
sources: []
---
# MCP Paths

`AgentShared/.agents/` is the shared-system root. Shared MCP registry files live there:

```text
AgentShared/.agents/mcp/
```

This directory is a registry and template store. It is not an agent's live MCP config directory.

Canonical shared-system sources are:

```text
.agents/skills/    shared skill real copies
.agents/memories/  shared memory real copy
.agents/mcp/       shared MCP registry and templates
.agents/scripts/   onboarding, audit, and resolver scripts
.agents/state/     shared environment state
```

Do not call `.agents/` the vault. Do not put live Agent configs, secrets, package installs, or cache directories into the shared MCP registry.

## Local Discovery Entry

Each computer can link the shared registry to a local stable handle:

```text
macOS:
~/.agents/mcp

Windows:
%USERPROFILE%\.agents\mcp
```

macOS uses a symlink. Windows uses a Junction. The target is that machine's actual shared-system path.

WSL uses a whole-directory link for `~/.agents/mcp`, normally pointing through the Windows unified root. Do not create one symlink per MCP server and do not link WSL live Agent configs into iCloud.

## No Shared Live Configs

Do not place these live files directly in iCloud or replace them with iCloud links:

```text
~/.codex/config.toml
~/.claude.json
~/.cursor/mcp.json
~/.config/opencode/opencode.json
~/.hermes/config.yaml
```

Those files can contain local paths, profiles, credentials, unrelated MCPs, and agent-specific state.

## Discovery Priority

1. From this skill's real path, infer `AgentShared/.agents/mcp/`.
2. From the current directory, search upward for `.agents/mcp/`.
3. Use `AGENT_SHARED_MCPS_ROOT` when set.
4. Use `AGENT_SHARED_SYSTEM_ROOT`, appending `mcp`.
5. Resolve `~/.agents/mcp` or `%USERPROFILE%\.agents\mcp`.
6. If none or multiple conflicting candidates are found, ask the user.

## Multiple Windows Machines

Every Windows computer can mount iCloud at a different absolute path. The Junction target must be discovered from the current machine and must not be copied as a universal rule.

Windows display users in state or examples, including `Administrator`, are current-machine facts only. Environment IDs use `macos`, `windows`, `wsl`, and `linux`; machine matching is case-insensitive.

Use the sync scripts instead of writing a remembered Windows drive letter:

```text
.agents/scripts/macos-mcp-sync.command
.agents/scripts/windows-mcp-sync.cmd
```

These scripts are first-onboarding entry points. Later registry audits, resolver previews, and per-agent installs should use `agent-shared-mcps` helpers. There is no background sync; writes require preview and approval.
