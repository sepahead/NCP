# Independent Node signed-forwarding verifier

> **Quarantine:** this native TypeScript/Node implementation is non-normative,
> non-shipping, and unable to grant NCP identity, authority, a session, a lease,
> operation success, plant action, certification, or release readiness.

This verifier independently implements the bounded signed-forwarding envelope
parser and authentication projection. It shares no Python parser, FFI, or crypto
binding with the PyNaCl reference. The reviewed runtime is Node 26.3.0 with
OpenSSL 3.6.2; TypeScript 5.9.2 and `@types/node` 26.1.1 are exact in the npm
lock, including registry integrity values.

The verifier:

- parses JSON with its own bounded recursive-descent parser;
- rejects duplicate names after escape decoding, invalid UTF-8, BOMs,
  unpaired surrogates, unsafe integers, floats outside payloads, and excess
  depth, width, nodes, strings, or bytes;
- preserves exact received protected/payload base64url strings for the signing
  input;
- accepts only the exact flattened `Ed25519` profile and current exact-byte
  default-deny key manifest;
- enforces distinct signer/carrier principal and entity identities plus exact
  route, plane, class, audience, manifest, security, time, session, stream, or
  operation bindings; and
- returns an explicit authentication projection containing no NCP authority.

Node/OpenSSL's native Ed25519 result is not treated as a complete strict-profile
check. On the pinned runtime, a zero public key and zero signature verify
successfully for at least the ASCII message `protected.payload`. The wrapper
therefore rejects noncanonical public keys and encoded `R`, the seven reviewed
small-order compressed representatives on both sign encodings, and scalar
`S >= L` before calling the native verifier. The regression suite retains both
the native acceptance and wrapper rejection, plus the RFC 8032 empty-message
known-answer vector.

This implementation deliberately has no replay database. The Python reference
continues to prove and execute durable commit-before-handoff replay behavior.
The public differential gate gives every Python evaluation a fresh replay store
and compares the two implementations' parsing, authentication, manifest,
profile, and payload-binding decisions. This separation does not prove a second
durable replay implementation.

Run:

```bash
./run.sh
```

The runner verifies the exact Node/OpenSSL/dependency boundary, compiles under
strict TypeScript settings, and executes twenty-one tests, including six
mutation tests of the boundary verifier itself. The parent prototype
runner additionally executes the public differential corpus.
