# NCP 2 specification

Status: draft for implementation, 23 October 2026.
This document is normative. The key words MUST, MUST NOT, SHOULD, SHOULD NOT, and MAY are to be interpreted as described in RFC 2119 and RFC 8174 when, and only when, they appear in all capitals.
The [design record](../docs/design/NCP-2-DESIGN.md) gives the reasons for each decision.

## 1. Scope

NCP couples independently owned programs, each in its own process.
It defines one frame format and two interaction patterns:

- **Exchange.** A client sends one request at a time to an owner. The owner executes each request at most once and keeps its response until the client acknowledges it. Use exchanges for simulation steps and for any operation that must not run twice.
- **Stream.** A publisher sends a sequence of messages to zero or more subscribers. Subscribers detect loss, reordering, and changed messages. Use streams for live sensor data and for monitors and recorders.

NCP defines the bindings that carry frames (section 9), a transcript format (section 10), and the identity of application contracts (section 11).
Applications define their operations, message bodies, units, clocks, and accepted values.

## 2. Terms

| Term | Meaning |
| --- | --- |
| Frame | The unit of transfer: header, JSON text, attachments, and digest (section 3). |
| Identity | The SHA-256 digest of a frame's bytes before its digest field, as 64 lowercase hexadecimal characters. |
| Owner | The program that executes requests of an exchange session. |
| Client | The program that sends requests of an exchange session. |
| Session | One exchange between one client and one owner, from `open` to its end. |
| Bound | The largest frame, in bytes, that a receiver accepts. |
| Contract | A document that defines an application's operations and messages (section 11). |

## 3. Frame format

A frame is a byte string with this layout:

| Offset | Size | Field |
| --- | --- | --- |
| 0 | 4 | Magic: the bytes `4E 43 50 02` (`"NCP"` and 2). |
| 4 | 4 | `J`: length of the JSON region, unsigned, big-endian. |
| 8 | 4 | `A`: length of the attachment region, unsigned, big-endian. |
| 12 | `J` | JSON region: one JSON text (section 4), then zero to seven space bytes (`0x20`). |
| 12 + `J` | `A` | Attachment region (section 5). |
| 12 + `J` + `A` | 32 | Digest: SHA-256 of bytes 0 to 12 + `J` + `A` − 1. |

Rules:

1. `12 + J` MUST be a multiple of 8. The sender adds the space bytes for this.
2. The frame length, `44 + J + A`, MUST NOT exceed the receiver's bound.
3. A receiver MUST check the magic, `J`, `A`, and the bound before it reads the rest of the frame.
4. A receiver MUST compute the digest and compare it with the digest field before it parses the JSON region. A frame with a different digest is a bad frame.
   Exception: on a pipe pair or a Unix domain socket where no other program can change frames between the two endpoints, an application MAY turn off this comparison for the frames that it receives.
   The identity of a received frame is then its digest field as received.
   A transcript verifier always makes the comparison (section 10).
5. The identity of a frame is the digest field as 64 lowercase hexadecimal characters. Senders and receivers compute identities from the exact bytes. NCP defines no canonical encoding.

## 4. JSON region

The JSON region MUST contain one JSON text as defined in RFC 8259, encoded in UTF-8 without a byte order mark, whose value is an object, followed only by padding spaces.
A receiver MUST reject the frame as a bad frame if any of these conditions is true:

- The text is not valid JSON, or its value is not an object.
- An object contains two members with the same name.
- A number without a fraction or exponent is `-0`, or has a magnitude larger than 2^53 − 1.
- A number with a fraction or exponent is outside the finite range of IEEE 754 binary64, for example `1e400`.
- A string contains an escaped unpaired surrogate (`\uD800` to `\uDFFF` that does not form a pair).
- Objects and arrays nest deeper than 64 levels.

A sender MUST check these conditions before it sends a frame.
An owner whose result breaks them ends the session with `owner_failure` (section 7.5).
Senders SHOULD write the compact form without spaces between tokens.
Member order has no meaning.

## 5. Attachments and arrays

The attachment region holds zero or more attachments, which are byte strings.
The envelope member `att` lists their lengths in order.

1. If `att` is absent or an empty array, `A` MUST be 0.
2. Attachment 0 starts at offset 0 of the region. Attachment `i + 1` starts at the first multiple of 8 at or after the end of attachment `i`. Padding bytes between attachments MUST be zero.
3. `A` MUST equal the end of the last attachment. The region has no trailing padding.
4. A frame MUST NOT have more than 1024 attachments.

An **array** is a JSON value of this form:

```json
{"ncp.array": {"dtype": "u32", "shape": [1788], "att": 0}}
```

- `dtype` is one of `u8`, `i8`, `u16`, `i16`, `u32`, `i32`, `u64`, `i64`, `f32`, `f64`. Elements are little-endian.
- `shape` is an array of zero or more integers, each 0 or larger. Elements are in row-major order. An empty shape is one element.
- `att` is the index of the attachment that holds the elements. Its length MUST equal the product of the shape and the element size.
- Each attachment MUST belong to exactly one array of the frame.

Because each attachment starts at a multiple of 8 from the start of the frame, a receiver can read arrays in place.

## 6. Messages

### 6.1 Request

A request is an object with exactly these members (`att` is optional):

| Member | Value |
| --- | --- |
| `ncp` | The integer 2. |
| `session` | The session identifier: a version 4 UUID in lowercase hyphenated form. |
| `seq` | The sequence number: 0 for `open`, then 1, 2, 3, and so on. |
| `op` | The operation: 1 to 64 characters from `a`–`z`, `0`–`9`, `_`, `.`, `-`, starting with a letter. |
| `ack` | `null` for `open`; otherwise the identity of the last response that the client accepted. |
| `body` | Any JSON value. |
| `att` | The attachment lengths (section 5). |

### 6.2 Response

A response is an object with exactly these members (`att` is optional):

| Member | Value |
| --- | --- |
| `ncp` | The integer 2. |
| `session` | The session of the request. |
| `seq` | The sequence number of the request. |
| `request` | The identity of the request frame. |
| `outcome` | `ok`, `rejected`, or `ended` (section 7.4). |
| `code` | `null` if `outcome` is `ok`; otherwise a code of 1 to 64 characters from `a`–`z` and `_` (section 7.5). |
| `body` | Any JSON value. For `rejected` and `ended`, an object with optional detail members. |
| `att` | The attachment lengths (section 5). |

### 6.3 Stream message

A stream message is an object with exactly these members (`att` is optional):

| Member | Value |
| --- | --- |
| `ncp` | The integer 2. |
| `stream` | The stream identifier: 1 to 256 characters from `a`–`z`, `A`–`Z`, `0`–`9`, `_`, `.`, `-`, `/`. A new publisher instance uses a new identifier. |
| `seq` | 1 for the first message, then 2, 3, and so on. |
| `prev` | `null` for the first message; otherwise the identity of the previous message of the stream. |
| `contract` | The identity of the stream's contract (section 11). |
| `body` | Any JSON value. |
| `att` | The attachment lengths (section 5). |

A receiver MUST treat a message with a missing member, an extra member, or a member of the wrong type as a bad frame.

## 7. Exchange

### 7.1 Session start

1. The client chooses a new random session identifier.
2. The client sends a request with `seq` 0, `op` `open`, `ack` `null`, and this body:

   | Member | Value |
   | --- | --- |
   | `application` | The application name of the contract. |
   | `contract` | The identity of the contract. |
   | `bound` | The bound that the client requests, from 65,536 to 67,108,864. |
   | `run` | Optional. A string of up to 256 characters that names the run. |

3. Until the owner sends the `open` response, both sides use the bound 65,536.
4. The owner accepts the session if the application and the contract match its own. Its `ok` response has this body:

   | Member | Value |
   | --- | --- |
   | `bound` | The session bound: the smaller of the requested bound and the owner's largest bound. |
   | `application` | The owner's application name. |
   | `contract` | The owner's contract identity. |
   | `implementation` | The name and version of the owner's NCP implementation. |

   A client MUST ignore members of this body that it does not know. Later versions can add members.
5. After the `open` response, both sides use the session bound for all frames of the session.

### 7.2 Owner state

An owner keeps, for each session:

- `high`: the sequence number of the last request that it executed or ended. It is 0 after `open`.
- `kept`: the last response that is not `rejected`, with its frame bytes, its identity, and the identity of its request.
- `ended`: true after a response with outcome `ended` or an `ok` response to `close`.

### 7.3 Owner rules

The owner handles one frame at a time, in arrival order, with these steps in this order:

1. If the frame is bad (sections 3 to 6), apply the binding's bad-frame rule (section 9). Stop.
2. If `ncp` is not 2, reject with `wrong_protocol`.
3. If no session is open: if `op` is `open` and `seq` is 0, apply section 7.1; otherwise reject with `not_open`. Stop.
4. If `session` is not the open session, reject with `wrong_session`. Stop.
5. If `seq` equals `high` and `kept` exists:
   - If the request identity equals the identity in `kept`, send the frame bytes of `kept` again. Stop.
   - Otherwise reject with `seq_conflict`. Stop.
6. If `seq` is less than `high`, reject with `seq_stale`. Stop.
7. If `seq` is greater than `high` + 1, reject with `seq_gap`. Stop.
8. If `ended` is true, reject with `session_ended`. Stop.
9. If `ack` is `null`, reject with `ack_missing`. If `ack` differs from the identity of `kept`, reject with `ack_mismatch`. Stop.
10. If `op` is `open`, reject with `already_open`. Stop.
11. If `op` is not `close` and the contract has no such operation, reject with `unknown_op`. If the application finds the body invalid before it changes any state, reject with `body_invalid`. Stop.
12. Release `kept`. Set `high` to `seq`.
13. Execute the request:
    - For `close`, end the session and respond `ok` with an empty object as body.
    - Otherwise call the application. If it returns a result, respond `ok` with the result. If it raises an error, respond `ended` with `owner_failure`.
    - If the `ok` response would exceed the session bound, respond `ended` with `result_too_large` and the body `{"size": S, "bound": B}`, where `S` is the frame size that the response would need.
14. Keep the response as `kept`. If the outcome is `ended`, or the operation is `close`, set `ended` to true.

A `rejected` response changes no state. The owner does not keep it, and the same request gets the same rejection again.

### 7.4 Outcomes

| Outcome | Meaning | The session |
| --- | --- | --- |
| `ok` | The owner executed the request once. The body is the result. | Continues, unless the operation was `close`. |
| `rejected` | This frame executed nothing and changed no state. Except after `seq_stale`, the owner has never executed the request (section 7.5). | Continues. The client can send a corrected request with the same `seq`. |
| `ended` | The session cannot continue. The code tells whether the request executed. | Ends. |

### 7.5 Codes

| Code | Outcome | The request executed |
| --- | --- | --- |
| `wrong_protocol`, `not_open`, `already_open`, `wrong_session`, `seq_gap`, `seq_conflict`, `ack_missing`, `ack_mismatch`, `unknown_op`, `body_invalid`, `contract_mismatch`, `bound_unacceptable`, `session_ended` | `rejected` | No |
| `seq_stale` | `rejected` | Not by this frame. An earlier copy of the request may have executed: a delayed copy of an executed request gets this code once a later request has executed. |
| `result_too_large` | `ended` | Yes |
| `owner_failure` | `ended` | Unknown |
| `bad_frame`, `shutdown` | `ended` | No request is named |

For `contract_mismatch` and `bound_unacceptable`, the owner responds to `open` and stays without a session.

Later versions of this specification can add codes. A receiver MUST accept a code that it does not know and use the outcome: after `rejected`, the frame executed nothing; after `ended`, the request is possibly executed.

### 7.6 Client rules

1. The client sends one request at a time and keeps its frame bytes until it accepts a response.
2. A response belongs to the request if `session`, `seq`, and `request` match. The client MUST ignore other frames, except that a frame with code `bad_frame` or `shutdown` ends the session.
3. After an `ok` response, the client sets `ack` of its next request to the identity of that response.
4. After a `rejected` response, the state of the owner is unchanged.
5. After an `ended` response, the session is over. For `owner_failure`, the client MUST treat the request as possibly executed.
6. On a binding that can lose frames (section 9.2), the client MAY send the same request frame again after a timeout. The owner sends the kept response again (rule 7.3.5).
7. If the client cannot get a response, it MUST treat the request as possibly executed and end the session.

### 7.7 Properties

These rules give the following properties. The Lean proofs in `formal/` establish properties 1 to 3 and the owner's side of properties 5 and 6 for every sequence of requests, so for any client and network. They establish property 4 for every network that loses, repeats, delays, or reorders frames, if changed frames are detected, no third party sends frames with valid digests, and no other request frame has the client's request identity. The model check in `model/` tests all six in every reachable state of bounded runs with lost, repeated, delayed, and changed frames, and with crashes of either side:

1. The owner executes each request at most once.
2. The owner executes requests in sequence order, without gaps.
3. The owner executes request `n + 1` only after the client acknowledged response `n` by its identity.
4. A response that the client accepts as `ok` is the response to its own request, from one execution.
5. A request that the client learns was `rejected` did not execute.
6. In a complete transcript, each request names the identity of the response before it, and each response names the identity of its request. The session is one hash chain, so the identity of the last response commits to every accepted request and response of the session.

## 8. Streams

1. A publisher numbers the messages of a stream from 1, sets `prev` to the identity of its previous message, and sets `contract` to the identity of the stream's contract.
2. A subscriber keeps, for each stream, the next expected `seq` and the identity of the last message it accepted.
3. If `seq` is the expected value and `prev` matches, the subscriber accepts the message.
4. If `seq` is larger than expected, the subscriber accepts the message and reports the number of lost messages.
5. If `seq` is the expected value and `prev` does not match, the subscriber MUST NOT accept the message and reports a broken chain.
6. If `seq` is smaller than expected, the subscriber drops the message as a repeat.
7. A subscriber that receives a message with an unknown `contract` MUST NOT accept it.

Streams give no delivery guarantee. Freshness and rate limits belong to the stream's contract.

## 9. Bindings

### 9.1 Byte-stream binding

The byte-stream binding sends frames back to back over one reliable, ordered byte stream: a pair of pipes, a Unix domain socket, or a TCP connection.

1. One connection carries one session.
2. A receiver reads the 12-byte header, checks it (section 3), and then reads the rest of the frame.
3. **Bad-frame rule:** if a receiver gets a bad frame, it sends, where it can, a response with `session` and `seq` set to `null`, outcome `ended`, and code `bad_frame`, and then closes the connection.
4. On a pipe pair, the owner reads frames from its standard input and writes frames to its standard output. It MUST NOT write anything else to its standard output.
5. An owner that listens on a Unix domain socket SHOULD create it in a directory that only the users of the session can access. On one machine, a Unix domain socket is the preferred connection between programs that the owner does not start.
6. A TCP endpoint MUST set `TCP_NODELAY`. By default, a TCP endpoint MUST listen on and connect to loopback addresses only. Other addresses require an explicit option. Use a secure tunnel or the Zenoh binding with TLS on networks that are not trusted.
7. If the connection closes, the session ends. A request without a response is possibly executed.
8. An implementation SHOULD set the send and receive buffers of a socket to at least 1 MiB. Small default buffers, such as the 8 KiB of a Unix domain socket on macOS, multiply the time that a large frame takes.

### 9.2 Zenoh binding

The Zenoh binding carries the same frame bytes as Zenoh payloads. It is optional.

1. An owner declares a queryable on `ncp/x/<service>`. A client sends each request frame as the payload of a query to that key. The owner replies with the response frame.
2. A publisher puts stream frames on `ncp/s/<stream-key>`. Subscribers subscribe to that key.
3. **Bad-frame rule:** a receiver drops a bad frame.
4. The client accepts only the reply that matches its request (rule 7.6.2). If no reply arrives in time, it sends the same request frame again.
5. Each owner MUST use its own service key.
6. Deployments on networks that are not trusted MUST use TLS with client certificates and Zenoh access control.

## 10. Transcripts

A transcript records the frames that one program sent and received.
Each record has this layout:

| Size | Field |
| --- | --- |
| 1 | Kind: 1 = sent, 2 = received. |
| 8 | Monotonic time in nanoseconds, unsigned, big-endian. |
| 4 | Frame length, unsigned, big-endian. |
| frame length | The frame bytes. |

A transcript file starts with the 8 bytes `4E 43 50 54 00 00 00 01` (`"NCPT"` and version 1).

A transcript is **complete** for a session if it contains the `open` request, a response for every request, and the response to `close`.
A verifier MUST check the digests of all frames, the sequence numbers, and the hash chain (property 7.7.6).
A complete, verified transcript proves which requests and responses the recorder sent and received, and in which order.
It does not prove who produced them.

## 11. Contracts

A contract is a JSON document that an application publishes. Its identity is the SHA-256 digest of its exact bytes, as 64 lowercase hexadecimal characters.
It MUST contain these members:

| Member | Value |
| --- | --- |
| `ncp_contract` | The integer 1. |
| `application` | The application name, 1 to 128 characters. |
| `version` | The contract version. |
| `operations` | An object. Each member names one exchange operation and describes its request body and result. |
| `streams` | An object. Each member names one stream type and describes its body, rate, and freshness. |

The descriptions of bodies, units, and clocks are the application's. NCP only compares contract identities.

## 12. Limits

| Limit | Value |
| --- | --- |
| Bound before `open` completes | 65,536 bytes |
| Largest session bound | 67,108,864 bytes |
| Default session bound in the reference SDKs | 1,048,576 bytes |
| JSON nesting | 64 levels |
| Integer magnitude | 2^53 − 1 |
| Attachments in a frame | 1024 |
| Operation name | 64 characters |
| Stream identifier | 256 characters |

## 13. Security

- NCP checks integrity against accidental damage and gives a hash-chained record. It does not authenticate peers. A peer that can write to the binding can make frames with valid digests.
- Pipes and Unix domain sockets rely on operating-system access control. TCP is limited to loopback by default. On networks that are not trusted, use a secure tunnel or the Zenoh binding with mutual TLS and access control.
- Applications that need authority, such as commands to physical machines, add their own signed authority in their contract. Haldir does this for plant commands.
- Bounds limit memory. Receivers check lengths before they allocate.
- If an application turns off the digest comparison (section 3, rule 4), damage between the two endpoints is not detected while the session runs. Identities, the hash chain, and transcript verification do not change.

## 14. Conformance

An implementation conforms if it passes the vectors in `conformance/` for the parts that it implements: frames, arrays, owner rules, client rules, streams, bindings, and transcripts.
The vectors give exact input frames and the expected outcome, code, and state.

## 15. Reserved names

These names are reserved for later versions of NCP and for NCP profiles. Applications MUST NOT use them with other meanings.

1. Operation names that start with `ncp.`.
2. Object members, at any level of a body, whose names start with `ncp.`. Section 5 uses `ncp.array`.

The design record (`docs/design/NCP-2-DESIGN.md`, section 11) describes the profiles that are planned for these names.

## 16. Threads, processes, and clusters (informative)

NCP needs no change for parallel programs. These patterns use it as specified:

- **Threads.** One session handles one request at a time. A program can run many sessions in parallel threads, one thread for each session at a time. A simulator can use any number of threads inside one request.
- **Many sessions.** A host that couples many programs, for example one controller for each agent, sends one request to each session and waits for all responses before the next step. The reference SDKs provide this as one call. Sessions are independent, so a slow or ended session does not change the others.
- **Rank-0 owner.** An MPI-parallel simulator, such as NEST with MPI, runs the owner in rank 0. Rank 0 passes each request to all ranks with an MPI broadcast, all ranks execute it, and rank 0 collects the result with an MPI gather before it responds. The client sees one session.
- **One session for each rank.** Each rank runs its own owner, usually over TCP. The client sends the requests and combines the results. This spreads the data over several connections.
- **Two parallel simulators.** To exchange data between the ranks of two MPI-parallel simulators inside one cluster job, MUSIC or a direct MPI coupling is the better tool. NCP then connects that job to programs outside it, such as a body, a monitor, or a recorder.
- **Nodes.** Between nodes, use the byte-stream binding over TCP with the explicit option for cluster networks, or the Zenoh binding. Each request costs one network round trip.
