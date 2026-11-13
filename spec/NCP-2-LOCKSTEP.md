# NCP 2 profile: lockstep

Status: a profile of NCP 2.0, release candidate, revision 1 of 13 November 2026.
This document is normative. The key words MUST, MUST NOT, SHOULD, SHOULD NOT, and MAY are to be interpreted as described in RFC 2119 and RFC 8174 when, and only when, they appear in all capitals.
It builds on the [NCP 2 specification](NCP-2.md) and changes nothing in it. The Python SDK implements it as `ncp.Lockstep` (owner) and `ncp.LockstepClient` (client), and the Rust SDK as `ncp::Lockstep` and `ncp::LockstepClient`.

## 1. Purpose

A simulation step changes state that outlives the session: the world advances by one tick for each step.
NCP 2 tells a client whether its last request executed. But if a session ends with its last step possibly executed, for example because the connection broke or a time limit passed, the session cannot tell the client whether the world advanced.
This profile numbers the steps of the owner's state with ticks that outlive sessions. The `open` response of a new session gives the current tick, so the client learns whether its last step ran, and can send it again if it did not.

## 2. Terms

| Term | Meaning |
| --- | --- |
| Tick | The number of lockstep steps that the owner's state has applied. The owner names the tick of its state when it starts, 0 by default. |
| State digest | A string of 1 to 128 characters that the application derives from its state after each step, or `null`. Equal states give equal digests. |
| Lockstep operation | An operation of the contract that the owner serves under this profile. |

## 3. Feature

1. A client asks for the profile with the feature `ncp.lockstep` and an empty object as its parameters in its `open` request (specification, section 7.1).
2. An owner that serves the profile enables the feature with the parameters `{"tick": T, "state": S}`: the tick and the state digest of its state when it accepts the `open`.
3. A client MUST NOT send a lockstep step in a session whose `open` response does not enable the feature.

## 4. Requests

1. The body of a request of a lockstep operation MUST be an object with the member `ncp.tick`: an object with exactly the members `tick`, the tick that the step advances to, and `state`, the state digest that the step answers.
2. A client sets `tick` to the last tick that it knows plus 1, and `state` to the last state digest that it knows.

## 5. Owner rules

The owner keeps one tick and one state digest for its state, across all sessions.

1. The owner declines a request of a lockstep operation with `body_invalid` (specification, section 7.3, rule 12) if the body has no `ncp.tick` member as section 4 defines it, if `tick` is not the owner's tick plus 1, or if `state` is not the owner's state digest. The request never executes. The body of the response SHOULD say which check failed, in its member `detail`.
2. Otherwise the owner executes the step. From the check of rule 1 to the end of the execution, the owner MUST NOT execute another lockstep step of any session.
3. After the step, the owner sets its tick to `tick` and its state digest to the application's digest of the new state. The body of the `ok` response is an object: the application's result, with the member `ncp.tick` set to `{"tick": T, "state": S}`, the new tick and the new state digest.
4. Operations that are not lockstep operations do not change the tick.

## 6. Client rules

1. After an `ok` response to a step, the client MUST check that `ncp.tick` names the tick of its request. The client then knows the owner's tick and state digest.
2. After a `declined` response, the step did not run, and it never will.
3. **Recovery.** If a step is possibly executed (specification, section 7.7, property 7), the client opens a new session with the feature.
   - If the `open` response names the tick of the step, the step ran.
   - If it names the tick of the step minus 1, the step did not run. The client can send it again.
   - Any other tick means that the owner's state changed in another way, for example by another client. The client MUST then treat the step as possibly executed.

## 7. Properties and limits

- **One verdict for each step.** If the owner keeps its tick and state while the client recovers, recovery turns every step that is possibly executed into a step that ran or did not run.
- **One stepping client.** If several clients step the same owner, one client's recovery can find another client's tick, and rule 6.3 then gives no verdict. Use one stepping client, or the [rounds profile](NCP-2-ROUNDS.md).
- **Restarts.** The verdict describes the owner's current state. An owner that restarts without its tick and state starts again at its initial tick. A step that ran before the restart then shows as "did not run", because its effect is not in the current state. If a step has effects outside the owner's state, such as the motion of an actuator, this verdict does not say whether those effects happened.
- **Evidence.** Both SDKs test this profile (`LockstepTests` in `python/tests/test_ncp.py`, and `rust/tests/sessions.rs`). It is neither model checked nor proved.

## 8. Example

```text
open request body:   {"application": "world", "contract": "…", "bound": 1048576,
                      "features": {"ncp.lockstep": {}}}
open response body:  {"bound": 1048576, "application": "world", "contract": "…",
                      "implementation": "…", "nonce": "…",
                      "features": {"ncp.lockstep": {"tick": 41, "state": "9f2c"}}}
step request body:   {"dt_ms": 10, "ncp.tick": {"tick": 42, "state": "9f2c"}}
step response body:  {"observation": [0.1, 0.2], "ncp.tick": {"tick": 42, "state": "77ab"}}
```
