# NCP agent instructions

These rules apply to every automated or human change in this repository.

## Read first

Read [`README.md`](README.md), [`NEURO_CYBERNETIC_PROTOCOL.md`](NEURO_CYBERNETIC_PROTOCOL.md),
[`docs/1.0-scope.md`](docs/1.0-scope.md), [`SECURITY.md`](SECURITY.md), and
[`RELEASE_READINESS.md`](RELEASE_READINESS.md) before changing protocol, security,
transport, packages, conformance, migration, or claims.

## Current boundary

Repository HEAD is the unreleased, release-blocked `1.0.0-rc.1` candidate: wire
`1.0`, compact proto contract hash `163acc57d8a62b66`. `v0.8.0` is the latest
immutable release and is a different wire. Never imply that changing manifests,
passing local tests, or freezing a candidate baseline releases or certifies 1.0.

The frozen Engram wire-0.8 inventory remains historical migration input. Engram has
an explicit native-1.0 migration in progress, but that worktree is not installed-
artifact or live certification. Never infer migration from copied protocol files or
create a silent consumer-specific fork; update and verify the consumer's runtime,
descriptor, fixtures, and transport behavior together.

## Normative changes

The precedence and complete source list are generated in
[`contract/manifest.v1.json`](contract/manifest.v1.json). Assume a change is
wire-visible unless proved otherwise. Update proto, Rust types, JSON Schemas,
canonical and behavior vectors, conformance manifest, generated TypeScript, FFI
fixtures, compact hash, candidate baseline, migration notes, and all affected docs
as one reviewed change.

Do not hand-edit generated schemas, generated TypeScript types, copied testdata, or
generated manifests. Change the source and run the generator. The compact
`CONTRACT_HASH` is not the complete normative SHA-256 digest.

No unknown/default value may grant identity, authority, capability, channel,
security, plant, lifecycle, or operation success. JSON limits apply before semantic
allocation. Missing evidence and not-run gates stay failures, not passes.

## Security, safety, and science

- Payload identity never authenticates itself; bind it to the verified transport
  principal and default-deny manifest.
- `production-secure` cannot downgrade. `dev-loopback-insecure` is loopback/UDS
  only and visibly insecure.
- Active action and mutating RPCs require a matching live session epoch and bounded
  authority lease; step/run/close also require idempotency context and receipts.
- Plant profiles are content-addressed. The body is final actuator authority. NCP
  ESTOP is not physical certification and no universal zero-safe action exists.
- Simulation outputs remain `calibrated_posterior=false` and
  `is_simulation_output=true`; never claim paper reproduction or posterior
  calibration.
- External-model advice is non-normative and cannot certify protocol, security,
  safety, interoperability, scale, or release readiness.

## Required verification

Run focused tests while editing and [`scripts/check.sh`](scripts/check.sh) before a
release-candidate handoff. The complete local gate includes Rust fmt/clippy/tests,
Python wheel and tests, C/C++ ABI, TypeScript generation/build/corpus, proto/schema
parity, exact mandatory manifest coverage, frozen candidate baseline, security and
plant profiles, package archives, dependency policy, and Buf.

External live mTLS/ACL/cert rotation/revocation, two installed independent non-Rust
peers, fault/soak, duration fuzz/sanitizers, performance certification, signatures,
SBOM/provenance, clean-room reproduction, and all six consumer certifications are
distinct pre-release gates. Record them as **NOT RUN** until exact evidence exists.
Publication follows those gates; post-publication install and emergency-revocation
validations are a separate non-blocking phase.

## Repository hygiene

Use `rg` for search, `apply_patch` for edits, preserve unrelated work, and never
weaken a guard merely to make a test pass. Historical 0.8 documents may retain old
values only when explicitly labelled frozen history. Current documents must use the
candidate/release distinction consistently.
