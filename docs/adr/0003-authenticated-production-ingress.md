# ADR-003 — Authenticate production ingress before interpretation

- Decision status: derived from the non-normative decision registry
- Task: `B01`
- Candidate: unreleased, release-blocked `1.0.0-rc.1`
- Normative effect before authorized N01 promotion: none
- Required reviewers: two independent security/cryptography reviewers,
  transport implementer

## Context

Pinned Zenoh `1.9.0` does not expose the verified certificate principal on each
stable application callback. Zenoh source IDs and payload `IdentityClaim` values
are sender-controlled metadata. Direct `production-secure` therefore correctly
fails closed.

B04 established local feasibility for a terminating TLS 1.3 ingress and for a
strict flattened-JWS forwarding envelope. It did not establish production
security, live rotation/revocation, key custody, containment, or external review.

## Proposed decision

Production input shall use one non-negotiable endpoint profile selected by trusted
configuration:

1. **A-direct:** a distinct terminating TLS 1.3 ingress derives the operation
   actor from the verified client leaf certificate and a content-addressed,
   default-deny manifest. The same process passes an unforgeable internal
   authenticated context with the same bounded payload bytes to NCP admission.
2. **B-over-A forwarding:** only where the original operation signer cannot
   remain the transport peer. A authenticates a carrier restricted to an exact
   forwarding grant; a strict flattened JWS authenticates a distinct operation
   signer. Both axes are mandatory and congruent.

Direct Zenoh `production-secure` remains unavailable until an exactly pinned API
exposes callback-visible verified principal evidence and passes fresh review.

Each configured production endpoint resolves exactly one ADR-001
`AuthorityRealmKey`, the canonical tuple of server authority principal and stable
realm ID. The key comes from the installed realm enrollment and endpoint
configuration, never from caller bytes. It excludes credential/security epochs,
replay-store incarnations, transaction-store incarnations, and every session
generation. An endpoint that cannot resolve one installed, non-retired realm
stays closed.

Every realm-scoped request, protected frame, authenticated internal context,
forwarding grant, replay record, admission fact, rejection receipt, and
successful handoff receipt carries
`authority_realm_key: AuthorityRealmKey` as a direct canonical member. The
canonical bytes and digest of each object include it. The inner NCP request also
carries the same direct member. A receiver cannot infer it from the endpoint,
route, audience, manifest, certificate, parent envelope, session generation, or
another receipt when it validates portable evidence.

The default-deny manifest is indexed by the exact realm key before actor and
capability selection. Its admitted tuple includes
`(AuthorityRealmKey, authenticated transport principal, operation signer when
applicable, profile, plane, literal route, message class, audience)`. A route
realm segment is only the canonical route projection of the stable realm ID. It
must match the direct key and the installed endpoint realm. It cannot supply the
server-authority-principal member or authorize a realm. Audience grants,
carrier-forwarding grants, key mappings, and routing rules are realm-scoped and
cannot use a wildcard, default, inherited, or cross-realm entry.

Replay and idempotency state is partitioned by `AuthorityRealmKey` before its
operation-specific key. Equal actor, session kind, logical session ID,
generation, operation ID, signature, and payload bytes in another realm are a
different attempted fact. They cannot be accepted as a retry, rejected as an
already-used local operation, or merged into one receipt lineage. Missing,
unknown, default, retired, or mismatched realm values reject before session
lookup, semantic allocation, replay mutation, callback, or side effect.

Every session-scoped ingress, replay, admission, and receipt projection uses the
exact consumer foreign key
`(AuthorityRealmKey, session_kind, logical_session_id, generation)`. Its direct
`authority_realm_key` is the tuple's first canonical member; the session
coordinates complete the tuple once. A route-only projection, a missing realm,
or a divergent compatibility copy rejects before consumer lookup.

B-over-A replay commitment and NCP handoff form one crash-safe operation. The
durable `ForwardingReplayKey` is the canonical tuple of `AuthorityRealmKey`,
authenticated operation-signer principal, and the stable signed operation/replay
identity from the protected context. It excludes the carrier, envelope digest,
inner NCP idempotency context and payload bytes. The entry selected by that key
binds the authenticated carrier and forwarding grant, protected-envelope digest,
inner NCP idempotency context, and exact payload bytes. Thus a changed carrier,
grant, digest, idempotency context or byte sequence selects the same entry and
conflicts; it cannot evade replay detection by selecting a new content-derived
key. Its closed state is
`RESERVED_PENDING_NCP_HANDOFF | FORWARDED_TERMINAL |
REJECTED_TERMINAL`. The first transition atomically burns the replay key and
installs one immutable, bounded `ForwardingNcpHandoffOutboxItem` containing the
same authenticated context and exact bytes. A replay reservation without that
recoverable item cannot commit.

Only a queryable NCP handoff result can terminalize the entry.
`FORWARDED_TERMINAL` binds an authenticated NCP-admission-boundary receipt over
the exact realm, outbox item, bytes, signer, and inner idempotency context. It
proves handoff only, not operation success. `REJECTED_TERMINAL` binds definitive
authenticated evidence that the same handoff created or reserved no application,
session, authority or plant mutation beyond the retained same-key terminal
rejection result itself. Timeout, cancellation, process crash, missing reply, or
uncertain NCP state selects neither terminal branch. The entry remains
`RESERVED_PENDING_NCP_HANDOFF` and the worker queries or resumes the same
idempotency context with the same bytes.

After bounds, carrier, signer, realm, and signature verification, an exact retry
queries this entry before semantic work can create a second operation. It returns
the retained terminal receipt or resumes the one outbox item. A changed carrier,
grant, byte, actor, route, audience, or idempotency context under the same stable
replay key is a conflict. A realm or signer change selects a distinct key and
cannot reuse the prior entry as retry evidence. Replay-store loss, rollback, an
unrecoverable outbox, or an NCP boundary without durable same-key query/resume
keeps B-over-A mutation forwarding closed. A crash after replay commitment can
therefore cause delay or denial, but
it cannot make the retry opaque, discard the request, or duplicate the NCP
mutation.

The NCP boundary retains the same-key idempotency result for at least as long as
the forwarding entry can remain pending, including its maximum recovery window.
The forwarding store cannot evict a pending entry or its immutable outbox item
before it has installed and retained one terminal receipt. If either retention
relationship cannot be proved after restart, the forwarding profile remains
closed.

The only unauthenticated development profile is `dev-loopback-insecure`. Trusted
configuration can bind it only to an IP loopback address or an absolute
Unix-domain socket path. It rejects wildcard, unspecified, non-loopback, relative
socket, and production-profile endpoints. Every API, startup diagnostic, status,
and session transcript exposes an unmistakable insecure state. The profile never
negotiates or downgrades from `production-secure`.

The development profile still binds one configured direct `AuthorityRealmKey` to
every realm-scoped frame and local receipt. That label does not authenticate an
actor or upgrade development evidence, but it prevents local stores from merging
two realms.

The signed profile accepts exactly the fully specified JOSE algorithm
`Ed25519` registered by RFC 9864, never deprecated polymorphic `EdDSA`, `none`,
remote key URLs, embedded keys, unprotected headers, compact/general
serialization, detached payloads, or caller-selected algorithms. Protected
context binds exact route, plane, message class, profile, issuer, audience,
stable-core digest, security-state digest, key manifest and epoch, validity
interval, session generation, payload digest, and applicable stream or operation
replay context. It also binds the direct `AuthorityRealmKey`; all referenced
realm-scoped inner context carries an exactly equal key.

Authentication precedes semantic interpretation and never grants a session,
lease, lifecycle transition, operation outcome, disposition, or plant action.

## Low-overhead ingress reconciliation

A-direct does not require a separate process. When transport termination and
NCP admission share one trust process, the transport mints one receiver-owned
opaque capability. Caller bytes cannot construct, serialize, alter, split, or
recombine that capability.

When transport termination is in another process, the deployment must use an
authenticated operating-system-protected handoff. The handoff must preserve the
same exact context. Otherwise, the deployment must use B-over-A. A copied
principal, certificate subject, route, or context digest is not a capability.

A-direct is the proposed hot-data path. It authenticates the connection once and
prepares one immutable context for each permitted route and frame class. A hot
frame does not repeat application signatures, realm strings, key identifiers,
security epochs, or manifest scans that this context already fixes.

B-over-A remains an explicit low-rate forwarding path. Each mutating operation
installs one immutable durable outbox item before any external send. The outbox
binds the signer, exact protected bytes, target, route, audience, realm, session,
operation class, security state, and idempotency key.

Each send attempt uses one short owner transition. The owner rechecks security,
revocation, target permission, and the operation deadline, then marks that exact
attempt active before network work starts. Network work runs outside the owner
lock. Timeout, cancellation, crash, or an unknown target result keeps the same
attempt unresolved. It cannot create a fresh item or operation identity.
Recovery queries the same item. An exact resend is permitted only when the
installed target profile binds the same protected bytes and idempotency key to
retained no-reuse state. Otherwise, authenticated non-acceptance is required
before another send.

The transport profile validates its native certificate, URI, or operating-system
identity once and maps it to one canonical NCP principal. It never applies an
NCP route-segment grammar to the native transport identity.

The verified native identity projection is 1 through 1,024 UTF-8 bytes under its
transport-specific canonicalization rule. The transport rejects an oversized,
ambiguous, noncanonical, or unmapped projection before it mints the capability.
Credential rotation can map several exact current credentials to one principal,
but caller bytes cannot request that mapping.

Named proof objects in this ADR describe observable bindings. A local
implementation can combine them into one bounded record and transition. It must
preserve the failure order, no-reuse behavior, and recovery result.

## Rejected alternatives

- Trust payload identity, Zenoh source ID, connection topology, certificate common
  name, or router ACL inference at the application boundary.
- Enable production mode with a warning when actor binding is unavailable.
- Negotiate A-direct versus B-over-A from the received message.
- Let a carrier and signer share principal/entity identity.
- Invent custom signature framing instead of a strict reviewed JWS profile.
- Count B04's local prototypes as production evidence.
- Mark a replay key consumed before durably retaining exact bytes and a queryable
  inner idempotency context.
- Treat timeout, task cancellation, or crash after replay commit as definitive
  NCP rejection and accept a fresh mutation.

## Illustrative wire wrapper

The inner payload remains a generic NCP message. Proposed forwarding syntax:

```json
{
  "protected": "ZXhhY3QtYmFzZTY0dXJsLXByb3RlY3RlZA",
  "payload": "ZXhhY3QtYmFzZTY0dXJsLW5jcC1wYXlsb2Fk",
  "signature": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
}
```

The strings above are illustrative only and do not form a valid signature.

The decoded protected header, before base64url encoding, has this shape in
addition to its exact registered fields:

```json
{
  "alg": "Ed25519",
  "authority_realm_key": {
    "server_authority_principal_id": "ncp-authority-a",
    "stable_realm_id": "realm-a"
  },
  "route": "realm-a/session/plant-alpha/command/controller-a",
  "audience": "plant-body-a"
}
```

## Invalid or hostile example

```json
{
  "protected": "eyJhbGciOiJFZERTQSJ9",
  "payload": "e30",
  "signature": "",
  "header": {
    "jku": "https://attacker.invalid/keyset.json"
  }
}
```

This rejects before payload interpretation. It uses a forbidden algorithm label
and omits the direct `AuthorityRealmKey`.

## Actors and state transitions

A-direct:

`LISTENING -> TLS_VERIFIED -> REALM_RESOLVED -> MANIFEST_BOUND ->
FRAME_BOUNDED -> AUTHENTICATED_CONTEXT -> REALM_CONGRUENCE_CHECKED ->
NCP_ADMISSION`.

B-over-A adds:

`CARRIER_VERIFIED -> SIGNED_FRAME_BOUNDED -> SIGNER_MANIFEST_BOUND ->
SIGNATURE_VERIFIED -> REALM_CONGRUENCE_CHECKED ->
FORWARDING_REPLAY_KEY_LOOKUP`.

An absent stable key follows
`CONTENT_COMMITMENT_VALIDATED -> RESERVED_PENDING_NCP_HANDOFF ->
NCP_HANDOFF_QUERY/RESUME -> FORWARDED_TERMINAL/REJECTED_TERMINAL`. An exact
existing entry goes directly from lookup to its retained terminal result or the
same pending query/resume path. An existing key whose committed carrier, grant,
envelope, bytes, route, audience or inner idempotency context differs follows
`CONFLICT_REJECTED_NO_HANDOFF` and cannot alter that entry.

Any pre-reservation failure transitions to `REJECTED` with no authenticated
context. Rotation or revocation atomically retires affected mappings and
connections. A realm change
requires a different endpoint/domain lineage; it is not key rotation or a live
context rebind. After `RESERVED_PENDING_NCP_HANDOFF`, an uncertain handoff is
not a fresh `REJECTED` transition; it remains the recoverable pending state.

## Bounds and resource behavior

TLS versions, frame bytes, JSON nodes/depth/members, protected bytes, payload
bytes, strings, integers, base64url, manifest entries, keys, replay scopes,
pending handoff entries, immutable outbox bytes, terminal receipts, queues,
diagnostics, verification time, retry/query work, and recovery work are finite.
Capacity for the replay entry and exact outbox item is reserved before the
replay transition commits. Bounds are checked before expensive parsing,
signature verification, allocation, logging, or side effects.

Subject to B01 independent review and later B02/N01 implementation and
rebaseline, the proposed semantic collection rule uses a trusted message class
and decoded path, not an untrusted payload discriminator or a field-name
spelling. The declared `max_metadata_entries=256` ceiling would apply
independently to each `OpenSession.bindings[*].entity.meta` object. The proposed
path contains an explicit typed array-item step. JSON ingress would enforce the
rule during duplicate-aware structural preflight, before generic tree or typed
allocation; typed and protobuf entry points would enforce the same
immediate-member count before semantic use. The trusted route or API type would
select the expected message class. For an authenticated outer envelope, generic
bounds would apply to that envelope and the authenticated context would select
the class used to stream-decode its exact inner bytes.

Under the proposal, decoded RFC 6901 member identity, not member order or raw
spelling, would select the registered map. Duplicate-key rejection would take
precedence. A new distinct 257th member would reject with `NCP-LIMIT-003` before
the key or its value is retained or the value is parsed. A non-object at the
proposed path would later reject with the ordinary wire-shape decision. An
additive `meta` or `metadata` member at any unregistered path would receive only
the generic bounds and normal unknown-field handling. No accepted class/path
assignment exists yet. Rust and TypeScript do not implement the proposed rule,
and the Python developer reader currently applies a post-parse recursive name
heuristic. Those are candidate gaps, not accepted alternate semantics.

## Threat and hazard analysis

The design addresses self-authentication, algorithm confusion, route/audience
substitution, carrier identity laundering, replay, stale keys, manifest rollback,
and partial-frame delivery. The ingress and key store remain trusted computing
base components. Memory corruption, host compromise, CA/key custody, trusted
time, multi-host replay consensus, and plant consequences of denial remain
external risks.

Direct realm binding prevents a valid request or forwarding receipt from one
realm from being replayed through an endpoint whose principal, textual session,
generation, and bytes otherwise match. It also prevents route-only authority and
consumer projections that accidentally discard the server authority principal.
An implementation must test the stronger collision case where every field and
byte except `AuthorityRealmKey` is equal.

The crash-safe handoff prevents a second failure mode: a replay store can
correctly reject duplicates while losing whether the first request reached NCP.
Without exact retained bytes and inner idempotency query, the system must either
drop a legitimate retry forever or risk a duplicate mutation. The pending state
preserves that uncertainty without granting success.

## Formal properties

- No payload field can construct an authenticated actor.
- Every admitted production message has exactly one configured profile.
- Every admitted realm-scoped request has one direct `AuthorityRealmKey` equal
  across endpoint enrollment, authenticated context, default-deny manifest,
  protected header, inner request, route projection, audience, replay state, and
  admission receipt.
- Missing, default, wildcard, retired, or mismatched realm data produces no
  replay commit, callback, session lookup, or semantic side effect.
- A manifest, audience, carrier grant, route rule, replay key, or evidence
  projection that drops `AuthorityRealmKey` is invalid.
- Every session-scoped ingress, replay, admission, or receipt projection uses
  `(AuthorityRealmKey, session_kind, logical_session_id, generation)` as its
  exact consumer foreign key.
- Same-principal, same-session, same-generation, same-operation, same-byte
  attempts under different realm keys never deduplicate or share admission
  state.
- An exact protected-byte replay at another authenticated endpoint realm rejects.
  A separately valid frame with all non-realm fields equal but either
  `AuthorityRealmKey` coordinate changed uses a distinct replay lineage. The
  corpus mutates the server authority principal and stable realm ID independently.
- `dev-loopback-insecure` binds only loopback IP or an absolute Unix-domain
  socket, remains visibly insecure, and cannot result from production downgrade.
- B-over-A admission implies distinct authorized carrier and signer identities.
- Route, plane, class, audience, and digests agree across transport, wrapper,
  manifest, and inner message.
- B-over-A replay reservation atomically installs one immutable exact-byte
  handoff outbox item and the same realm-bound inner NCP idempotency context.
- A crash or reply loss after replay reservation leaves exactly one queryable
  `RESERVED_PENDING_NCP_HANDOFF` entry. Exact retry returns or resumes it and
  cannot create another NCP mutation.
- The NCP same-key query result outlives every permitted pending-handoff recovery
  window, and the forwarding store retains the pending entry and exact outbox
  item until a terminal receipt is durable. Eviction cannot turn uncertainty
  into a fresh request.
- `FORWARDED_TERMINAL` requires an exact NCP-boundary handoff receipt.
  `REJECTED_TERMINAL` requires definitive no-mutation evidence. Ambiguity cannot
  select either branch.
- The stable `ForwardingReplayKey` is independent of carrier and content. The
  selected entry commits the exact carrier, forwarding grant, envelope, bytes,
  route, audience and inner idempotency context. Changing any committed member
  under that key is a conflict and creates no handoff.
- Authentication success alone cannot satisfy an authority predicate.

## Migration

No current shipping adapter changes in B01. N04 implements the accepted envelope
and N06 integrates it while preserving direct-Zenoh fail-closed behavior. All
bindings receive the same public corpus. That corpus includes cross-realm replay,
route/direct-key disagreement, realm-dropping projection, and manifest/audience
realm-substitution mutants. It also crashes before and after replay reservation,
outbox persistence, NCP boundary acceptance, terminal receipt installation, and
reply delivery. Changed-byte retry, duplicate worker, cross-realm pending-entry
substitution, false terminal rejection, and a handoff receipt with the wrong
inner idempotency context must reject. Live profiles remain unavailable until
external security gates pass.

## Operational recovery

Manifest ambiguity, state loss, rollback, key removal, clock uncertainty, or
replay-store corruption stops admission. Recovery is an authenticated
out-of-band owner operation with a distinct recovery epoch/store identity; an
in-band message cannot self-authorize it. A healthy restart drains or queries
the exact pending realm-bound handoff entry before accepting a conflicting
operation. It never reconstructs changed bytes or marks ambiguity terminal.

## Compatibility and rollback

Endpoints pin one exact profile; no fallback exists. Rollback restores the prior
disabled production path or a complete reviewed ingress release, never an
unauthenticated compatibility mode.

## Open questions

<a id="ncp-b01-selector-allocation-adr-003-v1"></a>

The process-isolation question is closed by the low-overhead ingress
reconciliation. The same-process direct endpoint uses an opaque receiver-owned
capability. Separate-process termination uses an authenticated protected
handoff or signed forwarding. Isolation can strengthen containment but cannot
weaken any binding.

Future B03 allocation names and reviewed exclusions will be maintained in the
[external selector-allocation inventory](selector-allocation.authoring.v1.json)
under this stable ADR anchor. The current inventory is incomplete, has not been
reviewed, and contains no allocation or exclusion rows. It is coordination
evidence only and grants no release or gate status.

## Ten-lens review

1. Semantics: profile and authenticated actor meanings are exact.
2. Security: verification precedes interpretation; downgrade is unavailable.
3. Safety: ingress grants no lease or plant success.
4. Lifecycle: rotation, revocation, restart, and replay recovery fail closed.
5. Resources: every encoding and verification layer is bounded.
6. Migration: all languages share exact vectors; direct Zenoh stays disabled.
7. Science: signatures authenticate provenance but do not validate claims.
8. Operations: configuration, alarms, key rotation, and recovery are explicit.
9. Evidence: independent crypto review and live rotation/revocation remain gates.
10. Governance: manifest, keys, ingress, incidents, and deprecation have owners.

## Ratification record

The non-normative decision registry records exact review evidence and derives the
current decision status. This invariant text does not change when review state
changes. B04 is local feasibility evidence only.
