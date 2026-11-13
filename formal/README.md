# Machine-checked model of NCP 2

This directory holds a Lean 4 model of the NCP 2 owner and of a client that follows the client rules, and proofs of their properties (specification, section 7).
It uses only Lean's core library, in the version that [`lean-toolchain`](lean-toolchain) names.
The proofs run before release. They add nothing to the SDKs at run time.

## The model

| File | Contents |
| --- | --- |
| [`NCP2/Model.lean`](NCP2/Model.lean) | The owner: rules 7.3.2 to 7.3.13 as one function, `step`, from the owner state and one request to the new state and the response. Definitions only. |
| [`NCP2/ClientModel.lean`](NCP2/ClientModel.lean) | A client that follows section 7.6: `clientStep` for each event (send, a response arrives, the time limit passes), with its verdicts as ghost state. Definitions only. |
| [`NCP2/Chain.lean`](NCP2/Chain.lean) | The hash chain of admitted exchanges and its lemmas. |
| [`NCP2/Owner.lean`](NCP2/Owner.lean) | The owner invariant, at most once, rejections, retransmissions, and stops. |
| [`NCP2/Client.lean`](NCP2/Client.lean) | What a response that the owner sent says about the owner's history. |
| [`NCP2/Openings.lean`](NCP2/Openings.lean) | The first exchange of every history is an accepted `open` that carries the nonce of its input. |
| [`NCP2/Progress.lean`](NCP2/Progress.lean) | Correct requests are executed. |
| [`NCP2/ClientProofs.lean`](NCP2/ClientProofs.lean) | What the client's verdicts mean, alone and composed with the owner. |
| [`Statements.lean`](Statements.lean) | Every claim, without its proof. Review this file: it is what the proofs establish. |
| [`Audit.lean`](Audit.lean) | Each claim proved from the library, and the axioms of each proof. |
| [`Oracle.lean`](Oracle.lean) | The owner's `step` as the executable `ncp2-oracle`, for differential tests. |
| [`mutants.py`](mutants.py) | The mutation test of the claims. |

The digest function `H` is a parameter. The owner compares identities where the rules do.
An owner takes a sequence of inputs. Each input is a request with the application's behavior at that step, or a stop of the owner.
The behavior is the application's verdict on the body of a call, its result (a value, an error, or a result too large for the session), and the nonce that the owner draws if the step opens a session.
So the proofs cover every application, also one whose verdict depends on its own state, and every source of nonces.

## The claims

Each claim holds for every sequence of inputs, of any length.
A request can come from any client, through any network, after any fault of the network or of the client.
So the owner's claims do not depend on the client or on the network.

| Claim | Statement | Specification |
| --- | --- | --- |
| `AtMostOnce` | No request is admitted twice. | 7.7, property 1 |
| `OpeningsDisjoint` | Two runs whose `open` inputs never share a nonce admit no common request except `open`. A restarted owner, or an owner that forgot a session, is a new run. | 7.7, property 1; assumption A4 |
| `InOrder` | The admitted requests carry the sequence numbers 0, 1, 2, ... | 7.7, property 2 |
| `Acknowledged` | Each admitted request after `open` acknowledges the identity of the response before it. | 7.7, property 3 |
| `NothingAfterEnd` | Nothing is admitted after an exchange that ends the session. | 7.3.8 |
| `NothingAfterStop` | A stopped owner admits nothing. | 7.3.10; 7.7, property 5 |
| `RejectedChangesNothing` | A `rejected` response changes no state. | 7.7, property 6 |
| `RejectionMeansNotAdmitted` | Every rejection except `seq_stale` answers a request that the owner has not admitted. | 7.5; 7.7, property 6 |
| `StaleMayHaveExecuted` | For every digest, `seq_stale` can answer a request that executed. | 7.5 |
| `RetransmissionIdentical` | The kept request, sent again, gets the kept response again and changes nothing. | 7.3.5 |
| `Commitment` | Equal identities of the last responses of two histories imply equal histories. | 7.7, property 8; assumption A3 |
| `OkIsOwnExecution` | An `ok` response that names a request is the response of exactly one execution of it. | 7.7, property 4 |
| `DeclinedIsFinal` | A request that the owner declined never executes, after any further inputs. | 7.7, property 5 |
| `ShutdownIsFinal` | A request that got `shutdown` is never admitted, after any further inputs. | 7.7, property 5 |
| `HistoryFromInputs` | The owner admits only requests that it received. | 7.3 |
| `FaultFreeProgress` | Over a network without faults, a client that follows section 7.6 gets `open` and every valid call executed, in order. | 7.3, 7.6 |
| `UnknownIsLast` | A client that follows section 7.6 has at most one verdict "possibly executed" in a session, and it is the last. | 7.7, property 7 |
| `RejectedOnlyForOpen` | Such a client has the verdict "rejected" only for `open`. A rejection of another request ends its session as possibly executed. | 7.6.4 |
| `ClientTruthful` | Each verdict "executed" and "not executed" of such a client is true in the owner's history, then and after any further inputs. | 7.7, property 7 |

The safety claims would also hold for an owner that executes nothing. `FaultFreeProgress` rules that out.
`StaleMayHaveExecuted` corrected an earlier text of the specification, whose table of codes listed `seq_stale` with the requests that did not execute.

The assumptions of section 7.7 appear in the claims as hypotheses:

- **A1 and A2** (changed frames are detected; no third party forges frames). The client claims assume that every response that the client accepts is one that the owner sent.
- **A3** (no two frames of the runs share a digest). `Commitment`, `OpeningsDisjoint`, `OkIsOwnExecution`, `DeclinedIsFinal`, `ShutdownIsFinal`, and `ClientTruthful` assume that the digest has no collision among the frames or requests of the runs. No function from all frames to 256-bit digests is injective, so the claims assume only what a collision-resistant digest can give.
- **A4** (no two openings share a nonce). `OpeningsDisjoint` assumes that the `open` inputs of the two runs have different nonces.

[`Audit.lean`](Audit.lean) proves each statement from the library, so a theorem whose type drifts from its claim fails the build. It prints the axioms of each proof.
The gate allows only Lean's standard axioms (`propext`, `Classical.choice`, `Quot.sound`), so no `sorry` and no added axiom.
The gate also replays every proof with `leanchecker --fresh`: the Lean kernel checks the compiled proofs again, outside the elaborator that produced them. It is the same kernel. A second, independent kernel is not used.

## How strong the claims are

A proof shows only what its statement says, and a weak statement can be proved about a bad model.
[`mutants.py`](mutants.py) measures what the claims constrain.
It injects eleven defects, one at a time, into a temporary copy: nine into the owner model and two into the client model.
It checks that the mutated model still compiles, and requires the proofs to fail.
Lake stops at the first module that fails. The script therefore replaces each failing proof with `sorry`, builds again until the build succeeds, and reads the axioms of every claim.
A claim whose proof now uses `sorryAx` is a claim whose proof the defect broke.

Each defect breaks the proof of the claim that forbids it.
An owner that declines every call breaks exactly two proofs: the progress claim, and the example in which `seq_stale` answers a request that executed. The other seventeen claims, every safety claim among them, still prove for it with the standard axioms only.
A constant nonce breaks `OpeningsDisjoint`: without assumption A4 on real nonces, a copy of a step from an earlier opening could run again.

Read the table in two ways.
A blank cell is a proof: the claim still holds for the broken model, so the claim does not constrain that rule.
An `x` means that the proof as written fails. Many proofs share the owner invariant, so one broken rule breaks many of them, and an `x` alone does not show that the claim is false for that model.
Eleven mutants are a sample of defects, not a measure of every possible one.
`mutants.py --table` prints the table, and the gate fails if this copy differs from the run.

<!-- mutant-table:begin -->
| Claim | no ack check | gaps accepted | runs after end | re-executes copy | rejection changes state | decline not kept | stop ignored | constant nonce | declines every call | client goes on after rejection | client goes on after time limit |
| --- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `AtMostOnce` | x | x | x | x | x | x |  |  |  |  |  |
| `InOrder` | x | x | x | x | x | x |  |  |  |  |  |
| `Acknowledged` | x | x | x | x | x | x |  |  |  |  |  |
| `NothingAfterEnd` | x | x | x | x | x | x |  |  |  |  |  |
| `RejectedChangesNothing` |  |  |  | x | x |  |  |  |  |  |  |
| `RetransmissionIdentical` | x | x | x | x | x | x |  |  |  |  |  |
| `Commitment` | x | x | x | x | x | x |  |  |  |  |  |
| `OpeningsDisjoint` | x | x | x | x | x | x |  | x |  |  |  |
| `OkIsOwnExecution` | x | x | x | x | x | x |  |  |  |  |  |
| `DeclinedIsFinal` | x | x | x | x | x | x |  |  |  |  |  |
| `ShutdownIsFinal` | x | x | x | x | x | x | x |  |  |  |  |
| `RejectionMeansNotAdmitted` | x | x | x | x | x | x |  |  |  |  |  |
| `StaleMayHaveExecuted` |  |  |  |  |  |  |  |  | x |  |  |
| `NothingAfterStop` |  |  |  | x |  |  | x |  |  |  |  |
| `HistoryFromInputs` |  |  |  | x |  |  |  |  |  |  |  |
| `FaultFreeProgress` |  |  |  |  |  |  |  | x | x |  |  |
| `UnknownIsLast` |  |  |  |  |  |  |  |  |  |  | x |
| `RejectedOnlyForOpen` |  |  |  |  |  |  |  |  |  | x |  |
| `ClientTruthful` | x | x | x | x | x | x | x |  |  |  |  |
<!-- mutant-table:end -->

## The model as a test oracle

[`Oracle.lean`](Oracle.lean) compiles the same `step` function into the program `ncp2-oracle`.
[`../model/conformance.py`](../model/conformance.py) `--oracle` drives it, the Python owner, and the Rust owner with the same random traces.
The traces hold correct, repeated, stale, skipped, and foreign requests, every `open` verdict, invalid, failing, and too large calls, exact copies of earlier requests, stops, and restarts of the owner.
All three owners must give the same outcome and code for every input, and the traces must reach every code that an owner sends.
`--self-test` runs the Python owner with ten known defects, and the traces must detect each one.
This follows the pattern of AWS Cedar: a proved model, and differential tests of the implementations against it.

## What is not proved

- **The implementations.** The Python and Rust owners and clients are not proved. The oracle traces test the owners against the proved model, and the shared vectors test both SDKs. These tests cover many inputs, but not all.
- **Client verdicts across a restart of the owner.** `ClientTruthful` is about one run of one owner. A client that keeps its session while the owner restarts talks to two runs. [`../model/simulate.py`](../model/simulate.py) checks the real SDK client and owner in this case, in every reachable state of bounded runs with up to two faults. That check found the gap that rule 7.6.4 closes: a delayed copy of `open` can open a lost session again, and a later call then gets `rejected` although an earlier copy may have executed. The Lean model does not cover two runs for the client.
- **The frame codec.** Decoding, the JSON rules, attachments, and digests are tested by the shared vectors and by differential fuzzing (`../conformance`), not proved.
- **The digest and the peer.** The claims assume that `H` has no collision among the frames involved. For SHA-256, this is an assumption about the hash function, not a theorem. The client claims also assume that no third party forges frames.
- **Liveness under faults.** No claim says that a request sent again eventually gets a response. `FaultFreeProgress` covers only a network that delivers every frame once, in order, and unchanged.
- **Sizes and time.** Whether a result is too large for the session is an input of the model. The model does not compute frame sizes, and it has no clocks.
- **Streams, transcripts, and bindings.** Sections 8 to 10 are tested, not modeled.
- **The abstraction.** The model represents bodies, sessions, and identities by numbers. A difference between the text of the specification and the model would go unnoticed by the proofs. The oracle traces against the real owners check that step.

## Commands

With [elan](https://github.com/leanprover/elan) installed:

```text
lake build --wfail                   # check every proof, warnings fatal, and build ncp2-oracle
lake env lean Audit.lean             # print the axioms of each claim
lake env leanchecker --fresh Audit   # replay every proof in the kernel
python3 mutants.py --check README.md # the mutation test, and the table above
```

[`../scripts/check_ncp2.sh`](../scripts/check_ncp2.sh) runs all four, checks the axioms, and runs the oracle traces.
