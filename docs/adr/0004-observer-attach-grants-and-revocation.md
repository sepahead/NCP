# ADR-004 — Attach observers with bounded grants and revocation

- Status: `PROPOSED`
- Task: `B01`
- Candidate: unreleased, release-blocked `1.0.0-rc.1`
- Normative effect while proposed: none
- Required reviewers: Prisoma owner, Galadriel owner, security reviewer

## Context

Galadriel and Prisoma need read-only access to live observations and command
dispositions. Current consumers cannot securely infer a live server-issued
session generation, negotiated contract, streams, or permitted channels from the
first frame. Traffic cannot choose its own authorization context, and a generic
session description can expose private topology.

## Proposed decision

NCP shall define an authenticated observer lifecycle:

- `AttachObserver` requests access to one already-live typed session;
- `ObserverAttached` returns a body/service-issued descriptor plus a bounded
  read-only grant;
- `RenewObserverGrant`, `DetachObserver`, and body-issued revocation provide
  explicit lifecycle and receipts.

The descriptor binds:

- exact requester and responder principals;
- session kind, logical session ID, and exact `SessionRef.generation`;
- stable-core, release/corpus diagnostics, transcript, security-state, and
  applicable plant-profile digests;
- permitted planes, routes, message classes, channels, extensions, and history
  window;
- declared stream descriptors and current publisher identities;
- finite grant ID, issue/expiry times, receiver-local deadline policy, and
  revocation epoch;
- privacy/redaction policy and descriptor digest; and
- operation context and body/service receipt.

The observer principal can subscribe or query only within the exact grant.
Observer grants never authorize publish, command, ESTOP, lifecycle mutation,
authority operations, dispositions, stream declaration, or extension assessment.

Galadriel's optional assessment producer uses a different principal, credentials,
manifest, route, and process boundary under ADR-008/011. Observer credentials
cannot be upgraded or reused.

## Rejected alternatives

- Learn the session generation from the first data frame.
- Allow unrestricted fleet/session wildcard subscription after TLS.
- Return descriptors without access control or privacy filtering.
- Use the same Galadriel credential for observation and assessment.
- Treat an expired grant as a temporary warning while continuing delivery.

## Illustrative wire example

```json
{
  "ncp_version": "1.0",
  "kind": "attach_observer",
  "session_id": "plant-alpha",
  "requested_planes": [
    "observation"
  ],
  "requested_channels": [
    "pose_position"
  ],
  "identity": {
    "principal_id": "prisoma-observer-a",
    "entity_id": "prisoma-capture-a",
    "role": "observer",
    "plane": "observation"
  },
  "operation_id": "2b8f8e42-6ad5-4d4e-8eb4-d0e814182fc1"
}
```

## Invalid or hostile example

```json
{
  "ncp_version": "1.0",
  "kind": "attach_observer",
  "session_id": "plant-alpha",
  "requested_planes": [
    "action"
  ],
  "requested_channels": [
    "*"
  ]
}
```

Unknown, wildcarded, action-plane, or unauthenticated requests reject without
revealing a descriptor.

## Actors and state transitions

`DETACHED -> ATTACHING -> ATTACHED -> RENEWING -> ATTACHED -> REVOKED/EXPIRED
-> DETACHED`.

Revocation, expiry, session-generation retirement, security-state change,
privacy-policy change, or descriptor mismatch terminates delivery. Reattachment
is a new authenticated operation and never restores an old grant implicitly.

## Bounds and resource behavior

Requests, descriptor fields, route/channel/stream counts, history window, grant
duration, concurrent observers, queue depth, retained bytes, query size, and
diagnostics are finite. Observer queues are separate from control/action queues.
Slow or absent observers cause explicit observer gaps or detachment, never
control backpressure.

## Threat and hazard analysis

This decision prevents first-frame authorization, topology disclosure, observer
credential escalation, stale-session capture, and observer-induced control
blocking. Read access can still expose sensitive plant or research data, so
privacy filtering, retention, least privilege, audit, and incident revocation
remain deployment obligations.

## Formal properties

- No observer operation changes plant/session authority state.
- Every delivered frame matches one live unexpired grant and descriptor.
- Grant scope is a subset of the authenticated manifest scope.
- Revocation or generation retirement prevents later delivery.
- Observer queue state cannot block action/control progress.

## Migration

Galadriel and Prisoma add optional native-1.0 observer adapters only after the
provider contract is implemented and pinned. Existing raw subscriptions remain
untrusted migration input and cannot receive native role qualification.

## Operational recovery

After restart, consumers reattach and compare exact descriptor identity. Gaps are
recorded; they are never filled or interpolated. A body that cannot restore
grant/revocation state retires grants and requires reattachment.

## Compatibility and rollback

Unknown attach messages fail on the old candidate. Rollback uses the last
complete provider/consumer pair and disables the observer adapter; it does not
re-enable raw wildcard trust.

## Open questions

Exact privacy labels and history-query limits are registry inputs for B03/N02.
They may restrict access further but cannot grant mutation or allow first-frame
attachment.

## Ten-lens review

1. Semantics: attach, descriptor, grant, and data are separate.
2. Security: exact verified principal and least-privilege scope are required.
3. Safety: observers are unable to actuate or block fail-safe behavior.
4. Lifecycle: expiry, revoke, restart, and generation changes are explicit.
5. Resources: observer work and retention are bounded and isolated.
6. Migration: native attach replaces untrusted inference.
7. Science: gaps and missing variables stay visible.
8. Operations: privacy, audit, reattach, and diagnostics are executable.
9. Evidence: revoke, stale, wildcard, and non-authority negatives are required.
10. Governance: session owner grants access; consumer owners manage local data.

## Ratification record

No qualifying owner or security review is recorded.
