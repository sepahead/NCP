#!/usr/bin/env python3
"""Issue and validate local-only selector-allocation review receipts.

This module closes one narrow B01 bookkeeping gap.  The allocation inventory can
carry ``provenance_review.status=REVIEWED`` only after a separate review document
binds the exact semantic subject, allocation assignment, review profile, schemas,
and committed source blobs.  The review document does not select its own reviewer
policy.  The caller must supply :class:`ReviewAuthorityPolicy` from a separately
controlled local workflow.

The boundary is deliberately local-only.  It authenticates no human or
organization, proves no independent review, grants no protocol or release
authority, and cannot satisfy an external or independent evidence floor.  A caller
that needs any of those claims must use a separately authenticated verifier.
The receipt records an unauthenticated caller assertion.  Its SHA-256 commitments
provide content integrity, not identity authentication.  Do not expose its minting
API as a reviewer-authentication service.

Promotion and reopen helpers are pure compare-before-write plans.  An integrating
generator consumes the plan through its fixed-lock, durable-journal transaction.
That transaction updates the inventory binding, maintained closure commitments,
compact source, and review-generation state with exact compare-before-write
guards.  Persisting only the inventory and state, or only one of them, is an
invalid transition.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import selectors
import signal
import stat
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable, NoReturn

from selector_allocation_inventory import (
    ADR_ALLOCATION_MODULE_PATHS,
    ADR_ALLOCATION_PATHS,
    ALLOCATION_IDENTITY_COMMITMENT_SUITE,
    ALLOCATION_KINDS,
    ALLOCATION_REVIEW_PROFILE_KEYS,
    ALLOCATION_REVIEW_PROFILE_SCHEMA,
    INVENTORY_SCHEMA_ID,
    INVENTORY_SCHEMA_SHA256,
    MAX_ADR_DOCUMENT_BYTES,
    MODEL_ALLOCATION_PROJECTION_SCHEMA,
    MODEL_ORIGIN_SIGNAL_PROJECTION_SCHEMA,
    PROVENANCE_REVIEW_DOMAIN,
    PROVENANCE_REVIEW_SUITE,
    RESOURCE_CLOSURE_PROJECTION_SCHEMA,
    SEMANTIC_REVIEW_SUBJECT_KEYS,
    SEMANTIC_REVIEW_SUBJECT_SUITE,
    SEMANTIC_SHAPE_COMMITMENT_SUITE,
    SEMANTIC_SHAPE_PROJECTION_SCHEMA,
    adr_source_set_sha256,
    build_allocation_review_profile,
    build_inventory_binding,
    inventory_bytes,
    inventory_to_oracle,
    oracle_to_inventory,
    provenance_assignment_sha256,
    semantic_review_subject_commitment,
    validate_allocation_inventory,
    validate_allocation_review_profile_schema_binding,
)
from selector_closure_codec import (
    MAX_COMPACT_BYTES,
    MAX_EXPANDED_BYTES,
    SelectorClosureCodecError,
    canonical_bytes,
    decode_compact_source,
    parse_json_bytes,
    read_bounded_regular_file,
    serialize_compact_source,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REVIEW_DOCUMENT_SCHEMA = (
    ROOT / "docs" / "adr" / "selector-allocation.review.schema.v1.json"
)
DEFAULT_REVIEW_STATE = (
    ROOT / "docs" / "adr" / "selector-allocation.review-state.v1.json"
)
DEFAULT_REVIEW_STATE_SCHEMA = (
    ROOT / "docs" / "adr" / "selector-allocation.review-state.schema.v1.json"
)

REVIEW_DOCUMENT_SCHEMA_FILE = "selector-allocation.review.schema.v1.json"
REVIEW_DOCUMENT_SCHEMA_ID = "ncp.b01-selector-allocation-review.v1"
REVIEW_DOCUMENT_SCHEMA_URL = (
    "https://sepahead.github.io/ncp/schemas/b01-selector-allocation-review.v1.json"
)
REVIEW_DOCUMENT_SCHEMA_SHA256 = (
    "8013d018aa3570be6d3718306b19e2363b860797e1749b5ae3028983bff25d52"
)
REVIEW_STATE_FILE = "selector-allocation.review-state.v1.json"
REVIEW_STATE_SCHEMA_FILE = "selector-allocation.review-state.schema.v1.json"
REVIEW_STATE_SCHEMA_URL = (
    "https://sepahead.github.io/ncp/schemas/"
    "b01-selector-allocation-review-state.v1.json"
)
REVIEW_STATE_SCHEMA_SHA256 = (
    "6c2af2cce1765144c2259f3b1825596934f38a8c4bc5c2d14c65f11a5ef46df3"
)
AUTHORING_SCHEMA_URL = (
    "https://sepahead.github.io/ncp/schemas/b01-selector-closure-authoring.v1.json"
)
COMPACT_SCHEMA_URL = (
    "https://sepahead.github.io/ncp/schemas/b01-selector-closure-source.compact.v1.json"
)
AUTHORIZATION_MANIFEST_SCHEMA = (
    "ncp.b01-selector-allocation-review-authorization-manifest.v1"
)
REVIEW_RECEIPT_SCHEMA = "ncp.b01-selector-allocation-review-receipt.v1"
REVIEW_STATE_SCHEMA = "ncp.b01-selector-allocation-review-generation-state.v1"
REVIEW_SUBJECT_SCHEMA = "ncp.b01-selector-allocation-review-subject.v1"
REVIEW_TAXONOMY_SCHEMA = "ncp.b01-selector-allocation-taxonomy.v1"
REVIEW_MODEL_PROJECTION_SCHEMA = (
    "ncp.b01-selector-allocation-reviewed-model-projection.v4"
)

AUTHORITY_CLASS = "LOCAL_ONLY"
CLAIM_BOUNDARY = (
    "LOCAL_ONLY_EXACT_SELECTOR_ALLOCATION_PROVENANCE_REVIEW_AUTHORIZATION_"
    "NO_EXTERNAL_INDEPENDENT_PROTOCOL_RELEASE_OR_CERTIFICATION_AUTHORITY"
)
IDENTITY_ASSURANCE = (
    "CALLER_SUPPLIED_LOCAL_POLICY_ONLY_NO_SIGNATURE_OR_EXTERNAL_IDENTITY_PROOF"
)
REVIEWER_ROLE = "SELECTOR_ALLOCATION_PROVENANCE_REVIEWER"
REVIEW_SCOPE = (
    "EXACT_SEMANTIC_SUBJECT_ASSIGNMENT_TAXONOMY_PROJECTIONS_SCHEMAS_AND_SOURCE_CUT"
)
REVIEWER_SEPARATION_RULE = (
    "REVIEWER_IDENTIFIER_DIFFERS_FROM_ISSUER_AND_ALL_IMPLEMENTATION_OWNER_IDENTIFIERS"
)
REVIEW_DISPOSITION = "AUTHORIZE_EXACT_REVIEWED_PROMOTION"
REVIEWER_ATTESTATION = (
    "CALLER_ASSERTS_EXACT_BOUND_SUBJECT_REVIEW_FOR_LOCAL_PROVENANCE_ONLY_"
    "NO_IDENTITY_PROOF"
)
PROHIBITED_AUTHORITY_CLAIMS = (
    "EXTERNAL_AUTHORITY",
    "INDEPENDENT_AUTHORITY",
    "PROTOCOL_OR_RELEASE_AUTHORITY",
    "CERTIFICATION_OR_PUBLICATION_AUTHORITY",
)
WORKTREE_REQUIREMENT = "HEAD_EQUALS_COMMIT_AND_ENTIRE_WORKTREE_CLEAN"

CANONICALIZATION = "NCP_PRINTABLE_ASCII_SAFE_INTEGER_JSON_V1"
FRAMING = "DOMAIN_BYTES_THEN_UINT64_BE_CANONICAL_BYTE_LENGTH_THEN_CANONICAL_BYTES"
SCALAR_DOMAIN = (
    "NULL_BOOLEAN_SIGNED_INTEGER_ABS_LE_9007199254740991_PRINTABLE_ASCII_STRING_ONLY"
)
ASSIGNMENT_SCALAR_DOMAIN = SCALAR_DOMAIN

AUTHORIZATION_MANIFEST_DOMAIN = (
    b"ncp.b01.selector-allocation.review-authorization-manifest.v1\x00"
)
REVIEW_RECEIPT_DOMAIN = b"ncp.b01.selector-allocation.review-receipt.v1\x00"
REVIEW_STATE_DOMAIN = b"ncp.b01.selector-allocation.review-generation-state.v1\x00"
REVIEW_TRANSITION_DOMAIN = b"ncp.b01.selector-allocation.review-transition.v1\x00"

MAX_REVIEW_DOCUMENT_BYTES = 512 * 1024
MAX_REVIEW_SCHEMA_BYTES = 512 * 1024
MAX_REVIEW_STATE_BYTES = 16 * 1024
MAX_REVIEW_STATE_SCHEMA_BYTES = 64 * 1024
MAX_GIT_COMMAND_OUTPUT_BYTES = 20 * 1024 * 1024
MAX_GIT_ERROR_BYTES = 64 * 1024
MAX_GIT_COMMAND_INPUT_BYTES = 64 * 1024
GIT_COMMAND_TIMEOUT_SECONDS = 20.0
MAX_SCHEMA_ERRORS = 64
MAX_SAFE_INTEGER = 9_007_199_254_740_991
MAX_REVIEW_REASON_CHARS = 512

SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")
SHA1_OBJECT_ID = re.compile(r"^[0-9a-f]{40}$")
SHA256_OBJECT_ID = re.compile(r"^[0-9a-f]{64}$")
IDENTITY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._@+-]{2,127}$")
SAFE_BRANCH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,127}$")
SAFE_REPOSITORY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{2,127}$")
UUID_V4 = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)

# These are the exact committed inputs to one allocation review.  A caller
# cannot add, remove, rename, or redirect a role.  The expanded semantic payload
# is deterministically decoded from ``semantic_compact_source``.
REQUIRED_SOURCE_ROLES: tuple[tuple[str, str, int], ...] = (
    (
        "allocation_inventory",
        "docs/adr/selector-allocation.authoring.v1.json",
        4 * 1024 * 1024,
    ),
    (
        "allocation_schema",
        "docs/adr/selector-allocation.authoring.schema.v1.json",
        64 * 1024,
    ),
    (
        "semantic_authoring_source",
        "docs/adr/selector-closure.authoring.v1.json",
        16 * 1024 * 1024,
    ),
    (
        "semantic_authoring_schema",
        "docs/adr/selector-closure.authoring.schema.v1.json",
        1024 * 1024,
    ),
    (
        "semantic_compact_source",
        "docs/adr/selector-closure.source.v1.json",
        MAX_COMPACT_BYTES,
    ),
    (
        "semantic_compact_schema",
        "docs/adr/selector-closure.source.schema.v1.json",
        1024 * 1024,
    ),
    (
        "allocation_boundary_implementation",
        "scripts/selector_allocation_inventory.py",
        2 * 1024 * 1024,
    ),
    (
        "semantic_generator",
        "scripts/generate_selector_closure_source.py",
        4 * 1024 * 1024,
    ),
    (
        "semantic_checker",
        "scripts/check_selector_closure.py",
        8 * 1024 * 1024,
    ),
    (
        "semantic_codec",
        "scripts/selector_closure_codec.py",
        2 * 1024 * 1024,
    ),
    (
        "resource_closure_projection",
        "scripts/selector_resource_closure.py",
        2 * 1024 * 1024,
    ),
    (
        "review_boundary_implementation",
        "scripts/selector_allocation_review.py",
        2 * 1024 * 1024,
    ),
    (
        "review_generation_state",
        "docs/adr/selector-allocation.review-state.v1.json",
        MAX_REVIEW_STATE_BYTES,
    ),
    (
        "review_generation_state_schema",
        "docs/adr/selector-allocation.review-state.schema.v1.json",
        MAX_REVIEW_STATE_SCHEMA_BYTES,
    ),
    (
        "review_document_schema",
        "docs/adr/selector-allocation.review.schema.v1.json",
        MAX_REVIEW_SCHEMA_BYTES,
    ),
    *(
        (
            f"adr_{index:03d}_source",
            path,
            MAX_ADR_DOCUMENT_BYTES,
        )
        for index, path in enumerate(ADR_ALLOCATION_PATHS, 1)
    ),
    *(
        (
            f"adr_{adr_index:03d}_module_{module_index:03d}",
            path,
            MAX_ADR_DOCUMENT_BYTES,
        )
        for adr_index, module_paths in enumerate(
            ADR_ALLOCATION_MODULE_PATHS,
            1,
        )
        for module_index, path in enumerate(module_paths, 1)
    ),
)
REQUIRED_SOURCE_ROLE_PATHS = {
    role: path for role, path, _maximum_bytes in REQUIRED_SOURCE_ROLES
}
REQUIRED_SOURCE_ROLE_LIMITS = {
    role: maximum_bytes for role, _path, maximum_bytes in REQUIRED_SOURCE_ROLES
}
TRANSITION_MUTABLE_SOURCE_ROLES = frozenset(
    {
        "allocation_inventory",
        "semantic_authoring_source",
        "semantic_compact_source",
        "review_generation_state",
    }
)

COMMITMENT_KEYS = {
    "algorithm",
    "byte_length",
    "canonicalization",
    "domain_hex",
    "framing",
    "scalar_domain",
    "sha256",
}
REVIEW_STATE_KEYS = {
    "active_assignment_sha256",
    "active_inventory_sha256",
    "authority_class",
    "current_receipt_sha256",
    "last_consumed_receipt_sha256",
    "next_review_generation",
    "prior_state_sha256",
    "schema",
    "state_version",
}
BLOB_KEYS = {"byte_length", "git_blob", "mode", "path", "role", "sha256"}
SOURCE_CUT_KEYS = {
    "blobs",
    "branch",
    "commit",
    "object_format",
    "repository",
    "tree",
    "worktree_requirement",
}
REVIEWER_AUTHORIZATION_KEYS = {
    "authorization_issuer_identity",
    "implementation_owner_identities",
    "reviewer_identity",
    "reviewer_role",
    "scope",
    "separation_rule",
}
ALLOCATION_SCHEMA_BINDING_KEYS = {"byte_length", "schema_id", "sha256"}
ASSIGNMENT_SUITE_KEYS = set(PROVENANCE_REVIEW_SUITE) | {"scalar_domain"}
TAXONOMY_KEYS = {"required_kinds", "schema"}
MODEL_PROJECTION_KEYS = {
    "model_allocation_count",
    "model_allocation_sha256",
    "model_origin_signal_projection_schema",
    "model_origin_signal_row_count",
    "model_origin_signal_sha256",
    "model_projection_schema",
    "resource_closure_row_count",
    "resource_closure_schema",
    "resource_closure_sha256",
    "schema",
    "semantic_shape_entry_count",
    "semantic_shape_projection_schema",
    "semantic_shape_sha256",
}
REVIEW_SUBJECT_KEYS = {
    "allocation_review_profile",
    "allocation_schema_binding",
    "assignment_commitment_suite",
    "model_projection",
    "provenance_assignment_sha256",
    "semantic_review_subject",
    "taxonomy",
}
AUTHORIZATION_MANIFEST_KEYS = {
    "authority_class",
    "authorization_id",
    "claim_boundary",
    "expected_review_state",
    "expected_review_state_commitment",
    "identity_assurance",
    "review_generation",
    "review_subject",
    "reviewer_authorization",
    "schema",
    "source_cut",
}
REVIEW_RECEIPT_KEYS = {
    "authority_class",
    "authorization_id",
    "authorization_manifest_byte_length",
    "authorization_manifest_sha256",
    "claim_boundary",
    "disposition",
    "expected_review_state_sha256",
    "prohibited_authority_claims",
    "review_generation",
    "review_id",
    "reviewed_assignment_sha256",
    "reviewer_attestation",
    "reviewer_identity",
    "reviewer_role",
    "schema",
    "semantic_review_subject_sha256",
}
REVIEW_DOCUMENT_KEYS = {
    "$schema",
    "authority_class",
    "authorization_manifest",
    "authorization_manifest_commitment",
    "claim_boundary",
    "external_authority",
    "independent_authority",
    "release_authority",
    "review_receipt",
    "review_receipt_commitment",
    "schema",
}


class SelectorAllocationReviewError(ValueError):
    """The local-only review document or transition is invalid."""


def _fail(message: str) -> NoReturn:
    raise SelectorAllocationReviewError(message)


def _require(condition: bool, message: str) -> None:
    if not condition:
        _fail(message)


def _closed_object(value: Any, *, keys: set[str], label: str) -> dict[str, Any]:
    _require(isinstance(value, dict), f"{label} must be an object")
    actual = set(value)
    _require(
        actual == keys,
        f"{label} fields differ: missing={sorted(keys - actual)!r} "
        f"extra={sorted(actual - keys)!r}",
    )
    return value


def _require_sha256(value: Any, *, label: str) -> str:
    _require(
        isinstance(value, str) and SHA256_HEX.fullmatch(value) is not None,
        f"{label} must be lowercase 64-hex SHA-256",
    )
    return value


def _require_positive_safe_integer(value: Any, *, label: str) -> int:
    _require(
        type(value) is int and 0 < value <= MAX_SAFE_INTEGER,
        f"{label} must be a positive JSON-safe integer",
    )
    return value


def _require_nonnegative_safe_integer(value: Any, *, label: str) -> int:
    _require(
        type(value) is int and 0 <= value <= MAX_SAFE_INTEGER,
        f"{label} must be a nonnegative JSON-safe integer",
    )
    return value


def _require_identity(value: Any, *, label: str) -> str:
    _require(
        isinstance(value, str) and IDENTITY.fullmatch(value) is not None,
        (
            f"{label} must be 3-128 printable ASCII identity characters "
            "without whitespace or path separators"
        ),
    )
    return value


def _require_uuid_v4(value: Any, *, label: str) -> str:
    _require(
        isinstance(value, str) and UUID_V4.fullmatch(value) is not None,
        f"{label} must be a canonical lowercase UUIDv4",
    )
    try:
        parsed = uuid.UUID(value)
    except ValueError as error:
        _fail(f"{label} is not a UUID: {error}")
    _require(
        parsed.version == 4 and parsed.variant == uuid.RFC_4122,
        f"{label} must use RFC 4122 UUIDv4 bits",
    )
    return value


def _canonical_review_bytes(value: Any) -> bytes:
    """Encode the explicit portable subset used by every review commitment."""

    def encode_string(item: str, *, label: str) -> bytes:
        _require(
            all(0x20 <= ord(character) <= 0x7E for character in item),
            f"{label} must contain printable ASCII characters only",
        )
        escaped = item.replace("\\", "\\\\").replace('"', '\\"')
        return b'"' + escaped.encode("ascii") + b'"'

    def encode(item: Any, *, path: str, depth: int) -> bytes:
        _require(depth <= 64, "review JSON exceeds 64 levels")
        item_type = type(item)
        if item_type is dict:
            _require(
                all(type(key) is str for key in item),
                f"{path}: object key is not a string",
            )
            try:
                ordered_keys = sorted(
                    item,
                    key=lambda candidate: candidate.encode("ascii"),
                )
            except UnicodeEncodeError as error:
                _fail(f"{path}: object key is not ASCII: {error}")
            members = [
                encode_string(key, label=f"{path} object key")
                + b":"
                + encode(item[key], path=f"{path}/{key}", depth=depth + 1)
                for key in ordered_keys
            ]
            return b"{" + b",".join(members) + b"}"
        if item_type is list:
            return (
                b"["
                + b",".join(
                    encode(child, path=f"{path}/{index}", depth=depth + 1)
                    for index, child in enumerate(item)
                )
                + b"]"
            )
        if item_type is str:
            return encode_string(item, label=path)
        if item_type is bool:
            return b"true" if item else b"false"
        if item is None:
            return b"null"
        if item_type is int:
            _require(
                abs(item) <= MAX_SAFE_INTEGER,
                f"{path}: integer is outside the JSON-safe range",
            )
            return str(item).encode("ascii")
        _fail(f"{path}: scalar type {item_type.__name__!r} is outside the codec")

    try:
        return encode(value, path="$", depth=0)
    except RecursionError:
        _fail("review JSON exceeds the supported recursion bound")


def review_document_bytes(document: dict[str, Any]) -> bytes:
    """Return canonical review-document bytes with exactly one trailing LF."""

    raw = _canonical_review_bytes(document) + b"\n"
    _require(
        len(raw) <= MAX_REVIEW_DOCUMENT_BYTES,
        f"review document exceeds {MAX_REVIEW_DOCUMENT_BYTES} bytes",
    )
    return raw


def _content_commitment(content: Any, *, domain: bytes) -> dict[str, Any]:
    raw = _canonical_review_bytes(content)
    digest = sha256()
    digest.update(domain)
    digest.update(len(raw).to_bytes(8, "big"))
    digest.update(raw)
    return {
        "algorithm": "SHA256",
        "byte_length": len(raw),
        "canonicalization": CANONICALIZATION,
        "domain_hex": domain.hex(),
        "framing": FRAMING,
        "scalar_domain": SCALAR_DOMAIN,
        "sha256": digest.hexdigest(),
    }


def _validate_content_commitment(
    commitment: Any,
    content: Any,
    *,
    domain: bytes,
    label: str,
) -> dict[str, Any]:
    commitment = _closed_object(commitment, keys=COMMITMENT_KEYS, label=label)
    expected = _content_commitment(content, domain=domain)
    _require(commitment == expected, f"{label} does not bind the exact content")
    return commitment


@dataclass(frozen=True)
class ReviewAuthorityPolicy:
    """Caller-supplied local policy; its protection is outside this module."""

    repository: str
    branch: str
    authorization_issuer_identity: str
    reviewer_identity: str
    reviewer_role: str
    implementation_owner_identities: tuple[str, ...]

    def validate(self) -> None:
        _validate_repository_text(self.repository)
        _validate_branch_text(self.branch)
        issuer = _require_identity(
            self.authorization_issuer_identity,
            label="review policy authorization issuer",
        )
        reviewer = _require_identity(
            self.reviewer_identity,
            label="review policy reviewer",
        )
        _require(
            self.reviewer_role == REVIEWER_ROLE,
            f"review policy role must be exactly {REVIEWER_ROLE}",
        )
        owners = self.implementation_owner_identities
        _require(
            isinstance(owners, tuple) and 0 < len(owners) <= 64,
            "review policy implementation owners must be a nonempty bounded tuple",
        )
        for index, owner in enumerate(owners):
            _require_identity(owner, label=f"review policy owner {index}")
        _require(
            tuple(sorted(set(owners))) == owners,
            "review policy implementation owners must be sorted and unique",
        )
        _require(
            issuer in owners,
            "review policy issuer must be one of the implementation owners",
        )
        _require(
            reviewer != issuer and reviewer not in owners,
            "review policy reviewer must be separate from issuer and owners",
        )

    def projection(self) -> dict[str, Any]:
        self.validate()
        return {
            "authorization_issuer_identity": self.authorization_issuer_identity,
            "implementation_owner_identities": list(
                self.implementation_owner_identities
            ),
            "reviewer_identity": self.reviewer_identity,
            "reviewer_role": self.reviewer_role,
            "scope": REVIEW_SCOPE,
            "separation_rule": REVIEWER_SEPARATION_RULE,
        }


@dataclass(frozen=True)
class ReviewGenerationState:
    """Small content-addressed state that makes review receipts one-use."""

    state_version: int
    next_review_generation: int
    active_assignment_sha256: str | None
    active_inventory_sha256: str | None
    current_receipt_sha256: str | None
    last_consumed_receipt_sha256: str | None
    prior_state_sha256: str | None

    @classmethod
    def genesis(cls) -> "ReviewGenerationState":
        return cls(
            state_version=0,
            next_review_generation=1,
            active_assignment_sha256=None,
            active_inventory_sha256=None,
            current_receipt_sha256=None,
            last_consumed_receipt_sha256=None,
            prior_state_sha256=None,
        )

    def validate(self) -> None:
        _require_nonnegative_safe_integer(
            self.state_version,
            label="review state version",
        )
        _require_positive_safe_integer(
            self.next_review_generation,
            label="review state next generation",
        )
        for value, label in (
            (
                self.active_assignment_sha256,
                "review state active assignment",
            ),
            (
                self.active_inventory_sha256,
                "review state active inventory",
            ),
            (self.current_receipt_sha256, "review state current receipt"),
            (
                self.last_consumed_receipt_sha256,
                "review state last consumed receipt",
            ),
            (self.prior_state_sha256, "review state prior state"),
        ):
            if value is not None:
                _require_sha256(value, label=label)
        if self.state_version == 0:
            _require(
                self == ReviewGenerationState.genesis(),
                "review state version zero must be the exact genesis state",
            )
        elif self.current_receipt_sha256 is None:
            _require(
                self.active_assignment_sha256 is None
                and self.active_inventory_sha256 is None
                and self.last_consumed_receipt_sha256 is not None
                and self.prior_state_sha256 is not None
                and self.state_version == 2 * (self.next_review_generation - 1),
                (
                    "non-genesis open review state has an impossible "
                    "version, generation, or receipt history"
                ),
            )
        else:
            _require(
                self.active_assignment_sha256 is not None
                and self.active_inventory_sha256 is not None
                and self.last_consumed_receipt_sha256 == self.current_receipt_sha256
                and self.prior_state_sha256 is not None
                and self.state_version == 2 * self.next_review_generation - 1,
                (
                    "active review state has an impossible version, "
                    "generation, or receipt history"
                ),
            )
        _require(
            self.current_receipt_sha256 is None
            or self.current_receipt_sha256 == self.last_consumed_receipt_sha256,
            "current review receipt must equal the last consumed receipt",
        )

    def projection(self) -> dict[str, Any]:
        self.validate()
        return {
            "active_assignment_sha256": self.active_assignment_sha256,
            "active_inventory_sha256": self.active_inventory_sha256,
            "authority_class": AUTHORITY_CLASS,
            "current_receipt_sha256": self.current_receipt_sha256,
            "last_consumed_receipt_sha256": self.last_consumed_receipt_sha256,
            "next_review_generation": self.next_review_generation,
            "prior_state_sha256": self.prior_state_sha256,
            "schema": REVIEW_STATE_SCHEMA,
            "state_version": self.state_version,
        }

    def commitment(self) -> dict[str, Any]:
        return _content_commitment(self.projection(), domain=REVIEW_STATE_DOMAIN)


def review_state_bytes(state: ReviewGenerationState) -> bytes:
    """Serialize one exact local-only review-generation state."""

    raw = _canonical_review_bytes(state.projection()) + b"\n"
    _require(
        len(raw) <= MAX_REVIEW_STATE_BYTES,
        f"review generation state exceeds {MAX_REVIEW_STATE_BYTES} bytes",
    )
    return raw


def _first_bounded_schema_error(
    validator: Any,
    value: Any,
) -> tuple[Any | None, bool, int]:
    """Return one deterministic error from a bounded validation window."""

    errors: list[Any] = []
    truncated = False
    for error in validator.iter_errors(value):
        if len(errors) == MAX_SCHEMA_ERRORS:
            truncated = True
            break
        errors.append(error)
    if not errors:
        return None, truncated, 0
    first = min(
        errors,
        key=lambda error: (
            tuple(str(part) for part in error.absolute_path),
            error.validator or "",
            tuple(str(part) for part in error.absolute_schema_path),
        ),
    )
    return first, truncated, len(errors)


def _validate_review_state_schema_bytes(raw: bytes) -> dict[str, Any]:
    """Meta-validate the exact closed state-file schema."""

    try:
        from jsonschema import Draft202012Validator
        from jsonschema.exceptions import SchemaError
    except ImportError as error:
        _fail(f"JSON Schema validation dependency is unavailable: {error}")
    _require(
        sha256(raw).hexdigest() == REVIEW_STATE_SCHEMA_SHA256,
        "review-state schema reviewed byte identity changed",
    )
    schema = parse_json_bytes(
        raw,
        label="selector allocation review-state schema",
        maximum_bytes=MAX_REVIEW_STATE_SCHEMA_BYTES,
    )
    _require(isinstance(schema, dict), "review-state schema must be an object")
    _require(
        schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema"
        and schema.get("$id") == REVIEW_STATE_SCHEMA_URL,
        "review-state schema has an unexpected identity",
    )
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as error:
        _fail(f"review-state schema is invalid: {error.message}")
    return schema


def load_review_generation_state(
    state_path: Path = DEFAULT_REVIEW_STATE,
    schema_path: Path = DEFAULT_REVIEW_STATE_SCHEMA,
) -> ReviewGenerationState:
    """Load a bounded canonical state file and enforce its semantic invariants."""

    schema_raw = read_bounded_regular_file(
        schema_path,
        maximum_bytes=MAX_REVIEW_STATE_SCHEMA_BYTES,
        label="selector allocation review-state schema",
    )
    schema = _validate_review_state_schema_bytes(schema_raw)
    raw = read_bounded_regular_file(
        state_path,
        maximum_bytes=MAX_REVIEW_STATE_BYTES,
        label="selector allocation review-generation state",
    )
    value = parse_json_bytes(
        raw,
        label=str(state_path),
        maximum_bytes=MAX_REVIEW_STATE_BYTES,
    )
    _require(isinstance(value, dict), "review-generation state must be an object")
    _require(
        raw == _canonical_review_bytes(value) + b"\n",
        "review-generation state is not canonical with exactly one trailing LF",
    )
    try:
        from jsonschema import Draft202012Validator
    except ImportError as error:
        _fail(f"JSON Schema validation dependency is unavailable: {error}")
    error, truncated, error_count = _first_bounded_schema_error(
        Draft202012Validator(schema), value
    )
    if error is not None:
        count_text = (
            f">={MAX_SCHEMA_ERRORS + 1}" if truncated else str(error_count)
        )
        _fail(
            "review-generation state fails its schema: "
            f"{error.message}; errors={count_text}"
        )
    state = _validate_review_state_projection(
        value,
        label="persisted review-generation state",
    )
    _require(
        raw == review_state_bytes(state),
        "review-generation state differs from its exact semantic projection",
    )
    return state


@dataclass(frozen=True)
class GitSourceSnapshot:
    """An immutable local Git cut and exact required regular blobs."""

    source_cut: dict[str, Any]
    blob_bytes_by_role: dict[str, bytes]


@dataclass(frozen=True)
class ReviewValidation:
    """Validated review inputs used to construct a promotion plan."""

    inventory: dict[str, Any]
    inventory_schema: dict[str, Any]
    inventory_schema_raw: bytes
    expanded_semantic_source: dict[str, Any]
    assignment_sha256: str
    receipt_sha256: str
    review_state: ReviewGenerationState
    source_snapshot: GitSourceSnapshot


@dataclass(frozen=True)
class ReviewTransitionPlan:
    """Pure compare-and-swap inputs and outputs for an atomic integration."""

    action: str
    expected_inventory_bytes: bytes
    next_inventory_bytes: bytes
    expected_inventory_sha256: str
    next_inventory_sha256: str
    expected_review_state: ReviewGenerationState
    next_review_state: ReviewGenerationState
    expected_review_state_sha256: str
    next_review_state_sha256: str
    reviewed_assignment_sha256: str
    review_receipt_sha256: str
    source_cut: dict[str, Any]
    transition_subject_sha256: str


def _validate_branch_text(branch: Any) -> str:
    _require(
        isinstance(branch, str)
        and SAFE_BRANCH.fullmatch(branch) is not None
        and ".." not in branch
        and "@{" not in branch
        and "//" not in branch
        and not branch.endswith(("/", ".", ".lock"))
        and "/./" not in branch,
        "branch is not a safe canonical branch name",
    )
    return branch


def _validate_repository_text(repository: Any) -> str:
    _require(
        isinstance(repository, str)
        and SAFE_REPOSITORY.fullmatch(repository) is not None
        and ".." not in repository
        and "//" not in repository
        and "/./" not in repository
        and not repository.startswith("/")
        and not repository.endswith(("/", "/.")),
        "repository is not a safe canonical identifier",
    )
    return repository


def _clean_git_environment() -> dict[str, str]:
    environment = {
        key: value for key, value in os.environ.items() if not key.startswith("GIT_")
    }
    environment.update(
        {
            "GCM_INTERACTIVE": "never",
            "GIT_NO_LAZY_FETCH": "1",
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_PAGER": "",
            "GIT_TERMINAL_PROMPT": "0",
            "LC_ALL": "C",
        }
    )
    return environment


def _run_git(
    repo_root: Path,
    *arguments: str,
    maximum_output_bytes: int = MAX_GIT_COMMAND_OUTPUT_BYTES,
    standard_input: bytes | None = None,
    _timeout_seconds: float = GIT_COMMAND_TIMEOUT_SECONDS,
) -> bytes:
    """Run Git without a shell and bound captured output before allocation."""

    _require(
        type(maximum_output_bytes) is int
        and 0 <= maximum_output_bytes <= MAX_GIT_COMMAND_OUTPUT_BYTES,
        "Git command output bound is invalid",
    )
    _require(
        standard_input is None
        or (
            type(standard_input) is bytes
            and len(standard_input) <= MAX_GIT_COMMAND_INPUT_BYTES
        ),
        f"Git command input exceeds {MAX_GIT_COMMAND_INPUT_BYTES} bytes",
    )
    _require(
        type(_timeout_seconds) in {int, float}
        and 0 < _timeout_seconds <= GIT_COMMAND_TIMEOUT_SECONDS,
        "Git command timeout is invalid",
    )
    command = [
        "git",
        "--no-pager",
        "--no-replace-objects",
        "-c",
        "core.quotePath=false",
        "-c",
        "core.fsmonitor=false",
        "-c",
        "core.hooksPath=/dev/null",
        "-c",
        "submodule.recurse=false",
        *arguments,
    ]
    process: subprocess.Popen[bytes] | None = None
    completed_normally = False
    stdout = bytearray()
    stderr = bytearray()
    deadline = time.monotonic() + _timeout_seconds

    def stop_process_group() -> None:
        if process is None:
            return
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except OSError:
            # The child can exit between poll() and killpg().  Some platforms
            # report that race as EPERM rather than ESRCH.  A direct kill is a
            # bounded fallback; ProcessLookupError means the child is gone.
            try:
                process.kill()
            except ProcessLookupError:
                pass

    try:
        process = subprocess.Popen(
            command,
            cwd=repo_root,
            env=_clean_git_environment(),
            stdin=(subprocess.PIPE if standard_input is not None else subprocess.DEVNULL),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        _require(
            process.stdout is not None and process.stderr is not None,
            "Git command pipes are unavailable",
        )
        input_offset = 0
        with selectors.DefaultSelector() as selector:
            for stream, stream_name in (
                (process.stdout, "stdout"),
                (process.stderr, "stderr"),
            ):
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, selectors.EVENT_READ, ("read", stream_name))
            if process.stdin is not None:
                if standard_input:
                    os.set_blocking(process.stdin.fileno(), False)
                    selector.register(process.stdin, selectors.EVENT_WRITE, ("write", "stdin"))
                else:
                    process.stdin.close()

            def close_stream(stream: Any) -> None:
                try:
                    selector.unregister(stream)
                except KeyError:
                    pass
                stream.close()

            while selector.get_map():
                remaining_seconds = deadline - time.monotonic()
                if remaining_seconds <= 0:
                    _fail(f"Git command timed out: {arguments!r}")
                events = selector.select(remaining_seconds)
                if not events:
                    _fail(f"Git command timed out: {arguments!r}")
                for key, _mask in events:
                    operation, stream_name = key.data
                    stream = key.fileobj
                    if operation == "write":
                        _require(
                            standard_input is not None,
                            "Git stdin selector has no input",
                        )
                        try:
                            written = os.write(
                                stream.fileno(),
                                standard_input[input_offset : input_offset + 64 * 1024],
                            )
                        except BrokenPipeError:
                            close_stream(stream)
                            continue
                        if written == 0:
                            _fail("Git command stdin made no progress")
                        input_offset += written
                        if input_offset == len(standard_input):
                            close_stream(stream)
                        continue

                    target = stdout if stream_name == "stdout" else stderr
                    limit = (
                        maximum_output_bytes
                        if stream_name == "stdout"
                        else MAX_GIT_ERROR_BYTES
                    )
                    try:
                        chunk = os.read(
                            stream.fileno(),
                            min(64 * 1024, limit + 1 - len(target)),
                        )
                    except BlockingIOError:
                        continue
                    if not chunk:
                        close_stream(stream)
                        continue
                    target.extend(chunk)
                    _require(
                        len(target) <= limit,
                        f"Git {'command' if stream_name == 'stdout' else 'error'} "
                        f"output exceeds {limit} bytes",
                    )

        remaining_seconds = deadline - time.monotonic()
        if remaining_seconds <= 0:
            _fail(f"Git command timed out: {arguments!r}")
        returncode = process.wait(timeout=remaining_seconds)
        completed_normally = returncode == 0
    except (OSError, subprocess.SubprocessError) as error:
        _fail(f"Git command failed to execute: {arguments!r}: {error}")
    finally:
        if not completed_normally:
            stop_process_group()
        if process is not None:
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None and not stream.closed:
                    stream.close()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                _fail(f"Git command could not be reaped: {arguments!r}")
    if returncode != 0:
        diagnostic = (
            stderr.decode("utf-8", errors="replace")
            .strip()
            .encode("unicode_escape")
            .decode("ascii")
        )
        _fail(
            f"Git command failed exit={returncode} "
            f"arguments={arguments!r}: {diagnostic}"
        )
    return bytes(stdout)


def _validate_repository_root(repo_root: Path) -> Path:
    try:
        resolved = repo_root.resolve(strict=True)
        mode = resolved.lstat().st_mode
    except OSError as error:
        _fail(f"cannot resolve repository root {repo_root}: {error}")
    _require(
        stat.S_ISDIR(mode) and not stat.S_ISLNK(mode),
        "repository root must be a non-symlink directory",
    )
    top = (
        _run_git(
            resolved,
            "rev-parse",
            "--show-toplevel",
            maximum_output_bytes=4096,
        )
        .decode("utf-8")
        .strip()
    )
    try:
        actual = Path(top).resolve(strict=True)
    except OSError as error:
        _fail(f"Git reported an invalid repository root: {error}")
    _require(actual == resolved, "provided path is not the exact Git worktree root")
    return resolved


def _object_id_pattern(object_format: str) -> re.Pattern[str]:
    if object_format == "sha1":
        return SHA1_OBJECT_ID
    if object_format == "sha256":
        return SHA256_OBJECT_ID
    _fail(f"unsupported Git object format {object_format!r}")


def _require_object_id(
    value: Any,
    *,
    object_format: str,
    label: str,
) -> str:
    pattern = _object_id_pattern(object_format)
    _require(
        isinstance(value, str) and pattern.fullmatch(value) is not None,
        f"{label} must be a full lowercase {object_format} object ID",
    )
    return value


def _parse_ls_tree_entry(
    raw: bytes,
    *,
    expected_path: str,
    object_format: str,
) -> tuple[str, str]:
    _require(
        raw.endswith(b"\x00") and raw.count(b"\x00") == 1,
        f"Git tree lookup for {expected_path} must return exactly one entry",
    )
    entry = raw[:-1]
    try:
        metadata, path_raw = entry.split(b"\t", 1)
        mode_raw, type_raw, object_raw = metadata.split(b" ", 2)
        path = path_raw.decode("ascii")
        mode = mode_raw.decode("ascii")
        object_type = type_raw.decode("ascii")
        object_id = object_raw.decode("ascii")
    except (UnicodeDecodeError, ValueError) as error:
        _fail(f"malformed Git tree entry for {expected_path}: {error}")
    _require(
        path == expected_path,
        f"Git tree returned a substituted path for {expected_path}",
    )
    _require(
        mode in {"100644", "100755"} and object_type == "blob",
        f"review source {expected_path} must be a regular Git blob",
    )
    _require_object_id(
        object_id,
        object_format=object_format,
        label=f"Git blob for {expected_path}",
    )
    return mode, object_id


def _read_git_blob(
    repo_root: Path,
    object_id: str,
    *,
    maximum_bytes: int,
    object_format: str,
    label: str,
) -> bytes:
    _require_object_id(object_id, object_format=object_format, label=label)
    size_text = (
        _run_git(
            repo_root,
            "cat-file",
            "-s",
            object_id,
            maximum_output_bytes=64,
        )
        .decode("ascii")
        .strip()
    )
    _require(
        size_text.isascii() and size_text.isdecimal(),
        f"{label} has a malformed Git object size",
    )
    object_size = int(size_text)
    _require(
        0 < object_size <= maximum_bytes,
        f"{label} is outside its {maximum_bytes}-byte bound",
    )
    raw = _run_git(
        repo_root,
        "cat-file",
        "blob",
        object_id,
        maximum_output_bytes=maximum_bytes,
    )
    _require(
        len(raw) == object_size,
        f"{label} byte count differs from its Git object size",
    )
    return raw


def _require_visible_index_entry(repo_root: Path, path: str) -> None:
    """Reject skip-worktree/assume-unchanged concealment for a reviewed path."""

    entry = _run_git(
        repo_root,
        "--literal-pathspecs",
        "ls-files",
        "-v",
        "-z",
        "--",
        path,
        maximum_output_bytes=4096,
    )
    _require(
        entry == b"H " + path.encode("ascii") + b"\x00",
        f"reviewed path is absent, duplicated, skip-worktree, or assume-unchanged: {path}",
    )


def _require_visible_index_entries(
    repo_root: Path,
    paths: tuple[str, ...],
) -> None:
    """Batch the same exact index-visibility check for a closed path set."""

    _require(
        paths
        and len(paths) == len(set(paths))
        and all(
            isinstance(path, str) and path.isascii() and path and "\x00" not in path
            for path in paths
        ),
        "reviewed index path set is empty, duplicated, or invalid",
    )
    maximum_output_bytes = sum(len(path.encode("ascii")) + 3 for path in paths)
    raw = _run_git(
        repo_root,
        "--literal-pathspecs",
        "ls-files",
        "-v",
        "-z",
        "--",
        *paths,
        maximum_output_bytes=maximum_output_bytes,
    )
    records = raw.split(b"\x00")
    _require(
        records[-1] == b"",
        "reviewed index batch is not NUL terminated",
    )
    observed: set[str] = set()
    for record in records[:-1]:
        _require(
            record.startswith(b"H "),
            "reviewed index batch contains a concealed or non-ordinary entry",
        )
        try:
            path = record[2:].decode("ascii")
        except UnicodeDecodeError as error:
            _fail(f"reviewed index batch contains a non-ASCII path: {error}")
        _require(
            path in paths and path not in observed,
            f"reviewed index batch contains an unknown or repeated path: {path}",
        )
        observed.add(path)
    _require(
        observed == set(paths),
        "reviewed index batch is missing a required visible path",
    )


def _read_git_blob_sizes(
    repo_root: Path,
    requests: tuple[tuple[str, str, int], ...],
    *,
    object_format: str,
) -> tuple[int, ...]:
    """Batch bounded Git-object metadata before any blob content is read."""

    _require(requests, "Git blob-size batch is empty")
    object_ids: list[str] = []
    for label, object_id, maximum_bytes in requests:
        _require(
            isinstance(label, str)
            and label
            and type(maximum_bytes) is int
            and maximum_bytes > 0,
            "Git blob-size request is invalid",
        )
        object_ids.append(
            _require_object_id(
                object_id,
                object_format=object_format,
                label=label,
            )
        )
    standard_input = ("\n".join(object_ids) + "\n").encode("ascii")
    maximum_output_bytes = sum(len(object_id) + 32 for object_id in object_ids)
    raw = _run_git(
        repo_root,
        "cat-file",
        "--batch-check",
        maximum_output_bytes=maximum_output_bytes,
        standard_input=standard_input,
    )
    lines = raw.splitlines()
    _require(
        len(lines) == len(requests),
        "Git blob-size batch returned an unexpected result count",
    )
    sizes: list[int] = []
    for line, (label, expected_object_id, maximum_bytes) in zip(
        lines,
        requests,
        strict=True,
    ):
        try:
            object_id_raw, object_type, size_raw = line.split(b" ", 2)
            object_id = object_id_raw.decode("ascii")
            object_size_text = size_raw.decode("ascii")
        except (UnicodeDecodeError, ValueError) as error:
            _fail(f"{label} has malformed batched Git metadata: {error}")
        _require(
            object_id == expected_object_id
            and object_type == b"blob"
            and object_size_text.isascii()
            and object_size_text.isdecimal(),
            f"{label} has substituted batched Git metadata",
        )
        object_size = int(object_size_text)
        _require(
            0 < object_size <= maximum_bytes,
            f"{label} is outside its {maximum_bytes}-byte bound",
        )
        sizes.append(object_size)
    return tuple(sizes)


def _read_git_blob_with_size(
    repo_root: Path,
    object_id: str,
    *,
    object_size: int,
    object_format: str,
    label: str,
) -> bytes:
    """Read one blob after its exact size was returned by a bounded batch."""

    _require_object_id(object_id, object_format=object_format, label=label)
    _require(
        type(object_size) is int and object_size > 0,
        f"{label} has an invalid prechecked Git object size",
    )
    raw = _run_git(
        repo_root,
        "cat-file",
        "blob",
        object_id,
        maximum_output_bytes=object_size,
    )
    _require(
        len(raw) == object_size,
        f"{label} byte count differs from its prechecked Git object size",
    )
    return raw


def _read_git_tree_entries(
    repo_root: Path,
    commit: str,
    paths: tuple[str, ...],
    *,
    object_format: str,
) -> dict[str, tuple[str, str]]:
    """Resolve a closed literal path set from one commit in one Git query."""

    _require_object_id(
        commit,
        object_format=object_format,
        label="batched Git tree commit",
    )
    _require(
        paths
        and len(paths) == len(set(paths))
        and all(
            isinstance(path, str) and path.isascii() and path and "\x00" not in path
            for path in paths
        ),
        "batched Git tree path set is empty, duplicated, or invalid",
    )
    maximum_output_bytes = sum(
        len(path.encode("ascii")) + len(commit) + 32 for path in paths
    )
    raw = _run_git(
        repo_root,
        "--literal-pathspecs",
        "ls-tree",
        "-z",
        "--full-tree",
        commit,
        "--",
        *paths,
        maximum_output_bytes=maximum_output_bytes,
    )
    records = raw.split(b"\x00")
    _require(
        records[-1] == b"",
        "batched Git tree result is not NUL terminated",
    )
    observed: dict[str, tuple[str, str]] = {}
    expected = set(paths)
    for record in records[:-1]:
        try:
            _metadata, path_raw = record.split(b"\t", 1)
            path = path_raw.decode("ascii")
        except (UnicodeDecodeError, ValueError) as error:
            _fail(f"batched Git tree contains a malformed path: {error}")
        _require(
            path in expected and path not in observed,
            f"batched Git tree contains an unknown or repeated path: {path}",
        )
        observed[path] = _parse_ls_tree_entry(
            record + b"\x00",
            expected_path=path,
            object_format=object_format,
        )
    _require(
        set(observed) == expected,
        "batched Git tree is missing a required path",
    )
    return observed


def _worktree_git_mode(mode: int) -> str:
    """Project a regular worktree mode onto Git's closed blob-mode domain."""

    _require(
        type(mode) is int and stat.S_ISREG(mode) and not stat.S_ISLNK(mode),
        "worktree mode projection requires one regular non-symlink file",
    )
    return "100755" if mode & 0o111 else "100644"


def _snapshot_review_source(
    repo_root: Path,
    source_commit: str,
    policy: ReviewAuthorityPolicy,
    *,
    require_current_clean_head: bool,
) -> GitSourceSnapshot:
    """Resolve one exact commit/tree and the closed required blob inventory."""
    policy.validate()
    repo_root = _validate_repository_root(repo_root)
    object_format = (
        _run_git(
            repo_root,
            "rev-parse",
            "--show-object-format",
            maximum_output_bytes=64,
        )
        .decode("ascii")
        .strip()
    )
    _object_id_pattern(object_format)
    source_commit = _require_object_id(
        source_commit,
        object_format=object_format,
        label="review source commit",
    )
    object_type = (
        _run_git(
            repo_root,
            "cat-file",
            "-t",
            source_commit,
            maximum_output_bytes=64,
        )
        .decode("ascii")
        .strip()
    )
    _require(object_type == "commit", "review source object must be a commit")
    commit_size_text = (
        _run_git(
            repo_root,
            "cat-file",
            "-s",
            source_commit,
            maximum_output_bytes=64,
        )
        .decode("ascii")
        .strip()
    )
    _require(
        commit_size_text.isascii()
        and commit_size_text.isdecimal()
        and 0 < int(commit_size_text) <= 1024 * 1024,
        "review source commit object is outside its byte bound",
    )
    commit_object = _run_git(
        repo_root,
        "cat-file",
        "-p",
        source_commit,
        maximum_output_bytes=1024 * 1024,
    )
    _require(
        len(commit_object) == int(commit_size_text),
        "review source commit bytes differ from the Git object size",
    )
    first_line = commit_object.splitlines()[0].decode("ascii", errors="strict")
    _require(first_line.startswith("tree "), "review source commit has no tree")
    tree = first_line.removeprefix("tree ")
    _require_object_id(tree, object_format=object_format, label="review source tree")

    # Validate the branch with Git only after the stricter local text filter.
    branch = _validate_branch_text(policy.branch)
    _run_git(
        repo_root,
        "check-ref-format",
        "--branch",
        branch,
        maximum_output_bytes=1024,
    )
    if require_current_clean_head:
        head = (
            _run_git(
                repo_root,
                "rev-parse",
                "--verify",
                "HEAD",
                maximum_output_bytes=128,
            )
            .decode("ascii")
            .strip()
        )
        _require_object_id(head, object_format=object_format, label="current HEAD")
        _require(head == source_commit, "review source commit must equal current HEAD")
        current_branch = (
            _run_git(
                repo_root,
                "symbolic-ref",
                "--quiet",
                "--short",
                "HEAD",
                maximum_output_bytes=1024,
            )
            .decode("ascii")
            .strip()
        )
        _require(
            current_branch == branch,
            "review policy branch must equal the current attached branch",
        )
        status = _run_git(
            repo_root,
            "status",
            "--porcelain=v2",
            "-z",
            "--untracked-files=all",
            maximum_output_bytes=16 * 1024 * 1024,
        )
        _require(
            status == b"",
            "review issuance and promotion require an entirely clean worktree",
        )

    blobs: list[dict[str, Any]] = []
    blob_bytes_by_role: dict[str, bytes] = {}
    blob_mode_by_role: dict[str, str] = {}
    for role, path, maximum_bytes in REQUIRED_SOURCE_ROLES:
        _require_visible_index_entry(repo_root, path)
        # ``--literal-pathspecs`` prevents ``:(...)`` and other pathspec magic.
        entry = _run_git(
            repo_root,
            "--literal-pathspecs",
            "ls-tree",
            "-z",
            "--full-tree",
            source_commit,
            "--",
            path,
            maximum_output_bytes=4096,
        )
        mode, object_id = _parse_ls_tree_entry(
            entry,
            expected_path=path,
            object_format=object_format,
        )
        raw = _read_git_blob(
            repo_root,
            object_id,
            maximum_bytes=maximum_bytes,
            object_format=object_format,
            label=f"review source blob {role}",
        )
        _require(
            0 < len(raw) <= maximum_bytes,
            f"review source blob {role} is outside its byte bound",
        )
        blobs.append(
            {
                "byte_length": len(raw),
                "git_blob": object_id,
                "mode": mode,
                "path": path,
                "role": role,
                "sha256": sha256(raw).hexdigest(),
            }
        )
        blob_bytes_by_role[role] = raw
        blob_mode_by_role[role] = mode

    if require_current_clean_head:
        # Issuance and promotion execute against the exact implementation in
        # the reviewed current cut.  Historical receipt inspection during a
        # reopen is different: the current verifier can legitimately be newer
        # than the implementation bound into the old receipt.  The reopen API
        # separately snapshots the clean current cut before it inspects the
        # historical receipt.
        executing_sources = {
            "allocation_boundary_implementation": (
                ROOT / "scripts" / "selector_allocation_inventory.py"
            ),
            "semantic_generator": (
                ROOT / "scripts" / "generate_selector_closure_source.py"
            ),
            "semantic_checker": ROOT / "scripts" / "check_selector_closure.py",
            "semantic_codec": ROOT / "scripts" / "selector_closure_codec.py",
            "resource_closure_projection": (
                ROOT / "scripts" / "selector_resource_closure.py"
            ),
            "review_boundary_implementation": Path(__file__),
        }
        for role, executing_path in executing_sources.items():
            executing_raw = read_bounded_regular_file(
                executing_path,
                maximum_bytes=REQUIRED_SOURCE_ROLE_LIMITS[role],
                label=f"executing review implementation {role}",
            )
            _require(
                executing_raw == blob_bytes_by_role[role],
                (f"executing implementation differs from reviewed Git blob: {role}"),
            )

        for role, path, maximum_bytes in REQUIRED_SOURCE_ROLES:
            worktree_path = repo_root / path
            try:
                mode = worktree_path.lstat().st_mode
            except OSError as error:
                _fail(f"cannot inspect reviewed worktree file {path}: {error}")
            _require(
                _worktree_git_mode(mode) == blob_mode_by_role[role],
                f"reviewed worktree file mode differs from Git: {path}",
            )
            worktree_raw = read_bounded_regular_file(
                worktree_path,
                maximum_bytes=maximum_bytes,
                label=f"reviewed worktree file {role}",
            )
            _require(
                worktree_raw == blob_bytes_by_role[role],
                f"reviewed worktree bytes differ from committed blob: {path}",
            )
        final_head = (
            _run_git(
                repo_root,
                "rev-parse",
                "--verify",
                "HEAD",
                maximum_output_bytes=128,
            )
            .decode("ascii")
            .strip()
        )
        _require(
            final_head == source_commit,
            "review source HEAD changed while the source cut was read",
        )
        final_status = _run_git(
            repo_root,
            "status",
            "--porcelain=v2",
            "-z",
            "--untracked-files=all",
            maximum_output_bytes=16 * 1024 * 1024,
        )
        _require(
            final_status == b"",
            "review worktree changed while the source cut was read",
        )

    return GitSourceSnapshot(
        source_cut={
            "blobs": blobs,
            "branch": branch,
            "commit": source_commit,
            "object_format": object_format,
            "repository": policy.repository,
            "tree": tree,
            "worktree_requirement": WORKTREE_REQUIREMENT,
        },
        blob_bytes_by_role=blob_bytes_by_role,
    )


def snapshot_review_source(
    repo_root: Path,
    source_commit: str,
    policy: ReviewAuthorityPolicy,
    *,
    require_current_clean_head: bool,
) -> GitSourceSnapshot:
    """Resolve the exact clean current cut used for issuance and promotion."""

    _require(
        require_current_clean_head is True,
        (
            "review authority requires current HEAD, branch, and the entire "
            "worktree to match the declared clean source cut"
        ),
    )
    return _snapshot_review_source(
        repo_root,
        source_commit,
        policy,
        require_current_clean_head=True,
    )


def snapshot_historical_review_source(
    repo_root: Path,
    source_commit: str,
    policy: ReviewAuthorityPolicy,
) -> GitSourceSnapshot:
    """Resolve committed review blobs for reopen without asserting current HEAD."""

    return _snapshot_review_source(
        repo_root,
        source_commit,
        policy,
        require_current_clean_head=False,
    )


def verify_transition_source_cut(
    repo_root: Path,
    source_cut: dict[str, Any],
    mutable_role_bytes: dict[str, tuple[bytes, bytes]],
) -> dict[str, str]:
    """Verify one clean-cut descendant containing only an exact transaction prefix.

    This is not review issuance and does not relax ``validate_review_document``.
    It exists only so journal recovery can recheck the immutable committed cut
    after one or more tracked transaction outputs have been installed.
    """

    source_cut = _validate_source_cut_shape(source_cut)
    _require(
        set(mutable_role_bytes) == TRANSITION_MUTABLE_SOURCE_ROLES,
        "transition recovery must bind the exact four mutable source roles",
    )
    for role, alternatives in mutable_role_bytes.items():
        _require(
            isinstance(alternatives, tuple)
            and len(alternatives) == 2
            and all(type(raw) is bytes for raw in alternatives),
            f"transition mutable role {role} must have exact old/new bytes",
        )
        _require(
            alternatives[0] != alternatives[1],
            f"transition mutable role {role} must change bytes",
        )

    repo_root = _validate_repository_root(repo_root)
    object_format = (
        _run_git(
            repo_root,
            "rev-parse",
            "--show-object-format",
            maximum_output_bytes=64,
        )
        .decode("ascii")
        .strip()
    )
    _require(
        object_format == source_cut["object_format"],
        "transition repository object format differs from the source cut",
    )
    head = (
        _run_git(
            repo_root,
            "rev-parse",
            "--verify",
            "HEAD",
            maximum_output_bytes=128,
        )
        .decode("ascii")
        .strip()
    )
    _require(
        head == source_cut["commit"],
        "transition source HEAD differs from the reviewed commit",
    )
    branch = (
        _run_git(
            repo_root,
            "symbolic-ref",
            "--quiet",
            "--short",
            "HEAD",
            maximum_output_bytes=1024,
        )
        .decode("ascii")
        .strip()
    )
    _require(
        branch == source_cut["branch"],
        "transition source branch differs from the reviewed branch",
    )
    commit_object = _run_git(
        repo_root,
        "cat-file",
        "-p",
        source_cut["commit"],
        maximum_output_bytes=1024 * 1024,
    )
    first_line = commit_object.splitlines()[0].decode("ascii", errors="strict")
    _require(
        first_line == f"tree {source_cut['tree']}",
        "transition source commit tree differs from the reviewed tree",
    )

    state_by_role: dict[str, str] = {}
    allowed_paths = {
        REQUIRED_SOURCE_ROLE_PATHS[role] for role in TRANSITION_MUTABLE_SOURCE_ROLES
    }
    source_blobs = source_cut["blobs"]
    source_paths = tuple(blob["path"] for blob in source_blobs)
    _require_visible_index_entries(repo_root, source_paths)
    tree_entries = _read_git_tree_entries(
        repo_root,
        source_cut["commit"],
        source_paths,
        object_format=object_format,
    )
    blob_sizes = _read_git_blob_sizes(
        repo_root,
        tuple(
            (
                f"transition source blob {blob['role']}",
                blob["git_blob"],
                REQUIRED_SOURCE_ROLE_LIMITS[blob["role"]],
            )
            for blob in source_blobs
        ),
        object_format=object_format,
    )
    for blob, object_size in zip(source_blobs, blob_sizes, strict=True):
        role = blob["role"]
        path = blob["path"]
        mode, object_id = tree_entries[path]
        _require(
            mode == blob["mode"] and object_id == blob["git_blob"],
            f"transition source Git entry differs for {role}",
        )
        committed_raw = _read_git_blob_with_size(
            repo_root,
            object_id,
            object_size=object_size,
            object_format=object_format,
            label=f"transition source blob {role}",
        )
        _require(
            len(committed_raw) == blob["byte_length"]
            and sha256(committed_raw).hexdigest() == blob["sha256"],
            f"transition source blob commitment differs for {role}",
        )
        try:
            worktree_stat = (repo_root / path).lstat()
        except OSError as error:
            _fail(f"cannot inspect transition worktree source {role}: {error}")
        _require(
            _worktree_git_mode(worktree_stat.st_mode) == blob["mode"],
            f"transition worktree mode differs from committed source: {role}",
        )
        worktree_raw = read_bounded_regular_file(
            repo_root / path,
            maximum_bytes=REQUIRED_SOURCE_ROLE_LIMITS[role],
            label=f"transition worktree source {role}",
        )
        if role in mutable_role_bytes:
            expected_raw, next_raw = mutable_role_bytes[role]
            if worktree_raw == expected_raw:
                state_by_role[role] = "EXPECTED"
            elif worktree_raw == next_raw:
                state_by_role[role] = "NEXT"
            else:
                _fail(f"transition mutable source has third-state bytes: {role}")
            _require(
                committed_raw == expected_raw,
                f"transition expected bytes differ from committed source: {role}",
            )
        else:
            _require(
                worktree_raw == committed_raw,
                f"immutable transition source changed: {role}",
            )

    status = _run_git(
        repo_root,
        "status",
        "--porcelain=v2",
        "-z",
        "--untracked-files=all",
        maximum_output_bytes=16 * 1024 * 1024,
    )
    observed_dirty_paths: set[str] = set()
    for record in status.split(b"\x00"):
        if not record:
            continue
        fields = record.split(b" ", 8)
        _require(
            len(fields) == 9 and fields[0] == b"1" and fields[1] == b".M",
            "transition worktree contains a non-ordinary or staged change",
        )
        try:
            dirty_path = fields[8].decode("ascii")
        except UnicodeDecodeError as error:
            _fail(f"transition dirty path is not ASCII: {error}")
        _require(
            dirty_path in allowed_paths,
            f"transition worktree contains an unrelated dirty path: {dirty_path}",
        )
        _require(
            dirty_path not in observed_dirty_paths,
            f"transition worktree repeats a dirty path: {dirty_path}",
        )
        observed_dirty_paths.add(dirty_path)
    expected_dirty_paths = {
        REQUIRED_SOURCE_ROLE_PATHS[role]
        for role, state in state_by_role.items()
        if state == "NEXT"
    }
    _require(
        observed_dirty_paths == expected_dirty_paths,
        "transition Git status differs from exact old/new artifact states",
    )
    return state_by_role


def _validate_review_schema_bytes(raw: bytes) -> dict[str, Any]:
    try:
        from jsonschema import Draft202012Validator
        from jsonschema.exceptions import SchemaError
    except ImportError as error:
        _fail(f"JSON Schema validation dependency is unavailable: {error}")

    _require(
        0 < len(raw) <= MAX_REVIEW_SCHEMA_BYTES,
        "review document schema is outside its byte bound",
    )
    _require(
        sha256(raw).hexdigest() == REVIEW_DOCUMENT_SCHEMA_SHA256,
        "review document schema reviewed byte identity changed",
    )
    schema = parse_json_bytes(
        raw,
        label="selector allocation review schema",
        maximum_bytes=MAX_REVIEW_SCHEMA_BYTES,
    )
    _require(isinstance(schema, dict), "review document schema must be an object")
    _require(
        schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema"
        and schema.get("$id") == REVIEW_DOCUMENT_SCHEMA_URL
        and schema.get("type") == "object"
        and schema.get("additionalProperties") is False,
        "review document schema has an unexpected root identity",
    )
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as error:
        _fail(f"review document schema fails draft 2020-12 meta-validation: {error}")
    _validate_review_schema_runtime_parity(schema)
    return schema


def _validate_review_schema_runtime_parity(schema: dict[str, Any]) -> None:
    """Require exact cardinality and suite parity with the runtime boundary."""

    definitions = schema.get("$defs")
    _require(
        isinstance(definitions, dict),
        "review document schema definitions are missing",
    )
    for name, runtime_keys in (
        ("allocationReviewProfile", ALLOCATION_REVIEW_PROFILE_KEYS),
        ("semanticReviewSubject", SEMANTIC_REVIEW_SUBJECT_KEYS),
    ):
        rule = _closed_object(
            definitions.get(name),
            keys={
                "additionalProperties",
                "maxProperties",
                "properties",
                "required",
                "type",
            },
            label=f"review document schema {name}",
        )
        properties = rule["properties"]
        required = rule["required"]
        _require(
            rule["type"] == "object"
            and rule["additionalProperties"] is False
            and isinstance(properties, dict)
            and isinstance(required, list)
            and len(required) == len(set(required))
            and set(required) == runtime_keys
            and set(properties) == runtime_keys
            and rule["maxProperties"] == len(runtime_keys),
            f"review document schema {name} differs from runtime keys",
        )

    _require(
        definitions.get("allocationIdentityCommitmentSuite")
        == {"const": ALLOCATION_IDENTITY_COMMITMENT_SUITE},
        "review document schema allocation identity suite differs from runtime",
    )
    _require(
        definitions.get("semanticShapeCommitmentSuite")
        == {"const": SEMANTIC_SHAPE_COMMITMENT_SUITE},
        "review document schema semantic-shape suite differs from runtime",
    )

    subject_properties = definitions["semanticReviewSubject"]["properties"]
    for key, value in SEMANTIC_REVIEW_SUBJECT_SUITE.items():
        rule = subject_properties[key]
        if key == "excluded_top_level_keys":
            expected_rule = {
                "type": "array",
                "minItems": len(value),
                "maxItems": len(value),
                "prefixItems": [{"const": item} for item in value],
                "items": False,
            }
        else:
            expected_rule = {"const": value}
        _require(
            rule == expected_rule,
            "review document schema semantic review subject "
            f"field differs from runtime: {key}",
        )


def _validate_review_schema_instance(
    document: dict[str, Any],
    schema: dict[str, Any],
) -> None:
    """Apply the exact committed review schema as defense in depth."""

    try:
        from jsonschema import Draft202012Validator
    except ImportError as error:
        _fail(f"JSON Schema validation dependency is unavailable: {error}")
    error, truncated, error_count = _first_bounded_schema_error(
        Draft202012Validator(schema), document
    )
    if error is not None:
        path = "/" + "/".join(str(part) for part in error.absolute_path)
        count_text = (
            f">={MAX_SCHEMA_ERRORS + 1}" if truncated else str(error_count)
        )
        _fail(
            f"review document fails its committed schema at {path}: "
            f"{error.message}; errors={count_text}"
        )


def _validate_adr_source_blobs(
    inventory: dict[str, Any],
    snapshot: GitSourceSnapshot,
) -> None:
    """Bind each reviewed ADR source row to its exact committed Git blob."""

    raw_by_role = snapshot.blob_bytes_by_role
    for adr_index, document in enumerate(inventory["documents"], 1):
        main_role = f"adr_{adr_index:03d}_source"
        main_raw = raw_by_role[main_role]
        _require(
            document["path"] == REQUIRED_SOURCE_ROLE_PATHS[main_role]
            and document["byte_length"] == len(main_raw)
            and document["sha256"] == sha256(main_raw).hexdigest(),
            f"allocation review ADR-{adr_index:03d} main source differs from Git",
        )
        for module_index, module in enumerate(document["modules"], 1):
            module_role = f"adr_{adr_index:03d}_module_{module_index:03d}"
            module_raw = raw_by_role[module_role]
            _require(
                module["path"] == REQUIRED_SOURCE_ROLE_PATHS[module_role]
                and module["byte_length"] == len(module_raw)
                and module["sha256"] == sha256(module_raw).hexdigest(),
                (
                    f"allocation review ADR-{adr_index:03d} module "
                    f"{module_index} differs from Git"
                ),
            )


def _validate_derived_review_profile(
    inventory: dict[str, Any],
    expanded: dict[str, Any],
) -> None:
    """Recompute every model projection bound by the local review profile."""

    # Imports stay lazy so the generator can import this module without an
    # initialization cycle when it integrates the transition plans.
    from generate_selector_closure_source import (
        _default_incomplete_refresh_metrics,
    )
    from selector_resource_closure import derive_resource_closure

    try:
        (
            model_allocation_count,
            model_allocation_sha256,
            model_origin_signal_row_count,
            model_origin_signal_sha256,
            semantic_shape_entry_count,
            semantic_shape_sha256,
        ) = _default_incomplete_refresh_metrics(expanded)
        _, resource_closure = derive_resource_closure(expanded)
    except (KeyError, TypeError, ValueError) as error:
        _fail(f"review profile projection derivation failed: {error}")
    profile = inventory["allocation_review_profile"]
    _require(
        {
            "model_allocation_count": model_allocation_count,
            "model_allocation_sha256": model_allocation_sha256,
            "model_origin_signal_row_count": model_origin_signal_row_count,
            "model_origin_signal_sha256": model_origin_signal_sha256,
            "resource_closure_row_count": resource_closure["row_count"],
            "resource_closure_sha256": resource_closure["sha256"],
            "semantic_shape_entry_count": semantic_shape_entry_count,
            "semantic_shape_sha256": semantic_shape_sha256,
        }
        == {
            "model_allocation_count": profile["model_allocation_count"],
            "model_allocation_sha256": profile["model_allocation_sha256"],
            "model_origin_signal_row_count": profile["model_origin_signal_row_count"],
            "model_origin_signal_sha256": profile["model_origin_signal_sha256"],
            "resource_closure_row_count": profile["resource_closure_row_count"],
            "resource_closure_sha256": profile["resource_closure_sha256"],
            "semantic_shape_entry_count": profile["semantic_shape_entry_count"],
            "semantic_shape_sha256": profile["semantic_shape_sha256"],
        },
        (
            "allocation review profile differs from the freshly derived "
            "model, resource-closure, or semantic-shape projection"
        ),
    )


def _load_review_inputs_from_snapshot(
    snapshot: GitSourceSnapshot,
) -> tuple[
    dict[str, Any],
    bytes,
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    ReviewGenerationState,
]:
    # Import lazily so the semantic generator can import this module when it
    # integrates the transition APIs without creating a module-import cycle.
    from generate_selector_closure_source import (
        AUTHORING_SCHEMA_SHA256,
        COMPACT_SCHEMA_SHA256,
        _assert_supported_schema,
        _validate_schema_instance,
        prepare_canonical_source,
    )

    raw_by_role = snapshot.blob_bytes_by_role
    inventory_schema_raw = raw_by_role["allocation_schema"]
    _require(
        sha256(inventory_schema_raw).hexdigest() == INVENTORY_SCHEMA_SHA256,
        "committed allocation schema reviewed byte identity changed",
    )
    inventory_schema = parse_json_bytes(
        inventory_schema_raw,
        label="committed allocation schema",
        maximum_bytes=REQUIRED_SOURCE_ROLE_LIMITS["allocation_schema"],
    )
    _require(
        isinstance(inventory_schema, dict),
        "committed allocation schema must be an object",
    )
    inventory_raw = raw_by_role["allocation_inventory"]
    inventory = parse_json_bytes(
        inventory_raw,
        label="committed allocation inventory",
        maximum_bytes=REQUIRED_SOURCE_ROLE_LIMITS["allocation_inventory"],
    )
    _require(
        isinstance(inventory, dict),
        "committed allocation inventory must be an object",
    )
    _require(
        inventory_raw == inventory_bytes(inventory),
        "committed allocation inventory is not canonical with one trailing LF",
    )
    validate_allocation_inventory(inventory, inventory_schema)
    validate_allocation_review_profile_schema_binding(
        inventory,
        inventory_schema_raw,
    )
    _validate_adr_source_blobs(inventory, snapshot)

    authoring_schema_raw = raw_by_role["semantic_authoring_schema"]
    _require(
        sha256(authoring_schema_raw).hexdigest() == AUTHORING_SCHEMA_SHA256,
        "committed semantic authoring schema reviewed byte identity changed",
    )
    authoring_schema = parse_json_bytes(
        authoring_schema_raw,
        label="committed semantic authoring schema",
        maximum_bytes=REQUIRED_SOURCE_ROLE_LIMITS["semantic_authoring_schema"],
    )
    _require(
        isinstance(authoring_schema, dict)
        and authoring_schema.get("$schema")
        == "https://json-schema.org/draft/2020-12/schema"
        and authoring_schema.get("$id") == AUTHORING_SCHEMA_URL,
        "committed semantic authoring schema has an unexpected identity",
    )
    _assert_supported_schema(authoring_schema)
    authoring_raw = raw_by_role["semantic_authoring_source"]
    authoring = parse_json_bytes(
        authoring_raw,
        label="committed semantic authoring source",
        maximum_bytes=REQUIRED_SOURCE_ROLE_LIMITS["semantic_authoring_source"],
    )
    _require(
        isinstance(authoring, dict),
        "committed semantic authoring source must be an object",
    )
    _validate_schema_instance(authoring, authoring_schema)
    _require(
        authoring_raw == canonical_bytes(authoring) + b"\n",
        "committed semantic authoring source is not canonical with one trailing LF",
    )

    compact_raw = raw_by_role["semantic_compact_source"]
    envelope = parse_json_bytes(
        compact_raw,
        label="committed compact semantic source",
        maximum_bytes=MAX_COMPACT_BYTES,
    )
    _require(
        isinstance(envelope, dict),
        "committed compact semantic source must be an object",
    )
    compact_schema_raw = raw_by_role["semantic_compact_schema"]
    _require(
        sha256(compact_schema_raw).hexdigest() == COMPACT_SCHEMA_SHA256,
        "committed compact semantic schema reviewed byte identity changed",
    )
    compact_schema = parse_json_bytes(
        compact_schema_raw,
        label="committed compact semantic schema",
        maximum_bytes=REQUIRED_SOURCE_ROLE_LIMITS["semantic_compact_schema"],
    )
    _require(
        isinstance(compact_schema, dict)
        and compact_schema.get("$schema")
        == "https://json-schema.org/draft/2020-12/schema"
        and compact_schema.get("$id") == COMPACT_SCHEMA_URL,
        "committed compact semantic schema has an unexpected identity",
    )
    _validate_schema_instance(envelope, compact_schema)
    expanded = decode_compact_source(
        envelope,
        maximum_expanded_bytes=MAX_EXPANDED_BYTES,
    )
    _require(
        serialize_compact_source(
            expanded,
            maximum_compact_bytes=MAX_COMPACT_BYTES,
            maximum_expanded_bytes=MAX_EXPANDED_BYTES,
        )
        == compact_raw,
        "committed compact semantic source is not its deterministic encoding",
    )
    _require(
        expanded.get("adr_allocation_oracle") == inventory_to_oracle(inventory),
        "committed semantic source oracle differs from the allocation inventory",
    )
    expected_binding = build_inventory_binding(inventory_raw, inventory_schema_raw)
    _require(
        authoring.get("adr_allocation_inventory_binding") == expected_binding,
        "committed semantic authoring source has a stale allocation binding",
    )
    _require(
        prepare_canonical_source(authoring, inventory_to_oracle(inventory)) == expanded,
        "committed semantic authoring and compact sources are not equivalent",
    )
    _require(
        semantic_review_subject_commitment(expanded)
        == inventory["semantic_review_subject"],
        "allocation inventory does not bind the exact expanded semantic subject",
    )
    _validate_derived_review_profile(inventory, expanded)
    state_schema = _validate_review_state_schema_bytes(
        raw_by_role["review_generation_state_schema"]
    )
    state_value = parse_json_bytes(
        raw_by_role["review_generation_state"],
        label="committed review-generation state",
        maximum_bytes=REQUIRED_SOURCE_ROLE_LIMITS["review_generation_state"],
    )
    _require(
        isinstance(state_value, dict),
        "committed review-generation state must be an object",
    )
    try:
        from jsonschema import Draft202012Validator
    except ImportError as error:
        _fail(f"JSON Schema validation dependency is unavailable: {error}")
    state_error, truncated, error_count = _first_bounded_schema_error(
        Draft202012Validator(state_schema), state_value
    )
    if state_error is not None:
        count_text = (
            f">={MAX_SCHEMA_ERRORS + 1}" if truncated else str(error_count)
        )
        _fail(
            "committed review-generation state fails its schema: "
            f"{state_error.message}; errors={count_text}"
        )
    committed_state = _validate_review_state_projection(
        state_value,
        label="committed review-generation state",
    )
    _require(
        raw_by_role["review_generation_state"] == review_state_bytes(committed_state),
        "committed review-generation state is not canonical",
    )
    review_schema = _validate_review_schema_bytes(raw_by_role["review_document_schema"])
    return (
        inventory,
        inventory_schema_raw,
        inventory_schema,
        expanded,
        review_schema,
        committed_state,
    )


def _assignment_sha256(inventory: dict[str, Any]) -> str:
    projection = {
        "allocation_review_profile": inventory["allocation_review_profile"],
        "allocations": inventory["allocations"],
        "document_source_sets": [
            {
                "adr_id": document["adr_id"],
                "allocation_anchor_id": document["allocation_anchor_id"],
                "source_set": document["source_set"],
            }
            for document in inventory["documents"]
        ],
        "exclusions": inventory["exclusions"],
        "semantic_review_subject": inventory["semantic_review_subject"],
    }
    portable_raw = _canonical_review_bytes(projection)
    _require(
        canonical_bytes(projection) == portable_raw,
        (
            "allocation assignment is outside the declared portable "
            "canonical scalar domain"
        ),
    )
    portable_digest = sha256()
    portable_digest.update(PROVENANCE_REVIEW_DOMAIN)
    portable_digest.update(portable_raw)
    existing_digest = provenance_assignment_sha256(
        inventory["documents"],
        inventory["allocations"],
        inventory["exclusions"],
        inventory["allocation_review_profile"],
        inventory["semantic_review_subject"],
    )
    _require(
        existing_digest == portable_digest.hexdigest(),
        "portable assignment commitment differs from the inventory commitment",
    )
    return existing_digest


def _build_review_subject(
    inventory: dict[str, Any],
    inventory_schema_raw: bytes,
) -> dict[str, Any]:
    profile = inventory["allocation_review_profile"]
    assignment_sha256 = _assignment_sha256(inventory)
    return {
        "allocation_review_profile": copy.deepcopy(profile),
        "allocation_schema_binding": {
            "byte_length": len(inventory_schema_raw),
            "schema_id": INVENTORY_SCHEMA_ID,
            "sha256": sha256(inventory_schema_raw).hexdigest(),
        },
        "assignment_commitment_suite": {
            **copy.deepcopy(PROVENANCE_REVIEW_SUITE),
            "scalar_domain": ASSIGNMENT_SCALAR_DOMAIN,
        },
        "model_projection": {
            "model_allocation_count": profile["model_allocation_count"],
            "model_allocation_sha256": profile["model_allocation_sha256"],
            "model_origin_signal_projection_schema": (
                MODEL_ORIGIN_SIGNAL_PROJECTION_SCHEMA
            ),
            "model_origin_signal_row_count": profile["model_origin_signal_row_count"],
            "model_origin_signal_sha256": profile["model_origin_signal_sha256"],
            "model_projection_schema": MODEL_ALLOCATION_PROJECTION_SCHEMA,
            "resource_closure_row_count": profile["resource_closure_row_count"],
            "resource_closure_schema": RESOURCE_CLOSURE_PROJECTION_SCHEMA,
            "resource_closure_sha256": profile["resource_closure_sha256"],
            "schema": REVIEW_MODEL_PROJECTION_SCHEMA,
            "semantic_shape_entry_count": profile["semantic_shape_entry_count"],
            "semantic_shape_projection_schema": (SEMANTIC_SHAPE_PROJECTION_SCHEMA),
            "semantic_shape_sha256": profile["semantic_shape_sha256"],
        },
        "provenance_assignment_sha256": assignment_sha256,
        "semantic_review_subject": copy.deepcopy(inventory["semantic_review_subject"]),
        "taxonomy": {
            "required_kinds": list(ALLOCATION_KINDS),
            "schema": REVIEW_TAXONOMY_SCHEMA,
        },
    }


def _validate_review_state_projection(
    value: Any,
    *,
    label: str,
) -> ReviewGenerationState:
    value = _closed_object(value, keys=REVIEW_STATE_KEYS, label=label)
    _require(
        value["authority_class"] == AUTHORITY_CLASS
        and value["schema"] == REVIEW_STATE_SCHEMA,
        f"{label} has an unexpected suite",
    )
    state = ReviewGenerationState(
        state_version=value["state_version"],
        next_review_generation=value["next_review_generation"],
        active_assignment_sha256=value["active_assignment_sha256"],
        active_inventory_sha256=value["active_inventory_sha256"],
        current_receipt_sha256=value["current_receipt_sha256"],
        last_consumed_receipt_sha256=value["last_consumed_receipt_sha256"],
        prior_state_sha256=value["prior_state_sha256"],
    )
    state.validate()
    _require(state.projection() == value, f"{label} is not canonical")
    return state


def _validate_source_cut_shape(value: Any) -> dict[str, Any]:
    value = _closed_object(value, keys=SOURCE_CUT_KEYS, label="review source cut")
    _require(
        value["worktree_requirement"] == WORKTREE_REQUIREMENT,
        "review source cut has an unexpected worktree requirement",
    )
    _validate_branch_text(value["branch"])
    _require(
        value["object_format"] in {"sha1", "sha256"},
        "review source cut has an unsupported Git object format",
    )
    _require_object_id(
        value["commit"],
        object_format=value["object_format"],
        label="review source commit",
    )
    _require_object_id(
        value["tree"],
        object_format=value["object_format"],
        label="review source tree",
    )
    _validate_repository_text(value["repository"])
    blobs = value["blobs"]
    _require(
        isinstance(blobs, list) and len(blobs) == len(REQUIRED_SOURCE_ROLES),
        "review source cut has an unexpected blob count",
    )
    for index, (blob, expected) in enumerate(
        zip(blobs, REQUIRED_SOURCE_ROLES, strict=True)
    ):
        role, path, maximum_bytes = expected
        blob = _closed_object(
            blob,
            keys=BLOB_KEYS,
            label=f"review source blob {index}",
        )
        _require(
            blob["role"] == role and blob["path"] == path,
            f"review source blob {index} has a substituted role or path",
        )
        _require(
            blob["mode"] in {"100644", "100755"},
            f"review source blob {role} has an invalid mode",
        )
        _require_object_id(
            blob["git_blob"],
            object_format=value["object_format"],
            label=f"review source blob {role}",
        )
        _require_positive_safe_integer(
            blob["byte_length"],
            label=f"review source blob {role} byte length",
        )
        _require(
            blob["byte_length"] <= maximum_bytes,
            f"review source blob {role} exceeds its byte bound",
        )
        _require_sha256(blob["sha256"], label=f"review source blob {role} SHA-256")
    return value


def _validate_reviewer_authorization(
    value: Any,
    *,
    policy: ReviewAuthorityPolicy,
) -> dict[str, Any]:
    value = _closed_object(
        value,
        keys=REVIEWER_AUTHORIZATION_KEYS,
        label="reviewer authorization",
    )
    expected = policy.projection()
    _require(
        value == expected,
        "review document reviewer authorization differs from trusted local policy",
    )
    return value


def _validate_review_subject_shape(value: Any) -> dict[str, Any]:
    value = _closed_object(value, keys=REVIEW_SUBJECT_KEYS, label="review subject")
    _require_sha256(
        value["provenance_assignment_sha256"],
        label="review subject assignment SHA-256",
    )
    allocation_binding = _closed_object(
        value["allocation_schema_binding"],
        keys=ALLOCATION_SCHEMA_BINDING_KEYS,
        label="review subject allocation schema binding",
    )
    _require_positive_safe_integer(
        allocation_binding["byte_length"],
        label="review subject allocation schema byte length",
    )
    _require(
        allocation_binding["schema_id"] == INVENTORY_SCHEMA_ID,
        "review subject allocation schema has an unexpected ID",
    )
    _require_sha256(
        allocation_binding["sha256"],
        label="review subject allocation schema SHA-256",
    )
    assignment_suite = _closed_object(
        value["assignment_commitment_suite"],
        keys=ASSIGNMENT_SUITE_KEYS,
        label="review subject assignment suite",
    )
    _require(
        assignment_suite
        == {
            **PROVENANCE_REVIEW_SUITE,
            "scalar_domain": ASSIGNMENT_SCALAR_DOMAIN,
        },
        "review subject has an unexpected assignment commitment suite",
    )
    taxonomy = _closed_object(
        value["taxonomy"],
        keys=TAXONOMY_KEYS,
        label="review subject taxonomy",
    )
    _require(
        taxonomy
        == {
            "required_kinds": list(ALLOCATION_KINDS),
            "schema": REVIEW_TAXONOMY_SCHEMA,
        },
        "review subject has an unexpected allocation taxonomy",
    )
    model_projection = _closed_object(
        value["model_projection"],
        keys=MODEL_PROJECTION_KEYS,
        label="review subject model projection",
    )
    _require(
        model_projection["schema"] == REVIEW_MODEL_PROJECTION_SCHEMA
        and model_projection["model_projection_schema"]
        == MODEL_ALLOCATION_PROJECTION_SCHEMA
        and model_projection["model_origin_signal_projection_schema"]
        == MODEL_ORIGIN_SIGNAL_PROJECTION_SCHEMA
        and model_projection["resource_closure_schema"]
        == RESOURCE_CLOSURE_PROJECTION_SCHEMA
        and model_projection["semantic_shape_projection_schema"]
        == SEMANTIC_SHAPE_PROJECTION_SCHEMA,
        "review subject has an unexpected projection suite",
    )
    _require_positive_safe_integer(
        model_projection["model_allocation_count"],
        label="review subject model allocation count",
    )
    _require_positive_safe_integer(
        model_projection["model_origin_signal_row_count"],
        label="review subject model origin signal count",
    )
    _require_positive_safe_integer(
        model_projection["semantic_shape_entry_count"],
        label="review subject semantic shape count",
    )
    _require_positive_safe_integer(
        model_projection["resource_closure_row_count"],
        label="review subject resource closure row count",
    )
    _require_sha256(
        model_projection["model_allocation_sha256"],
        label="review subject model allocation SHA-256",
    )
    _require_sha256(
        model_projection["model_origin_signal_sha256"],
        label="review subject model origin signal SHA-256",
    )
    _require_sha256(
        model_projection["semantic_shape_sha256"],
        label="review subject semantic shape SHA-256",
    )
    _require_sha256(
        model_projection["resource_closure_sha256"],
        label="review subject resource closure SHA-256",
    )
    profile = _closed_object(
        value["allocation_review_profile"],
        keys=ALLOCATION_REVIEW_PROFILE_KEYS,
        label="review subject allocation review profile",
    )
    _require(
        profile["schema"] == ALLOCATION_REVIEW_PROFILE_SCHEMA,
        "review subject allocation review profile has an unexpected schema",
    )
    _require(
        isinstance(value["semantic_review_subject"], dict),
        "review subject semantic review subject must be an object",
    )
    # The inventory validator checks the complete semantic subject shape and
    # suite.  This boundary checks its content against the committed inventory.
    return value


def build_review_document(
    repo_root: Path,
    source_commit: str,
    policy: ReviewAuthorityPolicy,
    review_state: ReviewGenerationState,
    *,
    authorization_id: str,
    review_id: str,
) -> dict[str, Any]:
    """Build one canonical local-only authorization manifest and receipt."""

    policy.validate()
    review_state.validate()
    _require(
        review_state.current_receipt_sha256 is None,
        "a new review requires an open review-generation state",
    )
    authorization_id = _require_uuid_v4(
        authorization_id,
        label="review authorization ID",
    )
    review_id = _require_uuid_v4(review_id, label="review receipt ID")
    _require(
        authorization_id != review_id,
        "review authorization and receipt IDs must be distinct",
    )
    snapshot = snapshot_review_source(
        repo_root,
        source_commit,
        policy,
        require_current_clean_head=True,
    )
    (
        inventory,
        schema_raw,
        _schema,
        _expanded,
        review_schema,
        committed_state,
    ) = _load_review_inputs_from_snapshot(snapshot)
    _require(
        committed_state == review_state,
        "review issuance state differs from the exact committed state file",
    )
    _require(
        inventory["provenance_review"]["status"] == "NOT_REVIEWED"
        and inventory["provenance_review"]["reviewed_assignment_sha256"] == "0" * 64,
        "review issuance requires an exact NOT_REVIEWED allocation inventory",
    )
    review_subject = _build_review_subject(inventory, schema_raw)
    expected_state = review_state.projection()
    expected_state_commitment = review_state.commitment()
    manifest = {
        "authority_class": AUTHORITY_CLASS,
        "authorization_id": authorization_id,
        "claim_boundary": CLAIM_BOUNDARY,
        "expected_review_state": expected_state,
        "expected_review_state_commitment": expected_state_commitment,
        "identity_assurance": IDENTITY_ASSURANCE,
        "review_generation": review_state.next_review_generation,
        "review_subject": review_subject,
        "reviewer_authorization": policy.projection(),
        "schema": AUTHORIZATION_MANIFEST_SCHEMA,
        "source_cut": snapshot.source_cut,
    }
    manifest_commitment = _content_commitment(
        manifest,
        domain=AUTHORIZATION_MANIFEST_DOMAIN,
    )
    receipt = {
        "authority_class": AUTHORITY_CLASS,
        "authorization_id": authorization_id,
        "authorization_manifest_byte_length": manifest_commitment["byte_length"],
        "authorization_manifest_sha256": manifest_commitment["sha256"],
        "claim_boundary": CLAIM_BOUNDARY,
        "disposition": REVIEW_DISPOSITION,
        "expected_review_state_sha256": expected_state_commitment["sha256"],
        "prohibited_authority_claims": list(PROHIBITED_AUTHORITY_CLAIMS),
        "review_generation": review_state.next_review_generation,
        "review_id": review_id,
        "reviewed_assignment_sha256": review_subject["provenance_assignment_sha256"],
        "reviewer_attestation": REVIEWER_ATTESTATION,
        "reviewer_identity": policy.reviewer_identity,
        "reviewer_role": policy.reviewer_role,
        "schema": REVIEW_RECEIPT_SCHEMA,
        "semantic_review_subject_sha256": review_subject["semantic_review_subject"][
            "sha256"
        ],
    }
    receipt_commitment = _content_commitment(receipt, domain=REVIEW_RECEIPT_DOMAIN)
    document = {
        "$schema": REVIEW_DOCUMENT_SCHEMA_FILE,
        "authority_class": AUTHORITY_CLASS,
        "authorization_manifest": manifest,
        "authorization_manifest_commitment": manifest_commitment,
        "claim_boundary": CLAIM_BOUNDARY,
        "external_authority": False,
        "independent_authority": False,
        "release_authority": False,
        "review_receipt": receipt,
        "review_receipt_commitment": receipt_commitment,
        "schema": REVIEW_DOCUMENT_SCHEMA_ID,
    }
    review_document_bytes(document)
    _validate_review_schema_instance(document, review_schema)
    return document


def _validate_review_document(
    repo_root: Path,
    document: dict[str, Any],
    policy: ReviewAuthorityPolicy,
    review_state: ReviewGenerationState,
    *,
    require_current_clean_head: bool,
) -> ReviewValidation:
    """Validate the document, trusted policy, exact Git blobs, and subject."""

    policy.validate()
    review_state.validate()
    document = _closed_object(
        document,
        keys=REVIEW_DOCUMENT_KEYS,
        label="selector allocation review document",
    )
    _require(
        document["$schema"] == REVIEW_DOCUMENT_SCHEMA_FILE
        and document["schema"] == REVIEW_DOCUMENT_SCHEMA_ID
        and document["authority_class"] == AUTHORITY_CLASS
        and document["claim_boundary"] == CLAIM_BOUNDARY
        and document["external_authority"] is False
        and document["independent_authority"] is False
        and document["release_authority"] is False,
        "review document has an unexpected authority or schema boundary",
    )
    manifest = _closed_object(
        document["authorization_manifest"],
        keys=AUTHORIZATION_MANIFEST_KEYS,
        label="review authorization manifest",
    )
    manifest_commitment = _validate_content_commitment(
        document["authorization_manifest_commitment"],
        manifest,
        domain=AUTHORIZATION_MANIFEST_DOMAIN,
        label="review authorization manifest commitment",
    )
    _require(
        manifest["schema"] == AUTHORIZATION_MANIFEST_SCHEMA
        and manifest["authority_class"] == AUTHORITY_CLASS
        and manifest["claim_boundary"] == CLAIM_BOUNDARY
        and manifest["identity_assurance"] == IDENTITY_ASSURANCE,
        "review authorization manifest has an unexpected suite",
    )
    _require_uuid_v4(
        manifest["authorization_id"],
        label="review authorization manifest ID",
    )
    _require_positive_safe_integer(
        manifest["review_generation"],
        label="review authorization generation",
    )
    _validate_reviewer_authorization(
        manifest["reviewer_authorization"],
        policy=policy,
    )
    expected_state = _validate_review_state_projection(
        manifest["expected_review_state"],
        label="review authorization expected state",
    )
    _require(
        expected_state == review_state,
        "review authorization expected state differs from current local state",
    )
    expected_state_commitment = _validate_content_commitment(
        manifest["expected_review_state_commitment"],
        manifest["expected_review_state"],
        domain=REVIEW_STATE_DOMAIN,
        label="review authorization expected-state commitment",
    )
    _require(
        manifest["review_generation"] == review_state.next_review_generation,
        "review authorization generation differs from current local state",
    )
    _require(
        review_state.current_receipt_sha256 is None,
        "review authorization cannot consume an already active review state",
    )
    source_cut = _validate_source_cut_shape(manifest["source_cut"])
    _require(
        source_cut["repository"] == policy.repository
        and source_cut["branch"] == policy.branch,
        "review source cut differs from trusted local repository policy",
    )
    review_subject = _validate_review_subject_shape(manifest["review_subject"])

    receipt = _closed_object(
        document["review_receipt"],
        keys=REVIEW_RECEIPT_KEYS,
        label="selector allocation review receipt",
    )
    receipt_commitment = _validate_content_commitment(
        document["review_receipt_commitment"],
        receipt,
        domain=REVIEW_RECEIPT_DOMAIN,
        label="selector allocation review receipt commitment",
    )
    _require(
        receipt
        == {
            "authority_class": AUTHORITY_CLASS,
            "authorization_id": manifest["authorization_id"],
            "authorization_manifest_byte_length": manifest_commitment["byte_length"],
            "authorization_manifest_sha256": manifest_commitment["sha256"],
            "claim_boundary": CLAIM_BOUNDARY,
            "disposition": REVIEW_DISPOSITION,
            "expected_review_state_sha256": expected_state_commitment["sha256"],
            "prohibited_authority_claims": list(PROHIBITED_AUTHORITY_CLAIMS),
            "review_generation": manifest["review_generation"],
            "review_id": receipt["review_id"],
            "reviewed_assignment_sha256": review_subject[
                "provenance_assignment_sha256"
            ],
            "reviewer_attestation": REVIEWER_ATTESTATION,
            "reviewer_identity": policy.reviewer_identity,
            "reviewer_role": policy.reviewer_role,
            "schema": REVIEW_RECEIPT_SCHEMA,
            "semantic_review_subject_sha256": review_subject["semantic_review_subject"][
                "sha256"
            ],
        },
        "review receipt does not bind the exact authorization and subject",
    )
    _require_uuid_v4(receipt["review_id"], label="review receipt ID")
    _require(
        receipt["review_id"] != manifest["authorization_id"],
        "review authorization and receipt IDs must be distinct",
    )
    _require(
        receipt_commitment["sha256"] != review_state.last_consumed_receipt_sha256,
        "review receipt reuses the immediately prior consumed receipt",
    )

    actual_snapshot = (
        snapshot_review_source(
            repo_root,
            source_cut["commit"],
            policy,
            require_current_clean_head=True,
        )
        if require_current_clean_head
        else snapshot_historical_review_source(
            repo_root,
            source_cut["commit"],
            policy,
        )
    )
    _require(
        actual_snapshot.source_cut == source_cut,
        "review source cut differs from exact local Git objects",
    )
    (
        inventory,
        schema_raw,
        schema,
        expanded,
        review_schema,
        committed_state,
    ) = _load_review_inputs_from_snapshot(actual_snapshot)
    _require(
        committed_state == review_state,
        "review source state differs from the exact committed state file",
    )
    _require(
        inventory["provenance_review"]["status"] == "NOT_REVIEWED"
        and inventory["provenance_review"]["reviewed_assignment_sha256"] == "0" * 64,
        "review source inventory must be exactly NOT_REVIEWED",
    )
    expected_subject = _build_review_subject(inventory, schema_raw)
    _require(
        review_subject == expected_subject,
        "review subject differs from the exact committed allocation source",
    )
    assignment_sha256 = expected_subject["provenance_assignment_sha256"]
    _require(
        receipt["reviewed_assignment_sha256"] == assignment_sha256,
        "review receipt has a wrong assignment digest",
    )
    _validate_review_schema_instance(document, review_schema)
    return ReviewValidation(
        inventory=inventory,
        inventory_schema=schema,
        inventory_schema_raw=schema_raw,
        expanded_semantic_source=expanded,
        assignment_sha256=assignment_sha256,
        receipt_sha256=receipt_commitment["sha256"],
        review_state=committed_state,
        source_snapshot=actual_snapshot,
    )


def validate_review_document(
    repo_root: Path,
    document: dict[str, Any],
    policy: ReviewAuthorityPolicy,
    review_state: ReviewGenerationState,
    *,
    require_current_clean_head: bool,
) -> ReviewValidation:
    """Validate one review only against the exact clean current source cut."""

    _require(
        require_current_clean_head is True,
        "review authority validation cannot bypass the clean current-HEAD check",
    )
    return _validate_review_document(
        repo_root,
        document,
        policy,
        review_state,
        require_current_clean_head=True,
    )


def validate_active_review_for_reopen(
    repo_root: Path,
    document: dict[str, Any],
    policy: ReviewAuthorityPolicy,
    current_state: ReviewGenerationState,
    current_inventory: dict[str, Any],
) -> ReviewValidation:
    """Verify the historical receipt and its exact active reviewed successor."""

    current_state.validate()
    _require(
        current_state.current_receipt_sha256 is not None,
        "active-review reopen validation requires an active receipt",
    )
    manifest = _closed_object(
        document.get("authorization_manifest"),
        keys=AUTHORIZATION_MANIFEST_KEYS,
        label="active review authorization manifest",
    )
    expected_prior_state = _validate_review_state_projection(
        manifest["expected_review_state"],
        label="active review expected prior state",
    )
    validated = _validate_review_document(
        repo_root,
        document,
        policy,
        expected_prior_state,
        require_current_clean_head=False,
    )
    assignment_sha256 = _assignment_sha256(current_inventory)
    current_inventory_sha256 = sha256(inventory_bytes(current_inventory)).hexdigest()
    _require(
        current_inventory["provenance_review"]["status"] == "REVIEWED"
        and current_inventory["provenance_review"]["reviewed_assignment_sha256"]
        == assignment_sha256,
        "active review inventory is not the exact reviewed assignment",
    )
    _require(
        validated.receipt_sha256 == current_state.current_receipt_sha256
        and validated.assignment_sha256 == assignment_sha256
        and current_state.active_assignment_sha256 == assignment_sha256
        and current_state.active_inventory_sha256 == current_inventory_sha256,
        "active review receipt, assignment, inventory, or state binding differs",
    )
    _require(
        current_state.prior_state_sha256 == expected_prior_state.commitment()["sha256"]
        and current_state.state_version == expected_prior_state.state_version + 1
        and current_state.next_review_generation
        == expected_prior_state.next_review_generation,
        "active review state is not the exact successor of the receipt prior state",
    )
    return validated


def load_review_document(path: Path) -> dict[str, Any]:
    """Read one bounded regular canonical review document."""

    raw = read_bounded_regular_file(
        path,
        maximum_bytes=MAX_REVIEW_DOCUMENT_BYTES,
        label="selector allocation review document",
    )
    document = parse_json_bytes(
        raw,
        label=str(path),
        maximum_bytes=MAX_REVIEW_DOCUMENT_BYTES,
    )
    _require(isinstance(document, dict), "review document must be an object")
    _require(
        raw == review_document_bytes(document),
        "review document is not canonical JSON with exactly one trailing LF",
    )
    return document


def _next_promoted_state(
    current: ReviewGenerationState,
    receipt_sha256: str,
    assignment_sha256: str,
    inventory_sha256: str,
) -> ReviewGenerationState:
    prior = current.commitment()["sha256"]
    result = ReviewGenerationState(
        state_version=current.state_version + 1,
        next_review_generation=current.next_review_generation,
        active_assignment_sha256=assignment_sha256,
        active_inventory_sha256=inventory_sha256,
        current_receipt_sha256=receipt_sha256,
        last_consumed_receipt_sha256=receipt_sha256,
        prior_state_sha256=prior,
    )
    result.validate()
    return result


def _next_reopened_state(
    current: ReviewGenerationState,
) -> ReviewGenerationState:
    _require(
        current.current_receipt_sha256 is not None,
        "review reopen requires an active receipt",
    )
    prior = current.commitment()["sha256"]
    result = ReviewGenerationState(
        state_version=current.state_version + 1,
        next_review_generation=current.next_review_generation + 1,
        active_assignment_sha256=None,
        active_inventory_sha256=None,
        current_receipt_sha256=None,
        last_consumed_receipt_sha256=current.last_consumed_receipt_sha256,
        prior_state_sha256=prior,
    )
    result.validate()
    return result


def _transition_subject_sha256(content: dict[str, Any]) -> str:
    return _content_commitment(
        content,
        domain=REVIEW_TRANSITION_DOMAIN,
    )["sha256"]


def _promoted_allocation_is_complete(
    inventory: dict[str, Any],
    expanded_semantic_source: dict[str, Any],
) -> bool:
    """Derive terminal status from exact model coverage; never trust a status edit."""

    from check_selector_closure import (  # Imported lazily to avoid CLI cycles.
        BLOCKING_ADR_EXCLUSION_CLASSIFICATIONS,
        _model_allocations,
    )

    model = {
        tuple(allocation.identity_row())
        for allocation in _model_allocations(expanded_semantic_source)
    }
    declared = {
        (
            row["kind"],
            row["exact_name"],
            row["semantic_ref"],
            row["unit_id"],
        )
        for row in inventory["allocations"]
    }
    blocking_exclusions = [
        row
        for row in inventory["exclusions"]
        if row["classification"] in BLOCKING_ADR_EXCLUSION_CLASSIFICATIONS
    ]
    return declared == model and not blocking_exclusions


def plan_review_promotion(
    repo_root: Path,
    document: dict[str, Any],
    policy: ReviewAuthorityPolicy,
    review_state: ReviewGenerationState,
) -> ReviewTransitionPlan:
    """Plan one atomic NOT_REVIEWED -> REVIEWED inventory/state transition."""

    validated = validate_review_document(
        repo_root,
        document,
        policy,
        review_state,
        require_current_clean_head=True,
    )
    inventory = validated.inventory
    _require(
        inventory["provenance_review"]["status"] == "NOT_REVIEWED",
        "review promotion requires NOT_REVIEWED inventory state",
    )
    before = inventory_bytes(inventory)
    promoted = copy.deepcopy(inventory)
    promoted["provenance_review"]["status"] = "REVIEWED"
    promoted["provenance_review"]["reviewed_assignment_sha256"] = (
        validated.assignment_sha256
    )
    promoted["status"] = (
        "COMPLETE"
        if _promoted_allocation_is_complete(
            promoted,
            validated.expanded_semantic_source,
        )
        else "INCOMPLETE_FAIL_CLOSED"
    )
    validate_allocation_inventory(promoted, validated.inventory_schema)
    validate_allocation_review_profile_schema_binding(
        promoted,
        validated.inventory_schema_raw,
    )
    after = inventory_bytes(promoted)
    next_state = _next_promoted_state(
        review_state,
        validated.receipt_sha256,
        validated.assignment_sha256,
        sha256(after).hexdigest(),
    )
    expected_state_sha256 = review_state.commitment()["sha256"]
    next_state_sha256 = next_state.commitment()["sha256"]
    transition_subject = {
        "action": "PROMOTE_TO_REVIEWED",
        "authority_class": AUTHORITY_CLASS,
        "expected_inventory_sha256": sha256(before).hexdigest(),
        "expected_review_state_sha256": expected_state_sha256,
        "next_inventory_sha256": sha256(after).hexdigest(),
        "next_review_state_sha256": next_state_sha256,
        "review_receipt_sha256": validated.receipt_sha256,
        "reviewed_assignment_sha256": validated.assignment_sha256,
        "terminal_allocation_status": promoted["status"],
        "schema": "ncp.b01-selector-allocation-review-transition.v1",
        "source_commit": validated.source_snapshot.source_cut["commit"],
        "source_tree": validated.source_snapshot.source_cut["tree"],
    }
    return ReviewTransitionPlan(
        action="PROMOTE_TO_REVIEWED",
        expected_inventory_bytes=before,
        next_inventory_bytes=after,
        expected_inventory_sha256=transition_subject["expected_inventory_sha256"],
        next_inventory_sha256=transition_subject["next_inventory_sha256"],
        expected_review_state=review_state,
        next_review_state=next_state,
        expected_review_state_sha256=expected_state_sha256,
        next_review_state_sha256=next_state_sha256,
        reviewed_assignment_sha256=validated.assignment_sha256,
        review_receipt_sha256=validated.receipt_sha256,
        source_cut=copy.deepcopy(validated.source_snapshot.source_cut),
        transition_subject_sha256=_transition_subject_sha256(transition_subject),
    )


def plan_review_reopen(
    inventory: dict[str, Any],
    inventory_schema: dict[str, Any],
    inventory_schema_raw: bytes,
    review_state: ReviewGenerationState,
    *,
    reason: str,
    source_cut: dict[str, Any],
) -> ReviewTransitionPlan:
    """Plan one atomic REVIEWED -> NOT_REVIEWED inventory/state transition."""

    review_state.validate()
    source_cut = _validate_source_cut_shape(source_cut)
    _require(
        review_state.current_receipt_sha256 is not None,
        "review reopen requires the active review receipt",
    )
    _require(
        isinstance(reason, str)
        and 0 < len(reason) <= MAX_REVIEW_REASON_CHARS
        and all(0x20 <= ord(character) <= 0x7E for character in reason),
        "review reopen reason must be bounded nonempty printable ASCII",
    )
    validate_allocation_inventory(inventory, inventory_schema)
    validate_allocation_review_profile_schema_binding(
        inventory,
        inventory_schema_raw,
    )
    assignment_sha256 = _assignment_sha256(inventory)
    exact_inventory_sha256 = sha256(inventory_bytes(inventory)).hexdigest()
    _require(
        inventory["provenance_review"]["status"] == "REVIEWED"
        and inventory["provenance_review"]["reviewed_assignment_sha256"]
        == assignment_sha256,
        "review reopen requires an exact REVIEWED assignment",
    )
    _require(
        review_state.active_assignment_sha256 == assignment_sha256
        and review_state.active_inventory_sha256 == exact_inventory_sha256,
        "review reopen state does not bind the exact active inventory assignment",
    )
    before = inventory_bytes(inventory)
    reopened = copy.deepcopy(inventory)
    reopened["provenance_review"]["status"] = "NOT_REVIEWED"
    reopened["provenance_review"]["reviewed_assignment_sha256"] = "0" * 64
    if reopened["status"] == "COMPLETE":
        reopened["status"] = "INCOMPLETE_FAIL_CLOSED"
    validate_allocation_inventory(reopened, inventory_schema)
    validate_allocation_review_profile_schema_binding(
        reopened,
        inventory_schema_raw,
    )
    after = inventory_bytes(reopened)
    next_state = _next_reopened_state(review_state)
    expected_state_sha256 = review_state.commitment()["sha256"]
    next_state_sha256 = next_state.commitment()["sha256"]
    receipt_sha256 = review_state.current_receipt_sha256
    reason_commitment = _content_commitment(
        {"reason": reason},
        domain=REVIEW_TRANSITION_DOMAIN,
    )["sha256"]
    transition_subject = {
        "action": "REOPEN_TO_NOT_REVIEWED",
        "authority_class": AUTHORITY_CLASS,
        "expected_inventory_sha256": sha256(before).hexdigest(),
        "expected_review_state_sha256": expected_state_sha256,
        "next_inventory_sha256": sha256(after).hexdigest(),
        "next_review_state_sha256": next_state_sha256,
        "reason_sha256": reason_commitment,
        "review_receipt_sha256": receipt_sha256,
        "reviewed_assignment_sha256": assignment_sha256,
        "schema": "ncp.b01-selector-allocation-review-transition.v1",
        "source_commit": source_cut["commit"],
        "source_tree": source_cut["tree"],
    }
    return ReviewTransitionPlan(
        action="REOPEN_TO_NOT_REVIEWED",
        expected_inventory_bytes=before,
        next_inventory_bytes=after,
        expected_inventory_sha256=transition_subject["expected_inventory_sha256"],
        next_inventory_sha256=transition_subject["next_inventory_sha256"],
        expected_review_state=review_state,
        next_review_state=next_state,
        expected_review_state_sha256=expected_state_sha256,
        next_review_state_sha256=next_state_sha256,
        reviewed_assignment_sha256=assignment_sha256,
        review_receipt_sha256=receipt_sha256,
        source_cut=copy.deepcopy(source_cut),
        transition_subject_sha256=_transition_subject_sha256(transition_subject),
    )


def _expect_rejection(action: Any, label: str) -> None:
    try:
        action()
    except (
        KeyError,
        OSError,
        SelectorAllocationReviewError,
        SelectorClosureCodecError,
        TypeError,
        UnicodeError,
    ):
        return
    _fail(f"review self-test accepted {label}")


def _write_fixture(path: Path, raw: bytes, *, executable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o755 if executable else 0o644,
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _replace_fixture(path: Path, raw: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_TRUNC)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _reseal_document(document: dict[str, Any]) -> None:
    manifest = document["authorization_manifest"]
    manifest_commitment = _content_commitment(
        manifest,
        domain=AUTHORIZATION_MANIFEST_DOMAIN,
    )
    document["authorization_manifest_commitment"] = manifest_commitment
    receipt = document["review_receipt"]
    receipt["authorization_manifest_byte_length"] = manifest_commitment["byte_length"]
    receipt["authorization_manifest_sha256"] = manifest_commitment["sha256"]
    document["review_receipt_commitment"] = _content_commitment(
        receipt,
        domain=REVIEW_RECEIPT_DOMAIN,
    )


def _git_fixture(repo: Path, *arguments: str) -> bytes:
    return _run_git(repo, *arguments, maximum_output_bytes=2 * 1024 * 1024)


def run_self_test() -> int:
    """Exercise tampering, replay, Git substitution, and atomic state cases."""

    from generate_selector_closure_source import (
        _default_incomplete_refresh_metrics,
        _recompute_closure_commitments,
        _sample_expanded_source,
        prepare_authoring_source,
    )
    from selector_resource_closure import derive_resource_closure

    schema_raw = read_bounded_regular_file(
        DEFAULT_REVIEW_DOCUMENT_SCHEMA,
        maximum_bytes=MAX_REVIEW_SCHEMA_BYTES,
        label="review self-test schema",
    )
    review_schema = _validate_review_schema_bytes(schema_raw)
    cases = 1
    _expect_rejection(
        lambda: _canonical_review_bytes(("tuple", "is", "not", "JSON")),
        "non-JSON tuple container",
    )
    _expect_rejection(
        lambda: _run_git(ROOT, "--version", maximum_output_bytes=-1),
        "negative Git output bound",
    )
    _expect_rejection(
        lambda: _run_git(
            ROOT,
            "--version",
            maximum_output_bytes=MAX_GIT_COMMAND_OUTPUT_BYTES + 1,
        ),
        "Git output bound above the global limit",
    )
    _expect_rejection(
        lambda: _run_git(ROOT, "--version", maximum_output_bytes=True),
        "boolean Git output bound",
    )
    _expect_rejection(
        lambda: _run_git(ROOT, "--version", standard_input=bytearray()),
        "non-bytes Git input",
    )
    _expect_rejection(
        lambda: _run_git(
            ROOT,
            "--version",
            standard_input=b"x" * (MAX_GIT_COMMAND_INPUT_BYTES + 1),
        ),
        "Git input above the global limit",
    )
    _expect_rejection(
        lambda: _run_git(ROOT, "--version", _timeout_seconds=0),
        "zero Git timeout",
    )
    impossible_state = ReviewGenerationState(
        state_version=100,
        next_review_generation=1,
        active_assignment_sha256=None,
        active_inventory_sha256=None,
        current_receipt_sha256=None,
        last_consumed_receipt_sha256=None,
        prior_state_sha256="0" * 64,
    )
    _expect_rejection(impossible_state.validate, "impossible review generation state")
    cases += 8

    def expect_git_rejection(
        action: Callable[[], bytes],
        message_fragment: str,
        label: str,
    ) -> None:
        try:
            action()
        except SelectorAllocationReviewError as error:
            _require(
                message_fragment in str(error),
                f"{label} produced the wrong failure: {error}",
            )
            return
        _fail(f"review self-test accepted {label}")

    git_environment = _clean_git_environment()
    _require(
        git_environment.get("GIT_NO_LAZY_FETCH") == "1"
        and git_environment.get("GIT_TERMINAL_PROMPT") == "0"
        and git_environment.get("GIT_OPTIONAL_LOCKS") == "0",
        "Git fail-closed environment changed",
    )
    cases += 1
    with tempfile.TemporaryDirectory(
        prefix="ncp-selector-allocation-fake-git-self-test-"
    ) as fake_directory_name:
        fake_directory = Path(fake_directory_name).resolve(strict=True)
        fake_bin = fake_directory / "bin"
        fake_bin.mkdir()
        fake_git = fake_bin / "git"
        fake_source = f"""#!{sys.executable}
import os
import sys
import time

def write_all(descriptor, value):
    offset = 0
    while offset < len(value):
        offset += os.write(descriptor, value[offset:])

mode = os.environ["NCP_FAKE_GIT_MODE"]
if mode == "exact":
    write_all(1, b"x" * 4096)
elif mode == "overflow":
    write_all(1, b"x" * 4097)
    time.sleep(5)
elif mode == "stderr-overflow":
    write_all(2, b"e" * 65537)
    time.sleep(5)
elif mode == "duplex":
    write_all(1, b"o" * 60000)
    write_all(2, b"e" * 60000)
    value = sys.stdin.buffer.read()
    if len(value) != 65536:
        raise SystemExit(9)
    write_all(1, b"done")
elif mode == "descendant":
    if os.fork() == 0:
        time.sleep(0.5)
        with open(os.environ["NCP_FAKE_GIT_SURVIVAL_PATH"], "xb") as handle:
            handle.write(b"survived")
        os._exit(0)
    os._exit(0)
elif mode == "nonzero-descendant":
    if os.fork() == 0:
        os.close(1)
        os.close(2)
        time.sleep(0.5)
        with open(os.environ["NCP_FAKE_GIT_SURVIVAL_PATH"], "xb") as handle:
            handle.write(b"survived")
        os._exit(0)
    os._exit(7)
else:
    raise SystemExit(8)
""".encode("utf-8")
        _write_fixture(fake_git, fake_source, executable=True)
        original_path = os.environ.get("PATH")
        original_mode = os.environ.get("NCP_FAKE_GIT_MODE")
        original_survival_path = os.environ.get("NCP_FAKE_GIT_SURVIVAL_PATH")
        survival_path = fake_directory / "descendant-survived"
        os.environ["PATH"] = (
            str(fake_bin)
            if original_path is None
            else f"{fake_bin}{os.pathsep}{original_path}"
        )
        os.environ["NCP_FAKE_GIT_SURVIVAL_PATH"] = str(survival_path)
        try:
            os.environ["NCP_FAKE_GIT_MODE"] = "exact"
            _require(
                _run_git(
                    ROOT,
                    "ignored",
                    maximum_output_bytes=4096,
                    _timeout_seconds=2,
                )
                == b"x" * 4096,
                "Git exact output bound changed",
            )
            os.environ["NCP_FAKE_GIT_MODE"] = "overflow"
            expect_git_rejection(
                lambda: _run_git(
                    ROOT,
                    "ignored",
                    maximum_output_bytes=4096,
                    _timeout_seconds=2,
                ),
                "output exceeds 4096 bytes",
                "Git stdout bound while producer is live",
            )
            os.environ["NCP_FAKE_GIT_MODE"] = "stderr-overflow"
            expect_git_rejection(
                lambda: _run_git(
                    ROOT,
                    "ignored",
                    maximum_output_bytes=1,
                    _timeout_seconds=2,
                ),
                f"error output exceeds {MAX_GIT_ERROR_BYTES} bytes",
                "Git stderr bound while producer is live",
            )
            os.environ["NCP_FAKE_GIT_MODE"] = "duplex"
            duplex_output = _run_git(
                ROOT,
                "ignored",
                maximum_output_bytes=64 * 1024,
                standard_input=b"i" * MAX_GIT_COMMAND_INPUT_BYTES,
                _timeout_seconds=2,
            )
            _require(
                duplex_output == b"o" * 60000 + b"done",
                "Git duplex pipe result changed",
            )
            os.environ["NCP_FAKE_GIT_MODE"] = "descendant"
            expect_git_rejection(
                lambda: _run_git(
                    ROOT,
                    "ignored",
                    maximum_output_bytes=1,
                    _timeout_seconds=0.1,
                ),
                "timed out",
                "Git descendant-held pipe timeout",
            )
            time.sleep(0.7)
            _require(
                not survival_path.exists(),
                "Git timeout left a descendant process alive",
            )
            nonzero_survival_path = fake_directory / "nonzero-descendant-survived"
            os.environ["NCP_FAKE_GIT_SURVIVAL_PATH"] = str(
                nonzero_survival_path
            )
            os.environ["NCP_FAKE_GIT_MODE"] = "nonzero-descendant"
            expect_git_rejection(
                lambda: _run_git(
                    ROOT,
                    "ignored",
                    maximum_output_bytes=1,
                    _timeout_seconds=2,
                ),
                "exit=7",
                "nonzero Git leader with a detached descendant",
            )
            time.sleep(0.7)
            _require(
                not nonzero_survival_path.exists(),
                "nonzero Git exit left a descendant process alive",
            )
        finally:
            if original_path is None:
                os.environ.pop("PATH", None)
            else:
                os.environ["PATH"] = original_path
            if original_mode is None:
                os.environ.pop("NCP_FAKE_GIT_MODE", None)
            else:
                os.environ["NCP_FAKE_GIT_MODE"] = original_mode
            if original_survival_path is None:
                os.environ.pop("NCP_FAKE_GIT_SURVIVAL_PATH", None)
            else:
                os.environ["NCP_FAKE_GIT_SURVIVAL_PATH"] = original_survival_path
        cases += 6
    with tempfile.TemporaryDirectory(
        prefix="ncp-selector-allocation-review-self-test-"
    ) as directory_name:
        repo = Path(directory_name).resolve(strict=True)
        _git_fixture(repo, "init", "-b", "main")
        _git_fixture(repo, "config", "user.name", "NCP Review Self Test")
        _git_fixture(repo, "config", "user.email", "review-self-test@example.invalid")

        allocation_schema_raw = (
            ROOT / "docs" / "adr" / "selector-allocation.authoring.schema.v1.json"
        ).read_bytes()
        allocation_schema = parse_json_bytes(
            allocation_schema_raw,
            label="review self-test allocation schema",
        )
        semantic_authoring_schema_raw = (
            ROOT / "docs" / "adr" / "selector-closure.authoring.schema.v1.json"
        ).read_bytes()
        semantic_authoring_schema = parse_json_bytes(
            semantic_authoring_schema_raw,
            label="review self-test semantic authoring schema",
        )
        bridge_profile_rule = semantic_authoring_schema["properties"][
            "observer_read_capture_bridge_profile"
        ]
        _require(
            isinstance(bridge_profile_rule, dict)
            and set(bridge_profile_rule) == {"const"}
            and isinstance(bridge_profile_rule["const"], dict),
            "review self-test requires one exact observer bridge profile",
        )
        expanded = _sample_expanded_source(
            allocation_schema_raw,
            observer_read_capture_bridge_profile=bridge_profile_rule["const"],
        )
        expanded["selectors"][0]["state_domains"][0]["states"] = []
        expanded["selectors"][0]["events"][0]["transition_kind"] = (
            "sample-transition-kind::SampleGenesis"
        )
        adr_fixture_bytes: dict[str, bytes] = {}
        for adr_index, document in enumerate(
            expanded["adr_allocation_oracle"]["documents"],
            1,
        ):
            main_role = f"adr_{adr_index:03d}_source"
            main_raw = f"# Review self-test source: {document['path']}\n".encode(
                "ascii"
            )
            adr_fixture_bytes[main_role] = main_raw
            document["byte_length"] = len(main_raw)
            document["sha256"] = sha256(main_raw).hexdigest()
            for module_index, module in enumerate(document["modules"], 1):
                module_role = f"adr_{adr_index:03d}_module_{module_index:03d}"
                module_raw = f"# Review self-test module: {module['path']}\n".encode(
                    "ascii"
                )
                adr_fixture_bytes[module_role] = module_raw
                module["byte_length"] = len(module_raw)
                module["sha256"] = sha256(module_raw).hexdigest()
            document["source_set"]["sha256"] = adr_source_set_sha256(
                adr_id=document["adr_id"],
                path=document["path"],
                byte_length=document["byte_length"],
                source_sha256=document["sha256"],
                modules=document["modules"],
            )
        _recompute_closure_commitments(expanded)
        (
            model_count,
            model_sha256,
            origin_signal_count,
            origin_signal_sha256,
            shape_count,
            shape_sha256,
        ) = _default_incomplete_refresh_metrics(expanded)
        _, resource_closure = derive_resource_closure(expanded)
        oracle = expanded["adr_allocation_oracle"]
        oracle["model_allocation_count"] = model_count
        oracle["model_allocation_sha256"] = model_sha256
        oracle["semantic_shape_entry_count"] = shape_count
        oracle["semantic_shape_sha256"] = shape_sha256
        oracle["allocation_review_profile"] = build_allocation_review_profile(
            allocation_schema_raw=allocation_schema_raw,
            model_allocation_count=model_count,
            model_allocation_sha256=model_sha256,
            model_origin_signal_row_count=origin_signal_count,
            model_origin_signal_sha256=origin_signal_sha256,
            resource_closure_row_count=resource_closure["row_count"],
            resource_closure_sha256=resource_closure["sha256"],
            semantic_shape_entry_count=shape_count,
            semantic_shape_sha256=shape_sha256,
        )
        oracle["semantic_review_subject"] = semantic_review_subject_commitment(expanded)
        _recompute_closure_commitments(expanded)
        sample = oracle_to_inventory(copy.deepcopy(expanded["adr_allocation_oracle"]))
        validate_allocation_inventory(sample, allocation_schema)
        _validate_derived_review_profile(sample, expanded)
        stale_profile = copy.deepcopy(sample)
        stale_profile["allocation_review_profile"]["model_allocation_sha256"] = "f" * 64
        _expect_rejection(
            lambda: _validate_derived_review_profile(stale_profile, expanded),
            "self-asserted review profile digest",
        )
        cases += 1
        nonportable_assignment = copy.deepcopy(sample)
        nonportable_assignment["exclusions"] = [
            {
                "adr_id": "ADR-001",
                "classification": "MODEL_OMISSION_FAIL_CLOSED",
                "exact_name": "NonportableAssignment",
                "reason": "non-ASCII \N{SNOWMAN}",
                "source_anchor": "ncp-b01-selector-allocation-adr-001-v1",
            }
        ]
        _expect_rejection(
            lambda: _assignment_sha256(nonportable_assignment),
            "non-ASCII assignment scalar",
        )
        unsafe_integer_assignment = copy.deepcopy(sample)
        unsafe_integer_assignment["allocation_review_profile"][
            "model_allocation_count"
        ] = MAX_SAFE_INTEGER + 1
        _expect_rejection(
            lambda: _assignment_sha256(unsafe_integer_assignment),
            "unsafe-integer assignment scalar",
        )
        cases += 2
        compact_raw = serialize_compact_source(expanded)
        allocation_raw = inventory_bytes(sample)
        allocation_binding = build_inventory_binding(
            allocation_raw,
            allocation_schema_raw,
        )
        authoring_raw = (
            canonical_bytes(prepare_authoring_source(expanded, allocation_binding))
            + b"\n"
        )

        fixture_bytes = {
            "allocation_inventory": allocation_raw,
            "allocation_schema": allocation_schema_raw,
            "semantic_authoring_source": authoring_raw,
            "semantic_authoring_schema": semantic_authoring_schema_raw,
            "semantic_compact_source": compact_raw,
            "semantic_compact_schema": (
                ROOT / "docs" / "adr" / "selector-closure.source.schema.v1.json"
            ).read_bytes(),
            "allocation_boundary_implementation": (
                ROOT / "scripts" / "selector_allocation_inventory.py"
            ).read_bytes(),
            "semantic_generator": (
                ROOT / "scripts" / "generate_selector_closure_source.py"
            ).read_bytes(),
            "semantic_checker": (
                ROOT / "scripts" / "check_selector_closure.py"
            ).read_bytes(),
            "semantic_codec": (
                ROOT / "scripts" / "selector_closure_codec.py"
            ).read_bytes(),
            "resource_closure_projection": (
                ROOT / "scripts" / "selector_resource_closure.py"
            ).read_bytes(),
            "review_boundary_implementation": Path(__file__).read_bytes(),
            "review_generation_state": review_state_bytes(
                ReviewGenerationState.genesis()
            ),
            "review_generation_state_schema": (
                ROOT
                / "docs"
                / "adr"
                / "selector-allocation.review-state.schema.v1.json"
            ).read_bytes(),
            "review_document_schema": schema_raw,
        }
        fixture_bytes.update(adr_fixture_bytes)
        for role, path, _maximum_bytes in REQUIRED_SOURCE_ROLES:
            _write_fixture(
                repo / path,
                fixture_bytes[role],
                executable=role.endswith("implementation")
                or role in {"semantic_generator", "semantic_checker"},
            )
        _git_fixture(repo, "add", "--all")
        _git_fixture(
            repo,
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-m",
            "Create exact review self-test source",
        )
        source_commit = (
            _git_fixture(
                repo,
                "rev-parse",
                "HEAD",
            )
            .decode("ascii")
            .strip()
        )
        _expect_rejection(
            lambda: _run_git(
                repo,
                "show",
                f"{source_commit}:docs/adr/selector-closure.authoring.v1.json",
                maximum_output_bytes=32,
            ),
            "Git stdout enforcement-time bound",
        )
        cases += 1

        policy = ReviewAuthorityPolicy(
            repository="sepahead/NCP",
            branch="main",
            authorization_issuer_identity="owner@example.invalid",
            reviewer_identity="reviewer@example.invalid",
            reviewer_role=REVIEWER_ROLE,
            implementation_owner_identities=("owner@example.invalid",),
        )
        state = ReviewGenerationState.genesis()
        document = build_review_document(
            repo,
            source_commit,
            policy,
            state,
            authorization_id="11111111-1111-4111-8111-111111111111",
            review_id="22222222-2222-4222-8222-222222222222",
        )
        validation = validate_review_document(
            repo,
            document,
            policy,
            state,
            require_current_clean_head=True,
        )
        _expect_rejection(
            lambda: validate_review_document(
                repo,
                document,
                policy,
                state,
                require_current_clean_head=False,
            ),
            "clean current-HEAD authority bypass",
        )
        duplicate_schema_role = copy.deepcopy(document)
        duplicate_schema_role["authorization_manifest"]["source_cut"]["blobs"][1] = (
            copy.deepcopy(
                duplicate_schema_role["authorization_manifest"]["source_cut"]["blobs"][
                    0
                ]
            )
        )
        _expect_rejection(
            lambda: _validate_review_schema_instance(
                duplicate_schema_role,
                review_schema,
            ),
            "schema-level source role and path substitution",
        )
        oversized_schema_role = copy.deepcopy(document)
        oversized_schema_role["authorization_manifest"]["source_cut"]["blobs"][0][
            "byte_length"
        ] = REQUIRED_SOURCE_ROLE_LIMITS["allocation_inventory"] + 1
        _expect_rejection(
            lambda: _validate_review_schema_instance(
                oversized_schema_role,
                review_schema,
            ),
            "schema-level per-role byte-limit bypass",
        )
        wrong_oid_width = copy.deepcopy(document)
        object_format = wrong_oid_width["authorization_manifest"]["source_cut"][
            "object_format"
        ]
        wrong_oid_width["authorization_manifest"]["source_cut"]["commit"] = "0" * (
            64 if object_format == "sha1" else 40
        )
        _expect_rejection(
            lambda: _validate_review_schema_instance(
                wrong_oid_width,
                review_schema,
            ),
            "schema-level object-format OID-width mismatch",
        )
        _require(
            validation.assignment_sha256 == _assignment_sha256(sample),
            "review self-test changed the assignment digest",
        )
        cases += 6

        canonical = review_document_bytes(document)
        document_path = repo.parent / f"{repo.name}-review-document.json"
        _write_fixture(document_path, canonical)
        _require(
            load_review_document(document_path) == document,
            "canonical review document did not round trip",
        )
        document_path.unlink()
        cases += 1

        promotion = plan_review_promotion(repo, document, policy, state)
        promoted_inventory = parse_json_bytes(
            promotion.next_inventory_bytes,
            label="promoted review self-test inventory",
        )
        _require(
            promoted_inventory["provenance_review"]["status"] == "REVIEWED"
            and promoted_inventory["provenance_review"]["reviewed_assignment_sha256"]
            == validation.assignment_sha256
            and promoted_inventory["status"] == "INCOMPLETE_FAIL_CLOSED"
            and promotion.next_review_state.active_assignment_sha256
            == validation.assignment_sha256
            and promotion.next_review_state.active_inventory_sha256
            == sha256(promotion.next_inventory_bytes).hexdigest(),
            "review promotion did not install the exact reviewed assignment",
        )
        active_validation = validate_active_review_for_reopen(
            repo,
            document,
            policy,
            promotion.next_review_state,
            promoted_inventory,
        )
        _require(
            active_validation.receipt_sha256 == promotion.review_receipt_sha256,
            "active review validation changed the exact receipt",
        )
        wrong_inventory_state = ReviewGenerationState(
            state_version=promotion.next_review_state.state_version,
            next_review_generation=(promotion.next_review_state.next_review_generation),
            active_assignment_sha256=(
                promotion.next_review_state.active_assignment_sha256
            ),
            active_inventory_sha256="f" * 64,
            current_receipt_sha256=(promotion.next_review_state.current_receipt_sha256),
            last_consumed_receipt_sha256=(
                promotion.next_review_state.last_consumed_receipt_sha256
            ),
            prior_state_sha256=promotion.next_review_state.prior_state_sha256,
        )
        wrong_inventory_state.validate()
        _expect_rejection(
            lambda: plan_review_reopen(
                promoted_inventory,
                allocation_schema,
                allocation_schema_raw,
                wrong_inventory_state,
                reason="reject substituted active inventory state",
                source_cut=document["authorization_manifest"]["source_cut"],
            ),
            "active state bound to a different reviewed inventory",
        )
        cases += 3

        sibling_document = build_review_document(
            repo,
            source_commit,
            policy,
            state,
            authorization_id="33333333-3333-4333-8333-333333333333",
            review_id="44444444-4444-4444-8444-444444444444",
        )
        sibling_promotion = plan_review_promotion(
            repo,
            sibling_document,
            policy,
            state,
        )
        _require(
            sibling_promotion.expected_inventory_sha256
            == promotion.expected_inventory_sha256
            and sibling_promotion.expected_review_state_sha256
            == promotion.expected_review_state_sha256
            and sibling_promotion.next_inventory_sha256
            == promotion.next_inventory_sha256
            and sibling_promotion.review_receipt_sha256
            != promotion.review_receipt_sha256
            and sibling_promotion.next_review_state_sha256
            != promotion.next_review_state_sha256,
            "same-predecessor review plans do not expose one state-CAS winner",
        )
        _expect_rejection(
            lambda: validate_active_review_for_reopen(
                repo,
                sibling_document,
                policy,
                promotion.next_review_state,
                promoted_inventory,
            ),
            "sibling receipt substituted for the active review document",
        )
        nonexistent_source = copy.deepcopy(document)
        nonexistent_source["authorization_manifest"]["source_cut"]["commit"] = (
            "f"
            * len(nonexistent_source["authorization_manifest"]["source_cut"]["commit"])
        )
        _reseal_document(nonexistent_source)
        _expect_rejection(
            lambda: validate_active_review_for_reopen(
                repo,
                nonexistent_source,
                policy,
                promotion.next_review_state,
                promoted_inventory,
            ),
            "active review document with a nonexistent Git commit",
        )
        cases += 3

        _expect_rejection(
            lambda: plan_review_promotion(
                repo,
                document,
                policy,
                promotion.next_review_state,
            ),
            "direct review receipt replay",
        )
        reopened = plan_review_reopen(
            promoted_inventory,
            allocation_schema,
            allocation_schema_raw,
            promotion.next_review_state,
            reason="semantic source will change",
            source_cut=document["authorization_manifest"]["source_cut"],
        )
        reopened_inventory = parse_json_bytes(
            reopened.next_inventory_bytes,
            label="reopened review self-test inventory",
        )
        _require(
            reopened_inventory["provenance_review"]["status"] == "NOT_REVIEWED"
            and reopened.next_review_state.next_review_generation == 2,
            "review reopen did not invalidate and advance the generation",
        )
        _expect_rejection(
            lambda: plan_review_promotion(
                repo,
                document,
                policy,
                reopened.next_review_state,
            ),
            "review receipt replay after reopen",
        )
        cases += 3

        wrong_digest = copy.deepcopy(document)
        wrong_digest["authorization_manifest"]["review_subject"][
            "provenance_assignment_sha256"
        ] = "f" * 64
        wrong_digest["review_receipt"]["reviewed_assignment_sha256"] = "f" * 64
        _reseal_document(wrong_digest)
        _expect_rejection(
            lambda: validate_review_document(
                repo,
                wrong_digest,
                policy,
                state,
                require_current_clean_head=True,
            ),
            "re-sealed wrong assignment digest",
        )
        cases += 1

        substituted_path = copy.deepcopy(document)
        substituted_path["authorization_manifest"]["source_cut"]["blobs"][0]["path"] = (
            ":(top)docs/adr/selector-allocation.authoring.v1.json"
        )
        _reseal_document(substituted_path)
        _expect_rejection(
            lambda: validate_review_document(
                repo,
                substituted_path,
                policy,
                state,
                require_current_clean_head=True,
            ),
            "Git pathspec injection",
        )
        cases += 1

        injected_ref = copy.deepcopy(document)
        injected_ref["authorization_manifest"]["source_cut"]["commit"] = "HEAD^{tree}"
        _reseal_document(injected_ref)
        _expect_rejection(
            lambda: validate_review_document(
                repo,
                injected_ref,
                policy,
                state,
                require_current_clean_head=True,
            ),
            "Git revision injection",
        )
        cases += 1

        substituted_source = copy.deepcopy(document)
        substituted_source["authorization_manifest"]["source_cut"]["tree"] = "0" * 40
        _reseal_document(substituted_source)
        _expect_rejection(
            lambda: validate_review_document(
                repo,
                substituted_source,
                policy,
                state,
                require_current_clean_head=True,
            ),
            "source tree substitution",
        )
        cases += 1

        tampered_reviewer = copy.deepcopy(document)
        tampered_reviewer["authorization_manifest"]["reviewer_authorization"][
            "reviewer_identity"
        ] = "attacker@example.invalid"
        tampered_reviewer["review_receipt"]["reviewer_identity"] = (
            "attacker@example.invalid"
        )
        _reseal_document(tampered_reviewer)
        _expect_rejection(
            lambda: validate_review_document(
                repo,
                tampered_reviewer,
                policy,
                state,
                require_current_clean_head=True,
            ),
            "re-sealed reviewer identity tampering",
        )
        cases += 1

        tampered_role = copy.deepcopy(document)
        tampered_role["authorization_manifest"]["reviewer_authorization"][
            "reviewer_role"
        ] = "RELEASE_AUTHORITY"
        tampered_role["review_receipt"]["reviewer_role"] = "RELEASE_AUTHORITY"
        _reseal_document(tampered_role)
        _expect_rejection(
            lambda: validate_review_document(
                repo,
                tampered_role,
                policy,
                state,
                require_current_clean_head=True,
            ),
            "re-sealed reviewer role tampering",
        )
        cases += 1

        tampered_assignment_suite = copy.deepcopy(document)
        tampered_assignment_suite["authorization_manifest"]["review_subject"][
            "assignment_commitment_suite"
        ]["row_ordering"] = "REVERSE_ORDER"
        _reseal_document(tampered_assignment_suite)
        _expect_rejection(
            lambda: validate_review_document(
                repo,
                tampered_assignment_suite,
                policy,
                state,
                require_current_clean_head=True,
            ),
            "re-sealed assignment commitment suite tampering",
        )
        cases += 1

        compact_path = repo / REQUIRED_SOURCE_ROLE_PATHS["semantic_compact_source"]
        altered_expanded = copy.deepcopy(expanded)
        altered_expanded["selectors"][0]["selector_id"] = "MUTATED_SELECTOR"
        _replace_fixture(compact_path, serialize_compact_source(altered_expanded))
        _expect_rejection(
            lambda: plan_review_promotion(repo, document, policy, state),
            "uncommitted semantic scalar mutation",
        )
        _replace_fixture(compact_path, compact_raw)
        cases += 1

        schema_path = repo / REQUIRED_SOURCE_ROLE_PATHS["allocation_schema"]
        _replace_fixture(schema_path, allocation_schema_raw + b" ")
        _expect_rejection(
            lambda: plan_review_promotion(repo, document, policy, state),
            "allocation schema byte substitution",
        )
        _replace_fixture(schema_path, allocation_schema_raw)
        cases += 1

        checker_path = repo / REQUIRED_SOURCE_ROLE_PATHS["semantic_checker"]
        checker_raw = checker_path.read_bytes()
        _replace_fixture(checker_path, checker_raw + b"# dirty substitution\n")
        _expect_rejection(
            lambda: plan_review_promotion(repo, document, policy, state),
            "dirty reviewed-source substitution",
        )
        _replace_fixture(checker_path, checker_raw)
        cases += 1

        adr_path = repo / REQUIRED_SOURCE_ROLE_PATHS["adr_004_source"]
        adr_raw = adr_path.read_bytes()
        _replace_fixture(adr_path, adr_raw + b"# substituted review source\n")
        _expect_rejection(
            lambda: plan_review_promotion(repo, document, policy, state),
            "reviewed ADR source substitution",
        )
        _replace_fixture(adr_path, adr_raw)
        cases += 1

        unrelated = repo / "unrelated-untracked"
        _write_fixture(unrelated, b"dirty\n")
        _expect_rejection(
            lambda: plan_review_promotion(repo, document, policy, state),
            "untracked worktree substitution",
        )
        unrelated.unlink()
        cases += 1

        noncanonical_path = repo.parent / f"{repo.name}-noncanonical-review.json"
        _write_fixture(
            noncanonical_path,
            json.dumps(document, indent=2, sort_keys=True).encode("ascii") + b"\n",
        )
        _expect_rejection(
            lambda: load_review_document(noncanonical_path),
            "noncanonical review document",
        )
        noncanonical_path.unlink()
        cases += 1

        unsafe_policy = ReviewAuthorityPolicy(
            repository=policy.repository,
            branch="main^{tree}",
            authorization_issuer_identity=policy.authorization_issuer_identity,
            reviewer_identity=policy.reviewer_identity,
            reviewer_role=policy.reviewer_role,
            implementation_owner_identities=policy.implementation_owner_identities,
        )
        _expect_rejection(unsafe_policy.validate, "unsafe policy branch")
        for unsafe_repository in (
            "sepahead//NCP",
            "sepahead/./NCP",
            "sepahead/NCP/.",
        ):
            unsafe_repository_policy = ReviewAuthorityPolicy(
                repository=unsafe_repository,
                branch=policy.branch,
                authorization_issuer_identity=(policy.authorization_issuer_identity),
                reviewer_identity=policy.reviewer_identity,
                reviewer_role=policy.reviewer_role,
                implementation_owner_identities=(
                    policy.implementation_owner_identities
                ),
            )
            _expect_rejection(
                unsafe_repository_policy.validate,
                f"noncanonical policy repository {unsafe_repository!r}",
            )
        self_review_policy = ReviewAuthorityPolicy(
            repository=policy.repository,
            branch=policy.branch,
            authorization_issuer_identity=policy.authorization_issuer_identity,
            reviewer_identity=policy.authorization_issuer_identity,
            reviewer_role=policy.reviewer_role,
            implementation_owner_identities=policy.implementation_owner_identities,
        )
        _expect_rejection(self_review_policy.validate, "implementation-owner review")
        cases += 5

    return cases


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run hostile local review-boundary tests",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.self_test:
            cases = run_self_test()
            print(
                "selector allocation review self-test: PASS "
                f"cases={cases} authority={AUTHORITY_CLASS} "
                "external=NOT_AUTHORIZED independent=NOT_AUTHORIZED "
                "release=NOT_AUTHORIZED"
            )
            return 0
        print(
            "selector allocation review: FAIL: use --self-test or import the "
            "issue/validate/transition APIs",
            file=sys.stderr,
        )
        return 2
    except (
        KeyError,
        OSError,
        SelectorAllocationReviewError,
        SelectorClosureCodecError,
        TypeError,
        UnicodeError,
    ) as error:
        print(f"selector allocation review: FAIL: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
