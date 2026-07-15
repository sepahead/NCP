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
| Proto/schema/canonical-vector parity | complete matrix passes locally and in hosted CI at exact implementation cut `f08c2ad` | source-bound tests are not signed release-artifact or independent evidence |
| Mandatory self-describing corpus | current manifest has 282 required vectors (275 stable, 7 migration), 13 requirements, and zero-skip exact-set enforcement; complete local and hosted replay passed at `f08c2ad` after the lifecycle/schema correction | signed external conformance reports remain required |
| Ordered canonical bytes and stable integers | local harness covers 14 all-surface stable vectors across 16 ordered Rust/TypeScript/Python-FFI/C-FFI pairs; TypeScript discovers 45 reachable stable-integer schema paths and tests exact/unsafe boundaries | Python and C share Rust code; installed independent peers, complete normative traffic, alternate engines/platforms, and signed reports remain required |
| Universal bounded JSON | implemented in Rust and independent TypeScript; FFI replay and the dependency-free PyNEST JSONL reader are gated before generic decoding | live/fuzz duration still required |
| Identity/security/session/authority/idempotency/receipt model | protocol/core decisions implemented with negative corpus | Zenoh transport-authenticated peer binding unavailable; `open_secure` fails closed |
| Plant profile, safety governor, action buffer, ESTOP | implemented with deterministic tests | non-certifying; each consumer needs a safety case |
| Candidate JSON baseline `v1.0.0` | regenerated and exact-verified against the current schemas/vectors | candidate audit snapshot only; never a tag or release proof |
| Candidate package builds/install smoke | packageable archives and local installs passed for exact implementation cut `f08c2ad` on 2026-07-14 | immutable multi-OS install matrix and public-registry ownership remain required |
| Audit and traceability controls | deterministic OPEN threat register, complete tracked-file latent-path inventory, and 100-node local requirement graph are machine-checked | local bookkeeping does not resolve threats, validate semantic edge adequacy, or replace independent review |
| Supply-chain and candidate dossier | deterministic inventory, CycloneDX 1.6 SBOM, license/vulnerability reports, provenance policy, and exact-revision double-build workflow are implemented | final exact-source dossier, hosted attestations, signatures, registry ownership, clean-room reproduction, and multi-platform artifacts remain NOT RUN |
| Local convergence | generated artifact locks candidate identities, `NO_GO`, ten NOT-RUN non-local gates, six consumer handoffs, and post-publication checks | predecessor gates and cross-repository consumer certifications remain unresolved |
| Package/runtime identity | package, wire, compact proto, complete normative digest, and RC build sentinel exposed; coherence gate implemented | `unreleased-worktree` is deliberately non-certifying |

The complete `scripts/check.sh` gate and hosted CI run
[`29366777050`](https://github.com/sepahead/NCP/actions/runs/29366777050) passed for
exact source `f08c2ad5f68bab0a583db918439660636996ca07` on 2026-07-14. The lock
uses the non-yanked `spin` 0.9.9/0.10.1 replacements. The runs covered the local
package, binding, bounded-ingress, corpus, archive, dependency-policy, and protobuf
matrix. They provide an immutable source revision, but no signatures,
multi-platform environment set, final artifact dossier, or independent
reproduction. This is time-bound preflight evidence, not a release receipt. The
generated normative identity and candidate baseline match the checked source cut.
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
- reproducible artifact comparison, checksums, vulnerability report, license
  notices, signed SBOM/provenance, and signature verification;
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
