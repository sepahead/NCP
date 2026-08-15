#!/usr/bin/env python3
"""Parse every proposed ADR JSON fence with the two separate B04 parsers.

This is syntax, duplicate-member, UTF-8, numeric-grammar, and resource-bound
evidence only. It does not implement the proposed messages, accept an ADR,
establish interoperability, or change the normative contract.
"""

from __future__ import annotations

import argparse
import base64
import importlib.util
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ADR_DIR = ROOT / "docs" / "adr"
PROTOTYPE = ROOT / "prototypes" / "authenticated-ingress" / "signed-forwarding-envelope"
NODE = PROTOTYPE / "node-verifier"
ADR_PATH = re.compile(r"00(0[1-9]|1[01])-[a-z0-9]+(?:-[a-z0-9]+)*\.md")
ADR_NUMBERED_CANDIDATE = re.compile(r"(?:000[1-9]|001[01]).*\.md", re.IGNORECASE)
MIN_ADR_MARKDOWN_BYTES = 1024
MAX_ADR_MARKDOWN_BYTES = 256 * 1024
MAX_ADR_CORPUS_BYTES = 2 * 1024 * 1024
MAX_JSON_EXAMPLE_BYTES = 131_072


class ExampleError(ValueError):
    """The proposed ADR example corpus is incomplete or parser-divergent."""


def validate_proposed_paths(paths: list[Path]) -> list[Path]:
    identifiers: list[int] = []
    for path in paths:
        match = ADR_PATH.fullmatch(path.name)
        if match is None:
            raise ExampleError(f"noncanonical proposed ADR path: {path.name}")
        identifiers.append(int(match.group(1)))
    if identifiers != list(range(1, 12)):
        raise ExampleError(
            "expected exactly one canonical Markdown file for each "
            "ADR-001 through ADR-011"
        )
    return paths


def proposed_paths() -> list[Path]:
    paths = sorted(
        path
        for path in ADR_DIR.iterdir()
        if ADR_NUMBERED_CANDIDATE.fullmatch(path.name)
    )
    return validate_proposed_paths(paths)


def validate_adr_markdown_byte_count(byte_count: int, path: str) -> int:
    if (
        type(byte_count) is not int
        or not MIN_ADR_MARKDOWN_BYTES <= byte_count <= MAX_ADR_MARKDOWN_BYTES
    ):
        raise ExampleError(
            f"{path} byte size is outside "
            f"{MIN_ADR_MARKDOWN_BYTES}..{MAX_ADR_MARKDOWN_BYTES}"
        )
    return byte_count


def validate_adr_corpus_byte_counts(byte_counts: list[int]) -> int:
    total = 0
    for index, byte_count in enumerate(byte_counts):
        total += validate_adr_markdown_byte_count(
            byte_count, f"ADR corpus entry {index}"
        )
        if total > MAX_ADR_CORPUS_BYTES:
            raise ExampleError(
                "ADR Markdown corpus exceeds the aggregate byte limit of "
                f"{MAX_ADR_CORPUS_BYTES}"
            )
    return total


def extract_exact_json_fences(markdown: bytes, *, label: str) -> list[bytes]:
    """Return top-level exact JSON fences under the shared B01 grammar."""
    try:
        markdown.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ExampleError(f"{label} is not UTF-8: {error}") from error

    fences: list[bytes] = []
    state: tuple[str, int] | None = None
    line_start = 0
    while line_start < len(markdown):
        newline = markdown.find(b"\n", line_start)
        line_end = newline if newline >= 0 else len(markdown)
        logical_end = line_end
        if logical_end > line_start and markdown[logical_end - 1] == 0x0D:
            logical_end -= 1
        line = markdown[line_start:logical_end]
        next_line = line_end + 1 if line_end < len(markdown) else len(markdown)

        if state is None and line == b"```json":
            if line_end == len(markdown):
                raise ExampleError(
                    f"{label} JSON fence opener has no following content line"
                )
            state = ("json", next_line)
        elif state is None and line.startswith(b"```"):
            state = ("other", 0)
        elif state is not None and state[0] == "json" and line == b"```":
            content_end = line_start
            if content_end > state[1] and markdown[content_end - 1] == 0x0A:
                content_end -= 1
                if content_end > state[1] and markdown[content_end - 1] == 0x0D:
                    content_end -= 1
            fences.append(markdown[state[1] : content_end])
            state = None
        elif state is not None and state[0] == "other" and line == b"```":
            state = None
        line_start = next_line

    if state is not None:
        raise ExampleError(f"{label} contains an unclosed Markdown fence")
    return fences


def examples() -> list[tuple[str, bytes]]:
    found: list[tuple[str, bytes]] = []
    byte_counts: list[int] = []
    for path in proposed_paths():
        relative = path.relative_to(ROOT).as_posix()
        content = read_regular_file_no_follow(path, label=relative)
        byte_counts.append(len(content))
        fences = extract_exact_json_fences(content, label=relative)
        if not fences:
            raise ExampleError(f"{relative} has no JSON example")
        for index, value in enumerate(fences, start=1):
            found.append(
                (
                    f"{relative}#json-{index}",
                    value,
                )
            )
    validate_adr_corpus_byte_counts(byte_counts)
    return found


def read_regular_file_no_follow(path: Path, *, label: str) -> bytes:
    no_follow = getattr(os, "O_NOFOLLOW", None)
    if no_follow is None:
        raise ExampleError("this ADR checker requires O_NOFOLLOW support")
    flags = os.O_RDONLY | no_follow | getattr(os, "O_BINARY", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise ExampleError(
            f"cannot open {label} without following links: {error}"
        ) from error
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ExampleError(f"{label} must be a regular non-symlink file")
        validate_adr_markdown_byte_count(before.st_size, label)
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            content = handle.read(MAX_ADR_MARKDOWN_BYTES + 1)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    before_identity = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    )
    after_identity = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    )
    if before_identity != after_identity or len(content) != after.st_size:
        raise ExampleError(f"{label} changed while it was read")
    return content


def python_parse(values: list[tuple[str, bytes]]) -> None:
    strict = load_python_parser()
    limits = strict.JsonLimits(
        max_bytes=MAX_JSON_EXAMPLE_BYTES,
        max_depth=32,
        max_nodes=100_000,
        max_members=4_096,
        max_string_bytes=65_536,
    )
    for name, value in values:
        try:
            strict.strict_json_loads(value, limits, allow_floats=False)
        except strict.PrototypeError as error:
            raise ExampleError(f"Python parser rejected {name}: {error}") from error


def load_python_parser() -> Any:
    path = PROTOTYPE / "prototype" / "strict.py"
    spec = importlib.util.spec_from_file_location("ncp_b04_strict_json", path)
    if spec is None or spec.loader is None:
        raise ExampleError("cannot create an import specification for strict.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except ImportError as error:
        raise ExampleError(f"cannot import Python prototype parser: {error}") from error
    return module


NODE_PROGRAM = r"""
import { strictJsonParse } from "./dist/src/strict-json.js";
const limits = {
  maxBytes: __MAX_JSON_EXAMPLE_BYTES__,
  maxDepth: 32,
  maxNodes: 100000,
  maxMembers: 4096,
  maxStringBytes: 65536,
};
let input = "";
for await (const chunk of process.stdin) input += chunk;
const values = JSON.parse(input);
for (const value of values) {
  strictJsonParse(Buffer.from(value.json, "base64"), limits, false);
}
process.stdout.write(JSON.stringify({ accepted: values.length }) + "\n");
""".replace("__MAX_JSON_EXAMPLE_BYTES__", str(MAX_JSON_EXAMPLE_BYTES))


def node_parse(values: list[tuple[str, bytes]]) -> None:
    try:
        build = subprocess.run(
            ["npm", "run", "build", "--silent"],
            cwd=NODE,
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ExampleError(f"cannot build separate Node parser: {error}") from error
    if build.returncode != 0:
        detail = (build.stderr or build.stdout).strip()[-2000:]
        raise ExampleError(
            "separate Node parser build failed; install its exact lock first: " + detail
        )
    request = json.dumps(
        [
            {
                "name": name,
                "json": base64.b64encode(value).decode("ascii"),
            }
            for name, value in values
        ],
        separators=(",", ":"),
    ).encode("utf-8")
    try:
        result = subprocess.run(
            ["node", "--input-type=module", "--eval", NODE_PROGRAM],
            cwd=NODE,
            input=request,
            check=False,
            capture_output=True,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ExampleError(f"cannot run separate Node parser: {error}") from error
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()[-2000:]
        raise ExampleError(f"Node parser rejected the ADR corpus: {detail}")
    try:
        response: Any = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise ExampleError("Node parser returned malformed status JSON") from error
    if response != {"accepted": len(values)}:
        raise ExampleError(f"Node parser returned unexpected status: {response!r}")


def self_test() -> None:
    if ADR_PATH.fullmatch("0001-double--hyphen.md") is not None:
        raise AssertionError("ADR checker accepted a noncanonical Markdown filename")
    if ADR_NUMBERED_CANDIDATE.fullmatch("0001subject.MD") is None:
        raise AssertionError("ADR checker ignored a malformed numbered Markdown file")
    canonical_paths = [
        Path(f"docs/adr/{number:04d}-subject-{number}.md") for number in range(1, 12)
    ]
    validate_proposed_paths(canonical_paths)
    duplicate_paths = [*canonical_paths[:-1], canonical_paths[0]]
    duplicate_paths.sort()
    try:
        validate_proposed_paths(duplicate_paths)
    except ExampleError:
        pass
    else:
        raise AssertionError("ADR checker accepted a duplicate ADR number")
    exact_fences = extract_exact_json_fences(
        b'```text\n```json\n{"ignored":true}\n```\n'
        b'```json\r\n{"accepted":true}\r\n```\r\n',
        label="self-test Markdown",
    )
    if exact_fences != [b'{"accepted":true}']:
        raise AssertionError("ADR checker accepted a nested JSON fence")
    try:
        extract_exact_json_fences(b"```json\n{}\n", label="self-test unclosed Markdown")
    except ExampleError:
        pass
    else:
        raise AssertionError("ADR checker accepted an unclosed JSON fence")

    validate_adr_markdown_byte_count(MAX_ADR_MARKDOWN_BYTES, "self-test ADR exact cap")
    try:
        validate_adr_markdown_byte_count(
            MAX_ADR_MARKDOWN_BYTES + 1, "self-test ADR cap plus one"
        )
    except ExampleError:
        pass
    else:
        raise AssertionError("ADR checker accepted the Markdown cap plus one byte")
    aggregate_at_cap = [MAX_ADR_MARKDOWN_BYTES] * 7 + [
        MAX_ADR_MARKDOWN_BYTES - 3 * MIN_ADR_MARKDOWN_BYTES,
        MIN_ADR_MARKDOWN_BYTES,
        MIN_ADR_MARKDOWN_BYTES,
        MIN_ADR_MARKDOWN_BYTES,
    ]
    if validate_adr_corpus_byte_counts(aggregate_at_cap) != MAX_ADR_CORPUS_BYTES:
        raise AssertionError("ADR checker corpus exact-cap test is malformed")
    aggregate_over_cap = aggregate_at_cap.copy()
    aggregate_over_cap[7] += 1
    try:
        validate_adr_corpus_byte_counts(aggregate_over_cap)
    except ExampleError:
        pass
    else:
        raise AssertionError("ADR checker accepted the corpus cap plus one byte")

    strict = load_python_parser()
    limits = strict.JsonLimits(128, 8, 32, 8, 32)
    hostile = b'{"duplicate":1,"duplicate":2}'
    try:
        strict.strict_json_loads(hostile, limits)
    except strict.PrototypeError:
        pass
    else:
        raise AssertionError("Python prototype accepted duplicate JSON members")
    try:
        node_parse([("hostile-duplicate", hostile)])
    except ExampleError:
        pass
    else:
        raise AssertionError("Node prototype accepted duplicate JSON members")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="also require both prototypes to reject duplicate members",
    )
    args = parser.parse_args()
    try:
        if args.self_test:
            self_test()
        corpus = examples()
        python_parse(corpus)
        node_parse(corpus)
        print(
            f"OK ADR examples: {len(corpus)} JSON fences accepted by separate "
            "Python and Node prototype parsers; semantic implementation not claimed"
        )
        return 0
    except (ExampleError, OSError, UnicodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
