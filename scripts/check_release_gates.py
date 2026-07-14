#!/usr/bin/env python3
"""Validate the phased NCP release-gate registry.

Initial release authorization and post-publication validation are deliberately
different phases.  This checker keeps their identifiers disjoint, ensures every
candidate requirement fails closed, and prevents a post-publication action from
becoming an impossible prerequisite for the initial tag.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
import tomllib
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "contract" / "release-gates.v1.json"
RELEASE_WORKFLOW = ROOT / ".github" / "workflows" / "release.yml"
ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

PRE_RELEASE_IDS = (
    "normative-contract",
    "zero-skip-conformance",
    "live-mtls-acl-rotation-revocation",
    "two-independent-non-rust-live-peers",
    "fault-backpressure-restart-soak",
    "fuzz-sanitizer-duration",
    "performance-resource-profile",
    "installed-package-matrix",
    "registry-namespace-ownership",
    "consumer-certification",
    "independent-clean-room-reproduction",
    "signed-sbom-provenance",
)
POST_RELEASE_IDS = (
    "post-publication-install-smoke",
    "post-publication-emergency-revocation-exercise",
)


class GatePolicyError(ValueError):
    """The machine release policy is incomplete or internally inconsistent."""


def _object_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, member in pairs:
        if key in value:
            raise GatePolicyError(f"duplicate JSON key {key!r}")
        value[key] = member
    return value


def load(path: Path = REGISTRY) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=_object_no_duplicates
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise GatePolicyError(f"cannot read release-gate registry: {error}") from error
    if not isinstance(value, dict):
        raise GatePolicyError("release-gate registry must be one JSON object")
    return value


def _entries(value: Any, field: str, *, post_release: bool) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise GatePolicyError(f"{field} must be a non-empty array")
    identifiers: list[str] = []
    allowed = {"id", "required", "local"}
    if post_release:
        allowed.add("blocks_initial_release")
    for index, entry in enumerate(value):
        path = f"{field}[{index}]"
        if not isinstance(entry, dict) or set(entry) != allowed:
            raise GatePolicyError(f"{path} must contain exactly {sorted(allowed)}")
        identifier = entry["id"]
        if not isinstance(identifier, str) or ID.fullmatch(identifier) is None:
            raise GatePolicyError(f"{path}.id is not a canonical kebab-case identifier")
        if entry["required"] is not True:
            raise GatePolicyError(f"{path}.required must fail closed as true")
        if not isinstance(entry["local"], bool):
            raise GatePolicyError(f"{path}.local must be a boolean")
        if post_release and entry["blocks_initial_release"] is not False:
            raise GatePolicyError(
                f"{path}.blocks_initial_release must be false; publication must precede it"
            )
        identifiers.append(identifier)
    if len(identifiers) != len(set(identifiers)):
        raise GatePolicyError(f"{field} contains a duplicate identifier")
    return tuple(identifiers)


def package_version() -> str:
    try:
        manifest = tomllib.loads((ROOT / "Cargo.toml").read_text(encoding="utf-8"))
        version = manifest["workspace"]["package"]["version"]
    except (OSError, UnicodeError, tomllib.TOMLDecodeError, KeyError) as error:
        raise GatePolicyError(f"cannot derive workspace package version: {error}") from error
    if not isinstance(version, str) or not version:
        raise GatePolicyError("workspace package version must be a non-empty string")
    return version


def validate(value: dict[str, Any], expected_candidate: str | None = None) -> None:
    candidate = expected_candidate if expected_candidate is not None else package_version()
    if value.get("schema") != "ncp.release-gates.v1":
        raise GatePolicyError("schema must be ncp.release-gates.v1")
    if value.get("candidate") != candidate:
        raise GatePolicyError(
            f"candidate must equal workspace package version {candidate!r}"
        )
    if value.get("release_allowed") is not False:
        raise GatePolicyError("the unreleased candidate must retain release_allowed=false")

    pre = _entries(value.get("pre_release_gates"), "pre_release_gates", post_release=False)
    post = _entries(
        value.get("post_release_validations"),
        "post_release_validations",
        post_release=True,
    )
    if pre != PRE_RELEASE_IDS:
        raise GatePolicyError(
            "pre_release_gates must contain the canonical ordered set: "
            + ", ".join(PRE_RELEASE_IDS)
        )
    if post != POST_RELEASE_IDS:
        raise GatePolicyError(
            "post_release_validations must contain the canonical ordered set: "
            + ", ".join(POST_RELEASE_IDS)
        )
    overlap = set(pre) & set(post)
    if overlap:
        raise GatePolicyError(f"release phases overlap: {', '.join(sorted(overlap))}")

    for field in ("pre_release_policy", "post_release_policy"):
        policy = value.get(field)
        if not isinstance(policy, str) or not policy.strip():
            raise GatePolicyError(f"{field} must be a non-empty policy string")


def require_release_allowed(value: dict[str, Any]) -> None:
    """Fail closed when a tag workflow is invoked for the held candidate.

    The current registry deliberately pins ``release_allowed=false``.  Moving the
    hold is a reviewed source change that must also replace this candidate-only
    validator with evidence-bound release authorization; a tag alone cannot do it.
    """

    if value.get("release_allowed") is not True:
        raise GatePolicyError(
            "release packaging is blocked: contract/release-gates.v1.json retains "
            "release_allowed=false and required external evidence is NOT RUN"
        )


def validate_release_workflow_hold(text: str | None = None) -> None:
    if text is None:
        try:
            text = RELEASE_WORKFLOW.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            raise GatePolicyError(f"cannot read release workflow: {error}") from error
    required_step = (
        "- name: Enforce candidate release hold\n"
        "        run: python3 scripts/check_release_gates.py --require-release-allowed"
    )
    if required_step not in text:
        raise GatePolicyError(
            "tag-triggered release workflow must enforce --require-release-allowed "
            "before archive construction"
        )


def self_test() -> None:
    good = load()
    candidate = package_version()
    validate(good, candidate)
    validate_release_workflow_hold()

    missing_performance = copy.deepcopy(good)
    missing_performance["pre_release_gates"] = [
        gate
        for gate in missing_performance["pre_release_gates"]
        if gate["id"] != "performance-resource-profile"
    ]
    missing_registry_ownership = copy.deepcopy(good)
    missing_registry_ownership["pre_release_gates"] = [
        gate
        for gate in missing_registry_ownership["pre_release_gates"]
        if gate["id"] != "registry-namespace-ownership"
    ]
    post_blocks = copy.deepcopy(good)
    post_blocks["post_release_validations"][0]["blocks_initial_release"] = True
    duplicate = copy.deepcopy(good)
    duplicate["pre_release_gates"].append(
        copy.deepcopy(duplicate["pre_release_gates"][0])
    )
    stale_candidate = copy.deepcopy(good)
    stale_candidate["candidate"] = "9.9.9"
    for hostile in (
        missing_performance,
        missing_registry_ownership,
        post_blocks,
        duplicate,
        stale_candidate,
    ):
        try:
            validate(hostile, candidate)
        except GatePolicyError:
            continue
        raise AssertionError("hostile release-gate policy passed validation")

    try:
        require_release_allowed(good)
    except GatePolicyError:
        pass
    else:
        raise AssertionError("release hold did not block tag-triggered packaging")

    try:
        validate_release_workflow_hold("name: hostile workflow\n")
    except GatePolicyError:
        pass
    else:
        raise AssertionError("release workflow without the hold passed validation")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--self-test", action="store_true", help="also run negative policy mutations"
    )
    parser.add_argument(
        "--require-release-allowed",
        action="store_true",
        help="fail unless this exact source is explicitly authorized for tag packaging",
    )
    args = parser.parse_args()
    try:
        policy = load()
        validate(policy)
        validate_release_workflow_hold()
        if args.require_release_allowed:
            require_release_allowed(policy)
        if args.self_test:
            self_test()
    except (GatePolicyError, AssertionError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(
        "OK release-gate policy: "
        f"{len(PRE_RELEASE_IDS)} pre-release gates, "
        f"{len(POST_RELEASE_IDS)} post-release validations"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
