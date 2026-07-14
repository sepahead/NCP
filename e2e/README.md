# NCP end-to-end evidence

This directory contains developer integration runners for the unreleased,
release-blocked NCP `1.0.0-rc.1` candidate. They are not the independent secure
live-peer campaign required for release.

Runner exit statuses are deliberately strict:

- `0` means every scenario required by that local smoke ran and passed;
- `1` means a configured run or its input failed;
- `2` means **NOT RUN** because a required service, peer, or scenario was absent.

`NOT RUN` is nonzero and must never be converted to PASS by CI or an orchestration
wrapper.

The self-contained Rust Zenoh tests exercise real sessions and transport plumbing,
but both endpoints use the Rust reference and therefore do not prove independent
interoperability. Run them with:

```bash
cargo test -p ncp-zenoh --test cross_session_rpc
```

[`nest_five_networks.py`](nest_five_networks.py) is a thin native-wire-1.0 client
intended to smoke five NEST model families through the same lifecycle. It requires a
separately started native 1.0 `SessionService` that implements complete identity and
security negotiation, session generations, operations, authority, and receipts. The
current Engram native-1.0 migration is in progress but has not yet produced retained
runner evidence, so this runner remains **NOT RUN** against a compatible native
service.

Run it only against a separately provisioned numeric loopback endpoint:

```bash
NCP_E2E_HOST=127.0.0.1 NCP_E2E_PORT=28474 python3 e2e/nest_five_networks.py
```

Connection failure is reported as `LOCAL SMOKE RESULT: NOT RUN` with exit status 2.
The runner reports PASS only when all five fixed model-family scenarios execute and
pass. A partial scenario set is NOT RUN, while any attempted scenario failure is
FAIL.

The runner takes the initial authoritative `state_version` from `SessionOpened`,
constructs each `request-digest-v1` value with the independent Python algorithm,
validates each receipt's terminal outcome, digests, correlation, state advance, and
responder identity-field presence, and advances its
expected state only from that receipt. It never guesses state after an absent or
malformed reply. The service must pre-provision the runner's exact dev-loopback
authority lease and return that same active lease in the developer-only,
non-normative `SessionOpened.dev_smoke_authority` extension. The runner never mints
or acquires authority from payload bytes; self-assertion or a matching holder name
does not grant authority. Because this profile has no transport authentication, the
runner cannot authenticate the receipt's responder identity and is not security
evidence.

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

[`run_cross_language_e2e.py`](run_cross_language_e2e.py) now quarantines the former
Engram MockBackend/Rust TCP path. Merely finding `bridge_server.py` does not prove
native-1.0 compatibility, and the incompatible historical TCP example was removed
because it omitted mandatory native-1.0 lifecycle context. The guard starts no
process, prints `RESULT: NOT RUN`,
and exits 2 until it is replaced by an end-to-end native implementation. Legacy
wire-0.8 smoke belongs to the immutable 0.8 tag. `ncp-gateway` is a same-wire 1.0
edge and cannot translate that backend; the separately labelled terminating gateway
is migration evidence, not native-1.0 interoperability.

Release evidence first requires an adapter that exposes the verified transport
principal and binds it to `IdentityClaim`; the current Zenoh secure open path fails
closed. The later campaign must use installed artifacts and `production-secure`,
two non-Rust independent peers, exact normative/corpus digests, correct and
incorrect identity/ACL/cert cases, lifecycle plus all four planes, and the combined
fault/restart/backpressure subset. See
[`../RELEASE_READINESS.md`](../RELEASE_READINESS.md).
