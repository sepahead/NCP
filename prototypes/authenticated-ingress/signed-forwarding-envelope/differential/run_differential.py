#!/usr/bin/env python3
"""Fail on any Python/Node decision, code, or projection disagreement."""

from __future__ import annotations

import json
import subprocess
import sys
from hashlib import sha256
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from prototype.strict import b64url_decode  # noqa: E402

CORPUS = Path(__file__).with_name("corpus.v1.json")
PYTHON_ADAPTER = Path(__file__).with_name("python_adapter.py")
NODE_ADAPTER = ROOT / "node-verifier" / "dist" / "src" / "cli.js"
RESPONSE_SCHEMA = "ncp.prototype.signed-forwarding-node-response.v1"


class DifferentialError(ValueError):
    """One implementation or expected-result disagreement."""


def canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")


def invoke(command: list[str], request: bytes, identifier: str) -> dict[str, Any]:
    completed = subprocess.run(  # noqa: S603 - commands are fixed by the local harness
        command,
        input=request,
        capture_output=True,
        check=False,
        timeout=20,
    )
    if completed.returncode != 0:
        raise DifferentialError(
            f"{identifier}: {' '.join(command)} exited {completed.returncode}: "
            f"{completed.stderr.decode(errors='replace')}"
        )
    if completed.stderr:
        raise DifferentialError(
            f"{identifier}: adapter wrote stderr: {completed.stderr.decode(errors='replace')}"
        )
    try:
        response = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise DifferentialError(f"{identifier}: adapter response is not JSON") from error
    if not isinstance(response, dict) or response.get("schema") != RESPONSE_SCHEMA:
        raise DifferentialError(f"{identifier}: adapter response schema drifted")
    return response


def compare_case(case: dict[str, Any]) -> None:
    identifier = case["id"]
    request = b64url_decode(case["request_b64"], maximum=2_200_000)
    python = invoke([sys.executable, str(PYTHON_ADAPTER)], request, identifier)
    node = invoke(["node", str(NODE_ADAPTER)], request, identifier)
    if python != node:
        raise DifferentialError(
            f"{identifier}: Python/Node disagreement\n"
            f"python={json.dumps(python, sort_keys=True)}\n"
            f"node={json.dumps(node, sort_keys=True)}"
        )
    expected = case["expected"]
    if python.get("accepted") is not expected["accepted"]:
        raise DifferentialError(f"{identifier}: decision differs from corpus expectation")
    if python["accepted"]:
        if set(python) != {"accepted", "projection", "schema"}:
            raise DifferentialError(f"{identifier}: accepted response members drifted")
        digest = sha256(canonical_json(python["projection"])).hexdigest()
        if digest != expected["projection_sha256"]:
            raise DifferentialError(f"{identifier}: accepted projection digest drifted")
    else:
        if set(python) != {"accepted", "error_code", "schema"}:
            raise DifferentialError(f"{identifier}: rejected response members drifted")
        if python["error_code"] != expected["error_code"]:
            raise DifferentialError(f"{identifier}: rejection code drifted")


def main() -> int:
    try:
        document = json.loads(CORPUS.read_bytes())
        for case in document["cases"]:
            compare_case(case)
    except (
        OSError,
        json.JSONDecodeError,
        KeyError,
        subprocess.SubprocessError,
        DifferentialError,
        ValueError,
    ) as error:
        print(f"signed-forwarding differential verification failed: {error}")
        return 1
    print(f"Python/PyNaCl and Node/OpenSSL agree on {len(document['cases'])} cases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
