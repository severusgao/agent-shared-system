# Public project maintenance

Use Chinese by default for collaboration; keep identifiers and API names unchanged.

- This checkout is the public framework, not a user's live installation.
- `.agents/skills/` owns shared methods; `.agents/memories/` owns maintained shared context; `.agents/mcp/` owns templates, not live configuration.
- Resolve paths from the current checkout or skill; never encode a person's username, drive or machine address as a default.
- Preserve one maintained source per rule. Link from summaries. Keep paired AGENTS.md and CLAUDE.md bodies identical within a directory.
- Consult the relevant core skill before maintenance. Read only task-relevant memory. Existing user authorization continues across necessary steps; respect explicit preview-only boundaries.
- Before changing user installations, preview exact paths. Preserve private/native skills, configurations and user memory. Never infer that another host is ready.
- Keep dependencies, secrets and actual Agent configuration local. Changes to MCP configuration use agent-shared-mcps.
- Tests must use temporary homes and sources. Never run installation tests against the maintainer's real home.
- Do not commit personal memory, session transcripts, runtime state, keys, caches or release binaries.
- Run relevant checks and report source, link, discovery and operational verification separately.

Memory relevance and candidate gates follow `.agents/skills/agent-shared-memories/references/TRIGGER_POLICY.md`.
