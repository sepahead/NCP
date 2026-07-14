# NCP — Neuro-Cybernetic Protocol

NCP is a versioned, project-agnostic canonical-JSON contract for connecting a
neural simulator or neuromorphic controller to robots, UAVs, simulators, and
read-only analysis clients.

> **Current status:** repository HEAD is the **unreleased, release-blocked**
> `1.0.0-rc.1` candidate: wire `1.0`, compact proto contract hash
> `163acc57d8a62b66`. The latest immutable annotated source tag is `v0.8.0`; it is a
> different, incompatible wire. Do not describe this candidate as NCP 1.0,
> production-certified, published, signed, or consumer-certified.

The complete normative SHA-256 contract digest and exact source list are generated
in [`contract/manifest.v1.json`](contract/manifest.v1.json). The short 16-hex
`CONTRACT_HASH` is an advisory FNV-1a digest of the canonical protobuf structure;
it is not the complete normative digest.

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
| Perception | body | `{realm}/session/{id}/sensor[/{channel}]` | replace latest |
| Action | commander or operator | `{realm}/session/{id}/command[/{channel}]` | highest fail-safe severity: ESTOP, then HOLD/non-active, then Active; equal severity replaces latest |
| Observation | body | `{realm}/session/{id}/observation` | drop oldest and count |

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

Zenoh is the only stable 1.0 transport binding. WebSocket/JSON remains
experimental. gRPC, transparent proxying, delegation, protobuf as a runtime wire,
`BulkObservation`, and bare `NCPB` transport frames are excluded. The bounded
`BulkBlock` codec remains available only for local/offline experiments. See
[`docs/1.0-scope.md`](docs/1.0-scope.md).

The stable Zenoh action wrapper owns one command epoch/sequence allocator across
Active, HOLD, and ESTOP. An attempted put consumes its position. If fail-safe
delivery is ambiguous, Active admission stays blocked until the caller submits a
new logical fail-safe at a new position and it publishes successfully; the adapter
never busy-retries the ambiguous bytes at the old position.

The current `ncp-zenoh` adapter cannot obtain a transport-authenticated remote
principal from its callback surface and therefore cannot bind `IdentityClaim` to
the verified peer. Its `open_secure` path fails closed; the stable transport shape
and QoS implementation must not be confused with an available
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
| [`ncp-zenoh`](ncp-zenoh/) | stable Zenoh wire/QoS binding; production peer-identity binding unavailable | Rust reference |
| [`@sepahead/ncp`](ncp-ts/) | independent TypeScript validator/client and experimental WebSocket binding | independent decision code; live external certification not run |
| [`ncp-python`](ncp-python/) | Python/PyO3 interface | Rust FFI, not independent |
| [`ncp-cpp`](ncp-cpp/) | C ABI and C++ header | Rust FFI, not independent |
| [`ncp-gateway`](ncp-gateway/) | same-wire Rust-to-Python lifecycle edge | requires a native wire-1.0 `SessionService`; not the 0.8 migration gateway |

All manifests currently identify `1.0.0-rc.1`. These artifacts are candidates and
have not been published. The 0.8-to-1.0 translator is a separate, labelled,
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

Required local tools are Rust 1.88+, Python 3, a C++17 compiler, Bun/npm, Buf, and
`cargo-deny`.

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
certification, signed SBOM/provenance, clean-room reproduction, and downstream
consumer certification also remain required and are explicitly **NOT RUN** for this
candidate. Publication follows those gates; the separate post-publication install
smoke and emergency-revocation exercise then validate the published artifacts and do
not retroactively serve as prerequisites for their own publication.

## Downstream compatibility

The known consumers are Engram, crebain, crebain-galadriel-producer, galadriel,
haldir, and prisoma. Engram has an explicit local native-1.0 migration in progress,
but has not passed installed-artifact or live-transport certification; the other
five remain on wire 0.8. None is 1.0-certified. The frozen v0.8 Engram inventory is
historical migration input, not a claim about the mutable migration worktree. No
consumer may claim native 1.0 support until it passes the installed-artifact and
live-transport matrix.

See [`INTEGRATING.md`](INTEGRATING.md) for the breaking migration checklist and
[`docs/0.8-current-baseline.md`](docs/0.8-current-baseline.md) for the frozen legacy
baseline.

## Documentation map

- [`NEURO_CYBERNETIC_PROTOCOL.md`](NEURO_CYBERNETIC_PROTOCOL.md): normative prose.
- [`SECURITY.md`](SECURITY.md): profiles, trust boundary, and deployment checks.
- [`RELEASE_READINESS.md`](RELEASE_READINESS.md): evidence ledger and blockers.
- [`docs/1.0-candidate-receipts.md`](docs/1.0-candidate-receipts.md): per-task local
  receipts and exact not-run acceptance gaps.
- [`docs/handoff/README.md`](docs/handoff/README.md): separate non-normative
  standalone `T000`–`T119` and current max-effort `T000`–`T145` audit records;
  both expose guarded reviewer-comment fields and authorize no release.
- [`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md): current residual risks.
- [`VERSIONING.md`](VERSIONING.md): compatibility and release policy.
- [`CONTRIBUTING.md`](CONTRIBUTING.md): contribution workflow.
- [`CHANGELOG.md`](CHANGELOG.md): candidate and historical changes.

## License and citation

NCP is dual-licensed under either [MIT](LICENSE-MIT) or
[Apache-2.0](LICENSE-APACHE) at your option. [`CITATION.cff`](CITATION.cff)
describes repository HEAD as an unreleased candidate; use the metadata from the
immutable `v0.8.0` tag when citing the latest release.
