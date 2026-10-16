---
tags: [agents, skills, agent-targets]
created: 2026-07-06
updated: 2026-09-14
type: reference
status: stable
sources: []
---
# Agent Targets

This reference describes Agent skill discovery targets. It is for the second link layer:

```text
local unified skills root -> each Agent's own skills directory
```

The first layer is handled by the shared-system deployment scripts:

```text
AgentShared/.agents/skills -> ~/.agents/skills
AgentShared/.agents/skills -> %USERPROFILE%\.agents\skills
```

WSL uses the same second-layer idea. The public root setup links its unified root directly to the verified mounted source; the legacy wrapper links back to the Windows unified root. Do not point WSL directly at a remembered Windows iCloud path.

## Registry

The machine-readable registry is `references/agent_targets.json`. Keep it portable:

- Use `$HOME` on macOS.
- Use `%USERPROFILE%` on Windows.
- Do not put an iCloud drive letter, Windows username, or one machine's absolute shared-source path into the registry.
- Current Windows display users such as `Administrator` are observed machine facts only.
- Register only Agent skill discovery directories, not MCP config locations, plugin caches, model caches, or package installs.
- Environment IDs use `macos`, `windows`, `wsl`, and `linux`; machine matching is case-insensitive.

Built-in targets:

| Agent | macOS skill directory | Windows skill directory |
|---|---|---|
| Codex | `$HOME/.codex/skills` | `%USERPROFILE%\.codex\skills` |
| Claude Code | `$HOME/.claude/skills` | `%USERPROFILE%\.claude\skills` |
| Hermes | `$HOME/.hermes/skills` | `%USERPROFILE%\.hermes\skills` |
| Gemini | `$HOME/.gemini/skills` | `%USERPROFILE%\.gemini\skills` |
| OpenCode | `$HOME/.opencode/skills` | `%USERPROFILE%\.opencode\skills` |
| WorkBuddy | `$HOME/.workbuddy/skills` | `%USERPROFILE%\.workbuddy\skills` |
| Cursor | `$HOME/.cursor/skills-cursor` | `%USERPROFILE%\.cursor\skills-cursor` |

## Adding A New Agent

Before adding a target, verify the Agent really reads skills from that directory on the current machine. Then propose a change that includes:

- Agent name and stable id.
- Supported platforms.
- Skill directory template for each platform.
- Link strategy: symlink on macOS, Junction or compatible directory link on Windows.
- Validation command or manual check.

Do not infer a new target from a package name, app icon, or config folder alone.

## Audit And Deployment

Use the helper script from the shared-system root:

```bash
python3 .agents/skills/agent-shared-skills/scripts/sync_agent_skill_links.py --format markdown
python3 .agents/skills/agent-shared-skills/scripts/sync_agent_skill_links.py --agents workbuddy --skills agent-shared-skills --format markdown
```

On Windows use `py -3`:

```powershell
py -3 .agents\skills\agent-shared-skills\scripts\sync_agent_skill_links.py --format markdown
py -3 .agents\skills\agent-shared-skills\scripts\sync_agent_skill_links.py --agents workbuddy --skills agent-shared-skills --format markdown
```

The script audits by default. It only changes links with `--apply`, and it asks for confirmation unless `--yes` is also passed.

The script does not run in the background. Re-run audits after adding or deleting shared skills because the syncable set is the current scan of `.agents/skills/*/SKILL.md`.

The script only manages local unified entries that resolve to shared-source shared skills. Local-only skills that happen to live in `~/.agents/skills` or `%USERPROFILE%\.agents\skills` are reported as extras and ignored.

To sync one Agent directory without adding it to the registry first, pass a direct target:

```bash
python3 .agents/skills/agent-shared-skills/scripts/sync_agent_skill_links.py --target-dir "$HOME/.workbuddy/skills" --create-roots --format markdown
```

On Windows:

```powershell
py -3 .agents\skills\agent-shared-skills\scripts\sync_agent_skill_links.py --target-dir "%USERPROFILE%\.workbuddy\skills" --create-roots --format markdown
```

Use `--apply` only after reviewing the plan. Applied syncs update `state/agent_skill_instances.json` unless `--no-record` is provided.

Recorded statuses are state hints: `legacy` records are preserved evidence, `superseded_candidate` records can be replaced after review, and `conflict` plans require explicit resolution. A WSL bootstrap may report `state_pending` when links were handled but state could not be written.

An applied record describes the selected skills and the last observed time, not every capability of that Agent. A filtered sync must not be reported as complete coverage of the canonical source. Record preserved same-name native directories and other exclusions in the remediation report; use an unfiltered preview to expose outstanding conflicts. Recorded-only checks cannot discover unregistered Agents. Other-environment records are historical metadata until checked on that device.

To check only Agent directories already recorded for the current machine:

```bash
python3 .agents/skills/agent-shared-skills/scripts/sync_agent_skill_links.py --recorded-only --format markdown
```

## Bootstrapping A New Agent

A new Agent cannot use `agent-shared-skills` before it can see the skill. Bootstrap it from outside that Agent with the two-stage launchers:

```text
.agents/scripts/macos-skill-sync.command
.agents/scripts/windows-skill-sync.cmd
```

The launcher first exposes shared-source skills to the local unified root. It then asks for one Agent skills directory and uses `sync_agent_skill_links.py --target-dir ...` to preview and apply the second layer.

After the Agent can see `agent-shared-skills`, future checks can be driven from that Agent.

For WSL first-time onboarding, run the Windows wrapper
`.agents/scripts/windows-wsl-shared-sync.cmd`. When it asks for an Agent skills
directory, enter the directory as seen inside WSL, using a Linux absolute path
such as `/home/user/.codex/skills`. Do not enter a Windows Explorer path
or a `\\wsl.localhost\...` path. The wrapper runs the internal
`wsl-shared-system-sync.sh` worker as the detected WSL user, verifies the
unified and Agent skill links after apply, and records the WSL Agent instance.

For registered targets, the lower-level command remains:

```bash
python3 .agents/skills/agent-shared-skills/scripts/sync_agent_skill_links.py --agents <agent-id> --create-roots --apply
```

## Apply Scope And Recovery

注册表表示支持的目录模板，不表示本次授权。只读审计可扫描模板；写入必须指定 `--target-dir` 或 `--agents`。`--recorded-only` 本身不是写入目标授权。

真实同名目录默认冲突，普通 `--apply --yes` 不接管；经明确批准的接管需同时提供目标、`--skills` 与 `--replace-local`。两个参数在预览和应用时保持一致。首次启动器遇到冲突停止；需要接管时使用同一 helper 的精确目标计划，而不是放宽默认值。

链接 helper 对每项修改重新检查目标和源；失败逆序恢复本批入口。恢复失败保留原备份并给出具体路径，不删除外部新增内容。备份与目标需在同一文件系统以支持保留链接语义的重命名。冲突、技能不可用或执行失败返回非零退出码。状态写入失败显示 `state_pending`，不伪称同步完成。

Layer 1 启动器复用同一链接执行器，将共享源作为输入、统一目录作为精确目标，并使用 `--no-record`；Layer 2 以统一目录为输入。支持列表不授权修改原生技能、插件或私有配置。
