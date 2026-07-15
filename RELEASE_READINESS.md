# NCP 1.0 release-readiness ledger

**Verdict: BLOCKED — do not tag or publish.** Repository HEAD is the unreleased
`1.0.0-rc.1` candidate (wire `1.0`, compact proto hash
`163acc57d8a62b66`). A version string and local test pass are not a release.

The canonical machine policy is
[`contract/release-gates.v1.json`](contract/release-gates.v1.json). Every required
pre-release gate must refer to the same immutable source, normative digest, package
hashes, and environment manifest. `NOT RUN`, skipped, stale, source-tree-only, or
unsigned evidence is a failure for initial release.

## Candidate evidence

| Gate | Candidate state | Release meaning |
|---|---|---|
| Released baseline and historical mirror boundary | read-only gate binds the annotated tag object, peeled commit, fixed path, and exact subtree for every `v0.5.0`–`v0.8.0` baseline; Buf explicitly reports that initial package `ncp.v1` has no released same-major comparison target and does not compare the intentional major break with `ncp.v0` | establishes immutable local migration/history input only; it is not tag-signature, artifact, or consumer evidence; later v1 candidates must compare with the latest registered v1 release |
| Stable/excluded surface and registries | implemented; generated digest gate present | not a release by itself |
| Proto/schema/canonical-vector parity | complete matrix passes locally and in hosted CI at exact source boundary `ef357d20692f707e185495dcfd16b16556fec264` | source-bound tests are not release-artifact or independent evidence |
| Mandatory self-describing corpus | current manifest has 282 required vectors (275 stable, 7 migration), 13 requirements, and zero-skip exact-set enforcement; complete local and hosted replay passed at `ef357d20692f707e185495dcfd16b16556fec264` | signed external conformance reports remain required |
| Ordered canonical bytes and stable integers | local harness covers 14 all-surface stable vectors across 16 ordered Rust/TypeScript/Python-FFI/C-FFI pairs; TypeScript discovers 45 reachable stable-integer schema paths and tests exact/unsafe boundaries | Python and C share Rust code; installed independent peers, complete normative traffic, alternate engines/platforms, and signed reports remain required |
| Universal bounded JSON | implemented in Rust and independent TypeScript; FFI replay and the dependency-free PyNEST JSONL reader are gated before generic decoding | live/fuzz duration still required |
| Identity/security/session/authority/idempotency/receipt model | protocol/core decisions implemented with negative corpus | Zenoh transport-authenticated peer binding unavailable; `open_secure` fails closed |
| Plant profile, safety governor, action buffer, ESTOP | implemented with deterministic tests | non-certifying; each consumer needs a safety case |
| Candidate JSON baseline `v1.0.0` | regenerated and exact-verified against the current schemas/vectors | candidate audit snapshot only; never a tag or release proof |
| Candidate package builds/install smoke | five Rust archives, one Linux abi3 wheel, one Python sdist, and two npm tarballs were built twice as applicable and verified for exact source `ef357d20692f707e185495dcfd16b16556fec264` on 2026-07-15 | immutable multi-OS/ABI install matrix and public-registry ownership remain required |
| Audit and traceability controls | deterministic OPEN threat register, complete tracked-file latent-path inventory, and 100-node local requirement graph are machine-checked | local bookkeeping does not resolve threats, validate semantic edge adequacy, or replace independent review |
| Supply-chain and candidate dossier | a held, one-platform, exact-source dossier passed checksums, five applicable comparisons, install/identity/behavior smoke, exact-source verification, a ten-subject SLSA provenance attestation, and an aggregate CycloneDX attestation; `release_authorized=false` | final release-bound multi-platform artifacts, publisher signatures, registry ownership, independent clean-room reproduction, and release authorization remain **NOT RUN** |
| Local convergence | generated artifact locks candidate identities, `NO_GO`, ten NOT-RUN non-local gates, six consumer handoffs, and post-publication checks | predecessor gates and cross-repository consumer certifications remain unresolved |
| Package/runtime identity | package, wire, compact proto, complete normative digest, and RC build sentinel exposed; coherence gate implemented | `unreleased-worktree` is deliberately non-certifying |

The complete `scripts/check.sh` gate and hosted CI run
[`29414498370`](https://github.com/sepahead/NCP/actions/runs/29414498370) passed for
exact source `ef357d20692f707e185495dcfd16b16556fec264`, tree
`940e5de1ee5435ceb77485f94070e3f894b94c66`, on 2026-07-15. The lock
uses the non-yanked `spin` 0.9.9/0.10.1 replacements. The runs covered the local
package, binding, bounded-ingress, corpus, archive, dependency-policy, and protobuf
matrix. This is time-bound preflight evidence, not a release receipt. The generated
normative identity and candidate baseline match the checked source cut.

The separate held-candidate workflow run
[`29414924349`](https://github.com/sepahead/NCP/actions/runs/29414924349) also
passed for that exact source. Artifact
[`8342883563`](https://github.com/sepahead/NCP/actions/runs/29414924349/artifacts/8342883563)
has SHA-256
`b2228a89232e3751a3fc205dbda1f66cc07eac7c1f7811f5cdea0a44d6277ed5`.
Its 19-file dossier has 18 checksum entries and nine package subjects. SLSA
attestation `35446154` covers the exact nine packages plus aggregate checksum
subject (Rekor index `2172913900`; canonical bundle-object SHA-256
`eac629acd68a9e2f63097508655fb9ea77ebdeae192c15818c2a0d8df08be9f5`).
CycloneDX attestation `35446158` covers that aggregate subject (Rekor index
`2172913945`; canonical bundle-object SHA-256
`fc85bb970b4835128f0b1a71818c38a330bd306528b238058aa4d43b6fdff2c9`).
A separate exact-source verifier recomputed all hashes and the ten-subject manifest,
enforced the repository/workflow/source/ref/hosted-runner/predicate constraints,
and confirmed the canonical embedded CycloneDX predicate equals the retained SBOM.
The direct wheels were byte-compared only with each other; the sdist-rebuilt wheel
received a separate install/identity/behavior smoke and was not compared with the
direct wheel. The dossier records `release_authorized=false` and does not supply a
tag, publication, final publisher signatures, multi-platform release artifacts, or
independent clean-room reproduction.

Two source-level holds also remain unchanged: `RUSTSEC-2026-0041` is still present
through Zenoh's resolved `lz4_flex` dependency even though transport compression is
disabled, and the stable Zenoh adapter still cannot bind a callback-visible
transport-authenticated principal for `production-secure`. The candidate therefore
remains `NO_GO`.

Per-task receipts and their exact residual acceptance gaps are indexed in
[`docs/1.0-candidate-receipts.md`](docs/1.0-candidate-receipts.md).

## Required implementation prerequisite

The stable Zenoh callback API used by `ncp-zenoh` does not expose a
transport-authenticated remote principal to the subscriber/queryable handler. The
adapter therefore cannot bind the payload `IdentityClaim` to verified transport
identity through the default-deny authority manifest. `ZenohBus::open_secure`
intentionally fails before opening a session. A callback-visible authenticated
principal (or a different adapter with equivalent verified binding) must be
implemented and locally negative-tested before the live security gate can start.

## Required external pre-release gates

The following are **NOT RUN** and independently block release:

- after the implementation prerequisite above, live `production-secure` mTLS,
  default-deny ACL, wrong-principal/entity/plane, certificate validity, rotation,
  revocation, and downgrade campaign;
- two independently implemented, installed, non-Rust live transport peers without
  Rust decision FFI;
- delay/loss/duplication/reordering/partition/router restart/peer restart/slow
  consumer/observation flood combinations and duration soak/leak evidence;
- duration fuzzing and sanitizers across JSON decoders, state machines, FFI, and
  independent peers;
- release-bound latency/throughput/memory/queue profiles on supported platforms;
- clean installs and full applicable conformance for crates, wheel/sdist, npm, and
  C/C++ artifacts built from one immutable source;
- verified ownership of every intended public package namespace, with unrelated
  registry names resolved or renamed consistently before publication;
- final release-bound reproducible comparison across supported platforms,
  checksums, vulnerability report, license notices, SBOM/provenance, publisher
  signatures, and signature verification; the held one-platform candidate
  attestations above do not satisfy this gate;
- independent clean-room build and core-conformance reproduction;
- native installed-artifact certification for Engram, crebain,
  crebain-galadriel-producer, galadriel, haldir, and prisoma.

## Required post-release validations

The following run only after the tag and artifacts are published. They are required
operational validations, but cannot block their own initial publication:

- install the published artifacts in clean environments and rerun the package smoke;
- exercise the documented emergency-revocation procedure against the published
  release.

A failure invokes the release remediation or revocation procedure and must remain
visible in the release dossier; it does not rewrite the failed validation as a
pre-publication pass.

## Consumer state

Engram has an explicit local native-1.0 migration in progress, but its installed-
artifact and live-transport certification are **NOT RUN**. The other five inventoried
consumers remain on wire 0.8. None of the six is 1.0-certified. The frozen Engram
wire-0.8 inventory remains historical migration input, not a description of its
mutable migration worktree. `ncp-gateway` is a same-wire 1.0 Rust/Python edge and
cannot make an unmigrated 0.8 Python backend compatible. The separate migration
translator is a labelled terminating gateway and is ineligible for native 1.0
certification.

## Release authorization

A `v1.0.0` tag is permitted only after all required pre-release rows are passed,
every report contains the exact normative and corpus digests with no applicable
skip, all packages self-identify consistently, all required consumers accept the
handoff, and the signed release dossier is independently reproduced. The required
post-release validations begin after publication. Until the pre-release threshold:

- do not create or move a release tag;
- do not publish crates/npm/wheels/binaries as stable 1.0;
- do not call `1.0.0-rc.1` production-ready or certified;
- do not backfill missing evidence with model review or inference.
