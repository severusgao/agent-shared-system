# 跨平台入口与验收

依赖本机 Python 3.12+，使用标准库。共享源按当前技能真实路径或既有发现入口解析；新技能不安装 Python、不复制环境、不改全局配置。

## 来源发现

| Agent | 默认发现 | 可指定入口 |
|---|---|---|
| Codex | `CODEX_HOME` 或实际用户主目录 `.codex` 下的 sessions、archived_sessions | `--source codex:profile:<根或文件>` |
| Claude | `CLAUDE_CONFIG_DIR` 或主目录 `.claude/projects` | `--source claude:profile:<根或文件>` |
| Hermes | `HERMES_HOME` 或主目录 `.hermes/state.db`，以及存在的 profiles 下 state.db | `--source hermes:profile:<state.db>` |
| 其他 Agent | 不猜测其格式 | `import-summary` |

发现仅限约定入口及用户指定位置，不扫描整个磁盘。WSL 身份包含发行版；默认只发现 WSL 本机历史，Windows 历史由 Windows 采集后导入摘要。所有路径在目标环境重新核实。

## Mac

从技能真实目录运行 `python3 -B scripts/evidence.py discover`，检查入口与实际环境身份。首次 collect 默认 30 天。使用现有 macOS 接入工具或限定 `--skills agent-shared-evolution` 的链接工具接入已核实 Agent；新 Codex 会话验证发现、触发和实际读取。

已有启动器校验失败时，可直接使用现有 Python 链接助手，限定新技能，先预览再在授权内应用。Layer 1 使用共享 Skills 同时作为 `--shared-root` 和 `--local-root`，以实际统一入口作为 `--target-dir`，加 `--target-id unified --skills agent-shared-evolution --no-record`；Layer 2 使用实际统一入口作为 `--local-root`，限定已核实的 `--agents` 与该技能。助手位于同级 `agent-shared-skills/scripts/sync_agent_skill_links.py`。启动器修复另行进入审阅包。

## Windows

先通过现有 Windows 接入入口曝光新技能，确认主目录、Python 和共享源。以下命令在技能真实目录运行：

```powershell
py -3 -B scripts/evidence.py discover
py -3 -B scripts/evidence.py collect
py -3 -B -m unittest discover -s tests
```

不把已有 Administrator、盘符或 iCloud 挂载位置写成通用模板。Windows 可以独立发起复盘并应用已批准批次；先检查是否有其他设备编辑同批来源。应用环境不改变跨系统评估义务。

## WSL

使用现有 Windows→WSL 接入入口，在实际发行版内核实 Linux 路径和 Python，再运行与 Mac 相同的命令。Skills 逐项链接；Memories/MCP 仍为整体目录链接。不把 Windows 路径直接传入 Linux 接入工具。

## 每个环境的验收

macOS、Windows、WSL、独立 Linux 均可作为本批应用环境；按可用能力选择，保持一批一个写入方。应用前约定本批必须完成的验证和其他环境待验项目，未实测的设备状态单独保留；临时副本清理不无限等待其他设备上线。临时副本规则只由 [APPLY](APPLY.md) 维护。

1. 发现输出的身份、profile、真实路径与本机一致。
2. 指定窗口采集可见消息，coverage 明确完整、空、部分或缺失；没有日期的材料不伪造时间。
3. 新 Agent 会话正确选择此技能并读取必要文件；普通任务不启动全体系复盘。
4. 本地适配存在时验证执行前读取，未经共享路由的原生加载单独记录。
5. 核对批准批次摘要与本机读取文件一致，再分别测试入口和代表性使用。
6. 记录测试时间、方法及材料位置。路径测试和样本测试不等于目标机器实测。

首版交付要求 Mac 实测和 Windows/WSL 可运行入口及说明。Windows/WSL 未实测时明确标记；未设置任何周期自动运行。
