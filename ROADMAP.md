# NCP Roadmap

> A prioritized, honest improvement plan for the Neuro-Cybernetic Protocol (NCP)
> SDK and wire contract. It distills a deep-research review of NCP against the
> 2025–2026 agent-protocol, robotics-middleware, RL/simulation-RPC, and
> neuroscience-co-simulation landscape into pre-1.0 work. Read `RATIONALE.md` for
> why NCP exists and what it deliberately borrows; read `SECURITY.md` for the
> current threat model and its disclosed limitation. This roadmap does not repeat
> those documents — it sequences the work.

## Status: what NCP v0.x is, and is not

NCP v0.x is a versioned, transport-agnostic wire contract that serves a running
NEST point- and rate-neuron network to external robot/UAV/analysis clients over
QoS-differentiated Zenoh planes, with scientific provenance baked into every frame
(`is_simulation_output=true`, `calibrated_posterior=false`) and a safety-gated
action plane (`mode ∈ {init,active,hold,estop}`, `ttl_ms` fail-safe). It is a
**control artifact, not a validated scientific reproduction** — output is never a
paper-reproduction claim, and the provenance discriminators are mandatory and
fail-closed precisely to keep that boundary machine-checkable. It is a single
reference SDK (proto-native — `proto/ncp.proto` normative, `ncp-core` the Rust
reference implementation; Python via PyO3, TypeScript types via ts-rs, a C ABI for
C/C++) with field/type/cardinality parity guards and a shared four-surface behavior
corpus. Python/C deliberately reuse the Rust reference and independent live-transport
clients remain future work. It is **pre-1.0** (released wire `0.7`, contract
`f05e328cad20959d`; `0.7` closes precision, enum, provenance, nested-frame,
typed-error, and hostile-bulk acceptance gaps; the latest immutable release is
`v0.7.0`; earlier wires are documented in `VERSIONING.md`): the wire
may change, minor versions are treated as breaking, and the version guard fails
rather than silently coercing. NCP's contribution is a typed, provenance-first, safety-gated wire
contract — not novel control science and not the first SNN-in-the-loop robot loop
(that lineage belongs to MUSIC and the ROS-MUSIC toolchain; see "Honest positioning").

---

## P0 — Authenticate the action/command plane

**This is the #1 deployment gate, honestly disclosed in `SECURITY.md`.** The
default/open transport is unauthenticated and effectively world-writable to any
participant that can reach it; `controller_id` is self-asserted unless mTLS proves
the peer. The local `mode`/`ttl_ms` governor is
defense-in-depth, not network security.

**Landed (#7):** a complete TLS-only, mTLS-required, default-deny Zenoh router template
([`deploy/zenoh-access-control.json5`](deploy/zenoh-access-control.json5)) in which
only an authenticated commander may publish commands and observers are read-only,
plus a strict client template, safe realm renderer, concrete enablement steps, and
the DDS-Security / MAVLink-2
comparators in [`SECURITY.md`](SECURITY.md).

**Landed (hardening pass):** the ACL template is now **loadable** — it previously
used `"get"` in `messages`, which is not a valid Zenoh token, so zenohd would
reject the whole config (the mitigation read as "secured" while doing nothing).
Fixed to the correct tokens (`query` / `declare_subscriber`), clarified exact CN
matching, and added `scripts/check_acl_template.py`. The CI guard now proves the
complete TLS/default-deny shape, exact identities, RPC authority, command/sensor/
observation PUT authority, and observer read-only coverage.

- **Validate the mTLS-bound identity in a live deployment.** The remaining P0 work
  is exercising the ACL + mutual-TLS enforcement end-to-end (a perception-only
  identity is *rejected* on the action plane; only the commander succeeds), so the
  `controller_id` is *proven* by the transport rather than self-asserted. *Why:*
  this closes the textbook confused-deputy / world-writable failure class — the
  template now ships a *loadable* mechanism; only a recorded live run remains.
  `scripts/verify_acl_deployment.py` now uses authenticated observer-received
  nonces, same-plane allowed baselines, bounded denial windows, a late-delivery
  quarantine, and a separate no-certificate connection test. A successful live
  run is evidence; `--self-test` alone is not.

P0 is the gate for any deployment beyond a trusted, closed realm. Until live mTLS
enforcement is validated, the `SECURITY.md` "closed realm only" guidance stands.

---

## P0 (near-term, no wire change) — Land the three high-severity hardening fixes

[`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md) catalogs continuing adversarial audits
of the SDK (correctness, safety, robustness, overhead). The three original
**high** findings are all `safe` — local correctness fixes that change no on-wire
bytes, and each turns a current *fail-open* into the intended *fail-closed*.
**All three are now fixed** (commit `0672168`, each wire-safe and regression-tested),
alongside further `safe` fail-closed hardening (non-finite/negative safety limits,
backward-clock steps, `LinkMonitor` overflow, bounded `max_horizon_len`), and the
wire-0.6 enforcement cut then closed the replay/version gaps, and 0.7 closes the
newly found cross-language acceptance/provenance/bulk gaps. The three high items are retained
below for provenance, marked ✓ **DONE**. The remaining medium/low work is tracked in
`KNOWN_LIMITATIONS.md`.

1. **Bulk-decode OOM amplification — `bulk.rs:356` · safety · safe. ✓ DONE (`0672168`).**
   `BulkBlock::decode` previously allocated per declared column with no cumulative budget, so
   overlapping / duplicate column and name offsets let a small frame declare on the order of
   ~64,000× its own size in allocations — an observation-plane OOM denial-of-
   service. *Fix:* bound the running total of declared payload by the input length;
   a conforming block lays its columns out disjointly (`sum(data_len) <=
   bytes.len()`), so the budget rejects only amplifying blocks and accepts every
   well-formed one. A 64 MiB absolute ceiling and fallible encoder now complement
   this budget. Bare blocks are no longer accepted as observation frames.

2. **Watchdog defeated by an unbounded / non-finite `ttl_ms` —
   `safety.rs:417` (and the `+Inf` path at `safety.rs:432`) · safety · safe. ✓ DONE (`0672168`).** The
   `CommandWatchdog` deadline backstop previously trusted the wire `ttl_ms` verbatim
   (`self.ttl_s = ttl_ms.max(0.0) / 1000.0`), so a huge or `+Inf` value disables
   the staleness deadline outright — a single command can permanently pin the
   actuator "live," defeating the very fail-safe `SECURITY.md` leans on as defense-
   in-depth. *Fix:* clamp the enforced ttl to a finite documented maximum and map a
   non-finite `ttl_ms` to 0 (immediately stale). The wire still carries `ttl_ms`
   unchanged; only local enforcement is bounded.

3. **Empty position channel bypasses the geofence — `safety.rs:293` · safety ·
   safe. ✓ DONE (`0672168`).** An empty position-channel vector previously yielded `r = 0`, so a malformed or
   dropped position frame reads as "at the origin, inside the fence" instead of
   failing safe — the opposite of the adjacent `None`-channel arm, which correctly
   HOLDs. *Fix:* treat an empty position vector like a missing channel (HOLD),
   mirrored at the `horizon` look-ahead (`safety.rs:338`). This is a concrete,
   *non-adversarial* instance of the geofence-defeat risk `SECURITY.md` already
   flags for spoofed / false-data-injection sensor frames: here a merely malformed
   frame silently slips the fence.

*Why these sit beside P0 rather than under P3:* P0 above secures *who* may command;
these secure what the safety governor and bulk decoder do with a *malformed or
adversarial* frame once it is admitted. Both are prerequisites for any deployment
beyond a trusted, closed realm — but unlike the mTLS/ACL P0, these need **no live
infrastructure** to close, only the patch and a test, which is why they are the
cheapest high-value safety work available now. Wire 0.6 resolved the version/seq
gaps and the wire-0.7 release resolves per-verb RPC addressing; the remaining
items are tracked individually rather than by the retired numeric audit summary.


---

## P1 — Identity & capability negotiation

- **Replace the ad-hoc self-asserted id with a standards-grade identity.** Adopt
  W3C Decentralized Identifiers (DIDs, e.g. `did:wba`) plus verifiable credentials,
  or an explicit capability handshake, as the open-realm identity model; for a
  closed-realm v0, mTLS client certs / Zenoh auth are the pragmatic mechanism with
  DID as the open-realm path. *Why:* DID + verifiable-credential identity is the
  established alternative to reinventing an identity scheme, and reviewers measure a
  protocol on authentication-mode diversity, not on a bespoke id field.
- **Negotiate capabilities at `open_session`.** Have peers advertise and verify
  which planes they may use (perception, action, both, neither) as part of the
  control-RPC handshake, rather than implicitly trusting a connecting peer. *Why:*
  capability negotiation makes the per-plane ACL from P0 a first-class, auditable
  contract instead of an out-of-band convention.

---

## P1 — Versioning: from local guard to negotiated, pinned handshake

NCP's `check_version` correctly fails closed, and the version is now negotiated in
the two-way lifecycle handshake with typed/versioned failures.

- **Peer-negotiated handshake on the control plane. (Landed.)** `OpenSession` and
  every typed reply enforce the full pre-1.0 major/minor compatibility gate;
  incompatibility returns `ErrorFrame` rather than a fabricated success shape.
- **Pin and verify the wire-contract definition. (Landed; hardened.)**
  `ncp_core::CONTRACT_HASH` + `verify_contract` + `negotiate(version, hash)` let peers
  detect a post-agreement schema mutation; a conformance test recomputes the hash from
  the real proto so a forgotten bump fails CI. The hash is now **comment-insensitive**:
  it is FNV-1a of the *canonicalized* proto (`canonical_proto` strips comments and
  normalizes whitespace, respecting string literals) via `contract_hash_of_proto`, so a
  comment- or formatting-only edit no longer flips it — closing the spurious-rebump
  churn the `v0.2.5`/`v0.2.6` releases documented. **(v0.3.0)** the hash is now carried in
  the control-plane handshake envelope: `OpenSession`/`SessionOpened` gained a `contract_hash`
  field, the typed clients/servers call `negotiate(version, hash)`, and the shared
  corpus pins every binding to the Rust-computed contract identity.
  **(v0.4.0)** the separation of concerns was completed: `ncp_version` is the *hard
  compatibility gate*, and the contract hash is an **advisory identity signal**
  (`negotiate` returns `ContractStatus`; a mismatch is logged, not rejected) — so
  additive evolution and the consumer-neutral `package ncp.v0` rename don't break a
  version-compatible flow. `canonical_proto` is now wire-semantic: it drops
  `package`/top-level `option`, preserves syntax/imports plus structured `wire string`
  and `wire key` annotations, and makes naming changes hash-neutral. *Remaining:*
  upgrade FNV → a
  signed/cryptographic digest if the threat model needs adversarial (not just accidental)
  integrity.
- **Keep failing closed. (Hardened.)** `check_version` no longer coerces a malformed
  minor to 0 (the latent fail-open the review found): minor parsing is now as strict
  as major. *Remaining:* the documented "minor is breaking" rule + a
  backward-compatibility policy check across a future stable-major upgrade.

---

## P1 — Conformance: from parity test to a shared golden corpus

`conformance.rs` checks field-set and required-array parity between serialized Rust
messages and the JSON Schemas; `scripts/check_proto_schema_parity.py` adds the
`proto/ncp.proto` ↔ JSON Schema side (field-set + enum wire-string parity). Real
drift guards, supplemented by concrete schema validation and shared behavior vectors.

**Landed (#9):** a golden-vector corpus — JSON message vectors *and* a binary
bulk-codec vector — in [`conformance/vectors/`](conformance/vectors/), validated by
`scripts/check_conformance_vectors.py` (with a stdlib reference decoder any peer can
run); a `buf breaking` WIRE/WIRE_JSON gate against the `v0.2.0` baseline; and
[`GOVERNANCE.md`](GOVERNANCE.md) documenting the governance model + the mechanical
interop gates + the neutral-home path.

- **Behavioral outcomes across every binding. (Landed.)** Rust, Python, TypeScript,
  and C/C++ replay the same `validate`, version/hash, and safety-governor vectors;
  the dedicated Python wheel job and TS distribution job hard-gate their peers.
- **Scope it honestly.** Conformance here is implementation-vs-spec compliance, not
  interoperability (which would require multiple independent implementations
  interacting). Do not claim alignment to formal ISO/IEC 9646 / ETSI methodologies;
  a pragmatic golden-fixture corpus is the appropriate bar.

---

## P2 — Observability

- **First-class OpenTelemetry spans** across the control RPC and the data planes,
  and an **append-only run-log as the source of truth** for what was commanded,
  observed, and rejected. *Why:* the agent-protocol literature repeatedly flags
  missing/optional observability and missing result provenance as a maintainability
  failure mode; an append-only log also gives the safety governor's reject
  decisions an auditable trail.

---

## P2 — Packaging & citation

- **Dual MIT OR Apache-2.0 licensing. (Landed.)** Moved from MIT-only to the
  `MIT OR Apache-2.0` crates.io convention: `LICENSE` → `LICENSE-MIT`, added
  `LICENSE-APACHE`, and updated `Cargo.toml`, `package.json`, `CITATION.cff`, and
  the README. *Why:* it is the Rust-ecosystem norm and removes a friction point for
  downstream adoption.
- **PyPI wheels via maturin.** Build the PyO3 binding into wheels (consider `abi3`
  so one wheel covers CPython 3.8+ per platform) and add a `pyproject.toml`. *Why:*
  maturin is the canonical PyO3-to-PyPI path; a published wheel is table stakes for
  the Python peer to be usable without a Rust toolchain.
- **Zenodo DOI via the GitHub–Zenodo archive.** Tagged releases now exist
  (through `v0.7.0`); enable the GitHub–Zenodo integration so a release is archived
  and a DOI minted, then add it to the existing `CITATION.cff`. *Why:* a DOI is the
  minimum citable artifact; the repo currently has a `CITATION.cff` with no DOI.
- **Defer JOSS.** A JOSS submission is viable only after roughly six months of
  public history with genuine ongoing iteration, a substantial (not thin) SDK, and
  demonstrated research impact. Until then, prefer arXiv plus a robotics /
  neuromorphic workshop for the protocol write-up. *Why:* JOSS desk-rejects
  short-history "single burst of commits" repos and thin API wrappers; planning
  around the timing gate is more honest than rushing it.

---

## P3 — Performance (measure first)

- **Reduce per-frame allocation and clone churn on the hot path.** Hold a persistent
  Zenoh `Publisher`, precompute key expressions once, and avoid per-frame `String`
  / `Vec` allocation in the perception/action loops. *Why:* the data planes are the
  perpetual sub-10 ms path, and steady-state allocation is the obvious cost — but
  this is P3 deliberately: **measure before optimizing**, and do not claim latency
  leadership (a software NEST-over-Zenoh loop will not approach on-chip neuromorphic
  figures, which are task-specific demos).

- **The "measure first" gate is now met — and the verdict is "the contract is
  nearly free."** The audit added the repo's first release microbenchmark
  (`ncp-core/examples/overhead.rs`; the repo previously had none), which puts
  numbers on the per-tick SDK cost: a full control tick is **~1 µs** (CommandFrame
  serialize 248 ns / deserialize 446 ns at 215 B; SensorFrame 223 / 474 ns at
  195 B; `SafetyGovernor::govern` 140 ns; `ReflexController::step` 134 ns), with
  transport at ~0.1 ms on a Zenoh loopback (tens of µs over SHM). Against a
  20–1000 Hz control budget that is **0.003–0.1%** of the tick — NEST / in-sim
  compute dominates by orders of magnitude, so the typed-contract-plus-safety-
  governor is **not** meaningful overhead and removing NCP would not buy a faster
  loop. The performance work that remains is therefore the **`safe`,
  `overhead`-tagged items in [`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md)**, not
  a redesign. The single highest-value one: `ncp-zenoh`'s `ZenohBus::put` calls
  `payload.to_vec()` on every publish (`lib.rs:441`), copying the whole serialized
  frame and **defeating the SHM zero-copy that is already enabled** — moving the
  owned buffer into Zenoh `ZBytes` removes one full per-frame copy with no wire
  change. JSON stays the debuggable default; an opt-in *negotiated* binary control-
  frame codec (or protobuf) is worth adding only if a kHz / bandwidth-constrained
  consumer actually needs it (the additive path sketched in the `messages.rs:794`
  backlog item, mirroring how `BulkBlock` was added for observations).

---

## P2 — Real-time honesty & sizing (measured)

A benchmark sweep on NEST 3.8.0 (16 cores) put numbers on §7 of
[`NEST_REALTIME.md`](NEST_REALTIME.md): for a Brunel-style net at ~500
syn/neuron and ~13 Hz, **>=1x real time is reached only at N=10000 and only at
>=4 threads** (T=8 = 2.01x); no N>=50000 config reaches real time on 16 cores
(best N=50000 T=16 = 0.35x). A live NCP session that exceeds that budget will
silently lag wall-clock. These items make the lag honest and give the principled
mitigations. Full numbers + method in [`NEST_REALTIME.md`](NEST_REALTIME.md) and
[`PERFORMANCE.md`](PERFORMANCE.md); reproduce with `scripts/bench_realtime.py` and
`scripts/bench_overlap.py`.

- **`open_session` real-time-budget check + telemetry.** At session open, given the
  network size, `sim.chunk_ms`, and the requested control rate, estimate the
  real-time factor (or measure it from a short untimed warmup, as the benchmark
  does) and **warn / refuse-as-non-realtime** when the loop cannot keep up — then
  surface the achieved real-time factor and per-chunk wall time in `ControlStatus`
  telemetry. *Why:* the sweep shows the binding constraint is the real-time factor
  (compute vs wall), **not** the chunk size — shrinking `chunk_ms` buys latency, not
  throughput, and while compute-bound makes it worse (per-`Run()` overhead climbs).
  A session should **fail honest** (declared offline / sub-real-time) rather than
  advertise a live loop it cannot sustain. This also fits the provenance-first
  posture: a real-time claim becomes a checked discriminator, not an assumption.

- **Run transport on a native thread, off the NEST *Python* thread (GIL-grounded,
  measured).** `nest.Run()` holds the Python GIL for essentially its full duration,
  so an in-process *Python* thread overlaps transport with compute only ~1.0–1.25×.
  A **native OS thread**, however, overlaps fully — measured **1.68×** for a C
  pthread (a faithful proxy for a Rust `std::thread` / PyO3 background thread) vs
  **1.08×** for a Python thread ([`scripts/bench_gil_overlap.py`](scripts/bench_gil_overlap.py)).
  So run the per-tick transport (CommandFrame/SensorFrame serialization + Zenoh RTT)
  on a native thread: either the **Rust gateway / a separate process** (recommended —
  also isolates the loop from Python GC jitter) or an **in-process PyO3 background
  thread**. (Releasing the GIL inside PyNEST via Cython `with nogil` would also work,
  but requires an upstream NEST patch.) *Why:* this is the configuration in which
  transport I/O actually overlaps compute; it codifies that the NEST kernel and the
  transport stack must not share the *Python* thread — not merely the interpreter.

- **`CommandFrame.horizon` + `ttl_ms` HOLD as the principled real-time mitigation.**
  When the real-time budget cannot be met (or the link drops), the actuator replays
  the predictive `horizon` setpoints — each entry expiring at its own
  `t + i·horizon_dt_ms`, capped by `ttl_ms`, then **HOLD fires** (the `ActionBuffer`
  / `CommandWatchdog` in `ncp-core::safety`; see [`RESILIENCE.md`](RESILIENCE.md)).
  *Why:* this is exactly the lever for the sub-real-time / lagging-loop regime the
  sweep exposes — predictive lookahead buys `N · horizon_dt_ms` of ride-through, and
  a bounded HOLD is the honest fail-safe when the brain cannot keep pace, rather than
  pretending a stale command is current.

- **Distributed / MPI-NEST as the path to bigger live brains.** The sweep was
  OpenMP-only, single MPI rank; memory was never the limiter (~5 GB at 100M
  synapses) — **compute/wall time was**, and it degrades ~linearly with synapse
  count. *Why:* the only way to push the ~10k–20k-neuron live ceiling materially
  higher is MPI scale-out across ranks/nodes (or lower indegree). NCP serving a
  multi-rank NEST kernel is the natural growth path; document it as the route to
  larger real-time brains rather than implying single-node scales indefinitely.

- **Sensible default `local_num_threads`.** Default the NEST backend toward the
  **4–8 thread band**, not 1 and not blindly 16. *Why:* efficiency peaked there
  (super-linear, cache-driven — N=50000 T=8 efficiency ~1.12) and collapsed to ~0.66
  at T=16; 1 thread leaves >6x on the table and all-16 wastes ~30–35% to
  memory-bandwidth/synchronization contention. A measured default beats an arbitrary
  one. (Expose it; do not hard-code — the right value is hardware-dependent.)

---

## Future direction: simulator-agnosticism (a second backend)

NCP's wire is **simulator-agnostic by design, NEST-implemented in fact.** The
typed record/stimulus vocabulary (`V_m`, `spikes`, `rate`, `weight`, `current_pA`,
`rate_hz`, `spike_times`) are abstract spiking-network concepts, **not** NEST APIs;
each `SimulationBackend` maps them to its simulator (NEST `V_m` ↔ NEURON `v`,
`current_pA` ↔ NEURON `IClamp`, `spikes` ↔ NEURON `NetCon`). The simulator-specific
long tail — model recordables (`g_ex`, `S`), connection params (siegert
`drift_factor`/`diffusion_factor`) — rides the generic `recordables[]` / `params{}`
escape hatches (#10), which the backend resolves. The only NEST-shaped leakage is
in free strings the backend owns, not the typed wire.

**This costs the NEST path nothing.** Adding a NEURON / Brian2 / GeNN /
neuromorphic backend is a *new `SimulationBackend` implementation* in the host
simulation service (the seam is the backend abstraction, not the wire), **not a wire
change** — it cannot slow or degrade NEST. NEST is the reference and only implemented backend today, so
simulator-agnosticism is a **designed property, not yet a shipped one**: no second
backend exists. When one lands, the points to abstract are `NetworkRefKind::Builtin`
(a NEST model name) and the recordable-string conventions, and the `VERSIONING.md`
promotion rule applies (a recordable common across simulators graduates to a typed
enum variant, additively).

## #10 neuron-family coverage (landed in v0.2.0)

`#10` shipped in **v0.2.0** (reference backend verified on NEST 3.9), extending the
wire **additively**: `Observable.binary_state`, `StimulusKind.rate_inject`,
`RecordTarget.recordables`, `Observation.recordable`, `StimulusTarget.params` —
covering conductance (`g_ex`/`g_in`/`w`), rate models, and binary state via a
generic named-recordable + named-param mechanism, wired in the reference backend via
NEST `multimeter`/`step_rate_generator`/`spin_detector`. The wire `ncp_version` was
bumped `0.1`→`0.2`, so the version guard fires on the new enum values — an old `0.1`
peer is fail-closed rejected rather than silently dropping a frame carrying
`binary_state`/`rate_inject`, and
downstream consumers re-pin to `tag=v0.2.0` to speak the new wire.

**Remaining:** niche driving (binary `noise_generator`, siegert
`diffusion_connection`) needs a driver-neuron topology. Observation-plane seq
stamping landed in wire 0.6, and lossless unknown-enum preservation landed in the
wire-0.7 release.

## #6 bulk observation codec (landed in v0.2.0)

`ncp-core::bulk::BulkBlock` is a bounded, parse-free packed column codec, roughly
2× smaller than repeated doubles and byte-pinned by a binary conformance vector.
It is currently local/offline only. The proto reserves a complete `BulkObservation`
envelope, but no peer may transport it until negotiated encode/decode/conformance
ships in every SDK. JSON `ObservationFrame` is the only shipped representation.

## Honest positioning

NCP's closed-loop spiking-neural / NEST-in-the-loop story is **not** a new control
science result and **not** the first SNN-robot loop. Prior neurorobotics
middleware already did real-time simulation-to-robot closed loops — MUSIC and the
ROS-MUSIC toolchain established the continuous/event channel taxonomy and a
NEST-to-robot loop, and the HBP Neurorobotics Platform generalized the data-model
side. NCP's actual, defensible contribution is a **typed, provenance-first,
safety-gated wire contract with a conformance program** that complements (does not
replace) that neuroscience middleware and ROS 2 / DDS robotics middleware. Any
write-up must frame it that way, keep the provenance discriminators mandatory and
conformance-checked, and explicitly disclaim that NCP output is a control artifact,
never a validated neuroscientific reproduction.

---

## Non-goals (for now)

- **Multi-commander / federation.** Coordinating multiple simultaneous commanders,
  cross-realm federation, and multi-writer "who-steps-when" arbitration are deferred
  past 1.0; v0.x assumes a single controlling authority per realm.
- **Not a substitute for network security.** Even with the P0 work landed, NCP's
  safety governor and ACLs are defense-in-depth on top of a properly secured
  realm — they are not, and will not claim to be, a replacement for network-level
  authentication and isolation.
