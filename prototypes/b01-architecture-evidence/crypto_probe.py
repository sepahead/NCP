#!/usr/bin/env python3
"""Machine-local real Ed25519 timing screen for the B01 preliminary evidence."""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.metadata
import json
import platform
import statistics
import sys
import sysconfig
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import _cffi_backend
import nacl
import nacl._sodium
from nacl.exceptions import BadSignatureError
from nacl.signing import SigningKey

PRELIMINARY_SINGLE_VERIFY_BUDGET_US = 100_000
MAX_SIGNING_INPUT_BYTES = 1_420_000
ROOT = Path(__file__).resolve().parent
CRYPTO_PROJECT = ROOT.parent / "authenticated-ingress" / "signed-forwarding-envelope"
CLAIM_BOUNDARY = (
    "Thread and process CPU p95 values are machine-local computational tripwires "
    "over fixed messages and synchronous real Ed25519 verification calls. Maximum "
    "CPU and wall elapsed times are observations only. The process clock is retained "
    "to expose CPU used outside the calling thread. These measurements are not a "
    "production deadline, constant-time analysis, key-custody evidence, performance "
    "qualification, package-provenance result, or guarantee."
)


class CryptoProbeError(RuntimeError):
    """One real-verification, rejection, mutation, or local-budget failure."""


def _percentile(values: list[int], numerator: int, denominator: int) -> int:
    ordered = sorted(values)
    index = min(len(ordered) - 1, (len(ordered) * numerator) // denominator)
    return ordered[index]


def _measure(
    action: Callable[[], None], iterations: int
) -> tuple[list[int], list[int], list[int]]:
    thread_cpu_values: list[int] = []
    process_cpu_values: list[int] = []
    wall_values: list[int] = []
    for _ in range(iterations):
        wall_started = time.perf_counter_ns()
        process_cpu_started = time.process_time_ns()
        thread_cpu_started = time.thread_time_ns()
        action()
        thread_cpu_values.append((time.thread_time_ns() - thread_cpu_started) // 1_000)
        process_cpu_values.append(
            (time.process_time_ns() - process_cpu_started) // 1_000
        )
        wall_values.append((time.perf_counter_ns() - wall_started) // 1_000)
    return thread_cpu_values, process_cpu_values, wall_values


def _summary(values: list[int]) -> dict[str, int]:
    return {
        "iterations": len(values),
        "minimum_us": min(values),
        "median_us": int(statistics.median(values)),
        "p95_us": _percentile(values, 95, 100),
        "maximum_us": max(values),
    }


def _cpu_p95_budget_gate(observed_us: int) -> None:
    if observed_us > PRELIMINARY_SINGLE_VERIFY_BUDGET_US:
        raise CryptoProbeError(
            "local Ed25519 verification exceeded the preliminary CPU-p95 screen budget"
        )


def _clock_metadata(name: str) -> dict[str, Any]:
    information = time.get_clock_info(name)
    return {
        "adjustable": information.adjustable,
        "implementation": information.implementation,
        "monotonic": information.monotonic,
        "resolution_ns": max(1, round(information.resolution * 1_000_000_000)),
    }


def _file_identity(path: Path) -> dict[str, Any]:
    content = path.read_bytes()
    return {
        "path": path.relative_to(ROOT.parents[1]).as_posix(),
        "sha256": hashlib.sha256(content).hexdigest(),
        "bytes": len(content),
    }


def _artifact_identity(module: str, path_value: str | None) -> dict[str, Any]:
    if path_value is None:
        raise CryptoProbeError(f"loaded module {module} has no file identity")
    path = Path(path_value).resolve(strict=True)
    content = path.read_bytes()
    return {
        "module": module,
        "filename": path.name,
        "sha256": hashlib.sha256(content).hexdigest(),
        "bytes": len(content),
    }


def _distribution_identity(name: str) -> dict[str, Any]:
    distribution = importlib.metadata.distribution(name)
    files = distribution.files
    if files is None or not files:
        raise CryptoProbeError(f"{name} distribution file inventory is unavailable")
    environment_root = Path(sys.prefix).resolve(strict=True)
    entries: list[dict[str, Any]] = []
    total_bytes = 0
    for package_path in sorted(files, key=lambda item: item.as_posix()):
        relative = Path(package_path.as_posix())
        if relative.is_absolute():
            raise CryptoProbeError(f"{name} distribution file is absolute")
        path = Path(distribution.locate_file(package_path)).resolve(strict=True)
        if not path.is_relative_to(environment_root) or not path.is_file():
            raise CryptoProbeError(f"{name} distribution file is absent or unbounded")
        content = path.read_bytes()
        entries.append(
            {
                "path": package_path.as_posix(),
                "sha256": hashlib.sha256(content).hexdigest(),
                "bytes": len(content),
            }
        )
        total_bytes += len(content)
    manifest = json.dumps(
        entries,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    return {
        "name": distribution.metadata["Name"],
        "version": distribution.version,
        "files": len(entries),
        "bytes": total_bytes,
        "manifest_sha256": hashlib.sha256(manifest).hexdigest(),
    }


def _runtime_identity() -> dict[str, Any]:
    executable = Path(sys.executable).resolve(strict=True)
    executable_content = executable.read_bytes()
    soabi = sysconfig.get_config_var("SOABI")
    if not isinstance(soabi, str) or not soabi:
        raise CryptoProbeError("Python SOABI is unavailable")
    return {
        "python": {
            "implementation": platform.python_implementation(),
            "version": platform.python_version(),
            "build": sys.version,
            "cache_tag": sys.implementation.cache_tag,
            "soabi": soabi,
            "isolated": sys.flags.isolated == 1,
            "no_user_site": sys.flags.no_user_site == 1,
            "safe_path": bool(sys.flags.safe_path),
            "executable": {
                "filename": executable.name,
                "sha256": hashlib.sha256(executable_content).hexdigest(),
                "bytes": len(executable_content),
            },
        },
        "distributions": {
            "pynacl": _distribution_identity("PyNaCl"),
            "cffi": _distribution_identity("cffi"),
        },
        "loaded_native_artifacts": {
            "pynacl_sodium": _artifact_identity(
                "nacl._sodium",
                nacl._sodium.__file__,
            ),
            "cffi_backend": _artifact_identity(
                "_cffi_backend",
                _cffi_backend.__file__,
            ),
        },
    }


def _environment_identity() -> dict[str, Any]:
    return {
        "clock_metadata": {
            "thread_time": _clock_metadata("thread_time"),
            "process_time": _clock_metadata("process_time"),
            "perf_counter": _clock_metadata("perf_counter"),
        },
        "runtime_identity": _runtime_identity(),
    }


def build_result() -> dict[str, object]:
    environment = _environment_identity()
    signing_key = SigningKey(bytes(range(32)))
    verify_key = signing_key.verify_key
    cases = (
        ("empty", b"", 300),
        ("64k", b"x" * 65_536, 150),
        ("max_profile_input", b"x" * MAX_SIGNING_INPUT_BYTES, 40),
    )
    results: list[dict[str, object]] = []
    overall_thread_cpu_max = 0
    overall_process_cpu_max = 0
    overall_wall_max = 0
    overall_thread_cpu_p95_max = 0
    overall_process_cpu_p95_max = 0
    for label, message, iterations in cases:
        signature = signing_key.sign(message).signature
        invalid = bytearray(signature)
        invalid[-1] ^= 1

        for _ in range(10):
            verify_key.verify(message, signature)

        (
            valid_thread_cpu_values,
            valid_process_cpu_values,
            valid_wall_values,
        ) = _measure(
            lambda: verify_key.verify(message, signature),
            iterations,
        )

        def reject_invalid() -> None:
            try:
                verify_key.verify(message, bytes(invalid))
            except BadSignatureError:
                return
            raise CryptoProbeError("mutated full-length signature was accepted")

        (
            invalid_thread_cpu_values,
            invalid_process_cpu_values,
            invalid_wall_values,
        ) = _measure(reject_invalid, iterations)
        valid_thread_summary = _summary(valid_thread_cpu_values)
        invalid_thread_summary = _summary(invalid_thread_cpu_values)
        valid_process_summary = _summary(valid_process_cpu_values)
        invalid_process_summary = _summary(invalid_process_cpu_values)
        valid_wall_summary = _summary(valid_wall_values)
        invalid_wall_summary = _summary(invalid_wall_values)
        case_thread_cpu_p95 = max(
            valid_thread_summary["p95_us"],
            invalid_thread_summary["p95_us"],
        )
        case_process_cpu_p95 = max(
            valid_process_summary["p95_us"],
            invalid_process_summary["p95_us"],
        )
        _cpu_p95_budget_gate(max(case_thread_cpu_p95, case_process_cpu_p95))
        overall_thread_cpu_max = max(
            overall_thread_cpu_max,
            valid_thread_summary["maximum_us"],
            invalid_thread_summary["maximum_us"],
        )
        overall_process_cpu_max = max(
            overall_process_cpu_max,
            valid_process_summary["maximum_us"],
            invalid_process_summary["maximum_us"],
        )
        overall_wall_max = max(
            overall_wall_max,
            valid_wall_summary["maximum_us"],
            invalid_wall_summary["maximum_us"],
        )
        overall_thread_cpu_p95_max = max(
            overall_thread_cpu_p95_max,
            case_thread_cpu_p95,
        )
        overall_process_cpu_p95_max = max(
            overall_process_cpu_p95_max,
            case_process_cpu_p95,
        )
        results.append(
            {
                "case": label,
                "message_bytes": len(message),
                "valid_thread_cpu": valid_thread_summary,
                "invalid_full_length_thread_cpu": invalid_thread_summary,
                "valid_process_cpu": valid_process_summary,
                "invalid_full_length_process_cpu": invalid_process_summary,
                "valid_wall": valid_wall_summary,
                "invalid_full_length_wall": invalid_wall_summary,
            }
        )

    try:
        _cpu_p95_budget_gate(PRELIMINARY_SINGLE_VERIFY_BUDGET_US + 1)
    except CryptoProbeError:
        cpu_p95_budget_detector_self_tested = True
    else:
        raise CryptoProbeError(
            "CPU-p95 budget detector did not reject a seeded overrun"
        )

    return {
        "schema": "ncp.b01-preliminary-ed25519-resource-result.v4",
        "algorithm": "Ed25519",
        "library": "PyNaCl",
        "pynacl_version": nacl.__version__,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "measurement_clocks": {
            "budget": ["thread_time_ns", "process_time_ns"],
            "observational": "perf_counter_ns",
        },
        "clock_metadata": environment["clock_metadata"],
        "execution_model": "synchronous-pynacl-verify-key-call",
        "runtime_project": {
            "pyproject": _file_identity(CRYPTO_PROJECT / "pyproject.toml"),
            "lock": _file_identity(CRYPTO_PROJECT / "uv.lock"),
        },
        "runtime_identity": environment["runtime_identity"],
        "preliminary_single_verify_cpu_p95_budget_us": (
            PRELIMINARY_SINGLE_VERIFY_BUDGET_US
        ),
        "largest_signing_input_bytes": MAX_SIGNING_INPUT_BYTES,
        "maximum_observed_thread_cpu_us": overall_thread_cpu_max,
        "maximum_observed_process_cpu_us": overall_process_cpu_max,
        "maximum_observed_wall_us": overall_wall_max,
        "maximum_observed_thread_cpu_p95_us": overall_thread_cpu_p95_max,
        "maximum_observed_process_cpu_p95_us": overall_process_cpu_p95_max,
        "cpu_p95_budget_detector_self_tested": (cpu_p95_budget_detector_self_tested),
        "result_validator_self_tested": False,
        "cases": results,
        "claim_boundary": CLAIM_BOUNDARY,
    }


def _validate_summary(value: Any, iterations: int) -> None:
    if not isinstance(value, dict) or set(value) != {
        "iterations",
        "minimum_us",
        "median_us",
        "p95_us",
        "maximum_us",
    }:
        raise CryptoProbeError("timing summary shape drifted")
    if (
        value["iterations"] != iterations
        or not all(
            isinstance(value[name], int) and not isinstance(value[name], bool)
            for name in ("minimum_us", "median_us", "p95_us", "maximum_us")
        )
        or not (
            0
            <= value["minimum_us"]
            <= value["median_us"]
            <= value["p95_us"]
            <= value["maximum_us"]
        )
    ):
        raise CryptoProbeError("timing summary is invalid or nonmonotonic")


def validate_result(value: Any) -> None:
    if not isinstance(value, dict):
        raise CryptoProbeError("result is not an object")
    if (
        value.get("schema") != "ncp.b01-preliminary-ed25519-resource-result.v4"
        or value.get("algorithm") != "Ed25519"
        or value.get("library") != "PyNaCl"
        or value.get("pynacl_version") != "1.6.2"
        or value.get("measurement_clocks")
        != {
            "budget": ["thread_time_ns", "process_time_ns"],
            "observational": "perf_counter_ns",
        }
        or value.get("execution_model") != "synchronous-pynacl-verify-key-call"
        or value.get("claim_boundary") != CLAIM_BOUNDARY
        or value.get("preliminary_single_verify_cpu_p95_budget_us")
        != PRELIMINARY_SINGLE_VERIFY_BUDGET_US
        or value.get("largest_signing_input_bytes") != MAX_SIGNING_INPUT_BYTES
        or value.get("cpu_p95_budget_detector_self_tested") is not True
        or value.get("result_validator_self_tested") is not True
    ):
        raise CryptoProbeError("result identity or claim boundary drifted")
    expected_runtime = {
        "pyproject": _file_identity(CRYPTO_PROJECT / "pyproject.toml"),
        "lock": _file_identity(CRYPTO_PROJECT / "uv.lock"),
    }
    if value.get("runtime_project") != expected_runtime:
        raise CryptoProbeError("runtime project identity drifted")
    if value.get("runtime_identity") != _runtime_identity():
        raise CryptoProbeError("executed runtime identity drifted")
    clock_metadata = value.get("clock_metadata")
    if clock_metadata != _environment_identity()["clock_metadata"]:
        raise CryptoProbeError("clock metadata drifted from the measured clocks")
    cases = value.get("cases")
    expected_cases = (
        ("empty", 0, 300),
        ("64k", 65_536, 150),
        ("max_profile_input", 1_420_000, 40),
    )
    if not isinstance(cases, list) or len(cases) != len(expected_cases):
        raise CryptoProbeError("case inventory drifted")
    summary_fields = (
        "valid_thread_cpu",
        "invalid_full_length_thread_cpu",
        "valid_process_cpu",
        "invalid_full_length_process_cpu",
        "valid_wall",
        "invalid_full_length_wall",
    )
    for case, (label, message_bytes, iterations) in zip(
        cases, expected_cases, strict=True
    ):
        if (
            not isinstance(case, dict)
            or case.get("case") != label
            or case.get("message_bytes") != message_bytes
            or set(case) != {"case", "message_bytes", *summary_fields}
        ):
            raise CryptoProbeError("case identity or shape drifted")
        for field in summary_fields:
            _validate_summary(case[field], iterations)
        _cpu_p95_budget_gate(
            max(
                case["valid_thread_cpu"]["p95_us"],
                case["invalid_full_length_thread_cpu"]["p95_us"],
                case["valid_process_cpu"]["p95_us"],
                case["invalid_full_length_process_cpu"]["p95_us"],
            )
        )
    aggregate_fields = {
        "maximum_observed_thread_cpu_us": max(
            case[field]["maximum_us"]
            for case in cases
            for field in ("valid_thread_cpu", "invalid_full_length_thread_cpu")
        ),
        "maximum_observed_process_cpu_us": max(
            case[field]["maximum_us"]
            for case in cases
            for field in ("valid_process_cpu", "invalid_full_length_process_cpu")
        ),
        "maximum_observed_wall_us": max(
            case[field]["maximum_us"]
            for case in cases
            for field in ("valid_wall", "invalid_full_length_wall")
        ),
        "maximum_observed_thread_cpu_p95_us": max(
            case[field]["p95_us"]
            for case in cases
            for field in ("valid_thread_cpu", "invalid_full_length_thread_cpu")
        ),
        "maximum_observed_process_cpu_p95_us": max(
            case[field]["p95_us"]
            for case in cases
            for field in ("valid_process_cpu", "invalid_full_length_process_cpu")
        ),
    }
    if any(
        value.get(field) != expected for field, expected in aggregate_fields.items()
    ):
        raise CryptoProbeError("aggregate timing summary drifted")


def self_test(value: dict[str, object]) -> None:
    value["result_validator_self_tested"] = True
    validate_result(value)
    mutations: tuple[tuple[tuple[str, ...], Any], ...] = (
        (("measurement_clocks", "budget"), ["perf_counter_ns"]),
        (("runtime_project", "lock", "sha256"), "0" * 64),
        (("runtime_identity", "python", "executable", "sha256"), "0" * 64),
        (
            (
                "runtime_identity",
                "loaded_native_artifacts",
                "pynacl_sodium",
                "sha256",
            ),
            "0" * 64,
        ),
        (("clock_metadata", "thread_time", "implementation"), "FORGED"),
        (
            ("maximum_observed_process_cpu_p95_us",),
            PRELIMINARY_SINGLE_VERIFY_BUDGET_US + 1,
        ),
    )
    for path, replacement in mutations:
        hostile = copy.deepcopy(value)
        cursor: Any = hostile
        for member in path[:-1]:
            cursor = cursor[member]
        cursor[path[-1]] = replacement
        try:
            validate_result(hostile)
        except CryptoProbeError:
            continue
        raise CryptoProbeError(f"result-validator mutation survived: {'.'.join(path)}")


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--self-test", action="store_true")
    mode.add_argument("--runtime-identity", action="store_true")
    arguments = parser.parse_args()
    if arguments.runtime_identity:
        print(json.dumps(_environment_identity(), sort_keys=True))
        return 0
    result = build_result()
    if arguments.self_test:
        self_test(result)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
