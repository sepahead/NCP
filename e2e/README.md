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
runner has no retained passing native-service evidence in this directory.
Its live integration status remains **NOT RUN**.
The separate [local reference profile](../docs/local-v1/README.md) uses another contract and does not qualify this runner.

Run it only against a separately provisioned numeric loopback endpoint:

```bash
NCP_E2E_HOST=127.0.0.1 NCP_E2E_PORT=28474 python3 e2e/nest_five_networks.py
```

Connection failure is reported as `LOCAL SMOKE RESULT: NOT RUN` with exit status 2.
The runner reports PASS only when all five closed-loop model-family scenarios execute and
pass. A partial scenario set is NOT RUN, while any attempted scenario failure is
FAIL. The runner stops after the first attempted failure. A failure after session
open can leave a server generation that the runner cannot safely close without the
exact authority and state version. The operator must reconcile or restart the
development service before retry. Continuing would hide the first defect behind
secondary session-ownership failures.

The runner takes the initial authoritative `state_version` from `SessionOpened`,
constructs each `request-digest-v1` value with the independent Python algorithm,
and validates each receipt's terminal outcome, request-digest correlation,
non-regressing authoritative state, and exact equality to the body identity
established by `SessionOpened`.
The current candidate has no approved nonrecursive projection by which an
independent client can recompute `result_digest` from the wire reply. The runner
therefore checks only that this member is a lowercase SHA-256 value and reports
its result-digest binding as **NOT EVALUATED**. It does not claim result-body
certification. It advances its expected state only from the correlated terminal
receipt. Equality is valid because a successful generic mutation can commit
without changing the versioned state. Regression is invalid. The runner never
increments or guesses state after an absent or malformed reply. The service
must pre-provision the runner's exact dev-loopback
authority lease and return that same active lease in the developer-only,
non-normative `SessionOpened.dev_smoke_authority` extension. The runner never mints
or acquires authority from payload bytes; self-assertion or a matching holder name
does not grant authority. A future-issued, expired, oversized, or generation-foreign
lease fails before the first mutation. Because this profile has no transport
authentication, the runner cannot authenticate the receipt's responder identity and
is not security evidence.

Each model-family scenario applies three 100 ms control intervals. The first
current is fixed by the case. Each later current is computed only from the prior,
terminally receipted spike observation:

\[
e_k = r-y_k,
\qquad
u_{k+1}=\operatorname{clip}_{[u_{\min},u_{\max}]}
\!\left(u_k+K_p e_k\right).
\]

Here, \(y_k\) is the observed spike count, \(r\) is the case target, and \(K_p\)
is a positive gain in picoamperes per spike. The clip operation keeps every
stimulus inside the declared case interval. The runner requires the literal `nest`
backend. It validates the exact resolved model and population, the closed provenance
member set, one fresh observation-stream position, the exact negotiated spike
series, and the 100 ms simulation-time advance before it computes the next command.
Unknown series members, an explicit null numeric array, and an undeclared unit or
recordable fail. Each spike timestamp must lie inside the newly advanced interval
and have one parallel positive NEST node ID. The receiver accepts any positive
first stream position because it can join after earlier positions. It then requires
one unchanged stream epoch and a strictly increasing sequence.
This is a bounded causal simulation loop. Three intervals do not prove convergence,
stability, timing qualification, scientific validity, physical effect, or an
independently recomputed result-body digest.

Reply ingress is a pure-Python implementation of the universal contract: the
binary socket reader caps bytes before allocation, requires one LF/CRLF-delimited
frame, decodes strict UTF-8, and scans duplicate decoded keys, nesting, node/member,
array, string/key, number, and channel budgets before `json.loads` builds the
admitted object. Its metadata check is a later recursive `meta`/`metadata`
name heuristic. It does not implement the proposed trusted-message-class and
decoded-path rule for `OpenSession.bindings[*].entity.meta`, and therefore does
not establish equal preallocation enforcement of the 256-entry ceiling. This
developer runner does not depend on the Rust extension for its generic bounded
framing, but the class-specific metadata gate remains open.

The five-model test is model-family closed-loop transport breadth: LIF alpha/exp,
Izhikevich, Hodgkin–Huxley, and adaptive exponential integrate/stimulate/record
through one contract. It is not scientific validation, paper reproduction,
calibration, real-time certification, or a plant safety case.

### Historical NEST and ecosystem compatibility result

A local NEST 3.9.0 probe on 18 August 2026 reached the Engram native-1.0 migration
bridge only after its developer security-state digest was explicitly aligned with
the NCP profile digest. The two programs selected different default
developer digests. The bridge then opened the first NEST session but did not
return the required pre-provisioned `dev_smoke_authority`. The runner rejected the
mutation before it could claim success. This is the intended fail-closed result.

That probe did not establish a plant feedback loop.
At that time, Crebain and Prisoma exposed wire-0.8 surfaces, while this runner required native wire 1.0.
Crebain lacked the selected body-authority and disposition path.
Prisoma provided observation without a current-tick action edge.
These observations describe the dated probe, not the current ecosystem implementation.
Current reference-profile ownership and remaining gates are recorded in the [local guide](../docs/local-v1/README.md).
This runner still requires separate installed qualification against its broader candidate contract.

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
