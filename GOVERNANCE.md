# NCP governance

NCP aims to be a reusable, project-agnostic protocol with independently
interoperable implementations. Repository HEAD is an unreleased, release-blocked
`1.0.0-rc.1` candidate; it is not yet an adopted or neutral standard.

## Current stewardship

The canonical repository is `sepahead/NCP`, maintained by Sepehr Mahmoudian. Changes
land through review and must follow [`CONTRIBUTING.md`](CONTRIBUTING.md). The
maintainer may reject a change that weakens interoperability, security, boundedness,
scientific honesty, plant authority, or evidence quality even when it is convenient
for one consumer.

No consumer owns protocol semantics. Engram, crebain, producer, galadriel, haldir,
and prisoma migrate through the shared contract and conformance process; core does
not add project-specific fields/classes/topics.

## Normative authority

[`contract/manifest.v1.json`](contract/manifest.v1.json) lists and digests the exact
normative sources and precedence. Implementations and examples are informative. A
conflict is a release-blocking defect and cannot be settled by selecting the more
permissive artifact.

Stable 1.x evolution is additive. Breaking changes require a new major and migration
plan. Security, limits, capability status, and plant/scientific boundaries are part
of the contract, not optional deployment commentary.

## Mechanical accountability

Governance depends on reproducible gates rather than trust:

- proto/schema/generated/canonical-vector parity and a frozen JSON baseline;
- exact mandatory corpus coverage in every applicable implementation;
- complete normative and corpus digests;
- installed-package introspection and reproducible artifacts;
- live secure/fault/fuzz/performance campaigns;
- independent clean-room reproduction and downstream acceptance.

Skipped, missing, unsigned, stale, or source-tree-only evidence does not pass a
release gate. External-model review cannot vote or certify a gate.

## Release authority

An immutable release tag and package publication require every required
`pre_release_gates` entry in
[`contract/release-gates.v1.json`](contract/release-gates.v1.json) to pass against
one artifact set, including all six consumers. A candidate version bump or local
test run is insufficient. Release artifacts, reports, signatures, SBOM/provenance,
compatibility matrix, support term, and emergency revocation procedure must be
publicly reviewable. The registry's `post_release_validations` run against the
published artifacts and cannot be prerequisites for their own initial publication.

The candidate currently fails that threshold; external gates are **NOT RUN**. See
[`RELEASE_READINESS.md`](RELEASE_READINESS.md).

## Path to broader governance

After at least two independent implementations and multiple independent adopters
demonstrate sustained interoperability, the project should formalize a technical
steering process, conflict-of-interest rules, security response team, release
signers, and a neutral organizational home. Neutrality is earned by participation
and reproducible evidence, not declared by naming this repository a standard.
