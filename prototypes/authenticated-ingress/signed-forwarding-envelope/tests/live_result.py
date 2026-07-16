#!/usr/bin/env python3
"""Emit one bounded machine-local result without private key material."""

from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

import nacl

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from prototype.forwarding import (
    MAX_MANIFEST_BYTES,
    MAX_OUTER_BYTES,
    MAX_PAYLOAD_BYTES,
    MAX_PROTECTED_BYTES,
    verify_and_commit,
)
from prototype.replay import MAX_REPLAY_DATABASE_BYTES, MAX_REPLAY_SCOPES, ReplayStore
from prototype.strict import b64url_decode
from tests.common import NOW, initialize_store, material


def main() -> int:
    started = time.monotonic_ns()
    measurements: list[dict[str, int]] = []
    for message_class in ("command_frame", "step_request"):
        value = material(message_class)
        with tempfile.TemporaryDirectory() as tmp:
            path, pinned = initialize_store(Path(tmp), value.owner)
            with ReplayStore.open(path, pinned) as store:
                accepted = verify_and_commit(
                    value.envelope,
                    manifest=value.manifest,
                    profile=value.profile,
                    carrier=value.carrier,
                    replay_store=store,
                    now_utc_ms=NOW,
                )
                pragmas = store.runtime_pragmas()
            outer = json.loads(value.envelope)
            measurements.append(
                {
                    "database": path.stat().st_size,
                    "envelope": len(value.envelope),
                    "manifest": len(value.manifest_bytes),
                    "payload": len(accepted.payload),
                    "protected": len(
                        b64url_decode(outer["protected"], maximum=MAX_PROTECTED_BYTES)
                    ),
                }
            )

    result = {
        "schema": "ncp.prototype.signed-forwarding-result.v1",
        "scope": "quarantined-local-feasibility",
        "profiles": ["command_frame", "step_request"],
        "crypto": {
            "algorithm": "Ed25519",
            "library": "PyNaCl",
            "pynacl_version": nacl.__version__,
            "signing_input_uses_received_encoded_strings": True,
        },
        "replay": {
            "sqlite_version": sqlite3.sqlite_version,
            "journal_mode": pragmas["journal_mode"],
            "synchronous": "FULL" if pragmas["synchronous"] == 2 else "UNKNOWN",
            "begin_mode": "IMMEDIATE",
            "conditional_upsert": True,
            "commit_before_handoff": True,
            "delivery_semantics": "at-most-once-with-explicit-crash-loss-window",
            "recovery_epoch_signed": True,
            "filesystem_rollback_detected": False,
            "scope_capacity": MAX_REPLAY_SCOPES,
        },
        "resources": {
            "accepted_messages": 2,
            "elapsed_microseconds_local": (time.monotonic_ns() - started) // 1_000,
            "largest_envelope_bytes": max(item["envelope"] for item in measurements),
            "largest_manifest_bytes": max(item["manifest"] for item in measurements),
            "largest_payload_bytes": max(item["payload"] for item in measurements),
            "largest_protected_bytes": max(item["protected"] for item in measurements),
            "largest_replay_database_bytes": max(item["database"] for item in measurements),
            "envelope_limit_bytes": MAX_OUTER_BYTES,
            "manifest_limit_bytes": MAX_MANIFEST_BYTES,
            "payload_limit_bytes": MAX_PAYLOAD_BYTES,
            "protected_limit_bytes": MAX_PROTECTED_BYTES,
            "replay_database_limit_bytes": MAX_REPLAY_DATABASE_BYTES,
        },
        "claim_boundary": {
            "ncp_authority_granted": False,
            "plant_action_granted": False,
            "production_security_proved": False,
            "filesystem_rollback_protection_proved": False,
            "independent_parser_gate_satisfied": True,
            "b04_complete": False,
            "release_gate_satisfied": False,
        },
    }
    print("NCP_FORWARDING_RESULT=" + json.dumps(result, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
