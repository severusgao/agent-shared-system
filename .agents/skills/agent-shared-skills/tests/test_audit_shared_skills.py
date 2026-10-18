from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from audit_shared_skills import _detect_likely_overlap, audit, build_manifest, manifest_path  # noqa: E402


def _write_skill(
    root: Path,
    name: str,
    description: str,
    *,
    disable_model_invocation: bool = False,
    allow_implicit_invocation: bool | None = None,
    short_description: str | None = None,
) -> None:
    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    frontmatter = ["---", f"name: {name}", f"description: {description}"]
    if disable_model_invocation:
        frontmatter.append("disable-model-invocation: true")
    frontmatter.extend(["---", f"# {name}", ""])
    (skill_dir / "SKILL.md").write_text("\n".join(frontmatter), encoding="utf-8")

    if allow_implicit_invocation is not None or short_description is not None:
        agents_dir = skill_dir / "agents"
        agents_dir.mkdir()
        lines = ["interface:", f'  display_name: "{name}"']
        if short_description is not None:
            lines.append(f'  short_description: "{short_description}"')
        if allow_implicit_invocation is not None:
            lines.extend(
                [
                    "policy:",
                    "  allow_implicit_invocation: "
                    + ("true" if allow_implicit_invocation else "false"),
                ]
            )
        (agents_dir / "openai.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _warnings_for(result: dict[str, object], skill_name: str) -> list[str]:
    return [
        str(item)
        for item in result["warnings"]  # type: ignore[index]
        if str(item).startswith(f"{skill_name}:")
    ]


class AuditSharedSkillsTests(unittest.TestCase):
    def test_short_chinese_user_invoked_description_is_valid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "skills"
            root.mkdir()
            _write_skill(
                root,
                "explicit-skill",
                "把讨论整理成正式规格说明。",
                disable_model_invocation=True,
                allow_implicit_invocation=False,
                short_description="把当前讨论整理成可交付和可复用的正式规格说明文档入口",
            )

            result = audit(root)

            self.assertEqual(_warnings_for(result, "explicit-skill"), [])

    def test_model_invoked_chinese_description_requires_trigger_clause(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "skills"
            root.mkdir()
            _write_skill(root, "good", "当用户要求诊断测试失败或性能回退时使用。")
            _write_skill(root, "bad", "可靠的软件问题诊断方法。")

            result = audit(root)

            self.assertFalse(any("good:" in item for item in result["warnings"]))
            self.assertTrue(
                any("bad: model-invoked description has no trigger clause" in item for item in result["warnings"])
            )

    def test_invocation_policy_mismatch_warns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "skills"
            root.mkdir()
            _write_skill(
                root,
                "mismatch",
                "由用户显式调用的辅助技能。",
                disable_model_invocation=True,
                allow_implicit_invocation=True,
                short_description="供用户显式调用并完成指定辅助任务的共享技能入口",
            )

            result = audit(root)

            self.assertTrue(
                any("mismatch: invocation policy mismatch" in item for item in result["warnings"])
            )

    def test_missing_references_directory_is_not_a_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "skills"
            root.mkdir()
            _write_skill(root, "simple", "用于处理无需附加参考文件的简单任务。")

            result = audit(root)

            self.assertFalse(any("no references directory" in item for item in result["warnings"]))

    def test_openai_short_description_bounds_are_checked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "skills"
            root.mkdir()
            _write_skill(
                root,
                "short-ui",
                "当用户需要检查界面元数据时使用。",
                allow_implicit_invocation=True,
                short_description="太短",
            )

            result = audit(root)

            self.assertTrue(
                any("short-ui: short_description must be 25-64 characters" in item for item in result["warnings"])
            )

    def test_chinese_overlap_is_detected(self) -> None:
        warnings = _detect_likely_overlap(
            [
                {
                    "name": "alpha",
                    "description": "当需要审计共享技能并检查跨系统链接、重复能力和配置冲突时使用。",
                },
                {
                    "name": "beta",
                    "description": "当需要审计共享工具并检查跨系统链接、重复能力和配置冲突时使用。",
                },
            ]
        )

        self.assertTrue(any("alpha/beta" in item for item in warnings))

    def test_directory_without_skill_md_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "skills"
            (root / "lost-skill" / "agents").mkdir(parents=True)
            _write_skill(root, "kept", "当用户要求诊断问题时使用。")

            result = audit(root)

            self.assertIn("directory without SKILL.md: lost-skill", result["errors"])

    def test_manifest_detects_missing_skill_and_required_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "skills"
            _write_skill(root, "kept", "当用户要求诊断问题时使用。")
            _write_skill(root, "agent-shared-skills", "当需要审计共享技能时使用。")
            (root / "kept" / "local").mkdir()
            (root / "kept" / "local" / "ADAPTATION.md").write_text("x\n", encoding="utf-8")
            manifest = build_manifest(root)
            manifest["skills"]["gone"] = ["SKILL.md"]
            manifest_path(root).parent.mkdir(parents=True)
            manifest_path(root).write_text(json.dumps(manifest), encoding="utf-8")
            (root / "kept" / "local" / "ADAPTATION.md").unlink()
            _write_skill(root, "new-one", "当用户要求新功能时使用。")

            result = audit(root)

            self.assertIn("expected skill missing: gone", result["errors"])
            self.assertIn("expected file missing: kept/local/ADAPTATION.md", result["errors"])
            self.assertTrue(any(item.startswith("skill not in manifest: new-one") for item in result["warnings"]))

    def test_without_manifest_only_warns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "skills"
            _write_skill(root, "kept", "当用户要求诊断问题时使用。")

            result = audit(root)

            self.assertEqual(result["errors"], [])
            self.assertTrue(any("no expected-skills manifest" in item for item in result["warnings"]))

    def test_icloud_conflict_copy_and_broken_markdown_link_are_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "skills"
            _write_skill(root, "kept", "当用户要求诊断问题时使用。")
            skill = root / "kept"
            (skill / "SKILL 2.md").write_text("copy\n", encoding="utf-8")
            (skill / "Chapter 2.md").write_text("[guide](missing.md) ![clip](clip.mp4)\n", encoding="utf-8")

            result = audit(root)

            self.assertIn("possible sync conflict copy: kept/SKILL 2.md", result["errors"])
            self.assertFalse(any("Chapter 2.md" in item and "conflict" in item for item in result["errors"]))
            self.assertIn("broken local link: kept/Chapter 2.md -> missing.md", result["errors"])
            self.assertIn("broken local link: kept/Chapter 2.md -> clip.mp4", result["warnings"])


if __name__ == "__main__":
    unittest.main()
