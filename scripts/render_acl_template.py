#!/usr/bin/env python3
"""Render the secure Zenoh router template for an exact NCP realm.

Zenoh does not interpolate an ``NCP_REALM`` environment variable inside ACL key
expressions. Leaving the template on ``ncp/...`` while peers use ``engram/ncp/...``
silently makes default-DENY reject legitimate traffic. This renderer performs the
single audited substitution and rejects realm key-expression injection.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile
import unicodedata
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_TEMPLATE = REPO / "deploy" / "zenoh-access-control.json5"
QUOTED_KEY = re.compile(r'"([^"\n]*(?:/session/|/rpc/)[^"\n]*)"')


def valid_segment(segment: str) -> bool:
    return bool(segment) and not any(
        char in "/*$#?" or char.isspace() or unicodedata.category(char).startswith("C")
        for char in segment
    )


def valid_realm(realm: str) -> bool:
    return bool(realm) and all(valid_segment(segment) for segment in realm.split("/"))


def render(text: str, realm: str) -> str:
    if not valid_realm(realm):
        raise ValueError(f"invalid NCP realm key prefix: {realm!r}")
    keys = QUOTED_KEY.findall(text)
    if not keys:
        raise ValueError("template contains no quoted NCP key expressions")
    foreign = [key for key in keys if not key.startswith("ncp/")]
    if foreign:
        raise ValueError(
            "template mixes the default realm with pre-rendered key expressions: "
            f"{foreign!r}"
        )
    rendered = text.replace('"ncp/', f'"{realm}/')
    rendered_keys = QUOTED_KEY.findall(rendered)
    if len(rendered_keys) != len(keys) or any(
        not key.startswith(f"{realm}/") for key in rendered_keys
    ):
        raise AssertionError("not every NCP key expression was rendered exactly once")
    return rendered


def _atomic_write(output: Path, rendered: str) -> None:
    """Write a complete config before replacing the destination.

    The temporary file is owner-only: rendered configs name certificate/key
    locations and are operational security material even though they contain no
    private-key bytes themselves.
    """
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{output.name}.", dir=output.parent)
    temporary_path = Path(temporary)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(rendered)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_path, 0o600)
        os.replace(temporary_path, output)
    finally:
        temporary_path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--realm", required=True, help="exact realm prefix, e.g. engram/ncp")
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--output", required=True, help="output path, or - for stdout")
    parser.add_argument("--force", action="store_true", help="replace an existing output file")
    args = parser.parse_args()

    try:
        rendered = render(args.template.read_text(encoding="utf-8"), args.realm)
    except (OSError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    if args.output == "-":
        sys.stdout.write(rendered)
        return 0

    output = Path(args.output)
    if output.exists() and not args.force:
        print(f"ERROR: refusing to replace {output}; pass --force", file=sys.stderr)
        return 2
    try:
        _atomic_write(output, rendered)
    except OSError as error:
        print(f"ERROR: could not write {output}: {error}", file=sys.stderr)
        return 2
    print(f"rendered realm {args.realm!r}: {args.template} -> {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
