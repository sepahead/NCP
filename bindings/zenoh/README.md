# The Zenoh binding of NCP 2

This directory holds the Zenoh binding of [specification section 9.2](../../spec/NCP-2.md#92-zenoh-binding), for Python ([`python/`](python), package `sepahead-ncp-zenoh`, module `ncp_zenoh`) and for Rust ([`rust/`](rust), crate `sepahead-ncp-zenoh`, library `ncp_zenoh`).
Use it when the programs of a closed loop run on different computers, or when a network can lose messages. On one computer, pipes and Unix domain sockets (section 9.1) are simpler and faster.

The binding is optional. The NCP 2 core packages do not depend on Zenoh: the Python SDK uses only the standard library, and the Rust SDK keeps its four dependencies. Both binding packages are tested with Zenoh 1.10.2 and accept later 1.x releases. They use TCP and TLS links only: no QUIC, no shared memory, and no compression.
The packages are version 2.0.0, like the rest of NCP 2.0, which is prepared for release; the tag and the publication follow.

## How it works

- An owner serves on the Zenoh key `ncp/x/<service>`. A client sends each request frame as the payload of a Zenoh query to that key, and the owner replies with the response frame. The frames are the same bytes as on a pipe.
- A message can be lost, so the client's channel is *lossy*: when no reply arrives within the channel's time limit (1 s by default), the client sends the same request frame again, at most three times. The owner answers a repeated request with the response that it kept (rule 7.3.5), so the request still runs at most once.
- A receiver drops a damaged frame without a reply; the client then sends the request again.
- One service serves many sessions, one owner for each session identifier. A session that sends no request for 10 minutes after its last response is forgotten. A request with `seq` greater than 0 of a session that the service does not hold, because it forgot the session or restarted, gets `ended` with the code `session_expired`, so the client treats it as possibly executed (rule 9.2.7). The time must exceed the longest time that a client waits for a response, all repeats included: 4 s with the defaults. Above 4,096 live sessions (`max_sessions`), an `open` gets `rejected` with the code `refused`.
- Streams travel as Zenoh publications on `ncp/s/<name>`. A subscriber checks them with the core SDK's `Subscriber`, which reports lost, repeated, and changed messages.
- Service and stream names are Zenoh keys without wildcards: chunks of letters, digits, `_`, `.`, and `-`, separated by `/`.
- The server checks the digest of each frame, or its authentication code with the server's key, before it reads the message or routes it to a session (section 3, rule 5). A frame of a session that the server does not hold has the handshake bound of 64 KiB (rule 9.2.10); a larger one gets no reply.
- The server runs each session in its own thread (rule 9.2.8). A long step of one session does not delay the other sessions of the same service, and the [rounds profile](../../spec/NCP-2-ROUNDS.md) can use the server. Within one session, the server handles the requests in their order of arrival, one at a time. A session with a request in progress is never forgotten.
- `stop(grace)` stops the server as rule 9.2.9 says: the checks of rules 7.3.1 to 7.3.9 still apply, so a copy of a kept request gets the kept response; an `open` gets `rejected` with `refused`; and a request that the owner would otherwise admit gets `ended` with `shutdown`, and is never admitted. After `grace` seconds, the server undeclares the service.
- A step that takes longer than the client's time limit is not a failure: the client sends the request again, and the owner answers the repeat with its kept response once the step has run. The client gives up after its last repeat, 4 s after the first send with the defaults, so give a client of long steps a longer limit, for example `ZenohChannel(session, service, timeout=30)` in Python or `.with_timeout(Duration::from_secs(30))` in Rust.

## Use it

Python, with the core package and `eclipse-zenoh` 1.10.2 or a later 1.x release installed:

```python
import zenoh, ncp, ncp_zenoh

# Owner: serve the application `Handler` on ncp/x/lab/nest, one owner for each session.
session = zenoh.open(config)
server = ncp_zenoh.Server(session, "lab/nest", lambda: ncp.Owner(contract, Handler())).start()

# Client: an ordinary ncp.Client over a Zenoh channel.
channel = ncp_zenoh.ZenohChannel(zenoh.open(config), "lab/nest")
with ncp.Client(channel, contract) as client:
    result = client.call("step", {"dt_ms": 1})

server.stop(grace=1.0)
```

Rust:

```rust
use ncp_zenoh::{Server, ServeOptions, ZenohChannel};

// Owner: declare the service; each session runs in its own thread.
let make_owner = move || ncp::Owner::new(contract.clone(), World::default());
let server = Server::declare(&session, "lab/nest", make_owner, ServeOptions::default())?;

// Client.
let channel = ZenohChannel::new(&session, "lab/nest")?;
let mut client = ncp::Client::new(channel, &contract);
client.open()?;
let result = client.call("step", serde_json::json!({"dt_ms": 1}), &[])?;
client.close()?;

server.stop(std::time::Duration::from_secs(1));
```

## Networks that are not trusted

Rule 9.2.6 requires TLS with client certificates and Zenoh access control on such networks.
`secure_config` (Python) and `secure_config` with `TlsFiles` (Rust) write a configuration with TLS links only, a certificate on both sides of each link (mutual TLS), names checked on connect, and no multicast scouting.
Add access control on both sides before you open the sessions.
On the owner's side, this example lets only the client whose certificate has the common name `host-a` use the service `lab/nest`:

```json5
access_control: {
  enabled: true,
  default_permission: "deny",
  rules: [{ id: "ncp-exchange", messages: ["query", "reply", "declare_queryable"],
            flows: ["ingress", "egress"], permission: "allow", key_exprs: ["ncp/x/lab/nest"] }],
  subjects: [{ id: "host-a", cert_common_names: ["host-a"] }],
  policies: [{ rules: ["ncp-exchange"], subjects: ["host-a"] }],
}
```

On the client's side, the access control admits only the owner as the one that may declare the queryable and reply on the service key. Without it, any peer with a certificate of the same CA could declare `ncp/x/lab/nest` and answer the client's queries. This example admits only the owner whose certificate has the common name `nest-owner`:

```json5
access_control: {
  enabled: true,
  default_permission: "deny",
  rules: [
    { id: "send-queries", messages: ["query"], flows: ["egress"], permission: "allow",
      key_exprs: ["ncp/x/lab/nest"] },
    { id: "owner-replies", messages: ["reply", "declare_queryable"], flows: ["ingress"],
      permission: "allow", key_exprs: ["ncp/x/lab/nest"] },
  ],
  subjects: [{ id: "nest-owner", cert_common_names: ["nest-owner"] }],
  policies: [{ rules: ["send-queries", "owner-replies"], subjects: ["nest-owner"] }],
}
```

NCP checks the integrity of every message; Zenoh's TLS and access control decide who may send them. For authentication of every frame by NCP itself, give both sides the same key (specification section 13.2): the client (`ncp.Client(..., key=K)`, `Client::with_key`), the server (`Server(..., key=K)` in Python, `ServeOptions { key: Some(K), .. }` in Rust), and each owner that the server makes (`ncp.Owner(..., key=K)`, `Owner::with_key`). The server checks the authentication code of each request before it reads the message, and authenticates the responses that it makes itself. It drops an `open` for an owner whose key differs from its own.

## Tests

[`scripts/check_ncp2_zenoh.sh`](../../scripts/check_ncp2_zenoh.sh) runs both test suites, the Rust format and lint checks, and the tests across the two languages. The tests, in [`python/tests/test_zenoh.py`](python/tests/test_zenoh.py) and [`rust/tests/zenoh.rs`](rust/tests/zenoh.rs), check, with two Zenoh sessions on the loopback interface, once each service has answered a probe request:

- a session with attachments, whose transcript verifies;
- a lost reply and a lost query: each step still runs once;
- a damaged frame gets no reply, and the session goes on; a request with `seq` greater than 0 of a session that the service does not hold gets `session_expired`, and a request with `seq` 0 other than `open` gets `not_open`;
- after an owner restart, a step that ran before the restart is reported as possibly executed; a declined request sent twice gets the same answer, and the session goes on; a failing validation ends only its own session; a deeply nested payload is dropped without stopping the service; above the limit, an `open` is refused; a rejected `open` keeps no session;
- sessions of one service are independent: a long step of one session does not delay another, and a failing handler ends only its own session, possibly executed;
- a stopping server answers a copy of a kept request with the kept response, a later request with `shutdown`, and an `open` with `refused`, and then undeclares the service;
- a forgotten session ends with `session_expired`, and its request does not run;
- a step longer than the expiry time keeps its session, because idle time counts from the last response;
- a subscriber accepts every stream message in order;
- mutual TLS admits a client whose certificate the CA signed and refuses a client of another CA; the owner's access control admits only the named client, and the same refused client is admitted without it; the client's access control admits only the named owner, so an impostor with a certificate of the same CA gets no query, and the same impostor answers without it;
- a Python client against the Rust owner and a Rust client against the Python owner, each with a lost reply.

## What this does not show

- No measurement of time yet: the binding has not run in a benchmark protocol.
- Two Zenoh sessions on one computer, over the loopback interface, without a router and without a real network.
- The certificates of the TLS tests are made by `openssl` for the test, with an elliptic-curve key and a lifetime of 30 days.
- The Rust lockfile holds `lz4_flex` 0.10.0, because `zenoh-transport` 1.10.2 depends on it; the advisory GHSA-vvp9-7p8x-rfvv concerns its decompression, which Zenoh uses only with the `transport_compression` feature. This binding does not enable that feature.
