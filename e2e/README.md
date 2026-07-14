# NCP end-to-end evidence

This directory contains developer integration runners for the unreleased,
release-blocked NCP `1.0.0-rc.1` candidate. They are not the independent secure
live-peer campaign required for release.

The self-contained Rust Zenoh tests exercise real sessions and transport plumbing,
but both endpoints use the Rust reference and therefore do not prove independent
interoperability. Run them with:

```bash
cargo test -p ncp-zenoh --test cross_session_rpc
```

[`nest_five_networks.py`](nest_five_networks.py) is a thin native-wire-1.0 client
intended to smoke five NEST model families through the same lifecycle. It requires a
separately started native 1.0 `SessionService` that implements authenticated
negotiation, session generations, operations, authority, and receipts. The current
Engram native-1.0 migration is in progress but has not yet produced retained runner
evidence, so this runner remains **NOT RUN** against a certified compatible server.

The runner takes the initial authoritative `state_version` from `SessionOpened`,
constructs each `request-digest-v1` value with the independent Python algorithm,
correlates the authenticated terminal receipt, and advances its expected state only
from that receipt. It never guesses state after an absent or malformed reply. The
service must provision the runner's dev-loopback commander as the active authority
holder; payload self-assertion does not grant authority.

Reply ingress is a pure-Python implementation of the universal contract: the
binary socket reader caps bytes before allocation, requires one LF/CRLF-delimited
frame, decodes strict UTF-8, and scans duplicate decoded keys, nesting, node/member,
array, string/key, number, channel, and metadata budgets before `json.loads` builds
the admitted object. This developer runner therefore does not depend on the Rust
extension merely to claim native bounded framing.

The five-model test is only model-family transport breadth: LIF alpha/exp,
Izhikevich, Hodgkin–Huxley, and adaptive exponential integrate/stimulate/record
through one contract. It is not scientific validation, paper reproduction,
calibration, real-time certification, or a plant safety case.

Legacy cross-language scripts that rely on an Engram mock/bridge must remain on the
immutable wire-0.8 tag or be migrated end-to-end before use. Engram's current local
migration does not change that rule. `ncp-gateway` is a
same-wire 1.0 edge and cannot translate that backend. The explicit terminating
gateway is labelled migration evidence and cannot count as native 1.0
interoperability.

Release evidence first requires an adapter that exposes the verified transport
principal and binds it to `IdentityClaim`; the current Zenoh secure open path fails
closed. The later campaign must use installed artifacts and `production-secure`,
two non-Rust independent peers, exact normative/corpus digests, correct and
incorrect identity/ACL/cert cases, lifecycle plus all four planes, and the combined
fault/restart/backpressure subset. See
[`../RELEASE_READINESS.md`](../RELEASE_READINESS.md).
