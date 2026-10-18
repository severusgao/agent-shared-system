---
tags: [agents, skills, lifecycle]
created: 2026-07-06
updated: 2026-10-18
type: reference
status: stable
sources: []
---
# Shared Skill Lifecycle

Use this reference when installing, creating, migrating, or retiring a shared skill.

After a shared skill is added, removed, renamed, or materially changed, preview
the dynamic shared-system README with:

```bash
python3 .agents/scripts/generate-shared-system-readme.py --preview
```

Write it within authorization covering the installation/update and related documentation; preserve a review step only when the user reserved it. The generator
updates only marked generated sections; it does not replace the manual rules in
`AgentShared/.agents/README.md`.

In the same change, refresh the expected-skills manifest
`references/skills_manifest.json`:

```bash
python3 -B .agents/skills/agent-shared-skills/scripts/audit_shared_skills.py --write-manifest
```

The manifest records which skills and required files (`SKILL.md`, plus
`agents/openai.yaml` and `local/ADAPTATION.md` when present) should exist. The
audit reports a missing manifest entry, a directory without `SKILL.md`, a broken
Markdown link or a sync conflict copy as an error, so file loss from
synchronization is not mistaken for retirement. Write the manifest only after an
approved install, update or retirement; the command refuses while any directory
lacks `SKILL.md`.

The repository ships only `references/skills_manifest.example.json`, which lists
the core skills. Setup copies it to `skills_manifest.json` when that file is
missing and never overwrites an existing manifest; the generated manifest is
local to each installation and stays out of version control.

## Placement Decision

| Situation | Placement |
|---|---|
| Cross-system, cross-agent capability the user wants to keep | `AgentShared/.agents/skills/<skill>` |
| One agent's private behavior or experimental prompt | That agent's native/private skill or memory area |
| One project/repo-specific convention | The project repository, not the shared-source skill store |
| One-off command, temporary workaround, or local package install | Do not create a shared skill |
| Existing shared skill already covers it | Extend or document the existing skill after approval |

## Naming

- Use lowercase letters, digits, and hyphens.
- Keep names short and action/domain oriented.
- Prefer existing domain namespaces when helpful.
- The folder name must equal the `name` in `SKILL.md`.

## Metadata Language

- Keep folder names, frontmatter `name`, commands, file names, protocol names, and CLI/API identifiers unchanged.
- Write every shared-skill `SKILL.md` frontmatter `description` entirely in Chinese while preserving every distinct trigger branch needed for automatic selection.
- User-invoked descriptions should be concise and human-facing. Model-invoked descriptions must preserve every distinct trigger branch needed for automatic selection.
- Write an existing `agents/openai.yaml` `short_description` as a 25-64 character Chinese summary. Do not create `openai.yaml` only for localization.
- Do not translate a third-party skill body, script, reference, or default prompt unless the user separately approves that functional/documentation fork.

## Creating Or Installing A Shared Skill

1. 按任务能力查重，决定复用、扩展、创建或跳过；摘要列出顶层与嵌套入口，勿把未进 CATALOG 当作不存在。
2. 第三方来源先确认仓库、版本和许可，在共享目录外暂存并检查文件；不直接把在线最新分支覆盖到正在使用的共享源。
3. 比较同名技能及已批准的本地覆盖；在 `UPSTREAM_SOURCES.md` 记录来源、版本和覆盖。自制技能明确自身维护范围，不冒充上游镜像。
4. 按下方 [跨系统安装说明](#cross-system-installation) 补齐并验收对应技能的依赖、安装入口和本机验证方法。
5. 只复制必需的 SKILL.md、参考、脚本、模板和资源。排除 `.git`、缓存、虚拟环境、安装目录、临时输出和凭据；不得借本次安装迁移既有凭据例外。
6. 完成结构、元数据和引用检查，再进入正式共享源。按已授权目标接入；放入共享源不自动授权部署到全部 Agent。
7. 初次接入使用现有系统启动器，后续使用链接辅助脚本。真实同名目录默认冲突；明确接管必须指定目标、技能和 `--replace-local`。
8. 仅在类别或核心入口改变时更新 CATALOG；使用既有生成器更新 README。已授权的文档配套修改不重复申请批准。
9. 分别报告源文件就绪、入口链接已验证、Agent 已发现、实际执行通过。没有证据的阶段标记未验证；失败保留原版本及恢复所需信息。

Installation staging and rollback copies stay outside the shared source. Keep a restorable previous version before an upstream replacement; interrupted installation must not be reported as complete. Do not independently deploy nested entries or move third-party files to satisfy a flat catalog.

<a id="cross-system-installation"></a>
## 跨系统安装说明

本要求适用于所有共享技能的新增、安装、更新和在新系统或 Agent 上的首次使用；检查范围为本次涉及的技能。第一次安装时，应把可复用的安装方法留在共享技能中，使另一环境的 Agent 不依赖原聊天记录也能准备本机环境。

纯方法或文档技能无需新增独立安装文件；条件分支只说明所需能力和触发条件。基础 Python、Node、Bash 的共同准备方法可引用 [本机基础运行环境](LOCAL_RUNTIME.md)，专用组件留在目标技能说明中。

### 说明放在哪里

- 从技能自身的 `SKILL.md` 能直接读到安装说明，或沿明确的相对链接到达随技能分发的说明；已有完整上游说明时复用并记录对应版本，避免复制维护。操作命令中的相对路径从技能真实目录解析，不依赖聊天工作目录或其他 Agent 的变量。
- 第三方技能优先保留上游正文；额外的跨系统说明放在 `local/ADAPTATION.md`，并在 `UPSTREAM_SOURCES.md` 记录适配及必要的入口覆盖。目标 Agent 直接加载技能时也须能到达说明；仅由治理路由读取适配文件，不能证明原生加载会读取它。上游正文或入口的改动仍遵守既有授权和版本保留规则。
- 共享安装方法、版本约束和验证步骤；二进制、包目录、虚拟环境、缓存、运行配置及凭据保留在各机本地。

### 必须能回答的问题

1. **需要什么：** 区分纯文档技能、随附脚本和外部运行依赖；列明必需与可选的 CLI、运行时、浏览器扩展、服务、MCP 或 Agent 原生工具。纯文档技能明确无需额外运行依赖，仍注明需要的 Agent 能力。
2. **怎样检查和安装：** 对适用的 macOS、Windows、WSL、独立 Linux/Linux 分支，给出依赖检测、官方安装入口或命令、必要的版本约束及调用方式。WSL 明确发行版内与 Windows 宿主分别安装什么、怎样连接。无需额外安装、不支持、安装方法待核实和已知方法但未实测须分别标明；不为凑齐平台编造命令。
3. **哪些步骤由用户完成：** 说明登录、授权、扩展安装、配对等人工步骤和所需认证类型，只给本机配置方法，不保存实际凭据。依赖 MCP 时转交 `agent-shared-mcps`；安装依赖或变更本机配置仍须在当前授权内。
4. **怎样验证与维护：** 给出版本或入口检查和最小实际任务、成功判据及必要清理步骤；指出自动更新、安装器覆盖共享入口等维护影响。命令执行成功或健康检查通过不能替代实际任务验证。

### 完成标准与缺口处理

- 从目标 Agent 可见的技能入口走读说明，确认上述问题都有明确答案，所需引用随技能可达；需要在线安装材料时核对其官方来源和版本。当前环境执行最小任务；其他环境分别标记验证状态，不沿用首次安装机的成功结论。
- 复查或更新现有技能时同时检查这份说明；发现缺口，在本次授权内补齐可核实部分。无法核实的平台明确留下缺口及所需动作，不宣称已具备完整跨系统安装能力，也不因一个分支缺失阻塞已可验证的其他分支。
- 结构审计只证明其实际检查的结构与元数据，不能证明安装说明完整或各平台可运行。交付时区分说明就绪、入口可达、Agent 已发现和本机实际任务通过。

## Deleting A Shared Skill

1. Prepare a proposal first; do not delete immediately.
2. List replacement skill, affected links, references, memories, scripts, and Agent directories.
3. After approval, remove the shared-source real copy and clean or leave local links according to the approved plan.
4. Run summary and audit; verify no stale mandatory route points to the deleted skill.
5. Remove deleted skills from active catalog and routing references.

## Renaming A Shared Skill

1. Treat rename as create new name plus retire old name.
2. Preserve the old skill until references, local links, and Agent links are accounted for.
3. Update `SKILL.md` `name`, folder name, routing references, memory references, and any script allowlists.
4. Run summary, audit, and recorded Agent link audit.

## Migrating A Local Skill Into Shared Skills

1. Inspect the local skill and identify secrets, caches, package folders, or machine-specific paths.
2. Remove or externalize anything that should not sync through iCloud.
3. Normalize paths to shared-system-relative paths, discovery scripts, or environment variables.
4. Copy only the durable skill files into `.agents/skills/<skill>`.
5. Replace local discovery entries with symlinks or Junctions only after backup and user approval.

## Adding A New Agent Target

1. Verify the Agent's real skill discovery directory on the current machine.
2. If this is a one-off or first-time onboarding, run the two-stage launcher and provide the Agent skills directory when prompted.
3. If the Agent will be used repeatedly, add a portable template to `references/agent_targets.json`; use `$HOME` or `%USERPROFILE%`.
4. Document the target in `references/AGENT_TARGETS.md`.
5. Run `scripts/sync_agent_skill_links.py --format markdown` or `--recorded-only --format markdown` to audit before applying.
6. Apply only after the plan is reviewed.

## Retiring A Shared Skill

Do not delete first. Prepare a proposal that includes:

- Why the skill is obsolete.
- Which skill replaces it, if any.
- Which docs and memories refer to it.
- How local symlinks or Junctions should be handled.
- Validation after retirement.
