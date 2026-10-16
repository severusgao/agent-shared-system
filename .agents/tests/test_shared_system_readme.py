import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "generate-shared-system-readme.py"
SPEC = importlib.util.spec_from_file_location("generate_shared_system_readme", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


BASE_README = """# Shared System

Manual rule: preserve this text.

<!-- BEGIN GENERATED: shared-skills -->
old skills
<!-- END GENERATED: shared-skills -->

<!-- BEGIN GENERATED: shared-mcps -->
old mcps
<!-- END GENERATED: shared-mcps -->

<!-- BEGIN GENERATED: scripts -->
old scripts
<!-- END GENERATED: scripts -->
"""


class SharedSystemReadmeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.agents = self.root / ".agents"
        (self.agents / "skills" / "demo-skill").mkdir(parents=True)
        (self.agents / "skills" / "demo-skill" / "SKILL.md").write_text(
            "---\nname: demo-skill\ndescription: Demo | skill\n---\n# Demo\n",
            encoding="utf-8",
        )
        (self.agents / "mcp" / "catalog").mkdir(parents=True)
        (self.agents / "mcp" / "catalog" / "demo.json").write_text(
            json.dumps({
                "id": "demo-mcp",
                "label": "Demo MCP",
                "description": "A shared MCP",
            }),
            encoding="utf-8",
        )
        (self.agents / "scripts").mkdir(parents=True)
        (self.agents / "scripts" / "sync.cmd").write_text("", encoding="utf-8")
        (self.agents / "README.md").write_text(BASE_README, encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def test_dynamic_sections_include_current_skill_mcp_and_script(self):
        updated = MODULE.render_document(self.root, BASE_README)
        self.assertIn("`demo-skill`", updated)
        self.assertIn("Demo \\| skill", updated)
        self.assertIn("`demo-mcp`", updated)
        self.assertIn("`sync.cmd`", updated)

    def test_manual_content_is_preserved(self):
        updated = MODULE.render_document(self.root, BASE_README)
        self.assertIn("Manual rule: preserve this text.", updated)

    def test_generation_is_stable(self):
        first = MODULE.render_document(self.root, BASE_README)
        second = MODULE.render_document(self.root, first)
        self.assertEqual(first, second)

    def test_missing_optional_sources_are_tolerated(self):
        (self.agents / "mcp").rename(self.agents / "mcp.disabled")
        (self.agents / "scripts").rename(self.agents / "scripts.disabled")
        updated = MODULE.render_document(self.root, BASE_README)
        self.assertIn("（暂无 MCP）", updated)
        self.assertIn("（暂无脚本）", updated)

    def test_generated_content_does_not_include_machine_paths_or_secrets(self):
        generated = MODULE.render_document(self.root, BASE_README)
        self.assertNotRegex(generated, r"/Users/|[A-Za-z]:\\|/mnt/c/")
        self.assertNotRegex(generated, r"(?i)token|secret|api[_ -]?key")


if __name__ == "__main__":
    unittest.main()
