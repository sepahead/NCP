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
import math
import os
import socket
import sys
import time
import uuid
from dataclasses import dataclass
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
ADVANCE_MS = 100.0
CONTROL_STEPS = 3


@dataclass(frozen=True, slots=True)
class ClosedLoopCase:
    """One bounded developer-smoke controller and reference NEST plant."""

    label: str
    model: str
    population_size: int
    initial_current_p_a: float
    target_spikes: int
    gain_p_a_per_spike: float
    minimum_current_p_a: float
    maximum_current_p_a: float


NETWORKS = (
    ClosedLoopCase(
        "iaf_psc_alpha (current LIF)", "iaf_psc_alpha", 10, 500.0, 20, 12.5, 0.0, 1500.0
    ),
    ClosedLoopCase(
        "iaf_psc_exp (exp-synapse LIF)", "iaf_psc_exp", 10, 500.0, 20, 12.5, 0.0, 1500.0
    ),
    ClosedLoopCase(
        "izhikevich (regular spiking)", "izhikevich", 8, 10.0, 12, 0.5, 0.0, 30.0
    ),
    ClosedLoopCase(
        "hh_psc_alpha (Hodgkin-Huxley)", "hh_psc_alpha", 6, 650.0, 12, 20.0, 0.0, 1500.0
    ),
    ClosedLoopCase(
        "aeif_cond_alpha (adaptive EIF)",
        "aeif_cond_alpha",
        6,
        500.0,
        12,
        20.0,
        0.0,
        1500.0,
    ),
)
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
    payload = (
        json.dumps(message, allow_nan=False, ensure_ascii=False, separators=(",", ":"))
        + "\n"
    ).encode()
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
        raise ReplyIngressError(
            f"native NCP reply failed bounded ingress: {error}"
        ) from error
    except OSError as error:
        raise ReplyIngressError(f"native NCP reply read failed: {error}") from error
    if not isinstance(reply, dict):
        raise RuntimeError("NCP reply is not a JSON object")
    if reply.get("ncp_version") != NCP:
        raise RuntimeError(
            f"reply wire mismatch: {reply.get('ncp_version')!r} != {NCP!r}"
        )
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
        raise RuntimeError(
            "SessionOpened generation is not a canonical lowercase UUIDv4"
        )
    if authority.get("session_epoch") != session_epoch:
        raise RuntimeError(
            "dev_smoke_authority belongs to a different session generation"
        )
    if (
        authority.get("holder_principal_id") != COMMANDER_PRINCIPAL
        or authority.get("holder_entity_id") != COMMANDER_ENTITY
    ):
        raise RuntimeError("dev_smoke_authority belongs to a different holder")
    if not _bounded_id(authority.get("issuer_principal_id")):
        raise RuntimeError("dev_smoke_authority issuer_principal_id is invalid")
    term = authority.get("term")
    if (
        not isinstance(term, int)
        or isinstance(term, bool)
        or not 1 <= term <= SAFE_INTEGER_MAX
    ):
        raise RuntimeError(
            "dev_smoke_authority term is not a positive JSON-safe integer"
        )
    lease_id = authority.get("lease_id")
    if not _canonical_uuid4(lease_id):
        raise RuntimeError("dev_smoke_authority lease_id is not a canonical UUIDv4")
    issued = authority.get("issued_at_utc_ms")
    expires = authority.get("expires_at_utc_ms")
    now_utc_ms = int(time.time() * 1000)
    if (
        not isinstance(issued, int)
        or isinstance(issued, bool)
        or not isinstance(expires, int)
        or isinstance(expires, bool)
        or issued <= 0
        or issued > SAFE_INTEGER_MAX
        or issued > now_utc_ms
        or expires > SAFE_INTEGER_MAX
        or expires <= issued
        or expires - issued > 60_000
        or expires <= now_utc_ms
    ):
        raise RuntimeError("dev_smoke_authority interval is invalid or expired")
    return authority


def _responder_identity(opened: dict[str, Any]) -> tuple[str, str]:
    """Return the exact body payload coordinate carried by SessionOpened.

    The loopback smoke compares this coordinate with later receipt fields. It
    does not authenticate the responder; that requires a transport-authenticated
    live gate outside this runner.
    """

    identity = opened.get("identity")
    if not isinstance(identity, dict) or set(identity) != {
        "principal_id",
        "entity_id",
        "role",
        "plane",
    }:
        raise RuntimeError("session_opened carries no exact responder identity")
    if identity.get("role") != "body" or identity.get("plane") != "control":
        raise RuntimeError("session_opened responder is not the control-plane body")
    principal = identity.get("principal_id")
    entity = identity.get("entity_id")
    if not _bounded_id(principal) or not _bounded_id(entity):
        raise RuntimeError("session_opened responder identity fields are invalid")
    return str(principal), str(entity)


def _resolved_execution(opened: dict[str, Any], case: ClosedLoopCase) -> str:
    """Validate the exact NEST execution identity returned by SessionOpened."""

    backend = opened.get("backend")
    resolved = opened.get("resolved")
    provenance = opened.get("provenance")
    if backend != "nest":
        raise RuntimeError("session_opened did not select the required NEST backend")
    if not isinstance(resolved, dict) or resolved != {"pop": case.population_size}:
        raise RuntimeError(
            "session_opened resolved population does not match the request"
        )
    required_provenance = {
        "network_ref",
        "backend",
        "calibrated_posterior",
        "is_simulation_output",
        "advisory_only",
    }
    allowed_provenance = required_provenance | {"seed", "note"}
    if (
        not isinstance(provenance, dict)
        or not required_provenance <= set(provenance) <= allowed_provenance
        or not (
            provenance.get("network_ref") == case.model
            and provenance.get("backend") == backend
            and provenance.get("calibrated_posterior") is False
            and provenance.get("is_simulation_output") is True
            and provenance.get("advisory_only") is True
        )
    ):
        raise RuntimeError(
            "session_opened provenance contradicts the requested execution"
        )
    seed = provenance.get("seed")
    if seed is not None and (
        not isinstance(seed, int)
        or isinstance(seed, bool)
        or not -SAFE_INTEGER_MAX <= seed <= SAFE_INTEGER_MAX
    ):
        raise RuntimeError("session_opened provenance seed is not a JSON-safe integer")
    note = provenance.get("note")
    if note is not None and not isinstance(note, str):
        raise RuntimeError("session_opened provenance note is not a string or null")
    return str(backend)


def _seal_mutation(
    request: dict[str, Any],
    session_epoch: str,
    state_version: int,
    authority: dict[str, Any],
) -> dict[str, Any]:
    if (
        not isinstance(state_version, int)
        or isinstance(state_version, bool)
        or not 0 <= state_version <= SAFE_INTEGER_MAX
    ):
        raise RuntimeError(
            "authoritative state_version is not a non-negative JSON-safe integer"
        )
    now_utc_ms = int(time.time() * 1000)
    deadline = min(now_utc_ms + 30_000, int(authority["expires_at_utc_ms"]))
    if deadline <= now_utc_ms:
        raise RuntimeError(
            "authority lease expired before the mutation could be sealed"
        )
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


def _receipt(
    reply: dict[str, Any],
    request: dict[str, Any],
    previous_state: int,
    responder: tuple[str, str],
) -> int:
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
    # The current candidate defines no approved nonrecursive projection from the
    # wire reply to result_digest. This check is syntax only. Operation/request
    # correlation, non-regressing state adoption, FIFO response ownership, and
    # the fresh observation position still fail closed. This runner does not
    # claim independent certification of the result body from the digest.
    result_digest = receipt.get("result_digest")
    if not _lower_sha256(result_digest):
        raise RuntimeError(
            "responder receipt carries no lowercase SHA-256 result digest"
        )
    next_state = receipt.get("state_version")
    if (
        not isinstance(next_state, int)
        or isinstance(next_state, bool)
        or not previous_state <= next_state <= SAFE_INTEGER_MAX
    ):
        raise RuntimeError(
            "successful receipt state_version precedes the authoritative request state"
        )
    committed = receipt.get("committed_at_utc_ms")
    if (
        not isinstance(committed, int)
        or isinstance(committed, bool)
        or not 1 <= committed <= SAFE_INTEGER_MAX
    ):
        raise RuntimeError(
            "responder receipt carries no positive JSON-safe commit timestamp"
        )
    receipt_responder = (
        receipt.get("responder_principal_id"),
        receipt.get("responder_entity_id"),
    )
    if not all(_bounded_id(value) for value in receipt_responder):
        raise RuntimeError(
            "responder receipt carries invalid responder identity fields"
        )
    if receipt_responder != responder:
        raise RuntimeError(
            "responder receipt identity differs from the body coordinate carried by open"
        )
    return next_state


def _raise_error(reply: dict[str, Any], request_kind: str, session_id: str) -> None:
    if reply.get("kind") != "error":
        return
    if reply.get("request_kind") not in (None, request_kind):
        raise RuntimeError("error reply is correlated to a different request kind")
    if reply.get("session_id") not in (None, session_id):
        raise RuntimeError("error reply is correlated to a different session")
    raise RuntimeError(
        f"native service rejected {request_kind}: {reply.get('error')!r}"
    )


def _validate_case(case: ClosedLoopCase) -> None:
    if not _bounded_id(case.model) or not case.label:
        raise ValueError("closed-loop case has an invalid model or empty label")
    if (
        not isinstance(case.population_size, int)
        or isinstance(case.population_size, bool)
        or case.population_size <= 0
    ):
        raise ValueError(f"{case.model} population_size must be a positive integer")
    if (
        not isinstance(case.target_spikes, int)
        or isinstance(case.target_spikes, bool)
        or case.target_spikes < 0
    ):
        raise ValueError(f"{case.model} target_spikes must be a non-negative integer")
    parameters = (
        case.initial_current_p_a,
        case.gain_p_a_per_spike,
        case.minimum_current_p_a,
        case.maximum_current_p_a,
    )
    if not all(
        isinstance(value, (int, float)) and not isinstance(value, bool)
        for value in parameters
    ):
        raise ValueError(f"{case.model} controller parameters must be numeric")
    if not all(math.isfinite(float(value)) for value in parameters):
        raise ValueError(f"{case.model} controller parameters must be finite")
    if case.gain_p_a_per_spike <= 0.0:
        raise ValueError(f"{case.model} controller gain must be positive")
    if not case.minimum_current_p_a < case.maximum_current_p_a:
        raise ValueError(f"{case.model} current interval must be non-empty")
    if (
        not case.minimum_current_p_a
        <= case.initial_current_p_a
        <= case.maximum_current_p_a
    ):
        raise ValueError(
            f"{case.model} initial current must be inside the current interval"
        )


def _next_control(
    case: ClosedLoopCase, current_p_a: float, spikes: int
) -> tuple[int, float]:
    """Return error and the saturated next command for the proportional loop."""

    if not math.isfinite(current_p_a):
        raise RuntimeError("closed-loop current is not finite")
    if not isinstance(spikes, int) or isinstance(spikes, bool) or spikes < 0:
        raise RuntimeError("closed-loop spike count is not a non-negative integer")
    error = case.target_spikes - spikes
    unconstrained = current_p_a + case.gain_p_a_per_spike * error
    if not math.isfinite(unconstrained):
        raise RuntimeError("closed-loop proportional update is not finite")
    return error, min(
        case.maximum_current_p_a,
        max(case.minimum_current_p_a, unconstrained),
    )


def _spike_observation(
    observation: dict[str, Any],
    previous_sim_time_ms: float,
    expected_sim_time_ms: float,
) -> tuple[int, float]:
    """Validate the negotiated spike series and return its causal sample."""

    if (
        not math.isfinite(previous_sim_time_ms)
        or not math.isfinite(expected_sim_time_ms)
        or previous_sim_time_ms < 0.0
        or expected_sim_time_ms <= previous_sim_time_ms
    ):
        raise RuntimeError("closed-loop simulation interval is invalid")
    sim_time = observation.get("sim_time_ms")
    if (
        not isinstance(sim_time, (int, float))
        or isinstance(sim_time, bool)
        or not math.isfinite(float(sim_time))
        or not math.isclose(
            float(sim_time), expected_sim_time_ms, rel_tol=0.0, abs_tol=1e-9
        )
    ):
        raise RuntimeError(
            "observation sim_time_ms does not equal the commanded cumulative advance"
        )
    records = observation.get("records")
    if not isinstance(records, dict) or set(records) != {"spk"}:
        raise RuntimeError(
            "observation does not carry exactly the negotiated spk record series"
        )
    record = records["spk"]
    if not isinstance(record, dict):
        raise RuntimeError("observation spk record is not an object")
    allowed_record_fields = {
        "port",
        "target",
        "observable",
        "times",
        "values",
        "senders",
        "unit",
        "recordable",
    }
    if not set(record) <= allowed_record_fields:
        raise RuntimeError("observation spk record carries an unknown member")
    if (
        record.get("port") != "spk"
        or record.get("target") != "pop"
        or record.get("observable") != "spikes"
    ):
        raise RuntimeError(
            "observation spk record changed the negotiated port, target, or observable"
        )
    times = record.get("times")
    if not isinstance(times, list) or any(
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(float(value))
        for value in times
    ):
        raise RuntimeError("observation spk times are not a finite numeric array")
    if any(
        not previous_sim_time_ms < float(timestamp) <= expected_sim_time_ms
        for timestamp in times
    ):
        raise RuntimeError(
            "observation spk time is outside the newly advanced interval"
        )
    if any(float(later) < float(earlier) for earlier, later in zip(times, times[1:])):
        raise RuntimeError("observation spk times are not non-decreasing")
    if "values" in record and record["values"] != []:
        raise RuntimeError(
            "observation spike series unexpectedly carries scalar values"
        )
    if record.get("unit") is not None or record.get("recordable") is not None:
        raise RuntimeError(
            "observation spike series changed its negotiated unit or recordable"
        )
    senders = record.get("senders")
    if not isinstance(senders, list) or len(senders) != len(times):
        raise RuntimeError("observation spk sender and time arrays disagree")
    if any(
        not isinstance(sender, int)
        or isinstance(sender, bool)
        or not 1 <= sender <= SAFE_INTEGER_MAX
        for sender in senders
    ):
        raise RuntimeError(
            "observation spk sender is not a positive JSON-safe NEST node ID"
        )
    return len(times), float(sim_time)


def _observation_stream(
    observation: dict[str, Any], prior: tuple[str, int] | None
) -> tuple[str, int]:
    """Admit one fresh position from the session's observation stream."""

    stream = observation.get("stream")
    if not isinstance(stream, dict) or set(stream) != {"epoch", "seq"}:
        raise RuntimeError("observation carries no exact stream position")
    epoch = stream.get("epoch")
    seq = stream.get("seq")
    if not _canonical_uuid4(epoch):
        raise RuntimeError("observation stream epoch is not a canonical UUIDv4")
    if (
        not isinstance(seq, int)
        or isinstance(seq, bool)
        or not 1 <= seq <= SAFE_INTEGER_MAX
    ):
        raise RuntimeError(
            "observation stream sequence is not a positive JSON-safe integer"
        )
    # A publisher starts an epoch at 1, but this consumer may first observe any
    # later positive position. Requiring a complete prefix would reject a valid
    # join after loss or after a publisher began before this RPC exchange.
    if prior is not None and (epoch != prior[0] or seq <= prior[1]):
        raise RuntimeError("observation stream changed epoch, replayed, or regressed")
    return epoch, seq


def run_one(
    sock: socket.socket,
    reader: Any,
    case: ClosedLoopCase,
) -> dict[str, Any]:
    _validate_case(case)
    label = case.label
    model = case.model
    population_size = case.population_size
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
    if opened.get("kind") != "session_opened" or opened.get("ok") is not True:
        raise RuntimeError(f"invalid session_opened reply: {opened!r}")
    if opened.get("session_id") != session_id:
        raise RuntimeError("session_opened belongs to a different logical session")
    if (
        opened.get("gateway_permitted") is not False
        or opened.get("gateway") is not None
    ):
        raise RuntimeError("native smoke service returned a gateway-attributed session")
    if (
        opened.get("security_profile") != SECURITY_PROFILE
        or opened.get("security_state_digest") != SECURITY_STATE_DIGEST
    ):
        raise RuntimeError(
            "session_opened changed the precommitted security negotiation"
        )
    backend = _resolved_execution(opened, case)
    generation = (opened.get("session") or {}).get("generation")
    state_version = opened.get("state_version")
    if not _canonical_uuid4(generation):
        raise RuntimeError(
            "session_opened carried no canonical server-issued generation"
        )
    if (
        not isinstance(state_version, int)
        or isinstance(state_version, bool)
        or not 0 <= state_version <= SAFE_INTEGER_MAX
    ):
        raise RuntimeError(
            "session_opened carried no authoritative initial state_version"
        )

    authority = _preprovisioned_authority(opened, generation)
    responder = _responder_identity(opened)
    total_spikes = 0
    per_step: list[dict[str, float | int | None]] = []
    current = case.initial_current_p_a
    observation_position: tuple[str, int] | None = None
    for index in range(CONTROL_STEPS):
        step = _seal_mutation(
            {
                "ncp_version": NCP,
                "kind": "step_request",
                "session_id": session_id,
                "advance_ms": ADVANCE_MS,
                "session": {"generation": generation},
                "stimulus": {
                    "ncp_version": NCP,
                    "kind": "stimulus_frame",
                    "session_id": session_id,
                    "t": time.monotonic(),
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
            raise RuntimeError(
                f"step returned {observation.get('kind')!r}, not observation_frame"
            )
        if (
            observation.get("calibrated_posterior") is not False
            or observation.get("is_simulation_output") is not True
        ):
            raise RuntimeError("observation violated the scientific boundary")
        if (observation.get("session") or {}).get("generation") != generation:
            raise RuntimeError("observation belongs to a different session generation")
        if observation.get("session_id") != session_id:
            raise RuntimeError("observation belongs to a different logical session")
        if observation.get("source") is not None:
            raise RuntimeError(
                "RPC observation incorrectly carried an observation-plane source"
            )
        observation_position = _observation_stream(observation, observation_position)
        state_version = _receipt(observation, step, state_version, responder)
        spikes, sim_time_ms = _spike_observation(
            observation,
            index * ADVANCE_MS,
            (index + 1) * ADVANCE_MS,
        )
        total_spikes += spikes
        error, next_current = _next_control(case, current, spikes)
        per_step.append(
            {
                "index": index,
                "command_p_a": current,
                "spikes": spikes,
                "error": error,
                "next_command_p_a": next_current if index + 1 < CONTROL_STEPS else None,
                "sim_time_ms": sim_time_ms,
            }
        )
        current = next_current

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
    _receipt(closed, close, state_version, responder)
    return {
        "label": label,
        "model": model,
        "ok": True,
        "backend": backend,
        "pop": population_size,
        "target_spikes": case.target_spikes,
        "total_spikes": total_spikes,
        "per_step": per_step,
        "closed_ok": True,
    }


def _configured_endpoint() -> tuple[str, int]:
    if tuple(case.model for case in NETWORKS) != REQUIRED_MODELS:
        raise ValueError(
            "closed-loop cases do not match the five required model families"
        )
    if (
        not isinstance(CONTROL_STEPS, int)
        or isinstance(CONTROL_STEPS, bool)
        or not 2 <= CONTROL_STEPS <= SAFE_INTEGER_MAX
    ):
        raise ValueError("closed-loop smoke requires at least two control intervals")
    if (
        not isinstance(ADVANCE_MS, (int, float))
        or isinstance(ADVANCE_MS, bool)
        or not math.isfinite(float(ADVANCE_MS))
        or ADVANCE_MS <= 0.0
    ):
        raise ValueError("closed-loop ADVANCE_MS must be finite and positive")
    for case in NETWORKS:
        _validate_case(case)
    if not _lower_sha256(SECURITY_STATE_DIGEST):
        raise ValueError(
            "NCP_E2E_SECURITY_STATE_DIGEST must be 64 lowercase hexadecimal characters"
        )
    try:
        address = ipaddress.ip_address(HOST)
    except ValueError as error:
        raise ValueError(
            "NCP_E2E_HOST must be a numeric loopback IP address"
        ) from error
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
            "native-1.0 SessionService unavailable at "
            f"{endpoint[0]}:{endpoint[1]}: {error}"
        )
        return NOT_RUN
    with sock, sock.makefile("rb") as reader:
        sock.settimeout(120)
        results = []
        for case in NETWORKS:
            try:
                results.append(run_one(sock, reader, case))
            except Exception as error:  # noqa: BLE001 - runner reports per-model failures
                results.append(
                    {
                        "label": case.label,
                        "model": case.model,
                        "ok": False,
                        "detail": str(error),
                    }
                )
                # Any failure after OpenSession may leave a live server generation
                # that this client cannot safely close without the exact authority
                # and state version. Continuing would turn that residual state into
                # secondary failures and obscure the first causal defect. A framing
                # failure is even stronger because unread bytes can also destroy
                # FIFO reply correlation. Close this connection after the first
                # attempted failure and require explicit server-side reconciliation
                # before a new run.
                break

    print(
        f"\n=== five closed-loop NEST model families via native NCP {NCP}, "
        f"{time.time() - started:.1f}s ==="
    )
    print(
        f"{'network':32} {'pop':>4} {'target/step':>11} "
        f"{'total y':>7}  intervals(u_pA->y)"
    )
    print("-" * 86)
    passed = 0
    for result in results:
        if result.get("ok"):
            passed += 1
            steps = " ".join(
                f"{step['command_p_a']:g}->{step['spikes']}"
                for step in result["per_step"]
            )
            print(
                f"{result['label']:32} {result['pop']:>4} "
                f"{result['target_spikes']:>6} {result['total_spikes']:>7}  {steps}"
            )
        else:
            print(f"{result['label']:32}  FAILED: {str(result.get('detail'))[:120]}")
    print("-" * 86)
    status, exit_code = _result_status(results)
    print(
        f"backend={results[0].get('backend') if results else '?'}  "
        f"ok={passed}/{EXPECTED_NETWORK_COUNT}  "
        f"executed={len(results)}/{EXPECTED_NETWORK_COUNT}"
    )
    print(
        "receipt_result_digest_binding=NOT EVALUATED "
        "(no approved client-recomputable result projection)"
    )
    if status == "NOT RUN":
        print("one or more required model-family scenarios were not executed")
    elif status == "FAIL" and len(results) < EXPECTED_NETWORK_COUNT:
        print(
            "stopped after the first attempted failure; reconcile or restart the "
            "development service before retry"
        )
    print(f"LOCAL SMOKE RESULT: {status}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
