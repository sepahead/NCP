# Exact Zenoh 1.9.0 metadata probe

> **Status:** quarantined, non-normative, non-shipping local-feasibility probe.
> It cannot authenticate an NCP caller and cannot satisfy a release gate.

The probe combines two different kinds of information that must not be confused:

- [`source-matrix.v1.json`](source-matrix.v1.json) binds conclusions to exact
  files from the pinned Zenoh 1.9.0 crate and upstream commit.
- [`src/main.rs`](src/main.rs) executes two explicit loopback TCP peers and tests
  what crosses subscriber, query, reply, session-info, and liveliness APIs.

The strongest live counterexample deliberately makes a publisher label a sample
with the receiver's Zenoh entity ID and an arbitrary sequence number. The receiver
observes those chosen values. The equivalent query and reply cases are also tested.
Omitting source information leaves it absent; Zenoh does not synthesize a verified
certificate principal. Liveliness events and replies likewise have no source
information in the observed path.

This does not prove an API field is absent. Absence is established only by the
exact source/API review; the live probe supplies counterexamples to treating
`SourceInfo` as authentication. Router ACL and TLS behavior is outside this probe.

Run the complete section check:

```bash
./run.sh
```

The command verifies source and lockfile identity, runs hostile verifier tests,
formats, lints with warnings denied, runs the live test, and requires the live
output to match
[`expected-result.v1.json`](expected-result.v1.json) exactly before emitting the
deterministic JSON observation summary.

The exact Zenoh graph contains `lz4_flex 0.10.0`, which the local RustSec database
flags as `RUSTSEC-2026-0041`. The affected block decompression calls are behind
Zenoh's `transport_compression` feature, and the source verifier rejects that
feature if enabled. This bounded reachability fact is not a vulnerability waiver:
the quarantined dependency graph must not ship, and a future feature change fails
the probe before execution.
The probe reserves an unused loopback port immediately before opening the listener;
another local process could win that small race, which produces a test failure,
never a false security pass.
