#!/usr/bin/env python3
"""Run local SDK source and installed-wheel controls. Grant no release authority.

The complete check.sh composition owns broad-core feature checks, Markdown,
whitespace and the separate current/pinned dependency policy scans.
This runner owns only standalone source, package and SDK behavior checks.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import zipfile
from contextlib import contextmanager
from pathlib import Path

INSTALLED_PROGRAM = r"""
import hashlib, json, pathlib, sys, ncp_local
from ncp_local.modular_owner import profile_digest

root = pathlib.Path(ncp_local.__file__).parent.resolve()
expected = json.loads(pathlib.Path(sys.argv[1]).read_text())
if not root.is_relative_to(pathlib.Path(sys.argv[2]).resolve()):
    raise RuntimeError("SDK import escaped fresh installation")
actual = {
    str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
    for p in root.rglob("*")
    if p.is_file() and "__pycache__" not in p.parts
}
if actual != expected:
    raise RuntimeError("installed SDK bytes differ from wheel/source")
print(
    json.dumps(
        {
            "installed_root": str(root),
            "profile_digest": profile_digest(),
            "files": actual,
        },
        sort_keys=True,
    )
)
"""
SUITE_PROGRAM = r"""
import pathlib, sys, unittest, ncp_local

installed_root = pathlib.Path(ncp_local.__file__).parent.resolve()
expected_root = pathlib.Path(sys.argv[2]).resolve()


def verify_origins():
    for name, module in tuple(sys.modules.items()):
        if name == "ncp_local" or name.startswith("ncp_local."):
            origin = getattr(module, "__file__", None)
            if origin is None or not pathlib.Path(origin).resolve().is_relative_to(
                expected_root
            ):
                raise RuntimeError("SDK module escaped installed package: " + name)


if not installed_root.is_relative_to(expected_root):
    raise RuntimeError("SDK package is not installed")
verify_origins()
suite = unittest.defaultTestLoader.discover(sys.argv[1])
if not suite.countTestCases():
    raise RuntimeError("empty SDK suite")
result = unittest.TextTestRunner(verbosity=2).run(suite)
verify_origins()
raise SystemExit(0 if result.wasSuccessful() and not result.skipped else 1)
"""

ROOT = Path(__file__).resolve().parents[1]
KILL_WAIT_SECONDS = 5.0
DIAGNOSTICS = None
COMMAND_NUMBER = 0
REFERENCE_COMMIT = "de751d499b5e07d1c95a072e08255083d77cb38b"
REFERENCE_FILES = (
    "ncp-core/src/local.rs",
    "ncp-core/src/local_data.rs",
    "ncp-core/src/bounded_json.rs",
    "ncp-core/src/canonical_digest.rs",
    "ncp-core/local-profile.v1.json",
    "ncp-core/tests/local.rs",
    "ncp-core/tests/local_binary64.rs",
    "ncp-core/tests/local_profile_contract.rs",
    "local/rust/local-profile.v1.json",
    "local/rust/src/local.rs",
    "local/rust/src/local_data.rs",
    "local/python/ncp_local/__init__.py",
    "local/python/ncp_local/protocol.py",
    "local/python/ncp_local/wire.py",
    "local/python/ncp_local/data.py",
    "local/python/ncp_local/local-profile.v1.json",
    "local/release.v1.json",
    "Cargo.toml",
    "Cargo.lock",
    "local/rust/Cargo.toml",
    "local/rust/Cargo.lock",
    "local/python/pyproject.toml",
)


def git_executable():
    executable = shutil.which("git")
    if executable is None:
        raise RuntimeError("Git is unavailable")
    return str(Path(executable).absolute())


def git_environment():
    environment = {
        key: value for key, value in os.environ.items() if not key.startswith("GIT_")
    }
    environment.update(
        GIT_CONFIG_GLOBAL=os.devnull,
        GIT_CONFIG_SYSTEM=os.devnull,
        GIT_CONFIG_NOSYSTEM="1",
        GIT_NO_REPLACE_OBJECTS="1",
        GIT_OPTIONAL_LOCKS="0",
    )
    return environment


def source_rows(root=ROOT) -> dict[str, dict[str, str | int]]:
    # Fixed local Git query. No shell or caller-provided Git expression.
    output = subprocess.check_output(  # noqa: S603
        [
            git_executable(),
            "ls-files",
            "-z",
            "--cached",
            "--others",
            "--exclude-standard",
        ],
        cwd=root,
        env=git_environment(),
        timeout=20,
    )
    result = {}
    for name in sorted(set(output.decode("utf-8").split("\0")) - {""}):
        path = root / name
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode):
            content = os.readlink(path).encode("utf-8")
        elif stat.S_ISREG(info.st_mode):
            content = path.read_bytes()
        else:
            raise RuntimeError(f"source entry is not a file: {name}")
        result[name] = {
            "bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
            "mode": stat.S_IMODE(info.st_mode),
        }
    return result


def reference_parity(
    root=ROOT, revision=REFERENCE_COMMIT, files=REFERENCE_FILES
) -> None:
    for name in files:
        # The source contract fixes this historical revision and file roster.
        expected = subprocess.check_output(  # noqa: S603
            [git_executable(), "show", f"{revision}:{name}"],
            cwd=root,
            env=git_environment(),
            timeout=20,
        )
        if (root / name).read_bytes() != expected:
            raise RuntimeError(f"historical reference changed: {name}")


def wheel_contents(wheel: Path, source: dict) -> dict[str, str]:
    expected = {
        name.removeprefix("local/python/"): row["sha256"]
        for name, row in source.items()
        if name.startswith("local/python/ncp_local/")
    }
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise RuntimeError("wheel contains duplicate entries")
        actual = {
            name: hashlib.sha256(archive.read(name)).hexdigest()
            for name in names
            if name.startswith("ncp_local/") and not name.endswith("/")
        }
    if not expected or actual != expected:
        raise RuntimeError("wheel package entries differ from selected source bytes")
    return {
        name.removeprefix("ncp_local/"): digest for name, digest in expected.items()
    }


class CleanupUnconfirmedError(RuntimeError):
    """The direct child was not confirmed reaped within the cleanup deadline."""


def source_unchanged(expected, root=ROOT):
    if source_rows(root) != expected:
        raise RuntimeError("SDK gate changed source bytes, modes or source membership")


def require_probe(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or not os.access(path, os.X_OK):
        raise RuntimeError(f"mandatory native probe is not an executable file: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


@contextmanager
def gate_directory():
    temporary = Path(tempfile.mkdtemp(prefix="ncp-local-sdk-"))
    try:
        yield temporary
    except BaseException:
        print(
            f"FAILED: SDK gate diagnostics retained at {temporary}",
            file=sys.stderr,
            flush=True,
        )
        raise
    else:
        try:
            shutil.rmtree(temporary)
        except OSError:
            print(
                f"FAILED: SDK gate cleanup is incomplete at {temporary}",
                file=sys.stderr,
                flush=True,
            )
            raise


def run(argv, *, environment, timeout=1200, cwd=ROOT) -> None:
    global COMMAND_NUMBER
    if DIAGNOSTICS is None:
        raise RuntimeError("SDK gate diagnostic directory is not prepared")
    COMMAND_NUMBER += 1
    command = [str(value) for value in argv]
    log = DIAGNOSTICS / f"command-{COMMAND_NUMBER:03d}.log"
    receipt = log.with_suffix(".json")
    row = {
        "command": command,
        "cwd": str(cwd),
        "timeout_s": timeout,
        "log": log.name,
        "status": "RUNNING",
    }
    receipt.write_text(json.dumps(row, indent=2) + "\n")
    print(json.dumps(row), flush=True)
    start = time.monotonic()
    with log.open("wb") as output:
        try:
            # Only this maintained gate and its explicit controls call this helper.
            process = subprocess.Popen(  # noqa: S603
                command,
                cwd=cwd,
                env=environment,
                stdout=output,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        except OSError as error:
            row.update(
                status="FAIL",
                error=f"{type(error).__name__}: {error}",
                process_started=False,
            )
            receipt.write_text(json.dumps(row, indent=2) + "\n")
            raise
        try:
            row["pid"] = process.pid
            receipt.write_text(json.dumps(row, indent=2) + "\n")
            code = process.wait(timeout=timeout)
        except BaseException as primary:
            row.update(
                status="FAIL",
                error=f"{type(primary).__name__}: {primary}",
                post_kill_reap_confirmed=False,
            )
            try:
                os.killpg(process.pid, signal.SIGKILL)
                row["process_group_kill"] = "SENT"
            except ProcessLookupError:
                row["process_group_kill"] = "ALREADY_ABSENT"
            except OSError as error:
                row["process_group_kill"] = repr(error)
            try:
                row["returncode"] = process.wait(timeout=KILL_WAIT_SECONDS)
                row["post_kill_reap_confirmed"] = True
            except (subprocess.TimeoutExpired, OSError) as error:
                row["cleanup_error"] = repr(error)
            row["elapsed_s"] = time.monotonic() - start
            try:
                receipt.write_text(json.dumps(row, indent=2) + "\n")
            except OSError as error:
                row["diagnostic_write_error"] = repr(error)
                print(json.dumps(row), file=sys.stderr, flush=True)
            if not row["post_kill_reap_confirmed"]:
                raise CleanupUnconfirmedError(
                    f"cleanup unconfirmed; retain {DIAGNOSTICS}"
                ) from primary
            raise
    row.update(
        status="PASS" if code == 0 else "FAIL",
        returncode=code,
        elapsed_s=time.monotonic() - start,
        log_sha256=hashlib.sha256(log.read_bytes()).hexdigest(),
    )
    receipt.write_text(json.dumps(row, indent=2) + "\n")
    with log.open("rb") as output:
        shutil.copyfileobj(output, sys.stdout.buffer)
    sys.stdout.flush()
    if code:
        raise RuntimeError(f"gate command failed with exit {code}: {command}")


def main() -> None:
    global DIAGNOSTICS
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--python", default=sys.executable, help="Python >=3.11; fresh SDK venvs only"
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run only mandatory gate-integrity controls",
    )
    args = parser.parse_args()
    python = shutil.which(args.python)
    if python is None:
        raise RuntimeError("selected SDK Python is unavailable")
    environment = git_environment()
    for key in (
        "PYTHONPATH",
        "PYTHONHOME",
        "CARGO_TARGET_DIR",
        "RUSTFLAGS",
        "CARGO_ENCODED_RUSTFLAGS",
    ):
        environment.pop(key, None)
    environment.update(PYTHONDONTWRITEBYTECODE="1", PIP_DISABLE_PIP_VERSION_CHECK="1")
    with gate_directory() as temporary:
        DIAGNOSTICS = temporary
        run(
            [sys.executable, "-I", ROOT / "scripts/test_local_sdk_gate.py"],
            environment=environment,
        )
        if args.self_test:
            print(
                "SDK gate-integrity controls passed; "
                "SDK operational checks were not run"
            )
            return
        before = source_rows()
        reference_parity()
        source_bytes = (json.dumps(before, indent=2) + "\n").encode("utf-8")
        source_digest = hashlib.sha256(source_bytes).hexdigest()
        (temporary / "source-before.json").write_bytes(source_bytes)
        print(
            json.dumps(
                {"source_roster_sha256": source_digest, "source_files": len(before)}
            ),
            flush=True,
        )
        run(
            [
                python,
                "-I",
                "-c",
                "import sys; print(sys.version); "
                "raise SystemExit(0 if sys.version_info >= (3,11) else 1)",
            ],
            environment=environment,
        )
        for toolchain in ("1.96.0", "1.88.0"):
            for arguments in (
                ("cargo", "--version"),
                ("rustc", "-Vv"),
                ("cargo", "clippy", "--version"),
            ):
                run(
                    [arguments[0], "+" + toolchain, *arguments[1:]],
                    environment=environment,
                )
        run(
            [
                "cargo",
                "+1.96.0",
                "fmt",
                "--manifest-path",
                "local/rust/Cargo.toml",
                "--",
                "--check",
            ],
            environment=environment,
        )
        for generator in (
            "scripts/project_modular_profile.py",
            "scripts/project_local_rust.py",
        ):
            run([python, "-I", generator, "--check"], environment=environment)
        run(
            [
                "cargo",
                "+1.96.0",
                "fetch",
                "--manifest-path",
                "local/rust/Cargo.toml",
                "--locked",
            ],
            environment=environment,
        )
        for toolchain in ("1.96.0", "1.88.0"):
            native = dict(
                environment, CARGO_TARGET_DIR=str(temporary / ("rust-" + toolchain))
            )
            for command in ("test", "clippy"):
                argv = [
                    "cargo",
                    "+" + toolchain,
                    command,
                    "--manifest-path",
                    "local/rust/Cargo.toml",
                    "--all-features",
                    "--locked",
                    "--offline",
                ]
                if command == "clippy":
                    argv += ["--all-targets", "--", "-D", "warnings"]
                run(argv, environment=native)
        native = dict(environment, CARGO_TARGET_DIR=str(temporary / "rust-1.96.0"))
        run(
            [
                "cargo",
                "+1.96.0",
                "build",
                "--manifest-path",
                "local/rust/Cargo.toml",
                "--locked",
                "--offline",
                "--examples",
            ],
            environment=native,
        )
        run(
            [
                "cargo",
                "+1.96.0",
                "package",
                "--manifest-path",
                "local/rust/Cargo.toml",
                "--allow-dirty",
                "--locked",
                "--offline",
            ],
            environment=native,
        )
        archives = list((temporary / "rust-1.96.0/package").glob("*.crate"))
        if len(archives) != 1 or not archives[0].is_file():
            raise RuntimeError("SDK package did not produce exactly one Rust archive")
        rust_archive_digest = hashlib.sha256(archives[0].read_bytes()).hexdigest()
        build_source = temporary / "wheel-source"
        for name in before:
            if name.startswith("local/python/"):
                destination = build_source / name.removeprefix("local/python/")
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / name, destination, follow_symlinks=False)
        build = temporary / "build"
        installed = temporary / "installed"
        for target in (build, installed):
            run(
                [python, "-I", "-m", "venv", target],
                environment=environment,
                timeout=120,
            )
        build_python = build / "bin/python"
        installed_python = installed / "bin/python"
        run(
            [
                build_python,
                "-I",
                "-m",
                "pip",
                "install",
                "--only-binary=:all:",
                "-r",
                ROOT / "scripts/requirements-local-sdk-build.txt",
            ],
            environment=environment,
            timeout=300,
        )
        run(
            [build_python, "-I", "-m", "pip", "list", "--format=json"],
            environment=environment,
        )
        run(
            [
                build_python,
                "-I",
                "-m",
                "pip",
                "wheel",
                "--no-index",
                "--no-deps",
                "--no-build-isolation",
                "--wheel-dir",
                temporary / "dist",
                build_source,
            ],
            environment=environment,
        )
        wheels = list((temporary / "dist").glob("*.whl"))
        if len(wheels) != 1:
            raise RuntimeError("SDK build did not produce exactly one wheel")
        expected_package = wheel_contents(wheels[0], before)
        run(
            [
                installed_python,
                "-I",
                "-m",
                "pip",
                "install",
                "--only-binary=:all:",
                "-r",
                ROOT / "local/profile/requirements-test.txt",
            ],
            environment=environment,
            timeout=300,
        )
        run(
            [
                installed_python,
                "-I",
                "-m",
                "pip",
                "install",
                "--no-index",
                "--no-deps",
                wheels[0],
            ],
            environment=environment,
        )
        expected_file = temporary / "expected-package.json"
        expected_file.write_text(json.dumps(expected_package, sort_keys=True) + "\n")
        run(
            [installed_python, "-I", "-c", INSTALLED_PROGRAM, expected_file, installed],
            environment=environment,
            cwd=temporary,
        )
        probes = {}
        for key, name in (
            ("NCP_LOCAL_CONTRACT_PROBE", "local_contract_probe"),
            ("NCP_MODULAR_PROBE", "modular_buffer_probe"),
            ("NCP_MODULAR_OWNER_PROBE", "modular_owner_probe"),
        ):
            path = temporary / "rust-1.96.0/debug/examples" / name
            probes[key] = str(path)
            print(json.dumps({"probe": name, "sha256": require_probe(path)}))
        for suite in ("local/python/tests", "local/profile", "local/modular"):
            run(
                [
                    installed_python,
                    "-I",
                    "-c",
                    SUITE_PROGRAM,
                    str(ROOT / suite),
                    installed,
                ],
                environment=dict(environment, **probes),
                cwd=temporary,
                timeout=600,
            )
        run([python, "-I", "scripts/check_local_scope.py"], environment=environment)
        reference_parity()
        source_unchanged(before)
        print(
            json.dumps(
                {
                    "status": "LOCAL_SDK_CONTROLS_PASS",
                    "source_unchanged": True,
                    "source_roster_sha256": source_digest,
                    "source_files": len(before),
                    "historical_reference_files": len(REFERENCE_FILES),
                    "rust_crate_sha256": rust_archive_digest,
                    "wheel_sha256": hashlib.sha256(wheels[0].read_bytes()).hexdigest(),
                    "release_authorized": False,
                    "dependency_policy_owned_by_complete_gate": True,
                }
            )
        )


if __name__ == "__main__":
    main()
