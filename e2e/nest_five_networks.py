#!/usr/bin/env python3
"""Drive five NEST model families through a native NCP 1.0 lifecycle service.

This is a developer smoke runner, not release interoperability or scientific
validation.  It requires a separately started, native-wire-1.0 service with the
dev-loopback security profile, pre-provisioned authority, idempotent operations,
and complete terminal receipts.  Engram's current wire-0.8 bridge is not such a
service and must not be used as an implicit compatibility fallback.
"""

from __future__ import annotations

import ipaddress
import json
import os
import socket
import sys
import time
import uuid
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from check_request_digests import request_digest  # noqa: E402
from e2e.bounded_json import (  # noqa: E402
    MAX_FRAME_BYTES,
    SAFE_INTEGER_MAX,
    BoundedJsonError,
    parse_bounded_json_line,
)


def _wire_identity() -> tuple[str, str]:
    corpus = json.loads((ROOT / "conformance/behavior/vectors.json").read_text())
    return str(corpus["ncp_version"]), str(corpus["contract_hash"])


NCP, HASH = _wire_identity()
HOST = os.environ.get("NCP_E2E_HOST", "127.0.0.1")
PORT_TEXT = os.environ.get("NCP_E2E_PORT", "28474")
SECURITY_PROFILE = "dev-loopback-insecure"
SECURITY_STATE_DIGEST = os.environ.get(
    "NCP_E2E_SECURITY_STATE_DIGEST",
    "1b8d5d1f0209b1c9c3131ab8787464f7d8ea17c4db7d9bc65084617fee44e21c",
)
COMMANDER_PRINCIPAL = "nest-smoke-commander"
COMMANDER_ENTITY = "nest-smoke-controller"

NETWORKS = [
    # (label, NEST model, population size, current_pA per 100 ms step)
    ("iaf_psc_alpha (current LIF)", "iaf_psc_alpha", 10, [500.0, 750.0, 1000.0]),
    ("iaf_psc_exp (exp-synapse LIF)", "iaf_psc_exp", 10, [500.0, 750.0, 1000.0]),
    ("izhikevich (regular spiking)", "izhikevich", 8, [10.0, 15.0, 20.0]),
    ("hh_psc_alpha (Hodgkin-Huxley)", "hh_psc_alpha", 6, [650.0, 800.0, 1000.0]),
    ("aeif_cond_alpha (adaptive EIF)", "aeif_cond_alpha", 6, [500.0, 750.0, 1000.0]),
]
REQUIRED_MODELS = (
    "iaf_psc_alpha",
    "iaf_psc_exp",
    "izhikevich",
    "hh_psc_alpha",
    "aeif_cond_alpha",
)
EXPECTED_NETWORK_COUNT = len(REQUIRED_MODELS)
PASS = 0
FAIL = 1
NOT_RUN = 2


class ReplyIngressError(RuntimeError):
    """Fatal framing/admission failure; the socket cannot be safely reused."""


def rpc(sock: socket.socket, reader: Any, message: dict[str, Any]) -> dict[str, Any]:
    payload = (json.dumps(message, separators=(",", ":")) + "\n").encode()
    if len(payload) - 1 > MAX_FRAME_BYTES:
        raise RuntimeError("native NCP request exceeds the JSON frame byte limit")
    try:
        sock.sendall(payload)
    except OSError as error:
        # sendall may have written a prefix. Reusing the stream could concatenate
        # the next request onto a truncated frame and destroy FIFO correlation.
        raise ReplyIngressError(f"native NCP request send failed: {error}") from error
    try:
        reply = parse_bounded_json_line(reader)
    except BoundedJsonError as error:
        raise ReplyIngressError(f"native NCP reply failed bounded ingress: {error}") from error
    except OSError as error:
        raise ReplyIngressError(f"native NCP reply read failed: {error}") from error
    if not isinstance(reply, dict):
        raise RuntimeError("NCP reply is not a JSON object")
    if reply.get("ncp_version") != NCP:
        raise RuntimeError(f"reply wire mismatch: {reply.get('ncp_version')!r} != {NCP!r}")
    return reply


def _identity() -> dict[str, Any]:
    return {
        "principal_id": COMMANDER_PRINCIPAL,
        "entity_id": COMMANDER_ENTITY,
        "role": "commander",
        "plane": "control",
    }


def _canonical_uuid4(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = uuid.UUID(value)
    except ValueError:
        return False
    return parsed.version == 4 and str(parsed) == value


def _bounded_id(value: Any, maximum: int = 128) -> bool:
    if not isinstance(value, str):
        return False
    try:
        encoded = value.encode("utf-8", errors="strict")
    except UnicodeEncodeError:
        return False
    return 0 < len(encoded) <= maximum and not any(
        character.isspace()
        or ord(character) < 0x20
        or 0x7F <= ord(character) <= 0x9F
        or character in "/*$#?\ufeff"
        for character in value
    )


def _lower_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _preprovisioned_authority(
    opened: dict[str, Any], session_epoch: str
) -> dict[str, Any]:
    """Read the exact active lease from a developer-only SessionOpened extension."""

    authority = opened.get("dev_smoke_authority")
    if not isinstance(authority, dict):
        raise RuntimeError(
            "native smoke service omitted its pre-provisioned dev_smoke_authority lease"
        )
    expected_fields = {
        "session_epoch",
        "term",
        "lease_id",
        "issuer_principal_id",
        "holder_principal_id",
        "holder_entity_id",
        "issued_at_utc_ms",
        "expires_at_utc_ms",
    }
    if set(authority) != expected_fields:
        raise RuntimeError("dev_smoke_authority does not have the exact lease shape")
    if not _canonical_uuid4(session_epoch):
        raise RuntimeError("SessionOpened generation is not a canonical lowercase UUIDv4")
    if authority.get("session_epoch") != session_epoch:
        raise RuntimeError("dev_smoke_authority belongs to a different session generation")
    if authority.get("holder_principal_id") != COMMANDER_PRINCIPAL or authority.get(
        "holder_entity_id"
    ) != COMMANDER_ENTITY:
        raise RuntimeError("dev_smoke_authority belongs to a different holder")
    if not _bounded_id(authority.get("issuer_principal_id")):
        raise RuntimeError("dev_smoke_authority issuer_principal_id is invalid")
    term = authority.get("term")
    if not isinstance(term, int) or isinstance(term, bool) or not 1 <= term <= SAFE_INTEGER_MAX:
        raise RuntimeError("dev_smoke_authority term is not a positive JSON-safe integer")
    lease_id = authority.get("lease_id")
    if not _canonical_uuid4(lease_id):
        raise RuntimeError("dev_smoke_authority lease_id is not a canonical UUIDv4")
    issued = authority.get("issued_at_utc_ms")
    expires = authority.get("expires_at_utc_ms")
    if (
        not isinstance(issued, int)
        or isinstance(issued, bool)
        or not isinstance(expires, int)
        or isinstance(expires, bool)
        or issued <= 0
        or issued > SAFE_INTEGER_MAX
        or expires > SAFE_INTEGER_MAX
        or expires <= issued
        or expires - issued > 60_000
        or expires <= int(time.time() * 1000)
    ):
        raise RuntimeError("dev_smoke_authority interval is invalid or expired")
    return authority


def _seal_mutation(
    request: dict[str, Any], session_epoch: str, state_version: int, authority: dict[str, Any]
) -> dict[str, Any]:
    if not isinstance(state_version, int) or isinstance(state_version, bool) or not 0 <= state_version <= SAFE_INTEGER_MAX:
        raise RuntimeError("authoritative state_version is not a non-negative JSON-safe integer")
    now_utc_ms = int(time.time() * 1000)
    deadline = min(now_utc_ms + 30_000, int(authority["expires_at_utc_ms"]))
    if deadline <= now_utc_ms:
        raise RuntimeError("authority lease expired before the mutation could be sealed")
    request["operation"] = {
        "operation_id": str(uuid.uuid4()),
        "request_digest": "",
        "session_epoch": session_epoch,
        "expected_state_version": state_version,
        "deadline_utc_ms": deadline,
        "retry": False,
    }
    request["authority"] = authority
    request["operation"]["request_digest"] = request_digest(request)
    return request


def _receipt(reply: dict[str, Any], request: dict[str, Any], previous_state: int) -> int:
    receipt = reply.get("receipt")
    if not isinstance(receipt, dict):
        raise RuntimeError("successful mutation reply omitted its responder receipt")
    operation = request["operation"]
    if receipt.get("operation_id") != operation["operation_id"]:
        raise RuntimeError("responder receipt operation_id does not correlate")
    if receipt.get("request_digest") != operation["request_digest"]:
        raise RuntimeError("responder receipt request_digest does not correlate")
    if receipt.get("outcome") != "succeeded":
        raise RuntimeError(f"mutation did not succeed: {receipt.get('outcome')!r}")
    result_digest = receipt.get("result_digest")
    if not _lower_sha256(result_digest):
        raise RuntimeError("responder receipt carries no lowercase SHA-256 result digest")
    next_state = receipt.get("state_version")
    if (
        not isinstance(next_state, int)
        or isinstance(next_state, bool)
        or not previous_state < next_state <= SAFE_INTEGER_MAX
    ):
        raise RuntimeError("successful receipt did not advance authoritative state_version")
    committed = receipt.get("committed_at_utc_ms")
    if (
        not isinstance(committed, int)
        or isinstance(committed, bool)
        or not 1 <= committed <= SAFE_INTEGER_MAX
    ):
        raise RuntimeError("responder receipt carries no positive JSON-safe commit timestamp")
    if not _bounded_id(receipt.get("responder_principal_id")) or not _bounded_id(
        receipt.get("responder_entity_id")
    ):
        raise RuntimeError("responder receipt carries invalid responder identity fields")
    return next_state


def _raise_error(reply: dict[str, Any], request_kind: str, session_id: str) -> None:
    if reply.get("kind") != "error":
        return
    if reply.get("request_kind") not in (None, request_kind):
        raise RuntimeError("error reply is correlated to a different request kind")
    if reply.get("session_id") not in (None, session_id):
        raise RuntimeError("error reply is correlated to a different session")
    raise RuntimeError(f"native service rejected {request_kind}: {reply.get('error')!r}")


def run_one(
    sock: socket.socket,
    reader: Any,
    label: str,
    model: str,
    population_size: int,
    currents: list[float],
) -> dict[str, Any]:
    session_id = f"nest-{model}"
    open_request = {
        "ncp_version": NCP,
        "kind": "open_session",
        "session_id": session_id,
        "network": {
            "kind": "builtin",
            "ref": model,
            "population_sizes": {"pop": population_size},
        },
        "record": {
            "targets": [{"port": "spk", "target": "pop", "observable": "spikes"}]
        },
        "stimulus": {
            "targets": [{"port": "drive", "target": "pop", "kind": "current_pA"}]
        },
        "sim": {"dt_ms": 0.1, "chunk_ms": 10.0, "mode": "stream"},
        "bindings": [],
        "contract_hash": HASH,
        "identity": _identity(),
        "security_profile": SECURITY_PROFILE,
        "security_state_digest": SECURITY_STATE_DIGEST,
        "gateway_permitted": False,
    }
    opened = rpc(sock, reader, open_request)
    _raise_error(opened, "open_session", session_id)
    provenance = opened.get("provenance")
    if opened.get("kind") != "session_opened" or opened.get("ok") is not True:
        raise RuntimeError(f"invalid session_opened reply: {opened!r}")
    if opened.get("session_id") != session_id:
        raise RuntimeError("session_opened belongs to a different logical session")
    if opened.get("gateway_permitted") is not False or opened.get("gateway") is not None:
        raise RuntimeError("native smoke service returned a gateway-attributed session")
    if not isinstance(provenance, dict) or not (
        provenance.get("calibrated_posterior") is False
        and provenance.get("is_simulation_output") is True
        and provenance.get("advisory_only") is True
    ):
        raise RuntimeError("session_opened violated the scientific boundary")
    if opened.get("security_profile") != SECURITY_PROFILE or opened.get(
        "security_state_digest"
    ) != SECURITY_STATE_DIGEST:
        raise RuntimeError("session_opened changed the precommitted security negotiation")
    generation = (opened.get("session") or {}).get("generation")
    state_version = opened.get("state_version")
    if not _canonical_uuid4(generation):
        raise RuntimeError("session_opened carried no canonical server-issued generation")
    if (
        not isinstance(state_version, int)
        or isinstance(state_version, bool)
        or not 0 <= state_version <= SAFE_INTEGER_MAX
    ):
        raise RuntimeError("session_opened carried no authoritative initial state_version")

    authority = _preprovisioned_authority(opened, generation)
    total_spikes = 0
    per_step: list[tuple[float, int, Any]] = []
    for index, current in enumerate(currents):
        step = _seal_mutation(
            {
                "ncp_version": NCP,
                "kind": "step_request",
                "session_id": session_id,
                "advance_ms": 100.0,
                "session": {"generation": generation},
                "stimulus": {
                    "ncp_version": NCP,
                    "kind": "stimulus_frame",
                    "session_id": session_id,
                    "t": float(index),
                    "session": {"generation": generation},
                    "values": {"drive": {"data": [current], "unit": "pA"}},
                },
            },
            generation,
            state_version,
            authority,
        )
        observation = rpc(sock, reader, step)
        _raise_error(observation, "step_request", session_id)
        if observation.get("kind") != "observation_frame":
            raise RuntimeError(f"step returned {observation.get('kind')!r}, not observation_frame")
        if observation.get("calibrated_posterior") is not False or observation.get(
            "is_simulation_output"
        ) is not True:
            raise RuntimeError("observation violated the scientific boundary")
        if (observation.get("session") or {}).get("generation") != generation:
            raise RuntimeError("observation belongs to a different session generation")
        if observation.get("session_id") != session_id:
            raise RuntimeError("observation belongs to a different logical session")
        if observation.get("source") is not None:
            raise RuntimeError("RPC observation incorrectly carried an observation-plane source")
        state_version = _receipt(observation, step, state_version)
        record = (observation.get("records") or {}).get("spk", {})
        spikes = len(record.get("times", []) or [])
        total_spikes += spikes
        per_step.append((current, spikes, observation.get("sim_time_ms")))

    close = _seal_mutation(
        {
            "ncp_version": NCP,
            "kind": "close_session",
            "session_id": session_id,
            "session": {"generation": generation},
        },
        generation,
        state_version,
        authority,
    )
    closed = rpc(sock, reader, close)
    _raise_error(closed, "close_session", session_id)
    if closed.get("kind") != "session_closed" or closed.get("ok") is not True:
        raise RuntimeError(f"invalid session_closed reply: {closed!r}")
    if (closed.get("session") or {}).get("generation") != generation:
        raise RuntimeError("session_closed belongs to a different generation")
    if closed.get("session_id") != session_id:
        raise RuntimeError("session_closed belongs to a different logical session")
    _receipt(closed, close, state_version)
    return {
        "label": label,
        "model": model,
        "ok": True,
        "backend": opened.get("backend"),
        "pop": population_size,
        "total_spikes": total_spikes,
        "per_step": per_step,
        "closed_ok": True,
    }


def _configured_endpoint() -> tuple[str, int]:
    if not _lower_sha256(SECURITY_STATE_DIGEST):
        raise ValueError(
            "NCP_E2E_SECURITY_STATE_DIGEST must be 64 lowercase hexadecimal characters"
        )
    try:
        address = ipaddress.ip_address(HOST)
    except ValueError as error:
        raise ValueError("NCP_E2E_HOST must be a numeric loopback IP address") from error
    if not address.is_loopback:
        raise ValueError("NCP_E2E_HOST must be loopback for dev-loopback-insecure")
    if isinstance(address, ipaddress.IPv6Address) and address.scope_id is not None:
        raise ValueError("NCP_E2E_HOST must not carry an IPv6 scope identifier")
    try:
        port = int(PORT_TEXT)
    except ValueError as error:
        raise ValueError("NCP_E2E_PORT must be an integer") from error
    if not 1 <= port <= 65_535:
        raise ValueError("NCP_E2E_PORT must be in 1..=65535")
    return str(address), port


def _result_status(results: list[dict[str, Any]]) -> tuple[str, int]:
    if any(result.get("ok") is not True for result in results):
        return "FAIL", FAIL
    if tuple(result.get("model") for result in results) != REQUIRED_MODELS:
        return "NOT RUN", NOT_RUN
    return "PASS", PASS


def main() -> int:
    started = time.time()
    try:
        endpoint = _configured_endpoint()
    except ValueError as error:
        print(f"LOCAL SMOKE RESULT: FAIL\nconfiguration error: {error}")
        return FAIL
    try:
        sock = socket.create_connection(endpoint, timeout=120)
    except OSError as error:
        print(
            "LOCAL SMOKE RESULT: NOT RUN\n"
            f"native-1.0 SessionService unavailable at {endpoint[0]}:{endpoint[1]}: {error}"
        )
        return NOT_RUN
    with sock, sock.makefile("rb") as reader:
        sock.settimeout(120)
        results = []
        for label, model, population_size, currents in NETWORKS:
            try:
                results.append(
                    run_one(sock, reader, label, model, population_size, currents)
                )
            except Exception as error:  # noqa: BLE001 - runner reports per-model failures
                results.append(
                    {"label": label, "model": model, "ok": False, "detail": str(error)}
                )
                if isinstance(error, ReplyIngressError):
                    # An oversized/unterminated line may leave bytes buffered.
                    # Close the connection instead of treating them as the next
                    # model's reply and manufacturing false evidence.
                    break

    print(f"\n=== five NEST model families via native NCP {NCP}, {time.time()-started:.1f}s ===")
    print(f"{'network':32} {'pop':>4} {'spikes':>7}  steps(current_pA->spikes)")
    print("-" * 86)
    passed = 0
    for result in results:
        if result.get("ok"):
            passed += 1
            steps = " ".join(f"{int(current)}->{count}" for current, count, _ in result["per_step"])
            print(
                f"{result['label']:32} {result['pop']:>4} "
                f"{result['total_spikes']:>7}  {steps}"
            )
        else:
            print(f"{result['label']:32}  FAILED: {str(result.get('detail'))[:120]}")
    print("-" * 86)
    status, exit_code = _result_status(results)
    print(
        f"backend={results[0].get('backend') if results else '?'}  "
        f"ok={passed}/{EXPECTED_NETWORK_COUNT}  executed={len(results)}/{EXPECTED_NETWORK_COUNT}"
    )
    if status == "NOT RUN":
        print("one or more required model-family scenarios were not executed")
    print(f"LOCAL SMOKE RESULT: {status}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
