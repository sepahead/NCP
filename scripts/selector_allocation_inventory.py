#!/usr/bin/env python3
"""Load the external, non-normative B01 selector-allocation inventory.

The selector authoring source binds exact inventory and schema bytes.  This
module owns that binding boundary.  It does not decide whether the inventory is
complete.  The selector semantic checker compares the declared rows with the
expanded model and binds each row to one stable ADR Open-questions anchor.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import stat
import sys
import tempfile
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, NoReturn

from selector_closure_codec import (
    SelectorClosureCodecError,
    canonical_bytes,
    parse_json_bytes,
    read_bounded_regular_file,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INVENTORY = ROOT / "docs" / "adr" / "selector-allocation.authoring.v1.json"
DEFAULT_SCHEMA = ROOT / "docs" / "adr" / "selector-allocation.authoring.schema.v1.json"

ALLOCATION_BINDING_KEY = "adr_allocation_inventory_binding"
ALLOCATION_ORACLE_KEY = "adr_allocation_oracle"
INVENTORY_FILE = "selector-allocation.authoring.v1.json"
INVENTORY_SCHEMA_FILE = "selector-allocation.authoring.schema.v1.json"
INVENTORY_SCHEMA_ID = "ncp.b01-selector-allocation-authoring.v1"
INVENTORY_SCHEMA_URL = (
    "https://sepahead.github.io/ncp/schemas/b01-selector-allocation-authoring.v1.json"
)
INVENTORY_SCHEMA_SHA256 = (
    "2f7851cddc366e430c24220a25d3716d0d7d34bc4a80335c7a0b55e2b8fdc802"
)
INVENTORY_CANONICALIZATION = (
    "UTF8_JSON_SORTED_KEYS_NO_INSIGNIFICANT_WHITESPACE_ONE_TRAILING_LF"
)
INVENTORY_CLAIM_BOUNDARY = "NON_NORMATIVE_B01_SEMANTIC_ALLOCATION_PROVENANCE_ONLY"
DOCUMENT_ROW_COMMITMENT_DOMAIN = b"ncp.b01.selector-allocation.document-rows.v1\x00"
DOCUMENT_ROW_COMMITMENT = {
    "allocation_row_fields": [
        "adr_id",
        "exact_name",
        "kind",
        "semantic_ref",
        "source_anchor",
        "unit_id",
    ],
    "algorithm": "SHA256",
    "canonicalization": "UTF8_JSON_SORTED_KEYS_NO_INSIGNIFICANT_WHITESPACE",
    "domain_hex": DOCUMENT_ROW_COMMITMENT_DOMAIN.hex(),
    "exclusion_row_fields": [
        "adr_id",
        "classification",
        "exact_name",
        "reason",
        "source_anchor",
    ],
    "fixed_vectors": {
        "empty_allocations": {
            "expected_sha256": (
                "761748e85c96b94054fe41918f2d8adda17c771563fb6db431a8016531e2bad2"
            ),
            "row_kind": "allocations",
            "rows": [],
        },
        "empty_exclusions": {
            "expected_sha256": (
                "603dda71edd252684ce5e51750df30b801bfec0763a799b8c4e4a3a3afeddd05"
            ),
            "row_kind": "exclusions",
            "rows": [],
        },
        "nonempty_allocation": {
            "expected_canonical_rows_byte_length": 237,
            "expected_canonical_rows_utf8_hex": (
                "5b7b226164725f6964223a224144522d303031222c2265786163745f6e61"
                "6d65223a2253616d706c6554797065222c226b696e64223a225459504522"
                "2c2273656d616e7469635f726566223a2273616d706c652d747970653a3a"
                "53616d706c6554797065222c22736f757263655f616e63686f72223a226e"
                "63702d6230312d73656c6563746f722d616c6c6f636174696f6e2d616472"
                "2d3030312d7631222c22756e69745f6964223a2264653663653839303331"
                "633164303464343737363238396166353832643836323337323938616534"
                "306137363138336362323966666430653533646538636266227d5d"
            ),
            "expected_sha256": (
                "4c4b49955e674d54ab5cafcd5ec5309925513ff55e5b4981ee576a91a49758f7"
            ),
            "row_kind": "allocations",
            "rows": [
                {
                    "adr_id": "ADR-001",
                    "exact_name": "SampleType",
                    "kind": "TYPE",
                    "semantic_ref": "sample-type::SampleType",
                    "source_anchor": "ncp-b01-selector-allocation-adr-001-v1",
                    "unit_id": (
                        "de6ce89031c1d04d4776289af582d86237298ae40a76183cb29"
                        "ffd0e53de8cbf"
                    ),
                }
            ],
        },
        "nonempty_exclusion": {
            "expected_canonical_rows_byte_length": 171,
            "expected_canonical_rows_utf8_hex": (
                "5b7b226164725f6964223a224144522d303031222c22636c617373696669"
                "636174696f6e223a22454e554d5f4f525f4252414e43485f56414c554522"
                "2c2265786163745f6e616d65223a2253616d706c65416c696173222c2272"
                "6561736f6e223a22466978656420766563746f722e222c22736f75726365"
                "5f616e63686f72223a226e63702d6230312d73656c6563746f722d616c6c"
                "6f636174696f6e2d6164722d3030312d7631227d5d"
            ),
            "expected_sha256": (
                "117399630910a085ff8713f4913d98c728d92035ddb652b2a21a3f06501eb957"
            ),
            "row_kind": "exclusions",
            "rows": [
                {
                    "adr_id": "ADR-001",
                    "classification": "ENUM_OR_BRANCH_VALUE",
                    "exact_name": "SampleAlias",
                    "reason": "Fixed vector.",
                    "source_anchor": "ncp-b01-selector-allocation-adr-001-v1",
                }
            ],
        },
        "schema": "ncp.b01-selector-allocation-document-row-fixed-vectors.v1",
    },
    "framing": ("DOMAIN_BYTES_THEN_ASCII_ROW_KIND_THEN_NUL_THEN_CANONICAL_ROWS_BYTES"),
    "output": "LOWERCASE_HEXADECIMAL_64_CHARACTERS",
    "row_kind_encoding": "LOWERCASE_ASCII_EXACT_TOKEN",
    "row_ordering": "PRESERVE_CANONICAL_PROVENANCE_ROW_ORDER",
    "row_kinds": ["allocations", "exclusions"],
    "row_projection": "EXACT_STORED_TOP_LEVEL_ROW_OBJECTS_NO_FIELD_ELISION",
    "row_selection": (
        "FILTER_TOP_LEVEL_ROWS_BY_EXACT_ADR_ID_PRESERVING_TOP_LEVEL_ORDER"
    ),
    "row_shape": "JSON_ARRAY_OF_JSON_OBJECT_ROWS",
}
PROVENANCE_REVIEW_DOMAIN = b"ncp.b01.selector-allocation.provenance-review.v5\x00"
PROVENANCE_REVIEW_CLAIM_BOUNDARY = (
    "EXACT_SEMANTIC_REVIEW_SUBJECT_ADR_AND_ANCHOR_ASSIGNMENT_REVIEW_ONLY_"
    "NOT_PROTOCOL_RELEASE_OR_EXTERNAL_EVIDENCE"
)
PROVENANCE_REVIEW_SUITE = {
    "algorithm": "SHA256",
    "allocation_ordering_fields": [
        "adr_id",
        "source_anchor",
        "kind",
        "exact_name",
        "semantic_ref",
        "unit_id",
    ],
    "canonicalization": "UTF8_JSON_SORTED_KEYS_NO_INSIGNIFICANT_WHITESPACE",
    "claim_boundary": PROVENANCE_REVIEW_CLAIM_BOUNDARY,
    "document_ordering": "LEXICOGRAPHIC_ASCENDING_BY_ADR_ID_ASCII_BYTES",
    "document_source_set_row_fields": [
        "adr_id",
        "allocation_anchor_id",
        "source_set",
    ],
    "document_source_set_row_shape": "JSON_OBJECT",
    "domain_hex": PROVENANCE_REVIEW_DOMAIN.hex(),
    "exclusion_ordering_fields": [
        "adr_id",
        "source_anchor",
        "exact_name",
        "classification",
    ],
    "fixed_vectors": {
        "minimal_assignment": {
            "expected_projection": {
                "allocation_review_profile": {"schema": "sample"},
                "allocations": [],
                "document_source_sets": [
                    {
                        "adr_id": "ADR-001",
                        "allocation_anchor_id": (
                            "ncp-b01-selector-allocation-adr-001-v1"
                        ),
                        "source_set": {"sha256": "0" * 64},
                    }
                ],
                "exclusions": [],
                "semantic_review_subject": {"sha256": "1" * 64},
            },
            "expected_sha256": (
                "8ae4d48b5a67be5e34321ccca0c96118e0e112af6da3fec833d2d816ec16ca28"
            ),
            "input": {
                "allocation_review_profile": {"schema": "sample"},
                "allocations": [],
                "documents": [
                    {
                        "adr_id": "ADR-001",
                        "allocation_anchor_id": (
                            "ncp-b01-selector-allocation-adr-001-v1"
                        ),
                        "source_set": {"sha256": "0" * 64},
                    }
                ],
                "exclusions": [],
                "semantic_review_subject": {"sha256": "1" * 64},
            },
        },
        "schema": "ncp.b01-selector-allocation-provenance-review-fixed-vectors.v1",
    },
    "framing": "DOMAIN_BYTES_THEN_CANONICAL_PROJECTION_BYTES",
    "output": "LOWERCASE_HEXADECIMAL_64_CHARACTERS",
    "projection_fields": [
        "allocation_review_profile",
        "allocations",
        "document_source_sets",
        "exclusions",
        "semantic_review_subject",
    ],
    "projection_shape": "JSON_OBJECT",
    "row_ordering": (
        "LEXICOGRAPHIC_ASCENDING_BY_DECLARED_FIELD_ORDER_OVER_ASCII_BYTES"
    ),
}
PROVENANCE_REVIEW_STATUSES = frozenset({"NOT_REVIEWED", "REVIEWED"})
ALLOCATION_REVIEW_PROFILE_SCHEMA = "ncp.b01-selector-allocation-review-profile.v4"
MODEL_ALLOCATION_PROJECTION_SCHEMA = "ncp.b01-selector-allocation-model-projection.v4"
MODEL_ALLOCATION_PROJECTION_DOMAIN = (
    b"ncp.b01.selector-allocation.model-projection.v4\x00"
)
MODEL_ORIGIN_SIGNAL_PROJECTION_SCHEMA = (
    "ncp.b01-selector-allocation-origin-signal-projection.v1"
)
MODEL_ORIGIN_SIGNAL_PROJECTION_DOMAIN = (
    b"ncp.b01.selector-allocation.origin-signal-projection.v1\x00"
)
ALLOCATION_UNIT_ID_DOMAIN = b"ncp.b01.selector-allocation.unit-id.v1\x00"
SEMANTIC_SHAPE_PROJECTION_SCHEMA = (
    "ncp.b01-selector-allocation-semantic-shape-projection.v3"
)
SEMANTIC_SHAPE_PROJECTION_DOMAIN = (
    b"ncp.b01.selector-allocation.semantic-shape-projection.v3\x00"
)
RESOURCE_CLOSURE_PROJECTION_SCHEMA = "ncp.b01-resource-closure.v2"
SEMANTIC_REVIEW_SUBJECT_DOMAIN = (
    b"ncp.b01.selector-allocation.semantic-review-subject.v2\x00"
)
SEMANTIC_REVIEW_SUBJECT_CANONICALIZATION = "NCP_PRINTABLE_ASCII_SAFE_INTEGER_JSON_V1"
SEMANTIC_REVIEW_SUBJECT_FRAMING = (
    "DOMAIN_BYTES_THEN_UINT64_BE_CANONICAL_BYTE_LENGTH_THEN_CANONICAL_BYTES"
)
SEMANTIC_REVIEW_SUBJECT_SCALAR_DOMAIN = (
    "NULL_BOOLEAN_SIGNED_INTEGER_ABS_LE_9007199254740991_PRINTABLE_ASCII_STRING_ONLY"
)
SEMANTIC_REVIEW_SUBJECT_CLAIM_BOUNDARY = (
    "EXACT_CANONICAL_EXPANDED_SEMANTIC_PAYLOAD_EXCLUDING_ALLOCATION_ORACLE_"
    "DERIVED_COMMITMENTS_GENERATOR_METADATA_AND_EXECUTABLE_PROBE_BINDINGS"
)
SEMANTIC_REVIEW_SUBJECT_EXCLUDED_TOP_LEVEL_KEYS = (
    "adr_allocation_oracle",
    "adversarial_probe_bindings",
    "closure_commitments",
    "generated_by",
    "generated_view",
)
ADR_SOURCE_SET_SCHEMA = "ncp.b01-adr-source-set.v1"
ADR_SOURCE_SET_DOMAIN = b"ncp.b01-adr-source-set.v1\x00"
ADR_SOURCE_SET_SUITE = {
    "canonicalization": "UTF8_JSON_SORTED_KEYS_NO_INSIGNIFICANT_WHITESPACE",
    "digest_algorithm": "SHA256",
    "domain_hex": ADR_SOURCE_SET_DOMAIN.hex(),
    "fixed_vectors": {
        "main_with_two_modules": {
            "expected_projection": {
                "decision_id": "ADR-004",
                "schema": ADR_SOURCE_SET_SCHEMA,
                "sources": [
                    {
                        "bytes": 1,
                        "kind": "main",
                        "path": (
                            "docs/adr/0004-observer-attach-grants-and-revocation.md"
                        ),
                        "sha256": "0" * 64,
                    },
                    {
                        "bytes": 1,
                        "kind": "module",
                        "path": "docs/adr/modules/first.md",
                        "sha256": "1" * 64,
                    },
                    {
                        "bytes": 1,
                        "kind": "module",
                        "path": "docs/adr/modules/second.md",
                        "sha256": "2" * 64,
                    },
                ],
            },
            "expected_sha256": (
                "c196f117c10d961d952eb0ca1bfc368772f56a378fa96355e1e769e6fd1e5d50"
            ),
            "input": {
                "byte_length": 1,
                "decision_id": "ADR-004",
                "modules": [
                    {
                        "byte_length": 1,
                        "path": "docs/adr/modules/first.md",
                        "sha256": "1" * 64,
                    },
                    {
                        "byte_length": 1,
                        "path": "docs/adr/modules/second.md",
                        "sha256": "2" * 64,
                    },
                ],
                "path": "docs/adr/0004-observer-attach-grants-and-revocation.md",
                "sha256": "0" * 64,
            },
        },
        "schema": "ncp.b01-adr-source-set-fixed-vectors.v1",
    },
    "framing": (
        "DOMAIN_BYTES_THEN_UINT64_BE_CANONICAL_BYTE_LENGTH_THEN_CANONICAL_BYTES"
    ),
    "output": "LOWERCASE_HEXADECIMAL_64_CHARACTERS",
    "projection_fields": ["decision_id", "schema", "sources"],
    "projection_shape": "JSON_OBJECT",
    "schema": ADR_SOURCE_SET_SCHEMA,
    "source_ordering": "MAIN_SOURCE_THEN_DECLARED_MODULE_ORDER",
    "source_row_fields": ["bytes", "kind", "path", "sha256"],
    "source_row_shape": "JSON_OBJECT",
}

# The completed typed inventory is expected to exceed 2 MiB.  Four MiB remains
# below the independent 16 MiB expanded-source limit while bounding allocation
# before JSON parsing.
MAX_ALLOCATION_INVENTORY_BYTES = 4 * 1024 * 1024
MAX_ALLOCATION_SCHEMA_BYTES = 64 * 1024
MAX_ALLOCATION_ROWS = 65_536
MAX_ADR_DOCUMENT_BYTES = 256 * 1024
MAX_ADR_CORPUS_BYTES = 2 * 1024 * 1024
MAX_ADR_MODULES_PER_DOCUMENT = 8
MAX_SEMANTIC_SHAPE_ROWS = 1_000_000
MAX_SEMANTIC_SHAPE_BYTES = 32 * 1024 * 1024
MAX_SEMANTIC_SHAPE_POINTER_CHARS = 8 * 1024
MAX_SEMANTIC_SHAPE_DEPTH = 64
MAX_SEMANTIC_REVIEW_SUBJECT_BYTES = 16 * 1024 * 1024
MAX_SEMANTIC_REVIEW_SUBJECT_DEPTH = 64
MAX_SAFE_INTEGER = 9_007_199_254_740_991
MAX_SEMANTIC_REF_CHARS = 1024
MAX_MODEL_EVIDENCE_LOCATION_CHARS = 8 * 1024
MAX_EXCLUSION_REASON_CHARS = 1024

ALLOCATION_KINDS = (
    "EVENT",
    "PROFILE",
    "RESOURCE",
    "SELECTOR",
    "STATE",
    "TYPE",
)
ALLOCATION_KIND_SET = frozenset(ALLOCATION_KINDS)
ALLOCATION_ORIGIN_KINDS = frozenset(
    {
        "ARTIFACT_REGISTRY_ENTRY",
        "DECLARED_EVENT",
        "RESOURCE_DECLARATION",
        "SELECTOR_DECLARATION",
        "STATE_DECLARATION",
        "STRUCTURAL_PROFILE_DEFINITION",
        "SUBORDINATE_EVENT_DECLARATION",
    }
)
ALLOCATION_SIGNAL_KINDS = frozenset(
    {
        "RESOURCE_BACKING",
        "SELECTOR_USAGE",
        "STRUCTURAL_PROFILE_REFERENCE",
    }
)
ALLOCATION_IDENTITY_COMMITMENT_SUITE = {
    "algorithm": "SHA256",
    "canonicalization": "UTF8_JSON_SORTED_KEYS_NO_INSIGNIFICANT_WHITESPACE",
    "evidence_ordering": (
        "LEXICOGRAPHIC_ASCENDING_BY_DECLARED_FIELD_ORDER_OVER_ASCII_BYTES"
    ),
    "evidence_ordering_fields": ["evidence_kind", "semantic_location"],
    "evidence_row_fields": ["evidence_kind", "semantic_location"],
    "evidence_row_shape": "JSON_OBJECT",
    "evidence_scalar_domain": (
        "TRIMMED_NONEMPTY_PRINTABLE_ASCII_U+0020_THROUGH_U+007E"
    ),
    "evidence_uniqueness": (
        "EXACT_EVIDENCE_KIND_SEMANTIC_LOCATION_PAIR_UNIQUE_PER_ARRAY"
    ),
    "fixed_vectors": {
        "schema": "ncp.b01-selector-allocation-identity-fixed-vectors.v1",
        "unit_model_origin": {
            "expected_identity_projection": [
                "TYPE",
                "SampleType",
                "sample-type::SampleType",
                "de6ce89031c1d04d4776289af582d86237298ae40a76183cb29ffd0e53de8cbf",
            ],
            "expected_model_projection_sha256": (
                "045fe6a71fdc4f995b9af1d68cc42aadadbd19ffb9920892929e7fb27af7635f"
            ),
            "expected_origin_signal_row_count": 1,
            "expected_origin_signal_sha256": (
                "6d44f8227c9ec96c38afea4f02f9b42b2cded6d82bc699be0d531cd901461268"
            ),
            "expected_unit_id": (
                "de6ce89031c1d04d4776289af582d86237298ae40a76183cb29ffd0e53de8cbf"
            ),
            "identity_input": [
                "TYPE",
                "SampleType",
                "sample-type::SampleType",
            ],
            "model_projection_input": [
                [
                    "TYPE",
                    "SampleType",
                    "sample-type::SampleType",
                    (
                        "de6ce89031c1d04d4776289af582d86237298ae40a76183cb29"
                        "ffd0e53de8cbf"
                    ),
                ]
            ],
            "origin_signal_projection_input": [
                {
                    "exact_name": "SampleType",
                    "kind": "TYPE",
                    "origins": [
                        {
                            "evidence_kind": "ARTIFACT_REGISTRY_ENTRY",
                            "semantic_location": (
                                "artifact-ref::sample-type::SampleType"
                            ),
                        }
                    ],
                    "semantic_ref": "sample-type::SampleType",
                    "signals": [],
                    "unit_id": (
                        "de6ce89031c1d04d4776289af582d86237298ae40a76183cb29"
                        "ffd0e53de8cbf"
                    ),
                }
            ],
        },
    },
    "framing": (
        "DOMAIN_BYTES_THEN_UINT64_BE_CANONICAL_BYTE_LENGTH_THEN_CANONICAL_BYTES"
    ),
    "identity_evidence_rule": (
        "ORIGINS_AND_SIGNALS_EXCLUDED_FROM_UNIT_ID_MODEL_PROJECTION_"
        "EQUALITY_AND_HASHING"
    ),
    "identity_excluded_fields": ["origins", "signals"],
    "identity_fields": ["kind", "exact_name", "semantic_ref"],
    "identity_scalar_domain": "PRINTABLE_ASCII_CLOSED_BY_KIND_GRAMMAR",
    "identity_shape": "JSON_ARRAY",
    "model_projection_domain_hex": MODEL_ALLOCATION_PROJECTION_DOMAIN.hex(),
    "model_projection_ordering": (
        "LEXICOGRAPHIC_ASCENDING_BY_DECLARED_FIELD_ORDER_OVER_ASCII_BYTES"
    ),
    "model_projection_ordering_fields": [
        "kind",
        "exact_name",
        "semantic_ref",
        "unit_id",
    ],
    "model_projection_row_fields": [
        "kind",
        "exact_name",
        "semantic_ref",
        "unit_id",
    ],
    "model_projection_row_shape": "JSON_ARRAY",
    "model_projection_shape": "JSON_ARRAY_OF_JSON_ARRAY_ROWS",
    "model_projection_uniqueness": "EXACT_ROW_UNIQUE_AND_UNIT_ID_UNIQUE",
    "origin_kinds": sorted(ALLOCATION_ORIGIN_KINDS),
    "origin_requirement": "ONE_OR_MORE_CLOSED_MECHANICAL_ORIGINS_PER_UNIT",
    "origin_signal_projection_domain_hex": (
        MODEL_ORIGIN_SIGNAL_PROJECTION_DOMAIN.hex()
    ),
    "origin_signal_projection_ordering": (
        "LEXICOGRAPHIC_ASCENDING_BY_DECLARED_FIELD_ORDER_OVER_ASCII_BYTES"
    ),
    "origin_signal_projection_ordering_fields": [
        "kind",
        "exact_name",
        "semantic_ref",
        "unit_id",
    ],
    "origin_signal_projection_row_fields": [
        "exact_name",
        "kind",
        "origins",
        "semantic_ref",
        "signals",
        "unit_id",
    ],
    "origin_signal_projection_row_shape": "JSON_OBJECT",
    "origin_signal_projection_shape": "JSON_ARRAY_OF_JSON_OBJECT_ROWS",
    "origin_signal_projection_uniqueness": "UNIT_ID_UNIQUE",
    "schema": "ncp.b01-selector-allocation-identity-commitment-suite.v1",
    "signal_authority": (
        "ZERO_OR_MORE_CLOSED_NONAUTHORITATIVE_SIGNALS_NEVER_SELECT_"
        "IDENTITY_OR_ADR_ASSIGNMENT"
    ),
    "signal_kinds": sorted(ALLOCATION_SIGNAL_KINDS),
    "unit_id_domain_hex": ALLOCATION_UNIT_ID_DOMAIN.hex(),
    "unit_id_output": "LOWERCASE_HEXADECIMAL_64_CHARACTERS",
}
SEMANTIC_REVIEW_SUBJECT_SUITE = {
    "algorithm": "SHA256",
    "canonicalization": SEMANTIC_REVIEW_SUBJECT_CANONICALIZATION,
    "claim_boundary": SEMANTIC_REVIEW_SUBJECT_CLAIM_BOUNDARY,
    "domain_hex": SEMANTIC_REVIEW_SUBJECT_DOMAIN.hex(),
    "excluded_top_level_keys": list(SEMANTIC_REVIEW_SUBJECT_EXCLUDED_TOP_LEVEL_KEYS),
    "fixed_vectors": {
        "nesting_depth_boundary": {
            "construction": (
                "ROOT_OBJECT_MEMBER_X_WITH_NULL_WRAPPED_IN_N_SINGLETON_ARRAYS"
            ),
            "expected_accepted_canonical_utf8_byte_length": 136,
            "expected_accepted_canonical_utf8_hex": (
                "7b2278223a5b5b5b5b5b5b5b5b5b5b5b5b5b5b5b5b5b5b5b5b5b5b5b5b5b5b5b5b5b5b5b5b5b5b5b"
                "5b5b5b5b5b5b5b5b5b5b5b5b5b5b5b5b5b5b5b5b5b5b5b5b5b5b5b5b6e756c6c5d5d5d5d5d5d5d5d"
                "5d5d5d5d5d5d5d5d5d5d5d5d5d5d5d5d5d5d5d5d5d5d5d5d5d5d5d5d5d5d5d5d5d5d5d5d5d5d5d5d"
                "5d5d5d5d5d5d5d5d5d5d5d5d5d5d5d7d"
            ),
            "expected_accepted_sha256": (
                "27007f10558810346f9ca729d79e19a327d6d5174991f8a5944d2babb870bf7f"
            ),
            "first_rejected_array_wrapper_count": 64,
            "maximum_accepted_array_wrapper_count": 63,
            "root_depth": 0,
        },
        "schema": "ncp.b01-selector-allocation-semantic-subject-fixed-vectors.v2",
        "semantic_model": {
            "expected_byte_length": 50,
            "expected_canonical_utf8_hex": (
                "7b2273656d616e7469635f6d6f64656c223a7b226272616e63685f6964"
                "223a224649525354222c226c696d6974223a317d7d"
            ),
            "expected_projection": {
                "semantic_model": {
                    "branch_id": "FIRST",
                    "limit": 1,
                }
            },
            "expected_sha256": (
                "15c7b92ff8ad2fcd9f928b603d4c7e143dc2eb9e2df3c4a3f8ee83ada34da19d"
            ),
            "input": {
                "adr_allocation_oracle": {},
                "semantic_model": {
                    "branch_id": "FIRST",
                    "limit": 1,
                },
            },
        },
    },
    "framing": SEMANTIC_REVIEW_SUBJECT_FRAMING,
    "integer_encoding": (
        "MINUS_ONLY_WHEN_NEGATIVE_THEN_UNPADDED_BASE10_DIGITS_WITH_ZERO_AS_0"
    ),
    "list_ordering": "PRESERVE_SOURCE_ARRAY_ORDER",
    "maximum_canonical_bytes": MAX_SEMANTIC_REVIEW_SUBJECT_BYTES,
    "maximum_nesting_depth": MAX_SEMANTIC_REVIEW_SUBJECT_DEPTH,
    "nesting_depth_counting": (
        "DOCUMENT_ROOT_IS_DEPTH_0_EACH_ARRAY_OR_OBJECT_CHILD_INCREMENTS_BY_1"
    ),
    "object_member_ordering": (
        "RECURSIVE_LEXICOGRAPHIC_ASCENDING_BY_MEMBER_NAME_ASCII_BYTES"
    ),
    "output": "LOWERCASE_HEXADECIMAL_64_CHARACTERS",
    "projection_rule": (
        "EXACT_TOP_LEVEL_OBJECT_AFTER_EXCLUDING_DECLARED_TOP_LEVEL_KEYS_"
        "NO_OTHER_FIELD_ELISION"
    ),
    "projection_shape": "JSON_OBJECT",
    "root_depth": 0,
    "scalar_domain": SEMANTIC_REVIEW_SUBJECT_SCALAR_DOMAIN,
    "string_escaping": (
        "BACKSLASH_AS_DOUBLE_BACKSLASH_DOUBLE_QUOTE_AS_BACKSLASH_DOUBLE_QUOTE_"
        "NO_OTHER_ESCAPES"
    ),
}
SEMANTIC_SHAPE_COMMITMENT_SUITE = {
    "algorithm": "SHA256",
    "array_index_treatment": (
        "UNPADDED_BASE10_NONNEGATIVE_INTEGER_SEGMENT_WITH_ZERO_AS_0_"
        "ORDERED_BY_COMPLETE_POINTER_ASCII_BYTES"
    ),
    "bounds_application": "REJECT_BEFORE_DIGEST_SUCCESS_IF_ANY_BOUND_EXCEEDED",
    "canonicalization": "UTF8_JSON_SORTED_KEYS_NO_INSIGNIFICANT_WHITESPACE",
    "domain_hex": SEMANTIC_SHAPE_PROJECTION_DOMAIN.hex(),
    "fixed_vectors": {
        "nesting_depth_boundary": {
            "construction": (
                "ROOT_OBJECT_MEMBER_X_WITH_NULL_WRAPPED_IN_N_SINGLETON_ARRAYS"
            ),
            "expected_accepted_entry_count": 65,
            "expected_accepted_projection_byte_length": 5006,
            "expected_accepted_sha256": (
                "ffdf1822c36f52e46e9ede5e4880b02a47fdeb5936540a8fdb23f447afc6c325"
            ),
            "first_rejected_array_wrapper_count": 64,
            "maximum_accepted_array_wrapper_count": 63,
            "root_depth": 0,
        },
        "representative_types_and_escaping": {
            "expected_entry_count": 7,
            "expected_projection_byte_length": 121,
            "expected_projection_rows": [
                ["", "object"],
                ["/", "null"],
                ["/~0", "string"],
                ["/~1", "array"],
                ["/~1/0", "boolean"],
                ["/~1/1", "integer"],
                ["/~1/2", "integer"],
            ],
            "expected_sha256": (
                "4a24a885fe8a123556ff83f27ab7389f4c498044420fe6afa27be3d60e7a2325"
            ),
            "source_canonical_utf8_byte_length": 63,
            "source_canonical_utf8_hex": (
                "7b22223a6e756c6c2c222f223a5b747275652c2d3930303731393932353437343039"
                "39312c393030373139393235343734303939315d2c227e223a2278227d"
            ),
        },
        "schema": "ncp.b01-selector-allocation-semantic-shape-fixed-vectors.v3",
    },
    "framing": (
        "DOMAIN_BYTES_THEN_UINT64_BE_CANONICAL_BYTE_LENGTH_THEN_CANONICAL_BYTES"
    ),
    "maximum_entries": MAX_SEMANTIC_SHAPE_ROWS,
    "maximum_nesting_depth": MAX_SEMANTIC_SHAPE_DEPTH,
    "maximum_pointer_characters": MAX_SEMANTIC_SHAPE_POINTER_CHARS,
    "maximum_projection_bytes": MAX_SEMANTIC_SHAPE_BYTES,
    "nesting_depth_counting": (
        "DOCUMENT_ROOT_IS_DEPTH_0_EACH_ARRAY_OR_OBJECT_CHILD_INCREMENTS_BY_1"
    ),
    "object_member_ordering": (
        "LEXICOGRAPHIC_ASCENDING_BY_RFC6901_ESCAPED_MEMBER_TOKEN_ASCII_BYTES"
    ),
    "output": "LOWERCASE_HEXADECIMAL_64_CHARACTERS",
    "pointer_root_token": "",
    "pointer_scalar_domain": (
        "EMPTY_DOCUMENT_ROOT_OR_SLASH_PREFIXED_PRINTABLE_ASCII_RFC6901_SEGMENTS"
    ),
    "pointer_segment_escaping": ("REPLACE_TILDE_WITH_~0_THEN_REPLACE_SLASH_WITH_~1"),
    "pointer_syntax": "RFC6901_JSON_POINTER",
    "projection_shape": "JSON_ARRAY_OF_JSON_ARRAY_ROWS",
    "row_fields": ["json_pointer", "type_token"],
    "row_ordering": (
        "LEXICOGRAPHIC_ASCENDING_BY_STORED_RFC6901_JSON_POINTER_ASCII_BYTES"
    ),
    "row_shape": "JSON_ARRAY_OF_EXACTLY_TWO_STRINGS",
    "row_uniqueness": "JSON_POINTER_UNIQUE",
    "root_depth": 0,
    "scalar_domain": (
        "NULL_EXACT_BOOLEAN_CANONICAL_SIGNED_SAFE_INTEGER_ABS_LE_"
        "9007199254740991_EMPTY_OR_PRINTABLE_ASCII_STRING"
    ),
    "schema": "ncp.b01-selector-allocation-semantic-shape-commitment-suite.v3",
    "source_shape": "JSON_OBJECT",
    "source_member_name_domain": ("EMPTY_OR_PRINTABLE_ASCII_U+0020_THROUGH_U+007E"),
    "stream_projection": (
        "OPEN_BRACKET_THEN_CANONICAL_ROWS_COMMA_SEPARATED_THEN_CLOSE_BRACKET"
    ),
    "type_token_mapping": {
        "array": "JSON_ARRAY",
        "boolean": "JSON_LITERAL_TRUE_OR_FALSE",
        "integer": (
            "CANONICAL_SIGNED_INTEGER_TOKEN_ABS_LE_9007199254740991_"
            "NEGATIVE_ZERO_FORBIDDEN"
        ),
        "null": "JSON_LITERAL_NULL",
        "object": "JSON_OBJECT",
        "string": "EMPTY_OR_PRINTABLE_ASCII_JSON_STRING",
    },
    "type_tokens": [
        "array",
        "boolean",
        "integer",
        "null",
        "object",
        "string",
    ],
}
ALLOCATION_STATUSES = frozenset({"COMPLETE", "INCOMPLETE_FAIL_CLOSED"})
EXCLUSION_CLASSIFICATIONS = frozenset(
    {
        "CROSS_ADR_REFERENCE_NONDEFINING",
        "ENUM_OR_BRANCH_VALUE",
        "HISTORICAL_OR_REJECTED_ALIAS",
        "MODEL_OMISSION_FAIL_CLOSED",
        "PROFILE_OR_INVARIANT_IDENTIFIER",
    }
)
ADR_ALLOCATION_PATHS = (
    "docs/adr/0001-separate-simulation-and-plant-sessions.md",
    "docs/adr/0002-contract-identity-and-release-authorization.md",
    "docs/adr/0003-authenticated-production-ingress.md",
    "docs/adr/0004-observer-attach-grants-and-revocation.md",
    "docs/adr/0005-declared-stream-lifecycle.md",
    "docs/adr/0006-body-issued-authority-and-time.md",
    "docs/adr/0007-command-disposition-journal.md",
    "docs/adr/0008-extension-namespace-and-galadriel-separation.md",
    "docs/adr/0009-security-state-rotation-and-revocation.md",
    "docs/adr/0010-plane-qos-retention-and-overload.md",
    "docs/adr/0011-ecosystem-topology-and-handover.md",
)
ADR_ALLOCATION_MODULE_PATHS = (
    (),
    (),
    (),
    ("docs/adr/modules/adr-004-cross-store-observer-closure-and-enrollment.md",),
    (),
    (),
    (),
    (),
    ("docs/adr/modules/adr-009-cross-store-producer-and-compromise-evidence.md",),
    (),
    (),
)
ADR_ALLOCATION_ANCHOR_IDS = tuple(
    f"ncp-b01-selector-allocation-adr-{index:03d}-v1"
    for index in range(1, len(ADR_ALLOCATION_PATHS) + 1)
)
ADR_ALLOCATION_ANCHOR_BY_ID = {
    f"ADR-{index:03d}": anchor_id
    for index, anchor_id in enumerate(ADR_ALLOCATION_ANCHOR_IDS, 1)
}

SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")
SEMANTIC_ID = re.compile(r"^[A-Z][A-Z0-9_]*$")
EXACT_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
RESOURCE_EXACT_NAME = re.compile(r"^[A-Z][A-Z0-9_]*(?:\.[A-Z][A-Z0-9_]*)+$")
ADR_ID = re.compile(r"^ADR-[0-9]{3}$")
ALLOCATION_REF = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*::[A-Za-z0-9_]+$")
STATE_SEMANTIC_ID = re.compile(
    r"^([A-Z][A-Z0-9_]*)\.([A-Z][A-Z0-9_]*)\.([A-Z][A-Z0-9_]*)$"
)
PROFILE_ID_SEMANTIC_REF = re.compile(r"^profile-id::([A-Z][A-Z0-9_]*)$")
PROFILE_PATH_SEMANTIC_REF = re.compile(r"^/[A-Za-z0-9_~/-]+$")
PROFILE_REFERENCE_SEMANTIC_REF = re.compile(
    r"^profile-ref::[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+$"
)
RESOURCE_SEMANTIC_REF = re.compile(
    r"^resource-id::([A-Z][A-Z0-9_]*(?:\.[A-Z][A-Z0-9_]*)+)$"
)
SELECTOR_SEMANTIC_REF = re.compile(r"^selector-id::([A-Z][A-Z0-9_]*)$")
STATE_SEMANTIC_REF = re.compile(
    r"^state-id::([A-Z][A-Z0-9_]*)\.([A-Z][A-Z0-9_]*)\.([A-Z][A-Z0-9_]*)$"
)

INVENTORY_METADATA_KEYS = {
    "$schema",
    "candidate",
    "normative",
    "schema",
    "task",
}
ORACLE_KEYS = {
    "allocation_review_profile",
    "allocations",
    "claim_boundary",
    "document_row_commitment",
    "documents",
    "exclusions",
    "model_allocation_count",
    "model_allocation_sha256",
    "provenance_review",
    "required_kinds",
    "semantic_review_subject",
    "semantic_shape_entry_count",
    "semantic_shape_sha256",
    "status",
}
PROVENANCE_REVIEW_KEYS = set(PROVENANCE_REVIEW_SUITE) | {
    "reviewed_assignment_sha256",
    "status",
}
SEMANTIC_REVIEW_SUBJECT_KEYS = set(SEMANTIC_REVIEW_SUBJECT_SUITE) | {
    "byte_length",
    "sha256",
}
ALLOCATION_REVIEW_PROFILE_KEYS = {
    "allocation_identity_commitment_suite",
    "allocation_schema_byte_length",
    "allocation_schema_id",
    "allocation_schema_sha256",
    "model_allocation_count",
    "model_allocation_sha256",
    "model_origin_signal_projection_schema",
    "model_origin_signal_row_count",
    "model_origin_signal_sha256",
    "model_projection_schema",
    "required_kinds",
    "resource_closure_row_count",
    "resource_closure_schema",
    "resource_closure_sha256",
    "schema",
    "semantic_shape_entry_count",
    "semantic_shape_commitment_suite",
    "semantic_shape_projection_schema",
    "semantic_shape_sha256",
}
DOCUMENT_ROW_COMMITMENT_KEYS = {
    "allocation_row_fields",
    "algorithm",
    "canonicalization",
    "domain_hex",
    "exclusion_row_fields",
    "fixed_vectors",
    "framing",
    "output",
    "row_kind_encoding",
    "row_ordering",
    "row_kinds",
    "row_projection",
    "row_selection",
    "row_shape",
}
INVENTORY_KEYS = INVENTORY_METADATA_KEYS | ORACLE_KEYS
BINDING_KEYS = {
    "authoring_byte_length",
    "authoring_file",
    "authoring_sha256",
    "canonicalization",
    "schema_byte_length",
    "schema_file",
    "schema_id",
    "schema_sha256",
}
DOCUMENT_KEYS = {
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
DOCUMENT_MODULE_KEYS = {
    "byte_length",
    "path",
    "sha256",
}
DOCUMENT_SOURCE_SET_KEYS = set(ADR_SOURCE_SET_SUITE) | {"sha256"}
ALLOCATION_ROW_KEYS = {
    "adr_id",
    "exact_name",
    "kind",
    "semantic_ref",
    "source_anchor",
    "unit_id",
}
MODEL_ORIGIN_SIGNAL_ROW_KEYS = {
    "exact_name",
    "kind",
    "origins",
    "semantic_ref",
    "signals",
    "unit_id",
}
MODEL_EVIDENCE_ROW_KEYS = {
    "evidence_kind",
    "semantic_location",
}
EXCLUSION_ROW_KEYS = {
    "adr_id",
    "classification",
    "exact_name",
    "reason",
    "source_anchor",
}

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
        r"^ADR-[0-9]{3}$",
        r"^[0-9a-f]{64}$",
        r"^[A-Za-z][A-Za-z0-9_]*$",
        r"^[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)*$",
        r"^ncp-b01-selector-allocation-adr-[0-9]{3}-v1$",
    }
)


class SelectorAllocationInventoryError(ValueError):
    """The external allocation inventory or its binding is invalid."""


@dataclass(frozen=True)
class AllocationInventorySnapshot:
    """Exact bytes and decoded values used for one generation attempt."""

    base_directory: Path
    binding: dict[str, Any]
    inventory: dict[str, Any]
    inventory_path: Path
    inventory_raw: bytes
    oracle: dict[str, Any]
    schema_path: Path
    schema_raw: bytes


def _fail(message: str) -> NoReturn:
    raise SelectorAllocationInventoryError(message)


def _require(condition: bool, message: str) -> None:
    if not condition:
        _fail(message)


def _closed_object(
    value: Any,
    *,
    keys: set[str],
    label: str,
) -> dict[str, Any]:
    _require(isinstance(value, dict), f"{label}: expected an object")
    _require(
        set(value) == keys,
        (f"{label}: expected exact keys {sorted(keys)}, got {sorted(value)}"),
    )
    return value


def _assert_no_mutable_aliases(value: Any, *, label: str) -> None:
    """Reject shared dict/list identities in values supplied by Python callers."""

    seen: dict[int, str] = {}
    pending: list[tuple[Any, str]] = [(value, "$")]
    while pending:
        current, path = pending.pop()
        if not isinstance(current, (dict, list)):
            continue
        identity = id(current)
        prior = seen.get(identity)
        _require(
            prior is None,
            f"{label}: mutable JSON subtree alias at {path}; first seen at {prior}",
        )
        seen[identity] = path
        if isinstance(current, dict):
            for key, child in current.items():
                pending.append((child, f"{path}.{key}"))
        else:
            for index, child in enumerate(current):
                pending.append((child, f"{path}[{index}]"))


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
            isinstance(schema["enum"], list) and bool(schema["enum"]),
            f"{path}.enum: expected a nonempty array",
        )
    if "required" in schema:
        required = schema["required"]
        _require(
            isinstance(required, list)
            and all(isinstance(item, str) for item in required)
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
    additional = schema.get("additionalProperties")
    if isinstance(additional, dict):
        _assert_supported_schema(
            additional,
            f"{path}.additionalProperties",
        )
    elif "additionalProperties" in schema:
        _require(
            isinstance(additional, bool),
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
                _validate_schema_instance(item, properties[key], f"{path}.{key}")
            elif additional is False:
                _fail(f"{path}: unknown property {key!r}")
            elif isinstance(additional, dict):
                _validate_schema_instance(item, additional, f"{path}.{key}")
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
            items = [canonical_bytes(item) for item in value]
            _require(
                len(items) == len(set(items)),
                f"{path}: contains duplicate items",
            )
        if "items" in schema:
            for index, item in enumerate(value):
                _validate_schema_instance(item, schema["items"], f"{path}[{index}]")
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


def load_inventory_schema(path: Path) -> tuple[bytes, dict[str, Any]]:
    raw = read_bounded_regular_file(
        path,
        maximum_bytes=MAX_ALLOCATION_SCHEMA_BYTES,
        label="selector allocation authoring schema",
    )
    _require(
        sha256(raw).hexdigest() == INVENTORY_SCHEMA_SHA256,
        "allocation schema reviewed byte identity changed",
    )
    value = parse_json_bytes(raw, label=str(path))
    _require(isinstance(value, dict), "allocation schema must be an object")
    _assert_supported_schema(value)
    _require(
        value.get("$schema") == "https://json-schema.org/draft/2020-12/schema",
        "allocation schema must use JSON Schema draft 2020-12",
    )
    _require(
        value.get("$id") == INVENTORY_SCHEMA_URL,
        "allocation schema has an unexpected $id",
    )
    _require(value.get("type") == "object", "allocation schema root must be object")
    _require(
        value.get("additionalProperties") is False,
        "allocation schema root must reject additional properties",
    )
    _require(
        value.get("required") == sorted(INVENTORY_KEYS),
        "allocation schema has an unexpected root requirement set",
    )
    _require(
        set(value.get("properties", {})) == INVENTORY_KEYS,
        "allocation schema has an unexpected root property set",
    )
    return raw, value


def _require_positive_integer(value: Any, *, label: str) -> None:
    _require(
        isinstance(value, int) and not isinstance(value, bool) and value > 0,
        f"{label}: expected a positive integer",
    )


def document_rows_sha256(
    rows: list[dict[str, Any]],
    *,
    row_kind: str,
) -> str:
    """Hash one domain-separated row array with ADR and anchor provenance."""

    _require(
        row_kind in {"allocations", "exclusions"},
        f"unsupported document row commitment kind {row_kind!r}",
    )
    digest = sha256()
    digest.update(DOCUMENT_ROW_COMMITMENT_DOMAIN)
    digest.update(row_kind.encode("ascii"))
    digest.update(b"\x00")
    digest.update(canonical_bytes(rows))
    return digest.hexdigest()


def build_not_reviewed_provenance_review() -> dict[str, Any]:
    """Return the exact fail-closed provenance suite and zero review state."""

    return {
        **copy.deepcopy(PROVENANCE_REVIEW_SUITE),
        "reviewed_assignment_sha256": "0" * 64,
        "status": "NOT_REVIEWED",
    }


def allocation_unit_id(kind: str, exact_name: str, semantic_ref: str) -> str:
    """Derive one portable unit ID from the owner-free semantic identity."""

    projection = canonical_bytes([kind, exact_name, semantic_ref])
    digest = sha256()
    digest.update(ALLOCATION_UNIT_ID_DOMAIN)
    digest.update(len(projection).to_bytes(8, "big"))
    digest.update(projection)
    return digest.hexdigest()


def allocation_identity_projection(
    kind: str,
    exact_name: str,
    semantic_ref: str,
) -> list[str]:
    """Return the complete owner-free row used by the model commitment."""

    return [
        kind,
        exact_name,
        semantic_ref,
        allocation_unit_id(kind, exact_name, semantic_ref),
    ]


def _validate_allocation_identity_fields(
    kind: Any,
    exact_name: Any,
    semantic_ref: Any,
    unit_id: Any,
    *,
    label: str,
) -> None:
    """Validate one closed semantic identity and its derived unit ID."""

    _require(
        isinstance(kind, str) and kind in ALLOCATION_KIND_SET,
        f"{label}: unknown allocation kind",
    )
    _require(
        isinstance(exact_name, str)
        and (
            RESOURCE_EXACT_NAME.fullmatch(exact_name)
            if kind == "RESOURCE"
            else EXACT_NAME.fullmatch(exact_name)
        )
        is not None
        and isinstance(semantic_ref, str)
        and 3 <= len(semantic_ref) <= MAX_SEMANTIC_REF_CHARS
        and isinstance(unit_id, str)
        and SHA256_HEX.fullmatch(unit_id) is not None,
        f"{label}: invalid semantic identity",
    )
    if kind == "PROFILE":
        _require(
            (
                PROFILE_PATH_SEMANTIC_REF.fullmatch(semantic_ref) is not None
                and "//" not in semantic_ref
            )
            or PROFILE_ID_SEMANTIC_REF.fullmatch(semantic_ref) is not None
            or PROFILE_REFERENCE_SEMANTIC_REF.fullmatch(semantic_ref) is not None,
            f"{label}: invalid PROFILE semantic reference",
        )
    elif kind == "RESOURCE":
        resource_match = RESOURCE_SEMANTIC_REF.fullmatch(semantic_ref)
        _require(
            resource_match is not None and resource_match.group(1) == exact_name,
            f"{label}: RESOURCE semantic identity mismatch",
        )
    elif kind == "SELECTOR":
        selector_match = SELECTOR_SEMANTIC_REF.fullmatch(semantic_ref)
        _require(
            selector_match is not None and selector_match.group(1) == exact_name,
            f"{label}: SELECTOR semantic identity mismatch",
        )
    elif kind in {"EVENT", "TYPE"}:
        _require(
            ALLOCATION_REF.fullmatch(semantic_ref) is not None,
            f"{label}: invalid {kind} semantic reference",
        )
        if kind == "TYPE":
            _require(
                semantic_ref.split("::", 1)[1] == exact_name,
                f"{label}: TYPE semantic identity mismatch",
            )
    else:
        state_match = STATE_SEMANTIC_REF.fullmatch(semantic_ref)
        _require(
            state_match is not None and state_match.group(3) == exact_name,
            f"{label}: STATE semantic identity mismatch",
        )
    _require(
        unit_id == allocation_unit_id(kind, exact_name, semantic_ref),
        f"{label}: forged unit ID",
    )


def model_allocation_projection_sha256(rows: list[list[str]]) -> str:
    """Hash canonical owner-free identity rows under the v4 model domain."""

    _require(isinstance(rows, list), "model allocation projection must be an array")
    normalized_rows: list[list[str]] = []
    unit_ids: set[str] = set()
    for index, row in enumerate(rows):
        label = f"model allocation projection[{index}]"
        _require(
            isinstance(row, list) and len(row) == 4,
            f"{label}: expected an exact four-field identity row",
        )
        kind, exact_name, semantic_ref, unit_id = row
        _validate_allocation_identity_fields(
            kind,
            exact_name,
            semantic_ref,
            unit_id,
            label=label,
        )
        _require(unit_id not in unit_ids, f"{label}: duplicate unit ID")
        unit_ids.add(unit_id)
        normalized_rows.append([kind, exact_name, semantic_ref, unit_id])

    projection = canonical_bytes(sorted(normalized_rows))
    digest = sha256()
    digest.update(MODEL_ALLOCATION_PROJECTION_DOMAIN)
    digest.update(len(projection).to_bytes(8, "big"))
    digest.update(projection)
    return digest.hexdigest()


def model_origin_signal_projection_commitment(
    rows: list[dict[str, Any]],
) -> tuple[int, str]:
    """Hash sorted origin/signal rows separately from semantic unit identity."""

    _require(isinstance(rows, list), "origin/signal projection must be an array")
    normalized_rows: list[dict[str, Any]] = []
    unit_ids: set[str] = set()
    for index, row in enumerate(rows):
        label = f"origin/signal projection[{index}]"
        _closed_object(row, keys=MODEL_ORIGIN_SIGNAL_ROW_KEYS, label=label)
        kind = row["kind"]
        exact_name = row["exact_name"]
        semantic_ref = row["semantic_ref"]
        unit_id = row["unit_id"]
        _validate_allocation_identity_fields(
            kind,
            exact_name,
            semantic_ref,
            unit_id,
            label=label,
        )
        _require(unit_id not in unit_ids, f"{label}: duplicate unit ID")
        unit_ids.add(unit_id)

        normalized_evidence: dict[str, list[dict[str, str]]] = {}
        for field, allowed_kinds in (
            ("origins", ALLOCATION_ORIGIN_KINDS),
            ("signals", ALLOCATION_SIGNAL_KINDS),
        ):
            evidence_rows = row[field]
            _require(
                isinstance(evidence_rows, list),
                f"{label}.{field}: expected an array",
            )
            if field == "origins":
                _require(
                    bool(evidence_rows),
                    f"{label}.origins: every unit needs a mechanical origin",
                )
            evidence_keys: set[tuple[str, str]] = set()
            normalized_items: list[dict[str, str]] = []
            for evidence_index, evidence in enumerate(evidence_rows):
                evidence_label = f"{label}.{field}[{evidence_index}]"
                _closed_object(
                    evidence,
                    keys=MODEL_EVIDENCE_ROW_KEYS,
                    label=evidence_label,
                )
                evidence_kind = evidence["evidence_kind"]
                semantic_location = evidence["semantic_location"]
                _require(
                    isinstance(evidence_kind, str) and evidence_kind in allowed_kinds,
                    f"{evidence_label}: unknown evidence kind",
                )
                _require(
                    isinstance(semantic_location, str)
                    and semantic_location
                    and semantic_location == semantic_location.strip()
                    and all(
                        0x20 <= ord(character) <= 0x7E
                        for character in semantic_location
                    )
                    and len(semantic_location) <= MAX_MODEL_EVIDENCE_LOCATION_CHARS,
                    f"{evidence_label}: invalid semantic location",
                )
                evidence_key = (evidence_kind, semantic_location)
                _require(
                    evidence_key not in evidence_keys,
                    f"{evidence_label}: duplicate evidence",
                )
                evidence_keys.add(evidence_key)
                normalized_items.append(
                    {
                        "evidence_kind": evidence_kind,
                        "semantic_location": semantic_location,
                    }
                )
            normalized_evidence[field] = sorted(
                normalized_items,
                key=lambda item: (
                    item["evidence_kind"],
                    item["semantic_location"],
                ),
            )
        normalized_rows.append(
            {
                "exact_name": exact_name,
                "kind": kind,
                "origins": normalized_evidence["origins"],
                "semantic_ref": semantic_ref,
                "signals": normalized_evidence["signals"],
                "unit_id": unit_id,
            }
        )

    projection = canonical_bytes(
        sorted(
            normalized_rows,
            key=lambda row: (
                row["kind"],
                row["exact_name"],
                row["semantic_ref"],
                row["unit_id"],
            ),
        )
    )
    digest = sha256()
    digest.update(MODEL_ORIGIN_SIGNAL_PROJECTION_DOMAIN)
    digest.update(len(projection).to_bytes(8, "big"))
    digest.update(projection)
    return len(normalized_rows), digest.hexdigest()


def adr_source_set_sha256(
    *,
    adr_id: str,
    path: str,
    byte_length: int,
    source_sha256: str,
    modules: list[dict[str, Any]],
) -> str:
    """Hash one ordered ADR main-and-module source set."""

    sources = [
        {
            "bytes": byte_length,
            "kind": "main",
            "path": path,
            "sha256": source_sha256,
        },
        *[
            {
                "bytes": module["byte_length"],
                "kind": "module",
                "path": module["path"],
                "sha256": module["sha256"],
            }
            for module in modules
        ],
    ]
    projection = canonical_bytes(
        {
            "decision_id": adr_id,
            "schema": ADR_SOURCE_SET_SCHEMA,
            "sources": sources,
        }
    )
    digest = sha256()
    digest.update(ADR_SOURCE_SET_DOMAIN)
    digest.update(len(projection).to_bytes(8, "big"))
    digest.update(projection)
    return digest.hexdigest()


def build_allocation_review_profile(
    *,
    allocation_schema_raw: bytes,
    model_allocation_count: int,
    model_allocation_sha256: str,
    model_origin_signal_row_count: int,
    model_origin_signal_sha256: str,
    resource_closure_row_count: int,
    resource_closure_sha256: str,
    semantic_shape_entry_count: int,
    semantic_shape_sha256: str,
) -> dict[str, Any]:
    """Bind the review to one exact taxonomy, projection, and schema."""

    _require(
        0 < len(allocation_schema_raw) <= MAX_ALLOCATION_SCHEMA_BYTES,
        "allocation review profile schema bytes are outside the supported bound",
    )
    _require(
        isinstance(model_origin_signal_row_count, int)
        and not isinstance(model_origin_signal_row_count, bool)
        and model_origin_signal_row_count == model_allocation_count
        and model_origin_signal_row_count > 0,
        "allocation review profile origin/signal rows must cover every model unit",
    )
    _require(
        isinstance(model_origin_signal_sha256, str)
        and SHA256_HEX.fullmatch(model_origin_signal_sha256) is not None,
        "allocation review profile origin/signal digest is invalid",
    )
    return {
        "allocation_identity_commitment_suite": copy.deepcopy(
            ALLOCATION_IDENTITY_COMMITMENT_SUITE
        ),
        "allocation_schema_byte_length": len(allocation_schema_raw),
        "allocation_schema_id": INVENTORY_SCHEMA_ID,
        "allocation_schema_sha256": sha256(allocation_schema_raw).hexdigest(),
        "model_allocation_count": model_allocation_count,
        "model_allocation_sha256": model_allocation_sha256,
        "model_origin_signal_projection_schema": (
            MODEL_ORIGIN_SIGNAL_PROJECTION_SCHEMA
        ),
        "model_origin_signal_row_count": model_origin_signal_row_count,
        "model_origin_signal_sha256": model_origin_signal_sha256,
        "model_projection_schema": MODEL_ALLOCATION_PROJECTION_SCHEMA,
        "required_kinds": list(ALLOCATION_KINDS),
        "resource_closure_row_count": resource_closure_row_count,
        "resource_closure_schema": RESOURCE_CLOSURE_PROJECTION_SCHEMA,
        "resource_closure_sha256": resource_closure_sha256,
        "schema": ALLOCATION_REVIEW_PROFILE_SCHEMA,
        "semantic_shape_entry_count": semantic_shape_entry_count,
        "semantic_shape_commitment_suite": copy.deepcopy(
            SEMANTIC_SHAPE_COMMITMENT_SUITE
        ),
        "semantic_shape_projection_schema": SEMANTIC_SHAPE_PROJECTION_SCHEMA,
        "semantic_shape_sha256": semantic_shape_sha256,
    }


def provenance_assignment_sha256(
    documents: list[dict[str, Any]],
    allocations: list[dict[str, Any]],
    exclusions: list[dict[str, Any]],
    allocation_review_profile: dict[str, Any],
    semantic_review_subject: dict[str, Any],
) -> str:
    """Hash the exact ADR sources, assignments, and semantic review subject."""

    digest = sha256()
    digest.update(PROVENANCE_REVIEW_DOMAIN)
    digest.update(
        canonical_bytes(
            {
                "allocation_review_profile": allocation_review_profile,
                "allocations": allocations,
                "document_source_sets": [
                    {
                        "adr_id": document["adr_id"],
                        "allocation_anchor_id": document["allocation_anchor_id"],
                        "source_set": document["source_set"],
                    }
                    for document in documents
                ],
                "exclusions": exclusions,
                "semantic_review_subject": semantic_review_subject,
            }
        )
    )
    return digest.hexdigest()


def _semantic_review_subject_canonical_bytes(value: Any) -> bytes:
    """Encode the declared language-neutral semantic-review JSON subset."""

    def encode_string(item: str, *, label: str) -> bytes:
        _require(
            all(0x20 <= ord(character) <= 0x7E for character in item),
            f"{label} must contain printable ASCII characters only",
        )
        escaped = item.replace("\\", "\\\\").replace('"', '\\"')
        return b'"' + escaped.encode("ascii") + b'"'

    def encode(item: Any, *, path: str, depth: int) -> bytes:
        _require(
            depth <= MAX_SEMANTIC_REVIEW_SUBJECT_DEPTH,
            (
                "semantic review subject exceeds "
                f"{MAX_SEMANTIC_REVIEW_SUBJECT_DEPTH} JSON levels"
            ),
        )
        item_type = type(item)
        if item_type is dict:
            encoded_items: list[bytes] = []
            _require(
                all(type(key) is str for key in item),
                f"{path}: semantic review subject object key is not a string",
            )
            for key in sorted(item, key=lambda candidate: candidate.encode("ascii")):
                encoded_key = encode_string(key, label=f"{path} object key")
                encoded_value = encode(
                    item[key],
                    path=f"{path}/{key}",
                    depth=depth + 1,
                )
                encoded_items.append(encoded_key + b":" + encoded_value)
            return b"{" + b",".join(encoded_items) + b"}"
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
                f"{path}: semantic review subject integer is outside the safe range",
            )
            return str(item).encode("ascii")
        _fail(
            f"{path}: semantic review subject scalar type "
            f"{item_type.__name__!r} is outside the declared semantic domain"
        )

    try:
        return encode(value, path="$", depth=0)
    except UnicodeEncodeError as error:
        _fail(f"semantic review subject contains a non-ASCII object key: {error}")
    except RecursionError:
        _fail("semantic review subject exceeds the supported recursion bound")


def semantic_review_subject_commitment(
    canonical_source: dict[str, Any],
) -> dict[str, Any]:
    """Commit to every semantic scalar without creating an oracle hash cycle."""

    _require(
        isinstance(canonical_source, dict),
        "semantic review subject source must be an object",
    )
    _require(
        ALLOCATION_ORACLE_KEY in canonical_source,
        "semantic review subject requires the canonical allocation oracle",
    )
    _require(
        ALLOCATION_BINDING_KEY not in canonical_source,
        "semantic review subject cannot be computed from an authoring envelope",
    )
    projection = {
        key: value
        for key, value in canonical_source.items()
        if key not in SEMANTIC_REVIEW_SUBJECT_EXCLUDED_TOP_LEVEL_KEYS
    }
    raw = _semantic_review_subject_canonical_bytes(projection)
    _require(
        0 < len(raw) <= MAX_SEMANTIC_REVIEW_SUBJECT_BYTES,
        (f"semantic review subject bytes are outside the supported bound: {len(raw)}"),
    )
    digest = sha256()
    digest.update(SEMANTIC_REVIEW_SUBJECT_DOMAIN)
    digest.update(len(raw).to_bytes(8, "big"))
    digest.update(raw)
    return {
        **copy.deepcopy(SEMANTIC_REVIEW_SUBJECT_SUITE),
        "byte_length": len(raw),
        "sha256": digest.hexdigest(),
    }


def _rows_for_adr(
    rows: list[dict[str, Any]],
    adr_id: str,
) -> list[dict[str, Any]]:
    return [row for row in rows if row["adr_id"] == adr_id]


def validate_allocation_inventory(
    inventory: dict[str, Any],
    schema: dict[str, Any],
) -> None:
    """Validate the external inventory's closed shape and local invariants."""

    _assert_supported_schema(schema)
    _assert_no_mutable_aliases(inventory, label="allocation inventory")
    _closed_object(inventory, keys=INVENTORY_KEYS, label="allocation inventory")
    _validate_schema_instance(inventory, schema)
    _require(
        inventory["required_kinds"] == list(ALLOCATION_KINDS),
        "allocation inventory required_kinds must be exact and sorted",
    )
    _require(
        inventory["status"] in ALLOCATION_STATUSES,
        "allocation inventory has an invalid status",
    )
    _closed_object(
        inventory["document_row_commitment"],
        keys=DOCUMENT_ROW_COMMITMENT_KEYS,
        label="allocation inventory document_row_commitment",
    )
    _require(
        inventory["document_row_commitment"] == DOCUMENT_ROW_COMMITMENT,
        "allocation inventory has an unexpected document row commitment suite",
    )
    _require_positive_integer(
        inventory["model_allocation_count"],
        label="allocation inventory model_allocation_count",
    )
    _require(
        inventory["model_allocation_count"] <= MAX_ALLOCATION_ROWS,
        (f"allocation inventory model_allocation_count exceeds {MAX_ALLOCATION_ROWS}"),
    )
    _require_positive_integer(
        inventory["semantic_shape_entry_count"],
        label="allocation inventory semantic_shape_entry_count",
    )
    _require(
        inventory["semantic_shape_entry_count"] <= MAX_SEMANTIC_SHAPE_ROWS,
        (
            "allocation inventory semantic_shape_entry_count exceeds "
            f"{MAX_SEMANTIC_SHAPE_ROWS}"
        ),
    )
    allocation_review_profile = _closed_object(
        inventory["allocation_review_profile"],
        keys=ALLOCATION_REVIEW_PROFILE_KEYS,
        label="allocation inventory allocation_review_profile",
    )
    identity_commitment_suite = _closed_object(
        allocation_review_profile["allocation_identity_commitment_suite"],
        keys=set(ALLOCATION_IDENTITY_COMMITMENT_SUITE),
        label=(
            "allocation inventory allocation_review_profile."
            "allocation_identity_commitment_suite"
        ),
    )
    _require(
        identity_commitment_suite == ALLOCATION_IDENTITY_COMMITMENT_SUITE,
        "allocation inventory has an unexpected identity commitment suite",
    )
    semantic_shape_commitment_suite = _closed_object(
        allocation_review_profile["semantic_shape_commitment_suite"],
        keys=set(SEMANTIC_SHAPE_COMMITMENT_SUITE),
        label=(
            "allocation inventory allocation_review_profile."
            "semantic_shape_commitment_suite"
        ),
    )
    _require(
        semantic_shape_commitment_suite == SEMANTIC_SHAPE_COMMITMENT_SUITE,
        "allocation inventory has an unexpected semantic shape commitment suite",
    )
    _require(
        allocation_review_profile["schema"] == ALLOCATION_REVIEW_PROFILE_SCHEMA
        and allocation_review_profile["allocation_schema_id"] == INVENTORY_SCHEMA_ID
        and allocation_review_profile["model_projection_schema"]
        == MODEL_ALLOCATION_PROJECTION_SCHEMA
        and allocation_review_profile["model_origin_signal_projection_schema"]
        == MODEL_ORIGIN_SIGNAL_PROJECTION_SCHEMA
        and allocation_review_profile["resource_closure_schema"]
        == RESOURCE_CLOSURE_PROJECTION_SCHEMA
        and allocation_review_profile["semantic_shape_projection_schema"]
        == SEMANTIC_SHAPE_PROJECTION_SCHEMA,
        "allocation inventory has an unexpected allocation review profile suite",
    )
    _require(
        allocation_review_profile["required_kinds"] == list(ALLOCATION_KINDS),
        "allocation review profile has an unexpected allocation taxonomy",
    )
    _require(
        {
            "model_allocation_count": allocation_review_profile[
                "model_allocation_count"
            ],
            "model_allocation_sha256": allocation_review_profile[
                "model_allocation_sha256"
            ],
            "semantic_shape_entry_count": allocation_review_profile[
                "semantic_shape_entry_count"
            ],
            "semantic_shape_sha256": allocation_review_profile["semantic_shape_sha256"],
        }
        == {
            "model_allocation_count": inventory["model_allocation_count"],
            "model_allocation_sha256": inventory["model_allocation_sha256"],
            "semantic_shape_entry_count": inventory["semantic_shape_entry_count"],
            "semantic_shape_sha256": inventory["semantic_shape_sha256"],
        },
        "allocation review profile does not bind the maintained model metrics",
    )
    _require(
        isinstance(allocation_review_profile["allocation_schema_byte_length"], int)
        and not isinstance(
            allocation_review_profile["allocation_schema_byte_length"], bool
        )
        and 0
        < allocation_review_profile["allocation_schema_byte_length"]
        <= MAX_ALLOCATION_SCHEMA_BYTES,
        "allocation review profile has an invalid schema byte length",
    )
    _require(
        isinstance(allocation_review_profile["allocation_schema_sha256"], str)
        and SHA256_HEX.fullmatch(allocation_review_profile["allocation_schema_sha256"])
        is not None,
        "allocation review profile has an invalid schema SHA-256",
    )
    _require_positive_integer(
        allocation_review_profile["resource_closure_row_count"],
        label="allocation review profile resource_closure_row_count",
    )
    _require(
        isinstance(allocation_review_profile["resource_closure_sha256"], str)
        and SHA256_HEX.fullmatch(allocation_review_profile["resource_closure_sha256"])
        is not None,
        "allocation review profile has an invalid resource closure SHA-256",
    )
    _require_positive_integer(
        allocation_review_profile["model_origin_signal_row_count"],
        label="allocation review profile model_origin_signal_row_count",
    )
    _require(
        allocation_review_profile["model_origin_signal_row_count"]
        == allocation_review_profile["model_allocation_count"],
        "allocation review profile origin/signal rows do not cover every model unit",
    )
    _require(
        isinstance(allocation_review_profile["model_origin_signal_sha256"], str)
        and SHA256_HEX.fullmatch(
            allocation_review_profile["model_origin_signal_sha256"]
        )
        is not None,
        "allocation review profile has an invalid origin/signal SHA-256",
    )
    semantic_review_subject = _closed_object(
        inventory["semantic_review_subject"],
        keys=SEMANTIC_REVIEW_SUBJECT_KEYS,
        label="allocation inventory semantic_review_subject",
    )
    _require(
        {key: semantic_review_subject[key] for key in SEMANTIC_REVIEW_SUBJECT_SUITE}
        == SEMANTIC_REVIEW_SUBJECT_SUITE,
        "allocation inventory has an unexpected semantic review subject suite",
    )
    _require_positive_integer(
        semantic_review_subject["byte_length"],
        label="allocation inventory semantic_review_subject.byte_length",
    )
    _require(
        semantic_review_subject["byte_length"] <= MAX_SEMANTIC_REVIEW_SUBJECT_BYTES,
        (
            "allocation inventory semantic review subject exceeds "
            f"{MAX_SEMANTIC_REVIEW_SUBJECT_BYTES} bytes"
        ),
    )
    _require(
        isinstance(semantic_review_subject["sha256"], str)
        and SHA256_HEX.fullmatch(semantic_review_subject["sha256"]) is not None,
        "allocation inventory has an invalid semantic review subject SHA-256",
    )

    allocations = inventory["allocations"]
    documents = inventory["documents"]
    exclusions = inventory["exclusions"]
    _require(
        len(allocations) + len(exclusions) <= MAX_ALLOCATION_ROWS,
        (
            "allocation and exclusion rows exceed the combined "
            f"{MAX_ALLOCATION_ROWS} row bound"
        ),
    )
    provenance_review = _closed_object(
        inventory["provenance_review"],
        keys=PROVENANCE_REVIEW_KEYS,
        label="allocation inventory provenance_review",
    )
    _require(
        {key: provenance_review[key] for key in PROVENANCE_REVIEW_SUITE}
        == PROVENANCE_REVIEW_SUITE,
        "allocation inventory has an unexpected provenance review suite",
    )
    _require(
        provenance_review["status"] in PROVENANCE_REVIEW_STATUSES,
        "allocation inventory has an unknown provenance review status",
    )
    _require(
        SHA256_HEX.fullmatch(provenance_review["reviewed_assignment_sha256"])
        is not None,
        "allocation inventory has an invalid reviewed assignment SHA-256",
    )
    expected_review_digest = (
        provenance_assignment_sha256(
            documents,
            allocations,
            exclusions,
            allocation_review_profile,
            semantic_review_subject,
        )
        if provenance_review["status"] == "REVIEWED"
        else "0" * 64
    )
    _require(
        provenance_review["reviewed_assignment_sha256"] == expected_review_digest,
        "allocation inventory provenance review does not bind the exact rows",
    )
    _require(
        inventory["status"] != "COMPLETE" or provenance_review["status"] == "REVIEWED",
        "allocation inventory cannot be complete before provenance review",
    )

    _require(
        [item.get("path") for item in documents] == list(ADR_ALLOCATION_PATHS),
        "allocation inventory has an unexpected ADR path inventory",
    )
    _require(
        [item.get("adr_id") for item in documents]
        == [f"ADR-{index:03d}" for index in range(1, 12)],
        "allocation inventory has an unexpected ADR ID inventory",
    )
    _require(
        [item.get("allocation_anchor_id") for item in documents]
        == list(ADR_ALLOCATION_ANCHOR_IDS),
        "allocation inventory has an unexpected stable ADR anchor inventory",
    )
    _require(
        [
            tuple(
                module.get("path")
                for module in item.get("modules", [])
                if isinstance(module, dict)
            )
            for item in documents
        ]
        == list(ADR_ALLOCATION_MODULE_PATHS),
        "allocation inventory has an unexpected ordered ADR module inventory",
    )
    document_corpus_bytes = 0
    source_paths: list[str] = []
    for index, document in enumerate(documents):
        label = f"allocation inventory documents[{index}]"
        _closed_object(document, keys=DOCUMENT_KEYS, label=label)
        adr_id = document["adr_id"]
        _require(
            ADR_ID.fullmatch(adr_id) is not None,
            f"{label}: invalid ADR ID",
        )
        _require(
            document["allocation_anchor_id"] == ADR_ALLOCATION_ANCHOR_BY_ID[adr_id],
            f"{label}: anchor is not the stable anchor for {adr_id}",
        )
        _require(
            isinstance(document["allocation_row_count"], int)
            and not isinstance(document["allocation_row_count"], bool)
            and 0 <= document["allocation_row_count"] <= MAX_ALLOCATION_ROWS,
            f"{label}: invalid allocation row count",
        )
        _require(
            isinstance(document["exclusion_row_count"], int)
            and not isinstance(document["exclusion_row_count"], bool)
            and 0 <= document["exclusion_row_count"] <= MAX_ALLOCATION_ROWS,
            f"{label}: invalid exclusion row count",
        )
        _require_positive_integer(document["byte_length"], label=f"{label}.byte_length")
        _require(
            document["byte_length"] <= MAX_ADR_DOCUMENT_BYTES,
            f"{label}: byte length exceeds {MAX_ADR_DOCUMENT_BYTES}",
        )
        document_corpus_bytes += document["byte_length"]
        for key in (
            "allocation_rows_sha256",
            "exclusion_rows_sha256",
            "sha256",
        ):
            _require(
                SHA256_HEX.fullmatch(document[key]) is not None,
                f"{label}.{key}: invalid SHA-256",
            )
        path = Path(document["path"])
        _require(
            not path.is_absolute() and ".." not in path.parts,
            f"{label}: path escapes the repository",
        )
        source_paths.append(document["path"])
        modules = document["modules"]
        _require(
            isinstance(modules, list) and len(modules) <= MAX_ADR_MODULES_PER_DOCUMENT,
            (f"{label}: module count exceeds {MAX_ADR_MODULES_PER_DOCUMENT}"),
        )
        _require(
            tuple(module.get("path") for module in modules)
            == ADR_ALLOCATION_MODULE_PATHS[index],
            f"{label}: ordered module paths do not match {adr_id}",
        )
        for module_index, module in enumerate(modules):
            module_label = f"{label}.modules[{module_index}]"
            _closed_object(module, keys=DOCUMENT_MODULE_KEYS, label=module_label)
            _require_positive_integer(
                module["byte_length"],
                label=f"{module_label}.byte_length",
            )
            _require(
                module["byte_length"] <= MAX_ADR_DOCUMENT_BYTES,
                (f"{module_label}: byte length exceeds {MAX_ADR_DOCUMENT_BYTES}"),
            )
            _require(
                SHA256_HEX.fullmatch(module["sha256"]) is not None,
                f"{module_label}.sha256: invalid SHA-256",
            )
            module_path = Path(module["path"])
            _require(
                not module_path.is_absolute() and ".." not in module_path.parts,
                f"{module_label}: path escapes the repository",
            )
            source_paths.append(module["path"])
            document_corpus_bytes += module["byte_length"]
        source_set = _closed_object(
            document["source_set"],
            keys=DOCUMENT_SOURCE_SET_KEYS,
            label=f"{label}.source_set",
        )
        _require(
            {key: source_set[key] for key in ADR_SOURCE_SET_SUITE}
            == ADR_SOURCE_SET_SUITE,
            f"{label}: source-set commitment suite is not supported",
        )
        _require(
            SHA256_HEX.fullmatch(source_set["sha256"]) is not None,
            f"{label}.source_set.sha256: invalid SHA-256",
        )
        _require(
            source_set["sha256"]
            == adr_source_set_sha256(
                adr_id=adr_id,
                path=document["path"],
                byte_length=document["byte_length"],
                source_sha256=document["sha256"],
                modules=modules,
            ),
            f"{label}: source-set digest does not bind the ordered sources",
        )
        allocation_rows = _rows_for_adr(allocations, adr_id)
        exclusion_rows = _rows_for_adr(exclusions, adr_id)
        _require(
            document["allocation_row_count"] == len(allocation_rows),
            f"{label}: allocation row count does not match the external rows",
        )
        _require(
            document["allocation_rows_sha256"]
            == document_rows_sha256(
                allocation_rows,
                row_kind="allocations",
            ),
            f"{label}: allocation row digest does not match the external rows",
        )
        _require(
            document["exclusion_row_count"] == len(exclusion_rows),
            f"{label}: exclusion row count does not match the external rows",
        )
        _require(
            document["exclusion_rows_sha256"]
            == document_rows_sha256(
                exclusion_rows,
                row_kind="exclusions",
            ),
            f"{label}: exclusion row digest does not match the external rows",
        )
    _require(
        len(source_paths) == len(set(source_paths)),
        "allocation inventory aliases one ADR source path more than once",
    )
    _require(
        document_corpus_bytes <= MAX_ADR_CORPUS_BYTES,
        (f"allocation inventory ADR corpus exceeds {MAX_ADR_CORPUS_BYTES} bytes"),
    )

    allocation_order: list[tuple[str, str, str, str, str, str]] = []
    model_rows: list[tuple[str, str, str, str]] = []
    unit_ids: list[str] = []
    allocation_identifiers: list[tuple[str, str]] = []
    for index, allocation in enumerate(allocations):
        label = f"allocation inventory allocations[{index}]"
        _closed_object(allocation, keys=ALLOCATION_ROW_KEYS, label=label)
        adr_id = allocation["adr_id"]
        exact_name = allocation["exact_name"]
        kind = allocation["kind"]
        semantic_ref = allocation["semantic_ref"]
        unit_id = allocation["unit_id"]
        _require(ADR_ID.fullmatch(adr_id) is not None, f"{label}: invalid ADR ID")
        _validate_allocation_identity_fields(
            kind,
            exact_name,
            semantic_ref,
            unit_id,
            label=label,
        )
        _require(
            allocation["source_anchor"] == ADR_ALLOCATION_ANCHOR_BY_ID.get(adr_id),
            f"{label}: source anchor does not match the stable ADR anchor",
        )
        allocation_order.append(
            (
                adr_id,
                allocation["source_anchor"],
                kind,
                exact_name,
                semantic_ref,
                unit_id,
            )
        )
        model_rows.append((kind, exact_name, semantic_ref, unit_id))
        unit_ids.append(unit_id)
        allocation_identifiers.append((adr_id, exact_name))
    _require(
        allocation_order == sorted(allocation_order),
        "allocation inventory rows are not in canonical provenance order",
    )
    _require(
        len(model_rows) == len(set(model_rows)),
        "allocation inventory contains duplicate model rows",
    )
    _require(
        len(unit_ids) == len(set(unit_ids)),
        "allocation inventory contains duplicate unit IDs",
    )
    exclusion_order: list[tuple[str, str, str, str]] = []
    exclusion_identifiers: list[tuple[str, str]] = []
    for index, exclusion in enumerate(exclusions):
        label = f"allocation inventory exclusions[{index}]"
        _closed_object(exclusion, keys=EXCLUSION_ROW_KEYS, label=label)
        adr_id = exclusion["adr_id"]
        exact_name = exclusion["exact_name"]
        classification = exclusion["classification"]
        reason = exclusion["reason"]
        _require(ADR_ID.fullmatch(adr_id) is not None, f"{label}: invalid ADR ID")
        _require(
            EXACT_NAME.fullmatch(exact_name) is not None,
            f"{label}: invalid exact name",
        )
        _require(
            classification in EXCLUSION_CLASSIFICATIONS,
            f"{label}: invalid classification",
        )
        _require(
            isinstance(reason, str)
            and reason == reason.strip()
            and bool(reason)
            and len(reason) <= MAX_EXCLUSION_REASON_CHARS,
            f"{label}: reason must be nonempty, trimmed, and bounded",
        )
        _require(
            exclusion["source_anchor"] == ADR_ALLOCATION_ANCHOR_BY_ID.get(adr_id),
            f"{label}: source anchor does not match the stable ADR anchor",
        )
        exclusion_order.append(
            (
                adr_id,
                exclusion["source_anchor"],
                exact_name,
                classification,
            )
        )
        exclusion_identifiers.append((adr_id, exact_name))
    _require(
        exclusion_order == sorted(exclusion_order),
        "allocation exclusions are not in canonical provenance order",
    )
    _require(
        len(exclusion_identifiers) == len(set(exclusion_identifiers)),
        "allocation inventory contains duplicate exclusion identifiers",
    )
    overlap = set(allocation_identifiers) & set(exclusion_identifiers)
    _require(
        not overlap,
        (
            "allocation inventory classifies identifiers as both allocated "
            f"and excluded: {sorted(overlap)[:3]}"
        ),
    )


def inventory_bytes(inventory: dict[str, Any]) -> bytes:
    raw = canonical_bytes(inventory) + b"\n"
    _require(
        len(raw) <= MAX_ALLOCATION_INVENTORY_BYTES,
        (f"allocation inventory exceeds {MAX_ALLOCATION_INVENTORY_BYTES} bytes"),
    )
    return raw


def validate_allocation_review_profile_schema_binding(
    inventory: dict[str, Any],
    schema_raw: bytes,
) -> None:
    """Require the reviewed projection profile to bind the exact schema bytes."""

    profile = inventory["allocation_review_profile"]
    _require(
        profile["allocation_schema_byte_length"] == len(schema_raw)
        and profile["allocation_schema_sha256"] == sha256(schema_raw).hexdigest(),
        "allocation review profile does not bind the exact allocation schema",
    )


def inventory_to_oracle(inventory: dict[str, Any]) -> dict[str, Any]:
    _closed_object(inventory, keys=INVENTORY_KEYS, label="allocation inventory")
    return copy.deepcopy({key: inventory[key] for key in sorted(ORACLE_KEYS)})


def oracle_to_inventory(oracle: dict[str, Any]) -> dict[str, Any]:
    _closed_object(oracle, keys=ORACLE_KEYS, label="ADR allocation oracle")
    return {
        "$schema": INVENTORY_SCHEMA_FILE,
        "allocation_review_profile": copy.deepcopy(oracle["allocation_review_profile"]),
        "allocations": copy.deepcopy(oracle["allocations"]),
        "candidate": "1.0.0-rc.1",
        "claim_boundary": oracle["claim_boundary"],
        "document_row_commitment": copy.deepcopy(oracle["document_row_commitment"]),
        "documents": copy.deepcopy(oracle["documents"]),
        "exclusions": copy.deepcopy(oracle["exclusions"]),
        "model_allocation_count": oracle["model_allocation_count"],
        "model_allocation_sha256": oracle["model_allocation_sha256"],
        "normative": False,
        "provenance_review": copy.deepcopy(oracle["provenance_review"]),
        "required_kinds": copy.deepcopy(oracle["required_kinds"]),
        "schema": INVENTORY_SCHEMA_ID,
        "semantic_review_subject": copy.deepcopy(oracle["semantic_review_subject"]),
        "semantic_shape_entry_count": oracle["semantic_shape_entry_count"],
        "semantic_shape_sha256": oracle["semantic_shape_sha256"],
        "status": oracle["status"],
        "task": "B01",
    }


def validate_inventory_binding(binding: Any) -> dict[str, Any]:
    binding = _closed_object(
        binding,
        keys=BINDING_KEYS,
        label="allocation inventory binding",
    )
    _require(
        binding["authoring_file"] == INVENTORY_FILE,
        "allocation inventory binding has an unexpected authoring file",
    )
    _require(
        binding["schema_file"] == INVENTORY_SCHEMA_FILE,
        "allocation inventory binding has an unexpected schema file",
    )
    _require(
        binding["schema_id"] == INVENTORY_SCHEMA_ID,
        "allocation inventory binding has an unexpected schema ID",
    )
    _require(
        binding["canonicalization"] == INVENTORY_CANONICALIZATION,
        "allocation inventory binding has an unexpected canonicalization",
    )
    for key, maximum in (
        ("authoring_byte_length", MAX_ALLOCATION_INVENTORY_BYTES),
        ("schema_byte_length", MAX_ALLOCATION_SCHEMA_BYTES),
    ):
        value = binding[key]
        _require(
            isinstance(value, int)
            and not isinstance(value, bool)
            and 0 < value <= maximum,
            f"allocation inventory binding has an invalid {key}",
        )
    for key in ("authoring_sha256", "schema_sha256"):
        _require(
            isinstance(binding[key], str)
            and SHA256_HEX.fullmatch(binding[key]) is not None,
            f"allocation inventory binding has an invalid {key}",
        )
    return binding


def build_inventory_binding(
    inventory_raw: bytes,
    schema_raw: bytes,
) -> dict[str, Any]:
    _require(
        0 < len(inventory_raw) <= MAX_ALLOCATION_INVENTORY_BYTES,
        "allocation inventory bytes are outside the supported bound",
    )
    _require(
        0 < len(schema_raw) <= MAX_ALLOCATION_SCHEMA_BYTES,
        "allocation inventory schema bytes are outside the supported bound",
    )
    return {
        "authoring_byte_length": len(inventory_raw),
        "authoring_file": INVENTORY_FILE,
        "authoring_sha256": sha256(inventory_raw).hexdigest(),
        "canonicalization": INVENTORY_CANONICALIZATION,
        "schema_byte_length": len(schema_raw),
        "schema_file": INVENTORY_SCHEMA_FILE,
        "schema_id": INVENTORY_SCHEMA_ID,
        "schema_sha256": sha256(schema_raw).hexdigest(),
    }


def _require_regular_directory(path: Path) -> None:
    try:
        mode = path.lstat().st_mode
    except OSError as error:
        _fail(f"cannot inspect allocation inventory directory {path}: {error}")
    _require(
        stat.S_ISDIR(mode) and not stat.S_ISLNK(mode),
        f"allocation inventory directory must be a non-symlink directory: {path}",
    )


def _require_distinct_files(left: Path, right: Path) -> None:
    try:
        if left.exists() and right.exists():
            _require(
                not os.path.samefile(left, right),
                "allocation inventory and schema must be distinct files",
            )
    except OSError as error:
        _fail(f"cannot compare allocation inventory path identities: {error}")


def load_bound_allocation_inventory(
    base_directory: Path,
    binding: dict[str, Any],
) -> AllocationInventorySnapshot:
    """Load exact sibling files bound by the selector authoring source."""

    validated_binding = validate_inventory_binding(binding)
    _require_regular_directory(base_directory)
    inventory_path = base_directory / INVENTORY_FILE
    schema_path = base_directory / INVENTORY_SCHEMA_FILE
    _require_distinct_files(inventory_path, schema_path)
    schema_raw, schema = load_inventory_schema(schema_path)
    inventory_raw = read_bounded_regular_file(
        inventory_path,
        maximum_bytes=MAX_ALLOCATION_INVENTORY_BYTES,
        label="selector allocation authoring inventory",
    )
    _require(
        len(schema_raw) == validated_binding["schema_byte_length"],
        "allocation inventory schema byte length does not match its binding",
    )
    _require(
        sha256(schema_raw).hexdigest() == validated_binding["schema_sha256"],
        "allocation inventory schema digest does not match its binding",
    )
    _require(
        len(inventory_raw) == validated_binding["authoring_byte_length"],
        "allocation inventory byte length does not match its binding",
    )
    _require(
        sha256(inventory_raw).hexdigest() == validated_binding["authoring_sha256"],
        "allocation inventory digest does not match its binding",
    )
    inventory = parse_json_bytes(inventory_raw, label=str(inventory_path))
    _require(isinstance(inventory, dict), "allocation inventory must be an object")
    _require(
        inventory_raw == inventory_bytes(inventory),
        (
            "allocation inventory is not canonical JSON with exactly one "
            "trailing newline"
        ),
    )
    validate_allocation_inventory(inventory, schema)
    validate_allocation_review_profile_schema_binding(inventory, schema_raw)
    snapshot = AllocationInventorySnapshot(
        base_directory=base_directory,
        binding=copy.deepcopy(validated_binding),
        inventory=inventory,
        inventory_path=inventory_path,
        inventory_raw=inventory_raw,
        oracle=inventory_to_oracle(inventory),
        schema_path=schema_path,
        schema_raw=schema_raw,
    )
    verify_inventory_snapshot_unchanged(snapshot)
    return snapshot


def verify_inventory_snapshot_unchanged(
    snapshot: AllocationInventorySnapshot,
) -> None:
    current_schema = read_bounded_regular_file(
        snapshot.schema_path,
        maximum_bytes=MAX_ALLOCATION_SCHEMA_BYTES,
        label="selector allocation schema stability check",
    )
    current_inventory = read_bounded_regular_file(
        snapshot.inventory_path,
        maximum_bytes=MAX_ALLOCATION_INVENTORY_BYTES,
        label="selector allocation inventory stability check",
    )
    _require(
        current_schema == snapshot.schema_raw,
        "allocation inventory schema changed during use",
    )
    _require(
        current_inventory == snapshot.inventory_raw,
        "allocation inventory changed during use",
    )


def _refresh_document_source_set(document: dict[str, Any]) -> None:
    document["source_set"] = copy.deepcopy(ADR_SOURCE_SET_SUITE)
    document["source_set"]["sha256"] = adr_source_set_sha256(
        adr_id=document["adr_id"],
        path=document["path"],
        byte_length=document["byte_length"],
        source_sha256=document["sha256"],
        modules=document["modules"],
    )


def _sample_document(
    *,
    index: int,
    path: str,
    allocation_rows_sha256: str,
    exclusion_rows_sha256: str,
) -> dict[str, Any]:
    adr_id = f"ADR-{index:03d}"
    modules = [
        {
            "byte_length": 1,
            "path": module_path,
            "sha256": "0" * 64,
        }
        for module_path in ADR_ALLOCATION_MODULE_PATHS[index - 1]
    ]
    document = {
        "adr_id": adr_id,
        "allocation_anchor_id": ADR_ALLOCATION_ANCHOR_IDS[index - 1],
        "allocation_row_count": 0,
        "allocation_rows_sha256": allocation_rows_sha256,
        "byte_length": 1,
        "exclusion_row_count": 0,
        "exclusion_rows_sha256": exclusion_rows_sha256,
        "modules": modules,
        "path": path,
        "sha256": "0" * 64,
    }
    _refresh_document_source_set(document)
    return document


def _sample_inventory(schema_raw: bytes) -> dict[str, Any]:
    empty_allocation_digest = document_rows_sha256(
        [],
        row_kind="allocations",
    )
    empty_exclusion_digest = document_rows_sha256(
        [],
        row_kind="exclusions",
    )
    return {
        "$schema": INVENTORY_SCHEMA_FILE,
        "allocation_review_profile": build_allocation_review_profile(
            allocation_schema_raw=schema_raw,
            model_allocation_count=1,
            model_allocation_sha256="0" * 64,
            model_origin_signal_row_count=1,
            model_origin_signal_sha256="0" * 64,
            resource_closure_row_count=1,
            resource_closure_sha256="0" * 64,
            semantic_shape_entry_count=1,
            semantic_shape_sha256="0" * 64,
        ),
        "allocations": [],
        "candidate": "1.0.0-rc.1",
        "claim_boundary": INVENTORY_CLAIM_BOUNDARY,
        "document_row_commitment": copy.deepcopy(DOCUMENT_ROW_COMMITMENT),
        "documents": [
            _sample_document(
                index=index,
                path=path,
                allocation_rows_sha256=empty_allocation_digest,
                exclusion_rows_sha256=empty_exclusion_digest,
            )
            for index, path in enumerate(ADR_ALLOCATION_PATHS, 1)
        ],
        "exclusions": [],
        "model_allocation_count": 1,
        "model_allocation_sha256": "0" * 64,
        "normative": False,
        "provenance_review": build_not_reviewed_provenance_review(),
        "required_kinds": list(ALLOCATION_KINDS),
        "schema": INVENTORY_SCHEMA_ID,
        "semantic_review_subject": {
            **copy.deepcopy(SEMANTIC_REVIEW_SUBJECT_SUITE),
            "byte_length": 1,
            "sha256": "0" * 64,
        },
        "semantic_shape_entry_count": 1,
        "semantic_shape_sha256": "0" * 64,
        "status": "INCOMPLETE_FAIL_CLOSED",
        "task": "B01",
    }


def _sample_allocation_row(
    *,
    adr_id: str,
    exact_name: str,
    kind: str,
    semantic_ref: str,
) -> dict[str, Any]:
    """Build one self-test row with a derived, never caller-selected unit ID."""

    return {
        "adr_id": adr_id,
        "exact_name": exact_name,
        "kind": kind,
        "semantic_ref": semantic_ref,
        "source_anchor": ADR_ALLOCATION_ANCHOR_BY_ID[adr_id],
        "unit_id": allocation_unit_id(kind, exact_name, semantic_ref),
    }


def _write_exact(path: Path, raw: bytes) -> None:
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o600,
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


def _expect_rejection(action: Any, label: str) -> None:
    try:
        action()
    except (SelectorAllocationInventoryError, SelectorClosureCodecError):
        return
    _fail(f"allocation inventory self-test accepted {label}")


def run_self_test(schema_path: Path = DEFAULT_SCHEMA) -> int:
    """Exercise hostile canonicality, provenance, alias, race, and bound cases."""

    schema_raw, schema = load_inventory_schema(schema_path)
    sample = _sample_inventory(schema_raw)
    validate_allocation_inventory(sample, schema)
    _require(
        sample["documents"][0]["allocation_rows_sha256"]
        != sample["documents"][0]["exclusion_rows_sha256"],
        "allocation and exclusion row commitment domains collide",
    )
    _require(
        oracle_to_inventory(inventory_to_oracle(sample)) == sample,
        "allocation inventory oracle round trip changed the source",
    )
    canonical = inventory_bytes(sample)
    binding = build_inventory_binding(canonical, schema_raw)
    cases = 3

    identity_vector = ALLOCATION_IDENTITY_COMMITMENT_SUITE["fixed_vectors"][
        "unit_model_origin"
    ]
    sample_identity = allocation_identity_projection(*identity_vector["identity_input"])
    _require(
        sample_identity == identity_vector["expected_identity_projection"]
        and sample_identity[3] == identity_vector["expected_unit_id"],
        "allocation unit ID changed its fixed owner-free self-test vector",
    )
    _require(
        model_allocation_projection_sha256(identity_vector["model_projection_input"])
        == identity_vector["expected_model_projection_sha256"],
        "model allocation projection changed its fixed v4 self-test vector",
    )
    for hostile_rows, label in (
        ([sample_identity[:-1]], "model row with missing unit ID"),
        ([sample_identity + ["unknown"]], "open-shaped model row"),
        (
            [[*sample_identity[:-1], "f" * 64]],
            "model row with forged unit ID",
        ),
        ([sample_identity, copy.deepcopy(sample_identity)], "duplicate model unit ID"),
        (
            [
                allocation_identity_projection(
                    "UNKNOWN",
                    "SampleType",
                    "sample-type::SampleType",
                )
            ],
            "model row with unknown kind",
        ),
    ):
        _expect_rejection(
            lambda value=hostile_rows: model_allocation_projection_sha256(value),
            label,
        )
        cases += 1
    sample_origin_row = copy.deepcopy(
        identity_vector["origin_signal_projection_input"][0]
    )
    _require(
        model_origin_signal_projection_commitment(
            identity_vector["origin_signal_projection_input"]
        )
        == (
            identity_vector["expected_origin_signal_row_count"],
            identity_vector["expected_origin_signal_sha256"],
        ),
        "origin/signal projection changed its fixed self-test vector",
    )
    cases += 3

    multi_evidence_row = copy.deepcopy(sample_origin_row)
    multi_evidence_row["origins"].append(
        {
            "evidence_kind": "STRUCTURAL_PROFILE_DEFINITION",
            "semantic_location": "json-pointer::/sample_profile",
        }
    )
    multi_evidence_row["signals"] = [
        {
            "evidence_kind": "STRUCTURAL_PROFILE_REFERENCE",
            "semantic_location": "profile-reference::SAMPLE_PROFILE",
        },
        {
            "evidence_kind": "SELECTOR_USAGE",
            "semantic_location": "selector-id::SAMPLE",
        },
    ]
    reversed_evidence_row = copy.deepcopy(multi_evidence_row)
    reversed_evidence_row["origins"].reverse()
    reversed_evidence_row["signals"].reverse()
    _require(
        model_origin_signal_projection_commitment([multi_evidence_row])
        == model_origin_signal_projection_commitment([reversed_evidence_row]),
        "origin/signal projection depends on nested evidence order",
    )
    cases += 1

    for mutate, label in (
        (
            lambda value: value["origins"].clear(),
            "unit without a mechanical origin",
        ),
        (
            lambda value: value["origins"].append(copy.deepcopy(value["origins"][0])),
            "duplicate origin evidence",
        ),
        (
            lambda value: value["signals"].append(
                {
                    "evidence_kind": "UNKNOWN",
                    "semantic_location": "selector-id::SAMPLE",
                }
            ),
            "unknown signal evidence kind",
        ),
        (
            lambda value: value.__setitem__("unknown", True),
            "open-shaped evidence row",
        ),
        (
            lambda value: value.__setitem__("unit_id", "f" * 64),
            "forged evidence unit ID",
        ),
        (
            lambda value: value["origins"][0].__setitem__(
                "semantic_location",
                "artifact-ref::sample-type::SampleType\N{SNOWMAN}",
            ),
            "Unicode evidence location",
        ),
        (
            lambda value: value["origins"][0].__setitem__(
                "semantic_location",
                " artifact-ref::sample-type::SampleType",
            ),
            "noncanonical padded evidence location",
        ),
        (
            lambda value: value["origins"][0].__setitem__(
                "semantic_location",
                "artifact-ref::sample-type::SampleType\n",
            ),
            "control character in evidence location",
        ),
    ):
        hostile_evidence_row = copy.deepcopy(sample_origin_row)
        mutate(hostile_evidence_row)
        _expect_rejection(
            lambda value=hostile_evidence_row: (
                model_origin_signal_projection_commitment([value])
            ),
            label,
        )
        cases += 1

    subject_source = {
        "adr_allocation_oracle": {"transport_only": "first"},
        "adversarial_probe_bindings": {"receipt": "first"},
        "closure_commitments": {"derived": "first"},
        "generated_by": "first-generator",
        "generated_view": "first-view",
        "semantic_model": {"branch_id": "FIRST", "limit": 1},
    }
    subject_commitment = semantic_review_subject_commitment(subject_source)
    subject_vector = SEMANTIC_REVIEW_SUBJECT_SUITE["fixed_vectors"]["semantic_model"]
    fixed_subject_commitment = semantic_review_subject_commitment(
        subject_vector["input"]
    )
    _require(
        (
            fixed_subject_commitment["byte_length"],
            fixed_subject_commitment["sha256"],
        )
        == (
            subject_vector["expected_byte_length"],
            subject_vector["expected_sha256"],
        )
        and subject_commitment == fixed_subject_commitment,
        "semantic review subject changed its fixed domain/framing vector",
    )
    _require(
        _semantic_review_subject_canonical_bytes(
            subject_vector["expected_projection"]
        ).hex()
        == subject_vector["expected_canonical_utf8_hex"],
        "semantic review subject changed its artifact-declared canonical bytes",
    )
    reordered_subject_source = {
        "semantic_model": {"limit": 1, "branch_id": "FIRST"},
        "generated_view": "second-view",
        "generated_by": "second-generator",
        "closure_commitments": {"derived": "second"},
        "adversarial_probe_bindings": {"receipt": "second"},
        "adr_allocation_oracle": {"transport_only": "second"},
    }
    _require(
        semantic_review_subject_commitment(reordered_subject_source)
        == subject_commitment,
        (
            "semantic review subject binds insertion order or an explicitly "
            "excluded transport field"
        ),
    )
    renamed_subject_source = copy.deepcopy(subject_source)
    renamed_subject_source["semantic_model"]["branch_id"] = "RENAMED"
    _require(
        semantic_review_subject_commitment(renamed_subject_source)
        != subject_commitment,
        "semantic review subject ignored a scalar semantic rename",
    )
    cases += 3
    subject_depth_vector = SEMANTIC_REVIEW_SUBJECT_SUITE["fixed_vectors"][
        "nesting_depth_boundary"
    ]
    _require(
        subject_depth_vector["root_depth"] == 0,
        "semantic review subject fixed-vector root depth changed",
    )

    def subject_depth_projection(array_wrapper_count: int) -> dict[str, Any]:
        nested: Any = None
        for _ in range(array_wrapper_count):
            nested = [nested]
        return {"x": nested}

    maximum_depth_projection = subject_depth_projection(
        subject_depth_vector["maximum_accepted_array_wrapper_count"]
    )
    maximum_depth_raw = _semantic_review_subject_canonical_bytes(
        maximum_depth_projection
    )
    _require(
        len(maximum_depth_raw)
        == subject_depth_vector["expected_accepted_canonical_utf8_byte_length"]
        and maximum_depth_raw.hex()
        == subject_depth_vector["expected_accepted_canonical_utf8_hex"],
        "semantic review subject maximum-depth canonical vector changed",
    )
    maximum_depth_digest = sha256()
    maximum_depth_digest.update(SEMANTIC_REVIEW_SUBJECT_DOMAIN)
    maximum_depth_digest.update(len(maximum_depth_raw).to_bytes(8, "big"))
    maximum_depth_digest.update(maximum_depth_raw)
    _require(
        maximum_depth_digest.hexdigest()
        == subject_depth_vector["expected_accepted_sha256"],
        "semantic review subject maximum-depth digest vector changed",
    )
    maximum_depth_commitment = semantic_review_subject_commitment(
        {
            ALLOCATION_ORACLE_KEY: {},
            **maximum_depth_projection,
        }
    )
    _require(
        maximum_depth_commitment["byte_length"]
        == subject_depth_vector["expected_accepted_canonical_utf8_byte_length"]
        and maximum_depth_commitment["sha256"]
        == subject_depth_vector["expected_accepted_sha256"],
        "semantic review subject maximum-depth end-to-end vector changed",
    )
    _expect_rejection(
        lambda: _semantic_review_subject_canonical_bytes(
            subject_depth_projection(
                subject_depth_vector["first_rejected_array_wrapper_count"]
            )
        ),
        "semantic review subject first depth beyond the declared maximum",
    )
    cases += 5
    authoring_subject_source = copy.deepcopy(subject_source)
    authoring_subject_source.pop(ALLOCATION_ORACLE_KEY)
    authoring_subject_source[ALLOCATION_BINDING_KEY] = {}
    _expect_rejection(
        lambda: semantic_review_subject_commitment(authoring_subject_source),
        "semantic review subject computed from an authoring envelope",
    )
    cases += 1
    _require(
        _semantic_review_subject_canonical_bytes(
            {"z": [None, False, True, -1, 0, 1, 'a"b\\c'], "a": {}}
        )
        == b'{"a":{},"z":[null,false,true,-1,0,1,"a\\"b\\\\c"]}',
        "semantic review subject canonical codec changed its fixed self-test vector",
    )
    for hostile_value, label in (
        ({"semantic_model": {"value": -0.0}}, "negative-zero float"),
        ({"semantic_model": {"value": 1.0}}, "integral float"),
        (
            {"semantic_model": {"value": 9_007_199_254_740_992}},
            "integer outside the cross-language safe range",
        ),
        ({"semantic_model": {"value": "non-ASCII \N{SNOWMAN}"}}, "Unicode scalar"),
        ({"semantic_model": {"value": "line\nbreak"}}, "control character"),
        ({"semantic_model": {"non\N{SNOWMAN}": "key"}}, "Unicode object key"),
    ):
        hostile_source = copy.deepcopy(subject_source)
        hostile_source.update(hostile_value)
        _expect_rejection(
            lambda value=hostile_source: semantic_review_subject_commitment(value),
            f"semantic review subject {label}",
        )
    cases += 7

    _expect_rejection(
        lambda: document_rows_sha256([], row_kind=""),
        "default document row commitment kind",
    )
    cases += 1
    document_vectors = DOCUMENT_ROW_COMMITMENT["fixed_vectors"]
    _require(
        all(
            document_rows_sha256(
                vector["rows"],
                row_kind=vector["row_kind"],
            )
            == vector["expected_sha256"]
            for vector in (
                document_vectors["empty_allocations"],
                document_vectors["empty_exclusions"],
                document_vectors["nonempty_allocation"],
                document_vectors["nonempty_exclusion"],
            )
        ),
        "document row commitments changed their fixed framing vectors",
    )
    _require(
        all(
            len(canonical_bytes(vector["rows"]))
            == vector["expected_canonical_rows_byte_length"]
            and canonical_bytes(vector["rows"]).hex()
            == vector["expected_canonical_rows_utf8_hex"]
            for vector in (
                document_vectors["nonempty_allocation"],
                document_vectors["nonempty_exclusion"],
            )
        ),
        "document row commitments changed their nonempty canonical row vectors",
    )
    cases += 2

    with tempfile.TemporaryDirectory(
        prefix="ncp-selector-allocation-self-test-"
    ) as directory_name:
        directory = Path(directory_name).resolve(strict=True)
        inventory_path = directory / INVENTORY_FILE
        copied_schema_path = directory / INVENTORY_SCHEMA_FILE
        _write_exact(inventory_path, canonical)
        _write_exact(copied_schema_path, schema_raw)
        snapshot = load_bound_allocation_inventory(directory, binding)
        _require(
            snapshot.oracle == inventory_to_oracle(sample),
            "allocation inventory self-test changed the oracle projection",
        )

        noncanonical_path = directory / "noncanonical"
        noncanonical_path.mkdir()
        _write_exact(
            noncanonical_path / INVENTORY_SCHEMA_FILE,
            schema_raw,
        )
        pretty = json.dumps(sample, indent=2, sort_keys=True).encode("utf-8") + b"\n"
        _write_exact(noncanonical_path / INVENTORY_FILE, pretty)
        pretty_binding = build_inventory_binding(pretty, schema_raw)
        _expect_rejection(
            lambda: load_bound_allocation_inventory(
                noncanonical_path,
                pretty_binding,
            ),
            "noncanonical inventory bytes",
        )
        cases += 1

        duplicate_key_path = directory / "duplicate-key"
        duplicate_key_path.mkdir()
        _write_exact(
            duplicate_key_path / INVENTORY_SCHEMA_FILE,
            schema_raw,
        )
        duplicate_key_raw = b'{"schema":"first","schema":"second"}\n'
        _write_exact(
            duplicate_key_path / INVENTORY_FILE,
            duplicate_key_raw,
        )
        duplicate_key_binding = build_inventory_binding(
            duplicate_key_raw,
            schema_raw,
        )
        _expect_rejection(
            lambda: load_bound_allocation_inventory(
                duplicate_key_path,
                duplicate_key_binding,
            ),
            "duplicate JSON object key",
        )
        cases += 1

        wrong_binding = copy.deepcopy(binding)
        wrong_binding["authoring_sha256"] = "f" * 64
        _expect_rejection(
            lambda: load_bound_allocation_inventory(directory, wrong_binding),
            "wrong inventory provenance digest",
        )
        cases += 1

        escaping_binding = copy.deepcopy(binding)
        escaping_binding["authoring_file"] = "../inventory.json"
        _expect_rejection(
            lambda: load_bound_allocation_inventory(directory, escaping_binding),
            "escaping inventory path",
        )
        cases += 1

        wrong_schema_binding = copy.deepcopy(binding)
        wrong_schema_binding["schema_byte_length"] += 1
        _expect_rejection(
            lambda: load_bound_allocation_inventory(
                directory,
                wrong_schema_binding,
            ),
            "wrong schema provenance length",
        )
        cases += 1

        hardlink_path = directory / "hardlink"
        hardlink_path.mkdir()
        _write_exact(hardlink_path / INVENTORY_FILE, canonical)
        os.link(
            hardlink_path / INVENTORY_FILE,
            hardlink_path / INVENTORY_SCHEMA_FILE,
        )
        _expect_rejection(
            lambda: load_bound_allocation_inventory(hardlink_path, binding),
            "hard-linked inventory and schema",
        )
        cases += 1

        changed_inventory = copy.deepcopy(sample)
        changed_inventory["unknown"] = True
        _expect_rejection(
            lambda: validate_allocation_inventory(changed_inventory, schema),
            "unknown inventory property",
        )
        cases += 1

        omitted_profile = copy.deepcopy(sample)
        omitted_profile["required_kinds"].remove("PROFILE")
        _expect_rejection(
            lambda: validate_allocation_inventory(omitted_profile, schema),
            "omitted PROFILE kind",
        )
        cases += 1

        for mutate, label in (
            (
                lambda value: value["document_row_commitment"].__setitem__(
                    "algorithm",
                    "UNKNOWN",
                ),
                "unknown document row commitment algorithm",
            ),
            (
                lambda value: value["document_row_commitment"].__setitem__(
                    "framing",
                    "UNKNOWN",
                ),
                "unknown document row commitment framing",
            ),
            (
                lambda value: value["document_row_commitment"].__setitem__(
                    "row_kinds",
                    ["exclusions", "allocations"],
                ),
                "reordered document row kinds",
            ),
            (
                lambda value: value["document_row_commitment"].__setitem__(
                    "row_selection",
                    "UNKNOWN",
                ),
                "unknown document row selection",
            ),
            (
                lambda value: value["document_row_commitment"]["fixed_vectors"][
                    "nonempty_allocation"
                ].__setitem__("expected_sha256", "f" * 64),
                "changed document row fixed vector",
            ),
            (
                lambda value: value["documents"][0]["source_set"].__setitem__(
                    "framing",
                    "UNKNOWN",
                ),
                "unknown ADR source-set framing",
            ),
            (
                lambda value: value["documents"][0]["source_set"]["fixed_vectors"][
                    "main_with_two_modules"
                ].__setitem__("expected_sha256", "f" * 64),
                "changed ADR source-set fixed vector",
            ),
            (
                lambda value: value["provenance_review"].__setitem__(
                    "framing",
                    "UNKNOWN",
                ),
                "unknown provenance review framing",
            ),
            (
                lambda value: value["provenance_review"]["projection_fields"].reverse(),
                "reordered provenance review projection fields",
            ),
            (
                lambda value: value["provenance_review"]["fixed_vectors"][
                    "minimal_assignment"
                ].__setitem__("expected_sha256", "f" * 64),
                "changed provenance review fixed vector",
            ),
            (
                lambda value: value["allocation_review_profile"][
                    "allocation_identity_commitment_suite"
                ].__setitem__("unit_id_domain_hex", "f" * 64),
                "changed unit ID domain",
            ),
            (
                lambda value: value["allocation_review_profile"][
                    "allocation_identity_commitment_suite"
                ].pop("framing"),
                "missing identity commitment framing",
            ),
            (
                lambda value: value["allocation_review_profile"][
                    "allocation_identity_commitment_suite"
                ].__setitem__("unknown", True),
                "open identity commitment suite",
            ),
            (
                lambda value: value["allocation_review_profile"][
                    "allocation_identity_commitment_suite"
                ]["fixed_vectors"]["unit_model_origin"].__setitem__(
                    "expected_unit_id",
                    "f" * 64,
                ),
                "changed allocation identity fixed vector",
            ),
            (
                lambda value: value["allocation_review_profile"][
                    "semantic_shape_commitment_suite"
                ].__setitem__("pointer_root_token", "/"),
                "colliding semantic shape root token",
            ),
            (
                lambda value: value["allocation_review_profile"][
                    "semantic_shape_commitment_suite"
                ]["type_tokens"].reverse(),
                "reordered semantic shape type taxonomy",
            ),
            (
                lambda value: value["allocation_review_profile"][
                    "semantic_shape_commitment_suite"
                ].pop("maximum_projection_bytes"),
                "missing semantic shape commitment bound",
            ),
            (
                lambda value: value["allocation_review_profile"][
                    "semantic_shape_commitment_suite"
                ]["fixed_vectors"]["representative_types_and_escaping"].__setitem__(
                    "expected_sha256",
                    "f" * 64,
                ),
                "changed semantic shape fixed vector",
            ),
            (
                lambda value: value["semantic_review_subject"].__setitem__(
                    "projection_rule",
                    "UNKNOWN",
                ),
                "unknown semantic review subject projection",
            ),
            (
                lambda value: value["semantic_review_subject"].pop("output"),
                "missing semantic review subject output encoding",
            ),
            (
                lambda value: value["semantic_review_subject"]["fixed_vectors"][
                    "semantic_model"
                ].__setitem__("expected_sha256", "f" * 64),
                "changed semantic review subject fixed vector",
            ),
        ):
            unknown_commitment_suite = copy.deepcopy(sample)
            mutate(unknown_commitment_suite)
            _expect_rejection(
                lambda value=unknown_commitment_suite: validate_allocation_inventory(
                    value, schema
                ),
                label,
            )
            cases += 1

        for key, value, label in (
            (
                "model_allocation_count",
                MAX_ALLOCATION_ROWS + 1,
                "oversized model allocation count",
            ),
            (
                "semantic_shape_entry_count",
                MAX_SEMANTIC_SHAPE_ROWS + 1,
                "oversized semantic shape count",
            ),
        ):
            oversized_count = copy.deepcopy(sample)
            oversized_count[key] = value
            _expect_rejection(
                lambda value=oversized_count: validate_allocation_inventory(
                    value,
                    schema,
                ),
                label,
            )
            cases += 1

        oversized_document = copy.deepcopy(sample)
        oversized_document["documents"][0]["byte_length"] = MAX_ADR_DOCUMENT_BYTES + 1
        _refresh_document_source_set(oversized_document["documents"][0])
        _expect_rejection(
            lambda: validate_allocation_inventory(oversized_document, schema),
            "oversized ADR document commitment",
        )
        cases += 1

        source_vector = ADR_SOURCE_SET_SUITE["fixed_vectors"]["main_with_two_modules"]
        source_input = source_vector["input"]
        forward_modules = copy.deepcopy(source_input["modules"])
        _require(
            adr_source_set_sha256(
                adr_id="ADR-004",
                path=ADR_ALLOCATION_PATHS[3],
                byte_length=1,
                source_sha256="0" * 64,
                modules=forward_modules,
            )
            != adr_source_set_sha256(
                adr_id="ADR-004",
                path=ADR_ALLOCATION_PATHS[3],
                byte_length=1,
                source_sha256="0" * 64,
                modules=list(reversed(forward_modules)),
            ),
            "ADR source-set digest does not bind module order",
        )
        cases += 1
        _require(
            adr_source_set_sha256(
                adr_id=source_input["decision_id"],
                path=source_input["path"],
                byte_length=source_input["byte_length"],
                source_sha256=source_input["sha256"],
                modules=forward_modules,
            )
            == source_vector["expected_sha256"],
            "ADR source-set commitment changed its fixed domain/framing vector",
        )
        _require(
            {
                "decision_id": source_input["decision_id"],
                "schema": ADR_SOURCE_SET_SCHEMA,
                "sources": [
                    {
                        "bytes": source_input["byte_length"],
                        "kind": "main",
                        "path": source_input["path"],
                        "sha256": source_input["sha256"],
                    },
                    *[
                        {
                            "bytes": module["byte_length"],
                            "kind": "module",
                            "path": module["path"],
                            "sha256": module["sha256"],
                        }
                        for module in source_input["modules"]
                    ],
                ],
            }
            == source_vector["expected_projection"],
            "ADR source-set fixed vector has an incoherent projection",
        )
        cases += 2
        _require(
            adr_source_set_sha256(
                adr_id="ADR-004",
                path=ADR_ALLOCATION_PATHS[3],
                byte_length=1,
                source_sha256="0" * 64,
                modules=forward_modules,
            )
            != adr_source_set_sha256(
                adr_id="ADR-009",
                path=ADR_ALLOCATION_PATHS[3],
                byte_length=1,
                source_sha256="0" * 64,
                modules=forward_modules,
            ),
            "ADR source-set digest does not bind the decision ID",
        )
        cases += 1
        provenance_vector = PROVENANCE_REVIEW_SUITE["fixed_vectors"][
            "minimal_assignment"
        ]
        provenance_input = provenance_vector["input"]
        _require(
            provenance_assignment_sha256(
                documents=provenance_input["documents"],
                allocations=provenance_input["allocations"],
                exclusions=provenance_input["exclusions"],
                allocation_review_profile=provenance_input["allocation_review_profile"],
                semantic_review_subject=provenance_input["semantic_review_subject"],
            )
            == provenance_vector["expected_sha256"],
            "provenance review changed its fixed domain/framing vector",
        )
        _require(
            {
                "allocation_review_profile": provenance_input[
                    "allocation_review_profile"
                ],
                "allocations": provenance_input["allocations"],
                "document_source_sets": [
                    {
                        "adr_id": document["adr_id"],
                        "allocation_anchor_id": document["allocation_anchor_id"],
                        "source_set": document["source_set"],
                    }
                    for document in provenance_input["documents"]
                ],
                "exclusions": provenance_input["exclusions"],
                "semantic_review_subject": provenance_input["semantic_review_subject"],
            }
            == provenance_vector["expected_projection"],
            "provenance review fixed vector has an incoherent projection",
        )
        cases += 2

        def swap_adr_modules(value: dict[str, Any]) -> None:
            left = copy.deepcopy(value["documents"][3]["modules"])
            right = copy.deepcopy(value["documents"][8]["modules"])
            value["documents"][3]["modules"] = right
            value["documents"][8]["modules"] = left

        for mutate, refresh_indexes, label in (
            (
                lambda value: value["documents"][3]["modules"].clear(),
                (3,),
                "missing ADR module",
            ),
            (
                swap_adr_modules,
                (3, 8),
                "swapped ADR module",
            ),
            (
                lambda value: value["documents"][3]["modules"].append(
                    copy.deepcopy(value["documents"][3]["modules"][0])
                ),
                (3,),
                "duplicate ADR module",
            ),
            (
                lambda value: value["documents"][3]["modules"][0].__setitem__(
                    "sha256",
                    "f" * 64,
                ),
                (),
                "stale ADR module digest",
            ),
            (
                lambda value: value["documents"][3]["modules"][0].__setitem__(
                    "byte_length",
                    MAX_ADR_DOCUMENT_BYTES + 1,
                ),
                (3,),
                "oversized ADR module",
            ),
            (
                lambda value: value["documents"][3]["modules"][0].__setitem__(
                    "path",
                    "../escaped-module.md",
                ),
                (3,),
                "ADR module path escape",
            ),
            (
                lambda value: value["documents"][3]["modules"][0].__setitem__(
                    "path",
                    value["documents"][3]["path"],
                ),
                (3,),
                "ADR module alias of its main source",
            ),
        ):
            hostile_module = copy.deepcopy(sample)
            mutate(hostile_module)
            for document_index in refresh_indexes:
                _refresh_document_source_set(
                    hostile_module["documents"][document_index]
                )
            _expect_rejection(
                lambda value=hostile_module: validate_allocation_inventory(
                    value,
                    schema,
                ),
                label,
            )
            cases += 1

        stale_source_set = copy.deepcopy(sample)
        stale_source_set["documents"][3]["source_set"]["sha256"] = "f" * 64
        _expect_rejection(
            lambda: validate_allocation_inventory(stale_source_set, schema),
            "stale ADR source-set digest",
        )
        cases += 1

        oversized_corpus = copy.deepcopy(sample)
        for document in oversized_corpus["documents"]:
            document["byte_length"] = MAX_ADR_DOCUMENT_BYTES
            for module in document["modules"]:
                module["byte_length"] = MAX_ADR_DOCUMENT_BYTES
            _refresh_document_source_set(document)
        _expect_rejection(
            lambda: validate_allocation_inventory(oversized_corpus, schema),
            "oversized aggregate ADR source corpus",
        )
        cases += 1

        invalid_profile = copy.deepcopy(sample)
        invalid_profile["allocations"] = [
            _sample_allocation_row(
                adr_id="ADR-001",
                exact_name="sample_profile",
                kind="PROFILE",
                semantic_ref="not-a-stable-profile-reference",
            )
        ]
        _expect_rejection(
            lambda: validate_allocation_inventory(invalid_profile, schema),
            "PROFILE without JSON-pointer provenance",
        )
        cases += 1

        for row, label in (
            (
                _sample_allocation_row(
                    adr_id="ADR-001",
                    exact_name="SAMPLE_HEAD",
                    kind="RESOURCE",
                    semantic_ref="resource-id::SAMPLE.HEAD",
                ),
                "RESOURCE without its exact dotted identity",
            ),
            (
                _sample_allocation_row(
                    adr_id="ADR-001",
                    exact_name="SAMPLE.HEAD",
                    kind="RESOURCE",
                    semantic_ref="resource-id::OTHER.HEAD",
                ),
                "RESOURCE semantic identity mismatch",
            ),
            (
                _sample_allocation_row(
                    adr_id="ADR-001",
                    exact_name="SAMPLE",
                    kind="SELECTOR",
                    semantic_ref="resource-id::SAMPLE.HEAD",
                ),
                "SELECTOR with a resource semantic reference",
            ),
        ):
            hostile_kind = copy.deepcopy(sample)
            hostile_kind["allocations"] = [row]
            hostile_kind["documents"][0]["allocation_row_count"] = 1
            hostile_kind["documents"][0]["allocation_rows_sha256"] = (
                document_rows_sha256(
                    hostile_kind["allocations"],
                    row_kind="allocations",
                )
            )
            _expect_rejection(
                lambda value=hostile_kind: validate_allocation_inventory(
                    value,
                    schema,
                ),
                label,
            )
            cases += 1

        alias_row = _sample_allocation_row(
            adr_id="ADR-001",
            exact_name="SampleType",
            kind="TYPE",
            semantic_ref="sample-type::SampleType",
        )
        aliased = copy.deepcopy(sample)
        aliased["allocations"] = [alias_row, alias_row]
        _expect_rejection(
            lambda: validate_allocation_inventory(aliased, schema),
            "mutable subtree alias",
        )
        cases += 1

        anchored = copy.deepcopy(sample)
        anchored["allocations"] = [copy.deepcopy(alias_row)]
        anchored["documents"][0]["allocation_row_count"] = 1
        anchored["documents"][0]["allocation_rows_sha256"] = document_rows_sha256(
            anchored["allocations"],
            row_kind="allocations",
        )
        validate_allocation_inventory(anchored, schema)
        cases += 1

        unit_id_mutants: list[tuple[str, Any]] = [
            (
                "missing unit ID",
                lambda value: value["allocations"][0].pop("unit_id"),
            ),
            (
                "unknown unit ID encoding",
                lambda value: value["allocations"][0].__setitem__(
                    "unit_id",
                    "UNKNOWN",
                ),
            ),
            (
                "forged unit ID",
                lambda value: value["allocations"][0].__setitem__(
                    "unit_id",
                    "f" * 64,
                ),
            ),
            (
                "legacy owner field outside the closed v4 row",
                lambda value: value["allocations"][0].__setitem__(
                    "owner_selector_id",
                    "SHARED",
                ),
            ),
        ]
        for label, mutate in unit_id_mutants:
            hostile_unit_id = copy.deepcopy(anchored)
            mutate(hostile_unit_id)
            hostile_unit_id["documents"][0]["allocation_rows_sha256"] = (
                document_rows_sha256(
                    hostile_unit_id["allocations"],
                    row_kind="allocations",
                )
            )
            _expect_rejection(
                lambda value=hostile_unit_id: validate_allocation_inventory(
                    value,
                    schema,
                ),
                label,
            )
            cases += 1

        duplicate_unit_id = copy.deepcopy(anchored)
        second_row = _sample_allocation_row(
            adr_id="ADR-001",
            exact_name="OtherType",
            kind="TYPE",
            semantic_ref="other-type::OtherType",
        )
        second_row["unit_id"] = duplicate_unit_id["allocations"][0]["unit_id"]
        duplicate_unit_id["allocations"].append(second_row)
        duplicate_unit_id["documents"][0]["allocation_row_count"] = 2
        duplicate_unit_id["documents"][0]["allocation_rows_sha256"] = (
            document_rows_sha256(
                duplicate_unit_id["allocations"],
                row_kind="allocations",
            )
        )
        _expect_rejection(
            lambda: validate_allocation_inventory(duplicate_unit_id, schema),
            "duplicate unit ID across distinct semantic identities",
        )
        cases += 1

        reviewed = copy.deepcopy(anchored)
        reviewed["provenance_review"]["status"] = "REVIEWED"
        reviewed["provenance_review"]["reviewed_assignment_sha256"] = (
            provenance_assignment_sha256(
                reviewed["documents"],
                reviewed["allocations"],
                reviewed["exclusions"],
                reviewed["allocation_review_profile"],
                reviewed["semantic_review_subject"],
            )
        )
        validate_allocation_inventory(reviewed, schema)
        cases += 1

        stale_review_subject = copy.deepcopy(reviewed)
        stale_review_subject["semantic_review_subject"]["sha256"] = "f" * 64
        _expect_rejection(
            lambda: validate_allocation_inventory(stale_review_subject, schema),
            "reviewed assignment with a changed semantic review subject",
        )
        cases += 1

        stale_reviewed_source_set = copy.deepcopy(reviewed)
        stale_reviewed_source_set["documents"][3]["modules"][0]["sha256"] = "e" * 64
        _refresh_document_source_set(stale_reviewed_source_set["documents"][3])
        _expect_rejection(
            lambda: validate_allocation_inventory(
                stale_reviewed_source_set,
                schema,
            ),
            "reviewed assignment with changed ADR module source set",
        )
        cases += 1

        for mutate, label in (
            (
                lambda value: value["provenance_review"].__setitem__(
                    "status",
                    "UNKNOWN",
                ),
                "unknown provenance review status",
            ),
            (
                lambda value: value["provenance_review"].__setitem__(
                    "reviewed_assignment_sha256",
                    "0" * 64,
                ),
                "review status with a stale assignment digest",
            ),
        ):
            hostile_review = copy.deepcopy(reviewed)
            mutate(hostile_review)
            _expect_rejection(
                lambda value=hostile_review: validate_allocation_inventory(
                    value,
                    schema,
                ),
                label,
            )
            cases += 1

        premature_complete = copy.deepcopy(anchored)
        premature_complete["status"] = "COMPLETE"
        _expect_rejection(
            lambda: validate_allocation_inventory(
                premature_complete,
                schema,
            ),
            "complete status before provenance review",
        )
        cases += 1

        for mutate, label in (
            (
                lambda value: value["allocations"][0].__setitem__(
                    "source_anchor",
                    ADR_ALLOCATION_ANCHOR_BY_ID["ADR-002"],
                ),
                "allocation reassigned to another ADR anchor",
            ),
            (
                lambda value: value["allocations"][0].__setitem__(
                    "source_anchor",
                    "",
                ),
                "allocation with an empty default anchor",
            ),
            (
                lambda value: value["allocations"].clear(),
                "deleted allocation with stale per-ADR commitment",
            ),
            (
                lambda value: value["documents"][0].__setitem__(
                    "allocation_rows_sha256",
                    "f" * 64,
                ),
                "stale per-ADR allocation-row digest",
            ),
            (
                lambda value: value["documents"][0].__setitem__(
                    "allocation_anchor_id",
                    ADR_ALLOCATION_ANCHOR_BY_ID["ADR-002"],
                ),
                "reassigned document anchor",
            ),
        ):
            hostile_anchor = copy.deepcopy(anchored)
            mutate(hostile_anchor)
            _expect_rejection(
                lambda value=hostile_anchor: validate_allocation_inventory(
                    value,
                    schema,
                ),
                label,
            )
            cases += 1

        duplicate_allocation = copy.deepcopy(anchored)
        duplicate_allocation["allocations"].append(
            copy.deepcopy(duplicate_allocation["allocations"][0])
        )
        duplicate_allocation["documents"][0]["allocation_row_count"] = 2
        duplicate_allocation["documents"][0]["allocation_rows_sha256"] = (
            document_rows_sha256(
                duplicate_allocation["allocations"],
                row_kind="allocations",
            )
        )
        _expect_rejection(
            lambda: validate_allocation_inventory(
                duplicate_allocation,
                schema,
            ),
            "duplicate allocation row with refreshed commitment",
        )
        cases += 1

        for exact_name, kind, semantic_ref, label in (
            (
                "SampleType",
                "TYPE",
                "sample-type::DifferentType",
                "TYPE reference with a different exact name",
            ),
            (
                "CREATE_SAMPLE",
                "EVENT",
                "not-an-allocation-reference",
                "EVENT without an allocation reference",
            ),
            (
                "ACTIVE",
                "STATE",
                "state-id::OTHER.ROOT.DIFFERENT",
                "STATE reference with a different exact name",
            ),
        ):
            invalid_provenance = copy.deepcopy(sample)
            invalid_provenance["allocations"] = [
                _sample_allocation_row(
                    adr_id="ADR-001",
                    exact_name=exact_name,
                    kind=kind,
                    semantic_ref=semantic_ref,
                )
            ]
            invalid_provenance["documents"][0]["allocation_row_count"] = 1
            invalid_provenance["documents"][0]["allocation_rows_sha256"] = (
                document_rows_sha256(
                    invalid_provenance["allocations"],
                    row_kind="allocations",
                )
            )
            _expect_rejection(
                lambda value=invalid_provenance: validate_allocation_inventory(
                    value,
                    schema,
                ),
                label,
            )
            cases += 1

        moved_allocation = copy.deepcopy(anchored)
        moved_allocation["allocations"][0]["adr_id"] = "ADR-002"
        moved_allocation["allocations"][0]["source_anchor"] = (
            ADR_ALLOCATION_ANCHOR_BY_ID["ADR-002"]
        )
        _expect_rejection(
            lambda: validate_allocation_inventory(moved_allocation, schema),
            "allocation moved across ADRs without new document commitments",
        )
        cases += 1

        explicitly_moved_allocation = copy.deepcopy(moved_allocation)
        explicitly_moved_allocation["documents"][0]["allocation_row_count"] = 0
        explicitly_moved_allocation["documents"][0]["allocation_rows_sha256"] = (
            document_rows_sha256(
                [],
                row_kind="allocations",
            )
        )
        explicitly_moved_allocation["documents"][1]["allocation_row_count"] = 1
        explicitly_moved_allocation["documents"][1]["allocation_rows_sha256"] = (
            document_rows_sha256(
                explicitly_moved_allocation["allocations"],
                row_kind="allocations",
            )
        )
        validate_allocation_inventory(explicitly_moved_allocation, schema)
        _require(
            inventory_bytes(explicitly_moved_allocation) != inventory_bytes(anchored),
            "explicit ADR reassignment did not change the bound inventory bytes",
        )
        cases += 2

        stale_reviewed_move = copy.deepcopy(explicitly_moved_allocation)
        stale_reviewed_move["provenance_review"] = copy.deepcopy(
            reviewed["provenance_review"]
        )
        _expect_rejection(
            lambda: validate_allocation_inventory(stale_reviewed_move, schema),
            "ADR reassignment with a stale semantic-review commitment",
        )
        cases += 1
        stale_reviewed_move["provenance_review"]["reviewed_assignment_sha256"] = (
            provenance_assignment_sha256(
                stale_reviewed_move["documents"],
                stale_reviewed_move["allocations"],
                stale_reviewed_move["exclusions"],
                stale_reviewed_move["allocation_review_profile"],
                stale_reviewed_move["semantic_review_subject"],
            )
        )
        validate_allocation_inventory(stale_reviewed_move, schema)
        cases += 1

        _expect_rejection(
            lambda: read_bounded_regular_file(
                inventory_path,
                maximum_bytes=len(canonical) - 1,
                label="allocation inventory self-test bound",
            ),
            "oversized inventory",
        )
        cases += 1

        symlink_directory = directory / "symlink"
        symlink_directory.mkdir()
        _write_exact(
            symlink_directory / INVENTORY_SCHEMA_FILE,
            schema_raw,
        )
        (symlink_directory / INVENTORY_FILE).symlink_to(inventory_path)
        _expect_rejection(
            lambda: load_bound_allocation_inventory(
                symlink_directory,
                binding,
            ),
            "symlink inventory",
        )
        cases += 1

        real_ancestor = directory / "real-ancestor"
        real_ancestor.mkdir()
        nested_inventory_directory = real_ancestor / "nested"
        nested_inventory_directory.mkdir()
        _write_exact(
            nested_inventory_directory / INVENTORY_SCHEMA_FILE,
            schema_raw,
        )
        _write_exact(
            nested_inventory_directory / INVENTORY_FILE,
            canonical,
        )
        symlink_ancestor = directory / "symlink-ancestor"
        symlink_ancestor.symlink_to(real_ancestor, target_is_directory=True)
        _expect_rejection(
            lambda: load_bound_allocation_inventory(
                symlink_ancestor / "nested",
                binding,
            ),
            "symlinked ancestor directory",
        )
        cases += 1

        symlink_base = directory / "symlink-base"
        symlink_base.symlink_to(
            nested_inventory_directory,
            target_is_directory=True,
        )
        _expect_rejection(
            lambda: load_bound_allocation_inventory(
                symlink_base,
                binding,
            ),
            "symlinked base directory",
        )
        cases += 1

        descriptor = os.open(copied_schema_path, os.O_WRONLY | os.O_TRUNC)
        try:
            os.write(descriptor, schema_raw + b" ")
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        _expect_rejection(
            lambda: verify_inventory_snapshot_unchanged(snapshot),
            "schema changed after validation",
        )
        cases += 1
        descriptor = os.open(copied_schema_path, os.O_WRONLY | os.O_TRUNC)
        try:
            os.write(descriptor, schema_raw)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

        replaced = canonical[:-2] + (b" " if canonical[-2:-1] != b" " else b"x") + b"\n"
        descriptor = os.open(inventory_path, os.O_WRONLY | os.O_TRUNC)
        try:
            os.write(descriptor, replaced)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        _expect_rejection(
            lambda: verify_inventory_snapshot_unchanged(snapshot),
            "inventory changed after validation",
        )
        cases += 1

    return cases


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--inventory",
        type=Path,
        default=DEFAULT_INVENTORY,
        help="allocation authoring inventory",
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=DEFAULT_SCHEMA,
        help="allocation authoring schema",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run hostile loader tests",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.self_test:
            cases = run_self_test(args.schema)
            print(f"selector allocation inventory self-test: PASS cases={cases}")
            return 0
        schema_raw, schema = load_inventory_schema(args.schema)
        raw = read_bounded_regular_file(
            args.inventory,
            maximum_bytes=MAX_ALLOCATION_INVENTORY_BYTES,
            label="selector allocation authoring inventory",
        )
        value = parse_json_bytes(raw, label=str(args.inventory))
        _require(isinstance(value, dict), "allocation inventory must be an object")
        _require(
            raw == inventory_bytes(value),
            "allocation inventory is not canonical JSON with one trailing newline",
        )
        validate_allocation_inventory(value, schema)
        validate_allocation_review_profile_schema_binding(value, schema_raw)
        print(
            "selector allocation inventory structural check: PASS "
            f"bytes={len(raw)} sha256={sha256(raw).hexdigest()} "
            f"schema_sha256={sha256(schema_raw).hexdigest()} "
            f"status={value['status']} completeness=NOT_EVALUATED "
            "adr_snapshots=NOT_EVALUATED"
        )
        return 0
    except (
        KeyError,
        OSError,
        SelectorAllocationInventoryError,
        SelectorClosureCodecError,
        TypeError,
    ) as error:
        print(
            f"selector allocation inventory structural check: FAIL: {error}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
