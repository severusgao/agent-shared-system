# External capabilities

A shared skill is an instruction package, not an installed program. Agent-native tools, account features, plugins and permissions vary by machine and client.

- Check current native tools before installing another implementation.
- Resolve CLI commands and versions locally. Follow the skill's setup guide; do not run unrelated upstream setup commands.
- Route MCP setup through agent-shared-mcps. Catalog availability does not establish that a server is configured, registered or operational.
- Keep binaries, environments, caches, credentials and live Agent configuration local.
- Do not copy private/native skills into the shared source without explicit scope and license review.
- Invocation flags differ by client. Validate the current Agent's discovery and loading rather than promise universal automatic invocation.
