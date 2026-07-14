#!/usr/bin/env python3
"""Probe a live Zenoh router's mTLS and per-plane key ACL enforcement.

The return value of ``session.put`` is not ACL evidence: a local Zenoh session can
accept a put even when the router drops it. This verifier therefore establishes an
authenticated observer subscription first, publishes a unique nonce for every
trial, and judges the router only by delivery acknowledgments:

* an allowed nonce MUST reach the observer;
* a denied nonce MUST remain unobserved; and
* every denied check requires a successful allowed baseline on the same plane.

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
    passed: bool
    detail: str

    def __str__(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        return (
            f"  [{status}] Step {self.step}: {self.description}\n"
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


def _wait_for_router(session: Any, timeout_s: float) -> bool:
    deadline = time.monotonic() + timeout_s
    while True:
        try:
            if _router_ids(session):
                return True
        except Exception:
            return False
        if time.monotonic() >= deadline:
            return False
        time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))


def _payload_bytes(sample: Any) -> bytes:
    payload = sample.payload
    try:
        return bytes(payload)
    except TypeError:
        return bytes(payload.to_bytes())


class DeliveryRecorder:
    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._deliveries: set[tuple[str, str, bytes]] = set()

    def callback(self, sample: Any) -> None:
        try:
            key_expr = sample.key_expr
            if callable(key_expr):
                key_expr = key_expr()
            key = str(key_expr)
            kind = getattr(sample, "kind", "put")
            if callable(kind):
                kind = kind()
            kind_name = getattr(kind, "name", None)
            kind_text = str(kind_name if kind_name is not None else kind).lower()
            operation = "delete" if "delete" in kind_text else "put"
            payload = b"" if operation == "delete" else _payload_bytes(sample)
        except Exception:
            return
        with self._condition:
            self._deliveries.add((operation, key, payload))
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


def _optional_payload_bytes(message: Any) -> bytes:
    payload = message.payload
    if callable(payload):
        payload = payload()
    if payload is None:
        return b""
    try:
        return bytes(payload)
    except TypeError:
        return bytes(payload.to_bytes())


class RpcRecorder:
    def __init__(self, key: str) -> None:
        self.key = key
        self._condition = threading.Condition()
        self._seen: set[bytes] = set()
        self._errors: list[str] = []

    @staticmethod
    def reply_payload(request_payload: bytes) -> bytes:
        return b"ncp-acl-rpc-reply:" + request_payload

    def callback(self, query: Any) -> None:
        try:
            request_payload = _optional_payload_bytes(query)
            query.reply(self.key, self.reply_payload(request_payload))
        except Exception as error:
            with self._condition:
                self._errors.append(str(error))
                self._condition.notify_all()
            return
        with self._condition:
            self._seen.add(request_payload)
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


def _rpc_replies(
    session: Any, key: str, request_payload: bytes, timeout_s: float
) -> tuple[list[bytes], list[str]]:
    payloads: list[bytes] = []
    errors: list[str] = []
    try:
        replies = session.get(key, timeout=timeout_s, payload=request_payload)
        for reply in replies:
            try:
                sample = reply.ok
                if callable(sample):
                    sample = sample()
                if sample is not None:
                    payloads.append(_optional_payload_bytes(sample))
            except Exception as error:
                errors.append(str(error))
    except Exception as error:
        errors.append(str(error))
    return payloads, errors


def _evaluate_delivery(
    *, expect_delivery: bool, observed: bool, plane_baseline_ok: bool
) -> tuple[bool, str]:
    if expect_delivery:
        return observed, "nonce delivery acknowledged" if observed else "allowed nonce was not observed"
    if not plane_baseline_ok:
        return False, "denial is inconclusive because this plane has no allowed delivery baseline"
    return (not observed), (
        "nonce remained unobserved after the denial window"
        if not observed
        else "forbidden nonce reached the observer"
    )


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
        ProbeCase(4, ROLE_BODY, PLANE_COMMAND, command, "put", False),
        ProbeCase(5, ROLE_OBSERVER, PLANE_COMMAND, command, "put", False),
        ProbeCase(6, ROLE_COMMANDER, PLANE_SENSOR, sensor, "put", False),
        ProbeCase(7, ROLE_OBSERVER, PLANE_SENSOR, sensor, "put", False),
        ProbeCase(8, ROLE_COMMANDER, PLANE_OBSERVATION, observation, "put", False),
        ProbeCase(9, ROLE_OBSERVER, PLANE_OBSERVATION, observation, "put", False),
        ProbeCase(10, ROLE_COMMANDER, PLANE_COMMAND, command, "delete", False),
        ProbeCase(11, ROLE_BODY, PLANE_SENSOR, sensor, "delete", False),
        ProbeCase(12, ROLE_BODY, PLANE_OBSERVATION, observation, "delete", False),
        ProbeCase(
            13,
            ROLE_COMMANDER,
            PLANE_COMMAND,
            f"{realm}/session/*/command",
            "put",
            False,
        ),
        ProbeCase(
            14,
            ROLE_COMMANDER,
            PLANE_COMMAND,
            f"{realm}/session/{session_id}/command/*",
            "put",
            False,
        ),
        ProbeCase(
            15,
            ROLE_COMMANDER,
            PLANE_COMMAND,
            f"{realm}/session/{session_id}/command/forbidden/deep",
            "put",
            False,
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
) -> CheckResult:
    session = None
    try:
        session = zenoh.open(_to_zenoh_config(zenoh, spec))
    except Exception as error:
        return CheckResult(
            step,
            "client with no certificate cannot establish mTLS",
            "NO_ROUTER_CONNECTION",
            "OPEN_REJECTED",
            True,
            f"transport rejected the no-certificate client: {error}",
        )
    try:
        connected = _wait_for_router(session, timeout_s)
        return CheckResult(
            step,
            "client with no certificate cannot establish mTLS",
            "NO_ROUTER_CONNECTION",
            "ROUTER_CONNECTED" if connected else "NO_ROUTER_CONNECTION",
            not connected,
            "no authenticated router link appeared during the rejection window"
            if not connected
            else "router accepted a client that presented no certificate",
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
    denied_deliveries: list[tuple[int, str, str, bytes]] = []
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
                    f"FAIL: {role} client did not establish an authenticated router link",
                    file=sys.stderr,
                )
                return 1

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

        plane_baselines: dict[str, bool] = {}
        for case in plan:
            payload = (
                f"ncp-acl-proof:{run_nonce}:{case.step}:{secrets.token_hex(16)}"
            ).encode("ascii")
            operation_detail = f"local {case.operation} accepted"
            actor_connected = bool(_router_ids(sessions[case.actor]))
            required_links = set(case.required_receivers) | {
                RECEIVER_OBSERVER_FLEET if not case.expect_delivery else case.actor
            }
            try:
                receivers_connected = all(
                    bool(_router_ids(sessions[role])) for role in required_links
                )
                if not actor_connected or not receivers_connected:
                    raise RuntimeError("actor or required receiver lost its router link")
                if case.operation == "put":
                    sessions[case.actor].put(case.key, payload)
                elif case.operation == "delete":
                    sessions[case.actor].delete(case.key)
                else:  # pragma: no cover - frozen probe-plan invariant
                    raise AssertionError(f"unsupported probe operation {case.operation!r}")
            except Exception as error:
                operation_detail = f"local {case.operation} raised: {error}"
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
                observed = recorders[RECEIVER_OBSERVER_FLEET].wait(
                    case.operation, case.key, payload, args.timeout
                )
                delivery_detail = "forbidden separate fleet-observer delivery check"
            passed, detail = _evaluate_delivery(
                expect_delivery=case.expect_delivery,
                observed=observed,
                plane_baseline_ok=plane_baselines.get(case.plane, False),
            )
            try:
                links_intact = bool(_router_ids(sessions[case.actor])) and all(
                    bool(_router_ids(sessions[role])) for role in required_links
                )
            except Exception:
                links_intact = False
            if not links_intact:
                passed = False
                detail = "actor or observer lost its authenticated router link during the probe"
            if case.expect_delivery:
                plane_baselines[case.plane] = passed
            else:
                denied_deliveries.append(
                    (len(results), case.operation, case.key, payload)
                )
            results.append(
                CheckResult(
                    case.step,
                    f"{case.actor} {case.operation.upper()} on {case.plane} plane",
                    "DELIVERED" if case.expect_delivery else "NOT_DELIVERED",
                    "DELIVERED" if observed else "NOT_DELIVERED",
                    passed,
                    f"{detail}; {delivery_detail}; {operation_detail}",
                )
            )

        # One final rejection window catches a forbidden sample that arrived just
        # after its per-case timeout. Nonces are unique, so no legitimate traffic
        # can satisfy this check accidentally.
        time.sleep(args.timeout)
        for result_index, operation, key, payload in denied_deliveries:
            if recorders[RECEIVER_OBSERVER_FLEET].contains(
                operation, key, payload
            ):
                previous = results[result_index]
                results[result_index] = CheckResult(
                    previous.step,
                    previous.description,
                    previous.expected,
                    "DELIVERED",
                    False,
                    "forbidden nonce arrived during the final rejection quarantine",
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
        positive_replies, positive_errors = _rpc_replies(
            sessions[ROLE_COMMANDER], rpc_key, rpc_positive, args.timeout
        )
        positive_seen = rpc_recorder.wait_seen(rpc_positive, args.timeout)
        expected_reply = RpcRecorder.reply_payload(rpc_positive)
        positive_ok = (
            positive_seen
            and expected_reply in positive_replies
            and not positive_errors
            and not rpc_recorder.errors()
        )
        results.append(
            CheckResult(
                len(plan) + 1,
                "commander query reaches body queryable and body reply returns",
                "QUERY_AND_REPLY_DELIVERED",
                "QUERY_AND_REPLY_DELIVERED" if positive_ok else "RPC_INCOMPLETE",
                positive_ok,
                "body query observed="
                f"{positive_seen}; replies={len(positive_replies)}; "
                f"client_errors={positive_errors}; server_errors={rpc_recorder.errors()}",
            )
        )

        observer_query = f"ncp-acl-rpc:{run_nonce}:observer-query".encode("ascii")
        observer_replies, observer_errors = _rpc_replies(
            sessions[ROLE_OBSERVER], rpc_key, observer_query, args.timeout
        )
        time.sleep(args.timeout)
        observer_seen = rpc_recorder.contains(observer_query)
        observer_ok = positive_ok and not observer_seen and not observer_replies
        results.append(
            CheckResult(
                len(plan) + 2,
                "observer cannot issue lifecycle RPC query",
                "QUERY_NOT_DELIVERED",
                "QUERY_DELIVERED" if observer_seen else "QUERY_NOT_DELIVERED",
                observer_ok,
                "positive RPC baseline="
                f"{positive_ok}; replies={len(observer_replies)}; "
                f"client_errors={observer_errors}",
            )
        )

        body_query = f"ncp-acl-rpc:{run_nonce}:body-query".encode("ascii")
        body_replies, body_errors = _rpc_replies(
            sessions[ROLE_BODY_QUERY], rpc_key, body_query, args.timeout
        )
        time.sleep(args.timeout)
        body_seen = rpc_recorder.contains(body_query)
        body_query_ok = positive_ok and not body_seen and not body_replies
        results.append(
            CheckResult(
                len(plan) + 3,
                "body cannot issue lifecycle RPC query",
                "QUERY_NOT_DELIVERED",
                "QUERY_DELIVERED" if body_seen else "QUERY_NOT_DELIVERED",
                body_query_ok,
                f"positive RPC baseline={positive_ok}; replies={len(body_replies)}; "
                f"client_errors={body_errors}",
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
            declaration_detail = "local declaration accepted"
            try:
                unauthorized_handle = sessions[role].declare_queryable(
                    rpc_key, unauthorized.callback
                )
                subscribers.append(unauthorized_handle)
            except Exception as error:
                declaration_detail = f"local declaration rejected: {error}"
            if args.settle:
                time.sleep(args.settle)
            probe = f"ncp-acl-rpc:{run_nonce}:{role}-queryable".encode("ascii")
            replies, query_errors = _rpc_replies(
                sessions[ROLE_COMMANDER], rpc_key, probe, args.timeout
            )
            body_observed = rpc_recorder.wait_seen(probe, args.timeout)
            unauthorized_observed = unauthorized.contains(probe)
            expected_body_reply = RpcRecorder.reply_payload(probe)
            queryable_ok = (
                body_observed
                and expected_body_reply in replies
                and not unauthorized_observed
                and not unauthorized.errors()
            )
            results.append(
                CheckResult(
                    len(plan) + offset,
                    description,
                    "UNAUTHORIZED_QUERYABLE_NOT_REACHED",
                    "UNAUTHORIZED_QUERYABLE_REACHED"
                    if unauthorized_observed
                    else "UNAUTHORIZED_QUERYABLE_NOT_REACHED",
                    queryable_ok,
                    f"body baseline observed={body_observed}; replies={len(replies)}; "
                    f"client_errors={query_errors}; "
                    f"unauthorized_errors={unauthorized.errors()}; "
                    f"{declaration_detail}",
                )
            )
            if unauthorized_handle is not None:
                _close(unauthorized_handle)

        results.append(
            _verify_no_certificate(zenoh, specs["no-cert"], args.timeout, len(plan) + 6)
        )
    except Exception as error:
        print(f"FAIL: live verification could not complete: {error}", file=sys.stderr)
        return 1
    finally:
        for subscriber in reversed(subscribers):
            _close(subscriber)
        for session in sessions.values():
            _close(session)

    print("Zenoh router ACL prerequisite (nonce delivery proof)")
    print(f"  endpoint: {args.endpoint}")
    print(f"  realm:    {args.realm}")
    print(f"  session:  {session_id} (exact pre-rendered quarantine namespace)")
    print()
    for result in results:
        print(result)
    print()
    if all(result.passed for result in results):
        print(
            "RESULT: ROUTER-ONLY PRECHECK PASSED — broad-selector data and "
            "protocol-closed RPC deliveries were observed, denied PUT/DELETE/"
            "wildcard/RPC deliveries were absent, and "
            "no-cert mTLS failed. NCP "
            "production-secure remains blocked until transport-authenticated peer "
            "identity is bound to IdentityClaim."
        )
        return 0
    failed = sum(not result.passed for result in results)
    print(f"RESULT: {failed} of {len(results)} invariants FAILED — deployment is NOT validated.")
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

    # Delivery truth table: a local put is irrelevant; only observer receipt counts,
    # and a denied result without a proven same-plane baseline is inconclusive.
    truth_cases = [
        (True, True, False, True),
        (True, False, False, False),
        (False, False, True, True),
        (False, True, True, False),
        (False, False, False, False),
    ]
    for expect, observed, baseline, wanted in truth_cases:
        got, _ = _evaluate_delivery(
            expect_delivery=expect,
            observed=observed,
            plane_baseline_ok=baseline,
        )
        if got != wanted:
            failures.append(
                "delivery evaluator accepted an unsafe truth-table case: "
                f"expect={expect} observed={observed} baseline={baseline}"
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
        wanted = expected_receivers.get(case.plane, ()) if case.expect_delivery else ()
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
                print(f"  - {failure}", file=sys.stderr)
            return 1
        print("OK: ACL deployment verifier offline self-test passed")
        return 0

    specs, errors = _validate_live_args(args)
    if errors:
        print("ERROR: invalid live verification configuration:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 2
    if args.dry_run:
        preview_session = args.session_id
        print("OK: strict client configurations and credential paths validated")
        print(f"  endpoint: {args.endpoint}")
        print(f"  realm:    {args.realm}")
        print(f"  session:  {preview_session}")
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
