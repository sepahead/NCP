# NCP 1.0 implementation task ledger

> **Generated file — do not edit.** Edit
> [`task-ledger.v1.json`](../../evidence/implementation/task-ledger.v1.json), run
> `python3 scripts/generate_implementation_ledger.py --write`, then run the checker.
> This is evidence bookkeeping, not release authorization or certification.

Blueprint SHA-256: `34cef2a6d8ca6fd514d412ce3ca69162d7ce8a5a7e3a1ca7601c79ee27705122`.

Can this ledger grant release authorization? **false**.

## Current decision

The candidate remains **NO_GO**. A local pass means only that a bounded
repository-local acceptance slice passed. External and independent obligations remain
separate, and publication tasks cannot start through a status edit.

| Status | Count |
|---|---:|
| `OPEN` | 53 |
| `IN_PROGRESS` | 1 |
| `BLOCKED` | 0 |
| `LOCAL_PASS` | 2 |
| `EXTERNAL_PASS` | 0 |
| `INDEPENDENT_PASS` | 0 |
| `COMPLETE` | 0 |

Active tasks: `B01`.

Dependency-ready open tasks: none.

## Active task recovery checkpoints

### `B01` — Decide and ratify ADR-001 through ADR-011

Strengthened B01 source is pushed and remote-verified at `81941954f33078aa6a8dd85d70e392aae5469246` (tree `dc2c433e5e09cce9f03e981d9cbed44f84e72d00`). Its exact clean result binds the unchanged normative digest, contract-manifest bytes, Z3 binary, 13 sources, Git cleanliness, and Fable E response `080ad93775d6dec018a08efeadd49b0d57e6162a90f4bc7cf9a8b43199246d32`. It explored 11,444 composition, 35 deny, and 1,415 wire-cutover states; killed 23 model and four SMT mutations; passed eleven SMT checks; and detected every resource-probe fault. ADR-008 is proposed at `1379477feebd886823d1511af5df0b7a7019795aef9ee8023147a4ef0a5f56b6` and ADR-011 at `96d243fd41868a70fc00c0f309a5f87e0058f6fce5308e2c98d147e18f76421f`. Canonical result SHA-256 is `3f140dad12147500048644899f69893c1dd985d0001c900ec66b18143be51fe7`; raw/deterministic-gzip log SHA-256 values are `08ba5c52a42b505eb409734b218cf793380778c2f44cc9d151589e2364222c94`/`eb885f3c430e41f3386a860fc9cd74e23b4a1244ed94d03db281d7565d371603`. The earlier `541e1e7` result is superseded. The complete clean local gate passed at remote-verified `a9e0f48520649becc5507fc7d0ba069e4e20af92`; raw/gzip log SHA-256 values are `8dcba99800e4af9ea7f672a51cadc8e91edbee1d5b9ff94cb5a2b18f38620daf`/`11042f9980566d0dbc5687957c2045f6dc902e7a2d212d9769dbc9d834e4b67a`. The exact packet requests human same-digest review at `https://github.com/sepahead/NCP/issues/21`; responses count only with the required role, digest, independence, and disposition fields. These remain non-passing working files: commands, artifacts, and reviewers are empty; all ADRs are PROPOSED; B01 is IN_PROGRESS. Next obtain qualifying reviews. Do not create the normative registry, alter ADR/wire bytes, start dependent tasks, or infer release readiness.

Current residual risks:

- All eleven ADRs remain PROPOSED and have no qualifying owner or independent same-digest review; B01 has not reached any passing evidence class.
- The generated registry is intentionally non-normative and outside contract/; promotion and the deliberate candidate rebaseline remain blocked.
- Wire examples remain draft JSON only. Independent Python/Node syntax replay and the exact clean-source preliminary model/resource run pass, but the retained result is bounded non-passing working evidence; canonical formal work, refinement, and every downstream implementation remain open.
- Five usable exact Fable 5 consultations are non-normative challenge input only. Five failed or incomplete attempts returned no complete usable answer, and no model response counts as review, proof, interoperability, or evidence.
- The current 1.0.0-rc.1 normative digest and compact hash are unchanged; external security, plant, consumer, performance, supply-chain, and release gates remain NOT RUN or blocked.

## Three required review perspectives

| ID | Perspective | Blueprint lenses | Required question |
|---|---|---|---|
| `P1` | Protocol and security correctness | `L1`, `L2`, `L3` | Does the change preserve exact semantics, verified identity and authority, fail-closed behavior, and the plant safety boundary under hostile or ambiguous input? |
| `P2` | Consumer and runtime usability | `L4`, `L5`, `L6`, `L8` | Can independent consumers implement, operate, observe, recover, migrate, and bound the behavior without private forks or unsafe defaults? |
| `P3` | Operational and scientific evidence | `L5`, `L7`, `L9`, `L10` | Do retained evidence, statistics, non-claims, independent review, release governance, and lifecycle ownership justify exactly the stated status? |

Every task must also pass all ten blueprint lenses. `NOT_APPLICABLE` requires a
specific rationale and reviewer; it is not an omitted review.

## Evidence floors and checked gate names

`LOCAL` is bounded repository evidence only. `EXTERNAL` additionally requires the
checked live/owner/platform gate names below. `INDEPENDENT` additionally requires
the checked number of distinct non-owner reviewer identities. Reopening a passing
task starts a new evidence generation; evidence from an older generation does not
satisfy the floor.

| External-floor task | Required checked gate ID |
|---|---|
| `B02` | `owner-rebaseline-authorization` |
| `N09` | `current-advisory-and-registry-identity` |
| `R11` | `owner-approved-stewardship-policy` |
| `X02` | `composed-ecosystem-multi-writer` |
| `F04` | `live-security-fault-soak-rotation-revocation` |
| `F05` | `release-performance-resource-visual` |
| `R10` | `incident-response-exercise` |
| `R03` | `signed-tag-remote-draft-release` |
| `R04` | `protected-build-sign-attest-stage` |
| `R05` | `registry-and-github-publication` |
| `R06` | `github-metadata-controls-and-clean-install-docs` |
| `R07` | `consumer-tag-repin-and-revalidation` |
| `R08` | `ecosystem-metadata-and-profile` |
| `R09` | `public-install-and-emergency-revocation` |

| Independent-floor task | Minimum distinct independent identities |
|---|---:|
| `B01` | 2 |
| `F01` | 2 |
| `E05` | 1 |
| `H03` | 1 |
| `G03` | 1 |
| `P03` | 1 |
| `C05` | 1 |
| `X00` | 1 |
| `X01` | 2 |
| `X03` | 2 |
| `X04` | 2 |
| `R00` | 2 |
| `R02` | 2 |

## Intake repository snapshot

| Repository | Branch | HEAD | Tree | Dirty paths | Intake disposition |
|---|---|---|---|---:|---|
| NCP | `main` | `6e8278366755` | `cbb9153e5499` | 0 | Clean provider intake at 6e82783667554b8d8b433261e6b8ae588e94d89f; B00 owns only the listed ledger, generated-view, instruction, and gate-wiring paths. |
| Engram / Paper2Brain | `main` | `92853d2fe6e8` | `1625378dcd22` | 168 | Preserve all 168 stopped-agent paths; do not stage, reset, clean, or bulk-format them during provider work. |
| Haldir | `wip/current-file-review-ledger` | `bb6c0a7b27bb` | `2b472937b393` | 0 | Clean stopped-agent branch; do not change it before its dependency-ready H01 intake. |
| Galadriel | `main` | `f541f3eda7cf` | `47aa9b75e988` | 0 | Clean main baseline; do not change it before dependency-ready G01. |
| Crebain | `main` | `3e3ee5d0b752` | `4be236496ef5` | 0 | Clean canonical body baseline; keep separate from the producer worktree. |
| Crebain Galadriel producer | `feat/galadriel-integration-refresh` | `113ee70d5660` | `55eb96da6d98` | 0 | Clean feature worktree; reconcile only in C04 after canonical C01-C03. |
| Prisoma | `main` | `b0185d98aea8` | `0d7287deb631` | 0 | Clean main baseline; preserve v0.8 history while adding a parallel 1.0 observer. |
| pid-rs | `main` | `1410c8808f1b` | `516a2c956494` | 0 | Clean standalone estimator/run-log baseline; preserve its protocol-neutral dependency direction and refresh consumer pins only in dependency-ready Galadriel/Prisoma tasks. |
| sepahead profile | `main` | `80a5c1d5af3a` | `ed84f1da473e` | 2 | Preserve the two unrelated untracked tool directories; edit only canonical sources when R08 is evidence-ready. |

## Ten-lens mapping to the prior twenty-lens review

| Lens | Name | Prior lenses | Stricter rule |
|---|---|---|---|
| `L1` | Contract and semantics | `L02`, `L04`, `L13`, `L14` | Both taxonomies must pass; disagreement across prose, types, schemas, wire, generated packages, or SemVer remains a failure. |
| `L2` | Security and authority | `L06`, `L07`, `L08`, `L09` | Identity, provenance, cryptography, authority, safety, and hostile-parser obligations all apply; an unknown or missing value grants nothing. |
| `L3` | Safety and plant boundary | `L08`, `L11`, `L19`, `L20` | Authority, lifecycle, human recovery, and counterfactual hazard review all pass; protocol ESTOP never becomes physical certification. |
| `L4` | Distributed systems | `L05`, `L11`, `L12`, `L18` | Ordering, replay, lifecycle, determinism, and ecosystem composition all pass across loss, partition, restart, concurrency, and partial commit. |
| `L5` | Resource and real-time bounds | `L09`, `L10`, `L15` | Parser, resource, deployment, queue, deadline, storage, and overload bounds are explicit before allocation and fail closed. |
| `L6` | Interoperability and migration | `L12`, `L13`, `L14`, `L18` | Reproducibility, API/FFI/SemVer, wire parity, and composition all pass in independent installed implementations without silent translation. |
| `L7` | Science and statistics | `L01`, `L03`, `L06`, `L17` | Claim scope, estimand/statistics, provenance, and evidence quality all pass; missing variables and simulations cannot be promoted. |
| `L8` | Implementation and operations | `L13`, `L15`, `L16`, `L19` | APIs, deployment, observability, recovery, accessibility, and human governance are executable and hard to misuse. |
| `L9` | Verification and evidence | `L03`, `L12`, `L17`, `L20` | Mathematical, reproducibility, evidence-quality, negative, and counterfactual obligations all pass at their stated abstraction only. |
| `L10` | Lifecycle and governance | `L01`, `L06`, `L16`, `L18`, `L19` | Claims, provenance, forensics, ecosystem ownership, human governance, revocation, support, and succession are explicit and current. |

## Dependency-ordered tasks

| Task | Status | Claim tier | Required evidence class | Scope | Dependencies | Repository | Source commit | Residual risks |
|---|---|---|---|---|---|---|---|---:|
| `B00` | `LOCAL_PASS` | `COORDINATION_ONLY` | `LOCAL` | Create the live implementation and evidence ledger | — | NCP | `6381d2a7cc82` | 4 |
| `B04` | `LOCAL_PASS` | `COORDINATION_ONLY` | `LOCAL` | Prove authenticated-ingress and independent-parser feasibility | `B00` | NCP prototypes | `3754635404f3` | 6 |
| `B01` | `IN_PROGRESS` | `COORDINATION_ONLY` | `INDEPENDENT` | Decide and ratify ADR-001 through ADR-011 | `B00`, `B04` | NCP | `81941954f330` | 5 |
| `B02` | `OPEN` | `COORDINATION_ONLY` | `EXTERNAL` | Authorize and identify the deliberate pre-release rebaseline | `B01` | NCP | `—` | 0 |
| `B03` | `OPEN` | `COORDINATION_ONLY` | `LOCAL` | Reserve registries, namespaces, error codes, and owners | `B01` | NCP | `—` | 0 |
| `N01` | `OPEN` | `IMPLEMENTATION_ONLY` | `LOCAL` | Establish the single normative source graph and identity projections | `B02`, `B03` | NCP | `—` | 0 |
| `N02` | `OPEN` | `IMPLEMENTATION_ONLY` | `LOCAL` | Implement typed simulation, plant, and observer session lifecycles | `N01` | NCP | `—` | 0 |
| `N03` | `OPEN` | `IMPLEMENTATION_ONLY` | `LOCAL` | Implement declared streams, domain-separated authority, and command disposition | `N01`, `N02` | NCP | `—` | 0 |
| `N04` | `OPEN` | `IMPLEMENTATION_ONLY` | `LOCAL` | Implement the production authenticated envelope and semantic security state | `B01`, `N01`, `N02` | NCP | `—` | 0 |
| `X00` | `OPEN` | `QUALIFICATION_REQUIRED` | `INDEPENDENT` | Prototype an early independent non-Rust draft peer | `N02`, `N03`, `N04` | independent draft-peer environment | `—` | 0 |
| `N05` | `OPEN` | `IMPLEMENTATION_ONLY` | `LOCAL` | Refactor critical Rust behavior into pure checked transition cores | `N02`, `N03`, `N04` | NCP | `—` | 0 |
| `N06` | `OPEN` | `IMPLEMENTATION_ONLY` | `LOCAL` | Integrate security and state machines into Zenoh without trusting callbacks | `N04`, `N05` | NCP | `—` | 0 |
| `N07` | `OPEN` | `IMPLEMENTATION_ONLY` | `LOCAL` | Regenerate and harden all supported language and package surfaces | `N05`, `N06`, `X00` | NCP | `—` | 0 |
| `N08` | `OPEN` | `IMPLEMENTATION_ONLY` | `LOCAL` | Rebuild conformance, behavior, migration, and fixture coverage | `N02`, `N03`, `N04`, `N07` | NCP | `—` | 0 |
| `N09` | `OPEN` | `IMPLEMENTATION_ONLY` | `EXTERNAL` | Remove supply-chain and package-identity release blockers | `N06`, `N07` | NCP | `—` | 0 |
| `N10` | `OPEN` | `IMPLEMENTATION_ONLY` | `LOCAL` | Rewrite normative and user documentation and regenerate visuals | `N01`, `N02`, `N03`, `N04`, `N05`, `N06`, `N07`, `N08`, `N09` | NCP | `—` | 0 |
| `F01` | `OPEN` | `IMPLEMENTATION_ONLY` | `INDEPENDENT` | Implement and independently review the TLA+ model suite | `N02`, `N03`, `N04` | NCP | `—` | 0 |
| `F02` | `OPEN` | `IMPLEMENTATION_ONLY` | `LOCAL` | Implement SMT, Kani, and model-to-Rust refinement checks | `N01`, `N05`, `F01` | NCP | `—` | 0 |
| `F03` | `OPEN` | `IMPLEMENTATION_ONLY` | `LOCAL` | Implement differential, property, fuzz, sanitizer, and mutation campaigns | `N07`, `N08`, `F02` | NCP | `—` | 0 |
| `R01` | `OPEN` | `IMPLEMENTATION_ONLY` | `LOCAL` | Create the final untagged 1.0.0 source cut and publication machinery | `N10`, `F03` | NCP | `—` | 0 |
| `R11` | `OPEN` | `GOVERNANCE_OPERATION` | `EXTERNAL` | Establish durable 1.0 stewardship without pretending software is eternal | `N10` | NCP and ecosystem governance | `—` | 0 |
| `E01` | `OPEN` | `IMPLEMENTATION_ONLY` | `LOCAL` | Establish Engram's clean native-1.0 integration baseline | `N07`, `N08`, `N09`, `R01` | Engram | `—` | 0 |
| `H01` | `OPEN` | `IMPLEMENTATION_ONLY` | `LOCAL` | Add a parallel haldir-ncp10 adapter without mutating v0.8 history | `N07`, `N08`, `N09`, `R01` | Haldir | `—` | 0 |
| `G01` | `OPEN` | `IMPLEMENTATION_ONLY` | `LOCAL` | Create Galadriel's native-1.0 observer and extension adapter | `B03`, `N07`, `N08`, `N09`, `R01` | Galadriel | `—` | 0 |
| `C01` | `OPEN` | `IMPLEMENTATION_ONLY` | `LOCAL` | Create Crebain's separate native-1.0 plant adapter and exact pins | `N07`, `N08`, `N09`, `R01` | Crebain | `—` | 0 |
| `P01` | `OPEN` | `IMPLEMENTATION_ONLY` | `LOCAL` | Add a parallel native-1.0 Prisoma observer | `N07`, `N08`, `N09`, `R01` | Prisoma | `—` | 0 |
| `E02` | `OPEN` | `IMPLEMENTATION_ONLY` | `LOCAL` | Split Engram's simulation responder from plant commander types | `E01`, `N02`, `N07` | Engram | `—` | 0 |
| `H02` | `OPEN` | `IMPLEMENTATION_ONLY` | `LOCAL` | Integrate body-issued authority and dispositions into Haldir Gate | `H01`, `N03`, `G01` | Haldir | `—` | 0 |
| `G02` | `OPEN` | `IMPLEMENTATION_ONLY` | `LOCAL` | Bind Galadriel lifecycle and monitoring to authenticated observer state | `G01`, `N04`, `N06` | Galadriel | `—` | 0 |
| `C02` | `OPEN` | `IMPLEMENTATION_ONLY` | `LOCAL` | Implement Crebain as body-issued authority and disposition source | `C01`, `N03`, `N04`, `N05`, `N06` | Crebain | `—` | 0 |
| `P02` | `OPEN` | `IMPLEMENTATION_ONLY` | `LOCAL` | Preserve missing-variable and research-claim semantics in native capture | `P01` | Prisoma | `—` | 0 |
| `E03` | `OPEN` | `IMPLEMENTATION_ONLY` | `LOCAL` | Implement Engram's authenticated transport and declared streams | `E02`, `N04`, `N06` | Engram | `—` | 0 |
| `C03` | `OPEN` | `IMPLEMENTATION_ONLY` | `LOCAL` | Migrate Crebain sensor and Galadriel-extension publication | `C02`, `G01` | Crebain | `—` | 0 |
| `E04` | `OPEN` | `IMPLEMENTATION_ONLY` | `LOCAL` | Implement Engram direct and Haldir-gated plant integration | `E02`, `E03`, `N03`, `C02`, `H01` | Engram | `—` | 0 |
| `C04` | `OPEN` | `IMPLEMENTATION_ONLY` | `LOCAL` | Reconcile and retire the separate Galadriel-producer work branch | `C01`, `C02`, `C03` | Crebain and producer worktree | `—` | 0 |
| `X01` | `OPEN` | `QUALIFICATION_REQUIRED` | `INDEPENDENT` | Qualify two genuinely independent installed non-Rust peers | `N07`, `N08`, `E03`, `X00` | independent peer lab | `—` | 0 |
| `X02` | `OPEN` | `QUALIFICATION_REQUIRED` | `EXTERNAL` | Run the composed ecosystem and multi-writer campaign | `E04`, `H02`, `G02`, `C03`, `C04`, `P02`, `X01` | isolated ecosystem lab | `—` | 0 |
| `E05` | `OPEN` | `QUALIFICATION_REQUIRED` | `INDEPENDENT` | Certify Engram's exact installed native-1.0 artifact | `E01`, `E02`, `E03`, `E04`, `X01`, `X02` | Engram certification environment | `—` | 0 |
| `H03` | `OPEN` | `QUALIFICATION_REQUIRED` | `INDEPENDENT` | Qualify Haldir's secure commander and deny-only receiver roles | `H02`, `C02`, `X01`, `X02` | Haldir certification environment | `—` | 0 |
| `G03` | `OPEN` | `QUALIFICATION_REQUIRED` | `INDEPENDENT` | Qualify Galadriel's installed observer and deny-only assessor roles | `G01`, `G02`, `C03`, `X01`, `X02` | Galadriel certification environment | `—` | 0 |
| `P03` | `OPEN` | `QUALIFICATION_REQUIRED` | `INDEPENDENT` | Migrate the fault observatory and certify Prisoma's observer role | `P01`, `P02`, `X01`, `X02` | Prisoma certification environment | `—` | 0 |
| `F04` | `OPEN` | `QUALIFICATION_REQUIRED` | `EXTERNAL` | Execute the live security, fault, soak, rotation, and revocation campaign | `F03`, `X01`, `X02` | cross-ecosystem lab | `—` | 0 |
| `C05` | `OPEN` | `QUALIFICATION_REQUIRED` | `INDEPENDENT` | Certify Crebain body and producer integration separately | `C02`, `C03`, `C04`, `E05`, `H03`, `G03`, `X01`, `X02` | Crebain certification environment | `—` | 0 |
| `X03` | `OPEN` | `QUALIFICATION_REQUIRED` | `INDEPENDENT` | Issue nine exact consumer and extension role qualification receipts | `E05`, `H03`, `G03`, `C05`, `P03`, `X02`, `F04` | cross-ecosystem adjudication | `—` | 0 |
| `X04` | `OPEN` | `QUALIFICATION_REQUIRED` | `INDEPENDENT` | Reproduce the provider and ecosystem from clean rooms | `X03`, `N09` | independent clean builders | `—` | 0 |
| `F05` | `OPEN` | `QUALIFICATION_REQUIRED` | `EXTERNAL` | Execute release-bound performance, resource, and final visual campaigns | `N10`, `F04`, `X03`, `X04` | cross-ecosystem lab | `—` | 0 |
| `R00` | `OPEN` | `QUALIFICATION_REQUIRED` | `INDEPENDENT` | Hand the qualified candidate to the release runbook | `F01`, `F02`, `F03`, `F04`, `F05`, `N10`, `R01`, `X03`, `X04` | NCP | `—` | 0 |
| `R10` | `OPEN` | `GOVERNANCE_OPERATION` | `EXTERNAL` | Execute rollback, withdrawal, revocation, and incident response | `N10`, `F04` | incident-response exercise | `—` | 0 |
| `R02` | `OPEN` | `RELEASE_OPERATION` | `INDEPENDENT` | Issue the signed release-authorization bundle | `R00`, `R10`, `R11` | independent release adjudication | `—` | 0 |
| `R03` | `OPEN` | `RELEASE_OPERATION` | `EXTERNAL` | Create and verify the immutable signed tag and draft GitHub Release | `R02` | NCP release environment | `—` | 0 |
| `R04` | `OPEN` | `RELEASE_OPERATION` | `EXTERNAL` | Build, compare, sign, attest, and stage final artifacts | `R03` | protected release builders | `—` | 0 |
| `R05` | `OPEN` | `RELEASE_OPERATION` | `EXTERNAL` | Publish exact registry artifacts and the GitHub Release | `R04` | protected publication environment | `—` | 0 |
| `R06` | `OPEN` | `RELEASE_OPERATION` | `EXTERNAL` | Update NCP README, GitHub description, topics, and repository controls | `R05` | NCP and GitHub | `—` | 0 |
| `R07` | `OPEN` | `RELEASE_OPERATION` | `EXTERNAL` | Repin and revalidate every consumer against the immutable tag | `R05` | all consumer repositories | `—` | 0 |
| `R08` | `OPEN` | `RELEASE_OPERATION` | `EXTERNAL` | Update ecosystem repository metadata and the public selected-work profile | `R06`, `R07` | ecosystem GitHub and profile | `—` | 0 |
| `R09` | `OPEN` | `RELEASE_OPERATION` | `EXTERNAL` | Run post-publication installs and emergency-revocation exercise | `R05` | public install hosts and revocation lab | `—` | 0 |

## Status-change receipts

| Task | From | To | Timestamp (UTC) | Correlation ID | Receipt |
|---|---|---|---|---|---|
| `B00` | `OPEN` | `IN_PROGRESS` | `2026-07-16T05:56:27Z` | `ncp-v1-finalization-20260716-b00` | initial start; receipt not required |
| `B00` | `IN_PROGRESS` | `LOCAL_PASS` | `2026-07-16T08:59:26Z` | `ncp-v1-finalization-20260716-b00-local-pass` | passing receipt for commit `6381d2a7cc82` |
| `B04` | `OPEN` | `IN_PROGRESS` | `2026-07-16T09:18:11Z` | `ncp-v1-finalization-20260716-b04` | initial start; receipt not required |
| `B04` | `IN_PROGRESS` | `LOCAL_PASS` | `2026-07-16T17:12:35Z` | `ncp-v1-finalization-20260716-b04-local-pass` | passing receipt for commit `3754635404f3` |
| `B01` | `OPEN` | `IN_PROGRESS` | `2026-07-16T17:53:20Z` | `ncp-v1-finalization-20260716-b01` | initial start; receipt not required |

## Update and verification

```bash
python3 scripts/check_implementation_ledger.py --self-test
python3 scripts/generate_implementation_ledger.py --check
scripts/check.sh
```

Raw logs referenced by future receipts must be bounded, repository-relative, and
content-addressed. Credentials, private keys, absolute workstation paths, mutable
source refs, missing outputs, unexplained skips, and self-review cannot be evidence.
