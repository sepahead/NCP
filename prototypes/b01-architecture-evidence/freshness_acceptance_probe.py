#!/usr/bin/env python3
"""Falsify bounded freshness, acceptance, and fail-safe design assumptions.

This deterministic model is synthetic, non-normative B01 challenge material.
It is not an NCP implementation, refinement proof, transport qualification,
physical-safety argument, production-deadline measurement, or release gate.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import itertools
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import IntEnum, StrEnum
from typing import Any


class ProbeError(RuntimeError):
    """One bounded probe obligation failed closed."""


class Mode(StrEnum):
    """Closed action mode used by the synthetic model."""

    ACTIVE = "ACTIVE"
    HOLD = "HOLD"
    ESTOP = "ESTOP"


class Severity(IntEnum):
    """Restrictive-action order. Larger values are more restrictive."""

    ACTIVE = 0
    HOLD = 1
    ESTOP = 2


class EndpointProof(StrEnum):
    """Evidence available while resolving one external transport attempt."""

    ACCEPTED = "ACCEPTED"
    NO_ACCEPTANCE = "NO_ACCEPTANCE"
    NONE = "NONE"


class GateOrder(StrEnum):
    """Authenticated order between acceptance and a gate fence."""

    NO_FENCE = "NO_FENCE"
    ACCEPTANCE_BEFORE_FENCE = "ACCEPTANCE_BEFORE_FENCE"
    FENCE_BEFORE_ACCEPTANCE = "FENCE_BEFORE_ACCEPTANCE"
    UNKNOWN = "UNKNOWN"


class TransportDisposition(StrEnum):
    """Closed synthetic external-transport result."""

    DELIVERED = "DELIVERED"
    REJECTED = "REJECTED"
    AMBIGUOUS = "AMBIGUOUS"
    INVALID_EVIDENCE = "INVALID_EVIDENCE"


class CrashCut(StrEnum):
    """Crash points around one Active value/watchdog transaction."""

    BEFORE_COMMIT = "BEFORE_COMMIT"
    BETWEEN_VALUE_AND_WATCHDOG = "BETWEEN_VALUE_AND_WATCHDOG"
    AFTER_COMMIT = "AFTER_COMMIT"


@dataclass(frozen=True)
class Mutation:
    """One isolated hostile design change."""

    name: str
    expected_violation: str


MUTATIONS: tuple[Mutation, ...] = (
    Mutation("deadline_from_receive", "body_absolute_deadline"),
    Mutation("deadline_from_sender", "body_absolute_deadline"),
    Mutation("ttl_deadline_omitted", "body_absolute_deadline"),
    Mutation("deadline_equality_accepted", "strict_acceptance_deadline"),
    Mutation("start_proves_acceptance", "acceptance_not_start"),
    Mutation("acceptance_order_unchecked", "acceptance_after_start"),
    Mutation("retry_refreshes_deadline", "retry_preserves_deadline"),
    Mutation("non_body_grant_accepted", "body_issued_grant"),
    Mutation("slot_position_unbound", "exact_grant_slot"),
    Mutation("retired_slot_reused", "retired_slot_tombstone"),
    Mutation("grant_mode_unbound", "grant_mode_bound"),
    Mutation("grant_clock_unbound", "grant_clock_bound"),
    Mutation("lazy_expiry_reclassified", "expiry_outcome_stable"),
    Mutation("hold_rechecks_retired_grant", "reservation_snapshot_stable"),
    Mutation("timeout_is_rejected", "transport_ambiguity_preserved"),
    Mutation("local_return_is_delivered", "transport_ambiguity_preserved"),
    Mutation("fence_checked_only_at_start", "transport_fence_linearized"),
    Mutation("unknown_gate_order_delivered", "transport_gate_order_required"),
    Mutation("late_resolution_forgets_acceptance", "pre_fence_acceptance_stable"),
    Mutation("exact_replay_allocates_attempt", "exact_replay_no_attempt"),
    Mutation("exact_replay_reinvokes_effect", "exact_replay_no_effect"),
    Mutation("signature_variant_allocates", "signature_variant_no_state"),
    Mutation("conflicts_are_unbounded", "bounded_position_conflicts"),
    Mutation("content_is_position_key", "position_key_stable"),
    Mutation("effect_slot_capacity_unbounded", "bounded_effect_slots"),
    Mutation("repeat_estop_upgrade_reinvokes", "single_estop_upgrade"),
    Mutation("command_chain_keyed_by_position", "single_command_chain"),
    Mutation("hold_clears_after_estop_pending", "pending_estop_dominates_hold"),
    Mutation("hold_clears_after_estop_accepted", "accepted_estop_dominates_hold"),
    Mutation(
        "restrictive_missing_arbiter_pending",
        "arbiter_pending_precedes_body_mirror",
    ),
    Mutation(
        "restrictive_invokes_before_body_mirror",
        "body_mirror_precedes_invocation",
    ),
    Mutation(
        "restrictive_resolves_before_invocation",
        "invocation_precedes_arbiter_resolution",
    ),
    Mutation(
        "restrictive_completes_before_arbiter_resolution",
        "arbiter_resolution_precedes_body_completion",
    ),
    Mutation(
        "restrictive_replay_reinvokes",
        "unified_exact_replay_no_second_invocation",
    ),
    Mutation(
        "restrictive_replay_recompletes",
        "unified_exact_replay_no_second_completion",
    ),
    Mutation(
        "restrictive_reuses_fence_epoch",
        "unified_fresh_fence_epoch",
    ),
    Mutation(
        "restrictive_mirror_wrong_token",
        "body_mirror_binds_pending_operation",
    ),
    Mutation(
        "restrictive_reuses_consumed_token",
        "unified_chain_token_one_use",
    ),
    Mutation(
        "upgrade_reuses_hold_token",
        "upgrade_uses_fresh_chain_token",
    ),
    Mutation(
        "upgrade_without_completed_hold",
        "upgrade_requires_completed_hold",
    ),
    Mutation(
        "upgrade_bypasses_arbiter",
        "upgrade_uses_unified_physical_dag",
    ),
    Mutation(
        "drain_estop_bypasses_arbiter",
        "drain_estop_uses_unified_physical_dag",
    ),
    Mutation(
        "capacity_fallback_bypasses_arbiter",
        "capacity_fallback_uses_unified_physical_dag",
    ),
    Mutation(
        "capacity_fallback_uses_general_token",
        "capacity_fallback_uses_pre_reserved_token",
    ),
    Mutation(
        "capacity_retirement_uses_fail_safe_reservation_mirror",
        "capacity_retirement_uses_cause_owned_pending_mirror",
    ),
    Mutation(
        "capacity_retirement_uses_fail_safe_result_mirror",
        "capacity_retirement_uses_generic_result_mirror",
    ),
    Mutation(
        "unified_hold_effect_after_estop_pending",
        "unified_severity_order",
    ),
    Mutation(
        "restrictive_recovery_mints_token",
        "unified_crash_recovery_identity",
    ),
    Mutation(
        "restrictive_recovery_reinvokes",
        "unified_crash_recovery_no_reinvocation",
    ),
    Mutation(
        "hold_outcome_unknown_aliases_effective",
        "hold_outcome_unknown_is_distinct",
    ),
    Mutation(
        "hold_outcome_unknown_is_nonterminal",
        "hold_outcome_unknown_is_terminal",
    ),
    Mutation(
        "exact_retirement_rewrites_hold_unknown",
        "exact_retirement_preserves_terminal_hold_result",
    ),
    Mutation(
        "finalize_from_hold_pending",
        "hold_pending_cannot_finalize",
    ),
    Mutation(
        "lost_isolation_skips_proof",
        "lost_isolation_requires_proof",
    ),
    Mutation(
        "lost_isolation_closes_hold_effective",
        "lost_isolation_pending_hold_becomes_unknown",
    ),
    Mutation(
        "lost_isolation_leaves_hold_pending",
        "lost_isolation_pending_hold_becomes_unknown",
    ),
    Mutation(
        "non_specialized_retirement_allows_estop_latched",
        "non_specialized_retirement_rejects_estop_latched",
    ),
    Mutation(
        "non_specialized_retirement_allows_estop_unknown",
        "non_specialized_retirement_rejects_estop_unknown",
    ),
    Mutation(
        "unknown_retirement_closure_kind_accepted",
        "retirement_closure_union_closed",
    ),
    Mutation(
        "unknown_retirement_hold_state_accepted",
        "retirement_hold_lifecycle_union_closed",
    ),
    Mutation(
        "unknown_retirement_estop_floor_accepted",
        "retirement_estop_floor_union_closed",
    ),
    Mutation(
        "unknown_retirement_authorization_allows_estop",
        "retirement_authorization_union_closed",
    ),
    Mutation(
        "forged_lost_isolation_evidence_finalizes",
        "lost_isolation_proof_revalidated_at_finalization",
    ),
    Mutation(
        "forged_lost_pending_effective_finalizes",
        "lost_pending_closure_shape_exact",
    ),
    Mutation(
        "forged_exact_terminal_hold_without_preservation_finalizes",
        "exact_terminal_hold_preservation_revalidated",
    ),
    Mutation(
        "generation_without_actuation_domain",
        "generation_has_exactly_one_actuation_domain",
    ),
    Mutation(
        "generation_with_multiple_actuation_domains",
        "generation_has_exactly_one_actuation_domain",
    ),
    Mutation(
        "arbiter_mirror_cross_domain",
        "arbiter_mirror_matches_generation_domain",
    ),
    Mutation(
        "cross_domain_atomic_success",
        "atomic_success_stays_within_one_domain",
    ),
    Mutation(
        "independent_domains_share_session",
        "independent_domains_require_independent_sessions",
    ),
    Mutation(
        "same_domain_multi_actuator_rejected",
        "qualified_multi_actuator_domain_permitted",
    ),
    Mutation(
        "actuation_domain_key_unknown_default",
        "actuation_domain_key_closed",
    ),
    Mutation(
        "conflict_graph_omits_active",
        "conflict_graph_covers_active",
    ),
    Mutation(
        "conflict_graph_omits_hold",
        "conflict_graph_covers_hold",
    ),
    Mutation(
        "conflict_graph_omits_estop",
        "conflict_graph_covers_estop",
    ),
    Mutation(
        "conflict_graph_omits_watchdog",
        "conflict_graph_covers_watchdog",
    ),
    Mutation(
        "conflict_graph_omits_interlock",
        "conflict_graph_covers_interlock",
    ),
    Mutation(
        "conflict_graph_omits_reset",
        "conflict_graph_covers_reset",
    ),
    Mutation(
        "conflict_graph_omits_shared_bus",
        "conflict_graph_covers_shared_bus",
    ),
    Mutation(
        "domain_selector_cas_ignored",
        "global_domain_selector_serializes",
    ),
    Mutation(
        "disjoint_domains_conflict",
        "disjoint_domains_can_reserve_separately",
    ),
    Mutation(
        "domain_registry_unbounded",
        "domain_registry_bounded",
    ),
    Mutation(
        "caller_selected_domain_substitution",
        "creation_receipt_binds_reserved_domain",
    ),
    Mutation(
        "registry_allows_generation_domain_rebind",
        "registry_generation_owns_one_domain",
    ),
    Mutation(
        "incomplete_effect_footprint_accepted",
        "effect_footprint_complete",
    ),
    Mutation(
        "conflict_graph_scoped_per_body",
        "global_conflicts_span_body_principals",
    ),
    Mutation(
        "wrong_physical_jurisdiction_enrolled",
        "registration_matches_selector_jurisdiction",
    ),
    Mutation(
        "wrong_jurisdiction_incarnation_enrolled",
        "registration_matches_selector_incarnation",
    ),
    Mutation(
        "duplicate_live_jurisdiction_selector",
        "one_live_selector_per_jurisdiction_incarnation",
    ),
    Mutation(
        "topology_change_without_full_fence",
        "topology_change_requires_complete_fence",
    ),
    Mutation(
        "topology_change_without_physical_isolation",
        "topology_change_requires_physical_isolation",
    ),
    Mutation(
        "topology_change_without_reenrollment",
        "topology_change_requires_full_reenrollment",
    ),
    Mutation(
        "physical_jurisdiction_key_unknown_default",
        "physical_jurisdiction_key_closed",
    ),
    Mutation(
        "jurisdiction_incarnation_unknown_default",
        "physical_jurisdiction_incarnation_closed",
    ),
    Mutation(
        "physical_topology_digest_unknown_default",
        "physical_actuation_topology_digest_closed",
    ),
    Mutation(
        "domain_body_principal_unknown_default",
        "domain_body_principal_closed",
    ),
    Mutation(
        "domain_session_id_unknown_default",
        "domain_session_id_closed",
    ),
    Mutation(
        "domain_generation_id_unknown_default",
        "domain_generation_id_closed",
    ),
    Mutation(
        "effect_footprint_resource_unknown_default",
        "effect_footprint_resources_closed",
    ),
    Mutation(
        "jurisdiction_selector_id_unknown_default",
        "jurisdiction_selector_id_closed",
    ),
    Mutation(
        "concurrent_jurisdiction_incarnations",
        "one_live_incarnation_per_jurisdiction",
    ),
    Mutation(
        "receipt_prior_version_boolean_default",
        "creation_receipt_version_exact_integer",
    ),
    Mutation(
        "actuation_domain_actuator_set_unbounded",
        "actuation_domain_cardinality_bounded",
    ),
    Mutation("active_watchdog_after_value", "active_watchdog_atomic"),
    Mutation("active_watchdog_before_value", "active_watchdog_atomic"),
    Mutation("watchdog_is_volatile", "active_watchdog_persistent"),
    Mutation("replay_refreshes_watchdog", "active_replay_no_refresh"),
    Mutation("watchdog_exceeds_bounds", "active_watchdog_bounded"),
    Mutation("watchdog_clock_restart_copies_deadline", "watchdog_restart_fails_closed"),
    Mutation("prestart_cut_leaves_admitted_tip", "prestart_cut_terminalizes"),
    Mutation("prestart_cut_requires_attempt", "prestart_cut_terminalizes"),
    Mutation(
        "pre_admission_effect_reused_as_applied",
        "pre_admission_effect_not_application",
    ),
    Mutation("drain_grant_not_preallocated", "drain_grant_preallocated"),
    Mutation("drain_allows_general_mode", "drain_estop_only"),
    Mutation("drain_mints_second_grant", "single_drain_grant"),
    Mutation("drain_mints_second_token", "single_drain_token"),
    Mutation("drain_leaves_remote_edge_open", "drain_use_closes_remote_edge"),
    Mutation("intent_sender_time_authorizes", "intent_receiver_freshness"),
    Mutation("intent_receive_refreshes", "intent_receiver_freshness"),
    Mutation("intent_non_receiver_grant", "intent_receiver_issued_grant"),
    Mutation("body_type_aliases_authorize", "body_input_types_closed"),
    Mutation("transport_type_aliases_authorize", "transport_input_types_closed"),
    Mutation("intent_type_aliases_authorize", "intent_input_types_closed"),
    Mutation("effect_command_subclass_authorizes", "effect_command_input_types_closed"),
    Mutation(
        "restrictive_path_alias_authorizes", "restrictive_path_input_types_closed"
    ),
    Mutation(
        "foreign_restrictive_operation_authorized",
        "restrictive_operation_capability_identity",
    ),
    Mutation(
        "retirement_evidence_subclass_authorized",
        "retirement_evidence_types_closed",
    ),
    Mutation("actuation_binding_subclass_authorized", "actuation_binding_types_closed"),
    Mutation(
        "actuation_registration_subclass_authorized",
        "actuation_registration_types_closed",
    ),
    Mutation(
        "equal_creation_receipt_authorized",
        "creation_receipt_capability_identity",
    ),
    Mutation("active_type_aliases_authorize", "active_input_types_closed"),
    Mutation("drain_type_aliases_authorize", "drain_input_types_closed"),
    Mutation(
        "equal_drain_grant_authorized",
        "drain_grant_capability_identity",
    ),
    Mutation(
        "orphan_effect_token_authorized",
        "effect_token_provenance_closed",
    ),
    Mutation(
        "forged_restrictive_state_authorized",
        "restrictive_retained_state_closed",
    ),
    Mutation(
        "incomplete_restrictive_replay_authorized",
        "restrictive_replay_terminal_only",
    ),
    Mutation(
        "caller_constructed_retirement_evidence_authorized",
        "retirement_evidence_issuer_identity",
    ),
    Mutation(
        "retirement_isolation_proof_equality_authorized",
        "physical_isolation_capability_identity",
    ),
    Mutation(
        "caller_constructed_active_state_authorized",
        "active_retained_state_closed",
    ),
    Mutation(
        "selector_derived_state_unchecked",
        "selector_derived_state_exact",
    ),
    Mutation(
        "selector_scope_cache_trusted",
        "selector_scope_revalidated",
    ),
    Mutation(
        "forged_drain_state_authorized",
        "drain_retained_state_closed",
    ),
    Mutation(
        "unbounded_identifier_authorized",
        "authority_identifiers_bounded",
    ),
    Mutation(
        "ordinary_participant_commitment_binds_candidate_head",
        "ordinary_participant_admission_digest_dag_acyclic",
    ),
)

MUTATION_NAMES = frozenset(mutation.name for mutation in MUTATIONS)

REQUIRED_WITNESSES = frozenset(
    {
        "absolute_deadline_ignores_delayed_receive_for_all_modes",
        "acceptance_at_deadline_rejects",
        "late_acceptance_after_early_start_rejects",
        "acceptance_before_attempt_start_rejects",
        "sender_timestamp_is_non_authoritative",
        "retry_keeps_original_acceptance_deadline",
        "wrong_body_grant_rejects",
        "wrong_slot_rejects",
        "retired_slot_rejects",
        "wrong_mode_rejects",
        "wrong_clock_rejects",
        "expired_outcome_survives_later_fence",
        "hold_uses_captured_reservation_after_grant_retirement",
        "pre_fence_acceptance_resolves_after_fence",
        "fence_before_acceptance_blocks_delivery",
        "missing_gate_order_is_ambiguous",
        "timeout_without_endpoint_proof_is_ambiguous",
        "definitive_no_acceptance_is_rejected",
        "exact_replay_allocates_nothing",
        "active_signature_variants_allocate_nothing",
        "same_position_conflicts_saturate",
        "third_position_hits_capacity_without_eviction",
        "hold_to_estop_upgrades_once",
        "same_command_other_position_has_one_chain",
        "pending_estop_supersedes_delayed_hold",
        "accepted_estop_supersedes_delayed_hold",
        "initial_hold_uses_unified_physical_dag",
        "initial_estop_uses_unified_physical_dag",
        "hold_to_estop_upgrade_uses_new_chain_token_and_epoch",
        "drain_estop_uses_pre_reserved_chain_token_and_epoch",
        "capacity_fallback_uses_pre_reserved_chain_token_and_epoch",
        "capacity_retirement_uses_cause_owned_pending_mirror",
        "capacity_retirement_uses_generic_result_mirror",
        "every_restrictive_path_invokes_once",
        "body_mirror_binds_exact_pending_operation",
        "arbiter_resolution_precedes_body_completion",
        "restrictive_chain_token_is_one_use",
        "upgrade_requires_completed_hold_predecessor",
        "pending_estop_rejects_delayed_hold_without_effect",
        "exact_replay_returns_terminal_chain_without_invocation",
        "crash_at_each_dag_cut_reuses_exact_operation",
        "hold_outcome_unknown_is_distinct_and_terminal",
        "exact_arbiter_retirement_preserves_terminal_hold_result",
        "hold_pending_cannot_finalize",
        "lost_arbiter_isolation_requires_proof",
        "lost_arbiter_isolation_terminalizes_pending_hold_as_unknown",
        "non_specialized_retirement_rejects_both_estop_floors",
        "specialized_retirement_accepts_both_estop_floors",
        "retirement_closed_unions_reject_unknown_values",
        "retirement_finalization_revalidates_closure_evidence",
        "generation_binds_one_domain_and_one_scalar_mirror",
        "qualified_domain_can_contain_multiple_atomic_actuators",
        "cross_domain_atomic_success_rejects",
        "independent_domains_use_independent_sessions",
        "global_conflict_graph_covers_every_effect_channel",
        "global_domain_selector_serializes_reservations",
        "disjoint_domains_serialize_and_both_reserve",
        "domain_creation_receipt_selects_reservation",
        "domain_registry_is_bounded",
        "generation_registry_owns_one_domain",
        "effect_footprint_requires_every_channel",
        "overlapping_body_principals_conflict_globally",
        "one_live_selector_owns_each_jurisdiction_incarnation",
        "topology_change_fences_isolates_and_reenrolls",
        "actuation_domain_scope_and_owner_identifiers_fail_closed",
        "effect_footprint_resource_ids_fail_closed",
        "one_live_incarnation_owns_each_physical_jurisdiction",
        "actuation_domain_cardinality_is_bounded",
        "active_value_and_watchdog_are_atomic",
        "watchdog_survives_restart",
        "active_replay_does_not_refresh_watchdog",
        "new_active_value_respects_command_and_lease_bounds",
        "watchdog_clock_discontinuity_has_restrictive_receipt",
        "prestart_cut_closes_admitted_without_attempt",
        "pre_admission_effect_has_distinct_restrictive_association",
        "drain_grant_is_preallocated",
        "drain_has_one_estop_only_grant",
        "drain_has_one_escalation_token",
        "drain_token_use_closes_remote_edge",
        "intent_uses_receiver_issued_freshness",
        "intent_delayed_receive_does_not_refresh",
        "all_authority_inputs_use_exact_closed_types_and_capability_identity",
        "all_retained_authority_state_is_semantically_closed_and_provenanced",
        "ordinary_participant_admission_digest_dag_is_exact_and_acyclic",
    }
)

EXPECTED_CASE_COUNTS = {
    "body_freshness": 254,
    "transport_acceptance": 9,
    "effect_journal": 33,
    "unified_physical_boundary": 62,
    "retirement_closure": 18,
    "actuation_domain_binding": 40,
    "active_watchdog": 8,
    "retirement_drain": 8,
    "intent_freshness": 3,
    "input_closedness": 69,
    "semantic_state_closure": 37,
    "ordinary_participant_admission_dag": 6,
}
EXPECTED_HOSTILE_REJECTION_COUNTS = {
    "body_freshness": 198,
    "transport_acceptance": 8,
    "effect_journal": 1,
    "unified_physical_boundary": 5,
    "retirement_closure": 12,
    "actuation_domain_binding": 35,
    "active_watchdog": 0,
    "retirement_drain": 2,
    "intent_freshness": 2,
    "input_closedness": 69,
    "semantic_state_closure": 37,
    "ordinary_participant_admission_dag": 0,
}
EXPECTED_MUTANT_COUNT = 144
EXPECTED_SEMANTIC_RESULT_SHA256 = (
    "b65472caa556971a89dfc8d1f8b23f1a280a83580de4a146bd04924d7b9cf3d3"
)


@dataclass
class Audit:
    """Counters, violations, and non-vacuity evidence for one model run."""

    cases: int = 0
    hostile_rejections: int = 0
    violations: set[str] = field(default_factory=set)
    witnesses: set[str] = field(default_factory=set)
    campaign_cases: dict[str, int] = field(default_factory=dict)
    campaign_hostile_rejections: dict[str, int] = field(default_factory=dict)

    def case(self, count: int = 1) -> None:
        self.cases += count

    def reject(self) -> None:
        self.hostile_rejections += 1

    def require(self, condition: bool, invariant: str) -> None:
        if not condition:
            self.violations.add(invariant)

    def witness(self, name: str, condition: bool = True) -> None:
        if condition:
            self.witnesses.add(name)


def _exact_bool(value: object) -> bool:
    """Reject bool-like subclasses and integer aliases."""

    return type(value) is bool


def _exact_int(value: object) -> bool:
    """Reject booleans and integer subclasses at authority boundaries."""

    return type(value) is int


def _exact_nonnegative_int(value: object) -> bool:
    return _exact_int(value) and value >= 0


def _exact_optional_int(value: object) -> bool:
    return value is None or _exact_int(value)


def _exact_nonempty_str(value: object) -> bool:
    """Accept one exact, non-empty string without normalizing aliases."""

    return type(value) is str and bool(value)


MAX_SYNTHETIC_IDENTIFIER_BYTES = 256


def _exact_closed_identifier(value: object) -> bool:
    """Accept one bounded printable-ASCII non-default identifier."""

    return (
        _exact_nonempty_str(value)
        and 1 <= len(value.encode("utf-8")) <= MAX_SYNTHETIC_IDENTIFIER_BYTES
        and value == value.strip()
        and value.upper() not in {"0", "DEFAULT", "NONE", "UNKNOWN", "UNSPECIFIED"}
        and all(0x20 <= ord(character) <= 0x7E for character in value)
    )


def _exact_optional_closed_identifier(value: object) -> bool:
    return value is None or _exact_closed_identifier(value)


def _exact_enum(value: object, expected: type[StrEnum] | type[IntEnum]) -> bool:
    """Require the exact closed-enum class, not a raw scalar alias."""

    return type(value) is expected


def _exact_tuple_of(
    value: object,
    member_predicate: Any,
    *,
    nonempty: bool = False,
) -> bool:
    if type(value) is not tuple or (nonempty and not value):
        return False
    return all(member_predicate(member) for member in value)


def _exact_frozenset_of(
    value: object,
    member_predicate: Any,
    *,
    nonempty: bool = False,
) -> bool:
    if type(value) is not frozenset or (nonempty and not value):
        return False
    return all(member_predicate(member) for member in value)


def _validate_mutation_selector(mutation: object) -> str | None:
    if mutation is None:
        return None
    if type(mutation) is not str or mutation not in MUTATION_NAMES:
        raise ProbeError(f"unknown or inexact mutation selector {mutation!r}")
    return mutation


@dataclass(frozen=True)
class BodyGrant:
    """Minimum body-issued freshness commitment used by the probe."""

    body_issued: bool
    body_clock: str
    issue_tick: int
    max_not_after: int
    publisher: str
    stream_epoch: str
    slots: tuple[int, ...]
    modes: frozenset[Mode]
    retired_slots: frozenset[int] = frozenset()


@dataclass(frozen=True)
class CommandCandidate:
    """One exact slot-bound command candidate."""

    mode: Mode
    publisher: str
    stream_epoch: str
    sequence: int
    ttl_ticks: int
    sender_tick: int
    receive_tick: int
    start_tick: int
    acceptance_tick: int
    body_clock: str
    retry: bool = False
    proposed_retry_deadline: int | None = None


@dataclass(frozen=True)
class TransportCase:
    """One installed-attempt resolution scenario."""

    start_tick: int
    acceptance_tick: int | None
    original_deadline: int
    proof: EndpointProof
    gate_order: GateOrder
    resolution_tick: int
    fence_tick: int | None = None
    local_return_success: bool = False
    retry: bool = False
    proposed_retry_deadline: int | None = None


@dataclass(frozen=True)
class IntentCase:
    """Receiver-freshness scenario for one synthetic HaldirIntentV2."""

    receiver_issued_grant: bool
    grant_issue_tick: int
    grant_not_after: int
    ttl_ticks: int
    sender_tick: int
    receive_tick: int
    acceptance_tick: int


def _body_grant_is_exact(value: object) -> bool:
    return (
        type(value) is BodyGrant
        and _exact_bool(value.body_issued)
        and _exact_closed_identifier(value.body_clock)
        and _exact_nonnegative_int(value.issue_tick)
        and _exact_nonnegative_int(value.max_not_after)
        and _exact_closed_identifier(value.publisher)
        and _exact_closed_identifier(value.stream_epoch)
        and _exact_tuple_of(value.slots, _exact_nonnegative_int, nonempty=True)
        and _exact_frozenset_of(
            value.modes,
            lambda member: _exact_enum(member, Mode),
            nonempty=True,
        )
        and _exact_frozenset_of(value.retired_slots, _exact_nonnegative_int)
    )


def _command_candidate_is_exact(value: object) -> bool:
    return (
        type(value) is CommandCandidate
        and _exact_enum(value.mode, Mode)
        and _exact_closed_identifier(value.publisher)
        and _exact_closed_identifier(value.stream_epoch)
        and _exact_nonnegative_int(value.sequence)
        and _exact_int(value.ttl_ticks)
        and _exact_nonnegative_int(value.sender_tick)
        and _exact_nonnegative_int(value.receive_tick)
        and _exact_nonnegative_int(value.start_tick)
        and _exact_nonnegative_int(value.acceptance_tick)
        and _exact_closed_identifier(value.body_clock)
        and _exact_bool(value.retry)
        and _exact_optional_int(value.proposed_retry_deadline)
    )


def _transport_case_is_exact(value: object) -> bool:
    return (
        type(value) is TransportCase
        and _exact_nonnegative_int(value.start_tick)
        and (
            value.acceptance_tick is None
            or _exact_nonnegative_int(value.acceptance_tick)
        )
        and _exact_nonnegative_int(value.original_deadline)
        and _exact_enum(value.proof, EndpointProof)
        and _exact_enum(value.gate_order, GateOrder)
        and _exact_nonnegative_int(value.resolution_tick)
        and (value.fence_tick is None or _exact_nonnegative_int(value.fence_tick))
        and _exact_bool(value.local_return_success)
        and _exact_bool(value.retry)
        and _exact_optional_int(value.proposed_retry_deadline)
    )


def _intent_case_is_exact(value: object) -> bool:
    return (
        type(value) is IntentCase
        and _exact_bool(value.receiver_issued_grant)
        and _exact_nonnegative_int(value.grant_issue_tick)
        and _exact_nonnegative_int(value.grant_not_after)
        and _exact_int(value.ttl_ticks)
        and _exact_nonnegative_int(value.sender_tick)
        and _exact_nonnegative_int(value.receive_tick)
        and _exact_nonnegative_int(value.acceptance_tick)
    )


class Model:
    """Correct design or one named single-defect mutation."""

    def __init__(self, mutation: str | None = None) -> None:
        self.mutation = _validate_mutation_selector(mutation)

    def _body_deadline(self, grant: BodyGrant, command: CommandCandidate) -> int:
        issue_tick = grant.issue_tick
        if self.mutation == "deadline_from_receive":
            issue_tick = command.receive_tick
        elif self.mutation == "deadline_from_sender":
            issue_tick = command.sender_tick
        if self.mutation == "ttl_deadline_omitted":
            return grant.max_not_after
        return min(grant.max_not_after, issue_tick + command.ttl_ticks)

    def body_accepts(self, grant: BodyGrant, command: CommandCandidate) -> bool:
        """Evaluate exact grant/slot context and acceptance freshness."""

        if self.mutation not in {
            "body_type_aliases_authorize",
            "unbounded_identifier_authorized",
        } and (
            not _body_grant_is_exact(grant) or not _command_candidate_is_exact(command)
        ):
            return False
        if not grant.body_issued and self.mutation != "non_body_grant_accepted":
            return False
        if (
            grant.body_clock != command.body_clock
            and self.mutation != "grant_clock_unbound"
        ):
            return False
        if grant.publisher != command.publisher:
            return False
        if grant.stream_epoch != command.stream_epoch:
            return False
        if (
            command.sequence not in grant.slots
            and self.mutation != "slot_position_unbound"
        ):
            return False
        if (
            command.sequence in grant.retired_slots
            and self.mutation != "retired_slot_reused"
        ):
            return False
        if command.mode not in grant.modes and self.mutation != "grant_mode_unbound":
            return False
        if command.ttl_ticks <= 0 or grant.issue_tick >= grant.max_not_after:
            return False
        if (
            command.acceptance_tick < command.start_tick
            and self.mutation != "acceptance_order_unchecked"
        ):
            return False

        deadline = self._body_deadline(grant, command)
        if command.retry and self.mutation == "retry_refreshes_deadline":
            if command.proposed_retry_deadline is not None:
                deadline = command.proposed_retry_deadline
        checked_tick = command.acceptance_tick
        if self.mutation == "start_proves_acceptance":
            checked_tick = command.start_tick
        if self.mutation == "deadline_equality_accepted":
            return command.start_tick < deadline and checked_tick <= deadline
        return command.start_tick < deadline and checked_tick < deadline

    def transport_disposition(self, case: TransportCase) -> TransportDisposition:
        """Resolve an attempt from endpoint evidence, not a local result label."""

        if (
            self.mutation != "transport_type_aliases_authorize"
            and not _transport_case_is_exact(case)
        ):
            return TransportDisposition.INVALID_EVIDENCE
        deadline = case.original_deadline
        if case.retry and self.mutation == "retry_refreshes_deadline":
            if case.proposed_retry_deadline is not None:
                deadline = case.proposed_retry_deadline

        if case.proof == EndpointProof.NO_ACCEPTANCE:
            return TransportDisposition.REJECTED
        if case.proof == EndpointProof.NONE:
            if self.mutation == "timeout_is_rejected":
                return TransportDisposition.REJECTED
            if (
                self.mutation == "local_return_is_delivered"
                and case.local_return_success
            ):
                return TransportDisposition.DELIVERED
            return TransportDisposition.AMBIGUOUS

        if case.acceptance_tick is None:
            return TransportDisposition.INVALID_EVIDENCE
        if (
            case.acceptance_tick < case.start_tick
            and self.mutation != "acceptance_order_unchecked"
        ):
            return TransportDisposition.INVALID_EVIDENCE
        checked_tick = case.acceptance_tick
        if self.mutation == "start_proves_acceptance":
            checked_tick = case.start_tick
        deadline_ok = checked_tick < deadline
        if self.mutation == "deadline_equality_accepted":
            deadline_ok = checked_tick <= deadline
        if not deadline_ok:
            return TransportDisposition.INVALID_EVIDENCE

        if case.gate_order == GateOrder.UNKNOWN:
            if self.mutation == "unknown_gate_order_delivered":
                return TransportDisposition.DELIVERED
            return TransportDisposition.AMBIGUOUS
        if case.gate_order == GateOrder.FENCE_BEFORE_ACCEPTANCE:
            if self.mutation == "fence_checked_only_at_start":
                return TransportDisposition.DELIVERED
            return TransportDisposition.INVALID_EVIDENCE
        if case.gate_order == GateOrder.ACCEPTANCE_BEFORE_FENCE and (
            case.fence_tick is None or case.acceptance_tick >= case.fence_tick
        ):
            return TransportDisposition.INVALID_EVIDENCE
        if case.gate_order == GateOrder.NO_FENCE and case.fence_tick is not None:
            return TransportDisposition.INVALID_EVIDENCE
        if (
            self.mutation == "late_resolution_forgets_acceptance"
            and case.gate_order == GateOrder.ACCEPTANCE_BEFORE_FENCE
            and case.fence_tick is not None
            and case.resolution_tick >= case.fence_tick
        ):
            return TransportDisposition.AMBIGUOUS
        return TransportDisposition.DELIVERED

    def intent_accepts(self, case: IntentCase) -> bool:
        """Evaluate receiver-issued Haldir intent freshness."""

        if (
            self.mutation != "intent_type_aliases_authorize"
            and not _intent_case_is_exact(case)
        ):
            return False
        if (
            not case.receiver_issued_grant
            and self.mutation != "intent_non_receiver_grant"
        ):
            return False
        base_tick = case.grant_issue_tick
        if self.mutation == "intent_sender_time_authorizes":
            base_tick = case.sender_tick
        elif self.mutation == "intent_receive_refreshes":
            base_tick = case.receive_tick
        deadline = min(case.grant_not_after, base_tick + case.ttl_ticks)
        return case.acceptance_tick < deadline


def _body_oracle(grant: BodyGrant, command: CommandCandidate) -> bool:
    """Independent correct body-freshness predicate."""

    if (
        not _body_grant_is_exact(grant)
        or not _command_candidate_is_exact(command)
        or not grant.body_issued
        or grant.body_clock != command.body_clock
        or grant.publisher != command.publisher
        or grant.stream_epoch != command.stream_epoch
        or command.sequence not in grant.slots
        or command.sequence in grant.retired_slots
        or command.mode not in grant.modes
        or command.ttl_ticks <= 0
        or grant.issue_tick >= grant.max_not_after
        or command.acceptance_tick < command.start_tick
    ):
        return False
    deadline = min(grant.max_not_after, grant.issue_tick + command.ttl_ticks)
    return command.start_tick < deadline and command.acceptance_tick < deadline


def _transport_oracle(case: TransportCase) -> TransportDisposition:
    """Independent correct endpoint-evidence resolution."""

    if not _transport_case_is_exact(case):
        return TransportDisposition.INVALID_EVIDENCE
    if case.proof == EndpointProof.NO_ACCEPTANCE:
        return TransportDisposition.REJECTED
    if case.proof == EndpointProof.NONE:
        return TransportDisposition.AMBIGUOUS
    if case.acceptance_tick is None or case.acceptance_tick >= case.original_deadline:
        return TransportDisposition.INVALID_EVIDENCE
    if case.acceptance_tick < case.start_tick:
        return TransportDisposition.INVALID_EVIDENCE
    if case.gate_order == GateOrder.UNKNOWN:
        return TransportDisposition.AMBIGUOUS
    if case.gate_order == GateOrder.FENCE_BEFORE_ACCEPTANCE:
        if case.fence_tick is None or case.acceptance_tick <= case.fence_tick:
            return TransportDisposition.INVALID_EVIDENCE
        return TransportDisposition.INVALID_EVIDENCE
    if case.gate_order == GateOrder.ACCEPTANCE_BEFORE_FENCE:
        if case.fence_tick is None or case.acceptance_tick >= case.fence_tick:
            return TransportDisposition.INVALID_EVIDENCE
    elif case.fence_tick is not None:
        return TransportDisposition.INVALID_EVIDENCE
    return TransportDisposition.DELIVERED


def _intent_oracle(case: IntentCase) -> bool:
    """Independent receiver-freshness predicate."""

    if not _intent_case_is_exact(case):
        return False
    deadline = min(case.grant_not_after, case.grant_issue_tick + case.ttl_ticks)
    return case.receiver_issued_grant and case.acceptance_tick < deadline


def _campaign_body_freshness(model: Model, audit: Audit) -> None:
    grant = BodyGrant(
        body_issued=True,
        body_clock="body-clock-a",
        issue_tick=100,
        max_not_after=113,
        publisher="haldir-commander-a",
        stream_epoch="epoch-a",
        slots=(7, 8),
        modes=frozenset(Mode),
    )
    modes = tuple(Mode)
    sender_ticks = (0, 107, 1_000_000)
    receive_ticks = (101, 107, 111)
    start_ticks = (102, 107, 108)
    acceptance_ticks = (107, 108, 109)
    delayed_mode_results: dict[Mode, bool] = {}
    for mode, sender, receive, start, acceptance in itertools.product(
        modes,
        sender_ticks,
        receive_ticks,
        start_ticks,
        acceptance_ticks,
    ):
        command = CommandCandidate(
            mode=mode,
            publisher=grant.publisher,
            stream_epoch=grant.stream_epoch,
            sequence=7,
            ttl_ticks=8,
            sender_tick=sender,
            receive_tick=receive,
            start_tick=start,
            acceptance_tick=acceptance,
            body_clock=grant.body_clock,
        )
        expected = _body_oracle(grant, command)
        actual = model.body_accepts(grant, command)
        audit.case()
        audit.require(actual == expected, "body_absolute_deadline")
        if not expected:
            audit.reject()
        if (sender, receive, start, acceptance) == (107, 111, 107, 109):
            delayed_mode_results[mode] = actual
    audit.witness(
        "absolute_deadline_ignores_delayed_receive_for_all_modes",
        set(delayed_mode_results) == set(Mode)
        and not any(delayed_mode_results.values()),
    )
    strict_grant = BodyGrant(**{**grant.__dict__, "max_not_after": 108})
    equality = CommandCandidate(
        mode=Mode.ACTIVE,
        publisher=grant.publisher,
        stream_epoch=grant.stream_epoch,
        sequence=7,
        ttl_ticks=20,
        sender_tick=108,
        receive_tick=107,
        start_tick=107,
        acceptance_tick=108,
        body_clock=grant.body_clock,
    )
    equality_rejected = not model.body_accepts(strict_grant, equality)
    audit.case()
    audit.require(equality_rejected, "strict_acceptance_deadline")
    audit.require(equality_rejected, "acceptance_not_start")
    audit.witness("acceptance_at_deadline_rejects", equality_rejected)
    audit.witness(
        "late_acceptance_after_early_start_rejects",
        equality_rejected,
    )
    if equality_rejected:
        audit.reject()
    prestart_acceptance = CommandCandidate(
        **{
            **equality.__dict__,
            "start_tick": 104,
            "acceptance_tick": 103,
        }
    )
    prestart_rejected = not model.body_accepts(strict_grant, prestart_acceptance)
    audit.case()
    audit.require(prestart_rejected, "acceptance_after_start")
    audit.witness(
        "acceptance_before_attempt_start_rejects",
        prestart_rejected,
    )
    if prestart_rejected:
        audit.reject()
    sender_hostile = CommandCandidate(
        **{
            **equality.__dict__,
            "sender_tick": 1_000_000,
            "acceptance_tick": 109,
        }
    )
    sender_rejected = not model.body_accepts(strict_grant, sender_hostile)
    audit.case()
    audit.require(sender_rejected, "body_absolute_deadline")
    audit.witness("sender_timestamp_is_non_authoritative", sender_rejected)
    if sender_rejected:
        audit.reject()

    retry = CommandCandidate(
        **{
            **equality.__dict__,
            "ttl_ticks": 8,
            "acceptance_tick": 112,
            "retry": True,
            "proposed_retry_deadline": 120,
        }
    )
    retry_actual = model.body_accepts(grant, retry)
    audit.case()
    audit.require(not retry_actual, "retry_preserves_deadline")
    audit.witness("retry_keeps_original_acceptance_deadline", not retry_actual)
    if not retry_actual:
        audit.reject()

    valid_acceptance = CommandCandidate(
        **{
            **equality.__dict__,
            "acceptance_tick": 107,
        }
    )
    invalid_grants = (
        (
            "wrong_body_grant_rejects",
            BodyGrant(**{**grant.__dict__, "body_issued": False}),
            valid_acceptance,
            "body_issued_grant",
        ),
        (
            "wrong_slot_rejects",
            grant,
            CommandCandidate(**{**valid_acceptance.__dict__, "sequence": 99}),
            "exact_grant_slot",
        ),
        (
            "retired_slot_rejects",
            BodyGrant(**{**grant.__dict__, "retired_slots": frozenset({7})}),
            valid_acceptance,
            "retired_slot_tombstone",
        ),
        (
            "wrong_mode_rejects",
            BodyGrant(**{**grant.__dict__, "modes": frozenset({Mode.HOLD})}),
            valid_acceptance,
            "grant_mode_bound",
        ),
        (
            "wrong_clock_rejects",
            grant,
            CommandCandidate(
                **{**valid_acceptance.__dict__, "body_clock": "body-clock-b"}
            ),
            "grant_clock_bound",
        ),
    )
    for witness, candidate_grant, candidate_command, invariant in invalid_grants:
        actual = model.body_accepts(candidate_grant, candidate_command)
        audit.case()
        audit.require(not actual, invariant)
        audit.witness(witness, not actual)
        if not actual:
            audit.reject()

    # The first definitive freshness cause remains stable after later fences.
    initial_cause = "EXPIRED"
    expiry_tombstone = {
        "slot": 7,
        "deadline": 108,
        "cause": initial_cause,
    }
    later_cause = initial_cause
    if model.mutation == "lazy_expiry_reclassified":
        expiry_tombstone = {}
        later_cause = "SUPERSEDED"
    audit.case()
    expiry_stable = later_cause == initial_cause and expiry_tombstone == {
        "slot": 7,
        "deadline": 108,
        "cause": "EXPIRED",
    }
    audit.require(expiry_stable, "expiry_outcome_stable")
    audit.witness(
        "expired_outcome_survives_later_fence",
        expiry_stable,
    )

    # A fail-safe reservation captures exact grant evidence before retiring it.
    expected_snapshot = {
        "grant_deadline": 108,
        "slot": 7,
        "mode": Mode.HOLD,
    }
    captured_snapshot = dict(expected_snapshot)
    live_grant_after_reservation = False
    boundary_result = "APPLIED_HOLD"
    if (
        model.mutation == "hold_rechecks_retired_grant"
        and not live_grant_after_reservation
    ):
        boundary_result = "FAILED_RECHECK"
    audit.case()
    audit.require(
        boundary_result == "APPLIED_HOLD" and captured_snapshot == expected_snapshot,
        "reservation_snapshot_stable",
    )
    audit.witness(
        "hold_uses_captured_reservation_after_grant_retirement",
        boundary_result == "APPLIED_HOLD",
    )


def _campaign_transport(model: Model, audit: Audit) -> None:
    cases = (
        (
            "pre_fence_acceptance_resolves_after_fence",
            TransportCase(
                start_tick=103,
                acceptance_tick=106,
                original_deadline=108,
                proof=EndpointProof.ACCEPTED,
                gate_order=GateOrder.ACCEPTANCE_BEFORE_FENCE,
                resolution_tick=112,
                fence_tick=107,
            ),
        ),
        (
            "fence_before_acceptance_blocks_delivery",
            TransportCase(
                start_tick=103,
                acceptance_tick=106,
                original_deadline=108,
                proof=EndpointProof.ACCEPTED,
                gate_order=GateOrder.FENCE_BEFORE_ACCEPTANCE,
                resolution_tick=107,
                fence_tick=104,
            ),
        ),
        (
            "missing_gate_order_is_ambiguous",
            TransportCase(
                start_tick=103,
                acceptance_tick=106,
                original_deadline=108,
                proof=EndpointProof.ACCEPTED,
                gate_order=GateOrder.UNKNOWN,
                resolution_tick=109,
                fence_tick=105,
            ),
        ),
        (
            "timeout_without_endpoint_proof_is_ambiguous",
            TransportCase(
                start_tick=103,
                acceptance_tick=None,
                original_deadline=108,
                proof=EndpointProof.NONE,
                gate_order=GateOrder.UNKNOWN,
                resolution_tick=109,
                fence_tick=105,
            ),
        ),
        (
            "definitive_no_acceptance_is_rejected",
            TransportCase(
                start_tick=103,
                acceptance_tick=None,
                original_deadline=108,
                proof=EndpointProof.NO_ACCEPTANCE,
                gate_order=GateOrder.FENCE_BEFORE_ACCEPTANCE,
                resolution_tick=109,
                fence_tick=104,
            ),
        ),
        (
            "local_success_without_endpoint_proof_is_ambiguous",
            TransportCase(
                start_tick=103,
                acceptance_tick=None,
                original_deadline=108,
                proof=EndpointProof.NONE,
                gate_order=GateOrder.NO_FENCE,
                resolution_tick=104,
                local_return_success=True,
            ),
        ),
        (
            "acceptance_at_deadline_is_invalid",
            TransportCase(
                start_tick=103,
                acceptance_tick=108,
                original_deadline=108,
                proof=EndpointProof.ACCEPTED,
                gate_order=GateOrder.NO_FENCE,
                resolution_tick=108,
            ),
        ),
        (
            "acceptance_before_attempt_start_is_invalid",
            TransportCase(
                start_tick=103,
                acceptance_tick=102,
                original_deadline=108,
                proof=EndpointProof.ACCEPTED,
                gate_order=GateOrder.NO_FENCE,
                resolution_tick=104,
            ),
        ),
        (
            "retry_does_not_refresh_acceptance",
            TransportCase(
                start_tick=107,
                acceptance_tick=112,
                original_deadline=108,
                proof=EndpointProof.ACCEPTED,
                gate_order=GateOrder.NO_FENCE,
                resolution_tick=112,
                retry=True,
                proposed_retry_deadline=120,
            ),
        ),
    )
    invariant_by_witness = {
        "pre_fence_acceptance_resolves_after_fence": "pre_fence_acceptance_stable",
        "fence_before_acceptance_blocks_delivery": "transport_fence_linearized",
        "missing_gate_order_is_ambiguous": "transport_gate_order_required",
        "timeout_without_endpoint_proof_is_ambiguous": (
            "transport_ambiguity_preserved"
        ),
        "definitive_no_acceptance_is_rejected": "transport_ambiguity_preserved",
        "local_success_without_endpoint_proof_is_ambiguous": (
            "transport_ambiguity_preserved"
        ),
        "acceptance_at_deadline_is_invalid": "strict_acceptance_deadline",
        "acceptance_before_attempt_start_is_invalid": "acceptance_after_start",
        "retry_does_not_refresh_acceptance": "retry_preserves_deadline",
    }
    for witness, case in cases:
        expected = _transport_oracle(case)
        actual = model.transport_disposition(case)
        audit.case()
        audit.require(actual == expected, invariant_by_witness[witness])
        if expected != TransportDisposition.DELIVERED:
            audit.reject()
        if witness in REQUIRED_WITNESSES:
            audit.witness(witness, actual == expected)


def _campaign_intent_freshness(model: Model, audit: Audit) -> None:
    cases = (
        IntentCase(True, 200, 213, 8, 207, 201, 207),
        IntentCase(True, 200, 213, 8, 1_000_000, 211, 209),
        IntentCase(False, 200, 213, 8, 207, 201, 207),
    )
    invariants = (
        "intent_receiver_freshness",
        "intent_receiver_freshness",
        "intent_receiver_issued_grant",
    )
    actual_results: list[bool] = []
    for case, invariant in zip(cases, invariants, strict=True):
        expected = _intent_oracle(case)
        actual = model.intent_accepts(case)
        actual_results.append(actual)
        audit.case()
        audit.require(actual == expected, invariant)
        if not expected:
            audit.reject()
    audit.witness(
        "intent_uses_receiver_issued_freshness",
        actual_results[0] and not actual_results[2],
    )
    audit.witness(
        "intent_delayed_receive_does_not_refresh",
        not actual_results[1],
    )


@dataclass(frozen=True)
class EffectCommand:
    """One bounded command/effect-slot input."""

    command_id: str
    position: int
    content_digest: str
    signature_digest: str
    mode: Mode


@dataclass
class EffectSlot:
    """Bounded durable allocation state for one exact publisher position."""

    canonical_content: str
    mode: Mode
    durable_attempts: int
    restrictive_operations: int
    command_id: str = ""
    position: int = -1
    first_conflict_digest: str | None = None
    conflict_saturated: bool = False
    estop_upgrade_used: bool = False


@dataclass
class BoundaryToken:
    """One durable fail-safe boundary reservation."""

    severity: Severity
    token_id: str = ""
    slot_key: object = None
    command_id: str = ""
    reservation_ordinal: int = -1
    reservation_transition: int = -1
    terminal_result: str | None = None
    completion_ordinal: int | None = None
    completion_transition: int | None = None

    @property
    def terminal(self) -> bool:
        return self.terminal_result is not None


def _effect_command_is_exact(value: object) -> bool:
    return (
        type(value) is EffectCommand
        and _exact_closed_identifier(value.command_id)
        and _exact_nonnegative_int(value.position)
        and _exact_closed_identifier(value.content_digest)
        and _exact_closed_identifier(value.signature_digest)
        and _exact_enum(value.mode, Mode)
    )


def _effect_slot_is_exact(value: object) -> bool:
    return (
        type(value) is EffectSlot
        and _exact_closed_identifier(value.canonical_content)
        and _exact_enum(value.mode, Mode)
        and _exact_int(value.durable_attempts)
        and value.durable_attempts >= 0
        and _exact_int(value.restrictive_operations)
        and value.restrictive_operations >= 0
        and _exact_closed_identifier(value.command_id)
        and _exact_nonnegative_int(value.position)
        and _exact_optional_closed_identifier(value.first_conflict_digest)
        and _exact_bool(value.conflict_saturated)
        and _exact_bool(value.estop_upgrade_used)
    )


def _boundary_token_is_exact(
    value: object,
    key_predicate: Any,
) -> bool:
    return (
        type(value) is BoundaryToken
        and _exact_enum(value.severity, Severity)
        and _exact_closed_identifier(value.token_id)
        and key_predicate(value.slot_key)
        and _exact_closed_identifier(value.command_id)
        and _exact_nonnegative_int(value.reservation_ordinal)
        and _exact_nonnegative_int(value.reservation_transition)
        and _exact_optional_closed_identifier(value.terminal_result)
        and (
            value.completion_ordinal is None
            or _exact_nonnegative_int(value.completion_ordinal)
        )
        and (
            value.completion_transition is None
            or _exact_nonnegative_int(value.completion_transition)
        )
        and (
            (value.terminal_result is None)
            == (value.completion_ordinal is None)
            == (value.completion_transition is None)
        )
    )


class EffectJournal:
    """Bounded slot allocator and severity-order sketch.

    This model counts restrictive operations selected for the physical DAG. It
    does not treat selection as a physical invocation. The separate unified
    boundary campaign challenges the complete commit order and one-use effect.
    """

    MAX_EFFECT_SLOTS = 2

    def __init__(self, mutation: str | None) -> None:
        self.mutation = _validate_mutation_selector(mutation)
        self.slots: dict[object, EffectSlot] = {}
        self.command_chains: set[object] = set()
        self.tokens: dict[str, BoundaryToken] = {}
        self.highest_pending = Severity.ACTIVE
        self.highest_accepted = Severity.ACTIVE
        self.completion_log: list[str] = []
        self._token_counter = 0
        self._transition_counter = 0

    @staticmethod
    def _key_is_exact(value: object) -> bool:
        return (
            _exact_nonnegative_int(value)
            or _exact_closed_identifier(value)
            or _exact_tuple_of(
                value,
                lambda member: (
                    _exact_nonnegative_int(member) or _exact_closed_identifier(member)
                ),
                nonempty=True,
            )
        )

    def _state_is_exact(self) -> bool:
        structurally_exact = (
            type(self.slots) is dict
            and all(
                self._key_is_exact(key) and _effect_slot_is_exact(slot)
                for key, slot in self.slots.items()
            )
            and type(self.command_chains) is set
            and all(self._key_is_exact(key) for key in self.command_chains)
            and type(self.tokens) is dict
            and all(
                _exact_closed_identifier(token_id)
                and _boundary_token_is_exact(token, self._key_is_exact)
                for token_id, token in self.tokens.items()
            )
            and _exact_enum(self.highest_pending, Severity)
            and _exact_enum(self.highest_accepted, Severity)
            and type(self.completion_log) is list
            and all(_exact_closed_identifier(item) for item in self.completion_log)
            and _exact_nonnegative_int(self._token_counter)
            and _exact_nonnegative_int(self._transition_counter)
        )
        if not structurally_exact:
            return False
        if self.mutation == "orphan_effect_token_authorized":
            return True

        expected_token_ids = {
            f"boundary-token-{ordinal}" for ordinal in range(self._token_counter)
        }
        if set(self.tokens) != expected_token_ids:
            return False
        if any(
            token.token_id != token_id
            or token.reservation_ordinal
            != int(token_id.removeprefix("boundary-token-"))
            for token_id, token in self.tokens.items()
        ):
            return False
        transition_events: list[tuple[int, str, BoundaryToken]] = []
        for token in self.tokens.values():
            transition_events.append((token.reservation_transition, "RESERVE", token))
            if token.completion_transition is not None:
                transition_events.append(
                    (token.completion_transition, "COMPLETE", token)
                )
        if len(transition_events) != self._transition_counter or sorted(
            event[0] for event in transition_events
        ) != list(range(self._transition_counter)):
            return False

        expected_chain_keys: set[object] = set()
        for slot_key, slot in self.slots.items():
            expected_slot_key: object = slot.position
            if self.mutation == "content_is_position_key":
                expected_slot_key = (slot.position, slot.canonical_content)
            if slot_key != expected_slot_key:
                return False
            chain_key: object = slot.command_id
            if self.mutation == "command_chain_keyed_by_position":
                chain_key = (slot.command_id, slot.position)
            expected_chain_keys.add(chain_key)

            slot_tokens = sorted(
                (token for token in self.tokens.values() if token.slot_key == slot_key),
                key=lambda token: token.reservation_ordinal,
            )
            if (
                any(token.command_id != slot.command_id for token in slot_tokens)
                or slot.restrictive_operations != len(slot_tokens)
                or slot.durable_attempts < 1
                or (slot.first_conflict_digest is None and slot.conflict_saturated)
            ):
                return False
            severity_sequence = tuple(token.severity for token in slot_tokens)
            valid_slot_state = (
                (
                    slot.mode == Mode.ACTIVE
                    and severity_sequence == ()
                    and not slot.estop_upgrade_used
                )
                or (
                    slot.mode == Mode.HOLD
                    and severity_sequence == (Severity.HOLD,)
                    and not slot.estop_upgrade_used
                )
                or (
                    slot.mode == Mode.ESTOP
                    and severity_sequence == (Severity.ESTOP,)
                    and not slot.estop_upgrade_used
                )
                or (
                    slot.mode == Mode.ESTOP
                    and severity_sequence == (Severity.HOLD, Severity.ESTOP)
                    and slot.estop_upgrade_used
                )
            )
            if not valid_slot_state:
                return False
        if self.command_chains != expected_chain_keys:
            return False
        if any(token.slot_key not in self.slots for token in self.tokens.values()):
            return False

        pending_tokens: dict[str, BoundaryToken] = {}
        replayed_highest_accepted = Severity.ACTIVE
        completed: list[BoundaryToken] = []
        for _transition, event_kind, token in sorted(transition_events):
            if event_kind == "RESERVE":
                if (
                    token.token_id in pending_tokens
                    or token.terminal
                    and (
                        token.completion_transition is not None
                        and token.completion_transition < token.reservation_transition
                    )
                ):
                    return False
                pending_tokens[token.token_id] = token
                continue
            if pending_tokens.get(token.token_id) is not token:
                return False
            pending_other = max(
                (
                    other.severity
                    for token_id, other in pending_tokens.items()
                    if token_id != token.token_id
                ),
                default=Severity.ACTIVE,
            )
            blocker = max(pending_other, replayed_highest_accepted)
            expected_result = (
                f"DEFINITIVE_NO_EFFECT_SUPERSEDED_{token.severity.name}"
                if token.severity < blocker
                else f"APPLIED_{token.severity.name}"
            )
            if token.terminal_result != expected_result:
                return False
            if expected_result.startswith("APPLIED_"):
                replayed_highest_accepted = max(
                    replayed_highest_accepted,
                    token.severity,
                )
            pending_tokens.pop(token.token_id)
            completed.append(token)
        if [token.completion_ordinal for token in completed] != list(
            range(len(completed))
        ) or self.completion_log != [token.terminal_result for token in completed]:
            return False
        expected_pending = max(
            (token.severity for token in pending_tokens.values()),
            default=Severity.ACTIVE,
        )
        return (
            self.highest_pending == expected_pending
            and self.highest_accepted == replayed_highest_accepted
        )

    @staticmethod
    def _severity(mode: Mode) -> Severity:
        return Severity[mode.name]

    def _slot_key(self, command: EffectCommand) -> object:
        if self.mutation == "content_is_position_key":
            return (command.position, command.content_digest)
        return command.position

    def _chain_key(self, command: EffectCommand) -> object:
        if self.mutation == "command_chain_keyed_by_position":
            return (command.command_id, command.position)
        return command.command_id

    def _reserve(
        self,
        severity: Severity,
        *,
        slot_key: object,
        command_id: str,
    ) -> str:
        token_id = f"boundary-token-{self._token_counter}"
        reservation_ordinal = self._token_counter
        self._token_counter += 1
        reservation_transition = self._transition_counter
        self._transition_counter += 1
        self.tokens[token_id] = BoundaryToken(
            severity=severity,
            token_id=token_id,
            slot_key=slot_key,
            command_id=command_id,
            reservation_ordinal=reservation_ordinal,
            reservation_transition=reservation_transition,
        )
        self.highest_pending = max(self.highest_pending, severity)
        return token_id

    def submit(self, command: EffectCommand) -> tuple[str, str | None]:
        """Install, replay, conflict, or monotonically upgrade one slot."""

        if not self._state_is_exact():
            return "INVALID_STATE", None
        if (
            self.mutation != "effect_command_subclass_authorizes"
            and not _effect_command_is_exact(command)
        ):
            return "INVALID_COMMAND", None
        key = self._slot_key(command)
        chain_key = self._chain_key(command)
        existing = self.slots.get(key)
        if (
            existing is None
            and len(self.slots) >= self.MAX_EFFECT_SLOTS
            and self.mutation != "effect_slot_capacity_unbounded"
        ):
            return "CAPACITY_EXHAUSTED", None
        self.command_chains.add(chain_key)
        mode = command.mode
        if self.mutation == "effect_command_subclass_authorizes" and type(mode) is str:
            try:
                mode = Mode(mode)
            except ValueError:
                return "INVALID_COMMAND", None
        severity = self._severity(mode)
        if existing is None:
            operation_count = 1 if severity > Severity.ACTIVE else 0
            self.slots[key] = EffectSlot(
                canonical_content=command.content_digest,
                mode=command.mode,
                durable_attempts=1,
                restrictive_operations=operation_count,
                command_id=command.command_id,
                position=command.position,
            )
            token = (
                self._reserve(
                    severity,
                    slot_key=key,
                    command_id=command.command_id,
                )
                if operation_count
                else None
            )
            return "NEW", token

        if existing.canonical_content == command.content_digest:
            if (
                self.mutation == "exact_replay_allocates_attempt"
                and command.signature_digest == "signature-a"
            ):
                existing.durable_attempts += 1
            if (
                self.mutation == "exact_replay_reinvokes_effect"
                and severity > Severity.ACTIVE
                and command.signature_digest == "signature-a"
            ):
                existing.restrictive_operations += 1
                return "REPLAY_REINVOKED", self._reserve(
                    severity,
                    slot_key=key,
                    command_id=command.command_id,
                )
            if (
                self.mutation == "signature_variant_allocates"
                and command.signature_digest != "signature-a"
            ):
                existing.durable_attempts += 1
            return "EXACT_REPLAY", None

        conflict_digest = hashlib.sha256(
            command.content_digest.encode("utf-8")
        ).hexdigest()
        valid_estop_upgrade = (
            severity == Severity.ESTOP
            and self._severity(existing.mode) == Severity.HOLD
            and not existing.estop_upgrade_used
        )
        repeated_estop_upgrade = (
            self.mutation == "repeat_estop_upgrade_reinvokes"
            and severity == Severity.ESTOP
            and existing.estop_upgrade_used
        )
        if valid_estop_upgrade or repeated_estop_upgrade:
            existing.durable_attempts += 1
            existing.restrictive_operations += 1
            existing.mode = Mode.ESTOP
            existing.estop_upgrade_used = True
            if existing.first_conflict_digest is None:
                existing.first_conflict_digest = conflict_digest
            else:
                existing.conflict_saturated = True
            return "HOLD_TO_ESTOP_UPGRADE", self._reserve(
                Severity.ESTOP,
                slot_key=key,
                command_id=command.command_id,
            )

        if existing.first_conflict_digest is None:
            existing.first_conflict_digest = conflict_digest
            existing.durable_attempts += 1
            return "FIRST_CONFLICT", None
        existing.conflict_saturated = True
        if self.mutation == "conflicts_are_unbounded":
            existing.durable_attempts += 1
        return "CONFLICT_SATURATED", None

    def complete(self, token_id: str) -> str:
        """Complete one reservation under global severity ordering."""

        if not self._state_is_exact() or type(token_id) is not str:
            return "INVALID_TOKEN"
        token = self.tokens.get(token_id)
        if token is None or not _boundary_token_is_exact(token, self._key_is_exact):
            return "INVALID_TOKEN"
        if not all(
            _boundary_token_is_exact(other, self._key_is_exact)
            for other in self.tokens.values()
        ) or not all(_effect_slot_is_exact(slot) for slot in self.slots.values()):
            return "INVALID_STATE"
        if token.terminal:
            return "ALREADY_TERMINAL"

        pending_other = max(
            (
                other.severity
                for key, other in self.tokens.items()
                if key != token_id and not other.terminal
            ),
            default=Severity.ACTIVE,
        )
        blocker = max(pending_other, self.highest_accepted)
        if self.mutation == "hold_clears_after_estop_pending":
            blocker = self.highest_accepted
        elif self.mutation == "hold_clears_after_estop_accepted":
            blocker = pending_other

        if token.severity < blocker:
            result = f"DEFINITIVE_NO_EFFECT_SUPERSEDED_{token.severity.name}"
        else:
            self.highest_accepted = max(self.highest_accepted, token.severity)
            result = f"APPLIED_{token.severity.name}"
        token.terminal_result = result
        token.completion_ordinal = len(self.completion_log)
        token.completion_transition = self._transition_counter
        self._transition_counter += 1
        self.completion_log.append(result)
        self.highest_pending = max(
            (other.severity for other in self.tokens.values() if not other.terminal),
            default=Severity.ACTIVE,
        )
        return result

    def total_attempts(self) -> int:
        if not self._state_is_exact():
            return 0
        return sum(slot.durable_attempts for slot in self.slots.values())

    def total_restrictive_operations(self) -> int:
        if not self._state_is_exact():
            return 0
        return sum(slot.restrictive_operations for slot in self.slots.values())


def _command(
    command_id: str,
    position: int,
    content: str,
    mode: Mode,
    *,
    signature: str = "signature-a",
) -> EffectCommand:
    return EffectCommand(command_id, position, content, signature, mode)


def _campaign_effect_journal(model: Model, audit: Audit) -> None:
    journal = EffectJournal(model.mutation)
    first = _command("command-1", 7, "content-a", Mode.HOLD)
    _result, _hold_token = journal.submit(first)
    baseline_attempts = journal.total_attempts()
    baseline_operations = journal.total_restrictive_operations()
    for _index in range(5):
        journal.submit(first)
        audit.case()
    audit.require(
        journal.total_attempts() == baseline_attempts,
        "exact_replay_no_attempt",
    )
    audit.require(
        journal.total_restrictive_operations() == baseline_operations,
        "exact_replay_no_effect",
    )
    audit.witness(
        "exact_replay_allocates_nothing",
        journal.total_attempts() == baseline_attempts
        and journal.total_restrictive_operations() == baseline_operations,
    )

    # Re-signing exact Active content does not change its command/effect identity.
    active_journal = EffectJournal(model.mutation)
    active = _command("active-1", 20, "active-content", Mode.ACTIVE)
    active_journal.submit(active)
    for signature in ("signature-b", "signature-c", "signature-d"):
        active_journal.submit(
            _command(
                "active-1",
                20,
                "active-content",
                Mode.ACTIVE,
                signature=signature,
            )
        )
        audit.case()
    audit.require(
        active_journal.total_attempts() == 1
        and active_journal.total_restrictive_operations() == 0,
        "signature_variant_no_state",
    )
    audit.witness(
        "active_signature_variants_allocate_nothing",
        active_journal.total_attempts() == 1
        and active_journal.total_restrictive_operations() == 0,
    )

    conflict_journal = EffectJournal(model.mutation)
    conflict_journal.submit(first)
    for index in range(12):
        conflict_journal.submit(
            _command("command-1", 7, f"hold-conflict-{index}", Mode.HOLD)
        )
        audit.case()
    slot = next(iter(conflict_journal.slots.values()))
    bounded_before_upgrade = (
        len(conflict_journal.slots) == 1
        and slot.durable_attempts <= 2
        and slot.first_conflict_digest is not None
        and slot.conflict_saturated
        and slot.restrictive_operations == 1
    )
    audit.require(bounded_before_upgrade, "bounded_position_conflicts")
    audit.require(len(conflict_journal.slots) == 1, "position_key_stable")
    audit.witness("same_position_conflicts_saturate", bounded_before_upgrade)

    conflict_journal.submit(_command("command-1", 7, "estop-upgrade-1", Mode.ESTOP))
    operations_after_upgrade = conflict_journal.total_restrictive_operations()
    for index in range(8):
        conflict_journal.submit(
            _command("command-1", 7, f"estop-upgrade-{index + 2}", Mode.ESTOP)
        )
        audit.case()
    audit.require(
        conflict_journal.total_restrictive_operations()
        == operations_after_upgrade
        == 2,
        "single_estop_upgrade",
    )
    audit.witness(
        "hold_to_estop_upgrades_once",
        conflict_journal.total_restrictive_operations() == 2,
    )

    conflict_journal.submit(_command("command-1", 8, "other-position", Mode.ESTOP))
    audit.case()
    audit.require(
        len(conflict_journal.command_chains) == 1,
        "single_command_chain",
    )
    audit.witness(
        "same_command_other_position_has_one_chain",
        len(conflict_journal.command_chains) == 1,
    )
    bounded_snapshot = (
        copy.deepcopy(conflict_journal.slots),
        copy.deepcopy(conflict_journal.command_chains),
        conflict_journal.total_attempts(),
        conflict_journal.total_restrictive_operations(),
    )
    capacity_result, capacity_token = conflict_journal.submit(
        _command("command-2", 9, "third-position", Mode.HOLD)
    )
    audit.case()
    capacity_closed = (
        capacity_result == "CAPACITY_EXHAUSTED"
        and capacity_token is None
        and (
            conflict_journal.slots,
            conflict_journal.command_chains,
            conflict_journal.total_attempts(),
            conflict_journal.total_restrictive_operations(),
        )
        == bounded_snapshot
    )
    audit.require(capacity_closed, "bounded_effect_slots")
    audit.witness(
        "third_position_hits_capacity_without_eviction",
        capacity_closed,
    )
    if capacity_closed:
        audit.reject()

    pending = EffectJournal(model.mutation)
    _hold_result, pending_hold = pending.submit(
        _command("hold-pending", 1, "hold", Mode.HOLD)
    )
    _estop_result, pending_estop = pending.submit(
        _command("estop-pending", 2, "estop", Mode.ESTOP)
    )
    if pending_hold is None or pending_estop is None:
        raise ProbeError("fail-safe reservation was not allocated")
    delayed_hold_result = pending.complete(pending_hold)
    audit.case()
    audit.require(
        delayed_hold_result == "DEFINITIVE_NO_EFFECT_SUPERSEDED_HOLD",
        "pending_estop_dominates_hold",
    )
    audit.witness(
        "pending_estop_supersedes_delayed_hold",
        delayed_hold_result == "DEFINITIVE_NO_EFFECT_SUPERSEDED_HOLD",
    )

    accepted = EffectJournal(model.mutation)
    _hold_result, accepted_hold = accepted.submit(
        _command("hold-accepted", 1, "hold", Mode.HOLD)
    )
    _estop_result, accepted_estop = accepted.submit(
        _command("estop-accepted", 2, "estop", Mode.ESTOP)
    )
    if accepted_hold is None or accepted_estop is None:
        raise ProbeError("fail-safe reservation was not allocated")
    estop_result = accepted.complete(accepted_estop)
    delayed_after_accept = accepted.complete(accepted_hold)
    audit.case()
    audit.require(
        estop_result == "APPLIED_ESTOP"
        and delayed_after_accept == "DEFINITIVE_NO_EFFECT_SUPERSEDED_HOLD",
        "accepted_estop_dominates_hold",
    )
    audit.witness(
        "accepted_estop_supersedes_delayed_hold",
        delayed_after_accept == "DEFINITIVE_NO_EFFECT_SUPERSEDED_HOLD",
    )

    # The pre-admission fail-safe clear is not a post-admission application
    # event. A later generic restrictive-effect association needs a distinct
    # acceptance that invokes no second clear. This probe does not select its
    # eventual normative terminal enum.
    effect_acceptance_sequence = 10
    admission_sequence = 11
    boundary_invocations = 1
    if model.mutation == "pre_admission_effect_reused_as_applied":
        restrictive_association_sequence = effect_acceptance_sequence
        restrictive_associations = 0
    else:
        restrictive_association_sequence = 12
        restrictive_associations = 1
    valid_restrictive_association = (
        effect_acceptance_sequence
        < admission_sequence
        < restrictive_association_sequence
        and restrictive_associations == 1
        and boundary_invocations == 1
    )
    audit.case()
    audit.require(
        valid_restrictive_association,
        "pre_admission_effect_not_application",
    )
    audit.witness(
        "pre_admission_effect_has_distinct_restrictive_association",
        valid_restrictive_association,
    )


class RestrictivePath(StrEnum):
    """Closed entry paths into the one synthetic physical boundary."""

    INITIAL_HOLD = "INITIAL_HOLD"
    INITIAL_ESTOP = "INITIAL_ESTOP"
    UPGRADE_ESTOP = "UPGRADE_ESTOP"
    DRAIN_ESTOP = "DRAIN_ESTOP"
    CAPACITY_RETIREMENT_RESTRICTIVE = "CAPACITY_RETIREMENT_RESTRICTIVE"


class RestrictiveCrashCut(StrEnum):
    """Durable cuts in the restrictive-action commit DAG."""

    AFTER_ARBITER_PENDING = "AFTER_ARBITER_PENDING"
    AFTER_BODY_MIRROR = "AFTER_BODY_MIRROR"
    AFTER_BOUNDARY_INVOCATION = "AFTER_BOUNDARY_INVOCATION"
    AFTER_ARBITER_RESOLUTION = "AFTER_ARBITER_RESOLUTION"


@dataclass(frozen=True)
class RestrictiveToken:
    """One path-bound, pre-reserved, one-use restrictive-chain token."""

    token_id: str
    path: RestrictivePath
    pre_reserved: bool = True


@dataclass
class UnifiedRestrictiveOperation:
    """One operation spanning arbiter, body mirror, boundary, and completion."""

    operation_id: str
    path: RestrictivePath
    severity: Severity
    token: RestrictiveToken
    fence_epoch: int
    predecessor_token_id: str | None = None
    events: list[str] = field(default_factory=list)
    body_mirror_token_id: str | None = None
    body_mirror_owner: str | None = None
    boundary_invocations: int = 0
    physical_effects: int = 0
    boundary_result: str | None = None
    arbiter_resolved: bool = False
    body_result_consumer: str | None = None
    body_completions: int = 0


def _restrictive_token_is_exact(value: object) -> bool:
    return (
        type(value) is RestrictiveToken
        and _exact_closed_identifier(value.token_id)
        and _exact_enum(value.path, RestrictivePath)
        and _exact_bool(value.pre_reserved)
    )


def _restrictive_operation_is_exact(value: object) -> bool:
    return (
        type(value) is UnifiedRestrictiveOperation
        and _exact_closed_identifier(value.operation_id)
        and _exact_enum(value.path, RestrictivePath)
        and _exact_enum(value.severity, Severity)
        and _restrictive_token_is_exact(value.token)
        and _exact_int(value.fence_epoch)
        and value.fence_epoch > 0
        and _exact_optional_closed_identifier(value.predecessor_token_id)
        and type(value.events) is list
        and all(_exact_nonempty_str(event) for event in value.events)
        and _exact_optional_closed_identifier(value.body_mirror_token_id)
        and _exact_optional_closed_identifier(value.body_mirror_owner)
        and _exact_int(value.boundary_invocations)
        and value.boundary_invocations >= 0
        and _exact_int(value.physical_effects)
        and value.physical_effects >= 0
        and _exact_optional_closed_identifier(value.boundary_result)
        and _exact_bool(value.arbiter_resolved)
        and _exact_optional_closed_identifier(value.body_result_consumer)
        and _exact_int(value.body_completions)
        and value.body_completions >= 0
    )


class UnifiedPhysicalBoundary:
    """Executable five-commit model for every restrictive physical action."""

    EXPECTED_EVENTS = (
        "ARBITER_PENDING",
        "BODY_OPERATION_MIRROR",
        "PHYSICAL_BOUNDARY_INVOCATION",
        "ARBITER_RESOLVE",
        "BODY_COMPLETE",
    )
    BODY_MIRROR_OWNERS = {
        RestrictivePath.INITIAL_HOLD: "RESERVE_BODY_FAIL_SAFE_SIDE_EFFECT",
        RestrictivePath.INITIAL_ESTOP: "RESERVE_BODY_FAIL_SAFE_SIDE_EFFECT",
        RestrictivePath.UPGRADE_ESTOP: "UPGRADE_BODY_FAIL_SAFE_TO_ESTOP",
        RestrictivePath.DRAIN_ESTOP: "ESTOP_ONLY_DRAIN_ADMISSION",
        RestrictivePath.CAPACITY_RETIREMENT_RESTRICTIVE: (
            "EXHAUST_BODY_REMOTE_COMMAND_CAPACITY_TO_RETIREMENT_DRAIN"
        ),
    }
    BODY_RESULT_CONSUMERS = {
        RestrictivePath.INITIAL_HOLD: "COMPLETE_RESERVED_FAIL_SAFE_COMMAND",
        RestrictivePath.INITIAL_ESTOP: "COMPLETE_RESERVED_FAIL_SAFE_COMMAND",
        RestrictivePath.UPGRADE_ESTOP: "COMPLETE_RESERVED_FAIL_SAFE_COMMAND",
        RestrictivePath.DRAIN_ESTOP: "COMPLETE_RESERVED_FAIL_SAFE_COMMAND",
        RestrictivePath.CAPACITY_RETIREMENT_RESTRICTIVE: (
            "RECONCILE_BODY_ACTUATION_ARBITER_TRANSITION/RESTRICTIVE_RESULT_MIRROR"
        ),
    }
    SEMANTIC_STATE_BYPASS_MUTATIONS = frozenset(
        {
            "restrictive_missing_arbiter_pending",
            "restrictive_invokes_before_body_mirror",
            "restrictive_resolves_before_invocation",
            "restrictive_completes_before_arbiter_resolution",
            "restrictive_mirror_wrong_token",
            "restrictive_replay_reinvokes",
            "restrictive_replay_recompletes",
            "restrictive_reuses_fence_epoch",
            "restrictive_reuses_consumed_token",
            "restrictive_recovery_mints_token",
            "restrictive_recovery_reinvokes",
            "upgrade_reuses_hold_token",
            "upgrade_without_completed_hold",
            "upgrade_bypasses_arbiter",
            "drain_estop_bypasses_arbiter",
            "capacity_fallback_bypasses_arbiter",
            "capacity_fallback_uses_general_token",
            "capacity_retirement_uses_fail_safe_reservation_mirror",
            "capacity_retirement_uses_fail_safe_result_mirror",
            "forged_restrictive_state_authorized",
        }
    )

    def __init__(self, mutation: str | None) -> None:
        self.mutation = _validate_mutation_selector(mutation)
        self.operations: dict[str, UnifiedRestrictiveOperation] = {}
        self.pending: dict[str, UnifiedRestrictiveOperation] = {}
        self._operation_counter = 0
        self._fence_counter = 0
        self._tokens = {
            path: RestrictiveToken(
                token_id=f"pre-reserved-{path.value.lower()}",
                path=path,
            )
            for path in RestrictivePath
        }
        self._used_token_ids: set[str] = set()
        self.highest_resolved = Severity.ACTIVE

    def _owns_operation(self, operation: object) -> bool:
        return (
            _restrictive_operation_is_exact(operation)
            and self.operations.get(operation.operation_id) is operation
        )

    def _state_is_exact(self) -> bool:
        structurally_exact = (
            type(self.operations) is dict
            and all(
                _exact_closed_identifier(operation_id)
                and _restrictive_operation_is_exact(operation)
                and operation.operation_id == operation_id
                for operation_id, operation in self.operations.items()
            )
            and type(self.pending) is dict
            and all(
                _exact_closed_identifier(operation_id)
                and self.operations.get(operation_id) is operation
                for operation_id, operation in self.pending.items()
            )
            and type(self._tokens) is dict
            and all(
                _exact_enum(path, RestrictivePath)
                and _restrictive_token_is_exact(token)
                and token.path == path
                for path, token in self._tokens.items()
            )
            and set(self._tokens) == set(RestrictivePath)
            and type(self._used_token_ids) is set
            and all(
                _exact_closed_identifier(token_id) for token_id in self._used_token_ids
            )
            and _exact_nonnegative_int(self._operation_counter)
            and _exact_nonnegative_int(self._fence_counter)
            and _exact_enum(self.highest_resolved, Severity)
        )
        if not structurally_exact:
            return False
        if self.mutation in self.SEMANTIC_STATE_BYPASS_MUTATIONS:
            return True
        if any(
            token.token_id != f"pre-reserved-{path.value.lower()}"
            or not token.pre_reserved
            for path, token in self._tokens.items()
        ):
            return False
        return self._semantic_state_is_closed()

    def _operation_prefix_length(
        self,
        operation: UnifiedRestrictiveOperation,
    ) -> int | None:
        events = tuple(operation.events)
        for prefix_length in range(1, len(self.EXPECTED_EVENTS) + 1):
            if events == self.EXPECTED_EVENTS[:prefix_length]:
                return prefix_length
        return None

    def _operation_semantics_are_closed(
        self,
        operation: UnifiedRestrictiveOperation,
    ) -> bool:
        prefix_length = self._operation_prefix_length(operation)
        if (
            prefix_length is None
            or operation.severity != self._severity(operation.path)
            or operation.token.path != operation.path
            or operation.token is not self._tokens[operation.path]
        ):
            return False

        if operation.path == RestrictivePath.UPGRADE_ESTOP:
            predecessors = [
                candidate
                for candidate in self.operations.values()
                if candidate.token.token_id == operation.predecessor_token_id
            ]
            if (
                len(predecessors) != 1
                or predecessors[0].path != RestrictivePath.INITIAL_HOLD
                or self._operation_prefix_length(predecessors[0])
                != len(self.EXPECTED_EVENTS)
                or predecessors[0].boundary_result != "APPLIED_HOLD"
                or predecessors[0].fence_epoch >= operation.fence_epoch
            ):
                return False
        elif operation.predecessor_token_id is not None:
            return False

        has_mirror = prefix_length >= 2
        has_invocation = prefix_length >= 3
        has_resolution = prefix_length >= 4
        has_completion = prefix_length >= 5
        if has_mirror:
            if (
                operation.body_mirror_token_id != operation.token.token_id
                or operation.body_mirror_owner
                != self.BODY_MIRROR_OWNERS[operation.path]
            ):
                return False
        elif (
            operation.body_mirror_token_id is not None
            or operation.body_mirror_owner is not None
        ):
            return False

        allowed_result = (
            f"APPLIED_{operation.severity.name}",
            f"DEFINITIVE_NO_EFFECT_SUPERSEDED_{operation.severity.name}",
        )
        if has_invocation:
            if (
                operation.boundary_invocations != 1
                or operation.boundary_result not in allowed_result
                or operation.physical_effects
                != int(operation.boundary_result.startswith("APPLIED_"))
            ):
                return False
        elif (
            operation.boundary_invocations != 0
            or operation.physical_effects != 0
            or operation.boundary_result is not None
        ):
            return False

        if operation.arbiter_resolved is not has_resolution:
            return False
        if has_completion:
            if (
                operation.body_result_consumer
                != self.BODY_RESULT_CONSUMERS[operation.path]
                or operation.body_completions != 1
            ):
                return False
        elif (
            operation.body_result_consumer is not None
            or operation.body_completions != 0
        ):
            return False
        return True

    def _semantic_state_is_closed(self) -> bool:
        ordered_operations = list(self.operations.values())
        if (
            self._operation_counter != len(ordered_operations)
            or self._fence_counter != len(ordered_operations)
            or [operation.operation_id for operation in ordered_operations]
            != [
                f"restrictive-operation-{ordinal}"
                for ordinal in range(1, len(ordered_operations) + 1)
            ]
            or [operation.fence_epoch for operation in ordered_operations]
            != list(range(1, len(ordered_operations) + 1))
            or not all(
                self._operation_semantics_are_closed(operation)
                for operation in ordered_operations
            )
        ):
            return False
        expected_used_tokens = {
            operation.token.token_id for operation in ordered_operations
        }
        if self._used_token_ids != expected_used_tokens:
            return False
        expected_pending = {
            operation.operation_id: operation
            for operation in ordered_operations
            if self._operation_prefix_length(operation) < len(self.EXPECTED_EVENTS)
        }
        if self.pending != expected_pending or any(
            self.pending[operation_id] is not operation
            for operation_id, operation in expected_pending.items()
        ):
            return False
        expected_highest_resolved = max(
            (
                operation.severity
                for operation in ordered_operations
                if operation.arbiter_resolved
                and operation.boundary_result == f"APPLIED_{operation.severity.name}"
            ),
            default=Severity.ACTIVE,
        )
        return self.highest_resolved == expected_highest_resolved

    @staticmethod
    def _severity(path: RestrictivePath) -> Severity:
        if path in {
            RestrictivePath.INITIAL_HOLD,
            RestrictivePath.CAPACITY_RETIREMENT_RESTRICTIVE,
        }:
            return Severity.HOLD
        return Severity.ESTOP

    def _bypasses_pending(self, path: RestrictivePath) -> bool:
        return (
            self.mutation == "restrictive_missing_arbiter_pending"
            or (
                self.mutation == "upgrade_bypasses_arbiter"
                and path == RestrictivePath.UPGRADE_ESTOP
            )
            or (
                self.mutation == "drain_estop_bypasses_arbiter"
                and path == RestrictivePath.DRAIN_ESTOP
            )
            or (
                self.mutation == "capacity_fallback_bypasses_arbiter"
                and path == RestrictivePath.CAPACITY_RETIREMENT_RESTRICTIVE
            )
        )

    def start(
        self,
        path: RestrictivePath,
        *,
        predecessor: UnifiedRestrictiveOperation | None = None,
    ) -> UnifiedRestrictiveOperation:
        """Install the arbiter operation, token, and fresh epoch first."""

        if not self._state_is_exact():
            raise ProbeError("restrictive boundary state shape is not exact")
        if self.mutation != "restrictive_path_alias_authorizes" and not _exact_enum(
            path, RestrictivePath
        ):
            raise ProbeError("restrictive path is not an exact closed value")
        if predecessor is not None and path != RestrictivePath.UPGRADE_ESTOP:
            raise ProbeError(
                "restrictive predecessor is valid only for an ESTOP upgrade"
            )
        if predecessor is not None and not self._owns_operation(predecessor):
            if self.mutation != "foreign_restrictive_operation_authorized":
                raise ProbeError("restrictive predecessor is not retained here")
        valid_upgrade_predecessor = (
            predecessor is not None
            and (
                self._owns_operation(predecessor)
                or self.mutation == "foreign_restrictive_operation_authorized"
            )
            and predecessor.path == RestrictivePath.INITIAL_HOLD
            and predecessor.arbiter_resolved
            and predecessor.body_completions == 1
            and predecessor.boundary_result == "APPLIED_HOLD"
        )
        if (
            path == RestrictivePath.UPGRADE_ESTOP
            and not valid_upgrade_predecessor
            and self.mutation != "upgrade_without_completed_hold"
        ):
            raise ProbeError("ESTOP upgrade lacks one completed HOLD predecessor")

        token = self._tokens[path]
        if (
            self.mutation == "upgrade_reuses_hold_token"
            and path == RestrictivePath.UPGRADE_ESTOP
            and predecessor is not None
        ):
            token = predecessor.token
        elif (
            self.mutation == "capacity_fallback_uses_general_token"
            and path == RestrictivePath.CAPACITY_RETIREMENT_RESTRICTIVE
        ):
            token = RestrictiveToken(
                "general-capacity-token",
                RestrictivePath.INITIAL_ESTOP,
                pre_reserved=False,
            )
        if token.token_id in self._used_token_ids and self.mutation not in {
            "restrictive_reuses_consumed_token",
            "upgrade_reuses_hold_token",
        }:
            raise ProbeError("restrictive-chain token was already consumed")

        self._operation_counter += 1
        self._fence_counter += 1
        fence_epoch = self._fence_counter
        if self.mutation == "restrictive_reuses_fence_epoch":
            fence_epoch = 1
        operation = UnifiedRestrictiveOperation(
            operation_id=f"restrictive-operation-{self._operation_counter}",
            path=path,
            severity=self._severity(path),
            token=token,
            fence_epoch=fence_epoch,
            predecessor_token_id=(
                predecessor.token.token_id if predecessor is not None else None
            ),
        )
        self.operations[operation.operation_id] = operation
        self._used_token_ids.add(token.token_id)
        if not self._bypasses_pending(path):
            operation.events.append("ARBITER_PENDING")
            self.pending[operation.operation_id] = operation
        return operation

    def mirror(self, operation: UnifiedRestrictiveOperation) -> bool:
        """Install the cause-owned body mirror for the exact pending token."""

        if not self._state_is_exact():
            return False
        if not self._owns_operation(operation):
            if self.mutation != "foreign_restrictive_operation_authorized":
                return False
            if not _restrictive_operation_is_exact(operation):
                return False
        if (
            self.mutation not in self.SEMANTIC_STATE_BYPASS_MUTATIONS
            and self._operation_prefix_length(operation) != 1
        ):
            return False
        pending_matches = self.pending.get(operation.operation_id) is operation
        if self.mutation == "foreign_restrictive_operation_authorized":
            pending_matches = operation.operation_id in self.pending
        if not pending_matches and not self._bypasses_pending(operation.path):
            return False
        mirror_token = operation.token.token_id
        if self.mutation == "restrictive_mirror_wrong_token":
            mirror_token = f"{mirror_token}-wrong"
        operation.body_mirror_token_id = mirror_token
        mirror_owner = self.BODY_MIRROR_OWNERS[operation.path]
        if (
            self.mutation == "capacity_retirement_uses_fail_safe_reservation_mirror"
            and operation.path == RestrictivePath.CAPACITY_RETIREMENT_RESTRICTIVE
        ):
            mirror_owner = "RESERVE_BODY_FAIL_SAFE_SIDE_EFFECT"
        operation.body_mirror_owner = mirror_owner
        operation.events.append("BODY_OPERATION_MIRROR")
        return True

    def invoke(self, operation: UnifiedRestrictiveOperation) -> bool:
        """Consume the mirror once at the single severity-aware boundary."""

        if not self._state_is_exact():
            return False
        if not self._owns_operation(operation):
            if self.mutation != "foreign_restrictive_operation_authorized":
                return False
            if not _restrictive_operation_is_exact(operation):
                return False
        if (
            self.mutation not in self.SEMANTIC_STATE_BYPASS_MUTATIONS
            and self._operation_prefix_length(operation) != 2
        ):
            return False
        if (
            operation.body_mirror_token_id is None
            and self.mutation != "restrictive_invokes_before_body_mirror"
        ):
            return False
        if operation.boundary_invocations:
            return False
        operation.events.append("PHYSICAL_BOUNDARY_INVOCATION")
        operation.boundary_invocations += 1
        blocker = max(
            (
                pending.severity
                for operation_id, pending in self.pending.items()
                if operation_id != operation.operation_id
                and not pending.arbiter_resolved
            ),
            default=Severity.ACTIVE,
        )
        blocker = max(blocker, self.highest_resolved)
        if (
            operation.severity < blocker
            and self.mutation != "unified_hold_effect_after_estop_pending"
        ):
            operation.boundary_result = (
                f"DEFINITIVE_NO_EFFECT_SUPERSEDED_{operation.severity.name}"
            )
            return True
        operation.boundary_result = f"APPLIED_{operation.severity.name}"
        operation.physical_effects += 1
        return True

    def resolve(self, operation: UnifiedRestrictiveOperation) -> bool:
        """Install the exact boundary result in the arbiter."""

        if not self._state_is_exact():
            return False
        if not self._owns_operation(operation):
            if self.mutation != "foreign_restrictive_operation_authorized":
                return False
            if not _restrictive_operation_is_exact(operation):
                return False
        if (
            self.mutation not in self.SEMANTIC_STATE_BYPASS_MUTATIONS
            and self._operation_prefix_length(operation) != 3
        ):
            return False
        if (
            operation.boundary_result is None
            and self.mutation != "restrictive_resolves_before_invocation"
        ):
            return False
        if operation.boundary_result is None:
            operation.boundary_result = f"APPLIED_{operation.severity.name}"
        operation.events.append("ARBITER_RESOLVE")
        operation.arbiter_resolved = True
        if operation.boundary_result.startswith("APPLIED_"):
            self.highest_resolved = max(self.highest_resolved, operation.severity)
        return True

    def complete(self, operation: UnifiedRestrictiveOperation) -> bool:
        """Let the body consume the exact installed arbiter result."""

        if not self._state_is_exact():
            return False
        if not self._owns_operation(operation):
            if self.mutation != "foreign_restrictive_operation_authorized":
                return False
            if not _restrictive_operation_is_exact(operation):
                return False
        if (
            self.mutation not in self.SEMANTIC_STATE_BYPASS_MUTATIONS
            and self._operation_prefix_length(operation) != 4
        ):
            return False
        if (
            not operation.arbiter_resolved
            and self.mutation != "restrictive_completes_before_arbiter_resolution"
        ):
            return False
        result_consumer = self.BODY_RESULT_CONSUMERS[operation.path]
        if (
            self.mutation == "capacity_retirement_uses_fail_safe_result_mirror"
            and operation.path == RestrictivePath.CAPACITY_RETIREMENT_RESTRICTIVE
        ):
            result_consumer = "COMPLETE_RESERVED_FAIL_SAFE_COMMAND"
        operation.body_result_consumer = result_consumer
        operation.events.append("BODY_COMPLETE")
        operation.body_completions += 1
        if operation.arbiter_resolved:
            self.pending.pop(operation.operation_id, None)
        return True

    def run(
        self,
        path: RestrictivePath,
        *,
        predecessor: UnifiedRestrictiveOperation | None = None,
    ) -> UnifiedRestrictiveOperation:
        """Drive one operation through the five commits."""

        operation = self.start(path, predecessor=predecessor)
        if self.mutation == "restrictive_invokes_before_body_mirror":
            self.invoke(operation)
            self.mirror(operation)
        else:
            self.mirror(operation)

        if self.mutation == "restrictive_resolves_before_invocation":
            self.resolve(operation)
            self.invoke(operation)
            self.complete(operation)
        elif self.mutation == "restrictive_completes_before_arbiter_resolution":
            self.invoke(operation)
            self.complete(operation)
            self.resolve(operation)
        else:
            self.invoke(operation)
            self.resolve(operation)
            self.complete(operation)
        return operation

    def replay(self, operation_id: str) -> UnifiedRestrictiveOperation:
        """Return the installed terminal chain without allocating or acting."""

        if not self._state_is_exact() or type(operation_id) is not str:
            raise ProbeError("replay operation identifier is not an exact string")
        operation = self.operations.get(operation_id)
        if operation is None or not self._owns_operation(operation):
            raise ProbeError("replay operation is not retained here")
        if (
            self._operation_prefix_length(operation) != len(self.EXPECTED_EVENTS)
            and self.mutation != "incomplete_restrictive_replay_authorized"
        ):
            raise ProbeError("replay operation is not terminal")
        if self.mutation == "restrictive_replay_reinvokes":
            operation.boundary_invocations += 1
            operation.physical_effects += 1
        if self.mutation == "restrictive_replay_recompletes":
            operation.body_completions += 1
        return operation

    def advance_to_cut(
        self,
        path: RestrictivePath,
        cut: RestrictiveCrashCut,
    ) -> UnifiedRestrictiveOperation:
        """Create one normal prefix ending at the selected durable cut."""

        if not self._state_is_exact():
            raise ProbeError("restrictive boundary state shape is not exact")
        if not _exact_enum(cut, RestrictiveCrashCut):
            raise ProbeError("restrictive crash cut is not an exact closed value")
        operation = self.start(path)
        if cut == RestrictiveCrashCut.AFTER_ARBITER_PENDING:
            return operation
        self.mirror(operation)
        if cut == RestrictiveCrashCut.AFTER_BODY_MIRROR:
            return operation
        self.invoke(operation)
        if cut == RestrictiveCrashCut.AFTER_BOUNDARY_INVOCATION:
            return operation
        self.resolve(operation)
        return operation

    def recover(
        self,
        operation: UnifiedRestrictiveOperation,
    ) -> UnifiedRestrictiveOperation:
        """Resume the exact durable operation and never repeat an invocation."""

        if not self._state_is_exact():
            raise ProbeError("restrictive boundary state shape is not exact")
        if not self._owns_operation(operation):
            if self.mutation != "foreign_restrictive_operation_authorized":
                raise ProbeError("recovery operation is not retained here")
            if not _restrictive_operation_is_exact(operation):
                raise ProbeError("recovery operation shape is not exact")
        if self.mutation == "restrictive_recovery_mints_token":
            operation.token = RestrictiveToken(
                f"{operation.token.token_id}-recovery",
                operation.path,
            )
        if self.mutation == "restrictive_recovery_reinvokes":
            operation.events.append("PHYSICAL_BOUNDARY_INVOCATION")
            operation.boundary_invocations += 1
            operation.physical_effects += 1

        if "BODY_OPERATION_MIRROR" not in operation.events:
            self.mirror(operation)
        if "PHYSICAL_BOUNDARY_INVOCATION" not in operation.events:
            self.invoke(operation)
        if "ARBITER_RESOLVE" not in operation.events:
            self.resolve(operation)
        if "BODY_COMPLETE" not in operation.events:
            self.complete(operation)
        return operation


def _unified_dag_is_exact(operation: UnifiedRestrictiveOperation) -> bool:
    """Check the exact five-commit order and one-use boundary semantics."""

    if not _restrictive_operation_is_exact(operation):
        return False
    expected_effects = int(
        operation.boundary_result is not None
        and operation.boundary_result.startswith("APPLIED_")
    )
    return (
        tuple(operation.events) == UnifiedPhysicalBoundary.EXPECTED_EVENTS
        and operation.body_mirror_token_id == operation.token.token_id
        and operation.body_mirror_owner
        == UnifiedPhysicalBoundary.BODY_MIRROR_OWNERS[operation.path]
        and operation.boundary_invocations == 1
        and operation.physical_effects == expected_effects
        and operation.arbiter_resolved
        and operation.body_result_consumer
        == UnifiedPhysicalBoundary.BODY_RESULT_CONSUMERS[operation.path]
        and operation.body_completions == 1
    )


def _campaign_unified_physical_boundary(model: Model, audit: Audit) -> None:
    """Challenge every restrictive path, replay, severity, and crash cut."""

    path_operations: dict[RestrictivePath, UnifiedRestrictiveOperation] = {}
    for path in (
        RestrictivePath.INITIAL_HOLD,
        RestrictivePath.INITIAL_ESTOP,
        RestrictivePath.DRAIN_ESTOP,
        RestrictivePath.CAPACITY_RETIREMENT_RESTRICTIVE,
    ):
        boundary = UnifiedPhysicalBoundary(model.mutation)
        operation = boundary.run(path)
        path_operations[path] = operation
        audit.case(5)

    upgrade_boundary = UnifiedPhysicalBoundary(model.mutation)
    predecessor = upgrade_boundary.run(RestrictivePath.INITIAL_HOLD)
    upgrade = upgrade_boundary.run(
        RestrictivePath.UPGRADE_ESTOP,
        predecessor=predecessor,
    )
    path_operations[RestrictivePath.UPGRADE_ESTOP] = upgrade
    audit.case(5)

    exact_by_path = {
        path: _unified_dag_is_exact(operation)
        for path, operation in path_operations.items()
    }
    audit.require(
        path_operations[RestrictivePath.INITIAL_HOLD].events
        and path_operations[RestrictivePath.INITIAL_HOLD].events[0]
        == "ARBITER_PENDING",
        "arbiter_pending_precedes_body_mirror",
    )
    audit.require(
        all(
            operation.events.index("BODY_OPERATION_MIRROR")
            < operation.events.index("PHYSICAL_BOUNDARY_INVOCATION")
            for operation in path_operations.values()
        ),
        "body_mirror_precedes_invocation",
    )
    audit.require(
        all(
            operation.events.index("PHYSICAL_BOUNDARY_INVOCATION")
            < operation.events.index("ARBITER_RESOLVE")
            for operation in path_operations.values()
        ),
        "invocation_precedes_arbiter_resolution",
    )
    audit.require(
        all(
            operation.events.index("ARBITER_RESOLVE")
            < operation.events.index("BODY_COMPLETE")
            for operation in path_operations.values()
        ),
        "arbiter_resolution_precedes_body_completion",
    )
    audit.require(
        all(
            operation.body_mirror_token_id == operation.token.token_id
            for operation in path_operations.values()
        ),
        "body_mirror_binds_pending_operation",
    )
    audit.require(
        exact_by_path[RestrictivePath.UPGRADE_ESTOP],
        "upgrade_uses_unified_physical_dag",
    )
    audit.require(
        exact_by_path[RestrictivePath.DRAIN_ESTOP],
        "drain_estop_uses_unified_physical_dag",
    )
    audit.require(
        exact_by_path[RestrictivePath.CAPACITY_RETIREMENT_RESTRICTIVE],
        "capacity_fallback_uses_unified_physical_dag",
    )
    audit.require(
        upgrade.token.token_id != predecessor.token.token_id,
        "upgrade_uses_fresh_chain_token",
    )
    audit.require(
        upgrade.fence_epoch > predecessor.fence_epoch,
        "unified_fresh_fence_epoch",
    )
    capacity = path_operations[RestrictivePath.CAPACITY_RETIREMENT_RESTRICTIVE]
    audit.require(
        capacity.token.pre_reserved
        and capacity.token.path == RestrictivePath.CAPACITY_RETIREMENT_RESTRICTIVE,
        "capacity_fallback_uses_pre_reserved_token",
    )
    capacity_pending_mirror_is_cause_owned = (
        capacity.body_mirror_owner
        == "EXHAUST_BODY_REMOTE_COMMAND_CAPACITY_TO_RETIREMENT_DRAIN"
    )
    capacity_result_mirror_is_generic = (
        capacity.body_result_consumer == "RECONCILE_BODY_ACTUATION_ARBITER_TRANSITION/"
        "RESTRICTIVE_RESULT_MIRROR"
    )
    audit.require(
        capacity_pending_mirror_is_cause_owned,
        "capacity_retirement_uses_cause_owned_pending_mirror",
    )
    audit.require(
        capacity_result_mirror_is_generic,
        "capacity_retirement_uses_generic_result_mirror",
    )
    audit.witness(
        "initial_hold_uses_unified_physical_dag",
        exact_by_path[RestrictivePath.INITIAL_HOLD],
    )
    audit.witness(
        "initial_estop_uses_unified_physical_dag",
        exact_by_path[RestrictivePath.INITIAL_ESTOP],
    )
    audit.witness(
        "hold_to_estop_upgrade_uses_new_chain_token_and_epoch",
        exact_by_path[RestrictivePath.UPGRADE_ESTOP]
        and upgrade.token.token_id != predecessor.token.token_id
        and upgrade.fence_epoch > predecessor.fence_epoch,
    )
    drain = path_operations[RestrictivePath.DRAIN_ESTOP]
    audit.witness(
        "drain_estop_uses_pre_reserved_chain_token_and_epoch",
        exact_by_path[RestrictivePath.DRAIN_ESTOP]
        and drain.token.pre_reserved
        and drain.fence_epoch > 0,
    )
    audit.witness(
        "capacity_fallback_uses_pre_reserved_chain_token_and_epoch",
        exact_by_path[RestrictivePath.CAPACITY_RETIREMENT_RESTRICTIVE]
        and capacity.token.pre_reserved
        and capacity.fence_epoch > 0,
    )
    audit.witness(
        "capacity_retirement_uses_cause_owned_pending_mirror",
        capacity_pending_mirror_is_cause_owned,
    )
    audit.witness(
        "capacity_retirement_uses_generic_result_mirror",
        capacity_result_mirror_is_generic,
    )
    audit.witness(
        "every_restrictive_path_invokes_once",
        all(
            operation.boundary_invocations == 1
            for operation in path_operations.values()
        ),
    )
    audit.witness(
        "body_mirror_binds_exact_pending_operation",
        all(
            operation.body_mirror_token_id == operation.token.token_id
            for operation in path_operations.values()
        ),
    )
    audit.witness(
        "arbiter_resolution_precedes_body_completion",
        all(
            operation.events.index("ARBITER_RESOLVE")
            < operation.events.index("BODY_COMPLETE")
            for operation in path_operations.values()
        ),
    )

    invalid_invoke_boundary = UnifiedPhysicalBoundary(model.mutation)
    invalid_invoke = invalid_invoke_boundary.start(RestrictivePath.INITIAL_HOLD)
    if not invalid_invoke_boundary.invoke(invalid_invoke):
        audit.reject()
    audit.case()
    invalid_complete_boundary = UnifiedPhysicalBoundary(model.mutation)
    invalid_complete = invalid_complete_boundary.start(RestrictivePath.INITIAL_HOLD)
    if not invalid_complete_boundary.complete(invalid_complete):
        audit.reject()
    audit.case()

    one_use_boundary = UnifiedPhysicalBoundary(model.mutation)
    one_use_boundary.run(RestrictivePath.INITIAL_HOLD)
    try:
        one_use_boundary.start(RestrictivePath.INITIAL_HOLD)
    except ProbeError:
        reused_token_rejected = True
    else:
        reused_token_rejected = False
    audit.case()
    if reused_token_rejected:
        audit.reject()
    audit.require(reused_token_rejected, "unified_chain_token_one_use")
    audit.witness(
        "restrictive_chain_token_is_one_use",
        reused_token_rejected,
    )

    missing_predecessor_boundary = UnifiedPhysicalBoundary(model.mutation)
    try:
        missing_predecessor_boundary.run(RestrictivePath.UPGRADE_ESTOP)
    except ProbeError:
        missing_predecessor_rejected = True
    else:
        missing_predecessor_rejected = False
    audit.case()
    if missing_predecessor_rejected:
        audit.reject()
    audit.require(
        missing_predecessor_rejected,
        "upgrade_requires_completed_hold",
    )
    audit.witness(
        "upgrade_requires_completed_hold_predecessor",
        missing_predecessor_rejected,
    )

    replay_mutation = (
        model.mutation
        if model.mutation
        in {
            "restrictive_replay_reinvokes",
            "restrictive_replay_recompletes",
            "incomplete_restrictive_replay_authorized",
        }
        else None
    )
    replay_boundary = UnifiedPhysicalBoundary(replay_mutation)
    replay_operation = replay_boundary.run(RestrictivePath.INITIAL_HOLD)
    replay_identity = (
        replay_operation.operation_id,
        replay_operation.token.token_id,
        replay_operation.fence_epoch,
        replay_operation.boundary_invocations,
        replay_operation.body_completions,
    )
    for _index in range(3):
        replay_boundary.replay(replay_operation.operation_id)
        audit.case()
    replay_after = (
        replay_operation.operation_id,
        replay_operation.token.token_id,
        replay_operation.fence_epoch,
        replay_operation.boundary_invocations,
        replay_operation.body_completions,
    )
    audit.require(
        replay_operation.boundary_invocations == 1,
        "unified_exact_replay_no_second_invocation",
    )
    audit.require(
        replay_operation.body_completions == 1,
        "unified_exact_replay_no_second_completion",
    )
    audit.witness(
        "exact_replay_returns_terminal_chain_without_invocation",
        replay_identity == replay_after,
    )

    severity_boundary = UnifiedPhysicalBoundary(model.mutation)
    pending_estop = severity_boundary.start(RestrictivePath.INITIAL_ESTOP)
    delayed_hold = severity_boundary.run(RestrictivePath.INITIAL_HOLD)
    severity_boundary.mirror(pending_estop)
    severity_boundary.invoke(pending_estop)
    severity_boundary.resolve(pending_estop)
    severity_boundary.complete(pending_estop)
    audit.case(10)
    delayed_hold_rejected = (
        delayed_hold.boundary_result == "DEFINITIVE_NO_EFFECT_SUPERSEDED_HOLD"
        and delayed_hold.physical_effects == 0
        and pending_estop.physical_effects == 1
    )
    audit.require(delayed_hold_rejected, "unified_severity_order")
    if delayed_hold_rejected:
        audit.reject()
    audit.witness(
        "pending_estop_rejects_delayed_hold_without_effect",
        delayed_hold_rejected,
    )

    recovery_exact = True
    recovery_no_reinvocation = True
    for cut in RestrictiveCrashCut:
        recovery_boundary = UnifiedPhysicalBoundary(model.mutation)
        recovering = recovery_boundary.advance_to_cut(
            RestrictivePath.INITIAL_ESTOP,
            cut,
        )
        before_identity = (
            recovering.operation_id,
            recovering.token.token_id,
            recovering.fence_epoch,
        )
        recovered = recovery_boundary.recover(recovering)
        after_identity = (
            recovered.operation_id,
            recovered.token.token_id,
            recovered.fence_epoch,
        )
        recovery_exact = (
            recovery_exact
            and before_identity == after_identity
            and _unified_dag_is_exact(recovered)
        )
        recovery_no_reinvocation = (
            recovery_no_reinvocation and recovered.boundary_invocations == 1
        )
        audit.case(5)
    audit.require(recovery_exact, "unified_crash_recovery_identity")
    audit.require(
        recovery_no_reinvocation,
        "unified_crash_recovery_no_reinvocation",
    )
    audit.witness("crash_at_each_dag_cut_reuses_exact_operation", recovery_exact)


class HoldBoundaryLifecycle(StrEnum):
    """Closed HOLD lifecycle, including terminal ambiguous physical outcome."""

    NONE = "NONE"
    HOLD_PENDING = "HOLD_PENDING"
    HOLD_EFFECTIVE = "HOLD_EFFECTIVE"
    HOLD_OUTCOME_UNKNOWN = "HOLD_OUTCOME_UNKNOWN"
    HOLD_CYCLE_CONSUMED = "HOLD_CYCLE_CONSUMED"


class EstopLifecycleFloor(StrEnum):
    """Generation-global ESTOP floor retained through retirement."""

    NONE = "NONE"
    ESTOP_LATCHED = "ESTOP_LATCHED"
    ESTOP_OUTCOME_UNKNOWN = "ESTOP_OUTCOME_UNKNOWN"


class RetirementClosureKind(StrEnum):
    """Closed body-boundary retirement-evidence union."""

    EXACT_ARBITER_RETIREMENT = "EXACT_ARBITER_RETIREMENT"
    LOST_ARBITER_PHYSICAL_ISOLATION = "LOST_ARBITER_PHYSICAL_ISOLATION"


class RetirementAuthorization(StrEnum):
    """Whether retirement has the specialized ESTOP lifecycle authority."""

    NON_SPECIALIZED = "NON_SPECIALIZED"
    OPERATOR_RESET_AND_RETIRE_GENERATION = "OPERATOR_RESET_AND_RETIRE_GENERATION"


@dataclass(frozen=True)
class PhysicalIsolationProof:
    """One machine-retained qualified physical-isolation capability."""

    proof_id: str


def _physical_isolation_proof_is_exact(value: object) -> bool:
    return type(value) is PhysicalIsolationProof and _exact_closed_identifier(
        value.proof_id
    )


@dataclass(frozen=True)
class RetirementClosureEvidence:
    """Installed closure result; isolation never impersonates arbiter evidence."""

    kind: RetirementClosureKind
    hold_state: HoldBoundaryLifecycle
    estop_floor: EstopLifecycleFloor
    pending_hold_closed: bool
    exact_terminal_hold_result_preserved: bool
    physical_isolation_proved: bool
    closure_id: str = ""
    physical_isolation_proof_id: str | None = None


def _retirement_closure_evidence_is_exact(value: object) -> bool:
    return (
        type(value) is RetirementClosureEvidence
        and _exact_enum(value.kind, RetirementClosureKind)
        and _exact_enum(value.hold_state, HoldBoundaryLifecycle)
        and _exact_enum(value.estop_floor, EstopLifecycleFloor)
        and _exact_bool(value.pending_hold_closed)
        and _exact_bool(value.exact_terminal_hold_result_preserved)
        and _exact_bool(value.physical_isolation_proved)
        and _exact_closed_identifier(value.closure_id)
        and _exact_optional_closed_identifier(value.physical_isolation_proof_id)
    )


class RetirementClosureMachine:
    """Bounded model for terminal HOLD and ESTOP-aware finalization."""

    TERMINAL_HOLD_STATES = frozenset(
        {
            HoldBoundaryLifecycle.HOLD_EFFECTIVE,
            HoldBoundaryLifecycle.HOLD_OUTCOME_UNKNOWN,
            HoldBoundaryLifecycle.HOLD_CYCLE_CONSUMED,
        }
    )

    def __init__(self, mutation: str | None) -> None:
        self.mutation = _validate_mutation_selector(mutation)
        self._closure_counter = 0
        self._installed_evidence: dict[str, RetirementClosureEvidence] = {}
        self._issued_evidence: list[RetirementClosureEvidence] = []
        self._physical_isolation_proof = PhysicalIsolationProof(
            "qualified-physical-isolation-proof"
        )

    def _evidence_semantics_are_closed(
        self,
        evidence: RetirementClosureEvidence,
    ) -> bool:
        hold_is_closed = (
            evidence.hold_state == HoldBoundaryLifecycle.NONE
            or evidence.hold_state in self.TERMINAL_HOLD_STATES
        )
        if evidence.kind == RetirementClosureKind.EXACT_ARBITER_RETIREMENT:
            return (
                hold_is_closed
                and not evidence.pending_hold_closed
                and evidence.exact_terminal_hold_result_preserved
                == (evidence.hold_state in self.TERMINAL_HOLD_STATES)
                and not evidence.physical_isolation_proved
                and evidence.physical_isolation_proof_id is None
            )
        return (
            evidence.kind == RetirementClosureKind.LOST_ARBITER_PHYSICAL_ISOLATION
            and hold_is_closed
            and (
                not evidence.pending_hold_closed
                or evidence.hold_state == HoldBoundaryLifecycle.HOLD_OUTCOME_UNKNOWN
            )
            and not evidence.exact_terminal_hold_result_preserved
            and evidence.physical_isolation_proved
            and evidence.physical_isolation_proof_id
            == self._physical_isolation_proof.proof_id
        )

    def _state_is_exact(self) -> bool:
        if (
            not _physical_isolation_proof_is_exact(self._physical_isolation_proof)
            or not _exact_nonnegative_int(self._closure_counter)
            or type(self._installed_evidence) is not dict
            or type(self._issued_evidence) is not list
            or not all(
                _exact_closed_identifier(closure_id)
                and _retirement_closure_evidence_is_exact(evidence)
                and evidence.closure_id == closure_id
                for closure_id, evidence in self._installed_evidence.items()
            )
            or not all(
                _retirement_closure_evidence_is_exact(evidence)
                for evidence in self._issued_evidence
            )
        ):
            return False
        expected_ids = [
            f"retirement-closure-{ordinal}" for ordinal in range(self._closure_counter)
        ]
        return (
            len(self._installed_evidence) == self._closure_counter
            and len(self._issued_evidence) == self._closure_counter
            and list(self._installed_evidence) == expected_ids
            and [evidence.closure_id for evidence in self._issued_evidence]
            == expected_ids
            and all(
                self._installed_evidence[closure_id] is evidence
                and self._evidence_semantics_are_closed(evidence)
                for closure_id, evidence in zip(
                    expected_ids,
                    self._issued_evidence,
                    strict=True,
                )
            )
        )

    def physical_isolation_proof(self) -> PhysicalIsolationProof:
        """Return the exact qualified-isolation capability retained here."""

        return self._physical_isolation_proof

    def _retain_evidence(
        self,
        *,
        kind: RetirementClosureKind,
        hold_state: HoldBoundaryLifecycle,
        estop_floor: EstopLifecycleFloor,
        pending_hold_closed: bool,
        exact_terminal_hold_result_preserved: bool,
        physical_isolation_proved: bool,
        physical_isolation_proof_id: str | None,
    ) -> RetirementClosureEvidence:
        closure_id = f"retirement-closure-{self._closure_counter}"
        self._closure_counter += 1
        evidence = RetirementClosureEvidence(
            kind=kind,
            hold_state=hold_state,
            estop_floor=estop_floor,
            pending_hold_closed=pending_hold_closed,
            exact_terminal_hold_result_preserved=(exact_terminal_hold_result_preserved),
            physical_isolation_proved=physical_isolation_proved,
            closure_id=closure_id,
            physical_isolation_proof_id=physical_isolation_proof_id,
        )
        self._installed_evidence[closure_id] = evidence
        self._issued_evidence.append(evidence)
        return evidence

    def observed_hold_state(
        self,
        state: HoldBoundaryLifecycle,
    ) -> HoldBoundaryLifecycle:
        """Return the installed state, including one hostile alias mutant."""

        if not _exact_enum(state, HoldBoundaryLifecycle):
            raise ProbeError("HOLD lifecycle state is not an exact closed value")
        if (
            self.mutation == "hold_outcome_unknown_aliases_effective"
            and state == HoldBoundaryLifecycle.HOLD_OUTCOME_UNKNOWN
        ):
            return HoldBoundaryLifecycle.HOLD_EFFECTIVE
        return state

    def is_terminal_hold_state(self, state: HoldBoundaryLifecycle) -> bool:
        """Classify a HOLD result without upgrading ambiguity to success."""

        if not _exact_enum(state, HoldBoundaryLifecycle):
            return False
        if (
            self.mutation == "hold_outcome_unknown_is_nonterminal"
            and state == HoldBoundaryLifecycle.HOLD_OUTCOME_UNKNOWN
        ):
            return False
        return state in self.TERMINAL_HOLD_STATES

    def install_closure(
        self,
        *,
        kind: RetirementClosureKind,
        hold_state: HoldBoundaryLifecycle,
        estop_floor: EstopLifecycleFloor = EstopLifecycleFloor.NONE,
        physical_isolation_proof: PhysicalIsolationProof | None = None,
    ) -> RetirementClosureEvidence | None:
        """Install one exact-arbiter or proved-isolation closure branch."""

        if not self._state_is_exact():
            return None
        proof_is_retained = (
            _physical_isolation_proof_is_exact(physical_isolation_proof)
            and physical_isolation_proof is self._physical_isolation_proof
        )
        if (
            self.mutation == "retirement_isolation_proof_equality_authorized"
            and _physical_isolation_proof_is_exact(physical_isolation_proof)
        ):
            proof_is_retained = (
                physical_isolation_proof == self._physical_isolation_proof
            )
        if physical_isolation_proof is not None and not proof_is_retained:
            return None
        if not _exact_enum(kind, RetirementClosureKind):
            if self.mutation != "unknown_retirement_closure_kind_accepted":
                return None
            kind = RetirementClosureKind.LOST_ARBITER_PHYSICAL_ISOLATION
        if not _exact_enum(hold_state, HoldBoundaryLifecycle):
            if self.mutation != "unknown_retirement_hold_state_accepted":
                return None
            hold_state = HoldBoundaryLifecycle.NONE
        if not _exact_enum(estop_floor, EstopLifecycleFloor):
            if self.mutation != "unknown_retirement_estop_floor_accepted":
                return None
            estop_floor = EstopLifecycleFloor.NONE

        if kind == RetirementClosureKind.EXACT_ARBITER_RETIREMENT:
            if physical_isolation_proof is not None:
                return None
            if hold_state == HoldBoundaryLifecycle.HOLD_PENDING:
                return None
            installed_hold_state = self.observed_hold_state(hold_state)
            if (
                self.mutation == "exact_retirement_rewrites_hold_unknown"
                and hold_state == HoldBoundaryLifecycle.HOLD_OUTCOME_UNKNOWN
            ):
                installed_hold_state = HoldBoundaryLifecycle.HOLD_EFFECTIVE
            if (
                installed_hold_state != HoldBoundaryLifecycle.NONE
                and not self.is_terminal_hold_state(installed_hold_state)
            ):
                return None
            terminal_result_preserved = (
                hold_state in self.TERMINAL_HOLD_STATES
                and installed_hold_state == hold_state
            )
            return self._retain_evidence(
                kind=kind,
                hold_state=installed_hold_state,
                estop_floor=estop_floor,
                pending_hold_closed=False,
                exact_terminal_hold_result_preserved=terminal_result_preserved,
                physical_isolation_proved=False,
                physical_isolation_proof_id=None,
            )

        if not proof_is_retained and self.mutation != "lost_isolation_skips_proof":
            return None
        installed_hold_state = self.observed_hold_state(hold_state)
        pending_hold_closed = False
        if hold_state == HoldBoundaryLifecycle.HOLD_PENDING:
            pending_hold_closed = True
            installed_hold_state = HoldBoundaryLifecycle.HOLD_OUTCOME_UNKNOWN
            if self.mutation == "lost_isolation_closes_hold_effective":
                installed_hold_state = HoldBoundaryLifecycle.HOLD_EFFECTIVE
            elif self.mutation == "lost_isolation_leaves_hold_pending":
                installed_hold_state = HoldBoundaryLifecycle.HOLD_PENDING
                pending_hold_closed = False
        return self._retain_evidence(
            kind=kind,
            hold_state=installed_hold_state,
            estop_floor=estop_floor,
            pending_hold_closed=pending_hold_closed,
            exact_terminal_hold_result_preserved=False,
            physical_isolation_proved=proof_is_retained,
            physical_isolation_proof_id=(
                physical_isolation_proof.proof_id if proof_is_retained else None
            ),
        )

    def can_finalize(
        self,
        evidence: RetirementClosureEvidence | None,
        authorization: RetirementAuthorization,
    ) -> bool:
        """Reject nonterminal HOLD and ESTOP without specialized retirement."""

        if not self._state_is_exact():
            return False
        evidence_is_exact = _retirement_closure_evidence_is_exact(evidence)
        if self.mutation == "retirement_evidence_subclass_authorized" and isinstance(
            evidence, RetirementClosureEvidence
        ):
            evidence_is_exact = (
                _exact_enum(evidence.kind, RetirementClosureKind)
                and _exact_enum(evidence.hold_state, HoldBoundaryLifecycle)
                and _exact_enum(evidence.estop_floor, EstopLifecycleFloor)
                and _exact_bool(evidence.pending_hold_closed)
                and _exact_bool(evidence.exact_terminal_hold_result_preserved)
                and _exact_bool(evidence.physical_isolation_proved)
                and _exact_closed_identifier(evidence.closure_id)
                and _exact_optional_closed_identifier(
                    evidence.physical_isolation_proof_id
                )
            )
        if not evidence_is_exact:
            return False
        evidence_identity_is_retained = self._installed_evidence.get(
            evidence.closure_id
        ) is evidence and any(
            candidate is evidence for candidate in self._issued_evidence
        )
        if self.mutation in {
            "retirement_evidence_subclass_authorized",
            "forged_lost_isolation_evidence_finalizes",
            "forged_lost_pending_effective_finalizes",
            "forged_exact_terminal_hold_without_preservation_finalizes",
            "finalize_from_hold_pending",
            "caller_constructed_retirement_evidence_authorized",
        }:
            evidence_identity_is_retained = True
        if not evidence_identity_is_retained:
            return False
        if not _exact_enum(authorization, RetirementAuthorization):
            if self.mutation != "unknown_retirement_authorization_allows_estop":
                return False
            authorization = RetirementAuthorization.OPERATOR_RESET_AND_RETIRE_GENERATION
        if evidence.kind == RetirementClosureKind.EXACT_ARBITER_RETIREMENT:
            if (
                evidence.physical_isolation_proved
                or evidence.physical_isolation_proof_id is not None
                or evidence.pending_hold_closed
            ):
                return False
            expected_preservation = evidence.hold_state in self.TERMINAL_HOLD_STATES
            if (
                evidence.exact_terminal_hold_result_preserved != expected_preservation
                and self.mutation
                != "forged_exact_terminal_hold_without_preservation_finalizes"
            ):
                return False
        else:
            if (
                not evidence.physical_isolation_proved
                or evidence.physical_isolation_proof_id
                != self._physical_isolation_proof.proof_id
            ) and self.mutation != "forged_lost_isolation_evidence_finalizes":
                return False
            if evidence.exact_terminal_hold_result_preserved:
                return False
            if (
                evidence.pending_hold_closed
                and evidence.hold_state != HoldBoundaryLifecycle.HOLD_OUTCOME_UNKNOWN
                and self.mutation != "forged_lost_pending_effective_finalizes"
            ):
                return False
        if evidence.hold_state == HoldBoundaryLifecycle.HOLD_PENDING:
            if self.mutation != "finalize_from_hold_pending":
                return False
        elif (
            evidence.hold_state != HoldBoundaryLifecycle.NONE
            and not self.is_terminal_hold_state(evidence.hold_state)
        ):
            return False
        if (
            evidence.estop_floor == EstopLifecycleFloor.ESTOP_LATCHED
            and authorization == RetirementAuthorization.NON_SPECIALIZED
            and self.mutation != "non_specialized_retirement_allows_estop_latched"
        ):
            return False
        if (
            evidence.estop_floor == EstopLifecycleFloor.ESTOP_OUTCOME_UNKNOWN
            and authorization == RetirementAuthorization.NON_SPECIALIZED
            and self.mutation != "non_specialized_retirement_allows_estop_unknown"
        ):
            return False
        return True


def _campaign_retirement_closure(model: Model, audit: Audit) -> None:
    """Challenge terminal HOLD closure and specialized ESTOP retirement."""

    machine = RetirementClosureMachine(model.mutation)
    observed_unknown = machine.observed_hold_state(
        HoldBoundaryLifecycle.HOLD_OUTCOME_UNKNOWN
    )
    unknown_is_distinct = (
        observed_unknown == HoldBoundaryLifecycle.HOLD_OUTCOME_UNKNOWN
        and observed_unknown != HoldBoundaryLifecycle.HOLD_EFFECTIVE
    )
    unknown_is_terminal = machine.is_terminal_hold_state(
        HoldBoundaryLifecycle.HOLD_OUTCOME_UNKNOWN
    )
    audit.case()
    audit.require(unknown_is_distinct, "hold_outcome_unknown_is_distinct")
    audit.require(unknown_is_terminal, "hold_outcome_unknown_is_terminal")
    audit.witness(
        "hold_outcome_unknown_is_distinct_and_terminal",
        unknown_is_distinct and unknown_is_terminal,
    )

    exact_results_preserved = True
    for terminal_hold_state in (
        HoldBoundaryLifecycle.HOLD_EFFECTIVE,
        HoldBoundaryLifecycle.HOLD_OUTCOME_UNKNOWN,
    ):
        exact = machine.install_closure(
            kind=RetirementClosureKind.EXACT_ARBITER_RETIREMENT,
            hold_state=terminal_hold_state,
        )
        preserved = (
            exact is not None
            and exact.hold_state == terminal_hold_state
            and exact.exact_terminal_hold_result_preserved
            and machine.can_finalize(
                exact,
                RetirementAuthorization.NON_SPECIALIZED,
            )
        )
        exact_results_preserved = exact_results_preserved and preserved
        audit.case()
    audit.require(
        exact_results_preserved,
        "exact_retirement_preserves_terminal_hold_result",
    )
    audit.witness(
        "exact_arbiter_retirement_preserves_terminal_hold_result",
        exact_results_preserved,
    )

    forged_pending = RetirementClosureEvidence(
        kind=RetirementClosureKind.EXACT_ARBITER_RETIREMENT,
        hold_state=HoldBoundaryLifecycle.HOLD_PENDING,
        estop_floor=EstopLifecycleFloor.NONE,
        pending_hold_closed=False,
        exact_terminal_hold_result_preserved=False,
        physical_isolation_proved=False,
        closure_id="forged-pending-closure",
    )
    direct_pending_finalization_rejected = not machine.can_finalize(
        forged_pending,
        RetirementAuthorization.NON_SPECIALIZED,
    )
    audit.case()
    if direct_pending_finalization_rejected:
        audit.reject()

    exact_pending_rejected = (
        machine.install_closure(
            kind=RetirementClosureKind.EXACT_ARBITER_RETIREMENT,
            hold_state=HoldBoundaryLifecycle.HOLD_PENDING,
        )
        is None
    )
    audit.case()
    if exact_pending_rejected:
        audit.reject()
    hold_pending_rejected = (
        direct_pending_finalization_rejected and exact_pending_rejected
    )
    audit.require(hold_pending_rejected, "hold_pending_cannot_finalize")
    audit.witness("hold_pending_cannot_finalize", hold_pending_rejected)

    unproved_isolation_rejected = (
        machine.install_closure(
            kind=RetirementClosureKind.LOST_ARBITER_PHYSICAL_ISOLATION,
            hold_state=HoldBoundaryLifecycle.HOLD_PENDING,
        )
        is None
    )
    audit.case()
    if unproved_isolation_rejected:
        audit.reject()
    audit.require(unproved_isolation_rejected, "lost_isolation_requires_proof")
    audit.witness(
        "lost_arbiter_isolation_requires_proof",
        unproved_isolation_rejected,
    )

    isolated_pending = machine.install_closure(
        kind=RetirementClosureKind.LOST_ARBITER_PHYSICAL_ISOLATION,
        hold_state=HoldBoundaryLifecycle.HOLD_PENDING,
        physical_isolation_proof=machine.physical_isolation_proof(),
    )
    isolation_terminalizes_unknown = (
        isolated_pending is not None
        and isolated_pending.pending_hold_closed
        and isolated_pending.hold_state == HoldBoundaryLifecycle.HOLD_OUTCOME_UNKNOWN
        and machine.is_terminal_hold_state(isolated_pending.hold_state)
        and machine.can_finalize(
            isolated_pending,
            RetirementAuthorization.NON_SPECIALIZED,
        )
    )
    audit.case()
    audit.require(
        isolation_terminalizes_unknown,
        "lost_isolation_pending_hold_becomes_unknown",
    )
    audit.witness(
        "lost_arbiter_isolation_terminalizes_pending_hold_as_unknown",
        isolation_terminalizes_unknown,
    )

    ordinary_estop_rejections: dict[EstopLifecycleFloor, bool] = {}
    specialized_estop_acceptances: dict[EstopLifecycleFloor, bool] = {}
    for estop_floor in (
        EstopLifecycleFloor.ESTOP_LATCHED,
        EstopLifecycleFloor.ESTOP_OUTCOME_UNKNOWN,
    ):
        estop_closure = machine.install_closure(
            kind=RetirementClosureKind.EXACT_ARBITER_RETIREMENT,
            hold_state=HoldBoundaryLifecycle.NONE,
            estop_floor=estop_floor,
        )
        ordinary_rejected = not machine.can_finalize(
            estop_closure,
            RetirementAuthorization.NON_SPECIALIZED,
        )
        ordinary_estop_rejections[estop_floor] = ordinary_rejected
        audit.case()
        if ordinary_rejected:
            audit.reject()
        specialized_estop_acceptances[estop_floor] = machine.can_finalize(
            estop_closure,
            RetirementAuthorization.OPERATOR_RESET_AND_RETIRE_GENERATION,
        )
        audit.case()

    audit.require(
        ordinary_estop_rejections[EstopLifecycleFloor.ESTOP_LATCHED],
        "non_specialized_retirement_rejects_estop_latched",
    )
    audit.require(
        ordinary_estop_rejections[EstopLifecycleFloor.ESTOP_OUTCOME_UNKNOWN],
        "non_specialized_retirement_rejects_estop_unknown",
    )
    audit.require(
        all(specialized_estop_acceptances.values()),
        "specialized_retirement_handles_estop_floors",
    )
    audit.witness(
        "non_specialized_retirement_rejects_both_estop_floors",
        all(ordinary_estop_rejections.values()),
    )
    audit.witness(
        "specialized_retirement_accepts_both_estop_floors",
        all(specialized_estop_acceptances.values()),
    )

    unknown_kind_rejected = (
        machine.install_closure(
            kind="UNKNOWN_RETIREMENT_CLOSURE",
            hold_state=HoldBoundaryLifecycle.NONE,
            physical_isolation_proof=machine.physical_isolation_proof(),
        )
        is None
    )
    audit.case()
    if unknown_kind_rejected:
        audit.reject()
    unknown_hold_state_rejected = (
        machine.install_closure(
            kind=RetirementClosureKind.EXACT_ARBITER_RETIREMENT,
            hold_state="UNKNOWN_HOLD_LIFECYCLE",
        )
        is None
    )
    audit.case()
    if unknown_hold_state_rejected:
        audit.reject()
    unknown_estop_floor_rejected = (
        machine.install_closure(
            kind=RetirementClosureKind.EXACT_ARBITER_RETIREMENT,
            hold_state=HoldBoundaryLifecycle.NONE,
            estop_floor="UNKNOWN_ESTOP_FLOOR",
        )
        is None
    )
    audit.case()
    if unknown_estop_floor_rejected:
        audit.reject()
    unknown_authorization_closure = machine.install_closure(
        kind=RetirementClosureKind.EXACT_ARBITER_RETIREMENT,
        hold_state=HoldBoundaryLifecycle.NONE,
        estop_floor=EstopLifecycleFloor.ESTOP_LATCHED,
    )
    unknown_authorization_rejected = not machine.can_finalize(
        unknown_authorization_closure,
        "UNKNOWN_RETIREMENT_AUTHORIZATION",
    )
    audit.case()
    if unknown_authorization_rejected:
        audit.reject()

    audit.require(unknown_kind_rejected, "retirement_closure_union_closed")
    audit.require(
        unknown_hold_state_rejected,
        "retirement_hold_lifecycle_union_closed",
    )
    audit.require(
        unknown_estop_floor_rejected,
        "retirement_estop_floor_union_closed",
    )
    audit.require(
        unknown_authorization_rejected,
        "retirement_authorization_union_closed",
    )
    audit.witness(
        "retirement_closed_unions_reject_unknown_values",
        unknown_kind_rejected
        and unknown_hold_state_rejected
        and unknown_estop_floor_rejected
        and unknown_authorization_rejected,
    )

    forged_unproved_isolation = RetirementClosureEvidence(
        kind=RetirementClosureKind.LOST_ARBITER_PHYSICAL_ISOLATION,
        hold_state=HoldBoundaryLifecycle.HOLD_OUTCOME_UNKNOWN,
        estop_floor=EstopLifecycleFloor.NONE,
        pending_hold_closed=True,
        exact_terminal_hold_result_preserved=False,
        physical_isolation_proved=False,
        closure_id="forged-unproved-isolation",
    )
    unproved_forgery_rejected = not machine.can_finalize(
        forged_unproved_isolation,
        RetirementAuthorization.NON_SPECIALIZED,
    )
    audit.case()
    if unproved_forgery_rejected:
        audit.reject()

    forged_effective_isolation = RetirementClosureEvidence(
        kind=RetirementClosureKind.LOST_ARBITER_PHYSICAL_ISOLATION,
        hold_state=HoldBoundaryLifecycle.HOLD_EFFECTIVE,
        estop_floor=EstopLifecycleFloor.NONE,
        pending_hold_closed=True,
        exact_terminal_hold_result_preserved=False,
        physical_isolation_proved=True,
        closure_id="forged-effective-isolation",
        physical_isolation_proof_id=(machine.physical_isolation_proof().proof_id),
    )
    effective_forgery_rejected = not machine.can_finalize(
        forged_effective_isolation,
        RetirementAuthorization.NON_SPECIALIZED,
    )
    audit.case()
    if effective_forgery_rejected:
        audit.reject()

    forged_exact_without_preservation = RetirementClosureEvidence(
        kind=RetirementClosureKind.EXACT_ARBITER_RETIREMENT,
        hold_state=HoldBoundaryLifecycle.HOLD_OUTCOME_UNKNOWN,
        estop_floor=EstopLifecycleFloor.NONE,
        pending_hold_closed=False,
        exact_terminal_hold_result_preserved=False,
        physical_isolation_proved=False,
        closure_id="forged-exact-without-preservation",
    )
    exact_preservation_forgery_rejected = not machine.can_finalize(
        forged_exact_without_preservation,
        RetirementAuthorization.NON_SPECIALIZED,
    )
    audit.case()
    if exact_preservation_forgery_rejected:
        audit.reject()

    audit.require(
        unproved_forgery_rejected,
        "lost_isolation_proof_revalidated_at_finalization",
    )
    audit.require(
        effective_forgery_rejected,
        "lost_pending_closure_shape_exact",
    )
    audit.require(
        exact_preservation_forgery_rejected,
        "exact_terminal_hold_preservation_revalidated",
    )
    audit.witness(
        "retirement_finalization_revalidates_closure_evidence",
        unproved_forgery_rejected
        and effective_forgery_rejected
        and exact_preservation_forgery_rejected,
    )


@dataclass(frozen=True)
class ActuationAuthorityDomainBinding:
    """One generation's scalar actuation-domain and arbiter-mirror binding."""

    session_id: str
    generation_id: str
    generation_domain_keys: tuple[str, ...]
    arbiter_mirror_domain_key: str
    actuator_domain_keys: tuple[str, ...]
    atomic_success_claimed: bool
    qualified_atomic_boundary: bool


def _actuation_domain_binding_is_exact(value: object) -> bool:
    return (
        type(value) is ActuationAuthorityDomainBinding
        and _exact_nonempty_str(value.session_id)
        and _exact_nonempty_str(value.generation_id)
        and _exact_tuple_of(
            value.generation_domain_keys,
            _exact_nonempty_str,
        )
        and _exact_nonempty_str(value.arbiter_mirror_domain_key)
        and _exact_tuple_of(
            value.actuator_domain_keys,
            _exact_nonempty_str,
            nonempty=True,
        )
        and _exact_bool(value.atomic_success_claimed)
        and _exact_bool(value.qualified_atomic_boundary)
    )


UNKNOWN_OR_DEFAULT_IDENTIFIERS = frozenset(
    {"0", "DEFAULT", "NONE", "UNKNOWN", "UNSPECIFIED"}
)
MAX_AUTHORITY_IDENTIFIER_BYTES = 256
MAX_ACTUATORS_PER_DOMAIN = 8


def _closed_digest(value: object) -> bool:
    """Accept one non-default lowercase SHA-256 value."""

    return (
        type(value) is str
        and value != "0" * 64
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _closed_authority_identifier(value: object) -> bool:
    """Accept one bounded, explicit ASCII authority identifier."""

    return (
        type(value) is str
        and 1 <= len(value.encode("utf-8")) <= MAX_AUTHORITY_IDENTIFIER_BYTES
        and value == value.strip()
        and value.upper() not in UNKNOWN_OR_DEFAULT_IDENTIFIERS
        and all(0x20 <= ord(character) <= 0x7E for character in value)
    )


class ActuationDomainBindingModel:
    """Reject distributed atomicity disguised as one body generation."""

    def __init__(self, mutation: str | None) -> None:
        self.mutation = _validate_mutation_selector(mutation)

    def _domain_key_is_closed(self, value: str) -> bool:
        if (
            self.mutation == "actuation_domain_key_unknown_default"
            and value == "UNKNOWN"
        ):
            return True
        return _closed_digest(value)

    def accepts(self, binding: ActuationAuthorityDomainBinding) -> bool:
        """Validate one scalar mirror against the generation's sole domain."""

        binding_shape_is_exact = _actuation_domain_binding_is_exact(binding)
        if self.mutation == "actuation_binding_subclass_authorized" and isinstance(
            binding, ActuationAuthorityDomainBinding
        ):
            binding_shape_is_exact = (
                _exact_nonempty_str(binding.session_id)
                and _exact_nonempty_str(binding.generation_id)
                and _exact_tuple_of(
                    binding.generation_domain_keys,
                    _exact_nonempty_str,
                )
                and _exact_nonempty_str(binding.arbiter_mirror_domain_key)
                and _exact_tuple_of(
                    binding.actuator_domain_keys,
                    _exact_nonempty_str,
                    nonempty=True,
                )
                and _exact_bool(binding.atomic_success_claimed)
                and _exact_bool(binding.qualified_atomic_boundary)
            )
        if not binding_shape_is_exact:
            return False
        domain_count = len(binding.generation_domain_keys)
        if domain_count != 1:
            zero_bypass = (
                domain_count == 0
                and self.mutation == "generation_without_actuation_domain"
            )
            multiple_bypass = (
                domain_count > 1
                and self.mutation == "generation_with_multiple_actuation_domains"
            )
            if not (zero_bypass or multiple_bypass):
                return False
            selected_domain = binding.arbiter_mirror_domain_key
        else:
            selected_domain = binding.generation_domain_keys[0]
        if (
            not self._domain_key_is_closed(selected_domain)
            or not self._domain_key_is_closed(binding.arbiter_mirror_domain_key)
            or not (
                1 <= len(binding.actuator_domain_keys) <= MAX_ACTUATORS_PER_DOMAIN
                or self.mutation == "actuation_domain_actuator_set_unbounded"
            )
            or not all(
                self._domain_key_is_closed(domain_key)
                for domain_key in binding.actuator_domain_keys
            )
        ):
            return False
        if (
            binding.arbiter_mirror_domain_key != selected_domain
            and self.mutation != "arbiter_mirror_cross_domain"
        ):
            return False
        if (
            any(
                domain_key != selected_domain
                for domain_key in binding.actuator_domain_keys
            )
            and self.mutation != "cross_domain_atomic_success"
        ):
            return False
        if (
            len(binding.actuator_domain_keys) > 1
            and binding.qualified_atomic_boundary
            and self.mutation == "same_domain_multi_actuator_rejected"
        ):
            return False
        if len(binding.actuator_domain_keys) > 1 and not (
            binding.atomic_success_claimed and binding.qualified_atomic_boundary
        ):
            return False
        return _closed_authority_identifier(
            binding.session_id
        ) and _closed_authority_identifier(binding.generation_id)

    def independent_domains_are_session_isolated(
        self,
        bindings: tuple[ActuationAuthorityDomainBinding, ...],
    ) -> bool:
        """Require distinct sessions whenever the domain keys are distinct."""

        if not _exact_tuple_of(
            bindings,
            lambda binding: (
                type(binding) is ActuationAuthorityDomainBinding
                or (
                    self.mutation == "actuation_binding_subclass_authorized"
                    and isinstance(binding, ActuationAuthorityDomainBinding)
                )
            ),
            nonempty=True,
        ) or not all(self.accepts(binding) for binding in bindings):
            return False
        domain_keys = {binding.generation_domain_keys[0] for binding in bindings}
        if len(domain_keys) <= 1:
            return True
        session_ids = {binding.session_id for binding in bindings}
        return (
            len(session_ids) == len(bindings)
            or self.mutation == "independent_domains_share_session"
        )


@dataclass(frozen=True)
class ActuationEffectFootprint:
    """Complete enrolled physical-effect footprint for one authority domain."""

    active: tuple[str, ...]
    hold: tuple[str, ...]
    estop: tuple[str, ...]
    watchdog: tuple[str, ...]
    interlock: tuple[str, ...]
    reset: tuple[str, ...]
    shared_bus: tuple[str, ...]

    CHANNELS = (
        "active",
        "hold",
        "estop",
        "watchdog",
        "interlock",
        "reset",
        "shared_bus",
    )

    def resources(self, *, omitted_channel: str | None = None) -> frozenset[str]:
        """Flatten every non-omitted channel into one global conflict domain."""

        if omitted_channel is not None and (
            type(omitted_channel) is not str or omitted_channel not in self.CHANNELS
        ):
            raise ProbeError("omitted effect channel is not an exact closed value")
        if not self.complete():
            return frozenset()
        return frozenset(
            resource
            for channel in self.CHANNELS
            if channel != omitted_channel
            for resource in getattr(self, channel)
        )

    def complete(self) -> bool:
        """Require every authority-relevant effect channel to be enrolled."""

        return type(self) is ActuationEffectFootprint and all(
            type(getattr(self, channel)) is tuple
            and 1 <= len(getattr(self, channel)) <= 8
            and all(
                _closed_authority_identifier(resource)
                for resource in getattr(self, channel)
            )
            for channel in self.CHANNELS
        )


@dataclass(frozen=True)
class ActuationAuthorityDomainCreationReceipt:
    """Registry-owned creation receipt; callers cannot select another key."""

    domain_key: str
    body_principal: str
    session_id: str
    generation_id: str
    jurisdiction_key: str
    jurisdiction_incarnation: str
    topology_digest: str
    prior_selector_version: int


@dataclass(frozen=True)
class ActuationAuthorityDomainRegistration:
    """One domain entry in the installed global registry selector."""

    domain_key: str
    body_principal: str
    session_id: str
    generation_id: str
    jurisdiction_key: str
    jurisdiction_incarnation: str
    topology_digest: str
    footprint: ActuationEffectFootprint
    creation_receipt: ActuationAuthorityDomainCreationReceipt


def _creation_receipt_fields_are_exact(
    value: ActuationAuthorityDomainCreationReceipt,
    *,
    allow_prior_boolean: bool = False,
) -> bool:
    return (
        _exact_nonempty_str(value.domain_key)
        and _exact_nonempty_str(value.body_principal)
        and _exact_nonempty_str(value.session_id)
        and _exact_nonempty_str(value.generation_id)
        and _exact_nonempty_str(value.jurisdiction_key)
        and _exact_nonempty_str(value.jurisdiction_incarnation)
        and _exact_nonempty_str(value.topology_digest)
        and (
            _exact_int(value.prior_selector_version)
            or (allow_prior_boolean and type(value.prior_selector_version) is bool)
        )
    )


def _creation_receipt_is_exact(value: object) -> bool:
    return type(
        value
    ) is ActuationAuthorityDomainCreationReceipt and _creation_receipt_fields_are_exact(
        value
    )


def _footprint_fields_are_exact(value: ActuationEffectFootprint) -> bool:
    return all(
        type(getattr(value, channel)) is tuple
        and all(_exact_nonempty_str(resource) for resource in getattr(value, channel))
        for channel in ActuationEffectFootprint.CHANNELS
    )


def _footprint_fields_are_closed(value: ActuationEffectFootprint) -> bool:
    return _footprint_fields_are_exact(value) and all(
        1 <= len(getattr(value, channel)) <= 8
        and all(
            _closed_authority_identifier(resource)
            for resource in getattr(value, channel)
        )
        for channel in ActuationEffectFootprint.CHANNELS
    )


def _registration_fields_are_exact(
    value: ActuationAuthorityDomainRegistration,
    *,
    allow_subclasses: bool = False,
    allow_prior_boolean: bool = False,
) -> bool:
    footprint_type_ok = (
        isinstance(value.footprint, ActuationEffectFootprint)
        if allow_subclasses
        else type(value.footprint) is ActuationEffectFootprint
    )
    receipt_type_ok = (
        isinstance(
            value.creation_receipt,
            ActuationAuthorityDomainCreationReceipt,
        )
        if allow_subclasses
        else type(value.creation_receipt) is ActuationAuthorityDomainCreationReceipt
    )
    return (
        _exact_nonempty_str(value.domain_key)
        and _exact_nonempty_str(value.body_principal)
        and _exact_nonempty_str(value.session_id)
        and _exact_nonempty_str(value.generation_id)
        and _exact_nonempty_str(value.jurisdiction_key)
        and _exact_nonempty_str(value.jurisdiction_incarnation)
        and _exact_nonempty_str(value.topology_digest)
        and footprint_type_ok
        and _footprint_fields_are_exact(value.footprint)
        and receipt_type_ok
        and _creation_receipt_fields_are_exact(
            value.creation_receipt,
            allow_prior_boolean=allow_prior_boolean,
        )
    )


def _registration_is_exact(value: object) -> bool:
    return type(
        value
    ) is ActuationAuthorityDomainRegistration and _registration_fields_are_exact(value)


PHYSICAL_ACTUATION_JURISDICTION_KEY = hashlib.sha256(
    b"synthetic-physical-actuation-jurisdiction"
).hexdigest()
PHYSICAL_ACTUATION_JURISDICTION_INCARNATION = (
    "synthetic-physical-actuation-jurisdiction-incarnation-a"
)
PHYSICAL_ACTUATION_TOPOLOGY_DIGEST = hashlib.sha256(
    b"synthetic-physical-actuation-topology-a"
).hexdigest()


class InstalledActuationAuthorityDomainSelector:
    """One bounded global registry map and enrolled physical conflict graph."""

    MAX_DOMAINS = 4

    def __init__(
        self,
        mutation: str | None,
        *,
        jurisdiction_key: str = PHYSICAL_ACTUATION_JURISDICTION_KEY,
        jurisdiction_incarnation: str = (PHYSICAL_ACTUATION_JURISDICTION_INCARNATION),
        topology_digest: str = PHYSICAL_ACTUATION_TOPOLOGY_DIGEST,
    ) -> None:
        self.mutation = _validate_mutation_selector(mutation)
        self.jurisdiction_key = jurisdiction_key
        self.jurisdiction_incarnation = jurisdiction_incarnation
        self.topology_digest = topology_digest
        self.scope_types_are_exact = (
            type(jurisdiction_key) is str
            and type(jurisdiction_incarnation) is str
            and type(topology_digest) is str
        )
        self.version = 0
        self.topology_revision = 0
        self.registry: dict[str, ActuationAuthorityDomainRegistration] = {}
        self._registration_order: list[str] = []
        self.generation_owner: dict[tuple[str, str], str] = {}
        self.conflict_graph: set[frozenset[str]] = set()
        self.reserved_domain_keys: set[str] = set()

    def _state_is_exact(self) -> bool:
        current_scope_types_are_exact = (
            type(self.jurisdiction_key) is str
            and type(self.jurisdiction_incarnation) is str
            and type(self.topology_digest) is str
        )
        scope_is_closed = (
            _closed_digest(self.jurisdiction_key)
            and _closed_authority_identifier(self.jurisdiction_incarnation)
            and _closed_digest(self.topology_digest)
        )
        if self.mutation == "selector_scope_cache_trusted":
            scope_is_closed = self.scope_types_are_exact
        structurally_exact = (
            current_scope_types_are_exact
            and self.scope_types_are_exact == current_scope_types_are_exact
            and scope_is_closed
            and _exact_nonnegative_int(self.version)
            and _exact_nonnegative_int(self.topology_revision)
            and type(self.registry) is dict
            and all(
                _closed_digest(domain_key)
                and _registration_is_exact(registration)
                and registration.domain_key == domain_key
                for domain_key, registration in self.registry.items()
            )
            and type(self._registration_order) is list
            and all(
                _closed_digest(domain_key) for domain_key in self._registration_order
            )
            and type(self.generation_owner) is dict
            and all(
                _exact_tuple_of(
                    owner,
                    _closed_authority_identifier,
                )
                and len(owner) == 2
                and _closed_digest(domain_key)
                for owner, domain_key in self.generation_owner.items()
            )
            and type(self.conflict_graph) is set
            and all(
                _exact_frozenset_of(edge, _closed_digest) and 1 <= len(edge) <= 2
                for edge in self.conflict_graph
            )
            and type(self.reserved_domain_keys) is set
            and all(
                _closed_digest(domain_key) for domain_key in self.reserved_domain_keys
            )
        )
        if not structurally_exact:
            scope_semantic_mutation = (
                (
                    self.mutation == "physical_jurisdiction_key_unknown_default"
                    and type(self.jurisdiction_key) is str
                )
                or (
                    self.mutation == "jurisdiction_incarnation_unknown_default"
                    and type(self.jurisdiction_incarnation) is str
                )
                or (
                    self.mutation == "physical_topology_digest_unknown_default"
                    and type(self.topology_digest) is str
                )
            )
            if not scope_semantic_mutation:
                return False
            structurally_exact = (
                current_scope_types_are_exact
                and self.scope_types_are_exact == current_scope_types_are_exact
                and _exact_nonnegative_int(self.version)
                and _exact_nonnegative_int(self.topology_revision)
                and type(self.registry) is dict
                and not self.registry
                and type(self._registration_order) is list
                and not self._registration_order
                and type(self.generation_owner) is dict
                and not self.generation_owner
                and type(self.conflict_graph) is set
                and not self.conflict_graph
                and type(self.reserved_domain_keys) is set
                and not self.reserved_domain_keys
            )
        if not structurally_exact:
            return False
        if self.mutation == "selector_derived_state_unchecked":
            return True

        if self._registration_order != list(self.registry):
            return False
        expected_generation_owner = {
            (registration.session_id, registration.generation_id): domain_key
            for domain_key, registration in self.registry.items()
        }
        if self.generation_owner != expected_generation_owner:
            return False
        if len(self.generation_owner) != len(self.registry):
            return False
        if any(
            not registration.footprint.complete()
            or registration.domain_key != domain_key
            or (
                self.mutation != "selector_scope_cache_trusted"
                and (
                    registration.jurisdiction_key != self.jurisdiction_key
                    or registration.jurisdiction_incarnation
                    != self.jurisdiction_incarnation
                    or registration.topology_digest != self.topology_digest
                )
            )
            or registration.creation_receipt.domain_key != domain_key
            or registration.creation_receipt.body_principal
            != registration.body_principal
            or registration.creation_receipt.session_id != registration.session_id
            or registration.creation_receipt.generation_id != registration.generation_id
            or registration.creation_receipt.jurisdiction_key
            != registration.jurisdiction_key
            or registration.creation_receipt.jurisdiction_incarnation
            != registration.jurisdiction_incarnation
            or registration.creation_receipt.topology_digest
            != registration.topology_digest
            for domain_key, registration in self.registry.items()
        ):
            return False
        expected_conflict_graph: set[frozenset[str]] = set()
        registrations = list(self.registry.items())
        for index, (domain_key, registration) in enumerate(registrations):
            resources = registration.footprint.resources()
            for other_domain_key, other_registration in registrations[index + 1 :]:
                if resources.intersection(other_registration.footprint.resources()):
                    expected_conflict_graph.add(
                        frozenset({domain_key, other_domain_key})
                    )
        if self.conflict_graph != expected_conflict_graph:
            return False
        if (
            not self.reserved_domain_keys.issubset(self.registry)
            or any(
                edge.issubset(self.reserved_domain_keys) for edge in self.conflict_graph
            )
            or self.version
            != len(self.registry)
            + len(self.reserved_domain_keys)
            + self.topology_revision
        ):
            return False
        return True

    def register(self, registration: ActuationAuthorityDomainRegistration) -> bool:
        """Atomically install one entry and its complete derived conflict edges."""

        if not self._state_is_exact():
            return False
        registration_shape_is_exact = _registration_is_exact(registration)
        if (
            self.mutation == "receipt_prior_version_boolean_default"
            and type(registration) is ActuationAuthorityDomainRegistration
        ):
            registration_shape_is_exact = _registration_fields_are_exact(
                registration,
                allow_prior_boolean=True,
            )
        if self.mutation == "actuation_registration_subclass_authorized" and isinstance(
            registration, ActuationAuthorityDomainRegistration
        ):
            registration_shape_is_exact = _registration_fields_are_exact(
                registration,
                allow_subclasses=True,
            )
        if (
            not registration_shape_is_exact
            or not self.scope_types_are_exact
            or not _closed_digest(registration.domain_key)
            or (
                not _closed_authority_identifier(registration.body_principal)
                and self.mutation != "domain_body_principal_unknown_default"
            )
            or (
                not _closed_authority_identifier(registration.session_id)
                and self.mutation != "domain_session_id_unknown_default"
            )
            or (
                not _closed_authority_identifier(registration.generation_id)
                and self.mutation != "domain_generation_id_unknown_default"
            )
            or (
                (
                    not _closed_digest(registration.jurisdiction_key)
                    or not _closed_digest(self.jurisdiction_key)
                )
                and self.mutation
                not in {
                    "physical_jurisdiction_key_unknown_default",
                    "selector_scope_cache_trusted",
                }
            )
            or (
                (
                    not _closed_authority_identifier(
                        registration.jurisdiction_incarnation
                    )
                    or not _closed_authority_identifier(self.jurisdiction_incarnation)
                )
                and self.mutation
                not in {
                    "jurisdiction_incarnation_unknown_default",
                    "selector_scope_cache_trusted",
                }
            )
            or (
                (
                    not _closed_digest(registration.topology_digest)
                    or not _closed_digest(self.topology_digest)
                )
                and self.mutation
                not in {
                    "physical_topology_digest_unknown_default",
                    "selector_scope_cache_trusted",
                }
            )
            or (
                (
                    type(registration.creation_receipt.prior_selector_version)
                    is not int
                    or registration.creation_receipt.prior_selector_version < 0
                )
                and self.mutation != "receipt_prior_version_boolean_default"
            )
            or registration.domain_key in self.registry
            or registration.creation_receipt.domain_key != registration.domain_key
            or registration.creation_receipt.body_principal
            != registration.body_principal
            or registration.creation_receipt.session_id != registration.session_id
            or registration.creation_receipt.generation_id != registration.generation_id
            or registration.creation_receipt.jurisdiction_key
            != registration.jurisdiction_key
            or registration.creation_receipt.jurisdiction_incarnation
            != registration.jurisdiction_incarnation
            or registration.creation_receipt.topology_digest
            != registration.topology_digest
            or registration.creation_receipt.prior_selector_version != self.version
        ):
            return False
        if (
            registration.jurisdiction_key != self.jurisdiction_key
            and self.mutation
            not in {
                "wrong_physical_jurisdiction_enrolled",
                "selector_scope_cache_trusted",
            }
        ):
            return False
        if (
            registration.jurisdiction_incarnation != self.jurisdiction_incarnation
            and self.mutation
            not in {
                "wrong_jurisdiction_incarnation_enrolled",
                "selector_scope_cache_trusted",
            }
        ):
            return False
        if (
            registration.topology_digest != self.topology_digest
            and self.mutation != "selector_scope_cache_trusted"
        ):
            return False
        footprint_complete = registration.footprint.complete()
        if self.mutation == "actuation_registration_subclass_authorized":
            footprint_complete = _footprint_fields_are_closed(registration.footprint)
        if not footprint_complete and self.mutation not in {
            "incomplete_effect_footprint_accepted",
            "effect_footprint_resource_unknown_default",
        }:
            return False
        if (
            len(self.registry) >= self.MAX_DOMAINS
            and self.mutation != "domain_registry_unbounded"
        ):
            return False
        owner_key = (registration.session_id, registration.generation_id)
        if (
            owner_key in self.generation_owner
            and self.mutation != "registry_allows_generation_domain_rebind"
        ):
            return False

        omitted_channel = None
        for channel in ActuationEffectFootprint.CHANNELS:
            if self.mutation == f"conflict_graph_omits_{channel}":
                omitted_channel = channel
                break
        new_resources = registration.footprint.resources(
            omitted_channel=omitted_channel
        )
        for existing in self.registry.values():
            if (
                self.mutation == "conflict_graph_scoped_per_body"
                and existing.body_principal != registration.body_principal
            ):
                continue
            existing_resources = existing.footprint.resources(
                omitted_channel=omitted_channel
            )
            if new_resources.intersection(existing_resources):
                self.conflict_graph.add(
                    frozenset({registration.domain_key, existing.domain_key})
                )
        self.registry[registration.domain_key] = registration
        self._registration_order.append(registration.domain_key)
        self.generation_owner[owner_key] = registration.domain_key
        self.version += 1
        return True

    def reserve(
        self,
        *,
        requested_domain_key: str,
        creation_receipt: ActuationAuthorityDomainCreationReceipt,
        expected_selector_version: int,
    ) -> bool:
        """Serialize reservation and reject any enrolled footprint conflict."""

        if (
            not self._state_is_exact()
            or not _closed_digest(requested_domain_key)
            or not _creation_receipt_is_exact(creation_receipt)
            or not _exact_int(expected_selector_version)
            or expected_selector_version < 0
        ):
            return False
        if (
            expected_selector_version != self.version
            and self.mutation != "domain_selector_cas_ignored"
        ):
            return False
        registration = self.registry.get(requested_domain_key)
        if registration is None:
            return False
        receipt_matches = creation_receipt is registration.creation_receipt
        if self.mutation == "caller_selected_domain_substitution":
            receipt_matches = True
        elif self.mutation == "equal_creation_receipt_authorized":
            receipt_matches = creation_receipt == registration.creation_receipt
        if not receipt_matches:
            return False
        conflicts = any(
            frozenset({requested_domain_key, reserved_domain_key})
            in self.conflict_graph
            for reserved_domain_key in self.reserved_domain_keys
        )
        if self.mutation == "disjoint_domains_conflict" and self.reserved_domain_keys:
            conflicts = True
        if requested_domain_key in self.reserved_domain_keys or conflicts:
            return False
        self.reserved_domain_keys.add(requested_domain_key)
        self.version += 1
        return True

    def replace_topology(
        self,
        *,
        new_topology_digest: str,
        fenced_domain_keys: frozenset[str],
        physical_isolation_proved: bool,
        replacement_registrations: tuple[ActuationAuthorityDomainRegistration, ...],
    ) -> bool:
        """Replace topology only through a complete physical ownership cut."""

        if (
            not self._state_is_exact()
            or type(new_topology_digest) is not str
            or not _exact_frozenset_of(fenced_domain_keys, _closed_digest)
            or not _exact_bool(physical_isolation_proved)
            or not _exact_tuple_of(
                replacement_registrations,
                _registration_is_exact,
            )
        ):
            return False
        if (
            not _closed_digest(new_topology_digest)
            and self.mutation != "physical_topology_digest_unknown_default"
        ):
            return False
        old_scopes = {
            (
                registration.body_principal,
                registration.session_id,
                registration.generation_id,
            )
            for registration in self.registry.values()
        }
        if (
            fenced_domain_keys != frozenset(self.registry)
            and self.mutation != "topology_change_without_full_fence"
        ):
            return False
        if (
            not physical_isolation_proved
            and self.mutation != "topology_change_without_physical_isolation"
        ):
            return False
        replacement_scopes = {
            (
                registration.body_principal,
                registration.session_id,
                registration.generation_id,
            )
            for registration in replacement_registrations
        }
        if (
            not replacement_registrations
            or replacement_scopes != old_scopes
            or any(
                registration.topology_digest != new_topology_digest
                for registration in replacement_registrations
            )
        ) and self.mutation != "topology_change_without_reenrollment":
            return False

        replacement = InstalledActuationAuthorityDomainSelector(
            self.mutation,
            jurisdiction_key=self.jurisdiction_key,
            jurisdiction_incarnation=self.jurisdiction_incarnation,
            topology_digest=new_topology_digest,
        )
        if replacement_registrations and not all(
            replacement.register(registration)
            for registration in replacement_registrations
        ):
            return False
        self.topology_digest = new_topology_digest
        self.registry = replacement.registry
        self._registration_order = replacement._registration_order
        self.generation_owner = replacement.generation_owner
        self.conflict_graph = replacement.conflict_graph
        self.reserved_domain_keys = set()
        self.topology_revision += 1
        self.version = len(self.registry) + self.topology_revision
        return True


class InstalledPhysicalActuationJurisdictionDirectory:
    """Admit one live selector for each jurisdiction key/incarnation pair."""

    def __init__(self, mutation: str | None) -> None:
        self.mutation = _validate_mutation_selector(mutation)
        self.live_selectors: dict[tuple[str, str], str] = {}

    def enroll(
        self,
        *,
        selector_id: str,
        jurisdiction_key: str,
        jurisdiction_incarnation: str,
    ) -> bool:
        """Reject a second live selector for the same physical jurisdiction."""

        if type(self.live_selectors) is not dict or not all(
            type(selector_scope) is tuple
            and len(selector_scope) == 2
            and _closed_digest(selector_scope[0])
            and _closed_authority_identifier(selector_scope[1])
            and _closed_authority_identifier(selector_id)
            for selector_scope, selector_id in self.live_selectors.items()
        ):
            return False
        selector_key = (jurisdiction_key, jurisdiction_incarnation)
        if (
            (
                not _closed_authority_identifier(selector_id)
                and self.mutation != "jurisdiction_selector_id_unknown_default"
            )
            or (
                not _closed_digest(jurisdiction_key)
                and self.mutation != "physical_jurisdiction_key_unknown_default"
            )
            or (
                not _closed_authority_identifier(jurisdiction_incarnation)
                and self.mutation != "jurisdiction_incarnation_unknown_default"
            )
        ):
            return False
        if (
            selector_key in self.live_selectors
            and self.mutation != "duplicate_live_jurisdiction_selector"
        ):
            return False
        if (
            any(
                live_jurisdiction_key == jurisdiction_key
                and live_incarnation != jurisdiction_incarnation
                for live_jurisdiction_key, live_incarnation in self.live_selectors
            )
            and self.mutation != "concurrent_jurisdiction_incarnations"
        ):
            return False
        self.live_selectors[selector_key] = selector_id
        return True


def _effect_footprint(
    prefix: str,
    *,
    overlap_channel: str | None = None,
    shared_resource: str | None = None,
) -> ActuationEffectFootprint:
    """Create a complete footprint with at most one deliberate overlap."""

    members = {
        channel: (f"{prefix}:{channel}",)
        for channel in ActuationEffectFootprint.CHANNELS
    }
    if overlap_channel is not None:
        if shared_resource is None:
            raise ProbeError("overlap channel lacks its shared resource")
        members[overlap_channel] = (shared_resource,)
    return ActuationEffectFootprint(**members)


def _domain_registration(
    *,
    domain_key: str,
    session_id: str,
    generation_id: str,
    footprint: ActuationEffectFootprint,
    prior_selector_version: int,
    body_principal: str | None = None,
    jurisdiction_key: str = PHYSICAL_ACTUATION_JURISDICTION_KEY,
    jurisdiction_incarnation: str = (PHYSICAL_ACTUATION_JURISDICTION_INCARNATION),
    topology_digest: str = PHYSICAL_ACTUATION_TOPOLOGY_DIGEST,
) -> ActuationAuthorityDomainRegistration:
    """Construct a registration and registry-bound creation receipt."""

    return ActuationAuthorityDomainRegistration(
        domain_key=domain_key,
        body_principal=(
            f"body:{session_id}" if body_principal is None else body_principal
        ),
        session_id=session_id,
        generation_id=generation_id,
        jurisdiction_key=jurisdiction_key,
        jurisdiction_incarnation=jurisdiction_incarnation,
        topology_digest=topology_digest,
        footprint=footprint,
        creation_receipt=ActuationAuthorityDomainCreationReceipt(
            domain_key=domain_key,
            body_principal=(
                f"body:{session_id}" if body_principal is None else body_principal
            ),
            session_id=session_id,
            generation_id=generation_id,
            jurisdiction_key=jurisdiction_key,
            jurisdiction_incarnation=jurisdiction_incarnation,
            topology_digest=topology_digest,
            prior_selector_version=prior_selector_version,
        ),
    )


def _campaign_actuation_domain_binding(model: Model, audit: Audit) -> None:
    """Challenge exact-one domains, scalar mirrors, and atomicity scope."""

    domain_model = ActuationDomainBindingModel(model.mutation)
    domain_a = hashlib.sha256(b"qualified-actuation-domain-a").hexdigest()
    domain_b = hashlib.sha256(b"qualified-actuation-domain-b").hexdigest()
    valid_single = ActuationAuthorityDomainBinding(
        session_id="session-a",
        generation_id="generation-a",
        generation_domain_keys=(domain_a,),
        arbiter_mirror_domain_key=domain_a,
        actuator_domain_keys=(domain_a,),
        atomic_success_claimed=True,
        qualified_atomic_boundary=True,
    )
    single_accepted = domain_model.accepts(valid_single)
    audit.case()
    audit.require(
        single_accepted,
        "generation_has_exactly_one_actuation_domain",
    )

    valid_atomic_multi = ActuationAuthorityDomainBinding(
        session_id="session-a",
        generation_id="generation-a",
        generation_domain_keys=(domain_a,),
        arbiter_mirror_domain_key=domain_a,
        actuator_domain_keys=(domain_a, domain_a),
        atomic_success_claimed=True,
        qualified_atomic_boundary=True,
    )
    qualified_multi_accepted = domain_model.accepts(valid_atomic_multi)
    audit.case()
    audit.require(
        qualified_multi_accepted,
        "qualified_multi_actuator_domain_permitted",
    )

    unbounded_actuator_binding = ActuationAuthorityDomainBinding(
        **{
            **valid_atomic_multi.__dict__,
            "actuator_domain_keys": (domain_a,) * (MAX_ACTUATORS_PER_DOMAIN + 1),
        }
    )
    unbounded_actuator_set_rejected = not domain_model.accepts(
        unbounded_actuator_binding
    )
    audit.case()
    if unbounded_actuator_set_rejected:
        audit.reject()
    audit.require(
        unbounded_actuator_set_rejected,
        "actuation_domain_cardinality_bounded",
    )

    hostile_bindings = {
        "zero": ActuationAuthorityDomainBinding(
            **{
                **valid_single.__dict__,
                "generation_domain_keys": (),
            }
        ),
        "multiple": ActuationAuthorityDomainBinding(
            **{
                **valid_single.__dict__,
                "generation_domain_keys": (domain_a, domain_b),
            }
        ),
        "mirror": ActuationAuthorityDomainBinding(
            **{
                **valid_single.__dict__,
                "arbiter_mirror_domain_key": domain_b,
            }
        ),
        "cross_atomic": ActuationAuthorityDomainBinding(
            **{
                **valid_atomic_multi.__dict__,
                "actuator_domain_keys": (domain_a, domain_b),
            }
        ),
        "unknown": ActuationAuthorityDomainBinding(
            **{
                **valid_single.__dict__,
                "generation_domain_keys": ("UNKNOWN",),
                "arbiter_mirror_domain_key": "UNKNOWN",
                "actuator_domain_keys": ("UNKNOWN",),
            }
        ),
    }
    hostile_rejected: dict[str, bool] = {}
    for name, binding in hostile_bindings.items():
        rejected = not domain_model.accepts(binding)
        hostile_rejected[name] = rejected
        audit.case()
        if rejected:
            audit.reject()

    audit.require(
        hostile_rejected["zero"] and hostile_rejected["multiple"],
        "generation_has_exactly_one_actuation_domain",
    )
    audit.require(
        hostile_rejected["mirror"],
        "arbiter_mirror_matches_generation_domain",
    )
    audit.require(
        hostile_rejected["cross_atomic"],
        "atomic_success_stays_within_one_domain",
    )
    audit.require(
        hostile_rejected["unknown"],
        "actuation_domain_key_closed",
    )

    second_session_domain = ActuationAuthorityDomainBinding(
        session_id="session-b",
        generation_id="generation-b",
        generation_domain_keys=(domain_b,),
        arbiter_mirror_domain_key=domain_b,
        actuator_domain_keys=(domain_b,),
        atomic_success_claimed=True,
        qualified_atomic_boundary=True,
    )
    distinct_sessions_accepted = domain_model.independent_domains_are_session_isolated(
        (valid_single, second_session_domain)
    )
    audit.case()
    same_session_domain = ActuationAuthorityDomainBinding(
        **{
            **second_session_domain.__dict__,
            "session_id": valid_single.session_id,
        }
    )
    same_session_rejected = not domain_model.independent_domains_are_session_isolated(
        (valid_single, same_session_domain)
    )
    audit.case()
    if same_session_rejected:
        audit.reject()
    session_isolation = distinct_sessions_accepted and same_session_rejected
    audit.require(
        session_isolation,
        "independent_domains_require_independent_sessions",
    )

    audit.witness(
        "generation_binds_one_domain_and_one_scalar_mirror",
        single_accepted
        and hostile_rejected["zero"]
        and hostile_rejected["multiple"]
        and hostile_rejected["mirror"],
    )
    audit.witness(
        "qualified_domain_can_contain_multiple_atomic_actuators",
        qualified_multi_accepted,
    )
    audit.witness(
        "actuation_domain_cardinality_is_bounded",
        qualified_multi_accepted and unbounded_actuator_set_rejected,
    )
    audit.witness(
        "cross_domain_atomic_success_rejects",
        hostile_rejected["cross_atomic"],
    )
    audit.witness(
        "independent_domains_use_independent_sessions",
        session_isolation,
    )

    conflict_rejections: dict[str, bool] = {}
    for channel in ActuationEffectFootprint.CHANNELS:
        selector = InstalledActuationAuthorityDomainSelector(model.mutation)
        channel_domain_a = hashlib.sha256(
            f"registry-{channel}-domain-a".encode()
        ).hexdigest()
        channel_domain_b = hashlib.sha256(
            f"registry-{channel}-domain-b".encode()
        ).hexdigest()
        footprint_a = _effect_footprint(f"registry-{channel}-a")
        shared_resource = getattr(footprint_a, channel)[0]
        footprint_b = _effect_footprint(
            f"registry-{channel}-b",
            overlap_channel=channel,
            shared_resource=shared_resource,
        )
        registration_a = _domain_registration(
            domain_key=channel_domain_a,
            session_id=f"registry-{channel}-session-a",
            generation_id=f"registry-{channel}-generation-a",
            footprint=footprint_a,
            prior_selector_version=0,
        )
        registration_b = _domain_registration(
            domain_key=channel_domain_b,
            session_id=f"registry-{channel}-session-b",
            generation_id=f"registry-{channel}-generation-b",
            footprint=footprint_b,
            prior_selector_version=1,
        )
        registered = selector.register(registration_a) and selector.register(
            registration_b
        )
        first_reserved = registered and selector.reserve(
            requested_domain_key=channel_domain_a,
            creation_receipt=registration_a.creation_receipt,
            expected_selector_version=2,
        )
        second_reserved = selector.reserve(
            requested_domain_key=channel_domain_b,
            creation_receipt=registration_b.creation_receipt,
            expected_selector_version=3,
        )
        conflict_pair = frozenset({channel_domain_a, channel_domain_b})
        rejected = (
            registered
            and first_reserved
            and not second_reserved
            and conflict_pair in selector.conflict_graph
        )
        conflict_rejections[channel] = rejected
        audit.case()
        if not second_reserved:
            audit.reject()
        audit.require(rejected, f"conflict_graph_covers_{channel}")
    all_cross_body_conflicts_rejected = all(conflict_rejections.values())
    audit.require(
        all_cross_body_conflicts_rejected,
        "global_conflicts_span_body_principals",
    )

    cas_selector = InstalledActuationAuthorityDomainSelector(model.mutation)
    cas_domain_a = hashlib.sha256(b"cas-disjoint-domain-a").hexdigest()
    cas_domain_b = hashlib.sha256(b"cas-disjoint-domain-b").hexdigest()
    cas_registration_a = _domain_registration(
        domain_key=cas_domain_a,
        session_id="cas-session-a",
        generation_id="cas-generation-a",
        footprint=_effect_footprint("cas-a"),
        prior_selector_version=0,
    )
    cas_registration_b = _domain_registration(
        domain_key=cas_domain_b,
        session_id="cas-session-b",
        generation_id="cas-generation-b",
        footprint=_effect_footprint("cas-b"),
        prior_selector_version=1,
    )
    cas_registered = cas_selector.register(
        cas_registration_a
    ) and cas_selector.register(cas_registration_b)
    common_prior_version = cas_selector.version
    cas_first = cas_registered and cas_selector.reserve(
        requested_domain_key=cas_domain_a,
        creation_receipt=cas_registration_a.creation_receipt,
        expected_selector_version=common_prior_version,
    )
    cas_second = cas_selector.reserve(
        requested_domain_key=cas_domain_b,
        creation_receipt=cas_registration_b.creation_receipt,
        expected_selector_version=common_prior_version,
    )
    cas_serialized = cas_first and not cas_second
    audit.case()
    if not cas_second:
        audit.reject()
    audit.require(cas_serialized, "global_domain_selector_serializes")

    disjoint_selector = InstalledActuationAuthorityDomainSelector(model.mutation)
    disjoint_registration_a = _domain_registration(
        domain_key=domain_a,
        session_id="serialized-session-a",
        generation_id="serialized-generation-a",
        footprint=_effect_footprint("serialized-a"),
        prior_selector_version=0,
    )
    disjoint_registration_b = _domain_registration(
        domain_key=domain_b,
        session_id="serialized-session-b",
        generation_id="serialized-generation-b",
        footprint=_effect_footprint("serialized-b"),
        prior_selector_version=1,
    )
    disjoint_registered = disjoint_selector.register(
        disjoint_registration_a
    ) and disjoint_selector.register(disjoint_registration_b)
    disjoint_first = disjoint_registered and disjoint_selector.reserve(
        requested_domain_key=domain_a,
        creation_receipt=disjoint_registration_a.creation_receipt,
        expected_selector_version=2,
    )
    disjoint_second = disjoint_selector.reserve(
        requested_domain_key=domain_b,
        creation_receipt=disjoint_registration_b.creation_receipt,
        expected_selector_version=3,
    )
    disjoint_both_reserved = disjoint_first and disjoint_second
    audit.case()
    audit.require(
        disjoint_both_reserved,
        "disjoint_domains_can_reserve_separately",
    )

    capacity_selector = InstalledActuationAuthorityDomainSelector(model.mutation)
    capacity_registrations: list[ActuationAuthorityDomainRegistration] = []
    for index in range(capacity_selector.MAX_DOMAINS + 1):
        registration = _domain_registration(
            domain_key=hashlib.sha256(f"capacity-domain-{index}".encode()).hexdigest(),
            session_id=f"capacity-session-{index}",
            generation_id=f"capacity-generation-{index}",
            footprint=_effect_footprint(f"capacity-{index}"),
            prior_selector_version=index,
        )
        capacity_registrations.append(registration)
    capacity_prefix_installed = all(
        capacity_selector.register(registration)
        for registration in capacity_registrations[: capacity_selector.MAX_DOMAINS]
    )
    overflow_rejected = not capacity_selector.register(capacity_registrations[-1])
    audit.case()
    if overflow_rejected:
        audit.reject()
    bounded_registry = capacity_prefix_installed and overflow_rejected
    audit.require(bounded_registry, "domain_registry_bounded")

    substitution_selector = InstalledActuationAuthorityDomainSelector(model.mutation)
    substitution_registration_a = _domain_registration(
        domain_key=domain_a,
        session_id="substitution-session-a",
        generation_id="substitution-generation-a",
        footprint=_effect_footprint("substitution-a"),
        prior_selector_version=0,
    )
    substitution_registration_b = _domain_registration(
        domain_key=domain_b,
        session_id="substitution-session-b",
        generation_id="substitution-generation-b",
        footprint=_effect_footprint("substitution-b"),
        prior_selector_version=1,
    )
    substitution_registered = substitution_selector.register(
        substitution_registration_a
    ) and substitution_selector.register(substitution_registration_b)
    substitution_rejected = not (
        substitution_registered
        and substitution_selector.reserve(
            requested_domain_key=domain_b,
            creation_receipt=substitution_registration_a.creation_receipt,
            expected_selector_version=2,
        )
    )
    audit.case()
    if substitution_rejected:
        audit.reject()
    audit.require(
        substitution_rejected,
        "creation_receipt_binds_reserved_domain",
    )

    rebind_selector = InstalledActuationAuthorityDomainSelector(model.mutation)
    rebind_registration_a = _domain_registration(
        domain_key=domain_a,
        session_id="one-generation-session",
        generation_id="one-generation",
        footprint=_effect_footprint("rebind-a"),
        prior_selector_version=0,
    )
    rebind_registration_b = _domain_registration(
        domain_key=domain_b,
        session_id="one-generation-session",
        generation_id="one-generation",
        footprint=_effect_footprint("rebind-b"),
        prior_selector_version=1,
    )
    rebind_first = rebind_selector.register(rebind_registration_a)
    rebind_rejected = not rebind_selector.register(rebind_registration_b)
    audit.case()
    if rebind_rejected:
        audit.reject()
    one_generation_one_domain = rebind_first and rebind_rejected
    audit.require(
        one_generation_one_domain,
        "registry_generation_owns_one_domain",
    )

    incomplete_selector = InstalledActuationAuthorityDomainSelector(model.mutation)
    complete_footprint = _effect_footprint("incomplete-control")
    incomplete_footprint = ActuationEffectFootprint(
        **{
            **complete_footprint.__dict__,
            "active": (),
        }
    )
    incomplete_registration = _domain_registration(
        domain_key=domain_a,
        session_id="incomplete-session",
        generation_id="incomplete-generation",
        footprint=incomplete_footprint,
        prior_selector_version=0,
    )
    incomplete_rejected = not incomplete_selector.register(incomplete_registration)
    audit.case()
    if incomplete_rejected:
        audit.reject()
    audit.require(incomplete_rejected, "effect_footprint_complete")

    audit.witness(
        "global_conflict_graph_covers_every_effect_channel",
        all(conflict_rejections.values()),
    )
    audit.witness(
        "global_domain_selector_serializes_reservations",
        cas_serialized,
    )
    audit.witness(
        "disjoint_domains_serialize_and_both_reserve",
        disjoint_both_reserved,
    )
    audit.witness(
        "domain_creation_receipt_selects_reservation",
        substitution_rejected,
    )
    audit.witness("domain_registry_is_bounded", bounded_registry)
    audit.witness(
        "generation_registry_owns_one_domain",
        one_generation_one_domain,
    )
    audit.witness(
        "effect_footprint_requires_every_channel",
        incomplete_rejected,
    )

    wrong_jurisdiction_selector = InstalledActuationAuthorityDomainSelector(
        model.mutation
    )
    wrong_jurisdiction_registration = _domain_registration(
        domain_key=domain_a,
        session_id="wrong-jurisdiction-session",
        generation_id="wrong-jurisdiction-generation",
        footprint=_effect_footprint("wrong-jurisdiction"),
        prior_selector_version=0,
        jurisdiction_key=hashlib.sha256(b"wrong-jurisdiction").hexdigest(),
    )
    wrong_jurisdiction_rejected = not wrong_jurisdiction_selector.register(
        wrong_jurisdiction_registration
    )
    audit.case()
    if wrong_jurisdiction_rejected:
        audit.reject()
    audit.require(
        wrong_jurisdiction_rejected,
        "registration_matches_selector_jurisdiction",
    )

    wrong_incarnation_selector = InstalledActuationAuthorityDomainSelector(
        model.mutation
    )
    wrong_incarnation_registration = _domain_registration(
        domain_key=domain_a,
        session_id="wrong-incarnation-session",
        generation_id="wrong-incarnation-generation",
        footprint=_effect_footprint("wrong-incarnation"),
        prior_selector_version=0,
        jurisdiction_incarnation="wrong-jurisdiction-incarnation",
    )
    wrong_incarnation_rejected = not wrong_incarnation_selector.register(
        wrong_incarnation_registration
    )
    audit.case()
    if wrong_incarnation_rejected:
        audit.reject()
    audit.require(
        wrong_incarnation_rejected,
        "registration_matches_selector_incarnation",
    )

    jurisdiction_directory = InstalledPhysicalActuationJurisdictionDirectory(
        model.mutation
    )
    first_selector_enrolled = jurisdiction_directory.enroll(
        selector_id="jurisdiction-selector-a",
        jurisdiction_key=PHYSICAL_ACTUATION_JURISDICTION_KEY,
        jurisdiction_incarnation=(PHYSICAL_ACTUATION_JURISDICTION_INCARNATION),
    )
    duplicate_selector_rejected = not jurisdiction_directory.enroll(
        selector_id="jurisdiction-selector-b",
        jurisdiction_key=PHYSICAL_ACTUATION_JURISDICTION_KEY,
        jurisdiction_incarnation=(PHYSICAL_ACTUATION_JURISDICTION_INCARNATION),
    )
    audit.case()
    if duplicate_selector_rejected:
        audit.reject()
    sole_jurisdiction_selector = first_selector_enrolled and duplicate_selector_rejected
    audit.require(
        sole_jurisdiction_selector,
        "one_live_selector_per_jurisdiction_incarnation",
    )

    invalid_resource_footprint = _effect_footprint("unknown-resource-control")
    invalid_resource_footprint = ActuationEffectFootprint(
        **{
            **invalid_resource_footprint.__dict__,
            "active": ("UNKNOWN",),
        }
    )
    closedness_specs: tuple[
        tuple[
            str,
            str,
            dict[str, Any],
            dict[str, Any],
            ActuationEffectFootprint,
            tuple[str, str, str] | None,
        ],
        ...,
    ] = (
        (
            "jurisdiction_key",
            "physical_jurisdiction_key_closed",
            {"jurisdiction_key": "UNKNOWN"},
            {"jurisdiction_key": "UNKNOWN"},
            _effect_footprint("unknown-jurisdiction-key"),
            (
                "closed-selector-for-unknown-key",
                "UNKNOWN",
                PHYSICAL_ACTUATION_JURISDICTION_INCARNATION,
            ),
        ),
        (
            "jurisdiction_incarnation",
            "physical_jurisdiction_incarnation_closed",
            {"jurisdiction_incarnation": "UNKNOWN"},
            {"jurisdiction_incarnation": "UNKNOWN"},
            _effect_footprint("unknown-jurisdiction-incarnation"),
            (
                "closed-selector-for-unknown-incarnation",
                PHYSICAL_ACTUATION_JURISDICTION_KEY,
                "UNKNOWN",
            ),
        ),
        (
            "topology_digest",
            "physical_actuation_topology_digest_closed",
            {"topology_digest": "0" * 64},
            {"topology_digest": "0" * 64},
            _effect_footprint("unknown-topology"),
            None,
        ),
        (
            "body_principal",
            "domain_body_principal_closed",
            {},
            {"body_principal": "UNKNOWN"},
            _effect_footprint("unknown-body"),
            None,
        ),
        (
            "session_id",
            "domain_session_id_closed",
            {},
            {"session_id": "UNKNOWN"},
            _effect_footprint("unknown-session"),
            None,
        ),
        (
            "generation_id",
            "domain_generation_id_closed",
            {},
            {"generation_id": "UNKNOWN"},
            _effect_footprint("unknown-generation"),
            None,
        ),
        (
            "footprint_resource",
            "effect_footprint_resources_closed",
            {},
            {},
            invalid_resource_footprint,
            None,
        ),
        (
            "receipt_prior_version",
            "creation_receipt_version_exact_integer",
            {},
            {"prior_selector_version": False},
            _effect_footprint("boolean-prior-version"),
            None,
        ),
    )
    closedness_rejections: dict[str, bool] = {}
    for (
        name,
        invariant,
        selector_options,
        registration_options,
        footprint,
        directory_scope,
    ) in closedness_specs:
        selector = InstalledActuationAuthorityDomainSelector(
            model.mutation,
            **selector_options,
        )
        registration_arguments: dict[str, Any] = {
            "domain_key": hashlib.sha256(
                f"closedness-domain-{name}".encode()
            ).hexdigest(),
            "body_principal": f"closedness-body-{name}",
            "session_id": f"closedness-session-{name}",
            "generation_id": f"closedness-generation-{name}",
            "footprint": footprint,
            "prior_selector_version": 0,
        }
        registration_arguments.update(registration_options)
        registration = _domain_registration(**registration_arguments)
        rejected = not selector.register(registration)
        if directory_scope is not None:
            (
                selector_id,
                jurisdiction_key,
                jurisdiction_incarnation,
            ) = directory_scope
            directory = InstalledPhysicalActuationJurisdictionDirectory(model.mutation)
            rejected = rejected and not directory.enroll(
                selector_id=selector_id,
                jurisdiction_key=jurisdiction_key,
                jurisdiction_incarnation=jurisdiction_incarnation,
            )
        closedness_rejections[name] = rejected
        audit.case()
        if rejected:
            audit.reject()
        audit.require(rejected, invariant)

    invalid_selector_id_directory = InstalledPhysicalActuationJurisdictionDirectory(
        model.mutation
    )
    invalid_selector_id_rejected = not invalid_selector_id_directory.enroll(
        selector_id="UNKNOWN",
        jurisdiction_key=PHYSICAL_ACTUATION_JURISDICTION_KEY,
        jurisdiction_incarnation=PHYSICAL_ACTUATION_JURISDICTION_INCARNATION,
    )
    audit.case()
    if invalid_selector_id_rejected:
        audit.reject()
    audit.require(
        invalid_selector_id_rejected,
        "jurisdiction_selector_id_closed",
    )

    incarnation_directory = InstalledPhysicalActuationJurisdictionDirectory(
        model.mutation
    )
    first_incarnation_enrolled = incarnation_directory.enroll(
        selector_id="jurisdiction-incarnation-selector-a",
        jurisdiction_key=PHYSICAL_ACTUATION_JURISDICTION_KEY,
        jurisdiction_incarnation=PHYSICAL_ACTUATION_JURISDICTION_INCARNATION,
    )
    concurrent_incarnation_rejected = not incarnation_directory.enroll(
        selector_id="jurisdiction-incarnation-selector-b",
        jurisdiction_key=PHYSICAL_ACTUATION_JURISDICTION_KEY,
        jurisdiction_incarnation="synthetic-jurisdiction-incarnation-b",
    )
    audit.case()
    if concurrent_incarnation_rejected:
        audit.reject()
    sole_live_incarnation = (
        first_incarnation_enrolled and concurrent_incarnation_rejected
    )
    audit.require(
        sole_live_incarnation,
        "one_live_incarnation_per_jurisdiction",
    )

    scope_and_owner_identifiers_closed = (
        all(
            closedness_rejections[name]
            for name in (
                "jurisdiction_key",
                "jurisdiction_incarnation",
                "topology_digest",
                "body_principal",
                "session_id",
                "generation_id",
                "receipt_prior_version",
            )
        )
        and invalid_selector_id_rejected
    )
    audit.witness(
        "actuation_domain_scope_and_owner_identifiers_fail_closed",
        scope_and_owner_identifiers_closed,
    )
    audit.witness(
        "effect_footprint_resource_ids_fail_closed",
        closedness_rejections["footprint_resource"],
    )
    audit.witness(
        "one_live_incarnation_owns_each_physical_jurisdiction",
        sole_live_incarnation,
    )

    new_topology_digest = hashlib.sha256(
        b"synthetic-physical-actuation-topology-b"
    ).hexdigest()

    def topology_transition_fixture() -> tuple[
        InstalledActuationAuthorityDomainSelector,
        ActuationAuthorityDomainRegistration,
        ActuationAuthorityDomainRegistration,
    ]:
        selector = InstalledActuationAuthorityDomainSelector(model.mutation)
        old_registration = _domain_registration(
            domain_key=domain_a,
            session_id="topology-session",
            generation_id="topology-generation",
            body_principal="topology-body",
            footprint=_effect_footprint("topology-old"),
            prior_selector_version=0,
        )
        if not selector.register(old_registration):
            raise ProbeError("topology fixture could not register its old domain")
        replacement_registration = _domain_registration(
            domain_key=domain_b,
            session_id="topology-session",
            generation_id="topology-generation",
            body_principal="topology-body",
            footprint=_effect_footprint("topology-new"),
            prior_selector_version=0,
            topology_digest=new_topology_digest,
        )
        return selector, old_registration, replacement_registration

    topology_selector, old_registration, replacement_registration = (
        topology_transition_fixture()
    )
    topology_replaced = topology_selector.replace_topology(
        new_topology_digest=new_topology_digest,
        fenced_domain_keys=frozenset({old_registration.domain_key}),
        physical_isolation_proved=True,
        replacement_registrations=(replacement_registration,),
    )
    topology_replacement_exact = (
        topology_replaced
        and topology_selector.topology_digest == new_topology_digest
        and set(topology_selector.registry) == {replacement_registration.domain_key}
        and not topology_selector.reserved_domain_keys
    )
    audit.case()

    missing_fence_selector, old_registration, replacement_registration = (
        topology_transition_fixture()
    )
    missing_fence_rejected = not missing_fence_selector.replace_topology(
        new_topology_digest=new_topology_digest,
        fenced_domain_keys=frozenset(),
        physical_isolation_proved=True,
        replacement_registrations=(replacement_registration,),
    )
    audit.case()
    if missing_fence_rejected:
        audit.reject()
    audit.require(
        missing_fence_rejected,
        "topology_change_requires_complete_fence",
    )

    missing_isolation_selector, old_registration, replacement_registration = (
        topology_transition_fixture()
    )
    missing_isolation_rejected = not missing_isolation_selector.replace_topology(
        new_topology_digest=new_topology_digest,
        fenced_domain_keys=frozenset({old_registration.domain_key}),
        physical_isolation_proved=False,
        replacement_registrations=(replacement_registration,),
    )
    audit.case()
    if missing_isolation_rejected:
        audit.reject()
    audit.require(
        missing_isolation_rejected,
        "topology_change_requires_physical_isolation",
    )

    missing_reenrollment_selector, old_registration, _replacement_registration = (
        topology_transition_fixture()
    )
    missing_reenrollment_rejected = not (
        missing_reenrollment_selector.replace_topology(
            new_topology_digest=new_topology_digest,
            fenced_domain_keys=frozenset({old_registration.domain_key}),
            physical_isolation_proved=True,
            replacement_registrations=(),
        )
    )
    audit.case()
    if missing_reenrollment_rejected:
        audit.reject()
    audit.require(
        missing_reenrollment_rejected,
        "topology_change_requires_full_reenrollment",
    )

    audit.witness(
        "overlapping_body_principals_conflict_globally",
        all_cross_body_conflicts_rejected,
    )
    audit.witness(
        "one_live_selector_owns_each_jurisdiction_incarnation",
        wrong_jurisdiction_rejected
        and wrong_incarnation_rejected
        and sole_jurisdiction_selector,
    )
    audit.witness(
        "topology_change_fences_isolates_and_reenrolls",
        topology_replacement_exact
        and missing_fence_rejected
        and missing_isolation_rejected
        and missing_reenrollment_rejected,
    )


ORDINARY_PARTICIPANT_NATIVE_FACT = "OwnerAuthorizedNativeGenesisFact"
ORDINARY_PARTICIPANT_WRITE_IDENTITIES = "NativeParticipantReadWriteSelectorIdentitySet"
ORDINARY_PARTICIPANT_COMMITMENT = (
    "AuthorityTransactionDomainParticipantAdmissionCommitment"
)
ORDINARY_PARTICIPANT_CAS_CONDITION = "AuthorityTransactionCASCondition"
ORDINARY_PARTICIPANT_NATIVE_HEAD_CANDIDATE = "CandidateNativeParticipantStateHead"
ORDINARY_PARTICIPANT_NATIVE_SELECTOR_CANDIDATE = (
    "CandidateInstalledNativeParticipantSelector"
)
ORDINARY_PARTICIPANT_REGISTRY_ENTRY_CANDIDATE = (
    "CandidateAuthorityTransactionDomainParticipantRegistryEntry"
)
ORDINARY_PARTICIPANT_DOMAIN_HEAD_CANDIDATE = (
    "CandidateAuthorityTransactionDomainStateHead"
)
ORDINARY_PARTICIPANT_DOMAIN_SELECTOR_CANDIDATE = (
    "CandidateInstalledAuthorityTransactionDomainSelector"
)
ORDINARY_PARTICIPANT_TRANSACTION_RECEIPT = "AuthorityTransactionCommitReceipt"
ORDINARY_PARTICIPANT_NATIVE_GENESIS_RECEIPT = "NativeParticipantGenesisReceipt"
ORDINARY_PARTICIPANT_ADMISSION_RECEIPT = (
    "AuthorityTransactionDomainParticipantAdmissionReceipt"
)

ORDINARY_PARTICIPANT_ADMISSION_DEPENDENCIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (ORDINARY_PARTICIPANT_NATIVE_FACT, ()),
    (ORDINARY_PARTICIPANT_WRITE_IDENTITIES, ()),
    (
        ORDINARY_PARTICIPANT_COMMITMENT,
        (ORDINARY_PARTICIPANT_NATIVE_FACT,),
    ),
    (
        ORDINARY_PARTICIPANT_CAS_CONDITION,
        (
            ORDINARY_PARTICIPANT_COMMITMENT,
            ORDINARY_PARTICIPANT_NATIVE_FACT,
            ORDINARY_PARTICIPANT_WRITE_IDENTITIES,
        ),
    ),
    (
        ORDINARY_PARTICIPANT_NATIVE_HEAD_CANDIDATE,
        (
            ORDINARY_PARTICIPANT_CAS_CONDITION,
            ORDINARY_PARTICIPANT_COMMITMENT,
            ORDINARY_PARTICIPANT_NATIVE_FACT,
        ),
    ),
    (
        ORDINARY_PARTICIPANT_NATIVE_SELECTOR_CANDIDATE,
        (
            ORDINARY_PARTICIPANT_CAS_CONDITION,
            ORDINARY_PARTICIPANT_COMMITMENT,
            ORDINARY_PARTICIPANT_NATIVE_FACT,
            ORDINARY_PARTICIPANT_NATIVE_HEAD_CANDIDATE,
        ),
    ),
    (
        ORDINARY_PARTICIPANT_REGISTRY_ENTRY_CANDIDATE,
        (
            ORDINARY_PARTICIPANT_CAS_CONDITION,
            ORDINARY_PARTICIPANT_COMMITMENT,
            ORDINARY_PARTICIPANT_NATIVE_FACT,
        ),
    ),
    (
        ORDINARY_PARTICIPANT_DOMAIN_HEAD_CANDIDATE,
        (
            ORDINARY_PARTICIPANT_CAS_CONDITION,
            ORDINARY_PARTICIPANT_COMMITMENT,
            ORDINARY_PARTICIPANT_NATIVE_FACT,
            ORDINARY_PARTICIPANT_REGISTRY_ENTRY_CANDIDATE,
        ),
    ),
    (
        ORDINARY_PARTICIPANT_DOMAIN_SELECTOR_CANDIDATE,
        (
            ORDINARY_PARTICIPANT_CAS_CONDITION,
            ORDINARY_PARTICIPANT_COMMITMENT,
            ORDINARY_PARTICIPANT_DOMAIN_HEAD_CANDIDATE,
            ORDINARY_PARTICIPANT_NATIVE_FACT,
        ),
    ),
    (
        ORDINARY_PARTICIPANT_TRANSACTION_RECEIPT,
        (
            ORDINARY_PARTICIPANT_CAS_CONDITION,
            ORDINARY_PARTICIPANT_DOMAIN_HEAD_CANDIDATE,
            ORDINARY_PARTICIPANT_DOMAIN_SELECTOR_CANDIDATE,
            ORDINARY_PARTICIPANT_NATIVE_HEAD_CANDIDATE,
            ORDINARY_PARTICIPANT_NATIVE_SELECTOR_CANDIDATE,
            ORDINARY_PARTICIPANT_REGISTRY_ENTRY_CANDIDATE,
        ),
    ),
    (
        ORDINARY_PARTICIPANT_NATIVE_GENESIS_RECEIPT,
        (
            ORDINARY_PARTICIPANT_NATIVE_HEAD_CANDIDATE,
            ORDINARY_PARTICIPANT_NATIVE_SELECTOR_CANDIDATE,
            ORDINARY_PARTICIPANT_TRANSACTION_RECEIPT,
        ),
    ),
    (
        ORDINARY_PARTICIPANT_ADMISSION_RECEIPT,
        (
            ORDINARY_PARTICIPANT_NATIVE_GENESIS_RECEIPT,
            ORDINARY_PARTICIPANT_REGISTRY_ENTRY_CANDIDATE,
            ORDINARY_PARTICIPANT_TRANSACTION_RECEIPT,
        ),
    ),
)

ORDINARY_PARTICIPANT_CANDIDATE_ARTIFACTS = frozenset(
    {
        ORDINARY_PARTICIPANT_NATIVE_HEAD_CANDIDATE,
        ORDINARY_PARTICIPANT_NATIVE_SELECTOR_CANDIDATE,
        ORDINARY_PARTICIPANT_REGISTRY_ENTRY_CANDIDATE,
        ORDINARY_PARTICIPANT_DOMAIN_HEAD_CANDIDATE,
        ORDINARY_PARTICIPANT_DOMAIN_SELECTOR_CANDIDATE,
    }
)
ORDINARY_PARTICIPANT_RECEIPT_ARTIFACTS = frozenset(
    {
        ORDINARY_PARTICIPANT_TRANSACTION_RECEIPT,
        ORDINARY_PARTICIPANT_NATIVE_GENESIS_RECEIPT,
        ORDINARY_PARTICIPANT_ADMISSION_RECEIPT,
    }
)


def _ordinary_participant_admission_dependency_map(
    mutation: str | None,
) -> dict[str, tuple[str, ...]]:
    """Return the fresh ordinary-participant digest graph."""

    dependencies = dict(ORDINARY_PARTICIPANT_ADMISSION_DEPENDENCIES)
    if mutation == "ordinary_participant_commitment_binds_candidate_head":
        dependencies[ORDINARY_PARTICIPANT_COMMITMENT] = tuple(
            sorted(
                {
                    *dependencies[ORDINARY_PARTICIPANT_COMMITMENT],
                    ORDINARY_PARTICIPANT_NATIVE_HEAD_CANDIDATE,
                }
            )
        )
    return dependencies


def _dependency_topological_order(
    dependencies: dict[str, tuple[str, ...]],
) -> tuple[str, ...]:
    """Return a deterministic order, or a strict prefix when a cycle exists."""

    installed: set[str] = set()
    order: list[str] = []
    while len(installed) < len(dependencies):
        ready = sorted(
            artifact
            for artifact, prerequisites in dependencies.items()
            if artifact not in installed and set(prerequisites).issubset(installed)
        )
        if not ready:
            break
        installed.update(ready)
        order.extend(ready)
    return tuple(order)


def _ordinary_participant_admission_dag_evidence() -> dict[str, Any]:
    """Build the reviewed baseline graph and content-addressed node fixtures."""

    dependencies = _ordinary_participant_admission_dependency_map(None)
    order = _dependency_topological_order(dependencies)
    _require(
        len(order) == len(dependencies),
        "ordinary participant admission baseline digest graph is cyclic",
    )
    digests: dict[str, str] = {}
    for artifact in order:
        digests[artifact] = _sha256_json(
            {
                "domain": "ncp-b01-ordinary-participant-admission-dag-node-v1",
                "artifact": artifact,
                "dependencies": tuple(
                    (dependency, digests[dependency])
                    for dependency in dependencies[artifact]
                ),
            }
        )
    return {
        "branch": "INSTALL_FRESH_SELECTOR_WITH_NATIVE_GENESIS",
        "artifacts": [
            {
                "artifact": artifact,
                "depends_on": list(dependencies[artifact]),
                "artifact_digest": digests[artifact],
            }
            for artifact in order
        ],
        "topological_order": list(order),
        "admission_commitment_excludes": sorted(
            {
                *ORDINARY_PARTICIPANT_CANDIDATE_ARTIFACTS,
                ORDINARY_PARTICIPANT_CAS_CONDITION,
                *ORDINARY_PARTICIPANT_RECEIPT_ARTIFACTS,
            }
        ),
        "cas_condition_binds": [
            ORDINARY_PARTICIPANT_COMMITMENT,
            ORDINARY_PARTICIPANT_NATIVE_FACT,
            ORDINARY_PARTICIPANT_WRITE_IDENTITIES,
        ],
        "cas_condition_excludes": sorted(
            {
                *ORDINARY_PARTICIPANT_CANDIDATE_ARTIFACTS,
                *ORDINARY_PARTICIPANT_RECEIPT_ARTIFACTS,
            }
        ),
        "candidate_binds": [
            ORDINARY_PARTICIPANT_CAS_CONDITION,
            ORDINARY_PARTICIPANT_COMMITMENT,
            ORDINARY_PARTICIPANT_NATIVE_FACT,
        ],
        "receipt_order": [
            ORDINARY_PARTICIPANT_TRANSACTION_RECEIPT,
            ORDINARY_PARTICIPANT_NATIVE_GENESIS_RECEIPT,
            ORDINARY_PARTICIPANT_ADMISSION_RECEIPT,
        ],
        "cycle_mutant": "ordinary_participant_commitment_binds_candidate_head",
        "digest_graph": "EXACT_ACYCLIC",
    }


def _campaign_ordinary_participant_admission_dag(
    model: Model,
    audit: Audit,
) -> None:
    """Challenge the fresh ordinary-participant admission digest order."""

    dependencies = _ordinary_participant_admission_dependency_map(model.mutation)
    known_artifacts = set(dependencies)
    references_are_closed = all(
        set(prerequisites).issubset(known_artifacts)
        for prerequisites in dependencies.values()
    )
    order = _dependency_topological_order(dependencies)
    graph_is_acyclic = len(order) == len(dependencies)
    commitment_dependencies = set(dependencies[ORDINARY_PARTICIPANT_COMMITMENT])
    commitment_is_receipt_free_and_pre_candidate = commitment_dependencies == {
        ORDINARY_PARTICIPANT_NATIVE_FACT
    } and not commitment_dependencies.intersection(
        {
            ORDINARY_PARTICIPANT_CAS_CONDITION,
            *ORDINARY_PARTICIPANT_CANDIDATE_ARTIFACTS,
            *ORDINARY_PARTICIPANT_RECEIPT_ARTIFACTS,
        }
    )
    cas_dependencies = set(dependencies[ORDINARY_PARTICIPANT_CAS_CONDITION])
    cas_is_receipt_free_and_pre_candidate = cas_dependencies == {
        ORDINARY_PARTICIPANT_COMMITMENT,
        ORDINARY_PARTICIPANT_NATIVE_FACT,
        ORDINARY_PARTICIPANT_WRITE_IDENTITIES,
    }
    candidate_dependencies_are_forward_only = all(
        {
            ORDINARY_PARTICIPANT_CAS_CONDITION,
            ORDINARY_PARTICIPANT_COMMITMENT,
            ORDINARY_PARTICIPANT_NATIVE_FACT,
        }.issubset(dependencies[artifact])
        and not set(dependencies[artifact]).intersection(
            ORDINARY_PARTICIPANT_RECEIPT_ARTIFACTS
        )
        for artifact in ORDINARY_PARTICIPANT_CANDIDATE_ARTIFACTS
    )
    receipts_are_strictly_post_candidate = (
        ORDINARY_PARTICIPANT_TRANSACTION_RECEIPT
        in dependencies[ORDINARY_PARTICIPANT_NATIVE_GENESIS_RECEIPT]
        and ORDINARY_PARTICIPANT_TRANSACTION_RECEIPT
        in dependencies[ORDINARY_PARTICIPANT_ADMISSION_RECEIPT]
        and ORDINARY_PARTICIPANT_NATIVE_GENESIS_RECEIPT
        in dependencies[ORDINARY_PARTICIPANT_ADMISSION_RECEIPT]
        and ORDINARY_PARTICIPANT_CANDIDATE_ARTIFACTS.issubset(
            dependencies[ORDINARY_PARTICIPANT_TRANSACTION_RECEIPT]
        )
    )
    exact_baseline_dependencies = dependencies == dict(
        ORDINARY_PARTICIPANT_ADMISSION_DEPENDENCIES
    )

    audit.case(6)
    audit.require(
        references_are_closed,
        "ordinary_participant_admission_dependency_set_closed",
    )
    audit.require(
        graph_is_acyclic,
        "ordinary_participant_admission_digest_dag_acyclic",
    )
    audit.require(
        commitment_is_receipt_free_and_pre_candidate,
        "ordinary_participant_commitment_precedes_condition_and_candidates",
    )
    audit.require(
        cas_is_receipt_free_and_pre_candidate,
        "ordinary_participant_condition_precedes_candidates",
    )
    audit.require(
        candidate_dependencies_are_forward_only,
        "ordinary_participant_candidates_exclude_future_receipts",
    )
    audit.require(
        receipts_are_strictly_post_candidate,
        "ordinary_participant_receipts_follow_atomic_commit",
    )
    audit.witness(
        "ordinary_participant_admission_digest_dag_is_exact_and_acyclic",
        references_are_closed
        and graph_is_acyclic
        and exact_baseline_dependencies
        and commitment_is_receipt_free_and_pre_candidate
        and cas_is_receipt_free_and_pre_candidate
        and candidate_dependencies_are_forward_only
        and receipts_are_strictly_post_candidate,
    )


class ActiveStateKind(StrEnum):
    """Closed cross-field union for one retained Active boundary state."""

    INITIAL_HOLD = "INITIAL_HOLD"
    ACTIVE = "ACTIVE"
    WATCHDOG_HOLD = "WATCHDOG_HOLD"
    CLOCK_DISCONTINUITY_HOLD = "CLOCK_DISCONTINUITY_HOLD"
    FAIL_CLOSED_HOLD = "FAIL_CLOSED_HOLD"


@dataclass
class ActiveDurableState:
    """Persistent application value and watchdog state."""

    value_digest: str | None = None
    watchdog_deadline: int | None = None
    watchdog_clock: str | None = None
    accepted_attempts: int = 0
    mode: Mode = Mode.HOLD
    local_restrictive_receipt: bool = False
    state_kind: ActiveStateKind = ActiveStateKind.INITIAL_HOLD
    revision: int = 0


def _active_durable_state_is_exact(value: object) -> bool:
    return (
        type(value) is ActiveDurableState
        and (value.value_digest is None or _exact_closed_identifier(value.value_digest))
        and (
            value.watchdog_deadline is None
            or _exact_nonnegative_int(value.watchdog_deadline)
        )
        and _exact_optional_closed_identifier(value.watchdog_clock)
        and _exact_int(value.accepted_attempts)
        and value.accepted_attempts >= 0
        and _exact_enum(value.mode, Mode)
        and _exact_bool(value.local_restrictive_receipt)
        and _exact_enum(value.state_kind, ActiveStateKind)
        and _exact_nonnegative_int(value.revision)
    )


def _active_state_fingerprint(
    value: ActiveDurableState,
) -> tuple[object, ...]:
    """Capture the complete retained state at the boundary-owned install."""

    return (
        value.value_digest,
        value.watchdog_deadline,
        value.watchdog_clock,
        value.accepted_attempts,
        value.mode,
        value.local_restrictive_receipt,
        value.state_kind,
        value.revision,
    )


class ActiveBoundary:
    """Synthetic atomic Active application boundary."""

    def __init__(self, mutation: str | None) -> None:
        self.mutation = _validate_mutation_selector(mutation)
        self.state = ActiveDurableState()
        self._retained_state = self.state
        self._retained_state_fingerprint = _active_state_fingerprint(self.state)

    def _install_state(self, state: ActiveDurableState) -> None:
        self.state = state
        self._retained_state = state
        self._retained_state_fingerprint = _active_state_fingerprint(state)

    def _fail_closed_state(self) -> None:
        previous_revision = (
            self.state.revision
            if type(self.state) is ActiveDurableState
            and _exact_nonnegative_int(self.state.revision)
            else 0
        )
        self._install_state(
            ActiveDurableState(
                mode=Mode.HOLD,
                local_restrictive_receipt=True,
                state_kind=ActiveStateKind.FAIL_CLOSED_HOLD,
                revision=previous_revision + 1,
            )
        )

    @staticmethod
    def _state_semantics_are_closed(state: ActiveDurableState) -> bool:
        if state.state_kind == ActiveStateKind.INITIAL_HOLD:
            return (
                state.value_digest is None
                and state.watchdog_deadline is None
                and state.watchdog_clock is None
                and state.accepted_attempts == 0
                and state.mode == Mode.HOLD
                and not state.local_restrictive_receipt
                and state.revision == 0
            )
        if state.state_kind == ActiveStateKind.ACTIVE:
            return (
                state.value_digest is not None
                and state.watchdog_deadline is not None
                and state.watchdog_clock is not None
                and state.accepted_attempts >= 1
                and state.mode == Mode.ACTIVE
                and not state.local_restrictive_receipt
                and state.revision >= 1
            )
        if state.state_kind == ActiveStateKind.WATCHDOG_HOLD:
            return (
                state.value_digest is not None
                and state.watchdog_deadline is not None
                and state.watchdog_clock is not None
                and state.accepted_attempts >= 1
                and state.mode == Mode.HOLD
                and not state.local_restrictive_receipt
                and state.revision >= 2
            )
        if state.state_kind == ActiveStateKind.CLOCK_DISCONTINUITY_HOLD:
            return (
                state.value_digest is not None
                and state.watchdog_deadline is None
                and state.watchdog_clock is None
                and state.accepted_attempts >= 1
                and state.mode == Mode.HOLD
                and state.local_restrictive_receipt
                and state.revision >= 2
            )
        return (
            state.state_kind == ActiveStateKind.FAIL_CLOSED_HOLD
            and state.value_digest is None
            and state.watchdog_deadline is None
            and state.watchdog_clock is None
            and state.accepted_attempts == 0
            and state.mode == Mode.HOLD
            and state.local_restrictive_receipt
            and state.revision >= 1
        )

    def _state_is_usable(self) -> bool:
        identity_is_retained = self.state is self._retained_state
        fingerprint_is_retained = (
            type(self.state) is ActiveDurableState
            and _active_state_fingerprint(self.state)
            == self._retained_state_fingerprint
        )
        semantics_are_closed = _active_durable_state_is_exact(
            self.state
        ) and self._state_semantics_are_closed(self.state)
        if self.mutation == "caller_constructed_active_state_authorized":
            identity_is_retained = True
            fingerprint_is_retained = True
            semantics_are_closed = _active_durable_state_is_exact(self.state)
        if identity_is_retained and fingerprint_is_retained and semantics_are_closed:
            return True
        self._fail_closed_state()
        return False

    def accept(
        self,
        *,
        value_digest: str,
        acceptance_tick: int,
        command_deadline: int,
        lease_deadline: int,
        crash_cut: CrashCut,
    ) -> None:
        if not self._state_is_usable():
            raise ProbeError("Active durable state shape is not exact")
        if self.mutation != "active_type_aliases_authorize" and not (
            _exact_closed_identifier(value_digest)
            and _exact_nonnegative_int(acceptance_tick)
            and _exact_nonnegative_int(command_deadline)
            and _exact_nonnegative_int(lease_deadline)
            and _exact_enum(crash_cut, CrashCut)
        ):
            raise ProbeError("Active acceptance input shape is not exact")
        deadline = min(command_deadline, lease_deadline)
        if self.mutation == "watchdog_exceeds_bounds":
            deadline = max(command_deadline, lease_deadline) + 5
        if acceptance_tick >= deadline:
            raise ProbeError("probe attempted a late Active acceptance")

        if crash_cut == CrashCut.BEFORE_COMMIT:
            if self.mutation == "active_watchdog_before_value":
                self.state.watchdog_deadline = deadline
                self.state.watchdog_clock = "body-clock-a"
            return
        if (
            crash_cut == CrashCut.BETWEEN_VALUE_AND_WATCHDOG
            and self.mutation == "active_watchdog_after_value"
        ):
            self.state.value_digest = value_digest
            self.state.accepted_attempts += 1
            self.state.mode = Mode.ACTIVE
            return
        if (
            crash_cut == CrashCut.BETWEEN_VALUE_AND_WATCHDOG
            and self.mutation == "active_watchdog_before_value"
        ):
            self.state.watchdog_deadline = deadline
            self.state.watchdog_clock = "body-clock-a"
            return

        # The correct model has no externally visible mid-transaction state.
        self._install_state(
            ActiveDurableState(
                value_digest=value_digest,
                watchdog_deadline=deadline,
                watchdog_clock="body-clock-a",
                accepted_attempts=self.state.accepted_attempts + 1,
                mode=Mode.ACTIVE,
                state_kind=ActiveStateKind.ACTIVE,
                revision=self.state.revision + 1,
            )
        )

    def restart(self) -> None:
        if not self._state_is_usable():
            return
        if self.mutation == "watchdog_is_volatile":
            self.state.watchdog_deadline = None
            self.state.watchdog_clock = None

    def discontinuous_clock_restart(self) -> None:
        """Handle restart without authenticated watchdog-clock continuity."""

        if not self._state_is_usable():
            return
        if self.state.state_kind != ActiveStateKind.ACTIVE:
            return
        if self.mutation == "watchdog_clock_restart_copies_deadline":
            self.state.watchdog_clock = "body-clock-b"
            return
        self._install_state(
            ActiveDurableState(
                value_digest=self.state.value_digest,
                accepted_attempts=self.state.accepted_attempts,
                mode=Mode.HOLD,
                local_restrictive_receipt=True,
                state_kind=ActiveStateKind.CLOCK_DISCONTINUITY_HOLD,
                revision=self.state.revision + 1,
            )
        )

    def replay(self, receive_tick: int) -> None:
        if not self._state_is_usable() or not _exact_nonnegative_int(receive_tick):
            return
        if self.state.state_kind != ActiveStateKind.ACTIVE:
            return
        if self.mutation == "replay_refreshes_watchdog":
            self.state.watchdog_deadline = receive_tick + 8
            self.state.accepted_attempts += 1

    def advance(self, tick: int) -> None:
        if not self._state_is_usable() or not _exact_nonnegative_int(tick):
            return
        if self.state.state_kind != ActiveStateKind.ACTIVE:
            return
        deadline = self.state.watchdog_deadline
        if deadline is not None and tick >= deadline:
            self._install_state(
                ActiveDurableState(
                    value_digest=self.state.value_digest,
                    watchdog_deadline=deadline,
                    watchdog_clock=self.state.watchdog_clock,
                    accepted_attempts=self.state.accepted_attempts,
                    mode=Mode.HOLD,
                    state_kind=ActiveStateKind.WATCHDOG_HOLD,
                    revision=self.state.revision + 1,
                )
            )


def _campaign_active_watchdog(model: Model, audit: Audit) -> None:
    atomic = True
    for crash_cut in CrashCut:
        boundary = ActiveBoundary(model.mutation)
        boundary.accept(
            value_digest="value-a",
            acceptance_tick=104,
            command_deadline=108,
            lease_deadline=110,
            crash_cut=crash_cut,
        )
        committed = (
            boundary.state.value_digest == "value-a"
            and boundary.state.watchdog_deadline == 108
            and boundary.state.watchdog_clock == "body-clock-a"
            and boundary.state.accepted_attempts == 1
            and boundary.state.mode == Mode.ACTIVE
        )
        absent = (
            boundary.state.value_digest is None
            and boundary.state.watchdog_deadline is None
            and boundary.state.watchdog_clock is None
            and boundary.state.accepted_attempts == 0
            and boundary.state.mode == Mode.HOLD
        )
        atomic_state = committed or absent
        atomic = atomic and atomic_state
        audit.case()
        audit.require(atomic_state, "active_watchdog_atomic")
    audit.witness("active_value_and_watchdog_are_atomic", atomic)

    persisted = ActiveBoundary(model.mutation)
    persisted.accept(
        value_digest="value-b",
        acceptance_tick=104,
        command_deadline=108,
        lease_deadline=110,
        crash_cut=CrashCut.AFTER_COMMIT,
    )
    persisted_deadline = persisted.state.watchdog_deadline
    if persisted_deadline is None:
        raise ProbeError("accepted Active value has no watchdog")
    persisted.restart()
    persisted.advance(persisted_deadline)
    audit.case()
    audit.require(
        persisted.state.watchdog_deadline == persisted_deadline
        and persisted.state.mode == Mode.HOLD,
        "active_watchdog_persistent",
    )
    audit.witness(
        "watchdog_survives_restart",
        persisted.state.watchdog_deadline == persisted_deadline
        and persisted.state.mode == Mode.HOLD,
    )

    replay = ActiveBoundary(model.mutation)
    replay.accept(
        value_digest="value-c",
        acceptance_tick=104,
        command_deadline=108,
        lease_deadline=110,
        crash_cut=CrashCut.AFTER_COMMIT,
    )
    before = copy.deepcopy(replay.state)
    replay.replay(receive_tick=107)
    audit.case()
    audit.require(replay.state == before, "active_replay_no_refresh")
    audit.witness("active_replay_does_not_refresh_watchdog", replay.state == before)

    bounded = ActiveBoundary(model.mutation)
    bounded.accept(
        value_digest="value-d",
        acceptance_tick=104,
        command_deadline=108,
        lease_deadline=106,
        crash_cut=CrashCut.AFTER_COMMIT,
    )
    audit.case()
    audit.require(
        bounded.state.watchdog_deadline == 106,
        "active_watchdog_bounded",
    )
    audit.witness(
        "new_active_value_respects_command_and_lease_bounds",
        bounded.state.watchdog_deadline == 106,
    )

    discontinuity = ActiveBoundary(model.mutation)
    discontinuity.accept(
        value_digest="value-e",
        acceptance_tick=104,
        command_deadline=108,
        lease_deadline=110,
        crash_cut=CrashCut.AFTER_COMMIT,
    )
    discontinuity.discontinuous_clock_restart()
    restart_failed_closed = (
        discontinuity.state.mode == Mode.HOLD
        and discontinuity.state.watchdog_deadline is None
        and discontinuity.state.watchdog_clock is None
        and discontinuity.state.local_restrictive_receipt
    )
    audit.case()
    audit.require(restart_failed_closed, "watchdog_restart_fails_closed")
    audit.witness(
        "watchdog_clock_discontinuity_has_restrictive_receipt",
        restart_failed_closed,
    )

    # A cut can close an admitted Active tip before START. It neither fabricates
    # an application attempt nor waits forever for evidence that cannot exist.
    admitted_state = "ADMITTED"
    attempt_installed = False
    boundary_invocations = 0
    cut_evidence_installed = True
    if model.mutation == "prestart_cut_leaves_admitted_tip":
        terminal_state = admitted_state
    elif model.mutation == "prestart_cut_requires_attempt" and not attempt_installed:
        terminal_state = "BLOCKED_AWAITING_NONEXISTENT_ATTEMPT"
    else:
        terminal_state = "SUPERSEDED_BEFORE_APPLICATION_ATTEMPT"
    audit.case()
    prestart_closed = (
        terminal_state == "SUPERSEDED_BEFORE_APPLICATION_ATTEMPT"
        and cut_evidence_installed
        and not attempt_installed
        and boundary_invocations == 0
    )
    audit.require(prestart_closed, "prestart_cut_terminalizes")
    audit.witness(
        "prestart_cut_closes_admitted_without_attempt",
        prestart_closed,
    )


@dataclass(frozen=True)
class DrainGrant:
    """One preallocated retirement-drain freshness grant and slot."""

    grant_id: str
    mode: Mode
    slot: int
    capacity_operation_id: str = ""
    capacity_token_id: str = ""
    issuer_sequence: int = -1


def _drain_grant_is_exact(value: object) -> bool:
    return (
        type(value) is DrainGrant
        and _exact_closed_identifier(value.grant_id)
        and _exact_enum(value.mode, Mode)
        and _exact_nonnegative_int(value.slot)
        and _exact_closed_identifier(value.capacity_operation_id)
        and _exact_closed_identifier(value.capacity_token_id)
        and _exact_nonnegative_int(value.issuer_sequence)
    )


class DrainMachine:
    """Irreversible retirement drain routed through the unified boundary."""

    def __init__(self, mutation: str | None) -> None:
        self.mutation = _validate_mutation_selector(mutation)
        self.phase = "OPEN"
        self.grants: list[DrainGrant] = []
        self._issued_grants: dict[str, DrainGrant] = {}
        self._grant_counter = 0
        self.escalation_tokens_used = 0
        self.applied_identity: tuple[str, str] | None = None
        self.applied_operation: UnifiedRestrictiveOperation | None = None
        self.capacity_cut_operation: UnifiedRestrictiveOperation | None = None
        self._retained_capacity_cut: UnifiedRestrictiveOperation | None = None
        self._retained_applied_identity: tuple[str, str] | None = None
        self._retained_applied_operation: UnifiedRestrictiveOperation | None = None
        self.remote_edge_closed = False
        self.boundary = UnifiedPhysicalBoundary(mutation)

    def _state_is_exact(self) -> bool:
        structurally_exact = (
            type(self.phase) is str
            and self.phase in {"OPEN", "RETIRED_DRAIN_ONLY"}
            and type(self.grants) is list
            and all(_drain_grant_is_exact(grant) for grant in self.grants)
            and type(self._issued_grants) is dict
            and all(
                _exact_closed_identifier(grant_id)
                and _drain_grant_is_exact(grant)
                and grant.grant_id == grant_id
                for grant_id, grant in self._issued_grants.items()
            )
            and _exact_nonnegative_int(self._grant_counter)
            and _exact_nonnegative_int(self.escalation_tokens_used)
            and type(self.boundary) is UnifiedPhysicalBoundary
            and (
                self.applied_identity is None
                or (
                    _exact_tuple_of(
                        self.applied_identity,
                        _exact_closed_identifier,
                    )
                    and len(self.applied_identity) == 2
                )
            )
            and (
                self.applied_operation is None
                or self.boundary._owns_operation(self.applied_operation)
            )
            and (
                self.capacity_cut_operation is None
                or self.boundary._owns_operation(self.capacity_cut_operation)
            )
            and (
                self._retained_capacity_cut is None
                or self.boundary._owns_operation(self._retained_capacity_cut)
            )
            and (
                self._retained_applied_identity is None
                or (
                    _exact_tuple_of(
                        self._retained_applied_identity,
                        _exact_closed_identifier,
                    )
                    and len(self._retained_applied_identity) == 2
                )
            )
            and (
                self._retained_applied_operation is None
                or self.boundary._owns_operation(self._retained_applied_operation)
            )
            and _exact_bool(self.remote_edge_closed)
            and self.boundary._state_is_exact()
        )
        if not structurally_exact:
            return False
        if self.mutation == "forged_drain_state_authorized":
            return True
        if (
            self._grant_counter != len(self._issued_grants)
            or set(self._issued_grants)
            != {f"drain-grant-{ordinal}" for ordinal in range(self._grant_counter)}
            or len(self.grants) != len(self._issued_grants)
            or any(
                grant.grant_id != grant_id
                or grant.issuer_sequence != ordinal
                or self._issued_grants.get(grant_id) is not grant
                for ordinal, (grant_id, grant) in enumerate(self._issued_grants.items())
            )
            or any(
                self._issued_grants.get(grant.grant_id) is not grant
                for grant in self.grants
            )
        ):
            return False
        if self.phase == "OPEN":
            return (
                not self.grants
                and self.capacity_cut_operation is None
                and self._retained_capacity_cut is None
                and self.applied_identity is None
                and self.applied_operation is None
                and self._retained_applied_identity is None
                and self._retained_applied_operation is None
                and self.escalation_tokens_used == 0
                and not self.remote_edge_closed
            )
        if (
            self.capacity_cut_operation is None
            or not self.boundary._owns_operation(self.capacity_cut_operation)
            or self.capacity_cut_operation is not self._retained_capacity_cut
            or self.capacity_cut_operation.path
            != RestrictivePath.CAPACITY_RETIREMENT_RESTRICTIVE
            or not _unified_dag_is_exact(self.capacity_cut_operation)
            or any(
                grant.capacity_operation_id != self.capacity_cut_operation.operation_id
                or grant.capacity_token_id != self.capacity_cut_operation.token.token_id
                for grant in self.grants
            )
        ):
            return False
        if not self.grants and self.mutation != "drain_grant_not_preallocated":
            return False
        if self.mutation not in {
            "drain_allows_general_mode",
            "drain_mints_second_grant",
        } and any(grant.mode != Mode.ESTOP or grant.slot != 1 for grant in self.grants):
            return False
        if self.escalation_tokens_used == 0:
            return (
                self.applied_identity is None
                and self.applied_operation is None
                and self._retained_applied_identity is None
                and self._retained_applied_operation is None
            )
        if self.escalation_tokens_used != 1:
            return (
                self.mutation == "drain_mints_second_token"
                and self.applied_identity is self._retained_applied_identity
                and self.applied_operation is self._retained_applied_operation
            )
        return (
            self.applied_identity is not None
            and self.applied_operation is not None
            and self.applied_identity is self._retained_applied_identity
            and self.applied_operation is self._retained_applied_operation
            and self.boundary._owns_operation(self.applied_operation)
            and self.applied_operation.path == RestrictivePath.DRAIN_ESTOP
            and _unified_dag_is_exact(self.applied_operation)
            and self.applied_operation.fence_epoch
            > self.capacity_cut_operation.fence_epoch
            and (
                self.remote_edge_closed
                or self.mutation == "drain_leaves_remote_edge_open"
            )
        )

    def _issue_grant(self, mode: Mode) -> DrainGrant:
        if self.capacity_cut_operation is None:
            raise ProbeError("drain grant lacks its capacity-cut provenance")
        grant_id = f"drain-grant-{self._grant_counter}"
        grant = DrainGrant(
            grant_id=grant_id,
            mode=mode,
            slot=1,
            capacity_operation_id=self.capacity_cut_operation.operation_id,
            capacity_token_id=self.capacity_cut_operation.token.token_id,
            issuer_sequence=self._grant_counter,
        )
        self._grant_counter += 1
        self._issued_grants[grant_id] = grant
        self.grants.append(grant)
        return grant

    def exhaust_capacity(self) -> None:
        if not self._state_is_exact() or self.phase != "OPEN":
            return
        capacity_cut = self.boundary.run(
            RestrictivePath.CAPACITY_RETIREMENT_RESTRICTIVE
        )
        self.capacity_cut_operation = capacity_cut
        self._retained_capacity_cut = capacity_cut
        self.phase = "RETIRED_DRAIN_ONLY"
        if self.mutation != "drain_grant_not_preallocated":
            self._issue_grant(Mode.ESTOP)

    def request_grant(self, mode: Mode) -> DrainGrant | None:
        if not self._state_is_exact():
            return None
        if self.mutation != "drain_type_aliases_authorize" and not _exact_enum(
            mode, Mode
        ):
            return None
        if self.phase != "RETIRED_DRAIN_ONLY":
            return None
        if mode != Mode.ESTOP:
            if self.mutation == "drain_allows_general_mode":
                return self._issue_grant(mode)
            return None
        if not self.grants and self.mutation == "drain_grant_not_preallocated":
            return self._issue_grant(Mode.ESTOP)
        if self.mutation == "drain_mints_second_grant" and self.grants:
            return self._issue_grant(Mode.ESTOP)
        return self.grants[0] if self.grants else None

    def consume(
        self,
        grant: DrainGrant | None,
        *,
        command_id: str,
        content_digest: str,
        mode: Mode,
    ) -> str:
        if not self._state_is_exact():
            return "REJECTED"
        input_types_are_exact = (
            (grant is None or _drain_grant_is_exact(grant))
            and _exact_closed_identifier(command_id)
            and _exact_closed_identifier(content_digest)
            and _exact_enum(mode, Mode)
        )
        if (
            self.mutation != "drain_type_aliases_authorize"
            and not input_types_are_exact
        ):
            return "REJECTED"
        identity = (command_id, content_digest)
        retained_grant = (
            grant is not None
            and any(candidate is grant for candidate in self.grants)
            and self._issued_grants.get(grant.grant_id) is grant
        )
        if self.mutation == "forged_drain_state_authorized":
            retained_grant = grant is not None and any(
                candidate is grant for candidate in self.grants
            )
        if self.mutation == "equal_drain_grant_authorized":
            retained_grant = grant is not None and grant in self.grants
        if (
            grant is None
            or not retained_grant
            or grant.mode != Mode.ESTOP
            or mode != Mode.ESTOP
        ):
            if mode == Mode.ESTOP:
                self.remote_edge_closed = True
                return "REJECTED_REMOTE_EDGE_CLOSED"
            return "REJECTED"
        if self.applied_identity == identity:
            if self.applied_operation is not None:
                self.boundary.replay(self.applied_operation.operation_id)
            return "EXACT_REPLAY"
        if self.remote_edge_closed and self.mutation != "drain_mints_second_token":
            return "REMOTE_EDGE_CLOSED_NO_NEW_EFFECT"
        if self.escalation_tokens_used == 0:
            applied_operation = self.boundary.run(RestrictivePath.DRAIN_ESTOP)
            self.escalation_tokens_used = 1
            self.applied_identity = identity
            self._retained_applied_identity = identity
            self.applied_operation = applied_operation
            self._retained_applied_operation = applied_operation
            if self.mutation != "drain_leaves_remote_edge_open":
                self.remote_edge_closed = True
            return "REMOTE_ESTOP_ACCEPTED"
        if self.mutation == "drain_mints_second_token":
            self.escalation_tokens_used += 1
            self.applied_identity = identity
            self._retained_applied_identity = identity
            return "REMOTE_ESTOP_ACCEPTED"
        return "REMOTE_EDGE_CLOSED_NO_NEW_EFFECT"


def _campaign_drain(model: Model, audit: Audit) -> None:
    drain = DrainMachine(model.mutation)
    drain.exhaust_capacity()
    audit.case()
    preallocated = (
        len(drain.grants) == 1
        and drain.grants[0].mode == Mode.ESTOP
        and drain.grants[0].slot == 1
        and drain.capacity_cut_operation is not None
        and _unified_dag_is_exact(drain.capacity_cut_operation)
        and drain.capacity_cut_operation.severity == Severity.HOLD
    )
    audit.require(preallocated, "drain_grant_preallocated")
    audit.witness("drain_grant_is_preallocated", preallocated)

    active = drain.request_grant(Mode.ACTIVE)
    hold = drain.request_grant(Mode.HOLD)
    first = drain.request_grant(Mode.ESTOP)
    second = drain.request_grant(Mode.ESTOP)
    audit.case(4)
    estop_only = active is None and hold is None
    single_grant = (
        first is not None
        and second == first
        and len({grant.grant_id for grant in drain.grants}) == 1
    )
    audit.require(estop_only, "drain_estop_only")
    audit.require(single_grant, "single_drain_grant")
    audit.witness("drain_has_one_estop_only_grant", estop_only and single_grant)
    if active is None:
        audit.reject()
    if hold is None:
        audit.reject()

    first_result = drain.consume(
        first,
        command_id="drain-estop",
        content_digest="content-a",
        mode=Mode.ESTOP,
    )
    replay_result = drain.consume(
        first,
        command_id="drain-estop",
        content_digest="content-a",
        mode=Mode.ESTOP,
    )
    conflict_result = drain.consume(
        first,
        command_id="drain-estop",
        content_digest="content-b",
        mode=Mode.ESTOP,
    )
    audit.case(3)
    one_token = (
        first_result == "REMOTE_ESTOP_ACCEPTED"
        and replay_result == "EXACT_REPLAY"
        and drain.escalation_tokens_used == 1
        and drain.applied_operation is not None
        and _unified_dag_is_exact(drain.applied_operation)
        and drain.capacity_cut_operation is not None
        and drain.applied_operation.token.token_id
        != drain.capacity_cut_operation.token.token_id
        and drain.applied_operation.fence_epoch
        > drain.capacity_cut_operation.fence_epoch
    )
    audit.require(one_token, "single_drain_token")
    audit.witness("drain_has_one_escalation_token", one_token)
    edge_closed = (
        conflict_result == "REMOTE_EDGE_CLOSED_NO_NEW_EFFECT"
        and drain.remote_edge_closed
        and drain.escalation_tokens_used == 1
        and drain.applied_operation is not None
        and drain.applied_operation.boundary_invocations == 1
    )
    audit.require(edge_closed, "drain_use_closes_remote_edge")
    audit.witness("drain_token_use_closes_remote_edge", edge_closed)


def _campaign_input_closedness(model: Model, audit: Audit) -> None:
    """Challenge exact classes, scalar aliases, containers, and capabilities."""

    class StrAlias(str):
        pass

    class IntAlias(int):
        pass

    class TupleAlias(tuple):
        pass

    class FrozensetAlias(frozenset):
        pass

    class DictAlias(dict):
        pass

    class ListAlias(list):
        pass

    class BodyGrantSubclass(BodyGrant):
        pass

    class CommandCandidateSubclass(CommandCandidate):
        pass

    class TransportCaseSubclass(TransportCase):
        pass

    class IntentCaseSubclass(IntentCase):
        pass

    class EffectCommandSubclass(EffectCommand):
        pass

    class EffectSlotSubclass(EffectSlot):
        pass

    class BoundaryTokenSubclass(BoundaryToken):
        pass

    class RestrictiveTokenSubclass(RestrictiveToken):
        pass

    class UnifiedRestrictiveOperationSubclass(UnifiedRestrictiveOperation):
        pass

    class RetirementClosureEvidenceSubclass(RetirementClosureEvidence):
        pass

    class ActuationAuthorityDomainBindingSubclass(ActuationAuthorityDomainBinding):
        pass

    class ActuationEffectFootprintSubclass(ActuationEffectFootprint):
        pass

    class ActuationAuthorityDomainCreationReceiptSubclass(
        ActuationAuthorityDomainCreationReceipt
    ):
        pass

    class ActuationAuthorityDomainRegistrationSubclass(
        ActuationAuthorityDomainRegistration
    ):
        pass

    class ActiveDurableStateSubclass(ActiveDurableState):
        pass

    class DrainGrantSubclass(DrainGrant):
        pass

    all_rejected = True

    def record(rejected: bool, invariant: str) -> None:
        nonlocal all_rejected
        audit.case()
        if rejected:
            audit.reject()
        all_rejected = all_rejected and rejected
        audit.require(rejected, invariant)

    grant = BodyGrant(
        body_issued=True,
        body_clock="body-clock-exact",
        issue_tick=10,
        max_not_after=20,
        publisher="body-publisher-exact",
        stream_epoch="body-stream-exact",
        slots=(1,),
        modes=frozenset({Mode.ACTIVE}),
    )
    command = CommandCandidate(
        mode=Mode.ACTIVE,
        publisher=grant.publisher,
        stream_epoch=grant.stream_epoch,
        sequence=1,
        ttl_ticks=8,
        sender_tick=11,
        receive_tick=11,
        start_tick=11,
        acceptance_tick=12,
        body_clock=grant.body_clock,
    )
    record(
        not model.body_accepts(BodyGrantSubclass(**grant.__dict__), command),
        "body_input_types_closed",
    )
    record(
        not model.body_accepts(
            grant,
            CommandCandidateSubclass(**command.__dict__),
        ),
        "body_input_types_closed",
    )
    record(
        not model.body_accepts(
            BodyGrant(
                **{
                    **grant.__dict__,
                    "body_clock": StrAlias(grant.body_clock),
                }
            ),
            command,
        ),
        "body_input_types_closed",
    )
    record(
        not _body_oracle(
            grant,
            CommandCandidate(**{**command.__dict__, "mode": "ACTIVE"}),
        ),
        "body_input_types_closed",
    )
    record(
        not _body_oracle(
            BodyGrant(
                **{
                    **grant.__dict__,
                    "slots": TupleAlias((1,)),
                    "modes": frozenset({"ACTIVE"}),
                }
            ),
            command,
        ),
        "body_input_types_closed",
    )
    record(
        not model.body_accepts(
            grant,
            CommandCandidate(**{**command.__dict__, "mode": "ACTIVE"}),
        ),
        "body_input_types_closed",
    )
    record(
        not model.body_accepts(
            BodyGrant(**{**grant.__dict__, "body_issued": 1}),
            command,
        ),
        "body_input_types_closed",
    )
    record(
        not model.body_accepts(
            BodyGrant(**{**grant.__dict__, "slots": [1]}),
            command,
        ),
        "body_input_types_closed",
    )
    record(
        not model.body_accepts(
            BodyGrant(**{**grant.__dict__, "slots": TupleAlias((1,))}),
            command,
        ),
        "body_input_types_closed",
    )
    record(
        not model.body_accepts(
            BodyGrant(
                **{
                    **grant.__dict__,
                    "modes": FrozensetAlias({Mode.ACTIVE}),
                }
            ),
            command,
        ),
        "body_input_types_closed",
    )
    record(
        not model.body_accepts(
            BodyGrant(**{**grant.__dict__, "modes": frozenset({"ACTIVE"})}),
            command,
        ),
        "body_input_types_closed",
    )
    record(
        not model.body_accepts(
            grant,
            CommandCandidate(**{**command.__dict__, "acceptance_tick": IntAlias(12)}),
        ),
        "body_input_types_closed",
    )
    record(
        not model.body_accepts(
            grant,
            CommandCandidate(
                **{
                    **command.__dict__,
                    "proposed_retry_deadline": False,
                }
            ),
        ),
        "body_input_types_closed",
    )

    transport = TransportCase(
        start_tick=11,
        acceptance_tick=12,
        original_deadline=20,
        proof=EndpointProof.ACCEPTED,
        gate_order=GateOrder.NO_FENCE,
        resolution_tick=13,
    )
    for hostile_transport in (
        TransportCaseSubclass(**transport.__dict__),
        TransportCase(**{**transport.__dict__, "proof": "ACCEPTED"}),
        TransportCase(**{**transport.__dict__, "gate_order": "NO_FENCE"}),
        TransportCase(**{**transport.__dict__, "local_return_success": 1}),
        TransportCase(**{**transport.__dict__, "acceptance_tick": IntAlias(12)}),
    ):
        record(
            model.transport_disposition(hostile_transport)
            == TransportDisposition.INVALID_EVIDENCE,
            "transport_input_types_closed",
        )
    record(
        _transport_oracle(
            TransportCase(
                **{
                    **transport.__dict__,
                    "proof": "ACCEPTED",
                    "gate_order": "NO_FENCE",
                }
            )
        )
        == TransportDisposition.INVALID_EVIDENCE,
        "transport_input_types_closed",
    )

    intent = IntentCase(True, 10, 20, 8, 11, 11, 12)
    record(
        not model.intent_accepts(IntentCaseSubclass(**intent.__dict__)),
        "intent_input_types_closed",
    )
    record(
        not model.intent_accepts(
            IntentCase(**{**intent.__dict__, "receiver_issued_grant": 1})
        ),
        "intent_input_types_closed",
    )
    record(
        not model.intent_accepts(
            IntentCase(**{**intent.__dict__, "acceptance_tick": IntAlias(12)})
        )
        and not _intent_oracle(
            IntentCase(**{**intent.__dict__, "acceptance_tick": IntAlias(12)})
        ),
        "intent_input_types_closed",
    )

    effect = EffectCommand("exact-effect", 1, "content", "signature", Mode.HOLD)
    record(
        EffectJournal(model.mutation).submit(EffectCommandSubclass(**effect.__dict__))
        == ("INVALID_COMMAND", None),
        "effect_command_input_types_closed",
    )
    record(
        EffectJournal(model.mutation).submit(
            EffectCommand(**{**effect.__dict__, "mode": "HOLD"})
        )
        == ("INVALID_COMMAND", None),
        "effect_command_input_types_closed",
    )
    record(
        EffectJournal(model.mutation).submit(
            EffectCommand(**{**effect.__dict__, "position": True})
        )
        == ("INVALID_COMMAND", None),
        "effect_command_input_types_closed",
    )
    record(
        EffectJournal(model.mutation).submit(
            EffectCommand(**{**effect.__dict__, "position": IntAlias(1)})
        )
        == ("INVALID_COMMAND", None),
        "effect_command_input_types_closed",
    )
    record(
        EffectJournal(model.mutation).submit(
            EffectCommand(
                **{**effect.__dict__, "command_id": StrAlias(effect.command_id)}
            )
        )
        == ("INVALID_COMMAND", None),
        "effect_command_input_types_closed",
    )
    token_journal = EffectJournal(model.mutation)
    _effect_result, effect_token = token_journal.submit(effect)
    if effect_token is None:
        raise ProbeError("exact-type fixture did not allocate an effect token")
    record(
        token_journal.complete(StrAlias(effect_token)) == "INVALID_TOKEN",
        "effect_command_input_types_closed",
    )
    slot_state_journal = EffectJournal(model.mutation)
    active_effect = EffectCommand(
        "active-state-exact",
        2,
        "active-state-content",
        "active-state-signature",
        Mode.ACTIVE,
    )
    slot_state_journal.submit(active_effect)
    slot_key = next(iter(slot_state_journal.slots))
    slot_state_journal.slots[slot_key] = EffectSlotSubclass(
        **slot_state_journal.slots[slot_key].__dict__
    )
    record(
        slot_state_journal.submit(active_effect) == ("INVALID_STATE", None),
        "effect_command_input_types_closed",
    )
    token_state_journal = EffectJournal(model.mutation)
    _token_state_result, token_state_id = token_state_journal.submit(effect)
    if token_state_id is None:
        raise ProbeError("exact-type fixture did not allocate a state token")
    token_state_journal.tokens[token_state_id] = BoundaryTokenSubclass(
        **token_state_journal.tokens[token_state_id].__dict__
    )
    record(
        token_state_journal.complete(token_state_id) == "INVALID_TOKEN",
        "effect_command_input_types_closed",
    )

    path_boundary = UnifiedPhysicalBoundary(model.mutation)
    try:
        path_boundary.start("INITIAL_ESTOP")
    except ProbeError:
        path_alias_rejected = True
    else:
        path_alias_rejected = False
    record(path_alias_rejected, "restrictive_path_input_types_closed")

    cut_boundary = UnifiedPhysicalBoundary(model.mutation)
    try:
        cut_boundary.advance_to_cut(
            RestrictivePath.INITIAL_ESTOP,
            "AFTER_ARBITER_PENDING",
        )
    except ProbeError:
        cut_alias_rejected = True
    else:
        cut_alias_rejected = False
    record(cut_alias_rejected, "restrictive_path_input_types_closed")

    operation_boundary = UnifiedPhysicalBoundary(model.mutation)
    retained_operation = operation_boundary.start(RestrictivePath.INITIAL_HOLD)
    foreign_operation = copy.deepcopy(retained_operation)
    record(
        not operation_boundary.mirror(foreign_operation),
        "restrictive_operation_capability_identity",
    )
    operation_subclass = UnifiedRestrictiveOperationSubclass(
        **{
            **retained_operation.__dict__,
            "events": list(retained_operation.events),
        }
    )
    record(
        not operation_boundary.mirror(operation_subclass),
        "restrictive_operation_capability_identity",
    )
    token_subclass_boundary = UnifiedPhysicalBoundary(model.mutation)
    token_subclass_operation = token_subclass_boundary.start(
        RestrictivePath.INITIAL_HOLD
    )
    token_subclass_operation.token = RestrictiveTokenSubclass(
        **token_subclass_operation.token.__dict__
    )
    record(
        not token_subclass_boundary.mirror(token_subclass_operation),
        "restrictive_operation_capability_identity",
    )
    try:
        operation_boundary.replay(StrAlias(retained_operation.operation_id))
    except ProbeError:
        replay_alias_rejected = True
    else:
        replay_alias_rejected = False
    record(replay_alias_rejected, "restrictive_operation_capability_identity")

    retirement_machine = RetirementClosureMachine(model.mutation)
    evidence = RetirementClosureEvidence(
        kind=RetirementClosureKind.EXACT_ARBITER_RETIREMENT,
        hold_state=HoldBoundaryLifecycle.NONE,
        estop_floor=EstopLifecycleFloor.NONE,
        pending_hold_closed=False,
        exact_terminal_hold_result_preserved=False,
        physical_isolation_proved=False,
        closure_id="exact-type-retirement-evidence",
    )
    record(
        not retirement_machine.can_finalize(
            RetirementClosureEvidenceSubclass(**evidence.__dict__),
            RetirementAuthorization.NON_SPECIALIZED,
        ),
        "retirement_evidence_types_closed",
    )
    record(
        not retirement_machine.can_finalize(
            RetirementClosureEvidence(
                **{**evidence.__dict__, "pending_hold_closed": 0}
            ),
            RetirementAuthorization.NON_SPECIALIZED,
        ),
        "retirement_evidence_types_closed",
    )
    record(
        not retirement_machine.can_finalize(
            evidence,
            "NON_SPECIALIZED",
        ),
        "retirement_evidence_types_closed",
    )
    record(
        retirement_machine.install_closure(
            kind=RetirementClosureKind.EXACT_ARBITER_RETIREMENT,
            hold_state=HoldBoundaryLifecycle.NONE,
            physical_isolation_proof=0,
        )
        is None,
        "retirement_evidence_types_closed",
    )

    domain_key = hashlib.sha256(b"exact-type-domain").hexdigest()
    binding = ActuationAuthorityDomainBinding(
        session_id="exact-session",
        generation_id="exact-generation",
        generation_domain_keys=(domain_key,),
        arbiter_mirror_domain_key=domain_key,
        actuator_domain_keys=(domain_key,),
        atomic_success_claimed=True,
        qualified_atomic_boundary=True,
    )
    binding_model = ActuationDomainBindingModel(model.mutation)
    record(
        not binding_model.accepts(
            ActuationAuthorityDomainBindingSubclass(**binding.__dict__)
        ),
        "actuation_binding_types_closed",
    )
    record(
        not binding_model.accepts(
            ActuationAuthorityDomainBinding(
                **{**binding.__dict__, "atomic_success_claimed": 1}
            )
        ),
        "actuation_binding_types_closed",
    )
    record(
        not binding_model.accepts(
            ActuationAuthorityDomainBinding(
                **{**binding.__dict__, "generation_domain_keys": [domain_key]}
            )
        ),
        "actuation_binding_types_closed",
    )

    registration = _domain_registration(
        domain_key=domain_key,
        session_id="registration-session",
        generation_id="registration-generation",
        footprint=_effect_footprint("registration-exact"),
        prior_selector_version=0,
    )
    registration_subclass = ActuationAuthorityDomainRegistrationSubclass(
        **registration.__dict__
    )
    record(
        not InstalledActuationAuthorityDomainSelector(model.mutation).register(
            registration_subclass
        ),
        "actuation_registration_types_closed",
    )
    receipt_subclass = ActuationAuthorityDomainCreationReceiptSubclass(
        **registration.creation_receipt.__dict__
    )
    registration_with_receipt_subclass = ActuationAuthorityDomainRegistration(
        **{**registration.__dict__, "creation_receipt": receipt_subclass}
    )
    record(
        not InstalledActuationAuthorityDomainSelector(model.mutation).register(
            registration_with_receipt_subclass
        ),
        "actuation_registration_types_closed",
    )
    footprint_subclass = ActuationEffectFootprintSubclass(
        **registration.footprint.__dict__
    )
    registration_with_footprint_subclass = ActuationAuthorityDomainRegistration(
        **{**registration.__dict__, "footprint": footprint_subclass}
    )
    record(
        not InstalledActuationAuthorityDomainSelector(model.mutation).register(
            registration_with_footprint_subclass
        ),
        "actuation_registration_types_closed",
    )

    receipt_selector = InstalledActuationAuthorityDomainSelector(model.mutation)
    if not receipt_selector.register(registration):
        raise ProbeError("exact-type fixture could not register its domain")
    equal_receipt = ActuationAuthorityDomainCreationReceipt(
        **registration.creation_receipt.__dict__
    )
    record(
        not receipt_selector.reserve(
            requested_domain_key=registration.domain_key,
            creation_receipt=equal_receipt,
            expected_selector_version=1,
        ),
        "creation_receipt_capability_identity",
    )
    container_selector = InstalledActuationAuthorityDomainSelector(model.mutation)
    if not container_selector.register(registration):
        raise ProbeError("exact-type container fixture could not register its domain")
    container_selector.registry = DictAlias(container_selector.registry)
    record(
        not container_selector.reserve(
            requested_domain_key=registration.domain_key,
            creation_receipt=registration.creation_receipt,
            expected_selector_version=1,
        ),
        "actuation_registration_types_closed",
    )
    record(
        not receipt_selector.reserve(
            requested_domain_key=registration.domain_key,
            creation_receipt=registration.creation_receipt,
            expected_selector_version=True,
        ),
        "creation_receipt_capability_identity",
    )
    record(
        not receipt_selector.reserve(
            requested_domain_key=StrAlias(registration.domain_key),
            creation_receipt=registration.creation_receipt,
            expected_selector_version=1,
        ),
        "creation_receipt_capability_identity",
    )

    topology_selector = InstalledActuationAuthorityDomainSelector(model.mutation)
    if not topology_selector.register(registration):
        raise ProbeError("exact-type topology fixture could not register its domain")
    replacement_digest = hashlib.sha256(b"exact-type-topology").hexdigest()
    replacement_registration = _domain_registration(
        domain_key=hashlib.sha256(b"exact-type-replacement-domain").hexdigest(),
        session_id=registration.session_id,
        generation_id=registration.generation_id,
        footprint=_effect_footprint("replacement-exact"),
        prior_selector_version=0,
        topology_digest=replacement_digest,
    )
    record(
        not topology_selector.replace_topology(
            new_topology_digest=replacement_digest,
            fenced_domain_keys={registration.domain_key},
            physical_isolation_proved=True,
            replacement_registrations=(replacement_registration,),
        ),
        "actuation_registration_types_closed",
    )
    record(
        not topology_selector.replace_topology(
            new_topology_digest=replacement_digest,
            fenced_domain_keys=FrozensetAlias({registration.domain_key}),
            physical_isolation_proved=True,
            replacement_registrations=(replacement_registration,),
        ),
        "actuation_registration_types_closed",
    )
    record(
        not topology_selector.replace_topology(
            new_topology_digest=replacement_digest,
            fenced_domain_keys=frozenset({registration.domain_key}),
            physical_isolation_proved=1,
            replacement_registrations=(replacement_registration,),
        ),
        "actuation_registration_types_closed",
    )
    record(
        not topology_selector.replace_topology(
            new_topology_digest=replacement_digest,
            fenced_domain_keys=frozenset({registration.domain_key}),
            physical_isolation_proved=True,
            replacement_registrations=TupleAlias((replacement_registration,)),
        ),
        "actuation_registration_types_closed",
    )
    record(
        not topology_selector.replace_topology(
            new_topology_digest=replacement_digest,
            fenced_domain_keys=frozenset({registration.domain_key}),
            physical_isolation_proved=True,
            replacement_registrations=[replacement_registration],
        ),
        "actuation_registration_types_closed",
    )

    scope_selector = InstalledActuationAuthorityDomainSelector(
        model.mutation,
        jurisdiction_key=StrAlias(PHYSICAL_ACTUATION_JURISDICTION_KEY),
    )
    record(
        not scope_selector.register(registration),
        "actuation_registration_types_closed",
    )
    directory = InstalledPhysicalActuationJurisdictionDirectory(model.mutation)
    record(
        not directory.enroll(
            selector_id=StrAlias("exact-selector"),
            jurisdiction_key=PHYSICAL_ACTUATION_JURISDICTION_KEY,
            jurisdiction_incarnation=PHYSICAL_ACTUATION_JURISDICTION_INCARNATION,
        ),
        "actuation_registration_types_closed",
    )

    def active_input_was_rejected(**overrides: Any) -> bool:
        boundary = ActiveBoundary(model.mutation)
        arguments: dict[str, Any] = {
            "value_digest": "active-exact",
            "acceptance_tick": 11,
            "command_deadline": 20,
            "lease_deadline": 21,
            "crash_cut": CrashCut.AFTER_COMMIT,
        }
        arguments.update(overrides)
        try:
            boundary.accept(**arguments)
        except ProbeError:
            pass
        return (
            boundary.state.mode != Mode.ACTIVE
            and boundary.state.value_digest is None
            and boundary.state.accepted_attempts == 0
        )

    record(
        active_input_was_rejected(crash_cut="AFTER_COMMIT"),
        "active_input_types_closed",
    )
    record(
        active_input_was_rejected(acceptance_tick=True),
        "active_input_types_closed",
    )
    record(
        active_input_was_rejected(acceptance_tick=IntAlias(11)),
        "active_input_types_closed",
    )
    record(
        active_input_was_rejected(value_digest=StrAlias("active-exact")),
        "active_input_types_closed",
    )
    state_boundary = ActiveBoundary(model.mutation)
    state_boundary.state = ActiveDurableStateSubclass(
        value_digest="forged-active",
        watchdog_deadline=20,
        watchdog_clock="body-clock-forged",
        accepted_attempts=1,
        mode=Mode.ACTIVE,
    )
    state_boundary.replay(12)
    record(
        type(state_boundary.state) is ActiveDurableState
        and state_boundary.state.mode == Mode.HOLD
        and state_boundary.state.value_digest is None
        and state_boundary.state.local_restrictive_receipt,
        "active_input_types_closed",
    )

    drain_input_mutation = (
        model.mutation
        if model.mutation
        in {
            "drain_type_aliases_authorize",
            "equal_drain_grant_authorized",
        }
        else None
    )
    request_drain = DrainMachine(drain_input_mutation)
    request_drain.exhaust_capacity()
    record(
        request_drain.request_grant("ESTOP") is None,
        "drain_input_types_closed",
    )

    raw_mode_drain = DrainMachine(drain_input_mutation)
    raw_mode_drain.exhaust_capacity()
    raw_mode_grant = raw_mode_drain.request_grant(Mode.ESTOP)
    raw_mode_result = raw_mode_drain.consume(
        raw_mode_grant,
        command_id="raw-mode-drain",
        content_digest="raw-mode-content",
        mode="ESTOP",
    )
    record(
        raw_mode_result not in {"REMOTE_ESTOP_ACCEPTED", "EXACT_REPLAY"}
        and raw_mode_drain.escalation_tokens_used == 0,
        "drain_input_types_closed",
    )

    equal_grant_drain = DrainMachine(drain_input_mutation)
    equal_grant_drain.exhaust_capacity()
    retained_grant = equal_grant_drain.request_grant(Mode.ESTOP)
    if retained_grant is None:
        raise ProbeError("exact-type fixture lacks its retained drain grant")
    equal_grant = DrainGrant(**retained_grant.__dict__)
    equal_grant_result = equal_grant_drain.consume(
        equal_grant,
        command_id="equal-grant-drain",
        content_digest="equal-grant-content",
        mode=Mode.ESTOP,
    )
    record(
        equal_grant_result not in {"REMOTE_ESTOP_ACCEPTED", "EXACT_REPLAY"}
        and equal_grant_drain.escalation_tokens_used == 0,
        "drain_grant_capability_identity",
    )

    subclass_grant_drain = DrainMachine(drain_input_mutation)
    subclass_grant_drain.exhaust_capacity()
    subclass_retained = subclass_grant_drain.request_grant(Mode.ESTOP)
    if subclass_retained is None:
        raise ProbeError("exact-type fixture lacks its subclass drain grant")
    subclass_result = subclass_grant_drain.consume(
        DrainGrantSubclass(**subclass_retained.__dict__),
        command_id="subclass-grant-drain",
        content_digest="subclass-grant-content",
        mode=Mode.ESTOP,
    )
    record(
        subclass_result not in {"REMOTE_ESTOP_ACCEPTED", "EXACT_REPLAY"}
        and subclass_grant_drain.escalation_tokens_used == 0,
        "drain_input_types_closed",
    )
    int_slot_grant_drain = DrainMachine(drain_input_mutation)
    int_slot_grant_drain.exhaust_capacity()
    int_slot_retained = int_slot_grant_drain.request_grant(Mode.ESTOP)
    if int_slot_retained is None:
        raise ProbeError("exact-type fixture lacks its integer-slot drain grant")
    int_slot_result = int_slot_grant_drain.consume(
        DrainGrant(
            **{
                **int_slot_retained.__dict__,
                "slot": IntAlias(int_slot_retained.slot),
            }
        ),
        command_id="integer-slot-drain",
        content_digest="integer-slot-content",
        mode=Mode.ESTOP,
    )
    record(
        int_slot_result not in {"REMOTE_ESTOP_ACCEPTED", "EXACT_REPLAY"}
        and int_slot_grant_drain.escalation_tokens_used == 0,
        "drain_input_types_closed",
    )

    command_alias_drain = DrainMachine(drain_input_mutation)
    command_alias_drain.exhaust_capacity()
    command_alias_grant = command_alias_drain.request_grant(Mode.ESTOP)
    command_alias_result = command_alias_drain.consume(
        command_alias_grant,
        command_id=StrAlias("command-alias-drain"),
        content_digest="command-alias-content",
        mode=Mode.ESTOP,
    )
    record(
        command_alias_result not in {"REMOTE_ESTOP_ACCEPTED", "EXACT_REPLAY"}
        and command_alias_drain.escalation_tokens_used == 0,
        "drain_input_types_closed",
    )
    grant_container_drain = DrainMachine(drain_input_mutation)
    grant_container_drain.exhaust_capacity()
    grant_container_drain.grants = ListAlias(grant_container_drain.grants)
    record(
        grant_container_drain.request_grant(Mode.ESTOP) is None,
        "drain_input_types_closed",
    )

    audit.witness(
        "all_authority_inputs_use_exact_closed_types_and_capability_identity",
        all_rejected,
    )


def _campaign_semantic_state_closure(model: Model, audit: Audit) -> None:
    """Challenge retained-state unions, provenance, indexes, and identifier bounds."""

    all_rejected = True

    def record(rejected: bool, invariant: str) -> None:
        nonlocal all_rejected
        audit.case()
        if rejected:
            audit.reject()
        all_rejected = all_rejected and rejected
        audit.require(rejected, invariant)

    effect_mutation = (
        model.mutation if model.mutation == "orphan_effect_token_authorized" else None
    )
    orphan_journal = EffectJournal(effect_mutation)
    orphan_identifier = f"boundary-token-{orphan_journal._token_counter}"
    orphan_token = BoundaryToken(
        severity=Severity.HOLD,
        token_id=orphan_identifier,
        slot_key=0,
        command_id="orphan-command",
        reservation_ordinal=0,
        reservation_transition=0,
    )
    orphan_journal.tokens[orphan_token.token_id] = orphan_token
    orphan_journal._token_counter = 1
    orphan_journal._transition_counter = 1
    orphan_result = orphan_journal.complete(orphan_token.token_id)
    record(
        orphan_result not in {"APPLIED_HOLD", "ALREADY_TERMINAL"}
        and not orphan_journal.completion_log,
        "effect_token_provenance_closed",
    )

    mismatched_token_journal = EffectJournal(effect_mutation)
    _mismatch_result, mismatch_token_id = mismatched_token_journal.submit(
        _command("mismatch-command", 1, "mismatch-content", Mode.HOLD)
    )
    if mismatch_token_id is None:
        raise ProbeError("semantic fixture did not allocate its effect token")
    mismatched_token_journal.tokens[mismatch_token_id].slot_key = 99
    record(
        mismatched_token_journal.complete(mismatch_token_id)
        in {"INVALID_TOKEN", "INVALID_STATE"},
        "effect_token_provenance_closed",
    )

    forged_terminal_journal = EffectJournal(effect_mutation)
    _forged_result, forged_token_id = forged_terminal_journal.submit(
        _command("forged-terminal", 2, "forged-terminal-content", Mode.HOLD)
    )
    if forged_token_id is None:
        raise ProbeError("semantic fixture did not allocate its terminal token")
    forged_token = forged_terminal_journal.tokens[forged_token_id]
    forged_token.terminal_result = "APPLIED_HOLD"
    forged_token.completion_ordinal = 0
    forged_token.completion_transition = 1
    forged_terminal_journal._transition_counter = 2
    record(
        forged_terminal_journal.complete(forged_token_id)
        in {"INVALID_TOKEN", "INVALID_STATE"},
        "effect_token_provenance_closed",
    )

    priority_journal = EffectJournal(effect_mutation)
    _priority_hold_result, priority_hold_id = priority_journal.submit(
        _command("priority-hold", 4, "priority-hold-content", Mode.HOLD)
    )
    _priority_estop_result, priority_estop_id = priority_journal.submit(
        _command("priority-estop", 5, "priority-estop-content", Mode.ESTOP)
    )
    if priority_hold_id is None or priority_estop_id is None:
        raise ProbeError("semantic priority fixture did not allocate both tokens")
    priority_hold = priority_journal.tokens[priority_hold_id]
    priority_hold.terminal_result = "APPLIED_HOLD"
    priority_hold.completion_ordinal = 0
    priority_hold.completion_transition = 2
    priority_journal._transition_counter = 3
    priority_journal.completion_log = ["APPLIED_HOLD"]
    priority_journal.highest_accepted = Severity.HOLD
    record(
        not priority_journal._state_is_exact(),
        "effect_token_provenance_closed",
    )

    mismatched_count_journal = EffectJournal(effect_mutation)
    mismatched_count_journal.submit(
        _command("mismatched-count", 3, "mismatched-count-content", Mode.HOLD)
    )
    next(iter(mismatched_count_journal.slots.values())).restrictive_operations = 0
    record(
        not mismatched_count_journal._state_is_exact(),
        "effect_token_provenance_closed",
    )

    restrictive_mutation = (
        model.mutation
        if model.mutation == "forged_restrictive_state_authorized"
        else None
    )
    forged_boundary = UnifiedPhysicalBoundary(restrictive_mutation)
    forged_operation = forged_boundary.advance_to_cut(
        RestrictivePath.INITIAL_HOLD,
        RestrictiveCrashCut.AFTER_BODY_MIRROR,
    )
    forged_operation.events = [
        "ARBITER_PENDING",
        "PHYSICAL_BOUNDARY_INVOCATION",
    ]
    forged_operation.boundary_result = "APPLIED_HOLD"
    try:
        recovered_forgery = forged_boundary.recover(forged_operation)
    except ProbeError:
        forged_recovery_rejected = True
    else:
        forged_recovery_rejected = not (
            recovered_forgery.arbiter_resolved
            and recovered_forgery.boundary_result == "APPLIED_HOLD"
            and recovered_forgery.boundary_invocations == 0
            and recovered_forgery.physical_effects == 0
            and recovered_forgery.body_completions == 1
        )
    record(
        forged_recovery_rejected,
        "restrictive_retained_state_closed",
    )

    def restrictive_state_at(
        cut: RestrictiveCrashCut,
    ) -> tuple[UnifiedPhysicalBoundary, UnifiedRestrictiveOperation]:
        boundary = UnifiedPhysicalBoundary(restrictive_mutation)
        operation = boundary.advance_to_cut(
            RestrictivePath.INITIAL_HOLD,
            cut,
        )
        return boundary, operation

    prefix_mutations: list[
        tuple[UnifiedPhysicalBoundary, UnifiedRestrictiveOperation]
    ] = []
    boundary, operation = restrictive_state_at(
        RestrictiveCrashCut.AFTER_ARBITER_PENDING
    )
    operation.boundary_result = "APPLIED_HOLD"
    prefix_mutations.append((boundary, operation))
    boundary, operation = restrictive_state_at(RestrictiveCrashCut.AFTER_BODY_MIRROR)
    operation.boundary_invocations = 1
    prefix_mutations.append((boundary, operation))
    boundary, operation = restrictive_state_at(
        RestrictiveCrashCut.AFTER_BOUNDARY_INVOCATION
    )
    operation.physical_effects = 0
    prefix_mutations.append((boundary, operation))
    boundary, operation = restrictive_state_at(
        RestrictiveCrashCut.AFTER_ARBITER_RESOLUTION
    )
    operation.arbiter_resolved = False
    prefix_mutations.append((boundary, operation))
    terminal_boundary = UnifiedPhysicalBoundary(restrictive_mutation)
    terminal_operation = terminal_boundary.run(RestrictivePath.INITIAL_HOLD)
    terminal_operation.body_completions = 0
    prefix_mutations.append((terminal_boundary, terminal_operation))
    pending_boundary, pending_operation = restrictive_state_at(
        RestrictiveCrashCut.AFTER_ARBITER_PENDING
    )
    pending_boundary.pending.clear()
    prefix_mutations.append((pending_boundary, pending_operation))
    token_boundary, token_operation = restrictive_state_at(
        RestrictiveCrashCut.AFTER_ARBITER_PENDING
    )
    token_boundary._used_token_ids.add("unowned-token")
    prefix_mutations.append((token_boundary, token_operation))
    for boundary, _operation in prefix_mutations:
        record(
            not boundary._state_is_exact(),
            "restrictive_retained_state_closed",
        )
    unexpected_predecessor_boundary = UnifiedPhysicalBoundary(restrictive_mutation)
    unexpected_predecessor = unexpected_predecessor_boundary.run(
        RestrictivePath.INITIAL_HOLD
    )
    try:
        unexpected_predecessor_boundary.start(
            RestrictivePath.DRAIN_ESTOP,
            predecessor=unexpected_predecessor,
        )
    except ProbeError:
        unexpected_predecessor_rejected = True
    else:
        unexpected_predecessor_rejected = False
    record(
        unexpected_predecessor_rejected,
        "restrictive_retained_state_closed",
    )

    replay_mutation = (
        model.mutation
        if model.mutation == "incomplete_restrictive_replay_authorized"
        else None
    )
    incomplete_replay_boundary = UnifiedPhysicalBoundary(replay_mutation)
    incomplete_replay = incomplete_replay_boundary.advance_to_cut(
        RestrictivePath.INITIAL_HOLD,
        RestrictiveCrashCut.AFTER_ARBITER_PENDING,
    )
    try:
        incomplete_replay_boundary.replay(incomplete_replay.operation_id)
    except ProbeError:
        incomplete_replay_rejected = True
    else:
        incomplete_replay_rejected = False
    record(
        incomplete_replay_rejected,
        "restrictive_replay_terminal_only",
    )

    retirement_mutation = (
        model.mutation
        if model.mutation
        in {
            "caller_constructed_retirement_evidence_authorized",
            "retirement_isolation_proof_equality_authorized",
        }
        else None
    )
    retirement_machine = RetirementClosureMachine(retirement_mutation)
    isolation_proof = retirement_machine.physical_isolation_proof()
    constructed_isolation = RetirementClosureEvidence(
        kind=RetirementClosureKind.LOST_ARBITER_PHYSICAL_ISOLATION,
        hold_state=HoldBoundaryLifecycle.NONE,
        estop_floor=EstopLifecycleFloor.NONE,
        pending_hold_closed=False,
        exact_terminal_hold_result_preserved=False,
        physical_isolation_proved=True,
        closure_id="caller-constructed-isolation",
        physical_isolation_proof_id=isolation_proof.proof_id,
    )
    record(
        not retirement_machine.can_finalize(
            constructed_isolation,
            RetirementAuthorization.NON_SPECIALIZED,
        ),
        "retirement_evidence_issuer_identity",
    )
    installed_exact = retirement_machine.install_closure(
        kind=RetirementClosureKind.EXACT_ARBITER_RETIREMENT,
        hold_state=HoldBoundaryLifecycle.NONE,
    )
    if installed_exact is None:
        raise ProbeError("semantic retirement fixture did not install exact evidence")
    equal_installed = RetirementClosureEvidence(**installed_exact.__dict__)
    record(
        not retirement_machine.can_finalize(
            equal_installed,
            RetirementAuthorization.NON_SPECIALIZED,
        ),
        "retirement_evidence_issuer_identity",
    )
    registry_machine = RetirementClosureMachine(retirement_mutation)
    registry_evidence = registry_machine.install_closure(
        kind=RetirementClosureKind.EXACT_ARBITER_RETIREMENT,
        hold_state=HoldBoundaryLifecycle.NONE,
    )
    if registry_evidence is None:
        raise ProbeError("semantic retirement registry fixture was not installed")
    registry_replacement = RetirementClosureEvidence(**registry_evidence.__dict__)
    registry_machine._installed_evidence[registry_evidence.closure_id] = (
        registry_replacement
    )
    record(
        not registry_machine.can_finalize(
            registry_replacement,
            RetirementAuthorization.NON_SPECIALIZED,
        ),
        "retirement_evidence_issuer_identity",
    )
    equal_isolation_proof = PhysicalIsolationProof(isolation_proof.proof_id)
    record(
        retirement_machine.install_closure(
            kind=RetirementClosureKind.LOST_ARBITER_PHYSICAL_ISOLATION,
            hold_state=HoldBoundaryLifecycle.HOLD_PENDING,
            physical_isolation_proof=equal_isolation_proof,
        )
        is None,
        "physical_isolation_capability_identity",
    )

    active_mutation = (
        model.mutation
        if model.mutation == "caller_constructed_active_state_authorized"
        else None
    )
    active_without_watchdog = ActiveBoundary(active_mutation)
    active_without_watchdog.state = ActiveDurableState(mode=Mode.ACTIVE)
    active_without_watchdog.advance(100)
    record(
        active_without_watchdog.state.mode == Mode.HOLD
        and active_without_watchdog.state.state_kind
        == ActiveStateKind.FAIL_CLOSED_HOLD,
        "active_retained_state_closed",
    )
    plausible_active = ActiveBoundary(active_mutation)
    plausible_active.state = ActiveDurableState(
        value_digest="plausible-active",
        watchdog_deadline=200,
        watchdog_clock="body-clock-plausible",
        accepted_attempts=1,
        mode=Mode.ACTIVE,
        state_kind=ActiveStateKind.ACTIVE,
        revision=1,
    )
    plausible_active.advance(100)
    record(
        plausible_active.state.mode == Mode.HOLD
        and plausible_active.state.state_kind == ActiveStateKind.FAIL_CLOSED_HOLD,
        "active_retained_state_closed",
    )
    mutated_retained_active = ActiveBoundary(active_mutation)
    mutated_retained_active.state.mode = Mode.ACTIVE
    mutated_retained_active.advance(100)
    record(
        mutated_retained_active.state.mode == Mode.HOLD
        and mutated_retained_active.state.state_kind
        == ActiveStateKind.FAIL_CLOSED_HOLD,
        "active_retained_state_closed",
    )
    coherent_in_place_active = ActiveBoundary(active_mutation)
    coherent_in_place_active.state.value_digest = "coherent-in-place-active"
    coherent_in_place_active.state.watchdog_deadline = 200
    coherent_in_place_active.state.watchdog_clock = "body-clock-coherent"
    coherent_in_place_active.state.accepted_attempts = 1
    coherent_in_place_active.state.mode = Mode.ACTIVE
    coherent_in_place_active.state.state_kind = ActiveStateKind.ACTIVE
    coherent_in_place_active.state.revision = 1
    coherent_in_place_active.advance(100)
    record(
        coherent_in_place_active.state.mode == Mode.HOLD
        and coherent_in_place_active.state.state_kind
        == ActiveStateKind.FAIL_CLOSED_HOLD,
        "active_retained_state_closed",
    )

    selector_mutation = (
        model.mutation if model.mutation == "selector_derived_state_unchecked" else None
    )
    selector_domain_a = hashlib.sha256(b"semantic-selector-domain-a").hexdigest()
    selector_domain_b = hashlib.sha256(b"semantic-selector-domain-b").hexdigest()
    owner_selector = InstalledActuationAuthorityDomainSelector(selector_mutation)
    owner_registration = _domain_registration(
        domain_key=selector_domain_a,
        session_id="semantic-owner-session",
        generation_id="semantic-owner-generation",
        footprint=_effect_footprint("semantic-owner"),
        prior_selector_version=0,
    )
    if not owner_selector.register(owner_registration):
        raise ProbeError("semantic selector fixture could not register owner")
    owner_selector.generation_owner.clear()
    owner_reserved = owner_selector.reserve(
        requested_domain_key=selector_domain_a,
        creation_receipt=owner_registration.creation_receipt,
        expected_selector_version=1,
    )
    record(
        not owner_reserved,
        "selector_derived_state_exact",
    )

    conflict_selector = InstalledActuationAuthorityDomainSelector(selector_mutation)
    conflict_footprint_a = _effect_footprint("semantic-conflict-a")
    shared_active = conflict_footprint_a.active[0]
    conflict_registration_a = _domain_registration(
        domain_key=selector_domain_a,
        session_id="semantic-conflict-session-a",
        generation_id="semantic-conflict-generation-a",
        footprint=conflict_footprint_a,
        prior_selector_version=0,
    )
    conflict_registration_b = _domain_registration(
        domain_key=selector_domain_b,
        session_id="semantic-conflict-session-b",
        generation_id="semantic-conflict-generation-b",
        footprint=_effect_footprint(
            "semantic-conflict-b",
            overlap_channel="active",
            shared_resource=shared_active,
        ),
        prior_selector_version=1,
    )
    if not (
        conflict_selector.register(conflict_registration_a)
        and conflict_selector.register(conflict_registration_b)
    ):
        raise ProbeError("semantic selector fixture could not register conflicts")
    conflict_selector.conflict_graph.clear()
    conflict_first = conflict_selector.reserve(
        requested_domain_key=selector_domain_a,
        creation_receipt=conflict_registration_a.creation_receipt,
        expected_selector_version=2,
    )
    conflict_second = conflict_selector.reserve(
        requested_domain_key=selector_domain_b,
        creation_receipt=conflict_registration_b.creation_receipt,
        expected_selector_version=3,
    )
    record(
        not (conflict_first and conflict_second),
        "selector_derived_state_exact",
    )

    scope_mutation = (
        model.mutation if model.mutation == "selector_scope_cache_trusted" else None
    )
    scope_selector = InstalledActuationAuthorityDomainSelector(scope_mutation)
    scope_registration = _domain_registration(
        domain_key=selector_domain_a,
        session_id="semantic-scope-session",
        generation_id="semantic-scope-generation",
        footprint=_effect_footprint("semantic-scope"),
        prior_selector_version=0,
    )
    if not scope_selector.register(scope_registration):
        raise ProbeError("semantic selector fixture could not register scope")
    scope_selector.jurisdiction_key = "UNKNOWN"
    scope_reserved = scope_selector.reserve(
        requested_domain_key=selector_domain_a,
        creation_receipt=scope_registration.creation_receipt,
        expected_selector_version=1,
    )
    record(
        not scope_reserved,
        "selector_scope_revalidated",
    )

    drain_mutation = (
        model.mutation if model.mutation == "forged_drain_state_authorized" else None
    )
    forged_drain = DrainMachine(drain_mutation)
    forged_drain.phase = "RETIRED_DRAIN_ONLY"
    forged_capacity_identifier = "-".join(("forged", "capacity", "token"))
    forged_grant = DrainGrant(
        grant_id="drain-grant-0",
        mode=Mode.ESTOP,
        slot=1,
        capacity_operation_id="forged-capacity-operation",
        capacity_token_id=forged_capacity_identifier,
        issuer_sequence=0,
    )
    forged_drain.grants = [forged_grant]
    forged_drain._issued_grants = {forged_grant.grant_id: forged_grant}
    forged_drain._grant_counter = 1
    forged_drain_result = forged_drain.consume(
        forged_grant,
        command_id="forged-drain-command",
        content_digest="forged-drain-content",
        mode=Mode.ESTOP,
    )
    record(
        forged_drain_result != "REMOTE_ESTOP_ACCEPTED"
        and forged_drain.escalation_tokens_used == 0
        and forged_drain.applied_operation is None,
        "drain_retained_state_closed",
    )
    phase_only_drain = DrainMachine(drain_mutation)
    phase_only_drain.phase = "RETIRED_DRAIN_ONLY"
    record(
        not phase_only_drain._state_is_exact(),
        "drain_retained_state_closed",
    )
    boundary_only_drain = DrainMachine(drain_mutation)
    boundary_only_capacity_cut = boundary_only_drain.boundary.run(
        RestrictivePath.CAPACITY_RETIREMENT_RESTRICTIVE
    )
    boundary_only_drain.phase = "RETIRED_DRAIN_ONLY"
    boundary_only_drain.capacity_cut_operation = boundary_only_capacity_cut
    boundary_only_grant = DrainGrant(
        grant_id="drain-grant-0",
        mode=Mode.ESTOP,
        slot=1,
        capacity_operation_id=boundary_only_capacity_cut.operation_id,
        capacity_token_id=boundary_only_capacity_cut.token.token_id,
        issuer_sequence=0,
    )
    boundary_only_drain.grants = [boundary_only_grant]
    boundary_only_drain._issued_grants = {
        boundary_only_grant.grant_id: boundary_only_grant
    }
    boundary_only_drain._grant_counter = 1
    boundary_only_result = boundary_only_drain.consume(
        boundary_only_grant,
        command_id="boundary-only-drain-command",
        content_digest="boundary-only-drain-content",
        mode=Mode.ESTOP,
    )
    record(
        boundary_only_result != "REMOTE_ESTOP_ACCEPTED"
        and boundary_only_drain.escalation_tokens_used == 0,
        "drain_retained_state_closed",
    )
    forged_applied_drain = DrainMachine(drain_mutation)
    forged_applied_drain.exhaust_capacity()
    forged_applied_operation = forged_applied_drain.boundary.run(
        RestrictivePath.DRAIN_ESTOP
    )
    forged_applied_drain.escalation_tokens_used = 1
    forged_applied_drain.applied_identity = (
        "forged-applied-command",
        "forged-applied-content",
    )
    forged_applied_drain.applied_operation = forged_applied_operation
    forged_applied_drain.remote_edge_closed = True
    record(
        not forged_applied_drain._state_is_exact(),
        "drain_retained_state_closed",
    )
    missing_cut_drain = DrainMachine(drain_mutation)
    missing_cut_drain.exhaust_capacity()
    missing_cut_grant = missing_cut_drain.request_grant(Mode.ESTOP)
    missing_cut_drain.capacity_cut_operation = None
    record(
        not missing_cut_drain._state_is_exact()
        and missing_cut_drain.consume(
            missing_cut_grant,
            command_id="missing-cut-command",
            content_digest="missing-cut-content",
            mode=Mode.ESTOP,
        )
        != "REMOTE_ESTOP_ACCEPTED",
        "drain_retained_state_closed",
    )

    identifier_mutation = (
        model.mutation if model.mutation == "unbounded_identifier_authorized" else None
    )
    identifier_model = Model(identifier_mutation)
    for identifier in (
        "",
        "   ",
        "UNKNOWN",
        "x" * (MAX_SYNTHETIC_IDENTIFIER_BYTES + 1),
        "clock\ncontrol",
        "clock-\N{LATIN SMALL LETTER E WITH ACUTE}",
    ):
        identifier_grant = BodyGrant(
            body_issued=True,
            body_clock=identifier,
            issue_tick=10,
            max_not_after=20,
            publisher="identifier-publisher",
            stream_epoch="identifier-stream",
            slots=(1,),
            modes=frozenset({Mode.ACTIVE}),
        )
        identifier_command = CommandCandidate(
            mode=Mode.ACTIVE,
            publisher=identifier_grant.publisher,
            stream_epoch=identifier_grant.stream_epoch,
            sequence=1,
            ttl_ticks=8,
            sender_tick=11,
            receive_tick=11,
            start_tick=11,
            acceptance_tick=12,
            body_clock=identifier,
        )
        record(
            not identifier_model.body_accepts(
                identifier_grant,
                identifier_command,
            )
            and not _body_oracle(identifier_grant, identifier_command),
            "authority_identifiers_bounded",
        )

    audit.witness(
        "all_retained_authority_state_is_semantically_closed_and_provenanced",
        all_rejected,
    )


def _run_model(mutation: str | None) -> Audit:
    model = Model(mutation)
    audit = Audit()
    campaigns = (
        ("body_freshness", _campaign_body_freshness),
        ("transport_acceptance", _campaign_transport),
        ("effect_journal", _campaign_effect_journal),
        ("unified_physical_boundary", _campaign_unified_physical_boundary),
        ("retirement_closure", _campaign_retirement_closure),
        ("actuation_domain_binding", _campaign_actuation_domain_binding),
        (
            "ordinary_participant_admission_dag",
            _campaign_ordinary_participant_admission_dag,
        ),
        ("active_watchdog", _campaign_active_watchdog),
        ("retirement_drain", _campaign_drain),
        ("intent_freshness", _campaign_intent_freshness),
        ("input_closedness", _campaign_input_closedness),
        ("semantic_state_closure", _campaign_semantic_state_closure),
    )
    for name, campaign in campaigns:
        cases_before = audit.cases
        rejections_before = audit.hostile_rejections
        campaign(model, audit)
        audit.campaign_cases[name] = audit.cases - cases_before
        audit.campaign_hostile_rejections[name] = (
            audit.hostile_rejections - rejections_before
        )
    return audit


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ProbeError(message)


def _sha256_json(value: Any) -> str:
    encoded = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_result() -> dict[str, Any]:
    """Run the reference model and every registered single-defect mutant."""

    _require(
        len(MUTATION_NAMES) == len(MUTATIONS),
        "registered mutation names are not unique",
    )
    _require(
        len(MUTATIONS) == EXPECTED_MUTANT_COUNT,
        "registered mutation count changed without review",
    )
    baseline = _run_model(None)
    _require(not baseline.violations, "reference model violates an invariant")
    _require(
        baseline.witnesses == REQUIRED_WITNESSES,
        "reference model witness set changed without review",
    )
    _require(
        baseline.campaign_cases == EXPECTED_CASE_COUNTS,
        "baseline campaign case counts changed without review",
    )
    _require(
        baseline.campaign_hostile_rejections == EXPECTED_HOSTILE_REJECTION_COUNTS,
        "baseline hostile-rejection counts changed without review",
    )

    mutation_results: list[dict[str, Any]] = []
    survivors: list[str] = []
    for mutation in MUTATIONS:
        audit = _run_model(mutation.name)
        killed = mutation.expected_violation in audit.violations
        if not killed:
            survivors.append(mutation.name)
        mutation_results.append(
            {
                "mutation": mutation.name,
                "expected_violation": mutation.expected_violation,
                "killed": killed,
                "observed_violations": sorted(audit.violations),
            }
        )
    _require(not survivors, f"hostile mutants survived: {survivors}")

    semantic_summary = {
        "baseline_cases": baseline.cases,
        "baseline_hostile_rejections": baseline.hostile_rejections,
        "campaign_case_counts": baseline.campaign_cases,
        "campaign_hostile_rejection_counts": (baseline.campaign_hostile_rejections),
        "invariant_witnesses": sorted(baseline.witnesses),
        "mutations": mutation_results,
    }
    semantic_result_sha256 = _sha256_json(semantic_summary)
    _require(
        semantic_result_sha256 == EXPECTED_SEMANTIC_RESULT_SHA256,
        "semantic result changed without review",
    )
    return {
        "schema": "ncp.b01-freshness-acceptance-probe.v2",
        "probe": "freshness_acceptance",
        "status": "synthetic_pre_ratification_non_normative",
        "review_lenses": (
            "body_clock_freshness",
            "acceptance_linearization",
            "durable_idempotency_and_bounds",
            "safety_severity_order",
            "crash_consistency",
            "unified_physical_boundary_commit_dag",
            "profile_specific_capacity_retirement",
            "terminal_hold_and_estop_retirement_closure",
            "single_actuation_authority_domain_per_generation",
            "ordinary_participant_admission_digest_dag",
            "transport_fence_and_retirement",
            "exact_type_and_capability_identity",
            "retained_state_semantic_closure_and_issuer_provenance",
            "derived_registry_index_revalidation",
            "bounded_authority_identifier_language",
        ),
        "counts": {
            "baseline_cases": baseline.cases,
            "hostile_rejections": baseline.hostile_rejections,
            "invariant_witnesses": len(baseline.witnesses),
            "registered_mutants": len(MUTATIONS),
            "killed_mutants": len(MUTATIONS) - len(survivors),
            "surviving_mutants": len(survivors),
        },
        "campaign_case_counts": baseline.campaign_cases,
        "campaign_hostile_rejection_counts": (baseline.campaign_hostile_rejections),
        "surviving_mutants": survivors,
        "semantic_result_sha256": semantic_result_sha256,
        "invariant_witnesses": sorted(baseline.witnesses),
        "mutation_matrix": mutation_results,
        "retirement_closure_model": {
            "hold_states": [state.value for state in HoldBoundaryLifecycle],
            "terminal_hold_states": sorted(
                state.value for state in RetirementClosureMachine.TERMINAL_HOLD_STATES
            ),
            "estop_floors": [state.value for state in EstopLifecycleFloor],
            "closure_branches": [kind.value for kind in RetirementClosureKind],
            "hold_pending_direct_finalization": "FORBIDDEN",
            "exact_arbiter_terminal_hold_result": "PRESERVE_EXACTLY",
            "lost_arbiter_pending_hold_result": "HOLD_OUTCOME_UNKNOWN",
            "estop_retirement_authorization": ("OPERATOR_RESET_AND_RETIRE_GENERATION"),
            "unknown_union_values": "REJECT",
            "finalization_revalidates_closure_evidence": True,
            "closure_evidence_identity": (
                "SAME_MACHINE_ISSUED_OBJECT_IN_MAP_AND_ISSUANCE_LEDGER"
            ),
            "physical_isolation_proof_identity": ("SAME_MACHINE_RETAINED_CAPABILITY"),
        },
        "actuation_authority_domain_model": {
            "domain_key_type": "ActuationAuthorityDomainKey",
            "domain_keys_per_plant_generation": 1,
            "arbiter_mirror_cardinality": "SCALAR_EXACTLY_ONE",
            "mirror_set_permitted": False,
            "qualified_atomic_multi_actuator_domain_permitted": True,
            "max_actuators_per_domain": MAX_ACTUATORS_PER_DOMAIN,
            "cross_domain_atomic_success_permitted": False,
            "independent_domain_session_rule": "DISTINCT_SESSIONS",
            "unknown_or_default_domain_key": "REJECT",
            "digest_policy": "LOWERCASE_SHA256_NONZERO",
            "authority_identifier_policy": (
                "BOUNDED_EXPLICIT_PRINTABLE_ASCII_NON_DEFAULT"
            ),
            "authority_identifier_max_bytes": MAX_AUTHORITY_IDENTIFIER_BYTES,
            "installed_selector": "InstalledActuationAuthorityDomainSelector",
            "global_registry_capacity": (
                InstalledActuationAuthorityDomainSelector.MAX_DOMAINS
            ),
            "registry_selector_cardinality": ("ONE_PER_JURISDICTION_INCARNATION"),
            "enrolled_conflict_channels": list(ActuationEffectFootprint.CHANNELS),
            "reservation_concurrency": "SINGLE_SELECTOR_CAS",
            "creation_receipt_binds_domain_key": True,
            "creation_receipt_version": "EXACT_NONNEGATIVE_INTEGER",
            "caller_selected_reservation_substitution": "REJECT",
            "disjoint_domains": "SERIALIZE_THEN_RESERVE_FOR_DISTINCT_SESSIONS",
            "selector_scope_type": "PhysicalActuationJurisdictionKey",
            "physical_actuation_jurisdiction_key": (
                PHYSICAL_ACTUATION_JURISDICTION_KEY
            ),
            "physical_actuation_jurisdiction_incarnation": (
                PHYSICAL_ACTUATION_JURISDICTION_INCARNATION
            ),
            "body_principal_scope": "ALL_ENROLLED_BODIES_IN_JURISDICTION",
            "live_selectors_per_jurisdiction_incarnation": 1,
            "live_jurisdiction_incarnations_per_key": 1,
            "topology_change_requirements": [
                "COMPLETE_DOMAIN_FENCE",
                "QUALIFIED_PHYSICAL_ISOLATION",
                "FULL_DOMAIN_REENROLLMENT",
            ],
        },
        "input_closedness_model": {
            "dataclass_policy": "EXACT_CLASS_NO_SUBCLASSES",
            "enum_policy": "EXACT_ENUM_CLASS_NO_RAW_SCALAR_ALIASES",
            "boolean_policy": "EXACT_BOOL_NOT_INTEGER",
            "integer_policy": "EXACT_INT_NOT_BOOL_OR_SUBCLASS",
            "string_policy": "EXACT_STRING_NOT_SUBCLASS",
            "container_policy": "EXACT_DECLARED_CONTAINER_AND_MEMBER_TYPES",
            "invalid_input_authority": "NONE_FAIL_CLOSED",
            "identifier_policy": ("BOUNDED_EXPLICIT_PRINTABLE_ASCII_NON_DEFAULT"),
            "identifier_max_bytes": MAX_SYNTHETIC_IDENTIFIER_BYTES,
            "retained_state_policy": (
                "EXACT_CLOSED_UNION_DERIVED_INDEXES_AND_ISSUER_PROVENANCE"
            ),
            "retained_capability_identity": {
                "effect_boundary_token": (
                    "ISSUED_SLOT_COMMAND_AND_TRANSITION_PROVENANCE"
                ),
                "restrictive_operation": "SAME_RETAINED_OBJECT",
                "retirement_closure_evidence": ("SAME_MACHINE_ISSUED_OBJECT"),
                "physical_isolation_proof": ("SAME_MACHINE_RETAINED_OBJECT"),
                "active_durable_state": (
                    "SAME_RETAINED_OBJECT_AND_INSTALL_FINGERPRINT"
                ),
                "actuation_domain_creation_receipt": "SAME_RETAINED_OBJECT",
                "retirement_drain_grant": "SAME_RETAINED_OBJECT",
                "retirement_drain_capacity_cut": ("SAME_MACHINE_RETAINED_OPERATION"),
                "retirement_drain_applied_operation": (
                    "SAME_MACHINE_RETAINED_OPERATION"
                ),
            },
        },
        "retained_state_closure_model": {
            "effect_journal": (
                "REPLAY_ISSUER_LINKED_RESERVATION_AND_COMPLETION_TRANSITIONS"
            ),
            "unified_physical_boundary": (
                "EXACT_COMMIT_PREFIX_DERIVED_COUNTERS_AND_ONE_USE_TOKEN"
            ),
            "retirement_closure": (
                "CLOSED_EVIDENCE_UNION_AND_DUAL_ISSUANCE_INDEX_IDENTITY"
            ),
            "active_boundary": ("CLOSED_STATE_UNION_AND_BOUNDARY_INSTALL_FINGERPRINT"),
            "actuation_domain_selector": (
                "RECOMPUTED_GENERATION_OWNER_AND_GLOBAL_CONFLICT_GRAPH"
            ),
            "retirement_drain": (
                "MACHINE_ISSUED_CAPACITY_CUT_GRANT_AND_APPLIED_OPERATION"
            ),
            "authority_identifiers": ("MAX_256_BYTES_PRINTABLE_ASCII_NON_DEFAULT"),
            "invalid_or_inconsistent_state_authority": "NONE_FAIL_CLOSED",
        },
        "ordinary_participant_admission_dag": (
            _ordinary_participant_admission_dag_evidence()
        ),
        "claim_boundary": {
            "bounded_executable_counterexamples_only": True,
            "abstract_state_and_receipt_invariants_only": True,
            "capacity_action_is_fixture_profile_specific": True,
            "universal_safe_action_established": False,
            "restrictive_terminal_enum_selected": False,
            "normative_contract_changed": False,
            "adr_accepted": False,
            "implementation_or_refinement_proved": False,
            "interoperability_or_transport_qualified": False,
            "physical_safety_established": False,
            "production_deadline_evidence": False,
            "independent_review_satisfied": False,
            "external_gate_satisfied": False,
            "release_authorized": False,
            "strongest_local_statement": (
                "No counterexample was found in this bounded synthetic model; "
                "every registered single-defect mutant was detected and every "
                "registered non-vacuity witness was reached."
            ),
        },
    }


def validate_result(value: Any) -> None:
    """Reject stale, omitted, or altered result material."""

    expected = build_result()
    _require(
        type(value) is dict
        and json.dumps(value, separators=(",", ":"), sort_keys=True)
        == json.dumps(expected, separators=(",", ":"), sort_keys=True),
        "freshness/acceptance result differs from deterministic semantic replay",
    )


def _self_test() -> None:
    result = build_result()
    validate_result(json.loads(json.dumps(result)))

    altered = copy.deepcopy(result)
    altered["counts"]["surviving_mutants"] = 1
    try:
        validate_result(altered)
    except ProbeError:
        pass
    else:
        raise ProbeError("seeded stale-result mutation was not rejected")

    omitted = copy.deepcopy(result)
    omitted["mutation_matrix"] = omitted["mutation_matrix"][:-1]
    try:
        validate_result(omitted)
    except ProbeError:
        pass
    else:
        raise ProbeError("seeded omitted-mutant result was not rejected")

    class ResultSubclass(dict):
        pass

    try:
        validate_result(ResultSubclass(result))
    except ProbeError:
        pass
    else:
        raise ProbeError("seeded result-container subclass was not rejected")

    class MutationSelectorSubclass(str):
        pass

    try:
        Model(MutationSelectorSubclass(MUTATIONS[0].name))
    except ProbeError:
        pass
    else:
        raise ProbeError("seeded mutation-selector subclass was not rejected")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    arguments = parser.parse_args(argv)
    if arguments.self_test:
        _self_test()
        print("freshness acceptance self-test: PASS")
        return 0
    json.dump(build_result(), sys.stdout, sort_keys=True, separators=(",", ":"))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
