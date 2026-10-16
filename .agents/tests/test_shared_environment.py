from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from shared_environment import (  # noqa: E402
    ConcurrentStateChange,
    StateConflict,
    build_environment_identity,
    load_json_state,
    record_environment,
)


class EnvironmentIdentityTests(unittest.TestCase):
    def test_windows_identity_is_case_insensitive(self) -> None:
        upper = build_environment_identity(
            platform_name="windows",
            machine="ADMINISTRATOR",
            user="Administrator",
            home=r"C:\Users\Administrator",
        )
        mixed = build_environment_identity(
            platform_name="windows",
            machine="Administrator",
            user="Administrator",
            home=r"C:\Users\Administrator",
        )
        self.assertEqual(upper.environment_id, mixed.environment_id)
        self.assertEqual(upper.environment_id, "windows:administrator:administrator")
        self.assertEqual(mixed.machine_display, "Administrator")

    def test_wsl_distributions_have_distinct_ids(self) -> None:
        first = build_environment_identity(
            platform_name="wsl",
            machine="Administrator",
            user="gao",
            home="/home/gao",
            wsl_distro="Ubuntu-26.04",
        )
        second = build_environment_identity(
            platform_name="wsl",
            machine="Administrator",
            user="gao",
            home="/home/gao",
            wsl_distro="Ubuntu-24.04",
        )
        self.assertNotEqual(first.environment_id, second.environment_id)
        self.assertEqual(first.environment_id, "wsl:administrator:ubuntu-26.04:gao")

    def test_record_environment_merges_without_dropping_other_hosts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "shared_system_instances.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "environments": [{"environment_id": "macos:mac:user"}],
                    }
                ),
                encoding="utf-8",
            )
            identity = build_environment_identity(
                platform_name="windows",
                machine="Administrator",
                user="Administrator",
                home=r"C:\Users\Administrator",
            )
            record_environment(
                path,
                identity,
                unified_root=r"C:\Users\Administrator\.agents",
                windows_agents_root=None,
                audit={"skills": "ok", "mcp": "missing", "memories": "missing"},
            )
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(len(data["environments"]), 2)

    def test_concurrent_change_preserves_original(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            path.write_text('{"schema_version": 1, "environments": []}\n', encoding="utf-8")
            identity = build_environment_identity("linux", "server", "gao", "/home/gao")
            with self.assertRaises(ConcurrentStateChange):
                record_environment(
                    path,
                    identity,
                    unified_root="/home/gao/.agents",
                    windows_agents_root=None,
                    audit={},
                    before_replace=lambda: path.write_text(
                        '{"changed": true}\n', encoding="utf-8"
                    ),
                )
            self.assertEqual(
                json.loads(path.read_text(encoding="utf-8")), {"changed": True}
            )

    def test_existing_empty_state_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            path.write_text("", encoding="utf-8")
            identity = build_environment_identity("linux", "server", "gao", "/home/gao")
            with self.assertRaises(StateConflict):
                record_environment(
                    path,
                    identity,
                    unified_root="/home/gao/.agents",
                    windows_agents_root=None,
                    audit={},
                )
            self.assertEqual(path.read_text(encoding="utf-8"), "")

    def test_non_object_environment_entry_is_rejected_without_rewrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            original = '{"schema_version": 1, "environments": [null]}\n'
            path.write_text(original, encoding="utf-8")
            with self.assertRaisesRegex(
                StateConflict,
                "non-object environment at index 0",
            ):
                load_json_state(path)
            self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_duplicate_environment_ids_are_rejected_without_rewrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            original = json.dumps(
                {
                    "schema_version": 1,
                    "environments": [
                        {"environment_id": "linux:server:gao", "first_seen": "2026-07-13T00:00:00Z"},
                        {"environment_id": "linux:server:gao", "last_sync": "2026-07-13T01:00:00Z"},
                    ],
                }
            ) + "\n"
            path.write_text(original, encoding="utf-8")
            identity = build_environment_identity("linux", "server", "gao", "/home/gao")
            with self.assertRaisesRegex(
                StateConflict,
                "duplicate environment_id 'linux:server:gao'",
            ):
                record_environment(
                    path,
                    identity,
                    unified_root="/home/gao/.agents",
                    windows_agents_root=None,
                    audit={},
                )
            self.assertEqual(path.read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main()
