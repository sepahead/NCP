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
- **The locked Zenoh graph contains an unresolved transitive advisory.** Zenoh
  1.9.0 requires `lz4_flex` 0.10.0, affected by `RUSTSEC-2026-0041`, and cannot
  select a patched compatible release. NCP disables Zenoh defaults and
  `transport_compression`, which keeps the affected block-decompression call out
  of the resolved workspace build and is checked mechanically. The package is
  still present, downstream feature unification can re-enable the path, and no
  stable publication may proceed until Zenoh permits a patched dependency and the
  waiver is removed.
- **No known consumer has completed native 1.0 certification.** Engram has an
  explicit local native-1.0 migration in progress; crebain,
  crebain-galadriel-producer, galadriel, haldir, and prisoma remain wire 0.8.
  Installed-artifact and live-transport certification are incomplete for all six.

## Protocol and implementation boundaries

- The compact 16-hex `CONTRACT_HASH` is advisory and covers canonical protobuf
  structure, not the complete normative set. Release evidence must use the SHA-256
  digest in `contract/manifest.v1.json`.
- `ncp-gateway` is a same-wire native 1.0 edge. It cannot bridge an unmigrated 0.8
  Python backend; Engram's in-progress native migration must satisfy the same
  contract, or a legacy deployment must use the separate labelled terminating
  migration gateway.
- The reviewed `ncp-zenoh` dependency profile is exactly TCP, TLS, UDP, and shared
  memory with Zenoh default features and transport compression disabled. A host
  that unifies `zenoh/default` or `zenoh/transport_compression` changes the compiled
  security surface and is outside this candidate profile.
- The legacy translator currently specifies only explicit channel requirement
  mapping. It rejects missing/null/malformed/mixed fields and cannot invent
  identity, security, session, authority, operation, receipt, or plant context.
- WebSocket/JSON is experimental. Zenoh is the only stable transport binding. gRPC,
  delegation, transparent proxying, protobuf runtime wire, `BulkObservation`, and
  bare `NCPB` transport are excluded. Stable here names the canonical wire/key/QoS
  binding, not a completed `production-secure` implementation.
- `BulkBlock` remains a bounded local/offline codec. It has no stable transport
  envelope and must never be published bare.
- `ZenohBus::put` currently clones each serialized payload with `to_vec()` before
  handing it to Zenoh. This is bounded and wire-neutral but prevents a true owned-
  buffer/shared-memory zero-copy action path; performance certification must measure
  the shipped copy rather than claim zero-copy.
- The reference idempotency cache is bounded and snapshot-capable, but exactly-once
  claims require server integration and durable restart evidence. If an outcome
  cannot be proved, the only valid response is `outcome_unknown`.
- Wire 1.0 has no applied-command or physical-stop acknowledgement. A Zenoh put
  success is not proof of plant receipt or actuation; a put error is delivery-
  ambiguous. The adapter consumes that position and blocks Active after an ambiguous
  fail-safe until a new-position fail-safe succeeds, but only plant-local safety and
  a future authenticated acknowledgement can prove the resulting physical state.
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
