#!/usr/bin/env python3
"""Run the bounded, local, non-normative B01 source-index challenge model.

The model separates source, observer, anchor, transport, lineage, and body
authorities. No synthetic transaction crosses those owners. A pass is not an
implementation, refinement, interoperability, security, safety, review,
certification, or release result. The repository checker binds the exact script
bytes because its standard-input execution has no stable source path.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Any, TypeVar, get_args, get_origin, get_type_hints

MAX_ELIGIBLE_ROOTS = 4
MAX_ISSUANCE_ENTRIES = 8
MAX_GENERATION_SLOTS = 8
MAX_QUEUE_RECORDS = 8
MAX_OBSERVER_OPERATIONS = 8
MAX_OBSERVER_ENROLLMENTS = 4
MAX_OBSERVER_TOMBSTONES = 4
MAX_OBSERVER_RETAINED_BYTES = 65_536
MAX_PRODUCER_NAMESPACES = 4
MAX_LINEAGE_INCARNATIONS_PER_NAMESPACE = 4
MAX_CHALLENGE_BYTES = 256
MAX_CAPSULE_BYTES = 1_024
MAX_REQUESTER_FRAME_BYTES = 4_096
MAX_VERIFIED_TRANSPORT_CONTEXTS = 8
MAX_RETIRED_TRANSPORT_CONTEXTS = 32
MAX_TRANSPORT_SECURITY_EPOCHS = 16
MAX_IDENTIFIER_UTF8_BYTES = 256
MAX_STABLE_KEY_UTF8_BYTES = 2_048
MAX_NAMESPACE_UTF8_BYTES = 768
MAX_PLANT_PROFILE_DOCUMENT_BYTES = 4_096
ANCHOR_RESERVATION_PARTICIPANT_CHARGE = 1
ANCHOR_RESERVATION_BYTE_CHARGE = 16_384
ANCHOR_OWNER_PARTICIPANT_CAP = 4
ANCHOR_OWNER_BYTE_CAP = 65_536
ANCHOR_GLOBAL_PARTICIPANT_CAP = 16
ANCHOR_GLOBAL_BYTE_CAP = 262_144
CLOCK_VALUE_MAX = (1 << 63) - 1
CLOCK_OFFSET_ABS_MAX = (1 << 62) - 1
SPARSE_TREE_HEIGHT = 256
SPARSE_PROOF_BYTES = 8_272
SPARSE_PROOF_MAGIC = b"NCOGSPV1"
SPARSE_SUITE = "OBSERVER_GRANT_SPARSE_MERKLE_SHA256_V1"
SYNTHETIC_PROOF_GOLDEN = {
    "anchor_membership_sha256": (
        "85a97fa7f9891a5bb360af1058b31885fa9ac146d9bde726b413260fbf398283"
    ),
    "anchor_nonmembership_sha256": (
        "ede46fd2fde016706e2f02e1fb4e0817e50ea1da062669259c74d0bd8107c1ca"
    ),
    "anchor_root": ("288e0f5f2402218bbfece930e78bb17cab99717f8d8d6e692fa9e291d1868979"),
    "empty_anchor_root": (
        "d7685b67289e29fe00aabd5ec888f8f7ae35c17dfb0aad5d233a5fa85550fa26"
    ),
    "empty_source_root": (
        "0782f31e15a0fbf0c0b9484cdd6053b6166091f4641901dfb2b7b2280f3574dc"
    ),
    "source_membership_sha256": (
        "b4de2c52b84bf741b5d5077c2da13930129bde683fca8fd9161b99aba3a3101b"
    ),
    "source_nonmembership_sha256": (
        "13d1f9f7ff9210eac659b25af380c6b2d53b974cdf9650b17e61c99acad90729"
    ),
    "source_root": ("982a3974cc77a360e53c5e7a9014da5bcede1decc82e81a1be63acbe48f4e8bb"),
}
CLAIM_BOUNDARY = (
    "This deterministic finite source-index probe challenges only its local "
    "synthetic abstraction. It is not a protocol or implementation proof, "
    "interoperability result, transport-security qualification, plant-safety "
    "evidence, independent review, certification, or release authorization."
)


class ProbeError(RuntimeError):
    pass


Reject = ProbeError


class AvailabilityProfile(StrEnum):
    SOURCE_RETIREMENT_ONLY = "SOURCE_RETIREMENT_ONLY"
    SOURCE_RETIREMENT_OR_INDEPENDENT_CHALLENGE_EXPOSURE_ANCHOR = (
        "SOURCE_RETIREMENT_OR_INDEPENDENT_CHALLENGE_EXPOSURE_ANCHOR"
    )


ANCHOR_AVAILABILITY_PROFILE = (
    AvailabilityProfile.SOURCE_RETIREMENT_OR_INDEPENDENT_CHALLENGE_EXPOSURE_ANCHOR
)
ANCHOR_PROFILE = ANCHOR_AVAILABILITY_PROFILE
SOURCE_ONLY = AvailabilityProfile.SOURCE_RETIREMENT_ONLY
_TOMBSTONE = "PERMANENT_CLOSURE_TOMBSTONE"
_COOPERATIVE = "SOURCE_COOPERATIVELY_RETIRED"
_ISOLATED = "SOURCE_PERMANENTLY_ISOLATED"
_ANCHOR_RETIREMENT = "COOPERATIVE_ANCHOR_RETIREMENT"


class SourceNamespaceBootstrapState(StrEnum):
    ABSENT = "ABSENT"
    RESERVATION_INTENT_PENDING = "PENDING_ANCHOR_CAPACITY_RESERVATION"
    PENDING = "PENDING_NAMESPACE_GENESIS"
    LIVE = "LIVE_NAMESPACE"
    CANCELED = "PERMANENTLY_RETIRED"


class AnchorNamespaceBootstrapState(StrEnum):
    ABSENT = "ABSENT"
    OPEN = "ANCHOR_OPEN"
    FROZEN = "ANCHOR_FROZEN_AFTER_TERMINAL_SOURCE_CLOSURE"
    CANCELED = "ANCHOR_TERMINAL_AFTER_SOURCE_NAMESPACE_CANCELLATION"


class AnchorNamespaceReservationState(StrEnum):
    ABSENT = "ABSENT"
    RESERVED = "RESERVED_PENDING_ANCHOR_GENESIS"
    MATERIALIZED = "MATERIALIZED"
    TERMINAL = "TERMINAL_RETAINED"


class SourceIndexPhase(StrEnum):
    OPEN = "SOURCE_ISSUANCE_OPEN"
    FROZEN = "SOURCE_ISSUANCE_FROZEN_PERMANENTLY_RETIRED"


class RootAdmissionPhase(StrEnum):
    PENDING = "PENDING_ANCHOR_ENROLLMENT"
    ELIGIBLE = "ELIGIBLE"
    CANCELED = "CANCELED_BEFORE_SOURCE_CONFIRMATION"
    FROZEN_PENDING = "FROZEN_BEFORE_SOURCE_CONFIRMATION"


class RegisteredRootAuthorityState(StrEnum):
    ACTIVE = "REGISTERED_ACTIVE"
    RETIREMENT_PENDING = "RETIREMENT_PENDING"
    RETIRED = "PERMANENTLY_RETIRED"


def _retain_opaque(value: object, memo: dict[int, object]) -> object:
    del memo
    return value


class _Opaque:
    __slots__ = ()
    __deepcopy__ = _retain_opaque


class OpaqueRegisteredRootAuthorityCredential(_Opaque):
    __slots__ = ()


_CONFIGURED_REGISTERED_ROOT_AUTHORITY_CREDENTIAL = (
    OpaqueRegisteredRootAuthorityCredential()
)


class AnchorPhase(StrEnum):
    ABSENT = "ANCHOR_SELECTOR_ABSENT_NEVER_USED"
    PENDING_SOURCE_CONFIRMATION = "ANCHOR_GENESIS_PENDING_SOURCE_CONFIRMATION"
    OPEN = "ANCHOR_OPEN"
    FROZEN = "ANCHOR_FROZEN_AFTER_TERMINAL_SOURCE_CLOSURE"
    CANCELED = "ANCHOR_TERMINAL_AFTER_SOURCE_NAMESPACE_CANCELLATION"


class AnchorClosureCause(StrEnum):
    NO_ANCHOR_CLOSURE = "NO_ANCHOR_CLOSURE"
    COOPERATIVE = "COOPERATIVE_SOURCE_PERMANENT_RETIREMENT"
    ISOLATION = "PERMANENT_SOURCE_ACCEPTANCE_AUTHORITY_ISOLATION"


class AnchorClosureEvidenceState(StrEnum):
    NONE = "NO_ANCHOR_CLOSURE_EVIDENCE"
    COOPERATIVE_ONLY = "COOPERATIVE_ONLY"
    ISOLATION_ONLY = "ISOLATION_ONLY"
    COOPERATIVE_AND_ISOLATION = "COOPERATIVE_AND_ISOLATION"


class IndexEntryKind(StrEnum):
    CHALLENGE_ISSUED = "CHALLENGE_ISSUED"
    CANCELED_BEFORE_ISSUANCE = "CANCELED_BEFORE_ISSUANCE"


class SlotState(StrEnum):
    AVAILABLE = "AVAILABLE"
    CONSUMED_BY_ACCEPTED_REQUEST = "CONSUMED_BY_ACCEPTED_REQUEST"
    CANCELED_UNUSED = "CANCELED_UNUSED"
    EXPIRED_UNUSED = "EXPIRED_UNUSED"


class DeliveryGate(StrEnum):
    DIRECT_DELIVERY_READY = "DIRECT_DELIVERY_READY"
    ANCHOR_PAIRED_FRAME_PENDING = "ANCHOR_PAIRED_FRAME_PENDING"
    ANCHOR_PAIRED_FRAME_ADMITTED = "ANCHOR_PAIRED_FRAME_ADMITTED"
    DELIVERY_TERMINAL = "DELIVERY_TERMINAL"


class QueueRecordState(StrEnum):
    MAY_HAVE_BEEN_EXPOSED = "MAY_HAVE_BEEN_EXPOSED"
    TERMINALIZED = "TERMINALIZED"


class HandoffQuiescenceResult(StrEnum):
    # These are closed protocol-state labels, not authentication tokens.
    ZERO_BYTES_ACCEPTED_TOKEN_RELEASED = "ZERO_BYTES_ACCEPTED_TOKEN_RELEASED"  # noqa: S105
    MAY_HAVE_BEEN_EXPOSED_TOKEN_RELEASED = "MAY_HAVE_BEEN_EXPOSED_TOKEN_RELEASED"  # noqa: S105
    OUTCOME_UNKNOWN_DISPATCHER_AND_SOCKET_FENCED = (
        "OUTCOME_UNKNOWN_DISPATCHER_AND_SOCKET_FENCED"
    )


class TransportChannelState(StrEnum):
    ACTIVE = "ACTIVE"
    CLOSED = "CLOSED"
    REVOKED = "REVOKED"


class DistributedClosureState(StrEnum):
    TERMINAL = "DISTRIBUTED_ACCEPTANCE_AUTHORITY_PERMANENTLY_CLOSED"


class LocalOperationState(StrEnum):
    INTENT_PREPARED = "INTENT_PREPARED"
    RESOLVED_WITHOUT_INSTALLATION = "RESOLVED_WITHOUT_INSTALLATION"


class ClosureOrigin(StrEnum):
    SOURCE = "SOURCE_INDEX_FROZEN_PERMANENTLY_RETIRED"
    ANCHOR = "INDEPENDENT_ANCHOR_FROZEN_AFTER_TERMINAL_SOURCE_CLOSURE"


class ClosureEvidenceState(StrEnum):
    SOURCE_ONLY = "SOURCE_ONLY"
    ANCHOR_ONLY = "ANCHOR_ONLY"
    SOURCE_AND_ANCHOR = "SOURCE_AND_ANCHOR"


class ClosureOperationPartitionKind(StrEnum):
    RESOLVE_PREPARED_SOURCE_NO_CHALLENGE = "RESOLVE_PREPARED_SOURCE_NO_CHALLENGE"
    RESOLVE_PREPARED_ANCHOR_NONMEMBERSHIP = "RESOLVE_PREPARED_ANCHOR_NONMEMBERSHIP"
    RESOLVE_PREPARED_ANCHOR_MEMBERSHIP_ACCEPTANCE_PERMANENTLY_CLOSED = (
        "RESOLVE_PREPARED_ANCHOR_MEMBERSHIP_ACCEPTANCE_PERMANENTLY_CLOSED"
    )
    PRESERVE_OPERATION_PHASE_PENDING_EXACT_TERMINAL_RESULT = (
        "PRESERVE_OPERATION_PHASE_PENDING_EXACT_TERMINAL_RESULT"
    )
    PRESERVE_RESOLVED_OR_INSTALLED_CLOSED_HISTORY = (
        "PRESERVE_RESOLVED_OR_INSTALLED_CLOSED_HISTORY"
    )


PRESERVE_CLOSED_HISTORY_PARTITION_KIND = (
    ClosureOperationPartitionKind.PRESERVE_RESOLVED_OR_INSTALLED_CLOSED_HISTORY
)
PRESERVE_PENDING_PARTITION_KIND = (
    ClosureOperationPartitionKind.PRESERVE_OPERATION_PHASE_PENDING_EXACT_TERMINAL_RESULT
)
RESOLVE_SOURCE_NO_CHALLENGE_PARTITION_KIND = (
    ClosureOperationPartitionKind.RESOLVE_PREPARED_SOURCE_NO_CHALLENGE
)
RESOLVE_ANCHOR_NONMEMBERSHIP_PARTITION_KIND = (
    ClosureOperationPartitionKind.RESOLVE_PREPARED_ANCHOR_NONMEMBERSHIP
)
RESOLVE_ANCHOR_MEMBERSHIP_PARTITION_KIND = ClosureOperationPartitionKind(
    "RESOLVE_PREPARED_ANCHOR_MEMBERSHIP_ACCEPTANCE_PERMANENTLY_CLOSED"
)


class ProofContext(StrEnum):
    SOURCE = "SOURCE_ISSUANCE_INDEX"
    ANCHOR = "INDEPENDENT_EXPOSURE_ANCHOR"

    @property
    def wire_byte(self) -> int:
        if self is ProofContext.SOURCE:
            return 0x01
        if self is ProofContext.ANCHOR:
            return 0x02
        raise Reject()


class ProofKind(StrEnum):
    NONMEMBERSHIP = "NONMEMBERSHIP"
    MEMBERSHIP = "MEMBERSHIP"

    @property
    def wire_byte(self) -> int:
        if self is ProofKind.NONMEMBERSHIP:
            return 0x00
        if self is ProofKind.MEMBERSHIP:
            return 0x01
        raise Reject()


class ResolutionOutcome(StrEnum):
    UNRESOLVED = "UNRESOLVED_OPERATION"
    SOURCE_FROZEN_KEY_NONMEMBERSHIP = "FROZEN_KEY_NONMEMBERSHIP"
    SOURCE_FROZEN_CANCELED_MEMBERSHIP = "FROZEN_CANCELED_BEFORE_ISSUANCE_MEMBERSHIP"
    ANCHOR_FROZEN_NONMEMBERSHIP = (
        "NO_ANCHOR_QUALIFIED_EXPOSURE_PROVED_NOT_SOURCE_NONISSUANCE"
    )
    ANCHOR_FROZEN_MEMBERSHIP = "MAY_HAVE_BEEN_EXPOSED_BUT_ACCEPTANCE_PERMANENTLY_CLOSED"
    PRESERVE_EXACT_TERMINAL = "PRESERVE_OPERATION_PHASE_PENDING_EXACT_TERMINAL_RESULT"


@dataclass(frozen=True, order=True)
class StableKey:
    authority_realm: str
    source_kind: str
    logical_source_id: str
    requester_principal: str
    observer_root_incarnation: str
    request_operation: str
    request_kind: str
    logical_target_key: str

    @property
    def source_namespace(self) -> tuple[str, str, str]:
        return (self.authority_realm, self.source_kind, self.logical_source_id)


class OpaqueTransportProducerCapability(_Opaque):
    __slots__ = ()


class OpaqueLiveTransportHandle(_Opaque):
    __slots__ = ()


class OpaqueStateOwnerCredential(_Opaque):
    __slots__ = ()


class OpaqueLineageAuthorityCredential(_Opaque):
    __slots__ = ()


_CONFIGURED_LINEAGE_AUTHORITY_CREDENTIAL = OpaqueLineageAuthorityCredential()


class OpaqueBodyPlantProfileAuthorityCredential(_Opaque):
    __slots__ = ()


_CONFIGURED_BODY_PLANT_PROFILE_AUTHORITY_CREDENTIAL = (
    OpaqueBodyPlantProfileAuthorityCredential()
)
BodyProfileCredential = OpaqueBodyPlantProfileAuthorityCredential


class OpaqueDistributedClosureAuthorityCredential(_Opaque):
    __slots__ = ()


_CONFIGURED_DISTRIBUTED_CLOSURE_AUTHORITY_CREDENTIAL = (
    OpaqueDistributedClosureAuthorityCredential()
)
DistributedClosureCredential = OpaqueDistributedClosureAuthorityCredential


@dataclass(frozen=True)
class VerifiedTransportContext:
    connection_id: str
    authenticated_principal: str
    replay_domain: str
    transport_security_epoch: str
    channel_binding_digest: str
    verification_digest: str
    producer_capability: OpaqueTransportProducerCapability = field(repr=False)
    live_channel_handle: OpaqueLiveTransportHandle = field(repr=False)


@dataclass
class TransportAuthorityStore:
    authority_id: str = "configured-transport-authority-v1"
    security_epoch: str = "transport-security-v1"
    producer_capability: OpaqueTransportProducerCapability = field(
        default_factory=lambda: OpaqueTransportProducerCapability()
    )
    revision: int = 0
    context_capacity: int = MAX_VERIFIED_TRANSPORT_CONTEXTS
    contexts: dict[str, VerifiedTransportContext] = field(default_factory=dict)
    retired_contexts: dict[str, VerifiedTransportContext] = field(default_factory=dict)
    channel_states: dict[str, TransportChannelState] = field(default_factory=dict)
    used_security_epochs: set[str] = field(
        default_factory=lambda: {"transport-security-v1"}
    )
    replay_tombstone_accumulator: str = field(
        default_factory=lambda: _fixture_digest("transport-replay-tombstone-genesis")
    )
    handoff_receipts: dict[str, ProtectedHandoffQuiescenceReceipt] = field(
        default_factory=dict
    )


@dataclass(frozen=True)
class SourceNamespaceAnchorReservationIntent:
    source_namespace: tuple[str, str, str]
    reservation_intent_id: str
    source_owner_key: str
    source_owner_lifetime_slot: str
    lineage_selector_incarnation: str
    source_index_selector_incarnation: str
    anchor_selector_incarnation: str
    availability_profile: AvailabilityProfile
    anchor_authority: str
    commit_digest: str


@dataclass(frozen=True)
class IndependentAnchorNamespaceCapacityReservation:
    reservation_intent: SourceNamespaceAnchorReservationIntent
    reservation_id: str
    receipt_digest: str

    @property
    def source_namespace(self) -> tuple[str, str, str]:
        return self.reservation_intent.source_namespace

    @property
    def source_owner_key(self) -> str:
        return self.reservation_intent.source_owner_key

    @property
    def source_owner_lifetime_slot(self) -> str:
        return self.reservation_intent.source_owner_lifetime_slot

    @property
    def lineage_selector_incarnation(self) -> str:
        return self.reservation_intent.lineage_selector_incarnation

    @property
    def source_index_selector_incarnation(self) -> str:
        return self.reservation_intent.source_index_selector_incarnation

    @property
    def anchor_selector_incarnation(self) -> str:
        return self.reservation_intent.anchor_selector_incarnation

    @property
    def availability_profile(self) -> AvailabilityProfile:
        return self.reservation_intent.availability_profile

    @property
    def anchor_authority(self) -> str:
        return self.reservation_intent.anchor_authority


@dataclass(frozen=True)
class SourceNamespaceAllocation:
    source_namespace: tuple[str, str, str]
    allocation_id: str
    lineage_selector_incarnation: str
    source_index_selector_incarnation: str
    anchor_selector_incarnation: str
    availability_profile: AvailabilityProfile
    anchor_authority: str
    anchor_reservation: IndependentAnchorNamespaceCapacityReservation


@dataclass(frozen=True)
class SourceAnchorAllocationBinding:
    source_namespace: tuple[str, str, str]
    anchor_authority: str
    anchor_selector_incarnation: str
    reservation_id: str
    allocation_id: str


@dataclass(frozen=True)
class SourceNamespaceCancellationProjection:
    allocation: SourceNamespaceAllocation
    cancellation_commit: str
    audience_purpose: str = "SOURCE_NAMESPACE_ALLOCATION_CANCELLATION"
    verification_class: str = _TOMBSTONE


@dataclass(frozen=True)
class SourceNamespaceReservationIntentCancellationProjection:
    reservation_intent: SourceNamespaceAnchorReservationIntent
    cancellation_commit: str
    audience_purpose: str = "SOURCE_NAMESPACE_ANCHOR_RESERVATION_INTENT_CANCELLATION"
    verification_class: str = _TOMBSTONE


@dataclass(frozen=True)
class ProtectedSourceNamespaceReservationIntentHierarchy:
    intent: SourceNamespaceAnchorReservationIntent
    producer_authority_id: str
    producer_registry_incarnation: str
    producer_security_epoch: str
    source_commit_receipt_digest: str
    producer_credential: OpaqueStateOwnerCredential = field(repr=False)
    protection: ProtectedArtifactChain


@dataclass(frozen=True)
class ProtectedAnchorNamespaceCapacityReservationHierarchy:
    reservation: IndependentAnchorNamespaceCapacityReservation
    producer_authority_id: str
    producer_registry_incarnation: str
    producer_security_epoch: str
    source_intent_hierarchy_digest: str
    owner_participant_units_charged: int
    owner_bytes_charged: int
    global_participant_units_charged: int
    global_bytes_charged: int
    anchor_commit_receipt_digest: str
    producer_credential: OpaqueStateOwnerCredential = field(repr=False)
    protection: ProtectedArtifactChain


@dataclass(frozen=True)
class ProtectedSourceNamespaceAllocationHierarchy:
    allocation: SourceNamespaceAllocation
    producer_authority_id: str
    producer_registry_incarnation: str
    producer_security_epoch: str
    anchor_reservation_hierarchy_digest: str
    source_commit_receipt_digest: str
    producer_credential: OpaqueStateOwnerCredential = field(repr=False)
    protection: ProtectedArtifactChain


@dataclass(frozen=True)
class ProtectedAnchorNamespaceGenesisHierarchy:
    allocation_hierarchy_digest: str
    allocation: SourceNamespaceAllocation
    producer_authority_id: str
    producer_registry_incarnation: str
    producer_security_epoch: str
    anchor_genesis_projection_digest: str
    anchor_commit_receipt_digest: str
    producer_credential: OpaqueStateOwnerCredential = field(repr=False)
    protection: ProtectedArtifactChain


@dataclass(frozen=True)
class ProtectedSourceNamespaceCancellationHierarchy:
    projection: (
        SourceNamespaceCancellationProjection
        | SourceNamespaceReservationIntentCancellationProjection
    )
    producer_authority_id: str
    producer_registry_incarnation: str
    producer_security_epoch: str
    source_commit_receipt_digest: str
    producer_credential: OpaqueStateOwnerCredential = field(repr=False)
    protection: ProtectedArtifactChain


@dataclass
class SourceNamespaceRegistryModel:
    producer_credential: OpaqueStateOwnerCredential = field(
        default_factory=OpaqueStateOwnerCredential, repr=False
    )
    producer_authority_id: str = "source-namespace-authority-v1"
    registry_incarnation: str = "source-namespace-registry-v1"
    security_epoch: str = "source-namespace-security-v1"
    state: SourceNamespaceBootstrapState = SourceNamespaceBootstrapState.ABSENT
    reservation_intent: SourceNamespaceAnchorReservationIntent | None = None
    reservation_intent_cancellation: (
        SourceNamespaceReservationIntentCancellationProjection | None
    ) = None
    allocation: SourceNamespaceAllocation | None = None
    cancellation: SourceNamespaceCancellationProjection | None = None
    anchor_genesis_projection_digest: str | None = None
    reservation_intent_hierarchy: (
        ProtectedSourceNamespaceReservationIntentHierarchy | None
    ) = None
    allocation_hierarchy: ProtectedSourceNamespaceAllocationHierarchy | None = None
    anchor_genesis_hierarchy: ProtectedAnchorNamespaceGenesisHierarchy | None = None
    cancellation_hierarchy: ProtectedSourceNamespaceCancellationHierarchy | None = None
    anchor_reservation_hierarchy: (
        ProtectedAnchorNamespaceCapacityReservationHierarchy | None
    ) = None
    trusted_anchor_producer_credential: OpaqueStateOwnerCredential | None = field(
        default=None, repr=False
    )
    trusted_anchor_registry_coordinate: tuple[str, str, str] | None = None


@dataclass
class AnchorNamespaceRegistryModel:
    producer_credential: OpaqueStateOwnerCredential = field(
        default_factory=OpaqueStateOwnerCredential, repr=False
    )
    producer_authority_id: str = "independent-anchor-authority"
    registry_incarnation: str = "anchor-namespace-registry-v1"
    security_epoch: str = "anchor-namespace-security-v1"
    state: AnchorNamespaceBootstrapState = AnchorNamespaceBootstrapState.ABSENT
    reservation_state: AnchorNamespaceReservationState = (
        AnchorNamespaceReservationState.ABSENT
    )
    reservation: IndependentAnchorNamespaceCapacityReservation | None = None
    allocation: SourceNamespaceAllocation | None = None
    eligible_root_count: int = 0
    challenge_entry_count: int = 0
    admission_count: int = 0
    in_flight_count: int = 0
    cancellation_projection: (
        SourceNamespaceCancellationProjection
        | SourceNamespaceReservationIntentCancellationProjection
        | None
    ) = None
    cancellation_finalization_receipt: str | None = None
    source_closure_terminal_cause: str | None = None
    source_closure_finalization_receipt: str | None = None
    owner_participant_units_charged: int = 0
    owner_bytes_charged: int = 0
    global_participant_units_charged: int = 0
    global_bytes_charged: int = 0
    reservation_hierarchy: (
        ProtectedAnchorNamespaceCapacityReservationHierarchy | None
    ) = None
    genesis_hierarchy: ProtectedAnchorNamespaceGenesisHierarchy | None = None
    cancellation_hierarchy: ProtectedSourceNamespaceCancellationHierarchy | None = None
    source_intent_hierarchy: (
        ProtectedSourceNamespaceReservationIntentHierarchy | None
    ) = None
    trusted_source_producer_credential: OpaqueStateOwnerCredential | None = field(
        default=None, repr=False
    )
    trusted_source_registry_coordinate: tuple[str, str, str] | None = None


@dataclass
class AnchorAuthorityNamespaceRegistryModel:
    anchor_authority: str
    registry_incarnation: str = "anchor-namespace-registry-v1"
    security_epoch: str = "anchor-namespace-security-v1"
    producer_credential: OpaqueStateOwnerCredential = field(
        default_factory=OpaqueStateOwnerCredential, repr=False
    )
    slots: dict[tuple[str, str], AnchorNamespaceRegistryModel] = field(
        default_factory=dict
    )
    reservation_intent_index: dict[str, tuple[str, str]] = field(default_factory=dict)
    source_namespace_index: dict[tuple[str, str, str], tuple[str, str]] = field(
        default_factory=dict
    )
    lineage_selector_index: dict[str, tuple[str, str]] = field(default_factory=dict)
    source_index_selector_index: dict[str, tuple[str, str]] = field(
        default_factory=dict
    )
    anchor_selector_index: dict[str, tuple[str, str]] = field(default_factory=dict)
    owner_participant_units_charged: dict[str, int] = field(default_factory=dict)
    owner_bytes_charged: dict[str, int] = field(default_factory=dict)
    global_participant_units_charged: int = 0
    global_bytes_charged: int = 0
    authority_domain_retirement_receipt: str | None = None


@dataclass(frozen=True)
class EligibleRoot:
    root_id: str
    root_incarnation: str
    availability_profile: AvailabilityProfile
    registered_root_hierarchy_digest: str
    source_enrollment_hierarchy_digest: str
    anchor_enrollment_entry_digest: str | None
    authority_credential: OpaqueRegisteredRootAuthorityCredential = field(
        default_factory=OpaqueRegisteredRootAuthorityCredential, repr=False
    )

    @property
    def audience_key(self) -> tuple[str, str]:
        return (self.root_id, self.root_incarnation)


@dataclass(frozen=True)
class CurrentRegisteredObserverRootAuthority:
    root: EligibleRoot
    observer_role_version: str
    source_security_epoch: str
    state: RegisteredRootAuthorityState


@dataclass(frozen=True)
class QualifiedClockRelation:
    relation_id: str
    source_clock_id: str
    anchor_clock_id: str
    source_clock_epoch: str
    anchor_clock_epoch: str
    anchor_minus_source_lower: int
    anchor_minus_source_upper: int
    source_valid_from: int
    source_valid_through_exclusive: int
    anchor_valid_from: int
    anchor_valid_through_exclusive: int
    source_reference_value: int
    anchor_reference_value: int
    maximum_relative_rate_ppb: int
    semantic_digest: str


@dataclass(frozen=True)
class BoundedClockSample:
    clock_id: str
    clock_epoch: str
    lower: int
    upper: int


@dataclass(frozen=True)
class ProtectedArtifactChain:
    audience_purpose: str
    verification_class: str
    envelope_digest: str
    family_manifest_digest: str
    pre_manifest_digest: str
    producer_completion_digest: str
    delivery_capsule_digest: str
    audience_proof_digest: str
    manifest_proof_digest: str
    delivery_verification_digest: str


EMPTY_PROTECTION = ProtectedArtifactChain(*("" for _ in range(10)))


@dataclass(frozen=True)
class PlantProfile:
    profile_id: str
    profile_revision: str
    media_type: str
    profile_document: bytes
    body_principal: str
    body_enrollment_digest: str
    physical_actuation_jurisdiction_key: str
    jurisdiction_registry_incarnation: str
    authority_transaction_domain_key: str
    actuation_authority_domain_key: str

    def canonical_bytes(self) -> bytes:
        _validate_closed_graph(self)
        value = {
            "actuation_authority_domain_key": self.actuation_authority_domain_key,
            "authority_transaction_domain_key": (self.authority_transaction_domain_key),
            "body_enrollment_digest": self.body_enrollment_digest,
            "body_principal": self.body_principal,
            "jurisdiction_registry_incarnation": (
                self.jurisdiction_registry_incarnation
            ),
            "media_type": self.media_type,
            "physical_actuation_jurisdiction_key": (
                self.physical_actuation_jurisdiction_key
            ),
            "profile_document_hex": self.profile_document.hex(),
            "profile_id": self.profile_id,
            "profile_revision": self.profile_revision,
        }
        return json.dumps(
            value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")

    @property
    def content_digest(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


@dataclass(frozen=True)
class ProtectedInstalledPlantProfileHierarchy:
    source_namespace: tuple[str, str, str]
    source_authority_id: str
    source_index_incarnation: str
    body_authority_id: str
    body_security_epoch: str
    profile: PlantProfile
    plant_profile_digest: str
    producer_credential: OpaqueBodyPlantProfileAuthorityCredential = field(repr=False)
    protection: ProtectedArtifactChain


@dataclass
class BodyPlantProfileAuthorityStore:
    authority_id: str = "configured-body-plant-profile-authority-v1"
    security_epoch: str = "body-plant-profile-security-v1"
    body_principal: str = "crebain-body-v1"
    body_enrollment_digest: str = field(
        default_factory=lambda: _fixture_digest(
            "configured-body-plant-profile-enrollment-v1"
        )
    )
    physical_actuation_jurisdiction_key: str = "physical-jurisdiction-v1"
    jurisdiction_registry_incarnation: str = "jurisdiction-registry-v1"
    producer_credential: OpaqueBodyPlantProfileAuthorityCredential = field(
        default=_CONFIGURED_BODY_PLANT_PROFILE_AUTHORITY_CREDENTIAL, repr=False
    )
    revision: int = 0
    hierarchies: dict[tuple[str, str, str], ProtectedInstalledPlantProfileHierarchy] = (
        field(default_factory=dict)
    )


@dataclass(frozen=True)
class RegisteredObserverRootAuthorityFact:
    root: EligibleRoot
    observer_role_version: str
    source_security_epoch: str
    manifest_decision: str


@dataclass(frozen=True)
class ProtectedRegisteredObserverRootAuthorityHierarchy:
    fact: RegisteredObserverRootAuthorityFact
    protection: ProtectedArtifactChain


@dataclass
class RegisteredObserverRootAuthorityProducerStore:
    producer_credential: OpaqueRegisteredRootAuthorityCredential = field(
        default_factory=OpaqueRegisteredRootAuthorityCredential, repr=False
    )
    revision: int = 0
    hierarchies: dict[
        tuple[str, str], ProtectedRegisteredObserverRootAuthorityHierarchy
    ] = field(default_factory=dict)


@dataclass(frozen=True)
class ObserverRootEnrollmentEligibility:
    source_namespace: tuple[str, str, str]
    root: EligibleRoot
    anchor_authority: str
    source_index_incarnation: str
    anchor_entry_key: str
    exclusive_anchor_cutoff: int
    source_security_epoch: str
    observer_role_version: str
    qualified_clock_relation: QualifiedClockRelation

    @property
    def clock_relation_id(self) -> str:
        return self.qualified_clock_relation.relation_id

    @property
    def clock_relation_digest(self) -> str:
        return self.qualified_clock_relation.semantic_digest


@dataclass(frozen=True)
class ProtectedObserverRootEnrollmentEligibilityHierarchy:
    eligibility: ObserverRootEnrollmentEligibility
    audience_purpose: str
    verification_class: str
    envelope_digest: str
    family_manifest_digest: str
    pre_manifest_digest: str
    producer_completion_digest: str
    delivery_capsule_digest: str
    audience_proof_digest: str
    manifest_proof_digest: str
    delivery_verification_digest: str


@dataclass(frozen=True)
class ProtectedAnchorSourceEnrollmentNotificationHierarchy:
    eligibility_hierarchy_digest: str
    anchor_entry_digest: str
    source_namespace: tuple[str, str, str]
    root_audience_key: tuple[str, str]
    anchor_authority: str
    exclusive_anchor_cutoff: int
    audience_purpose: str
    verification_class: str
    envelope_digest: str
    family_manifest_digest: str
    pre_manifest_digest: str
    producer_completion_digest: str
    delivery_capsule_digest: str
    audience_proof_digest: str
    manifest_proof_digest: str
    delivery_verification_digest: str


@dataclass(frozen=True)
class ProtectedSourceObserverRootEnrollmentHierarchy:
    source_namespace: tuple[str, str, str]
    root: EligibleRoot
    registered_authority_hierarchy_digest: str
    eligibility_hierarchy_digest: str | None
    anchor_notification_hierarchy_digest: str | None
    observer_role_version: str
    source_security_epoch: str
    enrollment_receipt_digest: str
    protection: ProtectedArtifactChain


@dataclass
class SourceRootAdmissionEntry:
    eligibility_hierarchy: ProtectedObserverRootEnrollmentEligibilityHierarchy | None
    phase: RootAdmissionPhase
    anchor_notification_digest: str | None = None


@dataclass(frozen=True)
class SourceIndexEntry:
    stable_key: StableKey
    kind: IndexEntryKind
    source_generation: str | None = None
    slot_id: str | None = None
    challenge_commitment: str | None = None
    paired_frame_admission_key: str | None = None
    plant_profile_digest: str | None = None


@dataclass
class FreshnessSlot:
    stable_key: StableKey
    source_generation: str
    slot_id: str
    challenge_commitment: str
    state: SlotState
    delivery_gate: DeliveryGate
    paired_frame_admission_key: str | None
    live_session_epoch: str
    authority_lease_not_after: int
    acceptance_not_after: int
    source_security_epoch: str
    plant_profile_digest: str | None
    accepted_grant_id: str | None = None
    expiry_clock_sample: BoundedClockSample | None = None


@dataclass
class AcceptedGrant:
    grant_id: str
    stable_key: StableKey
    live_session_epoch: str
    authority_lease_not_after: int
    acceptance_not_after: int
    source_security_epoch: str
    plant_profile_digest: str | None
    acceptance_transport_verification_digest: str
    acceptance_receipt_digest: str
    closure_plan_id: str
    closure_plan_digest: str
    predecessor_grant_id: str | None
    closure_receipt: ProtectedAcceptedGrantClosureReceipt | None = None


@dataclass(frozen=True)
class DistributedGrantClosureFact:
    state: DistributedClosureState
    authority_id: str
    authority_security_epoch: str
    closure_plan_id: str
    closure_plan_digest: str
    grant_id: str
    stable_key: StableKey
    live_session_epoch: str
    source_authority_id: str
    source_index_incarnation: str
    accepted_source_security_epoch: str
    closure_source_security_epoch: str
    plant_profile_digest: str | None
    acceptance_transport_verification_digest: str
    acceptance_receipt_digest: str


@dataclass(frozen=True)
class ProtectedDistributedGrantClosureHierarchy:
    fact: DistributedGrantClosureFact
    producer_credential: OpaqueDistributedClosureAuthorityCredential = field(repr=False)
    protection: ProtectedArtifactChain


@dataclass
class DistributedClosureAuthorityStore:
    authority_id: str = "configured-distributed-closure-authority-v1"
    security_epoch: str = "distributed-closure-security-v1"
    producer_credential: OpaqueDistributedClosureAuthorityCredential = field(
        default=_CONFIGURED_DISTRIBUTED_CLOSURE_AUTHORITY_CREDENTIAL, repr=False
    )
    revision: int = 0
    hierarchies: dict[
        tuple[str, str, str, str], ProtectedDistributedGrantClosureHierarchy
    ] = field(default_factory=dict)


@dataclass(frozen=True)
class AcceptedGrantClosureFact:
    grant_id: str
    stable_key: StableKey
    live_session_epoch: str
    source_authority_id: str
    source_index_incarnation: str
    accepted_source_security_epoch: str
    closure_source_security_epoch: str
    plant_profile_digest: str | None
    acceptance_transport_verification_digest: str
    acceptance_receipt_digest: str
    distributed_closure: ProtectedDistributedGrantClosureHierarchy


@dataclass(frozen=True)
class ProtectedAcceptedGrantClosureEvidenceHierarchy:
    fact: AcceptedGrantClosureFact
    producer_credential: OpaqueStateOwnerCredential = field(repr=False)
    protection: ProtectedArtifactChain


@dataclass(frozen=True)
class ProtectedAcceptedGrantClosureReceipt:
    grant_id: str
    requester_principal: str
    live_session_epoch: str
    source_authority_id: str
    source_index_incarnation: str
    source_security_epoch: str
    closure_source_security_epoch: str
    acceptance_transport_verification_digest: str
    distributed_closure_hierarchy_digest: str
    closure_evidence_hierarchy_digest: str
    source_commit_receipt_digest: str
    producer_credential: OpaqueStateOwnerCredential = field(repr=False)


@dataclass(frozen=True)
class PrivateChallengeMaterial:
    stable_key: StableKey
    challenge_bytes: bytes
    source_observer_capsule: bytes
    source_producer_coordinate: str
    transport_context: VerifiedTransportContext
    paired_frame_admission_key: str | None

    @property
    def challenge_commitment(self) -> str:
        return hashlib.sha256(self.challenge_bytes).hexdigest()

    @property
    def requester_connection(self) -> str:
        return self.transport_context.connection_id

    @property
    def replay_domain(self) -> str:
        return self.transport_context.replay_domain


@dataclass(frozen=True)
class ProtectedSourceChallengePublicationHierarchy:
    source_entry: SourceIndexEntry
    source_authority_id: str
    source_index_incarnation: str
    source_enrollment_hierarchy_digest: str
    transport_verification_digest: str
    source_capsule_digest: str
    source_producer_coordinate: str
    previous_source_root: bytes
    committed_source_root: bytes
    membership_proof: bytes
    source_commit_receipt_digest: str
    source_retention_receipt_digest: str
    producer_credential: OpaqueStateOwnerCredential = field(repr=False)
    protection: ProtectedArtifactChain


@dataclass(frozen=True)
class RequesterFrame:
    stable_key_digest: str
    challenge_bytes: bytes
    source_observer_capsule: bytes
    anchor_observer_capsule: bytes | None
    source_producer_coordinate: str
    anchor_producer_coordinate: str | None
    paired_frame_admission_key: str | None
    requester_connection: str
    authenticated_principal: str
    replay_domain: str
    transport_security_epoch: str
    transport_verification_digest: str
    plant_profile_digest: str | None

    def canonical_bytes(self) -> bytes:
        _validate_closed_graph(self)
        value = {
            "anchor_observer_capsule_hex": (
                None
                if self.anchor_observer_capsule is None
                else self.anchor_observer_capsule.hex()
            ),
            "anchor_producer_coordinate": self.anchor_producer_coordinate,
            "challenge_bytes_hex": self.challenge_bytes.hex(),
            "paired_frame_admission_key": self.paired_frame_admission_key,
            "plant_profile_digest": self.plant_profile_digest,
            "replay_domain": self.replay_domain,
            "requester_connection": self.requester_connection,
            "authenticated_principal": self.authenticated_principal,
            "source_observer_capsule_hex": self.source_observer_capsule.hex(),
            "source_producer_coordinate": self.source_producer_coordinate,
            "stable_key_digest": self.stable_key_digest,
            "transport_security_epoch": self.transport_security_epoch,
            "transport_verification_digest": self.transport_verification_digest,
        }
        encoded = json.dumps(
            value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
        if len(encoded) > MAX_REQUESTER_FRAME_BYTES:
            raise Reject()
        return encoded


def _parse_requester_frame(raw: bytes) -> tuple[dict[str, object], bytes, bytes, bytes]:
    if type(raw) is not bytes or not (1 <= len(raw) <= MAX_REQUESTER_FRAME_BYTES):
        raise Reject()
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise Reject() from error
    expected_keys = {
        "anchor_observer_capsule_hex",
        "anchor_producer_coordinate",
        "authenticated_principal",
        "challenge_bytes_hex",
        "paired_frame_admission_key",
        "plant_profile_digest",
        "replay_domain",
        "requester_connection",
        "source_observer_capsule_hex",
        "source_producer_coordinate",
        "stable_key_digest",
        "transport_security_epoch",
        "transport_verification_digest",
    }
    if type(value) is not dict or set(value) != expected_keys:
        raise Reject()
    if (
        type(value["challenge_bytes_hex"]) is not str
        or type(value["source_observer_capsule_hex"]) is not str
        or type(value["anchor_observer_capsule_hex"]) is not str
        or type(value["anchor_producer_coordinate"]) is not str
        or type(value["authenticated_principal"]) is not str
        or type(value["paired_frame_admission_key"]) is not str
        or type(value["replay_domain"]) is not str
        or type(value["requester_connection"]) is not str
        or type(value["source_producer_coordinate"]) is not str
        or type(value["stable_key_digest"]) is not str
        or type(value["transport_security_epoch"]) is not str
        or type(value["transport_verification_digest"]) is not str
        or (
            value["plant_profile_digest"] is not None
            and type(value["plant_profile_digest"]) is not str
        )
    ):
        raise Reject()
    canonical = json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    if canonical != raw:
        raise Reject()
    try:
        challenge = bytes.fromhex(value["challenge_bytes_hex"])
        source_capsule = bytes.fromhex(value["source_observer_capsule_hex"])
        anchor_capsule = bytes.fromhex(value["anchor_observer_capsule_hex"])
    except ValueError as error:
        raise Reject() from error
    if (
        challenge.hex() != value["challenge_bytes_hex"]
        or source_capsule.hex() != value["source_observer_capsule_hex"]
        or anchor_capsule.hex() != value["anchor_observer_capsule_hex"]
        or len(value["stable_key_digest"]) != 64
        or any(
            character not in "0123456789abcdef"
            for character in value["stable_key_digest"]
        )
        or not value["paired_frame_admission_key"]
        or not value["requester_connection"]
        or not value["authenticated_principal"]
        or not value["replay_domain"]
        or not value["transport_security_epoch"]
        or not value["source_producer_coordinate"]
        or not value["anchor_producer_coordinate"]
        or len(value["transport_verification_digest"]) != 64
        or any(
            character not in "0123456789abcdef"
            for character in value["transport_verification_digest"]
        )
        or (
            value["plant_profile_digest"] is not None
            and not _complete_digest_set((value["plant_profile_digest"],))
        )
        or not challenge
        or len(challenge) > MAX_CHALLENGE_BYTES
        or not source_capsule
        or len(source_capsule) > MAX_CAPSULE_BYTES
        or not anchor_capsule
        or len(anchor_capsule) > MAX_CAPSULE_BYTES
    ):
        raise Reject()
    return value, challenge, source_capsule, anchor_capsule


@dataclass(frozen=True)
class AnchorObserverAudienceOpaqueRelayBinding:
    observer_envelope_identity: str
    observer_envelope_bytes_digest: str
    observer_envelope_authentication_set_digest: str
    producer_coordinate: str


@dataclass
class PairedQueueRecord:
    admission_key: str
    stable_key: StableKey
    transport_context: VerifiedTransportContext
    frame_bytes: bytes
    frame_digest: str
    source_capsule_digest: str
    anchor_capsule_digest: str
    opaque_relay_binding: AnchorObserverAudienceOpaqueRelayBinding
    mapped_acceptance_cutoff: int
    clock_relation_id: str
    clock_relation_digest: str
    anchor_clock_id: str
    anchor_clock_epoch: str
    state: QueueRecordState
    handoff_receipt_digest: str | None = None

    @property
    def requester_connection(self) -> str:
        return self.transport_context.connection_id

    @property
    def replay_domain(self) -> str:
        return self.transport_context.replay_domain


@dataclass
class SourceIssuanceIndexStore:
    source_namespace: tuple[str, str, str]
    availability_profile: AvailabilityProfile
    source_index_incarnation: str = "source-index-v1"
    source_security_epoch: str = "source-security-v1"
    observer_role_version: str = "observer-role-v1"
    source_clock_id: str = "source-clock"
    source_clock_epoch: str = "source-clock-epoch-v1"
    live_session_epoch: str = "source-session-epoch-v1"
    authority_lease_not_after: int = 20_000
    acceptance_not_after: int = 10_000
    plant_profile_digest: str | None = None
    phase: SourceIndexPhase = SourceIndexPhase.OPEN
    eligible_capacity: int = MAX_ELIGIBLE_ROOTS
    entry_capacity: int = MAX_ISSUANCE_ENTRIES
    root_admissions: dict[tuple[str, str], SourceRootAdmissionEntry] = field(
        default_factory=dict
    )
    registered_root_authorities: dict[
        tuple[str, str], CurrentRegisteredObserverRootAuthority
    ] = field(default_factory=dict)
    anchor_allocation_binding: SourceAnchorAllocationBinding | None = None
    eligible_roots: dict[tuple[str, str], EligibleRoot] = field(default_factory=dict)
    enrollment_receipts: dict[tuple[str, str], str] = field(default_factory=dict)
    enrollment_hierarchies: dict[
        tuple[str, str], ProtectedSourceObserverRootEnrollmentHierarchy
    ] = field(default_factory=dict)
    entries: dict[StableKey, SourceIndexEntry] = field(default_factory=dict)
    issuance_hierarchies: dict[
        StableKey, ProtectedSourceChallengePublicationHierarchy
    ] = field(default_factory=dict)
    frozen_root: bytes | None = None
    frozen_audience: tuple[tuple[str, str], ...] = ()


@dataclass
class GenerationSlotStore:
    slot_capacity: int = MAX_GENERATION_SLOTS
    slots: dict[tuple[str, str], FreshnessSlot] = field(default_factory=dict)
    absent_intent_tombstones: dict[StableKey, str] = field(default_factory=dict)
    accepted_grants: dict[str, AcceptedGrant] = field(default_factory=dict)
    closure_evidence_hierarchies: dict[
        str, ProtectedAcceptedGrantClosureEvidenceHierarchy
    ] = field(default_factory=dict)
    private_challenges: dict[tuple[str, str], PrivateChallengeMaterial] = field(
        default_factory=dict
    )


@dataclass
class AuthoritativePairedFrameQueue:
    record_capacity: int = MAX_QUEUE_RECORDS
    records: dict[str, PairedQueueRecord] = field(default_factory=dict)


@dataclass
class SourceAuthorityDomain:
    index: SourceIssuanceIndexStore
    source_authority_id: str = "source-authority-v1"
    producer_credential: OpaqueStateOwnerCredential = field(
        default_factory=OpaqueStateOwnerCredential, repr=False
    )
    trusted_lineage_authority_credential: OpaqueLineageAuthorityCredential = field(
        default=_CONFIGURED_LINEAGE_AUTHORITY_CREDENTIAL, repr=False
    )
    trusted_body_plant_profile_authority_credential: BodyProfileCredential = field(
        default=_CONFIGURED_BODY_PLANT_PROFILE_AUTHORITY_CREDENTIAL, repr=False
    )
    trusted_distributed_closure_authority_credential: DistributedClosureCredential = (
        field(default=_CONFIGURED_DISTRIBUTED_CLOSURE_AUTHORITY_CREDENTIAL, repr=False)
    )
    trusted_distributed_closure_authority_id: str = (
        "configured-distributed-closure-authority-v1"
    )
    trusted_distributed_closure_security_epoch: str = "distributed-closure-security-v1"
    installed_plant_profile_hierarchy: (
        ProtectedInstalledPlantProfileHierarchy | None
    ) = None
    trusted_anchor_coordinate: (
        tuple[str, str, str, OpaqueStateOwnerCredential] | None
    ) = field(default=None, repr=False)
    registered_root_authority_producer: RegisteredObserverRootAuthorityProducerStore = (
        field(
            default_factory=lambda: RegisteredObserverRootAuthorityProducerStore(
                producer_credential=(_CONFIGURED_REGISTERED_ROOT_AUTHORITY_CREDENTIAL)
            )
        )
    )
    transport_authority: TransportAuthorityStore = field(
        default_factory=TransportAuthorityStore
    )
    generations: GenerationSlotStore = field(default_factory=GenerationSlotStore)
    queue: AuthoritativePairedFrameQueue = field(
        default_factory=AuthoritativePairedFrameQueue
    )
    in_flight_exposure: set[str] = field(default_factory=set)
    closure_hierarchy: ProtectedClosureBundleHierarchy | None = None
    cooperative_retirement_hierarchy: (
        ProtectedCooperativeSourceRetirementHierarchy | None
    ) = None


@dataclass(frozen=True)
class AnchorEntry:
    stable_key: StableKey
    source_index_entry_digest: str
    challenge_commitment: str
    intended_observer_root_id: str
    paired_frame_admission_key: str
    mapped_acceptance_cutoff: int
    anchor_clock_id: str
    anchor_clock_epoch: str
    clock_relation_id: str
    clock_relation_digest: str
    plant_profile_digest: str | None


@dataclass(frozen=True)
class ProtectedAnchorEntryHierarchy:
    entry: AnchorEntry
    anchor_authority: str
    anchor_selector_incarnation: str
    anchor_security_epoch: str
    source_publication_hierarchy_digest: str
    previous_anchor_root: bytes
    committed_anchor_root: bytes
    membership_proof: bytes
    anchor_commit_receipt_digest: str
    anchor_retention_receipt_digest: str
    producer_credential: OpaqueStateOwnerCredential = field(repr=False)
    protection: ProtectedArtifactChain


@dataclass(frozen=True)
class ProtectedAnchorObserverRelayHierarchy:
    anchor_entry_hierarchy_digest: str
    entry: AnchorEntry
    anchor_observer_capsule: bytes
    binding: AnchorObserverAudienceOpaqueRelayBinding
    common_completion_coordinate: str
    producer_credential: OpaqueStateOwnerCredential = field(repr=False)
    protection: ProtectedArtifactChain


@dataclass(frozen=True)
class IsolationEvidence:
    source_namespace: tuple[str, str, str]
    surface_kinds: tuple[str, ...]


class OpaqueHigherRootIsolationCredential(_Opaque):
    __slots__ = ()


_CONFIGURED_HIGHER_ROOT_ISOLATION_CREDENTIAL = OpaqueHigherRootIsolationCredential()


class OpaqueIsolationSurfaceCredential(_Opaque):
    __slots__ = ()


@dataclass(frozen=True)
class IsolationSurfaceTerminalReceipt:
    source_namespace: tuple[str, str, str]
    surface_kind: str
    authority_id: str
    registry_incarnation: str
    security_epoch: str
    terminal_receipt_digest: str
    producer_credential: OpaqueIsolationSurfaceCredential = field(repr=False)


@dataclass
class IsolationSurfaceAuthorityStore:
    surface_kind: str
    authority_id: str
    registry_incarnation: str = "isolation-surface-registry-v1"
    security_epoch: str = "isolation-surface-security-v1"
    producer_credential: OpaqueIsolationSurfaceCredential = field(
        default_factory=OpaqueIsolationSurfaceCredential, repr=False
    )
    receipts: dict[tuple[str, str, str], IsolationSurfaceTerminalReceipt] = field(
        default_factory=dict
    )


@dataclass(frozen=True)
class ProtectedIsolationEvidenceHierarchy:
    evidence: IsolationEvidence
    authority_id: str
    registry_incarnation: str
    security_epoch: str
    security_epoch_sequence: int
    surface_terminal_receipts: tuple[IsolationSurfaceTerminalReceipt, ...]
    producer_credential: OpaqueHigherRootIsolationCredential = field(repr=False)
    protection: ProtectedArtifactChain


@dataclass
class HigherRootIsolationAuthorityStore:
    authority_id: str = "configured-higher-root-isolation-authority-v1"
    registry_incarnation: str = "higher-root-isolation-registry-v1"
    security_epoch: str = "higher-root-isolation-security-v1"
    security_epoch_sequence: int = 1
    producer_credential: OpaqueHigherRootIsolationCredential = field(
        default_factory=OpaqueHigherRootIsolationCredential, repr=False
    )
    hierarchies: dict[tuple[str, str, str], ProtectedIsolationEvidenceHierarchy] = (
        field(default_factory=dict)
    )


@dataclass(frozen=True)
class CooperativeSourceRetirementProjection:
    source_namespace: tuple[str, str, str]
    anchor_authority: str
    anchor_selector_incarnation: str
    reservation_id: str
    allocation_id: str
    availability_profile: AvailabilityProfile
    frozen_source_index_root: bytes
    source_retirement_receipt_digest: str
    source_index_closure_receipt_digest: str
    accepted_grant_closure_inventory_digest: str
    no_successor_evidence_digest: str


@dataclass(frozen=True)
class ProtectedCooperativeSourceRetirementHierarchy:
    projection: CooperativeSourceRetirementProjection
    family_kinds: tuple[str, ...]
    closure_audience: tuple[tuple[str, str], ...]
    source_closure_hierarchy_digest: str
    source_authority_id: str
    source_index_incarnation: str
    source_security_epoch: str
    no_successor_hierarchy: ProtectedNoSuccessorEvidenceHierarchy
    producer_credential: OpaqueStateOwnerCredential = field(repr=False)
    audience_purpose: str
    verification_class: str
    envelope_digest: str
    family_manifest_digest: str
    pre_manifest_digest: str
    producer_completion_digest: str
    delivery_capsule_digest: str
    audience_proof_digest: str
    manifest_proof_digest: str
    delivery_verification_digest: str


@dataclass(frozen=True)
class SourceRetirementProducerInventory:
    family_kinds: tuple[str, ...]
    pre_manifest_digest: str | None
    producer_completion_digest: str | None


@dataclass(frozen=True)
class ProtectedNoSuccessorEvidenceHierarchy:
    source_namespace: tuple[str, str, str]
    source_index_incarnation: str
    authority_id: str
    registry_incarnation: str
    security_epoch: str
    terminal_receipt_digest: str
    producer_credential: OpaqueLineageAuthorityCredential = field(repr=False)


@dataclass
class SourceLineageAuthorityStore:
    authority_id: str = "configured-source-lineage-authority-v1"
    registry_incarnation: str = "source-lineage-registry-v1"
    security_epoch: str = "source-lineage-security-v1"
    producer_credential: OpaqueLineageAuthorityCredential = field(
        default=_CONFIGURED_LINEAGE_AUTHORITY_CREDENTIAL, repr=False
    )
    live_incarnations: dict[tuple[str, str, str], set[str]] = field(
        default_factory=dict
    )
    terminal_hierarchies: dict[
        tuple[str, str, str], ProtectedNoSuccessorEvidenceHierarchy
    ] = field(default_factory=dict)


@dataclass
class IndependentAnchorStore:
    source_namespace: tuple[str, str, str]
    anchor_authority: str = "independent-anchor-authority"
    anchor_selector_incarnation: str = "anchor-selector-v1"
    anchor_security_epoch: str = "anchor-security-v1"
    producer_credential: OpaqueStateOwnerCredential = field(
        default_factory=OpaqueStateOwnerCredential, repr=False
    )
    trusted_isolation_authority_credential: OpaqueHigherRootIsolationCredential = field(
        default=_CONFIGURED_HIGHER_ROOT_ISOLATION_CREDENTIAL, repr=False
    )
    trusted_isolation_authority_id: str = (
        "configured-higher-root-isolation-authority-v1"
    )
    trusted_isolation_registry_incarnation: str = "higher-root-isolation-registry-v1"
    minimum_isolation_security_epoch_sequence: int = 1
    trusted_lineage_authority_credential: OpaqueLineageAuthorityCredential = field(
        default=_CONFIGURED_LINEAGE_AUTHORITY_CREDENTIAL, repr=False
    )
    trusted_source_coordinate: (
        tuple[str, str, str, OpaqueStateOwnerCredential] | None
    ) = field(default=None, repr=False)
    anchor_clock_id: str = "anchor-clock"
    anchor_clock_epoch: str = "anchor-clock-epoch-v1"
    phase: AnchorPhase = AnchorPhase.ABSENT
    eligible_capacity: int = MAX_ELIGIBLE_ROOTS
    entry_capacity: int = MAX_ISSUANCE_ENTRIES
    eligible_roots: dict[tuple[str, str], EligibleRoot] = field(default_factory=dict)
    enrollment_eligibility_digests: dict[tuple[str, str], str] = field(
        default_factory=dict
    )
    enrollment_eligibility_hierarchies: dict[
        tuple[str, str], ProtectedObserverRootEnrollmentEligibilityHierarchy
    ] = field(default_factory=dict)
    enrollment_notifications: dict[
        tuple[str, str], ProtectedAnchorSourceEnrollmentNotificationHierarchy
    ] = field(default_factory=dict)
    enrollment_cutoffs: dict[tuple[str, str], int] = field(default_factory=dict)
    enrollment_clock_relations: dict[tuple[str, str], QualifiedClockRelation] = field(
        default_factory=dict
    )
    entries: dict[StableKey, AnchorEntry] = field(default_factory=dict)
    entry_hierarchies: dict[StableKey, ProtectedAnchorEntryHierarchy] = field(
        default_factory=dict
    )
    relay_hierarchies: dict[str, ProtectedAnchorObserverRelayHierarchy] = field(
        default_factory=dict
    )
    in_flight_mutations: set[str] = field(default_factory=set)
    cooperative_retirement_digest: str | None = None
    isolation_digest: str | None = None
    closure_evidence_state: AnchorClosureEvidenceState = AnchorClosureEvidenceState.NONE
    first_closure_cause: AnchorClosureCause = AnchorClosureCause.NO_ANCHOR_CLOSURE
    reservation_terminal_cause: str | None = None
    frozen_root: bytes | None = None
    frozen_audience: tuple[tuple[str, str], ...] = ()
    closure_hierarchy: ProtectedClosureBundleHierarchy | None = None


@dataclass
class LocalOperation:
    stable_key: StableKey
    state: LocalOperationState = LocalOperationState.INTENT_PREPARED
    verified_request_attempt_present: bool = False
    exact_terminal_evidence_pending: bool = False
    resolution_outcome: ResolutionOutcome = ResolutionOutcome.UNRESOLVED


@dataclass(frozen=True)
class NamespaceClosureTombstone:
    source_namespace: tuple[str, str, str]
    observer_root_incarnation: str
    evidence_state: ClosureEvidenceState
    source_index_root: bytes | None = None
    anchor_root: bytes | None = None
    enrollment_ancestry_digest: str = ""
    source_import: ClosureOriginImportRecord | None = None
    anchor_import: ClosureOriginImportRecord | None = None
    latest_complete_partition: tuple[ClosureOperationPartitionEntry, ...] = ()
    latest_complete_partition_digest: str = ""
    latest_import_receipt_digest: str = ""


@dataclass(frozen=True)
class ClosureOperationPartitionEntry:
    stable_key: StableKey
    kind: ClosureOperationPartitionKind
    prior_operation_digest: str
    installed_operation_digest: str
    resolution_proof_digest: str | None


@dataclass(frozen=True)
class ClosureOriginImportRecord:
    origin: ClosureOrigin
    bundle_digest: str
    request_digest: str
    installed_partition_digest: str
    import_receipt_digest: str


@dataclass
class ObserverLocalStore:
    observer_root_id: str
    observer_root_incarnation: str
    operation_capacity: int = MAX_OBSERVER_OPERATIONS
    enrollment_capacity: int = MAX_OBSERVER_ENROLLMENTS
    tombstone_capacity: int = MAX_OBSERVER_TOMBSTONES
    trusted_producer_coordinates: dict[
        tuple[str, str, str],
        tuple[
            tuple[str, str, str, OpaqueStateOwnerCredential],
            tuple[str, str, str, OpaqueStateOwnerCredential] | None,
        ],
    ] = field(default_factory=dict, repr=False)
    enrollments: dict[tuple[str, str, str], EligibleRoot] = field(default_factory=dict)
    enrollment_hierarchies: dict[
        tuple[str, str, str], ProtectedSourceObserverRootEnrollmentHierarchy
    ] = field(default_factory=dict)
    operations: dict[StableKey, LocalOperation] = field(default_factory=dict)
    closure_tombstones: dict[
        tuple[tuple[str, str, str], str], NamespaceClosureTombstone
    ] = field(default_factory=dict)


@dataclass(frozen=True)
class ClosureBundle:
    source_namespace: tuple[str, str, str]
    availability_profile: AvailabilityProfile
    context: ProofContext
    root: bytes
    audience: tuple[tuple[str, str], ...]
    origin: ClosureOrigin
    anchor_closure_cause: AnchorClosureCause = AnchorClosureCause.NO_ANCHOR_CLOSURE


@dataclass(frozen=True)
class ProtectedClosureBundleHierarchy:
    bundle: ClosureBundle
    producer_kind: str
    producer_authority_id: str
    producer_security_epoch: str
    enrollment_ancestry_digest: str
    closure_commit_receipt_digest: str
    producer_credential: OpaqueStateOwnerCredential = field(repr=False)
    protection: ProtectedArtifactChain


@dataclass(frozen=True)
class ResolutionProof:
    body: bytes
    proof_kind: ProofKind
    source_entry: SourceIndexEntry | None
    anchor_entry: AnchorEntry | None
    claimed_outcome: ResolutionOutcome


@dataclass(frozen=True)
class DeliveryView:
    status: str
    frame_bytes: bytes | None


@dataclass(frozen=True)
class HandoffAttempt:
    result: HandoffQuiescenceResult
    frame_bytes: bytes | None


@dataclass(frozen=True)
class ProtectedHandoffQuiescenceReceipt:
    admission_key: str
    transport_verification_digest: str
    frame_digest: str
    result: HandoffQuiescenceResult
    dispatcher_epoch: str
    receipt_digest: str
    producer_capability: OpaqueTransportProducerCapability = field(repr=False)


# Concise internal aliases keep the executable challenge below its source cap.
# Canonical class names remain unchanged and are the only names reported.
Anchor = IndependentAnchorStore
AnchorBootstrap = AnchorNamespaceBootstrapState
AnchorEvidenceState = AnchorClosureEvidenceState
AnchorRegistry = AnchorNamespaceRegistryModel
AuthorityRegistry = AnchorAuthorityNamespaceRegistryModel
Availability = AvailabilityProfile
ClockRelation = QualifiedClockRelation
ClosureAuthority = DistributedClosureAuthorityStore
HandoffResult = HandoffQuiescenceResult
IntentCancellation = SourceNamespaceReservationIntentCancellationProjection
IsolationAuthority = HigherRootIsolationAuthorityStore
IsolationReceipt = IsolationSurfaceTerminalReceipt
IsolationSurface = IsolationSurfaceAuthorityStore
LineageStore = SourceLineageAuthorityStore
NamespaceAllocation = SourceNamespaceAllocation
NamespaceCancellation = SourceNamespaceCancellationProjection
OperationState = LocalOperationState
RelayBinding = AnchorObserverAudienceOpaqueRelayBinding
ProtectedAllocation = ProtectedSourceNamespaceAllocationHierarchy
ProtectedAnchorEntry = ProtectedAnchorEntryHierarchy
ProtectedCancellation = ProtectedSourceNamespaceCancellationHierarchy
ProtectedDistributedClosure = ProtectedDistributedGrantClosureHierarchy
ProtectedEligibility = ProtectedObserverRootEnrollmentEligibilityHierarchy
ProtectedEnrollment = ProtectedSourceObserverRootEnrollmentHierarchy
ProtectedGenesis = ProtectedAnchorNamespaceGenesisHierarchy
ProtectedGrantClosure = ProtectedAcceptedGrantClosureEvidenceHierarchy
ProtectedHandoff = ProtectedHandoffQuiescenceReceipt
ProtectedIntent = ProtectedSourceNamespaceReservationIntentHierarchy
ProtectedIsolation = ProtectedIsolationEvidenceHierarchy
ProtectedNoSuccessor = ProtectedNoSuccessorEvidenceHierarchy
ProtectedNotification = ProtectedAnchorSourceEnrollmentNotificationHierarchy
ProtectedPlantProfile = ProtectedInstalledPlantProfileHierarchy
ProtectedRelay = ProtectedAnchorObserverRelayHierarchy
ProtectedReservation = ProtectedAnchorNamespaceCapacityReservationHierarchy
ProtectedRetirement = ProtectedCooperativeSourceRetirementHierarchy
ProtectedRootAuthority = ProtectedRegisteredObserverRootAuthorityHierarchy
ProtectionChain = ProtectedArtifactChain
ReservationIntent = SourceNamespaceAnchorReservationIntent
ReservationState = AnchorNamespaceReservationState
RetirementInventory = SourceRetirementProducerInventory
RootAuthorityState = RegisteredRootAuthorityState
Source = SourceAuthorityDomain
SourceBootstrap = SourceNamespaceBootstrapState
SourceRegistry = SourceNamespaceRegistryModel
TransportContext = VerifiedTransportContext
TransportState = TransportChannelState
TransportStore = TransportAuthorityStore


_CLOSED_FIELDS = (
    (ReservationIntent, "availability_profile", Availability),
    (NamespaceAllocation, "availability_profile", Availability),
    (SourceRegistry, "state", SourceBootstrap),
    (AnchorRegistry, "state", AnchorBootstrap),
    (AnchorRegistry, "reservation_state", ReservationState),
    (EligibleRoot, "availability_profile", Availability),
    (CurrentRegisteredObserverRootAuthority, "state", RootAuthorityState),
    (SourceRootAdmissionEntry, "phase", RootAdmissionPhase),
    (SourceIndexEntry, "kind", IndexEntryKind),
    (FreshnessSlot, "state", SlotState),
    (FreshnessSlot, "delivery_gate", DeliveryGate),
    (DistributedGrantClosureFact, "state", DistributedClosureState),
    (PairedQueueRecord, "state", QueueRecordState),
    (SourceIssuanceIndexStore, "availability_profile", Availability),
    (SourceIssuanceIndexStore, "phase", SourceIndexPhase),
    (CooperativeSourceRetirementProjection, "availability_profile", Availability),
    (Anchor, "phase", AnchorPhase),
    (Anchor, "closure_evidence_state", AnchorEvidenceState),
    (Anchor, "first_closure_cause", AnchorClosureCause),
    (LocalOperation, "state", OperationState),
    (LocalOperation, "resolution_outcome", ResolutionOutcome),
    (NamespaceClosureTombstone, "evidence_state", ClosureEvidenceState),
    (ClosureOperationPartitionEntry, "kind", ClosureOperationPartitionKind),
    (ClosureOriginImportRecord, "origin", ClosureOrigin),
    (ClosureBundle, "availability_profile", Availability),
    (ClosureBundle, "context", ProofContext),
    (ClosureBundle, "origin", ClosureOrigin),
    (ClosureBundle, "anchor_closure_cause", AnchorClosureCause),
    (ResolutionProof, "proof_kind", ProofKind),
    (ResolutionProof, "claimed_outcome", ResolutionOutcome),
    (HandoffAttempt, "result", HandoffResult),
    (ProtectedHandoff, "result", HandoffResult),
)
_CLOSED_MAP_VALUE_FIELDS = ((TransportStore, "channel_states", TransportState),)
_DECLARED_TYPES = tuple(
    (name, value)
    for name, value in globals().items()
    if type(value) is type and value.__name__ == name
)
_CANONICAL_DATACLASS_TYPES = frozenset(
    value
    for _, value in _DECLARED_TYPES
    if getattr(value, "__dataclass_fields__", None) is not None
)
_CANONICAL_ENUM_TYPES = frozenset(
    enum_type for _, _, enum_type in (*_CLOSED_FIELDS, *_CLOSED_MAP_VALUE_FIELDS)
)
_CANONICAL_OPAQUE_TYPES = frozenset(
    value for name, value in _DECLARED_TYPES if name.startswith("Opaque")
)
_CANONICAL_SCALAR_TYPES = (type(None), bool, int, str, bytes)
_FIELD_HINTS = {owner: get_type_hints(owner) for owner in _CANONICAL_DATACLASS_TYPES}
_REQUIRED_FIELDS = {
    owner: frozenset(
        name for name, hint in hints.items() if type(None) not in get_args(hint)
    )
    for owner, hints in _FIELD_HINTS.items()
}


def _closed_member(value: object, enum_type: type[StrEnum]) -> None:
    if type(value) is not enum_type or not any(value is member for member in enum_type):
        raise Reject()


def _validate_closed_graph(root: object) -> None:
    pending = [root]
    visited: set[int] = set()
    while pending:
        value = pending.pop()
        value_type = type(value)
        if value_type is dict:
            identity = id(value)
            if identity in visited:
                continue
            visited.add(identity)
            pending.extend(value)
            pending.extend(value.values())
            continue
        if value_type in (list, tuple, set):
            identity = id(value)
            if identity in visited:
                continue
            visited.add(identity)
            pending.extend(value)
            continue
        fields = getattr(value_type, "__dataclass_fields__", None)
        if fields is not None:
            if value_type not in _CANONICAL_DATACLASS_TYPES:
                raise Reject()
            identity = id(value)
            if identity in visited:
                continue
            visited.add(identity)
            for owner, name, enum_type in _CLOSED_FIELDS:
                if value_type is owner:
                    _closed_member(getattr(value, name, None), enum_type)
            for owner, name, enum_type in _CLOSED_MAP_VALUE_FIELDS:
                if value_type is owner:
                    members = getattr(value, name, None)
                    if type(members) is not dict:
                        raise Reject()
                    for member in members.values():
                        _closed_member(member, enum_type)
            for name in fields:
                if not hasattr(value, name):
                    raise Reject()
                member = getattr(value, name)
                if name in _REQUIRED_FIELDS[value_type] and member is None:
                    raise Reject()
                pending.append(member)
            continue
        if value_type in _CANONICAL_ENUM_TYPES:
            _closed_member(value, value_type)
            continue
        if (
            value_type not in _CANONICAL_OPAQUE_TYPES
            and value_type not in _CANONICAL_SCALAR_TYPES
        ):
            raise Reject()


def _validate_captures(operation: Callable[..., object]) -> None:
    _validate_closed_graph(
        (
            operation.__defaults__,
            operation.__kwdefaults__,
            tuple(cell.cell_contents for cell in operation.__closure__ or ()),
        )
    )


T = TypeVar("T")
R = TypeVar("R")


def _require_result_type(value: object, expected_type: type[R]) -> R:
    if type(value) is not expected_type:
        raise Reject()
    return value


def _replace_state(target: object, candidate: object) -> None:
    target.__dict__.clear()
    target.__dict__.update(candidate.__dict__)


def _atomic(
    state: T, operation: Callable[[T], object], validator: Callable[[T], None]
) -> object:
    _validate_closed_graph(state)
    _validate_captures(operation)
    independent_versions: tuple[int, int] | None = None
    if type(state) is Source:
        candidate = copy.copy(state)
        for name in (
            "index",
            "generations",
            "queue",
            "in_flight_exposure",
            "closure_hierarchy",
            "cooperative_retirement_hierarchy",
        ):
            setattr(candidate, name, copy.deepcopy(getattr(state, name)))
        independent_versions = (
            state.registered_root_authority_producer.revision,
            state.transport_authority.revision,
        )
    else:
        candidate = copy.deepcopy(state)
    result = operation(candidate)
    _validate_closed_graph(candidate)
    validator(candidate)
    if independent_versions is not None and (
        candidate.registered_root_authority_producer
        is not state.registered_root_authority_producer
        or candidate.transport_authority is not state.transport_authority
        or independent_versions
        != (
            state.registered_root_authority_producer.revision,
            state.transport_authority.revision,
        )
    ):
        raise Reject()
    _replace_state(state, candidate)
    return copy.deepcopy(result)


def _atomic_anchor_transition(
    anchor: Anchor,
    namespace_registry: AuthorityRegistry,
    operation: Callable[[Anchor, AnchorRegistry], object],
) -> object:
    _validate_anchor(anchor)
    _validate_authority_registry(namespace_registry)
    _validate_anchor_binding(anchor, namespace_registry)
    _validate_captures(operation)
    candidate_anchor = copy.deepcopy(anchor)
    candidate_registry = copy.deepcopy(namespace_registry)
    candidate_slot = _slot_for_anchor(candidate_registry, candidate_anchor)
    result = operation(candidate_anchor, candidate_slot)
    _rebuild_authority_indexes(candidate_registry)
    _validate_anchor(candidate_anchor)
    _validate_authority_registry(candidate_registry)
    _validate_anchor_binding(candidate_anchor, candidate_registry)
    _replace_state(anchor, candidate_anchor)
    _replace_state(namespace_registry, candidate_registry)
    return copy.deepcopy(result)


def _u64(value: int) -> bytes:
    if type(value) is not int or value < 0 or value >= 1 << 64:
        raise Reject()
    return value.to_bytes(8, "big")


def _identifier(value: str, maximum_bytes: int = MAX_IDENTIFIER_UTF8_BYTES) -> bytes:
    if type(value) is not str:
        raise Reject()
    encoded = value.encode("utf-8")
    if (
        not encoded
        or len(encoded) > maximum_bytes
        or "\x00" in value
        or any(ord(character) < 0x20 for character in value)
    ):
        raise Reject()
    return encoded


def _validate_namespace(namespace: tuple[str, str, str]) -> None:
    if type(namespace) is not tuple or len(namespace) != 3:
        raise Reject()
    encoded = [_identifier(member) for member in namespace]
    if (
        namespace[1] not in {"SIMULATION", "PLANT"}
        or sum(len(member) for member in encoded) > MAX_NAMESPACE_UTF8_BYTES
    ):
        raise Reject()


def _validate_stable_key(key: StableKey) -> None:
    _validate_closed_graph(key)
    _validate_namespace(key.source_namespace)
    encoded = [
        _identifier(key.authority_realm),
        _identifier(key.source_kind),
        _identifier(key.logical_source_id),
        _identifier(key.requester_principal),
        _identifier(key.observer_root_incarnation),
        _identifier(key.request_operation),
        _identifier(key.request_kind),
        _identifier(key.logical_target_key),
    ]
    if (
        key.request_kind != "ATTACH"
        or not key.request_operation.startswith("operation-")
        or sum(len(member) for member in encoded) > MAX_STABLE_KEY_UTF8_BYTES
    ):
        raise Reject()


def _u128(value: int) -> bytes:
    if type(value) is not int or value < 0 or value >= 1 << 128:
        raise Reject()
    return value.to_bytes(16, "big")


def _lp(value: bytes) -> bytes:
    if type(value) is not bytes:
        raise Reject()
    return _u128(len(value)) + value


def _encoded_json_value(value: object) -> bytes:
    if value is None:
        return b"\x00"
    if value is False:
        return b"\x01"
    if value is True:
        return b"\x02"
    if type(value) is str:
        raw = value.encode("utf-8")
        return b"\x04" + _u64(len(raw)) + raw
    if type(value) is list:
        return (
            b"\x05"
            + _u64(len(value))
            + b"".join(_encoded_json_value(member) for member in value)
        )
    if type(value) is dict:
        if not all(type(key) is str for key in value):
            raise Reject()
        ordered = sorted(value, key=lambda key: key.encode("utf-8"))
        return (
            b"\x06"
            + _u64(len(ordered))
            + b"".join(
                _encoded_json_value(key) + _encoded_json_value(value[key])
                for key in ordered
            )
        )
    raise Reject()


def _canonical_projection(domain: str, value: dict[str, object]) -> bytes:
    if type(domain) is not str or type(value) is not dict:
        raise Reject()
    raw_domain = domain.encode("ascii")
    if not (1 <= len(raw_domain) <= 128) or b"\x00" in raw_domain:
        raise Reject()
    return raw_domain + b"\x00" + _encoded_json_value(value)


def stable_key_bytes(key: StableKey) -> bytes:
    _validate_stable_key(key)
    return _canonical_projection(
        "ncp.observer-grant.source-issuance-stable-key.v1",
        {
            "authority_realm": key.authority_realm,
            "logical_source_id": key.logical_source_id,
            "logical_target_key": key.logical_target_key,
            "observer_root_incarnation": key.observer_root_incarnation,
            "request_kind": key.request_kind,
            "request_operation": key.request_operation,
            "requester_principal": key.requester_principal,
            "source_kind": key.source_kind,
        },
    )


def _tree_digest(tag: str, context: str, *fields: bytes) -> bytes:
    encoded = (
        _lp(tag.encode("ascii"))
        + _lp(SPARSE_SUITE.encode("ascii"))
        + _lp(context.encode("ascii"))
        + b"".join(_lp(field) for field in fields)
    )
    return hashlib.sha256(encoded).digest()


def stable_key_digest(key: StableKey) -> bytes:
    return _tree_digest("NCP1/OGSM/KEY", "STABLE_KEY", stable_key_bytes(key))


def source_entry_bytes(entry: SourceIndexEntry) -> bytes:
    _validate_closed_graph(entry)
    value: dict[str, object] = {
        "kind": entry.kind.value,
        "plant_profile_digest": entry.plant_profile_digest,
        "stable_key_digest": stable_key_digest(entry.stable_key).hex(),
    }
    if entry.kind is IndexEntryKind.CHALLENGE_ISSUED:
        if (
            entry.source_generation is None
            or entry.slot_id is None
            or entry.challenge_commitment is None
        ):
            raise Reject()
        value.update(
            {
                "challenge_commitment": entry.challenge_commitment,
                "paired_frame_admission_key": (entry.paired_frame_admission_key),
                "slot_id": entry.slot_id,
                "source_generation": entry.source_generation,
            }
        )
    elif any(
        member is not None
        for member in (
            entry.source_generation,
            entry.slot_id,
            entry.challenge_commitment,
            entry.paired_frame_admission_key,
        )
    ):
        raise Reject()
    return _canonical_projection("ncp.observer-grant.source-issuance-entry.v1", value)


def anchor_entry_bytes(entry: AnchorEntry) -> bytes:
    _validate_closed_graph(entry)
    return _canonical_projection(
        "ncp.observer-grant.challenge-exposure-anchor-entry.v1",
        {
            "anchor_clock_epoch": entry.anchor_clock_epoch,
            "anchor_clock_id": entry.anchor_clock_id,
            "challenge_commitment": entry.challenge_commitment,
            "clock_relation_digest": entry.clock_relation_digest,
            "clock_relation_id": entry.clock_relation_id,
            "intended_observer_root_id": entry.intended_observer_root_id,
            "mapped_acceptance_cutoff": str(entry.mapped_acceptance_cutoff),
            "paired_frame_admission_key": entry.paired_frame_admission_key,
            "plant_profile_digest": entry.plant_profile_digest,
            "source_index_entry_digest": entry.source_index_entry_digest,
            "stable_key_digest": stable_key_digest(entry.stable_key).hex(),
        },
    )


class SparseMerkleTree:
    def __init__(self, context: ProofContext, entries: dict[StableKey, bytes]) -> None:
        _closed_member(context, ProofContext)
        _validate_closed_graph(entries)
        self.context = context
        self.entries = dict(entries)
        self.empty = self._empty_ladder(context)
        leaves: dict[int, bytes] = {}
        self._paths: dict[bytes, tuple[StableKey, bytes]] = {}
        for key, canonical_entry in sorted(
            entries.items(), key=lambda item: stable_key_bytes(item[0])
        ):
            path = stable_key_digest(key)
            prior = self._paths.get(path)
            if prior is not None and (prior[0] != key or prior[1] != canonical_entry):
                raise Reject()
            self._paths[path] = (key, canonical_entry)
            entry_digest = _tree_digest(
                "NCP1/OGSM/ENTRY", context.value, canonical_entry
            )
            leaves[int.from_bytes(path, "big")] = _tree_digest(
                "NCP1/OGSM/PRESENT", context.value, path, entry_digest
            )
        self.levels: list[dict[int, bytes]] = [leaves]
        for height in range(1, SPARSE_TREE_HEIGHT + 1):
            children = self.levels[-1]
            parents: dict[int, bytes] = {}
            for parent in sorted({child >> 1 for child in children}):
                left = children.get(parent << 1, self.empty[height - 1])
                right = children.get((parent << 1) | 1, self.empty[height - 1])
                parents[parent] = _tree_digest(
                    "NCP1/OGSM/NODE", context.value, _u64(height), left, right
                )
            self.levels.append(parents)
        self.root = self.levels[SPARSE_TREE_HEIGHT].get(0, self.empty[-1])

    @staticmethod
    def _empty_ladder(context: ProofContext) -> list[bytes]:
        _closed_member(context, ProofContext)
        empty = [_tree_digest("NCP1/OGSM/EMPTY", context.value, _u64(0))]
        for height in range(1, SPARSE_TREE_HEIGHT + 1):
            empty.append(
                _tree_digest(
                    "NCP1/OGSM/NODE", context.value, _u64(height), empty[-1], empty[-1]
                )
            )
        return empty

    def proof(self, key: StableKey, kind: ProofKind) -> bytes:
        _closed_member(kind, ProofKind)
        path = stable_key_digest(key)
        present = path in self._paths and self._paths[path][0] == key
        if kind is ProofKind.MEMBERSHIP and not present:
            raise Reject()
        if kind is ProofKind.NONMEMBERSHIP and present:
            raise Reject()
        key_integer = int.from_bytes(path, "big")
        siblings = []
        for height in range(SPARSE_TREE_HEIGHT):
            node_index = key_integer >> height
            siblings.append(self.levels[height].get(node_index ^ 1, self.empty[height]))
        body = (
            SPARSE_PROOF_MAGIC
            + bytes((self.context.wire_byte, kind.wire_byte))
            + b"\x00" * 6
            + self.root
            + path
            + b"".join(siblings)
        )
        if len(body) != SPARSE_PROOF_BYTES:
            raise AssertionError("sparse proof encoder length drift")
        return body


def verify_sparse_proof(
    body: bytes,
    *,
    expected_context: ProofContext,
    expected_kind: ProofKind,
    expected_root: bytes,
    stable_key: StableKey,
    canonical_entry: bytes | None,
) -> None:
    _closed_member(expected_context, ProofContext)
    _closed_member(expected_kind, ProofKind)
    _validate_closed_graph(stable_key)
    if (
        type(body) is not bytes
        or type(expected_root) is not bytes
        or (canonical_entry is not None and type(canonical_entry) is not bytes)
    ):
        raise Reject()
    if len(body) != SPARSE_PROOF_BYTES:
        raise Reject()
    if body[:8] != SPARSE_PROOF_MAGIC:
        raise Reject()
    if body[8] != expected_context.wire_byte:
        raise Reject()
    if body[9] != expected_kind.wire_byte:
        raise Reject()
    if body[10:16] != b"\x00" * 6:
        raise Reject()
    encoded_root = body[16:48]
    if encoded_root != expected_root:
        raise Reject()
    path = body[48:80]
    expected_path = stable_key_digest(stable_key)
    if path != expected_path:
        raise Reject()
    siblings = [
        body[80 + index * 32 : 80 + (index + 1) * 32]
        for index in range(SPARSE_TREE_HEIGHT)
    ]
    empty = SparseMerkleTree._empty_ladder(expected_context)
    if expected_kind is ProofKind.NONMEMBERSHIP:
        if canonical_entry is not None:
            raise Reject()
        current = empty[0]
    else:
        if canonical_entry is None:
            raise Reject()
        entry_digest = _tree_digest(
            "NCP1/OGSM/ENTRY", expected_context.value, canonical_entry
        )
        current = _tree_digest(
            "NCP1/OGSM/PRESENT", expected_context.value, path, entry_digest
        )
    path_integer = int.from_bytes(path, "big")
    for index, sibling in enumerate(siblings):
        bit = (path_integer >> index) & 1
        left, right = (current, sibling) if bit == 0 else (sibling, current)
        current = _tree_digest(
            "NCP1/OGSM/NODE", expected_context.value, _u64(index + 1), left, right
        )
    if current != encoded_root:
        raise Reject()


def _incarnation_root(
    eligible_roots: dict[tuple[str, str], EligibleRoot], incarnation: str
) -> EligibleRoot:
    _validate_closed_graph(eligible_roots)
    _identifier(incarnation)
    matches = [
        entry
        for entry in eligible_roots.values()
        if entry.root_incarnation == incarnation
    ]
    if len(matches) != 1:
        raise Reject()
    return matches[0]


def _fixture_digest(label: str) -> str:
    if type(label) is not str:
        raise Reject()
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _transport_digest(context: TransportContext) -> str:
    _validate_closed_graph(context)
    return hashlib.sha256(
        json.dumps(
            {
                "authenticated_principal": context.authenticated_principal,
                "channel_binding_digest": context.channel_binding_digest,
                "connection_id": context.connection_id,
                "replay_domain": context.replay_domain,
                "transport_security_epoch": context.transport_security_epoch,
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()


def _transport_replay_accumulator(
    prior: str, context: TransportContext, state: TransportState
) -> str:
    _closed_member(state, TransportState)
    return _fixture_digest(
        "transport-replay-tombstone|"
        + repr((prior, context.verification_digest, state.value))
    )


def _validate_transport(store: TransportStore) -> None:
    _validate_closed_graph(store)
    _identifier(store.authority_id)
    _identifier(store.security_epoch)
    if (
        not store.authority_id
        or not store.security_epoch
        or store.context_capacity <= 0
        or store.context_capacity > MAX_VERIFIED_TRANSPORT_CONTEXTS
        or len(store.contexts) > store.context_capacity
        or len(store.retired_contexts) > MAX_RETIRED_TRANSPORT_CONTEXTS
        or not 1 <= len(store.used_security_epochs) <= MAX_TRANSPORT_SECURITY_EPOCHS
        or store.security_epoch not in store.used_security_epochs
        or set(store.contexts) & set(store.retired_contexts)
        or set(store.channel_states)
        != set(store.contexts) | set(store.retired_contexts)
        or store.revision < 0
        or not _complete_digest_set((store.replay_tombstone_accumulator,))
        or len(store.handoff_receipts) > MAX_QUEUE_RECORDS
    ):
        raise Reject()
    for epoch in store.used_security_epochs:
        _identifier(epoch)
    seen_channels: set[tuple[str, str]] = set()
    for digest, context in {**store.contexts, **store.retired_contexts}.items():
        _identifier(context.connection_id)
        _identifier(context.authenticated_principal)
        _identifier(context.replay_domain)
        _identifier(context.transport_security_epoch)
        channel_epoch = (context.connection_id, context.transport_security_epoch)
        if (
            digest != context.verification_digest
            or digest != _transport_digest(context)
            or context.producer_capability is not store.producer_capability
            or type(context.live_channel_handle) is not OpaqueLiveTransportHandle
            or not context.connection_id
            or not context.authenticated_principal
            or not context.replay_domain
            or not context.transport_security_epoch
            or not _complete_digest_set(
                (context.channel_binding_digest, context.verification_digest)
            )
            or channel_epoch in seen_channels
            or (
                digest in store.contexts
                and (
                    store.channel_states[digest] is not TransportState.ACTIVE
                    or context.transport_security_epoch != store.security_epoch
                )
            )
            or (
                digest in store.retired_contexts
                and store.channel_states[digest] is TransportState.ACTIVE
            )
        ):
            raise Reject()
        seen_channels.add(channel_epoch)
    for admission_key, receipt in store.handoff_receipts.items():
        _identifier(admission_key)
        if (
            receipt.admission_key != admission_key
            or receipt.producer_capability is not store.producer_capability
            or not _complete_digest_set(
                (
                    receipt.transport_verification_digest,
                    receipt.frame_digest,
                    receipt.receipt_digest,
                )
            )
            or receipt.receipt_digest
            != _fixture_digest(
                "transport-handoff-quiescence|"
                + repr(
                    (
                        receipt.admission_key,
                        receipt.transport_verification_digest,
                        receipt.frame_digest,
                        receipt.result.value,
                        receipt.dispatcher_epoch,
                    )
                )
            )
        ):
            raise Reject()


def transport_authenticate(
    store: TransportStore,
    *,
    connection_id: str,
    authenticated_principal: str,
    replay_domain: str,
    transport_security_epoch: str = "transport-security-v1",
) -> TransportContext:
    def mutate(candidate: TransportStore) -> TransportContext:
        if (
            not connection_id
            or not authenticated_principal
            or not replay_domain
            or not transport_security_epoch
            or transport_security_epoch != candidate.security_epoch
        ):
            raise Reject()
        channel_binding_digest = _fixture_digest(
            "transport-channel-binding|"
            + connection_id
            + "|"
            + transport_security_epoch
        )
        provisional = TransportContext(
            connection_id=connection_id,
            authenticated_principal=authenticated_principal,
            replay_domain=replay_domain,
            transport_security_epoch=transport_security_epoch,
            channel_binding_digest=channel_binding_digest,
            verification_digest="",
            producer_capability=candidate.producer_capability,
            live_channel_handle=OpaqueLiveTransportHandle(),
        )
        context = replace(
            provisional, verification_digest=_transport_digest(provisional)
        )
        for prior in (
            *candidate.contexts.values(),
            *candidate.retired_contexts.values(),
        ):
            if (prior.connection_id, prior.transport_security_epoch) == (
                context.connection_id,
                context.transport_security_epoch,
            ):
                if (
                    prior.authenticated_principal != context.authenticated_principal
                    or prior.replay_domain != context.replay_domain
                    or prior.channel_binding_digest != context.channel_binding_digest
                    or prior.verification_digest != context.verification_digest
                ):
                    raise Reject()
                if prior.verification_digest in candidate.retired_contexts:
                    raise Reject()
                return prior
        if len(candidate.contexts) >= candidate.context_capacity:
            raise Reject()
        candidate.contexts[context.verification_digest] = context
        candidate.channel_states[context.verification_digest] = TransportState.ACTIVE
        candidate.revision += 1
        return context

    result = _atomic(store, mutate, _validate_transport)
    return _require_result_type(result, TransportContext)


def transport_close(store: TransportStore, context: TransportContext) -> None:
    def mutate(candidate: TransportStore) -> None:
        digest = context.verification_digest
        if candidate.retired_contexts.get(digest) == context:
            if candidate.channel_states[digest] is TransportState.CLOSED:
                return
            raise Reject()
        if candidate.contexts.get(digest) != context:
            raise Reject()
        if len(candidate.retired_contexts) >= MAX_RETIRED_TRANSPORT_CONTEXTS:
            raise Reject()
        candidate.contexts.pop(digest)
        candidate.retired_contexts[digest] = context
        candidate.channel_states[digest] = TransportState.CLOSED
        candidate.replay_tombstone_accumulator = _transport_replay_accumulator(
            candidate.replay_tombstone_accumulator, context, TransportState.CLOSED
        )
        candidate.revision += 1

    _atomic(store, mutate, _validate_transport)


def transport_rotate_security_epoch(
    store: TransportStore, new_security_epoch: str
) -> None:
    def mutate(candidate: TransportStore) -> None:
        _identifier(new_security_epoch)
        if (
            new_security_epoch in candidate.used_security_epochs
            or len(candidate.used_security_epochs) >= MAX_TRANSPORT_SECURITY_EPOCHS
            or len(candidate.retired_contexts) + len(candidate.contexts)
            > MAX_RETIRED_TRANSPORT_CONTEXTS
        ):
            raise Reject()
        candidate.security_epoch = new_security_epoch
        candidate.used_security_epochs.add(new_security_epoch)
        for digest, context in tuple(candidate.contexts.items()):
            candidate.contexts.pop(digest)
            candidate.retired_contexts[digest] = context
            candidate.channel_states[digest] = TransportState.REVOKED
            candidate.replay_tombstone_accumulator = _transport_replay_accumulator(
                candidate.replay_tombstone_accumulator, context, TransportState.REVOKED
            )
        candidate.revision += 1

    _atomic(store, mutate, _validate_transport)


def _require_transport(
    store: TransportStore, context: TransportContext, *, expected_principal: str
) -> None:
    _validate_transport(store)
    if (
        store.contexts.get(context.verification_digest) != context
        or store.channel_states.get(context.verification_digest)
        is not TransportState.ACTIVE
        or context.transport_security_epoch != store.security_epoch
        or context.verification_digest != _transport_digest(context)
        or context.authenticated_principal != expected_principal
    ):
        raise Reject()


def transport_publish_handoff_quiescence(
    store: TransportStore,
    context: TransportContext,
    *,
    admission_key: str,
    frame_digest: str,
    result: HandoffResult,
) -> ProtectedHandoff:
    _closed_member(result, HandoffResult)

    def mutate(candidate: TransportStore) -> ProtectedHandoff:
        _require_transport(
            candidate, context, expected_principal=context.authenticated_principal
        )
        _identifier(admission_key)
        if not _complete_digest_set((frame_digest,)):
            raise Reject()
        dispatcher_epoch = context.verification_digest + ":" + admission_key
        receipt = ProtectedHandoff(
            admission_key,
            context.verification_digest,
            frame_digest,
            result,
            dispatcher_epoch,
            _fixture_digest(
                "transport-handoff-quiescence|"
                + repr(
                    (
                        admission_key,
                        context.verification_digest,
                        frame_digest,
                        result.value,
                        dispatcher_epoch,
                    )
                )
            ),
            candidate.producer_capability,
        )
        prior = candidate.handoff_receipts.get(admission_key)
        if prior is not None:
            if prior != receipt:
                raise Reject()
            return prior
        if len(candidate.handoff_receipts) >= MAX_QUEUE_RECORDS:
            raise Reject()
        candidate.handoff_receipts[admission_key] = receipt
        candidate.revision += 1
        return receipt

    result_receipt = _atomic(store, mutate, _validate_transport)
    return _require_result_type(result_receipt, ProtectedHandoff)


def _root_authority_value(
    fact: RegisteredObserverRootAuthorityFact,
) -> tuple[EligibleRoot, str, str, str]:
    return (
        fact.root,
        fact.observer_role_version,
        fact.source_security_epoch,
        fact.manifest_decision,
    )


def _validate_root_authority(hierarchy: ProtectedRootAuthority) -> None:
    _validate_closed_graph(hierarchy)
    fact = hierarchy.fact
    if (
        not fact.observer_role_version
        or not fact.source_security_epoch
        or fact.manifest_decision != "ALLOW_EXACT_REGISTERED_OBSERVER_ROOT"
    ):
        raise Reject()
    _validate_protection(
        hierarchy.protection,
        domain="registered-observer-root-authority",
        semantic_value=_root_authority_value(fact),
        audience_purpose="SOURCE_REGISTERED_OBSERVER_ROOT_AUTHORITY",
        verification_class="DEFAULT_DENY_MANIFEST_DECISION",
    )


def _validate_root_producer(
    store: RegisteredObserverRootAuthorityProducerStore,
) -> None:
    _validate_closed_graph(store)
    if (
        store.producer_credential
        is not _CONFIGURED_REGISTERED_ROOT_AUTHORITY_CREDENTIAL
        or store.revision < 0
        or len(store.hierarchies) > MAX_ELIGIBLE_ROOTS
    ):
        raise Reject()
    incarnations: set[str] = set()
    for audience_key, hierarchy in store.hierarchies.items():
        _validate_root_authority(hierarchy)
        root = hierarchy.fact.root
        _validate_root(root)
        if (
            root.audience_key != audience_key
            or root.root_incarnation in incarnations
            or root.authority_credential is not store.producer_credential
            or root.registered_root_hierarchy_digest != _registered_root_digest(root)
            or root.source_enrollment_hierarchy_digest
            != _source_enrollment_digest(root)
        ):
            raise Reject()
        incarnations.add(root.root_incarnation)


def registered_root_authority_publish(
    store: RegisteredObserverRootAuthorityProducerStore,
    root: EligibleRoot,
    *,
    observer_role_version: str,
    source_security_epoch: str,
) -> ProtectedRootAuthority:
    def mutate(
        candidate: RegisteredObserverRootAuthorityProducerStore,
    ) -> ProtectedRootAuthority:
        if (
            candidate.producer_credential
            is not _CONFIGURED_REGISTERED_ROOT_AUTHORITY_CREDENTIAL
            or root.authority_credential is not candidate.producer_credential
            or root.registered_root_hierarchy_digest != _registered_root_digest(root)
            or root.source_enrollment_hierarchy_digest
            != _source_enrollment_digest(root)
        ):
            raise Reject()
        fact = RegisteredObserverRootAuthorityFact(
            root=root,
            observer_role_version=observer_role_version,
            source_security_epoch=source_security_epoch,
            manifest_decision="ALLOW_EXACT_REGISTERED_OBSERVER_ROOT",
        )
        hierarchy = ProtectedRootAuthority(
            fact=fact,
            protection=_protect(
                "registered-observer-root-authority",
                _root_authority_value(fact),
                audience_purpose="SOURCE_REGISTERED_OBSERVER_ROOT_AUTHORITY",
                verification_class="DEFAULT_DENY_MANIFEST_DECISION",
            ),
        )
        prior = candidate.hierarchies.get(root.audience_key)
        if prior is not None:
            if prior != hierarchy:
                raise Reject()
            return prior
        if len(candidate.hierarchies) >= MAX_ELIGIBLE_ROOTS:
            raise Reject()
        candidate.hierarchies[root.audience_key] = hierarchy
        candidate.revision += 1
        return hierarchy

    result = _atomic(store, mutate, _validate_root_producer)
    return _require_result_type(result, ProtectedRootAuthority)


def _protection_digests(
    domain: str, semantic_value: object
) -> tuple[str, str, str, str, str, str, str, str]:
    semantic_digest = hashlib.sha256(repr(semantic_value).encode("utf-8")).hexdigest()
    envelope = _fixture_digest(domain + "|envelope|" + semantic_digest)
    family_manifest = _fixture_digest(domain + "|family-manifest|" + envelope)
    pre_manifest = _fixture_digest(domain + "|pre-manifest|" + family_manifest)
    producer_completion = _fixture_digest(
        domain + "|producer-completion|" + pre_manifest
    )
    delivery_capsule = _fixture_digest(
        domain + "|delivery-capsule|" + envelope + "|" + producer_completion
    )
    audience_proof = _fixture_digest(
        domain + "|audience-proof|" + envelope + "|" + family_manifest
    )
    manifest_proof = _fixture_digest(
        domain + "|manifest-proof|" + family_manifest + "|" + pre_manifest
    )
    delivery_verification = _fixture_digest(
        domain
        + "|delivery-verification|"
        + delivery_capsule
        + "|"
        + audience_proof
        + "|"
        + manifest_proof
    )
    return (
        envelope,
        family_manifest,
        pre_manifest,
        producer_completion,
        delivery_capsule,
        audience_proof,
        manifest_proof,
        delivery_verification,
    )


def _protect(
    domain: str,
    semantic_value: object,
    *,
    audience_purpose: str,
    verification_class: str,
) -> ProtectedArtifactChain:
    digests = _protection_digests(domain, semantic_value)
    return ProtectedArtifactChain(
        audience_purpose=audience_purpose,
        verification_class=verification_class,
        envelope_digest=digests[0],
        family_manifest_digest=digests[1],
        pre_manifest_digest=digests[2],
        producer_completion_digest=digests[3],
        delivery_capsule_digest=digests[4],
        audience_proof_digest=digests[5],
        manifest_proof_digest=digests[6],
        delivery_verification_digest=digests[7],
    )


def _validate_protection(
    chain: ProtectedArtifactChain,
    *,
    domain: str,
    semantic_value: object,
    audience_purpose: str,
    verification_class: str,
) -> None:
    expected = _protect(
        domain,
        semantic_value,
        audience_purpose=audience_purpose,
        verification_class=verification_class,
    )
    if chain != expected:
        raise Reject()


def _object_digest(value: object) -> str:
    _validate_closed_graph(value)
    return hashlib.sha256(repr(value).encode("utf-8")).hexdigest()


def _validate_plant_profile(profile: PlantProfile) -> None:
    for value in (
        profile.profile_id,
        profile.profile_revision,
        profile.media_type,
        profile.body_principal,
        profile.physical_actuation_jurisdiction_key,
        profile.jurisdiction_registry_incarnation,
        profile.authority_transaction_domain_key,
        profile.actuation_authority_domain_key,
    ):
        _identifier(value)
    if (
        not _complete_digest_set((profile.body_enrollment_digest,))
        or type(profile.profile_document) is not bytes
        or not 1 <= len(profile.profile_document) <= MAX_PLANT_PROFILE_DOCUMENT_BYTES
        or profile.media_type != "application/ncp-plant-profile+json"
        or not profile.canonical_bytes()
    ):
        raise Reject()


def _plant_profile_value(hierarchy: ProtectedPlantProfile) -> tuple[object, ...]:
    return (
        hierarchy.source_namespace,
        hierarchy.source_authority_id,
        hierarchy.source_index_incarnation,
        hierarchy.body_authority_id,
        hierarchy.body_security_epoch,
        hierarchy.profile,
        hierarchy.plant_profile_digest,
    )


def _validate_plant_hierarchy(
    hierarchy: ProtectedPlantProfile,
    *,
    expected_credential: OpaqueBodyPlantProfileAuthorityCredential,
) -> None:
    _validate_namespace(hierarchy.source_namespace)
    _validate_plant_profile(hierarchy.profile)
    for value in (
        hierarchy.source_authority_id,
        hierarchy.source_index_incarnation,
        hierarchy.body_authority_id,
        hierarchy.body_security_epoch,
    ):
        _identifier(value)
    if (
        hierarchy.source_namespace[1] != "PLANT"
        or hierarchy.profile.authority_transaction_domain_key
        != hierarchy.source_namespace[0]
        or hierarchy.plant_profile_digest != hierarchy.profile.content_digest
        or not _complete_digest_set((hierarchy.plant_profile_digest,))
        or hierarchy.producer_credential is not expected_credential
    ):
        raise Reject()
    _validate_protection(
        hierarchy.protection,
        domain="installed-body-plant-profile",
        semantic_value=_plant_profile_value(hierarchy),
        audience_purpose="PLANT_SESSION_GENERATION_SOURCE_AUTHORITY",
        verification_class="BODY_OWNED_CONTENT_ADDRESSED_PLANT_PROFILE",
    )


def _validate_body_authority(store: BodyPlantProfileAuthorityStore) -> None:
    for value in (
        store.authority_id,
        store.security_epoch,
        store.body_principal,
        store.physical_actuation_jurisdiction_key,
        store.jurisdiction_registry_incarnation,
    ):
        _identifier(value)
    if (
        store.producer_credential
        is not _CONFIGURED_BODY_PLANT_PROFILE_AUTHORITY_CREDENTIAL
        or store.revision < 0
        or not _complete_digest_set((store.body_enrollment_digest,))
        or len(store.hierarchies) > MAX_PRODUCER_NAMESPACES
    ):
        raise Reject()
    for namespace, hierarchy in store.hierarchies.items():
        _validate_plant_hierarchy(
            hierarchy, expected_credential=store.producer_credential
        )
        if (
            hierarchy.source_namespace != namespace
            or hierarchy.body_authority_id != store.authority_id
            or hierarchy.body_security_epoch != store.security_epoch
            or hierarchy.profile.body_principal != store.body_principal
            or hierarchy.profile.body_enrollment_digest != store.body_enrollment_digest
            or hierarchy.profile.physical_actuation_jurisdiction_key
            != store.physical_actuation_jurisdiction_key
            or hierarchy.profile.jurisdiction_registry_incarnation
            != store.jurisdiction_registry_incarnation
        ):
            raise Reject()


def body_publish_installed_plant_profile(
    store: BodyPlantProfileAuthorityStore,
    source_namespace: tuple[str, str, str],
    *,
    source_authority_id: str,
    source_index_incarnation: str,
    profile_id: str,
    profile_revision: str,
    profile_document: bytes,
) -> ProtectedPlantProfile:
    def mutate(candidate: BodyPlantProfileAuthorityStore) -> ProtectedPlantProfile:
        _validate_namespace(source_namespace)
        if source_namespace[1] != "PLANT":
            raise Reject()
        profile = PlantProfile(
            profile_id=profile_id,
            profile_revision=profile_revision,
            media_type="application/ncp-plant-profile+json",
            profile_document=profile_document,
            body_principal=candidate.body_principal,
            body_enrollment_digest=candidate.body_enrollment_digest,
            physical_actuation_jurisdiction_key=(
                candidate.physical_actuation_jurisdiction_key
            ),
            jurisdiction_registry_incarnation=(
                candidate.jurisdiction_registry_incarnation
            ),
            authority_transaction_domain_key=source_namespace[0],
            actuation_authority_domain_key=("actuation-domain:" + source_namespace[2]),
        )
        _validate_plant_profile(profile)
        provisional = ProtectedPlantProfile(
            source_namespace=source_namespace,
            source_authority_id=source_authority_id,
            source_index_incarnation=source_index_incarnation,
            body_authority_id=candidate.authority_id,
            body_security_epoch=candidate.security_epoch,
            profile=profile,
            plant_profile_digest=profile.content_digest,
            producer_credential=candidate.producer_credential,
            protection=EMPTY_PROTECTION,
        )
        hierarchy = replace(
            provisional,
            protection=_protect(
                "installed-body-plant-profile",
                _plant_profile_value(provisional),
                audience_purpose="PLANT_SESSION_GENERATION_SOURCE_AUTHORITY",
                verification_class=("BODY_OWNED_CONTENT_ADDRESSED_PLANT_PROFILE"),
            ),
        )
        prior = candidate.hierarchies.get(source_namespace)
        if prior is not None:
            if prior != hierarchy:
                raise Reject()
            return prior
        if len(candidate.hierarchies) >= MAX_PRODUCER_NAMESPACES:
            raise Reject()
        candidate.hierarchies[source_namespace] = hierarchy
        candidate.revision += 1
        return hierarchy

    result = _atomic(store, mutate, _validate_body_authority)
    return _require_result_type(result, ProtectedPlantProfile)


def _grant_plan_digest(
    source_authority_id: str, source_index_incarnation: str, grant: AcceptedGrant
) -> str:
    return _fixture_digest(
        "distributed-closure-plan|"
        + repr(
            (
                grant.closure_plan_id,
                grant.grant_id,
                grant.stable_key,
                grant.live_session_epoch,
                source_authority_id,
                source_index_incarnation,
                grant.source_security_epoch,
                grant.plant_profile_digest,
                grant.acceptance_transport_verification_digest,
                grant.acceptance_receipt_digest,
            )
        )
    )


def _closure_binding(
    fact: AcceptedGrantClosureFact | DistributedGrantClosureFact,
) -> tuple[object, ...]:
    return (
        fact.grant_id,
        fact.stable_key,
        fact.live_session_epoch,
        fact.source_authority_id,
        fact.source_index_incarnation,
        fact.accepted_source_security_epoch,
        fact.closure_source_security_epoch,
        fact.plant_profile_digest,
        fact.acceptance_transport_verification_digest,
        fact.acceptance_receipt_digest,
    )


def _distributed_binding(fact: DistributedGrantClosureFact) -> tuple[object, ...]:
    return (fact.closure_plan_id, fact.closure_plan_digest, *_closure_binding(fact))


def _expected_distributed_binding(
    source: Source, grant: AcceptedGrant
) -> tuple[object, ...]:
    return (
        grant.closure_plan_id,
        grant.closure_plan_digest,
        grant.grant_id,
        grant.stable_key,
        grant.live_session_epoch,
        source.source_authority_id,
        source.index.source_index_incarnation,
        grant.source_security_epoch,
        source.index.source_security_epoch,
        grant.plant_profile_digest,
        grant.acceptance_transport_verification_digest,
        grant.acceptance_receipt_digest,
    )


def _distributed_key(fact: DistributedGrantClosureFact) -> tuple[str, str, str, str]:
    return (
        fact.source_authority_id,
        fact.source_index_incarnation,
        fact.grant_id,
        fact.closure_plan_id,
    )


def _protect_distributed(fact: DistributedGrantClosureFact) -> ProtectionChain:
    return _protect(
        "distributed-grant-closure-authority",
        fact,
        audience_purpose="CURRENT_SOURCE_ACCEPTED_GRANT_CLOSURE_IMPORT",
        verification_class="DISTINCT_AUTHORITY_TERMINAL_GRANT_PLAN",
    )


def _validate_distributed_closure(
    hierarchy: object,
    *,
    expected_credential: OpaqueDistributedClosureAuthorityCredential,
) -> None:
    if type(hierarchy) is not ProtectedDistributedClosure:
        raise Reject()
    _validate_closed_graph(hierarchy)
    fact = hierarchy.fact
    _validate_stable_key(fact.stable_key)
    for value in (
        fact.authority_id,
        fact.authority_security_epoch,
        fact.closure_plan_id,
        fact.grant_id,
        fact.live_session_epoch,
        fact.source_authority_id,
        fact.source_index_incarnation,
        fact.accepted_source_security_epoch,
        fact.closure_source_security_epoch,
    ):
        _identifier(value)
    if (
        fact.state is not DistributedClosureState.TERMINAL
        or hierarchy.producer_credential is not expected_credential
        or (
            fact.plant_profile_digest is not None
            and not _complete_digest_set((fact.plant_profile_digest,))
        )
        or not _complete_digest_set(
            (
                fact.closure_plan_digest,
                fact.acceptance_transport_verification_digest,
                fact.acceptance_receipt_digest,
            )
        )
    ):
        raise Reject()
    _validate_protection(
        hierarchy.protection,
        domain="distributed-grant-closure-authority",
        semantic_value=fact,
        audience_purpose="CURRENT_SOURCE_ACCEPTED_GRANT_CLOSURE_IMPORT",
        verification_class="DISTINCT_AUTHORITY_TERMINAL_GRANT_PLAN",
    )


def _validate_closure_authority(store: ClosureAuthority) -> None:
    _validate_closed_graph(store)
    if (
        store.authority_id != "configured-distributed-closure-authority-v1"
        or store.security_epoch != "distributed-closure-security-v1"
        or store.producer_credential
        is not _CONFIGURED_DISTRIBUTED_CLOSURE_AUTHORITY_CREDENTIAL
        or store.revision < 0
        or len(store.hierarchies) > MAX_GENERATION_SLOTS
    ):
        raise Reject()
    for key, hierarchy in store.hierarchies.items():
        _validate_distributed_closure(
            hierarchy, expected_credential=store.producer_credential
        )
        fact = hierarchy.fact
        if key != _distributed_key(fact) or (
            fact.authority_id,
            fact.authority_security_epoch,
        ) != (store.authority_id, store.security_epoch):
            raise Reject()


def _validate_grant_closure(
    hierarchy: ProtectedGrantClosure,
    *,
    expected_credential: OpaqueStateOwnerCredential,
    expected_distributed_credential: OpaqueDistributedClosureAuthorityCredential,
) -> None:
    _validate_closed_graph(hierarchy)
    fact = hierarchy.fact
    _validate_distributed_closure(
        fact.distributed_closure, expected_credential=expected_distributed_credential
    )
    external = fact.distributed_closure.fact
    _validate_stable_key(fact.stable_key)
    for value in (
        fact.grant_id,
        fact.live_session_epoch,
        fact.source_authority_id,
        fact.source_index_incarnation,
        fact.accepted_source_security_epoch,
        fact.closure_source_security_epoch,
    ):
        _identifier(value)
    if (
        hierarchy.producer_credential is not expected_credential
        or (
            fact.plant_profile_digest is not None
            and not _complete_digest_set((fact.plant_profile_digest,))
        )
        or not _complete_digest_set(
            (
                fact.acceptance_transport_verification_digest,
                fact.acceptance_receipt_digest,
            )
        )
        or _closure_binding(fact) != _closure_binding(external)
    ):
        raise Reject()
    _validate_protection(
        hierarchy.protection,
        domain="accepted-grant-distributed-closure",
        semantic_value=fact,
        audience_purpose="SOURCE_ACCEPTED_GRANT_CLOSURE_IMPORT",
        verification_class="CURRENT_SOURCE_AUTHORITY_PROTECTED_CLOSURE",
    )


def _grant_closure_receipt(
    source: Source, grant: AcceptedGrant, hierarchy: ProtectedGrantClosure
) -> ProtectedAcceptedGrantClosureReceipt:
    hierarchy_digest = _object_digest(hierarchy)
    fact = hierarchy.fact
    distributed_digest = _object_digest(fact.distributed_closure)
    commit_semantic = (
        grant.grant_id,
        grant.live_session_epoch,
        source.source_authority_id,
        source.index.source_index_incarnation,
        grant.source_security_epoch,
        fact.closure_source_security_epoch,
        grant.acceptance_transport_verification_digest,
        distributed_digest,
        hierarchy_digest,
    )
    return ProtectedAcceptedGrantClosureReceipt(
        grant_id=grant.grant_id,
        requester_principal=grant.stable_key.requester_principal,
        live_session_epoch=grant.live_session_epoch,
        source_authority_id=source.source_authority_id,
        source_index_incarnation=source.index.source_index_incarnation,
        source_security_epoch=grant.source_security_epoch,
        closure_source_security_epoch=fact.closure_source_security_epoch,
        acceptance_transport_verification_digest=(
            grant.acceptance_transport_verification_digest
        ),
        distributed_closure_hierarchy_digest=distributed_digest,
        closure_evidence_hierarchy_digest=hierarchy_digest,
        source_commit_receipt_digest=_fixture_digest(
            "grant-closure-import|" + repr(commit_semantic)
        ),
        producer_credential=source.producer_credential,
    )


def _enrollment_value(hierarchy: ProtectedEnrollment) -> tuple[object, ...]:
    return (
        hierarchy.source_namespace,
        hierarchy.root,
        hierarchy.registered_authority_hierarchy_digest,
        hierarchy.eligibility_hierarchy_digest,
        hierarchy.anchor_notification_hierarchy_digest,
        hierarchy.observer_role_version,
        hierarchy.source_security_epoch,
    )


def _validate_enrollment(hierarchy: ProtectedEnrollment) -> None:
    _validate_closed_graph(hierarchy)
    semantic_value = _enrollment_value(hierarchy)
    expected_receipt = _fixture_digest(
        "source-observer-root-enrollment-receipt|" + repr(semantic_value)
    )
    if (
        hierarchy.enrollment_receipt_digest != expected_receipt
        or not _complete_digest_set(
            (
                hierarchy.registered_authority_hierarchy_digest,
                hierarchy.enrollment_receipt_digest,
            )
        )
        or not hierarchy.observer_role_version
        or not hierarchy.source_security_epoch
    ):
        raise Reject()
    if hierarchy.root.availability_profile is SOURCE_ONLY:
        if (
            hierarchy.eligibility_hierarchy_digest is not None
            or hierarchy.anchor_notification_hierarchy_digest is not None
        ):
            raise Reject()
    elif (
        hierarchy.eligibility_hierarchy_digest is None
        or hierarchy.anchor_notification_hierarchy_digest is None
        or not _complete_digest_set(
            (
                hierarchy.eligibility_hierarchy_digest,
                hierarchy.anchor_notification_hierarchy_digest,
            )
        )
    ):
        raise Reject()
    _validate_protection(
        hierarchy.protection,
        domain="source-observer-root-enrollment",
        semantic_value=semantic_value + (expected_receipt,),
        audience_purpose="OBSERVER_ROOT_SOURCE_ENROLLMENT",
        verification_class="DURABLE_SOURCE_AUTHORITY_COMMIT",
    )


def _publication_value(
    hierarchy: ProtectedSourceChallengePublicationHierarchy,
) -> tuple[object, ...]:
    return (
        hierarchy.source_authority_id,
        hierarchy.source_index_incarnation,
        hierarchy.source_entry,
        hierarchy.source_enrollment_hierarchy_digest,
        hierarchy.transport_verification_digest,
        hierarchy.source_capsule_digest,
        hierarchy.source_producer_coordinate,
        hierarchy.previous_source_root,
        hierarchy.committed_source_root,
        hashlib.sha256(hierarchy.membership_proof).hexdigest(),
        hierarchy.source_commit_receipt_digest,
        hierarchy.source_retention_receipt_digest,
    )


def _validate_publication(
    hierarchy: ProtectedSourceChallengePublicationHierarchy,
    *,
    expected_credential: OpaqueStateOwnerCredential | None = None,
) -> None:
    _validate_closed_graph(hierarchy)
    entry = hierarchy.source_entry
    commit_semantic = (
        hierarchy.source_authority_id,
        hierarchy.source_index_incarnation,
        entry,
        hierarchy.previous_source_root,
        hierarchy.committed_source_root,
    )
    expected_commit = _fixture_digest("source-index-commit|" + repr(commit_semantic))
    expected_retention = _fixture_digest(
        "source-index-retention|"
        + expected_commit
        + "|"
        + hashlib.sha256(hierarchy.membership_proof).hexdigest()
    )
    if (
        entry.kind is not IndexEntryKind.CHALLENGE_ISSUED
        or not hierarchy.source_authority_id
        or not hierarchy.source_index_incarnation
        or len(hierarchy.previous_source_root) != 32
        or len(hierarchy.committed_source_root) != 32
        or hierarchy.source_commit_receipt_digest != expected_commit
        or hierarchy.source_retention_receipt_digest != expected_retention
        or not _complete_digest_set(
            (
                hierarchy.source_enrollment_hierarchy_digest,
                hierarchy.transport_verification_digest,
                hierarchy.source_capsule_digest,
                hierarchy.source_commit_receipt_digest,
                hierarchy.source_retention_receipt_digest,
            )
        )
        or not hierarchy.source_producer_coordinate
        or (
            expected_credential is not None
            and hierarchy.producer_credential is not expected_credential
        )
    ):
        raise Reject()
    verify_sparse_proof(
        hierarchy.membership_proof,
        expected_context=ProofContext.SOURCE,
        expected_kind=ProofKind.MEMBERSHIP,
        expected_root=hierarchy.committed_source_root,
        stable_key=entry.stable_key,
        canonical_entry=source_entry_bytes(entry),
    )
    _validate_protection(
        hierarchy.protection,
        domain="source-challenge-publication",
        semantic_value=_publication_value(hierarchy),
        audience_purpose="REGISTERED_OBSERVER_ROOT_PRIVATE_CHALLENGE",
        verification_class="DURABLE_SOURCE_INDEX_COMMIT",
    )


def _anchor_entry_value(hierarchy: ProtectedAnchorEntry) -> tuple[object, ...]:
    return (
        hierarchy.anchor_authority,
        hierarchy.anchor_selector_incarnation,
        hierarchy.anchor_security_epoch,
        hierarchy.entry,
        hierarchy.source_publication_hierarchy_digest,
        hierarchy.previous_anchor_root,
        hierarchy.committed_anchor_root,
        hashlib.sha256(hierarchy.membership_proof).hexdigest(),
        hierarchy.anchor_commit_receipt_digest,
        hierarchy.anchor_retention_receipt_digest,
    )


def _validate_anchor_entry(
    hierarchy: ProtectedAnchorEntry,
    *,
    expected_credential: OpaqueStateOwnerCredential | None = None,
) -> None:
    commit_semantic = (
        hierarchy.anchor_authority,
        hierarchy.anchor_selector_incarnation,
        hierarchy.anchor_security_epoch,
        hierarchy.entry,
        hierarchy.source_publication_hierarchy_digest,
        hierarchy.previous_anchor_root,
        hierarchy.committed_anchor_root,
    )
    expected_commit = _fixture_digest("anchor-entry-commit|" + repr(commit_semantic))
    expected_retention = _fixture_digest(
        "anchor-entry-retention|"
        + expected_commit
        + "|"
        + hashlib.sha256(hierarchy.membership_proof).hexdigest()
    )
    if (
        not hierarchy.anchor_authority
        or not hierarchy.anchor_selector_incarnation
        or not hierarchy.anchor_security_epoch
        or len(hierarchy.previous_anchor_root) != 32
        or len(hierarchy.committed_anchor_root) != 32
        or hierarchy.anchor_commit_receipt_digest != expected_commit
        or hierarchy.anchor_retention_receipt_digest != expected_retention
        or not _complete_digest_set(
            (
                hierarchy.source_publication_hierarchy_digest,
                hierarchy.anchor_commit_receipt_digest,
                hierarchy.anchor_retention_receipt_digest,
            )
        )
        or (
            expected_credential is not None
            and hierarchy.producer_credential is not expected_credential
        )
    ):
        raise Reject()
    verify_sparse_proof(
        hierarchy.membership_proof,
        expected_context=ProofContext.ANCHOR,
        expected_kind=ProofKind.MEMBERSHIP,
        expected_root=hierarchy.committed_anchor_root,
        stable_key=hierarchy.entry.stable_key,
        canonical_entry=anchor_entry_bytes(hierarchy.entry),
    )
    _validate_protection(
        hierarchy.protection,
        domain="anchor-challenge-entry",
        semantic_value=_anchor_entry_value(hierarchy),
        audience_purpose="SOURCE_PAIRED_FRAME_ADMISSION",
        verification_class="DURABLE_INDEPENDENT_ANCHOR_COMMIT",
    )


def _relay_value(hierarchy: ProtectedRelay) -> tuple[object, ...]:
    return (
        hierarchy.anchor_entry_hierarchy_digest,
        hierarchy.entry,
        hashlib.sha256(hierarchy.anchor_observer_capsule).hexdigest(),
        hierarchy.binding,
        hierarchy.common_completion_coordinate,
    )


def _validate_relay(
    hierarchy: ProtectedRelay,
    *,
    expected_credential: OpaqueStateOwnerCredential | None = None,
) -> None:
    admission_key = hierarchy.entry.paired_frame_admission_key
    if (
        not hierarchy.anchor_observer_capsule
        or len(hierarchy.anchor_observer_capsule) > MAX_CAPSULE_BYTES
        or not _complete_digest_set((hierarchy.anchor_entry_hierarchy_digest,))
        or hierarchy.binding.producer_coordinate != "anchor-producer:" + admission_key
        or hierarchy.common_completion_coordinate
        != "anchor-completion:" + admission_key
        or (
            expected_credential is not None
            and hierarchy.producer_credential is not expected_credential
        )
    ):
        raise Reject()
    _validate_protection(
        hierarchy.protection,
        domain="anchor-observer-opaque-relay",
        semantic_value=_relay_value(hierarchy),
        audience_purpose="REGISTERED_OBSERVER_ROOT_OPAQUE_RELAY",
        verification_class="DURABLE_INDEPENDENT_ANCHOR_OUTPUT",
    )


def _closure_value(hierarchy: ProtectedClosureBundleHierarchy) -> tuple[object, ...]:
    return (
        hierarchy.bundle,
        hierarchy.producer_kind,
        hierarchy.producer_authority_id,
        hierarchy.producer_security_epoch,
        hierarchy.enrollment_ancestry_digest,
        hierarchy.closure_commit_receipt_digest,
    )


def _build_closure(
    bundle: ClosureBundle,
    *,
    producer_kind: str,
    producer_authority_id: str,
    producer_security_epoch: str,
    enrollment_ancestry_digest: str,
    producer_credential: OpaqueStateOwnerCredential,
) -> ProtectedClosureBundleHierarchy:
    commit_semantic = (
        bundle,
        producer_kind,
        producer_authority_id,
        producer_security_epoch,
        enrollment_ancestry_digest,
    )
    commit_receipt = _fixture_digest(
        "namespace-closure-commit|" + repr(commit_semantic)
    )
    provisional = ProtectedClosureBundleHierarchy(
        bundle=bundle,
        producer_kind=producer_kind,
        producer_authority_id=producer_authority_id,
        producer_security_epoch=producer_security_epoch,
        enrollment_ancestry_digest=enrollment_ancestry_digest,
        closure_commit_receipt_digest=commit_receipt,
        producer_credential=producer_credential,
        protection=EMPTY_PROTECTION,
    )
    return replace(
        provisional,
        protection=_protect(
            "namespace-closure-bundle",
            _closure_value(provisional),
            audience_purpose="ENROLLED_OBSERVER_NAMESPACE_CLOSURE",
            verification_class="PERMANENT_RETAINED_CLOSURE_ROOT",
        ),
    )


def _validate_closure(
    hierarchy: ProtectedClosureBundleHierarchy,
    *,
    expected_credential: OpaqueStateOwnerCredential,
) -> None:
    _validate_closed_graph(hierarchy)
    expected = _build_closure(
        hierarchy.bundle,
        producer_kind=hierarchy.producer_kind,
        producer_authority_id=hierarchy.producer_authority_id,
        producer_security_epoch=hierarchy.producer_security_epoch,
        enrollment_ancestry_digest=hierarchy.enrollment_ancestry_digest,
        producer_credential=expected_credential,
    )
    if (
        hierarchy != expected
        or hierarchy.producer_credential is not expected_credential
        or hierarchy.producer_kind not in {"SOURCE", "ANCHOR"}
        or not hierarchy.producer_authority_id
        or not hierarchy.producer_security_epoch
        or not _complete_digest_set(
            (
                hierarchy.enrollment_ancestry_digest,
                hierarchy.closure_commit_receipt_digest,
            )
        )
        or len(hierarchy.bundle.root) != 32
    ):
        raise Reject()


def _anchor_eligibility_digest(root: EligibleRoot) -> str:
    return _json_digest(
        {
            "availability_profile": root.availability_profile.value,
            "registered_root_hierarchy_digest": (root.registered_root_hierarchy_digest),
            "root_id": root.root_id,
            "root_incarnation": root.root_incarnation,
            "source_enrollment_hierarchy_digest": (
                root.source_enrollment_hierarchy_digest
            ),
        }
    )


def _registered_root_digest(root: EligibleRoot) -> str:
    return _json_digest(
        {
            "availability_profile": root.availability_profile.value,
            "root_id": root.root_id,
            "root_incarnation": root.root_incarnation,
            "source_enrollment_hierarchy_digest": (
                root.source_enrollment_hierarchy_digest
            ),
        }
    )


def _source_enrollment_digest(root: EligibleRoot) -> str:
    return _json_digest(
        {
            "availability_profile": root.availability_profile.value,
            "root_id": root.root_id,
            "root_incarnation": root.root_incarnation,
        }
    )


def _validate_root(root: EligibleRoot) -> None:
    _validate_closed_graph(root)
    _identifier(root.root_id)
    _identifier(root.root_incarnation)
    if (
        root.authority_credential
        is not _CONFIGURED_REGISTERED_ROOT_AUTHORITY_CREDENTIAL
        or root.source_enrollment_hierarchy_digest != _source_enrollment_digest(root)
        or root.registered_root_hierarchy_digest != _registered_root_digest(root)
    ):
        raise Reject()
    if root.availability_profile is SOURCE_ONLY:
        if root.anchor_enrollment_entry_digest is not None:
            raise Reject()
    elif root.availability_profile is ANCHOR_PROFILE:
        if root.anchor_enrollment_entry_digest != _anchor_eligibility_digest(root):
            raise Reject()
    else:
        raise Reject()


def _complete_digest_set(values: tuple[str, ...]) -> bool:
    return all(
        len(value) == 64 and all(character in "0123456789abcdef" for character in value)
        for value in values
    )


def _eligibility_digest(hierarchy: ProtectedEligibility) -> str:
    return hashlib.sha256(repr(hierarchy).encode("utf-8")).hexdigest()


def _notification_digest(hierarchy: ProtectedNotification) -> str:
    return hashlib.sha256(repr(hierarchy).encode("utf-8")).hexdigest()


def _clock_digest(relation: ClockRelation) -> str:
    value = {
        "anchor_clock_epoch": relation.anchor_clock_epoch,
        "anchor_clock_id": relation.anchor_clock_id,
        "anchor_minus_source_lower": relation.anchor_minus_source_lower,
        "anchor_minus_source_upper": relation.anchor_minus_source_upper,
        "anchor_reference_value": relation.anchor_reference_value,
        "anchor_valid_from": relation.anchor_valid_from,
        "anchor_valid_through_exclusive": (relation.anchor_valid_through_exclusive),
        "maximum_relative_rate_ppb": relation.maximum_relative_rate_ppb,
        "relation_id": relation.relation_id,
        "source_clock_epoch": relation.source_clock_epoch,
        "source_clock_id": relation.source_clock_id,
        "source_reference_value": relation.source_reference_value,
        "source_valid_from": relation.source_valid_from,
        "source_valid_through_exclusive": (relation.source_valid_through_exclusive),
    }
    return hashlib.sha256(
        json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()


def _seal_clock_relation(relation: ClockRelation) -> ClockRelation:
    return replace(relation, semantic_digest=_clock_digest(relation))


def _validate_clock(relation: ClockRelation) -> None:
    for value in (
        relation.relation_id,
        relation.source_clock_id,
        relation.anchor_clock_id,
        relation.source_clock_epoch,
        relation.anchor_clock_epoch,
    ):
        _identifier(value)
    reference_offset = relation.anchor_reference_value - relation.source_reference_value
    maximum_source_distance = max(
        relation.source_reference_value - relation.source_valid_from,
        (relation.source_valid_through_exclusive - 1) - relation.source_reference_value,
    )
    rate_drift_bound = (
        relation.maximum_relative_rate_ppb * maximum_source_distance + 999_999_999
    ) // 1_000_000_000
    if (
        not relation.relation_id
        or not relation.source_clock_id
        or not relation.anchor_clock_id
        or not relation.source_clock_epoch
        or not relation.anchor_clock_epoch
        or relation.anchor_minus_source_lower > relation.anchor_minus_source_upper
        or abs(relation.anchor_minus_source_lower) > CLOCK_OFFSET_ABS_MAX
        or abs(relation.anchor_minus_source_upper) > CLOCK_OFFSET_ABS_MAX
        or not (
            0
            <= relation.source_valid_from
            < relation.source_valid_through_exclusive
            <= CLOCK_VALUE_MAX
        )
        or not (
            0
            <= relation.anchor_valid_from
            < relation.anchor_valid_through_exclusive
            <= CLOCK_VALUE_MAX
        )
        or not (
            relation.source_valid_from
            <= relation.source_reference_value
            < relation.source_valid_through_exclusive
        )
        or not (
            relation.anchor_valid_from
            <= relation.anchor_reference_value
            < relation.anchor_valid_through_exclusive
        )
        or not (0 <= relation.maximum_relative_rate_ppb <= 1_000_000_000)
        or relation.anchor_minus_source_lower > reference_offset - rate_drift_bound
        or relation.anchor_minus_source_upper < reference_offset + rate_drift_bound
        or relation.semantic_digest != _clock_digest(relation)
    ):
        raise Reject()


def _validate_sample(sample: BoundedClockSample) -> None:
    _identifier(sample.clock_id)
    _identifier(sample.clock_epoch)
    if (
        not sample.clock_id
        or not sample.clock_epoch
        or not (0 <= sample.lower <= sample.upper <= CLOCK_VALUE_MAX)
    ):
        raise Reject()


def _checked_clock_add(value: int, offset: int) -> int:
    if not (0 <= value <= CLOCK_VALUE_MAX):
        raise Reject()
    if abs(offset) > CLOCK_OFFSET_ABS_MAX:
        raise Reject()
    result = value + offset
    if not (0 <= result <= CLOCK_VALUE_MAX):
        raise Reject()
    return result


def _clock_images(
    sample: BoundedClockSample, relation: ClockRelation
) -> tuple[int, int]:
    _validate_sample(sample)
    _validate_clock(relation)
    if (
        sample.clock_id != relation.source_clock_id
        or sample.clock_epoch != relation.source_clock_epoch
        or sample.lower < relation.source_valid_from
        or sample.upper >= relation.source_valid_through_exclusive
    ):
        raise Reject()
    mapped = (
        _checked_clock_add(sample.lower, relation.anchor_minus_source_lower),
        _checked_clock_add(sample.upper, relation.anchor_minus_source_upper),
    )
    if (
        mapped[0] < relation.anchor_valid_from
        or mapped[1] >= relation.anchor_valid_through_exclusive
    ):
        raise Reject()
    return mapped


def _validate_anchor_sample(
    sample: BoundedClockSample, relation: ClockRelation
) -> None:
    _validate_sample(sample)
    _validate_clock(relation)
    if (
        sample.clock_id != relation.anchor_clock_id
        or sample.clock_epoch != relation.anchor_clock_epoch
        or sample.lower < relation.anchor_valid_from
        or sample.upper >= relation.anchor_valid_through_exclusive
    ):
        raise Reject()


def _validate_eligibility(hierarchy: ProtectedEligibility) -> None:
    _validate_closed_graph(hierarchy)
    eligibility = hierarchy.eligibility
    _validate_clock(eligibility.qualified_clock_relation)
    digests = (
        hierarchy.envelope_digest,
        hierarchy.family_manifest_digest,
        hierarchy.pre_manifest_digest,
        hierarchy.producer_completion_digest,
        hierarchy.delivery_capsule_digest,
        hierarchy.audience_proof_digest,
        hierarchy.manifest_proof_digest,
        hierarchy.delivery_verification_digest,
    )
    expected_digests = _protection_digests(
        "observer-root-enrollment-eligibility", eligibility
    )
    if (
        hierarchy.audience_purpose != "OBSERVER_ROOT_ENROLLMENT_ELIGIBILITY"
        or hierarchy.verification_class != "EPHEMERAL_AUTHORITY_WINDOW"
        or not _complete_digest_set(digests)
        or digests != expected_digests
        or eligibility.root.availability_profile is not ANCHOR_PROFILE
        or not eligibility.anchor_authority
        or not eligibility.source_index_incarnation
        or not eligibility.anchor_entry_key
        or eligibility.exclusive_anchor_cutoff <= 0
        or not eligibility.source_security_epoch
        or not eligibility.observer_role_version
        or not _complete_digest_set(
            (
                eligibility.root.registered_root_hierarchy_digest,
                eligibility.root.source_enrollment_hierarchy_digest,
                eligibility.clock_relation_digest,
            )
        )
        or eligibility.root.anchor_enrollment_entry_digest
        != _anchor_eligibility_digest(eligibility.root)
    ):
        raise Reject()


def _validate_notification(hierarchy: ProtectedNotification) -> None:
    _validate_closed_graph(hierarchy)
    digests = (
        hierarchy.envelope_digest,
        hierarchy.family_manifest_digest,
        hierarchy.pre_manifest_digest,
        hierarchy.producer_completion_digest,
        hierarchy.delivery_capsule_digest,
        hierarchy.audience_proof_digest,
        hierarchy.manifest_proof_digest,
        hierarchy.delivery_verification_digest,
    )
    semantic_value = (
        hierarchy.eligibility_hierarchy_digest,
        hierarchy.anchor_entry_digest,
        hierarchy.source_namespace,
        hierarchy.root_audience_key,
        hierarchy.anchor_authority,
        hierarchy.exclusive_anchor_cutoff,
        hierarchy.audience_purpose,
        hierarchy.verification_class,
    )
    expected_digests = _protection_digests(
        "anchor-source-enrollment-notification", semantic_value
    )
    if (
        hierarchy.audience_purpose != "OBSERVER_ROOT_ENROLLMENT_NOTIFICATION"
        or hierarchy.verification_class != "DURABLE_HISTORICAL_COMMIT"
        or not _complete_digest_set(
            (
                hierarchy.eligibility_hierarchy_digest,
                hierarchy.anchor_entry_digest,
                *digests,
            )
        )
        or digests != expected_digests
        or not hierarchy.anchor_authority
        or hierarchy.exclusive_anchor_cutoff <= 0
    ):
        raise Reject()


def _validate_lineage(store: LineageStore) -> None:
    for value in (store.authority_id, store.registry_incarnation, store.security_epoch):
        _identifier(value)
    if (
        store.producer_credential is not _CONFIGURED_LINEAGE_AUTHORITY_CREDENTIAL
        or len(store.live_incarnations) > MAX_PRODUCER_NAMESPACES
        or len(store.terminal_hierarchies) > MAX_PRODUCER_NAMESPACES
        or any(
            len(incarnations) > MAX_LINEAGE_INCARNATIONS_PER_NAMESPACE
            for incarnations in store.live_incarnations.values()
        )
    ):
        raise Reject()
    for namespace, incarnations in store.live_incarnations.items():
        _validate_namespace(namespace)
        for incarnation in incarnations:
            _identifier(incarnation)
    for namespace, hierarchy in store.terminal_hierarchies.items():
        if store.live_incarnations.get(namespace) or (
            hierarchy.source_namespace != namespace
            or hierarchy.authority_id != store.authority_id
            or hierarchy.registry_incarnation != store.registry_incarnation
            or hierarchy.security_epoch != store.security_epoch
            or hierarchy.producer_credential is not store.producer_credential
            or hierarchy.terminal_receipt_digest
            != _fixture_digest(
                "lineage-no-successor|"
                + repr(
                    (
                        namespace,
                        hierarchy.source_index_incarnation,
                        store.authority_id,
                        store.registry_incarnation,
                        store.security_epoch,
                    )
                )
            )
        ):
            raise Reject()


def lineage_register_source(
    store: LineageStore, namespace: tuple[str, str, str], source_index_incarnation: str
) -> None:
    def mutate(candidate: LineageStore) -> None:
        _validate_namespace(namespace)
        _identifier(source_index_incarnation)
        if namespace in candidate.terminal_hierarchies:
            raise Reject()
        candidate.live_incarnations.setdefault(namespace, set()).add(
            source_index_incarnation
        )

    _atomic(store, mutate, _validate_lineage)


def lineage_finalize_no_successor(
    store: LineageStore, namespace: tuple[str, str, str], source_index_incarnation: str
) -> ProtectedNoSuccessor:
    def mutate(candidate: LineageStore) -> ProtectedNoSuccessor:
        prior = candidate.terminal_hierarchies.get(namespace)
        if prior is not None:
            if prior.source_index_incarnation != source_index_incarnation:
                raise Reject()
            return prior
        if candidate.live_incarnations.get(namespace) != {source_index_incarnation}:
            raise Reject()
        hierarchy = ProtectedNoSuccessor(
            namespace,
            source_index_incarnation,
            candidate.authority_id,
            candidate.registry_incarnation,
            candidate.security_epoch,
            _fixture_digest(
                "lineage-no-successor|"
                + repr(
                    (
                        namespace,
                        source_index_incarnation,
                        candidate.authority_id,
                        candidate.registry_incarnation,
                        candidate.security_epoch,
                    )
                )
            ),
            candidate.producer_credential,
        )
        candidate.live_incarnations[namespace].clear()
        candidate.terminal_hierarchies[namespace] = hierarchy
        return hierarchy

    result = _atomic(store, mutate, _validate_lineage)
    return _require_result_type(result, ProtectedNoSuccessor)


def _validate_retirement(
    hierarchy: ProtectedRetirement,
    *,
    expected_source_credential: OpaqueStateOwnerCredential | None = None,
    expected_lineage_credential: OpaqueLineageAuthorityCredential | None = None,
) -> None:
    _validate_closed_graph(hierarchy)
    projection = hierarchy.projection
    digests = (
        hierarchy.envelope_digest,
        hierarchy.family_manifest_digest,
        hierarchy.pre_manifest_digest,
        hierarchy.producer_completion_digest,
        hierarchy.delivery_capsule_digest,
        hierarchy.audience_proof_digest,
        hierarchy.manifest_proof_digest,
        hierarchy.delivery_verification_digest,
    )
    expected_digests = _protection_digests(
        "cooperative-source-retirement",
        (
            projection,
            hierarchy.family_kinds,
            hierarchy.closure_audience,
            hierarchy.source_closure_hierarchy_digest,
            hierarchy.source_authority_id,
            hierarchy.source_index_incarnation,
            hierarchy.source_security_epoch,
            hierarchy.no_successor_hierarchy,
            hierarchy.audience_purpose,
            hierarchy.verification_class,
        ),
    )
    if (
        hierarchy.audience_purpose != "SOURCE_NAMESPACE_COOPERATIVE_RETIREMENT"
        or hierarchy.verification_class != _TOMBSTONE
        or not _complete_digest_set(
            (
                projection.source_retirement_receipt_digest,
                projection.source_index_closure_receipt_digest,
                projection.accepted_grant_closure_inventory_digest,
                hierarchy.source_closure_hierarchy_digest,
                *digests,
            )
        )
        or digests != expected_digests
        or len(projection.frozen_source_index_root) != 32
        or projection.availability_profile is not ANCHOR_PROFILE
        or not projection.anchor_authority
        or not projection.anchor_selector_incarnation
        or not projection.reservation_id
        or not projection.allocation_id
        or projection.no_successor_evidence_digest
        != _object_digest(hierarchy.no_successor_hierarchy)
        or (
            expected_source_credential is not None
            and hierarchy.producer_credential is not expected_source_credential
        )
        or (
            expected_lineage_credential is not None
            and hierarchy.no_successor_hierarchy.producer_credential
            is not expected_lineage_credential
        )
        or hierarchy.no_successor_hierarchy.source_namespace
        != projection.source_namespace
        or hierarchy.no_successor_hierarchy.source_index_incarnation
        != hierarchy.source_index_incarnation
        or _ANCHOR_RETIREMENT not in hierarchy.family_kinds
        or tuple(sorted(hierarchy.closure_audience)) != hierarchy.closure_audience
    ):
        raise Reject()


def _validate_source(source: Source) -> None:
    _validate_closed_graph(source)
    index = source.index
    generations = source.generations
    _validate_namespace(index.source_namespace)
    _identifier(source.source_authority_id)
    for value in (
        index.source_index_incarnation,
        index.source_security_epoch,
        index.observer_role_version,
        index.source_clock_id,
        index.source_clock_epoch,
        index.live_session_epoch,
    ):
        _identifier(value)
    plant_hierarchy = source.installed_plant_profile_hierarchy
    if (
        source.trusted_body_plant_profile_authority_credential
        is not _CONFIGURED_BODY_PLANT_PROFILE_AUTHORITY_CREDENTIAL
        or source.trusted_distributed_closure_authority_credential
        is not _CONFIGURED_DISTRIBUTED_CLOSURE_AUTHORITY_CREDENTIAL
        or source.trusted_distributed_closure_authority_id
        != "configured-distributed-closure-authority-v1"
        or source.trusted_distributed_closure_security_epoch
        != "distributed-closure-security-v1"
    ):
        raise Reject()
    if index.source_namespace[1] == "PLANT":
        if plant_hierarchy is None:
            raise Reject()
        _validate_plant_hierarchy(
            plant_hierarchy,
            expected_credential=(
                source.trusted_body_plant_profile_authority_credential
            ),
        )
        if (
            plant_hierarchy.source_namespace != index.source_namespace
            or plant_hierarchy.source_authority_id != source.source_authority_id
            or plant_hierarchy.source_index_incarnation
            != index.source_index_incarnation
            or index.plant_profile_digest != plant_hierarchy.plant_profile_digest
        ):
            raise Reject()
    elif plant_hierarchy is not None or index.plant_profile_digest is not None:
        raise Reject()
    if (
        not 0
        < index.acceptance_not_after
        <= index.authority_lease_not_after
        <= CLOCK_VALUE_MAX
    ):
        raise Reject()
    if (
        not 1 <= index.eligible_capacity <= MAX_ELIGIBLE_ROOTS
        or not 1 <= index.entry_capacity <= MAX_ISSUANCE_ENTRIES
        or not 1 <= generations.slot_capacity <= MAX_GENERATION_SLOTS
        or not 1 <= source.queue.record_capacity <= MAX_QUEUE_RECORDS
        or len(source.in_flight_exposure) > MAX_QUEUE_RECORDS
    ):
        raise Reject()
    for exposure in source.in_flight_exposure:
        _identifier(exposure)
    _validate_transport(source.transport_authority)
    _validate_root_producer(source.registered_root_authority_producer)
    if (
        len(index.root_admissions) > index.eligible_capacity
        or len(index.registered_root_authorities) > index.eligible_capacity
        or len(index.eligible_roots) > index.eligible_capacity
    ):
        raise Reject()
    if index.availability_profile is SOURCE_ONLY:
        if (
            index.anchor_allocation_binding is not None
            or source.trusted_anchor_coordinate is not None
        ):
            raise Reject()
    elif index.anchor_allocation_binding is not None:
        binding = index.anchor_allocation_binding
        trusted_anchor = source.trusted_anchor_coordinate
        if trusted_anchor is not None:
            for value in trusted_anchor[:3]:
                _identifier(value)
        if (
            binding.source_namespace != index.source_namespace
            or not binding.anchor_authority
            or not binding.anchor_selector_incarnation
            or not binding.reservation_id
            or not binding.allocation_id
            or trusted_anchor is None
            or trusted_anchor[:2]
            != (binding.anchor_authority, binding.anchor_selector_incarnation)
        ):
            raise Reject()
    registered_incarnations: set[str] = set()
    for audience_key, authority in index.registered_root_authorities.items():
        root = authority.root
        producer_hierarchy = source.registered_root_authority_producer.hierarchies.get(
            audience_key
        )
        if (
            root.audience_key != audience_key
            or root.availability_profile is not index.availability_profile
            or not authority.observer_role_version
            or not authority.source_security_epoch
            or not _complete_digest_set(
                (
                    root.registered_root_hierarchy_digest,
                    root.source_enrollment_hierarchy_digest,
                )
            )
            or root.root_incarnation in registered_incarnations
            or producer_hierarchy is None
            or producer_hierarchy.fact.root != root
            or producer_hierarchy.fact.observer_role_version
            != authority.observer_role_version
            or producer_hierarchy.fact.source_security_epoch
            != authority.source_security_epoch
        ):
            raise Reject()
        registered_incarnations.add(root.root_incarnation)
    eligible_admissions: dict[tuple[str, str], EligibleRoot] = {}
    for audience_key, admission in index.root_admissions.items():
        hierarchy = admission.eligibility_hierarchy
        if hierarchy is None:
            root = index.eligible_roots.get(audience_key)
            if (
                admission.phase is not RootAdmissionPhase.ELIGIBLE
                or root is None
                or root.availability_profile is not SOURCE_ONLY
                or admission.anchor_notification_digest is not None
            ):
                raise Reject()
            eligible_admissions[audience_key] = root
            continue
        _validate_eligibility(hierarchy)
        root = hierarchy.eligibility.root
        registered_authority = index.registered_root_authorities.get(audience_key)
        if (
            root.audience_key != audience_key
            or hierarchy.eligibility.source_namespace != index.source_namespace
            or hierarchy.eligibility.source_index_incarnation
            != index.source_index_incarnation
            or registered_authority is None
            or registered_authority.root != root
        ):
            raise Reject()
        if admission.phase is RootAdmissionPhase.ELIGIBLE:
            if (
                admission.anchor_notification_digest is None
                or index.eligible_roots.get(audience_key) != root
            ):
                raise Reject()
            eligible_admissions[audience_key] = root
        elif (
            audience_key in index.eligible_roots
            or admission.anchor_notification_digest is not None
        ):
            raise Reject()
        if (
            index.phase is SourceIndexPhase.OPEN
            and admission.phase is RootAdmissionPhase.FROZEN_PENDING
        ):
            raise Reject()
        if (
            index.phase is SourceIndexPhase.FROZEN
            and admission.phase is RootAdmissionPhase.PENDING
        ):
            raise Reject()
    if eligible_admissions != index.eligible_roots:
        raise Reject()
    if not (
        set(index.eligible_roots)
        == set(index.enrollment_receipts)
        == set(index.enrollment_hierarchies)
    ):
        raise Reject()
    for audience_key, root in index.eligible_roots.items():
        enrollment_hierarchy = index.enrollment_hierarchies[audience_key]
        _validate_enrollment(enrollment_hierarchy)
        registered_hierarchy = (
            source.registered_root_authority_producer.hierarchies.get(audience_key)
        )
        registered_authority = index.registered_root_authorities[audience_key]
        admission = index.root_admissions[audience_key]
        expected_eligibility_digest = (
            None
            if admission.eligibility_hierarchy is None
            else _eligibility_digest(admission.eligibility_hierarchy)
        )
        if (
            enrollment_hierarchy.root != root
            or enrollment_hierarchy.source_namespace != index.source_namespace
            or enrollment_hierarchy.observer_role_version
            != registered_authority.observer_role_version
            or enrollment_hierarchy.source_security_epoch
            != registered_authority.source_security_epoch
            or registered_hierarchy is None
            or enrollment_hierarchy.registered_authority_hierarchy_digest
            != _object_digest(registered_hierarchy)
            or enrollment_hierarchy.eligibility_hierarchy_digest
            != expected_eligibility_digest
            or enrollment_hierarchy.anchor_notification_hierarchy_digest
            != admission.anchor_notification_digest
            or enrollment_hierarchy.enrollment_receipt_digest
            != index.enrollment_receipts[audience_key]
        ):
            raise Reject()
    root_incarnations = [
        (
            admission.eligibility_hierarchy.eligibility.root.root_incarnation
            if admission.eligibility_hierarchy is not None
            else index.eligible_roots[audience_key].root_incarnation
        )
        for audience_key, admission in index.root_admissions.items()
    ]
    if len(root_incarnations) != len(set(root_incarnations)):
        raise Reject()
    if len(index.entries) > index.entry_capacity:
        raise Reject()
    if len(generations.slots) > generations.slot_capacity:
        raise Reject()
    if len(source.queue.records) > source.queue.record_capacity:
        raise Reject()

    issued_slots: dict[tuple[str, str], SourceIndexEntry] = {}
    canceled_keys: set[StableKey] = set()
    for key, entry in index.entries.items():
        if key.source_namespace != index.source_namespace:
            raise Reject()
        if entry.stable_key != key:
            raise Reject()
        if entry.plant_profile_digest != index.plant_profile_digest:
            raise Reject()
        source_entry_bytes(entry)
        if entry.kind is IndexEntryKind.CANCELED_BEFORE_ISSUANCE:
            canceled_keys.add(key)
            continue
        if entry.source_generation is None or entry.slot_id is None:
            raise Reject()
        slot_key = (entry.source_generation, entry.slot_id)
        if slot_key in issued_slots:
            raise Reject()
        issued_slots[slot_key] = entry

    if canceled_keys != set(generations.absent_intent_tombstones):
        raise Reject()
    if set(issued_slots) != set(generations.slots):
        raise Reject()
    if set(issued_slots) != set(generations.private_challenges):
        raise Reject()
    issued_keys = {entry.stable_key for entry in issued_slots.values()}
    if issued_keys != set(index.issuance_hierarchies):
        raise Reject()
    for key in issued_keys:
        hierarchy = index.issuance_hierarchies[key]
        _validate_publication(hierarchy, expected_credential=source.producer_credential)
        entry = index.entries[key]
        root = _incarnation_root(index.eligible_roots, key.observer_root_incarnation)
        enrollment_hierarchy = index.enrollment_hierarchies[root.audience_key]
        slot_key = (entry.source_generation or "", entry.slot_id or "")
        material = generations.private_challenges[slot_key]
        if (
            hierarchy.source_entry != entry
            or hierarchy.source_authority_id != source.source_authority_id
            or hierarchy.source_index_incarnation != index.source_index_incarnation
            or hierarchy.source_enrollment_hierarchy_digest
            != _object_digest(enrollment_hierarchy)
            or hierarchy.transport_verification_digest
            != material.transport_context.verification_digest
            or hierarchy.source_capsule_digest
            != hashlib.sha256(material.source_observer_capsule).hexdigest()
            or hierarchy.source_producer_coordinate
            != material.source_producer_coordinate
        ):
            raise Reject()

    admission_keys: dict[str, tuple[str, str]] = {}
    referenced_grants: set[str] = set()
    for slot_key, slot in generations.slots.items():
        entry = issued_slots[slot_key]
        material = generations.private_challenges[slot_key]
        if (
            slot.stable_key != entry.stable_key
            or material.stable_key != entry.stable_key
            or slot.challenge_commitment != entry.challenge_commitment
            or material.challenge_commitment != entry.challenge_commitment
            or slot.paired_frame_admission_key != entry.paired_frame_admission_key
            or material.paired_frame_admission_key != entry.paired_frame_admission_key
            or slot.live_session_epoch != index.live_session_epoch
            or slot.authority_lease_not_after != index.authority_lease_not_after
            or not 0 < slot.acceptance_not_after <= index.acceptance_not_after
            or (
                index.availability_profile is SOURCE_ONLY
                and slot.acceptance_not_after != index.acceptance_not_after
            )
            or slot.source_security_epoch != index.source_security_epoch
            or slot.plant_profile_digest != index.plant_profile_digest
            or not material.source_producer_coordinate
            or material.transport_context.authenticated_principal
            != slot.stable_key.requester_principal
            or material.transport_context.verification_digest
            != _transport_digest(material.transport_context)
            or (
                source.transport_authority.contexts.get(
                    material.transport_context.verification_digest
                )
                or source.transport_authority.retired_contexts.get(
                    material.transport_context.verification_digest
                )
            )
            != material.transport_context
        ):
            raise Reject()
        eligible = _incarnation_root(
            index.eligible_roots, slot.stable_key.observer_root_incarnation
        )
        if eligible.availability_profile is not index.availability_profile:
            raise Reject()

        if slot.state is SlotState.AVAILABLE:
            if (
                slot.accepted_grant_id is not None
                or slot.expiry_clock_sample is not None
            ):
                raise Reject()
            if index.availability_profile is SOURCE_ONLY:
                if (
                    slot.delivery_gate is not DeliveryGate.DIRECT_DELIVERY_READY
                    or slot.paired_frame_admission_key is not None
                ):
                    raise Reject()
            elif slot.delivery_gate not in {
                DeliveryGate.ANCHOR_PAIRED_FRAME_PENDING,
                DeliveryGate.ANCHOR_PAIRED_FRAME_ADMITTED,
            }:
                raise Reject()
        elif slot.delivery_gate is not DeliveryGate.DELIVERY_TERMINAL:
            raise Reject()
        if slot.state is SlotState.EXPIRED_UNUSED:
            if slot.expiry_clock_sample is None:
                raise Reject()
            _validate_sample(slot.expiry_clock_sample)
            if (
                slot.expiry_clock_sample.clock_id != index.source_clock_id
                or slot.expiry_clock_sample.clock_epoch != index.source_clock_epoch
                or slot.expiry_clock_sample.lower < slot.acceptance_not_after
            ):
                raise Reject()
        elif slot.expiry_clock_sample is not None:
            raise Reject()

        admission_key = slot.paired_frame_admission_key
        if admission_key is not None:
            if admission_key in admission_keys:
                raise Reject()
            admission_keys[admission_key] = slot_key
        if slot.delivery_gate is DeliveryGate.ANCHOR_PAIRED_FRAME_PENDING:
            if admission_key in source.queue.records:
                raise Reject()
        if slot.delivery_gate is DeliveryGate.ANCHOR_PAIRED_FRAME_ADMITTED:
            record = source.queue.records.get(admission_key or "")
            if (
                record is None
                or record.stable_key != slot.stable_key
                or record.state is QueueRecordState.TERMINALIZED
            ):
                raise Reject()
        if slot.state is SlotState.CONSUMED_BY_ACCEPTED_REQUEST:
            grant = generations.accepted_grants.get(slot.accepted_grant_id or "")
            closure_hierarchy = generations.closure_evidence_hierarchies.get(
                slot.accepted_grant_id or ""
            )
            if (
                grant is None
                or grant.stable_key != slot.stable_key
                or grant.live_session_epoch != slot.live_session_epoch
                or grant.authority_lease_not_after != slot.authority_lease_not_after
                or grant.acceptance_not_after != slot.acceptance_not_after
                or grant.source_security_epoch != slot.source_security_epoch
                or grant.plant_profile_digest != slot.plant_profile_digest
                or grant.acceptance_transport_verification_digest
                != material.transport_context.verification_digest
                or grant.closure_plan_id != "closure-plan:" + grant.grant_id
                or grant.closure_plan_digest
                != _grant_plan_digest(
                    source.source_authority_id, index.source_index_incarnation, grant
                )
                or not _complete_digest_set(
                    (
                        grant.acceptance_transport_verification_digest,
                        grant.acceptance_receipt_digest,
                        grant.closure_plan_digest,
                    )
                )
                or grant.predecessor_grant_id is not None
                or (
                    grant.closure_receipt is not None
                    and (
                        closure_hierarchy is None
                        or grant.closure_receipt
                        != _grant_closure_receipt(source, grant, closure_hierarchy)
                    )
                )
            ):
                raise Reject()
            if closure_hierarchy is not None:
                _validate_grant_closure(
                    closure_hierarchy,
                    expected_credential=source.producer_credential,
                    expected_distributed_credential=(
                        source.trusted_distributed_closure_authority_credential
                    ),
                )
                external = closure_hierarchy.fact.distributed_closure.fact
                if (
                    external.authority_id
                    != source.trusted_distributed_closure_authority_id
                    or external.authority_security_epoch
                    != source.trusted_distributed_closure_security_epoch
                    or _distributed_binding(external)
                    != _expected_distributed_binding(source, grant)
                ):
                    raise Reject()
            referenced_grants.add(grant.grant_id)
        elif slot.accepted_grant_id is not None:
            raise Reject()

    if referenced_grants != set(generations.accepted_grants):
        raise Reject()
    if not set(generations.closure_evidence_hierarchies).issubset(referenced_grants):
        raise Reject()
    targets = [
        grant.stable_key.logical_target_key
        for grant in generations.accepted_grants.values()
    ]
    if len(targets) != len(set(targets)):
        raise Reject()

    for admission_key, record in source.queue.records.items():
        slot_key = admission_keys.get(admission_key)
        if slot_key is None:
            raise Reject()
        slot = generations.slots[slot_key]
        root = _incarnation_root(
            index.eligible_roots, slot.stable_key.observer_root_incarnation
        )
        admission = index.root_admissions[root.audience_key]
        if admission.eligibility_hierarchy is None:
            raise Reject()
        expected_relation = (
            admission.eligibility_hierarchy.eligibility.qualified_clock_relation
        )
        binding = record.opaque_relay_binding
        binding_digests = (
            binding.observer_envelope_bytes_digest,
            binding.observer_envelope_authentication_set_digest,
        )
        if (
            record.admission_key != admission_key
            or record.stable_key != slot.stable_key
            or not binding.observer_envelope_identity
            or binding.producer_coordinate != "anchor-producer:" + admission_key
            or record.mapped_acceptance_cutoff <= 0
            or record.clock_relation_id != expected_relation.relation_id
            or record.clock_relation_digest != expected_relation.semantic_digest
            or not record.anchor_clock_id
            or not record.anchor_clock_epoch
            or any(
                len(digest) != 64
                or any(character not in "0123456789abcdef" for character in digest)
                for digest in (*binding_digests, record.clock_relation_digest)
            )
            or (
                record.handoff_receipt_digest is not None
                and (
                    source.transport_authority.handoff_receipts.get(admission_key)
                    is None
                    or source.transport_authority.handoff_receipts[
                        admission_key
                    ].receipt_digest
                    != record.handoff_receipt_digest
                )
            )
        ):
            raise Reject()
        if hashlib.sha256(record.frame_bytes).hexdigest() != record.frame_digest:
            raise Reject()
        frame, challenge, source_capsule, anchor_capsule = _parse_requester_frame(
            record.frame_bytes
        )
        if (
            frame["stable_key_digest"] != stable_key_digest(slot.stable_key).hex()
            or frame["paired_frame_admission_key"] != admission_key
            or frame["requester_connection"] != record.requester_connection
            or frame["authenticated_principal"]
            != record.transport_context.authenticated_principal
            or frame["replay_domain"] != record.replay_domain
            or frame["transport_security_epoch"]
            != record.transport_context.transport_security_epoch
            or frame["transport_verification_digest"]
            != record.transport_context.verification_digest
            or frame["plant_profile_digest"] != index.plant_profile_digest
            or record.transport_context.authenticated_principal
            != record.stable_key.requester_principal
            or record.transport_context.verification_digest
            != _transport_digest(record.transport_context)
            or frame["source_producer_coordinate"]
            != generations.private_challenges[slot_key].source_producer_coordinate
            or frame["anchor_producer_coordinate"]
            != record.opaque_relay_binding.producer_coordinate
            or hashlib.sha256(challenge).hexdigest() != slot.challenge_commitment
            or hashlib.sha256(source_capsule).hexdigest()
            != record.source_capsule_digest
            or hashlib.sha256(anchor_capsule).hexdigest()
            != record.anchor_capsule_digest
        ):
            raise Reject()
        if slot.delivery_gate is DeliveryGate.ANCHOR_PAIRED_FRAME_ADMITTED:
            if record.state is QueueRecordState.TERMINALIZED:
                raise Reject()
        elif slot.delivery_gate is DeliveryGate.DELIVERY_TERMINAL:
            if record.state is not QueueRecordState.TERMINALIZED:
                raise Reject()
        else:
            raise Reject()

    if index.phase is SourceIndexPhase.OPEN:
        if (
            index.frozen_root is not None
            or index.frozen_audience
            or source.closure_hierarchy is not None
            or source.cooperative_retirement_hierarchy is not None
        ):
            raise Reject()
    else:
        if index.frozen_root is None:
            raise Reject()
        if index.frozen_audience != tuple(sorted(index.eligible_roots)):
            raise Reject()
        for slot in generations.slots.values():
            if slot.state is SlotState.AVAILABLE:
                raise Reject()
            if slot.state is SlotState.CONSUMED_BY_ACCEPTED_REQUEST:
                grant = generations.accepted_grants[slot.accepted_grant_id or ""]
                if grant.closure_receipt is None:
                    raise Reject()
        if any(
            record.state is not QueueRecordState.TERMINALIZED
            for record in source.queue.records.values()
        ):
            raise Reject()
        retained_tree = SparseMerkleTree(
            ProofContext.SOURCE,
            {key: source_entry_bytes(entry) for key, entry in index.entries.items()},
        )
        if retained_tree.root != index.frozen_root:
            raise Reject()
        closure_hierarchy = source.closure_hierarchy
        if closure_hierarchy is None:
            raise Reject()
        _validate_closure(
            closure_hierarchy, expected_credential=source.producer_credential
        )
        expected_ancestry_digest = _object_digest(
            tuple(
                sorted(
                    (audience_key, _object_digest(hierarchy))
                    for audience_key, hierarchy in (
                        index.enrollment_hierarchies.items()
                    )
                )
            )
        )
        if (
            closure_hierarchy.bundle
            != ClosureBundle(
                source_namespace=index.source_namespace,
                availability_profile=index.availability_profile,
                context=ProofContext.SOURCE,
                root=index.frozen_root,
                audience=index.frozen_audience,
                origin=ClosureOrigin.SOURCE,
            )
            or closure_hierarchy.producer_authority_id != source.source_authority_id
            or closure_hierarchy.producer_security_epoch != index.source_security_epoch
            or closure_hierarchy.enrollment_ancestry_digest != expected_ancestry_digest
        ):
            raise Reject()
        cooperative_hierarchy = source.cooperative_retirement_hierarchy
        if cooperative_hierarchy is not None:
            _validate_retirement(
                cooperative_hierarchy,
                expected_source_credential=source.producer_credential,
                expected_lineage_credential=source.trusted_lineage_authority_credential,
            )
            if (
                index.availability_profile is not ANCHOR_PROFILE
                or cooperative_hierarchy.projection.frozen_source_index_root
                != index.frozen_root
                or cooperative_hierarchy.source_closure_hierarchy_digest
                != _object_digest(closure_hierarchy)
                or cooperative_hierarchy.closure_audience != index.frozen_audience
                or cooperative_hierarchy.source_authority_id
                != source.source_authority_id
                or cooperative_hierarchy.source_index_incarnation
                != index.source_index_incarnation
                or cooperative_hierarchy.source_security_epoch
                != index.source_security_epoch
            ):
                raise Reject()


def new_source(
    namespace: tuple[str, str, str],
    profile: Availability,
    *,
    eligible_capacity: int = MAX_ELIGIBLE_ROOTS,
    entry_capacity: int = MAX_ISSUANCE_ENTRIES,
    slot_capacity: int = MAX_GENERATION_SLOTS,
    plant_profile_hierarchy: ProtectedPlantProfile | None = None,
) -> Source:
    _closed_member(profile, Availability)
    source = Source(
        index=SourceIssuanceIndexStore(
            source_namespace=namespace,
            availability_profile=profile,
            eligible_capacity=eligible_capacity,
            entry_capacity=entry_capacity,
            plant_profile_digest=(
                None
                if plant_profile_hierarchy is None
                else plant_profile_hierarchy.plant_profile_digest
            ),
        ),
        installed_plant_profile_hierarchy=plant_profile_hierarchy,
        generations=GenerationSlotStore(slot_capacity=slot_capacity),
    )
    _validate_source(source)
    return source


def source_import_current_registered_root_authority(
    source: Source, hierarchy: ProtectedRootAuthority
) -> None:
    def mutate(candidate: Source) -> None:
        index = candidate.index
        _validate_root_authority(hierarchy)
        fact = hierarchy.fact
        root = fact.root
        if (
            index.phase is not SourceIndexPhase.OPEN
            or root.availability_profile is not index.availability_profile
            or candidate.registered_root_authority_producer.hierarchies.get(
                root.audience_key
            )
            != hierarchy
            or fact.observer_role_version != index.observer_role_version
            or fact.source_security_epoch != index.source_security_epoch
            or not _complete_digest_set(
                (
                    root.registered_root_hierarchy_digest,
                    root.source_enrollment_hierarchy_digest,
                )
            )
        ):
            raise Reject()
        authority = CurrentRegisteredObserverRootAuthority(
            root=root,
            observer_role_version=fact.observer_role_version,
            source_security_epoch=fact.source_security_epoch,
            state=RootAuthorityState.ACTIVE,
        )
        prior = index.registered_root_authorities.get(root.audience_key)
        if prior is not None:
            if prior != authority:
                raise Reject()
            return
        if len(index.registered_root_authorities) >= index.eligible_capacity:
            raise Reject()
        if any(
            entry.root.root_incarnation == root.root_incarnation
            for entry in index.registered_root_authorities.values()
        ):
            raise Reject()
        index.registered_root_authorities[root.audience_key] = authority

    _atomic(source, mutate, _validate_source)


def source_begin_registered_root_retirement(
    source: Source, root_audience_key: tuple[str, str]
) -> None:
    def mutate(candidate: Source) -> None:
        index = candidate.index
        authority = index.registered_root_authorities.get(root_audience_key)
        if index.phase is not SourceIndexPhase.OPEN or authority is None:
            raise Reject()
        if authority.state is RootAuthorityState.RETIREMENT_PENDING:
            return
        if authority.state is not RootAuthorityState.ACTIVE:
            raise Reject()
        index.registered_root_authorities[root_audience_key] = replace(
            authority, state=RootAuthorityState.RETIREMENT_PENDING
        )

    _atomic(source, mutate, _validate_source)


def source_complete_registered_root_retirement(
    source: Source, root_audience_key: tuple[str, str]
) -> None:
    def mutate(candidate: Source) -> None:
        index = candidate.index
        authority = index.registered_root_authorities.get(root_audience_key)
        if index.phase is not SourceIndexPhase.OPEN or authority is None:
            raise Reject()
        if authority.state is RootAuthorityState.RETIRED:
            return
        if authority.state is not RootAuthorityState.RETIREMENT_PENDING:
            raise Reject()
        index.registered_root_authorities[root_audience_key] = replace(
            authority, state=RootAuthorityState.RETIRED
        )

    _atomic(source, mutate, _validate_source)


def source_bind_anchor(
    source: Source, anchor: Anchor, allocation: NamespaceAllocation
) -> None:
    def mutate(candidate: Source) -> None:
        index = candidate.index
        _require_allocation(allocation)
        coordinate = (
            anchor.anchor_authority,
            anchor.anchor_selector_incarnation,
            anchor.anchor_security_epoch,
            anchor.producer_credential,
        )
        binding = SourceAnchorAllocationBinding(
            source_namespace=allocation.source_namespace,
            anchor_authority=allocation.anchor_authority,
            anchor_selector_incarnation=allocation.anchor_selector_incarnation,
            reservation_id=allocation.anchor_reservation.reservation_id,
            allocation_id=allocation.allocation_id,
        )
        if (
            index.phase is not SourceIndexPhase.OPEN
            or index.availability_profile is not ANCHOR_PROFILE
            or allocation.source_namespace != index.source_namespace
            or coordinate[:2]
            != (allocation.anchor_authority, allocation.anchor_selector_incarnation)
        ):
            raise Reject()
        if index.anchor_allocation_binding is not None:
            if (
                index.anchor_allocation_binding != binding
                or candidate.trusted_anchor_coordinate != coordinate
            ):
                raise Reject()
            return
        if index.root_admissions or index.eligible_roots or index.entries:
            raise Reject()
        index.anchor_allocation_binding = binding
        candidate.trusted_anchor_coordinate = coordinate

    _atomic(source, mutate, _validate_source)


def source_publish_anchor_enrollment_eligibility(
    source: Source,
    root: EligibleRoot,
    *,
    exclusive_anchor_cutoff: int,
    source_clock_sample: BoundedClockSample,
    clock_relation: ClockRelation,
) -> ProtectedEligibility:
    def mutate(candidate: Source) -> ProtectedEligibility:
        index = candidate.index
        registered_authority = index.registered_root_authorities.get(root.audience_key)
        anchor_binding = index.anchor_allocation_binding
        if (
            index.phase is not SourceIndexPhase.OPEN
            or index.availability_profile is not ANCHOR_PROFILE
            or root.availability_profile is not index.availability_profile
            or root.anchor_enrollment_entry_digest is None
            or registered_authority is None
            or registered_authority.root != root
            or registered_authority.state is not RootAuthorityState.ACTIVE
            or registered_authority.observer_role_version != index.observer_role_version
            or registered_authority.source_security_epoch != index.source_security_epoch
            or anchor_binding is None
        ):
            raise Reject()
        _validate_clock(clock_relation)
        _, conservative_anchor_upper = _clock_images(
            source_clock_sample, clock_relation
        )
        if (
            clock_relation.source_clock_id != index.source_clock_id
            or clock_relation.source_clock_epoch != index.source_clock_epoch
            or clock_relation.relation_id == ""
            or conservative_anchor_upper >= exclusive_anchor_cutoff
        ):
            raise Reject()
        eligibility = ObserverRootEnrollmentEligibility(
            source_namespace=index.source_namespace,
            root=root,
            anchor_authority=anchor_binding.anchor_authority,
            source_index_incarnation=index.source_index_incarnation,
            anchor_entry_key="anchor-root-entry:" + root.root_incarnation,
            exclusive_anchor_cutoff=exclusive_anchor_cutoff,
            source_security_epoch=index.source_security_epoch,
            observer_role_version=index.observer_role_version,
            qualified_clock_relation=clock_relation,
        )
        (
            envelope_digest,
            family_manifest_digest,
            pre_manifest_digest,
            producer_completion_digest,
            delivery_capsule_digest,
            audience_proof_digest,
            manifest_proof_digest,
            delivery_verification_digest,
        ) = _protection_digests("observer-root-enrollment-eligibility", eligibility)
        hierarchy = ProtectedEligibility(
            eligibility=eligibility,
            audience_purpose="OBSERVER_ROOT_ENROLLMENT_ELIGIBILITY",
            verification_class="EPHEMERAL_AUTHORITY_WINDOW",
            envelope_digest=envelope_digest,
            family_manifest_digest=family_manifest_digest,
            pre_manifest_digest=pre_manifest_digest,
            producer_completion_digest=producer_completion_digest,
            delivery_capsule_digest=delivery_capsule_digest,
            audience_proof_digest=audience_proof_digest,
            manifest_proof_digest=manifest_proof_digest,
            delivery_verification_digest=delivery_verification_digest,
        )
        _validate_eligibility(hierarchy)
        prior = index.root_admissions.get(root.audience_key)
        if prior is not None:
            if prior.eligibility_hierarchy != hierarchy:
                raise Reject()
            return hierarchy
        if len(index.root_admissions) >= index.eligible_capacity:
            raise Reject()
        if any(
            admission.eligibility_hierarchy is not None
            and admission.eligibility_hierarchy.eligibility.root.root_incarnation
            == root.root_incarnation
            for admission in index.root_admissions.values()
        ):
            raise Reject()
        index.root_admissions[root.audience_key] = SourceRootAdmissionEntry(
            eligibility_hierarchy=hierarchy, phase=RootAdmissionPhase.PENDING
        )
        return hierarchy

    result = _atomic(source, mutate, _validate_source)
    return _require_result_type(result, ProtectedEligibility)


def source_cancel_anchor_enrollment_eligibility_after_cutoff(
    source: Source,
    root_audience_key: tuple[str, str],
    *,
    source_clock_sample: BoundedClockSample,
    clock_relation: ClockRelation,
) -> None:
    def mutate(candidate: Source) -> None:
        index = candidate.index
        if index.phase is not SourceIndexPhase.OPEN:
            raise Reject()
        admission = index.root_admissions.get(root_audience_key)
        if (
            admission is None
            or admission.phase is not RootAdmissionPhase.PENDING
            or admission.eligibility_hierarchy is None
        ):
            raise Reject()
        eligibility = admission.eligibility_hierarchy.eligibility
        conservative_anchor_lower, _ = _clock_images(
            source_clock_sample, clock_relation
        )
        if (
            clock_relation != eligibility.qualified_clock_relation
            or conservative_anchor_lower < eligibility.exclusive_anchor_cutoff
        ):
            raise Reject()
        admission.phase = RootAdmissionPhase.CANCELED

    _atomic(source, mutate, _validate_source)


def source_enroll_root(
    source: Source,
    root: EligibleRoot,
    *,
    anchor: Anchor | None = None,
    anchor_notification: (ProtectedNotification | None) = None,
    source_clock_sample: BoundedClockSample | None = None,
    clock_relation: ClockRelation | None = None,
) -> ProtectedEnrollment:
    def mutate(candidate: Source) -> ProtectedEnrollment:
        index = candidate.index
        if index.phase is not SourceIndexPhase.OPEN:
            raise Reject()
        if root.availability_profile is not index.availability_profile:
            raise Reject()
        registered_authority = index.registered_root_authorities.get(root.audience_key)
        if (
            registered_authority is None
            or registered_authority.root != root
            or registered_authority.state is not RootAuthorityState.ACTIVE
            or registered_authority.observer_role_version != index.observer_role_version
            or registered_authority.source_security_epoch != index.source_security_epoch
        ):
            raise Reject()
        if index.availability_profile is SOURCE_ONLY:
            if (
                root.anchor_enrollment_entry_digest is not None
                or anchor is not None
                or anchor_notification is not None
                or source_clock_sample is not None
                or clock_relation is not None
            ):
                raise Reject()
        else:
            admission = index.root_admissions.get(root.audience_key)
            if (
                root.anchor_enrollment_entry_digest is None
                or anchor is None
                or admission is None
                or admission.phase
                not in {RootAdmissionPhase.PENDING, RootAdmissionPhase.ELIGIBLE}
                or admission.eligibility_hierarchy is None
                or anchor_notification is None
                or source_clock_sample is None
                or clock_relation is None
            ):
                raise Reject()
            _validate_notification(anchor_notification)
            eligibility = admission.eligibility_hierarchy.eligibility
            _, conservative_anchor_upper = _clock_images(
                source_clock_sample, clock_relation
            )
            if (
                anchor_notification.eligibility_hierarchy_digest
                != _eligibility_digest(admission.eligibility_hierarchy)
                or anchor.enrollment_notifications.get(root.audience_key)
                != anchor_notification
                or anchor.enrollment_eligibility_hierarchies.get(root.audience_key)
                != admission.eligibility_hierarchy
                or anchor_notification.anchor_entry_digest
                != root.anchor_enrollment_entry_digest
                or anchor_notification.source_namespace != index.source_namespace
                or anchor_notification.root_audience_key != root.audience_key
                or anchor_notification.anchor_authority != eligibility.anchor_authority
                or anchor_notification.exclusive_anchor_cutoff
                != eligibility.exclusive_anchor_cutoff
                or clock_relation != eligibility.qualified_clock_relation
                or index.source_security_epoch != eligibility.source_security_epoch
                or index.observer_role_version != eligibility.observer_role_version
                or conservative_anchor_upper >= eligibility.exclusive_anchor_cutoff
            ):
                raise Reject()
        registered_hierarchy = (
            candidate.registered_root_authority_producer.hierarchies.get(
                root.audience_key
            )
        )
        if registered_hierarchy is None:
            raise Reject()
        registered_digest = _object_digest(registered_hierarchy)
        eligibility_digest = (
            None
            if index.availability_profile is SOURCE_ONLY
            else _eligibility_digest(admission.eligibility_hierarchy)
        )
        notification_digest = (
            None
            if anchor_notification is None
            else _notification_digest(anchor_notification)
        )
        enrollment_semantic_value = (
            index.source_namespace,
            root,
            registered_digest,
            eligibility_digest,
            notification_digest,
            index.observer_role_version,
            index.source_security_epoch,
        )
        enrollment_receipt_digest = _fixture_digest(
            "source-observer-root-enrollment-receipt|" + repr(enrollment_semantic_value)
        )
        enrollment_hierarchy = ProtectedEnrollment(
            source_namespace=index.source_namespace,
            root=root,
            registered_authority_hierarchy_digest=registered_digest,
            eligibility_hierarchy_digest=eligibility_digest,
            anchor_notification_hierarchy_digest=notification_digest,
            observer_role_version=index.observer_role_version,
            source_security_epoch=index.source_security_epoch,
            enrollment_receipt_digest=enrollment_receipt_digest,
            protection=_protect(
                "source-observer-root-enrollment",
                enrollment_semantic_value + (enrollment_receipt_digest,),
                audience_purpose="OBSERVER_ROOT_SOURCE_ENROLLMENT",
                verification_class="DURABLE_SOURCE_AUTHORITY_COMMIT",
            ),
        )
        prior = index.eligible_roots.get(root.audience_key)
        if prior is not None:
            if (
                prior != root
                or index.enrollment_hierarchies.get(root.audience_key)
                != enrollment_hierarchy
                or index.enrollment_receipts.get(root.audience_key)
                != enrollment_receipt_digest
            ):
                raise Reject()
            return enrollment_hierarchy
        if len(index.eligible_roots) >= index.eligible_capacity:
            raise Reject()
        if any(
            enrolled.root_incarnation == root.root_incarnation
            for enrolled in index.eligible_roots.values()
        ):
            raise Reject()
        index.eligible_roots[root.audience_key] = root
        if index.availability_profile is SOURCE_ONLY:
            index.root_admissions[root.audience_key] = SourceRootAdmissionEntry(
                eligibility_hierarchy=None, phase=RootAdmissionPhase.ELIGIBLE
            )
        else:
            admission.phase = RootAdmissionPhase.ELIGIBLE
            admission.anchor_notification_digest = _notification_digest(
                anchor_notification
            )
        index.enrollment_receipts[root.audience_key] = enrollment_receipt_digest
        index.enrollment_hierarchies[root.audience_key] = enrollment_hierarchy
        return enrollment_hierarchy

    result = _atomic(source, mutate, _validate_source)
    return _require_result_type(result, ProtectedEnrollment)


def _key_root(source: Source, key: StableKey) -> EligibleRoot:
    root = _incarnation_root(source.index.eligible_roots, key.observer_root_incarnation)
    if root.availability_profile is not source.index.availability_profile:
        raise Reject()
    return root


def _require_current_root(source: Source, key: StableKey) -> EligibleRoot:
    root = _key_root(source, key)
    authority = source.index.registered_root_authorities.get(root.audience_key)
    if (
        authority is None
        or authority.root != root
        or authority.state is not RootAuthorityState.ACTIVE
        or authority.observer_role_version != source.index.observer_role_version
        or authority.source_security_epoch != source.index.source_security_epoch
    ):
        raise Reject()
    return root


def source_issue(
    source: Source,
    key: StableKey,
    *,
    transport_context: TransportContext,
    source_generation: str,
    slot_id: str,
    challenge_bytes: bytes,
    source_observer_capsule: bytes,
    source_producer_coordinate: str,
    paired_frame_admission_key: str | None,
) -> SourceIndexEntry:
    def mutate(candidate: Source) -> SourceIndexEntry:
        index = candidate.index
        generations = candidate.generations
        _validate_stable_key(key)
        if index.phase is not SourceIndexPhase.OPEN:
            raise Reject()
        if key.source_namespace != index.source_namespace:
            raise Reject()
        _identifier(source_generation)
        _identifier(slot_id)
        _identifier(source_producer_coordinate)
        _require_current_root(candidate, key)
        if (
            candidate.transport_authority.contexts.get(
                transport_context.verification_digest
            )
            != transport_context
            or candidate.transport_authority.channel_states.get(
                transport_context.verification_digest
            )
            is not TransportState.ACTIVE
            or transport_context.transport_security_epoch
            != candidate.transport_authority.security_epoch
            or transport_context.producer_capability
            is not candidate.transport_authority.producer_capability
            or transport_context.authenticated_principal != key.requester_principal
        ):
            raise Reject()
        prior_entry = index.entries.get(key)
        if prior_entry is not None:
            if prior_entry.kind is not IndexEntryKind.CHALLENGE_ISSUED:
                raise Reject()
            prior_slot_key = (
                prior_entry.source_generation or "",
                prior_entry.slot_id or "",
            )
            prior_material = generations.private_challenges.get(prior_slot_key)
            if (
                prior_entry.source_generation != source_generation
                or prior_entry.slot_id != slot_id
                or prior_entry.paired_frame_admission_key != paired_frame_admission_key
                or prior_material is None
                or prior_material.challenge_bytes != challenge_bytes
                or prior_material.source_observer_capsule != source_observer_capsule
                or prior_material.source_producer_coordinate
                != source_producer_coordinate
                or prior_material.transport_context != transport_context
            ):
                raise Reject()
            return prior_entry
        if len(index.entries) >= index.entry_capacity:
            raise Reject()
        slot_key = (source_generation, slot_id)
        if slot_key in generations.slots:
            raise Reject()
        if len(generations.slots) >= generations.slot_capacity:
            raise Reject()
        if (
            not challenge_bytes
            or len(challenge_bytes) > MAX_CHALLENGE_BYTES
            or not source_observer_capsule
            or len(source_observer_capsule) > MAX_CAPSULE_BYTES
        ):
            raise Reject()
        if not source_producer_coordinate:
            raise Reject()
        if index.availability_profile is SOURCE_ONLY:
            if paired_frame_admission_key is not None:
                raise Reject()
            gate = DeliveryGate.DIRECT_DELIVERY_READY
            fixed_acceptance_not_after = index.acceptance_not_after
        else:
            if not paired_frame_admission_key:
                raise Reject()
            _identifier(paired_frame_admission_key)
            if paired_frame_admission_key in candidate.queue.records:
                raise Reject()
            gate = DeliveryGate.ANCHOR_PAIRED_FRAME_PENDING
            enrolled_root = _key_root(candidate, key)
            eligibility = index.root_admissions[
                enrolled_root.audience_key
            ].eligibility_hierarchy
            if eligibility is None:
                raise Reject()
            fixed_acceptance_not_after = min(
                index.acceptance_not_after,
                _checked_clock_add(
                    eligibility.eligibility.exclusive_anchor_cutoff,
                    -eligibility.eligibility.qualified_clock_relation.anchor_minus_source_upper,
                ),
            )
            if fixed_acceptance_not_after <= 0:
                raise Reject()
        previous_tree = SparseMerkleTree(
            ProofContext.SOURCE,
            {
                retained_key: source_entry_bytes(retained_entry)
                for retained_key, retained_entry in index.entries.items()
            },
        )
        material = PrivateChallengeMaterial(
            stable_key=key,
            challenge_bytes=challenge_bytes,
            source_observer_capsule=source_observer_capsule,
            source_producer_coordinate=source_producer_coordinate,
            transport_context=transport_context,
            paired_frame_admission_key=paired_frame_admission_key,
        )
        entry = SourceIndexEntry(
            stable_key=key,
            kind=IndexEntryKind.CHALLENGE_ISSUED,
            source_generation=source_generation,
            slot_id=slot_id,
            challenge_commitment=material.challenge_commitment,
            paired_frame_admission_key=paired_frame_admission_key,
            plant_profile_digest=index.plant_profile_digest,
        )
        index.entries[key] = entry
        generations.slots[slot_key] = FreshnessSlot(
            stable_key=key,
            source_generation=source_generation,
            slot_id=slot_id,
            challenge_commitment=material.challenge_commitment,
            state=SlotState.AVAILABLE,
            delivery_gate=gate,
            paired_frame_admission_key=paired_frame_admission_key,
            live_session_epoch=index.live_session_epoch,
            authority_lease_not_after=index.authority_lease_not_after,
            acceptance_not_after=fixed_acceptance_not_after,
            source_security_epoch=index.source_security_epoch,
            plant_profile_digest=index.plant_profile_digest,
        )
        generations.private_challenges[slot_key] = material
        committed_tree = SparseMerkleTree(
            ProofContext.SOURCE,
            {
                retained_key: source_entry_bytes(retained_entry)
                for retained_key, retained_entry in index.entries.items()
            },
        )
        enrollment_hierarchy = index.enrollment_hierarchies[
            _key_root(candidate, key).audience_key
        ]
        source_commit_receipt_digest = _fixture_digest(
            "source-index-commit|"
            + repr(
                (
                    candidate.source_authority_id,
                    index.source_index_incarnation,
                    entry,
                    previous_tree.root,
                    committed_tree.root,
                )
            )
        )
        membership_proof = committed_tree.proof(key, ProofKind.MEMBERSHIP)
        source_retention_receipt_digest = _fixture_digest(
            "source-index-retention|"
            + source_commit_receipt_digest
            + "|"
            + hashlib.sha256(membership_proof).hexdigest()
        )
        provisional_hierarchy = ProtectedSourceChallengePublicationHierarchy(
            source_entry=entry,
            source_authority_id=candidate.source_authority_id,
            source_index_incarnation=index.source_index_incarnation,
            source_enrollment_hierarchy_digest=_object_digest(enrollment_hierarchy),
            transport_verification_digest=(transport_context.verification_digest),
            source_capsule_digest=hashlib.sha256(source_observer_capsule).hexdigest(),
            source_producer_coordinate=source_producer_coordinate,
            previous_source_root=previous_tree.root,
            committed_source_root=committed_tree.root,
            membership_proof=membership_proof,
            source_commit_receipt_digest=source_commit_receipt_digest,
            source_retention_receipt_digest=source_retention_receipt_digest,
            producer_credential=candidate.producer_credential,
            protection=EMPTY_PROTECTION,
        )
        hierarchy = replace(
            provisional_hierarchy,
            protection=_protect(
                "source-challenge-publication",
                _publication_value(provisional_hierarchy),
                audience_purpose=("REGISTERED_OBSERVER_ROOT_PRIVATE_CHALLENGE"),
                verification_class="DURABLE_SOURCE_INDEX_COMMIT",
            ),
        )
        _validate_publication(
            hierarchy, expected_credential=candidate.producer_credential
        )
        index.issuance_hierarchies[key] = hierarchy
        return entry

    result = _atomic(source, mutate, _validate_source)
    return _require_result_type(result, SourceIndexEntry)


def source_cancel_absent(
    source: Source, key: StableKey, *, transport_context: TransportContext
) -> SourceIndexEntry:
    def mutate(candidate: Source) -> SourceIndexEntry:
        index = candidate.index
        _validate_stable_key(key)
        if index.phase is not SourceIndexPhase.OPEN:
            raise Reject()
        if key.source_namespace != index.source_namespace:
            raise Reject()
        _require_transport(
            candidate.transport_authority,
            transport_context,
            expected_principal=key.requester_principal,
        )
        _key_root(candidate, key)
        prior = index.entries.get(key)
        if prior is not None:
            if (
                prior.kind is IndexEntryKind.CANCELED_BEFORE_ISSUANCE
                and candidate.generations.absent_intent_tombstones.get(key)
                == "CANCELED_BEFORE_ISSUANCE"
            ):
                return prior
            raise Reject()
        if len(index.entries) >= index.entry_capacity:
            raise Reject()
        entry = SourceIndexEntry(
            stable_key=key,
            kind=IndexEntryKind.CANCELED_BEFORE_ISSUANCE,
            plant_profile_digest=index.plant_profile_digest,
        )
        index.entries[key] = entry
        candidate.generations.absent_intent_tombstones[key] = "CANCELED_BEFORE_ISSUANCE"
        return entry

    result = _atomic(source, mutate, _validate_source)
    return _require_result_type(result, SourceIndexEntry)


def _slot_for_entry(
    source: Source, key: StableKey
) -> tuple[tuple[str, str], SourceIndexEntry, FreshnessSlot]:
    entry = source.index.entries.get(key)
    if entry is None or entry.kind is not IndexEntryKind.CHALLENGE_ISSUED:
        raise Reject()
    if entry.source_generation is None or entry.slot_id is None:
        raise Reject()
    slot_key = (entry.source_generation, entry.slot_id)
    slot = source.generations.slots.get(slot_key)
    if slot is None:
        raise Reject()
    return slot_key, entry, slot


def _terminalize_queue_if_present(source: Source, slot: FreshnessSlot) -> None:
    admission_key = slot.paired_frame_admission_key
    if admission_key is not None and admission_key in source.queue.records:
        source.queue.records[admission_key].state = QueueRecordState.TERMINALIZED


def source_cancel_available(
    source: Source, key: StableKey, *, transport_context: TransportContext
) -> None:
    def mutate(candidate: Source) -> None:
        if candidate.index.phase is not SourceIndexPhase.OPEN:
            raise Reject()
        _, _, slot = _slot_for_entry(candidate, key)
        _require_transport(
            candidate.transport_authority,
            transport_context,
            expected_principal=key.requester_principal,
        )
        if slot.state is SlotState.CANCELED_UNUSED:
            return
        if slot.state is not SlotState.AVAILABLE:
            raise Reject()
        _terminalize_queue_if_present(candidate, slot)
        slot.state = SlotState.CANCELED_UNUSED
        slot.delivery_gate = DeliveryGate.DELIVERY_TERMINAL

    _atomic(source, mutate, _validate_source)


def source_expire_available(
    source: Source, key: StableKey, *, source_clock_sample: BoundedClockSample
) -> None:
    def mutate(candidate: Source) -> None:
        if candidate.index.phase is not SourceIndexPhase.OPEN:
            raise Reject()
        _, _, slot = _slot_for_entry(candidate, key)
        _validate_sample(source_clock_sample)
        if (
            source_clock_sample.clock_id != candidate.index.source_clock_id
            or source_clock_sample.clock_epoch != candidate.index.source_clock_epoch
            or slot.live_session_epoch != candidate.index.live_session_epoch
            or slot.source_security_epoch != candidate.index.source_security_epoch
            or source_clock_sample.lower < slot.acceptance_not_after
        ):
            raise Reject()
        if slot.state is SlotState.EXPIRED_UNUSED:
            if slot.expiry_clock_sample != source_clock_sample:
                raise Reject()
            return
        if slot.state is not SlotState.AVAILABLE:
            raise Reject()
        _terminalize_queue_if_present(candidate, slot)
        slot.state = SlotState.EXPIRED_UNUSED
        slot.delivery_gate = DeliveryGate.DELIVERY_TERMINAL
        slot.expiry_clock_sample = source_clock_sample

    _atomic(source, mutate, _validate_source)


def _direct_requester_frame(source: Source, slot_key: tuple[str, str]) -> bytes:
    material = source.generations.private_challenges[slot_key]
    frame = RequesterFrame(
        stable_key_digest=stable_key_digest(material.stable_key).hex(),
        challenge_bytes=material.challenge_bytes,
        source_observer_capsule=material.source_observer_capsule,
        anchor_observer_capsule=None,
        source_producer_coordinate=material.source_producer_coordinate,
        anchor_producer_coordinate=None,
        paired_frame_admission_key=None,
        requester_connection=material.requester_connection,
        authenticated_principal=(material.transport_context.authenticated_principal),
        replay_domain=material.replay_domain,
        transport_security_epoch=(material.transport_context.transport_security_epoch),
        transport_verification_digest=(material.transport_context.verification_digest),
        plant_profile_digest=source.index.plant_profile_digest,
    )
    return frame.canonical_bytes()


def source_delivery_view(
    source: Source, key: StableKey, *, transport_context: TransportContext
) -> DeliveryView:
    _validate_source(source)
    _validate_stable_key(key)
    _validate_closed_graph(transport_context)
    slot_key, _, slot = _slot_for_entry(source, key)
    material = source.generations.private_challenges[slot_key]
    if (
        source.transport_authority.contexts.get(transport_context.verification_digest)
        != transport_context
        or source.transport_authority.channel_states.get(
            transport_context.verification_digest
        )
        is not TransportState.ACTIVE
        or transport_context.transport_security_epoch
        != source.transport_authority.security_epoch
        or transport_context.producer_capability
        is not source.transport_authority.producer_capability
        or transport_context.authenticated_principal != key.requester_principal
        or material.transport_context != transport_context
    ):
        return DeliveryView("TRANSPORT_CONTEXT_NOT_CURRENT", None)
    if slot.state is not SlotState.AVAILABLE:
        return DeliveryView("TERMINAL_OR_CONSUMED", None)
    try:
        _require_current_root(source, key)
    except Reject:
        return DeliveryView("REGISTERED_ROOT_AUTHORITY_NOT_CURRENT", None)
    if slot.delivery_gate is DeliveryGate.DIRECT_DELIVERY_READY:
        return DeliveryView(
            DeliveryGate.DIRECT_DELIVERY_READY.value,
            _direct_requester_frame(source, slot_key),
        )
    if slot.delivery_gate is DeliveryGate.ANCHOR_PAIRED_FRAME_PENDING:
        return DeliveryView("ANCHOR_ADMISSION_PENDING", None)
    if slot.delivery_gate is DeliveryGate.ANCHOR_PAIRED_FRAME_ADMITTED:
        return DeliveryView(DeliveryGate.ANCHOR_PAIRED_FRAME_ADMITTED.value, None)
    return DeliveryView(DeliveryGate.DELIVERY_TERMINAL.value, None)


def _validate_anchor(anchor: Anchor) -> None:
    _validate_closed_graph(anchor)
    _validate_namespace(anchor.source_namespace)
    _identifier(anchor.anchor_authority)
    _identifier(anchor.anchor_selector_incarnation)
    _identifier(anchor.anchor_security_epoch)
    if anchor.trusted_source_coordinate is not None:
        for value in anchor.trusted_source_coordinate[:3]:
            _identifier(value)
    if (
        not 1 <= anchor.eligible_capacity <= MAX_ELIGIBLE_ROOTS
        or not 1 <= anchor.entry_capacity <= MAX_ISSUANCE_ENTRIES
        or len(anchor.in_flight_mutations) > anchor.entry_capacity
    ):
        raise Reject()
    for mutation in anchor.in_flight_mutations:
        _identifier(mutation)
    if len(anchor.eligible_roots) > anchor.eligible_capacity:
        raise Reject()
    if not (
        set(anchor.eligible_roots)
        == set(anchor.enrollment_eligibility_digests)
        == set(anchor.enrollment_eligibility_hierarchies)
        == set(anchor.enrollment_notifications)
        == set(anchor.enrollment_cutoffs)
        == set(anchor.enrollment_clock_relations)
    ):
        raise Reject()
    root_incarnations = [
        root.root_incarnation for root in anchor.eligible_roots.values()
    ]
    if len(root_incarnations) != len(set(root_incarnations)):
        raise Reject()
    for audience_key, root in anchor.eligible_roots.items():
        eligibility_hierarchy = anchor.enrollment_eligibility_hierarchies[audience_key]
        notification = anchor.enrollment_notifications[audience_key]
        _validate_eligibility(eligibility_hierarchy)
        _validate_notification(notification)
        eligibility = eligibility_hierarchy.eligibility
        if (
            eligibility.root != root
            or anchor.enrollment_eligibility_digests[audience_key]
            != _eligibility_digest(eligibility_hierarchy)
            or notification.eligibility_hierarchy_digest
            != anchor.enrollment_eligibility_digests[audience_key]
            or notification.root_audience_key != audience_key
            or notification.anchor_entry_digest != root.anchor_enrollment_entry_digest
            or notification.source_namespace != anchor.source_namespace
            or notification.anchor_authority != anchor.anchor_authority
            or notification.exclusive_anchor_cutoff
            != anchor.enrollment_cutoffs[audience_key]
            or eligibility.qualified_clock_relation
            != anchor.enrollment_clock_relations[audience_key]
        ):
            raise Reject()
    if len(anchor.entries) > anchor.entry_capacity:
        raise Reject()
    if set(anchor.entries) != set(anchor.entry_hierarchies):
        raise Reject()
    for key, entry in anchor.entries.items():
        hierarchy = anchor.entry_hierarchies[key]
        _validate_anchor_entry(
            hierarchy, expected_credential=anchor.producer_credential
        )
        if key.source_namespace != anchor.source_namespace:
            raise Reject()
        if entry.stable_key != key:
            raise Reject()
        if (
            hierarchy.entry != entry
            or hierarchy.anchor_authority != anchor.anchor_authority
            or hierarchy.anchor_selector_incarnation
            != anchor.anchor_selector_incarnation
            or hierarchy.anchor_security_epoch != anchor.anchor_security_epoch
        ):
            raise Reject()
        anchor_entry_bytes(entry)
        root = _incarnation_root(anchor.eligible_roots, key.observer_root_incarnation)
        if (
            root.availability_profile is not ANCHOR_PROFILE
            or entry.mapped_acceptance_cutoff
            != anchor.enrollment_cutoffs[root.audience_key]
            or entry.anchor_clock_id != anchor.anchor_clock_id
            or entry.anchor_clock_epoch != anchor.anchor_clock_epoch
            or entry.clock_relation_id
            != anchor.enrollment_clock_relations[root.audience_key].relation_id
            or entry.clock_relation_digest
            != anchor.enrollment_clock_relations[root.audience_key].semantic_digest
        ):
            raise Reject()
    if len(anchor.relay_hierarchies) > anchor.entry_capacity:
        raise Reject()
    for admission_key, relay_hierarchy in anchor.relay_hierarchies.items():
        _validate_relay(relay_hierarchy, expected_credential=anchor.producer_credential)
        entry_hierarchy = anchor.entry_hierarchies.get(relay_hierarchy.entry.stable_key)
        if (
            relay_hierarchy.entry.paired_frame_admission_key != admission_key
            or entry_hierarchy is None
            or relay_hierarchy.anchor_entry_hierarchy_digest
            != _object_digest(entry_hierarchy)
            or relay_hierarchy.entry != entry_hierarchy.entry
        ):
            raise Reject()
    if anchor.phase in {
        AnchorPhase.ABSENT,
        AnchorPhase.PENDING_SOURCE_CONFIRMATION,
        AnchorPhase.CANCELED,
    }:
        if (
            anchor.eligible_roots
            or anchor.enrollment_eligibility_digests
            or anchor.enrollment_eligibility_hierarchies
            or anchor.enrollment_notifications
            or anchor.enrollment_cutoffs
            or anchor.enrollment_clock_relations
            or anchor.entries
            or anchor.entry_hierarchies
            or anchor.relay_hierarchies
            or anchor.in_flight_mutations
            or anchor.cooperative_retirement_digest is not None
            or anchor.isolation_digest is not None
            or anchor.closure_evidence_state is not AnchorEvidenceState.NONE
            or anchor.first_closure_cause is not AnchorClosureCause.NO_ANCHOR_CLOSURE
            or anchor.reservation_terminal_cause is not None
            or anchor.frozen_root is not None
            or anchor.frozen_audience
            or anchor.closure_hierarchy is not None
        ):
            raise Reject()
        return
    if anchor.phase is AnchorPhase.OPEN:
        if (
            anchor.cooperative_retirement_digest is not None
            or anchor.isolation_digest is not None
            or anchor.closure_evidence_state is not AnchorEvidenceState.NONE
            or anchor.first_closure_cause is not AnchorClosureCause.NO_ANCHOR_CLOSURE
            or anchor.reservation_terminal_cause is not None
            or anchor.frozen_root is not None
            or anchor.frozen_audience
            or anchor.closure_hierarchy is not None
        ):
            raise Reject()
    else:
        expected_evidence_state = (
            AnchorEvidenceState.COOPERATIVE_AND_ISOLATION
            if (
                anchor.cooperative_retirement_digest is not None
                and anchor.isolation_digest is not None
            )
            else (
                AnchorEvidenceState.COOPERATIVE_ONLY
                if anchor.cooperative_retirement_digest is not None
                else AnchorEvidenceState.ISOLATION_ONLY
            )
        )
        expected_terminal_cause = (
            _COOPERATIVE
            if anchor.first_closure_cause is AnchorClosureCause.COOPERATIVE
            else _ISOLATED
        )
        if (
            anchor.frozen_root is None
            or (
                anchor.cooperative_retirement_digest is None
                and anchor.isolation_digest is None
            )
            or anchor.closure_evidence_state is not expected_evidence_state
            or anchor.first_closure_cause
            not in {AnchorClosureCause.COOPERATIVE, AnchorClosureCause.ISOLATION}
            or anchor.reservation_terminal_cause != expected_terminal_cause
        ):
            raise Reject()
        if anchor.frozen_audience != tuple(sorted(anchor.eligible_roots)):
            raise Reject()
        if anchor.in_flight_mutations:
            raise Reject()
        retained_tree = SparseMerkleTree(
            ProofContext.ANCHOR,
            {key: anchor_entry_bytes(entry) for key, entry in anchor.entries.items()},
        )
        if retained_tree.root != anchor.frozen_root:
            raise Reject()
        closure_hierarchy = anchor.closure_hierarchy
        if closure_hierarchy is None:
            raise Reject()
        _validate_closure(
            closure_hierarchy, expected_credential=anchor.producer_credential
        )
        expected_bundle = ClosureBundle(
            source_namespace=anchor.source_namespace,
            availability_profile=(ANCHOR_PROFILE),
            context=ProofContext.ANCHOR,
            root=anchor.frozen_root,
            audience=anchor.frozen_audience,
            origin=ClosureOrigin.ANCHOR,
            anchor_closure_cause=anchor.first_closure_cause,
        )
        if (
            closure_hierarchy.bundle != expected_bundle
            or closure_hierarchy.producer_authority_id != anchor.anchor_authority
            or closure_hierarchy.producer_security_epoch != anchor.anchor_security_epoch
            or closure_hierarchy.enrollment_ancestry_digest
            != _anchor_ancestry_digest(anchor)
        ):
            raise Reject()


def new_anchor(namespace: tuple[str, str, str]) -> Anchor:
    anchor = Anchor(source_namespace=namespace)
    _validate_anchor(anchor)
    return anchor


def anchor_enroll_root(
    anchor: Anchor,
    namespace_registry: AuthorityRegistry,
    source: Source,
    eligibility_hierarchy: ProtectedEligibility,
    *,
    anchor_clock_sample: BoundedClockSample,
    clock_relation: ClockRelation,
) -> ProtectedNotification:
    def mutate(
        candidate: Anchor, candidate_registry: AnchorRegistry
    ) -> ProtectedNotification:
        _validate_eligibility(eligibility_hierarchy)
        eligibility = eligibility_hierarchy.eligibility
        root = eligibility.root
        retained_notification = candidate.enrollment_notifications.get(
            root.audience_key
        )
        if retained_notification is not None:
            if (
                candidate.eligible_roots.get(root.audience_key) != root
                or candidate.enrollment_eligibility_hierarchies.get(root.audience_key)
                != eligibility_hierarchy
                or candidate.enrollment_eligibility_digests.get(root.audience_key)
                != _eligibility_digest(eligibility_hierarchy)
                or candidate.enrollment_clock_relations.get(root.audience_key)
                != clock_relation
            ):
                raise Reject()
            return retained_notification
        source_admission = source.index.root_admissions.get(root.audience_key)
        if candidate.phase is not AnchorPhase.OPEN:
            raise Reject()
        if (
            candidate_registry.trusted_source_producer_credential
            is not source.producer_credential
            or candidate.trusted_source_coordinate
            != (
                source.source_authority_id,
                source.index.source_index_incarnation,
                source.index.source_security_epoch,
                source.producer_credential,
            )
            or source.index.source_namespace != candidate.source_namespace
            or source_admission is None
            or source_admission.eligibility_hierarchy != eligibility_hierarchy
            or eligibility.source_namespace != candidate.source_namespace
            or eligibility.anchor_authority != candidate.anchor_authority
            or root.availability_profile is not ANCHOR_PROFILE
            or root.anchor_enrollment_entry_digest is None
            or not root.source_enrollment_hierarchy_digest
        ):
            raise Reject()
        _validate_anchor_sample(anchor_clock_sample, clock_relation)
        if (
            clock_relation != eligibility.qualified_clock_relation
            or clock_relation.anchor_clock_id != candidate.anchor_clock_id
            or clock_relation.anchor_clock_epoch != candidate.anchor_clock_epoch
            or anchor_clock_sample.clock_id != candidate.anchor_clock_id
            or anchor_clock_sample.clock_epoch != candidate.anchor_clock_epoch
            or anchor_clock_sample.upper >= eligibility.exclusive_anchor_cutoff
        ):
            raise Reject()
        hierarchy_digest = _eligibility_digest(eligibility_hierarchy)
        prior = candidate.eligible_roots.get(root.audience_key)
        if prior is not None:
            if (
                prior != root
                or candidate.enrollment_eligibility_digests[root.audience_key]
                != hierarchy_digest
            ):
                raise Reject()
        else:
            if len(candidate.eligible_roots) >= candidate.eligible_capacity:
                raise Reject()
            if any(
                enrolled.root_incarnation == root.root_incarnation
                for enrolled in candidate.eligible_roots.values()
            ):
                raise Reject()
            candidate.eligible_roots[root.audience_key] = root
            candidate.enrollment_eligibility_digests[root.audience_key] = (
                hierarchy_digest
            )
            candidate.enrollment_eligibility_hierarchies[root.audience_key] = (
                eligibility_hierarchy
            )
            candidate.enrollment_cutoffs[root.audience_key] = (
                eligibility.exclusive_anchor_cutoff
            )
            candidate.enrollment_clock_relations[root.audience_key] = (
                eligibility.qualified_clock_relation
            )
        semantic_value = (
            hierarchy_digest,
            root.anchor_enrollment_entry_digest,
            candidate.source_namespace,
            root.audience_key,
            candidate.anchor_authority,
            eligibility.exclusive_anchor_cutoff,
            "OBSERVER_ROOT_ENROLLMENT_NOTIFICATION",
            "DURABLE_HISTORICAL_COMMIT",
        )
        (
            envelope_digest,
            family_manifest_digest,
            pre_manifest_digest,
            producer_completion_digest,
            delivery_capsule_digest,
            audience_proof_digest,
            manifest_proof_digest,
            delivery_verification_digest,
        ) = _protection_digests("anchor-source-enrollment-notification", semantic_value)
        notification = ProtectedNotification(
            eligibility_hierarchy_digest=hierarchy_digest,
            anchor_entry_digest=root.anchor_enrollment_entry_digest,
            source_namespace=candidate.source_namespace,
            root_audience_key=root.audience_key,
            anchor_authority=candidate.anchor_authority,
            exclusive_anchor_cutoff=eligibility.exclusive_anchor_cutoff,
            audience_purpose="OBSERVER_ROOT_ENROLLMENT_NOTIFICATION",
            verification_class="DURABLE_HISTORICAL_COMMIT",
            envelope_digest=envelope_digest,
            family_manifest_digest=family_manifest_digest,
            pre_manifest_digest=pre_manifest_digest,
            producer_completion_digest=producer_completion_digest,
            delivery_capsule_digest=delivery_capsule_digest,
            audience_proof_digest=audience_proof_digest,
            manifest_proof_digest=manifest_proof_digest,
            delivery_verification_digest=delivery_verification_digest,
        )
        _validate_notification(notification)
        candidate.enrollment_notifications[root.audience_key] = notification
        candidate_registry.eligible_root_count = len(candidate.eligible_roots)
        return notification

    result = _atomic_anchor_transition(anchor, namespace_registry, mutate)
    return _require_result_type(result, ProtectedNotification)


def anchor_append(
    anchor: Anchor,
    namespace_registry: AuthorityRegistry,
    source: Source,
    source_entry: SourceIndexEntry,
    *,
    intended_observer_root_id: str,
    mapped_acceptance_cutoff: int,
    anchor_clock_sample: BoundedClockSample,
) -> ProtectedAnchorEntry:
    def mutate(
        candidate: Anchor, candidate_registry: AnchorRegistry
    ) -> ProtectedAnchorEntry:
        retained_hierarchy = candidate.entry_hierarchies.get(source_entry.stable_key)
        if retained_hierarchy is not None:
            if (
                retained_hierarchy.entry.source_index_entry_digest
                != hashlib.sha256(source_entry_bytes(source_entry)).hexdigest()
                or retained_hierarchy.entry.intended_observer_root_id
                != intended_observer_root_id
                or retained_hierarchy.entry.mapped_acceptance_cutoff
                != mapped_acceptance_cutoff
            ):
                raise Reject()
            return retained_hierarchy
        if candidate.phase is not AnchorPhase.OPEN:
            raise Reject()
        if source_entry.kind is not IndexEntryKind.CHALLENGE_ISSUED:
            raise Reject()
        if (
            candidate_registry.trusted_source_producer_credential
            is not source.producer_credential
            or candidate.trusted_source_coordinate
            != (
                source.source_authority_id,
                source.index.source_index_incarnation,
                source.index.source_security_epoch,
                source.producer_credential,
            )
            or source_entry.stable_key.source_namespace != candidate.source_namespace
            or source_entry.challenge_commitment is None
            or source_entry.paired_frame_admission_key is None
            or source_entry.plant_profile_digest != source.index.plant_profile_digest
        ):
            raise Reject()
        source_hierarchy = source.index.issuance_hierarchies.get(
            source_entry.stable_key
        )
        if source_hierarchy is None or source_hierarchy.source_entry != source_entry:
            raise Reject()
        _validate_publication(
            source_hierarchy, expected_credential=source.producer_credential
        )
        root = _incarnation_root(
            candidate.eligible_roots, source_entry.stable_key.observer_root_incarnation
        )
        if root.root_id != intended_observer_root_id:
            raise Reject()
        qualified_relation = candidate.enrollment_clock_relations[root.audience_key]
        _validate_anchor_sample(anchor_clock_sample, qualified_relation)
        if (
            anchor_clock_sample.clock_id != candidate.anchor_clock_id
            or anchor_clock_sample.clock_epoch != candidate.anchor_clock_epoch
            or mapped_acceptance_cutoff
            != candidate.enrollment_cutoffs[root.audience_key]
            or anchor_clock_sample.upper >= mapped_acceptance_cutoff
        ):
            raise Reject()
        if source_entry.stable_key in candidate.entries:
            raise Reject()
        if len(candidate.entries) >= candidate.entry_capacity:
            raise Reject()
        previous_tree = SparseMerkleTree(
            ProofContext.ANCHOR,
            {
                retained_key: anchor_entry_bytes(retained_entry)
                for retained_key, retained_entry in candidate.entries.items()
            },
        )
        entry = AnchorEntry(
            stable_key=source_entry.stable_key,
            source_index_entry_digest=hashlib.sha256(
                source_entry_bytes(source_entry)
            ).hexdigest(),
            challenge_commitment=source_entry.challenge_commitment,
            intended_observer_root_id=intended_observer_root_id,
            paired_frame_admission_key=(source_entry.paired_frame_admission_key),
            mapped_acceptance_cutoff=mapped_acceptance_cutoff,
            anchor_clock_id=candidate.anchor_clock_id,
            anchor_clock_epoch=candidate.anchor_clock_epoch,
            clock_relation_id=qualified_relation.relation_id,
            clock_relation_digest=qualified_relation.semantic_digest,
            plant_profile_digest=source_entry.plant_profile_digest,
        )
        candidate.entries[source_entry.stable_key] = entry
        committed_tree = SparseMerkleTree(
            ProofContext.ANCHOR,
            {
                retained_key: anchor_entry_bytes(retained_entry)
                for retained_key, retained_entry in candidate.entries.items()
            },
        )
        membership_proof = committed_tree.proof(
            source_entry.stable_key, ProofKind.MEMBERSHIP
        )
        source_hierarchy_digest = _object_digest(source_hierarchy)
        commit_semantic = (
            candidate.anchor_authority,
            candidate.anchor_selector_incarnation,
            candidate.anchor_security_epoch,
            entry,
            source_hierarchy_digest,
            previous_tree.root,
            committed_tree.root,
        )
        anchor_commit_receipt_digest = _fixture_digest(
            "anchor-entry-commit|" + repr(commit_semantic)
        )
        anchor_retention_receipt_digest = _fixture_digest(
            "anchor-entry-retention|"
            + anchor_commit_receipt_digest
            + "|"
            + hashlib.sha256(membership_proof).hexdigest()
        )
        provisional_hierarchy = ProtectedAnchorEntry(
            entry=entry,
            anchor_authority=candidate.anchor_authority,
            anchor_selector_incarnation=(candidate.anchor_selector_incarnation),
            anchor_security_epoch=candidate.anchor_security_epoch,
            source_publication_hierarchy_digest=source_hierarchy_digest,
            previous_anchor_root=previous_tree.root,
            committed_anchor_root=committed_tree.root,
            membership_proof=membership_proof,
            anchor_commit_receipt_digest=anchor_commit_receipt_digest,
            anchor_retention_receipt_digest=(anchor_retention_receipt_digest),
            producer_credential=candidate.producer_credential,
            protection=EMPTY_PROTECTION,
        )
        hierarchy = replace(
            provisional_hierarchy,
            protection=_protect(
                "anchor-challenge-entry",
                _anchor_entry_value(provisional_hierarchy),
                audience_purpose="SOURCE_PAIRED_FRAME_ADMISSION",
                verification_class="DURABLE_INDEPENDENT_ANCHOR_COMMIT",
            ),
        )
        _validate_anchor_entry(
            hierarchy, expected_credential=candidate.producer_credential
        )
        candidate.entry_hierarchies[source_entry.stable_key] = hierarchy
        candidate_registry.challenge_entry_count = len(candidate.entries)
        return hierarchy

    result = _atomic_anchor_transition(anchor, namespace_registry, mutate)
    return _require_result_type(result, ProtectedAnchorEntry)


def anchor_publish_observer_opaque_relay(
    anchor: Anchor,
    namespace_registry: AuthorityRegistry,
    anchor_entry_hierarchy: ProtectedAnchorEntry,
    anchor_observer_capsule: bytes,
    binding: RelayBinding,
) -> ProtectedRelay:
    def mutate(candidate: Anchor, candidate_registry: AnchorRegistry) -> ProtectedRelay:
        _validate_anchor_entry(
            anchor_entry_hierarchy, expected_credential=candidate.producer_credential
        )
        entry = anchor_entry_hierarchy.entry
        admission_key = entry.paired_frame_admission_key
        if (
            candidate.phase is not AnchorPhase.OPEN
            or candidate.entry_hierarchies.get(entry.stable_key)
            != anchor_entry_hierarchy
            or not anchor_observer_capsule
            or len(anchor_observer_capsule) > MAX_CAPSULE_BYTES
            or not binding.observer_envelope_identity
            or binding.producer_coordinate != "anchor-producer:" + admission_key
            or not _complete_digest_set(
                (
                    binding.observer_envelope_bytes_digest,
                    binding.observer_envelope_authentication_set_digest,
                )
            )
        ):
            raise Reject()
        provisional = ProtectedRelay(
            anchor_entry_hierarchy_digest=_object_digest(anchor_entry_hierarchy),
            entry=entry,
            anchor_observer_capsule=anchor_observer_capsule,
            binding=binding,
            common_completion_coordinate="anchor-completion:" + admission_key,
            producer_credential=candidate.producer_credential,
            protection=EMPTY_PROTECTION,
        )
        hierarchy = replace(
            provisional,
            protection=_protect(
                "anchor-observer-opaque-relay",
                _relay_value(provisional),
                audience_purpose="REGISTERED_OBSERVER_ROOT_OPAQUE_RELAY",
                verification_class="DURABLE_INDEPENDENT_ANCHOR_OUTPUT",
            ),
        )
        prior = candidate.relay_hierarchies.get(admission_key)
        if prior is not None:
            if prior != hierarchy:
                raise Reject()
            return prior
        _validate_relay(hierarchy, expected_credential=candidate.producer_credential)
        candidate.relay_hierarchies[admission_key] = hierarchy
        candidate_registry.admission_count = len(candidate.relay_hierarchies)
        return hierarchy

    result = _atomic_anchor_transition(anchor, namespace_registry, mutate)
    return _require_result_type(result, ProtectedRelay)


def source_admit_paired_frame(
    source: Source,
    key: StableKey,
    anchor: Anchor,
    anchor_entry_hierarchy: ProtectedAnchorEntry,
    relay_hierarchy: ProtectedRelay,
    *,
    source_clock_sample: BoundedClockSample,
    clock_relation: ClockRelation,
) -> bytes:
    def mutate(candidate: Source) -> bytes:
        if candidate.index.phase is not SourceIndexPhase.OPEN:
            raise Reject()
        slot_key, source_entry, slot = _slot_for_entry(candidate, key)
        if slot.delivery_gate is DeliveryGate.ANCHOR_PAIRED_FRAME_ADMITTED:
            record = candidate.queue.records.get(slot.paired_frame_admission_key or "")
            if (
                record is None
                or anchor.entry_hierarchies.get(key) != anchor_entry_hierarchy
                or anchor.relay_hierarchies.get(record.admission_key) != relay_hierarchy
                or record.clock_relation_digest != clock_relation.semantic_digest
            ):
                raise Reject()
            _, anchor_upper = _clock_images(source_clock_sample, clock_relation)
            if anchor_upper >= record.mapped_acceptance_cutoff:
                raise Reject()
            return record.frame_bytes
        if (
            candidate.index.availability_profile is not ANCHOR_PROFILE
            or slot.state is not SlotState.AVAILABLE
            or slot.delivery_gate is not DeliveryGate.ANCHOR_PAIRED_FRAME_PENDING
        ):
            raise Reject()
        _validate_anchor_entry(
            anchor_entry_hierarchy, expected_credential=anchor.producer_credential
        )
        _validate_relay(relay_hierarchy, expected_credential=anchor.producer_credential)
        anchor_entry = anchor_entry_hierarchy.entry
        anchor_observer_capsule = relay_hierarchy.anchor_observer_capsule
        opaque_relay_binding = relay_hierarchy.binding
        allocation_binding = candidate.index.anchor_allocation_binding
        source_publication = candidate.index.issuance_hierarchies.get(key)
        if (
            allocation_binding is None
            or candidate.trusted_anchor_coordinate
            != (
                anchor.anchor_authority,
                anchor.anchor_selector_incarnation,
                anchor.anchor_security_epoch,
                anchor.producer_credential,
            )
            or allocation_binding.anchor_authority != anchor.anchor_authority
            or allocation_binding.anchor_selector_incarnation
            != anchor.anchor_selector_incarnation
            or anchor.entry_hierarchies.get(key) != anchor_entry_hierarchy
            or anchor.relay_hierarchies.get(anchor_entry.paired_frame_admission_key)
            != relay_hierarchy
            or relay_hierarchy.anchor_entry_hierarchy_digest
            != _object_digest(anchor_entry_hierarchy)
            or source_publication is None
            or anchor_entry_hierarchy.source_publication_hierarchy_digest
            != _object_digest(source_publication)
        ):
            raise Reject()
        eligible_root = _require_current_root(candidate, key)
        admission = candidate.index.root_admissions[eligible_root.audience_key]
        if admission.eligibility_hierarchy is None:
            raise Reject()
        qualified_relation = (
            admission.eligibility_hierarchy.eligibility.qualified_clock_relation
        )
        _, conservative_anchor_upper = _clock_images(
            source_clock_sample, clock_relation
        )
        if (
            anchor_entry.stable_key != key
            or anchor_entry.intended_observer_root_id != eligible_root.root_id
            or anchor_entry.challenge_commitment != source_entry.challenge_commitment
            or anchor_entry.source_index_entry_digest
            != hashlib.sha256(source_entry_bytes(source_entry)).hexdigest()
            or anchor_entry.paired_frame_admission_key
            != source_entry.paired_frame_admission_key
            or clock_relation != qualified_relation
            or anchor_entry.clock_relation_id != qualified_relation.relation_id
            or anchor_entry.clock_relation_digest != qualified_relation.semantic_digest
            or clock_relation.source_clock_id != candidate.index.source_clock_id
            or clock_relation.source_clock_epoch != candidate.index.source_clock_epoch
            or clock_relation.anchor_clock_id != anchor_entry.anchor_clock_id
            or clock_relation.anchor_clock_epoch != anchor_entry.anchor_clock_epoch
            or conservative_anchor_upper >= anchor_entry.mapped_acceptance_cutoff
        ):
            raise Reject()
        expected_anchor_producer_coordinate = (
            "anchor-producer:" + anchor_entry.paired_frame_admission_key
        )
        digest_members = (
            opaque_relay_binding.observer_envelope_bytes_digest,
            opaque_relay_binding.observer_envelope_authentication_set_digest,
        )
        if (
            not anchor_observer_capsule
            or len(anchor_observer_capsule) > MAX_CAPSULE_BYTES
            or not opaque_relay_binding.observer_envelope_identity
            or opaque_relay_binding.producer_coordinate
            != expected_anchor_producer_coordinate
            or any(
                len(digest) != 64
                or any(character not in "0123456789abcdef" for character in digest)
                for digest in digest_members
            )
            or relay_hierarchy.common_completion_coordinate
            != "anchor-completion:" + anchor_entry.paired_frame_admission_key
        ):
            raise Reject()
        material = candidate.generations.private_challenges[slot_key]
        frame = RequesterFrame(
            stable_key_digest=stable_key_digest(key).hex(),
            challenge_bytes=material.challenge_bytes,
            source_observer_capsule=material.source_observer_capsule,
            anchor_observer_capsule=anchor_observer_capsule,
            source_producer_coordinate=material.source_producer_coordinate,
            anchor_producer_coordinate=opaque_relay_binding.producer_coordinate,
            paired_frame_admission_key=anchor_entry.paired_frame_admission_key,
            requester_connection=material.requester_connection,
            authenticated_principal=(
                material.transport_context.authenticated_principal
            ),
            replay_domain=material.replay_domain,
            transport_security_epoch=(
                material.transport_context.transport_security_epoch
            ),
            transport_verification_digest=(
                material.transport_context.verification_digest
            ),
            plant_profile_digest=candidate.index.plant_profile_digest,
        )
        frame_bytes = frame.canonical_bytes()
        admission_key = anchor_entry.paired_frame_admission_key
        if admission_key in candidate.queue.records:
            raise Reject()
        if len(candidate.queue.records) >= candidate.queue.record_capacity:
            raise Reject()
        candidate.queue.records[admission_key] = PairedQueueRecord(
            admission_key=admission_key,
            stable_key=key,
            transport_context=material.transport_context,
            frame_bytes=frame_bytes,
            frame_digest=hashlib.sha256(frame_bytes).hexdigest(),
            source_capsule_digest=hashlib.sha256(
                material.source_observer_capsule
            ).hexdigest(),
            anchor_capsule_digest=hashlib.sha256(anchor_observer_capsule).hexdigest(),
            opaque_relay_binding=opaque_relay_binding,
            mapped_acceptance_cutoff=anchor_entry.mapped_acceptance_cutoff,
            clock_relation_id=anchor_entry.clock_relation_id,
            clock_relation_digest=anchor_entry.clock_relation_digest,
            anchor_clock_id=anchor_entry.anchor_clock_id,
            anchor_clock_epoch=anchor_entry.anchor_clock_epoch,
            state=QueueRecordState.MAY_HAVE_BEEN_EXPOSED,
        )
        slot.delivery_gate = DeliveryGate.ANCHOR_PAIRED_FRAME_ADMITTED
        return frame_bytes

    result = _atomic(source, mutate, _validate_source)
    return _require_result_type(result, bytes)


def source_handoff_paired_frame(
    source: Source,
    key: StableKey,
    *,
    transport_context: TransportContext,
    source_clock_sample: BoundedClockSample,
    clock_relation: ClockRelation,
    quiescence_receipt: ProtectedHandoff,
) -> HandoffAttempt:
    def mutate(candidate: Source) -> HandoffAttempt:
        _require_current_root(candidate, key)
        _, _, slot = _slot_for_entry(candidate, key)
        if (
            slot.state is not SlotState.AVAILABLE
            or slot.delivery_gate is not DeliveryGate.ANCHOR_PAIRED_FRAME_ADMITTED
            or slot.paired_frame_admission_key is None
        ):
            raise Reject()
        record = candidate.queue.records.get(slot.paired_frame_admission_key)
        if record is None or record.state is QueueRecordState.TERMINALIZED:
            raise Reject()
        if (
            candidate.transport_authority.contexts.get(
                transport_context.verification_digest
            )
            != transport_context
            or candidate.transport_authority.channel_states.get(
                transport_context.verification_digest
            )
            is not TransportState.ACTIVE
            or transport_context.transport_security_epoch
            != candidate.transport_authority.security_epoch
            or transport_context.producer_capability
            is not candidate.transport_authority.producer_capability
            or transport_context.authenticated_principal != key.requester_principal
        ):
            raise Reject()
        if record.transport_context != transport_context:
            raise Reject()
        if (
            candidate.transport_authority.handoff_receipts.get(record.admission_key)
            != quiescence_receipt
            or quiescence_receipt.producer_capability
            is not candidate.transport_authority.producer_capability
            or quiescence_receipt.transport_verification_digest
            != transport_context.verification_digest
            or quiescence_receipt.frame_digest != record.frame_digest
        ):
            raise Reject()
        _, conservative_anchor_upper = _clock_images(
            source_clock_sample, clock_relation
        )
        if (
            clock_relation.relation_id != record.clock_relation_id
            or clock_relation.semantic_digest != record.clock_relation_digest
            or clock_relation.source_clock_id != candidate.index.source_clock_id
            or clock_relation.source_clock_epoch != candidate.index.source_clock_epoch
            or clock_relation.anchor_clock_id != record.anchor_clock_id
            or clock_relation.anchor_clock_epoch != record.anchor_clock_epoch
            or conservative_anchor_upper >= record.mapped_acceptance_cutoff
        ):
            raise Reject()
        if record.handoff_receipt_digest is not None:
            if record.handoff_receipt_digest != quiescence_receipt.receipt_digest:
                raise Reject()
        else:
            record.handoff_receipt_digest = quiescence_receipt.receipt_digest
            if quiescence_receipt.result is not (
                HandoffResult.MAY_HAVE_BEEN_EXPOSED_TOKEN_RELEASED
            ):
                record.state = QueueRecordState.TERMINALIZED
                slot.state = SlotState.CANCELED_UNUSED
                slot.delivery_gate = DeliveryGate.DELIVERY_TERMINAL
        return HandoffAttempt(
            result=quiescence_receipt.result,
            frame_bytes=(
                record.frame_bytes
                if quiescence_receipt.result
                is HandoffResult.MAY_HAVE_BEEN_EXPOSED_TOKEN_RELEASED
                else None
            ),
        )

    result = _atomic(source, mutate, _validate_source)
    return _require_result_type(result, HandoffAttempt)


def source_accept(
    source: Source,
    key: StableKey,
    *,
    transport_context: TransportContext,
    requester_frame: bytes,
    source_clock_sample: BoundedClockSample,
) -> str:
    def mutate(candidate: Source) -> str:
        if candidate.index.phase is not SourceIndexPhase.OPEN:
            raise Reject()
        if (
            candidate.transport_authority.contexts.get(
                transport_context.verification_digest
            )
            != transport_context
            or candidate.transport_authority.channel_states.get(
                transport_context.verification_digest
            )
            is not TransportState.ACTIVE
            or transport_context.transport_security_epoch
            != candidate.transport_authority.security_epoch
            or transport_context.producer_capability
            is not candidate.transport_authority.producer_capability
            or transport_context.authenticated_principal != key.requester_principal
        ):
            raise Reject()
        slot_key, _, slot = _slot_for_entry(candidate, key)
        material = candidate.generations.private_challenges[slot_key]
        if material.transport_context != transport_context:
            raise Reject()
        _validate_sample(source_clock_sample)
        if (
            source_clock_sample.clock_id != candidate.index.source_clock_id
            or source_clock_sample.clock_epoch != candidate.index.source_clock_epoch
            or slot.live_session_epoch != candidate.index.live_session_epoch
            or slot.source_security_epoch != candidate.index.source_security_epoch
        ):
            raise Reject()
        if slot.state is SlotState.CONSUMED_BY_ACCEPTED_REQUEST:
            grant_id = slot.accepted_grant_id
            if grant_id is None:
                raise Reject()
            if slot.paired_frame_admission_key is None:
                expected_retry_frame = _direct_requester_frame(candidate, slot_key)
            else:
                retained_record = candidate.queue.records.get(
                    slot.paired_frame_admission_key
                )
                if retained_record is None:
                    raise Reject()
                expected_retry_frame = retained_record.frame_bytes
            if requester_frame != expected_retry_frame:
                raise Reject()
            return grant_id
        if (
            source_clock_sample.upper >= slot.acceptance_not_after
            or source_clock_sample.upper >= slot.authority_lease_not_after
        ):
            raise Reject()
        if slot.state is not SlotState.AVAILABLE:
            raise Reject()
        _require_current_root(candidate, key)
        if slot.delivery_gate is DeliveryGate.DIRECT_DELIVERY_READY:
            expected_frame = _direct_requester_frame(candidate, slot_key)
        elif (
            slot.delivery_gate is DeliveryGate.ANCHOR_PAIRED_FRAME_ADMITTED
            and slot.paired_frame_admission_key is not None
        ):
            record = candidate.queue.records.get(slot.paired_frame_admission_key)
            if record is None or record.state is QueueRecordState.TERMINALIZED:
                raise Reject()
            expected_frame = record.frame_bytes
        else:
            raise Reject()
        if requester_frame != expected_frame:
            raise Reject()
        if any(
            grant.stable_key.logical_target_key == key.logical_target_key
            for grant in candidate.generations.accepted_grants.values()
        ):
            raise Reject()
        grant_id = "grant:" + stable_key_digest(key).hex()
        if grant_id in candidate.generations.accepted_grants:
            raise Reject()
        grant = AcceptedGrant(
            grant_id=grant_id,
            stable_key=key,
            live_session_epoch=slot.live_session_epoch,
            authority_lease_not_after=slot.authority_lease_not_after,
            acceptance_not_after=slot.acceptance_not_after,
            source_security_epoch=slot.source_security_epoch,
            plant_profile_digest=slot.plant_profile_digest,
            acceptance_transport_verification_digest=(
                transport_context.verification_digest
            ),
            acceptance_receipt_digest=_fixture_digest(
                "accepted-grant|" + repr((grant_id, slot, source_clock_sample))
            ),
            closure_plan_id="closure-plan:" + grant_id,
            closure_plan_digest="",
            predecessor_grant_id=None,
        )
        grant.closure_plan_digest = _grant_plan_digest(
            candidate.source_authority_id,
            candidate.index.source_index_incarnation,
            grant,
        )
        candidate.generations.accepted_grants[grant_id] = grant
        _terminalize_queue_if_present(candidate, slot)
        slot.state = SlotState.CONSUMED_BY_ACCEPTED_REQUEST
        slot.delivery_gate = DeliveryGate.DELIVERY_TERMINAL
        slot.accepted_grant_id = grant_id
        return grant_id

    result = _atomic(source, mutate, _validate_source)
    return _require_result_type(result, str)


def distributed_closure_publish(
    authority: ClosureAuthority, source: Source, grant_id: str
) -> ProtectedDistributedClosure:
    _validate_source(source)

    def mutate(candidate: ClosureAuthority) -> ProtectedDistributedClosure:
        if source.index.phase is not SourceIndexPhase.OPEN:
            raise Reject()
        grant = source.generations.accepted_grants.get(grant_id)
        if (
            grant is None
            or grant.closure_plan_id != "closure-plan:" + grant.grant_id
            or grant.closure_plan_digest
            != _grant_plan_digest(
                source.source_authority_id, source.index.source_index_incarnation, grant
            )
        ):
            raise Reject()
        fact = DistributedGrantClosureFact(
            state=DistributedClosureState.TERMINAL,
            authority_id=candidate.authority_id,
            authority_security_epoch=candidate.security_epoch,
            closure_plan_id=grant.closure_plan_id,
            closure_plan_digest=grant.closure_plan_digest,
            grant_id=grant.grant_id,
            stable_key=grant.stable_key,
            live_session_epoch=grant.live_session_epoch,
            source_authority_id=source.source_authority_id,
            source_index_incarnation=source.index.source_index_incarnation,
            accepted_source_security_epoch=grant.source_security_epoch,
            closure_source_security_epoch=source.index.source_security_epoch,
            plant_profile_digest=grant.plant_profile_digest,
            acceptance_transport_verification_digest=(
                grant.acceptance_transport_verification_digest
            ),
            acceptance_receipt_digest=grant.acceptance_receipt_digest,
        )
        hierarchy = ProtectedDistributedClosure(
            fact, candidate.producer_credential, _protect_distributed(fact)
        )
        key = _distributed_key(fact)
        prior = candidate.hierarchies.get(key)
        if prior is not None:
            if prior != hierarchy:
                raise Reject()
            return prior
        if len(candidate.hierarchies) >= MAX_GENERATION_SLOTS:
            raise Reject()
        candidate.hierarchies[key] = hierarchy
        candidate.revision += 1
        return hierarchy

    result = _atomic(authority, mutate, _validate_closure_authority)
    return _require_result_type(result, ProtectedDistributedClosure)


def source_import_accepted_grant_closure(
    source: Source, authority: ClosureAuthority, distributed: object
) -> ProtectedAcceptedGrantClosureReceipt:
    _validate_closure_authority(authority)

    def mutate(candidate: Source) -> ProtectedAcceptedGrantClosureReceipt:
        if candidate.index.phase is not SourceIndexPhase.OPEN:
            raise Reject()
        _validate_distributed_closure(
            distributed,
            expected_credential=(
                candidate.trusted_distributed_closure_authority_credential
            ),
        )
        external = distributed.fact
        key = _distributed_key(external)
        grant = candidate.generations.accepted_grants.get(external.grant_id)
        if (
            grant is None
            or authority.hierarchies.get(key) != distributed
            or authority.authority_id
            != candidate.trusted_distributed_closure_authority_id
            or authority.security_epoch
            != candidate.trusted_distributed_closure_security_epoch
            or authority.producer_credential
            is not candidate.trusted_distributed_closure_authority_credential
            or external.state is not DistributedClosureState.TERMINAL
            or _distributed_binding(external)
            != _expected_distributed_binding(candidate, grant)
        ):
            raise Reject()
        fact = AcceptedGrantClosureFact(
            grant_id=grant.grant_id,
            stable_key=grant.stable_key,
            live_session_epoch=grant.live_session_epoch,
            source_authority_id=candidate.source_authority_id,
            source_index_incarnation=candidate.index.source_index_incarnation,
            accepted_source_security_epoch=grant.source_security_epoch,
            closure_source_security_epoch=candidate.index.source_security_epoch,
            plant_profile_digest=grant.plant_profile_digest,
            acceptance_transport_verification_digest=(
                grant.acceptance_transport_verification_digest
            ),
            acceptance_receipt_digest=grant.acceptance_receipt_digest,
            distributed_closure=distributed,
        )
        hierarchy = ProtectedGrantClosure(
            fact,
            candidate.producer_credential,
            _protect(
                "accepted-grant-distributed-closure",
                fact,
                audience_purpose="SOURCE_ACCEPTED_GRANT_CLOSURE_IMPORT",
                verification_class="CURRENT_SOURCE_AUTHORITY_PROTECTED_CLOSURE",
            ),
        )
        _validate_grant_closure(
            hierarchy,
            expected_credential=candidate.producer_credential,
            expected_distributed_credential=(
                candidate.trusted_distributed_closure_authority_credential
            ),
        )
        prior = candidate.generations.closure_evidence_hierarchies.get(grant.grant_id)
        if prior is not None and prior != hierarchy:
            raise Reject()
        receipt = _grant_closure_receipt(candidate, grant, hierarchy)
        if grant.closure_receipt is not None:
            if grant.closure_receipt != receipt:
                raise Reject()
            return grant.closure_receipt
        candidate.generations.closure_evidence_hierarchies[grant.grant_id] = hierarchy
        grant.closure_receipt = receipt
        return receipt

    result = _atomic(source, mutate, _validate_source)
    return _require_result_type(result, ProtectedAcceptedGrantClosureReceipt)


def source_freeze(source: Source) -> ClosureBundle:
    def mutate(candidate: Source) -> ClosureBundle:
        _validate_source(candidate)
        if candidate.index.phase is SourceIndexPhase.FROZEN:
            if candidate.closure_hierarchy is None:
                raise Reject()
            return candidate.closure_hierarchy.bundle
        if (
            candidate.index.availability_profile is ANCHOR_PROFILE
            and candidate.index.anchor_allocation_binding is None
        ):
            raise Reject()
        if candidate.in_flight_exposure:
            raise Reject()
        for slot in candidate.generations.slots.values():
            if slot.state is SlotState.AVAILABLE:
                raise Reject()
            if slot.state is SlotState.CONSUMED_BY_ACCEPTED_REQUEST:
                grant = candidate.generations.accepted_grants.get(
                    slot.accepted_grant_id or ""
                )
                if grant is None or grant.closure_receipt is None:
                    raise Reject()
        if any(
            record.state is not QueueRecordState.TERMINALIZED
            for record in candidate.queue.records.values()
        ):
            raise Reject()
        tree = SparseMerkleTree(
            ProofContext.SOURCE,
            {
                key: source_entry_bytes(entry)
                for key, entry in candidate.index.entries.items()
            },
        )
        for admission in candidate.index.root_admissions.values():
            if admission.phase is RootAdmissionPhase.PENDING:
                admission.phase = RootAdmissionPhase.FROZEN_PENDING
        candidate.index.phase = SourceIndexPhase.FROZEN
        candidate.index.frozen_root = tree.root
        candidate.index.frozen_audience = tuple(sorted(candidate.index.eligible_roots))
        bundle = ClosureBundle(
            source_namespace=candidate.index.source_namespace,
            availability_profile=candidate.index.availability_profile,
            context=ProofContext.SOURCE,
            root=tree.root,
            audience=candidate.index.frozen_audience,
            origin=ClosureOrigin.SOURCE,
        )
        enrollment_ancestry_digest = _object_digest(
            tuple(
                sorted(
                    (audience_key, _object_digest(hierarchy))
                    for audience_key, hierarchy in (
                        candidate.index.enrollment_hierarchies.items()
                    )
                )
            )
        )
        candidate.closure_hierarchy = _build_closure(
            bundle,
            producer_kind="SOURCE",
            producer_authority_id=candidate.source_authority_id,
            producer_security_epoch=candidate.index.source_security_epoch,
            enrollment_ancestry_digest=enrollment_ancestry_digest,
            producer_credential=candidate.producer_credential,
        )
        return bundle

    result = _atomic(source, mutate, _validate_source)
    return _require_result_type(result, ClosureBundle)


def _retirement_projection(
    source: Source, no_successor_hierarchy: ProtectedNoSuccessor
) -> CooperativeSourceRetirementProjection:
    binding = source.index.anchor_allocation_binding
    if (
        source.index.phase is not SourceIndexPhase.FROZEN
        or source.index.availability_profile is not ANCHOR_PROFILE
        or binding is None
        or binding.source_namespace != source.index.source_namespace
        or source.index.frozen_root is None
        or any(
            grant.closure_receipt is None
            for grant in source.generations.accepted_grants.values()
        )
    ):
        raise Reject()
    prefix = (
        source.index.source_namespace[2]
        + "|"
        + binding.anchor_authority
        + "|"
        + binding.anchor_selector_incarnation
        + "|"
        + binding.reservation_id
        + "|"
        + binding.allocation_id
        + "|"
        + source.index.frozen_root.hex()
    )
    return CooperativeSourceRetirementProjection(
        source_namespace=source.index.source_namespace,
        anchor_authority=binding.anchor_authority,
        anchor_selector_incarnation=binding.anchor_selector_incarnation,
        reservation_id=binding.reservation_id,
        allocation_id=binding.allocation_id,
        availability_profile=source.index.availability_profile,
        frozen_source_index_root=source.index.frozen_root,
        source_retirement_receipt_digest=_fixture_digest(
            prefix + "|source-retirement-receipt"
        ),
        source_index_closure_receipt_digest=_fixture_digest(
            prefix + "|source-index-closure-receipt"
        ),
        accepted_grant_closure_inventory_digest=_object_digest(
            tuple(
                sorted(
                    (grant_id, grant.closure_receipt)
                    for grant_id, grant in source.generations.accepted_grants.items()
                )
            )
        ),
        no_successor_evidence_digest=_object_digest(no_successor_hierarchy),
    )


def source_retirement_producer_inventory(
    source: Source, no_successor_hierarchy: ProtectedNoSuccessor | None = None
) -> RetirementInventory:
    _validate_source(source)
    _validate_closed_graph(no_successor_hierarchy)
    if source.index.phase is not SourceIndexPhase.FROZEN:
        raise Reject()
    family_kinds: list[str] = []
    if source.index.frozen_audience:
        family_kinds.append("OBSERVER_NAMESPACE_CLOSURE")
    if source.index.availability_profile is ANCHOR_PROFILE:
        family_kinds.append(_ANCHOR_RETIREMENT)
    if not family_kinds:
        return RetirementInventory((), None, None)
    if source.closure_hierarchy is None:
        raise Reject()
    family_tuple = tuple(family_kinds)
    closure_hierarchy_digest = _object_digest(source.closure_hierarchy)
    if source.index.availability_profile is ANCHOR_PROFILE:
        if no_successor_hierarchy is None:
            raise Reject()
        projection = _retirement_projection(source, no_successor_hierarchy)
        chain = _protection_digests(
            "cooperative-source-retirement",
            (
                projection,
                family_tuple,
                source.index.frozen_audience,
                closure_hierarchy_digest,
                source.source_authority_id,
                source.index.source_index_incarnation,
                source.index.source_security_epoch,
                no_successor_hierarchy,
                "SOURCE_NAMESPACE_COOPERATIVE_RETIREMENT",
                _TOMBSTONE,
            ),
        )
        return RetirementInventory(
            family_kinds=family_tuple,
            pre_manifest_digest=chain[2],
            producer_completion_digest=chain[3],
        )
    chain = _protection_digests(
        "source-retirement-output-inventory",
        (
            source.index.source_namespace,
            source.source_authority_id,
            source.index.source_security_epoch,
            source.index.frozen_root,
            source.index.frozen_audience,
            family_tuple,
            closure_hierarchy_digest,
        ),
    )
    return RetirementInventory(
        family_kinds=family_tuple,
        pre_manifest_digest=chain[2],
        producer_completion_digest=chain[3],
    )


def source_build_cooperative_retirement_hierarchy(
    source: Source,
    lineage_authority: LineageStore,
    no_successor_hierarchy: ProtectedNoSuccessor,
) -> ProtectedRetirement:
    _validate_source(source)
    _validate_lineage(lineage_authority)
    if (
        lineage_authority.producer_credential
        is not source.trusted_lineage_authority_credential
        or lineage_authority.terminal_hierarchies.get(source.index.source_namespace)
        != no_successor_hierarchy
    ):
        raise Reject()
    projection = _retirement_projection(source, no_successor_hierarchy)
    inventory = source_retirement_producer_inventory(source, no_successor_hierarchy)
    if (
        _ANCHOR_RETIREMENT not in inventory.family_kinds
        or inventory.pre_manifest_digest is None
        or inventory.producer_completion_digest is None
    ):
        raise Reject()
    if source.closure_hierarchy is None:
        raise Reject()
    closure_hierarchy_digest = _object_digest(source.closure_hierarchy)
    (
        envelope_digest,
        family_manifest_digest,
        pre_manifest_digest,
        producer_completion_digest,
        delivery_capsule_digest,
        audience_proof_digest,
        manifest_proof_digest,
        delivery_verification_digest,
    ) = _protection_digests(
        "cooperative-source-retirement",
        (
            projection,
            inventory.family_kinds,
            source.index.frozen_audience,
            closure_hierarchy_digest,
            source.source_authority_id,
            source.index.source_index_incarnation,
            source.index.source_security_epoch,
            no_successor_hierarchy,
            "SOURCE_NAMESPACE_COOPERATIVE_RETIREMENT",
            _TOMBSTONE,
        ),
    )
    if (
        inventory.pre_manifest_digest != pre_manifest_digest
        or inventory.producer_completion_digest != producer_completion_digest
    ):
        raise Reject()
    hierarchy = ProtectedRetirement(
        projection=projection,
        family_kinds=inventory.family_kinds,
        closure_audience=source.index.frozen_audience,
        source_closure_hierarchy_digest=closure_hierarchy_digest,
        source_authority_id=source.source_authority_id,
        source_index_incarnation=source.index.source_index_incarnation,
        source_security_epoch=source.index.source_security_epoch,
        no_successor_hierarchy=no_successor_hierarchy,
        producer_credential=source.producer_credential,
        audience_purpose="SOURCE_NAMESPACE_COOPERATIVE_RETIREMENT",
        verification_class=_TOMBSTONE,
        envelope_digest=envelope_digest,
        family_manifest_digest=family_manifest_digest,
        pre_manifest_digest=pre_manifest_digest,
        producer_completion_digest=producer_completion_digest,
        delivery_capsule_digest=delivery_capsule_digest,
        audience_proof_digest=audience_proof_digest,
        manifest_proof_digest=manifest_proof_digest,
        delivery_verification_digest=delivery_verification_digest,
    )
    _validate_retirement(
        hierarchy,
        expected_source_credential=source.producer_credential,
        expected_lineage_credential=source.trusted_lineage_authority_credential,
    )

    def retain(candidate: Source) -> ProtectedRetirement:
        if (
            candidate.index.phase is not SourceIndexPhase.FROZEN
            or candidate.closure_hierarchy is None
            or hierarchy.source_closure_hierarchy_digest
            != _object_digest(candidate.closure_hierarchy)
        ):
            raise Reject()
        prior = candidate.cooperative_retirement_hierarchy
        if prior is not None:
            if prior != hierarchy:
                raise Reject()
            return prior
        candidate.cooperative_retirement_hierarchy = hierarchy
        return hierarchy

    result = _atomic(source, retain, _validate_source)
    return _require_result_type(result, ProtectedRetirement)


REQUIRED_ISOLATION_SURFACES = (
    "BODY_OR_PLANT_ACTUATOR_AUTHORITY",
    "CHALLENGE_SIGNING_PUBLICATION_AND_DELIVERY",
    "DERIVED_AUTHORITY_CONSUMER",
    "GRANT_SIGNING_REGISTRY_AND_RETRY",
    "REPLICA_BACKUP_RESTORE_AND_RECOVERY",
    "REQUEST_INGRESS_VALIDATION_AND_ACCEPTANCE",
    "RESTART_SUCCESSOR_AND_ALTERNATE_BOOTSTRAP",
    "SOURCE_GENERATION_FRESHNESS_AND_GRANT_REGISTRIES",
    "SOURCE_LINEAGE_NAMESPACE_AND_INDEX",
)


def _validate_isolation_surface(store: IsolationSurface) -> None:
    if store.surface_kind not in REQUIRED_ISOLATION_SURFACES:
        raise Reject()
    for value in (store.authority_id, store.registry_incarnation, store.security_epoch):
        _identifier(value)
    if len(store.receipts) > MAX_PRODUCER_NAMESPACES:
        raise Reject()
    for namespace, receipt in store.receipts.items():
        if (
            receipt.source_namespace != namespace
            or receipt.surface_kind != store.surface_kind
            or receipt.authority_id != store.authority_id
            or receipt.registry_incarnation != store.registry_incarnation
            or receipt.security_epoch != store.security_epoch
            or receipt.producer_credential is not store.producer_credential
            or receipt.terminal_receipt_digest
            != _fixture_digest(
                "isolation-surface-terminal|"
                + repr(
                    (
                        namespace,
                        store.surface_kind,
                        store.authority_id,
                        store.registry_incarnation,
                        store.security_epoch,
                    )
                )
            )
        ):
            raise Reject()


def isolation_surface_finalize(
    store: IsolationSurface, namespace: tuple[str, str, str]
) -> IsolationReceipt:
    def mutate(candidate: IsolationSurface) -> IsolationReceipt:
        _validate_namespace(namespace)
        prior = candidate.receipts.get(namespace)
        if prior is not None:
            return prior
        receipt = IsolationReceipt(
            namespace,
            candidate.surface_kind,
            candidate.authority_id,
            candidate.registry_incarnation,
            candidate.security_epoch,
            _fixture_digest(
                "isolation-surface-terminal|"
                + repr(
                    (
                        namespace,
                        candidate.surface_kind,
                        candidate.authority_id,
                        candidate.registry_incarnation,
                        candidate.security_epoch,
                    )
                )
            ),
            candidate.producer_credential,
        )
        candidate.receipts[namespace] = receipt
        return receipt

    result = _atomic(store, mutate, _validate_isolation_surface)
    return _require_result_type(result, IsolationReceipt)


def _isolation_value(hierarchy: ProtectedIsolation) -> tuple[object, ...]:
    return (
        hierarchy.evidence,
        hierarchy.authority_id,
        hierarchy.registry_incarnation,
        hierarchy.security_epoch,
        hierarchy.security_epoch_sequence,
        hierarchy.surface_terminal_receipts,
    )


def _validate_isolation(
    hierarchy: ProtectedIsolation,
    *,
    expected_credential: OpaqueHigherRootIsolationCredential,
) -> None:
    evidence = hierarchy.evidence
    expected_surfaces = tuple(sorted(REQUIRED_ISOLATION_SURFACES))
    receipt_surfaces = tuple(
        receipt.surface_kind for receipt in hierarchy.surface_terminal_receipts
    )
    _validate_namespace(evidence.source_namespace)
    if (
        hierarchy.producer_credential is not expected_credential
        or hierarchy.security_epoch_sequence <= 0
        or evidence.surface_kinds != expected_surfaces
        or receipt_surfaces != expected_surfaces
        or len(set(receipt_surfaces)) != len(receipt_surfaces)
        or any(
            receipt.source_namespace != evidence.source_namespace
            or not _complete_digest_set((receipt.terminal_receipt_digest,))
            for receipt in hierarchy.surface_terminal_receipts
        )
    ):
        raise Reject()
    _validate_protection(
        hierarchy.protection,
        domain="higher-root-permanent-isolation",
        semantic_value=_isolation_value(hierarchy),
        audience_purpose="INDEPENDENT_ANCHOR_PERMANENT_SOURCE_ISOLATION",
        verification_class="HIGHER_ROOT_IRREVERSIBLE_TERMINAL_EVIDENCE",
    )


def _validate_isolation_authority(store: IsolationAuthority) -> None:
    if (
        store.producer_credential is not _CONFIGURED_HIGHER_ROOT_ISOLATION_CREDENTIAL
        or store.security_epoch_sequence <= 0
        or len(store.hierarchies) > MAX_PRODUCER_NAMESPACES
    ):
        raise Reject()
    for value in (store.authority_id, store.registry_incarnation, store.security_epoch):
        _identifier(value)
    for namespace, hierarchy in store.hierarchies.items():
        _validate_isolation(hierarchy, expected_credential=store.producer_credential)
        if hierarchy.evidence.source_namespace != namespace:
            raise Reject()
        if (
            hierarchy.authority_id != store.authority_id
            or hierarchy.registry_incarnation != store.registry_incarnation
            or hierarchy.security_epoch != store.security_epoch
            or hierarchy.security_epoch_sequence != store.security_epoch_sequence
        ):
            raise Reject()


def higher_root_publish_isolation(
    store: IsolationAuthority,
    evidence: IsolationEvidence,
    surface_inputs: tuple[tuple[IsolationSurface, IsolationReceipt], ...],
) -> ProtectedIsolation:
    def mutate(candidate: IsolationAuthority) -> ProtectedIsolation:
        if (
            candidate.producer_credential
            is not _CONFIGURED_HIGHER_ROOT_ISOLATION_CREDENTIAL
        ):
            raise Reject()
        receipts: list[IsolationReceipt] = []
        for surface_store, receipt in surface_inputs:
            _validate_isolation_surface(surface_store)
            if (
                surface_store.receipts.get(evidence.source_namespace) != receipt
                or receipt.producer_credential is not surface_store.producer_credential
            ):
                raise Reject()
            receipts.append(receipt)
        receipt_tuple = tuple(sorted(receipts, key=lambda value: value.surface_kind))
        provisional = ProtectedIsolation(
            evidence=evidence,
            authority_id=candidate.authority_id,
            registry_incarnation=candidate.registry_incarnation,
            security_epoch=candidate.security_epoch,
            security_epoch_sequence=candidate.security_epoch_sequence,
            surface_terminal_receipts=receipt_tuple,
            producer_credential=candidate.producer_credential,
            protection=EMPTY_PROTECTION,
        )
        hierarchy = replace(
            provisional,
            protection=_protect(
                "higher-root-permanent-isolation",
                _isolation_value(provisional),
                audience_purpose=("INDEPENDENT_ANCHOR_PERMANENT_SOURCE_ISOLATION"),
                verification_class=("HIGHER_ROOT_IRREVERSIBLE_TERMINAL_EVIDENCE"),
            ),
        )
        _validate_isolation(
            hierarchy, expected_credential=candidate.producer_credential
        )
        prior = candidate.hierarchies.get(evidence.source_namespace)
        if prior is not None:
            if prior != hierarchy:
                raise Reject()
            return prior
        candidate.hierarchies[evidence.source_namespace] = hierarchy
        return hierarchy

    result = _atomic(store, mutate, _validate_isolation_authority)
    return _require_result_type(result, ProtectedIsolation)


def _isolation_digest(
    anchor: Anchor, authority: IsolationAuthority, hierarchy: ProtectedIsolation
) -> str:
    _validate_isolation_authority(authority)
    _validate_isolation(
        hierarchy, expected_credential=anchor.trusted_isolation_authority_credential
    )
    evidence = hierarchy.evidence
    if evidence.source_namespace != anchor.source_namespace:
        raise Reject()
    if (
        authority.producer_credential
        is not anchor.trusted_isolation_authority_credential
        or hierarchy.authority_id != anchor.trusted_isolation_authority_id
        or hierarchy.registry_incarnation
        != anchor.trusted_isolation_registry_incarnation
        or hierarchy.security_epoch_sequence
        < anchor.minimum_isolation_security_epoch_sequence
        or authority.hierarchies.get(evidence.source_namespace) != hierarchy
    ):
        raise Reject()
    return _object_digest(hierarchy)


def _retirement_digest(hierarchy: ProtectedRetirement) -> str:
    return hashlib.sha256(repr(hierarchy).encode("utf-8")).hexdigest()


def _anchor_ancestry_digest(anchor: Anchor) -> str:
    return _object_digest(
        tuple(
            sorted(
                (
                    audience_key,
                    _object_digest(hierarchy),
                    _notification_digest(anchor.enrollment_notifications[audience_key]),
                )
                for audience_key, hierarchy in (
                    anchor.enrollment_eligibility_hierarchies.items()
                )
            )
        )
    )


def _retain_anchor_closure(anchor: Anchor, bundle: ClosureBundle) -> None:
    hierarchy = _build_closure(
        bundle,
        producer_kind="ANCHOR",
        producer_authority_id=anchor.anchor_authority,
        producer_security_epoch=anchor.anchor_security_epoch,
        enrollment_ancestry_digest=_anchor_ancestry_digest(anchor),
        producer_credential=anchor.producer_credential,
    )
    if anchor.closure_hierarchy is not None and anchor.closure_hierarchy != hierarchy:
        raise Reject()
    anchor.closure_hierarchy = hierarchy


def anchor_finalize_cooperative_source_retirement(
    anchor: Anchor,
    namespace_registry: AuthorityRegistry,
    source: Source,
    hierarchy: ProtectedRetirement,
) -> ClosureBundle:
    def mutate(candidate: Anchor, candidate_registry: AnchorRegistry) -> ClosureBundle:
        _validate_retirement(
            hierarchy,
            expected_source_credential=candidate_registry.trusted_source_producer_credential,
            expected_lineage_credential=candidate.trusted_lineage_authority_credential,
        )
        projection = hierarchy.projection
        hierarchy_digest = _retirement_digest(hierarchy)
        terminalization_receipt = "anchor-cooperative-final:" + hierarchy_digest
        if candidate.phase is AnchorPhase.FROZEN:
            if (
                candidate.first_closure_cause is not AnchorClosureCause.COOPERATIVE
                or candidate.cooperative_retirement_digest != hierarchy_digest
                or candidate.frozen_root is None
                or candidate_registry.state is not AnchorBootstrap.FROZEN
                or candidate_registry.source_closure_terminal_cause != _COOPERATIVE
                or candidate_registry.source_closure_finalization_receipt
                != terminalization_receipt
            ):
                raise Reject()
            bundle = ClosureBundle(
                source_namespace=candidate.source_namespace,
                availability_profile=projection.availability_profile,
                context=ProofContext.ANCHOR,
                root=candidate.frozen_root,
                audience=candidate.frozen_audience,
                origin=ClosureOrigin.ANCHOR,
                anchor_closure_cause=AnchorClosureCause.COOPERATIVE,
            )
            _retain_anchor_closure(candidate, bundle)
            return bundle
        if (
            candidate.phase is not AnchorPhase.OPEN
            or candidate.in_flight_mutations
            or source.cooperative_retirement_hierarchy != hierarchy
            or candidate.trusted_source_coordinate
            != (
                source.source_authority_id,
                source.index.source_index_incarnation,
                source.index.source_security_epoch,
                source.producer_credential,
            )
            or hierarchy.source_authority_id != source.source_authority_id
            or hierarchy.source_index_incarnation
            != source.index.source_index_incarnation
            or hierarchy.source_security_epoch != source.index.source_security_epoch
            or source.closure_hierarchy is None
            or hierarchy.source_closure_hierarchy_digest
            != _object_digest(source.closure_hierarchy)
            or projection.source_namespace != candidate.source_namespace
            or projection.anchor_authority != candidate.anchor_authority
            or projection.availability_profile is not ANCHOR_PROFILE
            or candidate_registry.state is not AnchorBootstrap.OPEN
            or candidate_registry.reservation_state is not ReservationState.MATERIALIZED
            or candidate_registry.allocation is None
            or projection.anchor_selector_incarnation
            != candidate_registry.allocation.anchor_selector_incarnation
            or projection.reservation_id
            != candidate_registry.allocation.anchor_reservation.reservation_id
            or projection.allocation_id != candidate_registry.allocation.allocation_id
        ):
            raise Reject()
        charge_before = _reservation_charge(candidate_registry)
        tree = SparseMerkleTree(
            ProofContext.ANCHOR,
            {
                key: anchor_entry_bytes(entry)
                for key, entry in candidate.entries.items()
            },
        )
        candidate.phase = AnchorPhase.FROZEN
        candidate.cooperative_retirement_digest = hierarchy_digest
        candidate.closure_evidence_state = AnchorEvidenceState.COOPERATIVE_ONLY
        candidate.first_closure_cause = AnchorClosureCause.COOPERATIVE
        candidate.reservation_terminal_cause = _COOPERATIVE
        candidate.frozen_root = tree.root
        candidate.frozen_audience = tuple(sorted(candidate.eligible_roots))
        candidate_registry.state = AnchorBootstrap.FROZEN
        candidate_registry.reservation_state = ReservationState.TERMINAL
        candidate_registry.source_closure_terminal_cause = _COOPERATIVE
        candidate_registry.source_closure_finalization_receipt = terminalization_receipt
        candidate_registry.eligible_root_count = len(candidate.eligible_roots)
        candidate_registry.challenge_entry_count = len(candidate.entries)
        candidate_registry.admission_count = len(candidate.relay_hierarchies)
        candidate_registry.in_flight_count = len(candidate.in_flight_mutations)
        if _reservation_charge(candidate_registry) != charge_before:
            raise Reject()
        bundle = ClosureBundle(
            source_namespace=candidate.source_namespace,
            availability_profile=projection.availability_profile,
            context=ProofContext.ANCHOR,
            root=tree.root,
            audience=candidate.frozen_audience,
            origin=ClosureOrigin.ANCHOR,
            anchor_closure_cause=AnchorClosureCause.COOPERATIVE,
        )
        _retain_anchor_closure(candidate, bundle)
        return bundle

    result = _atomic_anchor_transition(anchor, namespace_registry, mutate)
    return _require_result_type(result, ClosureBundle)


def anchor_freeze(
    anchor: Anchor,
    namespace_registry: AuthorityRegistry,
    isolation_authority: IsolationAuthority,
    isolation_hierarchy: ProtectedIsolation,
) -> ClosureBundle:
    def mutate(candidate: Anchor, candidate_registry: AnchorRegistry) -> ClosureBundle:
        isolation_digest = _isolation_digest(
            candidate, isolation_authority, isolation_hierarchy
        )
        terminalization_receipt = "anchor-isolation-final:" + isolation_digest
        if candidate.phase is AnchorPhase.FROZEN:
            if (
                candidate.first_closure_cause is not AnchorClosureCause.ISOLATION
                or candidate.isolation_digest != isolation_digest
                or candidate.frozen_root is None
                or candidate_registry.state is not AnchorBootstrap.FROZEN
                or candidate_registry.source_closure_terminal_cause != _ISOLATED
                or candidate_registry.source_closure_finalization_receipt
                != terminalization_receipt
            ):
                raise Reject()
            bundle = ClosureBundle(
                source_namespace=candidate.source_namespace,
                availability_profile=(ANCHOR_PROFILE),
                context=ProofContext.ANCHOR,
                root=candidate.frozen_root,
                audience=candidate.frozen_audience,
                origin=ClosureOrigin.ANCHOR,
                anchor_closure_cause=AnchorClosureCause.ISOLATION,
            )
            _retain_anchor_closure(candidate, bundle)
            return bundle
        if candidate.in_flight_mutations:
            raise Reject()
        if (
            candidate.phase is not AnchorPhase.OPEN
            or candidate_registry.state is not AnchorBootstrap.OPEN
            or candidate_registry.reservation_state is not ReservationState.MATERIALIZED
        ):
            raise Reject()
        charge_before = _reservation_charge(candidate_registry)
        tree = SparseMerkleTree(
            ProofContext.ANCHOR,
            {
                key: anchor_entry_bytes(entry)
                for key, entry in candidate.entries.items()
            },
        )
        candidate.phase = AnchorPhase.FROZEN
        candidate.isolation_digest = isolation_digest
        candidate.closure_evidence_state = AnchorEvidenceState.ISOLATION_ONLY
        candidate.first_closure_cause = AnchorClosureCause.ISOLATION
        candidate.reservation_terminal_cause = _ISOLATED
        candidate.frozen_root = tree.root
        candidate.frozen_audience = tuple(sorted(candidate.eligible_roots))
        candidate_registry.state = AnchorBootstrap.FROZEN
        candidate_registry.reservation_state = ReservationState.TERMINAL
        candidate_registry.source_closure_terminal_cause = _ISOLATED
        candidate_registry.source_closure_finalization_receipt = terminalization_receipt
        candidate_registry.eligible_root_count = len(candidate.eligible_roots)
        candidate_registry.challenge_entry_count = len(candidate.entries)
        candidate_registry.admission_count = len(candidate.relay_hierarchies)
        candidate_registry.in_flight_count = len(candidate.in_flight_mutations)
        if _reservation_charge(candidate_registry) != charge_before:
            raise Reject()
        bundle = ClosureBundle(
            source_namespace=candidate.source_namespace,
            availability_profile=(ANCHOR_PROFILE),
            context=ProofContext.ANCHOR,
            root=tree.root,
            audience=candidate.frozen_audience,
            origin=ClosureOrigin.ANCHOR,
            anchor_closure_cause=AnchorClosureCause.ISOLATION,
        )
        _retain_anchor_closure(candidate, bundle)
        return bundle

    result = _atomic_anchor_transition(anchor, namespace_registry, mutate)
    return _require_result_type(result, ClosureBundle)


def anchor_refine_terminal_source_closure_evidence(
    anchor: Anchor,
    namespace_registry: AuthorityRegistry,
    *,
    cooperative_source: Source | None = None,
    cooperative_hierarchy: (ProtectedRetirement | None) = None,
    isolation_authority: IsolationAuthority | None = None,
    isolation_hierarchy: ProtectedIsolation | None = None,
) -> str:
    def mutate(candidate: Anchor, candidate_registry: AnchorRegistry) -> str:
        if candidate.phase is not AnchorPhase.FROZEN:
            raise Reject()
        cooperative_supplied = (
            cooperative_source is not None and cooperative_hierarchy is not None
        )
        isolation_supplied = (
            isolation_authority is not None and isolation_hierarchy is not None
        )
        if (cooperative_source is None) != (cooperative_hierarchy is None):
            raise Reject()
        if (isolation_authority is None) != (isolation_hierarchy is None):
            raise Reject()
        supplied = int(cooperative_supplied) + int(isolation_supplied)
        if supplied != 1:
            raise Reject()
        if cooperative_hierarchy is not None:
            if cooperative_source is None:
                raise Reject()
            _validate_retirement(
                cooperative_hierarchy,
                expected_source_credential=candidate_registry.trusted_source_producer_credential,
                expected_lineage_credential=candidate.trusted_lineage_authority_credential,
            )
            projection = cooperative_hierarchy.projection
            digest = _retirement_digest(cooperative_hierarchy)
            if (
                projection.source_namespace != candidate.source_namespace
                or projection.anchor_authority != candidate.anchor_authority
                or cooperative_source.cooperative_retirement_hierarchy
                != cooperative_hierarchy
                or candidate.trusted_source_coordinate
                != (
                    cooperative_source.source_authority_id,
                    cooperative_source.index.source_index_incarnation,
                    cooperative_source.index.source_security_epoch,
                    cooperative_source.producer_credential,
                )
                or cooperative_hierarchy.source_authority_id
                != cooperative_source.source_authority_id
                or cooperative_hierarchy.source_index_incarnation
                != cooperative_source.index.source_index_incarnation
                or cooperative_hierarchy.source_security_epoch
                != cooperative_source.index.source_security_epoch
            ):
                raise Reject()
            if candidate.cooperative_retirement_digest is not None:
                if candidate.cooperative_retirement_digest != digest:
                    raise Reject()
                return "anchor-closure-refinement:" + digest
            if (
                candidate.closure_evidence_state
                is not AnchorEvidenceState.ISOLATION_ONLY
            ):
                raise Reject()
            candidate.cooperative_retirement_digest = digest
        else:
            if isolation_authority is None or isolation_hierarchy is None:
                raise Reject()
            digest = _isolation_digest(
                candidate, isolation_authority, isolation_hierarchy
            )
            if candidate.isolation_digest is not None:
                if candidate.isolation_digest != digest:
                    raise Reject()
                return "anchor-closure-refinement:" + digest
            if (
                candidate.closure_evidence_state
                is not AnchorEvidenceState.COOPERATIVE_ONLY
            ):
                raise Reject()
            candidate.isolation_digest = digest
        candidate.closure_evidence_state = AnchorEvidenceState.COOPERATIVE_AND_ISOLATION
        return "anchor-closure-refinement:" + digest

    return _require_result_type(
        _atomic_anchor_transition(anchor, namespace_registry, mutate), str
    )


def source_resolution_tree(source: Source) -> SparseMerkleTree:
    _validate_source(source)
    if source.index.phase is not SourceIndexPhase.FROZEN:
        raise Reject()
    tree = SparseMerkleTree(
        ProofContext.SOURCE,
        {key: source_entry_bytes(entry) for key, entry in source.index.entries.items()},
    )
    if tree.root != source.index.frozen_root:
        raise Reject()
    return tree


def anchor_resolution_tree(anchor: Anchor) -> SparseMerkleTree:
    _validate_anchor(anchor)
    if anchor.phase is not AnchorPhase.FROZEN:
        raise Reject()
    tree = SparseMerkleTree(
        ProofContext.ANCHOR,
        {key: anchor_entry_bytes(entry) for key, entry in anchor.entries.items()},
    )
    if tree.root != anchor.frozen_root:
        raise Reject()
    return tree


def _json_digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()


def _operation_digest(operation: LocalOperation) -> str:
    return _json_digest(
        {
            "exact_terminal_evidence_pending": (
                operation.exact_terminal_evidence_pending
            ),
            "resolution_outcome": operation.resolution_outcome.value,
            "stable_key_digest": stable_key_digest(operation.stable_key).hex(),
            "state": operation.state.value,
            "verified_request_attempt_present": (
                operation.verified_request_attempt_present
            ),
        }
    )


def _observer_ancestry_digest(hierarchy: ProtectedEnrollment) -> str:
    _validate_enrollment(hierarchy)
    return _object_digest(hierarchy)


def _bundle_digest(bundle: ClosureBundle) -> str:
    return _json_digest(
        {
            "anchor_closure_cause": bundle.anchor_closure_cause.value,
            "audience": [list(member) for member in bundle.audience],
            "availability_profile": bundle.availability_profile.value,
            "context": bundle.context.value,
            "origin": bundle.origin.value,
            "root": bundle.root.hex(),
            "source_namespace": list(bundle.source_namespace),
        }
    )


def _proof_digest(resolution: ResolutionProof) -> str:
    return _json_digest(
        {
            "anchor_entry_digest": (
                None
                if resolution.anchor_entry is None
                else hashlib.sha256(
                    anchor_entry_bytes(resolution.anchor_entry)
                ).hexdigest()
            ),
            "body_digest": hashlib.sha256(resolution.body).hexdigest(),
            "claimed_outcome": resolution.claimed_outcome.value,
            "proof_kind": resolution.proof_kind.value,
            "source_entry_digest": (
                None
                if resolution.source_entry is None
                else hashlib.sha256(
                    source_entry_bytes(resolution.source_entry)
                ).hexdigest()
            ),
        }
    )


def _import_request_digest(
    bundle: ClosureBundle, resolutions: dict[StableKey, ResolutionProof]
) -> str:
    return _json_digest(
        {
            "bundle_digest": _bundle_digest(bundle),
            "resolution_partition": [
                {
                    "resolution_proof_digest": _proof_digest(resolutions[key]),
                    "stable_key_digest": stable_key_digest(key).hex(),
                }
                for key in sorted(resolutions, key=stable_key_bytes)
            ],
        }
    )


def _partition_digest(partition: tuple[ClosureOperationPartitionEntry, ...]) -> str:
    return _json_digest(
        [
            {
                "installed_operation_digest": entry.installed_operation_digest,
                "kind": entry.kind.value,
                "prior_operation_digest": entry.prior_operation_digest,
                "resolution_proof_digest": entry.resolution_proof_digest,
                "stable_key_digest": stable_key_digest(entry.stable_key).hex(),
            }
            for entry in partition
        ]
    )


def _import_receipt_digest(
    origin: ClosureOrigin, request_digest: str, partition_digest: str
) -> str:
    return _json_digest(
        {
            "installed_partition_digest": partition_digest,
            "origin": origin.value,
            "request_digest": request_digest,
        }
    )


def _validate_observer(observer: ObserverLocalStore) -> None:
    _validate_closed_graph(observer)
    _identifier(observer.observer_root_id)
    _identifier(observer.observer_root_incarnation)
    if (
        not 1 <= observer.operation_capacity <= MAX_OBSERVER_OPERATIONS
        or not 1 <= observer.enrollment_capacity <= MAX_OBSERVER_ENROLLMENTS
        or not 1 <= observer.tombstone_capacity <= MAX_OBSERVER_TOMBSTONES
    ):
        raise Reject()
    if (
        len(observer.operations) > observer.operation_capacity
        or len(observer.enrollments) > observer.enrollment_capacity
        or len(observer.trusted_producer_coordinates) > observer.enrollment_capacity
        or len(observer.closure_tombstones) > observer.tombstone_capacity
        or len(
            repr(
                (
                    tuple(sorted(observer.enrollments)),
                    tuple(sorted(observer.closure_tombstones)),
                )
            ).encode("utf-8")
        )
        > MAX_OBSERVER_RETAINED_BYTES
    ):
        raise Reject()
    for namespace, (
        source_coordinate,
        anchor_coordinate,
    ) in observer.trusted_producer_coordinates.items():
        _validate_namespace(namespace)
        for value in source_coordinate[:3]:
            _identifier(value)
        if anchor_coordinate is not None:
            for value in anchor_coordinate[:3]:
                _identifier(value)
    for tombstone_key, tombstone in observer.closure_tombstones.items():
        roots = (tombstone.source_index_root, tombstone.anchor_root)
        if any(root is not None and len(root) != 32 for root in roots):
            raise Reject()
        expected_state = (
            ClosureEvidenceState.SOURCE_AND_ANCHOR
            if all(root is not None for root in roots)
            else (
                ClosureEvidenceState.SOURCE_ONLY
                if tombstone.source_index_root is not None
                else ClosureEvidenceState.ANCHOR_ONLY
            )
        )
        if (
            all(root is None for root in roots)
            or tombstone.evidence_state is not expected_state
            or tombstone_key
            != (tombstone.source_namespace, tombstone.observer_root_incarnation)
        ):
            raise Reject()
        enrollment = observer.enrollments.get(tombstone.source_namespace)
        enrollment_hierarchy = observer.enrollment_hierarchies.get(
            tombstone.source_namespace
        )
        if (
            enrollment is None
            or enrollment_hierarchy is None
            or enrollment.root_incarnation != tombstone.observer_root_incarnation
            or tombstone.enrollment_ancestry_digest
            != _observer_ancestry_digest(enrollment_hierarchy)
        ):
            raise Reject()
        origin_product = (
            (
                ClosureOrigin.SOURCE,
                tombstone.source_index_root,
                tombstone.source_import,
            ),
            (ClosureOrigin.ANCHOR, tombstone.anchor_root, tombstone.anchor_import),
        )
        for origin, root, record in origin_product:
            if (root is None) != (record is None):
                raise Reject()
            if record is None:
                continue
            record_digests = (
                record.bundle_digest,
                record.request_digest,
                record.installed_partition_digest,
                record.import_receipt_digest,
            )
            if (
                record.origin is not origin
                or not _complete_digest_set(record_digests)
                or record.import_receipt_digest
                != _import_receipt_digest(
                    origin, record.request_digest, record.installed_partition_digest
                )
            ):
                raise Reject()
        partition = tombstone.latest_complete_partition
        if (
            tuple(
                sorted(partition, key=lambda entry: stable_key_bytes(entry.stable_key))
            )
            != partition
        ):
            raise Reject()
        if tombstone.latest_complete_partition_digest != _partition_digest(
            partition
        ) or not _complete_digest_set(
            (
                tombstone.latest_complete_partition_digest,
                tombstone.latest_import_receipt_digest,
            )
        ):
            raise Reject()
        latest_records = [
            record
            for record in (tombstone.source_import, tombstone.anchor_import)
            if record is not None
            and record.import_receipt_digest == tombstone.latest_import_receipt_digest
            and record.installed_partition_digest
            == tombstone.latest_complete_partition_digest
        ]
        if len(latest_records) != 1:
            raise Reject()
        expected_operation_keys = {
            key
            for key in observer.operations
            if key.source_namespace == tombstone.source_namespace
        }
        if {entry.stable_key for entry in partition} != expected_operation_keys:
            raise Reject()
        for entry in partition:
            operation = observer.operations[entry.stable_key]
            if entry.installed_operation_digest != _operation_digest(
                operation
            ) or not _complete_digest_set(
                (entry.prior_operation_digest, entry.installed_operation_digest)
            ):
                raise Reject()
            if entry.kind is PRESERVE_CLOSED_HISTORY_PARTITION_KIND:
                if (
                    entry.prior_operation_digest != entry.installed_operation_digest
                    or entry.resolution_proof_digest is not None
                    or operation.state
                    is not OperationState.RESOLVED_WITHOUT_INSTALLATION
                ):
                    raise Reject()
            elif entry.resolution_proof_digest is None or not _complete_digest_set(
                (entry.resolution_proof_digest,)
            ):
                raise Reject()
            if (
                operation.state is OperationState.INTENT_PREPARED
                and not operation.exact_terminal_evidence_pending
            ):
                raise Reject()
    if set(observer.enrollments) != set(observer.enrollment_hierarchies):
        raise Reject()
    for namespace, enrollment in observer.enrollments.items():
        enrollment_hierarchy = observer.enrollment_hierarchies[namespace]
        _validate_enrollment(enrollment_hierarchy)
        if enrollment.root_id != observer.observer_root_id:
            raise Reject()
        if enrollment.root_incarnation != observer.observer_root_incarnation:
            raise Reject()
        if not enrollment.source_enrollment_hierarchy_digest:
            raise Reject()
        if (
            enrollment_hierarchy.source_namespace != namespace
            or enrollment_hierarchy.root != enrollment
            or namespace not in observer.trusted_producer_coordinates
        ):
            raise Reject()
    for key, operation in observer.operations.items():
        if operation.stable_key != key:
            raise Reject()
        if operation.state is OperationState.RESOLVED_WITHOUT_INSTALLATION:
            if (
                operation.resolution_outcome is ResolutionOutcome.UNRESOLVED
                or operation.exact_terminal_evidence_pending
            ):
                raise Reject()
        elif operation.state is OperationState.INTENT_PREPARED:
            expected = (
                ResolutionOutcome.PRESERVE_EXACT_TERMINAL
                if operation.exact_terminal_evidence_pending
                else ResolutionOutcome.UNRESOLVED
            )
            if operation.resolution_outcome is not expected:
                raise Reject()
        else:
            raise Reject()


def observer_configure_namespace_producers(
    observer: ObserverLocalStore, source: Source, anchor: Anchor | None
) -> None:
    def mutate(candidate: ObserverLocalStore) -> None:
        namespace = source.index.source_namespace
        coordinate = (
            (
                source.source_authority_id,
                source.index.source_index_incarnation,
                source.index.source_security_epoch,
                source.producer_credential,
            ),
            None
            if anchor is None
            else (
                anchor.anchor_authority,
                anchor.anchor_selector_incarnation,
                anchor.anchor_security_epoch,
                anchor.producer_credential,
            ),
        )
        prior = candidate.trusted_producer_coordinates.get(namespace)
        if prior is not None and prior != coordinate:
            raise Reject()
        if prior is None and len(candidate.trusted_producer_coordinates) >= (
            candidate.enrollment_capacity
        ):
            raise Reject()
        candidate.trusted_producer_coordinates[namespace] = coordinate

    _atomic(observer, mutate, _validate_observer)


def observer_install_enrollment(
    observer: ObserverLocalStore,
    source: Source,
    hierarchy: ProtectedEnrollment,
    *,
    anchor: Anchor | None = None,
) -> None:
    def mutate(candidate: ObserverLocalStore) -> None:
        _validate_enrollment(hierarchy)
        source_namespace = hierarchy.source_namespace
        root = hierarchy.root
        expected_coordinates = candidate.trusted_producer_coordinates.get(
            source_namespace
        )
        if (
            expected_coordinates is None
            or expected_coordinates[0]
            != (
                source.source_authority_id,
                source.index.source_index_incarnation,
                source.index.source_security_epoch,
                source.producer_credential,
            )
            or root.root_id != candidate.observer_root_id
            or root.root_incarnation != candidate.observer_root_incarnation
        ):
            raise Reject()
        prior_hierarchy = candidate.enrollment_hierarchies.get(source_namespace)
        if prior_hierarchy is not None:
            if (
                prior_hierarchy != hierarchy
                or candidate.enrollments.get(source_namespace) != root
            ):
                raise Reject()
            return
        if (
            source.index.enrollment_hierarchies.get(root.audience_key) != hierarchy
            or source.index.eligible_roots.get(root.audience_key) != root
        ):
            raise Reject()
        if len(candidate.enrollments) >= candidate.enrollment_capacity:
            raise Reject()
        if root.availability_profile is SOURCE_ONLY:
            if (
                root.anchor_enrollment_entry_digest is not None
                or anchor is not None
                or expected_coordinates[1] is not None
                or hierarchy.anchor_notification_hierarchy_digest is not None
            ):
                raise Reject()
        else:
            notification = (
                None
                if anchor is None
                else anchor.enrollment_notifications.get(root.audience_key)
            )
            if (
                expected_coordinates[1] is None
                or anchor is None
                or expected_coordinates[1]
                != (
                    anchor.anchor_authority,
                    anchor.anchor_selector_incarnation,
                    anchor.anchor_security_epoch,
                    anchor.producer_credential,
                )
                or root.anchor_enrollment_entry_digest is None
                or notification is None
                or _notification_digest(notification)
                != hierarchy.anchor_notification_hierarchy_digest
            ):
                raise Reject()
        candidate.enrollments[source_namespace] = root
        candidate.enrollment_hierarchies[source_namespace] = hierarchy

    _atomic(observer, mutate, _validate_observer)


def observer_prepare(observer: ObserverLocalStore, key: StableKey) -> None:
    def mutate(candidate: ObserverLocalStore) -> None:
        _validate_stable_key(key)
        if key.observer_root_incarnation != candidate.observer_root_incarnation:
            raise Reject()
        enrollment = candidate.enrollments.get(key.source_namespace)
        if enrollment is None:
            raise Reject()
        tombstone_key = (key.source_namespace, candidate.observer_root_incarnation)
        if tombstone_key in candidate.closure_tombstones:
            raise Reject()
        prior = candidate.operations.get(key)
        if prior is not None:
            if (
                prior.state is OperationState.INTENT_PREPARED
                and not prior.verified_request_attempt_present
            ):
                return
            raise Reject()
        if len(candidate.operations) >= candidate.operation_capacity:
            raise Reject()
        if any(
            operation.stable_key.logical_target_key == key.logical_target_key
            and operation.state is not OperationState.RESOLVED_WITHOUT_INSTALLATION
            for operation in candidate.operations.values()
        ):
            raise Reject()
        candidate.operations[key] = LocalOperation(stable_key=key)

    _atomic(observer, mutate, _validate_observer)


def observer_record_verified_attempt(
    observer: ObserverLocalStore, key: StableKey
) -> None:
    def mutate(candidate: ObserverLocalStore) -> None:
        operation = candidate.operations.get(key)
        if (
            operation is None
            or operation.state is not OperationState.INTENT_PREPARED
            or operation.exact_terminal_evidence_pending
        ):
            raise Reject()
        operation.verified_request_attempt_present = True

    _atomic(observer, mutate, _validate_observer)


def observer_import_closure(
    observer: ObserverLocalStore,
    producer: Source | Anchor,
    bundle: ClosureBundle,
    resolutions: dict[StableKey, ResolutionProof],
) -> str:
    def mutate(candidate: ObserverLocalStore) -> str:
        if type(producer) is Source:
            producer_hierarchy = producer.closure_hierarchy
            expected_producer_kind = "SOURCE"
            expected_context = ProofContext.SOURCE
            expected_credential = producer.producer_credential
        elif type(producer) is Anchor:
            producer_hierarchy = producer.closure_hierarchy
            expected_producer_kind = "ANCHOR"
            expected_context = ProofContext.ANCHOR
            expected_credential = producer.producer_credential
        else:
            raise Reject()
        trusted_coordinates = candidate.trusted_producer_coordinates.get(
            bundle.source_namespace
        )
        if trusted_coordinates is None:
            raise Reject()
        if type(producer) is Source:
            actual_coordinate = (
                producer.source_authority_id,
                producer.index.source_index_incarnation,
                producer.index.source_security_epoch,
                producer.producer_credential,
            )
            if trusted_coordinates[0] != actual_coordinate:
                raise Reject()
        else:
            actual_coordinate = (
                producer.anchor_authority,
                producer.anchor_selector_incarnation,
                producer.anchor_security_epoch,
                producer.producer_credential,
            )
            if trusted_coordinates[1] != actual_coordinate:
                raise Reject()
        if (
            producer_hierarchy is None
            or producer_hierarchy.bundle != bundle
            or producer_hierarchy.producer_kind != expected_producer_kind
            or bundle.context is not expected_context
        ):
            raise Reject()
        _validate_closure(producer_hierarchy, expected_credential=expected_credential)
        if (
            bundle.context is ProofContext.SOURCE
            and bundle.origin is not ClosureOrigin.SOURCE
        ) or (
            bundle.context is ProofContext.ANCHOR
            and bundle.origin is not ClosureOrigin.ANCHOR
        ):
            raise Reject()
        if (
            bundle.context is ProofContext.SOURCE
            and bundle.anchor_closure_cause is not AnchorClosureCause.NO_ANCHOR_CLOSURE
        ) or (
            bundle.context is ProofContext.ANCHOR
            and bundle.anchor_closure_cause is AnchorClosureCause.NO_ANCHOR_CLOSURE
        ):
            raise Reject()
        if (
            bundle.context is ProofContext.ANCHOR
            and bundle.availability_profile is not ANCHOR_PROFILE
        ):
            raise Reject()
        if (
            len(bundle.root) != 32
            or len(set(bundle.audience)) != len(bundle.audience)
            or bundle.audience != tuple(sorted(bundle.audience))
        ):
            raise Reject()
        enrollment = candidate.enrollments.get(bundle.source_namespace)
        enrollment_hierarchy = candidate.enrollment_hierarchies.get(
            bundle.source_namespace
        )
        if enrollment is None:
            raise Reject()
        if enrollment_hierarchy is None:
            raise Reject()
        if enrollment.audience_key not in bundle.audience:
            raise Reject()
        if enrollment.availability_profile is not bundle.availability_profile:
            raise Reject()
        bundle_digest = _bundle_digest(bundle)
        request_digest = _import_request_digest(bundle, resolutions)
        enrollment_ancestry_digest = _observer_ancestry_digest(enrollment_hierarchy)
        tombstone_key = (bundle.source_namespace, candidate.observer_root_incarnation)
        prior = candidate.closure_tombstones.get(tombstone_key)
        if prior is None and len(candidate.closure_tombstones) >= (
            candidate.tombstone_capacity
        ):
            raise Reject()
        if (
            prior is not None
            and prior.enrollment_ancestry_digest != enrollment_ancestry_digest
        ):
            raise Reject()
        existing_record = (
            None
            if prior is None
            else (
                prior.source_import
                if bundle.origin is ClosureOrigin.SOURCE
                else prior.anchor_import
            )
        )
        if existing_record is not None:
            if (
                existing_record.bundle_digest != bundle_digest
                or existing_record.request_digest != request_digest
            ):
                raise Reject()
            return existing_record.import_receipt_digest

        complete_keys = tuple(
            sorted(
                (
                    key
                    for key in candidate.operations
                    if key.source_namespace == bundle.source_namespace
                ),
                key=stable_key_bytes,
            )
        )
        if prior is None:
            proof_required = {
                key
                for key in complete_keys
                if candidate.operations[key].state is OperationState.INTENT_PREPARED
            }
        else:
            proof_required = {
                key
                for key in complete_keys
                if candidate.operations[key].state is OperationState.INTENT_PREPARED
                and candidate.operations[key].exact_terminal_evidence_pending
            }
        if set(resolutions) != proof_required:
            raise Reject()
        partition_entries: list[ClosureOperationPartitionEntry] = []
        for key in complete_keys:
            operation = candidate.operations[key]
            prior_operation_digest = _operation_digest(operation)
            if key not in proof_required:
                if operation.state is not OperationState.RESOLVED_WITHOUT_INSTALLATION:
                    raise Reject()
                partition_entries.append(
                    ClosureOperationPartitionEntry(
                        stable_key=key,
                        kind=(PRESERVE_CLOSED_HISTORY_PARTITION_KIND),
                        prior_operation_digest=prior_operation_digest,
                        installed_operation_digest=prior_operation_digest,
                        resolution_proof_digest=None,
                    )
                )
                continue
            resolution = resolutions[key]
            if bundle.context is ProofContext.SOURCE:
                canonical_entry = (
                    None
                    if resolution.source_entry is None
                    else source_entry_bytes(resolution.source_entry)
                )
                if resolution.anchor_entry is not None:
                    raise Reject()
            else:
                canonical_entry = (
                    None
                    if resolution.anchor_entry is None
                    else anchor_entry_bytes(resolution.anchor_entry)
                )
                if resolution.source_entry is not None:
                    raise Reject()
            verify_sparse_proof(
                resolution.body,
                expected_context=bundle.context,
                expected_kind=resolution.proof_kind,
                expected_root=bundle.root,
                stable_key=key,
                canonical_entry=canonical_entry,
            )

            if bundle.context is ProofContext.SOURCE:
                if resolution.proof_kind is ProofKind.NONMEMBERSHIP:
                    expected = ResolutionOutcome.SOURCE_FROZEN_KEY_NONMEMBERSHIP
                else:
                    entry = resolution.source_entry
                    if entry is None or entry.stable_key != key:
                        raise Reject()
                    if entry.kind is IndexEntryKind.CANCELED_BEFORE_ISSUANCE:
                        expected = ResolutionOutcome.SOURCE_FROZEN_CANCELED_MEMBERSHIP
                    else:
                        expected = ResolutionOutcome.PRESERVE_EXACT_TERMINAL
            elif resolution.proof_kind is ProofKind.NONMEMBERSHIP:
                expected = ResolutionOutcome.ANCHOR_FROZEN_NONMEMBERSHIP
            else:
                entry = resolution.anchor_entry
                if entry is None or entry.stable_key != key:
                    raise Reject()
                expected = ResolutionOutcome.ANCHOR_FROZEN_MEMBERSHIP

            if operation.verified_request_attempt_present:
                expected = ResolutionOutcome.PRESERVE_EXACT_TERMINAL
            if resolution.claimed_outcome is not expected:
                raise Reject()

            operation.resolution_outcome = expected
            if expected is ResolutionOutcome.PRESERVE_EXACT_TERMINAL:
                operation.exact_terminal_evidence_pending = True
                partition_kind = PRESERVE_PENDING_PARTITION_KIND
            else:
                operation.state = OperationState.RESOLVED_WITHOUT_INSTALLATION
                operation.exact_terminal_evidence_pending = False
                if bundle.context is ProofContext.SOURCE:
                    partition_kind = RESOLVE_SOURCE_NO_CHALLENGE_PARTITION_KIND
                elif resolution.proof_kind is ProofKind.NONMEMBERSHIP:
                    partition_kind = RESOLVE_ANCHOR_NONMEMBERSHIP_PARTITION_KIND
                else:
                    partition_kind = RESOLVE_ANCHOR_MEMBERSHIP_PARTITION_KIND
            partition_entries.append(
                ClosureOperationPartitionEntry(
                    stable_key=key,
                    kind=partition_kind,
                    prior_operation_digest=prior_operation_digest,
                    installed_operation_digest=_operation_digest(operation),
                    resolution_proof_digest=_proof_digest(resolution),
                )
            )
        partition = tuple(partition_entries)
        partition_digest = _partition_digest(partition)
        import_receipt_digest = _import_receipt_digest(
            bundle.origin, request_digest, partition_digest
        )
        import_record = ClosureOriginImportRecord(
            origin=bundle.origin,
            bundle_digest=bundle_digest,
            request_digest=request_digest,
            installed_partition_digest=partition_digest,
            import_receipt_digest=import_receipt_digest,
        )
        source_import = (
            import_record
            if bundle.origin is ClosureOrigin.SOURCE
            else (None if prior is None else prior.source_import)
        )
        anchor_import = (
            import_record
            if bundle.origin is ClosureOrigin.ANCHOR
            else (None if prior is None else prior.anchor_import)
        )
        source_root = (
            bundle.root
            if bundle.origin is ClosureOrigin.SOURCE
            else (None if prior is None else prior.source_index_root)
        )
        anchor_root = (
            bundle.root
            if bundle.origin is ClosureOrigin.ANCHOR
            else (None if prior is None else prior.anchor_root)
        )
        intended_tombstone = NamespaceClosureTombstone(
            source_namespace=bundle.source_namespace,
            observer_root_incarnation=candidate.observer_root_incarnation,
            evidence_state=(
                ClosureEvidenceState.SOURCE_AND_ANCHOR
                if source_import is not None and anchor_import is not None
                else (
                    ClosureEvidenceState.SOURCE_ONLY
                    if source_import is not None
                    else ClosureEvidenceState.ANCHOR_ONLY
                )
            ),
            source_index_root=source_root,
            anchor_root=anchor_root,
            enrollment_ancestry_digest=enrollment_ancestry_digest,
            source_import=source_import,
            anchor_import=anchor_import,
            latest_complete_partition=partition,
            latest_complete_partition_digest=partition_digest,
            latest_import_receipt_digest=import_receipt_digest,
        )
        candidate.closure_tombstones[tombstone_key] = intended_tombstone
        return import_receipt_digest

    result = _atomic(observer, mutate, _validate_observer)
    return _require_result_type(result, str)


def _intent_digest(intent: ReservationIntent) -> str:
    value = {
        "anchor_authority": intent.anchor_authority,
        "anchor_selector_incarnation": intent.anchor_selector_incarnation,
        "availability_profile": intent.availability_profile.value,
        "lineage_selector_incarnation": intent.lineage_selector_incarnation,
        "reservation_intent_id": intent.reservation_intent_id,
        "source_index_selector_incarnation": (intent.source_index_selector_incarnation),
        "source_namespace": intent.source_namespace,
        "source_owner_key": intent.source_owner_key,
        "source_owner_lifetime_slot": intent.source_owner_lifetime_slot,
    }
    return hashlib.sha256(
        json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()


def _require_intent(intent: ReservationIntent) -> None:
    _validate_namespace(intent.source_namespace)
    for value in (
        intent.reservation_intent_id,
        intent.source_owner_key,
        intent.source_owner_lifetime_slot,
        intent.lineage_selector_incarnation,
        intent.source_index_selector_incarnation,
        intent.anchor_selector_incarnation,
        intent.anchor_authority,
    ):
        _identifier(value)
    if (
        len(intent.source_namespace) != 3
        or not all(intent.source_namespace)
        or not intent.reservation_intent_id
        or not intent.source_owner_key
        or not intent.source_owner_lifetime_slot
        or not intent.lineage_selector_incarnation
        or not intent.source_index_selector_incarnation
        or not intent.anchor_selector_incarnation
        or intent.availability_profile is not ANCHOR_PROFILE
        or not intent.anchor_authority
        or intent.commit_digest != "source-intent:" + _intent_digest(intent)
    ):
        raise Reject()


def _allocation_digest(allocation: NamespaceAllocation) -> str:
    value = {
        "allocation_id": allocation.allocation_id,
        "anchor_authority": allocation.anchor_authority,
        "anchor_selector_incarnation": allocation.anchor_selector_incarnation,
        "availability_profile": allocation.availability_profile.value,
        "lineage_selector_incarnation": allocation.lineage_selector_incarnation,
        "anchor_reservation_receipt_digest": (
            allocation.anchor_reservation.receipt_digest
        ),
        "anchor_reservation_id": allocation.anchor_reservation.reservation_id,
        "reservation_intent_commit_digest": (
            allocation.anchor_reservation.reservation_intent.commit_digest
        ),
        "source_owner_key": allocation.anchor_reservation.source_owner_key,
        "source_owner_lifetime_slot": (
            allocation.anchor_reservation.source_owner_lifetime_slot
        ),
        "source_index_selector_incarnation": (
            allocation.source_index_selector_incarnation
        ),
        "source_namespace": allocation.source_namespace,
    }
    return hashlib.sha256(
        json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()


def _reservation_receipt_digest(
    reservation_intent: ReservationIntent, reservation_id: str
) -> str:
    _require_intent(reservation_intent)
    _identifier(reservation_id)
    return _fixture_digest(
        "anchor-capacity-reservation-projection|"
        + repr((reservation_intent, reservation_id))
    )


def _require_allocation(allocation: NamespaceAllocation) -> None:
    reservation = allocation.anchor_reservation
    _require_intent(reservation.reservation_intent)
    for value in (
        allocation.allocation_id,
        allocation.lineage_selector_incarnation,
        allocation.source_index_selector_incarnation,
        allocation.anchor_selector_incarnation,
        allocation.anchor_authority,
        reservation.reservation_id,
    ):
        _identifier(value)
    if (
        allocation.availability_profile is not ANCHOR_PROFILE
        or len(allocation.source_namespace) != 3
        or not all(allocation.source_namespace)
        or not allocation.allocation_id
        or not allocation.lineage_selector_incarnation
        or not allocation.source_index_selector_incarnation
        or not allocation.anchor_selector_incarnation
        or not allocation.anchor_authority
        or reservation.source_namespace != allocation.source_namespace
        or reservation.lineage_selector_incarnation
        != allocation.lineage_selector_incarnation
        or reservation.source_index_selector_incarnation
        != allocation.source_index_selector_incarnation
        or reservation.anchor_selector_incarnation
        != allocation.anchor_selector_incarnation
        or reservation.availability_profile is not allocation.availability_profile
        or reservation.anchor_authority != allocation.anchor_authority
        or reservation.reservation_intent.source_namespace
        != allocation.source_namespace
        or not reservation.reservation_id
        or reservation.receipt_digest
        != _reservation_receipt_digest(
            reservation.reservation_intent, reservation.reservation_id
        )
    ):
        raise Reject()


def _validate_intent(
    hierarchy: ProtectedIntent,
    *,
    expected_credential: OpaqueStateOwnerCredential | None = None,
) -> None:
    _require_intent(hierarchy.intent)
    coordinate = (
        hierarchy.producer_authority_id,
        hierarchy.producer_registry_incarnation,
        hierarchy.producer_security_epoch,
    )
    for value in coordinate:
        _identifier(value)
    expected_receipt = _fixture_digest(
        "source-namespace-intent-commit|" + repr((hierarchy.intent, coordinate))
    )
    if hierarchy.source_commit_receipt_digest != expected_receipt or (
        expected_credential is not None
        and hierarchy.producer_credential is not expected_credential
    ):
        raise Reject()
    _validate_protection(
        hierarchy.protection,
        domain="source-namespace-reservation-intent",
        semantic_value=(hierarchy.intent, coordinate, expected_receipt),
        audience_purpose="INDEPENDENT_ANCHOR_CAPACITY_RESERVATION",
        verification_class="DURABLE_SOURCE_PREINTENT_COMMIT",
    )


def _validate_reservation(
    hierarchy: ProtectedReservation,
    *,
    expected_credential: OpaqueStateOwnerCredential | None = None,
) -> None:
    reservation = hierarchy.reservation
    _require_intent(reservation.reservation_intent)
    semantic_value = (
        reservation,
        (
            hierarchy.producer_authority_id,
            hierarchy.producer_registry_incarnation,
            hierarchy.producer_security_epoch,
        ),
        hierarchy.source_intent_hierarchy_digest,
        hierarchy.owner_participant_units_charged,
        hierarchy.owner_bytes_charged,
        hierarchy.global_participant_units_charged,
        hierarchy.global_bytes_charged,
    )
    expected_receipt = _fixture_digest(
        "anchor-namespace-reservation-commit|" + repr(semantic_value)
    )
    if (
        not _complete_digest_set((hierarchy.source_intent_hierarchy_digest,))
        or hierarchy.owner_participant_units_charged
        != ANCHOR_RESERVATION_PARTICIPANT_CHARGE
        or hierarchy.owner_bytes_charged != ANCHOR_RESERVATION_BYTE_CHARGE
        or hierarchy.global_participant_units_charged
        != ANCHOR_RESERVATION_PARTICIPANT_CHARGE
        or hierarchy.global_bytes_charged != ANCHOR_RESERVATION_BYTE_CHARGE
        or hierarchy.anchor_commit_receipt_digest != expected_receipt
        or (
            expected_credential is not None
            and hierarchy.producer_credential is not expected_credential
        )
    ):
        raise Reject()
    _validate_protection(
        hierarchy.protection,
        domain="anchor-namespace-capacity-reservation",
        semantic_value=semantic_value + (expected_receipt,),
        audience_purpose="SOURCE_NAMESPACE_ALLOCATION",
        verification_class="DURABLE_NO_REFUND_CAPACITY_CHARGE",
    )


def _validate_allocation(
    hierarchy: ProtectedAllocation,
    *,
    expected_credential: OpaqueStateOwnerCredential | None = None,
) -> None:
    _require_allocation(hierarchy.allocation)
    semantic_value = (
        hierarchy.allocation,
        (
            hierarchy.producer_authority_id,
            hierarchy.producer_registry_incarnation,
            hierarchy.producer_security_epoch,
        ),
        hierarchy.anchor_reservation_hierarchy_digest,
    )
    expected_receipt = _fixture_digest(
        "source-namespace-allocation-commit|" + repr(semantic_value)
    )
    if (
        not _complete_digest_set((hierarchy.anchor_reservation_hierarchy_digest,))
        or hierarchy.source_commit_receipt_digest != expected_receipt
        or (
            expected_credential is not None
            and hierarchy.producer_credential is not expected_credential
        )
    ):
        raise Reject()
    _validate_protection(
        hierarchy.protection,
        domain="source-namespace-allocation",
        semantic_value=semantic_value + (expected_receipt,),
        audience_purpose="INDEPENDENT_ANCHOR_NAMESPACE_GENESIS",
        verification_class="DURABLE_SOURCE_ALLOCATION_COMMIT",
    )


def _validate_genesis(
    hierarchy: ProtectedGenesis,
    *,
    expected_credential: OpaqueStateOwnerCredential | None = None,
) -> None:
    _require_allocation(hierarchy.allocation)
    semantic_value = (
        hierarchy.allocation_hierarchy_digest,
        hierarchy.allocation,
        (
            hierarchy.producer_authority_id,
            hierarchy.producer_registry_incarnation,
            hierarchy.producer_security_epoch,
        ),
        hierarchy.anchor_genesis_projection_digest,
    )
    expected_receipt = _fixture_digest(
        "anchor-namespace-genesis-commit|" + repr(semantic_value)
    )
    if (
        not _complete_digest_set(
            (
                hierarchy.allocation_hierarchy_digest,
                hierarchy.anchor_genesis_projection_digest,
            )
        )
        or hierarchy.anchor_commit_receipt_digest != expected_receipt
        or (
            expected_credential is not None
            and hierarchy.producer_credential is not expected_credential
        )
    ):
        raise Reject()
    _validate_protection(
        hierarchy.protection,
        domain="anchor-namespace-genesis",
        semantic_value=semantic_value + (expected_receipt,),
        audience_purpose="SOURCE_NAMESPACE_REGISTRATION",
        verification_class="DURABLE_INDEPENDENT_ANCHOR_GENESIS",
    )


def _validate_cancellation(
    hierarchy: ProtectedCancellation,
    *,
    expected_credential: OpaqueStateOwnerCredential | None = None,
) -> None:
    _validate_closed_graph(hierarchy)
    if type(hierarchy) is not ProtectedCancellation or type(
        hierarchy.projection
    ) not in (IntentCancellation, NamespaceCancellation):
        raise Reject()
    semantic_value = hierarchy.projection
    coordinate = (
        hierarchy.producer_authority_id,
        hierarchy.producer_registry_incarnation,
        hierarchy.producer_security_epoch,
    )
    expected_receipt = _fixture_digest(
        "source-namespace-cancellation-commit|" + repr((semantic_value, coordinate))
    )
    if hierarchy.source_commit_receipt_digest != expected_receipt or (
        expected_credential is not None
        and hierarchy.producer_credential is not expected_credential
    ):
        raise Reject()
    _validate_protection(
        hierarchy.protection,
        domain="source-namespace-cancellation",
        semantic_value=(semantic_value, coordinate, expected_receipt),
        audience_purpose=semantic_value.audience_purpose,
        verification_class=semantic_value.verification_class,
    )


def _validate_source_registry(source: SourceRegistry) -> None:
    _validate_closed_graph(source)
    for value in (
        source.producer_authority_id,
        source.registry_incarnation,
        source.security_epoch,
    ):
        _identifier(value)
    source_coordinate = (
        source.producer_authority_id,
        source.registry_incarnation,
        source.security_epoch,
    )
    if source.state is SourceBootstrap.ABSENT:
        if (
            source.reservation_intent is not None
            or source.reservation_intent_cancellation is not None
            or source.allocation is not None
            or source.cancellation is not None
            or source.anchor_genesis_projection_digest is not None
            or source.reservation_intent_hierarchy is not None
            or source.allocation_hierarchy is not None
            or source.anchor_genesis_hierarchy is not None
            or source.cancellation_hierarchy is not None
            or source.anchor_reservation_hierarchy is not None
            or source.trusted_anchor_producer_credential is not None
            or source.trusted_anchor_registry_coordinate is not None
        ):
            raise Reject()
        return
    if source.reservation_intent is None:
        raise Reject()
    _require_intent(source.reservation_intent)
    intent_hierarchy = source.reservation_intent_hierarchy
    if intent_hierarchy is None or intent_hierarchy.intent != source.reservation_intent:
        raise Reject()
    _validate_intent(intent_hierarchy, expected_credential=source.producer_credential)
    if (
        intent_hierarchy.producer_authority_id,
        intent_hierarchy.producer_registry_incarnation,
        intent_hierarchy.producer_security_epoch,
    ) != source_coordinate:
        raise Reject()
    if source.state is SourceBootstrap.RESERVATION_INTENT_PENDING:
        if (
            source.reservation_intent_cancellation is not None
            or source.allocation is not None
            or source.cancellation is not None
            or source.anchor_genesis_projection_digest is not None
            or source.allocation_hierarchy is not None
            or source.anchor_genesis_hierarchy is not None
            or source.cancellation_hierarchy is not None
            or source.anchor_reservation_hierarchy is not None
            or source.trusted_anchor_producer_credential is not None
            or source.trusted_anchor_registry_coordinate is not None
        ):
            raise Reject()
        return
    if source.allocation is None:
        if (
            source.state is SourceBootstrap.CANCELED
            and source.reservation_intent_cancellation is not None
            and source.cancellation is None
            and source.anchor_genesis_projection_digest is None
            and source.allocation_hierarchy is None
            and source.anchor_genesis_hierarchy is None
            and source.cancellation_hierarchy is not None
            and source.anchor_reservation_hierarchy is None
            and source.trusted_anchor_producer_credential is None
            and source.trusted_anchor_registry_coordinate is None
            and source.reservation_intent_cancellation.reservation_intent
            == source.reservation_intent
        ):
            if (
                source.reservation_intent_cancellation.verification_class != _TOMBSTONE
                or source.reservation_intent_cancellation.audience_purpose
                != "SOURCE_NAMESPACE_ANCHOR_RESERVATION_INTENT_CANCELLATION"
                or source.reservation_intent_cancellation.cancellation_commit
                != "source-intent-cancel:" + _intent_digest(source.reservation_intent)
            ):
                raise Reject()
            _validate_cancellation(
                source.cancellation_hierarchy,
                expected_credential=source.producer_credential,
            )
            if (
                source.cancellation_hierarchy.projection
                != source.reservation_intent_cancellation
                or (
                    source.cancellation_hierarchy.producer_authority_id,
                    source.cancellation_hierarchy.producer_registry_incarnation,
                    source.cancellation_hierarchy.producer_security_epoch,
                )
                != source_coordinate
            ):
                raise Reject()
            return
        raise Reject()
    if (
        source.allocation.anchor_reservation.reservation_intent
        != source.reservation_intent
    ):
        raise Reject()
    allocation_hierarchy = source.allocation_hierarchy
    if (
        allocation_hierarchy is None
        or allocation_hierarchy.allocation != source.allocation
    ):
        raise Reject()
    _validate_allocation(
        allocation_hierarchy, expected_credential=source.producer_credential
    )
    if (
        allocation_hierarchy.producer_authority_id,
        allocation_hierarchy.producer_registry_incarnation,
        allocation_hierarchy.producer_security_epoch,
    ) != source_coordinate:
        raise Reject()
    anchor_reservation_hierarchy = source.anchor_reservation_hierarchy
    if (
        anchor_reservation_hierarchy is None
        or source.trusted_anchor_producer_credential is None
        or source.trusted_anchor_registry_coordinate is None
    ):
        raise Reject()
    _validate_reservation(
        anchor_reservation_hierarchy,
        expected_credential=source.trusted_anchor_producer_credential,
    )
    if (
        (
            anchor_reservation_hierarchy.producer_authority_id,
            anchor_reservation_hierarchy.producer_registry_incarnation,
            anchor_reservation_hierarchy.producer_security_epoch,
        )
        != source.trusted_anchor_registry_coordinate
        or anchor_reservation_hierarchy.reservation
        != source.allocation.anchor_reservation
        or allocation_hierarchy.anchor_reservation_hierarchy_digest
        != _object_digest(anchor_reservation_hierarchy)
    ):
        raise Reject()
    if source.state is SourceBootstrap.PENDING:
        if (
            source.reservation_intent_cancellation is not None
            or source.cancellation is not None
            or source.anchor_genesis_projection_digest is not None
            or source.anchor_genesis_hierarchy is not None
            or source.cancellation_hierarchy is not None
        ):
            raise Reject()
        return
    if source.state is SourceBootstrap.LIVE:
        if (
            source.reservation_intent_cancellation is not None
            or source.cancellation is not None
            or not source.anchor_genesis_projection_digest
            or source.anchor_genesis_hierarchy is None
            or source.cancellation_hierarchy is not None
        ):
            raise Reject()
        _validate_genesis(
            source.anchor_genesis_hierarchy,
            expected_credential=source.trusted_anchor_producer_credential,
        )
        if (
            (
                source.anchor_genesis_hierarchy.producer_authority_id,
                source.anchor_genesis_hierarchy.producer_registry_incarnation,
                source.anchor_genesis_hierarchy.producer_security_epoch,
            )
            != source.trusted_anchor_registry_coordinate
            or source.anchor_genesis_hierarchy.anchor_genesis_projection_digest
            != source.anchor_genesis_projection_digest
            or source.anchor_genesis_hierarchy.allocation != source.allocation
        ):
            raise Reject()
        return
    if source.state is SourceBootstrap.CANCELED:
        if (
            source.reservation_intent_cancellation is not None
            or source.cancellation is None
            or source.cancellation_hierarchy is None
            or source.anchor_genesis_hierarchy is not None
        ):
            raise Reject()
        if source.cancellation.allocation != source.allocation:
            raise Reject()
        _validate_cancellation(
            source.cancellation_hierarchy,
            expected_credential=source.producer_credential,
        )
        if source.cancellation_hierarchy.projection != source.cancellation:
            raise Reject()
        if (
            source.cancellation_hierarchy.producer_authority_id,
            source.cancellation_hierarchy.producer_registry_incarnation,
            source.cancellation_hierarchy.producer_security_epoch,
        ) != source_coordinate:
            raise Reject()
        return
    raise Reject()


def _reservation_charge(anchor: AnchorRegistry) -> tuple[int, int, int, int]:
    return (
        anchor.owner_participant_units_charged,
        anchor.owner_bytes_charged,
        anchor.global_participant_units_charged,
        anchor.global_bytes_charged,
    )


def _charge_anchor_reservation_slot(anchor: AnchorRegistry) -> None:
    charge = _reservation_charge(anchor)
    intended = (
        ANCHOR_RESERVATION_PARTICIPANT_CHARGE,
        ANCHOR_RESERVATION_BYTE_CHARGE,
        ANCHOR_RESERVATION_PARTICIPANT_CHARGE,
        ANCHOR_RESERVATION_BYTE_CHARGE,
    )
    if charge == intended:
        return
    if any(charge):
        raise Reject()
    (
        anchor.owner_participant_units_charged,
        anchor.owner_bytes_charged,
        anchor.global_participant_units_charged,
        anchor.global_bytes_charged,
    ) = intended


def _validate_anchor_registry(anchor: AnchorRegistry) -> None:
    _validate_closed_graph(anchor)
    counts = (
        anchor.eligible_root_count,
        anchor.challenge_entry_count,
        anchor.admission_count,
        anchor.in_flight_count,
    )
    charge = _reservation_charge(anchor)
    intended_charge = (
        ANCHOR_RESERVATION_PARTICIPANT_CHARGE,
        ANCHOR_RESERVATION_BYTE_CHARGE,
        ANCHOR_RESERVATION_PARTICIPANT_CHARGE,
        ANCHOR_RESERVATION_BYTE_CHARGE,
    )
    if any(value < 0 for value in (*counts, *charge)):
        raise Reject()
    if (
        anchor.owner_participant_units_charged
        != anchor.global_participant_units_charged
        or anchor.owner_bytes_charged != anchor.global_bytes_charged
        or anchor.owner_participant_units_charged > ANCHOR_OWNER_PARTICIPANT_CAP
        or anchor.owner_bytes_charged > ANCHOR_OWNER_BYTE_CAP
        or anchor.global_participant_units_charged > ANCHOR_GLOBAL_PARTICIPANT_CAP
        or anchor.global_bytes_charged > ANCHOR_GLOBAL_BYTE_CAP
    ):
        raise Reject()
    if anchor.reservation_state is ReservationState.ABSENT:
        if any(charge):
            raise Reject()
    elif charge != intended_charge:
        raise Reject()

    source_closure_fields = (
        anchor.source_closure_terminal_cause,
        anchor.source_closure_finalization_receipt,
    )
    source_provenance_fields = (
        anchor.source_intent_hierarchy,
        anchor.trusted_source_producer_credential,
        anchor.trusted_source_registry_coordinate,
    )
    anchor_coordinate = (
        anchor.producer_authority_id,
        anchor.registry_incarnation,
        anchor.security_epoch,
    )
    if anchor.reservation_state is ReservationState.ABSENT:
        if (
            anchor.state is not AnchorBootstrap.ABSENT
            or anchor.reservation is not None
            or anchor.allocation is not None
            or any(counts)
            or anchor.cancellation_projection is not None
            or anchor.cancellation_finalization_receipt is not None
            or any(source_closure_fields)
            or anchor.reservation_hierarchy is not None
            or anchor.genesis_hierarchy is not None
            or anchor.cancellation_hierarchy is not None
            or any(value is not None for value in source_provenance_fields)
        ):
            raise Reject()
        return
    intent = _slot_intent(anchor)
    if (
        anchor.source_intent_hierarchy is None
        or anchor.trusted_source_producer_credential is None
        or anchor.source_intent_hierarchy.intent != intent
    ):
        raise Reject()
    _validate_intent(
        anchor.source_intent_hierarchy,
        expected_credential=anchor.trusted_source_producer_credential,
    )
    if (
        anchor.source_intent_hierarchy.producer_authority_id,
        anchor.source_intent_hierarchy.producer_registry_incarnation,
        anchor.source_intent_hierarchy.producer_security_epoch,
    ) != anchor.trusted_source_registry_coordinate:
        raise Reject()
    for hierarchy in (anchor.reservation_hierarchy, anchor.genesis_hierarchy):
        if (
            hierarchy is not None
            and (
                hierarchy.producer_authority_id,
                hierarchy.producer_registry_incarnation,
                hierarchy.producer_security_epoch,
            )
            != anchor_coordinate
        ):
            raise Reject()
    if anchor.reservation_state is ReservationState.RESERVED:
        if (
            anchor.state is not AnchorBootstrap.ABSENT
            or anchor.reservation is None
            or anchor.allocation is not None
            or any(counts)
            or anchor.cancellation_projection is not None
            or anchor.cancellation_finalization_receipt is not None
            or any(source_closure_fields)
            or anchor.reservation_hierarchy is None
            or anchor.genesis_hierarchy is not None
            or anchor.cancellation_hierarchy is not None
        ):
            raise Reject()
        _require_intent(anchor.reservation.reservation_intent)
        _validate_reservation(
            anchor.reservation_hierarchy, expected_credential=anchor.producer_credential
        )
        if anchor.reservation_hierarchy.reservation != anchor.reservation:
            raise Reject()
        if (
            anchor.reservation_hierarchy.producer_authority_id,
            anchor.reservation_hierarchy.producer_registry_incarnation,
            anchor.reservation_hierarchy.producer_security_epoch,
        ) != anchor_coordinate:
            raise Reject()
        return
    if anchor.reservation_state is ReservationState.MATERIALIZED:
        if (
            anchor.state is not AnchorBootstrap.OPEN
            or anchor.reservation is None
            or anchor.allocation is None
            or anchor.allocation.anchor_reservation != anchor.reservation
            or anchor.cancellation_projection is not None
            or anchor.cancellation_finalization_receipt is not None
            or any(source_closure_fields)
            or anchor.reservation_hierarchy is None
            or anchor.genesis_hierarchy is None
            or anchor.cancellation_hierarchy is not None
        ):
            raise Reject()
        _require_allocation(anchor.allocation)
        _validate_reservation(
            anchor.reservation_hierarchy, expected_credential=anchor.producer_credential
        )
        _validate_genesis(
            anchor.genesis_hierarchy, expected_credential=anchor.producer_credential
        )
        if (
            anchor.reservation_hierarchy.reservation != anchor.reservation
            or anchor.genesis_hierarchy.allocation != anchor.allocation
            or (
                anchor.genesis_hierarchy.producer_authority_id,
                anchor.genesis_hierarchy.producer_registry_incarnation,
                anchor.genesis_hierarchy.producer_security_epoch,
            )
            != anchor_coordinate
        ):
            raise Reject()
        return
    if anchor.reservation_state is ReservationState.TERMINAL:
        if anchor.state is AnchorBootstrap.FROZEN:
            if (
                anchor.reservation is None
                or anchor.allocation is None
                or anchor.allocation.anchor_reservation != anchor.reservation
                or anchor.cancellation_projection is not None
                or anchor.cancellation_finalization_receipt is not None
                or anchor.source_closure_terminal_cause not in {_COOPERATIVE, _ISOLATED}
                or not anchor.source_closure_finalization_receipt
                or anchor.reservation_hierarchy is None
                or anchor.genesis_hierarchy is None
                or anchor.cancellation_hierarchy is not None
            ):
                raise Reject()
            _require_allocation(anchor.allocation)
            _validate_reservation(
                anchor.reservation_hierarchy,
                expected_credential=anchor.producer_credential,
            )
            _validate_genesis(
                anchor.genesis_hierarchy, expected_credential=anchor.producer_credential
            )
            return
        if (
            anchor.state is not AnchorBootstrap.CANCELED
            or any(counts)
            or anchor.cancellation_projection is None
            or anchor.cancellation_finalization_receipt is None
            or any(source_closure_fields)
            or anchor.cancellation_hierarchy is None
        ):
            raise Reject()
        if type(anchor.cancellation_projection) is IntentCancellation:
            if (
                anchor.allocation is not None
                or anchor.genesis_hierarchy is not None
                or (
                    anchor.reservation is None
                    and anchor.reservation_hierarchy is not None
                )
                or (
                    anchor.reservation is not None
                    and (
                        anchor.reservation.reservation_intent
                        != anchor.cancellation_projection.reservation_intent
                        or anchor.reservation_hierarchy is None
                    )
                )
            ):
                raise Reject()
        elif type(anchor.cancellation_projection) is NamespaceCancellation:
            if (
                anchor.reservation is None
                or anchor.allocation is None
                or anchor.reservation_hierarchy is None
                or anchor.allocation.anchor_reservation != anchor.reservation
                or anchor.cancellation_projection.allocation != anchor.allocation
            ):
                raise Reject()
        else:
            raise Reject()
        if anchor.reservation_hierarchy is not None:
            _validate_reservation(
                anchor.reservation_hierarchy,
                expected_credential=anchor.producer_credential,
            )
            if anchor.reservation_hierarchy.reservation != anchor.reservation:
                raise Reject()
        if anchor.genesis_hierarchy is not None:
            _validate_genesis(
                anchor.genesis_hierarchy, expected_credential=anchor.producer_credential
            )
            if anchor.genesis_hierarchy.allocation != anchor.allocation:
                raise Reject()
        _validate_cancellation(
            anchor.cancellation_hierarchy,
            expected_credential=anchor.trusted_source_producer_credential,
        )
        if anchor.cancellation_hierarchy.projection != anchor.cancellation_projection:
            raise Reject()
        if (
            anchor.cancellation_hierarchy.producer_authority_id,
            anchor.cancellation_hierarchy.producer_registry_incarnation,
            anchor.cancellation_hierarchy.producer_security_epoch,
        ) != anchor.trusted_source_registry_coordinate:
            raise Reject()
        return
    raise Reject()


def _anchor_authority_slot_key(intent: ReservationIntent) -> tuple[str, str]:
    return (intent.source_owner_key, intent.source_owner_lifetime_slot)


def _slot_intent(slot: AnchorRegistry) -> ReservationIntent:
    if slot.reservation is not None:
        return slot.reservation.reservation_intent
    projection = slot.cancellation_projection
    if type(projection) is IntentCancellation:
        return projection.reservation_intent
    raise Reject()


def _insert_exact_index(
    index: dict[object, tuple[str, str]], coordinate: object, slot_key: tuple[str, str]
) -> None:
    prior = index.get(coordinate)
    if prior is not None and prior != slot_key:
        raise Reject()
    index[coordinate] = slot_key


def _validate_authority_registry(registry: AuthorityRegistry) -> None:
    _validate_closed_graph(registry)
    _identifier(registry.anchor_authority)
    _identifier(registry.registry_incarnation)
    _identifier(registry.security_epoch)
    if (
        ANCHOR_RESERVATION_PARTICIPANT_CHARGE <= 0
        or ANCHOR_RESERVATION_BYTE_CHARGE <= 0
        or ANCHOR_OWNER_PARTICIPANT_CAP < ANCHOR_RESERVATION_PARTICIPANT_CHARGE
        or ANCHOR_OWNER_BYTE_CAP < ANCHOR_RESERVATION_BYTE_CHARGE
        or ANCHOR_GLOBAL_PARTICIPANT_CAP < ANCHOR_OWNER_PARTICIPANT_CAP
        or ANCHOR_GLOBAL_BYTE_CAP < ANCHOR_OWNER_BYTE_CAP
    ):
        raise Reject()

    reservation_intent_index: dict[str, tuple[str, str]] = {}
    source_namespace_index: dict[tuple[str, str, str], tuple[str, str]] = {}
    lineage_selector_index: dict[str, tuple[str, str]] = {}
    source_index_selector_index: dict[str, tuple[str, str]] = {}
    anchor_selector_index: dict[str, tuple[str, str]] = {}
    owner_participant_units_charged: dict[str, int] = {}
    owner_bytes_charged: dict[str, int] = {}
    global_participant_units_charged = 0
    global_bytes_charged = 0
    all_slots_terminal = bool(registry.slots)

    for slot_key, slot in registry.slots.items():
        if (
            len(slot_key) != 2
            or not all(type(value) is str and value for value in slot_key)
            or slot.producer_credential is not registry.producer_credential
            or (
                slot.producer_authority_id,
                slot.registry_incarnation,
                slot.security_epoch,
            )
            != (
                registry.anchor_authority,
                registry.registry_incarnation,
                registry.security_epoch,
            )
            or slot.reservation_state is ReservationState.ABSENT
        ):
            raise Reject()
        _validate_anchor_registry(slot)
        intent = _slot_intent(slot)
        if (
            intent.anchor_authority != registry.anchor_authority
            or _anchor_authority_slot_key(intent) != slot_key
        ):
            raise Reject()
        _insert_exact_index(
            reservation_intent_index, intent.reservation_intent_id, slot_key
        )
        _insert_exact_index(source_namespace_index, intent.source_namespace, slot_key)
        _insert_exact_index(
            lineage_selector_index, intent.lineage_selector_incarnation, slot_key
        )
        _insert_exact_index(
            source_index_selector_index,
            intent.source_index_selector_incarnation,
            slot_key,
        )
        _insert_exact_index(
            anchor_selector_index, intent.anchor_selector_incarnation, slot_key
        )
        owner_participant_units_charged[intent.source_owner_key] = (
            owner_participant_units_charged.get(intent.source_owner_key, 0)
            + slot.owner_participant_units_charged
        )
        owner_bytes_charged[intent.source_owner_key] = (
            owner_bytes_charged.get(intent.source_owner_key, 0)
            + slot.owner_bytes_charged
        )
        global_participant_units_charged += slot.global_participant_units_charged
        global_bytes_charged += slot.global_bytes_charged
        all_slots_terminal = all_slots_terminal and (
            slot.reservation_state is ReservationState.TERMINAL
            and slot.state in {AnchorBootstrap.CANCELED, AnchorBootstrap.FROZEN}
        )

    if (
        registry.reservation_intent_index != reservation_intent_index
        or registry.source_namespace_index != source_namespace_index
        or registry.lineage_selector_index != lineage_selector_index
        or registry.source_index_selector_index != source_index_selector_index
        or registry.anchor_selector_index != anchor_selector_index
        or registry.owner_participant_units_charged != owner_participant_units_charged
        or registry.owner_bytes_charged != owner_bytes_charged
        or registry.global_participant_units_charged != global_participant_units_charged
        or registry.global_bytes_charged != global_bytes_charged
        or any(
            value > ANCHOR_OWNER_PARTICIPANT_CAP
            for value in owner_participant_units_charged.values()
        )
        or any(value > ANCHOR_OWNER_BYTE_CAP for value in owner_bytes_charged.values())
        or global_participant_units_charged > ANCHOR_GLOBAL_PARTICIPANT_CAP
        or global_bytes_charged > ANCHOR_GLOBAL_BYTE_CAP
    ):
        raise Reject()
    if registry.authority_domain_retirement_receipt is not None:
        if not all_slots_terminal:
            raise Reject()
        expected_receipt = _anchor_authority_domain_retirement_receipt(registry)
        if registry.authority_domain_retirement_receipt != expected_receipt:
            raise Reject()


def _validate_anchor_binding(
    anchor: Anchor, namespace_registry: AuthorityRegistry
) -> None:
    _validate_closed_graph((anchor, namespace_registry))
    _validate_authority_registry(namespace_registry)
    slot = _slot_for_anchor(namespace_registry, anchor)
    intent = _slot_intent(slot)
    allocation = slot.allocation
    if (
        intent.source_namespace != anchor.source_namespace
        or intent.anchor_authority != anchor.anchor_authority
        or intent.anchor_selector_incarnation != anchor.anchor_selector_incarnation
        or namespace_registry.producer_credential is not anchor.producer_credential
        or slot.producer_credential is not anchor.producer_credential
        or slot.eligible_root_count != len(anchor.eligible_roots)
        or slot.challenge_entry_count != len(anchor.entries)
        or slot.admission_count != len(anchor.relay_hierarchies)
        or slot.in_flight_count != len(anchor.in_flight_mutations)
    ):
        raise Reject()
    if anchor.phase is AnchorPhase.ABSENT:
        if (
            slot.state is not AnchorBootstrap.ABSENT
            or slot.reservation_state is not ReservationState.RESERVED
            or allocation is not None
        ):
            raise Reject()
        return
    if (
        allocation is None
        or allocation.source_namespace != anchor.source_namespace
        or allocation.anchor_authority != anchor.anchor_authority
        or allocation.anchor_selector_incarnation != anchor.anchor_selector_incarnation
    ):
        raise Reject()
    if slot.state is AnchorBootstrap.OPEN:
        if (
            anchor.phase
            not in {AnchorPhase.PENDING_SOURCE_CONFIRMATION, AnchorPhase.OPEN}
            or slot.reservation_state is not ReservationState.MATERIALIZED
        ):
            raise Reject()
        return
    if slot.state is AnchorBootstrap.FROZEN:
        if (
            anchor.phase is not AnchorPhase.FROZEN
            or slot.reservation_state is not ReservationState.TERMINAL
            or slot.source_closure_terminal_cause != anchor.reservation_terminal_cause
        ):
            raise Reject()
        return
    if slot.state is AnchorBootstrap.CANCELED:
        if (
            anchor.phase is not AnchorPhase.CANCELED
            or slot.reservation_state is not ReservationState.TERMINAL
            or slot.cancellation_projection is None
            or slot.cancellation_finalization_receipt is None
        ):
            raise Reject()
        return
    raise Reject()


def _rebuild_authority_indexes(registry: AuthorityRegistry) -> None:
    registry.reservation_intent_index.clear()
    registry.source_namespace_index.clear()
    registry.lineage_selector_index.clear()
    registry.source_index_selector_index.clear()
    registry.anchor_selector_index.clear()
    registry.owner_participant_units_charged.clear()
    registry.owner_bytes_charged.clear()
    registry.global_participant_units_charged = 0
    registry.global_bytes_charged = 0
    for slot_key, slot in registry.slots.items():
        intent = _slot_intent(slot)
        _insert_exact_index(
            registry.reservation_intent_index, intent.reservation_intent_id, slot_key
        )
        _insert_exact_index(
            registry.source_namespace_index, intent.source_namespace, slot_key
        )
        _insert_exact_index(
            registry.lineage_selector_index,
            intent.lineage_selector_incarnation,
            slot_key,
        )
        _insert_exact_index(
            registry.source_index_selector_index,
            intent.source_index_selector_incarnation,
            slot_key,
        )
        _insert_exact_index(
            registry.anchor_selector_index, intent.anchor_selector_incarnation, slot_key
        )
        registry.owner_participant_units_charged[intent.source_owner_key] = (
            registry.owner_participant_units_charged.get(intent.source_owner_key, 0)
            + slot.owner_participant_units_charged
        )
        registry.owner_bytes_charged[intent.source_owner_key] = (
            registry.owner_bytes_charged.get(intent.source_owner_key, 0)
            + slot.owner_bytes_charged
        )
        registry.global_participant_units_charged += (
            slot.global_participant_units_charged
        )
        registry.global_bytes_charged += slot.global_bytes_charged


def _authority_slot(
    registry: AuthorityRegistry, intent: ReservationIntent
) -> AnchorRegistry:
    slot = registry.slots.get(_anchor_authority_slot_key(intent))
    if slot is None or _slot_intent(slot) != intent:
        raise Reject()
    return slot


def _slot_for_anchor(registry: AuthorityRegistry, anchor: Anchor) -> AnchorRegistry:
    slot_key = registry.source_namespace_index.get(anchor.source_namespace)
    slot = None if slot_key is None else registry.slots.get(slot_key)
    if slot is None:
        raise Reject()
    intent = _slot_intent(slot)
    if (
        intent.anchor_authority != anchor.anchor_authority
        or intent.anchor_selector_incarnation != anchor.anchor_selector_incarnation
    ):
        raise Reject()
    return slot


def _anchor_allocation(
    registry: AuthorityRegistry, anchor: Anchor
) -> NamespaceAllocation:
    allocation = _slot_for_anchor(registry, anchor).allocation
    if allocation is None:
        raise Reject()
    return allocation


def source_prepare_reservation(
    source: SourceRegistry, intent: ReservationIntent
) -> ProtectedIntent:
    def mutate(candidate: SourceRegistry) -> ProtectedIntent:
        _require_intent(intent)
        coordinate = (
            candidate.producer_authority_id,
            candidate.registry_incarnation,
            candidate.security_epoch,
        )
        receipt = _fixture_digest(
            "source-namespace-intent-commit|" + repr((intent, coordinate))
        )
        hierarchy = ProtectedIntent(
            intent=intent,
            producer_authority_id=coordinate[0],
            producer_registry_incarnation=coordinate[1],
            producer_security_epoch=coordinate[2],
            source_commit_receipt_digest=receipt,
            producer_credential=candidate.producer_credential,
            protection=_protect(
                "source-namespace-reservation-intent",
                (intent, coordinate, receipt),
                audience_purpose="INDEPENDENT_ANCHOR_CAPACITY_RESERVATION",
                verification_class="DURABLE_SOURCE_PREINTENT_COMMIT",
            ),
        )
        if candidate.reservation_intent_hierarchy is not None:
            if (
                candidate.reservation_intent != intent
                or candidate.reservation_intent_hierarchy != hierarchy
            ):
                raise Reject()
            return hierarchy
        if candidate.state is not SourceBootstrap.ABSENT:
            raise Reject()
        candidate.state = SourceBootstrap.RESERVATION_INTENT_PENDING
        candidate.reservation_intent = intent
        candidate.reservation_intent_hierarchy = hierarchy
        return hierarchy

    result = _atomic(source, mutate, _validate_source_registry)
    return _require_result_type(result, ProtectedIntent)


def source_cancel_namespace_reservation_intent(
    source: SourceRegistry,
) -> ProtectedCancellation:
    def mutate(candidate: SourceRegistry) -> ProtectedCancellation:
        if (
            candidate.state is SourceBootstrap.CANCELED
            and type(candidate.reservation_intent_cancellation) is IntentCancellation
            and candidate.cancellation_hierarchy is not None
        ):
            return candidate.cancellation_hierarchy
        if (
            candidate.state is not SourceBootstrap.RESERVATION_INTENT_PENDING
            or candidate.reservation_intent is None
        ):
            raise Reject()
        projection = IntentCancellation(
            reservation_intent=candidate.reservation_intent,
            cancellation_commit=(
                "source-intent-cancel:" + _intent_digest(candidate.reservation_intent)
            ),
        )
        coordinate = (
            candidate.producer_authority_id,
            candidate.registry_incarnation,
            candidate.security_epoch,
        )
        receipt = _fixture_digest(
            "source-namespace-cancellation-commit|" + repr((projection, coordinate))
        )
        hierarchy = ProtectedCancellation(
            projection=projection,
            producer_authority_id=coordinate[0],
            producer_registry_incarnation=coordinate[1],
            producer_security_epoch=coordinate[2],
            source_commit_receipt_digest=receipt,
            producer_credential=candidate.producer_credential,
            protection=_protect(
                "source-namespace-cancellation",
                (projection, coordinate, receipt),
                audience_purpose=projection.audience_purpose,
                verification_class=projection.verification_class,
            ),
        )
        candidate.state = SourceBootstrap.CANCELED
        candidate.reservation_intent_cancellation = projection
        candidate.cancellation_hierarchy = hierarchy
        return hierarchy

    result = _atomic(source, mutate, _validate_source_registry)
    return _require_result_type(result, ProtectedCancellation)


def _anchor_reserve_namespace_capacity_in_slot(
    anchor: AnchorRegistry,
    source: SourceRegistry,
    reservation: IndependentAnchorNamespaceCapacityReservation,
    intent_hierarchy: ProtectedIntent,
) -> ProtectedReservation:
    def mutate(candidate: AnchorRegistry) -> ProtectedReservation:
        _require_intent(reservation.reservation_intent)
        _validate_intent(
            intent_hierarchy, expected_credential=source.producer_credential
        )
        if (
            source.reservation_intent_hierarchy != intent_hierarchy
            or intent_hierarchy.intent != reservation.reservation_intent
        ):
            raise Reject()
        semantic_value = (
            reservation,
            (
                candidate.producer_authority_id,
                candidate.registry_incarnation,
                candidate.security_epoch,
            ),
            _object_digest(intent_hierarchy),
            ANCHOR_RESERVATION_PARTICIPANT_CHARGE,
            ANCHOR_RESERVATION_BYTE_CHARGE,
            ANCHOR_RESERVATION_PARTICIPANT_CHARGE,
            ANCHOR_RESERVATION_BYTE_CHARGE,
        )
        receipt = _fixture_digest(
            "anchor-namespace-reservation-commit|" + repr(semantic_value)
        )
        hierarchy = ProtectedReservation(
            reservation=reservation,
            producer_authority_id=candidate.producer_authority_id,
            producer_registry_incarnation=candidate.registry_incarnation,
            producer_security_epoch=candidate.security_epoch,
            source_intent_hierarchy_digest=_object_digest(intent_hierarchy),
            owner_participant_units_charged=(ANCHOR_RESERVATION_PARTICIPANT_CHARGE),
            owner_bytes_charged=ANCHOR_RESERVATION_BYTE_CHARGE,
            global_participant_units_charged=(ANCHOR_RESERVATION_PARTICIPANT_CHARGE),
            global_bytes_charged=ANCHOR_RESERVATION_BYTE_CHARGE,
            anchor_commit_receipt_digest=receipt,
            producer_credential=candidate.producer_credential,
            protection=_protect(
                "anchor-namespace-capacity-reservation",
                semantic_value + (receipt,),
                audience_purpose="SOURCE_NAMESPACE_ALLOCATION",
                verification_class="DURABLE_NO_REFUND_CAPACITY_CHARGE",
            ),
        )
        if candidate.reservation_hierarchy is not None:
            if (
                candidate.reservation != reservation
                or candidate.reservation_hierarchy != hierarchy
                or candidate.source_intent_hierarchy != intent_hierarchy
                or candidate.trusted_source_producer_credential
                is not source.producer_credential
                or candidate.trusted_source_registry_coordinate
                != (
                    source.producer_authority_id,
                    source.registry_incarnation,
                    source.security_epoch,
                )
            ):
                raise Reject()
            return hierarchy
        if (
            candidate.reservation_state is not ReservationState.ABSENT
            or candidate.state is not AnchorBootstrap.ABSENT
        ):
            raise Reject()
        if (
            reservation.availability_profile is not ANCHOR_PROFILE
            or not reservation.reservation_id
            or not reservation.receipt_digest
            or not reservation.anchor_selector_incarnation
            or not reservation.anchor_authority
        ):
            raise Reject()
        _charge_anchor_reservation_slot(candidate)
        candidate.reservation_state = ReservationState.RESERVED
        candidate.reservation = reservation
        candidate.reservation_hierarchy = hierarchy
        candidate.source_intent_hierarchy = intent_hierarchy
        candidate.trusted_source_producer_credential = source.producer_credential
        candidate.trusted_source_registry_coordinate = (
            source.producer_authority_id,
            source.registry_incarnation,
            source.security_epoch,
        )
        return hierarchy

    result = _atomic(anchor, mutate, _validate_anchor_registry)
    return _require_result_type(result, ProtectedReservation)


def anchor_reserve_namespace_capacity(
    registry: AuthorityRegistry,
    source: SourceRegistry,
    reservation: IndependentAnchorNamespaceCapacityReservation,
    intent_hierarchy: ProtectedIntent,
) -> ProtectedReservation:
    def mutate(candidate: AuthorityRegistry) -> ProtectedReservation:
        if candidate.authority_domain_retirement_receipt is not None:
            raise Reject()
        intent = reservation.reservation_intent
        if intent.anchor_authority != candidate.anchor_authority:
            raise Reject()
        slot_key = _anchor_authority_slot_key(intent)
        slot = candidate.slots.get(slot_key)
        if slot is None:
            slot = AnchorRegistry(
                producer_credential=candidate.producer_credential,
                producer_authority_id=candidate.anchor_authority,
                registry_incarnation=candidate.registry_incarnation,
                security_epoch=candidate.security_epoch,
            )
            candidate.slots[slot_key] = slot
        elif _slot_intent(slot) != intent:
            raise Reject()
        result = _anchor_reserve_namespace_capacity_in_slot(
            slot, source, reservation, intent_hierarchy
        )
        _rebuild_authority_indexes(candidate)
        return result

    result = _atomic(registry, mutate, _validate_authority_registry)
    return _require_result_type(result, ProtectedReservation)


def _anchor_import_source_reservation_intent_cancellation_in_slot(
    anchor: AnchorRegistry, source: SourceRegistry, hierarchy: ProtectedCancellation
) -> str:
    def mutate(candidate: AnchorRegistry) -> str:
        _validate_cancellation(
            hierarchy,
            expected_credential=(
                candidate.trusted_source_producer_credential
                or source.producer_credential
            ),
        )
        if (
            (
                candidate.trusted_source_producer_credential is not None
                and candidate.trusted_source_producer_credential
                is not source.producer_credential
            )
            or source.cancellation_hierarchy != hierarchy
            or type(hierarchy.projection) is not IntentCancellation
        ):
            raise Reject()
        projection = hierarchy.projection
        intent = projection.reservation_intent
        _require_intent(intent)
        if (
            projection.verification_class != _TOMBSTONE
            or projection.audience_purpose
            != "SOURCE_NAMESPACE_ANCHOR_RESERVATION_INTENT_CANCELLATION"
            or projection.cancellation_commit
            != "source-intent-cancel:" + _intent_digest(intent)
        ):
            raise Reject()
        receipt = "anchor-intent-cancel-final:" + projection.cancellation_commit
        if candidate.state is AnchorBootstrap.CANCELED:
            if (
                candidate.reservation_state is not ReservationState.TERMINAL
                or candidate.cancellation_projection != projection
                or candidate.cancellation_hierarchy != hierarchy
                or candidate.cancellation_finalization_receipt != receipt
                or candidate.source_intent_hierarchy
                != source.reservation_intent_hierarchy
                or candidate.trusted_source_producer_credential
                is not source.producer_credential
                or candidate.trusted_source_registry_coordinate
                != (
                    source.producer_authority_id,
                    source.registry_incarnation,
                    source.security_epoch,
                )
            ):
                raise Reject()
            return receipt
        if (
            candidate.state is not AnchorBootstrap.ABSENT
            or candidate.reservation_state
            not in {ReservationState.ABSENT, ReservationState.RESERVED}
            or (
                candidate.reservation is not None
                and candidate.reservation.reservation_intent != intent
            )
        ):
            raise Reject()
        _charge_anchor_reservation_slot(candidate)
        candidate.state = AnchorBootstrap.CANCELED
        candidate.reservation_state = ReservationState.TERMINAL
        candidate.cancellation_projection = projection
        candidate.cancellation_hierarchy = hierarchy
        candidate.cancellation_finalization_receipt = receipt
        candidate.source_intent_hierarchy = source.reservation_intent_hierarchy
        candidate.trusted_source_producer_credential = source.producer_credential
        candidate.trusted_source_registry_coordinate = (
            source.producer_authority_id,
            source.registry_incarnation,
            source.security_epoch,
        )
        return receipt

    return _require_result_type(_atomic(anchor, mutate, _validate_anchor_registry), str)


def anchor_import_source_reservation_intent_cancellation(
    registry: AuthorityRegistry,
    source: SourceRegistry,
    hierarchy: ProtectedCancellation,
) -> str:
    def mutate(candidate: AuthorityRegistry) -> str:
        if candidate.authority_domain_retirement_receipt is not None:
            raise Reject()
        if type(hierarchy.projection) is not IntentCancellation:
            raise Reject()
        intent = hierarchy.projection.reservation_intent
        if intent.anchor_authority != candidate.anchor_authority:
            raise Reject()
        slot_key = _anchor_authority_slot_key(intent)
        slot = candidate.slots.get(slot_key)
        if slot is None:
            slot = AnchorRegistry(
                producer_credential=candidate.producer_credential,
                producer_authority_id=candidate.anchor_authority,
                registry_incarnation=candidate.registry_incarnation,
                security_epoch=candidate.security_epoch,
            )
            candidate.slots[slot_key] = slot
        elif _slot_intent(slot) != intent:
            raise Reject()
        receipt = _anchor_import_source_reservation_intent_cancellation_in_slot(
            slot, source, hierarchy
        )
        _rebuild_authority_indexes(candidate)
        return receipt

    return _require_result_type(
        _atomic(registry, mutate, _validate_authority_registry), str
    )


def source_allocate_namespace(
    source: SourceRegistry,
    anchor: AuthorityRegistry,
    allocation: NamespaceAllocation,
    reservation_hierarchy: ProtectedReservation,
) -> ProtectedAllocation:
    def mutate(candidate: SourceRegistry) -> ProtectedAllocation:
        _validate_reservation(
            reservation_hierarchy, expected_credential=anchor.producer_credential
        )
        anchor_slot = _authority_slot(
            anchor, allocation.anchor_reservation.reservation_intent
        )
        if (
            anchor_slot.reservation_hierarchy != reservation_hierarchy
            or reservation_hierarchy.reservation != allocation.anchor_reservation
        ):
            raise Reject()
        _require_allocation(allocation)
        semantic_value = (
            allocation,
            (
                candidate.producer_authority_id,
                candidate.registry_incarnation,
                candidate.security_epoch,
            ),
            _object_digest(reservation_hierarchy),
        )
        receipt = _fixture_digest(
            "source-namespace-allocation-commit|" + repr(semantic_value)
        )
        hierarchy = ProtectedAllocation(
            allocation=allocation,
            producer_authority_id=candidate.producer_authority_id,
            producer_registry_incarnation=candidate.registry_incarnation,
            producer_security_epoch=candidate.security_epoch,
            anchor_reservation_hierarchy_digest=_object_digest(reservation_hierarchy),
            source_commit_receipt_digest=receipt,
            producer_credential=candidate.producer_credential,
            protection=_protect(
                "source-namespace-allocation",
                semantic_value + (receipt,),
                audience_purpose="INDEPENDENT_ANCHOR_NAMESPACE_GENESIS",
                verification_class="DURABLE_SOURCE_ALLOCATION_COMMIT",
            ),
        )
        if candidate.allocation_hierarchy is not None:
            if (
                candidate.allocation != allocation
                or candidate.allocation_hierarchy != hierarchy
                or candidate.anchor_reservation_hierarchy != reservation_hierarchy
                or candidate.trusted_anchor_producer_credential
                is not anchor.producer_credential
                or candidate.trusted_anchor_registry_coordinate
                != (
                    anchor.anchor_authority,
                    anchor.registry_incarnation,
                    anchor.security_epoch,
                )
            ):
                raise Reject()
            return hierarchy
        if (
            candidate.state is not SourceBootstrap.RESERVATION_INTENT_PENDING
            or candidate.reservation_intent
            != allocation.anchor_reservation.reservation_intent
        ):
            raise Reject()
        candidate.state = SourceBootstrap.PENDING
        candidate.allocation = allocation
        candidate.allocation_hierarchy = hierarchy
        candidate.anchor_reservation_hierarchy = reservation_hierarchy
        candidate.trusted_anchor_producer_credential = anchor.producer_credential
        candidate.trusted_anchor_registry_coordinate = (
            anchor.anchor_authority,
            anchor.registry_incarnation,
            anchor.security_epoch,
        )
        return hierarchy

    result = _atomic(source, mutate, _validate_source_registry)
    return _require_result_type(result, ProtectedAllocation)


def _anchor_create_from_source_allocation_in_slot(
    namespace_slot: AnchorRegistry,
    anchor: Anchor,
    source: SourceRegistry,
    allocation_hierarchy: ProtectedAllocation,
) -> ProtectedGenesis:
    _validate_allocation(
        allocation_hierarchy, expected_credential=source.producer_credential
    )
    if (
        source.allocation_hierarchy != allocation_hierarchy
        or namespace_slot.trusted_source_producer_credential
        is not source.producer_credential
        or (
            allocation_hierarchy.producer_authority_id,
            allocation_hierarchy.producer_registry_incarnation,
            allocation_hierarchy.producer_security_epoch,
        )
        != namespace_slot.trusted_source_registry_coordinate
    ):
        raise Reject()
    allocation = allocation_hierarchy.allocation
    _require_allocation(allocation)
    allocation_digest = _object_digest(allocation_hierarchy)
    genesis_projection_digest = _fixture_digest(
        "anchor-genesis-projection|" + allocation_digest
    )
    semantic_value = (
        allocation_digest,
        allocation,
        (
            namespace_slot.producer_authority_id,
            namespace_slot.registry_incarnation,
            namespace_slot.security_epoch,
        ),
        genesis_projection_digest,
    )
    receipt = _fixture_digest("anchor-namespace-genesis-commit|" + repr(semantic_value))
    hierarchy = ProtectedGenesis(
        allocation_hierarchy_digest=allocation_digest,
        allocation=allocation,
        producer_authority_id=namespace_slot.producer_authority_id,
        producer_registry_incarnation=namespace_slot.registry_incarnation,
        producer_security_epoch=namespace_slot.security_epoch,
        anchor_genesis_projection_digest=genesis_projection_digest,
        anchor_commit_receipt_digest=receipt,
        producer_credential=namespace_slot.producer_credential,
        protection=_protect(
            "anchor-namespace-genesis",
            semantic_value + (receipt,),
            audience_purpose="SOURCE_NAMESPACE_REGISTRATION",
            verification_class="DURABLE_INDEPENDENT_ANCHOR_GENESIS",
        ),
    )
    if namespace_slot.genesis_hierarchy is not None:
        if (
            namespace_slot.allocation != allocation
            or namespace_slot.genesis_hierarchy != hierarchy
            or anchor.phase
            not in {AnchorPhase.PENDING_SOURCE_CONFIRMATION, AnchorPhase.OPEN}
        ):
            raise Reject()
        return hierarchy
    if (
        namespace_slot.state is not AnchorBootstrap.ABSENT
        or namespace_slot.reservation_state is not ReservationState.RESERVED
        or namespace_slot.reservation != allocation.anchor_reservation
        or anchor.phase is not AnchorPhase.ABSENT
        or anchor.source_namespace != allocation.source_namespace
        or anchor.anchor_authority != allocation.anchor_authority
        or anchor.anchor_selector_incarnation != allocation.anchor_selector_incarnation
    ):
        raise Reject()
    namespace_slot.state = AnchorBootstrap.OPEN
    namespace_slot.reservation_state = ReservationState.MATERIALIZED
    namespace_slot.allocation = allocation
    namespace_slot.genesis_hierarchy = hierarchy
    anchor.phase = AnchorPhase.PENDING_SOURCE_CONFIRMATION
    return hierarchy


def anchor_create_from_source_allocation(
    registry: AuthorityRegistry,
    anchor: Anchor,
    source: SourceRegistry,
    allocation_hierarchy: ProtectedAllocation,
) -> ProtectedGenesis:
    def mutate(
        candidate_anchor: Anchor, candidate_slot: AnchorRegistry
    ) -> ProtectedGenesis:
        return _anchor_create_from_source_allocation_in_slot(
            candidate_slot, candidate_anchor, source, allocation_hierarchy
        )

    result = _atomic_anchor_transition(anchor, registry, mutate)
    return _require_result_type(result, ProtectedGenesis)


def materialized_anchor_registry(
    anchor: Anchor, source_authority: Source, *, coordinate_suffix: str
) -> AuthorityRegistry:
    if source_authority.index.source_namespace != anchor.source_namespace:
        raise Reject()
    source_owner_key = "source-owner:" + anchor.source_namespace[2]
    intent = ReservationIntent(
        source_namespace=anchor.source_namespace,
        reservation_intent_id="source-intent:" + coordinate_suffix,
        source_owner_key=source_owner_key,
        source_owner_lifetime_slot="source-owner-slot:" + coordinate_suffix,
        lineage_selector_incarnation="lineage:" + coordinate_suffix,
        source_index_selector_incarnation="source-index:" + coordinate_suffix,
        anchor_selector_incarnation="anchor:" + coordinate_suffix,
        availability_profile=(ANCHOR_PROFILE),
        anchor_authority=anchor.anchor_authority,
        commit_digest="",
    )
    intent = replace(intent, commit_digest=("source-intent:" + _intent_digest(intent)))
    anchor.anchor_selector_incarnation = intent.anchor_selector_incarnation
    reservation_id = "anchor-reservation:" + coordinate_suffix
    reservation = IndependentAnchorNamespaceCapacityReservation(
        reservation_intent=intent,
        reservation_id=reservation_id,
        receipt_digest=_reservation_receipt_digest(intent, reservation_id),
    )
    allocation = NamespaceAllocation(
        source_namespace=anchor.source_namespace,
        allocation_id="source-allocation:" + coordinate_suffix,
        lineage_selector_incarnation=intent.lineage_selector_incarnation,
        source_index_selector_incarnation=intent.source_index_selector_incarnation,
        anchor_selector_incarnation=intent.anchor_selector_incarnation,
        availability_profile=intent.availability_profile,
        anchor_authority=intent.anchor_authority,
        anchor_reservation=reservation,
    )
    registry = AuthorityRegistry(
        anchor_authority=anchor.anchor_authority,
        producer_credential=anchor.producer_credential,
    )
    source_registry = SourceRegistry(
        producer_credential=source_authority.producer_credential
    )
    intent_hierarchy = source_prepare_reservation(source_registry, intent)
    reservation_hierarchy = anchor_reserve_namespace_capacity(
        registry, source_registry, reservation, intent_hierarchy
    )
    allocation_hierarchy = source_allocate_namespace(
        source_registry, registry, allocation, reservation_hierarchy
    )
    anchor_create_from_source_allocation(
        registry, anchor, source_registry, allocation_hierarchy
    )
    genesis_hierarchy = _authority_slot(registry, intent).genesis_hierarchy
    if genesis_hierarchy is None:
        raise Reject()
    source_register_namespace(source_registry, registry, anchor, genesis_hierarchy)
    anchor_activate_registered_namespace(
        registry, anchor, source_registry, genesis_hierarchy
    )
    anchor.trusted_source_coordinate = (
        source_authority.source_authority_id,
        source_authority.index.source_index_incarnation,
        source_authority.index.source_security_epoch,
        source_authority.producer_credential,
    )
    _validate_anchor_binding(anchor, registry)
    return registry


def _anchor_authority_domain_retirement_receipt(registry: AuthorityRegistry) -> str:
    inventory: list[tuple[object, ...]] = []
    for slot_key, slot in sorted(registry.slots.items()):
        terminal_receipt = (
            slot.source_closure_finalization_receipt
            or slot.cancellation_finalization_receipt
        )
        if (
            slot.reservation_state is not ReservationState.TERMINAL
            or slot.state not in {AnchorBootstrap.CANCELED, AnchorBootstrap.FROZEN}
            or not terminal_receipt
        ):
            raise Reject()
        inventory.append(
            (
                slot_key,
                _intent_digest(_slot_intent(slot)),
                slot.state.value,
                terminal_receipt,
                _reservation_charge(slot),
            )
        )
    if not inventory:
        raise Reject()
    semantic_value = (
        registry.anchor_authority,
        tuple(inventory),
        tuple(sorted(registry.reservation_intent_index.items())),
        tuple(sorted(registry.source_namespace_index.items())),
        tuple(sorted(registry.lineage_selector_index.items())),
        tuple(sorted(registry.source_index_selector_index.items())),
        tuple(sorted(registry.anchor_selector_index.items())),
        tuple(sorted(registry.owner_participant_units_charged.items())),
        tuple(sorted(registry.owner_bytes_charged.items())),
        registry.global_participant_units_charged,
        registry.global_bytes_charged,
    )
    return "anchor-authority-domain-retired:" + _fixture_digest(
        "anchor-authority-domain-retirement|" + repr(semantic_value)
    )


def anchor_finalize_authority_domain_retirement(
    namespace_registry: AuthorityRegistry,
) -> str:
    def mutate(candidate: AuthorityRegistry) -> str:
        receipt = _anchor_authority_domain_retirement_receipt(candidate)
        if candidate.authority_domain_retirement_receipt is not None:
            if candidate.authority_domain_retirement_receipt != receipt:
                raise Reject()
            return receipt
        candidate.authority_domain_retirement_receipt = receipt
        return receipt

    charge_before = (
        copy.deepcopy(namespace_registry.owner_participant_units_charged),
        copy.deepcopy(namespace_registry.owner_bytes_charged),
        namespace_registry.global_participant_units_charged,
        namespace_registry.global_bytes_charged,
    )
    result = _require_result_type(
        _atomic(namespace_registry, mutate, _validate_authority_registry), str
    )
    charge_after = (
        namespace_registry.owner_participant_units_charged,
        namespace_registry.owner_bytes_charged,
        namespace_registry.global_participant_units_charged,
        namespace_registry.global_bytes_charged,
    )
    if charge_after != charge_before:
        raise Reject()
    return result


def source_register_namespace(
    source: SourceRegistry,
    anchor: AuthorityRegistry,
    anchor_store: Anchor,
    genesis_hierarchy: ProtectedGenesis,
) -> None:
    _validate_source_registry(source)
    _validate_authority_registry(anchor)
    _validate_anchor_binding(anchor_store, anchor)
    _validate_genesis(genesis_hierarchy, expected_credential=anchor.producer_credential)
    allocation = genesis_hierarchy.allocation
    anchor_slot = _authority_slot(
        anchor, allocation.anchor_reservation.reservation_intent
    )
    if (
        anchor_slot.genesis_hierarchy != genesis_hierarchy
        or source.trusted_anchor_producer_credential is not anchor.producer_credential
    ):
        raise Reject()

    def mutate(candidate: SourceRegistry) -> None:
        if candidate.state is SourceBootstrap.LIVE:
            if (
                candidate.allocation != allocation
                or candidate.anchor_genesis_hierarchy != genesis_hierarchy
            ):
                raise Reject()
            return
        if (
            candidate.state is not SourceBootstrap.PENDING
            or candidate.allocation != allocation
            or anchor_store.phase is not AnchorPhase.PENDING_SOURCE_CONFIRMATION
        ):
            raise Reject()
        candidate.state = SourceBootstrap.LIVE
        candidate.anchor_genesis_projection_digest = (
            genesis_hierarchy.anchor_genesis_projection_digest
        )
        candidate.anchor_genesis_hierarchy = genesis_hierarchy

    _atomic(source, mutate, _validate_source_registry)


def anchor_activate_registered_namespace(
    anchor: AuthorityRegistry,
    anchor_store: Anchor,
    source: SourceRegistry,
    genesis_hierarchy: ProtectedGenesis,
) -> None:
    _validate_source_registry(source)
    _validate_authority_registry(anchor)
    _validate_anchor_binding(anchor_store, anchor)
    if (
        source.state is not SourceBootstrap.LIVE
        or source.anchor_genesis_hierarchy != genesis_hierarchy
        or source.trusted_anchor_producer_credential is not anchor.producer_credential
    ):
        raise Reject()

    def mutate(candidate_anchor: Anchor, candidate_slot: AnchorRegistry) -> None:
        _validate_genesis(
            genesis_hierarchy, expected_credential=candidate_slot.producer_credential
        )
        if candidate_slot.genesis_hierarchy != genesis_hierarchy:
            raise Reject()
        if candidate_anchor.phase is AnchorPhase.OPEN:
            return
        if candidate_anchor.phase is not AnchorPhase.PENDING_SOURCE_CONFIRMATION:
            raise Reject()
        candidate_anchor.phase = AnchorPhase.OPEN

    _atomic_anchor_transition(anchor_store, anchor, mutate)


def source_cancel_pending_namespace(source: SourceRegistry) -> ProtectedCancellation:
    def mutate(candidate: SourceRegistry) -> ProtectedCancellation:
        if (
            candidate.state is SourceBootstrap.CANCELED
            and candidate.cancellation is not None
            and candidate.cancellation_hierarchy is not None
        ):
            return candidate.cancellation_hierarchy
        if (
            candidate.state is not SourceBootstrap.PENDING
            or candidate.allocation is None
        ):
            raise Reject()
        projection = NamespaceCancellation(
            allocation=candidate.allocation,
            cancellation_commit=(
                "source-cancel:" + _allocation_digest(candidate.allocation)
            ),
        )
        coordinate = (
            candidate.producer_authority_id,
            candidate.registry_incarnation,
            candidate.security_epoch,
        )
        receipt = _fixture_digest(
            "source-namespace-cancellation-commit|" + repr((projection, coordinate))
        )
        hierarchy = ProtectedCancellation(
            projection=projection,
            producer_authority_id=coordinate[0],
            producer_registry_incarnation=coordinate[1],
            producer_security_epoch=coordinate[2],
            source_commit_receipt_digest=receipt,
            producer_credential=candidate.producer_credential,
            protection=_protect(
                "source-namespace-cancellation",
                (projection, coordinate, receipt),
                audience_purpose=projection.audience_purpose,
                verification_class=projection.verification_class,
            ),
        )
        candidate.state = SourceBootstrap.CANCELED
        candidate.cancellation = projection
        candidate.cancellation_hierarchy = hierarchy
        return hierarchy

    result = _atomic(source, mutate, _validate_source_registry)
    return _require_result_type(result, ProtectedCancellation)


def _anchor_import_source_namespace_cancellation_in_slot(
    anchor: AnchorRegistry, source: SourceRegistry, hierarchy: ProtectedCancellation
) -> str:
    def mutate(candidate: AnchorRegistry) -> str:
        _validate_cancellation(
            hierarchy, expected_credential=candidate.trusted_source_producer_credential
        )
        if (
            candidate.trusted_source_producer_credential
            is not source.producer_credential
            or source.cancellation_hierarchy != hierarchy
            or type(hierarchy.projection) is not NamespaceCancellation
        ):
            raise Reject()
        projection = hierarchy.projection
        _require_allocation(projection.allocation)
        if (
            projection.verification_class != _TOMBSTONE
            or projection.audience_purpose != "SOURCE_NAMESPACE_ALLOCATION_CANCELLATION"
        ):
            raise Reject()
        expected_commit = "source-cancel:" + _allocation_digest(projection.allocation)
        if projection.cancellation_commit != expected_commit:
            raise Reject()
        receipt = "anchor-cancel-final:" + expected_commit
        if candidate.state is AnchorBootstrap.CANCELED:
            if (
                candidate.reservation_state is not ReservationState.TERMINAL
                or candidate.cancellation_projection != projection
                or candidate.cancellation_hierarchy != hierarchy
                or candidate.cancellation_finalization_receipt != receipt
            ):
                raise Reject()
            return receipt
        if candidate.state is AnchorBootstrap.ABSENT:
            if (
                candidate.reservation_state is not ReservationState.RESERVED
                or candidate.reservation != projection.allocation.anchor_reservation
            ):
                raise Reject()
            candidate.allocation = projection.allocation
        elif candidate.state is AnchorBootstrap.OPEN:
            if (
                candidate.reservation_state is not ReservationState.MATERIALIZED
                or candidate.reservation != projection.allocation.anchor_reservation
                or candidate.allocation != projection.allocation
            ):
                raise Reject()
            if any(
                (
                    candidate.eligible_root_count,
                    candidate.challenge_entry_count,
                    candidate.admission_count,
                    candidate.in_flight_count,
                )
            ):
                raise Reject()
        else:
            raise Reject()
        candidate.state = AnchorBootstrap.CANCELED
        candidate.reservation_state = ReservationState.TERMINAL
        candidate.cancellation_projection = projection
        candidate.cancellation_hierarchy = hierarchy
        candidate.cancellation_finalization_receipt = receipt
        return receipt

    return _require_result_type(_atomic(anchor, mutate, _validate_anchor_registry), str)


def anchor_import_source_namespace_cancellation(
    registry: AuthorityRegistry,
    source: SourceRegistry,
    hierarchy: ProtectedCancellation,
    *,
    anchor_store: Anchor | None = None,
) -> str:
    if type(hierarchy.projection) is not NamespaceCancellation:
        raise Reject()
    intent = hierarchy.projection.allocation.anchor_reservation.reservation_intent
    retained_slot = _authority_slot(registry, intent)
    if retained_slot.state is AnchorBootstrap.OPEN:
        if anchor_store is None:
            raise Reject()

        def mutate_bound(
            candidate_anchor: Anchor, candidate_slot: AnchorRegistry
        ) -> str:
            if candidate_anchor.phase is AnchorPhase.CANCELED:
                return _anchor_import_source_namespace_cancellation_in_slot(
                    candidate_slot, source, hierarchy
                )
            if (
                candidate_anchor.phase is not AnchorPhase.PENDING_SOURCE_CONFIRMATION
                or candidate_anchor.eligible_roots
                or candidate_anchor.entries
                or candidate_anchor.relay_hierarchies
                or candidate_anchor.in_flight_mutations
            ):
                raise Reject()
            receipt = _anchor_import_source_namespace_cancellation_in_slot(
                candidate_slot, source, hierarchy
            )
            candidate_anchor.phase = AnchorPhase.CANCELED
            return receipt

        return _require_result_type(
            _atomic_anchor_transition(anchor_store, registry, mutate_bound), str
        )
    if anchor_store is not None:
        raise Reject()

    def mutate(candidate: AuthorityRegistry) -> str:
        slot = _authority_slot(candidate, intent)
        receipt = _anchor_import_source_namespace_cancellation_in_slot(
            slot, source, hierarchy
        )
        _rebuild_authority_indexes(candidate)
        return receipt

    return _require_result_type(
        _atomic(registry, mutate, _validate_authority_registry), str
    )


class Harness:
    def __init__(self) -> None:
        self.accepted: set[str] = set()
        self.invariants: set[str] = set()
        self.rejections: set[str] = set()
        self.witnesses: set[str] = set()

    def accept(self, label: str) -> None:
        if label in self.accepted:
            raise AssertionError(label)
        self.accepted.add(label)

    def check(self, label: str, condition: bool) -> None:
        if not condition:
            raise AssertionError(label)
        if label in self.invariants:
            raise AssertionError(label)
        self.invariants.add(label)

    def witness(self, label: str) -> None:
        if label in self.witnesses:
            raise AssertionError(label)
        self.witnesses.add(label)

    def reject(self, label: str, operation: Callable[[], object]) -> None:
        try:
            operation()
        except (Reject, ValueError):
            if label in self.rejections:
                raise AssertionError(label)
            self.rejections.add(label)
            return
        raise AssertionError(label)


def _root(*, root_id: str, incarnation: str, profile: Availability) -> EligibleRoot:
    _closed_member(profile, Availability)
    root = EligibleRoot(
        root_id=root_id,
        root_incarnation=incarnation,
        availability_profile=profile,
        registered_root_hierarchy_digest="",
        source_enrollment_hierarchy_digest="",
        anchor_enrollment_entry_digest=None,
        authority_credential=(_CONFIGURED_REGISTERED_ROOT_AUTHORITY_CREDENTIAL),
    )
    root = replace(
        root, source_enrollment_hierarchy_digest=(_source_enrollment_digest(root))
    )
    root = replace(
        root, registered_root_hierarchy_digest=(_registered_root_digest(root))
    )
    if profile is SOURCE_ONLY:
        return root
    return replace(
        root, anchor_enrollment_entry_digest=(_anchor_eligibility_digest(root))
    )


def _key(
    namespace: tuple[str, str, str],
    root_incarnation: str,
    suffix: str,
    *,
    target: str | None = None,
) -> StableKey:
    return StableKey(
        authority_realm=namespace[0],
        source_kind=namespace[1],
        logical_source_id=namespace[2],
        requester_principal="observer-principal",
        observer_root_incarnation=root_incarnation,
        request_operation="operation-" + suffix,
        request_kind="ATTACH",
        logical_target_key=target or "target-" + suffix,
    )


def _enroll_source(source: Source, root: EligibleRoot) -> None:
    registered_hierarchy = registered_root_authority_publish(
        source.registered_root_authority_producer,
        root,
        observer_role_version=source.index.observer_role_version,
        source_security_epoch=source.index.source_security_epoch,
    )
    source_import_current_registered_root_authority(source, registered_hierarchy)
    source_enroll_root(source, root)


def _qualified_clock_relation(source: Source, anchor: Anchor) -> ClockRelation:
    return _seal_clock_relation(
        ClockRelation(
            relation_id="clock-relation:"
            + source.index.source_namespace[2]
            + ":"
            + anchor.anchor_authority,
            source_clock_id=source.index.source_clock_id,
            anchor_clock_id=anchor.anchor_clock_id,
            source_clock_epoch=source.index.source_clock_epoch,
            anchor_clock_epoch=anchor.anchor_clock_epoch,
            anchor_minus_source_lower=10,
            anchor_minus_source_upper=20,
            source_valid_from=0,
            source_valid_through_exclusive=1_000,
            anchor_valid_from=0,
            anchor_valid_through_exclusive=2_000,
            source_reference_value=0,
            anchor_reference_value=15,
            maximum_relative_rate_ppb=1_000,
            semantic_digest="",
        )
    )


def _anchor_sample(
    anchor: Anchor, *, lower: int = 49, upper: int = 50
) -> BoundedClockSample:
    return BoundedClockSample(
        clock_id=anchor.anchor_clock_id,
        clock_epoch=anchor.anchor_clock_epoch,
        lower=lower,
        upper=upper,
    )


def _source_sample(
    source: Source, *, lower: int = 40, upper: int = 41
) -> BoundedClockSample:
    return BoundedClockSample(
        clock_id=source.index.source_clock_id,
        clock_epoch=source.index.source_clock_epoch,
        lower=lower,
        upper=upper,
    )


def _enroll_anchor_profile(
    source: Source,
    anchor: Anchor,
    namespace_registry: AuthorityRegistry,
    root: EligibleRoot,
) -> tuple[ProtectedEligibility, ProtectedNotification]:
    source_bind_anchor(source, anchor, _anchor_allocation(namespace_registry, anchor))
    registered_hierarchy = registered_root_authority_publish(
        source.registered_root_authority_producer,
        root,
        observer_role_version=source.index.observer_role_version,
        source_security_epoch=source.index.source_security_epoch,
    )
    source_import_current_registered_root_authority(source, registered_hierarchy)
    relation = _qualified_clock_relation(source, anchor)
    eligibility = source_publish_anchor_enrollment_eligibility(
        source,
        root,
        exclusive_anchor_cutoff=100,
        source_clock_sample=BoundedClockSample(
            clock_id=source.index.source_clock_id,
            clock_epoch=source.index.source_clock_epoch,
            lower=0,
            upper=1,
        ),
        clock_relation=relation,
    )
    notification = anchor_enroll_root(
        anchor,
        namespace_registry,
        source,
        eligibility,
        anchor_clock_sample=BoundedClockSample(
            clock_id=anchor.anchor_clock_id,
            clock_epoch=anchor.anchor_clock_epoch,
            lower=30,
            upper=31,
        ),
        clock_relation=relation,
    )
    source_enroll_root(
        source,
        root,
        anchor=anchor,
        anchor_notification=notification,
        source_clock_sample=BoundedClockSample(
            clock_id=source.index.source_clock_id,
            clock_epoch=source.index.source_clock_epoch,
            lower=40,
            upper=41,
        ),
        clock_relation=relation,
    )
    return eligibility, notification


def _enroll_observer(
    observer: ObserverLocalStore,
    source: Source,
    root: EligibleRoot,
    *,
    anchor: Anchor | None = None,
) -> None:
    hierarchy = source.index.enrollment_hierarchies.get(root.audience_key)
    if hierarchy is None:
        raise Reject()
    observer_configure_namespace_producers(observer, source, anchor)
    observer_install_enrollment(observer, source, hierarchy, anchor=anchor)


def _authenticate_key(source: Source, key: StableKey) -> TransportContext:
    return transport_authenticate(
        source.transport_authority,
        connection_id="connection:" + key.requester_principal,
        authenticated_principal=key.requester_principal,
        replay_domain="replay:" + key.logical_source_id,
    )


def _issue(
    source: Source,
    key: StableKey,
    *,
    generation: str,
    slot: str,
    admission_key: str | None,
) -> SourceIndexEntry:
    transport_context = _authenticate_key(source, key)
    return source_issue(
        source,
        key,
        transport_context=transport_context,
        source_generation=generation,
        slot_id=slot,
        challenge_bytes=("challenge:" + key.request_operation).encode(),
        source_observer_capsule=("source-capsule:" + key.request_operation).encode(),
        source_producer_coordinate=("source-producer:" + key.request_operation),
        paired_frame_admission_key=admission_key,
    )


def _key_transport(source: Source, key: StableKey) -> TransportContext:
    slot_key, _, _ = _slot_for_entry(source, key)
    return source.generations.private_challenges[slot_key].transport_context


def _publish_handoff(
    source: Source, key: StableKey, result: HandoffResult
) -> ProtectedHandoff:
    _, _, slot = _slot_for_entry(source, key)
    record = source.queue.records[slot.paired_frame_admission_key or ""]
    return transport_publish_handoff_quiescence(
        source.transport_authority,
        record.transport_context,
        admission_key=record.admission_key,
        frame_digest=record.frame_digest,
        result=result,
    )


def _opaque_relay_binding(
    *, admission_key: str, observer_envelope_identity: str
) -> RelayBinding:
    return RelayBinding(
        observer_envelope_identity=observer_envelope_identity,
        observer_envelope_bytes_digest=hashlib.sha256(
            ("observer-envelope:" + observer_envelope_identity).encode()
        ).hexdigest(),
        observer_envelope_authentication_set_digest=hashlib.sha256(
            ("observer-envelope-auth:" + observer_envelope_identity).encode()
        ).hexdigest(),
        producer_coordinate="anchor-producer:" + admission_key,
    )


def _complete_isolation(namespace: tuple[str, str, str]) -> IsolationEvidence:
    return IsolationEvidence(
        source_namespace=namespace, surface_kinds=REQUIRED_ISOLATION_SURFACES
    )


def _complete_no_successor(source: Source) -> tuple[LineageStore, ProtectedNoSuccessor]:
    store = LineageStore()
    lineage_register_source(
        store, source.index.source_namespace, source.index.source_index_incarnation
    )
    return store, lineage_finalize_no_successor(
        store, source.index.source_namespace, source.index.source_index_incarnation
    )


def _isolation_inputs(
    namespace: tuple[str, str, str],
) -> tuple[tuple[IsolationSurface, IsolationReceipt], ...]:
    return tuple(
        (surface_store, isolation_surface_finalize(surface_store, namespace))
        for surface in REQUIRED_ISOLATION_SURFACES
        for surface_store in (
            IsolationSurface(surface, "configured-isolation-surface:" + surface),
        )
    )


def _complete_isolation_hierarchy(
    namespace: tuple[str, str, str],
) -> tuple[IsolationAuthority, ProtectedIsolation]:
    authority = IsolationAuthority(
        producer_credential=(_CONFIGURED_HIGHER_ROOT_ISOLATION_CREDENTIAL)
    )
    hierarchy = higher_root_publish_isolation(
        authority, _complete_isolation(namespace), _isolation_inputs(namespace)
    )
    return authority, hierarchy


def _source_resolution(source: Source, key: StableKey) -> ResolutionProof:
    tree = source_resolution_tree(source)
    entry = source.index.entries.get(key)
    if entry is None:
        return ResolutionProof(
            body=tree.proof(key, ProofKind.NONMEMBERSHIP),
            proof_kind=ProofKind.NONMEMBERSHIP,
            source_entry=None,
            anchor_entry=None,
            claimed_outcome=(ResolutionOutcome.SOURCE_FROZEN_KEY_NONMEMBERSHIP),
        )
    if entry.kind is IndexEntryKind.CANCELED_BEFORE_ISSUANCE:
        outcome = ResolutionOutcome.SOURCE_FROZEN_CANCELED_MEMBERSHIP
    else:
        outcome = ResolutionOutcome.PRESERVE_EXACT_TERMINAL
    return ResolutionProof(
        body=tree.proof(key, ProofKind.MEMBERSHIP),
        proof_kind=ProofKind.MEMBERSHIP,
        source_entry=entry,
        anchor_entry=None,
        claimed_outcome=outcome,
    )


def _anchor_resolution(
    anchor: Anchor, key: StableKey, *, attempt_present: bool
) -> ResolutionProof:
    tree = anchor_resolution_tree(anchor)
    entry = anchor.entries.get(key)
    if attempt_present:
        outcome = ResolutionOutcome.PRESERVE_EXACT_TERMINAL
    elif entry is None:
        outcome = ResolutionOutcome.ANCHOR_FROZEN_NONMEMBERSHIP
    else:
        outcome = ResolutionOutcome.ANCHOR_FROZEN_MEMBERSHIP
    return ResolutionProof(
        body=tree.proof(
            key, (ProofKind.NONMEMBERSHIP if entry is None else ProofKind.MEMBERSHIP)
        ),
        proof_kind=(ProofKind.NONMEMBERSHIP if entry is None else ProofKind.MEMBERSHIP),
        source_entry=None,
        anchor_entry=entry,
        claimed_outcome=outcome,
    )


def scenario_closed_enum_matrix(harness: Harness) -> None:
    specs = _CLOSED_FIELDS + _CLOSED_MAP_VALUE_FIELDS
    owners = {owner for owner, _, _ in specs}

    def semantic_value(hint: object) -> object:
        arguments = get_args(hint)
        if type(None) in arguments:
            return None
        origin = get_origin(hint)
        if origin in (dict, list, tuple, set):
            return origin()
        if arguments:
            return semantic_value(arguments[0])
        if hint in _CANONICAL_DATACLASS_TYPES:
            return shell(hint)
        if hint in _CANONICAL_ENUM_TYPES:
            return next(iter(hint))
        if hint in _CANONICAL_OPAQUE_TYPES or hint in (bool, int, str, bytes):
            return hint()
        raise AssertionError(hint)

    def shell(owner: type[object], *, all_none: bool = False) -> object:
        value = object.__new__(owner)
        for name, hint in _FIELD_HINTS[owner].items():
            object.__setattr__(value, name, None if all_none else semantic_value(hint))
        return value

    def hostile_type(owner: type[object]) -> type[object]:
        return type("Hostile" + owner.__name__, (owner,), {})

    class HostileEnum(StrEnum):
        VALUE = "VALUE"

    def graph_rejects(value: object) -> bool:
        try:
            _validate_closed_graph(value)
        except Reject:
            return True
        return False

    def captures_reject(value: object) -> bool:
        operations = (
            lambda: value,
            lambda value=value: value,
            lambda *, value=value: value,
        )
        for operation in operations:
            try:
                _validate_captures(operation)
            except Reject:
                continue
            return False
        return True

    def fixture(owner: type[object], name: str, hostile: object) -> object:
        value = shell(owner)
        if any(
            owner is candidate and name == field
            for candidate, field, _ in _CLOSED_MAP_VALUE_FIELDS
        ):
            hostile = {"fixture": hostile}
        object.__setattr__(value, name, hostile)
        return value

    complete = {owner: shell(owner) for owner in _CANONICAL_DATACLASS_TYPES}
    _validate_source_registry(SourceRegistry())
    _validate_closed_graph(tuple(shell(owner) for owner in owners))
    enum_types = {
        value
        for value in globals().values()
        if isinstance(value, type)
        and value is not StrEnum
        and issubclass(value, StrEnum)
    }
    declared_direct = set()
    declared_maps = set()
    for owner, hints in _FIELD_HINTS.items():
        for name, hint in hints.items():
            if isinstance(hint, type) and issubclass(hint, StrEnum):
                declared_direct.add((owner, name, hint))
            elif get_origin(hint) is dict:
                value_type = get_args(hint)[1]
                if isinstance(value_type, type) and issubclass(value_type, StrEnum):
                    declared_maps.add((owner, name, value_type))
    harness.check(
        "closed_enum_matrix_covers_every_declared_enum_field_and_capture_boundary",
        {enum_type for _, _, enum_type in specs} == enum_types
        and set(_CLOSED_FIELDS) == declared_direct
        and set(_CLOSED_MAP_VALUE_FIELDS) == declared_maps
        and owners <= _CANONICAL_DATACLASS_TYPES
        and all(name in owner.__dataclass_fields__ for owner, name, _ in specs)
        and all(
            captures_reject(fixture(owner, name, hostile))
            for owner, name, enum_type in specs
            for hostile in (
                "UNKNOWN_DEFAULT",
                str(next(iter(enum_type))),
                hostile_type(str)(str(next(iter(enum_type)))),
                HostileEnum.VALUE,
                None,
            )
        ),
    )
    harness.check(
        "closed_graph_completeness_matrix_covers_and_accepts_optional_none_forms",
        len(_CANONICAL_DATACLASS_TYPES) == 76
        and all(
            set(_FIELD_HINTS[owner]) == set(owner.__dataclass_fields__)
            and _REQUIRED_FIELDS[owner]
            and not graph_rejects(value)
            and all(
                getattr(value, name) is None
                for name in _FIELD_HINTS[owner].keys() - _REQUIRED_FIELDS[owner]
            )
            for owner, value in complete.items()
        ),
    )
    harness.check(
        "closed_graph_rejects_all_76_all_none_and_each_required_none_shell",
        all(
            graph_rejects(shell(owner, all_none=True))
            for owner in _CANONICAL_DATACLASS_TYPES
        )
        and all(
            graph_rejects(
                replace(
                    value,
                    **{name: None},
                )
            )
            for owner, value in complete.items()
            for name in _REQUIRED_FIELDS[owner]
        ),
    )
    for owner, name, _ in specs:
        for label, hostile in (("UNKNOWN_DEFAULT", "UNKNOWN_DEFAULT"), ("NONE", None)):
            harness.reject(
                "closed_enum_rejects_" + owner.__name__ + "_" + name + "_" + label,
                lambda value=fixture(owner, name, hostile): _validate_closed_graph(
                    value
                ),
            )
    harness.check(
        "closed_graph_rejects_all_76_dataclass_subclasses",
        all(
            graph_rejects(object.__new__(hostile_type(owner)))
            for owner in _CANONICAL_DATACLASS_TYPES
        ),
    )
    harness.check(
        "closed_graph_rejects_all_9_opaque_subclasses",
        all(
            graph_rejects(object.__new__(hostile_type(owner)))
            for owner in _CANONICAL_OPAQUE_TYPES
        ),
    )
    harness.check(
        "closed_graph_and_atomic_captures_reject_container_scalar_enum_subclasses",
        all(
            graph_rejects(hostile_type(owner)())
            and captures_reject(hostile_type(owner)())
            for owner in (dict, list, tuple, set, int, str, bytes)
        )
        and graph_rejects(HostileEnum.VALUE)
        and captures_reject(HostileEnum.VALUE),
    )
    for owner, value in (
        (HandoffAttempt, object.__new__(hostile_type(HandoffAttempt))),
        (str, hostile_type(str)()),
        (bytes, hostile_type(bytes)()),
    ):
        harness.reject(
            "result_boundary_rejects_" + owner.__name__ + "_subclass",
            lambda owner=owner, value=value: _require_result_type(value, owner),
        )
    for label, operation in (
        ("identifier", lambda: _identifier(hostile_type(str)("x"))),
        ("u64", lambda: _u64(hostile_type(int)(1))),
        ("lp", lambda: _lp(hostile_type(bytes)(b"x"))),
        ("json", lambda: _encoded_json_value(hostile_type(dict)())),
        (
            "namespace",
            lambda: _validate_namespace(
                hostile_type(tuple)(("realm", "SIMULATION", "source"))
            ),
        ),
        ("frame", lambda: _parse_requester_frame(hostile_type(bytes)(b"{}"))),
    ):
        harness.reject("primitive_boundary_rejects_" + label + "_subclass", operation)
    observer = ObserverLocalStore("closed-type-root", "closed-type-incarnation")
    bundle = ClosureBundle(
        ("closed-type-realm", "SIMULATION", "closed-type-source"),
        SOURCE_ONLY,
        ProofContext.SOURCE,
        b"",
        (),
        ClosureOrigin.SOURCE,
        AnchorClosureCause.NO_ANCHOR_CLOSURE,
    )
    for owner in (Source, Anchor):
        hostile = hostile_type(owner)
        harness.reject(
            "producer_dispatch_rejects_" + owner.__name__ + "_subclass",
            lambda hostile=hostile: observer_import_closure(
                observer, object.__new__(hostile), bundle, {}
            ),
        )
    for owner in (IntentCancellation, NamespaceCancellation):
        projection = object.__new__(hostile_type(owner))
        hierarchy = shell(ProtectedCancellation)
        object.__setattr__(hierarchy, "projection", projection)
        harness.reject(
            "cancellation_dispatch_rejects_" + owner.__name__ + "_subclass",
            lambda hierarchy=hierarchy: _validate_cancellation(hierarchy),
        )
    namespace = ("realm-closed-enum", "SIMULATION", "source-closed-enum")
    for label, profile in (("unknown_default", "UNKNOWN_DEFAULT"), ("none", None)):
        harness.reject(
            "new_source_rejects_" + label + "_profile",
            lambda profile=profile: new_source(namespace, profile),
        )
    root = _root(
        root_id="observer-root-closed-enum",
        incarnation="observer-root-closed-enum-v1",
        profile=SOURCE_ONLY,
    )
    hostile_root = hostile_type(EligibleRoot)(**root.__dict__)
    object.__setattr__(hostile_root, "availability_profile", "UNKNOWN_DEFAULT")
    harness.reject(
        "root_validator_rejects_eligible_root_subclass_with_unknown_profile",
        lambda: _validate_root(hostile_root),
    )
    hostile_store = hostile_type(TransportStore)()
    hostile_store.channel_states["hostile-channel"] = "UNKNOWN_DEFAULT"
    harness.reject(
        "transport_validator_rejects_store_subclass_with_unknown_channel_state",
        lambda: _validate_transport(hostile_store),
    )
    transport = TransportStore()
    context = transport_authenticate(
        transport,
        connection_id="closed-type-connection",
        authenticated_principal="closed-type-principal",
        replay_domain="closed-type-replay",
    )
    transport.contexts[context.verification_digest] = replace(
        context, live_channel_handle=hostile_type(OpaqueLiveTransportHandle)()
    )
    harness.reject(
        "transport_validator_rejects_live_handle_subclass",
        lambda: _validate_transport(transport),
    )
    source = new_source(namespace, SOURCE_ONLY)
    _enroll_source(source, root)
    key = _key(namespace, root.root_incarnation, "closed-enum")
    _issue(
        source,
        key,
        generation="closed-generation",
        slot="closed-slot",
        admission_key=None,
    )
    source_cancel_available(source, key, transport_context=_key_transport(source, key))
    for label, hostile in (("unknown_default", "UNKNOWN_DEFAULT"), ("none", None)):
        candidate = copy.deepcopy(source)
        _, _, slot = _slot_for_entry(candidate, key)
        slot.state = hostile
        slot.delivery_gate = DeliveryGate.DELIVERY_TERMINAL
        harness.reject(
            "source_freeze_rejects_" + label + "_slot_state",
            lambda candidate=candidate: source_freeze(candidate),
        )
    candidate = copy.deepcopy(source)
    generation, slot_id, slot = _slot_for_entry(candidate, key)
    hostile_slot = hostile_type(FreshnessSlot)(**slot.__dict__)
    hostile_slot.state = "UNKNOWN_DEFAULT"
    hostile_slot.delivery_gate = DeliveryGate.DELIVERY_TERMINAL
    candidate.generations.slots[(generation, slot_id)] = hostile_slot
    harness.reject(
        "source_freeze_rejects_terminal_freshness_slot_subclass",
        lambda: source_freeze(candidate),
    )
    candidate = copy.deepcopy(source)
    candidate.generations.slots[(generation, slot_id)] = shell(
        FreshnessSlot, all_none=True
    )
    harness.reject(
        "source_freeze_rejects_all_none_exact_freshness_slot",
        lambda: source_freeze(candidate),
    )
    harness.witness("closed_types_reject_unknown_none_and_subclasses")


def scenario_namespace_anchor_bootstrap_races(harness: Harness) -> None:
    anchor_authority = "bootstrap-anchor-authority"

    def intent_for(suffix: str, *, owner: str = "bootstrap-owner") -> ReservationIntent:
        intent = ReservationIntent(
            source_namespace=(
                "realm-bootstrap-" + suffix,
                "SIMULATION",
                "source-bootstrap-" + suffix,
            ),
            reservation_intent_id="intent-" + suffix,
            source_owner_key=owner,
            source_owner_lifetime_slot="owner-slot-" + suffix,
            lineage_selector_incarnation="lineage-" + suffix,
            source_index_selector_incarnation="source-index-" + suffix,
            anchor_selector_incarnation="anchor-" + suffix,
            availability_profile=(ANCHOR_PROFILE),
            anchor_authority=anchor_authority,
            commit_digest="",
        )
        return replace(
            intent, commit_digest=("source-intent:" + _intent_digest(intent))
        )

    def pending_bootstrap(
        suffix: str,
    ) -> tuple[
        SourceRegistry,
        AuthorityRegistry,
        ReservationIntent,
        NamespaceAllocation,
        ProtectedIntent,
        ProtectedAllocation,
    ]:
        source = SourceRegistry()
        intent = intent_for(suffix)
        intent_hierarchy = source_prepare_reservation(source, intent)
        anchor = AuthorityRegistry(anchor_authority=anchor_authority)
        reservation_id = "reservation-" + suffix
        reservation = IndependentAnchorNamespaceCapacityReservation(
            intent, reservation_id, _reservation_receipt_digest(intent, reservation_id)
        )
        reservation_hierarchy = anchor_reserve_namespace_capacity(
            anchor, source, reservation, intent_hierarchy
        )
        allocation = NamespaceAllocation(
            intent.source_namespace,
            "allocation-" + suffix,
            intent.lineage_selector_incarnation,
            intent.source_index_selector_incarnation,
            intent.anchor_selector_incarnation,
            intent.availability_profile,
            intent.anchor_authority,
            reservation,
        )
        allocation_hierarchy = source_allocate_namespace(
            source, anchor, allocation, reservation_hierarchy
        )
        return (
            source,
            anchor,
            intent,
            allocation,
            intent_hierarchy,
            allocation_hierarchy,
        )

    (
        source,
        anchor_registry,
        intent,
        allocation,
        intent_hierarchy,
        allocation_hierarchy,
    ) = pending_bootstrap("success")
    harness.check(
        "intent_retry_after_allocation_returns_exact_retained_hierarchy",
        source_prepare_reservation(source, intent) == intent_hierarchy,
    )
    harness.reject(
        "allocation_rejects_oversized_reservation_receipt_before_charge",
        lambda: _require_allocation(
            replace(
                allocation,
                anchor_reservation=replace(
                    allocation.anchor_reservation, receipt_digest="x" * 300_000
                ),
            )
        ),
    )
    changed_epoch_registry = copy.deepcopy(anchor_registry)
    changed_epoch_registry.security_epoch = "anchor-namespace-security-v2"
    harness.reject(
        "bootstrap_rejects_registry_epoch_substitution",
        lambda: _validate_authority_registry(changed_epoch_registry),
    )
    anchor_store = Anchor(
        source_namespace=intent.source_namespace,
        anchor_authority=intent.anchor_authority,
        anchor_selector_incarnation=intent.anchor_selector_incarnation,
        producer_credential=anchor_registry.producer_credential,
    )
    genesis = anchor_create_from_source_allocation(
        anchor_registry, anchor_store, source, allocation_hierarchy
    )
    harness.reject(
        "anchor_activation_rejects_unregistered_source",
        lambda: anchor_activate_registered_namespace(
            copy.deepcopy(anchor_registry), copy.deepcopy(anchor_store), source, genesis
        ),
    )
    source_register_namespace(source, anchor_registry, anchor_store, genesis)
    harness.check(
        "source_registration_does_not_mutate_independent_anchor_head",
        source.state is SourceBootstrap.LIVE
        and anchor_store.phase is AnchorPhase.PENDING_SOURCE_CONFIRMATION,
    )
    anchor_activate_registered_namespace(anchor_registry, anchor_store, source, genesis)
    anchor_activate_registered_namespace(anchor_registry, anchor_store, source, genesis)
    harness.check(
        "anchor_activation_requires_prior_exact_source_registration",
        anchor_store.phase is AnchorPhase.OPEN
        and _authority_slot(anchor_registry, intent).reservation_state
        is ReservationState.MATERIALIZED,
    )
    harness.reject(
        "live_namespace_rejects_delayed_cancellation",
        lambda: source_cancel_pending_namespace(source),
    )

    (
        cancel_source,
        cancel_registry,
        cancel_intent,
        _,
        _,
        cancel_allocation_hierarchy,
    ) = pending_bootstrap("cancel-before-genesis")
    cancellation = source_cancel_pending_namespace(cancel_source)
    cancellation_receipt = anchor_import_source_namespace_cancellation(
        cancel_registry, cancel_source, cancellation
    )
    harness.check(
        "cancellation_before_genesis_installs_terminal_selector",
        _authority_slot(cancel_registry, cancel_intent).reservation_state
        is ReservationState.TERMINAL,
    )
    harness.check(
        "anchor_cancellation_exact_retry_is_idempotent",
        anchor_import_source_namespace_cancellation(
            cancel_registry, cancel_source, cancellation
        )
        == cancellation_receipt,
    )
    harness.reject(
        "delayed_genesis_loses_to_cancellation",
        lambda: anchor_create_from_source_allocation(
            cancel_registry,
            Anchor(
                cancel_intent.source_namespace,
                anchor_authority=cancel_intent.anchor_authority,
                anchor_selector_incarnation=(cancel_intent.anchor_selector_incarnation),
                producer_credential=cancel_registry.producer_credential,
            ),
            cancel_source,
            cancel_allocation_hierarchy,
        ),
    )

    (
        orphan_source,
        orphan_registry,
        orphan_intent,
        _,
        _,
        orphan_allocation_hierarchy,
    ) = pending_bootstrap("cancel-after-genesis")
    orphan_anchor = Anchor(
        orphan_intent.source_namespace,
        anchor_authority=orphan_intent.anchor_authority,
        anchor_selector_incarnation=orphan_intent.anchor_selector_incarnation,
        producer_credential=orphan_registry.producer_credential,
    )
    anchor_create_from_source_allocation(
        orphan_registry, orphan_anchor, orphan_source, orphan_allocation_hierarchy
    )
    orphan_cancellation = source_cancel_pending_namespace(orphan_source)
    counterfeit_cancellation = replace(
        orphan_cancellation, producer_credential=OpaqueStateOwnerCredential()
    )
    harness.reject(
        "anchor_rejects_counterfeit_source_cancellation",
        lambda: anchor_import_source_namespace_cancellation(
            orphan_registry,
            orphan_source,
            counterfeit_cancellation,
            anchor_store=orphan_anchor,
        ),
    )
    nonempty_registry = copy.deepcopy(orphan_registry)
    nonempty_anchor = copy.deepcopy(orphan_anchor)
    nonempty_anchor.in_flight_mutations.add("pending")
    _authority_slot(nonempty_registry, orphan_intent).in_flight_count = 1
    harness.reject(
        "actual_nonempty_anchor_blocks_namespace_cancellation",
        lambda: anchor_import_source_namespace_cancellation(
            nonempty_registry,
            orphan_source,
            orphan_cancellation,
            anchor_store=nonempty_anchor,
        ),
    )
    anchor_import_source_namespace_cancellation(
        orphan_registry, orphan_source, orphan_cancellation, anchor_store=orphan_anchor
    )
    harness.check(
        "actual_anchor_and_parent_cancel_in_one_anchor_transaction",
        orphan_anchor.phase is AnchorPhase.CANCELED
        and _authority_slot(orphan_registry, orphan_intent).state
        is AnchorBootstrap.CANCELED,
    )
    detached = copy.deepcopy(_authority_slot(orphan_registry, orphan_intent))
    detached.in_flight_count = 1
    harness.check(
        "detached_slot_mutation_cannot_change_authoritative_parent",
        _authority_slot(orphan_registry, orphan_intent).in_flight_count == 0
        and detached.in_flight_count == 1,
    )

    capacity_registry = AuthorityRegistry(anchor_authority=anchor_authority)
    capacity_owner = "bounded-owner"

    def terminalize_intent(candidate_intent: ReservationIntent) -> None:
        candidate_source = SourceRegistry()
        source_prepare_reservation(candidate_source, candidate_intent)
        anchor_import_source_reservation_intent_cancellation(
            capacity_registry,
            candidate_source,
            source_cancel_namespace_reservation_intent(candidate_source),
        )

    for index in range(ANCHOR_OWNER_PARTICIPANT_CAP):
        terminalize_intent(intent_for("capacity-" + str(index), owner=capacity_owner))
    harness.check(
        "terminal_slots_never_refund_owner_capacity",
        capacity_registry.owner_participant_units_charged[capacity_owner]
        == ANCHOR_OWNER_PARTICIPANT_CAP
        and capacity_registry.owner_bytes_charged[capacity_owner]
        == ANCHOR_OWNER_BYTE_CAP,
    )
    cap_source = SourceRegistry()
    cap_intent = intent_for("capacity-plus-one", owner=capacity_owner)
    source_prepare_reservation(cap_source, cap_intent)
    cap_cancellation = source_cancel_namespace_reservation_intent(cap_source)
    harness.reject(
        "owner_capacity_is_nonborrowable_after_terminalization",
        lambda: anchor_import_source_reservation_intent_cancellation(
            capacity_registry, cap_source, cap_cancellation
        ),
    )
    retirement_receipt = anchor_finalize_authority_domain_retirement(capacity_registry)
    harness.check(
        "authority_retirement_exact_retry_covers_every_terminal_slot",
        anchor_finalize_authority_domain_retirement(capacity_registry)
        == retirement_receipt,
    )
    post_source = SourceRegistry()
    post_intent = intent_for("post-retirement", owner="post-owner")
    source_prepare_reservation(post_source, post_intent)
    post_cancellation = source_cancel_namespace_reservation_intent(post_source)
    harness.reject(
        "authority_retirement_rejects_every_new_slot",
        lambda: anchor_import_source_reservation_intent_cancellation(
            capacity_registry, post_source, post_cancellation
        ),
    )
    harness.reject(
        "authority_retirement_rejects_a_nonterminal_slot",
        lambda: anchor_finalize_authority_domain_retirement(anchor_registry),
    )
    harness.accept("namespace_anchor_registration_wins")
    harness.accept("namespace_cancellation_races_are_terminal")
    harness.accept("authority_wide_capacity_and_retirement")
    harness.witness("source_confirmation_precedes_independent_anchor_activation")
    harness.witness("terminal_namespace_slots_never_refund_capacity")
    harness.witness("owner_capacity_is_nonborrowable")
    harness.witness("cancellation_and_genesis_share_the_anchor_selector")


def scenario_root_enrollment_handshake_races(harness: Harness) -> None:
    namespace = ("realm-enrollment", "SIMULATION", "source-enrollment")
    profile = ANCHOR_PROFILE
    root = _root(
        root_id="observer-root-enrollment",
        incarnation="observer-root-enrollment-v1",
        profile=profile,
    )
    source = new_source(namespace, profile, eligible_capacity=1)
    anchor = new_anchor(namespace)
    registry = materialized_anchor_registry(
        anchor, source, coordinate_suffix="enrollment"
    )
    source_bind_anchor(source, anchor, _anchor_allocation(registry, anchor))
    registered = registered_root_authority_publish(
        source.registered_root_authority_producer,
        root,
        observer_role_version=source.index.observer_role_version,
        source_security_epoch=source.index.source_security_epoch,
    )
    source_import_current_registered_root_authority(source, registered)
    relation = _qualified_clock_relation(source, anchor)
    eligibility = source_publish_anchor_enrollment_eligibility(
        source,
        root,
        exclusive_anchor_cutoff=100,
        source_clock_sample=BoundedClockSample(
            source.index.source_clock_id, source.index.source_clock_epoch, 0, 1
        ),
        clock_relation=relation,
    )
    harness.reject(
        "anchor_enrollment_rejects_strict_cutoff_equality",
        lambda: anchor_enroll_root(
            anchor,
            registry,
            source,
            eligibility,
            anchor_clock_sample=BoundedClockSample(
                anchor.anchor_clock_id, anchor.anchor_clock_epoch, 100, 100
            ),
            clock_relation=relation,
        ),
    )
    notification = anchor_enroll_root(
        anchor,
        registry,
        source,
        eligibility,
        anchor_clock_sample=BoundedClockSample(
            anchor.anchor_clock_id, anchor.anchor_clock_epoch, 30, 31
        ),
        clock_relation=relation,
    )
    pending_key = _key(namespace, root.root_incarnation, "pending-enrollment")
    harness.reject(
        "anchor_enrollment_alone_never_authorizes_source_issuance",
        lambda: _issue(
            source,
            pending_key,
            generation="generation-pending",
            slot="slot-pending",
            admission_key="admission-pending",
        ),
    )
    source_enroll_root(
        source,
        root,
        anchor=anchor,
        anchor_notification=notification,
        source_clock_sample=BoundedClockSample(
            source.index.source_clock_id, source.index.source_clock_epoch, 40, 41
        ),
        clock_relation=relation,
    )
    harness.check(
        "two_stage_enrollment_requires_both_producer_commits",
        root.audience_key in anchor.eligible_roots
        and root.audience_key in source.index.eligible_roots
        and source.index.root_admissions[root.audience_key].phase
        is RootAdmissionPhase.ELIGIBLE,
    )
    harness.check(
        "anchor_enrollment_exact_retry_returns_retained_notification",
        anchor_enroll_root(
            anchor,
            registry,
            source,
            eligibility,
            anchor_clock_sample=BoundedClockSample(
                anchor.anchor_clock_id, anchor.anchor_clock_epoch, 30, 31
            ),
            clock_relation=relation,
        )
        == notification,
    )
    counterfeit_source = copy.deepcopy(source)
    counterfeit_source.index.source_security_epoch = "source-security-v2"
    harness.reject(
        "anchor_rejects_changed_source_security_epoch_after_genesis",
        lambda: anchor_append(
            anchor,
            registry,
            counterfeit_source,
            _issue(
                counterfeit_source,
                pending_key,
                generation="generation-counterfeit",
                slot="slot-counterfeit",
                admission_key="admission-counterfeit",
            ),
            intended_observer_root_id=root.root_id,
            mapped_acceptance_cutoff=100,
            anchor_clock_sample=_anchor_sample(anchor),
        ),
    )
    observer = ObserverLocalStore(root.root_id, root.root_incarnation)
    _enroll_observer(observer, source, root, anchor=anchor)
    changed_source = copy.deepcopy(source)
    changed_source.index.source_security_epoch = "source-security-v2"
    harness.reject(
        "observer_rejects_pinned_source_epoch_rebinding",
        lambda: observer_configure_namespace_producers(
            observer, changed_source, anchor
        ),
    )
    harness.accept("observer_root_enrollment_two_stage_handshake")
    harness.accept("observer_root_enrollment_cutoff_race")
    harness.witness("anchor_enrollment_never_substitutes_for_source_confirmation")
    harness.witness("source_anchor_and_observer_pin_exact_producer_epochs")


def scenario_profile_and_enrollment(harness: Harness) -> None:
    namespace = ("realm-profile", "SIMULATION", "source-profile")
    source_only = _root(
        root_id="observer-root",
        incarnation="observer-root-source-only-v1",
        profile=SOURCE_ONLY,
    )
    source = new_source(namespace, SOURCE_ONLY, eligible_capacity=1)
    _enroll_source(source, source_only)
    _enroll_source(source, source_only)
    harness.check(
        "exact_source_enrollment_retry_is_idempotent",
        len(source.index.eligible_roots) == 1,
    )

    changed = copy.deepcopy(source_only)
    object.__setattr__(
        changed, "source_enrollment_hierarchy_digest", "changed-source-enrollment"
    )
    before = copy.deepcopy(source)
    harness.reject(
        "changed_source_enrollment_retry", lambda: _enroll_source(source, changed)
    )
    harness.check("failed_changed_enrollment_is_atomic", source == before)

    wrong_profile_root = _root(
        root_id="observer-root-2",
        incarnation="observer-root-anchor-v1",
        profile=ANCHOR_PROFILE,
    )
    harness.reject(
        "source_only_store_rejects_anchor_profile_root",
        lambda: _enroll_source(source, wrong_profile_root),
    )
    harness.reject(
        "eligible_root_cap_plus_one",
        lambda: _enroll_source(
            source,
            _root(
                root_id="observer-root-3",
                incarnation="observer-root-source-only-v2",
                profile=SOURCE_ONLY,
            ),
        ),
    )
    harness.reject(
        "unknown_availability_profile", lambda: Availability("UNKNOWN_DEFAULT")
    )
    harness.check(
        "closed_availability_profile_names_are_exact",
        {profile.value for profile in Availability}
        == {
            "SOURCE_RETIREMENT_ONLY",
            "SOURCE_RETIREMENT_OR_INDEPENDENT_CHALLENGE_EXPOSURE_ANCHOR",
        },
    )
    harness.reject(
        "plant_source_requires_content_addressed_profile",
        lambda: new_source(
            ("realm-plant", "PLANT", "source-plant"),
            SOURCE_ONLY,
        ),
    )
    plant_namespace = ("realm-plant", "PLANT", "source-plant")
    body_profile_authority = BodyPlantProfileAuthorityStore()
    plant_profile_hierarchy = body_publish_installed_plant_profile(
        body_profile_authority,
        plant_namespace,
        source_authority_id="source-authority-v1",
        source_index_incarnation="source-index-v1",
        profile_id="plant-profile-alpha",
        profile_revision="plant-profile-alpha-v1",
        profile_document=(b'{"hold_policy":"profile-defined","rate_limit_hz":100}'),
    )
    harness.reject(
        "simulation_source_forbids_plant_profile",
        lambda: new_source(
            namespace,
            SOURCE_ONLY,
            plant_profile_hierarchy=plant_profile_hierarchy,
        ),
    )
    harness.reject(
        "plant_source_rejects_caller_substituted_profile_digest",
        lambda: new_source(
            plant_namespace,
            SOURCE_ONLY,
            plant_profile_hierarchy=replace(
                plant_profile_hierarchy, plant_profile_digest="11" * 32
            ),
        ),
    )
    harness.reject(
        "plant_source_rejects_changed_body_enrollment_ancestry",
        lambda: new_source(
            plant_namespace,
            SOURCE_ONLY,
            plant_profile_hierarchy=replace(
                plant_profile_hierarchy,
                profile=replace(
                    plant_profile_hierarchy.profile, body_enrollment_digest="22" * 32
                ),
            ),
        ),
    )
    plant = new_source(
        plant_namespace,
        SOURCE_ONLY,
        plant_profile_hierarchy=plant_profile_hierarchy,
    )
    plant_root = _root(
        root_id="plant-observer",
        incarnation="plant-observer-v1",
        profile=SOURCE_ONLY,
    )
    _enroll_source(plant, plant_root)
    plant_entry = _issue(
        plant,
        _key(plant.index.source_namespace, plant_root.root_incarnation, "plant"),
        generation="plant-generation",
        slot="plant-slot",
        admission_key=None,
    )
    harness.check(
        "typed_body_owned_plant_profile_binds_entry_and_requester_frame",
        plant_entry.plant_profile_digest
        == plant_profile_hierarchy.profile.content_digest
        and plant_entry.plant_profile_digest
        == plant_profile_hierarchy.plant_profile_digest
        and b'"plant_profile_digest":"'
        in source_delivery_view(
            plant,
            plant_entry.stable_key,
            transport_context=_key_transport(plant, plant_entry.stable_key),
        ).frame_bytes,
    )
    harness.reject(
        "source_identifiers_are_bounded_before_semantic_allocation",
        lambda: _validate_source(
            replace(
                source, index=replace(source.index, source_security_epoch="🧠" * 65)
            )
        ),
    )
    harness.reject(
        "observer_rejects_enrollment_capacity_above_manifest",
        lambda: _validate_observer(
            ObserverLocalStore(
                "observer",
                "observer-v1",
                enrollment_capacity=MAX_OBSERVER_ENROLLMENTS + 1,
            )
        ),
    )
    harness.accept("profile_and_enrollment_product")
    harness.witness("exact_closed_availability_profile_product")


def scenario_registered_root_retirement_currentness(harness: Harness) -> None:
    namespace = ("realm-root-retirement", "SIMULATION", "source-root-retirement")
    root = _root(
        root_id="observer-root-retirement",
        incarnation="observer-root-retirement-v1",
        profile=SOURCE_ONLY,
    )
    source = new_source(namespace, SOURCE_ONLY)
    _enroll_source(source, root)
    key = _key(namespace, root.root_incarnation, "issue-before-retirement")
    _issue(
        source,
        key,
        generation="generation-retirement",
        slot="slot-retirement",
        admission_key=None,
    )
    context = _key_transport(source, key)
    frame = source_delivery_view(source, key, transport_context=context).frame_bytes
    if frame is None:
        raise AssertionError("active source-only delivery frame missing")

    source_begin_registered_root_retirement(source, root.audience_key)
    source_begin_registered_root_retirement(source, root.audience_key)
    harness.reject(
        "root_retirement_pending_blocks_new_grant_acceptance",
        lambda: source_accept(
            source,
            key,
            transport_context=context,
            requester_frame=frame,
            source_clock_sample=_source_sample(source),
        ),
    )
    harness.check(
        "root_retirement_pending_suppresses_challenge_delivery",
        source_delivery_view(source, key, transport_context=context)
        == DeliveryView("REGISTERED_ROOT_AUTHORITY_NOT_CURRENT", None),
    )
    source_cancel_available(source, key, transport_context=context)
    source_complete_registered_root_retirement(source, root.audience_key)
    source_complete_registered_root_retirement(source, root.audience_key)
    closure = source_freeze(source)
    harness.check(
        "retired_registered_root_remains_in_frozen_closure_audience",
        closure.audience == (root.audience_key,) and key in source.index.entries,
    )

    retirement_first = new_source(namespace, SOURCE_ONLY)
    _enroll_source(retirement_first, root)
    source_begin_registered_root_retirement(retirement_first, root.audience_key)
    harness.reject(
        "root_retirement_first_blocks_new_challenge_issuance",
        lambda: _issue(
            retirement_first,
            _key(namespace, root.root_incarnation, "retirement-first"),
            generation="generation-retirement-first",
            slot="slot-retirement-first",
            admission_key=None,
        ),
    )
    harness.accept("registered_root_retirement_currentness_race")
    harness.witness("retirement_preserves_enrollment_for_closure_not_new_authority")


def scenario_local_prepare_and_closure_races(harness: Harness) -> None:
    namespace = ("realm-race", "SIMULATION", "source-race")
    root = _root(
        root_id="observer-root-race",
        incarnation="observer-root-race-v1",
        profile=SOURCE_ONLY,
    )
    source = new_source(namespace, SOURCE_ONLY)
    _enroll_source(source, root)
    observer = ObserverLocalStore(root.root_id, root.root_incarnation)
    _enroll_observer(observer, source, root)
    closure = source_freeze(source)

    key = _key(namespace, root.root_incarnation, "prepare-before-import")
    observer_prepare(observer, key)
    harness.check(
        "remote_source_freeze_does_not_veto_local_prepare",
        observer.operations[key].state is OperationState.INTENT_PREPARED,
    )
    observer_import_closure(
        observer, source, closure, {key: _source_resolution(source, key)}
    )
    harness.check(
        "prepare_first_operation_resolves_in_import_partition",
        observer.operations[key].state is OperationState.RESOLVED_WITHOUT_INSTALLATION,
    )
    harness.check(
        "source_nonmembership_resolution_is_exact",
        observer.operations[key].resolution_outcome
        is ResolutionOutcome.SOURCE_FROZEN_KEY_NONMEMBERSHIP,
    )
    harness.reject(
        "prepare_after_local_closure_import",
        lambda: observer_prepare(
            observer, _key(namespace, root.root_incarnation, "after-import")
        ),
    )

    import_first = ObserverLocalStore(root.root_id, root.root_incarnation)
    _enroll_observer(import_first, source, root)
    wrong_origin = replace(closure, origin=ClosureOrigin.ANCHOR)
    before = copy.deepcopy(import_first)
    harness.reject(
        "closure_context_origin_substitution",
        lambda: observer_import_closure(import_first, source, wrong_origin, {}),
    )
    harness.check(
        "failed_closure_origin_substitution_is_atomic", import_first == before
    )
    observer_import_closure(import_first, source, closure, {})
    harness.reject(
        "closure_first_blocks_later_prepare",
        lambda: observer_prepare(
            import_first, _key(namespace, root.root_incarnation, "closure-first")
        ),
    )
    harness.check(
        "retired_external_registry_cannot_shrink_frozen_audience",
        closure.audience == (root.audience_key,),
    )
    harness.accept("prepare_first_local_import_race")
    harness.accept("closure_first_local_import_race")
    harness.witness("remote_freeze_does_not_order_observer_local_prepare")
    harness.witness("closure_import_is_the_local_prepare_linearization")
    harness.witness("retained_audience_outlives_current_registration")


def scenario_slot_lifecycle_and_source_freeze(harness: Harness) -> None:
    def empty_source(label: str) -> tuple[Source, EligibleRoot]:
        namespace = ("realm-" + label, "SIMULATION", "source-" + label)
        root = _root(
            root_id="observer-root-" + label,
            incarnation="observer-root-" + label + "-v1",
            profile=SOURCE_ONLY,
        )
        source = new_source(namespace, SOURCE_ONLY)
        _enroll_source(source, root)
        return source, root

    source, root = empty_source("slots")
    namespace = source.index.source_namespace
    transport_owner = source.transport_authority
    root_owner = source.registered_root_authority_producer

    absent = _key(namespace, root.root_incarnation, "absent-cancel")
    absent_context = _authenticate_key(source, absent)
    absent_entry = source_cancel_absent(
        source, absent, transport_context=absent_context
    )
    harness.check(
        "authenticated_absent_cancellation_exact_retry_is_idempotent",
        source_cancel_absent(source, absent, transport_context=absent_context)
        == absent_entry
        and absent_entry.kind is IndexEntryKind.CANCELED_BEFORE_ISSUANCE
        and all(
            slot.stable_key != absent for slot in source.generations.slots.values()
        ),
    )
    harness.reject(
        "absent_cancellation_rejects_counterfeit_transport_owner",
        lambda: source_cancel_absent(
            source,
            _key(namespace, root.root_incarnation, "counterfeit-cancel"),
            transport_context=transport_authenticate(
                TransportStore(),
                connection_id="counterfeit",
                authenticated_principal=absent.requester_principal,
                replay_domain="counterfeit",
            ),
        ),
    )
    harness.reject(
        "successor_generation_cannot_reissue_burned_stable_key",
        lambda: _issue(
            source, absent, generation="successor", slot="reused", admission_key=None
        ),
    )

    canceled = _key(namespace, root.root_incarnation, "canceled")
    _issue(source, canceled, generation="g1", slot="s1", admission_key=None)
    before = copy.deepcopy(source)
    harness.reject("available_slot_blocks_source_freeze", lambda: source_freeze(source))
    harness.check("failed_available_freeze_is_atomic", source == before)
    canceled_context = _key_transport(source, canceled)
    canceled_result = source_cancel_available(
        source, canceled, transport_context=canceled_context
    )
    harness.check(
        "authenticated_available_cancellation_exact_retry_is_idempotent",
        source_cancel_available(source, canceled, transport_context=canceled_context)
        == canceled_result,
    )
    harness.check(
        "source_transactions_preserve_independent_owner_identity",
        source.transport_authority is transport_owner
        and source.registered_root_authority_producer is root_owner,
    )
    expired = _key(namespace, root.root_incarnation, "expired")
    _issue(source, expired, generation="g1", slot="s2", admission_key=None)
    expiry_cutoff = source.index.acceptance_not_after
    before_expiry_rejections = copy.deepcopy(source)
    harness.reject(
        "available_slot_expiry_rejects_pre_cutoff_sample",
        lambda: source_expire_available(
            source,
            expired,
            source_clock_sample=_source_sample(
                source, lower=expiry_cutoff - 1, upper=expiry_cutoff - 1
            ),
        ),
    )
    harness.reject(
        "available_slot_expiry_rejects_cutoff_straddling_uncertainty",
        lambda: source_expire_available(
            source,
            expired,
            source_clock_sample=_source_sample(
                source, lower=expiry_cutoff - 1, upper=expiry_cutoff
            ),
        ),
    )
    harness.reject(
        "available_slot_expiry_rejects_wrong_clock_epoch",
        lambda: source_expire_available(
            source,
            expired,
            source_clock_sample=BoundedClockSample(
                source.index.source_clock_id,
                "source-clock-epoch-counterfeit",
                expiry_cutoff,
                expiry_cutoff,
            ),
        ),
    )
    restarted_expiry_source = copy.deepcopy(source)
    restarted_expiry_source.index.live_session_epoch = (
        "source-session-epoch-after-restart"
    )
    harness.reject(
        "available_slot_expiry_rejects_session_epoch_substitution",
        lambda: source_expire_available(
            restarted_expiry_source,
            expired,
            source_clock_sample=_source_sample(
                restarted_expiry_source, lower=expiry_cutoff, upper=expiry_cutoff
            ),
        ),
    )
    security_cut_expiry_source = copy.deepcopy(source)
    security_cut_expiry_source.index.source_security_epoch = "source-security-after-cut"
    harness.reject(
        "available_slot_expiry_rejects_source_security_epoch_substitution",
        lambda: source_expire_available(
            security_cut_expiry_source,
            expired,
            source_clock_sample=_source_sample(
                security_cut_expiry_source, lower=expiry_cutoff, upper=expiry_cutoff
            ),
        ),
    )
    harness.check(
        "failed_available_slot_expiry_proofs_are_atomic",
        source == before_expiry_rejections,
    )
    expiry_sample = _source_sample(source, lower=expiry_cutoff, upper=expiry_cutoff)
    source_expire_available(source, expired, source_clock_sample=expiry_sample)
    source_expire_available(source, expired, source_clock_sample=expiry_sample)
    harness.reject(
        "available_slot_expiry_rejects_changed_terminal_retry",
        lambda: source_expire_available(
            source,
            expired,
            source_clock_sample=_source_sample(
                source, lower=expiry_cutoff, upper=expiry_cutoff + 1
            ),
        ),
    )

    accepted = _key(namespace, root.root_incarnation, "accepted")
    _issue(source, accepted, generation="g2", slot="s1", admission_key=None)
    context = _key_transport(source, accepted)
    frame = source_delivery_view(
        source, accepted, transport_context=context
    ).frame_bytes
    if frame is None:
        raise AssertionError("direct delivery frame missing")

    closed = copy.deepcopy(source)
    closed_context = _key_transport(closed, accepted)
    transport_close(closed.transport_authority, closed_context)
    harness.check(
        "closed_transport_channel_is_terminal_and_returns_no_bytes",
        closed.transport_authority.channel_states[closed_context.verification_digest]
        is TransportState.CLOSED
        and source_delivery_view(closed, accepted, transport_context=closed_context)
        == DeliveryView("TRANSPORT_CONTEXT_NOT_CURRENT", None),
    )
    harness.reject(
        "closed_transport_channel_cannot_accept_a_request",
        lambda: source_accept(
            closed,
            accepted,
            transport_context=closed_context,
            requester_frame=frame,
            source_clock_sample=_source_sample(closed),
        ),
    )

    rotated = copy.deepcopy(source)
    old_context = _key_transport(rotated, accepted)
    transport_rotate_security_epoch(
        rotated.transport_authority, "transport-security-v2"
    )
    harness.check(
        "transport_epoch_rotation_revokes_prior_channel_and_delivery",
        rotated.transport_authority.channel_states[old_context.verification_digest]
        is TransportState.REVOKED
        and source_delivery_view(rotated, accepted, transport_context=old_context)
        == DeliveryView("TRANSPORT_CONTEXT_NOT_CURRENT", None),
    )
    harness.reject(
        "revoked_transport_channel_cannot_be_closed_as_if_active",
        lambda: transport_close(rotated.transport_authority, old_context),
    )
    new_context = transport_authenticate(
        rotated.transport_authority,
        connection_id=old_context.connection_id,
        authenticated_principal=old_context.authenticated_principal,
        replay_domain=old_context.replay_domain,
        transport_security_epoch="transport-security-v2",
    )
    harness.check(
        "new_epoch_channel_cannot_recover_old_issued_challenge_bytes",
        source_delivery_view(rotated, accepted, transport_context=new_context)
        == DeliveryView("TRANSPORT_CONTEXT_NOT_CURRENT", None),
    )
    harness.reject(
        "transport_security_epoch_cannot_be_reused_after_rotation",
        lambda: transport_rotate_security_epoch(
            rotated.transport_authority, "transport-security-v1"
        ),
    )
    harness.reject(
        "same_named_fresh_transport_registry_lacks_producer_membership",
        lambda: _require_transport(
            TransportStore(), context, expected_principal=accepted.requester_principal
        ),
    )
    harness.reject(
        "reconstructed_transport_context_lacks_live_channel_identity",
        lambda: _require_transport(
            source.transport_authority,
            replace(context, live_channel_handle=OpaqueLiveTransportHandle()),
            expected_principal=accepted.requester_principal,
        ),
    )

    bounded = TransportStore(context_capacity=1)
    bounded_context = transport_authenticate(
        bounded,
        connection_id="bounded-1",
        authenticated_principal="principal-1",
        replay_domain="replay-1",
    )
    harness.reject(
        "transport_registry_rejects_capacity_plus_one",
        lambda: transport_authenticate(
            bounded,
            connection_id="bounded-2",
            authenticated_principal="principal-2",
            replay_domain="replay-2",
        ),
    )
    transport_close(bounded, bounded_context)
    replacement_context = transport_authenticate(
        bounded,
        connection_id="bounded-2",
        authenticated_principal="principal-2",
        replay_domain="replay-2",
    )
    harness.check(
        "terminal_transport_context_releases_only_live_capacity",
        len(bounded.contexts) == len(bounded.retired_contexts) == 1
        and replacement_context.verification_digest in bounded.contexts,
    )
    harness.reject(
        "transport_registry_rejects_zero_capacity_configuration",
        lambda: _validate_transport(TransportStore(context_capacity=0)),
    )
    harness.reject(
        "transport_registry_rejects_manifest_cap_plus_one_configuration",
        lambda: _validate_transport(
            TransportStore(context_capacity=MAX_VERIFIED_TRANSPORT_CONTEXTS + 1)
        ),
    )
    harness.reject(
        "transport_registry_rejects_oversized_unicode_connection",
        lambda: transport_authenticate(
            TransportStore(),
            connection_id="🧠" * 65,
            authenticated_principal="principal",
            replay_domain="replay",
        ),
    )

    cutoff_branch = copy.deepcopy(source)
    harness.reject(
        "acceptance_rejects_fixed_cutoff_equality",
        lambda: source_accept(
            cutoff_branch,
            accepted,
            transport_context=_key_transport(cutoff_branch, accepted),
            requester_frame=frame,
            source_clock_sample=_source_sample(
                cutoff_branch,
                lower=cutoff_branch.index.acceptance_not_after,
                upper=cutoff_branch.index.acceptance_not_after,
            ),
        ),
    )
    grant_id = source_accept(
        source,
        accepted,
        transport_context=context,
        requester_frame=frame,
        source_clock_sample=_source_sample(source),
    )
    harness.check(
        "exact_committed_acceptance_retry_survives_cutoff",
        source_accept(
            source,
            accepted,
            transport_context=context,
            requester_frame=frame,
            source_clock_sample=_source_sample(source),
        )
        == grant_id
        and source_accept(
            source,
            accepted,
            transport_context=context,
            requester_frame=frame,
            source_clock_sample=_source_sample(
                source,
                lower=source.index.acceptance_not_after,
                upper=source.index.acceptance_not_after,
            ),
        )
        == grant_id,
    )
    harness.reject(
        "changed_consumed_acceptance_retry",
        lambda: source_accept(
            source,
            accepted,
            transport_context=context,
            requester_frame=frame + b"x",
            source_clock_sample=_source_sample(source),
        ),
    )
    restarted = copy.deepcopy(source)
    restarted.index.live_session_epoch = "source-session-epoch-v2"
    harness.reject(
        "acceptance_rejects_restart_session_epoch_substitution",
        lambda: source_accept(
            restarted,
            accepted,
            transport_context=_key_transport(restarted, accepted),
            requester_frame=frame,
            source_clock_sample=_source_sample(restarted),
        ),
    )

    duplicate = _key(
        namespace,
        root.root_incarnation,
        "duplicate-target",
        target=accepted.logical_target_key,
    )
    _issue(source, duplicate, generation="g3", slot="s1", admission_key=None)
    duplicate_context = _key_transport(source, duplicate)
    duplicate_frame = source_delivery_view(
        source, duplicate, transport_context=duplicate_context
    ).frame_bytes
    harness.reject(
        "source_cas_enforces_authority_wide_logical_target_exclusivity",
        lambda: source_accept(
            source,
            duplicate,
            transport_context=duplicate_context,
            requester_frame=duplicate_frame or b"",
            source_clock_sample=_source_sample(source),
        ),
    )
    source_cancel_available(source, duplicate, transport_context=duplicate_context)
    before = copy.deepcopy(source)
    harness.reject(
        "consumed_slot_without_closed_grant_blocks_source_freeze",
        lambda: source_freeze(source),
    )
    harness.check("failed_unclosed_grant_freeze_is_atomic", source == before)
    transport_close(source.transport_authority, context)
    transport_rotate_security_epoch(source.transport_authority, "transport-security-v2")
    closure_authority = ClosureAuthority()
    source_before_external = copy.deepcopy(source)
    distributed = distributed_closure_publish(closure_authority, source, grant_id)
    harness.check(
        "distributed_closure_authority_does_not_mutate_source_or_live_transport",
        source == source_before_external
        and distributed.producer_credential is not source.producer_credential,
    )

    def hostile_external(
        **changes: object,
    ) -> tuple[ClosureAuthority, ProtectedDistributedClosure]:
        fact = replace(distributed.fact, **changes)
        hierarchy = replace(
            distributed, fact=fact, protection=_protect_distributed(fact)
        )
        authority = copy.deepcopy(closure_authority)
        authority.hierarchies = {_distributed_key(fact): hierarchy}
        return authority, hierarchy

    for label, changes in (
        ("cross_grant", {"grant_id": "cross-grant"}),
        ("cross_plan", {"closure_plan_id": "cross-plan"}),
        ("stale_session", {"live_session_epoch": "stale-session"}),
        ("cross_source", {"source_authority_id": "cross-source"}),
        ("stale_accepted_epoch", {"accepted_source_security_epoch": "stale"}),
        ("stale_current_epoch", {"closure_source_security_epoch": "stale"}),
        ("unknown_default_state", {"state": "UNKNOWN_DEFAULT"}),
        ("none_state", {"state": None}),
    ):
        hostile_pair = hostile_external(**changes)
        harness.reject(
            "distributed_closure_rejects_" + label,
            lambda hostile_pair=hostile_pair: source_import_accepted_grant_closure(
                source, *hostile_pair
            ),
        )
    counterfeit_authority = copy.deepcopy(closure_authority)
    counterfeit = replace(
        distributed, producer_credential=OpaqueDistributedClosureAuthorityCredential()
    )
    counterfeit_authority.hierarchies[next(iter(counterfeit_authority.hierarchies))] = (
        counterfeit
    )
    harness.reject(
        "distributed_closure_rejects_counterfeit_authority",
        lambda: source_import_accepted_grant_closure(
            source, counterfeit_authority, counterfeit
        ),
    )
    harness.reject(
        "distributed_closure_rejects_digest_only_input",
        lambda: source_import_accepted_grant_closure(
            source, closure_authority, _object_digest(distributed)
        ),
    )
    grant_receipt = source_import_accepted_grant_closure(
        source, closure_authority, distributed
    )
    harness.check(
        "protected_grant_closure_survives_acceptance_channel_retirement",
        source.transport_authority.channel_states[context.verification_digest]
        is TransportState.CLOSED
        and source.transport_authority.security_epoch == "transport-security-v2"
        and grant_receipt.acceptance_transport_verification_digest
        == context.verification_digest
        and source_import_accepted_grant_closure(source, closure_authority, distributed)
        == grant_receipt,
    )
    harness.check(
        "distributed_closure_publication_exact_retry_is_idempotent",
        distributed_closure_publish(closure_authority, source, grant_id) == distributed,
    )
    closure = source_freeze(source)
    harness.check(
        "source_freeze_is_exact_and_matches_retained_terminal_tree",
        source_freeze(source) == closure
        and closure.root == source_resolution_tree(source).root
        and source.index.phase is SourceIndexPhase.FROZEN
        and all(
            slot.state is not SlotState.AVAILABLE
            for slot in source.generations.slots.values()
        ),
    )

    empty, empty_root = empty_source("orphan")
    orphan_key = _key(
        empty.index.source_namespace, empty_root.root_incarnation, "orphan"
    )
    orphan_slot = copy.deepcopy(empty)
    orphan_slot.generations.slots[("g", "s")] = FreshnessSlot(
        stable_key=orphan_key,
        source_generation="g",
        slot_id="s",
        challenge_commitment="orphan",
        state=SlotState.CANCELED_UNUSED,
        delivery_gate=DeliveryGate.DELIVERY_TERMINAL,
        paired_frame_admission_key=None,
        live_session_epoch=empty.index.live_session_epoch,
        authority_lease_not_after=empty.index.authority_lease_not_after,
        acceptance_not_after=empty.index.acceptance_not_after,
        source_security_epoch=empty.index.source_security_epoch,
        plant_profile_digest=None,
    )
    orphan_tombstone = copy.deepcopy(empty)
    orphan_tombstone.generations.absent_intent_tombstones[orphan_key] = (
        "CANCELED_BEFORE_ISSUANCE"
    )
    orphan_grant = copy.deepcopy(empty)
    orphan_grant.generations.accepted_grants["orphan-grant"] = AcceptedGrant(
        grant_id="orphan-grant",
        stable_key=orphan_key,
        live_session_epoch=empty.index.live_session_epoch,
        authority_lease_not_after=empty.index.authority_lease_not_after,
        acceptance_not_after=empty.index.acceptance_not_after,
        source_security_epoch=empty.index.source_security_epoch,
        plant_profile_digest=None,
        acceptance_transport_verification_digest="22" * 32,
        acceptance_receipt_digest="11" * 32,
        closure_plan_id="closure-plan:orphan-grant",
        closure_plan_digest="33" * 32,
        predecessor_grant_id=None,
    )
    in_flight = copy.deepcopy(empty)
    in_flight.in_flight_exposure.add("exposure")
    for label, candidate in (
        ("orphan_generation_slot_blocks_freeze", orphan_slot),
        ("orphan_absent_intent_tombstone_blocks_freeze", orphan_tombstone),
        ("orphan_accepted_grant_blocks_freeze", orphan_grant),
        ("in_flight_exposure_blocks_freeze", in_flight),
    ):
        harness.reject(label, lambda candidate=candidate: source_freeze(candidate))

    harness.accept("generation_slot_terminal_partition")
    harness.accept("accepted_grant_closure_gate")
    harness.witness("available_slot_is_not_finalizable")
    harness.witness("consumed_slot_requires_complete_grant_closure")
    harness.witness("source_generation_is_excluded_from_stable_key")


def scenario_anchor_gate_and_authoritative_queue(harness: Harness) -> None:
    namespace = ("realm-anchor", "SIMULATION", "source-anchor")
    profile = ANCHOR_PROFILE
    root = _root(
        root_id="observer-root-anchor",
        incarnation="observer-root-anchor-v1",
        profile=profile,
    )
    source = new_source(namespace, profile)
    anchor = new_anchor(namespace)
    anchor_registry = materialized_anchor_registry(
        anchor, source, coordinate_suffix="anchor-gate"
    )
    _enroll_anchor_profile(source, anchor, anchor_registry, root)
    relation = _qualified_clock_relation(source, anchor)
    key = _key(namespace, root.root_incarnation, "paired")
    source_entry = _issue(
        source,
        key,
        generation="generation-anchor-1",
        slot="slot-anchor-1",
        admission_key="admission-key-1",
    )
    pending = source_delivery_view(
        source, key, transport_context=_key_transport(source, key)
    )
    harness.check(
        "pending_gate_returns_nonsecret_status_only",
        pending.status == "ANCHOR_ADMISSION_PENDING" and pending.frame_bytes is None,
    )
    harness.reject(
        "pending_gate_blocks_acceptance",
        lambda: source_accept(
            source,
            key,
            transport_context=_key_transport(source, key),
            requester_frame=b"forged-pending-frame",
            source_clock_sample=_source_sample(source),
        ),
    )

    harness.reject(
        "anchor_append_rejects_commit_time_cutoff_equality",
        lambda: anchor_append(
            anchor,
            anchor_registry,
            source,
            source_entry,
            intended_observer_root_id=root.root_id,
            mapped_acceptance_cutoff=100,
            anchor_clock_sample=_anchor_sample(anchor, lower=99, upper=100),
        ),
    )
    anchor_entry = anchor_append(
        anchor,
        anchor_registry,
        source,
        source_entry,
        intended_observer_root_id=root.root_id,
        mapped_acceptance_cutoff=100,
        anchor_clock_sample=_anchor_sample(anchor),
    )
    still_pending = source_delivery_view(
        source, key, transport_context=_key_transport(source, key)
    )
    harness.check(
        "anchor_append_alone_does_not_open_delivery_gate",
        still_pending.status == "ANCHOR_ADMISSION_PENDING"
        and still_pending.frame_bytes is None,
    )
    harness.reject(
        "anchor_append_without_paired_admission_blocks_acceptance",
        lambda: source_accept(
            source,
            key,
            transport_context=_key_transport(source, key),
            requester_frame=b"anchor-member-is-not-a-frame",
            source_clock_sample=_source_sample(source),
        ),
    )

    sibling_root_entry = replace(
        anchor_entry.entry, intended_observer_root_id="sibling-observer-root"
    )
    anchor_capsule = b"anchor-observer-capsule"
    opaque_relay_binding = _opaque_relay_binding(
        admission_key="admission-key-1",
        observer_envelope_identity="anchor-observer-envelope-1",
    )
    opaque_relay_hierarchy = anchor_publish_observer_opaque_relay(
        anchor, anchor_registry, anchor_entry, anchor_capsule, opaque_relay_binding
    )
    harness.reject(
        "opaque_relay_rejects_entry_absent_from_producer_store",
        lambda: anchor_publish_observer_opaque_relay(
            new_anchor(namespace),
            anchor_registry,
            anchor_entry,
            anchor_capsule,
            opaque_relay_binding,
        ),
    )
    hostile_admissions = (
        (
            "paired_admission_rejects_sibling_root_projection",
            replace(anchor_entry, entry=sibling_root_entry),
            opaque_relay_hierarchy,
        ),
        (
            "paired_admission_rejects_changed_anchor_hierarchy",
            replace(
                anchor_entry, anchor_security_epoch="sibling-anchor-security-epoch"
            ),
            opaque_relay_hierarchy,
        ),
        (
            "paired_admission_rejects_changed_opaque_observer_capsule",
            anchor_entry,
            replace(
                opaque_relay_hierarchy, anchor_observer_capsule=anchor_capsule + b"x"
            ),
        ),
        (
            "paired_admission_rejects_changed_anchor_producer_coordinate",
            anchor_entry,
            replace(
                opaque_relay_hierarchy,
                binding=replace(
                    opaque_relay_binding,
                    producer_coordinate="anchor-producer:sibling-admission",
                ),
            ),
        ),
    )
    for label, hostile_entry, hostile_relay in hostile_admissions:
        harness.reject(
            label,
            lambda hostile_entry=hostile_entry, hostile_relay=hostile_relay: (
                source_admit_paired_frame(
                    source,
                    key,
                    anchor,
                    hostile_entry,
                    hostile_relay,
                    source_clock_sample=_source_sample(source),
                    clock_relation=relation,
                )
            ),
        )

    harness.reject(
        "paired_admission_rejects_conservative_anchor_cutoff_equality",
        lambda: source_admit_paired_frame(
            source,
            key,
            anchor,
            anchor_entry,
            opaque_relay_hierarchy,
            source_clock_sample=_source_sample(source, lower=79, upper=80),
            clock_relation=relation,
        ),
    )
    admitted_frame = source_admit_paired_frame(
        source,
        key,
        anchor,
        anchor_entry,
        opaque_relay_hierarchy,
        source_clock_sample=_source_sample(source),
        clock_relation=relation,
    )
    harness.check(
        "paired_admission_exact_retry_returns_retained_frame",
        source_admit_paired_frame(
            source,
            key,
            anchor,
            anchor_entry,
            opaque_relay_hierarchy,
            source_clock_sample=_source_sample(source),
            clock_relation=relation,
        )
        == admitted_frame,
    )
    _, _, admitted_slot = _slot_for_entry(source, key)
    harness.check(
        "paired_gate_and_queue_record_commit_together",
        admitted_slot.delivery_gate is DeliveryGate.ANCHOR_PAIRED_FRAME_ADMITTED
        and source.queue.records["admission-key-1"].frame_bytes == admitted_frame
        and source.queue.records["admission-key-1"].state
        is QueueRecordState.MAY_HAVE_BEEN_EXPOSED,
    )
    queue_without_gate = copy.deepcopy(source)
    _, _, detached_gate = _slot_for_entry(queue_without_gate, key)
    detached_gate.delivery_gate = DeliveryGate.ANCHOR_PAIRED_FRAME_PENDING
    harness.reject(
        "queue_record_without_admitted_gate_is_invalid",
        lambda: _validate_source(queue_without_gate),
    )
    sibling_transport_context = transport_authenticate(
        source.transport_authority,
        connection_id="connection:sibling",
        authenticated_principal=key.requester_principal,
        replay_domain="replay:source-anchor",
    )
    handoff_alternatives = copy.deepcopy(source)
    quiescence_receipt = _publish_handoff(
        source, key, HandoffResult.MAY_HAVE_BEEN_EXPOSED_TOKEN_RELEASED
    )
    before_wrong_handoff = copy.deepcopy(source)
    harness.reject(
        "paired_handoff_rejects_changed_connection",
        lambda: source_handoff_paired_frame(
            source,
            key,
            transport_context=sibling_transport_context,
            source_clock_sample=_source_sample(source),
            clock_relation=relation,
            quiescence_receipt=quiescence_receipt,
        ),
    )
    harness.check("failed_paired_handoff_is_atomic", source == before_wrong_handoff)
    for label, result in (
        (
            "zero_byte_quiescence_releases_token_without_returning_frame",
            HandoffResult.ZERO_BYTES_ACCEPTED_TOKEN_RELEASED,
        ),
        (
            "producer_fenced_unknown_terminalizes_dispatch_without_frame",
            HandoffResult.OUTCOME_UNKNOWN_DISPATCHER_AND_SOCKET_FENCED,
        ),
    ):
        alternative = copy.deepcopy(handoff_alternatives)
        receipt = _publish_handoff(alternative, key, result)
        outcome = source_handoff_paired_frame(
            alternative,
            key,
            transport_context=_key_transport(alternative, key),
            source_clock_sample=_source_sample(alternative),
            clock_relation=relation,
            quiescence_receipt=receipt,
        )
        harness.check(
            label,
            outcome.result is result
            and outcome.frame_bytes is None
            and alternative.queue.records["admission-key-1"].state
            is QueueRecordState.TERMINALIZED,
        )
    harness.reject(
        "one_dispatcher_epoch_cannot_publish_a_second_outcome",
        lambda: transport_publish_handoff_quiescence(
            source.transport_authority,
            _key_transport(source, key),
            admission_key="admission-key-1",
            frame_digest=hashlib.sha256(admitted_frame).hexdigest(),
            result=HandoffResult.ZERO_BYTES_ACCEPTED_TOKEN_RELEASED,
        ),
    )
    harness.reject(
        "paired_handoff_rejects_fresh_mapped_cutoff_equality",
        lambda: source_handoff_paired_frame(
            source,
            key,
            transport_context=_key_transport(source, key),
            source_clock_sample=_source_sample(source, lower=79, upper=80),
            clock_relation=relation,
            quiescence_receipt=quiescence_receipt,
        ),
    )
    handed_off = source_handoff_paired_frame(
        source,
        key,
        transport_context=_key_transport(source, key),
        source_clock_sample=_source_sample(source),
        clock_relation=relation,
        quiescence_receipt=quiescence_receipt,
    )
    harness.check(
        "may_have_been_exposed_handoff_returns_exact_admitted_frame",
        handed_off.result is HandoffResult.MAY_HAVE_BEEN_EXPOSED_TOKEN_RELEASED
        and handed_off.frame_bytes == admitted_frame
        and source.queue.records["admission-key-1"].state
        is QueueRecordState.MAY_HAVE_BEEN_EXPOSED,
    )
    harness.check(
        "paired_handoff_exact_retry_returns_same_outcome_and_bytes",
        source_handoff_paired_frame(
            source,
            key,
            transport_context=_key_transport(source, key),
            source_clock_sample=_source_sample(source),
            clock_relation=relation,
            quiescence_receipt=quiescence_receipt,
        )
        == handed_off,
    )
    harness.reject(
        "acceptance_rejects_changed_admitted_frame",
        lambda: source_accept(
            source,
            key,
            transport_context=_key_transport(source, key),
            requester_frame=admitted_frame + b"x",
            source_clock_sample=_source_sample(source),
        ),
    )
    grant_id = source_accept(
        source,
        key,
        transport_context=_key_transport(source, key),
        requester_frame=admitted_frame,
        source_clock_sample=_source_sample(source),
    )
    terminal_view = source_delivery_view(
        source, key, transport_context=_key_transport(source, key)
    )
    harness.check(
        "consumed_query_returns_no_new_frame",
        terminal_view.frame_bytes is None
        and source.queue.records["admission-key-1"].state
        is QueueRecordState.TERMINALIZED,
    )
    closure_authority = ClosureAuthority()
    distributed = distributed_closure_publish(closure_authority, source, grant_id)
    source_import_accepted_grant_closure(source, closure_authority, distributed)
    source_freeze(source)
    reservation_charge_before = _reservation_charge(
        _slot_for_anchor(anchor_registry, anchor)
    )
    isolation_authority, isolation_hierarchy = _complete_isolation_hierarchy(namespace)
    anchor_bundle = anchor_freeze(
        anchor, anchor_registry, isolation_authority, isolation_hierarchy
    )
    harness.check(
        "anchor_membership_root_is_retained_after_isolation",
        anchor_bundle.root == anchor_resolution_tree(anchor).root,
    )
    harness.check(
        "isolation_terminalization_retains_full_reservation_charge",
        _reservation_charge(_slot_for_anchor(anchor_registry, anchor))
        == reservation_charge_before,
    )
    harness.accept("anchor_pending_append_admit_handoff_accept")
    harness.accept("paired_queue_terminalization")
    harness.witness("pending_gate_prevents_retry_bytes_and_acceptance")
    harness.witness("queue_record_and_gate_share_source_cas")
    harness.witness("admission_commit_never_proves_challenge_nonexposure")
    harness.witness("anchor_append_is_not_requester_delivery_authority")


def scenario_cooperative_anchor_retirement(harness: Harness) -> None:
    def source_only_inventory(suffix: str, *, enrolled: bool) -> RetirementInventory:
        source = new_source(
            ("realm-inventory-" + suffix, "SIMULATION", "source-inventory-" + suffix),
            SOURCE_ONLY,
        )
        if enrolled:
            _enroll_source(
                source,
                _root(
                    root_id="observer-root-inventory-" + suffix,
                    incarnation="observer-root-inventory-" + suffix + "-v1",
                    profile=SOURCE_ONLY,
                ),
            )
        source_freeze(source)
        return source_retirement_producer_inventory(source)

    empty_inventory = source_only_inventory("empty", enrolled=False)
    observer_inventory = source_only_inventory("observer", enrolled=True)
    harness.check(
        "source_only_retirement_inventory_depends_only_on_frozen_audience",
        empty_inventory == RetirementInventory((), None, None)
        and observer_inventory.family_kinds == ("OBSERVER_NAMESPACE_CLOSURE",),
    )

    empty_namespace = ("realm-anchor-empty", "SIMULATION", "source-anchor-empty")
    empty_source = new_source(empty_namespace, ANCHOR_PROFILE)
    empty_anchor = new_anchor(empty_namespace)
    empty_registry = materialized_anchor_registry(
        empty_anchor, empty_source, coordinate_suffix="anchor-empty-retirement"
    )
    source_bind_anchor(
        empty_source, empty_anchor, _anchor_allocation(empty_registry, empty_anchor)
    )
    source_freeze(empty_source)
    empty_lineage, empty_no_successor = _complete_no_successor(empty_source)
    empty_anchor_inventory = source_retirement_producer_inventory(
        empty_source, empty_no_successor
    )
    harness.check(
        "anchor_profile_empty_retirement_keeps_anchor_family_and_completion",
        empty_anchor_inventory.family_kinds == (_ANCHOR_RETIREMENT,)
        and empty_anchor_inventory.pre_manifest_digest is not None
        and empty_anchor_inventory.producer_completion_digest is not None,
    )
    anchor_finalize_cooperative_source_retirement(
        empty_anchor,
        empty_registry,
        empty_source,
        source_build_cooperative_retirement_hierarchy(
            empty_source, empty_lineage, empty_no_successor
        ),
    )

    namespace = ("realm-cooperative", "SIMULATION", "source-cooperative")
    profile = ANCHOR_PROFILE
    root = _root(
        root_id="observer-root-cooperative",
        incarnation="observer-root-cooperative-v1",
        profile=profile,
    )
    source = new_source(namespace, profile)
    anchor = new_anchor(namespace)
    registry = materialized_anchor_registry(
        anchor, source, coordinate_suffix="cooperative-append"
    )
    _enroll_anchor_profile(source, anchor, registry, root)

    sibling = new_anchor(namespace)
    sibling.anchor_authority = "sibling-independent-anchor-authority"
    sibling_registry = materialized_anchor_registry(
        sibling, source, coordinate_suffix="cooperative-sibling"
    )
    harness.reject(
        "source_rejects_sibling_anchor_allocation_rebinding",
        lambda: source_bind_anchor(
            copy.deepcopy(source),
            sibling,
            _anchor_allocation(sibling_registry, sibling),
        ),
    )

    observer = ObserverLocalStore(root.root_id, root.root_incarnation)
    _enroll_observer(observer, source, root, anchor=anchor)
    key = _key(namespace, root.root_incarnation, "cooperative-append")
    observer_prepare(observer, key)
    source_entry = _issue(
        source,
        key,
        generation="generation-cooperative",
        slot="slot-cooperative",
        admission_key="admission-cooperative",
    )
    closure_first_anchor = copy.deepcopy(anchor)
    closure_first_registry = copy.deepcopy(registry)
    anchor_append(
        anchor,
        registry,
        source,
        source_entry,
        intended_observer_root_id=root.root_id,
        mapped_acceptance_cutoff=100,
        anchor_clock_sample=_anchor_sample(anchor),
    )
    source_cancel_available(source, key, transport_context=_key_transport(source, key))
    source_closure = source_freeze(source)

    successor_lineage = LineageStore()
    lineage_register_source(
        successor_lineage, namespace, source.index.source_index_incarnation
    )
    for index in range(1, MAX_LINEAGE_INCARNATIONS_PER_NAMESPACE):
        lineage_register_source(
            successor_lineage, namespace, "source-index-sibling-" + str(index)
        )
    harness.reject(
        "lineage_registry_rejects_incarnation_capacity_plus_one",
        lambda: lineage_register_source(
            successor_lineage, namespace, "source-index-capacity-plus-one"
        ),
    )
    harness.reject(
        "cooperative_retirement_rejects_live_same_namespace_successor",
        lambda: lineage_finalize_no_successor(
            successor_lineage, namespace, source.index.source_index_incarnation
        ),
    )

    lineage, no_successor = _complete_no_successor(source)
    inventory = source_retirement_producer_inventory(source, no_successor)
    hierarchy = source_build_cooperative_retirement_hierarchy(
        source, lineage, no_successor
    )
    binding = source.index.anchor_allocation_binding
    harness.check(
        "nonempty_anchor_retirement_binds_two_families_and_exact_coordinate",
        inventory.family_kinds == ("OBSERVER_NAMESPACE_CLOSURE", _ANCHOR_RETIREMENT)
        and inventory.pre_manifest_digest is not None
        and inventory.producer_completion_digest is not None
        and binding is not None
        and hierarchy.projection.anchor_authority == binding.anchor_authority
        and hierarchy.projection.allocation_id == binding.allocation_id,
    )
    harness.reject(
        "cooperative_retirement_rejects_counterfeit_lineage_credential",
        lambda: source_build_cooperative_retirement_hierarchy(
            source,
            lineage,
            replace(
                no_successor, producer_credential=OpaqueLineageAuthorityCredential()
            ),
        ),
    )

    charge = _reservation_charge(_slot_for_anchor(registry, anchor))
    append_first_closure = anchor_finalize_cooperative_source_retirement(
        anchor, registry, source, hierarchy
    )
    frozen_root = anchor.frozen_root
    frozen_entries = copy.deepcopy(anchor.entries)
    harness.check(
        "append_first_cooperative_closure_is_exact_nonrefunding_and_idempotent",
        key in anchor.entries
        and append_first_closure.anchor_closure_cause is AnchorClosureCause.COOPERATIVE
        and _reservation_charge(_slot_for_anchor(registry, anchor)) == charge
        and anchor_finalize_cooperative_source_retirement(
            anchor, registry, source, hierarchy
        )
        == append_first_closure
        and anchor_append(
            anchor,
            registry,
            source,
            source_entry,
            intended_observer_root_id=root.root_id,
            mapped_acceptance_cutoff=100,
            anchor_clock_sample=_anchor_sample(anchor),
        )
        == anchor.entry_hierarchies[key],
    )

    closure_first_hierarchy = source_build_cooperative_retirement_hierarchy(
        source, lineage, no_successor
    )
    isolation_first_anchor = copy.deepcopy(closure_first_anchor)
    isolation_first_registry = copy.deepcopy(closure_first_registry)
    closure_first_bundle = anchor_finalize_cooperative_source_retirement(
        closure_first_anchor, closure_first_registry, source, closure_first_hierarchy
    )
    harness.reject(
        "closure_first_anchor_rejects_delayed_append",
        lambda: anchor_append(
            closure_first_anchor,
            closure_first_registry,
            source,
            source_entry,
            intended_observer_root_id=root.root_id,
            mapped_acceptance_cutoff=100,
            anchor_clock_sample=_anchor_sample(closure_first_anchor),
        ),
    )
    harness.check(
        "closure_first_retains_empty_anchor_entry_root",
        not closure_first_anchor.entries
        and closure_first_bundle.anchor_closure_cause is AnchorClosureCause.COOPERATIVE,
    )

    for label, suffix, hostile_hierarchy in (
        (
            "cooperative_anchor_closure_rejects_mismatched_anchor",
            "mismatched-anchor",
            replace(
                hierarchy,
                projection=replace(
                    hierarchy.projection, anchor_authority="sibling-anchor-authority"
                ),
            ),
        ),
        (
            "cooperative_anchor_closure_rejects_wrong_profile",
            "wrong-profile",
            replace(
                hierarchy,
                projection=replace(
                    hierarchy.projection,
                    availability_profile=SOURCE_ONLY,
                ),
            ),
        ),
        (
            "cooperative_anchor_closure_rejects_forged_completion",
            "forged-completion",
            replace(hierarchy, producer_completion_digest="0" * 64),
        ),
    ):
        hostile_anchor = new_anchor(namespace)
        hostile_registry = materialized_anchor_registry(
            hostile_anchor, source, coordinate_suffix=suffix
        )

        def finalize_hostile_cooperative_retirement(
            retained_anchor: Anchor = hostile_anchor,
            retained_registry: AuthorityRegistry = (hostile_registry),
            retained_hierarchy: ProtectedRetirement = (hostile_hierarchy),
        ) -> ClosureBundle:
            return anchor_finalize_cooperative_source_retirement(
                retained_anchor, retained_registry, source, retained_hierarchy
            )

        harness.reject(label, finalize_hostile_cooperative_retirement)

    observer_import_closure(
        observer, source, source_closure, {key: _source_resolution(source, key)}
    )
    observer_import_closure(
        observer,
        anchor,
        append_first_closure,
        {key: _anchor_resolution(anchor, key, attempt_present=False)},
    )
    harness.check(
        "cooperative_anchor_closure_resolves_unattempted_operation",
        observer.operations[key].state is OperationState.RESOLVED_WITHOUT_INSTALLATION
        and observer.closure_tombstones[
            (namespace, observer.observer_root_incarnation)
        ].evidence_state
        is ClosureEvidenceState.SOURCE_AND_ANCHOR,
    )
    harness.reject(
        "anchor_closure_without_cause_rejects",
        lambda: observer_import_closure(
            copy.deepcopy(observer),
            anchor,
            replace(append_first_closure, anchor_closure_cause=None),
            {},
        ),
    )

    isolation_authority, isolation = _complete_isolation_hierarchy(namespace)
    refinement = anchor_refine_terminal_source_closure_evidence(
        anchor,
        registry,
        isolation_authority=isolation_authority,
        isolation_hierarchy=isolation,
    )
    harness.check(
        "cooperative_then_isolation_refines_without_rewriting_frozen_outputs",
        anchor.closure_evidence_state is AnchorEvidenceState.COOPERATIVE_AND_ISOLATION
        and anchor.first_closure_cause is AnchorClosureCause.COOPERATIVE
        and anchor.frozen_root == frozen_root
        and anchor.entries == frozen_entries
        and bool(refinement),
    )

    anchor_freeze(
        isolation_first_anchor, isolation_first_registry, isolation_authority, isolation
    )
    isolation_root = isolation_first_anchor.frozen_root
    anchor_refine_terminal_source_closure_evidence(
        isolation_first_anchor,
        isolation_first_registry,
        cooperative_source=source,
        cooperative_hierarchy=closure_first_hierarchy,
    )
    harness.check(
        "isolation_then_cooperative_preserves_first_terminal_cause",
        isolation_first_anchor.closure_evidence_state
        is AnchorEvidenceState.COOPERATIVE_AND_ISOLATION
        and isolation_first_anchor.first_closure_cause is AnchorClosureCause.ISOLATION
        and isolation_first_anchor.frozen_root == isolation_root,
    )

    retained_charge = _reservation_charge(_slot_for_anchor(registry, anchor))
    retirement = anchor_finalize_authority_domain_retirement(registry)
    harness.check(
        "authority_retirement_is_exact_and_never_refunds_terminal_charge",
        anchor_finalize_authority_domain_retirement(registry) == retirement
        and _reservation_charge(_slot_for_anchor(registry, anchor)) == retained_charge,
    )
    harness.accept("cooperative_anchor_retirement_closes_normal_lifecycle")
    harness.accept("source_retirement_producer_inventory_four_case_product")
    harness.accept("anchor_terminal_closure_evidence_refines_monotonically")
    harness.witness("cooperative_retirement_never_claims_permanent_isolation")
    harness.witness("normal_source_retirement_terminalizes_without_reservation_refund")


def scenario_anchor_conservative_resolution(harness: Harness) -> None:
    namespace = ("realm-conservative", "SIMULATION", "source-conservative")
    profile = ANCHOR_PROFILE
    root = _root(
        root_id="observer-root-conservative",
        incarnation="observer-root-conservative-v1",
        profile=profile,
    )
    source = new_source(namespace, profile)
    anchor = new_anchor(namespace)
    registry = materialized_anchor_registry(
        anchor, source, coordinate_suffix="conservative-resolution"
    )
    _enroll_anchor_profile(source, anchor, registry, root)
    relation = _qualified_clock_relation(source, anchor)
    observer = ObserverLocalStore(root.root_id, root.root_incarnation)
    _enroll_observer(observer, source, root, anchor=anchor)

    def prepare_and_issue(suffix: str) -> tuple[StableKey, SourceIndexEntry]:
        key = _key(namespace, root.root_incarnation, suffix)
        observer_prepare(observer, key)
        entry = _issue(
            source,
            key,
            generation="generation-conservative",
            slot="slot-" + suffix,
            admission_key="admission-" + suffix,
        )
        return key, entry

    unanchored, _ = prepare_and_issue("unanchored")
    anchored, anchored_source_entry = prepare_and_issue("anchored")
    anchor_append(
        anchor,
        registry,
        source,
        anchored_source_entry,
        intended_observer_root_id=root.root_id,
        mapped_acceptance_cutoff=100,
        anchor_clock_sample=_anchor_sample(anchor),
    )
    attempted, attempted_source_entry = prepare_and_issue("attempted")
    attempted_anchor_entry = anchor_append(
        anchor,
        registry,
        source,
        attempted_source_entry,
        intended_observer_root_id=root.root_id,
        mapped_acceptance_cutoff=100,
        anchor_clock_sample=_anchor_sample(anchor),
    )
    relay = anchor_publish_observer_opaque_relay(
        anchor,
        registry,
        attempted_anchor_entry,
        b"anchor-capsule-attempted",
        _opaque_relay_binding(
            admission_key="admission-attempted",
            observer_envelope_identity="anchor-observer-envelope-attempted",
        ),
    )
    admitted = source_admit_paired_frame(
        source,
        attempted,
        anchor,
        attempted_anchor_entry,
        relay,
        source_clock_sample=_source_sample(source),
        clock_relation=relation,
    )
    handoff = source_handoff_paired_frame(
        source,
        attempted,
        transport_context=_key_transport(source, attempted),
        source_clock_sample=_source_sample(source),
        clock_relation=relation,
        quiescence_receipt=_publish_handoff(
            source, attempted, HandoffResult.MAY_HAVE_BEEN_EXPOSED_TOKEN_RELEASED
        ),
    )
    harness.check(
        "attempt_frame_is_byte_identical_to_admitted_frame",
        handoff.frame_bytes == admitted,
    )
    observer_record_verified_attempt(observer, attempted)

    incomplete = IsolationEvidence(namespace, REQUIRED_ISOLATION_SURFACES[:-1])
    harness.reject(
        "anchor_freeze_rejects_incomplete_surface_inventory",
        lambda: higher_root_publish_isolation(
            IsolationAuthority(
                producer_credential=_CONFIGURED_HIGHER_ROOT_ISOLATION_CREDENTIAL
            ),
            incomplete,
            _isolation_inputs(namespace),
        ),
    )
    surface_inputs = _isolation_inputs(namespace)
    harness.reject(
        "higher_root_rejects_counterfeit_surface_owner_receipt",
        lambda: higher_root_publish_isolation(
            IsolationAuthority(
                producer_credential=_CONFIGURED_HIGHER_ROOT_ISOLATION_CREDENTIAL
            ),
            _complete_isolation(namespace),
            (
                (
                    surface_inputs[0][0],
                    replace(
                        surface_inputs[0][1],
                        producer_credential=OpaqueIsolationSurfaceCredential(),
                    ),
                ),
                *surface_inputs[1:],
            ),
        ),
    )
    harness.reject(
        "isolation_namespace_is_bounded_before_surface_allocation",
        lambda: _isolation_inputs(("x" * 300_000, "SIMULATION", "source")),
    )
    isolation_authority, isolation = _complete_isolation_hierarchy(namespace)
    harness.reject(
        "anchor_rejects_changed_higher_root_registry_incarnation",
        lambda: anchor_freeze(
            copy.deepcopy(anchor),
            copy.deepcopy(registry),
            isolation_authority,
            replace(isolation, registry_incarnation="higher-root-registry-v0"),
        ),
    )
    anchor_closure = anchor_freeze(anchor, registry, isolation_authority, isolation)
    resolutions = {
        key: _anchor_resolution(anchor, key, attempt_present=key == attempted)
        for key in (unanchored, anchored, attempted)
    }
    hostile = dict(resolutions)
    hostile[unanchored] = replace(
        hostile[unanchored],
        claimed_outcome=ResolutionOutcome.SOURCE_FROZEN_KEY_NONMEMBERSHIP,
    )
    before = copy.deepcopy(observer)
    harness.reject(
        "anchor_nonmembership_cannot_claim_source_nonissuance",
        lambda: observer_import_closure(observer, anchor, anchor_closure, hostile),
    )
    harness.check("failed_anchor_overclaim_import_is_atomic", observer == before)

    source_first = copy.deepcopy(observer)
    anchor_receipt = observer_import_closure(
        observer, anchor, anchor_closure, resolutions
    )
    harness.check(
        "anchor_resolution_is_conservative_and_attempt_sensitive",
        observer.operations[unanchored].resolution_outcome
        is ResolutionOutcome.ANCHOR_FROZEN_NONMEMBERSHIP
        and observer.operations[anchored].resolution_outcome
        is ResolutionOutcome.ANCHOR_FROZEN_MEMBERSHIP
        and observer.operations[attempted].exact_terminal_evidence_pending,
    )
    for key in (unanchored, anchored, attempted):
        source_cancel_available(
            source, key, transport_context=_key_transport(source, key)
        )
    source_closure = source_freeze(source)
    attempted_resolution = {attempted: _source_resolution(source, attempted)}
    source_receipt = observer_import_closure(
        observer, source, source_closure, attempted_resolution
    )
    tombstone = observer.closure_tombstones[
        (namespace, observer.observer_root_incarnation)
    ]
    harness.check(
        "anchor_then_source_closure_refines_without_reopening",
        tombstone.evidence_state is ClosureEvidenceState.SOURCE_AND_ANCHOR
        and observer.operations[unanchored].state
        is OperationState.RESOLVED_WITHOUT_INSTALLATION
        and observer.operations[anchored].state
        is OperationState.RESOLVED_WITHOUT_INSTALLATION
        and observer.operations[attempted].exact_terminal_evidence_pending,
    )

    source_first_resolutions = {
        key: _source_resolution(source, key)
        for key in (unanchored, anchored, attempted)
    }
    observer_import_closure(
        source_first, source, source_closure, source_first_resolutions
    )
    observer_import_closure(source_first, anchor, anchor_closure, resolutions)
    harness.check(
        "source_then_anchor_closure_converges_to_same_operation_partition",
        all(
            source_first.operations[key].state is observer.operations[key].state
            and source_first.operations[key].exact_terminal_evidence_pending
            == observer.operations[key].exact_terminal_evidence_pending
            for key in (unanchored, anchored, attempted)
        ),
    )
    harness.reject(
        "same_origin_closure_retry_rejects_changed_partition",
        lambda: observer_import_closure(observer, source, source_closure, {}),
    )
    harness.check(
        "byte_identical_nonempty_closure_retries_return_exact_receipts",
        observer_import_closure(observer, source, source_closure, attempted_resolution)
        == source_receipt
        and observer_import_closure(observer, anchor, anchor_closure, resolutions)
        == anchor_receipt,
    )
    harness.accept("anchor_nonmembership_conservative_resolution")
    harness.accept("anchor_membership_conservative_resolution")
    harness.accept("namespace_closure_evidence_refines_monotonically")
    harness.witness("anchor_nonmembership_is_not_source_nonissuance")
    harness.witness("anchor_membership_is_not_nonexposure_or_nonacceptance")
    harness.witness("attempt_present_preserves_exact_terminal_obligation")
    harness.witness("closure_evidence_refinement_never_reopens_resolved_work")


def _mutate_byte(body: bytes, index: int, value: int) -> bytes:
    mutable = bytearray(body)
    mutable[index] = value
    return bytes(mutable)


def _reverse_sibling_chunks(body: bytes) -> bytes:
    siblings = [
        body[80 + index * 32 : 80 + (index + 1) * 32]
        for index in range(SPARSE_TREE_HEIGHT)
    ]
    return body[:80] + b"".join(reversed(siblings))


def scenario_exact_sparse_proofs(harness: Harness) -> None:
    namespace = ("realm-proof", "SIMULATION", "source-proof")
    incarnation = "observer-root-proof-v1"
    source_key = _key(namespace, incarnation, "source-member")
    source_entry = SourceIndexEntry(source_key, IndexEntryKind.CANCELED_BEFORE_ISSUANCE)
    source_tree = SparseMerkleTree(
        ProofContext.SOURCE, {source_key: source_entry_bytes(source_entry)}
    )
    source_absent = _key(namespace, incarnation, "source-absent")
    anchor_key = _key(namespace, incarnation, "anchor-member")
    anchor_entry = AnchorEntry(
        anchor_key,
        "11" * 32,
        "22" * 32,
        "observer-root-proof",
        "admission-proof",
        100,
        "anchor-clock-proof",
        "anchor-clock-epoch-proof",
        "clock-relation-proof",
        "33" * 32,
        None,
    )
    anchor_tree = SparseMerkleTree(
        ProofContext.ANCHOR, {anchor_key: anchor_entry_bytes(anchor_entry)}
    )
    anchor_absent = _key(namespace, incarnation, "anchor-absent")
    source_member = source_tree.proof(source_key, ProofKind.MEMBERSHIP)
    source_none = source_tree.proof(source_absent, ProofKind.NONMEMBERSHIP)
    anchor_member = anchor_tree.proof(anchor_key, ProofKind.MEMBERSHIP)
    anchor_none = anchor_tree.proof(anchor_absent, ProofKind.NONMEMBERSHIP)

    def verify(
        body: bytes,
        context: ProofContext,
        kind: ProofKind,
        root: bytes,
        key: StableKey,
        entry: bytes | None,
    ) -> None:
        verify_sparse_proof(
            body,
            expected_context=context,
            expected_kind=kind,
            expected_root=root,
            stable_key=key,
            canonical_entry=entry,
        )

    cases = (
        (
            source_member,
            ProofContext.SOURCE,
            ProofKind.MEMBERSHIP,
            source_tree.root,
            source_key,
            source_entry_bytes(source_entry),
        ),
        (
            source_none,
            ProofContext.SOURCE,
            ProofKind.NONMEMBERSHIP,
            source_tree.root,
            source_absent,
            None,
        ),
        (
            anchor_member,
            ProofContext.ANCHOR,
            ProofKind.MEMBERSHIP,
            anchor_tree.root,
            anchor_key,
            anchor_entry_bytes(anchor_entry),
        ),
        (
            anchor_none,
            ProofContext.ANCHOR,
            ProofKind.NONMEMBERSHIP,
            anchor_tree.root,
            anchor_absent,
            None,
        ),
    )
    for case in cases:
        verify(*case)
    empty_source = SparseMerkleTree(ProofContext.SOURCE, {})
    empty_anchor = SparseMerkleTree(ProofContext.ANCHOR, {})
    golden = {
        "anchor_membership_sha256": hashlib.sha256(anchor_member).hexdigest(),
        "anchor_nonmembership_sha256": hashlib.sha256(anchor_none).hexdigest(),
        "anchor_root": anchor_tree.root.hex(),
        "empty_anchor_root": empty_anchor.root.hex(),
        "empty_source_root": empty_source.root.hex(),
        "source_membership_sha256": hashlib.sha256(source_member).hexdigest(),
        "source_nonmembership_sha256": hashlib.sha256(source_none).hexdigest(),
        "source_root": source_tree.root.hex(),
    }
    harness.check(
        "sparse_layout_context_and_golden_are_exact",
        {len(case[0]) for case in cases} == {SPARSE_PROOF_BYTES}
        and source_tree.root != anchor_tree.root
        and empty_source.root != empty_anchor.root
        and golden == SYNTHETIC_PROOF_GOLDEN,
    )
    for label, hostile in (
        ("length", source_member[:-1]),
        ("context", _mutate_byte(source_member, 8, ProofContext.ANCHOR.wire_byte)),
        ("root", _mutate_byte(source_member, 16, source_member[16] ^ 1)),
        ("siblings", _reverse_sibling_chunks(source_member)),
    ):
        harness.reject(
            "proof_rejects_" + label + "_substitution",
            lambda hostile=hostile: verify(
                hostile,
                ProofContext.SOURCE,
                ProofKind.MEMBERSHIP,
                source_tree.root,
                source_key,
                source_entry_bytes(source_entry),
            ),
        )
    harness.reject(
        "proof_rejects_cross_context_verification",
        lambda: verify(
            anchor_member,
            ProofContext.SOURCE,
            ProofKind.MEMBERSHIP,
            anchor_tree.root,
            anchor_key,
            anchor_entry_bytes(anchor_entry),
        ),
    )
    harness.accept("source_and_anchor_sparse_proof_product")
    harness.witness("proof_contexts_are_not_interchangeable")
    harness.witness("proof_body_layout_is_exactly_NCOGSPV1_8272")


TYPED_ARTIFACT_NAMES = tuple(
    sorted(
        name
        for name, value in globals().items()
        if isinstance(value, type)
        and value.__name__ == name
        and (hasattr(value, "__dataclass_fields__") or value is SparseMerkleTree)
    )
)


def canonical_digest(value: object) -> str:
    raw = json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def build_result() -> dict[str, Any]:
    harness = Harness()
    scenario_closed_enum_matrix(harness)
    scenario_namespace_anchor_bootstrap_races(harness)
    scenario_root_enrollment_handshake_races(harness)
    scenario_profile_and_enrollment(harness)
    scenario_registered_root_retirement_currentness(harness)
    scenario_local_prepare_and_closure_races(harness)
    scenario_slot_lifecycle_and_source_freeze(harness)
    scenario_anchor_gate_and_authoritative_queue(harness)
    scenario_cooperative_anchor_retirement(harness)
    scenario_anchor_conservative_resolution(harness)
    scenario_exact_sparse_proofs(harness)

    limits = {
        "anchor_global_bytes": ANCHOR_GLOBAL_BYTE_CAP,
        "anchor_global_participant_units": ANCHOR_GLOBAL_PARTICIPANT_CAP,
        "anchor_owner_bytes": ANCHOR_OWNER_BYTE_CAP,
        "anchor_owner_participant_units": ANCHOR_OWNER_PARTICIPANT_CAP,
        "anchor_reservation_bytes": ANCHOR_RESERVATION_BYTE_CHARGE,
        "anchor_reservation_participant_units": (ANCHOR_RESERVATION_PARTICIPANT_CHARGE),
        "capsule_bytes": MAX_CAPSULE_BYTES,
        "challenge_bytes": MAX_CHALLENGE_BYTES,
        "clock_offset_absolute": CLOCK_OFFSET_ABS_MAX,
        "clock_value": CLOCK_VALUE_MAX,
        "eligible_roots": MAX_ELIGIBLE_ROOTS,
        "generation_slots": MAX_GENERATION_SLOTS,
        "identifier_utf8_bytes": MAX_IDENTIFIER_UTF8_BYTES,
        "issuance_entries": MAX_ISSUANCE_ENTRIES,
        "lineage_incarnations_per_namespace": (MAX_LINEAGE_INCARNATIONS_PER_NAMESPACE),
        "namespace_utf8_bytes": MAX_NAMESPACE_UTF8_BYTES,
        "observer_operations": MAX_OBSERVER_OPERATIONS,
        "observer_enrollments": MAX_OBSERVER_ENROLLMENTS,
        "observer_retained_bytes": MAX_OBSERVER_RETAINED_BYTES,
        "observer_tombstones": MAX_OBSERVER_TOMBSTONES,
        "paired_queue_records": MAX_QUEUE_RECORDS,
        "producer_namespaces": MAX_PRODUCER_NAMESPACES,
        "requester_frame_bytes": MAX_REQUESTER_FRAME_BYTES,
        "retired_transport_contexts": MAX_RETIRED_TRANSPORT_CONTEXTS,
        "sparse_proof_bytes": SPARSE_PROOF_BYTES,
        "sparse_tree_height": SPARSE_TREE_HEIGHT,
        "stable_key_utf8_bytes": MAX_STABLE_KEY_UTF8_BYTES,
        "transport_contexts": MAX_VERIFIED_TRANSPORT_CONTEXTS,
        "transport_security_epochs": MAX_TRANSPORT_SECURITY_EPOCHS,
    }
    if (
        len(harness.accepted) > 64
        or len(harness.invariants) > 256
        or len(harness.rejections) > 256
        or len(harness.witnesses) > 128
    ):
        raise AssertionError("probe result exceeded its declared output bounds")
    semantic_model = {
        "abstraction_boundaries": [
            "DISTRIBUTED_GRANT_CLOSURE_IS_PROTECTED_CURRENT_SOURCE_OUTPUT_OVER_SYNTHETIC_EXTERNAL_EVIDENCE_NOT_LIVE_QUALIFICATION",
            "BODY_PLANT_PROFILE_AUTHORITY_AND_ANCESTRY_ARE_SYNTHETIC_INPUTS_NOT_PHYSICAL_OR_DEPLOYMENT_QUALIFICATION",
            "OPAQUE_CREDENTIALS_EXACT_STORE_MEMBERSHIP_AND_TERMINAL_RECEIPTS_ARE_SYNTHETIC_AUTHORITY_INPUTS_NOT_CRYPTOGRAPHIC_EVIDENCE",
            "PERMANENT_ISOLATION_INVENTORY_IS_A_SYNTHETIC_INPUT_NOT_EXTERNAL_QUALIFICATION",
            "SERIALIZED_HANDOFF_RETURN_MODELS_AN_EXCLUSIVE_DISPATCH_TOKEN_NOT_AN_ATOMIC_DATABASE_NETWORK_DELIVERY",
            "SPARSE_ENTRY_PROJECTIONS_ARE_LOCAL_FIXTURES_WHILE_PROOF_LAYOUT_AND_ROOT_MECHANICS_FOLLOW_THE_PROPOSED_ADR",
        ],
        "atomicity": {
            "anchor_authority_joint_participants": [
                "INDEPENDENT_ANCHOR_RUNTIME",
                "AUTHORITY_NAMESPACE_SLOT_AND_INDICES",
            ],
            "anchor_authority_store": "ONE_CONFIGURED_ANCHOR_AUTHORITY_CAS_DOMAIN",
            "namespace_registration_order": [
                "SOURCE_REGISTRY_COMMIT",
                "ANCHOR_AUTHORITY_ACTIVATION_COMMIT",
            ],
            "observer_local_store": "INDEPENDENT_CAS_DOMAIN",
            "source_namespace_registry": "INDEPENDENT_CAS_DOMAIN",
            "source_domain_joint_participants": [
                "SOURCE_ISSUANCE_INDEX",
                "GENERATION_LOCAL_FRESHNESS_SLOTS",
                "AUTHORITATIVE_PAIRED_FRAME_QUEUE",
            ],
            "source_domain_independent_read_only_participants": [
                "BODY_PLANT_PROFILE_AUTHORITY",
                "REGISTERED_ROOT_AUTHORITY_PRODUCER",
                "TRANSPORT_AUTHORITY",
            ],
            "synthetic_cross_store_cas": False,
        },
        "accepted_scenarios": sorted(harness.accepted),
        "availability_profiles": sorted(profile.value for profile in Availability),
        "anchor_closure_causes": sorted(cause.value for cause in AnchorClosureCause),
        "anchor_closure_evidence_states": sorted(
            state.value for state in AnchorEvidenceState
        ),
        "bootstrap": {
            "authority_coordinate_indices": [
                "ANCHOR_SELECTOR_INCARNATION",
                "LINEAGE_SELECTOR_INCARNATION",
                "RESERVATION_INTENT_ID",
                "SOURCE_INDEX_SELECTOR_INCARNATION",
                "SOURCE_NAMESPACE",
                "SOURCE_OWNER_KEY_AND_LIFETIME_SLOT",
            ],
            "capacity_refund": "NEVER",
            "owner_capacity_borrowing": "FORBIDDEN",
            "anchor_states": sorted(state.value for state in AnchorBootstrap),
            "reservation_states": sorted(state.value for state in ReservationState),
            "source_states": sorted(state.value for state in SourceBootstrap),
            "synthetic_cross_store_cas": False,
        },
        "claim_boundary": (
            "LOCAL_DETERMINISTIC_SYNTHETIC_FALSIFICATION_ONLY_NOT_NORMATIVE_"
            "REFINEMENT_INTEROPERABILITY_SECURITY_SAFETY_EXTERNAL_REVIEW_OR_"
            "RELEASE_EVIDENCE"
        ),
        "closure_origins": sorted(origin.value for origin in ClosureOrigin),
        "closure_evidence_states": sorted(
            state.value for state in ClosureEvidenceState
        ),
        "delivery_gates": sorted(gate.value for gate in DeliveryGate),
        "handoff_quiescence_results": sorted(result.value for result in HandoffResult),
        "hostile_rejections": sorted(harness.rejections),
        "invariants": sorted(harness.invariants),
        "limits": limits,
        "local_operation_states": sorted(state.value for state in OperationState),
        "opaque_authority_type_names": sorted(
            name
            for name, value in globals().items()
            if isinstance(value, type) and name.startswith("Opaque")
        ),
        "proof": {
            "contexts": sorted(context.value for context in ProofContext),
            "local_synthetic_golden": SYNTHETIC_PROOF_GOLDEN,
            "kinds": sorted(kind.value for kind in ProofKind),
            "magic": SPARSE_PROOF_MAGIC.decode("ascii"),
            "suite": SPARSE_SUITE,
        },
        "resolution_outcomes": sorted(outcome.value for outcome in ResolutionOutcome),
        "root_admission_phases": sorted(phase.value for phase in RootAdmissionPhase),
        "slot_states": sorted(state.value for state in SlotState),
        "time_semantics": {
            "acceptance": "BOUNDED_UPPER_STRICTLY_BEFORE_EXCLUSIVE_CUTOFF",
            "expiry": "BOUNDED_LOWER_AT_OR_AFTER_EXCLUSIVE_CUTOFF",
            "expiry_epoch": "EXACT_SOURCE_CLOCK_SESSION_AND_SECURITY_EPOCH",
        },
        "transport_channel_states": sorted(state.value for state in TransportState),
        "typed_artifact_names": list(TYPED_ARTIFACT_NAMES),
        "witnesses": sorted(harness.witnesses),
    }
    counts = {
        "accepted_scenarios": len(harness.accepted),
        "invariants": len(harness.invariants),
        "rejected_hostile_cases": len(harness.rejections),
        "typed_artifacts": len(TYPED_ARTIFACT_NAMES),
        "witnesses": len(harness.witnesses),
    }
    return {
        "schema": "ncp.b01-source-issuance-index-probe.v1",
        "scope": "bounded-local-synthetic-counterexample-discovery",
        "claim_boundary": CLAIM_BOUNDARY,
        "counts": counts,
        "semantic_digest": canonical_digest(semantic_model),
    }


EXPECTED_SOURCE_PROBE_COUNTS = {
    "accepted_scenarios": 20,
    "invariants": 71,
    "rejected_hostile_cases": 188,
    "typed_artifacts": 77,
    "witnesses": 27,
}
EXPECTED_SOURCE_PROBE_SEMANTIC_DIGEST = (
    "cb36719f18ae78f2cc0a8fdb3f149ac31ed17a80968a15733228c2db65bd59a6"
)


def validate_result(value: Any) -> None:
    if type(value) is not dict or set(value) != {
        "schema",
        "scope",
        "claim_boundary",
        "counts",
        "semantic_digest",
    }:
        raise Reject()
    if (
        value["schema"] != "ncp.b01-source-issuance-index-probe.v1"
        or value["scope"] != "bounded-local-synthetic-counterexample-discovery"
        or value["claim_boundary"] != CLAIM_BOUNDARY
        or value["counts"] != EXPECTED_SOURCE_PROBE_COUNTS
        or value["semantic_digest"] != EXPECTED_SOURCE_PROBE_SEMANTIC_DIGEST
    ):
        raise Reject()


def _self_test(value: dict[str, Any]) -> None:
    validate_result(value)
    repeated = build_result()
    if json.dumps(value, sort_keys=True) != json.dumps(repeated, sort_keys=True):
        raise Reject()
    mutations: tuple[tuple[tuple[str, ...], object], ...] = (
        (("schema",), "ncp.b01-source-issuance-index-probe.v999"),
        (("scope",), "certified"),
        (("claim_boundary",), "protocol correctness proven"),
        (("counts", "accepted_scenarios"), 0),
        (("counts", "invariants"), 0),
        (("counts", "rejected_hostile_cases"), 0),
        (("counts", "typed_artifacts"), 0),
        (("counts", "witnesses"), 0),
        (("semantic_digest",), "0" * 64),
    )
    for path, replacement in mutations:
        hostile = copy.deepcopy(value)
        if len(path) == 1:
            hostile[path[0]] = replacement
        else:
            nested = hostile[path[0]]
            if type(nested) is not dict:
                raise Reject()
            nested[path[1]] = replacement
        try:
            validate_result(hostile)
        except Reject:
            continue
        raise Reject()
    for omitted in ("counts", "semantic_digest"):
        hostile = copy.deepcopy(value)
        del hostile[omitted]
        try:
            validate_result(hostile)
        except Reject:
            continue
        raise Reject()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    arguments = parser.parse_args()
    result = build_result()
    validate_result(result)
    if arguments.self_test:
        _self_test(result)
    print(json.dumps(result, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
