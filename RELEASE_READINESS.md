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
| Universal bounded JSON | generic frame, depth, node, member, array, key, string, number, and channel bounds are implemented in Rust and independent TypeScript; FFI replay and the dependency-free PyNEST JSONL reader exercise them | the declared `max_metadata_entries=256` ceiling has no accepted message-class/path assignment; ADR-003 proposes `OpenSession.bindings[*].entity.meta`, while Rust/TypeScript lack that preallocation rule and Python applies a post-parse name heuristic; ratification, rebaseline, class/path parity, and live/fuzz duration remain unresolved |
| Identity/security/session/authority/idempotency/receipt model | protocol/core decisions implemented with negative corpus | Zenoh transport-authenticated peer binding unavailable; `open_secure` fails closed |
| Plant profile, safety governor, action buffer, ESTOP | deterministic candidate tests exist | checked codec paths still invent missing midpoint/zero values, permit sparse components, and select units by mapping order; installed-profile validation is not integrated into Active admission, and its current `PlantCommand` projection cannot carry units; correction, rebaseline, body integration, and every consumer safety case remain unresolved |
| Candidate JSON baseline `v1.0.0` | regenerated and exact-verified against the current schemas/vectors | candidate audit snapshot only; never a tag or release proof |
| Candidate package builds/install smoke | five Rust archives, one Linux abi3 wheel, one Python sdist, and two npm tarballs were built twice as applicable and verified for historical source `ef357d20692f707e185495dcfd16b16556fec264` on 2026-07-15 | current archive-alone Cargo metadata executes and observes the affected Zenoh registry fallback; the injected-root run is only `CONDITIONAL_PASS`, while self-contained resolution stays `OPEN_FAIL_CLOSED` and `NO_GO`; immutable multi-OS/ABI install matrix and public-registry ownership remain required |
| Audit and traceability controls | deterministic OPEN threat register, complete tracked-file latent-path inventory, and generated 117-requirement local graph are machine-checked | local bookkeeping does not resolve threats, validate semantic edge adequacy, or replace independent review |
| Supply-chain and candidate dossier | current local evidence selects fixed `lz4_flex 0.11.6` through one exact reviewed Zenoh transport backport; the earlier held, one-platform dossier passed its checks at a superseded source and records `release_authorized=false` | Cargo does not verify the backport SSH signature, a root patch does not propagate from a published library dependency, and final release-bound multi-platform artifacts, publisher signatures, registry ownership, independent clean-room reproduction, and release authorization remain **NOT RUN** |
| Local convergence | generated artifact locks candidate identities, `NO_GO`, ten NOT-RUN non-local gates, a historical six-surface handoff inventory across five canonical consumer repositories, the nine exact role subjects, an auxiliary non-peer importer inventory, and post-publication checks | predecessor gates and all nine exact consumer/extension role qualifications remain unresolved; neither a surface nor an importer is a role receipt |
| Package/runtime identity | package, wire, compact proto, complete normative digest, and RC build sentinel exposed; coherence gate implemented | `unreleased-worktree` is deliberately non-certifying |

B01 is still `IN_PROGRESS`. Its maintained allocation oracle is intentionally
`INCOMPLETE_FAIL_CLOSED` and `NOT_REVIEWED`, with a zero reviewed-assignment
digest. The explicit local and hosted review-candidate checks admit only that
tuple, run the strict architecture checks and bound probes, and relax only the
final allocation-completeness requirement. Their pass is local draft-integrity
evidence. It is not ADR acceptance, B01 completion, release authorization,
external evidence, or independent review. The review-candidate mode rejects a
completed allocation state so that transition to the normal complete gate must
be deliberate.

The complete `scripts/check.sh` gate and hosted CI run
[`29414498370`](https://github.com/sepahead/NCP/actions/runs/29414498370) passed for
exact source `ef357d20692f707e185495dcfd16b16556fec264`, tree
`940e5de1ee5435ceb77485f94070e3f894b94c66`, on 2026-07-15. The lock
uses the non-yanked `spin` 0.9.9/0.10.1 replacements. The runs covered the local
package, binding, bounded-ingress, corpus, archive, dependency-policy, and protobuf
matrix. This is time-bound preflight evidence, not a release receipt. The generated
normative identity and candidate baseline match the checked source cut.

The held local-convergence artifact retains the historical six handoff surfaces
that its current candidate gate enumerates across five canonical consumer
repositories. That inventory does not satisfy the nine exact role qualifications
listed below. `pid-rs` is not an NCP peer and receives no role receipt.

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

The current root and quarantined-probe locks select fixed `lz4_flex 0.11.6`
through `zenoh-transport 1.9.0` backport revision
`6b93b15d0795748b7f76c72eae07f1cda517e762`. This removes
`RUSTSEC-2026-0041` from those resolved graphs. It does not revise the historical
held dossier above. Cargo does not verify the Git SSH signature, and a Cargo patch
does not propagate from a published library dependency. Final package design,
installed artifacts, signatures, SBOM/provenance, and independent reproduction
remain required.

The normalized `ncp-zenoh` and `ncp-gateway` archive locks demonstrate the
consequence: without a consuming-root patch, they select affected
`lz4_flex 0.10.0`. The local archive checker executes Cargo metadata and observes
that failure, then applies and verifies the exact backport at its test root before
compilation. The patched run is `CONDITIONAL_PASS`; self-contained distribution
remains `OPEN_FAIL_CLOSED` and `NO_GO`.

The stable Zenoh adapter still cannot bind a callback-visible authenticated
transport principal for `production-secure`. This implementation prerequisite and
the external pre-release gates keep the candidate at `NO_GO`.

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
- native installed-artifact qualification for all nine exact role subjects:

  - Engram simulation responder
  - Engram plant commander
  - Haldir NCP commander
  - Haldir Galadriel-assessment receiver
  - Galadriel NCP observer
  - Galadriel raw-advisory publisher
  - Crebain body
  - Crebain Galadriel-producer surface
  - Prisoma NCP observer

  A historical surface or auxiliary importer entry is not a role receipt.

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

Engram has an explicit local native-1.0 migration in progress. Qualification of
its installed responder and commander roles and its live transport is **NOT RUN**.
The other five historical handoff surfaces remain on wire 0.8. None of the nine
required role subjects is qualified for 1.0. The frozen Engram wire-0.8 inventory
remains historical migration input. It does not describe the mutable migration
worktree. `ncp-gateway` is a same-wire 1.0 Rust/Python edge. It cannot make an
unmigrated 0.8 Python backend compatible. The separate migration translator is a
labeled terminating gateway. It is ineligible for native 1.0 qualification.
The PhD thesis counterexample harness is an auxiliary pinned wire-0.8 importer,
not an installed peer or role subject.

## Release authorization

A `v1.0.0` tag is permitted only after all required pre-release rows are passed,
every report contains the exact normative and corpus digests with no applicable
skip, all packages self-identify consistently, all nine exact installed role
subjects have qualifying role receipts, and the signed release dossier is
independently reproduced. The required post-release validations begin after
publication. Until the pre-release threshold:

- do not create or move a release tag;
- do not publish crates/npm/wheels/binaries as stable 1.0;
- do not call `1.0.0-rc.1` production-ready or certified;
- do not backfill missing evidence with model review or inference.
