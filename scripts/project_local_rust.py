#!/usr/bin/env python3
"""Project the narrow local Rust distribution without forking canonical code."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT / "local/rust"
SOURCES = {
    "src/modular_wire.rs": ("ncp-core/src/modular_wire.rs", "identity"),
    "src/modular_owner.rs": ("ncp-core/src/modular_owner.rs", "identity"),
    "src/modular_client.rs": ("ncp-core/src/modular_client.rs", "identity"),
    "src/modular_profile.v1.json": ("ncp-core/src/modular_profile.v1.json", "identity"),
    "tests/modular_owner.rs": ("ncp-core/tests/modular_owner.rs", "test_import_only"),
    "tests/modular_wire.rs": ("ncp-core/tests/modular_wire.rs", "test_import_only"),
    "tests/fixtures/modular-binary64.json": ("ncp-core/tests/fixtures/modular-binary64.json", "identity"),
    "tests/support/modular_fixture.rs": ("ncp-core/tests/support/modular_fixture.rs", "test_import_only"),
    "examples/modular_owner_probe.rs": ("ncp-core/examples/modular_owner_probe.rs", "test_import_only"),
    "examples/modular_buffer_probe.rs": ("ncp-core/examples/modular_buffer_probe.rs", "test_import_only"),
    "src/modular_buffer.rs": ("ncp-core/src/modular_buffer.rs", "identity"),
    "tests/modular_buffer.rs": ("ncp-core/tests/modular_buffer.rs", "test_import_only"),
    "src/local.rs": ("ncp-core/src/local.rs", "identity"),
    "src/local_data.rs": ("ncp-core/src/local_data.rs", "identity"),
    "src/bounded_json.rs": ("ncp-core/src/bounded_json.rs", "identity"),
    "src/canonical_digest.rs": ("ncp-core/src/canonical_digest.rs", "identity"),
    "local-profile.v1.json": ("ncp-core/local-profile.v1.json", "identity"),
    "tests/local.rs": ("ncp-core/tests/local.rs", "test_import_only"),
    "tests/local_binary64.rs": ("ncp-core/tests/local_binary64.rs", "test_import_only"),
    "tests/local_profile_contract.rs": (
        "ncp-core/tests/local_profile_contract.rs",
        "test_import_only",
    ),
    "tests/fixtures/local-profile-identity.json": (
        "ncp-core/tests/fixtures/local-profile-identity.json",
        "identity",
    ),
    "tests/fixtures/local-binary64.json": (
        "ncp-core/tests/fixtures/local-binary64.json",
        "identity",
    ),
    "examples/local_contract_probe.rs": (
        "ncp-core/examples/local_contract_probe.rs",
        "test_import_only",
    ),
    "LICENSE-MIT": ("LICENSE-MIT", "identity"),
    "LICENSE-APACHE": ("LICENSE-APACHE", "identity"),
}


def projected() -> dict[str, bytes]:
    outputs = {}
    rows = []
    for destination, (source, transform) in sorted(SOURCES.items()):
        original = (ROOT / source).read_bytes()
        result = original
        if transform == "test_import_only":
            result = original.replace(b"ncp_core::", b"ncp_local::")
            if result == original:
                raise ValueError(f"expected package import missing: {source}")
        elif transform != "identity":
            raise ValueError(f"unsupported transform: {transform}")
        outputs[destination] = result
        rows.append(
            {
                "source": source,
                "destination": destination,
                "transformation": transform,
                "source_sha256": hashlib.sha256(original).hexdigest(),
                "destination_sha256": hashlib.sha256(result).hexdigest(),
            }
        )
    manifest = {
        "schema": "ncp.local-rust-source-projection.v1",
        "scope": "source byte parity; not installed qualification or release authorization",
        "files": rows,
    }
    outputs["source-projection.v1.json"] = (
        json.dumps(manifest, indent=2) + "\n"
    ).encode()
    return outputs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    args = parser.parse_args()
    failures = []
    for name, content in projected().items():
        path = DESTINATION / name
        if args.write:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        elif not path.is_file() or path.read_bytes() != content:
            failures.append(name)
    if failures:
        for name in failures:
            print(f"local Rust projection differs: {name}")
        return 1
    print("local Rust source projection: exact parity")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
