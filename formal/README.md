# Machine-checked model of the NCP 2 owner

This directory holds a Lean 4 model of the NCP 2 owner (specification, section 7) and proofs of its safety properties.
It uses only Lean's core library. The proofs run before release and add nothing to the SDKs at run time.

## What is proved

[`NCP2/Model.lean`](NCP2/Model.lean) states owner rules 7.3.2 to 7.3.14 as one function, `step`, from the owner state and one decoded request to the new state and the response.
The digest function `H` is a parameter, and `step` compares identities where the rules do.
The behavior of the application (a result, an error, or a result that is too large) is an input of each step, so the proofs cover every application.

The theorems hold for every sequence of requests, in any number of steps. A request can come from any client, through any network, after any fault, so the owner's properties do not depend on the client or on the network.

| Theorem | File | Statement | Specification |
| --- | --- | --- | --- |
| `inv_step`, `inv_run` | [`Owner.lean`](NCP2/Owner.lean) | Every step keeps the owner invariant: before `open` nothing happened; after it, the accepted history is a hash chain whose last exchange is the kept one | 7.2, 7.3 |
| `Chain.seqs` | [`Chain.lean`](NCP2/Chain.lean) | The accepted requests carry the sequence numbers 0, 1, 2, ..., without gaps | 7.7.2 |
| `run_at_most_once` | `Owner.lean` | No request is executed twice | 7.7.1 |
| `Chain` (constructor `extend`) | `Chain.lean` | Each accepted request acknowledges the identity of the response before it, and nothing is accepted after an exchange that ends the session | 7.7.3, 7.3.8 |
| `step_rejected` | `Owner.lean` | A `rejected` response changes no state | 7.3, 7.4 |
| `step_retransmit` | `Owner.lean` | The kept request, sent again, gets the kept response again and changes nothing | 7.3.5 |
| `Chain.unique` | `Chain.lean` | If `H` has no collision among the frames of two histories, equal identities of their last responses imply equal histories | 7.7.6 |

[`Audit.lean`](Audit.lean) prints the axioms of each theorem. The gate requires exactly Lean's standard axioms (`propext`, `Classical.choice`, `Quot.sound`): no `sorry` and no added axiom.

## The model as a test oracle

[`Oracle.lean`](Oracle.lean) compiles the same `step` function into the program `ncp2-oracle`.
`../model/conformance.py --oracle` sends it random traces of correct, repeated, stale, skipped, invalid, and failing requests, and compares its outcomes and codes with those of a real owner.
The Python owner and the Rust owner agree with it on every trace of the gate.
This follows the pattern of AWS Cedar: a proved model, and differential testing of the implementations against it.

## What is not proved

- **The implementations.** The Python and Rust owners are not proved. They are tested against the proved model on random traces, which cover many inputs but not all.
- **The frame codec.** Decoding, JSON checks, attachments, and digests are tested by the shared vectors and by differential fuzzing (`../conformance`), not proved.
- **What a correct client learns.** Properties 4 and 5 of section 7.7, and the client side of property 6, depend on the client rules and on the network. `../model/ncp2_model.py` checks them in every reachable state of small bounded runs (3 steps, 2 faults, with loss, repetition, reordering, damage, and crashes). They are not proved for unbounded runs.
- **The digest.** `Chain.unique` assumes that `H` has no collision among the frames involved. For SHA-256 this is an assumption about the hash function, not a theorem.
- **The abstraction.** The model represents bodies, sessions, and identities by numbers. A difference between the specification's text and the model would go unnoticed by the proofs; the conformance traces against the real owners are the check on that step.

## Commands

With [elan](https://github.com/leanprover/elan) installed, which selects the Lean version in [`lean-toolchain`](lean-toolchain):

```text
lake build --wfail          # check every proof, warnings fatal, and build ncp2-oracle
lake env lean Audit.lean    # print the axioms of each theorem
```

[`../scripts/check_ncp2.sh`](../scripts/check_ncp2.sh) runs both, the axiom check, and the conformance traces against the oracle.
