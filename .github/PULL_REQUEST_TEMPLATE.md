<!--
Thanks for contributing to NCP! NCP is pre-1.0 and experimental — the wire format may still change.
Please fill out the checklist below. Remove sections that genuinely don't apply, but don't skip them silently.
-->

## Summary

<!-- What does this PR do, and why? Link any related issue (e.g. "Closes #123"). -->

## Checklist

- [ ] Tests added or updated for the change
- [ ] `cargo test` passes locally
- [ ] `cargo fmt --all -- --check` is clean
- [ ] `cargo clippy --all-targets --all-features -- -D warnings` is clean
- [ ] Conformance test suite passes
- [ ] Docs updated where behavior or public API changed
- [ ] No vendor-specific or project-specific names introduced (NCP is project-agnostic)

## Wire change?

- [ ] This PR **does not** change the wire format (frames, planes, schema, or proto)

If it **does** change the wire format, all of the following are required:

- [ ] `ncp_version` bumped appropriately
- [ ] Spec (`NEURO_CYBERNETIC_PROTOCOL.md`), `schemas/`, and/or `proto/` updated to match
- [ ] Conformance tests updated to cover the new/changed wire behavior

## Notes for reviewers

<!-- Anything reviewers should pay special attention to (tricky bits, follow-ups, known gaps). -->
