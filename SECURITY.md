# NCP security

> **Candidate status:** these are the requirements for unreleased
> `1.0.0-rc.1`. Local configuration and validator tests exist, but the stable
> Zenoh adapter cannot yet expose a transport-authenticated remote principal for
> payload-identity binding. Its production-secure open path fails closed. Live
> mTLS, ACL, certificate rotation/revocation, packet/process capture, and
> independent-host certification are therefore **NOT RUN**, and the candidate is
> release-blocked.

Report vulnerabilities privately through the repository's GitHub security advisory
flow. Do not include credentials, private keys, sensitive plant data, or exploit
details in a public issue.

## Threat boundary

NCP assumes a network attacker may read, inject, replay, reorder, delay, duplicate,
or drop traffic; a credentialed peer may claim the wrong entity/role/plane; a prior
authority holder may reconnect or replay; and malformed JSON may attempt resource
exhaustion. Local simulation or plant processes may crash or restart.

NCP does not defend a fully compromised body host, certify physical safety, define a
universal safe action, or turn `mode`/`ttl_ms` into authentication. The body remains
final actuator authority and needs independent safety controls.

## Baseline profiles

The only registered profiles are defined in
[`contract/security-profiles.v1.json`](contract/security-profiles.v1.json).

### `dev-loopback-insecure`

This profile permits only loopback TCP or an absolute Unix-domain socket. It has no
transport authentication and must expose an unmistakable insecure status. A
non-loopback bind, downgrade flag, TLS fragments, hidden discovery/listeners, or a
claim that this profile is production-safe fails startup.

### `production-secure`

This profile requires all of the following, with no fail-soft fallback:

- mutual TLS on every remote connection;
- validation of certificate chain, peer identity, hostname/service identity, and
  validity interval;
- protected private-key material outside repository/image content;
- one default-deny authority manifest for realm, certificate principal, NCP entity,
  principal role, and allowed planes;
- explicit action publishers; wildcard action grants are forbidden;
- certificate revocation and rotation procedures;
- profile ID and exact SHA-256 security-state digest in negotiation and audit;
- no plaintext, discovery, listener, or insecure-profile downgrade on failure.

Partial configuration is invalid. A router or peer must not start a production NCP
surface until the complete precommitted profile validates.

The digest algorithm is portable and closed, not `sha256(json.dumps(...))` or a
language-specific struct serialization. The normative
[`security-state-digest`](contract/security-state-digest.v1.json) projection uses
the shared [typed canonical encoding](contract/canonical-digest.v1.json), sorts
principals and planes semantically, inserts the documented false authority-flag
defaults, and covers the exact bind, authority, TLS-path, downgrade, and status
state. Unknown members, duplicate identities/planes, malformed Unicode,
noncanonical endpoints, and projection-limit violations reject before hashing.
Certificate and key file bytes are deliberately outside the digest; installed
certificate validity and key protection remain runtime checks.

The current `ncp-zenoh` callback surface supplies the key and payload but not the
verified remote certificate principal. It therefore cannot compare that principal
with `IdentityClaim` through the authority manifest. `ZenohBus::open_secure`
performs a TLS-client **configuration preflight** and then fails closed before
opening. That preflight does not validate the authority manifest, deployed router
ACL, negotiated security-state digest, callback-visible peer principal, rotation,
or revocation. All of those checks and their negative tests are prerequisites to
lifting the fail-closed gate. The templates do not make generic `open`,
`with_config`, or `from_session` calls `production-secure`.

## Identity and authorization

`IdentityClaim` is payload metadata, not proof. The transport adapter obtains the
verified certificate identity and calls the authority manifest to authenticate the
claimed principal/entity on the actual plane. A match on principal alone is
insufficient. Unknown roles/planes and identity segments containing wildcards,
separators, whitespace, control characters, or excessive length fail closed.

That binding is a missing implementation prerequisite, not merely missing test
evidence. A TLS connection or router key ACL without callback-visible verified peer
identity cannot satisfy it.

Every NCP-aware data-plane boundary binds both routing identity and incarnation: the
payload `session_id` must exactly equal the session encoded in the actual Zenoh key,
and `session.generation` must equal the current server-issued generation retained
from `SessionOpened`, before publication, callback delivery, or latch mutation. The
rule covers perception, action, observation, named channels, and ESTOP. Every remote
ESTOP needs a complete kind/version/own-stream/session envelope; only its authority
lease may be absent after authenticated actor/plane and exact live-session admission.
Inbound messages are never repaired or assigned a generation. This isolation check
does not establish that an ESTOP reached the intended plant, that the plant executed
a safe action, or that physical motion stopped; those require independent body-local
safety and delivery evidence.

Action authority additionally requires a live session generation and matching
bounded lease. Lifecycle mutations require the same lease plus idempotency context;
receipts bind results to the authenticated responder. Operator reset/override rights
are separate manifest bits and may only belong to an enrolled operator.

Lease renewal authenticates two actors, not just lease bytes: the supplied issuer
and current holder must match the active immutable lease, the issuer must be an
enrolled commander or an operator with explicit override authority, and the holder
must remain the enrolled commander. The receiver's current monotonic deadline must
be strictly unexpired. A late renewal fails closed to HOLD and cannot revive the
term; a newer acquisition is required.

There is no stable wire-1.0 reset RPC. An authorized body-local or out-of-band ESTOP
reset is successful only as a session-generation cut: retire the current generation,
authority and lease, and all associated stream state, then remain non-actuating until
a fresh `SessionOpened` creates a new generation, fresh streams are established, and
a new matching authority lease is acquired. A local governor, authority-machine,
or buffer reset helper alone neither authenticates a reset nor restores remote
authority. A frame from the retired pre-reset generation, including ESTOP, is
rejected by exact route/session binding before latch or control processing.
The old authority machine and action buffer are retired audit state and reject every
later open, acquire, renew, reconnect, or command operation; implementations create
fresh objects only after a new generation is issued.

Revocation blocks new authentication immediately, transitions affected active
authority to fail-safe behavior, and does not clear ESTOP. Reconnect must prove the
same epoch, term, lease, principal, and entity within the local monotonic deadline.

## Configuration artifacts

[`deploy/profiles/`](deploy/profiles/) contains profile templates and
[`deploy/zenoh-access-control.json5`](deploy/zenoh-access-control.json5) contains the
reference per-plane Zenoh ACL structure. Templates are not credentials and are not
deployment evidence. Render them from the same realm/entity manifest, provision real
certificates securely, and validate with:

```bash
python3 scripts/validate_security_profile.py --self-test
python3 scripts/check_acl_template.py
python3 scripts/verify_acl_deployment.py --self-test
```

Those commands prove deterministic configuration rules only. Release certification
cannot begin until an adapter provides the required authenticated-principal binding.
It must then start installed peers and a real router, exercise correct and incorrect
CA, expired/not-yet-valid certificates, wrong entity/plane, unauthorized action,
downgrade, rotation, and revocation, and retain packet/process/ACL evidence. The
matrix must also inject missing/cross-session IDs and missing/stale generations on
every data plane (including named channels and complete ESTOP envelopes), prove
rejection before delivery or latch mutation, and prove a complete same-live-session
ESTOP reaches the intended plant-safe-action path. This external production-secure
campaign is **NOT RUN**; none of that live evidence exists yet.

## Resource and audit controls

Apply [`contract/limits.v1.json`](contract/limits.v1.json) before generic JSON
allocation. Bound transport tasks and queues by plane; never hide an observation
flood or retry storm behind unbounded work.

One Zenoh command publisher uses one epoch and position allocator for Active, HOLD,
and ESTOP. An attempted put consumes the position even when delivery is ambiguous.
After an ambiguous fail-safe attempt, the bounded dispatcher rejects Active until a
new logical fail-safe with a new position succeeds; it never spins on or reissues
the ambiguous position.

Exercise duplicate, replayed, reordered, and delayed frames both within one live
session and across retired session/stream epochs. A duplicate or stale frame must
not refresh a lease, watchdog, TTL, authority, stream high-water mark, or active
output. ESTOP retains its documented same-session fail-safe priority, but it does
not bypass routing identity. These local rules have deterministic tests; the
multi-process fault/replay campaign remains **NOT RUN**.

Audit events follow [`contract/observability.v1.json`](contract/observability.v1.json).
Do not log secrets or raw channel payloads by default, and do not put session,
principal, entity, or operation IDs into metric labels. The local SHA-256 audit chain
detects mutation but is not a signature; production evidence requires an independent
external anchor.

## Release decision

Passing local tests does not make `production-secure` available or certified. The
implementation prerequisite and external pre-release gate are tracked in
[`RELEASE_READINESS.md`](RELEASE_READINESS.md), under the canonical policy in
[`contract/release-gates.v1.json`](contract/release-gates.v1.json). Until both pass
against one immutable installed-artifact set, do not expose this candidate as a
production control surface.

The current fail-closed unit test checks the exact missing-principal-binding error
before the transport opener is reached in source order. It is a reason-code and
control-flow regression, not packet/process proof of zero network side effects; the
latter belongs to the external certification matrix and remains **NOT RUN**.
