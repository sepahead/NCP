# Zenoh metadata-probe section review

> **Decision:** local section pass; proceed only to the quarantined terminating
> TLS-ingress prototype. This is not a pass for `production-secure`, a release
> gate, interoperability, authorization, plant action, or NCP 1.0 publication.

Review date: 2026-07-16. Reviewed input: exact crates.io `zenoh 1.9.0`, checksum
`85e22d7002ac149ef17fe400bb40a267ebbba40a83413bab03da7762256fa94e`, upstream
commit `81c6c933b6e41d72a05f04c4442ef57717ddc72b`.

## Self-explanation

I needed to answer one narrow question before designing authenticated ingress:
can the NCP application callback bind an incoming direct-Zenoh message to the
principal that Zenoh's transport actually authenticated?

The answer for the reviewed Zenoh input is **no**. Two evidence classes support
that answer without being confused:

1. The source matrix binds the reviewed API conclusion to the exact registry
   checksum, upstream commit, file hashes, and relevant source fragments. Stable
   samples expose content metadata but no verified certificate principal. The
   unstable `SourceInfo` is a Zenoh entity ID and sequence supplied through sender
   builders. Query reply IDs and session peer IDs are Zenoh identifiers, not
   per-delivery verified certificate attribution. Liveliness construction supplies
   no source or replier information.
2. The live probe supplies counterexamples. A publisher labels its sample with
   the receiver's entity ID and an arbitrary sequence, and the receiver observes
   both. Query and reply senders do the equivalent. Omitting `SourceInfo` leaves
   it absent. Liveliness put, query, and delete paths expose no source, and the
   liveliness reply exposes no replier ID in the tested topology.

Therefore `SourceInfo`, reply IDs, session peer lists, payload identity, key
expressions, or router ACL outcomes cannot be promoted into NCP's authenticated
payload-principal binding. Direct Zenoh remains fail-closed for
`production-secure`. This conclusion does not say Zenoh TLS or ACL is defective;
it says the reviewed application boundary does not expose the verified fact NCP
must bind.

## Corrections made during review

The first working result used two observation names that exceeded the live
evidence. A hard-coded field said no certificate principal was observed even
though the probe intentionally uses no TLS, and another field described the
meaning of `replier_id` when the run only measured its presence. Both were
removed or renamed. Live observations now report only measured behavior; API
meaning stays in the source-bound matrix and claim boundary.

The source verifier was also tightened to reject path traversal and accidental
Zenoh transport-compression enablement. Seven hostile verifier tests now reject
compression enablement, parent-path escape, a wrong source hash, optimistic gate
promotion, and incomplete result data while accepting the exact reviewed cases.

## Independent assumption challenge

- **A live counterexample proves API absence.** Rejected. Runtime behavior cannot
  prove that no other field or configuration exists. API absence is a
  pinned-source conclusion; the live run proves sender control and observed
  omissions only.
- **Sender control makes every Zenoh deployment unauthenticated.** Rejected. TLS
  and router ACL can authenticate and filter inside Zenoh. Those controls remain
  defense in depth; the missing fact is callback-visible, per-delivery principal
  binding required by NCP.
- **A Zenoh entity ID is a certificate identity.** Rejected. The reviewed types
  and documentation define a Zenoh identifier, not a certificate fingerprint or
  verified public-key identity. No equivalence is inferred.
- **One optional reply ID is always present.** Rejected. Presence depends on the
  path and topology. The result reports presence only for this exact run;
  liveliness reply absence is tested separately.
- **One-process loopback peers prove interoperability.** Rejected. Both peers use
  the same Rust implementation, process, dependency graph, and host. This is an
  API-boundary test, not an independent-peer gate.
- **Source hashes make the review formally complete.** Rejected. Hashes preserve
  reviewed bytes but cannot prove the human conclusion or cover future versions,
  plugins, or undocumented internals. The conclusion is exact-version and bounded.
- **Deterministic expected JSON makes the runtime evidence independent.**
  Rejected. The probe and verifier share one repository and reviewer; correlated
  edits could preserve a false pass. Exact comparison prevents drift but is local
  self-evidence only.
- **The loopback port reservation is race-free.** Rejected. The port is released
  before Zenoh binds it. Another process can win the race and cause a bounded
  failure, not a false security pass.
- **A passing dependency audit is implicit.** Rejected. The exact graph contains
  `lz4_flex 0.10.0`, reported as `RUSTSEC-2026-0041` by the 2026-07-13 local
  advisory database. Affected decompression calls are feature-gated out, and the
  verifier rejects compression enablement, but the quarantined graph must not ship
  and the advisory is not waived.

## Three-lens review

### 1. Protocol, security, and plant boundary

- No normative NCP file, wire type, compact hash, authority rule, or plant profile
  changed.
- Every sender-controlled, missing, unstable, or merely topological identifier
  grants no identity, authority, capability, channel, lifecycle success, or plant
  action.
- The probe runs explicit loopback TCP without TLS and says so in its output. It
  cannot be selected as `production-secure` or weaken that profile's fail-closed
  behavior.
- No ESTOP, actuator command, lease, session epoch, receipt, or safety claim is
  generated. Physical certification remains outside NCP.

Result: the protocol/security conclusion is internally consistent and safer than
accepting unbound transport or payload metadata. The only permitted next step is
to prototype a boundary that can observe and bind a verified principal.

### 2. Consumer and runtime usability

- Existing NCP users receive no new shipping API or behavior from this section;
  compatibility is unchanged.
- The result explains why direct Zenoh cannot satisfy Engram, Crebain, Haldir, or
  any other consumer's production identity requirement merely by copying an
  entity ID into a message.
- A usable production path still requires the separately quarantined terminating
  TLS-ingress prototype, manifest admission, replay handling, bounded parsing,
  and consumer integration. None exists yet.
- The executable probe is isolated from the root workspace and packages, uses
  exact dependencies, applies operation timeouts, and produces a deterministic
  reviewed result.

Result: the probe answers the prerequisite question without imposing a premature
consumer API. It does not yet make NCP production-usable.

### 3. Operations, science, and evidence quality

- `run.sh` checks registry lock identity, upstream source identity, 11 exact file
  hashes and fragments, the disabled compression feature, seven hostile verifier
  cases, Rust formatting, warnings-denied clippy, a live Rust test, and exact JSON
  output.
- The run is reproducible on the recorded local environment but is neither
  independent nor distributed. It does not test TLS, ACL, certificate rotation,
  revocation, malformed network frames, duration fuzzing, soak, or performance.
- No external-model response is used as evidence. No statistical, scientific,
  posterior-calibration, or paper-reproduction claim is made.
- The exact Zenoh dependency graph retains a known advisory in code excluded by
  the reviewed feature graph. This is acceptable only for the local quarantined
  probe and remains a shipping prohibition.

Result: evidence is proportional to the feasibility question, preserves negative
results and limitations, and cannot be mistaken for a release gate.

## Section decision and next boundary

This section passes its bounded local objective. It establishes that the exact
direct-Zenoh application surface cannot provide NCP's required authenticated
principal binding and supplies executable sender-control counterexamples. It
authorizes only the next research activity: implement and try to falsify prototype
A, a terminating TLS 1.3 ingress that owns certificate verification and forwards
the resulting principal fact over a protected local boundary.

Prototype A must fail closed before NCP parsing when the client certificate or
manifest admission fails, keep identity distinct from authority, enforce limits
before semantic allocation, and remain non-shipping until its own self-explanation,
independent challenge, and three-lens review pass.
