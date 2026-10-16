---
tags: [agents, skills, update-policy]
created: 2026-07-06
updated: 2026-10-05
type: reference
status: stable
sources: []
---
# Update Policy

Shared skill updates follow the canonical [Approval Required](../../../memories/AGENT_RULES.md#approval-required) rule. Agent-initiated changes need a proposal and approval; explicit authorization to design and implement within a defined scope permits the necessary implementation choices without repeated approval. Preserve any review step reserved by the user.

Approval is also required for local link rewrites, state migrations, and any helper invocation that writes outside a dry-run preview. There is no background sync.

The shared-system README follows the same approval boundary. Its dynamic
sections may be discovered automatically, but changes are written only after a
preview lists the affected entries and existing authorization covers those changes. Use
`.agents/scripts/generate-shared-system-readme.py --check` to detect drift and
`--preview` before `--write`.

## Scope

Every current shared skill discovered by scanning `.agents/skills/*/SKILL.md` can evolve through this policy. A skill does not need to be listed in `references/CATALOG.md` to be eligible.

## Approval Gate

For Agent-initiated changes, a single inconvenience is not enough: use the Evolution Gate and propose a precise change. A direct user request to update within a defined scope is authorization, not merely a keyword signal.

## Proposal Template

```markdown
## Proposed Shared Skill Update

- Trigger:
- Target skill:
- Target files:
- Exact text or behavior to add/change/remove:
- Existing coverage:
- Why this is stable and reusable:
- macOS/Windows/agent impact:
- Validation:
- Rollback:
```

## Evolution Gate

Propose a skill update only when:

1. The issue has repeated, or is clearly likely to recur and expensive to solve again.
2. Inputs, procedure, output, and stopping condition are stable.
3. Existing shared skills, memories, scripts, or native agent features do not already cover it adequately.
4. The proposed change can be validated.
5. The change does not add secrets, temporary logs, caches, local package folders, or unverified guesses.

## Third-Party Upgrades

1. Resolve the recorded upstream repository and pinned revision from `references/UPSTREAM_SOURCES.md`.
2. Compare every installed file with upstream. Ignore only the local overlays explicitly recorded for that source.
3. Preserve approved Chinese metadata overlays, but compare each trigger with the new upstream version and refresh the translation when meaning changes; do not blindly retain old Chinese descriptions.
4. Treat any other local difference as a possible functional fork; stop and ask before overwriting it.
5. After an upgrade, run structure validation, shared-skill audit, upstream comparison, and README preview.

## After Approval

1. Edit only the approved shared skill files.
2. Update relevant root docs or shared memories if the rule affects cross-agent behavior.
3. Run this skill's audit or summary helper when shared skill structure, routing, lifecycle, or category notes changed.
4. Run `scripts/sync_agent_skill_links.py --format markdown` when Agent target or path rules changed.
5. Update `references/CATALOG.md` only for durable core entry points, routing notes, or category changes.
6. If path, environment, or state semantics changed, update root docs and approved shared memory files together.
7. Report changed files, verification results, and any remaining risk.
8. When descriptions changed, preview and then update the generated shared-skill section of `AgentShared/.agents/README.md` after approval.

## Rollback

Rollback should be possible by reverting the changed skill files and rerunning validation. If local symlinks or Junctions were changed, state exactly which local entry must be restored.

## Three Separate Actions

- 改进提议：从稳定、重复的需求提出精确变更，不在每次任务收尾例行提出。
- 检查上游：按需只读比较已记录版本和候选版本，报告差异与兼容性；本技能不提供定时检查。
- 应用更新：在对应授权内执行，按对应流程保留必要恢复能力，核对本地覆盖和必要依赖，再更新来源记录。由 `agent-shared-evolution` 组织的批次遵循其 [临时副本生命周期](../../agent-shared-evolution/references/APPLY.md#临时副本生命周期)，完成约定验证后清理旧内容。本技能不提供无人值守升级。

## Multiple Environments

同一技能的一次更新由一个环境完成，避免其他设备同时编辑。写入前重新读取目标；若相对预览发生变化或出现同步冲突，停止覆盖并报告。iCloud 的文件同步不保证事务性发布或互斥。实例记录是上次观察，不是远端设备的在线证明；本轮沿用现有状态格式，不迁移或补造状态。
