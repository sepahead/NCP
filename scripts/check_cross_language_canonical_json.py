#!/usr/bin/env python3
"""Exact canonical-byte matrix for every stable all-surface wire-shape vector.

Rust is exercised directly by an integration-test report, Python through the
installed PyO3 wheel, C/C++ through the exported C ABI, and TypeScript through
the built independent validator/emitter. Python and C/C++ intentionally remain
labelled Rust FFI wrappers; this is binding and ordered-pair evidence, not four
independent implementations.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import importlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "conformance" / "manifest.v1.json"
VECTORS = ROOT / "conformance" / "vectors"
SURFACES = ("rust", "python-ffi", "cpp-ffi", "typescript")


class CheckError(RuntimeError):
    pass


def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=ROOT,
        check=True,
        text=True,
        **kwargs,
    )


def required_ids() -> set[str]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    result = {
        vector["id"]
        for vector in manifest["vectors"]
        if vector.get("required") is True
        and vector.get("stability") == "stable-1.0"
        and vector.get("suite") == "wire-shape"
        and set(SURFACES).issubset(
            set(vector.get("applicability", {}).get("implementations", []))
        )
    }
    if len(result) != 14:
        raise CheckError(
            f"expected 14 all-surface stable wire vectors, found {len(result)}"
        )
    return result


def source_vectors(expected: set[str]) -> dict[str, tuple[str, str]]:
    result: dict[str, tuple[str, str]] = {}
    for path in sorted(VECTORS.glob("*.json")):
        raw = path.read_text(encoding="utf-8")
        value = json.loads(raw)
        kind = value.get("kind")
        if not isinstance(kind, str):
            raise CheckError(f"{path}: no string kind")
        vector_id = f"wire/{kind}/canonical"
        if vector_id in result:
            raise CheckError(f"duplicate source vector {vector_id}")
        result[vector_id] = (kind, raw)
    if set(result) != expected:
        raise CheckError(
            f"source vector set mismatch: missing={sorted(expected - set(result))}, "
            f"extra={sorted(set(result) - expected)}"
        )
    return result


def rust_producer(temp: Path) -> dict[str, str]:
    report = temp / "rust-producer.json"
    environment = os.environ.copy()
    environment["NCP_CANONICAL_JSON_REPORT"] = str(report)
    run(
        [
            "cargo",
            "test",
            "-q",
            "-p",
            "ncp-core",
            "--locked",
            "--test",
            "canonical_json_bytes",
            "mandatory_wire_vectors_emit_deterministic_canonical_bytes",
            "--",
            "--exact",
        ],
        env=environment,
    )
    value = json.loads(report.read_text(encoding="utf-8"))
    if (
        value.get("schema") != "ncp.canonical-json-emission-report.v1"
        or value.get("implementation") != "rust"
        or not isinstance(value.get("vectors"), dict)
    ):
        raise CheckError("Rust producer emitted an invalid report")
    return value["vectors"]


def load_python_binding() -> object:
    try:
        binding = importlib.import_module("ncp")
    except ImportError as error:
        raise CheckError(
            "the installed candidate Python wheel is required; run this check with "
            "the wheel venv's python"
        ) from error
    if not callable(getattr(binding, "validate", None)):
        raise CheckError("installed ncp module has no validate function")
    return binding


def dynamic_library() -> Path:
    run(["cargo", "build", "-q", "-p", "ncp-cpp", "--locked"])
    candidates = [
        ROOT / "target" / "debug" / "libncp_cpp.so",
        ROOT / "target" / "debug" / "libncp_cpp.dylib",
        ROOT / "target" / "debug" / "ncp_cpp.dll",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise CheckError(
        f"ncp-cpp dynamic library not found at {[str(path) for path in candidates]}"
    )


def cpp_validator() -> Callable[[str, str], str]:
    library = ctypes.CDLL(str(dynamic_library()))
    library.ncp_validate.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
    library.ncp_validate.restype = ctypes.c_void_p
    library.ncp_string_free.argtypes = [ctypes.c_void_p]
    library.ncp_string_free.restype = None

    def validate(kind: str, encoded: str) -> str:
        pointer = library.ncp_validate(kind.encode("utf-8"), encoded.encode("utf-8"))
        if not pointer:
            raise CheckError(f"C/C++ FFI rejected {kind}")
        try:
            return ctypes.string_at(pointer).decode("utf-8")
        finally:
            library.ncp_string_free(pointer)

    # Keep the library alive through the closure.
    setattr(validate, "_library", library)
    return validate


def typescript_producer() -> dict[str, str]:
    run(["bun", "run", "build"], stdout=subprocess.DEVNULL)
    completed = run(
        ["node", "ncp-ts/scripts/emit-canonical-json.mjs"],
        stdout=subprocess.PIPE,
    )
    value = json.loads(completed.stdout)
    if (
        value.get("schema") != "ncp.canonical-json-emission-report.v1"
        or value.get("implementation") != "typescript"
        or not isinstance(value.get("vectors"), dict)
    ):
        raise CheckError("TypeScript producer emitted an invalid report")
    return value["vectors"]


def ensure_vector_set(label: str, vectors: dict[str, str], expected: set[str]) -> None:
    if set(vectors) != expected:
        raise CheckError(
            f"{label}: vector set mismatch: missing={sorted(expected - set(vectors))}, "
            f"extra={sorted(set(vectors) - expected)}"
        )
    for vector_id, encoded in vectors.items():
        if not isinstance(encoded, str):
            raise CheckError(f"{label} {vector_id}: canonical payload is not a string")
        encoded.encode("utf-8")


def consume_all(
    validator: Callable[[str, str], str],
    producers: dict[str, dict[str, str]],
) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for producer, vectors in producers.items():
        consumed: dict[str, str] = {}
        for vector_id, encoded in vectors.items():
            kind = vector_id.removeprefix("wire/").removesuffix("/canonical")
            consumed[vector_id] = validator(kind, encoded)
        result[producer] = consumed
    return result


def rust_consumer(
    temp: Path, producers: dict[str, dict[str, str]]
) -> dict[str, dict[str, str]]:
    matrix_input = temp / "producer-matrix.json"
    matrix_report = temp / "rust-consumer.json"
    matrix_input.write_text(
        json.dumps({"producers": producers}, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    environment = os.environ.copy()
    environment["NCP_CANONICAL_JSON_MATRIX_INPUT"] = str(matrix_input)
    environment["NCP_CANONICAL_JSON_MATRIX_REPORT"] = str(matrix_report)
    run(
        [
            "cargo",
            "test",
            "-q",
            "-p",
            "ncp-core",
            "--locked",
            "--test",
            "canonical_json_bytes",
            "optional_cross_language_producer_matrix_round_trips_through_rust",
            "--",
            "--exact",
        ],
        env=environment,
    )
    value = json.loads(matrix_report.read_text(encoding="utf-8"))
    if (
        value.get("schema") != "ncp.canonical-json-consumer-report.v1"
        or value.get("consumer") != "rust"
        or not isinstance(value.get("producers"), dict)
    ):
        raise CheckError("Rust consumer emitted an invalid matrix report")
    return value["producers"]


def typescript_consumer(
    producers: dict[str, dict[str, str]],
) -> dict[str, dict[str, str]]:
    completed = run(
        ["node", "ncp-ts/scripts/emit-canonical-json.mjs", "--consume"],
        input=json.dumps({"producers": producers}, separators=(",", ":")),
        stdout=subprocess.PIPE,
    )
    value = json.loads(completed.stdout)
    if (
        value.get("schema") != "ncp.canonical-json-consumer-report.v1"
        or value.get("consumer") != "typescript"
        or not isinstance(value.get("producers"), dict)
    ):
        raise CheckError("TypeScript consumer emitted an invalid matrix report")
    return value["producers"]


def verify_matrix(
    producers: dict[str, dict[str, str]],
    consumers: dict[str, dict[str, dict[str, str]]],
    expected_ids: set[str],
) -> list[str]:
    if set(producers) != set(SURFACES) or set(consumers) != set(SURFACES):
        raise CheckError("producer/consumer surface set is incomplete")
    ordered_pairs: list[str] = []
    for producer in SURFACES:
        reference = producers[producer]
        ensure_vector_set(f"producer {producer}", reference, expected_ids)
        for consumer in SURFACES:
            pair = f"{producer}->{consumer}"
            ordered_pairs.append(pair)
            consumed = consumers[consumer].get(producer)
            if not isinstance(consumed, dict):
                raise CheckError(f"missing ordered pair {pair}")
            ensure_vector_set(pair, consumed, expected_ids)
            for vector_id in sorted(expected_ids):
                if consumed[vector_id].encode("utf-8") != reference[vector_id].encode(
                    "utf-8"
                ):
                    raise CheckError(
                        f"{pair} {vector_id}: consumer changed canonical bytes"
                    )
                if consumed[vector_id] != producers["rust"][vector_id]:
                    raise CheckError(
                        f"{pair} {vector_id}: emitted bytes differ from Rust reference"
                    )
    expected_pairs = {
        f"{producer}->{consumer}" for producer in SURFACES for consumer in SURFACES
    }
    if set(ordered_pairs) != expected_pairs or len(ordered_pairs) != len(
        expected_pairs
    ):
        raise CheckError("ordered producer/consumer matrix is not exact")
    return ordered_pairs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--report", type=Path, help="optional non-normative summary report path"
    )
    args = parser.parse_args()

    expected = required_ids()
    sources = source_vectors(expected)
    binding = load_python_binding()
    cpp_validate = cpp_validator()

    with tempfile.TemporaryDirectory(prefix="ncp-canonical-matrix-") as directory:
        temp = Path(directory)
        producers = {
            "rust": rust_producer(temp),
            "python-ffi": {
                vector_id: binding.validate(kind, raw)
                for vector_id, (kind, raw) in sources.items()
            },
            "cpp-ffi": {
                vector_id: cpp_validate(kind, raw)
                for vector_id, (kind, raw) in sources.items()
            },
            "typescript": typescript_producer(),
        }
        for surface, vectors in producers.items():
            ensure_vector_set(f"producer {surface}", vectors, expected)

        def python_validate(kind: str, encoded: str) -> str:
            return binding.validate(kind, encoded)

        consumers = {
            "rust": rust_consumer(temp, producers),
            "python-ffi": consume_all(python_validate, producers),
            "cpp-ffi": consume_all(cpp_validate, producers),
            "typescript": typescript_consumer(producers),
        }
        ordered_pairs = verify_matrix(producers, consumers, expected)

    vector_hashes = {
        vector_id: hashlib.sha256(
            producers["rust"][vector_id].encode("utf-8")
        ).hexdigest()
        for vector_id in sorted(expected)
    }
    evidence = {
        "schema": "ncp.cross-language-canonical-json-report.v1",
        "surfaces": list(SURFACES),
        "independence": {
            "rust": "reference",
            "typescript": "independent-emitter-and-validator",
            "python-ffi": "rust-ffi-wrapper",
            "cpp-ffi": "rust-ffi-wrapper",
        },
        "vector_ids": sorted(expected),
        "canonical_sha256": vector_hashes,
        "ordered_pairs": ordered_pairs,
        "transmissions": len(ordered_pairs) * len(expected),
    }
    encoded_evidence = json.dumps(
        evidence, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    evidence["report_sha256"] = hashlib.sha256(encoded_evidence).hexdigest()
    if args.report is not None:
        args.report.write_text(
            json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    print(
        "OK cross-language canonical JSON: "
        f"{len(SURFACES)} producers x {len(SURFACES)} consumers x {len(expected)} vectors "
        f"= {evidence['transmissions']} exact byte-preserving transmissions; "
        f"report_sha256={evidence['report_sha256']}"
    )
    print(
        "NOTE python-ffi and cpp-ffi share the Rust codec and are not independent implementations"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (CheckError, subprocess.CalledProcessError, OSError, ValueError) as error:
        print(f"FAIL cross-language canonical JSON: {error}", file=sys.stderr)
        raise SystemExit(1) from error
