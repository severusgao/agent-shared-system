# Choosing between file-based and service-based memory

[English](comparison.en.md) · [简体中文](comparison.md) · [Project home](../README.md)

TencentDB Agent Memory is a strong service-based project with layered memory processing, a management panel, asset organization, permissions and agent connectivity. This comparison concerns deployment and collaboration tradeoffs, not a benchmark ranking.

Agent Shared System maintains skills, memory and rules in readable files, synchronizes copies to each computer, then relies on agents to retrieve, refine and review the relevant content.

## When files fit

- An individual moving between an office Windows PC and a home Mac.
- Several computers, standalone Linux or WSL, and several agents.
- A preference for directly readable, reviewable, portable files.
- Individuals or small teams with reliable synchronization and coordinated writing.

At home you can read background already synchronized locally without keeping the office computer online as a memory server. New content still depends on the chosen provider. Models and external tools may require a network connection.

## Tradeoffs

| Dimension | Agent Shared System | TencentDB Agent Memory |
|---|---|---|
| Sharing | Files synchronized to local copies | Clients request a common running backend |
| Deployment | No always-on memory service or database in the core | Can run locally, in WSL or on a server; shared clients need network access to it |
| Across locations | Use the file provider without a separate route to an office memory backend | Configure connectivity to the common backend |
| Concurrent use | Local reads; coordinate writes to the same file | The backend processes access and writes; validate behavior for the chosen deployment |
| Memory formation | Agent refinement, source checks, review and authorized text maintenance | Layered backend processing, deduplication and asset workflows |
| Content review | Organize independent agent review using file-review conventions | Inspected defaults include model processing and event records; those alone do not establish multi-agent cross-review |
| Retrieval | Topics, keywords, aliases, provenance and agent query expansion | BM25, optional vector retrieval and related tool interfaces |
| Permissions | Provider/folder permissions, no memory-level ACL | Team, user, asset visibility and permission management |
| Knowledge and code | No built-in Wiki compiler or code graph | Wiki and CodeGraph assets |
| Maintenance | Sync, file organization, local dependencies and review | Service, network, storage, models, backup and upgrades |

## Strengths and boundaries

Our strengths depend on the use case: local access across locations, readable and portable files, reusable methods across agents, reviewed evolution of rules and skills, and separation of formal conclusions from candidate evidence.

Both systems can be paired with an externally organized multi-agent review process. Independent review must actually happen. Several models repeating one source do not automatically improve reliability. Readability alone proves no factual correctness.

We have not compared same-task accuracy, recall, token cost or stability. Do not infer that this project is universally more advanced or produces better memory.

Evaluate Tencent's project for centralized automation, detailed team permissions and a rich asset backend. Consider this project for file-based continuity with a smaller memory-infrastructure footprint. The approaches can be combined or inform each other.

## Source scope

The Tencent observations come from static reading at commit `e9a82935b52741e0c798c75326e90b7144eb4d5f`, without deploying it. Consult current upstream documentation and validate behavior before adopting it.

- [Installation and positioning](https://github.com/TencentCloud/TencentDB-Agent-Memory/blob/e9a82935b52741e0c798c75326e90b7144eb4d5f/INSTALL_CN.md)
- [Default deduplication and failure handling](https://github.com/TencentCloud/TencentDB-Agent-Memory/blob/e9a82935b52741e0c798c75326e90b7144eb4d5f/MemoryCore/src/core/record/l1-dedup.ts)
- [Skill refinement prompt](https://github.com/TencentCloud/TencentDB-Agent-Memory/blob/e9a82935b52741e0c798c75326e90b7144eb4d5f/MemoryCore/src/core/skill/prompts/skill-review-prompt.ts)
- [Audit-event implementation](https://github.com/TencentCloud/TencentDB-Agent-Memory/blob/e9a82935b52741e0c798c75326e90b7144eb4d5f/MemoryCore/src/core/store/sqlite/memory-store.ts)
