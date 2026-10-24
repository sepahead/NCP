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
| `responses_logged`, `step_log_prefix` | [`Client.lean`](NCP2/Client.lean) | Every response that is not `rejected` belongs to an exchange in the history, then and at every later time | 7.4 |
| `ok_is_own_execution` | `Client.lean` | An `ok` response that names the identity of a request is the response of exactly one execution of that request, if no other request frame shares the identity | 7.7.4 |
| `step_rejected_not_logged` | `Client.lean` | Every rejection except `seq_stale` means that the owner has never executed the request | 7.5, 7.7.5 |
| `seqStale_after_execution` | `Client.lean` | For every digest, a delayed copy of an executed request gets `seq_stale` once a later request has executed: the code says that this frame executed nothing, not that the request never executed | 7.5 |

The client-side theorems are about responses that the owner sent. They cover every network that loses, repeats, delays, or reorders frames, under two assumptions: changed frames are detected (by the digest check, or because the binding is a reliable stream), and no third party sends frames with valid digests. A digest is not an authentication code; the binding authenticates the peer.
`seqStale_after_execution` corrected the specification, whose table of codes listed `seq_stale` with the requests that did not execute.

[`Statements.lean`](Statements.lean) states every claim without its proof: it is the file to review.
[`Audit.lean`](Audit.lean) proves each statement from the library, so a theorem whose type drifts from its stated claim fails the build, and prints the axioms of each proof.
The gate allows only Lean's standard axioms (`propext`, `Classical.choice`, `Quot.sound`), so no `sorry` and no added axiom, and replays every proof with `leanchecker --fresh`: the Lean kernel checks the compiled proofs again, outside the elaborator that produced them. It is the same kernel; a second, independent kernel is not used.

## The model as a test oracle

[`Oracle.lean`](Oracle.lean) compiles the same `step` function into the program `ncp2-oracle`.
`../model/conformance.py --oracle` sends it random traces of correct, repeated, stale, skipped, invalid, and failing requests, and compares its outcomes and codes with those of a real owner.
The Python owner and the Rust owner agree with it on every trace of the gate.
`--self-test` measures the strength of the traces: it runs the Python owner with each of five known defects (no acknowledgement check, accepted gaps, a forgotten kept request, execution after the end, a wrong rejection code), and each defect must make a trace fail.
Continuing traces after an ending response found a fault in the harness: its mapping of requests to the Python reference model left the application's failure flag out of a request's identity, so two different frames looked like one. The Lean oracle is not affected, because its requests carry the flag in their body.
This follows the pattern of AWS Cedar: a proved model, and differential testing of the implementations against it.

## What is not proved

- **The implementations.** The Python and Rust owners are not proved. They are tested against the proved model on random traces, which cover many inputs but not all.
- **The frame codec.** Decoding, JSON checks, attachments, and digests are tested by the shared vectors and by differential fuzzing (`../conformance`), not proved.
- **The client's own discipline.** That a client which follows section 7.6 never receives `seq_stale` for its current request, and that the requests it accepts form one chain, depend on the client rules. `../model/ncp2_model.py` checks them in every reachable state of small bounded runs (3 steps, 2 faults, with loss, repetition, reordering, damage, and crashes). They are not proved for unbounded runs.
- **The digest and the peer.** `Chain.unique` and `ok_is_own_execution` assume that `H` has no collision among the frames involved; for SHA-256 this is an assumption about the hash function, not a theorem. The client-side theorems also assume that no third party forges frames.
- **Liveness.** No theorem says that a retransmitted request eventually gets a response.
- **Size checks.** Whether a result is too large for the session is an input of the model; the model does not compute frame sizes.
- **The abstraction.** The model represents bodies, sessions, and identities by numbers. A difference between the specification's text and the model would go unnoticed by the proofs; the conformance traces against the real owners are the check on that step.

## Commands

With [elan](https://github.com/leanprover/elan) installed, which selects the Lean version in [`lean-toolchain`](lean-toolchain):

```text
lake build --wfail          # check every proof, warnings fatal, and build ncp2-oracle
lake env lean Audit.lean    # print the axioms of each claim
lake env leanchecker --fresh Audit   # replay every proof in the kernel
```

[`../scripts/check_ncp2.sh`](../scripts/check_ncp2.sh) runs both, the axiom check, and the conformance traces against the oracle.
