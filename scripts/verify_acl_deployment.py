#!/usr/bin/env python3
"""Probe a live Zenoh router's mTLS and per-plane key ACL enforcement.

The return value of ``session.put`` is not ACL evidence: a local Zenoh session can
accept a put even when the router drops it. This verifier therefore establishes an
authenticated observer subscription first, publishes a unique nonce for every
trial, and judges the router only by delivery acknowledgments:

* an allowed nonce MUST reach the observer;
* a forbidden nonce or RPC reaching its destination is always a failure; and
* a clean negative observation requires a successful allowed baseline on the same
  plane, but remains inconclusive without a correlated router-side denial receipt.

Client-side validation, timeout, parsing, or declaration errors and authenticated
link loss are not denial evidence: those checks are ``NOT RUN``. A forbidden
correlated delivery is always ``FAIL``. Zenoh's Python API exposes no router ACL
denial acknowledgement, and this CLI accepts no vendor-specific audit-log format,
so bounded non-delivery is also ``NOT RUN`` rather than a server-attributed pass.
Exit status is 0 for PASS, 1 for FAIL, and 2 for NOT RUN or incomplete execution.

It covers command PUT = commander, sensor/observation PUT = body, delivery through
the actual sensor/session/fleet subscriber selectors, denied DELETE and wildcard
action publication, protocol-closed commander-to-body query/reply, negative
query/queryable roles, and a separate no-client-cert transport rejection. The
router must be rendered for the same exact quarantined ``--session-id``; never point
this synthetic-payload probe at an actuator-bound session.

The Zenoh CLI fallback was intentionally removed: ``z_put`` alone cannot prove
end-to-end delivery or distinguish ACL denial from a broken route.

This is a router-only prerequisite, not the NCP ``production-secure`` gate. The
current ``ncp-zenoh`` callback surface does not expose the authenticated remote
principal needed to bind a payload ``IdentityClaim``; ``ZenohBus.open_secure``
fails closed until that implementation gap is resolved.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import secrets
import sys
import threading
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from render_acl_template import valid_realm, valid_segment

ROLE_COMMANDER = "commander"
ROLE_BODY = "body"
ROLE_OBSERVER = "observer"
RECEIVER_OBSERVER_SESSION = "observer-session"
RECEIVER_OBSERVER_FLEET = "observer-fleet"
ROLE_COMMANDER_QUERYABLE = "commander-queryable"
ROLE_BODY_QUERY = "body-query"
PLANE_COMMAND = "command"
PLANE_SENSOR = "sensor"
PLANE_OBSERVATION = "observation"
MAX_DIAGNOSTIC_BYTES = 1_024
MAX_PROBE_KEY_BYTES = 1_024
MAX_PROBE_PAYLOAD_BYTES = 1_024
MAX_RECORDED_DELIVERIES = 4_096
MAX_RECORDED_RPC_REQUESTS = 4_096
MAX_ERROR_ENTRIES = 8
MAX_RPC_REPLIES = 64


class CheckStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_RUN = "NOT RUN"


def _bounded_text(value: object, limit: int = MAX_DIAGNOSTIC_BYTES) -> str:
    try:
        source = str(value)
    except Exception:
        source = "<diagnostic unavailable>"
    if limit <= 0:
        return ""
    marker = "..."[:limit]
    parts: list[str] = []
    part_sizes: list[int] = []
    encoded_bytes = 0
    for char in source:
        fragment = char if char.isprintable() else f"\\u{ord(char):04x}"
        fragment_bytes = fragment.encode("utf-8", errors="replace")
        if encoded_bytes + len(fragment_bytes) > limit:
            content_limit = max(0, limit - len(marker.encode("ascii")))
            while parts and encoded_bytes > content_limit:
                parts.pop()
                encoded_bytes -= part_sizes.pop()
            return "".join(parts) + marker
        parts.append(fragment)
        part_sizes.append(len(fragment_bytes))
        encoded_bytes += part_sizes[-1]
    return "".join(parts)


def _append_error(errors: list[str], error: object) -> None:
    if len(errors) < MAX_ERROR_ENTRIES:
        errors.append(_bounded_text(error))
    elif len(errors) == MAX_ERROR_ENTRIES:
        errors.append("additional errors omitted")


@dataclass(frozen=True)
class IdentityFiles:
    certificate: str
    private_key: str


@dataclass(frozen=True)
class ProbeCase:
    step: int
    actor: str
    plane: str
    key: str
    operation: str
    expect_delivery: bool
    required_receivers: tuple[str, ...] = ()


@dataclass(frozen=True)
class CheckResult:
    step: int
    description: str
    expected: str
    actual: str
    status: CheckStatus
    detail: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "description", _bounded_text(self.description, 256))
        object.__setattr__(self, "expected", _bounded_text(self.expected, 128))
        object.__setattr__(self, "actual", _bounded_text(self.actual, 128))
        object.__setattr__(self, "detail", _bounded_text(self.detail))

    @property
    def passed(self) -> bool:
        return self.status is CheckStatus.PASS

    def __str__(self) -> str:
        return (
            f"  [{self.status.value}] Step {self.step}: {self.description}\n"
            f"          expected={self.expected}, actual={self.actual}\n"
            f"          {self.detail}"
        )


def _nested(value: object, *path: str) -> object | None:
    for part in path:
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def _endpoint_strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for nested in value for item in _endpoint_strings(nested)]
    if isinstance(value, dict):
        return [item for nested in value.values() for item in _endpoint_strings(nested)]
    return []


def client_config_spec(
    endpoint: str,
    ca: str,
    identity: IdentityFiles | None,
) -> dict[str, object]:
    """Build the strict TLS client shape used by this router-only probe."""
    tls: dict[str, object] = {
        "root_ca_certificate": ca,
        "verify_name_on_connect": True,
        "close_link_on_expiration": True,
    }
    if identity is not None:
        tls["connect_certificate"] = identity.certificate
        tls["connect_private_key"] = identity.private_key
    return {
        "mode": "client",
        "connect": {"endpoints": [endpoint], "exit_on_failure": True},
        "listen": {"endpoints": []},
        "scouting": {
            "multicast": {"enabled": False},
            "gossip": {"enabled": False},
        },
        "transport": {"link": {"tls": tls}},
    }


def validate_client_config_spec(
    config: dict[str, object], *, require_identity: bool
) -> list[str]:
    """Validate the TLS client config prerequisite, not NCP identity binding."""
    errors: list[str] = []
    if config.get("mode") != "client":
        errors.append('mode must be "client"')
    endpoints = _endpoint_strings(_nested(config, "connect", "endpoints"))
    if not endpoints or any(
        not endpoint.startswith("tls/")
        or any(char.isspace() or ord(char) < 32 for char in endpoint)
        for endpoint in endpoints
    ):
        errors.append("connect endpoints must be non-empty and exclusively valid tls/ endpoints")
    if _nested(config, "connect", "exit_on_failure") is not True:
        errors.append("connect/exit_on_failure must be true")
    if _endpoint_strings(_nested(config, "listen", "endpoints")):
        errors.append("client must not expose listen endpoints")
    for path in (("scouting", "multicast", "enabled"), ("scouting", "gossip", "enabled")):
        if _nested(config, *path) is not False:
            errors.append(f"{'/'.join(path)} must be false")

    tls = _nested(config, "transport", "link", "tls")
    if not isinstance(tls, dict):
        return errors + ["transport/link/tls must be an object"]
    ca = tls.get("root_ca_certificate")
    if not isinstance(ca, str) or not ca.strip():
        errors.append("root_ca_certificate must be non-empty")
    if tls.get("verify_name_on_connect") is not True:
        errors.append("verify_name_on_connect must be true")
    if tls.get("close_link_on_expiration") is not True:
        errors.append("close_link_on_expiration must be true")
    certificate = tls.get("connect_certificate")
    private_key = tls.get("connect_private_key")
    if (certificate is None) != (private_key is None):
        errors.append("connect certificate and private key must be supplied together")
    if require_identity:
        if not isinstance(certificate, str) or not certificate.strip():
            errors.append("connect_certificate must be non-empty")
        if not isinstance(private_key, str) or not private_key.strip():
            errors.append("connect_private_key must be non-empty")
    elif certificate is not None or private_key is not None:
        errors.append("no-certificate probe must omit both client identity fields")
    return errors


def _insert_config_tree(config: Any, path: str, value: object) -> None:
    config.insert_json5(path, json.dumps(value, separators=(",", ":")))


def _to_zenoh_config(zenoh: Any, spec: dict[str, object]) -> Any:
    config = zenoh.Config()
    _insert_config_tree(config, "mode", spec["mode"])
    _insert_config_tree(config, "connect/endpoints", _nested(spec, "connect", "endpoints"))
    _insert_config_tree(
        config, "connect/exit_on_failure", _nested(spec, "connect", "exit_on_failure")
    )
    _insert_config_tree(config, "listen/endpoints", _nested(spec, "listen", "endpoints"))
    _insert_config_tree(
        config,
        "scouting/multicast/enabled",
        _nested(spec, "scouting", "multicast", "enabled"),
    )
    _insert_config_tree(
        config,
        "scouting/gossip/enabled",
        _nested(spec, "scouting", "gossip", "enabled"),
    )
    _insert_config_tree(config, "transport/link/tls", _nested(spec, "transport", "link", "tls"))
    return config


def _router_ids(session: Any) -> list[object]:
    info = session.info
    if callable(info):  # compatibility with older zenoh-python releases
        info = info()
    routers = info.routers_zid()
    return list(routers)


def _wait_for_router_evidence(
    session: Any, timeout_s: float
) -> tuple[bool, str | None]:
    deadline = time.monotonic() + timeout_s
    while True:
        try:
            if _router_ids(session):
                return True, None
        except Exception as error:
            return False, _bounded_text(error)
        if time.monotonic() >= deadline:
            return False, None
        time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))


def _wait_for_router(session: Any, timeout_s: float) -> bool:
    connected, error = _wait_for_router_evidence(session, timeout_s)
    return connected and error is None


def _sessions_connected(sessions: tuple[Any, ...]) -> bool:
    try:
        return bool(sessions) and all(bool(_router_ids(session)) for session in sessions)
    except Exception:
        return False


def _key_expr_text(value: object, *, label: str) -> str:
    if callable(value):
        value = value()
    key = str(value)
    encoded_bytes = 0
    for char in key:
        encoded_bytes += len(char.encode("utf-8"))
        if encoded_bytes > MAX_PROBE_KEY_BYTES:
            raise ValueError(
                f"{label} key is empty, malformed, or exceeds the probe limit"
            )
    if (
        not key
        or any(char.isspace() or not char.isprintable() for char in key)
    ):
        raise ValueError(f"{label} key is empty, malformed, or exceeds the probe limit")
    return key


def _bounded_payload_bytes(
    message: Any, *, allow_none: bool, label: str
) -> bytes:
    payload = message.payload
    if callable(payload):
        payload = payload()
    if payload is None:
        if allow_none:
            return b""
        raise ValueError(f"{label} payload is missing")
    if isinstance(payload, int):
        raise TypeError(f"{label} payload must be bytes-like")
    try:
        payload_length = payload.nbytes if isinstance(payload, memoryview) else len(payload)
    except (TypeError, AttributeError):
        payload_length = None
    if payload_length is not None and payload_length > MAX_PROBE_PAYLOAD_BYTES:
        raise ValueError(f"{label} payload exceeds the probe limit")
    if isinstance(payload, (bytes, bytearray, memoryview)):
        value = bytes(payload)
    else:
        to_bytes = getattr(payload, "to_bytes", None)
        converted = to_bytes() if callable(to_bytes) else payload
        if isinstance(converted, int):
            raise TypeError(f"{label} payload conversion was not bytes-like")
        try:
            converted_length = (
                converted.nbytes
                if isinstance(converted, memoryview)
                else len(converted)
            )
        except (TypeError, AttributeError):
            converted_length = None
        if (
            converted_length is not None
            and converted_length > MAX_PROBE_PAYLOAD_BYTES
        ):
            raise ValueError(f"{label} payload exceeds the probe limit")
        value = bytes(converted)
    if len(value) > MAX_PROBE_PAYLOAD_BYTES:
        raise ValueError(f"{label} payload exceeds the probe limit")
    return value


class DeliveryRecorder:
    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._deliveries: set[tuple[str, str, bytes]] = set()
        self._errors: list[str] = []
        self._error_events = 0

    def _record_error(self, error: object) -> None:
        self._error_events += 1
        _append_error(self._errors, error)

    def callback(self, sample: Any) -> None:
        try:
            key = _key_expr_text(sample.key_expr, label="sample")
            kind = getattr(sample, "kind", "put")
            if callable(kind):
                kind = kind()
            kind_name = getattr(kind, "name", None)
            kind_text = _bounded_text(
                kind_name if kind_name is not None else kind, 64
            ).strip().lower()
            if kind_name is None and "." in kind_text:
                kind_text = kind_text.rsplit(".", 1)[-1]
            if kind_text == "delete":
                operation = "delete"
            elif kind_text == "put":
                operation = "put"
            else:
                raise ValueError("sample kind is neither PUT nor DELETE")
            payload = (
                b""
                if operation == "delete"
                else _bounded_payload_bytes(
                    sample, allow_none=False, label="sample"
                )
            )
        except Exception as error:
            with self._condition:
                self._record_error(error)
                self._condition.notify_all()
            return
        with self._condition:
            delivery = (operation, key, payload)
            if (
                len(self._deliveries) >= MAX_RECORDED_DELIVERIES
                and delivery not in self._deliveries
            ):
                self._record_error("delivery recorder capacity exceeded")
                self._condition.notify_all()
                return
            self._deliveries.add(delivery)
            self._condition.notify_all()

    def wait(
        self, operation: str, key: str, payload: bytes, timeout_s: float
    ) -> bool:
        delivery = (operation, key, b"" if operation == "delete" else payload)
        deadline = time.monotonic() + timeout_s
        with self._condition:
            while delivery not in self._deliveries:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._condition.wait(remaining)
            return True

    def contains(self, operation: str, key: str, payload: bytes) -> bool:
        with self._condition:
            delivery = (operation, key, b"" if operation == "delete" else payload)
            return delivery in self._deliveries

    def error_count(self) -> int:
        with self._condition:
            return self._error_events

    def errors_since(self, marker: int) -> list[str]:
        with self._condition:
            return list(self._errors) if self._error_events > marker else []


class RpcRecorder:
    def __init__(self, key: str) -> None:
        self.key = key
        self._condition = threading.Condition()
        self._seen: set[bytes] = set()
        self._errors: list[str] = []
        self._error_events = 0

    def _record_error(self, error: object) -> None:
        self._error_events += 1
        _append_error(self._errors, error)

    @staticmethod
    def reply_payload(request_payload: bytes) -> bytes:
        return b"ncp-acl-rpc-reply:" + request_payload

    def callback(self, query: Any) -> None:
        try:
            request_payload = _bounded_payload_bytes(
                query, allow_none=True, label="RPC request"
            )
        except Exception as error:
            with self._condition:
                self._record_error(error)
                self._condition.notify_all()
            return
        with self._condition:
            if (
                len(self._seen) >= MAX_RECORDED_RPC_REQUESTS
                and request_payload not in self._seen
            ):
                self._record_error("RPC recorder capacity exceeded")
                self._condition.notify_all()
                return
            self._seen.add(request_payload)
            self._condition.notify_all()
        try:
            query.reply(self.key, self.reply_payload(request_payload))
        except Exception as error:
            with self._condition:
                self._record_error(error)
                self._condition.notify_all()

    def wait_seen(self, request_payload: bytes, timeout_s: float) -> bool:
        deadline = time.monotonic() + timeout_s
        with self._condition:
            while request_payload not in self._seen:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._condition.wait(remaining)
            return True

    def contains(self, request_payload: bytes) -> bool:
        with self._condition:
            return request_payload in self._seen

    def errors(self) -> list[str]:
        with self._condition:
            return list(self._errors)

    def error_count(self) -> int:
        with self._condition:
            return self._error_events

    def errors_since(self, marker: int) -> list[str]:
        with self._condition:
            return list(self._errors) if self._error_events > marker else []


def _rpc_replies(
    session: Any, key: str, request_payload: bytes, timeout_s: float
) -> tuple[list[bytes], list[str]]:
    payloads: list[bytes] = []
    errors: list[str] = []
    try:
        key = _key_expr_text(key, label="RPC request")
        if len(request_payload) > MAX_PROBE_PAYLOAD_BYTES:
            raise ValueError("RPC request payload exceeds the probe limit")
    except Exception as error:
        _append_error(errors, error)
        return payloads, errors
    try:
        replies = session.get(key, timeout=timeout_s, payload=request_payload)
        for reply_index, reply in enumerate(replies):
            if reply_index >= MAX_RPC_REPLIES:
                _append_error(errors, "RPC reply count exceeded the probe limit")
                break
            try:
                sample = reply.ok
                if callable(sample):
                    sample = sample()
                if sample is None:
                    raise ValueError("RPC reply did not contain a success sample")
                reply_error = getattr(reply, "err", None)
                if callable(reply_error):
                    reply_error = reply_error()
                if reply_error is not None:
                    raise ValueError("RPC reply contained both success and error values")
                reply_key = _key_expr_text(sample.key_expr, label="RPC reply")
                if reply_key != key:
                    raise ValueError("RPC reply key did not exactly match the query key")
                payload = _bounded_payload_bytes(
                    sample, allow_none=False, label="RPC reply"
                )
                payloads.append(payload)
            except Exception as error:
                _append_error(errors, error)
    except Exception as error:
        _append_error(errors, error)
    return payloads, errors


def _evaluate_delivery(
    *,
    expect_delivery: bool,
    observed: bool,
    plane_baseline_ok: bool,
    operation_submitted: bool,
    links_intact: bool,
    parsing_errors: list[str],
) -> tuple[CheckStatus, str]:
    if not expect_delivery and observed:
        return CheckStatus.FAIL, "forbidden nonce reached the independent observer"
    if parsing_errors:
        return CheckStatus.NOT_RUN, "receiver parsing/correlation was incomplete"
    if not links_intact:
        return CheckStatus.NOT_RUN, "authenticated actor or receiver link was not intact"
    if not operation_submitted:
        return (
            CheckStatus.NOT_RUN,
            "client-side operation error is not router-side denial evidence",
        )
    if expect_delivery and observed:
        return CheckStatus.PASS, "nonce delivery acknowledged"
    if expect_delivery:
        return CheckStatus.FAIL, "allowed nonce was not observed"
    if not plane_baseline_ok:
        return (
            CheckStatus.NOT_RUN,
            "denial is inconclusive because this plane has no allowed delivery baseline",
        )
    return (
        CheckStatus.NOT_RUN,
        "bounded non-delivery is not a correlated router-side denial receipt",
    )


def _evaluate_denied_rpc(
    *,
    positive_baseline_ok: bool,
    server_observed: bool,
    replies: list[bytes],
    client_errors: list[str],
    server_errors: list[str],
    links_intact: bool,
) -> tuple[CheckStatus, str]:
    if server_observed or replies:
        return CheckStatus.FAIL, "forbidden RPC query or reply crossed the router"
    if client_errors or server_errors:
        return CheckStatus.NOT_RUN, "client or reply error is not router denial evidence"
    if not links_intact:
        return CheckStatus.NOT_RUN, "authenticated RPC links were not intact"
    if not positive_baseline_ok:
        return CheckStatus.NOT_RUN, "positive RPC baseline was not established"
    return (
        CheckStatus.NOT_RUN,
        "bounded non-delivery is not a correlated router-side denial receipt",
    )


def _evaluate_positive_rpc(
    *,
    server_observed: bool,
    replies: list[bytes],
    expected_reply: bytes,
    client_errors: list[str],
    server_errors: list[str],
    links_intact: bool,
) -> CheckStatus:
    if client_errors or server_errors or not links_intact:
        return CheckStatus.NOT_RUN
    if server_observed and replies == [expected_reply]:
        return CheckStatus.PASS
    return CheckStatus.FAIL


def _aggregate_status(results: list[CheckResult]) -> CheckStatus:
    if not results:
        return CheckStatus.NOT_RUN
    if any(result.status is CheckStatus.FAIL for result in results):
        return CheckStatus.FAIL
    if any(result.status is CheckStatus.NOT_RUN for result in results):
        return CheckStatus.NOT_RUN
    return CheckStatus.PASS


def _probe_plan(realm: str, session_id: str) -> list[ProbeCase]:
    command = f"{realm}/session/{session_id}/command"
    sensor = f"{realm}/session/{session_id}/sensor"
    observation = f"{realm}/session/{session_id}/observation"
    command_receivers = (
        ROLE_BODY,
        RECEIVER_OBSERVER_SESSION,
        RECEIVER_OBSERVER_FLEET,
    )
    body_data_receivers = (
        ROLE_COMMANDER,
        RECEIVER_OBSERVER_SESSION,
        RECEIVER_OBSERVER_FLEET,
    )
    return [
        ProbeCase(1, ROLE_COMMANDER, PLANE_COMMAND, command, "put", True, command_receivers),
        ProbeCase(2, ROLE_BODY, PLANE_SENSOR, sensor, "put", True, body_data_receivers),
        ProbeCase(
            3,
            ROLE_BODY,
            PLANE_OBSERVATION,
            observation,
            "put",
            True,
            body_data_receivers,
        ),
        ProbeCase(4, ROLE_BODY, PLANE_COMMAND, command, "put", False, command_receivers),
        ProbeCase(5, ROLE_OBSERVER, PLANE_COMMAND, command, "put", False, command_receivers),
        ProbeCase(6, ROLE_COMMANDER, PLANE_SENSOR, sensor, "put", False, body_data_receivers),
        ProbeCase(7, ROLE_OBSERVER, PLANE_SENSOR, sensor, "put", False, body_data_receivers),
        ProbeCase(
            8,
            ROLE_COMMANDER,
            PLANE_OBSERVATION,
            observation,
            "put",
            False,
            body_data_receivers,
        ),
        ProbeCase(
            9,
            ROLE_OBSERVER,
            PLANE_OBSERVATION,
            observation,
            "put",
            False,
            body_data_receivers,
        ),
        ProbeCase(
            10,
            ROLE_COMMANDER,
            PLANE_COMMAND,
            command,
            "delete",
            False,
            command_receivers,
        ),
        ProbeCase(
            11,
            ROLE_BODY,
            PLANE_SENSOR,
            sensor,
            "delete",
            False,
            body_data_receivers,
        ),
        ProbeCase(
            12,
            ROLE_BODY,
            PLANE_OBSERVATION,
            observation,
            "delete",
            False,
            body_data_receivers,
        ),
        ProbeCase(
            13,
            ROLE_COMMANDER,
            PLANE_COMMAND,
            f"{realm}/session/*/command",
            "put",
            False,
            command_receivers,
        ),
        ProbeCase(
            14,
            ROLE_COMMANDER,
            PLANE_COMMAND,
            f"{realm}/session/{session_id}/command/*",
            "put",
            False,
            command_receivers,
        ),
        ProbeCase(
            15,
            ROLE_COMMANDER,
            PLANE_COMMAND,
            f"{realm}/session/{session_id}/command/forbidden/deep",
            "put",
            False,
            command_receivers,
        ),
    ]


def _required_path(value: str | None, label: str, errors: list[str]) -> str:
    if not value:
        errors.append(f"--{label} is required")
        return ""
    path = Path(value)
    if not path.is_file() or not os.access(path, os.R_OK):
        errors.append(f"--{label} does not name a readable file: {value}")
    return value


def _validate_live_args(args: argparse.Namespace) -> tuple[dict[str, dict[str, object]], list[str]]:
    errors: list[str] = []
    if not args.endpoint:
        errors.append("--endpoint is required")
    if not valid_realm(args.realm):
        errors.append(f"--realm is not a safe exact key prefix: {args.realm!r}")
    if not isinstance(args.session_id, str) or not valid_segment(args.session_id):
        errors.append(f"--session-id is not a safe exact key segment: {args.session_id!r}")
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        errors.append("--timeout must be finite and > 0")
    if not math.isfinite(args.settle) or args.settle < 0:
        errors.append("--settle must be finite and >= 0")

    ca = _required_path(args.ca, "ca", errors)
    identities = {
        ROLE_COMMANDER: IdentityFiles(
            _required_path(args.commander_cert, "commander-cert", errors),
            _required_path(args.commander_key, "commander-key", errors),
        ),
        ROLE_BODY: IdentityFiles(
            _required_path(args.body_cert, "body-cert", errors),
            _required_path(args.body_key, "body-key", errors),
        ),
        ROLE_OBSERVER: IdentityFiles(
            _required_path(args.observer_cert, "observer-cert", errors),
            _required_path(args.observer_key, "observer-key", errors),
        ),
    }
    resolved_certificates = {
        role: str(Path(identity.certificate).resolve())
        for role, identity in identities.items()
        if identity.certificate
    }
    if len(set(resolved_certificates.values())) != len(resolved_certificates):
        errors.append("commander, body, and observer must use distinct certificate files")
    resolved_keys = {
        role: str(Path(identity.private_key).resolve())
        for role, identity in identities.items()
        if identity.private_key
    }
    if len(set(resolved_keys.values())) != len(resolved_keys):
        errors.append("commander, body, and observer must use distinct private-key files")
    for role in resolved_certificates.keys() & resolved_keys.keys():
        if resolved_certificates[role] == resolved_keys[role]:
            errors.append(f"{role} certificate and private key must be separate files")
    endpoint = args.endpoint or ""
    specs = {
        role: client_config_spec(endpoint, ca, identity)
        for role, identity in identities.items()
    }
    specs["no-cert"] = client_config_spec(endpoint, ca, None)
    for role, spec in specs.items():
        config_errors = validate_client_config_spec(spec, require_identity=role != "no-cert")
        errors.extend(f"{role} client config: {error}" for error in config_errors)
    return specs, errors


def _close(resource: Any) -> None:
    try:
        undeclare = getattr(resource, "undeclare", None)
        if callable(undeclare):
            undeclare()
        else:
            close = getattr(resource, "close", None)
            if callable(close):
                close()
    except Exception:
        pass


def _verify_no_certificate(
    zenoh: Any,
    spec: dict[str, object],
    timeout_s: float,
    step: int,
    authenticated_sessions: tuple[Any, ...],
) -> CheckResult:
    description = "client with no certificate cannot establish mTLS"
    if not _sessions_connected(authenticated_sessions):
        return CheckResult(
            step,
            description,
            "NO_ROUTER_CONNECTION",
            "BASELINE_UNAVAILABLE",
            CheckStatus.NOT_RUN,
            "authenticated same-endpoint transport baseline was unavailable",
        )
    session = None
    try:
        session = zenoh.open(_to_zenoh_config(zenoh, spec))
    except Exception as error:
        return CheckResult(
            step,
            description,
            "NO_ROUTER_CONNECTION",
            "CLIENT_OPEN_ERROR",
            CheckStatus.NOT_RUN,
            "client open error is not attributable router-side denial evidence: "
            f"{_bounded_text(error)}",
        )
    try:
        connected, router_info_error = _wait_for_router_evidence(session, timeout_s)
        baseline_intact = _sessions_connected(authenticated_sessions)
        status = CheckStatus.FAIL if connected else CheckStatus.NOT_RUN
        return CheckResult(
            step,
            description,
            "NO_ROUTER_CONNECTION",
            "ROUTER_CONNECTED"
            if connected
            else "NO_ROUTER_CONNECTION"
            if baseline_intact and router_info_error is None
            else "EVIDENCE_INCOMPLETE",
            status,
            "router accepted a client that presented no certificate"
            if connected
            else "no router link appeared, but the client API supplied no correlated "
            "router-side mTLS denial receipt"
            if baseline_intact and router_info_error is None
            else f"router-info error={router_info_error!r}; authenticated baseline "
            f"intact={baseline_intact}",
        )
    finally:
        _close(session)


def run_live(args: argparse.Namespace, specs: dict[str, dict[str, object]]) -> int:
    try:
        import zenoh
    except ImportError:
        print("ERROR: zenoh-python is required (pip install eclipse-zenoh)", file=sys.stderr)
        return 2

    run_nonce = secrets.token_hex(12)
    session_id = args.session_id
    plan = _probe_plan(args.realm, session_id)
    sessions: dict[str, Any] = {}
    subscribers: list[Any] = []
    recorders = {
        ROLE_COMMANDER: DeliveryRecorder(),
        ROLE_BODY: DeliveryRecorder(),
        RECEIVER_OBSERVER_SESSION: DeliveryRecorder(),
        RECEIVER_OBSERVER_FLEET: DeliveryRecorder(),
    }
    results: list[CheckResult] = []
    denied_deliveries: list[
        tuple[
            int,
            str,
            str,
            bytes,
            tuple[str, ...],
            tuple[str, ...],
            dict[str, int],
        ]
    ] = []
    try:
        session_specs = {
            ROLE_COMMANDER: specs[ROLE_COMMANDER],
            ROLE_BODY: specs[ROLE_BODY],
            ROLE_OBSERVER: specs[ROLE_OBSERVER],
            RECEIVER_OBSERVER_SESSION: specs[ROLE_OBSERVER],
            RECEIVER_OBSERVER_FLEET: specs[ROLE_OBSERVER],
            ROLE_COMMANDER_QUERYABLE: specs[ROLE_COMMANDER],
            ROLE_BODY_QUERY: specs[ROLE_BODY],
        }
        for role, spec in session_specs.items():
            session = zenoh.open(_to_zenoh_config(zenoh, spec))
            sessions[role] = session
            if not _wait_for_router(session, args.timeout):
                print(
                    f"NOT RUN: {role} client did not establish an authenticated router link",
                    file=sys.stderr,
                )
                return 2

        subscription_keys: dict[str, tuple[str, ...]] = {
            ROLE_COMMANDER: (
                f"{args.realm}/session/{session_id}/sensor/**",
                f"{args.realm}/session/{session_id}/observation",
            ),
            ROLE_BODY: (f"{args.realm}/session/{session_id}/command",),
            RECEIVER_OBSERVER_SESSION: (
                f"{args.realm}/session/{session_id}/**",
            ),
            RECEIVER_OBSERVER_FLEET: (f"{args.realm}/session/**",),
        }
        for role, keys in subscription_keys.items():
            for key in keys:
                subscribers.append(
                    sessions[role].declare_subscriber(key, recorders[role].callback)
                )
        if args.settle:
            time.sleep(args.settle)

        plane_baselines: dict[str, CheckStatus] = {}
        for case in plan:
            payload = (
                f"ncp-acl-proof:{run_nonce}:{case.step}:{secrets.token_hex(16)}"
            ).encode("ascii")
            operation_submitted = False
            operation_detail = f"local {case.operation} was not submitted"
            required_links = set(case.required_receivers) | {
                RECEIVER_OBSERVER_FLEET if not case.expect_delivery else case.actor
            }
            required_links.add(case.actor)
            receiver_roles = case.required_receivers
            error_markers = {
                role: recorders[role].error_count() for role in receiver_roles
            }
            links_before = _sessions_connected(
                tuple(sessions[role] for role in required_links)
            )
            try:
                if links_before:
                    if case.operation == "put":
                        sessions[case.actor].put(case.key, payload)
                    elif case.operation == "delete":
                        sessions[case.actor].delete(case.key)
                    else:  # pragma: no cover - frozen probe-plan invariant
                        raise AssertionError(
                            f"unsupported probe operation {case.operation!r}"
                        )
                    operation_submitted = True
                    operation_detail = f"local {case.operation} submitted"
                else:
                    operation_detail = "required authenticated links absent before submit"
            except Exception as error:
                operation_detail = (
                    f"local {case.operation} error before attributable denial: "
                    f"{_bounded_text(error)}"
                )
            if case.expect_delivery:
                observed_receivers = [
                    receiver
                    for receiver in case.required_receivers
                    if recorders[receiver].wait(
                        case.operation, case.key, payload, args.timeout
                    )
                ]
                observed = len(observed_receivers) == len(case.required_receivers)
                delivery_detail = (
                    "required receivers="
                    f"{list(case.required_receivers)}, observed={observed_receivers}"
                )
            else:
                # Wait one bounded window on the broad independent observer, then
                # inspect every actual plane receiver. A router that leaks a
                # forbidden command only to the body is still an immediate FAIL.
                recorders[RECEIVER_OBSERVER_FLEET].wait(
                    case.operation, case.key, payload, args.timeout
                )
                observed_receivers = [
                    receiver
                    for receiver in case.required_receivers
                    if recorders[receiver].contains(
                        case.operation, case.key, payload
                    )
                ]
                observed = bool(observed_receivers)
                delivery_detail = (
                    "forbidden delivery checked at receivers="
                    f"{list(case.required_receivers)}, observed={observed_receivers}"
                )
            parsing_errors = [
                error
                for role in receiver_roles
                for error in recorders[role].errors_since(error_markers[role])
            ]
            links_after = _sessions_connected(
                tuple(sessions[role] for role in required_links)
            )
            status, detail = _evaluate_delivery(
                expect_delivery=case.expect_delivery,
                observed=observed,
                plane_baseline_ok=(
                    plane_baselines.get(case.plane) is CheckStatus.PASS
                ),
                operation_submitted=operation_submitted,
                links_intact=links_before and links_after,
                parsing_errors=parsing_errors,
            )
            if case.expect_delivery:
                plane_baselines[case.plane] = status
            else:
                denied_deliveries.append(
                    (
                        len(results),
                        case.operation,
                        case.key,
                        payload,
                        tuple(sorted(required_links)),
                        case.required_receivers,
                        error_markers,
                    )
                )
            results.append(
                CheckResult(
                    case.step,
                    f"{case.actor} {case.operation.upper()} on {case.plane} plane",
                    "DELIVERED" if case.expect_delivery else "NOT_DELIVERED",
                    "DELIVERED"
                    if observed
                    else (
                        "NOT_DELIVERED" if operation_submitted else "NOT_SUBMITTED"
                    ),
                    status,
                    f"{detail}; {delivery_detail}; parsing_errors={parsing_errors}; "
                    f"{operation_detail}",
                )
            )

        # One final rejection window catches a forbidden sample that arrived just
        # after its per-case timeout. Nonces are unique, so no legitimate traffic
        # can satisfy this check accidentally.
        time.sleep(args.timeout)
        for (
            result_index,
            operation,
            key,
            payload,
            required_roles,
            receiver_roles,
            error_markers,
        ) in denied_deliveries:
            observed_receivers = [
                role
                for role in receiver_roles
                if recorders[role].contains(operation, key, payload)
            ]
            if observed_receivers:
                previous = results[result_index]
                results[result_index] = CheckResult(
                    previous.step,
                    previous.description,
                    previous.expected,
                    "DELIVERED",
                    CheckStatus.FAIL,
                    "forbidden nonce arrived during the final rejection quarantine "
                    f"at receivers={observed_receivers}",
                )
            elif (
                any(
                    recorders[role].errors_since(error_markers[role])
                    for role in receiver_roles
                )
                or not _sessions_connected(
                    tuple(sessions[role] for role in required_roles)
                )
            ):
                previous = results[result_index]
                if previous.status is not CheckStatus.FAIL:
                    results[result_index] = CheckResult(
                        previous.step,
                        previous.description,
                        previous.expected,
                        "EVIDENCE_INCOMPLETE",
                        CheckStatus.NOT_RUN,
                        "receiver parsing or authenticated link continuity failed during "
                        "the final rejection quarantine",
                    )

        rpc_key = f"{args.realm}/rpc/open_session"
        rpc_recorder = RpcRecorder(rpc_key)
        subscribers.append(
            sessions[ROLE_BODY].declare_queryable(
                f"{args.realm}/rpc/*", rpc_recorder.callback
            )
        )
        if args.settle:
            time.sleep(args.settle)

        rpc_positive = f"ncp-acl-rpc:{run_nonce}:commander".encode("ascii")
        positive_server_error_marker = rpc_recorder.error_count()
        positive_links_before = _sessions_connected(
            (sessions[ROLE_COMMANDER], sessions[ROLE_BODY])
        )
        positive_replies, positive_errors = _rpc_replies(
            sessions[ROLE_COMMANDER], rpc_key, rpc_positive, args.timeout
        )
        positive_seen = rpc_recorder.wait_seen(rpc_positive, args.timeout)
        expected_reply = RpcRecorder.reply_payload(rpc_positive)
        positive_server_errors = rpc_recorder.errors_since(
            positive_server_error_marker
        )
        positive_links_intact = positive_links_before and _sessions_connected(
            (sessions[ROLE_COMMANDER], sessions[ROLE_BODY])
        )
        positive_status = _evaluate_positive_rpc(
            server_observed=positive_seen,
            replies=positive_replies,
            expected_reply=expected_reply,
            client_errors=positive_errors,
            server_errors=positive_server_errors,
            links_intact=positive_links_intact,
        )
        positive_ok = positive_status is CheckStatus.PASS
        results.append(
            CheckResult(
                len(plan) + 1,
                "commander query reaches body queryable and body reply returns",
                "QUERY_AND_REPLY_DELIVERED",
                "QUERY_AND_REPLY_DELIVERED" if positive_ok else "RPC_INCOMPLETE",
                positive_status,
                "body query observed="
                f"{positive_seen}; replies={len(positive_replies)}; "
                f"client_errors={positive_errors}; server_errors={positive_server_errors}; "
                f"links_intact={positive_links_intact}",
            )
        )

        observer_query = f"ncp-acl-rpc:{run_nonce}:observer-query".encode("ascii")
        observer_server_error_marker = rpc_recorder.error_count()
        observer_links_before = _sessions_connected(
            (sessions[ROLE_OBSERVER], sessions[ROLE_BODY])
        )
        observer_replies, observer_errors = _rpc_replies(
            sessions[ROLE_OBSERVER], rpc_key, observer_query, args.timeout
        )
        time.sleep(args.timeout)
        observer_seen = rpc_recorder.contains(observer_query)
        observer_server_errors = rpc_recorder.errors_since(
            observer_server_error_marker
        )
        observer_status, observer_detail = _evaluate_denied_rpc(
            positive_baseline_ok=positive_ok,
            server_observed=observer_seen,
            replies=observer_replies,
            client_errors=observer_errors,
            server_errors=observer_server_errors,
            links_intact=observer_links_before
            and _sessions_connected((sessions[ROLE_OBSERVER], sessions[ROLE_BODY])),
        )
        results.append(
            CheckResult(
                len(plan) + 2,
                "observer cannot issue lifecycle RPC query",
                "QUERY_NOT_DELIVERED",
                "QUERY_OR_REPLY_DELIVERED"
                if observer_seen or observer_replies
                else "QUERY_NOT_DELIVERED",
                observer_status,
                f"{observer_detail}; positive RPC baseline="
                f"{positive_ok}; replies={len(observer_replies)}; "
                f"client_errors={observer_errors}; "
                f"server_errors={observer_server_errors}",
            )
        )

        body_query = f"ncp-acl-rpc:{run_nonce}:body-query".encode("ascii")
        body_server_error_marker = rpc_recorder.error_count()
        body_links_before = _sessions_connected(
            (sessions[ROLE_BODY_QUERY], sessions[ROLE_BODY])
        )
        body_replies, body_errors = _rpc_replies(
            sessions[ROLE_BODY_QUERY], rpc_key, body_query, args.timeout
        )
        time.sleep(args.timeout)
        body_seen = rpc_recorder.contains(body_query)
        body_server_errors = rpc_recorder.errors_since(body_server_error_marker)
        body_query_status, body_query_detail = _evaluate_denied_rpc(
            positive_baseline_ok=positive_ok,
            server_observed=body_seen,
            replies=body_replies,
            client_errors=body_errors,
            server_errors=body_server_errors,
            links_intact=body_links_before
            and _sessions_connected((sessions[ROLE_BODY_QUERY], sessions[ROLE_BODY])),
        )
        results.append(
            CheckResult(
                len(plan) + 3,
                "body cannot issue lifecycle RPC query",
                "QUERY_NOT_DELIVERED",
                "QUERY_OR_REPLY_DELIVERED"
                if body_seen or body_replies
                else "QUERY_NOT_DELIVERED",
                body_query_status,
                f"{body_query_detail}; positive RPC baseline={positive_ok}; "
                f"replies={len(body_replies)}; "
                f"client_errors={body_errors}; server_errors={body_server_errors}",
            )
        )

        for offset, (role, description) in enumerate(
            (
                (ROLE_OBSERVER, "observer cannot serve or reply to lifecycle RPC"),
                (
                    ROLE_COMMANDER_QUERYABLE,
                    "commander cannot serve or reply to lifecycle RPC",
                ),
            ),
            start=4,
        ):
            unauthorized = RpcRecorder(rpc_key)
            unauthorized_handle = None
            declaration_submitted = False
            declaration_detail = "local declaration was not submitted"
            declaration_links_before = _sessions_connected((sessions[role],))
            try:
                if declaration_links_before:
                    unauthorized_handle = sessions[role].declare_queryable(
                        rpc_key, unauthorized.callback
                    )
                    subscribers.append(unauthorized_handle)
                    declaration_submitted = True
                    declaration_detail = "local declaration submitted"
                else:
                    declaration_detail = (
                        "required authenticated link absent before declaration"
                    )
            except Exception as error:
                declaration_detail = (
                    "client declaration error is not router denial evidence: "
                    f"{_bounded_text(error)}"
                )
            if args.settle:
                time.sleep(args.settle)
            probe = f"ncp-acl-rpc:{run_nonce}:{role}-queryable".encode("ascii")
            body_server_error_marker = rpc_recorder.error_count()
            unauthorized_error_marker = unauthorized.error_count()
            query_links_before = _sessions_connected(
                (sessions[role], sessions[ROLE_COMMANDER], sessions[ROLE_BODY])
            )
            replies, query_errors = _rpc_replies(
                sessions[ROLE_COMMANDER], rpc_key, probe, args.timeout
            )
            body_observed = rpc_recorder.wait_seen(probe, args.timeout)
            unauthorized_observed = unauthorized.wait_seen(probe, args.timeout)
            expected_body_reply = RpcRecorder.reply_payload(probe)
            body_server_errors = rpc_recorder.errors_since(
                body_server_error_marker
            )
            unauthorized_errors = unauthorized.errors_since(
                unauthorized_error_marker
            )
            links_intact = (
                declaration_links_before
                and query_links_before
                and _sessions_connected(
                (sessions[role], sessions[ROLE_COMMANDER], sessions[ROLE_BODY])
                )
            )
            if unauthorized_observed:
                queryable_status = CheckStatus.FAIL
                queryable_detail = "forbidden query reached the unauthorized queryable"
            elif (
                not declaration_submitted
                or query_errors
                or body_server_errors
                or unauthorized_errors
                or not links_intact
                or not positive_ok
            ):
                queryable_status = CheckStatus.NOT_RUN
                queryable_detail = "queryable denial evidence was incomplete"
            elif not body_observed or replies != [expected_body_reply]:
                queryable_status = CheckStatus.FAIL
                queryable_detail = "authorized body query/reply correlation failed"
            else:
                queryable_status = CheckStatus.NOT_RUN
                queryable_detail = (
                    "bounded non-delivery is not a correlated router-side denial receipt"
                )
            results.append(
                CheckResult(
                    len(plan) + offset,
                    description,
                    "UNAUTHORIZED_QUERYABLE_NOT_REACHED",
                    "UNAUTHORIZED_QUERYABLE_REACHED"
                    if unauthorized_observed
                    else (
                        "UNAUTHORIZED_QUERYABLE_NOT_REACHED"
                        if declaration_submitted
                        else "NOT_SUBMITTED"
                    ),
                    queryable_status,
                    f"{queryable_detail}; body baseline observed={body_observed}; "
                    f"replies={len(replies)}; "
                    f"client_errors={query_errors}; "
                    f"body_server_errors={body_server_errors}; "
                    f"unauthorized_errors={unauthorized_errors}; "
                    f"links_intact={links_intact}; "
                    f"{declaration_detail}",
                )
            )
            if unauthorized_handle is not None:
                _close(unauthorized_handle)

        results.append(
            _verify_no_certificate(
                zenoh,
                specs["no-cert"],
                args.timeout,
                len(plan) + 6,
                tuple(sessions.values()),
            )
        )
    except Exception as error:
        print(
            f"NOT RUN: live verification could not complete: {_bounded_text(error)}",
            file=sys.stderr,
        )
        return 2
    finally:
        for subscriber in reversed(subscribers):
            _close(subscriber)
        for session in sessions.values():
            _close(session)

    print("Zenoh router ACL prerequisite (nonce delivery proof)")
    print(f"  endpoint: {_bounded_text(args.endpoint)}")
    print(f"  realm:    {_bounded_text(args.realm)}")
    print(
        f"  session:  {_bounded_text(session_id)} "
        "(exact pre-rendered quarantine namespace)"
    )
    print()
    for result in results:
        print(result)
    print()
    overall = _aggregate_status(results)
    if overall is CheckStatus.PASS:
        print(
            "RESULT: ROUTER-ONLY PRECHECK PASSED — positive deliveries and explicit "
            "router-attributed denials were correlated. NCP "
            "production-secure remains blocked until transport-authenticated peer "
            "identity is bound to IdentityClaim."
        )
        return 0
    failed = sum(result.status is CheckStatus.FAIL for result in results)
    not_run = sum(result.status is CheckStatus.NOT_RUN for result in results)
    if overall is CheckStatus.NOT_RUN:
        print(
            f"RESULT: NOT RUN — {not_run} of {len(results)} invariants lacked "
            "attributable router evidence; deployment is NOT validated."
        )
        return 2
    print(
        f"RESULT: {failed} of {len(results)} invariants FAILED"
        + (f" and {not_run} were NOT RUN" if not_run else "")
        + " — deployment is NOT validated."
    )
    return 1


def _selftest() -> list[str]:
    failures: list[str] = []
    identity = IdentityFiles("client.pem", "client-key.pem")
    good = client_config_spec("tls/router.example:7447", "ca.pem", identity)
    if validate_client_config_spec(good, require_identity=True):
        failures.append("strict identity config was rejected")
    no_cert = client_config_spec("tls/router.example:7447", "ca.pem", None)
    if validate_client_config_spec(no_cert, require_identity=False):
        failures.append("intentional no-cert config was rejected by base validation")
    if not validate_client_config_spec(good, require_identity=False):
        failures.append("no-cert validation accepted a config that still carried an identity")

    mutations: list[tuple[str, dict[str, object], bool]] = []
    plaintext = json.loads(json.dumps(good))
    plaintext["connect"]["endpoints"] = ["tcp/router.example:7447"]  # type: ignore[index]
    mutations.append(("plaintext endpoint", plaintext, True))
    listener = json.loads(json.dumps(good))
    listener["listen"]["endpoints"] = ["tls/0.0.0.0:0"]  # type: ignore[index]
    mutations.append(("client listener", listener, True))
    discovery = json.loads(json.dumps(good))
    discovery["scouting"]["multicast"]["enabled"] = True  # type: ignore[index]
    mutations.append(("multicast discovery", discovery, True))
    no_name_check = json.loads(json.dumps(good))
    no_name_check["transport"]["link"]["tls"]["verify_name_on_connect"] = False  # type: ignore[index]
    mutations.append(("disabled TLS name verification", no_name_check, True))
    no_expiration_close = json.loads(json.dumps(good))
    no_expiration_close["transport"]["link"]["tls"][
        "close_link_on_expiration"
    ] = False  # type: ignore[index]
    mutations.append(("expired TLS link retention", no_expiration_close, True))
    no_connect_fail = json.loads(json.dumps(good))
    no_connect_fail["connect"]["exit_on_failure"] = False  # type: ignore[index]
    mutations.append(("connect fail-soft mode", no_connect_fail, True))
    missing_key = json.loads(json.dumps(good))
    del missing_key["transport"]["link"]["tls"]["connect_private_key"]  # type: ignore[index]
    mutations.append(("unpaired client certificate", missing_key, True))
    for description, config, require_identity in mutations:
        if not validate_client_config_spec(config, require_identity=require_identity):
            failures.append(f"{description} was NOT rejected")

    # Clean submission, a positive baseline, intact authenticated links, bounded
    # parsing, and exact nonce non-delivery narrow causes but cannot prove a router
    # ACL denial without a correlated router-side receipt.
    truth_cases = [
        (True, True, False, True, True, [], CheckStatus.PASS),
        (True, False, False, True, True, [], CheckStatus.FAIL),
        (True, True, False, False, True, [], CheckStatus.NOT_RUN),
        (False, False, True, True, True, [], CheckStatus.NOT_RUN),
        (False, True, True, False, True, [], CheckStatus.FAIL),
        (False, False, False, True, True, [], CheckStatus.NOT_RUN),
        (False, False, True, False, True, [], CheckStatus.NOT_RUN),
        (False, False, True, True, False, [], CheckStatus.NOT_RUN),
        (False, False, True, True, True, ["parse"], CheckStatus.NOT_RUN),
    ]
    for expect, observed, baseline, submitted, links, parse_errors, wanted in truth_cases:
        got, _ = _evaluate_delivery(
            expect_delivery=expect,
            observed=observed,
            plane_baseline_ok=baseline,
            operation_submitted=submitted,
            links_intact=links,
            parsing_errors=parse_errors,
        )
        if got is not wanted:
            failures.append(
                "delivery evaluator accepted an unsafe truth-table case: "
                f"expect={expect} observed={observed} baseline={baseline} "
                f"submitted={submitted} links={links} parse_errors={bool(parse_errors)}"
            )

    rpc_truth_cases = [
        (True, False, [], [], [], True, CheckStatus.NOT_RUN),
        (True, False, [], ["timeout"], [], True, CheckStatus.NOT_RUN),
        (True, False, [], [], ["parse"], True, CheckStatus.NOT_RUN),
        (True, True, [], ["other"], [], True, CheckStatus.FAIL),
        (True, False, [b"unrelated"], [], [], True, CheckStatus.FAIL),
        (False, False, [], [], [], True, CheckStatus.NOT_RUN),
        (True, False, [], [], [], False, CheckStatus.NOT_RUN),
    ]
    for (
        baseline,
        seen,
        replies,
        client_errors,
        server_errors,
        links,
        wanted,
    ) in rpc_truth_cases:
        got, _ = _evaluate_denied_rpc(
            positive_baseline_ok=baseline,
            server_observed=seen,
            replies=replies,
            client_errors=client_errors,
            server_errors=server_errors,
            links_intact=links,
        )
        if got is not wanted:
            failures.append(
                "RPC denial evaluator accepted unsafe evidence: "
                f"baseline={baseline} seen={seen} replies={len(replies)} "
                f"errors={bool(client_errors or server_errors)} links={links}"
            )

    expected_rpc_reply = b"correlated"
    positive_rpc_cases = [
        (True, [expected_rpc_reply], [], [], True, CheckStatus.PASS),
        (
            True,
            [expected_rpc_reply, b"unrelated"],
            [],
            [],
            True,
            CheckStatus.FAIL,
        ),
        (True, [expected_rpc_reply], ["timeout"], [], True, CheckStatus.NOT_RUN),
        (True, [expected_rpc_reply], [], ["reply error"], True, CheckStatus.NOT_RUN),
        (True, [expected_rpc_reply], [], [], False, CheckStatus.NOT_RUN),
        (False, [], [], [], True, CheckStatus.FAIL),
    ]
    for seen, replies, client_errors, server_errors, links, wanted in positive_rpc_cases:
        got = _evaluate_positive_rpc(
            server_observed=seen,
            replies=replies,
            expected_reply=expected_rpc_reply,
            client_errors=client_errors,
            server_errors=server_errors,
            links_intact=links,
        )
        if got is not wanted:
            failures.append(
                "positive RPC evaluator accepted malformed or unrelated evidence"
            )

    def result(status: CheckStatus) -> CheckResult:
        return CheckResult(1, "test", "expected", "actual", status, "detail")

    if _aggregate_status([result(CheckStatus.PASS)]) is not CheckStatus.PASS:
        failures.append("PASS aggregate was not preserved")
    if (
        _aggregate_status([result(CheckStatus.PASS), result(CheckStatus.NOT_RUN)])
        is not CheckStatus.NOT_RUN
    ):
        failures.append("NOT RUN aggregate was not preserved")
    if (
        _aggregate_status([result(CheckStatus.NOT_RUN), result(CheckStatus.FAIL)])
        is not CheckStatus.FAIL
    ):
        failures.append("FAIL aggregate did not take precedence")

    bounded = CheckResult(
        1,
        "test",
        "expected",
        "actual",
        CheckStatus.NOT_RUN,
        "x" * (MAX_DIAGNOSTIC_BYTES * 2) + "\ncontrol",
    )
    if len(bounded.detail.encode("utf-8")) > MAX_DIAGNOSTIC_BYTES or "\n" in bounded.detail:
        failures.append("diagnostic bounding or control escaping failed")
    if _bounded_text("exact", len("exact")) != "exact":
        failures.append("diagnostic bounding truncated an exactly bounded value")

    class Sample:
        def __init__(self, key: str, kind: str, payload: bytes) -> None:
            self.key_expr = key
            self.kind = kind
            self.payload = payload

    delivery_recorder = DeliveryRecorder()
    marker = delivery_recorder.error_count()
    delivery_recorder.callback(Sample("ncp/session/s/command", "unknown", b"nonce"))
    delivery_recorder.callback(Sample("ncp/session/s/command", "not-put", b"nonce"))
    delivery_recorder.callback(Sample("ncp/session/s/command\nforged", "put", b"nonce"))
    delivery_recorder.callback(
        Sample(
            "ncp/session/s/command",
            "put",
            b"x" * (MAX_PROBE_PAYLOAD_BYTES + 1),
        )
    )
    if not delivery_recorder.errors_since(marker):
        failures.append("delivery recorder accepted malformed or oversized input")
    integer_payload_marker = delivery_recorder.error_count()
    delivery_recorder.callback(
        Sample("ncp/session/s/command", "put", MAX_PROBE_PAYLOAD_BYTES + 1)  # type: ignore[arg-type]
    )
    if not delivery_recorder.errors_since(integer_payload_marker):
        failures.append("delivery recorder accepted an allocating integer payload")
    delivery_recorder.callback(Sample("ncp/session/s/command", "put", b"nonce"))
    if not delivery_recorder.contains("put", "ncp/session/s/command", b"nonce"):
        failures.append("delivery recorder lost an exact bounded nonce")
    if delivery_recorder.contains("put", "ncp/session/s/command", b"other"):
        failures.append("delivery recorder correlated an unrelated payload")

    class FailingReplyQuery:
        payload = b"hostile-query"

        @staticmethod
        def reply(_key: str, _payload: bytes) -> None:
            raise RuntimeError("reply failed")

    rpc_recorder = RpcRecorder("ncp/rpc/open_session")
    rpc_error_marker = rpc_recorder.error_count()
    rpc_recorder.callback(FailingReplyQuery())
    if (
        not rpc_recorder.contains(b"hostile-query")
        or not rpc_recorder.errors_since(rpc_error_marker)
    ):
        failures.append("RPC recorder lost query receipt when reply failed")

    class Reply:
        def __init__(self, ok: object) -> None:
            self.ok = ok

    class ReplySample:
        def __init__(
            self, payload: bytes, key_expr: str = "ncp/rpc/open_session"
        ) -> None:
            self.payload = payload
            self.key_expr = key_expr

    class RpcSession:
        def __init__(self, replies: object) -> None:
            self.replies = replies

        def get(self, _key: str, **_kwargs: object) -> object:
            if isinstance(self.replies, Exception):
                raise self.replies
            return self.replies

    payloads, errors = _rpc_replies(
        RpcSession(RuntimeError("client timeout")), "ncp/rpc/open_session", b"nonce", 0.0
    )
    if payloads or not errors:
        failures.append("client RPC timeout was not retained as incomplete evidence")
    payloads, errors = _rpc_replies(
        RpcSession([Reply(None)]), "ncp/rpc/open_session", b"nonce", 0.0
    )
    if payloads or not errors:
        failures.append("malformed RPC reply was accepted as correlated evidence")
    payloads, errors = _rpc_replies(
        RpcSession([Reply(ReplySample(b"exact", "ncp/rpc/unrelated"))]),
        "ncp/rpc/open_session",
        b"nonce",
        0.0,
    )
    if payloads or not errors:
        failures.append("wrong-key RPC reply was accepted as correlated evidence")
    payloads, errors = _rpc_replies(
        RpcSession(
            [Reply(ReplySample(b"x" * (MAX_PROBE_PAYLOAD_BYTES + 1)))]
        ),
        "ncp/rpc/open_session",
        b"nonce",
        0.0,
    )
    if payloads or not errors:
        failures.append("oversized RPC reply was accepted as correlated evidence")
    payloads, errors = _rpc_replies(
        RpcSession([Reply(ReplySample(b"exact"))]),
        "ncp/rpc/open_session",
        b"nonce",
        0.0,
    )
    if payloads != [b"exact"] or errors:
        failures.append("exact bounded RPC reply did not survive correlation parsing")
    payloads, errors = _rpc_replies(
        RpcSession(
            [Reply(ReplySample(b"exact")) for _ in range(MAX_RPC_REPLIES + 1)]
        ),
        "ncp/rpc/open_session",
        b"nonce",
        0.0,
    )
    if len(payloads) != MAX_RPC_REPLIES or not errors:
        failures.append("RPC reply-count bound did not reject excess valid replies")

    class FakeInfo:
        def __init__(self, routers: list[object] | Exception) -> None:
            self.routers = routers

        def routers_zid(self) -> list[object]:
            if isinstance(self.routers, Exception):
                raise self.routers
            return self.routers

    class FakeSession:
        def __init__(self, routers: list[object] | Exception) -> None:
            self.info = FakeInfo(routers)

        def close(self) -> None:
            return None

    class FakeConfig:
        def insert_json5(self, _path: str, _value: str) -> None:
            return None

    class FakeZenoh:
        Config = FakeConfig

        def __init__(self, opened: FakeSession | Exception) -> None:
            self.opened = opened

        def open(self, _config: object) -> FakeSession:
            if isinstance(self.opened, Exception):
                raise self.opened
            return self.opened

    authenticated = FakeSession([object()])
    no_cert_cases = [
        (FakeZenoh(RuntimeError("local validation")), CheckStatus.NOT_RUN),
        (FakeZenoh(FakeSession([])), CheckStatus.NOT_RUN),
        (FakeZenoh(FakeSession([object()])), CheckStatus.FAIL),
        (
            FakeZenoh(FakeSession(RuntimeError("malformed router info"))),
            CheckStatus.NOT_RUN,
        ),
    ]
    for fake_zenoh, wanted in no_cert_cases:
        got = _verify_no_certificate(
            fake_zenoh, no_cert, 0.0, 1, (authenticated,)
        )
        if got.status is not wanted:
            failures.append(
                "no-certificate probe accepted unsafe evidence: "
                f"wanted={wanted.value} got={got.status.value}"
            )

    plan = _probe_plan("engram/ncp", "acl-verify-test")
    expected_authority = {
        (ROLE_COMMANDER, PLANE_COMMAND, "put", True),
        (ROLE_BODY, PLANE_SENSOR, "put", True),
        (ROLE_BODY, PLANE_OBSERVATION, "put", True),
        (ROLE_BODY, PLANE_COMMAND, "put", False),
        (ROLE_OBSERVER, PLANE_COMMAND, "put", False),
        (ROLE_COMMANDER, PLANE_SENSOR, "put", False),
        (ROLE_OBSERVER, PLANE_SENSOR, "put", False),
        (ROLE_COMMANDER, PLANE_OBSERVATION, "put", False),
        (ROLE_OBSERVER, PLANE_OBSERVATION, "put", False),
        (ROLE_COMMANDER, PLANE_COMMAND, "delete", False),
        (ROLE_BODY, PLANE_SENSOR, "delete", False),
        (ROLE_BODY, PLANE_OBSERVATION, "delete", False),
    }
    actual_authority = {
        (case.actor, case.plane, case.operation, case.expect_delivery)
        for case in plan
        if case.step <= 12
    }
    if actual_authority != expected_authority or len(plan) != 15:
        failures.append("live probe plan lost an authority or negative case")
    expected_receivers = {
        PLANE_COMMAND: (
            ROLE_BODY,
            RECEIVER_OBSERVER_SESSION,
            RECEIVER_OBSERVER_FLEET,
        ),
        PLANE_SENSOR: (
            ROLE_COMMANDER,
            RECEIVER_OBSERVER_SESSION,
            RECEIVER_OBSERVER_FLEET,
        ),
        PLANE_OBSERVATION: (
            ROLE_COMMANDER,
            RECEIVER_OBSERVER_SESSION,
            RECEIVER_OBSERVER_FLEET,
        ),
    }
    for case in plan:
        wanted = expected_receivers.get(case.plane, ())
        if case.required_receivers != wanted:
            failures.append(
                f"{case.plane} probe has wrong receivers {case.required_receivers!r}"
            )
    wildcard_cases = {case.step: case.key for case in plan if case.step >= 13}
    if wildcard_cases != {
        13: "engram/ncp/session/*/command",
        14: "engram/ncp/session/acl-verify-test/command/*",
        15: "engram/ncp/session/acl-verify-test/command/forbidden/deep",
    }:
        failures.append("probe plan lost wildcard/deep action-route negatives")
    return failures


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--self-test", action="store_true", help="run offline negative self-tests")
    parser.add_argument("--dry-run", action="store_true", help="validate inputs and print the probe plan")
    parser.add_argument("--endpoint", help="Zenoh TLS endpoint, e.g. tls/router.example:7447")
    parser.add_argument("--realm", default="ncp", help="exact realm key prefix")
    parser.add_argument(
        "--session-id",
        dest="session_id",
        help="required exact pre-rendered quarantined session id; no legacy prefix alias",
    )
    parser.add_argument("--commander-cert")
    parser.add_argument("--commander-key")
    parser.add_argument("--body-cert")
    parser.add_argument("--body-key")
    parser.add_argument("--observer-cert")
    parser.add_argument("--observer-key")
    parser.add_argument("--ca", help="router CA certificate")
    parser.add_argument("--timeout", type=float, default=2.0, help="delivery/rejection window seconds")
    parser.add_argument("--settle", type=float, default=0.5, help="subscriber propagation delay seconds")
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.self_test:
        failures = _selftest()
        if failures:
            print("FAIL: ACL deployment verifier self-test failed:", file=sys.stderr)
            for failure in failures:
                print(f"  - {_bounded_text(failure)}", file=sys.stderr)
            return 1
        print("OK: ACL deployment verifier offline self-test passed")
        return 0

    specs, errors = _validate_live_args(args)
    if errors:
        print("ERROR: invalid live verification configuration:", file=sys.stderr)
        for error in errors:
            print(f"  - {_bounded_text(error)}", file=sys.stderr)
        return 2
    if args.dry_run:
        preview_session = args.session_id
        print("OK: strict client configurations and credential paths validated")
        print(f"  endpoint: {_bounded_text(args.endpoint)}")
        print(f"  realm:    {_bounded_text(args.realm)}")
        print(f"  session:  {_bounded_text(preview_session)}")
        for case in _probe_plan(args.realm, preview_session):
            verdict = "DELIVERED" if case.expect_delivery else "NOT_DELIVERED"
            receivers = (
                f" to {','.join(case.required_receivers)}"
                if case.required_receivers
                else ""
            )
            print(
                f"  {case.step}. {case.actor} {case.operation.upper()} -> "
                f"{case.plane}{receivers}: "
                f"expect {verdict}"
            )
        first_rpc = len(_probe_plan(args.realm, preview_session)) + 1
        print(f"  {first_rpc}. commander -> body RPC -> commander reply: expect DELIVERED")
        print(f"  {first_rpc + 1}. observer -> RPC query: expect NOT_DELIVERED")
        print(f"  {first_rpc + 2}. body -> RPC query: expect NOT_DELIVERED")
        print(f"  {first_rpc + 3}. observer queryable/reply: expect NOT_REACHED")
        print(f"  {first_rpc + 4}. commander queryable/reply: expect NOT_REACHED")
        print(f"  {first_rpc + 5}. no-client-cert: expect NO_ROUTER_CONNECTION")
        return 0
    return run_live(args, specs)


if __name__ == "__main__":
    raise SystemExit(main())
