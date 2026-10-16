---
tags: [agents, memories]
created: 2026-10-16
updated: 2026-10-16
type: topic
status: stable
sources:
  - .agents/memories/SOURCES.md
---
# Decisions

## Shared Documentation Placement

Skills, memory, MCP templates and reviewed proposals have separate owners. Keep one maintained source per rule; summarize and link elsewhere. Paired AGENTS.md/CLAUDE.md are the project-entry exception.

## Shared Skills

The actual shared files live under this installation's .agents/skills. Each machine exposes them through local links. Skills can be called by project-specific skills and can evolve within user authorization.

## Shared Memories

Markdown is the maintained source; sync software transports local file copies. This framework does not provide distributed locks, automatic background approvals or model training.

## Shared MCP Registry

Share intent and recipes, derive actual configuration on each host. Do not synchronize real Agent config or credentials.

## Sample Query

演示约定：示例项目名为 Atlas。此条仅用于验证查询，不是使用者的真实业务信息。
