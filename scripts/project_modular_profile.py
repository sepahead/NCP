#!/usr/bin/env python3
"""Copy exact modular descriptor bytes into the independent Python distribution."""
from __future__ import annotations
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    source = (ROOT / "ncp-core/src/modular_profile.v1.json").read_bytes()
    output = b'"""Generated exact descriptor bytes. This file grants no release authority."""\n\nCORE_DESCRIPTOR = ' + repr(source).encode("ascii") + b"\n"
    target = ROOT / "local/python/ncp_local/modular_profile.py"
    if args.write:
        target.write_bytes(output)
    elif not target.is_file() or target.read_bytes() != output:
        print("modular Python descriptor projection differs")
        return 1
    print("modular Python descriptor: exact source bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
