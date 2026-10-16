# 本机基础运行环境

核心 Python 工具要求 Python 3.12+。使用 python3 --version 或 py -3 --version 核实当前环境。元数据审计需要 PyYAML，版本固定在仓库根 requirements.txt。

从仓库根运行 `python3 scripts/setup.py --install-deps`（Windows 用 `py -3`），在当前电脑的私有数据目录建立虚拟环境；不把环境放入同步目录。安装依赖需要联网，仅在用户请求准备本机环境时执行。

macOS 可从 python.org 安装 Python；Windows 安装后检查 py/python 的实际解析；Linux 按发行版安装 Python 与 venv 支持。WSL 使用发行版内部的 Python，不复用宿主 Windows 的解释器。

CLI、Node、MCP、浏览器等均非核心统一必装项。只按目标技能的安装说明准备。版本检查之后，还需运行最小实际任务。
