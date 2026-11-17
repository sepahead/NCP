# Model checks of NCP 2

Three programs check the reference SDKs against the exchange rules of [section 7](../spec/NCP-2.md) and the [lockstep profile](../spec/NCP-2-LOCKSTEP.md).
They complement the Lean proofs in [`../formal`](../formal/README.md). The proofs cover a model of the rules for all inputs. These programs cover the real code for many inputs.

| Program | What it checks | Against |
| --- | --- | --- |
| [`simulate.py`](simulate.py) | The Python client and owner together, in every reachable state of bounded runs with faults | The eight properties of section 7.7, and progress without faults |
| [`lockstep.py`](lockstep.py) | The Python owner with the lockstep profile and a stepping client, in every reachable state of bounded runs with faults | Six safety properties, a stable holder, and progress without faults |
| [`conformance.py`](conformance.py) | The Python and Rust owners, on random traces | The Lean model of the owner, compiled into an oracle |

## simulate.py: an exhaustive check of the client and owner

The program drives the real state machines of the Python SDK: the client functions `request`, `receive`, `time_out`, and `closed`, and the owner function `step`.
They exchange real frames. The program only moves frames and checks results. It restates no protocol rule.

It explores two networks:

- **message**, the Zenoh binding: frames can be lost, repeated, delayed, and reordered, and the client sends a request again when its time limit passes;
- **stream**, a byte-stream binding: one ordered stream in each direction.

It explores every order of the client's steps, the owner's steps, the time limits, and these faults, up to a budget:

- loss and repetition of any frame (message);
- a restart of the owner, or the expiry of its session; copies of the earlier opening's requests can still arrive (message);
- a stop of the owner;
- requests of a faulty client or of a second writer in the session: a sequence gap, a wrong acknowledgement, another request with the next sequence number, and a request after the end (message);
- a broken connection, and damaged frames (stream);
- a response replaced by a `bad_frame` or `shutdown` response from another connection, replayed by a party on the path, as authentication of frames allows (stream).

The application declines bodies with `bad`, fails on `fail`, and returns a result too large for the session on `big`.
Its verdict on a body with `busy` depends on its state, and the search chooses that state at each step of the owner: the application declines with `conflict` and a reason, or it executes the request.
Five scripts of calls exercise `ok`, `declined` with `body_invalid`, `conflict`, and `unknown_op`, `owner_failure`, `result_too_large`, `ncp.ping`, and `close`.

In every reachable state, the program checks properties 1 to 8 of section 7.7.
It also checks that a stopped owner admits nothing, and that every run without faults and without expired time limits gives the verdicts that the application decides.
With two faults, it reaches about 2.6 million states in about 90 seconds. With one fault, it reaches about 105,000 states in a few seconds.

`--self-test` injects thirteen known defects into the SDK machines, one at a time, and requires a violation for each.
Ten are defects of the owner or the client: no acknowledgement check, accepted gaps, a forgotten kept request, execution after the end, a declined request that is not kept, a `conflict` response that is not kept, so that a copy of the request executes once the application is free (property 5 catches it), a constant nonce, an ignored stop, a client that accepts a response to another request, and a client that reports a time limit as "not executed".
Three are earlier rules: a client that trusts `session_expired`, a client that treats a rejected call as "not executed", and a client that trusts a response that names no request without checking its binding to the chain, as revision 3 allowed.

### What the check found

The first run found a gap in revision 2 of the specification.
The owner restarts, or the session expires. A delayed copy of the `open` request then opens the session again.
A later call acknowledges the response of the lost opening, so the owner rejects it with `ack_mismatch` or `seq_gap`.
Revision 2 told the client that a rejection meant "nothing ran", but an earlier copy of the call may have executed in the lost opening.
Rule 7.6.4 of revision 3 closes the gap: a rejection of a request other than `open` ends the session, and the request is possibly executed.

### Limits

- The runs are bounded: four calls, at most two faults, and one copy for each time limit.
- Only the Python client and owner run here. The Rust client applies the same rules, and the shared client vectors test it.
- The model has no clocks, and it has one session for each owner.

## lockstep.py: an exhaustive check of the lockstep profile

The program works as `simulate.py` does: the real owner of the Python SDK (`ncp.owner.step` with the real `ncp.Lockstep`) and the pure client machine of `ncp.client` exchange real frames, and a small program drives the client: open, take, step, step. After a step that is possibly executed, it opens a new session and takes the ticks; the verdict comes from `ncp.lockstep.judge`, which `LockstepClient.recover` also uses.
After a recovery without a verdict, the client goes on from the clock of the take, as `LockstepClient.recover` does.
It explores two shapes: one owner for each connection (a byte stream, where a copy of a frame arrives on a new connection) and one owner for each session identifier (as the Zenoh servers keep them), each with new session identifiers and with one identifier reused for all sessions.
Delay, reordering, and time limits are free. The faults are a copy of any frame that the client sent, the loss of a frame, the expiry of a session, a restart that keeps the clock, a restart to the same tick with another state, a restart to an earlier saved clock with its state (the initial clock included, as after a restart without a saved clock), and another client that takes the ticks and steps.

In every reachable world it checks:

- **S1.** A step with the verdict "did not run" never runs, and "ran" is true. After a restart to an earlier saved clock, the verdict describes the owner's state, as section 7 of the profile says: "did not run" then means that the step was not in that state when the take ran.
- **S2.** A step runs only in the opening whose take ran last.
- **S3.** The ticks count the steps in the owner's state, once each.
- **S4.** A recovery gives a verdict whenever its take finds the state that the client's known clock describes, or that state after the client's uncertain step: the clock changed in no other way. Ghost records of the steps in the owner's state make this exact, so a step of another client, or a restart, excuses no verdict that was still possible.
- **S5.** Accepting an `open` changes neither the clock nor the holder.
- **S6.** After "did not run", the state when the take ran was the state that the step answered.
- **L1.** No frame takes the ticks from the client's opening while the owner holds it, unless another client takes them.
- **Progress.** Runs without faults and time limits finish. The search checks it in the world where no transition other than a fault remains; without faults, that world is the end of the one run.

With one fault, the search reaches 469,268 worlds, and every property holds. On an Apple M4 Max it takes 15 to 90 seconds, depending on the load.
Its self-test injects thirteen known defects, at least one for each property, and detects each. Among them are the holder by session identifier of revision 2 of the profile and the takeover in `open` of revision 3.
Two of them, a take that ignores the term and a take that does not raise it, break only L1: the term keeps the holder stable, and the verdicts do not depend on it.

### Limits

- The runs are bounded: one stepping client with two steps, at most three sessions, and one fault in the gate. An advisory run outside the gate on 15 November 2026 checked two faults with `--max-worlds 60000000`: 8,087,105 worlds for the byte stream and 2,427,031 for Zenoh, in about 20 minutes, and every property held.
- Each owner step is atomic in the search, so the wait of a take for a running step is outside it. The SDK tests check that wait in both languages.
- The check does not cover an application that fails in a step (profile, rule 5.5), `result_too_large`, a stopping owner, bad frames, or more than one stepping client: the other client is atomic and steps once.
- The program drives the session client of the SDK and its own stepping program, and shares only `judge` with `LockstepClient`. The checks of `LockstepClient` and `take` on the responses (profile, rules 3.4, 6.1, 6.2, and 6.3) have SDK tests in both languages instead.
- Only the Python SDK runs here. The Rust SDK has the same rules, and its tests replay the cases that the search found.

## conformance.py: the owners against the Lean model

The program sends the same random traces to three owners: the compiled Lean model (`--oracle`), the Python owner, and an external owner program (`--owner`).
The traces hold correct, repeated, stale, skipped, and foreign requests, every `open` verdict, invalid, failing, and too large calls, unknown operations, `ncp.ping`, `close`, exact copies of earlier requests, stops, and restarts of the owner.
For every input, all owners must give the same outcome and code.
A response that the owner sends again must have the same bytes.
The application of the Python owner records what it executes, and no request may execute twice, also across restarts.
The run fails if the traces do not reach every code that an owner sends.

An external owner program speaks a command protocol on its standard input and output, so that the harness can stop and restart it:
`n` starts a new owner, `s` stops it, and `r` with a length and a frame asks for the response.
[`../rust/examples/model_owner.rs`](../rust/examples/model_owner.rs) drives the Rust owner in this way.

`--self-test` runs the Python owner with ten known defects, one at a time, and the traces must detect each.

## Commands

From the repository root:

```text
python3 model/simulate.py --faults 2                 # the exhaustive check
python3 model/simulate.py --faults 2 --self-test     # its mutation test
python3 model/lockstep.py --faults 1                 # the lockstep profile
python3 model/lockstep.py --faults 1 --self-test     # its mutation test
python3 model/conformance.py --traces 20000 --oracle formal/.lake/build/bin/ncp2-oracle \
    --owner rust/target/release/examples/model_owner
python3 model/conformance.py --traces 20000 --self-test --oracle formal/.lake/build/bin/ncp2-oracle
```

[`../scripts/check_ncp2.sh`](../scripts/check_ncp2.sh) runs all six.
