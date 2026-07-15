#!/usr/bin/env python3
"""Generate the commentable max-effort handoff review ledger.

This generator maps the frozen source index to repository-local evidence without
closing any handoff task.  Existing reviewer comments are preserved by task ID.
The resulting ledger is non-normative and remains NO_GO while any task or lens is
open.  It does not ingest or manufacture external evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INDEX = ROOT / "docs" / "handoff" / "max-effort-source-index.v2.json"
DEFAULT_AUDIT = ROOT / "docs" / "handoff" / "max-effort-audit-inputs.v2.json"
DEFAULT_OUTPUT = ROOT / "docs" / "handoff" / "max-effort-task-review.v2.json"

EXPECTED_INDEX_SHA256 = (
    "2e0337544d91a780415d5f86e6372f2067121fc60244c8a30d5231e5ab031b51"
)
EXPECTED_AUDIT_SHA256 = (
    "7932dbcfeac3014efc5f0977403c4e4df89a0072b03e2f1d4f6326f224b218eb"
)
LENS_IDS = tuple(f"L{index:02d}" for index in range(1, 21))
COMMIT_ID = re.compile(r"^[0-9a-f]{40}$")


class TemplateError(ValueError):
    """The source evidence cannot produce the closed review template."""


def _load(path: Path, expected_sha256: str) -> dict[str, Any]:
    try:
        payload = path.read_bytes()
        value = json.loads(payload)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise TemplateError(f"cannot load {path}: {error}") from error
    if hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise TemplateError(f"{path.name} differs from its reviewed identity")
    if not isinstance(value, dict):
        raise TemplateError(f"{path.name} must contain one JSON object")
    return value


def _source_commits(
    index: dict[str, Any], audit_inputs: dict[str, Any]
) -> tuple[str, str]:
    try:
        frozen_commit = audit_inputs["source_cuts"]["handoff_frozen"]["commit"]
        reviewed_commit = audit_inputs["source_cuts"]["reviewed_current"]["commit"]
        inventory_commit = audit_inputs["reviewed_source_inventory"]["source_commit"]
        declared_frozen = audit_inputs["handoff_package"]["declared_frozen_commit"]
        indexed_frozen = index["source"]["frozen_commit"]
    except (KeyError, TypeError) as error:
        raise TemplateError(
            "audit/source index does not bind both source cuts"
        ) from error
    for label, commit in (
        ("handoff frozen", frozen_commit),
        ("reviewed source", reviewed_commit),
    ):
        if not isinstance(commit, str) or COMMIT_ID.fullmatch(commit) is None:
            raise TemplateError(f"{label} commit is not a full lowercase Git ID")
    if frozen_commit != declared_frozen or frozen_commit != indexed_frozen:
        raise TemplateError("handoff frozen commit differs across bound inputs")
    if reviewed_commit != inventory_commit:
        raise TemplateError("reviewed source commit differs from its file inventory")
    return reviewed_commit, frozen_commit


def _global_findings(lenses: list[dict[str, str]]) -> list[dict[str, str]]:
    findings = {
        "L01": (
            "Candidate docs consistently distinguish local implementation from release, certification, and physical or scientific validation.",
            "Stale remote metadata, historical prose, or a version-only 0.9 relabel could still create a broader public claim than the evidence supports.",
        ),
        "L02": (
            "The protocol and closed registries specify many inputs, transitions, failures, and fail-closed defaults.",
            "Clock, provenance, final actuator routing, and some cross-component invariants are not yet one complete executable semantic model.",
        ),
        "L03": (
            "Simulation outputs are explicitly marked non-calibrated and simulated, and the repository avoids paper-reproduction claims.",
            "No release-bound calibration, statistical coverage, representative distribution, or physical-validation campaign exists.",
        ),
        "L04": (
            "Rust validators, bounded decoding, schemas, and closed enums reject broad classes of invalid states.",
            "All-language construction, defaults, feature combinations, migration, and FFI state-space parity have not been exhaustively proved.",
        ),
        "L05": (
            "Typed stream positions, exact-session epochs, monotonic high-water fencing, leases, idempotency contexts, and bounded capture migration are locally tested.",
            "Real process crash, rollover, delayed delivery, retained transport replay, and long-running all-client lifecycle campaigns remain incomplete.",
        ),
        "L06": (
            "The candidate records compact and complete contract identities, corpus digests, profile digests, receipts, immutable released baselines, and a deterministic local supply-chain inventory.",
            "The current review evidence is unsigned, some cross-repository inputs are mutable, and complete source-to-installed-artifact lineage has not been independently reproduced.",
        ),
        "L07": (
            "Production-secure refuses to start without callback-visible verified peer identity; dev-loopback is visibly insecure and default-deny templates are tested offline.",
            "The current Zenoh callback API cannot bind a verified peer principal to payload identity, and live rotation/revocation evidence is NOT RUN.",
        ),
        "L08": (
            "Roles, planes, exact sessions, leases, request digests, receipts, governors, and the plant body as final authority constrain mutation locally.",
            "Raw transport access, generic configuration entry points, and the absent live secure profile require explicit quarantine and independent deployment proof.",
        ),
        "L09": (
            "Universal JSON limits, duplicate-key-aware ingress, a four-surface canonical-byte matrix, and TypeScript stable-integer path checks have hostile local tests.",
            "The binding surfaces share Rust implementation code, and every independent decoder and producer has not demonstrated identical Unicode, non-finite, nesting, and path rejection across the complete mandatory corpus.",
        ),
        "L10": (
            "The contract bounds JSON, dimensions, queues, chunks, retries, and several transport resources before semantic work.",
            "Maximum-size CPU/RSS, allocation, log-volume, overload, and duration evidence is NOT RUN on the declared platform matrix.",
        ),
        "L11": (
            "Session, callback, queue, websocket, shutdown, and idempotency behavior has focused local test coverage.",
            "Arbitrary scheduling, cancellation, process crash, restart, leak, and long-duration lifecycle campaigns remain NOT RUN.",
        ),
        "L12": (
            "Locked dependencies, generated-output diffs, exact manifests, pinned workflow actions, deterministic SBOM inputs, archive comparison, and hosted CI provide strong local reproducibility controls.",
            "A final signed dossier, pinned multi-platform toolchains, clean-room reproduction, and independently rebuilt publication archives remain NOT RUN.",
        ),
        "L13": (
            "Rust, Python, C/C++, TypeScript, and gateway packages have explicit candidate versions and local archive or build checks.",
            "Stable API snapshots, all feature/platform combinations, installed package matrices, panic boundaries, and support windows remain incomplete.",
        ),
        "L14": (
            "Proto-first generation, schema parity, a 282-vector corpus, shared behavior vectors, generated TypeScript, and a four-surface ordered canonical-byte matrix reduce projection drift.",
            "Python and C expose the same Rust implementation, and the ordered matrix does not yet cover every normative type, independent peer implementation, or installed-platform combination; the BulkObservation and bare-NCPB quarantine remains local evidence only.",
        ),
        "L15": (
            "Named security and plant profiles, ACL templates, package checks, and release hold metadata fail closed locally.",
            "Production-secure is unavailable, generic Zenoh configuration is not profile-typed, and real PKI/router/rollback operations are NOT RUN.",
        ),
        "L16": (
            "Closed error registries, receipts, audit chains, scientific flags, and explicit unavailable/not-run states support diagnosis.",
            "Live distributed forensics, retention, redaction, clock correlation, crash evidence, and signed incident records are not demonstrated.",
        ),
        "L17": (
            "The local gate covers Rust, Python, C/C++, TypeScript, proto/schema, corpus, profiles, packages, dependencies, audit artifacts, supply-chain evidence, and Buf, with hostile self-tests.",
            "Fuzzing, mutation, sanitizers, real-router security, duration, performance, independent peers, and clean-room evidence remain NOT RUN.",
        ),
        "L18": (
            "NCP documents authority boundaries and treats consumer pins, copied protocol files, and local migrations as non-certifying.",
            "Engram is an uncertified native-1.0 migration while five consumers remain on wire 0.8; cross-repository convergence is therefore NO_GO.",
        ),
        "L19": (
            "Contribution, security, support, versioning, release-readiness, rollback, and reviewer-comment workflows are documented.",
            "Independent signers, incident drills, withdrawal rehearsal, long-term support decisions, and human reviewer acceptance are absent.",
        ),
        "L20": (
            "Adversarial review found and locally addressed a consumed-stream retry, an underconstrained convergence schema, weak handoff evidence helpers, and an incomplete local threat and traceability inventory.",
            "Coverage-guided quirky-case generation and independent red-team reproduction have not run, so unanticipated simple counterexamples may remain.",
        ),
    }
    result: list[dict[str, str]] = []
    for lens in lenses:
        identifier = lens["id"]
        finding, risk = findings[identifier]
        result.append(
            {
                "id": identifier,
                "name": lens["name"],
                "finding": finding,
                "residual_risk": risk,
                "status": "OPEN",
            }
        )
    return result


def _phase_evidence(phase: str) -> tuple[list[str], list[str]]:
    mapping: list[tuple[str, list[str], list[str]]] = [
        (
            "P0 Audit and scope",
            [
                "docs/handoff/max-effort-audit-inputs.v2.json",
                "docs/handoff/max-effort-source-index.v2.json",
                "RELEASE_READINESS.md",
            ],
            [
                "python3 scripts/check_max_effort_handoff_review.py --self-test",
                "scripts/check.sh",
            ],
        ),
        (
            "Root protocol",
            [
                "README.md",
                "NEURO_CYBERNETIC_PROTOCOL.md",
                "VERSIONING.md",
                "RELEASE_READINESS.md",
            ],
            [
                "python3 scripts/check_markdown_links.py",
                "scripts/check-version-coherence.sh",
            ],
        ),
        (
            "Normative IDL",
            ["proto/ncp.proto", "proto/README.md", "buf.yaml", "buf.gen.yaml"],
            ["buf lint", "buf build", "python3 scripts/check_buf_breaking.py"],
        ),
        (
            "Contract registry",
            [
                "contract/manifest.v1.json",
                "contract/release-gates.v1.json",
                "contract/limits.v1.json",
            ],
            [
                "python3 scripts/generate_contract_manifest.py",
                "python3 scripts/check_release_gates.py",
            ],
        ),
        (
            "JSON Schemas",
            [
                "schemas/index.json",
                "schemas/README.md",
                "scripts/check_proto_schema_parity.py",
            ],
            [
                "python3 scripts/check_proto_schema_parity.py",
                "python3 scripts/check_schema_defaults.py",
            ],
        ),
        (
            "Conformance manifest",
            [
                "conformance/manifest.v1.json",
                "conformance/behavior/vectors.json",
                "conformance/README.md",
            ],
            [
                "python3 scripts/check_conformance_vectors.py",
                "python3 scripts/check_behavior_vectors.py",
            ],
        ),
        (
            "Canonical JSON",
            [
                "ncp-core/src/bounded_json.rs",
                "ncp-core/src/canonical_digest.rs",
                "ncp-core/tests/conformance.rs",
            ],
            [
                "cargo test -p ncp-core --locked",
                "python3 scripts/check_request_digests.py",
            ],
        ),
        (
            "Core message types",
            ["ncp-core/src/messages.rs", "ncp-core/src/codec.rs", "proto/ncp.proto"],
            [
                "cargo test -p ncp-core --locked",
                "python3 scripts/check_proto_schema_parity.py",
            ],
        ),
        (
            "Sessions, generations",
            [
                "ncp-core/src/stream_fence.rs",
                "ncp-core/src/resilience.rs",
                "ncp-zenoh/tests/cross_session_rpc.rs",
            ],
            ["cargo test -p ncp-core --locked", "cargo test -p ncp-zenoh --locked"],
        ),
        (
            "Authority, lease",
            [
                "ncp-core/src/authority.rs",
                "ncp-core/src/idempotency.rs",
                "ncp-core/src/request_digest.rs",
            ],
            [
                "cargo test -p ncp-core --locked",
                "python3 scripts/check_request_digests.py",
            ],
        ),
        (
            "Action safety",
            [
                "ncp-core/src/safety.rs",
                "ncp-core/src/plant.rs",
                "ncp-zenoh/tests/safety_governor_over_wire.rs",
            ],
            [
                "cargo test -p ncp-core --locked",
                "cargo test -p ncp-zenoh --test safety_governor_over_wire --locked",
            ],
        ),
        (
            "Security and plant digests",
            [
                "ncp-core/src/security.rs",
                "ncp-core/src/plant.rs",
                "contract/security-state-digest.v1.json",
            ],
            [
                "python3 scripts/check_profile_digests.py",
                "python3 scripts/validate_security_profile.py --self-test",
            ],
        ),
        (
            "Audit chain",
            [
                "ncp-core/src/audit.rs",
                "ncp-core/src/bounded_json.rs",
                "e2e/bounded_json.py",
            ],
            [
                "cargo test -p ncp-core --locked",
                "python3 -m unittest -v e2e.test_bounded_json",
            ],
        ),
        (
            "C and language bindings",
            ["ncp-cpp/include/ncp.h", "ncp-cpp/src/lib.rs", "ncp-cpp/tests/corpus.rs"],
            [
                "cargo test -p ncp-cpp --locked",
                "python3 scripts/check_behavior_vectors.py",
            ],
        ),
        (
            "Zenoh adapter",
            [
                "ncp-zenoh/src/lib.rs",
                "ncp-zenoh/tests/loopback.rs",
                "ncp-zenoh/README.md",
            ],
            [
                "cargo test -p ncp-zenoh --locked",
                "python3 scripts/check_acl_template.py",
            ],
        ),
        (
            "Python package",
            [
                "ncp-python/src/lib.rs",
                "ncp-python/pyproject.toml",
                "ncp-python/tests/test_smoke.py",
            ],
            [
                "python3 scripts/check_behavior_vectors.py",
                "python3 scripts/check_rust_packages.py --offline",
            ],
        ),
        (
            "C++ package",
            [
                "ncp-cpp/include/ncp.h",
                "ncp-cpp/examples/demo.cpp",
                "ncp-cpp/tests/behavior_corpus.rs",
            ],
            [
                "cargo test -p ncp-cpp --locked",
                "python3 scripts/check_rust_packages.py --offline",
            ],
        ),
        (
            "TypeScript package",
            [
                "ncp-ts/src/index.ts",
                "ncp-ts/src/bounded-json.ts",
                "ncp-ts/scripts/check-behavior.mjs",
            ],
            ["bun run check:behavior", "bun run check:package"],
        ),
        (
            "Gateway",
            [
                "ncp-gateway/src/main.rs",
                "ncp-gateway/README.md",
                "ncp-core/src/migration.rs",
            ],
            [
                "cargo test -p ncp-gateway --locked",
                "scripts/check-version-coherence.sh",
            ],
        ),
        (
            "Secure deployment",
            ["deploy/README.md", "deploy/zenoh-access-control.json5", "SECURITY.md"],
            [
                "python3 scripts/check_acl_template.py",
                "python3 scripts/verify_acl_deployment.py --self-test",
            ],
        ),
        (
            "End-to-end and Engram",
            [
                "e2e/run_cross_language_e2e.py",
                "e2e/nest_five_networks.py",
                "e2e/README.md",
            ],
            [
                "python3 -m unittest -v e2e.test_bounded_json",
                "python3 e2e/run_cross_language_e2e.py --help",
            ],
        ),
        (
            "Generation and release scripts",
            [
                "scripts/check.sh",
                "scripts/README.md",
                "scripts/generate_contract_manifest.py",
            ],
            [
                "scripts/check.sh",
                "python3 scripts/generate_contract_manifest.py --self-test",
            ],
        ),
        (
            "Workflows and supply chain",
            [".github/workflows/ci.yml", ".github/workflows/release.yml", "deny.toml"],
            ["python3 scripts/check_release_gates.py --self-test", "cargo deny check"],
        ),
        (
            "Documentation and diagrams",
            [
                "docs/1.0-scope.md",
                "docs/1.0-candidate-receipts.md",
                "scripts/gen_diagrams.py",
            ],
            [
                "python3 scripts/check_markdown_links.py",
                "python3 scripts/gen_diagrams.py --check",
            ],
        ),
    ]
    for marker, paths, commands in mapping:
        if marker in phase:
            return paths, commands
    return ["RELEASE_READINESS.md", "docs/1.0-candidate-receipts.md"], [
        "scripts/check.sh"
    ]


def _coverage(identifier: str) -> str:
    number = int(identifier[1:])
    if identifier in {
        "T004",
        "T006",
        "T007",
        "T008",
        "T127",
        "T129",
        "T130",
        "T131",
        "T135",
        "T139",
        "T143",
    }:
        return "SUBSTANTIAL"
    if number <= 124:
        return "PARTIAL"
    if number == 134:
        return "SUBSTANTIAL"
    if number in {125, 126, 130, 133, 134, 137, 139, 141, 143, 144}:
        return "PARTIAL"
    if number in {127, 128, 129, 135, 142}:
        return "MINIMAL"
    return "NONE"


def _task_specific_evidence(task: dict[str, Any]) -> tuple[list[str], list[str]]:
    identifier = task["id"]
    paths, commands = _phase_evidence(task["phase"])
    overrides: dict[str, tuple[list[str], list[str]]] = {
        "T004": (
            [
                "evidence/audit/threat-register.v1.json",
                "scripts/generate_audit_artifacts.py",
                "scripts/check_audit_artifacts.py",
            ],
            [
                "python3 scripts/generate_audit_artifacts.py --check",
                "python3 scripts/check_audit_artifacts.py",
            ],
        ),
        "T006": (
            [
                "evidence/audit/latent-path-inventory.v1.json",
                "evidence/audit/manifest.v1.json",
                "scripts/check_audit_artifacts.py",
            ],
            [
                "python3 scripts/generate_audit_artifacts.py --check",
                "python3 scripts/check_audit_artifacts.py --self-test",
            ],
        ),
        "T007": (
            [
                "evidence/supply-chain/inventory.v1.json",
                "evidence/supply-chain/sbom.cdx.json",
                "evidence/supply-chain/license-report.v1.json",
                "evidence/supply-chain/vulnerability-report.v1.json",
                "evidence/supply-chain/provenance-policy.v1.json",
                "scripts/generate_supply_chain_evidence.py",
            ],
            [
                "python3 scripts/generate_supply_chain_evidence.py --check",
                "python3 scripts/generate_supply_chain_evidence.py --self-test",
                "cargo deny check advisories --disable-fetch",
            ],
        ),
        "T008": (
            [
                "evidence/audit/requirement-traceability.v1.json",
                "evidence/audit/manifest.v1.json",
                "scripts/check_audit_artifacts.py",
            ],
            [
                "python3 scripts/generate_audit_artifacts.py --check",
                "python3 scripts/check_audit_artifacts.py",
            ],
        ),
        "T125": (
            ["README.md", "VERSIONING.md", "docs/0.8-current-baseline.md"],
            ["scripts/check-version-coherence.sh"],
        ),
        "T126": (
            ["contract/manifest.v1.json", "proto/ncp.proto"],
            [
                "python3 scripts/generate_contract_manifest.py",
                "scripts/check-version-coherence.sh",
            ],
        ),
        "T127": (
            [
                "ncp-core/src/messages.rs",
                "ncp-core/tests/canonical_json_bytes.rs",
                "ncp-ts/src/canonical-json.ts",
                "scripts/check_cross_language_canonical_json.py",
            ],
            [
                "cargo test -p ncp-core --test canonical_json_bytes --locked",
                "python3 scripts/check_cross_language_canonical_json.py",
            ],
        ),
        "T128": (
            [
                "ncp-core/src/bounded_json.rs",
                "e2e/bounded_json.py",
                "ncp-ts/src/bounded-json.ts",
            ],
            [
                "python3 -m unittest -v e2e.test_bounded_json",
                "cargo test -p ncp-core --locked",
            ],
        ),
        "T129": (
            [
                "ncp-ts/scripts/check-integer-safety.mjs",
                "ncp-ts/src/bounded-json.ts",
                "ncp-ts/src/safety.ts",
            ],
            ["bun run check:integers"],
        ),
        "T130": (
            [
                "ncp-core/src/stream_fence.rs",
                "ncp-core/src/migration/capture.rs",
                "ncp-zenoh/tests/cross_session_rpc.rs",
            ],
            [
                "cargo test -p ncp-core migration::capture::tests --locked",
                "cargo test -p ncp-zenoh --locked",
            ],
        ),
        "T131": (
            [
                "scripts/check_cross_language_canonical_json.py",
                "ncp-ts/scripts/emit-canonical-json.mjs",
                "ncp-core/tests/canonical_json_bytes.rs",
            ],
            ["python3 scripts/check_cross_language_canonical_json.py"],
        ),
        "T132": (
            ["deploy/zenoh-access-control.json5", "scripts/verify_acl_deployment.py"],
            [
                "python3 scripts/verify_acl_deployment.py --self-test",
                "NOT RUN: real-router identity campaign",
            ],
        ),
        "T133": (
            ["README.md", "INTEGRATING.md", "docs/1.0-candidate-receipts.md"],
            ["NOT RUN: installed Engram native-1.0 certification"],
        ),
        "T134": (
            [
                "contract/surface.v1.json",
                "docs/1.0-scope.md",
                "conformance/manifest.v1.json",
                "conformance/README.md",
                "ncp-core/src/bulk.rs",
                "conformance/vectors/bulk_observation.bin",
            ],
            [
                "python3 scripts/generate_contract_manifest.py",
                "python3 scripts/check_conformance_vectors.py",
                "cargo test -p ncp-core --locked bulk::tests",
            ],
        ),
        "T135": (
            [
                "ncp-core/src/migration/capture.rs",
                "conformance/migration/v0.8-to-v1.0/wire-0.8-reconstructable-capture.json",
                "ncp-core/testdata/migration/wire-0.8-reconstructable-capture.json",
                "ncp-core/src/migration.rs",
            ],
            [
                "cargo test -p ncp-core migration::capture::tests --locked",
                "NOT RUN: retained real-world wire-0.8 capture campaign",
            ],
        ),
        "T136": (
            ["RELEASE_READINESS.md", "SECURITY.md"],
            [
                "NOT RUN: independent protocol, canonicalization, numeric, and deployment reviews"
            ],
        ),
        "T137": (
            [".github/workflows/ci.yml", "RELEASE_READINESS.md"],
            ["scripts/check.sh", "NOT RUN: full feature/platform/profile matrix"],
        ),
        "T138": (
            ["RELEASE_READINESS.md", "KNOWN_LIMITATIONS.md"],
            ["NOT RUN: duration fault, resource, cancellation, and restart campaigns"],
        ),
        "T139": (
            [
                "scripts/build_candidate_dossier.py",
                "scripts/check_rust_packages.py",
                "scripts/generate_supply_chain_evidence.py",
                ".github/workflows/candidate-dossier.yml",
                "evidence/supply-chain/sbom.cdx.json",
            ],
            [
                "python3 scripts/build_candidate_dossier.py --self-test",
                "python3 scripts/generate_supply_chain_evidence.py --check",
                "NOT RUN: final exact-revision hosted dossier and attestations",
            ],
        ),
        "T140": (
            ["RELEASE_READINESS.md", "CONTRIBUTING.md"],
            ["NOT RUN: independent clean-room reproduction"],
        ),
        "T141": (
            ["README.md", "CITATION.cff", "VERSIONING.md"],
            [
                "scripts/check-version-coherence.sh",
                "python3 scripts/check_markdown_links.py",
            ],
        ),
        "T142": (
            [".github/workflows/release.yml", "VERSIONING.md"],
            ["NOT RUN: publication, rollback, revocation, and withdrawal rehearsal"],
        ),
        "T143": (
            [
                "evidence/convergence/local-convergence.v1.json",
                "scripts/generate_convergence_manifest.py",
                "RELEASE_READINESS.md",
            ],
            [
                "python3 scripts/generate_convergence_manifest.py --check",
                "NOT RUN: cross-repository convergence and consumer certification",
            ],
        ),
        "T144": (
            ["docs/handoff/max-effort-task-review.v2.json", "RELEASE_READINESS.md"],
            [
                "python3 scripts/check_max_effort_handoff_review.py --self-test",
                "NOT RUN: independent final lead sign-off",
            ],
        ),
        "T145": (
            ["contract/release-gates.v1.json", "RELEASE_READINESS.md"],
            [
                "python3 scripts/check_release_gates.py",
                "NOT RUN: signed release-manager decision",
            ],
        ),
    }
    return overrides.get(identifier, (paths, commands))


def _acceptance_gap(task: dict[str, Any]) -> str:
    identifier = task["id"]
    number = int(identifier[1:])
    local_gaps = {
        "T004": "The generated register retains every threat OPEN and links local controls, but task dependencies, all twenty lens resolutions, external campaigns, and independent adversarial review remain incomplete.",
        "T006": "The deterministic tracked-file and latent-marker inventory has zero undispositioned text occurrences, but binary semantics, generated-state changes, dependency order, and independent review remain open.",
        "T007": "The deterministic dependency, feature, generator, asset, license, vulnerability, SBOM, and provenance-policy inventory exists locally; final artifact signatures, legal review, clean-room reproduction, and external registry evidence remain NOT RUN.",
        "T008": "The generated local requirement-to-code-to-test-to-evidence graph is checked for exact coverage and references, but it does not resolve OPEN requirements, prove semantic adequacy of every edge, or replace independent review.",
    }
    if identifier in local_gaps:
        return local_gaps[identifier]
    if number <= 124:
        return (
            "The repository has relevant local implementation and tests, but the task's repeated twelve-step procedure, all required counterfactuals, "
            "task-specific retained raw evidence, independent reproduction, dependencies, and all twenty lens resolutions are not complete."
        )
    if number == 125:
        return "Public candidate wording is largely reconciled, but a 0.9 release requires a coordinated normative rebaseline and cannot be closed locally."
    if number == 126:
        return "Current compact and complete digests reproduce locally, but final clean-source and independent artifact-bound verification is unsigned and not complete."
    if number == 127:
        return "The four declared package surfaces pass an ordered 14-vector canonical-byte matrix, but Python and C share Rust implementation code and the matrix does not yet cover every normative type, full mandatory corpus, independent peer, installed package, or platform."
    if number == 128:
        return "Several bounded decoders reject duplicate keys, but every independent decoder and schema entry path has not been exhaustively demonstrated."
    if number == 129:
        return "The TypeScript reachable stable-integer inventory and unsafe-value rejection proof pass locally, but independent review, alternate JavaScript engines/build targets, and installed-consumer evidence remain open."
    if number == 130:
        return "Focused core, capture, client, gateway, and transport restart checks pass locally, but result_digest has no approved normative nonrecursive result projection, and real process crash, retained-router replay, rollover, delayed delivery, and long-duration every-client campaigns remain NOT RUN."
    if number == 131:
        return "All sixteen ordered pairs across the four declared package surfaces pass the bounded canonical fixture matrix, but two bindings delegate to Rust and independent installed peers, complete normative traffic, and platform combinations remain NOT RUN."
    if number == 132:
        return "Offline ACL and verifier logic pass, but production-secure identity binding and the real-router multi-principal campaign are NOT RUN."
    if number == 133:
        return "Engram has an in-progress native-1.0 migration but installed-artifact and live compatible-server certification are NOT RUN."
    if number == 134:
        return "The closed surface registry and exact corpus exclusions prove the local quarantine branch; the task remains OPEN only because its handoff dependency chain, independent review, and signed release evidence are not closed."
    if number == 135:
        return "The bounded wire-0.8 validator checks explicit legacy units, frames, lineage, restart boundaries, and epistemic fields and excludes records needing unavailable native-1.0 authority or operation evidence; it emits no native-1.0 capture, and a retained real-world campaign and independent migration review remain NOT RUN."
    if number == 136:
        return "All four independent specialist reviews are NOT RUN."
    if number == 137:
        return "Hosted CI is Ubuntu-centric and does not cover the complete declared feature/platform/profile matrix."
    if number == 138:
        return "Long-duration resource, cancellation, restart, fault, and hostile-input campaigns are NOT RUN."
    if number == 139:
        return "Deterministic supply-chain evidence and an exact-revision reproducible dossier pipeline exist, but the final hosted dossier, attestations, signatures, clean-room reproduction, and publication archives remain NOT RUN."
    if number == 140:
        return "Independent clean-room build and critical evidence reproduction are NOT RUN."
    if number == 141:
        return "Repository and GitHub descriptions are corrected, but final immutable tag/package/support/citation reconciliation must wait for a real release candidate decision."
    if number == 142:
        return "Publication, rollback, revocation, withdrawal, and post-publication rehearsals are NOT RUN."
    if number == 143:
        return "The generated local convergence manifest records NO_GO and explicit non-local handoffs, but predecessor gates, all six consumer certifications, and cross-repository convergence remain unresolved."
    if number == 144:
        return "The current internal review is not an independent final lead-only review of one immutable release artifact set."
    return "The only truthful current decision is unsigned NO_GO; no release-manager signature or complete prerequisite chain exists."


def _task_record(task: dict[str, Any], comment: str | None) -> dict[str, Any]:
    paths, commands = _task_specific_evidence(task)
    local_summaries = {
        "T004": "A deterministic threat, misuse, failure, and quirky-case register links eighteen retained OPEN threats to local controls and explicit missing evidence without treating mitigation as closure.",
        "T006": "A deterministic per-file inventory binds byte counts, SHA-256 identities, Git blob identities, index state, text classification, and every reviewed latent-marker occurrence.",
        "T007": "Deterministic local inventory, CycloneDX SBOM, license, vulnerability, and provenance-policy artifacts cover declared dependencies, features, generators, workflows, assets, datasets, and fixtures.",
        "T008": "A generated traceability graph links one hundred local requirements to code, tests, commands, and evidence while preserving PARTIAL_LOCAL and NOT_RUN_EXTERNAL states.",
        "T127": "Four declared package surfaces exercise one canonical JSON algorithm over fourteen stable fixtures and compare exact bytes across all ordered surface pairs.",
        "T129": "The TypeScript proof inventories every reachable stable-integer path and rejects unsafe Number encodings at the bounded canonical boundary.",
        "T130": "Local restart checks exercise fresh session generations, epochs, high-water retirement, bounded capture lineage, and stale-state rejection across the implemented surfaces.",
        "T131": "The local canonical harness exercises all sixteen ordered producer-to-consumer pairs across Rust, Python FFI, C FFI, and TypeScript, with the shared-Rust binding limitation disclosed.",
        "T135": "A validation-only bounded wire-0.8 path checks explicit legacy units, frames, lineage, restart boundaries, and epistemic fields and excludes records needing unavailable native-1.0 authority or operation evidence; it does not reconstruct a native-1.0 capture.",
        "T139": "The repository contains deterministic supply-chain evidence and a held exact-revision pipeline that rebuilds and byte-compares five crates, a Python wheel and sdist, and two npm archives before optional hosted attestations.",
        "T143": "A deterministic local convergence artifact locks the candidate identities, local gates, explicit NOT_RUN external gates, consumer handoffs, and NO_GO decision.",
    }
    identifier = task["id"]
    if identifier == "T134":
        evidence_summary = "The reviewed cut explicitly excludes BulkObservation and bare NCPB from stable wire/public packages while retaining bounded BulkBlock only as an offline fixture. This proves the task's local quarantine alternative, not full handoff closure."
        residual_risk = "A future surface-registry, package, transport, or corpus change could undo the quarantine; independent review and the predecessor task chain remain OPEN."
    elif identifier in local_summaries:
        evidence_summary = local_summaries[identifier]
        residual_risk = f"This is repository-local evidence for {identifier}; its OPEN dependency chain, twenty-lens review, independent reproduction, and applicable external gates remain authoritative."
    else:
        evidence_summary = (
            f"Relevant local surfaces for '{task['title']}' were inventoried at the reviewed source cut; "
            "the paths and commands below are implementation leads, not completion evidence."
        )
        residual_risk = f"Treating local coverage of {task['id']} as closure could overstate the candidate and bypass its dependency, evidence, or independent-review requirements."
    return {
        "id": task["id"],
        "state": "OPEN",
        "implementation_coverage": _coverage(task["id"]),
        "lens_statuses": {identifier: "OPEN" for identifier in LENS_IDS},
        "evidence_summary": evidence_summary,
        "acceptance_gap": _acceptance_gap(task),
        "evidence": {"paths": paths, "commands": commands},
        "residual_risk": residual_risk,
        "reviewer_comment": comment,
    }


def _comments(path: Path) -> dict[str, str | None]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        tasks = value["tasks"]
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError) as error:
        raise TemplateError(f"cannot preserve comments from {path}: {error}") from error
    comments: dict[str, str | None] = {}
    for task in tasks:
        identifier = task.get("id")
        comment = task.get("reviewer_comment")
        if not isinstance(identifier, str) or identifier in comments:
            raise TemplateError("existing review has invalid or duplicate task IDs")
        if comment is not None and (
            not isinstance(comment, str) or not comment.strip()
        ):
            raise TemplateError(f"existing {identifier} reviewer_comment is invalid")
        comments[identifier] = comment
    return comments


def generate(
    index: dict[str, Any],
    audit_inputs: dict[str, Any],
    comments: dict[str, str | None],
) -> dict[str, Any]:
    tasks = index.get("tasks")
    lenses = index.get("twenty_lenses")
    if not isinstance(tasks, list) or len(tasks) != 146:
        raise TemplateError("source index must contain exactly 146 tasks")
    if not isinstance(lenses, list) or [lens.get("id") for lens in lenses] != list(
        LENS_IDS
    ):
        raise TemplateError("source index must contain the exact ordered twenty lenses")
    expected_ids = [f"T{number:03d}" for number in range(146)]
    if [task.get("id") for task in tasks] != expected_ids:
        raise TemplateError("source index must contain exact ordered T000 through T145")
    unknown_comments = set(comments) - set(expected_ids)
    if unknown_comments:
        raise TemplateError(
            f"cannot preserve comments for unknown tasks: {sorted(unknown_comments)}"
        )
    reviewed_commit, frozen_commit = _source_commits(index, audit_inputs)
    return {
        "schema": "ncp.max-effort-handoff-task-review.v2",
        "normative": False,
        "review_status": "NO_GO_OPEN_FOR_REVIEWER_REVIEW",
        "author": {"name": "Sepehr Mahmoudian"},
        "release_authorized": False,
        "claim_boundary": "This ledger maps reviewed local coverage and unresolved gaps. OPEN tasks, local tests, comments, and NO_GO bookkeeping do not certify a protocol, consumer, deployment, package, scientific result, or release.",
        "source_index": {
            "path": "docs/handoff/max-effort-source-index.v2.json",
            "sha256": EXPECTED_INDEX_SHA256,
            "source_ledger": "MASTER_TASK_LEDGER.yaml",
            "source_ledger_sha256": "9a411e41f1e44324311316af20404632b085b167e70eff1914aaff02ce65e947",
            "canonical_task_and_lens_index_sha256": "b4290ad1b08be16e1400c008d642ee14b416d6f39a33bb65c44f53dccd09897f",
            "task_count": 146,
            "lens_count": 20,
        },
        "audit_inputs": {
            "path": "docs/handoff/max-effort-audit-inputs.v2.json",
            "sha256": EXPECTED_AUDIT_SHA256,
            "reviewed_source_commit": reviewed_commit,
            "handoff_frozen_commit": frozen_commit,
        },
        "execution_disposition": {
            "declared_waves": 10,
            "declared_lanes": 3,
            "dependency_graph": "STRICT_SINGLE_CHAIN_T000_THROUGH_T145",
            "legal_task_execution": "SERIAL_AS_WRITTEN",
            "parallel_activity_boundary": "Independent file inspection may run in parallel, but it cannot close dependent tasks out of order.",
        },
        "completion_summary": {
            "tasks_total": 146,
            "tasks_complete": 0,
            "tasks_open": 146,
            "lens_reviews_total": 2920,
            "lens_reviews_resolved": 0,
            "lens_reviews_open": 2920,
            "decision": "NO_GO",
        },
        "requested_dispositions": {
            "requested_0_9_release": {
                "disposition": "REQUIRES_CROSS_REPOSITORY_NORMATIVE_REBASELINE",
                "action_taken": False,
                "finding": "Current bytes are package 1.0.0-rc.1, wire 1.0, proto ncp.v1, and compact hash 163acc57d8a62b66. A v0.9 label would be incoherent; a genuine 0.9 requires a reviewed normative rebaseline and coordinated consumer migration.",
            },
            "doi_and_zenodo": {
                "disposition": "DEFERRED_NOT_ASSIGNED",
                "action_taken": False,
                "finding": "No DOI or Zenodo archive is assigned or created. Citation metadata remains author-only candidate metadata until a later publication step assigns those identifiers.",
            },
            "historical_tag_and_release_cleanup": {
                "disposition": "RETAIN_IMMUTABLE_HISTORY",
                "action_taken": False,
                "finding": "No erroneous candidate tag or disposable release object exists. Historical annotated tags and release objects are compatibility, migration, and provenance evidence; v0.5.0 through v0.8.0 are machine-bound by released-baseline checks.",
            },
        },
        "global_twenty_lens_findings": _global_findings(lenses),
        "tasks": [_task_record(task, comments.get(task["id"])) for task in tasks],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--audit-inputs", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--check", action="store_true", help="compare generated bytes without writing"
    )
    args = parser.parse_args()
    try:
        index = _load(args.index, EXPECTED_INDEX_SHA256)
        audit_inputs = _load(args.audit_inputs, EXPECTED_AUDIT_SHA256)
        value = generate(index, audit_inputs, _comments(args.output))
        encoded = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
        if args.check:
            try:
                current = args.output.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as error:
                raise TemplateError(f"cannot read generated review: {error}") from error
            if current != encoded:
                raise TemplateError(
                    "max-effort review differs from reproducible template"
                )
        else:
            args.output.write_text(encoded, encoding="utf-8")
        print("OK max-effort review template: 146 OPEN tasks, 2920 OPEN lenses, NO_GO")
    except (TemplateError, OSError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
