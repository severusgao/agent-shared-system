# 兼容性与验证边界

[English](compatibility.en.md) · **简体中文** · [项目首页](../README_CN.md)

框架面向 macOS、Windows、独立 Linux 和 WSL。支持目录模板不等于当前版本客户端已加载；客户端发现和工具能力必须在实际设备验证。

| 环境 | 接入方式 | 首次公开版验证 |
|---|---|---|
| macOS | 本机逐技能 symlink；Memories/MCP 整目录链接 | 当前维护机的隔离环境运行，详见 release-audit.md |
| Windows | 本机逐技能 Junction；Memories/MCP 整目录 Junction | GitHub Windows runner 隔离接入测试通过；真实客户端待验 |
| 独立 Linux | Linux 本机逐技能 symlink 与整目录链接 | GitHub Ubuntu runner 隔离接入测试通过；真实客户端待验 |
| WSL | 在选定发行版中运行 Linux 启动入口，读取映射后的共享文件 | Windows/WSL 实机待验；普通 Linux 测试不替代 WSL |

不要求 Linux 使用 iCloud。选择该平台可用、能提供完整本地副本的同步工具；WSL 还可通过 Windows 的文件挂载访问同一来源。

Codex、Claude Code、Gemini CLI、Cursor、OpenCode、Hermes 和 WorkBuddy 有目录模板；先核实实际客户端，再选择目录。MCP 设置支持情况以 .agents/mcp/targets/agents.json 为准，未知配置只给片段不猜写。名称和图标用于示意，不代表官方合作或全部兼容性通过。

自动化结果：[三平台检查通过](https://github.com/severusgao/agent-shared-system/actions/runs/38985722976)，代码提交 `dfa2b3d84ff277cebd3bdd9b9e8559240e8ff701`。这验证脚本和隔离文件接入，不代表每种 Agent、同步工具或 WSL 发行版已完成真实调用。
