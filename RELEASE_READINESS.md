# Release readiness — NCP wire contract

Status of NCP's wire-0.7 **`v0.7.1` release**: can the `v0.7.x` line evolve
additively without breaking peers, and is the live medium + contract proven? This is
an honest, adversarially-reviewed assessment, not a green-badge claim.

**Verdict (wire `0.7`, latest release `v0.7.1`; checklist re-audited from the `v0.5.0`
foundation):** the implementation
closes acceptance, provenance, enum, error-frame, integer-precision, and hostile-bulk
gaps found after the `0.6` enforcement cut. `0.5` was the deliberate stable-wire cut
and `0.6` made `ncp_version` plus closed-loop `seq` normative; the
control-plane contract is proven end-to-end across a real process + language boundary,
over a real transport, with the safety authority and the version gate exercised on the
wire. NCP remains pre-1.0 (`0.x`, minor-is-breaking) by policy, with the residual
caveats called out at the end. The 0.7 JSON baseline is frozen, the release gates
pass, consumers are coordinated, and `v0.7.1` is the latest immutable tag.

## Where it stands

The control-plane contract flows end-to-end across a real process + language boundary,
over a real transport, **without NEST or `zenoh-python`** (the backend is separable
from the wire — engram's `MockBackend` emits real `Observation` frames):

- ✅ Two **independent Zenoh sessions** over a real tcp link drive `open→step→run→close`
  through the typed `ZenohNcpClient` + the version/advisory-contract handshake
  (`ncp-zenoh/tests/cross_session_rpc.rs`, readiness-polled).
- ✅ A **Rust** client drives the **real Python** engram server over localhost TCP
  (`e2e/run_cross_language_e2e.py` + `ncp-core/examples/ncp_tcp_client.rs`).
- ✅ engram's **real** `SessionService` serves the lifecycle across a process boundary
  (`engram/.../test_e2e_cross_process.py`, ubuntu smoke, NEST-free), with
  forward/backward-compat and malformed/unknown-frame robustness.
- ✅ All four peers decide identically on the contract functions (the behavioral corpus).
- ✅ The scientific-boundary discriminators hold on every reply over every medium.

## The release checklist

| # | Item | Severity | Status |
|---|---|---|---|
| 1 | **Safety governor over the wire** | release-blocking | ✅ `ncp-zenoh/tests/safety_governor_over_wire.rs`: a plant runs `SafetyGovernor::govern` on each `CommandFrame` received over a real Zenoh link; corpus-driven HOLD/ESTOP/clamp verdicts, and the **ESTOP latch survives the wire** (a breach latches; a subsequent clean frame is still ESTOP). |
| 2 | **Lossless additive enum handling** | release-blocking | ✅ Rust preserves unknown strings in `Unknown(String)`; JSON Schemas and TypeScript accept non-empty future strings while documenting known values; `Mode` grants authority only to exact `active`. The behavior corpus exercises the rule. |
| 3 | **Frozen JSON-wire baseline gate** | release-blocking | ✅ `conformance/baseline/v0.7.0/` freezes the released JSON projection; the recursive manifest protects additive compatibility and `--verify-exact` proves the audit snapshot is byte-identical at tag time. |
| 4 | **Wire-version single source + mixed-version e2e** | should-fix | ✅ Each peer + the corpus are cross-checked for `NCP_VERSION`/`CONTRACT_HASH` (`behavior_conformance.rs`, `check-version-coherence.sh`); an incompatible `0.6` peer is fail-closed against `0.7`, with the same-version happy path retained. |
| 5 | **new→old reply tolerance + nested unknown field** | should-fix | ✅ Reply-side + nested-message forward-compat tested (Rust + engram Pydantic); a pin asserts no wire model sets `extra='forbid'`. |

**Consciously deferred (nice-to-have, not blocking):** TS + C++ *live-transport* clients
in `e2e/run_cross_language_e2e.py` (cross-language decisions are already proven by the
4-peer behavioral corpus, and live transport by the Rust↔Python e2e), and a
cross-process bulk-codec round-trip (the bulk decoder's hostile-input fail-closed —
bad magic, lying length, allocation-bomb row count — is already comprehensively tested
in-process in `bulk.rs`, and the codec is byte-pinned + conformance-checked). These are
documented here rather than left silent.

## Residual caveats (disclosed limitations, by policy — not open blockers)

- **Pre-1.0 (`0.x`).** The wire may still change; minor-is-breaking, the version guard
  fails closed. Pin the latest immutable release, `tag = "v0.7.1"`.
- **Single reference implementation.** `proto/ncp.proto` is normative; `ncp-core` (Rust)
  is the reference and the other peers are bindings/mirrors verified by parity + the
  shared behavioral corpus. Python/C reuse the reference core and independent
  non-Rust live-transport clients are still deferred.
- **The default/open transport is unauthenticated.** The `mode`/`ttl_ms` governor is
  defense-in-depth, not network security. Run the shipped mTLS router + strict client
  profile or deploy on a trusted isolated network (`SECURITY.md`, `ROADMAP.md` P0).

**Bottom line:** the live cross-process loop is real and tested, and the forward-compat
and safety properties are proven on the wire. The frozen JSON baseline and completed
release gates make `v0.7.1` the latest immutable wire-0.7 release.
