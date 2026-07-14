#!/usr/bin/env python3
"""Generate or verify the mandatory NCP 1.0 conformance manifest.

The manifest is intentionally derived from the committed corpus.  A deleted,
renamed, duplicated, mutated, or unrecognized vector changes the generated
manifest and therefore fails ``--check``.  The corpus digest excludes the
manifest itself, avoiding a self-referential hash.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "conformance" / "manifest.v1.json"
BEHAVIOR = ROOT / "conformance" / "behavior" / "vectors.json"
REQUEST_DIGEST = ROOT / "conformance" / "request-digest" / "v1.json"
SECURITY_STATE_DIGEST = ROOT / "conformance" / "security-state-digest" / "v1.json"
PLANT_PROFILE = ROOT / "conformance" / "plant-profile" / "v1.json"
MIGRATION = (
    ROOT
    / "conformance"
    / "migration"
    / "v0.8-to-v1.0"
    / "channel-requirement.json"
)
VECTORS = ROOT / "conformance" / "vectors"
WIRE_VERSION = "1.0"
IMPLEMENTATIONS = ["rust", "typescript", "python-ffi", "cpp-ffi"]


def parse_int_preserve_negative_zero(token: str) -> int | float:
    return -0.0 if token == "-0" else int(token, 10)


def object_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, member in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key {key!r}")
        value[key] = member
    return value


def load_json(path: Path) -> Any:
    return json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=object_no_duplicates,
        parse_int=parse_int_preserve_negative_zero,
    )


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def roles_for(kind: str) -> list[str]:
    if kind in {"command_frame", "sensor_frame", "link_status", "control_status"}:
        return ["commander", "body"]
    if kind in {"observation_frame"}:
        return ["body", "observer"]
    if kind in {"capabilities"}:
        return ["commander", "body", "observer", "operator"]
    if kind in {
        "open_session",
        "step_request",
        "run_request",
        "close_session",
    }:
        return ["commander"]
    if kind in {"session_opened", "session_closed"}:
        return ["body"]
    return ["commander", "body", "observer", "operator"]


def clause_for_behavior(family: str, name: str) -> str:
    if family == "check_version":
        return "proto/ncp.proto#wire-version-compatibility"
    if family == "contract_status":
        return "proto/ncp.proto#contract-hash-advisory"
    if family == "govern":
        return "NEURO_CYBERNETIC_PROTOCOL.md#plant-safety-governor"
    if family == "action_buffer":
        return "NEURO_CYBERNETIC_PROTOCOL.md#action-buffer-and-estop"
    if "gateway" in name or "legacy_optional" in name:
        return "NEURO_CYBERNETIC_PROTOCOL.md#labelled-legacy-gateway"
    if "authority" in name:
        return "NEURO_CYBERNETIC_PROTOCOL.md#authority-leases"
    if "operation" in name or "receipt" in name:
        return "NEURO_CYBERNETIC_PROTOCOL.md#idempotent-lifecycle-rpcs"
    if "identity" in name or "security" in name:
        return "NEURO_CYBERNETIC_PROTOCOL.md#identity-and-security-profile"
    if name.startswith("capabilities_"):
        return "NEURO_CYBERNETIC_PROTOCOL.md#capability-negotiation"
    if "calibrated" in name or "not_sim" in name or "provenance" in name:
        return "NEURO_CYBERNETIC_PROTOCOL.md#scientific-boundary"
    if name.startswith("command_frame_") or name.startswith("sensor_frame_"):
        return "NEURO_CYBERNETIC_PROTOCOL.md#data-plane-envelope"
    if name.startswith("observation_"):
        return "NEURO_CYBERNETIC_PROTOCOL.md#observation-plane"
    if name.startswith("session_") or name.startswith("error_"):
        return "NEURO_CYBERNETIC_PROTOCOL.md#lifecycle-and-errors"
    return "contract/limits.v1.json#json"


def behavior_roles(family: str, case: dict[str, Any]) -> list[str]:
    if family in {"govern", "action_buffer"}:
        return ["body"]
    kind = case.get("input", {}).get("kind")
    return roles_for(kind) if isinstance(kind, str) else roles_for("")


def make_behavior_entries(data: dict[str, Any]) -> list[dict[str, Any]]:
    if data.get("ncp_version") != WIRE_VERSION:
        raise ValueError("behavior corpus wire version is not 1.0")
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    cases = data.get("cases")
    if not isinstance(cases, dict):
        raise ValueError("behavior corpus cases must be an object")
    for family in sorted(cases):
        family_cases = cases[family]
        if not isinstance(family_cases, list):
            raise ValueError(f"behavior family {family!r} must be an array")
        for index, case in enumerate(family_cases):
            if not isinstance(case, dict) or not isinstance(case.get("name"), str):
                raise ValueError(f"behavior {family}[{index}] has no string name")
            name = case["name"]
            vector_id = f"behavior/{family}/{name}"
            if vector_id in seen:
                raise ValueError(f"duplicate vector id {vector_id}")
            seen.add(vector_id)
            if family == "action_buffer":
                if not isinstance(case.get("operations"), list):
                    raise ValueError(f"{vector_id} must carry an operations array")
                input_pointer = f"/cases/{family}/{index}/operations"
                expected_pointer = f"/cases/{family}/{index}/operations/*/expect"
            else:
                if "input" not in case or "expect" not in case:
                    raise ValueError(f"{vector_id} must carry input and expect")
                input_pointer = f"/cases/{family}/{index}/input"
                expected_pointer = f"/cases/{family}/{index}/expect"
            entries.append(
                {
                    "id": vector_id,
                    "stability": "stable-1.0",
                    "suite": "behavior",
                    "normative_clause": clause_for_behavior(family, name),
                    "source": relative(BEHAVIOR),
                    "input": input_pointer,
                    "state": (
                        "stateful-sequence"
                        if family == "action_buffer"
                        else "fresh-instance-per-vector"
                    ),
                    "expected": expected_pointer,
                    "resource_budget": "contract/limits.v1.json#/json",
                    "applicability": {
                        "roles": behavior_roles(family, case),
                        "implementations": IMPLEMENTATIONS,
                        "transports": ["transport-independent"],
                    },
                    "wire_version": WIRE_VERSION,
                    "required": True,
                }
            )
    return entries


def make_wire_entries(paths: list[Path]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    seen_kinds: set[str] = set()
    for path in paths:
        value = load_json(path)
        kind = value.get("kind")
        if not isinstance(kind, str) or not kind:
            raise ValueError(f"{relative(path)} has no message kind")
        if kind in seen_kinds:
            raise ValueError(f"duplicate canonical wire vector for {kind}")
        seen_kinds.add(kind)
        entries.append(
            {
                "id": f"wire/{kind}/canonical",
                "stability": "stable-1.0",
                "suite": "wire-shape",
                "normative_clause": f"proto/ncp.proto#{kind}",
                "source": relative(path),
                "input": "",
                "state": "stateless",
                "expected": "accept-and-roundtrip-canonical-json",
                "resource_budget": "contract/limits.v1.json#/json",
                "applicability": {
                    "roles": roles_for(kind),
                    "implementations": IMPLEMENTATIONS,
                    "transports": ["canonical-json"],
                },
                "wire_version": WIRE_VERSION,
                "required": True,
            }
        )
    return entries


def make_request_digest_entries(data: dict[str, Any]) -> list[dict[str, Any]]:
    if data.get("wire_version") != WIRE_VERSION:
        raise ValueError("request-digest corpus wire version is not 1.0")
    cases = data.get("cases")
    if not isinstance(cases, list):
        raise ValueError("request-digest corpus cases must be an array")
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, case in enumerate(cases):
        case_id = case.get("id") if isinstance(case, dict) else None
        if not isinstance(case_id, str) or not case_id:
            raise ValueError(f"request-digest case {index} has no id")
        vector_id = f"request-digest/{case_id}"
        if vector_id in seen:
            raise ValueError(f"duplicate vector id {vector_id}")
        seen.add(vector_id)
        if not isinstance(case.get("patch"), list) or not isinstance(
            case.get("expected_digest"), str
        ):
            raise ValueError(f"{vector_id} has no patch/digest expectation")
        entries.append(
            {
                "id": vector_id,
                "stability": "stable-1.0",
                "suite": "request-digest-v1",
                "normative_clause": "contract/request-digest.v1.json",
                "source": relative(REQUEST_DIGEST),
                "input": f"/cases/{index}/patch",
                "state": "fresh-base-request-per-vector",
                "expected": f"/cases/{index}/expected_digest",
                "resource_budget": "contract/limits.v1.json#/request_digest",
                "applicability": {
                    "roles": ["commander", "body"],
                    "implementations": IMPLEMENTATIONS,
                    "transports": ["transport-independent"],
                },
                "wire_version": WIRE_VERSION,
                "required": True,
            }
        )
    return entries


def make_profile_entries(
    data: dict[str, Any],
    *,
    source: Path,
    prefix: str,
    suite: str,
    clause: str,
    resource_budget: str,
) -> list[dict[str, Any]]:
    if data.get("wire_version") != WIRE_VERSION:
        raise ValueError(f"{prefix} corpus wire version is not 1.0")
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for family in ("valid_cases", "invalid_cases"):
        cases = data.get(family)
        if not isinstance(cases, list):
            raise ValueError(f"{prefix} {family} must be an array")
        for index, case in enumerate(cases):
            case_id = case.get("id") if isinstance(case, dict) else None
            if not isinstance(case_id, str) or not case_id:
                raise ValueError(f"{prefix} {family}[{index}] has no id")
            vector_id = f"{prefix}/{case_id}"
            if vector_id in seen:
                raise ValueError(f"duplicate vector id {vector_id}")
            seen.add(vector_id)
            expectation = "expected_digest" if family == "valid_cases" else "expect"
            if "input" not in case or not isinstance(case.get(expectation), str):
                raise ValueError(f"{vector_id} has no input/{expectation}")
            entries.append(
                {
                    "id": vector_id,
                    "stability": "stable-1.0",
                    "suite": suite,
                    "normative_clause": clause,
                    "source": relative(source),
                    "input": f"/{family}/{index}/input",
                    "state": "stateless-validated-profile",
                    "expected": f"/{family}/{index}/{expectation}",
                    "resource_budget": resource_budget,
                    "applicability": {
                        "roles": ["commander", "body", "operator"],
                        "implementations": ["rust"],
                        "transports": ["transport-independent"],
                    },
                    "wire_version": WIRE_VERSION,
                    "required": True,
                }
            )
    return entries


def make_migration_entries(data: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    cases = data.get("cases")
    if not isinstance(cases, list):
        raise ValueError("migration cases must be an array")
    for index, case in enumerate(cases):
        vector_id = case.get("id") if isinstance(case, dict) else None
        if not isinstance(vector_id, str) or not vector_id:
            raise ValueError(f"migration case {index} has no id")
        entries.append(
            {
                "id": f"migration/{vector_id}",
                "stability": "migration-only",
                "suite": "v0.8-to-v1.0",
                "normative_clause": (
                    "NEURO_CYBERNETIC_PROTOCOL.md#labelled-legacy-gateway"
                ),
                "source": relative(MIGRATION),
                "input": f"/cases/{index}",
                "state": "authenticated-terminating-gateway",
                "expected": f"/cases/{index}/expected",
                "resource_budget": "contract/limits.v1.json#/json",
                "applicability": {
                    "roles": ["operator"],
                    "implementations": ["rust"],
                    "transports": ["terminating-gateway"],
                },
                "wire_version": WIRE_VERSION,
                "source_wire_version": "0.8",
                "required": True,
            }
        )
    return entries


def matching(entries: list[dict[str, Any]], *needles: str) -> list[str]:
    result = [
        entry["id"]
        for entry in entries
        if any(needle in entry["id"] for needle in needles)
    ]
    if not result:
        raise ValueError(f"coverage selector {needles!r} matched no vector")
    return result


def requirements(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    definitions = [
        (
            "NCP-REQ-001",
            "proto/ncp.proto#wire-version-compatibility",
            "Wire version compatibility is a fail-closed gate.",
            ("behavior/check_version/",),
        ),
        (
            "NCP-REQ-002",
            "contract/limits.v1.json#json",
            "Every JSON envelope is decoded within the universal resource budget.",
            ("unsafe", "fractional", "sequence_rejected", "bounded"),
        ),
        (
            "NCP-REQ-003",
            "NEURO_CYBERNETIC_PROTOCOL.md#identity-and-security-profile",
            "Identity role, entity, plane, profile, and security digest fail closed.",
            ("identity", "security_profile", "security_digest", "security-state-digest/"),
        ),
        (
            "NCP-REQ-004",
            "NEURO_CYBERNETIC_PROTOCOL.md#labelled-legacy-gateway",
            "Legacy translation is explicit, visible, one-way, and ambiguity rejecting.",
            ("gateway", "legacy_optional", "migration/"),
        ),
        (
            "NCP-REQ-005",
            "NEURO_CYBERNETIC_PROTOCOL.md#session-generations-and-stream-epochs",
            "Session-scoped messages bind a live session generation.",
            ("stale_operation_epoch", "stale_authority_epoch", "generation_without"),
        ),
        (
            "NCP-REQ-006",
            "NEURO_CYBERNETIC_PROTOCOL.md#authority-leases",
            "Actuation and lifecycle mutation require a bounded matching authority lease.",
            ("authority",),
        ),
        (
            "NCP-REQ-007",
            "NEURO_CYBERNETIC_PROTOCOL.md#idempotent-lifecycle-rpcs",
            "Lifecycle mutations carry idempotency context and terminal receipts.",
            ("operation", "receipt", "request-digest/"),
        ),
        (
            "NCP-REQ-008",
            "NEURO_CYBERNETIC_PROTOCOL.md#capability-negotiation",
            "Stable capabilities and channel requirements are explicit closed choices.",
            ("capabilities_",),
        ),
        (
            "NCP-REQ-009",
            "NEURO_CYBERNETIC_PROTOCOL.md#scientific-boundary",
            "Simulation output never claims a calibrated posterior or reproduction.",
            ("calibrated", "not_sim", "provenance"),
        ),
        (
            "NCP-REQ-010",
            "NEURO_CYBERNETIC_PROTOCOL.md#plant-safety-governor",
            "TTL, horizon, geofence, speed, HOLD, and ESTOP decisions are deterministic.",
            ("behavior/govern/", "behavior/action_buffer/"),
        ),
        (
            "NCP-REQ-011",
            "NEURO_CYBERNETIC_PROTOCOL.md#plant-profile",
            "Plant negotiation binds a content-addressed plant profile.",
            ("plant_profile_digest", "plant-profile/"),
        ),
        (
            "NCP-REQ-012",
            "NEURO_CYBERNETIC_PROTOCOL.md#lifecycle-and-errors",
            "Errors carry a registered code; version and session identity fields fail closed.",
            ("error_",),
        ),
        (
            "NCP-REQ-013",
            "proto/ncp.proto",
            "Every stable message kind has a canonical wire vector.",
            ("wire/",),
        ),
    ]
    return [
        {
            "id": requirement_id,
            "source": source,
            "requirement": statement,
            "vector_ids": matching(entries, *selectors),
        }
        for requirement_id, source, statement, selectors in definitions
    ]


def build_manifest() -> dict[str, Any]:
    behavior_data = load_json(BEHAVIOR)
    request_digest_data = load_json(REQUEST_DIGEST)
    security_digest_data = load_json(SECURITY_STATE_DIGEST)
    plant_profile_data = load_json(PLANT_PROFILE)
    migration_data = load_json(MIGRATION)
    wire_paths = sorted(VECTORS.glob("*.json"))
    source_paths = [
        BEHAVIOR,
        REQUEST_DIGEST,
        SECURITY_STATE_DIGEST,
        PLANT_PROFILE,
        MIGRATION,
        *wire_paths,
    ]
    entries = sorted(
        [
            *make_behavior_entries(behavior_data),
            *make_request_digest_entries(request_digest_data),
            *make_profile_entries(
                security_digest_data,
                source=SECURITY_STATE_DIGEST,
                prefix="security-state-digest",
                suite="security-state-digest-v1",
                clause="contract/security-state-digest.v1.json",
                resource_budget="contract/canonical-digest.v1.json#/limits",
            ),
            *make_profile_entries(
                plant_profile_data,
                source=PLANT_PROFILE,
                prefix="plant-profile",
                suite="plant-profile-v1",
                clause="contract/plant-profile.v1.json",
                resource_budget="contract/canonical-digest.v1.json#/limits",
            ),
            *make_wire_entries(wire_paths),
            *make_migration_entries(migration_data),
        ],
        key=lambda entry: entry["id"],
    )
    ids = [entry["id"] for entry in entries]
    if len(ids) != len(set(ids)):
        raise ValueError("the combined corpus contains duplicate vector ids")
    sources = [
        {
            "path": relative(path),
            "sha256": sha256_file(path),
            "bytes": path.stat().st_size,
        }
        for path in source_paths
    ]
    digest_input = {"sources": sources, "vectors": entries}
    manifest = {
        "schema": "ncp.conformance-manifest.v1",
        "status": "candidate-unreleased",
        "wire_version": WIRE_VERSION,
        "contract_hash": behavior_data["contract_hash"],
        "generated_by": "scripts/generate_conformance_manifest.py",
        "skip_policy": "required-vector-skip-is-failure",
        "unknown_vector_policy": "reject",
        "partial_report_policy": "reject",
        "corpus_digest_sha256": sha256_bytes(canonical_bytes(digest_input)),
        "sources": sources,
        "counts": {
            "required_total": len(entries),
            "stable_1_0": sum(
                entry["stability"] == "stable-1.0" for entry in entries
            ),
            "migration_only": sum(
                entry["stability"] == "migration-only" for entry in entries
            ),
        },
        "report_requirements": {
            "implementation_version": "required",
            "wire_version": "required",
            "contract_digest": "required",
            "corpus_digest": "required",
            "source_revision": "required",
            "executed_vector_ids": "exact-set-required",
            "skipped_vector_ids": "must-be-empty-for-applicable-stable-vectors",
            "result": "pass-only-if-complete",
            "signature": "required-for-release; unavailable-on-this-candidate",
        },
        "excluded_fixtures": [
            {
                "path": "conformance/vectors/bulk_observation.bin",
                "sha256": sha256_file(VECTORS / "bulk_observation.bin"),
                "reason": "offline-experimental BulkBlock; bare NCPB transport is excluded",
            }
        ],
        "normative_requirements": requirements(entries),
        "vectors": entries,
    }
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--write", action="store_true", help="replace the committed generated manifest"
    )
    args = parser.parse_args()
    generated = json.dumps(build_manifest(), ensure_ascii=False, indent=2) + "\n"
    if args.write:
        MANIFEST.write_text(generated, encoding="utf-8")
        print(f"wrote {relative(MANIFEST)}")
        return 0
    if not MANIFEST.exists():
        print(f"ERROR: {relative(MANIFEST)} is missing; run with --write")
        return 1
    current = MANIFEST.read_text(encoding="utf-8")
    if current != generated:
        print(
            f"ERROR: {relative(MANIFEST)} is stale or corpus coverage changed; "
            "run with --write and review the manifest diff"
        )
        return 1
    parsed = json.loads(current, object_pairs_hook=object_no_duplicates)
    print(
        "OK conformance manifest: "
        f"{parsed['counts']['required_total']} required vectors, "
        f"{len(parsed['normative_requirements'])} normative requirements, "
        f"digest {parsed['corpus_digest_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
