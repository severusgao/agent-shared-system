from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


FIXTURE_PARENT = os.environ.get("AGENT_TEST_TMPDIR") or (str(Path(os.environ["SystemRoot"]) / "Temp") if os.name == "nt" else None)

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import resolve_memories_root as resolver_module  # noqa: E402
from lint_memories import REQUIRED_FILES  # noqa: E402
from resolve_memories_root import ensure_local_entry, resolve  # noqa: E402


class ResolveMemoriesRootTests(unittest.TestCase):
    def _current_skill_memories_root(self) -> Path:
        return Path(resolver_module.__file__).resolve().parents[3] / "memories"

    def _create_memories_root(self, root: Path) -> Path:
        root.mkdir(parents=True, exist_ok=True)
        for name in REQUIRED_FILES:
            (root / name).write_text(
                "\n".join(
                    [
                        "---",
                        "tags: [agents, memories]",
                        "created: 2026-07-05",
                        "updated: 2026-07-20",
                        "type: topic",
                        "status: stable",
                        "sources: []",
                        "---",
                        f"# {name}",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
        return root

    def test_prefers_skill_realpath_over_stale_local_entry_outside_vault(self) -> None:
        with tempfile.TemporaryDirectory(dir=FIXTURE_PARENT) as tmp:
            base = Path(tmp)
            fake_home = base / "home"
            fake_home.joinpath(".agents").mkdir(parents=True)
            stale_root = self._create_memories_root(base / "stale-vault" / ".agents" / "memories")
            local_entry = fake_home / ".agents" / "memories"
            local_entry.symlink_to(stale_root, target_is_directory=True)

            local_result = resolve(start=base / "outside", home=fake_home, env={})

            self.assertEqual(local_result["method"], "skill-realpath")
            self.assertEqual(
                Path(local_result["memories_root"]),
                self._current_skill_memories_root().resolve(),
            )
            self.assertFalse(local_result["local_entry_matches_root"])

    def test_prefers_cwd_upward_over_local_entry(self) -> None:
        with tempfile.TemporaryDirectory(dir=FIXTURE_PARENT) as tmp:
            base = Path(tmp)
            fake_home = base / "home"
            fake_home.joinpath(".agents").mkdir(parents=True)
            vault_root = base / "vault"
            memories_root = self._create_memories_root(vault_root / ".agents" / "memories")
            other_root = self._create_memories_root(base / "other-vault" / ".agents" / "memories")
            (fake_home / ".agents" / "memories").symlink_to(other_root, target_is_directory=True)

            upward_result = resolve(start=vault_root / "workdb", home=fake_home)

            self.assertEqual(upward_result["method"], "cwd-upward")
            self.assertEqual(Path(upward_result["memories_root"]), memories_root.resolve())

    def test_broken_local_entry_warns_and_falls_back(self) -> None:
        with tempfile.TemporaryDirectory(dir=FIXTURE_PARENT) as tmp:
            base = Path(tmp)
            fake_home = base / "home"
            fake_home.joinpath(".agents").mkdir(parents=True)
            vault_root = base / "vault"
            self._create_memories_root(vault_root / ".agents" / "memories")
            (fake_home / ".agents" / "memories").symlink_to(
                fake_home / "missing",
                target_is_directory=True,
            )

            fallback_result = resolve(start=vault_root, home=fake_home)

            self.assertTrue(fallback_result["ok"])
            self.assertIn("broken local stable entry", fallback_result["warnings"])

    def test_prefers_agent_shared_memories_root_over_local_when_skill_unavailable(self) -> None:
        with tempfile.TemporaryDirectory(dir=FIXTURE_PARENT) as tmp:
            base = Path(tmp)
            fake_home = base / "home"
            fake_home.joinpath(".agents").mkdir(parents=True)
            local_root = self._create_memories_root(base / "local" / ".agents" / "memories")
            agent_root = self._create_memories_root(base / "agent-root" / ".agents" / "memories")
            (fake_home / ".agents" / "memories").symlink_to(local_root, target_is_directory=True)

            with mock.patch.object(resolver_module, "_candidate_from_skill", return_value=None):
                env_result = resolve(
                    start=base / "outside",
                    home=fake_home,
                    env={
                        "AGENT_SHARED_MEMORIES_ROOT": str(agent_root),
                    },
                )

            self.assertEqual(env_result["method"], "AGENT_SHARED_MEMORIES_ROOT")
            self.assertEqual(Path(env_result["memories_root"]), agent_root.resolve())

    def test_uses_local_entry_only_after_cwd_skill_and_env_candidates_fail(self) -> None:
        with tempfile.TemporaryDirectory(dir=FIXTURE_PARENT) as tmp:
            base = Path(tmp)
            fake_home = base / "home"
            fake_home.joinpath(".agents").mkdir(parents=True)
            local_root = self._create_memories_root(base / "local" / ".agents" / "memories")
            (fake_home / ".agents" / "memories").symlink_to(local_root, target_is_directory=True)

            with mock.patch.object(resolver_module, "_candidate_from_skill", return_value=None):
                result = resolve(start=base / "outside", home=fake_home, env={})

            self.assertEqual(result["method"], "local-stable-entry")
            self.assertEqual(Path(result["memories_root"]), local_root.resolve())

    def test_reports_wsl_runtime_metadata_and_mnt_target(self) -> None:
        with tempfile.TemporaryDirectory(dir=FIXTURE_PARENT) as tmp:
            base = Path(tmp)
            fake_home = base / "home"
            fake_home.joinpath(".agents").mkdir(parents=True)
            mnt_root = self._create_memories_root(base / "mnt" / "d" / "Users" / "Alice" / ".agents" / "memories")
            local_entry = fake_home / ".agents" / "memories"
            local_entry.symlink_to(mnt_root, target_is_directory=True)

            with mock.patch.object(resolver_module, "_candidate_from_skill", return_value=None):
                result = resolve(
                    start=base / "outside",
                    home=fake_home,
                    env={"WSL_DISTRO_NAME": "Ubuntu-26.04"},
                    sys_platform_name="linux",
                    os_name_value="posix",
                )

            self.assertEqual(result["platform"], "wsl")
            self.assertEqual(result["wsl_distro"], "Ubuntu-26.04")
            self.assertEqual(result["method"], "local-stable-entry")
            self.assertTrue(Path(result["local_entry_target"]).samefile(mnt_root))

    def test_reports_linux_runtime_metadata(self) -> None:
        with tempfile.TemporaryDirectory(dir=FIXTURE_PARENT) as tmp:
            base = Path(tmp)
            memories_root = self._create_memories_root(base / "vault" / ".agents" / "memories")

            result = resolve(
                start=memories_root,
                env={},
                sys_platform_name="linux",
                os_name_value="posix",
            )

            self.assertEqual(result["platform"], "linux")
            self.assertIsNone(result["wsl_distro"])
            self.assertEqual(result["sys_platform"], "linux")
            self.assertEqual(result["os_name"], "posix")

    def test_preview_then_apply_gate_creates_missing_local_entry(self) -> None:
        with tempfile.TemporaryDirectory(dir=FIXTURE_PARENT) as tmp:
            base = Path(tmp)
            fake_home = base / "home"
            canonical_root = self._create_memories_root(base / "vault" / ".agents" / "memories")

            preview = ensure_local_entry(canonical_root, home=fake_home)
            self.assertEqual(preview["action"], "create")
            self.assertFalse(preview["performed"])
            self.assertFalse((fake_home / ".agents" / "memories").exists())

            gated = ensure_local_entry(canonical_root, home=fake_home, apply=True, yes=False)
            self.assertEqual(gated["action"], "create")
            self.assertFalse(gated["performed"])
            self.assertFalse((fake_home / ".agents" / "memories").exists())

            applied = ensure_local_entry(canonical_root, home=fake_home, apply=True, yes=True)
            self.assertEqual(applied["action"], "create")
            self.assertTrue(applied["performed"])
            self.assertTrue((fake_home / ".agents" / "memories").is_symlink())

    def test_existing_matching_local_entry_is_left_unchanged(self) -> None:
        with tempfile.TemporaryDirectory(dir=FIXTURE_PARENT) as tmp:
            base = Path(tmp)
            fake_home = base / "home"
            fake_home.joinpath(".agents").mkdir(parents=True)
            canonical_root = self._create_memories_root(base / "vault" / ".agents" / "memories")
            local_entry = fake_home / ".agents" / "memories"
            local_entry.symlink_to(canonical_root, target_is_directory=True)

            result = ensure_local_entry(canonical_root, home=fake_home, apply=True, yes=True)

            self.assertEqual(result["action"], "skip")
            self.assertFalse(result["performed"])
            self.assertTrue(local_entry.is_symlink())
            self.assertEqual(local_entry.resolve(), canonical_root.resolve())

    def test_conflict_does_not_replace_real_directory(self) -> None:
        with tempfile.TemporaryDirectory(dir=FIXTURE_PARENT) as tmp:
            base = Path(tmp)
            fake_home = base / "home"
            local_entry = fake_home / ".agents" / "memories"
            local_entry.mkdir(parents=True)
            canonical_root = self._create_memories_root(base / "vault" / ".agents" / "memories")

            result = ensure_local_entry(canonical_root, home=fake_home, apply=True, yes=True)

            self.assertEqual(result["action"], "conflict")
            self.assertFalse(result["performed"])
            self.assertTrue(local_entry.is_dir())

    def test_lint_cli_without_root_uses_skill_realpath_before_local_stable_entry(self) -> None:
        with tempfile.TemporaryDirectory(dir=FIXTURE_PARENT) as tmp:
            base = Path(tmp)
            fake_home = base / "home"
            fake_home.joinpath(".agents").mkdir(parents=True)
            canonical_root = self._create_memories_root(base / "vault" / ".agents" / "memories")
            (fake_home / ".agents" / "memories").symlink_to(
                canonical_root,
                target_is_directory=True,
            )
            unrelated = base / "outside"
            unrelated.mkdir()
            script = SCRIPT_DIR / "lint_memories.py"
            env = dict(os.environ)
            env["HOME"] = str(fake_home)
            env["USERPROFILE"] = str(fake_home)

            completed = subprocess.run(
                [sys.executable, str(script), "--format", "json"],
                cwd=unrelated,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["root"], str(self._current_skill_memories_root().resolve()))
            self.assertEqual(payload["root_source"], "skill-realpath")
            self.assertEqual(payload["local_entry_kind"], "symlink")

    def test_lint_cli_explicit_root_wins(self) -> None:
        with tempfile.TemporaryDirectory(dir=FIXTURE_PARENT) as tmp:
            base = Path(tmp)
            fake_home = base / "home"
            fake_home.joinpath(".agents").mkdir(parents=True)
            local_root = self._create_memories_root(base / "local" / ".agents" / "memories")
            explicit_root = self._create_memories_root(base / "explicit" / ".agents" / "memories")
            (fake_home / ".agents" / "memories").symlink_to(
                local_root,
                target_is_directory=True,
            )
            unrelated = base / "outside"
            unrelated.mkdir()
            script = SCRIPT_DIR / "lint_memories.py"
            env = dict(os.environ)
            env["HOME"] = str(fake_home)
            env["USERPROFILE"] = str(fake_home)

            completed = subprocess.run(
                [sys.executable, str(script), "--root", str(explicit_root), "--format", "json"],
                cwd=unrelated,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["root"], str(explicit_root.resolve()))
            self.assertEqual(payload["root_source"], "explicit")
            self.assertTrue(Path(payload["local_entry_target"]).samefile(local_root))


if __name__ == "__main__":
    unittest.main()
