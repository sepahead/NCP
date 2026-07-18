# NCP 1.0 architecture decision review

This directory contains the proposed architecture decisions for task `B01`.
Every decision remains **PROPOSED**. None of these documents changes the current
unreleased, release-blocked `1.0.0-rc.1` normative contract, compact proto hash,
runtime authority, release status, or external evidence state.

The current candidate remains wire `1.0` with compact proto contract hash
`163acc57d8a62b66`. The immutable `v0.8.0` release remains a different wire and
is not edited or silently translated by these records.

## Staging rule

The generated draft registry is
[`decision-registry.proposed.v1.json`](decision-registry.proposed.v1.json). Its
source is
[`decision-registry.source.v1.json`](decision-registry.source.v1.json). Both live
outside `contract/` deliberately.

The current contract-manifest generator includes every
`contract/*.v1.json` file except its own output in the complete normative digest.
Therefore a proposed decision registry in `contract/` would silently become
normative. That is forbidden.

Promotion to `contract/decision-registry.v1.json` is allowed only in the later
ratification/rebaseline slice after all of these conditions hold:

1. every ADR is `ACCEPTED`;
2. every required owner and independent reviewer has signed the same exact
   content digest;
3. no normative open question remains;
4. the proposed wire examples parse in the two independent prototype parsers;
5. the required preliminary models and resource probes have no unresolved
   counterexample under their declared bounds;
6. the owner explicitly authorizes the deliberate pre-release rebaseline; and
7. one mechanical promotion verifies the hashes, writes the accepted registry,
   regenerates the complete contract identity, and rejects any non-accepted
   entry.

A status string inside `contract/` is not a staging boundary. Path exclusion plus
content-hash verification is the boundary.

## Decision set

| ADR | Proposed decision | Required reviewer roles before acceptance |
|---|---|---|
| [ADR-001](0001-separate-simulation-and-plant-sessions.md) | Separate simulation-service and plant-control session contracts. | NCP maintainer, Engram owner, Crebain body owner, independent protocol reviewer |
| [ADR-002](0002-contract-identity-and-release-authorization.md) | Separate wire, stable-core, release, corpus, extension, and authorization identities. | Protocol reviewer, release/supply-chain reviewer |
| [ADR-003](0003-authenticated-production-ingress.md) | Use an authenticated terminating ingress, with signed forwarding only as an explicit two-axis forwarding profile. | Two independent security/cryptography reviewers, transport implementer |
| [ADR-004](0004-observer-attach-grants-and-revocation.md) | Add authenticated bounded observer attach, descriptors, grants, privacy, and revocation. | Prisoma owner, Galadriel owner, security reviewer |
| [ADR-005](0005-declared-stream-lifecycle.md) | Declare, retire, and redeclare every stream; exhaustion never rotates implicitly. | Distributed-systems reviewer, all stream consumer owners |
| [ADR-006](0006-body-issued-authority-and-time.md) | Make plant authority body-issued, term-fenced, bounded, and monotonic-time enforced. | Safety reviewer, distributed-systems reviewer, Haldir owner, Crebain owner |
| [ADR-007](0007-command-disposition-journal.md) | Add body-issued bounded command dispositions, durable query, and explicit ambiguity. | Plant/safety reviewer, Haldir owner, Crebain owner |
| [ADR-008](0008-extension-namespace-and-galadriel-separation.md) | Separate stable NCP routes from registered Galadriel extension routes and credentials. | Protocol reviewer, Galadriel owner, Haldir owner, Crebain owner |
| [ADR-009](0009-security-state-rotation-and-revocation.md) | Bind semantic security state, key rotation, revocation, and reattachment explicitly. | Security reviewer, operations reviewer, supply-chain reviewer |
| [ADR-010](0010-plane-qos-retention-and-overload.md) | Specify finite per-plane QoS, retention, priority, overload, and observer isolation. | Real-time/performance reviewer, consumer reviewers |
| [ADR-011](0011-ecosystem-topology-and-handover.md) | Ratify standalone-first dependency direction, exclusive commander modes, body-coordinated handover, deny-only assessment, and pid-rs neutrality. | Every named consumer owner, pid-rs owner, independent security/distributed-systems reviewer, Crebain plant/safety reviewer |

## Common state and digest rules

The registry generator computes SHA-256 over the exact UTF-8 bytes of each ADR.
Any edit changes the digest and invalidates every earlier review of that ADR.
Review records must name:

- the reviewer identity and role;
- whether the reviewer is independent of the implementation owner;
- the exact ADR SHA-256;
- `ACCEPT`, `REJECT`, or `ACCEPT_WITH_CONDITIONS`;
- all conditions and their resolution evidence; and
- the review timestamp and evidence path.

No model-generated advice counts as a reviewer, approval, proof, or evidence.
Exact Fable 5 consultations used to challenge the drafts are recorded only as
non-normative design inputs in
[`../research/b01-fable-architecture-consultations.md`](../research/b01-fable-architecture-consultations.md):

- five usable exact-model consultations are recorded, ending with the cutover
  and review-packet challenge response SHA-256
  `080ad93775d6dec018a08efeadd49b0d57e6162a90f4bc7cf9a8b43199246d32`;
- five other exact-model or configuration attempts failed or returned incomplete
  text and are recorded as failed consultations, not advice.

The drafts accept useful counterexamples but reject suggestions that conflict
with current NCP semantics. In particular, `SessionRef.generation` and
`StreamPosition.epoch` are opaque UUIDv4 equality fences, never ordered counters,
and Prisoma is never part of the command path.

## Review lenses

Every ADR contains explicit decisions for all ten blueprint lenses:

1. protocol semantics;
2. security and trust;
3. safety and plant boundary;
4. distributed lifecycle;
5. resources and real time;
6. interoperability and migration;
7. science and statistics;
8. implementation and operations;
9. verification and evidence; and
10. lifecycle and governance.

The three mandatory review perspectives are also preserved:

- protocol, security, and plant correctness;
- consumer and runtime usability; and
- operations, science, and evidence honesty.

## Verify

Run:

```bash
python3 scripts/generate_decision_registry.py --self-test --check
python3 scripts/check_adr_examples.py --self-test
python3 scripts/check_markdown_links.py
python3 scripts/generate_audit_artifacts.py --self-test
python3 scripts/check_audit_artifacts.py --self-test
```

These checks establish only deterministic local draft consistency. They cannot
accept an ADR, satisfy B01's independent evidence floor, authorize a candidate
rebaseline, or release NCP 1.0.
