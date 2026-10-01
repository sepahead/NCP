# Owner decisions for NCP 1.0 (1 October 2026)

This record states the owner's decisions for finishing NCP 1.0. It is not an
independent review, a certification, or a release authorization by itself. The
non-normative decision registry in `docs/adr/` is unchanged; its structural checks
cannot prove authorship or independence in any case.

## 1. Architecture decisions ADR-001 to ADR-011

The owner delegated ratification to the maintainer's best judgement, with one
stated goal: Haldir must be as useful as possible for real-world operation with NCP
and the rest of the ecosystem. On that basis all eleven decisions are **accepted**
with three amendments.

| ADR | Decision | Accepted because |
|---|---|---|
| 001 | Separate simulation, plant and observer sessions | A union message with optional fields lets defaults choose safety meaning |
| 002 | Separate contract identity from release authorization | A version string or short hash cannot prove semantic compatibility |
| 003 | Authenticate production ingress before interpretation | Payload identity, Zenoh source IDs and certificate common names are forgeable |
| 004 | Attach observers with bounded grants and revocation | Observers must never widen into command authority |
| 005 | Declare and retire every stream explicitly | Inferred epochs and automatic rollover break loss and replay accounting |
| 006 | Body-issued authority and receiver-local time | The component that drives the actuators must issue and enforce authority |
| 007 | Journal body-issued command dispositions | Publication or a gate acknowledgement is not execution |
| 008 | Separate stable routes from extensions | Project payloads must not leak into the stable core |
| 009 | Bind semantic security state, rotation and revocation | Key and manifest changes must stop or re-admit sessions explicitly |
| 010 | Finite per-plane QoS and overload behaviour | Unbounded queues and shared capacity starve fail-safe traffic |
| 011 | Fix dependency direction and plant handover | NCP must stay project-neutral and every adapter optional |

### Amendments

- **A1, implementation profile.** NCP 1.0 implements the "low-overhead
  reconciliation" profile that each ADR defines. The safety, authority, time and
  fail-closed rules stay closed; only the implementation names and finite
  capacities are chosen during implementation.
- **A2, planner-neutral intents.** The Haldir-owned extension
  `org.sepahead.haldir.intent.v2` accepts signed intents from any enrolled
  planner. Engram is the first qualified publisher, not the only one. Haldir still
  constructs each command under its own principal and never forwards planner
  command bytes.
- **A3, body-neutral authority.** The enrolled body that issues and enforces plant
  authority is any vehicle adapter that implements ADR-006 and ADR-007. Crebain is
  the reference body. A future PX4, ArduPilot or ROS 2 bridge needs no change to
  the protocol.

Independent review of each ADR remains open and visible. Under decision 3 below it
is a post-release validation, not a hidden assumption.

## 2. Package names

The intended registry names `ncp-core` (crates.io) and `ncp` (PyPI) belong to
unrelated projects. NCP 1.0 publishes under the `sepahead-ncp` family:
`sepahead-ncp-core` and `sepahead-ncp-zenoh` on crates.io, `sepahead-ncp` on PyPI,
and `@sepahead/ncp` on npm. Rust import paths may keep the `ncp_core` library name.

## 3. Release gates

The `v1.0.0` tag is cut after every technical pre-release gate that the
maintainers can run passes. Gates that need parties outside the project — an
independent clean-room reproduction, independently implemented non-Rust live
peers, and independent consumer certification — become explicitly listed
post-release validations in the release notes. Their results, including failures,
are published and never rewritten as pre-release passes.

## 4. Migration

Every consumer moves to native NCP 1.0 and retires its wire-0.8 surface: Engram,
Crebain, Galadriel, Haldir, Prisoma, and the thesis counterexample harness. Until
the contract rebaseline that implements ADR-006, ADR-007 and ADR-008 lands,
consumers target the `1.0.0-rc.1` wire, in which a commander acquires its own
lease and the receiver enforces it. After the rebaseline they move to body-issued
authority and registered extensions.
