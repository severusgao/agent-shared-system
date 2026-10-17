# Setup and a second computer

[English](getting-started.en.md) · [简体中文](getting-started.md) · [Project home](../README.md)

## Prepare

1. Choose a synchronization provider. This guide uses iCloud Drive as its main example; Syncthing is an open-source alternative. For teams, choose a provider and sharing arrangement suited to the members rather than sharing one personal account.
2. Download the versioned ZIP from [Releases](https://github.com/severusgao/agent-shared-system/releases/latest). Extract the entire project into its final shared folder. Keep the hidden `.agents` directory and download the files locally before linking them. Choose the location first.
3. Install Python **3.12+** and an agent in the current environment. Git, Node, Docker, a database and a server are not core prerequisites.

## Choose a sync provider

- **iCloud Drive:** use the existing macOS/Windows client and keep the project files available locally. WSL may read the Windows-mounted folder. See [Apple's setup guide](https://support.apple.com/guide/icloud/set-up-icloud-drive-mm203b05aec8/icloud). An official Linux iCloud client is not assumed.
- **Syncthing:** use the release for your operating system from [the official project](https://github.com/syncthing/syncthing), then follow its [setup guide](https://docs.syncthing.net/intro/getting-started.html). Share the project source, including `.agents`, between the chosen devices and wait for synchronization before local onboarding.

Choose one sync engine for a folder. For Syncthing, use a regular local folder outside iCloud or another provider's managed directory. Share the project source rather than your agent home or its local links. Keep credentials, live MCP configuration and Syncthing's runtime database local; contributors also exclude `.git` metadata.

Syncthing exchanges new content when devices are online and connected at overlapping times. If your office and home computers are never online together, another computer or NAS can retain and forward changes. This is an optional file-sync node. Already-synchronized files remain locally readable. See [Syncthing's explanation](https://docs.syncthing.net/users/faq.html#what-is-syncthing).

For WSL, prefer the Windows-synchronized project folder with the distro's own agent and dependencies. The sync software is an external choice, not a bundled part of this framework.

## Run the entry point

| Environment | Action |
|---|---|
| macOS | Run `Start.command`. If the system blocks it, run `bash Start.command` from the inspected project directory rather than disabling system protections. |
| Windows | Run `Start-Windows.cmd`. It uses the existing Python for that process without changing global execution policy. |
| Linux | Run `bash Start-Linux.sh` in the project directory. |
| WSL | Enter the intended distribution, resolve its mounted Windows project path, and run `bash Start-Linux.sh`. Do not copy another computer's drive letter or distro path. |

The launcher asks for an agent and its actual skills directory. Defaults are directory templates; confirm that your current client reads the selected location. It displays a plan before applying it. Existing private directories, foreign links or linked parents cause a conflict rather than silent replacement.

If PyYAML is missing, the interactive entry point offers to prepare a local Python environment. Dependency installation accesses the network. You can also run these commands from the project folder:

```bash
python3 -B scripts/setup.py --install-deps
python3 -B scripts/setup.py --agent codex
python3 -B scripts/setup.py --agent codex --apply
```

On Windows, replace `python3` with `py -3 -X utf8`. Dependency preparation installs the core Python requirements; the agent, business CLIs, MCP services and their sign-in remain separate.

## Ask your agent to help

Substitute the real local project path in this prompt. Before discovery is set up, the agent can read the project files directly.

> Read `<local-project-path>/README.md`, `docs/getting-started.en.md` and `.agents/skills/agent-shared-skills/SKILL.md`. Confirm my current OS, WSL distribution if applicable, shared source and actual agent skills directory. Preview setup.py paths and preserve existing private skills. Apply the needed links within my onboarding authorization, prepare this machine's dependencies, then verify core-skill discovery and an Atlas sample-memory query. Prepare optional MCPs only when needed. Keep credentials local and do not treat another computer's status as proof this one is ready.

## Verify four stages

1. **Files:** read the four core skills and memory templates under `.agents`.
2. **Links:** preview setup again; the intended entries should report `skip`.
3. **Discovery:** reload the agent or start a new session and confirm it actually lists and reads `agent-shared-skills`.
4. **Operation:** ask the agent to follow the memory relevance policy and query **Atlas**, explicitly identifying it as a fictional sample rather than a fact about the user.

```bash
python3 -B .agents/skills/agent-shared-memories/scripts/query_memories.py --term Atlas --scope current --format json
```

Initialization creates only missing blank personal pages and state files. Existing content is preserved. Remove the fictional sample only within the user's authorization and without deleting real memory.

## A second computer

Wait for the same logical source to arrive locally, then run that environment's entry point. Do not reapply public templates over existing personal memory. Verify dependencies, sign-in, MCP setup and discovery separately. After adding a shared skill, refresh the local per-skill links and reload the client as needed.

Local files may remain readable offline. Synchronization, model requests and external tools may require a connection.

## Teams and conflicts

Choose a provider with an appropriate member-sharing model. This is file collaboration, with no memory-level ACL or distributed lock. Assign one writer for a shared rule or batch of edits; other members propose changes, wait for synchronization and review them. Compare and merge conflict copies explicitly.

## Update, move or remove

Back up the current installation. Inspect a new release separately, then update framework files using the release changes as a checklist. Preserve personal memory, evolution records and local configuration. Do not overwrite an entire personal installation with a fresh ZIP.

Moving the shared source may break old links. Preview again and inspect the old source before changing any existing entry.

```bash
python3 -B scripts/setup.py --agent codex --uninstall --apply
```

Removal unlinks only entries still pointing at this project. It retains shared data, private entries, configuration and the local Python environment. Inspect the dedicated runtime path separately if you also want to remove it.
