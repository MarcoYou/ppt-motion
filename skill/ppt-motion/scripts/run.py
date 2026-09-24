#!/usr/bin/env python3
"""Run ppt-motion with its own cached, pinned Python environment."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
REQUIREMENTS = SCRIPTS / 'requirements.txt'
ENGINE = SCRIPTS / 'ppt_motion.py'
READY_FILE = '.ppt-motion-runtime.json'
RUNTIME_SCHEMA = 1


class FileLock:
    """An OS-owned lock, released even if the installing process crashes."""

    def __init__(self, path: Path, timeout: float = 900):
        self.path, self.timeout, self.file = path, timeout, None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.file = self.path.open('a+b')
        if os.name == 'nt':
            import msvcrt
            self.file.seek(0, os.SEEK_END)
            if not self.file.tell():
                self.file.write(b'0')
                self.file.flush()
            def lock():
                self.file.seek(0)
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            def lock():
                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                lock()
                return self
            except OSError:
                if time.monotonic() >= deadline:
                    self.file.close()
                    raise RuntimeError(f'Timed out waiting for {self.path}. Another setup may still be running.')
                time.sleep(0.1)

    def __exit__(self, *exc):
        try:
            if os.name == 'nt':
                import msvcrt
                self.file.seek(0)
                msvcrt.locking(self.file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(), fcntl.LOCK_UN)
        finally:
            self.file.close()


def runtime_root() -> Path:
    if os.environ.get('PPT_MOTION_RUNTIME_ROOT'):
        return Path(os.environ['PPT_MOTION_RUNTIME_ROOT']).expanduser().resolve()
    if os.name == 'nt':
        base = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local'))
    elif sys.platform == 'darwin':
        base = Path.home() / 'Library' / 'Caches'
    else:
        base = Path(os.environ.get('XDG_CACHE_HOME', Path.home() / '.cache'))
    return base.expanduser().resolve() / 'ppt-motion'


def pinned_requirements(path: Path = REQUIREMENTS) -> dict[str, str]:
    pins = {}
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.partition('#')[0].strip()
        if not line:
            continue
        match = re.fullmatch(r'([A-Za-z0-9][A-Za-z0-9_.-]*)==([A-Za-z0-9][A-Za-z0-9_.+!-]*)', line)
        if not match:
            raise RuntimeError(f'Expected an exact package==version pin in {path}: {line}')
        if match[1].lower() in {name.lower() for name in pins}:
            raise RuntimeError(f'Duplicate dependency pin: {match[1]}')
        pins[match[1]] = match[2]
    if not pins:
        raise RuntimeError(f'No pinned dependencies found in {path}')
    return pins


def runtime_identity(requirements: Path = REQUIREMENTS) -> dict:
    return {
        'schema': RUNTIME_SCHEMA,
        'requirementsSha256': hashlib.sha256(requirements.read_bytes()).hexdigest(),
        'python': platform.python_version(),
        'implementation': sys.implementation.name,
        'cacheTag': sys.implementation.cache_tag,
        'interpreter': str(Path(getattr(sys, '_base_executable', sys.executable)).resolve()),
        'platform': sys.platform,
        'machine': platform.machine(),
    }


def runtime_path(identity: dict, root: Path | None = None) -> Path:
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:24]
    return (root if root is not None else runtime_root()) / 'venvs' / f'py{identity["python"]}-{key}'


def python_path(runtime: Path) -> Path:
    return runtime / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')


def clean_environment() -> dict[str, str]:
    # Keep explicit network/offline settings, but never allow pip target/prefix
    # settings or Python import paths to escape the managed environment.
    pip_settings = {
        'PIP_INDEX_URL', 'PIP_EXTRA_INDEX_URL', 'PIP_FIND_LINKS', 'PIP_NO_INDEX',
        'PIP_TRUSTED_HOST', 'PIP_CERT', 'PIP_CLIENT_CERT', 'PIP_CACHE_DIR',
        'PIP_PROXY', 'PIP_TIMEOUT', 'PIP_RETRIES',
    }
    env = {key: value for key, value in os.environ.items()
           if not key.startswith('PYTHON') and (not key.startswith('PIP_') or key in pip_settings)}
    env['PIP_CONFIG_FILE'] = os.devnull
    env['PIP_DISABLE_PIP_VERSION_CHECK'] = '1'
    return env


def probe_runtime(runtime: Path, pins: dict[str, str]) -> bool:
    interpreter = python_path(runtime)
    if not interpreter.is_file():
        return False
    probe = ('import importlib.metadata, json; import fitz; import lxml.etree; '
             f'pins = {pins!r}; '
             'assert all(importlib.metadata.version(k) == v for k, v in pins.items())')
    try:
        result = subprocess.run([str(interpreter), '-I', '-B', '-c', probe],
                                capture_output=True, env=clean_environment(), timeout=30)
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def runtime_ready(runtime: Path, identity: dict, pins: dict[str, str]) -> bool:
    if runtime.is_symlink():
        return False
    try:
        marker = json.loads((runtime / READY_FILE).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return False
    return marker == identity and probe_runtime(runtime, pins)


def ensure_runtime(requirements: Path = REQUIREMENTS, root: Path | None = None) -> tuple[Path, bool]:
    if sys.version_info < (3, 11):
        raise RuntimeError('Python 3.11 or newer is required.')
    pins, identity = pinned_requirements(requirements), runtime_identity(requirements)
    runtime = runtime_path(identity, root)
    with FileLock(runtime.parent / f'.{runtime.name}.lock'):
        if runtime_ready(runtime, identity, pins):
            return runtime, True
        if runtime.is_symlink():
            raise RuntimeError(f'Refusing to replace a symlink at runtime path: {runtime}')
        if runtime.exists():
            if not runtime.is_dir():
                raise RuntimeError(f'Runtime path is not a directory: {runtime}')
            shutil.rmtree(runtime)
        print(f'ppt-motion: preparing isolated runtime at {runtime}', file=sys.stderr, flush=True)
        try:
            subprocess.run([identity['interpreter'], '-I', '-m', 'venv', str(runtime)],
                           check=True, stdout=sys.stderr, stderr=sys.stderr,
                           env=clean_environment(), timeout=120)
            subprocess.run([str(python_path(runtime)), '-I', '-m', 'pip', 'install',
                            '--disable-pip-version-check', '--no-input', '--only-binary=:all:',
                            '--requirement', str(requirements)],
                           check=True, stdout=sys.stderr, stderr=sys.stderr,
                           env=clean_environment(), timeout=600)
            if not probe_runtime(runtime, pins):
                raise RuntimeError('The installed runtime did not pass its import/version check.')
            # Create directly at its permanent path: venv entry points embed it.
            (runtime / READY_FILE).write_text(json.dumps(identity, indent=2) + '\n', encoding='utf-8')
        except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
            (runtime / READY_FILE).unlink(missing_ok=True)
            raise RuntimeError(
                'Runtime setup failed; no global Python packages were installed. '
                'Check the error above, available disk space, and network access, then retry --setup. '
                'On Linux, ensure the Python venv/ensurepip package is installed. '
                'For offline setup, provide compatible pinned wheels using '
                'PIP_NO_INDEX=1 and PIP_FIND_LINKS=/path/to/wheels. '
                f'Details: {exc}'
            ) from exc
    return runtime, False


def engine_version() -> str:
    for node in ast.parse(ENGINE.read_text(encoding='utf-8')).body:
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == 'VERSION' for target in node.targets):
            return str(ast.literal_eval(node.value))
    return 'unknown'


def wrapper_help() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog='Commands: init, doctor, export-pdf, plan, apply-plan, build, check, inspect, serve, export-html. '
               'Pass COMMAND --help for engine options (prepares the runtime on first use). '
               'Set PPT_MOTION_RUNTIME_ROOT to choose the cache directory. '
               'Offline setup supports PIP_NO_INDEX=1 and PIP_FIND_LINKS=/path/to/wheels.')
    parser.add_argument('--setup', action='store_true', help='Prepare or validate the isolated runtime, then exit')
    parser.add_argument('--version', action='store_true', help='Show the engine version without installing anything')
    parser.add_argument('command', nargs='?', help='Engine command; all remaining arguments are forwarded unchanged')
    parser.print_help()


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args in (['--help'], ['-h'], ['--setup', '--help'], ['--setup', '-h']):
        wrapper_help()
        return 0
    try:
        if args == ['--version']:
            print(engine_version())
            return 0
        if args[0] == '--setup' and args != ['--setup']:
            raise RuntimeError('--setup must be used on its own; run an engine command separately.')
        runtime, reused = ensure_runtime()
        if args == ['--setup']:
            print(json.dumps({'runtime': str(runtime), 'python': str(python_path(runtime)),
                              'ready': True, 'reused': reused}))
            return 0
        return subprocess.call([str(python_path(runtime)), '-E', '-s', '-B', str(ENGINE), *args],
                               env=clean_environment())
    except KeyboardInterrupt:
        return 130
    except (OSError, RuntimeError) as exc:
        print(f'ppt-motion: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
