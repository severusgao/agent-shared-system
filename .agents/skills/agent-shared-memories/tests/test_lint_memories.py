from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

from lint_memories import REQUIRED_FILES, lint  # noqa: E402


def _frontmatter(name: str, *, status: str = "stable", sources: list[str] | None = None) -> str:
    source_lines = ["sources: []"]
    if sources:
        source_lines = ["sources:", *[f"  - {source}" for source in sources]]
    return "\n".join(
        [
            "---",
            "tags: [agents, memories]",
            "created: 2026-07-05",
            "updated: 2026-07-20",
            "type: topic",
            f"status: {status}",
            *source_lines,
            "---",
            f"# {name}",
            "",
        ]
    )


def _create_root(root: Path) -> Path:
    root.mkdir(parents=True)
    for name in REQUIRED_FILES:
        (root / name).write_text(_frontmatter(name), encoding="utf-8")
    return root


class LintMemoriesTests(unittest.TestCase):
    def test_valid_root_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _create_root(Path(tmp) / "memories")

            result = lint(root)

            self.assertTrue(result["ok"], result)

    def test_missing_frontmatter_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _create_root(Path(tmp) / "memories")
            (root / "USER_PROFILE.md").write_text("# User Profile\n", encoding="utf-8")

            result = lint(root)

            self.assertTrue(any("USER_PROFILE.md: missing frontmatter" in item for item in result["errors"]))

    def test_invalid_updated_date_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _create_root(Path(tmp) / "memories")
            text = (root / "TOOLS.md").read_text(encoding="utf-8").replace(
                "updated: 2026-07-20", "updated: recently"
            )
            (root / "TOOLS.md").write_text(text, encoding="utf-8")

            result = lint(root)

            self.assertTrue(any("TOOLS.md: invalid updated date" in item for item in result["errors"]))

    def test_deleted_staging_source_in_active_memory_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _create_root(Path(tmp) / "memories")
            (root / "ENVIRONMENT.md").write_text(
                _frontmatter(
                    "Environment",
                    sources=[".agents/memories/total memories/windows/source.md"],
                ),
                encoding="utf-8",
            )

            result = lint(root)

            self.assertTrue(any("ENVIRONMENT.md: deleted staging source" in item for item in result["errors"]))

    def test_sources_history_may_name_the_deleted_import_batch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _create_root(Path(tmp) / "memories")
            with (root / "SOURCES.md").open("a", encoding="utf-8") as handle:
                handle.write("Historical batch label: `total memories/windows-20260705`.\n")

            result = lint(root)

            self.assertTrue(result["ok"], result)

    def test_unexpected_proposal_directory_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _create_root(Path(tmp) / "memories")
            (root / "proposals").mkdir()
            (root / "proposals" / "bad.md").write_text(
                _frontmatter("Bad proposal", status="stable"), encoding="utf-8"
            )

            result = lint(root)

            self.assertTrue(any("unexpected top-level directory: proposals" in item for item in result["errors"]))

    def test_secret_and_conflict_copy_are_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _create_root(Path(tmp) / "memories")
            (root / "proposals").mkdir()
            (root / "proposals" / "iCloud conflicted copy.md").write_text(
                _frontmatter("Conflict")
                + "sk-abcdefghijklmnopqrstuvwxyz1234567890\n",
                encoding="utf-8",
            )

            result = lint(root)

            self.assertTrue(any("iCloud conflict copy found" in item for item in result["errors"]))
            self.assertTrue(any("openai_like_key found" in item for item in result["errors"]))


if __name__ == "__main__":
    unittest.main()
