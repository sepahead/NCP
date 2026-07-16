#!/usr/bin/env python3
"""Prepare one bounded current RustSec database for the local gate.

``cargo-deny 0.19.9`` clones the complete advisory-db history when its database
is absent.  This helper instead resolves the one official branch, creates a
depth-one clone in a fresh external Cargo home, verifies the exact commit and
tree before and after the clone, and writes a bounded receipt.  The caller must
still run cargo-deny with ``--disable-fetch`` and separately replay the
evidence-pinned advisory revision.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_URL = "https://github.com/RustSec/advisory-db"
EXPECTED_BRANCH = "main"
EXPECTED_BRANCH_REF = "refs/heads/main"
DATABASE_NAME = "advisory-db-3157b0e258782691"
DATABASE_DIRECTORY = re.compile(r"^advisory-db-[0-9a-f]{16}$")
REVISION = re.compile(r"^[0-9a-f]{40}$")
TREE = re.compile(r"^[0-9a-f]{40}$")
GIT_VERSION = re.compile(r"^git version [0-9]+\.[0-9]+(?:\.[0-9]+)?(?: .+)?$")
MAX_COMMAND_OUTPUT_BYTES = 64 * 1024
MAX_DATABASE_BYTES = 64 * 1024 * 1024
MAX_DATABASE_FILES = 5_000
MAX_DATABASE_DIRECTORIES = 5_000
MAX_DATABASE_PATH_BYTES = 1_024
MAX_DATABASE_PATH_DEPTH = 16
COMMAND_TIMEOUT_SECONDS = 300


class PreparationError(ValueError):
    """The current advisory database could not be prepared safely."""


def _outside_repository(path: Path, label: str) -> None:
    root = ROOT.resolve()
    if path == root or root in path.parents:
        raise PreparationError(f"{label} must be outside the repository")


def _git_binary() -> Path:
    value = shutil.which("git")
    if value is None:
        raise PreparationError("git is required")
    path = Path(value).resolve()
    try:
        mode = path.stat().st_mode
    except OSError as error:
        raise PreparationError(f"cannot inspect git: {error}") from error
    if not stat.S_ISREG(mode):
        raise PreparationError("git must resolve to a regular file")
    return path


def _git_environment(home: Path, git: Path) -> dict[str, str]:
    path_entries = [str(git.parent), "/usr/bin", "/bin", "/usr/sbin", "/sbin"]
    environment = {
        "PATH": ":".join(dict.fromkeys(path_entries)),
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(home / "xdg-config"),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_ASKPASS": "/usr/bin/false",
        "GCM_INTERACTIVE": "never",
        "GIT_ALLOW_PROTOCOL": "https",
        "LANG": "C",
        "LC_ALL": "C",
    }
    tmpdir = os.environ.get("TMPDIR")
    if tmpdir:
        environment["TMPDIR"] = tmpdir
    return environment


def _run(
    command: list[str],
    *,
    environment: dict[str, str],
    cwd: Path | None = None,
) -> bytes:
    try:
        process = subprocess.run(
            command,
            cwd=cwd or ROOT,
            env=environment,
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=COMMAND_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as error:
        raise PreparationError(
            f"{command[0]} timed out after {COMMAND_TIMEOUT_SECONDS} seconds"
        ) from error
    except OSError as error:
        raise PreparationError(f"cannot execute {command[0]}: {error}") from error
    if (
        len(process.stdout) > MAX_COMMAND_OUTPUT_BYTES
        or len(process.stderr) > MAX_COMMAND_OUTPUT_BYTES
    ):
        raise PreparationError(f"{command[0]} output exceeded the bounded limit")
    if process.returncode != 0:
        detail = process.stderr.decode("utf-8", "replace").strip()
        if not detail:
            detail = process.stdout.decode("utf-8", "replace").strip()
        raise PreparationError(
            f"{' '.join(command)} failed with exit {process.returncode}: {detail}"
        )
    return process.stdout


def _ls_remote_command(git: Path) -> list[str]:
    return [
        str(git),
        "-c",
        "credential.helper=",
        "ls-remote",
        "--symref",
        EXPECTED_URL,
        "HEAD",
        EXPECTED_BRANCH_REF,
    ]


def _clone_command(git: Path, destination: Path) -> list[str]:
    return [
        str(git),
        "-c",
        "credential.helper=",
        "clone",
        "--depth=1",
        "--single-branch",
        "--branch",
        EXPECTED_BRANCH,
        "--no-tags",
        EXPECTED_URL,
        str(destination),
    ]


def _parse_ls_remote(raw: bytes) -> str:
    if len(raw) > MAX_COMMAND_OUTPUT_BYTES or b"\x00" in raw:
        raise PreparationError("RustSec ls-remote output is unbounded or contains NUL")
    try:
        text = raw.decode("ascii", "strict")
    except UnicodeError as error:
        raise PreparationError("RustSec ls-remote output is not ASCII") from error
    lines = text.splitlines()
    expected_prefix = f"ref: {EXPECTED_BRANCH_REF}\tHEAD"
    if len(lines) != 3 or lines[0] != expected_prefix:
        raise PreparationError("RustSec ls-remote output has an unexpected shape")
    head = lines[1].split("\t")
    branch = lines[2].split("\t")
    if (
        len(head) != 2
        or len(branch) != 2
        or head[1] != "HEAD"
        or branch[1] != EXPECTED_BRANCH_REF
        or REVISION.fullmatch(head[0]) is None
        or branch[0] != head[0]
    ):
        raise PreparationError("RustSec HEAD and main do not resolve exactly")
    return head[0]


def _git(
    git: Path,
    database: Path,
    arguments: list[str],
    *,
    environment: dict[str, str],
) -> bytes:
    return _run(
        [str(git), "-C", str(database), *arguments],
        environment=environment,
    )


def _plain_inventory(path: Path) -> tuple[int, int, int]:
    files = 0
    directories = 0
    total_bytes = 0
    for root, names, filenames in os.walk(path, followlinks=False):
        root_path = Path(root)
        names.sort()
        filenames.sort()
        directories += 1
        if directories > MAX_DATABASE_DIRECTORIES:
            raise PreparationError(
                "RustSec database directory count exceeded its limit"
            )
        for name in [*names, *filenames]:
            candidate = root_path / name
            try:
                relative = candidate.relative_to(path)
            except ValueError as error:
                raise PreparationError(
                    "RustSec database traversal escaped its root"
                ) from error
            if (
                len(relative.as_posix().encode("utf-8")) > MAX_DATABASE_PATH_BYTES
                or len(relative.parts) > MAX_DATABASE_PATH_DEPTH
            ):
                raise PreparationError("RustSec database path exceeded its limit")
            try:
                metadata = candidate.lstat()
            except OSError as error:
                raise PreparationError(
                    f"cannot inspect RustSec database entry: {error}"
                ) from error
            if stat.S_ISLNK(metadata.st_mode):
                raise PreparationError("RustSec database contains a symbolic link")
            if stat.S_ISDIR(metadata.st_mode):
                continue
            if not stat.S_ISREG(metadata.st_mode):
                raise PreparationError("RustSec database contains a special entry")
            files += 1
            total_bytes += metadata.st_size
            if files > MAX_DATABASE_FILES:
                raise PreparationError("RustSec database file count exceeded its limit")
            if total_bytes > MAX_DATABASE_BYTES:
                raise PreparationError("RustSec database byte count exceeded its limit")
    return files, directories, total_bytes


def _one_line(raw: bytes, label: str, pattern: re.Pattern[str]) -> str:
    try:
        value = raw.decode("ascii", "strict").strip()
    except UnicodeError as error:
        raise PreparationError(f"{label} is not ASCII") from error
    if "\n" in value or pattern.fullmatch(value) is None:
        raise PreparationError(f"{label} is malformed")
    return value


def _validate_database(
    git: Path,
    database: Path,
    revision: str,
    *,
    environment: dict[str, str],
) -> dict[str, Any]:
    if not database.is_dir() or not (database / ".git").is_dir():
        raise PreparationError("RustSec clone has an unexpected layout")
    files, directories, total_bytes = _plain_inventory(database)
    head = _one_line(
        _git(
            git,
            database,
            ["rev-parse", "--verify", "HEAD^{commit}"],
            environment=environment,
        ),
        "RustSec HEAD",
        REVISION,
    )
    if head != revision:
        raise PreparationError("RustSec shallow clone differs from advertised HEAD")
    tree = _one_line(
        _git(
            git,
            database,
            ["rev-parse", "--verify", "HEAD^{tree}"],
            environment=environment,
        ),
        "RustSec tree",
        TREE,
    )
    shallow = (
        _git(
            git,
            database,
            ["rev-parse", "--is-shallow-repository"],
            environment=environment,
        )
        .decode("ascii", "strict")
        .strip()
    )
    if shallow != "true":
        raise PreparationError("RustSec current database must be depth-limited")
    shallow_file = database / ".git" / "shallow"
    try:
        shallow_bytes = shallow_file.read_bytes()
    except OSError as error:
        raise PreparationError(
            f"cannot read RustSec shallow boundary: {error}"
        ) from error
    if shallow_bytes != f"{revision}\n".encode("ascii"):
        raise PreparationError("RustSec shallow boundary is not the advertised commit")
    origin = (
        _git(
            git,
            database,
            ["config", "--get-all", "remote.origin.url"],
            environment=environment,
        )
        .decode("utf-8", "strict")
        .splitlines()
    )
    if origin != [EXPECTED_URL]:
        raise PreparationError("RustSec clone has an unexpected origin")
    remotes = (
        _git(git, database, ["remote"], environment=environment)
        .decode("ascii", "strict")
        .splitlines()
    )
    if remotes != ["origin"]:
        raise PreparationError("RustSec clone must have exactly one remote")
    refs_output = _git(
        git,
        database,
        ["for-each-ref", "--format=%(refname)%09%(objectname)"],
        environment=environment,
    ).decode("ascii", "strict")
    refs: dict[str, str] = {}
    for line in refs_output.splitlines():
        members = line.split("\t")
        if (
            len(members) != 2
            or members[0] in refs
            or REVISION.fullmatch(members[1]) is None
        ):
            raise PreparationError("RustSec clone contains malformed refs")
        refs[members[0]] = members[1]
    if refs != {
        EXPECTED_BRANCH_REF: revision,
        f"refs/remotes/origin/{EXPECTED_BRANCH}": revision,
    }:
        raise PreparationError("RustSec clone contains an unexpected ref set")
    if _git(git, database, ["status", "--porcelain"], environment=environment):
        raise PreparationError("RustSec clone is not clean")
    if (database / ".git" / "objects" / "info" / "alternates").exists():
        raise PreparationError("RustSec clone must not use object alternates")
    if _git(
        git,
        database,
        ["fsck", "--full", "--no-reflogs", "--unreachable", "--no-progress"],
        environment=environment,
    ):
        raise PreparationError("RustSec clone has unexpected unreachable objects")
    timestamp = _one_line(
        _git(
            git,
            database,
            ["show", "-s", "--format=%cI", "HEAD"],
            environment=environment,
        ),
        "RustSec commit timestamp",
        re.compile(r"^[0-9T:+-]+$"),
    )
    try:
        commit_time = dt.datetime.fromisoformat(timestamp)
    except ValueError as error:
        raise PreparationError("RustSec commit timestamp is invalid") from error
    if commit_time.tzinfo is None:
        raise PreparationError("RustSec commit timestamp lacks a timezone")
    now = dt.datetime.now(dt.UTC)
    if commit_time.astimezone(dt.UTC) > now + dt.timedelta(minutes=5):
        raise PreparationError("RustSec commit timestamp is implausibly in the future")
    return {
        "commit": head,
        "tree": tree,
        "commit_timestamp": timestamp,
        "file_count": files,
        "directory_count": directories,
        "bytes": total_bytes,
    }


def _validate_paths(destination: Path, receipt: Path) -> tuple[Path, Path, Path]:
    destination = destination.resolve()
    receipt = receipt.resolve()
    _outside_repository(destination, "advisory database destination")
    _outside_repository(receipt, "advisory database receipt")
    configured = os.environ.get("NCP_CURRENT_ADVISORY_DB_PATH")
    if configured is None or Path(configured).resolve() != destination:
        raise PreparationError(
            "destination must equal the absolute NCP_CURRENT_ADVISORY_DB_PATH"
        )
    if (
        destination.name != "advisory-dbs"
        or destination.parent.name != ".cargo"
        or DATABASE_DIRECTORY.fullmatch(DATABASE_NAME) is None
    ):
        raise PreparationError("advisory database destination has an unexpected layout")
    home = destination.parent.parent
    if not home.is_dir() or home.is_symlink():
        raise PreparationError("current advisory HOME must be a plain directory")
    if receipt == home or home in receipt.parents:
        raise PreparationError("advisory database receipt must be outside its HOME")
    if destination.exists() and (
        not destination.is_dir()
        or destination.is_symlink()
        or any(destination.iterdir())
    ):
        raise PreparationError("advisory database destination must be new or empty")
    if receipt.exists() or receipt.is_symlink():
        raise PreparationError("advisory database receipt path must be absent")
    if not receipt.parent.is_dir() or receipt.parent.is_symlink():
        raise PreparationError(
            "advisory database receipt parent must be a plain directory"
        )
    return destination, receipt, home


def _write_receipt(path: Path, value: dict[str, Any]) -> None:
    encoded = (
        json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    ).encode("ascii")
    if len(encoded) > MAX_COMMAND_OUTPUT_BYTES:
        raise PreparationError("advisory database receipt exceeded its limit")
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as error:
        raise PreparationError(
            f"cannot write advisory database receipt: {error}"
        ) from error


def prepare(destination: Path, receipt: Path) -> dict[str, Any]:
    destination, receipt, home = _validate_paths(destination, receipt)
    git = _git_binary()
    environment = _git_environment(home, git)
    (home / "xdg-config").mkdir(mode=0o700, exist_ok=True)
    destination.mkdir(mode=0o700, parents=True, exist_ok=True)
    before = _parse_ls_remote(_run(_ls_remote_command(git), environment=environment))
    partial = destination / f".{DATABASE_NAME}.partial"
    database = destination / DATABASE_NAME
    if (
        partial.exists()
        or partial.is_symlink()
        or database.exists()
        or database.is_symlink()
    ):
        raise PreparationError("advisory database clone paths must be absent")
    _run(_clone_command(git, partial), environment=environment)
    details = _validate_database(
        git,
        partial,
        before,
        environment=environment,
    )
    after = _parse_ls_remote(_run(_ls_remote_command(git), environment=environment))
    if after != before:
        raise PreparationError("RustSec advertised HEAD changed during preparation")
    partial.rename(database)
    lock_path = destination / "db.lock"
    descriptor = os.open(lock_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(descriptor)
    git_version = _one_line(
        _run([str(git), "--version"], environment=environment),
        "git version",
        GIT_VERSION,
    )
    result = {
        "schema": "ncp-current-rustsec-database-receipt-v1",
        "url": EXPECTED_URL,
        "branch": EXPECTED_BRANCH_REF,
        "advertised_before": before,
        "advertised_after": after,
        "commit": details["commit"],
        "tree": details["tree"],
        "commit_timestamp": details["commit_timestamp"],
        "verified_at_utc": dt.datetime.now(dt.UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "shallow": True,
        "fetch_depth": 1,
        "tags": False,
        "file_count": details["file_count"],
        "directory_count": details["directory_count"],
        "bytes": details["bytes"],
        "git_version": git_version,
        "cargo_deny_fetch_disabled_required": True,
    }
    _write_receipt(receipt, result)
    return result


def _self_test() -> None:
    valid = "a" * 40
    raw = (
        f"ref: {EXPECTED_BRANCH_REF}\tHEAD\n"
        f"{valid}\tHEAD\n"
        f"{valid}\t{EXPECTED_BRANCH_REF}\n"
    ).encode("ascii")
    if _parse_ls_remote(raw) != valid:
        raise AssertionError("valid RustSec ls-remote output rejected")
    hostile = [
        b"",
        raw + b"extra\tref\n",
        raw.replace(b"\tHEAD\n", b"\tHEAD\n", 1).replace(
            valid.encode("ascii"), b"A" * 40, 1
        ),
        raw.replace(b"refs/heads/main", b"refs/heads/master", 1),
        raw.replace(f"{valid}\tHEAD".encode(), f"{'b' * 40}\tHEAD".encode()),
        raw + b"\x00",
        raw[:-1] + b"\xff\n",
    ]
    for value in hostile:
        try:
            _parse_ls_remote(value)
        except PreparationError:
            pass
        else:
            raise AssertionError("hostile RustSec ls-remote output passed")
    git = Path("/usr/bin/git")
    expected_ls_remote = [
        str(git),
        "-c",
        "credential.helper=",
        "ls-remote",
        "--symref",
        EXPECTED_URL,
        "HEAD",
        EXPECTED_BRANCH_REF,
    ]
    if _ls_remote_command(git) != expected_ls_remote:
        raise AssertionError("RustSec ls-remote command profile drifted")
    clone = _clone_command(git, Path("/tmp/database"))
    for required in (
        "--depth=1",
        "--single-branch",
        "--branch",
        EXPECTED_BRANCH,
        "--no-tags",
        EXPECTED_URL,
    ):
        if required not in clone:
            raise AssertionError("RustSec clone command lost a bounded invariant")
    with tempfile.TemporaryDirectory(
        prefix="ncp-current-advisory-self-test-"
    ) as raw_root:
        root = Path(raw_root)
        plain = root / "plain"
        plain.mkdir()
        (plain / "file").write_bytes(b"x")
        if _plain_inventory(plain) != (1, 1, 1):
            raise AssertionError("plain RustSec inventory is incorrect")
        if hasattr(os, "symlink"):
            (plain / "link").symlink_to("file")
            try:
                _plain_inventory(plain)
            except PreparationError:
                pass
            else:
                raise AssertionError("linked RustSec entry passed inventory")
        special_root = root / "special"
        special_root.mkdir()
        if hasattr(os, "mkfifo"):
            os.mkfifo(special_root / "fifo")
            try:
                _plain_inventory(special_root)
            except PreparationError:
                pass
            else:
                raise AssertionError("special RustSec entry passed inventory")
        environment = _git_environment(root, git)
        for forbidden in (
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "ALL_PROXY",
            "GIT_DIR",
            "GIT_WORK_TREE",
            "GIT_CONFIG_COUNT",
        ):
            if forbidden in environment:
                raise AssertionError("Git environment retained an injection surface")
        if (
            environment.get("GIT_CONFIG_NOSYSTEM") != "1"
            or environment.get("GIT_CONFIG_GLOBAL") != "/dev/null"
            or environment.get("GIT_ALLOW_PROTOCOL") != "https"
        ):
            raise AssertionError("Git environment lost a fail-closed invariant")
        home = root / "home"
        home.mkdir()
        destination = home / ".cargo" / "advisory-dbs"
        receipt = root / "receipt.json"
        previous = os.environ.get("NCP_CURRENT_ADVISORY_DB_PATH")
        os.environ["NCP_CURRENT_ADVISORY_DB_PATH"] = str(destination)
        try:
            if _validate_paths(destination, receipt) != (
                destination.resolve(),
                receipt.resolve(),
                home.resolve(),
            ):
                raise AssertionError("valid advisory preparation paths drifted")
            destination.mkdir(parents=True)
            (destination / "occupied").write_bytes(b"x")
            try:
                _validate_paths(destination, receipt)
            except PreparationError:
                pass
            else:
                raise AssertionError("occupied advisory destination passed")
        finally:
            if previous is None:
                os.environ.pop("NCP_CURRENT_ADVISORY_DB_PATH", None)
            else:
                os.environ["NCP_CURRENT_ADVISORY_DB_PATH"] = previous
        try:
            _outside_repository(ROOT / "forbidden", "hostile destination")
        except PreparationError:
            pass
        else:
            raise AssertionError("repository-local advisory destination passed")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        if args.self_test:
            if args.destination is not None or args.receipt is not None:
                raise PreparationError(
                    "--self-test cannot be combined with preparation options"
                )
            _self_test()
            print("OK current advisory database preparer self-test")
            return 0
        if args.destination is None or args.receipt is None:
            raise PreparationError("--destination and --receipt are required")
        result = prepare(args.destination, args.receipt)
        print(
            "OK current RustSec advisory database prepared: "
            f"commit {result['commit']}, tree {result['tree']}, "
            f"{result['file_count']} files, {result['bytes']} bytes"
        )
    except (
        PreparationError,
        AssertionError,
        OSError,
        UnicodeError,
        ValueError,
    ) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
