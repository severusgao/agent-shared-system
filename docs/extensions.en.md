# Optional extensions

[English](extensions.en.md) · [简体中文](extensions.md) · [Project home](../README.md)

The public framework includes four governance skills. Downloading it does not install every business CLI, model, MCP service or agent.

## Add an extension

Check the author's official source, license and a fixed version outside the shared source first. Use `agent-shared-skills` to compare existing coverage. Within the user's authorization, add the required instructions, scripts and resources, preserve copyright notices, and link host-specific setup instructions. Refresh discovery on each host and verify actual use. Link to an unlicensed third-party project rather than redistributing its content.

## REA: skill, local CLI and optional MCP

REA is an optional example, not a core dependency. Its [upstream repository](https://github.com/morluto/rea) owns installation and version requirements. Inspect the selected version's runtime needs, install the CLI locally and check `rea --version`. Prepare only engines actually needed and supported by that version.

[`rea.json`](../.agents/mcp/catalog/rea.json) describes cross-platform launch intent. Resolve commands locally, use `agent-shared-mcps` to preview the selected agent configuration, reconnect the client, enumerate tools and perform a supported call. Unverified entries do not inherit another computer's ready status. Never synchronize real credentials in a template.

## Example skills

The [method-only](../examples/clear-task/SKILL.md) and [Git CLI](../examples/git-status/SKILL.md) examples demonstrate structure. They do not install automatically. Review before copying into shared skills within authorization, then refresh local links and run the example's success check.
