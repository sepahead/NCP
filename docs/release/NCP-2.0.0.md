# NCP 2.0.0 release record

Status: prepared on 11 November 2026, and rebuilt on 17 November 2026 for revision 7 of the specification, as the release candidate `2.0.0rc7` (Python) and `2.0.0-rc.7` (Rust). The tag and the publication of the packages are owner actions; this record lists what they publish. The commit that the tag names changes the versions to `2.0.0`, and the owner rebuilds from it (section "Owner steps").

## What 2.0.0 is

- The [NCP 2 specification](../../spec/NCP-2.md), release candidate, revision 7, with revision 3 of the [rounds profile](../../spec/NCP-2-ROUNDS.md) and revision 5 of the [lockstep profile](../../spec/NCP-2-LOCKSTEP.md).
- `sepahead-ncp` 2.0.0 (now `2.0.0rc7`), the Python SDK (module `ncp`), standard library only: [`python/`](../../python/README.md).
- `sepahead-ncp-core` 2.0.0 (now `2.0.0-rc.7`), the Rust SDK (library `ncp`): [`rust/`](../../rust/README.md).
- `sepahead-ncp-zenoh` 2.0.0 (now `2.0.0rc7` and `2.0.0-rc.7`), the optional Zenoh binding for Python and for Rust: [`bindings/zenoh/`](../../bindings/zenoh/README.md).
- Supported platforms: Linux and macOS, on which both gates run in hosted CI. Windows is not tested.

The [README](../../README.md#ncp-2-benchmarks-speed-lag-and-correctness) summarizes the measurements, and [what NCP 2 changes from NCP 1](../design/NCP-1-SHORTCOMINGS.md) lists the evidence for each change and the work that remains.

## Artifacts

`scripts/build_ncp2_release.py` first checked that the four packages have one version, in the Python and the Rust spelling, that each binding requires that core version or a later compatible one, that each package holds both license texts, and that the package READMEs, which become the PyPI and crates.io pages, link with absolute URLs to files and headings that exist. It then built these files twice, each time from fresh copies of the files that Git tracks in the package directories, with every time in the archives set to the release date (`SOURCE_DATE_EPOCH` = 1794355200, 2026-11-11T00:00:00Z), and checked that the two builds are identical, byte for byte, and that every file holds both license texts. setuptools writes the build time into a source distribution, so the script rewrites each one with the same files and bytes, in the order of their names, with the release date as every time and without owners.

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `sepahead-ncp-core-2.0.0-rc.7.crate` | 76,952 | `68728d6b893d9b002b50d18f03f7dfbf6bf70cd05e4757bc20d1ebc69dcf730d` |
| `sepahead_ncp-2.0.0rc7-py3-none-any.whl` | 115,081 | `4afb91376d1a4c8dbada1e7aded0d6d98774f28ee72e69aa5e5327bbd77535d0` |
| `sepahead_ncp-2.0.0rc7.tar.gz` | 111,709 | `2f5aef02b200d5a06152806182bb560e82c558e034260b66348c15f02e2b0c52` |
| `sepahead_ncp_zenoh-2.0.0rc7-py3-none-any.whl` | 13,674 | `98db219d72bd8555c6554eddc3832fff36d7dc2b203e6937d3964a9ff5a4a1d2` |
| `sepahead_ncp_zenoh-2.0.0rc7.tar.gz` | 12,526 | `6817d4fb4bba78cb08dbfdd568f3fab50cde9d0e00326dd926374444457e0ad5` |

The Python package now ships the conformance vectors (`ncp/vectors.json`), which `python -m ncp conformance` reads; they make up most of its size.

- With the same tools (see below), a rebuild from any commit with the same package files and lockfiles gives the same five files.
- The crate archive was made from a copy outside Git. `cargo publish` from the tagged commit adds `.cargo_vcs_info.json`, with the commit, so the published archive differs from this one by that file.
- The crate `sepahead-ncp-zenoh` depends on `sepahead-ncp-core` from the registry, so it can be packaged and published only after `sepahead-ncp-core` is.

The checksums are in [`evidence/release/ncp-2.0.0/SHA256SUMS`](../../evidence/release/ncp-2.0.0/SHA256SUMS).

## Build environment

macOS 26.5.1 on an Apple M4 Max; Python 3.15.0 with `build` 1.6.1 and setuptools 84.1.0, which both `pyproject.toml` files pin; Rust 1.99.1 with Cargo 1.99.1.

## Dependencies

[`evidence/release/ncp-2.0.0/dependencies.json`](../../evidence/release/ncp-2.0.0/dependencies.json) lists every resolved Rust package of both crates, with its version, source, checksum, and license, and the requirements of both Python packages.

The packages require ranges, such as `serde` 1.0.229 or a later 1.x release, not exact versions: an exact requirement in a library would force every consumer onto that one version and fail when another of its dependencies needs a newer one. The lockfiles fix the versions that the checks and the artifacts used, and `dependencies.json` records them.

- `sepahead-ncp` requires nothing beyond Python 3.11 or later.
- `sepahead-ncp-zenoh` (Python) requires `sepahead-ncp` 2.0.0rc7 or a later 2.x release and `eclipse-zenoh` 1.10.2 or a later 1.x release (EPL-2.0 OR Apache-2.0); its tests use 1.10.2.
- `sepahead-ncp-core` uses `getrandom` 0.3.4, `serde` 1.0.229, `serde_json` 1.0.154, `sha2` 0.11.1, and `socket2` 0.6.5, or later compatible releases; with their own dependencies, 29 packages. Each is under terms that include MIT or Apache-2.0, and `unicode-ident` also under Unicode-3.0 terms. Of these, `r-efi`, `wasip2`, and `wit-bindgen` are built only for UEFI and WASI targets.
- `sepahead-ncp-zenoh` (Rust) resolves 312 packages with Zenoh 1.10.2. The Zenoh packages are under EPL-2.0 OR Apache-2.0, `webpki-roots` under CDLA-Permissive-2.0, and `option-ext` 0.2.0, which Zenoh reaches through `dirs`, under MPL-2.0, which requires that its own files, when changed and distributed, stay available as source; all others are under permissive terms such as MIT, Apache-2.0, BSD, ISC, and Zlib.
- The binding's lockfile holds `lz4_flex` 0.10.0, which `zenoh-transport` requires; the advisory GHSA-vvp9-7p8x-rfvv (RUSTSEC-2026-0041) concerns its decompression, which Zenoh uses only with the `transport_compression` feature, and the binding does not enable it.
- `scripts/check_ncp2_advisories.sh` checks both Rust lockfiles against the RustSec database, with their licenses, sources, and banned features. The core has no exception. The binding has five, each without a fix that it can select, because Zenoh 1.10.2 is the latest 1.x release: the advisory above, which holds only while its policy refuses `transport_compression`, and the maintenance notices of `paste`, `unsafe-libyaml`, `rustls-pemfile`, and `humantime`, which are not vulnerabilities.

## Checks

The commit that holds this record passed, on this computer: the NCP 2 gate (`scripts/check_ncp2.sh`: the rules data and the requirements map, both SDKs, the shared vectors against both SDKs and the Rust programs, the exhaustive model check of the SDK client and owner with its mutation test, the owners against the compiled Lean model, the Lean proofs with their axiom audit and mutation test, the modular-composition test, and differential fuzzing of 200,000 frames); the Zenoh gate (`scripts/check_ncp2_zenoh.sh`); and the release build above, with its checks of versions, license texts, and README links. The workflows `NCP 2` and `NCP 2 Zenoh binding` run the two gates on Linux and macOS.

## Gates for the tag

Each gate is PASS, with its evidence, NOT RUN, or OPEN, which is a decision of the owner. Local evidence is not independent evidence.

| Gate | State |
| --- | --- |
| Both NCP 2 gates on this computer (macOS) | PASS at the commit that holds this record (section "Checks") |
| Both NCP 2 gates on Linux and macOS in hosted CI | The workflows `NCP 2` and `NCP 2 Zenoh binding` run them on each push; the run of the tagged commit is the evidence |
| Reproducible release build | PASS at the commit that holds this record: two identical builds (section "Artifacts") |
| Advisories, licenses, and sources of both Rust lockfiles | PASS on this computer on 18 November 2026 with the RustSec database at `472a4c9a` (`scripts/check_ncp2_advisories.sh`, section "Dependencies"); the workflow `NCP 2 advisories` repeats the check on each change and every week, and its run at the tagged commit is the evidence for the tag |
| Benchmarks and fault campaign on the revision that the tag names | NOT RUN: they ran with revision 2 of the SDKs; revision 7 changed the owner, the client, and both profiles |
| Fault campaign on the Zenoh binding, with owner restarts, session expiry, delayed and repeated `open`, and replayed frames | NOT RUN |
| Benchmark of the Zenoh binding | NOT RUN |
| A consumer of the exchange over the byte-stream binding | PASS: CREBAIN's closed loop and NEST controller on revision 4 (CREBAIN `a1df34c`) |
| A consumer of streams, of the Zenoh binding, of contract schemas, of authenticated frames, of feature operations, of decline reasons, and of each profile | NOT RUN: none uses them yet |
| Model check of the lockstep profile | PASS with one fault for revision 5, in the NCP 2 gate (`model/lockstep.py`, 565,424 worlds, with its self-test of seventeen known defects). Two faults: NOT RUN for revision 5 (an advisory run checked revision 4) |
| Model check of the rounds profile | NOT RUN |
| An implementation by another author | NOT RUN |
| External review | NOT RUN |
| Signatures, SBOM, and provenance of the published files | NOT RUN |
| Which parts the tag freezes | OPEN. The advisory design review of revision 6 recommends a freeze of the exercised core, with streams, the Zenoh binding, schemas, the key and TLS guidance, and both profiles provisional, each with its own revision. Revision 7 adds the text that it asked for before a freeze ([migration plan](../design/NCP-2-MIGRATION.md#open-work-after-revision-7)) |

## Owner steps

1. Decide which gates above must pass before the tag, and which parts the tag freezes. In one commit, change the versions of the four packages and the implementation string of the Python SDK from the release candidate to `2.0.0`, run both gates and the release build, and update the artifact table of this record. Then create the tag `v2.0.0` on that commit. The wire versions of NCP 1 used `v0.x`, `v1.0.0` stays reserved for the unreleased wire-1.0 candidate, and the local SDK used `sdk-v1.0.x`.
2. In a clean checkout of the tag, run `python3 scripts/build_ncp2_release.py OUT --python PYTHON`, with a PYTHON that has `build` 1.6.1, and compare `OUT/SHA256SUMS` with [`evidence/release/ncp-2.0.0/SHA256SUMS`](../../evidence/release/ncp-2.0.0/SHA256SUMS). With the tools above, the files are the same. Publish the Python files to PyPI, `sepahead-ncp` before `sepahead-ncp-zenoh`.
3. Publish the crates to crates.io: `cargo publish` in `rust/`, then in `bindings/zenoh/rust/`.

## Not part of this release

- The projects that use NCP 1 move to NCP 2 one at a time ([migration plan](../design/NCP-2-MIGRATION.md)); NCP 1 stays on the main branch until the last one has moved.
- The Zenoh binding has not yet been measured in a benchmark.
