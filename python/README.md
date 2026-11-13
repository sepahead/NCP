# NCP 2 for Python

The reference SDK of [NCP 2](https://github.com/sepahead/NCP/blob/main/spec/NCP-2.md): at-most-once exchanges with a truthful outcome, and hash-chained streams, between independent programs.
It uses only the Python standard library.

- Distribution name: `sepahead-ncp`. Import name: `ncp`.
- Python 3.11 or later. NumPy is optional: the SDK sends NumPy arrays as typed attachments when NumPy is installed.

Install it from a checkout of this repository:

```sh
pip install ./python
```

## An owner and a client

An owner runs an application's operations; a client sends requests to it.
They agree on a contract, a JSON document that both identify by the SHA-256 digest of its exact bytes (specification, section 11):

```json
{"ncp_contract": 1, "application": "counter", "version": "1", "operations": {"add": {}}, "streams": {}}
```

The owner, `owner.py`, serves one session on its standard input and output:

```python
import ncp

contract = ncp.Contract.load("contract.json")


class Counter:
    def __init__(self):
        self.total = 0

    def validate(self, request):
        if type(request.body.get("amount")) is not int:
            raise ncp.Declined("amount must be an integer")

    def execute(self, request):
        self.total += request.body["amount"]
        return {"total": self.total}


ncp.serve_stdio(ncp.Owner(contract, Counter()))
```

The client, `client.py`, starts the owner and calls it:

```python
import sys

import ncp

contract = ncp.Contract.load("contract.json")
with ncp.Client(ncp.spawn([sys.executable, "owner.py"]), contract) as client:
    print(client.call("add", {"amount": 2}).body)  # {'total': 2}
    print(client.call("add", {"amount": 3}).body)  # {'total': 5}
    try:
        client.call("add", {"amount": "three"})
    except ncp.Declined as declined:
        print(declined.code)  # body_invalid: it never runs, and the session goes on
    print(client.call("add", {"amount": 1}).body)  # {'total': 6}
```

`validate` must not change state: a declined request leaves the application as it was.
`execute` runs each admitted request at most once, also when the client sends a request again after a lost response.
The `with` block opens the session and closes it; closing the channel of `spawn` ends the child.

## Outcomes

`Client.call` returns a `Result` with `body`, `arrays`, and `identity`, or raises one of these exceptions. Each one says whether the request executed (specification, section 7.7, property 7):

| Exception | Executed | Meaning |
| --- | --- | --- |
| `ncp.Declined` | No, and never | The owner admitted the request and did not execute it. `code` is `body_invalid` or `unknown_op`. The session goes on. |
| `ncp.Ended` | `executed`: `YES`, `NO`, or `UNKNOWN` | The session is over. `code` is the owner's code, or a local one: `local.timeout`, `local.closed`, `local.protocol`, or `local.bad_frame`. |
| `ncp.Rejected` | No | Only for `open`: the owner opened no session. `code` says why, for example `refused`. |
| `ncp.UsageError` | No | The client refused the call before it sent anything, for example a call after the session ended, or a request larger than the session bound. |

A request is possibly executed (`UNKNOWN`) only when the client cannot know: a time limit passed, the connection closed, the owner failed or forgot the session, or the owner lost the session and a delayed copy of `open` opened it again (rule 7.6.4).
At most one request of a session is possibly executed, and it is the last one.

## Arrays

Bulk numbers travel as typed attachments, not as JSON numbers.
Put an `ncp.Array` or a NumPy array anywhere in a body:

```python
rates = ncp.Array("f64", [3], struct.pack("<3d", 1.5, 2.5, 4.0))
result = client.call("set_rates", {"rates": rates})
```

A received array is an `ncp.Array` whose `data` is a view of the frame, without a copy.
`tolist()` gives a list, and `to_numpy()` a NumPy array.
The types are `u8`, `i8`, `u16`, `i16`, `u32`, `i32`, `u64`, `i64`, `f32`, and `f64`, little-endian.

## Contracts and schemas

A contract can give each operation a `request` and a `result` schema, and each stream a `body` schema, in a closed subset of JSON Schema (specification, section 11.1).
The owner declines a request whose body does not match its schema with `body_invalid`, before it calls `validate`.
`python -m ncp id contract.json` checks a contract and prints its identity.
An owner can serve several contracts of one application, for example two versions during an upgrade: `ncp.Owner([old, new], handler)`.

## Connections

| Connection | Owner side | Client side |
| --- | --- | --- |
| Pipes to a child process | `serve_stdio(owner)` | `spawn(argv)` |
| Unix domain socket | `UnixServer(make_owner, path).start()` | `connect_unix(path)` |
| TCP | `TcpServer(make_owner, host, port).start()` | `connect_tcp(host, port)` |

A connection carries one session. `UnixServer` and `TcpServer` call `make_owner()` for each connection, run each session in its own thread, and take `ncp.Limits` for the number of sessions and the time limits of frames and idle sessions.
`stop()` sends each session the shutdown response, after the owner has answered every request that it read.
TCP accepts only loopback addresses unless you pass `allow_remote=True`. Between computers, use TLS with certificates on both sides (`tls=ncp.TlsConfig(...)`), or the optional [Zenoh binding](https://github.com/sepahead/NCP/blob/main/bindings/zenoh/README.md) (`ncp_zenoh`) with mutual TLS and access control.
Put a Unix domain socket in a directory that only the users of the sessions can access; the servers create it with mode 0600.

To call many sessions at once, for example one for each agent, use `ncp.call_all(clients, op, bodies)`.
It sends every request before it reads the first response, so the owners work at the same time without a thread for each session.
It returns, for each session in its place, the result or the exception; one failed session does not stop the others.

## Profiles

For many agents that share one owner, such as robots in one simulated world, `ncp.Rounds` implements the [rounds profile](https://github.com/sepahead/NCP/blob/main/spec/NCP-2-ROUNDS.md).
Each agent has its own session. The owner applies one request of each agent per round, in the fixed order of the members, and every agent receives the same record of the requests that the round applied:

```python
def step(round_number, inputs):  # inputs: (agent, body) in member order
    return {agent: {"seen": len(inputs)} for agent, body in inputs}

rounds = ncp.Rounds(contract, "act", ["drone-1", "drone-2"], step, deadline=1.0)
server = ncp.UnixServer(rounds.owner, "/run/world/world.sock").start()

# in each agent, k = 1, 2, 3, ...
result = client.call("act", {"ncp.round": {"agent": "drone-1", "round": k}, "thrust": 0.4})
record = ncp.RoundRecord.of(result, "drone-1")  # checks that the round applied this request
```

For one simulation that steps through ticks, `ncp.Lockstep` and `ncp.LockstepClient` implement the [lockstep profile](https://github.com/sepahead/NCP/blob/main/spec/NCP-2-LOCKSTEP.md): each step names the tick that it advances to, and after a lost session, a new session tells the client whether its last step ran.

## Streams

A stream sends messages without responses, for example sensor values. Each message names the previous one, so a subscriber detects lost, repeated, and changed messages:

```python
publisher = ncp.Publisher("camera/left", contract.identity, send)  # a unique stream identifier
publisher.publish({"exposure_ms": 8})

subscriber = ncp.Subscriber({contract.identity})
delivery = subscriber.receive(frame)  # delivery.status: accepted, joined, repeat, broken_chain, ...
```

## Transcripts

A transcript records every frame that a program sends and receives, with a hash chain over the records. A verifier checks the digests, the sequence numbers, the acknowledgements, and the chain:

```python
tap = ncp.Tap("run-17.ncpt", recorder="host")
with ncp.Client(ncp.spawn(argv, tap=tap), contract) as client:
    ...
tap.close()
report = ncp.verify_transcript("run-17.ncpt")  # report.ok, report.sessions, report.problems
```

`python -m ncp verify run-17.ncpt` does the same from the command line, and `python -m ncp inspect` prints a transcript.
A tap gives each record to the operating system before the frame is sent, so the transcript keeps every record up to a crash of the recording program.
`Tap(path, buffered=True)` collects records in a buffer of 1 MiB instead: one system call fewer for each frame, but a crash loses the records in the buffer.
With `key=`, the chain is an HMAC, and only a holder of the key can verify or extend it.

## Security

NCP checks the integrity of every frame with its SHA-256 digest. A digest is not an authentication code.
To authenticate every frame, give both sides the same key of at least 32 bytes: `ncp.Owner(contract, handler, key=key)` and `ncp.Client(channel, contract, key=key)` (specification, section 13.2).
On networks that are not trusted, also use TLS with certificates on both sides.

## Options

| Option | Default | Effect |
| --- | --- | --- |
| `Client(bound=...)` | 1 MiB | The largest frame of the session, from 64 KiB to 64 MiB. The owner can lower it. |
| `Client(timeout=..., retries=...)` | none, 3 | The time limit for a response, in seconds, and how often a lossy channel sends a request again. |
| `Owner(max_bound=...)` | 1 MiB | The largest session bound that the owner accepts. |
| `check_digests=False` | on | Turns off the comparison of received digests. Use it only on pipes or a Unix domain socket with no other program between the two ends (specification, section 3, rule 5). |
| `observer=` | log errors | Receives an `ncp.Event` for each step of a client, an owner, or a server. The default logs failures of the application on the logger `ncp`. |

## Tests

```sh
python3 tests/test_ncp.py
python3 tests/test_rounds.py
python3 tests/test_conformance.py
python -m ncp conformance --decoder PROGRAM --owner PROGRAM   # another implementation
```

`NCP_RUST_EXAMPLES=<directory of the Rust examples>` also runs a session with the Rust owner.
The SDK is tested on Linux and macOS. Windows has no Unix domain sockets in Python, and a receive time limit on a pipe fails there, because `select` accepts only sockets; pipes without a time limit and TCP are not tested on Windows.
