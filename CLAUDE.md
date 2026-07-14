# Model-facing repository guide

Follow [`AGENTS.md`](AGENTS.md); it is the durable operating policy. Repository
HEAD is the unreleased, release-blocked NCP `1.0.0-rc.1` candidate (wire `1.0`,
compact proto hash `163acc57d8a62b66`). The released `v0.8.0` baseline and the 1.0
candidate must never be conflated.

Protocol, security, safety, interoperability, and release conclusions must come
from normative artifacts, executable corpus evidence, and live installed-artifact
tests. Model review—including Claude/Fable advice—is optional, read-only,
non-normative, and ineligible as certification evidence. Keep any such request
laser-focused and do not provide unrelated repository context.

Before changing the wire, read
[`NEURO_CYBERNETIC_PROTOCOL.md`](NEURO_CYBERNETIC_PROTOCOL.md),
[`contract/manifest.v1.json`](contract/manifest.v1.json), and
[`conformance/manifest.v1.json`](conformance/manifest.v1.json). Regenerate all
derived artifacts and run [`scripts/check.sh`](scripts/check.sh). Never report a
not-run external gate as passed. Engram's explicit native-1.0 migration is in
progress; copied candidate files alone are not migration or certification.
