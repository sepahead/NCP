# deploy

[![License: MIT OR Apache-2.0](https://img.shields.io/badge/license-MIT%20OR%20Apache--2.0-blue.svg)](#license)

Deployment assets for the [Neuro-Cybernetic Protocol](../NEURO_CYBERNETIC_PROTOCOL.md) (NCP) —
the one normative protocol spoken by its Rust, Python, TypeScript, and C++ peers. This directory
holds a complete secure Zenoh router template and a strict client template, not application code.

## `zenoh-access-control.json5`

A complete TLS-only, mTLS-required, **default-DENY** Zenoh router template that closes the open-realm
action plane: only the authenticated `commander` subject may PUBLISH commands, the `robot`
publishes only sensors and reads commands, and `observer` taps are READ-ONLY. The three
planes (sensor / observation / command) get distinct per-subject permissions, so a
perception-only client can never command.

It is a **template** — render the exact realm safely, then replace certificate paths,
exact `cert_common_names`, and interfaces for your deployment:

```bash
python3 scripts/render_acl_template.py \
  --realm engram/ncp --output router-secure.json5
zenohd --config router-secure.json5
```

Zenoh does not interpolate `NCP_REALM` inside ACL key expressions; using the default
`ncp/...` policy with peers on another realm fails closed and rejects legitimate traffic.

## `zenoh-client-secure.json5`

A strict client template for `ZenohBus::open_secure` and `ncp-gateway`. Copy it per
identity, replace the TLS router endpoint and CA/client certificate/private-key paths,
and ensure the leaf certificate's exact CN appears in the router's subject list.
`NCP_ZENOH_CONFIG` on a peer points to this **client** file, never the router file.

For a long `step_request` or `run_request`, the query deadline must cover the
requested simulation duration plus backend/bridge overhead. Use
`ZenohBus::request_with_timeout` or `ZenohNcpClient::{step,run}_with_timeout`, or
set Zenoh's `queries_default_timeout` consistently. The gateway's backend socket
timeout is 30 seconds; leaving a shorter query timeout makes a healthy late reply
look like a dead server.

## Open-realm caveat

On an open realm the **realm string is addressing, not a credential** — anyone who can reach
the bus can spoof a subject. This ACL only binds authorization to identity once that identity
is **proven by mutual TLS**: `cert_common_names` are matched by exact string equality, and
without mTLS they are trivially spoofable and the ACL is meaningless. ACL/mTLS is **opt-in**;
see [`SECURITY.md`](../SECURITY.md) for the threat model and the TLS + ACL enablement steps.
The template is shape-checked by `scripts/check_acl_template.py`.

See the [repository README](../README.md) for the full NCP picture and crate map.

## License

Licensed under either of [MIT](../LICENSE-MIT) or [Apache-2.0](../LICENSE-APACHE) at your option.
