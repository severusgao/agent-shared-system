---
tags: [agents, memories, paths]
created: 2026-07-05
updated: 2026-09-09
type: topic
status: stable
sources: []
---
# Paths

Use this reference when a machine path, vault boundary, or local skill link is unclear.

## Boundary

`AgentShared/.agents/` is the independent shared-system root. It contains `skills/`, `memories/`, `mcp/`, `scripts/`, and `state/`; it is not part of any Obsidian vault.

## Discovery Priority

1. From the current directory, search upward for `.agents/memories/INDEX.md`.
2. From this skill real path, derive the shared-system root.
3. Use `AGENT_SHARED_MEMORIES_ROOT` when set.
4. Use `~/.agents/memories` only as a last fallback when it resolves to a valid shared Memories directory.
5. If multiple candidates or none are found, ask the user.

Broken local links are evidence but do not override a valid shared source.

## Runtime Normalization

Resolver runtime metadata is normalized from `WSL_DISTRO_NAME`, `sys.platform`, and `os.name`:

- `platform`: one of `macos`, `windows`, `linux`, `wsl`
- `wsl_distro`: populated only when `WSL_DISTRO_NAME` is present

Path normalization uses `Path.expanduser()` and `Path.resolve()`. Do not hardcode a Windows drive letter, username, or iCloud mount point. When a WSL local entry points into `/mnt/<drive>/...`, keep that target as-is; do not rewrite it to a guessed Windows path.

## Local Stable Entry

Shared Memories are linked as one whole directory, not per file:

```text
macOS:
~/.agents/memories
-> <shared-system-root>/memories

Windows:
%USERPROFILE%\.agents\memories
-> <shared-system-root>\memories

WSL:
~/.agents/memories
-> /mnt/<drive>/Users/<windows-user>/.agents/memories
```

The legacy WSL wrapper follows the Windows local unified root; the public root setup may instead link directly to the verified mounted shared source. Do not create per-file Memory links. A `/mnt/<drive>/...` target may use any drive letter exposed by the current machine.

Windows display users such as `Administrator` are current-machine facts only. Do not turn them into general examples or path templates.

When creating the macOS stable entry, preview first. Only create the symlink after explicit apply/yes. If a real file, real directory, or wrong link already occupies `~/.agents/memories`, report the conflict and do not replace it automatically.

## Local Skill Discovery

The real skill copy remains in the shared system:

```text
AgentShared/.agents/skills/agent-shared-memories/
```

Local discovery entries point to that real copy:

```text
macOS:
~/.agents/skills/agent-shared-memories

Windows:
%USERPROFILE%\.agents\skills\agent-shared-memories
```

Use a symlink on macOS and a Junction on Windows.
