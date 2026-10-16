# 历史证据接口

`scripts/evidence.py` 只采集用户可见消息及任务状态，不提取内部推理、工具调用正文、系统提示或运行配置。原生消息被标为 `excerpt`，须经 Agent 判断、核对和脱敏复核，才能成为共享证据摘要。

## 命令

```bash
python3 -B scripts/evidence.py discover
python3 -B scripts/evidence.py collect --output <本机路径/report.json>
python3 -B scripts/evidence.py collect --source codex:default:<本机Codex根>
python3 -B scripts/evidence.py collect --source hermes:office:<本机state.db> --days 30
python3 -B scripts/evidence.py import-summary --input <summaries.jsonl> --output <本机路径/import.json>
python3 -B scripts/evidence.py validate-package --package <package.json> --root <实际共享.agents根>
python3 -B scripts/evidence.py commit-review --report <本机report.json> --reference <已核对报告标识>
```

`--source` 可以重复，按前两个冒号切分，因此 Windows 盘符可以使用。显式来源替代默认发现。`--since`、`--until` 使用有时区的 ISO 时间；所有内部时间归一为 UTC，窗口为 `[since, until)`。首次默认 30 天，已有游标后默认 7 天；每个来源从更早的未复盘时间开始，避免间隔造成遗漏。展示日期使用用户时区。

输出默认在实际用户主目录的 `.agent-shared-evolution/runs/`。采集、导入和游标只允许写入该本机目录或系统临时目录，禁止指向共享根；检查解析后的路径，防止通过链接误写。首次调用不创建全局运行配置或安装依赖。

## 原生采集的限制

- Codex：扫描 sessions 与 archived_sessions 的实际事件；按 session 标识合并续写与归档；识别任务开始、完成和中断。忽略系统注入内容、推理与工具正文；默认排除标记为子 Agent 的继承历史。优先按原生消息 ID 去重，缺少 ID 时使用环境、角色、事件时间和可见文本指纹；不用文件名或修改时间判定周期。不同 ID 的语义重复仍需复核，不能当作多次独立纠正。
- Claude：区分真实 user 消息与 `tool_result`、元消息、sidechain；只提取可见文本。结束标记只给出 `completed_unverified`。
- Hermes：SQLite 只读事务读取 sessions/messages；只选取 user/assistant 的 content，不读取 reasoning 列。数据库结束时间不能证明成功；保留 parent_session_id 的关系，不把所有父子会话一概丢弃。
- 未识别的格式或缺失字段：列入 coverage 的 partial/missing；记录数量和定位线索，不猜测时间、结果或隐藏使用其他客户端格式。

发现结果只是本机入口，不是其他设备在线证明。原生采集结果不允许直接复制为共享档案。

单条 `excerpt` 最多 2400 字符，超出时保留 `truncated: true` 与原记录引用。需要判断的内容被截断时，按 `origin_ref` 在来源设备补读必要原文，或将该项保留待复核；不要把摘录当作全文。覆盖报告列出截断数量，消息数不能当作独立纠正次数。

## 摘要导入

每行 JSON 必须含：`schema_version: 1`、`environment_id`、`agent`、`profile`、`session_id`、`event_id`、`timestamp_utc`、`role`、`summary`、`outcome`、`origin_ref`。role 为 user/assistant/observation；outcome 为 unknown/open/aborted/completed_unverified/verified_success/verified_failure。verified 状态还必须有可复核的 `verification_ref`。

示例为结构说明，实际摘要必须引用真实来源：

```json
{"schema_version":1,"environment_id":"windows:machine:user","agent":"workbuddy","profile":"default","session_id":"actual-session-id","event_id":"actual-event-id","timestamp_utc":"2026-10-04T00:00:00Z","role":"observation","summary":"脱敏且已核对的实际发现","outcome":"verified_failure","origin_ref":"本机原记录标识","verification_ref":"实际失败检查记录"}
```

摘要必须核对说话者、条件、例外、否定、理由与真实结果，避免压缩改变原意。原始事件定位用于跨批去重；不同事件标识不自动证明不同事故。证据摘要继续使用 schema_version 1，不因审阅包升级到 v2 而更改。共享材料仅保留已审阅的 summary、事件标识、时间、结果与必要来源引用。自动脱敏覆盖常见密钥、凭据赋值、Authorization、Cookie、私钥及用户名路径；它不能证明所有敏感信息都已发现，导出前仍须内容复核。

## 审阅包

新模板使用 schema_version 2，逐项 platform_assessment 必须覆盖 macOS、Windows、WSL、独立 Linux，注明适用范围、影响、验证状态及验证方式；旧 schema_version 1 保留历史读取兼容。模板中的 candidates 最多五项，memory 项最多三项且属于同一相关组。每项包含 cause、owner、evidence_ids、existing_coverage、targets、exact_change、impact、validation、rollback、baseline 和 proposal_key。

baseline 的键是共享根内相对文件，值为 SHA-256；目标不存在时为 null。新候选添加 `proposal_revision` 和 `proposal_digest`，后者由 `scripts/review_contract.py` 的 `proposal_digest(candidate)` 计算，排除 status/digest 自身，涵盖完整候选内容与基线。修改内容先递增版本，再重算摘要；新提案结构校验要求完整版本和摘要，并拒绝不匹配的摘要。`validate-package --historical` 仅检查旧 v1/v2 结构，不补造批准；只读查询也保留历史兼容。历史缺少该字段时保留读取兼容，不补造批准。

Memories 候选可填写 `memory_update`，具体字段与质量规则见 [WRITE_POLICY](../../agent-shared-memories/references/WRITE_POLICY.md)。批准前保持 proposed；实际批准引用另记在决定记录，并携带 review_id、candidate_id、proposal_revision、proposal_digest。应用回执保存 candidate_id 到 proposal_digest 的 `proposal_digests` 映射、目标基线、作者摘要和验证引用；状态变化记录同一版本。`retracted` / `superseded` 说明撤回或替代依据及受影响条目。结构校验不构成批准、证据验证或写入授权。

## 决定记录与应用回执接口

`.agents/evolution/decisions.jsonl` 追加状态经过，不改写旧包或把提案快照当成当前状态。候选记录使用 `schema_version: 1`，携带同一 `review_id`、`candidate_id`、`proposal_revision`、`proposal_digest`、`decision` 和实际 `timestamp_utc`；批准含真实 `approval_ref`，应用含 `application_ref`，验证含 `verification_ref`。这些记录不改变审阅包 v2 或证据摘要 v1 的格式。

- `application_ref` 相对于 `.agents/evolution/` 根，例如 `actual-review/application.json`；共享验证材料的 `verification_ref` 同样使用 `actual-review/checks.json`。不要重复加 `.agents/evolution/`，也不复制应用机器的绝对路径作为共享回执入口。对话批准引用仍是批准材料标识，不要求是文件路径。
- `verified` 记录填写 `environment`，表示这次实际验证的平台，例如 `macos`、`windows` 或 `wsl`；机器及发行版身份可另外写入 `environment_id`。证据摘要仍使用自己的 `environment_id`，不能用它替代决定记录的 `environment`。设计适用范围、提案中的 platform_assessment 和文件同步不代表运行已验证。
- 应用回执的 `proposal_digests` 是 candidate_id 到批准摘要的映射；`authored_hashes` 的键相对于共享 `.agents/` 根，值为本批实际写入后的 SHA-256。完整原输出留本机，共享 verification_ref 指向精简检查材料。

保存后用[统一查询](../../agent-shared-memories/references/QUERY.md)复核本批候选的版本绑定、回执可读性、`current_target_match` 和 `verified_environments`，并核对原批准及真实检查。查询状态不代替这些检查，也不授予写入权限。本批新记录出现路径或环境缺失时，按追加原则补充本批纠正记录后复查，不覆盖已有决定；历史缺失保持未知，不补造旧验证。历史已实施包因后续变更不再匹配当前目标，只表示其旧检查不能证明当前文件，不自动变成新的待审包。

## 差异附件

`change_artifacts` 是候选中的可选映射：`{"patches/change.diff":"文件的SHA256"}`，路径相对于该审阅包目录。准确差异直接写在候选中时无需附件；引用外部差异、逐字操作等材料时登记全部用于确定改动的附件。附件摘要随完整候选进入 `proposal_digest`，不另建批准机制。

默认严格模式从 `--package` 所在目录核验实际文件；缺失、摘要不符、绝对路径、父目录跳转或链接越界均失败。Python 调用在存在附件时须传入 `package_dir`。内容改变后先停止应用，重新准备提案版本和摘要，旧批准不转移；不能只改同名附件。声明为空或省略时保持现有内联差异用法。

`--historical` 仅核验附件声明格式，供旧材料追溯，不确认附件当前可用，也不补造批准；正式应用使用默认严格模式。传入 `--root` 才核对正式目标基线，历史模式也不会绕过这一检查。校验通过只表示这些检查通过，不表示用户批准、证据真实或可以写入。
