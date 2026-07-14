#!/usr/bin/env python3
"""Report the current native-1.0 cross-language smoke-test disposition.

The former runner launched Engram's legacy mock bridge and sent pre-1.0 lifecycle
requests from Python and Rust. That path cannot exercise the 1.0 identity, security,
session-generation, authority, operation, or receipt contract and is deliberately
quarantined here instead of being presented as current interoperability evidence.

Exit status 2 means NOT RUN. It is intentionally nonzero so a missing or incompatible
peer cannot make CI green. Exit status 0 is reserved for a future complete native-1.0
run after this entrypoint is replaced with compatible installed peers and retained
evidence; this guard never returns it.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Sequence


NCP_ROOT = Path(__file__).resolve().parents[1]
NOT_RUN = 2
ENGRAM_BRIDGE = Path("backend/neurocontrol/bridge_server.py")


def prerequisite_gaps(engram: Path) -> tuple[str, ...]:
    """Return the blockers that prevent a native-1.0 cross-language run."""

    bridge = engram / ENGRAM_BRIDGE
    if bridge.is_file():
        service_gap = (
            f"{bridge} exists, but file presence does not establish a native-1.0 "
            "SessionService; the previously assumed MockBackend lifecycle is legacy "
            "migration input and is not executed by this candidate runner"
        )
    else:
        service_gap = (
            f"no native-1.0 Engram SessionService is available at {bridge}; "
            "set --engram only to inspect an explicit checkout"
        )
    return (
        service_gap,
        "no compatible installed Rust peer is registered; the incompatible legacy "
        "TCP example was removed instead of retaining an unbounded pre-1.0 client",
        "live production-secure identity/ACL/certificate evidence remains NOT RUN",
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Report why the native-1.0 cross-language smoke is NOT RUN."
    )
    parser.add_argument(
        "--engram",
        default=os.environ.get("ENGRAM_ROOT", str(NCP_ROOT.parent / "engram")),
        help="Engram checkout to inspect; it is never inferred compatible from file presence",
    )
    args = parser.parse_args(argv)

    print("=== native-1.0 cross-language developer smoke ===")
    print("RESULT: NOT RUN")
    for gap in prerequisite_gaps(Path(args.engram)):
        print(f"- {gap}")
    print("No server or peer process was started; no interoperability PASS was recorded.")
    return NOT_RUN


if __name__ == "__main__":
    raise SystemExit(main())
