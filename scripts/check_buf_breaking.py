#!/usr/bin/env python3
"""Run Buf breaking against the latest registered same-major release.

The current protobuf package is the compatibility line: ``ncp.v1`` must never be
compared with the intentionally incompatible ``ncp.v0`` releases.  The first
candidate on a new major therefore reports that no released same-major baseline
exists and performs no breaking comparison.  Once a release on that major is
registered, every later check selects the greatest registered release version on
the same package major and compares against its registered peeled commit.

Release rows come only from ``released-baselines.v1.json`` after the ordinary
released-baseline verifier has bound each annotated tag ref, tag object, peeled
commit, fixed baseline path, and subtree.  Buf receives the immutable commit OID,
not a movable tag name or a network default branch.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import check_released_baselines as released


REPO = Path(__file__).resolve().parents[1]
REGISTRY = REPO / "conformance" / "baseline" / "released-baselines.v1.json"
PROTO_PATH = Path("proto/ncp.proto")
MAX_PROTO_BYTES = 4 * 1024 * 1024
U64_MAX = 18_446_744_073_709_551_615
_SEMVER_TAG_RE = re.compile(
    r"v(0|[1-9][0-9]{0,19})\."
    r"(0|[1-9][0-9]{0,19})\."
    r"(0|[1-9][0-9]{0,19})\Z",
    re.ASCII,
)
_PACKAGE_DECL_RE = re.compile(
    r"^[ \t]*package[ \t]+([^;\r\n]+?)[ \t]*;", re.MULTILINE | re.ASCII
)
_PACKAGE_NAME_RE = re.compile(r"ncp\.v(0|[1-9][0-9]{0,19})\Z", re.ASCII)


class GateError(ValueError):
    """A fail-closed compatibility-gate input error."""


@dataclass(frozen=True)
class Baseline:
    tag: str
    version: tuple[int, int, int]
    package: str
    peeled_commit: str


@dataclass(frozen=True)
class Plan:
    current_package: str
    current_major: int
    baseline: Baseline | None


def _canonical_component(raw: str, label: str) -> int:
    try:
        value = int(raw)
    except ValueError as exc:
        raise GateError(f"{label} is not canonical ASCII decimal: {raw!r}") from exc
    if value > U64_MAX:
        raise GateError(f"{label} exceeds the NCP u64 version bound: {raw!r}")
    return value


def _tag_version(tag: str) -> tuple[int, int, int]:
    match = _SEMVER_TAG_RE.fullmatch(tag)
    if match is None:
        raise GateError(
            f"registered release tag must be canonical vMAJOR.MINOR.PATCH: {tag!r}"
        )
    major, minor, patch = (
        _canonical_component(component, f"release tag {tag!r} component")
        for component in match.groups()
    )
    return major, minor, patch


def _package(text: str, label: str) -> tuple[str, int]:
    declarations = _PACKAGE_DECL_RE.findall(text)
    if len(declarations) != 1:
        raise GateError(
            f"{label} must declare exactly one canonical package ncp.vMAJOR; "
            f"found {len(declarations)} package declarations"
        )
    package_name = declarations[0].strip()
    match = _PACKAGE_NAME_RE.fullmatch(package_name)
    if match is None:
        raise GateError(
            f"{label} package must be canonical ncp.vMAJOR; got {package_name!r}"
        )
    major = _canonical_component(match.group(1), f"{label} package major")
    return f"ncp.v{major}", major


def _read_regular(path: Path, label: str) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise GateError(
            f"cannot open {label} as a regular non-symlink file: {exc}"
        ) from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise GateError(f"{label} is not a regular file")
        if before.st_size > MAX_PROTO_BYTES:
            raise GateError(
                f"{label} exceeds the {MAX_PROTO_BYTES}-byte compatibility-gate limit"
            )
        chunks: list[bytes] = []
        size = 0
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_PROTO_BYTES:
                raise GateError(
                    f"{label} changed beyond the {MAX_PROTO_BYTES}-byte limit while read"
                )
            chunks.append(chunk)
        after = os.fstat(descriptor)
        identity_before = (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_mode,
        )
        identity_after = (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_mode,
        )
        if size != before.st_size or identity_before != identity_after:
            raise GateError(f"{label} changed while being read")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _decode_proto(payload: bytes, label: str) -> str:
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise GateError(f"{label} is not UTF-8: {exc}") from exc


def _current_package(repo: Path) -> tuple[str, int]:
    label = PROTO_PATH.as_posix()
    payload = _read_regular(repo / PROTO_PATH, label)
    return _package(_decode_proto(payload, label), label)


def _tagged_proto(repo: Path, release: dict[str, str]) -> bytes:
    tag = release["tag"]
    commit = release["peeled_commit"]
    result = released._git(
        repo, "ls-tree", "-z", commit, "--", PROTO_PATH.as_posix()
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise GateError(
            f"{tag}: cannot inspect tagged {PROTO_PATH.as_posix()}: {detail}"
        )
    records = [record for record in result.stdout.split(b"\0") if record]
    if len(records) != 1:
        raise GateError(
            f"{tag}: tagged {PROTO_PATH.as_posix()} is missing or moved "
            f"(found {len(records)} exact entries)"
        )
    try:
        metadata, raw_path = records[0].split(b"\t", 1)
        raw_mode, raw_kind, raw_oid = metadata.split(b" ", 2)
        mode = raw_mode.decode("ascii")
        kind = raw_kind.decode("ascii")
        oid = raw_oid.decode("ascii")
        tree_path = raw_path.decode("utf-8")
    except (ValueError, UnicodeDecodeError) as exc:
        raise GateError(f"{tag}: malformed tagged proto tree entry: {exc}") from exc
    if tree_path != PROTO_PATH.as_posix() or kind != "blob" or mode not in {
        "100644",
        "100755",
    }:
        raise GateError(
            f"{tag}: tagged proto must be one regular file at {PROTO_PATH.as_posix()}; "
            f"got path={tree_path!r}, kind={kind!r}, mode={mode!r}"
        )
    size_text, size_error = released._git_value(repo, "cat-file", "-s", oid)
    if (
        size_error
        or size_text is None
        or not size_text.isascii()
        or not size_text.isdigit()
    ):
        raise GateError(
            f"{tag}: cannot read tagged proto blob size: {size_error or size_text!r}"
        )
    size = int(size_text)
    if size > MAX_PROTO_BYTES:
        raise GateError(
            f"{tag}: tagged proto exceeds the {MAX_PROTO_BYTES}-byte gate limit"
        )
    payload = released._git(repo, "cat-file", "-p", oid)
    if payload.returncode != 0:
        detail = payload.stderr.decode("utf-8", errors="replace").strip()
        raise GateError(f"{tag}: cannot read tagged proto blob {oid}: {detail}")
    if len(payload.stdout) != size:
        raise GateError(
            f"{tag}: tagged proto size changed while read: expected {size}, "
            f"got {len(payload.stdout)}"
        )
    return payload.stdout


def _select_baseline(
    repo: Path, releases: list[dict[str, str]], current_major: int
) -> Baseline | None:
    candidates: list[Baseline] = []
    versions: list[tuple[int, int, int]] = []
    for release in releases:
        tag = release["tag"]
        version = _tag_version(tag)
        versions.append(version)
        payload = _tagged_proto(repo, release)
        package, package_major = _package(
            _decode_proto(payload, f"{tag}:{PROTO_PATH.as_posix()}"),
            f"{tag}:{PROTO_PATH.as_posix()}",
        )
        if package_major != version[0]:
            raise GateError(
                f"{tag}: tag major {version[0]} disagrees with tagged package {package}"
            )
        if package_major == current_major:
            candidates.append(
                Baseline(tag, version, package, release["peeled_commit"])
            )
    if versions != sorted(versions) or len(set(versions)) != len(versions):
        raise GateError(
            "released-baseline registry tags must be unique and strictly increasing "
            "by canonical release version"
        )
    return max(candidates, key=lambda candidate: candidate.version, default=None)


def resolve_plan(
    repo: Path = REPO,
    registry_path: Path = REGISTRY,
    expected_releases: tuple[str, ...] = released.EXPECTED_RELEASES,
) -> Plan:
    rows, problems = released.inspect_registry(repo, registry_path, expected_releases)
    if problems:
        raise GateError(
            "released-baseline registry/tag integrity failed:\n  - "
            + "\n  - ".join(problems)
        )
    current_package, current_major = _current_package(repo)
    baseline = _select_baseline(repo, rows, current_major)
    return Plan(current_package, current_major, baseline)


def _against_input(repo: Path, baseline: Baseline) -> str:
    common_dir, error = released._git_value(repo, "rev-parse", "--git-common-dir")
    if error or common_dir is None:
        raise GateError(f"cannot locate the verified Git object database: {error}")
    git_dir = Path(common_dir)
    if not git_dir.is_absolute():
        git_dir = repo / git_dir
    try:
        mode = git_dir.lstat().st_mode
    except OSError as exc:
        raise GateError(f"cannot inspect Git common directory {git_dir}: {exc}") from exc
    if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
        raise GateError(
            f"Git common directory must be a real non-symlink directory: {git_dir}"
        )
    return f"{git_dir.resolve().as_uri()}#commit={baseline.peeled_commit},subdir=."


def _no_baseline_message(plan: Plan) -> str:
    return (
        "PASS: Buf breaking has no registered released same-major baseline for "
        f"{plan.current_package}. This is the initial v{plan.current_major} "
        "compatibility line, so no cross-major comparison is run; registered "
        "older-major releases are intentionally incompatible."
    )


def _buf_breaking_command(repo: Path, baseline: Baseline) -> list[str]:
    return ["buf", "breaking", ".", "--against", _against_input(repo, baseline)]


def check(repo: Path = REPO, registry_path: Path = REGISTRY) -> int:
    try:
        plan = resolve_plan(repo, registry_path)
        try:
            build = subprocess.run(
                ["buf", "build", "."],
                cwd=repo,
                check=False,
                env=released._git_env(),
            )
        except OSError as exc:
            raise GateError(f"cannot execute required Buf build gate: {exc}") from exc
        if build.returncode != 0:
            print("BUF BUILD FAILURE before compatibility selection.", file=sys.stderr)
            return build.returncode or 1
        final_package, final_major = _current_package(repo)
        if (final_package, final_major) != (plan.current_package, plan.current_major):
            raise GateError("current proto package changed while Buf build was running")
        if plan.baseline is None:
            print(_no_baseline_message(plan))
            return 0
        print(
            "BUF BREAKING: comparing current "
            f"{plan.current_package} against latest registered same-major release "
            f"{plan.baseline.tag} at peeled commit {plan.baseline.peeled_commit}."
        )
        try:
            result = subprocess.run(
                _buf_breaking_command(repo, plan.baseline),
                cwd=repo,
                check=False,
                env=released._git_env(),
            )
        except OSError as exc:
            raise GateError(f"cannot execute required Buf breaking gate: {exc}") from exc
        if result.returncode != 0:
            print(
                f"BUF BREAKING FAILURE against {plan.baseline.tag} "
                f"({plan.baseline.peeled_commit}).",
                file=sys.stderr,
            )
            return result.returncode or 1
        # A concurrent package-line edit must not turn a comparison selected for
        # one major into evidence for another.
        final_package, final_major = _current_package(repo)
        if (final_package, final_major) != (plan.current_package, plan.current_major):
            raise GateError(
                "current proto package changed while the Buf comparison was running"
            )
        print(
            f"PASS: Buf WIRE/WIRE_JSON compatibility against {plan.baseline.tag} "
            "from the verified released-baseline registry."
        )
        return 0
    except GateError as exc:
        print(f"BUF BREAKING GATE ERROR: {exc}", file=sys.stderr)
        return 1


def _self_test() -> int:
    fixed_env = released._git_env()
    fixed_env.update(
        {
            "GIT_AUTHOR_NAME": "NCP Buf gate self-test",
            "GIT_AUTHOR_EMAIL": "ncp-buf-self-test@example.invalid",
            "GIT_COMMITTER_NAME": "NCP Buf gate self-test",
            "GIT_COMMITTER_EMAIL": "ncp-buf-self-test@example.invalid",
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

    def write_registry(path: Path, rows: list[dict[str, str]]) -> None:
        data: dict[str, Any] = {
            "schema": released.SCHEMA,
            "git_object_format": "sha1",
            "releases": rows,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    def make_repo(
        root: Path, specs: list[tuple[str, str, str]]
    ) -> tuple[Path, Path, list[dict[str, str]]]:
        repo = root
        repo.mkdir()
        run(repo, "init", "-q", "--object-format=sha1")
        (repo / "buf.yaml").write_text(
            "version: v2\n"
            "modules:\n"
            "  - path: proto\n"
            "breaking:\n"
            "  use:\n"
            "    - WIRE_JSON\n"
            "    - WIRE\n",
            encoding="utf-8",
        )
        rows: list[dict[str, str]] = []
        for tag, package, proto_path in specs:
            proto = repo / proto_path
            proto.parent.mkdir(parents=True, exist_ok=True)
            proto.write_text(
                f'syntax = "proto3";\npackage {package};\n'
                "message Fixture { string retained = 1; }\n",
                encoding="utf-8",
            )
            baseline_path = repo / "conformance" / "baseline" / tag
            baseline_path.mkdir(parents=True)
            (baseline_path / "wire.txt").write_text(
                f"released {tag}\n", encoding="utf-8"
            )
            run(repo, "add", ".")
            run(repo, "commit", "-q", "-m", f"release fixture {tag}")
            run(repo, "tag", "-a", tag, "-m", f"annotated fixture {tag}")
            tag_object = run(repo, "rev-parse", f"{tag}^{{tag}}")
            peeled_commit = run(repo, "rev-parse", f"{tag}^{{commit}}")
            baseline_tree = run(
                repo,
                "rev-parse",
                f"{peeled_commit}:conformance/baseline/{tag}",
            )
            rows.append(
                {
                    "tag": tag,
                    "tag_object": tag_object,
                    "peeled_commit": peeled_commit,
                    "baseline_path": f"conformance/baseline/{tag}",
                    "baseline_tree": baseline_tree,
                }
            )
        registry = repo / "conformance" / "baseline" / "released-baselines.v1.json"
        write_registry(registry, rows)
        return repo, registry, rows

    def expect_error(action, fragment: str) -> None:
        try:
            action()
        except GateError as exc:
            if fragment not in str(exc):
                raise AssertionError(
                    f"expected error containing {fragment!r}; got {exc!r}"
                ) from exc
            return
        raise AssertionError(f"hostile case unexpectedly passed; wanted {fragment!r}")

    with tempfile.TemporaryDirectory(prefix="ncp-buf-breaking-") as directory:
        root = Path(directory)
        repo, registry, rows = make_repo(
            root / "valid",
            [
                ("v0.1.0", "ncp.v0", "proto/ncp.proto"),
                ("v1.0.0", "ncp.v1", "proto/ncp.proto"),
                ("v1.2.0", "ncp.v1", "proto/ncp.proto"),
            ],
        )
        expected = tuple(row["tag"] for row in rows)
        plan = resolve_plan(repo, registry, expected)
        if plan.current_package != "ncp.v1" or plan.baseline is None:
            raise AssertionError(f"valid same-major plan was not resolved: {plan!r}")
        if plan.baseline.tag != "v1.2.0":
            raise AssertionError(f"latest same-major release was not selected: {plan!r}")
        target = _against_input(repo, plan.baseline)
        if f"#commit={rows[-1]['peeled_commit']},subdir=." not in target:
            raise AssertionError(
                f"Buf target is not bound to the peeled commit: {target}"
            )
        try:
            actual_buf = subprocess.run(
                _buf_breaking_command(repo, plan.baseline),
                cwd=repo,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=fixed_env,
            )
        except OSError as exc:
            raise AssertionError(f"self-test cannot execute required Buf: {exc}") from exc
        if actual_buf.returncode != 0:
            raise AssertionError(
                "same-major peeled-commit Buf comparison failed: "
                + actual_buf.stderr.decode("utf-8", errors="replace")
            )
        valid_proto = (repo / PROTO_PATH).read_bytes()
        (repo / PROTO_PATH).write_text(
            'syntax = "proto3";\npackage ncp.v1;\nmessage Fixture {}\n',
            encoding="utf-8",
        )
        hostile_buf = subprocess.run(
            _buf_breaking_command(repo, plan.baseline),
            cwd=repo,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=fixed_env,
        )
        if hostile_buf.returncode == 0:
            raise AssertionError(
                "Buf comparison accepted removal of a same-major released field"
            )
        (repo / PROTO_PATH).write_bytes(valid_proto)

        write_registry(registry, rows[:1])
        initial = resolve_plan(repo, registry, ("v0.1.0",))
        if initial.current_package != "ncp.v1" or initial.baseline is not None:
            raise AssertionError(
                f"initial v1 must explicitly have no same-major baseline: {initial!r}"
            )
        report = _no_baseline_message(initial)
        if "no registered released same-major baseline" not in report or (
            "initial v1 compatibility line" not in report
        ):
            raise AssertionError(f"initial-v1 report is not explicit: {report!r}")
        write_registry(registry, rows)

        moved_registry = registry.with_name("released-baselines.moved.json")
        registry.rename(moved_registry)
        expect_error(
            lambda: resolve_plan(repo, registry, expected), "registry is missing"
        )
        moved_registry.rename(registry)

        original_registry = registry.read_text(encoding="utf-8")
        registry.write_text(
            '{"schema":"ncp.released-baseline-registry.v1",'
            '"schema":"duplicate","git_object_format":"sha1","releases":[]}\n',
            encoding="utf-8",
        )
        expect_error(
            lambda: resolve_plan(repo, registry, expected), "duplicate JSON key"
        )
        registry.write_text(original_registry, encoding="utf-8")

        run(
            repo,
            "update-ref",
            f"refs/tags/{rows[-1]['tag']}",
            rows[-1]["peeled_commit"],
        )
        expect_error(lambda: resolve_plan(repo, registry, expected), "tag ref moved")
        run(
            repo,
            "update-ref",
            f"refs/tags/{rows[-1]['tag']}",
            rows[-1]["tag_object"],
        )

        reversed_rows = list(reversed(rows))
        write_registry(registry, reversed_rows)
        expect_error(
            lambda: resolve_plan(
                repo, registry, tuple(row["tag"] for row in reversed_rows)
            ),
            "strictly increasing",
        )
        write_registry(registry, rows)

        current_proto = repo / PROTO_PATH
        original_proto = current_proto.read_bytes()
        current_proto.write_text(
            'syntax = "proto3";\npackage wrong.v1;\npackage ncp.v1;\n',
            encoding="utf-8",
        )
        expect_error(lambda: resolve_plan(repo, registry, expected), "exactly one")
        current_proto.write_bytes(original_proto)
        current_proto.unlink()
        current_proto.symlink_to(repo / "outside.proto")
        expect_error(lambda: resolve_plan(repo, registry, expected), "non-symlink")
        current_proto.unlink()
        current_proto.write_bytes(original_proto)

        mismatch_repo, mismatch_registry, mismatch_rows = make_repo(
            root / "mismatch",
            [("v2.0.0", "ncp.v1", "proto/ncp.proto")],
        )
        expect_error(
            lambda: resolve_plan(
                mismatch_repo, mismatch_registry, (mismatch_rows[0]["tag"],)
            ),
            "disagrees with tagged package",
        )

        moved_repo, moved_proto_registry, moved_rows = make_repo(
            root / "moved-proto",
            [("v1.0.0", "ncp.v1", "proto/moved.proto")],
        )
        live_proto = moved_repo / PROTO_PATH
        live_proto.parent.mkdir(parents=True, exist_ok=True)
        live_proto.write_text('syntax = "proto3";\npackage ncp.v1;\n', encoding="utf-8")
        expect_error(
            lambda: resolve_plan(
                moved_repo, moved_proto_registry, (moved_rows[0]["tag"],)
            ),
            "missing or moved",
        )

    print(
        "OK Buf-breaking self-test: initial-v1 no-baseline reporting, latest same-major "
        "selection, real peeled-commit comparison, malformed/moved registry and tags, "
        "ordering, package mismatch, moved proto, duplicate package, and symlink inputs "
        "fail closed"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Buf breaking gate against the latest verified same-major release"
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run deterministic valid/hostile synthetic-repository regressions",
    )
    args = parser.parse_args()
    if args.self_test:
        return _self_test()
    return check()


if __name__ == "__main__":
    raise SystemExit(main())
