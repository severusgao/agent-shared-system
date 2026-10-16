---
tags: [agents, skills, paths]
created: 2026-07-06
updated: 2026-09-14
type: reference
status: stable
sources: []
---
# Paths

`AgentShared/.agents/` is the shared-system root. Shared skills are stored there:

```text
AgentShared/.agents/skills/<skill>
```

Do not write shared skills outside the shared-system root. Do not treat `.agents/` as an Obsidian vault.

Canonical shared-system sources are:

```text
.agents/skills/    shared skill real copies
.agents/memories/  shared long-term memory real copy
.agents/mcp/       shared MCP registry and templates
.agents/scripts/   onboarding, audit, and resolver scripts
.agents/state/     shared system environment state
```

These directories are siblings inside the shared system. Do not move live Agent configs, secrets, package installs, or cache directories into them.

Shared MCP registry entries live in a separate shared-system directory:

```text
AgentShared/.agents/mcp/
```

Use `agent-shared-mcps` for that directory. Do not mix MCP registry files with skill discovery links.

Shared Memories live in `.agents/memories/` and are governed by `agent-shared-memories`. Do not create per-file memory links from this skill.

## Discovery Priority

1. From this skill's real path, infer the shared-system root from `.agents/skills/agent-shared-skills/`.
2. From the current directory, search upward for `.agents/skills/`.
3. Use `AGENT_SHARED_SKILLS_ROOT` when set.
4. Use `AGENT_SHARED_SYSTEM_ROOT` when set, appending `skills`.
5. Inspect the local discovery entry for `agent-shared-skills` and resolve its symlink or Junction target.
6. If multiple candidates or none are found, ask the user.

## Local Discovery Entries

Local Agent discovery entries point to shared-system real copies:

```text
macOS:
~/.agents/skills/<skill>

Windows:
%USERPROFILE%\.agents\skills\<skill>
```

macOS uses symlinks. Windows uses Junctions. The left side is stable for the current user on that machine; the right-side target is machine-specific.

Current Windows usernames shown in state, such as `Administrator`, are machine facts. Do not use them as portable registry templates or documentation defaults.

## Two Link Layers

Keep the two layers separate:

```text
Layer 1:
AgentShared/.agents/skills/<skill>
-> ~/.agents/skills/<skill>
-> %USERPROFILE%\.agents\skills\<skill>

Layer 2:
~/.agents/skills/<skill>
-> each Agent's own skills directory/<skill>

%USERPROFILE%\.agents\skills\<skill>
-> each Agent's own skills directory\<skill>
```

Layer 1 uses the same transactional link helper through `.agents/scripts/deploy-cloud-skills-macos.command` and `.agents/scripts/deploy-cloud-skills-windows.cmd`.

Layer 2 is handled by `scripts/sync_agent_skill_links.py` in this skill. It links Agent entries to local unified entries that resolve to shared-source shared skills, not directly to one machine's iCloud path. Local-only entries in the unified root are ignored.

For first-time onboarding, use the recommended two-stage launchers:

```text
.agents/scripts/macos-skill-sync.command
.agents/scripts/windows-skill-sync.cmd
```

They run Layer 1 first, then ask for one Agent skills directory and run Layer 2 for that target.

There is no background sync. Scripts and helpers preview their planned writes and require explicit approval or `--apply --yes` before changing links or state.

## WSL Link Model

The legacy WSL wrapper follows the Windows unified root. For a fresh public installation, prefer the project root setup, which accepts the current verified mounted shared source. The legacy route is:

```text
Windows unified root:
%USERPROFILE%\.agents\skills\<skill>

WSL unified root:
~/.agents/skills/<skill>
-> /mnt/<drive>/Users/<windows-user>/.agents/skills/<skill>
```

Only shared-source Windows unified skill entries are imported into WSL. Memories and MCP are not per-skill: WSL uses whole-directory links for `~/.agents/memories` and `~/.agents/mcp`, governed by `agent-shared-memories` and `agent-shared-mcps`.

If WSL can create links but cannot write shared state because `python3` or required runtime support is missing, report `state_pending` and rerun the audit after Python is available.

The Windows WSL launcher asks for the Agent directory as a Linux absolute path
inside the selected distribution, for example `/home/name/.codex/skills`.
Do not enter a Windows path or a `\\wsl.localhost\...` Explorer path. The
launcher displays the selected WSL user's `HOME`, validates the input, runs the
worker as that user, verifies every link after apply, and records the WSL Agent
instance when Python is available.

`.agents/scripts/wsl-shared-system-sync.sh` is the internal WSL worker. It is
called by `windows-wsl-shared-sync.cmd` with discovered paths and is not a
desktop GUI entry point.

## Agent Skills Directory Input

The user should enter the directory that the target Agent reads as its skills root, not a specific skill folder.

These are equivalent after normalization:

```text
macOS:
/Users/name/.workbuddy/skills
/Users/name/.workbuddy/skills/

Windows:
C:\Users\name\.workbuddy\skills
C:\Users\name\.workbuddy\skills\
```

Do not enter a specific skill entry such as:

```text
/Users/name/.workbuddy/skills/agent-shared-skills
C:\Users\name\.workbuddy\skills\agent-shared-skills
```

The helper script strips outer quotes, handles spaces, expands `~`, `$HOME`, and `%USERPROFILE%`, and warns when the path appears to be one skill entry so the parent skills directory can be reviewed. Apply rejects such implicit normalization; pass the intended root explicitly. The directory name does not have to be exactly `skills`; use the Agent's actual discovery directory, such as `skills-cursor`, when that is what the Agent reads.

## Recorded Agent Instances

Successfully applied Agent syncs are recorded in:

```text
.agents/skills/agent-shared-skills/state/agent_skill_instances.json
```

These records are current-machine facts for auditing and repair. Absolute paths in this state file are not universal path rules and must not be copied into templates for other computers.

State records use environment identities:

```text
macos:<machine-key>:<user>
windows:<machine-key>:<user>
linux:<machine-key>:<user>
wsl:<windows-host-machine-key>:<distro>:<linux-user>
```

The machine key is case-insensitive. Display names preserve the observed machine text only for human readability.

Record status semantics:

- `current`: record belongs to the active environment.
- `other_environment`: record belongs to another machine, OS, or WSL distro and should be rendered as metadata unless explicitly targeted.
- `conflict`: a planned filesystem target already exists in a form that cannot be safely replaced without explicit approval.
- `state_pending`: filesystem exposure may be complete but state could not be recorded; rerun audit later.

## Multi-Windows Rule

Every Windows computer can mount iCloud at a different absolute path. Never turn one Windows drive letter, username, or iCloud mount into a universal rule.

The Junction target must be:

```text
<that machine's actual AgentShared path>\.agents\skills\<skill>
```

Use the deploy script or path discovery instead of hardcoding a Windows target.

Agent-specific skill directories also use templates, not one machine's absolute path. See `references/AGENT_TARGETS.md`.

## Examples Only

These examples are not universal rules:

```text
macOS example:
<current-iCloud-Drive>/AgentShared

Windows example:
<current-machine-iCloud-mount>\AgentShared
```

Command examples with an `.agents/` prefix run from the shared root's parent; omit that prefix when already in the shared root. Python 3.12+ and PyYAML are machine-local dependencies for the Python audit tools. Use `-B` to keep caches out of the shared source.
