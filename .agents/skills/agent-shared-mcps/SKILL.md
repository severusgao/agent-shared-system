---
name: agent-shared-mcps
description: 当需要跨 macOS、Windows、WSL、独立 Linux 或多个 Agent 注册、安装、审计、修复共享 MCP，检查服务可用性、动态端口和本机路径，或提出 MCP 规则升级时使用。只治理共享注册表和模板，不共享 Agent 运行配置。
---

# Agent Shared MCPs

运行 Python 助手前，按 [本机基础运行环境](../agent-shared-skills/references/LOCAL_RUNTIME.md#python-辅助脚本) 检查 Python 3.12+；这些助手仅用标准库，专用 MCP 依赖按其登记条目另行准备。

Use this skill as the control plane for shared MCP registry entries stored in the shared Agent system.

## Start Here

1. Resolve the shared MCP root. Prefer this skill's real path, the current shared-system directory, `AGENT_SHARED_MCPS_ROOT`, `AGENT_SHARED_SYSTEM_ROOT`, then the local discovery link.
2. Read `references/PATHS.md` when macOS/Windows paths, local `.agents/mcp`, or multiple computers are involved.
3. Read `references/REGISTRY.md` when adding, reviewing, or updating a shared MCP registry entry.
4. Read `references/AGENT_CONFIGS.md` when installing an MCP into Codex, Claude, Cursor, OpenCode, Hermes, or another agent.
5. Read `references/OPEN_DESIGN.md` for Open Design-specific daemon, dynamic port, CLI, and MCP rules.
6. Read `references/UPDATE_POLICY.md` before changing this skill or `.agents/mcp/`.

## Helpers

```bash
python3 .agents/skills/agent-shared-mcps/scripts/resolve_mcp_root.py --format json
python3 .agents/skills/agent-shared-mcps/scripts/audit_shared_mcps.py --format markdown
python3 .agents/skills/agent-shared-mcps/scripts/sync_agent_mcp.py --mcp open-design --agent codex --format markdown
```

Use `py -3` instead of `python3` on Windows when needed.

For first-time MCP onboarding from outside an agent, use:

```bash
.agents/scripts/macos-mcp-sync.command
.agents/scripts/windows-mcp-sync.cmd
```

## Non-Negotiables

- Store durable MCP registry templates in `AgentShared/.agents/mcp/`.
- Canonical shared-system sources are `.agents/skills/`, `.agents/memories/`, `.agents/mcp/`, `.agents/scripts/`, and `.agents/state/`; do not call `.agents/` a vault.
- Do not store or symlink an agent's real MCP config file through iCloud.
- Do not assume one Windows iCloud path, username, drive letter, daemon port, or socket applies to another machine.
- WSL exposes the shared MCP registry through a whole-directory link, not per-server files and not live Agent config links.
- Resolution statuses are `native`, `bridge`, `unsupported`, and `unverified`; post-install verification tracks `configured`, `registered`, and `operational`.
- Prefer the agent's own MCP CLI when available, such as `codex mcp add` or `claude mcp add`.
- For JSON-based agents, deep-merge one MCP server entry and preserve unrelated user configuration.
- For unverified agents or profiles, print a ready-to-paste snippet instead of writing guessed config.
- Preview before writing. Apply within explicit authorization under [Approval Required](../../memories/AGENT_RULES.md#approval-required), without repeating approval for the same scope.
- Keep secrets out of shared registry files unless the user explicitly asks for a shared token file and accepts the tradeoff.
- No background sync writes MCP registry, state, or live Agent configs.
