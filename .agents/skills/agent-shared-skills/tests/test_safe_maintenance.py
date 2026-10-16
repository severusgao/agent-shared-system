from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import sync_agent_skill_links as links
from summarize_shared_skills import summarize, parse_skill_md
from audit_shared_skills import audit as audit_skills
from skill_metadata import MetadataError


class SafeMaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / 'source'
        self.target = self.root / 'target'
        self.source.mkdir()
        self.target.mkdir()
        self.registry = self.root / 'registry.json'
        self.registry.write_text('{"targets": []}', encoding='utf-8')
        self.state = self.root / 'state.json'
        for name in ('alpha', 'beta'):
            directory = self.source / name
            directory.mkdir()
            (directory / 'SKILL.md').write_text(f'---\nname: {name}\ndescription: 当用户要求示例操作时使用。\n---\n', encoding='utf-8')

    def plan(self, replace=False, skills=None):
        return links.audit(self.source, self.source, self.registry, self.state,
                           None, skills, False, False,
                           direct_target={'id': 'test', 'root': self.target,
                                          'strategy': links.default_strategy(links.current_environment().platform)},
                           replace_local=replace)

    def apply(self, plan):
        return links.apply_plans(plan, self.root / 'backup', True)

    def cli(self, *args):
        return subprocess.run([sys.executable, '-B', str(SCRIPTS / 'sync_agent_skill_links.py'),
                               '--shared-root', str(self.source), '--local-root', str(self.source),
                               '--registry', str(self.registry), '--state-file', str(self.state),
                               *args], capture_output=True, text=True, encoding='utf-8')

    def test_apply_requires_selected_target(self):
        result = self.cli('--apply', '--yes')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.state.exists())

    def test_takeover_requires_skill_filter(self):
        result = self.cli('--target-dir', str(self.target), '--replace-local')
        self.assertNotEqual(result.returncode, 0)

    def test_real_directory_is_protected(self):
        (self.target / 'alpha').mkdir()
        with self.assertRaises(links.LinkApplyError):
            self.apply(self.plan())
        self.assertFalse(links.is_link_like(self.target / 'alpha'))
        self.assertFalse((self.target / 'beta').exists())

    def test_explicit_takeover_preserves_original(self):
        native = self.target / 'alpha'
        native.mkdir()
        (native / 'keep.txt').write_text('original', encoding='utf-8')
        self.apply(self.plan(True, ['alpha']))
        self.assertTrue(links.same_path(native, self.source / 'alpha'))
        backups = list((self.root / 'backup').rglob('keep.txt'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(), 'original')
        self.assertFalse((self.target / 'beta').exists())

    def test_failed_creation_restores_real_directory(self):
        native = self.target / 'alpha'
        native.mkdir()
        (native / 'keep.txt').write_text('original')
        with patch.object(links, 'create_link', side_effect=OSError('injected failure')):
            with self.assertRaises(links.LinkApplyError):
                self.apply(self.plan(True, ['alpha']))
        self.assertEqual((native / 'keep.txt').read_text(), 'original')

    def test_batch_failure_restores_earlier_link_and_failed_entry(self):
        old = self.root / 'old'
        old.mkdir()
        strategy = links.default_strategy(links.current_environment().platform)
        links.create_link(self.target / 'alpha', old, strategy)
        original_create = links.create_link
        def fail_second(entry, target, strategy):
            if entry.name == 'beta':
                raise OSError('second operation fails')
            return original_create(entry, target, strategy)
        with patch.object(links, 'create_link', side_effect=fail_second):
            with self.assertRaises(links.LinkApplyError):
                self.apply(self.plan())
        self.assertTrue(links.same_path(self.target / 'alpha', old))
        self.assertFalse(os.path.lexists(self.target / 'beta'))

    def test_changed_target_is_not_overwritten(self):
        plan = self.plan()
        (self.target / 'alpha').mkdir()
        with self.assertRaisesRegex(links.LinkApplyError, 'changed after preview'):
            self.apply(plan)
        self.assertTrue((self.target / 'alpha').is_dir())
        self.assertFalse((self.target / 'beta').exists())

    def test_rollback_failure_keeps_backup_and_reports_entry(self):
        native = self.target / 'alpha'
        native.mkdir()
        (native / 'keep.txt').write_text('original')
        rename = os.rename
        def fail_restore(source, destination):
            if Path(source).parent.parent.name == 'backup':
                raise OSError('restore unavailable')
            return rename(source, destination)
        with patch.object(links, 'create_link', side_effect=OSError('create unavailable')), patch.object(links.os, 'rename', side_effect=fail_restore):
            with self.assertRaisesRegex(links.LinkApplyError, 'restore unavailable'):
                self.apply(self.plan(True, ['alpha']))
        self.assertEqual(len(list((self.root / 'backup').rglob('keep.txt'))), 1)

    def test_broken_real_link_can_be_repaired(self):
        old = self.root / 'old'
        old.mkdir()
        strategy = links.default_strategy(links.current_environment().platform)
        links.create_link(self.target / 'alpha', old, strategy)
        old.rmdir()
        self.apply(self.plan(skills=['alpha']))
        self.assertTrue(links.same_path(self.target / 'alpha', self.source / 'alpha'))

    def test_failed_batch_removes_created_parent_directories(self):
        self.target = self.root / 'new-agent' / 'skills'
        plan = self.plan(skills=['alpha'])
        agent = plan['agents'][0]
        agent['root_action'] = 'create-root'
        agent['plans'] = [links.plan_entry(self.target, self.source, 'alpha')]
        with patch.object(links, 'create_link', side_effect=OSError('failure')):
            with self.assertRaises(links.LinkApplyError):
                self.apply(plan)
        self.assertFalse((self.root / 'new-agent').exists())

    def test_state_write_failure_reports_pending(self):
        argv = ['sync', '--shared-root', str(self.source), '--local-root', str(self.source),
                '--registry', str(self.registry), '--state-file', str(self.state),
                '--target-dir', str(self.target), '--skills', 'alpha', '--apply', '--yes']
        with patch.object(sys, 'argv', argv), patch.object(links, 'record_synced_instances', side_effect=OSError('state unavailable')):
            self.assertEqual(links.main(), 1)
        self.assertFalse(self.state.exists())

    def test_unavailable_skill_returns_failure_without_state(self):
        result = self.cli('--target-dir', str(self.target), '--skills', 'missing', '--apply', '--yes')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.state.exists())

    def test_cli_applies_only_to_temporary_target(self):
        result = self.cli('--target-dir', str(self.target), '--skills', 'alpha', '--apply', '--yes')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(links.same_path(self.target / 'alpha', self.source / 'alpha'))
        state = json.loads(self.state.read_text())
        self.assertEqual(len(state['instances']), 1)

    def test_multiline_yaml_and_nested_inventory(self):
        path = self.source / 'alpha' / 'SKILL.md'
        path.write_text('---\nname: alpha\ndescription: >\n  当用户要求\n  示例操作时使用。\ndisable-model-invocation: true\n---\n', encoding='utf-8')
        child = self.source / 'alpha' / 'child'
        child.mkdir()
        (child / 'SKILL.md').write_text('---\nname: child\ndescription: 当用户需要子技能时使用。\n---\n', encoding='utf-8')
        rows = summarize(self.source)
        self.assertEqual(len(rows), 2)
        self.assertIn('示例操作', rows[0]['description'])
        self.assertEqual(rows[0]['nested_skills'][0]['parent_skill'], 'alpha')
        self.assertTrue({'folder','name','description','has_scripts','has_references','has_openai_yaml'} <= rows[0].keys())

    def test_invalid_yaml_is_reported_not_executed(self):
        path = self.source / 'alpha' / 'SKILL.md'
        path.write_text('---\nname: alpha\ndescription: !!python/object/apply:os.system [echo unsafe]\n---\n')
        with self.assertRaises(MetadataError):
            parse_skill_md(path)
        self.assertTrue(audit_skills(self.source)['errors'])

    def test_quoted_boolean_is_rejected(self):
        path = self.source / 'alpha' / 'SKILL.md'
        path.write_text('---\nname: alpha\ndescription: "when needed: quoted text"\ndisable-model-invocation: "false"\n---\n')
        self.assertTrue(audit_skills(self.source)['errors'])

    def test_missing_yaml_dependency_has_actionable_message(self):
        with patch.dict(sys.modules, {'yaml': None}):
            with self.assertRaisesRegex(MetadataError, 'pip install PyYAML'):
                parse_skill_md(self.source / 'alpha' / 'SKILL.md')

    def test_cache_and_explicit_broken_links_are_reported(self):
        cache = self.source / 'alpha' / '__pycache__'
        cache.mkdir()
        (self.source / 'alpha' / 'notes.md').write_text('[missing](absent.md)\n[web](https://example.com)\n`[example](not-a-file.md)`\n')
        warnings = audit_skills(self.source)['warnings']
        self.assertTrue(any('generated/vendor' in item for item in warnings))
        self.assertTrue(any('absent.md' in item for item in warnings))
        self.assertFalse(any('not-a-file' in item for item in warnings))


if __name__ == '__main__':
    unittest.main()
