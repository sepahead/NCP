#!/usr/bin/env python3
"""Check the selected local scope and bounded receipt references.

This checks structure, identity, coverage, and locally observed file hashes.
It cannot establish that a recorded command ran or validate scientific claims.
The operational runner and exact archived command evidence supply those facts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import tomllib
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "local/python"))
from ncp_local import LocalError, decode, profile_descriptor_bytes, profile_digest  # noqa: E402

SCOPE_KEYS = {
    "schema",
    "release_name",
    "intended_tag",
    "status",
    "profile",
    "descriptor",
    "descriptor_raw_sha256",
    "descriptor_typed_digest",
    "normative_precedence",
    "packages",
    "application_roles",
    "supported_host_target",
    "excluded_capabilities",
    "bootstrap_requirements",
    "operational_requirements",
    "post_publication_requirements",
    "historical_scope",
    "bootstrap_receipt",
    "operational_receipt",
    "publication_receipt",
    "scientific_validation",
}
RECEIPTS = ("bootstrap_receipt", "operational_receipt", "publication_receipt")


def require(condition: bool, detail: str) -> None:
    if not condition:
        raise ValueError(detail)


def hexadecimal(value: Any, length: int) -> bool:
    return (
        type(value) is str
        and len(value) == length
        and all(c in "0123456789abcdef" for c in value)
    )


def source_path(root: Path, value: Any) -> Path:
    require(type(value) is str and bool(value), "empty source path")
    relative = Path(value)
    require(
        not relative.is_absolute() and ".." not in relative.parts,
        "source escapes registry root",
    )
    target = root / relative
    require(not target.is_symlink(), "source symlink is not a release reference")
    require(
        target.resolve().is_relative_to(root.resolve()),
        "resolved source escapes registry root",
    )
    require(target.is_file(), "source reference is not a file")
    return target


def referenced_bytes(root: Path, reference: Any, maximum: int) -> bytes:
    require(
        type(reference) is dict and set(reference) == {"path", "sha256"},
        "invalid evidence reference",
    )
    require(hexadecimal(reference["sha256"], 64), "invalid evidence digest")
    path = source_path(root, reference["path"])
    require(path.stat().st_size <= maximum, "evidence exceeds declared bound")
    with path.open("rb") as source:
        data = source.read(maximum + 1)
    require(len(data) <= maximum, "evidence changed beyond its bound")
    require(
        hashlib.sha256(data).hexdigest() == reference["sha256"],
        "evidence digest differs",
    )
    return data


def scope_digest(scope: dict[str, Any]) -> str:
    # Qualification status and references change after code is frozen. The
    # selected contract, packages, scopes, and all gate requirements stay bound.
    projection = {
        key: value for key, value in scope.items() if key not in {*RECEIPTS, "status"}
    }
    # Release metadata is not an application-wire digest domain. It uses
    # sorted UTF-8 JSON with no numeric scientific payloads or execution role.
    wire = json.dumps(
        projection,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode()
    return hashlib.sha256(b"ncp.local.release-scope.v1\0" + wire).hexdigest()


def check_receipt(
    root: Path, scope: dict[str, Any], stage: str, reference: Any
) -> None:
    receipt = decode(referenced_bytes(root, reference, 65_536))
    require(
        type(receipt) is dict
        and set(receipt)
        == {
            "schema",
            "stage",
            "profile_digest",
            "scope_digest",
            "status",
            "source_commits",
            "artifact_manifest",
            "checks",
            "scientific_validation",
        },
        "receipt schema differs",
    )
    require(
        receipt["schema"] == "ncp.local.release-receipt.v1"
        and receipt["stage"] == stage,
        "receipt stage differs",
    )
    require(
        receipt["profile_digest"] == scope["descriptor_typed_digest"]
        and receipt["scope_digest"] == scope_digest(scope),
        "receipt scope differs",
    )
    require(
        receipt["status"] == "passed" and receipt["scientific_validation"] is False,
        "receipt grants unsupported completion",
    )
    commits = receipt["source_commits"]
    require(
        type(commits) is dict
        and "NCP" in commits
        and all(
            type(name) is str and name and hexadecimal(commit, 40)
            for name, commit in commits.items()
        ),
        "receipt source commit roster differs",
    )
    # The manifest is separately typed and checked by its owning artifact gate.
    manifest = decode(referenced_bytes(root, receipt["artifact_manifest"], 65_536))
    require(type(manifest) is dict, "artifact manifest is not an object")
    key = (
        "post_publication_requirements"
        if stage == "publication"
        else stage + "_requirements"
    )
    requirements = scope[key]
    checks = receipt["checks"]
    require(
        type(checks) is list and len(checks) == len(requirements),
        "receipt gate roster is incomplete",
    )
    observed = []
    for check in checks:
        require(
            type(check) is dict and set(check) == {"requirement", "result", "evidence"},
            "receipt check schema differs",
        )
        require(
            check["result"] == "passed" and check["requirement"] in requirements,
            "receipt check is unresolved or unknown",
        )
        referenced_bytes(root, check["evidence"], 16 * 1024 * 1024)
        observed.append(check["requirement"])
    require(len(set(observed)) == len(requirements), "receipt duplicates a gate")


def check_scope(scope: Any, root: Path = ROOT) -> dict[str, Any]:
    require(type(scope) is dict and set(scope) == SCOPE_KEYS, "scope schema differs")
    require(scope["schema"] == "ncp.local-release-scope.v1", "scope version differs")
    require(scope["profile"] == "ncp.local-lockstep.v1", "unknown local profile")
    require(
        scope["scientific_validation"] is False, "scope grants scientific authority"
    )
    descriptor = source_path(root, scope["descriptor"]).read_bytes()
    require(
        len(descriptor) <= 65_536 and descriptor == profile_descriptor_bytes(),
        "SDK descriptor differs",
    )
    require(
        hashlib.sha256(descriptor).hexdigest() == scope["descriptor_raw_sha256"],
        "descriptor bytes differ",
    )
    require(
        profile_digest() == scope["descriptor_typed_digest"],
        "descriptor semantics differ",
    )
    data = decode(descriptor)
    require("status" not in data, "publication status entered wire identity")
    roles = scope["application_roles"]
    require(
        type(roles) is list and len(roles) == len(data["roles"]),
        "application role roster differs",
    )
    observed = set()
    for row in roles:
        require(
            type(row) is dict
            and set(row) == {"role", "owner", "profile", "source_visibility"},
            "application role schema differs",
        )
        require(
            row["role"] in data["roles"] and row["role"] not in observed,
            "application role is unknown or repeated",
        )
        require(
            all(type(row[key]) is str and row[key] for key in ("owner", "profile")),
            "application identity is empty",
        )
        require(
            row["source_visibility"] in {"public", "private"},
            "source access claim differs",
        )
        observed.add(row["role"])
    packages = scope["packages"]
    require(type(packages) is list and len(packages) == 2, "SDK roster differs")
    ecosystems = set()
    for row in packages:
        require(
            type(row) is dict and set(row) == {"name", "ecosystem", "manifest"},
            "SDK row schema differs",
        )
        require(
            row["ecosystem"] in {"Rust", "Python"}
            and row["ecosystem"] not in ecosystems,
            "SDK independence roster differs",
        )
        with source_path(root, row["manifest"]).open("rb") as source:
            manifest = tomllib.load(source)
        package = manifest["package" if row["ecosystem"] == "Rust" else "project"]
        require(
            package["name"] == row["name"] and package["version"] == "1.0.0",
            "SDK package identity differs",
        )
        ecosystems.add(row["ecosystem"])
    for key in (
        "bootstrap_requirements",
        "operational_requirements",
        "post_publication_requirements",
        "excluded_capabilities",
    ):
        values = scope[key]
        require(
            type(values) is list
            and values
            and all(type(value) is str and value for value in values)
            and len(set(values)) == len(values),
            "empty, repeated, or malformed scope requirements",
        )
    historical = scope["historical_scope"]
    require(
        type(historical) is dict
        and set(historical)
        == {
            "candidate",
            "scope",
            "gates",
            "status",
            "local_release_can_promote_historical_gates",
        },
        "historical scope schema differs",
    )
    require(
        historical["local_release_can_promote_historical_gates"] is False
        and historical["status"] == "release-blocked",
        "local scope promotes broader gates",
    )
    source_path(root, historical["scope"])
    source_path(root, historical["gates"])
    require(
        scope["status"] in {"unreleased", "qualified", "published"},
        "unknown release status",
    )
    if scope["status"] in {"qualified", "published"}:
        require(
            all(scope[key] is not None for key in RECEIPTS[:2]),
            "qualification evidence is absent",
        )
    if scope["status"] == "published":
        require(
            scope["publication_receipt"] is not None, "publication evidence is absent"
        )
    for key in RECEIPTS:
        if scope[key] is not None:
            check_receipt(root, scope, key.removesuffix("_receipt"), scope[key])
    return {
        "status": scope["status"],
        "scope_digest": scope_digest(scope),
        "validation_scope": "structure, identity, coverage, and referenced file hashes",
        "scientific_validation": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    with (ROOT / "local/release.v1.json").open("rb") as source:
        scope = decode(source.read(65_537))
    try:
        result = check_scope(scope)
    except (ValueError, OSError, KeyError, TypeError, LocalError) as error:
        print(f"local release scope rejected: {error}", file=sys.stderr)
        return 1
    print(
        f"local scope integrity passed; release status: {result['status']}; digest: {result['scope_digest']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
