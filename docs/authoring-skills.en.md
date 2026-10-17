# Create, call and synchronize shared skills

[English](authoring-skills.en.md) · [简体中文](authoring-skills.md) · [Project home](../README.md)

## Route before creating

Use `agent-shared-skills` to compare the task, existing skills and available native tools. Reuse an existing capability when suitable. Extend within its existing responsibility; create a separate skill for a distinct reusable purpose.

A project-specific skill can say “When needed, read the shared `<name>` skill's SKILL.md.” The current agent resolves the actual path. Reference the skill instead of copying its body into another maintained source.

## Minimal layout

```text
.agents/skills/example-skill/
  SKILL.md
  references/SETUP.md   # For dedicated dependencies
  scripts/             # Small required scripts, not installed packages or virtual environments
```

The entry point has `name` matching its directory and `description` explaining when to use it. Explain purpose, inputs, steps, boundaries and success criteria. Link dependency instructions from the entry point. Preserve third-party provenance and licensing; link any local adaptation from the skill itself.

## Starter

````markdown
---
name: example-skill
description: Use when the user needs the specific reusable task described here.
---
# Example skill

## Purpose and boundaries
Explain when to use this skill and when to hand off.

## Inputs and steps
List required inputs, steps and stopping conditions.

## Local setup
Identify method-only, CLI, MCP, API or native capabilities.
When dedicated dependencies exist, read [setup](references/SETUP.md).

## Verify
Run a minimal real task and describe success and failure handling.
````

## Dependency types

| Type | Shared source | Prepare on each host | Verify |
|---|---|---|---|
| Method-only | Steps, templates and decision rules | The agent's current capabilities | Complete a minimal task |
| Skill + CLI | Instructions, required scripts and setup recipe | Compatible runtime and CLI | Check the version and run a real command |
| Skill + MCP | Instructions, catalog/template and setup recipe | Service, agent configuration and sign-in | Call a real tool in the current agent |

The setup recipe states required versus optional tools, version constraints, detection commands, official installation links, platform branches, manual sign-in and a success check. Windows and WSL are separate environments; standalone Linux follows its distribution. Mark unsupported or unverified cases honestly.

## Use on a new computer

Wait for the files → refresh local discovery links → read SKILL.md and setup instructions → inspect local dependencies → prepare them within authorization → run a minimal task. Another computer's successful installation does not establish this computer's readiness.

Prepare a skill's dependencies when needed rather than installing every extension in bulk. Programs, caches, credentials and live MCP configuration stay local.

## Publish a new shared skill

Use the installer preview/apply entry or scope the core sync helper to the intended agent and skills. Per-skill links do not automatically expose every new directory. Refresh the links after adding or renaming a skill, then reload according to the client's behavior.

See the [method-only example](../examples/clear-task/SKILL.md) and [Git CLI example](../examples/git-status/SKILL.md). They illustrate authoring and are not automatically installed.
