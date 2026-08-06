# Why NCP was proposed — design rationale for the Neuro-Cybernetic Protocol

> **Current-status note:** this comparative argument is informative and partly
> historical. Repository HEAD is the unreleased, release-blocked NCP
> `1.0.0-rc.1` candidate; the latest immutable annotated source tag is `v0.8.0`.
> No rationale substitutes for live security, independent interoperability,
> fault, safety, or consumer evidence.

> This design rationale compares NCP with robotics middleware, environment APIs,
> agent protocols, and neuroscience co-simulation. It credits substrate functions
> to the substrate and states the composition alternative and NCP ownership cost.

## Thesis (and an honest caveat about it)

NCP targets a specific design point: a **versioned, transport-agnostic,
project-agnostic wire contract for simulation providers and external robot, UAV,
and analysis clients**. The contract includes neural record and stimulus
semantics, simulation provenance, plane-specific QoS, explicit command modes, and
an observation role that has no actuation authority. A NEST provider is one
intended implementation. No installed native-1.0 provider or observer role is
qualified yet.

The honest caveat, stated up front: "no off-the-shelf protocol occupies this exact
point" is **weak evidence of necessity**. Any sufficiently conjunctive target
(all of A∧B∧C∧D∧E) is unoccupied *by construction* — that is gerrymandering, not
proof. Comparing NCP with one component at a different layer is incomplete. The
useful question is whether a ROS 2 transport, application messages, and a watchdog
form a better deployment-specific composition. This document treats that
alternative separately.

## What NCP is

NCP is a domain-and-provenance layer over its selected transport. Normative
precedence is the versioned contract registries, protobuf field-number/message
shapes, generated JSON Schemas, prose specification, then mandatory corpus.

The reference implementation includes these packages:

- `ncp-core` supplies wire types, validation, safety primitives, codecs, and keys.
- `ncp-zenoh` supplies the stable transport binding.
- `ncp-gateway` supplies a Rust edge to a Python `SessionService` on wire 1.0.
- `ncp-python` and `ncp-cpp` expose Rust decisions through FFI.
- `@sepahead/ncp` supplies generated types and independent TypeScript decisions.

The Zenoh binding defines four key families. Control uses request/reply RPC.
Perception uses Best-Effort DROP plus an adapter-side replace-latest slot. Action
uses express, RealTime-priority DROP. Observation uses DROP and a bounded
drop-oldest queue policy. Known command modes are `init`, `active`, `hold`, and
`estop`; an unknown mode cannot authorize actuation. Every observation carries
`is_simulation_output=true` and `calibrated_posterior=false`. These fields identify
a simulation artifact, not a paper reproduction or calibrated posterior.

### One contract, many consumers (the generic-hub design)

NCP does not name consumer projects in its wire contract. One contract can therefore
target independently developed peers. The intended topology is
**hub-and-bodies**: a *commander/hub* can drive one or more *bodies*. Authorized
*observers* can receive observation-plane data without actuation authority.
The contract names none of them; the commander core speaks only
entity/channel-addressed NCP (see `INTEGRATING.md`). The following roles describe
the historical wire-0.8 topology and intended native-1.0 model; they are not current
native-1.0 interoperability evidence:

- **Engram** (a.k.a. Paper2Brain) is the intended **hub / command-center**. Its
  native-1.0 migration is in progress and not installed or live-qualified.
- **Crebain** is an intended body and owns the Galadriel-producer surface. Both
  historical surfaces remain wire 0.8.
- **Haldir** is an intended commander and Galadriel-assessment receiver. Its two
  historical surfaces remain wire 0.8.
- **Galadriel** is an intended NCP observer and raw-advisory publisher. Its two
  historical surfaces remain wire 0.8.
- **Prisoma** is an intended read-only analysis/observer client and remains wire
  0.8.
- **pid-rs** remains a protocol-neutral library/CLI. Consumer-owned adapters can
  call it, but it receives no NCP role receipt.
- **Cortexel** is historical intake inventory only. It is not an NCP dependency,
  consumer, commander, atlas owner, documentation-import target, or authority.
  ADR-011's content-bound review subject still contains an unratified optional
  export question; it grants no implementation task or work authority.

The intended first-principles payoff is that a conformant body and brain can
interoperate without either knowing the other's implementation—the same property
that lets an observer attach without changing the control path. That remains a
design goal until installed native peers prove it. A separate contract has value
only when its consumer and evidence boundaries justify its maintenance cost. A
single-framework deployment can have a smaller composition boundary.


## Why existing solutions were insufficient

Many compared technologies operate at a different layer. They supply transport,
serialization, simulation APIs, or application frameworks. NCP must therefore be
compared with a composition of those parts, not with one part in isolation. NCP
inherits transport and topology behavior from its substrate.

**ROS 2 / DDS.** ROS 2 topics, services, and actions can represent many NCP
surfaces. Its tooling can also be a better fit for a deployment that already uses
ROS 2. DDS QoS offers mechanisms that are related to NCP controls, but the meanings
are not equal. LIFESPAN limits sample validity, DEADLINE reports missed update
expectations, LIVELINESS reports writer availability, and OWNERSHIP selects among
writers. NCP's `ttl_ms` is enforced from the receiver's local acceptance time.
NCP declares identity, route, session generation, stream position, authority
lease, command mode, and a plant-profile digest for the intended receiver-admission
model. The current reference does not integrate installed-profile validation or
body execution into Active admission. DDS QoS alone does not supply the declared
NCP semantics or prove an actuator action. ROS 2 does not define NCP's neural
vocabulary or simulation-provenance boundary. A ROS-based composition remains a
valid design alternative, especially when all consumers already use ROS 2.

**Zenoh alone.** Zenoh is NCP's selected stable transport substrate. Queryables
carry control-plane RPC. DROP, express delivery, and priority settings implement
the current data-plane QoS mapping. Routed subscriptions support observation
delivery. Zenoh is payload-agnostic and does not define NCP types, neural semantics,
identity, authority, provenance, or plant policy. The capacity-one replace-latest
receive slot is NCP adapter behavior. Transport and topology properties come from
Zenoh, not from the NCP contract.

### Why Zenoh specifically — features, not raw latency

Choosing Zenoh is a feature decision, not a latency claim. Zenoh carries three
pub/sub planes plus the queryable RPC plane. It contributes no NCP neural,
provenance, identity, authority, or plant semantics. The adapter uses these
configured features:

- **Per-plane QoS** — action is express / RealTime priority / DROP, perception is
  DataHigh / DROP, and control is reliable / BLOCK. The typed adapter separately
  retains one freshest received perception frame. One bus, three
  reliability/priority regimes.
- **Queryable RPC** — request/reply for the control plane without bolting a second
  protocol onto the data bus.
- **Topology options** — the configured substrate supports direct or routed
  deployment and multiple subscribers. The NCP contract requires role and plane
  authorization. The current stable adapter cannot enforce remote
  `production-secure` identity and therefore fails closed.
- **Configured shared-memory facility** — the reviewed dependency profile enables
  Zenoh's `shared-memory` feature. The NCP publisher does not construct a shared-
  memory payload, so this repository demonstrates no NCP zero-copy path.

NCP does not claim that Zenoh leads on raw latency. The historical local figures in
[`PERFORMANCE.md`](PERFORMANCE.md) bind specific developer runs and do not compare
current DDS and Zenoh releases under one controlled profile. Zenoh is selected for
its routing, QoS, queryable, and topology features. A deployment must measure the
shipped NCP copy path, security profile, topology, payload, and load before it sets a
latency budget.

One wire-shape-neutral optimization candidate is worth recording.
`ZenohBus::put` in `ncp-zenoh/src/lib.rs` currently calls `payload.to_vec()` for
each publish. An owned-buffer or compatible `ZBytes` path could remove that copy.
It would not establish shared-memory zero-copy by itself. Ownership, buffer
compatibility, backpressure, security behavior, and end-to-end measurements still
need implementation and verification. See `KNOWN_LIMITATIONS.md` for the current
bus and safety boundaries.


**MAVLink / MAVROS.** MAVLink or MAVROS can own a UAV actuation edge that an NCP
body targets, such as a reviewed mapping from `CommandFrame` to a flight-controller
command. NCP does not define or qualify that mapping. MAVLink also does not define
NCP's neural record, stimulus, or simulation-provenance semantics.

**gRPC / protobuf.** A gRPC binding could express request/reply and streaming
surfaces. It would require a separately specified mapping for NCP's plane-specific
delivery, routing, overflow, and observation semantics. No gRPC performance or
fitness claim is made here. Stable NCP 1.0 excludes a gRPC binding and protobuf
runtime encoding, so adding either would require a reviewed protocol change and
conformance evidence.

### What the wire actually is — JSON at runtime, protobuf as the schema

A recurring overstatement worth correcting precisely: **protobuf is NCP's field-
shape IDL, not its shipped runtime encoding or sole contract source.**
`proto/ncp.proto` (plus the `gen/` parity output) is the field-number/message-shape
layer and the `buf breaking` gate — but its prost Rust bindings are **not compiled or wired as a runtime path**
(there is no `prost` dependency in the workspace, and `gen/rust` is not a workspace
member). What actually travels on the live planes is:

- **JSON (`serde_json`)** on every shipped plane — Sensor (perception), Command
  (action), RPC (control), and Observation. `ZenohBus` ships their JSON bytes.
- a bounded **local/offline `BulkBlock` columnar codec** (`ncp-core/src/bulk.rs`).
  It is not a transport frame; a future negotiated observation path must wrap it
  in complete metadata and ship in every binding first.

Why JSON is the stable runtime representation in this candidate:

1. **Inspectable with authorized tooling.** JSON lets an authorized diagnostic or
   experimental WebSocket endpoint display the `mode`, `ttl_ms`, and channel
   values without a protobuf decoder. Transport security and access controls still
   apply.
2. **One JSON interface across current bindings.** Python and C/C++ expose JSON
   through Rust FFI. TypeScript supplies generated types and independent JSON
   decisions. A consumer does not compile the protobuf runtime to use these paths.
3. **One contract, two projections.** The `.proto` and the `schemas/` JSON Schemas
   are kept in lockstep by parity guards, so protobuf's schema discipline is
   retained even though the bytes are JSON.

Why protobuf still earns its place: it is the **machine-checkable contract** that
pins field numbers and types so the JSON projection cannot silently drift.
Historical local measurements in [`PERFORMANCE.md`](PERFORMANCE.md) characterize
one JSON hot path, but they do not establish a release-bound transport or workload
budget. A future binary runtime would require explicit negotiation, complete
binding support, and a normative rebaseline. JSON remains the stable runtime
representation. The local `BulkBlock` codec demonstrates a packed layout, but it
does not establish a negotiated binary transport.


**dm_env_rpc / MCP / ACP / A2A.** `dm_env_rpc` is a networked environment-control
protocol and is close in spirit to NCP's control plane. NCP adds a different
contract for neural records and stimuli, plane-specific delivery, command modes,
authority, and simulation provenance. MCP, ACP, and A2A address tool or agent
orchestration rather than NCP's continuous plant data planes. This document makes
no comparative latency or maturity claim. Their versioned capability patterns are
useful control-plane design references, not substitutes for NCP data-plane and
plant semantics.

**Gym / dm_env / Gymnasium / PettingZoo.** Their `reset` and `step` operations and
typed observation/action specifications are useful API analogies for NCP lifecycle
operations and capabilities. The in-process APIs do not define NCP's wire,
transport security, plane QoS, or plant authority. Networked environment protocols
can bridge that gap with a different contract.

**MUSIC and the Neurorobotics Platform / PyNN / NEST Server.**
[Djurfeldt et al. 2010](https://pmc.ncbi.nlm.nih.gov/articles/PMC2846392/) describes
MUSIC ports for runtime event and continuous-data exchange between simulators.
That work is direct prior art for NCP's event and continuous neural channels.
[Weidel et al. 2016](https://www.frontiersin.org/articles/10.3389/fninf.2016.00031/full)
describes a NEST, MUSIC, ROS, and Gazebo closed loop. NCP must not claim to have
invented an SNN-robot loop or port-typed neural exchange.

NRP, PyNN, NESTML, and NEST Server provide additional simulation, model, and
service patterns. This document does not assert a current deployment, latency,
security, or topology comparison for those systems. NCP's intended difference is a
separately versioned contract for identity, authority, provenance, plane QoS, and
plant-facing behavior. That difference remains a design proposition until
installed independent peers qualify it.

## The strongest counter-argument: "compose, don't invent"

The one argument that genuinely threatens NCP's existence, stated in full so it
must be answered:

> *Take ROS 2 on a Zenoh middleware. Define three
> message packages — `neuro_msgs/RecordFrame`, `StimulusFrame`, `CommandFrame` —
> each with `bool is_simulation_output`, `bool calibrated_posterior`, and a
> `SimProvenance` sub-message. Set per-topic QoS: Reliable + Deadline + Lifespan
> for action, Best-Effort + KeepLast(1) for perception. Implement ESTOP/HOLD/TTL
> as a node-level lifecycle plus a Deadline/Liveliness/Lifespan watchdog. Non-ROS
> clients use an explicitly specified bridge. This composition still defines an
> application contract, but it reuses ROS 2 types, tooling, and lifecycle
> mechanisms. What does `ncp.proto` + `ncp-core` + `ncp-zenoh` + PyO3 buy that this
> composition does not?*

This is a viable alternative. The relevant NCP differences and limits are:

1. **Explicit off-ROS contract.** NCP provides JSON and language bindings without
   requiring a ROS graph in each consumer. *Weakness:* a reviewed ROS bridge can
   provide the same reach with a different maintenance boundary.
2. **Authority in the application contract.** NCP combines command mode with
   identity, route, session generation, authority lease, stream position, and plant
   profile. DDS QoS has related transport controls, but it does not automatically
   implement these NCP decisions. *Weakness:* NCP's composition must still prove
   the installed body behavior and is not safer merely because fields exist.
3. **One reference decision implementation.** Rust owns the reference validation,
   codec, and safety logic. Python and C/C++ reuse it through FFI. *Weakness:* local
   conformance tests are not an independent audit, live peer qualification, or
   physical safety evidence.
4. **Smaller dependency boundary for non-ROS consumers.** A plain analyzer can use
   the NCP package without a ROS build graph. *Weakness:* the value depends on the
   consumer set and team operations.

Net: the composition alternative is viable and can have a smaller maintenance cost
for a team that already uses ROS 2. NCP's intended fit is the non-ROS,
multi-language case where a separate contract boundary is useful. That fit remains
not demonstrated until installed heterogeneous peers complete qualification.

## The ten lenses

> **Disclaimer (read first).** Zenoh supplies transport, routing, pub/sub, and QoS
> mechanisms. Protobuf supplies a field-shape IDL. NCP specifies how its neural,
> provenance, identity, security, session, authority, plant, and plane semantics use
> those mechanisms. This document claims no novelty for a substrate feature or a
> concept that appears in prior work.

**1. Scientific provenance and boundary.** *Advantage:* every observation requires
`is_simulation_output=true` and `calibrated_posterior=false`. These values make the
candidate's scientific non-claim machine-checkable. *Disadvantage:* the values are
NCP domain assertions, not scientific validation. The proposed PROV/RO-Crate
session archive is not shipped.

**2. Latency and performance.** *Advantage:* the adapter maps each plane to an
explicit QoS policy and bounds its local receive behavior. *Disadvantage:* the
release-bound secure transport, workload, queue, memory, and platform profile is
**NOT RUN**. Historical component measurements in `PERFORMANCE.md` do not establish
end-to-end latency or a comparison with another system.

**3. Coupling, topology, and fleet.** *Advantage:* the selected substrate supports
multiple publishers and subscribers without putting a broker API in the NCP
contract. NCP adds declared roles and bounded authority for plant action.
*Disadvantage:* transport topology does not solve application scheduling, fleet
coordination, discovery policy, or plant ownership. Each deployment must define
and qualify those decisions.

**4. Transport abstraction and medium choice.** *Advantage:* stable NCP messages
use a validated JSON projection. Canonicalization helpers can emit a deterministic
typed projection for corpus and digest work. The Zenoh adapter can forward valid
caller-supplied JSON without normalizing whitespace or member order, so transmitted
bytes are not guaranteed to match across transports. `BulkBlock` remains
local/offline, and `ncp.proto` supplies field-number and message-shape IDL.
*Disadvantage:* Zenoh is the only stable 1.0 binding. The TypeScript WebSocket
binding is experimental. Stable browser, gRPC/protobuf-runtime, and DDS bindings
are not part of the candidate.

**5. Language and runtime interoperability.** *Advantage:* the normative layers
are implementation-neutral. Python and C/C++ reuse Rust reference decisions through
PyO3 and the C ABI. TypeScript implements bounded parsing, validation, client
correlation, and plant-side decisions independently. The recorded implementation
cut in [`docs/1.0-candidate-receipts.md`](docs/1.0-candidate-receipts.md) includes
local import, link, and corpus tests. *Disadvantage:* Python and
C/C++ are not independent decision implementations. TypeScript has no qualified
stable live transport, and the required installed non-Rust peer program is
**NOT RUN**.

**6. Safety and control authority.** *Advantage:* the action contract declares
explicit command mode, receiver-local TTL, session generation, stream position,
bounded authority lease, and a content-addressed plant-profile digest. DDS QoS
offers related sample-validity, availability, and writer-selection controls, but
it is not equivalent to this intended receiver-admission model. *Disadvantage:*
installed-profile validation and body-owned execution are not integrated into
Active admission, and the current `PlantCommand` projection cannot preserve units.
Python and C/C++ wrap the Rust decisions, and TypeScript has no qualified stable
live transport. The Zenoh adapter cannot expose the authenticated remote principal
that `production-secure` requires. Its secure open path fails closed. The live
certificate, ACL, rotation, and revocation campaign is **NOT RUN**. Protocol ESTOP
is not physical safety certification.

**7. Domain semantics.** *Advantage:* NCP defines a networked and versioned wire
vocabulary for named neural records and stimuli. *Disadvantage:* MUSIC and related
systems are prior art for neural exchange. The current Engram comparison point is
NEST-specific, and a second provider has not qualified the abstraction. Backend
mapping, custom recordables, parameters, and model constraints still create
provider-specific cost and behavior.

**8. Observability and analysis.** *Advantage:* NCP defines an observer role with no
actuation authority and typed stream/source correlation. Each published stream has
`stream:{epoch,seq}`. A derived command or observation can use
`source:{epoch,seq}` for correlation. *Disadvantage:* multi-subscriber delivery is
a substrate feature. `ZenohBus::subscribe_fleet` is explicitly an untrusted
diagnostic tap, not an authorized observer boundary. The candidate cannot enforce
remote `production-secure` observer identity until the transport-principal binding
exists. No installed observer role is qualified.

**9. Ecosystem maturity, adoption, and risk.** *Advantage:* NCP reuses Zenoh,
protobuf IDL, JSON Schema, and language packaging tools. *Disadvantage:* NCP has no
neutral standards body, released 1.0 ecosystem, or qualified independent live-peer
set. It also owns continuing Rust, FFI, TypeScript, schema, transport-version, and
conformance maintenance. An established middleware composition can have a smaller
ownership cost for some teams.

**10. Developer experience and governance.** *Advantage:* NCP has a schema-first
contract, separately packaged libraries, and a mandatory shape/behavior corpus.
*Disadvantage:* independent implementations and independent qualification are
incomplete. Intended public package namespace ownership is unresolved, and neutral
governance does not exist. The repository cannot infer standardization from local
completeness.

## Disadvantages & open risks (summary)

NCP's unreleased 1.0 candidate has one Rust reference, an independent TypeScript
decision implementation, two Rust-FFI bindings, and a mandatory corpus—but not the
required independent live installed-peer program. Engram's Python NEST backend has
an explicit local native-1.0 migration in progress, but it has not completed the
installed live evidence required by the native-1.0 Rust gateway contract.
The production-secure profile is specified, but the stable Zenoh adapter cannot
bind a verified transport peer to `IdentityClaim`. Its live mTLS, ACL, certificate,
rotation, and revocation campaign is **NOT RUN**. NCP builds on concepts found in
MUSIC, ROS/DDS, environment protocols, and agent protocols. It must not claim to
have invented SNN-robot loops, port-typed neural channels, or latency leadership.
Zenoh is the only stable transport binding, and WebSocket is experimental.
Observation completeness remains best-effort under DROP QoS. The PROV/RO-Crate
archive is not shipped. A ROS-based composition remains a valid alternative whose
cost depends on the team and consumer set. `KNOWN_LIMITATIONS.md` retains the live
evidence boundaries.
Integration, deployment, security, independent-peer, safety-case, and performance
risks remain explicit.

## What NCP deliberately borrows

- **Zenoh** — queryables (RPC), DROP (perception), express/RealTime (action), and
  routed subscriptions (observers). Adapter-side replace-latest is NCP code, not a
  wire guarantee.
- **MCP-style versioned schemas + capability handshake** — `ncp_version`
  negotiation and "learn what a backend supports, fail-closed on the unsupported."
- **MUSIC's port/connector taxonomy** — continuous-(V_m/rate) vs event-(spikes)
  channels, acknowledged as MUSIC lineage.
- **ROS/DDS QoS thinking** — the per-plane reliability, priority, and overflow
  split. DDS LIFESPAN is an analogy for bounded sample validity, not an equivalent
  definition of receiver-local `ttl_ms`.
- **Gym/dm_env(_rpc) ergonomics** — `open`/`step`/`run` and `*_spec`-style typed
  capabilities.
- **PROV / RO-Crate** — the intended provenance substrate for the session archive.

## When you should NOT use NCP / use X instead

- **Coupling simulators through established co-simulation ports:** evaluate MUSIC
  before adding NCP.
- **An all-ROS 2 deployment with no off-ROS consumers:** evaluate a ROS message and
  watchdog composition before maintaining a separate NCP boundary.
- **A safety-critical path:** select the transport and safety architecture from the
  installed system's qualified requirements. NCP supplies no physical
  certification.
- **In-process, single-language Python RL:** evaluate Gymnasium or `dm_env` before
  adding a network contract.
- **LLM tool-use / agent hand-off:** **MCP / A2A**.
- **Driving a flight controller directly:** **MAVLink/MAVROS** is the edge NCP
  targets rather than replaces.

NCP targets deployments that need an explicit multi-language contract for neural
records and stimuli, simulation provenance, bounded plant authority, plane-specific
delivery, and observation roles outside one application framework. The candidate
does not prove that this design is preferable for a deployment. Compare it with the
composition alternative, then require exact installed evidence before adoption.
