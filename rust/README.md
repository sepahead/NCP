# NCP 2 for Rust

The Rust core of [NCP 2](https://github.com/sepahead/NCP/blob/main/spec/NCP-2.md): at-most-once exchanges with a truthful outcome, and hash-chained streams, between independent programs.

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
They agree on a contract, a JSON document that both identify by the SHA-256 digest of its exact bytes (specification, section 11):

```json
{"ncp_contract": 1, "application": "counter", "version": "1", "operations": {"add": {}}, "streams": {}}
```

The owner serves one session on its standard input and output:

```rust
use ncp::{declined, AppError, Contract, Handler, Invalid, Owner, Reply, Request};
use serde_json::json;

struct Counter {
    total: i64,
}

impl Handler for Counter {
    fn validate(&mut self, request: &Request<'_>) -> Result<(), Invalid> {
        if !request.body["amount"].is_i64() {
            return Err(declined("amount must be an integer"));
        }
        Ok(())
    }

    fn execute(&mut self, request: &Request<'_>) -> Result<Reply, AppError> {
        self.total += request.body["amount"].as_i64().unwrap_or(0);
        Ok(json!({"total": self.total}).into())
    }
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let contract = Contract::from_bytes(std::fs::read("contract.json")?)?;
    let mut owner = Owner::new(contract, Counter { total: 0 });
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
    let mut client = Client::new(ncp::spawn(Command::new("./owner"))?, &contract);
    client.open()?;
    println!("{}", client.call("add", json!({"amount": 2}), &[])?.message["body"]); // {"total":2}
    println!("{}", client.call("add", json!({"amount": 3}), &[])?.message["body"]); // {"total":5}
    match client.call("add", json!({"amount": "three"}), &[]) {
        // It never runs, and the session goes on.
        Err(Error::Declined { code, .. }) => println!("{code}"), // body_invalid
        other => println!("unexpected: {other:?}"),
    }
    println!("{}", client.call("add", json!({"amount": 1}), &[])?.message["body"]); // {"total":6}
    client.close()?;
    Ok(())
}
```

`validate` must not change state: a declined request leaves the application as it was.
`execute` runs each admitted request at most once, also when the client sends a request again after a lost response.
Dropping the channel of `spawn` ends the child.

## Outcomes

`Client::call` returns the decoded `ok` response, or an `Error`. Each one says whether the request executed (specification, section 7.7, property 7); `Error::executed()` gives it for every variant:

| Error | Executed | Meaning |
| --- | --- | --- |
| `Error::Declined { code, .. }` | No, and never | The owner admitted the request and did not execute it. `code` is `body_invalid` or `unknown_op`. The session goes on. |
| `Error::Ended { code, executed, .. }` | `Yes`, `No`, or `Unknown` | The session is over. `code` is the owner's code, or a local one: `local.timeout`, `local.closed`, `local.protocol`, or `local.bad_frame`. |
| `Error::Rejected { code, .. }` | No | Only for `open`: the owner opened no session. |
| `Error::Usage(reason)` | No | The client refused the call before it sent anything, for example a call after the session ended, or a request larger than the session bound. |

A request is possibly executed (`Unknown`) only when the client cannot know: a time limit passed, the connection closed, the owner failed or forgot the session, or the owner lost the session and a delayed copy of `open` opened it again (rule 7.6.4).
At most one request of a session is possibly executed, and it is the last one.

The client rules are also pure functions over a `ClientState` (`client::request`, `client::receive`, `client::time_out`, `client::closed`), and the owner rules one function over an `OwnerState` (`owner::step`), for drivers of your own.

## Arrays

Bulk numbers travel as typed attachments. Make an `Array`, put its reference in the body, and pass the array with the call:

```rust
let rates = ncp::Array::from_f64(&[1.5, 2.5, 4.0]);
let reply = client.call("set_rates", json!({"rates": rates.reference(0)}), &[rates])?;
```

The encoder checks that each array has exactly one reference with its own type and shape.
A received frame keeps its bytes once: `array_bytes(i)` returns a slice of the frame, and `array_f64(i)` and the other typed readers return the elements.

## Contracts and schemas

A contract can give each operation a `request` and a `result` schema, and each stream a `body` schema, in a closed subset of JSON Schema (specification, section 11.1).
The owner declines a request whose body does not match its schema with `body_invalid`, before it calls `validate`.
An owner can serve several contracts of one application, for example two versions during an upgrade: `Owner::with_contracts(vec![old, new], handler)`.

## Connections

| Connection | Owner side | Client side |
| --- | --- | --- |
| Pipes to a child process | `serve_stdio(&mut owner)` | `spawn(command)` |
| A socket pair to a child process, with time limits | `serve_stdio(&mut owner)` | `spawn_unix(command)` |
| Unix domain socket | `serve_unix(path, make_owner, limits)` | `connect_unix(path)` |
| TCP | `serve_tcp(address, false, make_owner, limits)` | `connect_tcp(address, false)` |

A connection carries one session. `serve_unix` and `serve_tcp` call `make_owner()` for each connection, run each session in its own thread, and take `Limits` for the number of sessions and the time limits of frames and idle sessions. `Server::stop` sends each session the shutdown response, after the owner has answered every request that it read.
TCP accepts only loopback addresses unless the second argument is `true`; use that only on a trusted cluster network.
Between computers, or over a network that can lose messages, use the optional [Zenoh binding](https://github.com/sepahead/NCP/blob/main/bindings/zenoh/README.md) (crate `sepahead-ncp-zenoh`), with mutual TLS and access control on networks that are not trusted.
`set_timeout(Some(limit))` on a socket channel sets a time limit for each response: a call whose response does not arrive in time ends the session with `local.timeout`, possibly executed. A pipe takes no time limit; start the child with `spawn_unix` to give it one.
The binding sets 1 MiB socket buffers and `TCP_NODELAY`.
To call many sessions at once, use `ncp::call_all(&mut clients, op, bodies)`.
It sends every request before it reads the first response, so the owners work at the same time without a thread for each session, and it returns each session's result in its place.

The crate is tested on Linux and macOS. It also builds for Windows, without the Unix domain socket functions, but it is not tested there.

## Profiles, streams, and transcripts

`Lockstep` and `LockstepClient` implement the [lockstep profile](https://github.com/sepahead/NCP/blob/main/spec/NCP-2-LOCKSTEP.md): each step names the tick that it advances to, and after a lost session, a new session tells the client whether its last step ran.
`Publisher` numbers and chains the messages of a stream under a unique stream identifier; `Subscriber` reports each frame as accepted (with the number of lost messages before it), joined, a repeat, a conflict, a broken chain, an unknown contract, or a bad frame.
`Tap` records the frames that a channel sends and receives (`with_tap` on a channel), with a hash chain over the records, and `transcript::verify` checks the digests, the sequence numbers, the acknowledgements, and the chain.
A tap gives each record to the operating system before the frame is sent, so a transcript keeps every record up to a crash of the recording program.

## Options

| Option | Default | Effect |
| --- | --- | --- |
| `Client::with_bound` | 1 MiB | The largest frame of the session, from 64 KiB to 64 MiB. The owner can lower it. |
| `Client::with_retries` | 3 | How often a lossy channel sends a request again. |
| `Owner::with_max_bound` | 1 MiB | The largest session bound that the owner accepts, from 64 KiB to 64 MiB. |
| `with_key` on `Owner`, `Client`, `Subscriber`, `Publisher` | none | Authenticates every frame with HMAC-SHA-256 and a key of at least 32 bytes (specification, section 13.2). |
| `without_digest_check` on `Owner`, `Client`, `Subscriber` | check on | Turns off the comparison of received digests. Use it only on pipes or a Unix domain socket with no other program between the two ends (specification, section 3, rule 5). |
| `with_observer` on `Owner`, `Client` | errors to standard error | Receives an `Event` for each step. `events::Silent` drops them. |

## Tests and examples

```sh
cargo test --release
```

The tests include the shared conformance vectors of `../conformance` and, when `python3` is available, a session with the Python owner.
The examples are the owners and clients of the benchmarks and of the conformance tools: `echo_owner`, `bench_client`, `model_owner`, `conformance_owner`, and `decode_corpus`.
