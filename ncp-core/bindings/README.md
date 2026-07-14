# Generated TypeScript message types

These files are generated from the Rust reference types for the unreleased NCP
`1.0.0-rc.1` candidate. They are checked against the normative proto, JSON Schemas,
and corpus; they are not an additional source of truth and must not be edited by
hand.

```bash
cargo test -p ncp-core --features ts
node ncp-ts/scripts/sync-bindings.mjs
```

The sync step normalizes generator whitespace and copies the exact output into
`ncp-ts/src/generated/`; the TypeScript build then reproduces `ncp-ts/dist/`.
Rust `i64` values are represented as `bigint` in generated type declarations, while
the runtime JSON client uses the recursive `Wire<T>` projection and rejects values
outside the IEEE-754 safe-integer range.

Import the public surface from `@sepahead/ncp`, not directly from this directory.
The package also supplies independent semantic validation and bounded parsing; these
generated declarations alone do not authenticate or validate a message.
