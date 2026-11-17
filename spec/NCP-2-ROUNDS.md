# NCP 2 profile: rounds

Status: a profile of NCP 2.0, release candidate, revision 3 of 17 November 2026. Section 9 lists the changes of each revision. The profile is provisional: section 7 names the design work that remains before a consumer depends on it.
This document is normative. The key words MUST, MUST NOT, SHOULD, SHOULD NOT, and MAY are to be interpreted as described in RFC 2119 and RFC 8174 when, and only when, they appear in all capitals.
It builds on revision 7 of the [NCP 2 specification](NCP-2.md) and changes nothing in it. The Python SDK implements it as `ncp.Rounds` (owner), `ncp.RoundRecord` (client check), and `ncp.rounds.report`.

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
| History identity | 32 lowercase hexadecimal characters that the owner draws from at least 128 bits of a cryptographically secure random generator when it starts. |

## 3. Feature

1. A client asks for the profile with the feature `ncp.rounds` and the parameters `{"rev": [3]}` in its `open` request: the revisions of this profile that it speaks (specification, section 17, rule 1). An owner reads only the member `rev` of these parameters. An owner of this revision enables the feature only if `rev` is an array that has the integer 3.
2. An owner that serves the profile enables the feature with the parameters `{"rev": 3, "closed": K, "history": H}`: the last round that closed when the owner answered, and its history identity. Accepting an `open` changes no state of the profile (specification, rule 7.1.8).
3. A client MUST NOT send a request of the round operation in a session whose `open` response does not enable the feature with `rev` 3 and these members.

## 4. Requests

1. The body of a request of the round operation MUST be an object with the member `ncp.round`: an object with exactly the members `agent`, a string, and `round`, the number of a round: an integer from 1. The other members of the body belong to the application.
2. A client sends round K + 1 only after the response to its request for round K, as the specification requires for any two requests of a session.

## 5. Owner rules

The owner keeps the number of the last round that closed (0 at the start), the set of excluded members, with the round that each one missed, and, for each member, the session that the member is bound to, if any.

1. The owner declines a request of the round operation (specification, section 7.3, rule 12) for the first of these checks that holds, with its code, its reason, and its facts in the member `ncp.rounds`:

   | Check | Code | `ncp.reason` | `ncp.rounds` |
   | --- | --- | --- | --- |
   | 1. The session did not enable the feature (rule 3.3). | `body_invalid` | `ncp.rounds.feature` | none |
   | 2. The body has no `ncp.round` member as rule 4.1 defines it. | `body_invalid` | none | none |
   | 3. `agent` is not a member. | `body_invalid` | `ncp.rounds.member` | none |
   | 4. An earlier round K failed (rule 8). | `conflict` | `ncp.rounds.stopped` | `{"failed": K}` |
   | 5. The session is bound to another member. | `conflict` | `ncp.rounds.bound` | none |
   | 6. The member is excluded: it missed round K. | `conflict` | `ncp.rounds.excluded` | `{"missed": K}` |
   | 7. The member is bound to another session. | `conflict` | `ncp.rounds.bound` | none |
   | 8. `round` is not the number of the last closed round K plus 1. | `conflict` | `ncp.rounds.round` | `{"next": K + 1}` |
   | 9. The member already has a request in the open round. | `conflict` | `ncp.rounds.duplicate` | none |

   A declined request never executes, and the session goes on. The body of the response SHOULD say which check held, in its member `detail`. A client acts on the code, the reason, and the facts, not on `detail` (specification, rule 7.6.8).
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
7. When the session of a member ends, the member is no longer bound. A new session can bind it, unless the member is excluded.
8. If the application fails to apply round K, the owner responds `ended` with `owner_failure` to every request of round K, and rule 1 declines every later request of the round operation.
9. **Restart.** The state of this rule list outlives sessions but not the owner: an owner that restarts starts at round 0, with no excluded member and no bound member, and with a new history identity. A client that sees another history identity in a report knows that the rounds started again.

The owner MUST be able to accept requests of other sessions while requests of the open round wait for it to close. Serve each session in its own thread or task, as the Unix domain socket, TCP, and Zenoh servers of the reference SDKs do.

## 6. Client rules

1. After an `ok` response to a request of the round operation, a client MUST check that `agents` in `ncp.round_record` lists its member, and that the same row of `requests` holds the identity of its request. If not, the client MUST treat the response as a protocol error.
2. A client whose request was declined with the reason `ncp.rounds.excluded` can expect no later round to apply a request of that member while the history identity stays the same.
3. After the reason `ncp.rounds.round`, the client MAY send the request again for the round of the facts, `next`.

## 7. Properties and limits

- **Order.** The inputs of round K are its requests in member order. If the application applies them deterministically, the result of round K does not depend on the order in which the requests arrived.
- **Agreement.** Every agent of round K receives the same record. Identities are SHA-256 digests of exact frames, so the record names exactly the requests that the round applied. With the transcripts of the sessions (specification, section 10), anyone who can verify them can check that the agents received the same record and that each listed request is the one that its agent sent: anyone for frames with digests, and only a holder of the key for authenticated frames (specification, section 13.2).
- **Liveness.** A member that sends nothing delays the other members once, by at most the deadline. From the next round on, no round waits for it.
- **Timing.** Whether a late request still enters a round depends on time. The records say which requests each round applied, so a run can be replayed from its records, but two runs with different timing can apply different requests.
- **New sessions, no rejoining.** A member whose session ends can continue in a new session, if it sends its next request before the round closes without it. An excluded member cannot take part again while the owner runs.
- **Size.** The record grows with the number of members: 32 bytes and the name for each applied request. The session bound (specification, section 7.1) must hold it.
- **No recovery yet.** A member whose response was lost learns from a new session the last round that closed, not whether its request was applied, and it does not get its result. The rounds stop for ever after a failed step. Members bind by the first claim, under one key. These are the design work of a later revision, before a consumer depends on the profile.
- **Time limits.** A request waits in the owner until its round closes. A client's time limit for a request of the round operation MUST exceed the deadline and the time of a step; otherwise it ends a session whose request is still in the round.
- **Evidence.** The Python SDK tests this profile (`python/tests/test_rounds.py`). It is neither model checked nor proved.

## 8. Example

A request of round 7 and the response to it, with three members, one of which sent nothing in time:

```text
open features: {"ncp.rounds": {"rev": [3]}}   reported: {"ncp.rounds": {"rev": 3, "closed": 6, "history": "8c1d…"}}
request body:  {"ncp.round": {"agent": "drone-2", "round": 7}, "thrust": [0.1, 0.0, 9.8]}
response body: {"position": [1.0, 2.0, 3.5],
                "ncp.round_record": {"round": 7, "agents": ["drone-1", "drone-2"],
                                     "requests": {"ncp.array": {"dtype": "u8", "shape": [2, 32], "att": 0}},
                                     "missing": ["drone-3"]}}
```

A request for round 9 while round 7 is open gets `declined` with `conflict` and the body `{"detail": "round: round 9 is not open; the next round is 7", "ncp.reason": "ncp.rounds.round", "ncp.rounds": {"next": 7}}`.

## 9. Changes

### 9.1 Revision 3 (17 November 2026)

An advisory design review found that the profile had no feature, no revision on the wire, no reasons that a program can read, and no rule for a restart.

- Section 3: the feature `ncp.rounds`, its revision, and a report of the last closed round and the history identity.
- Rule 5.1: the order of the checks, the code `conflict` for a state that does not permit the request, the reasons `ncp.rounds.*`, and their facts, from revision 7 of the specification.
- Rule 5.9: what a restart does.
- Section 7: the limits that remain, and the client's time limit.

### 9.2 Revision 2 (13 November 2026)

Revision 2 follows revision 3 of the specification: a request that breaks a rule of this profile is declined, not rejected, and a member whose session ends can take a new session.
