# Signed-forwarding differential corpus

This gate compares the quarantined Python/PyNaCl reference with the independent
Node/OpenSSL verifier in separate processes. The committed corpus retains only
public keys, signed envelopes, exact requests, expected decision classes, and
accepted-projection hashes. Corpus-generation private keys exist only in memory
and are discarded before the file is written.

Every case starts with a fresh Python replay store. Replay ordering and recovery
remain the responsibility of the Python prototype's separate replay tests; this
corpus compares envelope parsing, authentication, profile congruence, manifest
behavior, and payload binding. A pass requires identical acceptance decisions,
identical rejection codes, or byte-for-byte-equivalent accepted projections.
Either verifier rejecting makes the combined path reject.

`corpus.v1.json` is generated once with:

```bash
uv run --locked python differential/generate_corpus.py \
  --output differential/corpus.v1.json
```

Regeneration creates new runtime keys and therefore is a reviewed corpus
replacement, not a deterministic formatting operation. Run the gate after the
Node verifier has been built:

```bash
./differential/run.sh
```
