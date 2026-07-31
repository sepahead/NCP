#!/usr/bin/env python3
"""Assemble one exact-source B01 preliminary architecture-evidence result."""

# The bounded support import must install its exact snapshot before probe imports.
# ruff: noqa: I001

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bounded_json_support import (
    BOUNDED_JSON_SUPPORT_PATHS,
    BoundedJsonError,
    JsonLimits,
    parse_json_bytes,
)
import decision_probe
import freshness_acceptance_probe
import model_check
import observer_authorization_probe
import observer_capture_probe
import resource_probe
import run_smt
import source_issuance_index_probe
from source_inventory import (
    SourceInventoryError,
    build_source_inventory,
    read_bounded_relative_file,
)

ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
MAX_CONTRACT_MANIFEST_BYTES = 65_536
MAX_ASSEMBLED_RESULT_BYTES = 2_000_000
CONTRACT_MANIFEST_JSON_LIMITS = JsonLimits(
    maximum_bytes=MAX_CONTRACT_MANIFEST_BYTES,
    maximum_depth=24,
    maximum_items=4_096,
    maximum_object_members=256,
    maximum_array_items=2_048,
    maximum_key_utf8_bytes=256,
    maximum_string_utf8_bytes=16_384,
    maximum_total_string_utf8_bytes=MAX_CONTRACT_MANIFEST_BYTES,
    maximum_integer_chars=32,
    maximum_float_chars=64,
    allow_floats=False,
)
EXPECTED_CONTRACT_SHA256 = (
    "9cae331742d01e9b164e029aa06c644e6b1886176d0816a6ef883af138355c90"
)


class AssemblyError(RuntimeError):
    """One source-enumeration, Git-binding, or result-assembly failure."""


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _git(*arguments: str) -> str:
    git = shutil.which("git")
    if git is None:
        raise AssemblyError("git is unavailable")
    completed = subprocess.run(  # noqa: S603
        [git, *arguments],
        cwd=REPOSITORY,
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if completed.stderr:
        raise AssemblyError(f"git {' '.join(arguments)} emitted stderr")
    return completed.stdout.strip()


def _sources() -> list[dict[str, Any]]:
    try:
        return build_source_inventory(
            ROOT,
            REPOSITORY,
            support_relative_paths=BOUNDED_JSON_SUPPORT_PATHS,
        )
    except (OSError, SourceInventoryError) as error:
        raise AssemblyError(f"source inventory failed closed: {error}") from error


def build_result() -> dict[str, Any]:
    source_commit = _git("rev-parse", "HEAD")
    source_tree = _git("rev-parse", "HEAD^{tree}")
    source_status = _git("status", "--short", "--", str(ROOT.relative_to(REPOSITORY)))
    repository_status = _git("status", "--short")
    try:
        manifest_bytes = read_bounded_relative_file(
            REPOSITORY,
            "contract/manifest.v1.json",
            maximum_bytes=MAX_CONTRACT_MANIFEST_BYTES,
            label="contract manifest",
        )
    except (OSError, SourceInventoryError) as error:
        raise AssemblyError(f"contract manifest snapshot failed: {error}") from error
    try:
        manifest = parse_json_bytes(
            manifest_bytes,
            limits=CONTRACT_MANIFEST_JSON_LIMITS,
            label="contract manifest",
        )
    except BoundedJsonError as error:
        raise AssemblyError(f"contract manifest JSON is invalid: {error}") from error
    if type(manifest) is not dict:
        raise AssemblyError("contract manifest root is not an exact object")
    if manifest.get("contract_digest_sha256") != EXPECTED_CONTRACT_SHA256:
        raise AssemblyError("current contract manifest digest changed")
    sources = _sources()
    decision_result = decision_probe.build_result()
    authorization_result = observer_authorization_probe.build_result()
    capture_result = observer_capture_probe.build_result()
    freshness_result = freshness_acceptance_probe.build_result()
    source_index_result = source_issuance_index_probe.build_result()
    model_result = model_check.build_result()
    smt_result = run_smt.build_result()
    resource_result = resource_probe.build_result()
    final_cut = (
        _git("rev-parse", "HEAD"),
        _git("rev-parse", "HEAD^{tree}"),
        _git("status", "--short", "--", str(ROOT.relative_to(REPOSITORY))),
        _git("status", "--short"),
    )
    if final_cut != (
        source_commit,
        source_tree,
        source_status,
        repository_status,
    ):
        raise AssemblyError("repository identity changed during result assembly")
    if _sources() != sources:
        raise AssemblyError("source bytes changed during result assembly")
    try:
        final_manifest_bytes = read_bounded_relative_file(
            REPOSITORY,
            "contract/manifest.v1.json",
            maximum_bytes=MAX_CONTRACT_MANIFEST_BYTES,
            label="contract manifest",
        )
    except (OSError, SourceInventoryError) as error:
        raise AssemblyError(f"contract manifest resnapshot failed: {error}") from error
    if final_manifest_bytes != manifest_bytes:
        raise AssemblyError("contract manifest changed during result assembly")
    return {
        "schema": "ncp.b01-preliminary-architecture-evidence.v2",
        "scope": "proposed-adrs-only",
        "task": "B01",
        "candidate": "1.0.0-rc.1",
        "wire_version": "1.0",
        "source_commit": source_commit,
        "source_tree": source_tree,
        "source_paths_clean": source_status == "",
        "source_status": source_status.splitlines(),
        "repository_clean": repository_status == "",
        "repository_status": repository_status.splitlines(),
        "generated_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "fable_advice_response_sha256": (
            "080ad93775d6dec018a08efeadd49b0d57e6162a90f4bc7cf9a8b43199246d32"
        ),
        "normative_contract_sha256": EXPECTED_CONTRACT_SHA256,
        "contract_manifest_sha256": _sha256(manifest_bytes),
        "compact_contract_hash": "163acc57d8a62b66",
        "sources": sources,
        "decision_probe": decision_result,
        "observer_authorization_probe": authorization_result,
        "observer_capture_probe": capture_result,
        "freshness_acceptance_probe": freshness_result,
        "source_issuance_index_probe": source_index_result,
        "model": model_result,
        "smt": smt_result,
        "resources": resource_result,
        "claim_boundary": {
            "adrs_accepted": False,
            "normative_contract_changed": False,
            "canonical_formal_task_started": False,
            "implementation_or_refinement_proved": False,
            "independent_review_satisfied": False,
            "external_gate_satisfied": False,
            "release_authorized": False,
            "strongest_local_statement": (
                "No counterexample was found within the recorded finite models, "
                "decision, observer-authorization, observer-capture, "
                "freshness-and-acceptance, source-issuance-index, and fixed local "
                "resource probes; every registered executable mutant was detected, "
                "every registered hostile input was rejected, and every registered "
                "invariant and semantic-contrast witness was reached within those "
                "encoded finite cases."
            ),
        },
    }


def main() -> int:
    result = "NCP_B01_PRELIMINARY_RESULT=" + json.dumps(
        build_result(), separators=(",", ":"), sort_keys=True
    )
    if len(result.encode("utf-8")) > MAX_ASSEMBLED_RESULT_BYTES:
        raise AssemblyError("assembled evidence result exceeds its output bound")
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
