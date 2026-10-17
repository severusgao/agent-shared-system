# 首次使用与第二台电脑

## 先准备

1. 选择同步工具。可选 iCloud Drive 或开源的 Syncthing，也可使用支持本地文件副本的其他工具；团队选择支持成员独立账号和目录授权的方案，不共用个人 Apple ID。独立 Linux 不假设存在官方 iCloud 客户端，可选支持 Linux 的 Syncthing 等同步工具。
2. 下载 GitHub Release 的版本 ZIP 并解压。把整个项目放到最终使用的同步目录，确认隐藏的 .agents 目录也完整保留、文件已下载到本地。先选定位置，再创建本机链接；不要在安装后随意移动源目录。
3. 当前系统安装 Python 3.12+ 和至少一个 Agent。Git 克隆不是使用前提，Node、Docker、数据库和服务器不是核心前置条件。

## 选择 iCloud 或 Syncthing

- **iCloud Drive**：使用现有 macOS/Windows 客户端，确保项目完整下载到本地；WSL 按实际挂载读取 Windows 文件。见 [Apple 官方设置说明](https://support.apple.com/guide/icloud/set-up-icloud-drive-mm203b05aec8/icloud)。
- **Syncthing**：从 [官方项目](https://github.com/syncthing/syncthing)选择当前系统版本，按[官方入门指南](https://docs.syncthing.net/intro/getting-started.html)互相添加设备并共享项目目录。先检查 `.agents` 已在同步范围，等目标机显示同步完成，再运行本框架入口。下载文件不等于同步软件已经安装、启动或配对完成。

同一份项目二选一，不要让两个同步工具同时管理同一目录。使用 Syncthing 时放在普通本地目录，避免嵌入 iCloud 等托管目录。共享项目来源，不共享各机的 `~/.agents` / Agent 用户目录链接、凭据或同步软件的运行数据库；贡献者 checkout 的 `.git` 元数据也不作为共享内容。

Syncthing 交换新内容需要设备同时在线并可连接。办公室与家中设备若从不同时在线，需要第三台持有文件的电脑或 NAS 接续同步。该节点不必运行记忆服务；已经同步的本地文件可离线读取。详情见[官方 FAQ](https://docs.syncthing.net/users/faq.html#what-is-syncthing)。

WSL 优先复用 Windows 已同步的项目目录，由 Windows 端管理文件同步，发行版内单独准备 Agent 与依赖。同步完成仍需分别验证 Agent 发现和实际查询。本项目尚未做 Syncthing 的跨设备实测，冲突处理仍遵循下方团队约定。

## 双击 / 运行入口

- macOS：双击 Start.command；系统阻止时，在终端对已核查的文件运行 `bash Start.command`。不关闭系统安全设置。
- Windows：运行 Start-Windows.cmd。启动器只对该进程使用现有 Python，不更改全局执行策略。
- 独立 Linux：从项目目录运行 `bash Start-Linux.sh`。
- WSL：在指定发行版内访问同步后的 Windows 项目目录，再运行 `bash Start-Linux.sh`。路径由 `wslpath` 或当前挂载实际解析，不能照抄别人的盘符。所有依赖在 WSL 内准备。

启动器询问 Agent 和实际 skills 目录。默认值只是目录模板，请核实当前客户端会读取它。安装先展示计划，确认后才创建本机入口。已有同名真实目录、其他来源链接或关联父目录时停止，不覆盖私人技能。

首次缺少 PyYAML 时，按提示建立本机独立运行环境；依赖安装会联网。也可从项目目录手工运行：

```bash
python3 -B scripts/setup.py --install-deps
python3 -B scripts/setup.py --agent codex
python3 -B scripts/setup.py --agent codex --apply
```

Windows 将 `python3` 替换为 `py -3 -X utf8`。`--install-deps` 只安装核心 Python 依赖；不安装 Agent、业务 CLI 或 MCP，也不申请 API Key。

## 让 Agent 帮助部署

把真实项目路径填入下面提示词。首次 Agent 还看不到核心技能时，直接让它读取项目文件即可。

> 请读取 `<本机项目路径>/README.md`、`docs/getting-started.md` 和 `.agents/skills/agent-shared-skills/SKILL.md`。确认当前系统、WSL 发行版（如适用）、共享目录和我的 Agent 技能入口。先用 setup.py 预览具体路径，不覆盖已有私有技能。按我的接入授权应用必要链接，准备当前机器所需依赖，再验证核心技能发现和 Atlas 示例记忆查询。MCP 与其他扩展按需准备，不同步真实凭据，不把其他电脑的状态当成本机成功。

## 验证四个阶段

1. 文件可读：检查 .agents/skills 中四项核心及 memory 模板。
2. 链接正确：setup 再次预览均为 skip。
3. Agent 发现：重载或新建会话，确认 Agent 实际列出并读取 agent-shared-skills。
4. 实际使用：让 Agent 按记忆相关性规则查询 Atlas 示例，指出它来自虚构模板，不作真实用户事实。

```bash
python3 -B .agents/skills/agent-shared-memories/scripts/query_memories.py --term Atlas --scope current --format json
```

初始化仅补缺失的空白个人页和状态文件。已有文件不覆盖。演示完成后可按授权删除 Atlas 示例；不要借此删除真实记忆。

## 第二台电脑

等待同一逻辑来源同步到本机，然后运行该系统入口。无需重新下载或用公共模板覆盖已有记忆。CLI、MCP、依赖、登录和客户端发现要在第二台电脑重新验证；技能新增后补齐该机链接。普通读取可使用已经落地的本地文件；文件同步、模型请求和外部工具可能仍需联网。

## 团队与冲突

可以通过具有成员共享权限的文件工具分发共享目录。它是文件协作，不提供细粒度记忆 ACL 或分布式锁。不同文件可分别维护；同一条规则或同一批修改指定一个写入方，其他人提交提案、等同步后再审阅。冲突副本要人工核对后合并，不能默默覆盖。

## 更新、移动与卸载

升级前备份使用中的文件；在新目录检查新发行版，将框架文件按清单更新到原目录，保留所有用户记忆、evolution 记录及本机配置。不要把新 ZIP 直接覆盖整个私人安装。贡献者源 checkout 不等于私人工作目录。

移动共享目录后，原链接可能失效；重新预览，显式检查旧来源再处理。卸载使用 `setup.py --agent <id> --uninstall --apply`，仅移除仍指向本项目的链接，保留数据、目录、配置和本机 Python 环境。依赖环境需删除时，核实其专用路径后另行处理。
