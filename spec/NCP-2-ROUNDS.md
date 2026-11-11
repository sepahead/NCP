# NCP 2 profile: rounds

Status: a profile of NCP 2.0, final, 11 November 2026. The Python SDK 2.0.0 implements it.
This document is normative. The key words MUST, MUST NOT, SHOULD, SHOULD NOT, and MAY are to be interpreted as described in RFC 2119 and RFC 8174 when, and only when, they appear in all capitals.
It builds on the [NCP 2 specification](NCP-2.md) and changes nothing in it. The Python SDK implements it as `ncp.Rounds` (owner) and `ncp.RoundRecord` (client check).

## 1. Purpose

One owner, such as a simulated world, serves many agents, each in its own session (specification, section 16).
In each round, every agent sends one request. The owner applies the requests of a round together, in a fixed order, and tells every agent which requests the round applied.
The result of a round then depends on its requests and not on the order in which they arrived, and every agent can check that its own request was applied, and with which others.

## 2. Terms

| Term | Meaning |
| --- | --- |
| Member | A name of 1 to 128 characters from a list that the owner fixes when it starts. The order of the list is the member order. |
| Round | A step of the owner. Rounds are numbered 1, 2, 3, and so on. |
| Round operation | The operation of the contract that the owner serves in rounds. |
| Deadline | A duration that the owner fixes when it starts. |

## 3. Requests

1. The body of a request of the round operation MUST be an object with the member `ncp.round`: an object with exactly the members `agent`, the name of a member, and `round`, the number of a round. The other members of the body belong to the application.
2. A client sends round K + 1 only after the response to its request for round K, as the specification requires for any two requests of a session.

## 4. Owner rules

The owner keeps the number of the last round that closed (0 at the start), the set of excluded members, and, for each member, the session that the member is bound to, if any.

1. The owner rejects a request of the round operation with `body_invalid` (specification 7.3, rule 11) if any of these holds:
   1. the body has no `ncp.round` member as section 3 defines it;
   2. `agent` is not a member;
   3. the session is bound to another member;
   4. the member is bound to another session;
   5. the member is excluded;
   6. `round` is not the number of the last closed round plus 1;
   7. an earlier round failed (rule 7).

   The rejection body SHOULD say which of these held, in its `detail` member.
2. Otherwise the owner accepts the request: it binds the member to the session, if the member was not bound, and adds the request to the round. A round opens when the owner accepts its first request.
3. A round closes when it has a request of every member that is not excluded, or when the deadline has passed since it opened, whichever comes first. A request that the owner accepted belongs to its round: the owner MUST NOT close a round between accepting a request and adding it.
4. When round K closes, every member that is not excluded and has no request in round K is excluded from every later round.
5. The owner then applies the requests of round K once, in member order, and responds to each of them with `ok`. The body of each response is an object: the application's result for that member, with the member `ncp.round_record`:

   | Member | Value |
   | --- | --- |
   | `round` | K. |
   | `agents` | The names of the members whose requests round K applied, in member order. |
   | `requests` | An array (specification, section 5) of dtype `u8` and shape `[n, 32]`, where n is the length of `agents`. Row i is the identity of the request of `agents[i]`, as 32 bytes. |
   | `missing` | The names of the members that rule 4 excluded when round K closed, in member order. |

6. Every response of round K carries the same record.
7. If the application fails to apply round K, the owner responds `ended` with `owner_failure` to every request of round K, and rule 1.7 rejects every later request of the round operation.

## 5. Client rules

1. After an `ok` response to a request of the round operation, a client MUST check that `agents` in `ncp.round_record` lists its member, and that the same row of `requests` holds the identity of its request. If not, the client MUST treat the response as a protocol error.
2. A client whose request was rejected because its member is excluded can expect no later round to apply a request of that member.

## 6. Properties and limits

- **Order.** The inputs of round K are its requests in member order. If the application applies them deterministically, the result of round K does not depend on the order in which the requests arrived.
- **Agreement.** Every agent of round K receives the same record. Identities are SHA-256 digests of exact frames, so the record names exactly the requests that the round applied. With the transcripts of the sessions (specification, section 10), anyone can check that the agents received the same record and that each listed request is the one that its agent sent.
- **Liveness.** A member that sends nothing delays the other members once, by at most the deadline. From the next round on, no round waits for it.
- **Timing.** Whether a late request still enters a round depends on time. The records say which requests each round applied, so a run can be replayed from its records, but two runs with different timing can apply different requests.
- **No rejoining.** An excluded member cannot take part again while the owner runs. A member that closes its session is excluded when the next round closes.
- **Size.** The record grows with the number of members: 32 bytes and the name for each applied request. The session bound (specification, section 7.1) must hold it.
- **Evidence.** This profile is tested in the Python SDK. It is neither model checked nor proved.

## 7. Example

A request of round 7 and the response to it, with three members, one of which sent nothing in time:

```text
request body:  {"ncp.round": {"agent": "drone-2", "round": 7}, "thrust": [0.1, 0.0, 9.8]}
response body: {"position": [1.0, 2.0, 3.5],
                "ncp.round_record": {"round": 7, "agents": ["drone-1", "drone-2"],
                                     "requests": {"ncp.array": {"dtype": "u8", "shape": [2, 32], "att": 0}},
                                     "missing": ["drone-3"]}}
```
