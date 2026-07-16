# Terminating TLS-ingress section review

> **Decision:** local prototype-A section pass; proceed only to the quarantined
> signed-forwarding prototype after this exact section is committed, pushed,
> remote-verified, and recorded in the B04 ledger. This is not a pass for
> `production-secure`, live mTLS/ACL/rotation/revocation, interoperability,
> authorization, plant action, release, or NCP 1.0 publication.

Review date: 2026-07-16.

Reviewed dependency boundary:

| Component | Version | Crates.io checksum | Upstream commit |
| --- | --- | --- | --- |
| rustls | `0.23.40` | `ef86cd5876211988985292b91c96a8f2d298df24e75989a43a3c73f2d4d8168b` | `b44c09fbca5172b3f5e5ed6ba2ffe6fcd934e07a` |
| tokio-rustls | `0.26.4` | `1729aa945f29d91ba541258c8df89027d5792d85a8841fb65e8bf0f4ede4ef61` | `0c14e1496ef50adade4ac7c7d1f0270dfb3cdda5` |
| rcgen, test-only | `0.14.8` | `57f6d249aad744e274e682777a50283a225a32705394ee6d5fcc01efa25e4055` | `a70f083fa21be1214de4aa3743cbf1ebfc62ddad` |
| ring | `0.17.14` | `a4689e6c2294d81e88dc6261c768b63bc4fcdb852be6d1352498b114f61383b7` | lock-bound registry source |
| rustls-webpki | `0.103.13` | `61c429a8649f110dddef65e2a5ad240f747e85f7758a6bccc7e5777bd33f756e` | lock-bound registry source |

The local run used rustc/cargo `1.96.0`, Python `3.14.6`, and OpenSSL `3.6.2`.
All versions are local observations, not portability or clean-room evidence.

## Self-explanation

The pinned Zenoh 1.9.0 callback cannot expose the verified certificate principal
for each delivery. Prototype A therefore owns a distinct TLS termination
boundary. Its job ends after it produces one inseparable diagnostic observation:
the exact verified leaf fingerprint, manifest-derived actor, endpoint profile,
manifest version, process-local boot epoch, payload digest, and the exact bounded
payload bytes that earned those values.

The implementation deliberately separates three decisions:

1. TLS verifies the certificate chain and possession of the client private key.
2. A bounded default-deny manifest admits the exact leaf for one literal endpoint.
3. The NCP payload is parsed only after those checks, and its identity claim must
   exactly match the transport-bound manifest actor.

None of those decisions grants NCP authority. The ordinary session generation,
stream epoch, lease, idempotency, receipt, lifecycle, safety, and plant-local
checks remain outside the prototype.

The first rotation design captured a manifest before the frame and rejected every
connection if the pointer changed. Review rejected that as a global
availability-amplification mechanism that still did not provide continuing
revocation. The implemented design uses the early snapshot only to deny. After
the complete frame is parsed, one current snapshot load linearizes the full
certificate/grant/claim decision. A concurrent unrelated update can pass; removal
of the relevant mapping before that load rejects.

## Corrections made during review

- The initial public constructor accepted any externally built
  `rustls::ServerConfig`. Although visible ticket and resource checks passed, a
  caller could have supplied optional client authentication. The API now accepts
  an opaque pinned-config type whose only constructor installs mandatory client
  verification and the exact TLS profile.
- The original context did not retain a digest of its payload. The digest is now
  computed internally from the same bytes before context construction, and the
  replay mock consumes that value instead of re-hashing a detached copy.
- Derived debug output would have printed the complete payload byte array.
  `AuthenticatedMessage` now has manual redacted debug output, tested with a
  sentinel value.
- Compile-time negative assertions now reject accidental `Clone`, `Default`,
  serde, deserialization, and `AsRef<[u8]>` implementations on the protected
  handoff types. The source verifier rejects public detachment or mutation
  methods, unsafe code, FFI, and optional-client-auth construction.
- A caller-supplied boot ID could have been reused accidentally. Each manifest
  store now obtains a random process-local epoch from `getrandom`; reconstructing
  the store is tested to produce a distinct epoch.
- Cargo defaults would have enabled TLS 1.2, AWS-LC, and logging. Both rustls
  dependencies now disable defaults and resolve only the ring/std features
  required by the prototype.
- rustls defaults to two TLS 1.3 tickets even when its ticketer starts disabled.
  The builder sets the ticket count to zero; an external OpenSSL transcript
  verifies that no `NewSessionTicket` is emitted.

## Independent assumption challenge

- **Exact SHA-256 authenticates the manifest publisher.** Rejected. A caller that
  can supply both bytes and digest can hash hostile bytes. The digest proves
  exact-byte agreement only. Publisher authentication and provenance are
  external requirements.
- **A higher generation is necessarily newer or safer.** Rejected. It is only
  greater within one process-local ordering. A hostile publisher can jump the
  counter or publish a syntactically valid policy regression. Durable rollback
  protection and policy review are absent.
- **One immutable snapshot provides continuing revocation.** Rejected. It gives
  an instantaneous linearizable admission decision. A rotation after the
  snapshot load is ordered after admission. The context is not a live lease, and
  downstream use must perform its own current authorization checks.
- **Global invalidation on every rotation is conservatively secure.** Rejected.
  It gives unrelated configuration churn a denial-of-service lever while leaving
  a post-admission revocation window. Per-message decision against one current
  snapshot is clearer and more testable.
- **TLS authentication makes payload identity trustworthy automatically.**
  Rejected. The exact principal, entity, role, plane, route, and message class
  remain a separate manifest and payload-congruence decision.
- **The certificate subject or intermediate identifies the actor.** Rejected.
  The implementation hashes only the exact verified first leaf DER. A chained
  certificate test proves the intermediate digest differs and is not selected.
- **Webpki enforces explicit clientAuth EKU.** Rejected. It rejects an explicit
  server-only EKU but accepts an absent EKU as unrestricted under the pinned
  behavior. The prototype records this limitation instead of claiming stricter
  enforcement.
- **No session ticket configuration proves every resumption implementation
  property.** Rejected. Source configuration, handshake-kind rejection, feature
  verification, and one OpenSSL transcript are local evidence. Cross-version and
  alternate-client behavior remains unproved.
- **A non-constructible Rust type is a security containment boundary.** Rejected.
  Getters expose copyable facts, and memory corruption or future unsafe/FFI code
  could defeat the invariant. The type prevents accidental construction and
  detachment in safe Rust; it cannot authorize use merely by possession.
- **The volatile duplicate mock is replay protection.** Rejected. Two identical
  messages authenticate successfully; the second is only observed as duplicate.
  Rebuilding the mock clears memory and still does not change ingress admission.
- **Loopback TLS proves live mTLS operations.** Rejected. It does not test
  deployment CA custody, authenticated manifest distribution, CRL/OCSP,
  multi-host ACLs, certificate rotation, revocation propagation, multi-instance
  convergence, hostile network middleboxes, or operational recovery.

## Executed falsification matrix

The complete runner executes eight hostile verifier tests and eighteen Rust
integration tests:

- positive exact TLS/certificate/manifest/payload binding;
- mandatory certificate, wrong CA, expired, not-yet-valid, server-only EKU, and
  explicit absent-EKU observation;
- exact leaf selection with an intermediate;
- TLS 1.2 refusal through OpenSSL, plaintext refusal, ALPN mismatch, full
  handshake enforcement, and no TLS 1.3 session ticket transcript;
- invalid digest, oversize manifest, unknown fields and roles, wildcard routes,
  duplicate IDs/fingerprints/grants/JSON names, rollback, equivocation,
  idempotent republish, concurrent publication, and untorn reads;
- false inner principal, wrong endpoint grant, malformed JSON, duplicate payload
  names, and extra identity members;
- zero/oversize framing before payload allocation, truncation, timeout, trailing
  bytes, second-frame behavior, and incomplete TLS closure;
- unrelated and actor-removing rotation races;
- immutable payload digest binding and debug redaction;
- duplicate observation separated from admission and reset across mock restart;
  and
- distinct boot epochs across reconstructed manifest stores.

The live result reports one 369-byte ephemeral manifest, one 583-byte NCP
payload, two connections, the 65,536-byte manifest limit, the 1,048,576-byte NCP
frame limit, and a variable local elapsed time. The exact manifest size remains
stable because the ephemeral certificate is represented only by its fixed-width
SHA-256 fingerprint. Timing is not a performance claim.

## Three-lens review

### 1. Protocol, security, and plant boundary

- No normative proto, Rust wire type, schema, vector, compact hash, candidate
  baseline, conformance manifest, shipping package, or direct-Zenoh behavior
  changed.
- Payload identity, certificate subjects, unknown values, parser defaults,
  duplicate names, missing fields, stale generations, and configuration absence
  cannot create a context.
- The protected handoff cannot grant an authority lease, operation success,
  session, stream freshness, lifecycle transition, channel capability, ESTOP,
  safe action, or actuator result.
- Crebain/body-local final actuator authority and physical certification remain
  unchanged and untested.

Result: the prototype preserves the authentication/authorization/actuation
separation and falsifies the main construction risks locally.

### 2. Consumer and runtime usability

- Consumers receive no shipping API or dependency from this isolated crate.
- The exact path shows how a future adapter could obtain a verified actor without
  trusting Zenoh metadata or payload claims.
- One frame per TLS connection is intentionally conservative and expensive. No
  pooling, streaming, multiplexing, backpressure policy, retry contract, or
  production deployment topology is selected.
- Manifest churn does not globally invalidate unrelated in-flight messages, but
  a removed actor fails at the final snapshot load.
- Replay remains a downstream semantic concern. The mock demonstrates the
  separation without pretending to implement NCP replay recovery.

Result: feasibility is positive for a bounded local boundary, while production
ergonomics and integration remain open ADR work.

### 3. Operations, science, and evidence quality

- `run.sh` verifies exact dependency features, protected source structure, Python
  verifier mutants, formatting, clippy, Rust tests, documentation, OpenSSL
  negatives, and the live resource result.
- Exact dependency versions and registry checksums are retained in `Cargo.lock`.
  Private certificate keys exist only in runtime memory or a uniquely named
  temporary directory removed by the tests; no private key is committed.
- A local `cargo audit` scan of the 90 lockfile dependencies reported no known
  RustSec vulnerability on the review date. The fetched advisory database is
  time-varying and this observation is not a frozen supply-chain gate.
- Five completed exact-model `claude-fable-5` consultations challenged replay
  ownership, TLS runtime evidence, protected handoff API design, manifest
  publication, and the later ecosystem authority topology. Adopted prototype-A
  corrections are reflected above. The topology response instead identified
  future ADR falsification cases around mode-transition races, signing-oracle
  behavior, assessor replay, telemetry saturation, restart asymmetry, and
  provenance-tainted control inputs. The model advice is non-normative and
  cannot count as a reviewer, evidence source, or gate.
- One additional Fable rotation response hit its output limit and three
  reformulations were refused; those incomplete responses were not counted as
  completed reviews or evidence.
- No scientific result, calibrated posterior, paper reproduction, performance,
  scale, soak, duration fuzz, interoperability, safety, or release conclusion is
  derived.

Result: the evidence is proportional to prototype A and preserves its negative
findings, especially manifest provenance, absent EKU behavior, and revocation
scope.

## Section decision and next boundary

Prototype A passes its bounded local objective: the exact implementation can
derive a verified leaf at the owning TLS boundary, bind it to a strict
default-deny manifest and the same immutable NCP payload, remain distinct from
authority, enforce pre-allocation limits, and reject the executed hostile cases.

This permits only the next B04 research section after an exact pushed receipt:
prototype B, the strict signed forwarding envelope with durable atomic replay
semantics and two independent non-Rust parsers. It does not permit B01 ADR
ratification, stable-source implementation, a consumer repository change,
shipping package inclusion, or any external gate promotion.
