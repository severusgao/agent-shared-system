from pathlib import Path
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

class OnboardingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "sync space" / "AgentShared"
        shutil.copytree(ROOT, self.root, ignore=shutil.ignore_patterns(".git", "__pycache__", "dist", "build", ".venv"))
        self.home = self.base / "home"
        self.home.mkdir()
        spec = importlib.util.spec_from_file_location("isolated_setup", self.root / "scripts/setup.py")
        self.setup = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.setup)
        self.target = self.home / ".codex/skills"

    def call(self, *args):
        return subprocess.run([sys.executable, "-B", str(self.root / "scripts/setup.py"), "--local-home", str(self.home), "--agent", "codex", *args], capture_output=True, text=True, encoding="utf-8")

    def test_preview_writes_nothing(self):
        before = set(self.home.rglob("*"))
        result = self.call()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(set(self.home.rglob("*")), before)
        self.assertEqual(len(json.loads(result.stdout)["links"]), 10)

    def test_complete_install_reapply_query_and_uninstall_preserve_data(self):
        result = self.call("--apply", "--yes")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertTrue(self.setup.same_link(self.home / ".agents/memories", self.root / ".agents/memories"))
        self.assertTrue(self.setup.same_link(self.home / ".agents/mcp", self.root / ".agents/mcp"))
        preview = self.call()
        self.assertTrue(all(p["action"] == "skip" for p in json.loads(preview.stdout)["links"]))
        self.assertEqual(self.call("--apply", "--yes").returncode, 0)
        q = subprocess.run([sys.executable, "-B", str(self.root / ".agents/skills/agent-shared-memories/scripts/query_memories.py"), "--term", "Atlas", "--scope", "current", "--format", "json"], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(q.returncode, 0, q.stderr)
        self.assertIn("Atlas", q.stdout)
        data = self.root / ".agents/memories/USER_PROFILE.md"
        data.write_text("Keep my own profile", encoding="utf-8")
        self.setup.initialize_missing()
        self.assertEqual(data.read_text(), "Keep my own profile")
        result = self.call("--uninstall", "--apply", "--yes")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(os.path.lexists(self.target / "agent-shared-skills"))
        self.assertEqual(data.read_text(), "Keep my own profile")

    def test_existing_private_directory_blocks_entire_apply(self):
        collision = self.target / "agent-shared-skills"
        collision.mkdir(parents=True)
        (collision / "private.txt").write_text("keep", encoding="utf-8")
        result = self.call("--apply", "--yes")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((collision / "private.txt").read_text(), "keep")
        self.assertFalse(os.path.lexists(self.home / ".agents/memories"))
        self.assertFalse(os.path.lexists(self.home / ".agents/skills/agent-shared-skills"))

    @unittest.skipIf(os.name == "nt", "POSIX ancestor-link guard; Windows junction path tested separately")
    def test_existing_shared_parent_is_not_followed(self):
        private = self.base / "private-source"
        private.mkdir()
        (self.home / ".agents").symlink_to(private, target_is_directory=True)
        result = self.call("--apply", "--yes")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(list(private.iterdir()), [])

    def test_partial_failure_rolls_back_only_created_links(self):
        # Failure after the first stage must not leave half-installed discovery links.
        calls = 0
        original = self.setup.helper
        def failing(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("injected later-stage failure")
            original(*args, **kwargs)
        self.setup.helper = failing
        plan = self.setup.build_plan(self.home, self.target)
        with self.assertRaisesRegex(RuntimeError, "injected"):
            self.setup.apply_plan(plan, self.home, self.target)
        self.assertTrue(all(not os.path.lexists(row["path"]) for row in plan))

    def test_uninstall_keeps_unrelated_entries(self):
        self.target.mkdir(parents=True)
        private = self.target / "agent-shared-skills"
        private.mkdir()
        result = self.call("--uninstall", "--apply", "--yes")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(private.is_dir())

if __name__ == "__main__":
    unittest.main()
