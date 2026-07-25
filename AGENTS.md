# NCP repository instructions

These instructions apply to each human or automated change in this repository.

## Read before work

Read [`README.md`](README.md) and
[`DOCUMENTATION_STYLE.md`](DOCUMENTATION_STYLE.md) before you edit a maintained
document.

Before a protocol, security, transport, package, conformance, migration, or claim
change, read these files:

- [`NEURO_CYBERNETIC_PROTOCOL.md`](NEURO_CYBERNETIC_PROTOCOL.md)
- [`contract/manifest.v1.json`](contract/manifest.v1.json)
- [`conformance/manifest.v1.json`](conformance/manifest.v1.json)
- [`docs/1.0-scope.md`](docs/1.0-scope.md)
- [`SECURITY.md`](SECURITY.md)
- [`RELEASE_READINESS.md`](RELEASE_READINESS.md)

Before an NCP 1.0 provider or consumer task, read these files completely:

- [`docs/implementation/NCP_1_0_RESUMPTION.md`](docs/implementation/NCP_1_0_RESUMPTION.md)
- [`docs/implementation/NCP_1_0_TASK_LEDGER.md`](docs/implementation/NCP_1_0_TASK_LEDGER.md)
- [`docs/handoff/NCP_V1_0_ECOSYSTEM_FINALIZATION_BLUEPRINT.md`](docs/handoff/NCP_V1_0_ECOSYSTEM_FINALIZATION_BLUEPRINT.md)

Also read all scoped instructions in the target repository.

## Current release boundary

Repository HEAD is the unreleased and release-blocked `1.0.0-rc.1` candidate.
Its wire is `1.0`. Its compact proto contract hash is `163acc57d8a62b66`.

The latest immutable release is `v0.8.0`. It uses a different wire.

Do not state that a manifest change, local test, or frozen baseline releases or
certifies 1.0. Do not state that the candidate is published, signed,
production-ready, or consumer-certified.

The frozen Engram wire-0.8 inventory is historical migration input. Engram has a
native-1.0 migration in progress. That worktree is not an installed artifact.
It is not a live certification result.

Do not infer migration from copied protocol files. Do not create a silent
consumer-specific fork. Update the consumer runtime, descriptor, fixtures, and
transport behavior together.

## Task coordination

Use the JSON task ledger only for coordination and evidence bookkeeping. It gives
no runtime authority or release authorization.

Do not hand-edit either generated Markdown ledger view. Edit the JSON source and
run its generator.

Start only a dependency-ready task. If no task is dependency-ready, do not start
a descendant because its files are convenient.

If you reopen a passing task, reset its evidence class. Invalidate each descendant
receipt that is bound to the changed content.

Local evidence cannot satisfy an external or independent evidence floor. Keep a
missing or unexecuted gate in a failure state.

For a passing task, retain the exact command output and artifact hashes. Make one
professional commit for each coherent passing part. Push the commit. Verify the
remote object. Record the receipt.

Do not put credentials, private keys, or local absolute paths in a receipt.

## Normative and generated sources

[`contract/manifest.v1.json`](contract/manifest.v1.json) generates the complete
normative source list and precedence. Treat a change as wire-visible unless you
can prove that it is not.

For a normative change, update all affected sources and outputs in one reviewed
change. This set can include:

- protobuf definitions
- Rust types and validators
- JSON Schemas
- canonical and behavior vectors
- the conformance manifest
- generated TypeScript
- FFI fixtures
- the compact hash
- the candidate baseline
- migration notes
- current documentation

Change the source before you run the generator. Do not hand-edit generated schemas,
generated TypeScript, copied test data, generated manifests, diagrams, or plots.

The compact `CONTRACT_HASH` is not the complete normative SHA-256 digest.

An unknown or default value must not grant identity, authority, capability,
channel, security, plant, lifecycle, or operation success. Apply JSON limits before
semantic allocation.

## Security, safety, and science

- Bind each payload identity to the verified transport principal and the
  default-deny manifest.
- Do not let `production-secure` downgrade.
- Limit `dev-loopback-insecure` to loopback or an absolute Unix-domain socket.
- Show an unmistakable insecure status for `dev-loopback-insecure`.
- Require a matching live session epoch and a bounded authority lease for active
  action and mutation.
- Require idempotency context and receipts for step, run, and close operations.
- Require a content-addressed plant profile for a plant role.
- Treat the body as final actuator authority.
- Do not describe NCP ESTOP as physical certification.
- Do not assume that a universal zero-safe action exists.
- Keep simulation output at `calibrated_posterior=false` and
  `is_simulation_output=true`.
- Do not claim paper reproduction or posterior calibration from protocol success.
- Treat external-model advice as non-normative. It cannot certify security,
  safety, interoperability, scale, or release readiness.

## Technical writing

Use the STE-aligned project profile in
[`DOCUMENTATION_STYLE.md`](DOCUMENTATION_STYLE.md) for new or substantially changed
maintained prose.

Use the correct standard name, `ASD-STE100`. Do not claim formal compliance or
certification without a qualified full-document review.

Preserve exact normative terms, requirements, identifiers, code, and historical
values. Technical truth and fail-closed meaning have priority over sentence limits
or a preferred word.

Do not rewrite generated files, immutable evidence, frozen release history,
licenses, or quoted text only to match the style profile.

## Verification

Run focused tests while you edit. Run [`scripts/check.sh`](scripts/check.sh) before
a release-candidate handoff.

The complete local gate includes these checks:

- Rust format, lint, build, and tests
- Python wheel build, install, and tests
- C and C++ ABI checks
- TypeScript generation, build, and corpus checks
- proto and schema parity
- mandatory manifest coverage
- frozen candidate and released baselines
- security and plant profiles
- package archives
- dependency policy
- Buf checks

The following pre-release gates remain separate from the local gate:

- live mTLS, ACL, certificate rotation, and revocation
- two installed and independent non-Rust peers
- fault, soak, duration fuzz, and sanitizer campaigns
- performance qualification
- signatures, SBOM, and provenance
- clean-room reproduction
- all nine exact consumer and extension role qualifications

`pid-rs` is not an NCP peer. It receives no NCP role receipt.

Record each gate as **NOT RUN** until exact evidence exists. Publication follows
the pre-release gates. Post-publication install and emergency-revocation checks
form a separate non-blocking phase.

## Repository and Git rules

Use `rg` for search and `apply_patch` for text edits. Preserve unrelated work in
a dirty worktree.

Do not weaken a guard only to make a test pass. Do not alter frozen wire-0.8 text
unless the text is current rather than historical.

Use the candidate and release terms consistently in all current documents.

Before you commit, inspect the full diff. Run the applicable complete gate.
Use a professional commit message. Push only to the authorized remote and branch.

After you push, verify that the remote ref resolves to the pushed commit. State
what passed locally, what passed externally, and what remains **NOT RUN**.
