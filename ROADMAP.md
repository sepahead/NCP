# NCP roadmap

> Repository HEAD is the unreleased, release-blocked `1.0.0-rc.1` candidate
> (wire `1.0`, compact proto hash `163acc57d8a62b66`). The roadmap is evidence-led:
> implementation presence is not certification.

## Candidate foundation

The candidate now has a frozen scope/registry model, exact v0.8 boundary, canonical
JSON/proto/schema parity, explicit security profiles, identity and plane claims,
session epochs, authority leases, idempotent mutations and receipts, bounded JSON,
plant profiles, four-plane queue policy, audit vocabulary, a mandatory
self-describing corpus, independent TypeScript validation, and a labelled
0.8-to-1.0 translation API.

These are source-level foundations. They do not close the release program until
their installed, live, adversarial, and downstream evidence gates pass.

## Workstream state

| Workstream | Candidate state | Next evidence |
|---|---|---|
| 0.8 baseline and mirror boundary | implemented | retain exact drift proof in final dossier |
| 1.0 scope, registries, precedence, full digest | implemented; regenerate at final freeze | independent digest reproduction |
| security profiles and identity binding | profile/core logic implemented; Zenoh callback principal binding unavailable and fail-closed | implement verified peer binding, then run live mTLS/ACL/rotation/revocation campaign |
| authority, reconnect, ESTOP, idempotency | primitives and corpus implemented | live restart/fault matrix |
| JSON limits and mandatory corpus | implemented across Rust/TS/FFI harnesses | fuzz/sanitizer duration and signed reports |
| plant-specific safety | profile/governor/buffer tests implemented | six consumer-owned safety cases |
| independent peers | TypeScript decision code implemented | second non-Rust implementation and secure live matrix |
| package coordination | RC manifests/build scripts implemented | clean multi-platform installed artifacts, reproducibility, SBOM/signatures |
| 0.8 migration gateway | bounded explicit channel mapping implemented | installed 0.8↔1.0 gateway fault/idempotency proof |
| consumer migration | Engram in progress; none certified | finish Engram evidence, then crebain, producer, galadriel, haldir, prisoma |
| 1.0 release | blocked | every required pre-release gate passed against one artifact set |

## Execution order

1. Finish the local candidate freeze: regenerate all derived artifacts, freeze and
   exact-verify `conformance/baseline/v1.0.0`, then pass `scripts/check.sh` without
   required skips.
2. Build immutable candidate crates, wheel/sdist, npm package, and C/C++ artifacts;
   make each self-identify with the same package/wire/normative/corpus/build data.
3. Implement transport-authenticated peer-principal binding for the stable Zenoh
   adapter (or an equivalent stable adapter), add a second genuinely independent
   non-Rust transport peer, and run the full secure live matrix with installed
   artifacts.
4. Run combined fault/restart/backpressure/soak, fuzz/sanitizer, and performance
   campaigns; archive raw logs and environment/toolchain manifests.
5. Migrate the six consumers one by one. A native 1.0 result cannot transit a legacy
   gateway, and each body supplies its own plant profile and safety case.
6. Produce checksums, vulnerability report, licenses, signed SBOM/provenance, and
   independent clean-room reproduction.
7. Only after every report refers to the same source and artifacts, create the
   annotated immutable `v1.0.0` tag and publish; then run post-publication install
   and emergency-revocation validations. Those post-release checks do not block the
   initial tag because their subject does not exist until publication.

## Post-1.0 candidates

Post-1.0 work is not part of the stable candidate unless separately specified and
negotiated. Possible areas include a certified WebSocket binding, a complete bounded
bulk observation envelope, additional transport bindings, stronger durable
idempotency services, signed audit anchoring, and additive plant-profile families.
None may weaken 1.x identity, authority, resource, safety, or scientific boundaries.
