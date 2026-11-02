> Dated record of the review of the improvements that NCP 2 adopted, deferred, or dropped, written on 23 October 2026 and added to the repository on 2 November 2026 without changes to its text. The [design record](../NCP-2-DESIGN.md) and the [specification](../../../spec/NCP-2.md) govern; where this record and they differ, they are current.

# NCP 2 improvement council, 23 October 2026

Question: which improvements to NCP 2 are justified, and which keep NCP fast, low-lag, competitive,
extensible, and lean? Candidates came from the coordination question (global order, atomic steps,
consensus), the digest-cost question, and the benchmark pilots.

## Councils and lenses (50)

| Council | Lenses |
| --- | --- |
| Correctness (1–9) | 1 safety (no wrong execution), 2 liveness, 3 exactly-once, 4 ordering, 5 failure atomicity, 6 crash recovery, 7 determinism, 8 model-checkability, 9 conformance testability |
| Performance (10–17) | 10 latency of a small call, 11 latency of a large call, 12 tail latency, 13 throughput, 14 memory, 15 CPU per byte, 16 cost when the feature is unused, 17 scalability in sessions |
| Extensibility (18–25) | 18 forward compatibility (old peer meets new peer), 19 backward compatibility, 20 versioning without fragmentation, 21 capability discovery, 22 namespace hygiene, 23 profile layering, 24 language parity, 25 third-party bindings |
| Operations (26–32) | 26 deployment, 27 observability, 28 debuggability, 29 misuse resistance, 30 configuration surface, 31 maintenance burden, 32 dependency hygiene |
| Science (33–38) | 33 reproducibility, 34 provenance, 35 evidence strength, 36 replay, 37 audit, 38 standards alignment (FMI, W3C Trace Context, OpenTelemetry) |
| Robotics and HPC (39–45) | 39 physical-world safety, 40 clocks and time, 41 multi-agent fit, 42 fleet fit (lossy networks), 43 MPI/cluster fit, 44 real-time fit, 45 energy |
| Competition (46–50) | 46 against gRPC, 47 against ZeroMQ, 48 against Zenoh and DDS/ROS 2, 49 against MUSIC and NRP-core, 50 justification of NCP's existence |

Fundamental limits applied throughout: no deterministic consensus on an asynchronous network with one
crash (FLP); two-phase commit is safe but blocks if the coordinator fails after yes votes; lossy links
give no common knowledge (two generals); physical actions cannot be undone.

## Verdicts

### A. Unknown codes are handled by their outcome (spec 7.5)

Lenses 18, 20, 25 decide it: without the rule, every new code (for example for a later profile)
breaks every deployed 2.0 client, which then reads the response as a bad frame. With the rule,
`rejected` keeps meaning "not executed" and an unknown `ended` code means "possibly executed", which
is the conservative reading (1, 3). Cost 0 (10, 16). Risk: an implementation typo in a code is
accepted; conformance vectors catch implementation codes (9). **Adopt (done). Add tests.**

### B. Reserved `ncp.` names (spec 15)

Lens 22: `ncp.array` already uses the prefix; reserving `ncp.` for operation names and body members
lets profiles appear without colliding with application names. Cost 0. The planned reservation of the
`open` member `resume` is unnecessary: the `open` body is NCP's namespace already, and an owner rejects
unknown `open` members with `body_invalid`, which a newer client can detect (18). **Adopt rules 1–2;
drop rule 3 (`resume`).**

### C. Clients ignore unknown members of the `open` response body (new)

Lenses 18, 21: an owner can later announce capabilities (for example a `features` list) in the `open`
response without breaking 2.0 clients, if clients ignore members they do not know. Owners keep
rejecting unknown `open` request members, so a newer client learns cleanly that an older owner lacks a
feature. Cost 0. **Adopt now** (spec 7.1 and both SDKs, with tests).

### D. Optional digest comparison (spec 3.4)

Measured: 34.9 → 24.6 µs at 1788 spikes and 974 → 568 µs at 1 MiB (Rust, both ends). Identities, the
hash chain, and transcripts do not change (3, 33–37). Misuse risk (29): turning it off with a program
in between (for example a recording proxy) hides damage; the documentation states the conditions, and
the default stays on. **Keep.**

### E. Hashing while receiving (overlap of the receiver's hash with the transfer)

Measured: no gain on pipes (974 → 940 µs at 1 MiB); the receiver's copy and hash run in series either
way. Only streaming at both ends would overlap the two hashes, which couples the owner to the binding
(31) and gains nothing below 64 KiB (10). **Rejected; recorded as a negative result.** Reconsider only
for a consumer that sends frames of megabytes at high rates.

### F. Chained transcripts (new; replaces the "owner journal" idea for ordering)

The planned owner journal would give a verifiable total order across an owner's sessions. A smaller
change gives the same: each transcript record carries a chain value, SHA-256 of the previous chain
value, the record kind, the time, and the frame's digest field. The last chain value then commits to
every record and its order (35, 37), so a transcript that one owner shares between all its sessions is
a tamper-evident total order across those sessions (4, 33, 36). Cost: one SHA-256 of 73 bytes per
recorded frame, about 0.15 µs, and 32 bytes per record; nothing when no transcript is written (16).
NCP 2 transcripts are new, so the format can include the chain from the start (19). **Adopt now**
(spec 10, both SDKs, verifier).

### G. Causal references `ncp.refs` (new profile)

A request or stream message may list, in the body member `ncp.refs`, the identities of frames that it
depends on. Because identities are SHA-256 digests, a frame can only name a frame that existed before
it; the references therefore form a happens-before graph across sessions, owners, and streams that no
one can backdate (4, 34, 35). A standard member name lets generic tools, such as the verifier and
Prisoma, build that graph without knowing each application's schema (27, 28, 33). It complements, not
replaces, W3C Trace Context: trace identifiers correlate, digests prove (38). Cost: 67 bytes per
reference, only when used (16). **Adopt now** (spec, verifier across several transcripts, both SDKs).

### H. Rounds (agreement on the inputs of a step, one owner, many agents)

An owner that serves N agents applies round k only when it has round k from every agent (or a deadline
passes), in a fixed order, and returns to each agent the list of request identities that it applied.
This makes multi-agent steps deterministic and verifiable (7, 33, 41) — the co-simulation master step
of FMI, NRP-core, and MUSIC, with exactly-once and evidence added (49). Needs no frame change: it is
owner behaviour plus the reserved names `ncp.round` and `ncp.round_record`. Liveness (2): a dead agent
must not stop the others; a deadline and an exclusion policy are required. **Adopt as an SDK helper
with the multi-agent benchmark**, Python first, Rust with the first Rust consumer.

### I. Session resume after an owner crash

Removes most `owner_failure` outcomes, but only if the session state is durable before each response
(an fsync per request: milliseconds on macOS, against 10 µs calls — lenses 10, 12) and the
application's own state is restored too. NCP's main owners (NEST) cannot restore their state, so resume
gives little in the core domain (41, 43). **Deferred.** Recovery today: checkpoint in the application,
open a new session, and use `status`-style application operations. Reconsider for a stateless command
service that needs it.

### J. Two-phase actions across owners (`ncp.prepare`, `ncp.commit`, `ncp.abort`, `ncp.status`)

NCP makes each phase exactly-once and auditable (3, 37), but the protocol keeps 2PC's limits: it blocks
if the coordinator fails after yes votes, and a "run at time T" variant needs synchronized clocks and a
bounded-delay assumption (39, 40). Needs a model check with crashes and losses before release (8).
**Deferred until a consumer needs it** (for example coordinated drone manoeuvres). The `ncp.` names are
reserved; the design record describes the pattern with today's NCP.

### K. Consensus

Replicated owners need a consensus algorithm (Raft, Paxos) that is safe always and live only under
partial synchrony. NCP must not embed one (31, 32): use an existing service (etcd, openraft) and carry
its messages over NCP sessions if wanted. **Documentation only.**

### L. Zenoh binding

Needed for fleets: discovery, many subscribers, lossy links (42, 48). Optional package so that the core
keeps three dependencies (32). **Planned after the core benchmark campaign.**

### M. PyO3 accelerator for the Python SDK

Pilots: Python NCP 2 is already the fastest Python protocol for small and medium calls (43 µs against
55–117 µs for ZeroMQ, Zenoh, HTTP, and gRPC). An accelerator adds a compiled build to a stdlib-only
package (26, 32). **Decide from the campaign results.**

### N. Sender-side streaming of the digest

Would overlap the sender's and the receiver's hashes for frames above 64 KiB (11). Couples the owner to
the binding (31). **Deferred** with the same condition as E.

## Second pass: no slop

The owner asked for a masterpiece without useless functionality or busywork. Every "adopt now" item
was checked again against one question: does it do work that nothing else in NCP already does?

- **F (chained transcripts): dropped.** The claim that a shared transcript gives the owner's total
  order of execution is false: a transcript records the order of arrival, and with one thread for each
  session the execution order can differ. The order that matters for replay must be made
  deterministic (H), not recorded. The rest of F's value already exists: the identity of a session's
  last response commits to every accepted exchange (now stated in spec property 7.7.6).
- **G (causal references): deferred.** Applications can put identities in their bodies today. A
  standard name and a cross-transcript verifier pay off only when a tool needs causal graphs; none does
  yet. The reserved `ncp.` prefix keeps the option at no cost.
- **A, B, C: kept.** They cost nothing at run time and prevent a real break: without them, the first
  new code or `open` member forces a new protocol version for every deployed client.
- **H (rounds): kept, but built with the multi-agent benchmark,** so that a real workload, not a
  speculative design, shapes it.

## Implementation now

A (with tests), B (without `resume`), C (spec sentence and tests; the clients already behaved so),
and the session-commitment sentence in property 7.7.6. H with the multi-agent benchmark. Everything
else is deferred or documented with its condition for reconsideration (design record section 11).
None of these changes adds work to a call.
