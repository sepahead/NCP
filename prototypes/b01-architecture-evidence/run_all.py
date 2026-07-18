#!/usr/bin/env python3
"""Assemble one exact-source B01 preliminary architecture-evidence result."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import model_check
import resource_probe
import run_smt

ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
SOURCE_SUFFIXES = {".py", ".sh", ".smt2", ".md"}
EXPECTED_CONTRACT_SHA256 = (
    "9cae331742d01e9b164e029aa06c644e6b1886176d0816a6ef883af138355c90"
)


class AssemblyError(RuntimeError):
    """One source-enumeration, Git-binding, or result-assembly failure."""


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _object_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, member in pairs:
        if key in value:
            raise AssemblyError(f"duplicate contract manifest key {key!r}")
        value[key] = member
    return value


def _reject_json_constant(value: str) -> None:
    raise AssemblyError(f"non-finite contract manifest constant {value!r}")


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
    output: list[dict[str, Any]] = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or path.suffix not in SOURCE_SUFFIXES:
            continue
        content = path.read_bytes()
        output.append(
            {
                "path": path.relative_to(REPOSITORY).as_posix(),
                "bytes": len(content),
                "sha256": _sha256(content),
            }
        )
    if len(output) < 10:
        raise AssemblyError("preliminary evidence source set is unexpectedly small")
    return output


def build_result() -> dict[str, Any]:
    source_status = _git("status", "--short", "--", str(ROOT.relative_to(REPOSITORY)))
    repository_status = _git("status", "--short")
    manifest_bytes = (REPOSITORY / "contract/manifest.v1.json").read_bytes()
    manifest = json.loads(
        manifest_bytes,
        object_pairs_hook=_object_no_duplicates,
        parse_constant=_reject_json_constant,
    )
    if manifest.get("contract_digest_sha256") != EXPECTED_CONTRACT_SHA256:
        raise AssemblyError("current contract manifest digest changed")
    return {
        "schema": "ncp.b01-preliminary-architecture-evidence.v1",
        "scope": "proposed-adrs-only",
        "task": "B01",
        "candidate": "1.0.0-rc.1",
        "wire_version": "1.0",
        "source_commit": _git("rev-parse", "HEAD"),
        "source_tree": _git("rev-parse", "HEAD^{tree}"),
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
        "sources": _sources(),
        "model": model_check.build_result(),
        "smt": run_smt.build_result(),
        "resources": resource_probe.build_result(),
        "claim_boundary": {
            "adrs_accepted": False,
            "normative_contract_changed": False,
            "canonical_formal_task_started": False,
            "implementation_or_refinement_proved": False,
            "independent_review_satisfied": False,
            "external_gate_satisfied": False,
            "release_authorized": False,
            "strongest_local_statement": (
                "No counterexample was found within the recorded finite models and "
                "fixed local resource corpus; every registered seeded mutation "
                "was detected."
            ),
        },
    }


def main() -> int:
    print(
        "NCP_B01_PRELIMINARY_RESULT="
        + json.dumps(build_result(), separators=(",", ":"), sort_keys=True)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
