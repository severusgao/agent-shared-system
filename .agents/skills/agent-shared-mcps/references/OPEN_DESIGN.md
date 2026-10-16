---
tags: [agents, mcps, open-design]
created: 2026-07-07
updated: 2026-07-07
type: reference
status: stable
sources: [https://github.com/nexu-io/open-design]
---
# Open Design MCP

Open Design is a local-first design workspace. It can be driven by a local agent such as Codex, and it also exposes a stdio MCP server that other agents can call.

## Key Distinction

Keep these directions separate:

```text
Open Design -> Codex
Codex generates inside Open Design.

Codex/Claude/Hermes -> Open Design MCP
The agent calls Open Design tools through an installed MCP server.
```

Both can be useful, but one does not imply the other.

## Dynamic Port Rule

Do not hardcode `127.0.0.1:7456` as the only valid Open Design daemon URL. Packaged desktop mode can use a dynamic loopback port and sidecar IPC.

Preferred discovery:

1. Read Open Design's `/api/mcp/install-info` from the running daemon.
2. Use the returned `command`, `args`, and `env`.
3. Preserve `OD_DATA_DIR`, `OD_SIDECAR_IPC_PATH`, and `ELECTRON_RUN_AS_NODE` when returned.

## CLI Collision Rule

On macOS and Linux, `od` may resolve to the system octal-dump command, not Open Design. Always check:

```bash
type -a od
```

If `od` is `/usr/bin/od`, do not use it as the Open Design CLI unless a wrapper is installed before `/usr/bin` on `PATH`.

## Useful Checks

```bash
codex mcp list
claude mcp get open-design
python3 .agents/skills/agent-shared-mcps/scripts/sync_agent_mcp.py --mcp open-design --agent codex --format markdown
```

The sync helper is allowed to discover a running Open Design daemon and preview the install command. Applying still requires explicit confirmation.
