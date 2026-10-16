# Shared-system maintenance entry

For installation and public usage start at [the project README](../README.md). The four core skills own detailed maintenance rules. This directory is independent of any Obsidian vault.

<!-- BEGIN GENERATED: shared-skills -->
### 当前共享 Skills

以下内容由 `.agents/skills/*/SKILL.md` 扫描生成，不是固定清单。

| Skill | 类型 | 用途 |
|---|---|---|
| `agent-shared-evolution` | 控制技能 | 当用户要求复盘对话或任务以改进 Agent Shared 体系，执行周期复盘，或重复纠正暴露跨组件问题时使用。组织证据、原因判断、改进审阅包和效果验证；正式更新转交相应治理技能。普通业务任务不例行启动全体系复盘。 |
| `agent-shared-mcps` | 控制技能 | 当需要跨 macOS、Windows、WSL、独立 Linux 或多个 Agent 注册、安装、审计、修复共享 MCP，检查服务可用性、动态端口和本机路径，或提出 MCP 规则升级时使用。只治理共享注册表和模板，不共享 Agent 运行配置。 |
| `agent-shared-memories` | 控制技能 | 当任务需要共享的用户偏好、环境约定、长期决定或既往共享体系复盘作为背景，或需收录、补充、纠错、替代、撤回长期记忆时使用。按需查询并核对适用条件，维护有来源的现行结论；无强信号时保持安静，正式写入沿用用户授权。 |
| `agent-shared-skills` | 控制技能 | 当需要按任务目标路由到合适 skill、选择或建议合适模型，或审计、安装、创建、迁移、更新、退役独立共享系统内的共享 skill 时使用；也用于判断是否读取共享长期记忆、处理 macOS、Windows、WSL、独立 Linux 链接和 Agent 目录对齐。共享记忆转交 agent-shared-memories，MCP 配置转交 agent-shared-mcps。 |

<!-- END GENERATED: shared-skills -->

<!-- BEGIN GENERATED: shared-mcps -->
### 当前共享 MCP

以下内容由 `.agents/mcp/catalog/*.json` 扫描生成；它不是 Agent 的实时 MCP 配置。

| ID | 名称 | 用途 |
|---|---|---|
| `rea` | REA | 本机软件逆向分析工具：分析原生程序、Electron/JavaScript、托管程序、软件包及运行行为。 |

<!-- END GENERATED: shared-mcps -->

<!-- BEGIN GENERATED: scripts -->
### 当前共享系统脚本

脚本真实副本位于 `.agents/scripts/`；首次接入和写入操作应先预览。

- `deploy-cloud-skills-macos.command`
- `deploy-cloud-skills-windows.cmd`
- `generate-shared-system-readme.py`
- `macos-mcp-sync.command`
- `macos-skill-sync.command`
- `shared_environment.py`
- `windows-mcp-sync.cmd`
- `windows-skill-sync.cmd`
- `windows-wsl-shared-sync.cmd`
- `wsl-shared-system-sync.sh`

<!-- END GENERATED: scripts -->

Memory triggers: `.agents/skills/agent-shared-memories/references/TRIGGER_POLICY.md`.
