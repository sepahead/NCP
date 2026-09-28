# NCP local SDK 1.0.0 release record

This page records the release of the standalone `ncp-local` packages as version `1.0.0` under the tag `sdk-v1.0.0`.
It states what the release contains, what it leaves unreleased, why this scope was chosen, and how to verify it.

Author and maintainer: **[Sepehr Mahmoudian](https://github.com/sepahead)**.

## What is released

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

## What is not released

| Scope | Status after this release |
| --- | --- |
| Broader protocol candidate `1.0.0-rc.1`, wire `1.0` | Unreleased and release-blocked. The protocol tag `v1.0.0` stays reserved for the sequence in [VERSIONING.md](../../VERSIONING.md). |
| Fixed-role reference `ncp.local-lockstep.v1` | Its [release registry](../release.v1.json) keeps its intended tag `local-v1.0.0` and its open receipts. |
| Modular product v1 | Installed qualification of each advertised application combination remains open, as listed in the [README](../../README.md#remaining-product-v1-work). |
| Package registries | No upload to crates.io or PyPI. Registry rights and self-contained distribution remain external prerequisites. |
| Signatures and attestations | Commits and tags stay unsigned by repository policy. Checksums detect corruption or substitution; they do not prove who produced the files. |

The released packages grant no remote, physical, real-time, or scientific authority.
Application evidence stays with the owning application and its dated receipts.

## Release conditions

The tag may point only to a commit that meets every condition below.

1. The complete local gate `scripts/check.sh` passed on that exact commit, including the standalone SDK source and installed-wheel controls.
2. The hosted CI run for that exact commit passed every job.
3. The package sources are unchanged between the gated commit and the built artifacts.
4. Two independent builds of the wheel and the Rust package archive from the tagged tree have identical SHA-256 digests.
5. A fresh virtual environment installs the released wheel without dependencies and passes the SDK suites against the installed bytes.

The attached provenance record reports the evidence for each condition.

## Council decision

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

## Compatibility promise

Later `1.x` releases of `ncp-local` keep the published descriptors and the public Rust and Python interfaces backward compatible.
A breaking change requires `2.0.0`.
The SDK line does not change the protocol's package version, `ncp_version`, contract manifest, or released `v0.8.0` baseline.

## Verify the release

```text
gh release download sdk-v1.0.0 --repo sepahead/NCP --dir ncp-sdk-v1.0.0
cd ncp-sdk-v1.0.0
shasum -a 256 -c SHA256SUMS
shasum -a 512 -c SHA512SUMS
git clone https://github.com/sepahead/NCP.git repository
mkdir tagged attached
git -C repository archive --format=tar --prefix=NCP-sdk-v1.0.0/ sdk-v1.0.0 | tar -xf - -C tagged
tar -xzf NCP-sdk-v1.0.0-source.tar.gz -C attached
diff -r tagged attached
python3 -m venv fresh
fresh/bin/python -m pip install --no-deps --no-index ncp_local-1.0.0-py3-none-any.whl
cd repository && git checkout --detach sdk-v1.0.0
../fresh/bin/python -I -m unittest discover -s local/python/tests -v
```

On Linux, `sha256sum -c` and `sha512sum -c` replace the `shasum` commands.
The complete installed-wheel and cross-language controls run through `python3 scripts/check_local_sdk.py` in a checkout of the tag.
That script needs Python 3.11 or later and the Rust `1.88.0` and `1.96.0` toolchains.
