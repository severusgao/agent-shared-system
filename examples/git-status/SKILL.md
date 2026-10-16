---
name: git-status
description: 当用户要求只读检查某个 Git 仓库的当前工作区状态时使用。
---
# Git 工作区状态

使用前读取 [本机准备](references/SETUP.md)。只处理用户指定的仓库，不扫描磁盘。

运行 `git -C <仓库路径> status --short --branch`，说明分支、改动和未知项。不提交、不重置、不上传。路径以参数传递，不能拼成可执行 shell 代码。

最小验证：在临时目录创建一个空 Git 仓库，检查 status 返回成功，再清理本次临时目录。命令成功不证明业务改动正确。
