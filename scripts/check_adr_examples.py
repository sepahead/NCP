#!/usr/bin/env python3
"""Parse every proposed ADR JSON fence with the two independent B04 parsers.

This is syntax, duplicate-member, UTF-8, numeric-grammar, and resource-bound
evidence only. It does not implement the proposed messages, accept an ADR,
establish interoperability, or change the normative contract.
"""

from __future__ import annotations

import argparse
import base64
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
ADR_DIR = ROOT / "docs" / "adr"
PROTOTYPE = (
    ROOT
    / "prototypes"
    / "authenticated-ingress"
    / "signed-forwarding-envelope"
)
NODE = PROTOTYPE / "node-verifier"
JSON_FENCE = re.compile(r"```json\n(.*?)\n```", re.DOTALL)
ADR_PATH = re.compile(r"00(?:0[1-9]|1[01])-[a-z0-9-]+\.md")


class ExampleError(ValueError):
    """The proposed ADR example corpus is incomplete or parser-divergent."""


def proposed_paths() -> list[Path]:
    paths = sorted(
        path
        for path in ADR_DIR.glob("*.md")
        if ADR_PATH.fullmatch(path.name)
    )
    if len(paths) != 11:
        raise ExampleError("expected exactly eleven proposed ADR Markdown files")
    return paths


def examples() -> list[tuple[str, bytes]]:
    found: list[tuple[str, bytes]] = []
    for path in proposed_paths():
        text = path.read_text(encoding="utf-8")
        fences = JSON_FENCE.findall(text)
        if not fences:
            raise ExampleError(f"{path.relative_to(ROOT)} has no JSON example")
        for index, value in enumerate(fences, start=1):
            found.append(
                (
                    f"{path.relative_to(ROOT)}#json-{index}",
                    value.encode("utf-8"),
                )
            )
    return found


def python_parse(values: list[tuple[str, bytes]]) -> None:
    strict = load_python_parser()
    limits = strict.JsonLimits(
        max_bytes=131_072,
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
  maxBytes: 131072,
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
"""


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
        raise ExampleError(f"cannot build independent Node parser: {error}") from error
    if build.returncode != 0:
        detail = (build.stderr or build.stdout).strip()[-2000:]
        raise ExampleError(
            "independent Node parser build failed; install its exact lock first: "
            + detail
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
        raise ExampleError(f"cannot run independent Node parser: {error}") from error
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
            f"OK ADR examples: {len(corpus)} JSON fences accepted by independent "
            "Python and Node prototype parsers; semantic implementation not claimed"
        )
        return 0
    except (ExampleError, OSError, UnicodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
