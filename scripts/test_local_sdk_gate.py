#!/usr/bin/env python3
"""Positive and negative controls for the maintained SDK gate itself.

The package fixtures are test-only Python modules. They are not NCP runtime
qualification. Process controls start real owned children. The unavailable-wait
control injects only the parent's wait observation, then separately reaps its child.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import venv
import warnings
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "local_sdk_gate", ROOT / "scripts/check_local_sdk.py"
)
gate = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = gate
SPEC.loader.exec_module(gate)


class GateIntegrity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.owned = tempfile.TemporaryDirectory(prefix="ncp-sdk-gate-controls-")
        cls.root = Path(cls.owned.name)
        cls.installation = cls.root / "installed"
        venv.EnvBuilder(with_pip=False).create(cls.installation)
        cls.python = cls.installation / "bin/python"
        cls.environment = dict(gate.git_environment(), PYTHONDONTWRITEBYTECODE="1")
        cls.environment.pop("PYTHONPATH", None)
        # This interpreter belongs to the newly created fixture environment.
        purelib = subprocess.check_output(  # noqa: S603
            [
                str(cls.python),
                "-I",
                "-c",
                "import sysconfig; print(sysconfig.get_path('purelib'))",
            ],
            text=True,
            env=cls.environment,
            timeout=10,
        ).strip()
        cls.package = Path(purelib) / "ncp_local"
        cls.package.mkdir()
        cls.package_bytes = {
            "__init__.py": b"VALUE = 7\n",
            "modular_owner.py": b"def profile_digest():\n    return 'fixture-only'\n",
        }
        for name, body in cls.package_bytes.items():
            (cls.package / name).write_bytes(body)
        cls.expected = {
            name: hashlib.sha256(body).hexdigest()
            for name, body in cls.package_bytes.items()
        }
        cls.expected_file = cls.root / "expected.json"
        cls.expected_file.write_text(json.dumps(cls.expected))

    @classmethod
    def tearDownClass(cls):
        cls.owned.cleanup()

    def setUp(self):
        self.scratch = Path(tempfile.mkdtemp(prefix="case-", dir=self.root))

    def execute(self, program, *arguments):
        # Programs below are fixed test-only positive and negative controls.
        return subprocess.run(  # noqa: S603
            [str(self.python), "-I", "-c", program, *map(str, arguments)],
            cwd=self.scratch,
            env=self.environment,
            capture_output=True,
            timeout=10,
        )

    def make_wheel(self, bodies):
        path = self.scratch / "fixture.whl"
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(path, "w") as archive:
                for name, body in bodies:
                    archive.writestr(name, body)
        return path

    def wheel_source(self):
        return {
            "local/python/ncp_local/" + name: {"sha256": digest}
            for name, digest in self.expected.items()
        }

    def test_exact_wheel_entries_pass(self):
        wheel = self.make_wheel(
            [("ncp_local/" + name, body) for name, body in self.package_bytes.items()]
        )
        self.assertEqual(gate.wheel_contents(wheel, self.wheel_source()), self.expected)

    def test_changed_missing_extra_and_duplicate_wheel_entries_fail(self):
        normal = [
            ("ncp_local/" + name, body) for name, body in self.package_bytes.items()
        ]
        mutations = [
            normal[:-1],
            normal + [("ncp_local/extra.py", b"extra")],
            [(normal[0][0], b"changed"), *normal[1:]],
            normal + [normal[0]],
        ]
        for rows in mutations:
            with self.subTest(rows=rows), self.assertRaises(RuntimeError):
                gate.wheel_contents(self.make_wheel(rows), self.wheel_source())

    def test_actual_installed_identity_passes(self):
        result = self.execute(
            gate.INSTALLED_PROGRAM, self.expected_file, self.installation
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["files"], self.expected)

    def test_changed_installed_bytes_fail(self):
        path = self.package / "__init__.py"
        try:
            path.write_bytes(b"VALUE = 8\n")
            result = self.execute(
                gate.INSTALLED_PROGRAM, self.expected_file, self.installation
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b"installed SDK bytes differ", result.stderr)
        finally:
            path.write_bytes(self.package_bytes["__init__.py"])

    def test_identical_source_package_cannot_replace_installation(self):
        source = self.scratch / "source"
        shutil.copytree(self.package, source / "ncp_local")
        prefix = "import sys; sys.path.insert(0, " + repr(str(source)) + ")\n"
        result = self.execute(
            prefix + gate.INSTALLED_PROGRAM, self.expected_file, self.installation
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"escaped fresh installation", result.stderr)

    def make_suite(self, source):
        suite = self.scratch / "suite"
        suite.mkdir()
        if source is not None:
            (suite / "test_control.py").write_text(source)
        return suite

    def test_nonempty_successful_suite_passes(self):
        suite = self.make_suite(
            "import unittest\nclass Check(unittest.TestCase):\n"
            " def test_control(self): self.assertEqual(2+2,4)\n"
        )
        result = self.execute(gate.SUITE_PROGRAM, suite, self.installation)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_empty_suite_fails(self):
        result = self.execute(
            gate.SUITE_PROGRAM, self.make_suite(None), self.installation
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"empty SDK suite", result.stderr)

    def test_skipped_required_control_fails(self):
        suite = self.make_suite(
            "import unittest\nclass Check(unittest.TestCase):\n"
            " @unittest.skip('selected negative')\n def test_control(self): pass\n"
        )
        result = self.execute(gate.SUITE_PROGRAM, suite, self.installation)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"skipped=1", result.stderr)

    def test_late_foreign_sdk_module_fails(self):
        suite = self.make_suite(
            "import unittest,sys,types\nclass Check(unittest.TestCase):\n"
            " def test_control(self):\n"
            "  module=types.ModuleType('ncp_local.foreign')\n"
            "  module.__file__='/not-the-installed-package/foreign.py'\n"
            "  sys.modules['ncp_local.foreign']=module\n"
        )
        result = self.execute(gate.SUITE_PROGRAM, suite, self.installation)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"SDK module escaped installed package", result.stderr)

    def test_executable_probe_passes_and_missing_unexecutable_alias_fail(self):
        probe = self.scratch / "probe"
        body = b"#!/bin/sh\nexit 0\n"
        probe.write_bytes(body)
        probe.chmod(0o700)
        self.assertEqual(gate.require_probe(probe), hashlib.sha256(body).hexdigest())
        # The complete executable fixture bytes were written just above.
        subprocess.run([str(probe)], check=True, timeout=3)  # noqa: S603
        probe.chmod(0o600)
        with self.assertRaises(RuntimeError):
            gate.require_probe(probe)
        with self.assertRaises(FileNotFoundError):
            gate.require_probe(self.scratch / "missing")
        alias = self.scratch / "alias"
        alias.symlink_to(probe)
        with self.assertRaises(RuntimeError):
            gate.require_probe(alias)

    def repository(self):
        root = self.scratch / "repository"
        root.mkdir()
        environment = gate.git_environment()

        def git(*arguments):
            # Fixed local fixture operations, without hooks or a shell.
            return subprocess.check_output(  # noqa: S603
                [gate.git_executable(), "-c", "core.hooksPath=/dev/null", *arguments],
                cwd=root,
                env=environment,
                timeout=10,
            )

        git("init", "--quiet", "--template=")
        (root / "input.txt").write_bytes(b"source bytes\n")
        git("add", "input.txt")
        git(
            "-c",
            "user.name=Gate fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "--quiet",
            "--no-gpg-sign",
            "-m",
            "fixture",
        )
        return root, git("rev-parse", "HEAD").decode().strip()

    def test_actual_git_source_and_reference_positive_negative(self):
        root, revision = self.repository()
        rows = gate.source_rows(root)
        gate.source_unchanged(rows, root)
        gate.reference_parity(root, revision, ("input.txt",))
        target = root / "input.txt"
        target.write_bytes(b"changed source\n")
        with self.assertRaises(RuntimeError):
            gate.source_unchanged(rows, root)
        with self.assertRaises(RuntimeError):
            gate.reference_parity(root, revision, ("input.txt",))
        target.write_bytes(b"source bytes\n")
        target.chmod(0o700)
        with self.assertRaises(RuntimeError):
            gate.source_unchanged(rows, root)
        target.chmod(rows["input.txt"]["mode"])
        (root / "extra.txt").write_bytes(b"unreviewed membership")
        with self.assertRaises(RuntimeError):
            gate.source_unchanged(rows, root)
        (root / "extra.txt").unlink()
        gate.source_unchanged(rows, root)

    def test_actual_git_replacement_cannot_rewrite_historical_reference(self):
        root, revision = self.repository()
        environment = gate.git_environment()
        environment.pop("GIT_NO_REPLACE_OBJECTS")

        def git(*arguments):
            # The replacement exists only inside this newly created fixture repo.
            return (
                subprocess.check_output(  # noqa: S603
                    [gate.git_executable(), *arguments],
                    cwd=root,
                    env=environment,
                    timeout=10,
                )
                .decode()
                .strip()
            )

        gate.reference_parity(root, revision, ("input.txt",))
        original = git("hash-object", "input.txt")
        (root / "input.txt").write_bytes(b"replacement bytes\n")
        replacement = git("hash-object", "-w", "input.txt")
        git("replace", original, replacement)
        self.assertEqual(git("show", f"{revision}:input.txt"), "replacement bytes")
        with self.assertRaises(RuntimeError):
            gate.reference_parity(root, revision, ("input.txt",))
        (root / "input.txt").write_bytes(b"source bytes\n")
        gate.reference_parity(root, revision, ("input.txt",))

    def test_actual_git_environment_cannot_redirect_source_or_reference(self):
        root, revision = self.repository()
        (root / "extra.py").write_bytes(b"selected source\n")
        expected = gate.source_rows(root)
        foreign = self.scratch / "foreign"
        shutil.copytree(root, foreign)
        (foreign / "extra.py").unlink()
        with patch.dict(
            os.environ,
            GIT_DIR=str(foreign / ".git"),
            GIT_WORK_TREE=str(foreign),
            GIT_INDEX_FILE=str(self.scratch / "absent-index"),
            GIT_CONFIG_COUNT="1",
            GIT_CONFIG_KEY_0="core.bare",
            GIT_CONFIG_VALUE_0="true",
        ):
            self.assertEqual(gate.source_rows(root), expected)
            gate.reference_parity(root, revision, ("input.txt",))
            (root / "input.txt").write_bytes(b"changed selected source\n")
            with self.assertRaises(RuntimeError):
                gate.reference_parity(root, revision, ("input.txt",))

    def test_fixture_setup_cannot_mutate_an_inherited_foreign_repository(self):
        foreign, _revision = self.repository()
        script = ROOT / "scripts/test_local_sdk_gate.py"
        program = (
            "import importlib.util, pathlib, sys\n"
            "spec=importlib.util.spec_from_file_location('fixture',sys.argv[1])\n"
            "m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)\n"
            "m.GateIntegrity.setUpClass()\n"
            "try:\n"
            " case=m.GateIntegrity();case.setUp();root,revision=case.repository()\n"
            " assert root.is_relative_to(case.root)\n"
            " assert root != pathlib.Path(sys.argv[2])\n"
            "finally: m.GateIntegrity.tearDownClass()\n"
        )

        def identities():
            return {
                str(path.relative_to(foreign)): (
                    path.stat().st_mode,
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                )
                for path in foreign.rglob("*")
                if path.is_file()
            }

        before = identities()
        self.assertTrue({"input.txt", ".git/index", ".git/HEAD"}.issubset(before))
        ordinary = gate.git_environment()
        redirected = dict(
            ordinary,
            GIT_DIR=str(foreign / ".git"),
            GIT_WORK_TREE=str(foreign),
            GIT_INDEX_FILE=str(foreign / ".git/index"),
            GIT_CONFIG_COUNT="1",
            GIT_CONFIG_KEY_0="core.bare",
            GIT_CONFIG_VALUE_0="true",
            GIT_CONFIG_PARAMETERS="'core.bare'='true'",
        )
        for environment in (ordinary, redirected):
            # This fixed child constructs fixtures only in its new private root.
            result = subprocess.run(  # noqa: S603
                [self.python, "-I", "-c", program, script, foreign],
                cwd=self.scratch,
                env=environment,
                capture_output=True,
                timeout=20,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(identities(), before)

    def test_real_process_success_and_timeout_reap(self):
        with patch.object(gate, "DIAGNOSTICS", self.scratch):
            gate.run(
                [self.python, "-I", "-c", "print('actual positive child')"],
                environment=self.environment,
                timeout=3,
            )
            with self.assertRaises(subprocess.TimeoutExpired):
                gate.run(
                    [self.python, "-I", "-c", "import time; time.sleep(30)"],
                    environment=self.environment,
                    timeout=0.2,
                )
        rows = [json.loads(p.read_text()) for p in self.scratch.glob("command-*.json")]
        self.assertTrue(any(row["status"] == "PASS" for row in rows))
        failed = next(row for row in rows if row["status"] == "FAIL")
        self.assertTrue(failed["post_kill_reap_confirmed"])
        with self.assertRaises(ProcessLookupError):
            os.kill(failed["pid"], 0)

    def test_spawn_failure_is_recorded_without_claiming_a_child(self):
        with patch.object(gate, "DIAGNOSTICS", self.scratch):
            with self.assertRaises(FileNotFoundError):
                gate.run(
                    [self.scratch / "absent-executable"],
                    environment=self.environment,
                    timeout=1,
                )
        row = json.loads(next(self.scratch.glob("command-*.json")).read_text())
        self.assertFalse(row["process_started"])
        self.assertEqual(row["status"], "FAIL")

    def test_post_spawn_receipt_failure_still_reaps_actual_child(self):
        original = Path.write_text
        calls = 0

        def write(path, *args, **kwargs):
            nonlocal calls
            if path.parent == self.scratch and path.suffix == ".json":
                calls += 1
                if calls == 2:
                    raise OSError("selected post-spawn diagnostic failure")
            return original(path, *args, **kwargs)

        with patch.object(gate, "DIAGNOSTICS", self.scratch):
            with patch.object(Path, "write_text", new=write):
                with self.assertRaisesRegex(OSError, "selected post-spawn"):
                    gate.run(
                        [self.python, "-I", "-c", "import time; time.sleep(30)"],
                        environment=self.environment,
                        timeout=1,
                    )
        row = json.loads(next(self.scratch.glob("command-*.json")).read_text())
        self.assertTrue(row["post_kill_reap_confirmed"])
        with self.assertRaises(ProcessLookupError):
            os.kill(row["pid"], 0)

    def test_unconfirmed_wait_is_bounded_and_retains_diagnostics(self):
        children = []
        waits = []
        original = subprocess.Popen

        def launch(*args, **kwargs):
            child = original(*args, **kwargs)
            children.append(child)
            real_wait = child.wait

            def wait(timeout=None):
                waits.append(timeout)
                if len(waits) == 2:
                    raise subprocess.TimeoutExpired(child.args, timeout)
                return real_wait(timeout=timeout)

            child.wait = wait
            return child

        retained = None
        try:
            with patch.object(gate.subprocess, "Popen", side_effect=launch):
                with self.assertRaises(gate.CleanupUnconfirmedError):
                    with gate.gate_directory() as retained:
                        with patch.object(gate, "DIAGNOSTICS", retained):
                            gate.run(
                                [
                                    self.python,
                                    "-I",
                                    "-c",
                                    "import time; time.sleep(30)",
                                ],
                                environment=self.environment,
                                timeout=0.2,
                            )
            self.assertEqual(waits, [0.2, gate.KILL_WAIT_SECONDS])
            self.assertTrue(retained.is_dir())
            row = json.loads(next(retained.glob("command-*.json")).read_text())
            self.assertFalse(row["post_kill_reap_confirmed"])
            self.assertEqual(row["status"], "FAIL")
        finally:
            for child in children:
                subprocess.Popen.wait(child, timeout=5)
                with self.assertRaises(ProcessLookupError):
                    os.kill(child.pid, 0)
            if retained is not None:
                shutil.rmtree(retained)


if __name__ == "__main__":
    unittest.main(verbosity=2)
