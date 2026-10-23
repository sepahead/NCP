# NCP 2 for Python

The reference SDK of [NCP 2](../spec/NCP-2.md): exactly-once exchanges and hash-chained streams between independent programs.
It uses only the Python standard library.

- Distribution name: `sepahead-ncp`. Import name: `ncp`.
- Python 3.11 or later. NumPy is optional: the SDK sends NumPy arrays as typed attachments when NumPy is installed.

Install it from a checkout of this repository:

```sh
pip install ./python
```

## An owner and a client

An owner runs an application's operations; a client sends requests to it.
They agree on a contract, a JSON document that the owner and the client identify by the SHA-256 digest of its exact bytes (specification section 11):

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

    def validate(self, op, body):
        if type(body.get("amount")) is not int:
            raise ncp.BodyInvalid("amount must be an integer")

    def execute(self, op, body):
        self.total += body["amount"]
        return {"total": self.total}


owner = ncp.Owner(contract.application, contract.identity, Counter(), contract.operations)
ncp.serve_stdio(owner)
```

The client, `client.py`, starts the owner and calls it:

```python
import sys

import ncp

contract = ncp.Contract.load("contract.json")
channel, process = ncp.spawn([sys.executable, "owner.py"])
client = ncp.Client(channel, application=contract.application, contract=contract.identity)
client.open()
print(client.call("add", {"amount": 2}).body)  # {'total': 2}
print(client.call("add", {"amount": 3}).body)  # {'total': 5}
try:
    client.call("add", {"amount": "three"})
except ncp.Rejected as rejected:
    print(rejected.code)  # body_invalid; the owner changed nothing
client.close()
process.wait()
```

`validate` must not change state: a rejected request leaves the owner as it was.
`execute` runs each accepted request once, also when the client sends a request again after a lost response.

## Outcomes

`Client.call` returns a `Result` with `body`, `identity`, and `arrays`, or raises:

| Exception | Meaning |
| --- | --- |
| `ncp.Rejected` | The owner did not execute the request and changed no state. `code` says why. The session continues. |
| `ncp.Ended` | The session is over. `executed` is `"yes"`, `"no"`, or `"unknown"` for the last request. |
| `ncp.ProtocolError` | The peer broke the protocol, for example with a bad frame. The session is over. |

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

## Connections

| Connection | Owner side | Client side |
| --- | --- | --- |
| Pipes to a child process | `serve_stdio(owner)` | `spawn(argv)` |
| Unix domain socket | `UnixServer(make_owner, path).start()` | `connect_unix(path)` |
| TCP | `TcpServer(make_owner, host, port).start()` | `connect_tcp(host, port)` |

A connection carries one session. `UnixServer` and `TcpServer` call `make_owner()` for each connection.
TCP accepts only loopback addresses unless you pass `allow_remote=True`; use it only on a trusted cluster network.
Put a Unix domain socket in a directory that only the users of the sessions can access.

To call many sessions at once, for example one for each agent, use `ncp.call_all(clients, op, bodies)`.
It returns, for each session in its place, the result or the exception; one failed session does not stop the others.

## Streams

A stream sends messages without responses, for example sensor values. Each message names the previous one, so a subscriber detects lost, repeated, and changed messages:

```python
publisher = ncp.Publisher("camera/left", contract.identity, send)
publisher.publish({"exposure_ms": 8})

subscriber = ncp.Subscriber({contract.identity})
delivery = subscriber.receive(frame)  # delivery.status: accepted, repeat, broken_chain, ...
```

## Transcripts

A transcript records every frame that a program sends and receives. A verifier checks the digests, the sequence numbers, and the hash chain:

```python
tap = ncp.Tap("run-17.ncpt")
channel, process = ncp.spawn(argv, tap=tap)
...
tap.close()
reports = ncp.verify_transcript("run-17.ncpt")  # one report for each session
```

A tap gives each record to the operating system at once, so the transcript keeps every record up to a crash of the recording program.
`Tap(path, buffered=True)` collects records in a buffer of 1 MiB instead: one system call fewer for each frame, but a crash loses the records in the buffer.
A failure to write a record raises, so that a session never runs on without its record.

## Options

| Option | Default | Effect |
| --- | --- | --- |
| `Client(bound=...)` | 1 MiB | The largest frame of the session, from 64 KiB to 64 MiB. The owner can lower it. |
| `Client(timeout=...)` | none | The time limit for a response, in seconds. |
| `Owner(max_bound=...)` | 1 MiB | The largest session bound that the owner accepts. |
| `check_digests=False` | on | Turns off the comparison of received digests. Use it only on pipes or a Unix domain socket with no other program between the two ends (specification section 3, rule 4). |

## Tests

```sh
python3 tests/test_ncp.py
python3 tests/test_conformance.py
```

`NCP_RUST_EXAMPLES=<directory of the Rust examples>` also runs a session with the Rust owner.
