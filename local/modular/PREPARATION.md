# NCP v1 preparation and the local SDK release

This page collects candidate notes, tested boundaries, and the remaining preparation checklist.
It does not declare complete product qualification.
The standalone `ncp-local` packages are released separately as SDK 1.0.0 under the tag `sdk-v1.0.0`.
The [SDK release record](SDK_RELEASE.md) states that scope, its council decision, and its verification.
The other scopes below have no release tag.

Author and maintainer: **[Sepehr Mahmoudian](https://github.com/sepahead)**.

## Three different scopes

| Scope | Current identity | Meaning |
| --- | --- | --- |
| Modular local applications | [Modular SDK contract](owner.md) and each selected application contract | Independently selected local owners, bounded buffers, original observations, and retained outcomes. The SDK packages are released as `sdk-v1.0.0`; application qualification remains open. |
| Earlier fixed-role reference | [Local release registry](../release.v1.json) | Separate descriptor, four-owner reference, and open bootstrap and operational receipts. Its intended tag does not authorize publication. |
| Broader protocol candidate | [`1.0.0-rc.1`, wire `1.0`](../../docs/1.0-scope.md) | Unreleased and release-blocked. Its independent review, security, distribution, and role gates remain required. |

The standalone Rust and Python packages are released as version `1.0.0` under the tag `sdk-v1.0.0`.
That release is neither a registry publication nor product acceptance.
This preparation changes no descriptor, wire value, release flag, or canonical task state.

NCP owns the local message and buffer contract.
CREBAIN owns simulated bodies and sensors. Engram owns its selected NEST application.
Prisoma owns capture and canonical experiment records when selected.
Applications remain usable without a mandatory ecosystem bundle.

The public [Engram repository](https://github.com/sepahead/engram) is a placeholder.
The implemented neural application lives in private `sepahead/Paper2Brain`.
Its source requires authorized repository access.
Public placeholder files cannot reproduce that private installation.
The intended paper-driven workflow remains distinct from arbitrary-paper reproduction.

## Candidate notes and retained evidence

The following records describe separate source and installation cohorts.
Their publication commits identify document snapshots, not a single shared execution source.
Each owning receipt retains its actual package, runtime, configuration, command, and outcome identities.

| Completed scoped work | Evidence and boundary |
| --- | --- |
| Independent local SDK and lifecycle controls | Rust and pure Python implement the selected local contracts. [SDK verification](../../README.md#implementations-and-verification) includes installed-wheel and cross-language controls. Application and resource qualification remain separate. |
| M1 sensor transfer | [Published M1 evidence](https://github.com/sepahead/prisoma/blob/2c229fc7eda40f85f24b68097a5de40b8db5e328/integrations/agent-bridge/evidence/M1_NATIVE_2026-09-23.md) retains 44 matching payloads and 4,326,400 bytes. Fault outcomes and incomplete captures remain visible. |
| Actual Engram body/neural host | The [current evidence index](STATUS.md#implemented-and-observed) links the private host record. Two arms completed 24 body ticks and eight NEST steps. Fresh direct NEST matched 64 count/rate values. The reference shares NEST's engine. |
| Canonical forecast and restored labels | [Published E1 evidence](https://github.com/sepahead/prisoma/blob/2c229fc7eda40f85f24b68097a5de40b8db5e328/integrations/agent-bridge/evidence/E1_NATIVE_2026-09-23.md) retains eight qualification cases and 112 study episodes. The frozen result is null or inconclusive. No useful forecast or policy benefit is claimed. |
| City source delivery and maximum batch | [Published city evidence](https://github.com/sepahead/crebain/tree/542898a9003e5dcb3ca4269576fc4ac0aad3db4f/integrations/ncp-force-city-sources/evidence) includes selected delivery faults and the three-tick maximum batch. The contract admits 1–256 entities under complete-plan limits. Admission is not universal operating qualification. |
| Source-bound interval separation | The [integrator-hull certificate](https://github.com/sepahead/crebain/blob/542898a9003e5dcb3ca4269576fc4ac0aad3db4f/integrations/ncp-force-city-sources/evidence/integrator-hull-2026-09-26.json) rejoins 88 retained trajectory pairs. It establishes separation under the declared integration law, not physical-flight safety. Original tracking fields remain unchanged. |
| Logical resources and observed containment | The same published city evidence includes twelve resource sessions and four separately selected stall cases. These retain actual cleanup facts and the earlier failed campaign. Logical allowances and sampled retirement do not establish complete memory or descendant bounds. |
| City horizon and CPU characterization | [Published horizon evidence](https://github.com/sepahead/crebain/blob/b9ad9edd1c7981fcf9ef18b4a09d3c581c60f0d6/integrations/ncp-force-city-sources/evidence/native-city-horizon-2026-09-27.md) retains a second maximum batch and a failed 7,200-tick CPU horizon. That case stopped at its 600-second deadline after 4,070 acknowledged ticks. [Published CPU and storage evidence](https://github.com/sepahead/crebain/blob/c892d206b3955d44c16d734af3c9bdaec163f5f2/integrations/ncp-force-city-sources/evidence/native-city-cpu-storage-2026-09-27.md) retains six short cases. All 144 route deadlines and 144 export deadlines were missed. |
| Performance characterization | [Published M1 timing](https://github.com/sepahead/prisoma/blob/2c229fc7eda40f85f24b68097a5de40b8db5e328/integrations/agent-bridge/evidence/M1_PERFORMANCE_2026-09-23.md) retains 192 executions. All 4,608 route deadlines and all 4,608 export deadlines were missed. No real-time qualification follows. |

The complete local NCP gate passed on source `9860e44817eab2b13fb9c64e4317738eb36cd592` on September 26, 2026.
Its private terminal log has SHA-256 `66a796fb01ee1fd4029258b5e916499981b45f947e372b102bd480dcb3c40dfa`.
This is local preflight evidence for that exact source, not the final handoff's gate or an external release receipt.
The later authorship milestone changed README attribution and its generated audit identities only.

Public summaries identify retained private artifacts. They do not replace original captures for independent replay.
File and package identities do not attest loaded interpreter, model, browser, or native-library bytes.

## Preparation checklist

| Required preparation | Acceptance boundary |
| --- | --- |
| Freeze exact sources and supported selections | Record each repository commit, source tree, package, runtime, descriptor, host, workload, and optional dependency. Preserve unrelated work. |
| Complete source gates | Run each owner's applicable gate. Before a new NCP candidate handoff, run the complete `scripts/check.sh` on its final fixed cut. |
| Rejoin installed observations | Use the owning dated terminal receipts. Preserve failed cases, uncertain effects, actual command exits, and unavailable cleanup facts. |
| State the measured operating envelope | Distinguish logical admission, sampled measurements, physical reservations, and unavailable metrics. Unrun horizons and configurations stay unqualified. |
| Prepare readable documentation | Keep notes, setup, descriptions, authorship, evidence links, mathematical meaning, and rendered Markdown consistent. Generate audit projections through their owner. |
| Retain unresolved prerequisites | Keep canonical release gates and independent floors unchanged. Name the actual missing input and the prepared subject. |
| Publish the prepared source | Push only the reviewed, gated commits to `main`. Verify remote objects and preserve the exact gate receipts. Only the SDK packages carry a release tag, `sdk-v1.0.0`; the other scopes create none. |

The [CREBAIN city guide](https://github.com/sepahead/crebain/tree/main/integrations/ncp-force-city-sources) indexes its maintained resource, lifecycle, and operating evidence.
The [CREBAIN sensor guide](https://github.com/sepahead/crebain/tree/main/integrations/ncp-force-ground-sensors) owns scalar and checkpoint-family selections.
The [Prisoma bridge](https://github.com/sepahead/prisoma/tree/main/integrations/agent-bridge) owns canonical execution and experiment evidence.
These maintained indexes may add separately dated receipts. New receipts do not change an earlier campaign's source, verdict, or qualification scope.

Complete allocation, copy, native CPU, graphics-memory, long-horizon, and successful latency qualification cannot be inferred from coarse spans or logical byte allowances.
Any additional scoped measurement must identify its instrument and retained limitations.
Haldir's velocity contract and Galadriel's scalar statistical input remain separate from the current city action and raw sensor contracts.
Their unsupported compositions cannot acquire authority through documentation or transport wrapping.

## Broader implementation remains open

The broader `1.0.0-rc.1` candidate needs implementation changes as well as external evidence.
Its [resumption brief](../../docs/implementation/NCP_1_0_RESUMPTION.md) records the remaining source conflicts and dependency order.
Proposed ADRs do not implement those changes or authorize blocked descendants.

| Implementation prerequisite | Current boundary |
| --- | --- |
| Receiver-owned transport provenance | The current Zenoh callback API does not supply authenticated peer identity. `production-secure` fails closed before opening a session. |
| Complete admission parity | Metadata-entry allocation and generic horizon validation retain unresolved cross-language differences. The accepted registry and coherent rebaseline are still required. |
| Body authority and lifecycle | Proposed session, lease, retained-outcome, plant-unit, and final-application rules need their dependency-gated implementation and controls. Local modular outcomes do not repair the broader runtime. |
| Self-contained dependency distribution | Conditioned archive checks use an exact consuming-root patch. They do not establish safe standalone resolution from published dependencies. |

These are source and design obligations. Additional external tests alone cannot complete them.

## External prerequisites remain explicit

The [canonical readiness ledger](../../RELEASE_READINESS.md) and [task ledger](../../docs/implementation/NCP_1_0_TASK_LEDGER.md) retain broader candidate authority.
Local application evidence cannot satisfy their independent or external floors.

The current [B01 review request](../../evidence/implementation/requests/B01/review-request.v1.json) is already prepared and non-authorizing.
Its SHA-256 is `af8daf9ff4ab42969b729ddc20eeb7ba45bfd11648d748605a6422b804663829`.
The [Version 2 reviewer kit](../../evidence/implementation/requests/B01/reviewer-kit.v2.json) has SHA-256 `62a265bfdca7951533d52015cf7e70fe3536c2a1953a799cf2e8d553868cbad0`.
The decision set is `1113dd7ca5a333a3f0a91632b8d8c52f8ac576045f959830434ba74067953bc4`.
Unrelated descendant commits do not require reissuing an unchanged review subject.

| Missing prerequisite | Required input |
| --- | --- |
| Qualified approval admission | Repository-policy authorization and a separately authenticated, independently qualified verifier, with reviewed subject, currentness, replay, and revocation controls. |
| B01 decisions | Genuine exact-subject reviews and adjudication for eleven proposed ADRs, 52 role obligations, 53 identity slots, and 112 evidence requirements. Six slots require independence. |
| B02 rebaseline | Accepted B01 decisions and authenticated owner authorization for the exact normative, source, migration, generator, corpus, and consumer effects. |
| Broad installed and secure qualification | Required independent live peers, eleven exact roles, supported platforms, security, duration, performance, and installed-artifact evidence. |
| Distribution and release authority | Verified registry rights, self-contained dependency resolution, independent reproduction, release-bound provenance and signatures, stewardship, and exact release authorization. |

Identity slots do not imply the same number of distinct people. The owner policy defines permitted reuse and disjointness.
No qualifying B01 reviews or accepted B02 authorization are supplied by this preparation page.
Local councils, hosted CI, hashes, and source archives do not replace those inputs.

The modular local SDK does not silently supply those missing remote capabilities.

Apart from the separately recorded SDK release, no tag, registry upload, stable artifact, or post-publication validation is part of this handoff.
Future publication requires its own exact authorization and gates.
Historical releases, frozen evidence, private-source access boundaries, and original failure records remain unchanged.
