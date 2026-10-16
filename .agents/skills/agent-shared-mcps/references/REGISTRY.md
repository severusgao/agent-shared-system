---
tags: [agents, mcps, registry]
created: 2026-07-07
updated: 2026-07-14
type: reference
status: stable
sources: []
---
# Shared MCP Registry

The registry describes MCP servers the user wants available across systems and agents.

## Layout

```text
.agents/mcp/
├── README.md
├── catalog/
│   └── <mcp-id>.json
├── targets/
│   └── agents.json
└── state/
    └── mcp_instances.json
```

## Catalog Rules

Each `catalog/<mcp-id>.json` stores durable, cross-system intent:

- `id`: stable lowercase id.
- `server_name`: MCP server name as it appears inside an agent config.
- `description`: what the server is for.
- `resolution`: how to discover a local runnable launch spec.
- `install_notes`: constraints and validation notes.

Do not store machine-specific final config as the source of truth. Store how to derive it on the current machine.

Resolution status meanings:

- `native`: a runnable spec was verified for the current environment.
- `bridge`: a runnable bridge spec was verified, such as WSL calling a Windows-side command.
- `unsupported`: the catalog explicitly says this platform is not supported.
- `unverified`: the registry has intent, but no safe runnable spec is verified for this environment.

## State Rules

`state/mcp_instances.json` records what was installed or audited on a specific machine and agent. Absolute paths in state are evidence, not universal path rules.

State instance keys include environment, agent, MCP id, and server name. Verification fields mean:

- `configured`: a write strategy or config location was available.
- `registered`: the target Agent reports or contains the server entry.
- `operational`: a real server/tool call check passed; `null` means not verified, not success.

Do not store API keys, OAuth values, cookies, or `.env` content in catalog or state.

## Add A New MCP

1. Confirm repeated cross-agent value.
2. Add a catalog JSON entry.
3. Add agent-specific installation behavior only if the format is verified.
4. Add a dry-run validation path.
5. Update `agent-shared-mcps` references and `agent-shared-skills` routing if it changes task selection.
