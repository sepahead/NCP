#!/usr/bin/env python3
"""Generate and validate the non-normative proposed NCP decision registry.

The proposed registry deliberately lives outside ``contract/``. The current
contract-manifest generator includes every ``contract/*.v1.json`` input in the
complete normative digest, so placing a PROPOSED record there would silently
change the release-blocked candidate contract.

This tool cannot accept an ADR, count model advice as review, authorize a
rebaseline, write the promotion target, or release NCP.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, NoReturn


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "adr" / "decision-registry.source.v1.json"
OUTPUT = ROOT / "docs" / "adr" / "decision-registry.proposed.v1.json"
SCHEMA = ROOT / "docs" / "adr" / "decision-registry.proposed.schema.v1.json"
PROMOTION_TARGET = ROOT / "contract" / "decision-registry.v1.json"

SOURCE_SCHEMA = "ncp.proposed-decision-registry-source.v1"
OUTPUT_SCHEMA = "ncp.proposed-decision-registry.v1"
GENERATOR = "scripts/generate_decision_registry.py"
EXPECTED_IDS = tuple(f"ADR-{number:03d}" for number in range(1, 12))
HEX64 = re.compile(r"^[0-9a-f]{64}$")
RELATIVE_PATH = re.compile(r"^(?!/)(?!.*(?:^|/)\.\.(?:/|$)).+$")
JSON_FENCE = re.compile(r"```json\n(.*?)\n```", re.DOTALL)

REQUIRED_SECTIONS = (
    "## Context",
    "## Proposed decision",
    "## Rejected alternatives",
    "## Invalid or hostile example",
    "## Actors and state transitions",
    "## Bounds and resource behavior",
    "## Threat and hazard analysis",
    "## Formal properties",
    "## Migration",
    "## Operational recovery",
    "## Compatibility and rollback",
    "## Open questions",
    "## Ten-lens review",
    "## Ratification record",
)

CLAIM_BOUNDARY = (
    "This generated registry records proposed architecture decisions only. It is "
    "non-normative, cannot satisfy independent review, cannot authorize the "
    "pre-release rebaseline or publication, and grants no runtime identity, "
    "authority, plant action, safety, interoperability, or scientific claim."
)


class RegistryError(ValueError):
    """The proposed decision registry is malformed or overclaims status."""


def fail(message: str) -> NoReturn:
    raise RegistryError(message)


def object_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, member in pairs:
        if key in value:
            fail(f"duplicate JSON key {key!r}")
        value[key] = member
    return value


def load_json(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        fail(f"expected regular non-symlink JSON file: {path.relative_to(ROOT)}")
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=object_no_duplicates,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        fail(f"cannot read {path.relative_to(ROOT)}: {error}")
    if not isinstance(value, dict):
        fail(f"{path.relative_to(ROOT)} must contain one JSON object")
    return value


def exact_keys(value: dict[str, Any], expected: set[str], path: str) -> None:
    actual = set(value)
    if actual != expected:
        fail(
            f"{path} keys differ: missing={sorted(expected - actual)}, "
            f"extra={sorted(actual - expected)}"
        )


def bounded_string(
    value: Any, path: str, *, minimum: int = 1, maximum: int = 1024
) -> str:
    if not isinstance(value, str) or not minimum <= len(value) <= maximum:
        fail(f"{path} must be a string of length {minimum}..{maximum}")
    if any(character == "\x00" for character in value):
        fail(f"{path} contains NUL")
    return value


def relative_path(value: Any, path: str) -> str:
    text = bounded_string(value, path, maximum=256)
    if not RELATIVE_PATH.fullmatch(text) or "\\" in text:
        fail(f"{path} must be a safe repository-relative POSIX path")
    return text


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def validate_markdown(
    decision: dict[str, Any], *, content_override: bytes | None = None
) -> tuple[str, int]:
    relative = decision["path"]
    path = ROOT / relative
    if content_override is None:
        if path.is_symlink() or not path.is_file() or ROOT.resolve() not in path.resolve().parents:
            fail(f"{relative} must be a regular repository file")
        content = path.read_bytes()
    else:
        content = content_override
    if not 1024 <= len(content) <= 131072:
        fail(f"{relative} byte size is outside 1024..131072")
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as error:
        fail(f"{relative} is not UTF-8: {error}")
    expected_heading = f"# {decision['id']} — {decision['title']}"
    if not text.startswith(expected_heading + "\n"):
        fail(f"{relative} does not start with {expected_heading!r}")
    if "- Status: `PROPOSED`" not in text[:1024]:
        fail(f"{relative} lacks exact PROPOSED status metadata")
    positions: list[int] = []
    for section in REQUIRED_SECTIONS:
        position = text.find(section)
        if position < 0:
            fail(f"{relative} lacks required section {section!r}")
        positions.append(position)
    if positions != sorted(positions):
        fail(f"{relative} required sections are out of order")
    lens = text[text.index("## Ten-lens review") : text.index("## Ratification record")]
    for number in range(1, 11):
        if not re.search(rf"(?m)^{number}\. ", lens):
            fail(f"{relative} lacks ten-lens item {number}")
    fences = JSON_FENCE.findall(text)
    if not fences:
        fail(f"{relative} must include at least one parseable JSON example")
    for index, fence in enumerate(fences):
        try:
            json.loads(fence, object_pairs_hook=object_no_duplicates)
        except (json.JSONDecodeError, RegistryError) as error:
            fail(f"{relative} JSON fence {index} is invalid: {error}")
    return sha256_bytes(content), len(content)


def validate_source(source: dict[str, Any]) -> list[dict[str, Any]]:
    exact_keys(
        source,
        {
            "schema",
            "normative",
            "candidate",
            "wire_version",
            "task",
            "claim_boundary",
            "promotion_target",
            "promotion_blocked_until_all_accepted",
            "decisions",
            "review_records",
        },
        "$",
    )
    if source["schema"] != SOURCE_SCHEMA:
        fail("$.schema is not the proposed registry source schema")
    if source["normative"] is not False:
        fail("$.normative must be false")
    if source["candidate"] != "1.0.0-rc.1" or source["wire_version"] != "1.0":
        fail("$.candidate/wire_version differs from the frozen draft target")
    if source["task"] != "B01":
        fail("$.task must be B01")
    bounded_string(source["claim_boundary"], "$.claim_boundary", minimum=80)
    if source["promotion_target"] != "contract/decision-registry.v1.json":
        fail("$.promotion_target differs from the reviewed target")
    if source["promotion_blocked_until_all_accepted"] is not True:
        fail("$.promotion_blocked_until_all_accepted must be true")
    if source["review_records"] != []:
        fail("$.review_records must remain empty until qualifying reviews exist")
    decisions = source["decisions"]
    if not isinstance(decisions, list) or len(decisions) != len(EXPECTED_IDS):
        fail("$.decisions must contain exactly ADR-001 through ADR-011")
    ids: list[str] = []
    paths: list[str] = []
    for index, decision in enumerate(decisions):
        path = f"$.decisions[{index}]"
        if not isinstance(decision, dict):
            fail(f"{path} must be an object")
        exact_keys(
            decision,
            {
                "id",
                "title",
                "path",
                "status",
                "required_review_roles",
                "defect_ids",
            },
            path,
        )
        identifier = bounded_string(decision["id"], f"{path}.id", maximum=7)
        ids.append(identifier)
        bounded_string(decision["title"], f"{path}.title", minimum=8, maximum=160)
        relative = relative_path(decision["path"], f"{path}.path")
        paths.append(relative)
        if not relative.startswith("docs/adr/") or not relative.endswith(".md"):
            fail(f"{path}.path must name an ADR Markdown file outside contract/")
        if decision["status"] != "PROPOSED":
            fail(f"{path}.status must remain PROPOSED in the draft registry")
        roles = decision["required_review_roles"]
        if (
            not isinstance(roles, list)
            or not 2 <= len(roles) <= 16
            or len(roles) != len(set(roles))
        ):
            fail(f"{path}.required_review_roles must be 2..16 unique roles")
        for role_index, role in enumerate(roles):
            bounded_string(
                role,
                f"{path}.required_review_roles[{role_index}]",
                minimum=3,
                maximum=128,
            )
        defects = decision["defect_ids"]
        if (
            not isinstance(defects, list)
            or not 1 <= len(defects) <= 8
            or len(defects) != len(set(defects))
        ):
            fail(f"{path}.defect_ids must be 1..8 unique IDs")
        for defect in defects:
            if not isinstance(defect, str) or not re.fullmatch(r"D(0[1-9]|1[0-7])", defect):
                fail(f"{path}.defect_ids contains an unknown defect")
    if tuple(ids) != EXPECTED_IDS or len(paths) != len(set(paths)):
        fail("$.decisions IDs are missing/out of order or paths are duplicated")
    covered_defects = {
        defect for decision in decisions for defect in decision["defect_ids"]
    }
    expected_defects = {f"D{number:02d}" for number in range(1, 18)}
    if covered_defects != expected_defects:
        fail(
            "$.decisions defect coverage differs from D01..D17: "
            f"missing={sorted(expected_defects - covered_defects)}, "
            f"extra={sorted(covered_defects - expected_defects)}"
        )
    return decisions


def build_registry(source: dict[str, Any] | None = None) -> dict[str, Any]:
    value = copy.deepcopy(source if source is not None else load_json(SOURCE))
    decisions = validate_source(value)
    generated_decisions: list[dict[str, Any]] = []
    for decision in decisions:
        digest, byte_count = validate_markdown(decision)
        generated_decisions.append(
            {
                **decision,
                "content_sha256": digest,
                "bytes": byte_count,
            }
        )
    if PROMOTION_TARGET.exists():
        fail(
            "contract/decision-registry.v1.json exists while every ADR is still "
            "PROPOSED; remove the unratified normative target"
        )
    source_bytes = SOURCE.read_bytes()
    return {
        "schema": OUTPUT_SCHEMA,
        "normative": False,
        "candidate": value["candidate"],
        "wire_version": value["wire_version"],
        "task": value["task"],
        "claim_boundary": CLAIM_BOUNDARY,
        "generated_by": GENERATOR,
        "source": {
            "path": SOURCE.relative_to(ROOT).as_posix(),
            "sha256": sha256_bytes(source_bytes),
            "bytes": len(source_bytes),
        },
        "promotion_target": value["promotion_target"],
        "promotion_blocked": True,
        "counts": {
            "decisions": len(generated_decisions),
            "proposed": len(generated_decisions),
            "accepted": 0,
            "review_records": 0,
        },
        "decisions": generated_decisions,
        "review_records": [],
    }


def generated_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def validate_generated(value: dict[str, Any], expected: dict[str, Any]) -> None:
    if value != expected:
        fail("generated proposed decision registry differs from exact expected content")
    if value.get("schema") != OUTPUT_SCHEMA or value.get("normative") is not False:
        fail("generated registry overclaims schema or normative status")
    if value.get("promotion_blocked") is not True:
        fail("generated registry does not block promotion")
    counts = value.get("counts")
    if counts != {
        "decisions": 11,
        "proposed": 11,
        "accepted": 0,
        "review_records": 0,
    }:
        fail("generated registry counts are optimistic or incomplete")
    for decision in value["decisions"]:
        if decision["status"] != "PROPOSED":
            fail("generated registry contains a non-PROPOSED decision")
        if not HEX64.fullmatch(decision["content_sha256"]):
            fail("generated registry contains an invalid content digest")


def must_fail(action, description: str) -> None:
    try:
        action()
    except RegistryError:
        return
    raise AssertionError(f"hostile self-test passed: {description}")


def self_test() -> None:
    source = load_json(SOURCE)
    first = generated_bytes(build_registry(source))
    second = generated_bytes(build_registry(source))
    if first != second:
        raise AssertionError("decision registry generation is not deterministic")

    hostile = copy.deepcopy(source)
    hostile["decisions"][0]["status"] = "ACCEPTED"
    must_fail(lambda: build_registry(hostile), "unreviewed ACCEPTED status")

    hostile = copy.deepcopy(source)
    hostile["decisions"][0]["path"] = "contract/decision-registry.v1.json"
    must_fail(lambda: build_registry(hostile), "proposed path inside contract/")

    hostile = copy.deepcopy(source)
    hostile["decisions"][0]["required_review_roles"] *= 2
    must_fail(lambda: build_registry(hostile), "duplicate reviewer roles")

    hostile = copy.deepcopy(source)
    hostile["decisions"][1]["defect_ids"].remove("D17")
    must_fail(lambda: build_registry(hostile), "incomplete D01..D17 coverage")

    decision = copy.deepcopy(source["decisions"][0])
    original = (ROOT / decision["path"]).read_bytes()
    damaged = original.replace(b"## Formal properties", b"## Missing properties", 1)
    must_fail(
        lambda: validate_markdown(decision, content_override=damaged),
        "missing mandatory ADR section",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--write", action="store_true", help="replace the generated proposed registry"
    )
    mode.add_argument(
        "--check",
        action="store_true",
        help="check the generated proposed registry (the default)",
    )
    parser.add_argument(
        "--self-test", action="store_true", help="also run hostile draft mutations"
    )
    args = parser.parse_args()

    try:
        if args.self_test:
            self_test()
        expected = build_registry()
        content = generated_bytes(expected)
        if args.write:
            OUTPUT.parent.mkdir(parents=True, exist_ok=True)
            OUTPUT.write_bytes(content)
            print(f"WROTE {OUTPUT.relative_to(ROOT)}")
            return 0
        current = load_json(OUTPUT)
        validate_generated(current, expected)
        if OUTPUT.read_bytes() != content:
            fail("generated registry formatting is stale")
        load_json(SCHEMA)
        print(
            "OK proposed decision registry: 11 PROPOSED ADRs, "
            "promotion blocked, no independent reviews recorded"
        )
        return 0
    except RegistryError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
