# NCP Versioning & Compatibility Policy

The wire contract carries a string `ncp_version` on every message. This document
is the **published versioning/breaking-change policy** — one of the artifacts a
protocol needs to become a standard (cf. MCP's date-based policy, OMG DDS's
interop program).

## Scheme: SemVer of the wire contract

NCP versions the **wire contract** (`proto/ncp.proto` + the JSON-Schema
projection) with [SemVer](https://semver.org): `MAJOR.MINOR.PATCH`.

- **MAJOR** — a backwards-incompatible wire change (removed/renamed field,
  changed type, removed enum value, changed semantics).
- **MINOR** — a backwards-compatible addition (new optional field, new enum
  value, new message). Existing peers keep interoperating.
- **PATCH** — clarifications/docs with no wire effect.

**Wire version vs crate/package version.** The `ncp_version` *wire* string
(currently `0.3`) versions the contract; the Rust crates and the `@sepehrmn/ncp`
package carry their own SemVer (see `Cargo.toml` / `package.json` for the current
SDK version — the manifests are the single source of truth) for the SDK. They usually move
together, but a PATCH that touches only code/docs/build artifacts (e.g. `0.3.0` →
`0.3.1`) leaves the wire at `0.3`. **Pin `tag = "v0.3.0"`** for the wire baseline
(what the `buf breaking` gate compares against); the crate at that-or-later tag is
wire-`0.3`-compatible.

**Pre-1.0 caveat (current):** while `0.x`, a **minor bump is treated as
breaking** — the version guard fails closed on any `0.x` minor difference
(`check_version`). Pin an exact version (`tag = "v0.3.0"`) for anything you build
against. `0.x` is explicitly unstable.

The current wire is **`0.3`** (`ncp_version = "0.3"`); receivers check the full
`ncp_version` and pre-1.0 require an exact `(major, minor)` match — any `0.x`
minor difference is fail-closed (see §version negotiation). `0.3`
added the symmetric `contract_hash` handshake field on `OpenSession`/`SessionOpened`
over `0.2` — additive, but a pre-1.0 minor bump, so a `0.2` peer is fail-closed
rejected. (`0.2` had added the neuron-family wire (#10) and bulk column codec (#6).)

## Enforcement: `buf breaking`

Breaking changes are caught mechanically, language-agnostically, by Buf's tiered
rules (configured in `buf.yaml`):

- **`WIRE` / `WIRE_JSON`** — binary and JSON wire compatibility (the contract).
- **`FILE` / `PACKAGE`** — source/codegen-level stability.

CI runs `buf lint`; `buf breaking` gates the wire against the first tag of the
current wire (`v0.3.0`, the wire-`0.3` baseline — see `.github/workflows/ci.yml`).
A change that trips `WIRE`/`WIRE_JSON` **must** bump MAJOR (or MINOR while `0.x`).

## Per-session version + contract handshake (landed in v0.3.0)

`check_version` / `negotiate` are **fail-closed library entry points**: a peer (or
gateway) calls `negotiate(peer_version, peer_hash)` at session setup and refuses a
mismatch (reject, never coerce). As of **v0.3.0** this is wired into an explicit
`open_session` handshake (it is still not auto-invoked on the *data-plane* receive
path — a version-mismatched frame there is handled by the deserializer as a parse
failure / dropped frame, not an explicit version error):

1. The client sends its `ncp_version` **and** `contract_hash` in `OpenSession`.
2. The server verifies both (`negotiate`) before doing any work; if it cannot serve
   a compatible major/minor, or the contract hash differs, it replies
   `SessionOpened{ ok: false, error: "…" }` and the session does not open (fail
   closed, never silently coerce). The reference server half is engram's
   `SessionService.handle`; the client half is `ncp-zenoh::ZenohNcpClient::open`,
   which `negotiate`s the `SessionOpened.contract_hash` it gets back.
3. Peers MAY support multiple versions but MUST agree on exactly one per session.

This turns "I refuse" into "we agreed (or explicitly did not)", which is what a
multi-peer protocol needs.

## Contract hash (the wire-identity digest)

`ncp_version` says *which version* a peer speaks; `CONTRACT_HASH` says *which exact
contract* — it is the FNV-1a digest of the **canonicalized** `proto/ncp.proto`
(`canonical_proto` strips `//` and `/* */` comments — respecting string literals —
and normalizes whitespace). Two peers agree iff their *semantic* contracts agree,
**independent of comments or formatting** (a comment-only edit no longer flips the
hash — the churn the `v0.2.5`/`v0.2.6` releases documented). It is **not** a
cryptographic MAC: adversarial integrity is the transport's job (mTLS); the hash
detects *accidental* drift / a post-agreement "rug-pull" schema mutation.

**Why it is a hardcoded constant** (`ncp_core::CONTRACT_HASH`, and the mirrored
`backend/neurocontrol/protocol.py::CONTRACT_HASH`) rather than computed at runtime:

- **The proto is not on disk at runtime.** `contract_hash_of_proto` reads the
  `.proto` via `CARGO_MANIFEST_DIR`, which only exists in the source tree at
  build/test time. A shipped binary / wheel / C ABI has no proto to hash, so the
  advertised value must be embedded.
- **It is a contract *identity*, not a derived quantity.** A pinned constant makes
  "which wire do I claim to speak" explicit, greppable, and reviewable, and makes a
  bump a deliberate, visible diff.
- **It is the shared cross-language anchor.** Rust and Python pin the *same* string
  and each recomputes it from its own proto copy in a test; the constant is the
  single value both are checked against, so a canonicalization bug in one language
  fails CI instead of silently yielding two hashes that reject each other.
- **Drift cannot ship.** `contract_hash_matches_proto` (Rust) and
  `test_contract_hash_matches_vendored_proto` (Python) assert the constant equals the
  computed value, so it is "hardcoded, but *provably equal* to the computed value."

The considered-and-rejected alternative is to drop the constant and compute it once
at startup from a compile-time-embedded proto
(`LazyLock::new(|| contract_hash_of_proto(include_str!(".../ncp.proto").as_bytes()))`).
That removes the forgot-to-bump error class but loses `const`-usability, the
greppable value, and the deliberate-bump property — and still needs a per-language
anchor for cross-language parity. The constant-plus-CI-guard form is intentional.

## Deprecation

A field/enum value being retired is first marked deprecated in `proto/ncp.proto`
(a comment + `[deprecated = true]`) for one MINOR cycle before removal in the next
MAJOR, so consumers get a compile-time / lint warning before the break.
