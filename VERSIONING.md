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
(currently `0.6`) versions the contract; the Rust crates and the `@sepahead/ncp`
package carry their own SemVer (see `Cargo.toml` / `package.json` for the current
SDK version — the manifests are the single source of truth) for the SDK. They usually move
together, but a PATCH that touches only code/docs/build artifacts (e.g. `0.5.0` →
`0.5.3` on the previous wire) leaves the wire string unchanged. **Pin
`tag = "v0.6.0"`** for the current wire baseline (what the `buf breaking` gate
compares against); the crate at that-or-later tag is wire-`0.6`-compatible.

**Wire 0.6 is a SEMANTIC break with an unchanged serialization.** No field,
type, or encoding changed — `CONTRACT_HASH` is identical to wire 0.5
(`24e8e6e31e1dec8a`) — but what a conforming peer MUST send changed: every
message must carry a compatible `ncp_version` (an absent version deserializes to
a detectable `""` and is rejected, never coerced to the receiver's own), and the
closed-loop frames must stamp `seq` (`sensor_frame`/`command_frame` `seq >= 1`
strictly increasing, `observation_frame` `>= 1` when published on the
observation plane, `0` only in pull/RPC replies; the pre-0.6 "`seq == 0` always
accepted" escape hatch is removed). Acceptance-rule changes are exactly what the
version string exists to gate — hence the minor bump, per the pre-1.0 caveat
below.

**Additive evolution is NON-breaking (since v0.4).** Adding an *optional* field or a
new message type does **not** bump the minor — protobuf/serde ignore unknown fields,
so a peer on an older minor keeps working. The minor bumps **only** for genuinely
incompatible changes (removing/renaming a field, changing a type, removing an enum
value, changing semantics). This corrects the earlier over-aggressive rule that forced
fleet re-pins (`v0.2.5/6/7/8`, and `0.2→0.3` for the merely-additive `contract_hash`
field). Two layers do the work: **`ncp_version`** is the hard *compatibility* gate
(`check_version`, exact `(major, minor)` pre-1.0), and **`CONTRACT_HASH`** is an
*advisory* identity signal (see §"Contract hash") that flags "same wire version, newer
contract revision" without breaking anyone.

**Pre-1.0 caveat:** while `0.x`, an *incompatible* minor bump is breaking and the
version guard fails closed on a minor difference (`check_version`). Pin an exact
version (`tag = "v0.6.0"`). `0.x` is explicitly unstable.

The current wire is **`0.6`** (`ncp_version = "0.6"`). `0.6` is the
**enforcement cut**: mandatory `ncp_version` on every message, mandatory
stamped `seq` on the closed-loop frames, normative observation-plane seq
stamping, and the removal of the `seq == 0` escape hatch — a semantic break
with an unchanged serialization (same `CONTRACT_HASH`). Earlier wires: `0.5`
was the **stable-wire cut** (the three bare proto `string mode` fields were
promoted to enums — a real `string`→enum wire change that recomputed
`CONTRACT_HASH` to `24e8e6e31e1dec8a`); `0.4` was the **decoupling +
robustness** release (the proto `package` was renamed `engram.ncp.v0 → ncp.v0`
— naming-only, hash-neutral; the contract handshake became advisory; the
additive-is-non-breaking policy above was adopted); `0.3` added the
`contract_hash` handshake field; `0.2` the neuron-family wire (#10) and bulk
column codec (#6).

<picture>
  <source media="(prefers-color-scheme: dark)"  srcset="docs/diagrams/versioning-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="docs/diagrams/versioning-light.svg">
  <img alt="NCP version-compatibility handshake. The wire contract breaks from 0.5 to 0.6 (an acceptance-rule change: mandatory ncp_version and stamped seq; the serialization is unchanged, so the contract hash stays 24e8e6e31e1dec8a). This feeds a hard compatibility gate, check_version, which requires an exact major.minor match and fails closed. A peer on 0.5 does not equal 0.6 and is rejected fail-closed with an error and no coercion; a peer on 0.6 matches exactly and the session opens (the highlighted green outcome). Separately, off the success path, a contract_hash difference is advisory only — logged, not rejected." src="docs/diagrams/versioning-light.svg" width="820">
</picture>

## Enforcement: `buf breaking`

Breaking changes are caught mechanically, language-agnostically, by Buf's tiered
rules (configured in `buf.yaml`):

- **`WIRE` / `WIRE_JSON`** — binary and JSON wire compatibility (the contract).
- **`FILE` / `PACKAGE`** — source/codegen-level stability.

CI runs `buf lint`; `buf breaking` gates the wire against the first tag of the
current wire (`v0.6.0`, the wire-`0.6` baseline — see `.github/workflows/ci.yml`).
A change that trips `WIRE`/`WIRE_JSON` **must** bump MAJOR (or MINOR while `0.x`).
(Wire 0.6 changed no proto structure, so `buf breaking` is byte-quiet across the
0.5→0.6 cut — the break is in the acceptance rules, gated by `ncp_version`.)

## Per-session version + contract handshake

At session setup the client sends its `ncp_version` **and** `contract_hash` in
`OpenSession`; the reference server (engram's `SessionService.handle`) and the Zenoh
client (`ncp-zenoh::ZenohNcpClient::open`) call `negotiate(peer_version, peer_hash)`.
The two checks are **separated by concern** (since v0.4):

1. **`ncp_version` is the hard *compatibility* gate.** An incompatible version
   (`check_version` — exact `(major, minor)` pre-1.0) is rejected, never coerced: the
   server replies `SessionOpened{ ok: false, error: "…" }` and the session does not
   open. "Can we speak the same wire at all?"
2. **`contract_hash` is an *advisory* identity signal.** `negotiate` returns a
   `ContractStatus` (`Match` / `NotAdvertised` / `Mismatch`); a `Mismatch` is **logged,
   not rejected**. "Are we on the exact same contract revision?" A mismatch within a
   compatible version is expected (e.g. one peer added an optional field — non-breaking
   per the additive policy) and must not break the flow. A `verify_contract` strict
   opt-in remains for deployments that *mandate* an exact revision (safety-certified
   configs).

Separating the two means additive evolution and naming-only proto changes never break
any version-compatible commander↔plant flow, while drift is still surfaced for
operators.
## Where the version gate runs — enforced end to end since wire 0.6

The gate runs at **both** layers since wire 0.6:

1. **Session establishment** — `check_version` inside `negotiate` at
   `OpenSession` (the reference server's `SessionService.handle`; the Zenoh
   client `ncp-zenoh::ZenohNcpClient::open`), plus per-reply validation in the
   typed RPC client.
2. **Per frame on the data plane** — `required_fields()` lists `ncp_version` for
   **every** `kind` (injected into every JSON Schema's `required` array with a
   `const` pin), `validate()` rejects an absent OR incompatible version, an
   absent version deserializes to a detectable `""` (never fabricated as the
   receiver's own), and the hot-path typed ingress
   (`ncp_core::decode_validated` / `WireFrame::validate_wire`, used by the Zenoh
   subscriber and publish gates) drops a version-less/incompatible/unstamped
   frame with a diagnostic. `diagnose_version` now also flags the absent-version
   case so a receiver can log *why* a frame was dropped.

The per-frame cost is one string comparison on an already-deserialized frame
(no extra parse — `validate_wire` works on the typed value), so the original
microseconds-budget argument no longer trades safety for speed. A transport that
delivers frames from a mismatched peer straight onto the data plane (bypassing
the `OpenSession` handshake) is now rejected at ingress rather than silently
accepted. Transport-level peer authentication (mTLS) remains the *adversarial*
integrity layer — the version gate is compatibility, not authentication (see
`SECURITY.md`).

## Contract hash (the wire-identity digest)

`ncp_version` says *which version* a peer speaks; `CONTRACT_HASH` says *which exact
contract* — it is the FNV-1a digest of the **wire-semantically canonicalized**
`proto/ncp.proto`. `canonical_proto` reduces the proto to its wire-relevant content:
it strips `//` and `/* */` comments (respecting string literals), normalizes
whitespace, **and drops the non-wire declaration lines** `syntax` / `package` /
`import` / top-level `option`. So a purely *naming* change — e.g. the v0.4 rename
`package engram.ncp.v0 → ncp.v0` that decoupled the protocol's identity from a
consumer — leaves the wire identical and is **hash-neutral**; only a real wire change
(add/remove/retype a field, change an enum value) flips the hash. It is **not** a
cryptographic MAC: adversarial integrity is the transport's job (mTLS); the hash
*detects* accidental drift, and per the handshake above a mismatch is advisory.

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
