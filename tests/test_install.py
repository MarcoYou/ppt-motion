"""Isolated installer/bootstrap checks; these tests never download packages."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PROJECT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


installer = load_module('test_installer', PROJECT / 'install.py')
runner = load_module('test_runner', PROJECT / 'skill/ppt-motion/scripts/run.py')


class InstallTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='ppt motion 설치 ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source' / 'ppt-motion'
        shutil.copytree(installer.SOURCE, self.source, ignore=installer.ignored)
        self.patch = mock.patch.object(installer, 'SOURCE', self.source)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.skills = self.root / 'user skills'
        self.target = self.skills / 'ppt-motion'

    def install(self, **kwargs):
        return installer.install('codex', self.skills, skip_runtime=True, **kwargs)

    def test_complete_copy_and_idempotent_update(self):
        first = self.install()
        self.assertTrue(first['changed'])
        self.assertIsNone(first['backup'])
        for relative in ('SKILL.md', 'scripts/run.py', 'scripts/requirements.txt',
                         'scripts/ppt_motion.py', 'assets/viewer.js', 'references/configuration.md'):
            self.assertEqual((self.source / relative).read_bytes(), (self.target / relative).read_bytes())
        self.assertEqual(installer.file_manifest(self.source), installer.file_manifest(self.target))
        self.assertFalse(any(self.target.rglob('*.pyc')))
        self.assertFalse(self.install()['changed'])
        self.assertFalse((self.skills / '.ppt-motion-backups').exists())

    def test_managed_update_keeps_previous_version(self):
        self.install()
        old = (self.target / 'SKILL.md').read_text(encoding='utf-8')
        (self.source / 'SKILL.md').write_text(old + '\nNew version\n', encoding='utf-8')
        result = self.install()
        backup = Path(result['backup'])
        self.assertEqual((backup / 'SKILL.md').read_text(encoding='utf-8'), old)
        self.assertEqual((self.target / 'SKILL.md').read_text(encoding='utf-8'), old + '\nNew version\n')
        self.assertFalse(self.install()['changed'])

    def test_modified_and_extra_files_require_force_and_are_backed_up(self):
        self.install()
        (self.target / 'SKILL.md').write_text('My custom skill', encoding='utf-8')
        (self.target / 'notes.txt').write_text('Keep me', encoding='utf-8')
        with self.assertRaisesRegex(RuntimeError, '--force'):
            self.install()
        self.assertEqual((self.target / 'SKILL.md').read_text(), 'My custom skill')
        result = self.install(force=True)
        self.assertEqual((Path(result['backup']) / 'notes.txt').read_text(), 'Keep me')
        self.assertEqual((Path(result['backup']) / 'SKILL.md').read_text(), 'My custom skill')

    def test_missing_file_and_corrupt_marker_are_not_managed(self):
        self.install()
        (self.target / 'assets/viewer.js').unlink()
        with self.assertRaisesRegex(RuntimeError, '--force'):
            self.install()
        self.install(force=True)
        (self.target / installer.MARKER).write_text('[]', encoding='utf-8')
        with self.assertRaisesRegex(RuntimeError, '--force'):
            self.install()

    def test_unmanaged_regular_file_backed_up(self):
        self.skills.mkdir()
        self.target.write_text('An existing file', encoding='utf-8')
        with self.assertRaisesRegex(RuntimeError, '--force'):
            self.install()
        result = self.install(force=True)
        self.assertEqual(Path(result['backup']).read_text(), 'An existing file')

    def test_existing_symlink_is_moved_without_modifying_referent(self):
        self.skills.mkdir()
        external = self.root / 'external'
        external.mkdir()
        (external / 'keep.txt').write_text('original', encoding='utf-8')
        try:
            self.target.symlink_to(external, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f'Symlinks unavailable: {exc}')
        with self.assertRaisesRegex(RuntimeError, '--force'):
            self.install()
        result = self.install(force=True)
        self.assertTrue(Path(result['backup']).is_symlink())
        self.assertFalse(self.target.is_symlink())
        self.assertEqual(list(external.iterdir()), [external / 'keep.txt'])
        self.assertEqual((external / 'keep.txt').read_text(), 'original')

    def test_broken_symlink_requires_force(self):
        self.skills.mkdir()
        try:
            self.target.symlink_to(self.root / 'absent', target_is_directory=True)
        except OSError as exc:
            self.skipTest(f'Symlinks unavailable: {exc}')
        with self.assertRaisesRegex(RuntimeError, '--force'):
            self.install()
        result = self.install(force=True)
        self.assertTrue(Path(result['backup']).is_symlink())
        self.assertFalse((self.root / 'absent').exists())

    def test_relative_symlink_backup_keeps_its_referent(self):
        self.skills.mkdir()
        external = self.root / 'original'
        external.mkdir()
        (external / 'keep.txt').write_text('original', encoding='utf-8')
        try:
            self.target.symlink_to('../original', target_is_directory=True)
        except OSError as exc:
            self.skipTest(f'Symlinks unavailable: {exc}')
        result = self.install(force=True)
        backup = Path(result['backup'])
        self.assertTrue(backup.is_symlink())
        self.assertEqual(backup.readlink(), Path('../original'))
        self.assertEqual(backup.resolve(), external.resolve())
        self.assertEqual((backup / 'keep.txt').read_text(), 'original')

    def test_bytecode_created_by_older_runner_does_not_block_updates(self):
        self.install()
        cache = self.target / 'scripts/__pycache__'
        cache.mkdir()
        (cache / 'sample.cpython-311.pyc').write_bytes(b'cached')
        self.assertFalse(self.install()['changed'])

    def test_setup_failure_preserves_existing_install(self):
        self.install()
        previous = installer.file_manifest(self.target)
        with (self.source / 'SKILL.md').open('a', encoding='utf-8') as output:
            output.write('\nnew version\n')
        with mock.patch.object(installer, 'setup_runtime', side_effect=RuntimeError('offline')):
            with self.assertRaisesRegex(RuntimeError, 'offline'):
                installer.install('codex', self.skills)
        self.assertEqual(installer.file_manifest(self.target), previous)
        self.assertFalse(list(self.skills.glob('.ppt-motion-stage-*')))

    def test_commit_failure_rolls_back_previous_install(self):
        self.install()
        previous = installer.file_manifest(self.target)
        with (self.source / 'SKILL.md').open('a', encoding='utf-8') as output:
            output.write('\nnew version\n')
        real_rename = Path.rename
        def fail_staging(path, destination):
            if path.name.startswith('.ppt-motion-stage-'):
                raise OSError('simulated final rename failure')
            return real_rename(path, destination)
        with mock.patch.object(Path, 'rename', fail_staging):
            with self.assertRaisesRegex(OSError, 'simulated'):
                self.install()
        self.assertEqual(installer.file_manifest(self.target), previous)
        self.assertFalse(list(self.skills.glob('.ppt-motion-stage-*')))

    def test_source_directory_is_never_install_destination(self):
        with self.assertRaisesRegex(RuntimeError, 'outside the source'):
            installer.install('codex', self.source.parent, skip_runtime=True, force=True)

    def test_cancellation_during_commit_restores_previous_install(self):
        self.install()
        previous = installer.file_manifest(self.target)
        with (self.source / 'SKILL.md').open('a', encoding='utf-8') as output:
            output.write('\nnew version\n')
        real_rename = Path.rename
        def interrupt_staging(path, destination):
            if path.name.startswith('.ppt-motion-stage-'):
                raise KeyboardInterrupt()
            return real_rename(path, destination)
        with mock.patch.object(Path, 'rename', interrupt_staging):
            with self.assertRaises(KeyboardInterrupt):
                self.install()
        self.assertEqual(installer.file_manifest(self.target), previous)
        self.assertFalse(list(self.skills.glob('.ppt-motion-stage-*')))

    def test_cli_both_clients_use_explicit_isolated_paths(self):
        for client in ('codex', 'claude-code'):
            destination = self.root / client
            result = subprocess.run([sys.executable, str(PROJECT / 'install.py'), '--client', client,
                                     '--skills-dir', str(destination), '--skip-runtime'],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload['installed'], str(destination.resolve() / 'ppt-motion'))
            self.assertEqual(payload['client'], client)

    def test_concurrent_installers_commit_once(self):
        command = [sys.executable, str(PROJECT / 'install.py'), '--client', 'codex',
                   '--skills-dir', str(self.skills), '--skip-runtime']
        processes = [subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                     for _ in range(2)]
        payloads = []
        for process in processes:
            stdout, stderr = process.communicate(timeout=30)
            self.assertEqual(process.returncode, 0, stderr)
            payloads.append(json.loads(stdout))
        self.assertEqual(sorted(payload['changed'] for payload in payloads), [False, True])
        self.assertIsNotNone(installer.managed_manifest(self.target))

    def test_default_directories_do_not_write_to_actual_home(self):
        with mock.patch.dict(os.environ, {'CODEX_HOME': str(self.root / 'custom codex')}):
            self.assertEqual(installer.default_skills_dir('codex'), self.root / 'custom codex/skills')
        with mock.patch.object(Path, 'home', return_value=self.root):
            self.assertEqual(installer.default_skills_dir('claude-code'), self.root / '.claude/skills')


class RuntimeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='motion runtime ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.requirements = self.root / 'requirements.txt'
        self.requirements.write_text('PyMuPDF==1.27.1\nlxml==6.0.2\n', encoding='utf-8')

    def fake_run(self, args, **kwargs):
        if 'venv' in args:
            runtime = Path(args[-1])
            interpreter = runner.python_path(runtime)
            interpreter.parent.mkdir(parents=True)
            interpreter.write_text('fake interpreter', encoding='utf-8')
        return subprocess.CompletedProcess(args, 0)

    def test_help_and_version_never_prepare_runtime(self):
        with mock.patch.object(runner, 'ensure_runtime', side_effect=AssertionError('must not install')):
            for args in ([], ['--help'], ['-h'], ['--setup', '--help'], ['--version']):
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    self.assertEqual(runner.main(args), 0)
                    self.assertTrue(output.getvalue().strip())

    def test_cache_reuse_probes_versions_without_reinstalling(self):
        with mock.patch.object(runner.subprocess, 'run', side_effect=self.fake_run) as commands:
            first, reused = runner.ensure_runtime(self.requirements, self.root / 'cache')
            self.assertFalse(reused)
            second, reused = runner.ensure_runtime(self.requirements, self.root / 'cache')
            self.assertTrue(reused)
            self.assertEqual(first, second)
        executed = [call.args[0] for call in commands.call_args_list]
        self.assertEqual(sum('venv' in command for command in executed), 1)
        self.assertEqual(sum('pip' in command for command in executed), 1)
        self.assertEqual(sum('-c' in command for command in executed), 2)
        self.assertTrue((first / runner.READY_FILE).is_file())

    def test_failed_setup_has_no_ready_marker_and_retries(self):
        def fail_pip(args, **kwargs):
            if 'pip' in args:
                raise subprocess.CalledProcessError(1, args)
            return self.fake_run(args, **kwargs)
        identity = runner.runtime_identity(self.requirements)
        runtime = runner.runtime_path(identity, self.root / 'cache')
        with mock.patch.object(runner.subprocess, 'run', side_effect=fail_pip):
            with self.assertRaisesRegex(RuntimeError, 'offline setup'):
                runner.ensure_runtime(self.requirements, self.root / 'cache')
        self.assertFalse((runtime / runner.READY_FILE).exists())
        with mock.patch.object(runner.subprocess, 'run', side_effect=self.fake_run):
            _, reused = runner.ensure_runtime(self.requirements, self.root / 'cache')
            self.assertFalse(reused)
        self.assertTrue((runtime / runner.READY_FILE).is_file())

    def test_invalid_import_does_not_mark_runtime_ready(self):
        def bad_import(args, **kwargs):
            if '-c' in args:
                return subprocess.CompletedProcess(args, 1)
            return self.fake_run(args, **kwargs)
        with mock.patch.object(runner.subprocess, 'run', side_effect=bad_import):
            with self.assertRaisesRegex(RuntimeError, 'import/version'):
                runner.ensure_runtime(self.requirements, self.root / 'cache')
        self.assertFalse(list((self.root / 'cache').rglob(runner.READY_FILE)))

    def test_broken_cached_runtime_is_rebuilt(self):
        with mock.patch.object(runner.subprocess, 'run', side_effect=self.fake_run):
            runtime, _ = runner.ensure_runtime(self.requirements, self.root / 'cache')
        runner.python_path(runtime).unlink()
        with mock.patch.object(runner.subprocess, 'run', side_effect=self.fake_run) as commands:
            rebuilt, reused = runner.ensure_runtime(self.requirements, self.root / 'cache')
        self.assertFalse(reused)
        self.assertEqual(rebuilt, runtime)
        self.assertEqual(sum('pip' in call.args[0] for call in commands.call_args_list), 1)

    def test_changed_requirements_and_interpreter_get_different_caches(self):
        initial = runner.runtime_identity(self.requirements)
        self.requirements.write_text('PyMuPDF==1.27.2\nlxml==6.0.2\n', encoding='utf-8')
        changed = runner.runtime_identity(self.requirements)
        self.assertNotEqual(runner.runtime_path(initial), runner.runtime_path(changed))
        changed_python = dict(initial, python='3.99.0')
        changed_machine = dict(initial, machine='a-different-machine')
        self.assertNotEqual(runner.runtime_path(initial), runner.runtime_path(changed_python))
        self.assertNotEqual(runner.runtime_path(initial), runner.runtime_path(changed_machine))

    def test_runtime_root_override(self):
        with mock.patch.dict(os.environ, {'PPT_MOTION_RUNTIME_ROOT': str(self.root)}):
            self.assertEqual(runner.runtime_root(), self.root.resolve())

    def test_forwarding_preserves_arguments_and_exit_code(self):
        runtime = self.root / 'cache'
        args = ['init', '--pdf', 'deck with spaces.pdf', '--out', '내 발표']
        with mock.patch.object(runner, 'ensure_runtime', return_value=(runtime, True)):
            with mock.patch.object(runner.subprocess, 'call', return_value=7) as call:
                self.assertEqual(runner.main(args), 7)
        self.assertEqual(call.call_args.args[0], [str(runner.python_path(runtime)), '-E', '-s', '-B', str(runner.ENGINE), *args])

    def test_forwarded_literal_setup_filename_is_not_a_wrapper_flag(self):
        runtime = self.root / 'cache'
        args = ['build', '--', '--setup']
        with mock.patch.object(runner, 'ensure_runtime', return_value=(runtime, True)):
            with mock.patch.object(runner.subprocess, 'call', return_value=0) as call:
                self.assertEqual(runner.main(args), 0)
        self.assertEqual(call.call_args.args[0][-3:], args)

    def test_pip_target_and_python_paths_cannot_escape_environment(self):
        unsafe = {'PIP_TARGET': '/do-not-write', 'PIP_PREFIX': '/do-not-write',
                  'PIP_CONFIG_FILE': '/custom-config', 'PYTHONPATH': '/custom-modules',
                  'PYTHONHOME': '/custom-python', 'PIP_NO_INDEX': '1', 'PIP_FIND_LINKS': str(self.root)}
        with mock.patch.dict(os.environ, unsafe):
            env = runner.clean_environment()
        for name in ('PIP_TARGET', 'PIP_PREFIX', 'PYTHONPATH', 'PYTHONHOME'):
            self.assertNotIn(name, env)
        self.assertEqual(env['PIP_CONFIG_FILE'], os.devnull)
        self.assertEqual(env['PIP_NO_INDEX'], '1')
        self.assertEqual(env['PIP_FIND_LINKS'], str(self.root))

    def test_unpinned_requirement_fails_before_any_subprocess(self):
        self.requirements.write_text('PyMuPDF>=1.27\n', encoding='utf-8')
        with mock.patch.object(runner.subprocess, 'run') as command:
            with self.assertRaisesRegex(RuntimeError, 'exact package==version'):
                runner.ensure_runtime(self.requirements, self.root / 'cache')
        command.assert_not_called()


if __name__ == '__main__':
    unittest.main()
