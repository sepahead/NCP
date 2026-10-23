# NCP local SDK release record

This page records the releases of the standalone `ncp-local` packages: version `1.0.1` under the tag `sdk-v1.0.1`, and version `1.0.0` under the tag `sdk-v1.0.0`.
It states what each release contains, what stays unreleased, why the scope was chosen, and how to verify a release.

Author and maintainer: **[Sepehr Mahmoudian](https://github.com/sepahead)**.

## SDK 1.0.1

Version `1.0.1` is a patch release. It makes both SDKs faster and keeps every check, every public interface, and every byte on the wire.

| Released item | Identity |
| --- | --- |
| Rust package | `ncp-local` `1.0.1`, from [`local/rust`](../rust/README.md) |
| Python package | `ncp-local` `1.0.1`, import name `ncp_local`, from [`local/python`](../python/README.md) |
| Contracts implemented | Unchanged from 1.0.0. The descriptors and their digests are identical. |
| Tag | Annotated, unsigned `sdk-v1.0.1` on one exact `main` commit |

### What changed

- **Rust.** The profile digest is derived once per process. In 1.0.0, each `LocalResponse::verify_integrity` call derived it again from the 41 KB descriptor.
  Request and response digests use a typed projection without an intermediate `serde_json::Value`.
  The owner serializes each response once, writes the digest into the placeholder of the last member, and keeps that digest instead of parsing its own output again.
- **Python.** `preflight` uses `_RunScanner`, a subclass of the unchanged reference scanner.
  It matches whole runs of whitespace, unescaped ASCII strings, and numbers with regular expressions, consumes exactly the characters of the reference loop, and applies the same checks.
  Every other input uses the reference method.
  The client encodes each request once and sends the bytes that its snapshot came from. The owner encodes each response once and writes the digest into its placeholder.

### Why the reference revision moved

`scripts/check_local_sdk.py` pins the local SDK sources to a reference revision. Until 1.0.1, that revision was `de751d4`, the 1.0.0 sources.
The owner decided on 22 October 2026 to move it to the 1.0.1 sources, commit `8346549`.
That commit differs from `f29bcc8`, which the benchmark measured, only by the formatting of one line in `wire.py` and of the new test.
No qualification receipt binds the earlier bytes, and the descriptor and its digest did not change.
The equivalence evidence below supports the decision. It does not replace a new qualification of the fixed-role reference.

### Equivalence evidence

| Evidence | Result |
| --- | --- |
| Rust owner transcript: valid steps, retries, result lookups, wrong and repeated acknowledgements, a role violation, a foreign run, sequence gaps, and the finish | The released and the 1.0.1 owner print the same 48 lines. |
| Python transcript: request bytes, owner outputs, and `LocalClient` frames over real pipes, including a backend failure, a rejected body, an oversized request, and a bad sequence number | The released and the 1.0.1 SDK print the same 70 lines. |
| Differential scan of `_RunScanner` against the reference scanner | 5,138,806 inputs gave the same outcome, error code, position, and counters. `tests/test_run_scanner.py` repeats a seeded subset in each run. |
| Typed and generic Rust digests | Unit tests compare both forms for every operation, outcome, code, and role, and for bodies of every JSON kind. |
| Suites | `ncp-core` (413 tests), `ncp-local` Rust, `local/python/tests`, `local/profile`, and `local/modular` with the Rust probes pass. `scripts/check_local_sdk.py` reports `LOCAL_SDK_CONTROLS_PASS`. |

### Measured speed

[Protocol 2](../../benchmarks/local-sdk-exchange/PROTOCOL-2.md) of the local SDK exchange benchmark fixed four hypotheses before its runs.
All 140 runs were valid, and all four hypotheses hold.
The table gives the median time of one lockstep call with an echo owner: one request and one acknowledgement, each with its verified response.

| Client and owner | Spikes per step | 1.0.0 | 1.0.1 | Paired ratio |
| --- | --- | --- | --- | --- |
| Rust and Rust | 0 | 359 µs | 41 µs | 8.9 |
| Rust and Rust | 127 | 403 µs | 74 µs | 5.5 |
| Python and Python | 0 | 1518 µs | 504 µs | 3.0 |
| Python and Python | 127 | 4252 µs | 1339 µs | 3.2 |
| Python and Rust | 0 | 862 µs | 259 µs | 3.3 |
| Rust and Python | 0 | 976 µs | 227 µs | 4.3 |

A framed echo between two processes took 7 µs in Rust and 15 µs in Python on the same computer.
The [benchmark README](../../benchmarks/local-sdk-exchange/README.md) gives the computer, software, times, and all configurations.

## SDK 1.0.0

This section records the first release, of version `1.0.0` under the tag `sdk-v1.0.0`.

### What is released

| Released item | Identity |
| --- | --- |
| Rust package | `ncp-local` `1.0.0`, from [`local/rust`](../rust/README.md) |
| Python package | `ncp-local` `1.0.0`, import name `ncp_local`, from [`local/python`](../python/README.md) |
| Contracts implemented | The [modular owner contract](owner.md) with its [core descriptor](../../ncp-core/src/modular_profile.v1.json), and the local-lockstep [descriptor](../../ncp-core/local-profile.v1.json) |
| Tag | Annotated, unsigned `sdk-v1.0.0` on one exact `main` commit |

Both packages provide bounded frames, exact typed digests, retained outcomes, acknowledgements, and bounded byte buffers.
The Python package uses only the standard library. The Rust package pins its three dependencies exactly and forbids unsafe code.

The GitHub release for `sdk-v1.0.0` attaches the Python wheel, the Rust package archive, a source archive of the tagged tree, SHA-256 and SHA-512 checksum lists, and a provenance record.
The provenance record names the tag, commit, tree, complete local gate result, hosted CI run, toolchains, and fixed build timestamp.

### Council decision

Five review lenses assessed each option: scientific validity, runtime correctness, security and provenance, statistics and generalization, and maintenance and operations.
A failed lens blocks its option even when the other lenses pass.

| Option | Decision | Deciding lens |
| --- | --- | --- |
| Tag the protocol `v1.0.0` now | Rejected | Security and provenance: the external reviews, signed provenance, and independent reproduction required by [VERSIONING.md](../../VERSIONING.md) are not run, and the release workflow deliberately refuses every current `v*` tag. |
| Tag the fixed-role reference `local-v1.0.0` | Rejected | Runtime correctness: its bootstrap, operational, and publication receipts are null. |
| Keep every scope tagless | Rejected | Maintenance and operations: the maintainer requested a v1 release, and the SDK scope meets its own gates. |
| Upload the packages to registries | Deferred | Security and provenance: registry uploads cannot be withdrawn cleanly, and registry rights are not verified. |
| Release the SDK packages as `sdk-v1.0.0` | Accepted | All five lenses pass for the stated scope and exclusions. |

Scientific validity passes because the release claims no experiment result.
Statistics and generalization pass because no measured application envelope is generalized.
Runtime correctness rests on the complete gate and hosted CI for the exact commit.
Security and provenance rest on locked builds, reproducible artifacts, and published checksums, with the absence of signatures stated.
Maintenance and operations pass because the separate tag namespace cannot trigger the protocol release workflow.

## What is not released

| Scope | Status |
| --- | --- |
| Broader protocol candidate `1.0.0-rc.1`, wire `1.0` | Unreleased and release-blocked. The protocol tag `v1.0.0` stays reserved for the sequence in [VERSIONING.md](../../VERSIONING.md). |
| Fixed-role reference `ncp.local-lockstep.v1` | Its [release registry](../release.v1.json) keeps its intended tag `local-v1.0.0` and its open receipts. |
| Modular product v1 | Installed qualification of each advertised application combination remains open, as listed in the [README](../../README.md#remaining-product-v1-work). |
| Package registries | No upload to crates.io or PyPI. Registry rights and self-contained distribution remain external prerequisites. |
| Signatures and attestations | Commits and tags stay unsigned by repository policy. Checksums detect corruption or substitution; they do not prove who produced the files. |

The released packages grant no remote, physical, real-time, or scientific authority.
Application evidence stays with the owning application and its dated receipts.

## Release conditions

A release tag may point only to a commit that meets every condition below.

1. The complete local gate `scripts/check.sh` passed on that exact commit, including the standalone SDK source and installed-wheel controls.
2. The hosted CI run for that exact commit passed every job.
3. The package sources are unchanged between the gated commit and the built artifacts.
4. Two independent builds of the wheel and the Rust package archive from the tagged tree have identical SHA-256 digests.
5. A fresh virtual environment installs the released wheel without dependencies and passes the SDK suites against the installed bytes.

The attached provenance record reports the evidence for each condition.

## Compatibility promise

Later `1.x` releases of `ncp-local` keep the published descriptors and the public Rust and Python interfaces backward compatible.
A breaking change requires `2.0.0`.
The SDK line does not change the protocol's package version, `ncp_version`, contract manifest, or released `v0.8.0` baseline.

## Verify a release

Replace `VERSION` with `1.0.1` or `1.0.0`.

```text
gh release download sdk-vVERSION --repo sepahead/NCP --dir ncp-sdk-vVERSION
cd ncp-sdk-vVERSION
shasum -a 256 -c SHA256SUMS
shasum -a 512 -c SHA512SUMS
git clone https://github.com/sepahead/NCP.git repository
mkdir tagged attached
git -C repository archive --format=tar --prefix=NCP-sdk-vVERSION/ sdk-vVERSION | tar -xf - -C tagged
tar -xzf NCP-sdk-vVERSION-source.tar.gz -C attached
diff -r tagged attached
python3 -m venv fresh
fresh/bin/python -m pip install --no-deps --no-index ncp_local-VERSION-py3-none-any.whl
cd repository && git checkout --detach sdk-vVERSION
../fresh/bin/python -I -m unittest discover -s local/python/tests -v
```

On Linux, `sha256sum -c` and `sha512sum -c` replace the `shasum` commands.
The complete installed-wheel and cross-language controls run through `python3 scripts/check_local_sdk.py` in a checkout of the tag.
That script needs Python 3.11 or later and the Rust `1.88.0` and `1.96.0` toolchains.
