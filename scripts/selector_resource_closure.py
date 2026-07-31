#!/usr/bin/env python3
"""Derive the fail-closed B01 resource ownership and use projection."""

from __future__ import annotations

import re
from collections import Counter
from hashlib import sha256
from typing import Any, NoReturn

from selector_closure_codec import canonical_bytes

RESOURCE_CLOSURE_SCHEMA = "ncp.b01-resource-closure.v2"
RESOURCE_CLOSURE_DOMAIN = b"ncp.b01.resource-closure.v2\x00"
RESOURCE_CLOSURE_CANONICALIZATION = (
    "UTF8_JSON_ROWS_SORTED_BY_CANONICAL_BYTE_ORDER_NO_INSIGNIFICANT_WHITESPACE"
)
RESOURCE_CLOSURE_FRAMING = (
    "DOMAIN_BYTES_THEN_UINT64_BE_PAYLOAD_BYTE_LENGTH_THEN_PAYLOAD_BYTES"
)
RESOURCE_CLOSURE_CLAIM_BOUNDARY = (
    "DERIVED_LOCAL_RESOURCE_DEFINITION_USE_AND_JOINT_PARTICIPANT_CLOSURE_ONLY_"
    "NOT_REVIEW_RELEASE_EXTERNAL_OR_INDEPENDENT_EVIDENCE"
)
RESOURCE_CLOSURE_KINDS = (
    "DEFINE",
    "EFFECT",
    "JTX_WRITE_PARTICIPANT",
    "MUTATION_DERIVED",
    "PROFILE_BINDING",
)
RESOURCE_CLASSES = frozenset(
    {
        "DECLARED_LOGICAL_RESOURCE",
        "PRIMARY_ROOT",
        "SELECTOR_CURRENTNESS",
        "STATE_DOMAIN_VIEW",
        "SUBORDINATE_HEAD",
    }
)
RESOURCE_ACTIONS = frozenset({"CONDITIONAL_COMPARE", "RESERVE", "WRITE"})
MUTATING_RESOURCE_ACTIONS = frozenset({"RESERVE", "WRITE"})
SEMANTIC_ID = re.compile(r"^[A-Z][A-Z0-9_]*$")
RESOURCE_ID = re.compile(r"^[A-Z][A-Z0-9_]*(?:\.[A-Z][A-Z0-9_]*)+$")
PROFILE_ID = re.compile(r"^[A-Z][A-Z0-9_]*$")
ALLOCATION_REF = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*::[A-Za-z0-9_]+$")

SUBORDINATE_HEAD_BACKINGS = {
    "ACTUATION_AUTHORITY_DOMAIN.BODY_ACTUATION_ARBITER_STATE_HEAD": (
        "body-actuation-arbiter-state-head-identity::BodyActuationArbiterStateHead"
    ),
    "GALADRIEL_LIFECYCLE.GALADRIEL_ASSESSMENT_HANDOFF_STATE_HEAD": (
        "galadriel-assessment-handoff-state-head-identity::"
        "GaladrielAssessmentHandoffStateHead"
    ),
    "OBSERVER_ATTACHMENT_TARGET_HISTORY.OBSERVER_GRANT_CLOSURE_AGGREGATION_HEAD": (
        "observer-grant-closure-aggregation-head-identity::"
        "ObserverGrantClosureAggregationHead"
    ),
}
SECURITY_SELECTOR_ARTIFACT = (
    "installed-security-authority-state-selector-identity::"
    "InstalledSecurityAuthorityStateSelector"
)
BODY_SESSION_CONTROL_HEAD_ARTIFACT = (
    "body-session-control-state-head-identity::BodySessionControlStateHead"
)


class ResourceClosureError(ValueError):
    """The resource closure is malformed or not closed."""


def _fail(message: str) -> NoReturn:
    raise ResourceClosureError(message)


def _require(condition: bool, message: str) -> None:
    if not condition:
        _fail(message)


def _exact_dict(value: Any, keys: set[str], *, label: str) -> dict[str, Any]:
    _require(isinstance(value, dict), f"{label}: expected an object")
    _require(set(value) == keys, f"{label}: expected exact keys {sorted(keys)}")
    return value


def _printable_ascii(value: Any, *, label: str, allow_empty: bool = False) -> str:
    _require(isinstance(value, str), f"{label}: expected a string")
    _require(allow_empty or bool(value), f"{label}: empty string is not permitted")
    _require(
        all(0x20 <= ord(character) <= 0x7E for character in value),
        f"{label}: expected printable ASCII",
    )
    return value


def _upper_snake_type_name(type_name: str) -> str:
    _require(
        re.fullmatch(r"[A-Z][A-Za-z0-9]*", type_name) is not None,
        f"root type has an invalid exact name: {type_name!r}",
    )
    return re.sub(r"(?<!^)(?=[A-Z])", "_", type_name).upper()


def _artifact_exact_name(reference: str, *, label: str) -> str:
    _require(
        isinstance(reference, str) and ALLOCATION_REF.fullmatch(reference) is not None,
        f"{label}: invalid artifact reference",
    )
    return reference.split("::", 1)[1]


def _canonical_sorted_rows(rows: list[list[str]]) -> tuple[list[list[str]], bytes]:
    for row_index, row in enumerate(rows):
        _require(
            isinstance(row, list) and all(isinstance(value, str) for value in row),
            f"resource closure row {row_index} is not a string array",
        )
        for value_index, value in enumerate(row):
            _printable_ascii(
                value,
                label=f"resource closure row {row_index}[{value_index}]",
                allow_empty=True,
            )
    encoded_rows = [(canonical_bytes(row), row) for row in rows]
    encoded_rows.sort(key=lambda item: item[0])
    sorted_rows = [row for _, row in encoded_rows]
    _require(
        len({encoded for encoded, _ in encoded_rows}) == len(encoded_rows),
        "resource closure contains a duplicate row",
    )
    return sorted_rows, canonical_bytes(sorted_rows)


def derive_resource_closure(
    data: dict[str, Any],
) -> tuple[list[list[str]], dict[str, Any]]:
    """Return exact resource rows and their domain-separated commitment."""

    selectors = data.get("selectors")
    artifacts_value = data.get("artifacts")
    profiles = data.get("joint_selector_transaction_profiles", {})
    event_catalog = data.get("closed_event_profile_catalog", {})
    ownership_profile = data.get("selector_ownership_profile", {})
    _require(isinstance(selectors, list) and selectors, "selectors must be nonempty")
    _require(isinstance(artifacts_value, list), "artifacts must be an array")
    _require(isinstance(profiles, dict), "joint transaction profiles must be an object")
    _require(isinstance(event_catalog, dict), "event profile catalog must be an object")
    _require(isinstance(ownership_profile, dict), "ownership profile must be an object")
    artifacts = set(artifacts_value)
    _require(
        len(artifacts) == len(artifacts_value),
        "artifact registry contains duplicate references",
    )

    rows: list[list[str]] = []
    registry: dict[str, tuple[str, str, str]] = {}
    event_index: dict[tuple[str, str], dict[str, Any]] = {}
    selector_ids: list[str] = []
    backing_owners: dict[str, str] = {}
    expected_state_domain_count = 0

    for selector_index, selector_value in enumerate(selectors):
        label = f"selectors[{selector_index}]"
        _require(isinstance(selector_value, dict), f"{label}: expected an object")
        selector = selector_value
        selector_id = _printable_ascii(
            selector.get("selector_id"),
            label=f"{label}.selector_id",
        )
        _require(
            SEMANTIC_ID.fullmatch(selector_id) is not None,
            f"{label}: invalid selector ID",
        )
        _require(selector_id not in selector_ids, f"{label}: duplicate selector ID")
        selector_ids.append(selector_id)
        selector_artifact = selector.get("selector")
        root_artifact = selector.get("root")
        _require(
            selector_artifact in artifacts, f"{label}: unregistered selector artifact"
        )
        _require(root_artifact in artifacts, f"{label}: unregistered root artifact")
        expected_selector_resource = f"{selector_id}.SELECTOR"
        expected_root_resource = (
            f"{selector_id}."
            f"{_upper_snake_type_name(_artifact_exact_name(root_artifact, label=label))}"
        )
        state_domains = selector.get("state_domains")
        resources = selector.get("owned_resources")
        events = selector.get("events")
        _require(
            isinstance(state_domains, list), f"{label}.state_domains: expected array"
        )
        _require(
            isinstance(resources, list), f"{label}.owned_resources: expected array"
        )
        _require(isinstance(events, list), f"{label}.events: expected array")
        expected_state_resources = {
            f"{selector_id}.STATE_DOMAIN.{domain['state_domain']}"
            for domain in state_domains
        }
        expected_state_domain_count += len(expected_state_resources)
        declared_resources: list[str] = []
        for resource_index, declaration_value in enumerate(resources):
            resource_label = f"{label}.owned_resources[{resource_index}]"
            declaration = _exact_dict(
                declaration_value,
                {"owner_selector_id", "resource"},
                label=resource_label,
            )
            owner = declaration["owner_selector_id"]
            resource = declaration["resource"]
            _require(owner == selector_id, f"{resource_label}: owner mismatch")
            _require(
                isinstance(resource, str)
                and RESOURCE_ID.fullmatch(resource) is not None
                and resource.startswith(f"{selector_id}."),
                f"{resource_label}: invalid resource identity",
            )
            _require(
                not any(
                    component.startswith("EMPTY_") for component in resource.split(".")
                ),
                f"{resource_label}: EMPTY phase/value aliases are not resources",
            )
            _require(resource not in registry, f"{resource_label}: duplicate resource")
            if resource == expected_selector_resource:
                resource_class = "SELECTOR_CURRENTNESS"
                backing = selector_artifact
            elif resource == expected_root_resource:
                resource_class = "PRIMARY_ROOT"
                backing = root_artifact
            elif resource in expected_state_resources:
                resource_class = "STATE_DOMAIN_VIEW"
                backing = resource.removeprefix(f"{selector_id}.STATE_DOMAIN.")
                backing = f"{selector_id}.{backing}"
            elif resource in SUBORDINATE_HEAD_BACKINGS:
                resource_class = "SUBORDINATE_HEAD"
                backing = SUBORDINATE_HEAD_BACKINGS[resource]
                _require(
                    backing in artifacts,
                    f"{resource_label}: unregistered subordinate-head artifact",
                )
            else:
                resource_class = "DECLARED_LOGICAL_RESOURCE"
                backing = ""
            _require(
                resource_class in RESOURCE_CLASSES,
                f"{resource_label}: unknown resource class",
            )
            if backing:
                _require(
                    backing not in backing_owners,
                    (
                        f"{resource_label}: backing {backing!r} is already bound to "
                        f"{backing_owners.get(backing)}"
                    ),
                )
                backing_owners[backing] = resource
            registry[resource] = (selector_id, resource_class, backing)
            declared_resources.append(resource)
            rows.append(["DEFINE", resource, selector_id, resource_class, backing])
        _require(
            declared_resources == sorted(declared_resources),
            f"{label}: owned resource registry is not canonical",
        )
        _require(
            expected_selector_resource in registry,
            f"{label}: missing selector-currentness resource",
        )
        _require(expected_root_resource in registry, f"{label}: missing primary root")
        _require(
            {
                resource
                for resource in declared_resources
                if resource.startswith(f"{selector_id}.STATE_DOMAIN.")
            }
            == expected_state_resources,
            f"{label}: state-domain resource bijection failed",
        )
        for event_position, event_value in enumerate(events):
            event_label = f"{label}.events[{event_position}]"
            _require(isinstance(event_value, dict), f"{event_label}: expected object")
            event_id = event_value.get("event_id")
            _require(
                isinstance(event_id, str)
                and SEMANTIC_ID.fullmatch(event_id) is not None,
                f"{event_label}: invalid event ID",
            )
            key = (selector_id, event_id)
            _require(key not in event_index, f"{event_label}: duplicate event")
            event_index[key] = event_value

    _require(
        sum(
            resource_class == "SELECTOR_CURRENTNESS"
            for _, resource_class, _ in registry.values()
        )
        == len(selector_ids),
        "resource closure selector-currentness count changed",
    )
    _require(
        sum(
            resource_class == "PRIMARY_ROOT"
            for _, resource_class, _ in registry.values()
        )
        == len(selector_ids),
        "resource closure primary-root count changed",
    )
    _require(
        sum(
            resource_class == "STATE_DOMAIN_VIEW"
            for _, resource_class, _ in registry.values()
        )
        == expected_state_domain_count,
        "resource closure state-domain count changed",
    )
    expected_subordinate_heads = {
        resource
        for resource in SUBORDINATE_HEAD_BACKINGS
        if resource.split(".", 1)[0] in selector_ids
    }
    _require(
        {
            resource
            for resource, (_, resource_class, _) in registry.items()
            if resource_class == "SUBORDINATE_HEAD"
        }
        == expected_subordinate_heads,
        "resource closure subordinate-head set is not complete and exact",
    )
    folded_resources: dict[str, str] = {}
    for resource in registry:
        folded = resource.casefold()
        _require(
            folded not in folded_resources,
            f"resource case-fold collision: {resource} and {folded_resources.get(folded)}",
        )
        folded_resources[folded] = resource

    for selector_id, event_id in sorted(event_index):
        event = event_index[(selector_id, event_id)]
        effects = event.get("common_case_effects")
        mutations = event.get("common_case_mutates")
        _require(isinstance(effects, list), f"{selector_id}.{event_id}: effects array")
        _require(
            isinstance(mutations, list), f"{selector_id}.{event_id}: mutates array"
        )
        effect_rows: list[list[str]] = []
        mutating_resources: set[str] = set()
        for effect_index, effect_value in enumerate(effects):
            effect_label = (
                f"{selector_id}.{event_id}.common_case_effects[{effect_index}]"
            )
            effect = _exact_dict(
                effect_value,
                {"action", "cardinality", "resource"},
                label=effect_label,
            )
            action = effect["action"]
            cardinality = effect["cardinality"]
            resource = effect["resource"]
            _require(action in RESOURCE_ACTIONS, f"{effect_label}: unknown action")
            _require(
                isinstance(cardinality, str)
                and SEMANTIC_ID.fullmatch(cardinality) is not None,
                f"{effect_label}: invalid cardinality",
            )
            _require(resource in registry, f"{effect_label}: unresolved resource")
            owner = registry[resource][0]
            if action in MUTATING_RESOURCE_ACTIONS:
                _require(
                    owner == selector_id,
                    f"{effect_label}: cross-owner mutation is forbidden",
                )
                mutating_resources.add(resource)
            row = [
                "EFFECT",
                selector_id,
                event_id,
                action,
                cardinality,
                resource,
                owner,
            ]
            effect_rows.append(row)
            rows.append(row)
        _require(
            len({canonical_bytes(row) for row in effect_rows}) == len(effect_rows),
            f"{selector_id}.{event_id}: duplicate effect",
        )
        _require(
            isinstance(mutations, list)
            and all(isinstance(resource, str) for resource in mutations),
            f"{selector_id}.{event_id}: invalid mutation list",
        )
        _require(
            len(set(mutations)) == len(mutations),
            f"{selector_id}.{event_id}: duplicate mutation",
        )
        _require(
            set(mutations) == mutating_resources,
            f"{selector_id}.{event_id}: effects and mutations are not bijective",
        )
        for resource in sorted(mutating_resources):
            owner = registry[resource][0]
            rows.append(["MUTATION_DERIVED", selector_id, event_id, resource, owner])

    security_serialization = event_catalog.get("security_serialization")
    if security_serialization is None:
        security_serialization = []
    _require(
        isinstance(security_serialization, list),
        "security-serialization profile inventory must be an array",
    )
    for index, profile_value in enumerate(security_serialization):
        label = f"security_serialization[{index}]"
        _require(isinstance(profile_value, dict), f"{label}: expected object")
        _require(
            profile_value.get("profile_id")
            == f"SECURITY_SERIALIZATION_PROFILE_{index + 1:03d}",
            f"{label}: profile order or ID changed",
        )
        value = profile_value.get("value")
        _require(isinstance(value, dict), f"{label}.value: expected object")
        target = value.get("compared_selector")
        _require(
            target == SECURITY_SELECTOR_ARTIFACT and target in artifacts,
            f"{label}: compared selector is not the canonical security selector",
        )
        resource = "SECURITY_AUTHORITY.SELECTOR"
        _require(resource in registry, f"{label}: security currentness is undefined")
        rows.append(
            [
                "PROFILE_BINDING",
                (
                    "/closed_event_profile_catalog/security_serialization/"
                    f"{index}/value/compared_selector"
                ),
                "SELECTOR_ARTIFACT_TO_CURRENTNESS_RESOURCE",
                target,
                resource,
                registry[resource][0],
            ]
        )
    if "BODY_SESSION_CONTROL" in selector_ids:
        body_profile = ownership_profile.get("BODY_SESSION_CONTROL")
        _require(isinstance(body_profile, dict), "body ownership profile is missing")
        body_target = body_profile.get("parent_head")
        body_resource = "BODY_SESSION_CONTROL.BODY_SESSION_CONTROL_STATE_HEAD"
        _require(
            body_target == BODY_SESSION_CONTROL_HEAD_ARTIFACT
            and body_target in artifacts
            and body_resource in registry,
            "body parent-head profile does not bind the canonical body root",
        )
        rows.append(
            [
                "PROFILE_BINDING",
                "/selector_ownership_profile/BODY_SESSION_CONTROL/parent_head",
                "HEAD_ARTIFACT_TO_RESOURCE",
                body_target,
                body_resource,
                registry[body_resource][0],
            ]
        )

    referenced_participants: set[tuple[str, str, str]] = set()
    for profile_id in sorted(profiles):
        profile = profiles[profile_id]
        _require(
            isinstance(profile, dict)
            and PROFILE_ID.fullmatch(profile_id) is not None
            and profile.get("profile_id") == profile_id,
            f"joint profile {profile_id!r} has an invalid identity",
        )
        participants = profile.get("participants")
        declared_count = profile.get("declared_writing_participant_count")
        _require(
            isinstance(participants, list)
            and isinstance(declared_count, int)
            and not isinstance(declared_count, bool)
            and len(participants) == declared_count
            and declared_count >= 2,
            f"{profile_id}: invalid participant count",
        )
        profile_selector_ids: set[str] = set()
        for participant_index, participant in enumerate(participants):
            label = f"{profile_id}.participants[{participant_index}]"
            _require(isinstance(participant, dict), f"{label}: expected object")
            selector_id = participant.get("selector_id")
            event_id = participant.get("event_id")
            _require(
                isinstance(selector_id, str)
                and isinstance(event_id, str)
                and (selector_id, event_id) in event_index,
                f"{label}: unknown event participant",
            )
            _require(
                selector_id not in profile_selector_ids,
                f"{profile_id}: selector participates more than once",
            )
            profile_selector_ids.add(selector_id)
            event = event_index[(selector_id, event_id)]
            _require(
                event.get("joint_selector_transaction_profile_ref") == profile_id,
                f"{label}: event profile reference mismatch",
            )
            local_writes = {
                effect["resource"]
                for effect in event["common_case_effects"]
                if effect["action"] in MUTATING_RESOURCE_ACTIONS
            }
            _require(local_writes, f"{label}: participant has no local write footprint")
            _require(
                all(registry[resource][0] == selector_id for resource in local_writes),
                f"{label}: participant repeats a foreign write",
            )
            key = (profile_id, selector_id, event_id)
            _require(
                key not in referenced_participants, f"{label}: duplicate participant"
            )
            referenced_participants.add(key)
            rows.append(["JTX_WRITE_PARTICIPANT", profile_id, selector_id, event_id])
    event_profile_participants = {
        (event["joint_selector_transaction_profile_ref"], selector_id, event_id)
        for (selector_id, event_id), event in event_index.items()
        if "joint_selector_transaction_profile_ref" in event
    }
    _require(
        event_profile_participants == referenced_participants,
        "event/profile participant references are not bijective",
    )

    sorted_rows, payload = _canonical_sorted_rows(rows)
    counts = Counter(row[0] for row in sorted_rows)
    _require(
        set(counts).issubset(RESOURCE_CLOSURE_KINDS),
        "resource closure row-kind inventory changed",
    )
    digest = sha256()
    digest.update(RESOURCE_CLOSURE_DOMAIN)
    digest.update(len(payload).to_bytes(8, "big"))
    digest.update(payload)
    commitment = {
        "algorithm": "SHA256",
        "byte_length": len(payload),
        "canonicalization": RESOURCE_CLOSURE_CANONICALIZATION,
        "claim_boundary": RESOURCE_CLOSURE_CLAIM_BOUNDARY,
        "domain_hex": RESOURCE_CLOSURE_DOMAIN.hex(),
        "framing": RESOURCE_CLOSURE_FRAMING,
        "per_kind_counts": {kind: counts[kind] for kind in RESOURCE_CLOSURE_KINDS},
        "row_count": len(sorted_rows),
        "schema": RESOURCE_CLOSURE_SCHEMA,
        "sha256": digest.hexdigest(),
    }
    return sorted_rows, commitment


def run_self_test() -> int:
    """Exercise byte framing and required subordinate-head closure."""

    rows = [
        ["EFFECT", "B", "E", "WRITE", "ROOT", "B.ROOT", "B"],
        ["DEFINE", "B.ROOT", "B", "PRIMARY_ROOT", "root::Root"],
    ]
    sorted_rows, payload = _canonical_sorted_rows(rows)
    _require(
        sorted_rows == [rows[1], rows[0]],
        "resource closure row byte order changed",
    )
    _require(
        payload == b'[["DEFINE","B.ROOT","B","PRIMARY_ROOT","root::Root"],'
        b'["EFFECT","B","E","WRITE","ROOT","B.ROOT","B"]]',
        "resource closure canonical payload vector changed",
    )
    hostile = rows + [rows[0]]
    try:
        _canonical_sorted_rows(hostile)
    except ResourceClosureError:
        pass
    else:
        _fail("resource closure accepted a duplicate row")

    selector_artifact = (
        "installed-galadriel-lifecycle-selector-identity::"
        "InstalledGaladrielLifecycleSelector"
    )
    root_artifact = (
        "galadriel-lifecycle-state-head-identity::GaladrielLifecycleStateHead"
    )
    subordinate_artifact = SUBORDINATE_HEAD_BACKINGS[
        "GALADRIEL_LIFECYCLE.GALADRIEL_ASSESSMENT_HANDOFF_STATE_HEAD"
    ]

    def subordinate_sample(*, include_subordinate: bool) -> dict[str, Any]:
        resources = [
            {
                "owner_selector_id": "GALADRIEL_LIFECYCLE",
                "resource": ("GALADRIEL_LIFECYCLE.GALADRIEL_LIFECYCLE_STATE_HEAD"),
            },
            {
                "owner_selector_id": "GALADRIEL_LIFECYCLE",
                "resource": "GALADRIEL_LIFECYCLE.SELECTOR",
            },
            {
                "owner_selector_id": "GALADRIEL_LIFECYCLE",
                "resource": "GALADRIEL_LIFECYCLE.STATE_DOMAIN.ROOT",
            },
        ]
        if include_subordinate:
            resources.append(
                {
                    "owner_selector_id": "GALADRIEL_LIFECYCLE",
                    "resource": (
                        "GALADRIEL_LIFECYCLE.GALADRIEL_ASSESSMENT_HANDOFF_STATE_HEAD"
                    ),
                }
            )
        resources.sort(key=lambda item: item["resource"])
        return {
            "artifacts": [
                root_artifact,
                selector_artifact,
                subordinate_artifact,
            ],
            "closed_event_profile_catalog": {},
            "joint_selector_transaction_profiles": {},
            "selector_ownership_profile": {},
            "selectors": [
                {
                    "events": [],
                    "owned_resources": resources,
                    "root": root_artifact,
                    "selector": selector_artifact,
                    "selector_id": "GALADRIEL_LIFECYCLE",
                    "state_domains": [{"state_domain": "ROOT"}],
                }
            ],
        }

    derive_resource_closure(subordinate_sample(include_subordinate=True))
    try:
        derive_resource_closure(subordinate_sample(include_subordinate=False))
    except ResourceClosureError:
        pass
    else:
        _fail("resource closure accepted a missing subordinate head")
    return 5


if __name__ == "__main__":
    cases = run_self_test()
    print(f"selector resource closure self-test: PASS cases={cases}")
