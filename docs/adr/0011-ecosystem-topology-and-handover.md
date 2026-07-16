# ADR-011 — Fix ecosystem dependency direction and plant handover

- Status: `PROPOSED`
- Task: `B01`
- Candidate: unreleased, release-blocked `1.0.0-rc.1`
- Normative effect while proposed: none
- Required reviewers: Engram, Haldir, Galadriel, Crebain, Prisoma, Cortexel, and
  pid-rs owners; independent security/distributed-systems reviewer; Crebain
  plant/safety reviewer

## Context

The ecosystem must remain standalone-first while supporting optional native NCP
roles. The unsafe ambiguities are:

- Engram simulation responder versus plant commander;
- direct Engram command versus Haldir-gated command;
- Haldir local permission versus Crebain plant authority;
- Galadriel observer versus deny-tightening assessor;
- standard NCP frames versus project extensions;
- observation/research consumers accidentally entering the control path; and
- pid-rs or visualization outputs being mistaken for identity, authority, truth,
  calibration, or role qualification.

## Proposed decision

### Dependency direction

NCP is a project-neutral provider and depends on no consumer application.
All application integrations are optional adapters absent from default builds
and startup.

| Component | Standalone boundary | Optional NCP boundary | Authority/evidence boundary |
|---|---|---|---|
| Engram | neural simulation without NCP or other applications | simulation responder and plant commander are separate adapters | simulation state authority is not plant authority |
| Haldir | signed local intent decisions without NCP/Galadriel | NCP commander and default-off Galadriel assessment receiver | local ALLOW/DENY is not body admission or execution |
| Galadriel | local/synthetic cross-sensor analysis | read-only NCP observer and separate assessment extension producer | observations/assessments never grant command or plant authority |
| Crebain | local body/research behavior without NCP | sole NCP body plus separate standard/extension telemetry producers | final software actuator admission and dispositions remain Crebain-owned |
| Prisoma | offline research and run-log analysis | read-only capture adapter | never publishes, commands, fills gaps, or enters the control path |
| pid-rs | protocol-neutral library/CLI | called only inside consumer-owned optional adapters | result/log grants no identity, permission, authority, or NCP role receipt |
| Cortexel | visualization/figure generation | consumes exported, labelled, non-authoritative artifacts if configured | never an NCP peer, observer grant holder, control dependency, or source of truth |

pid-rs depends on none of NCP, Engram, Haldir, Galadriel, Crebain, Prisoma, or
Cortexel. Cortexel does not become an NCP package dependency; producer-owned
exports terminate the trust boundary and retain source/provenance labels.

### Engram roles

ADR-001 separation is mandatory. The simulation responder and plant commander
use disjoint types, principals, manifests, endpoints, routes, state/replay
stores, credentials, and features. A responder-only build cannot publish action.

### Direct and gated plant modes

For one plant session generation, only one commander mode may hold a live body
lease:

- **DIRECT_ENGRAM:** Engram is the enrolled NCP commander and publishes new NCP
  commands under its current Crebain-issued lease.
- **GATED_HALDIR:** Engram holds no NCP plant lease. It sends a Haldir-local
  signed intent. Haldir authenticates and evaluates that intent, then constructs
  a new NCP command under Haldir's principal, declaration, idempotency context,
  and current Crebain-issued lease.

Haldir never forwards or re-signs Engram NCP bytes as if identity or authority
transferred. Crebain admits/applies/disposes both modes and remains the sole body
authority.

### Body-coordinated handover

Mode is an attribute of the current body-issued authority term, not an
application toggle. Handover uses ADR-006:

`ACTIVE(old mode/holder) -> STOP_OLD_ADMISSION -> HOLD_QUIESCING ->
RETIRE_OLD_LEASE_AND_STREAM -> PERSIST_HIGHER_TERM ->
GRANT_NEW_MODE/HOLDER -> DECLARE_NEW_STREAM -> ACTIVE`.

No old and new lease are live concurrently. Delayed old commands reject on exact
session generation, lease term/ID/holder, declared stream epoch, and sequence.
On crash ambiguity, Crebain restores into HOLD/reconnecting or retires the
session generation; wall-clock lease time never revives authority.

### Galadriel-to-Haldir composition

The optional assessor extension is push-only, default-off, distinctly
credentialed, and limited to `RECORD_ONLY` or `DENY_TIGHTEN`. Haldir applies:

```text
effective_permission = local_policy MEET fresh_verified_assessment
```

No assessment can create permission. However, lifecycle changes can widen
permission by removing a deny. Therefore retraction, expiry, extension disable,
base-policy widening, override, or restart reconstruction requires an explicit
authenticated monotonically versioned Haldir policy transition and audit record.
The configured absence posture may be record-only or deny-new-missions; it may
not turn missing evidence into a new ALLOW.

### Read-only and indirect components

Prisoma and Galadriel observers receive only bounded ADR-004 grants. They cannot
publish, declare streams, mutate lifecycle, acquire authority, ESTOP, or issue
dispositions. Gaps and missing variables remain explicit.

pid-rs operates on consumer-supplied protocol-neutral values. Its estimate can be
one input to application policy but has no authenticated actor, lease, command,
or outcome meaning.

Cortexel receives only labelled exported snapshots/figures. It cannot feed
runtime decisions unless a later separately reviewed application contract is
created; no such NCP edge is proposed here.

## Rejected alternatives

- Make NCP depend on, orchestrate, or certify consumer applications.
- Require NCP for any component's standalone core.
- Let Engram direct and Haldir gated commands contend under one live term.
- Let Haldir forward Engram command bytes or issue body leases/dispositions.
- Let Galadriel encode `ALLOW`, command, ESTOP, or reuse observer credentials.
- Put Prisoma, pid-rs, or Cortexel in the plant command path.
- Add consumer-specific fields to stable NCP messages.
- Infer installed compatibility from copied protocol files, manifests, or local
  tests.

## Illustrative gated flow

```json
{
  "intent_id": "80ad94de-e7b7-4b31-8b69-119d89a97511",
  "issuer": "engram-intent-a",
  "audience": "haldir-gate-a",
  "plant_session_generation": "00000000-0000-4000-8000-0000000000a2",
  "requested_effect": "mission-step",
  "expires_at_utc_ms": 1784200030000
}
```

After local ALLOW, Haldir creates a separate NCP `CommandFrame`; the intent is
audit correlation only and is never the command identity or lease.

## Invalid or hostile example

```json
{
  "kind": "command_frame",
  "identity": {
    "principal_id": "engram-commander-a"
  },
  "forwarded_by": "haldir-gate-a",
  "authority": {
    "issuer_principal_id": "haldir-gate-a"
  }
}
```

Haldir cannot transfer Engram identity or self-issue Crebain authority.

## Actors and state transitions

The composed model has orthogonal state:

- session kind: simulation or plant;
- plant mode: none, direct Engram, or gated Haldir;
- body lifecycle: init, hold, active, estop, closing, retired;
- current body lease: absent or one exact holder/term/ID;
- command stream: absent, live, or retired;
- Galadriel assessment mode: disabled, record-only, or deny-required;
- observer grants: independent bounded attachments; and
- research/visualization sinks: absent or read-only export consumers.

Only Crebain serializes plant mode/lease state. Observer and indirect sink states
do not participate in action admission.

## Bounds and resource behavior

Adapters, principals, endpoints, manifests, leases, intents, assessments, queues,
state stores, retries, handover time, observer grants, captures, run logs, and
exports are finite. Optional components cannot borrow reserved action/control
capacity or become startup prerequisites for unrelated modes.

## Threat and hazard analysis

The decision addresses split brain, identity laundering, stale delayed commands,
simulation authority confusion, deny lifecycle widening, observer actuation,
extension route confusion, research feedback, and hidden dependency cycles.

The strongest composed counterexample is: a body/commander handover overlaps a
Haldir restart that loses applied deny state while a delayed old command remains
buffered. If exclusivity is checked only during configuration, deny state fails
open, or the body checks only wall-clock lease expiry, every component can appear
locally plausible while the old authority chain actuates. The ADR-006 exact fence,
body serialization, durable/non-widening Haldir recovery, and continuous mode
invariant jointly reject that trace.

Prisoma and pid-rs must not be inserted into this counterexample's command path;
their required property is precisely that they have no such edge.

NCP does not certify physical safety, universal safe action, scientific
calibration, field validation, or command usefulness.

## Formal properties

A bounded TLA+/state-machine composition shall include two commanders, two body
generations, several lease terms, opaque stream epochs, delayed/reordered/
duplicated commands, crash at every handover step, Haldir restart, Galadriel
mode/TTL/replay, observer load, and state-store uncertainty.

Required invariants:

- at most one commander holds live plant action authority;
- every admitted command matches the exact current body fence;
- no permission widening occurs without an authenticated Haldir transition;
- no simulation grant satisfies plant authority;
- no observer, Prisoma, pid-rs, or Cortexel state changes action admission;
- extension overload cannot block body fail-safe/disposition work; and
- every accepted command has a body disposition/query path.

## Migration

Provider ADRs and rebaseline land first. Consumer tasks then implement separate
optional adapters against exact immutable NCP commits. Engram migrates responder
and commander roles separately; Haldir adds a native commander and separate
assessment receiver; Galadriel adds observer and assessor roles; Crebain adds the
body and separate producers; Prisoma adds read-only capture. pid-rs and Cortexel
receive no NCP peer role or aggregate qualification receipt.

## Operational recovery

Each mode has explicit startup diagnostics and no hidden fallback. Missing
optional components leave their mode unavailable without breaking standalone
cores. Handover ambiguity stays HOLD and is reconciled through body queries.
Assessment uncertainty follows non-widening Haldir policy. Observer/capture/export
gaps remain visible.

## Compatibility and rollback

Cross-repository work is not atomic. Each repository commits and pushes one
passing slice, then pins the exact prior provider/consumer subject. Rollback uses
complete compatible cuts and preserves immutable 0.8 history. No movable `main`
pin, copied file, or manifest-only repin establishes migration.

## Open questions

Exact extension IDs, package feature names, numeric handover bounds, and
deployment topology are B03 and implementation inputs. They cannot change the
authority, dependency, standalone, deny-only, read-only, or protocol-neutral
decisions above.

## Ten-lens review

1. Semantics: every edge, payload, role, and owner has one meaning.
2. Security: identities cannot transfer through forwarding or optional adapters.
3. Safety: Crebain remains sole body/final software actuator authority.
4. Lifecycle: handover, restart, TTL, mode, and absence are explicit.
5. Resources: optional roles cannot starve control or become hidden prerequisites.
6. Migration: provider-first exact pins avoid private forks and mixed wires.
7. Science: simulation/PID/observer/figure outputs retain non-claim boundaries.
8. Operations: standalone modes, recovery, diagnostics, and incident ownership
   are executable.
9. Evidence: composed faults and nine exact NCP role receipts remain distinct;
   pid-rs and Cortexel receive no peer receipt.
10. Governance: each adapter/schema/key/namespace/support boundary has an owner.

## Ratification record

No required owner, independent distributed-systems/security, or plant/safety
review is recorded. Exact Fable 5 advice is challenge input only and does not
satisfy any reviewer role.
