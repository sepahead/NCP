# Signed-forwarding prototype section review

> **Decision:** local prototype-B implementation-diversity section pass; proceed
> only to the terminal B04 exact-commit whole-repository gate and receipt. This
> is not yet a B04 terminal pass and is not evidence for production security,
> independent human review, interoperability, authorization, plant action,
> release, or NCP 1.0 publication.

Review date: 2026-07-16.

## What the executable result changed

The prose draft conflated outer replay state with NCP semantic state. Executable
examples showed that current NCP session generations and stream epochs are
canonical UUIDv4s. Operation requests carry an operation UUID, request digest,
and non-negative expected state version; there is no positive integer operation
generation to bind.

The prototype therefore separates:

- an always-present signed forwarding epoch/sequence for outer replay;
- a conditional exact payload stream binding for `command_frame`; and
- a conditional exact operation binding for `step_request`.

The other material correction came from the exact-model replay challenge. An
owner-authorized empty replacement store would have accepted old envelopes below
the lost high water if recovery epoch existed only in store metadata. Recovery
epoch is now a required signed envelope field and replay-key component. Recovery
invalidates all old envelopes and forces senders to reissue under the new epoch.

## Assumptions rejected

- **A valid signature transfers transport identity.** Rejected. The simulated
  carrier remains a distinct forwarding-only principal/entity pair, must differ
  from the signer on both identity axes, and is retained in the result context.
- **A valid signature grants NCP authority.** Rejected. The result contains no
  lease, operation outcome, idempotency result, lifecycle transition, plant
  admission, ESTOP, or safe-action fact.
- **Generic JWS compatibility is desirable here.** Rejected. Compact/general
  serialization, unprotected members, remote or embedded keys, alternate
  algorithms, unknown critical members, and profile negotiation all reject.
- **Decode/re-encode is harmless.** Rejected. Signature verification uses the
  exact received encoded protected and payload strings.
- **The payload stream can be reused as envelope replay for every message.**
  Rejected. Operation requests are not streamed messages; outer forwarding state
  is explicit and independent.
- **A higher key epoch is automatically trusted.** Rejected. The current exact
  manifest selects the key and grants. Overlap is explicit; removal has no
  fallback.
- **SQLite integrity proves current state.** Rejected. It detects structural
  corruption, not a copied-back valid snapshot.
- **Familiar SQLite object names prove the replay schema.** Rejected. Exact
  normalized `sqlite_schema.sql` for both tables and the capacity trigger is
  checked before use.
- **A signed initialization may replace an existing path.** Rejected.
  Initialization requires absence; replacement requires a recovery authorization
  that advances both recovery epoch and store identity.
- **Recovery can safely replace a database used by another local process.**
  Rejected. Every conforming open holds a shared advisory lock and recovery
  requires an exclusive non-blocking lock.
- **Commit-before-handoff is exactly-once.** Rejected. It is at-most-once with an
  explicit crash-loss window after commit and before consumer execution.
- **Owner-signed recovery preserves old high water.** Rejected. It deliberately
  resets state, so the signed recovery epoch must fence every prior envelope.
- **A simulated carrier context proves A-over-B composition.** Rejected. A live
  authenticated prototype-A context is not wired into this reference harness.
- **A successful native Ed25519 call is the strict profile.** Rejected. On Node
  26.3.0/OpenSSL 3.6.2, an all-zero public key and signature verify for at least
  the ASCII message `protected.payload`. The independent wrapper performs
  canonical point/scalar and reviewed small-order checks before the native call.
- **Two implementations written here are independent review.** Rejected. The
  native Node parser/crypto stack provides implementation diversity only. It
  supplies neither a second human identity nor installed-peer interoperability.

## Executed falsification

The deterministic runner executes eight hostile Python verifier self-tests,
fifteen Python forwarding/replay tests, three focused Python boundary tests,
twenty-one native Node tests (including six boundary-verifier mutants), and a
thirty-one-case process-isolated differential corpus:

- positive `command_frame` and `step_request` acceptance;
- strict outer/protected member sets, duplicate names, UTF-8/BOM/surrogate,
  base64url, integer, compact/general/unprotected and remote-key negatives;
- fixed Ed25519 selection, wrong key, changed protected/payload bytes,
  RFC 8032 known-answer verification, noncanonical scalar/point, seven reviewed
  small-order representatives on both sign encodings, native zero-key
  counterexample, and signature length checks;
- manifest digest, unknown member, wildcard, duplicate identity/epoch, exact
  grants, key overlap, epoch match and removed-key negatives;
- wrong carrier role/profile/route, signer-equals-carrier,
  carrier-entity-equals-signer, wrong audience/digest, stale clock interval, payload
  session/stream/operation mismatch, and A-direct profile rejection;
- equal/lower replay, independent forwarding epochs, restart, two-process
  duplicate race, 128-scope capacity, missing/corrupt/mismatched/oversize or
  insecure database state, oversize sidecars, and substituted schema SQL;
- owner signature, expiry, prior-state match, exactly advancing recovery epoch,
  distinct new store identity, initialization overwrite rejection,
  active-process recovery rejection, bounded authorization bytes, old-envelope
  rejection after recovery, and new-envelope acceptance; and
- subprocess death before commit, which permits retry, versus death after commit,
  which loses consumer handoff and rejects retry; and
- Python/Node equality for accepted authentication projections and exact
  rejection categories across both message profiles, manifest rotation/removal,
  exact/adjacent numeric and base64url edges, parser ambiguity, key/algorithm
  mutation, carrier/signer confusion, routing/time/profile mismatch, and payload
  semantic mismatch.

The machine-local result exercises two accepted messages. Its largest observations
are a 3,479-byte envelope, 1,307-byte protected header, 1,204-byte NCP payload,
494-byte key manifest, and 12,288-byte SQLite database. The values are resource
observations under one runtime, not performance or capacity qualifications.

## Three-lens review

### Protocol, security, and plant

- No proto, stable Rust type, JSON Schema, vector, compact hash, candidate
  baseline, conformance manifest, root workspace, shipping package, or direct
  Zenoh behavior changed.
- Signer, carrier, receiver, route, plane, class, profile, key manifest, key
  epoch, recovery epoch, session, payload context and payload digest are exact.
- The immutable handoff retains both signer/carrier identities, the carrier
  role/profile, and the exact stable-core and security-state digests.
- Unknown, missing, stale, ambiguous, replayed, downgraded, mismatched, or
  implementation-divergent input cannot construct the verified result.
- The result is authentication evidence only. Crebain/body-local final actuator
  authority and every ordinary NCP lease, idempotency, safety, lifecycle and
  operation check remain unchanged.

Result: bounded local profile, replay, and implementation-diversity invariants
pass without identity or authority transfer.

### Consumer and runtime

- The Python and Node implementations are isolated and unpublished; no consumer
  depends on them.
- PyNaCl 1.6.2, cffi 2.1.0, pycparser 3.0 and Ruff 0.15.21 are exact in `uv.lock`
  with registry artifact SHA-256 values.
- Node 26.3.0, OpenSSL 3.6.2, TypeScript 5.9.2, `@types/node` 26.1.1, and
  `undici-types` 8.3.0 are pinned or checked, with exact npm registry integrity
  values. A local npm audit reported no known vulnerabilities; like the Python
  audit, this is a time-varying observation rather than frozen evidence.
- A local `pip-audit` run with the fully pinned exported graph, no dependency
  resolution, and pip disabled reported no known vulnerabilities. This is a
  time-varying local observation, not a frozen supply-chain gate.
- The 128-scope bound intentionally fails closed and requires owner-authorized
  recovery rather than silent eviction. That is operationally expensive.
- Cooperative same-host opens share an advisory lock and SQLite serialization;
  recovery requires exclusive quiescence. Non-cooperating same-UID processes,
  shared filesystems, replicated state and multi-instance ownership remain
  outside the result.

Result: both verification stacks are executable and bounded, while replay
diversity, deployment topology, and live composition remain open.

### Operations, science, and evidence

- Runtime private signing and recovery keys exist only in test process memory.
  No private key, secret seed, credential path, or local absolute path is retained.
- The committed 241,671-byte differential corpus retains public keys and signed
  requests only. Regeneration creates new runtime keys and is a reviewed corpus
  replacement rather than a deterministic build step.
- Six earlier completed exact-model `claude-fable-5` consultations remain
  non-normative; the sixth replay/recovery challenge produced the adopted signed
  recovery epoch. A seventh exact `claude-fable-5`/`end_turn` challenge, raw SSE
  SHA-256
  `a5c58f4ad92076b502fd0c7c018e98058c20abc83432037a1bf6a15e74925797`,
  found no blocker to the narrow local pass and prompted the focused boundary,
  full sign-bit, and same-sequence/different-payload replay negatives. It counts
  as neither reviewer, parser, proof, nor gate.
- Focused exact/above JSON byte, depth, node, member, string, safe-integer and
  base64url bounds execute in both suites. Full-sized profile-limit sweeps,
  combinatorial boundary fuzz, kill-during-COMMIT, disk-full, WAL-aware
  backup/restore, filesystem rollback, trusted-time operations, owner-key
  custody, multi-host behavior, duration fuzz, soak, performance, independent
  interoperability and external gates are **NOT RUN**.
- No simulation, posterior, calibration, paper-reproduction, safety,
  certification, scale, performance, release or publication claim is derived.

Result: local evidence is proportional to two prototype B verification stacks
and preserves every unproved operational boundary.

## Next permitted boundary

The next dependency-ready work is the terminal B04 exact-commit local gate:
retain the coherent prototype commit remotely, run the complete
`scripts/check.sh` preflight from that exact source, bind the outputs and hashes
in a B04 receipt, and update the generated coordination views through their JSON
source. Any failure keeps B04 `IN_PROGRESS`.

Until that terminal receipt passes, B01 ADR ratification, stable implementation,
consumer repository changes, shipping packages and all external/release gates
remain blocked.
