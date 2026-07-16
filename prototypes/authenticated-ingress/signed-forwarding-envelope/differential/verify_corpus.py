#!/usr/bin/env python3
"""Verify the exact public-only corpus boundary before execution."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from prototype.strict import b64url_decode, sha256_hex  # noqa: E402

CORPUS = Path(__file__).with_name("corpus.v1.json")
SCHEMA = "ncp.prototype.signed-forwarding-differential-corpus.v1"
EXPECTED_IDS = {
    "accept-command",
    "accept-maximum-safe-forwarding-integer",
    "accept-overlap-next-key",
    "accept-overlap-old-key",
    "accept-step",
    "reject-a-direct-profile",
    "reject-algorithm-substitution",
    "reject-base64url-trailing-bits",
    "reject-carrier-entity-equals-signer",
    "reject-carrier-principal-equals-signer",
    "reject-changed-payload-bytes",
    "reject-duplicate-envelope-member",
    "reject-escaped-duplicate-request-member",
    "reject-expired-envelope",
    "reject-exponent-forwarding-integer",
    "reject-fractional-forwarding-integer",
    "reject-manifest-extra-field",
    "reject-manifest-wildcard",
    "reject-noncanonical-ed25519-s",
    "reject-nonascii-route-literal",
    "reject-negative-zero-forwarding-integer",
    "reject-padded-request-base64url",
    "reject-payload-session-mismatch",
    "reject-payload-stream-mismatch",
    "reject-protected-route-mismatch",
    "reject-removed-old-key",
    "reject-request-bom",
    "reject-request-invalid-utf8",
    "reject-small-order-public-key",
    "reject-unsafe-forwarding-integer",
    "reject-unprotected-key-selection",
}
FORBIDDEN_NAMES = {"private", "private_key", "secret", "seed", "signing_key"}


class CorpusError(ValueError):
    """The reviewed public corpus boundary drifted."""


def walk(value: object) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key.lower() in FORBIDDEN_NAMES:
                raise CorpusError(f"private-material field is forbidden: {key}")
            walk(child)
    elif isinstance(value, list):
        for child in value:
            walk(child)


def main() -> int:
    try:
        document = json.loads(CORPUS.read_bytes())
        if (
            document.get("schema") != SCHEMA
            or document.get("private_material_retained") is not False
        ):
            raise CorpusError("corpus schema or private-material declaration drifted")
        cases = document.get("cases")
        if not isinstance(cases, list) or not cases:
            raise CorpusError("corpus case list is missing")
        ids = {case.get("id") for case in cases if isinstance(case, dict)}
        if len(ids) != len(cases) or ids != EXPECTED_IDS:
            raise CorpusError(f"corpus identifiers differ: {ids!r}")
        walk(document)
        for case in cases:
            if set(case) != {"expected", "id", "note", "request_b64", "request_sha256"}:
                raise CorpusError(f"case {case.get('id')} members drifted")
            request = b64url_decode(case["request_b64"], maximum=2_200_000)
            if sha256_hex(request) != case["request_sha256"]:
                raise CorpusError(f"case {case['id']} request digest mismatch")
            expected = case["expected"]
            if expected.get("accepted") is True:
                if set(expected) != {"accepted", "projection_sha256"}:
                    raise CorpusError(f"accepted case {case['id']} expectation drifted")
            elif expected.get("accepted") is False:
                if set(expected) != {"accepted", "error_code"}:
                    raise CorpusError(f"rejected case {case['id']} expectation drifted")
            else:
                raise CorpusError(f"case {case['id']} has no exact decision")
    except (OSError, json.JSONDecodeError, CorpusError, ValueError) as error:
        print(f"differential corpus verification failed: {error}")
        return 1
    print(f"verified {len(cases)} public-only differential cases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
