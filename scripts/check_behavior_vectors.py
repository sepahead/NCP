#!/usr/bin/env python3
"""Behavioral conformance — the Python binding vs the decision corpus.

Replays every vector in `conformance/behavior/vectors.json` through the
`ncp` PyO3 binding (the Python peer is the canonical Rust core, surfaced via
`ncp-python`) and asserts it produces the outcome the corpus declares — the same
outcomes `ncp-core/tests/behavior_conformance.rs` pins the reference to. So a
divergence in the binding (a mistranslated error path, a dropped boundary check)
fails here rather than in a downstream Python consumer.

Covered: check_version (accept/reject/raise), contract_status (advisory
match/mismatch/absent), validate (required-field + scientific-boundary), and the
safety governor (HOLD / ESTOP / speed-clamp / watchdog) decisions.

The `ncp` module is built by maturin (`maturin develop -m ncp-python/Cargo.toml
--features extension-module`), which CI does not yet run (see ROADMAP.md — the
cargo gate only `cargo check`s ncp-python). So when the module is absent this
SKIPS with exit 0 and a clear message, mirroring how the repo already treats the
unbuilt binding; where the wheel IS built (local dev, the future maturin job) it
runs and gates. Stdlib-only otherwise.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CORPUS = REPO / "conformance" / "behavior" / "vectors.json"


def _velocity_magnitude(frame: dict) -> float:
    data = frame.get("channels", {}).get("velocity_setpoint", {}).get("data", [])
    return math.sqrt(sum(c * c for c in data))


def main() -> int:
    try:
        import ncp  # built by maturin from ncp-python
    except ImportError:
        print(
            "SKIP check_behavior_vectors: the `ncp` binding is not built "
            "(maturin develop -m ncp-python/Cargo.toml --features extension-module). "
            "The Rust reference still gates this corpus via "
            "ncp-core/tests/behavior_conformance.rs."
        )
        return 0

    corpus = json.loads(CORPUS.read_text())
    cases = corpus["cases"]
    failures: list[str] = []

    def check(cond: bool, msg: str) -> None:
        if not cond:
            failures.append(msg)

    # ── check_version ────────────────────────────────────────────────────────
    for c in cases["check_version"]:
        name, inp, exp = c["name"], c["input"], c["expect"]
        try:
            got = ncp.check_version(inp["version"], inp["strict"])
            raised = False
        except ValueError:
            got, raised = None, True
        if exp.get("error"):
            check(raised, f"check_version[{name}]: expected raise, got {got!r}")
        else:
            check(
                not raised and got == exp["compatible"],
                f"check_version[{name}]: want compatible={exp['compatible']}, "
                f"got {'<raised>' if raised else got!r}",
            )

    # ── contract_status ──────────────────────────────────────────────────────
    for c in cases["contract_status"]:
        name, inp, exp = c["name"], c["input"], c["expect"]
        got = ncp.contract_status(inp["peer_hash"])
        check(got == exp["status"], f"contract_status[{name}]: want {exp['status']!r}, got {got!r}")

    # ── validate ─────────────────────────────────────────────────────────────
    for c in cases["validate"]:
        name, inp, exp = c["name"], c["input"], c["expect"]
        try:
            ncp.validate(inp["kind"], json.dumps(inp["message"]))
            ok = True
        except ValueError:
            ok = False
        check(ok == exp["valid"], f"validate[{name}]: want valid={exp['valid']}, got {ok}")

    # ── govern ───────────────────────────────────────────────────────────────
    for c in cases["govern"]:
        name, inp, exp = c["name"], c["input"], c["expect"]
        sensor = inp.get("sensor")
        out = json.loads(
            ncp.govern(
                json.dumps(inp["limits"]),
                json.dumps(inp["command"]),
                inp["now_s"],
                None if sensor is None else json.dumps(sensor),
                inp["last_sensor_s"],
            )
        )
        check(out["mode"] == exp["mode"], f"govern[{name}]: mode want {exp['mode']!r}, got {out['mode']!r}")
        if "velocity_setpoint_magnitude" in exp:
            mag = _velocity_magnitude(out)
            check(
                abs(mag - exp["velocity_setpoint_magnitude"]) < 1e-9,
                f"govern[{name}]: |velocity| want {exp['velocity_setpoint_magnitude']}, got {mag}",
            )

    total = sum(len(v) for v in cases.values())
    if failures:
        print(f"FAIL check_behavior_vectors: {len(failures)}/{total} behavioral vectors diverged:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"OK check_behavior_vectors: {total} behavioral vectors match the ncp binding")
    return 0


if __name__ == "__main__":
    sys.exit(main())
