# Terminating TLS 1.3 ingress prototype

> **Quarantine:** this isolated crate is non-normative, non-shipping, loopback
> only, and unable to grant NCP identity, authority, a session, a lease,
> operation success, plant action, certification, or release readiness. It does
> not make direct Zenoh `production-secure` available.

This is prototype A from
[`../../../docs/research/authenticated-ingress-feasibility.md`](../../../docs/research/authenticated-ingress-feasibility.md).
It tests one narrow feasibility claim: a process that actually terminates mutual
TLS can bind the verified client leaf certificate to an exact bounded NCP
payload without trusting payload identity as authentication.

## Boundary under test

The only accepted path is:

```text
loopback TCP
  -> exact TLS 1.3 full mutual-authentication handshake
  -> exact verified client leaf DER SHA-256
  -> deny-only early lookup in a bounded default-deny manifest
  -> one length-prefixed bounded frame and complete TLS close boundary
  -> NCP bounded-JSON and semantic validation
  -> one current immutable manifest snapshot
  -> exact certificate + route + plane + class + inner-identity comparison
  -> non-serializable context paired with the same immutable payload bytes
  -> disposable diagnostic replay mock
```

The final manifest snapshot load is the admission linearization point. An early
lookup may reject an obvious miss but can never construct a context. A rotation
that removes the certificate before the final load rejects; an unrelated
rotation does not invalidate the connection globally. A rotation after the load
is ordered after this instantaneous admission decision. The context is not a
continuing authorization or revocation lease.

## Exact TLS profile

- `rustls = 0.23.40` and `tokio-rustls = 0.26.4`;
- ring provider only; no resolved `tls12`, AWS-LC, early-data, compression, or
  logging feature;
- TLS 1.3 only and ALPN exactly `ncp-prototype-a/1`;
- mandatory client certificate in the initial handshake;
- full handshake only; resumed or indeterminate handshakes reject;
- server session storage disabled, TLS 1.3 ticket count zero, early-data size
  zero, half-RTT data disabled, and secret extraction disabled;
- exact `peer_certificates()[0]` DER is hashed without re-encoding; and
- the server configuration is held behind an opaque type whose only constructor
  is the pinned builder.

The OpenSSL negative test uses a separate TLS stack so enabling a Rust TLS 1.2
test client cannot accidentally enable the forbidden feature through Cargo
feature unification. The positive OpenSSL TLS 1.3 transcript contains no
`NewSessionTicket`.

Pinned `rustls-webpki` rejects an explicit server-only EKU on a client
certificate. It treats an absent EKU extension as unrestricted and accepts it
when the certificate is otherwise valid and exactly enrolled. That observed
behavior is retained in a test and is not described as explicit clientAuth-EKU
enforcement.

## Manifest profile

The caller supplies exact JSON bytes and the expected lowercase SHA-256 of those
same bytes. The digest detects byte mismatch; it does not authenticate the
publisher or prove provenance. The manifest requires:

- schema `ncp.prototype.tls-ingress-manifest.v1`;
- a positive generation and explicit `default_deny: true`;
- bounded principal and grant counts;
- unique canonical principal IDs, entity IDs, and certificate fingerprints;
- a closed non-unknown principal role;
- lowercase exact leaf SHA-256;
- one or more unique literal route/plane/message-class grants; and
- no unknown fields, wildcard route syntax, duplicate JSON names, or stale
  generation.

Publication rules are process-local:

- lower generation: reject as rollback;
- equal generation and equal exact-byte digest: idempotent no-op;
- equal generation and different digest: reject as equivocation; and
- higher valid generation: atomically replace the immutable snapshot.

A random boot identifier distinguishes separate store lifetimes in diagnostic
contexts. There is no durable freshness, authenticated publisher, cross-instance
agreement, policy-regression analysis, or restart-spanning audit chain.

## Protected local handoff

`AuthenticatedMessage` owns both a private `AuthenticatedContext` and the exact
`Box<[u8]>`. Neither type is `Clone`, `Default`, serializable, deserializable, or
constructible outside this crate. There is no mutable payload accessor,
`into_parts`, FFI, unsafe code, queue, file handoff, or socket forwarding. Debug
output reports length and digest rather than payload bytes.

The fields remain ordinary copyable information once borrowed. The type is a
software invariant, not a process-containment boundary or authority capability.
Downstream authorization code must still perform the ordinary NCP manifest,
session, epoch, lease, idempotency, receipt, and plant-local admission checks.

The volatile replay probe deliberately admits the same valid TLS message twice,
then reports the second exact principal/payload digest as a duplicate. Rebuilding
the probe clears that observation without changing ingress admission. It is not
a replay guard or recovery authority.

## Verification

Run the complete section:

```bash
./run.sh
```

The command verifies:

- exact Cargo dependencies and resolved features;
- protected source invariants and absence of construction/detachment surfaces;
- eight hostile Python verifier tests;
- Rust formatting and warnings-denied all-target/all-feature clippy plus
  performance lints;
- eighteen Rust integration tests, doc tests, and library documentation build;
- external OpenSSL TLS 1.2 refusal;
- a TLS 1.3 transcript without session tickets; and
- one machine-local result with byte counts and elapsed time.

The live result records two loopback connections, a 65,536-byte manifest limit,
the NCP 1,048,576-byte frame limit, exact observed input sizes, and local elapsed
microseconds. These are resource-bound observations, not performance,
availability, scale, duration-fuzz, soak, or production evidence.

See [`SECTION_REVIEW.md`](SECTION_REVIEW.md) for the independent assumption
challenge, three-lens result, limitations, and next boundary.
