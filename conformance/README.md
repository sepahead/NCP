# NCP conformance corpus

The generated [`manifest.v1.json`](manifest.v1.json) makes the unreleased NCP
1.0 candidate corpus mandatory and self-describing. It currently requires 268
vectors: 261 stable vectors (209 behavior, 8 request-digest, 12 security-state
digest, 18 plant-profile, and 14 canonical JSON messages) plus 7 0.8-to-1.0
migration vectors.

The manifest records every vector ID, normative clause, source/pointer, state model,
resource budget, applicable role/implementation/transport, exact source hash,
corpus SHA-256 digest, and report requirements. Required skips, missing IDs,
duplicate IDs, partial reports, and unknown extras fail. Regenerate only through:

```bash
python3 scripts/generate_conformance_manifest.py --write
python3 scripts/generate_conformance_manifest.py
```

Directory roles:

```text
behavior/vectors.json                         semantic decisions and state sequences
security-state-digest/v1.json                 portable validated-security projection
plant-profile/v1.json                         closed profile/digest positive and negative cases
vectors/*.json                                one canonical stable message per kind
migration/v0.8-to-v1.0/channel-requirement.json
                                               explicit gateway positive/negative cases
vectors/bulk_observation.bin                  excluded offline BulkBlock fixture
baseline/released-baselines.v1.json           annotated-tag/commit/tree identity registry
baseline/v0.5.0 ... baseline/v0.8.0           immutable released snapshots
baseline/v1.0.0                               frozen candidate JSON audit snapshot
```

Rust is the reference behavior. TypeScript implements the stable semantic validator
and safety decisions independently. The deployment-profile checker independently
replays the portable security-state and plant-profile digest vectors in Python.
Python and C/C++ package bindings otherwise replay through Rust FFI and are binding
evidence, not independent implementations. Each harness must execute its exact
manifest-applicable set rather than choosing a convenient subset.

The binary fixture is explicitly excluded from stable transport conformance: bare
`NCPB` and `BulkObservation` are not stable 1.0 messages.

Run focused gates with:

```bash
python3 scripts/check_conformance_vectors.py
python3 scripts/check_profile_digests.py
python3 scripts/check_released_baselines.py
python3 scripts/check_buf_breaking.py
python3 scripts/check_behavior_vectors.py   # requires an installed candidate wheel
bun run check:behavior
cargo test -p ncp-core --all-features
```

A local zero-skip pass is necessary but not sufficient for release. Signed reports
must also identify the installed implementation version, full normative digest,
corpus digest, source revision, and exact executed IDs. Live transport/security/
fault evidence remains separate and is currently **NOT RUN**.

The released-baseline registry is also the only source for Buf comparison targets.
The initial `ncp.v1` candidate reports that no released same-major baseline exists;
it is not compared with incompatible `ncp.v0`. Once a v1 annotated release is added
to the registry, later v1 work compares with the latest registered v1 peeled commit.

See [`../NEURO_CYBERNETIC_PROTOCOL.md`](../NEURO_CYBERNETIC_PROTOCOL.md) and
[`../RELEASE_READINESS.md`](../RELEASE_READINESS.md).
