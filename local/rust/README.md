# NCP local Rust SDK

Status: release candidate. Installed qualification and publication remain open.

This standalone package implements `ncp.local-lockstep.v1`.
It contains bounded JSON framing, typed digests, fixed endpoint roles, exact retained outcomes, and the shared simulation data contract.

The independent [Python SDK](../python/README.md) implements the same descriptor.
The [local guide](../../docs/local-v1/README.md) defines the supported application envelope and remaining release gates.

The broader `ncp-core` and Zenoh candidate retain their separate, unpassed release gates.
This package does not depend on those candidate packages.
Local success grants no remote, physical, or scientific authority.

## Source and build

The generated source projection contains four byte-identical canonical modules and the exact shared descriptor.
Its source map records each source path, transformation, and SHA-256 digest.
Only test and example imports receive the mechanical package-name substitution.

Before a build, verify the source projection:

```sh
python3 scripts/project_local_rust.py --check
cargo test --manifest-path local/rust/Cargo.toml --locked
cargo clippy --manifest-path local/rust/Cargo.toml --all-targets --locked -- -D warnings
cargo package --manifest-path local/rust/Cargo.toml --locked
```

The commands run from the repository root.
An extracted package builds independently from its own manifest and lockfile.
The generation command is `python3 scripts/project_local_rust.py --write`.

The SDK exposes the `local` and `local_data` modules.
`bounded_json` supplies a structural scanner for bounded local storage tools.
The wire entrypoint also enforces its stricter 65,536-byte frame bound.

## Limits

The caller installs each role and fresh generation before opening its private channel.
Only one result can remain owed per endpoint.
An exact acknowledgement releases that result; it cannot authorize replay.
Execution uncertainty retires the generation.
This package does not resume a crashed generation.

The package does not reserve operating-system memory or physical disk space.
Its allocation and storage checks enforce declared logical bounds.
Application and process owners must enforce their separate resource and lifecycle contracts.
