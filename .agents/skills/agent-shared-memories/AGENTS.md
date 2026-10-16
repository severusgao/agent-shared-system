# Shared memory maintenance

Follow references/TRIGGER_POLICY.md and run the Memory Relevance Gate first.
If the gate does not match, do not resolve or read shared memory.
When it matches, resolve `.agents/memories/` from the current shared source.
Read `INDEX.md` (the same `.agents/memories/INDEX.md`) and only relevant sections.
This is the order: Memory Relevance Gate → resolve `.agents/memories/` → Read `INDEX.md` → Read `.agents/memories/INDEX.md`.
Follow READ_PROTOCOL.md for use and WRITE_POLICY.md for changes. User authorization must cover formal changes; do not mistake a candidate or assistant suggestion for approval.
Keep source conditions, exceptions and evidence. Never publish private user content. Validate after formal changes.
