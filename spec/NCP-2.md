# NCP 2 specification

Status: NCP 2.0, release candidate, revision 4 of 13 November 2026.
The tag `v2.0.0` freezes this text. After the tag, section 19 lists errata. An erratum corrects the text and changes no behavior.
This document is normative. The key words MUST, MUST NOT, SHOULD, SHOULD NOT, and MAY are to be interpreted as described in RFC 2119 and RFC 8174 when, and only when, they appear in all capitals.
The [design record](../docs/design/NCP-2-DESIGN.md) gives the reasons for each decision. [`ncp2-rules.json`](ncp2-rules.json) states the codes and outcomes of this document as data, and a check keeps the SDKs, the Lean model, and this text equal to it.

## 1. Scope

NCP couples independently owned programs, each in its own process.
It defines one frame format and two interaction patterns:

- **Exchange.** A client sends one request at a time to an owner. The owner admits each request at most once, keeps its answer, and gives every copy of the request the same answer. Use exchanges for simulation steps and for any operation that must not run twice.
- **Stream.** A publisher sends a sequence of messages to zero or more subscribers. Subscribers detect loss, reordering, and changed messages. Use streams for live sensor data and for monitors and recorders.

NCP defines the bindings that carry frames (section 9), a transcript format (section 10), the identity and the checked shapes of application contracts (section 11), and authenticated frames (section 13.2).
Applications define their operations, message bodies, units, clocks, and accepted values.
Profiles add rules for one kind of application (section 17).

## 2. Terms

| Term | Meaning |
| --- | --- |
| Frame | The unit of transfer: header, JSON text, attachments, and digest (section 3). |
| Identity | The digest field of a frame as 64 lowercase hexadecimal characters. |
| Owner | The program that executes the requests of an exchange session. |
| Client | The program that sends the requests of an exchange session. |
| Session | One exchange between one client and one owner, from `open` to its end. |
| Opening | One acceptance of an `open` by an owner. Each opening has its own nonce (section 7.1). |
| Admitted request | A request that the owner accepted into the session's hash chain. The owner keeps its response (section 7.3, rule 11). |
| Bound | The largest frame, in bytes, that a receiver accepts. |
| Contract | A document that defines an application's operations, streams, and shapes (section 11). |
| Possibly executed | The client cannot know whether the owner executed the request. |

## 3. Frame format

A frame is a byte string with this layout:

| Offset | Size | Field |
| --- | --- | --- |
| 0 | 4 | Magic: the bytes `4E 43 50 02` (`"NCP"` and 2). |
| 4 | 4 | `J`: length of the JSON region, unsigned, big-endian. |
| 8 | 4 | `A`: length of the attachment region, unsigned, big-endian. |
| 12 | `J` | JSON region: one JSON text (section 4), then zero to seven space bytes (`0x20`). |
| 12 + `J` | `A` | Attachment region (section 5). |
| 12 + `J` + `A` | 32 | Digest: SHA-256 of bytes 0 to 12 + `J` + `A` − 1, or the authentication code of section 13.2. |

Rules:

1. `12 + J` MUST be a multiple of 8.
2. The frame length, `44 + J + A`, MUST NOT exceed the receiver's bound. `J` MUST NOT exceed 1,048,576.
3. A receiver MUST check the magic, `J`, `A`, and the limits of rule 2 before it reads the rest of the frame.
4. The JSON region MUST start with the byte `{`. It MUST end with the byte `}` and then the fewest space bytes, zero to seven, that make `12 + J` a multiple of 8.
5. A receiver MUST compute the digest and compare it with the digest field before it parses the JSON region. A frame with a different digest is a bad frame.
   Exception: on a pipe pair or a Unix domain socket where no other program can change frames between the two endpoints, an application MAY turn off this comparison for the frames that it receives. It MUST NOT turn it off in an authenticated session (section 13.2).
   The identity of a received frame is then its digest field as received.
   A transcript verifier always makes the comparison (section 10).
6. The identity of a frame is the digest field as 64 lowercase hexadecimal characters. Senders and receivers compute identities from the exact bytes. NCP defines no canonical encoding.

The magic gives the version of the frame format. The member `ncp` of each message (section 6) gives the version of the message rules.

## 4. JSON region

The JSON region MUST contain one JSON text as defined in RFC 8259, encoded in UTF-8 without a byte order mark, whose value is an object, followed only by the padding of section 3, rule 4.
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

A number without a fraction or exponent is an integer. A number with a fraction or an exponent is not an integer, also when its value is whole. Receivers keep the two kinds apart.

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
- `shape` is an array of 0 to 32 integers, each 0 or larger. Elements are in row-major order. The number of elements is 0 if a dimension is 0, and otherwise the exact product of the dimensions; an empty shape is one element.
- `att` is the index of the attachment that holds the elements. Its length MUST equal the number of elements times the element size.
- Each attachment MUST belong to exactly one array of the frame.

Because each attachment starts at a multiple of 8 from the start of the frame, a receiver can read arrays in place.

## 6. Messages

A code is a string of 1 to 64 characters from `a`–`z` and `_`.
An operation name is a string of 1 to 64 characters from `a`–`z`, `0`–`9`, `_`, `.`, and `-` that starts with a letter.
A receiver MUST treat a message with a missing member, an extra member, or a member of the wrong type or format as a bad frame, except for a request of another protocol version (section 6.1).

### 6.1 Request

A request is an object with exactly these members (`att` is optional):

| Member | Value |
| --- | --- |
| `ncp` | The integer 2. A receiver treats a value that is not a non-negative integer as a bad frame. |
| `session` | The session identifier: a version 4 UUID in lowercase hyphenated form. |
| `seq` | The sequence number: 0 for `open`, then 1, 2, 3, and so on. |
| `op` | The operation: an operation name. |
| `ack` | `null` for `open`. Otherwise the identity of the last response that the client accepted with outcome `ok` or `declined`. |
| `body` | Any JSON value. |
| `att` | The attachment lengths (section 5). |

A request of another protocol version is a message whose `ncp` is a non-negative integer other than 2, whose `session` is a session identifier, and whose `seq` is a sequence number. It is not a bad frame, whatever its other members: the owner rejects it with `wrong_protocol` (section 7.3, rule 2), and the response names its `session`, its `seq`, and its identity.

### 6.2 Response

A response is an object with exactly these members (`att` is optional):

| Member | Value |
| --- | --- |
| `ncp` | The integer 2. A receiver treats a value that is not a non-negative integer as a bad frame. |
| `session` | The session of the request, or `null` (see below). |
| `seq` | The sequence number of the request, or `null`. |
| `request` | The identity of the request frame, or `null`. |
| `outcome` | `ok`, `declined`, `rejected`, or `ended` (section 7.4). |
| `code` | `null` if `outcome` is `ok`. Otherwise a code (section 7.5). |
| `body` | Any JSON value for `ok`. An object with optional detail members for the other outcomes. |
| `att` | The attachment lengths (section 5). |

`session`, `seq`, and `request` are all `null` only in a response with outcome `ended` that names no request: the bad-frame response and the shutdown response of the byte-stream binding (section 9.1). Its body binds it to the owner's chain: when the owner holds a session, the body is `{"session": S, "kept": K}`, where `S` is that session and `K` the identity of the owner's kept response; otherwise, the body is an empty object. Every other response names its request with all three.

### 6.3 Stream message

A stream message is an object with exactly these members (`att` is optional):

| Member | Value |
| --- | --- |
| `ncp` | The integer 2. A receiver treats any other value as a bad frame. |
| `stream` | The stream identifier: 1 to 256 characters from `a`–`z`, `A`–`Z`, `0`–`9`, `_`, `.`, `-`, `/`. |
| `seq` | 1 for the first message, then 2, 3, and so on. |
| `prev` | `null` for the first message. Otherwise the identity of the previous message of the stream. |
| `contract` | The identity of the stream's contract (section 11). |
| `body` | Any JSON value. |
| `att` | The attachment lengths (section 5). |

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
   | `features` | Optional. An object of at most 32 members. Each name is a feature name, in the format of an operation name. Each value is an object with the client's parameters for that feature. |

3. Until the owner sends the `open` response, both sides use the bound 65,536.
4. The owner checks the request in this order:
   1. If `ack` is not `null`, or the body is not an object with the members above and their types, it rejects with `body_invalid`.
   2. If the application and the contract do not name one contract of the owner, it rejects with `contract_mismatch`. An owner MAY accept several contracts of its application, for example two versions during an upgrade.
   3. If `bound` is outside the range, it rejects with `bound_unacceptable`.
   4. The owner MAY refuse the session for a reason of its own, such as a limit on open sessions, with the code `refused`.

   After a rejection, the owner stays without a session.
5. Otherwise the owner accepts the session. Its `ok` response has this body:

   | Member | Value |
   | --- | --- |
   | `bound` | The session bound: the smaller of the requested bound and the owner's largest bound. |
   | `application` | The owner's application name. |
   | `contract` | The identity of the contract that the session uses. |
   | `implementation` | The name and version of the owner's NCP implementation. |
   | `nonce` | 32 lowercase hexadecimal characters that the owner chooses at random for this opening. |
   | `features` | An object with the features of the request that the owner enables, each with the owner's parameters. |

   The owner MUST choose each nonce from at least 128 bits of a cryptographically secure random generator. Two openings MUST NOT share a nonce, also across restarts of the owner. An owner therefore MUST NOT restore the state of an opening (section 7.2), for example from a snapshot: after a restart, it holds no session. The identity of the `open` response is the root of the session's hash chain, so different nonces make the chains of two openings disjoint (section 7.7, property 1).
   An owner enables only features that it knows and that the request lists. A client MUST NOT use a feature that the response does not list.
   A client MUST ignore members of this body that it does not know. Later versions can add members.
   A client MUST check that `bound` is from 65,536 to the bound that it requested, that `nonce` has the form above, and that `features`, if present, is an object. Otherwise the session ends, and the `open` request is possibly executed. An owner of an earlier revision, which sends no nonce, therefore opens no session with a client of this revision.
6. After the `open` response, both sides use the session bound for all frames of the session.
7. A client that sends `open` again after a time limit sends the same frame, so that every copy names the same session.
8. An opening is not at most once: a delayed copy of `open` can open the session again after the owner lost it (rule 7.6.4). What an owner does when it accepts `open` must therefore be safe to repeat.

### 7.2 Owner state

An owner keeps, for each session:

- `high`: the sequence number of the last admitted request. It is 0 after `open`.
- `kept`: the response to the last admitted request, with its frame bytes, its identity, and the identity of its request.
- `ended`: true after a kept response with outcome `ended` and after the `ok` response to `close`.

### 7.3 Owner rules

The owner handles one frame of a session at a time, in arrival order, with these steps in this order:

1. If the frame is bad (sections 3 to 6), apply the binding's bad-frame rule (section 9). Stop.
2. If `ncp` is not 2, reject with `wrong_protocol`. Stop.
3. If the owner does not hold the session:
   - If `seq` is 0 and `op` is `open`, apply section 7.1.
   - If `seq` is 0 and `op` is not `open`, reject with `not_open`.
   - If `seq` is greater than 0, respond `ended` with `session_expired`. The owner never served the session, forgot it, or restarted. An earlier owner may have executed the request.

   Stop.
4. If `session` is not the session that the owner holds, reject with `wrong_session`. Stop.
5. If `seq` equals `high` and `kept` exists:
   - If the request identity equals the request identity in `kept`, send the frame bytes of `kept` again. Stop.
   - Otherwise reject with `seq_conflict`. Stop.
6. If `seq` is less than `high`, reject with `seq_stale`. Stop.
7. If `seq` is greater than `high` + 1, reject with `seq_gap`. Stop.
8. If `ended` is true, reject with `session_ended`. Stop.
9. If `ack` is `null`, reject with `ack_missing`. If `ack` differs from the identity of `kept`, reject with `ack_mismatch`. Stop.
10. If `op` is `open`, reject with `already_open`. If the owner stops (section 9.1, rule 9, and section 9.2, rule 9), respond `ended` with `shutdown`, and never admit the request later. Stop.
11. Admit the request: release `kept`, and set `high` to `seq`.
12. Execute the request:
    - For `close`, end the session and respond `ok` with an empty object as body. The owner ignores the body of `close`.
    - For `ncp.ping`, respond `ok` with an empty object as body. The owner does not call the application.
    - If the contract has no such operation, respond `declined` with `unknown_op`.
    - If the application finds the body invalid before it changes any state, respond `declined` with `body_invalid`. The body can say why in its member `detail`.
    - If the application fails while it checks the body, respond `ended` with `owner_failure`.
    - Otherwise call the application. If it returns a result, respond `ok` with the result. If it raises an error, respond `ended` with `owner_failure`.
    - If the JSON region of the `ok` response would exceed 1,048,576 bytes, respond `ended` with `result_too_large` and the body `{"json": J, "limit": 1048576}`, where `J` is the size of the JSON region that the response would need. Otherwise, if the `ok` response would exceed the session bound, respond `ended` with `result_too_large` and the body `{"size": S, "bound": B}`, where `S` is the frame size that the response would need.
13. Keep the response as `kept`. If the outcome is `ended`, or the operation is `close`, set `ended` to true.

A `rejected` response changes no state, and the owner does not keep it.
The owner keeps every response to an admitted request, whatever its outcome. Every copy of an admitted request therefore gets the same response bytes while the request is the last admitted one, and `seq_stale` after that. The owner's answer to a request never changes, also when the application would now judge the body differently.

### 7.4 Outcomes

| Outcome | Meaning | The session | The next request |
| --- | --- | --- | --- |
| `ok` | The owner executed the request once. The body is the result. | Continues, unless the operation was `close`. | `seq` + 1, `ack` the identity of this response. |
| `declined` | The owner admitted the request and did not execute it. It never will. The application state did not change. | Continues. | `seq` + 1, `ack` the identity of this response. |
| `rejected` | The owner did not admit this frame, and nothing changed. | A rejected `open` leaves no session. For any other request, the client ends the session (rule 7.6.4). | After `open`: a corrected `open`. Otherwise none. |
| `ended` | The session cannot continue. The code tells whether the request executed. | Ends. | None. Open a new session if needed. |

### 7.5 Codes

| Code | Outcome | What the owner knows | The client's verdict (section 7.6) |
| --- | --- | --- | --- |
| `wrong_protocol`, `not_open`, `already_open`, `wrong_session`, `seq_gap`, `seq_conflict`, `ack_missing`, `ack_mismatch`, `session_ended` | `rejected` | This frame was not admitted. | For `open`: no session is open. For another request: the session ends, and the request is possibly executed (rule 4). |
| `body_invalid`, `contract_mismatch`, `bound_unacceptable`, `refused` | `rejected`, in reply to `open` | No session was opened in reply to this frame. | No session is open (rule 4). |
| `seq_stale` | `rejected` | Not executed by this frame. An earlier copy may have executed: a delayed copy of an admitted request gets this code once a later request is admitted. | The session ends, and the request is possibly executed (rule 4). |
| `unknown_op`, `body_invalid` | `declined` | Not executed, and never will be. | Not executed (rule 3). The session goes on. |
| `result_too_large` | `ended` | Executed. | Executed (rule 5). |
| `owner_failure` | `ended` | Unknown. | Possibly executed (rule 5). |
| `session_expired` | `ended` | Unknown: the owner does not hold the session. | Possibly executed (rule 5). |
| `shutdown` | `ended` | Not executed: the owner stopped before it admitted the request, and it never admits it. | Not executed. A response that names no request counts only if it binds to the client's chain (rule 2). |
| `bad_frame` | `ended` | Not executed: the owner found the frame bad and executed nothing. | Not executed, if the response binds to the client's chain; otherwise possibly executed (rule 2). |

The code `body_invalid` has two outcomes. It is `rejected` in reply to `open` and `declined` in reply to any other request.

The column "What the owner knows" states what the owner knows about the frame in its current state. An owner that lost a session, by a restart or by expiry, knows nothing about the requests of the lost opening. A client therefore treats a `rejected` response to a request other than `open` as the end of the session, with the request possibly executed (rule 7.6.4). `spec/ncp2-rules.json` holds both columns as data: `executed` and `client`.

Later versions of this specification can add codes. A receiver MUST accept a code that it does not know and act on the outcome. After `rejected`, the frame was not admitted. After `declined`, the request never executes. After `ended`, the request is possibly executed.

### 7.6 Client rules

1. The client sends one request at a time. It keeps the frame bytes of the request until it accepts a response.
2. A response belongs to the request if `ncp` is 2 and `session`, `seq`, and `request` match the request.
   - On the byte-stream binding, any other frame is a protocol error. The session ends, and the request is possibly executed. A response that names no request (section 6.2) also ends the session. The request did not execute only if the response has the code `bad_frame` or `shutdown` and its body names the client's session and, as `kept`, the identity of the response that the request acknowledges. Otherwise the request is possibly executed: such a frame can be replayed from another connection, also when frames are authenticated.
   - On the Zenoh binding, the client ignores any other frame, also a response that names no request.
3. After an `ok` or a `declined` response, the client sets `seq` of its next request to the `seq` of this response plus 1, and `ack` to the identity of this response.
4. After a `rejected` response to `open`, no session is open. The client MAY send the same `open` again, or a corrected `open`; it SHOULD give a corrected `open` a new session identifier, so that a delayed copy of the first `open` cannot open the session with other parameters. A client that follows these rules receives `rejected` for another request only when the owner's state of the session differs from the client's. For example, the owner lost the session and a delayed copy of the `open` request opened it again, or another program sent requests with the client's session identifier. An earlier copy of the request may have executed in a lost opening. After a `rejected` response to a request other than `open`, the client MUST therefore end the session and treat the request as possibly executed.
5. After an `ended` response, the session is over. After `owner_failure`, `session_expired`, or a code that the client does not know, the client MUST treat the request as possibly executed.
6. On a binding that can lose frames (section 9.2), the client MAY send the same request frame again after a time limit. The owner sends the kept response again (rule 7.3.5).
7. If the client cannot get a response, it MUST treat the request as possibly executed and end the session. This applies when the time limit passes after the last copy of the request, and when the binding closes.

### 7.7 Properties

These properties hold under four assumptions:

- **A1.** A receiver detects every changed frame: it compares digests, or the binding delivers the bytes unchanged.
- **A2.** No third party makes frames with valid digests: frames are authenticated (section 13.2), or the binding admits only the two endpoints. Authentication does not prevent the replay of a frame that an endpoint made; the rules therefore bind every response that a client trusts to its request (rule 7.6.2) or to the owner's chain (section 6.2).
- **A3.** No two different frames of the runs share a digest.
- **A4.** No two openings share a nonce: owners draw nonces from a cryptographically secure random generator, and never restore the state of an opening (rule 7.1.5).

Under these assumptions, for every network that loses, repeats, delays, or reorders frames, and with crashes and restarts of the owner and the client and with the expiry of sessions:

1. **At most once.** An owner admits each request at most once. No request with `seq` greater than 0 is admitted by two openings. So no request is executed twice, also across restarts of the owner and the expiry of sessions.
2. **In order.** An owner admits the requests of a session in sequence order, without gaps.
3. **Acknowledged.** An owner admits request `n + 1` only after the client acknowledged response `n` by its identity.
4. **ok is true.** A response that the client accepts as `ok` is the response to its own request, from one execution.
5. **declined is final.** A request that the owner declined never executes. A request that got `shutdown` is never admitted. A stopped owner admits no request.
6. **rejected changes nothing.** A `rejected` response changes no state. Except after `seq_stale`, the opening that rejects a request has not admitted it. A client that follows section 7.6 receives `rejected` for a request other than `open` only after the owner lost the session and a delayed copy of `open` opened it again, or after another program used its session identifier.
7. **The client is told the truth.** Each verdict of a client that follows section 7.6 is true when the client reaches it, and it stays true. The verdict is "executed" after `ok` and `result_too_large`, "not executed" after `declined`, `shutdown`, and `bad_frame`, and "possibly executed" after all other `ended` codes, after `rejected` in reply to a request other than `open`, and after local failures. A response that names no request gives "not executed" only with the code `bad_frame` or `shutdown` and a body that binds it to the client's chain (rule 7.6.2), and "possibly executed" otherwise. At most one request of a session is possibly executed, and it is the last request of the session.
8. **One hash chain.** Each admitted request names the identity of the response before it, and each response names the identity of its request. The identity of the last response commits to every admitted request and response of the session.

[`formal/`](../formal/README.md) states which of these properties the Lean proofs establish, for which part of the system, and under which assumptions. [`model/`](../model/README.md) checks all eight properties against the reference SDKs in every reachable state of bounded runs. Both include restarts of the owner and the expiry of sessions. Neither models a crash of the client: a client that crashes keeps no verdict, and properties 1 to 3, 5, 6, and 8 do not depend on the client.

## 8. Streams

1. A publisher numbers the messages of a stream from 1. It sets `prev` to the identity of its previous message, and `contract` to the identity of the stream's contract.
2. A publisher instance MUST use a stream identifier that no other publisher instance uses, also after a restart. The reference SDKs append `/` and 16 random hexadecimal characters to the name that the application gives.
3. A subscriber keeps, for each stream, the `seq` and the identity of the last message that it accepted, and whether that message ended the stream. A subscriber MAY keep this state for a bounded number of streams. It then forgets the stream that it used least recently, and treats a later message of that stream as a message of a stream without state (rule 6).
4. A subscriber applies a bound to each stream frame. The contract describes the largest frame of each stream type (section 11). NCP does not say which stream type of the contract a message belongs to: the application chooses the bound, for example the largest frame of all the stream types that the subscriber accepts.
5. A subscriber that receives a message with an unknown `contract` MUST NOT accept it. It reports `unknown_contract`. The subscriber applies this rule before rules 6 to 12.
6. If the subscriber has no state for the stream, it accepts the message. If `seq` is 1, it reports `accepted`. If `seq` is greater than 1, it reports `joined`: it knows nothing about the earlier messages.
7. If `seq` is the last accepted `seq` plus 1 and `prev` matches, the subscriber accepts the message and reports `accepted`.
8. If `seq` is larger than the last accepted `seq` plus 1, the subscriber accepts the message and reports `accepted` with the number of lost messages.
9. If `seq` is the last accepted `seq` plus 1 and `prev` does not match, the subscriber MUST NOT accept the message. It reports `broken_chain`.
10. If `seq` is the last accepted `seq` and the identity differs, the subscriber MUST NOT accept the message. It reports `conflict`: two publishers share the identifier, or the message changed.
11. Otherwise, if `seq` is not larger than the last accepted `seq`, the subscriber drops the message as a `repeat`. This includes a message that arrives after a later message of its stream: the subscriber counted it as lost when it accepted the later one, and cannot tell it from a repeat.
12. A message whose body is an object with the member `ncp.end` ends the stream. The subscriber accepts it as rule 6, 7, or 8 says and reports the end. After the end, rules 10 and 11 still apply; instead of rules 7 to 9, the subscriber reports every message with a larger `seq` as a `conflict`.

Streams give no delivery guarantee. Freshness and rate limits belong to the stream's contract.
A subscriber sees the loss of the last messages of a stream only at a later message or at the end message. A publisher whose subscribers must detect such a loss sends messages at least as often as its contract states.
A key (section 13.2) shows that a holder of the key made a message, not that the message is new: anyone can send the messages of an old stream again. A subscriber without state for that stream accepts the first of them as `joined`. An application that must refuse old streams uses a new key for each run, or accepts only the stream identifiers that the publishers of the run announce, for example in an exchange.

## 9. Bindings

### 9.1 Byte-stream binding

The byte-stream binding sends frames back to back over one reliable, ordered byte stream: a pair of pipes, a Unix domain socket, or a TCP connection.

1. One connection carries at most one session. A session belongs to its connection: on another connection, a request of the session meets an owner that does not hold it, and gets the response of rule 7.3.3.
2. A receiver reads the 12-byte header, checks it (section 3), and then reads the rest of the frame.
3. **Bad-frame rule:** if a receiver gets a bad frame, it sends, where it can, a response that names no request (section 6.2), with outcome `ended`, code `bad_frame`, and the body that binds it to its chain, and then closes the connection.
4. On a pipe pair, the owner reads frames from its standard input and writes frames to its standard output. It MUST NOT write anything else to its standard output.
5. An owner that listens on a Unix domain socket SHOULD create it in a directory that only the users of the session can access. On one machine, a Unix domain socket is the preferred connection between programs that the owner does not start.
6. A TCP endpoint MUST set `TCP_NODELAY`. By default, a TCP endpoint MUST listen on and connect to loopback addresses only. Other addresses require an explicit option. On networks that are not trusted, use TLS (section 13.3), a secure tunnel, or the Zenoh binding with TLS.
7. If the connection closes, the session ends. A request without a response is possibly executed.
8. An implementation SHOULD set the send and receive buffers of a socket to at least 1 MiB. Small default buffers, such as the 8 KiB of a Unix domain socket on macOS, multiply the time that a large frame takes.
9. **Shutdown:** an owner MAY stop a session. It then reads no further frame, sends a response that names no request (section 6.2), with outcome `ended`, code `shutdown`, and the body that binds it to its chain, and closes the connection. It MUST have answered every request that it read. A request that the client sent and that has no response was therefore not admitted.
10. **Streams:** one connection, or one file, MAY carry the frames of one or more streams in one direction, back to back. The receiver applies section 8 to each frame. After a bad frame, the receiver closes the connection.

### 9.2 Zenoh binding

The Zenoh binding carries the same frame bytes as Zenoh payloads. It is optional.

1. An owner declares a queryable on `ncp/x/<service>`. A client sends each request frame as the payload of a query to that key. The owner replies with the response frame.
2. A publisher puts stream frames on `ncp/s/<stream-key>`. Subscribers subscribe to that key.
3. **Bad-frame rule:** a receiver drops a bad frame.
4. The client accepts only the reply that matches its request (rule 7.6.2). If no reply arrives in time, it sends the same request frame again.
5. Each owner MUST use its own service key. Service keys and stream keys contain no wildcards.
6. Deployments on networks that are not trusted MUST use TLS with client certificates and Zenoh access control on both sides. The owner's side admits only the clients of the service. The client's side admits only the owner as the one that may declare the queryable and reply on the service key.
7. An owner serves one session for each session identifier. It MAY forget a session that has no request in progress and has sent no request for a time, counted from the owner's last response to it, that the owner documents. The reference servers never forget a session with a request in progress. That time MUST exceed the longest time that a client of the service waits for a response, all copies included. A request of a forgotten session gets the response of rule 7.3.3.
8. An owner SHOULD execute the requests of different sessions independently, so that a long step of one session does not delay the other sessions.
9. **Shutdown:** an owner that stops handles each further frame with rules 7.3.1 to 7.3.9 as usual, so a copy of a kept request gets the kept response, and the other checks reject or respond as they say. It answers an `open` with `rejected` and `refused`. It responds `ended` with `shutdown` only to a request that rule 7.3.10 would otherwise let it admit, and it never admits that request later. It then undeclares the queryable.
10. An owner checks each frame as section 3 says, with its key in an authenticated session (section 13.2), before it reads the message, also to find the session of the frame. A frame of a session that the owner does not hold has the handshake bound of 65,536 bytes: a larger one is a bad frame. The responses that the owner makes without a session, under rule 7.3.2 and rule 7.3.3, carry the key of the owner.

## 10. Transcripts

A transcript records the frames that one program sent and received.

### 10.1 Format

A transcript file starts with the 8 bytes `4E 43 50 54 00 00 00 02` (`"NCPT"` and version 2).
Then follows the header: a 4-byte big-endian length `L` and `L` bytes of JSON text, at most 4096, with the rules of section 4. Its value is an object with these members:

| Member | Value |
| --- | --- |
| `recorder` | A name of the program that wrote the transcript, 0 to 256 characters. |
| `implementation` | The name and version of the NCP implementation that wrote it. |
| `started` | The time at which the recorder started, in UTC, as an RFC 3339 string with nanoseconds, for example `2026-11-13T09:30:00.123456789Z`. |
| `chain` | `sha256` or `hmac-sha256` (section 13.2). |

Then follow the records. Each record has this layout:

| Size | Field |
| --- | --- |
| 1 | Kind: 1 = sent, 2 = received, 3 = end. |
| 8 | Time in nanoseconds since the recorder started, from a monotonic clock, unsigned, big-endian. |
| 4 | Frame length, unsigned, big-endian. 0 for an end record. |
| frame length | The frame bytes. |
| 32 | Chain value. |

The chain value of the first record uses `c₀ = D(magic ‖ L ‖ header)`. The chain value of record `i` is `cᵢ = D(cᵢ₋₁ ‖ kind ‖ time ‖ length ‖ d)`, where `d` is the last 32 bytes of the record's frame bytes: the digest field of a frame. A record of fewer than 32 bytes, which cannot be a frame, uses all its bytes as `d`. For an end record, `d` is the number of earlier records as 8 bytes, unsigned, big-endian. `D` is SHA-256, or HMAC-SHA-256 with the session key when `chain` is `hmac-sha256`.
An end record is the last record of a transcript that its recorder closed.

### 10.2 Recording

A recorder MUST record a frame that it sends before it sends the frame, and a frame that it receives after it has received the whole frame.
A transcript therefore holds every request that a peer may have executed, also when the recorder stops while it sends. A frame whose sending failed stays recorded as sent.

### 10.3 Verification

A verifier MUST check, and report each failure:

- the digest of every frame, and the chain value of every record;
- for each exchange session, the direction of every frame: a client sends requests and receives responses, and an owner receives requests and sends responses;
- in a client's transcript, that the client sends its requests in order: each `seq` one more than that of the last request that the owner admitted, with `ack` naming the response to it (property 7.7.8);
- in an owner's transcript, that the owner admits no request out of that order: its response to such a request is `rejected`, or `ended` with `session_expired` or `shutdown`. A received request out of order is not a failure by itself, because the client sent it;
- that two responses to one request are the same bytes, unless one of them is `rejected`, or `ended` with `session_expired` or `shutdown`: an owner sends a kept response again byte for byte (section 7.3, rule 5);
- that the times do not decrease;
- the streams of section 8, with any contract;
- frames that are not NCP messages.

A verifier that is given a key MUST report a failure for a transcript that is not authenticated with that key: a transcript of version 1, or one whose `chain` is not `hmac-sha256`.

A verifier reports a record that ends before its length as a truncated transcript and verifies every record before it.
A session is **complete** if the transcript has its `open` request, a response to every request, and the `ok` response to `close`.
A complete, verified transcript is internally consistent. It shows which frames the recorder sent and received, and in which order, as far as the file can be trusted. Without a key, anyone can write a transcript that verifies. A transcript with `hmac-sha256` verifies only with the key (section 13.2).

A verifier SHOULD accept transcripts of version 1, whose files start with `4E 43 50 54 00 00 00 01`, have no header, and have records without chain values.

## 11. Contracts

A contract is a JSON document that an application publishes. Its identity is the SHA-256 digest of its exact bytes, as 64 lowercase hexadecimal characters.
The document MUST meet the rules of section 4. Its value MUST be an object with these members, and it MAY have others:

| Member | Value |
| --- | --- |
| `ncp_contract` | The integer 1. |
| `application` | The application name, 1 to 128 characters. |
| `version` | The contract version, 1 to 128 characters. |
| `operations` | An object. Each member names one exchange operation and describes its request body and result. |
| `streams` | An object. Each member names one stream type and describes its body, rate, freshness, and largest frame. |

Rules:

1. Operation names and stream type names have the format of an operation name (section 6). Operation names MUST NOT be `open` or `close`, and MUST NOT start with `ncp.`.
2. The value of each operation and each stream type is an object. The application describes its members. NCP reads only the member `ncp.schema`.
3. The member `ncp.schema` of an operation is an object with the optional members `request` and `result`, each a schema (section 11.1). The member `ncp.schema` of a stream type is an object with the optional member `body`, a schema.
4. An owner MUST decline a request whose body does not match the operation's `request` schema, with `body_invalid`, before it calls the application. A client MAY check a result against the `result` schema.
5. NCP compares contract identities. It does not compare the descriptions.

### 11.1 Schemas

A schema is an object with only the members of this table. A contract with another member in a schema is not a valid contract.

| Member | Meaning |
| --- | --- |
| `type` | One of `null`, `boolean`, `integer`, `number`, `string`, `array`, `object`, or an array of them. `integer` matches a number without a fraction or exponent (section 4). `number` matches every number. |
| `enum` | An array of values. The value MUST equal one of them. |
| `const` | A value. The value MUST equal it. |
| `minimum`, `maximum` | Numbers. A number MUST be at least, or at most, this value. |
| `exclusiveMinimum`, `exclusiveMaximum` | Numbers. A number MUST be greater, or less, than this value. |
| `minLength`, `maxLength` | Integers. A string MUST have at least, or at most, this number of Unicode code points. |
| `items` | A schema. Every element of an array MUST match it. |
| `minItems`, `maxItems` | Integers. An array MUST have at least, or at most, this number of elements. |
| `properties` | An object of schemas. Each member of the value with one of these names MUST match its schema. |
| `required` | An array of member names. The value MUST have each of these members. |
| `additionalProperties` | `false`, or a schema. With `false`, the value MUST NOT have members outside `properties`. With a schema, each such member MUST match it. |
| `ncp.array` | An object with the members `dtype`, a dtype or an array of dtypes, and `shape`, an array of integers or `null`. The value MUST be an array (section 5) with one of these dtypes and a shape of the same length, equal at each integer. |
| `description`, `title` | Strings. NCP ignores them. |

Two values are equal if they have the same JSON type and the same value. An integer and a number that is not an integer are never equal. The members of an object have no order.
`type`, `enum`, `const`, and `ncp.array` apply to every value. Every other keyword applies only to values of its kind. For example, `minimum` does not constrain a string, and `required` does not constrain an array of section 5.

## 12. Limits

| Limit | Value |
| --- | --- |
| Bound before `open` completes | 65,536 bytes |
| Largest session bound | 67,108,864 bytes |
| Default session bound in the reference SDKs | 1,048,576 bytes |
| JSON region | 1,048,576 bytes |
| JSON nesting | 64 levels |
| Integer magnitude | 2^53 − 1 |
| Attachments in a frame | 1024 |
| Operation name, feature name, code | 64 characters |
| Stream identifier | 256 characters |
| Features in an `open` request | 32 |
| Member `run` of an `open` request | 256 characters |
| Member `detail` of a response, as the reference owners write it | 256 characters |
| Dimensions of an array shape | 32 |
| Transcript header | 4096 bytes |

## 13. Security

### 13.1 What NCP protects

| Binding | Who can read frames | Who can send frames | What protects the frames |
| --- | --- | --- | --- |
| Pipe pair | The two processes, and programs of the same user that can attach to them | The two processes | Operating-system access control |
| Unix domain socket | The two processes | Every program that may open the socket file | The file's permissions and its directory |
| TCP, loopback | Programs on the same computer | Programs on the same computer | Only the loopback interface. Use TLS or authenticated frames when other users share the computer. |
| TCP, other networks | Every program on the path, unless TLS is used | Every program on the path, unless TLS or authenticated frames are used | TLS with client certificates (section 13.3) |
| Zenoh | Every Zenoh router on the path, unless the links use TLS | Every Zenoh session that access control admits | TLS on each link, access control on both sides (rule 9.2.6), and authenticated frames for protection from end to end |

- Without authenticated frames, the digest protects against accidental damage only. A peer that can write to the binding can make frames with valid digests.
- Bounds limit memory. Receivers check lengths before they allocate.
- If an application turns off the digest comparison (section 3, rule 5), damage between the two endpoints is not detected while the session runs. Identities, the hash chain, and transcript verification do not change.
- Applications that need authority for physical actions add their own signed authority in their contract. NCP does not decide who may move a machine.

### 13.2 Authenticated frames

Two endpoints that share a secret key `K` of at least 32 bytes MAY authenticate every frame of a binding:

1. The digest field of every frame holds HMAC-SHA-256 with the key `K` over the bytes before it (RFC 2104), instead of SHA-256.
2. A receiver configured with `K` verifies every frame with `K`. It treats every other frame as a bad frame. It MUST NOT turn off the comparison, and it MUST compare authentication codes in a time that does not depend on where they differ.
3. Identities, acknowledgements, and hash chains use the authentication codes as the identities of the frames.
4. A transcript of authenticated frames uses `hmac-sha256` for its chain, with the same key. Only a holder of `K` can verify it, and only a holder of `K` can make one that verifies.
5. Each endpoint gets `K` out of band, for example from a file that only its user can read. NCP does not exchange keys.

Authenticated frames protect from end to end against every party without the key, also across Zenoh routers. They do not prevent the replay of a frame that an endpoint made: the rules bind each response that a client trusts to its request or to the owner's chain, and a request replayed to another session or opening fails the checks of rules 7.3.4 to 7.3.9. They do not hide the content of frames. A sender and a receiver of a session cannot prove to a third party which of them made a frame, because both hold `K`.

### 13.3 TLS for TCP

A TCP endpoint MAY use TLS 1.3 with certificates on both sides. The server MUST require a client certificate signed by the authority that the deployment names. The client MUST check the server's certificate and name. The frames inside TLS are unchanged.

## 14. Conformance

An implementation conforms if it passes the vectors in [`conformance/`](../conformance/README.md) for the parts that it implements: frames, arrays, owner rules, client rules, streams, transcripts, contracts and schemas, and authenticated frames. The bindings and the profiles have no vectors yet; the tests of the SDKs check them.
The vectors give exact inputs and the expected outcome, code, verdict, and state. [`conformance/requirements.json`](../conformance/requirements.json) maps each MUST and MUST NOT of this document to the vectors that test it.
The command `python -m ncp conformance` runs the vectors against another implementation's decoder and owner programs.

## 15. Reserved names

These names are reserved for this specification, its later versions, and NCP profiles. Applications MUST NOT use them with other meanings.

1. Operation names and feature names that start with `ncp.`. This document defines `ncp.ping` (rule 7.3.12).
2. Object members, at any level of a body or a contract, whose names start with `ncp.`. This document defines `ncp.array` (section 5), `ncp.end` (section 8), and `ncp.schema` (section 11).

## 16. Threads, processes, and clusters (informative)

NCP needs no change for parallel programs. These patterns use it as specified:

- **Threads.** One session handles one request at a time. A program can run many sessions in parallel threads, one thread for each session at a time. A simulator can use any number of threads inside one request.
- **Many sessions.** A host that couples many programs, for example one controller for each agent, sends one request to each session and waits for all responses before the next step. The reference SDKs provide this as one call, which sends every request before it reads the first response, so that the programs work at the same time. Sessions are independent, so a slow or ended session does not change the others.
- **Rank-0 owner.** An MPI-parallel simulator, such as NEST with MPI, runs the owner in rank 0. Rank 0 passes each request to all ranks with an MPI broadcast, all ranks execute it, and rank 0 collects the result with an MPI gather before it responds. The client sees one session.
- **One session for each rank.** Each rank runs its own owner, usually over TCP. The client sends the requests and combines the results. This spreads the data over several connections.
- **Two parallel simulators.** To exchange data between the ranks of two MPI-parallel simulators inside one cluster job, MUSIC or a direct MPI coupling is the better tool. NCP then connects that job to programs outside it, such as a body, a monitor, or a recorder.
- **Nodes.** Between nodes, use the byte-stream binding over TCP with the explicit option for cluster networks and TLS where the network is not trusted, or the Zenoh binding. Each request costs one network round trip.

## 17. Profiles

A profile adds rules for one kind of application. It changes nothing in this document.

| Profile | Purpose |
| --- | --- |
| [Rounds](NCP-2-ROUNDS.md) | One owner applies the requests of many agents in rounds, in a fixed order, and tells each agent which requests each round applied. |
| [Lockstep](NCP-2-LOCKSTEP.md) | Each step names the tick that it advances to and the state that it answers. A client that lost a session learns from a new session whether its last step ran. |

## 18. When not to use NCP (informative)

- Inside one process: call the function.
- Between the ranks of one MPI job: use MPI or MUSIC.
- For fan-out of high-rate data to many subscribers without the need to detect changes: use a publish and subscribe system directly.
- For objects larger than 64 MiB: send them out of band and put their digest in a message.
- When a typed interface in many languages matters more than a checked record: gRPC or ROS 2 services.
- For hard real time: NCP gives no time guarantee.

## 19. Errata

None yet.
