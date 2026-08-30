import {
  canonicalJsonBytes,
  CanonicalJsonError,
  canonicalJsonText,
} from "./canonical-json.ts";
import {
  DecisionBindingError,
  validateReviewPacketBinding,
} from "./decision-binding.ts";
import { applyPatch, JsonPointerError } from "./json-pointer.ts";
import { evaluateSemantics, SemanticConfigurationError } from "./semantics.ts";
import { extractExactJsonFences, SourceFileError } from "./file-io.ts";
import {
  strictJsonParse,
  StrictJsonError,
  type JsonLimits,
  type JsonValue,
} from "./strict-json.ts";

const encoder = new TextEncoder();
type JsonObject = { [key: string]: JsonValue };

export interface SelfTestReport {
  readonly executed: number;
  readonly detected: number;
}

export function runSelfTests(): SelfTestReport {
  const report = { executed: 0, detected: 0 };
  report.executed += 1;
  const exactFences = extractExactJsonFences(
    encoder.encode(
      '```text\n```json\n{"ignored":true}\n```\n' +
        '```json\r\n{"accepted":true}\r\n```\r\n',
    ),
  );
  if (
    exactFences.length !== 1 ||
    new TextDecoder().decode(exactFences[0]) !== '{"accepted":true}'
  ) {
    throw new Error("exact JSON fence scanner accepted a nested marker");
  }
  report.detected += 1;
  expectThrows(
    () => extractExactJsonFences(encoder.encode("```json\n{}\n")),
    SourceFileError,
    "unclosed exact JSON fence",
    report,
  );
  const limits: JsonLimits = {
    maxBytes: 256,
    maxDepth: 4,
    maxNodes: 8,
    maxMembers: 4,
    maxArrayItems: 4,
    maxKeyBytes: 8,
    maxStringBytes: 8,
    maxTotalStringBytes: 32,
    maxIntegerCharacters: 16,
  };
  const accepted = strictJsonParse(encoder.encode('{"a":[1,true,null]}'), limits);
  if (!isObject(accepted) || !Array.isArray(accepted.a)) {
    throw new Error("strict parser self-test returned the wrong value");
  }

  expectStrictRejection('{"a":1,"a":2}', limits, "duplicate member guard", report);
  expectStrictRejection('{"a":1.0}', limits, "floating-point guard", report);
  expectStrictRejection('{"a":-0}', limits, "negative-zero guard", report);
  expectStrictRejection('{"a":01}', limits, "leading-zero guard", report);
  expectStrictRejection('{"a":9007199254740992}', limits, "safe-integer guard", report);
  expectStrictRejection('{"a":"123456789"}', limits, "string-byte guard", report);
  expectStrictRejection('{"a":{"b":{"c":{"d":0}}}}', limits, "depth guard", report);
  expectStrictRejectionContaining(
    '{"a":1,"b":2,"c":3,"d":4,"oversized":5}',
    limits,
    "member guard before excess-key decoding",
    "object member count exceeds",
    report,
  );
  expectStrictRejection(
    '{"123456789":0}',
    limits,
    "key-byte guard",
    report,
  );
  expectStrictRejection(
    '{"a":"12345678","b":"12345678","c":"12345678","d":"12345678"}',
    limits,
    "total-string-byte guard",
    report,
  );
  expectStrictRejection(
    '{"a":"\\uD83D\\uDE00x"}',
    { ...limits, maxTotalStringBytes: 5 },
    "incremental escaped total-string-byte guard",
    report,
  );
  expectStrictRejection(
    '{"a":12345678901234567}',
    limits,
    "integer-character guard",
    report,
  );
  expectStrictRejection(
    '{"a":[1,2,3,4,5]}',
    { ...limits, maxNodes: 100 },
    "array-item guard",
    report,
  );
  expectStrictRejection(
    '[1,2]',
    { ...limits, maxNodes: 2 },
    "node-count guard",
    report,
  );
  report.executed += 1;
  try {
    strictJsonParse(new Uint8Array(257), limits);
  } catch (error) {
    if (error instanceof StrictJsonError) report.detected += 1;
    else throw new Error("byte-length guard threw the wrong error type");
  }
  if (report.executed !== report.detected) {
    throw new Error("byte-length guard did not reject");
  }
  expectThrows(
    () => strictJsonParse(new Uint8Array([0x7b, 0x22, 0xff, 0x22, 0x3a, 0x31, 0x7d]), limits),
    StrictJsonError,
    "UTF-8 guard",
    report,
  );
  expectThrows(
    () =>
      strictJsonParse(
        new Uint8Array([0xef, 0xbb, 0xbf, 0x7b, 0x7d]),
        limits,
      ),
    StrictJsonError,
    "UTF-8 BOM guard",
    report,
  );
  report.executed += 1;
  const nestedAtMemberLimit = strictJsonParse(
    encoder.encode('{"a":{"b":1}}'),
    { ...limits, maxMembers: 1 },
  );
  if (
    !isObject(nestedAtMemberLimit) ||
    !isObject(nestedAtMemberLimit.a) ||
    nestedAtMemberLimit.a.b !== 1
  ) {
    throw new Error("per-object member guard rejected valid nested objects");
  }
  report.detected += 1;

  const decisionSetIdentity = {
    digest_algorithm: "sha256(domain || u64be(projection_bytes) || projection)",
    domain_hex: "00",
    schema: "ncp.b01-decision-set.v1",
    sha256: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  };
  const mismatchedDecisionSetIdentity = {
    ...decisionSetIdentity,
    sha256: "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  };
  const currentReviewRegistry = currentReviewPacketRegistry(
    decisionSetIdentity,
    [{}],
  );
  report.executed += 1;
  validateReviewPacketBinding(currentReviewRegistry, decisionSetIdentity);
  report.detected += 1;
  let extraSubjectMemberRejected = false;
  try {
    validateReviewPacketBinding(
      reviewSubjectOverride(currentReviewRegistry, { unexpected: false }),
      decisionSetIdentity,
    );
  } catch (error) {
    if (!(error instanceof DecisionBindingError)) {
      throw new Error("CURRENT packet extra-subject-member guard threw the wrong error");
    }
    extraSubjectMemberRejected = true;
  }
  if (!extraSubjectMemberRejected) {
    throw new Error("CURRENT packet extra-subject-member guard did not reject");
  }
  report.executed += 1;
  validateReviewPacketBinding(
    {
      review_packet_lifecycle: {
        schema: "ncp.b01-review-packet-lifecycle.v1",
        state: "SUPERSEDED",
      },
      review_packet_subject: null,
      review_records: [],
    },
    decisionSetIdentity,
  );
  report.detected += 1;
  report.executed += 1;
  validateReviewPacketBinding(
    {
      review_packet_lifecycle: {
        schema: "ncp.b01-review-packet-lifecycle.v1",
        state: "TEMPLATE",
      },
      review_packet_subject: null,
      review_records: [],
    },
    decisionSetIdentity,
  );
  report.detected += 1;
  expectThrows(
    () =>
      validateReviewPacketBinding(
        {
          review_packet_lifecycle: {
            schema: "ncp.b01-review-packet-lifecycle.v1",
            state: "CURRENT",
          },
          review_packet_subject: null,
          review_records: [],
        },
        decisionSetIdentity,
      ),
    DecisionBindingError,
    "CURRENT packet subject guard",
    report,
  );
  expectThrows(
    () =>
      validateReviewPacketBinding(
        currentReviewPacketRegistry(mismatchedDecisionSetIdentity, []),
        decisionSetIdentity,
      ),
    DecisionBindingError,
    "CURRENT packet subject identity guard",
    report,
  );
  expectThrows(
    () =>
      validateReviewPacketBinding(
        {
          review_packet_lifecycle: {
            schema: "ncp.b01-review-packet-lifecycle.v1",
            state: "SUPERSEDED",
          },
          review_packet_subject: structuredClone(
            currentReviewRegistry.review_packet_subject as JsonValue,
          ),
          review_records: [],
        },
        decisionSetIdentity,
      ),
    DecisionBindingError,
    "superseded packet subject guard",
    report,
  );
  expectThrows(
    () =>
      validateReviewPacketBinding(
        {
          review_packet_lifecycle: {
            schema: "ncp.b01-review-packet-lifecycle.v1",
            state: "TEMPLATE",
          },
          review_packet_subject: structuredClone(
            currentReviewRegistry.review_packet_subject as JsonValue,
          ),
          review_records: [],
        },
        decisionSetIdentity,
      ),
    DecisionBindingError,
    "template packet subject guard",
    report,
  );
  expectThrows(
    () =>
      validateReviewPacketBinding(
        {
          review_packet_lifecycle: {
            schema: "ncp.b01-review-packet-lifecycle.v1",
            state: "SUPERSEDED",
          },
          review_packet_subject: null,
          review_records: [{}],
        },
        decisionSetIdentity,
      ),
    DecisionBindingError,
    "non-current review-record guard",
    report,
  );
  expectThrows(
    () =>
      validateReviewPacketBinding(
        {
          review_packet_lifecycle: {
            schema: "ncp.b01-review-packet-lifecycle.v1",
            state: "UNKNOWN",
          },
          review_packet_subject: null,
          review_records: [],
        },
        decisionSetIdentity,
      ),
    DecisionBindingError,
    "packet lifecycle state guard",
    report,
  );
  expectThrows(
    () =>
      validateReviewPacketBinding(
        {
          review_packet_lifecycle: {
            schema: "ncp.b01-review-packet-lifecycle.v0",
            state: "SUPERSEDED",
          },
          review_packet_subject: null,
          review_records: [],
        },
        decisionSetIdentity,
      ),
    DecisionBindingError,
    "packet lifecycle schema guard",
    report,
  );
  expectThrows(
    () =>
      validateReviewPacketBinding(
        {
          review_packet_lifecycle: {
            schema: "ncp.b01-review-packet-lifecycle.v1",
            state: "SUPERSEDED",
            unexpected: false,
          },
          review_packet_subject: null,
          review_records: [],
        },
        decisionSetIdentity,
      ),
    DecisionBindingError,
    "packet lifecycle member-set guard",
    report,
  );
  expectThrows(
    () =>
      validateReviewPacketBinding(
        {
          review_packet_lifecycle: {
            schema: "ncp.b01-review-packet-lifecycle.v1",
          },
          review_packet_subject: null,
          review_records: [],
        },
        decisionSetIdentity,
      ),
    DecisionBindingError,
    "packet lifecycle missing-state guard",
    report,
  );
  expectThrows(
    () =>
      validateReviewPacketBinding(
        {
          review_packet_lifecycle: {
            schema: "ncp.b01-review-packet-lifecycle.v1",
            state: "SUPERSEDED",
          },
          review_records: [],
        },
        decisionSetIdentity,
      ),
    DecisionBindingError,
    "packet lifecycle missing-subject guard",
    report,
  );
  expectThrows(
    () =>
      validateReviewPacketBinding(
        {
          review_packet_lifecycle: {
            schema: "ncp.b01-review-packet-lifecycle.v1",
            state: "CURRENT",
          },
          review_packet_subject: { decision_set: decisionSetIdentity },
        },
        decisionSetIdentity,
      ),
    DecisionBindingError,
    "packet lifecycle missing-review-records guard",
    report,
  );

  const numericNestedBoolean = structuredClone(currentReviewRegistry);
  const numericNestedSubject = requiredSelfTestObject(
    numericNestedBoolean.review_packet_subject,
    "numeric nested subject",
  );
  const numericNestedDecisions = requiredSelfTestArray(
    numericNestedSubject.decisions,
    "numeric nested decisions",
  );
  const numericNestedDecision = requiredSelfTestObject(
    numericNestedDecisions[0],
    "numeric nested decision",
  );
  const numericNestedReviews = requiredSelfTestArray(
    numericNestedDecision.required_reviews,
    "numeric nested required reviews",
  );
  requiredSelfTestObject(
    numericNestedReviews[0],
    "numeric nested required review",
  ).requires_independence = 0;

  const emptyClaim = reviewSubjectOverride(currentReviewRegistry, {
    claim_boundary: "",
  });
  emptyClaim.claim_boundary = "";

  const orderedRegistry = structuredClone(currentReviewRegistry);
  const orderedRegistryDecisions = requiredSelfTestArray(
    orderedRegistry.decisions,
    "ordered registry decisions",
  );
  const orderedSubject = requiredSelfTestObject(
    orderedRegistry.review_packet_subject,
    "ordered review subject",
  );
  const orderedSubjectDecisions = requiredSelfTestArray(
    orderedSubject.decisions,
    "ordered review decisions",
  );
  const secondRegistryDecision = structuredClone(
    requiredSelfTestObject(orderedRegistryDecisions[0], "first registry decision"),
  );
  secondRegistryDecision.id = "ADR-002";
  secondRegistryDecision.title = "Second self-test decision";
  secondRegistryDecision.path = "docs/adr/0002-self-test.md";
  secondRegistryDecision.content_sha256 = "2".repeat(64);
  orderedRegistryDecisions.push(secondRegistryDecision);
  const secondSubjectDecision = structuredClone(
    requiredSelfTestObject(orderedSubjectDecisions[0], "first review decision"),
  );
  secondSubjectDecision.id = "ADR-002";
  secondSubjectDecision.title = "Second self-test decision";
  secondSubjectDecision.path = "docs/adr/0002-self-test.md";
  secondSubjectDecision.content_sha256 = "2".repeat(64);
  orderedSubjectDecisions.push(secondSubjectDecision);
  report.executed += 1;
  validateReviewPacketBinding(orderedRegistry, decisionSetIdentity);
  report.detected += 1;
  const swappedDecisions = structuredClone(orderedRegistry);
  requiredSelfTestArray(
    requiredSelfTestObject(
      swappedDecisions.review_packet_subject,
      "swapped review subject",
    ).decisions,
    "swapped review decisions",
  ).reverse();

  const hostileReviewBindings: ReadonlyArray<readonly [string, JsonObject]> = [
    [
      "CURRENT subject schema guard",
      reviewSubjectOverride(currentReviewRegistry, {
        schema: "ncp.b01-review-subject.v0",
      }),
    ],
    [
      "CURRENT subject state guard",
      reviewSubjectOverride(currentReviewRegistry, { state: "SUPERSEDED" }),
    ],
    [
      "CURRENT subject numeric-false guard",
      reviewSubjectOverride(currentReviewRegistry, { normative: 0 }),
    ],
    [
      "CURRENT subject numeric-true guard",
      reviewSubjectOverride(currentReviewRegistry, { promotion_blocked: 1 }),
    ],
    [
      "CURRENT subject claim-boundary guard",
      reviewSubjectOverride(currentReviewRegistry, { claim_boundary: "different" }),
    ],
    [
      "CURRENT subject review-policy guard",
      reviewSubjectOverride(currentReviewRegistry, {
        review_policy: { schema: "ncp.b01-review-policy.v0" },
      }),
    ],
    [
      "CURRENT subject missing-member guard",
      reviewSubjectWithoutMember(currentReviewRegistry, "decisions"),
    ],
    [
      "CURRENT source commit guard",
      reviewSubjectSourceOverride(currentReviewRegistry, { commit: "A".repeat(40) }),
    ],
    [
      "CURRENT source tree guard",
      reviewSubjectSourceOverride(currentReviewRegistry, { tree: "0".repeat(39) }),
    ],
    [
      "CURRENT decision-source digest guard",
      reviewDecisionSourceOverride(currentReviewRegistry, { sha256: "A".repeat(64) }),
    ],
    [
      "CURRENT decision-source path guard",
      reviewDecisionSourceOverride(currentReviewRegistry, {
        path: "docs/adr/other.json",
      }),
    ],
    [
      "CURRENT decision-source byte guard",
      reviewDecisionSourceOverride(currentReviewRegistry, { bytes: 2_097_153 }),
    ],
    [
      "CURRENT decision-source member-set guard",
      reviewDecisionSourceOverride(currentReviewRegistry, { unexpected: false }),
    ],
    [
      "CURRENT source member-set guard",
      reviewSubjectSourceOverride(currentReviewRegistry, { unexpected: false }),
    ],
    [
      "CURRENT decision projection guard",
      reviewSubjectDecisionOverride(currentReviewRegistry, {
        title: "Different self-test decision",
      }),
    ],
    [
      "CURRENT decision extra-member guard",
      reviewSubjectDecisionOverride(currentReviewRegistry, { status: "PROPOSED" }),
    ],
    [
      "CURRENT decision missing-member guard",
      reviewSubjectDecisionWithoutMember(currentReviewRegistry, "defect_ids"),
    ],
    ["CURRENT nested boolean type guard", numericNestedBoolean],
    ["CURRENT aligned empty-claim guard", emptyClaim],
    ["CURRENT decision-order guard", swappedDecisions],
  ];
  for (const [label, hostile] of hostileReviewBindings) {
    expectThrows(
      () => validateReviewPacketBinding(hostile, decisionSetIdentity),
      DecisionBindingError,
      label,
      report,
    );
  }

  const patched = applyPatch(
    { a: { b: 1 }, list: ["x"] },
    [
      { op: "replace", path: "/a/b", value: 2 },
      { op: "add", path: "/list/-", value: "y" },
      { op: "remove", path: "/list/0" },
    ],
  );
  if (
    !isObject(patched) ||
    !isObject(patched.a) ||
    patched.a.b !== 2 ||
    !Array.isArray(patched.list) ||
    patched.list.length !== 1 ||
    patched.list[0] !== "y"
  ) {
    throw new Error("JSON Pointer self-test returned the wrong value");
  }
  expectThrows(
    () => applyPatch({ a: 1 }, [{ op: "add", path: "/a", value: 2 }]),
    JsonPointerError,
    "add-overwrite guard",
    report,
  );
  expectThrows(
    () => applyPatch({ a: 1 }, [{ op: "replace", path: "/missing", value: 2 }]),
    JsonPointerError,
    "missing-target guard",
    report,
  );
  expectThrows(
    () => applyPatch({ a: 1 }, [{ op: "remove", path: "/~2" }]),
    JsonPointerError,
    "JSON Pointer escape guard",
    report,
  );
  expectThrows(
    () => applyPatch({ a: 1 }, [{ op: "remove", path: "" }]),
    JsonPointerError,
    "root-mutation guard",
    report,
  );
  let oversizedPointerRejected = false;
  try {
    applyPatch({ a: 1 }, [{ op: "remove", path: `/${"x".repeat(512)}` }]);
  } catch (error) {
    if (!(error instanceof JsonPointerError)) throw error;
    oversizedPointerRejected = true;
  }
  if (!oversizedPointerRejected) {
    throw new Error("JSON Pointer byte-bound guard did not reject");
  }
  const prototypeKey = applyPatch({}, [
    { op: "add", path: "/__proto__", value: { polluted: true } },
  ]);
  if (
    !isObject(prototypeKey) ||
    !Object.hasOwn(prototypeKey, "__proto__") ||
    ({} as { polluted?: boolean }).polluted !== undefined
  ) {
    throw new Error("JSON Pointer prototype-key isolation failed");
  }

  expectThrows(
    () =>
      evaluateSemantics({
        sourcePath: "docs/adr/0004-observer-attach-grants-and-revocation.md",
        ordinal: 1,
        profile: "ADR001_PLANT_KIND_SEPARATION_FRAGMENT_V1",
        document: { allocates_output_slot: false, state: "PENDING_INTENT_ONLY" },
        fixture: { expected_state: "PENDING_INTENT_ONLY", output_allocation_permitted: false },
      }),
    SemanticConfigurationError,
    "source-profile binding guard",
    report,
  );
  expectThrows(
    () =>
      evaluateSemantics({
        sourcePath: "docs/adr/0004-observer-attach-grants-and-revocation.md",
        ordinal: 1,
        profile: "ADR004_PENDING_RELEASE_RESERVATION_NONALLOCATION_V1",
        document: { allocates_output_slot: false, state: "PENDING_INTENT_ONLY" },
        fixture: {
          expected_state: "PENDING_INTENT_ONLY",
          output_allocation_permitted: false,
          unregistered_default: true,
        },
      }),
    SemanticConfigurationError,
    "fixture closure guard",
    report,
  );
  report.executed += 1;
  const semanticHostile = evaluateSemantics({
    sourcePath: "docs/adr/0004-observer-attach-grants-and-revocation.md",
    ordinal: 1,
    profile: "ADR004_PENDING_RELEASE_RESERVATION_NONALLOCATION_V1",
    document: { allocates_output_slot: true, state: "PENDING_INTENT_ONLY" },
    fixture: { expected_state: "PENDING_INTENT_ONLY", output_allocation_permitted: false },
  });
  if (
    semanticHostile.result !== "REJECT" ||
    semanticHostile.productionAdmission !== "NOT_APPLICABLE" ||
    semanticHostile.diagnostics.join(",") !== "PENDING_STATE_ALLOCATES_OUTPUT"
  ) {
    throw new Error("semantic hostile control escaped its guard");
  }
  report.detected += 1;

  report.executed += 1;
  const malformedQosRealm = evaluateSemantics({
    sourcePath: "docs/adr/0010-plane-qos-retention-and-overload.md",
    ordinal: 1,
    profile: "ADR010_ACTION_QOS_PROFILE_V1",
    document: {
      authority_realm_key: { server_authority_principal_id: "ncp-authority-a" },
      plane: "action",
      route: "realm-a/session/a/command/b",
      profile_id: "ncp-action-v1",
      capacity_per_stream: 1,
      ordering: "strict_stream_sequence",
      retention: "until_terminal_disposition_or_expiry",
      overload: "reject_new_active_and_emit_disposition",
      fail_safe_priority: ["estop", "hold", "active"],
    },
    fixture: {
      authenticated_realm_key: {
        server_authority_principal_id: "ncp-authority-a",
        stable_realm_id: "realm-a",
      },
      expected_route: "realm-a/session/a/command/b",
      maximum_capacity_per_stream: 1,
      required_fail_safe_priority: ["estop", "hold", "active"],
    },
  });
  const unsafeKeyEpoch = evaluateSemantics({
    sourcePath: "docs/adr/0009-security-state-rotation-and-revocation.md",
    ordinal: 1,
    profile: "ADR009_SECURITY_STATE_PROJECTION_V1",
    document: {
      authority_realm: {
        server_authority_principal: "spiffe://ncp.example/body-server",
        stable_realm_id: "plant-a",
      },
      profile: "ncp-production-ingress-v1",
      security_epoch: 12,
      revocation_epoch: 12,
      principals: [{ principal_id: "body-a", role: "body", planes: ["action"] }],
      key_epochs: [{
        kid: "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        algorithm: "Ed25519",
        epoch: 9_007_199_254_740_992,
      }],
    },
    fixture: {
      authenticated_authority_realm: {
        server_authority_principal: "spiffe://ncp.example/body-server",
        stable_realm_id: "plant-a",
      },
      maximum_security_epoch: 9_007_199_254_740_991,
      required_key_algorithm: "Ed25519",
      required_profile: "ncp-production-ingress-v1",
    },
  });
  const missingKeyEpochs = evaluateSemantics({
    sourcePath: "docs/adr/0009-security-state-rotation-and-revocation.md",
    ordinal: 1,
    profile: "ADR009_SECURITY_STATE_PROJECTION_V1",
    document: {
      authority_realm: {
        server_authority_principal: "spiffe://ncp.example/body-server",
        stable_realm_id: "plant-a",
      },
      profile: "ncp-production-ingress-v1",
      security_epoch: 12,
      revocation_epoch: 12,
      principals: [{ principal_id: "body-a", role: "body", planes: ["action"] }],
    },
    fixture: {
      authenticated_authority_realm: {
        server_authority_principal: "spiffe://ncp.example/body-server",
        stable_realm_id: "plant-a",
      },
      maximum_security_epoch: 9_007_199_254_740_991,
      required_key_algorithm: "Ed25519",
      required_profile: "ncp-production-ingress-v1",
    },
  });
  if (
    malformedQosRealm.result !== "REJECT" ||
    malformedQosRealm.diagnostics.join(",") !== "AUTHORITY_REALM_KEY_REQUIRED" ||
    unsafeKeyEpoch.result !== "REJECT" ||
    unsafeKeyEpoch.diagnostics.join(",") !== "KEY_EPOCH_MEMBERSHIP_REQUIRED" ||
    missingKeyEpochs.result !== "REJECT" ||
    missingKeyEpochs.diagnostics.join(",") !== "KEY_EPOCH_MEMBERSHIP_REQUIRED"
  ) {
    throw new Error("cross-language identity or exact-integer guard failed");
  }
  report.detected += 1;

  const contractFixture = {
    authenticated_realm_key: {
      server_authority_principal_id: "ncp-authority-a",
      stable_realm_id: "realm-a",
    },
    digest_algorithm: "sha256",
    expected_stable_core_digest:
      "sha256:1111111111111111111111111111111111111111111111111111111111111111",
  };
  const contractDocument = {
    authority_realm_key: contractFixture.authenticated_realm_key,
    stable_core_digest:
      "sha256:1111111111111111111111111111111111111111111111111111111111111111",
  };
  report.executed += 1;
  const compatibleMinor = evaluateSemantics({
    sourcePath: "docs/adr/0002-contract-identity-and-release-authorization.md",
    ordinal: 1,
    profile: "ADR002_REALM_BOUND_CONTRACT_IDENTITY_V1",
    document: { ...contractDocument, wire_version: "1.18446744073709551615" },
    fixture: contractFixture,
  });
  if (
    compatibleMinor.result !== "MATCH_NON_AUTHORIZING_EXCERPT" ||
    compatibleMinor.diagnostics.length !== 0
  ) {
    throw new Error("canonical same-major wire version was rejected");
  }
  report.detected += 1;

  report.executed += 1;
  const shorthand = evaluateSemantics({
    sourcePath: "docs/adr/0002-contract-identity-and-release-authorization.md",
    ordinal: 1,
    profile: "ADR002_REALM_BOUND_CONTRACT_IDENTITY_V1",
    document: {
      ...contractDocument,
      wire_version: "1",
      contract_hash: "163acc57d8a62b66",
    },
    fixture: contractFixture,
  });
  if (shorthand.result !== "MATCH_NON_AUTHORIZING_EXCERPT" || shorthand.diagnostics.length !== 0) {
    throw new Error("canonical 1 shorthand or advisory compact hash was rejected");
  }
  report.detected += 1;

  report.executed += 1;
  const malformedMinor = evaluateSemantics({
    sourcePath: "docs/adr/0002-contract-identity-and-release-authorization.md",
    ordinal: 1,
    profile: "ADR002_REALM_BOUND_CONTRACT_IDENTITY_V1",
    document: { ...contractDocument, wire_version: "1.00" },
    fixture: contractFixture,
  });
  const oversizedMinor = evaluateSemantics({
    sourcePath: "docs/adr/0002-contract-identity-and-release-authorization.md",
    ordinal: 1,
    profile: "ADR002_REALM_BOUND_CONTRACT_IDENTITY_V1",
    document: { ...contractDocument, wire_version: "1.184467440737095516150" },
    fixture: contractFixture,
  });
  if (
    malformedMinor.result !== "REJECT" ||
    malformedMinor.diagnostics.join(",") !== "WIRE_VERSION_MISMATCH" ||
    oversizedMinor.result !== "REJECT" ||
    oversizedMinor.diagnostics.join(",") !== "WIRE_VERSION_MISMATCH"
  ) {
    throw new Error("noncanonical same-major wire version escaped its guard");
  }
  report.detected += 1;

  report.executed += 1;
  const hierarchicalRealm = evaluateSemantics({
    sourcePath: "docs/adr/0005-declared-stream-lifecycle.md",
    ordinal: 1,
    profile: "ADR005_DECLARE_STREAM_EXCERPT_V1",
    document: {
      ncp_version: "1",
      kind: "declare_stream",
      authority_realm_key: {
        server_authority_principal_id: "ncp-authority-a",
        stable_realm_id: "region-a/plant-a",
      },
      route: "region-a/plant-a/session/plant-alpha/action/controller-a",
      sequence_start: 1,
      publisher_principal_id: "haldir-commander-a",
      stream_epoch: "00000000-0000-4000-8000-000000000001",
    },
    fixture: {
      authenticated_publisher_principal_id: "haldir-commander-a",
      authenticated_realm_key: {
        server_authority_principal_id: "ncp-authority-a",
        stable_realm_id: "region-a/plant-a",
      },
      expected_route: "region-a/plant-a/session/plant-alpha/action/controller-a",
      live_declaration_epoch_ids: [],
    },
  });
  if (
    hierarchicalRealm.result !== "MATCH_NON_AUTHORIZING_EXCERPT" ||
    hierarchicalRealm.diagnostics.length !== 0
  ) {
    throw new Error("hierarchical stable realm did not bind the complete route prefix");
  }
  report.detected += 1;

  const canonicalFixture = { z: 1, a: "é" };
  const canonicalExpected = '{"a":"é","z":1}';
  const canonicalExpectedBytes = encoder.encode(canonicalExpected);
  const canonicalBytes = canonicalJsonBytes(
    canonicalFixture,
    canonicalExpectedBytes.byteLength,
  );
  if (
    canonicalJsonText(canonicalFixture, canonicalExpectedBytes.byteLength) !==
      canonicalExpected ||
    canonicalBytes.byteLength !== canonicalExpectedBytes.byteLength ||
    canonicalBytes.some((byte, index) => byte !== canonicalExpectedBytes[index])
  ) {
    throw new Error("canonical JSON self-test returned unstable bytes");
  }
  let canonicalBoundRejected = false;
  try {
    canonicalJsonBytes(canonicalFixture, canonicalExpectedBytes.byteLength - 1);
  } catch (error) {
    if (!(error instanceof CanonicalJsonError)) {
      throw new Error("canonical JSON byte-bound self-test threw the wrong error");
    }
    canonicalBoundRejected = true;
  }
  if (!canonicalBoundRejected) {
    throw new Error("canonical JSON byte-bound self-test did not reject");
  }
  report.executed += 1;
  if (
    canonicalJsonText({ "\u{1f600}": 2, "\ue000": 1 }) !==
    '{"\ue000":1,"\u{1f600}":2}'
  ) {
    throw new Error("canonical JSON did not order keys by Unicode scalar value");
  }
  report.detected += 1;
  return report;
}

function currentReviewPacketRegistry(
  registeredIdentity: JsonObject,
  reviewRecords: JsonValue[],
): JsonObject {
  const reviewPolicy: JsonObject = {
    schema: "ncp.b01-review-policy.v1",
    generator: { path: "scripts/generate_decision_registry.py" },
  };
  const packetDecisionSource: JsonObject = {
    path: "docs/adr/decision-registry.source.v1.json",
    sha256: "c".repeat(64),
    bytes: 1,
  };
  const subjectDecision: JsonObject = {
    id: "ADR-001",
    title: "Self-test decision",
    path: "docs/adr/0001-self-test.md",
    module_paths: [],
    content_sha256: "d".repeat(64),
    bytes: 1,
    source_set: {},
    required_reviews: [{ role_id: "reviewer", requires_independence: false }],
    defect_ids: ["D01"],
  };
  return {
    normative: false,
    promotion_blocked: true,
    claim_boundary: "Self-test non-authorizing claim boundary.",
    review_policy: structuredClone(reviewPolicy),
    source: {
      path: "docs/adr/decision-registry.source.v1.json",
      sha256: "1".repeat(64),
      bytes: 2,
    },
    decisions: [{ ...structuredClone(subjectDecision), status: "PROPOSED" }],
    review_packet_lifecycle: {
      schema: "ncp.b01-review-packet-lifecycle.v1",
      state: "CURRENT",
    },
    review_packet_subject: {
      schema: "ncp.b01-review-subject.v1",
      state: "CURRENT",
      normative: false,
      claim_boundary: "Self-test non-authorizing claim boundary.",
      promotion_blocked: true,
      decision_set: structuredClone(registeredIdentity),
      review_policy: structuredClone(reviewPolicy),
      source: {
        commit: "e".repeat(40),
        tree: "f".repeat(40),
        decision_source: structuredClone(packetDecisionSource),
      },
      decisions: [structuredClone(subjectDecision)],
    },
    review_records: structuredClone(reviewRecords),
  };
}

function reviewSubjectOverride(registry: JsonObject, override: JsonObject): JsonObject {
  const hostile = structuredClone(registry);
  Object.assign(requiredSelfTestObject(hostile.review_packet_subject, "review subject"), override);
  return hostile;
}

function reviewSubjectSourceOverride(
  registry: JsonObject,
  override: JsonObject,
): JsonObject {
  const hostile = structuredClone(registry);
  const subject = requiredSelfTestObject(hostile.review_packet_subject, "review subject");
  Object.assign(requiredSelfTestObject(subject.source, "review subject source"), override);
  return hostile;
}

function reviewDecisionSourceOverride(
  registry: JsonObject,
  override: JsonObject,
): JsonObject {
  const hostile = structuredClone(registry);
  const subject = requiredSelfTestObject(hostile.review_packet_subject, "review subject");
  const source = requiredSelfTestObject(subject.source, "review subject source");
  Object.assign(
    requiredSelfTestObject(source.decision_source, "review subject decision source"),
    override,
  );
  return hostile;
}

function reviewSubjectDecisionOverride(
  registry: JsonObject,
  override: JsonObject,
): JsonObject {
  const hostile = structuredClone(registry);
  const subject = requiredSelfTestObject(hostile.review_packet_subject, "review subject");
  if (!Array.isArray(subject.decisions) || subject.decisions.length === 0) {
    throw new Error("review subject decisions fixture is empty");
  }
  Object.assign(requiredSelfTestObject(subject.decisions[0], "review subject decision"), override);
  return hostile;
}

function reviewSubjectWithoutMember(registry: JsonObject, member: string): JsonObject {
  const hostile = structuredClone(registry);
  delete requiredSelfTestObject(hostile.review_packet_subject, "review subject")[member];
  return hostile;
}

function reviewSubjectDecisionWithoutMember(
  registry: JsonObject,
  member: string,
): JsonObject {
  const hostile = structuredClone(registry);
  const subject = requiredSelfTestObject(hostile.review_packet_subject, "review subject");
  if (!Array.isArray(subject.decisions) || subject.decisions.length === 0) {
    throw new Error("review subject decisions fixture is empty");
  }
  delete requiredSelfTestObject(subject.decisions[0], "review subject decision")[member];
  return hostile;
}

function requiredSelfTestObject(value: JsonValue | undefined, label: string): JsonObject {
  if (!isObject(value)) throw new Error(`${label} fixture is not an object`);
  return value;
}

function requiredSelfTestArray(
  value: JsonValue | undefined,
  label: string,
): JsonValue[] {
  if (!Array.isArray(value)) throw new Error(`${label} fixture is not an array`);
  return value;
}

function expectStrictRejection(
  source: string,
  limits: JsonLimits,
  label: string,
  report: { executed: number; detected: number },
): void {
  expectThrows(
    () => strictJsonParse(encoder.encode(source), limits),
    StrictJsonError,
    label,
    report,
  );
}

function expectStrictRejectionContaining(
  source: string,
  limits: JsonLimits,
  label: string,
  detail: string,
  report: { executed: number; detected: number },
): void {
  report.executed += 1;
  try {
    strictJsonParse(encoder.encode(source), limits);
  } catch (error) {
    if (error instanceof StrictJsonError && error.message.includes(detail)) {
      report.detected += 1;
      return;
    }
    throw new Error(`${label} threw the wrong error`);
  }
  throw new Error(`${label} did not reject`);
}

function expectThrows(
  action: () => unknown,
  constructor: new (...args: never[]) => Error,
  label: string,
  report: { executed: number; detected: number },
): void {
  report.executed += 1;
  try {
    action();
  } catch (error) {
    if (error instanceof constructor) {
      report.detected += 1;
      return;
    }
    throw new Error(`${label} threw the wrong error type`);
  }
  throw new Error(`${label} did not reject`);
}

function isObject(value: unknown): value is JsonObject {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}
