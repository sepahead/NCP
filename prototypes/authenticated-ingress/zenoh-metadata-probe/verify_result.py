#!/usr/bin/env python3
"""Reject any live Zenoh observation that differs from the reviewed boundary."""

from __future__ import annotations

import json
import sys
from pathlib import Path


EXPECTED = Path(__file__).with_name("expected-result.v1.json")


class ResultVerificationError(ValueError):
    """The live result differs from the reviewed local boundary."""


def verify(observed: object, expected: object) -> None:
    if observed != expected:
        raise ResultVerificationError(
            "metadata-probe result differs from expected-result.v1.json"
        )


def main() -> int:
    try:
        expected = json.loads(EXPECTED.read_text(encoding="utf-8"))
        observed = json.load(sys.stdin)
    except (OSError, json.JSONDecodeError) as error:
        print(f"metadata-probe result is not readable JSON: {error}", file=sys.stderr)
        return 1
    try:
        verify(observed, expected)
    except ResultVerificationError as error:
        print(str(error), file=sys.stderr)
        print(
            json.dumps({"expected": expected, "observed": observed}, indent=2),
            file=sys.stderr,
        )
        return 1
    print(json.dumps(observed, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
