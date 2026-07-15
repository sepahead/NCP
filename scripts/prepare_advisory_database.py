#!/usr/bin/env python3
"""Prepare one disposable RustSec database at the evidence-pinned revision.

The destination must be a new external directory selected through
``NCP_ADVISORY_DB_PATH``. The script never rewrites the repository or a caller's
default Cargo advisory database.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "evidence" / "supply-chain" / "vulnerability-report.v1.json"
REVISION = re.compile(r"^[0-9a-f]{40}$")
EXPECTED_URL = "https://github.com/RustSec/advisory-db"
DATABASE_DIRECTORY = re.compile(r"^advisory-db-[0-9a-f]{16}$")


class PreparationError(ValueError):
    """The pinned advisory database could not be prepared safely."""


def _strict_json_object(raw: str, context: str) -> dict[str, Any]:
    """Decode one JSON object while rejecting duplicate keys at every depth."""

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise PreparationError(f"{context} contains duplicate JSON key {key!r}")
            value[key] = item
        return value

    def reject_non_finite(token: str) -> Any:
        raise PreparationError(f"{context} contains non-finite JSON number {token!r}")

    try:
        value = json.loads(
            raw,
            object_pairs_hook=reject_duplicates,
            parse_constant=reject_non_finite,
        )
    except (UnicodeError, json.JSONDecodeError) as error:
        raise PreparationError(f"cannot parse {context}: {error}") from error
    if not isinstance(value, dict):
        raise PreparationError(f"{context} must contain one JSON object")
    return value


def _run(command: list[str], *, cwd: Path = ROOT) -> bytes:
    try:
        process = subprocess.run(
            command,
            cwd=cwd,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as error:
        raise PreparationError(f"cannot execute {command[0]}: {error}") from error
    if process.returncode != 0:
        detail = process.stderr.decode("utf-8", "replace").strip()
        raise PreparationError(f"{' '.join(command)} failed: {detail}")
    return process.stdout


def _load_report(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise PreparationError(f"cannot parse {path}: {error}") from error
    return _strict_json_object(raw, "vulnerability report")


def _expected_revision(report: dict[str, Any]) -> str:
    database = report.get("advisory_database")
    if not isinstance(database, dict) or database.get("url") != EXPECTED_URL:
        raise PreparationError(
            "vulnerability report has an unexpected advisory database"
        )
    revision = database.get("revision")
    if not isinstance(revision, str) or REVISION.fullmatch(revision) is None:
        raise PreparationError("vulnerability report advisory revision is malformed")
    return revision


def _assert_plain_worktree(database: Path) -> None:
    for root, directories, files in os.walk(database, followlinks=False):
        root_path = Path(root)
        directories.sort()
        files.sort()
        for name in [*directories, *files]:
            path = root_path / name
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode) or not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
                raise PreparationError(
                    f"advisory database contains a link or special entry: {path}"
                )


def _assert_database(database: Path) -> None:
    if (
        not database.is_dir()
        or not (database / ".git").is_dir()
        or DATABASE_DIRECTORY.fullmatch(database.name) is None
    ):
        raise PreparationError("source advisory database has an unexpected layout")
    origins = (
        _run(
            ["git", "config", "--get-all", "remote.origin.url"],
            cwd=database,
        )
        .decode("utf-8", "strict")
        .splitlines()
    )
    if len(origins) != 1 or not origins[0]:
        raise PreparationError(
            "source advisory database must configure exactly one origin URL"
        )
    origin = origins[0]
    if origin.rstrip("/").removesuffix(".git") != EXPECTED_URL:
        raise PreparationError(f"unexpected advisory database origin {origin!r}")
    if _run(["git", "status", "--porcelain"], cwd=database):
        raise PreparationError("source advisory database is not clean")
    _assert_plain_worktree(database)


def prepare(destination: Path, revision: str, source_database: Path) -> Path:
    configured = os.environ.get("NCP_ADVISORY_DB_PATH")
    if configured is None or Path(configured).resolve() != destination:
        raise PreparationError(
            "destination must equal the absolute NCP_ADVISORY_DB_PATH"
        )
    if destination == ROOT or ROOT in destination.parents:
        raise PreparationError(
            "advisory database destination must be outside the repository"
        )
    if destination.exists() and any(destination.iterdir()):
        raise PreparationError("advisory database destination must be new or empty")
    source_database = source_database.resolve()
    if (
        source_database == destination
        or destination in source_database.parents
        or source_database in destination.parents
    ):
        raise PreparationError("source and destination advisory databases overlap")
    _assert_database(source_database)
    destination.mkdir(parents=True, exist_ok=True)
    database = destination / source_database.name
    _run(
        [
            "git",
            "clone",
            "--local",
            "--no-hardlinks",
            "--no-checkout",
            str(source_database),
            str(database),
        ]
    )
    _run(["git", "remote", "set-url", "origin", EXPECTED_URL], cwd=database)
    probe = subprocess.run(
        ["git", "cat-file", "-e", f"{revision}^{{commit}}"],
        cwd=database,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if probe.returncode != 0:
        _run(["git", "fetch", "--no-tags", "origin", revision], cwd=database)
    else:
        # Refresh FETCH_HEAD from the already authenticated/current local clone.
        # cargo-deny consults this metadata even during --disable-fetch replay.
        _run(
            ["git", "fetch", "--no-tags", str(source_database), revision],
            cwd=database,
        )
    _run(["git", "checkout", "--detach", revision], cwd=database)
    head = (
        _run(["git", "rev-parse", "--verify", "HEAD^{commit}"], cwd=database)
        .decode("ascii", "strict")
        .strip()
    )
    if head != revision:
        raise PreparationError(
            "prepared advisory database revision differs from evidence"
        )
    _assert_database(database)
    return database


def _self_test() -> None:
    valid = "a" * 40
    if REVISION.fullmatch(valid) is None:
        raise AssertionError("valid advisory revision rejected")
    for invalid in ("", "A" * 40, "a" * 39, "g" * 40):
        if REVISION.fullmatch(invalid) is not None:
            raise AssertionError(f"invalid advisory revision passed: {invalid!r}")
    if (
        _expected_revision(
            {"advisory_database": {"url": EXPECTED_URL, "revision": valid}}
        )
        != valid
    ):
        raise AssertionError("valid advisory report rejected")
    for ambiguous in (
        '{"advisory_database":{},"advisory_database":{}}',
        '{"advisory_database":{"revision":"a","revision":"b"}}',
        '{"dependency_count":-Infinity}',
    ):
        try:
            _strict_json_object(ambiguous, "hostile self-test report")
        except PreparationError:
            pass
        else:
            raise AssertionError("duplicate JSON key passed advisory report parsing")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--source-database", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        if args.self_test:
            if args.destination is not None or args.source_database is not None:
                raise PreparationError(
                    "--self-test cannot be combined with database options"
                )
            _self_test()
            print("OK advisory database preparer self-test")
            return 0
        if args.destination is None or args.source_database is None:
            raise PreparationError("--destination and --source-database are required")
        destination = args.destination.resolve()
        revision = _expected_revision(_load_report(REPORT))
        database = prepare(destination, revision, args.source_database.resolve())
        print(f"OK advisory database prepared at {revision}: {database}")
    except (PreparationError, AssertionError, OSError, UnicodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
