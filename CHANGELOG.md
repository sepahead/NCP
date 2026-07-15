# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### 1.0.0-rc.1 candidate (breaking; not released)

- Changed the wire to `1.0` and compact protobuf-structure hash to
  `163acc57d8a62b66`; added a generated complete normative SHA-256 manifest.
- Clarified realm, session generation, stream epoch, stream, plane, and route
  terminology across current candidate documentation. This changes the complete
  normative SHA-256 digest but does not change the wire-1.0 protobuf structure or
  compact hash.
- Added a non-normative standalone-handoff audit cut and reviewer-commentable
  `T000`–`T119` review ledger. All tasks remain open, release authorization remains
  false, the requested `0.9` line requires a separately reviewed normative
  rebaseline, and no DOI or Zenodo archive is assigned.
- Added a separate schema-2.0 max-effort handoff source index, updated-cut audit,
  and reviewer-commentable `T000`–`T145` review ledger. Exact guards retain all
  146 tasks and 2,920 lens reviews as `OPEN`, record the handoff's serial-DAG/wave
  contradiction and stale 268-vector claim, and preserve `NO_GO` without rewriting
  the earlier 120-task history.
- Added a reproducible 21-column file-review ledger for all 793 immutable Git blobs
  in the reviewed cut. It records the completed internal AI-assisted inspection,
  zero independent reviews, open findings, and no release authorization.
- Added deterministic local threat, latent-path, supply-chain, requirement-
  traceability, and convergence artifacts. The generated controls retain OPEN and
  NOT-RUN states and cannot turn repository inspection into release authorization.
- Added an exact 14-vector canonical-JSON matrix across all 16 ordered Rust,
  TypeScript, Python-FFI, and C-FFI surface pairs, plus a schema-discovered proof
  for every reachable TypeScript stable-integer path. The FFI rows are explicitly
  Rust wrappers rather than independent implementations.
- Added a bounded validation-only wire-0.8 capture migration path that rejects
  missing units, frames, session lineage, authority, epistemic status, or stream
  continuity instead of guessing a native-1.0 reconstruction.
- Added deterministic CycloneDX 1.6, dependency/feature/generator/asset, license,
  vulnerability, and provenance-policy evidence, plus a manual held-dossier
  workflow for exact-revision double builds, checksums, and hosted attestations.
  The workflow cannot tag or publish and does not satisfy any external gate until
  one immutable final artifact set is actually built and independently verified.
- Made the tag-triggered packaging workflow fail before archive construction while
  `release_allowed=false`, and renamed `scripts/check.sh` output as local preflight
  evidence so a green local run cannot be mistaken for external release approval.
- Bound the unresolved `RUSTSEC-2026-0041` transitive exposure to Zenoh 1.9.0's
  exact resolved feature graph. Default features and transport compression remain
  disabled, downstream feature unification is unsupported, and stable publication
  stays blocked until Zenoh permits a patched `lz4_flex`.
- Updated `anyhow` to 1.0.103, removing its resolved advisory while retaining the
  separately documented Zenoh/`lz4_flex` exposure and disabled compression path.
- Added public-registry namespace ownership as an explicit pre-release gate. Local
  archives remain packageability evidence only because the intended crates.io
  `ncp-core` and PyPI `ncp` distribution names identify unrelated projects.
- Reclassified historical performance plots and comparisons as non-normative,
  removed unmatched cross-system faster/slower claims, and made SVG generation
  deterministic with exact tool versions and strict benchmark-input validation.
- Corrected the Zenoh ACL to an exact default-deny source/destination flow matrix,
  concrete one-session action/data routes, and four protocol-closed RPC verbs;
  removed unused DELETE authority and added broad-selector, wildcard-publisher,
  and negative RPC-role probes. Also centralized pre-copy `ZBytes` frame admission,
  added a single-fault missing-authority CloseSession vector, pinned Buf remote
  generator versions/revisions, and regenerated current-wire diagrams. These are
  local candidate improvements; live security and other external acceptance gates
  remain **NOT RUN**.
- Added closed identity/role/plane claims, named security profiles and digests,
  session-bound authority leases, idempotent mutation contexts, authenticated
  responder receipts, plant profiles, stable capability negotiation, and explicit
  channel requirements.
- Added one universal bounded-JSON policy, four-plane queue semantics, audit/event
  registries, a mandatory self-describing exact-set corpus, and an independent
  TypeScript validator/client.
- Corrected the plane registry to expose named sensor/command routes but only one
  exact observation route, and made action overflow explicitly retain the highest
  fail-safe severity (`ESTOP` over HOLD/non-active over Active) with equal-severity
  latest-wins replacement.
- Split the machine release policy into required pre-release gates and non-blocking
  post-publication validations, adding the missing performance/resource profile and
  structural regression checks for both phases.
- Upgraded the candidate Markdown gate to verify same-file and cross-file
  GitHub-style heading anchors, duplicate-heading suffixes, explicit HTML anchors,
  and non-ignored untracked candidate documents.
- Reconciled current documentation with Engram's explicit in-progress native-1.0
  migration without treating it as installed/live certification, and time-bounded
  the earlier dirty-worktree receipts that migration and later normative edits
  superseded.
- Qualified NEST recorder-drain complexity and chunk/RNG invariance, separated Zenoh
  wire DROP from adapter-side replacement, and made clear that physical-chip output
  needs a future provenance discriminator rather than a false simulation label.
- Made `ErrorFrame.code` required and closed over the error registry. Missing or
  unknown codes fail validation; generic malformed-message RPC failures use
  `NCP-WIRE-001`, contained implementation failures use `NCP-INTERNAL-001`, and
  diagnostics no longer substitute for machine-readable classification.
- Corrected lifecycle correlation across the Rust and independent TypeScript
  validators: nested step/run stimuli now match the outer generation, session IDs
  use the 64-byte UTF-8 ceiling, successful receipts require `succeeded`, error
  receipts require `rejected`/`cancelled` plus the exact session pair, and the typed
  Zenoh client fences replies by generation, operation ID, and request digest.
  Generated schemas now require every `SessionRef` and `StreamPosition` identity
  member. This is a wire-1.0 candidate correction with an updated complete
  normative digest; it does not change the protobuf structure/compact hash or
  release/certify the candidate.
- Added package, wire, compact-proto, complete-contract, and non-certifying build
  identity introspection across Rust, TypeScript, Python, C/C++, and the gateway.
  The checked-in RC reports `unreleased-worktree`; it is not a source revision.
- Froze the wire-1.0 JSON candidate baseline at `conformance/baseline/v1.0.0` and
  added exact/current and additive-compatibility verification. This is an audit
  snapshot only; it is not a tag or release claim.
- Added a read-only released-baseline registry and gate that binds the annotated
  tag object, peeled commit, fixed path, and exact Git subtree for every frozen
  `v0.5.0`–`v0.8.0` baseline. Missing, extra, changed, symlinked, or moved content
  and missing, moved, or lightweight tags fail; this is an integrity check, not a
  new release, signature, or artifact-certification claim.
- Replaced the stale Buf comparison to `v0.7.0` with a registry-derived same-major
  gate. The initial `ncp.v1` candidate explicitly has no released v1 baseline and
  is never compared with intentionally incompatible `ncp.v0`; after a v1 release is
  registered, later v1 work compares with the latest verified annotated release's
  peeled commit. Deterministic hostile tests reject malformed, moved, reordered,
  mismatched, or symlinked registry/tag/proto inputs.
- The complete local `scripts/check.sh` matrix passed for the current dirty
  candidate snapshot on 2026-07-14, including five clean Rust package archives,
  an installed abi3 wheel, root/nested npm tarballs, the C++ demo, real local TCP
  Zenoh tests, bounded pure-Python JSONL ingress, dependency policy, and Buf. The
  run was a dirty, uncommitted worktree and is therefore time-bound preflight, not
  immutable release evidence; external pre-release gates remain not run and
  release-blocking.
- Closed every operational enum except `Mode`; unknown modes retain their exact
  string for relay but never authorize actuation and govern as HOLD. Unknown model,
  channel, stimulus, observation, simulation, role, or requirement values now fail
  at their semantic use sites across Rust, TypeScript, schemas, and hostile corpus
  cases.
- Bounded reply admission before owned allocation in local and Zenoh Rust RPC paths,
  the browser WebSocket client, gateway bridge, and the dependency-free PyNEST E2E
  client. Oversized transport diagnostics are prefix-bounded and preserve the
  stable `NCP-LIMIT-001` classification.
- Removed the Engram-specific default WebSocket URL from the TypeScript package;
  callers must supply a deployment endpoint. Binary browser replies are rejected
  without conversion, and outer UTF-8 byte counting no longer creates a duplicate
  `TextEncoder` allocation.
- Advanced the locked transitive `spin` 0.9.8/0.10.0 releases immediately after
  upstream yanked those lines to the non-yanked compatible replacements
  0.9.9/0.10.1; no advisory waiver or source fork was introduced.
- Closed the final Zenoh queue-policy drift: control admission now uses the
  normative 128-request ceiling, and typed observation subscriptions use an
  explicit 64-frame drop-oldest queue with a cumulative low-cardinality counter.
- Bound typed Zenoh perception and action payloads to the exact `session_id`
  encoded in their publish/subscribe key, including same-session enforcement for
  ESTOP, and added cross-session publish and raw-bypass subscriber regressions.
- Made authority renewal issuer- and holder-authenticated and legal only while the
  existing receiver-local monotonic deadline is strictly unexpired. Expired renewal
  fails to HOLD and requires a newer acquisition; serialized lease possession alone
  no longer renews authority.
- Made ESTOP reset a real generation retirement in the reference state: the old
  `AuthorityMachine` closes permanently and the old `ActionBuffer` retires. Neither
  can reopen, reacquire, renew, reconnect, or reactivate; fresh `SessionOpened`
  state is required. Python adds `ActionBuffer.is_retired()`, and the C ABI adds
  `ncp_action_buffer_is_retired`.
- Removed all expiry-based stream re-anchoring. Watchdogs, action buffers, and the
  reference loop bind one declaration to one epoch/high-water forever; lower/equal
  positions and foreign epochs remain rejected after expiry, and restart requires a
  fresh declaration.
- Required positive own-stream positions for `ControlStatus` and `LinkStatus`, made
  the reference loop publish 1..2^53−1 without repeating the maximum, and enforced
  `LinkStatus.observed_stream`/`last_arrival_seq` joint presence and high-water
  coherence in Rust and TypeScript.
- Changed `ControlTransport::send_command` to return `CommandSendOutcome` so the loop
  distinguishes accepted slots, prepublication replacement, and rejection without
  falsely advancing its caller-side position.
- Reworked `ZenohControlTransport` around one transport-owned action epoch/sequence
  allocator shared by Active, HOLD, and ESTOP. An attempted put consumes its
  position. Ambiguous fail-safe delivery latches Active rejection until a newly
  submitted fail-safe at a new position succeeds; exact-byte/position busy retry is
  forbidden, and `fail_safe_delivery_pending()` exposes the state.
- Routed C/C++ `ncp_validate` through the canonical bounded-JSON preflight before
  generic deserialization, including oversized, depth/node-budget, and duplicate
  top-level-key regressions.
- Corrected the secure-adapter boundary: TLS/ACL config validation cannot bind an
  `IdentityClaim` when the current Zenoh callback surface exposes no authenticated
  peer principal. `ZenohBus::open_secure` now fails closed before transport open;
  configuration fixtures and local tests are not production-security evidence.
- Added an explicit authenticated terminating 0.8→1.0 translation API. Ambiguous or
  context-free legacy inputs fail closed; `ncp-gateway` remains a same-wire native
  lifecycle edge and is not the migration translator.
- Excluded bare `NCPB`, `BulkObservation`, protobuf runtime transport, gRPC,
  delegation, and transparent proxying from stable 1.0.
- Kept the candidate release-blocked pending live security, two independent
  installed non-Rust peers, fault/soak, fuzz/sanitizer, performance, supply-chain,
  clean-room, and all six consumer-certification pre-release gates. Publication
  follows those gates; install and emergency-revocation validation follow
  publication.

## [0.8.0] - 2026-07-12

### Wire 0.8 (breaking)

The `v0.8.0` release speaks wire `0.8` with contract hash `d1b50a2d8a265276`. It
replaces the overloaded top-level `seq` with typed stream identity and source
correlation, fences session incarnations, and requires session identity on the
control plane. Its frozen JSON baseline (`conformance/baseline/v0.8.0/`),
cross-language release gates, and coordinated consumer pins establish it as the
latest immutable release. This is increment 1 of the wire-0.8 line
(see `docs/wire-0.8-stream-identity.md`); authority leasing (F-02), `publisher_id`
binding, and applied-command/stop acknowledgements are deferred to later increments.

#### Changed (wire contract and addressing)

- The single top-level `seq` — overloaded as an origin delivery sequence on
  `SensorFrame` but a source echo on `CommandFrame` / plane `ObservationFrame`,
  which `LinkMonitor`/`ActionBuffer` then misread as delivery loss (F-01) — is
  deleted and `reserved` (number **and** name) on every data-plane frame. There is
  no 0.8 alias.
- Every data-plane frame carries `stream: StreamPosition {epoch, seq}`: `epoch` is
  an opaque per-incarnation UUIDv4 (equality-only, unordered), `seq` starts at 1
  per epoch and strictly increases. `stream` is the **only** sequence read for loss
  accounting, `LinkMonitor`, and `ActionBuffer`.
- `source: StreamPosition` carries the directly-driving frame's `{epoch, seq}` for
  correlation/provenance only (never loss accounting). `source` **absence** replaces
  the old observation `seq == 0` sentinel; `command.source` is scoped to the
  enclosing frame's session, and cross-session source references are invalid.
- A server-issued `session: SessionRef {generation}` is issued on
  `SessionOpened(ok=true)` and required on every post-open session-scoped frame
  (Step/Run/Close/SessionClosed/Stimulus and the data plane), conditional on
  `ErrorFrame` (both or neither). The effective session identity is the inseparable
  pair `(session_id, generation)`, validated atomically under the session lock
  **before any side effect**, with no key→`session_id` or active→`generation` repair.
- `session_id` is now **required on the control plane** (`SensorFrame`,
  `CommandFrame`, `ControlStatus`) for transport-agnosticism: the normative gRPC
  `Control` stream has no Zenoh key to recover identity from, so the frame is
  self-describing and the Zenoh key becomes a redundant equality-checked binding.
- `t` is uniformly this publisher's local monotonic creation time scoped to
  `stream.epoch`; the driving sensor's time travels explicitly in optional
  `source_t`. No frame smuggles another peer's clock into `t`.
- `LinkStatus` reports the monitored stream's `observed_stream` (`{active epoch,
  forward high-water seq}`), its own `stream`, and `session`; `last_arrival_seq`
  is optional. Reorder/duplicate diagnostic counters are deferred until a bounded
  reorder window is normatively fixed.

#### Safety and robustness

- Receivers key stream state by `(session generation + authenticated publisher +
  routing key + message kind)` and keep `active_epoch`/`last_seq`/`retired_epochs`.
  A foreign random epoch cannot auto-replace the active stream (the foreign-epoch
  hijack is closed); a retired epoch is rejected even with a large seq; a duplicate
  or stale `seq` never refreshes the command watchdog.
- Session fencing rejects stale-generation and wrong-`session_id` traffic before any
  stimulus, advance, close, TTL refresh, epoch/seq state change, mode change, or
  ESTOP latch — a wrong-session ESTOP does not latch.

### Migration

Consumers re-pin to `v0.8.0` and move every `.seq` join to the typed
`stream`/`source` `{epoch, seq}` (observers correlate on `source`; bodies stamp
`stream`, copy `source`, and carry `session_id`/`session.generation`). See
`docs/wire-0.8-stream-identity.md` §11.

## [0.7.1] - 2026-07-11

Wire `0.7` and `CONTRACT_HASH=f05e328cad20959d` are unchanged from `v0.7.0`.
This patch replaces no tag: `v0.7.0` remains immutable.

### Fixed

- Updated the one `ncp-zenoh` format invocation rejected by the mandatory Rust
  1.88 Clippy `uninlined_format_args` lint, restoring a green release gate.
- The generic consumer re-pin tool now updates an explicit Cargo dependency
  `version` constraint together with its Git `tag`; previously a `0.6.0`
  constraint could make a correct `v0.7.0` tag fail dependency resolution.

### Changed

- Advanced the post-release Buf breaking baseline to the first wire-0.7 tag,
  `v0.7.0`, while keeping that frozen wire baseline unchanged for every 0.7 patch.

## [0.7.0] - 2026-07-11

### Wire 0.7 (breaking)

The `v0.7.0` release speaks wire `0.7` with contract hash
`f05e328cad20959d`. Its frozen JSON baseline, cross-language release gates, and
coordinated consumer pins establish it as the latest immutable release.

#### Changed (wire contract and addressing)

- Lifecycle RPC requests use exact transport keys
  `{realm}/rpc/{request_kind}` (`open_session`, `step_request`, `run_request`,
  `close_session`); servers declare `{realm}/rpc/*`. Structured `wire key`
  annotations now participate in `CONTRACT_HASH`, allowing per-verb transport ACLs.
- Every JSON `int64` value is restricted to ±(2^53−1), preventing Rust/C/Python
  peers from accepting values a JavaScript peer rounds to different bytes. The
  validators also agree with JSON Schema/JavaScript that integral spellings such
  as `1.0` and `1e0` are integers, while fractions remain invalid.
- Wire-version components share one exact grammar in every SDK: one or two
  unsigned ASCII-decimal `u64` components, with no sign, whitespace, patch, or
  overflow. TypeScript uses `BigInt` so it does not impose an accidental 2^53
  parser limit that Rust/Python/C++ lack.
- Rust preserves unknown non-empty enum strings for diagnostics and lossless relay,
  but all wire enums except `Mode` are closed at semantic ingress. `Mode` alone is
  same-major extensible: only exact `mode="active"` grants actuation, and every
  unknown/additive mode is governed as HOLD. Rust also rejects
  programmatic `Mode::Unknown("active")` collisions before validation or
  serialization, so an in-memory non-authority cannot canonicalize into authority.
- `kind`, nested stimulus identity, complete successful-session provenance, and
  explicit scientific-boundary assertions are enforced rather than fabricated.
- RPC failures are typed/versioned `ErrorFrame`s, and clients verify reply session
  identity before accepting a success.
- Observation maps are keyed by a unique series name, while each nested
  `Observation.port` retains the negotiated port. Multiple recordables from one
  port are therefore representable without collisions.
- `SessionOpened` success/failure fields are internally consistent: successful
  replies require matching top-level/provenance backends and no error; failures
  require an explanation and carry no success provenance.
- Envelope timestamps are now unambiguous: `t` is producer-local monotonic
  seconds, `seq` is the cross-plane join key, and `sim_time_ms` / observation
  sample times are simulation milliseconds.

#### Safety and robustness

- Active commands require a finite positive TTL, at least one finite command
  channel, complete finite predictive steps, and finite positive horizon cadence.
  Horizons are bounded by TTL and `MAX_HORIZON_STEPS = 65_536`; enforced TTL is
  capped at 60 seconds.
- Safety-governor and ActionBuffer ingress now fail closed on malformed wire
  envelopes in Rust, Python, TypeScript, and C/C++, while an inbound ESTOP still
  latches before validation.
- Safety-limit negotiation no longer trusts the first declared channel:
  `from_capabilities` selects only canonical `pose_position` /
  `velocity_setpoint` specs and requires `vec3`, width 3, and exact `m` / `m/s`
  units when the corresponding limit is enabled. Live tick-0 and horizon values
  repeat the unit/width gate, so mislabeled or truncated vectors HOLD instead of
  understating magnitude. Rust/TS and the shared cross-language govern corpus pin
  the behavior.
- Geofence enforcement is prospective under the documented kinematic command
  model, not merely reactive: it projects the
  canonical velocity trajectory through the full TTL/horizon actuation window,
  preserves safe inward motion, and HOLDs or truncates before a crossing. An
  unsafe first future step now HOLDs the entire command because an empty horizon
  means legacy tick-0 replay, not immediate drain. TTL expires at the deadline
  (`>=`), never one scheduler tick later; sensor freshness uses the same inclusive
  boundary. Geofence projection also requires matching effective sensor/command
  coordinate frames.
- Resetting an ESTOP-latched `ActionBuffer` clears the buffered command, sequence
  anchor, and watchdog timestamp; reset alone can never revive pre-ESTOP
  actuation. Stateful buffer decisions are pinned in the shared behavior corpus.
- Every non-Active command clears `ActionBuffer` actuation before envelope/sequence
  rejection, so a duplicate or malformed HOLD cannot leave the previous Active
  horizon running. Total-silence escalation and current geofence evaluation run
  before command-mode validation, so a controller's safe HOLD cannot mask a
  collapsed link or an already-breached boundary and suppress ESTOP.
- `CommandWatchdog` retains a local clock high-water mark: a backward/non-finite
  step revokes authority until time catches up **and a fresh command arrives**;
  merely reaching the old timestamp cannot revive a stale setpoint.
- `NeuroControlLoop` rejects invalid sensors/rates, does not step a controller on
  stale input, resets it on a sensor epoch restart, contains controller panics,
  detects cross-tick and mid-tick clock reversal, echoes sensor seq/t/frame, and
  normalizes TTL before geofence projection. It publishes no action before a
  truthful stamped sensor exists and never turns invalid output into actuation.
- `LinkMonitor` rejects unstamped/precision-unsafe sequence values, uses an
  inclusive CUSUM threshold, and caps JSON counters.
- Bulk encoding/decoding is fallible and bounded: duplicate/control-character
  names, non-zero padding, overlapping regions, conflicting payload columns,
  type-confused observation columns, non-finite reconstructed data, unchecked
  narrowing, and allocation amplification are rejected. Directory width is
  capped at 4,096 columns and region overlap validation is `O(n log n)`, closing
  the former pairwise-parser CPU amplification path.
- `CodecSpec::encode_checked` / `decode_checked` validate complete wire frames,
  finite monotonic ranges, supported rate/readout modes, unique mappings, safe
  neuron counts, and bounded component counts; bindings expose the checked path
  instead of silently encoding invalid inputs.
- Bare NCPB blocks are no longer accepted as observation frames. `BulkBlock`
  remains a golden-vector-pinned local/offline codec until a complete negotiated
  `BulkObservation` implementation ships in every SDK.

#### Security and deployment

- Realms are validated segment-by-segment; `Keys::try_new`, transport boundaries,
  and `ncp-gateway` reject wildcard/empty/control-character realm injection,
  including the invisible JavaScript-whitespace BOM (`U+FEFF`).
- The validated realm is immutable after construction, and fallible session/entity
  key builders let every wire-facing path reject key injection without panicking.
- The secure deployment assets now distinguish a complete mTLS/default-deny router
  (`deploy/zenoh-access-control.json5`) from strict peer clients
  (`deploy/zenoh-client-secure.json5`), with a safe exact-realm renderer.
- `ZenohBus::open_secure` requires client mode, TLS-only explicit endpoints, no
  listeners/discovery, CA + client credentials, and hostname verification.
- Local and Zenoh servers share one RPC boundary validator: exact selector and
  payload kind, request/reply session identity, response kind, typed error
  attribution, and handler panic containment are enforced before delivery.
- Zenoh RPC handlers execute on Tokio's blocking pool behind a 64-request cap
  covering both backend execution and reply delivery; completed tasks are reaped
  preferentially under sustained load. `serve_rpc` returns an abortable
  serve/reply task (an already executing synchronous call finishes normally),
  per-session subscriptions can be released, and closing a wrapper never closes
  a session borrowed with `from_session`.
- Generated JSON Schemas no longer publish deserialize-only failure sentinels as
  defaults. Required/const fields advertise no default, invalid NaN-as-null TTL
  annotations are removed, and the legitimate optional `mode="hold"` default is
  pinned by a recursive safety guard.
- Subscriber callback panics are contained, preventing one malformed sample from
  terminating a long-lived Zenoh subscription or suppressing healthy LocalBus
  subscribers; LocalBus queryable panics become explicit errors.
- Raw and typed Zenoh RPC clients expose per-call timeouts for long step/run
  simulations, avoiding accidental conflict with the gateway's backend timeout.
- `ZenohControlTransport` uses one latest-wins command dispatcher instead of one
  spawned task per tick. The pending slot is bounded to one frame, HOLD/ESTOP
  cannot be overwritten by Active, and a failed fail-safe publish is retried
  ahead of later actuation.
- NCP-aware data-plane subscriptions validate frames before callback delivery.
  Observation publishers/subscribers also bind payload `session_id` to the
  session encoded in the transport key, closing cross-session misrouting.
- The ACL grants command/observation/RPC authority only to the authenticated
  commander, sensor publication only to the robot, and read-only aligned data-plane
  access to observers.
- The live ACL verifier proves authorization with observer-received randomized
  nonces, same-plane positive baselines, denied-delivery absence, and a no-client-
  certificate quarantine check; local `put()` success is never treated as proof.

#### Conformance and supply chain

- Proto↔schema parity now checks types, cardinality, reverse coverage, nested
  required fields, enum strings, and lifecycle transport keys. The frozen-baseline
  manifest records recursive `$defs` shape for the forthcoming 0.7 snapshot.
- The shared behavior corpus exercises the stricter validation and safety outcomes
  across Rust, Python, TypeScript, and C/C++.
- CI actions are SHA-pinned with least-privilege permissions/timeouts; Bun installs
  are frozen, exact tool versions are used, and the audited dependency graph is
  refreshed.
- `scripts/check.sh` is now a complete local release gate, including isolated
  maturin wheel tests, the real C++ ABI demo, reproducible generated artifacts,
  schema/default/baseline checks, ACL proof self-tests, `cargo-deny`, and `buf`.

## [0.6.0] - 2026-07-06

**Wire 0.6 — the enforcement cut.** A **breaking** release: `NCP_VERSION` moves
`0.5 → 0.6`, so 0.5 and 0.6 peers fail closed against each other (pre-1.0 exact
`(major, minor)`). The break is **semantic, with an unchanged serialization** —
no proto field/type/encoding changed, so `CONTRACT_HASH` stays
`24e8e6e31e1dec8a`; what changed is what a conforming peer MUST send and what
receivers accept. Every pinned consumer re-pins to `v0.6.0` in lockstep.

### Changed (identity)

- **npm scope renamed `@sepehrmn/ncp` → `@sepahead/ncp`**, completing the
  `sepahead` org rename. This supersedes the earlier "keep the old scope"
  decision: the package is a git-tag import alias (never registry-published),
  and 0.6.0 already re-pins every consumer in lockstep, so the rename rides the
  same coordinated break at zero extra cost. Consumers update the dependency
  key and their `from '@sepahead/ncp'` imports when re-pinning.

### Changed (wire 0.6 — acceptance rules; breaking)

- **`ncp_version` is mandatory and value-checked on EVERY message** (closes the
  audited data-plane gap): `required_fields()` lists it for every `kind`,
  `gen-schemas` injects it into every schema's `required` plus a `const` pin,
  `validate()` rejects absent/incompatible versions, and an absent version now
  deserializes to a detectable `""` (field-level serde default) instead of
  silently defaulting to the receiver's own. Same for an absent `kind`.
- **Closed-loop seq discipline is mandatory** (removes the `seq == 0`
  always-accept escape hatch): `sensor_frame`/`command_frame` require a stamped,
  strictly-increasing `seq >= 1`; `CommandWatchdog`/`ActionBuffer` never accept
  `seq < 1` (an ESTOP still latches regardless — a fail-safe is never dropped);
  the `NeuroControlLoop` treats an unstamped sensor as absent and consumes only
  ACCEPTED frames (a replayed regression can no longer steer or be echoed).
  **Restart recovery without a wire epoch field:** a strictly-LOWER seq
  re-anchors a new stream epoch only once the stream has already expired; an
  EQUAL seq never re-anchors (no duty-cycled liveness from a frozen/replayed
  frame); the loop resets its `LinkMonitor` on an epoch re-anchor (new
  `LinkMonitor::reset`).
- **Observation-plane seq stamping is normative:** an `observation_frame`
  PUBLISHED on the observation plane must echo the driving `SensorFrame.seq`
  (`>= 1`; enforced by `ncp-zenoh::publish_observation`); `seq == 0` remains the
  pull/RPC-reply form (`validate()` allows `>= 0` for the kind; negatives
  reject).
- **`SafetyGovernor` latches on an INBOUND ESTOP command** instead of
  downgrading it to a non-latching HOLD — "a fail-safe is never dropped" now
  holds at every layer (new `inbound_estop_latches` corpus vector, replayed by
  all four language runners).

### Added

- **`ncp_core::WireFrame` + `decode_validated`** — the one-call typed data-plane
  ingress (kind check + version gate + seq bound, no `serde_json::Value`
  detour); wired into `ncp-zenoh`'s subscriber and publish gates
  (`put_sensor*`, `publish_command*` — ESTOP always passes, `publish_observation`
  — NCPB bulk blocks pass through). `ZenohNcpClient` RPC replies are now
  `validate()`d; `ZenohControlTransport::send_command` refuses to publish a
  wire-invalid frame (loud for Active, silent for the benign pre-first-sensor
  HOLD; ESTOP always publishes).
- **ncp-ts plant-side safety port** (`safety.ts`): `SafetyGovernor`,
  `CommandWatchdog`, `ActionBuffer`, `maxHorizonLen`, `assertWireFrame` — the TS
  peer now replays the FULL `govern` corpus (previously out-of-scope) plus
  seq/ttl/latch self-checks in `check-behavior.mjs`; the client hard-gates every
  reply's `ncp_version`.
- **Persistent (latching) governors in the bindings** — `ncp.Governor` (Python
  class) and `ncp_governor_new/govern/reset/is_estopped/note_link/safety_ok/free`
  (C ABI): the ESTOP latch survives across calls, which the one-shot
  `govern`/`ncp_govern` wrappers cannot provide by construction (they remain for
  stateless/corpus use, now documented as such). Latch regression tests in both
  bindings + the C++ demo.
- **`conformance/baseline/v0.6.0/`** — the frozen wire-0.6 baseline
  (`check_wire_baseline.py --freeze`).
- New behavior-corpus vectors: mandatory-version + seq-bound `validate` cases,
  wire-flip `check_version` cases, and `inbound_estop_latches` (govern).

### Fixed

- `diagnose_version` now flags an ABSENT or non-string `ncp_version` instead of
  returning `None` (the data plane can log why a version-less frame was
  dropped).
- The `ncp_validate` (C ABI) / `ncp.validate` (Python) canonical output now
  round-trips the kind-injected document, so an omitted-`kind` input yields the
  declared kind instead of a fabricated or empty one.
- Two golden vectors (`run_request.json`, `step_request.json`) carried a stale
  nested `"ncp_version": "0.2"` — now `0.6` like the rest of the corpus.
- Stale `"0.4"` version example in the `ncp_version()` C-ABI doc comment.

### Migration (consumers)

Re-pin to `tag = "v0.6.0"`, then: stamp `seq` starting at 1 on every published
`sensor_frame` (strictly increasing per stream), echo it on `command_frame`,
carry `ncp_version` on every message (SDK constructors do this), and stamp
`ObservationFrame.seq = driving sensor seq` when publishing on the observation
plane. Receivers: decode via `decode_validated` (Rust), `assertWireFrame` (TS),
`validate` (Python/C ABI). Unknown `kind`s on glob subscriptions should be
skipped before validation (additive kinds remain non-breaking). Onboarding a
NEW consumer still requires zero NCP-repo changes: pin the tag, stamp/echo seq,
carry the version, and drop a `.ncp-consumer` descriptor in YOUR repo.

## [0.5.3] - 2026-07-05

Safety-governor and link-monitor hardening plus a documentation-accuracy pass —
**no wire change**. `NCP_VERSION` stays `0.5` and `CONTRACT_HASH` stays
`24e8e6e31e1dec8a`; every fix is local (fail-closed) behaviour. Same-`0.5` peers
interoperate, so a re-pin is not strictly required — but it is how a consumer
actually *receives* these safety fixes, so re-pinning is recommended.

### Fixed (additional safety hardening, this release)

- **`ncp-core/src/resilience.rs` — `ActionBuffer::active` fail-OPEN on `mode=Init`.**
  The actuation gate was a DENYLIST (`Hold | Estop` HOLD, everything else drives),
  so an `Init` command — or any `Mode` variant added later — actuated by default.
  It is now an ALLOWLIST: only `Active` drives; every other mode fails safe to HOLD.
- **`ncp-core/src/safety.rs` — total link loss now escalates to latched ESTOP.**
  The CUSUM jam burst (`note_link`) only fires on *arriving* gappy frames, so a
  fully silent link sat in self-clearing HOLD forever. `govern` now escalates HOLD
  → latched ESTOP once total sensor silence exceeds `LINK_LOSS_ESTOP_FACTOR` (20)
  command-timeout deadlines (capped at `MAX_TTL_MS`), matching `note_link`'s stated
  intent. Wire-invisible: derived from the existing `command_timeout_ms`.
- **`ncp-core/src/safety.rs` — non-Active inbound mode normalized to HOLD.** The
  governor now returns a zeroed HOLD for any non-`Active` inbound command (defense
  in depth with the `ActionBuffer` allowlist), never forwarding an actuating
  setpoint under a non-Active mode.
- **`ncp-core/src/safety.rs` — bad `command_timeout_ms` now trips `config_fail_closed`.**
  A non-finite / non-positive timeout already forced HOLD, but `safety_ok()` still
  reported healthy; it now latches `config_fail_closed` so a misconfigured timeout
  is reported rather than silently wedged in a "healthy" HOLD.
- **`conformance/behavior/vectors.json`** gains cross-language govern vectors for the
  new behaviours (`link_collapse_escalates_estop`, `init_mode_holds`) and retunes
  `stale_sensor_holds` to a genuinely transient dropout — starting to close the
  gap that the fail-closed hardening had no cross-language conformance coverage.
- **`ncp-zenoh/examples/uav_drone_loop.rs`**: `% 10 == 0` → `.is_multiple_of(10)`
  (clean under newer clippy; `is_multiple_of` is available at the 1.88 MSRV).

### Fixed (from the prior hardening slice)

- **`ncp-core/src/safety.rs`**: a non-finite or negative `SafetyLimits` value
  (`NaN`/`±Inf`/`< 0` for `geofence_radius_m` or `max_speed_mps`) no longer
  silently *disables* enforcement. Because `NaN > 0.0` and `-5.0 > 0.0` are both
  false, the geofence/speed gates used to skip entirely (fail-OPEN); `govern` now
  latches `config_fail_closed`, HOLDs, and reports `safety_ok() == false`. `0.0`
  remains the documented "disabled" value. (`KNOWN_LIMITATIONS.md` medium ×2.)
- **`ncp-core/src/safety.rs`**: the sensor-staleness check and the
  `CommandWatchdog` deadline no longer fail OPEN on a backward (non-monotonic)
  clock step — `now_s < last` / `now_s < t` is now treated as stale/expired
  (HOLD), completing the earlier non-finite-clock guard.
- **`ncp-core/src/resilience.rs`**: `LinkMonitor` gap arithmetic (`seq - e`,
  `exp - first`) uses `saturating_sub`, so a mixed-sign extreme `seq` from a
  garbage/hostile peer can no longer overflow (debug panic / release wrap) and
  silently fail the jam detector open.
- **`ncp-core/src/resilience.rs`**: `max_horizon_len` returns `0` (no replay) for
  a non-finite `ttl_ms`/`horizon_dt_ms` instead of `usize::MAX` (from an
  `Inf as usize` saturation), so a garbage/`+Inf` ttl cannot authorise an
  effectively unbounded predictive horizon.

  All four add regression tests (`ncp-core` suite: 84 lib tests passing) and are
  `rustfmt` + `clippy -D warnings` clean; the cross-language behavior-conformance
  corpus is unaffected (its `govern` vectors all use finite, positive limits and
  forward clocks).

### Docs

- **`KNOWN_LIMITATIONS.md`**: rewritten to track each finding's **current
  status** rather than assert "none applied yet". All **3 high-severity** safety
  findings are marked resolved (commit `0672168`), plus the safety/resilience
  fixes above — **9 of 35 resolved**, 26 open (23 `safe`, 3 `wire-breaking`).
  Still-open items keep their concrete proposed fixes; the `codec` encode-fallback
  item is annotated as parity-coupled with Engram's `codec.py`.
- **`README.md`, `INTEGRATING.md`, `PERFORMANCE.md`, `RATIONALE.md`,
  `ROADMAP.md`**: corrected the stale "35 findings, none/3-high not yet applied"
  claim to reflect that the 3 high findings are fixed (9 of 35 resolved).
- **`INTEGRATING.md`**: added a worked **Engram (commander) + Prisoma (observer)**
  integration section — the RPC/version/advisory-hash policy a commander serves,
  and the real `ncp-observer` `open_realm` → `subscribe_{sensors,commands,
  observations}` → `(V,L,D,A)` (join on `seq`) → `finalize` observer flow.

## [0.5.2] - 2026-06-25

Code, CI, and documentation fixes — **no wire change**. `NCP_VERSION` stays
`0.5` and `CONTRACT_HASH` stays `24e8e6e31e1dec8a`; **`v0.5.0` remains the wire
baseline** (the `buf breaking` origin) and a `v0.5.0` peer is wire-identical to a
`v0.5.2` peer.

### Fixed

- **`ncp-cpp/examples/demo.cpp`**: the demo checked for version `"0.1"` but
  `ncp_version()` returns `"0.5"` — the pass condition was impossible and the
  demo always exited 1. Fixed to `"0.5"`. The `ncp.h` comment was stale too.
- **`ncp-core/src/keys.rs`**: key-segment validation (`debug_assert!` → `assert!`)
  is now enforced in release builds, not just debug. A caller passing a
  wildcard/slash-bearing session id (key-injection / cross-session leak) now
  panics fail-closed in every build, matching the runtime `check_id` guard
  `ncp-zenoh` already enforces at the transport boundary.
- **`ncp-python/src/lib.rs`**: docstring example showed `NCP_VERSION` as `"0.4"`;
  corrected to `"0.5"`.
- **`ncp-python/tests/test_smoke.py`**: `validate` smoke assertion was truthy-only
  (would pass on any non-empty string); now checks the canonical JSON contains
  the expected `kind` field.
- **`ROADMAP.md`**: stale release list (`v0.2.0`–`v0.2.8`) updated to
  `through v0.5.x`.

### Added

- **C++ demo smoke in CI**: `ncp-cpp/examples/demo.cpp` is now compiled and run
  in the `build-test` CI job, so a stale version string or a broken C ABI
  surface fails the gate (the demo version mismatch above shipped unnoticed
  because it was never CI'd).
- **Binding coverage notes**: `ncp-cpp/README.md` and `ncp-ts/README.md` now
  document which `ncp-core` modules are exposed through the binding and which
  are Rust-core-only, so the READMEs don't overstate the binding surface.

## [0.5.1] - 2026-06-22

Documentation, diagram, and tooling patch — **no wire change**. `NCP_VERSION` stays
`0.5` and `CONTRACT_HASH` stays `24e8e6e31e1dec8a`; **`v0.5.0` remains the wire
baseline** (the `buf breaking` origin) and a `v0.5.0` peer is wire-identical to a
`v0.5.1` peer.

### Added

- **Publication-grade performance plots** (`scripts/plot_perf.py` → `docs/plots/`): the
  real-time-factor scaling sweep and the I/O-overlap ceiling, rendered as committed
  light/dark SVGs and embedded in `PERFORMANCE.md`.

### Changed

- **Bespoke "Instrument Datasheet" SVG diagrams** replace the five Mermaid diagrams
  (topology, ecosystem, version handshake, safety FSM, session sequence) — one semantic,
  colourblind-safe design system with light/dark variants, generated by
  `scripts/gen_diagrams.py` and embedded via a `prefers-color-scheme` `<picture>`.
- **Renamed the example analysis / observer consumer to `prisoma`** throughout the docs,
  diagrams, and code comments (naming only — no wire effect; the separate `pid-rs`
  submodule, PID estimators and not an NCP consumer, is untouched).

### Fixed

- `PERFORMANCE.md` overlap-ceiling formula was inverted; corrected to
  `(compute+work)/max(compute,work)`.
- `RESILIENCE.md` safety-FSM note overstated ESTOP as latch-last; it emits a *zeroed*
  frame, matching `ncp-core/src/safety.rs`.
- `scripts/repin-ncp.sh` bash-3.2 empty-array guard; the e2e cross-language runner now
  tracks the wire version from the behavior corpus.

## [0.5.0] - 2026-06-21

The stable-wire cut. The deliberate, once-before-adoption breaking change that makes
`0.5` the baseline a stable wire is measured against, plus the release-readiness
checklist closed in full.

### Changed

- **BREAKING — the wire is cut `0.4` → `0.5`.** The three bare proto `string mode`
  fields are promoted to proto enums so `buf breaking` covers their value sets:
  `SimConfig.mode` → a new `SimMode {stream, batch}`, and `CommandFrame.mode` /
  `ControlStatus.mode` → the existing `Mode {init, active, hold, estop}`. The Rust
  serde reference already used these enums; the proto was the laggard. The JSON wire is
  **unchanged for known values** (serde/Pydantic still emit the lowercase strings) — the
  `string`→enum protobuf type change is what makes it `buf`-breaking. `NCP_VERSION` is
  now `0.5`; pre-1.0 the minor is breaking, so a `0.4` peer and a `0.5` peer
  fail-closed-reject each other (never silently mis-decode).
- **`CONTRACT_HASH` recomputed: `24e8e6e31e1dec8a`** (was `2cf0763ad61e4f1c`) — the
  FNV-1a of the new canonical proto. Advisory (a mismatch is logged, not rejected), but
  it moved because the proto moved; re-pinned in lockstep across `ncp-core`, `ncp-ts`,
  the behavior corpus, and the binding smoke tests.
- **Consumers re-pin to `tag = v0.5.0`** once (the downstream half of the wire cut).
- **sepahead/NCP#5 resolved: keep int64-as-JSON-numbers.** Range-guarded; a second wire
  break to adopt ProtoJSON int64-as-strings is not worth it. Documented in the proto header.

### Added

- **Safety governor over a real transport** (`ncp-zenoh/tests/safety_governor_over_wire.rs`).
  The HOLD/ESTOP/clamp authority is now proven across two independent Zenoh sessions over
  a real tcp link, not just in-process: corpus-driven `govern` verdicts **and the ESTOP
  latch surviving the wire**. (RELEASE_READINESS blocker #1.)
- **Frozen JSON-wire baseline gate** (`scripts/check_wire_baseline.py`,
  `conformance/baseline/v0.5.0/`). Extends `buf`'s proto-only breaking guarantee to the
  whole serde/Pydantic JSON wire: an additive-only diff (no removed field / enum value,
  no newly-required field, no type change within a wire version) of the current schemas
  vs the frozen v0.5.0 snapshot. Wired into `scripts/check.sh` + the CI conformance job.
  (RELEASE_READINESS blocker #3.)
- **Single-source wire-version assert + mixed-version e2e.** `NCP_VERSION` and
  `CONTRACT_HASH` are cross-checked against the behavior corpus header
  (`behavior_conformance.rs`) and across `{ncp-core, ncp-ts, corpus}`
  (`check-version-coherence.sh`); a `0.4` peer is proven fail-closed-rejected by a `0.5`
  server over both the engram cross-process and the Zenoh transports, with the matching
  `0.5↔0.5` happy path kept. (RELEASE_READINESS should-fix #4.)
- **Reply-side + nested-unknown forward-compat tolerance** (`ncp-core`; the engram
  Pydantic peer mirrors it): future fields in replies and in nested messages decode, and
  the engram enum mirror (`_missing_` → `UNKNOWN`, `Mode` → `HOLD`) completes the
  cross-language forward-compat the Rust `#[serde(other)] Unknown` started.
  (RELEASE_READINESS blocker #2 + should-fix #5.)

### Fixed

- **Unknown enum variants are now forward-compatible (additive-non-breaking).** An
  adversarial review found a real hole: the descriptive wire enums (`Observable`,
  `StimulusKind`, `NetworkRefKind`, `EntityRole`, `ChannelKind`, `Role`) derived
  `Deserialize` with no catch-all, so a peer that introduced a new enum string *within
  the same wire version* made every older peer **hard-reject the whole frame** — while
  `buf breaking` reports added enum values as non-breaking (gate and impl disagreed).
  Added a `#[serde(other)] Unknown` sentinel to each (mirroring `Mode`'s existing
  fail-safe-to-`Hold`), so an unrecognized value deserializes to `Unknown` instead of
  erroring. It is a **deserialization catch-all only** (`schemars(skip)` + `ts(skip)`),
  so the JSON Schema, the TS types, and `CONTRACT_HASH` are **unchanged** — pure
  runtime tolerance, no wire change. New test
  `unknown_enum_variant_is_forward_compatible_not_rejected`.

### Added

- **Live cross-process / cross-language end-to-end tests (`e2e/`).** Proves the wire
  contract flows across a real process + language boundary over a real transport —
  **without NEST or `zenoh-python`** (the backend is separable from the contract;
  engram's NEST-free `MockBackend` emits real `Observation` frames):
  - `ncp-zenoh/tests/cross_session_rpc.rs` — two **independent Zenoh sessions** over a
    real tcp link (multicast off) drive the full `open→step→run→close` RPC through the
    typed `ZenohNcpClient` (incl. the version + advisory-contract handshake), asserting
    the scientific-boundary discriminators survive the **production** medium. Gates via
    `cargo test`.
  - `ncp-core/examples/ncp_tcp_client.rs` + `e2e/run_cross_language_e2e.py` — a **Rust**
    client drives the **real Python** engram server (`bridge_server --backend mock`)
    over a localhost-TCP socket, proving a crebain/prisoma-style Rust peer interoperates
    with the Python server across a genuine process + language boundary.
  - (engram side) a cross-process pytest spawns the real `SessionService` as a separate
    process and asserts the lifecycle + **forward/backward compatibility** (unknown
    future field accepted, omitted optionals defaulted) — the additive,
    non-breaking-evolution guarantee, complementing the `buf breaking` wire gate.

### Documentation

- **NEST chunking / calibration / GIL / MUSIC, documented and source-verified.**
  `NEST_REALTIME.md` gains a thorough "chunking question" section answering, from the
  NEST 3.9 source, that (1) `calibrate()`→`pre_run_hook()` runs **once per `Prepare()`**,
  not per `Run()` (`node_manager.cpp::prepare_node_` is reached only from `prepare_nodes()`
  in `Prepare()`; `run()` calls only the IO-manager hook) — so NCP's Prepare-once pattern
  pays calibration once, and the "recalibrate every chunk" cost is the `Simulate()`-per-chunk
  anti-pattern NCP avoids; (2) **MUSIC also chunks** at `min_delay` ticks (NEST maps MUSIC
  ports inside that same once-per-`Prepare` calibrate; `run()` clamps to `min_delay`), so it
  is *not* a tax MUSIC escapes; (3) chunking is **bit-identical science** (ring buffers
  deliver at full delay across boundaries); (4) the only residual is a small *fixed*
  per-`Run()` cost that *vanishes* for big networks. Adds implementer caveats (snap
  `chunk_ms` to a `min_delay` multiple; prefer scheduled-time generators).
- **Corrected the MUSIC latency claim** in `NEST_REALTIME.md`/`PERFORMANCE.md`: MUSIC is
  buffered pairwise `MPI_Send`/`MPI_Recv` (Djurfeldt 2010, PMC2846392) with a tick-bound
  closed-loop floor (~70 ms @ 1 ms tick → ~350 ms @ 50 ms; Weidel 2016), **not** a
  low-microsecond shared-memory hop — NCP's ~0.1–1 ms transport is *under* that floor, so
  NCP is not slower (if anything faster) on single-loop reaction latency. The GIL-held
  verdict is re-stated as source-verified unchanged through NEST 3.10, and the headline
  "1.68× overlap" is re-labelled an off-GIL-contingent busy-spin *ceiling* (engram's
  deployed Python NEST path is serial; the native overlap lives only in the Rust gateway).
- **`scripts/verify_nest_chunking.py`** — a runnable NEST-3.9 proof: counts the
  `prepare_nodes()` log line (Prepare+N×Run → 1; Simulate×N → N), measures the fixed
  per-`Run` overhead, and asserts **bit-identical spike times + STDP weights** for
  chunked vs monolithic.
- **Citation + version corrections** (cross-project triple-check vs primary sources):
  the DDS/Zenoh latency benchmark is by **Liang et al. 2023** (arXiv:2303.09419 —
  Liang, Yuan & Lin), not "Zhang"; dropped an unsupported "Zenoh ~7 µs experimental
  low-latency profile" claim that the cited paper does not contain (added the paper's
  actual zenoh-pico ~5 µs single-machine figure); and bumped six stale `v0.4.3` tag
  pins in the README to the released **`v0.4.4`** (the BibTeX/manifests/CHANGELOG were
  already 0.4.4).

### Changed

- **NCP is now project-neutral — no consumer name baked into the protocol.** The
  load-bearing fix: `ncp_core::DEFAULT_REALM` changed from the project-specific
  `"engram/ncp"` to the neutral `"ncp"`. A realm is *addressing*, not a credential —
  a deployment chooses its own (an Engram fleet may standardise on `"engram/ncp"`,
  and its consumers target that string), but the protocol names no consumer. Also:
  - The Zenoh ACL template (`deploy/zenoh-access-control.json5`) is now **role-based**
    — the privileged command-publisher subject is `commander` (not `engram`), with
    `{realm}` neutralised to `ncp/…`; `scripts/check_acl_template.py`, `SECURITY.md`,
    and `deploy/README.md` track the rename.
  - Doc/comment de-privileging across `ncp-core` (keys/bus/transport), `ncp-zenoh`,
    `ncp-cpp` (ABI comments + demo), `ncp-python`, `ncp-ts`, the README, the
    `NEURO_CYBERNETIC_PROTOCOL` spec, `INTEGRATING.md`, and the gateway README: Engram
    is now consistently presented as ONE example commander/backend, not THE consumer.
  - **Flow-preserving:** the live `engram↔crebain`/`engram↔prisoma` rendezvous stays
    `"engram/ncp"`, now named explicitly by each consumer (their deployment choice)
    rather than inherited from NCP's default. Wire `0.4` unchanged; the proto, schemas,
    and golden vectors were already neutral and are untouched.

## [0.4.4] - 2026-06-21

Patch — **wire `0.4` unchanged** (no consumer re-pin). Cross-language behavioral parity.

### Added

- **ncp-python is now built + behaviorally gated in CI.** A dedicated `ncp-python` CI
  job builds the abi3 wheel via maturin (`--locked`) and installs it, then runs the
  behavioral corpus through the binding with `NCP_REQUIRE_BINDING=1` (which turns the
  previous skip-as-pass into a HARD failure if the wheel didn't build/import) plus a
  codec round-trip smoke test (`encode_rates`→`decode_command`, the one binding path
  the decision corpus doesn't cover). Closes the long-standing gap where the binding
  was only `cargo check`ed, so a runtime regression of the `CommandFrame.mode`
  ACTIVE-vs-HOLD class could have shipped green. The bare conformance step in
  `build-test` still skips cleanly (no binding there); the Rust/C++ runners gate
  regardless.

- **Cross-language behavioral parity (all four peers).** All four SDK peers now replay
  the shared decision corpus (`conformance/behavior/vectors.json`), so a divergence in
  any one peer's decision logic fails CI:
  - **TypeScript gained the hard version gate.** `ncp-ts` previously stamped
    `ncp_version` on every request but had no way to *check* one. Added `checkVersion()`
    + `NcpVersionError`, mirroring `ncp_core::check_version` exactly (pre-1.0 requires an
    exact `major.minor` match; strict throws; an unparseable version always throws). So
    TS now honours the same handshake principles as the Rust/Python/C++ peers
    (version gate + advisory contract hash + scientific boundary).
  - **C++ behavioral runner.** `ncp-cpp/tests/behavior_corpus.rs` drives the full corpus
    through the C ABI (`ncp_check_version`/`ncp_contract_status`/`ncp_validate`/
    `ncp_govern`); gates via `cargo test`.
  - **TS behavioral runner.** `ncp-ts/scripts/check-behavior.mjs` replays the subset the
    thin client implements (checkVersion/contractStatus/scientific-boundary) and
    fail-loud-lists `govern` + required-field `validate` as out-of-scope; gates in the
    `ts-dist` CI job. Wire `0.4` unchanged (additive; rebuilt `ncp-ts/dist`).

- **Behavioral conformance corpus.** `conformance/behavior/vectors.json` is a
  language-neutral `{function, input, expect}` decision corpus that pins *runtime
  behavior* (not just wire shape): `check_version` accept/reject/raise, `contract_status`
  advisory match/mismatch/absent, `validate` required-field + scientific-boundary, and the
  safety-governor HOLD/ESTOP/speed-clamp/watchdog outcomes. The Rust reference is pinned to
  it by `ncp-core/tests/behavior_conformance.rs` (gates in CI via `cargo test`, so the
  corpus can never claim an outcome the reference does not produce), and the Python binding
  is replayed against the identical corpus by `scripts/check_behavior_vectors.py` (skips
  with exit 0 until maturin builds `ncp` in CI; the Rust half gates regardless). Wired into
  `scripts/check.sh` and the CI conformance job. Wire `0.4` unchanged.
- **`contract_status` exposed to Python.** `ncp.contract_status(peer_hash)` returns the
  advisory tag (`"match"` / `"not_advertised"` / `"mismatch"`), mirroring
  `ncp_core::contract_status`, so the Python peer can run the advisory handshake check (and
  the behavioral corpus covers it in both languages). Additive; wire `0.4` unchanged.

## [0.4.3] - 2026-06-21

Patch — **wire `0.4` unchanged** (no consumer re-pin). Cross-language parity + governance.

### Added

- **C++ contract-hash parity.** The C ABI now exposes `ncp_contract_hash()` and an
  advisory `ncp_contract_status(peer_hash)` (`1`=match, `0`=not advertised, `2`=mismatch),
  mirroring `ncp_core::ContractStatus` — so all four peers (Rust, Python, TS, C++) share
  the contract-hash mechanism. (`ncp.h` updated.)
- **TS scientific-boundary validator.** `ncp-ts` exports `assertScientificBoundary()` +
  `NcpScientificBoundaryError`, enforcing the mandatory `is_simulation_output=true` /
  `calibrated_posterior=false` discriminators on an inbound `observation_frame` /
  `session_opened.provenance`, so a TS consumer can reject a frame that quietly claims
  calibrated / non-simulation status (mirrors the boundary pins `ncp_core::validate`
  enforces).
- **Governance:** a reproducible P0 mTLS+ACL validation checklist (`SECURITY.md`) and a
  pre-tag release runbook (`CONTRIBUTING.md`); the repo now enforces immutable `v*` tags
  via a GitHub ruleset (no delete/force-update).

## [0.4.2] - 2026-06-21

Patch — **wire `0.4` unchanged** (no consumer re-pin). NCP now **owns its JSON-Schema
generation** proto-first; the schema-from-a-consumer inversion is gone.

### Changed

- **Schema ownership cutover.** The committed `schemas/*.schema.json` are now generated
  by `gen-schemas` from the `ncp-core` serde reference types (schemars) — not from a
  downstream consumer's Pydantic models. The generator injects the `kind` discriminator
  `const` and the `required` array from the `required_fields()` validation contract
  (now `pub`), and the field defaults come straight from the Rust types — so the
  `CommandFrame.mode` fail-safe default (`hold`) is now **intrinsic and cannot drift**.
  CI **regenerates and diffs** the schemas on every run (`gen-schemas` + `diff`), so a
  Rust type change that isn't regenerated fails CI.
- `scripts/check_proto_schema_parity.py` adapted to the schemars projection (names a
  `$defs` type by its key, and reads the `oneOf` enum form schemars emits for enums with
  documented variants — restoring wire-string parity coverage for `Observable` /
  `StimulusKind`). `required_fields` is now `pub` (the generator's source of truth for
  `required`).
- Engram (`backend/neurocontrol`) is now a pure **consumer** of the NCP-owned schema:
  `export_schemas.py` is deprecated (no longer the source), and `test_schema_drift`
  checks engram's Pydantic models stay **field-compatible** with the vendored NCP schema
  (rather than producing it).

## [0.4.1] - 2026-06-21

Patch release — **wire `0.4` unchanged** (no consumer re-pin required; v0.4.0 and v0.4.1
interoperate). Safety fix + cross-language parity + documentation consistency.

### Fixed

- **Safety: `CommandFrame.mode` fail-safe default.** The committed JSON Schema (generated
  from engram's Pydantic) documented an omitted `mode` defaulting to the *actuating*
  `"active"`, contradicting the normative Rust reference (`default_command_mode()` →
  `Mode::Hold`). A `CommandFrame` built without an explicit mode must fail-safe to
  `hold`, never actuate. Fixed the engram Pydantic default to `Mode.HOLD`; the schema now
  reads `"hold"`. (The proto↔schema parity guard checks field-sets, not defaults, so it
  never caught this — see the new guard below.)
- Documentation drift: the `OpenSession`/`SessionOpened.contract_hash` field docs (Rust +
  the ts-rs-generated TS bindings) and the proto comments still described the handshake as
  *fail-closed-rejecting* a hash mismatch; corrected to **advisory** (the v0.4 behavior).

### Added

- **Schema-default safety guard** (`scripts/check_schema_defaults.py`, wired into CI): every
  committed schema field DEFAULT must equal the normative Rust reference (runs the
  proto-first `gen-schemas`). Closes the gap the parity guard left; would have caught the
  `mode` bug above.
- **TypeScript contract-hash parity.** `ncp-ts` now exports `NCP_CONTRACT_HASH` and an
  advisory `contractStatus()` (mirrors `ncp_core::contract_status`); `NeuroSimClient.open`
  sends the hash and logs a reply-mismatch advisory (does not throw). The
  version-coherence guard now also pins `CONTRACT_HASH` across `ncp-core` ↔ `ncp-ts`.

### Documentation

- Markdown consistency pass: version strings synced to `0.4` across
  `NEURO_CYBERNETIC_PROTOCOL.md`, `CONTRIBUTING.md`, `proto/README.md`, `schemas/README.md`,
  `ncp-python` docs, `VERSIONING.md`. `CONTRIBUTING.md`/`NEURO_CYBERNETIC_PROTOCOL.md`
  updated to the additive-is-non-breaking + advisory-handshake policy. `SECURITY.md` notes
  `contract_hash` is a drift detector, not a security control. `schemas/README.md` documents
  the proto-first `gen-schemas` path + the staged cutover. Consumer names removed from the
  versioning prose (protocol is consumer-agnostic).

## [0.4.0] - 2026-06-21

**Decoupling + robustness release (wire `0.3` → `0.4`).** Batches the structural fixes
into ONE bump (no more dribble): a consumer-neutral protocol identity, a contract
handshake that no longer breaks version-compatible flows, and a versioning policy where
additive evolution is non-breaking. A `0.3` peer is fail-closed rejected on version; all
consumers re-pin to `tag = v0.4.0` **once**, and future additive changes need no re-pin.

### Changed (breaking: wire `0.3` → `0.4`)

- **Protocol-identity decoupling.** The proto `package` is renamed
  `engram.ncp.v0 → ncp.v0` — the normative contract names *itself*, not a consumer.
  This is **wire-neutral** (NCP's JSON wire uses `kind` discriminators and `ncp-core`
  hand-written serde, not the prost package) and now **hash-neutral**: `canonical_proto`
  was refactored to hash only the *wire-semantic* content (message/field/enum), dropping
  the non-wire `syntax`/`package`/`import`/`option` lines, so naming changes no longer
  move `CONTRACT_HASH`. (The deployment *realm* `engram/ncp` is unchanged — it names the
  deployment, not the protocol, and is the live `engram↔crebain`/`prisoma` rendezvous.)
- **The contract handshake is now ADVISORY, not fail-closed.** `negotiate` gates on
  `ncp_version` (hard compatibility) and returns a `ContractStatus` (`Match` /
  `NotAdvertised` / `Mismatch`); a hash mismatch is **logged, not rejected**, so a
  version-compatible flow keeps working when a peer is on a newer contract revision
  (e.g. it added an optional field). A `verify_contract` strict opt-in remains for
  deployments that mandate an exact revision. Server (engram `SessionService.handle`)
  and client (`ncp-zenoh::open`) both log the advisory instead of failing.
- **Additive evolution is non-breaking (versioning policy).** Adding an optional field
  or new message type no longer bumps the minor (protobuf/serde ignore unknown fields);
  the minor bumps only for genuinely incompatible changes. This corrects the
  over-aggressive rule that forced the `v0.2.5/6/7/8` and `0.2→0.3` re-pins. `VERSIONING.md`
  rewritten accordingly; `ncp_version` is the compatibility gate, `CONTRACT_HASH` the
  advisory identity signal. `CONTRACT_HASH` = `2cf0763ad61e4f1c`.
- Engram (`backend/neurocontrol`) mirrors all of the above: semantic `canonical_proto`,
  advisory `contract_advisory`/`negotiate`, `NCP_VERSION` `0.4`. Proto enum/role comments
  de-named from NEST/Engram specifics to neutral "backend"/"commander" wording.

### Added

- **Proto-first, NCP-owned JSON-Schema generation (`gen-schemas`).** A new
  `ncp-core` `schema` feature derives `schemars::JsonSchema` on the wire types and a
  `gen-schemas` binary (`cargo run -p ncp-core --features schema --bin gen-schemas`)
  emits `schemas/*.schema.json` **from the serde reference types** — which are the
  conformance-locked reference impl of `proto/ncp.proto` and carry the enum wire
  strings in their `#[serde(rename)]`. This is the ownership infrastructure that
  removes the inversion where schemas were generated from a downstream consumer
  (engram's Pydantic). Off by default (zero impact on the default build/CI). The
  generator is verified to emit faithful field-sets and wire-string enums; the
  **cutover** (replacing the committed schemas, adapting the parity/conformance
  guards to the schemars shape + preserving the `kind` const, and migrating engram to
  consume rather than produce) is staged as the next step.

### Changed

- **Consumer pin tooling is now consumer-agnostic (decoupling).** NCP no longer names
  or enumerates any consumer. `scripts/check-consumer-pins.sh` and
  `scripts/repin-ncp.sh` **discover** consumers by globbing siblings for a
  `.ncp-consumer` descriptor (committed in the consumer's own repo), and CI's
  consumer-pin step keys off that glob. Onboarding a new consumer now requires **zero
  NCP-repo changes** — it commits a `.ncp-consumer` to its own repo. Documented in
  `INTEGRATING.md` §"Registering a consumer"; `CONTRIBUTING.md` / `scripts/README.md`
  de-named the specific consumers.
- `ncp-python` now exposes `CONTRACT_HASH` (alongside `NCP_VERSION`) so Python
  consumers import the canonical hash from the core instead of hardcoding it.

### Documentation

- Corrected `README.md` / `schemas/README.md`: JSON Schemas are the proto's JSON
  projection emitted from the reference Pydantic models (not "via buf") and parity-
  guarded against the proto; `ncp_version` shown as `0.3`. Flagged proto-native schema
  generation (so NCP owns its own schema source) as a tracked decoupling item.

- Documented `CONTRACT_HASH`: why it is a hardcoded constant (runtime has no proto;
  contract-identity; cross-language anchor; CI-guarded so it cannot drift) plus the
  considered `include_str!`+`LazyLock` alternative. Expanded the `ncp_core::CONTRACT_HASH`
  docstring and added `VERSIONING.md` §"Contract hash" + the landed handshake section.

## [0.3.0] - 2026-06-21

**Wire bump `0.2` → `0.3` (breaking, pre-1.0 minor-is-breaking).** A `0.2` peer is
fail-closed rejected by the version guard; all consumers must re-pin to `tag = v0.3.0`.
The `buf breaking` baseline moves to `v0.3.0` (the first tag of wire `0.3`).

### Added

- **Symmetric, fail-closed contract-hash handshake.** `OpenSession` and
  `SessionOpened` carry a new `contract_hash` field (proto field 9; serde
  `Option<String>` defaulting to our own `CONTRACT_HASH`). The client half
  (`ncp-zenoh::ZenohNcpClient::open`) now calls `negotiate(version, hash)` instead of
  only `check_version`, rejecting a `SessionOpened` whose advertised hash differs; the
  server half (engram's `SessionService.handle`) verifies the incoming
  `OpenSession.contract_hash` before dispatch. This turns the contract-pinning from a
  local-only function into an on-the-wire, peer-negotiated check (closes the ROADMAP P1
  "carry the hash in the handshake envelope" item).
- **Cross-language contract-hash parity.** The Python peer
  (`backend/neurocontrol/protocol.py`) gains a byte-identical port of `canonical_proto`
  / `contract_hash_of_proto` / `verify_contract` / `negotiate`, so Rust and Python
  independently recompute the same `CONTRACT_HASH` from the proto (verified against the
  vendored proto in engram's tests).

### Changed

- **`CONTRACT_HASH` is comment-insensitive** (landed in this cycle): hashed over a
  *canonicalized* proto (`ncp_core::canonical_proto` — `//` and `/* */` comments
  stripped respecting string literals, whitespace normalized) via
  `contract_hash_of_proto`, so a comment-/formatting-only edit no longer flips it (the
  churn the `v0.2.5`/`v0.2.6` entries documented). With the new envelope field the
  pinned value is `3e639fb1aa20e530`.
- `NCP_VERSION` `0.2` → `0.3` (Rust `ncp-core` and Python `backend/neurocontrol`);
  every JSON Schema's `ncp_version` default and all golden conformance vectors bump to
  `0.3`; ts-rs bindings regenerated for the new field.
- `scripts/check-version-coherence.sh` now also verifies the `README.md` bibtex
  `version = {…}` against Cargo/npm/CITATION (the drift that left the bibtex at `0.2.7`).

### Fixed

- `README.md` bibtex citation example was stale (`0.2.7`); now coherent with the release.

## [0.2.8] - 2026-06-20

### Security

- `ncp-zenoh`: secure-by-default transport. `ZenohBus::open`/`open_realm` now open a
  **hardened default** config with multicast scouting disabled, so a default
  deployment no longer auto-advertises on the LAN (peers still connect via explicit
  `connect`/`listen` endpoints). Added `ZenohBus::open_secure`,
  `ZenohBus::with_config_file`, and the `NCP_ZENOH_CONFIG` env hook (honored by
  `open`/`open_realm` and the `ncp-gateway` binary) to load the shipped per-plane ACL
  config (`deploy/zenoh-access-control.json5`). Loading fails closed — a missing or
  malformed config aborts the open rather than falling back to an open default, and
  `open_secure` refuses to start when `NCP_ZENOH_CONFIG` is unset. Documented that the
  realm is *addressing, not a credential*. No wire/proto change.

## [0.2.7] - 2026-06-20

Release-coherence fix. **No wire change** — `ncp_version` stays `0.2` and the conformance vectors are
unchanged. v0.2.6 was tagged but its crate manifests and the `@sepehrmn/ncp` npm package still
self-identified as `0.2.5` (the manifest version bump was omitted), so a consumer pinning `tag=v0.2.6`
compiled a crate reporting `0.2.5`. This release bumps the workspace crates and the npm package to
`0.2.7` so the git tag, the Cargo manifests, and the npm package agree. Consumers should re-pin from
v0.2.6 to v0.2.7. (v0.2.6 is left intact — tags are immutable once consumed.)

## [0.2.6] - 2026-06-20

Rebrand-only release. **No wire shape change** — `ncp_version` stays `"0.2"` and the JSON/binary
vectors are unchanged. **Compat note:** `CONTRACT_HASH` rebumped (`4c31db5c8eafbcf7` →
`07f829cabbd1684a`) because the proto's issue-reference comment changed; peers that exchange the
contract hash in `negotiate()` must run the same release, so upgrade the fleet together — this is
the designed contract-revision signal, not a wire break.

- Repointed all repository URLs from `github.com/sepehrmn/NCP` to
  `github.com/sepahead/NCP` (GitHub account rename); the `@sepehrmn/ncp` npm
  package name is unchanged (it is the published identity pinned by consumers).
  The proto's issue-reference comment changed too, so `CONTRACT_HASH` rebumped
  (`4c31db5c8eafbcf7` → `07f829cabbd1684a`); no wire/field/enum change.

## [0.2.5] - 2026-06-20

Conformance, validation, versioning, and supply-chain hardening — the v0.2.4
follow-on found by a 20-lens review. **No wire shape change** — `ncp_version` stays
`"0.2"` and the JSON/binary vectors are unchanged. **Compat note:** the proto's
version-policy comments were corrected (no field/enum/wire change), which rebumps
`CONTRACT_HASH` (`c35c4897a317049f` → `4c31db5c8eafbcf7`). Peers that exchange the
contract hash in `negotiate()` must run the same release, so upgrade the fleet
together — this is the designed contract-revision signal, not a wire break.

### Fixed
- **Conformance validator is now honest.** `check_conformance_vectors.py` no longer
  short-circuits `anyOf` (every nullable field — units, seed, durations, recordable,
  provenance — was previously unchecked) and gained primitive `type` checks, so a
  `{"type":"null"}` branch actually rejects a non-null and wrong-typed scalars fail.
- **Two-way proto↔schema parity.** `check_proto_schema_parity.py` added a reverse
  pass: a proto message with no JSON Schema (e.g. `BulkObservation`) and no
  documented allowlist entry now fails, closing the schema-only blind spot.
- **Language bindings validate like the reference.** `ncp-python` and `ncp-cpp`
  `validate()` previously only did a typed serde round-trip (silently defaulting a
  missing required field, round-tripping a tampered discriminator clean); they now
  delegate to `ncp_core::validate` first, and `link_status` was added to both
  dispatch tables (the one wire kind they were missing).
- **Version policy text matched the code.** The proto comments and the spec /
  VERSIONING docs said receivers check the "major only"; corrected to the actual
  exact `(major, minor)` pre-1.0 fail-closed rule (the README was already right).

### Added
- **`validate()` pins the scientific-boundary discriminators.** A frame asserting
  `calibrated_posterior=true` or `is_simulation_output=false` (top-level on
  `observation_frame`, or in `session_opened.provenance`) is now rejected, not
  trusted — mirroring the proto "always false"/"always true" contract.
- **Corpus coverage 4 → 13 kinds** with a coverage gate (every schema `kind` must
  have a golden vector), a `required_fields()`↔schema drift test, and a
  cross-language `ncp-cpp` corpus test that drives every JSON vector through the
  C ABI.
- **Supply-chain gate:** `cargo-deny` (advisories / licenses / bans / sources) +
  `deny.toml`, `--locked` on all CI cargo steps and the release publish dry-runs, a
  release tag↔version guard, and a `cargo check` of `ncp-python` (was never compiled
  in CI). The local `check.sh` now runs the parity + conformance gates too.

### Security
- **Glob subscribes enforce `check_id`** and the client `open()` runs the version
  handshake (carried over from the v0.2.4 transport work). `cargo-deny` documents
  three transitive advisories pinned by `zenoh 1.9.0` (lz4_flex block-API OOB,
  `paste`/`rustls-pemfile` unmaintained) with remove-when conditions.

## [0.2.4] - 2026-06-20

Safety, validation, and security hardening — the remaining major findings from the
10-lens protocol audit after v0.2.3. No wire change — `ncp_version` stays `"0.2"`;
all changes are plant-side/behavioral fixes, fail-safe deserialization, receive-path
validation, a sensor-plane ACL invariant, observability, and normative docs, so
existing peers and conformance vectors are unaffected. Crates/package `0.2.4`.

### Fixed
- **Real-time: `ActionBuffer`/`CommandWatchdog` reject stale & reordered commands.**
  A duplicate/reordered/replayed `CommandFrame` could overwrite a newer one and
  rewind the replay clock, and a trickle of stale commands kept the watchdog
  deadline "fresh" (fail-open during a blackout). Now: monotonic-forward `seq`
  acceptance drops them (`seq == 0` escape hatch for pull/sim streams) and the
  watchdog refreshes only on a strictly-advancing `seq`; an ESTOP still latches even
  if stale.
- **Safety: an unknown `mode` string deserializes to `HOLD`** rather than
  hard-erroring the whole `CommandFrame` (complements the v0.2.3 absent-mode→HOLD).
- **Resilience: bulk parallel columns must agree in length.** `observation_from_bulk`
  rejects a block whose `times`/`values`/`senders` disagree — fail closed at the
  untrusted-bytes boundary instead of silently pairing mismatched arrays.
- **Interop/safety: wrong-`kind` RPC replies are rejected** before the typed decode,
  so a misrouted but valid-JSON reply no longer becomes an all-default response.

### Security
- **Sensor-plane PUT is access-controlled, symmetric to the command plane.** The
  perception plane is a control input — a spoofed `SensorFrame` steers the controller
  and defeats the geofence (false-data injection) — so `check_acl_template.py` now
  enforces sensor-PUT → `robot` (and self-tests every run), and `SECURITY.md`
  documents the threat + remedy (publisher access control per DDS-Security / SROS2).

### Added
- `diagnose_version()` + a sensor-subscriber diagnostic so a dropped,
  version-incompatible frame is observable rather than silently ignored.

### Documentation
- A **normative action-plane liveness conformance clause**: a plant **MUST** fail
  safe (HOLD) on expired `ttl_ms` and **MUST NOT** actuate on a stale setpoint (the
  wire only detects a gap; the plant owns the safe state — RFC 2119/8174;
  IEC 61508 / ISO 13849 framing).

## [0.2.3] - 2026-06-20

Contract-vs-implementation reconciliations from a 10-lens protocol soundness audit.
No wire change — `ncp_version` stays `"0.2"`; the changes are a behavioral safety
fix, a fail-safe deserialization default, and doc corrections, so existing peers
and conformance vectors are unaffected. Crates/package `0.2.3`.

### Fixed
- **Real-time: `CommandFrame.seq` now echoes the originating `SensorFrame.seq`.**
  `NeuroControlLoop::tick()` overwrote it with the loop's own free-running counter,
  breaking the normative split-plane V↔A join (an observer pairing action to sensor
  on `seq` would mispair). The loop's tick counter now lives only on `ControlStatus`.
- **Safety: a `CommandFrame` that omits `mode` now deserializes to `HOLD`, not
  `ACTIVE`.** An untrusted/partial wire frame must never default to actuating; added
  a fail-safe serde field default. Programmatic `CommandFrame::default()` is unchanged.

### Documentation
- **Transport QoS corrected to match the Zenoh binding.** It sets best-effort
  `CongestionControl::Drop` + priority + `express` only — NOT conflation/keep-last,
  reliability, or a wire TTL/`LIFESPAN`; `ttl_ms` is enforced plant-side by
  `CommandWatchdog`. Fixed the key scheme, the DDS-mapping table (now labelled
  "DDS mapping, not set today"), README, and RESILIENCE.
- **Versioning policy clarified.** `check_version`/`negotiate` are fail-closed
  *library* entry points, not yet auto-invoked on the data-plane receive path;
  per-session `open_session` negotiation remains a ROADMAP P1 target.

## [0.2.2] - 2026-06-19

Hardening pass against ROADMAP P0/P1/P2 and a full-repo review. No wire change —
`ncp_version` stays `"0.2"`; all additions are additive APIs, a config fix, docs,
and CI guards, so existing peers/vectors are unaffected. Crates/package `0.2.2`.

### Security
- **P0 / #7 — the per-plane ACL template now actually loads.** `deploy/zenoh-access-control.json5`
  used `"get"` in `messages`, which is not a valid Zenoh access-control token, so
  zenohd would reject the whole config — leaving the world-writable action plane
  with no mitigation while reading as "secured." Replaced with the correct tokens
  (`query` for the get/querier side; pure data-plane reads use `declare_subscriber`)
  and clarified that `cert_common_names` matches by **exact** string (not glob).
  Added `scripts/check_acl_template.py` (stdlib-only) as a CI guard: it fails on any
  invalid `messages` token and enforces the safety invariant that only the `engram`
  commander policy may PUT on `…/command/**`. Wired into `scripts/check.sh`.

### Fixed
- **Safety (critical): predictive horizon bypassed the speed clamp.** `SafetyGovernor::govern`
  clamped only the tick-0 command; `CommandFrame.horizon[1..]` — replayed verbatim
  by `ActionBuffer` through dropouts — passed unclamped, defeating `max_speed_mps`
  on every tick after 0. Now every horizon step is speed-clamped with the same
  logic, and a step that cannot be enforced (absent/non-finite velocity) truncates
  the horizon there so replay HOLDs rather than emitting an unbounded setpoint.
- **Safety: staleness/watchdog backstops failed OPEN on a non-finite clock.** A NaN
  `now_s` made `(now_s - last) > timeout` evaluate false ("fresh") in both
  `SafetyGovernor::govern` and `CommandWatchdog::should_hold`; both now treat any
  non-finite clock input as stale/expired (HOLD).
- **Versioning: `check_version` coerced a malformed minor to 0 (latent fail-open).**
  A present-but-garbage minor (`"0.GARBAGE"`) or extra component (`"0.2.1"`) silently
  parsed to a `0` minor; minor parsing is now as strict as major (reject non-numeric
  / trailing components), so the fail-closed guard cannot become fail-open.
- **Codec: a dropped readout population decoded to full-reverse actuation.**
  `CodecSpec::decode` mapped an absent population to the value-range low bound
  (e.g. −1.5 m/s — commanded motion the governor's magnitude clamp passes). It now
  maps to the documented neutral midpoint (0.0 for a symmetric range).
- **Resilience: reordering permanently inflated `loss_rate`.** `LinkMonitor` counted
  a later-arriving (merely reordered) seq as a permanent loss, spuriously escalating
  the burst/HOLD fail-safe. It now reconciles out-of-order arrivals against a bounded
  missing-seq set, decrementing `lost`. `LinkMonitor::new` also validates/clamps
  `ref_loss` (to `[0,0.99]`) and `threshold` (>0, finite) so an out-of-range param
  can no longer disable or false-trip the jam detector.

### Added
- **P1 — wire-contract pinning.** `ncp_core::CONTRACT_HASH` (FNV-1a of `proto/ncp.proto`),
  `fnv1a_hex`, `verify_contract`, and `negotiate(version, contract_hash)` — a single
  "negotiate, reject, never coerce" handshake gate that detects a post-agreement
  schema mutation (the "rug-pull" class). A conformance test recomputes the hash from
  the real proto, so a proto edit that forgets to bump the constant fails CI.

### Changed
- **P2 — dual licensing.** Moved to `MIT OR Apache-2.0` (the Rust-ecosystem norm):
  `LICENSE` → `LICENSE-MIT`, added `LICENSE-APACHE`, and updated `Cargo.toml`,
  `package.json`, `CITATION.cff`, and the README license section/badge.

## [0.2.1] - 2026-06-17

Patch release: no wire change (`ncp_version` stays `"0.2"`); fixes a shipped-artifact
defect, doc accuracy, and documentation consistency. Crates/package versioned `0.2.1`.

### Fixed
- **The shipped TS package announced the wrong wire version.** The git-tracked,
  published `ncp-ts/dist` (the `@sepehrmn/ncp` build artifact) still stamped
  `ncp_version "0.1"` after the `0.2` source bump — so a JS/TS peer would be
  version-rejected by the Rust/Python peers. Rebuilt `dist` to `"0.2"`, pinned
  `typescript` for a reproducible build, and added a `ts dist up-to-date` CI job
  that fails when `dist` drifts from source.
- Doc accuracy in `ncp-core::bulk`: `Column::as_f64`/`as_i64` now note the lossy
  (i64→f64 >2^53 / float→int) arms not exercised by the codec; `BulkBlock::encode`
  documents its size limits; the `ncp-cpp` version-doc example says `"0.2"`.

### Changed
- Documentation consistency sweep across the markdown set (version strings, MSRV
  1.88, `v0.2.x` feature coverage for the bulk codec / ACL / governance / neuron
  families, and cross-link integrity).

## [0.2.0] - 2026-06-17

Pre-1.0 / pre-release: the wire contract may still change. The crates are versioned
`0.2.0` in `Cargo.toml` and the wire `ncp_version` string is `"0.2"`; tagged
`v0.2.0` (the first proto-bearing baseline, used by the `buf breaking` gate). The
`0.1`→`0.2` changes are additive, but a pre-1.0 minor bump is fail-closed by the
version guard, so peers must speak `0.2`.

### Added
- Initial protocol + Rust reference SDK (`ncp-core`, `ncp-zenoh`, `ncp-gateway`,
  `ncp-python`, `ncp-cpp`): QoS-differentiated Zenoh transport, a safety-gated
  action plane (mode/`ttl_ms`, latched ESTOP, fail-closed watchdog/geofence), and
  per-frame provenance.
- Two wire conformance guards: `ncp-core/tests/conformance.rs` (Rust serde ↔ JSON
  Schema) and `scripts/check_proto_schema_parity.py` (`proto/ncp.proto` ↔ JSON
  Schema — field-set + enum wire-string parity), both in CI.
- Buf scaffold (`buf.yaml` / `buf.gen.yaml`): lint, build and polyglot codegen
  (Rust/TS/Python) from `proto/ncp.proto`; `buf lint` in CI.
- **Neuron-family coverage (#10):** generic named-recordable + named-param wire —
  `Observable.binary_state`, `StimulusKind.rate_inject`, `RecordTarget.recordables`,
  `Observation.recordable`, `StimulusTarget.params` — so the contract serves NEST's
  point/conductance (`g_ex`/`g_in`/`w`), binary, and rate-based neuron families, not
  just spiking. Additive; the Engram reference backend wires it to NEST 3.9
  (`multimeter`/`step_rate_generator`/`spin_detector`), verified live.
- `VERSIONING.md` (SemVer wire policy + buf-breaking enforcement + version-negotiation
  target), a golden-vector **conformance corpus** (`conformance/vectors/` +
  `scripts/check_conformance_vectors.py`, in CI), and `deploy/zenoh-access-control.json5`
  (per-plane ACL template).
- **Bulk column codec (#6):** `ncp-core::bulk` — a packed little-endian, parse-free,
  random-access column block (`f32`/`f64`/`i32`/`i64`) for bulk observation arrays
  (spike trains, V_m traces), with the `BulkObservation` proto envelope. Additive,
  observation-plane-only (never the hot action loop); fully bounds-checked decode of
  untrusted bytes. A binary golden vector (`conformance/vectors/bulk_observation.bin`)
  + a Python reference decoder make it cross-language conformance-checked, byte-pinned
  to the Rust encoder.
- **Conformance corpus now spans JSON *and* binary (#9):** the validator checks the
  bulk binary vector via a stdlib reference decoder; `GOVERNANCE.md` documents the
  governance model + neutral-home path.
- **Action-plane authentication (#7):** corrected and completed the per-plane Zenoh
  ACL template into a functional default-deny policy (distinct engram/robot/observer
  subjects; only `engram` may publish commands; clients may query the RPC), and added
  concrete TLS+ACL enablement steps to `SECURITY.md` (DDS-Security / MAVLink-2-signing
  comparators already documented).
- `@sepehrmn/ncp` TypeScript package (`ncp-ts`): generated wire types, a
  transport-agnostic `NeuroSimClient`, and a WebSocket transport. The client
  surfaces server `{kind:"error"}` frames as thrown errors and rejects unsafe
  (>2^53) seeds.
- Release scaffolding (LICENSE, CITATION.cff, SECURITY.md, ROADMAP.md, this
  changelog, crates.io metadata) and CI.

### Changed
- **proto-native:** promoted `proto/ncp.proto` to the **normative wire contract**
  (previously a non-normative mirror). The JSON Schemas are its JSON projection and
  `ncp-core` is the reference implementation; all docs reconciled to this model.
- Named the protocol the **Neuro-Cybernetic Protocol (NCP)**.
- Vendored the spec, `.proto` definitions, and JSON schemas into the SDK so the
  wire contract ships with the reference implementation rather than living out of
  tree.

### Fixed
- **CI was red on every push and PR.** Transitive deps in `Cargo.lock` (`darling`,
  `time`/`time-core`, `rcgen`, `serde_with`, `home`) declare `rust-version 1.88`,
  and edition2024 deps need ≥1.85 — the pinned `1.81.0` toolchain could not even
  parse their manifests. Bumped the MSRV / CI toolchain to **1.88.0** (`Cargo.toml`,
  `ci.yml`, `release.yml`, README badge), unblocking the fmt/clippy/test gate and
  the dependabot dependency PRs.

[Unreleased]: https://github.com/sepahead/NCP/compare/v0.8.0...HEAD
[0.8.0]: https://github.com/sepahead/NCP/compare/v0.7.1...v0.8.0
[0.7.1]: https://github.com/sepahead/NCP/compare/v0.7.0...v0.7.1
[0.7.0]: https://github.com/sepahead/NCP/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/sepahead/NCP/compare/v0.5.3...v0.6.0
[0.5.3]: https://github.com/sepahead/NCP/compare/v0.5.2...v0.5.3
[0.5.2]: https://github.com/sepahead/NCP/compare/v0.5.1...v0.5.2
[0.5.1]: https://github.com/sepahead/NCP/compare/v0.5.0...v0.5.1
[0.5.0]: https://github.com/sepahead/NCP/compare/v0.4.4...v0.5.0
[0.4.4]: https://github.com/sepahead/NCP/compare/v0.4.3...v0.4.4
[0.4.3]: https://github.com/sepahead/NCP/compare/v0.4.2...v0.4.3
[0.4.2]: https://github.com/sepahead/NCP/compare/v0.4.1...v0.4.2
[0.4.1]: https://github.com/sepahead/NCP/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/sepahead/NCP/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/sepahead/NCP/compare/v0.2.8...v0.3.0
[0.2.8]: https://github.com/sepahead/NCP/compare/v0.2.7...v0.2.8
[0.2.7]: https://github.com/sepahead/NCP/compare/v0.2.6...v0.2.7
[0.2.6]: https://github.com/sepahead/NCP/compare/v0.2.5...v0.2.6
[0.2.5]: https://github.com/sepahead/NCP/compare/v0.2.4...v0.2.5
[0.2.4]: https://github.com/sepahead/NCP/compare/v0.2.3...v0.2.4
[0.2.3]: https://github.com/sepahead/NCP/compare/v0.2.2...v0.2.3
[0.2.2]: https://github.com/sepahead/NCP/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/sepahead/NCP/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/sepahead/NCP/releases/tag/v0.2.0
