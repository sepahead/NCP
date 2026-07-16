# Authenticated-ingress prototypes

> **Quarantine:** everything below this directory is non-normative, non-shipping,
> and unable to grant NCP identity, authority, operation success, plant action,
> certification, or release readiness. These prototypes are not members of the
> root Cargo workspace and are not included in any NCP package.

This directory implements the local-feasibility questions defined in
[`../../docs/research/authenticated-ingress-feasibility.md`](../../docs/research/authenticated-ingress-feasibility.md).
The order is deliberate:

1. [`zenoh-metadata-probe`](zenoh-metadata-probe/) checks the exact pinned Zenoh
   application metadata boundary.
2. [`tls-terminating-ingress`](tls-terminating-ingress/) tests the isolated,
   loopback-only TLS 1.3 boundary after the Zenoh-probe section.
3. A signed forwarding envelope may start only after the TLS-ingress section has
   its own recorded result and three-perspective review.

Passing a prototype proves only that one bounded implementation ran under the
recorded local environment. Live mTLS/ACL/rotation/revocation, independent peers,
duration fuzzing, soak, key custody, physical safety, and release gates remain
`NOT RUN` unless separate exact evidence says otherwise.
