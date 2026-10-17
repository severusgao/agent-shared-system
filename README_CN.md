<h1 align="center">Agent Shared System</h1>

<p align="center"><strong>一套共享文件，多台电脑，多个 Agent。</strong></p>

<p align="center"><a href="https://github.com/severusgao/agent-shared-system/releases/latest"><img src="assets/badges/release.svg" alt="Release v0.1.1"></a> <a href="LICENSE"><img src="assets/badges/license.svg" alt="MIT license"></a> <a href="docs/getting-started.md"><img src="assets/badges/python.svg" alt="Python 3.12 or newer"></a> <a href="https://github.com/severusgao/agent-shared-system/actions/workflows/check.yml"><img src="https://github.com/severusgao/agent-shared-system/actions/workflows/check.yml/badge.svg?branch=main" alt="Source checks"></a></p>

<p align="center"><a href="docs/compatibility.md"><img src="assets/badges/macos.svg" alt="macOS setup; see validation status"></a> <a href="docs/compatibility.md"><img src="assets/badges/windows.svg" alt="Windows setup; see validation status"></a> <a href="docs/compatibility.md"><img src="assets/badges/linux.svg" alt="Linux setup; see validation status"></a> <a href="docs/compatibility.md"><img src="assets/badges/wsl.svg" alt="WSL setup; see validation status"></a></p>

<p align="center"><a href="#synchronization"><img src="assets/badges/icloud.svg" alt="Sync option: iCloud"></a> <a href="#synchronization"><img src="assets/badges/syncthing.svg" alt="Sync option: Syncthing"></a></p>

<p align="center"><a href="#installation">安装</a> · <a href="#agents">Agent 接入</a> · <a href="#overview">项目简介</a> · <a href="#architecture">共享架构</a> · <a href="#memory-comparison">记忆对比</a> · <a href="#documentation">文档</a></p>

<p align="center"><a href="README.md">English</a> · <strong>简体中文</strong></p>

把技能、审阅过的长期记忆和 MCP 安装说明放进一个共享目录，以 **iCloud Drive 为主要示例**，也可选择开源的 **Syncthing**。各台电脑读取本地文件，工具、登录和凭据分别准备。

<a id="installation"></a>

## 安装

**下载 → 放入同步目录 → 接入本机 Agent。**

1. 从 [Releases](https://github.com/severusgao/agent-shared-system/releases/latest) 下载完整 ZIP，解压到最终使用的同步目录，保留隐藏的 `.agents`，并确认文件已下载到本地。
2. 当前环境准备 Python **3.12+** 和至少一个 Agent，再运行对应入口：

   | 环境 | 入口 |
   |---|---|
   | macOS | `Start.command` |
   | Windows | `Start-Windows.cmd` |
   | Linux | `bash Start-Linux.sh` |
   | WSL | 在选定发行版内访问 Windows 挂载的项目目录，运行 `bash Start-Linux.sh` |

3. 核对实际 Agent 技能目录，审阅接入计划后应用。重载 Agent，确认能读取核心技能，再查询虚构的 **Atlas** 示例记忆。

缺少核心 Python 依赖时，启动器会提示准备本机独立环境。接入先预览，遇到同名私有技能默认保留。详见[完整接入指南](docs/getting-started.md)，其中提供了可交给 Agent 的部署提示词。

第二台电脑等待同一来源同步完成后，再运行自己的系统入口。**文件可读 → Agent 已发现 → 依赖就绪 → 实际任务通过**是四个不同阶段。

<a id="agents"></a>

## Agent 接入

以下是技能目录接入模板，不代表每个客户端版本均已通过真实会话验证。先核实当前客户端实际加载的目录；不同时使用 `--target-dir` 指定。

| 客户端 | 接入选项 | 已提供 |
|---|---|---|
| <img src="assets/agents/codex.png" width="20" height="20" alt=""> Codex | `--agent codex` | 目录模板 |
| <img src="assets/agents/claude.png" width="20" height="20" alt=""> Claude Code | `--agent claude` | 目录模板 |
| <img src="assets/agents/gemini.png" width="20" height="20" alt=""> Gemini CLI | `--agent gemini` | 目录模板 |
| <img src="assets/agents/cursor.png" width="20" height="20" alt=""> Cursor | `--agent cursor` | 目录模板 |
| <img src="assets/agents/opencode.png" width="20" height="20" alt=""> OpenCode | `--agent opencode` | 目录模板 |
| Hermes | `--agent hermes` | 目录模板 |
| WorkBuddy | `--agent workbuddy` | 目录模板 |

图标用于识别客户端，来源见[图标说明](assets/ATTRIBUTION.md)。各系统与客户端的验证状态见[兼容性说明](docs/compatibility.md)。这里的 Hermes 指技能目录接入，不代表已经集成 Hermes Gateway。

<a id="overview"></a>

## 项目简介

这是面向**多台电脑、多个 Agent**的文件共享框架。核心采用可阅读的 Markdown、JSON 和轻量脚本，无需常驻记忆服务器或数据库。

| 核心技能 | 职责 |
|---|---|
| `agent-shared-skills` | 任务路由、技能复用与创建、本机发现入口维护 |
| `agent-shared-memories` | 按需查询背景、追踪来源、审阅候选、维护获准的长期结论 |
| `agent-shared-mcps` | MCP 注册表和模板、逐机准备、逐 Agent 配置与调用验证 |
| `agent-shared-evolution` | 复盘取证、改进审阅和实施后的效果验证 |

项目专属技能可以按名称调用共享技能。新增技能写清用途、触发条件、步骤、依赖和成功判据；涉及 CLI 或 MCP 时补充各系统准备说明。详见[技能编写指南](docs/authoring-skills.md)。

### 适合谁

- 办公室用 Windows、回家用 Mac，希望接续工作背景的个人。
- 同时使用多台电脑、独立 Linux 或 WSL，以及多个 Agent 的使用者。
- 希望直接阅读、审阅、迁移和备份记忆的人。
- 能协调文件写入，并选择合适同步工具的小团队。

已经同步的本地内容，在另一台电脑关机后仍可读取；新内容到达取决于同步工具。模型和外部工具可能需要联网。团队按同步工具能力使用独立账号与目录权限，同一文件的编辑需协调；框架不提供记忆级 ACL、数据库事务或分布式锁。

<a id="architecture"></a>

## 共享架构

![macOS、Windows、WSL 与独立 Linux 的共享架构](assets/architecture.png)

[查看原尺寸架构图](assets/architecture.png) · [各组件如何配合](docs/overview.md)

图中 Agent 的分布仅作示意。WSL 可读取 Windows 挂载的共享文件，同时保留自己的 Linux 运行环境；独立 Linux 单列，并选择该平台可用的同步工具。

```text
AgentShared/
├── README.md / Start.*
├── .agents/
│   ├── skills/       共享方法与治理技能
│   ├── memories/     正式背景与空白个人模板
│   ├── mcp/          注册表与安装模板
│   ├── evolution/    审阅后的提案和复盘
│   ├── scripts/      维护工具
│   └── state/        初始化产生的环境记录
├── docs/
└── examples/         纯方法与 CLI 示例
```

共享耐久的说明和审阅结果。本机保存程序、凭据、缓存、活跃数据库与真实 Agent 配置。公开版本仅包含中性模板和虚构示例。

<a id="synchronization"></a>

## 文件同步

**主要介绍 iCloud Drive，Syncthing 作为开源备选。** 同一共享目录选择一种同步方式。

| 方案 | 适用场景 | 平台与同步条件 |
|---|---|---|
| [iCloud Drive](https://support.apple.com/guide/icloud/set-up-icloud-drive-mm203b05aec8/icloud) | 已有苹果/iCloud 工作流 | macOS、Windows；WSL 可读取 Windows 同步目录。不假定 Linux 有官方客户端。 |
| [Syncthing](https://github.com/syncthing/syncthing) | 希望使用跨平台开源同步工具 | macOS、Windows、Linux；设备在线且可连接时交换文件。 |

使用 Syncthing，持有新内容的设备与接收设备需要有同时在线的时间，或通过另一台电脑、NAS 接续传递。第三台设备是可选同步节点，已经同步的文件仍可本地读取。设置方式参照[官方入门指南](https://docs.syncthing.net/intro/getting-started.html)。

Syncthing 使用普通本地目录，避开其他同步工具托管的目录。同步包含 `.agents` 的项目来源，再在各机建立自己的 Agent 入口。见[同步工具选择说明](docs/getting-started.md#选择-icloud-或-syncthing)。

<a id="memory-comparison"></a>

## 记忆方案对比

我们研究过优秀的 [TencentDB Agent Memory](https://github.com/TencentCloud/TencentDB-Agent-Memory)。它提供集中处理和管理能力，适合评估自动加工与团队权限需求。

本项目的优势在于跨端本地文件读取、办公室与家中的工作接续、可直接审阅和迁移的文本、多 Agent 参与整理与复核，以及技能、记忆和 MCP 说明共用一个来源。腾讯方案可在本机或 WSL 部署，多设备共用时需要访问共同运行的后台，并非必须另购服务器。

多 Agent 审核需要实际组织执行。两套系统没有进行同任务准确率、召回率或成本对照，不作质量高低排名。详见[完整比较及固定版本来源](docs/comparison.md)。

<a id="documentation"></a>

## 文档

[首次接入与第二台电脑](docs/getting-started.md) · [架构说明](docs/overview.md) · [技能编写](docs/authoring-skills.md) · [可选扩展](docs/extensions.md) · [兼容性](docs/compatibility.md) · [腾讯方案对比](docs/comparison.md)

[贡献指南](CONTRIBUTING.md) · [安全说明](SECURITY.md) · [版本记录](CHANGELOG.md) · [首版审计](docs/release-audit.md) · [反馈问题](https://github.com/severusgao/agent-shared-system/issues)

原创核心以 [MIT](LICENSE) 发布，第三方产品图标不在 MIT 授权范围。自动化文件检查不等于真实 Agent 已加载、WSL 已验证或外部工具全部可用。
