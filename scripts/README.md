# NCP maintenance scripts

These tools maintain the unreleased, release-blocked NCP `1.0.0-rc.1` candidate.
They do not publish, sign, tag, or convert a local pass into external certification.

## Contract and conformance

| Script | Purpose |
|---|---|
| `check.sh` | complete local Rust/Python/C++/TypeScript/proto/schema/profile/package preflight; never release authorization |
| `generate_contract_manifest.py [--write]` | exact normative source list and complete SHA-256 digest |
| `generate_conformance_manifest.py [--write]` | mandatory vector inventory, clauses, applicability, source hashes, corpus digest |
| `check_proto_schema_parity.py` | protobuf ↔ JSON Schema fields/types/enums |
| `check_conformance_vectors.py` | canonical JSON and excluded offline binary fixtures |
| `check_behavior_vectors.py` | installed Python-wheel replay with exact manifest coverage |
| `check_cross_language_canonical_json.py` | require exact canonical bytes for all 16 ordered pairs across the 14 stable all-surface wire vectors; Python/C are disclosed Rust FFI wrappers |
| `python3 -m unittest -v e2e.test_bounded_json` | dependency-free hostile ingress checks for the PyNEST JSONL client before generic decoding |
| `check_profile_digests.py` | independent Python replay of portable security-state and plant-profile digest vectors |
| `check_released_baselines.py [--self-test]` | read-only exact path/mode/blob verification of every registered released baseline against its bound annotated tag object, peeled commit, and subtree |
| `check_buf_breaking.py [--self-test]` | select the latest verified same-major annotated release for Buf, or explicitly report that an initial major has no released baseline |
| `check_buf_generator_pins.py [--self-test]` | require exact reviewed BSR remote-plugin versions, positive revisions, and output directories in `buf.gen.yaml` |
| `check_wire_baseline.py` | additive compatibility, freeze, and exact candidate snapshot verification |
| `check_schema_defaults.py` | reject optimistic or type-invalid generated defaults |
| `check_release_gates.py [--self-test]` | validate distinct pre-release gates and non-blocking post-publication checks; `--require-release-allowed` fails closed in tag workflows while the candidate hold is set |
| `check_dependency_exposure.py [--self-test]` | bind the reviewed Zenoh/lz4 versions and resolved Cargo features; fail if defaults or vulnerable transport compression becomes active |
| `generate_supply_chain_evidence.py [--self-test] [--check]` | reproducibly inventory locked dependencies/features/generators/assets, CycloneDX 1.6 components, licenses, and applicable advisories; local evidence only, never signed release provenance |
| `generate_convergence_manifest.py [--self-test] [--check]` | keep the local NO_GO boundary, open secure-adapter prerequisite, ten external pre-release handoffs, consumers, and post-publication checks machine-exact |
| `generate_audit_artifacts.py [--self-test] [--check\|--write]` | check or deterministically replace the OPEN threat register, per-file latent-path inventory, and requirement traceability graph |
| `check_audit_artifacts.py [--self-test]` | semantically validate generated audit artifacts and reject missing, stale, optimistic, or unreviewed entries |
| `check_handoff_review.py [--self-test]` | freeze the non-comment T000–T119 review content and source index while allowing only reviewer comments; never authorizes release |
| `generate_max_effort_handoff_index.py SOURCE [--output PATH]` | extract the exact 20-lens/T000–T145 index from the external schema-2.0 handoff using a strict stdlib parser |
| `generate_max_effort_review_template.py [--check]` | reproduce the NO_GO 146-task review while preserving reviewer comments |
| `check_max_effort_handoff_review.py [--self-test]` | freeze the max-effort source/audit identities and all non-comment review content; all tasks and lenses remain OPEN |
| `generate_file_review_ledger.py [--self-test] [--check]` | reproduce the exact 21-column, Git-blob-bound 793-file internal-review ledger without treating it as independent review or release evidence |
| `plot_perf.py [--self-test] [--check]` + `requirements-plot.txt` | deterministically reproduce explicitly non-normative historical SVGs and reject partial/mislabeled benchmark inputs |
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
| `build_candidate_dossier.py --source-revision REV --output DIR` | build exact archived source into twice-compared Rust/npm/Python candidate packages, smoke them, bind hashes/SBOM/toolchains, and emit an unsigned held dossier; never tags or publishes |
| `prepare_advisory_database.py --source-database DIR --destination DIR` | clone one current, verified RustSec database locally and rewind a disposable copy to the evidence-pinned revision for deterministic replay |
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
Standard npm re-pins regenerate only the Bun lockfile and disable lifecycle scripts.
The consumer command remains responsible for synchronizing its own mirror. Before
any mutation, the repinner requires every discovered consumer to be a clean Git
root on `main`, requires every descriptor and declared target to be tracked, and
rejects sparse or hidden index entries. A mutating run holds an advisory
`.git/ncp-repin.lock` in every consumer; other consumer tooling must honor that lock.
It then rechecks the fleet before writing. A failure restores tracked files, index
state, and transaction-created Git-visible paths while branch and `HEAD` still
match the recorded state. If either identity changes concurrently, rollback refuses
to rewrite that repository and reports the manual recovery requirement. Successful
output suggests staging only the exact paths changed by the run. Use
`repin-ncp.sh --dry-run TAG [BASE]` to perform the generic preflight and print
declared paths/actions without running commands, acquiring locks, or writing files.

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
