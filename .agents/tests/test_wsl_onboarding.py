from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "wsl-shared-system-sync.sh"


@unittest.skipIf(os.name == "nt", "Run POSIX onboarding integration tests inside WSL.")
class WslSharedSystemSyncTests(unittest.TestCase):
    def test_preview_mode_does_not_modify_links(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = WslFixture(Path(tmp))
            result = fixture.run()

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("preview", result.stdout.casefold())
            self.assertFalse((fixture.linux_home / ".agents" / "skills" / "alpha").exists())
            self.assertFalse((fixture.linux_home / ".agents" / "mcp").exists())
            self.assertFalse(fixture.state_file.exists())

    def test_apply_links_shared_layers_and_records_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = WslFixture(Path(tmp))
            fixture.enable_python(sys.executable)

            result = fixture.run("--yes")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((fixture.unified_skills / "alpha").is_symlink())
            self.assertTrue((fixture.unified_skills / "beta").is_symlink())
            self.assertFalse((fixture.unified_skills / "windows-private").exists())
            self.assertTrue((fixture.linux_home / ".agents" / "mcp").is_symlink())
            self.assertTrue((fixture.linux_home / ".agents" / "memories").is_symlink())
            self.assertTrue((fixture.agent_root / "alpha").is_symlink())
            self.assertTrue((fixture.agent_root / "beta").is_symlink())
            self.assertTrue((fixture.agent_root / "private-agent-skill").is_dir())
            self.assertTrue(fixture.state_file.exists())
            self.assertIn("verification: .agents/skills 2/2 readable", result.stdout)
            self.assertIn("verification: codex/skills 2/2 readable", result.stdout)
            self.assertIn("verification: .agents/mcp readable", result.stdout)
            self.assertIn("verification: .agents/memories readable", result.stdout)

            data = json.loads(fixture.state_file.read_text(encoding="utf-8"))
            self.assertEqual(len(data["environments"]), 1)
            record = data["environments"][0]
            self.assertEqual(record["environment_id"], "wsl:administrator:test-ubuntu:gao")
            self.assertEqual(record["windows_agents_root"], str(fixture.windows_agents))
            self.assertEqual(record["unified_root"], str(fixture.linux_home / ".agents"))

            agent_data = json.loads(fixture.agent_state_file.read_text(encoding="utf-8"))
            self.assertEqual(len(agent_data["instances"]), 1)
            agent_record = agent_data["instances"][0]
            self.assertEqual(agent_record["environment_id"], "wsl:administrator:test-ubuntu:gao")
            self.assertEqual(agent_record["agent_id"], "codex")
            self.assertEqual(agent_record["skills_dir"], str(fixture.agent_root))

    def test_apply_without_python_reports_state_pending(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = WslFixture(Path(tmp))
            fixture.disable_python()

            result = fixture.run("--yes")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("state_pending", result.stdout)
            self.assertTrue((fixture.unified_skills / "alpha").is_symlink())
            self.assertTrue((fixture.linux_home / ".agents" / "mcp").is_symlink())
            self.assertFalse(fixture.state_file.exists())

    def test_prune_skips_when_canonical_scan_is_incomplete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = WslFixture(Path(tmp))
            fixture.enable_python(sys.executable)

            initial = fixture.run("--yes")
            self.assertEqual(initial.returncode, 0, initial.stderr)
            stale_link = fixture.unified_skills / "beta"
            self.assertTrue(stale_link.is_symlink())

            skill_file = fixture.vault_skills / "beta" / "SKILL.md"
            skill_file.write_text("", encoding="utf-8")

            result = fixture.run("--yes", "--prune")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(stale_link.is_symlink())
            self.assertIn("prune skipped", result.stdout.casefold())
            self.assertIn("scan incomplete", result.stdout.casefold())

    def test_real_unified_root_conflict_stops_without_replace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = WslFixture(Path(tmp))
            fixture.enable_python(sys.executable)

            agents_root = fixture.linux_home / ".agents"
            agents_root.parent.mkdir(parents=True, exist_ok=True)
            agents_root.symlink_to(fixture.root / "unexpected-target", target_is_directory=True)

            result = fixture.run("--yes")

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("conflict", result.stderr.casefold())
            self.assertIn("real directory", result.stderr.casefold())
            self.assertFalse((fixture.linux_home / ".agents" / "mcp").exists())
            self.assertFalse(fixture.state_file.exists())

    def test_missing_explicit_canonical_root_fails_safe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = WslFixture(Path(tmp))
            fixture.enable_python(sys.executable)

            result = fixture.run_without_canonical_root("--yes")

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("windows-shared-skills-root", result.stderr)
            self.assertIn("required", result.stderr.casefold())
            self.assertFalse((fixture.linux_home / ".agents" / "skills" / "alpha").exists())
            self.assertFalse(fixture.state_file.exists())


class WslFixture:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.vault_skills = root / "vault-skills"
        self.windows_agents = root / "windows-agents"
        self.linux_home = root / "linux-home"
        self.state_file = root / "shared-system-state.json"
        self.agent_state_file = root / "agent-skill-state.json"
        self.bin_dir = root / "bin"
        self.agent_root = self.linux_home / ".codex" / "skills"
        self.unified_skills = self.linux_home / ".agents" / "skills"
        self._build()

    def run(self, *extra_args: str) -> subprocess.CompletedProcess[str]:
        command = [
            "bash",
            str(SCRIPT),
            "--windows-agents-root",
            str(self.windows_agents),
            "--windows-shared-skills-root",
            str(self.vault_skills),
            "--host-machine",
            "Administrator",
            "--agent-id",
            "codex",
            "--agent-skills-dir",
            str(self.agent_root),
            "--state-file",
            str(self.state_file),
            "--agent-state-file",
            str(self.agent_state_file),
            *extra_args,
        ]
        return subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            env=self.env,
        )

    def run_without_canonical_root(self, *extra_args: str) -> subprocess.CompletedProcess[str]:
        command = [
            "bash",
            str(SCRIPT),
            "--windows-agents-root",
            str(self.windows_agents),
            "--host-machine",
            "Administrator",
            "--agent-id",
            "codex",
            "--agent-skills-dir",
            str(self.agent_root),
            "--agent-state-file",
            str(self.agent_state_file),
            "--state-file",
            str(self.state_file),
            *extra_args,
        ]
        return subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            env=self.env,
        )

    def enable_python(self, python_executable: str) -> None:
        python_link = self.bin_dir / "python3"
        if python_link.exists() or python_link.is_symlink():
            python_link.unlink()
        python_link.symlink_to(python_executable)

    def disable_python(self) -> None:
        python_stub = self.bin_dir / "python3"
        python_stub.write_text("#!/usr/bin/env bash\nexit 127\n", encoding="utf-8")
        python_stub.chmod(0o755)

    @property
    def env(self) -> dict[str, str]:
        env = dict(os.environ)
        env["HOME"] = str(self.linux_home)
        env["USER"] = "gao"
        env["WSL_DISTRO_NAME"] = "Test-Ubuntu"
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["PATH"] = f"{self.bin_dir}{os.pathsep}{env.get('PATH', '')}"
        return env

    def _build(self) -> None:
        self.vault_skills.mkdir(parents=True)
        self.windows_agents.mkdir(parents=True)
        self.linux_home.mkdir(parents=True)
        self.bin_dir.mkdir(parents=True)
        (self.windows_agents / "mcp" / "catalog").mkdir(parents=True)
        (self.windows_agents / "memories" / "extensions").mkdir(parents=True)
        (self.agent_root / "private-agent-skill").mkdir(parents=True)
        (self.agent_root / "private-agent-skill" / "SKILL.md").write_text(
            "# Private\n", encoding="utf-8"
        )

        self._make_shared_skill("alpha")
        self._make_shared_skill("beta")

        private_skill = self.windows_agents / "skills" / "windows-private"
        private_skill.mkdir(parents=True)
        (private_skill / "SKILL.md").write_text("# Private Windows Skill\n", encoding="utf-8")

    def _make_shared_skill(self, name: str) -> None:
        target = self.vault_skills / name
        target.mkdir(parents=True)
        (target / "SKILL.md").write_text(f"# {name}\n", encoding="utf-8")
        skills_root = self.windows_agents / "skills"
        skills_root.mkdir(parents=True, exist_ok=True)
        (skills_root / name).symlink_to(target, target_is_directory=True)


if __name__ == "__main__":
    unittest.main()
