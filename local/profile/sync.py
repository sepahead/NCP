"""Copy the canonical descriptor into the independent Python artifact."""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    source = root / "ncp-core/local-profile.v1.json"
    target = root / "local/python/ncp_local/local-profile.v1.json"
    contents = source.read_bytes()
    if not 0 < len(contents) <= 65_536:
        raise SystemExit("canonical local descriptor exceeds its frame bound")
    if args.check:
        if target.read_bytes() != contents:
            raise SystemExit("Python descriptor differs from canonical source")
        print("local descriptor copy: exact byte parity")
    else:
        target.write_bytes(contents)
        print("local descriptor copy: synchronized")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
