#!/usr/bin/env python3
"""Generate the retained T004/T006/T008 audit artifacts.

The artifacts are deliberately non-normative.  They make three repository-owned
review obligations reproducible without turning local inspection into release or
certification evidence:

* the threat, misuse, failure, and quirky-case register;
* the exact tracked-text latent-marker/fallback inventory; and
* the requirement-to-code-to-test-to-evidence graph.

The marker inventory scans Git-indexed and non-ignored untracked worktree files.
Generated audit outputs are supplied as virtual expected bytes during the scan so
``--check`` detects stale output without depending on stale generated content.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tomllib
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
AUDIT_DIR = ROOT / "evidence" / "audit"
THREAT_REGISTER = AUDIT_DIR / "threat-register.v1.json"
LATENT_INVENTORY = AUDIT_DIR / "latent-path-inventory.v1.json"
TRACEABILITY = AUDIT_DIR / "requirement-traceability.v1.json"
MANIFEST = AUDIT_DIR / "manifest.v1.json"
README = AUDIT_DIR / "README.md"

SURFACE = ROOT / "contract" / "surface.v1.json"
RELEASE_GATES = ROOT / "contract" / "release-gates.v1.json"
CONFORMANCE = ROOT / "conformance" / "manifest.v1.json"
CONTRACT_MANIFEST = ROOT / "contract" / "manifest.v1.json"

SCHEMA_VERSION = "1"
WIRE_VERSION = "1.0"
GENERATOR = "scripts/generate_audit_artifacts.py"
CHECKER = "scripts/check_audit_artifacts.py"

TOKEN_CATALOG = {
    "M001": "TODO",
    "M002": "FIXME",
    "M003": "HACK",
    "M004": "XXX",
    "M005": "unimplemented",
    "M006": "dormant",
    "M007": "experimental",
    "M008": "fallback",
}
TOKEN_PATTERN = re.compile(
    r"\b(?:" + "|".join(re.escape(value) for value in TOKEN_CATALOG.values()) + r")\b",
    re.IGNORECASE,
)
TOKEN_ID = {value.casefold(): identifier for identifier, value in TOKEN_CATALOG.items()}

COUNTERFACTUALS = {
    "CF-01": "valid syntax with contradictory semantics",
    "CF-02": "authenticated but unauthorized producer",
    "CF-03": "stale yet correctly signed data",
    "CF-04": "correct version string with wrong contract or algorithm digest",
    "CF-05": "clean synthetic result under a nonrepresentative distribution",
    "CF-06": "timeout or capacity exhaustion followed by convenience fallback",
    "CF-07": "feature unification activating a privileged or experimental path",
    "CF-08": "partial migration accepted through default values",
    "CF-09": "crash between decision or output and durable evidence",
    "CF-10": "simple but odd input unlikely to resemble familiar examples",
}

CLAIM_BOUNDARY = (
    "These generated records are local, non-normative candidate audit controls. "
    "They do not close the handoff tasks, resolve independent review, satisfy an "
    "external release gate, certify a consumer or deployment, or authorize publication."
)


class AuditGenerationError(ValueError):
    """A deterministic audit artifact cannot be generated honestly."""


def _object_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, member in pairs:
        if key in value:
            raise AuditGenerationError(f"duplicate JSON key {key!r}")
        value[key] = member
    return value


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=_object_no_duplicates
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise AuditGenerationError(f"cannot read {relative(path)}: {error}") from error
    if not isinstance(value, dict):
        raise AuditGenerationError(f"{relative(path)} must contain one JSON object")
    return value


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def package_version() -> str:
    try:
        value = tomllib.loads((ROOT / "Cargo.toml").read_text(encoding="utf-8"))
        candidate = value["workspace"]["package"]["version"]
    except (OSError, UnicodeError, tomllib.TOMLDecodeError, KeyError) as error:
        raise AuditGenerationError(
            f"cannot derive candidate version: {error}"
        ) from error
    if not isinstance(candidate, str) or not candidate:
        raise AuditGenerationError(
            "workspace candidate version must be a non-empty string"
        )
    return candidate


def _threat(
    number: int,
    title: str,
    category: str,
    boundary: str,
    asset_or_claim: str,
    actor_or_trigger: str,
    preconditions: list[str],
    misuse_or_failure: str,
    accepted_case: str,
    rejected_case: str,
    impact: str,
    detection: list[str],
    prevention: list[str],
    failure_response: str,
    counterfactual_ids: list[str],
    requirement_ids: list[str],
    code_paths: list[str],
    test_paths: list[str],
    commands: list[str],
    evidence_paths: list[str],
    control_status: str,
    residual_risk: str,
    release_blocking: bool,
) -> dict[str, Any]:
    identifier = f"NCP-THREAT-{number:03d}"
    control_requirement = f"NCP-THREAT-REQ-{number:03d}"
    return {
        "id": identifier,
        "control_requirement_id": control_requirement,
        "title": title,
        "category": category,
        "boundary": boundary,
        "asset_or_claim": asset_or_claim,
        "actor_or_trigger": actor_or_trigger,
        "preconditions": preconditions,
        "misuse_or_failure": misuse_or_failure,
        "accepted_case": accepted_case,
        "rejected_case": rejected_case,
        "impact": impact,
        "detection": detection,
        "prevention": prevention,
        "failure_response": failure_response,
        "counterfactual_ids": counterfactual_ids,
        "requirement_ids": [*requirement_ids, control_requirement],
        "code_paths": code_paths,
        "test_paths": test_paths,
        "verification_commands": commands,
        "evidence_paths": evidence_paths,
        "control_status": control_status,
        "risk_status": "OPEN",
        "release_blocking": release_blocking,
        "residual_risk": residual_risk,
    }


def threat_records() -> list[dict[str, Any]]:
    behavior = "conformance/behavior/vectors.json"
    receipt = "docs/1.0-candidate-receipts.md"
    records = [
        _threat(
            1,
            "Payload identity is mistaken for authentication",
            "authentication",
            "transport principal to NCP identity claim",
            "principal, entity, role, and plane authorization",
            "remote peer with a syntactically valid claim",
            ["a payload reaches an NCP-aware transport boundary"],
            "The receiver trusts IdentityClaim without binding it to the verified transport principal.",
            "A development-loopback message remains visibly unauthenticated and non-production.",
            "A production message without callback-visible verified principal binding is rejected before state change.",
            "An attacker can impersonate a commander, body, observer, or operator.",
            ["profile reason codes", "identity and ACL negative vectors"],
            [
                "default-deny authority manifest",
                "production-secure open fails closed until binding exists",
            ],
            "Reject the message or startup; do not infer identity from payload fields.",
            ["CF-02"],
            ["NCP-REQ-003", "NCP-REQ-006"],
            [
                "ncp-core/src/security.rs",
                "ncp-core/src/messages.rs",
                "ncp-zenoh/src/lib.rs",
            ],
            ["ncp-core/tests/behavior_conformance.rs", "ncp-zenoh/tests/loopback.rs"],
            ["cargo test -p ncp-core --locked", "cargo test -p ncp-zenoh --locked"],
            ["SECURITY.md", "KNOWN_LIMITATIONS.md", receipt],
            "PARTIAL_LOCAL",
            "The stable Zenoh API still lacks callback-visible authenticated peer identity; the live campaign is NOT RUN.",
            True,
        ),
        _threat(
            2,
            "Authenticated peer exceeds enrolled authority",
            "authorization",
            "verified principal to exact entity, role, plane, session, and lease",
            "least privilege and final actuator authority",
            "credentialed but unauthorized peer",
            [
                "transport authentication succeeded",
                "the peer requests another plane or entity",
            ],
            "Authentication alone is treated as permission to publish or mutate.",
            "An enrolled commander with the exact live lease may issue an admitted mutation.",
            "A valid certificate for the wrong entity, role, plane, or lease is denied.",
            "A credentialed peer widens its authority or actuates another plant.",
            ["registered authorization errors", "ACL and authority negative tests"],
            [
                "exact claim binding",
                "closed roles and planes",
                "bounded matching lease",
            ],
            "Fail closed to denial or HOLD without changing authority state.",
            ["CF-02", "CF-01"],
            ["NCP-REQ-003", "NCP-REQ-006"],
            [
                "ncp-core/src/authority.rs",
                "ncp-core/src/security.rs",
                "deploy/zenoh-access-control.json5",
            ],
            ["ncp-core/tests/behavior_conformance.rs", "scripts/check_acl_template.py"],
            [
                "cargo test -p ncp-core --locked",
                "python3 scripts/check_acl_template.py",
            ],
            ["SECURITY.md", behavior, receipt],
            "LOCAL_PREREQUISITES_ONLY",
            "Offline policy is tested, but live verified-principal enforcement remains unavailable.",
            True,
        ),
        _threat(
            3,
            "Stale generation or stream position is replayed",
            "replay",
            "session generation and publisher stream",
            "freshness, high-water state, and restart fencing",
            "prior holder, delayed network sample, or restarted publisher",
            [
                "an old message remains well formed",
                "the session or publisher has advanced",
            ],
            "A correctly encoded stale frame refreshes a lease, watchdog, TTL, or output.",
            "The exact live generation and strictly increasing position are accepted.",
            "A retired generation, foreign epoch, duplicate, or lower sequence is rejected before callback or latch mutation.",
            "Old authority or action is revived after restart or reordering.",
            ["stream-fence result", "session mismatch error", "unchanged latch state"],
            [
                "generation binding",
                "one-epoch declaration",
                "permanent high-water state",
            ],
            "Reject without refreshing any deadline or safety state.",
            ["CF-03"],
            ["NCP-REQ-005", "NCP-REQ-006"],
            [
                "ncp-core/src/stream_fence.rs",
                "ncp-core/src/transport.rs",
                "ncp-zenoh/src/lib.rs",
            ],
            [
                "ncp-core/tests/behavior_conformance.rs",
                "ncp-zenoh/tests/cross_session_rpc.rs",
            ],
            ["cargo test -p ncp-core --locked", "cargo test -p ncp-zenoh --locked"],
            ["NEURO_CYBERNETIC_PROTOCOL.md", behavior, receipt],
            "LOCAL_VERIFIED_WITH_EXTERNAL_GAP",
            "Process-crash, capture replay, rollover, and duration campaigns remain incomplete.",
            True,
        ),
        _threat(
            4,
            "Version text masks contract or algorithm drift",
            "compatibility",
            "wire compatibility and complete normative identity",
            "one coherent candidate contract",
            "peer or package with the right wire string and different semantics",
            ["wire major is compatible", "contract bytes or digest algorithm differ"],
            "A matching version string is treated as proof of identical semantics.",
            "The wire gate accepts compatible 1.x and reports the exact complete digest separately.",
            "Malformed versions fail; compact or complete digest drift is surfaced and cannot certify artifacts.",
            "Peers silently disagree on security, safety, or canonicalization rules.",
            ["contract-status mismatch", "manifest and package identity checks"],
            [
                "complete SHA-256 manifest",
                "advisory compact hash",
                "version-coherence gate",
            ],
            "Reject malformed/incompatible wire and retain digest mismatch as non-certifying evidence.",
            ["CF-04"],
            ["NCP-REQ-001", "NCP-REQ-013"],
            [
                "ncp-core/src/contract_identity.rs",
                "ncp-core/src/messages.rs",
                "scripts/generate_contract_manifest.py",
            ],
            [
                "ncp-core/tests/behavior_conformance.rs",
                "scripts/check-version-coherence.sh",
            ],
            [
                "python3 scripts/generate_contract_manifest.py",
                "scripts/check-version-coherence.sh",
            ],
            ["contract/manifest.v1.json", behavior, receipt],
            "LOCAL_VERIFIED",
            "Independent artifact-bound verification and signatures remain external release evidence.",
            True,
        ),
        _threat(
            5,
            "Syntactically valid but contradictory state grants success",
            "semantic-integrity",
            "decoded message to state transition",
            "closed lifecycle, error, authority, capability, and scientific states",
            "peer constructing mutually inconsistent fields",
            ["JSON and schema syntax are valid"],
            "Unknown, default, or contradictory values are interpreted as authority or success.",
            "A complete known state satisfying all cross-field invariants is admitted.",
            "Unknown enums, missing evidence, mismatched receipts, or contradictory flags fail closed.",
            "Invalid combinations reach application or actuation state.",
            ["registered validation outcome", "negative corpus exact-set execution"],
            ["closed registries", "semantic validators", "non-authorizing defaults"],
            "Return a registered error or non-authorizing HOLD state.",
            ["CF-01", "CF-10"],
            ["NCP-REQ-008", "NCP-REQ-009", "NCP-REQ-012"],
            ["ncp-core/src/messages.rs", "ncp-core/src/safety.rs"],
            ["ncp-core/tests/behavior_conformance.rs", "ncp-core/tests/conformance.rs"],
            ["cargo test -p ncp-core --locked"],
            [behavior, "conformance/manifest.v1.json", receipt],
            "LOCAL_VERIFIED",
            "All-language construction and independent mutation evidence remain incomplete.",
            True,
        ),
        _threat(
            6,
            "Resource exhaustion triggers permissive recovery",
            "availability",
            "untrusted bytes and transport work queues",
            "bounded parsing, queues, retries, and fail-safe behavior",
            "malformed sender, slow consumer, flood, or exhausted host",
            ["an ingress or queue reaches a configured limit"],
            "A timeout, overflow, or allocation failure bypasses validation or widens authority.",
            "Within-budget input is decoded before semantic allocation.",
            "Oversize, over-depth, queue-full, timeout, or cancellation states fail explicitly without a permissive fallback.",
            "Denial of service becomes unauthorized delivery or invisible data loss.",
            ["NCP-LIMIT codes", "drop/reject counters", "bounded terminal errors"],
            ["universal preflight", "plane-specific capacities", "finite timeouts"],
            "Reject, count, HOLD, or terminate the affected transport; never grant success.",
            ["CF-06", "CF-10"],
            ["NCP-REQ-002", "NCP-REQ-010"],
            [
                "ncp-core/src/bounded_json.rs",
                "ncp-core/src/resilience.rs",
                "ncp-ts/src/ws.ts",
            ],
            [
                "e2e/test_bounded_json.py",
                "ncp-ts/scripts/check-ws.mjs",
                "ncp-zenoh/tests/loopback.rs",
            ],
            [
                "python3 -m unittest -v e2e.test_bounded_json",
                "cd ncp-ts && bun run check:ws",
                "cargo test -p ncp-zenoh --locked",
            ],
            ["contract/limits.v1.json", "RESILIENCE.md", receipt],
            "LOCAL_VERIFIED_WITH_EXTERNAL_GAP",
            "Maximum-size CPU/RSS, hostile traffic, leak, and duration evidence is NOT RUN.",
            True,
        ),
        _threat(
            7,
            "Dependency feature unification activates excluded code",
            "supply-chain",
            "resolved dependency features",
            "reviewed Zenoh transport surface and advisory containment",
            "downstream feature unification or dependency update",
            ["a dependent enables defaults or transport compression"],
            "An excluded vulnerable or privileged feature enters the compiled surface silently.",
            "The reviewed lock and exact feature set keep defaults and compression disabled.",
            "Unexpected Zenoh defaults, compression, or unreviewed versions fail the dependency-exposure gate.",
            "The shipped attack surface differs from the reviewed candidate.",
            ["resolved feature inspection", "cargo-deny advisory output"],
            [
                "exact lock",
                "feature exposure checker",
                "publication hold on the retained Zenoh/lz4 advisory",
            ],
            "Fail CI and keep publication blocked until the graph is patched and re-reviewed.",
            ["CF-07"],
            [],
            [
                "Cargo.lock",
                "ncp-zenoh/Cargo.toml",
                "scripts/check_dependency_exposure.py",
            ],
            ["scripts/check_dependency_exposure.py", ".github/workflows/ci.yml"],
            [
                "python3 scripts/check_dependency_exposure.py --self-test",
                "cargo deny check",
            ],
            [
                "KNOWN_LIMITATIONS.md",
                "deny.toml",
                "evidence/supply-chain/vulnerability-report.v1.json",
                receipt,
            ],
            "PARTIAL_LOCAL",
            "The reviewed Zenoh path still locks the lz4_flex advisory while defaults and compression remain disabled under the resolved-feature guard; that specific residual blocks stable publication.",
            True,
        ),
        _threat(
            8,
            "Partial 0.8 migration invents missing context",
            "migration",
            "legacy wire input to native 1.0 state",
            "identity, security, session, authority, units, frames, and epistemic integrity",
            "legacy gateway or copied consumer contract",
            ["wire 0.8 lacks mandatory 1.0 context"],
            "Defaults or guessed values make an incomplete legacy message appear native 1.0.",
            "The labelled terminating translator maps only explicit authenticated channel requirements.",
            "Missing, null, mixed, reverse, transparent, or context-inventing translation is rejected.",
            "A legacy peer gains native authority or produces scientifically mislabelled data.",
            ["migration reason code", "seven migration vectors"],
            [
                "one-way bounded translator",
                "no transparent proxy",
                "native consumer certification boundary",
            ],
            "Reject conversion and retain the source as legacy-unqualified input.",
            ["CF-08"],
            ["NCP-REQ-004"],
            [
                "ncp-core/src/migration.rs",
                "ncp-core/src/migration/capture.rs",
                "ncp-gateway/src/main.rs",
            ],
            [
                "ncp-core/tests/behavior_conformance.rs",
                "conformance/migration/v0.8-to-v1.0/wire-0.8-reconstructable-capture.json",
                "ncp-core/testdata/migration/wire-0.8-reconstructable-capture.json",
                "conformance/migration/v0.8-to-v1.0/channel-requirement.json",
            ],
            ["cargo test -p ncp-core --locked"],
            ["INTEGRATING.md", "KNOWN_LIMITATIONS.md", receipt],
            "PARTIAL_LOCAL",
            "The bounded repository validator checks explicit legacy units, frames, lineage, restart boundaries, and epistemic fields and excludes records needing unavailable native-1.0 authority or operation evidence; it emits no native-1.0 capture, while live consumer captures, independent clean-room replay, and installed-artifact migration certification remain NOT RUN.",
            True,
        ),
        _threat(
            9,
            "Crash separates mutation outcome from durable evidence",
            "crash-consistency",
            "idempotent mutation and responder receipt",
            "at-most-once retry semantics and explicit unknown outcome",
            "process crash, reply loss, cache eviction, or restart",
            [
                "a mutation may have committed",
                "the caller lacks a correlated terminal receipt",
            ],
            "The caller retries and assumes success or re-executes because the result is absent.",
            "A matching authenticated terminal receipt is replayed from retained idempotency state.",
            "Unprovable outcomes return outcome_unknown and are never guessed or executed again by assumption.",
            "A lifecycle mutation is duplicated or a false success is reported.",
            ["receipt correlation", "idempotency conflict/busy/unknown outcomes"],
            ["principal-bound cache key", "request digest", "snapshot-capable state"],
            "Return explicit unknown outcome and require reconciliation outside the mutation path.",
            ["CF-09"],
            ["NCP-REQ-007"],
            [
                "ncp-core/src/idempotency.rs",
                "ncp-core/src/request_digest.rs",
                "ncp-core/src/messages.rs",
            ],
            [
                "ncp-core/tests/behavior_conformance.rs",
                "conformance/request-digest/v1.json",
            ],
            [
                "cargo test -p ncp-core --locked",
                "python3 scripts/check_request_digests.py",
            ],
            ["NEURO_CYBERNETIC_PROTOCOL.md", behavior, receipt],
            "LOCAL_VERIFIED_WITH_EXTERNAL_GAP",
            "Durable server integration and process-crash campaigns remain NOT RUN.",
            True,
        ),
        _threat(
            10,
            "Synthetic output is promoted to scientific evidence",
            "scientific-integrity",
            "simulation output to downstream claim",
            "honest epistemic and provenance boundary",
            "operator, paper, dashboard, or downstream dataset",
            ["a clean simulation result resembles expected behavior"],
            "Simulation output is described as calibrated, experimental, representative, or a reproduction.",
            "Output remains explicitly simulation output with calibrated_posterior=false.",
            "Missing or upgraded epistemic flags and unsupported reproduction claims are rejected or removed.",
            "Scientific conclusions exceed the model, data, and validation evidence.",
            ["scientific-boundary validation", "claim and documentation review"],
            ["mandatory flags", "provenance fields", "explicit non-claims"],
            "Reject the message or narrow the public claim to raw simulation/control output.",
            ["CF-05"],
            ["NCP-REQ-009"],
            ["ncp-core/src/messages.rs", "ncp-core/src/audit.rs"],
            ["ncp-core/tests/behavior_conformance.rs", "ncp-cpp/tests/corpus.rs"],
            ["cargo test -p ncp-core --locked"],
            ["NEURO_CYBERNETIC_PROTOCOL.md", "NEUROMORPHIC.md", behavior],
            "LOCAL_VERIFIED_NON_CLAIM",
            "No external scientific validation or representative-distribution campaign exists.",
            False,
        ),
        _threat(
            11,
            "Protocol ESTOP is mistaken for physical safety certification",
            "physical-safety",
            "command protocol to plant actuation",
            "plant-owned safe action and final actuator authority",
            "deployment relying on mode text or transport success",
            ["an ESTOP or HOLD message is accepted or published"],
            "Protocol state is treated as proof that a physical plant stopped safely.",
            "The body applies its content-addressed plant profile and independent interlock.",
            "A missing/mismatched profile, stale session, or malformed ESTOP is rejected without inventing a universal action.",
            "Physical harm occurs despite a nominal protocol success.",
            [
                "profile digest",
                "governor/latch state",
                "plant-local acknowledgement outside current wire",
            ],
            [
                "body final authority",
                "profile-owned HOLD/ESTOP action",
                "physical-safety non-claim",
            ],
            "Fail safe at the body and retain the absence of physical acknowledgement as an open limitation.",
            ["CF-01", "CF-05"],
            ["NCP-REQ-010", "NCP-REQ-011"],
            ["ncp-core/src/plant.rs", "ncp-core/src/safety.rs", "ncp-zenoh/src/lib.rs"],
            [
                "ncp-core/tests/profile_digest_conformance.rs",
                "ncp-zenoh/tests/safety_governor_over_wire.rs",
            ],
            ["cargo test -p ncp-core --locked", "cargo test -p ncp-zenoh --locked"],
            ["SECURITY.md", "KNOWN_LIMITATIONS.md", receipt],
            "LOCAL_VERIFIED_NON_CLAIM",
            "No physical plant, universal safe action, or applied-command acknowledgement is certified.",
            False,
        ),
        _threat(
            12,
            "Production profile downgrades or starts partially configured",
            "configuration-security",
            "deployment configuration to transport startup",
            "mutual TLS, default-deny ACL, and no downgrade",
            "misconfiguration, missing secret, expired certificate, or rushed operator",
            ["production-secure is selected"],
            "A missing control silently falls back to plaintext, discovery, or development mode.",
            "A complete valid profile is precommitted and bound to an exact security-state digest.",
            "Partial TLS, insecure endpoints, hidden listeners, discovery, downgrade, or invalid files fail startup.",
            "A deployment appears secure while accepting unauthenticated or overbroad traffic.",
            [
                "profile validation reason",
                "startup failure",
                "live router evidence when available",
            ],
            ["closed profiles", "no fail-soft path", "security-state digest"],
            "Abort startup and keep the live security gate NOT RUN.",
            ["CF-06", "CF-02"],
            ["NCP-REQ-003"],
            [
                "ncp-core/src/security.rs",
                "ncp-zenoh/src/lib.rs",
                "scripts/validate_security_profile.py",
            ],
            [
                "scripts/validate_security_profile.py",
                "scripts/verify_acl_deployment.py",
            ],
            [
                "python3 scripts/validate_security_profile.py --self-test",
                "python3 scripts/verify_acl_deployment.py --self-test",
            ],
            ["SECURITY.md", "RELEASE_READINESS.md", receipt],
            "PARTIAL_LOCAL",
            "Principal binding is unimplemented and the live certificate/rotation/revocation campaign is NOT RUN.",
            True,
        ),
        _threat(
            13,
            "Route and payload refer to different live sessions",
            "routing-integrity",
            "actual transport key to payload session identity",
            "cross-session isolation",
            "misrouted, malicious, delayed, or copied data-plane sample",
            ["the payload itself is well formed"],
            "A receiver trusts the payload session while delivery occurred on another route or generation.",
            "Route session, payload session_id, and current generation all match exactly.",
            "Cross-route, missing, stale, or foreign generation samples are rejected before callback and latch mutation.",
            "One session observes or actuates another session's data.",
            ["route/session rejection", "callback count", "unchanged safety state"],
            ["typed transport wrappers", "exact session and generation checks"],
            "Drop or reject the sample without repairing inbound identity.",
            ["CF-03", "CF-10"],
            ["NCP-REQ-005", "NCP-REQ-012"],
            ["ncp-core/src/transport.rs", "ncp-zenoh/src/lib.rs"],
            ["ncp-zenoh/tests/cross_session_rpc.rs", "ncp-zenoh/tests/loopback.rs"],
            ["cargo test -p ncp-zenoh --locked"],
            ["NEURO_CYBERNETIC_PROTOCOL.md", "SECURITY.md", receipt],
            "LOCAL_VERIFIED_WITH_EXTERNAL_GAP",
            "Authenticated multi-process cross-session evidence remains part of the NOT RUN live campaign.",
            True,
        ),
        _threat(
            14,
            "Ambiguous delivery reuses an action position",
            "delivery-semantics",
            "action publisher to transport outcome",
            "single-use stream positions and fail-safe priority",
            "transport error after a put may already have delivered",
            ["put completion is ambiguous"],
            "The sender retries the same bytes or resumes Active without a new fail-safe position.",
            "Every attempted put consumes its position; a new logical fail-safe uses a new position.",
            "Same-position retry and Active while fail-safe delivery is pending are rejected.",
            "A replay bypasses high-water checks or Active resumes after an unproved stop.",
            [
                "publisher position state",
                "fail-safe pending state",
                "transport outcome",
            ],
            ["single allocator", "no busy retry", "new-position recovery"],
            "Block Active until a new fail-safe publishes successfully or declaration state is replaced.",
            ["CF-09", "CF-06"],
            ["NCP-REQ-005", "NCP-REQ-010"],
            ["ncp-zenoh/src/lib.rs", "ncp-core/src/transport.rs"],
            ["ncp-zenoh/tests/loopback.rs", "ncp-core/tests/behavior_conformance.rs"],
            ["cargo test -p ncp-zenoh --locked"],
            ["README.md", "SECURITY.md", receipt],
            "LOCAL_VERIFIED_WITH_EXTERNAL_GAP",
            "Fault injection against real routers and plants remains NOT RUN.",
            True,
        ),
        _threat(
            15,
            "Unicode, duplicate keys, or path tricks create cross-language ambiguity",
            "parser-differential",
            "raw bytes to semantic object, route, or file path",
            "one bounded interpretation across implementations",
            "odd-but-valid-looking JSON, Unicode, endpoint, or filesystem input",
            [
                "different runtimes would otherwise normalize or collapse input differently"
            ],
            "A duplicate, lone surrogate, unsafe integer, control character, or aliased path reaches semantics inconsistently.",
            "Canonical bounded input has one decoded key set, safe numbers, valid Unicode, and canonical paths.",
            "Duplicate/ambiguous/unsafe input is rejected before generic allocation, schema use, or file access.",
            "Peers disagree on identity, digest, route, or authority while accepting the same bytes.",
            [
                "NCP-LIMIT reason",
                "cross-language behavior corpus",
                "path no-follow checks",
            ],
            [
                "raw scanner",
                "canonical key grammar",
                "bounded no-follow file validation",
            ],
            "Reject the complete input; do not normalize it into an accepted identity.",
            ["CF-10", "CF-01"],
            ["NCP-REQ-002", "NCP-REQ-013"],
            [
                "ncp-core/src/bounded_json.rs",
                "ncp-ts/src/bounded-json.ts",
                "e2e/bounded_json.py",
            ],
            [
                "e2e/test_bounded_json.py",
                "ncp-cpp/tests/corpus.rs",
                "ncp-ts/scripts/check-behavior.mjs",
            ],
            [
                "python3 -m unittest -v e2e.test_bounded_json",
                "cd ncp-ts && bun run check:behavior",
                "cargo test -p ncp-cpp --locked",
            ],
            ["contract/limits.v1.json", "conformance/manifest.v1.json", receipt],
            "LOCAL_VERIFIED_WITH_EXTERNAL_GAP",
            "Duration fuzzing, sanitizers, and independent installed-peer differential evidence are NOT RUN.",
            True,
        ),
        _threat(
            16,
            "Package namespace or dependency provenance is misattributed",
            "supply-chain",
            "source and package identity to public registry artifact",
            "authentic package installation and provenance",
            "unrelated registry owner, typosquat, compromised dependency, or unsigned archive",
            ["local package archives build successfully"],
            "Local packageability or a not-found registry response is treated as ownership or provenance.",
            "Exact intended namespaces, artifacts, checksums, SBOM, signatures, and provenance are independently verified.",
            "Unowned names, unsigned artifacts, unresolved advisories, and missing provenance remain failed release gates.",
            "Users install unrelated or unreviewed code under an expected NCP name.",
            [
                "registry ownership receipt",
                "artifact digest and signature verification",
                "dependency policy",
            ],
            [
                "publication hold",
                "coordinated rename requirement",
                "signed provenance gate",
            ],
            "Do not publish; resolve ownership or rename every manifest, test, document, and consumer coherently.",
            ["CF-07", "CF-04"],
            [],
            [
                "scripts/check_rust_packages.py",
                "scripts/check_dependency_exposure.py",
                ".github/workflows/release.yml",
            ],
            ["scripts/check_rust_packages.py", "scripts/check_dependency_exposure.py"],
            ["python3 scripts/check_rust_packages.py --offline", "cargo deny check"],
            ["KNOWN_LIMITATIONS.md", "RELEASE_READINESS.md", receipt],
            "NOT_RUN_EXTERNAL",
            "Registry control, final SBOM/provenance/signatures, and clean-room reproduction are absent.",
            True,
        ),
        _threat(
            17,
            "Candidate evidence is relabelled as release authorization",
            "governance",
            "local implementation evidence to public release claim",
            "truthful candidate and evidence tier",
            "version-only relabel, stale metadata, missing signature, or incomplete checklist",
            ["local and hosted tests pass"],
            "A green source-tree gate is described as a published, certified, or signed release.",
            "Local evidence remains bound to the candidate cut and explicit unresolved gates.",
            "A release tag or stable publication is blocked while any required evidence is missing, skipped, stale, or unsigned.",
            "Public users rely on unsupported security, interoperability, performance, or safety claims.",
            ["release-gate checker", "candidate identity", "public metadata review"],
            ["release_allowed=false", "tag workflow hold", "NO_GO handoff ledger"],
            "Keep the candidate blocked and narrow or remove unsupported claims.",
            ["CF-04", "CF-05", "CF-09"],
            [],
            ["scripts/check_release_gates.py", ".github/workflows/release.yml"],
            ["scripts/check_release_gates.py", ".github/workflows/ci.yml"],
            ["python3 scripts/check_release_gates.py --self-test"],
            [
                "RELEASE_READINESS.md",
                "docs/handoff/max-effort-task-review.v2.json",
                receipt,
            ],
            "LOCAL_VERIFIED_RELEASE_HOLD",
            "Independent review, signatures, external gates, and publication receipts remain absent.",
            True,
        ),
        _threat(
            18,
            "Copied protocol files create a silent consumer fork",
            "ecosystem",
            "NCP candidate to downstream runtime and descriptor",
            "one explicit consumer migration with exact installed behavior",
            "partial repin, copied schema, or stale runtime implementation",
            ["a consumer changes a version string or vendored file"],
            "The consumer is called native 1.0 without updating runtime, descriptor, fixtures, transport, and evidence together.",
            "A consumer pins one immutable NCP cut and passes installed-artifact plus live-transport certification.",
            "Movable refs, copied files, mixed wire values, incomplete descriptors, and unqualified profiles remain uncertified.",
            "Cross-repository drift creates incompatible or unsafe ecosystem behavior.",
            [
                "consumer descriptor scan",
                "exact mirror revision",
                "installed/live certification report",
            ],
            ["immutable pins", "no silent fork policy", "six-consumer release gate"],
            "Reject the compatibility claim and retain explicit cross-repository prerequisites.",
            ["CF-08", "CF-04"],
            ["NCP-REQ-004"],
            ["scripts/consumer_pin_guard.py", "scripts/repin-ncp.sh"],
            ["scripts/test_consumer_pins.sh", "scripts/check-consumer-pins.sh"],
            ["scripts/test_consumer_pins.sh"],
            [
                "INTEGRATING.md",
                "RELEASE_READINESS.md",
                "docs/handoff/max-effort-audit-inputs.v2.json",
            ],
            "PARTIAL_LOCAL",
            "All six installed-artifact and live consumer certifications remain NOT RUN.",
            True,
        ),
    ]
    if [entry["id"] for entry in records] != [
        f"NCP-THREAT-{number:03d}" for number in range(1, 19)
    ]:
        raise AuditGenerationError(
            "threat identifiers must be exact ordered 001 through 018"
        )
    return records


def build_threat_register(candidate: str) -> dict[str, Any]:
    threats = threat_records()
    behavior_dimensions = [
        (
            "inputs",
            "Bounded canonical JSON, exact routes, profiles, packages, and immutable migration inputs.",
        ),
        (
            "validation",
            "Raw resource limits precede schema and semantic validation; unknown authorizing values fail closed.",
        ),
        (
            "state",
            "Session generations, stream high-water marks, authority terms, idempotency records, and safety latches are explicit.",
        ),
        (
            "transitions",
            "Lifecycle, authority, reset, reconnect, and fail-safe transitions are closed and non-reviving.",
        ),
        (
            "outputs",
            "Replies, receipts, frames, diagnostics, and audit events retain exact identity and scientific boundaries.",
        ),
        (
            "errors",
            "Registered codes classify failure; free text never grants success.",
        ),
        (
            "resources",
            "Envelope, queue, retry, task, and diagnostic budgets are finite before expensive work.",
        ),
        (
            "time",
            "UTC evidence is separated from local monotonic control deadlines; equality boundaries fail closed.",
        ),
        (
            "identity",
            "Payload claims require verified transport-principal, route, plane, and live-generation binding.",
        ),
        (
            "persistence",
            "Unknown mutation outcomes stay unknown; released baselines and evidence identities are immutable inputs.",
        ),
        (
            "concurrency",
            "Plane queues, callback ownership, cancellation, ambiguous delivery, and shutdown have explicit local behavior.",
        ),
        (
            "public_claims",
            "HEAD remains an unreleased candidate; security, safety, science, scale, consumers, and publication are not certified.",
        ),
    ]
    boundaries = [
        "untrusted bytes to bounded decoder",
        "decoded payload claim to verified transport principal",
        "transport route to live session and plane",
        "commander intent to body-owned final actuator authority",
        "simulation output to scientific or physical claim",
        "legacy wire and consumer repository to native 1.0",
        "source tree to installed package and public registry",
        "local evidence to release authorization",
    ]
    return {
        "schema": "ncp.audit-threat-register.v1",
        "normative": False,
        "candidate": candidate,
        "wire_version": WIRE_VERSION,
        "generated_by": GENERATOR,
        "claim_boundary": CLAIM_BOUNDARY,
        "task": "T004",
        "risk_status": "OPEN",
        "assumptions": [
            "Network attackers can read, inject, replay, reorder, delay, duplicate, or drop traffic.",
            "Credentialed peers can claim the wrong entity, role, plane, session, or authority.",
            "Processes, routers, and hosts can crash, restart, exhaust resources, or lose replies.",
            "The body host and physical safety system are outside NCP's certification boundary.",
            "Local source-tree tests cannot supply independent, live, duration, signed, or publication evidence.",
        ],
        "trust_boundaries": boundaries,
        "current_behavior_dimensions": [
            {"dimension": name, "current_behavior": behavior}
            for name, behavior in behavior_dimensions
        ],
        "mandatory_counterfactuals": [
            {"id": identifier, "scenario": scenario}
            for identifier, scenario in COUNTERFACTUALS.items()
        ],
        "counts": {
            "threats": len(threats),
            "open_risks": sum(entry["risk_status"] == "OPEN" for entry in threats),
            "release_blocking": sum(entry["release_blocking"] for entry in threats),
        },
        "threats": threats,
    }


NORMATIVE_TRACE: dict[str, dict[str, Any]] = {
    "NCP-REQ-001": {
        "code": ["ncp-core/src/messages.rs", "ncp-ts/src/client.ts"],
        "tests": [
            "ncp-core/tests/behavior_conformance.rs",
            "ncp-ts/scripts/check-behavior.mjs",
        ],
        "commands": [
            "cargo test -p ncp-core --locked",
            "cd ncp-ts && bun run check:behavior",
        ],
    },
    "NCP-REQ-002": {
        "code": [
            "ncp-core/src/bounded_json.rs",
            "ncp-ts/src/bounded-json.ts",
            "e2e/bounded_json.py",
        ],
        "tests": ["e2e/test_bounded_json.py", "ncp-core/tests/behavior_conformance.rs"],
        "commands": [
            "python3 -m unittest -v e2e.test_bounded_json",
            "cargo test -p ncp-core --locked",
        ],
    },
    "NCP-REQ-003": {
        "code": [
            "ncp-core/src/security.rs",
            "ncp-core/src/messages.rs",
            "ncp-zenoh/src/lib.rs",
        ],
        "tests": [
            "ncp-core/tests/behavior_conformance.rs",
            "scripts/validate_security_profile.py",
        ],
        "commands": [
            "cargo test -p ncp-core --locked",
            "python3 scripts/validate_security_profile.py --self-test",
        ],
    },
    "NCP-REQ-004": {
        "code": ["ncp-core/src/migration.rs", "ncp-gateway/src/main.rs"],
        "tests": [
            "ncp-core/tests/behavior_conformance.rs",
            "conformance/migration/v0.8-to-v1.0/channel-requirement.json",
        ],
        "commands": ["cargo test -p ncp-core --locked"],
    },
    "NCP-REQ-005": {
        "code": [
            "ncp-core/src/stream_fence.rs",
            "ncp-core/src/transport.rs",
            "ncp-zenoh/src/lib.rs",
        ],
        "tests": [
            "ncp-zenoh/tests/cross_session_rpc.rs",
            "ncp-core/tests/behavior_conformance.rs",
        ],
        "commands": [
            "cargo test -p ncp-zenoh --locked",
            "cargo test -p ncp-core --locked",
        ],
    },
    "NCP-REQ-006": {
        "code": [
            "ncp-core/src/authority.rs",
            "ncp-core/src/messages.rs",
            "ncp-core/src/safety.rs",
        ],
        "tests": [
            "ncp-core/tests/behavior_conformance.rs",
            "ncp-zenoh/tests/safety_governor_over_wire.rs",
        ],
        "commands": [
            "cargo test -p ncp-core --locked",
            "cargo test -p ncp-zenoh --locked",
        ],
    },
    "NCP-REQ-007": {
        "code": [
            "ncp-core/src/idempotency.rs",
            "ncp-core/src/request_digest.rs",
            "ncp-core/src/messages.rs",
        ],
        "tests": [
            "ncp-core/tests/behavior_conformance.rs",
            "conformance/request-digest/v1.json",
        ],
        "commands": [
            "cargo test -p ncp-core --locked",
            "python3 scripts/check_request_digests.py",
        ],
    },
    "NCP-REQ-008": {
        "code": ["ncp-core/src/messages.rs", "contract/capabilities.v1.json"],
        "tests": [
            "ncp-core/tests/behavior_conformance.rs",
            "ncp-ts/scripts/check-behavior.mjs",
        ],
        "commands": [
            "cargo test -p ncp-core --locked",
            "cd ncp-ts && bun run check:behavior",
        ],
    },
    "NCP-REQ-009": {
        "code": ["ncp-core/src/messages.rs", "ncp-ts/src/client.ts"],
        "tests": ["ncp-core/tests/behavior_conformance.rs", "ncp-cpp/tests/corpus.rs"],
        "commands": [
            "cargo test -p ncp-core --locked",
            "cargo test -p ncp-cpp --locked",
        ],
    },
    "NCP-REQ-010": {
        "code": ["ncp-core/src/safety.rs", "ncp-ts/src/safety.ts"],
        "tests": [
            "ncp-core/tests/behavior_conformance.rs",
            "ncp-ts/scripts/check-behavior.mjs",
        ],
        "commands": [
            "cargo test -p ncp-core --locked",
            "cd ncp-ts && bun run check:behavior",
        ],
    },
    "NCP-REQ-011": {
        "code": ["ncp-core/src/plant.rs", "scripts/validate_security_profile.py"],
        "tests": [
            "ncp-core/tests/profile_digest_conformance.rs",
            "conformance/plant-profile/v1.json",
        ],
        "commands": [
            "cargo test -p ncp-core --locked",
            "python3 scripts/check_profile_digests.py",
        ],
    },
    "NCP-REQ-012": {
        "code": ["ncp-core/src/messages.rs", "contract/errors.v1.json"],
        "tests": [
            "ncp-core/tests/behavior_conformance.rs",
            "ncp-ts/scripts/check-behavior.mjs",
        ],
        "commands": [
            "cargo test -p ncp-core --locked",
            "cd ncp-ts && bun run check:behavior",
        ],
    },
    "NCP-REQ-013": {
        "code": [
            "ncp-core/src/messages.rs",
            "scripts/generate_conformance_manifest.py",
        ],
        "tests": ["ncp-core/tests/conformance.rs", "ncp-cpp/tests/corpus.rs"],
        "commands": [
            "python3 scripts/check_conformance_vectors.py",
            "cargo test -p ncp-core --locked",
        ],
    },
}


def _node(
    identifier: str,
    kind: str,
    requirement: str,
    source_refs: list[str],
    code_paths: list[str],
    test_paths: list[str],
    evidence_paths: list[str],
    commands: list[str],
    evidence_status: str,
    claim_tier: str,
    release_effect: str,
    threat_ids: list[str] | None = None,
    vector_ids: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": identifier,
        "kind": kind,
        "requirement": requirement,
        "source_refs": source_refs,
        "code_paths": code_paths,
        "test_paths": test_paths,
        "evidence_paths": evidence_paths,
        "verification_commands": commands,
        "evidence_status": evidence_status,
        "claim_tier": claim_tier,
        "release_effect": release_effect,
        "threat_ids": threat_ids or [],
        "vector_ids": vector_ids or [],
    }


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").upper()
    if not slug:
        raise AuditGenerationError(f"cannot form a stable ID from {value!r}")
    return slug


def normative_nodes(
    conformance: dict[str, Any], threats: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    requirements = conformance.get("normative_requirements")
    if not isinstance(requirements, list):
        raise AuditGenerationError(
            "conformance manifest has no normative_requirements array"
        )
    linked: dict[str, list[str]] = {}
    for threat in threats:
        for requirement_id in threat["requirement_ids"]:
            linked.setdefault(requirement_id, []).append(threat["id"])
    identifiers = [item.get("id") for item in requirements if isinstance(item, dict)]
    if set(identifiers) != set(NORMATIVE_TRACE):
        raise AuditGenerationError(
            "normative trace mapping differs from conformance requirement IDs"
        )
    nodes: list[dict[str, Any]] = []
    for item in requirements:
        identifier = item["id"]
        mapping = NORMATIVE_TRACE[identifier]
        status = (
            "PARTIAL_LOCAL"
            if identifier
            in {"NCP-REQ-003", "NCP-REQ-004", "NCP-REQ-005", "NCP-REQ-007"}
            else "LOCAL_VERIFIED"
        )
        nodes.append(
            _node(
                identifier,
                "normative-requirement",
                item["requirement"],
                [item["source"]],
                mapping["code"],
                mapping["tests"],
                ["conformance/manifest.v1.json", "docs/1.0-candidate-receipts.md"],
                mapping["commands"],
                status,
                "local-source-bound-evidence",
                "release-blocking-open" if status == "PARTIAL_LOCAL" else "local-guard",
                sorted(linked.get(identifier, [])),
                item["vector_ids"],
            )
        )
    return nodes


def release_gate_nodes(
    release_gates: dict[str, Any], threats: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    mappings: dict[str, tuple[list[str], list[str], list[str]]] = {
        "normative-contract": (
            ["scripts/generate_contract_manifest.py"],
            ["scripts/generate_contract_manifest.py"],
            ["python3 scripts/generate_contract_manifest.py --self-test"],
        ),
        "zero-skip-conformance": (
            ["scripts/generate_conformance_manifest.py"],
            [
                "ncp-core/tests/behavior_conformance.rs",
                "scripts/check_behavior_vectors.py",
            ],
            ["python3 scripts/generate_conformance_manifest.py"],
        ),
        "live-mtls-acl-rotation-revocation": (
            ["ncp-zenoh/src/lib.rs", "scripts/verify_acl_deployment.py"],
            [
                "scripts/verify_acl_deployment.py",
                "scripts/validate_security_profile.py",
            ],
            ["python3 scripts/verify_acl_deployment.py --self-test"],
        ),
        "two-independent-non-rust-live-peers": (
            ["ncp-ts/src/client.ts", "e2e/run_cross_language_e2e.py"],
            ["ncp-ts/scripts/check-behavior.mjs", "e2e/test_runner_status.py"],
            ["cd ncp-ts && bun run check:behavior"],
        ),
        "fault-backpressure-restart-soak": (
            ["ncp-core/src/resilience.rs", "ncp-zenoh/src/lib.rs"],
            ["ncp-zenoh/tests/loopback.rs", "ncp-zenoh/tests/cross_session_rpc.rs"],
            ["cargo test -p ncp-zenoh --locked"],
        ),
        "fuzz-sanitizer-duration": (
            ["ncp-core/src/bounded_json.rs", "ncp-ts/src/bounded-json.ts"],
            ["e2e/test_bounded_json.py", "ncp-core/tests/behavior_conformance.rs"],
            ["python3 -m unittest -v e2e.test_bounded_json"],
        ),
        "performance-resource-profile": (
            ["scripts/bench_realtime.py", "scripts/plot_perf.py"],
            ["scripts/plot_perf.py"],
            ["python3 scripts/plot_perf.py --self-test --check"],
        ),
        "installed-package-matrix": (
            ["scripts/check_rust_packages.py", "ncp-ts/scripts/check-package.mjs"],
            ["ncp-python/tests/test_smoke.py", "ncp-cpp/tests/corpus.rs"],
            [
                "python3 scripts/check_rust_packages.py --offline",
                "cd ncp-ts && bun run check:package",
            ],
        ),
        "registry-namespace-ownership": (
            ["Cargo.toml", "ncp-python/pyproject.toml", "ncp-ts/package.json"],
            ["scripts/check_rust_packages.py"],
            ["python3 scripts/check_rust_packages.py --offline"],
        ),
        "consumer-certification": (
            ["scripts/consumer_pin_guard.py", "scripts/repin-ncp.sh"],
            ["scripts/test_consumer_pins.sh"],
            ["scripts/test_consumer_pins.sh"],
        ),
        "independent-clean-room-reproduction": (
            ["scripts/check.sh", ".github/workflows/ci.yml"],
            ["scripts/check.sh"],
            ["scripts/check.sh"],
        ),
        "signed-sbom-provenance": (
            [".github/workflows/release.yml", "deny.toml"],
            ["scripts/check_dependency_exposure.py"],
            ["cargo deny check"],
        ),
        "post-publication-install-smoke": (
            [".github/workflows/release.yml", "scripts/check_rust_packages.py"],
            ["ncp-python/tests/test_smoke.py", "ncp-ts/scripts/check-package.mjs"],
            ["python3 scripts/check_rust_packages.py --offline"],
        ),
        "post-publication-emergency-revocation-exercise": (
            [".github/workflows/release.yml", "scripts/verify_acl_deployment.py"],
            ["scripts/verify_acl_deployment.py"],
            ["python3 scripts/verify_acl_deployment.py --self-test"],
        ),
    }
    threat_links = {
        "live-mtls-acl-rotation-revocation": [
            "NCP-THREAT-001",
            "NCP-THREAT-002",
            "NCP-THREAT-012",
        ],
        "fault-backpressure-restart-soak": [
            "NCP-THREAT-003",
            "NCP-THREAT-006",
            "NCP-THREAT-009",
            "NCP-THREAT-014",
        ],
        "fuzz-sanitizer-duration": ["NCP-THREAT-006", "NCP-THREAT-015"],
        "registry-namespace-ownership": ["NCP-THREAT-016"],
        "consumer-certification": ["NCP-THREAT-018"],
        "signed-sbom-provenance": [
            "NCP-THREAT-007",
            "NCP-THREAT-016",
            "NCP-THREAT-017",
        ],
    }
    del threats  # links are deliberately explicit and stable above
    nodes: list[dict[str, Any]] = []
    for phase, field in (
        ("pre", "pre_release_gates"),
        ("post", "post_release_validations"),
    ):
        entries = release_gates.get(field)
        if not isinstance(entries, list):
            raise AuditGenerationError(f"release gates have no {field} array")
        for index, entry in enumerate(entries):
            gate_id = entry["id"]
            if gate_id not in mappings:
                raise AuditGenerationError(
                    f"release gate {gate_id!r} has no trace mapping"
                )
            code, tests, commands = mappings[gate_id]
            if phase == "post":
                status = "NOT_RUN_POST_PUBLICATION"
                tier = "post-publication-evidence-required"
                effect = "post-publication-nonblocking"
            elif entry["local"]:
                status = "LOCAL_VERIFIED"
                tier = "local-source-bound-evidence"
                effect = "local-guard"
            else:
                status = "NOT_RUN_EXTERNAL"
                tier = "external-evidence-required"
                effect = "release-blocking-open"
            nodes.append(
                _node(
                    f"NCP-RELEASE-{phase.upper()}-{_slug(gate_id)}",
                    f"{phase}-release-gate",
                    f"Gate {gate_id} must retain exact evidence for the declared release phase.",
                    [f"contract/release-gates.v1.json#/{field}/{index}"],
                    code,
                    tests,
                    ["RELEASE_READINESS.md", "docs/1.0-candidate-receipts.md"],
                    commands,
                    status,
                    tier,
                    effect,
                    threat_links.get(gate_id, []),
                )
            )
    return nodes


def surface_nodes(surface: dict[str, Any]) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    status = surface.get("status")
    if not isinstance(status, str) or not status:
        raise AuditGenerationError("surface has no non-empty status")
    nodes.append(
        _node(
            f"NCP-SURFACE-STATUS-{_slug(status)}",
            "candidate-status-claim",
            f"The repository contract surface status is exactly {status!r}.",
            ["contract/surface.v1.json#/status"],
            ["contract/release-gates.v1.json", ".github/workflows/release.yml"],
            ["scripts/check_release_gates.py"],
            ["RELEASE_READINESS.md", "docs/1.0-candidate-receipts.md"],
            ["python3 scripts/check_release_gates.py --self-test"],
            "LOCAL_VERIFIED",
            "local-release-hold",
            "release-blocking-open",
        )
    )

    precedence = surface.get("normative_precedence")
    if not isinstance(precedence, list) or not precedence:
        raise AuditGenerationError("surface has no normative_precedence array")
    for index, member in enumerate(precedence):
        if not isinstance(member, str) or not member:
            raise AuditGenerationError(
                f"surface normative_precedence[{index}] must be a non-empty string"
            )
        nodes.append(
            _node(
                f"NCP-SURFACE-NORMATIVE-PRECEDENCE-{index + 1:02d}",
                "normative-precedence-claim",
                f"Normative precedence position {index + 1} is exactly {member!r}.",
                [f"contract/surface.v1.json#/normative_precedence/{index}"],
                ["scripts/generate_contract_manifest.py"],
                ["scripts/generate_contract_manifest.py"],
                ["contract/manifest.v1.json", "docs/1.0-scope.md"],
                ["python3 scripts/generate_contract_manifest.py --self-test"],
                "LOCAL_VERIFIED",
                "local-source-bound-evidence",
                "local-guard",
            )
        )

    message_tests = ["ncp-core/tests/conformance.rs", "conformance/manifest.v1.json"]
    for group in ("messages", "encodings", "transports"):
        values = surface.get(group)
        if not isinstance(values, dict):
            raise AuditGenerationError(f"surface has no {group} object")
        for state, members in values.items():
            if not isinstance(members, list):
                raise AuditGenerationError(f"surface {group}.{state} must be an array")
            for index, member in enumerate(members):
                identifier = (
                    f"NCP-SURFACE-{_slug(group)}-{_slug(state)}-{_slug(member)}"
                )
                source = [f"contract/surface.v1.json#/{group}/{state}/{index}"]
                if group == "messages":
                    code = (
                        ["ncp-core/src/bulk.rs"]
                        if member == "bulk_observation"
                        else ["ncp-core/src/messages.rs"]
                    )
                    tests = message_tests
                    commands = [
                        "python3 scripts/check_conformance_vectors.py",
                        "cargo test -p ncp-core --locked",
                    ]
                elif group == "encodings":
                    code = (
                        [
                            "ncp-core/src/bounded_json.rs",
                            "ncp-core/src/canonical_digest.rs",
                        ]
                        if member == "canonical-json"
                        else ["contract/surface.v1.json", "ncp-core/src/bulk.rs"]
                    )
                    tests = [
                        "ncp-core/tests/conformance.rs",
                        "scripts/check_conformance_vectors.py",
                    ]
                    commands = ["python3 scripts/check_conformance_vectors.py"]
                elif member == "zenoh":
                    code = ["ncp-zenoh/src/lib.rs"]
                    tests = ["ncp-zenoh/tests/loopback.rs"]
                    commands = ["cargo test -p ncp-zenoh --locked"]
                elif member == "websocket-json":
                    code = ["ncp-ts/src/ws.ts"]
                    tests = ["ncp-ts/scripts/check-ws.mjs"]
                    commands = ["cd ncp-ts && bun run check:ws"]
                else:
                    code = ["contract/surface.v1.json"]
                    tests = ["scripts/generate_contract_manifest.py"]
                    commands = ["python3 scripts/generate_contract_manifest.py"]
                status = "PARTIAL_LOCAL" if member == "zenoh" else "LOCAL_VERIFIED"
                tier = (
                    "local-implementation-with-external-security-gap"
                    if member == "zenoh"
                    else "local-source-bound-evidence"
                )
                effect = (
                    "release-blocking-open"
                    if member == "zenoh"
                    else ("narrowed-claim" if state != "stable-1.0" else "local-guard")
                )
                nodes.append(
                    _node(
                        identifier,
                        "surface-claim",
                        f"{group} member {member!r} is classified exactly as {state!r}.",
                        source,
                        code,
                        tests,
                        ["contract/surface.v1.json", "docs/1.0-scope.md"],
                        commands,
                        status,
                        tier,
                        effect,
                        ["NCP-THREAT-012"] if member == "zenoh" else [],
                    )
                )

    planes = surface.get("planes")
    if not isinstance(planes, list) or not planes:
        raise AuditGenerationError("surface has no planes array")
    for index, member in enumerate(planes):
        if not isinstance(member, str) or not member:
            raise AuditGenerationError(f"surface planes[{index}] must be non-empty")
        nodes.append(
            _node(
                f"NCP-SURFACE-PLANE-{_slug(member)}",
                "plane-claim",
                f"The stable wire contains the exact {member!r} plane.",
                [f"contract/surface.v1.json#/planes/{index}"],
                ["ncp-core/src/keys.rs", "ncp-core/src/messages.rs"],
                ["ncp-core/tests/behavior_conformance.rs"],
                ["conformance/manifest.v1.json", "docs/1.0-scope.md"],
                ["cargo test -p ncp-core --locked"],
                "LOCAL_VERIFIED",
                "local-source-bound-evidence",
                "local-guard",
            )
        )

    stateful_acceptance = surface.get("stateful_acceptance")
    stateful_mappings: dict[str, tuple[list[str], list[str]]] = {
        "authority_renewal": (
            ["ncp-core/src/authority.rs", "ncp-core/src/messages.rs"],
            ["ncp-core/tests/behavior_conformance.rs"],
        ),
        "estop_reset": (
            ["ncp-core/src/safety.rs", "ncp-core/src/messages.rs"],
            [
                "ncp-core/tests/behavior_conformance.rs",
                "ncp-zenoh/tests/safety_governor_over_wire.rs",
            ],
        ),
        "stream_declaration": (
            ["ncp-core/src/stream_fence.rs", "ncp-core/src/resilience.rs"],
            ["ncp-core/tests/behavior_conformance.rs"],
        ),
        "status_stream": (
            ["ncp-core/src/messages.rs", "ncp-core/src/resilience.rs"],
            ["ncp-core/tests/behavior_conformance.rs"],
        ),
    }
    if not isinstance(stateful_acceptance, dict) or set(stateful_acceptance) != set(
        stateful_mappings
    ):
        raise AuditGenerationError(
            "surface stateful_acceptance differs from the complete trace mapping"
        )
    for member, rule in stateful_acceptance.items():
        if not isinstance(rule, str) or not rule:
            raise AuditGenerationError(
                f"surface stateful_acceptance.{member} must be non-empty"
            )
        code, tests = stateful_mappings[member]
        nodes.append(
            _node(
                f"NCP-SURFACE-STATEFUL-{_slug(member)}",
                "stateful-acceptance-claim",
                f"Stateful acceptance for {member!r} is exactly {rule!r}.",
                [f"contract/surface.v1.json#/stateful_acceptance/{member}"],
                code,
                tests,
                ["conformance/manifest.v1.json", "NEURO_CYBERNETIC_PROTOCOL.md"],
                ["cargo test -p ncp-core --locked"],
                "LOCAL_VERIFIED",
                "local-source-bound-evidence",
                "local-guard",
            )
        )

    extensions = surface.get("extensions")
    extension_mappings: dict[str, tuple[list[str], list[str]]] = {
        "unknown_json_fields": (
            ["ncp-core/src/bounded_json.rs", "ncp-core/src/messages.rs"],
            ["e2e/test_bounded_json.py", "ncp-core/tests/behavior_conformance.rs"],
        ),
        "unknown_enum_values": (
            ["ncp-core/src/messages.rs"],
            ["ncp-core/tests/behavior_conformance.rs"],
        ),
        "unknown_capabilities": (
            ["ncp-core/src/messages.rs", "contract/capabilities.v1.json"],
            ["ncp-core/tests/behavior_conformance.rs"],
        ),
        "experimental_as_stable": (
            ["ncp-core/src/messages.rs", "contract/surface.v1.json"],
            ["ncp-core/tests/behavior_conformance.rs"],
        ),
    }
    if not isinstance(extensions, dict) or set(extensions) != set(extension_mappings):
        raise AuditGenerationError(
            "surface extensions differ from the complete trace mapping"
        )
    for member, rule in extensions.items():
        if not isinstance(rule, str) or not rule:
            raise AuditGenerationError(f"surface extensions.{member} must be non-empty")
        code, tests = extension_mappings[member]
        commands = ["cargo test -p ncp-core --locked"]
        if member == "unknown_json_fields":
            commands.insert(0, "python3 -m unittest -v e2e.test_bounded_json")
        nodes.append(
            _node(
                f"NCP-SURFACE-EXTENSION-{_slug(member)}",
                "extension-policy-claim",
                f"Extension policy for {member!r} is exactly {rule!r}.",
                [f"contract/surface.v1.json#/extensions/{member}"],
                code,
                tests,
                ["conformance/manifest.v1.json", "docs/1.0-scope.md"],
                commands,
                "LOCAL_VERIFIED",
                "local-source-bound-evidence",
                "local-guard",
            )
        )

    packages = surface.get("packages")
    if not isinstance(packages, dict):
        raise AuditGenerationError("surface has no packages object")
    package_paths = {
        "ncp-core": "ncp-core/Cargo.toml",
        "ncp-zenoh": "ncp-zenoh/Cargo.toml",
        "ncp-gateway": "ncp-gateway/Cargo.toml",
        "ncp-python": "ncp-python/pyproject.toml",
        "ncp-cpp": "ncp-cpp/Cargo.toml",
        "@sepahead/ncp": "ncp-ts/package.json",
    }
    for state, members in packages.items():
        if not isinstance(members, list):
            raise AuditGenerationError(f"surface packages.{state} must be an array")
        for index, member in enumerate(members):
            package_path = package_paths.get(member)
            if package_path is None:
                raise AuditGenerationError(
                    f"surface package {member!r} has no trace mapping"
                )
            nodes.append(
                _node(
                    f"NCP-SURFACE-PACKAGE-{_slug(state)}-{_slug(member)}",
                    "package-claim",
                    f"Package {member!r} is classified exactly in surface set {state!r}.",
                    [f"contract/surface.v1.json#/packages/{state}/{index}"],
                    [package_path],
                    [
                        "scripts/check_rust_packages.py"
                        if member != "@sepahead/ncp"
                        else "ncp-ts/scripts/check-package.mjs"
                    ],
                    ["docs/1.0-candidate-receipts.md", "RELEASE_READINESS.md"],
                    [
                        "python3 scripts/check_rust_packages.py --offline"
                        if member != "@sepahead/ncp"
                        else "cd ncp-ts && bun run check:package"
                    ],
                    "PARTIAL_LOCAL" if state == "candidate" else "LOCAL_VERIFIED",
                    "candidate-package-local-evidence"
                    if state == "candidate"
                    else "explicit-independence-non-claim",
                    "release-blocking-open"
                    if state == "candidate"
                    else "narrowed-claim",
                    ["NCP-THREAT-016"] if state == "candidate" else [],
                )
            )
    non_claims = surface.get("non_claims")
    if not isinstance(non_claims, list):
        raise AuditGenerationError("surface has no non_claims array")
    for index, member in enumerate(non_claims):
        code = (
            ["ncp-core/src/safety.rs"]
            if "safety" in member or "zero-safe" in member
            else ["ncp-core/src/messages.rs"]
        )
        nodes.append(
            _node(
                f"NCP-SURFACE-NONCLAIM-{_slug(member)}",
                "explicit-non-claim",
                f"The candidate does not claim {member!r}.",
                [f"contract/surface.v1.json#/non_claims/{index}"],
                code,
                ["ncp-core/tests/behavior_conformance.rs"],
                ["README.md", "KNOWN_LIMITATIONS.md"],
                ["cargo test -p ncp-core --locked"],
                "NOT_CLAIMED",
                "explicit-non-claim",
                "narrowed-claim",
                ["NCP-THREAT-010", "NCP-THREAT-011"]
                if member
                in {
                    "paper-reproduction",
                    "calibrated-posterior",
                    "physical-safety-certification",
                    "universal-zero-safe-action",
                }
                else [],
            )
        )
    return nodes


def threat_requirement_nodes(threats: list[dict[str, Any]]) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    for index, threat in enumerate(threats):
        status = (
            "NOT_RUN_EXTERNAL"
            if threat["control_status"] == "NOT_RUN_EXTERNAL"
            else (
                "PARTIAL_LOCAL"
                if threat["control_status"]
                in {
                    "PARTIAL_LOCAL",
                    "LOCAL_PREREQUISITES_ONLY",
                    "LOCAL_VERIFIED_WITH_EXTERNAL_GAP",
                }
                else "LOCAL_VERIFIED"
            )
        )
        claim_tier = (
            "explicit-non-claim"
            if threat["control_status"] == "LOCAL_VERIFIED_NON_CLAIM"
            else (
                "external-evidence-required"
                if status == "NOT_RUN_EXTERNAL"
                else "local-control-with-open-risk"
            )
        )
        nodes.append(
            _node(
                threat["control_requirement_id"],
                "threat-control",
                f"Prevent or fail closed for {threat['title'].lower()} as specified by {threat['id']}.",
                [f"evidence/audit/threat-register.v1.json#/threats/{index}"],
                threat["code_paths"],
                threat["test_paths"],
                threat["evidence_paths"],
                threat["verification_commands"],
                status,
                claim_tier,
                "release-blocking-open"
                if threat["release_blocking"]
                else "narrowed-claim",
                [threat["id"]],
            )
        )
    return nodes


def _edges(requirements: list[dict[str, Any]]) -> list[dict[str, str]]:
    edges: list[dict[str, str]] = []
    relations = (
        ("code_paths", "implemented-by"),
        ("test_paths", "verified-by"),
        ("evidence_paths", "evidenced-by"),
        ("threat_ids", "mitigates"),
    )
    for requirement in requirements:
        for field, relation in relations:
            for target in requirement[field]:
                edges.append(
                    {"from": requirement["id"], "relation": relation, "to": target}
                )
    return sorted(edges, key=lambda edge: (edge["from"], edge["relation"], edge["to"]))


def build_traceability(
    candidate: str, threat_register: dict[str, Any]
) -> dict[str, Any]:
    conformance = load_json(CONFORMANCE)
    surface = load_json(SURFACE)
    release_gates = load_json(RELEASE_GATES)
    threats = threat_register["threats"]
    source_sets = {
        "normative_requirements": normative_nodes(conformance, threats),
        "release_gates": release_gate_nodes(release_gates, threats),
        "surface_claims": surface_nodes(surface),
        "threat_controls": threat_requirement_nodes(threats),
    }
    requirements = sorted(
        [node for nodes in source_sets.values() for node in nodes],
        key=lambda node: node["id"],
    )
    identifiers = [node["id"] for node in requirements]
    if len(identifiers) != len(set(identifiers)):
        raise AuditGenerationError(
            "traceability graph contains duplicate requirement IDs"
        )
    edges = _edges(requirements)
    status_counts = Counter(node["evidence_status"] for node in requirements)
    return {
        "schema": "ncp.requirement-traceability.v1",
        "normative": False,
        "candidate": candidate,
        "wire_version": WIRE_VERSION,
        "generated_by": GENERATOR,
        "claim_boundary": CLAIM_BOUNDARY,
        "task": "T008",
        "coverage_policy": (
            "The exact union of conformance normative requirements, phased release gates, "
            "surface/package/non-claim entries, and threat-control requirements must appear "
            "once. Every node retains code, test, evidence, command, claim-tier, and status links."
        ),
        "source_set_counts": {name: len(nodes) for name, nodes in source_sets.items()},
        "counts": {
            "requirements": len(requirements),
            "edges": len(edges),
            "by_evidence_status": dict(sorted(status_counts.items())),
        },
        "requirements": requirements,
        "edges": edges,
    }


def repository_paths() -> list[str]:
    try:
        output = subprocess.check_output(
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            cwd=ROOT,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise AuditGenerationError(
            f"cannot enumerate repository files: {error}"
        ) from error
    paths = {value.decode("utf-8") for value in output.split(b"\0") if value}
    paths.update(
        {
            GENERATOR,
            CHECKER,
            relative(README),
            relative(THREAT_REGISTER),
            relative(LATENT_INVENTORY),
            relative(TRACEABILITY),
            relative(MANIFEST),
        }
    )
    return sorted(paths)


def indexed_paths() -> set[str]:
    try:
        output = subprocess.check_output(
            ["git", "ls-files", "-z", "--cached"], cwd=ROOT
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise AuditGenerationError(
            f"cannot enumerate indexed files: {error}"
        ) from error
    return {value.decode("utf-8") for value in output.split(b"\0") if value}


def git_object_format() -> str:
    try:
        value = subprocess.check_output(
            ["git", "rev-parse", "--show-object-format"], cwd=ROOT, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError) as error:
        raise AuditGenerationError(
            f"cannot determine Git object format: {error}"
        ) from error
    if value not in {"sha1", "sha256"}:
        raise AuditGenerationError(f"unsupported Git object format {value!r}")
    return value


def git_blob_oid(content: bytes, object_format: str) -> str:
    framed = f"blob {len(content)}\0".encode("ascii") + content
    return hashlib.new(object_format, framed).hexdigest()


def _file_identity(
    path: str, content: bytes, indexed: set[str], object_format: str
) -> dict[str, Any]:
    return {
        "path": path,
        "bytes": len(content),
        "sha256": sha256_bytes(content),
        "git_blob_oid": git_blob_oid(content, object_format),
        "indexed": path in indexed,
    }


def _classification(path: str, token_id: str, line: str) -> tuple[str, str, list[str]]:
    lower = line.casefold()
    audit_paths = {
        GENERATOR,
        CHECKER,
        relative(README),
        relative(THREAT_REGISTER),
        relative(TRACEABILITY),
        relative(MANIFEST),
    }
    if path in audit_paths:
        return "AUDIT_CONTROL_TEXT", "NON_RUNTIME_AUDIT", [relative(README)]
    if (
        path.startswith("evidence/supply-chain/")
        or path == "scripts/generate_supply_chain_evidence.py"
    ):
        return (
            "RETAINED_EVIDENCE_CONTROL",
            "NON_RUNTIME_AUDIT",
            ["RELEASE_READINESS.md"],
        )
    if path.startswith("docs/handoff/"):
        return (
            "HANDOFF_OPEN_EVIDENCE",
            "NO_RELEASE_AUTHORIZATION",
            ["docs/handoff/README.md"],
        )
    if path.startswith(
        (
            "ncp-core/testdata/",
            "ncp-cpp/testdata/",
            "ncp-zenoh/testdata/",
            "ncp-ts/dist/",
        )
    ):
        return (
            "GENERATED_MIRROR",
            "SOURCE_GUARDED_ELSEWHERE",
            [
                "scripts/sync_rust_package_testdata.py",
                "ncp-ts/scripts/sync-bindings.mjs",
            ],
        )
    if path in {
        "CHANGELOG.md",
        "PERFORMANCE.md",
        "scripts/plot_perf.py",
    } or path.startswith(("docs/0.8", "docs/plots/", "docs/wire-0.8-")):
        return "HISTORICAL_OR_INFORMATIVE", "NOT_CURRENT_RELEASE_EVIDENCE", [path]
    if token_id in {"M001", "M002", "M003", "M004", "M005", "M006"}:
        return (
            "UNREVIEWED_ACTION_PATH",
            "BLOCKS_LOCAL_CLOSURE",
            ["KNOWN_LIMITATIONS.md"],
        )
    if token_id == "M007":
        return (
            "EXPLICIT_SCOPE_QUARANTINE",
            "NOT_STABLE_BY_IMPLICATION",
            ["contract/surface.v1.json", "docs/1.0-scope.md"],
        )
    if token_id == "M008":
        if path == "ncp-zenoh/src/lib.rs":
            return (
                "FAIL_SAFE_NON_WIDENING",
                "LOCAL_SAFETY_GUARD",
                ["ncp-zenoh/src/lib.rs", "SECURITY.md"],
            )
        if path == "ncp-core/src/keys.rs":
            return (
                "NEUTRAL_ROUTING_DEFAULT",
                "NO_IDENTITY_OR_AUTHORITY",
                ["ncp-core/src/keys.rs", "NEURO_CYBERNETIC_PROTOCOL.md"],
            )
        if path == "ncp-core/src/messages.rs":
            return (
                "BOUNDED_DIAGNOSTIC_ONLY",
                "NO_SEMANTIC_REPARSE",
                ["ncp-core/src/messages.rs", "contract/errors.v1.json"],
            )
        if path == "ncp-ts/src/canonical-json.ts":
            return (
                "VALIDATED_CANONICAL_DEFAULT",
                "NO_VALIDATION_OR_AUTHORITY_BYPASS",
                ["ncp-ts/src/canonical-json.ts", "ncp-ts/scripts/check-behavior.mjs"],
            )
        negative = (
            "no " in lower
            or "not " in lower
            or "never" in lower
            or "without" in lower
            or "cannot" in lower
            or "must not" in lower
            or "removed" in lower
        )
        if negative:
            return "NEGATIVE_POLICY_GUARD", "FAIL_CLOSED_REQUIREMENT", [path]
        if path in {"RATIONALE.md", "INTEGRATING.md"}:
            return "REVIEWED_DESIGN_EXPLANATION", "NO_AUTHORITY_WIDENING", [path]
    return "UNREVIEWED_ACTION_PATH", "BLOCKS_LOCAL_CLOSURE", ["KNOWN_LIMITATIONS.md"]


def _scan_content(path: str, content: bytes) -> tuple[list[dict[str, Any]], bool]:
    if b"\0" in content:
        return [], False
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return [], False
    file_hash = sha256_bytes(content)
    findings: list[dict[str, Any]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        for match in TOKEN_PATTERN.finditer(line):
            token_id = TOKEN_ID[match.group(0).casefold()]
            disposition, claim_effect, evidence_paths = _classification(
                path, token_id, line
            )
            line_hash = sha256_bytes(line.encode("utf-8"))
            occurrence_key = (
                f"{path}\0{line_number}\0{match.start() + 1}\0{token_id}\0{line_hash}"
            )
            findings.append(
                {
                    "id": "NCP-LATENT-"
                    + sha256_bytes(occurrence_key.encode("utf-8"))[:20].upper(),
                    "path": path,
                    "line": line_number,
                    "column": match.start() + 1,
                    "token_id": token_id,
                    "line_sha256": line_hash,
                    "file_sha256": file_hash,
                    "disposition": disposition,
                    "claim_effect": claim_effect,
                    "evidence_paths": evidence_paths,
                }
            )
    return findings, True


def build_latent_inventory(
    candidate: str, virtual_files: dict[str, bytes]
) -> dict[str, Any]:
    output_paths = {relative(LATENT_INVENTORY), relative(MANIFEST)}
    findings: list[dict[str, Any]] = []
    indexed = indexed_paths()
    object_format = git_object_format()
    text_files: list[dict[str, Any]] = []
    non_text_files: list[dict[str, Any]] = []
    scanned_paths: list[str] = []
    for path in repository_paths():
        if path in output_paths:
            continue
        content = virtual_files.get(path)
        if content is None:
            target = ROOT / path
            if not target.is_file():
                continue
            content = target.read_bytes()
        current, is_text = _scan_content(path, content)
        identity = _file_identity(path, content, indexed, object_format)
        if is_text:
            text_files.append(identity)
            scanned_paths.append(path)
            findings.extend(current)
        else:
            identity["reason"] = "NUL_BYTE" if b"\0" in content else "NON_UTF8"
            non_text_files.append(identity)
    findings.sort(
        key=lambda item: (item["path"], item["line"], item["column"], item["token_id"])
    )
    identifiers = [item["id"] for item in findings]
    if len(identifiers) != len(set(identifiers)):
        raise AuditGenerationError("latent inventory contains duplicate occurrence IDs")
    dispositions = Counter(item["disposition"] for item in findings)
    token_counts = Counter(item["token_id"] for item in findings)
    path_digest = sha256_bytes(canonical_bytes(scanned_paths))
    inventory = {
        "schema": "ncp.latent-path-inventory.v1",
        "normative": False,
        "candidate": candidate,
        "wire_version": WIRE_VERSION,
        "generated_by": GENERATOR,
        "claim_boundary": CLAIM_BOUNDARY,
        "task": "T006",
        "scan_policy": {
            "scope": "Git-indexed and non-ignored untracked UTF-8 worktree files",
            "case_sensitive": False,
            "word_bounded": True,
            "token_catalog": {
                identifier: {
                    "lexeme_sha256": sha256_bytes(value.casefold().encode("utf-8"))
                }
                for identifier, value in TOKEN_CATALOG.items()
            },
            "self_reference": "The two generated outputs excluded during construction are separately asserted to contain zero configured token matches.",
        },
        "file_inventory": {
            "git_object_format": object_format,
            "text_files": text_files,
            "non_text_files": non_text_files,
        },
        "counts": {
            "text_files": len(text_files),
            "binary_or_non_utf8_files": len(non_text_files),
            "occurrences": len(findings),
            "by_token_id": dict(sorted(token_counts.items())),
            "by_disposition": dict(sorted(dispositions.items())),
        },
        "scanned_path_set_sha256": path_digest,
        "occurrences": findings,
    }
    inventory_bytes = json_bytes(inventory)
    own_findings, own_is_text = _scan_content(
        relative(LATENT_INVENTORY), inventory_bytes
    )
    if not own_is_text or own_findings:
        raise AuditGenerationError(
            "latent inventory output must be UTF-8 and token-free"
        )
    return inventory


def build_manifest(candidate: str, artifacts: dict[str, bytes]) -> dict[str, Any]:
    source_inputs = [
        SURFACE,
        RELEASE_GATES,
        CONFORMANCE,
        CONTRACT_MANIFEST,
        ROOT / "Cargo.lock",
        ROOT / "bun.lock",
        ROOT / "evidence" / "supply-chain" / "vulnerability-report.v1.json",
    ]
    counts: dict[str, int] = {}
    for path, content in artifacts.items():
        value = json.loads(content, object_pairs_hook=_object_no_duplicates)
        if path == relative(THREAT_REGISTER):
            counts[path] = value["counts"]["threats"]
        elif path == relative(LATENT_INVENTORY):
            counts[path] = value["counts"]["occurrences"]
        else:
            counts[path] = value["counts"]["requirements"]
    return {
        "schema": "ncp.audit-evidence-manifest.v1",
        "normative": False,
        "candidate": candidate,
        "wire_version": WIRE_VERSION,
        "generated_by": GENERATOR,
        "claim_boundary": CLAIM_BOUNDARY,
        "artifacts": [
            {
                "path": path,
                "sha256": sha256_bytes(content),
                "bytes": len(content),
                "records": counts[path],
            }
            for path, content in sorted(artifacts.items())
        ],
        "source_inputs": [
            {
                "path": relative(path),
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
            }
            for path in source_inputs
        ],
        "generation_policy": "Rebuild from current repository inputs; byte drift or an unclassified latent path fails the local gate.",
    }


def build_artifacts() -> dict[str, bytes]:
    candidate = package_version()
    threat = build_threat_register(candidate)
    trace = build_traceability(candidate, threat)
    virtual_files = {
        relative(THREAT_REGISTER): json_bytes(threat),
        relative(TRACEABILITY): json_bytes(trace),
    }
    latent = build_latent_inventory(candidate, virtual_files)
    core = {
        relative(THREAT_REGISTER): virtual_files[relative(THREAT_REGISTER)],
        relative(LATENT_INVENTORY): json_bytes(latent),
        relative(TRACEABILITY): virtual_files[relative(TRACEABILITY)],
    }
    manifest = build_manifest(candidate, core)
    manifest_bytes = json_bytes(manifest)
    own_findings, own_is_text = _scan_content(relative(MANIFEST), manifest_bytes)
    if not own_is_text or own_findings:
        raise AuditGenerationError("audit manifest output must be UTF-8 and token-free")
    return {**core, relative(MANIFEST): manifest_bytes}


def self_test() -> None:
    first = build_threat_register("1.0.0-rc.1")
    second = build_threat_register("1.0.0-rc.1")
    if json_bytes(first) != json_bytes(second):
        raise AssertionError("threat register generation is not deterministic")
    coverage = {
        counterfactual
        for threat in first["threats"]
        for counterfactual in threat["counterfactual_ids"]
    }
    if coverage != set(COUNTERFACTUALS):
        raise AssertionError(
            "threat register does not cover every mandatory counterfactual"
        )
    hostile, is_text = _scan_content("hostile.rs", b"// TODO: permissive fallback\n")
    if not is_text or len(hostile) != 2:
        raise AssertionError("latent scanner missed a hostile multi-token line")
    if any(item["disposition"] != "UNREVIEWED_ACTION_PATH" for item in hostile):
        raise AssertionError("unknown hostile markers did not remain unreviewed")
    if _scan_content("binary.bin", b"TODO\0fallback")[1]:
        raise AssertionError("binary input was treated as tracked text")


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--write", action="store_true", help="replace the generated audit artifacts"
    )
    mode.add_argument(
        "--check",
        action="store_true",
        help="check generated audit artifacts without changing them (the default)",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="also run deterministic hostile scanner tests",
    )
    args = parser.parse_args()
    try:
        if args.self_test:
            self_test()
        artifacts = build_artifacts()
        if args.write:
            AUDIT_DIR.mkdir(parents=True, exist_ok=True)
            for path, content in artifacts.items():
                target = ROOT / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
                print(f"WROTE {path}")
            return 0
        stale: list[str] = []
        for path, expected in artifacts.items():
            target = ROOT / path
            if not target.is_file() or target.read_bytes() != expected:
                stale.append(path)
        if stale:
            print(
                "ERROR: audit artifacts are missing or stale: "
                + ", ".join(stale)
                + "; run scripts/generate_audit_artifacts.py --write and review",
                file=sys.stderr,
            )
            return 1
        threat = json.loads(artifacts[relative(THREAT_REGISTER)])
        latent = json.loads(artifacts[relative(LATENT_INVENTORY)])
        trace = json.loads(artifacts[relative(TRACEABILITY)])
        print(
            "OK audit artifacts: "
            f"{threat['counts']['threats']} threats, "
            f"{latent['counts']['occurrences']} latent-path occurrences, "
            f"{trace['counts']['requirements']} traced requirements"
        )
        return 0
    except AuditGenerationError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
