<!--
Thanks for contributing to NCP! Repository HEAD is the unreleased, release-blocked
1.0.0-rc.1 candidate; v0.8.0 remains the latest immutable release.
Please fill out the checklist below. Remove sections that genuinely don't apply, but don't skip them silently.
-->

## Summary

<!-- What does this PR do, and why? Link any related issue (e.g. "Closes #123"). -->

## Checklist

- [ ] Tests added or updated for the change
- [ ] `scripts/check.sh` passes locally, or each intentionally unavailable gate is recorded as `NOT RUN`
- [ ] The mandatory exact-set corpus has no applicable skips or unknown vectors
- [ ] Generated schemas, bindings, manifests, full contract digest, and candidate baseline are current
- [ ] Docs updated where behavior or public API changed
- [ ] No vendor-specific or project-specific names introduced (NCP is project-agnostic)
- [ ] No local pass is described as production, security, safety, consumer, or release certification

## Wire change?

- [ ] This PR **does not** change the wire format (frames, planes, schema, or proto)

If it **does** change the wire format, all of the following are required:

- [ ] Compatibility impact and migration behavior are explicit; no silent 0.8 coercion was added
- [ ] Spec, registries, proto, schemas, canonical vectors, behavior corpus, and digest were regenerated coherently
- [ ] The frozen candidate baseline was deliberately refreshed and exact-verified when required

## Notes for reviewers

<!-- Anything reviewers should pay special attention to (tricky bits, follow-ups, known gaps). -->
