#!/usr/bin/env python3
"""Prove that every registered released baseline still matches its annotated tag.

The normal wire-baseline gate compares HEAD with one compatibility anchor.  This
gate instead protects historical release evidence: it binds each release tag
object, the commit named by that annotated tag, and the baseline subtree stored in
that commit.  It then compares the checked-out baseline path to the tag tree by
Git mode and blob object ID.  Normal verification invokes only read-only Git
commands and never updates the index, refs, objects, or worktree.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any


REPO = Path(__file__).resolve().parents[1]
REGISTRY = REPO / "conformance" / "baseline" / "released-baselines.v1.json"
EXPECTED_RELEASES = ("v0.5.0", "v0.6.0", "v0.7.0", "v0.8.0")
SCHEMA = "ncp.released-baseline-registry.v1"
OID_RE = re.compile(r"[0-9a-f]+\Z", re.ASCII)
GIT_LOCATION_ENV = {
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_COMMON_DIR",
    "GIT_DIR",
    "GIT_INDEX_FILE",
    "GIT_NAMESPACE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_SHALLOW_FILE",
    "GIT_WORK_TREE",
}


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _strict_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise ValueError(f"{label} keys differ: missing={missing}, extra={extra}")


def _load_registry(
    path: Path, expected_releases: tuple[str, ...]
) -> tuple[str, list[dict[str, str]]]:
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError as exc:
        raise ValueError(f"registry is missing: {path}") from exc
    except OSError as exc:
        raise ValueError(f"cannot inspect registry {path}: {exc}") from exc
    if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
        raise ValueError(f"registry must be a regular non-symlink file: {path}")
    try:
        raw = json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicate_pairs
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read registry {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError("registry root must be an object")
    _strict_keys(raw, {"schema", "git_object_format", "releases"}, "registry")
    if raw["schema"] != SCHEMA:
        raise ValueError(f"registry schema must be {SCHEMA!r}")
    object_format = raw["git_object_format"]
    if not isinstance(object_format, str) or object_format not in {"sha1", "sha256"}:
        raise ValueError("git_object_format must be 'sha1' or 'sha256'")
    oid_length = 40 if object_format == "sha1" else 64
    releases = raw["releases"]
    if not isinstance(releases, list):
        raise ValueError("registry releases must be an array")
    tags = [item.get("tag") if isinstance(item, dict) else None for item in releases]
    if tags != list(expected_releases):
        raise ValueError(
            "registry must contain the exact ordered released-tag set "
            f"{list(expected_releases)!r}; got {tags!r}"
        )

    checked: list[dict[str, str]] = []
    item_keys = {
        "tag",
        "tag_object",
        "peeled_commit",
        "baseline_path",
        "baseline_tree",
    }
    for index, item in enumerate(releases):
        if not isinstance(item, dict):
            raise ValueError(f"release[{index}] must be an object")
        _strict_keys(item, item_keys, f"release[{index}]")
        tag = item["tag"]
        expected_path = f"conformance/baseline/{tag}"
        if item["baseline_path"] != expected_path:
            raise ValueError(
                f"release[{index}].baseline_path must be {expected_path!r}; "
                f"got {item['baseline_path']!r}"
            )
        parts = PurePosixPath(item["baseline_path"]).parts
        if not parts or PurePosixPath(item["baseline_path"]).is_absolute() or ".." in parts:
            raise ValueError(f"release[{index}] has unsafe baseline_path")
        for field in ("tag_object", "peeled_commit", "baseline_tree"):
            oid = item[field]
            if (
                not isinstance(oid, str)
                or len(oid) != oid_length
                or not OID_RE.fullmatch(oid)
            ):
                raise ValueError(
                    f"release[{index}].{field} must be one lowercase {object_format} OID"
                )
        checked.append({key: str(item[key]) for key in item_keys})
    return object_format, checked


def _git_env() -> dict[str, str]:
    env = os.environ.copy()
    for variable in GIT_LOCATION_ENV:
        env.pop(variable, None)
    env.update({"GIT_NO_REPLACE_OBJECTS": "1", "LC_ALL": "C"})
    return env


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=_git_env(),
    )


def _git_value(repo: Path, *args: str) -> tuple[str | None, str | None]:
    result = _git(repo, *args)
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        return None, detail or f"git {' '.join(args)} exited {result.returncode}"
    try:
        value = result.stdout.decode("ascii").strip()
    except UnicodeDecodeError as exc:
        return None, f"git {' '.join(args)} returned non-ASCII output: {exc}"
    return value, None


def _tag_headers(payload: bytes) -> dict[str, str]:
    header_block = payload.split(b"\n\n", 1)[0]
    headers: dict[str, str] = {}
    for raw_line in header_block.splitlines():
        if b" " not in raw_line:
            raise ValueError(f"malformed annotated-tag header: {raw_line!r}")
        raw_key, raw_value = raw_line.split(b" ", 1)
        try:
            key = raw_key.decode("ascii")
            value = raw_value.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(f"invalid annotated-tag header encoding: {exc}") from exc
        if key in headers:
            raise ValueError(f"duplicate annotated-tag header {key!r}")
        headers[key] = value
    return headers


def _tag_tree_entries(repo: Path, tree_oid: str) -> tuple[dict[bytes, tuple[str, str]], list[str]]:
    result = _git(repo, "ls-tree", "-rz", "-r", tree_oid)
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        return {}, [f"cannot enumerate baseline tree {tree_oid}: {detail}"]
    entries: dict[bytes, tuple[str, str]] = {}
    problems: list[str] = []
    for record in result.stdout.split(b"\0"):
        if not record:
            continue
        try:
            metadata, path = record.split(b"\t", 1)
            mode_raw, kind_raw, oid_raw = metadata.split(b" ", 2)
            mode = mode_raw.decode("ascii")
            kind = kind_raw.decode("ascii")
            oid = oid_raw.decode("ascii")
        except (ValueError, UnicodeDecodeError) as exc:
            problems.append(f"malformed git tree record {record!r}: {exc}")
            continue
        display = os.fsdecode(path)
        if path in entries:
            problems.append(f"tag tree has duplicate path {display!r}")
            continue
        if kind != "blob" or mode not in {"100644", "100755"}:
            problems.append(
                f"tag tree entry {display!r} is forbidden kind/mode {kind}/{mode}; "
                "released baselines may contain only regular files"
            )
        entries[path] = (mode, oid)
    return entries, problems


def _blob_oid(path: str, object_format: str) -> tuple[str | None, str | None]:
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        return None, f"cannot open regular file without following symlinks: {exc}"
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            return None, "entry changed to a non-regular file while being checked"
        digest = hashlib.new(object_format)
        digest.update(f"blob {before.st_size}\0".encode("ascii"))
        read_bytes = 0
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            read_bytes += len(chunk)
            digest.update(chunk)
        after = os.fstat(descriptor)
        stable = (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_mode,
        ) == (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_mode,
        )
        if read_bytes != before.st_size or not stable:
            return None, "file changed while being checked"
        return digest.hexdigest(), None
    finally:
        os.close(descriptor)


def _local_tree_entries(
    repo: Path, baseline_path: str, object_format: str
) -> tuple[dict[bytes, tuple[str, str]], list[str]]:
    root = repo.joinpath(*PurePosixPath(baseline_path).parts)
    problems: list[str] = []
    current = repo
    for part in PurePosixPath(baseline_path).parts:
        current /= part
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError:
            problems.append(f"baseline path is missing: {baseline_path}")
            return {}, problems
        except OSError as exc:
            problems.append(
                f"cannot inspect baseline path component "
                f"{current.relative_to(repo).as_posix()}: {exc}"
            )
            return {}, problems
        if stat.S_ISLNK(mode):
            problems.append(
                f"baseline path component is a forbidden symlink: "
                f"{current.relative_to(repo).as_posix()}"
            )
            return {}, problems
    if not root.is_dir():
        problems.append(f"baseline path is not a directory: {baseline_path}")
        return {}, problems

    entries: dict[bytes, tuple[str, str]] = {}

    def visit(directory: Path, relative: Path) -> None:
        try:
            with os.scandir(directory) as iterator:
                children = sorted(iterator, key=lambda item: os.fsencode(item.name))
        except OSError as exc:
            problems.append(f"cannot enumerate {directory.relative_to(repo)}: {exc}")
            return
        for child in children:
            child_relative = relative / child.name
            display = child_relative.as_posix()
            key = os.fsencode(display)
            try:
                child_mode = child.stat(follow_symlinks=False).st_mode
            except OSError as exc:
                problems.append(f"cannot stat {baseline_path}/{display}: {exc}")
                continue
            if stat.S_ISLNK(child_mode):
                problems.append(f"forbidden symlink: {baseline_path}/{display}")
            elif stat.S_ISDIR(child_mode):
                visit(Path(child.path), child_relative)
            elif stat.S_ISREG(child_mode):
                git_mode = "100755" if child_mode & 0o111 else "100644"
                oid, error = _blob_oid(child.path, object_format)
                if error:
                    problems.append(f"{baseline_path}/{display}: {error}")
                elif key in entries:
                    problems.append(f"duplicate local path: {baseline_path}/{display}")
                else:
                    entries[key] = (git_mode, oid or "")
            else:
                problems.append(f"forbidden non-regular entry: {baseline_path}/{display}")

    visit(root, Path())
    return entries, problems


def _compare_entries(
    tag: str,
    expected: dict[bytes, tuple[str, str]],
    actual: dict[bytes, tuple[str, str]],
) -> list[str]:
    problems: list[str] = []
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    changed = sorted(
        path
        for path in set(expected) & set(actual)
        if expected[path] != actual[path]
    )
    if missing:
        problems.append(f"{tag}: missing files: {[os.fsdecode(path) for path in missing]!r}")
    if extra:
        problems.append(f"{tag}: extra files: {[os.fsdecode(path) for path in extra]!r}")
    if changed:
        details = [
            {
                "path": os.fsdecode(path),
                "tag": f"{expected[path][0]} {expected[path][1]}",
                "worktree": f"{actual[path][0]} {actual[path][1]}",
            }
            for path in changed
        ]
        problems.append(f"{tag}: changed files (mode or bytes): {details!r}")
    return problems


def _verify_loaded(
    repo: Path, object_format: str, releases: list[dict[str, str]]
) -> list[str]:
    problems: list[str] = []
    top, error = _git_value(repo, "rev-parse", "--show-toplevel")
    if error or top is None:
        return [f"cannot identify repository root: {error}"]
    if Path(top).resolve() != repo.resolve():
        return [f"expected Git root {repo.resolve()}, got {Path(top).resolve()}"]
    actual_format, error = _git_value(repo, "rev-parse", "--show-object-format")
    if error or actual_format != object_format:
        return [
            f"repository object format {actual_format!r} does not match registry "
            f"{object_format!r}: {error or ''}".rstrip()
        ]

    for release in releases:
        tag = release["tag"]
        tag_object = release["tag_object"]
        peeled_commit = release["peeled_commit"]
        baseline_path = release["baseline_path"]
        baseline_tree = release["baseline_tree"]
        ref = f"refs/tags/{tag}"

        live_object, ref_error = _git_value(repo, "show-ref", "--verify", "--hash", ref)
        if ref_error or not live_object:
            problems.append(f"{tag}: annotated tag ref is missing: {ref_error}")
        else:
            if live_object != tag_object:
                problems.append(
                    f"{tag}: tag ref moved: registry={tag_object}, actual={live_object}"
                )
            live_type, type_error = _git_value(repo, "cat-file", "-t", live_object)
            if type_error or live_type != "tag":
                problems.append(
                    f"{tag}: tag ref is not annotated (lightweight or invalid): "
                    f"type={live_type!r}, error={type_error!r}"
                )
            live_peeled, peel_error = _git_value(repo, "rev-parse", "--verify", f"{ref}^{{commit}}")
            if peel_error or live_peeled != peeled_commit:
                problems.append(
                    f"{tag}: live tag peels to {live_peeled!r}, expected {peeled_commit}; "
                    f"{peel_error or ''}".rstrip()
                )

        registered_type, type_error = _git_value(repo, "cat-file", "-t", tag_object)
        if type_error or registered_type != "tag":
            problems.append(
                f"{tag}: registered tag object {tag_object} is unavailable or not a tag: "
                f"type={registered_type!r}, error={type_error!r}"
            )
            continue
        payload = _git(repo, "cat-file", "-p", tag_object)
        if payload.returncode != 0:
            problems.append(
                f"{tag}: cannot read registered annotated-tag object {tag_object}: "
                f"{payload.stderr.decode('utf-8', errors='replace').strip()}"
            )
            continue
        try:
            headers = _tag_headers(payload.stdout)
        except ValueError as exc:
            problems.append(f"{tag}: invalid annotated-tag object: {exc}")
            continue
        if headers.get("tag") != tag:
            problems.append(
                f"{tag}: annotated-tag object's embedded name is {headers.get('tag')!r}"
            )
        if headers.get("type") != "commit" or headers.get("object") != peeled_commit:
            problems.append(
                f"{tag}: annotated tag must directly name registered commit {peeled_commit}; "
                f"headers type={headers.get('type')!r}, object={headers.get('object')!r}"
            )
            continue
        commit_type, commit_error = _git_value(repo, "cat-file", "-t", peeled_commit)
        if commit_error or commit_type != "commit":
            problems.append(
                f"{tag}: registered peeled object is unavailable or not a commit: "
                f"type={commit_type!r}, error={commit_error!r}"
            )
            continue
        tag_tree, tree_error = _git_value(
            repo, "rev-parse", "--verify", f"{peeled_commit}:{baseline_path}"
        )
        if tree_error or not tag_tree:
            problems.append(
                f"{tag}: baseline path is missing or moved in the tagged commit: "
                f"{baseline_path}: {tree_error}"
            )
            continue
        tree_type, tree_type_error = _git_value(repo, "cat-file", "-t", tag_tree)
        if tree_type_error or tree_type != "tree":
            problems.append(
                f"{tag}: tagged baseline path is not a tree: "
                f"type={tree_type!r}, error={tree_type_error!r}"
            )
            continue
        if tag_tree != baseline_tree:
            problems.append(
                f"{tag}: baseline tree identity differs: registry={baseline_tree}, "
                f"tag={tag_tree}"
            )

        expected, expected_problems = _tag_tree_entries(repo, tag_tree)
        actual, actual_problems = _local_tree_entries(repo, baseline_path, object_format)
        problems.extend(f"{tag}: {problem}" for problem in expected_problems)
        problems.extend(f"{tag}: {problem}" for problem in actual_problems)
        problems.extend(_compare_entries(tag, expected, actual))
    return problems


def inspect_registry(
    repo: Path = REPO,
    registry_path: Path = REGISTRY,
    expected_releases: tuple[str, ...] = EXPECTED_RELEASES,
) -> tuple[list[dict[str, str]], list[str]]:
    """Parse and verify one immutable-registry snapshot.

    Consumers such as the Buf compatibility gate receive the exact release rows
    that were checked, rather than reparsing the registry under a weaker policy.
    Rows are returned only for diagnostic use when verification fails; callers
    must treat every non-empty problem list as fatal.
    """
    try:
        object_format, releases = _load_registry(registry_path, expected_releases)
    except ValueError as exc:
        return [], [str(exc)]
    return releases, _verify_loaded(repo, object_format, releases)


def verify(
    repo: Path = REPO,
    registry_path: Path = REGISTRY,
    expected_releases: tuple[str, ...] = EXPECTED_RELEASES,
) -> list[str]:
    return inspect_registry(repo, registry_path, expected_releases)[1]


def _write_registry(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _self_test() -> int:
    fixed_env = _git_env()
    fixed_env.update(
        {
            "GIT_AUTHOR_NAME": "NCP baseline self-test",
            "GIT_AUTHOR_EMAIL": "ncp-self-test@example.invalid",
            "GIT_COMMITTER_NAME": "NCP baseline self-test",
            "GIT_COMMITTER_EMAIL": "ncp-self-test@example.invalid",
            "GIT_AUTHOR_DATE": "2000-01-01T00:00:00+0000",
            "GIT_COMMITTER_DATE": "2000-01-01T00:00:00+0000",
            "LC_ALL": "C",
        }
    )

    def run(repo: Path, *args: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(repo), *args],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=fixed_env,
        )
        if result.returncode != 0:
            raise AssertionError(
                f"self-test git {' '.join(args)} failed: "
                f"{result.stderr.decode('utf-8', errors='replace')}"
            )
        return result.stdout.decode("ascii").strip()

    def assert_failure(problems: list[str], fragment: str) -> None:
        if not any(fragment in problem for problem in problems):
            raise AssertionError(
                f"expected failure containing {fragment!r}; got {problems!r}"
            )

    with tempfile.TemporaryDirectory(prefix="ncp-released-baselines-") as directory:
        repo = Path(directory)
        run(repo, "init", "-q", "--object-format=sha1")
        baseline = repo / "conformance" / "baseline" / "v0.1.0"
        baseline.mkdir(parents=True)
        artifact = baseline / "artifact.bin"
        artifact.write_bytes(b"released baseline\x00\xff\n")
        run(repo, "add", "conformance/baseline/v0.1.0/artifact.bin")
        run(repo, "commit", "-q", "-m", "release fixture")
        run(repo, "tag", "-a", "v0.1.0", "-m", "annotated release fixture")
        tag_object = run(repo, "rev-parse", "v0.1.0^{tag}")
        peeled_commit = run(repo, "rev-parse", "v0.1.0^{}")
        baseline_tree = run(repo, "rev-parse", f"{peeled_commit}:conformance/baseline/v0.1.0")
        registry_data: dict[str, Any] = {
            "schema": SCHEMA,
            "git_object_format": "sha1",
            "releases": [
                {
                    "tag": "v0.1.0",
                    "tag_object": tag_object,
                    "peeled_commit": peeled_commit,
                    "baseline_path": "conformance/baseline/v0.1.0",
                    "baseline_tree": baseline_tree,
                }
            ],
        }
        registry = repo / "conformance" / "baseline" / "released-baselines.v1.json"
        _write_registry(registry, registry_data)
        expected = ("v0.1.0",)
        if problems := verify(repo, registry, expected):
            raise AssertionError(f"valid released baseline failed: {problems!r}")

        original = artifact.read_bytes()
        artifact.write_bytes(b"changed")
        assert_failure(verify(repo, registry, expected), "changed files")
        artifact.write_bytes(original)

        artifact.unlink()
        assert_failure(verify(repo, registry, expected), "missing files")
        artifact.write_bytes(original)

        extra = baseline / "extra"
        extra.write_bytes(b"extra")
        assert_failure(verify(repo, registry, expected), "extra files")
        extra.unlink()

        artifact.chmod(0o755)
        assert_failure(verify(repo, registry, expected), "changed files")
        artifact.chmod(0o644)

        artifact.unlink()
        artifact.symlink_to(repo / "outside")
        assert_failure(verify(repo, registry, expected), "forbidden symlink")
        artifact.unlink()
        artifact.write_bytes(original)

        moved = baseline.with_name("v0.1.0-moved")
        baseline.rename(moved)
        assert_failure(verify(repo, registry, expected), "baseline path is missing")
        moved.rename(baseline)

        run(repo, "update-ref", "-d", "refs/tags/v0.1.0")
        assert_failure(verify(repo, registry, expected), "tag ref is missing")
        run(repo, "update-ref", "refs/tags/v0.1.0", tag_object)

        run(repo, "tag", "-a", "other-tag", "-m", "different annotated tag object")
        other_tag_object = run(repo, "rev-parse", "other-tag^{tag}")
        run(repo, "update-ref", "refs/tags/v0.1.0", other_tag_object)
        assert_failure(verify(repo, registry, expected), "tag ref moved")
        run(repo, "update-ref", "refs/tags/v0.1.0", tag_object)

        run(repo, "update-ref", "refs/tags/v0.1.0", peeled_commit)
        lightweight = verify(repo, registry, expected)
        assert_failure(lightweight, "tag ref moved")
        assert_failure(lightweight, "not annotated")
        run(repo, "update-ref", "refs/tags/v0.1.0", tag_object)

        wrong_tree = copy.deepcopy(registry_data)
        wrong_tree["releases"][0]["baseline_tree"] = "0" * 40
        _write_registry(registry, wrong_tree)
        assert_failure(verify(repo, registry, expected), "baseline tree identity differs")
        _write_registry(registry, registry_data)

        omitted = copy.deepcopy(registry_data)
        omitted["releases"] = []
        _write_registry(registry, omitted)
        assert_failure(verify(repo, registry, expected), "exact ordered released-tag set")
        _write_registry(registry, registry_data)

    print(
        "OK released-baseline self-test: exact bytes/modes/path set, symlinks, "
        "annotated tag refs, and registered object/tree identities fail closed"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only exact integrity gate for released frozen baselines."
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run deterministic mutations in a temporary synthetic Git repository",
    )
    args = parser.parse_args()
    if args.self_test:
        return _self_test()
    problems = verify()
    if problems:
        print("RELEASED BASELINE INTEGRITY FAILURE:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    print(
        "PASS: released baselines v0.5.0, v0.6.0, v0.7.0, and v0.8.0 "
        "exactly match their registered annotated-tag trees."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
