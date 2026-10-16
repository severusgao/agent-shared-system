from __future__ import annotations

import hashlib
import json
import io
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import batch_guard as b


class BatchGuardTests(unittest.TestCase):
    def prepare_completion(self, root):
        log = root / "checks.log"
        log.write_text("actual fixture verification passed", encoding="utf-8")
        verification = root / "verification.json"
        verification.write_text(json.dumps({"status": "passed", "checks": [{"name": "fixture",
            "exit_code": 0, "evidence_file": str(log), "sha256": b.sha(log)}]}), encoding="utf-8")
        return verification, root / "receipts/completion.json"

    def active_batch(self, root):
        shared = root / ".agents"; shared.mkdir()
        p = shared / "README.md"; p.write_text("old", encoding="utf-8")
        manifest = b.snapshot(shared, ["README.md"], root / "batches/first", "approved lifecycle")
        p.write_text("ours", encoding="utf-8"); b.seal(manifest, {"README.md": b.sha(p)})
        return shared, p, manifest

    def test_verified_application_cleans_only_temporary_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); _, p, manifest = self.active_batch(root)
            verification, receipt = self.prepare_completion(root)
            b.finish(manifest, verification, receipt)
            self.assertFalse(manifest.parent.exists())
            self.assertEqual(p.read_text(encoding="utf-8"), "ours")
            self.assertTrue(receipt.is_file())
            self.assertNotIn('"old"', receipt.read_text(encoding="utf-8"))

    def test_failed_check_or_changed_artifact_keeps_recovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); _, _, manifest = self.active_batch(root)
            verification, receipt = self.prepare_completion(root)
            proof = json.loads(verification.read_text(encoding="utf-8")); proof["checks"][0]["exit_code"] = 1
            verification.write_text(json.dumps(proof), encoding="utf-8")
            with self.assertRaises(ValueError): b.finish(manifest, verification, receipt)
            proof["checks"][0]["exit_code"] = 0; verification.write_text(json.dumps(proof), encoding="utf-8")
            (root / "checks.log").write_text("changed", encoding="utf-8")
            with self.assertRaises(ValueError): b.finish(manifest, verification, receipt)
            self.assertTrue((manifest.parent / "originals/README.md").exists())
            self.assertFalse(receipt.exists())

    def test_verified_recovery_can_finish_without_leaving_old_contents(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); _, p, manifest = self.active_batch(root)
            b.rollback(manifest)
            verification, receipt = self.prepare_completion(root)
            b.finish(manifest, verification, receipt)
            self.assertEqual(p.read_text(encoding="utf-8"), "old")
            self.assertFalse(manifest.parent.exists())
            self.assertEqual(json.loads(receipt.read_text(encoding="utf-8"))["outcome"], "rolled_back_verified")

    def test_interrupted_cleanup_resumes_before_next_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); shared, _, manifest = self.active_batch(root)
            verification, receipt = self.prepare_completion(root)
            original_unlink = Path.unlink
            def stop_on_manifest(path, *args, **kwargs):
                if path == manifest:
                    raise OSError("interrupted cleanup")
                return original_unlink(path, *args, **kwargs)
            with patch.object(Path, "unlink", stop_on_manifest):
                with self.assertRaises(OSError): b.finish(manifest, verification, receipt)
            self.assertEqual(json.loads(manifest.read_text(encoding="utf-8"))["status"], "verified")
            next_manifest = b.snapshot(shared, ["README.md"], root / "batches/second", "next authorized batch")
            self.assertFalse(manifest.parent.exists())
            self.assertTrue(next_manifest.exists())
            self.assertTrue(receipt.exists())

    def test_unfinished_batch_blocks_accumulation_and_foreign_entries_stop_deletion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); shared, _, manifest = self.active_batch(root)
            with self.assertRaises(ValueError):
                b.snapshot(shared, ["README.md"], root / "batches/second", "next")
            foreign = manifest.parent / "unrelated.txt"; foreign.write_text("keep", encoding="utf-8")
            verification, receipt = self.prepare_completion(root)
            with self.assertRaises(ValueError): b.finish(manifest, verification, receipt)
            self.assertTrue((manifest.parent / "originals/README.md").exists())
            self.assertEqual(foreign.read_text(encoding="utf-8"), "keep")
            self.assertFalse(receipt.exists())

    def test_later_source_change_stops_cleanup_and_legacy_directory_is_not_adopted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); _, p, manifest = self.active_batch(root)
            verification, receipt = self.prepare_completion(root)
            p.write_text("later change", encoding="utf-8")
            with self.assertRaises(ValueError): b.finish(manifest, verification, receipt)
            self.assertTrue(manifest.exists())
            data = json.loads(manifest.read_text(encoding="utf-8")); data.pop("kind"); b.save(manifest, data)
            self.assertEqual(b.resume_cleanup(manifest.parent.parent), {"cleaned": [], "pending": []})
            self.assertTrue(manifest.exists())

    def test_interrupted_snapshot_registers_old_contents_and_resumes_safely(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); shared = root / ".agents"; shared.mkdir()
            p = shared / "README.md"; p.write_text("old", encoding="utf-8")
            original_write = Path.write_bytes
            def interrupt_original(path, data):
                if "originals" in path.parts:
                    raise OSError("snapshot interrupted")
                return original_write(path, data)
            with patch.object(Path, "write_bytes", interrupt_original):
                with self.assertRaises(OSError):
                    b.snapshot(shared, ["README.md"], root / "batches/partial", "approved lifecycle")
            manifest = root / "batches/partial/manifest.json"
            self.assertEqual(json.loads(manifest.read_text(encoding="utf-8"))["status"], "preparing")
            result = b.resume_cleanup(root / "batches")
            self.assertEqual(result["pending"], ["partial"])
            self.assertEqual((manifest.parent / "originals/README.md").read_text(encoding="utf-8"), "old")
            b.check(manifest)
            b.seal(manifest, {"README.md": b.sha(p)})
            verification, receipt = self.prepare_completion(root)
            b.finish(manifest, verification, receipt)
            self.assertFalse(manifest.parent.exists())

    def test_failed_batch_restores_bytes_and_only_its_new_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / ".agents"
            original = root / "scripts/original.py"; original.parent.mkdir(parents=True); original.write_bytes(b"old\r\n")
            other = original.parent / "unrelated.txt"; other.write_text("keep", encoding="utf-8")
            manifest = b.snapshot(root, ["scripts/original.py", "skills/new/SKILL.md"], Path(tmp) / "backup", "explicit user request")
            b.check(manifest)
            original.write_text("new", encoding="utf-8")
            new = root / "skills/new/SKILL.md"; new.parent.mkdir(parents=True); new.write_text("created", encoding="utf-8")
            b.seal(manifest, {"scripts/original.py": b.sha(original), "skills/new/SKILL.md": b.sha(new)})
            b.rollback(manifest)
            self.assertEqual(original.read_bytes(), b"old\r\n")
            self.assertFalse(new.exists())
            self.assertEqual(other.read_text(encoding="utf-8"), "keep")

    def test_later_external_edit_stops_recovery_without_overwriting(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / ".agents"; root.mkdir()
            p = root / "README.md"; p.write_text("old", encoding="utf-8")
            manifest = b.snapshot(root, ["README.md"], Path(tmp) / "backup", "user request")
            p.write_text("ours", encoding="utf-8")
            b.seal(manifest, {"README.md": hashlib.sha256(b"ours").hexdigest()})
            p.write_text("theirs", encoding="utf-8")
            with self.assertRaises(ValueError):
                b.rollback(manifest)
            self.assertEqual(p.read_text(encoding="utf-8"), "theirs")

    def test_baseline_change_and_wrong_expected_cannot_be_silently_adopted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / ".agents"; root.mkdir()
            p = root / "AGENTS.md"; p.write_text("old", encoding="utf-8")
            manifest = b.snapshot(root, ["AGENTS.md"], Path(tmp) / "backup", "user request")
            p.write_text("external", encoding="utf-8")
            with self.assertRaises(ValueError):
                b.check(manifest)
            with self.assertRaises(ValueError):
                b.seal(manifest, {"AGENTS.md": hashlib.sha256(b"ours").hexdigest()})
            with self.assertRaises(ValueError):
                b.rollback(manifest)
            self.assertEqual(p.read_text(encoding="utf-8"), "external")

    def test_missing_approval_path_escape_and_credential_target_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / ".agents"; root.mkdir()
            for name, approval in [("README.md", ""), ("../escape", "user"), ("skills/firecrawl/token.txt", "user")]:
                with self.assertRaises(ValueError):
                    b.snapshot(root, [name], Path(tmp) / "backup", approval)
            self.assertFalse((Path(tmp) / "backup").exists())

    def test_corrupt_backup_blocks_all_recovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / ".agents"; root.mkdir()
            p = root / "README.md"; p.write_text("old", encoding="utf-8")
            manifest = b.snapshot(root, ["README.md"], Path(tmp) / "backup", "user")
            p.write_text("ours", encoding="utf-8"); b.seal(manifest, {"README.md": b.sha(p)})
            (manifest.parent / "originals/README.md").write_text("corrupt", encoding="utf-8")
            with self.assertRaises(ValueError):
                b.rollback(manifest)
            self.assertEqual(p.read_text(encoding="utf-8"), "ours")


    def test_cli_utf8_chinese_targets_survive_gbk_default(self):
        original = Path.read_text
        def default_gbk(path, encoding=None, errors=None):
            return original(path, encoding=encoding or "gbk", errors=errors)
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp); shared = base / ".agents"; shared.mkdir()
            name = "memories/说明.md"; target = shared / name
            target.parent.mkdir()
            target.write_text("原始内容", encoding="utf-8")
            targets = base / "目标.json"
            targets.write_text(json.dumps([name], ensure_ascii=False), encoding="utf-8")
            batch = base / "backups/编码批次"; manifest = batch / "manifest.json"
            expected = base / "摘要.json"
            output = io.StringIO(); error = io.StringIO()
            with patch.object(Path, "read_text", default_gbk), redirect_stdout(output), redirect_stderr(error):
                args = ["batch_guard.py", "snapshot", "--root", str(shared), "--targets", str(targets), "--output", str(batch), "--approval-ref", "fixture:批准编码测试"]
                with patch.object(sys, "argv", args): self.assertEqual(b.main(), 0, error.getvalue())
                target.write_text("修改内容", encoding="utf-8")
                expected.write_text(json.dumps({name: b.sha(target)}, ensure_ascii=False), encoding="utf-8")
                args = ["batch_guard.py", "seal", "--manifest", str(manifest), "--expected", str(expected)]
                with patch.object(sys, "argv", args): self.assertEqual(b.main(), 0, error.getvalue())
                args = ["batch_guard.py", "rollback", "--manifest", str(manifest)]
                with patch.object(sys, "argv", args): self.assertEqual(b.main(), 0, error.getvalue())
                self.assertEqual(target.read_text(encoding="utf-8"), "原始内容")
                verification, receipt = self.prepare_completion(base)
                b.finish(manifest, verification, receipt)
            self.assertFalse(batch.exists())
            self.assertEqual(json.loads(receipt.read_text(encoding="utf-8"))["outcome"], "rolled_back_verified")

if __name__ == "__main__":
    unittest.main()
