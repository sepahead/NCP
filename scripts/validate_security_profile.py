#!/usr/bin/env python3
"""Fail-closed NCP 1.0 deployment-profile configuration validator.

Structural validation is always applied. A production profile additionally opens
the exact regular, non-symlinked certificate/key files, checks private-key owner
permissions, certificate validity, certificate identity enrollment, and verifies
the leaf against the configured CA using the local OpenSSL executable. It never
reads key bytes into Python or writes credentials to a report.

Passing this validator does not provide the transport callback's authenticated
peer principal or bind it to ``IdentityClaim``. The current ``ncp-zenoh`` secure
open path fails closed on that separate implementation prerequisite.
"""

from __future__ import annotations

import argparse
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
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_object_no_duplicates,
            parse_int=_parse_int_preserve_negative_zero,
            parse_constant=lambda token: (_ for _ in ()).throw(
                ProfileError(f"non-finite JSON constant {token}")
            ),
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ProfileError(f"cannot read deployment profile: {error}") from error
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
        value.encode("utf-8", errors="strict")
    except UnicodeEncodeError as error:
        raise ProfileError(f"{field} contains invalid Unicode") from error
    if not Path(value).is_absolute():
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


def _safe_regular(path: Path, label: str) -> os.stat_result:
    try:
        info = path.lstat()
    except OSError as error:
        raise ProfileError(f"{label} cannot be opened: {error}") from error
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise ProfileError(f"{label} must be one non-symlinked regular file")
    return info


def _decode_certificate(path: Path, label: str) -> dict[str, Any]:
    try:
        return ssl._ssl._test_decode_cert(str(path))  # type: ignore[attr-defined]
    except (OSError, ssl.SSLError, ValueError) as error:
        raise ProfileError(f"{label} is not a readable X.509 certificate: {error}") from error


def _cert_identities(decoded: dict[str, Any]) -> set[str]:
    identities: set[str] = set()
    for kind, value in decoded.get("subjectAltName", []):
        if kind in {"URI", "DNS"} and isinstance(value, str):
            identities.add(value)
    return identities


def runtime(config: dict[str, Any]) -> None:
    structural(config)
    if config["profile"] != PROD:
        return
    tls = config["tls"]
    ca, peer, key = (Path(tls[name]) for name in ("ca_cert", "peer_cert", "private_key"))
    _safe_regular(ca, "CA certificate")
    _safe_regular(peer, "peer certificate")
    key_info = _safe_regular(key, "private key")
    if key_info.st_mode & (stat.S_IRWXG | stat.S_IRWXO):
        raise ProfileError("private key must not be accessible by group or other")

    now = datetime.now(UTC)
    for path, label in ((ca, "CA certificate"), (peer, "peer certificate")):
        decoded = _decode_certificate(path, label)
        for field, relation in (("notBefore", "before"), ("notAfter", "after")):
            text = decoded.get(field)
            if not isinstance(text, str):
                raise ProfileError(f"{label} has no {field}")
            moment = datetime.fromtimestamp(ssl.cert_time_to_seconds(text), UTC)
            if relation == "before" and now < moment:
                raise ProfileError(f"{label} is not valid yet")
            if relation == "after" and now >= moment:
                raise ProfileError(f"{label} is expired")

    enrolled = {
        grant["certificate_identity"] for grant in config["authority"]["principals"]
    }
    if not (_cert_identities(_decode_certificate(peer, "peer certificate")) & enrolled):
        raise ProfileError("peer certificate SAN is not enrolled in authority.principals")

    openssl = shutil.which("openssl")
    if openssl is None:
        raise ProfileError("production-secure startup requires openssl certificate verification")
    verified = subprocess.run(
        [openssl, "verify", "-CAfile", str(ca), str(peer)],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    if verified.returncode != 0:
        raise ProfileError("peer certificate does not verify against the configured CA")


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
        ext = root / "peer.ext"
        ext.write_text("subjectAltName=URI:urn:ncp:commander-1\n", encoding="utf-8")
        commands = [
            [openssl, "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "2", "-subj", "/CN=NCP Test CA", "-keyout", str(ca_key), "-out", str(ca_cert)],
            [openssl, "req", "-newkey", "rsa:2048", "-nodes", "-subj", "/CN=NCP Peer", "-keyout", str(peer_key), "-out", str(peer_csr)],
            [openssl, "x509", "-req", "-in", str(peer_csr), "-CA", str(ca_cert), "-CAkey", str(ca_key), "-CAcreateserial", "-days", "2", "-extfile", str(ext), "-out", str(peer_cert)],
        ]
        for command in commands:
            result = subprocess.run(command, capture_output=True, timeout=30, check=False)
            if result.returncode != 0:
                raise ProfileError("could not build ephemeral self-test certificate chain")
        peer_key.chmod(0o600)
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
        try:
            runtime(config)
        except ProfileError:
            pass
        else:
            raise AssertionError("world-readable private key was accepted")


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
