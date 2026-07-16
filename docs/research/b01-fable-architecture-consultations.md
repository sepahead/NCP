# B01 Fable 5 architecture consultations

These consultations are non-normative design challenge input for task `B01`.
They are not human or independent review, proof, interoperability evidence,
security approval, plant/safety evidence, scientific validation, or release
authorization. No API key, credential, private key, or raw secret-bearing request
is retained here.

## Consultation A — ecosystem authority composition

- Exact returned model: `claude-fable-5`
- Stop reason: `end_turn`
- Raw response SHA-256:
  `3b570327b7f34941bf72ddb747741a16cdfd38dd7507d4dc87480c30d1f26a1`
- Input tokens: 1,288
- Output tokens: 6,185
- Reported thinking tokens: 2,739
- Evidence class: advice only

The request asked five narrow questions about direct-versus-gated command,
Galadriel deny-only composition, simulation/plant separation, dependency
direction, and the strongest remaining composed counterexample.

### Advice retained

- Crebain must be the single serializer of the current plant commander term.
- Direct Engram and Haldir-gated modes need an explicit body-coordinated
  revoke/quiesce/regrant transition rather than a configuration toggle.
- Per-message deny-only semantics are insufficient if expiry, disable, restart,
  replay, base-policy change, or override can widen effective permission.
- Haldir must construct a new NCP command under its own principal and body-issued
  lease; it cannot forward or re-sign Engram command bytes as transferred
  identity.
- Simulation responder and plant commander credentials, routes, state, and
  resources must remain disjoint.
- Bounded composition models must cover delay, partition, crash, restart, replay,
  and handover.

### Advice revised or rejected

- A proposed new mandatory `world=SIM|PLANT` field on every record was not
  adopted. ADR-001 instead uses disjoint session kinds and authority domains,
  preserves mandatory `SimProvenance` for simulation output, and treats
  deployment/resource isolation separately. A new core field would require
  accepted ADRs and a deliberate rebaseline, not model advice.
- “Never zero commanding capability” was not adopted as a universal property.
  Some plant profiles require active HOLD behavior, while others cannot define a
  universal zero-safe action. The ratified profile must name the bounded
  quiescence/fail posture without implying physical certification.

## Consultation B — staging and fencing precision

- Exact returned model: `claude-fable-5`
- Stop reason: `end_turn`
- Response SHA-256:
  `dea58c92c924263285386492903d806925401c130d880eb6b8e1799cd37e156f`
- Input tokens: 872
- Output tokens: 6,871
- Reported thinking tokens: 3,384
- Evidence class: advice only

The request asked five narrow questions about proposed-registry staging,
Crebain-owned fencing, Galadriel lifecycle widening, simulation provenance, and
the strongest cross-component counterexample.

### Advice retained

- Proposed decisions must remain outside the current `contract/*.v1.json`
  normative glob. Promotion must verify exact accepted ADR hashes and occur in a
  single reviewed rebaseline slice.
- A status string inside a normative path is not a safe staging boundary.
- Galadriel/Haldir permission widening through expiry, disable, restart,
  base-policy edit, or retraction must be an explicit authenticated,
  monotonically versioned Haldir policy transition with an audit record.
- `SimProvenance` is non-authoritative for plant admission. Plant authority
  remains credential-, session-, route-, and Crebain-lease-bound.
- The composed model must jointly cover stale commands, commander exclusivity,
  deny-state recovery, and body restart.

### Advice revised or rejected

- The response proposed treating `SessionRef.generation` as a crash-monotonic
  ordered value and comparing
  `(session_generation, lease_term, stream_epoch, sequence)`
  lexicographically. This conflicts with the frozen NCP meaning:
  `SessionRef.generation` and `StreamPosition.epoch` are opaque canonical UUIDv4
  equality fences. ADR-005/006 instead require exact equality/currentness for
  generation, lease ID/holder, and stream epoch, plus separate monotonic rules
  for lease term and sequence.
- The response described a new stream as “epoch 0, sequence 0.” Native NCP
  epochs are UUIDv4 values and sequence begins at `1`; the drafts preserve that.
- The response placed a stale plant command through Prisoma into pid-rs before
  actuation. That topology is prohibited. Prisoma is read-only/offline, pid-rs
  is a protocol-neutral leaf, and neither is in the command path. The retained
  counterexample instead tests their required non-participation while focusing
  on Crebain, the old/new commander, Haldir recovery, and Galadriel deny state.
- Permanent deny persistence was narrowed to the configured non-widening Haldir
  posture. Deployments may choose record-only or deny-new-missions absence
  policy, but restart or configuration change cannot silently turn an applied
  restriction into a new ALLOW.

## Failed consultation attempts

These returned no usable advice and are not counted as consultations:

- an invalid request using an unsupported thinking configuration returned HTTP
  400, response SHA-256
  `aa30fef55a980ef5d8780e1286a8f0cac4cda8c4b72c0668735d90ef1a664952`;
- exact `claude-fable-5` with maximum effort exhausted 8,000 output tokens as
  thinking and returned no text, response SHA-256
  `60420e3cd8261ba04d209e30343d5531b1a00d70b5f9aed889c2313189e47639`;
- exact `claude-fable-5` with maximum effort exhausted 16,000 output tokens as
  thinking and returned no text, response SHA-256
  `36d8976037805bf71db7611ef06ac861c129d36181d4a1415b6f7677f7b7ee37`.

The usable retry kept the exact Fable 5 model but allowed default adaptive
allocation, producing Consultation B.

## Resulting draft changes

The consultations influenced:

- [ADR-001](../adr/0001-separate-simulation-and-plant-sessions.md);
- [ADR-006](../adr/0006-body-issued-authority-and-time.md);
- [ADR-008](../adr/0008-extension-namespace-and-galadriel-separation.md);
- [ADR-011](../adr/0011-ecosystem-topology-and-handover.md); and
- the generated B01 threat/requirement traceability controls.

All remain `PROPOSED`. A qualifying reviewer must assess the actual ADR bytes and
their exact registry hashes rather than relying on this summary.
