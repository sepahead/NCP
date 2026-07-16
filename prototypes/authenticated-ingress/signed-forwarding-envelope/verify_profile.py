#!/usr/bin/env python3
"""Verify exact dependencies and the quarantined forwarding source boundary."""

from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PYPROJECT = ROOT / "pyproject.toml"
LOCK = ROOT / "uv.lock"
FORWARDING = ROOT / "prototype" / "forwarding.py"
REPLAY = ROOT / "prototype" / "replay.py"

EXPECTED_PROJECT = {
    "name": "ncp-signed-forwarding-envelope-prototype",
    "version": "0.0.0",
    "requires-python": ">=3.14,<3.15",
    "dependencies": ["PyNaCl==1.6.2"],
}
EXPECTED_LOCKED = {
    "cffi": "2.1.0",
    "ncp-signed-forwarding-envelope-prototype": "0.0.0",
    "pycparser": "3.0",
    "pynacl": "1.6.2",
    "ruff": "0.15.21",
}


class VerificationError(ValueError):
    """The reviewed dependency or source boundary drifted."""


def verify_pyproject(document: dict[str, object]) -> None:
    project = document.get("project")
    if not isinstance(project, dict):
        raise VerificationError("project metadata is missing")
    for field, expected in EXPECTED_PROJECT.items():
        if project.get(field) != expected:
            raise VerificationError(f"project {field} differs from the reviewed value")
    groups = document.get("dependency-groups")
    if groups != {"dev": ["ruff==0.15.21"]}:
        raise VerificationError("development dependency group drifted")
    tool = document.get("tool")
    if not isinstance(tool, dict) or tool.get("uv") != {"package": False}:
        raise VerificationError("prototype must remain a non-package uv project")


def verify_lock(document: dict[str, object]) -> None:
    if document.get("version") != 1 or document.get("requires-python") != "==3.14.*":
        raise VerificationError("uv lock format or Python boundary drifted")
    packages = document.get("package")
    if not isinstance(packages, list):
        raise VerificationError("uv lock package list is missing")
    versions = {
        package.get("name"): package.get("version")
        for package in packages
        if isinstance(package, dict)
    }
    if len(packages) != len(versions) or versions != EXPECTED_LOCKED:
        raise VerificationError(f"resolved packages differ: {versions!r}")
    for package in packages:
        if not isinstance(package, dict) or package.get("source") == {"virtual": "."}:
            continue
        source = package.get("source")
        if source != {"registry": "https://pypi.org/simple"}:
            raise VerificationError("non-registry dependency source is present")
        artifacts = [package.get("sdist"), *(package.get("wheels") or [])]
        if not artifacts or any(
            not isinstance(artifact, dict)
            or not str(artifact.get("hash", "")).startswith("sha256:")
            for artifact in artifacts
        ):
            raise VerificationError("locked dependency artifact lacks SHA-256")


def verify_source(forwarding: str, replay: str) -> None:
    forwarding_required = [
        'TYPE = "ncp-forwarding-envelope+jws;v=1"',
        '"alg": "Ed25519"',
        '"crit": ["ncp"]',
        "VerifyKey(entry.public_key).verify(signing_input, signature)",
        (
            "exact_members(\n"
            "        strict_json_loads(envelope, OUTER_LIMITS),\n"
            '        {"payload", "protected", "signature"}'
        ),
        '"recovery_epoch"',
        '"forwarding_epoch"',
        '"forwarding_sequence"',
        "replay_store.commit_sequence(replay_key, forwarding_sequence)",
        "entry.issuer == carrier.principal_id",
        "entry.entity_id == carrier.entity_id",
        'if entry.role != "commander":',
    ]
    replay_required = [
        "PRAGMA journal_mode=WAL",
        "PRAGMA synchronous=FULL",
        "PRAGMA trusted_schema=OFF",
        "PRAGMA foreign_keys=ON",
        'self._connection.execute("BEGIN IMMEDIATE")',
        "WHERE high_water.sequence < excluded.sequence",
        'self._connection.execute("COMMIT")',
        'if failpoint == "after_commit":',
        "MAX_REPLAY_SCOPES = 128",
        "MAX_REPLAY_DATABASE_BYTES = 8_388_608",
        'getattr(os, "O_NOFOLLOW", None)',
        "os.fstat(file_descriptor)",
        "os.fsync(directory_descriptor)",
        'value["new_recovery_epoch"] != old.recovery_epoch + 1',
        'value["new_store_id"] == old.store_id',
        "key = validate_replay_key(key)",
        "replay database schema SQL is unknown",
        "initialization requires an absent replay database path",
        "replay store is active in another cooperating process",
    ]
    for fragment in forwarding_required:
        if fragment not in forwarding:
            raise VerificationError(f"forwarding invariant missing: {fragment!r}")
    for fragment in replay_required:
        if fragment not in replay:
            raise VerificationError(f"replay invariant missing: {fragment!r}")
    forbidden = [
        "INSERT OR REPLACE",
        "synchronous=NORMAL",
        "VerifyKey(ncp",
        "private_key =",
        "SigningKey(bytes",
    ]
    combined = forwarding + replay
    for fragment in forbidden:
        if fragment in combined:
            raise VerificationError(f"forbidden source surface found: {fragment!r}")


def main() -> int:
    try:
        verify_pyproject(tomllib.loads(PYPROJECT.read_text(encoding="utf-8")))
        verify_lock(tomllib.loads(LOCK.read_text(encoding="utf-8")))
        verify_source(
            FORWARDING.read_text(encoding="utf-8"),
            REPLAY.read_text(encoding="utf-8"),
        )
    except (OSError, tomllib.TOMLDecodeError, VerificationError) as error:
        print(f"forwarding profile verification failed: {error}")
        return 1
    print("forwarding dependencies and protected source boundary verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
