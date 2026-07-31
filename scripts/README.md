# NCP maintenance scripts

These tools maintain the unreleased, release-blocked NCP `1.0.0-rc.1` candidate.
They do not publish, sign, tag, or convert a local pass into external certification.

## Contract and conformance

| Script | Purpose |
|---|---|
| `check.sh` | complete local Rust/Python/C++/TypeScript/proto/schema/profile/package preflight; never release authorization |
| `check_implementation_ledger.py [--self-test]` | validate the exact 60-task implementation DAG, evidence floors, dependency receipts, reopen invalidations, bounded receipt formats, and required B03 allocation coverage. It rejects premature external or independent passes. It has no X05 trust parser, so X05 stays `OPEN` and **NOT RUN**. |
| `generate_implementation_ledger.py [--check\|--write]` | generate the task-ledger view and cross-repository resumption brief from the checked JSON source. Do not edit the generated Markdown. |
| `generate_decision_registry.py [--self-test] [--check\|--write]` | generate the non-normative B01 registry from exact `PROPOSED` ADR bytes. It rejects premature acceptance, rebaselining, or `contract/` promotion. |
| `validate_evidence_schemas.py [--self-test]` | bounded-read and validate the ledger and decision registry with the hash-locked Draft 2020-12 implementation. The same isolated lock supplies Ruff 0.15.21 for B01 Python format and lint checks; neither tool enters a shipped package surface. The validators reject unsupported references, keywords, regexes, formats, vocabularies, and schema drift. Structural validation does not prove external authorship or deployment truth. |
| `selector_closure_codec.py` | provide the bounded canonical codec for the non-normative B01 selector source. It rejects invalid, shared, cyclic, or over-budget input. Its conditional write path uses no-follow reads, parent locking, a single-link temporary inode, directory synchronization, and exact readback. |
| `selector_allocation_inventory.py [--self-test]` | validate the external non-normative allocation inventory, schema, provenance, commitment suites, and known-answer vectors with bounded reads. It records owner-free units, origins, and non-authorizing signals. It does not assign an ADR or decide completeness. |
| `selector_allocation_review.py --self-test` | exercise local review, receipt, promotion, reopen, and generation-state boundaries for the exact semantic subject and source cut. Its unsigned local receipt proves no identity, independence, protocol acceptance, or release authority. |
| `selector_resource_closure.py` | derive the exact resource-access and joint-transaction projection. It enforces one owner, one backing identity, local-only mutation, compare-only foreign access, and exact participant closure. The result is local structural evidence only. |
| `generate_selector_closure_source.py [--self-test] [--check] [--review-candidate] [--refresh-incomplete-authoring [--migrate-v2-empty-allocation-schema-binding --migrate-observer-read-capture-bridge-profile-v1-to-v2]]` | validate and reproduce the expanded and compact B01 sources against their exact inventory, schema, and semantic checks. Normal generation requires complete reviewed allocation provenance. The non-gating candidate mode accepts only the exact fail-closed unreviewed tuple. The two one-use migration switches must occur together. |
| `check_selector_closure.py [--self-test\|--inventory-gap-report\|--review-candidate\|--run-probes\|--probes-only]` | validate the closed B01 model, resource and artifact closure, lifecycle reachability, request-control product, commitments, and hostile mutations. The gap report is read-only and non-authorizing. Candidate mode relaxes only allocation completeness for the exact fail-closed tuple. Probe mode executes content-bound sources with bounded framing and resource limits, but it is not an OS sandbox or runtime-provenance check. |
| `generate_selector_closure_matrix.py [--self-test] [--check]` | generate or compare the non-normative review matrix from a valid compact source. Only the exact fail-closed candidate can render with allocation-only incompleteness. |
| `generate_selector_allocation_proposal.py [--self-test] [--check]` | compile owner-free v4 units into a deterministic review proposal with bound sources, origins, signals, matches, and ambiguity flags. Suggested routes cannot assign ownership, accept an ADR, or grant protocol or release authority. |
| `verify_selector_allocation_portability.mjs [--self-test]` | recompute the declared allocation, semantic, provenance, proposal, and source commitments with only the Node.js standard library. This is local implementation-diversity evidence, not an independent peer or release gate. |
| `check_adr_examples.py [--self-test]` | replay every proposed ADR JSON fence through the independent B04 Python and Node bounded parsers; syntax-only draft evidence, never semantic implementation or acceptance |
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
| `generate_supply_chain_evidence.py [--self-test] [--check]` | reproducibly inventory locked dependencies/features/generators/assets, CycloneDX 1.6 components, licenses, and applicable advisories; `NCP_ADVISORY_DB_PATH` can bind a prepared external database without changing `HOME`; local evidence only, never signed release provenance |
| `generate_convergence_manifest.py [--self-test] [--check]` | keep the local NO_GO boundary, open secure-adapter prerequisite, ten external pre-release handoffs, consumers, and post-publication checks machine-exact |
| `generate_audit_artifacts.py [--self-test] [--check\|--write]` | check or deterministically replace the OPEN threat register, per-file latent-path inventory, and requirement traceability graph |
| `check_audit_artifacts.py [--self-test]` | semantically validate generated audit artifacts and reject missing, stale, optimistic, or unreviewed entries |
| `check_handoff_review.py [--self-test]` | freeze the non-comment T000–T119 review content and source index while allowing only reviewer comments; never authorizes release |
| `generate_max_effort_handoff_index.py SOURCE [--output PATH]` | extract the exact 20-lens/T000–T145 index from the external schema-2.0 handoff using a strict stdlib parser |
| `generate_max_effort_review_template.py [--check]` | reproduce the NO_GO 146-task review while preserving reviewer comments |
| `check_max_effort_handoff_review.py [--self-test]` | freeze the max-effort source/audit identities and all non-comment review content; all tasks and lenses remain OPEN |
| `generate_file_review_ledger.py [--self-test] [--check]` | reproduce the exact 21-column, Git-blob-bound 828-file internal-review ledger without treating it as independent review or release evidence |
| `plot_perf.py [--self-test] [--check]` + `requirements-plot.txt` | deterministically reproduce explicitly non-normative historical SVGs and reject partial/mislabeled benchmark inputs |
| `sync_rust_package_testdata.py [--write]` | exact crate-local corpus/proto/schema copies |
| `check_markdown_links.py [--self-test]` | current indexed and non-ignored untracked Markdown target/anchor integrity; byte-frozen baseline Markdown is verified against its tag instead |

The complete local preflight and hosted CI run
`selector_allocation_review.py --self-test` and
`selector_resource_closure.py`. These local gates do not change any independent,
external, or release gate.

While the maintained allocation oracle has the exact
`INCOMPLETE_FAIL_CLOSED`/`NOT_REVIEWED`/zero-reviewed-digest state, the local
preflight and hosted CI use the explicit `--review-candidate` generator and
checker modes. The checker mode runs all strict architecture validators and all
bound probes. After the probes, it rechecks the semantic sources and every probe
source against the opening snapshots. It relaxes only the final allocation-
completeness requirement. A different incomplete tuple, a complete tuple, a
semantic defect, a source that differs at the final recheck, or a probe failure
rejects. A pass does not complete B01, accept an ADR, prove review, or authorize a
release. When allocation provenance becomes complete and reviewed, this mode
intentionally rejects until the local and hosted commands change to the normal
complete mode.

`generate_selector_closure_source.py --materialize-from-compact PATH` is a
mutating import operation. It decodes `PATH`, writes the allocation inventory
next to `--authoring` first, and then writes `--authoring`. It never writes the
compact input or `--output`. It creates only missing outputs and refuses an
existing output with different bytes. It also rechecks all input schemas, the
compact input, and both installed outputs. A partial process failure can leave an
unreferenced inventory before the authoring file exists; retry only after you
inspect both destinations. Maintained repository paths additionally require the
review-control lease.

The decision-registry generator, ADR-example checker, and selector allocation
oracle limit each ADR Markdown file to 256 KiB. They also limit the complete ADR
Markdown corpus to 2 MiB. These independent limits bound both one review subject
and total validation work. The JSON-example parser limit remains 128 KiB.

For B01, `changed_files` is an evidence declaration, not a reconstruction of the
working tree. The ledger checker requires canonical ordering and a minimum
governed set derived from the decision-source ADR and module paths plus the fixed
registry, ledger, schema-gate, CI, handoff, and readiness paths. It rejects an
omitted governed path. The final task receipt must still declare every additional
source and evidence file that the coherent B01 change contains.

The selector codec limits the compact source to 4 MiB and the decoded source to
16 MiB. The external allocation inventory has a separate 4 MiB pre-read bound.
The expanded authoring-schema input has a distinct 128 KiB bound. Its self-test
admits an exact-bound schema and rejects the same bytes plus one.
The bounds include capacity for the complete EVENT, PROFILE, RESOURCE, SELECTOR,
STATE, and TYPE provenance rows and their typed exclusions.

The bound-probe frame admits one script of at most 4 MiB and at most three
dependencies of 256 KiB each. Module names are at most 128 bytes. Source paths
are at most 512 bytes. The exact maximum complete frame is 4,983,223 bytes.
Each output channel is at most 2 MiB. Lower inherited CPU, file, core, and open
file limits remain lower and become hard child limits. The 512 MiB RSS check is
a polling high-water rejection. It is not prospective memory isolation. The
runner does not block absolute file access, network access, syscalls, or a
reviewed source that creates a new process session. Interpreter, standard
library, dynamic runtime, and kernel bytes are not content-bound. Within one
bound-source execution, class, instance, module, and code stability and the
absence of concurrent mutation are caller obligations. Launch uses POSIX
`preexec_fn` resource limits from a single-threaded parent. A descendant that
creates another process session can escape process-group timeout termination.

The encoder derives subtree identity and byte size without serializing each
occurrence. It limits the total canonical ordering material for selected object
table entries to the decoded-source byte limit.

The selector codec requires supported POSIX dirfd, no-follow, `flock`, hard-link,
rename, regular-file fsync, and directory-fsync behavior. The parent and each file
must have a trusted owner. Their mode bits must grant no group or world write.
Deployment must exclude an ACL or filesystem policy that grants an additional
writer. Each cooperating writer must hold the lock on the same parent inode.

An output that is absent at entry uses link-based no-clobber installation. A
replacement requires the exact unchanged target fingerprint under the parent lock.

The checks detect each exercised leaf, ancestor, permission, temporary-name,
hard-link, and destination mutation. They cannot exclude a root process or an
uncooperative authorized writer after the final path check. Fatal process
termination can prevent an error report. Remote filesystem, mount-namespace,
storage, or hardware behavior can limit the durability that fsync establishes.

If the codec catches an exception after an install attempt, it raises
`AtomicWriteOutcomeUnknownError`. This runtime error is separate from the
deterministic `SelectorClosureCodecError`. The caller must stop automatic retry.
A destination inspection is recovery input, not proof that an operation did not
occur.

The selector-allocation review integration uses one fixed lock and one durable
control file in the current worktree's Git-private directory. The control first
records `PENDING` with the old and new hash and byte length for all four tracked
artifacts. It also records each exact target payload. Recovery accepts only a
monotone prefix of the declared write order. It compares the current bytes before
each replacement and rechecks the exact Git source cut after each durable edge.
It changes the control to `ATTACHED` only after all four exact targets are durable.

Promotion writes the authoring source, compact source, and generation state before
it writes the reviewed inventory. Thus, `REVIEWED` is the last tracked state that
can become visible. Reopen writes the not-reviewed inventory first. Thus,
`NOT_REVIEWED` is the first tracked state that becomes visible. Recovery fails
closed on an illegal prefix. It rolls back an exposed reviewed promotion inventory
or installs the not-reviewed reopen inventory before it reports the poisoned
state.

The attached control is an accidental-rollback and crash-recovery high-water
mark for one surviving Git worktree only. A later transition must bind the full
tracked state, the exact byte commitments for all four tracked artifacts, and a
source commit that descends from the recorded commit and tree. When the
commitments still match, the control rechecks all four files. A missing control
can start only from the exact tracked genesis state.

After reopen, the attached artifact commitments remain historical rollback
evidence. Only the next promotion can re-anchor changed source artifacts. The
promotion requires all of these conditions:

- The tracked review state is the exact inactive post-reopen state.
- The inventory is canonical `NOT_REVIEWED` data with a zero reviewed digest.
- The prior source commit is a strict ancestor of the current source commit.
- Every required index and worktree file exactly matches the clean current
  commit.
- The current source artifacts differ from the prior attached commitments.

The pending control binds the complete prior attached control and its hash. It
also binds both commits, both trees, and both artifact-commitment sets. Active,
dirty, staged, same-commit, non-descendant, rollback, symlink, mode-change, and
non-promotion inputs fail closed.

The allocation and observer-profile bridges form one coupled migration. Either
migration switch without the other fails before the private lock is created.
The coupled migration is not a general compatibility mode. It requires
the exact 16,489-byte v2 schema commitment, the exact v2 model and review profile,
empty allocation and exclusion rows, canonical empty per-document row
commitments, `INCOMPLETE_FAIL_CLOSED`, `NOT_REVIEWED`, a zero reviewed digest, the
tracked genesis review state, and no Git-private review control. It also requires
the exact 48,359-byte v4 target schema with SHA-256
`2f7851cddc366e430c24220a25d3716d0d7d34bc4a80335c7a0b55e2b8fdc802`.
The bridge changes no allocation, exclusion, authority, or review status. It
refreshes the authoring envelope first and the inventory second so an interrupted
first write can recover from the exact target binding. It rejects v3 and all
other intermediate states.

The observer read/capture part accepts one exact predecessor profile and one
exact legacy probe-binding object. It accepts only the complete maintained v1
profile whose canonical JSON is 2,334 bytes with SHA-256
`7628f6e560622cf13f3ba29effa12a234c921a301255ebf4fd9f99f1981de7f8`.
Its target profile and complete probe graph come only from exact `const` values
in the authoring schema. The generator does not copy or independently redefine
the machine-readable bridge suite or the current probe evidence. The migration
also requires `INCOMPLETE_FAIL_CLOSED`, `NOT_REVIEWED`, a zero reviewed digest,
the exact tracked genesis state, and an absent private review control. It installs
the v2 profile and probe graph before it recomputes the semantic subject,
semantic shape, closure commitments, and inventory binding. Both migration flags
require the generated compact source to be absent and keep
it absent across both durable writes. This preserves the two-artifact migration
boundary without leaving an older compact representation beside newer authoring
bytes.
The migration pins the exact authoring schema and both complete artifact pairs.
It accepts only the exact predecessor, the exact authoring-first recovery prefix,
or the exact completed successor. A repeated call accepts the successor as an
idempotent no-op. Every hybrid, changed, unbound, or intermediate pair fails
closed.

Deleting or replacing Git-private state, copying files without it, cloning a new
worktree, an adversarial filesystem, and an uncooperative privileged writer are
outside this local control boundary. The control is not evidence, identity
authentication, tamper resistance, independent review, or protocol or release
authority.

## Security, plant, and packages

| Script | Purpose |
|---|---|
| `validate_security_profile.py` | fail-closed named-profile/authority rules and portable security-state digest implementation |
| `check_acl_template.py` | offline Zenoh ACL structure and negative mutations |
| `verify_acl_deployment.py` | router mTLS/ACL nonce-delivery probe; it cannot prove NCP payload-to-peer identity binding, and `--self-test` is logic only |
| `render_acl_template.py` | atomically render a validated exact realm and concrete action session |
| `check_rust_packages.py --offline` | package/extract/build/test publishable Rust crates without workspace leakage, using canonical local-patch identities across filesystem aliases |
| `build_candidate_dossier.py --source-revision REV --output DIR` | build exact archived source into twice-compared Rust/npm/release-profile Python candidate packages, smoke them, bind hashes/SBOM/toolchains, and emit an unsigned held dossier; never tags or publishes |
| `build_candidate_dossier.py --sdist-preflight REV` | build the exact Python sdist twice with Cargo network access disabled, require a prune-only two-crate lock, compare archive bytes, and revalidate the extracted source under `--locked --offline` |
| `build_candidate_dossier.py --verify-dossier DIR --require-hosted-toolchain --subject-checksums PATH` | independently recompute a held dossier's checksums, identities, comparisons, toolchain policy, package subjects, and exact attestation-subject manifest without authorizing release |
| `prepare_advisory_database.py --source-database DIR --destination DIR` | clone one current, verified RustSec database locally and rewind a disposable copy to the evidence-pinned revision for deterministic replay |
| `prepare_current_advisory_database.py --destination DIR --receipt FILE` | resolve the official RustSec main ref twice, prepare one bounded depth-one current database in a fresh external Cargo home, verify its exact commit/tree/layout, and retain an ephemeral local-gate receipt before cargo-deny runs with fetching disabled |
| `check-version-coherence.sh` | package/wire/compact-hash metadata coherence |
| `../ncp-ts/scripts/build-release.mjs --source-revision REV --output DIR` | archive one exact 40-hex `HEAD`, inject and verify the shared Rust/TypeScript build identity, and emit smoke-tested root+nested npm tarballs plus a hash receipt; never publishes |

The exact-source verifier mode was exercised against held-dossier run
[`29414924349`](https://github.com/sepahead/NCP/actions/runs/29414924349), sourced
from `ef357d20692f707e185495dcfd16b16556fec264`, after exact hosted CI run
[`29414498370`](https://github.com/sepahead/NCP/actions/runs/29414498370) passed.
It independently recomputed the 19-file dossier's 18 checksums, nine package
subjects, and ten attestation subjects. Artifact `8342883563` has SHA-256
`b2228a89232e3751a3fc205dbda1f66cc07eac7c1f7811f5cdea0a44d6277ed5`.
SLSA attestation `35446154` has Rekor index `2172913900` and canonical
bundle-object SHA-256
`eac629acd68a9e2f63097508655fb9ea77ebdeae192c15818c2a0d8df08be9f5`;
the aggregate CycloneDX attestation `35446158` has Rekor index `2172913945` and
canonical bundle-object SHA-256
`fc85bb970b4835128f0b1a71818c38a330bd306528b238058aa4d43b6fdff2c9`.
The verifier constrained signer/source/ref/hosted-runner/predicate identities and
matched the canonical embedded SBOM to the retained file. Direct wheels were
byte-compared only with each other; the sdist-rebuilt wheel passed separate
install/identity/behavior smoke.

That receipt is held candidate-only evidence with `release_authorized=false`. It
does not provide a tag, registry publication, DOI/archive deposit, final publisher
signatures, independent clean-room reproduction, multi-platform release artifacts,
or external certification. `RUSTSEC-2026-0041` and the unavailable
`production-secure` transport-principal binding remain holds; external gates remain
**NOT RUN** and the candidate remains `NO_GO`.

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

Required tools are Cargo/Rust 1.88+, Python 3, Node.js, a C++17 compiler, Bun,
npm, Buf, and `cargo-deny`. Hosted CI pins Node.js 24.18.0 and Bun 1.3.14. Any
missing required tool is a failed local gate. External security,
independent-peer, fault/soak, fuzz/sanitizer, signature/SBOM, clean-room, publication,
and consumer gates remain **NOT RUN** until separately evidenced.

The released-baseline check requires the complete local objects and annotated refs
for `v0.5.0` through `v0.8.0`. It is read-only in normal mode. Its registry binds
Git identities; it neither verifies tag signatures nor makes a new release claim.
The Buf gate consumes only those verified rows. The initial `ncp.v1` candidate has
no released v1 row and is intentionally not compared with `ncp.v0`; after a v1
release is registered, later v1 work compares with the greatest registered v1 tag's
peeled commit.
