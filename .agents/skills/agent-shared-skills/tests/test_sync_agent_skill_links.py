from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from audit_shared_skills import audit as audit_shared_skills_audit  # noqa: E402
from shared_environment import detect_environment  # noqa: E402
from sync_agent_skill_links import (  # noqa: E402
    audit,
    build_direct_target,
    instance_key,
    normalize_state,
    plan_entry,
    registry_platform_key,
)


def _write_skill(root: Path, name: str) -> None:
    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_dir.joinpath("SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {name} description long enough\n---\n",
        encoding="utf-8",
    )


class SyncAgentSkillLinksTests(unittest.TestCase):
    def test_broken_junction_is_relinked_not_created(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch("sync_agent_skill_links.os.path.lexists", return_value=True), \
                 mock.patch("sync_agent_skill_links.is_link_like", return_value=True), \
                 mock.patch("sync_agent_skill_links.read_link_target", return_value=str(root / "old")):
                with mock.patch("sync_agent_skill_links.entry_snapshot", return_value=("link",)):
                    plan = plan_entry(root / "agent", root / "unified", "example")
            self.assertEqual(plan["plan"], "relink")

    def test_wsl_uses_linux_registry_templates(self) -> None:
        self.assertEqual(registry_platform_key("wsl"), "linux")

    def test_v1_windows_record_is_preserved_as_legacy(self) -> None:
        state = normalize_state(
            {
                "version": 1,
                "instances": [
                    {
                        "agent_id": "codex",
                        "platform": "windows",
                        "machine": "都市傳説",
                        "home": r"C:\Users\Administrator",
                        "skills_dir": r"C:\Users\Administrator\.codex\skills",
                    }
                ],
            }
        )
        self.assertEqual(state["version"], 2)
        self.assertEqual(state["instances"][0]["status"], "legacy")

    def test_instance_key_includes_environment_and_agent(self) -> None:
        left = instance_key(
            {
                "environment_id": "wsl:host:ubuntu:user",
                "agent_id": "codex",
                "skills_dir": "/home/u/.codex/skills",
            }
        )
        right = instance_key(
            {
                "environment_id": "wsl:host:debian:user",
                "agent_id": "codex",
                "skills_dir": "/home/u/.codex/skills",
            }
        )
        self.assertNotEqual(left, right)

    def test_audit_only_manages_vault_backed_skills(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            shared_root = tmp_path / "vault" / ".agents" / "skills"
            local_root = tmp_path / "local" / ".agents" / "skills"
            agent_root = tmp_path / "agent" / ".codex" / "skills"
            registry = tmp_path / "agent_targets.json"
            state_path = tmp_path / "agent_skill_instances.json"

            shared_root.mkdir(parents=True)
            local_root.mkdir(parents=True)
            agent_root.mkdir(parents=True)
            registry.write_text('{"version": 1, "targets": []}\n', encoding="utf-8")
            state_path.write_text('{"version": 1, "instances": []}\n', encoding="utf-8")

            _write_skill(shared_root, "alpha")
            _write_skill(shared_root, "beta")

            (local_root / "alpha").symlink_to(shared_root / "alpha", target_is_directory=True)
            (local_root / "beta").symlink_to(shared_root / "beta", target_is_directory=True)
            _write_skill(local_root, "private-skill")

            direct_target, warning = build_direct_target(
                target_dir=str(agent_root),
                target_id="codex",
                target_label="Codex",
                strategy="symlink",
                current_platform="linux",
                known_skill_names=["alpha", "beta"],
            )
            self.assertIsNone(warning)

            result = audit(
                shared_root=shared_root,
                local_root=local_root,
                registry=registry,
                state_path=state_path,
                agents_filter=None,
                skills_filter=None,
                use_registry=False,
                include_recorded=False,
                direct_target=direct_target,
                target_warnings=[],
                create_roots=False,
            )

            plans = result["agents"][0]["plans"]
            self.assertEqual({item["skill"] for item in plans}, {"alpha", "beta"})

    def test_audit_shared_skills_uses_vault_agents_state_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            shared_root = tmp_path / "vault" / ".agents" / "skills"
            state_file = tmp_path / "vault" / ".agents" / "state" / "shared_system_instances.json"
            shared_root.mkdir(parents=True)
            state_file.parent.mkdir(parents=True)

            _write_skill(shared_root, "alpha")
            (shared_root / "alpha" / "references").mkdir()

            current = detect_environment()
            state_file.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "environments": [{"environment_id": current.environment_id}],
                    }
                ),
                encoding="utf-8",
            )

            result = audit_shared_skills_audit(shared_root)

            self.assertEqual(
                result["shared_system_state"]["state_file"],
                str(state_file.resolve()),
            )
            self.assertTrue(result["shared_system_state"]["exists"])
            self.assertTrue(result["shared_system_state"]["recorded"])

    def test_all_recorded_does_not_probe_unreachable_recorded_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            shared_root = tmp_path / "vault" / ".agents" / "skills"
            local_root = tmp_path / "local" / ".agents" / "skills"
            registry = tmp_path / "agent_targets.json"
            state_path = tmp_path / "agent_skill_instances.json"
            unreachable_root = tmp_path / "remote" / "missing" / "skills"

            shared_root.mkdir(parents=True)
            local_root.mkdir(parents=True)
            registry.write_text('{"version": 1, "targets": []}\n', encoding="utf-8")
            _write_skill(shared_root, "alpha")
            (local_root / "alpha").symlink_to(shared_root / "alpha", target_is_directory=True)

            current = detect_environment()
            state_path.write_text(
                json.dumps(
                    {
                        "version": 2,
                        "instances": [
                            {
                                "environment_id": current.environment_id,
                                "agent_id": "remote-agent",
                                "label": "Remote Agent",
                                "platform": current.platform,
                                "machine_display": current.machine_display,
                                "wsl_distro": current.wsl_distro,
                                "skills_dir": str(unreachable_root),
                                "link_strategy": "symlink",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            original_is_dir = Path.is_dir

            def guarded_is_dir(path_self: Path) -> bool:
                if path_self == unreachable_root:
                    raise AssertionError("recorded unreachable path should not be probed")
                return original_is_dir(path_self)

            with mock.patch("sync_agent_skill_links.Path.is_dir", autospec=True, side_effect=guarded_is_dir):
                result = audit(
                    shared_root=shared_root,
                    local_root=local_root,
                    registry=registry,
                    state_path=state_path,
                    agents_filter=None,
                    skills_filter=None,
                    use_registry=False,
                    include_recorded=False,
                    all_recorded=True,
                    direct_target=None,
                    target_warnings=[],
                    create_roots=False,
                )

            self.assertEqual(result["agents"], [])
            self.assertEqual(len(result["recorded_instances"]), 1)
            self.assertEqual(
                result["recorded_instances"][0]["skills_dir"],
                str(unreachable_root),
            )


if __name__ == "__main__":
    unittest.main()
