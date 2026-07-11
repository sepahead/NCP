# Security Policy

## Known limitation: the default/open transport is unauthenticated

NCP does not authenticate a frame at the message layer. The default quiet Zenoh
configuration disables multicast discovery but does **not** enable TLS or an ACL;
any participant that can reach that bus can publish action/command messages. A
complete opt-in mTLS router template, strict client template, and default-deny ACL
now ship under `deploy/`, but they protect a deployment only when operators actually
configure and use them.

**Deploy NCP only on a trusted, closed realm** (an isolated, access-controlled
Zenoh network). Do not expose the action/command plane on an open or shared
realm.

**The realm is addressing, not authentication.** A "realm" is just the leading
segment of the Zenoh key-expression (`{realm}/session/*/…`, built in
`ncp-core/src/keys.rs`) — a namespace prefix that keeps multiple NCP deployments
from colliding on a shared bus. It is *not* a security boundary: the realm string
is never checked against any credential, so knowing or guessing it grants no
rights and withholding it confers no protection. What actually gates access is the
reachability of the underlying Zenoh network plus the ACL/mTLS below — never the
key prefix. "Closed realm" above therefore means *a closed Zenoh network* (network
isolation, plus the ACL/mTLS that follow), not a secret realm name. Treat the
realm as routing metadata, never as a credential.

### Local fail-safe

As a defense-in-depth fail-safe, action bodies enforce `mode`, `ttl_ms`, and
(since wire 0.6) **seq discipline** locally at the receiver: a stale,
out-of-mode, version-less/incompatible, or unstamped (`seq < 1`) command is
rejected regardless of who sent it, and a duplicate/replayed `seq` never
refreshes the liveness deadline (the pre-0.6 "`seq == 0` always accepted"
escape hatch is removed). This is a local safety governor, **not** a substitute
for network-level authentication: seq discipline defends against transport
artifacts and buggy peers, not adversaries — an injecting attacker can forge
fresh, well-stamped frames, and alternating replays of different captured
frames across expiry windows are indistinguishable from a legitimate restart on
an unauthenticated wire. Adversarial integrity is mTLS's job (below).

> **`contract_hash` is not a security control.** The handshake's `contract_hash`
> (`ncp_core::CONTRACT_HASH`) is an FNV-1a digest that *detects accidental contract
> drift* between peers — it is **advisory** (a mismatch is logged, not rejected; see
> `VERSIONING.md`) and is **not** a cryptographic MAC. It provides no integrity or
> authenticity guarantee against an adversary; that is the transport's job (mTLS +
> the ACL below). Do not rely on it as an authentication or anti-tampering gate.

## Threat model & hardening path

The headline risk is a **confused-deputy / world-writable command surface**: on an
open realm, any participant that can reach `…/command` can drive an actuator, and
the local `mode`/`ttl_ms` governor answers "is this command currently valid?" but
not "may this sender command at all?". The fix is authentication + per-plane
authorization, modelled on the established robotics-control-bus mechanisms:

- **Transport auth/ACL** — enable Zenoh access-control + TLS and a per-plane ACL so
  a perception-only client cannot publish to the action plane (cf. **DDS-Security**
  authentication / access-control / cryptographic plugins).
- **Verified controller identity** — bind every action frame to a *proven*
  `controller_id` (mTLS client certs for a closed realm; DID/verifiable-credentials
  for an open realm), and consider per-message signing (cf. **MAVLink 2 message
  signing**) so a replayed or forged command is rejectable.

**The perception (sensor) plane is an equal attack surface.** Because the
controller computes commands *from* `SensorFrame`s, a participant that can PUBLISH
spoofed sensor data steers the actuator and can defeat the geofence — a
**false-data-injection (FDI)** attack — without ever touching `…/command`. There is
no local-governor equivalent here: sensor-side FDI can be made *perfectly
undetectable* to model-/residual-based monitors (the brain perceives "normal"
operation while the body is driven off trajectory — see Ueda & Kwon,
[arXiv:2408.10177](https://arxiv.org/abs/2408.10177), and Choi & Jang, WISA 2022,
[doi:10.1007/978-3-031-25659-2_14](https://doi.org/10.1007/978-3-031-25659-2_14)),
so a software safety governor is **not** a substitute. The remedy is the same as
for the command plane — **publisher access control**: under DDS-Security / ROS 2
SROS2, *publish* permission is access-controlled per topic independently of
subscribe, on default-deny governance (cf. the **DDS-Security** access-control model
and the SROS2 master governance that enables write access control on every topic).
NCP's ACL template therefore restricts `…/sensor/**` PUT to the `robot` (body)
subject, symmetric to `…/command/**` being restricted to `commander`; both
PUT-authority invariants are mechanically enforced by
[`scripts/check_acl_template.py`](scripts/check_acl_template.py).

This is tracked as ROADMAP **P0** (authenticate the action plane) and
[#7](https://github.com/sepahead/NCP/issues/7). A per-plane Zenoh ACL template
(default-deny; only the authenticated `commander` subject may publish commands, the
robot publishes only its sensors, observers are read-only) is provided at
[`deploy/zenoh-access-control.json5`](deploy/zenoh-access-control.json5) — pair it
with mutual TLS so each subject's identity is proven. Until this ships in a
deployment, the closed-realm guidance above stands.

## Enabling transport authentication (TLS + ACL)

The ACL only binds authorization to identity if that identity is **proven** by
mutual TLS — without mTLS the `cert_common_names` are spoofable and the ACL is
meaningless. To stand up an authenticated realm:

1. **Issue certificates.** Create a CA, then per-subject client certs whose exact
   Common Names appear in the ACL `subjects` lists. `cert_common_names` does **not**
   glob: a literal `robot-*` matches only that literal string, so enumerate every
   issued leaf CN. Keep the CA key offline and rotate leaf certs per policy.
2. **Render and start the router.** The template is pinned to the neutral `ncp`
   realm. Render an exact deployment realm, then replace the placeholder router
   certificate paths before starting Zenoh:

   ```bash
   python3 scripts/render_acl_template.py \
     --realm engram/ncp --output router-secure.json5
   zenohd --config router-secure.json5
   ```

   The router uses a TLS-only listener plus `root_ca_certificate`,
   `listen_certificate`, `listen_private_key`, and **`enable_mtls: true`**.
3. **Configure each peer as a client.** Copy
   [`deploy/zenoh-client-secure.json5`](deploy/zenoh-client-secure.json5) per
   identity and replace the router DNS name, CA, `connect_certificate`, and
   `connect_private_key`. Keep `mode: "client"`, listeners empty, multicast/gossip
   disabled, TLS-only connect endpoints, and `verify_name_on_connect: true`.
   `ZenohBus::open_secure` validates these properties before opening. Do not pass
   the router config to this client API.
4. **Verify the authority invariants.** With the realm up, confirm an `observer`/`robot`
   identity is *rejected* when it `put`s on `…/session/*/command/**` (only `commander`
   succeeds), AND that an `observer`/`commander` identity is *rejected* when it `put`s
   on `…/session/*/sensor/**` (only `robot` succeeds) — both control planes (action
   and perception) are then authenticated, not world-writable. Also verify only the
   commander publishes observations and queries/serves lifecycle RPC, while observers
   can subscribe to sensor, command, and observation traffic but cannot write.

Schema field names follow the Zenoh 1.x access-control config; validate against
your Zenoh version (authoritative: the zenoh.io configuration docs) before relying
on it. Live mTLS deployment validation is the remaining P0 item on
[#7](https://github.com/sepahead/NCP/issues/7).

### P0 closure checklist (requires delivery evidence)

Run [`scripts/verify_acl_deployment.py`](scripts/verify_acl_deployment.py) against a
*live* mTLS+ACL realm to close P0. A local `put()` success is not proof that the
router delivered a sample, so the verifier uses an authenticated observer and a
unique nonce for every trial. Its 3×3 role/plane matrix requires delivery for:

- commander → command;
- robot → sensor; and
- commander → observation.

The other six writes (including every observer write) must remain unobserved for a
bounded rejection window, and each denial is accepted only after a successful
same-plane baseline. A final quarantine catches late forbidden delivery. The tool
also proves all authenticated router links and separately requires a no-certificate
client to establish no router connection. It refuses plaintext endpoints,
listeners, discovery, missing/paired-wrong credentials, or disabled hostname
verification before the live run. See `scripts/README.md` for the exact invocation;
`--self-test` exercises its offline negative truth table and `--dry-run` validates
the deployment inputs.

A fully successful live run is suitable P0 evidence; no such run is committed in
this repository yet, so the "closed realm only" guidance remains. The template is
independently CI-guarded for mTLS/default-deny, exact identities, RPC authority,
command/sensor/observation PUT authority, and complete observer read access by
[`scripts/check_acl_template.py`](scripts/check_acl_template.py).

## Residual risks after mTLS + ACL (hardening backlog)

Enabling mutual TLS and the per-plane ACL closes the world-writable command and
perception **PUT** surface (the P0 invariants above). It does **not** make NCP
fully hardened. An adversarial review catalogued the items in
[`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md) **with per-finding status** —
the three high-severity findings (bulk-decode OOM budget, unbounded/non-finite
`ttl_ms`, empty-position geofence bypass) and the wire-0.6 pair (`seq == 0`
escape hatch, unenforced data-plane `ncp_version`) are **resolved with
regression tests**; the still-open security-relevant one is summarised below.

### Per-verb RPC addressing — RESOLVED in wire 0.7

Lifecycle requests now use distinct exact keys:
`{realm}/rpc/open_session`, `{realm}/rpc/step_request`,
`{realm}/rpc/run_request`, and `{realm}/rpc/close_session`; the server declares
`{realm}/rpc/*`. The shipped default-deny ACL grants lifecycle RPC query and
serve/reply authority only to the authenticated `commander`. This closes the old
single-key ambiguity and allows a deployment to split permissions further by verb
without inspecting the JSON body. The structural ACL guard rejects an unsplit RPC
key or non-commander RPC authority.

### Bulk/observation decode memory-amplification DoS — RESOLVED

`BulkBlock::decode` (`ncp-core/src/bulk.rs`) previously sized each column's
allocation from attacker-controlled directory fields with no cumulative budget —
an audited ~64,000× memory-amplification / OOM DoS reachable by any peer that
could publish on the observation plane. **Fixed** (commit `0672168`, with a
regression test): a running `alloc_budget` bounded by the input length rejects
any block whose summed declared `data_len` exceeds `bytes.len()`. The fix is
wire-compatible (every conforming block lays its columns out disjointly), so
hostile/amplifying blocks are rejected while conforming traffic is unaffected.
Publisher access control on the observation plane (the ACL above) remains the
first line; the budget makes the decoder safe even without it.

### Local safety-governor fail-OPEN edge cases — RESOLVED

The audit found inputs that made the receiver-side fail-safe fail *open*: an
unbounded/non-finite (`+Inf`) `ttl_ms` disabled the `CommandWatchdog` deadline
backstop, and an empty position channel read as the origin and bypassed the
geofence. **Both fixed** (commit `0672168`, with regression tests): the enforced
ttl is clamped to a finite ceiling (`MAX_TTL_MS`, non-finite → immediately
stale), and empty position data fails closed to HOLD like an absent channel.
Later hardening extended the same fail-closed treatment to non-finite/negative
`SafetyLimits`, backward/non-finite clocks, inbound-ESTOP latching, and the
wire-0.6 seq discipline (see `KNOWN_LIMITATIONS.md` for the full resolved
ledger).

## Supported versions

The protocol is pre-1.0. Security fixes target the latest released version.

## Reporting a vulnerability

Please report suspected vulnerabilities privately to the maintainer rather than
opening a public issue. Include a description, reproduction steps, and the
affected version. You can expect an acknowledgement and a plan for remediation.
