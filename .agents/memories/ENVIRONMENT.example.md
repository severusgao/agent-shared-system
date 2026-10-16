---
tags: [agents, memories]
created: 2026-10-16
updated: 2026-10-16
type: topic
status: stable
sources:
  - .agents/memories/SOURCES.md
---
# Environment

## Path Rules

Discover the current shared root from the skill or selected directory. Resolve Windows and WSL paths independently. A stored path is a hint, not proof of live state.

## Platforms

macOS, Windows, WSL and independent Linux are separate environments. Keep CLI, MCP processes, credentials and actual Agent configuration local. File availability is not runtime readiness.
