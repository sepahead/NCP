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
authority or stop the Crebain body daemon. Crebain owns its daemon lifecycle.

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
principal and current Crebain-issued lease.

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
type, schema ID, and purpose. The selected ingress profile binds the reference to
its realm, activation, audience, manifest, and replay coordinate. A-direct uses
the receiver-owned context. B-over-A uses the protected JWS envelope.

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

The selected X02 profile requires Crebain to advance its selected drones
atomically. It requires Engram to advance one NEST controller epoch from one
aggregate observation. Each required 1, 2, or 3-drone run uses one composite
fleet session.

The reusable plant-channel-layout profile defines encoding, bounds, digest
construction, slot vocabulary, and packer rules. It contains no concrete roster
or physical-resource assignment. The selected content-addressed layout instance
binds a sorted immutable stable-drone-ID roster and its concrete slots. NCP does
not branch on drones or Crebain.

The layout digest commits the plant-profile digest, roster, roster digest, and
ordered scalar-slot set. Each slot binds these fields:

- Contiguous scalar index.
- Stable drone ID.
- Plane, frame class, and channel direction.
- Channel semantic and component axis.
- Availability-group ordinal for each sensor slot.
- ENU coordinate frame.
- Exact unit and binary64 encoding.
- Numeric-domain or range reference.
- Physical-resource ID for a command slot.

The selected X02 layout maps each drone ID to these components:

- ENU position: three `m` values.
- ENU velocity: three `m/s` values.
- ENU acceleration command: three `m/s^2` values.

One aggregate `SensorFrame` contains `6N` scalar slots and one mandatory
layout-sized availability bitmap. One aggregate `CommandFrame` contains `3N`
scalars. One channel never mixes units. The layout proves a gap-free bijection
across the roster, required semantics, component axes, and availability groups.

X02 assigns one availability group to each drone's six sensor slots. Stable 1.0
fixes `1 = AVAILABLE` and `0 = UNAVAILABLE`. It also fixes
least-significant-bit-first group order and zero unused high bits. B03 allocates
the field identity, ceilings, errors, and profile identities. Each required fleet
uses one bitmap byte.

The all-available X02 bytes are `01`, `03`, and `07`. The first-drone
unavailable bytes are `00`, `02`, and `06`. An unavailable group retains
fixed offsets with canonical binary64 positive-zero placeholders. These bits are
internal encoding, not sensor values or safety policy.

Zero-based group `g` depends on command slots `[3g, 3g+1, 3g+2]`. Each slot
contains one binary64 positive-zero restrictive value. The layout instance binds
this map and the exact restrictive bytes. Preparation rejects missing, duplicate,
out-of-range, or conflicting dependencies before it creates a publisher.

Each producer prepares one opaque layout-bound publisher for its frame class.
Crebain owns the sensor publisher. Engram owns the direct command publisher.
Haldir owns the gated command publisher. Engram publishes only intent during a
gated authority term.

Preparation accepts the complete key roster. It creates opaque scalar and
availability-group handles. Each handle binds one layout member and prepared
publisher generation. Preparation rejects invalid keys before resolving offsets.
Input order grants no meaning. The installed layout sets every order.

Each frame resets every availability group to undecided. The publisher marks each
group exactly once. An available group requires every finite in-range scalar
exactly once. An unavailable group forbids caller scalar writes. The packer
writes its canonical placeholders internally.

Stale, foreign, duplicate, inherited, or post-seal handles reject. Missing
groups or values reject before position assignment. The decoder returns
`Available(values)` or `Unavailable`. It never exposes unavailable
placeholders as values.

The publisher assigns the final position and serializes once. It then moves the
immutable buffer into its layout-bound transport slot. The publisher and slot
form one opaque prepared capability. The API exposes no detached buffer or
context-rebind operation.

The publisher is the only application publisher for its route and frame class.
Its production API exposes no mutable byte alias, raw namespace handle, separate
signer, or second application publishing path.

The prepared context binds the profile, descriptor, layout instance, route,
session, generation, producer, connection incarnation, stream declaration,
frame class, security state, exact length, and transport slot. An A-direct hot
frame repeats no slot tag, layout digest, key ID, preparation digest, or
application signature. B-over-A uses its protected exact-byte envelope when
forwarding is required.

Each command cites the exact pending fleet sensor frame. The source identity
covers the complete bitmap and scalar storage. Crebain's source window and source
pin retain the exact availability projection.

One X02 Active command always contains all `3N` acceleration values. Each
unavailable sensor group requires canonical positive zero in its dependent
three-value command lane. This vector belongs to X02. NCP defines no universal
zero action.

Crebain validates the current prepared context and complete command before
simulator callback. A partial, stale, non-finite, wrong-length, wrong-profile,
wrong-layout, wrong-roster, wrong-source, unauthorized, or nonrestrictive frame
rejects as one unit. Crebain then applies its separately attributed local
fail-safe.

A correctly restricted X02 Active command receives `APPLIED`. It does not
receive `HOLD_EFFECTIVE`. The disposition binds the source pin, availability
projection, profile check, callback boundary, and applied-value reference.

### X02 NEST fault behavior

Engram uses one NEST 3.9 kernel and session for the complete fleet. Resolution is
`0.1 ms`. Each controller epoch is `20 ms`. The qualification seed is
`20260826`.

Each drone owns six signed populations. Two populations encode each acceleration
axis. Each population contains eight neurons. Baseline input is `100 Hz`.
Full-scale input is `5000 Hz` with `5.0 mV` weight.

An Engram controller manifest binds the exact NEST build and deterministic
settings. It binds every neuron, synapse, parameter, connection, and device. It
also binds the `6N` input transform and `3N` decoder with clamps. The manifest
binds target trajectories, seeds, thread count, and counter-based input streams.
Its artifact digest enters the X02 receipt.

Every drone owns disjoint nodes, synapses, stimulators, recorders, and RNG
streams. A stream key includes the qualification seed, stable drone ID,
population, neuron, and epoch. No lane consumes another lane's RNG state.
Deterministic thread settings form part of the receipt.

Each lane uses `NORMAL`, `UNAVAILABLE_RESTRICTIVE`, or `RECOVERY_WASHOUT`.
Unavailable input moves any lane to `UNAVAILABLE_RESTRICTIVE`. That state uses
neutralized input and the restrictive output. Its next available frame enters
`RECOVERY_WASHOUT`. Washout also uses neutralized input and restrictive output.
Another unavailable frame returns the lane to `UNAVAILABLE_RESTRICTIVE`. The
next available frame enters `NORMAL` and resumes normal encoding.

Engram never resets the NEST kernel during fault recovery. Every epoch advances
the exact NEST biological time. Fault handling changes only the affected lane's
input gate. Other lane topology, state, and generated bytes remain unchanged.
A receipt-qualified run proves bitwise equality against its no-fault baseline.
Restart restores the exact lane state or retires and reopens the session.

TLS record protection covers the exact bytes passed to its seal operation until
a successful receiver open. It detects record mutation after seal and before
open. It does not attest application provenance or the packer's prior state.

TLS cannot detect sender mutation before seal or receiver mutation after open.
It also cannot detect a plausible same-unit misassociation, bad physical wiring,
or a compromised packer. A swap of equal binary64 values is byte-identical.
Stronger origin claims require a separate profile with independent per-entity
attestors.

Crebain records transport acceptance separately from simulator callback entry
and body-boundary application. NCP does not claim physical atomicity from frame
acceptance. Crebain supplies any executor-level atomicity evidence.

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

Availability work is `O(ceil(group_count / 8))`. Up to eight groups add one
bitmap byte. The core adds no second hot message, digest, serialization, or
queue item. Preparation resolves groups and offsets before the tick loop.
Source pins retain immutable frames by reference. Condition detail uses separate
capacity and cannot borrow core resources.

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
- real NEST 3.9 closed loops with 1, 2, and 3 Crebain drones;
- canonical cross-language layouts and typed packing for all three fleet sizes;
- exhaustive masks, exact bytes, fixed lengths, and stable digests for all fleets;
- every single, pair, and all-drone fault. Include persistent and alternating
  faults, fault during washout, restart, recovery, and exact dispositions;
- receipt-qualified lane isolation and exact controller-manifest replay;
- compact-binary and compatibility-JSON availability parity;
- pin survival under pressure and exact restart restoration or retirement;
- one indivisible header, bitmap, and scalar queue item;
- typed missingness through direct, gated, Galadriel, and Prisoma paths;
- optional sensor-condition detail absent or late with unchanged safety behavior;
- one moved payload buffer with no extra application authentication field;
- read-only Prisoma capture with explicit gaps and missingness;
- default-off Galadriel observer and advisory-extension roles;
- clean restart, rotation, revocation, and bounded overload behavior.

The campaign must include these negative controls:

- cross-project Host API, private IPC, or `postMessage` semantic transport;
- panel lifecycle changing daemon, session, or authority state;
- SVG, static assets, packages, or opaque blobs used as protocol semantics;
- mixed direct and gated commanders for one authority term;
- partial fleet commands or cross-session atomicity assumptions;
- missing, short, long, padded, inherited, contradictory, or mutated availability;
- unavailable groups with caller values or nonrestrictive dependent commands;
- detached, split, spliced, separately dropped, or separately superseded bitmaps;
- wrong group membership, dependency map, or conflicting restrictive overlap;
- decoder exposure of unavailable placeholder bits as observations;
- optional condition detail that changes availability or blocks core traffic;
- privacy projection that converts unavailable input to available zero;
- kernel reset, cross-lane connections, shared RNG state, or nondeterministic threads;
- missing, duplicate, unknown, or invalid keyed packer records;
- raw application publisher, mutable-byte alias, or shared credential access;
- sealed-record or protected-envelope mutation before receiver open;
- sender mutation before seal treated as receiver-detectable provenance;
- receiver mutation after open treated as transport-detectable provenance;
- a slot handle or detached buffer accepted by a different prepared publisher;
- packer output treated as receiver-attested without independent evidence;
- same-unit misassociation treated as receiver-detectable provenance;
- NCP used for MUSIC scheduling or shared-clock claims;
- sender-local success treated as body admission or application;
- one role receipt reused for another role or artifact.

Host API 2 fleet evidence remains historical Host API evidence. It cannot satisfy
a native NCP role, transport, closed-loop, or release qualification.
X02 remains `OPEN`. This proposal records required evidence, not completed
native-NCP execution.
