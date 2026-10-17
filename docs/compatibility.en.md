# Compatibility and validation

[English](compatibility.en.md) · [简体中文](compatibility.md) · [Project home](../README.md)

The framework targets macOS, Windows, standalone Linux and WSL. A directory template is not proof that the current client discovers it. Validate discovery and tool operation on the actual device.

| Environment | Local entry | Validation |
|---|---|---|
| macOS | Per-skill symlinks; directory links for memories and MCP templates | Maintainer's isolated tests and GitHub macOS runner checks passed; actual client discovery is separate. |
| Windows | Per-skill Junctions; directory Junctions for memories and MCP templates | GitHub Windows runner isolated onboarding passed; actual desktop-client use remains to be verified. |
| Linux | Per-skill symlinks and directory links | GitHub Ubuntu runner isolated onboarding passed; actual client use remains to be verified. |
| WSL | Run Linux onboarding in the selected distribution against mounted shared files | Windows/WSL real-device behavior remains to be verified; Ubuntu CI does not establish WSL readiness. |

The platform badges identify intended setup environments and link to this table. They do not assert that every agent works on every platform.

## Agent templates

The installer provides directory templates for Codex, Claude Code, Gemini CLI, Cursor, OpenCode, Hermes and WorkBuddy. Confirm the current client's discovery mechanism before choosing a directory. Use `--target-dir` when appropriate.

MCP rendering and registration methods are listed in [`agents.json`](../.agents/mcp/targets/agents.json). Unknown clients receive a configuration fragment rather than a guessed live-config write. Hermes's skills entry does not establish Hermes Gateway integration. Names and icons imply neither endorsement nor universally verified compatibility.

## Evidence

[Three-platform checks](https://github.com/severusgao/agent-shared-system/actions/runs/38985722976) passed for commit `dfa2b3d84ff277cebd3bdd9b9e8559240e8ff701`. These are source and isolated filesystem checks, not real-model or all-client tests. See [current CI](https://github.com/severusgao/agent-shared-system/actions/workflows/check.yml) for subsequent runs and [the initial audit](release-audit.md) for the original validation record.

## Synchronization

The main walkthrough uses iCloud on macOS/Windows, with WSL reading the Windows folder. Standalone Linux can use an available provider such as Syncthing. The framework documents provider choices without installing or managing the sync software.
