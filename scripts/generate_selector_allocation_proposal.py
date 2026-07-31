#!/usr/bin/env python3
"""Compile an owner-free, non-authorizing selector-allocation review proposal.

The proposal preserves every v4 semantic review unit and its independently
committed mechanical origins and non-authoritative signals.  A route is only a
deterministic suggestion for later review.  No route, usage signal, prose
occurrence, digest, or generated file assigns ownership, accepts an ADR,
authenticates a reviewer, or grants protocol or release authority.
"""

from __future__ import annotations

import argparse
import copy
import os
import re
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, NoReturn

from check_selector_closure import (
    ALLOCATION_ORIGIN_KINDS,
    ALLOCATION_SIGNAL_KINDS,
    IDENTIFIER_TOKEN_RE,
    ClosureCheckError,
    ModelAllocation,
    _accepted_allocation_prose_identifiers,
    _candidate_allocation_adr_id,
    _extract_allocation_anchor,
    _model_allocation_sha256,
    _model_allocations,
    _model_origin_signal_commitment,
    validate_expanded_source,
)
from selector_allocation_inventory import (
    ADR_ALLOCATION_ANCHOR_BY_ID,
    ADR_ALLOCATION_MODULE_PATHS,
    ADR_ALLOCATION_PATHS,
    MAX_ADR_CORPUS_BYTES,
    MAX_ADR_DOCUMENT_BYTES,
    MODEL_ALLOCATION_PROJECTION_SCHEMA,
    MODEL_ORIGIN_SIGNAL_PROJECTION_SCHEMA,
)
from selector_closure_codec import (
    MAX_COMPACT_BYTES,
    AtomicWriteOutcomeUnknownError,
    SelectorClosureCodecError,
    _atomic_write_regular_file,
    canonical_bytes,
    canonical_sha256,
    decode_compact_source_bytes,
    parse_json_bytes,
    read_bounded_regular_file,
    validate_json_resource_bounds,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "docs" / "adr" / "selector-closure.source.v1.json"
DEFAULT_SCHEMA = ROOT / "docs" / "adr" / "selector-allocation.proposal.schema.v1.json"
DEFAULT_OUTPUT = ROOT / "docs" / "adr" / "selector-allocation.proposal.v1.json"

PROPOSAL_SCHEMA_FILE = "selector-allocation.proposal.schema.v1.json"
PROPOSAL_SCHEMA_ID = "ncp.b01-selector-allocation-proposal.v1"
PROPOSAL_SCHEMA_URL = (
    "https://sepahead.github.io/ncp/schemas/b01-selector-allocation-proposal.v1.json"
)
PROPOSAL_SCHEMA_SHA256 = (
    "bba560a33ef672721c74faa0f94ea05af5949be129f510250b55bb745f471541"
)
PROPOSAL_CLAIM_BOUNDARY = (
    "LOCAL_DETERMINISTIC_OWNER_FREE_REVIEW_PROPOSAL_ONLY_NOT_ALLOCATION_"
    "AUTHORITY_ADR_ACCEPTANCE_PROTOCOL_RELEASE_EXTERNAL_OR_INDEPENDENT_EVIDENCE"
)
MAX_PROPOSAL_BYTES = 12 * 1024 * 1024
MAX_PROPOSAL_SCHEMA_BYTES = 128 * 1024
MAX_PROPOSAL_ROWS = 65_536
MAX_COMPILER_SOURCE_BYTES = 2 * 1024 * 1024
MAX_COMPILER_SOURCE_SET_BYTES = 4 * 1024 * 1024
MAX_SCHEMA_ERRORS = 64

COMPILER_SOURCE_PATHS = (
    "scripts/check_selector_closure.py",
    "scripts/generate_selector_allocation_proposal.py",
    "scripts/selector_allocation_inventory.py",
    "scripts/selector_closure_codec.py",
    "scripts/selector_resource_closure.py",
)

ADR_IDS = tuple(f"ADR-{index:03d}" for index in range(1, 12))
SUGGESTED_DESTINATIONS = (*ADR_IDS, "UNMAPPED_SHARED")
ROUTE_RULE_CLASSES = (
    "BODY_ACCEPTED_PROSE_RULE",
    "BODY_DECLARATION_PARTITION_RULE",
    "DECLARING_SELECTOR_REGISTRY_RULE",
    "NO_TOTAL_RULE",
    "SEMANTIC_REFERENCE_RULE",
    "STRUCTURAL_PROFILE_RULE",
)
AMBIGUITY_FLAGS = (
    "MULTIPLE_ACCEPTED_PROSE_MATCHES",
    "MULTIPLE_DECLARING_SELECTORS",
    "MULTIPLE_PROSE_MENTIONS",
    "MULTIPLE_SELECTOR_USAGE_SIGNALS",
    "NO_ACCEPTED_PROSE_MATCH",
    "NO_DECLARING_SELECTOR",
    "RESOURCE_BACKING_SIGNAL_PRESENT",
    "SELECTOR_USAGE_SIGNAL_PRESENT",
    "STRUCTURAL_PROFILE_REFERENCE_SIGNAL_PRESENT",
    "SUGGESTED_ADR_DIFFERS_FROM_ACCEPTED_PROSE",
    "UNMAPPED_SHARED",
)

PROPOSAL_ROWS_DOMAIN = b"ncp.b01.selector-allocation.proposal-rows.v2\x00"
ORIGIN_KIND_DOMAIN = b"ncp.b01.selector-allocation.proposal-origin-kinds.v1\x00"
SIGNAL_KIND_DOMAIN = b"ncp.b01.selector-allocation.proposal-signal-kinds.v1\x00"
ROUTE_CLASS_DOMAIN = b"ncp.b01.selector-allocation.proposal-route-classes.v2\x00"
AMBIGUITY_DOMAIN = b"ncp.b01.selector-allocation.proposal-ambiguity-flags.v2\x00"
PROSE_SIGNAL_DOMAIN = b"ncp.b01.selector-allocation.proposal-prose-signals.v2\x00"
ADR_CORPUS_DOMAIN = b"ncp.b01.selector-allocation.proposal-adr-corpus.v1\x00"
COMPILER_SOURCE_SET_DOMAIN = (
    b"ncp.b01.selector-allocation.proposal-compiler-source-set.v1\x00"
)

COMMITMENT_ALGORITHM = (
    "SHA256_DOMAIN_THEN_UINT64_BE_CANONICAL_BYTE_LENGTH_THEN_CANONICAL_JSON"
)
COMMITMENT_CANONICALIZATION = "UTF8_JSON_SORTED_KEYS_NO_INSIGNIFICANT_WHITESPACE"

SELECTOR_LOCATION = re.compile(r"^selector-id::([A-Z][A-Z0-9_]*)")


class SelectorAllocationProposalError(ValueError):
    """The proposal input, route model, schema, or output is invalid."""


@dataclass(frozen=True)
class ProseCorpus:
    """Exact ADR text signals and content identities for one proposal cut."""

    accepted_by_adr: dict[str, frozenset[str]]
    all_by_adr: dict[str, frozenset[str]]
    source_rows: tuple[dict[str, Any], ...]
    snapshots: tuple[tuple[Path, bytes], ...]


@dataclass(frozen=True)
class CompilerSourceSet:
    """Exact repository source closure used to construct one proposal."""

    source_rows: tuple[dict[str, Any], ...]
    snapshots: tuple[tuple[Path, bytes], ...]


@dataclass(frozen=True)
class ProposalInputSnapshot:
    """One bounded input byte identity used by a proposal operation."""

    label: str
    maximum_bytes: int
    path: Path
    raw: bytes


@dataclass(frozen=True)
class ProposalRoute:
    """One deterministic suggestion and its explicit non-authorizing basis."""

    class_id: str
    suggested_adr_id: str
    basis_values: tuple[str, ...]


def _fail(message: str) -> NoReturn:
    raise SelectorAllocationProposalError(message)


def _require(condition: bool, message: str) -> None:
    if not condition:
        _fail(message)


def _require_exact(actual: Any, expected: Any, label: str) -> None:
    if actual != expected:
        _fail(f"{label}: expected {expected!r}, got {actual!r}")


def _lexical_absolute_path(path: Path, *, label: str) -> Path:
    try:
        raw_path = os.fspath(path)
    except TypeError as error:
        _fail(f"{label}: invalid path value: {error}")
    _require(
        type(raw_path) is str and raw_path and "\x00" not in raw_path,
        f"{label}: path must be nonempty text without NUL",
    )
    try:
        return Path(os.path.abspath(raw_path))
    except (OSError, TypeError, ValueError) as error:
        _fail(f"{label}: path is invalid: {error}")


def _relative_repo_path(path: Path, *, label: str) -> str:
    absolute = _lexical_absolute_path(path, label=label)
    try:
        relative = absolute.relative_to(ROOT)
    except ValueError as error:
        _fail(f"{label}: path is outside the repository: {error}")
    _require(
        relative.parts
        and all(part not in {"", ".", ".."} for part in relative.parts),
        f"{label}: path is not a closed repository-relative path",
    )
    return relative.as_posix()


def _same_file_or_resolved_path(first: Path, second: Path) -> bool:
    """Compare lexical, resolved, and existing-inode path identities."""

    first_absolute = _lexical_absolute_path(first, label="first path identity")
    second_absolute = _lexical_absolute_path(second, label="second path identity")
    if first_absolute == second_absolute:
        return True
    try:
        if os.path.samefile(first_absolute, second_absolute):
            return True
    except FileNotFoundError:
        pass
    except OSError as error:
        _fail(f"cannot compare existing path identities: {error}")
    try:
        return first_absolute.resolve(strict=False) == second_absolute.resolve(
            strict=False
        )
    except (OSError, RuntimeError) as error:
        _fail(f"cannot resolve path identities: {error}")


def _proposal_input_snapshots(
    *,
    source_path: Path,
    source_raw: bytes,
    schema_path: Path,
    schema_raw: bytes,
    prose: ProseCorpus,
    compiler_sources: CompilerSourceSet,
) -> tuple[ProposalInputSnapshot, ...]:
    snapshots = [
        ProposalInputSnapshot(
            label="proposal compact selector source",
            maximum_bytes=MAX_COMPACT_BYTES - 1,
            path=source_path,
            raw=source_raw,
        ),
        ProposalInputSnapshot(
            label="proposal schema",
            maximum_bytes=MAX_PROPOSAL_SCHEMA_BYTES,
            path=schema_path,
            raw=schema_raw,
        ),
    ]
    snapshots.extend(
        ProposalInputSnapshot(
            label="proposal compiler source",
            maximum_bytes=MAX_COMPILER_SOURCE_BYTES,
            path=path,
            raw=raw,
        )
        for path, raw in compiler_sources.snapshots
    )
    snapshots.extend(
        ProposalInputSnapshot(
            label="proposal prose source",
            maximum_bytes=MAX_ADR_DOCUMENT_BYTES,
            path=path,
            raw=raw,
        )
        for path, raw in prose.snapshots
    )
    return tuple(snapshots)


def _require_input_snapshots_unchanged(
    snapshots: tuple[ProposalInputSnapshot, ...],
) -> None:
    for snapshot in snapshots:
        current = read_bounded_regular_file(
            snapshot.path,
            maximum_bytes=snapshot.maximum_bytes,
            label=f"{snapshot.label} stability check",
        )
        _require_exact(
            current,
            snapshot.raw,
            f"{snapshot.path}: {snapshot.label} bytes",
        )


def _require_output_distinct_from_inputs(
    output_path: Path,
    snapshots: tuple[ProposalInputSnapshot, ...],
) -> None:
    for snapshot in snapshots:
        _require(
            not _same_file_or_resolved_path(output_path, snapshot.path),
            f"proposal output must not alias {snapshot.label}",
        )


def _require_final_cut_unchanged(
    *,
    output_path: Path,
    output_raw: bytes,
    snapshots: tuple[ProposalInputSnapshot, ...],
    phase_hook: Any = None,
    phase: str,
) -> None:
    """Bracket a final output identity with two bounded input passes."""

    if phase_hook is not None:
        phase_hook(phase)
    _require_input_snapshots_unchanged(snapshots)
    first_output = read_bounded_regular_file(
        output_path,
        maximum_bytes=MAX_PROPOSAL_BYTES,
        label="selector allocation proposal final output",
    )
    _require_exact(first_output, output_raw, "proposal final output bytes")
    _require_input_snapshots_unchanged(snapshots)
    second_output = read_bounded_regular_file(
        output_path,
        maximum_bytes=MAX_PROPOSAL_BYTES,
        label="selector allocation proposal repeated final output",
    )
    _require_exact(
        second_output,
        first_output,
        "proposal repeated final output bytes",
    )


def _install_proposal_if_inputs_current(
    *,
    output_path: Path,
    output_raw: bytes,
    snapshots: tuple[ProposalInputSnapshot, ...],
    phase_hook: Any = None,
) -> None:
    """Recheck inputs, then install with a late physical-alias fence."""

    _require_input_snapshots_unchanged(snapshots)
    _require_output_distinct_from_inputs(output_path, snapshots)

    def write_phase(phase: str) -> None:
        if phase_hook is not None:
            phase_hook(f"atomic-write:{phase}")
        if phase == "before-install":
            _require_output_distinct_from_inputs(output_path, snapshots)

    _atomic_write_regular_file(
        output_path,
        output_raw,
        label="selector allocation proposal output",
        phase_hook=write_phase,
    )


def _projection_sha256(domain: bytes, value: Any) -> str:
    payload = canonical_bytes(value)
    digest = sha256()
    digest.update(domain)
    digest.update(len(payload).to_bytes(8, "big"))
    digest.update(payload)
    return digest.hexdigest()


def _read_compiler_source_set() -> CompilerSourceSet:
    """Read the closed repository source closure for proposal construction."""

    source_rows: list[dict[str, Any]] = []
    snapshots: list[tuple[Path, bytes]] = []
    total_bytes = 0
    for relative_path in COMPILER_SOURCE_PATHS:
        path = ROOT / relative_path
        raw = read_bounded_regular_file(
            path,
            maximum_bytes=MAX_COMPILER_SOURCE_BYTES,
            label=f"proposal compiler source {relative_path}",
        )
        total_bytes += len(raw)
        _require(
            total_bytes <= MAX_COMPILER_SOURCE_SET_BYTES,
            (
                "proposal compiler source set exceeds "
                f"{MAX_COMPILER_SOURCE_SET_BYTES} bytes"
            ),
        )
        source_rows.append(
            {
                "byte_length": len(raw),
                "path": relative_path,
                "sha256": sha256(raw).hexdigest(),
            }
        )
        snapshots.append((path, raw))
    _require_exact(
        [row["path"] for row in source_rows],
        sorted(COMPILER_SOURCE_PATHS),
        "proposal compiler source order",
    )
    return CompilerSourceSet(
        source_rows=tuple(source_rows),
        snapshots=tuple(snapshots),
    )


def _require_compiler_snapshots_unchanged(
    compiler_sources: CompilerSourceSet,
) -> None:
    for path, expected in compiler_sources.snapshots:
        current = read_bounded_regular_file(
            path,
            maximum_bytes=MAX_COMPILER_SOURCE_BYTES,
            label="proposal compiler source stability check",
        )
        _require_exact(current, expected, f"{path}: proposal compiler source bytes")


def _class_summary(
    *,
    classes: tuple[str, ...],
    observed: Counter[str],
    domain: bytes,
    projection: Any,
) -> dict[str, Any]:
    unknown = set(observed) - set(classes)
    _require(not unknown, f"class summary contains unknown values: {sorted(unknown)}")
    return {
        "algorithm": COMMITMENT_ALGORITHM,
        "canonicalization": COMMITMENT_CANONICALIZATION,
        "counts": [
            {"class": class_id, "count": observed[class_id]} for class_id in classes
        ],
        "domain_hex": domain.hex(),
        "projection_sha256": _projection_sha256(domain, projection),
    }


def _load_schema(path: Path) -> tuple[bytes, dict[str, Any]]:
    raw = read_bounded_regular_file(
        path,
        maximum_bytes=MAX_PROPOSAL_SCHEMA_BYTES,
        label="selector allocation proposal schema",
    )
    _require_exact(
        sha256(raw).hexdigest(),
        PROPOSAL_SCHEMA_SHA256,
        "proposal schema reviewed byte identity",
    )
    schema = parse_json_bytes(
        raw,
        label=str(path),
        maximum_bytes=MAX_PROPOSAL_SCHEMA_BYTES,
    )
    _require(isinstance(schema, dict), "proposal schema must be an object")
    _require_exact(
        schema.get("$schema"),
        "https://json-schema.org/draft/2020-12/schema",
        "proposal schema dialect",
    )
    _require_exact(schema.get("$id"), PROPOSAL_SCHEMA_URL, "proposal schema $id")
    _require_exact(schema.get("type"), "object", "proposal schema root type")
    _require_exact(
        schema.get("additionalProperties"),
        False,
        "proposal schema root closure",
    )
    try:
        from jsonschema import Draft202012Validator
        from jsonschema.exceptions import SchemaError
    except ImportError as error:
        _fail(f"jsonschema is required for full proposal validation: {error}")
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as error:
        _fail(f"proposal schema is invalid: {error.message}")
    return raw, schema


def _validate_schema_instance(value: Any, schema: dict[str, Any]) -> None:
    try:
        from jsonschema import Draft202012Validator
    except ImportError as error:
        _fail(f"jsonschema is required for full proposal validation: {error}")
    errors = []
    truncated = False
    for error in Draft202012Validator(schema).iter_errors(value):
        if len(errors) == MAX_SCHEMA_ERRORS:
            truncated = True
            break
        errors.append(error)
    if errors:
        first = min(
            errors,
            key=lambda error: (
                tuple(str(part) for part in error.absolute_path),
                error.validator or "",
                tuple(str(part) for part in error.absolute_schema_path),
            ),
        )
        path = "$" + "".join(
            f"[{part}]" if isinstance(part, int) else f".{part}"
            for part in first.absolute_path
        )
        _fail(
            "proposal fails full JSON Schema validation: "
            f"{path}: {first.message}; errors="
            + (f">={MAX_SCHEMA_ERRORS + 1}" if truncated else str(len(errors)))
        )


def _read_utf8_source(
    path: Path,
    *,
    label: str,
) -> tuple[bytes, str, tuple[int, int]]:
    try:
        before = os.stat(path, follow_symlinks=False)
    except OSError as error:
        _fail(f"{label}: cannot stat source before read: {error}")
    raw = read_bounded_regular_file(
        path,
        maximum_bytes=MAX_ADR_DOCUMENT_BYTES,
        label=label,
    )
    try:
        after = os.stat(path, follow_symlinks=False)
    except OSError as error:
        _fail(f"{label}: cannot stat source after read: {error}")
    fingerprint_fields = (
        "st_dev",
        "st_ino",
        "st_mode",
        "st_nlink",
        "st_uid",
        "st_size",
        "st_mtime_ns",
        "st_ctime_ns",
    )
    _require_exact(
        tuple(getattr(before, field) for field in fingerprint_fields),
        tuple(getattr(after, field) for field in fingerprint_fields),
        f"{label}: path snapshot",
    )
    try:
        return raw, raw.decode("utf-8"), (after.st_dev, after.st_ino)
    except UnicodeDecodeError as error:
        _fail(f"{label}: source is not UTF-8: {error}")


def _read_prose_corpus() -> ProseCorpus:
    accepted_by_adr: dict[str, frozenset[str]] = {}
    all_by_adr: dict[str, frozenset[str]] = {}
    source_rows: list[dict[str, Any]] = []
    snapshots: list[tuple[Path, bytes]] = []
    source_identities: dict[tuple[int, int], str] = {}
    corpus_bytes = 0

    for index, relative_main in enumerate(ADR_ALLOCATION_PATHS, 1):
        adr_id = f"ADR-{index:03d}"
        main_path = ROOT / relative_main
        main_raw, main_text, identity = _read_utf8_source(
            main_path,
            label=f"{adr_id} proposal prose source",
        )
        corpus_bytes += len(main_raw)
        _require(
            corpus_bytes <= MAX_ADR_CORPUS_BYTES,
            f"proposal ADR corpus exceeds {MAX_ADR_CORPUS_BYTES} bytes",
        )
        _require(
            identity not in source_identities,
            f"{adr_id}: proposal prose source aliases {source_identities.get(identity)}",
        )
        source_identities[identity] = relative_main
        _extract_allocation_anchor(
            main_text,
            expected_anchor_id=ADR_ALLOCATION_ANCHOR_BY_ID[adr_id],
            label=f"{adr_id} proposal prose source",
        )
        snapshots.append((main_path, main_raw))
        texts = [main_text]
        module_rows: list[dict[str, Any]] = []
        for module_index, relative_module in enumerate(
            ADR_ALLOCATION_MODULE_PATHS[index - 1]
        ):
            module_path = ROOT / relative_module
            module_raw, module_text, module_identity = _read_utf8_source(
                module_path,
                label=f"{adr_id} proposal prose module {module_index}",
            )
            corpus_bytes += len(module_raw)
            _require(
                corpus_bytes <= MAX_ADR_CORPUS_BYTES,
                f"proposal ADR corpus exceeds {MAX_ADR_CORPUS_BYTES} bytes",
            )
            _require(
                module_identity not in source_identities,
                (
                    f"{adr_id}: proposal prose module aliases "
                    f"{source_identities.get(module_identity)}"
                ),
            )
            source_identities[module_identity] = relative_module
            snapshots.append((module_path, module_raw))
            texts.append(module_text)
            module_rows.append(
                {
                    "byte_length": len(module_raw),
                    "path": relative_module,
                    "sha256": sha256(module_raw).hexdigest(),
                }
            )
        accepted_by_adr[adr_id] = frozenset().union(
            *(
                frozenset(_accepted_allocation_prose_identifiers(text))
                for text in texts
            )
        )
        all_by_adr[adr_id] = frozenset().union(
            *(frozenset(IDENTIFIER_TOKEN_RE.findall(text)) for text in texts)
        )
        source_rows.append(
            {
                "adr_id": adr_id,
                "allocation_anchor_id": ADR_ALLOCATION_ANCHOR_BY_ID[adr_id],
                "main": {
                    "byte_length": len(main_raw),
                    "path": relative_main,
                    "sha256": sha256(main_raw).hexdigest(),
                },
                "modules": module_rows,
            }
        )

    _require_exact(tuple(accepted_by_adr), ADR_IDS, "proposal prose ADR set")
    return ProseCorpus(
        accepted_by_adr=accepted_by_adr,
        all_by_adr=all_by_adr,
        source_rows=tuple(source_rows),
        snapshots=tuple(snapshots),
    )


def _require_prose_snapshots_unchanged(corpus: ProseCorpus) -> None:
    for path, expected in corpus.snapshots:
        current = read_bounded_regular_file(
            path,
            maximum_bytes=MAX_ADR_DOCUMENT_BYTES,
            label="proposal prose source stability check",
        )
        _require_exact(current, expected, f"{path}: proposal prose source bytes")


def _matching_adr_ids(
    exact_name: str,
    *,
    identifiers_by_adr: dict[str, frozenset[str]],
) -> list[str]:
    return [adr_id for adr_id in ADR_IDS if exact_name in identifiers_by_adr[adr_id]]


def _declaring_selector_ids(allocation: ModelAllocation) -> tuple[str, ...]:
    selector_ids: set[str] = set()
    for origin in allocation.origins:
        match = SELECTOR_LOCATION.match(origin.semantic_location)
        if match is not None:
            selector_ids.add(match.group(1))
    return tuple(sorted(selector_ids))


def _signal_locations(
    allocation: ModelAllocation,
    evidence_kind: str,
) -> tuple[str, ...]:
    return tuple(
        sorted(
            signal.semantic_location
            for signal in allocation.signals
            if signal.evidence_kind == evidence_kind
        )
    )


def _proposal_route(
    allocation: ModelAllocation,
    *,
    prose: ProseCorpus,
) -> ProposalRoute:
    declaring_selector_ids = _declaring_selector_ids(allocation)
    suggested_adr_id = _candidate_allocation_adr_id(
        allocation,
        accepted_prose_identifiers={
            adr_id: set(values) for adr_id, values in prose.accepted_by_adr.items()
        },
    )
    _require(
        suggested_adr_id in SUGGESTED_DESTINATIONS,
        f"{allocation.unit_id}: route returned an unknown destination",
    )
    if suggested_adr_id == "UNMAPPED_SHARED":
        result = ProposalRoute("NO_TOTAL_RULE", suggested_adr_id, ())
    elif allocation.kind == "PROFILE":
        result = ProposalRoute(
            "STRUCTURAL_PROFILE_RULE",
            suggested_adr_id,
            (allocation.semantic_ref,),
        )
    elif declaring_selector_ids:
        if (
            declaring_selector_ids == ("BODY_SESSION_CONTROL",)
            and allocation.kind == "EVENT"
            and suggested_adr_id == "ADR-006"
            and allocation.exact_name in prose.accepted_by_adr["ADR-006"]
        ):
            result = ProposalRoute(
                "BODY_ACCEPTED_PROSE_RULE",
                suggested_adr_id,
                (
                    "BODY_SESSION_CONTROL",
                    f"accepted-prose::{suggested_adr_id}::{allocation.exact_name}",
                ),
            )
        else:
            class_id = (
                "BODY_DECLARATION_PARTITION_RULE"
                if declaring_selector_ids == ("BODY_SESSION_CONTROL",)
                else "DECLARING_SELECTOR_REGISTRY_RULE"
            )
            result = ProposalRoute(
                class_id,
                suggested_adr_id,
                declaring_selector_ids,
            )
    else:
        result = ProposalRoute(
            "SEMANTIC_REFERENCE_RULE",
            suggested_adr_id,
            (allocation.semantic_ref,),
        )
    _require(
        result.class_id in ROUTE_RULE_CLASSES,
        f"{allocation.unit_id}: route returned an unknown rule class",
    )
    return result


def _ambiguity_flags(
    allocation: ModelAllocation,
    *,
    route: ProposalRoute,
    prose_adr_ids: list[str],
    accepted_prose_adr_ids: list[str],
) -> list[str]:
    flags: set[str] = set()
    declaring_selector_ids = _declaring_selector_ids(allocation)
    usage_signals = _signal_locations(allocation, "SELECTOR_USAGE")
    if (
        allocation.kind in {"EVENT", "TYPE"}
        and not declaring_selector_ids
    ):
        flags.add("NO_DECLARING_SELECTOR")
    if len(declaring_selector_ids) > 1:
        flags.add("MULTIPLE_DECLARING_SELECTORS")
    if usage_signals:
        flags.add("SELECTOR_USAGE_SIGNAL_PRESENT")
    if len(usage_signals) > 1:
        flags.add("MULTIPLE_SELECTOR_USAGE_SIGNALS")
    if _signal_locations(allocation, "RESOURCE_BACKING"):
        flags.add("RESOURCE_BACKING_SIGNAL_PRESENT")
    if _signal_locations(allocation, "STRUCTURAL_PROFILE_REFERENCE"):
        flags.add("STRUCTURAL_PROFILE_REFERENCE_SIGNAL_PRESENT")
    if not accepted_prose_adr_ids:
        flags.add("NO_ACCEPTED_PROSE_MATCH")
    elif len(accepted_prose_adr_ids) > 1:
        flags.add("MULTIPLE_ACCEPTED_PROSE_MATCHES")
    if len(prose_adr_ids) > 1:
        flags.add("MULTIPLE_PROSE_MENTIONS")
    if (
        route.suggested_adr_id in ADR_IDS
        and accepted_prose_adr_ids
        and route.suggested_adr_id not in accepted_prose_adr_ids
    ):
        flags.add("SUGGESTED_ADR_DIFFERS_FROM_ACCEPTED_PROSE")
    if route.suggested_adr_id == "UNMAPPED_SHARED":
        flags.add("UNMAPPED_SHARED")
    _require(
        flags.issubset(AMBIGUITY_FLAGS),
        f"proposal produced unknown ambiguity flags: {sorted(flags)}",
    )
    return sorted(flags)


def _evidence_rows(allocation: ModelAllocation, *, origin: bool) -> list[dict[str, str]]:
    evidence = allocation.origins if origin else allocation.signals
    admitted = ALLOCATION_ORIGIN_KINDS if origin else ALLOCATION_SIGNAL_KINDS
    rows = [
        {
            "evidence_kind": item.evidence_kind,
            "semantic_location": item.semantic_location,
        }
        for item in evidence
    ]
    _require(
        all(row["evidence_kind"] in admitted for row in rows),
        f"{allocation.unit_id}: proposal contains an unknown evidence kind",
    )
    _require_exact(
        rows,
        sorted(
            rows,
            key=lambda row: (
                row["evidence_kind"],
                row["semantic_location"],
            ),
        ),
        "evidence order",
    )
    return rows


def _compile_rows(
    data: dict[str, Any],
    *,
    prose: ProseCorpus,
) -> tuple[set[ModelAllocation], list[dict[str, Any]]]:
    model = _model_allocations(data)
    _require(
        0 < len(model) <= MAX_PROPOSAL_ROWS,
        f"model allocation count is outside 1..{MAX_PROPOSAL_ROWS}",
    )
    rows: list[dict[str, Any]] = []
    for allocation in sorted(model):
        route = _proposal_route(allocation, prose=prose)
        prose_adr_ids = _matching_adr_ids(
            allocation.exact_name,
            identifiers_by_adr=prose.all_by_adr,
        )
        accepted_prose_adr_ids = _matching_adr_ids(
            allocation.exact_name,
            identifiers_by_adr=prose.accepted_by_adr,
        )
        rows.append(
            {
                "accepted_prose_adr_ids": accepted_prose_adr_ids,
                "ambiguity_flags": _ambiguity_flags(
                    allocation,
                    route=route,
                    prose_adr_ids=prose_adr_ids,
                    accepted_prose_adr_ids=accepted_prose_adr_ids,
                ),
                "declaring_selector_ids": list(
                    _declaring_selector_ids(allocation)
                ),
                "exact_name": allocation.exact_name,
                "kind": allocation.kind,
                "origin_evidence": _evidence_rows(allocation, origin=True),
                "prose_adr_ids": prose_adr_ids,
                "route_basis_values": list(route.basis_values),
                "route_rule_class": route.class_id,
                "semantic_ref": allocation.semantic_ref,
                "signal_evidence": _evidence_rows(allocation, origin=False),
                "suggested_adr_id": route.suggested_adr_id,
                "suggested_source_anchor": (
                    ADR_ALLOCATION_ANCHOR_BY_ID[route.suggested_adr_id]
                    if route.suggested_adr_id in ADR_IDS
                    else None
                ),
                "unit_id": allocation.unit_id,
            }
        )
    _require_exact(
        [
            [row["kind"], row["exact_name"], row["semantic_ref"], row["unit_id"]]
            for row in rows
        ],
        [allocation.identity_row() for allocation in sorted(model)],
        "proposal v4 model identity preservation",
    )
    return model, rows


def _build_summary(
    *,
    model: set[ModelAllocation],
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    kind_counts = Counter(allocation.kind for allocation in model)
    origin_counts = Counter(
        evidence.evidence_kind
        for allocation in model
        for evidence in allocation.origins
    )
    signal_counts = Counter(
        evidence.evidence_kind
        for allocation in model
        for evidence in allocation.signals
    )
    route_counts = Counter(row["route_rule_class"] for row in rows)
    destination_counts = Counter(row["suggested_adr_id"] for row in rows)
    ambiguity_counts = Counter(
        flag for row in rows for flag in row["ambiguity_flags"]
    )
    origin_projection = [
        [row["unit_id"], row["origin_evidence"]] for row in rows
    ]
    signal_projection = [
        [row["unit_id"], row["signal_evidence"]] for row in rows
    ]
    route_projection = [
        [
            row["unit_id"],
            row["route_rule_class"],
            row["route_basis_values"],
            row["suggested_adr_id"],
            row["suggested_source_anchor"],
        ]
        for row in rows
    ]
    ambiguity_projection = [
        [row["unit_id"], row["ambiguity_flags"]] for row in rows
    ]
    prose_projection = [
        [
            row["unit_id"],
            row["prose_adr_ids"],
            row["accepted_prose_adr_ids"],
        ]
        for row in rows
    ]
    origin_row_count, origin_signal_sha256 = _model_origin_signal_commitment(model)
    return {
        "ambiguity_flag_summary": _class_summary(
            classes=AMBIGUITY_FLAGS,
            observed=ambiguity_counts,
            domain=AMBIGUITY_DOMAIN,
            projection=ambiguity_projection,
        ),
        "candidate_route_counts": [
            {"class": destination, "count": destination_counts[destination]}
            for destination in SUGGESTED_DESTINATIONS
        ],
        "model_allocation_count": len(model),
        "model_allocation_sha256": _model_allocation_sha256(model),
        "model_kind_counts": {
            kind: kind_counts[kind]
            for kind in ("EVENT", "PROFILE", "RESOURCE", "SELECTOR", "STATE", "TYPE")
        },
        "model_origin_signal_row_count": origin_row_count,
        "model_origin_signal_sha256": origin_signal_sha256,
        "origin_kind_summary": _class_summary(
            classes=tuple(sorted(ALLOCATION_ORIGIN_KINDS)),
            observed=origin_counts,
            domain=ORIGIN_KIND_DOMAIN,
            projection=origin_projection,
        ),
        "proposal_row_count": len(rows),
        "proposal_rows_commitment": {
            "algorithm": COMMITMENT_ALGORITHM,
            "canonicalization": COMMITMENT_CANONICALIZATION,
            "domain_hex": PROPOSAL_ROWS_DOMAIN.hex(),
            "projection_sha256": _projection_sha256(PROPOSAL_ROWS_DOMAIN, rows),
        },
        "prose_signal_commitment": {
            "algorithm": COMMITMENT_ALGORITHM,
            "canonicalization": COMMITMENT_CANONICALIZATION,
            "domain_hex": PROSE_SIGNAL_DOMAIN.hex(),
            "projection_sha256": _projection_sha256(
                PROSE_SIGNAL_DOMAIN,
                prose_projection,
            ),
        },
        "route_rule_summary": _class_summary(
            classes=ROUTE_RULE_CLASSES,
            observed=route_counts,
            domain=ROUTE_CLASS_DOMAIN,
            projection=route_projection,
        ),
        "rows_with_ambiguity_count": sum(
            bool(row["ambiguity_flags"]) for row in rows
        ),
        "signal_kind_summary": _class_summary(
            classes=tuple(sorted(ALLOCATION_SIGNAL_KINDS)),
            observed=signal_counts,
            domain=SIGNAL_KIND_DOMAIN,
            projection=signal_projection,
        ),
        "unmapped_shared_row_count": destination_counts["UNMAPPED_SHARED"],
    }


def _build_proposal(
    data: dict[str, Any],
    *,
    prose: ProseCorpus,
    compiler_sources: CompilerSourceSet,
    compact_path_label: str,
    compact_raw: bytes,
    schema_path_label: str,
    schema_raw: bytes,
) -> dict[str, Any]:
    model, rows = _compile_rows(data, prose=prose)
    summary = _build_summary(model=model, rows=rows)
    adr_sources = [copy.deepcopy(row) for row in prose.source_rows]
    compiler_source_rows = [
        copy.deepcopy(row) for row in compiler_sources.source_rows
    ]
    source = {
        "adr_corpus": {
            "adr_count": len(adr_sources),
            "adr_sources": adr_sources,
            "algorithm": COMMITMENT_ALGORITHM,
            "canonicalization": COMMITMENT_CANONICALIZATION,
            "domain_hex": ADR_CORPUS_DOMAIN.hex(),
            "projection_sha256": _projection_sha256(
                ADR_CORPUS_DOMAIN,
                adr_sources,
            ),
        },
        "compact_source": {
            "byte_length": len(compact_raw),
            "path": compact_path_label,
            "sha256": sha256(compact_raw).hexdigest(),
        },
        "expanded_source": {
            "canonical_byte_length": len(canonical_bytes(data)),
            "schema": data.get("schema", "ncp.b01-selector-closure-source.v1"),
            "sha256": canonical_sha256(data),
        },
        "model_projection": {
            "allocation_count": len(model),
            "allocation_sha256": _model_allocation_sha256(model),
            "origin_signal_row_count": summary["model_origin_signal_row_count"],
            "origin_signal_sha256": summary["model_origin_signal_sha256"],
            "origin_signal_schema": MODEL_ORIGIN_SIGNAL_PROJECTION_SCHEMA,
            "schema": MODEL_ALLOCATION_PROJECTION_SCHEMA,
        },
        "proposal_compiler": {
            "algorithm": COMMITMENT_ALGORITHM,
            "canonicalization": COMMITMENT_CANONICALIZATION,
            "domain_hex": COMPILER_SOURCE_SET_DOMAIN.hex(),
            "entrypoint": "scripts/generate_selector_allocation_proposal.py",
            "projection_sha256": _projection_sha256(
                COMPILER_SOURCE_SET_DOMAIN,
                compiler_source_rows,
            ),
            "source_count": len(compiler_source_rows),
            "sources": compiler_source_rows,
        },
        "proposal_schema": {
            "byte_length": len(schema_raw),
            "id": PROPOSAL_SCHEMA_ID,
            "path": schema_path_label,
            "sha256": sha256(schema_raw).hexdigest(),
        },
    }
    return {
        "$schema": PROPOSAL_SCHEMA_FILE,
        "authority_boundary": {
            "allocation_effect": "NO_ASSIGNMENT_OR_ACCEPTANCE_AUTHORITY",
            "evidence_effect": "MECHANICAL_ORIGIN_AND_SIGNAL_DISCLOSURE_ONLY",
            "proposal_effect": (
                "NO_RUNTIME_PROTOCOL_REVIEW_RELEASE_EXTERNAL_OR_INDEPENDENT_AUTHORITY"
            ),
            "usage_effect": "SIGNAL_ONLY_NEVER_OWNERSHIP_OR_ROUTE_AUTHORITY",
            "unmapped_effect": "FAIL_CLOSED_REQUIRES_EXPLICIT_REVIEW",
        },
        "candidate": "1.0.0-rc.1",
        "claim_boundary": PROPOSAL_CLAIM_BOUNDARY,
        "normative": False,
        "rows": rows,
        "schema": PROPOSAL_SCHEMA_ID,
        "source": source,
        "summary": summary,
        "task": "B01",
    }


def _validate_proposal_semantics(
    proposal: dict[str, Any],
    *,
    data: dict[str, Any],
    prose: ProseCorpus,
    compiler_sources: CompilerSourceSet,
    compact_path_label: str,
    compact_raw: bytes,
    schema_path_label: str,
    schema_raw: bytes,
) -> None:
    """Recompile every relationship; JSON Schema alone is not semantic proof."""

    expected = _build_proposal(
        data,
        prose=prose,
        compiler_sources=compiler_sources,
        compact_path_label=compact_path_label,
        compact_raw=compact_raw,
        schema_path_label=schema_path_label,
        schema_raw=schema_raw,
    )
    _require_exact(
        canonical_bytes(proposal),
        canonical_bytes(expected),
        "proposal semantic recompilation",
    )


def _synthetic_prose() -> ProseCorpus:
    accepted = {adr_id: frozenset() for adr_id in ADR_IDS}
    all_identifiers = {adr_id: frozenset() for adr_id in ADR_IDS}
    accepted["ADR-004"] = frozenset({"SAME_EVENT"})
    accepted["ADR-006"] = frozenset({"BODY_RELEASE_ACCEPTED"})
    all_identifiers["ADR-004"] = frozenset({"NovelType", "SAME_EVENT"})
    all_identifiers["ADR-006"] = frozenset({"BODY_RELEASE_ACCEPTED"})
    rows = [
        {
            "adr_id": adr_id,
            "allocation_anchor_id": ADR_ALLOCATION_ANCHOR_BY_ID[adr_id],
            "main": {
                "byte_length": 1,
                "path": ADR_ALLOCATION_PATHS[index - 1],
                "sha256": "1" * 64,
            },
            "modules": [],
        }
        for index, adr_id in enumerate(ADR_IDS, 1)
    ]
    return ProseCorpus(
        accepted_by_adr=accepted,
        all_by_adr=all_identifiers,
        source_rows=tuple(rows),
        snapshots=(),
    )


def _synthetic_selector(
    selector_id: str,
    *,
    artifact_reference: str | None = None,
    declares_event: bool = False,
    event_id: str = "SAME_EVENT",
) -> dict[str, Any]:
    return {
        "events": (
            [
                {
                    "event_id": event_id,
                    "transition_kind": f"same-transition-kind::{event_id}",
                }
            ]
            if declares_event
            else []
        ),
        "owned_resources": [],
        "selector_id": selector_id,
        "state_domains": [],
        "synthetic_artifact_reference": artifact_reference,
    }


def _synthetic_data(*, usage_selector: str) -> dict[str, Any]:
    novel_reference = "novel-type::NovelType"
    return {
        "actor_profiles": {},
        "artifacts": [
            novel_reference,
            "same-transition-kind::SAME_EVENT",
        ],
        "selectors": [
            _synthetic_selector(
                "CONSUMER_SEMANTIC_CAPTURE",
                artifact_reference=(
                    novel_reference
                    if usage_selector == "CONSUMER_SEMANTIC_CAPTURE"
                    else None
                ),
            ),
            _synthetic_selector(
                "OBSERVER_AUTHORIZATION",
                artifact_reference=(
                    novel_reference
                    if usage_selector == "OBSERVER_AUTHORIZATION"
                    else None
                ),
                declares_event=True,
            ),
        ],
    }


def _run_synthetic_self_test(
    schema_raw: bytes,
    schema: dict[str, Any],
) -> int:
    killed = 0
    _require_exact(
        _projection_sha256(PROPOSAL_ROWS_DOMAIN, []),
        "87acf1fd60f576da617e666938422d1759455488c3e73eaa94db0e5511b34107",
        "proposal framed commitment fixed vector",
    )
    _require_exact(
        _projection_sha256(COMPILER_SOURCE_SET_DOMAIN, []),
        "aeb69522973710e8cd2a1a991b90d02355e455d93b07993706e780a4684e582e",
        "compiler source-set framed commitment fixed vector",
    )
    compiler_sources = _read_compiler_source_set()

    def expect_rejection(action: Any, label: str) -> None:
        nonlocal killed
        try:
            action()
        except SelectorAllocationProposalError:
            killed += 1
        else:
            _fail(f"self-test accepted {label}")

    prose = _synthetic_prose()
    first_data = _synthetic_data(usage_selector="CONSUMER_SEMANTIC_CAPTURE")
    second_data = _synthetic_data(usage_selector="OBSERVER_AUTHORIZATION")
    first_model, first_rows = _compile_rows(first_data, prose=prose)
    second_model, second_rows = _compile_rows(second_data, prose=prose)
    body_data = {
        "actor_profiles": {},
        "artifacts": ["same-transition-kind::BODY_RELEASE_ACCEPTED"],
        "selectors": [
            _synthetic_selector(
                "BODY_SESSION_CONTROL",
                declares_event=True,
                event_id="BODY_RELEASE_ACCEPTED",
            )
        ],
    }
    _body_model, body_rows = _compile_rows(body_data, prose=prose)
    _require_exact(
        _model_allocation_sha256(first_model),
        _model_allocation_sha256(second_model),
        "self-test consumer-independent unit identity",
    )
    _require(
        _model_origin_signal_commitment(first_model)
        != _model_origin_signal_commitment(second_model),
        "self-test consumer signal drift did not change its separate commitment",
    )
    event_row = next(row for row in first_rows if row["exact_name"] == "SAME_EVENT")
    _require_exact(
        {row["evidence_kind"] for row in event_row["origin_evidence"]},
        {"ARTIFACT_REGISTRY_ENTRY", "DECLARED_EVENT"},
        "self-test event/artifact origin aggregation",
    )
    novel_row = next(row for row in first_rows if row["exact_name"] == "NovelType")
    _require_exact(
        novel_row["suggested_adr_id"],
        "UNMAPPED_SHARED",
        "self-test unknown semantic reference route",
    )
    _require(
        "SELECTOR_USAGE_SIGNAL_PRESENT" in novel_row["ambiguity_flags"]
        and novel_row["route_basis_values"] == [],
        "self-test usage signal became route authority",
    )
    second_novel_row = next(
        row for row in second_rows if row["unit_id"] == novel_row["unit_id"]
    )
    _require_exact(
        (
            novel_row["route_rule_class"],
            novel_row["route_basis_values"],
            novel_row["suggested_adr_id"],
            novel_row["suggested_source_anchor"],
        ),
        (
            second_novel_row["route_rule_class"],
            second_novel_row["route_basis_values"],
            second_novel_row["suggested_adr_id"],
            second_novel_row["suggested_source_anchor"],
        ),
        "self-test usage-signal-independent route",
    )
    body_row = next(
        row for row in body_rows if row["exact_name"] == "BODY_RELEASE_ACCEPTED"
    )
    _require_exact(
        (
            body_row["suggested_adr_id"],
            body_row["route_rule_class"],
            body_row["route_basis_values"],
        ),
        (
            "ADR-006",
            "BODY_ACCEPTED_PROSE_RULE",
            [
                "BODY_SESSION_CONTROL",
                "accepted-prose::ADR-006::BODY_RELEASE_ACCEPTED",
            ],
        ),
        "self-test accepted-prose body event route",
    )

    proposal = _build_proposal(
        first_data,
        prose=prose,
        compiler_sources=compiler_sources,
        compact_path_label="docs/adr/synthetic-selector-source.v1.json",
        compact_raw=b"{}\n",
        schema_path_label=("docs/adr/selector-allocation.proposal.schema.v1.json"),
        schema_raw=schema_raw,
    )
    _validate_schema_instance(proposal, schema)
    _validate_proposal_semantics(
        proposal,
        data=first_data,
        prose=prose,
        compiler_sources=compiler_sources,
        compact_path_label="docs/adr/synthetic-selector-source.v1.json",
        compact_raw=b"{}\n",
        schema_path_label=("docs/adr/selector-allocation.proposal.schema.v1.json"),
        schema_raw=schema_raw,
    )
    _require_exact(
        canonical_bytes(proposal),
        canonical_bytes(
            _build_proposal(
                first_data,
                prose=prose,
                compiler_sources=compiler_sources,
                compact_path_label="docs/adr/synthetic-selector-source.v1.json",
                compact_raw=b"{}\n",
                schema_path_label=(
                    "docs/adr/selector-allocation.proposal.schema.v1.json"
                ),
                schema_raw=schema_raw,
            )
        ),
        "self-test deterministic proposal",
    )

    hostile_unknown = copy.deepcopy(proposal)
    hostile_unknown["authority"] = True
    expect_rejection(
        lambda: _validate_schema_instance(hostile_unknown, schema),
        "an unknown root property",
    )

    hostile_incomplete = copy.deepcopy(proposal)
    del hostile_incomplete["rows"][0]["unit_id"]
    expect_rejection(
        lambda: _validate_schema_instance(hostile_incomplete, schema),
        "an incomplete proposal row",
    )

    hostile_authority = copy.deepcopy(proposal)
    hostile_authority["authority_boundary"]["usage_effect"] = (
        "SIGNAL_MAY_ASSIGN_ROUTE"
    )
    expect_rejection(
        lambda: _validate_schema_instance(hostile_authority, schema),
        "an authority-boundary downgrade",
    )

    hostile_domain = copy.deepcopy(proposal)
    hostile_domain["summary"]["proposal_rows_commitment"]["domain_hex"] = (
        COMPILER_SOURCE_SET_DOMAIN.hex()
    )
    expect_rejection(
        lambda: _validate_schema_instance(hostile_domain, schema),
        "a substituted proposal commitment domain",
    )

    hostile_compiler_order = copy.deepcopy(proposal)
    hostile_compiler_order["source"]["proposal_compiler"]["sources"][0:2] = (
        reversed(
            hostile_compiler_order["source"]["proposal_compiler"]["sources"][0:2]
        )
    )
    expect_rejection(
        lambda: _validate_schema_instance(hostile_compiler_order, schema),
        "a reordered compiler source closure",
    )

    def expect_semantic_counterfeit(
        hostile: dict[str, Any],
        label: str,
    ) -> None:
        _validate_schema_instance(hostile, schema)
        expect_rejection(
            lambda: _validate_proposal_semantics(
                hostile,
                data=first_data,
                prose=prose,
                compiler_sources=compiler_sources,
                compact_path_label=("docs/adr/synthetic-selector-source.v1.json"),
                compact_raw=b"{}\n",
                schema_path_label=(
                    "docs/adr/selector-allocation.proposal.schema.v1.json"
                ),
                schema_raw=schema_raw,
            ),
            label,
        )

    hostile_unit = copy.deepcopy(proposal)
    hostile_unit["rows"][0]["unit_id"] = "2" * 64
    expect_semantic_counterfeit(hostile_unit, "a caller-selected unit ID")

    hostile_route = copy.deepcopy(proposal)
    row = hostile_route["rows"][0]
    row["route_rule_class"] = "SEMANTIC_REFERENCE_RULE"
    row["route_basis_values"] = [row["semantic_ref"]]
    row["suggested_adr_id"] = "ADR-011"
    row["suggested_source_anchor"] = ADR_ALLOCATION_ANCHOR_BY_ID["ADR-011"]
    expect_semantic_counterfeit(hostile_route, "a counterfeit route relationship")

    hostile_basis = copy.deepcopy(proposal)
    hostile_basis["rows"][0]["route_basis_values"] = ["fabricated-basis"]
    expect_semantic_counterfeit(hostile_basis, "a counterfeit route basis")

    hostile_duplicate = copy.deepcopy(proposal)
    duplicate = copy.deepcopy(hostile_duplicate["rows"][0])
    duplicate["signal_evidence"] = [
        {
            "evidence_kind": "SELECTOR_USAGE",
            "semantic_location": "selector-id::CONSUMER_SEMANTIC_CAPTURE",
        }
    ]
    hostile_duplicate["rows"].append(duplicate)
    expect_semantic_counterfeit(
        hostile_duplicate,
        "a duplicate unit with divergent signals",
    )

    hostile_summary = copy.deepcopy(proposal)
    hostile_summary["summary"]["candidate_route_counts"][0]["count"] += 1
    expect_semantic_counterfeit(hostile_summary, "a counterfeit route count")

    hostile_origin_digest = copy.deepcopy(proposal)
    hostile_origin_digest["source"]["model_projection"][
        "origin_signal_sha256"
    ] = "3" * 64
    expect_semantic_counterfeit(
        hostile_origin_digest,
        "a counterfeit origin/signal commitment",
    )

    hostile_compiler_source = copy.deepcopy(proposal)
    hostile_compiler_source["source"]["proposal_compiler"]["sources"][0][
        "sha256"
    ] = "4" * 64
    expect_semantic_counterfeit(
        hostile_compiler_source,
        "a counterfeit compiler dependency identity",
    )

    _require_exact(len(first_model), len(first_rows), "self-test row coverage")
    _require_exact(len(second_model), len(second_rows), "self-test moved row coverage")
    return killed


def _load_repository_inputs(
    source_path: Path,
) -> tuple[bytes, dict[str, Any], ProseCorpus]:
    source_raw = read_bounded_regular_file(
        source_path,
        maximum_bytes=MAX_COMPACT_BYTES - 1,
        label="proposal compact selector source",
    )
    _envelope, expanded = decode_compact_source_bytes(
        source_raw,
        label=str(source_path),
    )
    validate_expanded_source(
        expanded,
        require_complete_allocation=True,
        allow_incomplete_allocation=True,
    )
    return source_raw, expanded, _read_prose_corpus()


def _run_repository_self_test(
    source_path: Path,
) -> tuple[int, int]:
    source_raw, expanded, prose = _load_repository_inputs(source_path)
    model, rows = _compile_rows(expanded, prose=prose)
    overlap_count = sum(
        {
            "ARTIFACT_REGISTRY_ENTRY",
            "DECLARED_EVENT",
        }.issubset({origin.evidence_kind for origin in allocation.origins})
        for allocation in model
    )
    _require(
        overlap_count > 0,
        "repository self-test lost the current event/artifact origin overlap",
    )
    _require_exact(len(rows), len(model), "repository proposal unit coverage")
    _require_exact(
        _model_allocation_sha256(model),
        expanded["adr_allocation_oracle"]["model_allocation_sha256"],
        "repository proposal model digest",
    )
    _require_prose_snapshots_unchanged(prose)
    _require_exact(
        read_bounded_regular_file(
            source_path,
            maximum_bytes=MAX_COMPACT_BYTES - 1,
            label="proposal repository self-test source stability",
        ),
        source_raw,
        "proposal repository self-test source bytes",
    )
    return len(model), overlap_count


def _run_atomicity_self_test() -> int:
    """Kill bounded alias, stale-cut, and indeterminate-install mutants."""

    killed = 0

    def expect_rejection(action: Any, label: str) -> None:
        nonlocal killed
        try:
            action()
        except SelectorAllocationProposalError:
            killed += 1
        else:
            _fail(f"atomicity self-test accepted {label}")

    with tempfile.TemporaryDirectory(
        prefix=".ncp-selector-allocation-proposal-",
        dir=ROOT,
    ) as temporary:
        temporary_root = Path(temporary)
        input_path = temporary_root / "input.json"
        output_path = temporary_root / "output.json"
        alias_path = temporary_root / "output-alias.json"
        input_raw = b'{"input":1}\n'
        output_before = b'{"old":1}\n'
        output_after = b'{"new":1}\n'
        input_path.write_bytes(input_raw)
        output_path.write_bytes(output_before)
        snapshots = (
            ProposalInputSnapshot(
                label="synthetic proposal input",
                maximum_bytes=1024,
                path=input_path,
                raw=input_raw,
            ),
        )

        os.link(input_path, alias_path)
        expect_rejection(
            lambda: _require_output_distinct_from_inputs(alias_path, snapshots),
            "an existing hard-link input/output alias",
        )
        alias_path.unlink()

        def mutate_input_before_install(phase: str) -> None:
            if phase == "atomic-write:before-install":
                input_path.write_bytes(b'{"input":2}\n')

        def install_then_verify_mutated_input() -> None:
            _install_proposal_if_inputs_current(
                output_path=output_path,
                output_raw=output_after,
                snapshots=snapshots,
                phase_hook=mutate_input_before_install,
            )
            _require_final_cut_unchanged(
                output_path=output_path,
                output_raw=output_after,
                snapshots=snapshots,
                phase="mutated-install-final-stability",
            )

        expect_rejection(
            install_then_verify_mutated_input,
            "an input mutation during atomic installation",
        )
        _require_exact(
            output_path.read_bytes(),
            output_after,
            "atomicity self-test installed application identity",
        )
        input_path.write_bytes(input_raw)

        def alias_output_before_install(phase: str) -> None:
            if phase == "atomic-write:before-install":
                output_path.unlink()
                os.link(input_path, output_path)

        expect_rejection(
            lambda: _install_proposal_if_inputs_current(
                output_path=output_path,
                output_raw=output_after,
                snapshots=snapshots,
                phase_hook=alias_output_before_install,
            ),
            "an input/output alias introduced at the atomic install fence",
        )
        _require_exact(
            input_path.read_bytes(),
            input_raw,
            "atomicity self-test aliased input preservation",
        )
        output_path.unlink()
        output_path.write_bytes(output_after)

        def mutate_input_after_check(phase: str) -> None:
            if phase == "check-before-final-stability":
                input_path.write_bytes(b'{"input":3}\n')

        expect_rejection(
            lambda: _require_final_cut_unchanged(
                output_path=output_path,
                output_raw=output_after,
                snapshots=snapshots,
                phase_hook=mutate_input_after_check,
                phase="check-before-final-stability",
            ),
            "an input mutation after --check validation",
        )
        input_path.write_bytes(input_raw)

        def mutate_output_after_install(phase: str) -> None:
            if phase == "generation-before-final-stability":
                output_path.write_bytes(b'{"counterfeit":1}\n')

        expect_rejection(
            lambda: _require_final_cut_unchanged(
                output_path=output_path,
                output_raw=output_after,
                snapshots=snapshots,
                phase_hook=mutate_output_after_install,
                phase="generation-before-final-stability",
            ),
            "an output mutation after installation",
        )
        output_path.write_bytes(output_before)

        def raise_unknown_outcome(phase: str) -> None:
            if phase == "atomic-write:before-install":
                raise AtomicWriteOutcomeUnknownError("synthetic unknown outcome")

        try:
            _install_proposal_if_inputs_current(
                output_path=output_path,
                output_raw=output_after,
                snapshots=snapshots,
                phase_hook=raise_unknown_outcome,
            )
        except AtomicWriteOutcomeUnknownError:
            killed += 1
        else:
            _fail("atomicity self-test collapsed an indeterminate install outcome")

        output_path.write_bytes(output_after)
        _require_final_cut_unchanged(
            output_path=output_path,
            output_raw=output_after,
            snapshots=snapshots,
            phase="stable-cut",
        )

    return killed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "source",
        nargs="?",
        type=Path,
        default=DEFAULT_SOURCE,
        help="exact compact selector-closure source",
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=DEFAULT_SCHEMA,
        help="closed proposal JSON Schema",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="proposal output path",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="require the existing output to equal semantic recompilation",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="write canonical proposal JSON to stdout instead of a file",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run hostile synthetic tests and the current repository topology test",
    )
    return parser.parse_args()


def _execute(args: argparse.Namespace, *, _phase_hook: Any = None) -> int:
    schema_raw, schema = _load_schema(args.schema)
    if args.self_test:
        _require(
            not args.check and not args.stdout,
            "--self-test cannot be combined with --check or --stdout",
        )
        killed = _run_synthetic_self_test(schema_raw, schema)
        units, overlap_count = _run_repository_self_test(args.source)
        killed += _run_atomicity_self_test()
        print(
            "selector allocation proposal self-test: PASS "
            f"killed_mutants={killed} repository_units={units} "
            f"event_artifact_overlap_units={overlap_count}"
        )
        return 0

    _require(
        not (args.check and args.stdout),
        "--check and --stdout are mutually exclusive",
    )
    source_raw, expanded, prose = _load_repository_inputs(args.source)
    compiler_sources = _read_compiler_source_set()
    compact_path_label = _relative_repo_path(
        args.source,
        label="proposal compact selector source",
    )
    schema_path_label = _relative_repo_path(
        args.schema,
        label="proposal schema",
    )
    proposal = _build_proposal(
        expanded,
        prose=prose,
        compiler_sources=compiler_sources,
        compact_path_label=compact_path_label,
        compact_raw=source_raw,
        schema_path_label=schema_path_label,
        schema_raw=schema_raw,
    )
    validate_json_resource_bounds(
        proposal,
        label="selector allocation proposal",
        maximum_items=1_000_000,
        maximum_string_chars=8192,
        maximum_total_string_chars=MAX_PROPOSAL_BYTES,
    )
    _validate_schema_instance(proposal, schema)
    _validate_proposal_semantics(
        proposal,
        data=expanded,
        prose=prose,
        compiler_sources=compiler_sources,
        compact_path_label=compact_path_label,
        compact_raw=source_raw,
        schema_path_label=schema_path_label,
        schema_raw=schema_raw,
    )
    output_raw = canonical_bytes(proposal) + b"\n"
    _require(
        len(output_raw) <= MAX_PROPOSAL_BYTES,
        f"proposal exceeds {MAX_PROPOSAL_BYTES} bytes",
    )
    input_snapshots = _proposal_input_snapshots(
        source_path=args.source,
        source_raw=source_raw,
        schema_path=args.schema,
        schema_raw=schema_raw,
        prose=prose,
        compiler_sources=compiler_sources,
    )
    _require_input_snapshots_unchanged(input_snapshots)
    if args.stdout:
        sys.stdout.buffer.write(output_raw)
        sys.stdout.buffer.flush()
        if _phase_hook is not None:
            _phase_hook("stdout-before-final-stability")
        _require_input_snapshots_unchanged(input_snapshots)
        return 0
    output_path = _lexical_absolute_path(args.output, label="proposal output")
    _require_output_distinct_from_inputs(output_path, input_snapshots)
    if args.check:
        current = read_bounded_regular_file(
            args.output,
            maximum_bytes=MAX_PROPOSAL_BYTES,
            label="selector allocation proposal check output",
        )
        parsed = parse_json_bytes(
            current,
            label=str(args.output),
            maximum_bytes=MAX_PROPOSAL_BYTES,
        )
        _validate_schema_instance(parsed, schema)
        _validate_proposal_semantics(
            parsed,
            data=expanded,
            prose=prose,
            compiler_sources=compiler_sources,
            compact_path_label=compact_path_label,
            compact_raw=source_raw,
            schema_path_label=schema_path_label,
            schema_raw=schema_raw,
        )
        _require_exact(
            current,
            output_raw,
            "selector allocation proposal deterministic output",
        )
        _require_final_cut_unchanged(
            output_path=output_path,
            output_raw=current,
            snapshots=input_snapshots,
            phase_hook=_phase_hook,
            phase="check-before-final-stability",
        )
        print(
            "selector allocation proposal check: PASS "
            f"rows={len(proposal['rows'])} "
            "rows_sha256="
            f"{proposal['summary']['proposal_rows_commitment']['projection_sha256']}"
        )
        return 0

    _install_proposal_if_inputs_current(
        output_path=output_path,
        output_raw=output_raw,
        snapshots=input_snapshots,
        phase_hook=_phase_hook,
    )
    _require_final_cut_unchanged(
        output_path=output_path,
        output_raw=output_raw,
        snapshots=input_snapshots,
        phase_hook=_phase_hook,
        phase="generation-before-final-stability",
    )
    print(
        "selector allocation proposal generation: PASS "
        f"rows={len(proposal['rows'])} "
        f"unmapped_shared={proposal['summary']['unmapped_shared_row_count']} "
        "rows_sha256="
        f"{proposal['summary']['proposal_rows_commitment']['projection_sha256']}"
    )
    return 0


def main() -> int:
    args = parse_args()
    try:
        return _execute(args)
    except AtomicWriteOutcomeUnknownError as error:
        print(
            "selector allocation proposal: OUTCOME UNKNOWN: "
            f"{error}; the destination may contain the requested bytes. "
            "Inspect and reconcile by application identity; do not retry "
            "automatically.",
            file=sys.stderr,
        )
        return 2
    except (
        ClosureCheckError,
        KeyError,
        OSError,
        SelectorAllocationProposalError,
        SelectorClosureCodecError,
        TypeError,
    ) as error:
        print(f"selector allocation proposal: FAIL: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
