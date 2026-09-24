#!/usr/bin/env python3
"""Install the bundled ppt-motion skill and its isolated Python runtime."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

SOURCE = Path(__file__).resolve().parent / 'skill' / 'ppt-motion'
MARKER = '.ppt-motion-install.json'
MANAGED_BY = 'ppt-motion/install.py'


def default_skills_dir(client: str) -> Path:
    if client == 'codex':
        return Path(os.environ.get('CODEX_HOME') or Path.home() / '.codex').expanduser() / 'skills'
    return Path.home() / '.claude' / 'skills'


def ignored(directory: str, names: list[str]) -> set[str]:
    return {name for name in names if name in {'__pycache__', '.DS_Store', '.git'}
            or name.endswith(('.pyc', '.pyo'))}


def file_manifest(root: Path) -> dict[str, str]:
    files = {}
    for directory, subdirs, names in os.walk(root, followlinks=False):
        parent = Path(directory)
        # Runtime-created bytecode is never distributed or treated as user work.
        skip = ignored(directory, subdirs + names)
        subdirs[:] = sorted(name for name in subdirs if name not in skip)
        for name in subdirs + sorted(name for name in names if name not in skip):
            path = parent / name
            if path.is_symlink():
                raise RuntimeError(f'Symlink found in skill: {path}')
            if path.is_file() and path != root / MARKER:
                files[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
            elif not path.is_dir() and path != root / MARKER:
                raise RuntimeError(f'Unsupported file in skill: {path}')
    return files


def managed_manifest(target: Path) -> dict | None:
    if target.is_symlink() or not target.is_dir() or (target / MARKER).is_symlink():
        return None
    try:
        marker = json.loads((target / MARKER).read_text(encoding='utf-8'))
        if (marker.get('managedBy') != MANAGED_BY or marker.get('schema') != 1
                or not isinstance(marker.get('files'), dict)):
            return None
        if marker['files'] != file_manifest(target):
            return None
        return marker
    except (OSError, ValueError, AttributeError, RuntimeError):
        return None


def runner_module():
    spec = importlib.util.spec_from_file_location('ppt_motion_installer_runtime', SOURCE / 'scripts' / 'run.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def setup_runtime(skill: Path) -> None:
    result = subprocess.run([sys.executable, '-E', '-s', '-B', str(skill / 'scripts' / 'run.py'), '--setup'],
                            stdout=sys.stderr, stderr=sys.stderr)
    if result.returncode:
        raise RuntimeError('Runtime preparation failed; the previous installation was preserved. '
                           'Retry after resolving the error, or use --skip-runtime to install the skill files only.')


def install(client: str, skills_dir: Path, *, force: bool = False, skip_runtime: bool = False) -> dict:
    if sys.version_info < (3, 11):
        raise RuntimeError('Python 3.11 or newer is required.')
    if not (SOURCE / 'SKILL.md').is_file() or not (SOURCE / 'scripts' / 'run.py').is_file():
        raise RuntimeError(f'Bundled skill is missing at {SOURCE}. Run install.py from a complete checkout or release archive.')
    skills_dir = skills_dir.expanduser().resolve()
    target = skills_dir / 'ppt-motion'
    # Never resolve the final target: an existing link must be moved as a link.
    if target == SOURCE.resolve() or skills_dir.is_relative_to(SOURCE.resolve()):
        raise RuntimeError('Choose an installation directory outside the source skill.')
    if not target.is_symlink() and SOURCE.resolve().is_relative_to(target):
        raise RuntimeError('The installation destination contains the source checkout.')
    incoming = file_manifest(SOURCE)
    runner = runner_module()
    with runner.FileLock(skills_dir / '.ppt-motion-install.lock'):
        exists = target.exists() or target.is_symlink()
        managed = managed_manifest(target) if exists else None
        if exists and managed is None and not force:
            raise RuntimeError(f'{target} already exists and is unmanaged or locally modified. '
                               'Use --force to preserve it in a backup and install this version.')
        if managed and managed['files'] == incoming and managed.get('client') == client:
            if not skip_runtime:
                setup_runtime(target)
            return {'installed': str(target), 'client': client, 'changed': False,
                    'runtimePrepared': not skip_runtime, 'backup': None}
        staging = Path(tempfile.mkdtemp(prefix='.ppt-motion-stage-', dir=skills_dir))
        backup = None
        try:
            shutil.copytree(SOURCE, staging, dirs_exist_ok=True, ignore=ignored)
            copied = file_manifest(staging)
            if copied != incoming:
                raise RuntimeError('The source skill changed while copying; retry the installation.')
            (staging / MARKER).write_text(json.dumps({
                'schema': 1, 'managedBy': MANAGED_BY, 'client': client, 'files': copied,
            }, indent=2, sort_keys=True) + '\n', encoding='utf-8')
            if not skip_runtime:
                setup_runtime(staging)
            try:
                if exists:
                    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
                    suffix = f'{stamp}-{uuid.uuid4().hex[:8]}'
                    if target.is_symlink():
                        # Relative links must keep their original parent directory.
                        backup = skills_dir / f'.ppt-motion-backup-{suffix}'
                    else:
                        backup_root = skills_dir / '.ppt-motion-backups'
                        backup_root.mkdir(exist_ok=True)
                        backup = backup_root / f'ppt-motion-{suffix}'
                    target.rename(backup)
                staging.rename(target)
            except BaseException:
                # Restore after cancellation too, including an interrupt just
                # after the old installation has moved out of the way.
                if (backup is not None and (backup.exists() or backup.is_symlink())
                        and not (target.exists() or target.is_symlink())):
                    backup.rename(target)
                raise
        finally:
            if staging.exists():
                shutil.rmtree(staging)
        return {'installed': str(target), 'client': client, 'changed': True,
                'runtimePrepared': not skip_runtime, 'backup': str(backup) if backup else None}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--client', choices=['codex', 'claude-code'], required=True)
    parser.add_argument('--skills-dir', type=Path, help='Parent directory for the installed ppt-motion folder')
    parser.add_argument('--skip-runtime', action='store_true', help='Copy skill files now; prepare dependencies on first use')
    parser.add_argument('--force', action='store_true', help='Back up and replace an unmanaged or modified installation')
    args = parser.parse_args(argv)
    try:
        result = install(args.client, args.skills_dir or default_skills_dir(args.client),
                         force=args.force, skip_runtime=args.skip_runtime)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except KeyboardInterrupt:
        return 130
    except (OSError, RuntimeError) as exc:
        print(f'ppt-motion installer: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
