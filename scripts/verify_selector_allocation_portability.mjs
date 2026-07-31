#!/usr/bin/env node
/**
 * Independently recompute the portable B01 allocation commitments.
 *
 * This verifier intentionally uses only the Node.js standard library. It does
 * not import or execute the Python allocation implementation. Its result is
 * local implementation-diversity evidence only. It is not an independent peer,
 * an external review, an ADR assignment, or release authorization.
 */

import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { TextDecoder } from "node:util";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const MAX_SAFE_INTEGER = 9_007_199_254_740_991;
const MAX_SOURCE_BYTES = 16 * 1024 * 1024;
const MAX_INVENTORY_BYTES = 4 * 1024 * 1024;
const MAX_SCHEMA_BYTES = 128 * 1024;
const MAX_COMPACT_BYTES = 4 * 1024 * 1024;
const MAX_PROPOSAL_BYTES = 12 * 1024 * 1024;
const MAX_COMPILER_SOURCE_BYTES = 2 * 1024 * 1024;
const MAX_ADR_SOURCE_BYTES = 256 * 1024;
const MAX_JSON_DEPTH = 64;
const MAX_JSON_ITEMS = 1_000_000;
const MAX_JSON_NUMBER_CHARS = 128;
const MAX_JSON_STRING_CHARS = 8 * 1024;
const MAX_JSON_TOTAL_STRING_CHARS = 16 * 1024 * 1024;

const AUTHORING_PATH = "docs/adr/selector-closure.authoring.v1.json";
const INVENTORY_PATH = "docs/adr/selector-allocation.authoring.v1.json";
const INVENTORY_SCHEMA_PATH =
  "docs/adr/selector-allocation.authoring.schema.v1.json";
const COMPACT_PATH = "docs/adr/selector-closure.source.v1.json";
const PROPOSAL_PATH = "docs/adr/selector-allocation.proposal.v1.json";
const PROPOSAL_SCHEMA_PATH =
  "docs/adr/selector-allocation.proposal.schema.v1.json";
const PROPOSAL_SCHEMA_FILE = "selector-allocation.proposal.schema.v1.json";
const PROPOSAL_SCHEMA_ID = "ncp.b01-selector-allocation-proposal.v1";
const PROPOSAL_CLAIM_BOUNDARY =
  "LOCAL_DETERMINISTIC_OWNER_FREE_REVIEW_PROPOSAL_ONLY_NOT_ALLOCATION_AUTHORITY_ADR_ACCEPTANCE_PROTOCOL_RELEASE_EXTERNAL_OR_INDEPENDENT_EVIDENCE";
const COMMITMENT_ALGORITHM =
  "SHA256_DOMAIN_THEN_UINT64_BE_CANONICAL_BYTE_LENGTH_THEN_CANONICAL_JSON";
const COMMITMENT_CANONICALIZATION =
  "UTF8_JSON_SORTED_KEYS_NO_INSIGNIFICANT_WHITESPACE";
const PROPOSAL_DOMAINS = Object.freeze({
  adrCorpus: domainHex("ncp.b01.selector-allocation.proposal-adr-corpus.v1"),
  ambiguity: domainHex(
    "ncp.b01.selector-allocation.proposal-ambiguity-flags.v2",
  ),
  compilerSources: domainHex(
    "ncp.b01.selector-allocation.proposal-compiler-source-set.v1",
  ),
  originKinds: domainHex(
    "ncp.b01.selector-allocation.proposal-origin-kinds.v1",
  ),
  proseSignals: domainHex(
    "ncp.b01.selector-allocation.proposal-prose-signals.v2",
  ),
  routeClasses: domainHex(
    "ncp.b01.selector-allocation.proposal-route-classes.v2",
  ),
  rows: domainHex("ncp.b01.selector-allocation.proposal-rows.v2"),
  signalKinds: domainHex(
    "ncp.b01.selector-allocation.proposal-signal-kinds.v1",
  ),
});
const MODEL_DOMAINS = Object.freeze({
  modelProjection: domainHex(
    "ncp.b01.selector-allocation.model-projection.v4",
  ),
  originSignal: domainHex(
    "ncp.b01.selector-allocation.origin-signal-projection.v1",
  ),
  unitId: domainHex("ncp.b01.selector-allocation.unit-id.v1"),
});
const EXPECTED_SEMANTIC_SHAPE_SUITE = Object.freeze({
  algorithm: "SHA256",
  array_index_treatment:
    "UNPADDED_BASE10_NONNEGATIVE_INTEGER_SEGMENT_WITH_ZERO_AS_0_ORDERED_BY_COMPLETE_POINTER_ASCII_BYTES",
  bounds_application: "REJECT_BEFORE_DIGEST_SUCCESS_IF_ANY_BOUND_EXCEEDED",
  canonicalization: "UTF8_JSON_SORTED_KEYS_NO_INSIGNIFICANT_WHITESPACE",
  domain_hex: domainHex(
    "ncp.b01.selector-allocation.semantic-shape-projection.v3",
  ),
  fixed_vectors: {
    nesting_depth_boundary: {
      construction:
        "ROOT_OBJECT_MEMBER_X_WITH_NULL_WRAPPED_IN_N_SINGLETON_ARRAYS",
      expected_accepted_entry_count: 65,
      expected_accepted_projection_byte_length: 5006,
      expected_accepted_sha256:
        "ffdf1822c36f52e46e9ede5e4880b02a47fdeb5936540a8fdb23f447afc6c325",
      first_rejected_array_wrapper_count: 64,
      maximum_accepted_array_wrapper_count: 63,
      root_depth: 0,
    },
    representative_types_and_escaping: {
      expected_entry_count: 7,
      expected_projection_byte_length: 121,
      expected_projection_rows: [
        ["", "object"],
        ["/", "null"],
        ["/~0", "string"],
        ["/~1", "array"],
        ["/~1/0", "boolean"],
        ["/~1/1", "integer"],
        ["/~1/2", "integer"],
      ],
      expected_sha256:
        "4a24a885fe8a123556ff83f27ab7389f4c498044420fe6afa27be3d60e7a2325",
      source_canonical_utf8_byte_length: 63,
      source_canonical_utf8_hex:
        "7b22223a6e756c6c2c222f223a5b747275652c2d393030373139393235343734303939312c393030373139393235343734303939315d2c227e223a2278227d",
    },
    schema: "ncp.b01-selector-allocation-semantic-shape-fixed-vectors.v3",
  },
  framing:
    "DOMAIN_BYTES_THEN_UINT64_BE_CANONICAL_BYTE_LENGTH_THEN_CANONICAL_BYTES",
  maximum_entries: 1_000_000,
  maximum_nesting_depth: MAX_JSON_DEPTH,
  maximum_pointer_characters: 8 * 1024,
  maximum_projection_bytes: 32 * 1024 * 1024,
  nesting_depth_counting:
    "DOCUMENT_ROOT_IS_DEPTH_0_EACH_ARRAY_OR_OBJECT_CHILD_INCREMENTS_BY_1",
  object_member_ordering:
    "LEXICOGRAPHIC_ASCENDING_BY_RFC6901_ESCAPED_MEMBER_TOKEN_ASCII_BYTES",
  output: "LOWERCASE_HEXADECIMAL_64_CHARACTERS",
  pointer_root_token: "",
  pointer_scalar_domain:
    "EMPTY_DOCUMENT_ROOT_OR_SLASH_PREFIXED_PRINTABLE_ASCII_RFC6901_SEGMENTS",
  pointer_segment_escaping:
    "REPLACE_TILDE_WITH_~0_THEN_REPLACE_SLASH_WITH_~1",
  pointer_syntax: "RFC6901_JSON_POINTER",
  projection_shape: "JSON_ARRAY_OF_JSON_ARRAY_ROWS",
  row_fields: ["json_pointer", "type_token"],
  row_ordering:
    "LEXICOGRAPHIC_ASCENDING_BY_STORED_RFC6901_JSON_POINTER_ASCII_BYTES",
  row_shape: "JSON_ARRAY_OF_EXACTLY_TWO_STRINGS",
  row_uniqueness: "JSON_POINTER_UNIQUE",
  root_depth: 0,
  scalar_domain:
    "NULL_EXACT_BOOLEAN_CANONICAL_SIGNED_SAFE_INTEGER_ABS_LE_9007199254740991_EMPTY_OR_PRINTABLE_ASCII_STRING",
  schema: "ncp.b01-selector-allocation-semantic-shape-commitment-suite.v3",
  source_shape: "JSON_OBJECT",
  source_member_name_domain:
    "EMPTY_OR_PRINTABLE_ASCII_U+0020_THROUGH_U+007E",
  stream_projection:
    "OPEN_BRACKET_THEN_CANONICAL_ROWS_COMMA_SEPARATED_THEN_CLOSE_BRACKET",
  type_token_mapping: {
    array: "JSON_ARRAY",
    boolean: "JSON_LITERAL_TRUE_OR_FALSE",
    integer:
      "CANONICAL_SIGNED_INTEGER_TOKEN_ABS_LE_9007199254740991_NEGATIVE_ZERO_FORBIDDEN",
    null: "JSON_LITERAL_NULL",
    object: "JSON_OBJECT",
    string: "EMPTY_OR_PRINTABLE_ASCII_JSON_STRING",
  },
  type_tokens: ["array", "boolean", "integer", "null", "object", "string"],
});

const ADR_IDS = Object.freeze(
  Array.from({ length: 11 }, (_, index) => `ADR-${String(index + 1).padStart(3, "0")}`),
);
const ADR_SOURCES = Object.freeze([
  ["docs/adr/0001-separate-simulation-and-plant-sessions.md", []],
  ["docs/adr/0002-contract-identity-and-release-authorization.md", []],
  ["docs/adr/0003-authenticated-production-ingress.md", []],
  [
    "docs/adr/0004-observer-attach-grants-and-revocation.md",
    ["docs/adr/modules/adr-004-cross-store-observer-closure-and-enrollment.md"],
  ],
  ["docs/adr/0005-declared-stream-lifecycle.md", []],
  ["docs/adr/0006-body-issued-authority-and-time.md", []],
  ["docs/adr/0007-command-disposition-journal.md", []],
  ["docs/adr/0008-extension-namespace-and-galadriel-separation.md", []],
  [
    "docs/adr/0009-security-state-rotation-and-revocation.md",
    ["docs/adr/modules/adr-009-cross-store-producer-and-compromise-evidence.md"],
  ],
  ["docs/adr/0010-plane-qos-retention-and-overload.md", []],
  ["docs/adr/0011-ecosystem-topology-and-handover.md", []],
]);
const COMPILER_SOURCE_PATHS = Object.freeze([
  "scripts/check_selector_closure.py",
  "scripts/generate_selector_allocation_proposal.py",
  "scripts/selector_allocation_inventory.py",
  "scripts/selector_closure_codec.py",
  "scripts/selector_resource_closure.py",
]);
const PYTHON_CODEC_BOUND_DECLARATIONS = Object.freeze([
  "MAX_COMPACT_BYTES = 4 * 1024 * 1024",
  "MAX_JSON_DEPTH = 64",
  "MAX_JSON_ITEMS = 1_000_000",
  "MAX_JSON_NUMBER_CHARS = 128",
  "MAX_JSON_STRING_CHARS = 8192",
  "MAX_JSON_TOTAL_STRING_CHARS = MAX_EXPANDED_BYTES",
]);
const SUGGESTED_DESTINATIONS = Object.freeze([...ADR_IDS, "UNMAPPED_SHARED"]);
const ROUTE_RULE_CLASSES = Object.freeze([
  "BODY_ACCEPTED_PROSE_RULE",
  "BODY_DECLARATION_PARTITION_RULE",
  "DECLARING_SELECTOR_REGISTRY_RULE",
  "NO_TOTAL_RULE",
  "SEMANTIC_REFERENCE_RULE",
  "STRUCTURAL_PROFILE_RULE",
]);
const AMBIGUITY_FLAGS = Object.freeze([
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
]);
const MODEL_KINDS = Object.freeze([
  "EVENT",
  "PROFILE",
  "RESOURCE",
  "SELECTOR",
  "STATE",
  "TYPE",
]);
const ACCEPTED_ALLOCATION_PROSE_HEADINGS = new Set([
  "Proposed decision",
  "Actors and state transitions",
  "Bounds and resource behavior",
  "Cross-store producer, audience, retention, and compromise rules",
  "External composite-state enrollment and retirement",
  "Formal properties",
  "Local namespace-closure import and prepared-intent resolution",
  "Operational recovery",
  "Source issuance and independent exposure-anchor closure",
]);
const READ_SNAPSHOTS = new Map();
const READ_INODES = new Map();
const CANDIDATE_SELECTOR_ADR = Object.freeze({
  ACTUATION_AUTHORITY_DOMAIN: "ADR-007",
  AUTHORITY_REALM_ENROLLMENT_REGISTRY: "ADR-001",
  AUTHORITY_TRANSACTION_DOMAIN: "ADR-001",
  BODY_SESSION_CONTROL: "ADR-007",
  CONSUMER_SEMANTIC_CAPTURE: "ADR-004",
  CONSUMER_SURFACE_INVENTORY: "ADR-011",
  GALADRIEL_LIFECYCLE: "ADR-008",
  HALDIR_ASSESSMENT_RECEIVER: "ADR-008",
  HALDIR_COMMANDER_PUBLICATION: "ADR-008",
  HALDIR_POLICY: "ADR-008",
  INDEPENDENT_ANCHOR_NAMESPACE_RESERVATION_REGISTRY: "ADR-004",
  LOGICAL_SESSION_GENERATION_LINEAGE: "ADR-001",
  LOGICAL_SESSION_NAMESPACE_REGISTRY: "ADR-001",
  OBSERVER_ADMISSION: "ADR-004",
  OBSERVER_ATTACHMENT_TARGET_HISTORY: "ADR-004",
  OBSERVER_AUTHORIZATION: "ADR-004",
  OBSERVER_GRANT_CHALLENGE_EXPOSURE_ANCHOR: "ADR-004",
  OBSERVER_GRANT_SOURCE_ISSUANCE_INDEX: "ADR-004",
  OBSERVER_UNRESOLVED_TARGET_QUARANTINE: "ADR-004",
  PHYSICAL_ACTUATION_JURISDICTION_ENROLLMENT_REGISTRY: "ADR-007",
  PRISOMA_NUMERIC_EXECUTOR: "ADR-011",
  RECEIVER_ADMISSION: "ADR-005",
  SECURITY_AUTHORITY: "ADR-009",
  SIMULATION_SESSION_STATE: "ADR-001",
  TRUSTED_DELIVERY_RELEASE: "ADR-004",
});
const CANDIDATE_PROFILE_ADR = Object.freeze({
  actor_profiles: "ADR-011",
  actuation_authority_domain_registry_profile: "ADR-007",
  authority_realm_enrollment_registry_profile: "ADR-001",
  authority_transaction_domain_profile: "ADR-001",
  body_actuation_arbiter_profile: "ADR-007",
  bulk_disposition_journal_profile: "ADR-007",
  closed_event_profile_catalog: "ADR-001",
  consumer_lifecycle_union_profile: "ADR-011",
  deadline_linearization_profile: "ADR-006",
  decision_relation_profile: "ADR-001",
  forwarding_replay_profile: "ADR-003",
  joint_selector_transaction_profiles: "ADR-001",
  logical_session_generation_lineage_profile: "ADR-001",
  logical_session_namespace_registry_profile: "ADR-001",
  observer_grant_request_target_profile: "ADR-004",
  observer_read_capture_bridge_profile: "ADR-004",
  observer_unresolved_target_quarantine_profile: "ADR-004",
  physical_actuation_jurisdiction_enrollment_profile: "ADR-007",
  physical_actuation_jurisdiction_hardware_epoch_profile: "ADR-007",
  realm_scoped_direct_binding_profile: "ADR-001",
  security_authority_state_profile: "ADR-009",
  selector_ownership_profile: "ADR-011",
  sidecar_binding_profiles: "ADR-001",
  simulation_session_state_profile: "ADR-001",
  source_logical_session_retirement_profile: "ADR-001",
  verification_model_profile: "ADR-001",
});
const CANDIDATE_ADR001_JOINT_PROFILES = new Set([
  "JTX_REQUIRED_CHILD_MARKER_CONSUMPTION_AT_BODY_SESSION_CONTROL_STATE_NATIVE_GENESIS",
  "JTX_REQUIRED_CHILD_MARKER_CONSUMPTION_AT_OBSERVER_AUTHORIZATION_STATE_NATIVE_GENESIS",
  "JTX_REQUIRED_CHILD_MARKER_CONSUMPTION_AT_SIMULATION_SESSION_STATE_NATIVE_GENESIS",
  "JTX_SOURCE_LINEAGE_REGISTRATION",
]);
const CANDIDATE_BODY_ADR006_STATE_DOMAINS = new Set([
  "BODY_COMMAND_FRESHNESS_GRANT",
  "LEASE_CURRENTNESS",
  "LIFECYCLE_LATCH",
  "PENDING_AUTHORITY_OPERATION",
  "RETIREMENT_BOUNDARY_CLOSURE",
  "ROOT",
]);
const CANDIDATE_BODY_ADR006_TYPE_PREFIXES = Object.freeze([
  "BodyActuationBoundaryRetirementClosure",
  "BodyActuationDomainGenerationReconciliation",
  "BodyAuthorityDeadline",
  "BodyClockRestart",
  "BodyCommandFreshness",
  "BodyRetirementBoundaryClosure",
  "BodySessionGeneration",
  "ConfirmedEstop",
  "InstalledBodySessionControl",
  "PlantAuthority",
  "UnknownEstop",
]);
const CANDIDATE_BODY_CONTROL_ADR006_TYPE_FRAGMENTS = Object.freeze([
  "GenesisFact",
  "LeaseCurrentness",
  "LifecycleLatch",
  "PendingAuthorityOperation",
  "RetirementBoundaryClosure",
  "StateHead",
  "StateCommitReceipt",
  "StateSelector",
  "TransitionFact",
]);

const ORACLE_KEYS = [
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
];

class PortabilityError extends Error {}

function fail(message) {
  throw new PortabilityError(message);
}

function requireCondition(condition, message) {
  if (!condition) fail(message);
}

function requireExact(actual, expected, label) {
  if (canonicalText(actual) !== canonicalText(expected)) {
    fail(
      `${label}: expected ${canonicalText(expected)}, got ${canonicalText(actual)}`,
    );
  }
}

function compareAscii(left, right) {
  return Buffer.compare(Buffer.from(left, "ascii"), Buffer.from(right, "ascii"));
}

function requirePrintableAscii(value, label, { allowEmpty = false } = {}) {
  requireCondition(typeof value === "string", `${label}: expected a string`);
  requireCondition(allowEmpty || value.length > 0, `${label}: empty string`);
  requireCondition(
    /^[\x20-\x7e]*$/.test(value),
    `${label}: expected printable ASCII`,
  );
}

function canonicalText(value, label = "canonical JSON") {
  if (value === null) return "null";
  if (value === true) return "true";
  if (value === false) return "false";
  if (typeof value === "number") {
    requireCondition(
      Number.isSafeInteger(value) &&
        !Object.is(value, -0) &&
        Math.abs(value) <= MAX_SAFE_INTEGER,
      `${label}: number is not a portable safe integer`,
    );
    return String(value);
  }
  if (typeof value === "string") {
    requirePrintableAscii(value, `${label} string`, { allowEmpty: true });
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return `[${value
      .map((item, index) => canonicalText(item, `${label}[${index}]`))
      .join(",")}]`;
  }
  requireCondition(
    typeof value === "object" && Object.getPrototypeOf(value) === Object.prototype,
    `${label}: unsupported value`,
  );
  const keys = Object.keys(value).sort(compareAscii);
  return `{${keys
    .map((key) => {
      requirePrintableAscii(key, `${label} key`, { allowEmpty: true });
      return `${JSON.stringify(key)}:${canonicalText(value[key], `${label}.${key}`)}`;
    })
    .join(",")}}`;
}

function canonicalBytes(value, label) {
  return Buffer.from(canonicalText(value, label), "utf8");
}

function measureCanonicalByteLength(value, maximumBytes, label) {
  requireCondition(
    Number.isSafeInteger(maximumBytes) && maximumBytes >= 0,
    `${label}: invalid canonical byte bound`,
  );
  let total = 0;
  const pending = [{ kind: "node", label, value }];

  function addBytes(count) {
    requireCondition(
      Number.isSafeInteger(count) && count >= 0,
      `${label}: invalid canonical byte contribution`,
    );
    total += count;
    requireCondition(
      Number.isSafeInteger(total) && total <= maximumBytes,
      `${label}: canonical JSON exceeds ${maximumBytes} bytes`,
    );
  }

  while (pending.length > 0) {
    const current = pending.pop();
    if (current.kind === "array-frame") {
      if (current.nextIndex < current.value.length) {
        const nextIndex = current.nextIndex;
        pending.push({ ...current, nextIndex: nextIndex + 1 });
        pending.push({
          kind: "node",
          label: `${current.label}[${nextIndex}]`,
          value: current.value[nextIndex],
        });
      }
      continue;
    }
    if (current.kind === "object-frame") {
      if (current.nextIndex < current.keys.length) {
        const key = current.keys[current.nextIndex];
        pending.push({ ...current, nextIndex: current.nextIndex + 1 });
        pending.push({
          kind: "node",
          label: `${current.label}.${key}`,
          value: current.value[key],
        });
      }
      continue;
    }
    requireCondition(
      current.kind === "node",
      `${label}: unknown canonical measurement task`,
    );
    const item = current.value;
    if (item === null) {
      addBytes(4);
    } else if (item === true) {
      addBytes(4);
    } else if (item === false) {
      addBytes(5);
    } else if (typeof item === "number") {
      requireCondition(
        Number.isSafeInteger(item) && !Object.is(item, -0),
        `${current.label}: number is not a portable safe integer`,
      );
      addBytes(String(item).length);
    } else if (typeof item === "string") {
      requirePrintableAscii(item, `${current.label} string`, {
        allowEmpty: true,
      });
      addBytes(Buffer.byteLength(JSON.stringify(item), "utf8"));
    } else if (Array.isArray(item)) {
      addBytes(2 + Math.max(0, item.length - 1));
      if (item.length > 0) {
        pending.push({
          kind: "array-frame",
          label: current.label,
          nextIndex: 0,
          value: item,
        });
      }
    } else {
      requireCondition(
        typeof item === "object" &&
          Object.getPrototypeOf(item) === Object.prototype,
        `${current.label}: unsupported value`,
      );
      const keys = Object.keys(item);
      addBytes(2 + Math.max(0, keys.length - 1));
      for (let index = keys.length - 1; index >= 0; index -= 1) {
        const key = keys[index];
        requirePrintableAscii(key, `${current.label} key`, { allowEmpty: true });
        addBytes(Buffer.byteLength(JSON.stringify(key), "utf8") + 1);
      }
      if (keys.length > 0) {
        pending.push({
          keys,
          kind: "object-frame",
          label: current.label,
          nextIndex: 0,
          value: item,
        });
      }
    }
  }
  return total;
}

function boundedCanonicalBytes(value, maximumBytes, label) {
  const measured = measureCanonicalByteLength(value, maximumBytes, label);
  const raw = canonicalBytes(value, label);
  requireCondition(
    raw.length === measured,
    `${label}: measured and encoded canonical byte lengths differ`,
  );
  return raw;
}

function countJsonStringCharacters(
  value,
  label,
  maximumStringCharacters = MAX_JSON_STRING_CHARS,
) {
  requireCondition(typeof value === "string", `${label}: expected a string`);
  let characters = 0;
  for (let index = 0; index < value.length; index += 1) {
    const codeUnit = value.charCodeAt(index);
    if (codeUnit >= 0xd800 && codeUnit <= 0xdbff) {
      requireCondition(
        index + 1 < value.length &&
          value.charCodeAt(index + 1) >= 0xdc00 &&
          value.charCodeAt(index + 1) <= 0xdfff,
        `${label}: string contains a lone high surrogate`,
      );
      index += 1;
    } else {
      requireCondition(
        codeUnit < 0xdc00 || codeUnit > 0xdfff,
        `${label}: string contains a lone low surrogate`,
      );
    }
    characters += 1;
    requireCondition(
      characters <= maximumStringCharacters,
      `${label}: JSON string exceeds ${maximumStringCharacters} characters`,
    );
  }
  return characters;
}

function requireJsonDepth(
  value,
  maximumDepth,
  label,
  {
    maximumItems = MAX_JSON_ITEMS,
    maximumStringCharacters = MAX_JSON_STRING_CHARS,
    maximumTotalStringCharacters = MAX_JSON_TOTAL_STRING_CHARS,
  } = {},
) {
  requireCondition(
    Number.isSafeInteger(maximumDepth) && maximumDepth >= 0,
    `${label}: invalid maximum depth`,
  );
  const pending = [{ depth: 0, kind: "node", value }];
  let itemCount = 0;
  let maximumObservedDepth = 0;
  let totalStringCharacters = 0;

  function addString(stringValue, stringLabel) {
    itemCount += 1;
    requireCondition(
      itemCount <= maximumItems,
      `${label}: JSON item count exceeds ${maximumItems}`,
    );
    totalStringCharacters += countJsonStringCharacters(
      stringValue,
      stringLabel,
      maximumStringCharacters,
    );
    requireCondition(
      totalStringCharacters <= maximumTotalStringCharacters,
      `${label}: total JSON string content exceeds ${maximumTotalStringCharacters} characters`,
    );
  }

  function pushPending(task) {
    pending.push(task);
    requireCondition(
      pending.length <= maximumDepth + 2,
      `${label}: traversal frontier exceeds its depth-derived bound`,
    );
  }
  while (pending.length > 0) {
    const current = pending.pop();
    if (current.kind === "array-frame") {
      if (current.nextIndex < current.value.length) {
        const nextIndex = current.nextIndex;
        pushPending({ ...current, nextIndex: nextIndex + 1 });
        pushPending({
          depth: current.depth + 1,
          kind: "node",
          value: current.value[nextIndex],
        });
      }
      continue;
    }
    if (current.kind === "object-frame") {
      if (current.nextIndex < current.keys.length) {
        const key = current.keys[current.nextIndex];
        pushPending({ ...current, nextIndex: current.nextIndex + 1 });
        pushPending({
          depth: current.depth + 1,
          kind: "node",
          value: current.value[key],
        });
      }
      continue;
    }
    requireCondition(current.kind === "node", `${label}: unknown traversal task`);
    itemCount += 1;
    requireCondition(
      itemCount <= maximumItems,
      `${label}: JSON item count exceeds ${maximumItems}`,
    );
    requireCondition(
      current.depth <= maximumDepth,
      `${label}: exceeds ${maximumDepth} JSON levels from root depth 0`,
    );
    maximumObservedDepth = Math.max(maximumObservedDepth, current.depth);
    if (typeof current.value === "string") {
      itemCount -= 1;
      addString(current.value, `${label} string`);
    }
    if (Array.isArray(current.value) && current.value.length > 0) {
      pushPending({
        depth: current.depth,
        kind: "array-frame",
        nextIndex: 0,
        value: current.value,
      });
    } else if (
      current.value !== null &&
      typeof current.value === "object" &&
      Object.getPrototypeOf(current.value) === Object.prototype
    ) {
      const keys = Object.keys(current.value);
      for (const key of keys) {
        addString(key, `${label} object key`);
      }
      if (keys.length > 0) {
        pushPending({
          depth: current.depth,
          keys,
          kind: "object-frame",
          nextIndex: 0,
          value: current.value,
        });
      }
    }
  }
  return {
    itemCount,
    maximumDepth: maximumObservedDepth,
    totalStringCharacters,
  };
}

function scanJsonStringToken(
  text,
  openingIndex,
  label,
  maximumStringCharacters = MAX_JSON_STRING_CHARS,
) {
  let characters = 0;
  let pendingHighSurrogate = false;

  function addCharacter() {
    characters += 1;
    requireCondition(
      characters <= maximumStringCharacters,
      `${label}: JSON string exceeds ${maximumStringCharacters} characters`,
    );
  }

  function flushPendingHighSurrogate() {
    if (pendingHighSurrogate) {
      addCharacter();
      pendingHighSurrogate = false;
    }
  }

  for (let index = openingIndex + 1; index < text.length; index += 1) {
    const codeUnit = text.charCodeAt(index);
    if (codeUnit === 0x22) {
      flushPendingHighSurrogate();
      return { characters, closingIndex: index };
    }
    requireCondition(codeUnit >= 0x20, `${label}: unescaped control in JSON string`);
    if (codeUnit === 0x5c) {
      index += 1;
      requireCondition(index < text.length, `${label}: unterminated JSON escape`);
      const escape = text[index];
      if (escape !== "u") {
        requireCondition(
          '"\\/bfnrt'.includes(escape),
          `${label}: invalid JSON string escape`,
        );
        flushPendingHighSurrogate();
        addCharacter();
        continue;
      }
      requireCondition(
        index + 4 < text.length,
        `${label}: truncated JSON Unicode escape`,
      );
      const digits = text.slice(index + 1, index + 5);
      requireCondition(
        /^[0-9a-fA-F]{4}$/.test(digits),
        `${label}: invalid JSON Unicode escape`,
      );
      const escapedCodeUnit = Number.parseInt(digits, 16);
      index += 4;
      if (pendingHighSurrogate) {
        if (escapedCodeUnit >= 0xdc00 && escapedCodeUnit <= 0xdfff) {
          addCharacter();
          pendingHighSurrogate = false;
        } else {
          addCharacter();
          pendingHighSurrogate = false;
          if (escapedCodeUnit >= 0xd800 && escapedCodeUnit <= 0xdbff) {
            pendingHighSurrogate = true;
          } else {
            addCharacter();
          }
        }
      } else if (escapedCodeUnit >= 0xd800 && escapedCodeUnit <= 0xdbff) {
        pendingHighSurrogate = true;
      } else {
        addCharacter();
      }
      continue;
    }
    flushPendingHighSurrogate();
    if (codeUnit >= 0xd800 && codeUnit <= 0xdbff) {
      requireCondition(
        index + 1 < text.length &&
          text.charCodeAt(index + 1) >= 0xdc00 &&
          text.charCodeAt(index + 1) <= 0xdfff,
        `${label}: raw JSON string contains a lone high surrogate`,
      );
      index += 1;
    } else {
      requireCondition(
        codeUnit < 0xdc00 || codeUnit > 0xdfff,
        `${label}: raw JSON string contains a lone low surrogate`,
      );
    }
    addCharacter();
  }
  fail(`${label}: unterminated JSON string`);
}

function requireJsonTextBounds(
  text,
  maximumDepth,
  label,
  {
    maximumItems = MAX_JSON_ITEMS,
    maximumStringCharacters = MAX_JSON_STRING_CHARS,
    maximumTotalStringCharacters = MAX_JSON_TOTAL_STRING_CHARS,
  } = {},
) {
  requireCondition(typeof text === "string", `${label}: expected decoded text`);
  requireCondition(
    Number.isSafeInteger(maximumDepth) && maximumDepth >= 0,
    `${label}: invalid maximum depth`,
  );
  const frames = [];
  let rootState = "value";
  let itemCount = 0;
  let maximumObservedDepth = 0;
  let totalStringCharacters = 0;

  function addItem() {
    itemCount += 1;
    requireCondition(
      itemCount <= maximumItems,
      `${label}: JSON item count exceeds ${maximumItems}`,
    );
  }

  function addStringCharacters(characters) {
    totalStringCharacters += characters;
    requireCondition(
      totalStringCharacters <= maximumTotalStringCharacters,
      `${label}: total JSON string content exceeds ${maximumTotalStringCharacters} characters`,
    );
  }

  function startValue() {
    requireCondition(
      frames.length <= maximumDepth,
      `${label}: exceeds ${maximumDepth} JSON levels from root depth 0`,
    );
    maximumObservedDepth = Math.max(maximumObservedDepth, frames.length);
    if (frames.length === 0) {
      requireCondition(rootState === "value", `${label}: unexpected root value`);
      rootState = "in-value";
      return;
    }
    const frame = frames.at(-1);
    if (frame.kind === "array") {
      requireCondition(
        frame.state === "value-or-end" || frame.state === "value",
        `${label}: unexpected array value`,
      );
    } else {
      requireCondition(
        frame.state === "value",
        `${label}: unexpected object value`,
      );
    }
    frame.state = "in-value";
  }

  function finishValue() {
    if (frames.length === 0) {
      requireCondition(
        rootState === "in-value",
        `${label}: unexpected completed root value`,
      );
      rootState = "done";
      return;
    }
    const frame = frames.at(-1);
    requireCondition(
      frame.state === "in-value",
      `${label}: completed value is not expected`,
    );
    frame.state = "comma-or-end";
  }

  for (let index = 0; index < text.length; index += 1) {
    const character = text[index];
    if (["\t", "\n", "\r", " "].includes(character)) continue;
    if (character === '"') {
      const stringToken = scanJsonStringToken(
        text,
        index,
        label,
        maximumStringCharacters,
      );
      index = stringToken.closingIndex;
      addItem();
      addStringCharacters(stringToken.characters);
      const frame = frames.at(-1);
      if (
        frame !== undefined &&
        frame.kind === "object" &&
        (frame.state === "key-or-end" || frame.state === "key")
      ) {
        frame.state = "colon";
      } else {
        startValue();
        finishValue();
      }
      continue;
    }
    if (character === "{" || character === "[") {
      startValue();
      addItem();
      frames.push({
        kind: character === "{" ? "object" : "array",
        state: character === "{" ? "key-or-end" : "value-or-end",
      });
      continue;
    }
    if (character === "}" || character === "]") {
      requireCondition(frames.length > 0, `${label}: unmatched closing token`);
      const frame = frames.at(-1);
      const expectedKind = character === "}" ? "object" : "array";
      requireCondition(
        frame.kind === expectedKind &&
          (frame.state === "key-or-end" ||
            frame.state === "value-or-end" ||
            frame.state === "comma-or-end"),
        `${label}: unexpected closing token`,
      );
      frames.pop();
      finishValue();
      continue;
    }
    if (character === ":") {
      const frame = frames.at(-1);
      requireCondition(
        frame !== undefined &&
          frame.kind === "object" &&
          frame.state === "colon",
        `${label}: unexpected colon`,
      );
      frame.state = "value";
      continue;
    }
    if (character === ",") {
      const frame = frames.at(-1);
      requireCondition(
        frame !== undefined && frame.state === "comma-or-end",
        `${label}: unexpected comma`,
      );
      frame.state = frame.kind === "object" ? "key" : "value";
      continue;
    }
    startValue();
    addItem();
    while (
      index + 1 < text.length &&
      !["\t", "\n", "\r", " ", ",", "]", "}"].includes(text[index + 1])
    ) {
      index += 1;
    }
    finishValue();
  }
  requireCondition(
    frames.length === 0 && rootState === "done",
    `${label}: incomplete JSON structure`,
  );
  return {
    itemCount,
    maximumDepth: maximumObservedDepth,
    totalStringCharacters,
  };
}

function requireRawJsonDepth(raw, maximumDepth, label) {
  requireCondition(Buffer.isBuffer(raw), `${label}: expected raw bytes`);
  return requireJsonTextBounds(decodeUtf8(raw, label), maximumDepth, label);
}

function sha256(raw) {
  return crypto.createHash("sha256").update(raw).digest("hex");
}

function domainHex(asciiLabel) {
  requireCondition(
    typeof asciiLabel === "string" &&
      asciiLabel.length > 0 &&
      /^[\x21-\x7e]+$/.test(asciiLabel),
    "domain label is not nonempty visible ASCII",
  );
  return Buffer.from(`${asciiLabel}\0`, "ascii").toString("hex");
}

function uint64be(value) {
  requireCondition(
    Number.isSafeInteger(value) && value >= 0,
    "uint64 framing length is invalid",
  );
  const raw = Buffer.alloc(8);
  raw.writeBigUInt64BE(BigInt(value));
  return raw;
}

function parseDomainHex(value, label) {
  requireCondition(
    typeof value === "string" &&
      value.length > 0 &&
      value.length % 2 === 0 &&
      /^[0-9a-f]+$/.test(value),
    `${label}: invalid lowercase domain hex`,
  );
  const domain = Buffer.from(value, "hex");
  requireCondition(domain.at(-1) === 0, `${label}: domain lacks terminal NUL`);
  requireCondition(
    !domain.subarray(0, -1).includes(0),
    `${label}: domain contains an embedded NUL`,
  );
  return domain;
}

function framedCanonicalSha256(domainHex, value, label) {
  const payload = canonicalBytes(value, label);
  return sha256(
    Buffer.concat([
      parseDomainHex(domainHex, `${label} domain`),
      uint64be(payload.length),
      payload,
    ]),
  );
}

function directCanonicalSha256(domainHex, value, label) {
  return sha256(
    Buffer.concat([
      parseDomainHex(domainHex, `${label} domain`),
      canonicalBytes(value, label),
    ]),
  );
}

function statFingerprint(value) {
  return [
    value.dev,
    value.ino,
    value.mode,
    value.nlink,
    value.uid,
    value.size,
    value.mtimeNs,
    value.ctimeNs,
  ].map(String);
}

function resolveRepositoryPath(relativePath, label) {
  requirePrintableAscii(relativePath, label);
  requireCondition(
    !path.isAbsolute(relativePath) &&
      !relativePath.includes("\\") &&
      relativePath.split("/").every((part) => part && part !== "." && part !== ".."),
    `${label}: path is not a closed repository-relative POSIX path`,
  );
  const absolute = path.resolve(ROOT, ...relativePath.split("/"));
  requireCondition(
    absolute.startsWith(`${ROOT}${path.sep}`),
    `${label}: path escapes the repository`,
  );
  const parent = path.dirname(absolute);
  requireCondition(
    fs.realpathSync.native(parent) === parent,
    `${label}: parent path contains a symlink`,
  );
  return absolute;
}

function readExactBoundedDescriptor(
  descriptor,
  expectedBytes,
  maximumBytes,
  label,
  readOperation = fs.readSync,
) {
  requireCondition(
    Number.isSafeInteger(expectedBytes) && expectedBytes > 0,
    `${label}: expected size is invalid`,
  );
  requireCondition(
    Number.isSafeInteger(maximumBytes) && maximumBytes > 0,
    `${label}: maximum size is invalid`,
  );
  requireCondition(
    expectedBytes <= maximumBytes,
    `${label}: expected size exceeds ${maximumBytes}`,
  );
  const raw = Buffer.allocUnsafe(expectedBytes);
  let offset = 0;
  while (offset < expectedBytes) {
    const requested = expectedBytes - offset;
    const bytesRead = readOperation(
      descriptor,
      raw,
      offset,
      requested,
      null,
    );
    requireCondition(
      Number.isSafeInteger(bytesRead) && bytesRead > 0 && bytesRead <= requested,
      `${label}: short or invalid bounded read`,
    );
    offset += bytesRead;
  }
  const sentinel = Buffer.allocUnsafe(1);
  const extraBytes = readOperation(descriptor, sentinel, 0, 1, null);
  requireCondition(
    Number.isSafeInteger(extraBytes) && extraBytes >= 0 && extraBytes <= 1,
    `${label}: invalid extending-read result`,
  );
  requireCondition(extraBytes === 0, `${label}: extending read`);
  return raw;
}

function readBounded(relativePath, maximumBytes, label) {
  requireCondition(
    Number.isSafeInteger(maximumBytes) && maximumBytes > 0,
    `${label}: maximum size is invalid`,
  );
  const absolute = resolveRepositoryPath(relativePath, label);
  const beforePath = fs.lstatSync(absolute, { bigint: true });
  requireCondition(beforePath.isFile(), `${label}: expected a regular file`);
  requireCondition(!beforePath.isSymbolicLink(), `${label}: symlink is forbidden`);
  requireCondition(beforePath.nlink === 1n, `${label}: hard link is unsupported`);
  requireCondition(
    beforePath.size > 0n && beforePath.size <= BigInt(maximumBytes),
    `${label}: size is outside 1..${maximumBytes}`,
  );
  const noFollow = fs.constants.O_NOFOLLOW ?? 0;
  requireCondition(noFollow !== 0, `${label}: O_NOFOLLOW is unavailable`);
  const descriptor = fs.openSync(
    absolute,
    fs.constants.O_RDONLY | noFollow,
  );
  try {
    const opened = fs.fstatSync(descriptor, { bigint: true });
    requireExact(
      statFingerprint(opened),
      statFingerprint(beforePath),
      `${label} opened inode`,
    );
    const raw = readExactBoundedDescriptor(
      descriptor,
      Number(opened.size),
      maximumBytes,
      label,
    );
    const after = fs.fstatSync(descriptor, { bigint: true });
    requireExact(
      statFingerprint(after),
      statFingerprint(opened),
      `${label} stable opened inode`,
    );
    requireCondition(
      raw.length === Number(opened.size),
      `${label}: short or extending read`,
    );
    const finalPath = fs.lstatSync(absolute, { bigint: true });
    requireExact(
      statFingerprint(finalPath),
      statFingerprint(opened),
      `${label} stable path`,
    );
    const fingerprint = statFingerprint(opened);
    const prior = READ_SNAPSHOTS.get(relativePath);
    if (prior === undefined) {
      const inodeKey = `${fingerprint[0]}:${fingerprint[1]}`;
      const priorPath = READ_INODES.get(inodeKey);
      requireCondition(
        priorPath === undefined || priorPath === relativePath,
        `${label}: opened inode aliases ${priorPath}`,
      );
      READ_INODES.set(inodeKey, relativePath);
      READ_SNAPSHOTS.set(relativePath, {
        fingerprint,
        label,
        maximumBytes,
        raw: Buffer.from(raw),
      });
    } else {
      requireExact(fingerprint, prior.fingerprint, `${label} repository snapshot`);
      requireCondition(
        raw.equals(prior.raw),
        `${label}: repository bytes changed across source reads`,
      );
    }
    return raw;
  } finally {
    fs.closeSync(descriptor);
  }
}

function requireReadSnapshotsUnchanged() {
  for (const [relativePath, snapshot] of [...READ_SNAPSHOTS.entries()]) {
    const current = readBounded(
      relativePath,
      snapshot.maximumBytes,
      `${snapshot.label} final stability check`,
    );
    requireCondition(
      current.equals(snapshot.raw),
      `${snapshot.label}: repository bytes changed before verification completed`,
    );
  }
}

function requireCanonicalIntegerTokens(raw, label) {
  requireCondition(Buffer.isBuffer(raw), `${label}: expected raw bytes`);
  let inString = false;
  let escaped = false;
  for (let index = 0; index < raw.length; index += 1) {
    const octet = raw[index];
    if (inString) {
      if (escaped) {
        escaped = false;
      } else if (octet === 0x5c) {
        escaped = true;
      } else if (octet === 0x22) {
        inString = false;
      }
      continue;
    }
    if (octet === 0x22) {
      inString = true;
      continue;
    }
    if (octet !== 0x2d && (octet < 0x30 || octet > 0x39)) continue;
    let end = index + 1;
    while (
      end < raw.length &&
      ![
        0x09,
        0x0a,
        0x0d,
        0x20,
        0x2c,
        0x3a,
        0x5d,
        0x7d,
      ].includes(raw[end])
    ) {
      end += 1;
    }
    const tokenRaw = raw.subarray(index, end);
    requireCondition(
      tokenRaw.length <= MAX_JSON_NUMBER_CHARS,
      `${label}: JSON number exceeds ${MAX_JSON_NUMBER_CHARS} characters`,
    );
    requireCondition(
      tokenRaw.every((value) => value >= 0x20 && value <= 0x7e),
      `${label}: non-ASCII JSON number token`,
    );
    const token = tokenRaw.toString("ascii");
    requireCondition(
      /^(?:0|-[1-9][0-9]*|[1-9][0-9]*)$/.test(token),
      `${label}: noncanonical, fractional, exponent, or negative-zero number token ${JSON.stringify(token)}`,
    );
    let integer;
    try {
      integer = BigInt(token);
    } catch {
      fail(`${label}: invalid integer token ${JSON.stringify(token)}`);
    }
    requireCondition(
      integer >= -BigInt(MAX_SAFE_INTEGER) &&
        integer <= BigInt(MAX_SAFE_INTEGER),
      `${label}: integer token is outside the portable safe range`,
    );
    index = end - 1;
  }
}

function parseJsonWithPreflight(raw, maximumDepth, label) {
  requireCanonicalIntegerTokens(raw, label);
  const text = decodeUtf8(raw, label);
  const preflightMetrics = requireJsonTextBounds(text, maximumDepth, label);
  let value;
  try {
    value = JSON.parse(text);
  } catch (error) {
    fail(`${label}: invalid JSON: ${error.message}`);
  }
  const nativeMetrics = requireJsonDepth(value, maximumDepth, label);
  requireExact(
    nativeMetrics,
    preflightMetrics,
    `${label} preflight/native resource metrics`,
  );
  return value;
}

function parseCanonicalDocument(raw, label) {
  const value = parseJsonWithPreflight(raw, MAX_JSON_DEPTH, label);
  const expected = Buffer.concat([canonicalBytes(value, label), Buffer.from("\n")]);
  requireCondition(raw.equals(expected), `${label}: document is not canonical JSON`);
  return value;
}

function requireClosedKeys(value, expectedKeys, label) {
  requireCondition(
    value !== null && typeof value === "object" && !Array.isArray(value),
    `${label}: expected an object`,
  );
  requireExact(
    Object.keys(value).sort(compareAscii),
    [...expectedKeys].sort(compareAscii),
    `${label} keys`,
  );
}

function contentIdentity(raw, row, label) {
  requireClosedKeys(row, ["byte_length", "path", "sha256"], label);
  requireCondition(row.byte_length === raw.length, `${label}: byte length mismatch`);
  requireCondition(row.sha256 === sha256(raw), `${label}: SHA-256 mismatch`);
}

function sourceAnchor(adrId) {
  return `ncp-b01-selector-allocation-${adrId.toLowerCase()}-v1`;
}

function requireCommitment(commitment, expectedDomain, label) {
  requireClosedKeys(
    commitment,
    ["algorithm", "canonicalization", "domain_hex", "projection_sha256"],
    label,
  );
  requireCondition(
    commitment.algorithm === COMMITMENT_ALGORITHM,
    `${label}: unsupported algorithm`,
  );
  requireCondition(
    commitment.canonicalization === COMMITMENT_CANONICALIZATION,
    `${label}: unsupported canonicalization`,
  );
  requireCondition(
    commitment.domain_hex === expectedDomain,
    `${label}: substituted domain`,
  );
}

function requireSortedUniqueStrings(values, allowed, label) {
  requireCondition(Array.isArray(values), `${label}: expected an array`);
  for (const [index, value] of values.entries()) {
    requirePrintableAscii(value, `${label}[${index}]`);
    requireCondition(
      allowed === undefined || allowed.includes(value),
      `${label}[${index}]: unknown value`,
    );
  }
  requireExact(values, [...values].sort(compareAscii), `${label} order`);
  requireCondition(
    new Set(values).size === values.length,
    `${label}: duplicate value`,
  );
}

function decodeUtf8(raw, label) {
  try {
    return new TextDecoder("utf-8", { fatal: true }).decode(raw);
  } catch (error) {
    fail(`${label}: source is not UTF-8: ${error.message}`);
  }
}

function proseIdentifiers(texts) {
  const accepted = new Set();
  const all = new Set();
  for (const text of texts) {
    for (const match of text.matchAll(/\b[A-Za-z][A-Za-z0-9_]*\b/g)) {
      all.add(match[0]);
    }
    const headings = [
      ...text.matchAll(/^## ([^\r\n]+?)[ \t]*\r?$/gm),
    ];
    for (const [index, heading] of headings.entries()) {
      if (!ACCEPTED_ALLOCATION_PROSE_HEADINGS.has(heading[1])) continue;
      const sectionEnd =
        index + 1 < headings.length ? headings[index + 1].index : text.length;
      const section = text.slice(heading.index + heading[0].length, sectionEnd);
      for (const match of section.matchAll(/\b[A-Za-z][A-Za-z0-9_]*\b/g)) {
        accepted.add(match[0]);
      }
    }
  }
  return { accepted, all };
}

function declaringSelectorIds(row) {
  const selectorIds = new Set();
  for (const origin of row.origin_evidence) {
    const match = /^selector-id::([A-Z][A-Z0-9_]*)/.exec(
      origin.semantic_location,
    );
    if (match !== null) selectorIds.add(match[1]);
  }
  return [...selectorIds].sort(compareAscii);
}

function bodyTypeIsAdr006(exactName) {
  return (
    CANDIDATE_BODY_ADR006_TYPE_PREFIXES.some((prefix) =>
      exactName.startsWith(prefix),
    ) ||
    (exactName.startsWith("BodySessionControl") &&
      CANDIDATE_BODY_CONTROL_ADR006_TYPE_FRAGMENTS.some((fragment) =>
        exactName.includes(fragment),
      ))
  );
}

function candidateAllocationAdrId(row, acceptedByAdr) {
  const candidateSelectors = new Set();
  if (row.kind === "SELECTOR") {
    candidateSelectors.add(row.exact_name);
  } else if (row.kind === "RESOURCE") {
    candidateSelectors.add(row.exact_name.split(".", 1)[0]);
  } else if (row.kind === "STATE") {
    const match =
      /^state-id::([A-Z][A-Z0-9_]*)\.([A-Z][A-Z0-9_]*)\.([A-Z][A-Z0-9_]*)$/.exec(
        row.semantic_ref,
      );
    requireCondition(match !== null, "proposal STATE has an invalid semantic ref");
    candidateSelectors.add(match[1]);
  } else if (row.kind === "EVENT") {
    for (const origin of row.origin_evidence) {
      const match =
        /^selector-id::([A-Z][A-Z0-9_]*)\/event-id::/.exec(
          origin.semantic_location,
        );
      if (match !== null) candidateSelectors.add(match[1]);
    }
  }

  if (row.kind === "PROFILE") {
    if (row.semantic_ref.startsWith("/actor_profiles/")) return "ADR-011";
    if (row.semantic_ref.startsWith("/closed_event_profile_catalog/")) {
      return "ADR-001";
    }
    if (row.semantic_ref.startsWith("/joint_selector_transaction_profiles/")) {
      return CANDIDATE_ADR001_JOINT_PROFILES.has(row.exact_name)
        ? "ADR-001"
        : "ADR-004";
    }
    if (row.semantic_ref.startsWith("/sidecar_binding_profiles/")) {
      return "ADR-001";
    }
    const rootProfileKey = row.semantic_ref.startsWith("/")
      ? row.semantic_ref.split("/", 3)[1]
      : "";
    if (Object.hasOwn(CANDIDATE_PROFILE_ADR, rootProfileKey)) {
      return CANDIDATE_PROFILE_ADR[rootProfileKey];
    }
    return CANDIDATE_PROFILE_ADR[row.exact_name] ?? "UNMAPPED_SHARED";
  }

  if (
    candidateSelectors.size === 1 &&
    candidateSelectors.has("BODY_SESSION_CONTROL")
  ) {
    if (row.kind === "STATE") {
      const match =
        /^state-id::([A-Z][A-Z0-9_]*)\.([A-Z][A-Z0-9_]*)\.([A-Z][A-Z0-9_]*)$/.exec(
          row.semantic_ref,
        );
      requireCondition(match !== null, "body STATE has an invalid semantic ref");
      return CANDIDATE_BODY_ADR006_STATE_DOMAINS.has(match[2])
        ? "ADR-006"
        : "ADR-007";
    }
    if (
      row.kind === "RESOURCE" &&
      row.exact_name.startsWith("BODY_SESSION_CONTROL.STATE_DOMAIN.")
    ) {
      const stateDomain = row.exact_name.split(".").at(-1);
      return CANDIDATE_BODY_ADR006_STATE_DOMAINS.has(stateDomain)
        ? "ADR-006"
        : "ADR-007";
    }
    if (row.kind === "EVENT") {
      return acceptedByAdr.get("ADR-006").has(row.exact_name)
        ? "ADR-006"
        : "ADR-007";
    }
    return bodyTypeIsAdr006(row.exact_name) ? "ADR-006" : "ADR-007";
  }
  if (candidateSelectors.size === 1) {
    return CANDIDATE_SELECTOR_ADR[[...candidateSelectors][0]] ?? "UNMAPPED_SHARED";
  }

  if (
    [
      "ProtectedSourceLogicalSessionCooperativeAnchor",
      "ProtectedSourceLogicalSessionNamespaceAnchor",
      "SourceLogicalSessionCooperativeAnchor",
      "SourceLogicalSessionNamespaceAnchor",
    ].some((prefix) => row.exact_name.startsWith(prefix))
  ) {
    return "ADR-004";
  }
  const slug = row.semantic_ref.split("::", 1)[0];
  if (slug.startsWith("cross-store-")) return "ADR-009";
  if (slug.startsWith("forwarding-")) return "ADR-003";
  if (
    [
      "imported-realm-security-",
      "installed-security-",
      "local-security-",
      "security-authority-",
    ].some((prefix) => slug.startsWith(prefix))
  ) {
    return "ADR-009";
  }
  if (
    [
      "anchor-observer-",
      "independent-anchor-",
      "installed-independent-anchor-",
      "observer-",
      "protected-independent-anchor-",
      "protected-observer-",
      "protected-trusted-delivery-",
      "qualified-observer-",
      "qualified-permanent-source-isolation-",
      "trusted-delivery-",
    ].some((prefix) => slug.startsWith(prefix))
  ) {
    return "ADR-004";
  }
  if (
    [
      "declaration-",
      "frame-admission-",
      "historical-admission-",
      "receiver-evidence-",
    ].some((prefix) => slug.startsWith(prefix))
  ) {
    return "ADR-005";
  }
  if (
    ["authorization-deadline-", "retention-quiescence-"].some((prefix) =>
      slug.startsWith(prefix),
    )
  ) {
    return "ADR-004";
  }
  if (slug.startsWith("typed-deadline-")) return "ADR-006";
  if (
    ["actuation-authority-", "physical-actuation-"].some((prefix) =>
      slug.startsWith(prefix),
    )
  ) {
    return "ADR-007";
  }
  if (slug.startsWith("body-")) {
    return bodyTypeIsAdr006(row.exact_name) ? "ADR-006" : "ADR-007";
  }
  return "UNMAPPED_SHARED";
}

function expectedRoute(row, acceptedByAdr) {
  const selectorIds = declaringSelectorIds(row);
  const suggestedAdrId = candidateAllocationAdrId(row, acceptedByAdr);
  if (suggestedAdrId === "UNMAPPED_SHARED") {
    return {
      basis: [],
      classId: "NO_TOTAL_RULE",
      suggestedAdrId,
      suggestedSourceAnchor: null,
    };
  }
  if (row.kind === "PROFILE") {
    return {
      basis: [row.semantic_ref],
      classId: "STRUCTURAL_PROFILE_RULE",
      suggestedAdrId,
      suggestedSourceAnchor: sourceAnchor(suggestedAdrId),
    };
  }
  if (selectorIds.length > 0) {
    if (
      canonicalText(selectorIds) === canonicalText(["BODY_SESSION_CONTROL"]) &&
      row.kind === "EVENT" &&
      suggestedAdrId === "ADR-006" &&
      acceptedByAdr.get("ADR-006").has(row.exact_name)
    ) {
      return {
        basis: [
          "BODY_SESSION_CONTROL",
          `accepted-prose::${suggestedAdrId}::${row.exact_name}`,
        ],
        classId: "BODY_ACCEPTED_PROSE_RULE",
        suggestedAdrId,
        suggestedSourceAnchor: sourceAnchor(suggestedAdrId),
      };
    }
    return {
      basis: selectorIds,
      classId:
        canonicalText(selectorIds) === canonicalText(["BODY_SESSION_CONTROL"])
          ? "BODY_DECLARATION_PARTITION_RULE"
          : "DECLARING_SELECTOR_REGISTRY_RULE",
      suggestedAdrId,
      suggestedSourceAnchor: sourceAnchor(suggestedAdrId),
    };
  }
  return {
    basis: [row.semantic_ref],
    classId: "SEMANTIC_REFERENCE_RULE",
    suggestedAdrId,
    suggestedSourceAnchor: sourceAnchor(suggestedAdrId),
  };
}

function expectedAmbiguityFlags(row, route, proseAdrIds, acceptedProseAdrIds) {
  const flags = new Set();
  const selectorIds = declaringSelectorIds(row);
  const usageSignals = row.signal_evidence.filter(
    (evidence) => evidence.evidence_kind === "SELECTOR_USAGE",
  );
  if (["EVENT", "TYPE"].includes(row.kind) && selectorIds.length === 0) {
    flags.add("NO_DECLARING_SELECTOR");
  }
  if (selectorIds.length > 1) flags.add("MULTIPLE_DECLARING_SELECTORS");
  if (usageSignals.length > 0) flags.add("SELECTOR_USAGE_SIGNAL_PRESENT");
  if (usageSignals.length > 1) flags.add("MULTIPLE_SELECTOR_USAGE_SIGNALS");
  if (
    row.signal_evidence.some(
      (evidence) => evidence.evidence_kind === "RESOURCE_BACKING",
    )
  ) {
    flags.add("RESOURCE_BACKING_SIGNAL_PRESENT");
  }
  if (
    row.signal_evidence.some(
      (evidence) =>
        evidence.evidence_kind === "STRUCTURAL_PROFILE_REFERENCE",
    )
  ) {
    flags.add("STRUCTURAL_PROFILE_REFERENCE_SIGNAL_PRESENT");
  }
  if (acceptedProseAdrIds.length === 0) {
    flags.add("NO_ACCEPTED_PROSE_MATCH");
  } else if (acceptedProseAdrIds.length > 1) {
    flags.add("MULTIPLE_ACCEPTED_PROSE_MATCHES");
  }
  if (proseAdrIds.length > 1) flags.add("MULTIPLE_PROSE_MENTIONS");
  if (
    ADR_IDS.includes(route.suggestedAdrId) &&
    acceptedProseAdrIds.length > 0 &&
    !acceptedProseAdrIds.includes(route.suggestedAdrId)
  ) {
    flags.add("SUGGESTED_ADR_DIFFERS_FROM_ACCEPTED_PROSE");
  }
  if (route.suggestedAdrId === "UNMAPPED_SHARED") {
    flags.add("UNMAPPED_SHARED");
  }
  return [...flags].sort(compareAscii);
}

function inventoryOracle(inventory) {
  const oracle = {};
  for (const key of [...ORACLE_KEYS].sort(compareAscii)) {
    requireCondition(
      Object.hasOwn(inventory, key),
      `allocation inventory lacks oracle field ${key}`,
    );
    oracle[key] = structuredClone(inventory[key]);
  }
  return oracle;
}

function reconstructExpanded(authoring, inventory) {
  const expanded = structuredClone(authoring);
  const binding = expanded.adr_allocation_inventory_binding;
  requireCondition(
    binding !== null && typeof binding === "object" && !Array.isArray(binding),
    "authoring source lacks its allocation inventory binding",
  );
  delete expanded.adr_allocation_inventory_binding;
  expanded.adr_allocation_oracle = inventoryOracle(inventory);
  const metadata = expanded.canonical_source_metadata;
  requireClosedKeys(
    metadata,
    ["$schema", "generated_by", "schema"],
    "canonical source metadata",
  );
  delete expanded.canonical_source_metadata;
  for (const key of ["$schema", "generated_by", "schema"]) {
    expanded[key] = metadata[key];
  }
  return { binding, expanded };
}

function requireFramedSuite(suite, label, outputField = "output") {
  requireCondition(suite.algorithm === "SHA256", `${label}: unsupported algorithm`);
  requireCondition(
    suite.canonicalization ===
      "UTF8_JSON_SORTED_KEYS_NO_INSIGNIFICANT_WHITESPACE",
    `${label}: unsupported canonicalization`,
  );
  requireCondition(
    suite.framing ===
      "DOMAIN_BYTES_THEN_UINT64_BE_CANONICAL_BYTE_LENGTH_THEN_CANONICAL_BYTES",
    `${label}: unsupported framing`,
  );
  requireCondition(
    suite[outputField] === "LOWERCASE_HEXADECIMAL_64_CHARACTERS",
    `${label}: unsupported output encoding`,
  );
}

function requireDirectSuite(suite, label) {
  requireCondition(suite.algorithm === "SHA256", `${label}: unsupported algorithm`);
  requireCondition(
    suite.canonicalization ===
      "UTF8_JSON_SORTED_KEYS_NO_INSIGNIFICANT_WHITESPACE",
    `${label}: unsupported canonicalization`,
  );
  requireCondition(
    suite.framing === "DOMAIN_BYTES_THEN_CANONICAL_PROJECTION_BYTES",
    `${label}: unsupported framing`,
  );
  requireCondition(
    suite.output === "LOWERCASE_HEXADECIMAL_64_CHARACTERS",
    `${label}: unsupported output encoding`,
  );
}

function sortedEvidence(evidence, allowedKinds, label) {
  requireCondition(Array.isArray(evidence), `${label}: expected an array`);
  const rows = evidence.map((row, index) => {
    requireClosedKeys(
      row,
      ["evidence_kind", "semantic_location"],
      `${label}[${index}]`,
    );
    requireCondition(
      allowedKinds.includes(row.evidence_kind),
      `${label}[${index}]: unknown evidence kind`,
    );
    requirePrintableAscii(
      row.semantic_location,
      `${label}[${index}].semantic_location`,
    );
    requireCondition(
      row.semantic_location === row.semantic_location.trim(),
      `${label}[${index}]: untrimmed semantic location`,
    );
    return structuredClone(row);
  });
  rows.sort((left, right) => {
    const kind = compareAscii(left.evidence_kind, right.evidence_kind);
    return kind || compareAscii(left.semantic_location, right.semantic_location);
  });
  requireExact(rows, evidence, `${label} canonical order`);
  requireCondition(
    new Set(rows.map((row) => canonicalText(row))).size === rows.length,
    `${label}: duplicate evidence row`,
  );
  return rows;
}

function compareIdentityRows(left, right) {
  for (let index = 0; index < 4; index += 1) {
    const compared = compareAscii(left[index], right[index]);
    if (compared) return compared;
  }
  return 0;
}

function verifyAllocationModel(proposal, profile) {
  const suite = profile.allocation_identity_commitment_suite;
  requireFramedSuite(
    suite,
    "allocation identity commitment suite",
    "unit_id_output",
  );
  requireCondition(
    suite.schema ===
      "ncp.b01-selector-allocation-identity-commitment-suite.v1",
    "allocation identity commitment suite schema changed",
  );
  requireCondition(
    suite.unit_id_domain_hex === MODEL_DOMAINS.unitId &&
      suite.model_projection_domain_hex === MODEL_DOMAINS.modelProjection &&
      suite.origin_signal_projection_domain_hex === MODEL_DOMAINS.originSignal,
    "allocation identity commitment suite substituted a domain",
  );
  requireExact(
    suite.identity_fields,
    ["kind", "exact_name", "semantic_ref"],
    "allocation identity fields",
  );
  requireExact(
    suite.model_projection_row_fields,
    ["kind", "exact_name", "semantic_ref", "unit_id"],
    "model projection row fields",
  );
  requireCondition(
    suite.identity_evidence_rule ===
      "ORIGINS_AND_SIGNALS_EXCLUDED_FROM_UNIT_ID_MODEL_PROJECTION_EQUALITY_AND_HASHING",
    "allocation identity suite permits evidence to change identity",
  );
  requireCondition(
    suite.signal_authority ===
      "ZERO_OR_MORE_CLOSED_NONAUTHORITATIVE_SIGNALS_NEVER_SELECT_IDENTITY_OR_ADR_ASSIGNMENT",
    "allocation signal evidence acquired identity or route authority",
  );
  requireExact(
    suite.origin_kinds,
    [
      "ARTIFACT_REGISTRY_ENTRY",
      "DECLARED_EVENT",
      "RESOURCE_DECLARATION",
      "SELECTOR_DECLARATION",
      "STATE_DECLARATION",
      "STRUCTURAL_PROFILE_DEFINITION",
      "SUBORDINATE_EVENT_DECLARATION",
    ],
    "allocation origin taxonomy",
  );
  requireExact(
    suite.signal_kinds,
    [
      "RESOURCE_BACKING",
      "SELECTOR_USAGE",
      "STRUCTURAL_PROFILE_REFERENCE",
    ],
    "allocation signal taxonomy",
  );

  const identityRows = [];
  const originSignalRows = [];
  const unitIds = new Set();
  for (const [index, row] of proposal.rows.entries()) {
    const identity = [row.kind, row.exact_name, row.semantic_ref];
    for (const [fieldIndex, value] of identity.entries()) {
      requirePrintableAscii(value, `proposal row ${index} identity ${fieldIndex}`);
    }
    const expectedUnitId = framedCanonicalSha256(
      suite.unit_id_domain_hex,
      identity,
      `proposal row ${index} unit identity`,
    );
    requireCondition(
      row.unit_id === expectedUnitId,
      `proposal row ${index}: forged unit ID`,
    );
    requireCondition(!unitIds.has(row.unit_id), `duplicate proposal unit ID`);
    unitIds.add(row.unit_id);
    const origins = sortedEvidence(
      row.origin_evidence,
      suite.origin_kinds,
      `proposal row ${index} origins`,
    );
    requireCondition(origins.length > 0, `proposal row ${index}: missing origin`);
    const signals = sortedEvidence(
      row.signal_evidence,
      suite.signal_kinds,
      `proposal row ${index} signals`,
    );
    identityRows.push([...identity, row.unit_id]);
    originSignalRows.push({
      exact_name: row.exact_name,
      kind: row.kind,
      origins,
      semantic_ref: row.semantic_ref,
      signals,
      unit_id: row.unit_id,
    });
  }
  identityRows.sort(compareIdentityRows);
  originSignalRows.sort((left, right) =>
    compareIdentityRows(
      [left.kind, left.exact_name, left.semantic_ref, left.unit_id],
      [right.kind, right.exact_name, right.semantic_ref, right.unit_id],
    ),
  );
  requireExact(
    proposal.rows.map((row) => [
      row.kind,
      row.exact_name,
      row.semantic_ref,
      row.unit_id,
    ]),
    identityRows,
    "proposal identity row order",
  );

  const modelSha256 = framedCanonicalSha256(
    suite.model_projection_domain_hex,
    identityRows,
    "model allocation projection",
  );
  const originSignalSha256 = framedCanonicalSha256(
    suite.origin_signal_projection_domain_hex,
    originSignalRows,
    "model origin/signal projection",
  );
  const modelCount = identityRows.length;
  for (const [actual, expected, label] of [
    [proposal.summary.model_allocation_count, modelCount, "proposal model count"],
    [
      proposal.summary.model_allocation_sha256,
      modelSha256,
      "proposal model digest",
    ],
    [
      proposal.summary.model_origin_signal_row_count,
      modelCount,
      "proposal origin/signal count",
    ],
    [
      proposal.summary.model_origin_signal_sha256,
      originSignalSha256,
      "proposal origin/signal digest",
    ],
    [
      proposal.source.model_projection.allocation_count,
      modelCount,
      "proposal source model count",
    ],
    [
      proposal.source.model_projection.allocation_sha256,
      modelSha256,
      "proposal source model digest",
    ],
    [
      proposal.source.model_projection.origin_signal_row_count,
      modelCount,
      "proposal source origin/signal count",
    ],
    [
      proposal.source.model_projection.origin_signal_sha256,
      originSignalSha256,
      "proposal source origin/signal digest",
    ],
    [profile.model_allocation_count, modelCount, "review profile model count"],
    [profile.model_allocation_sha256, modelSha256, "review profile model digest"],
    [
      profile.model_origin_signal_row_count,
      modelCount,
      "review profile origin/signal count",
    ],
    [
      profile.model_origin_signal_sha256,
      originSignalSha256,
      "review profile origin/signal digest",
    ],
  ]) {
    requireCondition(actual === expected, `${label}: mismatch`);
  }
  return { identityRows, modelCount, modelSha256, originSignalRows, originSignalSha256 };
}

function verifySemanticReviewSubject(expanded, commitment) {
  requireCondition(
    commitment.algorithm === "SHA256",
    "semantic review subject has an unsupported algorithm",
  );
  requireCondition(
    commitment.canonicalization === "NCP_PRINTABLE_ASCII_SAFE_INTEGER_JSON_V1",
    "semantic review subject has an unsupported canonicalization",
  );
  requireCondition(
    commitment.framing ===
      "DOMAIN_BYTES_THEN_UINT64_BE_CANONICAL_BYTE_LENGTH_THEN_CANONICAL_BYTES",
    "semantic review subject has unsupported framing",
  );
  requireCondition(
    commitment.output === "LOWERCASE_HEXADECIMAL_64_CHARACTERS",
    "semantic review subject has unsupported output encoding",
  );
  requireCondition(
    commitment.scalar_domain ===
      "NULL_BOOLEAN_SIGNED_INTEGER_ABS_LE_9007199254740991_PRINTABLE_ASCII_STRING_ONLY",
    "semantic review subject has an unsupported scalar domain",
  );
  requireCondition(
    commitment.root_depth === 0 &&
      commitment.maximum_nesting_depth === 64,
    "semantic review subject depth convention or maximum changed",
  );
  requireCondition(
    commitment.nesting_depth_counting ===
      "DOCUMENT_ROOT_IS_DEPTH_0_EACH_ARRAY_OR_OBJECT_CHILD_INCREMENTS_BY_1",
    "semantic review subject nesting-depth counting changed",
  );
  requireCondition(
    commitment.projection_rule ===
      "EXACT_TOP_LEVEL_OBJECT_AFTER_EXCLUDING_DECLARED_TOP_LEVEL_KEYS_NO_OTHER_FIELD_ELISION",
    "semantic review subject has an unsupported projection rule",
  );
  const subject = structuredClone(expanded);
  for (const key of commitment.excluded_top_level_keys) {
    requireCondition(
      Object.hasOwn(subject, key),
      `semantic review subject exclusion ${key} is absent`,
    );
    delete subject[key];
  }
  requireJsonDepth(
    subject,
    commitment.maximum_nesting_depth,
    "semantic review subject",
  );
  const payload = canonicalBytes(subject, "semantic review subject");
  requireCondition(
    payload.length <= commitment.maximum_canonical_bytes,
    "semantic review subject exceeds its declared byte bound",
  );
  const digest = sha256(
    Buffer.concat([
      parseDomainHex(commitment.domain_hex, "semantic review subject domain"),
      uint64be(payload.length),
      payload,
    ]),
  );
  requireCondition(
    commitment.byte_length === payload.length,
    "semantic review subject byte length mismatch",
  );
  requireCondition(commitment.sha256 === digest, "semantic review subject digest mismatch");
  return { byteLength: payload.length, sha256: digest };
}

function pointerSegment(value) {
  requirePrintableAscii(value, "semantic shape member name", { allowEmpty: true });
  return value.replaceAll("~", "~0").replaceAll("/", "~1");
}

function semanticShapeType(value, pointer) {
  if (value === null) return "null";
  if (value === true || value === false) return "boolean";
  if (Array.isArray(value)) return "array";
  if (typeof value === "string") {
    requirePrintableAscii(value, `semantic shape string at ${pointer}`, {
      allowEmpty: true,
    });
    return "string";
  }
  if (typeof value === "number") {
    requireCondition(
      Number.isSafeInteger(value) && !Object.is(value, -0),
      `semantic shape source has a noncanonical or unsafe integer at ${pointer}`,
    );
    return "integer";
  }
  if (
    typeof value === "object" &&
    Object.getPrototypeOf(value) === Object.prototype
  ) {
    return "object";
  }
  fail(`semantic shape source has a non-JSON value at ${pointer}`);
}

/**
 * Project one row at a time. The task-count frontier is depth-bounded. Open
 * object-key snapshots are globally entry-bounded, and their minimum row bytes
 * are charged before value access or sorting. Object ordering compares escaped
 * segments, so preflight constructs at most one full child pointer at a time.
 * It materializes child values and rows only after the aggregate can fit.
 */
function semanticShapeRows(expanded, suite) {
  for (const [field, minimum] of [
    ["maximum_entries", 1],
    ["maximum_nesting_depth", 0],
    ["maximum_pointer_characters", 0],
    ["maximum_projection_bytes", 2],
  ]) {
    requireCondition(
      Number.isSafeInteger(suite[field]) && suite[field] >= minimum,
      `semantic shape ${field} is invalid`,
    );
  }
  const rows = [];
  let discoveredEntries = 0;
  let projectionBytes = 2;
  let retainedObjectKeySnapshots = 0;
  function reserveNode(depth, pointer, value) {
    requireCondition(
      depth <= suite.maximum_nesting_depth,
      "semantic shape exceeds its declared nesting bound",
    );
    requireCondition(
      pointer.length <= suite.maximum_pointer_characters,
      "semantic shape exceeds its pointer bound",
    );
    requireCondition(
      discoveredEntries < suite.maximum_entries,
      "semantic shape exceeds its entry bound",
    );
    const row = [pointer, semanticShapeType(value, pointer)];
    const rowByteLength = canonicalBytes(
      row,
      `semantic shape row ${pointer}`,
    ).length;
    requireCondition(
      rowByteLength <= suite.maximum_projection_bytes,
      "semantic shape row exceeds its projection byte bound",
    );
    const nextProjectionBytes =
      projectionBytes + rowByteLength + (discoveredEntries === 0 ? 0 : 1);
    requireCondition(
      nextProjectionBytes <= suite.maximum_projection_bytes,
      "semantic shape exceeds its projection byte bound",
    );
    discoveredEntries += 1;
    projectionBytes = nextProjectionBytes;
    return { depth, kind: "node", pointer, row, value };
  }
  const pending = [reserveNode(0, "", expanded)];
  function pushPending(task) {
    pending.push(task);
    requireCondition(
      pending.length <= suite.maximum_nesting_depth + 2,
      "semantic shape traversal task-count frontier exceeds its depth-derived bound",
    );
  }
  while (pending.length) {
    const current = pending.pop();
    if (current.kind === "array-frame") {
      if (current.nextIndex < current.value.length) {
        const index = current.nextIndex;
        pushPending({ ...current, nextIndex: index + 1 });
        const pointer = `${current.pointer}/${index}`;
        pushPending(
          reserveNode(
            current.depth + 1,
            pointer,
            current.value[index],
          ),
        );
      }
      continue;
    }
    if (current.kind === "object-frame") {
      if (current.nextIndex < current.keys.length) {
        const key = current.keys[current.nextIndex];
        pushPending({ ...current, nextIndex: current.nextIndex + 1 });
        const pointer = `${current.pointer}/${pointerSegment(key)}`;
        const row = [
          pointer,
          semanticShapeType(current.value[key], pointer),
        ];
        pushPending({
          depth: current.depth + 1,
          kind: "node",
          pointer,
          row,
          value: current.value[key],
        });
      } else {
        retainedObjectKeySnapshots -= current.keys.length;
        requireCondition(
          retainedObjectKeySnapshots >= 0,
          "semantic shape retained object-key snapshot count underflowed",
        );
      }
      continue;
    }
    requireCondition(
      current.kind === "node",
      "semantic shape traversal has an unknown task",
    );
    rows.push(current.row);
    if (Array.isArray(current.value)) {
      if (current.value.length > 0) {
        pushPending({
          depth: current.depth,
          kind: "array-frame",
          nextIndex: 0,
          pointer: current.pointer,
          value: current.value,
        });
      }
    } else if (
      current.value !== null &&
      typeof current.value === "object"
    ) {
      const keys = Object.keys(current.value);
      requireCondition(
        keys.length <= suite.maximum_entries - discoveredEntries,
        "semantic shape exceeds its entry bound",
      );
      let minimumProjectionBytes = projectionBytes;
      let projectedEntryCount = discoveredEntries;
      for (const key of keys) {
        const pointer = `${current.pointer}/${pointerSegment(key)}`;
        requireCondition(
          current.depth + 1 <= suite.maximum_nesting_depth,
          "semantic shape exceeds its declared nesting bound",
        );
        requireCondition(
          pointer.length <= suite.maximum_pointer_characters,
          "semantic shape exceeds its pointer bound",
        );
        const minimumRowByteLength = canonicalBytes(
          [pointer, "null"],
          `semantic shape minimum row ${pointer}`,
        ).length;
        const minimumIncrement =
          minimumRowByteLength + (projectedEntryCount === 0 ? 0 : 1);
        requireCondition(
          minimumProjectionBytes <= MAX_SAFE_INTEGER - minimumIncrement,
          "semantic shape minimum projection accounting overflowed",
        );
        minimumProjectionBytes += minimumIncrement;
        projectedEntryCount += 1;
      }
      requireCondition(
        minimumProjectionBytes <= suite.maximum_projection_bytes,
        "semantic shape exceeds its projection byte bound before value "
          + "materialization or member sorting",
      );
      for (const key of keys) {
        const pointer = `${current.pointer}/${pointerSegment(key)}`;
        reserveNode(current.depth + 1, pointer, current.value[key]);
      }
      keys.sort((left, right) =>
        compareAscii(
          pointerSegment(left),
          pointerSegment(right),
        ),
      );
      if (keys.length > 0) {
        // Each open object owns one key snapshot. Every retained key already
        // reserves a distinct global entry and minimum projection row, so the
        // aggregate live key snapshots are entry/input-bounded, not only
        // depth-bounded.
        retainedObjectKeySnapshots += keys.length;
        requireCondition(
          retainedObjectKeySnapshots <= discoveredEntries
            && retainedObjectKeySnapshots <= suite.maximum_entries,
          "semantic shape retained object-key snapshots exceed the global "
            + "entry bound",
        );
        pushPending({
          depth: current.depth,
          keys,
          kind: "object-frame",
          nextIndex: 0,
          pointer: current.pointer,
          value: current.value,
        });
      }
    }
  }
  requireCondition(
    rows.length === discoveredEntries && retainedObjectKeySnapshots === 0,
    "semantic shape traversal did not materialize every reserved row",
  );
  rows.sort((left, right) => compareAscii(left[0], right[0]));
  for (let index = 1; index < rows.length; index += 1) {
    requireCondition(
      rows[index - 1][0] !== rows[index][0],
      "semantic shape has a duplicate pointer",
    );
  }
  requireCondition(
    canonicalBytes(rows, "semantic shape projection").length === projectionBytes,
    "semantic shape streaming projection byte accounting diverged",
  );
  return rows;
}

function verifySemanticShape(expanded, profile) {
  const suite = profile.semantic_shape_commitment_suite;
  requireExact(
    suite,
    EXPECTED_SEMANTIC_SHAPE_SUITE,
    "semantic shape exact v3 commitment suite",
  );
  requireFramedSuite(suite, "semantic shape commitment suite");
  requireCondition(
    expanded !== null &&
      typeof expanded === "object" &&
      !Array.isArray(expanded) &&
      Object.getPrototypeOf(expanded) === Object.prototype,
    "semantic shape source is not the declared JSON object",
  );
  const rows = semanticShapeRows(expanded, suite);
  const projection = canonicalBytes(rows, "semantic shape projection");
  requireCondition(
    projection.length <= suite.maximum_projection_bytes,
    "semantic shape exceeds its projection byte bound",
  );
  const digest = sha256(
    Buffer.concat([
      parseDomainHex(suite.domain_hex, "semantic shape domain"),
      uint64be(projection.length),
      projection,
    ]),
  );
  requireCondition(
    profile.semantic_shape_entry_count === rows.length,
    "review profile semantic shape count mismatch",
  );
  requireCondition(
    profile.semantic_shape_sha256 === digest,
    "review profile semantic shape digest mismatch",
  );
  return { entryCount: rows.length, sha256: digest };
}

function verifyDocumentCommitments(inventory) {
  const rowSuite = inventory.document_row_commitment;
  requireCondition(rowSuite.algorithm === "SHA256", "document row algorithm");
  requireCondition(
    rowSuite.canonicalization ===
      "UTF8_JSON_SORTED_KEYS_NO_INSIGNIFICANT_WHITESPACE",
    "document row canonicalization is unsupported",
  );
  requireCondition(
    rowSuite.framing ===
      "DOMAIN_BYTES_THEN_ASCII_ROW_KIND_THEN_NUL_THEN_CANONICAL_ROWS_BYTES",
    "document row framing is unsupported",
  );
  requireExact(
    rowSuite.row_kinds,
    ["allocations", "exclusions"],
    "document row kinds",
  );
  const rowDomain = parseDomainHex(rowSuite.domain_hex, "document row domain");
  let corpusBytes = 0;
  for (const [index, document] of inventory.documents.entries()) {
    const label = `allocation document ${index}`;
    const mainRaw = readBounded(
      document.path,
      MAX_ADR_SOURCE_BYTES,
      `${label} main source`,
    );
    requireCondition(
      mainRaw.length === document.byte_length &&
        sha256(mainRaw) === document.sha256,
      `${label}: main source identity mismatch`,
    );
    corpusBytes += mainRaw.length;
    const sourceRows = [
      {
        bytes: mainRaw.length,
        kind: "main",
        path: document.path,
        sha256: sha256(mainRaw),
      },
    ];
    for (const [moduleIndex, module] of document.modules.entries()) {
      const moduleRaw = readBounded(
        module.path,
        MAX_ADR_SOURCE_BYTES,
        `${label} module ${moduleIndex}`,
      );
      requireCondition(
        moduleRaw.length === module.byte_length &&
          sha256(moduleRaw) === module.sha256,
        `${label}: module source identity mismatch`,
      );
      corpusBytes += moduleRaw.length;
      sourceRows.push({
        bytes: moduleRaw.length,
        kind: "module",
        path: module.path,
        sha256: sha256(moduleRaw),
      });
    }
    const sourceSuite = document.source_set;
    requireCondition(
      sourceSuite.digest_algorithm === "SHA256",
      `${label}: source-set algorithm is unsupported`,
    );
    requireCondition(
      sourceSuite.canonicalization ===
        "UTF8_JSON_SORTED_KEYS_NO_INSIGNIFICANT_WHITESPACE",
      `${label}: source-set canonicalization is unsupported`,
    );
    requireCondition(
      sourceSuite.framing ===
        "DOMAIN_BYTES_THEN_UINT64_BE_CANONICAL_BYTE_LENGTH_THEN_CANONICAL_BYTES",
      `${label}: source-set framing is unsupported`,
    );
    const sourceProjection = {
      decision_id: document.adr_id,
      schema: sourceSuite.schema,
      sources: sourceRows,
    };
    requireCondition(
      sourceSuite.sha256 ===
        framedCanonicalSha256(
          sourceSuite.domain_hex,
          sourceProjection,
          `${label} source set`,
        ),
      `${label}: source-set digest mismatch`,
    );

    for (const rowKind of ["allocations", "exclusions"]) {
      const rows = inventory[rowKind].filter(
        (row) => row.adr_id === document.adr_id,
      );
      const digest = sha256(
        Buffer.concat([
          rowDomain,
          Buffer.from(rowKind, "ascii"),
          Buffer.from([0]),
          canonicalBytes(rows, `${label} ${rowKind}`),
        ]),
      );
      requireCondition(
        document[`${rowKind.slice(0, -1)}_row_count`] === rows.length,
        `${label}: ${rowKind} count mismatch`,
      );
      requireCondition(
        document[`${rowKind.slice(0, -1)}_rows_sha256`] === digest,
        `${label}: ${rowKind} digest mismatch`,
      );
    }
  }
  requireCondition(corpusBytes <= 2 * 1024 * 1024, "ADR corpus exceeds bound");
}

function verifyProvenanceReview(inventory) {
  const review = inventory.provenance_review;
  if (review.status === "NOT_REVIEWED") {
    requireCondition(
      review.reviewed_assignment_sha256 === "0".repeat(64),
      "NOT_REVIEWED provenance has a nonzero assignment digest",
    );
    return;
  }
  requireCondition(review.status === "REVIEWED", "unknown provenance review status");
  requireDirectSuite(review, "provenance review suite");
  const projection = {
    allocation_review_profile: inventory.allocation_review_profile,
    allocations: inventory.allocations,
    document_source_sets: inventory.documents.map((document) => ({
      adr_id: document.adr_id,
      allocation_anchor_id: document.allocation_anchor_id,
      source_set: document.source_set,
    })),
    exclusions: inventory.exclusions,
    semantic_review_subject: inventory.semantic_review_subject,
  };
  requireCondition(
    review.reviewed_assignment_sha256 ===
      directCanonicalSha256(
        review.domain_hex,
        projection,
        "provenance review projection",
      ),
    "reviewed provenance assignment digest mismatch",
  );
}

function verifyProposalSourceSet(proposal, proposalSchemaRaw, compactRaw) {
  requireClosedKeys(
    proposal.source,
    [
      "adr_corpus",
      "compact_source",
      "expanded_source",
      "model_projection",
      "proposal_compiler",
      "proposal_schema",
    ],
    "proposal source",
  );
  contentIdentity(
    compactRaw,
    proposal.source.compact_source,
    "proposal compact source",
  );
  requireCondition(
    proposal.source.compact_source.path === COMPACT_PATH,
    "proposal binds an unexpected compact source path",
  );
  requireClosedKeys(
    proposal.source.expanded_source,
    ["canonical_byte_length", "schema", "sha256"],
    "proposal expanded source identity",
  );
  requireCondition(
    proposal.source.expanded_source.schema ===
      "ncp.b01-selector-closure-source.v1",
    "proposal expanded source schema changed",
  );
  requireClosedKeys(
    proposal.source.model_projection,
    [
      "allocation_count",
      "allocation_sha256",
      "origin_signal_row_count",
      "origin_signal_sha256",
      "origin_signal_schema",
      "schema",
    ],
    "proposal model projection identity",
  );
  requireCondition(
    proposal.source.model_projection.schema ===
      "ncp.b01-selector-allocation-model-projection.v4" &&
      proposal.source.model_projection.origin_signal_schema ===
        "ncp.b01-selector-allocation-origin-signal-projection.v1",
    "proposal model or origin/signal projection schema changed",
  );
  const schemaIdentity = proposal.source.proposal_schema;
  requireClosedKeys(
    schemaIdentity,
    ["byte_length", "id", "path", "sha256"],
    "proposal schema identity",
  );
  requireCondition(
    schemaIdentity.id === PROPOSAL_SCHEMA_ID &&
      schemaIdentity.path === PROPOSAL_SCHEMA_PATH,
    "proposal binds an unexpected schema path",
  );
  requireCondition(
    schemaIdentity.byte_length === proposalSchemaRaw.length &&
      schemaIdentity.sha256 === sha256(proposalSchemaRaw),
    "proposal schema identity mismatch",
  );
  let proposalSchema;
  try {
    proposalSchema = parseJsonWithPreflight(
      proposalSchemaRaw,
      MAX_JSON_DEPTH,
      "proposal schema",
    );
  } catch (error) {
    fail(`proposal schema is not JSON: ${error.message}`);
  }
  requireCondition(
    proposalSchema.$schema ===
      "https://json-schema.org/draft/2020-12/schema" &&
      proposalSchema.$id ===
        "https://sepahead.github.io/ncp/schemas/b01-selector-allocation-proposal.v1.json" &&
      proposalSchema.type === "object" &&
      proposalSchema.additionalProperties === false,
    "proposal schema root is not the closed expected schema",
  );

  const compiler = proposal.source.proposal_compiler;
  requireClosedKeys(
    compiler,
    [
      "algorithm",
      "canonicalization",
      "domain_hex",
      "entrypoint",
      "projection_sha256",
      "source_count",
      "sources",
    ],
    "proposal compiler source set",
  );
  requireCommitment(
    {
      algorithm: compiler.algorithm,
      canonicalization: compiler.canonicalization,
      domain_hex: compiler.domain_hex,
      projection_sha256: compiler.projection_sha256,
    },
    PROPOSAL_DOMAINS.compilerSources,
    "proposal compiler source-set commitment",
  );
  requireCondition(
    compiler.entrypoint === "scripts/generate_selector_allocation_proposal.py",
    "proposal compiler entrypoint changed",
  );
  requireCondition(
    Array.isArray(compiler.sources) &&
      compiler.source_count === COMPILER_SOURCE_PATHS.length &&
      compiler.sources.length === COMPILER_SOURCE_PATHS.length,
    "proposal compiler source closure cardinality mismatch",
  );
  for (const [index, source] of compiler.sources.entries()) {
    requireCondition(
      source.path === COMPILER_SOURCE_PATHS[index],
      `proposal compiler source ${index}: source path or order changed`,
    );
    const raw = readBounded(
      source.path,
      MAX_COMPILER_SOURCE_BYTES,
      `proposal compiler source ${index}`,
    );
    contentIdentity(raw, source, `proposal compiler source ${index}`);
    if (source.path === "scripts/selector_closure_codec.py") {
      const sourceText = decodeUtf8(raw, "selector closure codec source");
      for (const declaration of PYTHON_CODEC_BOUND_DECLARATIONS) {
        const firstDeclaration = sourceText.indexOf(declaration);
        requireCondition(
          firstDeclaration >= 0 &&
            firstDeclaration === sourceText.lastIndexOf(declaration),
          `Python and Node selector codec bounds are not exactly aligned: ${declaration}`,
        );
      }
    }
  }
  requireCondition(
    compiler.projection_sha256 ===
      framedCanonicalSha256(
        compiler.domain_hex,
        compiler.sources,
        "proposal compiler source set",
      ),
    "proposal compiler source-set digest mismatch",
  );

  const corpus = proposal.source.adr_corpus;
  requireClosedKeys(
    corpus,
    [
      "adr_count",
      "adr_sources",
      "algorithm",
      "canonicalization",
      "domain_hex",
      "projection_sha256",
    ],
    "proposal ADR corpus",
  );
  requireCommitment(
    {
      algorithm: corpus.algorithm,
      canonicalization: corpus.canonicalization,
      domain_hex: corpus.domain_hex,
      projection_sha256: corpus.projection_sha256,
    },
    PROPOSAL_DOMAINS.adrCorpus,
    "proposal ADR corpus commitment",
  );
  requireCondition(
    Array.isArray(corpus.adr_sources),
    "proposal ADR sources must be an array",
  );
  const sourceRows = structuredClone(corpus.adr_sources);
  requireCondition(
    corpus.adr_count === ADR_IDS.length &&
      sourceRows.length === ADR_IDS.length,
    "proposal ADR corpus closure cardinality mismatch",
  );
  const acceptedByAdr = new Map();
  const allByAdr = new Map();
  let corpusBytes = 0;
  for (const [index, source] of sourceRows.entries()) {
    requireClosedKeys(
      source,
      ["adr_id", "allocation_anchor_id", "main", "modules"],
      `proposal ADR source ${index}`,
    );
    const adrId = ADR_IDS[index];
    const [mainPath, modulePaths] = ADR_SOURCES[index];
    requireCondition(
      source.adr_id === adrId &&
        source.allocation_anchor_id === sourceAnchor(adrId) &&
        source.main.path === mainPath,
      `proposal ADR source ${index}: identity, anchor, path, or order changed`,
    );
    requireCondition(
      Array.isArray(source.modules) &&
        source.modules.length === modulePaths.length,
      `proposal ADR source ${index}: module closure changed`,
    );
    const mainRaw = readBounded(
      source.main.path,
      MAX_ADR_SOURCE_BYTES,
      `proposal ADR source ${index}`,
    );
    contentIdentity(mainRaw, source.main, `proposal ADR source ${index}`);
    corpusBytes += mainRaw.length;
    const texts = [decodeUtf8(mainRaw, `proposal ADR source ${index}`)];
    for (const [moduleIndex, module] of source.modules.entries()) {
      requireCondition(
        module.path === modulePaths[moduleIndex],
        `proposal ADR source ${index} module ${moduleIndex}: path or order changed`,
      );
      const moduleRaw = readBounded(
        module.path,
        MAX_ADR_SOURCE_BYTES,
        `proposal ADR source ${index} module ${moduleIndex}`,
      );
      contentIdentity(
        moduleRaw,
        module,
        `proposal ADR source ${index} module ${moduleIndex}`,
      );
      corpusBytes += moduleRaw.length;
      texts.push(
        decodeUtf8(
          moduleRaw,
          `proposal ADR source ${index} module ${moduleIndex}`,
        ),
      );
    }
    const identifiers = proseIdentifiers(texts);
    acceptedByAdr.set(adrId, identifiers.accepted);
    allByAdr.set(adrId, identifiers.all);
  }
  requireCondition(
    corpusBytes <= 2 * 1024 * 1024,
    "proposal ADR corpus exceeds its aggregate byte bound",
  );
  requireCondition(
    corpus.projection_sha256 ===
      framedCanonicalSha256(
        corpus.domain_hex,
        sourceRows,
        "proposal ADR corpus",
    ),
    "proposal ADR corpus digest mismatch",
  );
  return { acceptedByAdr, allByAdr };
}

function countValues(values) {
  const counts = new Map();
  for (const value of values) counts.set(value, (counts.get(value) ?? 0) + 1);
  return counts;
}

function verifyClassSummary(
  summary,
  projection,
  observedValues,
  expectedDomain,
  expectedClasses,
  label,
) {
  requireClosedKeys(
    summary,
    ["algorithm", "canonicalization", "counts", "domain_hex", "projection_sha256"],
    label,
  );
  requireCommitment(
    {
      algorithm: summary.algorithm,
      canonicalization: summary.canonicalization,
      domain_hex: summary.domain_hex,
      projection_sha256: summary.projection_sha256,
    },
    expectedDomain,
    label,
  );
  requireCondition(
    summary.projection_sha256 ===
      framedCanonicalSha256(summary.domain_hex, projection, `${label} projection`),
    `${label}: projection digest mismatch`,
  );
  requireCondition(Array.isArray(summary.counts), `${label}: counts are not an array`);
  requireExact(
    summary.counts.map((row) => row.class),
    expectedClasses,
    `${label} taxonomy and order`,
  );
  const observed = countValues(observedValues);
  for (const [index, row] of summary.counts.entries()) {
    requireClosedKeys(row, ["class", "count"], `${label} count ${index}`);
    requireCondition(
      row.count === (observed.get(row.class) ?? 0),
      `${label}: count mismatch for ${row.class}`,
    );
    observed.delete(row.class);
  }
  requireCondition(observed.size === 0, `${label}: missing observed class`);
}

function verifyProposalSemantics(proposal, identitySuite, prose) {
  requireClosedKeys(
    proposal,
    [
      "$schema",
      "authority_boundary",
      "candidate",
      "claim_boundary",
      "normative",
      "rows",
      "schema",
      "source",
      "summary",
      "task",
    ],
    "proposal",
  );
  requireCondition(
    proposal.$schema === PROPOSAL_SCHEMA_FILE &&
      proposal.schema === PROPOSAL_SCHEMA_ID &&
      proposal.candidate === "1.0.0-rc.1" &&
      proposal.normative === false &&
      proposal.task === "B01",
    "proposal metadata or non-normative candidate boundary changed",
  );
  requireCondition(
    proposal.claim_boundary === PROPOSAL_CLAIM_BOUNDARY,
    "proposal claim boundary changed",
  );
  requireExact(
    proposal.authority_boundary,
    {
      allocation_effect: "NO_ASSIGNMENT_OR_ACCEPTANCE_AUTHORITY",
      evidence_effect: "MECHANICAL_ORIGIN_AND_SIGNAL_DISCLOSURE_ONLY",
      proposal_effect:
        "NO_RUNTIME_PROTOCOL_REVIEW_RELEASE_EXTERNAL_OR_INDEPENDENT_AUTHORITY",
      unmapped_effect: "FAIL_CLOSED_REQUIRES_EXPLICIT_REVIEW",
      usage_effect: "SIGNAL_ONLY_NEVER_OWNERSHIP_OR_ROUTE_AUTHORITY",
    },
    "proposal authority boundary",
  );
  requireCondition(
    Array.isArray(proposal.rows) &&
      proposal.rows.length > 0 &&
      proposal.rows.length <= 65_536,
    "proposal row collection is outside its closed bound",
  );
  requireClosedKeys(
    proposal.summary,
    [
      "ambiguity_flag_summary",
      "candidate_route_counts",
      "model_allocation_count",
      "model_allocation_sha256",
      "model_kind_counts",
      "model_origin_signal_row_count",
      "model_origin_signal_sha256",
      "origin_kind_summary",
      "proposal_row_count",
      "proposal_rows_commitment",
      "prose_signal_commitment",
      "route_rule_summary",
      "rows_with_ambiguity_count",
      "signal_kind_summary",
      "unmapped_shared_row_count",
    ],
    "proposal summary",
  );
  requireCondition(
    proposal.summary.proposal_row_count === proposal.rows.length,
    "proposal row count mismatch",
  );
  const rowsCommitment = proposal.summary.proposal_rows_commitment;
  requireCommitment(
    rowsCommitment,
    PROPOSAL_DOMAINS.rows,
    "proposal row commitment",
  );
  requireCondition(
    rowsCommitment.projection_sha256 ===
      framedCanonicalSha256(
        rowsCommitment.domain_hex,
        proposal.rows,
        "proposal rows",
      ),
    "proposal row commitment mismatch",
  );

  for (const [index, row] of proposal.rows.entries()) {
    requireClosedKeys(
      row,
      [
        "accepted_prose_adr_ids",
        "ambiguity_flags",
        "declaring_selector_ids",
        "exact_name",
        "kind",
        "origin_evidence",
        "prose_adr_ids",
        "route_basis_values",
        "route_rule_class",
        "semantic_ref",
        "signal_evidence",
        "suggested_adr_id",
        "suggested_source_anchor",
        "unit_id",
      ],
      `proposal row ${index}`,
    );
    requireCondition(
      MODEL_KINDS.includes(row.kind),
      `proposal row ${index}: unknown model kind`,
    );
    requireSortedUniqueStrings(
      row.declaring_selector_ids,
      undefined,
      `proposal row ${index} selectors`,
    );
    requireSortedUniqueStrings(
      row.prose_adr_ids,
      ADR_IDS,
      `proposal row ${index} prose ADRs`,
    );
    requireSortedUniqueStrings(
      row.accepted_prose_adr_ids,
      ADR_IDS,
      `proposal row ${index} accepted-prose ADRs`,
    );
    requireSortedUniqueStrings(
      row.ambiguity_flags,
      AMBIGUITY_FLAGS,
      `proposal row ${index} ambiguity flags`,
    );
    requireSortedUniqueStrings(
      row.route_basis_values,
      undefined,
      `proposal row ${index} route basis`,
    );
    requireCondition(
      ROUTE_RULE_CLASSES.includes(row.route_rule_class) &&
        SUGGESTED_DESTINATIONS.includes(row.suggested_adr_id),
      `proposal row ${index}: route taxonomy is open`,
    );
    const expectedSelectors = declaringSelectorIds(row);
    const expectedProseAdrIds = ADR_IDS.filter((adrId) =>
      prose.allByAdr.get(adrId).has(row.exact_name),
    );
    const expectedAcceptedProseAdrIds = ADR_IDS.filter((adrId) =>
      prose.acceptedByAdr.get(adrId).has(row.exact_name),
    );
    requireExact(
      row.declaring_selector_ids,
      expectedSelectors,
      `proposal row ${index} declaring selectors`,
    );
    requireExact(
      row.prose_adr_ids,
      expectedProseAdrIds,
      `proposal row ${index} prose evidence`,
    );
    requireExact(
      row.accepted_prose_adr_ids,
      expectedAcceptedProseAdrIds,
      `proposal row ${index} accepted prose evidence`,
    );
    const route = expectedRoute(row, prose.acceptedByAdr);
    requireExact(
      {
        basis: row.route_basis_values,
        classId: row.route_rule_class,
        suggestedAdrId: row.suggested_adr_id,
        suggestedSourceAnchor: row.suggested_source_anchor,
      },
      route,
      `proposal row ${index} deterministic nonauthoritative route`,
    );
    requireExact(
      row.ambiguity_flags,
      expectedAmbiguityFlags(
        row,
        route,
        expectedProseAdrIds,
        expectedAcceptedProseAdrIds,
      ),
      `proposal row ${index} ambiguity derivation`,
    );
  }

  const kindCounts = countValues(proposal.rows.map((row) => row.kind));
  requireClosedKeys(
    proposal.summary.model_kind_counts,
    MODEL_KINDS,
    "proposal model kind counts",
  );
  for (const kind of MODEL_KINDS) {
    requireCondition(
      proposal.summary.model_kind_counts[kind] === (kindCounts.get(kind) ?? 0),
      `proposal kind count mismatch for ${kind}`,
    );
  }

  const originProjection = proposal.rows.map((row) => [
    row.unit_id,
    row.origin_evidence,
  ]);
  verifyClassSummary(
    proposal.summary.origin_kind_summary,
    originProjection,
    proposal.rows.flatMap((row) =>
      row.origin_evidence.map((evidence) => evidence.evidence_kind),
    ),
    PROPOSAL_DOMAINS.originKinds,
    [...identitySuite.origin_kinds],
    "proposal origin kind summary",
  );

  const signalProjection = proposal.rows.map((row) => [
    row.unit_id,
    row.signal_evidence,
  ]);
  verifyClassSummary(
    proposal.summary.signal_kind_summary,
    signalProjection,
    proposal.rows.flatMap((row) =>
      row.signal_evidence.map((evidence) => evidence.evidence_kind),
    ),
    PROPOSAL_DOMAINS.signalKinds,
    [...identitySuite.signal_kinds],
    "proposal signal kind summary",
  );

  const routeProjection = proposal.rows.map((row) => [
    row.unit_id,
    row.route_rule_class,
    row.route_basis_values,
    row.suggested_adr_id,
    row.suggested_source_anchor,
  ]);
  verifyClassSummary(
    proposal.summary.route_rule_summary,
    routeProjection,
    proposal.rows.map((row) => row.route_rule_class),
    PROPOSAL_DOMAINS.routeClasses,
    ROUTE_RULE_CLASSES,
    "proposal route summary",
  );

  const ambiguityProjection = proposal.rows.map((row) => [
    row.unit_id,
    row.ambiguity_flags,
  ]);
  verifyClassSummary(
    proposal.summary.ambiguity_flag_summary,
    ambiguityProjection,
    proposal.rows.flatMap((row) => row.ambiguity_flags),
    PROPOSAL_DOMAINS.ambiguity,
    AMBIGUITY_FLAGS,
    "proposal ambiguity summary",
  );

  const proseProjection = proposal.rows.map((row) => [
    row.unit_id,
    row.prose_adr_ids,
    row.accepted_prose_adr_ids,
  ]);
  const proseCommitment = proposal.summary.prose_signal_commitment;
  requireCommitment(
    proseCommitment,
    PROPOSAL_DOMAINS.proseSignals,
    "proposal prose signal commitment",
  );
  requireCondition(
    proseCommitment.projection_sha256 ===
      framedCanonicalSha256(
        proseCommitment.domain_hex,
        proseProjection,
        "proposal prose signals",
      ),
    "proposal prose signal commitment mismatch",
  );

  requireCondition(
    Array.isArray(proposal.summary.candidate_route_counts),
    "proposal destination counts are not an array",
  );
  requireExact(
    proposal.summary.candidate_route_counts.map((row) => row.class),
    SUGGESTED_DESTINATIONS,
    "proposal destination taxonomy and order",
  );
  const destinationCounts = countValues(
    proposal.rows.map((row) => row.suggested_adr_id),
  );
  for (const [index, row] of proposal.summary.candidate_route_counts.entries()) {
    requireClosedKeys(row, ["class", "count"], `proposal destination ${index}`);
    requireCondition(
      row.count === (destinationCounts.get(row.class) ?? 0),
      `proposal destination count mismatch for ${row.class}`,
    );
  }
  requireCondition(
    proposal.summary.unmapped_shared_row_count ===
      proposal.rows.filter((row) => row.suggested_adr_id === "UNMAPPED_SHARED")
        .length,
    "proposal UNMAPPED_SHARED count mismatch",
  );
  requireCondition(
    proposal.summary.rows_with_ambiguity_count ===
      proposal.rows.filter((row) => row.ambiguity_flags.length > 0).length,
    "proposal ambiguity-row count mismatch",
  );
}

function verifySuiteFixedVectors(inventory) {
  const profile = inventory.allocation_review_profile;
  const identitySuite = profile.allocation_identity_commitment_suite;
  const identityVector = identitySuite.fixed_vectors.unit_model_origin;
  const unitId = framedCanonicalSha256(
    identitySuite.unit_id_domain_hex,
    identityVector.identity_input,
    "identity fixed vector",
  );
  requireCondition(unitId === identityVector.expected_unit_id, "unit ID fixed vector");
  requireExact(
    [...identityVector.identity_input, unitId],
    identityVector.expected_identity_projection,
    "identity projection fixed vector",
  );
  requireCondition(
    framedCanonicalSha256(
      identitySuite.model_projection_domain_hex,
      identityVector.model_projection_input,
      "model fixed vector",
    ) === identityVector.expected_model_projection_sha256,
    "model projection fixed vector",
  );
  requireCondition(
    framedCanonicalSha256(
      identitySuite.origin_signal_projection_domain_hex,
      identityVector.origin_signal_projection_input,
      "origin/signal fixed vector",
    ) === identityVector.expected_origin_signal_sha256,
    "origin/signal projection fixed vector",
  );
  requireCondition(
    identityVector.origin_signal_projection_input.length ===
      identityVector.expected_origin_signal_row_count,
    "origin/signal count fixed vector",
  );

  const shapeSuite = profile.semantic_shape_commitment_suite;
  requireExact(
    shapeSuite,
    EXPECTED_SEMANTIC_SHAPE_SUITE,
    "semantic shape exact v3 commitment suite",
  );
  const shapeVector =
    shapeSuite.fixed_vectors.representative_types_and_escaping;
  const shapeSourceRaw = Buffer.from(
    shapeVector.source_canonical_utf8_hex,
    "hex",
  );
  const shapeSource = parseJsonWithPreflight(
    shapeSourceRaw,
    shapeSuite.maximum_nesting_depth,
    "semantic shape fixed-vector source",
  );
  requireCondition(
    shapeSourceRaw.length === shapeVector.source_canonical_utf8_byte_length,
    "semantic shape fixed-vector source byte length",
  );
  const shapeRows = semanticShapeRows(shapeSource, shapeSuite);
  requireExact(
    shapeRows,
    shapeVector.expected_projection_rows,
    "semantic shape fixed-vector rows",
  );
  const shapeRaw = canonicalBytes(shapeRows, "semantic shape fixed vector");
  requireCondition(
    shapeRaw.length === shapeVector.expected_projection_byte_length,
    "semantic shape fixed-vector byte length",
  );
  requireCondition(
    shapeRows.length === shapeVector.expected_entry_count,
    "semantic shape fixed-vector entry count",
  );
  requireCondition(
    sha256(
      Buffer.concat([
        parseDomainHex(shapeSuite.domain_hex, "semantic shape fixed domain"),
        uint64be(shapeRaw.length),
        shapeRaw,
      ]),
    ) === shapeVector.expected_sha256,
    "semantic shape fixed-vector digest",
  );
  const shapeDepthVector = shapeSuite.fixed_vectors.nesting_depth_boundary;
  function depthProjection(arrayWrapperCount) {
    let nested = null;
    for (let index = 0; index < arrayWrapperCount; index += 1) {
      nested = [nested];
    }
    return { x: nested };
  }
  const maximumShapeDepthSource = depthProjection(
    shapeDepthVector.maximum_accepted_array_wrapper_count,
  );
  const maximumShapeDepthSourceRaw = canonicalBytes(
    maximumShapeDepthSource,
    "semantic shape maximum-depth source",
  );
  requireRawJsonDepth(
    maximumShapeDepthSourceRaw,
    shapeSuite.maximum_nesting_depth,
    "semantic shape maximum-depth source",
  );
  requireJsonDepth(
    maximumShapeDepthSource,
    shapeSuite.maximum_nesting_depth,
    "semantic shape maximum-depth source",
  );
  const maximumShapeDepthRows = semanticShapeRows(
    maximumShapeDepthSource,
    shapeSuite,
  );
  const maximumShapeDepthProjection = canonicalBytes(
    maximumShapeDepthRows,
    "semantic shape maximum-depth projection",
  );
  requireCondition(
    maximumShapeDepthRows.length ===
      shapeDepthVector.expected_accepted_entry_count &&
      maximumShapeDepthProjection.length ===
        shapeDepthVector.expected_accepted_projection_byte_length &&
      sha256(
        Buffer.concat([
          parseDomainHex(
            shapeSuite.domain_hex,
            "semantic shape maximum-depth domain",
          ),
          uint64be(maximumShapeDepthProjection.length),
          maximumShapeDepthProjection,
        ]),
      ) === shapeDepthVector.expected_accepted_sha256,
    "semantic shape maximum-depth fixed vector",
  );
  const rejectedShapeDepthSource = depthProjection(
    shapeDepthVector.first_rejected_array_wrapper_count,
  );
  let rejectedRawShapeDepth = false;
  try {
    requireRawJsonDepth(
      canonicalBytes(
        rejectedShapeDepthSource,
        "semantic shape first-rejected-depth source",
      ),
      shapeSuite.maximum_nesting_depth,
      "semantic shape first-rejected-depth source",
    );
  } catch (error) {
    requireCondition(
      error instanceof PortabilityError,
      "semantic shape raw depth vector raised an unexpected error",
    );
    rejectedRawShapeDepth = true;
  }
  let rejectedSemanticShapeDepth = false;
  try {
    semanticShapeRows(rejectedShapeDepthSource, shapeSuite);
  } catch (error) {
    requireCondition(
      error instanceof PortabilityError,
      "semantic shape depth vector raised an unexpected error",
    );
    rejectedSemanticShapeDepth = true;
  }
  requireCondition(
    rejectedRawShapeDepth && rejectedSemanticShapeDepth,
    "semantic shape first-over-depth fixed vector was accepted",
  );

  const subjectSuite = inventory.semantic_review_subject;
  requireCondition(
    subjectSuite.nesting_depth_counting ===
      "DOCUMENT_ROOT_IS_DEPTH_0_EACH_ARRAY_OR_OBJECT_CHILD_INCREMENTS_BY_1",
    "semantic subject nesting-depth counting changed",
  );
  const subjectDepthVector = subjectSuite.fixed_vectors.nesting_depth_boundary;
  const expectedSubjectDepthRaw = Buffer.concat([
    Buffer.from('{"x":', "ascii"),
    Buffer.alloc(63, 0x5b),
    Buffer.from("null", "ascii"),
    Buffer.alloc(63, 0x5d),
    Buffer.from("}", "ascii"),
  ]);
  requireCondition(
    expectedSubjectDepthRaw.length === 136,
    "semantic subject nesting-depth KAT builder changed",
  );
  requireExact(
    subjectDepthVector,
    {
      construction:
        "ROOT_OBJECT_MEMBER_X_WITH_NULL_WRAPPED_IN_N_SINGLETON_ARRAYS",
      expected_accepted_canonical_utf8_byte_length: 136,
      expected_accepted_canonical_utf8_hex:
        expectedSubjectDepthRaw.toString("hex"),
      expected_accepted_sha256:
        "27007f10558810346f9ca729d79e19a327d6d5174991f8a5944d2babb870bf7f",
      first_rejected_array_wrapper_count: 64,
      maximum_accepted_array_wrapper_count: 63,
      root_depth: 0,
    },
    "semantic subject nesting-depth fixed vector",
  );
  const maximumSubjectDepthProjection = depthProjection(
    subjectDepthVector.maximum_accepted_array_wrapper_count,
  );
  const maximumSubjectDepthRaw = canonicalBytes(
    maximumSubjectDepthProjection,
    "semantic subject maximum-depth projection",
  );
  requireRawJsonDepth(
    maximumSubjectDepthRaw,
    subjectSuite.maximum_nesting_depth,
    "semantic subject maximum-depth projection",
  );
  requireJsonDepth(
    maximumSubjectDepthProjection,
    subjectSuite.maximum_nesting_depth,
    "semantic subject maximum-depth projection",
  );
  requireCondition(
    maximumSubjectDepthRaw.length ===
      subjectDepthVector.expected_accepted_canonical_utf8_byte_length &&
      maximumSubjectDepthRaw.toString("hex") ===
        subjectDepthVector.expected_accepted_canonical_utf8_hex &&
      sha256(
        Buffer.concat([
          parseDomainHex(
            subjectSuite.domain_hex,
            "semantic subject maximum-depth domain",
          ),
          uint64be(maximumSubjectDepthRaw.length),
          maximumSubjectDepthRaw,
        ]),
      ) === subjectDepthVector.expected_accepted_sha256,
    "semantic subject maximum-depth fixed vector",
  );
  const rejectedSubjectDepthProjection = depthProjection(
    subjectDepthVector.first_rejected_array_wrapper_count,
  );
  let rejectedSubjectDepth = false;
  try {
    requireRawJsonDepth(
      canonicalBytes(
        rejectedSubjectDepthProjection,
        "semantic subject first-rejected-depth projection",
      ),
      subjectSuite.maximum_nesting_depth,
      "semantic subject first-rejected-depth projection",
    );
  } catch (error) {
    requireCondition(
      error instanceof PortabilityError,
      "semantic subject depth vector raised an unexpected error",
    );
    rejectedSubjectDepth = true;
  }
  requireCondition(
    rejectedSubjectDepth,
    "semantic subject first-over-depth fixed vector was accepted",
  );
  const subjectVector = subjectSuite.fixed_vectors.semantic_model;
  const subjectProjection = structuredClone(subjectVector.input);
  for (const key of subjectSuite.excluded_top_level_keys) {
    delete subjectProjection[key];
  }
  requireExact(
    subjectProjection,
    subjectVector.expected_projection,
    "semantic subject fixed-vector projection",
  );
  const subjectRaw = canonicalBytes(
    subjectProjection,
    "semantic subject fixed vector",
  );
  requireCondition(
    subjectRaw.length === subjectVector.expected_byte_length &&
      subjectRaw.toString("hex") === subjectVector.expected_canonical_utf8_hex,
    "semantic subject fixed-vector canonical bytes",
  );
  requireCondition(
    sha256(
      Buffer.concat([
        parseDomainHex(subjectSuite.domain_hex, "semantic subject fixed domain"),
        uint64be(subjectRaw.length),
        subjectRaw,
      ]),
    ) === subjectVector.expected_sha256,
    "semantic subject fixed-vector digest",
  );

  const documentSuite = inventory.document_row_commitment;
  for (const [name, vector] of Object.entries(documentSuite.fixed_vectors)) {
    if (name === "schema") continue;
    const rowsRaw = canonicalBytes(vector.rows, `document fixed vector ${name}`);
    if (Object.hasOwn(vector, "expected_canonical_rows_byte_length")) {
      requireCondition(
        rowsRaw.length === vector.expected_canonical_rows_byte_length &&
          rowsRaw.toString("hex") === vector.expected_canonical_rows_utf8_hex,
        `document fixed vector ${name}: canonical bytes`,
      );
    }
    requireCondition(
      sha256(
        Buffer.concat([
          parseDomainHex(documentSuite.domain_hex, "document fixed domain"),
          Buffer.from(vector.row_kind, "ascii"),
          Buffer.from([0]),
          rowsRaw,
        ]),
      ) === vector.expected_sha256,
      `document fixed vector ${name}: digest`,
    );
  }

  const sourceSuite = inventory.documents[0].source_set;
  const sourceVector = sourceSuite.fixed_vectors.main_with_two_modules;
  requireCondition(
    framedCanonicalSha256(
      sourceSuite.domain_hex,
      sourceVector.expected_projection,
      "ADR source-set fixed vector",
    ) === sourceVector.expected_sha256,
    "ADR source-set fixed vector",
  );

  const provenanceSuite = inventory.provenance_review;
  const provenanceVector = provenanceSuite.fixed_vectors.minimal_assignment;
  requireCondition(
    directCanonicalSha256(
      provenanceSuite.domain_hex,
      provenanceVector.expected_projection,
      "provenance fixed vector",
    ) === provenanceVector.expected_sha256,
    "provenance review fixed vector",
  );
}

function runAlgorithmSelfTest() {
  let cases = 0;
  function expectFailure(action, label) {
    try {
      action();
    } catch (error) {
      requireCondition(
        error instanceof PortabilityError,
        `${label}: unexpected exception type`,
      );
      cases += 1;
      return;
    }
    fail(`${label}: hostile vector was accepted`);
  }
  requireCondition(
    canonicalText({ z: [null, false, true, -1, 0, 1, 'a"b\\c'], a: {} }) ===
      '{"a":{},"z":[null,false,true,-1,0,1,"a\\"b\\\\c"]}',
    "canonical JSON fixed vector changed",
  );
  function bufferedReader(source, maximumChunk = source.length || 1) {
    let sourceOffset = 0;
    return (_descriptor, target, targetOffset, requested) => {
      const count = Math.min(
        requested,
        maximumChunk,
        source.length - sourceOffset,
      );
      if (count <= 0) return 0;
      source.copy(
        target,
        targetOffset,
        sourceOffset,
        sourceOffset + count,
      );
      sourceOffset += count;
      return count;
    };
  }
  requireCondition(
    readExactBoundedDescriptor(
      -1,
      3,
      3,
      "exact descriptor fixed vector",
      bufferedReader(Buffer.from("abc", "ascii"), 1),
    ).equals(Buffer.from("abc", "ascii")),
    "partial exact descriptor read changed",
  );
  cases += 1;
  expectFailure(
    () =>
      readExactBoundedDescriptor(
        -1,
        3,
        3,
        "short descriptor fixed vector",
        bufferedReader(Buffer.from("ab", "ascii")),
      ),
    "premature descriptor EOF",
  );
  expectFailure(
    () =>
      readExactBoundedDescriptor(
        -1,
        3,
        3,
        "growing descriptor fixed vector",
        bufferedReader(Buffer.from("abcd", "ascii")),
      ),
    "descriptor growth sentinel",
  );
  expectFailure(
    () =>
      readExactBoundedDescriptor(
        -1,
        1,
        0,
        "invalid descriptor bound",
        bufferedReader(Buffer.from("a", "ascii")),
    ),
    "invalid descriptor maximum",
  );
  const boundedPartLeft = { a: "xx" };
  const boundedPartRight = { b: "yy" };
  requireCondition(
    boundedCanonicalBytes(
      boundedPartLeft,
      10,
      "left bounded canonical part",
    ).length === 10 &&
      boundedCanonicalBytes(
        boundedPartRight,
        10,
        "right bounded canonical part",
      ).length === 10,
    "individually bounded canonical parts changed",
  );
  cases += 1;
  expectFailure(
    () =>
      boundedCanonicalBytes(
        { left: boundedPartLeft, right: boundedPartRight },
        20,
        "combined canonical document",
      ),
    "combined canonical document over bound",
  );
  const tinyItemLimits = {
    maximumItems: 5,
    maximumStringCharacters: 8,
    maximumTotalStringCharacters: 8,
  };
  const exactItemText = '{"a":[1,true]}';
  const exactItemPreflight = requireJsonTextBounds(
    exactItemText,
    64,
    "exact JSON item vector",
    tinyItemLimits,
  );
  const exactItemNative = requireJsonDepth(
    JSON.parse(exactItemText),
    64,
    "exact JSON item vector",
    tinyItemLimits,
  );
  requireExact(
    exactItemNative,
    exactItemPreflight,
    "exact JSON item preflight/native metrics",
  );
  cases += 1;
  expectFailure(
    () =>
      requireJsonTextBounds(exactItemText, 64, "JSON item plus one", {
        ...tinyItemLimits,
        maximumItems: 4,
      }),
    "JSON item plus one",
  );
  for (const [vectorLabel, exactValue, plusOneValue, maximumCharacters] of [
    ["literal ASCII", "abc", "abcd", 3],
    ["escaped quote and backslash", '\"\\', '\"\\x', 2],
    ["escaped control", "\u0001", "\u0001x", 1],
    ["literal astral", "\ud83d\ude00", "\ud83d\ude00x", 1],
  ]) {
    const exactRaw = JSON.stringify(exactValue);
    const plusOneRaw = JSON.stringify(plusOneValue);
    requireJsonTextBounds(exactRaw, 64, `${vectorLabel} exact`, {
      maximumItems: 2,
      maximumStringCharacters: maximumCharacters,
      maximumTotalStringCharacters: maximumCharacters,
    });
    cases += 1;
    expectFailure(
      () =>
        requireJsonTextBounds(plusOneRaw, 64, `${vectorLabel} plus one`, {
          maximumItems: 2,
          maximumStringCharacters: maximumCharacters,
          maximumTotalStringCharacters: maximumCharacters + 1,
        }),
      `${vectorLabel} string plus one`,
    );
  }
  requireJsonTextBounds('"\\ud83d\\ude00"', 64, "escaped surrogate pair exact", {
    maximumItems: 1,
    maximumStringCharacters: 1,
    maximumTotalStringCharacters: 1,
  });
  cases += 1;
  expectFailure(
    () =>
      requireJsonTextBounds(
        '"\\ud83d\\ude00x"',
        64,
        "escaped surrogate pair plus one",
        {
          maximumItems: 1,
          maximumStringCharacters: 1,
          maximumTotalStringCharacters: 2,
        },
      ),
    "escaped surrogate pair plus one",
  );
  requireJsonTextBounds('["ab","c"]', 64, "aggregate strings exact", {
    maximumItems: 3,
    maximumStringCharacters: 2,
    maximumTotalStringCharacters: 3,
  });
  cases += 1;
  expectFailure(
    () =>
      requireJsonTextBounds('["ab","c"]', 64, "aggregate strings plus one", {
        maximumItems: 3,
        maximumStringCharacters: 2,
        maximumTotalStringCharacters: 2,
      }),
    "aggregate string plus one",
  );
  expectFailure(
    () =>
      parseJsonWithPreflight(
        Buffer.from('{"a":1,"a":2}', "ascii"),
        MAX_JSON_DEPTH,
        "duplicate literal key",
      ),
    "duplicate literal JSON key",
  );
  expectFailure(
    () =>
      parseJsonWithPreflight(
        Buffer.from('{"a":1,"\\u0061":2}', "ascii"),
        MAX_JSON_DEPTH,
        "duplicate escaped-equivalent key",
      ),
    "duplicate escaped-equivalent JSON key",
  );
  expectFailure(
    () =>
      parseJsonWithPreflight(
        Buffer.from('"\\ud800"', "ascii"),
        MAX_JSON_DEPTH,
        "lone surrogate",
      ),
    "lone JSON surrogate",
  );
  let numberLimitMessage = "";
  try {
    requireCanonicalIntegerTokens(
      Buffer.from(`{"x":${"1".repeat(MAX_JSON_NUMBER_CHARS + 1)}}`, "ascii"),
      "number token plus one",
    );
  } catch (error) {
    requireCondition(
      error instanceof PortabilityError,
      "number token plus one: unexpected exception type",
    );
    numberLimitMessage = error.message;
  }
  requireCondition(
    numberLimitMessage.includes(`exceeds ${MAX_JSON_NUMBER_CHARS} characters`),
    "number token length was not rejected before numeric conversion",
  );
  cases += 1;
  const originalJsonParse = JSON.parse;
  let doomedJsonReachedParser = false;
  JSON.parse = (...parseArguments) => {
    doomedJsonReachedParser = true;
    return originalJsonParse(...parseArguments);
  };
  try {
    expectFailure(
      () =>
        parseJsonWithPreflight(
          Buffer.from(`"${"x".repeat(MAX_JSON_STRING_CHARS + 1)}"`, "ascii"),
          MAX_JSON_DEPTH,
          "doomed JSON preflight",
        ),
      "doomed JSON before parser",
    );
  } finally {
    JSON.parse = originalJsonParse;
  }
  requireCondition(
    !doomedJsonReachedParser,
    "JSON.parse ran before a hostile string quota rejection",
  );
  cases += 1;
  expectFailure(
    () => canonicalText({ value: -0 }, "negative-zero derived value"),
    "native negative-zero canonicalization",
  );
  cases += 1;
  let maximumDepthVector = null;
  for (let depth = 0; depth < 64; depth += 1) {
    maximumDepthVector = [maximumDepthVector];
  }
  requireJsonDepth(maximumDepthVector, 64, "maximum-depth fixed vector");
  cases += 1;
  expectFailure(
    () => requireJsonDepth([maximumDepthVector], 64, "over-depth fixed vector"),
    "semantic subject one-level-over depth",
  );
  function exactDepthProjection(arrayWrapperCount) {
    let nested = null;
    for (let index = 0; index < arrayWrapperCount; index += 1) {
      nested = [nested];
    }
    return { x: nested };
  }
  const exactMaximumDepthSource = exactDepthProjection(
    EXPECTED_SEMANTIC_SHAPE_SUITE.fixed_vectors.nesting_depth_boundary
      .maximum_accepted_array_wrapper_count,
  );
  const exactMaximumDepthRaw = canonicalBytes(
    exactMaximumDepthSource,
    "exact semantic shape maximum-depth source",
  );
  requireRawJsonDepth(
    exactMaximumDepthRaw,
    MAX_JSON_DEPTH,
    "exact semantic shape maximum-depth source",
  );
  const exactMaximumDepthRows = semanticShapeRows(
    exactMaximumDepthSource,
    EXPECTED_SEMANTIC_SHAPE_SUITE,
  );
  const exactMaximumDepthProjection = canonicalBytes(
    exactMaximumDepthRows,
    "exact semantic shape maximum-depth projection",
  );
  requireCondition(
    exactMaximumDepthRows.length === 65 &&
      exactMaximumDepthProjection.length === 5006 &&
      framedCanonicalSha256(
        EXPECTED_SEMANTIC_SHAPE_SUITE.domain_hex,
        exactMaximumDepthRows,
        "exact semantic shape maximum-depth projection",
      ) ===
        "ffdf1822c36f52e46e9ede5e4880b02a47fdeb5936540a8fdb23f447afc6c325",
    "exact semantic shape maximum-depth vector changed",
  );
  cases += 1;
  const exactRejectedDepthSource = exactDepthProjection(
    EXPECTED_SEMANTIC_SHAPE_SUITE.fixed_vectors.nesting_depth_boundary
      .first_rejected_array_wrapper_count,
  );
  expectFailure(
    () =>
      requireRawJsonDepth(
        canonicalBytes(
          exactRejectedDepthSource,
          "exact semantic shape first-rejected-depth source",
        ),
        MAX_JSON_DEPTH,
        "exact semantic shape first-rejected-depth source",
      ),
    "raw semantic shape first-over-depth vector",
  );
  expectFailure(
    () =>
      semanticShapeRows(
        exactRejectedDepthSource,
        EXPECTED_SEMANTIC_SHAPE_SUITE,
      ),
    "semantic shape first-over-depth vector",
  );
  expectFailure(
    () => semanticShapeType(-0, "/hostile"),
    "native negative-zero semantic shape scalar",
  );
  expectFailure(
    () => semanticShapeType("\u03b2", "/hostile"),
    "Unicode semantic shape scalar",
  );
  expectFailure(
    () =>
      semanticShapeRows(
        { x: null },
        {
          ...EXPECTED_SEMANTIC_SHAPE_SUITE,
          maximum_entries: 1,
        },
      ),
    "semantic shape entry preallocation bound",
  );
  expectFailure(
    () =>
      semanticShapeRows(
        { xx: null },
        {
          ...EXPECTED_SEMANTIC_SHAPE_SUITE,
          maximum_pointer_characters: 2,
        },
      ),
    "semantic shape pointer preallocation bound",
  );
  expectFailure(
    () =>
      semanticShapeRows(
        {},
        {
          ...EXPECTED_SEMANTIC_SHAPE_SUITE,
          maximum_projection_bytes: 2,
        },
      ),
    "semantic shape projection preallocation bound",
  );
  const wideSemanticShapeObject = {};
  for (let index = 0; index < 50_000; index += 1) {
    wideSemanticShapeObject[`member-${String(index).padStart(5, "0")}`] = null;
  }
  expectFailure(
    () =>
      semanticShapeRows(
        wideSemanticShapeObject,
        {
          ...EXPECTED_SEMANTIC_SHAPE_SUITE,
          maximum_entries: 32,
        },
      ),
    "wide semantic shape object entry preflight",
  );
  expectFailure(
    () =>
      semanticShapeRows(
        wideSemanticShapeObject,
        {
          ...EXPECTED_SEMANTIC_SHAPE_SUITE,
          maximum_projection_bytes: 128,
        },
      ),
    "wide semantic shape object projection preflight",
  );
  let deepWideValueReads = 0;
  const guardedWideObject = {};
  for (let index = 0; index < 128; index += 1) {
    Object.defineProperty(
      guardedWideObject,
      `guarded-member-${String(index).padStart(3, "0")}`,
      {
        enumerable: true,
        get() {
          deepWideValueReads += 1;
          throw new Error("deep-wide value was materialized before preflight");
        },
      },
    );
  }
  let deepWideSemanticShapeObject = guardedWideObject;
  for (let depth = 0; depth < 8; depth += 1) {
    deepWideSemanticShapeObject = { branch: deepWideSemanticShapeObject };
  }
  expectFailure(
    () =>
      semanticShapeRows(
        deepWideSemanticShapeObject,
        {
          ...EXPECTED_SEMANTIC_SHAPE_SUITE,
          maximum_entries: 16,
        },
      ),
    "deep-wide semantic shape combined entry preflight",
  );
  expectFailure(
    () =>
      semanticShapeRows(
        deepWideSemanticShapeObject,
        {
          ...EXPECTED_SEMANTIC_SHAPE_SUITE,
          maximum_projection_bytes: 4_096,
        },
      ),
    "deep-wide semantic shape combined projection preflight",
  );
  requireCondition(
    deepWideValueReads === 0,
    "deep-wide semantic shape preflight materialized a doomed child row",
  );
  cases += 1;
  let longParentWideValueReads = 0;
  const longParentWideChildren = {};
  for (let index = 0; index < 5_000; index += 1) {
    Object.defineProperty(
      longParentWideChildren,
      `member-${String(index).padStart(5, "0")}`,
      {
        enumerable: true,
        get() {
          longParentWideValueReads += 1;
          throw new Error("long-parent wide child was materialized");
        },
      },
    );
  }
  const longParentWideObject = {
    ["p".repeat(8_000)]: longParentWideChildren,
  };
  expectFailure(
    () =>
      semanticShapeRows(
        longParentWideObject,
        EXPECTED_SEMANTIC_SHAPE_SUITE,
      ),
    "long-parent wide semantic shape projection preflight",
  );
  requireCondition(
    longParentWideValueReads === 0,
    "long-parent wide projection materialized a doomed child value",
  );
  cases += 1;
  expectFailure(
    () =>
      semanticShapeRows(
        { valid: null, "\u03b2": null },
        EXPECTED_SEMANTIC_SHAPE_SUITE,
      ),
    "semantic shape object Unicode member before sort",
  );
  for (const hostileNumber of [
    "1.0",
    "1e0",
    "-0",
    "9007199254740992",
    "-9007199254740992",
  ]) {
    expectFailure(
      () =>
        requireCanonicalIntegerTokens(
          Buffer.from(`{"value":${hostileNumber}}`, "ascii"),
          `hostile number ${hostileNumber}`,
        ),
      `noncanonical or unsafe number ${hostileNumber}`,
    );
  }
  requireCanonicalIntegerTokens(
    Buffer.from(
      '{"maximum":9007199254740991,"minimum":-9007199254740991,"zero":0}',
      "ascii",
    ),
    "safe integer boundary vector",
  );
  cases += 1;
  const unitDomain = Buffer.from(
    "ncp.b01.selector-allocation.unit-id.v1\0",
    "ascii",
  ).toString("hex");
  const modelDomain = Buffer.from(
    "ncp.b01.selector-allocation.model-projection.v4\0",
    "ascii",
  ).toString("hex");
  const identity = ["TYPE", "SampleType", "sample-type::SampleType"];
  const unitId = framedCanonicalSha256(
    unitDomain,
    identity,
    "algorithm self-test unit",
  );
  requireCondition(
    unitId ===
      "de6ce89031c1d04d4776289af582d86237298ae40a76183cb29ffd0e53de8cbf",
    "unit ID algorithm fixed vector changed",
  );
  cases += 1;
  requireCondition(
    framedCanonicalSha256(
      modelDomain,
      [[...identity, unitId]],
      "algorithm self-test model",
    ) === "045fe6a71fdc4f995b9af1d68cc42aadadbd19ffb9920892929e7fb27af7635f",
    "model algorithm fixed vector changed",
  );
  cases += 1;
  requireCondition(
    framedCanonicalSha256(unitDomain, [...identity, "extra"], "hostile vector") !==
      unitId,
    "algorithm self-test did not detect an identity mutation",
  );
  cases += 1;
  requireCondition(
    framedCanonicalSha256(PROPOSAL_DOMAINS.rows, [], "empty proposal rows") ===
      "87acf1fd60f576da617e666938422d1759455488c3e73eaa94db0e5511b34107",
    "proposal row commitment fixed vector changed",
  );
  cases += 1;
  requireCondition(
    framedCanonicalSha256(
      PROPOSAL_DOMAINS.compilerSources,
      [],
      "empty compiler source set",
    ) === "aeb69522973710e8cd2a1a991b90d02355e455d93b07993706e780a4684e582e",
    "compiler source-set commitment fixed vector changed",
  );
  cases += 1;
  expectFailure(
    () =>
      parseDomainHex(
        `${Buffer.concat([
          Buffer.from("bad", "ascii"),
          Buffer.from([0]),
          Buffer.from("domain", "ascii"),
        ]).toString("hex")}00`,
        "embedded-NUL domain",
      ),
    "embedded-NUL domain",
  );
  const extracted = proseIdentifiers([
    "# ADR\n\nBEFORE\n\n## Proposed decision\n\n`AcceptedType`\n\n## Context\n\n`ContextType`\n",
  ]);
  requireCondition(
    extracted.accepted.has("AcceptedType") &&
      !extracted.accepted.has("ContextType") &&
      extracted.all.has("ContextType"),
    "accepted prose section extraction changed",
  );
  cases += 1;
  const acceptedByAdr = new Map(
    ADR_IDS.map((adrId) => [adrId, new Set()]),
  );
  const signalOnlyRow = {
    exact_name: "NovelType",
    kind: "TYPE",
    origin_evidence: [
      {
        evidence_kind: "ARTIFACT_REGISTRY_ENTRY",
        semantic_location: "artifact-ref::novel-type::NovelType",
      },
    ],
    semantic_ref: "novel-type::NovelType",
    signal_evidence: [
      {
        evidence_kind: "SELECTOR_USAGE",
        semantic_location: "selector-id::CONSUMER_SEMANTIC_CAPTURE",
      },
    ],
  };
  const signalOnlyRoute = expectedRoute(signalOnlyRow, acceptedByAdr);
  requireExact(
    signalOnlyRoute,
    {
      basis: [],
      classId: "NO_TOTAL_RULE",
      suggestedAdrId: "UNMAPPED_SHARED",
      suggestedSourceAnchor: null,
    },
    "usage-signal-independent route fixed vector",
  );
  cases += 1;
  const selectorRoute = expectedRoute(
    {
      exact_name: "OBSERVER_AUTHORIZATION",
      kind: "SELECTOR",
      origin_evidence: [
        {
          evidence_kind: "SELECTOR_DECLARATION",
          semantic_location: "selector-id::OBSERVER_AUTHORIZATION",
        },
      ],
      semantic_ref: "selector-id::OBSERVER_AUTHORIZATION",
      signal_evidence: [],
    },
    acceptedByAdr,
  );
  requireCondition(
    selectorRoute.suggestedAdrId === "ADR-004" &&
      selectorRoute.classId === "DECLARING_SELECTOR_REGISTRY_RULE",
    "selector route fixed vector changed",
  );
  cases += 1;
  const profileRoute = expectedRoute(
    {
      exact_name: "SYNTHETIC_ACTOR_PROFILE",
      kind: "PROFILE",
      origin_evidence: [
        {
          evidence_kind: "STRUCTURAL_PROFILE_DEFINITION",
          semantic_location: "profile-path::/actor_profiles/example",
        },
      ],
      semantic_ref: "/actor_profiles/example",
      signal_evidence: [],
    },
    acceptedByAdr,
  );
  requireCondition(
    profileRoute.suggestedAdrId === "ADR-011" &&
      profileRoute.classId === "STRUCTURAL_PROFILE_RULE",
    "profile route fixed vector changed",
  );
  cases += 1;
  const bodyStateRoute = expectedRoute(
    {
      exact_name: "BODY_SESSION_CONTROL.LEASE_CURRENTNESS.ACTIVE",
      kind: "STATE",
      origin_evidence: [
        {
          evidence_kind: "STATE_DECLARATION",
          semantic_location:
            "selector-id::BODY_SESSION_CONTROL/state-domain::LEASE_CURRENTNESS/state-id::ACTIVE",
        },
      ],
      semantic_ref:
        "state-id::BODY_SESSION_CONTROL.LEASE_CURRENTNESS.ACTIVE",
      signal_evidence: [],
    },
    acceptedByAdr,
  );
  requireCondition(
    bodyStateRoute.suggestedAdrId === "ADR-006" &&
      bodyStateRoute.classId === "BODY_DECLARATION_PARTITION_RULE",
    "body state route fixed vector changed",
  );
  cases += 1;
  acceptedByAdr.get("ADR-006").add("BODY_RELEASE_ACCEPTED");
  const bodyEventRoute = expectedRoute(
    {
      exact_name: "BODY_RELEASE_ACCEPTED",
      kind: "EVENT",
      origin_evidence: [
        {
          evidence_kind: "DECLARED_EVENT",
          semantic_location:
            "selector-id::BODY_SESSION_CONTROL/event-id::BODY_RELEASE_ACCEPTED",
        },
      ],
      semantic_ref: "same-transition-kind::BODY_RELEASE_ACCEPTED",
      signal_evidence: [],
    },
    acceptedByAdr,
  );
  requireExact(
    bodyEventRoute,
    {
      basis: [
        "BODY_SESSION_CONTROL",
        "accepted-prose::ADR-006::BODY_RELEASE_ACCEPTED",
      ],
      classId: "BODY_ACCEPTED_PROSE_RULE",
      suggestedAdrId: "ADR-006",
      suggestedSourceAnchor: "ncp-b01-selector-allocation-adr-006-v1",
    },
    "accepted-prose body event route fixed vector",
  );
  cases += 1;
  const forwardingRoute = expectedRoute(
    {
      exact_name: "ForwardingEnvelope",
      kind: "TYPE",
      origin_evidence: [
        {
          evidence_kind: "ARTIFACT_REGISTRY_ENTRY",
          semantic_location:
            "artifact-ref::forwarding-envelope-type::ForwardingEnvelope",
        },
      ],
      semantic_ref: "forwarding-envelope-type::ForwardingEnvelope",
      signal_evidence: [],
    },
    acceptedByAdr,
  );
  requireCondition(
    forwardingRoute.suggestedAdrId === "ADR-003" &&
      forwardingRoute.classId === "SEMANTIC_REFERENCE_RULE",
    "semantic-prefix route fixed vector changed",
  );
  cases += 1;
  expectFailure(
    () =>
      requireClosedKeys(
        { algorithm: "SHA256", authority: true },
        ["algorithm"],
        "closed commitment",
      ),
    "unknown authority field",
  );
  requireCondition(
    MAX_COMPACT_BYTES === 4_194_304,
    "portable compact selector source bound changed",
  );
  cases += 1;
  return cases;
}

function verifyRepository() {
  const authoringRaw = readBounded(
    AUTHORING_PATH,
    MAX_SOURCE_BYTES,
    "selector authoring source",
  );
  const inventoryRaw = readBounded(
    INVENTORY_PATH,
    MAX_INVENTORY_BYTES,
    "selector allocation inventory",
  );
  const inventorySchemaRaw = readBounded(
    INVENTORY_SCHEMA_PATH,
    MAX_SCHEMA_BYTES,
    "selector allocation schema",
  );
  const compactRaw = readBounded(
    COMPACT_PATH,
    MAX_COMPACT_BYTES,
    "compact selector source",
  );
  const proposalRaw = readBounded(
    PROPOSAL_PATH,
    MAX_PROPOSAL_BYTES,
    "selector allocation proposal",
  );
  const proposalSchemaRaw = readBounded(
    PROPOSAL_SCHEMA_PATH,
    MAX_SCHEMA_BYTES,
    "selector allocation proposal schema",
  );

  const authoring = parseCanonicalDocument(authoringRaw, "selector authoring");
  const inventory = parseCanonicalDocument(inventoryRaw, "allocation inventory");
  const compact = parseCanonicalDocument(compactRaw, "compact selector source");
  const proposal = parseCanonicalDocument(proposalRaw, "allocation proposal");
  const { binding, expanded } = reconstructExpanded(authoring, inventory);
  requireJsonDepth(expanded, MAX_JSON_DEPTH, "expanded selector source");

  requireCondition(
    binding.authoring_file === path.basename(INVENTORY_PATH) &&
      binding.authoring_byte_length === inventoryRaw.length &&
      binding.authoring_sha256 === sha256(inventoryRaw),
    "authoring source does not bind exact inventory bytes",
  );
  requireCondition(
    binding.schema_file === path.basename(INVENTORY_SCHEMA_PATH) &&
      binding.schema_byte_length === inventorySchemaRaw.length &&
      binding.schema_sha256 === sha256(inventorySchemaRaw),
    "authoring source does not bind exact allocation schema bytes",
  );
  const profile = inventory.allocation_review_profile;
  requireCondition(
    profile.schema === "ncp.b01-selector-allocation-review-profile.v4",
    "allocation review profile is not v4",
  );
  requireCondition(
    profile.allocation_schema_byte_length === inventorySchemaRaw.length &&
      profile.allocation_schema_sha256 === sha256(inventorySchemaRaw),
    "allocation review profile does not bind exact schema bytes",
  );
  requireCondition(
    inventory.model_allocation_count === profile.model_allocation_count &&
      inventory.model_allocation_sha256 === profile.model_allocation_sha256 &&
      inventory.semantic_shape_entry_count ===
        profile.semantic_shape_entry_count &&
      inventory.semantic_shape_sha256 === profile.semantic_shape_sha256,
    "inventory top-level metrics differ from the v4 review profile",
  );

  const expandedRaw = boundedCanonicalBytes(
    expanded,
    MAX_SOURCE_BYTES,
    "expanded selector source",
  );
  const expandedSha256 = sha256(expandedRaw);
  requireCondition(
    proposal.source.expanded_source.canonical_byte_length === expandedRaw.length &&
      proposal.source.expanded_source.sha256 === expandedSha256,
    "proposal expanded-source identity mismatch",
  );
  requireCondition(
    compact.encoding.expanded_document_sha256 === expandedSha256,
    "compact envelope expanded-source identity mismatch",
  );

  verifySuiteFixedVectors(inventory);
  verifyDocumentCommitments(inventory);
  verifyProvenanceReview(inventory);
  const subject = verifySemanticReviewSubject(
    expanded,
    inventory.semantic_review_subject,
  );
  const shape = verifySemanticShape(expanded, profile);
  const model = verifyAllocationModel(proposal, profile);
  const prose = verifyProposalSourceSet(
    proposal,
    proposalSchemaRaw,
    compactRaw,
  );
  verifyProposalSemantics(
    proposal,
    profile.allocation_identity_commitment_suite,
    prose,
  );
  requireReadSnapshotsUnchanged();

  return {
    claim_boundary:
      "LOCAL_NODE_IMPLEMENTATION_DIVERSITY_ONLY_NOT_EXTERNAL_INDEPENDENT_PEER_REVIEW_ASSIGNMENT_OR_RELEASE_EVIDENCE",
    expanded_sha256: expandedSha256,
    model_allocation_count: model.modelCount,
    model_allocation_sha256: model.modelSha256,
    model_origin_signal_sha256: model.originSignalSha256,
    proposal_rows_sha256:
      proposal.summary.proposal_rows_commitment.projection_sha256,
    schema: "ncp.b01-selector-allocation-portability-verification.v1",
    semantic_review_subject_sha256: subject.sha256,
    semantic_shape_entry_count: shape.entryCount,
    semantic_shape_sha256: shape.sha256,
    status: "PASS",
  };
}

function main() {
  try {
    const selfTestCases = runAlgorithmSelfTest();
    if (process.argv.slice(2).includes("--self-test")) {
      requireCondition(
        process.argv.length === 3,
        "--self-test cannot be combined with other arguments",
      );
      process.stdout.write(
        `selector allocation portability self-test: PASS cases=${selfTestCases}\n`,
      );
      return 0;
    }
    requireCondition(
      process.argv.length === 2,
      "usage: verify_selector_allocation_portability.mjs [--self-test]",
    );
    process.stdout.write(`${canonicalText(verifyRepository())}\n`);
    return 0;
  } catch (error) {
    const message =
      error instanceof Error ? error.message : `unexpected failure: ${String(error)}`;
    process.stderr.write(`selector allocation portability: FAIL: ${message}\n`);
    return 1;
  }
}

process.exitCode = main();
