---
name: agent-shared-evolution
description: 当用户要求复盘对话或任务以改进 Agent Shared 体系，执行周期复盘，或重复纠正暴露跨组件问题时使用。组织证据、原因判断、改进审阅包和效果验证；正式更新转交相应治理技能。普通业务任务不例行启动全体系复盘。
---

# Agent Shared Evolution

改进整个 Agent Shared 体系，优先减少重复纠正和返工。负责跨组件复盘与跟踪；技能、Memories、MCP、脚本和接入状态仍各有正式维护入口。

## 选择工作方式

- 用户要求月度、周期或跨组件复盘：读取 [REVIEW.md](references/REVIEW.md)，完成覆盖报告和可审阅改进包。
- 普通任务出现稳定强信号：先完成该任务，只提出有关的候选；记忆候选交给 `agent-shared-memories`。没有信号时保持安静。
- 用户批准具体变更包：读取 [APPLY.md](references/APPLY.md)，调用相应治理技能实施并记录结果。
- 已应用的改进再次接受检查：对照原问题、实际任务和验证结果，记录有效、无效或尚未验证。模型自己的建议不是效果证据。

## 最小工作链

1. 明确设备、Agent、周期及缺失来源。首次默认 30 天；后续默认 7 天并补齐各来源未成功复盘的区间。
2. 需要历史采集或摘要导入时读取 [EVIDENCE.md](references/EVIDENCE.md)。完整聊天和中间结果留在来源设备。
3. 按需通过 `agent-shared-memories` 的只读查询核对当前结论、既有候选和变化依据，再判断规则缺失、已有规则未遵循、环境故障或证据不足；不重复建设已覆盖机制。
4. 按 REVIEW 中的门槛产生准确改动，默认优先最多五项；逐项评估 macOS、Windows、WSL、独立 Linux 的影响及验证状态。共享记忆门槛由 `agent-shared-memories` 维护。
5. 给出一份统一审阅包。沿用当前授权；用户保留的批量审阅步骤必须完成后再应用候选。
6. 应用后分别记录源文件、设备入口、Agent 使用与后续效果，保留未验证边界。

## 维护对象

| 对象 | 正式负责入口 |
|---|---|
| Skills、技能路由、第三方适配与链接 | `agent-shared-skills` |
| 共享 Memories、长期约定和决定 | `agent-shared-memories` |
| MCP 注册表与兼容性规则 | `agent-shared-mcps` |
| 共享脚本 | 原脚本、调用方及有关测试 |
| 接入状态 | 相应接入工具，依据实测记录 |

源通过技能真实路径、当前共享体系或已有发现入口定位。记录放在共享根内的 `evolution/`；它不是正式 Memories。暂存与恢复副本放在本机 `~/.agent-shared-evolution/`；按 APPLY 的临时副本生命周期收尾，精简回执保留，旧内容清理。

macOS、Windows、WSL、独立 Linux 均可在实际能力允许时发起复盘或应用已批准改动；选择能完成本批约定验证的一个环境写入共享源。复盘设备不限定改进适用系统，一个批次只由一个环境应用。跨平台使用、接入和验收时读取 [PLATFORMS.md](references/PLATFORMS.md)。

首版不配置周期调度。原生运行配置、依赖安装和私有能力作为本机建议列出。Obsidian 不属于本技能的更新目标。自身修改也遵守同样的审阅与授权规则。

## 工具入口

从实际技能目录运行；Windows 可使用 `py -3`。Python 3.12+ 为本机依赖，仅使用标准库。

```bash
python3 -B scripts/evidence.py discover
python3 -B scripts/evidence.py collect
python3 -B scripts/evidence.py validate-package --package <package.json>
python3 -B scripts/batch_guard.py --help
```

采集输出是本机证据摘录，不是自动生成的共享总结。经内容核对和脱敏复核后，才将必要材料写入 `.agents/evolution/`。审阅包结构见 [模板](templates/review-package.json)。
