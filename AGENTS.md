# Agent Notes (NCP)

Operating rules for coding agents (and humans) working on the **Neuro-Cybernetic
Protocol**. NCP is a *published, versioned, cross-language wire contract* with
downstream consumers pinned by tag — so the cost of a careless change is not "a bug
in this repo", it is "every peer and binding silently breaks". Read this top to
bottom before editing. `CONTRIBUTING.md` is the fuller human guide; this file is the
distilled, non-negotiable agent brief.

## What NCP is (one paragraph)

A single versioned, transport-agnostic, typed **wire contract** that lets a running
NEST/Engram spiking network serve robots, UAVs, and analysis clients over four
QoS-differentiated planes (Control RPC, best-effort Perception, express safety-gated
Action, read-only Observation), with a safety-gated action plane and per-frame
provenance. `proto/ncp.proto` is the **normative schema**; `ncp-core` (Rust) is the
**reference implementation of behavior** (codec, safety governor, keys, version).
Python (`ncp-python`, PyO3), C/C++ (`ncp-cpp`, C ABI), and TypeScript (`ncp-ts`,
`@sepahead/ncp`) peers all speak the *identical* wire off that one contract.

## The wire rule (NON-NEGOTIABLE)

**Never silently break the wire.** A change is one of three kinds — know which before you touch anything:

- **Wire-invisible** (code/docs/build/tests only): fine, no version implications. `CONTRACT_HASH` unchanged.
- **Additive / backwards-compatible** (new *optional* field, new enum value, new message): non-breaking since v0.4. Unknown fields are ignored, so it does **not** require an `ncp_version` bump — but it **does** change `CONTRACT_HASH` (advisory), and it is a **MINOR** SDK bump.
- **Incompatible / breaking** (remove/rename a field, change a type, remove an enum value, change the meaning of existing bytes): a **MAJOR** wire bump. In the *same* change you MUST update all four of:
  1. `NCP_VERSION` in **both** `ncp-core/src/messages.rs` and `ncp-ts/src/client.ts` (the coherence guard checks they agree — this skew shipped once).
  2. the spec (`NEURO_CYBERNETIC_PROTOCOL.md`), the `.proto` (`proto/`), and the JSON Schemas (`schemas/`).
  3. the conformance test (`ncp-core/tests/conformance.rs`) so it pins the new contract — **fix the drift, never weaken the test**.
  4. the prebuilt TS package (`bun run regen`, or `bun run build` for source-only) and commit the regenerated `ncp-ts/dist` (git-tracked, shipped as `@sepahead/ncp`; a stale `dist` announces the wrong wire).

When in doubt whether something is wire-visible, **assume it is**. `CONTRACT_HASH` is currently `f05e328cad20959d` for the wire-`0.7` line (introduced in `v0.7.0`; latest release `v0.7.1`). The `0.6 → 0.7` cut changes both acceptance rules and the normative shape (typed errors and complete reserved bulk-observation metadata), and the hash includes NCP's JSON enum `wire string` and lifecycle transport `wire key` annotations as well as proto structure. It appears across proto/docs/bindings and must move in lockstep — if the wire changes, update **every** occurrence together or the parity guards fail.

## Safety is the crown jewel — fail CLOSED, always

The action plane governs a physical robot. Every error path in `ncp-core/src/safety.rs`
and `ncp-core/src/resilience.rs` must **fail closed** (HOLD / reject / no actuation),
never fail open (skip the gate / actuate). Historical bugs here were all fail-*open*:
a `NaN`/negative limit that made `NaN > 0.0 == false` skip the geofence; a backward
clock step that made a staleness check pass; an `Inf as usize` that authorised an
unbounded predictive horizon; a hostile `seq` that overflowed the jam detector. When
you add a branch, ask: "if this input is garbage/hostile/non-finite, does control
actuate?" If yes, it is wrong. The `CommandFrame` `mode` default must be **HOLD**,
never an actuating mode. Any safety change needs a regression test **and** a
cross-language behavior-conformance vector (see below) — a fix with no vector is a gap.

## Cross-language parity (the second crown jewel)

`ncp-core` is the reference. `ncp-cpp`/`ncp-ts`/`ncp-python` must make the **identical**
encode/decode, version-check, and safety decisions. A frame the Rust side rejects but
the C++/TS side accepts (or vice-versa) is a **major interop bug**. Two guards keep the
wire in lock-step — if either fails, the wire has drifted; fix the drift, do not weaken
the guard:
- `ncp-core/tests/conformance.rs` — Rust serde ↔ JSON Schema, plus JSON **and** binary golden vectors (`conformance/vectors/`).
- `scripts/check_proto_schema_parity.py` — `proto/ncp.proto` ↔ JSON Schema (field-set + enum wire-string parity).

The shared **behavior-conformance corpus** (safety `govern` vectors etc.) must exercise
every binding. When you fix a safety edge case in Rust, add the vector so C++/TS/Python
are held to the same behavior.

## Build, test, and the mandatory gates

```bash
# whole workspace except the Python binding (it links libpython)
cargo build --workspace --exclude ncp-python
cargo test  --workspace --exclude ncp-python

# TypeScript bindings (ts-rs regen + behavior)
cargo test -p ncp-core --features ts

# Python binding — needs a Python 3.11 env + maturin (cargo test -p ncp-python
# fails locally with a libpython rpath error unless the interpreter lib is found;
# CI/maturin handle this — it is an environment quirk, not a code failure)
maturin develop -m ncp-python/Cargo.toml

# the full cross-language SDK matrix (what CI runs)
scripts/check.sh
```

**Mandatory before any PR (CI enforces all):**

```bash
cargo fmt --all -- --check
cargo clippy --workspace --all-targets -- -D warnings
cargo test -p ncp-core           # the wire conformance test MUST pass
```

Do NOT add Claude/AI assistants as commit or PR co-authors — no `Co-Authored-By:`
trailer, no "Generated with …" line, no 🤖 marker.

## Releases and tags (immutable)

Release tags are **immutable**: once `vX.Y.Z` is pushed, never delete, re-point, or
force-update it — consumers pin NCP by tag, and a moved tag silently changes the bytes
they resolve to. If a release is wrong, cut a **new** tag (bump the version).

A tag must be *coherent*: the Cargo workspace version, `package.json`, `ncp-ts/package.json`,
and `CITATION.cff` must all equal the tag version, and the annotated tag must peel to the
commit it was cut from. Guards:
- `scripts/check-version-coherence.sh <tag>` — asserts the above (CI "version coherence" job).
- `scripts/check-consumer-pins.sh` — from a full local tree, verifies every consumer (self-registered via a `.ncp-consumer` descriptor; see `INTEGRATING.md`) pins one agreed tag.
- `scripts/repin-ncp.sh <tag>` — re-pins every discovered consumer to a tag in one shot.

**Release runbook (everything green BEFORE the tag exists — never tag, then fix, then move):**

1. Bump every version site together to `X.Y.Z`: `Cargo.toml` (`[workspace.package]` + the path-dep `version=`), `package.json`, `ncp-ts/package.json`, `CITATION.cff`, and the `README.md` pins/bibtex.
2. Bump the wire constants **only if the wire changed**: `NCP_VERSION` in both `ncp-core/src/messages.rs` and `ncp-ts/src/client.ts`; recompute `CONTRACT_HASH` if the proto's wire-semantic content changed.
3. Regenerate: `bun run regen` (ts bindings + `dist`) and `cargo run -p ncp-core --features schema --bin gen-schemas` (schemas). For a new wire line, freeze its baseline once, then run `python3 scripts/check_wire_baseline.py --verify-exact conformance/baseline/v<WIRE>.0` before tagging.
4. Run the full gate: `scripts/check.sh` + `scripts/check-version-coherence.sh <tag>` + `scripts/check-consumer-pins.sh`. All green.
5. Only now cut the annotated tag at that commit and push. If anything is wrong, fix and bump to the next patch — **do not move the tag**.

**Patch releases** (docs/tests/additive, wire unchanged) do not *require* a consumer
re-pin — same `MAJOR.MINOR` peers interoperate — but re-pinning is how consumers actually
*receive* the fixes.

## Known downstream consumers (keep in lockstep)

- **prisoma** (`../prisoma`) — read-only `ncp-observer` tap; pins `ncp-core`/`ncp-zenoh` by tag. Consumes only the data-plane message types + `ZenohBus` subscribe API. Its PID study needs the **observation-plane `seq` stamping** (an `ObservationFrame` echoing its driving `SensorFrame.seq`) to make its D-axis exactly aligned; as of wire 0.6 this is **normative** — a producer MUST echo the driving sensor `seq` (`>= 1`) on any `observation_frame` published on the observation plane, enforced publisher-side by `ncp-zenoh::publish_observation` (`seq == 0` remains the pull/RPC-reply form).
- **crebain** (`../crebain`) — full Commander/plant client; pins NCP by tag in **both** `package.json` (`@sepahead/ncp`, TS) **and** `src-tauri/Cargo.toml` (`ncp-core`/`ncp-zenoh`, Rust). Uses a broad surface: `Mode`, `Observable`, `StimulusKind`, `ChannelValue`, `ActionBuffer`, `check_version`, `ZenohBus`, `ZenohNcpClient`, `WebSocketNeuroSim`, `NCP_VERSION`. A wire-breaking change breaks crebain on **both** sides — verify against `crebain/src-tauri/src/ncp/mod.rs` and `crebain/src/neuro/` before shipping one.

## Project-agnostic rule

The SDK stays **project- and vendor-neutral**: no consumer-specific names, realms, or
assumptions baked into `ncp-core`/`proto`. `DEFAULT_REALM` is the neutral `"ncp"`; a
deployment (e.g. Engram) chooses its own realm at the edge. The honesty boundary is
binding: returned `V_m`/spikes are raw simulation outputs (`is_simulation_output=true`,
`calibrated_posterior=false`), never a validated reproduction.

## Useful pointers

- Spec: `NEURO_CYBERNETIC_PROTOCOL.md`. Versioning policy: `VERSIONING.md`. Encoding rationale: `README.md` §Encoding + `RATIONALE.md`.
- Safety/resilience design: `RESILIENCE.md`, `KNOWN_LIMITATIONS.md` (admitted gaps — keep it honest, do not understate).
- Security posture (action plane unauthenticated by default; ACL template): `SECURITY.md`, `deploy/zenoh-access-control.json5`.
- Integration contract for consumers: `INTEGRATING.md` (`.ncp-consumer` descriptor).
