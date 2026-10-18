---
name: agent-shared-skills
description: 当需要按任务目标路由到合适 skill、选择或建议合适模型，或审计、安装、创建、迁移、更新、退役独立共享系统内的共享 skill 时使用；也用于判断是否读取共享长期记忆、处理 macOS、Windows、WSL、独立 Linux 链接和 Agent 目录对齐。共享记忆转交 agent-shared-memories，MCP 配置转交 agent-shared-mcps。
---

# Agent Shared Skills

Use this skill as the control plane for shared skills stored in the shared Agent system.

## 选择和使用技能

已明确匹配的普通任务直接读取目标技能，不必先运行治理审计或扫描全部存量。
只有需要选择、比较或查找技能时，才读取 `references/ROUTING.md`，按需运行摘要。
先按用户目标和交付物路由，再按技能自己的描述和当前环境实际能力确认；只加载完成当前任务所需的技能。
用户点名某个技能时优先使用；存在多个候选时，优先专用交付技能，其次通用能力技能，最后才使用治理技能。
模型选择只在用户要求、创建子任务，或难度、成本、时效会实质影响结果时触发；按 `references/ROUTING.md` 选择，并先核实现环境可用模型。
本技能能指导或建议模型选择，不能后台改写当前会话的模型或全局配置。
涉及原生工具与共享技能的能力重叠时，才读取 `references/EXTERNAL_CAPABILITIES.md`。
通过本路由选择共享技能后，若目标存在 `local/ADAPTATION.md`，在执行前一并读取；直接原生加载的适配是否生效须在目标环境单独验证。
执行外部工具前，先确认当前系统、Agent 和所选调用方式（CLI、MCP、API 或内置能力），再按目标技能检查本机依赖、入口和认证。WSL 另确认发行版。共享技能可读不代表工具已安装；不要沿用其他机器的安装状态或凭据。缺失时按该技能的本机说明和已有授权准备，只安装当前任务需要的能力；用一次实际调用验证，并分别报告各环境结果。
用户要求复盘对话、周期检查或改进 Agent Shared 跨组件流程时，转交 `agent-shared-evolution`；普通任务不例行启动全体系复盘。

## 安装与维护技能

1. 解析共享源：技能真实路径、当前目录向上查找、`AGENT_SHARED_SKILLS_ROOT`、`AGENT_SHARED_SYSTEM_ROOT`、本机发现入口，按此顺序。
2. 首次接触体系或新 Agent 接入时，读取 `references/QUICK_START.md`。
3. 安装、创建、迁移、更新、改名或退役时，读取 `references/LIFECYCLE.md` 和 `references/UPDATE_POLICY.md`。
4. 链接、跨系统或 Agent 接入时，读取 `references/PATHS.md` 和 `references/AGENT_TARGETS.md`。
5. 顶层 `skills/*/SKILL.md` 是部署单元；摘要另列嵌套入口及父技能，不自动展平。
6. 记忆和 MCP 的维护分别交给 `agent-shared-memories`、`agent-shared-mcps`。
7. 沿用 [Approval Required](../../memories/AGENT_RULES.md#approval-required) 的授权；明确授权设计并实施后，不为普通步骤重复审批。

所有共享技能的新增、更新及新系统或 Agent 的首次使用，按 [跨系统安装说明](references/LIFECYCLE.md#cross-system-installation) 检查安装方法是否从目标技能入口可达、依赖是否完整、本机是否验证；已有链接不代表依赖已安装。

## Shared Memory Checkpoints

Before finalizing task skill selection, run the Memory Relevance Gate defined by `.agents/skills/agent-shared-memories/references/TRIGGER_POLICY.md`. Route to `agent-shared-memories` only when long-term context can affect the task; otherwise continue without loading memory.

At task completion, the router only identifies and hands off potential durable/reusable shared-memory signals to `agent-shared-memories`; no potential signal means the router remains silent. `agent-shared-memories` owns and runs the Memory Candidate Gate, including deduplication, conflict checks, and precise proposals. The router does not directly write formal memories.

## 可选扩展与专属技能

任务可使用已安装的项目专属技能、共享技能或 Agent 原生能力。依赖未安装时，按目标技能说明检查本机环境；核心不依赖任何第三方专家库、业务技能或私人 profile。创建技能的方法见 [技能编写指南](../../../docs/authoring-skills.md)。

## References

- `references/QUICK_START.md`: short first-read guide for new Agents and first-time shared skill use.
- `references/CATALOG.md`: core entry points, categories, and durable routing notes; not a fixed full inventory.
- `references/ROUTING.md`: task-to-skill routing and common skill chains.
- `references/PATHS.md`: shared-system paths, macOS symlinks, Windows Junctions, and discovery order.
- `references/AGENT_TARGETS.md`: Agent skill directory registry, second-layer link rules, and new Agent registration.
- `references/LIFECYCLE.md`: where shared skills belong and how to create, install, migrate, or retire them.
- `references/LOCAL_RUNTIME.md`: shared preparation for basic Python, Node and optional Bash; read only for the dependencies the target skill uses.
- `references/skills_manifest.json`: expected skills and required files, initialized by setup from `skills_manifest.example.json`; the audit treats gaps as errors. Refresh with `--write-manifest` only after an approved lifecycle change.
- `references/EXTERNAL_CAPABILITIES.md`: how to treat agent-native skills, plugins, MCPs, and profile-specific abilities.
- `references/UPDATE_POLICY.md`: proposal, approval, validation, and rollback rules for shared skill updates.
- `references/UPSTREAM_SOURCES.md`: pinned upstream sources and local metadata overlays for third-party skills.

## Helpers

以下 `.agents/` 开头的命令从共享根的父目录运行；在共享根内运行时去掉该前缀。
Python 3.12+ 为本机依赖；摘要和审计还需要本机 PyYAML。缺失时提示 `python -m pip install PyYAML`，不自动安装。设置 `PYTHONDONTWRITEBYTECODE=1` 或使用 `-B`，避免缓存进入共享目录。

```bash
python3 .agents/skills/agent-shared-skills/scripts/resolve_skills_root.py --format json
python3 .agents/skills/agent-shared-skills/scripts/audit_shared_skills.py --root .agents/skills --format markdown
python3 .agents/skills/agent-shared-skills/scripts/summarize_shared_skills.py --root .agents/skills --format markdown
python3 .agents/skills/agent-shared-skills/scripts/sync_agent_skill_links.py --format markdown
python3 .agents/skills/agent-shared-skills/scripts/sync_agent_skill_links.py --recorded-only --format markdown
```

Use `py -3` instead of `python3` on Windows when needed.

For first-time Agent onboarding from outside the new Agent, use the shared-system scripts:

```bash
.agents/scripts/macos-skill-sync.command
.agents/scripts/windows-skill-sync.cmd
.agents/scripts/windows-wsl-shared-sync.cmd
```

## Shared Skill Sync Routing

When the user asks to synchronize shared skills to a local machine or Agent, use the existing shared-system script; do not copy the script or reimplement its logic inside this skill.

Choose the script from the requested scope:

- Windows shared source -> Windows local unified root (`%USERPROFILE%\\.agents\\skills`): `.agents/scripts/deploy-cloud-skills-windows.cmd`.
- Windows shared skills -> one Windows Agent directory: `.agents/scripts/windows-skill-sync.cmd`.
- Windows shared system -> WSL unified root and an optional WSL Agent directory: `.agents/scripts/windows-wsl-shared-sync.cmd`. This wrapper runs `.agents/scripts/wsl-shared-system-sync.sh` inside the selected WSL distribution.
- macOS shared skills -> one macOS Agent directory: `.agents/scripts/macos-skill-sync.command`.
- Ongoing audit or targeted repair of an already exposed Agent directory: `python3 .agents/skills/agent-shared-skills/scripts/sync_agent_skill_links.py`.
- Read-only recorded-instance check: add `--recorded-only`; omit `--apply` for a preview plan.

For WSL, enter the Agent directory as a Linux absolute path, such as `/home/name/.codex/skills` or `/home/name/.hermes/skills`; never pass a Windows Explorer path or a `\\\\wsl.localhost\\...` path to the WSL wrapper. The Hermes source checkout directory `/home/name/.hermes/hermes-agent/skills` is not a synchronization target.

Always inspect the preview first. Apply link or state changes within explicit authorization, following [Approval Required](../../memories/AGENT_RULES.md#approval-required); a new tool invocation does not require repeating existing approval. Preserve real local skill directories on same-name conflicts unless the user explicitly approves a backup-and-replace plan. Validate the unified root and every requested Agent directory after applying.

## Non-Negotiables

- Manage only `<shared-project>/.agents/skills/<skill>` shared skills.
- Canonical shared-system sources are `.agents/skills/`, `.agents/memories/`, `.agents/mcp/`, `.agents/scripts/`, and `.agents/state/`; do not call `.agents/` a vault.
- Treat macOS and Windows absolute paths as machine examples, not universal rules.
- WSL may use the public root setup to link directly to the mounted shared source, or use the legacy Windows-unified-root wrapper. Select one route; Memories and MCP are directory links governed by their respective skills.
- Current Windows display users such as `Administrator` are machine facts, not universal path templates.
- Environment IDs use `macos`, `windows`, `wsl`, and `linux`; machine matching is case-insensitive.
- Treat Codex, Claude, Hermes, MCP, plugin, and profile capabilities as current-environment facts that must be verified before use.
- Do not modify CC Switch or depend on CC Switch being present; this skill only audits and deploys shared skills through filesystem links.
- Do not install or render MCP configs here; use `agent-shared-mcps` for shared MCP registry and per-agent MCP setup.
- Do not copy full contents of other skills into this control skill.
- Do not store CLI binaries, package directories, caches, or per-machine installs inside the shared system unless a specific skill explicitly requires a small script or reference file.
- There is no background sync. Link and state writes require a preview and authorization covering the target; `--yes` does not expand scope.

## Project Workflow Routing

Route project-specific skills to shared skills by name; prepare each host independently.
