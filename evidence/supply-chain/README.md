# Candidate supply-chain evidence

These files are deterministic evidence for the unreleased, release-blocked
`1.0.0-rc.1` candidate. They inventory the resolved dependency graph, declared
features and generators, tracked assets and fixtures, package licenses, applicable
RustSec findings, and the hosted provenance requirements.

They are generated from the locked repository state:

```bash
python3 scripts/generate_supply_chain_evidence.py --self-test
python3 scripts/generate_supply_chain_evidence.py --check
python3 scripts/generate_supply_chain_evidence.py --validate-current-advisories
```

The normal `--check` is a pinned deterministic replay: it executes `cargo-deny`
against the reviewed local RustSec database revision and compares every generated
byte. The read-only `--validate-current-advisories` mode instead checks the exact
reviewed finding tuples and dispositions against the currently fetched database;
it neither writes nor compares deterministic evidence files. Hosted CI also runs
its own current-database advisory job.

`sbom.cdx.json` is a timestamp-free CycloneDX 1.6 inventory. The license and
vulnerability reports are machine-readable qualification inputs. Internal
workspace surfaces use non-registry BOM references, while registry PURLs are
reserved for resolved third-party packages. License records retain both raw and
reviewed normalized SPDX expressions. The provenance policy defines what a
candidate dossier must bind. None of these unsigned local files is a signature,
independent reproduction, registry-ownership receipt, publication, or release
authorization.
