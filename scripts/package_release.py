#!/usr/bin/env python3
"""Build deterministic, allowlisted client ZIPs; no source decks are bundled.

Run from any directory: python3 scripts/package_release.py [--out DIRECTORY].
Only the files named below are read. Adding a new engine module or asset requires
an explicit release-list change; a stray local file is never swept into a ZIP.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path, PurePosixPath
import stat
import tempfile
import zipfile

PROJECT = Path(__file__).resolve().parents[1]
RELEASE_VERSION = "0.4.0"
ARCHIVE_ROOT = "ppt-motion"
FIXED_TIME = (2020, 1, 1, 0, 0, 0)

# Keep explicit filenames: globs and recursive directory copies can publish data.
SKILL_FILES = (
    "SKILL.md",
    "agents/openai.yaml",
    "assets/index.html",
    "assets/viewer.css",
    "assets/viewer.js",
    "references/configuration.md",
    "references/motion-language.md",
    "references/object-workflow.md",
    "scripts/motion_plan.py",
    "scripts/ppt_motion.py",
    "scripts/pptx_inventory.py",
    "scripts/requirements.txt",
    "scripts/run.py",
    "scripts/svg_geometry.py",
)
COMMON_FILES = (
    "README.md",
    "CONTRACT.md",
    "QA.md",
    "install.py",
    "ppt-motion",
    "examples/make_generic_demo.py",
)
OPTIONAL_NOTICE_FILES = ("LICENSE", "NOTICE", "THIRD_PARTY_NOTICES.md", "VERSION")
CLAUDE_FILES = (".claude-plugin/plugin.json", ".claude-plugin/marketplace.json")
ARCHIVES = (
    "ppt-motion-codex.zip",
    "ppt-motion-claude-code.zip",
    "ppt-motion-claude-desktop.zip",
)
FORBIDDEN_PARTS = frozenset({
    ".git", ".env", ".venv", "venv", "__pycache__", "qa", "jobs", "dist",
    ".cache", "runtime", "node_modules", "nps-demo",
})
FORBIDDEN_SUFFIXES = frozenset({".pdf", ".pptx", ".ppt", ".pyc", ".pyo", ".pem", ".key"})


def read_allowed(root: Path, relative: str) -> bytes:
    """Reject path traversal and every symlink, including a symlinked ancestor."""
    path = PurePosixPath(relative)
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise ValueError(f"Unsafe release path: {relative}")
    if any(part in FORBIDDEN_PARTS or part.startswith(".env.") for part in path.parts):
        raise ValueError(f"Private/runtime path is not distributable: {relative}")
    if path.suffix.lower() in FORBIDDEN_SUFFIXES:
        raise ValueError(f"Source decks and generated files are not distributable: {relative}")
    current = root
    for part in path.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"Release input must not be a symlink: {relative}")
    if not current.is_file():
        raise ValueError(f"Required release input is missing: {relative}")
    return current.read_bytes()


def release_entries(root: Path) -> dict[str, dict[str, bytes]]:
    """Map each archive to its complete, reviewed payload before writing any ZIP."""
    skill = {name: read_allowed(root, f"skill/ppt-motion/{name}") for name in SKILL_FILES}
    engine = ast.parse(skill["scripts/ppt_motion.py"].decode("utf-8"))
    versions = [node.value.value for node in engine.body
                if isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == "VERSION" for target in node.targets)
                and isinstance(node.value, ast.Constant)]
    if versions != [RELEASE_VERSION]:
        raise ValueError("Engine VERSION must match the release builder")
    common = {name: read_allowed(root, name) for name in COMMON_FILES}
    notices = {name: read_allowed(root, name) for name in OPTIONAL_NOTICE_FILES if (root / name).exists()}
    manifests = {name: read_allowed(root, name) for name in CLAUDE_FILES}
    plugin = json.loads(manifests[".claude-plugin/plugin.json"])
    marketplace = json.loads(manifests[".claude-plugin/marketplace.json"])
    if plugin.get("name") != "ppt-motion" or plugin.get("version") != RELEASE_VERSION:
        raise ValueError("Plugin name/version must match the release builder")
    if plugin.get("skills") != "./skill/":
        raise ValueError("Plugin must use the bundled canonical ./skill/ directory")
    entries = marketplace.get("plugins", [])
    if (marketplace.get("name") != "ppt-motion" or len(entries) != 1
            or entries[0].get("name") != "ppt-motion" or entries[0].get("source") != "./"
            or entries[0].get("version") != RELEASE_VERSION
            or marketplace.get("metadata", {}).get("version") != RELEASE_VERSION):
        raise ValueError("Marketplace must target this release at the repository root")
    if "VERSION" in notices and notices["VERSION"].decode("utf-8").strip() != RELEASE_VERSION:
        raise ValueError("VERSION must match the release builder")

    repo = {**common, **notices, **{f"skill/ppt-motion/{name}": data for name, data in skill.items()}}
    desktop = {**skill, **notices}
    desktop["SKILL.md"] = read_allowed(root, "clients/claude-desktop/SKILL.md")
    payloads = {
        ARCHIVES[0]: repo,
        ARCHIVES[1]: {**repo, **manifests},
        ARCHIVES[2]: desktop,
    }
    return {archive: {f"{ARCHIVE_ROOT}/{name}": data for name, data in files.items()}
            for archive, files in payloads.items()}


def write_zip(destination: Path, entries: dict[str, bytes]) -> None:
    # ZIP_STORED also makes the bytes independent of zlib implementation/version.
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, data in sorted(entries.items()):
            info = zipfile.ZipInfo(name, date_time=FIXED_TIME)
            info.create_system = 3
            info.compress_type = zipfile.ZIP_STORED
            mode = 0o755 if name.endswith(".py") or name == f"{ARCHIVE_ROOT}/ppt-motion" else 0o644
            info.external_attr = (stat.S_IFREG | mode) << 16
            archive.writestr(info, data)


def build_release(root: Path = PROJECT, out: Path | None = None) -> dict[str, str]:
    root = Path(root).resolve()
    out = Path(out) if out is not None else root / "dist/releases"
    payloads = release_entries(root)
    out.mkdir(parents=True, exist_ok=True)
    checksums: dict[str, str] = {}
    # Build everything in a staging directory first, avoiding half-written ZIPs.
    with tempfile.TemporaryDirectory(prefix=".ppt-motion-release-", dir=out) as staging:
        stage = Path(staging)
        for name, entries in payloads.items():
            write_zip(stage / name, entries)
            checksums[name] = hashlib.sha256((stage / name).read_bytes()).hexdigest()
        (stage / "SHA256SUMS").write_text(
            "".join(f"{checksums[name]}  {name}\n" for name in sorted(checksums)),
            encoding="utf-8", newline="\n")
        for name in (*ARCHIVES, "SHA256SUMS"):
            (stage / name).replace(out / name)
    return checksums


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=PROJECT / "dist/releases",
                        help="Destination directory (default: dist/releases)")
    args = parser.parse_args(argv)
    try:
        checksums = build_release(out=args.out)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.exit(2, f"Release packaging failed: {exc}\n")
    print(json.dumps({"version": RELEASE_VERSION, "output": str(args.out.resolve()),
                      "sha256": checksums}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
