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


def build() -> dict[str, Any]:
    release = _load(ROOT / "contract" / "release-gates.v1.json")
    contract = _load(ROOT / "contract" / "manifest.v1.json")
    conformance = _load(ROOT / "conformance" / "manifest.v1.json")
    review = _load(ROOT / "docs" / "handoff" / "max-effort-task-review.v2.json")
    gates = release.get("pre_release_gates")
    if not isinstance(gates, list):
        raise ConvergenceError("release gate registry is malformed")
    local_ids = [
        gate["id"]
        for gate in gates
        if isinstance(gate, dict)
        and gate.get("required") is True
        and gate.get("local") is True
    ]
    external_ids = [
        gate["id"]
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
    counts = conformance.get("counts")
    if not isinstance(counts, dict):
        raise ConvergenceError("conformance counts are malformed")
    completion = review.get("completion_summary")
    dispositions = review.get("requested_dispositions")
    if not isinstance(completion, dict) or not isinstance(dispositions, dict):
        raise ConvergenceError("handoff completion or disposition state is malformed")

    external = []
    for identifier in external_ids:
        entry = {"id": identifier, "status": "NOT_RUN", **EXTERNAL_DETAILS[identifier]}
        if identifier == "consumer-certification":
            entry["current_consumer_inventory"] = list(CONSUMERS)
        external.append(entry)
    return {
        "schema": "ncp.local-convergence.v1",
        "candidate": contract["candidate"],
        "wire_version": contract["wire_version"],
        "compact_contract_hash": contract["wire_proto_contract_hash_fnv1a64"],
        "normative_contract_digest_sha256": contract["contract_digest_sha256"],
        "conformance_corpus_digest_sha256": conformance["corpus_digest_sha256"],
        "conformance_counts": {
            "required": counts["required_total"],
            "stable": counts["stable_1_0"],
            "migration": counts["migration_only"],
        },
        "release_authorized": False,
        "decision": "NO_GO",
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
        "post_publication_validations": release["post_release_validations"],
        "handoff_review_state": completion,
        "requested_dispositions": dispositions,
        "source_evidence": {
            path: _sha256(ROOT / path)
            for path in (
                "contract/release-gates.v1.json",
                "contract/manifest.v1.json",
                "conformance/manifest.v1.json",
                "docs/handoff/max-effort-task-review.v2.json",
            )
        },
        "claim_boundary": (
            "This is a deterministic NO_GO convergence and handoff inventory. It does "
            "not convert required local commands, open implementation prerequisites, "
            "or NOT_RUN external gates into passing evidence."
        ),
    }


def validate(value: dict[str, Any]) -> None:
    if value.get("release_authorized") is not False or value.get("decision") != "NO_GO":
        raise ConvergenceError("convergence manifest must remain release-blocked NO_GO")
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
    try:
        validate(released)
    except ConvergenceError:
        pass
    else:
        raise AssertionError("release authorization mutation passed")
    passed_external = copy.deepcopy(value)
    passed_external["external_pre_release_handoff"][0]["status"] = "PASS"
    try:
        validate(passed_external)
    except ConvergenceError:
        pass
    else:
        raise AssertionError("unevidenced external pass mutation passed")
    missing_consumer = copy.deepcopy(value)
    missing_consumer["external_pre_release_handoff"][7][
        "current_consumer_inventory"
    ].pop()
    try:
        validate(missing_consumer)
    except ConvergenceError:
        pass
    else:
        raise AssertionError("missing consumer mutation passed")
    missing_prerequisite = copy.deepcopy(value)
    missing_prerequisite["repository_owned_open_prerequisites"].pop()
    try:
        validate(missing_prerequisite)
    except ConvergenceError:
        pass
    else:
        raise AssertionError("missing repository prerequisite mutation passed")


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
    except (ConvergenceError, AssertionError, OSError, UnicodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    mode = "verified" if args.check else "generated"
    print(f"OK local convergence manifest {mode}: NO_GO, 10 external gates NOT_RUN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
