# Claude Code guide for NCP

[`AGENTS.md`](AGENTS.md) is the durable repository policy. It takes precedence over
this guide.

## Start here

1. Read `AGENTS.md` completely.
2. Read `README.md` and the required owner documents for the change.
3. Read `DOCUMENTATION_STYLE.md` before you change maintained prose.
4. Inspect the owning source, generator, tests, and current evidence.
5. Preserve unrelated work in each dirty repository.

## Current boundary

Repository HEAD is the unreleased and release-blocked NCP `1.0.0-rc.1` candidate.
Its wire is `1.0`. Its compact proto hash is `163acc57d8a62b66`.

The released `v0.8.0` baseline uses a different wire. Do not conflate the release
with the candidate.

Engram has a native-1.0 migration in progress. Copied candidate files do not prove
migration or certification.

## Work rules

- Start only a dependency-ready ledger task.
- Do not hand-edit generated files or generated ledger views.
- Treat a change as wire-visible unless you can prove that it is not.
- Regenerate all affected outputs from their source.
- Run focused checks and the applicable complete gate.
- Keep every unexecuted external gate at **NOT RUN**.
- Do not infer authority, safety, interoperability, or release status from local
  tests.

Protocol, security, safety, interoperability, and release conclusions require
normative sources and exact executable evidence. Model review is optional,
read-only advice. It is not certification evidence.

Give an external model only the context that its focused question requires. Do not
give it unrelated repository data.

## Technical writing

Use the STE-aligned profile in
[`DOCUMENTATION_STYLE.md`](DOCUMENTATION_STYLE.md). Use the correct name,
`ASD-STE100`.

Use American English and active voice. Use one term for one concept.

Limit procedural sentences to 20 words. Give one instruction in each sentence.
Put a necessary condition before the instruction.

Limit descriptive sentences to 25 words. Keep one topic in each paragraph.

Keep exact wire terms, requirements, identifiers, commands, and historical values.
Do not claim full ASD-STE100 compliance without a qualified full-document review.

## Before handoff

Run [`scripts/check.sh`](scripts/check.sh) when the task requires the complete local
gate. Inspect the complete diff before you commit.

Use one professional commit for one coherent passing part. Push it to the
authorized remote branch. Verify the remote commit after the push.

Report the exact local result. List each external or independent gate that remains
**NOT RUN**.
