# Modular local SDK under development

This component implements bounded payload primitives and a closed generic request owner under development.
It is not an installed application profile, launcher, or release.
The existing `ncp.local-lockstep.v1` descriptor and envelopes remain unchanged.

The Rust and Python modules independently implement chunks, manifests, owned buffers, imports, and logical capacity checks.
The [owner contract](owner.md) adds request admission, retained outcomes, acknowledgements, local reservation tickets, selected input leases, and terminal resource checks.
Its execution interface uses statically installed closed types.
Installed application schemas and application completeness remain separate requirements.
The SDK provides no arbitrary JSON operation tunnel.

`TrustedHostCreationContext` is a local host API.
Its constructor validates shape and binding only.
It does not attest prior request verification.
The host must supply its already verified complete request identity and causal predecessor.
It must never copy these fields from peer-selected body data.
The closed request owner constructs this context from its verified request before invoking a producer.
The host must create only one pool for each fresh endpoint generation.
Reconstructing a pool does not restore its prior counters or grant same-generation resume.
Pool counters do not implement request idempotency.

The host installs an exact semantic-digest roster before use.
An accepted digest identifies a host-selected semantic contract.
Digest membership does not validate dimensions, scalar type, layout, units, sensor clocks, or numeric policy.
The primitive does not load a schema, import a module, open a path, or validate sensor physics.
The host must validate payload semantics against its installed application contract before publication or scientific use.
Source-manifest verification checks the declared source binding and exact supplied data.
It does not prove that an imported artifact came from a live producer.

## Working-state bounds

| Item | Bound |
| --- | --- |
| Complete JSON frame | 65,536 bytes, excluding its four-byte length prefix |
| Decoded chunk | 32,768 bytes |
| One complete payload | 8,388,608 bytes |
| Endpoint payload reservations | 67,108,864 bytes |
| Endpoint live entries | 24 sealed buffers and incomplete imports combined |
| Incomplete imports | 12 within the same 24 entries |
| Composition | 16 endpoints and 268,435,456 reserved payload bytes |
| Serialized manifest | 4,096 bytes |
| Installed semantic roster | 64 SHA-256 digests |
| Logical metadata reservation | 131,072 bytes per endpoint |
| Retained outcome | One 65,536-byte frame per endpoint |
| Ingress and output staging | One 65,536-byte frame for each direction |
| Typed-digest staging | 131,072 bytes per operation |
| Owner/client frame accounting | Six logical frame extents, including verification and framed-read copies |
| Parsed and UTF8 accounting | Three parsed extents plus explicit source, scanner, and scalar scratch |
| Selected input metadata | 16,384 logical bytes; 24 unique local references |
| Decoded chunk scratch | One 32,768-byte chunk per operation |

These are logical SDK bounds, not process RSS or GPU-memory guarantees.
Payload reservations include full incomplete-import lengths before any chunk is accepted.
Producer buffers and receiver assemblies count independently, even when their hashes match.
An endpoint without payload buffers may reserve zero payload bytes.
It still consumes one endpoint slot and its declared frame and metadata reservations.
Conversion from incomplete to sealed keeps the same reservation and entry.

Persistent metadata has bounded cardinality and closed fields.
Each of 24 manifests has at most 4,096 serialized bytes.
The 64-entry semantic roster uses fixed 64-byte ASCII digests.
Bindings, counters, and entry categories have fixed field counts and bounded strings.
The logical metadata reservation is 131,072 bytes.
Language object headers and allocator overhead are not measured by that serialized-size argument.

Each operation is synchronous and permits one staging operation at a time per pool.
The Python caller must serialize access to one pool.
Rust requires an exclusive borrow for mutation.
Returned chunk frames are caller-owned bounded copies.
Callers that retain several copies must account for them separately.
The owner enforces its retained-frame and staging cardinalities.
The [owner contract](owner.md#logical-capacity-accounting) accounts for parsed representations, import metadata, and clients separately.

The producer copies admitted input into owned storage before hashing and publishing its manifest.
This API receives bytes that already exist.
It does not reserve a future sensor batch before simulator advancement.
The owner supplies local producer reservation tickets.
An application must obtain its required ticket before simulator advancement.
External storage reservations require separate explicit application operations and receipts.
A usage preview is not a reservation.
The importer reserves its complete destination storage before accepting data.
Contiguous chunk admission verifies length, index, offset, manifest identity, canonical base64, and chunk digest before writing.
Sealing verifies the complete payload hash.
Failed admission preserves counters, reservations, and existing buffer contents.

Acknowledging a creation result must not release the corresponding buffer.
Buffer release and incomplete-import abort affect only an exact named owned entry.
An unavailable handle does not prove that an earlier release or abort succeeded.
The primitive API has no remote outcome classification or automatic retry.
The client retains uncertain dispatches and prevents further operations on that channel.

## Open application boundaries

Installed sensor admission remains unimplemented.
The test-only tensor consumer checks finite `f32le` components and exact two-dimensional byte lengths.
Those controls do not implement an installed sensor profile.
The byte manifest carries no tensor dimensions, scalar type, layout, units, or sensor clock.
This refines the earlier combined-manifest proposal without weakening typed admission.
The reviewed successor uses a separately named closed sensor or tensor manifest.
That object binds this exact byte-manifest digest and every required typed field under its own digest.
The installed application result must bind the complete typed object.
The receiver must verify dimensions times scalar width against the payload length before import reservation or allocation.
No field may be added silently to a published byte-manifest v1.
Primitive publication alone cannot qualify typed sensor transfer.

The actual CREBAIN environment uses Bun, Node, Playwright, and Chromium Metal.
Its runtime does not fit the existing reference body's executable or Engram sandbox policy.
A modular launcher requires its own process, network, lifetime, and cleanup contract.
The typed bridge must preserve declared binary representations, including permitted signed zero.

CPU fork handles may remain local capabilities in the first sensor-transfer profile.
A 64 MiB serialized checkpoint cannot fit in one 8 MiB buffer.
Checkpoint export requires a separately typed segmentation contract.
Capture-only import grants no live branch, restore, or scientific completion authority.

The frozen composition council matrix remains the application acceptance plan.
The owner has a separate reviewed SDK boundary matrix.
Primitive and owner controls cover only their named structural requirements.
Real compositions, maximum sensor workloads, and installed qualification remain open.

## Focused verification

Build the test-only native probe before running cross-language controls.

```sh
cargo build --manifest-path local/rust/Cargo.toml --locked --examples
NCP_MODULAR_OWNER_PROBE="$PWD/local/rust/target/debug/examples/modular_owner_probe" \
  PYTHONPATH=local/python python3 -m unittest discover -s local/modular -v
```

The small-vector selection remains fixed.
A separate maximum structural case transfers all 256 chunks of one 8 MiB payload between Python and Rust.
Its negative changes the final byte and recomputes that chunk's hash.
Complete payload sealing must still reject the changed data.
This selected boundary control is not a sensor workload or performance benchmark.
