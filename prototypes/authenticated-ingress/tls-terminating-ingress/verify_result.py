#!/usr/bin/env python3
"""Extract and verify the machine-local TLS-ingress result."""

from __future__ import annotations

import json
import sys


PREFIX = "NCP_TLS_INGRESS_RESULT="
SCHEMA = "ncp.prototype.tls-terminating-ingress-result.v1"


class ResultVerificationError(ValueError):
    """The live result crossed its reviewed claim or resource boundary."""


def verify(result: object) -> None:
    if not isinstance(result, dict) or result.get("schema") != SCHEMA:
        raise ResultVerificationError("result schema is missing or unknown")
    if result.get("scope") != "quarantined-local-feasibility":
        raise ResultVerificationError("result scope is not quarantined local feasibility")

    tls = result.get("tls")
    if tls != {
        "version": "1.3",
        "provider": "ring",
        "client_certificate_required": True,
        "alpn": "ncp-prototype-a/1",
        "tickets_sent": 0,
        "resumption_accepted": False,
        "zero_rtt_accepted": False,
    }:
        raise ResultVerificationError("TLS result differs from the reviewed exact profile")

    binding = result.get("binding")
    if not isinstance(binding, dict):
        raise ResultVerificationError("binding result is missing")
    expected_true = {
        "exact_leaf_der_sha256",
        "manifest_default_deny",
        "payload_identity_exact_match",
        "same_immutable_payload",
    }
    if any(binding.get(field) is not True for field in expected_true):
        raise ResultVerificationError("a required binding observation is false or absent")
    if binding.get("manifest_generation") != 1 or binding.get("context_serialized") is not False:
        raise ResultVerificationError("binding generation or serialization boundary drifted")

    replay = result.get("replay_probe")
    if replay != {
        "ingress_admitted_identical_messages": 2,
        "duplicate_observations": [False, True],
        "durable": False,
        "affects_admission": False,
    }:
        raise ResultVerificationError("volatile replay observation differs from the review")

    resources = result.get("resources")
    if not isinstance(resources, dict):
        raise ResultVerificationError("resource measurements are missing")
    for field in (
        "manifest_bytes",
        "manifest_limit_bytes",
        "payload_bytes",
        "frame_limit_bytes",
        "connections",
        "elapsed_microseconds_local",
    ):
        value = resources.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise ResultVerificationError(f"resource measurement {field} is not positive")
    if resources["manifest_bytes"] > resources["manifest_limit_bytes"]:
        raise ResultVerificationError("manifest observation exceeds its pre-allocation limit")
    if resources["payload_bytes"] > resources["frame_limit_bytes"]:
        raise ResultVerificationError("payload observation exceeds its pre-allocation limit")
    if resources["connections"] != 2:
        raise ResultVerificationError("live result did not use exactly two connections")

    claim_boundary = result.get("claim_boundary")
    if not isinstance(claim_boundary, dict) or not claim_boundary:
        raise ResultVerificationError("claim boundary is missing")
    if any(value is not False for value in claim_boundary.values()):
        raise ResultVerificationError("a forbidden production, authority, or release claim is true")


def extract(stream: str) -> object:
    matches = [
        line[len(PREFIX) :]
        for line in stream.splitlines()
        if line.startswith(PREFIX)
    ]
    if len(matches) != 1:
        raise ResultVerificationError(
            f"expected exactly one {PREFIX!r} line, observed {len(matches)}"
        )
    try:
        return json.loads(matches[0])
    except json.JSONDecodeError as error:
        raise ResultVerificationError(f"result line is invalid JSON: {error}") from error


def main() -> int:
    try:
        result = extract(sys.stdin.read())
        verify(result)
    except ResultVerificationError as error:
        print(f"TLS-ingress result verification failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
