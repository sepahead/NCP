#!/usr/bin/env python3
"""Generate the fail-closed local-convergence and external-handoff manifest."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "evidence" / "convergence" / "local-convergence.v1.json"
EXTERNAL_DETAILS = {
    "live-mtls-acl-rotation-revocation": {
        "owner": "deployment security campaign",
        "evidence_required": "live wrong-principal/entity/plane, validity, rotation, revocation, ACL, and downgrade negatives bound to one artifact set",
    },
    "two-independent-non-rust-live-peers": {
        "owner": "independent peer implementers",
        "evidence_required": "two installed non-Rust implementations exercising the live transport without Rust decision FFI",
    },
    "fault-backpressure-restart-soak": {
        "owner": "qualification environment",
        "evidence_required": "delay/loss/duplication/reordering/partition, router/peer restart, slow-consumer/flood, and duration receipts",
    },
    "fuzz-sanitizer-duration": {
        "owner": "qualification environment",
        "evidence_required": "coverage-guided parser/state/FFI fuzzing plus sanitizers for the required duration and exact source",
    },
    "performance-resource-profile": {
        "owner": "supported-platform qualification",
        "evidence_required": "artifact-bound latency, throughput, memory, queue, and saturation profiles on declared platforms",
    },
    "installed-package-matrix": {
        "owner": "package qualification",
        "evidence_required": "clean installs and zero-skip conformance for crates, wheel/sdist, npm, and C/C++ artifacts",
    },
    "registry-namespace-ownership": {
        "owner": "package registry accounts",
        "evidence_required": "verified control of every final package name or one coordinated rename across manifests, docs, tests, and consumers",
    },
    "consumer-certification": {
        "owner": "consumer repositories",
        "evidence_required": "native installed-artifact certification for every enumerated consumer against the same NCP source and artifacts",
    },
    "independent-clean-room-reproduction": {
        "owner": "independent reproducer",
        "evidence_required": "clean-room source, package, core-conformance, and checksum reproduction without the originating build cache",
    },
    "signed-sbom-provenance": {
        "owner": "hosted build and independent verifier",
        "evidence_required": "verified package checksums, vulnerability/license dossier, SBOM/provenance attestations, signatures, and revocation procedure",
    },
}
CONSUMERS = (
    "Engram",
    "crebain",
    "crebain-galadriel-producer",
    "galadriel",
    "haldir",
    "prisoma",
)
REPOSITORY_PREREQUISITE_IDS = (
    "zenoh-production-secure-peer-principal-binding",
    "zenoh-lz4-rustsec-stable-publication-hold",
    "independent-result-digest-projection",
)
HELD_SOURCE_REVISION = "ef357d20692f707e185495dcfd16b16556fec264"
HELD_SOURCE_TREE = "940e5de1ee5435ceb77485f94070e3f894b94c66"
EXPECTED_HELD_DOSSIER_SHA256 = (
    "3a514781f7e86fe3e006de13ec486a99364f7adf838140a536ce02a396889574"
)
EXPECTED_HANDOFF_REVIEW_STATE = {
    "decision": "NO_GO",
    "lens_reviews_open": 2920,
    "lens_reviews_resolved": 0,
    "lens_reviews_total": 2920,
    "tasks_complete": 0,
    "tasks_open": 146,
    "tasks_total": 146,
}
EXPECTED_REQUESTED_DISPOSITIONS = {
    "doi_and_zenodo": {
        "action_taken": False,
        "disposition": "DEFERRED_NOT_ASSIGNED",
        "finding": (
            "No DOI or Zenodo archive is assigned or created. Citation metadata "
            "remains author-only candidate metadata until a later publication step "
            "assigns those identifiers."
        ),
    },
    "historical_tag_and_release_cleanup": {
        "action_taken": False,
        "disposition": "RETAIN_IMMUTABLE_HISTORY",
        "finding": (
            "No erroneous candidate tag or disposable release object exists. "
            "Historical annotated tags and release objects are compatibility, "
            "migration, and provenance evidence; v0.5.0 through v0.8.0 are "
            "machine-bound by released-baseline checks."
        ),
    },
    "requested_0_9_release": {
        "action_taken": False,
        "disposition": "REQUIRES_CROSS_REPOSITORY_NORMATIVE_REBASELINE",
        "finding": (
            "Current bytes are package 1.0.0-rc.1, wire 1.0, proto ncp.v1, and "
            "compact hash 163acc57d8a62b66. A v0.9 label would be incoherent; a "
            "genuine 0.9 requires a reviewed normative rebaseline and coordinated "
            "consumer migration."
        ),
    },
}
HELD_CANDIDATE_EVIDENCE = {
    "status": "HELD_CANDIDATE_EVIDENCE_ONLY",
    "source_revision": HELD_SOURCE_REVISION,
    "source_tree": HELD_SOURCE_TREE,
    "verified_at_utc": "2026-07-15T12:58:20Z",
    "hosted_ci": {
        "workflow_id": 297103412,
        "workflow_path": ".github/workflows/ci.yml",
        "run_id": 29414498370,
        "run_number": 207,
        "run_attempt": 1,
        "event": "push",
        "conclusion": "success",
    },
    "dossier_workflow": {
        "workflow_id": 313593531,
        "workflow_path": ".github/workflows/candidate-dossier.yml",
        "run_id": 29414924349,
        "run_number": 2,
        "run_attempt": 1,
        "event": "workflow_dispatch",
        "conclusion": "success",
    },
    "held_artifact": {
        "artifact_id": 8342883563,
        "name": ("ncp-candidate-dossier-ef357d20692f707e185495dcfd16b16556fec264"),
        "sha256": "b2228a89232e3751a3fc205dbda1f66cc07eac7c1f7811f5cdea0a44d6277ed5",
        "size_bytes": 2338294,
    },
    "verified_dossier": {
        "candidate_dossier_json_sha256": (
            "354ec10c350b367b5013119630d79254a49fb2b3da9676c1ce6fa5693d4e3cd2"
        ),
        "checksums_sha256": (
            "47ea382dcf4c103f80d2ae8401014772594511c009bd4b7cd686a72b88cd83c6"
        ),
        "attestation_subjects_sha256": (
            "e96526feb8d91e7c8af49ff4987ea4ab2ff68d110104c49bde86a9fd2668f7ad"
        ),
        "dossier_files": 19,
        "checksum_entries": 18,
        "package_subjects": 9,
        "attestation_subjects": 10,
        "reproducibility_comparisons": 5,
    },
    "attestations": {
        "slsa_provenance": {
            "github_attestation_id": 35446154,
            "predicate_type": "https://slsa.dev/provenance/v1",
            "subject_count": 10,
            "canonical_statement_sha256": (
                "acbd27d031b756d0c39e036134e4fcdb426b320ec1bae4d3160948b68f80b82f"
            ),
            "canonical_predicate_sha256": (
                "ceedfab5d22da329a637e0bf5197b04cb7d405378cc9801a1e8b1af8bd1250c8"
            ),
            "canonical_bundle_sha256": (
                "eac629acd68a9e2f63097508655fb9ea77ebdeae192c15818c2a0d8df08be9f5"
            ),
        },
        "cyclonedx_sbom": {
            "github_attestation_id": 35446158,
            "predicate_type": "https://cyclonedx.org/bom",
            "subject_count": 1,
            "canonical_statement_sha256": (
                "5c27ce73acde745ecee6e85b75881b6faca6bb779f4fcf7419f43de38ef18403"
            ),
            "canonical_predicate_sha256": (
                "768bfb3e5c245ae639df53cb61443f68ecc6f4200590c4e22bef05ab01e89953"
            ),
            "canonical_bundle_sha256": (
                "fc85bb970b4835128f0b1a71818c38a330bd306528b238058aa4d43b6fdff2c9"
            ),
            "predicate_exactly_matches_retained_sbom": True,
        },
    },
    "gate_effect": {
        "credit": "NONE",
        "installed-package-matrix": "NOT_RUN",
        "independent-clean-room-reproduction": "NOT_RUN",
        "signed-sbom-provenance": "NOT_RUN",
        "release_authorized": False,
        "publication_evidence": False,
    },
}


class ConvergenceError(ValueError):
    """The convergence manifest is malformed or overclaims readiness."""


def _strict_json_object(raw: str, context: str) -> dict[str, Any]:
    """Decode one JSON object while rejecting duplicate keys at every depth."""

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise ConvergenceError(f"{context} contains duplicate JSON key {key!r}")
            value[key] = item
        return value

    def reject_non_finite(token: str) -> Any:
        raise ConvergenceError(f"{context} contains non-finite JSON number {token!r}")

    try:
        value = json.loads(
            raw,
            object_pairs_hook=reject_duplicates,
            parse_constant=reject_non_finite,
        )
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ConvergenceError(f"cannot parse {context}: {error}") from error
    if not isinstance(value, dict):
        raise ConvergenceError(f"{context} must contain one JSON object")
    return value


def _load(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise ConvergenceError(
            f"cannot parse {path.relative_to(ROOT)}: {error}"
        ) from error
    return _strict_json_object(raw, str(path.relative_to(ROOT)))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_sha256(value: Any) -> str:
    canonical = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _object(value: Any, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConvergenceError(f"{context} must be an object")
    return value


def _held_candidate_evidence(audit: dict[str, Any]) -> dict[str, Any]:
    if audit.get("schema") != "ncp.max-effort-handoff-audit-inputs.v2":
        raise ConvergenceError("max-effort audit-input schema drifted")
    scope = _object(audit.get("scope"), "audit scope")
    if (
        audit.get("normative") is not False
        or scope.get("release_allowed") is not False
        or scope.get("decision") != "NO_GO"
        or scope.get("doi") != "NOT_ASSIGNED"
        or scope.get("zenodo_archive") != "NOT_CREATED"
    ):
        raise ConvergenceError("audit scope overclaims release or publication")
    held = _object(audit.get("hosted_candidate_dossier"), "held candidate receipt")
    if held.get("schema") != "ncp.hosted-candidate-dossier-receipt.v1":
        raise ConvergenceError("held candidate receipt schema drifted")
    if _canonical_sha256(held) != EXPECTED_HELD_DOSSIER_SHA256:
        raise ConvergenceError(
            "held candidate receipt differs from exact reviewed bytes"
        )
    source = _object(held.get("source_boundary"), "held source boundary")
    reviewed = _object(
        _object(audit.get("source_cuts"), "audit source cuts").get("reviewed_current"),
        "reviewed source cut",
    )
    reviewed_ci = _object(reviewed.get("hosted_ci"), "reviewed hosted CI")
    hosted_ci = _object(held.get("exact_hosted_ci"), "exact hosted CI")
    dossier_run = _object(
        held.get("successful_dossier_workflow"), "successful dossier workflow"
    )
    artifact = _object(held.get("held_artifact"), "held dossier artifact")
    dossier = _object(held.get("verified_dossier"), "verified dossier")
    verification = _object(dossier.get("verification"), "dossier verification")
    comparisons = _object(
        dossier.get("reproducibility_comparisons"),
        "dossier reproducibility comparisons",
    )
    attestations = _object(held.get("attestations"), "held attestations")
    slsa = _object(attestations.get("slsa_provenance"), "SLSA attestation")
    cyclonedx = _object(attestations.get("cyclonedx_sbom"), "CycloneDX attestation")
    cyclonedx_subject = _object(
        cyclonedx.get("subject"), "CycloneDX attestation subject"
    )
    certificate = _object(
        held.get("attestation_certificate_constraints"),
        "attestation certificate constraints",
    )
    gate_effect = _object(held.get("release_gate_effect"), "held gate effect")
    normative = _object(audit.get("normative_identities"), "normative identities")
    defect = _object(
        held.get("nonqualifying_defect_discovery"),
        "nonqualifying defect-discovery run",
    )

    summary = {
        "status": "HELD_CANDIDATE_EVIDENCE_ONLY",
        "source_revision": source.get("commit"),
        "source_tree": source.get("tree"),
        "verified_at_utc": held.get("verified_at_utc"),
        "hosted_ci": {
            key: hosted_ci.get(key)
            for key in (
                "workflow_id",
                "workflow_path",
                "run_id",
                "run_number",
                "run_attempt",
                "event",
                "conclusion",
            )
        },
        "dossier_workflow": {
            key: dossier_run.get(key)
            for key in (
                "workflow_id",
                "workflow_path",
                "run_id",
                "run_number",
                "run_attempt",
                "event",
                "conclusion",
            )
        },
        "held_artifact": {
            "artifact_id": artifact.get("artifact_id"),
            "name": artifact.get("name"),
            "sha256": artifact.get("digest"),
            "size_bytes": artifact.get("size_bytes"),
        },
        "verified_dossier": {
            "candidate_dossier_json_sha256": dossier.get(
                "candidate_dossier_json_sha256"
            ),
            "checksums_sha256": dossier.get("checksums_sha256"),
            "attestation_subjects_sha256": dossier.get("attestation_subjects_sha256"),
            "dossier_files": dossier.get("dossier_files"),
            "checksum_entries": dossier.get("checksum_entries"),
            "package_subjects": dossier.get("package_subjects"),
            "attestation_subjects": dossier.get("attestation_subjects"),
            "reproducibility_comparisons": len(comparisons),
        },
        "attestations": {
            "slsa_provenance": {
                key: slsa.get(key)
                for key in (
                    "github_attestation_id",
                    "predicate_type",
                    "subject_count",
                    "canonical_statement_sha256",
                    "canonical_predicate_sha256",
                    "canonical_bundle_sha256",
                )
            },
            "cyclonedx_sbom": {
                key: cyclonedx.get(key)
                for key in (
                    "github_attestation_id",
                    "predicate_type",
                    "subject_count",
                    "canonical_statement_sha256",
                    "canonical_predicate_sha256",
                    "canonical_bundle_sha256",
                    "predicate_exactly_matches_retained_sbom",
                )
            },
        },
        "gate_effect": {
            "credit": gate_effect.get("credit"),
            "installed-package-matrix": gate_effect.get("installed-package-matrix"),
            "independent-clean-room-reproduction": gate_effect.get(
                "independent-clean-room-reproduction"
            ),
            "signed-sbom-provenance": gate_effect.get("signed-sbom-provenance"),
            "release_authorized": source.get("release_authorized"),
            "publication_evidence": False,
        },
    }
    if summary != HELD_CANDIDATE_EVIDENCE:
        raise ConvergenceError(
            "held candidate evidence differs from the reviewed receipt"
        )

    source_identity = (HELD_SOURCE_REVISION, HELD_SOURCE_TREE)
    if (
        source.get("candidate_version") != "1.0.0-rc.1"
        or source.get("wire_version") != "1.0"
        or source.get("repository") != "sepahead/NCP"
        or source.get("ref") != "refs/heads/main"
        or source.get("release_authorized") is not False
    ):
        raise ConvergenceError("held source boundary drifted or authorizes release")
    if (reviewed.get("commit"), reviewed.get("tree")) != source_identity:
        raise ConvergenceError("reviewed source cut differs from held candidate source")
    if reviewed.get("origin_main_at_capture") != HELD_SOURCE_REVISION:
        raise ConvergenceError("held candidate source was not the captured origin main")
    if any(
        reviewed_ci.get(key) != hosted_ci.get(key)
        for key in (
            "workflow_id",
            "workflow_path",
            "run_id",
            "run_number",
            "run_attempt",
            "event",
            "ref",
            "head_sha",
            "conclusion",
        )
    ):
        raise ConvergenceError("reviewed and exact hosted CI receipts differ")
    for run, context in ((hosted_ci, "hosted CI"), (dossier_run, "dossier workflow")):
        if (
            run.get("head_sha") != HELD_SOURCE_REVISION
            or run.get("workflow_source_revision") != HELD_SOURCE_REVISION
            or run.get("ref") != "refs/heads/main"
            or run.get("status") != "completed"
        ):
            raise ConvergenceError(f"{context} is not bound to the held source")
    if (
        artifact.get("source_revision") != HELD_SOURCE_REVISION
        or artifact.get("workflow_run_id") != dossier_run.get("run_id")
        or artifact.get("digest_algorithm") != "sha256"
        or artifact.get("downloaded_zip_sha256") != artifact.get("digest")
        or artifact.get("expired_at_verification") is not False
        or artifact.get("release_authorized") is not False
    ):
        raise ConvergenceError("held artifact identity or release boundary drifted")
    if (
        dossier.get("source_revision") != HELD_SOURCE_REVISION
        or dossier.get("source_tree") != HELD_SOURCE_TREE
        or dossier.get("release_authorized") is not False
        or set(comparisons)
        != {
            "rust_source_archives",
            "npm_tarballs",
            "python_wheel_same_platform",
            "python_sdist_same_platform",
            "python_sdist_build_install_smoke",
        }
        or any(status != "PASS" for status in comparisons.values())
        or verification.get("exact_dossier_check") != "PASS"
        or verification.get("attestation_subject_manifest_match") != "PASS"
        or verification.get("subject_checksum_recomputation") != "PASS"
        or verification.get("cyclonedx_predicate_exact_sbom_match") != "PASS"
        or verification.get("hosted_toolchain_required") != "PASS"
        or verification.get("slsa_subject_verifications") != slsa.get("subject_count")
        or verification.get("verifier_source_revision") != HELD_SOURCE_REVISION
        or dossier.get("candidate_version") != source.get("candidate_version")
        or dossier.get("wire_version") != source.get("wire_version")
        or dossier.get("normative_contract_digest_sha256")
        != normative.get("complete_contract_sha256")
        or dossier.get("conformance_corpus_digest_sha256")
        != normative.get("mandatory_corpus_sha256")
    ):
        raise ConvergenceError("verified held dossier identity or checks drifted")
    subjects = slsa.get("subjects")
    dossier_subjects = dossier.get("subjects")
    if (
        not isinstance(subjects, list)
        or not isinstance(dossier_subjects, list)
        or len(dossier_subjects) != dossier.get("package_subjects")
        or len(subjects) != dossier.get("attestation_subjects")
        or slsa.get("subject_count") != dossier.get("attestation_subjects")
        or cyclonedx.get("subject_count") != 1
        or cyclonedx_subject.get("sha256") != dossier.get("checksums_sha256")
        or cyclonedx.get("retained_sbom_raw_sha256")
        != dossier.get("retained_sbom_sha256")
    ):
        raise ConvergenceError("attestation subjects differ from the held dossier")
    expected_attestation_subjects = []
    for index, subject in enumerate(dossier_subjects):
        item = _object(subject, f"dossier subject {index}")
        path = item.get("path")
        if not isinstance(path, str):
            raise ConvergenceError("dossier subject path is malformed")
        expected_attestation_subjects.append(
            {
                "name": f"candidate-held/candidate-dossier/{path}",
                "sha256": item.get("sha256"),
            }
        )
    expected_attestation_subjects.append(
        {
            "name": "candidate-held/candidate-dossier/checksums.sha256",
            "sha256": dossier.get("checksums_sha256"),
        }
    )
    if subjects != expected_attestation_subjects:
        raise ConvergenceError("SLSA subjects differ from verified package subjects")
    if (
        certificate.get("repository") != "sepahead/NCP"
        or certificate.get("repository_owner") != "sepahead"
        or certificate.get("certificate_issuer")
        != "https://token.actions.githubusercontent.com"
        or certificate.get("workflow_path") != dossier_run.get("workflow_path")
        or certificate.get("workflow_ref") != "refs/heads/main"
        or certificate.get("workflow_sha") != HELD_SOURCE_REVISION
        or certificate.get("build_signer_digest") != HELD_SOURCE_REVISION
        or certificate.get("build_signer_uri")
        != (
            "https://github.com/sepahead/NCP/.github/workflows/"
            "candidate-dossier.yml@refs/heads/main"
        )
        or certificate.get("build_trigger") != "workflow_dispatch"
        or certificate.get("source_repository_digest") != HELD_SOURCE_REVISION
        or certificate.get("source_repository_ref") != "refs/heads/main"
        or certificate.get("run_invocation_uri")
        != "https://github.com/sepahead/NCP/actions/runs/29414924349/attempts/1"
        or certificate.get("self_hosted_runner_permitted") is not False
    ):
        raise ConvergenceError("attestation certificate identity drifted")
    if (
        defect.get("run_id") != 29407942080
        or defect.get("head_sha") != "a506d473937ff27ce0a073b50a62e7546bae7c2c"
        or defect.get("conclusion") != "failure"
        or defect.get("artifact_count") != 0
        or defect.get("qualifying_evidence") is not False
        or defect.get("release_gate_credit") != "NONE"
        or defect.get("disposition") != "DEFECT_DISCOVERY_ONLY"
    ):
        raise ConvergenceError("failed predecessor run was promoted to evidence")
    return summary


def build() -> dict[str, Any]:
    release = _load(ROOT / "contract" / "release-gates.v1.json")
    contract = _load(ROOT / "contract" / "manifest.v1.json")
    conformance = _load(ROOT / "conformance" / "manifest.v1.json")
    review = _load(ROOT / "docs" / "handoff" / "max-effort-task-review.v2.json")
    audit = _load(ROOT / "docs" / "handoff" / "max-effort-audit-inputs.v2.json")
    held_candidate = _held_candidate_evidence(audit)
    gates = release.get("pre_release_gates")
    if not isinstance(gates, list):
        raise ConvergenceError("release gate registry is malformed")
    local_ids = [
        gate.get("id")
        for gate in gates
        if isinstance(gate, dict)
        and gate.get("required") is True
        and gate.get("local") is True
    ]
    external_ids = [
        gate.get("id")
        for gate in gates
        if isinstance(gate, dict)
        and gate.get("required") is True
        and gate.get("local") is False
    ]
    if set(EXTERNAL_DETAILS) != set(external_ids):
        raise ConvergenceError(
            "external handoff details differ from the release-gate registry"
        )
    if local_ids != ["normative-contract", "zero-skip-conformance"]:
        raise ConvergenceError("local release-gate set drifted")
    known_external = _object(
        audit.get("known_external_gates"), "audit external-gate inventory"
    )
    if (
        known_external.get("ids") != external_ids
        or known_external.get("status") != "NOT_RUN"
    ):
        raise ConvergenceError("audit external gates differ from the release registry")
    counts = conformance.get("counts")
    if not isinstance(counts, dict):
        raise ConvergenceError("conformance counts are malformed")
    completion = review.get("completion_summary")
    dispositions = review.get("requested_dispositions")
    if completion != EXPECTED_HANDOFF_REVIEW_STATE:
        raise ConvergenceError("handoff completion state drifted or overclaims closure")
    if dispositions != EXPECTED_REQUESTED_DISPOSITIONS:
        raise ConvergenceError("requested handoff dispositions drifted")
    normative = _object(audit.get("normative_identities"), "normative identities")
    held_source = _object(
        _object(audit.get("hosted_candidate_dossier"), "held candidate receipt").get(
            "source_boundary"
        ),
        "held source boundary",
    )
    if (
        held_candidate["source_revision"] != HELD_SOURCE_REVISION
        or held_source.get("candidate_version") != contract.get("candidate")
        or held_source.get("wire_version") != contract.get("wire_version")
        or normative.get("compact_proto_fnv1a64")
        != contract.get("wire_proto_contract_hash_fnv1a64")
        or normative.get("complete_contract_sha256")
        != contract.get("contract_digest_sha256")
        or normative.get("mandatory_corpus_sha256")
        != conformance.get("corpus_digest_sha256")
    ):
        raise ConvergenceError("held source and normative identities do not converge")

    external = []
    for identifier in external_ids:
        entry = {"id": identifier, "status": "NOT_RUN", **EXTERNAL_DETAILS[identifier]}
        if identifier == "consumer-certification":
            entry["current_consumer_inventory"] = list(CONSUMERS)
        external.append(entry)
    return {
        "schema": "ncp.local-convergence.v1",
        "candidate": contract.get("candidate"),
        "wire_version": contract.get("wire_version"),
        "compact_contract_hash": contract.get("wire_proto_contract_hash_fnv1a64"),
        "normative_contract_digest_sha256": contract.get("contract_digest_sha256"),
        "conformance_corpus_digest_sha256": conformance.get("corpus_digest_sha256"),
        "conformance_counts": {
            "required": counts.get("required_total"),
            "stable": counts.get("stable_1_0"),
            "migration": counts.get("migration_only"),
        },
        "release_authorized": False,
        "decision": "NO_GO",
        "held_candidate_evidence": held_candidate,
        "local_reproducible_gates": [
            {
                "id": "normative-contract",
                "status": "REQUIRED_REPRODUCIBLE_LOCAL_GATE",
                "command": "python3 scripts/generate_contract_manifest.py",
                "evidence": "contract/manifest.v1.json",
            },
            {
                "id": "zero-skip-conformance",
                "status": "REQUIRED_REPRODUCIBLE_LOCAL_GATE",
                "command": "scripts/check.sh",
                "evidence": "conformance/manifest.v1.json",
            },
        ],
        "repository_owned_open_prerequisites": [
            {
                "id": "zenoh-production-secure-peer-principal-binding",
                "status": "OPEN_FAIL_CLOSED",
                "reason": "Zenoh 1.9 callbacks do not identify the authenticated transport link/principal for each delivered sample or query.",
                "current_behavior": "ZenohBus::open_secure validates the strict config and refuses to open.",
                "acceptance": "Implement an adapter that supplies callback-visible verified peer identity, bind every ingress identity/plane to it, and pass local negative tests before any live campaign.",
            },
            {
                "id": "zenoh-lz4-rustsec-stable-publication-hold",
                "status": "OPEN_FAIL_CLOSED",
                "reason": "Zenoh 1.9.0 retains lz4_flex 0.10.0 under RUSTSEC-2026-0041; no patched 0.10 release exists.",
                "current_behavior": "Transport compression stays disabled and the resolved feature graph is guarded, but stable publication remains blocked.",
                "acceptance": "Upgrade to a reviewed Zenoh graph that resolves a patched lz4_flex, remove the advisory disposition, and pass the dependency exposure and current RustSec gates.",
            },
            {
                "id": "independent-result-digest-projection",
                "status": "OPEN_FAIL_CLOSED",
                "reason": "The receipt result_digest has no approved normative nonrecursive wire-result projection that independent clients can recompute.",
                "current_behavior": "Clients validate digest syntax and receipt correlation but do not claim result-body certification.",
                "acceptance": "Specify and review one bounded domain-separated result projection, implement independent Rust and TypeScript computation, add cross-language vectors, and rebaseline every affected normative artifact together.",
            },
        ],
        "external_pre_release_handoff": external,
        "post_publication_validations": release.get("post_release_validations"),
        "handoff_review_state": completion,
        "requested_dispositions": dispositions,
        "source_evidence": {
            path: _sha256(ROOT / path)
            for path in (
                "contract/release-gates.v1.json",
                "contract/manifest.v1.json",
                "conformance/manifest.v1.json",
                "docs/handoff/max-effort-audit-inputs.v2.json",
                "docs/handoff/max-effort-task-review.v2.json",
            )
        },
        "claim_boundary": (
            "This deterministic NO_GO convergence inventory acknowledges an exact "
            "held-candidate dossier and hosted attestations. It does not convert them, "
            "required local commands, open implementation prerequisites, or NOT_RUN "
            "external gates into release, independent-reproduction, publication, or "
            "certification evidence."
        ),
    }


def validate(value: dict[str, Any]) -> None:
    if value.get("release_authorized") is not False or value.get("decision") != "NO_GO":
        raise ConvergenceError("convergence manifest must remain release-blocked NO_GO")
    if value.get("held_candidate_evidence") != HELD_CANDIDATE_EVIDENCE:
        raise ConvergenceError(
            "held candidate summary was dropped, altered, or promoted"
        )
    if value.get("handoff_review_state") != EXPECTED_HANDOFF_REVIEW_STATE:
        raise ConvergenceError("handoff review state was altered or promoted")
    if value.get("requested_dispositions") != EXPECTED_REQUESTED_DISPOSITIONS:
        raise ConvergenceError("requested handoff dispositions were altered")
    external = value.get("external_pre_release_handoff")
    if not isinstance(external, list):
        raise ConvergenceError("external handoff must be an array")
    identifiers = [entry.get("id") for entry in external if isinstance(entry, dict)]
    if identifiers != list(EXTERNAL_DETAILS):
        raise ConvergenceError("external handoff is missing or reorders release gates")
    if any(entry.get("status") != "NOT_RUN" for entry in external):
        raise ConvergenceError("external handoff must remain NOT_RUN")
    consumer = next(
        entry for entry in external if entry["id"] == "consumer-certification"
    )
    if tuple(consumer.get("current_consumer_inventory") or ()) != CONSUMERS:
        raise ConvergenceError("consumer handoff inventory drifted")
    prerequisites = value.get("repository_owned_open_prerequisites")
    if not isinstance(prerequisites, list) or [
        entry.get("id") if isinstance(entry, dict) else None for entry in prerequisites
    ] != list(REPOSITORY_PREREQUISITE_IDS):
        raise ConvergenceError("open repository prerequisite was dropped")
    if any(entry.get("status") != "OPEN_FAIL_CLOSED" for entry in prerequisites):
        raise ConvergenceError("repository prerequisite overclaims completion")


def self_test(value: dict[str, Any]) -> None:
    def expect_invalid(candidate: dict[str, Any], context: str) -> None:
        try:
            validate(candidate)
        except ConvergenceError:
            pass
        else:
            raise AssertionError(f"{context} mutation passed convergence validation")

    def expect_invalid_receipt(path: tuple[str | int, ...], replacement: Any) -> None:
        hostile = copy.deepcopy(audit)
        target: Any = hostile
        for member in path[:-1]:
            if isinstance(member, int):
                if not isinstance(target, list):
                    raise AssertionError("hostile receipt path expected an array")
                target = target[member]
            else:
                target = _object(target, "hostile receipt path").get(member)
        final = path[-1]
        if isinstance(final, int):
            if not isinstance(target, list):
                raise AssertionError("hostile receipt path expected an array")
            target[final] = replacement
        else:
            _object(target, "hostile receipt path")[final] = replacement
        try:
            _held_candidate_evidence(hostile)
        except ConvergenceError:
            pass
        else:
            rendered = ".".join(str(member) for member in path)
            raise AssertionError(f"tampered held receipt field {rendered} passed")

    audit = _load(ROOT / "docs" / "handoff" / "max-effort-audit-inputs.v2.json")
    for ambiguous in (
        '{"release_authorized":true,"release_authorized":false}',
        '{"source_evidence":{"digest":"a","digest":"b"}}',
        '{"conformance_counts":{"required":NaN}}',
    ):
        try:
            _strict_json_object(ambiguous, "hostile self-test convergence JSON")
        except ConvergenceError:
            pass
        else:
            raise AssertionError("duplicate JSON key passed convergence parsing")
    released = copy.deepcopy(value)
    released["release_authorized"] = True
    expect_invalid(released, "release authorization")
    go_decision = copy.deepcopy(value)
    go_decision["decision"] = "GO"
    expect_invalid(go_decision, "GO decision")
    completed_review = copy.deepcopy(value)
    completed_review["handoff_review_state"].update(
        {
            "decision": "GO",
            "tasks_complete": 146,
            "tasks_open": 0,
            "lens_reviews_resolved": 2920,
            "lens_reviews_open": 0,
        }
    )
    expect_invalid(completed_review, "promoted handoff review")
    acted_disposition = copy.deepcopy(value)
    acted_disposition["requested_dispositions"]["doi_and_zenodo"]["action_taken"] = True
    expect_invalid(acted_disposition, "acted publication disposition")
    for index, identifier in enumerate(EXTERNAL_DETAILS):
        passed_external = copy.deepcopy(value)
        passed_external["external_pre_release_handoff"][index]["status"] = "PASS"
        expect_invalid(passed_external, f"external gate {identifier}")
    promoted_held = copy.deepcopy(value)
    promoted_held["held_candidate_evidence"]["gate_effect"][
        "signed-sbom-provenance"
    ] = "PASS"
    expect_invalid(promoted_held, "held-evidence gate credit")
    missing_consumer = copy.deepcopy(value)
    missing_consumer["external_pre_release_handoff"][7][
        "current_consumer_inventory"
    ].pop()
    expect_invalid(missing_consumer, "missing consumer")
    missing_prerequisite = copy.deepcopy(value)
    missing_prerequisite["repository_owned_open_prerequisites"].pop()
    expect_invalid(missing_prerequisite, "missing repository prerequisite")

    for path, replacement in (
        (
            ("hosted_candidate_dossier", "source_boundary", "commit"),
            "0" * 40,
        ),
        (
            ("hosted_candidate_dossier", "exact_hosted_ci", "run_id"),
            29414498371,
        ),
        (
            (
                "hosted_candidate_dossier",
                "exact_hosted_ci",
                "jobs",
                0,
                "conclusion",
            ),
            "failure",
        ),
        (
            (
                "hosted_candidate_dossier",
                "successful_dossier_workflow",
                "run_id",
            ),
            29414924350,
        ),
        (
            ("hosted_candidate_dossier", "held_artifact", "digest"),
            "0" * 64,
        ),
        (
            (
                "hosted_candidate_dossier",
                "verified_dossier",
                "verification",
                "hosted_toolchain_required",
            ),
            "FAIL",
        ),
        (
            (
                "hosted_candidate_dossier",
                "verified_dossier",
                "toolchain_receipt",
                "rustc",
            ),
            "unknown",
        ),
        (
            (
                "hosted_candidate_dossier",
                "attestations",
                "slsa_provenance",
                "github_attestation_id",
            ),
            35446155,
        ),
        (
            (
                "hosted_candidate_dossier",
                "attestations",
                "cyclonedx_sbom",
                "canonical_bundle_sha256",
            ),
            "0" * 64,
        ),
        (
            (
                "hosted_candidate_dossier",
                "attestations",
                "cyclonedx_sbom",
                "subject",
                "name",
            ),
            "unrelated",
        ),
        (
            (
                "hosted_candidate_dossier",
                "release_gate_effect",
                "signed-sbom-provenance",
            ),
            "PASS",
        ),
        (
            (
                "hosted_candidate_dossier",
                "release_gate_effect",
                "independent-clean-room-reproduction",
            ),
            "PASS",
        ),
        (
            (
                "hosted_candidate_dossier",
                "release_gate_effect",
                "installed-package-matrix",
            ),
            "PASS",
        ),
        (
            ("hosted_candidate_dossier", "release_gate_effect", "credit"),
            "PARTIAL",
        ),
        (
            (
                "hosted_candidate_dossier",
                "source_boundary",
                "release_authorized",
            ),
            True,
        ),
        (
            ("hosted_candidate_dossier", "normative"),
            True,
        ),
        (
            ("scope", "release_allowed"),
            True,
        ),
        (
            ("scope", "decision"),
            "GO",
        ),
        (
            (
                "hosted_candidate_dossier",
                "nonqualifying_defect_discovery",
                "qualifying_evidence",
            ),
            True,
        ),
    ):
        expect_invalid_receipt(path, replacement)


def encoded(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        value = build()
        validate(value)
        if args.self_test:
            self_test(value)
        expected = encoded(value)
        if args.check:
            if OUTPUT.read_bytes() != expected:
                raise ConvergenceError(f"{OUTPUT.relative_to(ROOT)} is stale")
        else:
            OUTPUT.parent.mkdir(parents=True, exist_ok=True)
            OUTPUT.write_bytes(expected)
    except (
        ConvergenceError,
        AssertionError,
        KeyError,
        OSError,
        TypeError,
        UnicodeError,
    ) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    mode = "verified" if args.check else "generated"
    print(f"OK local convergence manifest {mode}: NO_GO, 10 external gates NOT_RUN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
