# Model checks of NCP 2

Two programs check the reference SDKs against the exchange rules of [section 7](../spec/NCP-2.md).
They complement the Lean proofs in [`../formal`](../formal/README.md). The proofs cover a model of the rules for all inputs. These programs cover the real code for many inputs.

| Program | What it checks | Against |
| --- | --- | --- |
| [`simulate.py`](simulate.py) | The Python client and owner together, in every reachable state of bounded runs with faults | The eight properties of section 7.7, and progress without faults |
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
- a broken connection, and damaged frames (stream).

The application declines bodies with `bad`, fails on `fail`, and returns a result too large for the session on `big`.
Four scripts of calls exercise `ok`, `declined`, `owner_failure`, `result_too_large`, `unknown_op`, `ncp.ping`, and `close`.

In every reachable state, the program checks properties 1 to 8 of section 7.7.
It also checks that a stopped owner admits nothing, and that every run without faults and without expired time limits gives the verdicts that the application decides.
With two faults, it reaches about 2.6 million states in about 90 seconds. With one fault, it reaches about 105,000 states in a few seconds.

`--self-test` injects eleven known defects into the SDK machines, one at a time, and requires a violation for each.
Nine are defects of the owner or the client: no acknowledgement check, accepted gaps, a forgotten kept request, execution after the end, a declined request that is not kept, a constant nonce, an ignored stop, a client that accepts a response to another request, and a client that reports a time limit as "not executed".
Two are earlier rules: a client that trusts `session_expired`, and a client that treats a rejected call as "not executed".

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
python3 model/conformance.py --traces 20000 --oracle formal/.lake/build/bin/ncp2-oracle \
    --owner rust/target/release/examples/model_owner
python3 model/conformance.py --traces 20000 --self-test --oracle formal/.lake/build/bin/ncp2-oracle
```

[`../scripts/check_ncp2.sh`](../scripts/check_ncp2.sh) runs all four.
