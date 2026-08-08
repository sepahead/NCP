#!/usr/bin/env python3
"""Finite mutation probes for proposed observer and consumer decisions.

This is pre-ratification counterexample-discovery material. It is not a protocol
model, implementation proof, independent review, interoperability result, or
release evidence.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import itertools
import json
import re
from collections.abc import Callable, Iterable
from dataclasses import MISSING, asdict, dataclass, replace
from typing import Any

from observer_capture_probe import (
    build_capture_action_result,
    build_grant_lifecycle_result,
)

CLAIM_BOUNDARY = (
    "These finite guard, lifecycle, capture, and inventory probes challenge only "
    "their encoded abstractions. They do not prove protocol correctness, transport "
    "security, implementation refinement, interoperability, plant safety, or "
    "release readiness."
)

OBSERVER = "observer-principal"
ATTACKER = "attacker-principal"
SUBSCRIBE = "subscribe"
HISTORY_QUERY = "history_query"
PUBLISH = "publish"
CREATE_COMMAND = "create_command"
CREATE_DISPOSITION = "create_disposition"
ACQUIRE_AUTHORITY = "acquire_authority"
RENEW_AUTHORITY = "renew_authority"
ESTOP = "estop"
MUTATE_LIFECYCLE = "mutate_lifecycle"
DECLARE_PUBLISHER = "declare_publisher"
DECLARE_QUERYABLE = "declare_queryable"
DECLARE_STREAM = "declare_stream"
PUBLISH_ASSESSMENT = "publish_assessment"
SURFACE_INPUT_MANIFEST_PATH = ".ncp-surface-inputs.v1.json"
PYTHON_MIRROR_INPUT_MANIFEST_KEY = SURFACE_INPUT_MANIFEST_PATH
OUTPUT_INVENTORY_DESCRIPTOR_PATH = ".ncp-consumer"
SURFACE_INVENTORY_GENESIS_FROM_UNINITIALIZED = (
    "SURFACE_INVENTORY_GENESIS_FROM_UNINITIALIZED"
)
SURFACE_INVENTORY_REPIN_COMPARE_AND_SWAP = "SURFACE_INVENTORY_REPIN_COMPARE_AND_SWAP"
DESCRIPTOR_VERSION_FLOOR_ADVANCE = "DESCRIPTOR_VERSION_FLOOR_ADVANCE"
TRUSTED_SUBJECT_AUTHORIZATION_GRANT = "TRUSTED_SUBJECT_AUTHORIZATION_GRANT"
TRUSTED_SUBJECT_AUTHORIZATION_REVOKE = "TRUSTED_SUBJECT_AUTHORIZATION_REVOKE"
TRUSTED_SCANNER_AUTHORIZATION_GRANT = "TRUSTED_SCANNER_AUTHORIZATION_GRANT"
TRUSTED_SCANNER_AUTHORIZATION_REVOKE = "TRUSTED_SCANNER_AUTHORIZATION_REVOKE"
FENCE_INVENTORY_AUTHORITY = "FENCE_INVENTORY_AUTHORITY"
RETIRE_INVENTORY_AUTHORITY = "RETIRE_INVENTORY_AUTHORITY"
INVENTORY_TRANSITION_KINDS = {
    SURFACE_INVENTORY_GENESIS_FROM_UNINITIALIZED,
    SURFACE_INVENTORY_REPIN_COMPARE_AND_SWAP,
    DESCRIPTOR_VERSION_FLOOR_ADVANCE,
    TRUSTED_SUBJECT_AUTHORIZATION_GRANT,
    TRUSTED_SUBJECT_AUTHORIZATION_REVOKE,
    TRUSTED_SCANNER_AUTHORIZATION_GRANT,
    TRUSTED_SCANNER_AUTHORIZATION_REVOKE,
    FENCE_INVENTORY_AUTHORITY,
    RETIRE_INVENTORY_AUTHORITY,
}
INVENTORY_AUTHORITY_STATUSES = {
    "ACTIVE",
    "MIGRATION_REQUIRED_DISABLED",
    "AUTHORIZATION_REVOKED_DISABLED",
    "FENCED",
    "RETIRED",
}
SCANNER_RECEIPT_ELIGIBILITY = {"ELIGIBLE", "REVOKED_DISABLED"}
INVENTORY_PARENT_AUTHORITY = "ncp-b03-consumer-inventory-parent"
OBSERVER_READ_OPERATIONS = (SUBSCRIBE, HISTORY_QUERY)
OBSERVER_PROHIBITED_OPERATIONS = (
    PUBLISH,
    CREATE_COMMAND,
    CREATE_DISPOSITION,
    ACQUIRE_AUTHORITY,
    RENEW_AUTHORITY,
    ESTOP,
    MUTATE_LIFECYCLE,
    DECLARE_PUBLISHER,
    DECLARE_QUERYABLE,
    DECLARE_STREAM,
    PUBLISH_ASSESSMENT,
)
OBSERVER_OPERATIONS = (*OBSERVER_READ_OPERATIONS, *OBSERVER_PROHIBITED_OPERATIONS)
LITERAL_ROUTE = "ncp/session/plant-alpha/command/motor"
OTHER_ROUTE = "ncp/session/plant-alpha/command/other"
WILDCARD_ROUTE = "ncp/session/plant-alpha/command/*"
FULL = "full"
REDACTED = "redacted"
WIRE_08 = "wire-0.8"
WIRE_10 = "wire-1.0"
KNOWN_WIRES = {WIRE_08, WIRE_10}
WIRE_NEUTRAL = "not-applicable"
KNOWN_PROVIDER_WIRES = {*KNOWN_WIRES, WIRE_NEUTRAL}
NCP_V08_RELEASE_COMMIT = "2f5bd586d4bb20c90362bb6f5698b7f64057ba4e"
NCP_V08_RELEASE_TREE = "488b4add0c43417681c7d87d73e433d46bfa5b78"
NCP_V08_SUBJECT_ARTIFACT_SHA256 = (
    "2adf28e7c2f1956a824cadb93f048d66be74e90ce1c6ed0b7a1a921ba0b870de"
)
HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
IDENTIFIER = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
SCOPED_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_-]{0,127}$")
SURFACE_ID = re.compile(r"^surface_[0-9a-f]{64}$")
BOUNDED_TOKEN = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,127}$")
BOUNDED_CONTEXT_VALUE = re.compile(r"^[\x20-\x7e]{1,256}$")
TARGET_CFG_PREDICATE = re.compile(r'^cfg\(([a-z][a-z0-9_]*) = "([A-Za-z0-9_.-]+)"\)$')
PATH_COMPONENT = re.compile(r"^[A-Za-z0-9.][A-Za-z0-9._-]{0,127}$")
PACKAGE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9+.:/@?#=_~-]{0,255}$")
SEMVER_TAG = re.compile(
    r"^v(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
    r"(?:[-+][0-9A-Za-z.-]+)?$"
)
RELATIVE_PATH = re.compile(r"^(?!/)(?!.*(?:^|/)\.\.(?:/|$)).{1,256}$")
MAX_EXCLUSIONS = 4
MAX_DISCOVERY_RECORDS = 32
MAX_SURFACES = 16
MAX_PROVIDER_NODES = 64
MAX_PROVIDER_EDGES = 256
EXCLUSION_REASONS = {
    "documentation_only",
    "non_executable_historical",
    "scanner_fixture",
}
ROLE_CAPABILITY_CLASSES = {
    "observer": "observer_read",
    "assessor": "assessment_publish",
    "commander": "plant_command",
    "assessment_receiver": "assessment_receive",
    "simulation_responder": "simulation_respond",
    "plant_commander": "plant_command",
}
ISOLATED_CAPABILITY_PAIRS = {
    frozenset(("observer_read", "assessment_publish")),
    frozenset(("plant_command", "assessment_receive")),
    frozenset(("simulation_respond", "plant_command")),
    frozenset(("observer_read", "plant_command")),
}
PRIVILEGED_CAPABILITIES = {
    "assessment_publish",
    "assessment_receive",
    "plant_command",
    "simulation_respond",
}
KNOWN_ECOSYSTEMS = {"cargo", "python_mirror", "non_build"}
KNOWN_LOCATOR_KINDS = {"cargo_target", "python_mirror", "none"}
KNOWN_CONTRACT_IDENTITY_KINDS = {
    "complete_normative_contract",
    "frozen_wire_baseline_artifact",
}
SCOPED_SURFACE_FIELDS = {
    "deployment_profile": "deployment",
    "process_namespace": "process",
    "credential_set": "credential",
    "security_manifest": "security",
    "route_namespace": "routes",
    "state_store": "state",
    "configuration_namespace": "configuration",
    "evidence_namespace": "evidence",
    "plant_session_namespace": "session",
}
TRUSTED_DESCRIPTOR_VERSION_FLOORS = {
    "engram": 2,
    "galadriel": 2,
    "haldir": 2,
    "prisoma": 2,
}


class ProbeError(RuntimeError):
    """One baseline, sensitivity, bound, or result-shape failure."""


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _canonical_digest(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _executed_logic_mutant_witness(
    *,
    name: str,
    reason: str,
    witness: dict[str, Any],
    expected: Any,
    observed: Any,
) -> dict[str, Any]:
    if expected == observed:
        raise ProbeError(f"executed logic mutant survived: {name}")
    return {
        "name": name,
        "detected": True,
        "reason": reason,
        "expected": expected,
        "observed": observed,
        "witness": witness,
    }


def _hostile_witness(
    name: str,
    action: Callable[[], None],
    witness: dict[str, Any],
) -> dict[str, Any]:
    try:
        action()
    except ProbeError as error:
        return {
            "name": name,
            "rejected": True,
            "reason": str(error),
            "witness": witness,
        }
    raise ProbeError(f"hostile input was accepted: {name}")


def _invariant_witness(
    name: str,
    observed: bool,
    witness: dict[str, Any],
) -> dict[str, Any]:
    if not observed:
        raise ProbeError(f"invariant witness was not reached: {name}")
    return {
        "name": name,
        "reached": True,
        "witness": witness,
    }


@dataclass(frozen=True, slots=True)
class ObserverCase:
    verified_principal: str
    claimed_principal: str
    operation: str
    route: str
    revoked: bool
    expired: bool
    descriptor_matches: bool
    projection_mode: str
    projection_digest_matches: bool
    original_reference_authenticated: bool
    original_bytes_digest_matches: bool
    policy_digest_matches: bool
    visible_channels_match_policy: bool
    reported_complete: bool


def _observer_oracle(case: ObserverCase) -> bool:
    if case.verified_principal != OBSERVER:
        return False
    if case.claimed_principal != case.verified_principal:
        return False
    if case.operation not in OBSERVER_READ_OPERATIONS:
        return False
    if case.route != LITERAL_ROUTE:
        return False
    if case.revoked or case.expired or not case.descriptor_matches:
        return False
    if (
        not case.projection_digest_matches
        or not case.original_reference_authenticated
        or not case.policy_digest_matches
        or not case.visible_channels_match_policy
    ):
        return False
    if case.projection_mode == FULL:
        return case.original_bytes_digest_matches and case.reported_complete
    if case.projection_mode == REDACTED:
        return not case.reported_complete
    return False


def _observer_guard(case: ObserverCase, mutation: str | None) -> bool:
    principal_matches = (
        case.claimed_principal == OBSERVER
        if mutation == "trust_claimed_principal"
        else case.verified_principal == OBSERVER
        and case.claimed_principal == case.verified_principal
    )
    operation_matches = case.operation in OBSERVER_READ_OPERATIONS or (
        case.operation in OBSERVER_PROHIBITED_OPERATIONS
        and mutation == f"{case.operation}_as_read"
    )
    route_matches = case.route == LITERAL_ROUTE or (
        mutation == "wildcard_normalization" and case.route == WILDCARD_ROUTE
    )
    lifecycle_matches = (
        (not case.revoked or mutation == "ignore_revocation")
        and (not case.expired or mutation == "ignore_expiry")
        and (case.descriptor_matches or mutation == "learn_descriptor_from_first_frame")
    )
    projection_matches = (
        case.projection_digest_matches or mutation == "ignore_projection_digest"
    )
    original_reference_matches = (
        case.original_reference_authenticated
        or mutation == "trust_unauthenticated_original_reference"
    )
    policy_matches = (
        case.policy_digest_matches or mutation == "ignore_projection_policy_digest"
    )
    channel_matches = (
        case.visible_channels_match_policy
        or mutation == "ignore_visible_channel_policy"
    )
    if case.projection_mode == FULL:
        projection_honest = (
            case.original_bytes_digest_matches
            or mutation == "full_without_original_bytes"
        ) and (case.reported_complete or mutation == "full_marked_incomplete")
    elif case.projection_mode == REDACTED:
        projection_honest = (
            not case.reported_complete or mutation == "redacted_marked_complete"
        )
    else:
        projection_honest = False
    return (
        principal_matches
        and operation_matches
        and route_matches
        and lifecycle_matches
        and projection_matches
        and original_reference_matches
        and policy_matches
        and channel_matches
        and projection_honest
    )


def _observer_cases() -> list[ObserverCase]:
    return [
        ObserverCase(*values)
        for values in itertools.product(
            (OBSERVER, ATTACKER),
            (OBSERVER, ATTACKER),
            OBSERVER_OPERATIONS,
            (LITERAL_ROUTE, OTHER_ROUTE, WILDCARD_ROUTE),
            (False, True),
            (False, True),
            (False, True),
            (FULL, REDACTED),
            (False, True),
            (False, True),
            (False, True),
            (False, True),
            (False, True),
            (False, True),
        )
    ]


def _kill_observer_mutant(
    cases: Iterable[ObserverCase],
    mutation: str,
) -> dict[str, Any]:
    for case in cases:
        expected = _observer_oracle(case)
        observed = _observer_guard(case, mutation)
        if expected != observed:
            return _executed_logic_mutant_witness(
                name=mutation,
                reason="mutated projection guard disagreed with the exact oracle",
                witness=asdict(case),
                expected=expected,
                observed=observed,
            )
    raise ProbeError(f"observer logic mutant survived: {mutation}")


def _observer_result() -> dict[str, Any]:
    cases = _observer_cases()
    for case in cases:
        if _observer_guard(case, None) != _observer_oracle(case):
            raise ProbeError(
                "baseline observer projection guard differs from its oracle"
            )
    mutation_names = (
        "trust_claimed_principal",
        *(f"{operation}_as_read" for operation in OBSERVER_PROHIBITED_OPERATIONS),
        "wildcard_normalization",
        "ignore_revocation",
        "ignore_expiry",
        "learn_descriptor_from_first_frame",
        "ignore_projection_digest",
        "trust_unauthenticated_original_reference",
        "ignore_projection_policy_digest",
        "ignore_visible_channel_policy",
        "full_without_original_bytes",
        "full_marked_incomplete",
        "redacted_marked_complete",
    )
    admitted = sum(_observer_oracle(case) for case in cases)
    redacted_mismatch = ObserverCase(
        OBSERVER,
        OBSERVER,
        SUBSCRIBE,
        LITERAL_ROUTE,
        False,
        False,
        True,
        REDACTED,
        True,
        False,
        False,
        True,
        True,
        False,
    )
    return {
        "case_count": len(cases),
        "admitted": admitted,
        "rejected": len(cases) - admitted,
        "logic_mutants": [
            _kill_observer_mutant(cases, mutation) for mutation in mutation_names
        ],
        "invariant_witnesses": [
            _invariant_witness(
                "redacted_original_reference_must_authenticate",
                not _observer_oracle(redacted_mismatch),
                asdict(redacted_mismatch),
            ),
            _invariant_witness(
                "literal_read_does_not_authorize_privileged_operations",
                all(
                    not _observer_oracle(
                        replace(
                            redacted_mismatch,
                            operation=operation,
                            original_reference_authenticated=True,
                        )
                    )
                    for operation in OBSERVER_PROHIBITED_OPERATIONS
                ),
                {
                    "operations": list(OBSERVER_PROHIBITED_OPERATIONS),
                    "route": LITERAL_ROUTE,
                },
            ),
        ],
    }


@dataclass(frozen=True, slots=True)
class ResolutionContext:
    ecosystem: str
    host_triple: str
    target_triple: str
    resolver: str
    toolchain: str
    build_profile: str
    cfg: tuple[str, ...]
    effective_features: tuple[str, ...]
    surface_input_manifest_digest: str
    lock_input_digest: str
    config_input_digest: str
    patch_input_digest: str
    environment_input_digest: str
    flags_input_digest: str
    build_script_input_digest: str
    ci_invocation_digest: str
    deployment_invocation_digest: str


@dataclass(frozen=True, slots=True)
class ContractIdentity:
    kind: str
    digest_domain: str
    digest_sha256: str
    compact_hash_algorithm: str
    compact_hash: str


TRUSTED_WIRE_CONTRACT_IDENTITIES = {
    WIRE_08: ContractIdentity(
        kind="frozen_wire_baseline_artifact",
        digest_domain=(
            "sha256-exact-file-bytes:conformance/baseline/v0.8.0/wire_manifest.json"
        ),
        digest_sha256=(
            "b3e4d3e55fadf734e7bbd2471e7537e51cc4f5a094a2275fbacb0fa63dd083e2"
        ),
        compact_hash_algorithm="fnv1a64",
        compact_hash="d1b50a2d8a265276",
    ),
    WIRE_10: ContractIdentity(
        kind="complete_normative_contract",
        digest_domain="ncp.normative-contract.v1",
        digest_sha256=(
            "9cae331742d01e9b164e029aa06c644e6b1886176d0816a6ef883af138355c90"
        ),
        compact_hash_algorithm="fnv1a64",
        compact_hash="163acc57d8a62b66",
    ),
}


@dataclass(frozen=True, slots=True)
class SurfaceKey:
    repository: str
    root: str
    target: str
    features: tuple[str, ...]
    role: str
    activation_profile: str
    target_kind: str
    default_features: bool
    resolution_context_digest: str


@dataclass(frozen=True, slots=True)
class ProviderNode:
    package_id: str
    package_name: str
    source_identity: str
    contract_identity: ContractIdentity | None
    wire: str
    source_revision: str
    artifact_digest: str


@dataclass(frozen=True, slots=True)
class ProviderEdge:
    parent_package_id: str
    child_package_id: str
    resolution_context_digest: str
    target_predicate: str
    dependency_kind: str


@dataclass(frozen=True, slots=True)
class Surface:
    surface_id: str
    key: SurfaceKey
    resolution_context: ResolutionContext
    capability_class: str
    wire: str
    release_state: str
    subject_kind: str
    subject_label: str
    subject_revision: str
    artifact_digest: str
    lifecycle: str
    locator_kind: str
    surface_input_manifest_path: str
    manifest_path: str
    lock_path: str
    runtime_entrypoint: str
    deployment_profile: str
    deployment_domain: str
    closure_root_package_id: str
    ncp_provider_package_id: str
    provider_nodes: tuple[ProviderNode, ...]
    provider_edges: tuple[ProviderEdge, ...]
    executable: bool
    ci_built: bool
    deployment_activated: bool
    process_namespace: str
    credential_set: str
    security_manifest: str
    route_namespace: str
    state_store: str
    configuration_namespace: str
    evidence_namespace: str
    plant_session_namespace: str


@dataclass(frozen=True, slots=True)
class DiscoveryRecord:
    key: SurfaceKey
    resolution_context: ResolutionContext
    surface_id: str | None
    capability_class: str | None
    wire: str | None
    release_state: str | None
    subject_kind: str | None
    subject_label: str | None
    subject_revision: str | None
    artifact_digest: str | None
    lifecycle: str | None
    locator_kind: str | None
    surface_input_manifest_path: str | None
    manifest_path: str | None
    lock_path: str | None
    runtime_entrypoint: str | None
    deployment_profile: str | None
    deployment_domain: str | None
    closure_root_package_id: str | None
    ncp_provider_package_id: str | None
    provider_nodes: tuple[ProviderNode, ...]
    provider_edges: tuple[ProviderEdge, ...]
    process_namespace: str | None
    credential_set: str | None
    security_manifest: str | None
    route_namespace: str | None
    state_store: str | None
    configuration_namespace: str | None
    evidence_namespace: str | None
    plant_session_namespace: str | None
    executable: bool
    ci_built: bool
    deployment_activated: bool
    contains_ncp: bool
    record_digest: str


@dataclass(frozen=True, slots=True)
class SurfaceExclusion:
    key: SurfaceKey
    reason: str
    discovery_record_digest: str
    reviewer_id: str
    disposition: str


@dataclass(frozen=True, slots=True)
class ConsumerInventoryDescriptor:
    """The generated-last repository output; its digest is never an input."""

    repository: str
    descriptor_version: int
    surface_input_manifest_digests: tuple[str, ...]
    resolution_context_digests: tuple[str, ...]
    discovery_record_digests: tuple[str, ...]
    surface_ids: tuple[str, ...]
    surface_digests: tuple[str, ...]
    descriptor_digest: str


@dataclass(frozen=True, slots=True)
class TrustedSubjectAuthorizationState:
    inventory_authority_scope: str
    inventory_state_incarnation: str
    repository: str
    authorization_domain: str
    authorization_state_version: int
    policy_digest: str
    authorized_subject_receipt_digests: tuple[str, ...]
    authorization_evidence_digests: tuple[str, ...]
    state_digest: str


@dataclass(frozen=True, slots=True)
class TrustedScannerAuthorizationState:
    inventory_authority_scope: str
    inventory_state_incarnation: str
    repository: str
    authorization_domain: str
    authorization_state_version: int
    scanner_principal: str
    scanner_executable_digest: str
    scanner_dependency_closure_digest: str
    scanner_policy_digest: str
    scanner_policy_version: int
    scan_receipt_eligibility: str
    authorization_evidence_digests: tuple[str, ...]
    state_digest: str


@dataclass(frozen=True, slots=True)
class ConsumerSurfaceInventoryStateHead:
    inventory_authority_scope: str
    inventory_state_incarnation: str
    state_version: int
    repository: str
    source_tree_identity: str
    trusted_descriptor_version_floor: int
    inventory_authority_status: str
    surface_input_manifest_digests: tuple[str, ...]
    resolution_context_digests: tuple[str, ...]
    discovery_record_digests: tuple[str, ...]
    output_descriptor_digest: str
    trusted_subject_authorization_state_digest: str
    trusted_subject_receipt_digests: tuple[str, ...]
    trusted_scanner_authorization_state_digest: str
    scanner_policy_digest: str
    scanner_policy_version: int
    scan_receipt_eligibility: str
    surface_digests: tuple[str, ...]
    prior_inventory_head_digest: str | None
    state_head_digest: str


@dataclass(frozen=True, slots=True)
class InstalledConsumerSurfaceInventoryStateSelector:
    inventory_authority_scope: str
    inventory_state_incarnation: str
    parent_creation_receipt_digest: str
    repository: str
    selector_version: int
    status: str
    installed_head_digest: str | None
    genesis_consumed: bool
    selector_digest: str


@dataclass(frozen=True, slots=True)
class ConsumerSurfaceInventoryStateCommitReceipt:
    inventory_authority_scope: str
    inventory_state_incarnation: str
    state_version: int
    repository: str
    transition_kind: str
    prior_head_digest: str | None
    installed_head_digest: str
    prior_selector_digest: str
    installed_selector_digest: str
    selector_version: int
    commit_receipt_digest: str


@dataclass(frozen=True, slots=True)
class RepositoryInventoryAuthority:
    descriptor: ConsumerInventoryDescriptor
    head: ConsumerSurfaceInventoryStateHead
    selector: InstalledConsumerSurfaceInventoryStateSelector
    authorized_subject_receipt_digests: tuple[str, ...]
    trusted_subject_authorization_state: TrustedSubjectAuthorizationState
    trusted_scanner_authorization_state: TrustedScannerAuthorizationState
    commit_receipts: tuple[ConsumerSurfaceInventoryStateCommitReceipt, ...]


@dataclass(frozen=True, slots=True)
class ConsumerSurfaceInventoryTransition:
    repository: str
    affected_prior_surface_ids: frozenset[str]
    affected_installed_surface_ids: frozenset[str]
    descriptor: ConsumerInventoryDescriptor
    head: ConsumerSurfaceInventoryStateHead
    selector: InstalledConsumerSurfaceInventoryStateSelector
    commit_receipt: ConsumerSurfaceInventoryStateCommitReceipt
    persisted: bool


def _resolution_context_digest(context: ResolutionContext) -> str:
    return _canonical_digest(asdict(context))


def _context_input_digest(
    ecosystem: str,
    name: str,
    features: tuple[str, ...],
    seed: str,
) -> str:
    return _canonical_digest(
        {
            "fixture_kind": "synthetic_resolution_input",
            "ecosystem": ecosystem,
            "name": name,
            "effective_features": features,
            "seed": seed,
        }
    )


def _cargo_resolution_context(
    features: tuple[str, ...],
    *,
    host_triple: str = "x86_64-unknown-linux-gnu",
    target_triple: str = "x86_64-unknown-linux-gnu",
    resolver: str = "cargo-resolver-2",
    toolchain: str = "rust-1.88.0",
    build_profile: str = "release",
    cfg: tuple[str, ...] = ('target_arch="x86_64"', 'target_os="linux"'),
    seed: str = "baseline-cargo",
) -> ResolutionContext:
    ecosystem = "cargo"
    return ResolutionContext(
        ecosystem=ecosystem,
        host_triple=host_triple,
        target_triple=target_triple,
        resolver=resolver,
        toolchain=toolchain,
        build_profile=build_profile,
        cfg=tuple(sorted(cfg)),
        effective_features=features,
        surface_input_manifest_digest=_context_input_digest(
            ecosystem,
            PYTHON_MIRROR_INPUT_MANIFEST_KEY,
            features,
            seed,
        ),
        lock_input_digest=_context_input_digest(ecosystem, "lock", features, seed),
        config_input_digest=_context_input_digest(ecosystem, "config", features, seed),
        patch_input_digest=_context_input_digest(ecosystem, "patches", features, seed),
        environment_input_digest=_context_input_digest(
            ecosystem, "environment", features, seed
        ),
        flags_input_digest=_context_input_digest(ecosystem, "flags", features, seed),
        build_script_input_digest=_context_input_digest(
            ecosystem, "build-scripts", features, seed
        ),
        ci_invocation_digest=_context_input_digest(
            ecosystem, "ci-invocation", features, seed
        ),
        deployment_invocation_digest=_context_input_digest(
            ecosystem, "deployment-invocation", features, seed
        ),
    )


def _python_mirror_resolution_context(
    features: tuple[str, ...],
    *,
    seed: str = "baseline-python-mirror",
) -> ResolutionContext:
    ecosystem = "python_mirror"
    return ResolutionContext(
        ecosystem=ecosystem,
        host_triple="x86_64-unknown-linux-gnu",
        target_triple="x86_64-unknown-linux-gnu",
        resolver="python-import-graph-v1",
        toolchain="cpython-3.12",
        build_profile="production",
        cfg=("python_implementation=cpython",),
        effective_features=features,
        surface_input_manifest_digest=_context_input_digest(
            ecosystem,
            PYTHON_MIRROR_INPUT_MANIFEST_KEY,
            features,
            seed,
        ),
        lock_input_digest=_context_input_digest(
            ecosystem, "mirror-ref", features, seed
        ),
        config_input_digest=_context_input_digest(
            ecosystem, "backend/requirements.txt", features, seed
        ),
        patch_input_digest=_context_input_digest(ecosystem, "patches", features, seed),
        environment_input_digest=_context_input_digest(
            ecosystem, "environment", features, seed
        ),
        flags_input_digest=_context_input_digest(
            ecosystem, "python-flags", features, seed
        ),
        build_script_input_digest=_context_input_digest(
            ecosystem, "sync-script", features, seed
        ),
        ci_invocation_digest=_context_input_digest(
            ecosystem, "ci-invocation", features, seed
        ),
        deployment_invocation_digest=_context_input_digest(
            ecosystem, "deployment-invocation", features, seed
        ),
    )


def _non_build_resolution_context(features: tuple[str, ...]) -> ResolutionContext:
    ecosystem = "non_build"
    seed = "inactive-non-build"
    return ResolutionContext(
        ecosystem=ecosystem,
        host_triple="not-applicable",
        target_triple="not-applicable",
        resolver="not-applicable",
        toolchain="not-applicable",
        build_profile="not-applicable",
        cfg=(),
        effective_features=features,
        surface_input_manifest_digest=_context_input_digest(
            ecosystem,
            PYTHON_MIRROR_INPUT_MANIFEST_KEY,
            features,
            seed,
        ),
        lock_input_digest=_context_input_digest(ecosystem, "lock", features, seed),
        config_input_digest=_context_input_digest(ecosystem, "config", features, seed),
        patch_input_digest=_context_input_digest(ecosystem, "patches", features, seed),
        environment_input_digest=_context_input_digest(
            ecosystem, "environment", features, seed
        ),
        flags_input_digest=_context_input_digest(ecosystem, "flags", features, seed),
        build_script_input_digest=_context_input_digest(
            ecosystem, "build-scripts", features, seed
        ),
        ci_invocation_digest=_context_input_digest(
            ecosystem, "ci-invocation", features, seed
        ),
        deployment_invocation_digest=_context_input_digest(
            ecosystem, "deployment-invocation", features, seed
        ),
    )


def _default_resolution_context(
    features: tuple[str, ...],
    target_kind: str,
) -> ResolutionContext:
    if target_kind == "none":
        return _non_build_resolution_context(features)
    if target_kind == "module":
        return _python_mirror_resolution_context(features)
    return _cargo_resolution_context(features)


def _surface_key(
    repository: str,
    root: str,
    target: str,
    features: tuple[str, ...],
    role: str,
    activation_profile: str,
    *,
    target_kind: str,
    default_features: bool,
    resolution_context: ResolutionContext | None = None,
) -> SurfaceKey:
    context = resolution_context or _default_resolution_context(
        features,
        target_kind,
    )
    return SurfaceKey(
        repository=repository,
        root=root,
        target=target,
        features=features,
        role=role,
        activation_profile=activation_profile,
        target_kind=target_kind,
        default_features=default_features,
        resolution_context_digest=_resolution_context_digest(context),
    )


def _default_locator(
    key: SurfaceKey,
    context: ResolutionContext,
) -> tuple[str, str, str, str, str]:
    if context.ecosystem == "cargo":
        return (
            "cargo_target",
            SURFACE_INPUT_MANIFEST_PATH,
            f"{key.root}/Cargo.toml",
            "Cargo.lock",
            f"{key.root}/{key.target_kind}/{key.target}",
        )
    if context.ecosystem == "python_mirror":
        return (
            "python_mirror",
            SURFACE_INPUT_MANIFEST_PATH,
            "backend/requirements.txt",
            "ncp/.mirror-ref",
            f"{key.root}/{key.target}.py",
        )
    return ("none", "", "", "", "")


def _surface_scoped_identifier(surface_id: str, label: str) -> str:
    return f"{label}_{_digest(f'{surface_id}:{label}')}"


def _root_package_identity(key: SurfaceKey) -> tuple[str, str]:
    digest = _canonical_digest(
        {
            "repository": key.repository,
            "root": key.root,
        }
    )
    return (f"consumer-root@{digest}", f"consumer-root-{digest}")


def _node(
    package_id: str,
    wire: str,
    revision_seed: str,
    artifact_seed: str,
    *,
    package_name: str | None = None,
    source_identity: str | None = None,
    contract_identity: ContractIdentity | None = None,
) -> ProviderNode:
    resolved_name = (
        package_id.split("@", 1)[0] if package_name is None else package_name
    )
    resolved_source = (
        _digest(
            "official-ncp-provider-source"
            if resolved_name == "ncp-core"
            else f"provider-source:{resolved_name}"
        )
        if source_identity is None
        else source_identity
    )
    exact_wire08_release = (
        package_id == "ncp-core@0.8.0"
        and resolved_name == "ncp-core"
        and wire == WIRE_08
    )
    return ProviderNode(
        package_id=package_id,
        package_name=resolved_name,
        source_identity=resolved_source,
        contract_identity=(
            TRUSTED_WIRE_CONTRACT_IDENTITIES.get(wire)
            if resolved_name == "ncp-core" and contract_identity is None
            else contract_identity
        ),
        wire=wire,
        source_revision=(
            NCP_V08_RELEASE_COMMIT
            if exact_wire08_release
            else _digest(revision_seed)[:40]
        ),
        artifact_digest=(
            NCP_V08_SUBJECT_ARTIFACT_SHA256
            if exact_wire08_release
            else _digest(artifact_seed)
        ),
    )


def _stable_surface_id(key: SurfaceKey) -> str:
    return f"surface_{_canonical_digest(asdict(key))}"


def _discovery_digest(record: DiscoveryRecord) -> str:
    identity = asdict(record)
    identity.pop("record_digest")
    return _canonical_digest(identity)


def _seal_discovery(record: DiscoveryRecord) -> DiscoveryRecord:
    return replace(record, record_digest=_discovery_digest(record))


def _discovery_record(
    key: SurfaceKey,
    provider_nodes: tuple[ProviderNode, ...],
    *,
    provider_edges: tuple[ProviderEdge, ...] = (),
    surface: Surface | None = None,
    executable: bool,
    ci_built: bool,
    deployment_activated: bool,
    contains_ncp: bool,
    closure_root_package_id: str | None = None,
) -> DiscoveryRecord:
    if surface is not None and surface.key != key:
        raise ProbeError("discovery surface and key differ")
    active = executable or ci_built or deployment_activated
    resolution_context = (
        surface.resolution_context
        if surface is not None
        else _default_resolution_context(key.features, key.target_kind)
    )
    ordinary_locator = (
        _default_locator(key, resolution_context)
        if surface is None and active and not contains_ncp
        else (None, None, None, None, None)
    )
    record = DiscoveryRecord(
        key=key,
        resolution_context=resolution_context,
        surface_id=None if surface is None else surface.surface_id,
        capability_class=None if surface is None else surface.capability_class,
        wire=None if surface is None else surface.wire,
        release_state=None if surface is None else surface.release_state,
        subject_kind=None if surface is None else surface.subject_kind,
        subject_label=None if surface is None else surface.subject_label,
        subject_revision=None if surface is None else surface.subject_revision,
        artifact_digest=None if surface is None else surface.artifact_digest,
        lifecycle=None if surface is None else surface.lifecycle,
        locator_kind=(ordinary_locator[0] if surface is None else surface.locator_kind),
        surface_input_manifest_path=(
            ordinary_locator[1]
            if surface is None
            else surface.surface_input_manifest_path
        ),
        manifest_path=(
            ordinary_locator[2] if surface is None else surface.manifest_path
        ),
        lock_path=ordinary_locator[3] if surface is None else surface.lock_path,
        runtime_entrypoint=(
            ordinary_locator[4] if surface is None else surface.runtime_entrypoint
        ),
        deployment_profile=None if surface is None else surface.deployment_profile,
        deployment_domain=None if surface is None else surface.deployment_domain,
        closure_root_package_id=(
            closure_root_package_id
            if surface is None
            else surface.closure_root_package_id
        ),
        ncp_provider_package_id=(
            None if surface is None else surface.ncp_provider_package_id
        ),
        provider_nodes=provider_nodes,
        provider_edges=provider_edges,
        process_namespace=None if surface is None else surface.process_namespace,
        credential_set=None if surface is None else surface.credential_set,
        security_manifest=None if surface is None else surface.security_manifest,
        route_namespace=None if surface is None else surface.route_namespace,
        state_store=None if surface is None else surface.state_store,
        configuration_namespace=(
            None if surface is None else surface.configuration_namespace
        ),
        evidence_namespace=None if surface is None else surface.evidence_namespace,
        plant_session_namespace=(
            None if surface is None else surface.plant_session_namespace
        ),
        executable=executable,
        ci_built=ci_built,
        deployment_activated=deployment_activated,
        contains_ncp=contains_ncp,
        record_digest="",
    )
    return _seal_discovery(record)


def _surface(
    _surface_name: str,
    key: SurfaceKey,
    wire: str,
    dependency_nodes: tuple[ProviderNode, ...],
    *,
    lifecycle: str,
    release_state: str | None = None,
    subject_kind: str | None = None,
    subject_label: str | None = None,
    resolution_context: ResolutionContext | None = None,
    locator_kind: str | None = None,
    surface_input_manifest_path: str | None = None,
    manifest_path: str | None = None,
    lock_path: str | None = None,
    runtime_entrypoint: str | None = None,
    target_predicates: dict[str, str] | None = None,
) -> Surface:
    surface_id = _stable_surface_id(key)
    resolved_context = resolution_context or _default_resolution_context(
        key.features,
        key.target_kind,
    )
    if _resolution_context_digest(resolved_context) != key.resolution_context_digest:
        raise ProbeError("surface key and resolution context differ")
    default_locator = _default_locator(key, resolved_context)
    resolved_locator_kind = locator_kind or default_locator[0]
    resolved_surface_input_manifest_path = (
        surface_input_manifest_path or default_locator[1]
    )
    resolved_manifest_path = manifest_path or default_locator[2]
    resolved_lock_path = lock_path or default_locator[3]
    resolved_runtime_entrypoint = runtime_entrypoint or default_locator[4]
    capability_class = ROLE_CAPABILITY_CLASSES.get(key.role)
    if capability_class is None:
        raise ProbeError("surface role has no closed capability class")
    ncp_nodes = tuple(
        node for node in dependency_nodes if node.package_name == "ncp-core"
    )
    if len(ncp_nodes) != 1:
        raise ProbeError("surface must resolve one exact NCP provider node")
    ncp_provider = ncp_nodes[0]
    root_package_id, root_package_name = _root_package_identity(key)
    primary = _node(
        root_package_id,
        WIRE_NEUTRAL,
        f"{key.repository}:{key.root}:consumer-revision",
        f"{key.repository}:{key.root}:consumer-package",
        package_name=root_package_name,
    )
    provider_nodes = tuple(
        sorted(
            (primary, *dependency_nodes),
            key=lambda node: (
                node.package_id,
                node.wire,
                node.source_revision,
                node.artifact_digest,
            ),
        )
    )
    provider_edges = tuple(
        sorted(
            (
                ProviderEdge(
                    primary.package_id,
                    node.package_id,
                    key.resolution_context_digest,
                    target_predicate=(target_predicates or {}).get(
                        node.package_id,
                        "always",
                    ),
                    dependency_kind="runtime",
                )
                for node in dependency_nodes
            ),
            key=lambda edge: (
                edge.parent_package_id,
                edge.child_package_id,
            ),
        )
    )
    resolved_release_state = release_state or (
        "immutable_release" if wire == WIRE_08 else "candidate"
    )
    resolved_subject_kind = subject_kind or "git_commit"
    resolved_subject_label = subject_label or (
        "v0.8.0" if wire == WIRE_08 else "1.0.0-rc.1"
    )
    return Surface(
        surface_id=surface_id,
        key=key,
        resolution_context=resolved_context,
        capability_class=capability_class,
        wire=wire,
        release_state=resolved_release_state,
        subject_kind=resolved_subject_kind,
        subject_label=resolved_subject_label,
        subject_revision=ncp_provider.source_revision,
        artifact_digest=ncp_provider.artifact_digest,
        lifecycle=lifecycle,
        locator_kind=resolved_locator_kind,
        surface_input_manifest_path=resolved_surface_input_manifest_path,
        manifest_path=resolved_manifest_path,
        lock_path=resolved_lock_path,
        runtime_entrypoint=resolved_runtime_entrypoint,
        deployment_profile=_surface_scoped_identifier(surface_id, "deployment"),
        deployment_domain=f"{key.repository}_deployment_domain",
        closure_root_package_id=primary.package_id,
        ncp_provider_package_id=ncp_provider.package_id,
        provider_nodes=provider_nodes,
        provider_edges=provider_edges,
        executable=True,
        ci_built=True,
        deployment_activated=True,
        process_namespace=_surface_scoped_identifier(surface_id, "process"),
        credential_set=_surface_scoped_identifier(surface_id, "credential"),
        security_manifest=_surface_scoped_identifier(surface_id, "security"),
        route_namespace=_surface_scoped_identifier(surface_id, "routes"),
        state_store=_surface_scoped_identifier(surface_id, "state"),
        configuration_namespace=_surface_scoped_identifier(
            surface_id,
            "configuration",
        ),
        evidence_namespace=_surface_scoped_identifier(surface_id, "evidence"),
        plant_session_namespace=_surface_scoped_identifier(surface_id, "session"),
    )


def _baseline_inventory() -> tuple[
    tuple[DiscoveryRecord, ...],
    tuple[Surface, ...],
    tuple[SurfaceExclusion, ...],
]:
    node08 = _node(
        "ncp-core@0.8.0",
        WIRE_08,
        "ncp-0.8-revision",
        "ncp-0.8-artifact",
    )
    node10 = _node(
        "ncp-core@1.0.0-rc.1#candidate",
        WIRE_10,
        "ncp-1.0-candidate-revision",
        "ncp-1.0-candidate-artifact",
    )
    key08 = _surface_key(
        "galadriel",
        "crates/galadriel-ncp",
        "galadriel_ncp",
        ("zenoh",),
        "observer",
        "legacy-observer",
        target_kind="lib",
        default_features=False,
    )
    key_observer10 = _surface_key(
        "galadriel",
        "crates/galadriel-ncp10",
        "observer",
        ("observer", "wire10"),
        "observer",
        "native-observer",
        target_kind="bin",
        default_features=False,
    )
    key_assessor10 = _surface_key(
        "galadriel",
        "crates/galadriel-ncp10",
        "assessor",
        ("assessor", "wire10"),
        "assessor",
        "native-assessor",
        target_kind="bin",
        default_features=False,
    )
    key_engram10 = _surface_key(
        "engram",
        "backend/neurocontrol",
        "protocol",
        ("mirror", "wire10"),
        "simulation_responder",
        "native-simulation",
        target_kind="module",
        default_features=False,
    )
    surfaces = (
        _surface(
            "observer08",
            key08,
            WIRE_08,
            (node08,),
            lifecycle="historical_executable",
        ),
        _surface(
            "observer10",
            key_observer10,
            WIRE_10,
            (node10,),
            lifecycle="migration_candidate",
        ),
        _surface(
            "assessor10",
            key_assessor10,
            WIRE_10,
            (node10,),
            lifecycle="migration_candidate",
        ),
        _surface(
            "engram10",
            key_engram10,
            WIRE_10,
            (node10,),
            lifecycle="migration_candidate",
            subject_kind="synchronized_mirror",
        ),
    )
    docs_key = _surface_key(
        "galadriel",
        "docs/examples",
        "none",
        (),
        "non_surface",
        "not_activated",
        target_kind="none",
        default_features=False,
    )
    historical_key = _surface_key(
        "galadriel",
        "evidence/frozen-wire08",
        "none",
        (),
        "historical_input",
        "not_activated",
        target_kind="none",
        default_features=False,
    )
    discovery = (
        *(
            _discovery_record(
                surface.key,
                surface.provider_nodes,
                provider_edges=surface.provider_edges,
                surface=surface,
                executable=surface.executable,
                ci_built=surface.ci_built,
                deployment_activated=surface.deployment_activated,
                contains_ncp=True,
            )
            for surface in surfaces
        ),
        _discovery_record(
            docs_key,
            (),
            executable=False,
            ci_built=False,
            deployment_activated=False,
            contains_ncp=False,
        ),
        _discovery_record(
            historical_key,
            (),
            executable=False,
            ci_built=False,
            deployment_activated=False,
            contains_ncp=False,
        ),
    )
    exclusions = (
        SurfaceExclusion(
            docs_key,
            "documentation_only",
            discovery[-2].record_digest,
            "package-tooling-reviewer",
            "accepted_non_surface",
        ),
        SurfaceExclusion(
            historical_key,
            "non_executable_historical",
            discovery[-1].record_digest,
            "package-tooling-reviewer",
            "accepted_non_surface",
        ),
    )
    return discovery, surfaces, exclusions


def _baseline_scan_snapshot() -> dict[SurfaceKey, str]:
    """Bind every synthetic scanner record, not only its selection key."""
    return {record.key: record.record_digest for record in _baseline_inventory()[0]}


def _baseline_deployment_topology() -> dict[str, str]:
    return {
        surface.surface_id: surface.deployment_domain
        for surface in _baseline_inventory()[1]
    }


def _extended_scan_snapshot(
    discovery: tuple[DiscoveryRecord, ...],
) -> dict[SurfaceKey, str]:
    """Build an explicit synthetic scan fixture; this is not a real scan."""
    return {record.key: record.record_digest for record in discovery}


def _extended_deployment_topology(
    surfaces: tuple[Surface, ...],
) -> dict[str, str]:
    """Build an explicit synthetic topology fixture; this is not live evidence."""
    return {surface.surface_id: surface.deployment_domain for surface in surfaces}


def _canonical_relative_path(value: str) -> bool:
    parts = value.split("/")
    return (
        RELATIVE_PATH.fullmatch(value) is not None
        and "\\" not in value
        and all(
            part not in {"", ".", ".."} and PATH_COMPONENT.fullmatch(part) is not None
            for part in parts
        )
        and value == "/".join(parts)
    )


def _validate_key(key: SurfaceKey) -> None:
    if IDENTIFIER.fullmatch(key.repository) is None or not _canonical_relative_path(
        key.root
    ):
        raise ProbeError("surface root is invalid")
    if (
        IDENTIFIER.fullmatch(key.target) is None
        or IDENTIFIER.fullmatch(key.role) is None
        or IDENTIFIER.fullmatch(key.activation_profile) is None
        or key.target_kind
        not in {"bin", "lib", "example", "test", "service", "module", "none"}
        or not isinstance(key.default_features, bool)
        or HEX64.fullmatch(key.resolution_context_digest) is None
    ):
        raise ProbeError("surface target, role, or activation profile is invalid")
    if (
        tuple(sorted(set(key.features))) != key.features
        or len(key.features) > 32
        or any(IDENTIFIER.fullmatch(feature) is None for feature in key.features)
    ):
        raise ProbeError("surface feature set is not canonical and bounded")


def _validate_resolution_context(
    key: SurfaceKey,
    context: ResolutionContext,
) -> None:
    scalar_fields = (
        context.host_triple,
        context.target_triple,
        context.resolver,
        context.toolchain,
        context.build_profile,
    )
    digest_fields = (
        context.surface_input_manifest_digest,
        context.lock_input_digest,
        context.config_input_digest,
        context.patch_input_digest,
        context.environment_input_digest,
        context.flags_input_digest,
        context.build_script_input_digest,
        context.ci_invocation_digest,
        context.deployment_invocation_digest,
    )
    if (
        context.ecosystem not in KNOWN_ECOSYSTEMS
        or any(BOUNDED_TOKEN.fullmatch(value) is None for value in scalar_fields)
        or tuple(sorted(set(context.cfg))) != context.cfg
        or len(context.cfg) > 32
        or any(BOUNDED_CONTEXT_VALUE.fullmatch(value) is None for value in context.cfg)
        or context.effective_features != key.features
        or any(HEX64.fullmatch(value) is None for value in digest_fields)
        or _resolution_context_digest(context) != key.resolution_context_digest
    ):
        raise ProbeError("surface resolution context is invalid or unbound")
    ecosystem_target_kinds = {
        "cargo": {"bin", "lib", "example", "test", "service"},
        "python_mirror": {"module"},
        "non_build": {"none"},
    }
    if key.target_kind not in ecosystem_target_kinds[context.ecosystem]:
        raise ProbeError("surface ecosystem and target kind differ")


def _validate_locator(
    key: SurfaceKey,
    context: ResolutionContext,
    locator_kind: str,
    surface_input_manifest_path: str,
    manifest_path: str,
    lock_path: str,
    runtime_entrypoint: str,
) -> None:
    if (
        locator_kind not in KNOWN_LOCATOR_KINDS
        or not _canonical_relative_path(surface_input_manifest_path)
        or not _canonical_relative_path(manifest_path)
        or not _canonical_relative_path(lock_path)
        or not _canonical_relative_path(runtime_entrypoint)
        or OUTPUT_INVENTORY_DESCRIPTOR_PATH
        in {
            surface_input_manifest_path,
            manifest_path,
            lock_path,
            runtime_entrypoint,
        }
    ):
        raise ProbeError("surface locator is invalid or unbounded")
    if context.ecosystem == "cargo":
        valid = (
            locator_kind == "cargo_target"
            and surface_input_manifest_path == SURFACE_INPUT_MANIFEST_PATH
            and manifest_path == f"{key.root}/Cargo.toml"
            and lock_path.split("/")[-1] == "Cargo.lock"
            and runtime_entrypoint.split("/")[-1] == key.target
        )
    elif context.ecosystem == "python_mirror":
        valid = (
            locator_kind == "python_mirror"
            and surface_input_manifest_path == SURFACE_INPUT_MANIFEST_PATH
            and manifest_path == "backend/requirements.txt"
            and lock_path == "ncp/.mirror-ref"
            and runtime_entrypoint == f"{key.root}/{key.target}.py"
        )
    else:
        valid = False
    if not valid:
        raise ProbeError("surface locator and ecosystem differ")


def _validate_contract_identity(identity: ContractIdentity) -> None:
    if (
        identity.kind not in KNOWN_CONTRACT_IDENTITY_KINDS
        or BOUNDED_CONTEXT_VALUE.fullmatch(identity.digest_domain) is None
        or HEX64.fullmatch(identity.digest_sha256) is None
        or identity.compact_hash_algorithm != "fnv1a64"
        or re.fullmatch(r"[0-9a-f]{16}", identity.compact_hash) is None
    ):
        raise ProbeError("provider contract identity is invalid or unknown")


def _validate_node(node: ProviderNode) -> None:
    if (
        PACKAGE_ID.fullmatch(node.package_id) is None
        or BOUNDED_TOKEN.fullmatch(node.package_name) is None
        or HEX64.fullmatch(node.source_identity) is None
        or node.wire not in KNOWN_PROVIDER_WIRES
        or HEX40.fullmatch(node.source_revision) is None
        or HEX64.fullmatch(node.artifact_digest) is None
    ):
        raise ProbeError("resolved provider identity is invalid")
    if node.package_name == "ncp-core":
        if node.wire not in KNOWN_WIRES or node.contract_identity is None:
            raise ProbeError("NCP provider lacks a typed contract identity")
        _validate_contract_identity(node.contract_identity)
    elif node.contract_identity is not None:
        raise ProbeError("non-NCP provider asserts an NCP contract identity")


def _node_sort_key(node: ProviderNode) -> tuple[str, ...]:
    contract_identity = (
        ("", "", "", "", "")
        if node.contract_identity is None
        else (
            node.contract_identity.kind,
            node.contract_identity.digest_domain,
            node.contract_identity.digest_sha256,
            node.contract_identity.compact_hash_algorithm,
            node.contract_identity.compact_hash,
        )
    )
    return (
        node.package_id,
        node.package_name,
        node.source_identity,
        *contract_identity,
        node.wire,
        node.source_revision,
        node.artifact_digest,
    )


def _edge_sort_key(edge: ProviderEdge) -> tuple[str, ...]:
    return (
        edge.parent_package_id,
        edge.child_package_id,
        edge.resolution_context_digest,
        edge.target_predicate,
        edge.dependency_kind,
    )


def _target_predicate_is_active(
    target_predicate: str,
    context: ResolutionContext,
) -> bool:
    if target_predicate == "always":
        return True
    match = TARGET_CFG_PREDICATE.fullmatch(target_predicate)
    if match is None:
        return False
    key, value = match.groups()
    return f'{key}="{value}"' in context.cfg


def _validate_provider_closure(
    provider_nodes: tuple[ProviderNode, ...],
    provider_edges: tuple[ProviderEdge, ...],
    closure_root_package_id: str | None,
    resolution_context: ResolutionContext,
) -> None:
    resolution_context_digest = _resolution_context_digest(resolution_context)
    if (
        len(provider_nodes) > MAX_PROVIDER_NODES
        or len(provider_edges) > MAX_PROVIDER_EDGES
    ):
        raise ProbeError("provider closure exceeds node or edge bound")
    if not provider_nodes:
        if provider_edges or closure_root_package_id is not None:
            raise ProbeError("empty provider closure has graph identity")
        return
    if provider_nodes != tuple(sorted(provider_nodes, key=_node_sort_key)):
        raise ProbeError("provider closure nodes are not canonical")
    if provider_edges != tuple(sorted(provider_edges, key=_edge_sort_key)):
        raise ProbeError("provider closure edges are not canonical")
    package_ids = [node.package_id for node in provider_nodes]
    if len(package_ids) != len(set(package_ids)):
        raise ProbeError("provider closure contains a duplicate node")
    if closure_root_package_id not in set(package_ids):
        raise ProbeError("provider closure lacks its surface-root node")
    edge_pairs = [
        (edge.parent_package_id, edge.child_package_id) for edge in provider_edges
    ]
    if len(edge_pairs) != len(set(edge_pairs)):
        raise ProbeError("provider closure contains a duplicate edge")
    package_id_set = set(package_ids)
    if any(
        parent not in package_id_set
        or child not in package_id_set
        or parent == child
        or edge.dependency_kind != "runtime"
        or edge.resolution_context_digest != resolution_context_digest
        or not _target_predicate_is_active(
            edge.target_predicate,
            resolution_context,
        )
        for edge, (parent, child) in zip(provider_edges, edge_pairs, strict=True)
    ):
        raise ProbeError("provider edge is invalid or leaves the closure")
    parents: dict[str, set[str]] = {package_id: set() for package_id in package_ids}
    children: dict[str, set[str]] = {package_id: set() for package_id in package_ids}
    for parent, child in edge_pairs:
        parents[child].add(parent)
        children[parent].add(child)
    if parents[closure_root_package_id]:
        raise ProbeError("surface-root provider node has a parent")
    if any(
        not parents[package_id]
        for package_id in package_ids
        if package_id != closure_root_package_id
    ):
        raise ProbeError("provider node is orphaned")
    reached: set[str] = set()
    frontier = [closure_root_package_id]
    while frontier:
        package_id = frontier.pop()
        if package_id in reached:
            continue
        reached.add(package_id)
        frontier.extend(sorted(children[package_id], reverse=True))
    if reached != package_id_set:
        raise ProbeError("provider closure contains an unreachable node")
    indegree = {package_id: len(parents[package_id]) for package_id in package_ids}
    ready = sorted(package_id for package_id, degree in indegree.items() if degree == 0)
    processed = 0
    while ready:
        package_id = ready.pop()
        processed += 1
        for child in sorted(children[package_id], reverse=True):
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)
    if processed != len(package_ids):
        raise ProbeError("provider closure contains a cycle")


def _active(record: DiscoveryRecord) -> bool:
    return record.executable or record.ci_built or record.deployment_activated


def _subject_receipt_key(
    repository: str,
    release_state: str,
    subject_kind: str,
    wire: str,
    subject_label: str,
    node: ProviderNode,
) -> tuple[str, str, str, str, str, str, str]:
    return (
        repository,
        release_state,
        subject_kind,
        wire,
        subject_label,
        node.package_id,
        node.source_identity,
    )


def _default_subject_receipts() -> dict[
    tuple[str, str, str, str, str, str, str],
    tuple[str, str, ContractIdentity],
]:
    node08 = _node(
        "ncp-core@0.8.0",
        WIRE_08,
        "ncp-0.8-revision",
        "ncp-0.8-artifact",
    )
    node10 = _node(
        "ncp-core@1.0.0-rc.1#candidate",
        WIRE_10,
        "ncp-1.0-candidate-revision",
        "ncp-1.0-candidate-artifact",
    )
    receipts = {
        _subject_receipt_key(
            "galadriel",
            "immutable_release",
            "git_commit",
            WIRE_08,
            "v0.8.0",
            node08,
        ): (
            node08.source_revision,
            node08.artifact_digest,
            node08.contract_identity,
        ),
    }
    for repository, subject_kind in (
        ("galadriel", "git_commit"),
        ("haldir", "git_commit"),
        ("engram", "synchronized_mirror"),
    ):
        receipts[
            _subject_receipt_key(
                repository,
                "candidate",
                subject_kind,
                WIRE_10,
                "1.0.0-rc.1",
                node10,
            )
        ] = (
            node10.source_revision,
            node10.artifact_digest,
            node10.contract_identity,
        )
    return receipts


def _authorized_subject_receipts() -> frozenset[
    tuple[
        tuple[str, str, str, str, str, str, str],
        tuple[str, str, ContractIdentity],
    ]
]:
    node10 = _node(
        "ncp-core@1.0.0-rc.1#candidate",
        WIRE_10,
        "ncp-1.0-candidate-revision",
        "ncp-1.0-candidate-artifact",
    )
    future_node = _node(
        "ncp-core@1.0.0",
        WIRE_10,
        "future-v1-release-revision",
        "future-v1-release-artifact",
    )
    source_qualified_node = _node(
        ("git+https://github.com/sepahead/NCP?rev=0123456789abcdef#ncp-core@1.0.0"),
        WIRE_10,
        "source-qualified-provider-revision",
        "source-qualified-provider-artifact",
        package_name="ncp-core",
    )
    repinned_node10 = replace(
        node10,
        source_revision=_digest("new-target-revision")[:40],
        artifact_digest=_digest("new-target-artifact"),
    )
    authorized: set[
        tuple[
            tuple[str, str, str, str, str, str, str],
            tuple[str, str, ContractIdentity],
        ]
    ] = set(_default_subject_receipts().items())
    fixed_subjects = (
        (
            "haldir",
            "immutable_release",
            "published_package",
            WIRE_10,
            "v1.0.0",
            future_node,
        ),
        (
            "prisoma",
            "candidate",
            "git_commit",
            WIRE_10,
            "1.0.0-rc.1",
            source_qualified_node,
        ),
        (
            "galadriel",
            "candidate",
            "git_commit",
            WIRE_10,
            "1.0.0-rc.1",
            repinned_node10,
        ),
        (
            "engram",
            "candidate",
            "synchronized_mirror",
            WIRE_10,
            "1.0.0-rc.1",
            repinned_node10,
        ),
    )
    for repository, state, kind, wire, label, node in fixed_subjects:
        authorized.add(
            (
                _subject_receipt_key(
                    repository,
                    state,
                    kind,
                    wire,
                    label,
                    node,
                ),
                (
                    node.source_revision,
                    node.artifact_digest,
                    node.contract_identity,
                ),
            )
        )
    return frozenset(authorized)


def _validate_surfaces(
    discovery: tuple[DiscoveryRecord, ...],
    surfaces: tuple[Surface, ...],
    exclusions: tuple[SurfaceExclusion, ...],
    *,
    descriptor_version: int = 2,
    descriptor_versions: dict[str, int] | None = None,
    trusted_descriptor_version_floors: dict[str, int] | None = None,
    lock_global_identity: bool = False,
    scan_snapshot: dict[SurfaceKey, str] | None = None,
    deployment_topology: dict[str, str] | None = None,
    subject_receipts: (
        dict[
            tuple[str, str, str, str, str, str, str],
            tuple[str, str, ContractIdentity],
        ]
        | None
    ) = None,
) -> None:
    known_release_states = {"candidate", "immutable_release"}
    known_subject_kinds = {
        "git_commit",
        "published_package",
        "synchronized_mirror",
    }
    known_lifecycles = {
        "historical_executable",
        "migration_candidate",
        "qualified_native",
        "retired",
    }
    repositories = {record.key.repository for record in discovery}
    resolved_descriptor_versions = (
        {repository: descriptor_version for repository in repositories}
        if descriptor_versions is None
        else descriptor_versions
    )
    if set(resolved_descriptor_versions) != repositories or any(
        version not in {1, 2} for version in resolved_descriptor_versions.values()
    ):
        raise ProbeError("descriptor version map is incomplete or unknown")
    resolved_descriptor_floors = (
        {
            repository: TRUSTED_DESCRIPTOR_VERSION_FLOORS.get(repository, 2)
            for repository in repositories
        }
        if trusted_descriptor_version_floors is None
        else trusted_descriptor_version_floors
    )
    if set(resolved_descriptor_floors) != repositories or any(
        not isinstance(floor, int) or isinstance(floor, bool) or floor < 1
        for floor in resolved_descriptor_floors.values()
    ):
        raise ProbeError("trusted descriptor floor map is incomplete or invalid")
    for repository, version in resolved_descriptor_versions.items():
        floor = resolved_descriptor_floors[repository]
        if version < floor:
            raise ProbeError("descriptor version is below its trusted repository floor")
        if (
            version == 1
            and sum(surface.key.repository == repository for surface in surfaces) != 1
        ):
            raise ProbeError("legacy descriptor used for multiple surfaces")
    if (
        len(exclusions) > MAX_EXCLUSIONS
        or len(discovery) > MAX_DISCOVERY_RECORDS
        or len(surfaces) > MAX_SURFACES
    ):
        raise ProbeError("surface inventory exceeds a declared bound")
    trusted_subjects = (
        _default_subject_receipts() if subject_receipts is None else subject_receipts
    )
    trusted_scan_snapshot = (
        _baseline_scan_snapshot() if scan_snapshot is None else scan_snapshot
    )
    trusted_deployment_topology = (
        _baseline_deployment_topology()
        if deployment_topology is None
        else deployment_topology
    )
    authorized_subjects = _authorized_subject_receipts()
    if len(trusted_subjects) > 32 or any(
        item not in authorized_subjects for item in trusted_subjects.items()
    ):
        raise ProbeError("subject receipt store contains an unauthorized receipt")
    discovery_keys = [record.key for record in discovery]
    if len(discovery_keys) != len(set(discovery_keys)):
        raise ProbeError("discovery contains a duplicate surface key")
    record_surface_fields = (
        "surface_id",
        "capability_class",
        "wire",
        "release_state",
        "subject_kind",
        "subject_label",
        "subject_revision",
        "artifact_digest",
        "lifecycle",
        "locator_kind",
        "surface_input_manifest_path",
        "manifest_path",
        "lock_path",
        "runtime_entrypoint",
        "deployment_profile",
        "deployment_domain",
        "ncp_provider_package_id",
        "process_namespace",
        "credential_set",
        "security_manifest",
        "route_namespace",
        "state_store",
        "configuration_namespace",
        "evidence_namespace",
        "plant_session_namespace",
    )
    ordinary_forbidden_fields = tuple(
        field
        for field in record_surface_fields
        if field
        not in {
            "locator_kind",
            "surface_input_manifest_path",
            "manifest_path",
            "lock_path",
            "runtime_entrypoint",
        }
    )
    for record in discovery:
        _validate_key(record.key)
        _validate_resolution_context(record.key, record.resolution_context)
        if not all(
            isinstance(value, bool)
            for value in (
                record.executable,
                record.ci_built,
                record.deployment_activated,
                record.contains_ncp,
            )
        ):
            raise ProbeError("discovery state flags are not Boolean")
        if record.contains_ncp:
            if record.key.target_kind == "none" or any(
                getattr(record, field) is None for field in record_surface_fields
            ):
                raise ProbeError(
                    "NCP discovery record lacks a complete active/retired surface"
                )
            if (
                SURFACE_ID.fullmatch(record.surface_id) is None
                or record.capability_class
                != ROLE_CAPABILITY_CLASSES.get(record.key.role)
                or record.wire not in KNOWN_WIRES
                or record.release_state not in known_release_states
                or record.subject_kind not in known_subject_kinds
                or record.lifecycle not in known_lifecycles
                or not isinstance(record.subject_label, str)
                or not record.subject_label
                or len(record.subject_label) > 128
                or HEX40.fullmatch(record.subject_revision) is None
                or HEX64.fullmatch(record.artifact_digest) is None
                or IDENTIFIER.fullmatch(record.deployment_domain) is None
                or any(
                    SCOPED_IDENTIFIER.fullmatch(getattr(record, field)) is None
                    or getattr(record, field)
                    != _surface_scoped_identifier(
                        record.surface_id,
                        label,
                    )
                    for field, label in SCOPED_SURFACE_FIELDS.items()
                )
            ):
                raise ProbeError(
                    "NCP discovery optional identity is invalid or unbounded"
                )
            _validate_locator(
                record.key,
                record.resolution_context,
                record.locator_kind,
                record.surface_input_manifest_path,
                record.manifest_path,
                record.lock_path,
                record.runtime_entrypoint,
            )
        elif _active(record):
            if any(
                getattr(record, field) is not None
                for field in ordinary_forbidden_fields
            ):
                raise ProbeError("ordinary discovery asserts NCP surface-only identity")
            if (
                record.locator_kind is None
                or record.surface_input_manifest_path is None
                or record.manifest_path is None
                or record.lock_path is None
                or record.runtime_entrypoint is None
            ):
                raise ProbeError("ordinary discovery lacks a bounded locator")
            _validate_locator(
                record.key,
                record.resolution_context,
                record.locator_kind,
                record.surface_input_manifest_path,
                record.manifest_path,
                record.lock_path,
                record.runtime_entrypoint,
            )
        elif (
            any(getattr(record, field) is not None for field in record_surface_fields)
            or record.closure_root_package_id is not None
            or record.provider_nodes
            or record.provider_edges
        ):
            raise ProbeError(
                "inactive non-surface discovery contains forbidden optional state"
            )
        if HEX64.fullmatch(record.record_digest) is None:
            raise ProbeError("discovery-record digest is invalid or unbounded")
        for node in record.provider_nodes:
            _validate_node(node)
        _validate_provider_closure(
            record.provider_nodes,
            record.provider_edges,
            record.closure_root_package_id,
            record.resolution_context,
        )
        if record.contains_ncp:
            expected_root_id, expected_root_name = _root_package_identity(record.key)
            root_node = next(
                node
                for node in record.provider_nodes
                if node.package_id == record.closure_root_package_id
            )
            if (
                root_node.package_id != expected_root_id
                or root_node.package_name != expected_root_name
            ):
                raise ProbeError(
                    "surface-root provider identity is not the complete root digest"
                )
        derived_ncp_nodes = tuple(
            node for node in record.provider_nodes if node.package_name == "ncp-core"
        )
        if record.contains_ncp != bool(derived_ncp_nodes):
            raise ProbeError("discovery NCP classification contradicts its closure")
        if record.contains_ncp and (
            len(derived_ncp_nodes) != 1
            or record.ncp_provider_package_id != derived_ncp_nodes[0].package_id
        ):
            raise ProbeError("discovery does not bind one exact NCP provider")
        if not record.contains_ncp and record.ncp_provider_package_id is not None:
            raise ProbeError("non-NCP discovery asserts an NCP provider")
        if _discovery_digest(record) != record.record_digest:
            raise ProbeError("discovery-record content digest mismatch")
        if record.surface_id is not None and (
            not record.contains_ncp
            or not _active(record)
            and record.lifecycle != "retired"
        ):
            raise ProbeError(
                "bound discovery is neither an active NCP surface nor retired"
            )
    surface_ids = [surface.surface_id for surface in surfaces]
    if len(surface_ids) != len(set(surface_ids)) or any(
        SURFACE_ID.fullmatch(value) is None for value in surface_ids
    ):
        raise ProbeError("surface IDs are invalid or duplicate")
    if set(trusted_deployment_topology) != set(surface_ids) or any(
        IDENTIFIER.fullmatch(domain) is None
        for domain in trusted_deployment_topology.values()
    ):
        raise ProbeError("trusted deployment topology and surfaces differ")
    surface_keys = [surface.key for surface in surfaces]
    if len(surface_keys) != len(set(surface_keys)):
        raise ProbeError("one surface key was assigned more than once")
    provider_identities: dict[tuple[str, str, str], ProviderNode] = {}
    namespace_fields = (
        "process_namespace",
        "credential_set",
        "security_manifest",
        "route_namespace",
        "state_store",
        "configuration_namespace",
        "evidence_namespace",
        "plant_session_namespace",
    )
    cross_wire_fields = (
        "deployment_profile",
        *namespace_fields,
    )
    namespace_wires: dict[str, dict[tuple[str, str], set[str]]] = {
        field: {} for field in cross_wire_fields
    }
    runtime_wires: dict[tuple[str, str], set[str]] = {}
    for surface in surfaces:
        _validate_key(surface.key)
        _validate_resolution_context(surface.key, surface.resolution_context)
        if surface.key.target_kind == "none":
            raise ProbeError("active or retired NCP surface has no target kind")
        if surface.wire not in KNOWN_WIRES:
            raise ProbeError("unknown surface wire")
        if surface.release_state not in known_release_states:
            raise ProbeError("unknown release state")
        if surface.subject_kind not in known_subject_kinds:
            raise ProbeError("unknown subject kind")
        if surface.lifecycle not in known_lifecycles:
            raise ProbeError("unknown lifecycle")
        if surface.capability_class != ROLE_CAPABILITY_CLASSES.get(surface.key.role):
            raise ProbeError("surface role and capability class differ")
        current_candidate = (
            surface.wire == WIRE_10
            and surface.release_state == "candidate"
            and surface.subject_label == "1.0.0-rc.1"
            and surface.subject_kind in {"git_commit", "synchronized_mirror"}
        )
        immutable_subject = (
            surface.release_state == "immutable_release"
            and SEMVER_TAG.fullmatch(surface.subject_label) is not None
            and surface.subject_kind in known_subject_kinds
        )
        if not (current_candidate or immutable_subject):
            raise ProbeError("surface release subject is incoherent")
        if (
            not surface.subject_label
            or len(surface.subject_label) > 128
            or HEX40.fullmatch(surface.subject_revision) is None
            or HEX64.fullmatch(surface.artifact_digest) is None
        ):
            raise ProbeError("surface subject identity is invalid")
        _validate_locator(
            surface.key,
            surface.resolution_context,
            surface.locator_kind,
            surface.surface_input_manifest_path,
            surface.manifest_path,
            surface.lock_path,
            surface.runtime_entrypoint,
        )
        if (
            SCOPED_IDENTIFIER.fullmatch(surface.deployment_profile) is None
            or IDENTIFIER.fullmatch(surface.deployment_domain) is None
            or surface.deployment_domain
            != trusted_deployment_topology.get(surface.surface_id)
            or surface.surface_id != _stable_surface_id(surface.key)
        ):
            raise ProbeError(
                "deployment profile, trusted domain, or stable surface ID is invalid"
            )
        if surface.lifecycle == "retired" and (
            surface.executable or surface.ci_built or surface.deployment_activated
        ):
            raise ProbeError("retired surface remains executable, built, or active")
        if not surface.provider_nodes:
            raise ProbeError("surface has no resolved provider node")
        _validate_provider_closure(
            surface.provider_nodes,
            surface.provider_edges,
            surface.closure_root_package_id,
            surface.resolution_context,
        )
        expected_root_id, expected_root_name = _root_package_identity(surface.key)
        root_node = next(
            node
            for node in surface.provider_nodes
            if node.package_id == surface.closure_root_package_id
        )
        if (
            root_node.package_id != expected_root_id
            or root_node.package_name != expected_root_name
        ):
            raise ProbeError(
                "surface-root provider identity is not the complete root digest"
            )
        if surface.ncp_provider_package_id not in {
            node.package_id for node in surface.provider_nodes
        }:
            raise ProbeError("surface NCP provider is absent from its closure")
        ncp_provider = next(
            node
            for node in surface.provider_nodes
            if node.package_id == surface.ncp_provider_package_id
        )
        if (
            ncp_provider.package_name != "ncp-core"
            or surface.subject_revision != ncp_provider.source_revision
            or surface.artifact_digest != ncp_provider.artifact_digest
            or surface.wire != ncp_provider.wire
            or ncp_provider.contract_identity
            != TRUSTED_WIRE_CONTRACT_IDENTITIES[surface.wire]
        ):
            raise ProbeError("surface subject differs from its NCP provider node")
        receipt_key = _subject_receipt_key(
            surface.key.repository,
            surface.release_state,
            surface.subject_kind,
            surface.wire,
            surface.subject_label,
            ncp_provider,
        )
        if trusted_subjects.get(receipt_key) != (
            surface.subject_revision,
            surface.artifact_digest,
            ncp_provider.contract_identity,
        ):
            raise ProbeError(
                "provider identity lacks its exact trusted subject receipt"
            )
        for node in surface.provider_nodes:
            _validate_node(node)
            if node.wire not in {WIRE_NEUTRAL, surface.wire}:
                raise ProbeError("deployable closure mixes wire identities")
            identity_key = (
                surface.key.repository,
                surface.lock_path,
                node.package_id,
            )
            prior = provider_identities.setdefault(identity_key, node)
            if prior != node:
                raise ProbeError("shared provider package identity is inconsistent")
        for field in cross_wire_fields:
            value = getattr(surface, field)
            if SCOPED_IDENTIFIER.fullmatch(
                value
            ) is None or value != _surface_scoped_identifier(
                surface.surface_id,
                SCOPED_SURFACE_FIELDS[field],
            ):
                raise ProbeError(f"{field} is invalid or unbounded")
            namespace_wires[field].setdefault(
                (surface.deployment_domain, value),
                set(),
            ).add(surface.wire)
        runtime_wires.setdefault(
            (surface.deployment_domain, surface.runtime_entrypoint),
            set(),
        ).add(surface.wire)
    profile_wires: dict[tuple[str, str], set[str]] = {}
    for surface in surfaces:
        profile_wires.setdefault(
            (surface.deployment_domain, surface.key.activation_profile),
            set(),
        ).add(surface.wire)
    if any(len(wires) != 1 for wires in profile_wires.values()):
        raise ProbeError("one activation profile mixes wire identities")
    for field, values in namespace_wires.items():
        if any(len(wires) != 1 for wires in values.values()):
            raise ProbeError(f"{field} mixes incompatible wire identities")
    if any(len(wires) != 1 for wires in runtime_wires.values()):
        raise ProbeError("one runtime entry point mixes incompatible wire identities")
    privilege_fields = (
        "runtime_entrypoint",
        "deployment_profile",
        *namespace_fields,
    )
    for left, right in itertools.combinations(surfaces, 2):
        capability_pair = frozenset((left.capability_class, right.capability_class))
        requires_isolation = (
            capability_pair in ISOLATED_CAPABILITY_PAIRS
            or left.capability_class in PRIVILEGED_CAPABILITIES
            or right.capability_class in PRIVILEGED_CAPABILITIES
        )
        if not requires_isolation or left.deployment_domain != right.deployment_domain:
            continue
        same_build_capability = (
            left.key.repository == right.key.repository
            and left.key.root == right.key.root
            and left.key.target == right.key.target
            and left.key.target_kind == right.key.target_kind
            and left.key.default_features == right.key.default_features
            and left.key.features == right.key.features
            and left.key.resolution_context_digest
            == right.key.resolution_context_digest
        )
        if same_build_capability:
            raise ProbeError(
                "isolated capabilities share one target and effective build closure"
            )
        if left.key.activation_profile == right.key.activation_profile:
            raise ProbeError("isolated capabilities share one activation profile")
        for field in privilege_fields:
            if getattr(left, field) == getattr(right, field):
                raise ProbeError(
                    f"isolated capabilities share {field} privilege boundary"
                )
    records_by_key = {record.key: record for record in discovery}
    exclusion_keys = [exclusion.key for exclusion in exclusions]
    if len(exclusion_keys) != len(set(exclusion_keys)):
        raise ProbeError("surface exclusion keys are duplicate")
    for exclusion in exclusions:
        record = records_by_key.get(exclusion.key)
        if record is None:
            raise ProbeError("surface exclusion does not name a discovered tuple")
        if record.contains_ncp or _active(record):
            raise ProbeError("active or NCP-bearing discovery cannot be excluded")
        if exclusion.reason not in EXCLUSION_REASONS:
            raise ProbeError("surface exclusion reason is unknown")
        if exclusion.discovery_record_digest != record.record_digest:
            raise ProbeError("surface exclusion digest mismatch")
        if (
            IDENTIFIER.fullmatch(exclusion.reviewer_id) is None
            or exclusion.disposition != "accepted_non_surface"
        ):
            raise ProbeError("surface exclusion lacks a bounded reviewer disposition")
    expected_surface_keys = {record.key for record in discovery if record.contains_ncp}
    expected_exclusion_keys = {
        record.key
        for record in discovery
        if not record.contains_ncp and not _active(record)
    }
    if set(surface_keys) != expected_surface_keys:
        raise ProbeError("discovered eligible surfaces and inventory differ")
    if set(exclusion_keys) != expected_exclusion_keys:
        raise ProbeError("discovered non-surfaces and exclusions differ")
    for surface in surfaces:
        record = records_by_key[surface.key]
        exact_binding_fields = (
            "resolution_context",
            "surface_id",
            "capability_class",
            "wire",
            "release_state",
            "subject_kind",
            "subject_label",
            "subject_revision",
            "artifact_digest",
            "lifecycle",
            "locator_kind",
            "surface_input_manifest_path",
            "manifest_path",
            "lock_path",
            "runtime_entrypoint",
            "deployment_profile",
            "deployment_domain",
            "closure_root_package_id",
            "ncp_provider_package_id",
            "provider_nodes",
            "provider_edges",
            "process_namespace",
            "credential_set",
            "security_manifest",
            "route_namespace",
            "state_store",
            "configuration_namespace",
            "evidence_namespace",
            "plant_session_namespace",
            "executable",
            "ci_built",
            "deployment_activated",
        )
        for field in exact_binding_fields:
            if getattr(surface, field) != getattr(record, field):
                raise ProbeError(f"surface {field} differs from independent discovery")
        if not record.contains_ncp:
            raise ProbeError("active surface discovery does not contain NCP")
    if lock_global_identity:
        for repository, lock_path in {
            (surface.key.repository, surface.lock_path) for surface in surfaces
        }:
            wires = {
                node.wire
                for surface in surfaces
                if surface.key.repository == repository
                and surface.lock_path == lock_path
                for node in surface.provider_nodes
                if node.package_name == "ncp-core"
            }
            if len(wires) != 1:
                raise ProbeError("shared lock was assigned one global wire identity")
    discovery_snapshot = {record.key: record.record_digest for record in discovery}
    if discovery_snapshot != trusted_scan_snapshot:
        raise ProbeError(
            "discovery content differs from the explicit synthetic scan snapshot"
        )


def _replace_discovery(
    discovery: tuple[DiscoveryRecord, ...],
    key: SurfaceKey,
    **changes: Any,
) -> tuple[DiscoveryRecord, ...]:
    output = []
    for record in discovery:
        if record.key != key:
            output.append(record)
            continue
        updated = replace(record, **changes, record_digest="")
        output.append(_seal_discovery(updated))
    return tuple(output)


def _bind_discovery_to_surfaces(
    discovery: tuple[DiscoveryRecord, ...],
    surfaces: tuple[Surface, ...],
) -> tuple[DiscoveryRecord, ...]:
    by_key = {surface.key: surface for surface in surfaces}
    output = []
    for record in discovery:
        surface = by_key.get(record.key)
        if surface is None:
            output.append(record)
            continue
        output.append(
            _discovery_record(
                surface.key,
                surface.provider_nodes,
                provider_edges=surface.provider_edges,
                surface=surface,
                executable=surface.executable,
                ci_built=surface.ci_built,
                deployment_activated=surface.deployment_activated,
                contains_ncp=record.contains_ncp,
            )
        )
    return tuple(output)


def _replace_surface_and_discovery(
    discovery: tuple[DiscoveryRecord, ...],
    surfaces: tuple[Surface, ...],
    original: Surface,
    replacement: Surface,
) -> tuple[tuple[DiscoveryRecord, ...], tuple[Surface, ...]]:
    updated_surfaces = tuple(
        replacement if surface.surface_id == original.surface_id else surface
        for surface in surfaces
    )
    updated_discovery = tuple(
        _discovery_record(
            replacement.key,
            replacement.provider_nodes,
            provider_edges=replacement.provider_edges,
            surface=replacement,
            executable=replacement.executable,
            ci_built=replacement.ci_built,
            deployment_activated=replacement.deployment_activated,
            contains_ncp=True,
        )
        if record.key == original.key
        else record
        for record in discovery
    )
    return updated_discovery, updated_surfaces


def _sealed_dataclass(value: Any, digest_field: str) -> Any:
    payload = asdict(value)
    payload.pop(digest_field)
    return replace(value, **{digest_field: _canonical_digest(payload)})


def _repository_inventory_materials(
    repository: str,
    discovery: tuple[DiscoveryRecord, ...],
    surfaces: tuple[Surface, ...],
    exclusions: tuple[SurfaceExclusion, ...],
) -> tuple[
    tuple[DiscoveryRecord, ...],
    tuple[Surface, ...],
    tuple[SurfaceExclusion, ...],
]:
    repository_discovery = tuple(
        sorted(
            (record for record in discovery if record.key.repository == repository),
            key=lambda record: json.dumps(
                asdict(record.key),
                sort_keys=True,
                separators=(",", ":"),
            ),
        )
    )
    repository_surfaces = tuple(
        sorted(
            (surface for surface in surfaces if surface.key.repository == repository),
            key=lambda surface: surface.surface_id,
        )
    )
    repository_exclusions = tuple(
        sorted(
            (
                exclusion
                for exclusion in exclusions
                if exclusion.key.repository == repository
            ),
            key=lambda exclusion: json.dumps(
                asdict(exclusion.key),
                sort_keys=True,
                separators=(",", ":"),
            ),
        )
    )
    return repository_discovery, repository_surfaces, repository_exclusions


def _repository_receipt_digests(
    repository: str,
    subject_receipts: dict[
        tuple[str, str, str, str, str, str, str],
        tuple[str, str, ContractIdentity],
    ],
) -> tuple[str, ...]:
    return tuple(
        sorted(
            _canonical_digest(
                {
                    "key": list(key),
                    "revision": value[0],
                    "artifact": value[1],
                    "contract_identity": asdict(value[2]),
                }
            )
            for key, value in subject_receipts.items()
            if key[0] == repository
        )
    )


def _subject_receipt_digest(
    key: tuple[str, str, str, str, str, str, str],
    value: tuple[str, str, ContractIdentity],
) -> str:
    return _canonical_digest(
        {
            "key": list(key),
            "revision": value[0],
            "artifact": value[1],
            "contract_identity": asdict(value[2]),
        }
    )


def _default_authorized_subject_receipt_digests(repository: str) -> tuple[str, ...]:
    return tuple(
        sorted(
            _subject_receipt_digest(key, value)
            for key, value in _authorized_subject_receipts()
            if key[0] == repository
        )
    )


def _default_scanner_policy_digest(repository: str) -> str:
    return _canonical_digest(
        {
            "kind": "ConsumerSurfaceTrustedScannerPolicy",
            "repository": repository,
            "policy_version": 1,
            "closed_input_rule": "SOURCE_INPUTS_EXCLUDE_OUTPUT_DESCRIPTOR",
        }
    )


def _subject_authorization_state(
    repository: str,
    inventory_authority_scope: str,
    inventory_state_incarnation: str,
    authorized_subject_receipt_digests: tuple[str, ...],
    *,
    authorization_state_version: int,
    authorization_evidence_digests: tuple[str, ...],
) -> TrustedSubjectAuthorizationState:
    state = TrustedSubjectAuthorizationState(
        inventory_authority_scope=inventory_authority_scope,
        inventory_state_incarnation=inventory_state_incarnation,
        repository=repository,
        authorization_domain=(
            f"ncp.consumer-surface-inventory.subject-authorization/{repository}"
        ),
        authorization_state_version=authorization_state_version,
        policy_digest=_canonical_digest(
            {
                "kind": "TrustedSubjectAuthorizationPolicy",
                "repository": repository,
                "policy_version": 1,
                "authorization_rule": "EXACT_INDEPENDENT_RECEIPT_DIGEST",
            }
        ),
        authorized_subject_receipt_digests=authorized_subject_receipt_digests,
        authorization_evidence_digests=authorization_evidence_digests,
        state_digest="",
    )
    return _sealed_dataclass(state, "state_digest")


def _scanner_authorization_state(
    repository: str,
    inventory_authority_scope: str,
    inventory_state_incarnation: str,
    *,
    authorization_state_version: int,
    scanner_policy_digest: str,
    scanner_policy_version: int,
    scan_receipt_eligibility: str,
    authorization_evidence_digests: tuple[str, ...],
) -> TrustedScannerAuthorizationState:
    state = TrustedScannerAuthorizationState(
        inventory_authority_scope=inventory_authority_scope,
        inventory_state_incarnation=inventory_state_incarnation,
        repository=repository,
        authorization_domain=(
            f"ncp.consumer-surface-inventory.scanner-authorization/{repository}"
        ),
        authorization_state_version=authorization_state_version,
        scanner_principal=f"ncp-b03-inventory-scanner-{repository}",
        scanner_executable_digest=_digest(
            f"ncp-b03-inventory-scanner-executable:{repository}"
        ),
        scanner_dependency_closure_digest=_digest(
            f"ncp-b03-inventory-scanner-dependency-closure:{repository}"
        ),
        scanner_policy_digest=scanner_policy_digest,
        scanner_policy_version=scanner_policy_version,
        scan_receipt_eligibility=scan_receipt_eligibility,
        authorization_evidence_digests=authorization_evidence_digests,
        state_digest="",
    )
    return _sealed_dataclass(state, "state_digest")


def _initial_subject_authorization_state(
    repository: str,
    inventory_authority_scope: str,
    inventory_state_incarnation: str,
) -> TrustedSubjectAuthorizationState:
    authorized = _default_authorized_subject_receipt_digests(repository)
    return _subject_authorization_state(
        repository,
        inventory_authority_scope,
        inventory_state_incarnation,
        authorized,
        authorization_state_version=1,
        authorization_evidence_digests=tuple(
            _canonical_digest(
                {
                    "kind": "TrustedSubjectAuthorizationGrantEvidence",
                    "repository": repository,
                    "authorized_subject_receipt_digest": digest,
                    "parent_authority": INVENTORY_PARENT_AUTHORITY,
                }
            )
            for digest in authorized
        ),
    )


def _initial_scanner_authorization_state(
    repository: str,
    inventory_authority_scope: str,
    inventory_state_incarnation: str,
) -> TrustedScannerAuthorizationState:
    return _scanner_authorization_state(
        repository,
        inventory_authority_scope,
        inventory_state_incarnation,
        authorization_state_version=1,
        scanner_policy_digest=_default_scanner_policy_digest(repository),
        scanner_policy_version=1,
        scan_receipt_eligibility="ELIGIBLE",
        authorization_evidence_digests=(
            _canonical_digest(
                {
                    "kind": "TrustedScannerAuthorizationGrantEvidence",
                    "repository": repository,
                    "parent_authority": INVENTORY_PARENT_AUTHORITY,
                }
            ),
        ),
    )


def _validate_subject_authorization_state(
    state: TrustedSubjectAuthorizationState,
) -> None:
    expected_domain = (
        f"ncp.consumer-surface-inventory.subject-authorization/{state.repository}"
    )
    expected_policy_digest = _canonical_digest(
        {
            "kind": "TrustedSubjectAuthorizationPolicy",
            "repository": state.repository,
            "policy_version": 1,
            "authorization_rule": "EXACT_INDEPENDENT_RECEIPT_DIGEST",
        }
    )
    if (
        state.authorization_domain != expected_domain
        or state.authorization_state_version < 1
        or state.policy_digest != expected_policy_digest
        or state.authorized_subject_receipt_digests
        != tuple(sorted(set(state.authorized_subject_receipt_digests)))
        or not set(state.authorized_subject_receipt_digests).issubset(
            _default_authorized_subject_receipt_digests(state.repository)
        )
        or len(state.authorized_subject_receipt_digests) > 32
        or len(state.authorization_evidence_digests) > 64
        or not state.authorization_evidence_digests
        or len(set(state.authorization_evidence_digests))
        != len(state.authorization_evidence_digests)
        or any(
            HEX64.fullmatch(digest) is None
            for digest in (
                *state.authorized_subject_receipt_digests,
                *state.authorization_evidence_digests,
            )
        )
        or _sealed_dataclass(state, "state_digest") != state
    ):
        raise ProbeError("trusted-subject authorization state is not canonical")


def _validate_scanner_authorization_state(
    state: TrustedScannerAuthorizationState,
) -> None:
    expected_domain = (
        f"ncp.consumer-surface-inventory.scanner-authorization/{state.repository}"
    )
    if (
        state.authorization_domain != expected_domain
        or state.authorization_state_version < 1
        or state.scanner_principal != f"ncp-b03-inventory-scanner-{state.repository}"
        or state.scanner_executable_digest
        != _digest(f"ncp-b03-inventory-scanner-executable:{state.repository}")
        or state.scanner_dependency_closure_digest
        != _digest(f"ncp-b03-inventory-scanner-dependency-closure:{state.repository}")
        or state.scanner_policy_digest
        != _default_scanner_policy_digest(state.repository)
        or state.scanner_policy_version < 1
        or state.scan_receipt_eligibility not in SCANNER_RECEIPT_ELIGIBILITY
        or not state.authorization_evidence_digests
        or len(state.authorization_evidence_digests) > 64
        or len(set(state.authorization_evidence_digests))
        != len(state.authorization_evidence_digests)
        or any(
            HEX64.fullmatch(digest) is None
            for digest in state.authorization_evidence_digests
        )
        or _sealed_dataclass(state, "state_digest") != state
    ):
        raise ProbeError("trusted-scanner authorization state is not canonical")


def _descriptor_payload_contains_output(
    value: Any,
    output_digest: str | None = None,
) -> bool:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return OUTPUT_INVENTORY_DESCRIPTOR_PATH in encoded or (
        output_digest is not None and output_digest in encoded
    )


def _build_output_descriptor(
    repository: str,
    discovery: tuple[DiscoveryRecord, ...],
    surfaces: tuple[Surface, ...],
    exclusions: tuple[SurfaceExclusion, ...],
    *,
    descriptor_version: int = 2,
) -> ConsumerInventoryDescriptor:
    (
        repository_discovery,
        repository_surfaces,
        repository_exclusions,
    ) = _repository_inventory_materials(
        repository,
        discovery,
        surfaces,
        exclusions,
    )
    if not repository_discovery or not repository_surfaces:
        raise ProbeError("output descriptor repository inventory is empty")
    pre_descriptor_material = {
        "discovery": [asdict(record) for record in repository_discovery],
        "surfaces": [asdict(surface) for surface in repository_surfaces],
        "exclusions": [asdict(exclusion) for exclusion in repository_exclusions],
    }
    if _descriptor_payload_contains_output(pre_descriptor_material):
        raise ProbeError("output descriptor was bound as an inventory input")
    descriptor = ConsumerInventoryDescriptor(
        repository=repository,
        descriptor_version=descriptor_version,
        surface_input_manifest_digests=tuple(
            sorted(
                {
                    surface.resolution_context.surface_input_manifest_digest
                    for surface in repository_surfaces
                }
            )
        ),
        resolution_context_digests=tuple(
            sorted(
                {
                    surface.key.resolution_context_digest
                    for surface in repository_surfaces
                }
            )
        ),
        discovery_record_digests=tuple(
            sorted(record.record_digest for record in repository_discovery)
        ),
        surface_ids=tuple(
            sorted(surface.surface_id for surface in repository_surfaces)
        ),
        surface_digests=tuple(
            sorted(
                _canonical_digest(asdict(surface)) for surface in repository_surfaces
            )
        ),
        descriptor_digest="",
    )
    return _sealed_dataclass(descriptor, "descriptor_digest")


def _validate_output_descriptor(
    descriptor: ConsumerInventoryDescriptor,
    discovery: tuple[DiscoveryRecord, ...],
    surfaces: tuple[Surface, ...],
    exclusions: tuple[SurfaceExclusion, ...],
) -> None:
    expected = _build_output_descriptor(
        descriptor.repository,
        discovery,
        surfaces,
        exclusions,
        descriptor_version=descriptor.descriptor_version,
    )
    if descriptor != expected:
        raise ProbeError("output inventory descriptor is stale or self-referential")
    payload = asdict(descriptor)
    payload.pop("descriptor_digest")
    if _descriptor_payload_contains_output(payload, descriptor.descriptor_digest):
        raise ProbeError("output descriptor contains its path or its own digest")
    repository_discovery, repository_surfaces, _ = _repository_inventory_materials(
        descriptor.repository,
        discovery,
        surfaces,
        exclusions,
    )
    forbidden_inputs = (
        {surface.key.resolution_context_digest for surface in repository_surfaces}
        | {
            surface.resolution_context.surface_input_manifest_digest
            for surface in repository_surfaces
        }
        | {surface.artifact_digest for surface in repository_surfaces}
        | {record.record_digest for record in repository_discovery}
    )
    if descriptor.descriptor_digest in forbidden_inputs:
        raise ProbeError("output descriptor digest was reused as an earlier input")


def _source_tree_identity(
    repository: str,
    discovery: tuple[DiscoveryRecord, ...],
    surfaces: tuple[Surface, ...],
    exclusions: tuple[SurfaceExclusion, ...],
) -> str:
    repository_discovery, repository_surfaces, repository_exclusions = (
        _repository_inventory_materials(
            repository,
            discovery,
            surfaces,
            exclusions,
        )
    )
    return _canonical_digest(
        {
            "repository": repository,
            "discovery": [asdict(record) for record in repository_discovery],
            "surfaces": [asdict(surface) for surface in repository_surfaces],
            "exclusions": [asdict(exclusion) for exclusion in repository_exclusions],
        }
    )


def _inventory_authority_scope(repository: str) -> str:
    return f"ncp.consumer-surface-inventory/{repository}"


def _initial_inventory_state_incarnation(repository: str) -> str:
    """Return the parent-fixture allocation, not a reusable runtime generator."""
    return _canonical_digest(
        {
            "kind": "ConsumerSurfaceInventoryStateIncarnation",
            "parent_authority": INVENTORY_PARENT_AUTHORITY,
            "repository": repository,
            "allocation_ordinal": 1,
        }
    )


def _inventory_parent_creation_receipt_digest(
    repository: str,
    inventory_authority_scope: str,
    inventory_state_incarnation: str,
) -> str:
    return _canonical_digest(
        {
            "kind": "ConsumerSurfaceInventoryParentCreationReceipt",
            "parent_authority": INVENTORY_PARENT_AUTHORITY,
            "repository": repository,
            "inventory_authority_scope": inventory_authority_scope,
            "inventory_state_incarnation": inventory_state_incarnation,
            "created_selector_status": "UNINITIALIZED",
            "created_selector_version": 0,
        }
    )


def _build_inventory_head(
    descriptor: ConsumerInventoryDescriptor,
    discovery: tuple[DiscoveryRecord, ...],
    surfaces: tuple[Surface, ...],
    exclusions: tuple[SurfaceExclusion, ...],
    subject_receipts: dict[
        tuple[str, str, str, str, str, str, str],
        tuple[str, str, ContractIdentity],
    ],
    *,
    inventory_authority_scope: str,
    inventory_state_incarnation: str,
    state_version: int,
    trusted_descriptor_version_floor: int,
    inventory_authority_status: str,
    authorized_subject_receipt_digests: tuple[str, ...],
    trusted_subject_authorization_state: TrustedSubjectAuthorizationState,
    trusted_scanner_authorization_state: TrustedScannerAuthorizationState,
    scanner_policy_digest: str,
    scanner_policy_version: int,
    scan_receipt_eligibility: str,
    prior_inventory_head_digest: str | None,
) -> ConsumerSurfaceInventoryStateHead:
    _validate_output_descriptor(descriptor, discovery, surfaces, exclusions)
    _validate_subject_authorization_state(trusted_subject_authorization_state)
    _validate_scanner_authorization_state(trusted_scanner_authorization_state)
    if (
        trusted_descriptor_version_floor < 1
        or inventory_authority_status not in INVENTORY_AUTHORITY_STATUSES
        or tuple(sorted(set(authorized_subject_receipt_digests)))
        != authorized_subject_receipt_digests
        or any(
            HEX64.fullmatch(item) is None for item in authorized_subject_receipt_digests
        )
        or HEX64.fullmatch(scanner_policy_digest) is None
        or scanner_policy_version < 1
        or scan_receipt_eligibility not in SCANNER_RECEIPT_ELIGIBILITY
        or trusted_subject_authorization_state.inventory_authority_scope
        != inventory_authority_scope
        or trusted_subject_authorization_state.inventory_state_incarnation
        != inventory_state_incarnation
        or trusted_subject_authorization_state.repository != descriptor.repository
        or trusted_subject_authorization_state.authorized_subject_receipt_digests
        != authorized_subject_receipt_digests
        or _sealed_dataclass(
            trusted_subject_authorization_state,
            "state_digest",
        )
        != trusted_subject_authorization_state
        or trusted_scanner_authorization_state.inventory_authority_scope
        != inventory_authority_scope
        or trusted_scanner_authorization_state.inventory_state_incarnation
        != inventory_state_incarnation
        or trusted_scanner_authorization_state.repository != descriptor.repository
        or trusted_scanner_authorization_state.scanner_policy_digest
        != scanner_policy_digest
        or trusted_scanner_authorization_state.scanner_policy_version
        != scanner_policy_version
        or trusted_scanner_authorization_state.scan_receipt_eligibility
        != scan_receipt_eligibility
        or _sealed_dataclass(
            trusted_scanner_authorization_state,
            "state_digest",
        )
        != trusted_scanner_authorization_state
    ):
        raise ProbeError("inventory policy state is invalid or unbounded")
    repository_discovery, repository_surfaces, _ = _repository_inventory_materials(
        descriptor.repository,
        discovery,
        surfaces,
        exclusions,
    )
    head = ConsumerSurfaceInventoryStateHead(
        inventory_authority_scope=inventory_authority_scope,
        inventory_state_incarnation=inventory_state_incarnation,
        state_version=state_version,
        repository=descriptor.repository,
        source_tree_identity=_source_tree_identity(
            descriptor.repository,
            discovery,
            surfaces,
            exclusions,
        ),
        trusted_descriptor_version_floor=trusted_descriptor_version_floor,
        inventory_authority_status=inventory_authority_status,
        surface_input_manifest_digests=descriptor.surface_input_manifest_digests,
        resolution_context_digests=descriptor.resolution_context_digests,
        discovery_record_digests=tuple(
            sorted(record.record_digest for record in repository_discovery)
        ),
        output_descriptor_digest=descriptor.descriptor_digest,
        trusted_subject_authorization_state_digest=(
            trusted_subject_authorization_state.state_digest
        ),
        trusted_subject_receipt_digests=_repository_receipt_digests(
            descriptor.repository,
            subject_receipts,
        ),
        trusted_scanner_authorization_state_digest=(
            trusted_scanner_authorization_state.state_digest
        ),
        scanner_policy_digest=scanner_policy_digest,
        scanner_policy_version=scanner_policy_version,
        scan_receipt_eligibility=scan_receipt_eligibility,
        surface_digests=tuple(
            sorted(
                _canonical_digest(asdict(surface)) for surface in repository_surfaces
            )
        ),
        prior_inventory_head_digest=prior_inventory_head_digest,
        state_head_digest="",
    )
    return _sealed_dataclass(head, "state_head_digest")


def _selector(
    repository: str,
    *,
    inventory_authority_scope: str,
    inventory_state_incarnation: str,
    parent_creation_receipt_digest: str,
    selector_version: int,
    status: str,
    installed_head_digest: str | None,
    genesis_consumed: bool,
) -> InstalledConsumerSurfaceInventoryStateSelector:
    selector = InstalledConsumerSurfaceInventoryStateSelector(
        inventory_authority_scope=inventory_authority_scope,
        inventory_state_incarnation=inventory_state_incarnation,
        parent_creation_receipt_digest=parent_creation_receipt_digest,
        repository=repository,
        selector_version=selector_version,
        status=status,
        installed_head_digest=installed_head_digest,
        genesis_consumed=genesis_consumed,
        selector_digest="",
    )
    return _sealed_dataclass(selector, "selector_digest")


def _commit_receipt(
    repository: str,
    transition_kind: str,
    prior_head_digest: str | None,
    installed_head_digest: str,
    prior_selector: InstalledConsumerSurfaceInventoryStateSelector,
    installed_selector: InstalledConsumerSurfaceInventoryStateSelector,
) -> ConsumerSurfaceInventoryStateCommitReceipt:
    receipt = ConsumerSurfaceInventoryStateCommitReceipt(
        inventory_authority_scope=installed_selector.inventory_authority_scope,
        inventory_state_incarnation=installed_selector.inventory_state_incarnation,
        state_version=installed_selector.selector_version,
        repository=repository,
        transition_kind=transition_kind,
        prior_head_digest=prior_head_digest,
        installed_head_digest=installed_head_digest,
        prior_selector_digest=prior_selector.selector_digest,
        installed_selector_digest=installed_selector.selector_digest,
        selector_version=installed_selector.selector_version,
        commit_receipt_digest="",
    )
    return _sealed_dataclass(receipt, "commit_receipt_digest")


def _parent_created_uninitialized_inventory_selector(
    repository: str,
    *,
    inventory_state_incarnation: str | None = None,
) -> InstalledConsumerSurfaceInventoryStateSelector:
    inventory_authority_scope = _inventory_authority_scope(repository)
    incarnation = (
        _initial_inventory_state_incarnation(repository)
        if inventory_state_incarnation is None
        else inventory_state_incarnation
    )
    return _selector(
        repository,
        inventory_authority_scope=inventory_authority_scope,
        inventory_state_incarnation=incarnation,
        parent_creation_receipt_digest=_inventory_parent_creation_receipt_digest(
            repository,
            inventory_authority_scope,
            incarnation,
        ),
        selector_version=0,
        status="UNINITIALIZED",
        installed_head_digest=None,
        genesis_consumed=False,
    )


def _genesis_inventory_authority(
    repository: str,
    discovery: tuple[DiscoveryRecord, ...],
    surfaces: tuple[Surface, ...],
    exclusions: tuple[SurfaceExclusion, ...],
    subject_receipts: dict[
        tuple[str, str, str, str, str, str, str],
        tuple[str, str, ContractIdentity],
    ],
    *,
    uninitialized_selector: InstalledConsumerSurfaceInventoryStateSelector
    | None = None,
    trusted_parent_creation_receipt_digests: frozenset[str] | None = None,
    used_inventory_state_incarnations: frozenset[tuple[str, str]] = frozenset(),
) -> RepositoryInventoryAuthority:
    expected_parent_selector = _parent_created_uninitialized_inventory_selector(
        repository
    )
    prior_selector = uninitialized_selector or expected_parent_selector
    trusted_parent_receipts = (
        frozenset({expected_parent_selector.parent_creation_receipt_digest})
        if trusted_parent_creation_receipt_digests is None
        else trusted_parent_creation_receipt_digests
    )
    if (
        prior_selector.repository != repository
        or prior_selector.inventory_authority_scope
        != _inventory_authority_scope(repository)
        or not HEX64.fullmatch(prior_selector.inventory_state_incarnation)
        or prior_selector.parent_creation_receipt_digest
        != _inventory_parent_creation_receipt_digest(
            repository,
            prior_selector.inventory_authority_scope,
            prior_selector.inventory_state_incarnation,
        )
        or prior_selector.parent_creation_receipt_digest not in trusted_parent_receipts
        or (
            prior_selector.inventory_authority_scope,
            prior_selector.inventory_state_incarnation,
        )
        in used_inventory_state_incarnations
        or prior_selector.status != "UNINITIALIZED"
        or prior_selector.selector_version != 0
        or prior_selector.installed_head_digest is not None
        or prior_selector.genesis_consumed
        or _sealed_dataclass(prior_selector, "selector_digest") != prior_selector
    ):
        raise ProbeError(
            "surface inventory genesis lacks a fresh parent-created selector"
        )
    descriptor = _build_output_descriptor(
        repository,
        discovery,
        surfaces,
        exclusions,
    )
    trusted_subject_authorization_state = _initial_subject_authorization_state(
        repository,
        prior_selector.inventory_authority_scope,
        prior_selector.inventory_state_incarnation,
    )
    trusted_scanner_authorization_state = _initial_scanner_authorization_state(
        repository,
        prior_selector.inventory_authority_scope,
        prior_selector.inventory_state_incarnation,
    )
    authorized_subject_receipt_digests = (
        trusted_subject_authorization_state.authorized_subject_receipt_digests
    )
    head = _build_inventory_head(
        descriptor,
        discovery,
        surfaces,
        exclusions,
        subject_receipts,
        inventory_authority_scope=prior_selector.inventory_authority_scope,
        inventory_state_incarnation=prior_selector.inventory_state_incarnation,
        state_version=1,
        trusted_descriptor_version_floor=TRUSTED_DESCRIPTOR_VERSION_FLOORS.get(
            repository,
            2,
        ),
        inventory_authority_status="ACTIVE",
        authorized_subject_receipt_digests=authorized_subject_receipt_digests,
        trusted_subject_authorization_state=(trusted_subject_authorization_state),
        trusted_scanner_authorization_state=(trusted_scanner_authorization_state),
        scanner_policy_digest=(
            trusted_scanner_authorization_state.scanner_policy_digest
        ),
        scanner_policy_version=(
            trusted_scanner_authorization_state.scanner_policy_version
        ),
        scan_receipt_eligibility=(
            trusted_scanner_authorization_state.scan_receipt_eligibility
        ),
        prior_inventory_head_digest=None,
    )
    installed_selector = _selector(
        repository,
        inventory_authority_scope=prior_selector.inventory_authority_scope,
        inventory_state_incarnation=prior_selector.inventory_state_incarnation,
        parent_creation_receipt_digest=(prior_selector.parent_creation_receipt_digest),
        selector_version=1,
        status="INSTALLED",
        installed_head_digest=head.state_head_digest,
        genesis_consumed=True,
    )
    receipt = _commit_receipt(
        repository,
        SURFACE_INVENTORY_GENESIS_FROM_UNINITIALIZED,
        None,
        head.state_head_digest,
        prior_selector,
        installed_selector,
    )
    return RepositoryInventoryAuthority(
        descriptor=descriptor,
        head=head,
        selector=installed_selector,
        authorized_subject_receipt_digests=authorized_subject_receipt_digests,
        trusted_subject_authorization_state=(trusted_subject_authorization_state),
        trusted_scanner_authorization_state=(trusted_scanner_authorization_state),
        commit_receipts=(receipt,),
    )


def _initialize_inventory_authorities(
    discovery: tuple[DiscoveryRecord, ...],
    surfaces: tuple[Surface, ...],
    exclusions: tuple[SurfaceExclusion, ...],
    subject_receipts: dict[
        tuple[str, str, str, str, str, str, str],
        tuple[str, str, ContractIdentity],
    ],
) -> dict[str, RepositoryInventoryAuthority]:
    return {
        repository: _genesis_inventory_authority(
            repository,
            discovery,
            surfaces,
            exclusions,
            subject_receipts,
        )
        for repository in sorted({surface.key.repository for surface in surfaces})
    }


def _validate_authority(
    authority: RepositoryInventoryAuthority,
    discovery: tuple[DiscoveryRecord, ...],
    surfaces: tuple[Surface, ...],
    exclusions: tuple[SurfaceExclusion, ...],
    subject_receipts: dict[
        tuple[str, str, str, str, str, str, str],
        tuple[str, str, ContractIdentity],
    ],
) -> None:
    _validate_output_descriptor(authority.descriptor, discovery, surfaces, exclusions)
    expected_head = _build_inventory_head(
        authority.descriptor,
        discovery,
        surfaces,
        exclusions,
        subject_receipts,
        inventory_authority_scope=authority.head.inventory_authority_scope,
        inventory_state_incarnation=authority.head.inventory_state_incarnation,
        state_version=authority.head.state_version,
        trusted_descriptor_version_floor=(
            authority.head.trusted_descriptor_version_floor
        ),
        inventory_authority_status=authority.head.inventory_authority_status,
        authorized_subject_receipt_digests=(
            authority.authorized_subject_receipt_digests
        ),
        trusted_subject_authorization_state=(
            authority.trusted_subject_authorization_state
        ),
        trusted_scanner_authorization_state=(
            authority.trusted_scanner_authorization_state
        ),
        scanner_policy_digest=authority.head.scanner_policy_digest,
        scanner_policy_version=authority.head.scanner_policy_version,
        scan_receipt_eligibility=authority.head.scan_receipt_eligibility,
        prior_inventory_head_digest=authority.head.prior_inventory_head_digest,
    )
    if authority.head != expected_head:
        raise ProbeError("installed inventory head differs from repository material")
    if (
        authority.selector.status != "INSTALLED"
        or not authority.selector.genesis_consumed
        or authority.head.inventory_authority_scope
        != _inventory_authority_scope(authority.head.repository)
        or authority.selector.inventory_authority_scope
        != authority.head.inventory_authority_scope
        or authority.selector.inventory_state_incarnation
        != authority.head.inventory_state_incarnation
        or authority.selector.parent_creation_receipt_digest
        != _inventory_parent_creation_receipt_digest(
            authority.head.repository,
            authority.head.inventory_authority_scope,
            authority.head.inventory_state_incarnation,
        )
        or authority.head.state_version < 1
        or authority.selector.selector_version != authority.head.state_version
        or (
            authority.head.state_version == 1
            and authority.head.prior_inventory_head_digest is not None
        )
        or (
            authority.head.state_version > 1
            and authority.head.prior_inventory_head_digest is None
        )
        or authority.selector.installed_head_digest != authority.head.state_head_digest
        or authority.head.inventory_authority_status not in INVENTORY_AUTHORITY_STATUSES
        or authority.authorized_subject_receipt_digests
        != tuple(sorted(set(authority.authorized_subject_receipt_digests)))
        or authority.head.trusted_subject_authorization_state_digest
        != authority.trusted_subject_authorization_state.state_digest
        or authority.trusted_subject_authorization_state
        != _sealed_dataclass(
            authority.trusted_subject_authorization_state,
            "state_digest",
        )
        or (
            authority.trusted_subject_authorization_state.authorized_subject_receipt_digests
            != authority.authorized_subject_receipt_digests
        )
        or authority.head.trusted_scanner_authorization_state_digest
        != authority.trusted_scanner_authorization_state.state_digest
        or authority.trusted_scanner_authorization_state
        != _sealed_dataclass(
            authority.trusted_scanner_authorization_state,
            "state_digest",
        )
        or (
            authority.trusted_scanner_authorization_state.scanner_policy_digest
            != authority.head.scanner_policy_digest
        )
        or (
            authority.trusted_scanner_authorization_state.scanner_policy_version
            != authority.head.scanner_policy_version
        )
        or (
            authority.trusted_scanner_authorization_state.scan_receipt_eligibility
            != authority.head.scan_receipt_eligibility
        )
        or (
            authority.head.inventory_authority_status == "ACTIVE"
            and (
                authority.descriptor.descriptor_version
                < authority.head.trusted_descriptor_version_floor
                or authority.head.scan_receipt_eligibility != "ELIGIBLE"
                or not set(authority.head.trusted_subject_receipt_digests).issubset(
                    authority.authorized_subject_receipt_digests
                )
            )
        )
        or (
            authority.descriptor.descriptor_version
            < authority.head.trusted_descriptor_version_floor
            and authority.head.inventory_authority_status
            != "MIGRATION_REQUIRED_DISABLED"
        )
        or (
            authority.head.scan_receipt_eligibility == "REVOKED_DISABLED"
            and authority.head.inventory_authority_status
            != "AUTHORIZATION_REVOKED_DISABLED"
        )
        or (
            not set(authority.head.trusted_subject_receipt_digests).issubset(
                authority.authorized_subject_receipt_digests
            )
            and authority.head.inventory_authority_status
            != "AUTHORIZATION_REVOKED_DISABLED"
        )
        or _sealed_dataclass(authority.selector, "selector_digest")
        != authority.selector
    ):
        raise ProbeError(
            "installed selector is not the sole inventory currentness root"
        )
    if not authority.commit_receipts:
        raise ProbeError("installed inventory lacks a commit receipt")
    latest = authority.commit_receipts[-1]
    if (
        latest.repository != authority.head.repository
        or latest.inventory_authority_scope != authority.head.inventory_authority_scope
        or latest.inventory_state_incarnation
        != authority.head.inventory_state_incarnation
        or latest.state_version != authority.head.state_version
        or latest.installed_head_digest != authority.head.state_head_digest
        or latest.installed_selector_digest != authority.selector.selector_digest
        or latest.selector_version != authority.selector.selector_version
        or latest.transition_kind not in INVENTORY_TRANSITION_KINDS
        or _sealed_dataclass(latest, "commit_receipt_digest") != latest
    ):
        raise ProbeError("inventory commit receipt does not bind installed state")
    genesis = authority.commit_receipts[0]
    if (
        genesis.transition_kind != SURFACE_INVENTORY_GENESIS_FROM_UNINITIALIZED
        or genesis.prior_head_digest is not None
        or genesis.state_version != 1
        or genesis.selector_version != 1
        or any(
            _sealed_dataclass(receipt, "commit_receipt_digest") != receipt
            for receipt in authority.commit_receipts
        )
        or any(
            later.prior_head_digest != earlier.installed_head_digest
            or later.state_version != earlier.state_version + 1
            or later.selector_version != earlier.selector_version + 1
            or later.inventory_authority_scope != earlier.inventory_authority_scope
            or later.inventory_state_incarnation != earlier.inventory_state_incarnation
            for earlier, later in zip(
                authority.commit_receipts,
                authority.commit_receipts[1:],
            )
        )
    ):
        raise ProbeError("inventory receipt chain is reset, rolled back, or forked")


def _derived_inventory_authority_status(
    descriptor_version: int,
    trusted_descriptor_version_floor: int,
    installed_subject_receipt_digests: tuple[str, ...],
    authorized_subject_receipt_digests: tuple[str, ...],
    scan_receipt_eligibility: str,
) -> str:
    if descriptor_version < trusted_descriptor_version_floor:
        return "MIGRATION_REQUIRED_DISABLED"
    if scan_receipt_eligibility != "ELIGIBLE" or not set(
        installed_subject_receipt_digests
    ).issubset(authorized_subject_receipt_digests):
        return "AUTHORIZATION_REVOKED_DISABLED"
    return "ACTIVE"


def _transition_inventory_policy(
    authority: RepositoryInventoryAuthority,
    discovery: tuple[DiscoveryRecord, ...],
    surfaces: tuple[Surface, ...],
    exclusions: tuple[SurfaceExclusion, ...],
    subject_receipts: dict[
        tuple[str, str, str, str, str, str, str],
        tuple[str, str, ContractIdentity],
    ],
    *,
    transition_kind: str,
    expected_selector_digest: str,
    expected_head_digest: str,
    descriptor_version_floor: int | None = None,
    subject_receipt_digest: str | None = None,
) -> tuple[RepositoryInventoryAuthority, ConsumerSurfaceInventoryTransition]:
    _validate_authority(
        authority,
        discovery,
        surfaces,
        exclusions,
        subject_receipts,
    )
    if (
        authority.selector.selector_digest != expected_selector_digest
        or authority.head.state_head_digest != expected_head_digest
    ):
        raise ProbeError("inventory policy transition lost its selector CAS")
    if transition_kind not in (
        INVENTORY_TRANSITION_KINDS
        - {
            SURFACE_INVENTORY_GENESIS_FROM_UNINITIALIZED,
            SURFACE_INVENTORY_REPIN_COMPARE_AND_SWAP,
        }
    ):
        raise ProbeError("inventory policy transition kind is not allowed")
    if authority.head.inventory_authority_status in {"FENCED", "RETIRED"}:
        raise ProbeError("terminal inventory authority cannot transition")

    trusted_floor = authority.head.trusted_descriptor_version_floor
    authorized = set(authority.authorized_subject_receipt_digests)
    scanner_eligibility = authority.head.scan_receipt_eligibility
    forced_status: str | None = None
    known_authorizations = set(
        _default_authorized_subject_receipt_digests(authority.head.repository)
    )

    if transition_kind == DESCRIPTOR_VERSION_FLOOR_ADVANCE:
        if (
            descriptor_version_floor is None
            or descriptor_version_floor <= trusted_floor
            or subject_receipt_digest is not None
        ):
            raise ProbeError("descriptor floor transition is not a strict advance")
        trusted_floor = descriptor_version_floor
    elif transition_kind == TRUSTED_SUBJECT_AUTHORIZATION_GRANT:
        if (
            subject_receipt_digest is None
            or subject_receipt_digest in authorized
            or subject_receipt_digest not in known_authorizations
            or descriptor_version_floor is not None
        ):
            raise ProbeError("trusted-subject grant is unknown or already installed")
        authorized.add(subject_receipt_digest)
    elif transition_kind == TRUSTED_SUBJECT_AUTHORIZATION_REVOKE:
        if (
            subject_receipt_digest is None
            or subject_receipt_digest not in authorized
            or descriptor_version_floor is not None
        ):
            raise ProbeError("trusted-subject revocation target is not installed")
        authorized.remove(subject_receipt_digest)
    elif transition_kind == TRUSTED_SCANNER_AUTHORIZATION_GRANT:
        if (
            scanner_eligibility == "ELIGIBLE"
            or subject_receipt_digest is not None
            or descriptor_version_floor is not None
        ):
            raise ProbeError("trusted-scanner authorization is already installed")
        scanner_eligibility = "ELIGIBLE"
    elif transition_kind == TRUSTED_SCANNER_AUTHORIZATION_REVOKE:
        if (
            scanner_eligibility != "ELIGIBLE"
            or subject_receipt_digest is not None
            or descriptor_version_floor is not None
        ):
            raise ProbeError("trusted-scanner authorization is already revoked")
        scanner_eligibility = "REVOKED_DISABLED"
    elif transition_kind == FENCE_INVENTORY_AUTHORITY:
        if subject_receipt_digest is not None or descriptor_version_floor is not None:
            raise ProbeError("fence transition carries unrelated policy input")
        forced_status = "FENCED"
    elif transition_kind == RETIRE_INVENTORY_AUTHORITY:
        if subject_receipt_digest is not None or descriptor_version_floor is not None:
            raise ProbeError("retire transition carries unrelated policy input")
        forced_status = "RETIRED"

    authorized_tuple = tuple(sorted(authorized))
    status = forced_status or _derived_inventory_authority_status(
        authority.descriptor.descriptor_version,
        trusted_floor,
        _repository_receipt_digests(authority.head.repository, subject_receipts),
        authorized_tuple,
        scanner_eligibility,
    )
    trusted_subject_authorization_state = authority.trusted_subject_authorization_state
    if transition_kind in {
        TRUSTED_SUBJECT_AUTHORIZATION_GRANT,
        TRUSTED_SUBJECT_AUTHORIZATION_REVOKE,
    }:
        trusted_subject_authorization_state = _subject_authorization_state(
            authority.head.repository,
            authority.head.inventory_authority_scope,
            authority.head.inventory_state_incarnation,
            authorized_tuple,
            authorization_state_version=(
                authority.trusted_subject_authorization_state.authorization_state_version
                + 1
            ),
            authorization_evidence_digests=(
                *(
                    authority.trusted_subject_authorization_state.authorization_evidence_digests
                ),
                _canonical_digest(
                    {
                        "kind": f"{transition_kind}Evidence",
                        "repository": authority.head.repository,
                        "prior_authorization_state_digest": (
                            authority.trusted_subject_authorization_state.state_digest
                        ),
                        "subject_receipt_digest": subject_receipt_digest,
                    }
                ),
            ),
        )
    trusted_scanner_authorization_state = authority.trusted_scanner_authorization_state
    if transition_kind in {
        TRUSTED_SCANNER_AUTHORIZATION_GRANT,
        TRUSTED_SCANNER_AUTHORIZATION_REVOKE,
    }:
        trusted_scanner_authorization_state = _scanner_authorization_state(
            authority.head.repository,
            authority.head.inventory_authority_scope,
            authority.head.inventory_state_incarnation,
            authorization_state_version=(
                authority.trusted_scanner_authorization_state.authorization_state_version
                + 1
            ),
            scanner_policy_digest=authority.head.scanner_policy_digest,
            scanner_policy_version=authority.head.scanner_policy_version,
            scan_receipt_eligibility=scanner_eligibility,
            authorization_evidence_digests=(
                *(
                    authority.trusted_scanner_authorization_state.authorization_evidence_digests
                ),
                _canonical_digest(
                    {
                        "kind": f"{transition_kind}Evidence",
                        "repository": authority.head.repository,
                        "prior_authorization_state_digest": (
                            authority.trusted_scanner_authorization_state.state_digest
                        ),
                    }
                ),
            ),
        )
    successor_head = _build_inventory_head(
        authority.descriptor,
        discovery,
        surfaces,
        exclusions,
        subject_receipts,
        inventory_authority_scope=authority.head.inventory_authority_scope,
        inventory_state_incarnation=authority.head.inventory_state_incarnation,
        state_version=authority.head.state_version + 1,
        trusted_descriptor_version_floor=trusted_floor,
        inventory_authority_status=status,
        authorized_subject_receipt_digests=authorized_tuple,
        trusted_subject_authorization_state=(trusted_subject_authorization_state),
        trusted_scanner_authorization_state=(trusted_scanner_authorization_state),
        scanner_policy_digest=authority.head.scanner_policy_digest,
        scanner_policy_version=authority.head.scanner_policy_version,
        scan_receipt_eligibility=scanner_eligibility,
        prior_inventory_head_digest=authority.head.state_head_digest,
    )
    installed_selector = _selector(
        authority.head.repository,
        inventory_authority_scope=authority.selector.inventory_authority_scope,
        inventory_state_incarnation=authority.selector.inventory_state_incarnation,
        parent_creation_receipt_digest=(
            authority.selector.parent_creation_receipt_digest
        ),
        selector_version=authority.selector.selector_version + 1,
        status="INSTALLED",
        installed_head_digest=successor_head.state_head_digest,
        genesis_consumed=True,
    )
    commit_receipt = _commit_receipt(
        authority.head.repository,
        transition_kind,
        authority.head.state_head_digest,
        successor_head.state_head_digest,
        authority.selector,
        installed_selector,
    )
    installed_authority = RepositoryInventoryAuthority(
        descriptor=authority.descriptor,
        head=successor_head,
        selector=installed_selector,
        authorized_subject_receipt_digests=authorized_tuple,
        trusted_subject_authorization_state=(trusted_subject_authorization_state),
        trusted_scanner_authorization_state=(trusted_scanner_authorization_state),
        commit_receipts=(*authority.commit_receipts, commit_receipt),
    )
    _validate_authority(
        installed_authority,
        discovery,
        surfaces,
        exclusions,
        subject_receipts,
    )
    transition = ConsumerSurfaceInventoryTransition(
        repository=authority.head.repository,
        affected_prior_surface_ids=frozenset(),
        affected_installed_surface_ids=frozenset(),
        descriptor=authority.descriptor,
        head=successor_head,
        selector=installed_selector,
        commit_receipt=commit_receipt,
        persisted=True,
    )
    return installed_authority, transition


def _surface_inventory_digest(
    discovery: tuple[DiscoveryRecord, ...],
    surfaces: tuple[Surface, ...],
    exclusions: tuple[SurfaceExclusion, ...],
) -> str:
    canonical_discovery = sorted(
        (asdict(record) for record in discovery),
        key=lambda value: json.dumps(value, sort_keys=True, separators=(",", ":")),
    )
    canonical_surfaces = sorted(
        (asdict(surface) for surface in surfaces),
        key=lambda value: value["surface_id"],
    )
    canonical_exclusions = sorted(
        (asdict(exclusion) for exclusion in exclusions),
        key=lambda value: json.dumps(
            value["key"],
            sort_keys=True,
            separators=(",", ":"),
        ),
    )
    return _canonical_digest(
        {
            "discovery": canonical_discovery,
            "surfaces": canonical_surfaces,
            "exclusions": canonical_exclusions,
        }
    )


def _repository_inventory_digest(
    repository: str,
    discovery: tuple[DiscoveryRecord, ...],
    surfaces: tuple[Surface, ...],
    exclusions: tuple[SurfaceExclusion, ...],
) -> str:
    return _surface_inventory_digest(
        *_repository_inventory_materials(
            repository,
            discovery,
            surfaces,
            exclusions,
        )
    )


def _requested_repin_receipts(
    surfaces: tuple[Surface, ...],
    affected_ids: frozenset[str],
    revision: str,
    artifact: str,
) -> dict[
    tuple[str, str, str, str, str, str, str],
    tuple[str, str, ContractIdentity],
]:
    receipts: dict[
        tuple[str, str, str, str, str, str, str],
        tuple[str, str, ContractIdentity],
    ] = {}
    for surface in surfaces:
        if surface.surface_id not in affected_ids:
            continue
        provider = next(
            node
            for node in surface.provider_nodes
            if node.package_id == surface.ncp_provider_package_id
        )
        updated_provider = replace(
            provider,
            source_revision=revision,
            artifact_digest=artifact,
        )
        key = _subject_receipt_key(
            surface.key.repository,
            surface.release_state,
            surface.subject_kind,
            surface.wire,
            surface.subject_label,
            updated_provider,
        )
        value = (
            updated_provider.source_revision,
            updated_provider.artifact_digest,
            updated_provider.contract_identity,
        )
        prior = receipts.setdefault(key, value)
        if prior != value:
            raise ProbeError("one requested repin subject has conflicting receipts")
    return receipts


def _resolve_repin_group(
    surfaces: tuple[Surface, ...],
    target: str,
) -> frozenset[str]:
    by_id = {surface.surface_id: surface for surface in surfaces}
    target_surface = by_id.get(target)
    if target_surface is None:
        raise ProbeError("repin target does not exist")
    if target_surface.release_state == "immutable_release":
        raise ProbeError("immutable release surface cannot be repinned")
    related_ids = frozenset(
        surface.surface_id
        for surface in surfaces
        if (
            surface.key.repository,
            surface.lock_path,
            surface.ncp_provider_package_id,
        )
        == (
            target_surface.key.repository,
            target_surface.lock_path,
            target_surface.ncp_provider_package_id,
        )
    )
    immutable_related = frozenset(
        surface.surface_id
        for surface in surfaces
        if surface.surface_id in related_ids
        and surface.release_state == "immutable_release"
    )
    if immutable_related:
        raise ProbeError("candidate repin group contains an immutable release subject")
    return related_ids


def _repinned_surface(
    surface: Surface,
    revision: str,
    artifact: str,
    surface_input_manifest_digest: str,
) -> Surface:
    updated_context = replace(
        surface.resolution_context,
        surface_input_manifest_digest=surface_input_manifest_digest,
        lock_input_digest=_canonical_digest(
            {
                "kind": "staged-repin-lock-input",
                "repository": surface.key.repository,
                "lock_path": surface.lock_path,
                "prior_lock_input_digest": (
                    surface.resolution_context.lock_input_digest
                ),
                "provider_revision": revision,
                "provider_artifact": artifact,
            }
        ),
    )
    updated_key = replace(
        surface.key,
        resolution_context_digest=_resolution_context_digest(updated_context),
    )
    updated_surface_id = _stable_surface_id(updated_key)
    updated_nodes = tuple(
        replace(
            node,
            source_revision=revision,
            artifact_digest=artifact,
        )
        if node.package_id == surface.ncp_provider_package_id
        else node
        for node in surface.provider_nodes
    )
    updated_edges = tuple(
        replace(
            edge,
            resolution_context_digest=updated_key.resolution_context_digest,
        )
        for edge in surface.provider_edges
    )
    return replace(
        surface,
        surface_id=updated_surface_id,
        key=updated_key,
        resolution_context=updated_context,
        subject_revision=revision,
        artifact_digest=artifact,
        provider_nodes=updated_nodes,
        provider_edges=updated_edges,
        deployment_profile=_surface_scoped_identifier(
            updated_surface_id,
            "deployment",
        ),
        process_namespace=_surface_scoped_identifier(updated_surface_id, "process"),
        credential_set=_surface_scoped_identifier(updated_surface_id, "credential"),
        security_manifest=_surface_scoped_identifier(updated_surface_id, "security"),
        route_namespace=_surface_scoped_identifier(updated_surface_id, "routes"),
        state_store=_surface_scoped_identifier(updated_surface_id, "state"),
        configuration_namespace=_surface_scoped_identifier(
            updated_surface_id,
            "configuration",
        ),
        evidence_namespace=_surface_scoped_identifier(updated_surface_id, "evidence"),
        plant_session_namespace=_surface_scoped_identifier(
            updated_surface_id,
            "session",
        ),
    )


def _repin(
    discovery: tuple[DiscoveryRecord, ...],
    surfaces: tuple[Surface, ...],
    exclusions: tuple[SurfaceExclusion, ...],
    target: str,
    revision: str,
    artifact: str,
    *,
    inventory_authorities: dict[str, RepositoryInventoryAuthority],
    expected_selector_digest: str,
    expected_head_digest: str,
    expected_descriptor_digest: str,
    expected_inventory_digest: str,
    expected_affected_ids: frozenset[str],
    authorized_new_receipts: dict[
        tuple[str, str, str, str, str, str, str],
        tuple[str, str, ContractIdentity],
    ],
    scan_snapshot: dict[SurfaceKey, str] | None = None,
    deployment_topology: dict[str, str] | None = None,
    subject_receipts: (
        dict[
            tuple[str, str, str, str, str, str, str],
            tuple[str, str, ContractIdentity],
        ]
        | None
    ) = None,
    global_bug: bool,
    persist: bool = True,
) -> tuple[
    tuple[DiscoveryRecord, ...],
    tuple[Surface, ...],
    dict[
        tuple[str, str, str, str, str, str, str],
        tuple[str, str, ContractIdentity],
    ],
    dict[str, RepositoryInventoryAuthority],
    ConsumerSurfaceInventoryTransition,
]:
    trusted_subjects = (
        _default_subject_receipts()
        if subject_receipts is None
        else dict(subject_receipts)
    )
    repositories = {surface.key.repository for surface in surfaces}
    if set(inventory_authorities) != repositories:
        raise ProbeError("repository-local inventory authority set is incomplete")
    for authority in inventory_authorities.values():
        _validate_authority(
            authority,
            discovery,
            surfaces,
            exclusions,
            trusted_subjects,
        )
    _validate_surfaces(
        discovery,
        surfaces,
        exclusions,
        descriptor_versions={
            repository: inventory_authorities[repository].descriptor.descriptor_version
            for repository in repositories
        },
        trusted_descriptor_version_floors={
            repository: (
                inventory_authorities[repository].head.trusted_descriptor_version_floor
            )
            for repository in repositories
        },
        scan_snapshot=scan_snapshot,
        deployment_topology=deployment_topology,
        subject_receipts=trusted_subjects,
    )
    authorized_subjects = _authorized_subject_receipts()
    if any(item not in authorized_subjects for item in authorized_new_receipts.items()):
        raise ProbeError("repin new-subject receipt lacks fixed trust authorization")
    related_ids = _resolve_repin_group(surfaces, target)
    target_surface = next(
        surface for surface in surfaces if surface.surface_id == target
    )
    repository = target_surface.key.repository
    if (
        _repository_inventory_digest(
            repository,
            discovery,
            surfaces,
            exclusions,
        )
        != expected_inventory_digest
    ):
        raise ProbeError("repin repository-local prestate snapshot differs")
    output: list[Surface] = []
    selected_ids: set[str] = set()
    authority = inventory_authorities[repository]
    if (
        authority.selector.selector_digest != expected_selector_digest
        or authority.head.state_head_digest != expected_head_digest
        or authority.descriptor.descriptor_digest != expected_descriptor_digest
        or authority.selector.installed_head_digest != expected_head_digest
    ):
        raise ProbeError(
            "repin compare-and-swap expected local root is stale or sibling"
        )
    if (
        authority.head.inventory_authority_status != "ACTIVE"
        or authority.head.scan_receipt_eligibility != "ELIGIBLE"
    ):
        raise ProbeError("repin inventory authority is disabled")
    if related_ids != set(expected_affected_ids) and not global_bug:
        raise ProbeError("repin affected closure group was not explicitly authorized")
    selected_prestate = tuple(
        surface
        for surface in surfaces
        if surface.surface_id in related_ids
        or (global_bug and surface.release_state == "candidate")
    )
    if any(surface.key.repository != repository for surface in selected_prestate):
        raise ProbeError("repin cannot atomically select more than one repository")
    selected_ids = {surface.surface_id for surface in selected_prestate}
    if selected_ids != set(expected_affected_ids):
        raise ProbeError("repin selected the wrong authorized closure group")
    surface_input_manifest_digest = _canonical_digest(
        {
            "kind": "ConsumerSurfaceInputManifest",
            "repository": repository,
            "prior_manifest_digests": sorted(
                {
                    surface.resolution_context.surface_input_manifest_digest
                    for surface in selected_prestate
                }
            ),
            "actual_inputs": sorted(
                {
                    path
                    for surface in selected_prestate
                    for path in (
                        surface.manifest_path,
                        surface.lock_path,
                        surface.runtime_entrypoint,
                    )
                }
            ),
            "provider_revision": revision,
            "provider_artifact": artifact,
        }
    )
    if _descriptor_payload_contains_output(
        {
            "manifest_digest": surface_input_manifest_digest,
            "surfaces": [asdict(surface) for surface in selected_prestate],
        }
    ):
        raise ProbeError("repin input manifest contains the output descriptor")
    replacement_by_prior_id: dict[str, Surface] = {}
    for surface in surfaces:
        selected = surface.surface_id in selected_ids
        if not selected:
            output.append(surface)
            continue
        replacement_surface = _repinned_surface(
            surface,
            revision,
            artifact,
            surface_input_manifest_digest,
        )
        replacement_by_prior_id[surface.surface_id] = replacement_surface
        output.append(replacement_surface)
    updated_surfaces = tuple(output)
    expected_new_receipts = _requested_repin_receipts(
        updated_surfaces,
        frozenset(
            replacement.surface_id for replacement in replacement_by_prior_id.values()
        ),
        revision,
        artifact,
    )
    if authorized_new_receipts != expected_new_receipts:
        raise ProbeError(
            "repin lacks the exact independently authorized new-subject receipts"
        )
    if not {
        _subject_receipt_digest(key, value)
        for key, value in authorized_new_receipts.items()
    }.issubset(authority.authorized_subject_receipt_digests):
        raise ProbeError(
            "repin subject is not authorized by the installed inventory root"
        )
    for surface in updated_surfaces:
        if surface.surface_id not in {
            replacement.surface_id for replacement in replacement_by_prior_id.values()
        }:
            continue
        provider = next(
            node
            for node in surface.provider_nodes
            if node.package_id == surface.ncp_provider_package_id
        )
        trusted_subjects[
            _subject_receipt_key(
                surface.key.repository,
                surface.release_state,
                surface.subject_kind,
                surface.wire,
                surface.subject_label,
                provider,
            )
        ] = (
            provider.source_revision,
            provider.artifact_digest,
            provider.contract_identity,
        )
    if {
        key: trusted_subjects[key] for key in authorized_new_receipts
    } != authorized_new_receipts:
        raise ProbeError("repin did not install exact authorized subject receipts")
    updated_discovery = tuple(
        _discovery_record(
            replacement_by_prior_id[record.surface_id].key,
            replacement_by_prior_id[record.surface_id].provider_nodes,
            provider_edges=replacement_by_prior_id[record.surface_id].provider_edges,
            surface=replacement_by_prior_id[record.surface_id],
            executable=record.executable,
            ci_built=record.ci_built,
            deployment_activated=record.deployment_activated,
            contains_ncp=record.contains_ncp,
        )
        if record.surface_id in replacement_by_prior_id
        else record
        for record in discovery
    )
    _validate_surfaces(
        updated_discovery,
        updated_surfaces,
        exclusions,
        # This second pass checks the internally constructed candidate snapshot.
        # It is not the independent post-repin rescan that N07 must supply.
        scan_snapshot=_extended_scan_snapshot(updated_discovery),
        deployment_topology=_extended_deployment_topology(updated_surfaces),
        subject_receipts=trusted_subjects,
        descriptor_versions={
            repository_name: (
                inventory_authorities[repository_name].descriptor.descriptor_version
            )
            for repository_name in repositories
        },
        trusted_descriptor_version_floors={
            repository_name: (
                inventory_authorities[
                    repository_name
                ].head.trusted_descriptor_version_floor
            )
            for repository_name in repositories
        },
    )
    descriptor = _build_output_descriptor(
        repository,
        updated_discovery,
        updated_surfaces,
        exclusions,
    )
    successor_head = _build_inventory_head(
        descriptor,
        updated_discovery,
        updated_surfaces,
        exclusions,
        trusted_subjects,
        inventory_authority_scope=authority.head.inventory_authority_scope,
        inventory_state_incarnation=authority.head.inventory_state_incarnation,
        state_version=authority.head.state_version + 1,
        trusted_descriptor_version_floor=(
            authority.head.trusted_descriptor_version_floor
        ),
        inventory_authority_status="ACTIVE",
        authorized_subject_receipt_digests=(
            authority.authorized_subject_receipt_digests
        ),
        trusted_subject_authorization_state=(
            authority.trusted_subject_authorization_state
        ),
        trusted_scanner_authorization_state=(
            authority.trusted_scanner_authorization_state
        ),
        scanner_policy_digest=authority.head.scanner_policy_digest,
        scanner_policy_version=authority.head.scanner_policy_version,
        scan_receipt_eligibility=authority.head.scan_receipt_eligibility,
        prior_inventory_head_digest=authority.head.state_head_digest,
    )
    installed_selector = _selector(
        repository,
        inventory_authority_scope=authority.selector.inventory_authority_scope,
        inventory_state_incarnation=authority.selector.inventory_state_incarnation,
        parent_creation_receipt_digest=(
            authority.selector.parent_creation_receipt_digest
        ),
        selector_version=authority.selector.selector_version + 1,
        status="INSTALLED",
        installed_head_digest=successor_head.state_head_digest,
        genesis_consumed=True,
    )
    commit_receipt = _commit_receipt(
        repository,
        SURFACE_INVENTORY_REPIN_COMPARE_AND_SWAP,
        authority.head.state_head_digest,
        successor_head.state_head_digest,
        authority.selector,
        installed_selector,
    )
    transition = ConsumerSurfaceInventoryTransition(
        repository=repository,
        affected_prior_surface_ids=frozenset(replacement_by_prior_id),
        affected_installed_surface_ids=frozenset(
            surface.surface_id for surface in replacement_by_prior_id.values()
        ),
        descriptor=descriptor,
        head=successor_head,
        selector=installed_selector,
        commit_receipt=commit_receipt,
        persisted=persist,
    )
    if not persist:
        raise ProbeError("repin staged state was not installed by repository-local CAS")
    updated_authorities = dict(inventory_authorities)
    updated_authorities[repository] = RepositoryInventoryAuthority(
        descriptor=descriptor,
        head=successor_head,
        selector=installed_selector,
        authorized_subject_receipt_digests=(
            authority.authorized_subject_receipt_digests
        ),
        trusted_subject_authorization_state=(
            authority.trusted_subject_authorization_state
        ),
        trusted_scanner_authorization_state=(
            authority.trusted_scanner_authorization_state
        ),
        commit_receipts=(*authority.commit_receipts, commit_receipt),
    )
    if (
        inventory_authorities[repository].selector.selector_digest
        != expected_selector_digest
    ):
        raise ProbeError("repin lost its final selector compare-and-swap")
    _validate_authority(
        updated_authorities[repository],
        updated_discovery,
        updated_surfaces,
        exclusions,
        trusted_subjects,
    )
    return (
        updated_discovery,
        updated_surfaces,
        trusted_subjects,
        updated_authorities,
        transition,
    )


def _surface_result() -> dict[str, Any]:
    discovery, surfaces, exclusions = _baseline_inventory()
    _validate_surfaces(discovery, surfaces, exclusions)

    def validate_synthetic_fixture(
        fixture_discovery: tuple[DiscoveryRecord, ...],
        fixture_surfaces: tuple[Surface, ...],
        fixture_exclusions: tuple[SurfaceExclusion, ...],
        **options: Any,
    ) -> None:
        options.setdefault(
            "scan_snapshot",
            _extended_scan_snapshot(fixture_discovery),
        )
        options.setdefault(
            "deployment_topology",
            _extended_deployment_topology(fixture_surfaces),
        )
        _validate_surfaces(
            fixture_discovery,
            fixture_surfaces,
            fixture_exclusions,
            **options,
        )

    observer08, observer10, assessor10, engram10 = surfaces
    duplicate_key = surfaces + (
        replace(
            observer10,
            surface_id="observer10_copy",
        ),
    )
    duplicate_id = (
        observer08,
        observer10,
        replace(assessor10, surface_id=observer10.surface_id),
        engram10,
    )
    node08 = next(
        node
        for node in observer08.provider_nodes
        if node.package_id == observer08.ncp_provider_package_id
    )
    node10 = next(
        node
        for node in observer10.provider_nodes
        if node.package_id == observer10.ncp_provider_package_id
    )
    mixed_observer10 = replace(
        observer10,
        provider_nodes=tuple(
            sorted((*observer10.provider_nodes, node08), key=_node_sort_key)
        ),
        provider_edges=tuple(
            sorted(
                (
                    *observer10.provider_edges,
                    ProviderEdge(
                        observer10.closure_root_package_id,
                        node08.package_id,
                        observer10.key.resolution_context_digest,
                        target_predicate="always",
                        dependency_kind="runtime",
                    ),
                ),
                key=_edge_sort_key,
            )
        ),
    )
    mixed_closure = (
        observer08,
        mixed_observer10,
        assessor10,
        engram10,
    )
    mixed_discovery = _bind_discovery_to_surfaces(discovery, mixed_closure)
    orphan_node = _node(
        "ncp-extra@1.0.0-rc.1",
        WIRE_10,
        "orphan-revision",
        "orphan-artifact",
    )
    orphan_edge = (
        observer08,
        replace(
            observer10,
            provider_nodes=tuple(
                sorted(
                    (*observer10.provider_nodes, orphan_node),
                    key=_node_sort_key,
                )
            ),
        ),
        assessor10,
        engram10,
    )
    orphan_discovery = _bind_discovery_to_surfaces(discovery, orphan_edge)
    duplicate_provider = (
        observer08,
        replace(
            observer10,
            provider_nodes=tuple(
                sorted(
                    (
                        *observer10.provider_nodes,
                        observer10.provider_nodes[-1],
                    ),
                    key=_node_sort_key,
                )
            ),
        ),
        assessor10,
        engram10,
    )
    duplicate_provider_discovery = _bind_discovery_to_surfaces(
        discovery,
        duplicate_provider,
    )
    duplicate_edge = (
        observer08,
        replace(
            observer10,
            provider_edges=tuple(
                sorted(
                    (
                        *observer10.provider_edges,
                        observer10.provider_edges[0],
                    ),
                    key=_edge_sort_key,
                )
            ),
        ),
        assessor10,
        engram10,
    )
    duplicate_edge_discovery = _bind_discovery_to_surfaces(
        discovery,
        duplicate_edge,
    )
    cycle_node = _node(
        "ncp-cycle-fixture@1.0.0-rc.1",
        WIRE_10,
        "cycle-revision",
        "cycle-artifact",
    )
    provider_cycle = (
        observer08,
        replace(
            observer10,
            provider_nodes=tuple(
                sorted(
                    (*observer10.provider_nodes, cycle_node),
                    key=_node_sort_key,
                )
            ),
            provider_edges=tuple(
                sorted(
                    (
                        *observer10.provider_edges,
                        ProviderEdge(
                            node10.package_id,
                            cycle_node.package_id,
                            observer10.key.resolution_context_digest,
                            target_predicate="always",
                            dependency_kind="runtime",
                        ),
                        ProviderEdge(
                            cycle_node.package_id,
                            node10.package_id,
                            observer10.key.resolution_context_digest,
                            target_predicate="always",
                            dependency_kind="runtime",
                        ),
                    ),
                    key=_edge_sort_key,
                )
            ),
        ),
        assessor10,
        engram10,
    )
    provider_cycle_discovery = _bind_discovery_to_surfaces(
        discovery,
        provider_cycle,
    )
    inconsistent_node = replace(
        node10,
        artifact_digest=_digest("inconsistent-shared-provider"),
    )
    inconsistent_surfaces = (
        observer08,
        observer10,
        replace(
            assessor10,
            provider_nodes=tuple(
                sorted(
                    (
                        inconsistent_node
                        if node.package_id == assessor10.ncp_provider_package_id
                        else node
                        for node in assessor10.provider_nodes
                    ),
                    key=_node_sort_key,
                )
            ),
        ),
        engram10,
    )
    inconsistent_discovery = _bind_discovery_to_surfaces(
        discovery,
        inconsistent_surfaces,
    )
    mixed_profile_key = replace(
        observer10.key,
        activation_profile=observer08.key.activation_profile,
    )
    mixed_profile_surface = replace(
        observer10,
        surface_id=_stable_surface_id(mixed_profile_key),
        key=mixed_profile_key,
    )
    mixed_profile_discovery, mixed_profile = _replace_surface_and_discovery(
        discovery,
        surfaces,
        observer10,
        mixed_profile_surface,
    )
    unknown_node = replace(node10, wire="unknown")
    unknown_wire = (
        observer08,
        replace(observer10, wire="unknown", provider_nodes=(unknown_node,)),
        assessor10,
        engram10,
    )
    unknown_release = (
        observer08,
        replace(observer10, release_state="unknown"),
        assessor10,
        engram10,
    )
    unknown_subject = (
        observer08,
        replace(observer10, subject_kind="unknown"),
        assessor10,
        engram10,
    )
    unknown_lifecycle = (
        observer08,
        replace(observer10, lifecycle="unknown"),
        assessor10,
        engram10,
    )
    invalid_id = (
        observer08,
        replace(observer10, surface_id=""),
        assessor10,
        engram10,
    )
    noncanonical_features = (
        observer08,
        replace(
            observer10,
            key=replace(
                observer10.key,
                features=("wire10", "observer"),
            ),
        ),
        assessor10,
        engram10,
    )
    invalid_provider = (
        observer08,
        replace(
            observer10,
            provider_nodes=(
                observer10.provider_nodes[0],
                replace(node10, artifact_digest="0"),
            ),
        ),
        assessor10,
        engram10,
    )
    invalid_subject = (
        observer08,
        replace(observer10, subject_revision="main"),
        assessor10,
        engram10,
    )
    retired = (
        replace(
            observer08,
            lifecycle="retired",
            executable=False,
            ci_built=False,
            deployment_activated=False,
        ),
        observer10,
        assessor10,
        engram10,
    )
    swapped_ids = (
        observer08,
        replace(observer10, surface_id=assessor10.surface_id),
        replace(assessor10, surface_id=observer10.surface_id),
        engram10,
    )
    swapped_id_discovery = _bind_discovery_to_surfaces(discovery, swapped_ids)
    subject_provider_drift = (
        observer08,
        replace(
            observer10,
            subject_revision=_digest("forged-subject-revision")[:40],
            artifact_digest=_digest("forged-subject-artifact"),
        ),
        assessor10,
        engram10,
    )
    subject_provider_drift_discovery = _bind_discovery_to_surfaces(
        discovery,
        subject_provider_drift,
    )
    release_label_mismatch = (
        observer08,
        replace(
            observer10,
            release_state="immutable_release",
            subject_label="v0.8.0",
        ),
        assessor10,
        engram10,
    )
    release_label_mismatch_discovery = _bind_discovery_to_surfaces(
        discovery,
        release_label_mismatch,
    )
    executable_non_ncp_discovery = _replace_discovery(
        discovery,
        exclusions[0].key,
        executable=True,
    )
    namespace_relabel = (
        observer08,
        replace(
            observer10,
            process_namespace="arbitrary_process",
        ),
        assessor10,
        engram10,
    )
    runtime_relabel = (
        observer08,
        replace(
            observer10,
            runtime_entrypoint="bin/arbitrary-observer",
        ),
        assessor10,
        engram10,
    )
    contains_ncp_flip = _replace_discovery(
        discovery,
        observer10.key,
        contains_ncp=False,
    )
    ncp_free_key = replace(
        observer10.key,
        repository="invented",
        root="crates/no-ncp",
    )
    ncp_free_root = _node(
        f"{_stable_surface_id(ncp_free_key)}@consumer",
        WIRE_10,
        "invented-consumer-revision",
        "invented-consumer-artifact",
    )
    ncp_free_surface = replace(
        observer10,
        surface_id=_stable_surface_id(ncp_free_key),
        key=ncp_free_key,
        subject_revision=ncp_free_root.source_revision,
        artifact_digest=ncp_free_root.artifact_digest,
        manifest_path=f"{ncp_free_key.root}/Cargo.toml",
        runtime_entrypoint=f"{ncp_free_key.root}/bin/{ncp_free_key.target}",
        closure_root_package_id=ncp_free_root.package_id,
        ncp_provider_package_id=ncp_free_root.package_id,
        provider_nodes=(ncp_free_root,),
        provider_edges=(),
    )
    ncp_free_discovery, ncp_free_surfaces = _replace_surface_and_discovery(
        discovery,
        surfaces,
        observer10,
        ncp_free_surface,
    )
    ncp_free_discovery = _replace_discovery(
        ncp_free_discovery,
        ncp_free_key,
        contains_ncp=False,
    )
    frozen_drift_node = replace(
        node08,
        source_revision=_digest("forged-frozen-revision")[:40],
        artifact_digest=_digest("forged-frozen-artifact"),
    )
    frozen_drift_surface = replace(
        observer08,
        subject_revision=frozen_drift_node.source_revision,
        artifact_digest=frozen_drift_node.artifact_digest,
        provider_nodes=tuple(
            sorted(
                (
                    frozen_drift_node
                    if node.package_id == observer08.ncp_provider_package_id
                    else node
                    for node in observer08.provider_nodes
                ),
                key=_node_sort_key,
            )
        ),
    )
    frozen_drift_surfaces = (
        frozen_drift_surface,
        observer10,
        assessor10,
        engram10,
    )
    frozen_drift_discovery = _bind_discovery_to_surfaces(
        discovery,
        frozen_drift_surfaces,
    )
    invalid_role_key = replace(assessor10.key, role="assessor_shadow")
    invalid_role_surface = replace(
        assessor10,
        surface_id=_stable_surface_id(invalid_role_key),
        key=invalid_role_key,
    )
    invalid_role_discovery, invalid_role_surfaces = _replace_surface_and_discovery(
        discovery,
        surfaces,
        assessor10,
        invalid_role_surface,
    )
    graph_fixture_root = _node(
        "graph-fixture-root@1",
        WIRE_10,
        "graph-fixture-root-revision",
        "graph-fixture-root-artifact",
    )
    graph_fixture_a = _node(
        "graph-fixture-a@1",
        WIRE_10,
        "graph-fixture-a-revision",
        "graph-fixture-a-artifact",
    )
    graph_fixture_b = _node(
        "graph-fixture-b@1",
        WIRE_10,
        "graph-fixture-b-revision",
        "graph-fixture-b-artifact",
    )
    graph_fixture_nodes = tuple(
        sorted(
            (graph_fixture_root, graph_fixture_a, graph_fixture_b),
            key=_node_sort_key,
        )
    )
    graph_fixture_edges = tuple(
        sorted(
            (
                ProviderEdge(
                    graph_fixture_root.package_id,
                    graph_fixture_a.package_id,
                    observer10.key.resolution_context_digest,
                    target_predicate="always",
                    dependency_kind="runtime",
                ),
                ProviderEdge(
                    graph_fixture_root.package_id,
                    graph_fixture_b.package_id,
                    observer10.key.resolution_context_digest,
                    target_predicate="always",
                    dependency_kind="runtime",
                ),
            ),
            key=_edge_sort_key,
        )
    )
    oversized_graph_nodes = tuple(
        sorted(
            (
                _node(
                    f"bounded-fixture-{index:02d}@1",
                    WIRE_10,
                    f"bounded-fixture-{index:02d}-revision",
                    f"bounded-fixture-{index:02d}-artifact",
                )
                for index in range(MAX_PROVIDER_NODES + 1)
            ),
            key=_node_sort_key,
        )
    )
    oversized_graph_edges = tuple(
        sorted(
            (
                ProviderEdge(
                    oversized_graph_nodes[0].package_id,
                    node.package_id,
                    observer10.key.resolution_context_digest,
                    target_predicate="always",
                    dependency_kind="runtime",
                )
                for node in oversized_graph_nodes[1:]
            ),
            key=_edge_sort_key,
        )
    )
    future_node = _node(
        "ncp-core@1.0.0",
        WIRE_10,
        "future-v1-release-revision",
        "future-v1-release-artifact",
    )
    future_key = _surface_key(
        "haldir",
        "crates/haldir-ncp10",
        "commander",
        ("commander", "wire10"),
        "commander",
        "future-native-commander",
        target_kind="bin",
        default_features=False,
    )
    future_surface = _surface(
        "future10",
        future_key,
        WIRE_10,
        (future_node,),
        lifecycle="qualified_native",
        release_state="immutable_release",
        subject_kind="published_package",
        subject_label="v1.0.0",
    )
    future_record = _discovery_record(
        future_surface.key,
        future_surface.provider_nodes,
        provider_edges=future_surface.provider_edges,
        surface=future_surface,
        executable=True,
        ci_built=True,
        deployment_activated=True,
        contains_ncp=True,
    )
    future_receipts = {
        **_default_subject_receipts(),
        _subject_receipt_key(
            "haldir",
            "immutable_release",
            "published_package",
            WIRE_10,
            "v1.0.0",
            future_node,
        ): (
            future_node.source_revision,
            future_node.artifact_digest,
            future_node.contract_identity,
        ),
    }
    validate_synthetic_fixture(
        (*discovery, future_record),
        (*surfaces, future_surface),
        exclusions,
        subject_receipts=future_receipts,
    )
    haldir_commander_key = _surface_key(
        "haldir",
        "crates/haldir-ncp10",
        "commander",
        ("commander", "wire10"),
        "commander",
        "native-commander",
        target_kind="bin",
        default_features=False,
    )
    haldir_receiver_key = _surface_key(
        "haldir",
        "crates/haldir-ncp10",
        "assessment_receiver",
        ("assessment_receiver", "wire10"),
        "assessment_receiver",
        "native-assessment-receiver",
        target_kind="bin",
        default_features=False,
    )
    haldir_commander = _surface(
        "haldir-commander",
        haldir_commander_key,
        WIRE_10,
        (node10,),
        lifecycle="migration_candidate",
    )
    haldir_receiver = _surface(
        "haldir-receiver",
        haldir_receiver_key,
        WIRE_10,
        (node10,),
        lifecycle="migration_candidate",
    )
    haldir_receiver_collision = replace(
        haldir_receiver,
        credential_set=haldir_commander.credential_set,
        security_manifest=haldir_commander.security_manifest,
    )
    haldir_collision_surfaces = (
        *surfaces,
        haldir_commander,
        haldir_receiver_collision,
    )
    haldir_collision_discovery = (
        *discovery,
        _discovery_record(
            haldir_commander.key,
            haldir_commander.provider_nodes,
            provider_edges=haldir_commander.provider_edges,
            surface=haldir_commander,
            executable=True,
            ci_built=True,
            deployment_activated=True,
            contains_ncp=True,
        ),
        _discovery_record(
            haldir_receiver_collision.key,
            haldir_receiver_collision.provider_nodes,
            provider_edges=haldir_receiver_collision.provider_edges,
            surface=haldir_receiver_collision,
            executable=True,
            ci_built=True,
            deployment_activated=True,
            contains_ncp=True,
        ),
    )
    ordinary_key = _surface_key(
        "galadriel",
        "crates/ordinary-tool",
        "ordinary_tool",
        (),
        "non_surface",
        "not_activated",
        target_kind="bin",
        default_features=False,
    )
    ordinary_root = _node(
        "ordinary-tool@1",
        WIRE_10,
        "ordinary-tool-revision",
        "ordinary-tool-artifact",
    )
    ordinary_record = _discovery_record(
        ordinary_key,
        (ordinary_root,),
        executable=True,
        ci_built=True,
        deployment_activated=False,
        contains_ncp=False,
        closure_root_package_id=ordinary_root.package_id,
    )
    ordinary_discovery = (*discovery, ordinary_record)
    validate_synthetic_fixture(ordinary_discovery, surfaces, exclusions)
    latent_key = replace(
        observer10.key,
        root="crates/latent-ncp-adapter",
        target="latent_observer",
        activation_profile="latent-observer",
    )
    latent_surface = _surface(
        "latent-observer",
        latent_key,
        WIRE_10,
        (node10,),
        lifecycle="retired",
    )
    latent_bound_record = _discovery_record(
        latent_surface.key,
        latent_surface.provider_nodes,
        provider_edges=latent_surface.provider_edges,
        surface=latent_surface,
        executable=False,
        ci_built=False,
        deployment_activated=False,
        contains_ncp=True,
    )
    latent_unbound_record = _seal_discovery(
        replace(
            latent_bound_record,
            surface_id=None,
            record_digest="",
        )
    )
    retired_surface = replace(
        observer08,
        lifecycle="retired",
        executable=False,
        ci_built=False,
        deployment_activated=False,
    )
    retired_surfaces = (
        retired_surface,
        observer10,
        assessor10,
        engram10,
    )
    retired_discovery = _bind_discovery_to_surfaces(
        discovery,
        retired_surfaces,
    )
    validate_synthetic_fixture(
        retired_discovery,
        retired_surfaces,
        exclusions,
    )
    immutable_git_surface = replace(
        observer08,
        subject_kind="git_commit",
    )
    immutable_git_surfaces = (
        immutable_git_surface,
        observer10,
        assessor10,
        engram10,
    )
    immutable_git_discovery = _bind_discovery_to_surfaces(
        discovery,
        immutable_git_surfaces,
    )
    immutable_git_receipts = dict(_default_subject_receipts())
    immutable_git_receipts[
        _subject_receipt_key(
            "galadriel",
            "immutable_release",
            "git_commit",
            WIRE_08,
            "v0.8.0",
            node08,
        )
    ] = (
        node08.source_revision,
        node08.artifact_digest,
        node08.contract_identity,
    )
    validate_synthetic_fixture(
        immutable_git_discovery,
        immutable_git_surfaces,
        exclusions,
        subject_receipts=immutable_git_receipts,
    )
    source_qualified_node = _node(
        ("git+https://github.com/sepahead/NCP?rev=0123456789abcdef#ncp-core@1.0.0"),
        WIRE_10,
        "source-qualified-provider-revision",
        "source-qualified-provider-artifact",
        package_name="ncp-core",
    )
    source_qualified_key = _surface_key(
        "prisoma",
        "crates/ncp-observer",
        "ncp-observe",
        ("observer", "wire10"),
        "observer",
        "native-observer",
        target_kind="bin",
        default_features=False,
    )
    source_qualified_surface = _surface(
        "source-qualified",
        source_qualified_key,
        WIRE_10,
        (source_qualified_node,),
        lifecycle="migration_candidate",
        lock_path="crates/ncp-observer/Cargo.lock",
    )
    source_qualified_record = _discovery_record(
        source_qualified_surface.key,
        source_qualified_surface.provider_nodes,
        provider_edges=source_qualified_surface.provider_edges,
        surface=source_qualified_surface,
        executable=True,
        ci_built=True,
        deployment_activated=True,
        contains_ncp=True,
    )
    source_qualified_receipts = dict(_default_subject_receipts())
    source_qualified_receipts[
        _subject_receipt_key(
            "prisoma",
            "candidate",
            "git_commit",
            WIRE_10,
            "1.0.0-rc.1",
            source_qualified_node,
        )
    ] = (
        source_qualified_node.source_revision,
        source_qualified_node.artifact_digest,
        source_qualified_node.contract_identity,
    )
    validate_synthetic_fixture(
        (*discovery, source_qualified_record),
        (*surfaces, source_qualified_surface),
        exclusions,
        subject_receipts=source_qualified_receipts,
    )
    target_kind_key = replace(
        observer10.key,
        target_kind="example",
        activation_profile="native-observer-example",
    )
    target_kind_surface = _surface(
        "observer10-example",
        target_kind_key,
        WIRE_10,
        (node10,),
        lifecycle="migration_candidate",
    )
    target_kind_record = _discovery_record(
        target_kind_surface.key,
        target_kind_surface.provider_nodes,
        provider_edges=target_kind_surface.provider_edges,
        surface=target_kind_surface,
        executable=True,
        ci_built=True,
        deployment_activated=True,
        contains_ncp=True,
    )
    validate_synthetic_fixture(
        (*discovery, target_kind_record),
        (*surfaces, target_kind_surface),
        exclusions,
    )
    effective_feature_context = _cargo_resolution_context(("ncp-live",))
    effective_feature_key = replace(
        observer10.key,
        features=("ncp-live",),
        activation_profile="native-observer-live-feature",
        resolution_context_digest=_resolution_context_digest(effective_feature_context),
    )
    effective_feature_surface = _surface(
        "observer10-effective-feature",
        effective_feature_key,
        WIRE_10,
        (node10,),
        lifecycle="migration_candidate",
        resolution_context=effective_feature_context,
    )
    effective_feature_record = _discovery_record(
        effective_feature_surface.key,
        effective_feature_surface.provider_nodes,
        provider_edges=effective_feature_surface.provider_edges,
        surface=effective_feature_surface,
        executable=True,
        ci_built=True,
        deployment_activated=True,
        contains_ncp=True,
    )
    validate_synthetic_fixture(
        (*discovery, effective_feature_record),
        (*surfaces, effective_feature_surface),
        exclusions,
    )
    default_feature_key = replace(
        observer10.key,
        default_features=True,
        activation_profile="native-observer-default-features",
    )
    default_feature_surface = _surface(
        "observer10-default-feature-mode",
        default_feature_key,
        WIRE_10,
        (node10,),
        lifecycle="migration_candidate",
    )
    default_feature_record = _discovery_record(
        default_feature_surface.key,
        default_feature_surface.provider_nodes,
        provider_edges=default_feature_surface.provider_edges,
        surface=default_feature_surface,
        executable=True,
        ci_built=True,
        deployment_activated=True,
        contains_ncp=True,
    )
    validate_synthetic_fixture(
        (*discovery, default_feature_record),
        (*surfaces, default_feature_surface),
        exclusions,
    )
    dual_root_08_key = _surface_key(
        "galadriel",
        "crates/dual-adapter",
        "legacy_observer",
        ("observer", "wire08"),
        "observer",
        "dual-wire08-observer",
        target_kind="bin",
        default_features=False,
    )
    dual_root_10_key = _surface_key(
        "galadriel",
        "crates/dual-adapter",
        "native_observer",
        ("observer", "wire10"),
        "observer",
        "dual-wire10-observer",
        target_kind="bin",
        default_features=False,
    )
    dual_root_08_surface = _surface(
        "dual-root-08",
        dual_root_08_key,
        WIRE_08,
        (node08,),
        lifecycle="historical_executable",
    )
    dual_root_10_surface = _surface(
        "dual-root-10",
        dual_root_10_key,
        WIRE_10,
        (node10,),
        lifecycle="migration_candidate",
    )
    dual_root_records = tuple(
        _discovery_record(
            surface.key,
            surface.provider_nodes,
            provider_edges=surface.provider_edges,
            surface=surface,
            executable=True,
            ci_built=True,
            deployment_activated=True,
            contains_ncp=True,
        )
        for surface in (dual_root_08_surface, dual_root_10_surface)
    )
    validate_synthetic_fixture(
        (*discovery, *dual_root_records),
        (*surfaces, dual_root_08_surface, dual_root_10_surface),
        exclusions,
    )
    cross_repository_shared_domain = (
        replace(
            observer08,
            deployment_profile="production",
            deployment_domain="shared_deployment",
        ),
        observer10,
        assessor10,
        replace(
            engram10,
            deployment_profile="production",
            deployment_domain="shared_deployment",
        ),
    )
    cross_repository_shared_discovery = _bind_discovery_to_surfaces(
        discovery,
        cross_repository_shared_domain,
    )
    malicious_ncp_node = replace(
        node10,
        package_id="ncp-core@malicious-lookalike",
        source_identity=_digest("attacker-controlled-ncp-source"),
    )
    malicious_ncp_surface = replace(
        observer10,
        ncp_provider_package_id=malicious_ncp_node.package_id,
        subject_revision=malicious_ncp_node.source_revision,
        artifact_digest=malicious_ncp_node.artifact_digest,
        provider_nodes=tuple(
            sorted(
                (
                    malicious_ncp_node if node.package_id == node10.package_id else node
                    for node in observer10.provider_nodes
                ),
                key=_node_sort_key,
            )
        ),
        provider_edges=tuple(
            sorted(
                (
                    replace(
                        edge,
                        child_package_id=malicious_ncp_node.package_id,
                    )
                    if edge.child_package_id == node10.package_id
                    else edge
                    for edge in observer10.provider_edges
                ),
                key=_edge_sort_key,
            )
        ),
    )
    malicious_ncp_discovery, malicious_ncp_surfaces = _replace_surface_and_discovery(
        discovery,
        surfaces,
        observer10,
        malicious_ncp_surface,
    )
    malicious_self_receipts = dict(_default_subject_receipts())
    malicious_self_receipts[
        _subject_receipt_key(
            "galadriel",
            "candidate",
            "git_commit",
            WIRE_10,
            "1.0.0-rc.1",
            malicious_ncp_node,
        )
    ] = (
        malicious_ncp_node.source_revision,
        malicious_ncp_node.artifact_digest,
        malicious_ncp_node.contract_identity,
    )
    immutable_kind_flip_surfaces = (
        replace(observer08, subject_kind="synchronized_mirror"),
        observer10,
        assessor10,
        engram10,
    )
    immutable_kind_flip_discovery = _bind_discovery_to_surfaces(
        discovery,
        immutable_kind_flip_surfaces,
    )
    manifest_mismatch_surfaces = (
        observer08,
        replace(observer10, manifest_path="unrelated/Cargo.toml"),
        assessor10,
        engram10,
    )
    manifest_mismatch_discovery = _bind_discovery_to_surfaces(
        discovery,
        manifest_mismatch_surfaces,
    )
    output_descriptor_as_input_surfaces = (
        observer08,
        replace(
            observer10,
            surface_input_manifest_path=OUTPUT_INVENTORY_DESCRIPTOR_PATH,
        ),
        assessor10,
        engram10,
    )
    output_descriptor_as_input_discovery = _bind_discovery_to_surfaces(
        discovery,
        output_descriptor_as_input_surfaces,
    )
    python_output_descriptor_as_manifest_surfaces = (
        observer08,
        observer10,
        assessor10,
        replace(
            engram10,
            manifest_path=OUTPUT_INVENTORY_DESCRIPTOR_PATH,
        ),
    )
    python_output_descriptor_as_manifest_discovery = _bind_discovery_to_surfaces(
        discovery,
        python_output_descriptor_as_manifest_surfaces,
    )
    target_mismatch_surfaces = (
        observer08,
        replace(
            observer10,
            runtime_entrypoint=(
                f"{observer10.key.root}/{observer10.key.target_kind}/commander"
            ),
        ),
        assessor10,
        engram10,
    )
    target_mismatch_discovery = _bind_discovery_to_surfaces(
        discovery,
        target_mismatch_surfaces,
    )
    commander_assessor_key = replace(
        haldir_commander.key,
        activation_profile=assessor10.key.activation_profile,
    )
    commander_assessor_surface = replace(
        haldir_commander,
        surface_id=_stable_surface_id(commander_assessor_key),
        key=commander_assessor_key,
        deployment_domain=assessor10.deployment_domain,
        deployment_profile=assessor10.deployment_profile,
        process_namespace=assessor10.process_namespace,
        credential_set=assessor10.credential_set,
        security_manifest=assessor10.security_manifest,
        route_namespace=assessor10.route_namespace,
        state_store=assessor10.state_store,
        configuration_namespace=assessor10.configuration_namespace,
        evidence_namespace=assessor10.evidence_namespace,
        plant_session_namespace=assessor10.plant_session_namespace,
    )
    commander_assessor_discovery = (
        *discovery,
        _discovery_record(
            commander_assessor_surface.key,
            commander_assessor_surface.provider_nodes,
            provider_edges=commander_assessor_surface.provider_edges,
            surface=commander_assessor_surface,
            executable=True,
            ci_built=True,
            deployment_activated=True,
            contains_ncp=True,
        ),
    )
    commander_assessor_surfaces = (*surfaces, commander_assessor_surface)
    plant_commander_key = _surface_key(
        "haldir",
        "crates/haldir-ncp10",
        "plant_commander",
        ("plant_commander", "wire10"),
        "plant_commander",
        "native-plant-commander",
        target_kind="bin",
        default_features=False,
    )
    plant_commander_surface = _surface(
        "haldir-plant-commander",
        plant_commander_key,
        WIRE_10,
        (node10,),
        lifecycle="migration_candidate",
    )
    plant_commander_collision = replace(
        plant_commander_surface,
        credential_set=haldir_commander.credential_set,
        security_manifest=haldir_commander.security_manifest,
    )
    same_authority_surfaces = (
        *surfaces,
        haldir_commander,
        plant_commander_collision,
    )
    same_authority_discovery = (
        *discovery,
        _discovery_record(
            haldir_commander.key,
            haldir_commander.provider_nodes,
            provider_edges=haldir_commander.provider_edges,
            surface=haldir_commander,
            executable=True,
            ci_built=True,
            deployment_activated=True,
            contains_ncp=True,
        ),
        _discovery_record(
            plant_commander_collision.key,
            plant_commander_collision.provider_nodes,
            provider_edges=plant_commander_collision.provider_edges,
            surface=plant_commander_collision,
            executable=True,
            ci_built=True,
            deployment_activated=True,
            contains_ncp=True,
        ),
    )
    macos_context = _cargo_resolution_context(
        observer10.key.features,
        host_triple="aarch64-apple-darwin",
        target_triple="aarch64-apple-darwin",
        cfg=('target_arch="aarch64"', 'target_os="macos"'),
        seed="macos-context",
    )
    macos_key = replace(
        observer10.key,
        activation_profile="native-observer-macos",
        resolution_context_digest=_resolution_context_digest(macos_context),
    )
    macos_surface = _surface(
        "observer10-macos",
        macos_key,
        WIRE_10,
        (node10,),
        lifecycle="migration_candidate",
        resolution_context=macos_context,
        target_predicates={
            node10.package_id: 'cfg(target_os = "macos")',
        },
    )
    macos_record = _discovery_record(
        macos_surface.key,
        macos_surface.provider_nodes,
        provider_edges=macos_surface.provider_edges,
        surface=macos_surface,
        executable=True,
        ci_built=True,
        deployment_activated=True,
        contains_ncp=True,
    )
    validate_synthetic_fixture(
        (*discovery, macos_record),
        (*surfaces, macos_surface),
        exclusions,
    )

    context_mutations: tuple[tuple[str, dict[str, Any]], ...] = (
        ("host_triple", {"host_triple": "aarch64-apple-darwin"}),
        ("target_triple", {"target_triple": "aarch64-apple-darwin"}),
        ("resolver", {"resolver": "cargo-resolver-3"}),
        ("toolchain", {"toolchain": "rust-1.89.0"}),
        ("build_profile", {"build_profile": "debug"}),
        (
            "cfg",
            {"cfg": ('target_arch="x86_64"', 'target_os="macos"')},
        ),
        ("effective_features", {"effective_features": ("observer", "wire08")}),
        (
            "surface_input_manifest_digest",
            {"surface_input_manifest_digest": _digest("changed-input-manifest")},
        ),
        ("lock_input_digest", {"lock_input_digest": _digest("changed-lock")}),
        (
            "config_input_digest",
            {"config_input_digest": _digest("changed-config")},
        ),
        ("patch_input_digest", {"patch_input_digest": _digest("changed-patch")}),
        (
            "environment_input_digest",
            {"environment_input_digest": _digest("changed-environment")},
        ),
        ("flags_input_digest", {"flags_input_digest": _digest("changed-flags")}),
        (
            "build_script_input_digest",
            {"build_script_input_digest": _digest("changed-build-script")},
        ),
        (
            "ci_invocation_digest",
            {"ci_invocation_digest": _digest("changed-ci-invocation")},
        ),
        (
            "deployment_invocation_digest",
            {"deployment_invocation_digest": _digest("changed-deployment-invocation")},
        ),
    )
    context_drift_fixtures: list[
        tuple[
            str,
            tuple[DiscoveryRecord, ...],
            tuple[Surface, ...],
            ResolutionContext,
        ]
    ] = []
    for field, changes in context_mutations:
        changed_context = replace(observer10.resolution_context, **changes)
        changed_surface = replace(
            observer10,
            resolution_context=changed_context,
        )
        changed_discovery, changed_surfaces = _replace_surface_and_discovery(
            discovery,
            surfaces,
            observer10,
            changed_surface,
        )
        context_drift_fixtures.append(
            (field, changed_discovery, changed_surfaces, changed_context)
        )

    edge_context_drift_surface = replace(
        observer10,
        provider_edges=tuple(
            replace(edge, resolution_context_digest="0" * 64)
            for edge in observer10.provider_edges
        ),
    )
    edge_context_drift_discovery, edge_context_drift_surfaces = (
        _replace_surface_and_discovery(
            discovery,
            surfaces,
            observer10,
            edge_context_drift_surface,
        )
    )
    unknown_predicate_surface = replace(
        observer10,
        provider_edges=tuple(
            replace(edge, target_predicate="unknown")
            for edge in observer10.provider_edges
        ),
    )
    unknown_predicate_discovery, unknown_predicate_surfaces = (
        _replace_surface_and_discovery(
            discovery,
            surfaces,
            observer10,
            unknown_predicate_surface,
        )
    )
    inactive_cfg_predicate_surface = replace(
        observer10,
        provider_edges=tuple(
            replace(
                edge,
                target_predicate='cfg(target_os = "windows")',
            )
            for edge in observer10.provider_edges
        ),
    )
    inactive_cfg_predicate_discovery, inactive_cfg_predicate_surfaces = (
        _replace_surface_and_discovery(
            discovery,
            surfaces,
            observer10,
            inactive_cfg_predicate_surface,
        )
    )

    contract_identity_mutations: tuple[
        tuple[str, ContractIdentity],
        ...,
    ] = (
        (
            "unknown_kind",
            replace(node10.contract_identity, kind="unknown"),
        ),
        (
            "cross_kind",
            replace(
                node10.contract_identity,
                kind="frozen_wire_baseline_artifact",
            ),
        ),
        (
            "digest_domain",
            replace(
                node10.contract_identity,
                digest_domain="ncp.normative-contract.v2",
            ),
        ),
        (
            "digest_sha256",
            replace(node10.contract_identity, digest_sha256="0" * 64),
        ),
        (
            "compact_hash_algorithm",
            replace(node10.contract_identity, compact_hash_algorithm="sha256"),
        ),
        (
            "compact_hash",
            replace(node10.contract_identity, compact_hash="0" * 16),
        ),
    )
    contract_identity_fixtures: list[
        tuple[str, tuple[DiscoveryRecord, ...], tuple[Surface, ...]]
    ] = []
    for field, contract_identity in contract_identity_mutations:
        changed_node = replace(node10, contract_identity=contract_identity)
        changed_surface = replace(
            observer10,
            provider_nodes=tuple(
                changed_node if node.package_id == node10.package_id else node
                for node in observer10.provider_nodes
            ),
        )
        changed_discovery, changed_surfaces = _replace_surface_and_discovery(
            discovery,
            surfaces,
            observer10,
            changed_surface,
        )
        contract_identity_fixtures.append((field, changed_discovery, changed_surfaces))
    observer_receipt_key = _subject_receipt_key(
        observer10.key.repository,
        observer10.release_state,
        observer10.subject_kind,
        observer10.wire,
        observer10.subject_label,
        node10,
    )
    contract_receipt_drift = dict(_default_subject_receipts())
    contract_receipt_drift[observer_receipt_key] = (
        node10.source_revision,
        node10.artifact_digest,
        TRUSTED_WIRE_CONTRACT_IDENTITIES[WIRE_08],
    )

    excluded_record = discovery[-2]
    excluded_optional_values: tuple[tuple[str, Any], ...] = (
        ("surface_id", observer10.surface_id),
        ("capability_class", observer10.capability_class),
        ("wire", WIRE_10),
        ("release_state", "candidate"),
        ("subject_kind", "git_commit"),
        ("subject_label", "1.0.0-rc.1"),
        ("subject_revision", node10.source_revision),
        ("artifact_digest", node10.artifact_digest),
        ("lifecycle", "migration_candidate"),
        ("locator_kind", "cargo_target"),
        ("surface_input_manifest_path", OUTPUT_INVENTORY_DESCRIPTOR_PATH),
        ("manifest_path", "../outside/Cargo.toml"),
        ("lock_path", "Cargo.lock"),
        ("runtime_entrypoint", "/" + "x" * 1024),
        ("deployment_profile", "production"),
        ("deployment_domain", "invalid domain"),
        ("ncp_provider_package_id", node10.package_id),
        ("process_namespace", "process"),
        ("credential_set", "credential"),
        ("security_manifest", "security"),
        ("route_namespace", "routes"),
        ("state_store", "state"),
        ("configuration_namespace", "configuration"),
        ("evidence_namespace", "evidence"),
        ("plant_session_namespace", "session"),
    )
    exclusion_optional_fixtures: list[
        tuple[
            str,
            tuple[DiscoveryRecord, ...],
            tuple[SurfaceExclusion, ...],
        ]
    ] = []
    for field, value in excluded_optional_values:
        changed_record = _seal_discovery(
            replace(
                excluded_record,
                **{field: value},
                record_digest="",
            )
        )
        changed_discovery = tuple(
            changed_record if record.key == excluded_record.key else record
            for record in discovery
        )
        changed_exclusions = tuple(
            replace(
                exclusion,
                discovery_record_digest=changed_record.record_digest,
            )
            if exclusion.key == excluded_record.key
            else exclusion
            for exclusion in exclusions
        )
        exclusion_optional_fixtures.append(
            (field, changed_discovery, changed_exclusions)
        )

    excluded_graph_root = _node(
        "excluded-root@1",
        WIRE_NEUTRAL,
        "excluded-root-revision",
        "excluded-root-artifact",
    )
    excluded_graph_record = _seal_discovery(
        replace(
            excluded_record,
            closure_root_package_id=excluded_graph_root.package_id,
            provider_nodes=(excluded_graph_root,),
            record_digest="",
        )
    )
    excluded_graph_discovery = tuple(
        excluded_graph_record if record.key == excluded_record.key else record
        for record in discovery
    )
    excluded_graph_exclusions = tuple(
        replace(
            exclusion,
            discovery_record_digest=excluded_graph_record.record_digest,
        )
        if exclusion.key == excluded_record.key
        else exclusion
        for exclusion in exclusions
    )

    no_target_context = _non_build_resolution_context(observer10.key.features)
    no_target_key = replace(
        observer10.key,
        activation_profile="invalid-no-target",
        target_kind="none",
        resolution_context_digest=_resolution_context_digest(no_target_context),
    )
    no_target_surface = _surface(
        "observer10-no-target",
        no_target_key,
        WIRE_10,
        (node10,),
        lifecycle="migration_candidate",
        resolution_context=no_target_context,
    )
    no_target_record = _discovery_record(
        no_target_surface.key,
        no_target_surface.provider_nodes,
        provider_edges=no_target_surface.provider_edges,
        surface=no_target_surface,
        executable=True,
        ci_built=True,
        deployment_activated=True,
        contains_ncp=True,
    )
    truncated_surface_id = f"surface_{_canonical_digest(asdict(observer10.key))[:16]}"
    truncated_id_surface = replace(
        observer10,
        surface_id=truncated_surface_id,
    )
    truncated_id_discovery, truncated_id_surfaces = _replace_surface_and_discovery(
        discovery,
        surfaces,
        observer10,
        truncated_id_surface,
    )
    truncated_scoped_surface = replace(
        observer10,
        credential_set=(
            f"credential_{_digest(f'{observer10.surface_id}:credential')[:24]}"
        ),
    )
    truncated_scoped_discovery, truncated_scoped_surfaces = (
        _replace_surface_and_discovery(
            discovery,
            surfaces,
            observer10,
            truncated_scoped_surface,
        )
    )
    full_root_id, _ = _root_package_identity(observer10.key)
    full_root_digest = full_root_id.rsplit("@", 1)[-1]
    truncated_root_id = f"consumer-root@{full_root_digest[:16]}"
    truncated_root_name = f"consumer-root-{full_root_digest[:16]}"
    truncated_root_node = replace(
        next(
            node
            for node in observer10.provider_nodes
            if node.package_id == observer10.closure_root_package_id
        ),
        package_id=truncated_root_id,
        package_name=truncated_root_name,
    )
    truncated_root_surface = replace(
        observer10,
        closure_root_package_id=truncated_root_id,
        provider_nodes=tuple(
            sorted(
                (
                    truncated_root_node
                    if node.package_id == observer10.closure_root_package_id
                    else node
                    for node in observer10.provider_nodes
                ),
                key=_node_sort_key,
            )
        ),
        provider_edges=tuple(
            sorted(
                (
                    replace(
                        edge,
                        parent_package_id=truncated_root_id,
                    )
                    if edge.parent_package_id == observer10.closure_root_package_id
                    else edge
                    for edge in observer10.provider_edges
                ),
                key=_edge_sort_key,
            )
        ),
    )
    truncated_root_discovery, truncated_root_surfaces = _replace_surface_and_discovery(
        discovery,
        surfaces,
        observer10,
        truncated_root_surface,
    )
    role_variant = replace(
        observer10.key,
        role="assessment_receiver",
        activation_profile="native_assessment_receiver",
    )
    role_variant_surface = _surface(
        "observer10-shadow",
        role_variant,
        WIRE_10,
        (node10,),
        lifecycle="migration_candidate",
    )
    role_variant_record = _discovery_record(
        role_variant,
        role_variant_surface.provider_nodes,
        provider_edges=role_variant_surface.provider_edges,
        surface=role_variant_surface,
        executable=True,
        ci_built=True,
        deployment_activated=True,
        contains_ncp=True,
    )
    same_build_assessor_key = replace(
        observer10.key,
        role="assessor",
        activation_profile="same_build_assessor",
    )
    same_build_assessor = _surface(
        "same-build-assessor",
        same_build_assessor_key,
        WIRE_10,
        (node10,),
        lifecycle="migration_candidate",
    )
    same_build_assessor_record = _discovery_record(
        same_build_assessor.key,
        same_build_assessor.provider_nodes,
        provider_edges=same_build_assessor.provider_edges,
        surface=same_build_assessor,
        executable=True,
        ci_built=True,
        deployment_activated=True,
        contains_ncp=True,
    )
    same_build_commander_key = replace(
        engram10.key,
        role="plant_commander",
        activation_profile="same_build_plant_commander",
    )
    same_build_commander = _surface(
        "same-build-commander",
        same_build_commander_key,
        WIRE_10,
        (node10,),
        lifecycle="migration_candidate",
        subject_kind="synchronized_mirror",
    )
    same_build_commander_record = _discovery_record(
        same_build_commander.key,
        same_build_commander.provider_nodes,
        provider_edges=same_build_commander.provider_edges,
        surface=same_build_commander,
        executable=True,
        ci_built=True,
        deployment_activated=True,
        contains_ncp=True,
    )
    same_build_engram_receiver_key = replace(
        engram10.key,
        role="assessment_receiver",
        activation_profile="same_build_assessment_receiver",
    )
    same_build_engram_receiver = _surface(
        "same-build-engram-receiver",
        same_build_engram_receiver_key,
        WIRE_10,
        (node10,),
        lifecycle="migration_candidate",
        subject_kind="synchronized_mirror",
    )
    same_build_engram_receiver_record = _discovery_record(
        same_build_engram_receiver.key,
        same_build_engram_receiver.provider_nodes,
        provider_edges=same_build_engram_receiver.provider_edges,
        surface=same_build_engram_receiver,
        executable=True,
        ci_built=True,
        deployment_activated=True,
        contains_ncp=True,
    )

    hostile_inputs = [
        _hostile_witness(
            "empty_inventory_against_fixed_scan_baseline",
            lambda: _validate_surfaces((), (), ()),
            {"discovery_count": 0, "surface_count": 0},
        ),
        _hostile_witness(
            "self_sealed_inactivity_differs_from_trusted_scan_snapshot",
            lambda: _validate_surfaces(
                retired_discovery,
                retired_surfaces,
                exclusions,
            ),
            {
                "surface": retired_surface.surface_id,
                "trusted_lifecycle": observer08.lifecycle,
                "self_sealed_lifecycle": retired_surface.lifecycle,
            },
        ),
        _hostile_witness(
            "all_ncp_roots_omitted_from_inventory",
            lambda: _validate_surfaces(
                discovery[-2:],
                (),
                exclusions,
            ),
            {
                "retained_non_ncp_keys": [
                    asdict(record.key) for record in discovery[-2:]
                ],
            },
        ),
        _hostile_witness(
            "inactive_ncp_root_without_retired_surface",
            lambda: _validate_surfaces(
                (*discovery, latent_unbound_record),
                surfaces,
                exclusions,
            ),
            {
                "key": asdict(latent_unbound_record.key),
                "active": _active(latent_unbound_record),
                "contains_ncp": True,
            },
        ),
        _hostile_witness(
            "omitted_surface_tuple",
            lambda: _validate_surfaces(
                discovery,
                surfaces[:-1],
                exclusions,
            ),
            {"omitted": asdict(assessor10.key)},
        ),
        _hostile_witness(
            "duplicate_surface_tuple_assignment",
            lambda: _validate_surfaces(
                discovery,
                duplicate_key,
                exclusions,
            ),
            {"duplicated": asdict(observer10.key)},
        ),
        _hostile_witness(
            "duplicate_surface_id",
            lambda: _validate_surfaces(
                discovery,
                duplicate_id,
                exclusions,
            ),
            {"surface_id": observer10.surface_id},
        ),
        _hostile_witness(
            "stable_surface_ids_swapped_between_tuples",
            lambda: _validate_surfaces(
                swapped_id_discovery,
                swapped_ids,
                exclusions,
            ),
            {
                "first_key": asdict(observer10.key),
                "second_key": asdict(assessor10.key),
            },
        ),
        _hostile_witness(
            "mixed_wire_closure",
            lambda: _validate_surfaces(
                mixed_discovery,
                mixed_closure,
                exclusions,
            ),
            {"surface": observer10.surface_id},
        ),
        _hostile_witness(
            "orphaned_provider_edge",
            lambda: _validate_surfaces(
                orphan_discovery,
                orphan_edge,
                exclusions,
            ),
            {"package_id": orphan_node.package_id},
        ),
        _hostile_witness(
            "duplicate_provider_graph_node",
            lambda: _validate_surfaces(
                duplicate_provider_discovery,
                duplicate_provider,
                exclusions,
            ),
            {"package_id": observer10.provider_nodes[-1].package_id},
        ),
        _hostile_witness(
            "duplicate_provider_graph_edge",
            lambda: _validate_surfaces(
                duplicate_edge_discovery,
                duplicate_edge,
                exclusions,
            ),
            {"edge": asdict(observer10.provider_edges[0])},
        ),
        _hostile_witness(
            "provider_graph_cycle",
            lambda: _validate_surfaces(
                provider_cycle_discovery,
                provider_cycle,
                exclusions,
            ),
            {"cycle_node": cycle_node.package_id},
        ),
        _hostile_witness(
            "inconsistent_shared_provider_identity",
            lambda: _validate_surfaces(
                inconsistent_discovery,
                inconsistent_surfaces,
                exclusions,
            ),
            {"package_id": node10.package_id},
        ),
        _hostile_witness(
            "mixed_wire_activation_profile",
            lambda: _validate_surfaces(
                mixed_profile_discovery,
                mixed_profile,
                exclusions,
            ),
            {"profile": observer08.key.activation_profile},
        ),
        _hostile_witness(
            "noncanonical_provider_node_order",
            lambda: _validate_provider_closure(
                tuple(reversed(observer10.provider_nodes)),
                observer10.provider_edges,
                observer10.closure_root_package_id,
                observer10.resolution_context,
            ),
            {"surface": observer10.surface_id},
        ),
        _hostile_witness(
            "noncanonical_provider_edge_order",
            lambda: _validate_provider_closure(
                graph_fixture_nodes,
                tuple(reversed(graph_fixture_edges)),
                graph_fixture_root.package_id,
                observer10.resolution_context,
            ),
            {
                "edge_count": len(graph_fixture_edges),
                "root": graph_fixture_root.package_id,
            },
        ),
        _hostile_witness(
            "provider_graph_node_bound_exceeded",
            lambda: _validate_provider_closure(
                oversized_graph_nodes,
                oversized_graph_edges,
                oversized_graph_nodes[0].package_id,
                observer10.resolution_context,
            ),
            {
                "node_count": len(oversized_graph_nodes),
                "maximum": MAX_PROVIDER_NODES,
            },
        ),
        _hostile_witness(
            "non_runtime_provider_edge",
            lambda: _validate_provider_closure(
                observer10.provider_nodes,
                (
                    replace(
                        observer10.provider_edges[0],
                        dependency_kind="dev",
                    ),
                ),
                observer10.closure_root_package_id,
                observer10.resolution_context,
            ),
            {"dependency_kind": "dev"},
        ),
        _hostile_witness(
            "provider_package_id_control_character",
            lambda: _validate_node(replace(node10, package_id="ncp-core@\u0000evil")),
            {"package_id": "ncp-core@\\u0000evil"},
        ),
        _hostile_witness(
            "active_discovery_ncp_classification_flip",
            lambda: _validate_surfaces(
                contains_ncp_flip,
                surfaces,
                exclusions,
            ),
            {"surface": observer10.surface_id, "contains_ncp": False},
        ),
        _hostile_witness(
            "invented_active_ncp_free_surface",
            lambda: _validate_surfaces(
                ncp_free_discovery,
                ncp_free_surfaces,
                exclusions,
            ),
            {
                "surface": ncp_free_surface.surface_id,
                "provider": ncp_free_surface.ncp_provider_package_id,
            },
        ),
        _hostile_witness(
            "immutable_release_receipt_drift",
            lambda: _validate_surfaces(
                frozen_drift_discovery,
                frozen_drift_surfaces,
                exclusions,
            ),
            {
                "surface": observer08.surface_id,
                "subject_label": observer08.subject_label,
            },
        ),
        _hostile_witness(
            "unregistered_role_relabel",
            lambda: _validate_surfaces(
                invalid_role_discovery,
                invalid_role_surfaces,
                exclusions,
            ),
            {"role": invalid_role_key.role},
        ),
        _hostile_witness(
            "observer_receiver_same_build_relabel",
            lambda: validate_synthetic_fixture(
                (*discovery, role_variant_record),
                (*surfaces, role_variant_surface),
                exclusions,
            ),
            {
                "capabilities": [
                    observer10.capability_class,
                    role_variant_surface.capability_class,
                ],
                "target": observer10.key.target,
                "features": list(observer10.key.features),
            },
        ),
        _hostile_witness(
            "observer_assessor_same_build_relabel",
            lambda: validate_synthetic_fixture(
                (*discovery, same_build_assessor_record),
                (*surfaces, same_build_assessor),
                exclusions,
            ),
            {
                "capabilities": [
                    observer10.capability_class,
                    same_build_assessor.capability_class,
                ],
                "target": observer10.key.target,
                "features": list(observer10.key.features),
            },
        ),
        _hostile_witness(
            "responder_commander_same_build_relabel",
            lambda: validate_synthetic_fixture(
                (*discovery, same_build_commander_record),
                (*surfaces, same_build_commander),
                exclusions,
            ),
            {
                "capabilities": [
                    engram10.capability_class,
                    same_build_commander.capability_class,
                ],
                "target": engram10.key.target,
                "features": list(engram10.key.features),
            },
        ),
        _hostile_witness(
            "responder_receiver_same_build_relabel",
            lambda: validate_synthetic_fixture(
                (*discovery, same_build_engram_receiver_record),
                (*surfaces, same_build_engram_receiver),
                exclusions,
            ),
            {
                "capabilities": [
                    engram10.capability_class,
                    same_build_engram_receiver.capability_class,
                ],
                "target": engram10.key.target,
                "features": list(engram10.key.features),
            },
        ),
        _hostile_witness(
            "commander_receiver_privilege_collision",
            lambda: _validate_surfaces(
                haldir_collision_discovery,
                haldir_collision_surfaces,
                exclusions,
            ),
            {
                "capabilities": [
                    haldir_commander.capability_class,
                    haldir_receiver_collision.capability_class,
                ],
                "credential_set": haldir_commander.credential_set,
            },
        ),
        _hostile_witness(
            "untrusted_ncp_package_lookalike",
            lambda: _validate_surfaces(
                malicious_ncp_discovery,
                malicious_ncp_surfaces,
                exclusions,
            ),
            {
                "package_id": malicious_ncp_node.package_id,
                "source_identity": malicious_ncp_node.source_identity,
            },
        ),
        _hostile_witness(
            "caller_self_authorized_ncp_package_lookalike",
            lambda: _validate_surfaces(
                malicious_ncp_discovery,
                malicious_ncp_surfaces,
                exclusions,
                subject_receipts=malicious_self_receipts,
            ),
            {
                "package_id": malicious_ncp_node.package_id,
                "caller_supplied_receipt": True,
            },
        ),
        _hostile_witness(
            "immutable_subject_kind_receipt_reuse",
            lambda: _validate_surfaces(
                immutable_kind_flip_discovery,
                immutable_kind_flip_surfaces,
                exclusions,
            ),
            {"subject_kind": "synchronized_mirror"},
        ),
        _hostile_witness(
            "surface_manifest_outside_key_root",
            lambda: _validate_surfaces(
                manifest_mismatch_discovery,
                manifest_mismatch_surfaces,
                exclusions,
            ),
            {"manifest_path": "unrelated/Cargo.toml"},
        ),
        _hostile_witness(
            "output_descriptor_cannot_be_surface_input_manifest",
            lambda: _validate_surfaces(
                output_descriptor_as_input_discovery,
                output_descriptor_as_input_surfaces,
                exclusions,
            ),
            {
                "output_descriptor": OUTPUT_INVENTORY_DESCRIPTOR_PATH,
                "input_manifest": OUTPUT_INVENTORY_DESCRIPTOR_PATH,
            },
        ),
        _hostile_witness(
            "output_descriptor_cannot_be_python_package_manifest",
            lambda: _validate_surfaces(
                python_output_descriptor_as_manifest_discovery,
                python_output_descriptor_as_manifest_surfaces,
                exclusions,
            ),
            {
                "output_descriptor": OUTPUT_INVENTORY_DESCRIPTOR_PATH,
                "package_manifest": OUTPUT_INVENTORY_DESCRIPTOR_PATH,
            },
        ),
        _hostile_witness(
            "runtime_target_name_mismatch",
            lambda: _validate_surfaces(
                target_mismatch_discovery,
                target_mismatch_surfaces,
                exclusions,
            ),
            {
                "target": observer10.key.target,
                "runtime_entrypoint": target_mismatch_surfaces[1].runtime_entrypoint,
            },
        ),
        _hostile_witness(
            "assessor_commander_privilege_collision",
            lambda: _validate_surfaces(
                commander_assessor_discovery,
                commander_assessor_surfaces,
                exclusions,
            ),
            {
                "capabilities": [
                    assessor10.capability_class,
                    commander_assessor_surface.capability_class,
                ],
                "deployment_domain": assessor10.deployment_domain,
            },
        ),
        _hostile_witness(
            "same_command_capability_privilege_collision",
            lambda: _validate_surfaces(
                same_authority_discovery,
                same_authority_surfaces,
                exclusions,
            ),
            {
                "capability": haldir_commander.capability_class,
                "credential_set": haldir_commander.credential_set,
            },
        ),
        _hostile_witness(
            "cross_repository_shared_deployment_domain_collision",
            lambda: _validate_surfaces(
                cross_repository_shared_discovery,
                cross_repository_shared_domain,
                exclusions,
            ),
            {
                "deployment_domain": "shared_deployment",
                "deployment_profile": "production",
                "wires": [WIRE_08, WIRE_10],
            },
        ),
        _hostile_witness(
            "surface_subject_provider_drift",
            lambda: _validate_surfaces(
                subject_provider_drift_discovery,
                subject_provider_drift,
                exclusions,
            ),
            {"surface": observer10.surface_id},
        ),
        _hostile_witness(
            "subject_label_release_mismatch",
            lambda: _validate_surfaces(
                release_label_mismatch_discovery,
                release_label_mismatch,
                exclusions,
            ),
            {
                "wire": WIRE_10,
                "release_state": "immutable_release",
                "subject_label": "v0.8.0",
            },
        ),
        _hostile_witness(
            "executable_non_ncp_exclusion",
            lambda: _validate_surfaces(
                executable_non_ncp_discovery,
                surfaces,
                exclusions,
            ),
            {"key": asdict(exclusions[0].key), "executable": True},
        ),
        _hostile_witness(
            "process_namespace_relabel_without_discovery",
            lambda: _validate_surfaces(
                discovery,
                namespace_relabel,
                exclusions,
            ),
            {"surface": observer10.surface_id},
        ),
        _hostile_witness(
            "runtime_entrypoint_relabel_without_discovery",
            lambda: _validate_surfaces(
                discovery,
                runtime_relabel,
                exclusions,
            ),
            {"surface": observer10.surface_id},
        ),
    ]
    for field in (
        "deployment_profile",
        "process_namespace",
        "credential_set",
        "security_manifest",
        "route_namespace",
        "state_store",
        "configuration_namespace",
        "evidence_namespace",
        "plant_session_namespace",
    ):
        mixed_namespace = (
            observer08,
            replace(
                observer10,
                **{field: getattr(observer08, field)},
            ),
            assessor10,
            engram10,
        )
        mixed_namespace_discovery = _bind_discovery_to_surfaces(
            discovery,
            mixed_namespace,
        )
        hostile_inputs.append(
            _hostile_witness(
                f"mixed_wire_{field}",
                lambda records=mixed_namespace_discovery, values=mixed_namespace: (
                    _validate_surfaces(
                        records,
                        values,
                        exclusions,
                    )
                ),
                {"field": field, "value": getattr(observer08, field)},
            )
        )
    for field in (
        "runtime_entrypoint",
        "deployment_profile",
        "process_namespace",
        "credential_set",
        "security_manifest",
        "route_namespace",
        "state_store",
        "configuration_namespace",
        "evidence_namespace",
        "plant_session_namespace",
    ):
        collided_surfaces = (
            observer08,
            observer10,
            replace(
                assessor10,
                **{field: getattr(observer10, field)},
            ),
            engram10,
        )
        collided_discovery = _bind_discovery_to_surfaces(
            discovery,
            collided_surfaces,
        )
        hostile_inputs.append(
            _hostile_witness(
                f"observer_assessor_{field}_collision",
                lambda records=collided_discovery, values=collided_surfaces: (
                    _validate_surfaces(records, values, exclusions)
                ),
                {"field": field, "wire": WIRE_10},
            )
        )
    mixed_runtime = (
        observer08,
        replace(
            observer10,
            runtime_entrypoint=observer08.runtime_entrypoint,
        ),
        assessor10,
        engram10,
    )
    mixed_runtime_discovery = _bind_discovery_to_surfaces(
        discovery,
        mixed_runtime,
    )
    hostile_inputs.append(
        _hostile_witness(
            "mixed_wire_runtime_entrypoint",
            lambda: _validate_surfaces(
                mixed_runtime_discovery,
                mixed_runtime,
                exclusions,
            ),
            {"runtime_entrypoint": observer08.runtime_entrypoint},
        )
    )
    collided_activation_key = replace(
        assessor10.key,
        activation_profile=observer10.key.activation_profile,
    )
    collided_activation_surface = replace(
        assessor10,
        surface_id=_stable_surface_id(collided_activation_key),
        key=collided_activation_key,
    )
    collided_activation_discovery, collided_activation_surfaces = (
        _replace_surface_and_discovery(
            discovery,
            surfaces,
            assessor10,
            collided_activation_surface,
        )
    )
    hostile_inputs.append(
        _hostile_witness(
            "observer_assessor_activation_profile_collision",
            lambda: _validate_surfaces(
                collided_activation_discovery,
                collided_activation_surfaces,
                exclusions,
            ),
            {"activation_profile": observer10.key.activation_profile},
        )
    )
    for alias_name, alias_root in (
        ("dot_segment", "crates/./galadriel-ncp10"),
        ("duplicate_separator", "crates//galadriel-ncp10"),
        ("trailing_separator", "crates/galadriel-ncp10/"),
        ("windows_traversal", "..\\outside"),
        ("control_character", "crates/\u0000adapter"),
    ):
        hostile_inputs.append(
            _hostile_witness(
                f"noncanonical_surface_root_{alias_name}",
                lambda root=alias_root: _validate_key(
                    replace(observer10.key, root=root)
                ),
                {"root": alias_root},
            )
        )
    hostile_inputs.extend(
        [
            _hostile_witness(
                "unknown_wire",
                lambda: _validate_surfaces(
                    discovery,
                    unknown_wire,
                    exclusions,
                ),
                {"wire": "unknown"},
            ),
            _hostile_witness(
                "unknown_release_state",
                lambda: _validate_surfaces(
                    discovery,
                    unknown_release,
                    exclusions,
                ),
                {"release_state": "unknown"},
            ),
            _hostile_witness(
                "unknown_subject_kind",
                lambda: _validate_surfaces(
                    discovery,
                    unknown_subject,
                    exclusions,
                ),
                {"subject_kind": "unknown"},
            ),
            _hostile_witness(
                "unknown_lifecycle",
                lambda: _validate_surfaces(
                    discovery,
                    unknown_lifecycle,
                    exclusions,
                ),
                {"lifecycle": "unknown"},
            ),
            _hostile_witness(
                "invalid_surface_id",
                lambda: _validate_surfaces(
                    discovery,
                    invalid_id,
                    exclusions,
                ),
                {"surface_id": ""},
            ),
            _hostile_witness(
                "noncanonical_feature_set",
                lambda: _validate_surfaces(
                    discovery,
                    noncanonical_features,
                    exclusions,
                ),
                {"features": ["wire10", "observer"]},
            ),
            _hostile_witness(
                "invalid_provider_digest",
                lambda: _validate_surfaces(
                    discovery,
                    invalid_provider,
                    exclusions,
                ),
                {"artifact_digest": "0"},
            ),
            _hostile_witness(
                "invalid_subject_revision",
                lambda: _validate_surfaces(
                    discovery,
                    invalid_subject,
                    exclusions,
                ),
                {"subject_revision": "main"},
            ),
            _hostile_witness(
                "active_discovery_retired_descriptor",
                lambda: _validate_surfaces(
                    discovery,
                    retired,
                    exclusions,
                ),
                {
                    "surface": observer08.surface_id,
                    "descriptor_executable": False,
                    "discovery_executable": True,
                },
            ),
            _hostile_witness(
                "exclusion_digest_mismatch",
                lambda: _validate_surfaces(
                    discovery,
                    surfaces,
                    (
                        replace(
                            exclusions[0],
                            discovery_record_digest="0" * 64,
                        ),
                        exclusions[1],
                    ),
                ),
                {"excluded": asdict(exclusions[0].key)},
            ),
            _hostile_witness(
                "nonexistent_exclusion",
                lambda: _validate_surfaces(
                    discovery,
                    surfaces,
                    (
                        *exclusions,
                        SurfaceExclusion(
                            _surface_key(
                                "galadriel",
                                "docs/missing",
                                "none",
                                (),
                                "non_surface",
                                "not_activated",
                                target_kind="none",
                                default_features=False,
                            ),
                            "documentation_only",
                            _digest("missing-record"),
                            "package-tooling-reviewer",
                            "accepted_non_surface",
                        ),
                    ),
                ),
                {"root": "docs/missing"},
            ),
            _hostile_witness(
                "unknown_exclusion_reason",
                lambda: _validate_surfaces(
                    discovery,
                    surfaces,
                    (
                        replace(exclusions[0], reason="unknown"),
                        exclusions[1],
                    ),
                ),
                {"reason": "unknown"},
            ),
            _hostile_witness(
                "active_surface_exclusion",
                lambda: _validate_surfaces(
                    discovery,
                    surfaces,
                    (
                        *exclusions,
                        SurfaceExclusion(
                            observer10.key,
                            "scanner_fixture",
                            discovery[1].record_digest,
                            "package-tooling-reviewer",
                            "accepted_non_surface",
                        ),
                    ),
                ),
                {"surface": observer10.surface_id},
            ),
            _hostile_witness(
                "missing_exclusion_reviewer",
                lambda: _validate_surfaces(
                    discovery,
                    surfaces,
                    (
                        replace(exclusions[0], reviewer_id=""),
                        exclusions[1],
                    ),
                ),
                {"reviewer_id": ""},
            ),
            _hostile_witness(
                "exclusion_bound_exceeded",
                lambda: _validate_surfaces(
                    discovery,
                    surfaces,
                    exclusions * 3,
                ),
                {"count": len(exclusions) * 3, "maximum": MAX_EXCLUSIONS},
            ),
            _hostile_witness(
                "legacy_descriptor_with_multiple_surfaces",
                lambda: _validate_surfaces(
                    discovery,
                    surfaces,
                    exclusions,
                    descriptor_version=1,
                ),
                {"descriptor_version": 1, "surface_count": len(surfaces)},
            ),
            _hostile_witness(
                "repository_descriptor_downgrade_below_trusted_floor",
                lambda: _validate_surfaces(
                    discovery,
                    surfaces,
                    exclusions,
                    descriptor_versions={
                        "engram": 2,
                        "galadriel": 1,
                    },
                ),
                {
                    "repository": "galadriel",
                    "asserted_version": 1,
                    "trusted_floor": 2,
                },
            ),
            _hostile_witness(
                "unknown_descriptor_version",
                lambda: _validate_surfaces(
                    discovery,
                    surfaces,
                    exclusions,
                    descriptor_version=99,
                ),
                {"descriptor_version": 99},
            ),
            _hostile_witness(
                "lock_global_identity",
                lambda: _validate_surfaces(
                    discovery,
                    surfaces,
                    exclusions,
                    lock_global_identity=True,
                ),
                {
                    "shared_lock": "Cargo.lock",
                    "valid_per_surface_wires": [WIRE_08, WIRE_10],
                },
            ),
        ]
    )
    hostile_inputs.append(
        _hostile_witness(
            "surface_key_resolution_context_digest_drift",
            lambda: _validate_resolution_context(
                replace(
                    observer10.key,
                    resolution_context_digest="0" * 64,
                ),
                observer10.resolution_context,
            ),
            {
                "field": "resolution_context_digest",
                "surface": observer10.surface_id,
            },
        )
    )
    for (
        field,
        changed_discovery,
        changed_surfaces,
        changed_context,
    ) in context_drift_fixtures:
        hostile_inputs.append(
            _hostile_witness(
                f"resolution_context_{field}_drift",
                lambda changed_discovery=changed_discovery, changed_surfaces=changed_surfaces: (  # noqa: E501
                    validate_synthetic_fixture(
                        changed_discovery,
                        changed_surfaces,
                        exclusions,
                    )
                ),
                {
                    "field": field,
                    "context_digest": _resolution_context_digest(changed_context),
                },
            )
        )
    hostile_inputs.extend(
        (
            _hostile_witness(
                "provider_edge_resolution_context_drift",
                lambda: validate_synthetic_fixture(
                    edge_context_drift_discovery,
                    edge_context_drift_surfaces,
                    exclusions,
                ),
                {"resolution_context_digest": "0" * 64},
            ),
            _hostile_witness(
                "unknown_target_predicate",
                lambda: validate_synthetic_fixture(
                    unknown_predicate_discovery,
                    unknown_predicate_surfaces,
                    exclusions,
                ),
                {"target_predicate": "unknown"},
            ),
            _hostile_witness(
                "target_predicate_false_in_bound_resolution_context",
                lambda: validate_synthetic_fixture(
                    inactive_cfg_predicate_discovery,
                    inactive_cfg_predicate_surfaces,
                    exclusions,
                ),
                {
                    "target_predicate": 'cfg(target_os = "windows")',
                    "context_cfg": list(observer10.resolution_context.cfg),
                },
            ),
        )
    )
    for field, changed_discovery, changed_surfaces in contract_identity_fixtures:
        hostile_inputs.append(
            _hostile_witness(
                f"provider_contract_identity_{field}_drift",
                lambda changed_discovery=changed_discovery, changed_surfaces=changed_surfaces: (  # noqa: E501
                    validate_synthetic_fixture(
                        changed_discovery,
                        changed_surfaces,
                        exclusions,
                    )
                ),
                {"field": field},
            )
        )
    hostile_inputs.append(
        _hostile_witness(
            "subject_receipt_contract_identity_kind_drift",
            lambda: validate_synthetic_fixture(
                discovery,
                surfaces,
                exclusions,
                subject_receipts=contract_receipt_drift,
            ),
            {
                "expected_kind": node10.contract_identity.kind,
                "receipt_kind": TRUSTED_WIRE_CONTRACT_IDENTITIES[WIRE_08].kind,
            },
        )
    )
    for field, changed_discovery, changed_exclusions in exclusion_optional_fixtures:
        hostile_inputs.append(
            _hostile_witness(
                f"excluded_record_forbidden_{field}",
                lambda changed_discovery=changed_discovery, changed_exclusions=changed_exclusions: (  # noqa: E501
                    validate_synthetic_fixture(
                        changed_discovery,
                        surfaces,
                        changed_exclusions,
                    )
                ),
                {"field": field},
            )
        )
    hostile_inputs.extend(
        (
            _hostile_witness(
                "excluded_record_forbidden_provider_graph",
                lambda: validate_synthetic_fixture(
                    excluded_graph_discovery,
                    surfaces,
                    excluded_graph_exclusions,
                ),
                {"package_id": excluded_graph_root.package_id},
            ),
            _hostile_witness(
                "active_ncp_surface_target_kind_none",
                lambda: validate_synthetic_fixture(
                    (*discovery, no_target_record),
                    (*surfaces, no_target_surface),
                    exclusions,
                ),
                {
                    "surface": no_target_surface.surface_id,
                    "target_kind": "none",
                },
            ),
            _hostile_witness(
                "truncated_stable_surface_id",
                lambda: validate_synthetic_fixture(
                    truncated_id_discovery,
                    truncated_id_surfaces,
                    exclusions,
                ),
                {
                    "surface_id": truncated_surface_id,
                    "required_digest_hex_length": 64,
                },
            ),
            _hostile_witness(
                "truncated_privilege_boundary_identifier",
                lambda: validate_synthetic_fixture(
                    truncated_scoped_discovery,
                    truncated_scoped_surfaces,
                    exclusions,
                ),
                {
                    "credential_set": truncated_scoped_surface.credential_set,
                    "required_digest_hex_length": 64,
                },
            ),
            _hostile_witness(
                "truncated_surface_root_provider_identity",
                lambda: validate_synthetic_fixture(
                    truncated_root_discovery,
                    truncated_root_surfaces,
                    exclusions,
                ),
                {
                    "closure_root_package_id": (
                        truncated_root_surface.closure_root_package_id
                    ),
                    "required_digest_hex_length": 64,
                },
            ),
        )
    )
    revision = _digest("new-target-revision")[:40]
    artifact = _digest("new-target-artifact")
    baseline_inventory_digest = _surface_inventory_digest(
        discovery,
        surfaces,
        exclusions,
    )
    baseline_repin_inventory_digest = _repository_inventory_digest(
        "galadriel",
        discovery,
        surfaces,
        exclusions,
    )
    baseline_subject_receipts = _default_subject_receipts()
    baseline_authorities = _initialize_inventory_authorities(
        discovery,
        surfaces,
        exclusions,
        baseline_subject_receipts,
    )
    galadriel_authority = baseline_authorities["galadriel"]
    parent_created_inventory_selector = (
        _parent_created_uninitialized_inventory_selector("galadriel")
    )
    used_inventory_incarnation = frozenset(
        {
            (
                galadriel_authority.head.inventory_authority_scope,
                galadriel_authority.head.inventory_state_incarnation,
            )
        }
    )
    caller_supplied_uninitialized_selector = _sealed_dataclass(
        replace(
            parent_created_inventory_selector,
            parent_creation_receipt_digest=_digest(
                "caller-supplied-inventory-parent-creation"
            ),
            selector_digest="",
        ),
        "selector_digest",
    )
    sibling_inventory_selector = _parent_created_uninitialized_inventory_selector(
        "galadriel",
        inventory_state_incarnation=_digest("sibling-inventory-incarnation"),
    )
    baseline_repin_authority_args = {
        "inventory_authorities": baseline_authorities,
        "expected_selector_digest": galadriel_authority.selector.selector_digest,
        "expected_head_digest": galadriel_authority.head.state_head_digest,
        "expected_descriptor_digest": (
            galadriel_authority.descriptor.descriptor_digest
        ),
    }
    related_candidate_ids = frozenset({observer10.surface_id, assessor10.surface_id})
    all_candidate_ids = frozenset(
        surface.surface_id
        for surface in surfaces
        if surface.release_state == "candidate"
    )
    authorized_related_receipts = _requested_repin_receipts(
        surfaces,
        related_candidate_ids,
        revision,
        artifact,
    )
    authorized_global_receipts = _requested_repin_receipts(
        surfaces,
        all_candidate_ids,
        revision,
        artifact,
    )
    repin_subject_receipt_digest = next(
        iter(
            {
                _subject_receipt_digest(key, value)
                for key, value in authorized_related_receipts.items()
            }
        )
    )
    installed_galadriel_receipt_digest = _repository_receipt_digests(
        "galadriel",
        baseline_subject_receipts,
    )[0]
    floor_advanced_authority, floor_advance_transition = _transition_inventory_policy(
        galadriel_authority,
        discovery,
        surfaces,
        exclusions,
        baseline_subject_receipts,
        transition_kind=DESCRIPTOR_VERSION_FLOOR_ADVANCE,
        expected_selector_digest=(galadriel_authority.selector.selector_digest),
        expected_head_digest=galadriel_authority.head.state_head_digest,
        descriptor_version_floor=3,
    )
    scanner_revoked_authority, scanner_revoke_transition = _transition_inventory_policy(
        galadriel_authority,
        discovery,
        surfaces,
        exclusions,
        baseline_subject_receipts,
        transition_kind=TRUSTED_SCANNER_AUTHORIZATION_REVOKE,
        expected_selector_digest=(galadriel_authority.selector.selector_digest),
        expected_head_digest=galadriel_authority.head.state_head_digest,
    )
    scanner_restored_authority, scanner_grant_transition = _transition_inventory_policy(
        scanner_revoked_authority,
        discovery,
        surfaces,
        exclusions,
        baseline_subject_receipts,
        transition_kind=TRUSTED_SCANNER_AUTHORIZATION_GRANT,
        expected_selector_digest=(scanner_revoked_authority.selector.selector_digest),
        expected_head_digest=(scanner_revoked_authority.head.state_head_digest),
    )
    subject_revoked_authority, subject_revoke_transition = _transition_inventory_policy(
        galadriel_authority,
        discovery,
        surfaces,
        exclusions,
        baseline_subject_receipts,
        transition_kind=TRUSTED_SUBJECT_AUTHORIZATION_REVOKE,
        expected_selector_digest=(galadriel_authority.selector.selector_digest),
        expected_head_digest=galadriel_authority.head.state_head_digest,
        subject_receipt_digest=installed_galadriel_receipt_digest,
    )
    subject_restored_authority, subject_grant_transition = _transition_inventory_policy(
        subject_revoked_authority,
        discovery,
        surfaces,
        exclusions,
        baseline_subject_receipts,
        transition_kind=TRUSTED_SUBJECT_AUTHORIZATION_GRANT,
        expected_selector_digest=(subject_revoked_authority.selector.selector_digest),
        expected_head_digest=(subject_revoked_authority.head.state_head_digest),
        subject_receipt_digest=installed_galadriel_receipt_digest,
    )
    repin_subject_revoked_authority, repin_subject_revoke_transition = (
        _transition_inventory_policy(
            galadriel_authority,
            discovery,
            surfaces,
            exclusions,
            baseline_subject_receipts,
            transition_kind=TRUSTED_SUBJECT_AUTHORIZATION_REVOKE,
            expected_selector_digest=(galadriel_authority.selector.selector_digest),
            expected_head_digest=galadriel_authority.head.state_head_digest,
            subject_receipt_digest=repin_subject_receipt_digest,
        )
    )
    floor_advanced_authorities = dict(baseline_authorities)
    floor_advanced_authorities["galadriel"] = floor_advanced_authority
    scanner_revoked_authorities = dict(baseline_authorities)
    scanner_revoked_authorities["galadriel"] = scanner_revoked_authority
    subject_revoked_authorities = dict(baseline_authorities)
    subject_revoked_authorities["galadriel"] = subject_revoked_authority
    repin_subject_revoked_authorities = dict(baseline_authorities)
    repin_subject_revoked_authorities["galadriel"] = repin_subject_revoked_authority
    scanner_bytes_substitution = _sealed_dataclass(
        replace(
            galadriel_authority.trusted_scanner_authorization_state,
            scanner_executable_digest=_digest("substituted-scanner-executable"),
            state_digest="",
        ),
        "state_digest",
    )
    scanner_bytes_substitution_authority = replace(
        galadriel_authority,
        trusted_scanner_authorization_state=scanner_bytes_substitution,
    )
    attacker_revision = "d" * 40
    attacker_artifact = "e" * 64
    attacker_self_receipts = _requested_repin_receipts(
        surfaces,
        related_candidate_ids,
        attacker_revision,
        attacker_artifact,
    )
    forged_pre_repin_discovery = _replace_discovery(
        discovery,
        observer10.key,
        runtime_entrypoint=f"{observer10.key.root}/bin/forged_observer",
    )
    immutable_related_key = replace(
        observer10.key,
        target="immutable_observer",
        activation_profile="immutable-observer",
    )
    immutable_related_surface = replace(
        observer10,
        surface_id=_stable_surface_id(immutable_related_key),
        key=immutable_related_key,
        release_state="immutable_release",
        subject_kind="published_package",
        subject_label="v1.0.0",
    )
    hostile_inputs.extend(
        [
            _hostile_witness(
                "candidate_repin_group_contains_immutable_subject",
                lambda: _resolve_repin_group(
                    (*surfaces, immutable_related_surface),
                    observer10.surface_id,
                ),
                {
                    "target": observer10.surface_id,
                    "immutable_related": immutable_related_surface.surface_id,
                },
            ),
            _hostile_witness(
                "repin_rejects_forged_prestate_discovery",
                lambda: _repin(
                    forged_pre_repin_discovery,
                    surfaces,
                    exclusions,
                    observer10.surface_id,
                    revision,
                    artifact,
                    expected_inventory_digest=_surface_inventory_digest(
                        *_repository_inventory_materials(
                            "galadriel",
                            forged_pre_repin_discovery,
                            surfaces,
                            exclusions,
                        )
                    ),
                    expected_affected_ids=related_candidate_ids,
                    authorized_new_receipts=authorized_related_receipts,
                    **baseline_repin_authority_args,
                    global_bug=False,
                ),
                {
                    "surface": observer10.surface_id,
                    "forged_runtime": (f"{observer10.key.root}/bin/forged_observer"),
                },
            ),
            _hostile_witness(
                "repin_compare_and_swap_digest_mismatch",
                lambda: _repin(
                    discovery,
                    surfaces,
                    exclusions,
                    observer10.surface_id,
                    revision,
                    artifact,
                    expected_inventory_digest="0" * 64,
                    expected_affected_ids=related_candidate_ids,
                    authorized_new_receipts=authorized_related_receipts,
                    **baseline_repin_authority_args,
                    global_bug=False,
                ),
                {"expected_inventory_digest": "0" * 64},
            ),
            _hostile_witness(
                "repin_wrong_closure_group",
                lambda: _repin(
                    discovery,
                    surfaces,
                    exclusions,
                    observer10.surface_id,
                    revision,
                    artifact,
                    expected_inventory_digest=baseline_repin_inventory_digest,
                    expected_affected_ids=frozenset({observer10.surface_id}),
                    authorized_new_receipts=authorized_related_receipts,
                    **baseline_repin_authority_args,
                    global_bug=False,
                ),
                {
                    "authorized": [observer10.surface_id],
                    "derived": sorted(related_candidate_ids),
                },
            ),
            _hostile_witness(
                "immutable_release_repin",
                lambda: _repin(
                    discovery,
                    surfaces,
                    exclusions,
                    observer08.surface_id,
                    revision,
                    artifact,
                    expected_inventory_digest=baseline_repin_inventory_digest,
                    expected_affected_ids=frozenset({observer08.surface_id}),
                    authorized_new_receipts={},
                    **baseline_repin_authority_args,
                    global_bug=False,
                ),
                {
                    "surface": observer08.surface_id,
                    "release_state": observer08.release_state,
                },
            ),
            _hostile_witness(
                "repin_untrusted_new_subject",
                lambda: _repin(
                    discovery,
                    surfaces,
                    exclusions,
                    observer10.surface_id,
                    revision,
                    artifact,
                    expected_inventory_digest=baseline_repin_inventory_digest,
                    expected_affected_ids=related_candidate_ids,
                    authorized_new_receipts={},
                    **baseline_repin_authority_args,
                    global_bug=False,
                ),
                {
                    "surface": observer10.surface_id,
                    "revision": revision,
                },
            ),
            _hostile_witness(
                "repin_caller_self_authorized_arbitrary_subject",
                lambda: _repin(
                    discovery,
                    surfaces,
                    exclusions,
                    observer10.surface_id,
                    attacker_revision,
                    attacker_artifact,
                    expected_inventory_digest=baseline_repin_inventory_digest,
                    expected_affected_ids=related_candidate_ids,
                    authorized_new_receipts=attacker_self_receipts,
                    **baseline_repin_authority_args,
                    global_bug=False,
                ),
                {
                    "revision": attacker_revision,
                    "artifact": attacker_artifact,
                    "caller_supplied_receipt": True,
                },
            ),
            _hostile_witness(
                "repin_new_subject_receipt_scope_mismatch",
                lambda: _repin(
                    discovery,
                    surfaces,
                    exclusions,
                    observer10.surface_id,
                    revision,
                    artifact,
                    expected_inventory_digest=baseline_repin_inventory_digest,
                    expected_affected_ids=related_candidate_ids,
                    authorized_new_receipts=authorized_global_receipts,
                    **baseline_repin_authority_args,
                    global_bug=False,
                ),
                {
                    "authorized_receipt_count": len(authorized_global_receipts),
                    "required_receipt_count": len(authorized_related_receipts),
                },
            ),
        ]
    )
    hostile_inputs.extend(
        [
            _hostile_witness(
                "repin_prepared_before_descriptor_floor_advance",
                lambda: _repin(
                    discovery,
                    surfaces,
                    exclusions,
                    observer10.surface_id,
                    revision,
                    artifact,
                    inventory_authorities=floor_advanced_authorities,
                    expected_selector_digest=(
                        galadriel_authority.selector.selector_digest
                    ),
                    expected_head_digest=(galadriel_authority.head.state_head_digest),
                    expected_descriptor_digest=(
                        galadriel_authority.descriptor.descriptor_digest
                    ),
                    expected_inventory_digest=baseline_repin_inventory_digest,
                    expected_affected_ids=related_candidate_ids,
                    authorized_new_receipts=authorized_related_receipts,
                    global_bug=False,
                ),
                {
                    "prepared_selector": (galadriel_authority.selector.selector_digest),
                    "installed_selector": (
                        floor_advanced_authority.selector.selector_digest
                    ),
                    "installed_floor": (
                        floor_advanced_authority.head.trusted_descriptor_version_floor
                    ),
                },
            ),
            _hostile_witness(
                "repin_prepared_before_scanner_revocation",
                lambda: _repin(
                    discovery,
                    surfaces,
                    exclusions,
                    observer10.surface_id,
                    revision,
                    artifact,
                    inventory_authorities=scanner_revoked_authorities,
                    expected_selector_digest=(
                        galadriel_authority.selector.selector_digest
                    ),
                    expected_head_digest=(galadriel_authority.head.state_head_digest),
                    expected_descriptor_digest=(
                        galadriel_authority.descriptor.descriptor_digest
                    ),
                    expected_inventory_digest=baseline_repin_inventory_digest,
                    expected_affected_ids=related_candidate_ids,
                    authorized_new_receipts=authorized_related_receipts,
                    global_bug=False,
                ),
                {
                    "prepared_scanner_state": (
                        galadriel_authority.head.trusted_scanner_authorization_state_digest
                    ),
                    "installed_scanner_state": (
                        scanner_revoked_authority.head.trusted_scanner_authorization_state_digest
                    ),
                },
            ),
            _hostile_witness(
                "repin_under_revoked_scanner_authorization",
                lambda: _repin(
                    discovery,
                    surfaces,
                    exclusions,
                    observer10.surface_id,
                    revision,
                    artifact,
                    inventory_authorities=scanner_revoked_authorities,
                    expected_selector_digest=(
                        scanner_revoked_authority.selector.selector_digest
                    ),
                    expected_head_digest=(
                        scanner_revoked_authority.head.state_head_digest
                    ),
                    expected_descriptor_digest=(
                        scanner_revoked_authority.descriptor.descriptor_digest
                    ),
                    expected_inventory_digest=baseline_repin_inventory_digest,
                    expected_affected_ids=related_candidate_ids,
                    authorized_new_receipts=authorized_related_receipts,
                    global_bug=False,
                ),
                {
                    "authority_status": (
                        scanner_revoked_authority.head.inventory_authority_status
                    ),
                    "scan_receipt_eligibility": (
                        scanner_revoked_authority.head.scan_receipt_eligibility
                    ),
                },
            ),
            _hostile_witness(
                "repin_prepared_before_subject_revocation",
                lambda: _repin(
                    discovery,
                    surfaces,
                    exclusions,
                    observer10.surface_id,
                    revision,
                    artifact,
                    inventory_authorities=subject_revoked_authorities,
                    expected_selector_digest=(
                        galadriel_authority.selector.selector_digest
                    ),
                    expected_head_digest=(galadriel_authority.head.state_head_digest),
                    expected_descriptor_digest=(
                        galadriel_authority.descriptor.descriptor_digest
                    ),
                    expected_inventory_digest=baseline_repin_inventory_digest,
                    expected_affected_ids=related_candidate_ids,
                    authorized_new_receipts=authorized_related_receipts,
                    global_bug=False,
                ),
                {
                    "revoked_subject_receipt_digest": (
                        installed_galadriel_receipt_digest
                    ),
                    "installed_selector": (
                        subject_revoked_authority.selector.selector_digest
                    ),
                },
            ),
            _hostile_witness(
                "repin_requested_subject_revoked_in_current_authority",
                lambda: _repin(
                    discovery,
                    surfaces,
                    exclusions,
                    observer10.surface_id,
                    revision,
                    artifact,
                    inventory_authorities=repin_subject_revoked_authorities,
                    expected_selector_digest=(
                        repin_subject_revoked_authority.selector.selector_digest
                    ),
                    expected_head_digest=(
                        repin_subject_revoked_authority.head.state_head_digest
                    ),
                    expected_descriptor_digest=(
                        repin_subject_revoked_authority.descriptor.descriptor_digest
                    ),
                    expected_inventory_digest=baseline_repin_inventory_digest,
                    expected_affected_ids=related_candidate_ids,
                    authorized_new_receipts=authorized_related_receipts,
                    global_bug=False,
                ),
                {
                    "authority_status": (
                        repin_subject_revoked_authority.head.inventory_authority_status
                    ),
                    "revoked_requested_subject_receipt": (repin_subject_receipt_digest),
                },
            ),
            _hostile_witness(
                "inventory_policy_transition_losing_selector_cas",
                lambda: _transition_inventory_policy(
                    galadriel_authority,
                    discovery,
                    surfaces,
                    exclusions,
                    baseline_subject_receipts,
                    transition_kind=TRUSTED_SCANNER_AUTHORIZATION_REVOKE,
                    expected_selector_digest="0" * 64,
                    expected_head_digest=(galadriel_authority.head.state_head_digest),
                ),
                {
                    "expected_selector": "0" * 64,
                    "installed_selector": (
                        galadriel_authority.selector.selector_digest
                    ),
                },
            ),
            _hostile_witness(
                "scanner_authorization_bytes_substituted_behind_head_digest",
                lambda: _validate_authority(
                    scanner_bytes_substitution_authority,
                    discovery,
                    surfaces,
                    exclusions,
                    baseline_subject_receipts,
                ),
                {
                    "head_scanner_state_digest": (
                        galadriel_authority.head.trusted_scanner_authorization_state_digest
                    ),
                    "substituted_scanner_state_digest": (
                        scanner_bytes_substitution.state_digest
                    ),
                },
            ),
        ]
    )
    output_self_hash_mutant = replace(
        galadriel_authority.descriptor,
        surface_input_manifest_digests=(
            *galadriel_authority.descriptor.surface_input_manifest_digests,
            galadriel_authority.descriptor.descriptor_digest,
        ),
    )
    coherent_sibling_head = _build_inventory_head(
        galadriel_authority.descriptor,
        discovery,
        surfaces,
        exclusions,
        baseline_subject_receipts,
        inventory_authority_scope=(galadriel_authority.head.inventory_authority_scope),
        inventory_state_incarnation=(
            galadriel_authority.head.inventory_state_incarnation
        ),
        state_version=galadriel_authority.head.state_version + 1,
        trusted_descriptor_version_floor=(
            galadriel_authority.head.trusted_descriptor_version_floor
        ),
        inventory_authority_status=(
            galadriel_authority.head.inventory_authority_status
        ),
        authorized_subject_receipt_digests=(
            galadriel_authority.authorized_subject_receipt_digests
        ),
        trusted_subject_authorization_state=(
            galadriel_authority.trusted_subject_authorization_state
        ),
        trusted_scanner_authorization_state=(
            galadriel_authority.trusted_scanner_authorization_state
        ),
        scanner_policy_digest=galadriel_authority.head.scanner_policy_digest,
        scanner_policy_version=galadriel_authority.head.scanner_policy_version,
        scan_receipt_eligibility=(galadriel_authority.head.scan_receipt_eligibility),
        prior_inventory_head_digest=galadriel_authority.head.state_head_digest,
    )
    hostile_inputs.extend(
        [
            _hostile_witness(
                "repin_stale_installed_selector_cas",
                lambda: _repin(
                    discovery,
                    surfaces,
                    exclusions,
                    observer10.surface_id,
                    revision,
                    artifact,
                    inventory_authorities=baseline_authorities,
                    expected_selector_digest="0" * 64,
                    expected_head_digest=galadriel_authority.head.state_head_digest,
                    expected_descriptor_digest=(
                        galadriel_authority.descriptor.descriptor_digest
                    ),
                    expected_inventory_digest=baseline_repin_inventory_digest,
                    expected_affected_ids=related_candidate_ids,
                    authorized_new_receipts=authorized_related_receipts,
                    global_bug=False,
                ),
                {
                    "installed_selector": (
                        galadriel_authority.selector.selector_digest
                    ),
                    "stale_selector": "0" * 64,
                },
            ),
            _hostile_witness(
                "repin_sibling_inventory_head_cas",
                lambda: _repin(
                    discovery,
                    surfaces,
                    exclusions,
                    observer10.surface_id,
                    revision,
                    artifact,
                    inventory_authorities=baseline_authorities,
                    expected_selector_digest=(
                        galadriel_authority.selector.selector_digest
                    ),
                    expected_head_digest=coherent_sibling_head.state_head_digest,
                    expected_descriptor_digest=(
                        galadriel_authority.descriptor.descriptor_digest
                    ),
                    expected_inventory_digest=baseline_repin_inventory_digest,
                    expected_affected_ids=related_candidate_ids,
                    authorized_new_receipts=authorized_related_receipts,
                    global_bug=False,
                ),
                {
                    "installed_head": galadriel_authority.head.state_head_digest,
                    "sibling_head": coherent_sibling_head.state_head_digest,
                    "shared_prior": galadriel_authority.head.state_head_digest,
                },
            ),
            _hostile_witness(
                "surface_inventory_genesis_reuse",
                lambda: _genesis_inventory_authority(
                    "galadriel",
                    discovery,
                    surfaces,
                    exclusions,
                    baseline_subject_receipts,
                    uninitialized_selector=galadriel_authority.selector,
                ),
                {
                    "selector_status": galadriel_authority.selector.status,
                    "genesis_consumed": (galadriel_authority.selector.genesis_consumed),
                },
            ),
            _hostile_witness(
                "surface_inventory_post_use_uninitialized_reset",
                lambda: _genesis_inventory_authority(
                    "galadriel",
                    discovery,
                    surfaces,
                    exclusions,
                    baseline_subject_receipts,
                    uninitialized_selector=parent_created_inventory_selector,
                    used_inventory_state_incarnations=used_inventory_incarnation,
                ),
                {
                    "selector_status": "UNINITIALIZED",
                    "reused_incarnation": (
                        parent_created_inventory_selector.inventory_state_incarnation
                    ),
                },
            ),
            _hostile_witness(
                "surface_inventory_storage_loss_recreated_slot",
                lambda: _genesis_inventory_authority(
                    "galadriel",
                    discovery,
                    surfaces,
                    exclusions,
                    baseline_subject_receipts,
                    used_inventory_state_incarnations=used_inventory_incarnation,
                ),
                {
                    "prior_slot_lost": True,
                    "recreated_status": "UNINITIALIZED",
                },
            ),
            _hostile_witness(
                "surface_inventory_caller_supplied_uninitialized",
                lambda: _genesis_inventory_authority(
                    "galadriel",
                    discovery,
                    surfaces,
                    exclusions,
                    baseline_subject_receipts,
                    uninitialized_selector=caller_supplied_uninitialized_selector,
                ),
                {
                    "parent_creation_receipt": (
                        caller_supplied_uninitialized_selector.parent_creation_receipt_digest
                    ),
                    "trusted": False,
                },
            ),
            _hostile_witness(
                "surface_inventory_sibling_genesis",
                lambda: _genesis_inventory_authority(
                    "galadriel",
                    discovery,
                    surfaces,
                    exclusions,
                    baseline_subject_receipts,
                    uninitialized_selector=sibling_inventory_selector,
                ),
                {
                    "installed_incarnation": (
                        galadriel_authority.head.inventory_state_incarnation
                    ),
                    "sibling_incarnation": (
                        sibling_inventory_selector.inventory_state_incarnation
                    ),
                },
            ),
            _hostile_witness(
                "surface_inventory_authenticated_incarnation_reuse",
                lambda: _genesis_inventory_authority(
                    "galadriel",
                    discovery,
                    surfaces,
                    exclusions,
                    baseline_subject_receipts,
                    uninitialized_selector=sibling_inventory_selector,
                    trusted_parent_creation_receipt_digests=frozenset(
                        {sibling_inventory_selector.parent_creation_receipt_digest}
                    ),
                    used_inventory_state_incarnations=frozenset(
                        {
                            (
                                sibling_inventory_selector.inventory_authority_scope,
                                sibling_inventory_selector.inventory_state_incarnation,
                            )
                        }
                    ),
                ),
                {
                    "parent_creation_receipt_trusted": True,
                    "incarnation_already_used": True,
                },
            ),
            _hostile_witness(
                "output_descriptor_self_hash",
                lambda: _validate_output_descriptor(
                    output_self_hash_mutant,
                    discovery,
                    surfaces,
                    exclusions,
                ),
                {
                    "output_descriptor": OUTPUT_INVENTORY_DESCRIPTOR_PATH,
                    "self_digest": galadriel_authority.descriptor.descriptor_digest,
                },
            ),
            _hostile_witness(
                "cross_repository_repin_has_no_atomic_fleet_state",
                lambda: _repin(
                    discovery,
                    surfaces,
                    exclusions,
                    observer10.surface_id,
                    revision,
                    artifact,
                    expected_inventory_digest=baseline_repin_inventory_digest,
                    expected_affected_ids=related_candidate_ids,
                    authorized_new_receipts=authorized_global_receipts,
                    **baseline_repin_authority_args,
                    global_bug=True,
                ),
                {
                    "target_repository": "galadriel",
                    "other_repository": "engram",
                },
            ),
            _hostile_witness(
                "repin_lost_compare_and_swap",
                lambda: _repin(
                    discovery,
                    surfaces,
                    exclusions,
                    observer10.surface_id,
                    revision,
                    artifact,
                    expected_inventory_digest=baseline_repin_inventory_digest,
                    expected_affected_ids=related_candidate_ids,
                    authorized_new_receipts=authorized_related_receipts,
                    **baseline_repin_authority_args,
                    global_bug=False,
                    persist=False,
                ),
                {
                    "staged": True,
                    "installed_selector_advanced": False,
                },
            ),
        ]
    )
    (
        correct_repin_discovery,
        correct_repin,
        correct_repin_receipts,
        correct_repin_authorities,
        correct_repin_transition,
    ) = _repin(
        discovery,
        surfaces,
        exclusions,
        observer10.surface_id,
        revision,
        artifact,
        expected_inventory_digest=baseline_repin_inventory_digest,
        expected_affected_ids=related_candidate_ids,
        authorized_new_receipts=authorized_related_receipts,
        **baseline_repin_authority_args,
        global_bug=False,
    )
    global_changed = set(all_candidate_ids)
    future_inventory_discovery = (*discovery, future_record)
    future_inventory_surfaces = (*surfaces, future_surface)
    future_inventory_authorities = _initialize_inventory_authorities(
        future_inventory_discovery,
        future_inventory_surfaces,
        exclusions,
        future_receipts,
    )
    future_galadriel_authority = future_inventory_authorities["galadriel"]
    (
        _,
        future_preserving_repin,
        future_preserving_receipts,
        future_preserving_authorities,
        _,
    ) = _repin(
        future_inventory_discovery,
        future_inventory_surfaces,
        exclusions,
        observer10.surface_id,
        revision,
        artifact,
        expected_inventory_digest=_repository_inventory_digest(
            "galadriel",
            future_inventory_discovery,
            future_inventory_surfaces,
            exclusions,
        ),
        expected_affected_ids=related_candidate_ids,
        authorized_new_receipts=authorized_related_receipts,
        scan_snapshot=_extended_scan_snapshot(future_inventory_discovery),
        deployment_topology=_extended_deployment_topology(future_inventory_surfaces),
        subject_receipts=future_receipts,
        inventory_authorities=future_inventory_authorities,
        expected_selector_digest=(future_galadriel_authority.selector.selector_digest),
        expected_head_digest=future_galadriel_authority.head.state_head_digest,
        expected_descriptor_digest=(
            future_galadriel_authority.descriptor.descriptor_digest
        ),
        global_bug=False,
    )
    correct_changed = set(correct_repin_transition.affected_prior_surface_ids)
    logic_mutants = [
        _executed_logic_mutant_witness(
            name="untargeted_revision_digest_repin",
            reason="repin changed a surface other than the explicit target",
            witness={
                "target": observer10.surface_id,
                "changed": sorted(global_changed),
            },
            expected=sorted(correct_changed),
            observed=sorted(global_changed),
        )
    ]
    retired_record = next(
        record for record in retired_discovery if record.key == retired_surface.key
    )
    future_after_repin = next(
        surface
        for surface in future_preserving_repin
        if surface.surface_id == future_surface.surface_id
    )
    future_receipt_key = _subject_receipt_key(
        "haldir",
        "immutable_release",
        "published_package",
        WIRE_10,
        "v1.0.0",
        future_node,
    )
    correct_observer_after_repin = next(
        surface
        for surface in correct_repin
        if surface.key.target == observer10.key.target
        and surface.key.role == observer10.key.role
        and surface.key.repository == observer10.key.repository
    )
    correct_observer_provider = next(
        node
        for node in correct_observer_after_repin.provider_nodes
        if node.package_id == correct_observer_after_repin.ncp_provider_package_id
    )
    correct_observer_receipt_key = _subject_receipt_key(
        correct_observer_after_repin.key.repository,
        correct_observer_after_repin.release_state,
        correct_observer_after_repin.subject_kind,
        correct_observer_after_repin.wire,
        correct_observer_after_repin.subject_label,
        correct_observer_provider,
    )
    isolated_boundary_fields = (
        "runtime_entrypoint",
        "deployment_profile",
        "process_namespace",
        "credential_set",
        "security_manifest",
        "route_namespace",
        "state_store",
        "configuration_namespace",
        "evidence_namespace",
        "plant_session_namespace",
    )
    observer_assessor_boundary_pairs = {
        "activation_profile": (
            observer10.key.activation_profile,
            assessor10.key.activation_profile,
        ),
        **{
            field: (
                getattr(observer10, field),
                getattr(assessor10, field),
            )
            for field in isolated_boundary_fields
        },
    }
    inventory_digest = baseline_inventory_digest
    return {
        "fixture_kind": "bounded_synthetic_scan_and_topology_snapshot",
        "post_repin_external_rescan": "NOT RUN",
        "valid_surface_count": len(surfaces),
        "valid_exclusion_count": len(exclusions),
        "inventory_digest": inventory_digest,
        "repository_local_authority_count": len(baseline_authorities),
        "installed_inventory_heads": {
            repository: authority.head.state_head_digest
            for repository, authority in sorted(baseline_authorities.items())
        },
        "installed_inventory_authorization_states": {
            repository: {
                "authority_status": authority.head.inventory_authority_status,
                "trusted_descriptor_version_floor": (
                    authority.head.trusted_descriptor_version_floor
                ),
                "trusted_subject_authorization_state_digest": (
                    authority.trusted_subject_authorization_state.state_digest
                ),
                "trusted_scanner_authorization_state_digest": (
                    authority.trusted_scanner_authorization_state.state_digest
                ),
            }
            for repository, authority in sorted(baseline_authorities.items())
        },
        "inventory_policy_transition_receipts": {
            "descriptor_floor_advance": (
                floor_advance_transition.commit_receipt.commit_receipt_digest
            ),
            "scanner_revoke": (
                scanner_revoke_transition.commit_receipt.commit_receipt_digest
            ),
            "scanner_restore": (
                scanner_grant_transition.commit_receipt.commit_receipt_digest
            ),
            "subject_revoke": (
                subject_revoke_transition.commit_receipt.commit_receipt_digest
            ),
            "subject_restore": (
                subject_grant_transition.commit_receipt.commit_receipt_digest
            ),
        },
        "post_repin_local_head": (correct_repin_transition.head.state_head_digest),
        "post_repin_commit_receipt": (
            correct_repin_transition.commit_receipt.commit_receipt_digest
        ),
        "shared_lock_valid": (
            len(
                {
                    surface.lock_path
                    for surface in surfaces
                    if surface.key.repository == "galadriel"
                }
            )
            == 1
            and sum(surface.key.repository == "galadriel" for surface in surfaces) > 1
        ),
        "shared_root_distinct_target_valid": (
            observer10.key.root == assessor10.key.root
            and observer10.key.target != assessor10.key.target
        ),
        "shared_same_wire_provider_valid": (
            node10 in observer10.provider_nodes and node10 in assessor10.provider_nodes
        ),
        "role_only_relabel_rejected": any(
            witness["name"] == "observer_receiver_same_build_relabel"
            and witness["rejected"]
            for witness in hostile_inputs
        ),
        "release_subject_kinds_modeled": [
            "git_commit",
            "published_package",
            "synchronized_mirror",
        ],
        "runtime_namespaces_modeled": [
            "activation_profile",
            "deployment_profile",
            "deployment_domain",
            "runtime_entrypoint",
            "process_namespace",
            "credential_set",
            "security_manifest",
            "route_namespace",
            "state_store",
            "configuration_namespace",
            "evidence_namespace",
            "plant_session_namespace",
        ],
        "logic_mutants": logic_mutants,
        "hostile_inputs": hostile_inputs,
        "invariant_witnesses": [
            _invariant_witness(
                "surface_key_build_and_resolution_identity_are_required",
                SurfaceKey.__dataclass_fields__["target_kind"].default is MISSING
                and SurfaceKey.__dataclass_fields__["default_features"].default
                is MISSING
                and SurfaceKey.__dataclass_fields__["resolution_context_digest"].default
                is MISSING,
                {
                    "target_kind_required": True,
                    "default_features_required": True,
                    "resolution_context_digest_required": True,
                },
            ),
            _invariant_witness(
                "resolution_context_document_binds_every_build_input",
                _resolution_context_digest(observer10.resolution_context)
                == observer10.key.resolution_context_digest
                and observer10.resolution_context.effective_features
                == observer10.key.features
                and all(
                    HEX64.fullmatch(value) is not None
                    for value in (
                        observer10.resolution_context.surface_input_manifest_digest,
                        observer10.resolution_context.lock_input_digest,
                        observer10.resolution_context.config_input_digest,
                        observer10.resolution_context.patch_input_digest,
                        observer10.resolution_context.environment_input_digest,
                        observer10.resolution_context.flags_input_digest,
                        observer10.resolution_context.build_script_input_digest,
                        observer10.resolution_context.ci_invocation_digest,
                        observer10.resolution_context.deployment_invocation_digest,
                    )
                ),
                {
                    "context": asdict(observer10.resolution_context),
                    "resolution_context_digest": (
                        observer10.key.resolution_context_digest
                    ),
                },
            ),
            _invariant_witness(
                "different_resolution_contexts_have_distinct_full_surface_ids",
                observer10.key.repository == macos_surface.key.repository
                and observer10.key.root == macos_surface.key.root
                and observer10.key.target == macos_surface.key.target
                and observer10.key.features == macos_surface.key.features
                and observer10.key.resolution_context_digest
                != macos_surface.key.resolution_context_digest
                and observer10.surface_id != macos_surface.surface_id
                and SURFACE_ID.fullmatch(observer10.surface_id) is not None
                and SURFACE_ID.fullmatch(macos_surface.surface_id) is not None,
                {
                    "linux_surface": observer10.surface_id,
                    "macos_surface": macos_surface.surface_id,
                    "linux_context": observer10.key.resolution_context_digest,
                    "macos_context": macos_surface.key.resolution_context_digest,
                },
            ),
            _invariant_witness(
                "target_predicate_is_preserved_and_context_bound",
                len(macos_surface.provider_edges) == 1
                and macos_surface.provider_edges[0].target_predicate
                == 'cfg(target_os = "macos")'
                and macos_surface.provider_edges[0].resolution_context_digest
                == macos_surface.key.resolution_context_digest,
                {
                    "edge": asdict(macos_surface.provider_edges[0]),
                },
            ),
            _invariant_witness(
                "surface_ids_use_the_complete_key_digest",
                all(
                    surface.surface_id
                    == f"surface_{_canonical_digest(asdict(surface.key))}"
                    and SURFACE_ID.fullmatch(surface.surface_id) is not None
                    for surface in (*surfaces, macos_surface)
                ),
                {"digest_hex_length": 64},
            ),
            _invariant_witness(
                "inventory_compare_and_swap_digest_is_order_independent",
                inventory_digest
                == _surface_inventory_digest(
                    tuple(reversed(discovery)),
                    tuple(reversed(surfaces)),
                    tuple(reversed(exclusions)),
                ),
                {"inventory_digest": inventory_digest},
            ),
            _invariant_witness(
                "wire_contract_identity_kinds_are_closed_and_not_equated",
                node08.contract_identity == TRUSTED_WIRE_CONTRACT_IDENTITIES[WIRE_08]
                and node10.contract_identity
                == TRUSTED_WIRE_CONTRACT_IDENTITIES[WIRE_10]
                and node08.contract_identity.kind == "frozen_wire_baseline_artifact"
                and node10.contract_identity.kind == "complete_normative_contract"
                and node08.contract_identity != node10.contract_identity,
                {
                    WIRE_08: asdict(node08.contract_identity),
                    WIRE_10: asdict(node10.contract_identity),
                },
            ),
            _invariant_witness(
                "inactive_exclusions_are_a_closed_empty_optional_union",
                all(
                    not _active(record)
                    and not record.contains_ncp
                    and not record.provider_nodes
                    and not record.provider_edges
                    and record.closure_root_package_id is None
                    and all(
                        getattr(record, field) is None
                        for field, _ in excluded_optional_values
                    )
                    for record in discovery[-2:]
                ),
                {
                    "excluded_record_count": 2,
                    "forbidden_optional_field_count": len(excluded_optional_values),
                },
            ),
            _invariant_witness(
                "every_ncp_surface_has_a_real_ecosystem_target",
                all(
                    surface.key.target_kind != "none"
                    and surface.resolution_context.ecosystem
                    in {"cargo", "python_mirror"}
                    for surface in surfaces
                ),
                {
                    "target_kinds": sorted(
                        {surface.key.target_kind for surface in surfaces}
                    )
                },
            ),
            _invariant_witness(
                "input_package_lock_and_runtime_locators_are_separate",
                all(
                    surface.surface_input_manifest_path == SURFACE_INPUT_MANIFEST_PATH
                    and OUTPUT_INVENTORY_DESCRIPTOR_PATH
                    not in {
                        surface.surface_input_manifest_path,
                        surface.manifest_path,
                        surface.lock_path,
                        surface.runtime_entrypoint,
                    }
                    for surface in surfaces
                )
                and observer08.locator_kind == "cargo_target"
                and observer08.manifest_path == "crates/galadriel-ncp/Cargo.toml"
                and observer08.key.target == "galadriel_ncp"
                and observer08.key.target_kind == "lib"
                and source_qualified_surface.locator_kind == "cargo_target"
                and source_qualified_surface.key.target == "ncp-observe"
                and source_qualified_surface.key.target_kind == "bin"
                and source_qualified_surface.lock_path
                == "crates/ncp-observer/Cargo.lock"
                and engram10.locator_kind == "python_mirror"
                and engram10.surface_input_manifest_path == SURFACE_INPUT_MANIFEST_PATH
                and engram10.manifest_path == "backend/requirements.txt"
                and engram10.lock_path == "ncp/.mirror-ref"
                and engram10.runtime_entrypoint == "backend/neurocontrol/protocol.py",
                {
                    "engram": {
                        "input_manifest": engram10.surface_input_manifest_path,
                        "package_manifest": engram10.manifest_path,
                        "lock": engram10.lock_path,
                        "runtime": engram10.runtime_entrypoint,
                    },
                    "cargo_targets": [
                        {
                            "root": observer08.key.root,
                            "target": observer08.key.target,
                            "target_kind": observer08.key.target_kind,
                            "input_manifest": observer08.surface_input_manifest_path,
                            "package_manifest": observer08.manifest_path,
                            "lock": observer08.lock_path,
                        },
                        {
                            "root": source_qualified_surface.key.root,
                            "target": source_qualified_surface.key.target,
                            "target_kind": (source_qualified_surface.key.target_kind),
                            "input_manifest": (
                                source_qualified_surface.surface_input_manifest_path
                            ),
                            "package_manifest": source_qualified_surface.manifest_path,
                            "lock": source_qualified_surface.lock_path,
                        },
                    ],
                },
            ),
            _invariant_witness(
                "synthetic_scan_snapshot_binds_full_record_content",
                _baseline_scan_snapshot()
                == {record.key: record.record_digest for record in discovery}
                and _baseline_scan_snapshot()
                != {record.key: record.record_digest for record in retired_discovery},
                {
                    "record_count": len(discovery),
                    "fixture_kind": "synthetic",
                },
            ),
            _invariant_witness(
                "same_root_distinct_target_surfaces_are_valid",
                observer10.key.root == assessor10.key.root
                and observer10.key.target != assessor10.key.target,
                {
                    "observer": asdict(observer10.key),
                    "assessor": asdict(assessor10.key),
                },
            ),
            _invariant_witness(
                "role_profile_relabel_does_not_create_build_isolation",
                role_variant.root == observer10.key.root
                and role_variant.target == observer10.key.target
                and role_variant.features == observer10.key.features
                and role_variant.resolution_context_digest
                == observer10.key.resolution_context_digest
                and (
                    role_variant.role,
                    role_variant.activation_profile,
                )
                != (
                    observer10.key.role,
                    observer10.key.activation_profile,
                )
                and any(
                    witness["name"] == "observer_receiver_same_build_relabel"
                    and witness["rejected"]
                    for witness in hostile_inputs
                ),
                {
                    "first": asdict(observer10.key),
                    "second": asdict(role_variant),
                },
            ),
            _invariant_witness(
                "shared_same_wire_provider_is_valid",
                node10 in observer10.provider_nodes
                and node10 in assessor10.provider_nodes,
                {"package_id": node10.package_id},
            ),
            _invariant_witness(
                "shared_lock_is_evaluated_per_surface",
                observer08.lock_path == observer10.lock_path
                and observer08.wire != observer10.wire,
                {"lock_path": observer08.lock_path},
            ),
            _invariant_witness(
                "candidate_synchronized_mirror_is_representable",
                engram10.wire == WIRE_10
                and engram10.release_state == "candidate"
                and engram10.subject_kind == "synchronized_mirror",
                {
                    "surface": engram10.surface_id,
                    "release_state": engram10.release_state,
                    "subject_kind": engram10.subject_kind,
                },
            ),
            _invariant_witness(
                "future_immutable_wire10_release_is_representable",
                future_surface.wire == WIRE_10
                and future_surface.release_state == "immutable_release"
                and future_surface.subject_kind == "published_package"
                and future_surface.subject_label == "v1.0.0",
                {
                    "surface": future_surface.surface_id,
                    "subject_label": future_surface.subject_label,
                    "receipt_key": [
                        WIRE_10,
                        "v1.0.0",
                        future_node.package_id,
                    ],
                },
            ),
            _invariant_witness(
                "active_non_ncp_root_is_not_an_ncp_surface_or_exclusion",
                ordinary_record.surface_id is None
                and ordinary_record.contains_ncp is False
                and _active(ordinary_record)
                and ordinary_record.key not in {surface.key for surface in surfaces}
                and ordinary_record.key
                not in {exclusion.key for exclusion in exclusions},
                {
                    "key": asdict(ordinary_record.key),
                    "active": _active(ordinary_record),
                    "contains_ncp": ordinary_record.contains_ncp,
                },
            ),
            _invariant_witness(
                "inactive_retired_ncp_surface_is_representable",
                retired_record.surface_id == retired_surface.surface_id
                and retired_record.contains_ncp
                and not _active(retired_record)
                and retired_surface.lifecycle == "retired",
                {
                    "surface": retired_surface.surface_id,
                    "lifecycle": retired_surface.lifecycle,
                    "active": _active(retired_record),
                },
            ),
            _invariant_witness(
                "galadriel_v08_subject_matches_its_exact_git_release",
                immutable_git_surface.release_state == "immutable_release"
                and immutable_git_surface.subject_kind == "git_commit"
                and node08.source_revision == NCP_V08_RELEASE_COMMIT
                and node08.artifact_digest
                == _digest(
                    "git-tree-coordinate:"
                    f"{NCP_V08_RELEASE_COMMIT}:{NCP_V08_RELEASE_TREE}"
                )
                == NCP_V08_SUBJECT_ARTIFACT_SHA256
                and node08.contract_identity
                == TRUSTED_WIRE_CONTRACT_IDENTITIES[WIRE_08]
                and immutable_git_receipts[
                    _subject_receipt_key(
                        "galadriel",
                        "immutable_release",
                        "git_commit",
                        WIRE_08,
                        "v0.8.0",
                        node08,
                    )
                ]
                == (
                    node08.source_revision,
                    node08.artifact_digest,
                    node08.contract_identity,
                ),
                {
                    "surface": immutable_git_surface.surface_id,
                    "subject_kind": immutable_git_surface.subject_kind,
                    "release_commit": NCP_V08_RELEASE_COMMIT,
                    "release_tree": NCP_V08_RELEASE_TREE,
                    "subject_artifact_sha256": (NCP_V08_SUBJECT_ARTIFACT_SHA256),
                },
            ),
            _invariant_witness(
                "source_qualified_ncp_provider_is_representable",
                source_qualified_node.package_name == "ncp-core"
                and source_qualified_node.package_id.startswith("git+https://")
                and source_qualified_surface.ncp_provider_package_id
                == source_qualified_node.package_id,
                {
                    "package_id": source_qualified_node.package_id,
                    "package_name": source_qualified_node.package_name,
                },
            ),
            _invariant_witness(
                "target_kind_distinguishes_same_named_targets",
                target_kind_surface.key.target == observer10.key.target
                and target_kind_surface.key.target_kind != observer10.key.target_kind
                and target_kind_surface.surface_id != observer10.surface_id,
                {
                    "first": {
                        "target": observer10.key.target,
                        "target_kind": observer10.key.target_kind,
                        "surface_id": observer10.surface_id,
                    },
                    "second": {
                        "target": target_kind_surface.key.target,
                        "target_kind": target_kind_surface.key.target_kind,
                        "surface_id": target_kind_surface.surface_id,
                    },
                },
            ),
            _invariant_witness(
                "effective_features_are_package_specific_and_canonical",
                effective_feature_surface.key.features == ("ncp-live",)
                and tuple(sorted(set(effective_feature_surface.key.features)))
                == effective_feature_surface.key.features,
                {
                    "features": list(effective_feature_surface.key.features),
                    "activation_profile": (
                        effective_feature_surface.key.activation_profile
                    ),
                },
            ),
            _invariant_witness(
                "default_feature_mode_is_part_of_surface_identity",
                default_feature_surface.key.default_features
                and not observer10.key.default_features
                and default_feature_surface.surface_id != observer10.surface_id,
                {
                    "disabled_surface": observer10.surface_id,
                    "enabled_surface": default_feature_surface.surface_id,
                },
            ),
            _invariant_witness(
                "same_package_root_targets_share_one_closure_root_identity",
                observer10.key.root == assessor10.key.root
                and observer10.closure_root_package_id
                == assessor10.closure_root_package_id
                == _root_package_identity(observer10.key)[0]
                and len(observer10.closure_root_package_id.rsplit("@", 1)[-1]) == 64
                and next(
                    node
                    for node in observer10.provider_nodes
                    if node.package_id == observer10.closure_root_package_id
                )
                == next(
                    node
                    for node in assessor10.provider_nodes
                    if node.package_id == assessor10.closure_root_package_id
                ),
                {
                    "root": observer10.key.root,
                    "package_id": observer10.closure_root_package_id,
                },
            ),
            _invariant_witness(
                "observer_and_assessor_compose_with_distinct_privilege_boundaries",
                observer10.deployment_domain == assessor10.deployment_domain
                and observer10.capability_class == "observer_read"
                and assessor10.capability_class == "assessment_publish"
                and all(
                    left != right
                    for left, right in observer_assessor_boundary_pairs.values()
                ),
                {
                    "deployment_domain": observer10.deployment_domain,
                    "boundaries": observer_assessor_boundary_pairs,
                },
            ),
            _invariant_witness(
                "one_package_root_can_host_distinct_isolated_wire_surfaces",
                dual_root_08_surface.key.root == dual_root_10_surface.key.root
                and dual_root_08_surface.closure_root_package_id
                == dual_root_10_surface.closure_root_package_id
                and dual_root_08_surface.wire != dual_root_10_surface.wire
                and dual_root_08_surface.ncp_provider_package_id
                != dual_root_10_surface.ncp_provider_package_id
                and dual_root_08_surface.key.target != dual_root_10_surface.key.target
                and dual_root_08_surface.key.activation_profile
                != dual_root_10_surface.key.activation_profile
                and all(
                    getattr(dual_root_08_surface, field)
                    != getattr(dual_root_10_surface, field)
                    for field in isolated_boundary_fields
                ),
                {
                    "root": dual_root_08_surface.key.root,
                    "closure_root": dual_root_08_surface.closure_root_package_id,
                    "surfaces": [
                        {
                            "surface_id": dual_root_08_surface.surface_id,
                            "wire": dual_root_08_surface.wire,
                            "target": dual_root_08_surface.key.target,
                            "activation_profile": (
                                dual_root_08_surface.key.activation_profile
                            ),
                            "runtime_entrypoint": (
                                dual_root_08_surface.runtime_entrypoint
                            ),
                            "process_namespace": (
                                dual_root_08_surface.process_namespace
                            ),
                        },
                        {
                            "surface_id": dual_root_10_surface.surface_id,
                            "wire": dual_root_10_surface.wire,
                            "target": dual_root_10_surface.key.target,
                            "activation_profile": (
                                dual_root_10_surface.key.activation_profile
                            ),
                            "runtime_entrypoint": (
                                dual_root_10_surface.runtime_entrypoint
                            ),
                            "process_namespace": (
                                dual_root_10_surface.process_namespace
                            ),
                        },
                    ],
                    "same_process": (
                        dual_root_08_surface.process_namespace
                        == dual_root_10_surface.process_namespace
                    ),
                },
            ),
            _invariant_witness(
                "privilege_boundary_ids_use_complete_surface_id_digests",
                all(
                    getattr(surface, field)
                    == _surface_scoped_identifier(surface.surface_id, label)
                    and len(getattr(surface, field).rsplit("_", 1)[-1]) == 64
                    for surface in surfaces
                    for field, label in SCOPED_SURFACE_FIELDS.items()
                ),
                {
                    "scoped_field_count": len(SCOPED_SURFACE_FIELDS),
                    "digest_hex_length": 64,
                },
            ),
            _invariant_witness(
                "descriptor_version_floor_is_trusted_per_repository",
                all(
                    TRUSTED_DESCRIPTOR_VERSION_FLOORS.get(repository, 2) == 2
                    for repository in {record.key.repository for record in discovery}
                ),
                {
                    "trusted_floors": {
                        repository: TRUSTED_DESCRIPTOR_VERSION_FLOORS.get(
                            repository,
                            2,
                        )
                        for repository in sorted(
                            {record.key.repository for record in discovery}
                        )
                    },
                },
            ),
            _invariant_witness(
                "targeted_repin_changes_only_related_closure_group",
                correct_changed == {observer10.surface_id, assessor10.surface_id},
                {"changed": sorted(correct_changed)},
            ),
            _invariant_witness(
                "repin_preserves_unrelated_surfaces_in_and_outside_repository",
                next(
                    surface
                    for surface in correct_repin
                    if surface.surface_id == observer08.surface_id
                )
                == observer08
                and next(
                    surface
                    for surface in correct_repin
                    if surface.surface_id == engram10.surface_id
                )
                == engram10,
                {
                    "same_repository_unrelated": observer08.surface_id,
                    "other_repository_unrelated": engram10.surface_id,
                },
            ),
            _invariant_witness(
                "targeted_repin_updates_subject_closure_and_discovery_atomically",
                correct_observer_after_repin.subject_revision == revision
                and next(
                    node
                    for node in correct_observer_after_repin.provider_nodes
                    if node.package_id
                    == correct_observer_after_repin.ncp_provider_package_id
                ).source_revision
                == revision
                and next(
                    record
                    for record in correct_repin_discovery
                    if record.surface_id == correct_observer_after_repin.surface_id
                ).subject_revision
                == revision,
                {
                    "prior_surface": observer10.surface_id,
                    "installed_surface": correct_observer_after_repin.surface_id,
                    "revision": revision,
                },
            ),
            _invariant_witness(
                "repin_rederives_input_context_key_edges_discovery_then_output",
                correct_observer_after_repin.resolution_context.surface_input_manifest_digest
                != observer10.resolution_context.surface_input_manifest_digest
                and correct_observer_after_repin.key.resolution_context_digest
                != observer10.key.resolution_context_digest
                and correct_observer_after_repin.surface_id != observer10.surface_id
                and all(
                    edge.resolution_context_digest
                    == correct_observer_after_repin.key.resolution_context_digest
                    for edge in correct_observer_after_repin.provider_edges
                )
                and next(
                    record
                    for record in correct_repin_discovery
                    if record.surface_id == correct_observer_after_repin.surface_id
                ).key
                == correct_observer_after_repin.key
                and correct_repin_transition.descriptor.descriptor_digest
                == correct_repin_transition.head.output_descriptor_digest,
                {
                    "prior_input_manifest_digest": (
                        observer10.resolution_context.surface_input_manifest_digest
                    ),
                    "installed_input_manifest_digest": (
                        correct_observer_after_repin.resolution_context.surface_input_manifest_digest
                    ),
                    "output_descriptor_digest": (
                        correct_repin_transition.descriptor.descriptor_digest
                    ),
                },
            ),
            _invariant_witness(
                "output_descriptor_is_a_generated_last_leaf",
                not _descriptor_payload_contains_output(
                    {
                        "discovery": [
                            asdict(record) for record in correct_repin_discovery
                        ],
                        "surfaces": [asdict(surface) for surface in correct_repin],
                    },
                    correct_repin_transition.descriptor.descriptor_digest,
                )
                and correct_repin_transition.descriptor.descriptor_digest
                not in {surface.artifact_digest for surface in correct_repin},
                {
                    "path": OUTPUT_INVENTORY_DESCRIPTOR_PATH,
                    "descriptor_digest": (
                        correct_repin_transition.descriptor.descriptor_digest
                    ),
                },
            ),
            _invariant_witness(
                "repository_local_selector_is_the_sole_currentness_root",
                correct_repin_transition.persisted
                and correct_repin_transition.selector.installed_head_digest
                == correct_repin_transition.head.state_head_digest
                and correct_repin_authorities["galadriel"].selector
                == correct_repin_transition.selector
                and correct_repin_authorities["engram"]
                == baseline_authorities["engram"],
                {
                    "repository": correct_repin_transition.repository,
                    "selector_version": (
                        correct_repin_transition.selector.selector_version
                    ),
                    "unrelated_repository": "engram",
                },
            ),
            _invariant_witness(
                "inventory_scope_incarnation_and_versions_are_bound",
                (
                    galadriel_authority.head.inventory_authority_scope
                    == galadriel_authority.selector.inventory_authority_scope
                    == correct_repin_transition.head.inventory_authority_scope
                    == correct_repin_transition.selector.inventory_authority_scope
                    and galadriel_authority.head.inventory_state_incarnation
                    == galadriel_authority.selector.inventory_state_incarnation
                    == correct_repin_transition.head.inventory_state_incarnation
                    == (correct_repin_transition.selector.inventory_state_incarnation)
                    and galadriel_authority.head.state_version == 1
                    and correct_repin_transition.head.state_version == 2
                    and correct_repin_transition.selector.selector_version == 2
                    and correct_repin_transition.commit_receipt.state_version == 2
                    and (
                        correct_repin_transition.commit_receipt.inventory_state_incarnation
                        == galadriel_authority.head.inventory_state_incarnation
                    )
                ),
                {
                    "inventory_authority_scope": (
                        galadriel_authority.head.inventory_authority_scope
                    ),
                    "inventory_state_incarnation": (
                        galadriel_authority.head.inventory_state_incarnation
                    ),
                    "genesis_state_version": (galadriel_authority.head.state_version),
                    "repin_state_version": (
                        correct_repin_transition.head.state_version
                    ),
                },
            ),
            _invariant_witness(
                "genesis_is_one_use_and_repin_emits_a_bound_commit_receipt",
                galadriel_authority.commit_receipts[0].transition_kind
                == SURFACE_INVENTORY_GENESIS_FROM_UNINITIALIZED
                and galadriel_authority.selector.genesis_consumed
                and correct_repin_transition.commit_receipt.transition_kind
                == SURFACE_INVENTORY_REPIN_COMPARE_AND_SWAP
                and correct_repin_transition.commit_receipt.prior_head_digest
                == galadriel_authority.head.state_head_digest
                and correct_repin_transition.commit_receipt.installed_head_digest
                == correct_repin_transition.head.state_head_digest,
                {
                    "genesis_receipt": (
                        galadriel_authority.commit_receipts[0].commit_receipt_digest
                    ),
                    "repin_receipt": (
                        correct_repin_transition.commit_receipt.commit_receipt_digest
                    ),
                },
            ),
            _invariant_witness(
                "repin_requires_and_installs_exact_new_subject_receipt",
                correct_repin_receipts[correct_observer_receipt_key]
                == (
                    revision,
                    artifact,
                    correct_observer_provider.contract_identity,
                )
                and authorized_related_receipts[correct_observer_receipt_key]
                == correct_repin_receipts[correct_observer_receipt_key],
                {
                    "receipt_key": list(correct_observer_receipt_key),
                    "receipt": [
                        correct_repin_receipts[correct_observer_receipt_key][0],
                        correct_repin_receipts[correct_observer_receipt_key][1],
                        asdict(correct_repin_receipts[correct_observer_receipt_key][2]),
                    ],
                },
            ),
            _invariant_witness(
                "repin_preserves_unrelated_custom_subject_receipts",
                future_after_repin == future_surface
                and future_preserving_receipts[future_receipt_key]
                == future_receipts[future_receipt_key]
                and future_preserving_authorities["haldir"]
                == future_inventory_authorities["haldir"],
                {
                    "surface": future_surface.surface_id,
                    "receipt_key": list(future_receipt_key),
                },
            ),
            _invariant_witness(
                "inventory_policy_and_repin_share_one_selector_order",
                floor_advance_transition.commit_receipt.prior_selector_digest
                == galadriel_authority.selector.selector_digest
                and scanner_revoke_transition.commit_receipt.prior_selector_digest
                == galadriel_authority.selector.selector_digest
                and subject_revoke_transition.commit_receipt.prior_selector_digest
                == galadriel_authority.selector.selector_digest
                and floor_advance_transition.selector.selector_version == 2
                and scanner_revoke_transition.selector.selector_version == 2
                and subject_revoke_transition.selector.selector_version == 2,
                {
                    "common_prior_selector": (
                        galadriel_authority.selector.selector_digest
                    ),
                    "competing_transition_kinds": [
                        floor_advance_transition.commit_receipt.transition_kind,
                        scanner_revoke_transition.commit_receipt.transition_kind,
                        subject_revoke_transition.commit_receipt.transition_kind,
                        SURFACE_INVENTORY_REPIN_COMPARE_AND_SWAP,
                    ],
                },
            ),
            _invariant_witness(
                "inventory_floor_and_revocations_fail_closed_without_erasing_pins",
                floor_advanced_authority.head.inventory_authority_status
                == "MIGRATION_REQUIRED_DISABLED"
                and scanner_revoked_authority.head.inventory_authority_status
                == "AUTHORIZATION_REVOKED_DISABLED"
                and subject_revoked_authority.head.inventory_authority_status
                == "AUTHORIZATION_REVOKED_DISABLED"
                and floor_advanced_authority.descriptor
                == galadriel_authority.descriptor
                and scanner_revoked_authority.descriptor
                == galadriel_authority.descriptor
                and subject_revoked_authority.descriptor
                == galadriel_authority.descriptor
                and floor_advanced_authority.head.surface_digests
                == galadriel_authority.head.surface_digests
                and scanner_revoked_authority.head.surface_digests
                == galadriel_authority.head.surface_digests
                and subject_revoked_authority.head.surface_digests
                == galadriel_authority.head.surface_digests,
                {
                    "floor_status": (
                        floor_advanced_authority.head.inventory_authority_status
                    ),
                    "scanner_status": (
                        scanner_revoked_authority.head.inventory_authority_status
                    ),
                    "subject_status": (
                        subject_revoked_authority.head.inventory_authority_status
                    ),
                },
            ),
            _invariant_witness(
                "future_subject_revocation_denies_repin_without_disabling_current_pins",
                repin_subject_revoked_authority.head.inventory_authority_status
                == "ACTIVE"
                and (
                    repin_subject_receipt_digest
                    not in (
                        repin_subject_revoked_authority.trusted_subject_authorization_state.authorized_subject_receipt_digests
                    )
                )
                and (
                    repin_subject_revoked_authority.head.surface_digests
                    == galadriel_authority.head.surface_digests
                )
                and (
                    repin_subject_revoke_transition.commit_receipt.transition_kind
                    == TRUSTED_SUBJECT_AUTHORIZATION_REVOKE
                ),
                {
                    "authority_status": (
                        repin_subject_revoked_authority.head.inventory_authority_status
                    ),
                    "revoked_requested_subject_receipt": (repin_subject_receipt_digest),
                    "state_version": (
                        repin_subject_revoked_authority.head.state_version
                    ),
                },
            ),
            _invariant_witness(
                "canonical_authorization_states_are_retained_and_head_bound",
                (
                    galadriel_authority.head.trusted_subject_authorization_state_digest
                    == (
                        galadriel_authority.trusted_subject_authorization_state.state_digest
                    )
                    and (
                        galadriel_authority.head.trusted_scanner_authorization_state_digest
                        == (
                            galadriel_authority.trusted_scanner_authorization_state.state_digest
                        )
                    )
                    and (
                        subject_revoked_authority.trusted_subject_authorization_state.authorization_state_version
                        == 2
                    )
                    and (
                        scanner_revoked_authority.trusted_scanner_authorization_state.authorization_state_version
                        == 2
                    )
                    and (
                        subject_revoked_authority.head.trusted_subject_authorization_state_digest
                        != (
                            galadriel_authority.head.trusted_subject_authorization_state_digest
                        )
                    )
                    and (
                        scanner_revoked_authority.head.trusted_scanner_authorization_state_digest
                        != (
                            galadriel_authority.head.trusted_scanner_authorization_state_digest
                        )
                    )
                ),
                {
                    "subject_state": (
                        galadriel_authority.trusted_subject_authorization_state.state_digest
                    ),
                    "scanner_state": (
                        galadriel_authority.trusted_scanner_authorization_state.state_digest
                    ),
                },
            ),
            _invariant_witness(
                "authorization_restore_is_a_new_same_root_transition",
                scanner_restored_authority.head.inventory_authority_status == "ACTIVE"
                and subject_restored_authority.head.inventory_authority_status
                == "ACTIVE"
                and scanner_grant_transition.commit_receipt.transition_kind
                == TRUSTED_SCANNER_AUTHORIZATION_GRANT
                and subject_grant_transition.commit_receipt.transition_kind
                == TRUSTED_SUBJECT_AUTHORIZATION_GRANT
                and scanner_restored_authority.head.state_version == 3
                and subject_restored_authority.head.state_version == 3
                and scanner_restored_authority.selector.selector_version == 3
                and subject_restored_authority.selector.selector_version == 3,
                {
                    "scanner_restore_version": (
                        scanner_restored_authority.head.state_version
                    ),
                    "subject_restore_version": (
                        subject_restored_authority.head.state_version
                    ),
                },
            ),
        ],
    }


def _result_counts(result: dict[str, Any]) -> dict[str, int]:
    sections = (
        result["observer_projection"],
        result["grant_lifecycle"],
        result["capture_action"],
        result["surface_inventory"],
    )
    executable_mutant_sections = (
        result["observer_projection"],
        result["surface_inventory"],
    )
    semantic_contrast_sections = (
        result["grant_lifecycle"],
        result["capture_action"],
    )
    return {
        "probes": len(sections),
        "finite_cases_evaluated": (
            result["observer_projection"]["case_count"]
            + result["grant_lifecycle"]["case_count"]
            + result["capture_action"]["targeted_action_case_count"]
        ),
        "logic_mutants_killed": sum(
            len(section["logic_mutants"]) for section in executable_mutant_sections
        ),
        "semantic_contrasts_reached": sum(
            len(section["semantic_contrasts"]) for section in semantic_contrast_sections
        ),
        "hostile_inputs_rejected": sum(
            len(section.get("hostile_inputs", ())) for section in sections
        ),
        "invariant_witnesses_reached": sum(
            len(section["invariant_witnesses"]) for section in sections
        ),
        "fault_cases_survived": 0,
    }


def build_result() -> dict[str, Any]:
    result = {
        "schema": "ncp.b01-decision-probe-result.v3",
        "scope": (
            "bounded-observer-lifecycle-capture-and-surface-counterexample-discovery"
        ),
        "claim_boundary": CLAIM_BOUNDARY,
        "observer_projection": _observer_result(),
        "grant_lifecycle": build_grant_lifecycle_result(),
        "capture_action": build_capture_action_result(),
        "surface_inventory": _surface_result(),
    }
    result["counts"] = _result_counts(result)
    return result


def _canonical_result(value: Any) -> str:
    if not isinstance(value, dict):
        raise ProbeError("decision-probe result is not an object")
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def _validate_result_against_canonical(
    value: Any,
    expected_canonical: str,
) -> None:
    if _canonical_result(value) != expected_canonical:
        raise ProbeError(
            "decision-probe result differs from deterministic semantic replay"
        )


def _validated_replay_canonical(
    value: Any,
    replay_builder: Callable[[], dict[str, Any]],
) -> str:
    if not isinstance(value, dict):
        raise ProbeError("decision-probe result is not an object")
    expected_canonical = _canonical_result(replay_builder())
    _validate_result_against_canonical(value, expected_canonical)
    return expected_canonical


def validate_result(value: Any) -> None:
    _validated_replay_canonical(value, build_result)


def _set_path(value: dict[str, Any], path: tuple[str, ...], replacement: Any) -> None:
    cursor: Any = value
    for member in path[:-1]:
        cursor = cursor[member]
    cursor[path[-1]] = replacement


def _must_reject_result(
    baseline: dict[str, Any],
    path: tuple[str, ...],
    replacement: Any,
    expected_canonical: str,
) -> None:
    hostile = copy.deepcopy(baseline)
    _set_path(hostile, path, replacement)
    try:
        _validate_result_against_canonical(hostile, expected_canonical)
    except ProbeError:
        return
    raise ProbeError(f"self-test result mutation passed: {'.'.join(path)}")


def _self_test_replay_oracle_ordering() -> None:
    replay_state = {"phase": "before"}
    builder_observations: list[str] = []

    class MutatingResult(dict[str, str]):
        def items(self):
            replay_state["phase"] = "after"
            return super().items()

    def replay_builder() -> dict[str, str]:
        builder_observations.append(replay_state["phase"])
        return {"phase": replay_state["phase"]}

    hostile = MutatingResult({"phase": "after"})
    try:
        _validated_replay_canonical(
            hostile,
            replay_builder,
        )
    except ProbeError:
        if builder_observations != ["before"]:
            raise ProbeError(
                "self-test replay oracle was not built exactly once before validation"
            ) from None
        if replay_state["phase"] != "after":
            raise ProbeError(
                "self-test did not serialize the hostile replay candidate"
            ) from None
        return
    raise ProbeError("caller-controlled result influenced the replay oracle")


def self_test(result: dict[str, Any]) -> None:
    expected_canonical = _validated_replay_canonical(result, build_result)
    _self_test_replay_oracle_ordering()
    _validate_result_against_canonical(
        json.loads(json.dumps(result, separators=(",", ":"), sort_keys=True)),
        expected_canonical,
    )
    if (
        PYTHON_MIRROR_INPUT_MANIFEST_KEY != ".ncp-surface-inputs.v1.json"
        or OUTPUT_INVENTORY_DESCRIPTOR_PATH != ".ncp-consumer"
    ):
        raise ProbeError("surface input/output descriptor paths are not exact")
    python_context = _python_mirror_resolution_context(())
    exact_input_digest = _context_input_digest(
        "python_mirror",
        ".ncp-surface-inputs.v1.json",
        (),
        "baseline-python-mirror",
    )
    exact_package_manifest_digest = _context_input_digest(
        "python_mirror",
        "backend/requirements.txt",
        (),
        "baseline-python-mirror",
    )
    stale_output_descriptor_digest = _context_input_digest(
        "python_mirror",
        "consumer" + "-descriptor",
        (),
        "baseline-python-mirror",
    )
    exact_output_descriptor_digest = _context_input_digest(
        "python_mirror",
        OUTPUT_INVENTORY_DESCRIPTOR_PATH,
        (),
        "baseline-python-mirror",
    )
    if (
        python_context.surface_input_manifest_digest != exact_input_digest
        or python_context.config_input_digest != exact_package_manifest_digest
        or stale_output_descriptor_digest
        in {
            python_context.surface_input_manifest_digest,
            python_context.config_input_digest,
        }
        or exact_output_descriptor_digest
        in {
            python_context.surface_input_manifest_digest,
            python_context.config_input_digest,
        }
    ):
        raise ProbeError(
            "Python mirror context did not separate input and package manifests"
        )
    mutations = (
        (("schema",), "ncp.b01-decision-probe-result.v999"),
        (("counts", "logic_mutants_killed"), 0),
        (("counts", "semantic_contrasts_reached"), 0),
        (("counts", "hostile_inputs_rejected"), 0),
        (("counts", "invariant_witnesses_reached"), 0),
        (("observer_projection", "admitted"), 0),
        (("grant_lifecycle", "admitted"), 0),
        (("capture_action", "axis_contract_digest"), "0" * 64),
        (("surface_inventory", "inventory_digest"), "0" * 64),
        (
            ("surface_inventory", "shared_lock_valid"),
            not result["surface_inventory"]["shared_lock_valid"],
        ),
    )
    for path, replacement in mutations:
        _must_reject_result(result, path, replacement, expected_canonical)
    missing_fault = copy.deepcopy(result)
    missing_fault["observer_projection"]["logic_mutants"].pop()
    try:
        _validate_result_against_canonical(missing_fault, expected_canonical)
    except ProbeError:
        pass
    else:
        raise ProbeError("self-test missing logic mutant passed")
    missing_contrast = copy.deepcopy(result)
    missing_contrast["capture_action"]["semantic_contrasts"].pop()
    try:
        _validate_result_against_canonical(missing_contrast, expected_canonical)
    except ProbeError:
        pass
    else:
        raise ProbeError("self-test missing semantic contrast passed")
    duplicate_fault = copy.deepcopy(result)
    duplicate_fault["surface_inventory"]["hostile_inputs"].append(
        copy.deepcopy(duplicate_fault["surface_inventory"]["hostile_inputs"][0])
    )
    try:
        _validate_result_against_canonical(duplicate_fault, expected_canonical)
    except ProbeError:
        pass
    else:
        raise ProbeError("self-test duplicate hostile input passed")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    arguments = parser.parse_args()
    result = build_result()
    if arguments.self_test:
        self_test(result)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
