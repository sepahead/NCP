#!/usr/bin/env python3
"""Verify the machine-local forwarding prototype result."""

from __future__ import annotations

import json
import sys

PREFIX = "NCP_FORWARDING_RESULT="
SCHEMA = "ncp.prototype.signed-forwarding-result.v1"


class ResultError(ValueError):
    """A result crossed the reviewed resource or claim boundary."""


def _pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ResultError(f"duplicate result member {key!r}")
        result[key] = value
    return result


def _constant(token: str) -> None:
    raise ResultError(f"non-finite result token {token!r} is forbidden")


def verify(result: object) -> None:
    if not isinstance(result, dict) or result.get("schema") != SCHEMA:
        raise ResultError("result schema is missing or unknown")
    if set(result) != {
        "claim_boundary",
        "crypto",
        "profiles",
        "replay",
        "resources",
        "schema",
        "scope",
    }:
        raise ResultError("result members differ from the reviewed boundary")
    if result.get("scope") != "quarantined-local-feasibility":
        raise ResultError("result scope is not quarantined local feasibility")
    if result.get("profiles") != ["command_frame", "step_request"]:
        raise ResultError("both reviewed payload profiles were not exercised")
    if result.get("crypto") != {
        "algorithm": "Ed25519",
        "library": "PyNaCl",
        "pynacl_version": "1.6.2",
        "signing_input_uses_received_encoded_strings": True,
    }:
        raise ResultError("cryptographic result differs from the reviewed profile")
    replay = result.get("replay")
    if replay != {
        "sqlite_version": replay.get("sqlite_version") if isinstance(replay, dict) else None,
        "journal_mode": "wal",
        "synchronous": "FULL",
        "begin_mode": "IMMEDIATE",
        "conditional_upsert": True,
        "commit_before_handoff": True,
        "delivery_semantics": "at-most-once-with-explicit-crash-loss-window",
        "recovery_epoch_signed": True,
        "filesystem_rollback_detected": False,
        "scope_capacity": 128,
    }:
        raise ResultError("replay result differs from the reviewed boundary")
    if not isinstance(replay["sqlite_version"], str) or not replay["sqlite_version"]:
        raise ResultError("SQLite version observation is missing")

    resources = result.get("resources")
    if not isinstance(resources, dict):
        raise ResultError("resource measurements are missing")
    positive_fields = {
        "accepted_messages",
        "elapsed_microseconds_local",
        "largest_envelope_bytes",
        "largest_manifest_bytes",
        "largest_payload_bytes",
        "largest_protected_bytes",
        "largest_replay_database_bytes",
    }
    limit_fields = {
        "envelope_limit_bytes": 1_500_000,
        "manifest_limit_bytes": 65_536,
        "payload_limit_bytes": 1_048_576,
        "protected_limit_bytes": 16_384,
        "replay_database_limit_bytes": 8_388_608,
    }
    if set(resources) != positive_fields | set(limit_fields):
        raise ResultError("resource result members differ from the reviewed boundary")
    if any(
        not isinstance(resources.get(field), int)
        or isinstance(resources.get(field), bool)
        or resources[field] <= 0
        for field in positive_fields
    ):
        raise ResultError("a resource observation is absent or non-positive")
    if resources["accepted_messages"] != 2:
        raise ResultError("live run did not accept exactly two messages")
    if any(resources[field] != limit for field, limit in limit_fields.items()):
        raise ResultError("a predeclared resource limit drifted")
    observation_bounds = {
        "largest_envelope_bytes": 1_500_000,
        "largest_manifest_bytes": 65_536,
        "largest_payload_bytes": 1_048_576,
        "largest_protected_bytes": 16_384,
        "largest_replay_database_bytes": 8_388_608,
    }
    if any(resources[field] > limit for field, limit in observation_bounds.items()):
        raise ResultError("a resource observation exceeds its predeclared bound")

    claims = result.get("claim_boundary")
    expected_claims = {
        "ncp_authority_granted": False,
        "plant_action_granted": False,
        "production_security_proved": False,
        "filesystem_rollback_protection_proved": False,
        "independent_parser_gate_satisfied": False,
        "b04_complete": False,
        "release_gate_satisfied": False,
    }
    if claims != expected_claims:
        raise ResultError("claim boundary differs from the reviewed all-false result")


def extract(stream: str) -> object:
    lines = [line[len(PREFIX) :] for line in stream.splitlines() if line.startswith(PREFIX)]
    if len(lines) != 1:
        raise ResultError(f"expected exactly one result line, observed {len(lines)}")
    try:
        return json.loads(
            lines[0],
            object_pairs_hook=_pairs,
            parse_constant=_constant,
        )
    except ResultError:
        raise
    except json.JSONDecodeError as error:
        raise ResultError(f"result line is invalid JSON: {error}") from error


def main() -> int:
    try:
        result = extract(sys.stdin.read())
        verify(result)
    except ResultError as error:
        print(f"forwarding result verification failed: {error}")
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
