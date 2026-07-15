#!/usr/bin/env python3
"""Generate the 21-column max-effort file-review ledger from immutable Git bytes.

Unlike the helper supplied with the external handoff, this implementation reads
blobs from an exact commit, records Git object and SHA-256 identities, never follows
symlinks, emits the mandated columns in their mandated order, and distinguishes an
internal AI-assisted inspection from independent release review.  Mechanical
classification and a complete row count are not release certification.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = "ef357d20692f707e185495dcfd16b16556fec264"
DEFAULT_OUTPUT = ROOT / "docs" / "handoff" / "max-effort-file-review.v2.csv"
DEFAULT_MANIFEST = ROOT / "docs" / "handoff" / "max-effort-file-review-manifest.v2.json"
DEFAULT_REVIEW_STATUS = "INTERNAL_AI_REVIEW_COMPLETE_WITH_OPEN_FINDINGS"
DEFAULT_COMPLETED_AT = "2026-07-15T12:30:58Z"
SOURCE_ID = re.compile(r"^[0-9a-f]{40}$")
REVIEWERS = (
    "/root/cross_repo_audit",
    "/root/handoff_audit",
    "/root/repo_gap_audit",
)
REVIEW_STATUSES = {
    "REVIEW_ASSIGNED",
    "INTERNAL_AI_REVIEW_COMPLETE_WITH_OPEN_FINDINGS",
}
FIELDNAMES = (
    "path",
    "git_blob_id",
    "sha256",
    "bytes",
    "lines",
    "language",
    "generated",
    "generator",
    "public_surface",
    "security_critical",
    "science_critical",
    "authority_critical",
    "reviewer",
    "review_status",
    "requirements",
    "assumptions",
    "defects",
    "tests",
    "evidence",
    "disposition",
    "completed_at",
)
TEXT_EXTENSIONS = {
    ".rs",
    ".py",
    ".pyi",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".mjs",
    ".cjs",
    ".c",
    ".cc",
    ".cpp",
    ".h",
    ".hpp",
    ".sh",
    ".bash",
    ".zsh",
    ".md",
    ".rst",
    ".txt",
    ".toml",
    ".json",
    ".json5",
    ".yaml",
    ".yml",
    ".proto",
    ".xml",
    ".css",
    ".scss",
    ".html",
    ".svg",
}


class LedgerError(ValueError):
    """The immutable source tree cannot produce a truthful review ledger."""


def _git(repo: Path, *args: str, input_bytes: bytes | None = None) -> bytes:
    try:
        return subprocess.check_output(
            ["git", "-C", os.fspath(repo), *args],
            input=input_bytes,
            stderr=subprocess.PIPE,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        detail = ""
        if isinstance(error, subprocess.CalledProcessError):
            detail = error.stderr.decode("utf-8", "replace").strip()
        raise LedgerError(f"git {' '.join(args)} failed: {detail or error}") from error


def resolve_source(repo: Path, source: str) -> tuple[str, str]:
    commit = (
        _git(repo, "rev-parse", "--verify", f"{source}^{{commit}}").decode().strip()
    )
    if SOURCE_ID.fullmatch(commit) is None:
        raise LedgerError("resolved source is not a full lowercase commit ID")
    tree = _git(repo, "rev-parse", "--verify", f"{commit}^{{tree}}").decode().strip()
    if SOURCE_ID.fullmatch(tree) is None:
        raise LedgerError("resolved tree is not a full lowercase object ID")
    return commit, tree


def _tree_entries(repo: Path, commit: str) -> list[tuple[str, str, str, int, str]]:
    raw = _git(repo, "ls-tree", "-rz", "--full-tree", "--long", commit)
    entries: list[tuple[str, str, str, int, str]] = []
    for number, record in enumerate(member for member in raw.split(b"\0") if member):
        try:
            metadata, path_bytes = record.split(b"\t", 1)
            fields = metadata.split()
            if len(fields) != 4:
                raise ValueError("metadata field count")
            mode, kind, object_id, size = fields
            path = path_bytes.decode("utf-8")
            size_value = int(size) if size != b"-" else 0
        except (ValueError, UnicodeError) as error:
            raise LedgerError(f"cannot parse UTF-8 tree entry {number}") from error
        if mode not in {b"100644", b"100755", b"120000", b"160000"}:
            raise LedgerError(f"unsupported Git mode {mode!r} for {path!r}")
        if kind not in {b"blob", b"commit"}:
            raise LedgerError(f"unsupported Git object type {kind!r} for {path!r}")
        identifier = object_id.decode("ascii")
        if SOURCE_ID.fullmatch(identifier) is None:
            raise LedgerError(f"invalid Git object ID for {path!r}")
        entries.append(
            (mode.decode("ascii"), kind.decode("ascii"), identifier, size_value, path)
        )
    paths = [entry[4] for entry in entries]
    if len(paths) != len(set(paths)):
        raise LedgerError("source tree contains duplicate decoded paths")
    return entries


def _blob(
    repo: Path, kind: str, object_id: str, expected_size: int, path: str
) -> bytes:
    if kind == "commit":
        return object_id.encode("ascii")
    data = _git(repo, "cat-file", "blob", object_id)
    if len(data) != expected_size:
        raise LedgerError(
            f"Git size mismatch for {path!r}: tree={expected_size} blob={len(data)}"
        )
    return data


def _text(data: bytes, suffix: str) -> str | None:
    if suffix not in TEXT_EXTENSIONS and b"\0" in data[:8192]:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _line_count(text: str | None) -> int:
    if text is None:
        return 0
    return text.count("\n") + (1 if text and not text.endswith("\n") else 0)


def _language(path: str, mode: str, text: str | None) -> str:
    if mode == "120000":
        return "symlink"
    if mode == "160000":
        return "gitlink"
    name = Path(path).name
    suffix = Path(path).suffix.lower()
    names = {
        "Cargo.lock": "TOML lock",
        "Cargo.toml": "TOML",
        "CMakeLists.txt": "CMake",
        "Dockerfile": "Dockerfile",
        "LICENSE": "license text",
        "LICENSE-APACHE": "license text",
        "LICENSE-MIT": "license text",
        "Makefile": "Make",
        "bun.lock": "Bun lock",
    }
    extensions = {
        ".rs": "Rust",
        ".py": "Python",
        ".pyi": "Python stub",
        ".ts": "TypeScript",
        ".tsx": "TypeScript JSX",
        ".js": "JavaScript",
        ".mjs": "JavaScript module",
        ".cjs": "CommonJS",
        ".c": "C",
        ".cc": "C++",
        ".cpp": "C++",
        ".h": "C/C++ header",
        ".hpp": "C++ header",
        ".sh": "shell",
        ".md": "Markdown",
        ".toml": "TOML",
        ".json": "JSON",
        ".json5": "JSON5",
        ".yaml": "YAML",
        ".yml": "YAML",
        ".proto": "Protocol Buffers",
        ".svg": "SVG",
        ".png": "PNG",
        ".bin": "binary fixture",
        ".cff": "Citation File Format",
    }
    return names.get(
        name, extensions.get(suffix, "UTF-8 text" if text is not None else "binary")
    )


def _generated(path: str) -> tuple[str, str]:
    if path == "contract/manifest.v1.json":
        return "YES", "python3 scripts/generate_contract_manifest.py --write"
    if path == "conformance/manifest.v1.json":
        return "YES", "python3 scripts/generate_conformance_manifest.py --write"
    if path.startswith("schemas/") and path != "schemas/README.md":
        return "YES", "cargo run -p ncp-core --features schema --bin gen-schemas"
    if path.startswith("ncp-core/bindings/") or path.startswith(
        "ncp-ts/src/generated/"
    ):
        return "YES", "node ncp-ts/scripts/sync-bindings.mjs"
    if path.startswith("ncp-ts/dist/"):
        return "YES", "bun run build"
    if path.startswith("docs/diagrams/"):
        return "YES", "python3 scripts/gen_diagrams.py"
    if path.startswith("docs/plots/") and path.endswith(".svg"):
        return "YES", "python3 scripts/plot_perf.py"
    if "/testdata/" in path:
        return "YES", "python3 scripts/sync_rust_package_testdata.py --write"
    if path.startswith("conformance/baseline/"):
        return (
            "FROZEN",
            "immutable release/candidate baseline; verified by scripts/check_released_baselines.py or scripts/check_wire_baseline.py",
        )
    if path == "Cargo.lock":
        return "YES", "cargo generate-lockfile"
    if path == "bun.lock":
        return "YES", "bun install"
    return "NO", "NOT_APPLICABLE"


def _flags(path: str) -> tuple[str, str, str, str]:
    lower = path.lower()
    public = (
        path in {"README.md", "CITATION.cff", "VERSIONING.md", "SECURITY.md"}
        or lower.startswith(("proto/", "contract/", "schemas/", "docs/"))
        or any(
            part in lower
            for part in ("/readme.md", "/include/", "pyproject.toml", "package.json")
        )
    )
    security = any(
        token in lower
        for token in (
            "security",
            "authority",
            "idempotency",
            "request_digest",
            "audit",
            "bounded_json",
            "acl",
            "zenoh",
            "deploy/",
            "release",
            ".github/",
        )
    )
    science = any(
        token in lower
        for token in (
            "protocol",
            "messages",
            "schema",
            "conformance",
            "observation",
            "simulation",
            "nest",
            "performance",
            "resilience",
            "migration",
        )
    )
    authority = any(
        token in lower
        for token in (
            "authority",
            "action",
            "command",
            "safety",
            "plant",
            "watchdog",
            "zenoh",
            "gateway",
            "deploy/",
        )
    )
    return (
        *("YES" if value else "NO" for value in (public, security, science, authority)),
    )


def _requirements(path: str) -> str:
    groups = ["T000-T009"]
    if path.startswith("proto/") or Path(path).name.startswith("buf"):
        groups.append("T015-T019")
    elif path.startswith("contract/"):
        groups.append("T020-T024")
    elif path.startswith("schemas/"):
        groups.append("T025-T029")
    elif path.startswith("conformance/"):
        groups.append("T030-T034")
    elif path.startswith("ncp-zenoh/"):
        groups.append("T075-T079")
    elif path.startswith("ncp-python/"):
        groups.append("T080-T084")
    elif path.startswith("ncp-cpp/"):
        groups.extend(("T070-T074", "T085-T089"))
    elif path.startswith("ncp-ts/"):
        groups.append("T090-T094")
    elif path.startswith("ncp-gateway/"):
        groups.append("T095-T099")
    elif path.startswith("ncp-core/"):
        groups.append("T035-T069")
    elif path.startswith("deploy/"):
        groups.append("T100-T104")
    elif path.startswith("e2e/"):
        groups.append("T105-T109")
    elif path.startswith("scripts/") or Path(path).name in {
        "Cargo.lock",
        "bun.lock",
        "package.json",
    }:
        groups.append("T110-T114")
    elif path.startswith(".github/"):
        groups.append("T115-T119")
    elif path.startswith("docs/") or path.startswith("assets/"):
        groups.append("T120-T124")
    else:
        groups.append("T010-T014")
    groups.append("T125-T145")
    return ";".join(groups)


def _tests(path: str, generated: str) -> str:
    tests = ["scripts/check.sh"]
    if generated == "YES":
        tests.append("generator byte-diff in local preflight")
    if path.startswith("ncp-core/"):
        tests.append("cargo test -p ncp-core --locked")
    elif path.startswith("ncp-zenoh/"):
        tests.append("cargo test -p ncp-zenoh --locked")
    elif path.startswith("ncp-ts/"):
        tests.append("bun run check:behavior")
    elif path.startswith("ncp-python/"):
        tests.append("installed-wheel pytest and behavior corpus")
    elif path.startswith("ncp-cpp/"):
        tests.append("cargo test -p ncp-cpp --locked")
    return "; ".join(dict.fromkeys(tests))


def build(
    repo: Path,
    source: str,
    review_status: str,
    completed_at: str,
) -> tuple[str, dict[str, Any]]:
    if review_status not in REVIEW_STATUSES:
        raise LedgerError(f"unsupported review status {review_status!r}")
    if review_status == "REVIEW_ASSIGNED" and completed_at:
        raise LedgerError("assigned review rows must not have completed_at")
    if review_status != "REVIEW_ASSIGNED" and not completed_at:
        raise LedgerError("completed internal review rows require completed_at")
    commit, tree = resolve_source(repo, source)
    entries = _tree_entries(repo, commit)
    intermediate: list[dict[str, Any]] = []
    for mode, kind, object_id, size, path in entries:
        data = _blob(repo, kind, object_id, size, path)
        suffix = Path(path).suffix.lower()
        text = _text(data, suffix)
        lines = _line_count(text)
        generated, generator = _generated(path)
        public, security, science, authority = _flags(path)
        intermediate.append(
            {
                "path": path,
                "git_blob_id": object_id,
                "sha256": hashlib.sha256(data).hexdigest(),
                "bytes": len(data),
                "lines": lines,
                "language": _language(path, mode, text),
                "generated": generated,
                "generator": generator,
                "public_surface": public,
                "security_critical": security,
                "science_critical": science,
                "authority_critical": authority,
            }
        )

    lanes: list[dict[str, Any]] = [
        {"reviewer": reviewer, "lines": 0, "paths": []} for reviewer in REVIEWERS
    ]
    for row in sorted(intermediate, key=lambda item: int(item["lines"]), reverse=True):
        lane = min(lanes, key=lambda item: int(item["lines"]))
        lane["paths"].append(row["path"])
        lane["lines"] += row["lines"]
    reviewers = {path: lane["reviewer"] for lane in lanes for path in lane["paths"]}

    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=FIELDNAMES, lineterminator="\n")
    writer.writeheader()
    for row in intermediate:
        full = {
            **row,
            "reviewer": reviewers[row["path"]],
            "review_status": review_status,
            "requirements": _requirements(row["path"]),
            "assumptions": "Mechanical classification only; reviewer confirms semantics, generator provenance, criticality, tests, and disposition.",
            "defects": "See max-effort task review and retained lane findings; unresolved findings do not close this row.",
            "tests": _tests(row["path"], row["generated"]),
            "evidence": f"git:{commit}:{row['git_blob_id']};sha256:{row['sha256']}",
            "disposition": "OPEN_PENDING_TASK_CLOSURE_AND_INDEPENDENT_REVIEW",
            "completed_at": completed_at,
        }
        writer.writerow(full)
    csv_text = output.getvalue()
    reviewed_files = 0 if review_status == "REVIEW_ASSIGNED" else len(intermediate)
    manifest = {
        "schema": "ncp.max-effort-file-review-manifest.v2",
        "normative": False,
        "source_commit": commit,
        "source_tree": tree,
        "source_boundary": "Exact committed Git objects; worktree bytes and this subsequent evidence update are excluded.",
        "columns": list(FIELDNAMES),
        "tracked_files": len(intermediate),
        "internally_reviewed_files": reviewed_files,
        "independently_reviewed_files": 0,
        "critical_files_independently_reviewed": 0,
        "tracked_bytes": sum(int(row["bytes"]) for row in intermediate),
        "text_lines": sum(int(row["lines"]) for row in intermediate),
        "review_status": review_status,
        "completed_at": completed_at,
        "decision": "NO_GO",
        "reviewers": [
            {
                "id": lane["reviewer"],
                "files": len(lane["paths"]),
                "text_lines": lane["lines"],
                "independent_human_reviewer": False,
            }
            for lane in lanes
        ],
        "csv_sha256": hashlib.sha256(csv_text.encode("utf-8")).hexdigest(),
        "generator": shlex.join(
            [
                "python3",
                "scripts/generate_file_review_ledger.py",
                "--source",
                commit,
                "--review-status",
                review_status,
                "--completed-at",
                completed_at,
            ]
        ),
        "limitation": "Complete internal AI-assisted inspection and exact row coverage do not satisfy the handoff's independent critical-file review, task evidence, external gates, or release signature requirements.",
    }
    return csv_text, manifest


def _encoded_manifest(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def self_test() -> None:
    with tempfile.TemporaryDirectory() as directory:
        repo = Path(directory) / "repo"
        repo.mkdir()
        _git(repo, "init", "-q")
        _git(repo, "config", "user.name", "File Review Test")
        _git(repo, "config", "user.email", "test@example.invalid")
        (repo / "plain.txt").write_text("one\ntwo\n", encoding="utf-8")
        (repo / "odd,\nname.txt").write_text("three", encoding="utf-8")
        (repo / "binary.bin").write_bytes(b"\x00\xff")
        (repo / "link").symlink_to("plain.txt")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-qm", "fixture")
        ledger, manifest = build(repo, "HEAD", "REVIEW_ASSIGNED", "")
        rows = list(csv.DictReader(io.StringIO(ledger)))
        if len(rows) != 4 or tuple(rows[0]) != FIELDNAMES:
            raise AssertionError("fixture did not emit exact 21-column rows")
        by_path = {row["path"]: row for row in rows}
        if "odd,\nname.txt" not in by_path:
            raise AssertionError("CSV did not round-trip comma/newline path")
        if by_path["link"]["language"] != "symlink" or by_path["link"]["bytes"] != str(
            len("plain.txt")
        ):
            raise AssertionError(
                "symlink target was followed instead of hashing link bytes"
            )
        if manifest["tracked_files"] != 4 or manifest["internally_reviewed_files"] != 0:
            raise AssertionError("assigned manifest counts are wrong")
        complete, complete_manifest = build(
            repo,
            "HEAD",
            "INTERNAL_AI_REVIEW_COMPLETE_WITH_OPEN_FINDINGS",
            "2026-07-14T00:00:00Z",
        )
        if complete_manifest["internally_reviewed_files"] != 4 or not complete:
            raise AssertionError("completed internal manifest counts are wrong")
        expected_command = (
            "python3 scripts/generate_file_review_ledger.py "
            f"--source {complete_manifest['source_commit']} "
            "--review-status INTERNAL_AI_REVIEW_COMPLETE_WITH_OPEN_FINDINGS "
            "--completed-at 2026-07-14T00:00:00Z"
        )
        if complete_manifest["generator"] != expected_command:
            raise AssertionError(
                "manifest generator command did not reflect build arguments"
            )
        if not manifest["generator"].endswith("--completed-at ''"):
            raise AssertionError(
                "assigned-review generator omitted the required empty timestamp"
            )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--source", default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument(
        "--review-status",
        choices=sorted(REVIEW_STATUSES),
        default=DEFAULT_REVIEW_STATUS,
    )
    parser.add_argument("--completed-at", default=DEFAULT_COMPLETED_AT)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        if args.self_test:
            self_test()
        csv_text, manifest = build(
            args.repo.resolve(), args.source, args.review_status, args.completed_at
        )
        manifest_text = _encoded_manifest(manifest)
        if args.check:
            if args.output.read_text(encoding="utf-8") != csv_text:
                raise LedgerError(
                    "committed file-review CSV differs from exact Git source"
                )
            if args.manifest.read_text(encoding="utf-8") != manifest_text:
                raise LedgerError(
                    "committed file-review manifest differs from exact Git source"
                )
        else:
            args.output.write_text(csv_text, encoding="utf-8", newline="")
            args.manifest.write_text(manifest_text, encoding="utf-8")
        print(
            "OK max-effort file ledger: "
            f"{manifest['tracked_files']} files, {manifest['text_lines']} text lines, "
            f"{manifest['review_status']}, NO_GO"
        )
    except (LedgerError, OSError, UnicodeError, AssertionError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
