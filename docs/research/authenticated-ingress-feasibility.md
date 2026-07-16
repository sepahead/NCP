# Authenticated-ingress feasibility for NCP 1.0

> **Decision status:** accepted for quarantined local-feasibility prototypes;
> not accepted for a shipping adapter, normative contract change, release gate,
> or production deployment. NCP remains the unreleased, release-blocked
> `1.0.0-rc.1` candidate on wire `1.0` with compact proto hash
> `163acc57d8a62b66`. Direct Zenoh `production-secure` remains fail-closed.

## Purpose and excluded claims

This document decides what task `B04` may prototype before any protocol ADR is
ratified or any stable source changes. It answers one narrow prerequisite:

> Can an NCP implementation obtain an authenticated actor at an application
> boundary without trusting payload identity or weakening the current
> fail-closed policy?

The local prototype answer is **yes** through a distinct TLS-terminating ingress,
and **yes under a strict forwarding-only profile** through a signed outer
envelope when a forwarder is unavoidable. These are bounded feasibility results,
not shipping decisions. They do not make the current Zenoh adapter secure.

This work deliberately does not:

- change `proto/ncp.proto`, generated types, schemas, vectors, compact hash,
  manifests, packages, or any other stable wire source;
- add a shipping transport, capability, or extension;
- let a prototype identity, signature, route, or parser result grant an NCP
  lease, operation success, plant authority, safe-action result, or ESTOP result;
- count local TLS as the live mTLS/ACL/rotation/revocation gate;
- count two implementations written during this task as two independent people;
- count external-model advice as review, proof, interoperability, or evidence;
- claim independent peers, duration fuzzing, soak, key custody, plant safety,
  scale, publication, or release readiness.

## Fixed inputs

### Candidate boundary

The current security boundary is non-negotiable:

1. `IdentityClaim` is payload metadata, never proof.
2. A verified actor must be derived from the security boundary that performed
   authentication.
3. The verified actor must match the claimed principal, entity, role, actual
   route, plane, message class, live session generation, and current manifest.
4. Missing, unknown, stale, ambiguous, or mismatched data rejects.
5. Authentication is necessary but never sufficient for authorization. Leases,
   epochs, idempotency, receipts, and plant-local admission remain separate.

### Pinned Zenoh input

NCP pins `zenoh` `1.9.0`. The local Cargo registry records crates.io checksum
`85e22d7002ac149ef17fe400bb40a267ebbba40a83413bab03da7762256fa94e` and
upstream commit
`81c6c933b6e41d72a05f04c4442ef57717ddc72b`. Those exact bytes, rather than a
newer `latest` API, are the relevant implementation input.

The source review found:

| Surface | Callback-visible data | Authentication conclusion |
| --- | --- | --- |
| Stable subscriber `Sample` | key expression, payload, kind, encoding, timestamp, QoS, and attachment | No remote certificate principal is exposed. |
| Unstable `SourceInfo` | `EntityGlobalId` and source sequence number | A publisher or query builder can supply it, so NCP cannot treat it as authentication. |
| Queryable `Query` | selector, payload, encoding, attachment, and optional unstable `SourceInfo` | The optional source has the same sender-supplied limitation. |
| Query `Reply` | result and optional unstable Zenoh replier entity ID | A Zenoh entity ID is not the verified certificate identity bound to the request. |
| Liveliness | samples/replies whose source and replier information are set to `None` | Liveliness does not repair the identity gap. |
| `SessionInfo` | the local Zenoh ID and connected router/peer Zenoh IDs | It does not attribute an individual callback delivery to a verified certificate principal. |
| Router TLS and ACL | certificate common-name authentication and message filtering inside the Zenoh runtime | These facts are useful defense in depth, but the reviewed callback does not carry the verified fact to NCP's payload-binding decision. |

Primary sources:

- [Zenoh 1.9.0 `SourceInfo` source](https://github.com/eclipse-zenoh/zenoh/blob/81c6c933b6e41d72a05f04c4442ef57717ddc72b/zenoh/src/api/sample.rs#L77-L107)
  shows the unstable entity-ID and sequence-number shape.
- [Zenoh 1.9.0 sample builder source](https://github.com/eclipse-zenoh/zenoh/blob/81c6c933b6e41d72a05f04c4442ef57717ddc72b/zenoh/src/api/builders/sample.rs#L200-L213)
  shows that the sending builder can set `SourceInfo`.
- [Zenoh 1.9.0 queryable source](https://github.com/eclipse-zenoh/zenoh/blob/81c6c933b6e41d72a05f04c4442ef57717ddc72b/zenoh/src/api/queryable.rs#L170-L347)
  lists the application-visible query fields and optional source information.
- [Zenoh 1.9.0 session source](https://github.com/eclipse-zenoh/zenoh/blob/81c6c933b6e41d72a05f04c4442ef57717ddc72b/zenoh/src/api/session.rs#L2038-L2060)
  and its [liveliness reply path](https://github.com/eclipse-zenoh/zenoh/blob/81c6c933b6e41d72a05f04c4442ef57717ddc72b/zenoh/src/api/session.rs#L3096-L3116)
  construct liveliness samples with no source information.
- [Zenoh 1.9.0 `SessionInfo` documentation](https://docs.rs/zenoh/1.9.0/zenoh/session/struct.SessionInfo.html)
  defines session, router, and peer Zenoh-ID access.
- [Zenoh TLS documentation](https://zenoh.io/docs/manual/tls/) requires explicit
  protocol filtering to prevent non-TLS connectivity and documents mutual TLS.
- [Zenoh access-control documentation](https://zenoh.io/docs/manual/access-control/)
  documents certificate-common-name subjects, default permissions, topology
  sensitivity, and the fact that an empty subject is a wildcard.

### Direct-Zenoh decision

The direct `ncp-zenoh` path stays fail-closed for `production-secure`. A TLS link,
router-side ACL decision, Zenoh ID, key expression, or payload claim cannot be
silently promoted into the missing callback-visible authenticated principal.
Reconsideration requires a future exactly pinned Zenoh version whose application
delivery API exposes the verified principal for each message, followed by a fresh
source review, negative probe, and live evidence. Version novelty alone is not
evidence.

## Threat model

The attacker may:

- fully control a network, publish arbitrary bytes, choose payload identity, and
  replay, reorder, duplicate, delay, truncate, or route messages;
- possess a valid but unauthorized certificate or signing key;
- select any syntactically available transport, JOSE form, algorithm label,
  route, plane, message class, epoch, sequence, or manifest identifier;
- race manifest rotation, replay-state persistence, connection teardown, and
  concurrent admission;
- craft invalid UTF-8, duplicate JSON names, deep or wide JSON, noncanonical
  base64url, unsafe integers, and divergent Ed25519 encodings;
- crash or restart a process between replay check and durable commit;
- exploit a forwarder, parser, TLS ingress, logging path, queue, FFI boundary,
  unsafe block, or confused-deputy mapping;
- cause availability loss. A fail-closed denial is safer than an authority grant,
  but its operational and plant consequences must still be measured honestly.

The attacker is not assumed able to break TLS 1.3, SHA-256, or Ed25519 as
specified. Private-key protection, CA operations, host compromise, and physical
plant certification remain external assumptions and gates.

## Decision A: terminating TLS 1.3 ingress

### Role

A distinct ingress terminates TLS because that process is the boundary that can
actually observe the verified peer certificate. It is the primary design to
prototype. It is not a Zenoh mode and does not claim to fix Zenoh.

The prototype pipeline is:

```text
TLS 1.3 handshake
  -> verified client leaf DER
  -> SHA-256 fingerprint
  -> one immutable manifest snapshot
  -> exact fingerprint + route + plane + class mapping
  -> exact inner identity comparison
  -> immutable authenticated context + same immutable bounded payload buffer
  -> ordinary NCP authentication/authorization/admission checks
```

### Required invariants

The prototype acceptance checks all of these:

1. TLS is exactly 1.3. Non-TLS endpoints, TLS 1.2 or below, opportunistic
   downgrade, and alternate protocols are unavailable on this endpoint.
2. A client certificate is required during the initial handshake. Application
   bytes are not processed before certificate verification completes.
3. Session tickets, pre-shared-key resumption, 0-RTT, and post-handshake client
   authentication are disabled. If the chosen library cannot demonstrate that
   configuration, the prototype is a no-go.
4. The server fingerprints the exact verified peer leaf DER bytes. It does not
   hash a re-encoded certificate, a subject string, a common name, or an arbitrary
   chain element, and it never falls back from fingerprint matching.
5. A bounded, content-addressed, default-deny manifest has unique principal IDs,
   entity IDs, certificate fingerprints, routes, planes, roles, and message
   classes. A duplicate, wildcard, missing field, unknown member, invalid digest,
   excessive size, stale generation, or empty mapping prevents service.
6. One manifest snapshot and generation cover a complete message decision. The
   verified actor records that generation.
7. Route, plane, and message class are pinned by endpoint profile and checked
   again against the manifest and payload. They never default from payload data.
8. The payload `IdentityClaim` exactly matches the manifest-derived principal,
   entity, and role. Mismatch rejects and produces a bounded audit event.
9. The authenticated context and the already-bounded payload remain in one
   process, use immutable types/buffers, have no public/default/deserialization
   constructor, and are passed together. A serialized internal context is out of
   scope because it would create another authentication boundary.
10. Async ownership ties each message to the connection that supplied it.
    Connection IDs, buffers, and tasks cannot be reused across peers.
11. Manifest rotation, revocation, fingerprint removal, or generation replacement
    closes affected live connections at a defined atomic boundary. No message is
    accepted under a removed mapping after that boundary.
12. A complete bounded frame is required. EOF, timeout, truncation, excess bytes,
    trailing data, and incomplete close behavior never deliver a partial message.
13. No error, absence, optional value, empty string, anonymous actor, test mode,
    or log-derived value can produce an authenticated context.
14. Authentication does not grant a lease, widen a manifest, bypass session or
    stream generations, satisfy idempotency, or replace plant admission.

### Important limitation

An in-process capability type is a software construction, not a containment
boundary. Unsafe code, reflection, FFI, or ingress memory corruption could defeat
it. The prototype must inventory those paths and must not describe the result as
process isolation, least privilege, or a production trusted-computing base.

## Decision B: strict signed forwarding envelope

### Role and sequencing

B is a deferred forwarding-only alternative for deployments in which the original
operation signer cannot remain the transport peer. It is not accepted as a repair
for direct Zenoh and is not implemented ahead of A. The prototype is an outer
envelope only; it introduces no NCP wire field.

The only accepted serialization is flattened JWS JSON with exactly three outer
members: `protected`, `payload`, and `signature`. The verifier uses the received
encoded `protected` and `payload` strings directly when forming the RFC 7515
signing input. It never decodes and re-encodes them before signature verification.

Primary design sources:

- [RFC 7515](https://www.rfc-editor.org/rfc/rfc7515.html) defines the signing
  input, protected headers, flattened JSON serialization, critical parameters,
  base64url rules, and duplicate-header handling.
- [RFC 9864](https://www.rfc-editor.org/rfc/rfc9864.html) registers the fully
  specified `Ed25519` JOSE algorithm name; the polymorphic `EdDSA` name is not
  accepted by this profile.
- [RFC 8032](https://www.rfc-editor.org/rfc/rfc8032.html) specifies Ed25519 and
  supplies algorithm vectors.
- [RFC 8725](https://www.rfc-editor.org/rfc/rfc8725.html) requires algorithm
  verification, issuer/audience validation, explicit typing, and mutually
  exclusive validation rules for different token kinds.
- [RFC 8259](https://www.rfc-editor.org/rfc/rfc8259.html) explains JSON member,
  Unicode, and number interoperability hazards.

### Exact profile under test

The outer object has exactly:

- `protected`: canonical unpadded base64url of a strict UTF-8 JSON object;
- `payload`: canonical unpadded base64url of the immutable bounded NCP payload;
- `signature`: canonical unpadded base64url of exactly 64 Ed25519 signature bytes.

The protected object has exactly:

- `alg`: literal `Ed25519`;
- `typ`: a prototype-specific literal that cannot be confused with JWT or another
  JWS application profile;
- `crit`: exactly the one-element array `["ncp"]`;
- `ncp`: the exact context object below.

The protected `ncp` object binds:

- prototype profile/version and payload media type;
- one literal route, one closed plane, and one closed message class;
- one ASCII issuer and one ASCII receiver audience, never an audience array;
- stable-core digest, security-state digest, and exact key-manifest digest;
- `kid` as the content address of the exact public-key bytes and a positive key
  epoch selected from that manifest;
- issued-at and expiry bounds under an explicitly named clock policy;
- session ID and the exact canonical UUIDv4 session generation used by NCP;
- a separate forwarding epoch, positive safe-integer sequence, and positive
  recovery epoch for outer-envelope replay fencing;
- the exact payload stream epoch/sequence where the message class is streamed;
- the exact operation ID, request digest, and non-negative expected state version
  where the message class is idempotent; and
- SHA-256 of the decoded payload bytes.

The prototype does not rely on JSON canonicalization for signature validity. It
does require exact members and values after parsing. Literal routes do not use
Zenoh wildcard or key-expression equivalence.

### Parser and cryptographic invariants

1. The outer frame, protected bytes, payload bytes, strings, depth, nodes, members,
   and numeric tokens are bounded before semantic allocation.
2. Input is strict UTF-8 without BOM, overlong encodings, invalid code points, or
   unpaired surrogates. Object names are unique at every depth.
3. Integers use a closed decimal grammar, exclude negative zero, leading zeros,
   fractions, and exponents, and remain within the JavaScript safe-integer range.
4. Base64url excludes padding, whitespace, characters outside the alphabet, and
   noncanonical trailing bits. Decode/encode equality is checked.
5. Extra/missing members, unknown critical parameters, unprotected `header`,
   `signatures`, compact form, detached payload, compression, `none`, `EdDSA`,
   `jku`, `x5u`, `jwk`, `x5c`, and embedded key material reject.
6. The manifest, not attacker-controlled `alg`, selects the verifier. Header
   `alg` must exactly agree with the manifest's fixed Ed25519 entry.
7. Strict Ed25519 verification rejects wrong lengths, noncanonical scalar/point
   encodings, small-order inputs, and known cofactor-divergent cases.
8. Verification and consumption use the same immutable bytes and one manifest
   snapshot. No queue or file is re-read after verification.
9. Replay high-water check and commit are atomic and durable per signer, receiver,
   route, plane, class, session generation, forwarding epoch, key epoch, and
   recovery epoch.
10. Equal/lower sequences reject. Lost or corrupt replay state fails closed until
    an explicitly authenticated owner authorizes an epoch bump; the new recovery
    epoch is itself signed in every accepted forwarding envelope, so all
    pre-recovery envelopes reject. Initialization cannot overwrite an existing
    path, recovery must advance to a distinct store identity, and a cooperating
    active process prevents replacement through a shared/exclusive advisory lock.
    No in-band message may self-authorize recovery.
11. Manifest staleness, rollback, key removal, epoch mismatch, clock-policy
    failure, expired envelope, and wrong audience reject.
12. TypeScript and Python implementations use distinct JSON and Ed25519 stacks.
    If either rejects or their accepted semantic values differ, the decision is
    reject. This is implementation diversity, not independent-review evidence.

### Profile exclusivity and forwarding

Configuration pins one profile per endpoint, plane, and message class:

- **A-direct:** an authenticated transport operation principal; any B envelope is
  an ambiguity and rejects.
- **B-over-A forwarding:** A authenticates an authorized forwarder/carrier and B
  authenticates the distinct operation signer. The principal and entity identities
  must both differ. Both authentication axes are mandatory. The forwarder is
  allowed only the forwarding role for the exact route/plane/class; the signer is
  checked under its separate manifest role. Transport-only, signer-only,
  signer-as-forwarder, wrong audience, or any inner/outer profile mismatch rejects.
- No endpoint negotiates A-direct versus B-over-A from attacker-controlled input.

The B-over-A congruence rule checks the same literal route, plane, message class,
profile, receiver audience, stable-core digest, security-state digest, and manifest
generation across both decisions. Neither successful authentication can substitute
for a failure on the other axis.

## Hostile-test and falsification matrix

| Area | Hostile case | Required result |
| --- | --- | --- |
| Zenoh probe | sender chooses unstable source entity/sequence | Probe demonstrates sender control; source is never called authentication. |
| Zenoh probe | liveliness sample/reply | Source/replier information remains absent. |
| A handshake | no client certificate, untrusted issuer, expired/not-yet-valid leaf, wrong EKU | Handshake or admission fails; zero payload bytes reach core. |
| A protocol | TLS below 1.3, alternate protocol, ticket, resumption, 0-RTT, post-handshake auth | Unavailable or rejected. Any success is a no-go. |
| A mapping | unknown/duplicate fingerprint, wrong route/plane/class, invalid/stale manifest | Service does not produce a context. |
| A identity | valid certificate with false inner principal/entity/role | Reject and bounded alarm. |
| A concurrency | connection/buffer/task reuse and manifest rotation race | Every accepted context belongs to its originating connection and current snapshot. |
| A framing | oversize, timeout, truncation, trailing bytes, incomplete record | No partial delivery; bounded resources. |
| A construction | downstream/default/deserialization context construction | Structurally unavailable; compile/static negative test. |
| B syntax | duplicate/extra/missing members, alternate JWS form, unprotected or remote key | Both parsers reject. |
| B encoding | invalid UTF-8, BOM, surrogate, padded or noncanonical base64url | Both parsers reject before semantic use. |
| B numeric | fraction, exponent, leading zero, negative zero, unsafe integer, wrap boundary | Both parsers reject. |
| B cryptography | wrong algorithm/key/epoch, changed protected bytes or payload, RFC 8032 edge cases | Both verifiers reject. |
| B replay | exact replay, lower sequence, concurrent duplicate, state loss, initialization overwrite, active-process replacement, unauthorized epoch/store bump, schema or sidecar substitution | At most one atomic acceptance; state loss, schema drift, and unauthorized or unsafe recovery fail closed. |
| B routing | wrong audience, route, plane, class, profile, digest, generation | Reject. |
| Parser bounds | just-below, exact-limit, just-above, hostile width/depth/node/string sizes | Documented boundaries agree and remain bounded. |
| Differential | one parser accepts or produces a different semantic value | Global reject, alarm, and retained minimized case. |
| Cross-profile | B on A-direct, A-only or B-only on forwarding, signer principal/entity equals carrier | Reject without fallback. |
| Authority | valid TLS or JWS but no lease, session, idempotency, or plant admission | Ordinary NCP rejection remains unchanged. |

## Executed implementation-diversity result

The Python/PyNaCl reference and native TypeScript/Node verifier now execute
against a committed public-only thirty-one-case corpus in separate processes.
The Node implementation uses its own recursive-descent JSON parser and
Node/OpenSSL Ed25519 API; it shares no Python parser or FFI. Decisions,
rejection categories, and accepted authentication projections agree on every
retained case.

The result exposed a concrete native-crypto edge case. On Node 26.3.0 with
OpenSSL 3.6.2, an all-zero Ed25519 public key and signature verify for at least
the ASCII message `protected.payload`. The Node profile therefore rejects
noncanonical points, the seven reviewed small-order compressed representatives
on both sign encodings, and scalar `S >= L` before invoking native verification.
The regression retains the native acceptance and wrapper rejection. This does
not generalize to every input or runtime, and it does not replace future
cryptographic review.

The differential corpus retains no private key or seed. It covers both positive
NCP message profiles, the maximum safe forwarding integer, exact key overlap and
removal, duplicate/escaped names, UTF-8/BOM/base64url trailing bits, unsafe,
negative-zero, fractional and exponent number forms, non-ASCII route rejection,
algorithm/key/signature mutation, carrier/signer identity collision,
route/time/profile mismatch, and session/stream payload mismatch. Either
verifier rejecting is the combined global-reject result. The Node implementation
does not duplicate durable replay;
the Python reference commits every evaluated valid case to a fresh owner-pinned
store, while the separate replay suite remains the evidence for ordering,
recovery, and crash semantics.

This is implementation diversity, not independent human review or installed-peer
interoperability. Focused exact/above JSON byte, depth, node, member, string,
safe-integer and base64url bounds now execute in both language suites. Full-sized
profile-limit sweeps, combinatorial boundary fuzz, live A/B composition,
multi-host replay, filesystem rollback protection, trusted time/key custody,
duration fuzz, soak, performance and every external gate remain **NOT RUN**.

## Local gate decision

`B04` can reach `LOCAL_PASS` only if all of the following are retained and bound to
one exact pushed commit:

1. the exact pinned Zenoh source matrix and live negative probe;
2. executable A and B quarantined prototypes with no stable-source or package
   inclusion;
3. every hostile case above mapped to an executed test or explicitly `NOT RUN`;
4. zero acceptance of a negative vector;
5. deterministic positive vectors accepted by both B parsers with identical
   values, using distinct JSON and cryptographic stacks;
6. no public/default/deserializing A-context constructor and no serialized handoff;
7. resource measurements at all specified boundaries, clearly labelled as
   machine-local observations rather than performance certification;
8. exact environment/tool/dependency versions and content digests;
9. complete three-perspective and ten-lens reviews below;
10. the complete repository-local `scripts/check.sh` gate passing from the exact
    source commit, while all external gates remain `NOT RUN`.

No profile fallback, negative-vector acceptance, identity laundering, route/plane
confusion, non-atomic replay, stale-principal acceptance, unbounded hostile input,
stable-wire change, or weakened core authority guard is permitted; any occurrence
is an immediate no-go.

## Three-perspective review

### Protocol, security, and plant

The design preserves the foundational separation among authentication,
authorization, and actuation. A is preferred because it derives identity at the
boundary that performed certificate verification. B is restricted because a
signature authenticates a key holder, not the transport peer, route, current
lease, or plant-safe action. Both designs retain explicit route, plane, class,
generation, replay, manifest, and admission checks. Fail-closed availability loss
can still affect a plant, so the prototype must measure and report it without
calling a network rejection a physical safe state.

### Consumer and runtime

The profiles are statically selected, not negotiated per message. Consumers get an
unambiguous direct mode and a separate forwarding mode. The A context cannot be
serialized into an accidental bearer token. The B profile avoids language-specific
JSON canonicalization and requires parser agreement. These constraints increase
implementation cost and may reject otherwise valid generic JWS, but predictable
failure is the intended tradeoff for a control boundary.

### Operations, science, and evidence

Manifest distribution, trusted time, rotation coordination, replay persistence,
recovery authorization, private-key custody, process hardening, live Zenoh router
behavior, and plant effects remain open operational questions. Local benchmarks
are observations under one machine and toolchain. No posterior calibration, paper
reproduction, performance, scale, safety, interoperability, or release claim can
be inferred from B04.

## Ten-lens review checklist

1. **Wire and compatibility:** no stable field, hash, schema, vector, or package
   changes; outer prototypes are explicitly non-normative.
2. **Identity and authentication:** the authenticating boundary derives identity;
   payload and Zenoh entity IDs never authenticate themselves.
3. **Authorization and least privilege:** default deny, exact route/plane/class,
   distinct direct/signer/forwarder roles, and no signature-to-authority shortcut.
4. **Transport and topology:** direct Zenoh stays closed; A and B-over-A endpoints
   are distinct and cannot downgrade or negotiate profiles from input.
5. **Parsing and resources:** limits precede semantic allocation; duplicate,
   Unicode, integer, base64url, and member-set ambiguity reject.
6. **Concurrency, replay, and recovery:** connection ownership, manifest snapshot,
   atomic durable replay, restart behavior, and epoch recovery are explicit test
   subjects rather than implied properties.
7. **Key and configuration lifecycle:** exact key/certificate content addresses,
   provenance, freshness, rotation, revocation, staleness, and multi-instance
   atomicity remain fail-closed requirements and external operational gates.
8. **Plant and human safety:** network acceptance never certifies motion, safe
   action, watchdog behavior, or operator reset; Crebain/body-local authority is
   unchanged.
9. **Portability and consumer usability:** TypeScript and Python boundaries,
   JavaScript-safe integers, literal route bytes, and distinct crypto stacks expose
   cross-language disagreement before shipping.
10. **Evidence and release honesty:** exact commits, digests, commands, failures,
    machine context, and `NOT RUN` gates are retained; advice and local prototypes
    have no independent or release standing.

## External advisory input

An exact-model `claude-fable-5` maximum-effort request was deliberately narrow. Two
non-streaming attempts returned no bytes before their 120-second and 180-second
transport limits. One streamed attempt was incomplete at 300 seconds and was not
treated as a completed review. The terminal streamed response used model
`claude-fable-5`, stopped with `end_turn`, reported 1,189 input tokens and 10,133
output tokens including 7,492 thinking tokens, and had raw SSE SHA-256
`916d69b85350bca4479d294e9393e3bab5bb0affd14daaf5cd672dc58b1047f9` outside
the repository.

Its non-normative verdict was **ACCEPT for prototype-only** with five cautions that
this document adopts as falsification targets: ingress trusted-computing-base and
co-tenancy risk; rotation/revocation atomicity and manifest provenance; durable
replay recovery authority; exact A/B forwarding congruence; and correlated parser
or cryptographic dependencies. The response explicitly preserved direct Zenoh
fail-closed and all `NOT RUN` gates. This advice cannot count as a reviewer,
evidence source, proof, or gate result.

A seventh narrow exact-model challenge later returned model
`claude-fable-5`, terminal `end_turn`, and verdict `LOCAL_PASS` for only the
explicitly quarantined tested envelope. Its raw SSE SHA-256 was
`a5c58f4ad92076b502fd0c7c018e98058c20abc83432037a1bf6a15e74925797`
outside the repository. It prioritized exact boundary mechanics, both
small-order sign encodings, replay-key/order scrutiny, and evidence symmetry.
The focused boundary tests, full sign-bit coverage, and same-sequence
different-signed-payload replay negative were added. Existing before/after
commit crash tests and the signed replay scope already addressed its
under-specified replay concern. This advice remains non-normative and has no
reviewer or evidence standing.

## Exact next actions

1. Retain the Zenoh source/API matrix and build the live negative probe against
   exact `zenoh = 1.9.0`.
2. Build A as a quarantined loopback-only executable test boundary with ephemeral
   CA/server/client material, exact TLS and manifest checks, hostile connection
   cases, and a non-constructible in-process context.
3. **Completed locally:** build B with native Node/OpenSSL and Python/libsodium
   stacks, runtime-only private keys, and no committed private material.
4. **Completed locally:** retain exact dependencies, minimized hostile cases,
   a public-only differential corpus, and one full prototype runner.
5. **Completed for the prototype slice:** re-run the three perspectives and ten
   lenses against the executable results.
6. Retain the coherent prototype commit remotely, run the complete
   `scripts/check.sh` preflight from that exact source, and bind its outputs and
   hashes into the terminal B04 local receipt.
7. Do not begin B01 ADR ratification or normative implementation until that
   reviewed exact-commit receipt passes; external and independent gates remain
   **NOT RUN**.
