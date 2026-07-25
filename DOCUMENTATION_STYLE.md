# NCP technical writing style

This guide applies to project-owned, maintained technical prose. It does not change
the NCP contract or authorize a release.

## Writing profile

Use ASD-STE100 Simplified Technical English, Issue 9, as the project baseline.
See the [official ASD-STE100 website](https://www.asd-ste100.org/).

Call project prose **STE-aligned**. Do not call it compliant or certified unless
a qualified reviewer checks the complete controlled language and dictionary.

Use this order of priority:

1. Preserve technical truth and safety.
2. Preserve normative meaning and fail-closed behavior.
3. Use one clear term for each concept.
4. Make the text easy to read and translate.
5. Apply the preferred sentence and word rules.

If a style rule conflicts with an exact technical requirement, keep the exact
technical requirement.

## Language rules

- Use American English.
- Use short and common words when they keep the exact meaning.
- Use one approved term for one concept.
- Keep a descriptive sentence to 25 words or fewer.
- Keep a procedural sentence to 20 words or fewer.
- Use active voice when the actor is known and important.
- Use the imperative form for an instruction.
- Give one instruction in each sentence or numbered step.
- Put a condition before the action that it controls.
- Use simple verb tenses.
- Do not use contractions in technical prose.
- Do not use semicolons in technical prose.
- Use a vertical list for three or more items or for complex conditions.
- Keep one topic in each paragraph.
- Keep a paragraph to six sentences or fewer.
- State a safety instruction directly.
- State the probable result when a reader does not obey a safety instruction.

Prefer direct verbs. For example, use `use` instead of `utilize`. Use `start`
instead of `initiate` when both words have the same technical meaning.

Avoid vague words such as `simple`, `obvious`, `robust`, and `safe`. Replace each
word with the exact condition, limit, or evidence that supports it.

Do not use a pronoun when its noun can be unclear. Repeat the exact term when this
prevents ambiguity.

## Approved technical terms

Keep the exact capitalization and spelling of these terms:

- `NCP`
- `Engram`
- `Haldir`
- `Galadriel`
- `Crebain`
- `Prisoma`
- `Zenoh`
- `ASD-STE100`
- `TLA+`
- `Z3`
- `Kani`
- `Ed25519`
- `JWS`
- `ESTOP`
- `fail-safe`

Keep exact package, crate, import, route, field, enum, error, and capability names.
Do not replace a normative keyword such as **MUST** with a weaker word.

## Status and evidence terms

Use `candidate` for repository HEAD. Use `release` only for an immutable published
release.

Use **NOT RUN** when a required gate has no exact evidence. Do not use `verified`,
`certified`, or `proved` without the exact object and claim boundary.

Do not use local tests to claim live security, independent interoperability,
physical safety, scientific validity, or release readiness.

Do not describe simulation output as a paper reproduction or a calibrated
posterior. Do not describe protocol ESTOP as physical certification.

## Files that need special treatment

Do not rewrite these items only to match this profile:

- generated files
- immutable evidence
- frozen release history
- vendored or copied third-party text
- licenses
- codes of conduct
- exact quotations
- code and command blocks
- paths, identifiers, literals, and equations
- tables that contain exact machine values

Change generated prose only through its source and generator. Keep historical
values when the document clearly labels them as history.

## Documentation workflow

1. Identify the document owner and evidence class.
2. Read the owning protocol, registry, source, tests, and current status.
3. Check each version, hash, route, field, limit, command, and claim.
4. Change the smallest complete set of current documents.
5. Preserve generated files and frozen history unless their source workflow applies.
6. Run the focused documentation checks.
7. Read the rendered document from start to end.
8. Inspect the complete diff.
9. Run the applicable repository gate.

Use these focused checks:

```bash
python3 scripts/check_markdown_links.py --self-test
python3 scripts/check_markdown_links.py
git diff --check
```

Run the complete local gate before a release-candidate handoff:

```bash
scripts/check.sh
```

## Three review passes

Complete these reviews in order:

1. Check technical truth, authority, safety, science, and release claims.
2. Check language, terminology, spelling, grammar, and internal consistency.
3. Check the final render, links, tables, code blocks, and visual assets.

Record the exact scope of the review. An STE-aligned review is not a release,
security, safety, interoperability, or scientific certification.
