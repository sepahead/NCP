# NCP — Neuro-Cybernetic Protocol

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/logo-dark.svg">
    <source media="(prefers-color-scheme: light)" srcset="assets/logo-light.svg">
    <img src="assets/logo-light.svg" width="180" alt="NCP logo: perception and action lanes cross one bounded admission core.">
  </picture>
</p>

NCP is a versioned, project-agnostic canonical-JSON contract for connecting a
neural simulator or neuromorphic controller to robots, UAVs, simulators, and
read-only analysis clients.

> **Current status:** repository HEAD is the **unreleased, release-blocked**
> `1.0.0-rc.1` candidate: wire `1.0`, compact proto contract hash
> `163acc57d8a62b66`. The latest immutable annotated source tag is `v0.8.0`; it is a
> different, incompatible wire. Do not describe this candidate as the NCP 1.0 release,
> production-certified, published, signed, or consumer-certified.

The complete normative SHA-256 contract digest and exact source list are generated
in [`contract/manifest.v1.json`](contract/manifest.v1.json). The short 16-hex
`CONTRACT_HASH` is an advisory FNV-1a digest of the canonical protobuf structure.
It is not the complete normative digest.

## System at a glance

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/diagrams/overview-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="docs/diagrams/overview-light.svg">
  <img alt="Informative NCP function overview for the unreleased, release-blocked 1.0.0-rc.1 candidate. A received frame passes five shared gates in order: raw bounds, authenticated ingress, wire and stable-core identity, session and stream checks, and typed delivery. Action adds a sixth, conditional body-effect predicate. Four bounded planes then apply distinct ownership and overload rules. Direct production-secure Zenoh ingress is unavailable. The figure is not implementation, release, performance, interoperability, or certification evidence." src="docs/diagrams/overview-light.svg" width="1060">
</picture>

The figure shows the proposed admission order for one typed delivery. It is the
B01 target, not the current end-to-end implementation.

1. The receiver bounds raw bytes and structure before semantic allocation.
2. The receiver binds the verified transport principal to the installed manifest,
   audience, route, and security profile.
3. The receiver requires a canonical same-major wire and the exact stable-core
   identity.
4. The receiver checks the live session generation, stream epoch, position,
   lease, deadline, and no-reuse state.
5. The receiver uses a prepared layout and a finite plane-specific queue before
   it calls typed application code.

These five gates apply to every frame. An action frame also passes the sixth,
body-owned effect predicate before software admission can succeed.

The Control plane rejects overflow. The Perception plane replaces the latest
item and exposes loss. The Observation plane drops the oldest item and counts
gaps. The Action plane preserves fail-safe severity and terminates at the body
effect gate. The body remains the final software authority before an actuator
boundary.

NCP is a contract and a set of admission rules, libraries, and transport
bindings. It is not a central broker, an actuator, or a physical-safety
certification.

The complete proposed architecture is available in maintained
[Markdown](docs/implementation/NCP_1_0_LOW_OVERHEAD_ARCHITECTURE.md) and
[LaTeX source](docs/publication/ncp-system-design.tex). A checked
[system-design PDF](output/pdf/ncp-system-design.pdf) provides the publication
view. The report derives its
latency, memory, lifecycle, retry, queue, step, freshness, and reassembly
equations from named assumptions. It remains informative B01 material.

## What the 1.0 candidate changes

Wire 1.0 is an intentional break from 0.8. It adds authenticated principal/entity/
role/plane claims, named security profiles and digests, session generations and
stream epochs, bounded
authority leases, idempotent lifecycle operation contexts, authenticated responder
receipts, content-addressed plant profiles, closed stable capability negotiation,
universal JSON limits, and explicit channel requirements.

Four planes have distinct ownership and queue policies:

| Plane | Publisher | Key family | Queue policy |
|---|---|---|---|
| Control | commander or body | `{realm}/rpc/{request_kind}` | bounded; reject overflow |
| Perception | body | `{realm}/session/{session_id}/sensor[/{channel}]` | replace latest |
| Action | commander or operator | `{realm}/session/{session_id}/command[/{channel}]` | highest fail-safe severity: ESTOP, then HOLD/non-active, then Active; equal severity replaces latest |
| Observation | body | `{realm}/session/{session_id}/observation` | drop oldest and count |

Every typed data-plane boundary requires the live `SessionRef` returned by
`SessionOpened`, verifies that the payload `session_id` equals the concrete route,
and rejects a stale generation before callback or safety-latch mutation. Remote
ESTOP has no malformed-envelope bypass; only its authority lease may be absent after
authenticated actor/plane and exact live-session admission.

Wire 1.0 defines no stable ESTOP-reset RPC. A successful authorized body-local or
out-of-band reset is a session-generation cut: the body retires the current
generation, authority and lease, and every associated stream state, and remains
non-actuating until a fresh `SessionOpened` supplies a new generation, publishers
establish new streams, and a new matching authority lease is acquired. Local
governor or buffer reset helpers do not restore remote authority. Frames from the
retired pre-reset generation, including ESTOP, fail route/session binding before
latch or control processing.

Authority renewal authenticates both issuer and holder, requires an exact match to
the current immutable lease, and is legal only before the receiver's monotonic
deadline. Expiry moves the generation to HOLD and requires a newer acquisition;
serialized lease possession alone cannot renew. Stream expiry likewise grants no
replay exception: each declared sensor, command, or status stream remains bound to
one epoch and strictly increasing high-water mark until fresh declaration state is
created. Status sequence zero is invalid.

Zenoh is the only `stable-1.0` transport binding in the unreleased candidate.
WebSocket/JSON remains experimental. gRPC, transparent proxying, delegation,
protobuf as a runtime wire,
`BulkObservation`, and bare `NCPB` transport frames are excluded. The bounded
`BulkBlock` codec remains available only for local/offline experiments. See
[`docs/1.0-scope.md`](docs/1.0-scope.md).

The current `stable-1.0` Zenoh action wrapper owns one command epoch/sequence
allocator across
Active, HOLD, and ESTOP. An attempted put consumes its position. If fail-safe
delivery is ambiguous, Active admission stays blocked until the caller submits a
new logical fail-safe at a new position and it publishes successfully; the adapter
never busy-retries the ambiguous bytes at the old position.

The current `ncp-zenoh` adapter cannot obtain a transport-authenticated remote
principal from its callback surface and therefore cannot bind `IdentityClaim` to
the verified peer. Its `open_secure` path fails closed. The `stable-1.0`
transport shape and QoS implementation must not be confused with an available
`production-secure` adapter.

## Scientific and safety boundary

NCP transports raw simulation output and control artifacts. It does not validate a
paper reproduction, provide a calibrated posterior, certify a physical plant, or
define a universal safe action. An `ObservationFrame` must retain
`calibrated_posterior=false` and `is_simulation_output=true`.

The reference governor, command watchdog, action buffer, ESTOP latch, and plant
profile checks are deterministic software controls. A deployment still needs a
plant-owned safety case, tested safe actions, an independent hardware or plant-local
ESTOP interlock, and a transport adapter that fully implements the `production-secure`
profile. The current Zenoh adapter does not. Mode and TTL are not network security.

## Normative contract

The precedence order is:

1. [`contract/*.v1.json`](contract/) registries, explicitly excluding the derived
   `contract/manifest.v1.json` so the digest is not self-referential;
2. [`proto/ncp.proto`](proto/ncp.proto) field numbers and message shapes;
3. [`schemas/index.json`](schemas/index.json) and generated JSON Schemas;
4. [`NEURO_CYBERNETIC_PROTOCOL.md`](NEURO_CYBERNETIC_PROTOCOL.md);
5. [`conformance/manifest.v1.json`](conformance/manifest.v1.json) and its corpus.

An inconsistency is a release-blocking defect; implementations fail closed. The
Rust code and language bindings are informative implementations, not an additional
normative layer. The generated contract manifest lists and hashes the complete
normative source set; it describes that set but is not itself one of its inputs.

## Packages

| Package | Candidate role | Independence |
|---|---|---|
| [`ncp-core`](ncp-core/) | Rust reference types, validators, limits, authority, idempotency, safety | reference |
| [`ncp-zenoh`](ncp-zenoh/) | `stable-1.0` Zenoh wire/QoS binding. Production peer-identity binding unavailable. | Rust reference |
| [`@sepahead/ncp`](ncp-ts/) | independent TypeScript validator/client and experimental WebSocket binding | independent decision code; live external certification **NOT RUN** |
| [`ncp-python`](ncp-python/) | Python/PyO3 interface | Rust FFI, not independent |
| [`ncp-cpp`](ncp-cpp/) | C ABI and C++ header | Rust FFI, not independent |
| [`ncp-gateway`](ncp-gateway/) | same-wire Rust-to-Python lifecycle edge | requires a native wire-1.0 `SessionService`; not the 0.8 migration gateway |

All manifests currently identify `1.0.0-rc.1`. These artifacts are candidates and
have not been published. The 0.8-to-1.0 translator is a separate, labeled,
authenticated terminating-gateway API in `ncp-core::migration`; it rejects any
mapping that would require inventing identity, authority, security, plant, or
channel-requirement context.

Every package exposes coordinated package/wire/contract identity. Rust exports
`PACKAGE_VERSION`, `NCP_VERSION`, `CONTRACT_HASH`,
`NORMATIVE_CONTRACT_DIGEST`, and `BUILD_IDENTITY`; TypeScript and Python expose the
same concepts, the C ABI provides owned-string accessors, and
`ncp-gateway --identity-json` reports them without opening a transport. The
checked-in RC build identity is `unreleased-worktree`: it is a deliberate
non-certifying sentinel, not a source revision or release provenance claim.

## Build and verify

Required local tools are Rust 1.88+, Python 3.11+, Node.js 18+, a C++17 compiler,
Bun, npm, Buf, `cargo-deny` 0.19.9, `latexmk`, `rsvg-convert`, and the Poppler
PDF tools. The LaTeX installation must provide the packages imported by the
maintained system-design report. The complete gate invokes Bun and npm. Hosted
CI pins Node.js 24.18.0 and Bun 1.3.14. One hosted syntax-only replay uses
Node.js 26.3.0, then restores Node.js 24.18.0. The complete gate reproduces the
system-design PDF and compares its rendered content across publication
toolchains. Maintainers also require byte identity on the publication toolchain.

```bash
scripts/check.sh
```

The complete gate formats and lints the workspace, builds/tests Rust, builds and
installs the Python wheel, compiles the C/C++ demo, regenerates and tests
TypeScript, replays the mandatory corpus, checks proto/schema/baseline parity,
replays independent Rust/Python security-state and plant-profile digest vectors,
validates security and plant profiles, checks package archives, runs dependency
policy, lints/builds protobuf, and either compares it with the latest verified
same-major release or explicitly reports that an initial major has no released
baseline.

Useful focused commands:

```bash
cargo test -p ncp-core --all-features
bun run check:behavior
python3 scripts/check_conformance_vectors.py
python3 scripts/generate_conformance_manifest.py
python3 scripts/generate_contract_manifest.py
python3 scripts/check_profile_digests.py
python3 scripts/check_released_baselines.py
python3 scripts/check_buf_breaking.py --self-test
python3 scripts/check_buf_breaking.py
python3 scripts/check_wire_baseline.py
python3 scripts/check_release_gates.py --self-test
python3 scripts/check_markdown_links.py --self-test
```

Local green tests do not satisfy the external pre-release gates. A transport-visible
authenticated-principal binding must first be implemented before the live
mTLS/ACL/certificate rotation and revocation campaign can run. Two independently
installed non-Rust peers, fault/soak, duration fuzzing and sanitizers, performance
qualification, signed SBOM/provenance, and clean-room reproduction remain
required. All nine exact consumer and extension role qualifications are also
required. These gates are explicitly **NOT RUN** for this candidate. Publication
follows those gates. The separate post-publication checks validate the published
artifacts and cannot be prerequisites for their own publication.

## Downstream compatibility

The candidate registry retains a historical six-surface handoff inventory across
five canonical consumer repositories: `Engram`, `crebain`,
`crebain-galadriel-producer`, `galadriel`, `haldir`, and `prisoma`. The producer
surface belongs to canonical Crebain; it is not a sixth repository. Release
authorization requires these nine exact role subjects:

- Engram simulation responder
- Engram plant commander
- Haldir NCP commander
- Haldir Galadriel-assessment receiver
- Galadriel NCP observer
- Galadriel raw-advisory publisher
- Crebain body
- Crebain Galadriel-producer surface
- Prisoma NCP observer

A historical surface entry is not a role receipt. Engram has an explicit local
native-1.0 migration in progress. Its installed roles and live transport are not
qualified. The other five historical handoff surfaces remain on wire 0.8. None
of the nine roles is qualified for 1.0. The frozen v0.8 Engram inventory is
historical migration input. It does not describe the mutable migration worktree.
A consumer cannot claim native 1.0 support before its exact installed role and
live-transport matrix passes.

The separately pinned PhD thesis wire-0.8 counterexample harness is auxiliary
research audit tooling. It is not an installed NCP peer, is outside the historical
handoff and role inventories, and receives no role receipt.

See [`INTEGRATING.md`](INTEGRATING.md) for the breaking migration checklist and
[`docs/0.8-current-baseline.md`](docs/0.8-current-baseline.md) for the frozen legacy
baseline.

## Documentation map

- [`NEURO_CYBERNETIC_PROTOCOL.md`](NEURO_CYBERNETIC_PROTOCOL.md): normative prose.
- [`SECURITY.md`](SECURITY.md): profiles, trust boundary, and deployment checks.
- [`RELEASE_READINESS.md`](RELEASE_READINESS.md): evidence ledger and blockers.
- [`docs/implementation/NCP_1_0_LOW_OVERHEAD_ARCHITECTURE.md`](docs/implementation/NCP_1_0_LOW_OVERHEAD_ARCHITECTURE.md):
  non-normative B01 low-overhead runtime and ecosystem architecture recommendation,
  direct implementation gaps, and explicit later-task boundary.
- [`docs/research/authenticated-ingress-feasibility.md`](docs/research/authenticated-ingress-feasibility.md):
  non-normative B04 source review, prototype decisions, hostile matrix, and explicit
  local-versus-external evidence boundary; direct Zenoh remains fail-closed.
- [`docs/1.0-candidate-receipts.md`](docs/1.0-candidate-receipts.md): per-task local
  receipts and exact not-run acceptance gaps.
- [`evidence/audit/README.md`](evidence/audit/README.md): generated, non-normative
  threat, latent-path, and requirement-traceability audit controls.
- [`evidence/supply-chain/README.md`](evidence/supply-chain/README.md): generated
  dependency, SBOM, license, vulnerability, and provenance-policy evidence.
- [`evidence/convergence/README.md`](evidence/convergence/README.md): deterministic
  local `NO_GO` identity and explicit non-local handoff boundary.
- [`docs/handoff/README.md`](docs/handoff/README.md): separate non-normative
  standalone `T000`–`T119` and current max-effort `T000`–`T145` audit records;
  both expose guarded reviewer-comment fields and authorize no release.
- [`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md): current residual risks.
- [`VERSIONING.md`](VERSIONING.md): compatibility and release policy.
- [`CONTRIBUTING.md`](CONTRIBUTING.md): contribution workflow.
- [`DOCUMENTATION_STYLE.md`](DOCUMENTATION_STYLE.md): STE-aligned technical writing
  and documentation review rules.
- [`CHANGELOG.md`](CHANGELOG.md): candidate and historical changes.

## License and citation

NCP is dual-licensed under either [MIT](LICENSE-MIT) or
[Apache-2.0](LICENSE-APACHE) at your option. [`CITATION.cff`](CITATION.cff)
describes repository HEAD as an unreleased candidate; use the metadata from the
immutable `v0.8.0` tag when citing the latest release.
