# Neuro-Cybernetic Protocol 1.0 candidate

This document is the normative prose for the **unreleased, release-blocked**
`1.0.0-rc.1` candidate. The wire string is `1.0`; the compact protobuf-structure
hash is `163acc57d8a62b66`. It is incompatible with wire 0.8.

The key words **MUST**, **MUST NOT**, **REQUIRED**, **SHOULD**, **SHOULD NOT**, and
**MAY** are to be interpreted as in RFC 2119 and RFC 8174 when capitalized.

## Normative set and precedence

The machine-readable registries under [`contract/`](contract/) take precedence,
excluding the derived [`contract/manifest.v1.json`](contract/manifest.v1.json),
which cannot hash itself. They are followed by
[`proto/ncp.proto`](proto/ncp.proto), the JSON Schemas under [`schemas/`](schemas/),
this document, and the mandatory corpus described by
[`conformance/manifest.v1.json`](conformance/manifest.v1.json). A conflict is a
release-blocking defect; a peer MUST fail closed rather than choose the permissive
interpretation. The derived contract manifest enumerates and binds those exact
normative source bytes to one reproducible SHA-256 digest.

Only items explicitly listed `stable-1.0` in
[`contract/surface.v1.json`](contract/surface.v1.json) are stable. Canonical JSON is
the stable runtime encoding and Zenoh is the stable transport binding. Protobuf is
the field-number and shape IDL, not a stable runtime encoding.

## Normative terminology

The following terms are distinct and MUST NOT be used interchangeably:

- A **realm** is the validated exact deployment key-expression prefix that names
  one NCP routing domain. Knowing a realm proves no identity or authority.
- A **session** is one logical controller/body lifecycle named by `session_id`.
  The name may recur after restart; it is not sufficient to identify live state.
- A **generation** is the opaque, server-issued canonical lowercase UUIDv4 in
  `SessionRef` returned by one successful `SessionOpened`. It identifies one
  incarnation of a session and fences every later mutation, data frame, lease,
  receipt, and replay decision. Closing, reopening, or recovering a session never
  revives a retired generation.
- A **stream epoch** is the unguessable UUIDv4 in `stream.epoch` owned by one
  concrete publisher stream declaration. It scopes that stream's positive
  sequence numbers. A stream epoch is not a session generation and MUST NOT
  survive publisher redeclaration or restart. The legacy-named `session_epoch`
  members of `AuthorityLease` and `OperationContext` are not stream epochs: they
  carry the exact live `SessionRef.generation` and MUST equal it.
- A **stream** is the ordered sequence emitted by one authenticated publisher for
  one concrete route, message kind, plane, and live session generation under one
  stream epoch. A receiver applies replay/high-water policy to that complete
  identity.
- A **plane** is one of the closed transport-policy classes `control`,
  `perception`, `action`, or `observation`; it fixes publisher roles, message
  purpose, and QoS policy but is not itself a route or credential.
- A **route** is one concrete key produced by the grammar below. Wildcard
  selectors describe subscription coverage, not a publisher route, and MUST NOT
  broaden action authority.

Payload identity, the route, and the plane remain claims until bound to the
verified transport principal and the live generation. No default, omitted value,
or name equality supplies that binding.

## Wire version compatibility

Peers MUST reject a missing or malformed `ncp_version`, and any version whose major
component is not `1`. Each component is a canonical ASCII-decimal unsigned 64-bit
integer: zero is exactly `0`, nonzero values have no leading zero, and signs,
whitespace, suffixes, a patch component, Unicode digits, and values above
`18446744073709551615` are malformed. `1` is the canonical shorthand for `1.0`;
later 1.x minor versions are additive-compatible under the stable-line policy. No
0.8 field default, coercion, or transparent proxy behavior is permitted on a native
1.x session. The 16-hex `CONTRACT_HASH` is an advisory same-major diagnostic: a peer
reports a mismatch but the hard compatibility decision remains the wire version.
The complete normative contract digest is the release/conformance identity.

Unknown JSON fields MAY be retained or ignored only after the entire envelope has
passed the universal resource budget. Unknown closed security, plane, principal,
lifecycle, operation-outcome, and channel-requirement values MUST NOT authorize an
operation. Unknown capabilities MUST fail negotiation.

## Roles, planes, and keys

NCP distinguishes handshake roles (`controller`, `plant`, `observer`, `operator`)
from enrolled principal roles (`commander`, `body`, `observer`, `operator`). The
mapping is controller→commander, plant→body, observer→observer, and
operator→operator.

The four planes and publishers are fixed by
[`contract/planes.v1.json`](contract/planes.v1.json): control is commander/body,
perception is body, action is commander/operator, and observation is body. The key
grammar is:

```text
{realm}/rpc/{request_kind}
{realm}/session/{session_id}/sensor[/{channel}]
{realm}/session/{session_id}/command[/{channel}]
{realm}/session/{session_id}/observation
```

Realm, session, channel, principal, and entity segments MUST be bounded canonical
segments accepted by the key grammar. Wildcard action publishers are forbidden.

## Universal bounded JSON

Every ingress path MUST apply [`contract/limits.v1.json`](contract/limits.v1.json)
before semantic decoding. The limit covers encoded bytes, nesting, objects, arrays,
members, items, keys, strings, cumulative string bytes, channels, metadata, numeric
magnitude, and the IEEE-754 safe-integer range. Duplicate keys, invalid Unicode,
non-finite numbers, fractional integer fields, and malformed JSON are rejected with
the registered `NCP-LIMIT-*` outcome. A binding MUST NOT first allocate an
unbounded generic value and check the budget afterward.

## Identity and security profile

`IdentityClaim` contains `principal_id`, `entity_id`, closed `role`, and closed
`plane`. The claim is not a credential. A transport adapter MUST obtain the verified
cryptographic peer identity and bind it, through a default-deny authority manifest,
to exactly that claim before any state change or plane delivery. A certificate valid
for one entity or plane grants no authority for another.

Exactly two baseline profiles exist:

- `dev-loopback-insecure` is limited to loopback TCP or an absolute Unix-domain
  socket and MUST emit an unmistakable insecure status. It is not a production
  profile.
- `production-secure` requires mutual TLS, verified peer identity, certificate
  validity checks, protected private-key material, default-deny principal/entity/
  plane ACLs, and no downgrade.

Negotiation carries the profile ID and a lowercase 64-hex SHA-256
`security_state_digest`. Both sides MUST use the precommitted profile and digest;
partial or mismatched security configuration fails before session mutation. The
digest is the domain-separated typed semantic projection defined by
[`contract/security-state-digest.v1.json`](contract/security-state-digest.v1.json)
and [`contract/canonical-digest.v1.json`](contract/canonical-digest.v1.json): it
normalizes principal and plane order, materializes the two optional authority-flag
defaults, and covers every effective deployment member including certificate/key
paths (never key bytes). Unknown deployment members are rejected rather than left
unbound. The independent Python configuration validator replays the same golden
digests, but live certificate, rotation, revocation, and ACL certification is a
separate release gate.

## Capability negotiation

`Capabilities` binds `controller_id` to `identity.entity_id`, the handshake role to
the principal role, and the claim to the control plane. It MUST advertise each core
stable capability exactly once:

```text
ncp.core.canonical-json.v1
ncp.core.lifecycle.v1
ncp.core.authority-lease.v1
ncp.core.idempotent-mutation.v1
ncp.core.plant-profile.v1
```

`ncp.transport.zenoh.v1` is the only additional stable capability in the candidate.
Unknown, duplicate, excluded, or experimental-as-stable capability identifiers fail
negotiation.

Every `ChannelSpec` uses a closed `requirement` value: `required` or `optional`.
`unknown`, absence, and legacy `optional` ambiguity do not authorize a native 1.0
session. Names are unique within their list; kind, unit, size/arity, and requirement
MUST agree at both ends. A required channel cannot disappear through fallback.

## Lifecycle and errors

The lifecycle state model is closed/opening/init/active/hold/estop/closing/
reconnecting/failed. The legal transitions and operator override rules are enforced
by the authority state machine; unknown states never authorize action.

`OpenSession` carries the authenticated control-plane identity, chosen security
profile/digest, gateway policy, network/record/stimulus/simulation request, and the
advisory compact hash. A successful `SessionOpened` MUST return a new session
generation, matching responder identity and security state, resolved configuration,
honest simulation provenance, and the authoritative `state_version` that the first
mutation MUST use as `expected_state_version`. A failed open MUST NOT return a live
generation; its state version is non-authorizing diagnostic state only.

All errors carry `kind=error`, `ncp_version=1.0`, and a required exact `code` from
[`contract/errors.v1.json`](contract/errors.v1.json). A missing or unregistered
code is an invalid message; free-form `error` text is diagnostic and MUST NOT be
used as the failure classification. Generic RPC decoding, shape, version, and
correlation failures use `NCP-WIRE-001`; contained handler, bridge, overload, or
other implementation failures use `NCP-INTERNAL-001`. More specific registered
codes take precedence when their condition is known. `session_id` and `session`
MUST be both present or both absent. An error MUST NOT guess a session generation;
when a validated session-scoped request is being answered, the error retains the
request's exact pair. Pre-authentication and shape failures have no receipt, while a
committed rejection or cancellation may retain its authenticated terminal receipt.
No error, including one with a registered code, is an authorizing success.

## Session generations and stream epochs

A successful open creates a server-issued canonical lowercase UUIDv4
`session.generation`. Every subsequent session-scoped envelope, nested stimulus,
operation context, authority lease, and receipt correlation MUST refer to that same
incarnation. A stale generation is unusable evidence and MUST be rejected before
side effects. Reconnect does not silently create or adopt another generation.

Data and periodically published status streams additionally carry their own
canonical UUIDv4 `stream.epoch` and a strictly positive, monotonically increasing
JSON-safe `stream.seq`; zero is always unstamped. One receiver declaration binds
one stream epoch and high-water mark. Expiry, HOLD, or silence does not authorize a
lower sequence or foreign stream epoch; restart requires fresh authenticated
route/session declaration state. Source correlation uses a typed `source` stream
position; arrival order is not correlation.

## Authority leases

Lifecycle mutation and active action require an `AuthorityLease` bound to one live
session generation through its legacy-named `session_epoch` member, plus a strictly
positive term, canonical lease UUID, issuer principal, holder principal/entity, and
integer UTC issue/expiry times. The declared interval MUST be positive and no more
than 60 seconds. A receiver converts the accepted remaining duration to a local
monotonic deadline; UTC is retained for receipt/audit, not used as a continuously
trusted control clock.

Only an enrolled commander may hold controller authority. Initial self-acquisition,
holder transfer, and an explicitly enrolled operator override are distinct paths.
Terms only increase across acquisition/preemption; a stale term, different session
generation, wrong holder, expired lease, conflict, or clock-uncertainty violation
fails closed.
Expiry or loss of the holder transitions out of active authority. ESTOP remains
latched across disconnect/reconnect and cannot be cleared by reacquisition.

A renewal is not possession of a serialized lease. The receiver MUST authenticate
both the issuer and current holder, require their IDs and the immutable lease
identity to match the active record, require the issuer to be an enrolled commander
or an operator with explicit override authority, and require the current local
monotonic deadline to remain strictly unexpired. Renewal after expiry is rejected
and transitions to HOLD; recovery requires a newer acquisition. A retired session
generation cannot be opened, acquired, renewed, or reconnected.

## Idempotent lifecycle RPCs

`StepRequest`, `RunRequest`, and `CloseSession` are mutations and MUST carry both an
`OperationContext` and matching authority lease. The operation context includes a
canonical operation UUID, SHA-256 request digest, the legacy-named `session_epoch`
member containing the live session generation, expected state version, absolute
deadline, and explicit retry bit. It is not a stream epoch.

The digest is exactly `contract/request-digest.v1.json`: SHA-256 over the
domain-separated typed, length-prefixed semantic projection. Object order and JSON
number spelling do not affect it. The projection covers the full request, including
unknown extension members, except the renewable top-level `authority` envelope and
the attempt-local `operation.request_digest` and `operation.retry` members. A lease
may therefore be renewed and `retry` may change from false to true without changing
mutation identity; changing the operation ID, session generation, state
expectation, deadline, session, version, payload, or any other covered member
changes the digest. Every ingress MUST recompute and compare it after bounded JSON
and structural validation.
Digest equality never grants authority: before idempotency lookup, the server MUST
derive the caller from the authenticated transport, require that caller to be the
lease holder, and require the supplied lease to equal the `AuthorityMachine`'s
currently active unexpired lease. The cache key includes that authenticated
principal. An authority transfer therefore produces a distinct key and an
`outcome_unknown` retry result, never another principal's terminal replay; an
expired, stale, weaker, mismatched-holder, or payload-only lease is rejected before
the cache can reveal or replay a result.

The idempotency key binds authenticated caller principal, session ID, session
generation (carried in `session_epoch`), and operation ID. Reusing an ID with
different content is rejected. A retry may replay only an authenticated terminal
`ResponderReceipt`; in-progress work returns the registered busy outcome. If
restart, expiry, or eviction prevents the server from proving the result, it
returns `outcome_unknown` and MUST NOT execute the mutation again by assumption.

A terminal receipt binds operation ID, request and result SHA-256 digests, closed
outcome, state version, commit time, and authenticated responder principal/entity.
`SessionClosed` always carries it. An `ObservationFrame` returned as a step/run RPC
result carries it; a passive observation-plane publication may omit it. A client
MUST correlate a receipt before treating an RPC as committed and MUST obtain the
next expected state version from that receipt. A lost, absent, or uncorrelated reply
leaves the outcome and next state explicitly unknown; a client cannot increment or
guess either locally.

## Data-plane envelope

`SensorFrame`, `CommandFrame`, `LinkStatus`, and `ControlStatus` carry the wire
version, kind, session ID/generation, and stream position. The transport binds the
authenticated actor and actual plane before delivery; data frames do not
self-authenticate by adding a payload claim. Named channel data is finite and
bounded by the negotiated specification and plant profile.

`ControlStatus.stream` and `LinkStatus.stream` start at sequence 1 and never reuse a
position; an exhausted publisher becomes silent until a fresh declaration mints a
new stream epoch. `LinkStatus.observed_stream` and `last_arrival_seq` are present
together or absent together. When present, both are positive, and the last arrival
cannot exceed the observed forward high-water.

Before publication, callback delivery, safety-latch mutation, or any other state
change, the payload `session_id` MUST exactly equal the session encoded by the actual
transport route and the payload `session.generation` MUST exactly equal the current
server-issued generation retained from `SessionOpened`. This conjunctive binding
applies on perception, action, and observation paths, including named channels.
Neither a canonical but stale generation nor a payload claim can rebind a route.

Every remotely received ESTOP MUST carry the complete compatible `CommandFrame`
envelope: kind, version, its publisher's stream position, session ID, and live
generation. After authenticated actor/plane and exact route/session admission, ESTOP
MAY omit the authority lease; that is its only envelope exemption. A typed local
governor may construct or normalize an ESTOP before serialization using its immutable
live session binding, but an inbound network message is never repaired or assigned a
generation. Rejecting a malformed, stale, or misrouted ESTOP preserves session
isolation; it is not evidence that the intended plant received a stop, executed its
safe action, or physically stopped.

An active `CommandFrame` additionally carries a valid matching authority lease. A
missing, stale, expired, wrong-entity, or wrong-session lease forbids active output.
HOLD and ESTOP are fail-safe protocol modes, not credentials and not proof of
physical safety.

## Observation plane

`ObservationFrame` is published by the body/server and consumed read-only. It binds
the session generation and its own observation stream position. Record arrays have
matching lengths and finite values. When a record identifies a source, that source
is typed and generation-safe rather than inferred from arrival order.

Passive observation cannot mutate lifecycle or authority. An RPC-result observation
is distinguished by its responder receipt and MUST be verified as described above.
Bare binary `NCPB` is never a valid observation envelope.

## Scientific boundary

Every successful simulation session and every observation MUST represent raw output
of the specified model with `calibrated_posterior=false` and
`is_simulation_output=true`. Advisory and gateway data cannot upgrade those flags.
NCP output is not a validated paper reproduction, posterior sample, experimental
recording, or proof that model equations/parameters match a publication.

## Plant profile

A plant role MUST negotiate a lowercase 64-hex content digest for a validated
`ncp.plant-profile.v1`. The profile binds plant/body identity, revision, class,
sorted command channels, units, arities, numeric ranges, actuator semantics, HOLD
action, ESTOP action, and the plant-local executor. Unknown or mismatched digests
forbid active action. The closed schema, typed binary64-preserving projection, exact
domain, byte/depth budgets, and digest exclusion of only the root
`profile_digest_sha256` member are normative in
[`contract/plant-profile.v1.json`](contract/plant-profile.v1.json) and
[`contract/canonical-digest.v1.json`](contract/canonical-digest.v1.json).

The profile MUST state that the body is final actuator authority, protocol ESTOP is
not physical certification, and a consumer safety case is required. `hold_last` is
allowed only for a positive bounded duration and cannot be assumed safe by the
protocol. Neutral or shutdown actions define every command channel explicitly.

## Plant safety governor

Before actuation, the body validates the content-addressed plant profile, session and
authority, negotiated channel names/units/arities, finite values, ranges, freshness,
TTL, predictive horizon, and configured geofence/speed limits. The reference
governor deterministically clamps speed, truncates a horizon before a predicted
boundary crossing, enters non-latching HOLD for stale/missing data or invalid time,
and latches ESTOP on a boundary breach or explicit ESTOP.

A missing safe action, malformed position, non-finite value, undeclared channel, or
profile mismatch is not interpreted as zero-risk. The body executes its declared
local safe action and reports failure when that action cannot be proven.

## Action buffer and ESTOP

The action buffer is bounded and latest-wins for active commands, while pending HOLD
or ESTOP cannot be overwritten by active traffic. Remote actor/plane and exact
route/session admission occurs before this local buffer. Within that admitted
context, every non-active command clears buffered active output before replay checks.
Stream sequence must strictly advance forever within the declaration; timeout never
reopens a lower position, and a foreign stream epoch requires a fresh
buffer/declaration.
An older frame cannot refresh a deadline. Predictive replay is limited by both the
60-second TTL ceiling and the maximum 65,536 horizon entries.

TTL equality is expired. Clock rewind revokes output until time catches up and a
fresh command is accepted. ESTOP clears buffered actuation and latches across
messages, reconnect, and controller restart. Wire 1.0 defines no stable reset RPC.
An authenticated operator with explicit reset authority, plus the plant's local
reset preconditions, MAY initiate a body-local or out-of-band reset procedure.

A successful ESTOP reset MUST be a session-generation cut. The body MUST retire the
current session generation, authority and lease, and all associated stream epochs,
sequence high-water marks, deadlines, and buffered actuation. The old authority
machine and action-buffer objects become retired audit state, not reusable empty
objects. The body MUST remain
non-actuating until a fresh `SessionOpened` creates a new generation, publishers
establish new streams, and a new matching authority lease is acquired. A local
governor, authority-machine, or action-buffer reset primitive MAY clear its own
latched state only as part of that procedure; it MUST NOT restore remote authority
or make the retired session live. Every frame carrying the pre-reset generation,
including ESTOP, MUST fail exact route/session binding before latch or control
processing. ESTOP priority begins only after current-generation admission. No reset
may bypass physical safety interlocks.

## Queue and fault policy

All queues use the capacities and overflow policies in
[`contract/limits.v1.json`](contract/limits.v1.json): control rejects overflow,
perception replaces latest, action retains the highest fail-safe severity (ESTOP,
then HOLD/non-active, then Active) and replaces latest at equal severity, and
observation drops oldest while counting. A transport adapter MUST preserve those
semantics rather than create unbounded retry/task queues. Duplicate, reordered,
delayed, partitioned, restart, and replay behavior remains subject to authority,
session-generation, stream-epoch, idempotency, TTL, and ESTOP checks.

The stable Zenoh action publisher uses one transport-owned stream epoch and sequence
allocator across Active, HOLD, and ESTOP. Once a put is attempted, its position is
consumed even if delivery is ambiguous. A failed fail-safe latches a publication
requirement that blocks Active admission until the caller submits a new logical
fail-safe at a new position and that publication succeeds. An adapter MUST NOT
busy-loop or retry the ambiguous bytes at the old position.

## Audit and observability

Implementations emit the bounded event and metric vocabulary in
[`contract/observability.v1.json`](contract/observability.v1.json). Credentials,
private keys, raw channel payloads, and high-cardinality identifiers are excluded by
default. The reference SHA-256 audit chain detects local mutation but is not a
signature; production certification requires an independently anchored audit log.

## Labelled legacy gateway

Wire 0.8 may enter 1.0 only through an authenticated **terminating** gateway with an
explicit `GatewayAttribution { gateway_id, source_wire: "0.8" }`. Native peers opt in
using `gateway_permitted`; absence means native-only. Transparent proxying,
delegation, and implicit bidirectional coercion are excluded.

The only currently specified field translation is legacy `ChannelSpec.optional`:
`false` maps to `requirement=required`, and `true` maps to
`requirement=optional`, but only when explicit trusted gateway context supplies the
otherwise missing 1.0 identity/security/session/profile data. Missing, null,
non-boolean, mixed old/new fields, or a request to operate transparently is rejected.
The convenience translator without context always returns
`NCP-GATEWAY-002`; it cannot invent authority.

The same-wire [`ncp-gateway`](ncp-gateway/) process is not this migration gateway.
It accepts native 1.0 lifecycle JSON and therefore requires a native 1.0 Python
`SessionService` behind it.

## Exclusions and release boundary

`BulkObservation`, bare `NCPB` transport, protobuf runtime transport, gRPC,
transparent proxies, delegation, universal-zero claims, physical safety
certification, real-time certification, paper reproduction, and calibrated-posterior
claims are outside stable 1.0.

The repository candidate cannot become an NCP 1.0 release until every required
`pre_release_gates` entry in
[`contract/release-gates.v1.json`](contract/release-gates.v1.json) has evidence bound
to one immutable source and artifact set. Local corpus success does not substitute
for live mTLS/ACL/rotation/revocation, independent installed peers, fault/soak,
fuzz/sanitizer duration, performance/resource evidence, package/signature/SBOM,
clean-room reproduction, or consumer certification. The registry's
`post_release_validations` run only after publication and do not block the initial
tag or publication.
