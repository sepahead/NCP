# NCP conformance corpus

This directory holds the conformance material of two protocol generations.

## NCP 2

| File | Content |
| --- | --- |
| [`vectors.json`](vectors.json) | The vectors of [NCP 2](../spec/NCP-2.md), revision 4: 63 frames, 39 messages, 4 authenticated frames, 8 owner scenarios, 16 client cases, 17 stream cases, 19 transcripts, 21 contracts, and 35 schema cases, each with its expected result. |
| [`generate.py`](generate.py) | Writes `vectors.json` and the package copy `python/ncp/vectors.json`. The vectors are generated. Do not edit them. |
| [`requirements.json`](requirements.json) | Each normative line of the specification, with the vectors, tests, model checks, and Lean claims that test it. [`check_ncp2_requirements.py`](../scripts/check_ncp2_requirements.py) requires an entry for each line and checks each reference. |
| [`fuzz.py`](fuzz.py) | Differential fuzzing: the Python decoder and message checks against another implementation. |

### Test another implementation

1. Write a decoder program like [`decode_corpus`](../rust/examples/decode_corpus.rs). It reads a corpus file of entries: a 4-byte big-endian bound, a 4-byte big-endian length, and the frame. For each entry, it prints one line of JSON: the decoded message, its identity, its array bytes, and whether the message has the form of a request, a response, and a stream message.
2. Write an owner program like [`conformance_owner`](../rust/examples/conformance_owner.rs). It serves one session on its standard input and output, with the contract and the handler that `vectors.json` describes.
3. Run the vectors against both programs:

   ```text
   python -m ncp conformance --decoder PROGRAM --owner PROGRAM
   ```

4. Run the client cases against your client state machine, as [`rust/tests/conformance.rs`](../rust/tests/conformance.rs) does. They give the frames that the client receives and the verdict and state that it must reach.
5. Fuzz your decoder against the Python one:

   ```text
   python3 conformance/fuzz.py --decoder PROGRAM --cases 200000
   ```

6. Drive your owner state machine with the oracle traces of [`../model/conformance.py`](../model/README.md), through the command protocol of [`model_owner`](../rust/examples/model_owner.rs).

[`../scripts/check_ncp2.sh`](../scripts/check_ncp2.sh) runs all of these for the Rust SDK, and CI runs that script.

## NCP 1.0 candidate

The generated [`manifest.v1.json`](manifest.v1.json) makes the unreleased NCP
1.0 candidate corpus mandatory and self-describing. It currently requires 282
vectors: 275 stable vectors (223 behavior, 8 request-digest, 12 security-state
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
bun run check:integers
cargo test -p ncp-core --all-features
```

After building `ncp-ts/dist` and installing the candidate wheel into the active
Python environment, `python3 scripts/check_cross_language_canonical_json.py`
executes the exact 14-vector canonical-byte matrix across Rust, TypeScript,
Python FFI, and C/C++ FFI. It requires every one of the 16 ordered
producer-to-consumer pairs, including self-pairs, and compares 224 emitted byte
sequences. Python and C/C++ share the Rust codec, so their rows are binding
coverage rather than independent-implementation evidence. `bun run check:integers`
separately discovers all stable integer paths from the complete schema set and
proves the safe boundary plus pre-parse and programmatic unsafe-value rejection at
each path.

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
