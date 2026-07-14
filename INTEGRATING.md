# Integrating the NCP 1.0 candidate

> **Do not deploy this as released 1.0.** Repository HEAD is the unreleased,
> release-blocked `1.0.0-rc.1` candidate (wire `1.0`, compact proto hash
> `163acc57d8a62b66`). `v0.8.0` remains the latest immutable release and is not
> natively compatible.

An integration is certified only when it installs immutable candidate artifacts,
reports the same complete normative/corpus digests, passes every applicable vector
with zero skips, passes the live secure/fault subset, and supplies its own plant
safety case where it can actuate. A source checkout compiling is not certification.

## Choose a role

- A **commander** opens and mutates sessions and may hold action authority.
- A **body** serves simulation/plant data, publishes perception and observation,
  validates the plant profile, and remains final actuator authority.
- An **observer** subscribes read-only and cannot mutate lifecycle or action.
- An **operator** may initiate the deployment's body-local or out-of-band ESTOP
  reset procedure, or override authority, only when explicitly enrolled for that
  permission. Wire 1.0 has no stable reset RPC.

Enroll the cryptographic principal, entity, role, and exact plane set in one
default-deny authority manifest. Do not infer a role from a key or payload alone.

## Native 1.0 checklist

1. Pin one immutable candidate artifact set; record source revision, package hashes,
   package version, wire version, full normative digest, compact proto hash, corpus
   digest, toolchains, OS, and architecture.
2. Apply the universal JSON budget before generic allocation and semantic decoding.
3. Negotiate the exact security profile/digest, stable capability set, channel
   requirements, and content-addressed plant profile where applicable. Compute both
   digests from the normative typed projections in
   [`contract/security-state-digest.v1.json`](contract/security-state-digest.v1.json),
   [`contract/plant-profile.v1.json`](contract/plant-profile.v1.json), and
   [`contract/canonical-digest.v1.json`](contract/canonical-digest.v1.json), never
   from language-specific JSON serialization.
4. Bind each payload claim and plane delivery to the verified transport principal.
5. Treat the successful `SessionOpened.session.generation` as the only live
   incarnation. At every typed data-plane publish/subscribe boundary, require that
   generation and exact payload-ID-to-concrete-route equality before callbacks or
   safety latches. Reject stale nested sessions, operations, leases, and replies;
   ESTOP may omit only its lease, never its complete envelope or live binding.
6. Treat a successful authorized ESTOP reset as a session-generation cut: retire
   the current generation, authority and lease, and all stream state; remain
   non-actuating until a fresh `SessionOpened`, new generation, new streams, and new
   matching authority lease. Do not expose a local reset helper as a remote reset
   RPC. Reject every pre-reset frame by session binding before latch or control
   processing.
7. Require a valid bounded authority lease for active action and for step/run/close.
8. Generate canonical operation IDs/request digests and verify responder receipts;
   never retry when the result is unprovable except through the specified
   `outcome_unknown` recovery policy.
9. Implement the four queue policies exactly: control reject, perception latest,
   action highest fail-safe severity (ESTOP, HOLD/non-active, Active) with
   equal-severity latest-wins, observation drop-oldest-and-count.
10. Keep `calibrated_posterior=false` and `is_simulation_output=true` on simulation
   results.
11. Replay the exact applicable vector set from
    [`conformance/manifest.v1.json`](conformance/manifest.v1.json), then run the live
    secure/fault matrix from [`RELEASE_READINESS.md`](RELEASE_READINESS.md).

## Breaking migration from 0.8

There is no in-place decode fallback. At minimum, a consumer must account for these
breaking changes:

| Wire 0.8 | Wire 1.0 candidate |
|---|---|
| exact pre-1.0 wire `0.8` | stable-major wire `1.0` |
| compact hash `d1b50a2d8a265276` | compact hash `163acc57d8a62b66` plus full normative SHA-256 digest |
| `ChannelSpec.optional: bool` | closed `requirement: required|optional`; unknown/absent rejects |
| profile/identity context often deployment-only | negotiated `IdentityClaim`, security profile, and security-state digest |
| no stable capability manifest | exact closed stable capability set required |
| no plant-profile digest | plant role requires content-addressed plant profile |
| session generation only | session generation plus bounded authority lease on active/mutating paths |
| step/run/close lacked operation proof | operation context and authenticated terminal receipt |
| implementation-local JSON/resource limits | universal normative envelope budget |
| informal proxying | explicit `gateway_permitted` and visible gateway attribution only |

Audit every persisted frame, cache key, retry loop, router ACL, test fixture, UI
status, example, and telemetry consumer—not just public structs. An old cached frame
must fail as stale rather than acquire a new session or authority by default.

## Labelled terminating gateway

`ncp-core::migration` provides the bounded migration primitive. It is terminating,
authenticated, visible as source wire 0.8, and one-way into a separately validated
native 1.0 context. It maps explicit legacy `optional=false` to `required` and
`optional=true` to `optional`. Missing, null, string, mixed old/new, transparent, or
context-free inputs reject.

The gateway cannot invent identity, security, session epoch, authority, operation,
receipt, plant, or scientific evidence. A result that traverses it is labelled
legacy-translated and cannot count as native 1.0 certification. Native peers may set
`gateway_permitted=false`.

[`ncp-gateway`](ncp-gateway/) is unrelated to this version translation. It is a
same-wire native-1.0 lifecycle edge and requires a native-1.0 Python
`SessionService`.

## Registering a consumer

Consumer discovery is generic: `scripts/check-consumer-pins.sh` and
`scripts/repin-ncp.sh` inspect every sibling repository that commits a
`.ncp-consumer` descriptor. Adding a consumer never adds its name or layout to NCP.
The line-oriented descriptor accepts `#` comments and only declares consumer-owned
relative files:

```text
cargo_tag       Cargo.toml
cargo_lock      Cargo.lock
cargo_rev       Cargo.toml v0.8.0 2f5bd586d4bb20c90362bb6f5698b7f64057ba4e
cargo_lock_rev  Cargo.lock v0.8.0 2f5bd586d4bb20c90362bb6f5698b7f64057ba4e
npm_tag         package.json
npm_lock        bun.lock
mirror_ref      ncp/.mirror-ref
mirror_rev      ncp/.mirror-rev v0.8.0 2f5bd586d4bb20c90362bb6f5698b7f64057ba4e
python_wire     backend/protocol.py v0.8.0
repin_cmd       scripts/sync_ncp_mirror.sh {TAG} {REV}
```

`cargo_rev`, `cargo_lock_rev`, and `mirror_rev` bind a consumer-declared release
label to one lowercase 40-hex revision. For `mirror_rev`, the pin file contains
exactly that revision (optionally followed by one final LF); tag strings, branch
names, abbreviated hashes, whitespace, and extra lines fail the checker. This lets a
vendored mirror follow an immutable pushed candidate revision without pinning
movable `main` or requiring a premature tag. It does **not** make that candidate a
release: the offline checker reports the declared label and verifies the local pin
bytes, but cannot prove that a tag exists or resolves to the declared commit.

`repin-ncp.sh <tag>` has the stronger local-checkout boundary for every revision
descriptor: it requires the canonical tag in the local NCP checkout, resolves its
peeled 40-hex commit, supplies `{TAG}` and `{REV}` to a consumer-owned `repin_cmd`,
and updates the descriptor metadata after the command succeeds. The custom command
must atomically synchronize the mirror and write its revision pin; post-repin
verification fails if either remains stale. The generic script never hand-edits
vendored protocol content, runtime wire constants, commits, pushes, or tags.

Keep `python_wire` beside a mirror descriptor when the consumer has an independent
runtime implementation. Advancing mirror bytes alone cannot hide a stale runtime
wire: the checker continues to fail until the consumer completes and tests the
breaking migration.

## Known consumer inventory

| Consumer | Current boundary | Native 1.0 status |
|---|---|---|
| Engram | explicit local native-1.0 migration in progress; frozen 0.8 inventory retained as history | not installed-artifact/live certified |
| crebain | Rust/npm wire-0.8 pins and hardcoded wire/hash | not migrated/certified |
| crebain-galadriel-producer | wire-0.8 dependency surface | not migrated/certified |
| galadriel | exact wire-0.8 revision and fixtures | not migrated/certified |
| haldir | immutable `haldir-ncp08` compatibility surface | add parallel `haldir-ncp10`; retain 08 evidence |
| prisoma | observer client on wire 0.8 | not migrated/certified |

Migration ownership stays with each consumer. Protocol core must not add
consumer-specific classes, topics, fields, or safety semantics.

## Package notes

- `ncp-core` and `ncp-zenoh` are Rust candidate crates.
- `@sepahead/ncp` contains independently implemented TypeScript validation/client
  decisions; WebSocket is experimental.
- `ncp-python` and `ncp-cpp` expose Rust through FFI and are not independent peers.
- `ncp-gateway` requires a native 1.0 backend.

The RC packages are not published stable artifacts. Do not replace an immutable
consumer release pin with `main` or a workspace path and call that migration.
