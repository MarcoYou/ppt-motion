"""Release artifacts are reproducible, installable, and contain only public inputs."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

PROJECT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("package_release", PROJECT / "scripts/package_release.py")
packager = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(packager)


class ReleasePackageTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ppt motion packages ")
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.out = self.work / "releases"
        packager.build_release(PROJECT, self.out)

    def payload(self, name):
        with zipfile.ZipFile(self.out / name) as archive:
            return {path: archive.read(path) for path in archive.namelist()}

    def test_all_clients_have_complete_engine_and_distinct_install_layouts(self):
        codex = self.payload("ppt-motion-codex.zip")
        code = self.payload("ppt-motion-claude-code.zip")
        desktop = self.payload("ppt-motion-claude-desktop.zip")
        for relative in packager.SKILL_FILES:
            canonical = (PROJECT / "skill/ppt-motion" / relative).read_bytes()
            self.assertEqual(codex[f"ppt-motion/skill/ppt-motion/{relative}"], canonical)
            self.assertEqual(code[f"ppt-motion/skill/ppt-motion/{relative}"], canonical)
            if relative != "SKILL.md":
                self.assertEqual(desktop[f"ppt-motion/{relative}"], canonical)
        self.assertEqual(desktop["ppt-motion/SKILL.md"],
                         (PROJECT / "clients/claude-desktop/SKILL.md").read_bytes())
        self.assertNotEqual(desktop["ppt-motion/SKILL.md"], codex["ppt-motion/skill/ppt-motion/SKILL.md"])
        frontmatter = desktop["ppt-motion/SKILL.md"].decode("utf-8").split("---", 2)[1]
        metadata = dict(line.split(": ", 1) for line in frontmatter.strip().splitlines())
        self.assertEqual(metadata["name"], "ppt-motion")
        self.assertLessEqual(len(metadata["description"]), 200)
        for payload in (codex, code):
            self.assertIn("ppt-motion/install.py", payload)
            self.assertIn("ppt-motion/examples/make_generic_demo.py", payload)
        self.assertNotIn("ppt-motion/install.py", desktop)
        self.assertNotIn("ppt-motion/.claude-plugin/plugin.json", desktop)
        self.assertNotIn("ppt-motion/.claude-plugin/plugin.json", codex)
        manifest = json.loads(code["ppt-motion/.claude-plugin/plugin.json"])
        market = json.loads(code["ppt-motion/.claude-plugin/marketplace.json"])
        self.assertEqual(manifest["version"], "0.4.0")
        skill_dir = PurePosixPath("ppt-motion") / manifest["skills"]
        self.assertIn(str(skill_dir / "ppt-motion/SKILL.md"), code)
        self.assertEqual((market["name"], market["plugins"][0]["name"]), ("ppt-motion", "ppt-motion"))
        self.assertEqual(market["plugins"][0]["source"], "./")

    def test_extracted_local_client_packages_install_without_repository(self):
        for client in ("codex", "claude-code"):
            with self.subTest(client=client):
                unpacked = self.work / client
                with zipfile.ZipFile(self.out / f"ppt-motion-{client}.zip") as archive:
                    archive.extractall(unpacked)
                root = unpacked / "ppt-motion"
                target = self.work / f"{client} skills"
                completed = subprocess.run([
                    sys.executable, str(root / "install.py"), "--client", client,
                    "--skills-dir", str(target), "--skip-runtime",
                ], cwd=self.work, capture_output=True, text=True, encoding="utf-8")
                self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
                self.assertTrue((target / "ppt-motion/SKILL.md").is_file())
                for relative in packager.SKILL_FILES:
                    self.assertEqual((target / "ppt-motion" / relative).read_bytes(),
                                     (PROJECT / "skill/ppt-motion" / relative).read_bytes())
                help_result = subprocess.run([
                    sys.executable, str(target / "ppt-motion/scripts/run.py"), "--help",
                ], cwd=self.work, capture_output=True, text=True, encoding="utf-8")
                self.assertEqual(help_result.returncode, 0, help_result.stderr)
                self.assertIn("init", help_result.stdout)

    def test_desktop_script_runs_outside_repository_without_bootstrap_for_help(self):
        with zipfile.ZipFile(self.out / "ppt-motion-claude-desktop.zip") as archive:
            archive.extractall(self.work / "desktop")
        result = subprocess.run([
            sys.executable, str(self.work / "desktop/ppt-motion/scripts/run.py"), "--help",
        ], cwd=self.work, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("export-html", result.stdout)

    def test_archive_paths_and_checksums_are_safe_and_deterministic(self):
        before = {path.name: path.read_bytes() for path in self.out.iterdir()}
        second = self.work / "second"
        packager.build_release(PROJECT, second)
        self.assertEqual(before, {path.name: path.read_bytes() for path in second.iterdir()})
        expected_sums = []
        for name in sorted(packager.ARCHIVES):
            expected_sums.append(f"{hashlib.sha256(before[name]).hexdigest()}  {name}\n")
            with zipfile.ZipFile(self.out / name) as archive:
                self.assertEqual(archive.namelist(), sorted(archive.namelist()))
                self.assertEqual(len(archive.namelist()), len(set(archive.namelist())))
                for info in archive.infolist():
                    path = PurePosixPath(info.filename)
                    self.assertEqual(path.parts[0], "ppt-motion")
                    self.assertNotIn("..", path.parts)
                    self.assertFalse(path.is_absolute())
                    self.assertEqual(info.date_time, packager.FIXED_TIME)
                    self.assertTrue(set(path.parts).isdisjoint(packager.FORBIDDEN_PARTS))
                    self.assertNotIn(path.suffix.lower(), packager.FORBIDDEN_SUFFIXES)
                    self.assertNotIn(".env", info.filename)
                    self.assertNotIn(b"PRIVATE_RELEASE_CANARY", archive.read(info))
        self.assertEqual(before["SHA256SUMS"].decode("utf-8"), "".join(expected_sums))

    def fixture_repo(self):
        root = self.work / "fixture"
        paths = [*packager.COMMON_FILES, *packager.CLAUDE_FILES,
                 "clients/claude-desktop/SKILL.md",
                 *(f"skill/ppt-motion/{name}" for name in packager.SKILL_FILES),
                 *(name for name in packager.OPTIONAL_NOTICE_FILES if (PROJECT / name).exists())]
        for relative in paths:
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(PROJECT / relative, path)
        return root

    def test_unlisted_private_files_cannot_enter_any_archive(self):
        root = self.fixture_repo()
        for relative in (
            ".env", ".git/config", "qa/private-notes.txt", "private.pdf", "private.pptx",
            "examples/configure_nps.py", "examples/nps-demo/deck.json",
            "skill/ppt-motion/scripts/secret.py", "skill/ppt-motion/references/private.md",
            "skill/ppt-motion/assets/private.svg", "skill/ppt-motion/.venv/credentials.txt",
            "dist/releases/old.zip", "runtime/cache.txt",
        ):
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"PRIVATE_RELEASE_CANARY")
        # Different filesystem dates and modes cannot affect release bytes.
        for path in root.rglob("*"):
            if path.is_file():
                os.utime(path, (1000000000, 1000000000))
                path.chmod(0o600)
        output = self.work / "with-private-files"
        packager.build_release(root, output)
        for original in self.out.iterdir():
            self.assertEqual(original.read_bytes(), (output / original.name).read_bytes())

    def test_symlink_or_missing_required_input_fails_before_output(self):
        root = self.fixture_repo()
        target = root / "skill/ppt-motion/assets/viewer.js"
        target.unlink()
        with self.assertRaisesRegex(ValueError, "Required release input is missing"):
            packager.build_release(root, self.work / "missing")
        self.assertFalse((self.work / "missing").exists())
        target.symlink_to(PROJECT / "skill/ppt-motion/assets/viewer.js")
        with self.assertRaisesRegex(ValueError, "must not be a symlink"):
            packager.build_release(root, self.work / "symlink")
        self.assertFalse((self.work / "symlink").exists())

    def test_engine_version_drift_fails_before_packaging(self):
        root = self.fixture_repo()
        engine = root / "skill/ppt-motion/scripts/ppt_motion.py"
        engine.write_text(engine.read_text(encoding="utf-8") + "\nVERSION = '0.0.0'\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Engine VERSION must match"):
            packager.build_release(root, self.work / "version-drift")
        self.assertFalse((self.work / "version-drift").exists())


if __name__ == "__main__":
    unittest.main()
