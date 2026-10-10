import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import tempfile
import unittest


PROJECT = Path(__file__).resolve().parents[1]
CLI = PROJECT / "shebanglf.py"


class CliTests(unittest.TestCase):
    def setUp(self):
        scratch = PROJECT / ".test-tmp"
        scratch.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name) / "repo"
        self.repo.mkdir()
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        self.env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
                        GIT_TERMINAL_PROMPT="0", PYTHONDONTWRITEBYTECODE="1")
        self.git("init", "-q", "--template=")

    def git(self, *args, **kwargs):
        return subprocess.run(
            ["git", "-c", "core.autocrlf=false", *args], cwd=self.repo,
            env=self.env, capture_output=True, check=True, **kwargs,
        )

    def put(self, name, content, *, tracked=True, mode=0o644):
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        path.chmod(mode)
        if tracked:
            self.git("add", "--", name)
        return path

    def cli(self, *args, env=None, cwd=None, **process_options):
        return subprocess.run(
            [sys.executable, "-B", str(CLI), *args],
            cwd=cwd or self.repo, env=env or self.env,
            capture_output=True, text=True, timeout=10,
            **process_options,
        )

    def test_check_reports_crlf_without_writing(self):
        original = b"#!/bin/sh\r\necho hello\r\n"
        script = self.put("bootstrap", original)
        self.put("README.txt", b"keep Windows text\r\n")
        result = self.cli()
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn('CRLF "bootstrap": 2', result.stdout)
        self.assertNotIn("README.txt", result.stdout)
        self.assertEqual(script.read_bytes(), original)

    def test_fix_makes_extensionless_script_executable_without_staging(self):
        original = b"#!/bin/sh\r\nif true; then\r\n  echo hello\r\nfi\r\n"
        script = self.put("bootstrap", original, mode=0o751)
        with self.assertRaises(OSError):
            subprocess.run([str(script)], capture_output=True, timeout=5)
        index_before = self.git("ls-files", "--stage").stdout
        result = self.cli("--fix")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('FIXED "bootstrap": 4', result.stdout)
        self.assertEqual(script.read_bytes(), b"#!/bin/sh\nif true; then\n  echo hello\nfi\n")
        self.assertEqual(script.stat().st_mode & 0o777, 0o751)
        self.assertEqual(self.git("ls-files", "--stage").stdout, index_before)
        run = subprocess.run([str(script)], capture_output=True, timeout=5)
        self.assertEqual((run.returncode, run.stdout), (0, b"hello\n"))

    def test_clean_run_leaves_files_untouched_and_reports_scope(self):
        files = [
            self.put("ready", b"#!/usr/bin/env python3\nprint('ok')"),
            self.put("windows.bat", b"@echo off\r\necho hello\r\n"),
            self.put("empty", b""),
            self.put("untracked", b"#!/bin/sh\r\nexit 0\r\n", tracked=False),
        ]
        before = [(p.read_bytes(), p.stat().st_ino, p.stat().st_mtime_ns) for p in files]
        for _ in range(2):
            result = self.cli("--fix")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), "scripts=1 affected=0 fixed=0 skipped=0 errors=0")
        self.assertEqual([(p.read_bytes(), p.stat().st_ino, p.stat().st_mtime_ns) for p in files], before)

    def test_running_from_subdirectory_checks_the_repository_root(self):
        self.put("bootstrap", b"#!/bin/sh\r\nexit 0\r\n")
        self.put("scripts/clean", b"#!/bin/sh\nexit 0\n")
        result = self.cli(cwd=self.repo / "scripts")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn('CRLF "bootstrap"', result.stdout)
        self.assertIn("scripts=2 affected=1", result.stdout)

    def test_non_repository_returns_actionable_error(self):
        # A .git file blocks Git's upward discovery into this tool's own repository.
        outside = Path(self.temp.name) / "not-a-repo"
        outside.mkdir()
        (outside / ".git").write_text("gitdir: missing\n")
        result = self.cli(str(outside))
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("ERROR", result.stderr)
        self.assertIn("Git", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_missing_git_returns_actionable_error(self):
        result = self.cli(env={**self.env, "PATH": ""})
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("Git", result.stderr)
        self.assertIn("ERROR", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_inherited_git_overrides_cannot_redirect_repository(self):
        self.put("bootstrap", b"#!/bin/sh\r\nexit 0\r\n")
        overrides = {**self.env, "GIT_DIR": str(self.repo / "missing"),
                     "GIT_WORK_TREE": str(self.temp.name),
                     "GIT_INDEX_FILE": str(self.repo / "wrong-index")}
        result = self.cli(str(self.repo), env=overrides)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn('CRLF "bootstrap"', result.stdout)
        self.assertFalse((self.repo / "wrong-index").exists())

    def test_tracked_symlink_is_skipped_without_touching_target(self):
        original = b"#!/bin/sh\r\necho untouched\r\n"
        target = Path(self.temp.name) / "target"
        target.write_bytes(original)
        (self.repo / "link").symlink_to(target)
        self.git("add", "--", "link")
        result = self.cli("--fix")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('SKIP "link": symlink', result.stdout)
        self.assertIn("skipped=1", result.stdout)
        self.assertEqual(target.read_bytes(), original)
        self.assertTrue((self.repo / "link").is_symlink())

    def test_missing_unreadable_and_nonregular_entries_report_errors_and_continue(self):
        original = b"#!/bin/sh\r\nexit 0\r\n"
        missing = self.put("a-missing", original)
        missing.unlink()
        unreadable = self.put("b-unreadable", original)
        unreadable.chmod(0)
        self.addCleanup(unreadable.chmod, 0o644)
        directory = self.put("c-directory", original)
        directory.unlink()
        directory.mkdir()
        fifo = self.put("d-fifo", original)
        fifo.unlink()
        os.mkfifo(fifo)
        valid = self.put("z-valid", original)
        result = self.cli("--fix")
        self.assertEqual(result.returncode, 2, result.stderr)
        for name in ("a-missing", "b-unreadable", "c-directory", "d-fifo"):
            self.assertIn('ERROR "' + name + '"', result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertIn("errors=4", result.stdout)
        self.assertEqual(valid.read_bytes(), b"#!/bin/sh\nexit 0\n")

    def test_submodule_is_skipped_without_reading_its_files(self):
        original = b"#!/bin/sh\r\necho untouched\r\n"
        child = self.put("vendor/bootstrap", original, tracked=False)
        self.git("update-index", "--add", "--cacheinfo", "160000," + "1" * 40 + ",vendor")
        result = self.cli("--fix")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('SKIP "vendor": submodule', result.stdout)
        self.assertIn("scripts=0", result.stdout)
        self.assertEqual(child.read_bytes(), original)

    def test_working_tree_symlinks_in_any_path_component_are_refused(self):
        original = b"#!/bin/sh\r\necho untouched\r\n"
        outside = Path(self.temp.name) / "outside"
        outside.mkdir()
        target = outside / "run"
        target.write_bytes(original)
        direct = self.put("direct", original)
        direct.unlink()
        direct.symlink_to(target)
        nested = self.put("nested/run", original)
        nested.unlink()
        nested.parent.rmdir()
        nested.parent.symlink_to(outside, target_is_directory=True)
        result = self.cli("--fix")
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn('ERROR "direct": symlink', result.stderr)
        self.assertIn('ERROR "nested/run": symlink', result.stderr)
        self.assertEqual(target.read_bytes(), original)

    def test_nontext_shebang_files_are_refused_without_conversion(self):
        fixtures = {
            "nul": b"#!/bin/sh\r\n\x00payload\r\n",
            "control": b"#!/bin/sh\r\n\x01payload\r\n",
            "non-utf8": b"#!/bin/sh\r\necho \xff\r\n",
        }
        for name, content in fixtures.items():
            self.put(name, content)
        for args in ((), ("--fix",)):
            result = self.cli(*args)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn("errors=3", result.stdout)
            for name, content in fixtures.items():
                self.assertIn('ERROR "' + name + '"', result.stderr)
                self.assertEqual((self.repo / name).read_bytes(), content)

    def test_unusual_filename_and_mixed_endings_are_handled_byte_faithfully(self):
        name = "-run $(touch SHOULD_NOT_EXIST)\n\t" + os.fsdecode(b"\xff")
        original = "#!/bin/sh\r\n# café\n# literal\rcarriage\r\necho done".encode()
        expected = "#!/bin/sh\n# café\n# literal\rcarriage\necho done".encode()
        script = self.put(name, original)
        result = self.cli("--fix")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("FIXED " + json.dumps(name) + ": 2", result.stdout)
        self.assertEqual(len(result.stdout.splitlines()), 2)
        self.assertEqual(script.read_bytes(), expected)
        self.assertFalse((self.repo / "SHOULD_NOT_EXIST").exists())
        before = (script.stat().st_ino, script.stat().st_mtime_ns)
        again = self.cli("--fix")
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertEqual((script.stat().st_ino, script.stat().st_mtime_ns), before)

    def test_fix_refuses_hard_links(self):
        original = b"#!/bin/sh\r\nexit 0\r\n"
        script = self.put("run", original)
        alias = Path(self.temp.name) / "alias"
        os.link(script, alias)
        result = self.cli("--fix")
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn('ERROR "run": hard-linked', result.stderr)
        self.assertEqual(script.read_bytes(), original)
        self.assertEqual(alias.read_bytes(), original)
        self.assertEqual(script.stat().st_ino, alias.stat().st_ino)

    def test_unmerged_index_entry_is_reported_once_and_not_modified(self):
        original = b"#!/bin/sh\r\nexit 0\r\n"
        script = self.put("run", original)
        oid = self.git("rev-parse", ":run").stdout.strip()
        self.git("update-index", "--force-remove", "run")
        entries = b"".join(b"100644 " + oid + b" " + stage + b"\trun\n" for stage in (b"1", b"2", b"3"))
        self.git("update-index", "--index-info", input=entries)
        result = self.cli("--fix")
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(result.stderr.count('ERROR "run": unmerged'), 1)
        self.assertIn("errors=1", result.stdout)
        self.assertEqual(script.read_bytes(), original)

    def test_interrupted_write_keeps_original_and_cleans_temporary_files(self):
        original = b"#!/bin/sh\r\n" + b"# some data\r\n" * 100
        script = self.put("run", original, mode=0o750)
        before = set(self.repo.iterdir())

        def limit_file_size():
            resource.setrlimit(resource.RLIMIT_FSIZE, (128, 128))

        result = self.cli("--fix", preexec_fn=limit_file_size)
        self.assertEqual(script.read_bytes(), original)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn('ERROR "run"', result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertEqual(set(self.repo.iterdir()), before)
        self.assertEqual(script.stat().st_mode & 0o777, 0o750)

    def test_readonly_files_and_directories_leave_originals_untouched(self):
        original = b"#!/bin/sh\r\nexit 0\r\n"
        readonly = self.put("readonly", original, mode=0o444)
        blocked = self.put("locked/run", original)
        blocked.parent.chmod(0o555)
        self.addCleanup(blocked.parent.chmod, 0o755)
        result = self.cli("--fix")
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn('ERROR "readonly"', result.stderr)
        self.assertIn('ERROR "locked/run"', result.stderr)
        self.assertIn("errors=2", result.stdout)
        self.assertEqual(readonly.read_bytes(), original)
        self.assertEqual(blocked.read_bytes(), original)
        self.assertEqual(list(blocked.parent.iterdir()), [blocked])
