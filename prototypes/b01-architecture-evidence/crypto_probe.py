#!/usr/bin/env python3
"""Machine-local real Ed25519 timing screen for the B01 preliminary evidence."""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import time
from collections.abc import Callable

import nacl
from nacl.exceptions import BadSignatureError
from nacl.signing import SigningKey

PRELIMINARY_SINGLE_VERIFY_BUDGET_US = 100_000
MAX_SIGNING_INPUT_BYTES = 1_420_000


class CryptoProbeError(RuntimeError):
    """One real-verification, rejection, mutation, or local-budget failure."""


def _percentile(values: list[int], numerator: int, denominator: int) -> int:
    ordered = sorted(values)
    index = min(len(ordered) - 1, (len(ordered) * numerator) // denominator)
    return ordered[index]


def _measure(action: Callable[[], None], iterations: int) -> list[int]:
    values: list[int] = []
    for _ in range(iterations):
        started = time.perf_counter_ns()
        action()
        values.append((time.perf_counter_ns() - started) // 1_000)
    return values


def _summary(values: list[int]) -> dict[str, int]:
    return {
        "iterations": len(values),
        "minimum_us": min(values),
        "median_us": int(statistics.median(values)),
        "p95_us": _percentile(values, 95, 100),
        "maximum_us": max(values),
    }


def _deadline_gate(observed_us: int) -> None:
    if observed_us > PRELIMINARY_SINGLE_VERIFY_BUDGET_US:
        raise CryptoProbeError(
            "local Ed25519 verification exceeded the preliminary screen budget"
        )


def build_result() -> dict[str, object]:
    signing_key = SigningKey(bytes(range(32)))
    verify_key = signing_key.verify_key
    cases = (
        ("empty", b"", 300),
        ("64k", b"x" * 65_536, 150),
        ("max_profile_input", b"x" * MAX_SIGNING_INPUT_BYTES, 40),
    )
    results: list[dict[str, object]] = []
    overall_max = 0
    for label, message, iterations in cases:
        signature = signing_key.sign(message).signature
        invalid = bytearray(signature)
        invalid[-1] ^= 1

        for _ in range(10):
            verify_key.verify(message, signature)

        valid_values = _measure(
            lambda: verify_key.verify(message, signature),
            iterations,
        )

        def reject_invalid() -> None:
            try:
                verify_key.verify(message, bytes(invalid))
            except BadSignatureError:
                return
            raise CryptoProbeError("mutated full-length signature was accepted")

        invalid_values = _measure(reject_invalid, iterations)
        case_max = max(max(valid_values), max(invalid_values))
        _deadline_gate(case_max)
        overall_max = max(overall_max, case_max)
        results.append(
            {
                "case": label,
                "message_bytes": len(message),
                "valid": _summary(valid_values),
                "invalid_full_length": _summary(invalid_values),
            }
        )

    try:
        _deadline_gate(PRELIMINARY_SINGLE_VERIFY_BUDGET_US + 1)
    except CryptoProbeError:
        detector_self_tested = True
    else:
        raise CryptoProbeError("deadline detector did not reject a seeded overrun")

    return {
        "schema": "ncp.b01-preliminary-ed25519-resource-result.v1",
        "algorithm": "Ed25519",
        "library": "PyNaCl",
        "pynacl_version": nacl.__version__,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "preliminary_single_verify_budget_us": PRELIMINARY_SINGLE_VERIFY_BUDGET_US,
        "largest_signing_input_bytes": MAX_SIGNING_INPUT_BYTES,
        "maximum_observed_us": overall_max,
        "deadline_detector_self_tested": detector_self_tested,
        "cases": results,
        "claim_boundary": (
            "These timings are a machine-local screen over fixed messages and real "
            "Ed25519 verification. They are not a production deadline, constant-time "
            "analysis, key-custody evidence, performance qualification, or guarantee."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.parse_args()
    print(json.dumps(build_result(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
