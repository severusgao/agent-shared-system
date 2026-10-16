# Security and privacy

Do not post secrets, private memory, session databases or raw conversations in issues. Report a problem with a minimal fabricated reproduction. Use the maintainer contact shown on the GitHub profile; do not assume a private reporting channel exists.

Sync providers control file access. This project is not a sandbox, authentication layer, distributed lock, database or fine-grained ACL system. Treat third-party skills/scripts as untrusted code: inspect provenance and install only what is needed. Agent instructions do not prevent malicious tools from reading accessible files.

If a secret was published, revoke/rotate it at its provider and handle Git history; deleting the current file is not sufficient. Never scan or print a contributor's real credentials during checks.
