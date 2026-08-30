# ADR-011 module — Cross-project integration boundary

> Status: PROPOSED and non-normative. Parent: ADR-011.

This module is part of the ADR-011 B01 review source set. It defines the
integration boundary for NCP 1.0 ecosystem consumers. It has no normative effect
before B01 ratification, B02 rebaseline authorization, and N01 promotion.

## Boundary rule

Each project keeps its standalone core independent of NCP. An optional adapter
owns every NCP dependency, credential, route, and lifecycle obligation.

Cross-project runtime semantics use one stable NCP 1.0 message or one registered
NCP 1.0 extension. Project-private APIs and IPC remain inside one project trust
boundary. They never cross an ecosystem project boundary.

An adapter must not copy NCP schemas, route builders, or protocol source. It uses
one pinned NCP package and one exact contract identity.

## Presentation plane

Engram can host verified presentation UI assets from another project. The host can own
panel placement, theme, readiness, heartbeat, and container lifecycle.

An Engram NCP adapter can create a bounded read-only presentation projection.
The host can render that projection and its stale state. The projection binds an
opaque source-receipt digest but exposes no credential, route, grant, lease, or
mutable role state.

The host must not carry opaque project state or a live NCP object. An agent,
runtime, or controller cannot consume the projection as input. The projection
cannot prove protocol delivery, authority, body effect, or scientific evidence.

The panel submits one bounded operator intent to an Engram-local UI ingress.
That ingress can use Host API, private IPC, or a callback inside Engram's trust
boundary. Its payload contains no NCP object, credential, route, grant, lease,
receipt, or remote result. Engram policy maps an accepted intent to one
role-specific adapter call. Only that adapter crosses a project boundary, and it
uses NCP.

Closing or restarting a panel does not close an NCP session. It does not revoke
authority or stop the CREBAIN body daemon. CREBAIN owns its daemon lifecycle.

SVG is a presentation-only and non-contract format. SVG bytes, elements,
paths, attributes, rendered pixels, and derived identifiers are never protocol
messages, envelopes, schemas, authority objects, receipts, or runtime evidence.
Hosted SVG rejects scripts, event handlers, `foreignObject`, external resources,
navigation, network fetches, and external fonts.

## Registered Haldir intent extension

Gated mode uses the Haldir-owned registered extension
`org.sepahead.haldir.intent.v2`. Engram publishes `haldir.intent.v2` through its
dedicated extension-publisher role. Haldir receives it through a dedicated
extension-receiver role.

The extension manifest binds the exact owner, schema digest, canonical encoding,
route, producer, audience, security profile, bounds, and lifecycle policy. The
envelope binds the direct `AuthorityRealmKey`, plant-session foreign key,
freshness grant, replay coordinate, intent bytes, and optional source evidence.

Engram holds no plant lease in gated mode. Haldir verifies and evaluates the
intent. Haldir then constructs a fresh standard NCP `CommandFrame` under Haldir's
principal and current CREBAIN-issued lease.

Haldir never forwards or re-signs Engram command bytes. Engram's extension
signature grants no NCP commander identity, plant authority, or body admission.

Transport acceptance, Haldir intent admission, Haldir policy decision, NCP
command admission, body disposition, and body-boundary application are distinct
events. Evidence for one event cannot substitute for another.

These two extension roles require separate qualification receipts:

- Engram Haldir-intent extension publisher.
- Haldir Engram-intent extension receiver.

The complete ecosystem release matrix therefore contains eleven exact role
receipts. No repository-level or aggregate receipt can replace them.

## Extension encoding and attachments

The NCP 1.0 extension default is one bounded canonical-JSON semantic envelope.
The installed manifest selects one closed schema and one canonicalization
profile. Unknown members, duplicate decoded keys, non-canonical numbers, and
unsupported encodings reject before callback.

Large bytes remain outside the semantic envelope. A bounded attachment reference
contains an enrolled store ID, canonical object key, digest, byte length, media
type, schema ID, and purpose. The protected envelope binds the reference to its
realm, activation, audience, manifest, and replay coordinate.

An attachment reference grants no fetch authority by itself. The installed
manifest enrolls the exact HTTPS origin, resolved address set, TLS identity,
credential scope, timeouts, media types, size, count, and aggregate bytes. A
reference cannot contain a URL, user information, query, fragment, local path, or
redirect target. The receiver uses a non-ambient scoped credential. Redirects,
DNS or address drift, local-file resolution, and symlink traversal reject.

The receiver reserves every resource before it mints a one-use fetch capability.
That capability binds the envelope digest and exact attachment reference. The
receiver verifies length and digest before semantic use. Partial or unavailable
attachments make the dependent semantic branch unusable.

After all bytes verify, the activation owner atomically rechecks activation,
security, principal, audience, manifest, realm, session, freshness, revocation,
expiry, and resource currentness. The same transition consumes the one callback
right. A cut during fetch prevents callback entry.

NCP 1.0 does not define a generic chunk-reassembly protocol. A future binary
extension profile needs a new identity, explicit negotiation, independent bounds,
and separate qualification. It cannot become a static-asset or package tunnel.

## Plant-session granularity

A plant session represents one authority and admission domain. Its
content-addressed plant profile can describe one entity or one composite plant.

The selected X02 profile requires CREBAIN to advance its selected drones
atomically. It requires Engram to advance one NEST controller epoch from one
aggregate observation. Each required 1, 2, or 3-drone run uses one composite
fleet session.

The content-addressed profile binds a sorted immutable stable-drone-ID roster.
It also binds one exact channel-layout digest. Each drone ID maps to these
components in roster order:

- ENU position: three `m` values.
- ENU velocity: three `m/s` values.
- ENU acceleration command: three `m/s^2` values.

One aggregate `SensorFrame` contains `6N` scalars. One aggregate `CommandFrame`
contains `3N` scalars. One channel never mixes units.

Each command cites the exact pending fleet sensor frame. CREBAIN validates the
descriptor digest, layout digest, roster order, and whole frame before it invokes
the simulator. A partial, duplicate, unknown, misordered, stale, non-finite,
unit-mismatched, wrong-drone, same-unit cross-drone swap, or roster-permuted
channel rejects the whole frame.

CREBAIN records transport acceptance separately from simulator callback entry and
body-boundary application. NCP does not claim physical atomicity from frame
acceptance. CREBAIN supplies any executor-level atomicity evidence.

Future independently scheduled drones use independent sessions. Their plant
instances, profiles, leases, streams, and state stores remain disjoint. NCP grants
no barrier or atomic commit across sessions.

If coordinated frame admission is required, retire the component sessions first.
Then open one composite session. Overlapping actuator resources across component
and composite sessions reject.

## Time and MUSIC

MUSIC remains the shared-clock simulator-coupling protocol. NCP does not
implement, tunnel, reinterpret, or replace MUSIC time grants, lookahead,
scheduler barriers, tick ownership, or deadlock resolution.

NCP owns heterogeneous boundary identity, authority, lifecycle, bounded data,
and evidence. A deployment can use MUSIC and NCP together because their
responsibilities do not overlap.

The selected X02 profile uses independent clocks and exact NCP source
correlation. It does not qualify a shared-clock simulation. Any shared-clock
claim requires a separate MUSIC-qualified deployment and evidence set.

## Performance and resource claims

No transport has literal zero overhead. Any NCP overhead claim must bind one exact
artifact, hardware target, workload, security profile, transport, and measurement
receipt.

The prepared steady-state goal is zero payload-proportional allocation and at
most one payload copy where the selected transport permits it. This goal is not
a release claim until measured.

Qualification records p50, p95, p99, p99.9, maximum latency, jitter, deadline
misses, throughput, CPU time, allocation count, allocation bytes, queue depth,
and retained bytes. It reports every outlier and failure.

Control and action capacity remains isolated from observer and extension work.
An observer, UI panel, attachment fetch, or extension callback cannot consume
reserved control or action capacity.

## Required qualification scenarios

The ecosystem campaign must include these positive controls:

- standalone operation with every optional NCP adapter disabled;
- direct Engram control through standard NCP messages;
- gated Engram control through the registered Haldir intent extension;
- real NEST 3.9 closed loops with 1, 2, and 3 CREBAIN drones;
- read-only Prisoma capture with explicit gaps and missingness;
- default-off Galadriel observer and advisory-extension roles;
- clean restart, rotation, revocation, and bounded overload behavior.

The campaign must include these negative controls:

- cross-project Host API, private IPC, or `postMessage` semantic transport;
- panel lifecycle changing daemon, session, or authority state;
- SVG, static assets, packages, or opaque blobs used as protocol semantics;
- mixed direct and gated commanders for one authority term;
- partial fleet commands or cross-session atomicity assumptions;
- NCP used for MUSIC scheduling or shared-clock claims;
- sender-local success treated as body admission or application;
- one role receipt reused for another role or artifact.

Host API 2 fleet evidence remains historical Host API evidence. It cannot satisfy
a native NCP role, transport, closed-loop, or release qualification.
X02 remains `OPEN`. This proposal records required evidence, not completed
native-NCP execution.
