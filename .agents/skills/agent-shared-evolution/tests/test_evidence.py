from __future__ import annotations

from datetime import timedelta
import hashlib
import json
import io
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import evidence as e
from review_contract import proposal_digest

START = e.utc("2026-10-01T00:00:00Z")
END = e.utc("2026-10-04T00:00:00Z")


def jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def codex(kind, payload, timestamp="2026-10-02T00:00:00Z"):
    return {"type": kind, "payload": payload, "timestamp": timestamp}


def message(role, text, **kwargs):
    return codex("response_item", {"type": "message", "role": role, "content": [{"type": "input_text", "text": text}], **kwargs})


class EvidenceTests(unittest.TestCase):
    def test_archived_continuation_deduplicates_and_uses_events_not_filename(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = [codex("session_meta", {"id": "same"}, "2025-01-01T00:00:00Z"),
                    codex("event_msg", {"type": "task_started", "turn_id": "t"}),
                    message("user", "please inspect"), message("assistant", "done", phase="final")]
            jsonl(root / "sessions/2025/old.jsonl", rows)
            jsonl(root / "archived_sessions/copy.jsonl", rows + [codex("event_msg", {"type": "task_complete", "turn_id": "t"})])
            result = e.collect([e.source("codex", "default", root)], END, since=START)
            self.assertEqual(len(result["evidence"]), 2)
            self.assertEqual(result["deduplicated_events"], 2)
            self.assertEqual({r["outcome"] for r in result["evidence"]}, {"completed_unverified"})

    def test_aborted_open_child_reasoning_and_injected_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            jsonl(root / "sessions/main.jsonl", [codex("session_meta", {"id": "main"}),
                  codex("event_msg", {"type": "task_started", "turn_id": "one"}),
                  message("user", "# AGENTS.md instructions for test"),
                  message("user", "<recommended_plugins>available tools</recommended_plugins>\n# AGENTS.md instructions"),
                  message("user", "<skill>injected skill body</skill>"),
                  message("user", "real instruction"),
                  message("assistant", "hidden", channel="analysis"),
                  codex("response_item", {"type": "reasoning", "content": "hidden too"}),
                  codex("event_msg", {"type": "turn_aborted", "turn_id": "one"}),
                  codex("event_msg", {"type": "task_started", "turn_id": "two"}),
                  message("user", "open task", id="last")])
            jsonl(root / "sessions/child.jsonl", [codex("session_meta", {"id": "child", "source": {"subagent": "parent"}}), codex("session_meta", {"id": "main", "history_base": {"thread_id": "main"}}), message("user", "inherited")])
            result = e.collect([e.source("codex", "default", root)], END, since=START)
            # Equal timestamps are ordered by event digest, which includes environment
            # identity. Verify content/outcome association rather than one host's hash order.
            self.assertEqual({r["excerpt"]: (r["turn_id"], r["outcome"]) for r in result["evidence"]},
                             {"real instruction": ("one", "aborted"), "open task": ("two", "open")})
            keys = [(r["timestamp_utc"], r["event_id"]) for r in result["evidence"]]
            self.assertEqual(keys, sorted(keys))

    def artifact_package(self, name="patches/fixture.diff", content=b"fixture difference\n"):
        package = json.loads((Path(__file__).resolve().parents[1] / "templates/review-package.json").read_text(encoding="utf-8"))
        candidate = package["candidates"][0]
        candidate["exact_change"] = "Exact fixture difference in " + name
        candidate["change_artifacts"] = {name: hashlib.sha256(content).hexdigest()}
        candidate["proposal_digest"] = proposal_digest(candidate)
        return package

    def test_change_artifacts_bind_bytes_and_revision(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp); patch = base / "patches/fixture.diff"
            patch.parent.mkdir(); patch.write_bytes(b"fixture difference\n")
            package = self.artifact_package(); c = package["candidates"][0]
            self.assertEqual(e.validate_package(package, package_dir=base), ["candidate-1"])
            old_digest = c["proposal_digest"]
            patch.write_bytes(b"changed difference\n")
            with self.assertRaisesRegex(ValueError, "artifact changed"):
                e.validate_package(package, package_dir=base)
            c["change_artifacts"]["patches/fixture.diff"] = hashlib.sha256(patch.read_bytes()).hexdigest()
            with self.assertRaisesRegex(ValueError, "proposal content changed"):
                e.validate_package(package, package_dir=base)
            c["proposal_revision"] += 1; c["proposal_digest"] = proposal_digest(c)
            self.assertNotEqual(c["proposal_digest"], old_digest)
            self.assertEqual(e.validate_package(package, package_dir=base), ["candidate-1"])

    def test_change_artifacts_require_existing_files_and_package_directory(self):
        package = self.artifact_package()
        with self.assertRaisesRegex(ValueError, "package directory required"):
            e.validate_package(package)
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            with self.assertRaisesRegex(ValueError, "artifact is missing"):
                e.validate_package(package, package_dir=base)
            (base / "patches/fixture.diff").mkdir(parents=True)
            with self.assertRaisesRegex(ValueError, "artifact is missing"):
                e.validate_package(package, package_dir=base)

    def test_change_artifacts_reject_unsafe_paths_and_invalid_declarations(self):
        package = self.artifact_package(); c = package["candidates"][0]
        for name in ("", ".", "../outside.diff", "patches/../outside.diff", "/outside.diff",
                     "C:/outside.diff", "C:\\outside.diff", "patches\\fixture.diff", "patches//fixture.diff"):
            with self.subTest(name=name):
                c["change_artifacts"] = {name: "0" * 64}; c["proposal_digest"] = proposal_digest(c)
                with self.assertRaises(ValueError): e.validate_package(package, historical=True)
        for declaration in (None, [], {"patches/fixture.diff": "bad"}, {"patches/fixture.diff": None}):
            with self.subTest(declaration=declaration):
                c["change_artifacts"] = declaration; c["proposal_digest"] = proposal_digest(c)
                with self.assertRaises(ValueError): e.validate_package(package, historical=True)
        c["change_artifacts"] = {}; c["proposal_digest"] = proposal_digest(c)
        self.assertEqual(e.validate_package(package), ["candidate-1"])
        del c["change_artifacts"]; c["proposal_digest"] = proposal_digest(c)
        self.assertEqual(e.validate_package(package), ["candidate-1"])

    def test_change_artifacts_reject_symlink_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "package"; base.mkdir()
            outside = Path(tmp) / "outside.diff"; outside.write_bytes(b"fixture difference\n")
            try: (base / "link.diff").symlink_to(outside)
            except (OSError, NotImplementedError): self.skipTest("This host cannot create symlinks")
            package = self.artifact_package("link.diff")
            with self.assertRaisesRegex(ValueError, "artifact escapes"):
                e.validate_package(package, package_dir=base)

    def test_historical_artifacts_do_not_imply_availability_or_approval(self):
        package = self.artifact_package()
        self.assertEqual(e.validate_package(package, historical=True), ["candidate-1"])
        package["schema_version"] = 1
        c = package["candidates"][0]
        del c["proposal_revision"]; del c["proposal_digest"]; del c["change_artifacts"]
        self.assertEqual(e.validate_package(package, historical=True), ["candidate-1"])
        with self.assertRaises(ValueError): e.validate_package(package)

    def test_cli_artifact_check_is_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp); patch = base / "patches/fixture.diff"
            patch.parent.mkdir(); patch.write_bytes(b"fixture difference\n")
            package = base / "review-package.json"
            package.write_text(json.dumps(self.artifact_package()), encoding="utf-8")
            command = [sys.executable, "-B", str(Path(e.__file__).resolve()), "validate-package", "--package", str(package)]
            before = {str(p.relative_to(base)): p.read_bytes() for p in base.rglob("*") if p.is_file()}
            result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(json.loads(result.stdout)["valid"])
            self.assertEqual(before, {str(p.relative_to(base)): p.read_bytes() for p in base.rglob("*") if p.is_file()})
            patch.write_bytes(b"changed difference\n")
            changed = {str(p.relative_to(base)): p.read_bytes() for p in base.rglob("*") if p.is_file()}
            result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(result.returncode, 2)
            self.assertIn("artifact changed", json.loads(result.stderr)["error"])
            self.assertEqual(changed, {str(p.relative_to(base)): p.read_bytes() for p in base.rglob("*") if p.is_file()})

    def test_codex_app_page_context_is_not_human_feedback(self):
        self.assertFalse(e.injected_context("<external_codex_apps_open_page>"))
        frame = '<external_codex_apps_open_page>{"page_id":null}</external_codex_apps_open_page>'
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            jsonl(root / "sessions/main.jsonl", [codex("session_meta", {"id": "main"}),
                  message("user", frame), message("user", "  " + frame + "\n"),
                  message("user", "real instruction"),
                  message("user", frame + "\nPlease explain this tag"),
                  message("user", frame + "\nCompare these two states\n" + frame),
                  message("user", frame + "\nExplain this closing tag </external_codex_apps_open_page>")])
            report = e.collect([e.source("codex", "default", root)], END, since=START)
            self.assertCountEqual([r["excerpt"] for r in report["evidence"]],
                             ["real instruction", frame + "\nPlease explain this tag",
                              frame + "\nCompare these two states\n" + frame,
                              frame + "\nExplain this closing tag </external_codex_apps_open_page>"])
            self.assertEqual(report["coverage"][0]["diagnostics"]["excluded_context_messages"], 2)

    def test_claude_interruption_notice_is_not_a_human_message(self):
        notice = "[Request interrupted by user for tool use]"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "session.jsonl"
            jsonl(path, [{"type": "user", "sessionId": "s", "uuid": "one",
                         "timestamp": "2026-10-02T00:00:00Z", "message": {"content": notice}},
                        {"type": "user", "sessionId": "s", "uuid": "two",
                         "timestamp": "2026-10-02T00:00:01Z", "message": {"content": "Please explain " + notice}}])
            report = e.collect([e.source("claude", "default", path)], END, since=START)
            self.assertEqual([r["excerpt"] for r in report["evidence"]], ["Please explain " + notice])
            self.assertEqual(report["evidence"][0]["outcome"], "unknown")

    def test_claude_interruption_keeps_original_turn_outcomes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "session.jsonl"
            jsonl(path, [{"type": "user", "sessionId": "s", "uuid": "before", "timestamp": "2026-10-02T00:00:00Z", "message": {"content": "real question"}},
                        {"type": "user", "sessionId": "s", "uuid": "interruption", "timestamp": "2026-10-02T00:00:01Z", "message": {"content": "[Request interrupted by user for tool use]"}},
                        {"type": "assistant", "sessionId": "s", "timestamp": "2026-10-02T00:00:02Z", "message": {"content": "visible reply", "stop_reason": "end_turn"}}])
            report = e.collect([e.source("claude", "default", path)], END, since=START)
            self.assertEqual([r["excerpt"] for r in report["evidence"]], ["real question", "visible reply"])
            self.assertEqual([r["turn_id"] for r in report["evidence"]], ["before", "interruption"])
            self.assertEqual([r["outcome"] for r in report["evidence"]], ["unknown", "completed_unverified"])

    def test_restamped_human_fork_does_not_turn_old_message_into_new_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original = message("user", "old message", id="stable-message-id")
            original["timestamp"] = "2026-09-01T00:00:00Z"
            copied = {**original, "timestamp": "2026-10-02T00:00:00Z"}
            jsonl(root / "sessions/original.jsonl", [codex("session_meta", {"id": "original"}), original])
            jsonl(root / "sessions/fork.jsonl", [codex("session_meta", {"id": "fork", "parent_thread_id": "original", "forked_from_id": "original"}), copied])
            report = e.collect([e.source("codex", "default", root)], END, since=START)
            self.assertEqual(report["evidence"], [])
            self.assertEqual(report["deduplicated_events"], 1)

    def test_missing_corrupt_source_does_not_advance_cursor(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            jsonl(root / "one.jsonl", [message("user", "kept")])
            with (root / "one.jsonl").open("a", encoding="utf-8") as stream:
                stream.write("{broken\n")
            sources = [e.source("codex", "x", root), e.source("claude", "x", root / "missing")]
            cursors = {sources[0]["source_id"]: "2026-09-01T00:00:00Z"}
            result = e.collect(sources, END, 7, cursors=cursors)
            self.assertEqual([c["status"] for c in result["coverage"]], ["partial", "missing"])
            self.assertEqual(result["coverage"][0]["since_utc"], cursors[sources[0]["source_id"]])
            self.assertEqual(e.commit_review(result, "actual-review", cursors), cursors)

    def test_foreign_native_format_is_partial_instead_of_empty_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "foreign.jsonl"
            jsonl(p, [{"type": "user", "timestamp": "2026-10-02T00:00:00Z", "message": {"content": "different client"}}])
            result = e.collect([e.source("codex", "default", p)], END, since=START)
            self.assertEqual(result["coverage"][0]["status"], "partial")
            self.assertEqual(e.commit_review(result, "review", {}), {})

    def test_claude_tool_result_not_human_and_future_completion_not_used(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "session.jsonl"
            jsonl(path, [{"type": "user", "sessionId": "s", "uuid": "u", "timestamp": "2026-10-02T00:00:00Z", "message": {"content": "real question"}},
                         {"type": "user", "timestamp": "2026-10-02T00:00:01Z", "message": {"content": [{"type": "tool_result", "content": "tool output"}]}},
                         {"type": "assistant", "timestamp": "2026-10-02T00:00:02Z", "message": {"content": [{"type": "thinking", "thinking": "hidden"}, {"type": "text", "text": "visible"}]}},
                         {"type": "system", "subtype": "turn_duration", "timestamp": "2026-10-05T00:00:00Z"}])
            report = e.collect([e.source("claude", "default", path)], END, since=START)
            self.assertEqual([r["excerpt"] for r in report["evidence"]], ["real question", "visible"])
            self.assertEqual({r["outcome"] for r in report["evidence"]}, {"unknown"})

    def test_hermes_read_only_parent_retained_and_ended_is_not_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.db"
            db = sqlite3.connect(path)
            db.executescript("CREATE TABLE sessions(id TEXT, ended_at REAL, parent_session_id TEXT); CREATE TABLE messages(id INTEGER, session_id TEXT, role TEXT, content TEXT, timestamp REAL, reasoning TEXT);")
            db.execute("INSERT INTO sessions VALUES ('s',?, 'compressed-parent')", ((END - timedelta(days=1)).timestamp(),))
            db.execute("INSERT INTO messages VALUES (1,'s','assistant','visible',?,'private reasoning')", ((END - timedelta(days=2)).timestamp(),))
            db.commit(); db.close()
            before = path.read_bytes()
            report = e.collect([e.source("hermes", "office", path)], END, since=START)
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(report["evidence"][0]["parent_session_id"], "compressed-parent")
            self.assertEqual(report["evidence"][0]["outcome"], "completed_unverified")
            self.assertNotIn("private reasoning", json.dumps(report))

    def test_sensitive_text_and_internal_content_are_omitted(self):
        raw = 'api_key="abcdSECRET123"\nAuthorization: Bearer abcSECRET\nCookie: abcCOOKIE\nhttps://user:pass@example.com\nsk-12345678901234567890\n/Users/alice/docs\nC:\\Users\\Bob\\file\n<think>hidden reasoning</think>\n-----BEGIN PRIVATE KEY-----\nprivateTEXT\n-----END PRIVATE KEY-----'
        clean = e.redact(raw)
        for secret in ("abcdSECRET123", "abcSECRET", "abcCOOKIE", "user:pass", "12345678901234567890", "alice", "Bob", "hidden reasoning", "privateTEXT"):
            self.assertNotIn(secret, clean)

    def test_summary_requires_verification_and_discards_extra_fields(self):
        row = dict(schema_version=1, environment_id="windows:m:u", agent="workbuddy", profile="default", session_id="s", event_id="e", timestamp_utc="2026-10-02T08:00:00+08:00", role="observation", summary="checked", outcome="verified_success", origin_ref="actual record", reasoning="private")
        with self.assertRaises(ValueError):
            e.validate_summary(row)
        row["verification_ref"] = "real check"
        result = e.validate_summary(row)
        self.assertNotIn("reasoning", result)
        self.assertEqual(result["timestamp_utc"], "2026-10-02T00:00:00Z")
        row["timestamp_utc"] = "2026-10-02T00:00:00"
        with self.assertRaises(ValueError):
            e.validate_summary(row)

    def test_output_cannot_enter_shared_source_even_via_symlink(self):
        with self.assertRaises(ValueError):
            e.safe_local(e.SHARED_ROOT / "raw.json")
        with tempfile.TemporaryDirectory() as tmp:
            link = Path(tmp) / "shared"
            link.symlink_to(e.SHARED_ROOT, target_is_directory=True)
            with self.assertRaises(ValueError):
                e.safe_local(link / "raw.json")

    def test_package_detects_baseline_change_and_path_escape(self):
        package = json.loads((Path(__file__).resolve().parents[1] / "templates/review-package.json").read_text(encoding="utf-8"))
        c = package["candidates"][0]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(e.validate_package(package, root), [c["id"]])
            p = root / c["targets"][0]; p.parent.mkdir(parents=True); p.write_text("external change", encoding="utf-8")
            with self.assertRaises(ValueError):
                e.validate_package(package, root)
            c["targets"] = ["../outside"]; c["baseline"] = {"../outside": None}
            with self.assertRaises(ValueError):
                e.validate_package(package, root)

    def test_rejected_candidate_requires_new_distinct_evidence(self):
        c = {"proposal_key": "same-change", "evidence_ids": ["one"]}
        decisions = [{"proposal_key": c["proposal_key"], "evidence_ids": list(c["evidence_ids"]), "decision": "rejected"}]
        self.assertFalse(e.rejection_has_new_evidence(c, decisions))
        c["evidence_ids"].append("two")
        self.assertTrue(e.rejection_has_new_evidence(c, decisions))

    def test_new_package_requires_every_platform_assessment(self):
        package = json.loads((Path(__file__).resolve().parents[1] / "templates/review-package.json").read_text(encoding="utf-8"))
        self.assertEqual(package["schema_version"], 2)
        self.assertEqual(e.validate_package(package), ["candidate-1"])
        del package["candidates"][0]["platform_assessment"]["wsl"]
        c = package["candidates"][0]; c["proposal_digest"] = proposal_digest(c)
        with self.assertRaises(ValueError): e.validate_package(package)

    def test_platform_specific_fix_and_unverified_targets_are_explicit(self):
        package = json.loads((Path(__file__).resolve().parents[1] / "templates/review-package.json").read_text(encoding="utf-8"))
        item = package["candidates"][0]["platform_assessment"]["windows"]
        item.update(applies=False, verification_status="not_applicable", impact="Mac launcher only", validation="Windows source unchanged")
        c = package["candidates"][0]; c["proposal_digest"] = proposal_digest(c)
        e.validate_package(package)
        item["verification_status"] = "verified"
        c["proposal_digest"] = proposal_digest(c)
        with self.assertRaises(ValueError): e.validate_package(package)

    def test_historical_schema_one_remains_readable(self):
        package = json.loads((Path(__file__).resolve().parents[1] / "templates/review-package.json").read_text(encoding="utf-8"))
        package["schema_version"] = 1
        package["candidates"][0].pop("platform_assessment")
        package["candidates"][0].pop("proposal_digest")
        package["candidates"][0].pop("proposal_revision")
        self.assertEqual(e.validate_package(package, historical=True), ["candidate-1"])

    def test_new_package_requires_revision_digest_but_history_stays_readable(self):
        package = json.loads((Path(__file__).resolve().parents[1] / "templates/review-package.json").read_text(encoding="utf-8"))
        c = package["candidates"][0]
        c.pop("proposal_revision"); c.pop("proposal_digest")
        with self.assertRaises(ValueError): e.validate_package(package)
        self.assertEqual(e.validate_package(package, historical=True), ["candidate-1"])

    def test_proposal_digest_detects_changed_conditions_before_approval(self):
        package = json.loads((Path(__file__).resolve().parents[1] / "templates/review-package.json").read_text(encoding="utf-8"))
        c = package["candidates"][0]
        e.validate_package(package)
        c["exact_change"] += " Under a different condition."
        with self.assertRaises(ValueError): e.validate_package(package)

    def test_memory_update_requires_source_and_existing_target(self):
        package = json.loads((Path(__file__).resolve().parents[1] / "templates/review-package.json").read_text(encoding="utf-8"))
        c = package["candidates"][0]
        c.pop("proposal_digest")
        c.update(owner="memories", related_group="fixture")
        c["memory_update"] = {"operation": "correct", "knowledge_status": "observed", "target_refs": ["memories/DECISIONS.md#Fixture"], "basis_refs": []}
        with self.assertRaises(ValueError): e.validate_package(package)
        c["memory_update"]["basis_refs"] = ["fixture:actual-check"]
        c["proposal_digest"] = proposal_digest(c)
        self.assertEqual(e.validate_package(package), ["candidate-1"])


    def test_cli_utf8_cursors_survive_gbk_default(self):
        original = Path.read_text
        def default_gbk(path, encoding=None, errors=None):
            return original(path, encoding=encoding or "gbk", errors=errors)
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            cursor = base / "review-cursors.json"
            cursor.write_text(json.dumps({"旧来源": "2026-10-01T00:00:00Z"}, ensure_ascii=False), encoding="utf-8")
            report = base / "复盘.json"
            report.write_text(json.dumps({"schema_version": 1, "coverage": [{"source_id": "新来源", "status": "complete", "until_utc": "2026-10-05T00:00:00Z"}]}, ensure_ascii=False), encoding="utf-8")
            commands = [
                ["evidence.py", "collect", "--until", "2026-10-05T00:00:00Z", "--output", str(base / "采集.json")],
                ["evidence.py", "commit-review", "--report", str(report), "--reference", "fixture:编码复盘"],
            ]
            with patch.object(e, "LOCAL_ROOT", base), patch.object(e, "discover", return_value=[]), patch.object(Path, "read_text", default_gbk):
                for args in commands:
                    with self.subTest(command=args[1]), patch.object(sys, "argv", args), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                        self.assertEqual(e.main(), 0)
            self.assertTrue((base / "采集.json").is_file())
            self.assertEqual(json.loads(cursor.read_text(encoding="utf-8")), {"旧来源": "2026-10-01T00:00:00Z", "新来源": "2026-10-05T00:00:00Z"})

if __name__ == "__main__":
    unittest.main()
