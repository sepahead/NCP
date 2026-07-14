#!/usr/bin/env python3
"""Drive five NEST model families through a native NCP 1.0 lifecycle service.

This is a developer smoke runner, not release interoperability or scientific
validation.  It requires a separately started, native-wire-1.0 service with the
dev-loopback security profile, authority acquisition, idempotent operations, and
authenticated responder receipts.  Engram's current wire-0.8 bridge is not such a
service and must not be used as an implicit compatibility fallback.
"""

from __future__ import annotations

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
from e2e.bounded_json import BoundedJsonError, parse_bounded_json_line  # noqa: E402


def _wire_identity() -> tuple[str, str]:
    corpus = json.loads((ROOT / "conformance/behavior/vectors.json").read_text())
    return str(corpus["ncp_version"]), str(corpus["contract_hash"])


NCP, HASH = _wire_identity()
HOST = os.environ.get("NCP_E2E_HOST", "127.0.0.1")
PORT = int(os.environ.get("NCP_E2E_PORT", "28474"))
SECURITY_PROFILE = "dev-loopback-insecure"
SECURITY_STATE_DIGEST = os.environ.get(
    "NCP_E2E_SECURITY_STATE_DIGEST",
    "8b65c88deecefc922a191ea646b1a2b9602f733c61d7649e778d0d7087bc15ab",
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


class ReplyIngressError(RuntimeError):
    """Fatal framing/admission failure; the socket cannot be safely reused."""


def rpc(sock: socket.socket, reader: Any, message: dict[str, Any]) -> dict[str, Any]:
    sock.sendall((json.dumps(message, separators=(",", ":")) + "\n").encode())
    try:
        reply = parse_bounded_json_line(reader)
    except BoundedJsonError as error:
        raise ReplyIngressError(f"native NCP reply failed bounded ingress: {error}") from error
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


def _authority(session_epoch: str) -> dict[str, Any]:
    issued = int(time.time() * 1000)
    return {
        "session_epoch": session_epoch,
        "term": 1,
        "lease_id": str(uuid.uuid4()),
        "issuer_principal_id": COMMANDER_PRINCIPAL,
        "holder_principal_id": COMMANDER_PRINCIPAL,
        "holder_entity_id": COMMANDER_ENTITY,
        "issued_at_utc_ms": issued,
        "expires_at_utc_ms": issued + 60_000,
    }


def _seal_mutation(
    request: dict[str, Any], session_epoch: str, state_version: int, authority: dict[str, Any]
) -> dict[str, Any]:
    deadline = min(int(time.time() * 1000) + 30_000, int(authority["expires_at_utc_ms"]))
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
    if not isinstance(result_digest, str) or len(result_digest) != 64:
        raise RuntimeError("responder receipt carries no lowercase SHA-256 result digest")
    next_state = receipt.get("state_version")
    if not isinstance(next_state, int) or isinstance(next_state, bool) or next_state <= previous_state:
        raise RuntimeError("successful receipt did not advance authoritative state_version")
    if not receipt.get("responder_principal_id") or not receipt.get("responder_entity_id"):
        raise RuntimeError("responder receipt is not bound to an authenticated responder")
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
    if not isinstance(generation, str) or not generation:
        raise RuntimeError("session_opened carried no server-issued generation")
    if not isinstance(state_version, int) or isinstance(state_version, bool) or state_version < 0:
        raise RuntimeError("session_opened carried no authoritative initial state_version")

    authority = _authority(generation)
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


def main() -> int:
    started = time.time()
    with socket.create_connection((HOST, PORT), timeout=120) as sock:
        sock.settimeout(120)
        reader = sock.makefile("rb")
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
    print(f"backend={results[0].get('backend') if results else '?'}  ok={passed}/{len(results)}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
