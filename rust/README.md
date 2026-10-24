# NCP 2 for Rust

The Rust core of [NCP 2](../spec/NCP-2.md): exactly-once exchanges and hash-chained streams between independent programs.

- Crate name: `sepahead-ncp-core`. Library name: `ncp`.
- Rust 1.88 or later. No `unsafe` code.
- Dependencies: `serde` and `serde_json` for JSON, `sha2` for SHA-256 (with the ARMv8 and x86 instructions), and `socket2` to set socket buffer sizes.

Add it from a checkout of this repository:

```toml
[dependencies]
ncp = { package = "sepahead-ncp-core", path = "../NCP/rust" }
serde_json = "1"
```

## An owner and a client

An owner runs an application's operations; a client sends requests to it.
They agree on a contract, a JSON document that both identify by the SHA-256 digest of its exact bytes (specification section 11):

```json
{"ncp_contract": 1, "application": "counter", "version": "1", "operations": {"add": {}}, "streams": {}}
```

The owner serves one session on its standard input and output:

```rust
use ncp::{Contract, Decoded, Handler, Owner, Reply};
use serde_json::json;

struct Counter {
    total: i64,
}

impl Handler for Counter {
    fn validate(&mut self, _op: &str, request: &Decoded) -> Result<(), String> {
        match request.message["body"]["amount"].is_i64() {
            true => Ok(()),
            false => Err("amount must be an integer".into()),
        }
    }

    fn execute(&mut self, _op: &str, request: &Decoded) -> Result<Reply, Box<dyn std::error::Error + Send + Sync>> {
        self.total += request.message["body"]["amount"].as_i64().unwrap_or(0);
        Ok(json!({"total": self.total}).into())
    }
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let contract = Contract::from_bytes(std::fs::read("contract.json")?)?;
    let counter = Counter { total: 0 };
    let mut owner = Owner::new(&contract.application, &contract.identity, counter, contract.operations.clone(), ncp::DEFAULT_BOUND);
    ncp::serve_stdio(&mut owner)?;
    Ok(())
}
```

The client starts the owner and calls it:

```rust
use ncp::{Client, Contract, Error};
use serde_json::json;
use std::process::Command;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let contract = Contract::from_bytes(std::fs::read("contract.json")?)?;
    let (channel, mut child) = ncp::spawn(Command::new("./owner"))?;
    let mut client = Client::new(channel, &contract.application, &contract.identity);
    client.open()?;
    println!("{}", client.call("add", json!({"amount": 2}), &[])?.message["body"]); // {"total":2}
    println!("{}", client.call("add", json!({"amount": 3}), &[])?.message["body"]); // {"total":5}
    match client.call("add", json!({"amount": "three"}), &[]) {
        Err(Error::Rejected { code, .. }) => println!("{code}"), // body_invalid; the owner changed nothing
        other => println!("unexpected: {other:?}"),
    }
    client.close()?;
    child.wait()?;
    Ok(())
}
```

`validate` must not change state: a rejected request leaves the owner as it was.
`execute` runs each accepted request once, also when the client sends a request again after a lost response.

## Outcomes

`Client::call` returns the decoded `ok` response, or an `Error`:

| Error | Meaning |
| --- | --- |
| `Error::Rejected { code, body }` | The owner did not execute the request and changed no state. The session continues. |
| `Error::Ended { code, executed }` | The session is over. `executed` is `"yes"`, `"no"`, or `"unknown"` for the last request. |
| `Error::Protocol`, `Error::Frame`, `Error::Io` | The peer broke the protocol, or the connection failed. The session is over. |

## Arrays

Bulk numbers travel as typed attachments. Make an `Array`, put its reference in the body, and pass the array with the call:

```rust
let rates = ncp::Array::from_f64(&[1.5, 2.5, 4.0]);
let reply = client.call("set_rates", json!({"rates": rates.reference(0)}), &[rates])?;
```

The encoder checks that each array has exactly one reference with its own type and shape.
A received frame keeps its bytes once: `array_bytes(i)` returns a slice of the frame, and `array_f64(i)` and the other typed readers return the elements.

## Connections

| Connection | Owner side | Client side |
| --- | --- | --- |
| Pipes to a child process | `serve_stdio(&mut owner)` | `spawn(command)` |
| Unix domain socket | `unix_channel(stream)` for each accepted stream, then `serve` | `connect_unix(path)` |
| TCP | `listen_tcp(address, false)`, then `tcp_channel(stream)` and `serve` for each connection | `connect_tcp(address, false)` |

A connection carries one session. TCP accepts only loopback addresses unless the second argument is `true`; use that only on a trusted cluster network.
The binding sets 1 MiB socket buffers and `TCP_NODELAY`.
To call many sessions at once, use `ncp::call_all(&mut clients, op, bodies)`.

The crate is tested on Linux and macOS. It also builds for Windows, without the Unix domain socket functions, but it is not tested there; the examples and tests use Unix domain sockets.

## Streams and transcripts

`Publisher` numbers and chains the messages of a stream; `Subscriber` reports each frame as accepted (with the number of lost messages before it), a repeat, a broken chain, an unknown contract, or a bad frame.
`Tap` records the frames that a channel sends and receives (`with_tap` on a channel), and `transcript::verify` checks the digests, the sequence numbers, and the hash chain.
`Tap::create` gives each record to the operating system at once, so a transcript keeps every record up to a crash of the recording program; `Tap::create_buffered` saves one system call for each frame but loses its buffer in a crash.
A failure to write a record is an error of the channel's send or receive.

## Options

| Option | Default | Effect |
| --- | --- | --- |
| `Client::with_bound` | 1 MiB | The largest frame of the session, from 64 KiB to 64 MiB. The owner can lower it. |
| The `max_bound` argument of `Owner::new` | required | The largest session bound that the owner accepts, from 64 KiB to 64 MiB. |
| `without_digest_check` on `Owner`, `Client`, `Subscriber` | check on | Turns off the comparison of received digests. Use it only on pipes or a Unix domain socket with no other program between the two ends (specification section 3, rule 4). |

## Tests and examples

```sh
cargo test --release
```

The tests include the shared conformance vectors of `../conformance` and, when `python3` is available, a session with the Python owner.
The examples are the owners and clients of the benchmarks and of the conformance tools: `echo_owner`, `bench_client`, `model_owner`, and `decode_corpus`.
