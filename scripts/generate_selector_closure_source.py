#!/usr/bin/env python3
"""Generate the compact B01 selector source from its expanded authoring source."""

from __future__ import annotations

import argparse
import base64
import binascii
import copy
import fcntl
import os
import re
import shutil
import stat
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, NoReturn

from selector_allocation_inventory import (
    ADR_ALLOCATION_ANCHOR_IDS,
    ADR_ALLOCATION_MODULE_PATHS,
    ADR_ALLOCATION_PATHS,
    ADR_SOURCE_SET_SUITE,
    ALLOCATION_BINDING_KEY,
    ALLOCATION_KINDS,
    ALLOCATION_ORACLE_KEY,
    ALLOCATION_REVIEW_PROFILE_SCHEMA,
    DOCUMENT_ROW_COMMITMENT,
    INVENTORY_CLAIM_BOUNDARY,
    INVENTORY_FILE,
    INVENTORY_SCHEMA_FILE,
    MAX_ADR_DOCUMENT_BYTES,
    MAX_ALLOCATION_INVENTORY_BYTES,
    MAX_ALLOCATION_SCHEMA_BYTES,
    AllocationInventorySnapshot,
    SelectorAllocationInventoryError,
    adr_source_set_sha256,
    allocation_identity_projection,
    allocation_unit_id,
    build_allocation_review_profile,
    build_inventory_binding,
    build_not_reviewed_provenance_review,
    document_rows_sha256,
    inventory_bytes,
    inventory_to_oracle,
    load_bound_allocation_inventory,
    load_inventory_schema,
    model_allocation_projection_sha256,
    oracle_to_inventory,
    provenance_assignment_sha256,
    semantic_review_subject_commitment,
    validate_allocation_inventory,
    validate_allocation_review_profile_schema_binding,
    validate_inventory_binding,
    verify_inventory_snapshot_unchanged,
)
from selector_closure_codec import (
    MAX_COMPACT_BYTES,
    MAX_EXPANDED_BYTES,
    AtomicWriteOutcomeUnknownError,
    SelectorClosureCodecError,
    _atomic_write_regular_file,
    _read_bounded_regular_file,
    atomic_write_regular_file,
    canonical_bytes,
    canonical_sha256,
    load_compact_source,
    parse_json_bytes,
    read_bounded_regular_file,
    run_codec_self_test,
    serialize_compact_source,
)
from selector_resource_closure import derive_resource_closure

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_AUTHORING = ROOT / "docs" / "adr" / "selector-closure.authoring.v1.json"
DEFAULT_AUTHORING_SCHEMA = (
    ROOT / "docs" / "adr" / "selector-closure.authoring.schema.v1.json"
)
DEFAULT_OUTPUT = ROOT / "docs" / "adr" / "selector-closure.source.v1.json"

MAX_AUTHORING_SCHEMA_BYTES = 128 * 1024
MAX_COMPACT_SCHEMA_BYTES = 64 * 1024
AUTHORING_SCHEMA_FILE = "selector-closure.authoring.schema.v1.json"
AUTHORING_SCHEMA_ID = "ncp.b01-selector-closure-authoring.v1"
AUTHORING_SCHEMA_URL = (
    "https://sepahead.github.io/ncp/schemas/b01-selector-closure-authoring.v1.json"
)
AUTHORING_SCHEMA_SHA256 = (
    "68dd4c810e7020db636b4610d7cc7c86ceaaada40d96d0142cdb9b9ebf215ef3"
)
CANONICAL_SOURCE_SCHEMA_FILE = "selector-closure.source.schema.v1.json"
CANONICAL_SOURCE_SCHEMA_ID = "ncp.b01-selector-closure-source.v1"
COMPACT_SCHEMA_URL = (
    "https://sepahead.github.io/ncp/schemas/b01-selector-closure-source.compact.v1.json"
)
COMPACT_SCHEMA_SHA256 = (
    "049d9b313664d42c98f6b3c471284766d2670187f23bc19f650181d8294ed930"
)
CANONICAL_GENERATOR = "scripts/generate_selector_closure_source.py"
MATERIALIZATION_GENERATOR = (
    "scripts/generate_selector_closure_source.py --materialize-from-compact"
)
CANONICAL_SOURCE_METADATA_KEY = "canonical_source_metadata"
CANONICAL_SOURCE_METADATA_KEYS = {
    "$schema",
    "generated_by",
    "schema",
}

REVIEW_CONTROL_SCHEMA = "ncp.b01-selector-allocation-review-control.v2"
REVIEW_OPEN_SOURCE_REANCHOR_SCHEMA = (
    "ncp.b01-selector-allocation-open-source-reanchor.v1"
)
REVIEW_CONTROL_FILE = "ncp-selector-allocation-review-control.v1.json"
REVIEW_CONTROL_LOCK_FILE = "ncp-selector-allocation-review-control.lock"
REVIEW_CONTROL_CLAIM_BOUNDARY = (
    "LOCAL_PER_WORKTREE_ACCIDENTAL_ROLLBACK_AND_CRASH_RECOVERY_CONTROL_ONLY_"
    "REQUIRES_STABLE_GIT_PRIVATE_ANCESTOR_PATH_"
    "NO_EVIDENCE_AUTHENTICATION_TAMPER_RESISTANCE_OR_AUTHORITY"
)
# A pending journal carries both sides of all four bounded file transitions.
# This makes fail-closed recovery independent of mutable worktree bytes and of
# later Git-object availability. The raw artifacts can total just over 48 MiB;
# canonical base64 framing needs a correspondingly explicit upper bound.
MAX_REVIEW_CONTROL_BYTES = 66 * 1024 * 1024
MAX_REVIEW_CONTROL_JSON_DEPTH = 32
MAX_REVIEW_CONTROL_JSON_ITEMS = 16_384

# This one-use bridge pins the complete maintained v1 profile, rather than
# admitting a schema-name range.  The v2 successor is deliberately not copied
# here: it comes only from the exact const in the current authoring schema.
OBSERVER_BRIDGE_PROFILE_KEY = "observer_read_capture_bridge_profile"
ADVERSARIAL_PROBE_BINDINGS_KEY = "adversarial_probe_bindings"
BRIDGE_V1_MIGRATION_PROFILE_SCHEMA = "ncp.b01-observer-read-capture-bridge-profile.v1"
BRIDGE_V2_MIGRATION_PROFILE_SCHEMA = "ncp.b01-observer-read-capture-bridge-profile.v2"
BRIDGE_V1_MIGRATION_PROFILE_CANONICAL_BYTE_LENGTH = 2_334
BRIDGE_V1_MIGRATION_PROFILE_CANONICAL_SHA256 = (
    "7628f6e560622cf13f3ba29effa12a234c921a301255ebf4fd9f99f1981de7f8"
)
BRIDGE_V2_MIGRATION_PROFILE_CANONICAL_BYTE_LENGTH = 38_358
BRIDGE_V2_MIGRATION_PROFILE_CANONICAL_SHA256 = (
    "77469e4604f38f811c61b9c7a4abd5227990e815387a27a3f7556215eb6b75c1"
)
BRIDGE_V2_MIGRATION_PROFILE_DIGEST_DOMAIN = (
    "ncp.b01.bridge.ObserverReadCaptureBridgeProfileV2@1"
)
BRIDGE_V2_MIGRATION_PROFILE_DIGEST = (
    "4226b60f52d799e36be6446d1069ed0d79efe910895f1ba6301ba949a49ded0a"
)
BRIDGE_V2_MIGRATION_PROFILE_NORMALIZED_BYTE_LENGTH = 45_379
BRIDGE_V2_MIGRATION_PROFILE_NORMALIZED_SHA256 = (
    "7ddae8d9171ecd53d8306886d9ccbd9cdac2b5f2cda6578ddb00d4ffa3c7d56e"
)
BRIDGE_V2_COMMITMENT_SUITE_SCHEMA = "ncp.b01.bridge-canonical-commitment-suite.v1"
BRIDGE_V2_COMMITMENT_SUITE_CANONICAL_BYTE_LENGTH = 21_987
BRIDGE_V2_COMMITMENT_SUITE_CANONICAL_SHA256 = (
    "b61cdc4657245335240b5a95362fd6942fbbce4cab824e3d0a0e65d4ddce37f0"
)
BRIDGE_V2_COMMITMENT_SUITE_DIGEST_DOMAIN = "ncp.b01.bridge.CanonicalCommitmentSuite@1"
BRIDGE_V2_COMMITMENT_SUITE_DIGEST = (
    "92b1843fefd907cf30a1cfceb7fa251e2eb1ba46f3f47a68af4dfcf8d7608cf9"
)
BRIDGE_V2_COMMITMENT_SUITE_NORMALIZED_BYTE_LENGTH = 26_972
BRIDGE_V2_COMMITMENT_SUITE_NORMALIZED_SHA256 = (
    "fd4b60114ef7b365da5d49ac00af52bdde044148affdcde7b815bfa4b55ce4b2"
)
BRIDGE_V2_COMMITMENT_FRAME_PREFIX = b"NCP-B01-OBSERVER-READ-CAPTURE-BRIDGE-V1"
BRIDGE_V1_MIGRATION_PROFILE = {
    "authority_chain": [
        "LIVE_READ_CAPABILITY",
        "SEALED_NONAUTHORIZING_READ_DECISION",
        "LOCAL_RELEASE_AUTHORITY_RECHECK",
        "EXACT_DELIVERY",
        "LOCAL_IMMUTABLE_ADMISSION",
        "DETERMINISTIC_SEMANTIC_EXTRACTION",
    ],
    "authorization": {
        "capability_authority": "BOUNDED_CURRENT_READ_AUTHORITY_ONLY",
        "decision_authority_effect": "PREFLIGHT_ONLY_RELEASE_RECHECK_REQUIRED",
        "decision_seal_evidence": (
            "SYNTHETIC_PROBE_ONLY_NOT_CRYPTOGRAPHIC_QUALIFICATION"
        ),
        "release_recheck": (
            "EXACT_CURRENT_PRINCIPAL_CONNECTION_SESSION_SECURITY_REVOCATION_"
            "MANIFEST_SCOPE_AND_MEMBERSHIP"
        ),
    },
    "claim_boundary": (
        "NON_NORMATIVE_B01_ARCHITECTURE_PROFILE_NOT_WIRE_RELEASE_EXTERNAL_"
        "INDEPENDENT_INTEROPERABILITY_OR_CONSUMER_QUALIFICATION_EVIDENCE"
    ),
    "delivery_admission": {
        "admission_is_immutable_historical_evidence": True,
        "capsule_future_read_authority": False,
        "delivery_binds": [
            "VERIFIED_TRANSPORT_PRINCIPAL",
            "LIVE_CONNECTION",
            "REPLAY_DOMAIN",
            "SESSION_GENERATION",
            "SECURITY_STATE_AND_EPOCH",
            "REVOCATION_EPOCH",
            "DEFAULT_DENY_MANIFEST",
            "CANONICAL_READ_SCOPE",
            "BOUNDARY_SCOPE_MEMBERSHIP",
            "GRANT_ENTITLEMENT_DIGESTS",
            "PAYLOAD_DIGEST",
        ],
        "security_cut_rule": (
            "ADMITTED_BEFORE_CUT_REMAINS_HISTORICAL_WITHOUT_FUTURE_READ_AUTHORITY"
        ),
    },
    "exact_type_refs": {
        "admission_capsule": (
            "delivered-admission-evidence-capsule-type::"
            "DeliveredAdmissionEvidenceCapsule"
        ),
        "boundary_membership": (
            "observer-boundary-read-scope-membership-type::"
            "ObserverBoundaryReadScopeMembership"
        ),
        "canonical_scope": (
            "canonical-observer-read-scope-type::CanonicalObserverReadScope"
        ),
        "extraction_contract": (
            "deterministic-extraction-contract-type::DeterministicExtractionContract"
        ),
        "extraction_receipt": (
            "deterministic-extraction-receipt-type::DeterministicExtractionReceipt"
        ),
        "sealed_decision": (
            "sealed-observer-read-authorization-decision-type::"
            "SealedObserverReadAuthorizationDecision"
        ),
    },
    "route_classes": {
        "additional_closed_disposition": ["OBSERVATION_COMMAND_DISPOSITION"],
        "current_prisoma_delivery": [
            "ACTION_COMMAND_PROPOSAL",
            "OBSERVATION_FRAME",
            "PERCEPTION_PROJECTED_OBSERVATION",
            "PERCEPTION_SENSOR_FRAME",
        ],
    },
    "schema": BRIDGE_V1_MIGRATION_PROFILE_SCHEMA,
    "semantic_extraction": {
        "axis_members": {
            "A": ["a0"],
            "D": ["d_left", "d_right"],
            "L": ["l0"],
            "V": ["v0"],
        },
        "deterministic_receipt_count": 7,
        "replay": "REQUIRED_FOR_EACH_SEMANTIC_MEMBER_SAMPLE",
        "source": "RETAINED_ADMITTED_PAYLOAD_BYTES",
    },
    "unknown_default_missing_duplicate_or_substituted": "REJECT",
}

BRIDGE_V1_MIGRATION_PROBE_BINDINGS = {
    "claim_boundary": (
        "LOCAL_DETERMINISTIC_MODEL_EVIDENCE_ONLY_NOT_EXTERNAL_"
        "QUALIFICATION_CERTIFICATION_RELEASE_OR_PRODUCTION_EVIDENCE"
    ),
    "freshness_acceptance_probe": {
        "command": (
            "python3 prototypes/b01-architecture-evidence/freshness_acceptance_probe.py"
        ),
        "dependency_ids": [],
        "script_sha256": (
            "eeec3a61fd576cca23045ce577a257bc78be8d7058c19bd9f44e353ba77f7335"
        ),
        "stdout_sha256": (
            "ffa3517f2fba19b506d3eaf5db87bd9ee20b8510c66c5aac31cfe4853cb629dc"
        ),
    },
    "observer_authorization_probe": {
        "command": (
            "python3 prototypes/b01-architecture-evidence/"
            "observer_authorization_probe.py"
        ),
        "dependency_ids": ["observer_read_capture_bridge"],
        "script_sha256": (
            "5df72071a05d7bebc6f3768467866c5a2dd470c34958e5580093b98854ac4e12"
        ),
        "stdout_sha256": (
            "98c65dc58e80ca4f5d0b438cdcac2dcc4990c2e1373a5e4b63df4a815112b6bb"
        ),
    },
    "observer_capture_probe": {
        "command": (
            "python3 prototypes/b01-architecture-evidence/observer_capture_probe.py"
        ),
        "dependency_ids": ["observer_read_capture_bridge"],
        "script_sha256": (
            "53da9233f5d0b71dca86cdc5888d25e8c8a3e1d5526eef3317fc083ec16b67b2"
        ),
        "stdout_sha256": (
            "544e8e3dacd0b86bd6ecbe9e3d1a4da373e8794dccda8f864d496bc29c4cfdd1"
        ),
    },
    "shared_source_bindings": {
        "observer_read_capture_bridge": {
            "byte_length": 16_990,
            "module": "observer_read_capture_bridge",
            "path": (
                "prototypes/b01-architecture-evidence/observer_read_capture_bridge.py"
            ),
            "sha256": (
                "6ff1ec833c5b879de16aa1b9d031f6699c523478c13381690d5c279933d57f3b"
            ),
        }
    },
    "source_issuance_index_probe": {
        "command": (
            "python3 prototypes/b01-architecture-evidence/"
            "source_issuance_index_probe.py"
        ),
        "dependency_ids": [],
        "script_sha256": (
            "15c88f8def8323fc3465991a33b719ed951d8f2230ce936a7cf2cb92a8775412"
        ),
        "stdout_sha256": (
            "bd624fcb1dabb66c2d5aad76e6af9f0c1467ebd58d8870f6750a59f01b512be7"
        ),
    },
}

# This is a one-use bridge for the exact maintained empty-assignment v2
# predecessor.  It is intentionally a byte-bound target and a structurally
# exact source tuple, not a compatibility range.
V2_EMPTY_MIGRATION_SCHEMA_BYTE_LENGTH = 16_489
V2_EMPTY_MIGRATION_SCHEMA_SHA256 = (
    "6ba5965d9b2e72c2ba14165aa2cbdf84625f2dac3f66d60503bf30f8dfad1a13"
)
V2_EMPTY_MIGRATION_TARGET_SCHEMA_BYTE_LENGTH = 48_359
V2_EMPTY_MIGRATION_TARGET_SCHEMA_SHA256 = (
    "2f7851cddc366e430c24220a25d3716d0d7d34bc4a80335c7a0b55e2b8fdc802"
)
# The one-use combined migration is an exact maintained cut, not a semantic
# compatibility path. These identities are regenerated only when the reviewed
# predecessor or intended successor changes as one coherent source update.
EXACT_COMBINED_MIGRATION_AUTHORING_SCHEMA_BYTE_LENGTH = 83_271
EXACT_COMBINED_MIGRATION_AUTHORING_SCHEMA_SHA256 = (
    "68dd4c810e7020db636b4610d7cc7c86ceaaada40d96d0142cdb9b9ebf215ef3"
)
EXACT_PROBE_REPIN_PREDECESSOR_BINDING_BYTE_LENGTH = 4_696
EXACT_PROBE_REPIN_PREDECESSOR_BINDING_SHA256 = (
    "785fd68037fc83127d22deed832c8b5743a6c1bdb4a5dbea1dd6f4e2d36abcb6"
)
EXACT_PROBE_REPIN_TARGET_BINDING_BYTE_LENGTH = 4_696
EXACT_PROBE_REPIN_TARGET_BINDING_SHA256 = (
    "6d050663c6565f4b418e905a45c70b002fea15d9cd6990bae69c64febd8306cb"
)
EXACT_PROBE_REPIN_PREDECESSOR_OVERRIDES = (
    (
        "shared_source_bindings",
        "bounded_canonical",
        "byte_length",
        129_671,
    ),
    (
        "shared_source_bindings",
        "bounded_canonical",
        "sha256",
        "cd87d36c89160f2cfe378fea167683817f2fb0650623e6296a7f4ba8e918d232",
    ),
)
EXACT_PROBE_REPIN_PREDECESSOR_REMOVALS: tuple[tuple[str, ...], ...] = ()
EXACT_COMBINED_MIGRATION_PREDECESSOR_AUTHORING_BYTE_LENGTH = 12_858_110
EXACT_COMBINED_MIGRATION_PREDECESSOR_AUTHORING_SHA256 = (
    "c5d1cb9833e000e6a7e6278d1fb74b8b19e07886e611e7e8fd51b1e28b78abf1"
)
EXACT_COMBINED_MIGRATION_PREDECESSOR_INVENTORY_BYTE_LENGTH = 11_343
EXACT_COMBINED_MIGRATION_PREDECESSOR_INVENTORY_SHA256 = (
    "775071457e2dff09bfb07ee4ddeb840fdc930fefc4cf8b7ba67cdb4d26b08a0b"
)
EXACT_COMBINED_MIGRATION_SUCCESSOR_AUTHORING_BYTE_LENGTH = 12_897_150
EXACT_COMBINED_MIGRATION_SUCCESSOR_AUTHORING_SHA256 = (
    "3b6158e51fa01a2d8aca8508a899a0e3692e34facbf6d0d8c7791f6787bc8a64"
)
EXACT_COMBINED_MIGRATION_SUCCESSOR_INVENTORY_BYTE_LENGTH = 42_642
EXACT_COMBINED_MIGRATION_SUCCESSOR_INVENTORY_SHA256 = (
    "86f060eb63182e714dded9c314cf8e26ea4ce10fc17bbf6306c47b4133be6985"
)
V2_EMPTY_MIGRATION_DOCUMENT_ROW_COMMITMENT = {
    "algorithm": "SHA256",
    "canonicalization": "UTF8_JSON_SORTED_KEYS_NO_INSIGNIFICANT_WHITESPACE",
    "domain_hex": (
        "6e63702e6230312e73656c6563746f722d616c6c6f636174696f6e2e"
        "646f63756d656e742d726f77732e763100"
    ),
    "row_kinds": ["allocations", "exclusions"],
}
V2_EMPTY_MIGRATION_ADR_SOURCE_SET_SUITE = {
    "digest_algorithm": "SHA256",
    "domain_hex": "6e63702e6230312d6164722d736f757263652d7365742e763100",
    "schema": "ncp.b01-adr-source-set.v1",
}
# The successor refreshes ADR snapshots and moves the source-set commitment to
# its current richer suite.  Retain the small historical snapshot projection so
# the migration KAT can reconstruct the exact predecessor after the maintained
# files become the successor.  The complete reconstructed inventory is still
# required to match the frozen byte commitment below.
V2_EMPTY_MIGRATION_DOCUMENT_SOURCE_SNAPSHOTS = (
    (
        "ADR-001",
        151_733,
        "2f4279f394c10571c32100ea967eb24fed7f24bb049921eab5a5d5f254d03de1",
        (),
        "bf5fc4e284efa701fb4d49dfcc893b798fef55884bdc2b52509464ef44d2d5c7",
    ),
    (
        "ADR-002",
        16_005,
        "0c3d83f95254ddb6e16238027b27e59a7b54ea3d703e8155c950df255c009063",
        (),
        "11f1d11db2223582d687854038568ff0bf34256fcb4e6a1ff24a81bfb0cd96a9",
    ),
    (
        "ADR-003",
        19_602,
        "1f5e02cba4d482a44b7588bb146232e91f97143ea33b3c85a428047991b6721c",
        (),
        "2db528f7923854d3419d26b566786c0d1b88f5e15717e9fd9c42e1a3e805b120",
    ),
    (
        "ADR-004",
        259_467,
        "fe07c33b97c0d5aaab86292749fb9444c87d76429e6f03799df1c19ac557e7a3",
        (
            (
                "docs/adr/modules/"
                "adr-004-cross-store-observer-closure-and-enrollment.md",
                117_887,
                "c303f48d016bbf17f82b5dc13681de72f66f4893d9f761a4dbc1f1202438f9cc",
            ),
        ),
        "5f4f9ef854b7c63ab09972b322d1af40f7e7992c808f463c8870020b8083cb8f",
    ),
    (
        "ADR-005",
        38_309,
        "92eae6e339ab534518f0437cf7d41bac681be765377b7c4252980ea38ab999cb",
        (),
        "9a4fc1d134b9476ac1fe00aadd2674203d277d86de44cb900ecc1c1493f45abb",
    ),
    (
        "ADR-006",
        53_927,
        "e1f52350e9818d1dabee572decf957100d83e455d885b02c063b3d02d24f26b6",
        (),
        "a8d2fac8aaa51cbd83d4ccc3b1f6bf79134c533ac87bcf1fee41e270ff7087b8",
    ),
    (
        "ADR-007",
        221_494,
        "8e7c05973e6a0b291fdaceef7c8280505b910fda9b55b85b5a7c3e2fe3af9cde",
        (),
        "fc0b182531ef8f7ebde54fae51ac00c0fdaee16d8de9b46d96ea8cb76e17fa36",
    ),
    (
        "ADR-008",
        170_572,
        "eeea7c8a3c30f925f970da2788b1ce7e4b449f6f538eb8d78cfa7ed116d7993a",
        (),
        "85ea2c84b6125bd129254c81477f6d41344edc4e7669754897cbb9989badb87b",
    ),
    (
        "ADR-009",
        257_562,
        "b8031cdaa2ae7e3024ee4c623e99ff63bcb231353e66ee299888bec7b86841e4",
        (
            (
                "docs/adr/modules/"
                "adr-009-cross-store-producer-and-compromise-evidence.md",
                74_277,
                "47420d1b7a3b9bfa3ff767510c26e66520caa44ef735371d08faf4c16cc11800",
            ),
        ),
        "9dd098dea0786d83d09b0465db56da289f7a61b3b3705ef243ec49a1f3039b9c",
    ),
    (
        "ADR-010",
        14_277,
        "be4a05d1e52bc148053d37f1009a607d0d25ef6181c5e57504ef23935008ab05",
        (),
        "201ceb5436eaf71dedd0d78ee393b85aa9cb18a8d7f52481baa82c04e0b18144",
    ),
    (
        "ADR-011",
        70_556,
        "7f2d002dab4ece01068d783cf47a32ffa6f43c5467eb9f2b52fb5db7da46652f",
        (),
        "d9cf7aee473691802bf2851bb9894b5f3feca616bc2d3e9e64eab787cc3cad01",
    ),
)
V2_EMPTY_MIGRATION_PROFILE = {
    "allocation_schema_byte_length": V2_EMPTY_MIGRATION_SCHEMA_BYTE_LENGTH,
    "allocation_schema_id": "ncp.b01-selector-allocation-authoring.v1",
    "allocation_schema_sha256": V2_EMPTY_MIGRATION_SCHEMA_SHA256,
    "model_allocation_count": 2618,
    "model_allocation_sha256": (
        "fee9158a06563103d7dadec2aefa1f37c5bc861e7a6051f5931b6a8f0f0b1623"
    ),
    "model_projection_schema": "ncp.b01-selector-allocation-model-projection.v2",
    "required_kinds": list(ALLOCATION_KINDS),
    "resource_closure_row_count": 3626,
    "resource_closure_schema": "ncp.b01-resource-closure.v2",
    "resource_closure_sha256": (
        "c5bc4f3c76a032cd5b5f0c5241050d0b14c2be3127f84fcbd46d6dcff6f42f9c"
    ),
    "schema": "ncp.b01-selector-allocation-review-profile.v2",
    "semantic_shape_entry_count": 267405,
    "semantic_shape_projection_schema": (
        "ncp.b01-selector-allocation-semantic-shape-projection.v1"
    ),
    "semantic_shape_sha256": (
        "2634c7a0e9e1abd80b51e16e0dd0fb0a9eb8e49fd46e9eba4c8ca2baa1df901c"
    ),
}
V2_EMPTY_MIGRATION_PROVENANCE_REVIEW = {
    "algorithm": "SHA256",
    "canonicalization": "UTF8_JSON_SORTED_KEYS_NO_INSIGNIFICANT_WHITESPACE",
    "claim_boundary": (
        "EXACT_SEMANTIC_REVIEW_SUBJECT_ADR_OWNER_AND_ANCHOR_REVIEW_ONLY_"
        "NOT_PROTOCOL_RELEASE_OR_EXTERNAL_EVIDENCE"
    ),
    "domain_hex": (
        "6e63702e6230312e73656c6563746f722d616c6c6f636174696f6e2e"
        "70726f76656e616e63652d7265766965772e763400"
    ),
    "reviewed_assignment_sha256": "0" * 64,
    "status": "NOT_REVIEWED",
}
V2_EMPTY_MIGRATION_SEMANTIC_REVIEW_SUBJECT = {
    "algorithm": "SHA256",
    "byte_length": 12_851_303,
    "canonicalization": "NCP_PRINTABLE_ASCII_SAFE_INTEGER_JSON_V1",
    "claim_boundary": (
        "EXACT_CANONICAL_EXPANDED_SEMANTIC_PAYLOAD_EXCLUDING_ALLOCATION_ORACLE_"
        "DERIVED_COMMITMENTS_GENERATOR_METADATA_AND_EXECUTABLE_PROBE_BINDINGS"
    ),
    "domain_hex": (
        "6e63702e6230312e73656c6563746f722d616c6c6f636174696f6e2e"
        "73656d616e7469632d7265766965772d7375626a6563742e763200"
    ),
    "excluded_top_level_keys": [
        "adr_allocation_oracle",
        "adversarial_probe_bindings",
        "closure_commitments",
        "generated_by",
        "generated_view",
    ],
    "framing": (
        "DOMAIN_BYTES_THEN_UINT64_BE_CANONICAL_BYTE_LENGTH_THEN_CANONICAL_BYTES"
    ),
    "scalar_domain": (
        "NULL_BOOLEAN_SIGNED_INTEGER_ABS_LE_9007199254740991_"
        "PRINTABLE_ASCII_STRING_ONLY"
    ),
    "sha256": "7e19eccc550726111b21c9bb6d24ad35242d4aac36e54e351f271bce1e2f7c48",
}
REVIEW_ARTIFACT_ROLES = (
    "allocation_inventory",
    "semantic_authoring_source",
    "semantic_compact_source",
    "review_generation_state",
)
PROMOTION_WRITE_ORDER = (
    "semantic_authoring_source",
    "semantic_compact_source",
    "review_generation_state",
    "allocation_inventory",
)
REOPEN_WRITE_ORDER = (
    "allocation_inventory",
    "semantic_compact_source",
    "review_generation_state",
    "semantic_authoring_source",
)
CODEC_TEMP_NAME = re.compile(r"^\.ncp-[0-9a-f]{32}\.tmp$")

_SCHEMA_ANNOTATION_KEYS = {
    "$id",
    "$schema",
    "description",
    "title",
}
_SCHEMA_VALIDATION_KEYS = {
    "additionalProperties",
    "const",
    "enum",
    "items",
    "maxItems",
    "maxLength",
    "maxProperties",
    "minItems",
    "minLength",
    "pattern",
    "properties",
    "required",
    "type",
    "uniqueItems",
}
_JSON_TYPES = {
    "array",
    "boolean",
    "integer",
    "null",
    "number",
    "object",
    "string",
}
_ALLOWED_SCHEMA_PATTERNS = frozenset(
    {
        r"^[0-9a-f]{64}$",
        r"^[A-Z][A-Z0-9_]*$",
        r"^[a-z0-9]+(?:-[a-z0-9]+)*::[A-Za-z0-9_]+$",
    }
)


class SelectorClosureGenerationError(ValueError):
    """The authoring source or generation workflow is invalid."""


@dataclass(frozen=True)
class GenerationInputSnapshot:
    allocation: AllocationInventorySnapshot
    adr_sources: tuple[tuple[Path, bytes], ...]
    authoring_raw: bytes
    compact_schema_raw: bytes
    schema_raw: bytes


@dataclass(frozen=True)
class MaterializationInputSnapshot:
    allocation_schema_path: Path
    allocation_schema_raw: bytes
    compact_raw: bytes
    compact_schema_raw: bytes
    schema_raw: bytes


@dataclass(frozen=True)
class IncompleteRefreshGuardSnapshot:
    """One exact present or absent migration precondition."""

    label: str
    maximum_bytes: int
    path: Path
    raw: bytes | None


@dataclass(frozen=True)
class IncompleteRefreshInputSnapshot:
    """Exact mutable and immutable bytes used by one source refresh."""

    adr_sources: tuple[tuple[Path, bytes], ...]
    allocation_schema_raw: bytes
    authoring_raw: bytes
    guards: tuple[IncompleteRefreshGuardSnapshot, ...]
    inventory_raw: bytes
    schema_raw: bytes


@dataclass(frozen=True)
class IncompleteRefreshPlan:
    """Fully validated bytes for one recoverable authoring-first refresh."""

    adr_sources: tuple[tuple[Path, bytes], ...]
    authoring: dict[str, Any]
    authoring_raw: bytes
    canonical: dict[str, Any]
    inventory: dict[str, Any]
    inventory_raw: bytes


@dataclass(frozen=True)
class ExactMigrationArtifactCommitment:
    """One independently frozen exact artifact identity."""

    byte_length: int
    sha256: str

    def validate(self, *, label: str) -> None:
        _require(
            type(self.byte_length) is int
            and self.byte_length > 0
            and isinstance(self.sha256, str)
            and re.fullmatch(r"[0-9a-f]{64}", self.sha256) is not None,
            f"{label} migration artifact commitment is invalid",
        )

    def matches(self, raw: bytes) -> bool:
        return len(raw) == self.byte_length and sha256(raw).hexdigest() == self.sha256


@dataclass(frozen=True)
class ExactMigrationCut:
    """The exact authoring/inventory pair at one migration cut."""

    authoring: ExactMigrationArtifactCommitment
    inventory: ExactMigrationArtifactCommitment

    def validate(self, *, label: str) -> None:
        self.authoring.validate(label=f"{label} authoring")
        self.inventory.validate(label=f"{label} inventory")


def _exact_combined_migration_cuts() -> tuple[ExactMigrationCut, ExactMigrationCut]:
    """Return the only maintained predecessor and successor artifact pairs."""

    return (
        ExactMigrationCut(
            authoring=ExactMigrationArtifactCommitment(
                byte_length=(
                    EXACT_COMBINED_MIGRATION_PREDECESSOR_AUTHORING_BYTE_LENGTH
                ),
                sha256=EXACT_COMBINED_MIGRATION_PREDECESSOR_AUTHORING_SHA256,
            ),
            inventory=ExactMigrationArtifactCommitment(
                byte_length=(
                    EXACT_COMBINED_MIGRATION_PREDECESSOR_INVENTORY_BYTE_LENGTH
                ),
                sha256=EXACT_COMBINED_MIGRATION_PREDECESSOR_INVENTORY_SHA256,
            ),
        ),
        ExactMigrationCut(
            authoring=ExactMigrationArtifactCommitment(
                byte_length=(EXACT_COMBINED_MIGRATION_SUCCESSOR_AUTHORING_BYTE_LENGTH),
                sha256=EXACT_COMBINED_MIGRATION_SUCCESSOR_AUTHORING_SHA256,
            ),
            inventory=ExactMigrationArtifactCommitment(
                byte_length=(EXACT_COMBINED_MIGRATION_SUCCESSOR_INVENTORY_BYTE_LENGTH),
                sha256=EXACT_COMBINED_MIGRATION_SUCCESSOR_INVENTORY_SHA256,
            ),
        ),
    )


def _reconstruct_exact_combined_migration_predecessor(
    *,
    successor_authoring_raw: bytes,
    successor_inventory_raw: bytes,
) -> tuple[bytes, bytes]:
    """Invert the frozen one-use cut for a state-independent migration KAT.

    The predecessor remains the authority for what the one-use bridge admits.
    The maintained tree becomes the successor after the bridge runs, so the KAT
    cannot use mutable maintained files as its predecessor fixture.  This
    inverse is deliberately narrow: it admits only the exact successor pair,
    restores only the two migrated domains, and must reproduce both frozen
    predecessor byte commitments exactly.
    """

    predecessor_cut, successor_cut = _exact_combined_migration_cuts()
    _require(
        successor_cut.authoring.matches(successor_authoring_raw)
        and successor_cut.inventory.matches(successor_inventory_raw),
        "combined migration predecessor reconstruction requires the exact successor",
    )
    successor_authoring = parse_json_bytes(
        successor_authoring_raw,
        label="combined migration exact successor authoring",
        maximum_bytes=MAX_EXPANDED_BYTES,
    )
    successor_inventory = parse_json_bytes(
        successor_inventory_raw,
        label="combined migration exact successor inventory",
        maximum_bytes=MAX_ALLOCATION_INVENTORY_BYTES,
    )
    _require(
        isinstance(successor_authoring, dict) and isinstance(successor_inventory, dict),
        "combined migration exact successor roots must be objects",
    )

    predecessor_inventory = copy.deepcopy(successor_inventory)
    predecessor_inventory["document_row_commitment"] = copy.deepcopy(
        V2_EMPTY_MIGRATION_DOCUMENT_ROW_COMMITMENT
    )
    predecessor_inventory["allocation_review_profile"] = copy.deepcopy(
        V2_EMPTY_MIGRATION_PROFILE
    )
    predecessor_inventory["provenance_review"] = copy.deepcopy(
        V2_EMPTY_MIGRATION_PROVENANCE_REVIEW
    )
    predecessor_inventory["semantic_review_subject"] = copy.deepcopy(
        V2_EMPTY_MIGRATION_SEMANTIC_REVIEW_SUBJECT
    )
    predecessor_inventory["model_allocation_count"] = V2_EMPTY_MIGRATION_PROFILE[
        "model_allocation_count"
    ]
    predecessor_inventory["model_allocation_sha256"] = V2_EMPTY_MIGRATION_PROFILE[
        "model_allocation_sha256"
    ]
    predecessor_inventory["semantic_shape_entry_count"] = V2_EMPTY_MIGRATION_PROFILE[
        "semantic_shape_entry_count"
    ]
    predecessor_inventory["semantic_shape_sha256"] = V2_EMPTY_MIGRATION_PROFILE[
        "semantic_shape_sha256"
    ]
    predecessor_documents = predecessor_inventory.get("documents")
    _require(
        isinstance(predecessor_documents, list)
        and len(predecessor_documents)
        == len(V2_EMPTY_MIGRATION_DOCUMENT_SOURCE_SNAPSHOTS),
        "combined migration exact successor has an unexpected document set",
    )
    for document, snapshot in zip(
        predecessor_documents,
        V2_EMPTY_MIGRATION_DOCUMENT_SOURCE_SNAPSHOTS,
        strict=True,
    ):
        adr_id, byte_length, source_sha256, modules, source_set_sha256 = snapshot
        _require(
            isinstance(document, dict) and document.get("adr_id") == adr_id,
            "combined migration exact successor document order differs",
        )
        document["byte_length"] = byte_length
        document["sha256"] = source_sha256
        document["modules"] = [
            {
                "byte_length": module_byte_length,
                "path": module_path,
                "sha256": module_sha256,
            }
            for module_path, module_byte_length, module_sha256 in modules
        ]
        document["source_set"] = copy.deepcopy(V2_EMPTY_MIGRATION_ADR_SOURCE_SET_SUITE)
        document["source_set"]["sha256"] = source_set_sha256
    predecessor_inventory_raw = inventory_bytes(predecessor_inventory)
    _require(
        predecessor_cut.inventory.matches(predecessor_inventory_raw),
        (
            "combined migration inverse did not reproduce the frozen "
            "predecessor inventory"
        ),
    )

    predecessor_binding = copy.deepcopy(successor_authoring.get(ALLOCATION_BINDING_KEY))
    _require(
        isinstance(predecessor_binding, dict),
        "combined migration exact successor has no allocation binding",
    )
    predecessor_binding.update(
        {
            "authoring_byte_length": len(predecessor_inventory_raw),
            "authoring_sha256": sha256(predecessor_inventory_raw).hexdigest(),
            "schema_byte_length": V2_EMPTY_MIGRATION_SCHEMA_BYTE_LENGTH,
            "schema_sha256": V2_EMPTY_MIGRATION_SCHEMA_SHA256,
        }
    )
    validate_inventory_binding(predecessor_binding)

    predecessor_authoring_seed = copy.deepcopy(successor_authoring)
    predecessor_authoring_seed[OBSERVER_BRIDGE_PROFILE_KEY] = copy.deepcopy(
        BRIDGE_V1_MIGRATION_PROFILE
    )
    predecessor_authoring_seed[ADVERSARIAL_PROBE_BINDINGS_KEY] = copy.deepcopy(
        BRIDGE_V1_MIGRATION_PROBE_BINDINGS
    )
    predecessor_authoring_seed[ALLOCATION_BINDING_KEY] = copy.deepcopy(
        predecessor_binding
    )
    predecessor_canonical = _restore_canonical_source_envelope(
        predecessor_authoring_seed,
        inventory_to_oracle(predecessor_inventory),
    )
    _recompute_closure_commitments(predecessor_canonical)
    predecessor_authoring = prepare_authoring_source(
        predecessor_canonical,
        predecessor_binding,
    )
    predecessor_authoring_raw = _authoring_bytes(predecessor_authoring)
    _require(
        predecessor_cut.authoring.matches(predecessor_authoring_raw),
        (
            "combined migration inverse did not reproduce the frozen "
            "predecessor authoring source"
        ),
    )
    return predecessor_authoring_raw, predecessor_inventory_raw


@dataclass(frozen=True)
class ReviewArtifactTransition:
    """One exact old/new tracked artifact pair."""

    role: str
    path: Path
    maximum_bytes: int
    expected_raw: bytes
    next_raw: bytes


@dataclass(frozen=True)
class ReviewPersistencePlan:
    """Validated four-artifact transition plus its reviewed source cut."""

    action: str
    source_cut: dict[str, Any]
    transition_subject_sha256: str
    review_receipt_sha256: str
    reviewed_assignment_sha256: str
    artifacts: tuple[ReviewArtifactTransition, ...]
    write_order: tuple[str, ...]
    expected_state: Any
    next_state: Any


@dataclass(frozen=True)
class ReviewControlLease:
    """Opaque proof that this process holds one exact Git-private lock."""

    repo_root: Path
    control_path: Path
    lock_path: Path
    lock_descriptor: int
    lock_identity: tuple[int, ...]
    owner_pid: int
    nonce: object


_ACTIVE_REVIEW_CONTROL_LEASES: dict[int, ReviewControlLease] = {}


def _fail(message: str) -> NoReturn:
    raise SelectorClosureGenerationError(message)


def _require(condition: bool, message: str) -> None:
    if not condition:
        _fail(message)


def _schema_value_equal(actual: Any, expected: Any) -> bool:
    return type(actual) is type(expected) and canonical_bytes(
        actual
    ) == canonical_bytes(expected)


def _assert_supported_schema(schema: Any, path: str = "$") -> None:
    _require(isinstance(schema, dict), f"{path}: schema node must be an object")
    unsupported = set(schema) - _SCHEMA_ANNOTATION_KEYS - _SCHEMA_VALIDATION_KEYS
    _require(
        not unsupported,
        f"{path}: unsupported schema keywords {sorted(unsupported)}",
    )
    if "type" in schema:
        _require(
            schema["type"] in _JSON_TYPES,
            f"{path}.type: unsupported JSON type {schema['type']!r}",
        )
    if "enum" in schema:
        _require(
            isinstance(schema["enum"], list) and schema["enum"],
            f"{path}.enum: expected a nonempty array",
        )
    if "required" in schema:
        required = schema["required"]
        _require(
            isinstance(required, list)
            and all(isinstance(value, str) for value in required)
            and len(required) == len(set(required)),
            f"{path}.required: expected unique strings",
        )
    if "properties" in schema:
        properties = schema["properties"]
        _require(
            isinstance(properties, dict)
            and all(isinstance(key, str) for key in properties),
            f"{path}.properties: expected an object",
        )
        for key, child in properties.items():
            _assert_supported_schema(child, f"{path}.properties[{key!r}]")
    if isinstance(schema.get("additionalProperties"), dict):
        _assert_supported_schema(
            schema["additionalProperties"],
            f"{path}.additionalProperties",
        )
    elif "additionalProperties" in schema:
        _require(
            isinstance(schema["additionalProperties"], bool),
            f"{path}.additionalProperties: expected boolean or schema",
        )
    if "items" in schema:
        _assert_supported_schema(schema["items"], f"{path}.items")
    for key in (
        "maxItems",
        "maxLength",
        "maxProperties",
        "minItems",
        "minLength",
    ):
        if key in schema:
            _require(
                isinstance(schema[key], int)
                and not isinstance(schema[key], bool)
                and schema[key] >= 0,
                f"{path}.{key}: expected a nonnegative integer",
            )
    if "uniqueItems" in schema:
        _require(
            isinstance(schema["uniqueItems"], bool),
            f"{path}.uniqueItems: expected a boolean",
        )
    if "pattern" in schema:
        _require(
            isinstance(schema["pattern"], str)
            and schema["pattern"] in _ALLOWED_SCHEMA_PATTERNS,
            f"{path}.pattern: expected one reviewed expression",
        )
        try:
            re.compile(schema["pattern"])
        except re.error as error:
            _fail(f"{path}.pattern: invalid regular expression: {error}")


def _matches_json_type(value: Any, expected: str) -> bool:
    if expected == "null":
        return value is None
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "string":
        return isinstance(value, str)
    if expected == "array":
        return isinstance(value, list)
    if expected == "object":
        return isinstance(value, dict)
    return False


def _validate_schema_instance(
    value: Any,
    schema: dict[str, Any],
    path: str = "$",
) -> None:
    expected_type = schema.get("type")
    if expected_type is not None:
        _require(
            _matches_json_type(value, expected_type),
            f"{path}: expected {expected_type}, got {type(value).__name__}",
        )
    if "const" in schema:
        _require(
            _schema_value_equal(value, schema["const"]),
            f"{path}: expected constant {schema['const']!r}",
        )
    if "enum" in schema:
        _require(
            any(_schema_value_equal(value, item) for item in schema["enum"]),
            f"{path}: value is not in the closed enum",
        )

    if isinstance(value, dict):
        if "maxProperties" in schema:
            _require(
                len(value) <= schema["maxProperties"],
                f"{path}: exceeds {schema['maxProperties']} properties",
            )
        required = schema.get("required", [])
        missing = [key for key in required if key not in value]
        _require(not missing, f"{path}: missing required properties {missing}")
        properties = schema.get("properties", {})
        additional = schema.get("additionalProperties", True)
        for key, item in value.items():
            if key in properties:
                _validate_schema_instance(
                    item,
                    properties[key],
                    f"{path}.{key}",
                )
            elif additional is False:
                _fail(f"{path}: unknown property {key!r}")
            elif isinstance(additional, dict):
                _validate_schema_instance(
                    item,
                    additional,
                    f"{path}.{key}",
                )

    if isinstance(value, list):
        if "minItems" in schema:
            _require(
                len(value) >= schema["minItems"],
                f"{path}: has fewer than {schema['minItems']} items",
            )
        if "maxItems" in schema:
            _require(
                len(value) <= schema["maxItems"],
                f"{path}: exceeds {schema['maxItems']} items",
            )
        if schema.get("uniqueItems"):
            canonical_items = [canonical_bytes(item) for item in value]
            _require(
                len(canonical_items) == len(set(canonical_items)),
                f"{path}: contains duplicate items",
            )
        if "items" in schema:
            for index, item in enumerate(value):
                _validate_schema_instance(
                    item,
                    schema["items"],
                    f"{path}[{index}]",
                )

    if isinstance(value, str):
        if "minLength" in schema:
            _require(
                len(value) >= schema["minLength"],
                f"{path}: is shorter than {schema['minLength']} characters",
            )
        if "maxLength" in schema:
            _require(
                len(value) <= schema["maxLength"],
                f"{path}: exceeds {schema['maxLength']} characters",
            )
        if "pattern" in schema:
            _require(
                re.search(schema["pattern"], value) is not None,
                f"{path}: does not match {schema['pattern']!r}",
            )


def load_authoring_schema(path: Path) -> dict[str, Any]:
    raw = read_bounded_regular_file(
        path,
        maximum_bytes=MAX_AUTHORING_SCHEMA_BYTES,
        label="selector authoring schema",
    )
    _require(
        sha256(raw).hexdigest() == AUTHORING_SCHEMA_SHA256,
        "authoring schema reviewed byte identity changed",
    )
    value = parse_json_bytes(raw, label=str(path))
    _require(isinstance(value, dict), "authoring schema must be an object")
    _assert_supported_schema(value)
    _require(
        value.get("$schema") == "https://json-schema.org/draft/2020-12/schema",
        "authoring schema must use JSON Schema draft 2020-12",
    )
    _require(
        value.get("$id") == AUTHORING_SCHEMA_URL,
        "authoring schema has an unexpected $id",
    )
    return value


def load_compact_schema(path: Path) -> tuple[bytes, dict[str, Any]]:
    """Load the exact reviewed compact-schema bytes and basic identity."""

    raw = read_bounded_regular_file(
        path,
        maximum_bytes=MAX_COMPACT_SCHEMA_BYTES,
        label="selector compact schema",
    )
    _require(
        sha256(raw).hexdigest() == COMPACT_SCHEMA_SHA256,
        (
            "compact schema digest changed; review the schema and update "
            "COMPACT_SCHEMA_SHA256 in the same change"
        ),
    )
    value = parse_json_bytes(raw, label=str(path))
    _require(isinstance(value, dict), "compact schema must be an object")
    _require(
        value.get("$schema") == "https://json-schema.org/draft/2020-12/schema",
        "compact schema must use JSON Schema draft 2020-12",
    )
    _require(
        value.get("$id") == COMPACT_SCHEMA_URL,
        "compact schema has an unexpected $id",
    )
    _require(value.get("type") == "object", "compact schema root must be object")
    _require(
        value.get("additionalProperties") is False,
        "compact schema root must reject additional properties",
    )
    _require(
        value.get("required")
        == [
            "$schema",
            "schema",
            "normative",
            "candidate",
            "task",
            "encoding",
            "payload",
        ],
        "compact schema has an unexpected root requirement set",
    )
    return raw, value


def _recompute_closure_commitments(data: dict[str, Any]) -> None:
    artifacts = data.get("artifacts")
    coordinates = data.get("global_key_coordinate_registry")
    selectors = data.get("selectors")
    _require(isinstance(artifacts, list), "artifacts must be an array")
    _require(
        isinstance(coordinates, list),
        "global_key_coordinate_registry must be an array",
    )
    _require(isinstance(selectors, list), "selectors must be an array")
    for index, selector in enumerate(selectors):
        _require(
            isinstance(selector, dict) and isinstance(selector.get("selector_id"), str),
            f"selectors[{index}] must have a string selector_id",
        )
    profile_payload = {
        key: value
        for key, value in data.items()
        if key
        not in {
            "artifacts",
            "closure_commitments",
            "global_key_coordinate_registry",
            "selectors",
        }
    }
    _, resource_closure = derive_resource_closure(data)
    data["closure_commitments"] = {
        "algorithm": "SHA-256",
        "canonicalization": ("UTF8_JSON_SORTED_KEYS_NO_INSIGNIFICANT_WHITESPACE"),
        "selector_semantic_digests": [
            {
                "selector_id": selector["selector_id"],
                "sha256": canonical_sha256(selector),
            }
            for selector in selectors
        ],
        "artifact_registry_sha256": canonical_sha256(artifacts),
        "global_key_coordinate_registry_sha256": canonical_sha256(coordinates),
        "resource_closure": resource_closure,
        "structural_profiles_sha256": canonical_sha256(profile_payload),
    }


def prepare_authoring_source(
    expanded: dict[str, Any],
    allocation_binding: dict[str, Any],
) -> dict[str, Any]:
    """Convert a decoded canonical source into the expanded authoring envelope."""

    authoring = copy.deepcopy(expanded)
    _require(
        ALLOCATION_ORACLE_KEY in authoring,
        f"canonical source is missing {ALLOCATION_ORACLE_KEY}",
    )
    validate_inventory_binding(allocation_binding)
    bound_inventory_raw = inventory_bytes(
        oracle_to_inventory(authoring[ALLOCATION_ORACLE_KEY])
    )
    _require(
        len(bound_inventory_raw) == allocation_binding["authoring_byte_length"]
        and sha256(bound_inventory_raw).hexdigest()
        == allocation_binding["authoring_sha256"],
        "canonical allocation oracle does not match its authoring binding",
    )
    authoring.pop(ALLOCATION_ORACLE_KEY)
    authoring[ALLOCATION_BINDING_KEY] = copy.deepcopy(allocation_binding)
    source_metadata = {
        key: authoring[key] for key in sorted(CANONICAL_SOURCE_METADATA_KEYS)
    }
    authoring["$schema"] = AUTHORING_SCHEMA_FILE
    authoring["schema"] = AUTHORING_SCHEMA_ID
    authoring["generated_by"] = MATERIALIZATION_GENERATOR
    authoring[CANONICAL_SOURCE_METADATA_KEY] = source_metadata
    return authoring


def prepare_canonical_source(
    authoring: dict[str, Any],
    allocation_oracle: dict[str, Any],
) -> dict[str, Any]:
    """Restore metadata and reject stale maintained closure commitments."""

    allocation_binding = authoring.get(ALLOCATION_BINDING_KEY)
    _require(
        isinstance(allocation_binding, dict),
        f"{ALLOCATION_BINDING_KEY} must be an object",
    )
    validate_inventory_binding(allocation_binding)
    bound_inventory_raw = inventory_bytes(oracle_to_inventory(allocation_oracle))
    _require(
        len(bound_inventory_raw) == allocation_binding["authoring_byte_length"]
        and sha256(bound_inventory_raw).hexdigest()
        == allocation_binding["authoring_sha256"],
        "external allocation oracle does not match its authoring binding",
    )
    generated = _restore_canonical_source_envelope(
        authoring,
        allocation_oracle,
    )
    maintained_commitments = copy.deepcopy(generated.get("closure_commitments"))
    expected = copy.deepcopy(generated)
    _recompute_closure_commitments(expected)
    _require(
        maintained_commitments == expected["closure_commitments"],
        (
            "closure_commitments are stale; update the maintained authoring "
            "source and its commitments in one reviewed change"
        ),
    )
    return generated


def _restore_canonical_source_envelope(
    authoring: dict[str, Any],
    allocation_oracle: dict[str, Any],
) -> dict[str, Any]:
    """Restore canonical metadata without accepting or repairing commitments."""

    generated = copy.deepcopy(authoring)
    allocation_binding = generated.pop(ALLOCATION_BINDING_KEY, None)
    _require(
        isinstance(allocation_binding, dict),
        f"{ALLOCATION_BINDING_KEY} must be an object",
    )
    validate_inventory_binding(allocation_binding)
    _require(
        ALLOCATION_ORACLE_KEY not in generated,
        (
            f"authoring source must bind external {ALLOCATION_ORACLE_KEY} "
            "instead of embedding it"
        ),
    )
    generated[ALLOCATION_ORACLE_KEY] = copy.deepcopy(allocation_oracle)
    source_metadata = generated.pop(CANONICAL_SOURCE_METADATA_KEY, None)
    _require(
        isinstance(source_metadata, dict),
        f"{CANONICAL_SOURCE_METADATA_KEY} must be an object",
    )
    _require(
        set(source_metadata) == CANONICAL_SOURCE_METADATA_KEYS,
        f"{CANONICAL_SOURCE_METADATA_KEY} has unexpected keys",
    )
    _require(
        source_metadata["$schema"] == CANONICAL_SOURCE_SCHEMA_FILE,
        f"{CANONICAL_SOURCE_METADATA_KEY} has an unexpected $schema",
    )
    _require(
        source_metadata["schema"] == CANONICAL_SOURCE_SCHEMA_ID,
        f"{CANONICAL_SOURCE_METADATA_KEY} has an unexpected schema",
    )
    for key in sorted(CANONICAL_SOURCE_METADATA_KEYS):
        _require(
            isinstance(source_metadata[key], str),
            f"{CANONICAL_SOURCE_METADATA_KEY}.{key} must be a string",
        )
        generated[key] = source_metadata[key]
    return generated


def _validate_generated_semantics(
    generated: dict[str, Any],
    *,
    require_complete_allocation: bool = True,
    allow_incomplete_allocation: bool = False,
) -> tuple[tuple[Path, bytes], ...]:
    """Run the checker with strict architecture and an allocation-only switch."""

    from check_selector_closure import (  # Imported lazily to avoid CLI cycles.
        ClosureCheckError,
        validate_expanded_source,
    )

    adr_snapshots: dict[Path, bytes] = {}

    def retain_adr_snapshots(snapshots: dict[Path, bytes]) -> None:
        _require(not adr_snapshots, "semantic validator returned ADR snapshots twice")
        adr_snapshots.update(snapshots)

    try:
        validate_expanded_source(
            generated,
            require_complete_allocation=require_complete_allocation,
            allow_incomplete_allocation=allow_incomplete_allocation,
            adr_snapshot_sink=retain_adr_snapshots,
        )
    except (ClosureCheckError, KeyError, TypeError) as error:
        _fail(f"expanded semantic validation failed: {error}")
    expected_paths = {
        Path(path)
        for path in (
            *ADR_ALLOCATION_PATHS,
            *(path for paths in ADR_ALLOCATION_MODULE_PATHS for path in paths),
        )
    }
    _require(
        set(adr_snapshots) == expected_paths,
        "semantic validator returned an incomplete or unexpected ADR source set",
    )
    return tuple(sorted(adr_snapshots.items(), key=lambda item: item[0].as_posix()))


def _require_review_candidate_boundary(generated: dict[str, Any]) -> None:
    """Admit only the exact fail-closed, unreviewed candidate tuple."""

    oracle = generated.get(ALLOCATION_ORACLE_KEY)
    _require(
        isinstance(oracle, dict),
        "review-candidate source must contain the allocation oracle",
    )
    provenance_review = oracle.get("provenance_review")
    _require(
        oracle.get("status") == "INCOMPLETE_FAIL_CLOSED"
        and isinstance(provenance_review, dict)
        and provenance_review.get("status") == "NOT_REVIEWED"
        and provenance_review.get("reviewed_assignment_sha256") == "0" * 64,
        (
            "review-candidate mode requires the exact "
            "INCOMPLETE_FAIL_CLOSED/NOT_REVIEWED/zero-reviewed-digest tuple"
        ),
    )


def _authoring_bytes(data: dict[str, Any]) -> bytes:
    raw = canonical_bytes(data) + b"\n"
    _require(
        len(raw) <= MAX_EXPANDED_BYTES,
        f"authoring source exceeds {MAX_EXPANDED_BYTES} bytes",
    )
    return raw


def load_authoring_source(
    path: Path,
    schema: dict[str, Any],
) -> dict[str, Any]:
    raw = read_bounded_regular_file(
        path,
        maximum_bytes=MAX_EXPANDED_BYTES,
        label="selector authoring source",
    )
    value = parse_json_bytes(raw, label=str(path))
    _require(isinstance(value, dict), "authoring source must be an object")
    _validate_schema_instance(value, schema)
    _require(
        raw == _authoring_bytes(value),
        "authoring source is not canonical JSON with one trailing newline",
    )
    return value


def _load_canonical_unvalidated_authoring_source(
    path: Path,
) -> tuple[bytes, dict[str, Any]]:
    """Load canonical authoring bytes without granting schema compatibility."""

    raw = read_bounded_regular_file(
        path,
        maximum_bytes=MAX_EXPANDED_BYTES,
        label="legacy selector authoring migration input",
    )
    value = parse_json_bytes(raw, label=str(path))
    _require(isinstance(value, dict), "legacy authoring source must be an object")
    _require(
        raw == _authoring_bytes(value),
        "legacy authoring migration input is not canonical JSON",
    )
    return raw, value


def _bridge_v2_normalized_json(value: Any) -> Any:
    """Normalize the profile's JSON-only domain independently of bridge code."""

    value_type = type(value)
    if value_type is dict:
        _require(
            all(type(key) is str for key in value),
            "bridge v2 KAT mapping contains a non-string key",
        )
        return {
            "$bridge_kind": "mapping",
            "entries": [
                [key, _bridge_v2_normalized_json(value[key])] for key in sorted(value)
            ],
        }
    if value_type is list:
        return {
            "$bridge_kind": "list",
            "items": [_bridge_v2_normalized_json(item) for item in value],
        }
    _require(
        value is None or value_type in {bool, int, str},
        "bridge v2 KAT contains a non-JSON or unsupported scalar",
    )
    return value


def _bridge_v2_domain_kat(
    value: Any,
    *,
    domain: str,
) -> tuple[int, str, str]:
    normalized_raw = canonical_bytes(_bridge_v2_normalized_json(value))
    frame = (
        BRIDGE_V2_COMMITMENT_FRAME_PREFIX
        + b"\x00"
        + domain.encode("ascii")
        + b"\x00"
        + normalized_raw
    )
    return (
        len(normalized_raw),
        sha256(normalized_raw).hexdigest(),
        sha256(frame).hexdigest(),
    )


def _authoring_schema_bridge_profile(
    schema: dict[str, Any],
    *,
    expected_schema: str | None = None,
) -> dict[str, Any]:
    """Return an isolated exact bridge-profile const from the authoring schema."""

    properties = schema.get("properties")
    _require(
        isinstance(properties, dict),
        "authoring schema properties must be an object",
    )
    rule = properties.get(OBSERVER_BRIDGE_PROFILE_KEY)
    _require(
        isinstance(rule, dict)
        and set(rule) == {"const"}
        and isinstance(rule["const"], dict),
        "authoring schema must bind one exact observer read/capture bridge profile",
    )
    profile = copy.deepcopy(rule["const"])
    if expected_schema is not None:
        _require(
            profile.get("schema") == expected_schema,
            (
                "authoring schema observer read/capture bridge profile is not "
                f"the exact {expected_schema!r} target"
            ),
        )
    if profile.get("schema") == BRIDGE_V2_MIGRATION_PROFILE_SCHEMA:
        profile_raw = canonical_bytes(profile)
        _require(
            len(profile_raw) == BRIDGE_V2_MIGRATION_PROFILE_CANONICAL_BYTE_LENGTH
            and sha256(profile_raw).hexdigest()
            == BRIDGE_V2_MIGRATION_PROFILE_CANONICAL_SHA256,
            "authoring schema observer read/capture bridge v2 const differs "
            "from its frozen standard-JSON KAT",
        )
        _require(
            _bridge_v2_domain_kat(
                profile,
                domain=BRIDGE_V2_MIGRATION_PROFILE_DIGEST_DOMAIN,
            )
            == (
                BRIDGE_V2_MIGRATION_PROFILE_NORMALIZED_BYTE_LENGTH,
                BRIDGE_V2_MIGRATION_PROFILE_NORMALIZED_SHA256,
                BRIDGE_V2_MIGRATION_PROFILE_DIGEST,
            ),
            "authoring schema observer read/capture bridge v2 const differs "
            "from its frozen normalized/domain-separated KAT",
        )
        commitment = profile.get("canonical_commitment")
        _require(
            isinstance(commitment, dict)
            and set(commitment) == {"suite", "suite_digest", "suite_digest_domain"},
            "authoring schema observer read/capture bridge v2 const has an "
            "invalid commitment triple",
        )
        suite = commitment["suite"]
        _require(
            isinstance(suite, dict)
            and suite.get("schema") == BRIDGE_V2_COMMITMENT_SUITE_SCHEMA,
            "authoring schema observer read/capture bridge v2 const has an "
            "invalid commitment suite",
        )
        suite_raw = canonical_bytes(suite)
        _require(
            len(suite_raw) == BRIDGE_V2_COMMITMENT_SUITE_CANONICAL_BYTE_LENGTH
            and sha256(suite_raw).hexdigest()
            == BRIDGE_V2_COMMITMENT_SUITE_CANONICAL_SHA256
            and commitment["suite_digest_domain"]
            == BRIDGE_V2_COMMITMENT_SUITE_DIGEST_DOMAIN
            and commitment["suite_digest"] == BRIDGE_V2_COMMITMENT_SUITE_DIGEST,
            "authoring schema observer read/capture bridge v2 commitment "
            "differs from its frozen KAT",
        )
        _require(
            _bridge_v2_domain_kat(
                suite,
                domain=BRIDGE_V2_COMMITMENT_SUITE_DIGEST_DOMAIN,
            )
            == (
                BRIDGE_V2_COMMITMENT_SUITE_NORMALIZED_BYTE_LENGTH,
                BRIDGE_V2_COMMITMENT_SUITE_NORMALIZED_SHA256,
                BRIDGE_V2_COMMITMENT_SUITE_DIGEST,
            ),
            "authoring schema observer read/capture bridge v2 suite differs "
            "from its frozen normalized/domain-separated KAT",
        )
    return profile


def _authoring_schema_probe_bindings(
    schema: dict[str, Any],
) -> dict[str, Any]:
    """Return the schema-bound exact successor probe-evidence closure."""

    properties = schema.get("properties")
    _require(
        isinstance(properties, dict),
        "authoring schema properties must be an object",
    )
    rule = properties.get(ADVERSARIAL_PROBE_BINDINGS_KEY)
    _require(
        isinstance(rule, dict) and isinstance(rule.get("const"), dict),
        "authoring schema must bind one exact adversarial probe closure",
    )
    target = copy.deepcopy(rule["const"])
    _validate_schema_instance(target, rule)
    return target


def _probe_binding_commitment(bindings: dict[str, Any]) -> tuple[int, str]:
    raw = canonical_bytes(bindings)
    return len(raw), sha256(raw).hexdigest()


def _prepare_exact_adversarial_probe_binding_repin(
    *,
    authoring: dict[str, Any],
    schema: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """Install only the byte-bound successor probe-evidence closure."""

    target = _authoring_schema_probe_bindings(schema)
    _require(
        _probe_binding_commitment(target)
        == (
            EXACT_PROBE_REPIN_TARGET_BINDING_BYTE_LENGTH,
            EXACT_PROBE_REPIN_TARGET_BINDING_SHA256,
        ),
        "authoring schema adversarial probe target differs from its exact cut",
    )
    current = authoring.get(ADVERSARIAL_PROBE_BINDINGS_KEY)
    _require(
        isinstance(current, dict),
        "probe-binding repin input has no exact adversarial probe closure",
    )
    current_commitment = _probe_binding_commitment(current)
    predecessor = current_commitment == (
        EXACT_PROBE_REPIN_PREDECESSOR_BINDING_BYTE_LENGTH,
        EXACT_PROBE_REPIN_PREDECESSOR_BINDING_SHA256,
    )
    already_target = current == target and current_commitment == (
        EXACT_PROBE_REPIN_TARGET_BINDING_BYTE_LENGTH,
        EXACT_PROBE_REPIN_TARGET_BINDING_SHA256,
    )
    _require(
        predecessor or already_target,
        (
            "adversarial probe repin input is neither the exact maintained "
            "predecessor nor the exact authoring-schema target"
        ),
    )
    seeded = copy.deepcopy(authoring)
    seeded[ADVERSARIAL_PROBE_BINDINGS_KEY] = target
    preserved = copy.deepcopy(authoring)
    preserved.pop(ADVERSARIAL_PROBE_BINDINGS_KEY, None)
    seeded_preserved = copy.deepcopy(seeded)
    seeded_preserved.pop(ADVERSARIAL_PROBE_BINDINGS_KEY, None)
    _require(
        seeded_preserved == preserved,
        "adversarial probe repin changed unrelated authoring content",
    )
    _validate_schema_instance(seeded, schema)
    return seeded, predecessor


def _run_exact_adversarial_probe_binding_repin_self_test(
    schema: dict[str, Any],
) -> None:
    """Reject near-miss probe cuts and preserve unrelated authoring content."""

    target = _authoring_schema_probe_bindings(schema)
    predecessor = copy.deepcopy(target)
    for *path, value in EXACT_PROBE_REPIN_PREDECESSOR_OVERRIDES:
        cursor = predecessor
        for key in path[:-1]:
            cursor = cursor[key]
        cursor[path[-1]] = value
    for *path, key in EXACT_PROBE_REPIN_PREDECESSOR_REMOVALS:
        cursor = predecessor
        for part in path:
            cursor = cursor[part]
        _require(
            key in cursor,
            "adversarial probe repin predecessor removal fixture differs",
        )
        cursor.pop(key)
    _require(
        _probe_binding_commitment(predecessor)
        == (
            EXACT_PROBE_REPIN_PREDECESSOR_BINDING_BYTE_LENGTH,
            EXACT_PROBE_REPIN_PREDECESSOR_BINDING_SHA256,
        ),
        "adversarial probe repin predecessor fixture differs from its exact cut",
    )
    fixture_schema = {
        "additionalProperties": False,
        "properties": {
            ADVERSARIAL_PROBE_BINDINGS_KEY: {"const": target},
            "preserved": {"const": "unchanged"},
        },
        "required": [ADVERSARIAL_PROBE_BINDINGS_KEY, "preserved"],
        "type": "object",
    }
    authoring = {
        ADVERSARIAL_PROBE_BINDINGS_KEY: predecessor,
        "preserved": "unchanged",
    }
    original = copy.deepcopy(authoring)
    seeded, changed = _prepare_exact_adversarial_probe_binding_repin(
        authoring=authoring,
        schema=fixture_schema,
    )
    _require(
        changed
        and authoring == original
        and seeded[ADVERSARIAL_PROBE_BINDINGS_KEY] == target
        and seeded["preserved"] == "unchanged",
        "adversarial probe repin did not preserve its input and unrelated content",
    )
    replay, replay_changed = _prepare_exact_adversarial_probe_binding_repin(
        authoring=seeded,
        schema=fixture_schema,
    )
    _require(
        not replay_changed and replay == seeded,
        "adversarial probe repin exact replay changed its target",
    )
    hostile = copy.deepcopy(original)
    hostile[ADVERSARIAL_PROBE_BINDINGS_KEY]["observer_capture_probe"][
        "stdout_byte_length"
    ] += 1
    try:
        _prepare_exact_adversarial_probe_binding_repin(
            authoring=hostile,
            schema=fixture_schema,
        )
    except SelectorClosureGenerationError:
        pass
    else:
        _fail("adversarial probe repin accepted a near-miss predecessor")


def _same_file_or_resolved_path(left: Path, right: Path) -> bool:
    try:
        if left.exists() and right.exists() and os.path.samefile(left, right):
            return True
    except OSError as error:
        _fail(f"cannot compare path identities: {error}")
    try:
        return left.resolve(strict=False) == right.resolve(strict=False)
    except OSError as error:
        _fail(f"cannot resolve path identities: {error}")


def _require_distinct_paths(
    input_path: Path,
    output_path: Path,
    *,
    labels: tuple[str, str],
) -> None:
    _require(
        not _same_file_or_resolved_path(input_path, output_path),
        f"{labels[0]} and {labels[1]} must be different files",
    )


def _require_semantic_output_path_distinct(output_path: Path) -> None:
    """Forbid a generated compact output from replacing a semantic input."""

    for relative_path in (
        *ADR_ALLOCATION_PATHS,
        *(path for paths in ADR_ALLOCATION_MODULE_PATHS for path in paths),
    ):
        _require_distinct_paths(
            ROOT / relative_path,
            output_path,
            labels=(f"semantic ADR input {relative_path}", "compact output"),
        )


def _require_maintained_mutation_lease(
    paths: tuple[Path, ...],
    lease: ReviewControlLease | None,
) -> bool:
    """Require the opaque lease and report an exact maintained mutation."""

    maintained_paths = (
        DEFAULT_AUTHORING,
        DEFAULT_AUTHORING.with_name(INVENTORY_FILE),
        DEFAULT_OUTPUT,
    )
    maintained = any(
        _same_file_or_resolved_path(path, maintained)
        for path in paths
        for maintained in maintained_paths
    )
    if maintained:
        _require_active_review_control_lease(ROOT, lease)
    return maintained


def _atomic_write(
    path: Path,
    raw: bytes,
    *,
    create_only: bool = False,
    create_mode: int = 0o644,
) -> None:
    """Install exact bytes through the shared anchored-dirfd writer."""

    atomic_write_regular_file(
        path,
        raw,
        label="selector closure generated output",
        create_only=create_only,
        create_mode=create_mode,
    )


def _atomic_replace_if_current(
    path: Path,
    raw: bytes,
    *,
    expected_current: bytes,
    maximum_bytes: int,
    label: str,
    phase_hook: Any = None,
) -> None:
    """Replace one exact snapshot while the cooperative parent lock is held."""

    _require(
        type(raw) is bytes
        and type(expected_current) is bytes
        and 0 < len(raw) <= maximum_bytes
        and 0 < len(expected_current) <= maximum_bytes,
        f"{label} CAS inputs exceed their exact byte bound",
    )

    def forward_phase(phase: str) -> None:
        if phase_hook is not None:
            phase_hook(phase)

    _atomic_write_regular_file(
        path,
        raw,
        label=label,
        expected_current=expected_current,
        phase_hook=forward_phase,
    )


def _git_private_path(repo_root: Path, name: str) -> Path:
    """Resolve one fixed per-worktree Git-private path without shell parsing."""

    from selector_allocation_review import _run_git

    raw = _run_git(
        repo_root,
        "rev-parse",
        "--path-format=absolute",
        "--git-path",
        name,
        maximum_output_bytes=4096,
    )
    try:
        value = raw.decode("utf-8").strip()
    except UnicodeDecodeError as error:
        _fail(f"Git-private control path is not UTF-8: {error}")
    _require(value and "\n" not in value and "\x00" not in value, "invalid Git path")
    path = Path(value)
    _require(path.is_absolute() and path.name == name, "unexpected Git-private path")
    try:
        parent = path.parent.resolve(strict=True)
    except OSError as error:
        _fail(f"cannot resolve Git-private control directory: {error}")
    _require(
        stat.S_ISDIR(parent.lstat().st_mode) and not parent.is_symlink(),
        "Git-private control parent must be a non-symlink directory",
    )
    return parent / name


@contextmanager
def _review_control_lock(repo_root: Path) -> Iterator[ReviewControlLease]:
    """Hold the fixed per-worktree cooperative mutation lock.

    Same-owner renaming or replacement of the Git-private ancestor directory is
    outside this explicitly non-tamper-resistant coordination boundary. Each
    individual read/write still uses anchored no-follow path operations.
    """

    lock_path = _git_private_path(repo_root, REVIEW_CONTROL_LOCK_FILE)
    # Both leaves are one per-worktree coordination domain while the resolved
    # Git-private ancestor remains stable. Do not run a second Git resolution:
    # it could select another cooperative domain even without a path error.
    control_path = lock_path.with_name(REVIEW_CONTROL_FILE)
    _require(
        all(
            active.control_path != control_path
            for active in _ACTIVE_REVIEW_CONTROL_LEASES.values()
        ),
        "review control lock is already active in this process",
    )
    flags = (
        os.O_RDWR
        | os.O_CREAT
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptor = -1
    lease: ReviewControlLease | None = None
    try:
        descriptor = os.open(lock_path, flags, 0o600)
        locked = os.fstat(descriptor)
        _require(
            stat.S_ISREG(locked.st_mode)
            and not stat.S_ISLNK(locked.st_mode)
            and locked.st_nlink == 1
            and locked.st_uid == os.geteuid()
            and stat.S_IMODE(locked.st_mode) == 0o600,
            "review control lock is not one private owner-managed regular file",
        )
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        _require(
            all(
                active.control_path != control_path
                for active in _ACTIVE_REVIEW_CONTROL_LEASES.values()
            ),
            "review control lock is already active in this process",
        )
        lease = ReviewControlLease(
            repo_root=repo_root.resolve(strict=True),
            control_path=control_path,
            lock_path=lock_path,
            lock_descriptor=descriptor,
            lock_identity=(
                locked.st_dev,
                locked.st_ino,
                stat.S_IFMT(locked.st_mode),
                locked.st_uid,
                locked.st_nlink,
                stat.S_IMODE(locked.st_mode),
            ),
            owner_pid=os.getpid(),
            nonce=object(),
        )
        _ACTIVE_REVIEW_CONTROL_LEASES[id(lease)] = lease
        yield lease
    finally:
        if lease is not None:
            _ACTIVE_REVIEW_CONTROL_LEASES.pop(id(lease), None)
        if descriptor >= 0:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)


def _require_active_review_control_lease(
    repo_root: Path,
    lease: ReviewControlLease | None,
) -> Path:
    """Validate one live, same-process lock capability and return its control."""

    _require(
        type(lease) is ReviewControlLease
        and _ACTIVE_REVIEW_CONTROL_LEASES.get(id(lease)) is lease
        and lease.owner_pid == os.getpid(),
        "mutation requires the live opaque review-control lock lease",
    )
    try:
        resolved_root = repo_root.resolve(strict=True)
        locked = os.fstat(lease.lock_descriptor)
        visible_lock = lease.lock_path.lstat()
    except OSError as error:
        _fail(f"cannot validate active review-control lock lease: {error}")
    current_identity = (
        locked.st_dev,
        locked.st_ino,
        stat.S_IFMT(locked.st_mode),
        locked.st_uid,
        locked.st_nlink,
        stat.S_IMODE(locked.st_mode),
    )
    visible_identity = (
        visible_lock.st_dev,
        visible_lock.st_ino,
        stat.S_IFMT(visible_lock.st_mode),
        visible_lock.st_uid,
        visible_lock.st_nlink,
        stat.S_IMODE(visible_lock.st_mode),
    )
    _require(
        resolved_root == lease.repo_root
        and lease.control_path == lease.lock_path.with_name(REVIEW_CONTROL_FILE)
        and current_identity == lease.lock_identity == visible_identity,
        "review-control lock lease, repository, or stable path identity changed",
    )
    return lease.control_path


def _read_optional_control(path: Path) -> tuple[bytes, dict[str, Any]] | None:
    try:
        existing = path.lstat()
    except FileNotFoundError:
        return None
    _require(
        stat.S_ISREG(existing.st_mode)
        and not stat.S_ISLNK(existing.st_mode)
        and existing.st_nlink == 1
        and existing.st_uid == os.geteuid()
        and stat.S_IMODE(existing.st_mode) == 0o600,
        "private review control must be one owner-only regular non-symlink file",
    )
    raw = read_bounded_regular_file(
        path,
        maximum_bytes=MAX_REVIEW_CONTROL_BYTES,
        label="selector allocation private review control",
    )
    try:
        final = path.lstat()
    except OSError as error:
        _fail(f"private review control changed after its bounded read: {error}")
    _require(
        (
            existing.st_dev,
            existing.st_ino,
            existing.st_mode,
            existing.st_size,
            existing.st_mtime_ns,
            existing.st_ctime_ns,
        )
        == (
            final.st_dev,
            final.st_ino,
            final.st_mode,
            final.st_size,
            final.st_mtime_ns,
            final.st_ctime_ns,
        )
        and final.st_nlink == 1
        and final.st_uid == os.geteuid()
        and stat.S_IMODE(final.st_mode) == 0o600,
        "private review control identity or owner-only mode changed while read",
    )
    value = parse_json_bytes(
        raw,
        label=str(path),
        maximum_bytes=MAX_REVIEW_CONTROL_BYTES,
        maximum_depth=MAX_REVIEW_CONTROL_JSON_DEPTH,
        maximum_items=MAX_REVIEW_CONTROL_JSON_ITEMS,
        maximum_string_chars=MAX_REVIEW_CONTROL_BYTES,
        maximum_total_string_chars=MAX_REVIEW_CONTROL_BYTES,
    )
    _require(isinstance(value, dict), "private review control must be an object")
    _require(
        raw == canonical_bytes(value) + b"\n",
        "private review control is not canonical with one trailing LF",
    )
    _validate_review_control(value)
    return raw, value


def _require_absent_path(path: Path, *, label: str) -> None:
    """Reject every existing directory entry, including a broken symlink."""

    try:
        path.lstat()
    except FileNotFoundError:
        return
    except OSError as error:
        _fail(f"cannot inspect {label}: {error}")
    _fail(f"{label} must be absent")


def _validate_control_state_projection(value: Any, *, label: str) -> Any:
    from selector_allocation_review import _validate_review_state_projection

    return _validate_review_state_projection(value, label=label)


def _validate_artifact_control(value: Any, *, pending: bool) -> None:
    _require(isinstance(value, list) and len(value) == 4, "control artifacts invalid")
    roles: list[str] = []
    for item in value:
        _require(
            isinstance(item, dict)
            and set(item)
            == {
                "expected_byte_length",
                "expected_base64",
                "expected_sha256",
                "maximum_bytes",
                "next_base64",
                "next_byte_length",
                "next_sha256",
                "path",
                "role",
            },
            "private control artifact has an unexpected shape",
        )
        role = item["role"]
        roles.append(role)
        _require(role in REVIEW_ARTIFACT_ROLES, "private control role is unknown")
        _require(
            item["path"] == _review_role_path(role),
            "private control artifact path is substituted",
        )
        _require(
            type(item["maximum_bytes"]) is int
            and item["maximum_bytes"] == _review_role_limit(role),
            "private control artifact bound is substituted",
        )
        for prefix in ("expected", "next"):
            _require(
                type(item[f"{prefix}_byte_length"]) is int
                and 0 < item[f"{prefix}_byte_length"] <= item["maximum_bytes"]
                and isinstance(item[f"{prefix}_sha256"], str)
                and re.fullmatch(r"[0-9a-f]{64}", item[f"{prefix}_sha256"]) is not None,
                f"private control {prefix} commitment is invalid",
            )
        _require(pending, "only a pending control may carry exact payloads")
        for prefix in ("expected", "next"):
            _require(
                isinstance(item[f"{prefix}_base64"], str),
                f"pending control {prefix} payload is not text",
            )
            _decode_control_payload(item, prefix=prefix)
    _require(
        tuple(roles) == REVIEW_ARTIFACT_ROLES,
        "private control artifacts are not in canonical role order",
    )


def _validate_attached_artifact_control(value: Any) -> None:
    _require(
        isinstance(value, list) and len(value) == 4,
        "attached control artifacts are invalid",
    )
    roles: list[str] = []
    for item in value:
        _require(
            isinstance(item, dict)
            and set(item)
            == {
                "byte_length",
                "maximum_bytes",
                "path",
                "role",
                "sha256",
            },
            "attached control artifact has an unexpected shape",
        )
        role = item["role"]
        roles.append(role)
        _require(
            role in REVIEW_ARTIFACT_ROLES
            and item["path"] == _review_role_path(role)
            and type(item["maximum_bytes"]) is int
            and item["maximum_bytes"] == _review_role_limit(role)
            and type(item["byte_length"]) is int
            and 0 < item["byte_length"] <= item["maximum_bytes"]
            and isinstance(item["sha256"], str)
            and re.fullmatch(r"[0-9a-f]{64}", item["sha256"]) is not None,
            "attached control artifact commitment is invalid",
        )
    _require(
        tuple(roles) == REVIEW_ARTIFACT_ROLES,
        "attached control artifacts are not in canonical role order",
    )


def _validate_open_source_reanchor(
    value: Any,
    *,
    pending: dict[str, Any],
    expected_state: Any,
    source_cut: dict[str, Any],
) -> None:
    """Validate the complete historical-to-clean-descendant re-anchor proof."""

    _require(
        isinstance(value, dict)
        and set(value)
        == {
            "ancestry",
            "prior_attached",
            "prior_attached_sha256",
            "prior_source_commit",
            "prior_source_tree",
            "prior_tracked_artifacts",
            "reanchored_expected_artifacts",
            "reanchored_source_commit",
            "reanchored_source_tree",
            "schema",
        },
        "open-source re-anchor has an unexpected shape",
    )
    _require(
        value["schema"] == REVIEW_OPEN_SOURCE_REANCHOR_SCHEMA
        and value["ancestry"] == "PRIOR_COMMIT_IS_STRICT_ANCESTOR_OF_REANCHORED_COMMIT",
        "open-source re-anchor has an unexpected suite",
    )
    prior_attached = value["prior_attached"]
    _require(
        isinstance(prior_attached, dict) and prior_attached.get("status") == "ATTACHED",
        "open-source re-anchor prior control is not attached",
    )
    _validate_review_control(prior_attached)
    prior_raw = canonical_bytes(prior_attached) + b"\n"
    _require(
        len(prior_raw) <= MAX_REVIEW_CONTROL_BYTES
        and sha256(prior_raw).hexdigest() == value["prior_attached_sha256"]
        and value["prior_attached_sha256"] == pending["expected_attached_sha256"],
        "open-source re-anchor prior control commitment differs",
    )
    _validate_attached_artifact_control(value["prior_tracked_artifacts"])
    _validate_attached_artifact_control(value["reanchored_expected_artifacts"])
    expected_artifacts = [
        {
            "byte_length": item["expected_byte_length"],
            "maximum_bytes": item["maximum_bytes"],
            "path": item["path"],
            "role": item["role"],
            "sha256": item["expected_sha256"],
        }
        for item in pending["artifacts"]
    ]
    _require(
        value["prior_source_commit"] == prior_attached["last_source_commit"]
        and value["prior_source_tree"] == prior_attached["last_source_tree"]
        and value["prior_tracked_artifacts"] == prior_attached["tracked_artifacts"]
        and value["reanchored_source_commit"] == source_cut["commit"]
        and value["reanchored_source_tree"] == source_cut["tree"]
        and value["reanchored_expected_artifacts"] == expected_artifacts
        and value["prior_source_commit"] != value["reanchored_source_commit"],
        "open-source re-anchor cuts or artifacts are inconsistent",
    )
    _require(
        prior_attached["tracked_state"] == expected_state.projection()
        and prior_attached["tracked_state_sha256"]
        == expected_state.commitment()["sha256"]
        and expected_state.active_assignment_sha256 is None
        and expected_state.active_inventory_sha256 is None
        and expected_state.current_receipt_sha256 is None
        and expected_state.last_consumed_receipt_sha256 is not None
        and expected_state.prior_state_sha256 is not None,
        "open-source re-anchor requires one exact inactive review state",
    )


def _validate_review_control(value: dict[str, Any]) -> None:
    common = {
        "authority_class",
        "claim_boundary",
        "control_lineage_id",
        "evidence_authority",
        "external_authority",
        "independent_authority",
        "repository",
        "schema",
        "status",
        "worktree_scope",
    }
    _require(
        value.get("schema") == REVIEW_CONTROL_SCHEMA
        and value.get("authority_class") == "LOCAL_ONLY"
        and value.get("claim_boundary") == REVIEW_CONTROL_CLAIM_BOUNDARY
        and value.get("evidence_authority") is False
        and value.get("external_authority") is False
        and value.get("independent_authority") is False
        and value.get("worktree_scope") == "ONE_GIT_PRIVATE_WORKTREE_LINEAGE_ONLY",
        "private review control has an authority-bearing or unknown suite",
    )
    _require(
        isinstance(value.get("control_lineage_id"), str)
        and re.fullmatch(r"[0-9a-f]{32}", value["control_lineage_id"]) is not None,
        "private review control lineage is invalid",
    )
    _require(
        isinstance(value.get("repository"), str)
        and 3 <= len(value["repository"]) <= 128,
        "private review control repository is invalid",
    )
    if value.get("status") == "ATTACHED":
        _require(
            set(value)
            == common
            | {
                "last_source_commit",
                "last_source_tree",
                "tracked_artifacts",
                "tracked_state",
                "tracked_state_sha256",
            },
            "attached private review control has an unexpected shape",
        )
        _require(
            isinstance(value["last_source_commit"], str)
            and isinstance(value["last_source_tree"], str)
            and len(value["last_source_commit"]) == len(value["last_source_tree"])
            and re.fullmatch(
                r"(?:[0-9a-f]{40}|[0-9a-f]{64})",
                value["last_source_commit"],
            )
            is not None
            and re.fullmatch(
                r"(?:[0-9a-f]{40}|[0-9a-f]{64})",
                value["last_source_tree"],
            )
            is not None,
            "attached private review control has invalid Git object IDs",
        )
        attached_state = _validate_control_state_projection(
            value["tracked_state"],
            label="attached private review control state",
        )
        _validate_attached_artifact_control(value["tracked_artifacts"])
        attached_by_role = {item["role"]: item for item in value["tracked_artifacts"]}
        from selector_allocation_review import review_state_bytes

        attached_state_raw = review_state_bytes(attached_state)
        _require(
            attached_state.commitment()["sha256"] == value["tracked_state_sha256"]
            and attached_by_role["review_generation_state"]["byte_length"]
            == len(attached_state_raw)
            and attached_by_role["review_generation_state"]["sha256"]
            == sha256(attached_state_raw).hexdigest()
            and (
                attached_state.active_inventory_sha256 is None
                or attached_state.active_inventory_sha256
                == attached_by_role["allocation_inventory"]["sha256"]
            ),
            "attached private review control state or inventory digest differs",
        )
    elif value.get("status") == "PENDING":
        _require(
            set(value)
            == common
            | {
                "action",
                "artifacts",
                "expected_attached_sha256",
                "expected_state",
                "next_attached",
                "next_state",
                "open_source_reanchor",
                "review_receipt_sha256",
                "reviewed_assignment_sha256",
                "source_cut",
                "transition_subject_sha256",
                "write_order",
            },
            "pending private review control has an unexpected shape",
        )
        _require(
            value["action"] in {"PROMOTE_TO_REVIEWED", "REOPEN_TO_NOT_REVIEWED"},
            "pending private review control action is invalid",
        )
        expected_order = (
            PROMOTION_WRITE_ORDER
            if value["action"] == "PROMOTE_TO_REVIEWED"
            else REOPEN_WRITE_ORDER
        )
        _require(
            tuple(value["write_order"]) == expected_order,
            "pending private review control write order is invalid",
        )
        _validate_artifact_control(value["artifacts"], pending=True)
        artifact_by_role = {item["role"]: item for item in value["artifacts"]}
        expected_state = _validate_control_state_projection(
            value["expected_state"],
            label="pending private review expected state",
        )
        next_state = _validate_control_state_projection(
            value["next_state"],
            label="pending private review next state",
        )
        from selector_allocation_review import _validate_source_cut_shape

        source_cut = _validate_source_cut_shape(value["source_cut"])
        _require(
            source_cut["repository"] == value["repository"],
            "pending private review source repository differs",
        )
        _validate_review_control(value["next_attached"])
        if value["open_source_reanchor"] is not None:
            _require(
                value["action"] == "PROMOTE_TO_REVIEWED",
                "only promotion may carry an open-source re-anchor",
            )
            _validate_open_source_reanchor(
                value["open_source_reanchor"],
                pending=value,
                expected_state=expected_state,
                source_cut=source_cut,
            )
        expected_next_artifacts = [
            {
                "byte_length": item["next_byte_length"],
                "maximum_bytes": item["maximum_bytes"],
                "path": item["path"],
                "role": item["role"],
                "sha256": item["next_sha256"],
            }
            for item in value["artifacts"]
        ]
        _require(
            value["next_attached"]["status"] == "ATTACHED"
            and value["next_attached"]["control_lineage_id"]
            == value["control_lineage_id"]
            and value["next_attached"]["repository"] == value["repository"]
            and value["next_attached"]["tracked_state"] == next_state.projection()
            and value["next_attached"]["last_source_commit"] == source_cut["commit"]
            and value["next_attached"]["last_source_tree"] == source_cut["tree"]
            and value["next_attached"]["tracked_artifacts"] == expected_next_artifacts
            and expected_state.projection() != next_state.projection(),
            "pending private review next attachment is inconsistent",
        )
        for key in (
            "expected_attached_sha256",
            "review_receipt_sha256",
            "reviewed_assignment_sha256",
            "transition_subject_sha256",
        ):
            _require(
                isinstance(value[key], str)
                and re.fullmatch(r"[0-9a-f]{64}", value[key]) is not None,
                f"pending private review control {key} is invalid",
            )
        from selector_allocation_review import review_state_bytes

        expected_state_raw = review_state_bytes(expected_state)
        next_state_raw = review_state_bytes(next_state)
        state_artifact = artifact_by_role["review_generation_state"]
        _require(
            state_artifact["expected_byte_length"] == len(expected_state_raw)
            and state_artifact["expected_sha256"]
            == sha256(expected_state_raw).hexdigest()
            and _decode_control_payload(state_artifact) == next_state_raw,
            "pending private review state artifact differs from its state projections",
        )
        _require(
            next_state.prior_state_sha256 == expected_state.commitment()["sha256"]
            and next_state.state_version == expected_state.state_version + 1,
            "pending private review states are not direct content successors",
        )
        inventory_artifact = artifact_by_role["allocation_inventory"]
        if value["action"] == "PROMOTE_TO_REVIEWED":
            _require(
                expected_state.current_receipt_sha256 is None
                and next_state.current_receipt_sha256 == value["review_receipt_sha256"]
                and next_state.last_consumed_receipt_sha256
                == value["review_receipt_sha256"]
                and next_state.active_assignment_sha256
                == value["reviewed_assignment_sha256"]
                and next_state.active_inventory_sha256
                == inventory_artifact["next_sha256"]
                and next_state.next_review_generation
                == expected_state.next_review_generation,
                "pending promotion state does not bind its receipt and final inventory",
            )
        else:
            _require(
                expected_state.current_receipt_sha256 == value["review_receipt_sha256"]
                and expected_state.active_assignment_sha256
                == value["reviewed_assignment_sha256"]
                and expected_state.active_inventory_sha256
                == inventory_artifact["expected_sha256"]
                and next_state.current_receipt_sha256 is None
                and next_state.active_assignment_sha256 is None
                and next_state.active_inventory_sha256 is None
                and next_state.last_consumed_receipt_sha256
                == value["review_receipt_sha256"]
                and next_state.next_review_generation
                == expected_state.next_review_generation + 1,
                "pending reopen state does not invalidate its exact active receipt",
            )
    else:
        _fail("private review control has an unknown status")


def _decode_control_payload(
    item: dict[str, Any],
    *,
    prefix: str = "next",
) -> bytes:
    _require(
        prefix in {"expected", "next"},
        "private review control payload prefix is invalid",
    )
    payload_key = f"{prefix}_base64"
    byte_length_key = f"{prefix}_byte_length"
    digest_key = f"{prefix}_sha256"
    expected_encoded_length = 4 * ((item[byte_length_key] + 2) // 3)
    _require(
        len(item[payload_key]) == expected_encoded_length,
        f"private review control {prefix} base64 length differs from its "
        "declared decoded bound",
    )
    try:
        raw = base64.b64decode(item[payload_key], validate=True)
    except (binascii.Error, ValueError) as error:
        _fail(f"private review control payload is invalid base64: {error}")
    _require(
        base64.b64encode(raw).decode("ascii") == item[payload_key]
        and len(raw) == item[byte_length_key]
        and sha256(raw).hexdigest() == item[digest_key],
        f"private review control {prefix} payload differs from its commitment",
    )
    return raw


def _review_role_path(role: str) -> str:
    from selector_allocation_review import REQUIRED_SOURCE_ROLE_PATHS

    return REQUIRED_SOURCE_ROLE_PATHS[role]


def _review_role_limit(role: str) -> int:
    from selector_allocation_review import REQUIRED_SOURCE_ROLE_LIMITS

    return REQUIRED_SOURCE_ROLE_LIMITS[role]


def prepare_review_persistence_plan(
    repo_root: Path,
    transition: Any,
    *,
    authoring_path: Path = DEFAULT_AUTHORING,
    schema_path: Path = DEFAULT_AUTHORING_SCHEMA,
    compact_path: Path = DEFAULT_OUTPUT,
    state_path: Path | None = None,
) -> ReviewPersistencePlan:
    """Derive and strictly validate all four transition target byte strings."""

    from selector_allocation_review import (
        REVIEW_STATE_FILE,
        ReviewTransitionPlan,
        review_state_bytes,
        verify_transition_source_cut,
    )

    _require(
        isinstance(transition, ReviewTransitionPlan),
        "review persistence requires a validated review transition plan",
    )
    repo_root = repo_root.resolve(strict=True)
    state_path = state_path or authoring_path.with_name(REVIEW_STATE_FILE)
    expected_paths = {
        "allocation_inventory": repo_root / _review_role_path("allocation_inventory"),
        "semantic_authoring_source": repo_root
        / _review_role_path("semantic_authoring_source"),
        "semantic_compact_source": repo_root
        / _review_role_path("semantic_compact_source"),
        "review_generation_state": repo_root
        / _review_role_path("review_generation_state"),
    }
    provided_paths = {
        "allocation_inventory": authoring_path.with_name(INVENTORY_FILE),
        "semantic_authoring_source": authoring_path,
        "semantic_compact_source": compact_path,
        "review_generation_state": state_path,
    }
    for role in REVIEW_ARTIFACT_ROLES:
        _require(
            provided_paths[role].resolve(strict=True)
            == expected_paths[role].resolve(strict=True),
            f"review persistence path is not the reviewed repository path: {role}",
        )
    _require(
        schema_path.resolve(strict=True)
        == (repo_root / _review_role_path("semantic_authoring_schema")).resolve(
            strict=True
        ),
        "review persistence authoring schema path is substituted",
    )

    authoring_schema = load_authoring_schema(schema_path)
    allocation_schema_path = authoring_path.with_name(INVENTORY_SCHEMA_FILE)
    allocation_schema_raw, allocation_schema = load_inventory_schema(
        allocation_schema_path
    )
    expected_inventory = parse_json_bytes(
        transition.expected_inventory_bytes,
        label="review transition expected inventory",
        maximum_bytes=MAX_ALLOCATION_INVENTORY_BYTES,
    )
    next_inventory = parse_json_bytes(
        transition.next_inventory_bytes,
        label="review transition next inventory",
        maximum_bytes=MAX_ALLOCATION_INVENTORY_BYTES,
    )
    _require(
        isinstance(expected_inventory, dict) and isinstance(next_inventory, dict),
        "review transition inventories must be objects",
    )
    validate_allocation_inventory(expected_inventory, allocation_schema)
    validate_allocation_inventory(next_inventory, allocation_schema)
    validate_allocation_review_profile_schema_binding(
        expected_inventory,
        allocation_schema_raw,
    )
    validate_allocation_review_profile_schema_binding(
        next_inventory,
        allocation_schema_raw,
    )
    current_authoring_raw = read_bounded_regular_file(
        authoring_path,
        maximum_bytes=MAX_EXPANDED_BYTES,
        label="review transition expected authoring source",
    )
    current_authoring = load_authoring_source(authoring_path, authoring_schema)
    current_binding = build_inventory_binding(
        transition.expected_inventory_bytes,
        allocation_schema_raw,
    )
    _require(
        current_authoring[ALLOCATION_BINDING_KEY] == current_binding,
        "review transition authoring does not bind the expected inventory",
    )
    current_canonical = prepare_canonical_source(
        current_authoring,
        inventory_to_oracle(expected_inventory),
    )
    current_compact_raw = serialize_compact_source(current_canonical)
    _require(
        read_bounded_regular_file(
            compact_path,
            maximum_bytes=MAX_COMPACT_BYTES - 1,
            label="review transition expected compact source",
        )
        == current_compact_raw,
        "review transition compact source differs from expected canonical bytes",
    )
    next_canonical = _restore_canonical_source_envelope(
        current_authoring,
        inventory_to_oracle(next_inventory),
    )
    _recompute_closure_commitments(next_canonical)
    _validate_generated_semantics(
        next_canonical,
        allow_incomplete_allocation=(
            next_inventory["status"] == "INCOMPLETE_FAIL_CLOSED"
        ),
    )
    next_binding = build_inventory_binding(
        transition.next_inventory_bytes,
        allocation_schema_raw,
    )
    next_authoring = prepare_authoring_source(next_canonical, next_binding)
    _validate_schema_instance(next_authoring, authoring_schema)
    next_authoring_raw = _authoring_bytes(next_authoring)
    next_compact_raw = serialize_compact_source(next_canonical)
    expected_state_raw = review_state_bytes(transition.expected_review_state)
    next_state_raw = review_state_bytes(transition.next_review_state)
    _require(
        read_bounded_regular_file(
            state_path,
            maximum_bytes=_review_role_limit("review_generation_state"),
            label="review transition expected state",
        )
        == expected_state_raw,
        "review transition tracked state differs from its expected state",
    )
    artifacts_by_role = {
        "allocation_inventory": ReviewArtifactTransition(
            role="allocation_inventory",
            path=provided_paths["allocation_inventory"],
            maximum_bytes=_review_role_limit("allocation_inventory"),
            expected_raw=transition.expected_inventory_bytes,
            next_raw=transition.next_inventory_bytes,
        ),
        "semantic_authoring_source": ReviewArtifactTransition(
            role="semantic_authoring_source",
            path=authoring_path,
            maximum_bytes=_review_role_limit("semantic_authoring_source"),
            expected_raw=current_authoring_raw,
            next_raw=next_authoring_raw,
        ),
        "semantic_compact_source": ReviewArtifactTransition(
            role="semantic_compact_source",
            path=compact_path,
            maximum_bytes=_review_role_limit("semantic_compact_source"),
            expected_raw=current_compact_raw,
            next_raw=next_compact_raw,
        ),
        "review_generation_state": ReviewArtifactTransition(
            role="review_generation_state",
            path=state_path,
            maximum_bytes=_review_role_limit("review_generation_state"),
            expected_raw=expected_state_raw,
            next_raw=next_state_raw,
        ),
    }
    for artifact in artifacts_by_role.values():
        _require(
            artifact.expected_raw != artifact.next_raw,
            f"review transition does not change {artifact.role}",
        )
    mutable = {
        role: (
            artifacts_by_role[role].expected_raw,
            artifacts_by_role[role].next_raw,
        )
        for role in REVIEW_ARTIFACT_ROLES
    }
    states = verify_transition_source_cut(repo_root, transition.source_cut, mutable)
    _require(
        all(value == "EXPECTED" for value in states.values()),
        "new review transition must start from the exact clean expected cut",
    )
    write_order = (
        PROMOTION_WRITE_ORDER
        if transition.action == "PROMOTE_TO_REVIEWED"
        else REOPEN_WRITE_ORDER
    )
    _require(
        transition.action in {"PROMOTE_TO_REVIEWED", "REOPEN_TO_NOT_REVIEWED"},
        "review transition action is unknown",
    )
    return ReviewPersistencePlan(
        action=transition.action,
        source_cut=copy.deepcopy(transition.source_cut),
        transition_subject_sha256=transition.transition_subject_sha256,
        review_receipt_sha256=transition.review_receipt_sha256,
        reviewed_assignment_sha256=transition.reviewed_assignment_sha256,
        artifacts=tuple(artifacts_by_role[role] for role in REVIEW_ARTIFACT_ROLES),
        write_order=write_order,
        expected_state=transition.expected_review_state,
        next_state=transition.next_review_state,
    )


def _attached_artifact_commitments(
    artifacts: tuple[ReviewArtifactTransition, ...],
    *,
    use_next: bool,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in artifacts:
        raw = item.next_raw if use_next else item.expected_raw
        result.append(
            {
                "byte_length": len(raw),
                "maximum_bytes": item.maximum_bytes,
                "path": _review_role_path(item.role),
                "role": item.role,
                "sha256": sha256(raw).hexdigest(),
            }
        )
    _validate_attached_artifact_control(result)
    return result


def _attached_control(
    *,
    lineage_id: str,
    repository: str,
    source_cut: dict[str, Any],
    state: Any,
    artifacts: tuple[ReviewArtifactTransition, ...],
) -> dict[str, Any]:
    return {
        "authority_class": "LOCAL_ONLY",
        "claim_boundary": REVIEW_CONTROL_CLAIM_BOUNDARY,
        "control_lineage_id": lineage_id,
        "evidence_authority": False,
        "external_authority": False,
        "independent_authority": False,
        "last_source_commit": source_cut["commit"],
        "last_source_tree": source_cut["tree"],
        "repository": repository,
        "schema": REVIEW_CONTROL_SCHEMA,
        "status": "ATTACHED",
        "tracked_artifacts": _attached_artifact_commitments(
            artifacts,
            use_next=True,
        ),
        "tracked_state": state.projection(),
        "tracked_state_sha256": state.commitment()["sha256"],
        "worktree_scope": "ONE_GIT_PRIVATE_WORKTREE_LINEAGE_ONLY",
    }


def _artifact_control_item(artifact: ReviewArtifactTransition) -> dict[str, Any]:
    return {
        "expected_base64": base64.b64encode(artifact.expected_raw).decode("ascii"),
        "expected_byte_length": len(artifact.expected_raw),
        "expected_sha256": sha256(artifact.expected_raw).hexdigest(),
        "maximum_bytes": artifact.maximum_bytes,
        "next_base64": base64.b64encode(artifact.next_raw).decode("ascii"),
        "next_byte_length": len(artifact.next_raw),
        "next_sha256": sha256(artifact.next_raw).hexdigest(),
        "path": _review_role_path(artifact.role),
        "role": artifact.role,
    }


def _require_attached_control_ancestry(
    repo_root: Path,
    current_control: dict[str, Any],
    plan: ReviewPersistencePlan,
) -> None:
    """Reject a source-cut rollback within one surviving private lineage."""

    from selector_allocation_review import SelectorAllocationReviewError

    prior_commit = current_control["last_source_commit"]
    prior_tree = current_control["last_source_tree"]
    try:
        object_type = (
            _run_review_git(
                repo_root,
                "cat-file",
                "-t",
                prior_commit,
            )
            .decode("ascii", errors="strict")
            .strip()
        )
        resolved_tree = (
            _run_review_git(
                repo_root,
                "rev-parse",
                "--verify",
                f"{prior_commit}^{{tree}}",
            )
            .decode("ascii", errors="strict")
            .strip()
        )
        _require(
            object_type == "commit" and resolved_tree == prior_tree,
            "private review high-water commit differs from its recorded tree",
        )
        _run_review_git(
            repo_root,
            "merge-base",
            "--is-ancestor",
            prior_commit,
            plan.source_cut["commit"],
        )
    except (SelectorAllocationReviewError, UnicodeError) as error:
        _fail(
            "review transition source cut does not descend from the private "
            f"high-water commit: {error}"
        )


def _build_open_source_reanchor(
    repo_root: Path,
    *,
    current_control_raw: bytes,
    current_control: dict[str, Any],
    plan: ReviewPersistencePlan,
) -> dict[str, Any]:
    """Bind a clean descendant edit after reopen into the next promotion."""

    from selector_allocation_review import (
        ReviewGenerationState,
        review_state_bytes,
        verify_transition_source_cut,
    )

    _require(
        plan.action == "PROMOTE_TO_REVIEWED",
        "only promotion may re-anchor an open review source",
    )
    expected_state = plan.expected_state
    _require(
        isinstance(expected_state, ReviewGenerationState),
        "open-source re-anchor expected state is invalid",
    )
    expected_state.validate()
    _require(
        expected_state.active_assignment_sha256 is None
        and expected_state.active_inventory_sha256 is None
        and expected_state.current_receipt_sha256 is None
        and expected_state.last_consumed_receipt_sha256 is not None
        and expected_state.prior_state_sha256 is not None,
        "open-source re-anchor requires the exact post-reopen inactive state",
    )
    _require(
        current_control["tracked_state"] == expected_state.projection()
        and current_control["tracked_state_sha256"]
        == expected_state.commitment()["sha256"],
        "open-source re-anchor changed the tracked review state",
    )
    by_role = {item.role: item for item in plan.artifacts}
    _require(
        set(by_role) == set(REVIEW_ARTIFACT_ROLES)
        and by_role["review_generation_state"].expected_raw
        == review_state_bytes(expected_state),
        "open-source re-anchor does not bind the exact tracked state bytes",
    )
    inventory_raw = by_role["allocation_inventory"].expected_raw
    inventory = parse_json_bytes(
        inventory_raw,
        label="open-source re-anchor allocation inventory",
        maximum_bytes=_review_role_limit("allocation_inventory"),
    )
    _require(
        isinstance(inventory, dict)
        and inventory_raw == canonical_bytes(inventory) + b"\n"
        and isinstance(inventory.get("provenance_review"), dict)
        and inventory["provenance_review"].get("status") == "NOT_REVIEWED"
        and inventory["provenance_review"].get("reviewed_assignment_sha256")
        == "0" * 64,
        "open-source re-anchor inventory is not exactly NOT_REVIEWED",
    )
    _require(
        current_control_raw == _control_bytes(current_control),
        "open-source re-anchor prior control bytes changed",
    )
    _require_attached_control_ancestry(repo_root, current_control, plan)
    _require(
        current_control["last_source_commit"] != plan.source_cut["commit"],
        "open-source re-anchor requires a strict descendant source commit",
    )
    states = verify_transition_source_cut(
        repo_root,
        plan.source_cut,
        {item.role: (item.expected_raw, item.next_raw) for item in plan.artifacts},
    )
    _require(
        all(state == "EXPECTED" for state in states.values()),
        "open-source re-anchor must start from an exact clean committed cut",
    )
    reanchored_expected = _attached_artifact_commitments(
        plan.artifacts,
        use_next=False,
    )
    _require(
        current_control["tracked_artifacts"] != reanchored_expected,
        "unchanged attached artifacts do not require an open-source re-anchor",
    )
    value = {
        "ancestry": "PRIOR_COMMIT_IS_STRICT_ANCESTOR_OF_REANCHORED_COMMIT",
        "prior_attached": copy.deepcopy(current_control),
        "prior_attached_sha256": sha256(current_control_raw).hexdigest(),
        "prior_source_commit": current_control["last_source_commit"],
        "prior_source_tree": current_control["last_source_tree"],
        "prior_tracked_artifacts": copy.deepcopy(current_control["tracked_artifacts"]),
        "reanchored_expected_artifacts": reanchored_expected,
        "reanchored_source_commit": plan.source_cut["commit"],
        "reanchored_source_tree": plan.source_cut["tree"],
        "schema": REVIEW_OPEN_SOURCE_REANCHOR_SCHEMA,
    }
    return value


def _pending_control(
    repo_root: Path,
    plan: ReviewPersistencePlan,
    *,
    current_control_raw: bytes | None,
    current_control: dict[str, Any] | None,
) -> tuple[bytes, dict[str, Any]]:
    repository = plan.source_cut["repository"]
    open_source_reanchor: dict[str, Any] | None = None
    if current_control is None:
        from selector_allocation_review import ReviewGenerationState

        _require(
            plan.expected_state == ReviewGenerationState.genesis(),
            (
                "a missing private review high-water control can bootstrap "
                "only the exact tracked genesis state"
            ),
        )
        lineage_id = sha256(
            (
                "ncp.b01.selector-allocation.local-control-lineage.v1\x00"
                + repository
                + "\x00"
                + plan.source_cut["commit"]
                + "\x00"
                + plan.transition_subject_sha256
            ).encode("ascii")
        ).hexdigest()[:32]
        expected_attached_sha256 = "0" * 64
    else:
        expected_artifacts = _attached_artifact_commitments(
            plan.artifacts,
            use_next=False,
        )
        _require(
            current_control["status"] == "ATTACHED"
            and current_control["repository"] == repository
            and current_control["tracked_state"] == plan.expected_state.projection()
            and current_control["tracked_state_sha256"]
            == plan.expected_state.commitment()["sha256"],
            "private review high-water control differs from expected tracked state",
        )
        _require(
            current_control_raw is not None,
            "attached control bytes are absent",
        )
        if current_control["tracked_artifacts"] == expected_artifacts:
            _verify_attached_control_files(repo_root, current_control)
            _require_attached_control_ancestry(repo_root, current_control, plan)
        else:
            open_source_reanchor = _build_open_source_reanchor(
                repo_root,
                current_control_raw=current_control_raw,
                current_control=current_control,
                plan=plan,
            )
        lineage_id = current_control["control_lineage_id"]
        expected_attached_sha256 = sha256(current_control_raw).hexdigest()
    next_attached = _attached_control(
        lineage_id=lineage_id,
        repository=repository,
        source_cut=plan.source_cut,
        state=plan.next_state,
        artifacts=plan.artifacts,
    )
    pending = {
        "action": plan.action,
        "artifacts": [_artifact_control_item(item) for item in plan.artifacts],
        "authority_class": "LOCAL_ONLY",
        "claim_boundary": REVIEW_CONTROL_CLAIM_BOUNDARY,
        "control_lineage_id": lineage_id,
        "evidence_authority": False,
        "expected_attached_sha256": expected_attached_sha256,
        "expected_state": plan.expected_state.projection(),
        "external_authority": False,
        "independent_authority": False,
        "next_attached": next_attached,
        "next_state": plan.next_state.projection(),
        "open_source_reanchor": open_source_reanchor,
        "repository": repository,
        "review_receipt_sha256": plan.review_receipt_sha256,
        "reviewed_assignment_sha256": plan.reviewed_assignment_sha256,
        "schema": REVIEW_CONTROL_SCHEMA,
        "source_cut": copy.deepcopy(plan.source_cut),
        "status": "PENDING",
        "transition_subject_sha256": plan.transition_subject_sha256,
        "worktree_scope": "ONE_GIT_PRIVATE_WORKTREE_LINEAGE_ONLY",
        "write_order": list(plan.write_order),
    }
    _validate_review_control(pending)
    raw = canonical_bytes(pending) + b"\n"
    _require(
        len(raw) <= MAX_REVIEW_CONTROL_BYTES,
        "pending private review control exceeds its byte bound",
    )
    return raw, pending


def _control_bytes(value: dict[str, Any]) -> bytes:
    raw = canonical_bytes(value) + b"\n"
    _require(
        len(raw) <= MAX_REVIEW_CONTROL_BYTES,
        "private review control exceeds its byte bound",
    )
    return raw


def _verify_attached_control_files(
    repo_root: Path,
    control: dict[str, Any],
) -> None:
    """Require every tracked file to equal one attached high-water commitment."""

    _validate_review_control(control)
    _require(
        control["status"] == "ATTACHED",
        "attached-file verification requires an attached private control",
    )
    for item in control["tracked_artifacts"]:
        raw = read_bounded_regular_file(
            repo_root / item["path"],
            maximum_bytes=item["maximum_bytes"],
            label=f"attached private review artifact {item['role']}",
        )
        _require(
            len(raw) == item["byte_length"]
            and sha256(raw).hexdigest() == item["sha256"],
            f"attached private review artifact rolled back: {item['role']}",
        )


def _cleanup_exact_codec_temps(directory: Path, allowed_payloads: set[bytes]) -> int:
    """Remove only orphan codec temps whose bytes equal a pending target."""

    descriptor = -1
    removed = 0
    try:
        descriptor = os.open(
            directory,
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
        )
        opened = os.fstat(descriptor)
        _require(
            stat.S_ISDIR(opened.st_mode)
            and opened.st_uid == os.geteuid()
            and opened.st_mode & (stat.S_IWGRP | stat.S_IWOTH) == 0,
            "codec-temp parent is not an owner-managed directory",
        )
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        for name in os.listdir(descriptor):
            if CODEC_TEMP_NAME.fullmatch(name) is None:
                continue
            try:
                item = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
            except FileNotFoundError:
                continue
            _require(
                stat.S_ISREG(item.st_mode)
                and not stat.S_ISLNK(item.st_mode)
                and item.st_uid == os.geteuid()
                and item.st_nlink == 1
                and 0 < item.st_size <= MAX_REVIEW_CONTROL_BYTES,
                f"orphan codec temp is not a safe managed file: {name}",
            )
            child = os.open(
                name,
                os.O_RDONLY
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=descriptor,
            )
            try:
                chunks: list[bytes] = []
                remaining = item.st_size
                while remaining:
                    chunk = os.read(child, min(remaining, 64 * 1024))
                    _require(chunk, f"orphan codec temp truncated: {name}")
                    chunks.append(chunk)
                    remaining -= len(chunk)
                raw = b"".join(chunks)
            finally:
                os.close(child)
            _require(
                raw in allowed_payloads,
                f"foreign codec temp blocks deterministic recovery: {name}",
            )
            os.unlink(name, dir_fd=descriptor)
            removed += 1
        if removed:
            os.fsync(descriptor)
        return removed
    finally:
        if descriptor >= 0:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)


def _pending_artifacts(
    repo_root: Path,
    pending: dict[str, Any],
) -> tuple[ReviewArtifactTransition, ...]:
    artifacts: list[ReviewArtifactTransition] = []
    for item in pending["artifacts"]:
        role = item["role"]
        path = repo_root / item["path"]
        expected_raw = _decode_control_payload(item, prefix="expected")
        next_raw = _decode_control_payload(item, prefix="next")
        current_raw = read_bounded_regular_file(
            path,
            maximum_bytes=item["maximum_bytes"],
            label=f"pending review artifact {role}",
        )
        _require(
            current_raw in {expected_raw, next_raw},
            f"pending review artifact has third-state bytes: {role}",
        )
        artifacts.append(
            ReviewArtifactTransition(
                role=role,
                path=path,
                maximum_bytes=item["maximum_bytes"],
                expected_raw=expected_raw,
                next_raw=next_raw,
            )
        )
    return tuple(artifacts)


def _pending_inventory_artifact(
    repo_root: Path,
    pending: dict[str, Any],
) -> ReviewArtifactTransition:
    """Decode the journaled inventory pair without touching sibling artifacts."""

    item = next(
        entry
        for entry in pending["artifacts"]
        if entry["role"] == "allocation_inventory"
    )
    return ReviewArtifactTransition(
        role="allocation_inventory",
        path=repo_root / item["path"],
        maximum_bytes=item["maximum_bytes"],
        expected_raw=_decode_control_payload(item, prefix="expected"),
        next_raw=_decode_control_payload(item, prefix="next"),
    )


def _install_pending_inventory_fail_closed(
    repo_root: Path,
    pending: dict[str, Any],
    *,
    phase_hook: Any = None,
) -> str:
    """Put authority-bearing inventory in the non-reviewed side first."""

    inventory = _pending_inventory_artifact(repo_root, pending)
    current = read_bounded_regular_file(
        inventory.path,
        maximum_bytes=inventory.maximum_bytes,
        label="pending review fail-closed inventory",
    )
    if current == inventory.expected_raw:
        original_state = "EXPECTED"
    elif current == inventory.next_raw:
        original_state = "NEXT"
    else:
        original_state = "THIRD"
    poisoned = original_state == "THIRD"
    if pending["action"] == "PROMOTE_TO_REVIEWED":
        safe_raw = inventory.expected_raw
        unsafe_raw = inventory.next_raw
        label = "pending promotion inventory fail-closed rollback"
    else:
        safe_raw = inventory.next_raw
        unsafe_raw = inventory.expected_raw
        label = "pending reopen inventory fail-closed install"

    def inventory_phase(inner_phase: str) -> None:
        if phase_hook is not None:
            phase_hook(f"inventory:fail-closed:{inner_phase}")

    _reconcile_atomic_install(
        inventory.path,
        safe_raw,
        expected=(
            safe_raw
            if current == safe_raw
            else unsafe_raw
            if current == unsafe_raw
            else current
        ),
        maximum_bytes=inventory.maximum_bytes,
        label=label,
        phase_hook=inventory_phase,
    )
    installed = read_bounded_regular_file(
        inventory.path,
        maximum_bytes=inventory.maximum_bytes,
        label=f"{label} verification",
    )
    _require(installed == safe_raw, f"{label} did not install exact safe bytes")
    if phase_hook is not None:
        phase_hook("inventory:fail-closed:durable")
    _require(
        not poisoned,
        "pending review inventory had third-state bytes; exact safe bytes were "
        "installed and a fresh recovery attempt is required",
    )
    return original_state


def _artifact_states(
    repo_root: Path,
    pending: dict[str, Any],
    artifacts: tuple[ReviewArtifactTransition, ...],
) -> dict[str, str]:
    from selector_allocation_review import verify_transition_source_cut

    return verify_transition_source_cut(
        repo_root,
        pending["source_cut"],
        {
            artifact.role: (artifact.expected_raw, artifact.next_raw)
            for artifact in artifacts
        },
    )


def _require_legal_prefix(
    pending: dict[str, Any],
    states: dict[str, str],
) -> None:
    ordered = [states[role] for role in pending["write_order"]]
    seen_expected = False
    for state in ordered:
        if state == "EXPECTED":
            seen_expected = True
        else:
            _require(
                not seen_expected,
                "review transaction artifacts form an illegal non-prefix state",
            )


def _reconcile_atomic_install(
    path: Path,
    target: bytes,
    *,
    expected: bytes,
    maximum_bytes: int,
    label: str,
    phase_hook: Any = None,
) -> None:
    try:
        _atomic_replace_if_current(
            path,
            target,
            expected_current=expected,
            maximum_bytes=maximum_bytes,
            label=label,
            phase_hook=phase_hook,
        )
    except AtomicWriteOutcomeUnknownError:
        current = read_bounded_regular_file(
            path,
            maximum_bytes=maximum_bytes,
            label=f"{label} outcome reconciliation",
        )
        if current == target:
            # Seeing the renamed inode proves only visibility. The failed
            # parent-directory fsync left name durability unknown. Rewrite the
            # exact target through a fresh CAS so success includes a completed
            # parent-directory durability fence. If that fence is also
            # indeterminate, propagate the error instead of reporting durable.
            _atomic_replace_if_current(
                path,
                target,
                expected_current=target,
                maximum_bytes=maximum_bytes,
                label=f"{label} durability reconciliation",
                phase_hook=phase_hook,
            )
            return
        if current == expected:
            raise
        _fail(f"{label} reached third-state bytes after an unknown outcome")


def _recover_pending_locked(
    repo_root: Path,
    control_path: Path,
    control_raw: bytes,
    pending: dict[str, Any],
    *,
    phase_hook: Any = None,
) -> dict[str, Any]:
    """Recover one exact legal prefix to all-next and attach high-water state."""

    # Correct the only authority-bearing artifact before cleanup, Git reads,
    # sibling validation, journal re-fencing, or any other fallible recovery
    # work. Promotion rolls REVIEWED back to NOT_REVIEWED; reopen installs
    # NOT_REVIEWED first. Even a visible rollback with an indeterminate fsync is
    # safer than leaving authority exposed while control durability is retried.
    original_inventory_state = _install_pending_inventory_fail_closed(
        repo_root,
        pending,
        phase_hook=phase_hook,
    )

    # A prior create/rename may have made PENDING visible while its directory
    # fsync failed. Reinstall the identical journal through CAS before any
    # forward artifact mutation so the transaction descriptor itself is
    # durable. Inventory is already on the fail-closed side.
    _reconcile_atomic_install(
        control_path,
        control_raw,
        expected=control_raw,
        maximum_bytes=MAX_REVIEW_CONTROL_BYTES,
        label="pending review control durability fence",
        phase_hook=(
            (lambda phase: phase_hook(f"control:pending-fence:{phase}"))
            if phase_hook is not None
            else None
        ),
    )
    if phase_hook is not None:
        phase_hook("control:pending-fence:durable")

    artifacts = _pending_artifacts(repo_root, pending)
    allowed_artifact_payloads = {
        raw for item in artifacts for raw in (item.expected_raw, item.next_raw)
    }
    _cleanup_exact_codec_temps(
        (repo_root / _review_role_path("allocation_inventory")).parent,
        allowed_artifact_payloads,
    )
    next_attached_raw = _control_bytes(pending["next_attached"])
    _cleanup_exact_codec_temps(
        control_path.parent,
        {control_raw, next_attached_raw},
    )
    states = _artifact_states(repo_root, pending, artifacts)
    original_states = dict(states)
    original_states["allocation_inventory"] = original_inventory_state
    _require_legal_prefix(pending, original_states)
    _require_legal_prefix(pending, states)

    by_role = {item.role: item for item in artifacts}
    for role in pending["write_order"]:
        artifact = by_role[role]
        current = read_bounded_regular_file(
            artifact.path,
            maximum_bytes=artifact.maximum_bytes,
            label=f"review transaction current {role}",
        )
        if current == artifact.next_raw:
            continue
        _require(
            current == artifact.expected_raw,
            f"review transaction {role} changed before install",
        )

        def artifact_phase(inner_phase: str, *, artifact_role: str = role) -> None:
            if phase_hook is not None:
                phase_hook(f"artifact:{artifact_role}:{inner_phase}")

        _reconcile_atomic_install(
            artifact.path,
            artifact.next_raw,
            expected=artifact.expected_raw,
            maximum_bytes=artifact.maximum_bytes,
            label=f"review transaction {role}",
            phase_hook=artifact_phase,
        )
        if phase_hook is not None:
            phase_hook(f"artifact:{role}:durable")
        states = _artifact_states(repo_root, pending, artifacts)
        _require_legal_prefix(pending, states)

    final_states = _artifact_states(repo_root, pending, artifacts)
    _require(
        all(state == "NEXT" for state in final_states.values()),
        "review transaction did not install all exact target artifacts",
    )
    next_state = _validate_control_state_projection(
        pending["next_state"],
        label="completed review transaction state",
    )
    installed_state = read_bounded_regular_file(
        repo_root / _review_role_path("review_generation_state"),
        maximum_bytes=_review_role_limit("review_generation_state"),
        label="completed review transaction tracked state",
    )
    from selector_allocation_review import review_state_bytes

    _require(
        installed_state == review_state_bytes(next_state),
        "completed review transaction state bytes are inconsistent",
    )

    def control_phase(inner_phase: str) -> None:
        if phase_hook is not None:
            phase_hook(f"control:attach:{inner_phase}")

    _reconcile_atomic_install(
        control_path,
        next_attached_raw,
        expected=control_raw,
        maximum_bytes=MAX_REVIEW_CONTROL_BYTES,
        label="review transaction attach high-water control",
        phase_hook=control_phase,
    )
    if phase_hook is not None:
        phase_hook("control:attached:durable")
    loaded = _read_optional_control(control_path)
    _require(
        loaded is not None
        and loaded[0] == next_attached_raw
        and loaded[1] == pending["next_attached"],
        "review transaction high-water attachment differs after install",
    )
    return pending["next_attached"]


def apply_review_persistence_plan(
    repo_root: Path,
    plan: ReviewPersistencePlan,
    *,
    phase_hook: Any = None,
) -> dict[str, Any]:
    """Journal, apply, recover, and attach one local-only review transition."""

    with _review_control_lock(repo_root) as control_lease:
        control_path = _require_active_review_control_lease(
            repo_root,
            control_lease,
        )
        current = _read_optional_control(control_path)
        current_raw = current[0] if current else None
        current_control = current[1] if current else None
        if current_control is not None and current_control["status"] == "PENDING":
            _require(
                current_control["transition_subject_sha256"]
                == plan.transition_subject_sha256,
                "a different review transition is already pending",
            )
            return _recover_pending_locked(
                repo_root,
                control_path,
                current_raw,
                current_control,
                phase_hook=phase_hook,
            )
        pending_raw, pending = _pending_control(
            repo_root,
            plan,
            current_control_raw=current_raw,
            current_control=current_control,
        )
        _cleanup_exact_codec_temps(
            control_path.parent,
            {pending_raw, _control_bytes(pending["next_attached"])},
        )
        if current is None:
            _atomic_write_regular_file(
                control_path,
                pending_raw,
                label="review transaction initial pending control",
                create_only=True,
                create_mode=0o600,
                phase_hook=(
                    (lambda phase: phase_hook(f"control:pending:{phase}"))
                    if phase_hook is not None
                    else None
                ),
            )
        else:
            _reconcile_atomic_install(
                control_path,
                pending_raw,
                expected=current_raw,
                maximum_bytes=MAX_REVIEW_CONTROL_BYTES,
                label="review transaction pending control",
                phase_hook=(
                    (lambda phase: phase_hook(f"control:pending:{phase}"))
                    if phase_hook is not None
                    else None
                ),
            )
        if phase_hook is not None:
            phase_hook("control:pending:durable")
        installed = _read_optional_control(control_path)
        _require(
            installed is not None and installed[0] == pending_raw,
            "review transaction pending control was not installed exactly",
        )
        return _recover_pending_locked(
            repo_root,
            control_path,
            pending_raw,
            pending,
            phase_hook=phase_hook,
        )


def recover_pending_review_transition(
    repo_root: Path,
    *,
    phase_hook: Any = None,
) -> dict[str, Any] | None:
    """Recover the exact pending private control, if one exists."""

    with _review_control_lock(repo_root) as control_lease:
        control_path = _require_active_review_control_lease(
            repo_root,
            control_lease,
        )
        current = _read_optional_control(control_path)
        if current is None:
            return None
        raw, control = current
        if control["status"] == "ATTACHED":
            _verify_attached_control_files(repo_root, control)
            return control
        return _recover_pending_locked(
            repo_root,
            control_path,
            raw,
            control,
            phase_hook=phase_hook,
        )


def apply_local_review_promotion(
    repo_root: Path,
    review_document_path: Path,
    policy: Any,
    *,
    phase_hook: Any = None,
) -> dict[str, Any]:
    """Apply one caller-authorized local-only promotion; authenticate no identity."""

    from selector_allocation_review import (
        REVIEW_STATE_SCHEMA_FILE,
        load_review_document,
        load_review_generation_state,
        plan_review_promotion,
    )

    repo_root = repo_root.resolve(strict=True)
    authoring_path = repo_root / _review_role_path("semantic_authoring_source")
    schema_path = repo_root / _review_role_path("semantic_authoring_schema")
    compact_path = repo_root / _review_role_path("semantic_compact_source")
    state_path = repo_root / _review_role_path("review_generation_state")
    state = load_review_generation_state(
        state_path,
        state_path.with_name(REVIEW_STATE_SCHEMA_FILE),
    )
    document = load_review_document(review_document_path)
    transition = plan_review_promotion(
        repo_root,
        document,
        policy,
        state,
    )
    plan = prepare_review_persistence_plan(
        repo_root,
        transition,
        authoring_path=authoring_path,
        schema_path=schema_path,
        compact_path=compact_path,
        state_path=state_path,
    )
    return apply_review_persistence_plan(
        repo_root,
        plan,
        phase_hook=phase_hook,
    )


def apply_local_review_reopen(
    repo_root: Path,
    active_review_document_path: Path,
    policy: Any,
    *,
    reason: str,
    phase_hook: Any = None,
) -> dict[str, Any]:
    """Reopen one exact active local receipt and fail closed before other writes."""

    from selector_allocation_review import (
        REVIEW_STATE_SCHEMA_FILE,
        load_review_document,
        load_review_generation_state,
        plan_review_reopen,
        snapshot_review_source,
        validate_active_review_for_reopen,
    )

    repo_root = repo_root.resolve(strict=True)
    source_commit = (
        _run_review_git(repo_root, "rev-parse", "--verify", "HEAD")
        .decode("ascii")
        .strip()
    )
    source_snapshot = snapshot_review_source(
        repo_root,
        source_commit,
        policy,
        require_current_clean_head=True,
    )
    authoring_path = repo_root / _review_role_path("semantic_authoring_source")
    schema_path = repo_root / _review_role_path("semantic_authoring_schema")
    compact_path = repo_root / _review_role_path("semantic_compact_source")
    state_path = repo_root / _review_role_path("review_generation_state")
    state = load_review_generation_state(
        state_path,
        state_path.with_name(REVIEW_STATE_SCHEMA_FILE),
    )
    authoring_schema = load_authoring_schema(schema_path)
    authoring = load_authoring_source(authoring_path, authoring_schema)
    allocation = load_bound_allocation_inventory(
        authoring_path.parent,
        authoring[ALLOCATION_BINDING_KEY],
    )
    active_document = load_review_document(active_review_document_path)
    validate_active_review_for_reopen(
        repo_root,
        active_document,
        policy,
        state,
        allocation.inventory,
    )
    transition = plan_review_reopen(
        allocation.inventory,
        allocation.schema,
        allocation.schema_raw,
        state,
        reason=reason,
        source_cut=source_snapshot.source_cut,
    )
    plan = prepare_review_persistence_plan(
        repo_root,
        transition,
        authoring_path=authoring_path,
        schema_path=schema_path,
        compact_path=compact_path,
        state_path=state_path,
    )
    return apply_review_persistence_plan(
        repo_root,
        plan,
        phase_hook=phase_hook,
    )


def _run_review_git(repo_root: Path, *arguments: str) -> bytes:
    from selector_allocation_review import _run_git

    return _run_git(repo_root, *arguments, maximum_output_bytes=4096)


def _load_unbound_allocation_inventory(
    path: Path,
    schema: dict[str, Any],
) -> tuple[bytes, dict[str, Any]]:
    """Load a canonical inventory without trusting a potentially stale binding."""

    raw = read_bounded_regular_file(
        path,
        maximum_bytes=MAX_ALLOCATION_INVENTORY_BYTES,
        label="selector allocation inventory refresh input",
    )
    inventory = parse_json_bytes(raw, label=str(path))
    _require(isinstance(inventory, dict), "allocation inventory must be an object")
    _require(
        raw == inventory_bytes(inventory),
        "allocation inventory refresh input is not canonical JSON",
    )
    validate_allocation_inventory(inventory, schema)
    return raw, inventory


def _load_canonical_unvalidated_allocation_inventory(
    path: Path,
) -> tuple[bytes, dict[str, Any]]:
    """Load bounded canonical bytes without granting schema compatibility."""

    raw = read_bounded_regular_file(
        path,
        maximum_bytes=MAX_ALLOCATION_INVENTORY_BYTES,
        label="legacy selector allocation inventory migration input",
    )
    inventory = parse_json_bytes(raw, label=str(path))
    _require(isinstance(inventory, dict), "allocation inventory must be an object")
    _require(
        raw == inventory_bytes(inventory),
        "legacy allocation inventory migration input is not canonical JSON",
    )
    return raw, inventory


def _classify_exact_incomplete_migration_pair(
    *,
    authoring_raw: bytes,
    inventory_raw: bytes,
    predecessor: ExactMigrationCut,
    successor: ExactMigrationCut,
) -> str:
    """Admit only predecessor, authoring-first recovery, or exact replay."""

    predecessor.validate(label="predecessor")
    successor.validate(label="successor")
    _require(
        predecessor != successor
        and predecessor.authoring != successor.authoring
        and predecessor.inventory != successor.inventory,
        "migration predecessor and successor cuts are not pairwise distinct",
    )
    predecessor_authoring = predecessor.authoring.matches(authoring_raw)
    predecessor_inventory = predecessor.inventory.matches(inventory_raw)
    successor_authoring = successor.authoring.matches(authoring_raw)
    successor_inventory = successor.inventory.matches(inventory_raw)
    if predecessor_authoring and predecessor_inventory:
        return "EXACT_PREDECESSOR"
    if successor_authoring and predecessor_inventory:
        return "AUTHORING_FIRST_RECOVERY"
    if successor_authoring and successor_inventory:
        return "EXACT_COMPLETED_REPLAY"
    _fail(
        "migration artifact pair is neither the exact predecessor, the "
        "authoring-first recovery prefix, nor the exact completed successor"
    )


def _require_exact_maintained_migration_domain(
    *,
    source_root: Path,
    authoring_path: Path,
    schema_path: Path,
) -> Path:
    """Bind the one-use migration and its lock to the maintained repository."""

    try:
        physical_root = source_root.resolve(strict=True)
    except OSError as error:
        _fail(f"cannot resolve migration repository root: {error}")
    _require(
        stat.S_ISDIR(physical_root.lstat().st_mode) and not physical_root.is_symlink(),
        "migration repository root must be one physical directory",
    )
    expected = {
        "authoring source": physical_root
        / _review_role_path("semantic_authoring_source"),
        "authoring schema": physical_root
        / _review_role_path("semantic_authoring_schema"),
    }
    provided = {
        "authoring source": Path(os.path.abspath(os.fspath(authoring_path))),
        "authoring schema": Path(os.path.abspath(os.fspath(schema_path))),
    }
    for label, expected_path in expected.items():
        actual_path = provided[label]
        _require(
            actual_path == expected_path,
            f"migration {label} is outside its exact maintained role path",
        )
        try:
            actual_physical = actual_path.resolve(strict=True)
            expected_physical = expected_path.resolve(strict=True)
        except OSError as error:
            _fail(f"cannot resolve migration {label}: {error}")
        _require(
            actual_physical == expected_physical,
            f"migration {label} does not resolve to its maintained role",
        )
    return physical_root


def _snapshot_exact_incomplete_migration_boundary(
    *,
    authoring_path: Path,
    review_control_path: Path,
    source_root: Path,
) -> tuple[IncompleteRefreshGuardSnapshot, ...]:
    """Pin the local-only genesis/no-control boundary for one migration."""

    from selector_allocation_review import (
        MAX_REVIEW_STATE_BYTES,
        MAX_REVIEW_STATE_SCHEMA_BYTES,
        REVIEW_STATE_FILE,
        REVIEW_STATE_SCHEMA_FILE,
        ReviewGenerationState,
        SelectorAllocationReviewError,
        load_review_generation_state,
        review_state_bytes,
    )

    expected_control_path = _git_private_path(source_root, REVIEW_CONTROL_FILE)
    compact_path = source_root / _review_role_path("semantic_compact_source")
    _require(
        review_control_path == expected_control_path,
        "incomplete migration requires the fixed private review-control path",
    )
    _require_absent_path(
        review_control_path,
        label="incomplete migration private review control",
    )
    _require_absent_path(
        compact_path,
        label="incomplete migration compact source",
    )
    state_path = authoring_path.with_name(REVIEW_STATE_FILE)
    state_schema_path = authoring_path.with_name(REVIEW_STATE_SCHEMA_FILE)
    state_schema_raw = read_bounded_regular_file(
        state_schema_path,
        maximum_bytes=MAX_REVIEW_STATE_SCHEMA_BYTES,
        label="incomplete migration review-state schema snapshot",
    )
    state_raw = read_bounded_regular_file(
        state_path,
        maximum_bytes=MAX_REVIEW_STATE_BYTES,
        label="incomplete migration review-state snapshot",
    )
    try:
        state = load_review_generation_state(state_path, state_schema_path)
    except SelectorAllocationReviewError as error:
        _fail(f"incomplete migration review state is invalid: {error}")
    _require(
        state == ReviewGenerationState.genesis()
        and state_raw == review_state_bytes(ReviewGenerationState.genesis()),
        "incomplete migration requires the exact genesis review state",
    )
    _require(
        read_bounded_regular_file(
            state_schema_path,
            maximum_bytes=MAX_REVIEW_STATE_SCHEMA_BYTES,
            label="incomplete migration review-state schema stability check",
        )
        == state_schema_raw
        and read_bounded_regular_file(
            state_path,
            maximum_bytes=MAX_REVIEW_STATE_BYTES,
            label="incomplete migration review-state stability check",
        )
        == state_raw
        and _read_optional_control(review_control_path) is None,
        "incomplete migration boundary changed while it was loaded",
    )
    _require_absent_path(
        compact_path,
        label="incomplete migration compact source stability check",
    )
    return (
        IncompleteRefreshGuardSnapshot(
            label="private review control",
            maximum_bytes=MAX_REVIEW_CONTROL_BYTES,
            path=review_control_path,
            raw=None,
        ),
        IncompleteRefreshGuardSnapshot(
            label="compact source",
            maximum_bytes=MAX_COMPACT_BYTES,
            path=compact_path,
            raw=None,
        ),
        IncompleteRefreshGuardSnapshot(
            label="review-generation state",
            maximum_bytes=MAX_REVIEW_STATE_BYTES,
            path=state_path,
            raw=state_raw,
        ),
        IncompleteRefreshGuardSnapshot(
            label="review-state schema",
            maximum_bytes=MAX_REVIEW_STATE_SCHEMA_BYTES,
            path=state_schema_path,
            raw=state_schema_raw,
        ),
    )


def _prepare_exact_bridge_v1_profile_migration(
    *,
    authoring: dict[str, Any],
    schema: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """Install the exact schema-bound bridge and executable-evidence cut."""

    expected_v1_raw = canonical_bytes(BRIDGE_V1_MIGRATION_PROFILE)
    _require(
        len(expected_v1_raw) == BRIDGE_V1_MIGRATION_PROFILE_CANONICAL_BYTE_LENGTH
        and sha256(expected_v1_raw).hexdigest()
        == BRIDGE_V1_MIGRATION_PROFILE_CANONICAL_SHA256,
        "embedded bridge-v1 migration predecessor changed",
    )
    target_profile = _authoring_schema_bridge_profile(
        schema,
        expected_schema=BRIDGE_V2_MIGRATION_PROFILE_SCHEMA,
    )
    target_probe_bindings = _authoring_schema_probe_bindings(schema)
    profile = authoring.get(OBSERVER_BRIDGE_PROFILE_KEY)
    probe_bindings = authoring.get(ADVERSARIAL_PROBE_BINDINGS_KEY)
    legacy_profile = (
        isinstance(profile, dict)
        and profile == BRIDGE_V1_MIGRATION_PROFILE
        and profile.get("schema") == BRIDGE_V1_MIGRATION_PROFILE_SCHEMA
        and len(canonical_bytes(profile))
        == BRIDGE_V1_MIGRATION_PROFILE_CANONICAL_BYTE_LENGTH
        and sha256(canonical_bytes(profile)).hexdigest()
        == BRIDGE_V1_MIGRATION_PROFILE_CANONICAL_SHA256
    )
    legacy_cut = legacy_profile and probe_bindings == BRIDGE_V1_MIGRATION_PROBE_BINDINGS
    already_target = (
        profile == target_profile and probe_bindings == target_probe_bindings
    )
    _require(
        legacy_cut or already_target,
        (
            "observer bridge/probe migration input is neither the exact "
            "maintained v1 evidence cut nor the exact authoring-schema target"
        ),
    )
    seeded = copy.deepcopy(authoring)
    seeded[OBSERVER_BRIDGE_PROFILE_KEY] = target_profile
    seeded[ADVERSARIAL_PROBE_BINDINGS_KEY] = target_probe_bindings
    preserved = copy.deepcopy(authoring)
    preserved.pop(OBSERVER_BRIDGE_PROFILE_KEY, None)
    preserved.pop(ADVERSARIAL_PROBE_BINDINGS_KEY, None)
    seeded_preserved = copy.deepcopy(seeded)
    seeded_preserved.pop(OBSERVER_BRIDGE_PROFILE_KEY, None)
    seeded_preserved.pop(ADVERSARIAL_PROBE_BINDINGS_KEY, None)
    _require(
        seeded_preserved == preserved,
        "bridge/probe migration changed unrelated authoring content",
    )
    _validate_schema_instance(seeded, schema)
    return seeded, legacy_cut


def _prepare_exact_v2_empty_inventory_migration(
    *,
    allocation_schema: dict[str, Any],
    allocation_schema_raw: bytes,
    authoring: dict[str, Any],
    inventory: dict[str, Any],
    review_control_path: Path,
    state_path: Path,
) -> dict[str, Any]:
    """Admit only the exact fail-closed v2 predecessor and return a v4 seed."""

    from selector_allocation_review import (
        REVIEW_STATE_SCHEMA_FILE,
        ReviewGenerationState,
        SelectorAllocationReviewError,
        load_review_generation_state,
    )

    _require(
        len(allocation_schema_raw) == V2_EMPTY_MIGRATION_TARGET_SCHEMA_BYTE_LENGTH
        and sha256(allocation_schema_raw).hexdigest()
        == V2_EMPTY_MIGRATION_TARGET_SCHEMA_SHA256,
        "v2-empty migration target is not the exact v4 schema bytes",
    )
    _require(
        _read_optional_control(review_control_path) is None,
        "v2-empty migration requires an absent private review control",
    )
    try:
        state = load_review_generation_state(
            state_path,
            state_path.with_name(REVIEW_STATE_SCHEMA_FILE),
        )
    except SelectorAllocationReviewError as error:
        _fail(f"v2-empty migration review state is invalid: {error}")
    _require(
        state == ReviewGenerationState.genesis(),
        "v2-empty migration requires the exact genesis review state",
    )
    _require(
        inventory.get("status") == "INCOMPLETE_FAIL_CLOSED"
        and inventory.get("allocations") == []
        and inventory.get("exclusions") == [],
        (
            "v2-empty migration requires an exact fail-closed inventory "
            "without assignment or exclusion rows"
        ),
    )
    if (
        isinstance(inventory.get("allocation_review_profile"), dict)
        and inventory["allocation_review_profile"].get("schema")
        == ALLOCATION_REVIEW_PROFILE_SCHEMA
    ):
        # The exact successor is an idempotent no-op.  This does not widen the
        # migration input: the complete current schema and semantic validators
        # still apply, and the candidate remains empty, unreviewed, genesis,
        # and without private transition control.
        validate_allocation_inventory(inventory, allocation_schema)
        validate_allocation_review_profile_schema_binding(
            inventory,
            allocation_schema_raw,
        )
        _require(
            inventory["provenance_review"]["status"] == "NOT_REVIEWED"
            and inventory["provenance_review"]["reviewed_assignment_sha256"]
            == "0" * 64,
            "v2-empty migration successor is not exactly unreviewed",
        )
        return copy.deepcopy(inventory)
    _require(
        inventory.get("document_row_commitment")
        == V2_EMPTY_MIGRATION_DOCUMENT_ROW_COMMITMENT,
        "v2-empty migration document-row suite differs from the exact v2 tuple",
    )
    _require(
        inventory.get("allocation_review_profile") == V2_EMPTY_MIGRATION_PROFILE,
        "v2-empty migration profile differs from the exact maintained v2 tuple",
    )
    _require(
        inventory.get("provenance_review") == V2_EMPTY_MIGRATION_PROVENANCE_REVIEW,
        "v2-empty migration provenance differs from the exact unreviewed v2 tuple",
    )
    _require(
        inventory.get("semantic_review_subject")
        == V2_EMPTY_MIGRATION_SEMANTIC_REVIEW_SUBJECT,
        (
            "v2-empty migration semantic subject differs from the exact "
            "maintained v2 predecessor"
        ),
    )
    _require(
        inventory.get("model_allocation_count")
        == V2_EMPTY_MIGRATION_PROFILE["model_allocation_count"]
        and inventory.get("model_allocation_sha256")
        == V2_EMPTY_MIGRATION_PROFILE["model_allocation_sha256"]
        and inventory.get("semantic_shape_entry_count")
        == V2_EMPTY_MIGRATION_PROFILE["semantic_shape_entry_count"]
        and inventory.get("semantic_shape_sha256")
        == V2_EMPTY_MIGRATION_PROFILE["semantic_shape_sha256"]
        and inventory.get("required_kinds") == list(ALLOCATION_KINDS),
        "v2-empty migration top-level model taxonomy differs from its profile",
    )
    empty_allocation_sha256 = document_rows_sha256(
        [],
        row_kind="allocations",
    )
    empty_exclusion_sha256 = document_rows_sha256(
        [],
        row_kind="exclusions",
    )
    documents = inventory.get("documents")
    _require(
        isinstance(documents, list) and len(documents) == len(ADR_ALLOCATION_PATHS),
        "v2-empty migration has an unexpected ADR document inventory",
    )
    document_keys = {
        "adr_id",
        "allocation_anchor_id",
        "allocation_row_count",
        "allocation_rows_sha256",
        "byte_length",
        "exclusion_row_count",
        "exclusion_rows_sha256",
        "modules",
        "path",
        "sha256",
        "source_set",
    }
    module_keys = {"byte_length", "path", "sha256"}
    for index, document in enumerate(documents):
        expected_adr_id = f"ADR-{index + 1:03d}"
        expected_module_paths = ADR_ALLOCATION_MODULE_PATHS[index]
        _require(
            isinstance(document, dict)
            and set(document) == document_keys
            and document["adr_id"] == expected_adr_id
            and document["allocation_anchor_id"] == ADR_ALLOCATION_ANCHOR_IDS[index]
            and document["path"] == ADR_ALLOCATION_PATHS[index]
            and document["allocation_row_count"] == 0
            and document["allocation_rows_sha256"] == empty_allocation_sha256
            and document["exclusion_row_count"] == 0
            and document["exclusion_rows_sha256"] == empty_exclusion_sha256
            and isinstance(document["byte_length"], int)
            and not isinstance(document["byte_length"], bool)
            and 0 < document["byte_length"] <= MAX_ADR_DOCUMENT_BYTES
            and isinstance(document["sha256"], str)
            and re.fullmatch(r"[0-9a-f]{64}", document["sha256"]) is not None
            and isinstance(document["modules"], list)
            and len(document["modules"]) == len(expected_module_paths),
            f"v2-empty migration ADR snapshot is invalid: {expected_adr_id}",
        )
        for module_index, (module, expected_path) in enumerate(
            zip(
                document["modules"],
                expected_module_paths,
                strict=True,
            )
        ):
            _require(
                isinstance(module, dict)
                and set(module) == module_keys
                and module["path"] == expected_path
                and isinstance(module["byte_length"], int)
                and not isinstance(module["byte_length"], bool)
                and 0 < module["byte_length"] <= MAX_ADR_DOCUMENT_BYTES
                and isinstance(module["sha256"], str)
                and re.fullmatch(r"[0-9a-f]{64}", module["sha256"]) is not None,
                (
                    "v2-empty migration ADR module snapshot is invalid: "
                    f"{expected_adr_id}[{module_index}]"
                ),
            )
        source_set = document["source_set"]
        _require(
            isinstance(source_set, dict)
            and set(source_set)
            == set(V2_EMPTY_MIGRATION_ADR_SOURCE_SET_SUITE) | {"sha256"}
            and all(
                source_set[key] == value
                for key, value in V2_EMPTY_MIGRATION_ADR_SOURCE_SET_SUITE.items()
            )
            and source_set["sha256"]
            == adr_source_set_sha256(
                adr_id=document["adr_id"],
                path=document["path"],
                byte_length=document["byte_length"],
                source_sha256=document["sha256"],
                modules=document["modules"],
            ),
            (
                "v2-empty migration ADR source-set commitment is invalid: "
                f"{expected_adr_id}"
            ),
        )

    migrated = copy.deepcopy(inventory)
    migrated["document_row_commitment"] = copy.deepcopy(DOCUMENT_ROW_COMMITMENT)
    # Semantic-shape v3 commits the profile's JSON structure. Seed the complete
    # target profile before the metric pass so the pass does not hash the legacy
    # v2 profile shape and then install a structurally different v4 profile.
    migrated["allocation_review_profile"] = build_allocation_review_profile(
        allocation_schema_raw=allocation_schema_raw,
        model_allocation_count=V2_EMPTY_MIGRATION_PROFILE["model_allocation_count"],
        model_allocation_sha256=V2_EMPTY_MIGRATION_PROFILE["model_allocation_sha256"],
        model_origin_signal_row_count=V2_EMPTY_MIGRATION_PROFILE[
            "model_allocation_count"
        ],
        model_origin_signal_sha256="0" * 64,
        resource_closure_row_count=V2_EMPTY_MIGRATION_PROFILE[
            "resource_closure_row_count"
        ],
        resource_closure_sha256=V2_EMPTY_MIGRATION_PROFILE["resource_closure_sha256"],
        semantic_shape_entry_count=V2_EMPTY_MIGRATION_PROFILE[
            "semantic_shape_entry_count"
        ],
        semantic_shape_sha256=V2_EMPTY_MIGRATION_PROFILE["semantic_shape_sha256"],
    )
    migrated["provenance_review"] = build_not_reviewed_provenance_review()
    migrated["semantic_review_subject"] = semantic_review_subject_commitment(
        _restore_canonical_source_envelope(
            authoring,
            inventory_to_oracle(migrated),
        )
    )
    return migrated


def _refresh_inventory_document_snapshots(
    inventory: dict[str, Any],
    *,
    source_root: Path,
) -> tuple[dict[str, Any], tuple[tuple[Path, bytes], ...]]:
    """Refresh exact ADR main/module bytes without changing provenance rows."""

    refreshed = copy.deepcopy(inventory)
    source_snapshots: list[tuple[Path, bytes]] = []
    for document in refreshed["documents"]:
        main_path = source_root / document["path"]
        main_raw = read_bounded_regular_file(
            main_path,
            maximum_bytes=MAX_ADR_DOCUMENT_BYTES,
            label=f"{document['adr_id']} refresh main source",
        )
        document["byte_length"] = len(main_raw)
        document["sha256"] = sha256(main_raw).hexdigest()
        source_snapshots.append((main_path, main_raw))
        for module in document["modules"]:
            module_path = source_root / module["path"]
            module_raw = read_bounded_regular_file(
                module_path,
                maximum_bytes=MAX_ADR_DOCUMENT_BYTES,
                label=f"{document['adr_id']} refresh module source",
            )
            module["byte_length"] = len(module_raw)
            module["sha256"] = sha256(module_raw).hexdigest()
            source_snapshots.append((module_path, module_raw))
        document["source_set"] = copy.deepcopy(ADR_SOURCE_SET_SUITE)
        document["source_set"]["sha256"] = adr_source_set_sha256(
            adr_id=document["adr_id"],
            path=document["path"],
            byte_length=document["byte_length"],
            source_sha256=document["sha256"],
            modules=document["modules"],
        )
    _require(
        len(source_snapshots)
        == len({path.resolve(strict=True) for path, _ in source_snapshots}),
        "ADR refresh source inventory aliases one physical file",
    )
    return refreshed, tuple(source_snapshots)


def _default_incomplete_refresh_metrics(
    canonical: dict[str, Any],
) -> tuple[int, str, int, str, int, str]:
    """Compute the checker-owned model and semantic-shape commitments."""

    from check_selector_closure import (  # Imported lazily to avoid CLI cycles.
        _model_allocation_sha256,
        _model_allocations,
        _model_origin_signal_commitment,
        _semantic_shape_commitment,
    )

    model = _model_allocations(canonical)
    origin_signal_count, origin_signal_sha256 = _model_origin_signal_commitment(model)
    shape_count, shape_sha256 = _semantic_shape_commitment(canonical)
    return (
        len(model),
        _model_allocation_sha256(model),
        origin_signal_count,
        origin_signal_sha256,
        shape_count,
        shape_sha256,
    )


def _incomplete_refresh_preserved_inventory_projection(
    inventory: dict[str, Any],
) -> dict[str, Any]:
    """Return every field that source-snapshot refresh must not change."""

    preserved = copy.deepcopy(inventory)
    for key in (
        "allocation_review_profile",
        "model_allocation_count",
        "model_allocation_sha256",
        "semantic_review_subject",
        "semantic_shape_entry_count",
        "semantic_shape_sha256",
    ):
        preserved.pop(key)
    for document in preserved["documents"]:
        document.pop("byte_length")
        document.pop("sha256")
        document.pop("source_set")
        for module in document["modules"]:
            module.pop("byte_length")
            module.pop("sha256")
    return preserved


def _build_incomplete_refresh_plan(
    authoring: dict[str, Any],
    inventory: dict[str, Any],
    allocation_schema_raw: bytes,
    *,
    source_root: Path,
    metric_provider: Any = None,
) -> IncompleteRefreshPlan:
    """Build canonical commitments before deriving the maintained envelope."""

    preserved_inventory = _incomplete_refresh_preserved_inventory_projection(inventory)
    preserved_allocations = copy.deepcopy(inventory["allocations"])
    preserved_exclusions = copy.deepcopy(inventory["exclusions"])
    preserved_provenance_review = copy.deepcopy(inventory["provenance_review"])
    preserved_status = inventory["status"]
    refreshed_inventory, adr_sources = _refresh_inventory_document_snapshots(
        inventory,
        source_root=source_root,
    )
    metric_provider = metric_provider or _default_incomplete_refresh_metrics
    metric_source = _restore_canonical_source_envelope(
        authoring,
        inventory_to_oracle(refreshed_inventory),
    )
    metrics = metric_provider(metric_source)
    _require(
        isinstance(metrics, tuple) and len(metrics) == 6,
        "incomplete refresh metric provider returned an invalid result",
    )
    (
        model_count,
        model_sha256,
        origin_signal_count,
        origin_signal_sha256,
        shape_count,
        shape_sha256,
    ) = metrics
    _require(
        isinstance(model_count, int)
        and not isinstance(model_count, bool)
        and model_count > 0,
        "incomplete refresh model count is invalid",
    )
    _require(
        isinstance(shape_count, int)
        and not isinstance(shape_count, bool)
        and shape_count > 0,
        "incomplete refresh semantic-shape count is invalid",
    )
    _require(
        isinstance(origin_signal_count, int)
        and not isinstance(origin_signal_count, bool)
        and origin_signal_count == model_count,
        "incomplete refresh origin/signal rows do not cover every model unit",
    )
    for digest, label in (
        (model_sha256, "model"),
        (origin_signal_sha256, "origin/signal"),
        (shape_sha256, "semantic-shape"),
    ):
        _require(
            isinstance(digest, str)
            and re.fullmatch(r"[0-9a-f]{64}", digest) is not None,
            f"incomplete refresh {label} digest is invalid",
        )
    _, resource_closure = derive_resource_closure(metric_source)
    refreshed_inventory["model_allocation_count"] = model_count
    refreshed_inventory["model_allocation_sha256"] = model_sha256
    refreshed_inventory["allocation_review_profile"] = build_allocation_review_profile(
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
    refreshed_inventory["semantic_review_subject"] = semantic_review_subject_commitment(
        metric_source
    )
    refreshed_inventory["semantic_shape_entry_count"] = shape_count
    refreshed_inventory["semantic_shape_sha256"] = shape_sha256
    _require(
        _incomplete_refresh_preserved_inventory_projection(refreshed_inventory)
        == preserved_inventory,
        "incomplete refresh changed an author-maintained inventory field",
    )
    _require(
        refreshed_inventory["allocations"] == preserved_allocations,
        "incomplete refresh changed allocation rows",
    )
    _require(
        refreshed_inventory["exclusions"] == preserved_exclusions,
        "incomplete refresh changed exclusion rows",
    )
    _require(
        refreshed_inventory["provenance_review"] == preserved_provenance_review,
        "incomplete refresh changed provenance review state",
    )
    _require(
        refreshed_inventory["status"] == preserved_status,
        "incomplete refresh changed inventory status",
    )

    inventory_raw = inventory_bytes(refreshed_inventory)
    allocation_binding = build_inventory_binding(
        inventory_raw,
        allocation_schema_raw,
    )
    canonical = _restore_canonical_source_envelope(
        authoring,
        inventory_to_oracle(refreshed_inventory),
    )
    _recompute_closure_commitments(canonical)
    refreshed_authoring = prepare_authoring_source(
        canonical,
        allocation_binding,
    )
    authoring_raw = _authoring_bytes(refreshed_authoring)
    _require(
        prepare_canonical_source(
            refreshed_authoring,
            inventory_to_oracle(refreshed_inventory),
        )
        == canonical,
        "refreshed authoring does not reconstruct its canonical source",
    )
    return IncompleteRefreshPlan(
        adr_sources=adr_sources,
        authoring=refreshed_authoring,
        authoring_raw=authoring_raw,
        canonical=canonical,
        inventory=refreshed_inventory,
        inventory_raw=inventory_raw,
    )


def _verify_incomplete_refresh_inputs_unchanged(
    *,
    allocation_inventory_path: Path,
    allocation_schema_path: Path,
    authoring_path: Path,
    schema_path: Path,
    snapshot: IncompleteRefreshInputSnapshot,
    expected_authoring_raw: bytes,
    expected_inventory_raw: bytes,
) -> None:
    """Recheck every exact input snapshot around both atomic installs."""

    for guard in snapshot.guards:
        if guard.raw is None:
            _require_absent_path(
                guard.path,
                label=f"{guard.label} during incomplete migration",
            )
            continue
        current_guard = read_bounded_regular_file(
            guard.path,
            maximum_bytes=guard.maximum_bytes,
            label=f"{guard.label} migration stability check",
        )
        _require(
            current_guard == guard.raw,
            f"{guard.label} changed during incomplete migration",
        )
    current_authoring = read_bounded_regular_file(
        authoring_path,
        maximum_bytes=MAX_EXPANDED_BYTES,
        label="selector authoring refresh stability check",
    )
    current_inventory = read_bounded_regular_file(
        allocation_inventory_path,
        maximum_bytes=MAX_ALLOCATION_INVENTORY_BYTES,
        label="selector allocation inventory refresh stability check",
    )
    current_schema = read_bounded_regular_file(
        schema_path,
        maximum_bytes=MAX_AUTHORING_SCHEMA_BYTES,
        label="selector authoring schema refresh stability check",
    )
    current_allocation_schema = read_bounded_regular_file(
        allocation_schema_path,
        maximum_bytes=MAX_ALLOCATION_SCHEMA_BYTES,
        label="selector allocation schema refresh stability check",
    )
    _require(
        current_authoring == expected_authoring_raw,
        "authoring source changed during incomplete refresh",
    )
    _require(
        current_inventory == expected_inventory_raw,
        "allocation inventory changed during incomplete refresh",
    )
    _require(
        current_schema == snapshot.schema_raw,
        "authoring schema changed during incomplete refresh",
    )
    _require(
        current_allocation_schema == snapshot.allocation_schema_raw,
        "allocation schema changed during incomplete refresh",
    )
    for source_path, expected_raw in snapshot.adr_sources:
        current_raw = read_bounded_regular_file(
            source_path,
            maximum_bytes=MAX_ADR_DOCUMENT_BYTES,
            label="ADR source refresh stability check",
        )
        _require(
            current_raw == expected_raw,
            f"ADR source changed during incomplete refresh: {source_path}",
        )


def refresh_incomplete_authoring(
    authoring_path: Path,
    schema_path: Path,
    *,
    source_root: Path = ROOT,
    validate_semantics: bool = True,
    migrate_v2_empty_schema_binding: bool = False,
    migrate_observer_bridge_profile_v1_to_v2: bool = False,
    repin_adversarial_probe_bindings: bool = False,
    _metric_provider: Any = None,
    _phase_hook: Any = None,
    _review_control_lease: ReviewControlLease | None = None,
) -> tuple[int, str, int, str, int, str, int, str, int, str, bool]:
    """Refresh a fail-closed inventory and canonical authoring commitments."""

    _require(
        migrate_v2_empty_schema_binding == migrate_observer_bridge_profile_v1_to_v2,
        (
            "the allocation v2-to-v4 and observer bridge v1-to-v2 migrations "
            "form one semantic cut and must be enabled together"
        ),
    )
    migration_requested = (
        migrate_v2_empty_schema_binding or migrate_observer_bridge_profile_v1_to_v2
    )
    _require(
        not (migration_requested and repin_adversarial_probe_bindings),
        (
            "adversarial probe repin cannot be combined with the exact "
            "bridge/allocation migration"
        ),
    )
    allocation_inventory_path = authoring_path.with_name(INVENTORY_FILE)
    maintained_mutation = _require_maintained_mutation_lease(
        (authoring_path, allocation_inventory_path),
        _review_control_lease,
    )
    if maintained_mutation:
        _require(
            Path(os.path.abspath(os.fspath(authoring_path))) == DEFAULT_AUTHORING
            and Path(os.path.abspath(os.fspath(schema_path)))
            == DEFAULT_AUTHORING_SCHEMA
            and source_root.resolve(strict=True) == ROOT.resolve(strict=True),
            "maintained refresh inputs are outside the exact repository domain",
        )
    review_control_path: Path | None = None
    if migration_requested:
        source_root = _require_exact_maintained_migration_domain(
            source_root=source_root,
            authoring_path=authoring_path,
            schema_path=schema_path,
        )
        review_control_path = _require_active_review_control_lease(
            source_root,
            _review_control_lease,
        )
    allocation_schema_path = authoring_path.with_name(INVENTORY_SCHEMA_FILE)
    managed_paths = (
        (authoring_path, schema_path, ("authoring source", "authoring schema")),
        (
            authoring_path,
            allocation_inventory_path,
            ("authoring source", "allocation inventory"),
        ),
        (
            authoring_path,
            allocation_schema_path,
            ("authoring source", "allocation schema"),
        ),
        (
            schema_path,
            allocation_inventory_path,
            ("authoring schema", "allocation inventory"),
        ),
        (
            schema_path,
            allocation_schema_path,
            ("authoring schema", "allocation schema"),
        ),
        (
            allocation_inventory_path,
            allocation_schema_path,
            ("allocation inventory", "allocation schema"),
        ),
    )
    for left, right, labels in managed_paths:
        _require_distinct_paths(left, right, labels=labels)

    schema_raw = read_bounded_regular_file(
        schema_path,
        maximum_bytes=MAX_AUTHORING_SCHEMA_BYTES,
        label="selector authoring schema refresh snapshot",
    )
    if migration_requested:
        _require(
            len(schema_raw) == EXACT_COMBINED_MIGRATION_AUTHORING_SCHEMA_BYTE_LENGTH
            and sha256(schema_raw).hexdigest()
            == EXACT_COMBINED_MIGRATION_AUTHORING_SCHEMA_SHA256,
            "combined migration authoring schema is not the exact maintained cut",
        )
    schema = load_authoring_schema(schema_path)
    _require(
        parse_json_bytes(schema_raw, label=f"{schema_path} refresh snapshot") == schema,
        "authoring schema changed while refresh inputs were loaded",
    )
    allocation_schema_raw, allocation_schema = load_inventory_schema(
        allocation_schema_path
    )
    migration_guards: tuple[IncompleteRefreshGuardSnapshot, ...] = ()
    if migration_requested:
        _require(
            review_control_path is not None,
            "incomplete migration requires the fixed review-control lock",
        )
        migration_guards = _snapshot_exact_incomplete_migration_boundary(
            authoring_path=authoring_path,
            review_control_path=review_control_path,
            source_root=source_root,
        )

    migration_state: str | None = None
    legacy_authoring: dict[str, Any] | None = None
    legacy_inventory: dict[str, Any] | None = None
    if migration_requested:
        authoring_raw, legacy_authoring = _load_canonical_unvalidated_authoring_source(
            authoring_path
        )
        inventory_raw, legacy_inventory = (
            _load_canonical_unvalidated_allocation_inventory(allocation_inventory_path)
        )
        predecessor_cut, successor_cut = _exact_combined_migration_cuts()
        migration_state = _classify_exact_incomplete_migration_pair(
            authoring_raw=authoring_raw,
            inventory_raw=inventory_raw,
            predecessor=predecessor_cut,
            successor=successor_cut,
        )

    bridge_legacy_input_state = False
    if repin_adversarial_probe_bindings:
        authoring_raw, repin_authoring = _load_canonical_unvalidated_authoring_source(
            authoring_path
        )
        authoring, _ = _prepare_exact_adversarial_probe_binding_repin(
            authoring=repin_authoring,
            schema=schema,
        )
    elif migrate_observer_bridge_profile_v1_to_v2:
        _require(
            legacy_authoring is not None,
            "combined migration authoring snapshot is absent",
        )
        authoring, bridge_legacy_input_state = (
            _prepare_exact_bridge_v1_profile_migration(
                authoring=legacy_authoring,
                schema=schema,
            )
        )
    else:
        authoring_raw = read_bounded_regular_file(
            authoring_path,
            maximum_bytes=MAX_EXPANDED_BYTES,
            label="selector authoring refresh snapshot",
        )
        authoring = load_authoring_source(authoring_path, schema)
        _require(
            authoring_raw == _authoring_bytes(authoring),
            "authoring source changed while refresh inputs were loaded",
        )

    allocation_legacy_input_state = False
    if migrate_v2_empty_schema_binding:
        from selector_allocation_review import REVIEW_STATE_FILE

        _require(
            review_control_path is not None
            and review_control_path
            == _git_private_path(source_root, REVIEW_CONTROL_FILE),
            (
                "v2-empty migration requires the fixed review-control lock "
                "and its exact private control path"
            ),
        )
        _require(
            legacy_inventory is not None,
            "combined migration inventory snapshot is absent",
        )
        allocation_legacy_input_state = (
            legacy_inventory.get("allocation_review_profile")
            == V2_EMPTY_MIGRATION_PROFILE
        )
        inventory = _prepare_exact_v2_empty_inventory_migration(
            allocation_schema=allocation_schema,
            allocation_schema_raw=allocation_schema_raw,
            authoring=authoring,
            inventory=legacy_inventory,
            review_control_path=review_control_path,
            state_path=authoring_path.with_name(REVIEW_STATE_FILE),
        )
    else:
        inventory_raw, inventory = _load_unbound_allocation_inventory(
            allocation_inventory_path,
            allocation_schema,
        )
    for guard in migration_guards:
        for managed_path, managed_label in (
            (authoring_path, "authoring source"),
            (schema_path, "authoring schema"),
            (allocation_inventory_path, "allocation inventory"),
            (allocation_schema_path, "allocation schema"),
        ):
            _require_distinct_paths(
                guard.path,
                managed_path,
                labels=(guard.label, managed_label),
            )
    _require(
        inventory["status"] == "INCOMPLETE_FAIL_CLOSED",
        "refresh mode requires INCOMPLETE_FAIL_CLOSED allocation status",
    )
    _require(
        inventory["provenance_review"]["status"] == "NOT_REVIEWED"
        and inventory["provenance_review"]["reviewed_assignment_sha256"] == "0" * 64,
        "refresh mode requires an exact NOT_REVIEWED provenance state",
    )
    plan = _build_incomplete_refresh_plan(
        authoring,
        inventory,
        allocation_schema_raw,
        source_root=source_root,
        metric_provider=_metric_provider,
    )
    _validate_schema_instance(plan.authoring, schema)
    validate_allocation_inventory(plan.inventory, allocation_schema)
    if validate_semantics:
        _validate_generated_semantics(
            plan.canonical,
            allow_incomplete_allocation=True,
        )

    for source_path, _ in plan.adr_sources:
        for managed_path, managed_label in (
            (authoring_path, "authoring source"),
            (schema_path, "authoring schema"),
            (allocation_inventory_path, "allocation inventory"),
            (allocation_schema_path, "allocation schema"),
        ):
            _require_distinct_paths(
                source_path,
                managed_path,
                labels=("ADR refresh source", managed_label),
            )

    binding = validate_inventory_binding(authoring[ALLOCATION_BINDING_KEY])
    binding_matches_current_inventory = (
        binding["authoring_byte_length"] == len(inventory_raw)
        and binding["authoring_sha256"] == sha256(inventory_raw).hexdigest()
    )
    binding_matches_current_schema = (
        binding["schema_byte_length"] == len(allocation_schema_raw)
        and binding["schema_sha256"] == sha256(allocation_schema_raw).hexdigest()
    )
    binding_matches_plan_inventory = (
        binding["authoring_byte_length"] == len(plan.inventory_raw)
        and binding["authoring_sha256"] == sha256(plan.inventory_raw).hexdigest()
    )
    bound_input_state = (
        binding_matches_current_inventory and binding_matches_current_schema
    )
    authenticated_recovery_state = (
        authoring_raw == plan.authoring_raw
        and binding_matches_plan_inventory
        and binding_matches_current_schema
    )
    if migration_requested:
        _require(
            migration_state is not None,
            "combined migration exact-pair classification is absent",
        )
        _, successor_cut = _exact_combined_migration_cuts()
        _require(
            successor_cut.authoring.matches(plan.authoring_raw)
            and successor_cut.inventory.matches(plan.inventory_raw),
            "combined migration plan differs from its exact maintained successor",
        )
        expected_component_states = {
            "EXACT_PREDECESSOR": (True, True),
            "AUTHORING_FIRST_RECOVERY": (False, True),
            "EXACT_COMPLETED_REPLAY": (False, False),
        }
        _require(
            (
                bridge_legacy_input_state,
                allocation_legacy_input_state,
            )
            == expected_component_states[migration_state],
            "combined migration component states differ from the exact pair cut",
        )
    else:
        _require(
            bound_input_state or authenticated_recovery_state,
            (
                "refresh inputs are neither the bound inventory/schema pair "
                "nor an exact authoring-committed recovery state"
            ),
        )
    snapshot = IncompleteRefreshInputSnapshot(
        adr_sources=plan.adr_sources,
        allocation_schema_raw=allocation_schema_raw,
        authoring_raw=authoring_raw,
        guards=migration_guards,
        inventory_raw=inventory_raw,
        schema_raw=schema_raw,
    )
    if _phase_hook is not None:
        _phase_hook("plan-ready")
    _verify_incomplete_refresh_inputs_unchanged(
        allocation_inventory_path=allocation_inventory_path,
        allocation_schema_path=allocation_schema_path,
        authoring_path=authoring_path,
        schema_path=schema_path,
        snapshot=snapshot,
        expected_authoring_raw=authoring_raw,
        expected_inventory_raw=inventory_raw,
    )

    changed = False
    # Install the authoring envelope first. Its binding authenticates the exact
    # inventory bytes needed to recover after a crash; an unbound inventory
    # cannot authenticate itself as an interrupted refresh.
    if authoring_raw != plan.authoring_raw:
        _atomic_replace_if_current(
            authoring_path,
            plan.authoring_raw,
            expected_current=authoring_raw,
            maximum_bytes=MAX_EXPANDED_BYTES,
            label="selector authoring incomplete refresh",
        )
        changed = True
    _verify_incomplete_refresh_inputs_unchanged(
        allocation_inventory_path=allocation_inventory_path,
        allocation_schema_path=allocation_schema_path,
        authoring_path=authoring_path,
        schema_path=schema_path,
        snapshot=snapshot,
        expected_authoring_raw=plan.authoring_raw,
        expected_inventory_raw=inventory_raw,
    )
    if _phase_hook is not None:
        _phase_hook("authoring-installed")
    _verify_incomplete_refresh_inputs_unchanged(
        allocation_inventory_path=allocation_inventory_path,
        allocation_schema_path=allocation_schema_path,
        authoring_path=authoring_path,
        schema_path=schema_path,
        snapshot=snapshot,
        expected_authoring_raw=plan.authoring_raw,
        expected_inventory_raw=inventory_raw,
    )

    if inventory_raw != plan.inventory_raw:
        _atomic_replace_if_current(
            allocation_inventory_path,
            plan.inventory_raw,
            expected_current=inventory_raw,
            maximum_bytes=MAX_ALLOCATION_INVENTORY_BYTES,
            label="selector allocation inventory incomplete refresh",
        )
        changed = True
    _verify_incomplete_refresh_inputs_unchanged(
        allocation_inventory_path=allocation_inventory_path,
        allocation_schema_path=allocation_schema_path,
        authoring_path=authoring_path,
        schema_path=schema_path,
        snapshot=snapshot,
        expected_authoring_raw=plan.authoring_raw,
        expected_inventory_raw=plan.inventory_raw,
    )
    if _phase_hook is not None:
        _phase_hook("inventory-installed")
    _verify_incomplete_refresh_inputs_unchanged(
        allocation_inventory_path=allocation_inventory_path,
        allocation_schema_path=allocation_schema_path,
        authoring_path=authoring_path,
        schema_path=schema_path,
        snapshot=snapshot,
        expected_authoring_raw=plan.authoring_raw,
        expected_inventory_raw=plan.inventory_raw,
    )

    installed = load_authoring_source(authoring_path, schema)
    installed_allocation = load_bound_allocation_inventory(
        authoring_path.parent,
        installed[ALLOCATION_BINDING_KEY],
    )
    _require(
        installed == plan.authoring,
        "installed authoring differs from the incomplete refresh plan",
    )
    _require(
        installed_allocation.inventory == plan.inventory,
        "installed inventory differs from the incomplete refresh plan",
    )
    _require(
        prepare_canonical_source(installed, installed_allocation.oracle)
        == plan.canonical,
        "installed incomplete refresh does not reconstruct its canonical source",
    )
    _verify_incomplete_refresh_inputs_unchanged(
        allocation_inventory_path=allocation_inventory_path,
        allocation_schema_path=allocation_schema_path,
        authoring_path=authoring_path,
        schema_path=schema_path,
        snapshot=snapshot,
        expected_authoring_raw=plan.authoring_raw,
        expected_inventory_raw=plan.inventory_raw,
    )
    return (
        len(plan.authoring_raw),
        sha256(plan.authoring_raw).hexdigest(),
        len(plan.inventory_raw),
        sha256(plan.inventory_raw).hexdigest(),
        plan.inventory["model_allocation_count"],
        plan.inventory["model_allocation_sha256"],
        plan.inventory["semantic_review_subject"]["byte_length"],
        plan.inventory["semantic_review_subject"]["sha256"],
        plan.inventory["semantic_shape_entry_count"],
        plan.inventory["semantic_shape_sha256"],
        changed,
    )


def generate_compact_bytes(
    authoring_path: Path,
    schema_path: Path,
    *,
    validate_semantics: bool = True,
    review_candidate: bool = False,
) -> tuple[bytes, dict[str, Any], GenerationInputSnapshot]:
    compact_schema_path = schema_path.with_name(CANONICAL_SOURCE_SCHEMA_FILE)
    compact_schema_raw, _ = load_compact_schema(compact_schema_path)
    schema_raw = read_bounded_regular_file(
        schema_path,
        maximum_bytes=MAX_AUTHORING_SCHEMA_BYTES,
        label="selector authoring schema snapshot",
    )
    schema = load_authoring_schema(schema_path)
    snapshot_schema = parse_json_bytes(
        schema_raw,
        label=f"{schema_path} snapshot",
    )
    _require(
        snapshot_schema == schema,
        "authoring schema changed while generation inputs were loaded",
    )
    authoring_raw = read_bounded_regular_file(
        authoring_path,
        maximum_bytes=MAX_EXPANDED_BYTES,
        label="selector authoring source snapshot",
    )
    authoring = load_authoring_source(authoring_path, schema)
    _require(
        authoring_raw == _authoring_bytes(authoring),
        "authoring source changed while generation inputs were loaded",
    )
    allocation_snapshot = load_bound_allocation_inventory(
        authoring_path.parent,
        authoring[ALLOCATION_BINDING_KEY],
    )
    generated = prepare_canonical_source(
        authoring,
        allocation_snapshot.oracle,
    )
    if review_candidate:
        _require(
            validate_semantics,
            "review-candidate generation cannot bypass semantic validation",
        )
        _require_review_candidate_boundary(generated)
    adr_sources: tuple[tuple[Path, bytes], ...] = ()
    if validate_semantics:
        adr_sources = _validate_generated_semantics(
            generated,
            allow_incomplete_allocation=review_candidate,
        )
    raw = serialize_compact_source(generated)
    envelope = parse_json_bytes(raw, label="generated compact source")
    _require(isinstance(envelope, dict), "generated compact source is not an object")
    _require(
        envelope["encoding"]["expanded_document_sha256"] == canonical_sha256(generated),
        "generated compact source has the wrong expanded-document digest",
    )
    snapshot = GenerationInputSnapshot(
        allocation=allocation_snapshot,
        adr_sources=adr_sources,
        authoring_raw=authoring_raw,
        compact_schema_raw=compact_schema_raw,
        schema_raw=schema_raw,
    )
    _verify_generation_inputs_unchanged(
        authoring_path,
        schema_path,
        snapshot,
    )
    return raw, envelope, snapshot


def _verify_generation_inputs_unchanged(
    authoring_path: Path,
    schema_path: Path,
    snapshot: GenerationInputSnapshot,
) -> None:
    compact_schema_path = schema_path.with_name(CANONICAL_SOURCE_SCHEMA_FILE)
    current_compact_schema = read_bounded_regular_file(
        compact_schema_path,
        maximum_bytes=MAX_COMPACT_SCHEMA_BYTES,
        label="selector compact schema stability check",
    )
    current_schema = read_bounded_regular_file(
        schema_path,
        maximum_bytes=MAX_AUTHORING_SCHEMA_BYTES,
        label="selector authoring schema stability check",
    )
    current_authoring = read_bounded_regular_file(
        authoring_path,
        maximum_bytes=MAX_EXPANDED_BYTES,
        label="selector authoring source stability check",
    )
    _require(
        current_compact_schema == snapshot.compact_schema_raw,
        "compact schema changed during generation",
    )
    _require(
        current_schema == snapshot.schema_raw,
        "authoring schema changed during generation",
    )
    _require(
        current_authoring == snapshot.authoring_raw,
        "authoring source changed during generation",
    )
    verify_inventory_snapshot_unchanged(snapshot.allocation)
    for path, expected in snapshot.adr_sources:
        current = read_bounded_regular_file(
            ROOT / path,
            maximum_bytes=MAX_ADR_DOCUMENT_BYTES,
            label=f"{path} semantic source stability check",
        )
        _require(current == expected, f"{path}: ADR changed during generation")


def _check_output(path: Path, expected: bytes) -> None:
    actual = read_bounded_regular_file(
        path,
        maximum_bytes=MAX_COMPACT_BYTES - 1,
        label="generated compact selector source",
    )
    _require(actual == expected, f"stale generated selector source: {path}")


def _write_and_verify_compact(
    path: Path,
    expected: bytes,
    *,
    _review_control_lease: ReviewControlLease | None = None,
) -> None:
    maintained_mutation = _require_maintained_mutation_lease(
        (path,),
        _review_control_lease,
    )
    _require(
        not maintained_mutation
        or Path(os.path.abspath(os.fspath(path))) == DEFAULT_OUTPUT,
        "maintained compact output is outside its exact repository role path",
    )
    _atomic_write(path, expected)
    envelope, _ = load_compact_source(path)
    expected_envelope = parse_json_bytes(
        expected,
        label="expected compact selector source",
    )
    _require(
        envelope == expected_envelope,
        "installed compact source differs from the prevalidated output",
    )


def materialize_authoring(
    compact_path: Path,
    authoring_path: Path,
    schema_path: Path,
    *,
    validate_semantics: bool = True,
    _review_control_lease: ReviewControlLease | None = None,
) -> tuple[int, str, bool]:
    allocation_inventory_path = authoring_path.with_name(INVENTORY_FILE)
    allocation_schema_path = authoring_path.with_name(INVENTORY_SCHEMA_FILE)
    maintained_mutation = _require_maintained_mutation_lease(
        (authoring_path, allocation_inventory_path),
        _review_control_lease,
    )
    if maintained_mutation:
        _require(
            Path(os.path.abspath(os.fspath(compact_path))) == DEFAULT_OUTPUT
            and Path(os.path.abspath(os.fspath(authoring_path))) == DEFAULT_AUTHORING
            and Path(os.path.abspath(os.fspath(schema_path)))
            == DEFAULT_AUTHORING_SCHEMA,
            "maintained materialization inputs are outside exact repository roles",
        )
    _require_distinct_paths(
        compact_path,
        authoring_path,
        labels=("compact input", "authoring output"),
    )
    _require_distinct_paths(
        schema_path,
        authoring_path,
        labels=("authoring schema", "authoring output"),
    )
    compact_schema_path = schema_path.with_name(CANONICAL_SOURCE_SCHEMA_FILE)
    _require_distinct_paths(
        compact_path,
        compact_schema_path,
        labels=("compact input", "compact schema"),
    )
    _require_distinct_paths(
        compact_schema_path,
        authoring_path,
        labels=("compact schema", "authoring output"),
    )
    for left, right, labels in (
        (
            allocation_inventory_path,
            authoring_path,
            ("allocation inventory", "authoring output"),
        ),
        (
            allocation_schema_path,
            authoring_path,
            ("allocation schema", "authoring output"),
        ),
        (
            allocation_inventory_path,
            allocation_schema_path,
            ("allocation inventory", "allocation schema"),
        ),
        (
            allocation_inventory_path,
            compact_path,
            ("allocation inventory", "compact input"),
        ),
        (
            allocation_schema_path,
            compact_path,
            ("allocation schema", "compact input"),
        ),
        (
            allocation_inventory_path,
            schema_path,
            ("allocation inventory", "authoring schema"),
        ),
        (
            allocation_schema_path,
            schema_path,
            ("allocation schema", "authoring schema"),
        ),
        (
            allocation_inventory_path,
            compact_schema_path,
            ("allocation inventory", "compact schema"),
        ),
        (
            allocation_schema_path,
            compact_schema_path,
            ("allocation schema", "compact schema"),
        ),
    ):
        _require_distinct_paths(left, right, labels=labels)
    compact_schema_raw, _ = load_compact_schema(compact_schema_path)
    allocation_schema_raw, allocation_schema = load_inventory_schema(
        allocation_schema_path
    )
    schema_raw = read_bounded_regular_file(
        schema_path,
        maximum_bytes=MAX_AUTHORING_SCHEMA_BYTES,
        label="selector authoring schema materialization snapshot",
    )
    schema = load_authoring_schema(schema_path)
    _require(
        parse_json_bytes(
            schema_raw,
            label=f"{schema_path} materialization snapshot",
        )
        == schema,
        "authoring schema changed while materialization inputs were loaded",
    )
    compact_raw = read_bounded_regular_file(
        compact_path,
        maximum_bytes=MAX_COMPACT_BYTES - 1,
        label="compact selector materialization snapshot",
    )
    envelope, expanded = load_compact_source(compact_path)
    _require(
        compact_raw == canonical_bytes(envelope) + b"\n",
        "compact source changed while materialization inputs were loaded",
    )
    snapshot = MaterializationInputSnapshot(
        allocation_schema_path=allocation_schema_path,
        allocation_schema_raw=allocation_schema_raw,
        compact_raw=compact_raw,
        compact_schema_raw=compact_schema_raw,
        schema_raw=schema_raw,
    )
    if validate_semantics:
        _validate_generated_semantics(expanded)
    oracle = expanded.get(ALLOCATION_ORACLE_KEY)
    _require(
        isinstance(oracle, dict),
        f"compact payload is missing {ALLOCATION_ORACLE_KEY}",
    )
    inventory = oracle_to_inventory(oracle)
    validate_allocation_inventory(inventory, allocation_schema)
    validate_allocation_review_profile_schema_binding(
        inventory,
        allocation_schema_raw,
    )
    allocation_raw = inventory_bytes(inventory)
    allocation_binding = build_inventory_binding(
        allocation_raw,
        allocation_schema_raw,
    )
    authoring = prepare_authoring_source(expanded, allocation_binding)
    _validate_schema_instance(authoring, schema)
    _require(
        prepare_canonical_source(
            authoring,
            inventory_to_oracle(inventory),
        )
        == expanded,
        "materialized authoring source does not reconstruct the compact payload",
    )
    raw = _authoring_bytes(authoring)
    _verify_materialization_inputs_unchanged(
        compact_path,
        schema_path,
        snapshot,
    )
    authoring_exists = authoring_path.exists() or authoring_path.is_symlink()
    inventory_exists = (
        allocation_inventory_path.exists() or allocation_inventory_path.is_symlink()
    )
    if authoring_exists:
        installed_raw = read_bounded_regular_file(
            authoring_path,
            maximum_bytes=MAX_EXPANDED_BYTES,
            label="existing selector authoring source",
        )
        _require(
            installed_raw == raw,
            "refusing to overwrite a different selector authoring source",
        )
        installed = load_authoring_source(authoring_path, schema)
        _require(
            installed == authoring,
            "existing authoring source differs from the decoded compact payload",
        )
    if inventory_exists:
        installed_allocation_raw = read_bounded_regular_file(
            allocation_inventory_path,
            maximum_bytes=len(allocation_raw),
            label="existing selector allocation inventory",
        )
        _require(
            installed_allocation_raw == allocation_raw,
            "refusing to overwrite a different selector allocation inventory",
        )
    _verify_materialization_inputs_unchanged(
        compact_path,
        schema_path,
        snapshot,
    )

    # The inventory is written first.  A crash can leave an unreferenced
    # inventory, but it cannot leave an authoring source that references
    # missing bytes.
    if not inventory_exists:
        _atomic_write(
            allocation_inventory_path,
            allocation_raw,
            create_only=True,
        )
    if not authoring_exists:
        _atomic_write(authoring_path, raw, create_only=True)

    loaded_allocation = load_bound_allocation_inventory(
        authoring_path.parent,
        authoring[ALLOCATION_BINDING_KEY],
    )
    _require(
        loaded_allocation.oracle == inventory_to_oracle(inventory),
        "installed allocation inventory differs from the compact payload",
    )
    installed = load_authoring_source(authoring_path, schema)
    _require(
        installed == authoring,
        "installed authoring source differs from the prevalidated output",
    )
    _verify_materialization_inputs_unchanged(
        compact_path,
        schema_path,
        snapshot,
    )
    return (
        len(raw),
        canonical_sha256(authoring),
        not authoring_exists or not inventory_exists,
    )


def _verify_materialization_inputs_unchanged(
    compact_path: Path,
    schema_path: Path,
    snapshot: MaterializationInputSnapshot,
) -> None:
    compact_schema_path = schema_path.with_name(CANONICAL_SOURCE_SCHEMA_FILE)
    current_compact_schema = read_bounded_regular_file(
        compact_schema_path,
        maximum_bytes=MAX_COMPACT_SCHEMA_BYTES,
        label="selector compact schema materialization stability check",
    )
    current_schema = read_bounded_regular_file(
        schema_path,
        maximum_bytes=MAX_AUTHORING_SCHEMA_BYTES,
        label="selector authoring schema materialization stability check",
    )
    current_compact = read_bounded_regular_file(
        compact_path,
        maximum_bytes=MAX_COMPACT_BYTES - 1,
        label="compact selector materialization stability check",
    )
    current_allocation_schema = read_bounded_regular_file(
        snapshot.allocation_schema_path,
        maximum_bytes=len(snapshot.allocation_schema_raw),
        label="selector allocation schema materialization stability check",
    )
    _require(
        current_compact_schema == snapshot.compact_schema_raw,
        "compact schema changed during materialization",
    )
    _require(
        current_schema == snapshot.schema_raw,
        "authoring schema changed during materialization",
    )
    _require(
        current_compact == snapshot.compact_raw,
        "compact source changed during materialization",
    )
    _require(
        current_allocation_schema == snapshot.allocation_schema_raw,
        "allocation inventory schema changed during materialization",
    )


def _sample_expanded_source(
    allocation_schema_raw: bytes,
    *,
    observer_read_capture_bridge_profile: dict[str, Any],
) -> dict[str, Any]:
    empty_allocation_digest = document_rows_sha256(
        [],
        row_kind="allocations",
    )
    empty_exclusion_digest = document_rows_sha256(
        [],
        row_kind="exclusions",
    )
    sample_model_sha256 = model_allocation_projection_sha256(
        [
            allocation_identity_projection(
                "TYPE",
                "SampleSelector",
                "selector-type::SampleSelector",
            )
        ]
    )
    documents = []
    for index, path in enumerate(ADR_ALLOCATION_PATHS, 1):
        adr_id = f"ADR-{index:03d}"
        modules = [
            {
                "byte_length": 1,
                "path": module_path,
                "sha256": "0" * 64,
            }
            for module_path in ADR_ALLOCATION_MODULE_PATHS[index - 1]
        ]
        source_set = copy.deepcopy(ADR_SOURCE_SET_SUITE)
        source_set["sha256"] = adr_source_set_sha256(
            adr_id=adr_id,
            path=path,
            byte_length=1,
            source_sha256="0" * 64,
            modules=modules,
        )
        documents.append(
            {
                "adr_id": adr_id,
                "allocation_anchor_id": ADR_ALLOCATION_ANCHOR_IDS[index - 1],
                "allocation_row_count": 0,
                "allocation_rows_sha256": empty_allocation_digest,
                "byte_length": 1,
                "exclusion_row_count": 0,
                "exclusion_rows_sha256": empty_exclusion_digest,
                "modules": modules,
                "path": path,
                "sha256": "0" * 64,
                "source_set": source_set,
            }
        )
    sample = {
        "$schema": CANONICAL_SOURCE_SCHEMA_FILE,
        "schema": CANONICAL_SOURCE_SCHEMA_ID,
        "normative": False,
        "candidate": "1.0.0-rc.1",
        "task": "B01",
        "generated_by": CANONICAL_GENERATOR,
        "generated_view": "docs/adr/B01_SELECTOR_CLOSURE_MATRIX.md",
        "adr_allocation_oracle": {
            "allocation_review_profile": build_allocation_review_profile(
                allocation_schema_raw=allocation_schema_raw,
                model_allocation_count=1,
                model_allocation_sha256=sample_model_sha256,
                model_origin_signal_row_count=1,
                model_origin_signal_sha256="0" * 64,
                resource_closure_row_count=1,
                resource_closure_sha256="0" * 64,
                semantic_shape_entry_count=1,
                semantic_shape_sha256="0" * 64,
            ),
            "allocations": [],
            "claim_boundary": INVENTORY_CLAIM_BOUNDARY,
            "document_row_commitment": copy.deepcopy(DOCUMENT_ROW_COMMITMENT),
            "documents": documents,
            "exclusions": [],
            "model_allocation_count": 1,
            "model_allocation_sha256": sample_model_sha256,
            "provenance_review": build_not_reviewed_provenance_review(),
            "required_kinds": list(ALLOCATION_KINDS),
            "semantic_shape_entry_count": 1,
            "semantic_shape_sha256": "0" * 64,
            "status": "INCOMPLETE_FAIL_CLOSED",
        },
        "artifacts": [
            "selector-type::SampleSelector",
            "selector-root-type::SampleSelectorRoot",
            "selector-commit-receipt-type::SampleSelectorCommitReceipt",
        ],
        "global_key_coordinate_registry": [
            {
                "selector_id": "SAMPLE",
                "state_domain": "ROOT",
                "key_coordinates": ["sample_id"],
            }
        ],
        "observer_read_capture_bridge_profile": copy.deepcopy(
            observer_read_capture_bridge_profile
        ),
        "selectors": [
            {
                "selector_id": "SAMPLE",
                "selector": "selector-type::SampleSelector",
                "root": "selector-root-type::SampleSelectorRoot",
                "generic_receipt": (
                    "selector-commit-receipt-type::SampleSelectorCommitReceipt"
                ),
                "owned_resources": [
                    {
                        "owner_selector_id": "SAMPLE",
                        "resource": "SAMPLE.SAMPLE_SELECTOR_ROOT",
                    },
                    {
                        "owner_selector_id": "SAMPLE",
                        "resource": "SAMPLE.SELECTOR",
                    },
                    {
                        "owner_selector_id": "SAMPLE",
                        "resource": "SAMPLE.STATE_DOMAIN.ROOT",
                    },
                ],
                "state_domains": [{"state_domain": "ROOT"}],
                "events": [
                    {
                        "common_case_effects": [
                            {
                                "action": "WRITE",
                                "cardinality": "ROOT",
                                "resource": "SAMPLE.SAMPLE_SELECTOR_ROOT",
                            }
                        ],
                        "common_case_mutates": ["SAMPLE.SAMPLE_SELECTOR_ROOT"],
                        "event_id": "SAMPLE_GENESIS",
                    }
                ],
            }
        ],
        "closure_commitments": {},
    }
    _, sample_resource_closure = derive_resource_closure(sample)
    sample["adr_allocation_oracle"]["allocation_review_profile"] = (
        build_allocation_review_profile(
            allocation_schema_raw=allocation_schema_raw,
            model_allocation_count=1,
            model_allocation_sha256=sample_model_sha256,
            model_origin_signal_row_count=1,
            model_origin_signal_sha256="0" * 64,
            resource_closure_row_count=sample_resource_closure["row_count"],
            resource_closure_sha256=sample_resource_closure["sha256"],
            semantic_shape_entry_count=1,
            semantic_shape_sha256="0" * 64,
        )
    )
    sample["adr_allocation_oracle"]["semantic_review_subject"] = (
        semantic_review_subject_commitment(sample)
    )
    from check_selector_closure import _semantic_shape_commitment

    sample_shape_count, sample_shape_sha256 = _semantic_shape_commitment(sample)
    sample["adr_allocation_oracle"]["semantic_shape_entry_count"] = sample_shape_count
    sample["adr_allocation_oracle"]["semantic_shape_sha256"] = sample_shape_sha256
    sample["adr_allocation_oracle"]["allocation_review_profile"] = (
        build_allocation_review_profile(
            allocation_schema_raw=allocation_schema_raw,
            model_allocation_count=1,
            model_allocation_sha256=sample_model_sha256,
            model_origin_signal_row_count=1,
            model_origin_signal_sha256="0" * 64,
            resource_closure_row_count=sample_resource_closure["row_count"],
            resource_closure_sha256=sample_resource_closure["sha256"],
            semantic_shape_entry_count=sample_shape_count,
            semantic_shape_sha256=sample_shape_sha256,
        )
    )
    _require(
        _semantic_shape_commitment(sample) == (sample_shape_count, sample_shape_sha256),
        "sample semantic-shape commitment is not stable after scalar installation",
    )
    return sample


def _run_incomplete_refresh_self_test(
    directory: Path,
    *,
    allocation_schema: dict[str, Any],
    allocation_schema_raw: bytes,
    observer_read_capture_bridge_profile: dict[str, Any],
    schema_path: Path,
) -> None:
    """Exercise gating, preservation, recovery, aliases, and stale inputs."""

    def sample_metrics(
        metric_source: dict[str, Any],
    ) -> tuple[int, str, int, str, int, str]:
        from check_selector_closure import _semantic_shape_commitment

        shape_count, shape_sha256 = _semantic_shape_commitment(metric_source)
        return (
            1,
            model_allocation_projection_sha256(
                [
                    allocation_identity_projection(
                        "TYPE",
                        "SampleSelector",
                        "selector-type::SampleSelector",
                    )
                ]
            ),
            1,
            "1" * 64,
            shape_count,
            shape_sha256,
        )

    def prepare_workspace(
        name: str,
    ) -> tuple[Path, Path, Path, bytes, bytes]:
        source_root = directory / name
        maintenance_directory = source_root / "maintenance"
        maintenance_directory.mkdir(parents=True)
        for path in (
            *ADR_ALLOCATION_PATHS,
            *(
                module_path
                for module_paths in ADR_ALLOCATION_MODULE_PATHS
                for module_path in module_paths
            ),
        ):
            source_path = source_root / path
            source_path.parent.mkdir(parents=True, exist_ok=True)
            _atomic_write(
                source_path,
                f"refresh self-test source: {path}\n".encode(),
            )

        authoring_path = maintenance_directory / "authoring.json"
        allocation_path = maintenance_directory / INVENTORY_FILE
        allocation_schema_path = maintenance_directory / INVENTORY_SCHEMA_FILE
        _atomic_write(allocation_schema_path, allocation_schema_raw)

        sample = _sample_expanded_source(
            allocation_schema_raw,
            observer_read_capture_bridge_profile=(observer_read_capture_bridge_profile),
        )
        inventory = oracle_to_inventory(sample[ALLOCATION_ORACLE_KEY])
        sample_semantic_ref = "selector-type::SampleSelector"
        inventory["allocations"] = [
            {
                "adr_id": "ADR-001",
                "exact_name": "SampleSelector",
                "kind": "TYPE",
                "semantic_ref": sample_semantic_ref,
                "source_anchor": ADR_ALLOCATION_ANCHOR_IDS[0],
                "unit_id": allocation_unit_id(
                    "TYPE",
                    "SampleSelector",
                    sample_semantic_ref,
                ),
            }
        ]
        inventory["exclusions"] = [
            {
                "adr_id": "ADR-001",
                "classification": "PROFILE_OR_INVARIANT_IDENTIFIER",
                "exact_name": "SampleInvariant",
                "reason": "refresh self-test retained exclusion",
                "source_anchor": ADR_ALLOCATION_ANCHOR_IDS[0],
            }
        ]
        first_document = inventory["documents"][0]
        first_document["allocation_row_count"] = 1
        first_document["allocation_rows_sha256"] = document_rows_sha256(
            inventory["allocations"],
            row_kind="allocations",
        )
        first_document["exclusion_row_count"] = 1
        first_document["exclusion_rows_sha256"] = document_rows_sha256(
            inventory["exclusions"],
            row_kind="exclusions",
        )
        validate_allocation_inventory(inventory, allocation_schema)
        inventory_raw = inventory_bytes(inventory)
        binding = build_inventory_binding(
            inventory_raw,
            allocation_schema_raw,
        )
        sample[ALLOCATION_ORACLE_KEY] = inventory_to_oracle(inventory)
        _recompute_closure_commitments(sample)
        authoring = prepare_authoring_source(sample, binding)
        authoring["selectors"][0]["events"][0]["event_id"] = (
            "SAMPLE_GENESIS_MAINTAINED_EDIT"
        )
        authoring_raw = _authoring_bytes(authoring)
        _atomic_write(allocation_path, inventory_raw)
        _atomic_write(authoring_path, authoring_raw)
        return (
            source_root,
            authoring_path,
            allocation_path,
            authoring_raw,
            inventory_raw,
        )

    (
        source_root,
        authoring_path,
        allocation_path,
        stale_authoring_raw,
        stale_inventory_raw,
    ) = prepare_workspace("refresh-success")
    (
        refreshed_authoring_byte_count,
        refreshed_authoring_digest,
        refreshed_inventory_byte_count,
        refreshed_inventory_digest,
        refreshed_model_count,
        refreshed_model_digest,
        refreshed_subject_byte_length,
        refreshed_subject_digest,
        refreshed_shape_count,
        refreshed_shape_digest,
        changed,
    ) = refresh_incomplete_authoring(
        authoring_path,
        schema_path,
        source_root=source_root,
        validate_semantics=False,
        _metric_provider=sample_metrics,
    )
    _require(changed, "incomplete refresh self-test did not refresh stale inputs")
    refreshed_authoring_raw = read_bounded_regular_file(
        authoring_path,
        maximum_bytes=MAX_EXPANDED_BYTES,
        label="refreshed self-test authoring",
    )
    refreshed_inventory_raw = read_bounded_regular_file(
        allocation_path,
        maximum_bytes=MAX_ALLOCATION_INVENTORY_BYTES,
        label="refreshed self-test inventory",
    )
    _require(
        refreshed_authoring_raw != stale_authoring_raw
        and refreshed_inventory_raw != stale_inventory_raw,
        "incomplete refresh self-test did not update both maintained files",
    )
    refreshed_inventory = parse_json_bytes(
        refreshed_inventory_raw,
        label="refreshed self-test inventory",
    )
    stale_inventory = parse_json_bytes(
        stale_inventory_raw,
        label="stale self-test inventory",
    )
    _require(
        refreshed_authoring_byte_count == len(refreshed_authoring_raw)
        and refreshed_authoring_digest == sha256(refreshed_authoring_raw).hexdigest()
        and refreshed_inventory_byte_count == len(refreshed_inventory_raw)
        and refreshed_inventory_digest == sha256(refreshed_inventory_raw).hexdigest()
        and refreshed_model_count == refreshed_inventory["model_allocation_count"]
        and refreshed_model_digest == refreshed_inventory["model_allocation_sha256"]
        and refreshed_subject_byte_length
        == refreshed_inventory["semantic_review_subject"]["byte_length"]
        and refreshed_subject_digest
        == refreshed_inventory["semantic_review_subject"]["sha256"]
        and refreshed_shape_count == refreshed_inventory["semantic_shape_entry_count"]
        and refreshed_shape_digest == refreshed_inventory["semantic_shape_sha256"],
        "incomplete refresh reported values differ from installed bytes",
    )
    _require(
        _incomplete_refresh_preserved_inventory_projection(refreshed_inventory)
        == _incomplete_refresh_preserved_inventory_projection(stale_inventory),
        "incomplete refresh changed an author-maintained inventory field",
    )
    before_authoring_stat = authoring_path.stat()
    before_inventory_stat = allocation_path.stat()
    *_, changed = refresh_incomplete_authoring(
        authoring_path,
        schema_path,
        source_root=source_root,
        validate_semantics=False,
        _metric_provider=sample_metrics,
    )
    _require(not changed, "idempotent incomplete refresh reported a write")
    _require(
        authoring_path.stat().st_mtime_ns == before_authoring_stat.st_mtime_ns
        and allocation_path.stat().st_mtime_ns == before_inventory_stat.st_mtime_ns,
        "idempotent incomplete refresh rewrote maintained files",
    )

    (
        crash_root,
        crash_authoring_path,
        crash_inventory_path,
        crash_authoring_raw,
        crash_inventory_raw,
    ) = prepare_workspace("refresh-crash")

    class SimulatedRefreshCrashError(RuntimeError):
        pass

    def crash_after_authoring(phase: str) -> None:
        if phase == "authoring-installed":
            raise SimulatedRefreshCrashError

    try:
        refresh_incomplete_authoring(
            crash_authoring_path,
            schema_path,
            source_root=crash_root,
            validate_semantics=False,
            _metric_provider=sample_metrics,
            _phase_hook=crash_after_authoring,
        )
    except SimulatedRefreshCrashError:
        pass
    else:
        _fail("incomplete refresh crash self-test did not interrupt")
    _require(
        read_bounded_regular_file(
            crash_authoring_path,
            maximum_bytes=MAX_EXPANDED_BYTES,
            label="crash self-test authoring",
        )
        != crash_authoring_raw,
        "authoring-first crash did not install its recovery commitment",
    )
    _require(
        read_bounded_regular_file(
            crash_inventory_path,
            maximum_bytes=MAX_ALLOCATION_INVENTORY_BYTES,
            label="crash self-test inventory",
        )
        == crash_inventory_raw,
        "authoring-first crash changed inventory before its install",
    )
    *_, recovered = refresh_incomplete_authoring(
        crash_authoring_path,
        schema_path,
        source_root=crash_root,
        validate_semantics=False,
        _metric_provider=sample_metrics,
    )
    _require(recovered, "incomplete refresh did not recover authoring-first crash")
    recovered_authoring = load_authoring_source(
        crash_authoring_path,
        load_authoring_schema(schema_path),
    )
    recovered_allocation = load_bound_allocation_inventory(
        crash_authoring_path.parent,
        recovered_authoring[ALLOCATION_BINDING_KEY],
    )
    prepare_canonical_source(recovered_authoring, recovered_allocation.oracle)

    (
        forged_root,
        forged_authoring_path,
        forged_inventory_path,
        forged_authoring_raw,
        _,
    ) = prepare_workspace("refresh-forged-inventory-first")
    forged_authoring = load_authoring_source(
        forged_authoring_path,
        load_authoring_schema(schema_path),
    )
    _, forged_inventory = _load_unbound_allocation_inventory(
        forged_inventory_path,
        allocation_schema,
    )
    forged_plan = _build_incomplete_refresh_plan(
        forged_authoring,
        forged_inventory,
        allocation_schema_raw,
        source_root=forged_root,
        metric_provider=sample_metrics,
    )
    _atomic_write(forged_inventory_path, forged_plan.inventory_raw)
    try:
        refresh_incomplete_authoring(
            forged_authoring_path,
            schema_path,
            source_root=forged_root,
            validate_semantics=False,
            _metric_provider=sample_metrics,
        )
    except (SelectorClosureCodecError, SelectorClosureGenerationError):
        pass
    else:
        _fail("incomplete refresh trusted an unbound inventory-first state")
    _require(
        read_bounded_regular_file(
            forged_authoring_path,
            maximum_bytes=MAX_EXPANDED_BYTES,
            label="forged inventory-first self-test authoring",
        )
        == forged_authoring_raw
        and read_bounded_regular_file(
            forged_inventory_path,
            maximum_bytes=MAX_ALLOCATION_INVENTORY_BYTES,
            label="forged inventory-first self-test inventory",
        )
        == forged_plan.inventory_raw,
        "failed forged inventory-first refresh changed maintained files",
    )

    (
        completed_crash_root,
        completed_crash_authoring_path,
        _,
        _,
        _,
    ) = prepare_workspace("refresh-completed-crash")

    def crash_after_both_installs(phase: str) -> None:
        if phase == "inventory-installed":
            raise SimulatedRefreshCrashError

    try:
        refresh_incomplete_authoring(
            completed_crash_authoring_path,
            schema_path,
            source_root=completed_crash_root,
            validate_semantics=False,
            _metric_provider=sample_metrics,
            _phase_hook=crash_after_both_installs,
        )
    except SimulatedRefreshCrashError:
        pass
    else:
        _fail("completed-refresh crash self-test did not interrupt")
    *_, completed_crash_changed = refresh_incomplete_authoring(
        completed_crash_authoring_path,
        schema_path,
        source_root=completed_crash_root,
        validate_semantics=False,
        _metric_provider=sample_metrics,
    )
    _require(
        not completed_crash_changed,
        "completed refresh was not idempotent after a final-phase crash",
    )

    (
        stale_root,
        stale_authoring_path,
        stale_allocation_path,
        stale_source_authoring_raw,
        stale_source_inventory_raw,
    ) = prepare_workspace("refresh-stale-authoring")

    def mutate_authoring_after_plan(phase: str) -> None:
        if phase == "plan-ready":
            _atomic_write(stale_authoring_path, stale_source_authoring_raw + b" ")

    try:
        refresh_incomplete_authoring(
            stale_authoring_path,
            schema_path,
            source_root=stale_root,
            validate_semantics=False,
            _metric_provider=sample_metrics,
            _phase_hook=mutate_authoring_after_plan,
        )
    except SelectorClosureGenerationError:
        pass
    else:
        _fail("incomplete refresh accepted authoring changed after planning")
    _require(
        read_bounded_regular_file(
            stale_allocation_path,
            maximum_bytes=MAX_ALLOCATION_INVENTORY_BYTES,
            label="stale-plan self-test inventory",
        )
        == stale_source_inventory_raw,
        "failed stale-plan refresh changed the inventory",
    )

    (
        stale_inventory_root,
        stale_inventory_authoring_path,
        stale_inventory_path,
        stale_inventory_authoring_raw,
        stale_inventory_raw,
    ) = prepare_workspace("refresh-stale-inventory-after-authoring")

    def mutate_inventory_after_authoring(phase: str) -> None:
        if phase == "authoring-installed":
            _atomic_write(stale_inventory_path, stale_inventory_raw + b" ")

    try:
        refresh_incomplete_authoring(
            stale_inventory_authoring_path,
            schema_path,
            source_root=stale_inventory_root,
            validate_semantics=False,
            _metric_provider=sample_metrics,
            _phase_hook=mutate_inventory_after_authoring,
        )
    except SelectorClosureGenerationError:
        pass
    else:
        _fail("incomplete refresh overwrote inventory changed after authoring install")
    _require(
        read_bounded_regular_file(
            stale_inventory_authoring_path,
            maximum_bytes=MAX_EXPANDED_BYTES,
            label="post-authoring-race self-test authoring",
        )
        != stale_inventory_authoring_raw
        and read_bounded_regular_file(
            stale_inventory_path,
            maximum_bytes=MAX_ALLOCATION_INVENTORY_BYTES,
            label="post-authoring-race self-test inventory",
        )
        == stale_inventory_raw + b" ",
        "failed post-authoring race did not preserve the external inventory change",
    )

    (
        stale_adr_root,
        stale_adr_authoring_path,
        stale_adr_allocation_path,
        stale_adr_authoring_raw,
        stale_adr_inventory_raw,
    ) = prepare_workspace("refresh-stale-adr")
    stale_adr_path = stale_adr_root / ADR_ALLOCATION_PATHS[0]

    def mutate_adr_after_plan(phase: str) -> None:
        if phase == "plan-ready":
            _atomic_write(stale_adr_path, b"changed ADR source\n")

    try:
        refresh_incomplete_authoring(
            stale_adr_authoring_path,
            schema_path,
            source_root=stale_adr_root,
            validate_semantics=False,
            _metric_provider=sample_metrics,
            _phase_hook=mutate_adr_after_plan,
        )
    except SelectorClosureGenerationError:
        pass
    else:
        _fail("incomplete refresh accepted an ADR changed after planning")
    _require(
        read_bounded_regular_file(
            stale_adr_authoring_path,
            maximum_bytes=MAX_EXPANDED_BYTES,
            label="stale-ADR self-test authoring",
        )
        == stale_adr_authoring_raw
        and read_bounded_regular_file(
            stale_adr_allocation_path,
            maximum_bytes=MAX_ALLOCATION_INVENTORY_BYTES,
            label="stale-ADR self-test inventory",
        )
        == stale_adr_inventory_raw,
        "failed stale-ADR refresh changed maintained files",
    )

    (
        alias_root,
        alias_authoring_path,
        alias_allocation_path,
        _,
        _,
    ) = prepare_workspace("refresh-alias")
    alias_allocation_path.unlink()
    os.link(alias_authoring_path, alias_allocation_path)
    try:
        refresh_incomplete_authoring(
            alias_authoring_path,
            schema_path,
            source_root=alias_root,
            validate_semantics=False,
            _metric_provider=sample_metrics,
        )
    except SelectorClosureGenerationError:
        pass
    else:
        _fail("incomplete refresh accepted aliased maintained files")

    for workspace_name, hostile_status in (
        ("refresh-reviewed", "INCOMPLETE_FAIL_CLOSED"),
        ("refresh-complete", "COMPLETE"),
    ):
        (
            gated_root,
            gated_authoring_path,
            gated_allocation_path,
            _,
            _,
        ) = prepare_workspace(workspace_name)
        gated_raw = read_bounded_regular_file(
            gated_allocation_path,
            maximum_bytes=MAX_ALLOCATION_INVENTORY_BYTES,
            label="gated refresh self-test inventory",
        )
        gated_inventory = parse_json_bytes(
            gated_raw,
            label="gated refresh self-test inventory",
        )
        gated_inventory["status"] = hostile_status
        gated_inventory["provenance_review"]["status"] = "REVIEWED"
        gated_inventory["provenance_review"]["reviewed_assignment_sha256"] = (
            provenance_assignment_sha256(
                gated_inventory["documents"],
                gated_inventory["allocations"],
                gated_inventory["exclusions"],
                gated_inventory["allocation_review_profile"],
                gated_inventory["semantic_review_subject"],
            )
        )
        _atomic_write(
            gated_allocation_path,
            inventory_bytes(gated_inventory),
        )
        try:
            refresh_incomplete_authoring(
                gated_authoring_path,
                schema_path,
                source_root=gated_root,
                validate_semantics=False,
                _metric_provider=sample_metrics,
            )
        except SelectorClosureGenerationError:
            pass
        else:
            _fail("incomplete refresh accepted reviewed or complete inventory")

    cas_path = directory / "refresh-cas-guard.json"
    cas_current = b'{"state":"current"}\n'
    _atomic_write(cas_path, cas_current)
    try:
        _atomic_replace_if_current(
            cas_path,
            b'{"state":"replacement"}\n',
            expected_current=b'{"state":"stale"}\n',
            maximum_bytes=MAX_EXPANDED_BYTES,
            label="refresh CAS self-test",
        )
    except (SelectorClosureCodecError, SelectorClosureGenerationError):
        pass
    else:
        _fail("incomplete refresh CAS overwrote an unexpected current file")
    _require(
        read_bounded_regular_file(
            cas_path,
            maximum_bytes=MAX_EXPANDED_BYTES,
            label="refresh CAS self-test current file",
        )
        == cas_current,
        "failed incomplete refresh CAS changed the current file",
    )


def _run_review_transaction_self_test(directory: Path) -> None:
    """Crash every durable edge and prove exact legal-prefix recovery."""

    from selector_allocation_review import (
        REQUIRED_SOURCE_ROLES,
        ReviewAuthorityPolicy,
        ReviewGenerationState,
        SelectorAllocationReviewError,
        _run_git,
        review_state_bytes,
        snapshot_review_source,
    )

    executable_sources = {
        "allocation_boundary_implementation": (
            ROOT / "scripts" / "selector_allocation_inventory.py"
        ),
        "semantic_generator": Path(__file__),
        "semantic_checker": ROOT / "scripts" / "check_selector_closure.py",
        "semantic_codec": ROOT / "scripts" / "selector_closure_codec.py",
        "resource_closure_projection": (
            ROOT / "scripts" / "selector_resource_closure.py"
        ),
        "review_boundary_implementation": (
            ROOT / "scripts" / "selector_allocation_review.py"
        ),
    }
    transaction_policy = ReviewAuthorityPolicy(
        repository="sepahead/NCP-transaction-self-test",
        branch="main",
        authorization_issuer_identity="owner@example.invalid",
        reviewer_identity="reviewer@example.invalid",
        reviewer_role="SELECTOR_ALLOCATION_PROVENANCE_REVIEWER",
        implementation_owner_identities=("owner@example.invalid",),
    )

    templates: dict[str, tuple[Path, ReviewPersistencePlan]] = {}

    def build_template(action: str) -> tuple[Path, ReviewPersistencePlan]:
        _require(
            action in {"PROMOTE_TO_REVIEWED", "REOPEN_TO_NOT_REVIEWED"},
            "transaction self-test action is invalid",
        )
        slug = "promotion" if action == "PROMOTE_TO_REVIEWED" else "reopen"
        repo = directory / f"transaction-template-{slug}"
        repo.mkdir()
        _run_git(repo, "init", "-b", "main", maximum_output_bytes=4096)
        _run_git(
            repo,
            "config",
            "user.name",
            "NCP transaction self test",
            maximum_output_bytes=4096,
        )
        _run_git(
            repo,
            "config",
            "user.email",
            "transaction-self-test@example.invalid",
            maximum_output_bytes=4096,
        )
        genesis = ReviewGenerationState.genesis()
        assignment_sha256 = "a" * 64
        receipt_sha256 = "b" * 64
        if action == "PROMOTE_TO_REVIEWED":
            expected_inventory = b'{"status":"not-reviewed-expected"}\n'
            next_inventory = b'{"status":"reviewed-next"}\n'
            expected_state = genesis
            next_state = ReviewGenerationState(
                state_version=1,
                next_review_generation=1,
                active_assignment_sha256=assignment_sha256,
                active_inventory_sha256=sha256(next_inventory).hexdigest(),
                current_receipt_sha256=receipt_sha256,
                last_consumed_receipt_sha256=receipt_sha256,
                prior_state_sha256=genesis.commitment()["sha256"],
            )
            write_order = PROMOTION_WRITE_ORDER
        else:
            expected_inventory = b'{"status":"reviewed-expected"}\n'
            next_inventory = b'{"status":"not-reviewed-next"}\n'
            expected_state = ReviewGenerationState(
                state_version=1,
                next_review_generation=1,
                active_assignment_sha256=assignment_sha256,
                active_inventory_sha256=sha256(expected_inventory).hexdigest(),
                current_receipt_sha256=receipt_sha256,
                last_consumed_receipt_sha256=receipt_sha256,
                prior_state_sha256=genesis.commitment()["sha256"],
            )
            next_state = ReviewGenerationState(
                state_version=2,
                next_review_generation=2,
                active_assignment_sha256=None,
                active_inventory_sha256=None,
                current_receipt_sha256=None,
                last_consumed_receipt_sha256=receipt_sha256,
                prior_state_sha256=expected_state.commitment()["sha256"],
            )
            write_order = REOPEN_WRITE_ORDER
        expected_state.validate()
        next_state.validate()
        mutable_expected = {
            "allocation_inventory": expected_inventory,
            "semantic_authoring_source": (
                f'{{"authoring":"{slug}-expected"}}\n'.encode("ascii")
            ),
            "semantic_compact_source": (
                f'{{"compact":"{slug}-expected"}}\n'.encode("ascii")
            ),
            "review_generation_state": review_state_bytes(expected_state),
        }
        mutable_next = {
            "allocation_inventory": next_inventory,
            "semantic_authoring_source": (
                f'{{"authoring":"{slug}-next"}}\n'.encode("ascii")
            ),
            "semantic_compact_source": (
                f'{{"compact":"{slug}-next"}}\n'.encode("ascii")
            ),
            "review_generation_state": review_state_bytes(next_state),
        }
        expected_by_role: dict[str, bytes] = {}
        for role, relative_path, _maximum_bytes in REQUIRED_SOURCE_ROLES:
            if role in mutable_expected:
                raw = mutable_expected[role]
            elif role in executable_sources:
                raw = executable_sources[role].read_bytes()
            else:
                raw = f"{role} expected self-test bytes\n".encode("ascii")
            path = repo / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            _atomic_write(path, raw)
            expected_by_role[role] = raw
        _run_git(repo, "add", "--all", maximum_output_bytes=4096)
        _run_git(
            repo,
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-m",
            "Create review transaction fixture",
            maximum_output_bytes=4096,
        )
        commit = (
            _run_git(
                repo,
                "rev-parse",
                "HEAD",
                maximum_output_bytes=128,
            )
            .decode("ascii")
            .strip()
        )
        snapshot = snapshot_review_source(
            repo,
            commit,
            transaction_policy,
            require_current_clean_head=True,
        )
        artifacts = tuple(
            ReviewArtifactTransition(
                role=role,
                path=repo / _review_role_path(role),
                maximum_bytes=_review_role_limit(role),
                expected_raw=expected_by_role[role],
                next_raw=mutable_next[role],
            )
            for role in REVIEW_ARTIFACT_ROLES
        )
        plan = ReviewPersistencePlan(
            action=action,
            source_cut=snapshot.source_cut,
            transition_subject_sha256=(
                "c" * 64 if action == "PROMOTE_TO_REVIEWED" else "d" * 64
            ),
            review_receipt_sha256=receipt_sha256,
            reviewed_assignment_sha256=assignment_sha256,
            artifacts=artifacts,
            write_order=write_order,
            expected_state=expected_state,
            next_state=next_state,
        )
        if action == "REOPEN_TO_NOT_REVIEWED":
            prior_artifacts = tuple(
                ReviewArtifactTransition(
                    role=item.role,
                    path=item.path,
                    maximum_bytes=item.maximum_bytes,
                    expected_raw=item.next_raw,
                    next_raw=item.expected_raw,
                )
                for item in artifacts
            )
            prior_attached = _attached_control(
                lineage_id="0" * 32,
                repository=snapshot.source_cut["repository"],
                source_cut=snapshot.source_cut,
                state=expected_state,
                artifacts=prior_artifacts,
            )
            _atomic_write(
                _git_private_path(repo, REVIEW_CONTROL_FILE),
                _control_bytes(prior_attached),
                create_only=True,
                create_mode=0o600,
            )
        return repo, plan

    def workspace(
        name: str,
        action: str = "PROMOTE_TO_REVIEWED",
    ) -> tuple[Path, ReviewPersistencePlan]:
        if action not in templates:
            templates[action] = build_template(action)
        template_repo, template_plan = templates[action]
        repo = directory / name
        shutil.copytree(template_repo, repo, copy_function=shutil.copy2)
        artifacts = tuple(
            ReviewArtifactTransition(
                role=item.role,
                path=repo / _review_role_path(item.role),
                maximum_bytes=item.maximum_bytes,
                expected_raw=item.expected_raw,
                next_raw=item.next_raw,
            )
            for item in template_plan.artifacts
        )
        return repo, ReviewPersistencePlan(
            action=template_plan.action,
            source_cut=copy.deepcopy(template_plan.source_cut),
            transition_subject_sha256=template_plan.transition_subject_sha256,
            review_receipt_sha256=template_plan.review_receipt_sha256,
            reviewed_assignment_sha256=template_plan.reviewed_assignment_sha256,
            artifacts=artifacts,
            write_order=template_plan.write_order,
            expected_state=template_plan.expected_state,
            next_state=template_plan.next_state,
        )

    large_repo, large_template = workspace("transaction-large-control-roundtrip")
    maintained_authoring_raw = read_bounded_regular_file(
        ROOT / _review_role_path("semantic_authoring_source"),
        maximum_bytes=_review_role_limit("semantic_authoring_source"),
        label="large pending-control maintained authoring",
    )
    _require(
        len(maintained_authoring_raw) > 12 * 1024 * 1024
        and maintained_authoring_raw.endswith(b"\n"),
        "large pending-control fixture is not actual-size maintained authoring",
    )
    large_next_authoring_raw = maintained_authoring_raw[:-1] + b" \n"
    large_artifacts = tuple(
        ReviewArtifactTransition(
            role=item.role,
            path=item.path,
            maximum_bytes=item.maximum_bytes,
            expected_raw=(
                maintained_authoring_raw
                if item.role == "semantic_authoring_source"
                else item.expected_raw
            ),
            next_raw=(
                large_next_authoring_raw
                if item.role == "semantic_authoring_source"
                else item.next_raw
            ),
        )
        for item in large_template.artifacts
    )
    large_plan = ReviewPersistencePlan(
        action=large_template.action,
        source_cut=copy.deepcopy(large_template.source_cut),
        transition_subject_sha256=large_template.transition_subject_sha256,
        review_receipt_sha256=large_template.review_receipt_sha256,
        reviewed_assignment_sha256=large_template.reviewed_assignment_sha256,
        artifacts=large_artifacts,
        write_order=large_template.write_order,
        expected_state=large_template.expected_state,
        next_state=large_template.next_state,
    )
    large_control_raw, large_control = _pending_control(
        large_repo,
        large_plan,
        current_control_raw=None,
        current_control=None,
    )
    _require(
        len(large_control_raw) <= MAX_REVIEW_CONTROL_BYTES
        and max(len(item["expected_base64"]) for item in large_control["artifacts"])
        > 16 * 1024 * 1024,
        "actual-size pending control did not exercise the large-string parser",
    )
    try:
        parse_json_bytes(
            large_control_raw,
            label="large pending-control default parser rejection",
            maximum_bytes=MAX_REVIEW_CONTROL_BYTES,
        )
    except SelectorClosureCodecError:
        pass
    else:
        _fail("default JSON string bound accepted an actual-size pending control")
    large_control_path = directory / "actual-size-pending-control.json"
    _atomic_write(
        large_control_path,
        large_control_raw,
        create_only=True,
        create_mode=0o600,
    )
    loaded_large_control = _read_optional_control(large_control_path)
    _require(
        loaded_large_control == (large_control_raw, large_control),
        "actual-size pending control did not round-trip through its bounded parser",
    )

    def commit_fixture(repo: Path, message: str) -> str:
        _run_git(repo, "add", "--all", maximum_output_bytes=4096)
        _run_git(
            repo,
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-m",
            message,
            maximum_output_bytes=4096,
        )
        return (
            _run_git(
                repo,
                "rev-parse",
                "HEAD",
                maximum_output_bytes=128,
            )
            .decode("ascii")
            .strip()
        )

    def plan_from_clean_current_cut(
        repo: Path,
        *,
        action: str,
        expected_state: ReviewGenerationState,
        next_state: ReviewGenerationState,
        next_by_role: dict[str, bytes],
        receipt_sha256: str,
        assignment_sha256: str,
        transition_subject_sha256: str,
    ) -> ReviewPersistencePlan:
        _require(
            set(next_by_role) == set(REVIEW_ARTIFACT_ROLES),
            "cycle fixture next artifacts differ from the four exact roles",
        )
        commit = (
            _run_git(
                repo,
                "rev-parse",
                "HEAD",
                maximum_output_bytes=128,
            )
            .decode("ascii")
            .strip()
        )
        snapshot = snapshot_review_source(
            repo,
            commit,
            transaction_policy,
            require_current_clean_head=True,
        )
        artifacts: list[ReviewArtifactTransition] = []
        for role in REVIEW_ARTIFACT_ROLES:
            path = repo / _review_role_path(role)
            expected_raw = read_bounded_regular_file(
                path,
                maximum_bytes=_review_role_limit(role),
                label=f"cycle fixture expected {role}",
            )
            _require(
                expected_raw != next_by_role[role],
                f"cycle fixture transition does not change {role}",
            )
            artifacts.append(
                ReviewArtifactTransition(
                    role=role,
                    path=path,
                    maximum_bytes=_review_role_limit(role),
                    expected_raw=expected_raw,
                    next_raw=next_by_role[role],
                )
            )
        _require(
            artifacts[-1].expected_raw == review_state_bytes(expected_state)
            and artifacts[-1].next_raw == review_state_bytes(next_state),
            "cycle fixture state bytes differ from its projections",
        )
        return ReviewPersistencePlan(
            action=action,
            source_cut=snapshot.source_cut,
            transition_subject_sha256=transition_subject_sha256,
            review_receipt_sha256=receipt_sha256,
            reviewed_assignment_sha256=assignment_sha256,
            artifacts=tuple(artifacts),
            write_order=(
                PROMOTION_WRITE_ORDER
                if action == "PROMOTE_TO_REVIEWED"
                else REOPEN_WRITE_ORDER
            ),
            expected_state=expected_state,
            next_state=next_state,
        )

    def rebind_plan(repo: Path, plan: ReviewPersistencePlan) -> ReviewPersistencePlan:
        return ReviewPersistencePlan(
            action=plan.action,
            source_cut=copy.deepcopy(plan.source_cut),
            transition_subject_sha256=plan.transition_subject_sha256,
            review_receipt_sha256=plan.review_receipt_sha256,
            reviewed_assignment_sha256=plan.reviewed_assignment_sha256,
            artifacts=tuple(
                ReviewArtifactTransition(
                    role=item.role,
                    path=repo / _review_role_path(item.role),
                    maximum_bytes=item.maximum_bytes,
                    expected_raw=item.expected_raw,
                    next_raw=item.next_raw,
                )
                for item in plan.artifacts
            ),
            write_order=plan.write_order,
            expected_state=plan.expected_state,
            next_state=plan.next_state,
        )

    for action, order in (
        ("PROMOTE_TO_REVIEWED", PROMOTION_WRITE_ORDER),
        ("REOPEN_TO_NOT_REVIEWED", REOPEN_WRITE_ORDER),
    ):
        slug = "promotion" if action == "PROMOTE_TO_REVIEWED" else "reopen"
        phases = [
            "control:pending:temporary-file-fsynced",
            "control:pending:before-install",
            "control:pending:parent-directory-fsynced",
            "control:pending:durable",
            "inventory:fail-closed:temporary-file-fsynced",
            "inventory:fail-closed:before-install",
            "inventory:fail-closed:parent-directory-fsynced",
            "inventory:fail-closed:durable",
            "control:pending-fence:temporary-file-fsynced",
            "control:pending-fence:before-install",
            "control:pending-fence:parent-directory-fsynced",
            "control:pending-fence:durable",
            *(
                f"artifact:{role}:{phase}"
                for role in order
                if not (
                    action == "REOPEN_TO_NOT_REVIEWED"
                    and role == "allocation_inventory"
                )
                for phase in (
                    "temporary-file-fsynced",
                    "before-install",
                    "parent-directory-fsynced",
                    "durable",
                )
            ),
            "control:attach:temporary-file-fsynced",
            "control:attach:before-install",
            "control:attach:parent-directory-fsynced",
            "control:attached:durable",
        ]
        for index, crash_phase in enumerate(phases):
            repo, plan = workspace(
                f"transaction-crash-{slug}-{index:02d}",
                action,
            )
            child = os.fork()
            if child == 0:

                def hard_crash(phase: str) -> None:
                    if phase == crash_phase:
                        os._exit(97)

                try:
                    apply_review_persistence_plan(
                        repo,
                        plan,
                        phase_hook=hard_crash,
                    )
                except BaseException as error:
                    print(
                        "transaction crash child failed before "
                        f"{action}/{crash_phase}: {error}",
                        file=sys.stderr,
                        flush=True,
                    )
                    os._exit(98)
                os._exit(0)
            _, status = os.waitpid(child, 0)
            _require(
                os.WIFEXITED(status) and os.WEXITSTATUS(status) == 97,
                f"transaction crash phase was not reached: {action}/{crash_phase}",
            )
            control_path = _git_private_path(repo, REVIEW_CONTROL_FILE)
            observed_control = _read_optional_control(control_path)
            attached_is_successor = (
                observed_control is not None
                and observed_control[1]["status"] == "ATTACHED"
                and observed_control[1]["tracked_state"] == plan.next_state.projection()
                and observed_control[1]["tracked_state_sha256"]
                == plan.next_state.commitment()["sha256"]
                and observed_control[1]["tracked_artifacts"]
                == _attached_artifact_commitments(
                    plan.artifacts,
                    use_next=True,
                )
            )
            if observed_control is None or (
                observed_control[1]["status"] == "ATTACHED"
                and not attached_is_successor
            ):
                apply_review_persistence_plan(repo, plan)
            else:
                recover_pending_review_transition(repo)
            control = _read_optional_control(control_path)
            _require(
                control is not None and control[1]["status"] == "ATTACHED",
                f"transaction did not attach after {action}/{crash_phase}",
            )
            for artifact in plan.artifacts:
                _require(
                    read_bounded_regular_file(
                        artifact.path,
                        maximum_bytes=artifact.maximum_bytes,
                        label=f"transaction crash result {artifact.role}",
                    )
                    == artifact.next_raw,
                    f"transaction crash recovery differs for {artifact.role}",
                )
            _require(
                not any(
                    CODEC_TEMP_NAME.fullmatch(path.name)
                    for artifact in plan.artifacts
                    for path in artifact.path.parent.iterdir()
                ),
                f"transaction recovery left a codec temp: {action}/{crash_phase}",
            )

    def expect_rejection(action: Any, label: str) -> None:
        try:
            action()
        except (
            OSError,
            SelectorAllocationReviewError,
            SelectorClosureCodecError,
            SelectorClosureGenerationError,
        ):
            return
        _fail(f"review transaction self-test accepted {label}")

    # Prove that the high-water control is historical after reopen, while the
    # next promotion can bind exactly one clean descendant source cut.  This is
    # the minimum complete lifecycle: promote, reopen, edit, promote again.
    cycle_template_repo, cycle_first_promotion = workspace(
        "transaction-template-two-cycle"
    )
    first_attached = apply_review_persistence_plan(
        cycle_template_repo,
        cycle_first_promotion,
    )
    _require(
        first_attached["tracked_state"]
        == cycle_first_promotion.next_state.projection(),
        "first cycle promotion did not attach its exact active state",
    )
    commit_fixture(
        cycle_template_repo,
        "Commit first reviewed transaction result",
    )

    first_active_state = cycle_first_promotion.next_state
    reopened_state = ReviewGenerationState(
        state_version=2,
        next_review_generation=2,
        active_assignment_sha256=None,
        active_inventory_sha256=None,
        current_receipt_sha256=None,
        last_consumed_receipt_sha256=(cycle_first_promotion.review_receipt_sha256),
        prior_state_sha256=first_active_state.commitment()["sha256"],
    )
    reopened_state.validate()
    reopened_inventory = (
        canonical_bytes(
            {
                "cycle": "FIRST_REOPEN",
                "provenance_review": {
                    "reviewed_assignment_sha256": "0" * 64,
                    "status": "NOT_REVIEWED",
                },
            }
        )
        + b"\n"
    )
    reopened_authoring = b'{"cycle":"first-reopen-authoring"}\n'
    reopened_compact = b'{"cycle":"first-reopen-compact"}\n'
    cycle_reopen = plan_from_clean_current_cut(
        cycle_template_repo,
        action="REOPEN_TO_NOT_REVIEWED",
        expected_state=first_active_state,
        next_state=reopened_state,
        next_by_role={
            "allocation_inventory": reopened_inventory,
            "semantic_authoring_source": reopened_authoring,
            "semantic_compact_source": reopened_compact,
            "review_generation_state": review_state_bytes(reopened_state),
        },
        receipt_sha256=cycle_first_promotion.review_receipt_sha256,
        assignment_sha256=cycle_first_promotion.reviewed_assignment_sha256,
        transition_subject_sha256="1" * 64,
    )
    reopened_attached = apply_review_persistence_plan(
        cycle_template_repo,
        cycle_reopen,
    )
    _require(
        reopened_attached["tracked_state"] == reopened_state.projection(),
        "first cycle reopen did not attach its exact inactive state",
    )
    commit_fixture(
        cycle_template_repo,
        "Commit reopened transaction result",
    )

    second_expected_inventory = (
        canonical_bytes(
            {
                "cycle": "SECOND_REVIEW_EXPECTED",
                "provenance_review": {
                    "reviewed_assignment_sha256": "0" * 64,
                    "status": "NOT_REVIEWED",
                },
            }
        )
        + b"\n"
    )
    second_expected_authoring = b'{"cycle":"second-review-authoring"}\n'
    second_expected_compact = b'{"cycle":"second-review-compact"}\n'
    for role, raw in (
        ("allocation_inventory", second_expected_inventory),
        ("semantic_authoring_source", second_expected_authoring),
        ("semantic_compact_source", second_expected_compact),
    ):
        _atomic_write(
            cycle_template_repo / _review_role_path(role),
            raw,
        )
    commit_fixture(
        cycle_template_repo,
        "Commit clean descendant review edits",
    )

    second_assignment_sha256 = "2" * 64
    second_receipt_sha256 = "3" * 64
    second_inventory = (
        canonical_bytes(
            {
                "cycle": "SECOND_REVIEW_PROMOTED",
                "provenance_review": {
                    "reviewed_assignment_sha256": second_assignment_sha256,
                    "status": "REVIEWED",
                },
            }
        )
        + b"\n"
    )
    second_state = ReviewGenerationState(
        state_version=3,
        next_review_generation=2,
        active_assignment_sha256=second_assignment_sha256,
        active_inventory_sha256=sha256(second_inventory).hexdigest(),
        current_receipt_sha256=second_receipt_sha256,
        last_consumed_receipt_sha256=second_receipt_sha256,
        prior_state_sha256=reopened_state.commitment()["sha256"],
    )
    second_state.validate()
    cycle_second_promotion = plan_from_clean_current_cut(
        cycle_template_repo,
        action="PROMOTE_TO_REVIEWED",
        expected_state=reopened_state,
        next_state=second_state,
        next_by_role={
            "allocation_inventory": second_inventory,
            "semantic_authoring_source": (
                b'{"cycle":"second-review-promoted-authoring"}\n'
            ),
            "semantic_compact_source": (
                b'{"cycle":"second-review-promoted-compact"}\n'
            ),
            "review_generation_state": review_state_bytes(second_state),
        },
        receipt_sha256=second_receipt_sha256,
        assignment_sha256=second_assignment_sha256,
        transition_subject_sha256="4" * 64,
    )

    def cycle_workspace(name: str) -> tuple[Path, ReviewPersistencePlan]:
        repo = directory / name
        shutil.copytree(
            cycle_template_repo,
            repo,
            copy_function=shutil.copy2,
        )
        return repo, rebind_plan(repo, cycle_second_promotion)

    cycle_success_repo, cycle_success_plan = cycle_workspace(
        "transaction-two-cycle-success"
    )
    cycle_prior = _read_optional_control(
        _git_private_path(cycle_success_repo, REVIEW_CONTROL_FILE)
    )
    _require(
        cycle_prior is not None and cycle_prior[1]["status"] == "ATTACHED",
        "two-cycle fixture has no attached reopen high-water control",
    )
    cycle_pending_raw, cycle_pending = _pending_control(
        cycle_success_repo,
        cycle_success_plan,
        current_control_raw=cycle_prior[0],
        current_control=cycle_prior[1],
    )
    reanchor = cycle_pending["open_source_reanchor"]
    _require(
        isinstance(reanchor, dict)
        and reanchor["prior_attached"] == cycle_prior[1]
        and reanchor["prior_attached_sha256"] == sha256(cycle_prior[0]).hexdigest()
        and reanchor["prior_source_commit"] == cycle_prior[1]["last_source_commit"]
        and reanchor["reanchored_source_commit"]
        == cycle_success_plan.source_cut["commit"]
        and reanchor["prior_source_commit"] != reanchor["reanchored_source_commit"]
        and reanchor["prior_tracked_artifacts"] == cycle_prior[1]["tracked_artifacts"]
        and reanchor["reanchored_expected_artifacts"]
        == _attached_artifact_commitments(
            cycle_success_plan.artifacts,
            use_next=False,
        ),
        "two-cycle pending control omitted an exact re-anchor binding",
    )
    _require(
        cycle_pending_raw == _control_bytes(cycle_pending),
        "two-cycle pending control is not canonical",
    )

    for label, mutant in (
        (
            "changed re-anchor expected-attached hash",
            lambda value: value.__setitem__(
                "expected_attached_sha256",
                "5" * 64,
            ),
        ),
        (
            "changed re-anchor prior source tree",
            lambda value: value["open_source_reanchor"].__setitem__(
                "prior_source_tree",
                "6" * len(value["open_source_reanchor"]["prior_source_tree"]),
            ),
        ),
        (
            "changed re-anchor descendant artifacts",
            lambda value: value["open_source_reanchor"][
                "reanchored_expected_artifacts"
            ][0].__setitem__("sha256", "7" * 64),
        ),
        (
            "changed nested prior attachment",
            lambda value: value["open_source_reanchor"]["prior_attached"][
                "tracked_artifacts"
            ][0].__setitem__("sha256", "8" * 64),
        ),
        (
            "recursive pending prior attachment",
            lambda value: value["open_source_reanchor"]["prior_attached"].__setitem__(
                "status",
                "PENDING",
            ),
        ),
    ):
        changed = copy.deepcopy(cycle_pending)
        mutant(changed)
        expect_rejection(
            lambda value=changed: _validate_review_control(value),
            label,
        )

    cycle_final = apply_review_persistence_plan(
        cycle_success_repo,
        cycle_success_plan,
    )
    _require(
        cycle_final == cycle_pending["next_attached"]
        and cycle_final["tracked_state"] == second_state.projection()
        and all(
            read_bounded_regular_file(
                item.path,
                maximum_bytes=item.maximum_bytes,
                label=f"two-cycle final artifact {item.role}",
            )
            == item.next_raw
            for item in cycle_success_plan.artifacts
        ),
        "two-cycle promotion did not install one exact attached successor",
    )

    active_repo, active_plan = cycle_workspace("transaction-reanchor-active-reviewed")
    active_control = _read_optional_control(
        _git_private_path(active_repo, REVIEW_CONTROL_FILE)
    )
    _require(active_control is not None, "active-state mutant has no control")
    active_expected_plan = ReviewPersistencePlan(
        action=active_plan.action,
        source_cut=copy.deepcopy(active_plan.source_cut),
        transition_subject_sha256=active_plan.transition_subject_sha256,
        review_receipt_sha256=active_plan.review_receipt_sha256,
        reviewed_assignment_sha256=active_plan.reviewed_assignment_sha256,
        artifacts=active_plan.artifacts,
        write_order=active_plan.write_order,
        expected_state=first_active_state,
        next_state=active_plan.next_state,
    )
    expect_rejection(
        lambda: _build_open_source_reanchor(
            active_repo,
            current_control_raw=active_control[0],
            current_control=active_control[1],
            plan=active_expected_plan,
        ),
        "active reviewed state re-anchor",
    )

    same_commit_repo, same_commit_plan = cycle_workspace(
        "transaction-reanchor-same-commit"
    )
    same_commit_control = _read_optional_control(
        _git_private_path(same_commit_repo, REVIEW_CONTROL_FILE)
    )
    _require(
        same_commit_control is not None,
        "same-commit mutant has no control",
    )
    same_source_cut = copy.deepcopy(same_commit_plan.source_cut)
    same_source_cut["commit"] = same_commit_control[1]["last_source_commit"]
    same_source_cut["tree"] = same_commit_control[1]["last_source_tree"]
    same_commit_mutant = ReviewPersistencePlan(
        action=same_commit_plan.action,
        source_cut=same_source_cut,
        transition_subject_sha256=same_commit_plan.transition_subject_sha256,
        review_receipt_sha256=same_commit_plan.review_receipt_sha256,
        reviewed_assignment_sha256=same_commit_plan.reviewed_assignment_sha256,
        artifacts=same_commit_plan.artifacts,
        write_order=same_commit_plan.write_order,
        expected_state=same_commit_plan.expected_state,
        next_state=same_commit_plan.next_state,
    )
    expect_rejection(
        lambda: _build_open_source_reanchor(
            same_commit_repo,
            current_control_raw=same_commit_control[0],
            current_control=same_commit_control[1],
            plan=same_commit_mutant,
        ),
        "same-commit open artifact drift",
    )

    non_promote_repo, non_promote_plan = cycle_workspace(
        "transaction-reanchor-non-promotion"
    )
    non_promote_control = _read_optional_control(
        _git_private_path(non_promote_repo, REVIEW_CONTROL_FILE)
    )
    _require(non_promote_control is not None, "non-promotion mutant has no control")
    non_promote_mutant = ReviewPersistencePlan(
        action="REOPEN_TO_NOT_REVIEWED",
        source_cut=copy.deepcopy(non_promote_plan.source_cut),
        transition_subject_sha256=non_promote_plan.transition_subject_sha256,
        review_receipt_sha256=non_promote_plan.review_receipt_sha256,
        reviewed_assignment_sha256=non_promote_plan.reviewed_assignment_sha256,
        artifacts=non_promote_plan.artifacts,
        write_order=REOPEN_WRITE_ORDER,
        expected_state=non_promote_plan.expected_state,
        next_state=non_promote_plan.next_state,
    )
    expect_rejection(
        lambda: _build_open_source_reanchor(
            non_promote_repo,
            current_control_raw=non_promote_control[0],
            current_control=non_promote_control[1],
            plan=non_promote_mutant,
        ),
        "non-promotion re-anchor",
    )

    dirty_repo, dirty_plan = cycle_workspace("transaction-reanchor-dirty")
    _atomic_write(dirty_repo / "unrelated-untracked", b"hostile\n")
    expect_rejection(
        lambda: apply_review_persistence_plan(dirty_repo, dirty_plan),
        "dirty descendant re-anchor",
    )

    staged_repo, staged_plan = cycle_workspace("transaction-reanchor-staged")
    staged_authoring = next(
        item
        for item in staged_plan.artifacts
        if item.role == "semantic_authoring_source"
    )
    _atomic_write(staged_authoring.path, staged_authoring.next_raw)
    _run_git(
        staged_repo,
        "add",
        "--",
        _review_role_path(staged_authoring.role),
        maximum_output_bytes=4096,
    )
    expect_rejection(
        lambda: apply_review_persistence_plan(staged_repo, staged_plan),
        "index-only descendant re-anchor",
    )

    mode_repo, mode_plan = cycle_workspace("transaction-reanchor-mode")
    mode_authoring = next(
        item for item in mode_plan.artifacts if item.role == "semantic_authoring_source"
    )
    original_mode = stat.S_IMODE(mode_authoring.path.stat().st_mode)
    os.chmod(mode_authoring.path, original_mode ^ stat.S_IXUSR)
    expect_rejection(
        lambda: apply_review_persistence_plan(mode_repo, mode_plan),
        "mode-changed descendant re-anchor",
    )

    group_mode_repo, group_mode_plan = cycle_workspace(
        "transaction-reanchor-group-executable-mode"
    )
    group_mode_authoring = next(
        item
        for item in group_mode_plan.artifacts
        if item.role == "semantic_authoring_source"
    )
    group_mode = stat.S_IMODE(group_mode_authoring.path.stat().st_mode)
    _require(
        group_mode & 0o111 == 0,
        "group-executable mode mutant requires a non-executable source",
    )
    os.chmod(group_mode_authoring.path, group_mode | stat.S_IXGRP)  # noqa: S103
    expect_rejection(
        lambda: apply_review_persistence_plan(
            group_mode_repo,
            group_mode_plan,
        ),
        "group-executable descendant re-anchor",
    )

    symlink_repo, symlink_plan = cycle_workspace("transaction-reanchor-symlink")
    symlink_authoring = next(
        item
        for item in symlink_plan.artifacts
        if item.role == "semantic_authoring_source"
    )
    symlink_target = directory / "transaction-reanchor-symlink-target"
    _atomic_write(symlink_target, symlink_authoring.expected_raw)
    symlink_authoring.path.unlink()
    os.symlink(symlink_target, symlink_authoring.path)
    expect_rejection(
        lambda: apply_review_persistence_plan(symlink_repo, symlink_plan),
        "symlinked descendant re-anchor",
    )

    rollback_repo, rollback_plan = cycle_workspace("transaction-reanchor-rollback")
    rollback_authoring = next(
        item
        for item in rollback_plan.artifacts
        if item.role == "semantic_authoring_source"
    )
    _atomic_write(rollback_authoring.path, reopened_authoring)
    expect_rejection(
        lambda: apply_review_persistence_plan(rollback_repo, rollback_plan),
        "rolled-back open artifact re-anchor",
    )

    nonancestor_repo, nonancestor_plan = cycle_workspace(
        "transaction-reanchor-nonancestor"
    )
    nonancestor_tree = (
        _run_git(
            nonancestor_repo,
            "rev-parse",
            "HEAD^{tree}",
            maximum_output_bytes=128,
        )
        .decode("ascii")
        .strip()
    )
    orphan_commit = (
        _run_git(
            nonancestor_repo,
            "commit-tree",
            nonancestor_tree,
            "-m",
            "Create clean non-ancestor re-anchor cut",
            maximum_output_bytes=128,
        )
        .decode("ascii")
        .strip()
    )
    _run_git(
        nonancestor_repo,
        "update-ref",
        "refs/heads/main",
        orphan_commit,
        maximum_output_bytes=4096,
    )
    orphan_snapshot = snapshot_review_source(
        nonancestor_repo,
        orphan_commit,
        transaction_policy,
        require_current_clean_head=True,
    )
    nonancestor_mutant = ReviewPersistencePlan(
        action=nonancestor_plan.action,
        source_cut=orphan_snapshot.source_cut,
        transition_subject_sha256=nonancestor_plan.transition_subject_sha256,
        review_receipt_sha256=nonancestor_plan.review_receipt_sha256,
        reviewed_assignment_sha256=nonancestor_plan.reviewed_assignment_sha256,
        artifacts=nonancestor_plan.artifacts,
        write_order=nonancestor_plan.write_order,
        expected_state=nonancestor_plan.expected_state,
        next_state=nonancestor_plan.next_state,
    )
    expect_rejection(
        lambda: apply_review_persistence_plan(
            nonancestor_repo,
            nonancestor_mutant,
        ),
        "non-descendant clean re-anchor",
    )

    hostile_repo, hostile_plan = workspace("transaction-hostile-source-cut")
    hostile_pending_raw, hostile_pending = _pending_control(
        hostile_repo,
        hostile_plan,
        current_control_raw=None,
        current_control=None,
    )

    def hostile_states() -> dict[str, str]:
        return _artifact_states(
            hostile_repo,
            hostile_pending,
            hostile_plan.artifacts,
        )

    hostile_by_role = {item.role: item for item in hostile_plan.artifacts}
    allocation_artifact = hostile_by_role["allocation_inventory"]
    _atomic_write(allocation_artifact.path, b"third-state\n")
    expect_rejection(hostile_states, "third-state tracked bytes")
    _atomic_write(allocation_artifact.path, allocation_artifact.expected_raw)

    immutable_path = hostile_repo / _review_role_path("allocation_schema")
    immutable_raw = immutable_path.read_bytes()
    _atomic_write(immutable_path, immutable_raw + b"hostile")
    expect_rejection(hostile_states, "changed immutable reviewed source")
    _atomic_write(immutable_path, immutable_raw)

    authoring_artifact = hostile_by_role["semantic_authoring_source"]
    _atomic_write(authoring_artifact.path, authoring_artifact.next_raw)
    _run_git(
        hostile_repo,
        "add",
        "--",
        _review_role_path(authoring_artifact.role),
        maximum_output_bytes=4096,
    )
    expect_rejection(hostile_states, "staged tracked transition output")
    _atomic_write(authoring_artifact.path, authoring_artifact.expected_raw)
    _run_git(
        hostile_repo,
        "add",
        "--",
        _review_role_path(authoring_artifact.role),
        maximum_output_bytes=4096,
    )

    _run_git(
        hostile_repo,
        "switch",
        "-c",
        "hostile-source-branch",
        maximum_output_bytes=4096,
    )
    expect_rejection(hostile_states, "substituted transition branch")
    _run_git(
        hostile_repo,
        "switch",
        "main",
        maximum_output_bytes=4096,
    )

    unrelated_path = hostile_repo / "unrelated-untracked"
    _atomic_write(unrelated_path, b"unrelated\n")
    expect_rejection(hostile_states, "unrelated untracked file")
    unrelated_path.unlink()

    mode_path = authoring_artifact.path
    original_mode = stat.S_IMODE(mode_path.stat().st_mode)
    os.chmod(mode_path, original_mode ^ stat.S_IXUSR)
    expect_rejection(hostile_states, "changed tracked executable mode")
    os.chmod(mode_path, original_mode)

    index_path = _review_role_path("allocation_inventory")
    _run_git(
        hostile_repo,
        "update-index",
        "--skip-worktree",
        "--",
        index_path,
        maximum_output_bytes=4096,
    )
    expect_rejection(hostile_states, "skip-worktree concealment")
    _run_git(
        hostile_repo,
        "update-index",
        "--no-skip-worktree",
        "--",
        index_path,
        maximum_output_bytes=4096,
    )
    _run_git(
        hostile_repo,
        "update-index",
        "--assume-unchanged",
        "--",
        index_path,
        maximum_output_bytes=4096,
    )
    expect_rejection(hostile_states, "assume-unchanged concealment")
    _run_git(
        hostile_repo,
        "update-index",
        "--no-assume-unchanged",
        "--",
        index_path,
        maximum_output_bytes=4096,
    )

    link_source = directory / "transaction-hostile-link-source"
    _atomic_write(link_source, allocation_artifact.expected_raw)
    allocation_artifact.path.unlink()
    os.symlink(link_source, allocation_artifact.path)
    expect_rejection(hostile_states, "symlinked tracked transition output")
    allocation_artifact.path.unlink()
    os.link(link_source, allocation_artifact.path)
    expect_rejection(hostile_states, "hard-linked tracked transition output")
    allocation_artifact.path.unlink()
    link_source.unlink()
    _atomic_write(allocation_artifact.path, allocation_artifact.expected_raw)
    _require(
        all(value == "EXPECTED" for value in hostile_states().values()),
        "hostile source-cut fixture did not return to the exact expected state",
    )

    for action, poisoned_role in (
        ("PROMOTE_TO_REVIEWED", "allocation_inventory"),
        ("REOPEN_TO_NOT_REVIEWED", "semantic_compact_source"),
    ):
        slug = "promotion" if action == "PROMOTE_TO_REVIEWED" else "reopen"
        poisoned_repo, poisoned_plan = workspace(
            f"transaction-poisoned-{slug}",
            action,
        )
        existing_poisoned_control = _read_optional_control(
            _git_private_path(poisoned_repo, REVIEW_CONTROL_FILE)
        )
        poisoned_raw, poisoned_pending = _pending_control(
            poisoned_repo,
            poisoned_plan,
            current_control_raw=(
                existing_poisoned_control[0]
                if existing_poisoned_control is not None
                else None
            ),
            current_control=(
                existing_poisoned_control[1]
                if existing_poisoned_control is not None
                else None
            ),
        )
        poisoned_control_path = _git_private_path(
            poisoned_repo,
            REVIEW_CONTROL_FILE,
        )
        _atomic_write(
            poisoned_control_path,
            poisoned_raw,
            create_only=existing_poisoned_control is None,
            create_mode=0o600,
        )
        poisoned_by_role = {item.role: item for item in poisoned_plan.artifacts}
        poisoned_artifact = poisoned_by_role[poisoned_role]
        _atomic_write(poisoned_artifact.path, poisoned_artifact.next_raw)
        expect_rejection(
            lambda repo=poisoned_repo: recover_pending_review_transition(repo),
            f"illegal {action} artifact prefix",
        )
        poisoned_inventory = poisoned_by_role["allocation_inventory"]
        expected_fail_closed = (
            poisoned_inventory.expected_raw
            if action == "PROMOTE_TO_REVIEWED"
            else poisoned_inventory.next_raw
        )
        _require(
            read_bounded_regular_file(
                poisoned_inventory.path,
                maximum_bytes=poisoned_inventory.maximum_bytes,
                label=f"poisoned {action} inventory",
            )
            == expected_fail_closed,
            f"poisoned {action} did not restore the fail-closed inventory side",
        )

    for action in ("PROMOTE_TO_REVIEWED", "REOPEN_TO_NOT_REVIEWED"):
        slug = "promotion" if action == "PROMOTE_TO_REVIEWED" else "reopen"
        third_repo, third_plan = workspace(
            f"transaction-third-inventory-{slug}",
            action,
        )
        existing_third_control = _read_optional_control(
            _git_private_path(third_repo, REVIEW_CONTROL_FILE)
        )
        third_raw, third_pending = _pending_control(
            third_repo,
            third_plan,
            current_control_raw=(
                existing_third_control[0]
                if existing_third_control is not None
                else None
            ),
            current_control=(
                existing_third_control[1]
                if existing_third_control is not None
                else None
            ),
        )
        third_control_path = _git_private_path(
            third_repo,
            REVIEW_CONTROL_FILE,
        )
        _atomic_write(
            third_control_path,
            third_raw,
            create_only=existing_third_control is None,
            create_mode=0o600,
        )
        third_by_role = {item.role: item for item in third_plan.artifacts}
        third_inventory = third_by_role["allocation_inventory"]
        _atomic_write(third_inventory.path, b"literal-third-inventory-state\n")
        expect_rejection(
            lambda repo=third_repo: recover_pending_review_transition(repo),
            f"literal third-state {action} inventory",
        )
        fail_closed_raw = (
            third_inventory.expected_raw
            if action == "PROMOTE_TO_REVIEWED"
            else third_inventory.next_raw
        )
        _require(
            read_bounded_regular_file(
                third_inventory.path,
                maximum_bytes=third_inventory.maximum_bytes,
                label=f"third-state {action} fail-closed inventory",
            )
            == fail_closed_raw,
            f"third-state {action} did not install exact fail-closed inventory",
        )
        recovered = recover_pending_review_transition(third_repo)
        _require(
            recovered == third_pending["next_attached"],
            f"fresh recovery did not attach the {action} successor",
        )
        _require(
            all(
                read_bounded_regular_file(
                    item.path,
                    maximum_bytes=item.maximum_bytes,
                    label=f"third-state recovery result {item.role}",
                )
                == item.next_raw
                for item in third_plan.artifacts
            ),
            f"fresh recovery did not converge all {action} artifacts",
        )

    missing_control_repo, missing_control_plan = workspace(
        "transaction-missing-high-water",
        "REOPEN_TO_NOT_REVIEWED",
    )
    expect_rejection(
        lambda: _pending_control(
            missing_control_repo,
            missing_control_plan,
            current_control_raw=None,
            current_control=None,
        ),
        "non-genesis transition with missing private high-water control",
    )

    ancestry_repo, ancestry_plan = workspace(
        "transaction-high-water-ancestry",
        "REOPEN_TO_NOT_REVIEWED",
    )
    orphan_commit = (
        _run_git(
            ancestry_repo,
            "commit-tree",
            ancestry_plan.source_cut["tree"],
            "-m",
            "Create non-ancestor high-water object",
            maximum_output_bytes=128,
        )
        .decode("ascii")
        .strip()
    )
    orphan_source_cut = copy.deepcopy(ancestry_plan.source_cut)
    orphan_source_cut["commit"] = orphan_commit
    orphan_attached = _attached_control(
        lineage_id="1" * 32,
        repository=ancestry_plan.source_cut["repository"],
        source_cut=orphan_source_cut,
        state=ancestry_plan.expected_state,
        artifacts=tuple(
            ReviewArtifactTransition(
                role=item.role,
                path=item.path,
                maximum_bytes=item.maximum_bytes,
                expected_raw=item.next_raw,
                next_raw=item.expected_raw,
            )
            for item in ancestry_plan.artifacts
        ),
    )
    orphan_attached_raw = _control_bytes(orphan_attached)
    expect_rejection(
        lambda: _pending_control(
            ancestry_repo,
            ancestry_plan,
            current_control_raw=orphan_attached_raw,
            current_control=orphan_attached,
        ),
        "non-descendant private high-water source cut",
    )

    sibling_repo, sibling_plan = workspace("transaction-sibling-pending")
    sibling_raw, _ = _pending_control(
        sibling_repo,
        sibling_plan,
        current_control_raw=None,
        current_control=None,
    )
    _atomic_write(
        _git_private_path(sibling_repo, REVIEW_CONTROL_FILE),
        sibling_raw,
        create_only=True,
        create_mode=0o600,
    )
    sibling_conflict = ReviewPersistencePlan(
        action=sibling_plan.action,
        source_cut=copy.deepcopy(sibling_plan.source_cut),
        transition_subject_sha256="e" * 64,
        review_receipt_sha256=sibling_plan.review_receipt_sha256,
        reviewed_assignment_sha256=sibling_plan.reviewed_assignment_sha256,
        artifacts=sibling_plan.artifacts,
        write_order=sibling_plan.write_order,
        expected_state=sibling_plan.expected_state,
        next_state=sibling_plan.next_state,
    )
    expect_rejection(
        lambda: apply_review_persistence_plan(sibling_repo, sibling_conflict),
        "different sibling transition over one pending journal",
    )
    _require(
        all(
            read_bounded_regular_file(
                item.path,
                maximum_bytes=item.maximum_bytes,
                label=f"sibling conflict artifact {item.role}",
            )
            == item.expected_raw
            for item in sibling_plan.artifacts
        ),
        "sibling pending conflict changed a tracked artifact",
    )

    race_repo, race_plan = workspace("transaction-sibling-process-race")
    race_conflict = ReviewPersistencePlan(
        action=race_plan.action,
        source_cut=copy.deepcopy(race_plan.source_cut),
        transition_subject_sha256="e" * 64,
        review_receipt_sha256=race_plan.review_receipt_sha256,
        reviewed_assignment_sha256=race_plan.reviewed_assignment_sha256,
        artifacts=race_plan.artifacts,
        write_order=race_plan.write_order,
        expected_state=race_plan.expected_state,
        next_state=race_plan.next_state,
    )
    read_barrier, write_barrier = os.pipe()
    race_children: list[int] = []
    for candidate_plan in (race_plan, race_conflict):
        child = os.fork()
        if child == 0:
            os.close(write_barrier)
            try:
                token = os.read(read_barrier, 1)
                if token != b"x":
                    os._exit(22)
                apply_review_persistence_plan(race_repo, candidate_plan)
            except (
                OSError,
                SelectorAllocationReviewError,
                SelectorClosureCodecError,
                SelectorClosureGenerationError,
            ):
                os._exit(10)
            os._exit(0)
        race_children.append(child)
    os.close(read_barrier)
    os.write(write_barrier, b"xx")
    os.close(write_barrier)
    race_statuses: list[int] = []
    for child in race_children:
        _, status = os.waitpid(child, 0)
        _require(os.WIFEXITED(status), "sibling race child did not exit normally")
        race_statuses.append(os.WEXITSTATUS(status))
    _require(
        sorted(race_statuses) == [0, 10],
        "fixed review lock did not select exactly one sibling transition winner",
    )
    race_control = _read_optional_control(
        _git_private_path(race_repo, REVIEW_CONTROL_FILE)
    )
    _require(
        race_control is not None
        and race_control[1]["status"] == "ATTACHED"
        and all(
            read_bounded_regular_file(
                item.path,
                maximum_bytes=item.maximum_bytes,
                label=f"sibling race artifact {item.role}",
            )
            == item.next_raw
            for item in race_plan.artifacts
        ),
        "sibling process race did not converge to one exact attached successor",
    )
    rolled_back_artifact = next(
        item for item in race_plan.artifacts if item.role == "semantic_compact_source"
    )
    _atomic_write(rolled_back_artifact.path, rolled_back_artifact.expected_raw)
    expect_rejection(
        lambda: recover_pending_review_transition(race_repo),
        "attached control with a rolled-back tracked artifact",
    )
    _atomic_write(rolled_back_artifact.path, rolled_back_artifact.next_raw)
    _require(
        recover_pending_review_transition(race_repo) == race_control[1],
        "restored attached control did not verify all four tracked artifacts",
    )

    for action, order in (
        ("PROMOTE_TO_REVIEWED", PROMOTION_WRITE_ORDER),
        ("REOPEN_TO_NOT_REVIEWED", REOPEN_WRITE_ORDER),
    ):
        accepted = 0
        rejected = 0
        for bits in range(16):
            states = {
                role: ("NEXT" if bits & (1 << index) else "EXPECTED")
                for index, role in enumerate(REVIEW_ARTIFACT_ROLES)
            }
            pending = {"action": action, "write_order": list(order)}
            try:
                _require_legal_prefix(pending, states)
            except SelectorClosureGenerationError:
                rejected += 1
            else:
                accepted += 1
        _require(
            (accepted, rejected) == (5, 11),
            f"{action} legal-prefix partition differs from 5/11",
        )


def _run_semantic_validation_mode_self_test() -> None:
    """Prove normal generation is strict and candidate mode is allocation-only."""

    import check_selector_closure as checker

    original_validator = checker.validate_expanded_source
    calls: list[dict[str, Any]] = []

    def record_mode(_: dict[str, Any], **kwargs: Any) -> None:
        snapshot_sink = kwargs.pop("adr_snapshot_sink", None)
        _require(
            callable(snapshot_sink),
            "generator semantic validation omitted the ADR snapshot sink",
        )
        snapshot_sink(
            {
                Path(path): b"self-test ADR source snapshot\n"
                for path in (
                    *ADR_ALLOCATION_PATHS,
                    *(
                        module_path
                        for module_paths in ADR_ALLOCATION_MODULE_PATHS
                        for module_path in module_paths
                    ),
                )
            }
        )
        calls.append(kwargs)

    checker.validate_expanded_source = record_mode
    try:
        _validate_generated_semantics({})
        _validate_generated_semantics(
            {},
            allow_incomplete_allocation=True,
        )
    finally:
        checker.validate_expanded_source = original_validator
    _require(
        calls
        == [
            {
                "allow_incomplete_allocation": False,
                "require_complete_allocation": True,
            },
            {
                "allow_incomplete_allocation": True,
                "require_complete_allocation": True,
            },
        ],
        "generator semantic modes differ from strict/only-allocation policy",
    )
    try:
        original_validator(
            {},
            allow_incomplete_allocation=True,
            allow_known_incomplete=True,
        )
    except checker.ClosureCheckError:
        pass
    else:
        _fail("checker accepted simultaneous allocation-only and broad exceptions")


def _run_authoring_schema_bound_self_test(
    directory: Path,
    *,
    schema: dict[str, Any],
    schema_raw: bytes,
) -> None:
    """Prove the named authoring-schema reader accepts its bound and rejects +1."""

    directory = directory.resolve(strict=True)
    unpadded = schema_raw.rstrip(b" \t\r\n")
    _require(
        len(unpadded) <= MAX_AUTHORING_SCHEMA_BYTES,
        "authoring schema self-test source exceeds its named input bound",
    )
    exact_path = directory / "authoring-schema-exact-bound.json"
    exact_raw = unpadded + b" " * (MAX_AUTHORING_SCHEMA_BYTES - len(unpadded))
    _require(
        len(exact_raw) == MAX_AUTHORING_SCHEMA_BYTES,
        "authoring schema exact-bound fixture has an unexpected length",
    )
    _atomic_write(exact_path, exact_raw)
    exact_snapshot = read_bounded_regular_file(
        exact_path,
        maximum_bytes=MAX_AUTHORING_SCHEMA_BYTES,
        label="authoring schema exact-bound fixture",
    )
    _require(
        parse_json_bytes(
            exact_snapshot,
            label="authoring schema exact-bound fixture",
            maximum_bytes=MAX_AUTHORING_SCHEMA_BYTES,
        )
        == schema,
        "authoring schema bounded reader changed the exact-bound document",
    )
    try:
        load_authoring_schema(exact_path)
    except SelectorClosureGenerationError:
        pass
    else:
        _fail("authoring schema identity accepted padded exact-bound bytes")
    _atomic_write(exact_path, exact_raw + b" ")
    try:
        read_bounded_regular_file(
            exact_path,
            maximum_bytes=MAX_AUTHORING_SCHEMA_BYTES,
            label="authoring schema over-bound fixture",
        )
    except SelectorClosureCodecError:
        pass
    else:
        _fail("authoring schema reader accepted its byte bound plus one")


def _run_exact_migration_classifier_self_test() -> None:
    """Exhaust the frozen pair state machine, including a hostile third state."""

    predecessor_authoring = b"exact predecessor authoring\n"
    predecessor_inventory = b"exact predecessor inventory\n"
    successor_authoring = b"exact successor authoring\n"
    successor_inventory = b"exact successor inventory\n"
    hostile_authoring = b"valid but different authoring fixed point\n"
    hostile_inventory = b"valid but different inventory fixed point\n"

    def commitment(raw: bytes) -> ExactMigrationArtifactCommitment:
        return ExactMigrationArtifactCommitment(
            byte_length=len(raw),
            sha256=sha256(raw).hexdigest(),
        )

    predecessor = ExactMigrationCut(
        authoring=commitment(predecessor_authoring),
        inventory=commitment(predecessor_inventory),
    )
    successor = ExactMigrationCut(
        authoring=commitment(successor_authoring),
        inventory=commitment(successor_inventory),
    )
    expected = {
        (predecessor_authoring, predecessor_inventory): "EXACT_PREDECESSOR",
        (successor_authoring, predecessor_inventory): "AUTHORING_FIRST_RECOVERY",
        (successor_authoring, successor_inventory): "EXACT_COMPLETED_REPLAY",
    }
    accepted = 0
    rejected = 0
    for authoring_raw in (
        predecessor_authoring,
        successor_authoring,
        hostile_authoring,
    ):
        for inventory_raw in (
            predecessor_inventory,
            successor_inventory,
            hostile_inventory,
        ):
            pair = (authoring_raw, inventory_raw)
            if pair in expected:
                _require(
                    _classify_exact_incomplete_migration_pair(
                        authoring_raw=authoring_raw,
                        inventory_raw=inventory_raw,
                        predecessor=predecessor,
                        successor=successor,
                    )
                    == expected[pair],
                    "migration classifier changed an exact admitted state",
                )
                accepted += 1
                continue
            try:
                _classify_exact_incomplete_migration_pair(
                    authoring_raw=authoring_raw,
                    inventory_raw=inventory_raw,
                    predecessor=predecessor,
                    successor=successor,
                )
            except SelectorClosureGenerationError:
                rejected += 1
            else:
                _fail("migration classifier accepted a non-KAT artifact pair")
    _require(
        (accepted, rejected) == (3, 6),
        "migration classifier partition differs from exact 3/6",
    )


def _run_review_control_lease_self_test(directory: Path) -> None:
    """Reject copied, stale, path-only, and fork-inherited lock authority."""

    from selector_allocation_review import _run_git

    try:
        _require_maintained_mutation_lease((DEFAULT_AUTHORING,), None)
    except SelectorClosureGenerationError:
        pass
    else:
        _fail("maintained mutation accepted an absent review-control lease")

    repo = directory / "review-control-lease"
    repo.mkdir()
    _run_git(repo, "init", "-b", "main", maximum_output_bytes=4096)
    stale_lease: ReviewControlLease | None = None
    with _review_control_lock(repo) as lease:
        control_path = _require_active_review_control_lease(repo, lease)
        _require(
            control_path == _git_private_path(repo, REVIEW_CONTROL_FILE),
            "active review-control lease resolved the wrong control path",
        )
        forged = ReviewControlLease(
            repo_root=lease.repo_root,
            control_path=lease.control_path,
            lock_path=lease.lock_path,
            lock_descriptor=lease.lock_descriptor,
            lock_identity=lease.lock_identity,
            owner_pid=lease.owner_pid,
            nonce=object(),
        )
        for candidate, label in (
            (forged, "copied"),
            (control_path, "path-only"),
        ):
            try:
                _require_active_review_control_lease(repo, candidate)
            except SelectorClosureGenerationError:
                pass
            else:
                _fail(f"review-control lease self-test accepted {label} authority")
        child = os.fork()
        if child == 0:
            try:
                _require_active_review_control_lease(repo, lease)
            except SelectorClosureGenerationError:
                os._exit(0)
            os._exit(1)
        _, status = os.waitpid(child, 0)
        _require(
            os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0,
            "review-control lease survived a process boundary",
        )
        stale_lease = lease
    try:
        _require_active_review_control_lease(repo, stale_lease)
    except SelectorClosureGenerationError:
        pass
    else:
        _fail("review-control lease remained active after unlock")


def _run_exact_combined_migration_kat(directory: Path) -> None:
    """Exercise the production one-use migration across either maintained cut."""

    from selector_allocation_review import _run_git

    predecessor_cut, successor_cut = _exact_combined_migration_cuts()
    authoring_relative = _review_role_path("semantic_authoring_source")
    schema_relative = _review_role_path("semantic_authoring_schema")
    inventory_relative = _review_role_path("allocation_inventory")
    allocation_schema_relative = _review_role_path("allocation_schema")
    copied_roles = (
        "semantic_authoring_source",
        "semantic_authoring_schema",
        "allocation_inventory",
        "allocation_schema",
        "review_generation_state",
        "review_generation_state_schema",
    )
    source_paths = tuple(
        dict.fromkeys(
            (
                *ADR_ALLOCATION_PATHS,
                *(
                    module_path
                    for module_paths in ADR_ALLOCATION_MODULE_PATHS
                    for module_path in module_paths
                ),
            )
        )
    )
    maintained_authoring_raw = read_bounded_regular_file(
        ROOT / authoring_relative,
        maximum_bytes=_review_role_limit("semantic_authoring_source"),
        label="combined migration KAT maintained authoring",
    )
    maintained_inventory_raw = read_bounded_regular_file(
        ROOT / inventory_relative,
        maximum_bytes=_review_role_limit("allocation_inventory"),
        label="combined migration KAT maintained inventory",
    )
    maintained_schema_raw = read_bounded_regular_file(
        ROOT / schema_relative,
        maximum_bytes=_review_role_limit("semantic_authoring_schema"),
        label="combined migration KAT maintained authoring schema",
    )
    maintained_pair = _classify_exact_incomplete_migration_pair(
        authoring_raw=maintained_authoring_raw,
        inventory_raw=maintained_inventory_raw,
        predecessor=predecessor_cut,
        successor=successor_cut,
    )
    _require(
        maintained_pair in {"EXACT_PREDECESSOR", "EXACT_COMPLETED_REPLAY"}
        and len(maintained_schema_raw)
        == EXACT_COMBINED_MIGRATION_AUTHORING_SCHEMA_BYTE_LENGTH
        and sha256(maintained_schema_raw).hexdigest()
        == EXACT_COMBINED_MIGRATION_AUTHORING_SCHEMA_SHA256,
        (
            "combined migration KAT maintained pair is partial, unknown, or "
            "bound to a different schema"
        ),
    )
    if maintained_pair == "EXACT_PREDECESSOR":
        predecessor_authoring_raw = maintained_authoring_raw
        predecessor_inventory_raw = maintained_inventory_raw
    else:
        predecessor_authoring_raw, predecessor_inventory_raw = (
            _reconstruct_exact_combined_migration_predecessor(
                successor_authoring_raw=maintained_authoring_raw,
                successor_inventory_raw=maintained_inventory_raw,
            )
        )

    def prepare_workspace(name: str) -> tuple[Path, Path, Path, Path]:
        source_root = directory / name
        source_root.mkdir()
        for role in copied_roles:
            relative = _review_role_path(role)
            target = source_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if role == "semantic_authoring_source":
                raw = predecessor_authoring_raw
            elif role == "allocation_inventory":
                raw = predecessor_inventory_raw
            else:
                raw = read_bounded_regular_file(
                    ROOT / relative,
                    maximum_bytes=_review_role_limit(role),
                    label=f"combined migration KAT source {role}",
                )
            _atomic_write(target, raw)
        for relative in source_paths:
            target = source_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            raw = read_bounded_regular_file(
                ROOT / relative,
                maximum_bytes=MAX_ADR_DOCUMENT_BYTES,
                label=f"combined migration KAT ADR source {relative}",
            )
            _atomic_write(target, raw)
        _run_git(source_root, "init", "-b", "main", maximum_output_bytes=4096)
        return (
            source_root,
            source_root / authoring_relative,
            source_root / schema_relative,
            source_root / inventory_relative,
        )

    def migrate(
        source_root: Path,
        authoring_path: Path,
        schema_path: Path,
        *,
        phase_hook: Any = None,
    ) -> tuple[int, str, int, str, int, str, int, str, int, str, bool]:
        with _review_control_lock(source_root) as control_lease:
            return refresh_incomplete_authoring(
                authoring_path,
                schema_path,
                source_root=source_root,
                validate_semantics=False,
                migrate_v2_empty_schema_binding=True,
                migrate_observer_bridge_profile_v1_to_v2=True,
                _phase_hook=phase_hook,
                _review_control_lease=control_lease,
            )

    source_root, authoring_path, schema_path, inventory_path = prepare_workspace(
        "exact-combined-migration-success"
    )
    *_, changed = migrate(source_root, authoring_path, schema_path)
    successor_authoring_raw = read_bounded_regular_file(
        authoring_path,
        maximum_bytes=_review_role_limit("semantic_authoring_source"),
        label="combined migration KAT successor authoring",
    )
    successor_inventory_raw = read_bounded_regular_file(
        inventory_path,
        maximum_bytes=_review_role_limit("allocation_inventory"),
        label="combined migration KAT successor inventory",
    )
    _require(
        changed
        and successor_cut.authoring.matches(successor_authoring_raw)
        and successor_cut.inventory.matches(successor_inventory_raw),
        "combined migration KAT did not install its exact maintained successor",
    )
    reconstructed_authoring_raw, reconstructed_inventory_raw = (
        _reconstruct_exact_combined_migration_predecessor(
            successor_authoring_raw=successor_authoring_raw,
            successor_inventory_raw=successor_inventory_raw,
        )
    )
    _require(
        reconstructed_authoring_raw == predecessor_authoring_raw
        and reconstructed_inventory_raw == predecessor_inventory_raw,
        "combined migration KAT inverse did not recover its exact input pair",
    )
    hostile_successor_inventory = bytearray(successor_inventory_raw)
    hostile_successor_inventory[-2] ^= 1
    try:
        _reconstruct_exact_combined_migration_predecessor(
            successor_authoring_raw=successor_authoring_raw,
            successor_inventory_raw=bytes(hostile_successor_inventory),
        )
    except SelectorClosureGenerationError:
        pass
    else:
        _fail("combined migration inverse accepted a changed successor pair")
    *_, replay_changed = migrate(source_root, authoring_path, schema_path)
    _require(
        not replay_changed
        and authoring_path.read_bytes() == successor_authoring_raw
        and inventory_path.read_bytes() == successor_inventory_raw,
        "combined migration KAT exact replay changed successor bytes",
    )

    class SimulatedMigrationCrashError(RuntimeError):
        pass

    crash_root, crash_authoring, crash_schema, crash_inventory = prepare_workspace(
        "exact-combined-migration-crash"
    )

    def crash_after_authoring(phase: str) -> None:
        if phase == "authoring-installed":
            raise SimulatedMigrationCrashError

    try:
        migrate(
            crash_root,
            crash_authoring,
            crash_schema,
            phase_hook=crash_after_authoring,
        )
    except SimulatedMigrationCrashError:
        pass
    else:
        _fail("combined migration KAT did not stop after authoring install")
    _require(
        crash_authoring.read_bytes() == successor_authoring_raw
        and crash_inventory.read_bytes() == predecessor_inventory_raw,
        "combined migration KAT crash did not leave the exact recovery prefix",
    )
    *_, recovered_changed = migrate(crash_root, crash_authoring, crash_schema)
    _require(
        recovered_changed
        and crash_authoring.read_bytes() == successor_authoring_raw
        and crash_inventory.read_bytes() == successor_inventory_raw,
        "combined migration KAT did not recover its exact authoring-first prefix",
    )

    hybrid_root, hybrid_authoring, hybrid_schema, hybrid_inventory = prepare_workspace(
        "exact-combined-migration-hybrid-rejection"
    )
    allocation_schema_raw = read_bounded_regular_file(
        hybrid_root / allocation_schema_relative,
        maximum_bytes=_review_role_limit("allocation_schema"),
        label="combined migration KAT allocation schema",
    )
    hybrid_value = parse_json_bytes(
        predecessor_authoring_raw,
        label="combined migration KAT predecessor authoring",
        maximum_bytes=MAX_EXPANDED_BYTES,
    )
    hybrid_value[ALLOCATION_BINDING_KEY] = build_inventory_binding(
        successor_inventory_raw,
        allocation_schema_raw,
    )
    hybrid_authoring_raw = _authoring_bytes(hybrid_value)
    _atomic_write(hybrid_authoring, hybrid_authoring_raw)
    _atomic_write(hybrid_inventory, successor_inventory_raw)
    try:
        migrate(hybrid_root, hybrid_authoring, hybrid_schema)
    except SelectorClosureGenerationError:
        pass
    else:
        _fail("combined migration KAT accepted a predecessor/successor hybrid")
    _require(
        hybrid_authoring.read_bytes() == hybrid_authoring_raw
        and hybrid_inventory.read_bytes() == successor_inventory_raw,
        "rejected combined migration hybrid changed maintained bytes",
    )

    schema_root, schema_authoring, hostile_schema_path, schema_inventory = (
        prepare_workspace("exact-combined-migration-schema-rejection")
    )
    hostile_schema = parse_json_bytes(
        maintained_schema_raw,
        label="combined migration KAT authoring schema",
        maximum_bytes=MAX_AUTHORING_SCHEMA_BYTES,
    )
    hostile_schema["description"] = "HOSTILE SCHEMA ANNOTATION NOT IN MAINTAINED CUT"
    hostile_schema_raw = canonical_bytes(hostile_schema) + b"\n"
    _atomic_write(hostile_schema_path, hostile_schema_raw)
    try:
        migrate(schema_root, schema_authoring, hostile_schema_path)
    except SelectorClosureGenerationError:
        pass
    else:
        _fail("combined migration KAT accepted a substituted authoring schema")
    _require(
        schema_authoring.read_bytes() == predecessor_authoring_raw
        and schema_inventory.read_bytes() == predecessor_inventory_raw,
        "rejected combined migration schema substitution changed maintained bytes",
    )


def run_self_test(schema_path: Path) -> None:
    run_codec_self_test()
    _run_semantic_validation_mode_self_test()
    _run_exact_migration_classifier_self_test()
    schema_raw = read_bounded_regular_file(
        schema_path,
        maximum_bytes=MAX_AUTHORING_SCHEMA_BYTES,
        label="selector authoring schema self-test snapshot",
    )
    schema = load_authoring_schema(schema_path)
    _require(
        parse_json_bytes(schema_raw, label="authoring schema self-test snapshot")
        == schema,
        "authoring schema changed while the self-test snapshot was loaded",
    )
    observer_read_capture_bridge_profile = _authoring_schema_bridge_profile(
        schema,
        expected_schema=BRIDGE_V2_MIGRATION_PROFILE_SCHEMA,
    )
    _run_exact_adversarial_probe_binding_repin_self_test(schema)
    allocation_schema_raw, allocation_schema = load_inventory_schema(
        schema_path.with_name(INVENTORY_SCHEMA_FILE)
    )
    compact_schema_raw, _ = load_compact_schema(
        schema_path.with_name(CANONICAL_SOURCE_SCHEMA_FILE)
    )
    with tempfile.TemporaryDirectory(
        prefix="ncp-selector-source-self-test-"
    ) as directory_name:
        directory = Path(directory_name).resolve(strict=True)
        _run_authoring_schema_bound_self_test(
            directory,
            schema=schema,
            schema_raw=schema_raw,
        )
        _run_review_control_lease_self_test(directory)
        _run_incomplete_refresh_self_test(
            directory,
            allocation_schema=allocation_schema,
            allocation_schema_raw=allocation_schema_raw,
            observer_read_capture_bridge_profile=(observer_read_capture_bridge_profile),
            schema_path=schema_path,
        )
        _run_exact_combined_migration_kat(directory)
        _run_review_transaction_self_test(directory)
        authoring_path = directory / "authoring.json"
        allocation_path = directory / INVENTORY_FILE
        allocation_schema_copy = directory / INVENTORY_SCHEMA_FILE
        output_path = directory / "compact.json"
        compact_schema_copy = directory / CANONICAL_SOURCE_SCHEMA_FILE
        _atomic_write(allocation_schema_copy, allocation_schema_raw)
        _atomic_write(compact_schema_copy, compact_schema_raw)
        load_compact_schema(compact_schema_copy)
        _atomic_write(compact_schema_copy, compact_schema_raw + b" ")
        try:
            load_compact_schema(compact_schema_copy)
        except SelectorClosureGenerationError:
            pass
        else:
            _fail("compact schema binding accepted changed bytes")
        sample = _sample_expanded_source(
            allocation_schema_raw,
            observer_read_capture_bridge_profile=(observer_read_capture_bridge_profile),
        )
        _recompute_closure_commitments(sample)
        _require_review_candidate_boundary(sample)
        for label, mutation in (
            (
                "complete allocation status",
                lambda value: value[ALLOCATION_ORACLE_KEY].__setitem__(
                    "status", "COMPLETE"
                ),
            ),
            (
                "reviewed provenance status",
                lambda value: value[ALLOCATION_ORACLE_KEY][
                    "provenance_review"
                ].__setitem__("status", "REVIEWED"),
            ),
            (
                "nonzero reviewed assignment",
                lambda value: value[ALLOCATION_ORACLE_KEY][
                    "provenance_review"
                ].__setitem__("reviewed_assignment_sha256", "f" * 64),
            ),
            (
                "unknown provenance status",
                lambda value: value[ALLOCATION_ORACLE_KEY][
                    "provenance_review"
                ].__setitem__("status", "UNKNOWN"),
            ),
        ):
            hostile_candidate = copy.deepcopy(sample)
            mutation(hostile_candidate)
            try:
                _require_review_candidate_boundary(hostile_candidate)
            except SelectorClosureGenerationError:
                pass
            else:
                _fail(f"review-candidate mode accepted {label}")
        allocation_inventory = oracle_to_inventory(sample[ALLOCATION_ORACLE_KEY])
        validate_allocation_inventory(
            allocation_inventory,
            allocation_schema,
        )
        allocation_raw = inventory_bytes(allocation_inventory)
        allocation_binding = build_inventory_binding(
            allocation_raw,
            allocation_schema_raw,
        )
        _atomic_write(allocation_path, allocation_raw)
        authoring = prepare_authoring_source(sample, allocation_binding)
        _validate_schema_instance(authoring, schema)
        _atomic_write(authoring_path, _authoring_bytes(authoring))
        mismatched_oracle = copy.deepcopy(sample[ALLOCATION_ORACLE_KEY])
        mismatched_oracle["status"] = "COMPLETE"
        try:
            prepare_canonical_source(authoring, mismatched_oracle)
        except SelectorClosureGenerationError:
            pass
        else:
            _fail(
                "generator accepted an allocation oracle that did not "
                "match the authoring binding"
            )

        expected, _, snapshot = generate_compact_bytes(
            authoring_path,
            schema_path,
            validate_semantics=False,
        )
        _verify_generation_inputs_unchanged(
            authoring_path,
            schema_path,
            snapshot,
        )
        _atomic_write(authoring_path, snapshot.authoring_raw + b" ")
        try:
            _verify_generation_inputs_unchanged(
                authoring_path,
                schema_path,
                snapshot,
            )
        except SelectorClosureGenerationError:
            pass
        else:
            _fail("generation accepted an authoring source changed after validation")
        _atomic_write(authoring_path, snapshot.authoring_raw)
        _atomic_write(
            allocation_path,
            snapshot.allocation.inventory_raw + b" ",
        )
        try:
            _verify_generation_inputs_unchanged(
                authoring_path,
                schema_path,
                snapshot,
            )
        except SelectorAllocationInventoryError:
            pass
        else:
            _fail(
                "generation accepted an allocation inventory changed after validation"
            )
        _atomic_write(allocation_path, snapshot.allocation.inventory_raw)
        semantic_path = directory / "semantic-source.md"
        semantic_raw = b"semantic source snapshot\n"
        _atomic_write(semantic_path, semantic_raw)
        semantic_snapshot = GenerationInputSnapshot(
            allocation=snapshot.allocation,
            adr_sources=((semantic_path, semantic_raw),),
            authoring_raw=snapshot.authoring_raw,
            compact_schema_raw=snapshot.compact_schema_raw,
            schema_raw=snapshot.schema_raw,
        )
        _verify_generation_inputs_unchanged(
            authoring_path,
            schema_path,
            semantic_snapshot,
        )
        _atomic_write(semantic_path, semantic_raw + b"changed\n")
        try:
            _verify_generation_inputs_unchanged(
                authoring_path,
                schema_path,
                semantic_snapshot,
            )
        except SelectorClosureGenerationError:
            pass
        else:
            _fail("generation accepted an ADR source changed after validation")
        _atomic_write(semantic_path, semantic_raw)
        try:
            _require_semantic_output_path_distinct(ROOT / ADR_ALLOCATION_PATHS[0])
        except SelectorClosureGenerationError:
            pass
        else:
            _fail("generation accepted a compact output that aliases an ADR input")
        _write_and_verify_compact(output_path, expected)
        before_stat = output_path.stat()
        before_identity = (
            before_stat.st_dev,
            before_stat.st_ino,
            before_stat.st_mode,
            before_stat.st_size,
            before_stat.st_mtime_ns,
            before_stat.st_ctime_ns,
        )
        before_entries = sorted(path.name for path in directory.iterdir())
        _check_output(output_path, expected)
        after_stat = output_path.stat()
        after_identity = (
            after_stat.st_dev,
            after_stat.st_ino,
            after_stat.st_mode,
            after_stat.st_size,
            after_stat.st_mtime_ns,
            after_stat.st_ctime_ns,
        )
        _require(
            before_identity == after_identity,
            "--check mutated the generated output",
        )
        _require(
            before_entries == sorted(path.name for path in directory.iterdir()),
            "--check created or removed a file",
        )

        schema_substitution_output = directory / "schema-substitution-authoring.json"
        substituted_allocation_schema = copy.deepcopy(allocation_schema)
        substituted_allocation_schema["description"] += " Substituted bytes."
        _atomic_write(
            allocation_schema_copy,
            canonical_bytes(substituted_allocation_schema) + b"\n",
        )
        try:
            materialize_authoring(
                output_path,
                schema_substitution_output,
                schema_path,
                validate_semantics=False,
            )
        except SelectorAllocationInventoryError:
            pass
        else:
            _fail(
                "compact materialization laundered allocation provenance "
                "through a same-ID schema substitution"
            )
        _require(
            not schema_substitution_output.exists(),
            "failed schema-substitution materialization created authoring output",
        )
        _atomic_write(allocation_schema_copy, allocation_schema_raw)

        recovered_path = directory / "recovered-authoring.json"
        materialize_authoring(
            output_path,
            recovered_path,
            schema_path,
            validate_semantics=False,
        )
        recovered, _, _ = generate_compact_bytes(
            recovered_path,
            schema_path,
            validate_semantics=False,
        )
        _require(
            recovered == expected,
            "compact materialization round trip changed source bytes",
        )
        recovered_stat = recovered_path.stat()
        materialize_authoring(
            output_path,
            recovered_path,
            schema_path,
            validate_semantics=False,
        )
        _require(
            recovered_path.stat().st_mtime_ns == recovered_stat.st_mtime_ns,
            "idempotent materialization rewrote the authoring source",
        )
        different_authoring = copy.deepcopy(authoring)
        different_authoring["generated_view"] = "different"
        _atomic_write(
            recovered_path,
            _authoring_bytes(different_authoring),
        )
        different_stat = recovered_path.stat()
        try:
            materialize_authoring(
                output_path,
                recovered_path,
                schema_path,
                validate_semantics=False,
            )
        except SelectorClosureGenerationError:
            pass
        else:
            _fail("materialization overwrote a different authoring source")
        _require(
            recovered_path.stat().st_mtime_ns == different_stat.st_mtime_ns
            and read_bounded_regular_file(
                recovered_path,
                maximum_bytes=MAX_EXPANDED_BYTES,
                label="self-test recovered authoring source",
            )
            == _authoring_bytes(different_authoring),
            "failed materialization mutated a different authoring source",
        )

        stale = expected + b" "
        _atomic_write(output_path, stale)
        stale_stat = output_path.stat()
        try:
            _check_output(output_path, expected)
        except SelectorClosureGenerationError:
            pass
        else:
            _fail("--check accepted stale output")
        _require(
            read_bounded_regular_file(
                output_path,
                maximum_bytes=MAX_COMPACT_BYTES - 1,
                label="self-test stale compact output",
            )
            == stale,
            "--check rewrote stale output",
        )
        _require(
            output_path.stat().st_mtime_ns == stale_stat.st_mtime_ns,
            "--check changed stale output metadata",
        )

        try:
            _require_distinct_paths(
                authoring_path,
                authoring_path,
                labels=("input", "output"),
            )
        except SelectorClosureGenerationError:
            pass
        else:
            _fail("input/output identity guard accepted one path")

        hardlink_path = directory / "authoring-hardlink.json"
        os.link(authoring_path, hardlink_path)
        try:
            _require_distinct_paths(
                authoring_path,
                hardlink_path,
                labels=("input", "output"),
            )
        except SelectorClosureGenerationError:
            pass
        else:
            _fail("input/output identity guard accepted a hard link")

        oversized_path = directory / "oversized.json"
        _atomic_write(oversized_path, b"xx")
        try:
            read_bounded_regular_file(
                oversized_path,
                maximum_bytes=1,
                label="self-test oversized input",
            )
        except SelectorClosureCodecError:
            pass
        else:
            _fail("bounded reader accepted an oversized input")

        symlink_path = directory / "authoring-symlink.json"
        symlink_path.symlink_to(authoring_path)
        try:
            read_bounded_regular_file(
                symlink_path,
                maximum_bytes=MAX_EXPANDED_BYTES,
                label="self-test symlink input",
            )
        except SelectorClosureCodecError:
            pass
        else:
            _fail("bounded reader accepted a symlink")

        try:
            read_bounded_regular_file(
                directory,
                maximum_bytes=MAX_EXPANDED_BYTES,
                label="self-test nonregular input",
            )
        except SelectorClosureCodecError:
            pass
        else:
            _fail("bounded reader accepted a nonregular file")

        swap_path = directory / "swap-race.json"
        swap_target = directory / "swap-target.json"
        _atomic_write(swap_path, b'{"source":"original"}\n')
        _atomic_write(swap_target, b'{"source":"symlink-target"}\n')
        swapped = False

        def swap_before_open(phase: str) -> None:
            nonlocal swapped
            if phase == "parent-opened" and not swapped:
                swapped = True
                swap_path.unlink()
                swap_path.symlink_to(swap_target)

        try:
            _read_bounded_regular_file(
                swap_path,
                maximum_bytes=MAX_EXPANDED_BYTES,
                label="self-test symlink swap input",
                phase_hook=swap_before_open,
            )
        except SelectorClosureCodecError:
            pass
        else:
            _fail("bounded reader followed a symlink swapped before open")
        _require(swapped, "symlink-swap self-test hook did not run")

        hostile_source = copy.deepcopy(sample)
        hostile_source["hostile_reserved_literal"] = "@S0000"
        _recompute_closure_commitments(hostile_source)
        hostile = prepare_authoring_source(
            hostile_source,
            allocation_binding,
        )
        try:
            serialize_compact_source(
                prepare_canonical_source(
                    hostile,
                    inventory_to_oracle(allocation_inventory),
                )
            )
        except SelectorClosureCodecError:
            pass
        else:
            _fail("codec accepted a reserved token literal")

        stale_commitment = copy.deepcopy(authoring)
        stale_commitment["generated_view"] = "stale-commitment"
        try:
            prepare_canonical_source(
                stale_commitment,
                inventory_to_oracle(allocation_inventory),
            )
        except SelectorClosureGenerationError:
            pass
        else:
            _fail("generator silently repaired a stale maintained commitment")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--authoring",
        type=Path,
        default=DEFAULT_AUTHORING,
        help="expanded authoring source",
    )
    parser.add_argument(
        "--authoring-schema",
        type=Path,
        default=DEFAULT_AUTHORING_SCHEMA,
        help="authoring preflight schema",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="compact generated source",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail if the compact output is stale; never write",
    )
    parser.add_argument(
        "--review-candidate",
        action="store_true",
        help=(
            "NON-GATING: generate or check only the exact "
            "INCOMPLETE_FAIL_CLOSED/NOT_REVIEWED/zero-digest review candidate "
            "while relaxing allocation coverage only; all architecture "
            "validators remain strict and normal mode continues to require "
            "complete reviewed allocation provenance"
        ),
    )
    parser.add_argument(
        "--materialize-from-compact",
        type=Path,
        metavar="PATH",
        help=(
            "decode one compact source into --authoring and its external "
            "allocation inventory; requires the allocation schema beside "
            "--authoring and never writes --output"
        ),
    )
    parser.add_argument(
        "--refresh-incomplete-authoring",
        action="store_true",
        help=(
            "refresh only an INCOMPLETE_FAIL_CLOSED/NOT_REVIEWED external "
            "inventory, its exact binding, and canonical authoring "
            "commitments; never writes --output"
        ),
    )
    parser.add_argument(
        "--repin-adversarial-probe-bindings",
        action="store_true",
        help=(
            "with --refresh-incomplete-authoring, replace only the exact "
            "byte-bound predecessor adversarial-probe closure with the exact "
            "authoring-schema target; near-miss and unrelated migration cuts "
            "are rejected"
        ),
    )
    parser.add_argument(
        "--migrate-v2-empty-allocation-schema-binding",
        action="store_true",
        help=(
            "with --refresh-incomplete-authoring and the bridge-profile "
            "migration switch, migrate the exact "
            "empty-assignment v2/unreviewed/genesis/no-control/no-compact "
            "predecessor directly to the byte-bound v4 allocation schema; "
            "the switches form one semantic cut and no other compatibility "
            "state is accepted"
        ),
    )
    parser.add_argument(
        "--migrate-observer-read-capture-bridge-profile-v1-to-v2",
        action="store_true",
        help=(
            "with --refresh-incomplete-authoring and the allocation-schema "
            "migration switch, replace the exact "
            "maintained observer read/capture bridge profile v1 with the "
            "authoring schema's exact v2 const; the fail-closed candidate "
            "must remain unreviewed at genesis without transition control "
            "or a generated compact source"
        ),
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run hostile workflow tests without repository writes",
    )
    return parser.parse_args()


def _relative_label(path: Path) -> Path:
    try:
        return path.relative_to(ROOT)
    except ValueError:
        return path


def _execute_main(
    args: argparse.Namespace,
    *,
    review_control_lease: ReviewControlLease | None = None,
) -> int:
    try:
        action_count = sum(
            (
                bool(args.self_test),
                args.materialize_from_compact is not None,
                bool(args.refresh_incomplete_authoring),
            )
        )
        _require(
            action_count <= 1,
            (
                "--self-test, --materialize-from-compact, and "
                "--refresh-incomplete-authoring are mutually exclusive"
            ),
        )
        _require(
            not args.migrate_v2_empty_allocation_schema_binding
            or args.refresh_incomplete_authoring,
            (
                "--migrate-v2-empty-allocation-schema-binding requires "
                "--refresh-incomplete-authoring"
            ),
        )
        _require(
            not args.migrate_observer_read_capture_bridge_profile_v1_to_v2
            or args.refresh_incomplete_authoring,
            (
                "--migrate-observer-read-capture-bridge-profile-v1-to-v2 "
                "requires --refresh-incomplete-authoring"
            ),
        )
        _require(
            not args.repin_adversarial_probe_bindings
            or args.refresh_incomplete_authoring,
            (
                "--repin-adversarial-probe-bindings requires "
                "--refresh-incomplete-authoring"
            ),
        )
        _require(
            args.migrate_v2_empty_allocation_schema_binding
            == args.migrate_observer_read_capture_bridge_profile_v1_to_v2,
            (
                "the two exact migration switches form one semantic cut and "
                "must be supplied together"
            ),
        )
        _require(
            not args.repin_adversarial_probe_bindings
            or not args.migrate_v2_empty_allocation_schema_binding,
            (
                "--repin-adversarial-probe-bindings cannot be combined with "
                "the exact bridge/allocation migration"
            ),
        )
        if args.self_test:
            _require(
                not args.check
                and not args.review_candidate
                and not args.migrate_v2_empty_allocation_schema_binding
                and not (args.migrate_observer_read_capture_bridge_profile_v1_to_v2),
                (
                    "--self-test cannot be combined with --check, "
                    "--review-candidate, or migration"
                ),
            )
            _require(
                not args.repin_adversarial_probe_bindings,
                "--self-test cannot be combined with adversarial probe repin",
            )
            run_self_test(args.authoring_schema)
            print("selector closure source generator self-test: PASS")
            return 0

        if args.refresh_incomplete_authoring:
            _require(
                not args.check and not args.review_candidate,
                (
                    "--refresh-incomplete-authoring cannot be combined with "
                    "--check or --review-candidate"
                ),
            )
            (
                authoring_bytes,
                authoring_digest,
                inventory_bytes_count,
                inventory_digest,
                model_count,
                model_digest,
                subject_byte_length,
                subject_digest,
                shape_count,
                shape_digest,
                changed,
            ) = refresh_incomplete_authoring(
                args.authoring,
                args.authoring_schema,
                migrate_v2_empty_schema_binding=(
                    args.migrate_v2_empty_allocation_schema_binding
                ),
                migrate_observer_bridge_profile_v1_to_v2=(
                    args.migrate_observer_read_capture_bridge_profile_v1_to_v2
                ),
                repin_adversarial_probe_bindings=(
                    args.repin_adversarial_probe_bindings
                ),
                _review_control_lease=review_control_lease,
            )
            if args.migrate_v2_empty_allocation_schema_binding:
                action_label = (
                    "selector closure exact bridge-v1/allocation-v2-empty to "
                    "bridge-v2/allocation-v4 migration: "
                )
            elif args.repin_adversarial_probe_bindings:
                action_label = "selector closure exact adversarial probe repin: "
            else:
                action_label = "selector closure incomplete authoring refresh: "
            print(
                action_label + f"{'refreshed' if changed else 'already current'} "
                f"{_relative_label(args.authoring)} "
                f"authoring_bytes={authoring_bytes} "
                f"authoring_sha256={authoring_digest} "
                f"inventory_bytes={inventory_bytes_count} "
                f"inventory_sha256={inventory_digest} "
                f"model_allocation_count={model_count} "
                f"model_allocation_sha256={model_digest} "
                f"semantic_review_subject_bytes={subject_byte_length} "
                f"semantic_review_subject_sha256={subject_digest} "
                f"semantic_shape_entry_count={shape_count} "
                f"semantic_shape_sha256={shape_digest}"
            )
            return 0

        if args.materialize_from_compact is not None:
            _require(
                not args.check and not args.review_candidate,
                (
                    "--materialize-from-compact cannot be combined with "
                    "--check or --review-candidate"
                ),
            )
            byte_count, digest, created = materialize_authoring(
                args.materialize_from_compact,
                args.authoring,
                args.authoring_schema,
                _review_control_lease=review_control_lease,
            )
            print(
                "selector closure authoring source: "
                f"{'materialized' if created else 'already current'} "
                f"{_relative_label(args.authoring)} "
                f"bytes={byte_count} canonical_sha256={digest}"
            )
            return 0

        _require_distinct_paths(
            args.authoring,
            args.output,
            labels=("authoring input", "compact output"),
        )
        _require_distinct_paths(
            args.authoring,
            args.authoring_schema,
            labels=("authoring input", "authoring schema"),
        )
        _require_distinct_paths(
            args.authoring_schema,
            args.output,
            labels=("authoring schema", "compact output"),
        )
        compact_schema_path = args.authoring_schema.with_name(
            CANONICAL_SOURCE_SCHEMA_FILE
        )
        allocation_inventory_path = args.authoring.with_name(INVENTORY_FILE)
        allocation_schema_path = args.authoring.with_name(INVENTORY_SCHEMA_FILE)
        _require_distinct_paths(
            compact_schema_path,
            args.output,
            labels=("compact schema", "compact output"),
        )
        _require_distinct_paths(
            compact_schema_path,
            args.authoring,
            labels=("compact schema", "authoring input"),
        )
        for left, right, labels in (
            (
                allocation_inventory_path,
                args.output,
                ("allocation inventory", "compact output"),
            ),
            (
                allocation_schema_path,
                args.output,
                ("allocation schema", "compact output"),
            ),
            (
                allocation_inventory_path,
                args.authoring,
                ("allocation inventory", "authoring input"),
            ),
            (
                allocation_schema_path,
                args.authoring,
                ("allocation schema", "authoring input"),
            ),
            (
                allocation_inventory_path,
                allocation_schema_path,
                ("allocation inventory", "allocation schema"),
            ),
        ):
            _require_distinct_paths(left, right, labels=labels)
        _require_semantic_output_path_distinct(args.output)
        expected, envelope, snapshot = generate_compact_bytes(
            args.authoring,
            args.authoring_schema,
            review_candidate=args.review_candidate,
        )
        digest = envelope["encoding"]["expanded_document_sha256"]
        if args.check:
            _check_output(args.output, expected)
            _verify_generation_inputs_unchanged(
                args.authoring,
                args.authoring_schema,
                snapshot,
            )
            _check_output(args.output, expected)
            print(
                (
                    "selector closure source generator: "
                    "NON-GATING REVIEW CANDIDATE PASS "
                    if args.review_candidate
                    else "selector closure source generator: PASS "
                )
                + f"bytes={len(expected)} expanded_sha256={digest}"
            )
            return 0

        _verify_generation_inputs_unchanged(
            args.authoring,
            args.authoring_schema,
            snapshot,
        )
        _write_and_verify_compact(
            args.output,
            expected,
            _review_control_lease=review_control_lease,
        )
        _verify_generation_inputs_unchanged(
            args.authoring,
            args.authoring_schema,
            snapshot,
        )
        _check_output(args.output, expected)
        print(
            (
                "selector closure source generator: "
                "NON-GATING REVIEW CANDIDATE generated "
                if args.review_candidate
                else "selector closure source generator: generated "
            )
            + f"{_relative_label(args.output)} "
            f"bytes={len(expected)} expanded_sha256={digest}"
        )
        return 0
    except AtomicWriteOutcomeUnknownError as error:
        print(
            "selector closure source generator: OUTCOME UNKNOWN: "
            f"{error}; the destination may contain the requested bytes. "
            "Inspect and reconcile by application identity; do not retry "
            "automatically.",
            file=sys.stderr,
        )
        return 2
    except (
        KeyError,
        OSError,
        SelectorAllocationInventoryError,
        SelectorClosureCodecError,
        SelectorClosureGenerationError,
        TypeError,
    ) as error:
        print(f"selector closure source generator: FAIL: {error}", file=sys.stderr)
        return 1


def main() -> int:
    args = parse_args()
    migration_switches_are_coupled = (
        args.migrate_v2_empty_allocation_schema_binding
        == args.migrate_observer_read_capture_bridge_profile_v1_to_v2
    )
    mutates_repository_files = (
        migration_switches_are_coupled
        and not args.self_test
        and not args.check
        and (
            args.materialize_from_compact is not None
            or args.refresh_incomplete_authoring
            or args.output is not None
        )
    )
    context = (
        _review_control_lock(ROOT) if mutates_repository_files else nullcontext(None)
    )
    try:
        with context as control_lease:
            if control_lease is not None:
                control_path = _require_active_review_control_lease(
                    ROOT,
                    control_lease,
                )
                control = _read_optional_control(control_path)
                _require(
                    control is None or control[1]["status"] == "ATTACHED",
                    (
                        "a review transition is pending; recover it before any "
                        "generator mutation"
                    ),
                )
            return _execute_main(args, review_control_lease=control_lease)
    except (
        KeyError,
        OSError,
        SelectorAllocationInventoryError,
        SelectorClosureCodecError,
        SelectorClosureGenerationError,
        TypeError,
    ) as error:
        print(f"selector closure source generator: FAIL: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
