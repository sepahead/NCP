# NCP deployment assets

These are candidate templates and non-certifying reference profiles for NCP
`1.0.0-rc.1`. They contain no production credentials and are not evidence that the
live `production-secure` gate passed.

## Security profiles

- [`profiles/dev-loopback-insecure.json`](profiles/dev-loopback-insecure.json) is
  restricted to loopback/UDS, visibly insecure, and never valid for production.
- [`profiles/production-secure.template.json`](profiles/production-secure.template.json)
  requires mTLS, protected key material, default-deny authority, and no downgrade.
  It is a template; fill exact deployment endpoints, certificate identities, paths,
  realm, entities, roles, and planes.
- [`zenoh-access-control.json5`](zenoh-access-control.json5) and
  [`zenoh-client-secure.json5`](zenoh-client-secure.json5) are the reference Zenoh
  router/peer configuration shapes. Realm strings are addresses, not credentials.
  The current `ncp-zenoh` callbacks cannot expose the authenticated remote principal
  required to bind `IdentityClaim`; `ZenohBus::open_secure` therefore fails closed.
  These files are preflight fixtures, not an available production adapter.

Validate deterministic configuration rules with:

```bash
python3 scripts/check_acl_template.py
python3 scripts/verify_acl_deployment.py --self-test
python3 scripts/validate_security_profile.py --self-test
```

The self-tests do not open a certified live deployment. Before a release campaign,
the transport must implement and negative-test callback-visible authenticated-peer
binding. The later campaign must use real installed peers/certificates and retain
mTLS, correct/incorrect identity, wrong-plane, validity, rotation, revocation,
unauthorized-action, and downgrade evidence.

The router prerequisite probe uses the canonical roles from
`contract/planes.v1.json`: `commander` publishes commands and issues lifecycle
queries; `body` publishes sensor/observation data and serves lifecycle replies;
`observer` is read-only.

This minimal profile does not enroll an `operator` transport subject. A deployment
that needs the normative operator action role must add a distinct certificate
subject, exact action-plane rules, and matching authority-manifest grants. It MUST
NOT widen commander rules to approximate one. Operator override and reset authority
remain separate grants, and wire 1.0 defines no stable ESTOP-reset RPC.

Validate a concrete credential set before the live probe with `--dry-run`:

```bash
python3 scripts/verify_acl_deployment.py --dry-run \
  --endpoint tls/router.example:7447 --realm engram/ncp \
  --ca deploy/certs/ca.pem \
  --commander-cert deploy/certs/commander.pem \
  --commander-key deploy/certs/commander-key.pem \
  --body-cert deploy/certs/body.pem \
  --body-key deploy/certs/body-key.pem \
  --observer-cert deploy/certs/observer.pem \
  --observer-key deploy/certs/observer-key.pem
```

Removing `--dry-run` performs the nonce-delivery campaign. It remains only a
router ACL prerequisite and cannot satisfy the production-secure identity-binding
gate by itself.

## Plant profiles

[`plant-profiles/`](plant-profiles/) contains reference simulation, UAV, mobile-base,
and arm profiles. Each is `reference-non-certifying`, content-addressed, and states
that the body is final authority, protocol ESTOP is not physical certification, and
a consumer safety case is required. Their closed shape and typed digest projection
are defined by [`../contract/plant-profile.v1.json`](../contract/plant-profile.v1.json)
and [`../contract/canonical-digest.v1.json`](../contract/canonical-digest.v1.json);
JSON text formatting is never the digest input.

```bash
cargo run --quiet -p ncp-core --bin validate-plant-profile -- \
  deploy/plant-profiles/*.json
python3 scripts/check_profile_digests.py
```

Do not deploy a reference profile unchanged unless it exactly matches the real
plant, units, arities, ranges, executor, and safe actions and the owner has completed
its hazard analysis. Zero is not universally safe; neutral, shutdown, and bounded
hold-last are plant-owned decisions.

See [`../SECURITY.md`](../SECURITY.md),
[`../NEURO_CYBERNETIC_PROTOCOL.md`](../NEURO_CYBERNETIC_PROTOCOL.md), and
[`../RELEASE_READINESS.md`](../RELEASE_READINESS.md).
