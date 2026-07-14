#!/usr/bin/env python3
"""Extract the review-relevant index from the max-effort handoff ledger.

The handoff YAML is an external review input, not a repository dependency.  This
stdlib-only extractor deliberately understands only the closed scalar subset used
by the handoff's task and lens index.  It refuses unknown or malformed index
shapes instead of silently approximating YAML semantics.  The generated JSON is
non-normative evidence bookkeeping; it never authorizes a release.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Any


LENS_ID = re.compile(r"^L(?:0[1-9]|1[0-9]|20)$")
TASK_ID = re.compile(r"^T[0-9]{3}$")
TASK_FIELDS = (
    "id",
    "phase",
    "title",
    "source_scope",
    "focus",
    "dependencies",
    "execution_wave",
    "subagent_lane",
)


class IndexError(ValueError):
    """The external handoff index is malformed or outside the supported subset."""


def _decode_scalar(value: str, path: str) -> str:
    value = value.strip()
    if not value:
        raise IndexError(f"{path} must be a non-empty scalar")
    if value.startswith("'") or value.endswith("'"):
        if not (value.startswith("'") and value.endswith("'")):
            raise IndexError(f"{path} has an unterminated single-quoted scalar")
        return value[1:-1].replace("''", "'")
    if value.startswith('"') or value.endswith('"'):
        if not (value.startswith('"') and value.endswith('"')):
            raise IndexError(f"{path} has an unterminated double-quoted scalar")
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError as error:
            raise IndexError(f"{path} has an invalid double-quoted scalar") from error
        if not isinstance(decoded, str) or not decoded:
            raise IndexError(f"{path} must decode to a non-empty string")
        return decoded
    if value[0] in "[{&*!|>" or value.startswith(("null", "~")):
        raise IndexError(f"{path} uses unsupported YAML syntax")
    return value


def _top_scalar(lines: list[str], name: str) -> str:
    prefix = f"{name}:"
    matches = [line[len(prefix) :] for line in lines if line.startswith(prefix)]
    if len(matches) != 1:
        raise IndexError(f"expected exactly one top-level {name}")
    return _decode_scalar(matches[0], name)


def _folded_scalar(block: list[str], field: str, path: str) -> str:
    prefix = f"  {field}:"
    indices = [index for index, line in enumerate(block) if line.startswith(prefix)]
    if len(indices) != 1:
        raise IndexError(f"{path}.{field} must occur exactly once")
    index = indices[0]
    parts = [block[index][len(prefix) :].strip()]
    for line in block[index + 1 :]:
        if not line.startswith("    ") or line.startswith("    L"):
            break
        parts.append(line.strip())
    return _decode_scalar(" ".join(part for part in parts if part), f"{path}.{field}")


def _blocks(lines: list[str], pattern: re.Pattern[str]) -> list[list[str]]:
    starts = [index for index, line in enumerate(lines) if pattern.fullmatch(line)]
    blocks: list[list[str]] = []
    for position, start in enumerate(starts):
        stop = starts[position + 1] if position + 1 < len(starts) else len(lines)
        blocks.append(lines[start:stop])
    return blocks


def _parse_lenses(lines: list[str]) -> list[dict[str, str]]:
    try:
        start = lines.index("twenty_lenses:") + 1
        stop = lines.index("tasks:")
    except ValueError as error:
        raise IndexError("ledger must contain twenty_lenses followed by tasks") from error
    region = lines[start:stop]
    blocks = _blocks(region, re.compile(r"- id: L[0-9]{2}"))
    lenses: list[dict[str, str]] = []
    for index, block in enumerate(blocks):
        identifier = _decode_scalar(block[0].split(":", 1)[1], f"lens[{index}].id")
        name = _folded_scalar(block, "name", f"lens[{index}]")
        question = _folded_scalar(block, "question", f"lens[{index}]")
        if LENS_ID.fullmatch(identifier) is None:
            raise IndexError(f"lens[{index}].id is not canonical")
        lenses.append({"id": identifier, "name": name, "question": question})
    expected = [f"L{index:02d}" for index in range(1, 21)]
    if [lens["id"] for lens in lenses] != expected:
        raise IndexError("lens IDs must be the exact ordered range L01 through L20")
    return lenses


def _field(block: list[str], field: str, path: str) -> str:
    prefix = f"  {field}:"
    matches = [line[len(prefix) :] for line in block if line.startswith(prefix)]
    if len(matches) != 1:
        raise IndexError(f"{path}.{field} must occur exactly once")
    return _decode_scalar(matches[0], f"{path}.{field}")


def _dependencies(block: list[str], path: str) -> list[str]:
    marker = "  dependencies:"
    indices = [index for index, line in enumerate(block) if line.startswith(marker)]
    if len(indices) != 1:
        raise IndexError(f"{path}.dependencies must occur exactly once")
    index = indices[0]
    suffix = block[index][len(marker) :].strip()
    if suffix == "[]":
        return []
    if suffix:
        raise IndexError(f"{path}.dependencies must use the supported block-list form")
    dependencies: list[str] = []
    for line in block[index + 1 :]:
        if line.startswith("  - "):
            dependencies.append(_decode_scalar(line[4:], f"{path}.dependencies"))
            continue
        break
    if not dependencies:
        raise IndexError(f"{path}.dependencies block must not be empty")
    if len(dependencies) != len(set(dependencies)):
        raise IndexError(f"{path}.dependencies contains a duplicate")
    return dependencies


def _integer(block: list[str], field: str, path: str) -> int:
    value = _field(block, field, path)
    if not value.isascii() or not value.isdecimal():
        raise IndexError(f"{path}.{field} must be a non-negative decimal integer")
    return int(value)


def _parse_tasks(lines: list[str]) -> list[dict[str, Any]]:
    try:
        start = lines.index("tasks:") + 1
    except ValueError as error:
        raise IndexError("ledger is missing tasks") from error
    blocks = _blocks(lines[start:], re.compile(r"- id: T[0-9]{3}"))
    tasks: list[dict[str, Any]] = []
    earlier: set[str] = set()
    for index, block in enumerate(blocks):
        path = f"task[{index}]"
        identifier = _decode_scalar(block[0].split(":", 1)[1], f"{path}.id")
        if TASK_ID.fullmatch(identifier) is None:
            raise IndexError(f"{path}.id is not canonical")
        dependencies = _dependencies(block, path)
        for dependency in dependencies:
            if dependency not in earlier:
                raise IndexError(f"{path} references non-earlier dependency {dependency}")
        task = {
            "id": identifier,
            "phase": _folded_scalar(block, "phase", path),
            "title": _folded_scalar(block, "title", path),
            "source_scope": _folded_scalar(block, "source_scope", path),
            "focus": _folded_scalar(block, "focus", path),
            "dependencies": dependencies,
            "execution_wave": _integer(block, "execution_wave", path),
            "subagent_lane": _integer(block, "subagent_lane", path),
        }
        if tuple(task) != TASK_FIELDS:
            raise AssertionError("internal task field order drift")
        tasks.append(task)
        earlier.add(identifier)
    expected = [f"T{index:03d}" for index in range(146)]
    if [task["id"] for task in tasks] != expected:
        raise IndexError("task IDs must be the exact ordered range T000 through T145")
    if any(task["execution_wave"] not in range(10) for task in tasks):
        raise IndexError("execution_wave must be in the closed range 0 through 9")
    if any(task["subagent_lane"] not in range(1, 4) for task in tasks):
        raise IndexError("subagent_lane must be in the closed range 1 through 3")
    return tasks


def extract(path: Path) -> dict[str, Any]:
    try:
        payload = path.read_bytes()
        text = payload.decode("utf-8")
    except (OSError, UnicodeError) as error:
        raise IndexError(f"cannot read UTF-8 handoff ledger: {error}") from error
    lines = text.splitlines()
    schema = _top_scalar(lines, "schema")
    if schema != "2.0.0":
        raise IndexError("handoff schema must be exactly 2.0.0")
    return {
        "schema": "ncp.max-effort-handoff-source-index.v2",
        "normative": False,
        "source": {
            "file_name": path.name,
            "handoff_schema": schema,
            "sha256": hashlib.sha256(payload).hexdigest(),
            "project": _top_scalar(lines, "project"),
            "repository": _top_scalar(lines, "repository"),
            "frozen_commit": _top_scalar(lines, "frozen_commit"),
            "release_target": _top_scalar(lines, "release_target"),
        },
        "twenty_lenses": _parse_lenses(lines),
        "tasks": _parse_tasks(lines),
    }


def canonical_index_sha256(value: dict[str, Any]) -> str:
    canonical = json.dumps(
        {"twenty_lenses": value["twenty_lenses"], "tasks": value["tasks"]},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def self_test() -> None:
    fixture = """schema: 2.0.0
project: NCP
repository: https://example.invalid/NCP
frozen_commit: 0000000000000000000000000000000000000000
release_target: 1.0.0
twenty_lenses:
"""
    for index in range(1, 21):
        fixture += (
            f"- id: L{index:02d}\n"
            f"  name: Lens {index}\n"
            f"  question: Question {index}?\n"
        )
    fixture += "tasks:\n"
    for index in range(146):
        fixture += (
            f"- id: T{index:03d}\n"
            "  phase: 'Path group: test'\n"
            f"  title: Task {index}\n"
            "  source_scope: fixture\n"
            "  focus: parser\n"
        )
        if index == 0:
            fixture += "  dependencies: []\n"
        else:
            fixture += f"  dependencies:\n  - T{index - 1:03d}\n"
        fixture += f"  execution_wave: {min(index // 15, 9)}\n"
        fixture += f"  subagent_lane: {(index % 3) + 1}\n"
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "MASTER_TASK_LEDGER.yaml"
        path.write_text(fixture, encoding="utf-8")
        value = extract(path)
        if len(value["twenty_lenses"]) != 20 or len(value["tasks"]) != 146:
            raise AssertionError("valid fixture did not produce the closed index")
        hostile = fixture.replace("- id: T145", "- id: T144", 1)
        path.write_text(hostile, encoding="utf-8")
        try:
            extract(path)
        except IndexError:
            pass
        else:
            raise AssertionError("duplicate/missing task ID passed extraction")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", nargs="?", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        if args.self_test:
            self_test()
        if args.source is None:
            if not args.self_test:
                parser.error("source is required unless --self-test is used")
            print("OK max-effort handoff index extractor self-test")
            return 0
        value = extract(args.source)
        encoded = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
        if args.output is None:
            sys.stdout.write(encoded)
        else:
            args.output.write_text(encoded, encoding="utf-8")
        print(
            "OK max-effort source index: "
            f"{len(value['tasks'])} tasks, {len(value['twenty_lenses'])} lenses, "
            f"canonical={canonical_index_sha256(value)}",
            file=sys.stderr,
        )
    except (IndexError, OSError, AssertionError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
