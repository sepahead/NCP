# Local profile contract

Status: candidate. This document does not release or qualify an installed application.

The [canonical descriptor](../../ncp-core/local-profile.v1.json) binds the local contract through one typed SHA-256 digest.
Its complete value is normative. It contains no external shape references.
The [Python copy](../../local/python/ncp_local/local-profile.v1.json) must have identical bytes.

The descriptor includes three contract layers.

| Layer | Required behavior | Boundary |
| --- | --- | --- |
| Ingress and owner | Bounded framing, fixed identity, role checks, exact outcomes, and serial lifecycle | Every endpoint enforces this layer. |
| Shared application data | Closed plans, snapshots, proposals, body results, and semantic joins | Selected application profiles enforce their shared types. |
| Application contract | Exact configuration, model support, scientific algorithms, and capture evidence | Each installed application owns its complete contract. |

The shared body validator checks shape, time, bounds, and digest syntax.
It cannot authenticate a neural producer or compare an external proposal without the original envelopes.
The body, run owner, and capture application must perform those joins.

The covariance shape check does not prove positive definiteness, calibrated NIS, or a valid probability model.
The neural model token does not prove which populations ran.
An advisory monitor result grants no command authority.

## Ten approaches considered

| Approach | Expected benefit | Failure mode or decisive control |
| --- | --- | --- |
| Profile name only | Small identity | Change a bound without changing the name. The identity remains ambiguous. |
| Mutable documentation links | Easy editing | A linked rule can change after qualification. |
| Raw implementation hashes | Exact source identity | Source identity cannot define independent implementation semantics. |
| Pinned prose alone | Human-readable closure | Structural errors still require a separate machine check. |
| JSON Schema alone | Standard structural validation | A valid shape can contain a wrong predecessor digest. |
| Struct-generated schema alone | Low field drift | Struct fields omit important mathematical and lifecycle requirements. |
| Executable rule language | One runtime rule source | A new interpreter creates another semantic and security boundary. |
| Formal state model alone | Precise transition analysis | Model checking alone does not validate actual parsers or scientific payloads. |
| Self-contained shapes and named assertions | Small, auditable contract closure | Independent positive and negative controls must check implementation parity. |
| Linked digest tree | Modular contracts | Every reference requires exact resolution and installation closure. |

The selected approach combines self-contained shapes, named assertions, and an explicit lifecycle.
It retains independent Rust and Python validation.
It introduces no received expression evaluator.

## Five review lenses

| Lens | Contract requirement |
| --- | --- |
| Science | Preserve units, delayed readout, missingness, and explicit limits on scientific interpretation. |
| Runtime | Bind each predecessor, operation, outcome, acknowledgement, and generation. |
| Security and provenance | Check bounded data before mutation. A payload cannot select its role or executable. |
| Statistics and generalization | Keep structural acceptance separate from calibration and actual producer evidence. |
| Maintenance | Require descriptor identity, package byte parity, and independent executable controls. |

## Shape and semantics

The descriptor uses JSON Schema 2020-12 for structural constraints.
Two explicit annotations describe requirements that standard schema validation does not express.

- `x-lexical-integer` requires an integer token without a fraction, exponent, sign, or Boolean substitution.
- `x-max-utf8-bytes` limits decoded UTF-8 bytes, independently of character count.

The test-only schema engine implements these two annotations.
Production parsers and validators enforce them independently.
Duplicate decoded keys, invalid Unicode, and aggregate resource limits are checked before generic object materialization.

Named semantic assertions add plan alignment, exact time, component widths, missingness, source joins, and digest verification.
Each assertion names existing positive and negative native controls.
These controls detect specific defects. They are not a formal proof of every possible input.

For example, let `n` be the number of entities.
Each snapshot has `6*n` values: three position values and three velocity values per entity.
Each proposed acceleration has `3*n` values.
Each readout has `6*n` counts for positive and negative populations on three axes.

With two entities, these widths are 12 observations, six acceleration values, and 12 spike counts.
An unavailable entity retains its fixed slice and an explicit availability flag.
Its inert zero values are not a successful observation.

Let one step last 20,000 microseconds, with a 1,000-microsecond readout delay.
The first completed readout interval is `(0, 19000]` microseconds.
The second interval is `(19000, 39000]` microseconds.
The lower endpoint is excluded. The upper endpoint is included.
The declared delay leaves a final uncompleted tail; the protocol does not label that tail as silence.

## Identity and lifecycle

The digest includes every descriptor member and named requirement.
Publication and qualification status remain outside the descriptor, in separate release records.
The contract identity does not change merely because immutable qualification completes.
Object member order and whitespace do not change the typed digest.
Changing a bound, schema, semantic requirement, or lifecycle rule changes the profile identity.

Numbers use exact IEEE 754 binary64 bits.
Negative zero remains distinct from positive zero.
Scientific values are not rounded to make two implementations agree.

Snapshot digest projection inserts null for omitted `nis` and `source` option fields.
Request and response digests preserve nested omissions exactly.
Each digest excludes only its declared root digest field.

One generation has one serial owner and at most one retained exact response.
An identical retry retrieves that response while it remains retained.
A digest-bound acknowledgement releases it. An old released operation never executes again.

A result query can retrieve an owed outcome after retirement.
It cannot resume application mutation.
A timeout or unknown execution retires the coupled generation.
A new launch requires a fresh generation.

## Qualification commands

Install the [test-only requirements](../../local/profile/requirements-test.txt) in the qualification environment.
The Python SDK has no added runtime dependency.

```sh
python local/profile/sync.py --check
cargo build -p ncp-core --locked --offline --example local_contract_probe
cargo test -p ncp-core --locked --offline --test local_profile_contract
PYTHONPATH=local/python NCP_LOCAL_CONTRACT_PROBE=target/debug/examples/local_contract_probe python local/profile/test_contract.py -v
```

The gate rejects a missing native probe or schema dependency.
It checks closed fields, declared bounds, named semantic controls, and the complete outcome matrix.
It also checks byte parity, typed digest parity, and rejection of the previous candidate identity.

After a descriptor change, regenerate every package projection and rebuild each consumer.
Then repeat installed application and operational qualification with the new identity.
Prior receipts retain their historical digest. They cannot authorize the changed contract.
