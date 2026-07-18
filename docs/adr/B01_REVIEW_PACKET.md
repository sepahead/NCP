# B01 exact architecture review packet

This packet requests human, same-digest review of the eleven **PROPOSED** NCP
1.0 architecture decisions. It is not an approval record. It does not accept an
ADR, change the normative contract, satisfy B01, authorize a rebaseline, certify
interoperability or plant safety, or release NCP 1.0.

## Exact review subject

- ADR/prototype source commit:
  `81941954f33078aa6a8dd85d70e392aae5469246`
- ADR/prototype source tree:
  `dc2c433e5e09cce9f03e981d9cbed44f84e72d00`
- clean full-gate checkpoint:
  `a9e0f48520649becc5507fc7d0ba069e4e20af92`
- clean full-gate tree:
  `803380bc420b4e4723e3663ecceaf5652977fb3d`
- candidate: unreleased, release-blocked `1.0.0-rc.1`
- wire: `1.0`
- compact proto hash: `163acc57d8a62b66`
- complete normative digest:
  `9cae331742d01e9b164e029aa06c644e6b1886176d0816a6ef883af138355c90`
- exact `contract/manifest.v1.json` file SHA-256:
  `7a71920ebbd4df59e00a0f83026280de1e9395a545ecab1f879d13b1a1ba1e97`
- proposed registry file SHA-256:
  `e44cf8ba4e47558fcd768ce39dd48d64dd9262d96ff1502ed4f25bfc9d6850ba`

The later packet/evidence commit adds this review surface, the retained full-check
log, and generated coordination/audit mirrors; it does not alter the ADR bytes
below. A review is valid only for the exact ADR SHA-256 values it names. Any later
ADR edit invalidates that review.

## Decisions and required roles

| ADR | Exact content SHA-256 | Required reviewer roles |
|---|---|---|
| [ADR-001](0001-separate-simulation-and-plant-sessions.md) | `c379fd8d4d69c47dd7744a36da142164a0012279b2b3dafa0c230bba860c904b` | NCP maintainer; Engram owner; Crebain body owner; independent protocol reviewer |
| [ADR-002](0002-contract-identity-and-release-authorization.md) | `cd00a501f10d444eb23c7d8076de4f08862c3225c662ae9b0571fa8e4cd0f103` | protocol reviewer; release and supply-chain reviewer |
| [ADR-003](0003-authenticated-production-ingress.md) | `8aac232e1c60a74eb0875885fd84641f1186e4bfbf72b192787e02c83aa44545` | two independent security/cryptography reviewers; transport implementer |
| [ADR-004](0004-observer-attach-grants-and-revocation.md) | `cba3960513a4d40d1f4692580c3b4927bea57979f4703aab3c188f260b4a9656` | Prisoma owner; Galadriel owner; security reviewer |
| [ADR-005](0005-declared-stream-lifecycle.md) | `6760b9e545ccee75a2f8864d652603cd4b2e0d1e261fa89e56c319b7de56820e` | distributed-systems reviewer; Engram, Haldir, Galadriel, Crebain, and Prisoma stream owners |
| [ADR-006](0006-body-issued-authority-and-time.md) | `486501f2711aabf9addcc8b9fd4db2baaa49e125593591fbf8674f7220076053` | safety reviewer; distributed-systems reviewer; Haldir owner; Crebain owner |
| [ADR-007](0007-command-disposition-journal.md) | `c5411a4379ea8ae65887a7006ec233bae01f2279d026421c6ac366dde9406373` | plant/safety reviewer; Haldir owner; Crebain owner |
| [ADR-008](0008-extension-namespace-and-galadriel-separation.md) | `1379477feebd886823d1511af5df0b7a7019795aef9ee8023147a4ef0a5f56b6` | protocol reviewer; Galadriel owner; Haldir owner; Crebain owner |
| [ADR-009](0009-security-state-rotation-and-revocation.md) | `9adea1e3ad1a3a902860440ad2d3d88863e7eec7e1bd64ac50a048898a6c336a` | security reviewer; operations reviewer; supply-chain reviewer |
| [ADR-010](0010-plane-qos-retention-and-overload.md) | `9f67034f1b45a74ccbdd7726a387e58a411db5e5817f3a2042a20a1db94f213e` | real-time/performance reviewer; Engram, Haldir, Galadriel, Crebain, and Prisoma consumer reviewers |
| [ADR-011](0011-ecosystem-topology-and-handover.md) | `96d243fd41868a70fc00c0f309a5f87e0058f6fce5308e2c98d147e18f76421f` | every named consumer owner; pid-rs owner; independent security/distributed-systems reviewer; Crebain plant/safety reviewer |

The generated [proposed registry](decision-registry.proposed.v1.json) is the
machine-readable digest and role inventory. It remains non-normative, contains
zero review records, and is deliberately outside `contract/`.

## Ecosystem decision under review

The dependency and authority direction is standalone-first:

- NCP is a neutral provider and depends on no consumer application.
- Engram simulation responder and plant commander are separate optional roles.
- Direct Engram command and Haldir-gated command are mutually exclusive for one
  live body authority term.
- In gated mode, Engram sends a Haldir-local signed intent. Haldir creates a new
  NCP command under Haldir's principal and current Crebain-issued lease; Engram
  bytes never transfer identity or authority.
- Crebain remains the sole NCP body, lease issuer, final software actuator
  admission authority, and body command-disposition owner.
- Galadriel's NCP observer is read-only. Its separate default-off assessor is
  push-only and limited to `RECORD_ONLY` or authenticated `DENY_TIGHTEN`.
- Haldir owns local policy and applied-deny state. Its assessment disposition is
  an authenticated policy receipt, not a body command disposition or authority.
  Missing disposition never lets Galadriel infer `APPLIED_DENY`.
- Prisoma is read-only/offline; pid-rs is a protocol-neutral leaf; Cortexel is a
  labelled export sink. None is an NCP plant peer or command-path dependency.

Native v0.8-to-1.0 migration is a complete quiesced body-profile cut. Old
admission/listeners/principals/publishers and bounded queues close before a fresh
native session opens. Rollback is another complete cut with a fresh compatible
v0.8 incarnation. Neither direction permits dual-stack body admission or revival
of pre-cutover traffic. Generation and stream-epoch UUIDs are equality fences,
not counters.

## Current consumer baseline observation

These observations prevent copied files, active worktrees, or prerelease branches
from being mistaken for installed native-1.0 evidence. They are not review or
qualification receipts.

- Galadriel `12b8b05878fffcdf797405a4b31822e07948d3c0` is a local 0.9 source-candidate
  line whose candidate ref is pushed; its NCP compatibility remains historical
  v0.8, not native 1.0.
- Haldir `bb6c0a7b27bbc57fe9935f80e22d06ca3b60e8ba` documents the v0.8 Gate boundary
  correctly but is not a native-1.0 consumer receipt.
- Engram `dce24097b63161f4d24ad8ec1a20e0673bdc2c4c` has a native-1.0 migration in
  progress, but active unrelated work and copied protocol material establish no
  installed interoperability.
- Crebain `0a58a5b8dd799884ddb06f1308b1748216fab322`, Prisoma
  `63cff105e0e40281376e6f827d7782e9b351961a`, Cortexel
  `f49ff3554da95e26d9ba684c1e97c324e2597f16`, and pid-rs
  `adbd9026da1490a3c39663970ba4c2fc70a42376` retain the authority boundaries
  above. Active Cortexel/pid-rs work is unrelated and was not modified here.

## Preliminary challenge evidence

The retained result is
[`preliminary-architecture-8194195.v1.json`](../../evidence/implementation/working/B01/preliminary-architecture-8194195.v1.json),
SHA-256
`3f140dad12147500048644899f69893c1dd985d0001c900ec66b18143be51fe7`.
Its exact clean-source log is retained as
[`preliminary-architecture-8194195.log.gz`](../../evidence/implementation/working/B01/preliminary-architecture-8194195.log.gz),
SHA-256
`eb885f3c430e41f3386a860fc9cd74e23b4a1244ed94d03db281d7565d371603`.

Within their declared finite abstractions, the models explored 11,444 commander
composition states, 35 deny-lifecycle states, and 1,415 complete wire-cutover
states. All 23 registered Python mutations and four SMT mutations were detected;
all eleven registered SMT checks passed. Queue isolation, bounded parser/journal,
and local real-Ed25519 screens passed their explicit prototype bounds.

The complete local repository gate passed at `a9e0f48`. The raw log SHA-256 is
`8dcba99800e4af9ea7f672a51cadc8e91edbee1d5b9ff94cb5a2b18f38620daf`;
the retained deterministic
[`full-check-a9e0f48.log.gz`](../../evidence/implementation/working/B01/full-check-a9e0f48.log.gz)
SHA-256 is
`11042f9980566d0dbc5687957c2045f6dc902e7a2d212d9769dbc9d834e4b67a`.

Five usable exact `claude-fable-5` consultations are recorded in the
[consultation log](../research/b01-fable-architecture-consultations.md). The
latest response SHA-256 is
`080ad93775d6dec018a08efeadd49b0d57e6162a90f4bc7cf9a8b43199246d32`.
External-model advice is challenge input only and satisfies no review role.

## Reproduction commands

From an exact checkout of `a9e0f48520649becc5507fc7d0ba069e4e20af92`:

```bash
python3 scripts/check_implementation_ledger.py --self-test
python3 scripts/generate_implementation_ledger.py --check
python3 scripts/generate_decision_registry.py --self-test --check
python3 scripts/check_adr_examples.py --self-test
python3 scripts/generate_audit_artifacts.py --self-test --check
python3 scripts/check_audit_artifacts.py --self-test
prototypes/b01-architecture-evidence/run.sh
scripts/check.sh
```

Reviewers should independently compute the ADR SHA-256 values rather than trust
this packet. Local reproduction is useful challenge evidence but cannot replace
the required independent role and content-bound judgment.

## Required review focus

Review the selected ADRs through all three perspectives and the ten lenses named
in each ADR. In particular, try to find a counterexample involving:

- payload identity being mistaken for transport authentication;
- overlapping direct/gated leases or admission during handover;
- stale generation, term, lease, stream epoch, sequence, or delayed command;
- simulation state satisfying plant authority;
- assessment expiry, restart, retraction, disable, replay, forged disposition,
  queue overflow, or missing evidence widening permission;
- v0.8/native-1.0 dual admission or rollback revival of old traffic;
- observer/extension overload delaying control, disposition, watchdog, or
  fail-safe work;
- Prisoma, pid-rs, or Cortexel acquiring a hidden command-path edge;
- an unknown/default value granting capability, identity, success, or safety;
  and
- migration, packaging, or local tests being overstated as release or installed
  interoperability evidence.

## Review response template

```text
Reviewer identity:
Organization/team:
Reviewer role(s):
Independent of implementation owner: yes/no, with explanation
ADR ID(s) and exact SHA-256 reviewed:
Disposition for each: ACCEPT | REJECT | ACCEPT_WITH_CONDITIONS

Protocol/security/plant findings:
Consumer/runtime findings:
Operations/science/evidence findings:
Ten-lens omissions or counterexamples:
Conditions and exact resolution evidence required:
Commands/artifacts independently examined:
Timestamp (UTC):
```

An `ACCEPT_WITH_CONDITIONS` is not an acceptance until every condition is closed
against the same exact bytes. Model output, an AI review, an implementation-owner
self-review, a local green test, or a GitHub reaction does not satisfy an
independent reviewer role.

## Explicit non-claims and remaining gates

All ADRs remain `PROPOSED`; B01 remains `IN_PROGRESS`; the generated registry has
zero review records. The normative contract is unchanged. Canonical TLA+,
refinement, Kani, installed independent peers, live mTLS/ACL/rotation/revocation,
fault/soak, duration fuzz/sanitizers, performance qualification, signatures,
SBOM/provenance, clean-room reproduction, plant validation, all exact consumer
role qualifications, publication, and post-publication validation remain
separate `NOT RUN` or blocked gates. NCP ESTOP is not physical certification and
no universal zero-safe action is claimed.
