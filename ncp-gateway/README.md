# `ncp-gateway`

`ncp-gateway` is a native same-wire lifecycle edge for the unreleased,
release-blocked NCP `1.0.0-rc.1` candidate. It serves Zenoh lifecycle RPC keys and
forwards validated canonical JSON over a loopback newline-delimited socket to a
Python `SessionService`.

```text
native NCP 1.0 peers -> Zenoh {realm}/rpc/* -> ncp-gateway
                                              -> loopback native-1.0 SessionService
```

This binary is **not** the 0.8-to-1.0 migration gateway. It does not translate old
fields or invent identity/authority/operations/receipts. Engram's local native-1.0
migration is in progress but is not compatible merely because candidate files exist:
the backend must implement native wire 1.0 end to end and return correctly correlated
session generations and responder receipts.

Configuration:

```text
NCP_REALM        canonical deployment realm (default: ncp)
NCP_BRIDGE_ADDR  numeric loopback TCP SessionService address (default: 127.0.0.1:28474)
NCP_ZENOH_CONFIG requests the fail-closed production-secure path; startup currently refuses because authenticated peer identity is not callback-visible
```

`NCP_BRIDGE_ADDR` accepts only a numeric IPv4 or IPv6 loopback socket address,
for example `127.0.0.1:28474` or `[::1]:28474`, with a nonzero port. Hostnames,
unspecified addresses, Unix-domain paths, and non-loopback addresses fail startup
before the gateway opens Zenoh. The bridge protocol is plaintext and has no remote
deployment mode.

```bash
cargo run -p ncp-gateway
```

Query an installed binary without opening a transport with
`ncp-gateway --identity-json`. It reports package and wire versions, compact proto
hash, complete normative contract digest, and build identity. This RC reports
`unreleased-worktree`; an immutable release builder must supply an exact identity.

The gateway validates selector/request/reply/session shape and uses bounded Zenoh
RPC concurrency. Its loopback reply reader requires one newline-terminated JSON
frame, caps the read at the normative frame ceiling, and runs the universal bounded
preflight before returning bytes to the transport; malformed, duplicate-key,
unterminated, and oversized replies are contained as internal bridge failures. The
local socket does not upgrade backend trust. The current Zenoh adapter cannot bind a
transport-authenticated remote principal to `IdentityClaim`, so setting
`NCP_ZENOH_CONFIG` causes startup to fail closed rather than expose a purportedly
secure remote bus. Remote deployment remains unavailable until that binding is
implemented and the end-to-end security/audit gate passes.

The actual legacy translation primitive is `ncp_core::migration` and requires
explicit authenticated terminating context plus visible gateway attribution. See
[`INTEGRATING.md`](../INTEGRATING.md),
[`SECURITY.md`](../SECURITY.md), and
[`RELEASE_READINESS.md`](../RELEASE_READINESS.md).

Licensed under either [MIT](../LICENSE-MIT) or
[Apache-2.0](../LICENSE-APACHE).
