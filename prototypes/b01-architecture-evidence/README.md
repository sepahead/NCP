# B01 preliminary architecture evidence

This directory is a quarantined, non-normative counterexample-discovery and
resource-screening prototype for the eleven **PROPOSED** NCP 1.0 architecture
decisions. It does not accept an ADR, create
`contract/decision-registry.v1.json`, change the current wire, start the
canonical `formal/` program, prove implementation refinement, satisfy
independent review, or authorize release.

The current candidate remains unreleased and release-blocked `1.0.0-rc.1`,
wire `1.0`, compact contract hash `163acc57d8a62b66`, and complete normative
digest
`9cae331742d01e9b164e029aa06c644e6b1886176d0816a6ef883af138355c90`.

## Purpose

The B01 ratification gate requires proposed models to have no obvious
counterexample under declared bounds and preliminary resource estimates to fit
declared maxima and local cryptographic screens. The later F01/F02 program still
owns canonical TLA+, large configurations, liveness/fairness, refinement, SMT,
Kani, traces, and independent review.

This prototype therefore asks narrower questions:

1. Can a bounded direct-Engram to gated-Haldir handover, body restart, stream
   restart, lease expiry, hostile fence substitution, and reordered delivery
   admit a stale command?
2. Can Galadriel deny expiry, retraction, disable, restart, record-only input, or
   an unauthorized policy action widen Haldir permission without an
   authenticated monotonically versioned transition?
3. Can a complete v0.8-to-native-1.0 cutover and rollback overlap wire admission,
   activate before quiescence, or revive a pre-cutover incarnation?
4. Do the finite formulas have satisfiable ordinary-success premises, and do
   guard-removal mutations change their registered results?
5. On this machine and fixed corpus, do separate prototype queues remain
   structurally isolated, bounded parsing reject exact over-limit cases, a
   bounded journal preserve required recovery evidence, and real Ed25519
   verification remain inside a declared preliminary screen?

The strongest permitted result is:

> No counterexample was found within the recorded finite models and fixed local
> resource corpus; every registered seeded mutation was detected.

## Bounded state enumerator

[`model_check.py`](model_check.py) exhaustively explores three finite models.

### Composition model

The composition state includes:

- direct Engram or gated Haldir mode;
- body phase `ACTIVE`, transfer HOLD, restart HOLD, or expired-lease HOLD;
- one current body term;
- three deliberately non-chronological generation labels and three stream
  labels, compared only by equality in the correct model;
- zero or one live holder;
- up to two in-flight commands;
- applied/rejected identities; and
- a bounded handover/restart history.

The action set includes legitimate direct and gated issue, body-coordinated
handover, body restart/recovery, stream restart, lease expiry, arbitrary
delivery order, and hostile commands differing in exactly one of generation,
term, stream epoch, holder, or simulation/plant domain.

Required non-vacuity witnesses include:

- a fresh command applies;
- hostile and stale commands arrive and reject;
- two commands are simultaneously in flight;
- a formerly valid delayed command rejects while a currently valid fresh command
  remains pending after a handover or restart fence changed;
- direct-to-gated handover completes;
- restart or expiry recovery completes; and
- each independent fence and simulation-domain rejection is reached.

The model kills mutations that omit or order generation, omit term/epoch/holder,
admit simulation as plant, construct a Haldir command under Engram identity, or
overlap old/new holders.

### Galadriel/Haldir deny model

Permission is represented as:

```text
effective_allow = local_allow AND NOT applied_deny
```

`EXPIRE`, `RETRACT`, and `DISABLE` request removal but retain the applied deny.
Only an authenticated Haldir widening action with a strictly greater policy
revision removes it. Restart preserves the applied deny. `RECORD_ONLY` is the
identity operation. Both unauthenticated tightening and assessor ALLOW attempts
are blocked: monotone denial cannot justify an unauthenticated denial-of-service
path.

Required witnesses prove that authenticated deny application, rejected
unauthenticated tightening, pending expiry/retraction/disable, restart
preservation, blocked unauthorized widening, and legitimate authenticated
widening are all reachable. The mutation matrix clears deny state through each
lifecycle edge, accepts unauthenticated tightening, grants assessor ALLOW, or
disables the legitimate widening path; every mutation must fail.

### Complete wire-cutover model

The migration state starts with one v0.8 admission plane, performs a quiesced
cut to a fresh native-1.0 incarnation, and then performs a quiesced rollback to
a fresh v0.8 incarnation. Old and new admission are never open together.
Pre-cutover v0.8 commands remain deliverable as hostile delayed traffic so the
model must reject them both during native 1.0 and after rollback, while fresh
native-1.0 and rollback-v0.8 commands still apply.

The v0.8 incarnation labels are deliberately non-chronological and compared only
for equality. The mutation matrix attempts dual-stack admission, activation
before either quiescence, rollback incarnation reuse, ordered-incarnation
comparison, and cross-wire v0.8 admission during native 1.0; every mutation must
fail.

## Narrow SMT obligations

[`run_smt.py`](run_smt.py) pins local Z3 output to
`Z3 version 4.16.0 - 64 bit` and runs four SMT-LIB files:

| File | Registered checks |
|---|---|
| [`authority_handover.smt2`](smt/authority_handover.smt2) | a complete cut can grant; old and new authority cannot overlap |
| [`stale_admission.smt2`](smt/stale_admission.smt2) | an exact current fence can admit; a stale generation cannot |
| [`assessment_monotonicity.smt2`](smt/assessment_monotonicity.smt2) | authenticated deny removal, assessor tightening, and authenticated applied-deny disposition are satisfiable; unauthenticated widening and applied deny without that disposition are not |
| [`non_authority_inputs.smt2`](smt/non_authority_inputs.smt2) | valid body authority is satisfiable; observer/PID/export/simulation state cannot replace a body lease |

Each file has a guard-removal mutation. The runner binds the current Z3 binary,
rejects output/control commands in the source, requires exact `check-sat` and
push/pop counts, and accepts only the registered result tokens as the complete
stdout. Version drift, `unknown`, timeout, stderr, oversized/extra output,
missing satisfiable premises, or a surviving mutation fails.

These formulas are intentionally not placed in `formal/`; they are disposable
pre-ratification challenge material, not the F01/F02 source set.

## Resource screens

[`resource_probe.py`](resource_probe.py) performs four screens:

1. Separate control, action, observation, and extension queues use current
   candidate capacities where available. One hundred thousand offers per
   observer-class queue must leave action state intact and cause zero control
   rejection. A seeded shared-budget design must fail.
2. The independent Python bounded parser consumes approximately 32 KiB and
   993 KiB valid arrays, accepts the exact depth limit, and rejects frame+1,
   depth+1, duplicate decoded keys, and unterminated input. Peak traced memory
   and local time are recorded under deliberately broad preliminary screens,
   not production targets.
3. A prototype journal retains at most 128 entries and 65,536 encoded entry
   bytes, rejects the next append, uses the bounded duplicate-rejecting parser
   for restore, round-trips exact recovery-required deny records, and rejects
   truncated or duplicate-key snapshots. A seeded silent-eviction design must
   be detected.
4. [`crypto_probe.py`](crypto_probe.py) uses real PyNaCl Ed25519 verification for
   empty, 64 KiB, and 1,420,000-byte signing inputs. Valid and full-length invalid
   signatures are measured. The 100,000-microsecond single-verification screen
   is deliberately local and preliminary; the detector is self-tested with a
   seeded overrun.

Exact numeric journal, extension, disposition, and production-deadline values
remain B03/N03/N05/N06/performance-gate inputs. The prototype values cannot be
copied into the normative contract without those tasks.

## Exact Fable 5 challenges

The original model/resource design was challenged by exact `claude-fable-5`,
terminal `end_turn`, raw response SHA-256
`4de23e2a48bff1c69d50a454e9ba92360a1372bb8812ee8e443617c6df697282`.
A later exact, terminal cutover and review-packet challenge is bound into the
result by response
SHA-256
`080ad93775d6dec018a08efeadd49b0d57e6162a90f4bc7cf9a8b43199246d32`.
The later response reported 672 input tokens, 2,156 output tokens, and 69
thinking tokens.

Retained advice includes the two-command stale/fresh witness, hostile
equality-versus-ordering mutation, semantic deny-set shrinking definition,
authenticated widening success witness, authenticated deny-tightening admission,
strict SMT stdout handling, nested result validation, satisfiable SMT premises,
complete wire cuts, explicit assessment disposition, exact review binding, and
seeded faults for every probe. Rejected advice is documented in
[`SECTION_REVIEW.md`](SECTION_REVIEW.md). The model is advice only and satisfies
no reviewer or evidence floor.

## Run

Prerequisites are the repository Python/toolchain, `ruff`, `uv`, exact Z3 4.16.0,
and the already locked signed-forwarding prototype environment.

```bash
./run.sh
```

The runner:

- compiles and lints the Python sources;
- explores the three bounded models and kills twenty-three mutations;
- runs eleven SMT checks and kills four formula mutations;
- runs the queue/parser/journal/real-Ed25519 resource screens;
- inventories every prototype source by SHA-256;
- binds the result to a clean current Git commit/tree and exact current contract
  manifest bytes;
  and
- passes the single bounded result line through
  [`verify_result.py`](verify_result.py).

A green run is local preliminary evidence only. External mTLS/ACL,
rotation/revocation, installed peers, live plants, fault/soak, fuzz/sanitizers,
performance qualification, signatures, provenance, clean-room reproduction,
consumer role qualification, publication, and post-publication validation
remain separate gates.
