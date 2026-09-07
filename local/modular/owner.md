# Closed modular SDK owner under development

This SDK implements a synchronous owner and client for host-installed application types.
The Rust and Python implementations are independent.
Their tests use counter, byte, and finite tensor-consumer contracts.
Those contracts do not represent a scientific application or an installed ecosystem composition.

The core descriptor is [modular_profile.v1.json](../../ncp-core/src/modular_profile.v1.json).
Its schema family is `ncp.modular.request.v1` and `ncp.modular.response.v1`.
This family is a local profile schema, not NCP wire version 2.
The earlier `ncp.local-lockstep.v1` descriptor and envelopes remain separate.

## Installed application boundary

The host selects the application before exposing its channel.
The application supplies closed types for preparation, commands, imports, metadata, finish, results, imported results, and terminal results.
The application also supplies validators and its exact descriptor.
Each message binds both the core descriptor digest and application descriptor digest.

Rust uses associated types on `Contract` and `Application`.
Python uses separate installed decoders and frozen records.
The execution interface does not accept a method string with an arbitrary JSON value.
No request can install a schema, load a module, select an executable, or open a peer-selected path.

A generic trait cannot attest that a host implementation obeys its declared contract.
Application qualification must check descriptor closure, codec behavior, admission purity, scientific semantics, and installed artifact identity.
It must also check any application-owned memory or external resource limits.
Those qualification gates remain open.

The host must choose a fresh run and endpoint generation for each launch.
Constructing another owner with reused identity does not restore state or authorize resume.
The SDK keeps no unbounded history of prior generations.

## Exact requests and retained outcomes

Each request names a fixed binding, positive safe sequence, closed operation, and complete typed digest.
The binding names the profile, application, run, endpoint, and generation.
The maximum sequence is $2^{53}-1=9,007,199,254,740,991$.
Integer `-0`, floating sequences, booleans, and larger integers cannot identify an operation.

Universal JSON limits apply before generic decoding.
The codec rejects duplicate decoded keys, malformed Unicode, trailing data, and excess size or depth.
After typed decoding, the complete typed value must reproduce the admitted digest.
An omitted optional member cannot silently become an explicit null member.

The owner handles an exact owed duplicate before checking mutable application state.
This order matters after preparation, chunk append, or buffer release.
The original operation can have changed the state that admitted it.
Its exact retry returns the original retained bytes and performs no second execution.

One result remains owed until its exact acknowledgement.
A query can retrieve those original bytes by sequence and original request digest.
An unavailable result makes no claim about historical execution or release.
The owner stores one current ACK stamp, not an expanding release history.
Repeating that stamp cannot release a newer owed result.

The protocol predecessor identifies the last admitted result, including buffer operations.
Queries and ACKs do not change that predecessor.
The owner consumes an admitted sequence before application execution.
The client advances its next sequence only after an exact ACK for its committed result.

For example, preparation at sequence 1 produces result digest $r_1$.
After acknowledging $r_1$, the client can submit sequence 2 with predecessor $r_1$.
A pure input rejection leaves sequence 2 unused and preserves $r_1$.
The client can submit corrected input at sequence 2 without acknowledging that rejection.
Conflicts, unavailable results, and mismatched responses cannot use this transition.

## Reservation and execution boundary

Application admission reads state and returns `AdmissionDemand { inputs, outputs }`.
Admission must perform no I/O, external reservation, or backend mutation.
The core resolves every selected input and allocates every demanded output before consuming a sequence or buffer ID.
Failure during this staging phase releases only known core-owned allocations.

Entering the ticket consumes the operation identity and assigns monotonic buffer IDs.
The application receives an execution permit with only its selected input views and reserved output slots.
Each output write must extend its exact contiguous prefix.
Sealing requires every promised byte and publishes the same owned allocation.
An ignored input, write, or seal error prevents a complete result.

A local capacity preview is not a reservation.
A remote or durable storage reservation must be an explicit closed application operation.
Its exact receipt must precede dependent engine mutation.
Unknown cancellation cannot establish that external capacity is free.

A backend error, panic, invalid result, or incomplete output after entry consumes the sequence.
The owner retains a bounded indeterminate result when possible and retires the generation.
It never repairs that outcome into a favorable result or a clean pre-execution rejection.

Before commitment, the owner decodes the exact staged response with its installed output codec.
The decoded response must reproduce the complete typed digest.
Rust also requires structural equality between the original and decoded body.
Its result, imported-result, and terminal types therefore implement `PartialEq`.

This rejects `Some(NaN)` becoming JSON `null` and then `None`.
The digest comparison separately rejects signed-zero normalization.

Python validates finite scalars before serialization and rejects boolean values in installed integer slots.
A decoder failure after execution produces indeterminate retirement, including during finish.
Custom serializers, decoders, and equality remain trusted application implementations.

## Selected input leases

Each `InputSpec` contains an exact local `BufferRef` and expected manifest digest.
Admission accepts at most 24 unique selected references.
It checks generation, live membership, sealed state, and exact manifest identity before execution.
A stale, released, incomplete, duplicate, wrong-manifest, or excessive selection leaves the sequence and application state unchanged.

`ExecutionPermit.input(slot)` exposes one admitted immutable manifest and its read-only payload.
It grants no unnamed pool access, buffer release, import mutation, or new output demand.
The existing exclusive reservation ticket pins these selected entries during synchronous execution.
The input roster copies handles only; it does not duplicate payload bytes.

Rust ties each view to its permit borrow.
Several selected immutable views can coexist.
A private `Cell<bool>` latches misuse without granting shared output mutation.
Output writes retain an exclusive borrow.
Python expires the view wrapper when `execute` returns or throws, before ticket cleanup.
An extracted Python memoryview cannot be revoked.
The trusted application must respect that synchronous lifetime and separately account for retained aliases or copies.
Neither language's interface isolates a malicious installed application.

Import validation remains pure and must not cache payloads for later mutation.
The later mutating operation reads its explicitly admitted sealed view.
Imported-source membership and content joins do not establish producer authenticity or scientific validity.

The test consumers import actual finite `f32le` tensors with a closed two-dimensional shape.
Their application descriptors have distinct identities because their preparation and finish test schemas differ.
They are independent consumer controls, not one installed cross-language tensor application.
A later operation reads those bytes, sums the components, and adds the sum to application state.
An optional reserved output contains the computed `f32le` sum.
A sum outside finite `f32le` range retires after execution and publishes no successful output buffer.
Its result binds the exact input and output manifests.

Selected controls cover one changed byte, coherent changed manifests, nonfinite tensors, stale handles, and exhausted reservations.
They also check that ignored unnamed-input errors retire after entry.
These tests qualify the generic consumer seam only.
They do not qualify a camera, pretrained model, simulator, or graphics launcher.

## Buffer and metadata lifetimes

ACK releases the retained result frame only.
Producer buffers and receiver imports have separate explicit lifetimes.
Every receiver reserves the complete declared payload before accepting a chunk.
Payload reservations on different endpoints count independently.

For payload length $L$ and chunk bound $C=32,768$ bytes, the chunk count is $\lceil L/C\rceil$.
Each chunk must match its index, offset, length, canonical base64, and digest.
The final seal also verifies the complete payload digest.
Valid chunk hashes cannot substitute for that complete digest.

The SDK owns an immutable metadata record for each import.
The record binds the complete typed import descriptor and source byte manifest.
The SDK reserves metadata capacity before promoting an import.
Application validators receive read-only metadata and payload views.
They cannot alter core chunk indexing or bytes through this interface.

Sealing retains that metadata with the sealed buffer.
Exact abort or release removes the corresponding record.
A failed pure seal preserves incomplete bytes and capacity until explicit abort.
Retirement does not establish that a remote peer discarded its state.

Seal requests name the expected import request digest and source manifest digest.
The core checks these caller-known joins before promotion.
The result returns the exact core-owned receiver manifest alongside the application's typed result.
Independent verification checks receiver binding, reference, creation request, source manifest, and manifest digest.
These checks do not authenticate a producer or establish scientific validity.

A read request names the expected receiver manifest digest.
The owner checks that digest against its live handle before execution.
The client checks exact agreement with the returned chunk.
Applications do not reconstruct the core manifest privately to obtain this digest.

Finish requires zero live buffers, zero incomplete imports, and zero input or output demand.
The pool must remain empty after terminal validation.
Finish cannot publish fresh buffers after its empty-pool precheck.
Durable capture completeness remains an application obligation, separate from releasing memory buffers.

## Logical capacity accounting

### Definitions and scope

Let F = 65,536 bytes and C = 32,768 bytes.
A frame extent reserves F encoded wire bytes, including its bounded immutable-copy phase.
A parsed extent is a logical source/compact-JSON extent, not the native size of a Python or Rust object graph.
The raw JSON tree is charged by the admitted source bytes it represents.
The installed typed payload and its JSON projection are each charged by bounded compact-JSON content.
Core wrapper records, fixed keys, closed control messages, stack bookkeeping, and framing prefixes use the separate fixed metadata allowance.
Numeric values occupy their source or checked compact-JSON representation; this accounting does not equate Python object size with token length.

Python charges compact JSON scalars, escaped UTF8, keys, brackets, and separators before copying a projected child.
It counts Unicode width without first encoding an oversized string.
The complete envelope is bounded by encode_into before hashing or publication.
Its fixed wrapper metadata is separately covered while construction precedes that final complete-envelope check.
The digest checks bound copied key/string UTF8 independently, without imposing one language's numeric formatting on the other language.

An installed decoder can allocate arbitrary application objects before returning.
Those allocations, application-retained aliases/copies, accessor execution, external libraries, allocator headers, and tracebacks retained by caller code are outside this SDK logical model.
A qualified application must supply independent limits for them.
No row is a host attestation, physical allocation prepayment, or process memory guarantee.
Core output/import payload allocations and ticket metadata reservations still occur before the effect boundary.
Working extents are admission accounting placeholders; they are not all allocated as backing arrays in Python or Rust.

### Conservative distinct extents

No inactive digest scratch is silently reused to make the totals fit.
The following reservation counts all categories separately, including disjoint phases.

| Category | Owner | Client | Use |
| --- | ---: | ---: | --- |
| Core pool/ticket/context metadata | 131072 | 0 | Existing bounded manifests, outputs, identities and control records |
| Import metadata | 32768 | 0 | 24 × 1024 encoded records plus bounded staging/bookkeeping |
| Selected input metadata | 16384 | 0 | Two 24 × 256 input rosters plus 4096 fixed metadata |
| Complete frame extents | 6F | 6F | Existing four extents plus two framing/read-conversion extents |
| Parsed representation extents | 3F | 3F | Raw, typed, projected representations; assignments vary by phase |
| Digest/sort allowance | 131072 | 131072 | Streaming SHA state plus bounded borrowed-key row charge; projection stream is not materialized |
| Decoded chunk | C | C | Exact bounded decoded payload |
| Decoded Unicode source | F | F | UTF8-equivalent source text during strict scanner or json.loads |
| Scanner/token scratch | 2F | 2F | Ancestor key sets plus current key/number token; overlapping spelling and lstrip copy |
| UTF8/base64 scalar scratch | 2F | 2F | UTF8 sort keys, current scalar bytes, bounded escaped fragments, or base64 bytes and ASCII reencoding |
| Fixed client state | 0 | 4096 | Binding, digests, current query/ACK control records |
| Total | 1261568 | 1085440 | Excludes separately reserved payloads and caller/application storage |

The source scanner's captured key bytes come from disjoint regions of its bounded input.
A current number's spelling and sign-stripped spelling can coexist, so one extra F is explicit.
A captured key's temporary character list and joined value are at most 128 UTF8 bytes each.
Their duplication fits the second F because syntax separates that key from other captured content.
Object/list/hash-node allocator overhead is explicitly excluded, not inferred from these UTF8 bounds.

During hashing, source key UTF8 totals at most F after the text precheck.
Sorting retains borrowed-key rows within 130048 bytes and SHA bookkeeping within 1024 bytes.
Python's encoded sort-key strings and current scalar bytes use the separate 2F scalar category.
A canonical base64 string for one C-byte chunk is at most 43692 bytes.
Its intermediate encoded bytes and ASCII string total at most 87384 bytes, less than 2F.
The corresponding decoded C-byte payload has its own category.
Bounded JSON escaping has 256-character source fragments; simultaneous escaped Unicode and UTF8 fragments fit within 2F.

### Owner phase map

Each row states maximum participating representations, not the amount physically allocated at every instant.
All persistent metadata categories remain reserved throughout the owner lifetime.

| Phase | Complete encoded frames | Parsed extents | Other live categories |
| --- | --- | --- | --- |
| Framed receive before process | Retained + staging + prior loop ingress + new read bytearray + final read chunk + converted immutable bytes: at most 6F | None from process | Framing prefix/control metadata only |
| Strict ingress scanning | Retained + staging + current ingress; memoryview ingress can add immutable copy: at most 4F | None | Unicode source F; scanner 2F |
| Generic JSON materialization | Same at most 4F | Raw source tree 1F | Unicode source F; JSON token temporary within scanner 2F |
| Installed request decode | Same at most 4F | Raw input + constructed typed input: 2F | Digest/sort and scalar UTF8; no source scanner remains after successful parse |
| Request lossless rejoin | Retained + staging + ingress: 3F | Typed input + JSON projection: 2F | Digest/sort and scalar UTF8 |
| Pure input/output admission | Same 3F | Typed input: 1F | Input demand/spec clone and output ticket metadata; selected views copy no payload |
| Entered execute/semantic checks | Same 3F | Typed input + returned typed output: 2F | Application allocations separate; output payloads already reserved |
| Original output serialization | Same 3F | Original output + JSON projection: 2F | Input request has been dropped; scalar escaping/digest scratch |
| Strict outgoing scanning | Retained + staged candidate + ingress + immutable candidate copy: 4F | Original output: 1F | Unicode F + scanner 2F |
| Outgoing generic parse | Same at most 4F | Original output + raw output tree: 2F | Unicode F + JSON token scratch |
| Installed output decode | Retained + candidate + ingress: 3F after parse copy dies | Original output + raw output tree + decoded output: **3F** | Digest/sort and scalar UTF8; installed decoder-owned allocations separate |
| Decoded output rejoin | Same 3F; unowed retained slot reused deliberately | Decoded output + projected decoded output: 2F | Original is explicitly dropped; digest/sort and scalar UTF8 |
| Commit and borrowed publication | Retained + staging + ingress: 3F | None retained by owner | Fixed owed stamp only; caller copies require caller storage |
| Core read/append validation | Same at most 3F | Request and/or typed chunk/result, at most 2F | C decoded chunk plus 2F base64/UTF8 scratch |
| Import metadata accepted validation | Same at most 3F | Input and/or output, at most 2F | Admitted 1024-byte metadata trees/bytes use the separate 32768 category |
| Oversized import metadata staging | Same at most 3F | Typed request + returned typed metadata + projected metadata: at most 3F | The 1024-byte staging slot and fixed rejection are separate; failed metadata projection is not charged to the accepted-record allowance |
| Clean AdmissionError rejection | Same at most 3F | Current bounded preflight representations remain, at most 3F | Fixed rejection wrapper uses core metadata; application exception-owned allocations remain application storage |

A Python exception can retain the full current phase stack through its traceback.
Before a post-effect indeterminate diagnostic, process clears traceback, cause, and context, then exits the exception suite.
Only its closed stamp and reason cross that boundary.
Clean AdmissionError rejections still execute inside their exception suite and retain the current bounded preflight phase.
They add only a fixed rejection wrapper, not another full application-result projection.
Before post-effect diagnostic serialization, the exception object and its args must die.
The paired control checks an empty handled-exception context and release of an exception-owned failed object at diagnostic entry.
Rust explicitly drops its catch_unwind panic payload before diagnostic construction.
The failed phase is not added to the diagnostic phase as a second concurrent phase after these releases.
An unbound error or failed terminal diagnostic closes the channel without creating another correlated outcome.
If caller code retains the propagated exception, its traceback storage is caller-owned and grants no additional SDK execution.

### Client phase map

Client-held pending bytes remain reserved until matching ACK or clean rejection.
A direct verifier's caller-supplied original occupies the original parsed extent below.
Client.observe reconstructs its own original into that same extent.
An additional independently retained original/result is caller storage, not a second implicitly included extent.

| Phase | Complete encoded frames | Parsed extents | Other live categories |
| --- | --- | --- | --- |
| Begin command construction | Pending slot plus temporary output slot and returned immutable wire: at most 3F | Caller command + JSON projection: 2F | Scalar/escaping and digest/sort |
| Begin installed decode | Pending + new immutable request + verification frame: at most 3F | Caller command + raw request + typed request: 3F | Scanner/Unicode or digest phases as above |
| Ordinary dispatch receive | Pending + read bytearray + final chunk + converted bytes: at most 4F | None | Prefix/control metadata |
| Query/ACK dispatch receive | Pending + retained outbound query/ACK bytes + read bytearray + final chunk + converted bytes: at most 5F | Fixed control record only | Fits conservative six-frame reservation |
| Reconstruct original | Pending + inbound + verification frame: at most 3F | Raw original + typed original: 2F, then original + projection: 2F | Scanner/Unicode or digest/sort, sequentially |
| Verify response decode | Pending + inbound + optional immutable input copy + verification frame: at most 4F | Original request + raw response + decoded response: 3F | Scanner/Unicode first, then digest/sort |
| Response lossless rejoin | Same at most 4F | Original request + decoded response + JSON projection: 3F | Digest/sort and scalar UTF8 |
| Query shape inspection | Pending + inbound + bounded query wire/control: at most 3F | Original + raw shape: 2F | Query fixed control in 4096; shape dropped before full response decode |
| Query nested original reconstruction | Same at most 3F | Outer original + nested raw original + nested typed original: 3F | Bounded query metadata is separate |
| Apply result or ACK | Pending/inbound and optional outbound control: at most 3F | Original + returned result: at most 2F | No parsed result retained by client |
| Failure | Current row's objects may survive in propagated traceback | Same phase envelope, no diagnostic allocation | Client retires; caller retention is external storage |

Sixteen owners reserve 20,185,088 logical bytes, excluding payloads and clients.
Sixteen clients reserve another 17,367,040 logical bytes.
The composition payload ceiling remains 268,435,456 bytes.
These totals do not claim that all extents are simultaneously backed by allocated arrays.
They conservatively count categories that can be disjoint across phases.

The earlier two-parsed-output capacity argument was incorrect.
The current descriptor counts three such extents and the explicit frame/UTF8 phases above.
The prior codec tests remain functional evidence for their exact source, not proof of the superseded accounting argument.

## Channel retirement and open qualification

The host must supply deadline-aware I/O and a process lifetime guard.
The SDK does not install a runtime or sandbox policy.
EOF, partial framing, timeout, failed writes, and failed reads retire the channel.
A lost ACK preserves unresolved pending evidence and grants no transport retry or reconnect.
Direct inspection of an owned retained result grants no re-execution authority.

Typed sensor profiles, selected peer obligations, storage receipts, and scientific acceptance remain application-owned.
The actual CREBAIN runtime requires a separately qualified Bun, Node, browser, and Metal lifetime policy.
This SDK does not export CPU checkpoints or implement the required many-entity compositions.
Source controls cannot promote those open requirements into installed or scientific qualification.


## Outgoing-codec design review

The selected design combines installed decoding, Rust structural equality, and the exact typed-digest rejoin.
It closes a reproduced owner-commit failure without adding an application-specific exception.
The following alternatives were compared before implementation.

| Alternative | Main benefit | Decisive limitation or control |
| --- | --- | --- |
| Fixture-specific checks | Small edit | Another output type bypasses the fix |
| Semantic validator only | Existing interface | Boolean integer output was committed |
| Client-only rejection | Protects the receiver | Owner already reported successful finish |
| Decoder-only round trip | Rejects invalid closed shapes | Optional nonfinite values can collapse to null |
| Required finite wrappers | Strong application types | Generic outputs still need codec verification |
| Full strict Serde visitor | Checks all serialized scalar tokens | Adds a larger independent serializer surface |
| Application equality callback | Supports custom types | Duplicates the generic owner's obligation |
| Codec, structural equality, and digest | Reuses installed closed codecs | Requires explicit object-lifetime accounting |
| Dynamic schema engine | Supports runtime schemas | Adds an unnecessary installation authority |
| Arbitrary JSON outputs | Flexible payloads | Removes the closed application boundary |

Correctness requires invalid output to remain uncommitted.
Causality requires a consumed operation to remain consumed after output failure.
Resource accounting includes the transient verification frame and parsed phases.
Interoperability requires both decoders to accept the published meaning.
Maintenance favors a generic codec check over field-specific repair.

Selected controls cover prepare, application results, import sealing, and terminal results.
They include finite values, signed zero, optional absence, boolean integer errors, nonfinite values, and normalizing decoders.
These controls establish structural SDK behavior only.


## Input-lease design review

The selected design uses explicit bounded admission and borrowed input views.
Ten alternatives were compared through correctness, causality, interoperability, resource bounds, and maintainability.

| Alternative | Main benefit | Decisive limitation or control |
| --- | --- | --- |
| Cache during pure validation | Immediate later access | Hides mutation and ownership |
| Repeat bytes in each command | Simple consumer argument | Bypasses immutable import ownership |
| Expose the complete pool | Flexible access | Grants unrelated reads and lifecycle authority |
| Return local paths | Familiar file interfaces | Adds path authority and external state |
| Per-chunk callbacks only | Small scratch | Complicates complete-array consumers |
| Selected borrowed input views | Exact membership without payload copy | Requires explicit synchronous lifetime |
| Permanent application copies | Independent lifetime | Requires additional accounting and release rules |
| Shared-memory handles | Efficient transfer | Requires a separately qualified transport |
| Durable store handles | External replay | Adds storage transactions and authority |
| Implicit latest buffer | Short requests | Loses exact causal selection |

A capacity preview cannot substitute for an admitted ticket.
A view cannot convert a structural content join into producer authenticity.
The selected controls test real finite tensor consumption and preserve negative cases.
Installed application qualification remains separate.
