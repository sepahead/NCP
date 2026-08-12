# Known limitations of the NCP 1.0 candidate

> This ledger describes unreleased `1.0.0-rc.1` (wire `1.0`). The immutable
> `v0.8.0` limitations are historical and remain visible in that tag and
> [`docs/0.8-current-baseline.md`](docs/0.8-current-baseline.md).

The candidate is deliberately release-blocked. None of the items below may be
hidden by a version bump, optimistic default, model review, or local-only test.

## Release-blocking evidence gaps

- **The production-secure Zenoh identity binding is not implemented.** Profile and
  ACL config validators exist, but the current callback surface does not expose a
  transport-authenticated remote principal to bind to `IdentityClaim`.
  `ZenohBus::open_secure` fails closed. A replacement binding is required before
  the still-missing live mTLS/ACL/validity/rotation/revocation campaign can run.
- **Current authority-manifest grants are plane-wide.** `PrincipalGrant` has no
  exact route, audience, frame-class, session-kind, or operation allow-list.
  Production admission needs a receiver-owned prepared context that narrows each
  authenticated principal to those installed values before typed delivery.
- **Independent live peers are missing.** TypeScript has independent validation and
  safety decisions, but live installed cross-host interoperability with two
  non-Rust implementations has not been certified. Python and C/C++ call Rust FFI
  and do not count as independent decision implementations.
- **Fault and soak certification is missing.** The queue/state primitives have
  deterministic tests; combined network/process delay, loss, duplication,
  reordering, partition, restart, slow-consumer, flood, leak, and duration evidence
  is not present.
- **Fuzz/sanitizer duration evidence is missing.** Bounded decoders and negative
  vectors are not substitutes for the required multi-language fuzz campaign.
- **Release-bound performance profiles are missing.** Historical microbenchmarks are
  informative only and are not bound to the candidate artifacts/platform matrix.
- **Installed-artifact and supply-chain evidence is missing.** Packages are RC
  manifests in a workspace. Stable publication, multi-platform clean installs,
  reproducibility, signatures, SBOM/provenance, vulnerability reports, and
  clean-room reproduction are not complete.
- **Public package namespace ownership is unresolved.** As checked on 2026-07-14,
  the intended [`ncp-core` crates.io name](https://crates.io/crates/ncp-core) and
  [`ncp` Python distribution name](https://pypi.org/project/ncp/) belong to
  unrelated projects. A not-found response for another name is not proof of
  ownership. Registry access or coordinated distribution renaming must be proven
  before publication; local archives establish packageability only.
- **No required role has completed native 1.0 qualification.** Engram has an
  explicit local native-1.0 migration in progress. The other five historical
  handoff surfaces remain on wire 0.8. Installed-artifact and live-transport
  qualification is incomplete for these exact subjects:

  - Engram simulation responder
  - Engram plant commander
  - Haldir NCP commander
  - Haldir Galadriel-assessment receiver
  - Galadriel NCP observer
  - Galadriel raw-advisory publisher
  - Crebain body
  - Crebain Galadriel-producer surface
  - Prisoma NCP observer

  The historical six-surface inventory spans five canonical consumer
  repositories and is not a role-qualification result.

## Protocol and implementation boundaries

- The normative `proto/ncp.proto` comment abbreviates the predictive-horizon bound
  as `N <= ttl_ms/horizon_dt_ms`. The receiver deadline expires inclusively, and
  the executable window clamps TTL to 60 seconds. When the clamped binary64 ratio
  remains finite, the intended bound is
  `ceil(min(ttl_ms, 60_000)/horizon_dt_ms) - 1`, capped at 65,536, for finite
  positive inputs. A non-finite ratio permits zero steps, and a future step at the
  TTL boundary is not executable. The misleading normative comment is a
  release-blocking source conflict. Correcting it changes the complete normative
  digest and must follow the dependency-gated normative promotion/rebaseline
  workflow. The current mandatory corpus also lacks the exact-expiry and
  greater-than-60-second boundary cases. Rust validation and both `ActionBuffer`
  watchdogs clamp the executable window. The TypeScript
  `maxHorizonLen` helper also computes the clamped bound. However, generic
  TypeScript `assertNcpMessage` uses uncapped `ttl_ms` for its length check. It can
  accept steps beyond 60 seconds and can accept a nonempty horizon when a tiny
  positive cadence makes the ratio non-finite. N07 implementation parity and the
  dependency-gated corpus, proto, identity, and rebaseline workflow remain open.
- `LinkMonitor::new` replaces or clamps invalid loss parameters but permits an
  arbitrarily large finite CUSUM threshold. One sequence jump evaluates at most
  256 missing samples, so a higher threshold can miss an arbitrarily large gap.
  Its received and lost counters can also saturate without a visible saturation
  state. The prepared resilience profile must reject unsupported parameters and
  preserve a restrictive bounded-work result.
- The compact 16-hex `CONTRACT_HASH` is advisory and covers canonical protobuf
  structure, not the complete normative set. Default Rust and TypeScript
  negotiation accepts any `1.x` wire and does not reject an absent or different
  compact hash. It therefore does not establish the exact stable-core identity
  required by the proposed prepared-session architecture. Release evidence must
  use the SHA-256 digest in `contract/manifest.v1.json` until the deliberate
  rebaseline selects the runtime identity.
- Standalone `SafetyGovernor::govern` normalizes an invalid input
  `stream.seq` to `1` when it constructs a HOLD or ESTOP fallback. This preserves
  the current mandatory `unstamped_active_command_holds` behavior and does not
  invent a new epoch, but the governor has no publisher allocator or stream
  high-water state. Sequence `1` is the required initial numeric value for a newly
  declared stream, but the governor neither declares nor admits that position. A
  caller must not publish that fallback into an existing stream; it must withhold
  the frame or invoke the governor with the owning publisher's next fresh
  position. `NeuroControlLoop` stamps its own position before governance.
  Resolving the standalone Rust, FFI, and TypeScript behavior requires the
  dependency-gated normative and conformance-corpus workflow. Until then, direct
  publication of a normalized fallback is an open candidate limitation.
- `SafetyGovernor::with_channels` replaces an empty command-channel set with the
  configured velocity channel. Its later fallback tiers can instead emit an
  empty channel map. Neither behavior proves the required plant channel set.
  Prepared plant admission must reject an empty required set and preserve exact
  installed channel semantics.
- The declared `max_metadata_entries=256` ceiling has no accepted message-class
  and decoded-path assignment. ADR-003 proposes applying it to each
  `OpenSession.bindings[*].entity.meta` object. Rust and TypeScript apply only the
  generic object ceiling. The Python developer reader walks any key spelled
  `meta` or `metadata` after `json.loads`. Ratification, native class/path-aware
  preallocation enforcement, rebaseline, and 256/257 cross-language vectors
  remain open. An unrelated same-named additive field must not silently acquire
  consumer-specific semantics.
- Checked codec calls can still replace missing or short sensor inputs with rate
  midpoints, replace missing decoder populations with value midpoints, zero-fill
  sparse components, and let the last mapping select a channel unit. The
  content-addressed plant helper checks exact names, arity, and range but is not
  integrated into Active admission and its `PlantCommand` projection erases
  units. These values are not neutral or safe by default. Plant-eligible Active
  output requires a reviewed correction, candidate rebaseline, unit-preserving
  installed-profile validation at the body, and new boundary vectors.
- `ncp-gateway` is a same-wire native 1.0 edge. It cannot bridge an unmigrated 0.8
  Python backend; Engram's in-progress native migration must satisfy the same
  contract, or a legacy deployment must use the separate labeled terminating
  migration gateway.
- The reviewed `ncp-zenoh` dependency profile is exactly TCP, TLS, UDP, and shared
  memory with Zenoh default features and transport compression disabled. A host
  that unifies `zenoh/default` or `zenoh/transport_compression` changes the compiled
  security surface and is outside this candidate profile.
- The root lock uses exact `zenoh-transport 1.9.0` backport revision
  `9045545b72a77602a87f40203cb614b48157b4bc`. The conditioned graph selects
  patched `lz4_flex 0.11.6`, updates its `twox-hash` dependency to `2.1.3`, and
  selects non-yanked `spin 0.9.9` and `0.10.1`. The fork's qualification lock also
  selects fixed `crossbeam-epoch 0.9.20`, `rand 0.8.6` and `0.9.4`,
  `quinn-proto 0.11.15`, `rustls-webpki 0.103.13`, and `serde_with 3.21.0`.
  The fork CI pins `cargo-deny 0.19.9` and rejects yanked lock entries and current
  RustSec vulnerabilities.
  The checker verifies the fork revision, tree, tracked files, and reviewed
  upstream delta during qualification. The receipt classifies these checks as
  point-in-time local-process attestations and does not retain the exact fork
  source bytes. Cargo does not verify Git signatures. A Cargo patch is selected by
  the graph root and does not propagate from a published library dependency.
  Without a consuming-root patch, the normalized `ncp-zenoh` and `ncp-gateway`
  source archives resolve registry `zenoh-transport 1.9.0` to advisory-affected
  `lz4_flex 0.10.0` and its `twox-hash 1.6.3` dependency. The package checker does
  not compile that fallback. It applies the exact patch only at each consuming
  test root. It runs the exact fork's `security_backport` regression and
  compression-enabled library tests. Exact resolution and fetch can use network
  access. Cargo dependency access is offline only during compile and test. The
  checker claims no host or child-process network isolation and no host filesystem
  isolation. It compares both conditioned consumer source graphs before and after
  compilation, but retains no compiler-input trace. The result is
  `CONDITIONAL_PASS`, with
  `package_self_contained=false`,
  `self_contained_distribution_gate=OPEN_FAIL_CLOSED`, `decision=NO_GO`, and
  `release_authorized=false`. A release candidate needs a qualified upstream
  source or another reviewed distribution design that preserves the fixed graph
  for installed consumers.
- The legacy translator currently specifies only explicit channel requirement
  mapping. It rejects missing/null/malformed/mixed fields and cannot invent
  identity, security, session, authority, operation, receipt, or plant context.
- WebSocket/JSON is experimental. Zenoh is the only `stable-1.0` transport binding. gRPC,
  delegation, transparent proxying, protobuf runtime wire, `BulkObservation`, and
  bare `NCPB` transport are excluded. `stable-1.0` names the selected
  wire/key/QoS surface. It does not mean that the candidate is released or that
  a `production-secure` implementation is complete.
- `BulkBlock` remains a bounded local/offline codec. It has no stable transport
  envelope and must never be published bare.
- `ZenohBus::put` currently clones each serialized payload with `to_vec()` before
  handing it to Zenoh. This is bounded and wire-neutral but prevents a true owned-
  buffer/shared-memory zero-copy action path; performance certification must measure
  the shipped copy rather than claim zero-copy.
- The reference idempotency cache is bounded and snapshot-capable, but exactly-once
  claims require server integration and durable restart evidence. If an outcome
  cannot be proved, the only valid response is `outcome_unknown`. Pending entries
  have no runtime terminalization deadline, while capacity pressure can evict a
  completed entry before its configured retention deadline. Retained lookup also
  revalidates the expired request deadline and live lease before cache access.
- `OpenSession` has no operation or idempotency context. A timeout or overlapping
  client open can create a server generation whose reply the client discards.
  The contract requires a server-issued UUIDv4, but no selected durable realm
  issuer proves generation no-reuse across process restart. Session creation
  needs one logical-session owner, reserve-once operation identity, retained
  results, and a checked generation reservation in the deliberate rebaseline.
- The reference runtime has no single body-generation owner or deployment-wide
  physical effect-path registry. Process-local ownership and a network lease do
  not exclude another realm or failover process from the same hardware path.
  The selected architecture requires one deployment fence before a plant
  generation opens. This is a software exclusivity requirement, not a physical-
  safety claim.
- Forwarded mutating control operations have no selected durable exact-byte
  outbox, and observer projection release has no source-owned order against
  revocation. A restart can otherwise create a fresh remote mutation, while a
  receiver-only grant check cannot prove whether revoked bytes already escaped.
- Wire-1.0 `ResponderReceipt` covers lifecycle step, run, and close operations. A
  `CommandFrame` has no operation context, idempotency context, applied-command
  acknowledgement, or physical-stop acknowledgement. A Zenoh put success is not
  proof of plant receipt or actuation; a put error is delivery-ambiguous. The
  adapter consumes that position and blocks Active after an ambiguous fail-safe
  until a new-position fail-safe succeeds. Any applied-command or body-boundary
  receipt is deployment-local and does not prove the resulting physical state.
- Wire 1.0 has no stable ESTOP-reset RPC. Binding-level governor/action-buffer reset
  methods are local primitives only; transport identity, operator grant, physical
  reset interlocks, full generation retirement, and fresh-session reconstruction
  remain deployment responsibilities.
- The local SHA-256 audit chain is tamper-evident only within its local trust
  boundary. It is not signed and lacks the independently anchored production log.
- Rust may preserve unknown enum strings for diagnostics or lossless relay, but
  every wire-1.0 enum except `Mode` is closed and rejects unknown values. `Mode`
  alone is open; every unknown/additive mode is non-authorizing and governed as
  HOLD.
- `max_tilt_rad` remains advisory metadata; the current action governor does not
  enforce it. A plant safety case must not assume otherwise.

## Safety and scientific non-claims

- NCP HOLD/ESTOP is a deterministic protocol control, not a certified hardware
  emergency stop. Zero is not universally safe; the plant profile owns neutral,
  shutdown, or bounded hold-last behavior.
- The body is final actuator authority. Each consumer must prove its units, channel
  arities/ranges, executor, safe action, reset interlocks, and physical hazard case.
- Raw `V_m`, spikes, rates, and controller outputs are simulation/control artifacts.
  They are not experimental recordings, paper reproductions, calibrated posterior
  samples, or proof of model validity.
- NCP has not been certified as hard real-time, safety-critical, medical, aviation,
  automotive, military, or industrial-control infrastructure.

The authoritative gate state is
[`RELEASE_READINESS.md`](RELEASE_READINESS.md). Close a limitation only with evidence
bound to the exact source, normative digest, package artifacts, configuration, and
environment that the claim names.
