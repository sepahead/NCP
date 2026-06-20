# NCP Governance

NCP aims to be a **reusable, language-agnostic standard** (cf. MCP, OMG DDS,
MUSIC) — a wire contract many independent peers implement, not one project's
internal API. A standard needs a governance model and a path to a neutral home;
this document is that model. It is deliberately lightweight while the protocol is
pre-1.0.

## Current model (pre-1.0): maintainer stewardship

- The canonical repository is **[sepahead/NCP](https://github.com/sepahead/NCP)**.
  The maintainer is the steward of the wire contract and the final decision-maker
  on changes during `0.x`.
- The **normative artifact** is `proto/ncp.proto` (the wire IDL). Everything else
  — JSON Schemas, the Rust/Python/TS/C bindings, prose docs — is generated from or
  conformance-checked against it. A change is "to the standard" only if it changes
  the normative artifact or the [versioning policy](VERSIONING.md).
- Changes land by pull request. Substantive wire changes should reference an issue
  describing the motivation and the affected peers.

## How interoperability is enforced (not by trust)

Governance of a wire protocol is mostly mechanical. Three CI gates make
divergence a build failure rather than a disagreement:

1. **Proto ↔ JSON-Schema parity** (`scripts/check_proto_schema_parity.py`) — the
   IDL and the JSON projection cannot drift in field-set or enum wire-strings.
2. **Conformance corpus** (`conformance/vectors/` + `scripts/check_conformance_vectors.py`)
   — golden JSON *and* binary message instances every peer, in any language, runs
   to prove it reads/writes the wire identically. New message types and codecs
   (e.g. the bulk column block, #6) add a vector here.
3. **`buf breaking`** (`buf.yaml`) — `WIRE`/`WIRE_JSON` compatibility is checked
   against the last released tag, so an accidental breaking change is caught
   language-agnostically before release.

A peer is "NCP-conformant" if it passes the corpus; that is the membership test,
independent of who maintains it.

## Decision process

- **Additive changes** (new optional field, enum value, message, codec) — pre-1.0
  these are a MINOR bump (treated as breaking by the version guard; see
  [VERSIONING.md](VERSIONING.md)). They land by PR with a conformance vector.
- **Breaking changes** — a MAJOR bump (or MINOR while `0.x`); must be justified in
  an issue, pass `buf breaking` review, and follow the deprecation window in
  VERSIONING.md.
- **Disputes** — during `0.x`, resolved by the maintainer; the bias is toward the
  smallest change that keeps existing peers interoperating.

## Path to a neutral home

The intent is for NCP to outgrow single-maintainer stewardship as adoption grows.
The migration path, in order of increasing neutrality:

1. **Now** — maintainer-stewarded in `sepahead/NCP`, with the mechanical interop
   gates above doing the heavy lifting.
2. **Multi-implementer** — once ≥2 independent peers ship against the corpus, add
   named maintainers from those implementations and require their review for wire
   changes.
3. **Neutral org** — move the spec + conformance corpus to a vendor-neutral
   organization (a dedicated GitHub org, or a foundation/SDO such as the OMG-style
   model DDS uses) with a published change-control process. The conformance corpus
   and `buf breaking` baseline travel with the spec, so the interop contract is
   unaffected by the move.

Proposals to advance this path are welcome as issues.

## Code of Conduct

Participation is governed by the [Contributor Covenant](CODE_OF_CONDUCT.md).
