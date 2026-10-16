# 兼容性与验证边界

框架面向 macOS、Windows、独立 Linux 和 WSL。支持目录模板不等于当前版本客户端已加载；客户端发现和工具能力必须在实际设备验证。

| 环境 | 接入方式 | 首次公开版验证 |
|---|---|---|
| macOS | 本机逐技能 symlink；Memories/MCP 整目录链接 | 当前维护机的隔离环境运行，详见 release-audit.md |
| Windows | 本机逐技能 Junction；Memories/MCP 整目录 Junction | 自动测试入口已提供；实机使用待验 |
| 独立 Linux | Linux 本机逐技能 symlink 与整目录链接 | 自动测试入口已提供；实机使用待验 |
| WSL | 在选定发行版中运行 Linux 启动入口，读取映射后的共享文件 | Windows/WSL 实机待验；普通 Linux 测试不替代 WSL |

不要求 Linux 使用 iCloud。选择该平台可用、能提供完整本地副本的同步工具；WSL 还可通过 Windows 的文件挂载访问同一来源。

Codex、Claude Code、Gemini CLI、Cursor、OpenCode、Hermes 和 WorkBuddy 有目录模板；先核实实际客户端，再选择目录。MCP 设置支持情况以 .agents/mcp/targets/agents.json 为准，未知配置只给片段不猜写。名称和图标用于示意，不代表官方合作或全部兼容性通过。
