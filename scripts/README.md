# NCP maintenance scripts

These tools maintain the unreleased, release-blocked NCP `1.0.0-rc.1` candidate.
They do not publish, sign, tag, or convert a local pass into external certification.

## Contract and conformance

| Script | Purpose |
|---|---|
| `check.sh` | complete local Rust/Python/C++/TypeScript/proto/schema/profile/package gate |
| `generate_contract_manifest.py [--write]` | exact normative source list and complete SHA-256 digest |
| `generate_conformance_manifest.py [--write]` | mandatory vector inventory, clauses, applicability, source hashes, corpus digest |
| `check_proto_schema_parity.py` | protobuf ↔ JSON Schema fields/types/enums |
| `check_conformance_vectors.py` | canonical JSON and excluded offline binary fixtures |
| `check_behavior_vectors.py` | installed Python-wheel replay with exact manifest coverage |
| `python3 -m unittest -v e2e.test_bounded_json` | dependency-free hostile ingress checks for the PyNEST JSONL client before generic decoding |
| `check_profile_digests.py` | independent Python replay of portable security-state and plant-profile digest vectors |
| `check_released_baselines.py [--self-test]` | read-only exact path/mode/blob verification of every registered released baseline against its bound annotated tag object, peeled commit, and subtree |
| `check_buf_breaking.py [--self-test]` | select the latest verified same-major annotated release for Buf, or explicitly report that an initial major has no released baseline |
| `check_buf_generator_pins.py [--self-test]` | require exact reviewed BSR remote-plugin versions, positive revisions, and output directories in `buf.gen.yaml` |
| `check_wire_baseline.py` | additive compatibility, freeze, and exact candidate snapshot verification |
| `check_schema_defaults.py` | reject optimistic or type-invalid generated defaults |
| `check_release_gates.py [--self-test]` | validate distinct pre-release gates and non-blocking post-publication checks |
| `check_handoff_review.py [--self-test]` | freeze the non-comment T000–T119 review content and source index while allowing only supervisor comments; never authorizes release |
| `sync_rust_package_testdata.py [--write]` | exact crate-local corpus/proto/schema copies |
| `check_markdown_links.py [--self-test]` | current indexed and non-ignored untracked Markdown target/anchor integrity; byte-frozen baseline Markdown is verified against its tag instead |

## Security, plant, and packages

| Script | Purpose |
|---|---|
| `validate_security_profile.py` | fail-closed named-profile/authority rules and portable security-state digest implementation |
| `check_acl_template.py` | offline Zenoh ACL structure and negative mutations |
| `verify_acl_deployment.py` | router mTLS/ACL nonce-delivery probe; it cannot prove NCP payload-to-peer identity binding, and `--self-test` is logic only |
| `render_acl_template.py` | atomically render a validated exact realm and concrete action session |
| `check_rust_packages.py --offline` | package/extract/build/test publishable Rust crates without workspace leakage |
| `check-version-coherence.sh` | package/wire/compact-hash metadata coherence |
| `../ncp-ts/scripts/build-release.mjs --source-revision REV --output DIR` | archive one exact 40-hex `HEAD`, inject and verify the shared Rust/TypeScript build identity, and emit smoke-tested root+nested npm tarballs plus a hash receipt; never publishes |

## Consumer tooling

`check-consumer-pins.sh` and `repin-ncp.sh` discover `.ncp-consumer` descriptors.
They are pin-management tools, not compatibility certification. Engram's explicit
native-1.0 migration is in progress and intentionally makes a v0.8 pin check fail
until its descriptor/runtime/pin move coherently; the other five known consumers
remain on immutable `v0.8.0`. Never repin a consumer to movable `main`, and never
call an RC pin a completed installed-artifact certification.

Use `mirror_rev <pin-file> <release-label> <40-hex-revision>` for a vendored mirror
that must bind immutable source bytes instead of a tag string. The read-only checker
requires the exact revision in the pin file and reports the consumer-declared label;
it does not prove that the label exists upstream. For a coordinated tagged re-pin,
`repin-ncp.sh` resolves the local tag, substitutes both `{TAG}` and `{REV}` in the
consumer's `repin_cmd`, refreshes descriptor metadata, and then runs the checker.
The consumer command remains responsible for synchronizing its own mirror.

```bash
scripts/check-consumer-pins.sh v0.8.0
scripts/test_consumer_pins.sh
```

## Benchmarks

The `bench_*.py` and plotting scripts are informative developer measurements. Most
require PyNEST or platform-specific dependencies. Historical results do not satisfy
the candidate's release-bound performance and resource gate; a final campaign must
record source/artifact/config/toolchain/environment digests.

## Complete local run

```bash
scripts/check.sh
```

Required tools are Cargo/Rust 1.88+, Python 3, a C++17 compiler, Bun/npm, Buf, and
`cargo-deny`. Any missing required tool is a failed local gate. External security,
independent-peer, fault/soak, fuzz/sanitizer, signature/SBOM, clean-room, publication,
and consumer gates remain **NOT RUN** until separately evidenced.

The released-baseline check requires the complete local objects and annotated refs
for `v0.5.0` through `v0.8.0`. It is read-only in normal mode. Its registry binds
Git identities; it neither verifies tag signatures nor makes a new release claim.
The Buf gate consumes only those verified rows. The initial `ncp.v1` candidate has
no released v1 row and is intentionally not compared with `ncp.v0`; after a v1
release is registered, later v1 work compares with the greatest registered v1 tag's
peeled commit.
