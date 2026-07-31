#!/usr/bin/env python3
"""Generate the non-normative B01 selector-closure review matrix."""

from __future__ import annotations

import argparse
import copy
import sys
from pathlib import Path
from typing import Any, Callable

from check_selector_closure import (
    DEFAULT_SOURCE,
    ClosureCheckError,
    ModelAllocation,
    _model_allocations,
    _verify_adr_snapshots_unchanged,
    load_compact_source,
    validate_expanded_source,
)
from generate_selector_closure_source import (
    SelectorClosureGenerationError,
    _atomic_write,
    _require_distinct_paths,
)
from selector_allocation_inventory import (
    ADR_ALLOCATION_MODULE_PATHS,
    ADR_ALLOCATION_PATHS,
    ALLOCATION_KINDS,
)
from selector_closure_codec import (
    MAX_COMPACT_BYTES,
    MAX_EXPANDED_BYTES,
    AtomicWriteOutcomeUnknownError,
    SelectorClosureCodecError,
    canonical_bytes,
    read_bounded_regular_file,
)
from selector_resource_closure import derive_resource_closure

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "docs" / "adr" / "B01_SELECTOR_CLOSURE_MATRIX.md"
_PROBE_BINDING_METADATA_KEYS = frozenset(
    {"claim_boundary", "execution_profile", "shared_source_bindings"}
)


def _is_exact_review_candidate(data: dict[str, Any]) -> bool:
    """Recognize only the fail-closed tuple admitted for allocation review."""

    oracle = data.get("adr_allocation_oracle")
    provenance_review = (
        oracle.get("provenance_review") if isinstance(oracle, dict) else None
    )
    return (
        isinstance(oracle, dict)
        and oracle.get("status") == "INCOMPLETE_FAIL_CLOSED"
        and isinstance(provenance_review, dict)
        and provenance_review.get("status") == "NOT_REVIEWED"
        and provenance_review.get("reviewed_assignment_sha256") == "0" * 64
    )


def _validate_matrix_source(
    data: dict[str, Any],
    *,
    validator: Callable[..., Any] = validate_expanded_source,
    adr_snapshot_sink: Callable[[dict[Path, bytes]], None] | None = None,
) -> Any:
    """Validate a matrix input without enabling architectural draft exceptions."""

    review_candidate = _is_exact_review_candidate(data)
    kwargs: dict[str, Any] = {
        "require_complete_allocation": True,
        "allow_incomplete_allocation": review_candidate,
    }
    if adr_snapshot_sink is not None:
        kwargs["adr_snapshot_sink"] = adr_snapshot_sink
    return validator(data, **kwargs)


def _require_matrix_output_path_distinct(source: Path, output: Path) -> None:
    """Forbid a generated view from replacing any transitive semantic input."""

    _require_distinct_paths(
        source,
        output,
        labels=("compact source", "matrix output"),
    )
    for relative_path in (
        *ADR_ALLOCATION_PATHS,
        *(path for paths in ADR_ALLOCATION_MODULE_PATHS for path in paths),
    ):
        _require_distinct_paths(
            ROOT / relative_path,
            output,
            labels=(f"semantic ADR input {relative_path}", "matrix output"),
        )


def _checker_review_command(data: dict[str, Any]) -> str:
    """Return the checker mode that matches the maintained allocation tuple."""

    if _is_exact_review_candidate(data):
        return "python3 scripts/check_selector_closure.py --review-candidate"
    return "python3 scripts/check_selector_closure.py --run-probes"


def run_self_test() -> int:
    """Prove candidate rendering relaxes allocation coverage and nothing else."""

    exact_candidate = {
        "adr_allocation_oracle": {
            "provenance_review": {
                "reviewed_assignment_sha256": "0" * 64,
                "status": "NOT_REVIEWED",
            },
            "status": "INCOMPLETE_FAIL_CLOSED",
        }
    }
    calls: list[dict[str, Any]] = []

    def record_strict_mode(_: dict[str, Any], **kwargs: Any) -> object:
        if "allow_known_incomplete" in kwargs:
            raise AssertionError("matrix passed the broad legacy exception switch")
        calls.append(kwargs)
        return object()

    _validate_matrix_source(exact_candidate, validator=record_strict_mode)
    if calls != [
        {
            "allow_incomplete_allocation": True,
            "require_complete_allocation": True,
        }
    ]:
        raise SelectorClosureGenerationError(
            "matrix candidate did not select allocation-only validation"
        )

    hostile_mutations = (
        ("complete status", ("status", "COMPLETE")),
        ("reviewed provenance", ("provenance_status", "REVIEWED")),
        ("nonzero reviewed digest", ("reviewed_digest", "f" * 64)),
        ("unknown status", ("status", "UNKNOWN")),
    )
    for label, (field, value) in hostile_mutations:
        hostile = copy.deepcopy(exact_candidate)
        oracle = hostile["adr_allocation_oracle"]
        if field == "status":
            oracle["status"] = value
        elif field == "provenance_status":
            oracle["provenance_review"]["status"] = value
        else:
            oracle["provenance_review"]["reviewed_assignment_sha256"] = value
        calls.clear()
        _validate_matrix_source(hostile, validator=record_strict_mode)
        if calls != [
            {
                "allow_incomplete_allocation": False,
                "require_complete_allocation": True,
            }
        ]:
            raise SelectorClosureGenerationError(
                f"matrix treated {label} as an allocation-review candidate"
            )

    current_bindings = {
        "claim_boundary": "LOCAL_ONLY",
        "execution_profile": {"schema": "fixture"},
        "shared_source_bindings": {"fixture": {}},
        "fixture_probe": {
            "review_command": "python3 fixture_probe.py",
            "script_sha256": "a" * 64,
            "stdout_sha256": "b" * 64,
        },
    }
    if _bound_probe_rows(current_bindings) != [
        [
            "`fixture_probe`",
            "`python3 fixture_probe.py`",
            f"`{'a' * 64}`",
            f"`{'b' * 64}`",
        ]
    ]:
        raise SelectorClosureGenerationError(
            "matrix did not render the exact current probe-binding shape"
        )
    legacy_bindings = copy.deepcopy(current_bindings)
    legacy_probe = legacy_bindings["fixture_probe"]
    legacy_probe["command"] = legacy_probe.pop("review_command")
    try:
        _bound_probe_rows(legacy_bindings)
    except KeyError:
        pass
    else:
        raise SelectorClosureGenerationError(
            "matrix accepted the removed legacy probe command field"
        )
    if _checker_review_command(exact_candidate) != (
        "python3 scripts/check_selector_closure.py --review-candidate"
    ):
        raise SelectorClosureGenerationError(
            "matrix rendered a strict-completion command for the review candidate"
        )
    completed = copy.deepcopy(exact_candidate)
    completed_oracle = completed["adr_allocation_oracle"]
    completed_oracle["status"] = "COMPLETE"
    completed_oracle["provenance_review"]["status"] = "REVIEWED"
    completed_oracle["provenance_review"]["reviewed_assignment_sha256"] = "f" * 64
    if _checker_review_command(completed) != (
        "python3 scripts/check_selector_closure.py --run-probes"
    ):
        raise SelectorClosureGenerationError(
            "matrix did not restore strict probe checking for a reviewed source"
        )
    try:
        _require_matrix_output_path_distinct(
            Path("distinct-compact-input.json"),
            ROOT / ADR_ALLOCATION_PATHS[0],
        )
    except SelectorClosureGenerationError:
        pass
    else:
        raise SelectorClosureGenerationError(
            "matrix accepted an output that aliases a semantic ADR input"
        )
    return 10


def code(value: Any) -> str:
    return f"`{str(value).replace('`', '&#96;')}`"


def cell(value: Any) -> str:
    return str(value).replace("|", "&#124;").replace("\r", " ").replace("\n", " ")


def identifier(reference: str) -> str:
    return reference.split("::", 1)[-1]


def _bound_probe_rows(bindings: dict[str, Any]) -> list[list[str]]:
    """Render only exact executable probes from the current binding shape."""

    return [
        [
            code(probe_id),
            code(binding["review_command"]),
            code(binding["script_sha256"]),
            code(binding["stdout_sha256"]),
        ]
        for probe_id, binding in sorted(bindings.items())
        if probe_id not in _PROBE_BINDING_METADATA_KEYS
    ]


def table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    result = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    result.extend(
        "| " + " | ".join(cell(value) for value in row) + " |" for row in rows
    )
    return result


def event_edge_summary(
    selector: dict[str, Any],
    event: dict[str, Any],
) -> str:
    edge_by_id = {
        state_edge["edge_id"]: state_edge
        for state_edge in selector["state_edge_catalog"]
    }
    used = {
        edge_ref
        for transition_case in event["transition_cases"]
        for edge_ref in transition_case["state_edge_refs"]
    }
    root_edges = sorted(
        {
            (
                edge_by_id[edge_ref]["from_state"],
                edge_by_id[edge_ref]["to_state"],
            )
            for edge_ref in used
            if edge_by_id[edge_ref]["state_domain"] == "ROOT"
        }
    )
    root = ", ".join(f"{source}→{target}" for source, target in root_edges)
    subordinate = sum(
        edge_by_id[edge_ref]["state_domain"] != "ROOT" for edge_ref in used
    )
    parts = []
    if root:
        parts.append(root)
    if subordinate:
        parts.append(f"{subordinate} subordinate edge variants")
    return "; ".join(parts) if parts else "No state edge"


def render(data: dict[str, Any], expanded_sha256: str) -> str:
    selectors = data["selectors"]
    allocation_oracle = data["adr_allocation_oracle"]
    identity_commitment_suite = allocation_oracle["allocation_review_profile"][
        "allocation_identity_commitment_suite"
    ]
    semantic_shape_commitment_suite = allocation_oracle["allocation_review_profile"][
        "semantic_shape_commitment_suite"
    ]
    model_allocations = _model_allocations(data)
    resource_rows, resource_closure = derive_resource_closure(data)
    resource_effects_by_event: dict[tuple[str, str], list[list[str]]] = {}
    resource_mutations_by_event: dict[tuple[str, str], list[list[str]]] = {}
    for row in resource_rows:
        if row[0] == "EFFECT":
            resource_effects_by_event.setdefault((row[1], row[2]), []).append(row)
        elif row[0] == "MUTATION_DERIVED":
            resource_mutations_by_event.setdefault((row[1], row[2]), []).append(row)
    declared_allocations = {
        ModelAllocation(
            row["kind"],
            row["exact_name"],
            row["semantic_ref"],
        )
        for row in allocation_oracle["allocations"]
    }
    event_total = sum(len(selector["events"]) for selector in selectors)
    domain_total = sum(len(selector["state_domains"]) for selector in selectors)
    case_total = sum(
        len(event["transition_cases"])
        for selector in selectors
        for event in selector["events"]
    )
    sidecar_total = sum(
        len(event["post_cas_sidecars"])
        for selector in selectors
        for event in selector["events"]
    )

    lines = [
        "<!-- Generated by scripts/generate_selector_closure_matrix.py. -->",
        "",
        "# B01 selector closure matrix",
        "",
        "> **Status:** This file describes the unreleased and release-blocked",
        "> `1.0.0-rc.1` candidate. It is non-normative local design evidence.",
        "> It does not release, certify, sign, or qualify NCP or a consumer.",
        "",
        "This view is generated from the compact selector source.",
        "Do not edit this file by hand.",
        "",
        f"- Expanded source SHA-256: `{expanded_sha256}`",
        f"- Selectors: `{len(selectors)}`",
        f"- State domains: `{domain_total}`",
        f"- Events: `{event_total}`",
        f"- Semantic cases: `{case_total}`",
        f"- Post-CAS sidecars: `{sidecar_total}`",
        f"- Registered artifacts: `{len(data['artifacts'])}`",
        (
            "- Resource closure: "
            f"`{resource_closure['row_count']}` rows, "
            f"`{resource_closure['byte_length']}` canonical bytes, SHA-256 "
            f"`{resource_closure['sha256']}`"
        ),
        "",
        "The source uses one fail-closed rule.",
        "An unknown, default, missing, extra, duplicate, or legacy alias rejects.",
        "",
        "## Review boundaries",
        "",
        "The generated matrix supports local architecture review.",
        "It does not replace the normative contract or the pre-release gates.",
        "",
        "The following gates remain **NOT RUN** unless a separate exact receipt",
        "records them:",
        "",
        "- live mTLS, ACL, certificate rotation, and revocation",
        "- two installed and independent non-Rust peers",
        "- fault, soak, duration-fuzz, and sanitizer campaigns",
        "- performance qualification",
        "- signatures, SBOM, and provenance",
        "- clean-room reproduction",
        "- all nine exact consumer and extension role qualifications",
        "",
        "## Allocation provenance gate",
        "",
        "The maintained selector authoring source stores this inventory in a",
        "separate bounded canonical file and binds its exact bytes and schema.",
        "The compact source remains self-contained after generation.",
        "",
        f"- Status: `{allocation_oracle['status']}`",
        f"- Claim boundary: `{allocation_oracle['claim_boundary']}`",
        (
            "- Semantic ADR-and-anchor assignment review: "
            f"`{allocation_oracle['provenance_review']['status']}`"
        ),
        (
            "- Reviewed assignment SHA-256: "
            f"`{allocation_oracle['provenance_review']['reviewed_assignment_sha256']}`"
        ),
        (
            "- Modeled allocation surface: "
            f"`{allocation_oracle['model_allocation_count']}` rows, "
            f"SHA-256 `{allocation_oracle['model_allocation_sha256']}`"
        ),
        (
            "- Model origin/signal projection: "
            f"`{allocation_oracle['allocation_review_profile']['model_origin_signal_row_count']}` "
            "rows, SHA-256 "
            f"`{allocation_oracle['allocation_review_profile']['model_origin_signal_sha256']}`"
        ),
        (f"- Identity commitment suite: `{identity_commitment_suite['schema']}`"),
        (
            "- Unit/model/origin domains: "
            f"`{identity_commitment_suite['unit_id_domain_hex']}` / "
            f"`{identity_commitment_suite['model_projection_domain_hex']}` / "
            f"`{identity_commitment_suite['origin_signal_projection_domain_hex']}`"
        ),
        (
            "- Exact semantic review subject: "
            f"`{allocation_oracle['semantic_review_subject']['byte_length']}` "
            "canonical bytes, SHA-256 "
            f"`{allocation_oracle['semantic_review_subject']['sha256']}`"
        ),
        (
            "- Recursive semantic shape: "
            f"`{allocation_oracle['semantic_shape_entry_count']}` entries, "
            f"SHA-256 `{allocation_oracle['semantic_shape_sha256']}`"
        ),
        (
            "- Semantic-shape commitment suite/domain: "
            f"`{semantic_shape_commitment_suite['schema']}` / "
            f"`{semantic_shape_commitment_suite['domain_hex']}`"
        ),
        f"- Bound ADR documents: `{len(allocation_oracle['documents'])}`",
        f"- Typed exclusions: `{len(allocation_oracle['exclusions'])}`",
        "",
        "These rows assign non-normative B01 semantics to one proposed ADR",
        "jurisdiction. They do not reserve a B03 registry identifier, ratify B01,",
        "or grant release authority.",
        "",
        "The assignment review uses each complete owner-free unit, not a name alone.",
        "Each unit ID is derived from its kind, exact name, and stable semantic",
        "reference. Selector usage and resource backing are evidence signals only.",
        "They cannot change unit identity or select an ADR assignment. The separate",
        "origin/signal commitment exposes evidence drift. The review digest binds",
        "the exact semantic review subject, unit identity, ADR, and stable anchor.",
        "",
    ]
    lines.extend(
        table(
            ["Kind", "Modeled", "Allocated", "Missing"],
            [
                [
                    code(kind),
                    sum(1 for row in model_allocations if row.kind == kind),
                    sum(1 for row in declared_allocations if row.kind == kind),
                    sum(
                        1
                        for row in model_allocations - declared_allocations
                        if row.kind == kind
                    ),
                ]
                for kind in ALLOCATION_KINDS
            ],
        )
    )
    lines.extend(
        [
            "",
            "A missing row keeps the allocation status fail-closed.",
            (
                "`PROFILE` covers each top-level structural profile and each "
                "named plural-catalog profile by exact JSON pointer."
            ),
            "",
            "### Per-ADR provenance commitments",
            "",
        ]
    )
    allocation_kind_counts: dict[str, dict[str, int]] = {
        document["adr_id"]: {kind: 0 for kind in ALLOCATION_KINDS}
        for document in allocation_oracle["documents"]
    }
    for allocation in allocation_oracle["allocations"]:
        allocation_kind_counts[allocation["adr_id"]][allocation["kind"]] += 1
    lines.extend(
        table(
            [
                "ADR",
                *ALLOCATION_KINDS,
                "Allocation rows SHA-256",
                "Exclusions",
                "ADR source-set SHA-256",
            ],
            [
                [
                    code(document["adr_id"]),
                    *[
                        allocation_kind_counts[document["adr_id"]][kind]
                        for kind in ALLOCATION_KINDS
                    ],
                    code(document["allocation_rows_sha256"]),
                    document["exclusion_row_count"],
                    code(document["source_set"]["sha256"]),
                ]
                for document in allocation_oracle["documents"]
            ],
        )
    )
    lines.extend(
        [
            "",
            "## Selector index",
            "",
        ]
    )

    selector_rows: list[list[Any]] = []
    for selector in selectors:
        events = selector["events"]
        selector_rows.append(
            [
                code(selector["selector_id"]),
                code(selector["owner"]),
                code(identifier(selector["selector"])),
                code(identifier(selector["root"])),
                len(selector["state_domains"]),
                len(events),
                sum(len(event["transition_cases"]) for event in events),
                sum(len(event["partition_effects"]) for event in events),
                sum(len(event["post_cas_sidecars"]) for event in events),
            ]
        )
    lines.extend(
        table(
            [
                "Selector",
                "Owner",
                "Installed selector",
                "Root",
                "Domains",
                "Events",
                "Cases",
                "Partitions",
                "Sidecars",
            ],
            selector_rows,
        )
    )

    lines.extend(
        [
            "",
            "## First-principles architecture cuts",
            "",
            "### Logical session generation",
            "",
            "ADR-001 creates only simulation or plant source generations.",
            "Each generation allocates exactly two one-use child markers.",
            "",
        ]
    )
    lineage = data["logical_session_generation_lineage_profile"]
    lines.extend(
        table(
            ["Creation scope", "Exact required child roles"],
            [
                [
                    code(scope),
                    ", ".join(code(role) for role in roles),
                ]
                for scope, roles in lineage["required_child_role_sets"].items()
            ],
        )
    )
    lines.extend(
        [
            "",
            "Observer attach creates no ADR-001 lineage.",
            "It creates no observer logical session ID or observer generation.",
            "",
            "### Plant actuation jurisdiction",
            "",
        ]
    )
    actuation = data["actuation_authority_domain_registry_profile"]
    lines.extend(
        table(
            ["Property", "Closed value"],
            [
                [
                    "Stable selector key",
                    ", ".join(
                        code(value)
                        for value in actuation["stable_selector_key"]["fields"]
                    ),
                ],
                [
                    "Registry incarnation",
                    code(actuation["registry_incarnation"]["location"]),
                ],
                [
                    "Domain cardinality",
                    code(actuation["generation_binding"]["domain_cardinality"]),
                ],
                [
                    "Reservation",
                    code(actuation["genesis_handshake"]["reservation"]),
                ],
                [
                    "Domain confirmation",
                    code(actuation["genesis_handshake"]["domain_confirmation"]),
                ],
                [
                    "Body reconciliation",
                    code(actuation["genesis_handshake"]["body_reconciliation"]),
                ],
                [
                    "Parent live gate",
                    code(actuation["genesis_handshake"]["parent_live_gate"]),
                ],
            ],
        )
    )
    lines.extend(
        [
            "",
            "Closed owner states:",
            "",
        ]
    )
    lines.extend(f"- {code(state)}" for state in actuation["owner_states"])

    lines.extend(
        [
            "",
            "### Observer target serialization",
            "",
            "The target key excludes a source generation and requested scope.",
            "All overlapping requests for one logical target share one lock.",
            "",
        ]
    )
    observer = data["observer_grant_request_target_profile"]
    lines.extend(
        table(
            ["Axis", "Exact value"],
            [
                [
                    "Target key",
                    ", ".join(
                        code(value) for value in observer["target_key"]["fields"]
                    ),
                ],
                [
                    "Target phases",
                    " → ".join(
                        code(value)
                        for value in observer["global_history_selector"]["entry_phases"]
                    ),
                ],
                [
                    "Requested-set default",
                    code(observer["requested_set_decision"]["default"]),
                ],
                [
                    "Parent finalization",
                    code(observer["lineage_checkpoint"]["parent_finalization"]),
                ],
                [
                    "Checkpoint publication",
                    code(observer["lineage_checkpoint"]["publication"]),
                ],
            ],
        )
    )

    lines.extend(
        [
            "",
            "Parent finalization requires the local server-authority cut.",
            "It also requires the complete durable pending-target root.",
            "Remote closure and transport quiescence occur after parent finalization.",
            "",
            "### Simulation authority",
            "",
        ]
    )
    simulation = data["simulation_session_state_profile"]
    calibrated_marker = str(simulation["provenance"]["calibrated_posterior"]).lower()
    simulation_output_marker = str(
        simulation["provenance"]["is_simulation_output"]
    ).lower()
    lines.extend(
        table(
            ["Property", "Exact value"],
            [
                [
                    "States",
                    " → ".join(code(value) for value in simulation["states"]),
                ],
                [
                    "Pending authority",
                    code(simulation["pending_parent_authority"]),
                ],
                [
                    "Active authority",
                    code(simulation["active_authority"]),
                ],
                [
                    "Simulation marker",
                    (
                        f"`calibrated_posterior={calibrated_marker}`, "
                        f"`is_simulation_output={simulation_output_marker}`"
                    ),
                ],
            ],
        )
    )

    lines.extend(
        [
            "",
            "## Joint selector transactions",
            "",
            "Each listed transaction uses one local durable transaction.",
            "The transaction writes all declared installed selectors or writes none.",
            "Exactly one participant emits the joint commit receipt.",
            "",
        ]
    )
    joint_rows = []
    for profile_id, profile in sorted(
        data["joint_selector_transaction_profiles"].items()
    ):
        participants = " + ".join(
            f"{code(item['selector_id'])}.{code(item['event_id'])}"
            for item in profile["participants"]
        )
        case_scope = "<br>".join(
            (
                f"{code(item['selector_id'])}.{code(item['event_id'])}: "
                + ", ".join(code(case_id) for case_id in item["semantic_case_ids"])
            )
            for item in profile["participants"]
        )
        joint_rows.append(
            [
                code(profile_id),
                code(str(profile["declared_writing_participant_count"])),
                participants,
                case_scope,
                code(identifier(profile["commit_receipt"])),
                code(profile["partial_commit_behavior"]),
            ]
        )
    lines.extend(
        table(
            [
                "Profile",
                "Declared writers",
                "Writing participants",
                "Exact case scope",
                "Receipt",
                "Partial commit",
            ],
            joint_rows,
        )
    )

    lines.extend(
        [
            "",
            "## State-domain registry",
            "",
            "Key coordinates define selector serialization.",
            "Join fields also include content-addressed equality axes.",
            "",
        ]
    )
    domain_rows: list[list[Any]] = []
    for selector in selectors:
        for state_domain in selector["state_domains"]:
            domain_rows.append(
                [
                    code(selector["selector_id"]),
                    code(state_domain["state_domain"]),
                    code(identifier(state_domain["key_type"])),
                    ", ".join(code(value) for value in state_domain["key_coordinates"]),
                    code(state_domain["initial_state"]),
                    ", ".join(code(value) for value in state_domain["terminal_states"])
                    or "None",
                    ", ".join(code(value) for value in state_domain["states"]),
                ]
            )
    lines.extend(
        table(
            [
                "Selector",
                "State domain",
                "Key type",
                "Key coordinates",
                "Initial",
                "Terminal",
                "States",
            ],
            domain_rows,
        )
    )

    lines.extend(
        [
            "",
            "## Event closure",
            "",
            "Each event has one receipt-free pre-CAS object.",
            "The winning durable CAS installs the selector and receipt DAG.",
            "Each row lists the exact cases and partition identities.",
            "",
        ]
    )
    for selector in selectors:
        lines.extend(
            [
                f"### {code(selector['selector_id'])}",
                "",
            ]
        )
        event_rows: list[list[Any]] = []
        for event in selector["events"]:
            event_key = (selector["selector_id"], event["event_id"])
            resource_effects = resource_effects_by_event.get(event_key, [])
            resource_mutations = resource_mutations_by_event.get(event_key, [])
            sidecar_names = [
                code(identifier(item["artifact"]))
                for item in event["post_cas_sidecars"]
                if item["artifact"] != selector["generic_receipt"]
            ]
            partition_summaries = []
            for partition in event["partition_effects"]:
                case_ids = ",".join(partition["applies_to_semantic_case_ids"])
                branch_ids = ",".join(
                    branch["branch_id"] for branch in partition["branches"]
                )
                partition_summaries.append(
                    f"{code(partition['partition_id'])} "
                    f"cases={case_ids} branches={branch_ids}"
                )
            event_rows.append(
                [
                    code(event["event_id"]),
                    code(identifier(event["transition_kind"])),
                    code(event["operation_scope"]),
                    "<br>".join(
                        (
                            f"{code(case['semantic_case_id'])} "
                            f"[{code(case['evidence_variant_id'])}; "
                            f"edges={','.join(case['state_edge_refs'])}]"
                        )
                        for case in event["transition_cases"]
                    ),
                    event_edge_summary(selector, event),
                    "<br>".join(partition_summaries) or "None",
                    code(identifier(event["pre_cas_content"]["artifact"])),
                    "<br>".join(
                        (
                            f"{code(row[3])} {code(row[4])} "
                            f"{code(row[5])} owner={code(row[6])}"
                        )
                        for row in resource_effects
                    )
                    or "None",
                    ", ".join(code(row[3]) for row in resource_mutations) or "None",
                    ", ".join(sidecar_names) or "Generic only",
                    code(
                        event.get(
                            "joint_selector_transaction_profile_ref",
                            "NONE",
                        )
                    ),
                ]
            )
        lines.extend(
            table(
                [
                    "Event",
                    "Transition kind",
                    "Scope",
                    "Exact cases",
                    "State effect",
                    "Exact partitions",
                    "Pre-CAS object",
                    "Resource effects",
                    "Derived mutation footprint",
                    "Specialized sidecars",
                    "Joint profile",
                ],
                event_rows,
            )
        )
        lines.append("")

    lines.extend(
        [
            "## Bound adversarial probes",
            "",
            (
                "These bindings identify exact local model source and "
                "deterministic output bytes."
            ),
            "The output owns its result counts; this table does not duplicate them.",
            "A matching digest is not external qualification.",
            "",
        ]
    )
    probe_rows = _bound_probe_rows(data["adversarial_probe_bindings"])
    lines.extend(
        table(
            ["Probe", "Command", "Script SHA-256", "stdout SHA-256"],
            probe_rows,
        )
    )
    lines.extend(
        [
            "",
            "## Digest closure",
            "",
        ]
    )
    commitments = data["closure_commitments"]
    lines.extend(
        table(
            ["Object", "SHA-256"],
            [
                [
                    "Expanded source",
                    code(expanded_sha256),
                ],
                [
                    "Artifact registry",
                    code(commitments["artifact_registry_sha256"]),
                ],
                [
                    "Global key-coordinate registry",
                    code(commitments["global_key_coordinate_registry_sha256"]),
                ],
                [
                    "Structural profiles",
                    code(commitments["structural_profiles_sha256"]),
                ],
            ],
        )
    )
    lines.extend(
        [
            "",
            "Run the checker before review:",
            "",
            "```bash",
            _checker_review_command(data),
            "python3 scripts/generate_selector_closure_matrix.py --check",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_SOURCE,
        help="compact selector source",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="generated Markdown path",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail if the generated view is stale",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="prove candidate mode is allocation-only and fail closed",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    actual: bytes | None = None
    source_snapshot: bytes | None = None
    adr_snapshots: dict[Path, bytes] = {}
    try:
        if args.self_test:
            if args.check:
                raise SelectorClosureGenerationError(
                    "--self-test cannot be combined with --check"
                )
            cases = run_self_test()
            print(
                "selector closure matrix self-test: PASS "
                f"cases={cases} candidate_relaxation=ALLOCATION_ONLY"
            )
            return 0
        _require_matrix_output_path_distinct(args.source, args.output)
        if args.check:
            if not args.output.exists() and not args.output.is_symlink():
                raise SelectorClosureGenerationError(f"missing {args.output}")
            actual = read_bounded_regular_file(
                args.output,
                maximum_bytes=MAX_EXPANDED_BYTES,
                label="selector closure matrix",
            )
        source_snapshot = read_bounded_regular_file(
            args.source,
            maximum_bytes=MAX_COMPACT_BYTES - 1,
            label="selector closure matrix source snapshot",
        )
        envelope, expanded = load_compact_source(args.source)
        if source_snapshot != canonical_bytes(envelope) + b"\n":
            raise SelectorClosureGenerationError(
                "compact source changed while the matrix input was loaded"
            )
        # This matrix is the review input that exposes missing allocations. An
        # exact fail-closed candidate must therefore remain renderable before
        # its local-only provenance review. Only allocation coverage is relaxed;
        # every architecture validator remains strict. Every other state uses
        # the complete validator, and normal compact generation remains closed.
        summary = _validate_matrix_source(
            expanded,
            adr_snapshot_sink=adr_snapshots.update,
        )
        expected_adr_paths = {
            Path(path)
            for path in (
                *ADR_ALLOCATION_PATHS,
                *(path for paths in ADR_ALLOCATION_MODULE_PATHS for path in paths),
            )
        }
        if set(adr_snapshots) != expected_adr_paths:
            raise SelectorClosureGenerationError(
                "matrix validator returned an incomplete or unexpected ADR source set"
            )
        generated = render(
            expanded,
            envelope["encoding"]["expanded_document_sha256"],
        )
        current_source = read_bounded_regular_file(
            args.source,
            maximum_bytes=MAX_COMPACT_BYTES - 1,
            label="selector closure matrix source stability check",
        )
        if current_source != source_snapshot:
            raise SelectorClosureGenerationError(
                "compact source changed during matrix generation"
            )
        _verify_adr_snapshots_unchanged(adr_snapshots)
    except (
        ClosureCheckError,
        KeyError,
        OSError,
        SelectorClosureCodecError,
        SelectorClosureGenerationError,
        TypeError,
    ) as error:
        print(
            f"selector closure matrix: FAIL: {error}",
            file=sys.stderr,
        )
        return 1

    if args.check:
        expected = generated.encode("utf-8")
        if actual is None:
            print(
                "selector closure matrix: FAIL: internal missing check bytes",
                file=sys.stderr,
            )
            return 1
        if actual != expected:
            print(
                f"selector closure matrix: FAIL: stale {args.output}",
                file=sys.stderr,
            )
            return 1
        try:
            final_output = read_bounded_regular_file(
                args.output,
                maximum_bytes=MAX_EXPANDED_BYTES,
                label="selector closure matrix final stability check",
            )
            final_source = read_bounded_regular_file(
                args.source,
                maximum_bytes=MAX_COMPACT_BYTES - 1,
                label="selector closure matrix source final stability check",
            )
            _verify_adr_snapshots_unchanged(adr_snapshots)
        except (ClosureCheckError, SelectorClosureCodecError) as error:
            print(
                f"selector closure matrix: FAIL: {error}",
                file=sys.stderr,
            )
            return 1
        if final_output != actual or final_source != source_snapshot:
            print(
                "selector closure matrix: FAIL: input or output changed during --check",
                file=sys.stderr,
            )
            return 1
        print(
            "selector closure matrix: PASS "
            f"events={summary.events} "
            f"expanded_sha256={summary.expanded_sha256}"
        )
        return 0

    generated_bytes = generated.encode("utf-8")
    try:
        if source_snapshot is None:
            raise SelectorClosureGenerationError(
                "internal missing compact source snapshot"
            )
        if len(generated_bytes) > MAX_EXPANDED_BYTES:
            raise SelectorClosureGenerationError(
                f"generated matrix exceeds {MAX_EXPANDED_BYTES} bytes"
            )
        _atomic_write(args.output, generated_bytes)
        installed = read_bounded_regular_file(
            args.output,
            maximum_bytes=MAX_EXPANDED_BYTES,
            label="installed selector closure matrix",
        )
        final_source = read_bounded_regular_file(
            args.source,
            maximum_bytes=MAX_COMPACT_BYTES - 1,
            label="selector closure matrix source final stability check",
        )
        if installed != generated_bytes:
            raise SelectorClosureGenerationError(
                "installed matrix differs from the prevalidated output"
            )
        if final_source != source_snapshot:
            raise SelectorClosureGenerationError(
                "compact source changed during matrix installation"
            )
        _verify_adr_snapshots_unchanged(adr_snapshots)
    except AtomicWriteOutcomeUnknownError as error:
        print(
            "selector closure matrix: OUTCOME UNKNOWN: "
            f"{error}; the destination may contain the requested bytes. "
            "Inspect and reconcile by application identity; do not retry "
            "automatically.",
            file=sys.stderr,
        )
        return 2
    except (
        ClosureCheckError,
        SelectorClosureCodecError,
        SelectorClosureGenerationError,
    ) as error:
        print(
            f"selector closure matrix: FAIL: {error}",
            file=sys.stderr,
        )
        return 1
    try:
        output_label = args.output.relative_to(ROOT)
    except ValueError:
        output_label = args.output
    print(
        "selector closure matrix: generated "
        f"{output_label} "
        f"events={summary.events} "
        f"expanded_sha256={summary.expanded_sha256}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
