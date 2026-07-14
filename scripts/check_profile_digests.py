#!/usr/bin/env python3
"""Independent Python replay for security-state and plant-profile digests."""

from __future__ import annotations

import argparse
import copy
import json
import math
from pathlib import Path
from typing import Any

from validate_security_profile import (
    MAX_PROFILE_PROJECTION_BYTES,
    ProfileError,
    _canonical_projection,
    _object_no_duplicates,
    _parse_int_preserve_negative_zero,
    digest as security_digest,
)


ROOT = Path(__file__).resolve().parents[1]
SECURITY_VECTORS = ROOT / "conformance/security-state-digest/v1.json"
PLANT_VECTORS = ROOT / "conformance/plant-profile/v1.json"
PLANT_DOMAIN = b"ncp.plant-profile-digest.v1\0"
SAFE_INTEGER_MAX = 9_007_199_254_740_991
MAX_PLANT_CHANNELS = 256
MAX_PLANT_CHANNEL_ARITY = 4096
MAX_SAFE_HOLD_MS = 1000
PROFILE_KEYS = {
    "schema",
    "status",
    "profile_id",
    "revision",
    "plant_class",
    "body_entity_id",
    "command_channels",
    "hold_action",
    "estop_action",
    "body_is_final_authority",
    "protocol_estop_is_physical_certification",
    "consumer_safety_case_required",
    "profile_digest_sha256",
}
CHANNEL_KEYS = {"name", "unit", "arity", "min", "max", "actuator_semantics"}
ACTION_KEYS = {"kind", "channel_values", "hold_max_ms", "body_local_executor"}


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
        raise ProfileError(f"cannot read digest vector file {path}: {error}") from error
    if not isinstance(value, dict):
        raise ProfileError(f"digest vector file {path} must be an object")
    return value


def _exact(value: Any, keys: set[str], field: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise ProfileError(f"{field} must contain exactly {sorted(keys)}")
    return value


def _id(value: Any, maximum: int, field: str) -> str:
    if not isinstance(value, str):
        raise ProfileError(f"{field} must be a string")
    try:
        encoded = value.encode("utf-8", errors="strict")
    except UnicodeEncodeError as error:
        raise ProfileError(f"{field} contains invalid Unicode") from error
    if not encoded or len(encoded) > maximum or any(
        character.isspace()
        or ord(character) < 32
        or 127 <= ord(character) <= 159
        or character in "/*$#?\ufeff"
        for character in value
    ):
        raise ProfileError(f"{field} is not a bounded canonical ID")
    return value


def _text(value: Any, maximum: int, field: str) -> str:
    if not isinstance(value, str):
        raise ProfileError(f"{field} must be a string")
    try:
        encoded = value.encode("utf-8", errors="strict")
    except UnicodeEncodeError as error:
        raise ProfileError(f"{field} contains invalid Unicode") from error
    if not encoded or len(encoded) > maximum or any(
        ord(character) < 32 or 127 <= ord(character) <= 159 for character in value
    ):
        raise ProfileError(f"{field} is not bounded control-free text")
    return value


def _finite(value: Any, field: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ProfileError(f"{field} must be a number")
    number = float(value)
    if not math.isfinite(number) or abs(number) > 1e300:
        raise ProfileError(f"{field} must be a finite in-budget binary64 number")
    return number


def _safe_action(
    raw: Any,
    *,
    field: str,
    channels: dict[str, tuple[int, float, float]],
    estop: bool,
) -> None:
    action = _exact(raw, ACTION_KEYS, field)
    kind = action["kind"]
    if kind not in {"neutral", "hold_last", "shutdown"}:
        raise ProfileError(f"{field}.kind is not registered")
    if estop and kind == "hold_last":
        raise ProfileError("ESTOP action cannot be hold_last")
    _id(action["body_local_executor"], 128, f"{field}.body_local_executor")
    values = action["channel_values"]
    if not isinstance(values, dict):
        raise ProfileError(f"{field}.channel_values must be an object")
    hold = action["hold_max_ms"]
    if kind == "hold_last":
        if values or not isinstance(hold, int) or isinstance(hold, bool) or not 1 <= hold <= MAX_SAFE_HOLD_MS:
            raise ProfileError(f"{field} hold_last members are invalid")
        return
    if hold is not None or set(values) != set(channels):
        raise ProfileError(f"{field} must define exactly every command channel")
    for name, samples in values.items():
        arity, minimum, maximum = channels[name]
        if not isinstance(samples, list) or len(samples) != arity:
            raise ProfileError(f"{field}.{name} has the wrong arity")
        if any(not minimum <= _finite(sample, f"{field}.{name}") <= maximum for sample in samples):
            raise ProfileError(f"{field}.{name} is outside its channel bounds")


def validate_plant(profile: Any, *, verify_digest: bool) -> dict[str, Any]:
    value = _exact(profile, PROFILE_KEYS, "plant profile")
    if value["schema"] != "ncp.plant-profile.v1":
        raise ProfileError("plant profile schema is not ncp.plant-profile.v1")
    if value["status"] not in {"reference-non-certifying", "deployment-specific"}:
        raise ProfileError("plant profile status is not registered")
    if value["plant_class"] not in {"simulation", "uav", "mobile_base", "arm", "other"}:
        raise ProfileError("plant_class is not registered")
    _id(value["profile_id"], 128, "profile_id")
    _id(value["body_entity_id"], 128, "body_entity_id")
    revision = value["revision"]
    if not isinstance(revision, int) or isinstance(revision, bool) or not 1 <= revision <= SAFE_INTEGER_MAX:
        raise ProfileError("revision is outside 1..JSON-safe-integer-max")
    if (
        value["body_is_final_authority"] is not True
        or value["protocol_estop_is_physical_certification"] is not False
        or value["consumer_safety_case_required"] is not True
    ):
        raise ProfileError("plant profile weakens the non-certifying body-authority boundary")

    raw_channels = value["command_channels"]
    if not isinstance(raw_channels, list) or not 1 <= len(raw_channels) <= MAX_PLANT_CHANNELS:
        raise ProfileError("command_channels count is outside 1..256")
    channels: dict[str, tuple[int, float, float]] = {}
    prior: bytes | None = None
    for index, raw in enumerate(raw_channels):
        channel = _exact(raw, CHANNEL_KEYS, f"command_channels[{index}]")
        name = _id(channel["name"], 128, f"command_channels[{index}].name")
        encoded_name = name.encode("utf-8")
        if prior is not None and prior >= encoded_name:
            raise ProfileError("command channel names must be unique and lexically sorted")
        prior = encoded_name
        _text(channel["unit"], 64, f"command_channels[{index}].unit")
        _text(
            channel["actuator_semantics"],
            512,
            f"command_channels[{index}].actuator_semantics",
        )
        arity = channel["arity"]
        if not isinstance(arity, int) or isinstance(arity, bool) or not 1 <= arity <= MAX_PLANT_CHANNEL_ARITY:
            raise ProfileError(f"command_channels[{index}].arity is outside 1..4096")
        minimum = _finite(channel["min"], f"command_channels[{index}].min")
        maximum = _finite(channel["max"], f"command_channels[{index}].max")
        if minimum > maximum:
            raise ProfileError(f"command_channels[{index}] min exceeds max")
        channels[name] = (arity, minimum, maximum)

    _safe_action(value["hold_action"], field="hold_action", channels=channels, estop=False)
    _safe_action(value["estop_action"], field="estop_action", channels=channels, estop=True)
    embedded = value["profile_digest_sha256"]
    if not isinstance(embedded, str):
        raise ProfileError("profile_digest_sha256 must be a string")
    try:
        embedded.encode("utf-8", errors="strict")
    except UnicodeEncodeError as error:
        raise ProfileError("profile_digest_sha256 contains invalid Unicode") from error
    if len(embedded) != 64 or any(
        character not in "0123456789abcdef" for character in embedded
    ):
        if verify_digest:
            raise ProfileError("profile_digest_sha256 is not 64 lowercase hex")
    if verify_digest and embedded != plant_digest(value, validate=False):
        raise ProfileError("profile_digest_sha256 is stale or mismatched")
    return value


def plant_digest(profile: dict[str, Any], *, validate: bool = True) -> str:
    if validate:
        validate_plant(profile, verify_digest=False)
    projection = dict(profile)
    projection.pop("profile_digest_sha256")
    import hashlib

    return hashlib.sha256(_canonical_projection(PLANT_DOMAIN, projection)).hexdigest()


def _replay(
    path: Path,
    digest_fn,
    validate_fn,
    *,
    schema: str,
    normative_contract: str,
) -> tuple[int, int]:
    corpus = load(path)
    required_root = {
        "schema",
        "wire_version",
        "normative_contract",
        "valid_cases",
        "invalid_cases",
    }
    if set(corpus) != required_root:
        raise ProfileError(f"{path.name} corpus root members are not exact")
    if (
        corpus["schema"] != schema
        or corpus["wire_version"] != "1.0"
        or corpus["normative_contract"] != normative_contract
    ):
        raise ProfileError(f"{path.name} corpus identity is invalid")
    valid_cases = corpus["valid_cases"]
    invalid_cases = corpus["invalid_cases"]
    if not isinstance(valid_cases, list) or not valid_cases:
        raise ProfileError(f"{path.name} valid_cases must be a non-empty array")
    if not isinstance(invalid_cases, list) or not invalid_cases:
        raise ProfileError(f"{path.name} invalid_cases must be a non-empty array")
    seen: set[str] = set()
    passed = 0
    total = 0
    for case in valid_cases:
        total += 1
        if not isinstance(case, dict) or set(case) != {"id", "input", "expected_digest"}:
            raise ProfileError(f"{path.name} valid case shape is not exact")
        if (
            not isinstance(case["id"], str)
            or not case["id"]
            or case["id"] in seen
            or not isinstance(case["input"], dict)
            or not isinstance(case["expected_digest"], str)
            or len(case["expected_digest"]) != 64
            or any(character not in "0123456789abcdef" for character in case["expected_digest"])
        ):
            raise ProfileError(f"{path.name} valid case identity/input/digest is invalid")
        seen.add(case["id"])
        try:
            got = digest_fn(case["input"])
            if got != case["expected_digest"]:
                raise ProfileError(f"got {got}, expected {case['expected_digest']}")
        except (KeyError, TypeError, ValueError, OverflowError) as error:
            raise ProfileError(f"{path.name} valid case {case.get('id')!r} failed: {error}") from error
        passed += 1
    for case in invalid_cases:
        total += 1
        if not isinstance(case, dict) or set(case) not in (
            {"id", "input", "expect"},
            {"id", "input", "expect", "digest_expect"},
        ):
            raise ProfileError(f"{path.name} invalid case shape is not exact")
        if (
            not isinstance(case["id"], str)
            or not case["id"]
            or case["id"] in seen
            or not isinstance(case["input"], dict)
            or case["expect"] != "reject"
            or ("digest_expect" in case and case["digest_expect"] != "reject")
        ):
            raise ProfileError(f"{path.name} invalid case identity/input/expectation is invalid")
        seen.add(case["id"])
        if case.get("digest_expect") == "reject":
            try:
                digest_fn(case["input"])
            except (TypeError, ValueError, OverflowError, UnicodeError):
                pass
            else:
                raise ProfileError(
                    f"{path.name} invalid case {case['id']!r} was digestible"
                )
        try:
            validate_fn(case["input"])
        except (TypeError, ValueError, OverflowError, UnicodeError):
            passed += 1
            continue
        raise ProfileError(f"{path.name} invalid case {case.get('id')!r} was accepted")
    return passed, total


def canonical_self_test() -> None:
    negative_zero = json.loads("-0", parse_int=_parse_int_preserve_negative_zero)
    assert isinstance(negative_zero, float) and math.copysign(1.0, negative_zero) == -1.0
    assert _canonical_projection(b"a\0", None)
    for domain in (b"missing-nul", b"\0", b"ncp\0embedded\0", b"NCP.upper.v1\0"):
        try:
            _canonical_projection(domain, None)
        except ProfileError:
            pass
        else:
            raise AssertionError(f"invalid canonical domain {domain!r} was accepted")

    nested: Any = None
    for _ in range(33):
        nested = [nested]
    hostile_values = [
        nested,
        "x" * MAX_PROFILE_PROJECTION_BYTES,
        1e301,
    ]
    for value in hostile_values:
        try:
            _canonical_projection(b"ncp.test.v1\0", value)
        except ProfileError:
            pass
        else:
            raise AssertionError("out-of-budget canonical value was accepted")

    plant = load(PLANT_VECTORS)["valid_cases"][0]["input"]
    for invalid_digest in (7, "\ud800"):
        hostile = copy.deepcopy(plant)
        hostile["profile_digest_sha256"] = invalid_digest
        try:
            plant_digest(hostile)
        except ProfileError:
            pass
        else:
            raise AssertionError("invalid plant digest field was accepted for computation")

    security = load(SECURITY_VECTORS)["valid_cases"][0]["input"]
    hostile_security = copy.deepcopy(security)
    hostile_security["bind"] = {"kind": "unix", "path": "/\ud800"}
    try:
        security_digest(hostile_security)
    except ProfileError:
        pass
    else:
        raise AssertionError("invalid Unicode UDS path was accepted")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--print-plant-digest", type=Path)
    parser.add_argument("--print-security-digest", type=Path)
    arguments = parser.parse_args()
    if arguments.print_plant_digest:
        profile = load(arguments.print_plant_digest)
        print(plant_digest(profile))
        return 0
    if arguments.print_security_digest:
        profile = load(arguments.print_security_digest)
        print(security_digest(profile))
        return 0
    canonical_self_test()
    security = _replay(
        SECURITY_VECTORS,
        security_digest,
        security_digest,
        schema="ncp.security-state-digest.conformance.v1",
        normative_contract="contract/security-state-digest.v1.json",
    )
    plant = _replay(
        PLANT_VECTORS,
        plant_digest,
        lambda value: validate_plant(value, verify_digest=True),
        schema="ncp.plant-profile.conformance.v1",
        normative_contract="contract/plant-profile.v1.json",
    )
    print(
        f"OK portable profile digests: security {security[0]}/{security[1]}, "
        f"plant {plant[0]}/{plant[1]}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
