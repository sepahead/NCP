# NCP versioning and compatibility

> **Candidate status:** repository HEAD is the unreleased `1.0.0-rc.1` package
> candidate, wire `1.0`, compact proto hash `163acc57d8a62b66`. The latest immutable
> release remains `v0.8.0`; no `v1.0.0` tag or 1.0 publication exists.

NCP has four separate identities:

- package SemVer identifies a source/artifact release (`1.0.0-rc.1` at HEAD);
- `ncp_version` identifies wire compatibility (`1.0` at HEAD);
- the complete SHA-256 digest in
  [`contract/manifest.v1.json`](contract/manifest.v1.json) identifies the exact
  normative contract. The 16-hex `CONTRACT_HASH` is only an advisory digest of the
  canonical protobuf structure;
- package builds expose a build/source identity. The checked-in RC uses
  `unreleased-worktree`, which is deliberately non-certifying. An immutable release
  builder must inject an exact source identity and bind it to artifact provenance.
  A raw Rust `NCP_BUILD_IDENTITY` environment value is only a compiler input and is
  not release validation. The fail-closed npm builder accepts one exact lowercase
  40-hex `HEAD`, verifies the Rust seam, and injects TypeScript only in an archived
  staging tree; normal regeneration cannot create a certifying package.

## Compatibility rule

Wire versions contain one or two canonical ASCII-decimal `u64` components and no
suffix. Zero is exactly `0`; a nonzero component has no leading zero. Signs,
whitespace, Unicode digits, values above `18446744073709551615`, patch components,
and trailing junk fail closed. `1` means `1.0`. A stable 1.x peer accepts another
well-formed version with major `1`; minor releases on a published 1.x line must
therefore be additive-compatible.

Before 1.0, minor was breaking. Wire 0.8 therefore accepts only 0.8 and cannot
interoperate natively with 1.x. The migration boundary is the labelled terminating
gateway described in [`INTEGRATING.md`](INTEGRATING.md), never version coercion.

Within a published 1.x line:

- optional fields and values in enums explicitly documented as open may be added
  only where every older path remains safe. At wire 1.0 only `Mode` is open, and
  every unknown/additive mode is non-authorizing and governed as HOLD;
- stable fields, message kinds, enum values, semantics, limits, or requirements
  may not be removed or weakened;
- a field may not change type or become required;
- security/authority defaults may never become permissive;
- experimental/excluded features do not become stable by use.

A breaking change requires wire/package major 2 and a new frozen baseline. Package
patch releases may fix implementations without changing normative wire semantics.

## Candidate freeze and release

`conformance/baseline/v1.0.0/` is a candidate audit snapshot of the JSON projection,
not proof of release. `scripts/check_wire_baseline.py` enforces additive compatibility
and its `--verify-current-cut` mode proves the current wire minor's pre-tag snapshot
matches the current schema and canonical vectors without a hard-coded release path.

Released baselines are a separate historical-integrity boundary. The machine
registry at `conformance/baseline/released-baselines.v1.json` binds each of
`v0.5.0` through `v0.8.0` to its exact annotated-tag object, directly named commit,
fixed baseline path, and subtree object. `scripts/check_released_baselines.py`
read-only compares every checked-out file's Git mode and blob ID with that tag tree;
missing, extra, changed, symlinked, or moved baseline content and missing, moved, or
lightweight tags fail. This proves local identity with the registered Git objects;
it does not verify tag signatures, certify artifacts, or release the 1.0
candidate.

The protobuf breaking gate uses that same verified registry. It reads the exact
`package ncp.vMAJOR` from HEAD and from every registered release commit, then compares
with the greatest registered same-major release using its peeled commit OID. There is
no released `ncp.v1` baseline yet, so the initial 1.0 candidate explicitly reports
"no same-major released baseline" and runs no Buf comparison. Comparing it with
`v0.8.0`/`ncp.v0` would reject the intentional major break and is forbidden. After an
annotated v1 release is registered, every later v1 candidate must pass Buf
`WIRE`/`WIRE_JSON` compatibility against the latest registered v1 release. Malformed,
missing, reordered, or moved registry/tag/proto inputs fail closed.

The release sequence is:

1. freeze the normative sources and candidate JSON baseline;
2. compute the full normative digest and build all packages from one source;
3. pass zero-skip local and external gates, including consumers;
4. produce signed SBOM, provenance, checksums, and independent reproduction;
5. only then create the annotated immutable `v1.0.0` tag and publish artifacts.

Until step 5, use the candidate only for development. Do not pin `main`, an RC
version, or a candidate source revision as though it were the stable 1.0 release.
Legacy deployments that require the released contract must retain the immutable
`v0.8.0` pin and its limitations.
