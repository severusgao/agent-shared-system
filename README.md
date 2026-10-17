# Agent Shared System

[![Source checks](https://github.com/severusgao/agent-shared-system/actions/workflows/check.yml/badge.svg)](https://github.com/severusgao/agent-shared-system/actions/workflows/check.yml)

**One shared file system. Multiple computers. Multiple agents.**

一套共享文件，多台电脑，多个 Agent。

**English** · [简体中文](README_CN.md) · [Getting started (中文)](docs/getting-started.md) · [Architecture](docs/overview.md) · [Tencent comparison](docs/comparison.md)

Keep skills, reviewed long-term memory and MCP setup instructions in one shared folder. Use iCloud or another file synchronization provider to place local copies on each computer. Agents such as Codex, Claude Code, Gemini CLI, Cursor and OpenCode access those files through local entries. Tools, dependencies, credentials and live agent configuration stay local to each environment.

The core uses Markdown, JSON and lightweight scripts. It needs no always-on memory server or database.

用 iCloud 或其他文件同步工具，让各台电脑上的 Agent 共用技能、审阅过的长期记忆和 MCP 安装说明；工具与凭据各机准备，核心无需常驻记忆后台。

![macOS, Windows, WSL and standalone Linux architecture](assets/architecture.png)

Agent placement illustrates the architecture, not verified support for every client. See [brand attribution](assets/ATTRIBUTION.md).

## Who it is for · 适用人群

- Individuals moving between an office Windows PC and a home Mac.
- People using several computers, standalone Linux or WSL, and several agents.
- Users who want readable, reviewable and portable memory without operating a cross-location memory backend.
- Individuals and small teams with reliable file sync and a coordinated writing process. Team members use separate accounts and folder permissions.

Computers can read their downloaded local copies even when the office computer is off. New content still depends on synchronization. Concurrent edits to the same file require coordination. Models and external tools may still need network access.

适合在办公室和家中接续工作、使用多台电脑和多个 Agent 的个人，也适合能够协调文件写入的小团队。

## Four core skills

| Skill | Responsibility |
|---|---|
| `agent-shared-skills` | Task routing, skill reuse and creation, local discovery links |
| `agent-shared-memories` | Relevant memory queries, provenance, candidate review and maintained conclusions |
| `agent-shared-mcps` | MCP catalog and templates, per-host installation and per-agent verification |
| `agent-shared-evolution` | Evidence-based retrospectives, reviewed proposals and follow-up validation |

Project-specific skills may call shared skills. Every new skill should explain its purpose, triggers, steps, dependencies and success criteria. CLI/MCP skills also need host-specific setup instructions. Another computer must prepare its own dependencies and verify real operation. See [authoring skills](docs/authoring-skills.md).

## Download and start

1. Download the versioned ZIP from [Releases](https://github.com/severusgao/agent-shared-system/releases), extract the whole project into the final synchronization folder, and keep the hidden `.agents` directory. Download all files locally.
2. Install Python 3.12+ and an agent in the current environment. On macOS run `Start.command`; on Windows run `Start-Windows.cmd`; on Linux/WSL run `bash Start-Linux.sh`.
3. Verify the agent’s actual skills directory, review the local plan and apply it. Reload the agent and verify discovery, then query the fictional Atlas sample memory.

The launcher installs no agent or global prompt. Core dependencies require only PyYAML; preparing them accesses the network and creates a local runtime. Use `--target-dir` if your client needs another discovery directory. The [detailed guide](docs/getting-started.md) includes a prompt an agent can use to help deploy the system.

For a second computer, wait for synchronization and run that environment’s entry point. **File availability, agent discovery, dependency readiness and successful operation are separate checks.** Standalone Linux uses a suitable synchronization provider; WSL may read the Windows synchronized directory. An official iCloud client on Linux is not assumed.

## Why file-based memory · 文件记忆的价值

We studied [TencentDB Agent Memory](https://github.com/TencentCloud/TencentDB-Agent-Memory), a strong service-based memory project with centralized processing and management capabilities. It deserves consideration for centralized automation and team permission requirements.

Our strengths are local file access across devices, continuity between work and home without a separate route to an office memory backend, directly reviewable and portable text, optional independent review by multiple agents, and one shared source for skills, memory and MCP instructions.

Tencent’s system can run locally or in WSL; multiple devices sharing it need access to a common running backend. It does not inherently require purchasing a server. Multi-agent review here must actually be organized and performed. Agent count alone proves no quality advantage. We have not benchmarked accuracy, recall or cost against Tencent’s project. See the [detailed comparison and pinned source links](docs/comparison.md).

文件同步让各端使用本地副本，无需保持办公室电脑作为记忆主机在线；文本易读、易审阅、易迁移，并可组织多 Agent 提炼与复核。腾讯方案同样优秀，多端共用需访问共同后台，适合集中自动处理与权限管理；未经实测，不作记忆质量高低排名。

## Shared files and local runtime

```text
AgentShared/
├── README.md / Start.*
├── .agents/
│   ├── skills/       Four governance skills; optional extensions
│   ├── memories/     Maintained memory and blank personal templates
│   ├── mcp/          Catalog and setup templates
│   ├── evolution/    Reviewed proposals and retrospectives
│   ├── scripts/      Maintenance tools
│   └── state/        Environment records initialized locally
├── docs/
└── examples/         Method-only and CLI skill examples
```

Share durable methods, rules and reviewed knowledge. Keep binaries, secrets, live databases, caches and real agent configuration local. Releases contain neutral templates and synthetic examples, not the maintainer’s personal memories, sessions or account state.

This framework provides no memory-level ACL, database transaction or distributed lock. The [usage guide](docs/getting-started.md) explains coordinated team writes, upgrades preserving user data and unlink-only removal. See [extensions](docs/extensions.md) for third-party integrations.

## Verification and contribution

[Compatibility](docs/compatibility.md) · [Release audit](docs/release-audit.md) · [Contributing](CONTRIBUTING.md) · [Security](SECURITY.md)

Checks on macOS and isolated local onboarding do not establish real Windows, WSL, standalone Linux or all-agent support. Refer to the current validation record.

Original core code is [MIT licensed](LICENSE). Third-party brand assets are excluded from that grant.
