#!/usr/bin/env python3
"""Fail-closed NCP 1.0 deployment-profile configuration validator.

Structural validation is always applied. A production profile additionally captures
bounded regular, non-symlinked certificate/key files through no-follow descriptors,
checks private-key ownership and permissions, and performs every certificate/key
check against owner-only snapshots of those exact bytes. The retained mutable key
buffer is overwritten after capture, and credentials are never written to a report.

Passing this validator does not provide the transport callback's authenticated
peer principal or bind it to ``IdentityClaim``. The current ``ncp-zenoh`` secure
open path fails closed on that separate implementation prerequisite.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import ipaddress
import json
import math
import os
import shutil
import ssl
import stat
import struct
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEV = "dev-loopback-insecure"
PROD = "production-secure"
PLANES = {"control", "perception", "action", "observation"}
ROLES = {"commander", "body", "observer", "operator"}
SECURITY_STATE_DIGEST_DOMAIN_V1 = b"ncp.security-state-digest.v1\0"
MAX_PROFILE_PROJECTION_BYTES = 2_097_152
MAX_PROJECTION_DEPTH = 32
MAX_FINITE_NUMBER_MAGNITUDE = 1e300
MAX_DEPLOYMENT_PROFILE_BYTES = 1_048_576
MAX_CA_CERT_BYTES = 1_048_576
MAX_PEER_CERT_BYTES = 262_144
MAX_PRIVATE_KEY_BYTES = 262_144
MAX_OPENSSL_OUTPUT_BYTES = 16_384
READ_CHUNK_BYTES = 65_536


class ProfileError(ValueError):
    pass


def _check_keys(
    value: dict[str, Any],
    *,
    required: set[str],
    optional: set[str] = frozenset(),
    field: str,
) -> None:
    keys = set(value)
    missing = required - keys
    unknown = keys - required - optional
    if missing or unknown:
        raise ProfileError(
            f"{field} members are not exact: missing={sorted(missing)}, "
            f"unknown={sorted(unknown)}"
        )


def _object_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ProfileError(f"NCP-LIMIT-007: duplicate JSON key {key!r}")
        result[key] = value
    return result


def _parse_int_preserve_negative_zero(token: str) -> int | float:
    """Preserve the JSON lexical token ``-0`` as IEEE-754 negative zero."""
    return -0.0 if token == "-0" else int(token, 10)


def load(path: Path) -> dict[str, Any]:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0)
    descriptor: int | None = None
    try:
        descriptor = os.open(path, flags)
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ProfileError("deployment profile must be a regular file")
        if before.st_size > MAX_DEPLOYMENT_PROFILE_BYTES:
            raise ProfileError(
                f"deployment profile exceeds {MAX_DEPLOYMENT_PROFILE_BYTES} bytes"
            )
        payload = bytearray()
        while True:
            remaining = MAX_DEPLOYMENT_PROFILE_BYTES + 1 - len(payload)
            if remaining <= 0:
                raise ProfileError(
                    f"deployment profile exceeds {MAX_DEPLOYMENT_PROFILE_BYTES} bytes"
                )
            chunk = os.read(descriptor, min(READ_CHUNK_BYTES, remaining))
            if not chunk:
                break
            payload.extend(chunk)
            if len(payload) > MAX_DEPLOYMENT_PROFILE_BYTES:
                raise ProfileError(
                    f"deployment profile exceeds {MAX_DEPLOYMENT_PROFILE_BYTES} bytes"
                )
        after = os.fstat(descriptor)
        if (
            _stat_signature(after) != _stat_signature(before)
            or len(payload) != before.st_size
        ):
            raise ProfileError("deployment profile changed while it was being captured")
        value = json.loads(
            bytes(payload).decode("utf-8", errors="strict"),
            object_pairs_hook=_object_no_duplicates,
            parse_int=_parse_int_preserve_negative_zero,
            parse_constant=lambda token: (_ for _ in ()).throw(
                ProfileError(f"non-finite JSON constant {token}")
            ),
        )
    except ProfileError:
        raise
    except (OSError, RecursionError, UnicodeError, json.JSONDecodeError) as error:
        raise ProfileError(f"cannot read deployment profile: {error}") from error
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError as error:
                raise ProfileError("deployment profile descriptor could not be closed") from error
    if not isinstance(value, dict):
        raise ProfileError("deployment profile must be one JSON object")
    return value


def _clean_id(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ProfileError(f"{field} must be a non-empty string of at most 128 UTF-8 bytes")
    try:
        encoded = value.encode("utf-8", errors="strict")
    except UnicodeEncodeError as error:
        raise ProfileError(f"{field} contains invalid Unicode") from error
    if len(encoded) > 128:
        raise ProfileError(f"{field} must be a non-empty string of at most 128 UTF-8 bytes")
    if any(
        character.isspace()
        or ord(character) < 32
        or 127 <= ord(character) <= 159
        or character in "/*$#?\ufeff"
        for character in value
    ):
        raise ProfileError(f"{field} contains whitespace, a control, separator, or wildcard")
    return value


def _absolute_path(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise ProfileError(f"{field} must be an absolute path string")
    try:
        encoded = value.encode("utf-8", errors="strict")
    except UnicodeEncodeError as error:
        raise ProfileError(f"{field} contains invalid Unicode") from error
    if not encoded or len(encoded) > 4096 or "\0" in value or not Path(value).is_absolute():
        raise ProfileError(f"{field} must be an absolute path string")
    return value


def _authority(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("default_deny") is not True:
        raise ProfileError("authority must be an object with default_deny=true")
    _check_keys(
        value,
        required={"realm", "default_deny", "principals"},
        field="authority",
    )
    realm = value.get("realm")
    if isinstance(realm, str):
        try:
            realm.encode("utf-8", errors="strict")
        except UnicodeEncodeError as error:
            raise ProfileError("authority.realm contains invalid Unicode") from error
    if not isinstance(realm, str) or not realm or any(
        not segment
        or any(
            character in "/*$#?\ufeff"
            or character.isspace()
            or ord(character) < 32
            or 127 <= ord(character) <= 159
            for character in segment
        )
        for segment in realm.split("/")
    ):
        raise ProfileError("authority.realm is invalid")
    principals = value.get("principals")
    if not isinstance(principals, list) or not principals:
        raise ProfileError("authority.principals must be a non-empty array")
    principal_ids: set[str] = set()
    cert_ids: set[str] = set()
    for index, grant in enumerate(principals):
        if not isinstance(grant, dict):
            raise ProfileError(f"authority.principals[{index}] must be an object")
        _check_keys(
            grant,
            required={
                "principal_id",
                "certificate_identity",
                "entity_id",
                "role",
                "planes",
            },
            optional={"may_reset_estop", "may_override"},
            field=f"authority.principals[{index}]",
        )
        principal = _clean_id(grant.get("principal_id"), f"principals[{index}].principal_id")
        cert_id = _clean_id(
            grant.get("certificate_identity"), f"principals[{index}].certificate_identity"
        )
        _clean_id(grant.get("entity_id"), f"principals[{index}].entity_id")
        if principal in principal_ids or cert_id in cert_ids:
            raise ProfileError("principal_id and certificate_identity mappings must be one-to-one")
        principal_ids.add(principal)
        cert_ids.add(cert_id)
        role = grant.get("role")
        if role not in ROLES:
            raise ProfileError(f"principals[{index}].role is not registered")
        planes = grant.get("planes")
        if not isinstance(planes, list) or not planes or len(set(planes)) != len(planes):
            raise ProfileError(f"principals[{index}].planes must be unique and non-empty")
        if not set(planes) <= PLANES:
            raise ProfileError(f"principals[{index}].planes contains an unknown plane")
        if "action" in planes and role not in {"commander", "operator"}:
            raise ProfileError("only commander/operator principals may publish action")
        if grant.get("may_reset_estop", False) is True and role != "operator":
            raise ProfileError("only an operator principal may reset ESTOP")
        if grant.get("may_override", False) is True and role != "operator":
            raise ProfileError("only an operator principal may override authority")
        if not isinstance(grant.get("may_reset_estop", False), bool) or not isinstance(
            grant.get("may_override", False), bool
        ):
            raise ProfileError("operator authority flags must be booleans")
    return value


def _endpoint(value: Any, profile: str) -> None:
    if not isinstance(value, dict):
        raise ProfileError("bind must be an object")
    kind = value.get("kind")
    if kind == "tcp":
        _check_keys(value, required={"kind", "host", "port"}, field="bind")
        host, port = value.get("host"), value.get("port")
        if not isinstance(host, str) or not isinstance(port, int) or isinstance(port, bool):
            raise ProfileError("TCP bind requires string host and integer port")
        try:
            host_bytes = host.encode("utf-8", errors="strict")
        except UnicodeEncodeError as error:
            raise ProfileError("TCP bind host contains invalid Unicode") from error
        if not host_bytes or len(host_bytes) > 253 or any(
            character.isspace()
            or ord(character) < 32
            or 127 <= ord(character) <= 159
            for character in host
        ):
            raise ProfileError("TCP bind host is empty, oversized, or contains controls")
        if not (1 <= port <= 65535):
            raise ProfileError("TCP bind port is outside 1..65535")
        if profile == DEV:
            try:
                address = ipaddress.ip_address(host)
                loopback = (
                    isinstance(address, ipaddress.IPv4Address)
                    and address.packed[0] == 127
                ) or (
                    isinstance(address, ipaddress.IPv6Address)
                    and address.scope_id is None
                    and address == ipaddress.IPv6Address("::1")
                )
            except ValueError:
                loopback = False
            if not loopback:
                raise ProfileError("dev-loopback-insecure cannot bind a non-loopback address")
    elif kind == "unix":
        _check_keys(value, required={"kind", "path"}, field="bind")
        _absolute_path(value.get("path"), "UDS bind path")
    else:
        raise ProfileError("bind.kind must be tcp or unix")


def structural(config: dict[str, Any]) -> None:
    _check_keys(
        config,
        required={
            "profile",
            "bind",
            "authority",
            "tls",
            "allow_downgrade",
            "insecure_status",
        },
        field="deployment profile",
    )
    profile = config.get("profile")
    if profile not in {DEV, PROD}:
        raise ProfileError("profile must be dev-loopback-insecure or production-secure")
    if config.get("allow_downgrade") is not False:
        raise ProfileError("allow_downgrade must be explicitly false")
    _endpoint(config.get("bind"), profile)
    _authority(config.get("authority"))
    tls = config.get("tls")
    if profile == DEV:
        if tls is not None:
            raise ProfileError("dev-loopback-insecure must not carry partial TLS configuration")
        if config.get("insecure_status") is not True:
            raise ProfileError("dev-loopback-insecure must emit insecure_status=true")
    else:
        if config.get("insecure_status") is not False:
            raise ProfileError("production-secure must emit insecure_status=false")
        if not isinstance(tls, dict) or set(tls) != {"ca_cert", "peer_cert", "private_key"}:
            raise ProfileError("production-secure requires exactly ca_cert, peer_cert, private_key")
        for name, path in tls.items():
            _absolute_path(path, f"tls.{name}")


@dataclass
class _CapturedCredential:
    label: str
    info: os.stat_result
    payload: bytearray

    def wipe(self) -> None:
        self.payload[:] = b"\0" * len(self.payload)


@dataclass(frozen=True)
class _CredentialSnapshots:
    ca: Path
    peer: Path
    key: Path


def _stat_signature(info: os.stat_result) -> tuple[int, ...]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_uid,
        info.st_gid,
        info.st_nlink,
        info.st_size,
        getattr(info, "st_mtime_ns", int(info.st_mtime * 1_000_000_000)),
        getattr(info, "st_ctime_ns", int(info.st_ctime * 1_000_000_000)),
    )


def _validate_private_key_metadata(
    info: os.stat_result, *, effective_uid: int | None = None
) -> None:
    if effective_uid is None:
        get_effective_uid = getattr(os, "geteuid", None)
        if get_effective_uid is None:
            raise ProfileError(
                "production-secure private-key ownership requires POSIX effective-UID support"
            )
        effective_uid = get_effective_uid()
    if info.st_uid != effective_uid:
        raise ProfileError("private key must be owned by the effective process user")
    mode = stat.S_IMODE(info.st_mode)
    if not mode & stat.S_IRUSR:
        raise ProfileError("private key must be readable by its owner")
    if mode & (stat.S_IRWXG | stat.S_IRWXO):
        raise ProfileError("private key must not be accessible by group or other")
    if mode & (stat.S_IXUSR | stat.S_ISUID | stat.S_ISGID | stat.S_ISVTX):
        raise ProfileError("private key must not be executable or carry special mode bits")


def _capture_regular(
    path: Path,
    label: str,
    maximum_bytes: int,
    *,
    private_key: bool = False,
) -> _CapturedCredential:
    no_follow = getattr(os, "O_NOFOLLOW", None)
    if no_follow is None:
        raise ProfileError(
            "production-secure credential capture requires O_NOFOLLOW support"
        )
    flags = os.O_RDONLY | no_follow
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(path, flags)
    except (OSError, ValueError) as error:
        raise ProfileError(f"{label} cannot be opened safely: {error}") from error

    payload = bytearray()
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ProfileError(f"{label} must be one non-symlinked regular file")
        if before.st_size <= 0:
            raise ProfileError(f"{label} must not be empty")
        if before.st_size > maximum_bytes:
            raise ProfileError(f"{label} exceeds its {maximum_bytes}-byte limit")
        if private_key:
            _validate_private_key_metadata(before)

        while True:
            remaining = maximum_bytes + 1 - len(payload)
            if remaining <= 0:
                raise ProfileError(f"{label} exceeds its {maximum_bytes}-byte limit")
            chunk = os.read(descriptor, min(READ_CHUNK_BYTES, remaining))
            if not chunk:
                break
            payload.extend(chunk)
            if len(payload) > maximum_bytes:
                raise ProfileError(f"{label} exceeds its {maximum_bytes}-byte limit")

        after = os.fstat(descriptor)
        if _stat_signature(after) != _stat_signature(before) or len(payload) != before.st_size:
            raise ProfileError(f"{label} changed while it was being captured")
        return _CapturedCredential(label=label, info=before, payload=payload)
    except ProfileError:
        payload[:] = b"\0" * len(payload)
        raise
    except (OSError, OverflowError, ValueError) as error:
        payload[:] = b"\0" * len(payload)
        raise ProfileError(f"{label} could not be captured safely") from error
    finally:
        try:
            os.close(descriptor)
        except OSError as error:
            payload[:] = b"\0" * len(payload)
            raise ProfileError(f"{label} descriptor could not be closed safely") from error


def _require_single_pem_block(
    payload: bytearray, label: str, block_label: bytes
) -> None:
    begin = b"-----BEGIN " + block_label + b"-----"
    end = b"-----END " + block_label + b"-----"
    if payload.count(begin) != 1 or payload.count(end) != 1:
        raise ProfileError(f"{label} must contain exactly one {block_label.decode()} PEM block")
    start = payload.find(begin)
    finish = payload.find(end, start + len(begin))
    if finish < 0:
        raise ProfileError(f"{label} has an incomplete PEM block")
    if payload[:start].strip() or payload[finish + len(end) :].strip():
        raise ProfileError(f"{label} must not contain data outside its PEM block")
    if not payload[start + len(begin) : finish].strip():
        raise ProfileError(f"{label} PEM body must not be empty")


def _require_private_key_pem(payload: bytearray) -> None:
    allowed = (b"PRIVATE KEY", b"RSA PRIVATE KEY", b"EC PRIVATE KEY")
    present = [
        block_label
        for block_label in allowed
        if b"-----BEGIN " + block_label + b"-----" in payload
    ]
    if len(present) != 1 or b"-----BEGIN ENCRYPTED PRIVATE KEY-----" in payload:
        raise ProfileError("private key must contain exactly one unencrypted PEM private key")
    _require_single_pem_block(payload, "private key", present[0])


def _write_snapshot(path: Path, payload: bytearray) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as error:
        raise ProfileError("cannot create owner-only credential snapshot") from error
    try:
        os.fchmod(descriptor, 0o600)
        view = memoryview(payload)
        offset = 0
        while offset < len(view):
            written = os.write(descriptor, view[offset:])
            if written <= 0:
                raise ProfileError("credential snapshot write made no progress")
            offset += written
    except ProfileError:
        try:
            path.unlink()
        except OSError:
            pass
        raise
    except (OSError, OverflowError, ValueError) as error:
        try:
            path.unlink()
        except OSError:
            pass
        raise ProfileError("cannot write owner-only credential snapshot") from error
    finally:
        try:
            os.close(descriptor)
        except OSError as error:
            raise ProfileError("cannot close owner-only credential snapshot") from error


def _snapshot_credentials(
    config: dict[str, Any], snapshot_root: Path
) -> _CredentialSnapshots:
    tls = config["tls"]
    captured: list[_CapturedCredential] = []
    try:
        ca = _capture_regular(
            Path(tls["ca_cert"]), "CA certificate", MAX_CA_CERT_BYTES
        )
        captured.append(ca)
        peer = _capture_regular(
            Path(tls["peer_cert"]), "peer certificate", MAX_PEER_CERT_BYTES
        )
        captured.append(peer)
        key = _capture_regular(
            Path(tls["private_key"]),
            "private key",
            MAX_PRIVATE_KEY_BYTES,
            private_key=True,
        )
        captured.append(key)

        identities = {(item.info.st_dev, item.info.st_ino) for item in captured}
        if len(identities) != len(captured):
            raise ProfileError(
                "CA certificate, peer certificate, and private key must be distinct files"
            )
        if ca.payload == peer.payload:
            raise ProfileError("CA certificate and peer certificate must be distinct")
        _require_single_pem_block(ca.payload, "CA certificate", b"CERTIFICATE")
        _require_single_pem_block(peer.payload, "peer certificate", b"CERTIFICATE")
        _require_private_key_pem(key.payload)

        try:
            os.chmod(snapshot_root, 0o700)
        except OSError as error:
            raise ProfileError("cannot protect the credential snapshot directory") from error
        snapshots = _CredentialSnapshots(
            ca=snapshot_root / "ca.pem",
            peer=snapshot_root / "peer.pem",
            key=snapshot_root / "peer.key",
        )
        _write_snapshot(snapshots.ca, ca.payload)
        _write_snapshot(snapshots.peer, peer.payload)
        _write_snapshot(snapshots.key, key.payload)
        return snapshots
    finally:
        for item in captured:
            item.wipe()


def _decode_certificate(path: Path, label: str) -> dict[str, Any]:
    try:
        return ssl._ssl._test_decode_cert(str(path))  # type: ignore[attr-defined]
    except (AttributeError, OSError, OverflowError, ssl.SSLError, ValueError) as error:
        raise ProfileError(f"{label} is not a readable X.509 certificate: {error}") from error


def _cert_identities(decoded: dict[str, Any]) -> set[str]:
    identities: set[str] = set()
    for kind, value in decoded.get("subjectAltName", []):
        if kind in {"URI", "DNS"} and isinstance(value, str):
            identities.add(value)
    return identities


def _check_certificate_validity(
    decoded: dict[str, Any], label: str, now: datetime
) -> None:
    for field, relation in (("notBefore", "before"), ("notAfter", "after")):
        text = decoded.get(field)
        if not isinstance(text, str):
            raise ProfileError(f"{label} has no {field}")
        try:
            moment = datetime.fromtimestamp(ssl.cert_time_to_seconds(text), UTC)
        except (OSError, OverflowError, ValueError) as error:
            raise ProfileError(f"{label} has an invalid {field}") from error
        if relation == "before" and now < moment:
            raise ProfileError(f"{label} is not valid yet")
        if relation == "after" and now >= moment:
            raise ProfileError(f"{label} is expired")


def _openssl_ok(openssl: str, arguments: list[str], failure: str) -> None:
    environment = os.environ.copy()
    environment["LANG"] = "C"
    environment["LC_ALL"] = "C"
    try:
        result = subprocess.run(
            [openssl, *arguments],
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ProfileError(f"{failure}: openssl could not complete safely") from error
    if result.returncode != 0:
        raise ProfileError(failure)


def _openssl_purposes(openssl: str, certificate: Path, label: str) -> dict[str, str]:
    environment = os.environ.copy()
    environment["LANG"] = "C"
    environment["LC_ALL"] = "C"
    try:
        result = subprocess.run(
            [openssl, "x509", "-in", str(certificate), "-noout", "-purpose"],
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ProfileError(f"cannot inspect {label} purposes safely") from error
    if result.returncode != 0 or len(result.stdout) > MAX_OPENSSL_OUTPUT_BYTES:
        raise ProfileError(f"cannot inspect {label} purposes safely")
    try:
        lines = result.stdout.decode("ascii", errors="strict").splitlines()
    except UnicodeDecodeError as error:
        raise ProfileError(f"{label} purpose output is not canonical ASCII") from error
    purposes: dict[str, str] = {}
    for line in lines:
        if " : " in line:
            name, value = line.split(" : ", 1)
            purposes[name.strip()] = value.strip()
    return purposes


def _verify_production_snapshots(
    authority: dict[str, Any], snapshots: _CredentialSnapshots, openssl: str
) -> None:
    ca_decoded = _decode_certificate(snapshots.ca, "CA certificate")
    peer_decoded = _decode_certificate(snapshots.peer, "peer certificate")
    now = datetime.now(UTC)
    _check_certificate_validity(ca_decoded, "CA certificate", now)
    _check_certificate_validity(peer_decoded, "peer certificate", now)

    ca_purposes = _openssl_purposes(openssl, snapshots.ca, "CA certificate")
    if any(
        ca_purposes.get(purpose) != "Yes"
        for purpose in ("SSL client CA", "SSL server CA")
    ):
        raise ProfileError("configured CA certificate is not a TLS certificate authority")
    peer_purposes = _openssl_purposes(openssl, snapshots.peer, "peer certificate")
    if any(
        peer_purposes.get(purpose) != expected
        for purpose, expected in (
            ("SSL client", "Yes"),
            ("SSL server", "Yes"),
            ("SSL client CA", "No"),
            ("SSL server CA", "No"),
        )
    ):
        raise ProfileError(
            "peer certificate must be a non-CA certificate usable for TLS client "
            "and server authentication"
        )

    enrolled = {
        grant["certificate_identity"] for grant in authority["principals"]
    }
    matching_identities = _cert_identities(peer_decoded) & enrolled
    if len(matching_identities) != 1:
        raise ProfileError(
            "peer certificate SAN must select exactly one enrolled authority principal"
        )

    _openssl_ok(
        openssl,
        ["pkey", "-in", str(snapshots.key), "-noout", "-check", "-passin", "pass:"],
        "private key is malformed, encrypted, or internally inconsistent",
    )
    _openssl_ok(
        openssl,
        [
            "verify",
            "-no-CAfile",
            "-no-CApath",
            "-no-CAstore",
            "-CAfile",
            str(snapshots.ca),
            "-partial_chain",
            "-x509_strict",
            "-check_ss_sig",
            str(snapshots.ca),
        ],
        "configured CA certificate fails strict self-signature verification",
    )
    for purpose in ("sslclient", "sslserver"):
        _openssl_ok(
            openssl,
            [
                "verify",
                "-no-CAfile",
                "-no-CApath",
                "-no-CAstore",
                "-CAfile",
                str(snapshots.ca),
                "-x509_strict",
                "-purpose",
                purpose,
                str(snapshots.peer),
            ],
            f"peer certificate does not verify for {purpose} against the configured CA",
        )

    try:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        context.load_cert_chain(
            certfile=str(snapshots.peer), keyfile=str(snapshots.key)
        )
    except (OSError, ssl.SSLError, ValueError) as error:
        raise ProfileError(
            "private key does not match the peer certificate or cannot be loaded safely"
        ) from error


def runtime(config: dict[str, Any]) -> None:
    structural(config)
    if config["profile"] != PROD:
        return

    openssl = shutil.which("openssl")
    if openssl is None:
        raise ProfileError("production-secure startup requires openssl certificate verification")
    try:
        with tempfile.TemporaryDirectory(prefix="ncp-credential-snapshot-") as tmp:
            snapshot_root = Path(tmp)
            snapshots = _snapshot_credentials(config, snapshot_root)
            _verify_production_snapshots(config["authority"], snapshots, openssl)
    except ProfileError:
        raise
    except OSError as error:
        raise ProfileError("cannot create or remove owner-only credential snapshots") from error


def digest(config: dict[str, Any]) -> str:
    structural(config)
    principals = []
    for grant in sorted(config["authority"]["principals"], key=lambda item: item["principal_id"]):
        principals.append(
            {
                "principal_id": grant["principal_id"],
                "certificate_identity": grant["certificate_identity"],
                "entity_id": grant["entity_id"],
                "role": grant["role"],
                "planes": sorted(grant["planes"]),
                "may_reset_estop": grant.get("may_reset_estop", False),
                "may_override": grant.get("may_override", False),
            }
        )
    projection = {
        "profile": config["profile"],
        "bind": config["bind"],
        "authority": {
            "realm": config["authority"]["realm"],
            "default_deny": config["authority"]["default_deny"],
            "principals": principals,
        },
        "tls": config["tls"],
        "allow_downgrade": config["allow_downgrade"],
        "insecure_status": config["insecure_status"],
    }
    return hashlib.sha256(_canonical_projection(SECURITY_STATE_DIGEST_DOMAIN_V1, projection)).hexdigest()


def _append(output: bytearray, payload: bytes) -> None:
    if len(output) + len(payload) > MAX_PROFILE_PROJECTION_BYTES:
        raise ProfileError("canonical projection exceeds its byte budget")
    output.extend(payload)


def _length(output: bytearray, value: int) -> None:
    if not 0 <= value <= (1 << 64) - 1:
        raise ProfileError("canonical length is not representable as u64")
    _append(output, value.to_bytes(8, "big"))


def _string(output: bytearray, value: str) -> None:
    try:
        encoded = value.encode("utf-8", errors="strict")
    except UnicodeEncodeError as error:
        raise ProfileError("canonical projection contains invalid Unicode") from error
    _append(output, b"\x04")
    _length(output, len(encoded))
    _append(output, encoded)


def _canonical_value(output: bytearray, value: Any, depth: int) -> None:
    if depth > MAX_PROJECTION_DEPTH:
        raise ProfileError("canonical projection exceeds its nesting-depth budget")
    if value is None:
        _append(output, b"\x00")
    elif value is False:
        _append(output, b"\x01")
    elif value is True:
        _append(output, b"\x02")
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            number = float(value)
        except OverflowError as error:
            raise ProfileError(
                "canonical projection contains an out-of-budget number"
            ) from error
        if not math.isfinite(number) or abs(number) > MAX_FINITE_NUMBER_MAGNITUDE:
            raise ProfileError("canonical projection contains an out-of-budget number")
        _append(output, b"\x03")
        _append(output, struct.pack(">d", number))
    elif isinstance(value, str):
        _string(output, value)
    elif isinstance(value, list):
        _append(output, b"\x05")
        _length(output, len(value))
        for item in value:
            _canonical_value(output, item, depth + 1)
    elif isinstance(value, dict):
        try:
            entries = sorted(value.items(), key=lambda item: item[0].encode("utf-8", errors="strict"))
        except (AttributeError, UnicodeEncodeError) as error:
            raise ProfileError("canonical object keys must be valid Unicode strings") from error
        _append(output, b"\x06")
        _length(output, len(entries))
        for key, item in entries:
            _string(output, key)
            _canonical_value(output, item, depth + 1)
    else:
        raise ProfileError(f"unsupported canonical projection type {type(value).__name__}")


def _canonical_projection(domain: bytes, value: Any) -> bytes:
    body = domain[:-1] if domain.endswith(b"\0") else b""
    if (
        not 1 <= len(body) <= 128
        or not body[0:1].isalnum()
        or not body[-1:].isalnum()
        or any(
            byte not in b"abcdefghijklmnopqrstuvwxyz0123456789.-" for byte in body
        )
    ):
        raise ProfileError(
            "canonical digest domain must be a bounded lowercase ASCII identifier "
            "followed by exactly one NUL"
        )
    output = bytearray()
    _append(output, domain)
    _canonical_value(output, value, 0)
    return bytes(output)


def _expect_profile_error(description: str, operation: Any) -> None:
    try:
        operation()
    except ProfileError:
        return
    raise AssertionError(f"hostile self-test accepted {description}")


def self_test() -> None:
    negative_zero = json.loads("-0", parse_int=_parse_int_preserve_negative_zero)
    if not isinstance(negative_zero, float) or math.copysign(1.0, negative_zero) != -1.0:
        raise AssertionError("lexical JSON -0 was not preserved as binary64 negative zero")
    dev = load(Path(__file__).resolve().parents[1] / "deploy/profiles/dev-loopback-insecure.json")
    structural(dev)
    assert len(digest(dev)) == 64
    hostile = json.loads(json.dumps(dev))
    hostile["bind"]["host"] = "0.0.0.0"
    try:
        structural(hostile)
    except ProfileError:
        pass
    else:
        raise AssertionError("non-loopback insecure profile was accepted")

    openssl = shutil.which("openssl")
    if openssl is None:
        raise ProfileError("self-test requires openssl")
    with tempfile.TemporaryDirectory(prefix="ncp-profile-test-") as tmp:
        root = Path(tmp)
        ca_key, ca_cert = root / "ca.key", root / "ca.pem"
        peer_key, peer_csr, peer_cert = root / "peer.key", root / "peer.csr", root / "peer.pem"
        other_key = root / "other.key"
        other_ca_key, other_ca_cert = root / "other-ca.key", root / "other-ca.pem"
        ca_config = root / "ca.cnf"
        ca_config.write_text(
            """[req]
prompt = no
distinguished_name = distinguished_name
x509_extensions = ca_extensions

[distinguished_name]
CN = NCP Test CA

[ca_extensions]
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid:always,issuer
basicConstraints = critical,CA:TRUE,pathlen:0
keyUsage = critical,keyCertSign,cRLSign
""",
            encoding="utf-8",
        )
        peer_extensions = root / "peer.cnf"
        peer_extensions.write_text(
            """[peer_extensions]
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid,issuer
basicConstraints = critical,CA:FALSE
keyUsage = critical,digitalSignature,keyEncipherment
extendedKeyUsage = clientAuth,serverAuth
subjectAltName = URI:urn:ncp:commander-1
""",
            encoding="utf-8",
        )
        commands = [
            [
                openssl,
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-days",
                "2",
                "-config",
                str(ca_config),
                "-keyout",
                str(ca_key),
                "-out",
                str(ca_cert),
            ],
            [
                openssl,
                "req",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-subj",
                "/CN=NCP Peer",
                "-keyout",
                str(peer_key),
                "-out",
                str(peer_csr),
            ],
            [
                openssl,
                "x509",
                "-req",
                "-in",
                str(peer_csr),
                "-CA",
                str(ca_cert),
                "-CAkey",
                str(ca_key),
                "-CAcreateserial",
                "-days",
                "2",
                "-extfile",
                str(peer_extensions),
                "-extensions",
                "peer_extensions",
                "-out",
                str(peer_cert),
            ],
            [
                openssl,
                "genpkey",
                "-algorithm",
                "EC",
                "-pkeyopt",
                "ec_paramgen_curve:P-256",
                "-out",
                str(other_key),
            ],
            [
                openssl,
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-days",
                "2",
                "-config",
                str(ca_config),
                "-subj",
                "/CN=NCP Other Test CA",
                "-keyout",
                str(other_ca_key),
                "-out",
                str(other_ca_cert),
            ],
        ]
        for command in commands:
            result = subprocess.run(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=30,
                check=False,
            )
            if result.returncode != 0:
                raise ProfileError("could not build ephemeral self-test certificate chain")
        for private_key in (ca_key, peer_key, other_key, other_ca_key):
            private_key.chmod(0o600)
        config = load(
            Path(__file__).resolve().parents[1]
            / "deploy/profiles/production-secure.template.json"
        )
        config["tls"] = {
            "ca_cert": str(ca_cert),
            "peer_cert": str(peer_cert),
            "private_key": str(peer_key),
        }
        runtime(config)

        peer_key.chmod(0o644)
        _expect_profile_error("a world-readable private key", lambda: runtime(config))
        peer_key.chmod(0o700)
        _expect_profile_error("an executable private key", lambda: runtime(config))
        peer_key.chmod(0o200)
        _expect_profile_error("an owner-unreadable private key", lambda: runtime(config))
        peer_key.chmod(0o4600)
        _expect_profile_error("a private key with special mode bits", lambda: runtime(config))
        peer_key.chmod(0o600)

        key_info = peer_key.stat()
        _expect_profile_error(
            "a private key owned by another user",
            lambda: _validate_private_key_metadata(
                key_info, effective_uid=key_info.st_uid + 1
            ),
        )

        symlink_key = root / "symlink.key"
        symlink_key.symlink_to(peer_key)
        symlink_config = json.loads(json.dumps(config))
        symlink_config["tls"]["private_key"] = str(symlink_key)
        _expect_profile_error(
            "a symlinked private key", lambda: runtime(symlink_config)
        )

        aliased_peer = root / "aliased-peer.pem"
        os.link(peer_key, aliased_peer)
        aliased_config = json.loads(json.dumps(config))
        aliased_config["tls"]["peer_cert"] = str(aliased_peer)
        _expect_profile_error(
            "credential roles sharing one inode", lambda: runtime(aliased_config)
        )

        oversized_key = root / "oversized.key"
        with oversized_key.open("wb") as output:
            output.truncate(MAX_PRIVATE_KEY_BYTES + 1)
        oversized_key.chmod(0o600)
        oversized_config = json.loads(json.dumps(config))
        oversized_config["tls"]["private_key"] = str(oversized_key)
        _expect_profile_error(
            "an oversized private key", lambda: runtime(oversized_config)
        )

        oversized_peer = root / "oversized-peer.pem"
        with oversized_peer.open("wb") as output:
            output.truncate(MAX_PEER_CERT_BYTES + 1)
        oversized_peer_config = json.loads(json.dumps(config))
        oversized_peer_config["tls"]["peer_cert"] = str(oversized_peer)
        _expect_profile_error(
            "an oversized peer certificate", lambda: runtime(oversized_peer_config)
        )

        oversized_ca = root / "oversized-ca.pem"
        with oversized_ca.open("wb") as output:
            output.truncate(MAX_CA_CERT_BYTES + 1)
        oversized_ca_config = json.loads(json.dumps(config))
        oversized_ca_config["tls"]["ca_cert"] = str(oversized_ca)
        _expect_profile_error(
            "an oversized CA certificate", lambda: runtime(oversized_ca_config)
        )

        empty_key = root / "empty.key"
        empty_key.touch(mode=0o600)
        empty_config = json.loads(json.dumps(config))
        empty_config["tls"]["private_key"] = str(empty_key)
        _expect_profile_error("an empty private key", lambda: runtime(empty_config))

        oversized_profile = root / "oversized-profile.json"
        with oversized_profile.open("wb") as output:
            output.truncate(MAX_DEPLOYMENT_PROFILE_BYTES + 1)
        _expect_profile_error(
            "an oversized deployment profile", lambda: load(oversized_profile)
        )

        if hasattr(os, "mkfifo"):
            profile_fifo = root / "profile.fifo"
            os.mkfifo(profile_fifo, 0o600)
            _expect_profile_error(
                "a deployment-profile FIFO", lambda: load(profile_fifo)
            )

            fifo = root / "credential.fifo"
            os.mkfifo(fifo, 0o600)
            _expect_profile_error(
                "a credential FIFO",
                lambda: _capture_regular(fifo, "hostile credential", 1024),
            )

        malformed_key = root / "malformed.key"
        malformed_key.write_bytes(
            b"-----BEGIN PRIVATE KEY-----\nnot-base64\n-----END PRIVATE KEY-----\n"
        )
        malformed_key.chmod(0o600)
        malformed_config = json.loads(json.dumps(config))
        malformed_config["tls"]["private_key"] = str(malformed_key)
        _expect_profile_error(
            "a malformed private key", lambda: runtime(malformed_config)
        )

        wrong_key_config = json.loads(json.dumps(config))
        wrong_key_config["tls"]["private_key"] = str(other_key)
        _expect_profile_error(
            "a private key for another certificate", lambda: runtime(wrong_key_config)
        )

        wrong_ca_config = json.loads(json.dumps(config))
        wrong_ca_config["tls"]["ca_cert"] = str(other_ca_cert)
        _expect_profile_error(
            "a leaf issued by another CA", lambda: runtime(wrong_ca_config)
        )

        ca_lines = ca_cert.read_bytes().splitlines()
        ca_der = bytearray(base64.b64decode(b"".join(ca_lines[1:-1]), validate=True))
        ca_der[-1] ^= 1
        corrupt_ca = root / "corrupt-ca.pem"
        corrupt_ca.write_bytes(
            b"-----BEGIN CERTIFICATE-----\n"
            + base64.encodebytes(ca_der)
            + b"-----END CERTIFICATE-----\n"
        )
        corrupt_ca_config = json.loads(json.dumps(config))
        corrupt_ca_config["tls"]["ca_cert"] = str(corrupt_ca)
        _expect_profile_error(
            "a CA certificate with a corrupt self-signature",
            lambda: runtime(corrupt_ca_config),
        )

        _expect_profile_error(
            "a leaf certificate used as a CA",
            lambda: _verify_production_snapshots(
                config["authority"],
                _CredentialSnapshots(
                    ca=peer_cert,
                    peer=peer_cert,
                    key=peer_key,
                ),
                openssl,
            ),
        )
        _expect_profile_error(
            "a CA certificate used as a leaf",
            lambda: _verify_production_snapshots(
                config["authority"],
                _CredentialSnapshots(
                    ca=ca_cert,
                    peer=ca_cert,
                    key=ca_key,
                ),
                openssl,
            ),
        )

        duplicate_cert = root / "duplicate-cert.pem"
        duplicate_cert.write_bytes(peer_cert.read_bytes() + peer_cert.read_bytes())
        duplicate_config = json.loads(json.dumps(config))
        duplicate_config["tls"]["peer_cert"] = str(duplicate_cert)
        _expect_profile_error(
            "multiple leaf certificate PEM blocks", lambda: runtime(duplicate_config)
        )

        mutable = root / "mutable-credential.bin"
        mutable.write_bytes(b"A" * (READ_CHUNK_BYTES * 2))
        real_read = os.read
        mutation_triggered = False

        def racing_read(descriptor: int, count: int) -> bytes:
            nonlocal mutation_triggered
            chunk = real_read(descriptor, count)
            if chunk and not mutation_triggered:
                mutation_triggered = True
                with mutable.open("r+b") as output:
                    output.seek(READ_CHUNK_BYTES)
                    output.write(b"Z")
                    output.flush()
                    os.fsync(output.fileno())
            return chunk

        os.read = racing_read
        try:
            _expect_profile_error(
                "a credential modified during capture",
                lambda: _capture_regular(
                    mutable, "mutable credential", MAX_PRIVATE_KEY_BYTES
                ),
            )
        finally:
            os.read = real_read
        if not mutation_triggered:
            raise AssertionError("credential mutation race self-test did not execute")

        race_root = root / "path-swap"
        race_root.mkdir()
        race_ca = race_root / "ca.pem"
        race_peer = race_root / "peer.pem"
        race_key = race_root / "peer.key"
        shutil.copyfile(ca_cert, race_ca)
        shutil.copyfile(peer_cert, race_peer)
        shutil.copyfile(peer_key, race_key)
        race_key.chmod(0o600)
        race_config = json.loads(json.dumps(config))
        race_config["tls"] = {
            "ca_cert": str(race_ca),
            "peer_cert": str(race_peer),
            "private_key": str(race_key),
        }
        snapshot_root = race_root / "snapshots"
        snapshot_root.mkdir()
        snapshots = _snapshot_credentials(race_config, snapshot_root)
        if stat.S_IMODE(snapshot_root.stat().st_mode) != 0o700 or any(
            stat.S_IMODE(path.stat().st_mode) != 0o600
            for path in (snapshots.ca, snapshots.peer, snapshots.key)
        ):
            raise AssertionError("credential snapshots are not owner-only")
        peer_replacement = race_root / "replacement-peer.pem"
        key_replacement = race_root / "replacement-key.pem"
        shutil.copyfile(ca_cert, peer_replacement)
        shutil.copyfile(other_key, key_replacement)
        key_replacement.chmod(0o600)
        os.replace(peer_replacement, race_peer)
        os.replace(key_replacement, race_key)
        _verify_production_snapshots(race_config["authority"], snapshots, openssl)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("profile", type=Path, nargs="?")
    parser.add_argument("--structural-only", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    arguments = parser.parse_args()
    try:
        if arguments.self_test:
            self_test()
            print("OK: deployment-profile structural and ephemeral-certificate self-test passed")
            return 0
        if arguments.profile is None:
            parser.error("profile is required unless --self-test is used")
        config = load(arguments.profile)
        if arguments.structural_only:
            structural(config)
        else:
            runtime(config)
        print(
            json.dumps(
                {
                    "profile": config["profile"],
                    "security_state_digest": digest(config),
                    "status": (
                        "insecure"
                        if config["profile"] == DEV
                        else "configuration_validated_only"
                    ),
                    "transport_identity_binding_available": False,
                },
                sort_keys=True,
            )
        )
        return 0
    except ProfileError as error:
        print(f"NCP-PROFILE-001: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
