# Contributing

Use a separate source checkout and a branch. Do not develop from a personal synchronized installation. Keep personal memory, state, tokens, logs and raw conversations out of commits.

Discuss behavior changes with a concrete trigger, current behavior, proposed result and validation. Keep one maintained source per rule; keep paired AGENTS.md and CLAUDE.md identical. Preserve upstream licenses for extensions.

Run `python3 -B scripts/check.py` and `python3 -B scripts/run_tests.py`. Windows uses `py -3 -X utf8`. Tests use isolated temporary roots. Add behavior tests for installer, query or safety changes; report actual OS/Agent validation separately from mocks.

Use the release builder only from a clean public source tree. Never export a user's live runtime directory. See docs/release-audit.md for limitations of the initial release.
