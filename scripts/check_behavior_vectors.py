#!/usr/bin/env python3
"""Behavioral conformance — the Python binding vs the decision corpus.

Replays every vector in `conformance/behavior/vectors.json` through the
`ncp` PyO3 binding (the Python peer is the canonical Rust core, surfaced via
`ncp-python`) and asserts it produces the outcome the corpus declares — the same
outcomes `ncp-core/tests/behavior_conformance.rs` pins the reference to. So a
divergence in the binding (a mistranslated error path, a dropped boundary check)
fails here rather than in a downstream Python consumer.

Covered: check_version (accept/reject/raise), contract_status (advisory
match/mismatch/absent), validate (required-field + scientific-boundary), the
safety governor (HOLD / ESTOP / speed-clamp / watchdog), and the plant-side
ActionBuffer (TTL / replay / horizon / ESTOP) decisions.

The `ncp` module is built by maturin. Hosted CI and `scripts/check.sh` install the
locked wheel and set `NCP_REQUIRE_BINDING=1`, so an absent binding is a hard gate
failure there. A bare developer invocation may still skip with a clear message
when no wheel is installed; that convenience skip is not release evidence.
Stdlib-only otherwise.
"""
from __future__ import annotations

import json
import math
import os
import sys
from copy import deepcopy
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CORPUS = REPO / "conformance" / "behavior" / "vectors.json"
MANIFEST = REPO / "conformance" / "manifest.v1.json"
WIRE_VECTORS = REPO / "conformance" / "vectors"
REQUEST_DIGEST_VECTORS = REPO / "conformance" / "request-digest" / "v1.json"


def _parse_int_preserve_negative_zero(token: str) -> int | float:
    return -0.0 if token == "-0" else int(token, 10)


def _apply_digest_case(base: dict, case: dict) -> dict:
    request = deepcopy(base)
    for patch in case["patch"]:
        parent = request
        for segment in patch["path"][:-1]:
            parent = parent[segment]
        leaf = patch["path"][-1]
        if patch["op"] == "set":
            parent[leaf] = patch["value"]
        elif patch["op"] == "remove":
            del parent[leaf]
        else:
            raise AssertionError(f"unknown request-digest patch op {patch['op']!r}")
    return request


def _velocity_magnitude(frame: dict) -> float:
    data = frame.get("channels", {}).get("velocity_setpoint", {}).get("data", [])
    return math.sqrt(sum(c * c for c in data))


def main() -> int:
    # In the maturin CI job the binding MUST be importable — NCP_REQUIRE_BINDING=1
    # turns the skip into a hard failure, so this gate can never silently pass green
    # because the wheel wasn't built (skip-as-pass). The bare cargo job leaves the
    # skip intact (the Rust/C++ runners gate the corpus there regardless).
    require = os.environ.get("NCP_REQUIRE_BINDING") == "1"
    try:
        import ncp  # built by maturin from ncp-python
    except ImportError:
        if require:
            print(
                "FAIL check_behavior_vectors: NCP_REQUIRE_BINDING=1 but the `ncp` binding "
                "is not importable — build it with `maturin develop -m "
                "ncp-python/Cargo.toml --features extension-module`."
            )
            return 1
        print(
            "SKIP check_behavior_vectors: the `ncp` binding is not built "
            "(maturin develop -m ncp-python/Cargo.toml --features extension-module). "
            "The Rust/C++ runners still gate this corpus."
        )
        return 0

    corpus = json.loads(CORPUS.read_text())
    manifest = json.loads(MANIFEST.read_text())
    request_digest_vectors = json.loads(
        REQUEST_DIGEST_VECTORS.read_text(), parse_int=_parse_int_preserve_negative_zero
    )
    cases = corpus["cases"]
    failures: list[str] = []
    executed: set[str] = set()

    def check(cond: bool, msg: str) -> None:
        if not cond:
            failures.append(msg)

    # The binding's pinned constants must match the corpus header (the same pins the
    # TS runner asserts) — proves the wheel embeds the contract the corpus describes.
    check(
        corpus["ncp_version"] == ncp.NCP_VERSION,
        f"corpus ncp_version {corpus['ncp_version']} != ncp.NCP_VERSION {ncp.NCP_VERSION}",
    )
    check(
        corpus["contract_hash"] == ncp.CONTRACT_HASH,
        f"corpus contract_hash {corpus['contract_hash']} != ncp.CONTRACT_HASH {ncp.CONTRACT_HASH}",
    )

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
        executed.add(f"behavior/check_version/{name}")

    # ── contract_status ──────────────────────────────────────────────────────
    for c in cases["contract_status"]:
        name, inp, exp = c["name"], c["input"], c["expect"]
        got = ncp.contract_status(inp["peer_hash"])
        check(got == exp["status"], f"contract_status[{name}]: want {exp['status']!r}, got {got!r}")
        executed.add(f"behavior/contract_status/{name}")

    # ── validate ─────────────────────────────────────────────────────────────
    for c in cases["validate"]:
        name, inp, exp = c["name"], c["input"], c["expect"]
        try:
            ncp.validate(inp["kind"], json.dumps(inp["message"]))
            ok = True
        except ValueError:
            ok = False
        check(ok == exp["valid"], f"validate[{name}]: want valid={exp['valid']}, got {ok}")
        executed.add(f"behavior/validate/{name}")

    # ── request-digest-v1 ───────────────────────────────────────────────────
    for case in request_digest_vectors["cases"]:
        request = _apply_digest_case(request_digest_vectors["base_request"], case)
        try:
            got = ncp.request_digest(json.dumps(request, ensure_ascii=False))
        except ValueError as error:
            failures.append(f"request-digest[{case['id']}]: raised {error}")
            got = None
        check(
            got == case["expected_digest"],
            f"request-digest[{case['id']}]: want {case['expected_digest']}, got {got}",
        )
        executed.add(f"request-digest/{case['id']}")

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
        executed.add(f"behavior/govern/{name}")

    # ── action_buffer ────────────────────────────────────────────────────────
    for c in cases["action_buffer"]:
        name = c["name"]
        buffer = ncp.ActionBuffer()
        for index, operation in enumerate(c["operations"]):
            op = operation["op"]
            if op == "command":
                buffer.on_command(operation["now_s"], json.dumps(operation["command"]))
            elif op == "reset":
                buffer.reset()
            elif op == "active":
                active_json = buffer.active(operation["now_s"])
                expect = operation["expect"]
                active = active_json is not None
                check(
                    active == expect["active"],
                    f"action_buffer[{name}] operation {index}: active want "
                    f"{expect['active']}, got {active}",
                )
                if active_json is not None and "value" in expect:
                    channels = json.loads(active_json)
                    got = channels["velocity_setpoint"]["data"][0]
                    check(
                        abs(got - expect["value"]) < 1e-9,
                        f"action_buffer[{name}] operation {index}: value want "
                        f"{expect['value']}, got {got}",
                    )
                check(
                    buffer.is_estopped() == expect["estopped"],
                    f"action_buffer[{name}] operation {index}: estopped want "
                    f"{expect['estopped']}, got {buffer.is_estopped()}",
                )
            else:
                failures.append(f"action_buffer[{name}] operation {index}: unknown op {op!r}")
        executed.add(f"behavior/action_buffer/{name}")

    for path in sorted(WIRE_VECTORS.glob("*.json")):
        message = json.loads(path.read_text())
        kind = message.get("kind")
        try:
            ncp.validate(kind, json.dumps(message))
        except ValueError as error:
            failures.append(f"wire[{path.name}]: canonical vector rejected: {error}")
        executed.add(f"wire/{kind}/canonical")

    required = {
        vector["id"]
        for vector in manifest["vectors"]
        if vector.get("required") is True
        and vector.get("stability") == "stable-1.0"
        and "python-ffi" in vector["applicability"]["implementations"]
    }
    for vector_id in sorted(required - executed):
        failures.append(f"manifest: required Python vector {vector_id} was skipped")
    for vector_id in sorted(executed - required):
        failures.append(f"manifest: unrecognized extra Python vector {vector_id}")

    total = sum(len(v) for v in cases.values()) + len(request_digest_vectors["cases"])
    if failures:
        print(f"FAIL check_behavior_vectors: {len(failures)}/{total} behavioral vectors diverged:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(
        f"OK check_behavior_vectors: {total} behavioral + 14 canonical wire vectors "
        "match the ncp binding with zero manifest skips"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
