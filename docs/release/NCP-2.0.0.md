# NCP 2.0.0 release record

Status: prepared on 11 November 2026. The tag and the publication of the packages are owner actions; this record lists what they publish.

## What 2.0.0 is

- The [NCP 2 specification](../../spec/NCP-2.md), final, with the [rounds profile](../../spec/NCP-2-ROUNDS.md).
- `sepahead-ncp` 2.0.0, the Python SDK (module `ncp`), standard library only: [`python/`](../../python/README.md).
- `sepahead-ncp-core` 2.0.0, the Rust SDK (library `ncp`): [`rust/`](../../rust/README.md).
- `sepahead-ncp-zenoh` 2.0.0, the optional Zenoh binding for Python and for Rust: [`bindings/zenoh/`](../../bindings/zenoh/README.md).

The [README](../../README.md#ncp-2-benchmarks-speed-lag-and-correctness) summarizes the measurements, and [what NCP 2 changes from NCP 1](../design/NCP-1-SHORTCOMINGS.md) lists the evidence for each change and the work that remains.

## Artifacts

`scripts/build_ncp2_release.py` first checked that the four packages have one version, that each binding requires exactly that core version, that each package holds both license texts, and that the package READMEs, which become the PyPI and crates.io pages, link with absolute URLs to files and headings that exist. It then built these files twice, each time from fresh copies of the files that Git tracks in the package directories, with every time in the archives set to the release date (`SOURCE_DATE_EPOCH` = 1794355200, 2026-11-11T00:00:00Z), and checked that the two builds are identical, byte for byte, and that every file holds both license texts. setuptools writes the build time into a source distribution, so the script rewrites each one with the same files and bytes, in the order of their names, with the release date as every time and without owners.

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `sepahead-ncp-core-2.0.0.crate` | 36,557 | `74c71dfc590bb6e141b0a4c72e32ae459e947ff41eeccc65ffdb189c32a09113` |
| `sepahead_ncp-2.0.0-py3-none-any.whl` | 34,759 | `96f70b8cbeed036188f61f187944d7bc952298fe11e1af39bd0a6fc3a972fbdb` |
| `sepahead_ncp-2.0.0.tar.gz` | 33,648 | `fd0be4d4c906253948f8677d4a15cff7d3c6f72d07207d63fe1633929b1046e6` |
| `sepahead_ncp_zenoh-2.0.0-py3-none-any.whl` | 11,699 | `09d6676f848b4e041f579d7ab4ab1ffbac3b5e96d74651db91abc68d930dbc65` |
| `sepahead_ncp_zenoh-2.0.0.tar.gz` | 10,595 | `516999aeb26f3906955d452229c50cd691f1b7aecc2d99ef8b05d327a4730463` |

- With the same tools (see below), a rebuild from any commit with the same package files and lockfiles gives the same five files; a third build, run separately, gave the same checksums.
- The crate archive was made from a copy outside Git. `cargo publish` from the tagged commit adds `.cargo_vcs_info.json`, with the commit, so the published archive differs from this one by that file.
- The crate `sepahead-ncp-zenoh` depends on `sepahead-ncp-core` from the registry, so it can be packaged and published only after `sepahead-ncp-core` is.

The checksums are in [`evidence/release/ncp-2.0.0/SHA256SUMS`](../../evidence/release/ncp-2.0.0/SHA256SUMS).

## Build environment

macOS 26.5.1 on an Apple M4 Max; Python 3.15.0 with `build` 1.6.1 and setuptools 84.1.0, which both `pyproject.toml` files pin; Rust 1.99.1 with Cargo 1.99.1.

## Dependencies

[`evidence/release/ncp-2.0.0/dependencies.json`](../../evidence/release/ncp-2.0.0/dependencies.json) lists every resolved Rust package of both crates, with its version, source, checksum, and license, and the requirements of both Python packages.

The packages require ranges, such as `serde` 1.0.229 or a later 1.x release, not exact versions: an exact requirement in a library would force every consumer onto that one version and fail when another of its dependencies needs a newer one. The lockfiles fix the versions that the checks and the artifacts used, and `dependencies.json` records them.

- `sepahead-ncp` requires nothing beyond Python 3.11 or later.
- `sepahead-ncp-zenoh` (Python) requires `sepahead-ncp` 2.0.0 or a later 2.x release and `eclipse-zenoh` 1.10.2 or a later 1.x release (EPL-2.0 OR Apache-2.0); its tests use 1.10.2.
- `sepahead-ncp-core` uses `serde` 1.0.229, `serde_json` 1.0.154, `sha2` 0.11.1, and `socket2` 0.6.5, or later compatible releases; with their own dependencies, 25 packages, all under MIT, Apache-2.0, Unlicense, or Unicode-3.0 terms.
- `sepahead-ncp-zenoh` (Rust) resolves 312 packages with Zenoh 1.10.2. The Zenoh packages are under EPL-2.0 OR Apache-2.0, `webpki-roots` under CDLA-Permissive-2.0, and `option-ext` 0.2.0, which Zenoh reaches through `dirs`, under MPL-2.0, which requires that its own files, when changed and distributed, stay available as source; all others are under permissive terms such as MIT, Apache-2.0, BSD, ISC, and Zlib.
- The binding's lockfile holds `lz4_flex` 0.10.0, which `zenoh-transport` requires; the advisory GHSA-vvp9-7p8x-rfvv concerns its decompression, which Zenoh uses only with the `transport_compression` feature, and the binding does not enable it.

## Checks

The commit that holds this record passed, on this computer: the NCP 2 gate (`scripts/check_ncp2.sh`: both SDKs, the shared vectors, the model check and the model conformance of both owners, the Lean proofs with their axiom audit, the modular-composition test, and differential fuzzing of 200,000 frames); the Zenoh gate (`scripts/check_ncp2_zenoh.sh`); the release-owned machine-contract gates of the CI workflow; and the release build above, with its checks of versions, license texts, and README links. The workflows `NCP 2` and `NCP 2 Zenoh binding` run the two gates on Linux and macOS.

## Owner steps

1. Create the tag `v2.0.0` on the commit that holds this record. The wire versions of NCP 1 used `v0.x`, `v1.0.0` stays reserved for the unreleased wire-1.0 candidate, and the local SDK used `sdk-v1.0.x`.
2. In a clean checkout of the tag, run `python3 scripts/build_ncp2_release.py OUT --python PYTHON`, with a PYTHON that has `build` 1.6.1, and compare `OUT/SHA256SUMS` with [`evidence/release/ncp-2.0.0/SHA256SUMS`](../../evidence/release/ncp-2.0.0/SHA256SUMS). With the tools above, the files are the same. Publish the Python files to PyPI, `sepahead-ncp` before `sepahead-ncp-zenoh`.
3. Publish the crates to crates.io: `cargo publish` in `rust/`, then in `bindings/zenoh/rust/`.

## Not part of this release

- The projects that use NCP 1 move to NCP 2 one at a time ([migration plan](../design/NCP-2-MIGRATION.md)); NCP 1 stays on the main branch until the last one has moved.
- The Zenoh binding has not yet been measured in a benchmark.
