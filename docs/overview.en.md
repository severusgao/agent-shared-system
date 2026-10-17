# How the shared system works

[English](overview.en.md) · [简体中文](overview.md) · [Project home](../README.md)

## Across computers

![Cross-platform architecture](../assets/architecture.en.png)

One logical shared source is synchronized to local copies. The agent placements illustrate a possible arrangement, not platform certification. WSL may read mounted Windows files; standalone Linux is a separate lane.

## Four governance entries

| Entry | Responsibility | When to use it |
|---|---|---|
| `agent-shared-skills` | Route, create, install, synchronize and maintain skills | Choose a skill, inspect dependencies or onboard an agent |
| `agent-shared-memories` | Query context, track provenance and maintain approved memory | Restore relevant background or review a lasting conclusion |
| `agent-shared-mcps` | Maintain catalogs and local setup recipes | Prepare an MCP service and verify a call in the current agent |
| `agent-shared-evolution` | Collect evidence, review improvements and check effects | Investigate a reusable cross-component issue |

Project-specific skills can call a shared skill by name. Formal changes follow the user's current authorization and any review boundary they explicitly retained.

## A new skill reaches another computer

Task → route and compare existing capabilities → reuse or author the skill → review instructions and dependencies → synchronize files → refresh local discovery → prepare local CLI/MCP dependencies → verify a real task.

The entry point explains purpose, triggers, inputs, steps, boundaries, setup and success. Another computer reads those instructions and checks its own environment.

## Shared files and local tools

| Type | Shared | Local |
|---|---|---|
| Method-only skill | Steps, rules and templates | Current native capabilities |
| Skill + CLI | Instructions, required scripts and setup guide | Runtime and CLI installation |
| Skill + MCP | Instructions, catalog and configuration template | Service, live client config and credentials |

File availability, discovery, dependency readiness and actual operation are separate stages. Active databases, installed programs and credentials remain local.

## First use

Download the release → choose the final sync folder → have the agent read the setup guide → inspect the host → preview changes → apply within authorization → reload the client → query the fictional sample.

The walkthrough uses iCloud. Syncthing and other suitable tools can provide file synchronization instead. A single-computer installation can use a local folder without a sync provider. A new device uses existing memory rather than replacing it with public starter content.

## Office, home and a small team

Already-synchronized files can be read without keeping an office memory host online. New changes still depend on the provider's availability model. Coordinate edits to the same file and choose suitable member permissions.

TencentDB Agent Memory is a strong service-based alternative for centralized automation and management. This project's strengths are file portability and local access across computers; it makes no comparative quality claim. Read the [comparison](comparison.en.md).

## Icons

Client names and icons identify examples, not official endorsement. Codex uses the OpenAI developer-site favicon. See [attribution](../assets/ATTRIBUTION.md) for all five icon sources.
