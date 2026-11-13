#!/usr/bin/env python3
"""Check conformance/requirements.json against spec/NCP-2.md and the checks that it names.

The specification promises that the file maps each requirement to the checks that test it
(section 14). This script enforces the promise:

1. Every line of the specification with MUST, MUST NOT, SHOULD, SHOULD NOT, or REQUIRED, and every
   numbered rule of sections 7.3, 7.6, and 8, has exactly one entry with the same text and section.
   A changed requirement therefore needs a reviewed entry.
2. Every entry names at least one check, or says why it is untested. Only a SHOULD, or a rule for
   deployments, may stay untested.
3. Every reference exists: the vector case, the test function (of the SDKs or of the Zenoh
   bindings), the model property, the Lean claim, or the step of the gate.

Usage: check_ncp2_requirements.py   (from any directory; standard library only)
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KEYWORD = re.compile(r"\b(MUST|SHOULD|REQUIRED)\b")
HEADING = re.compile(r"^(#{2,3}) (\d+(?:\.\d+)?)\.? ")
NUMBERED_SECTIONS = ("7.3", "7.6", "8")
# Sections that describe the checks rather than state requirements.
META_SECTIONS = ("14",)


def extract(spec: str) -> list[tuple[str, str]]:
    """(section, text) of each requirement line, in document order."""
    found: list[tuple[str, str]] = []
    section, fence = "", False
    for line in spec.split("\n"):
        if line.startswith("```"):
            fence = not fence
            continue
        if fence:
            continue
        heading = HEADING.match(line)
        if heading:
            section = heading.group(2)
            continue
        text = line.strip()
        numbered = re.match(r"^(\d+)\. ", text)
        if section in NUMBERED_SECTIONS and numbered and not line.startswith(" "):
            found.append((f"{section}.{numbered.group(1)}", text))
        elif KEYWORD.search(text) and "RFC 2119" not in text and section not in META_SECTIONS:
            found.append((section, text))
    return found


def test_names(directory: Path, pattern: str) -> set[str]:
    names: set[str] = set()
    for path in directory.rglob("*"):
        if path.suffix in (".py", ".rs") and path.is_file():
            names.update(re.findall(pattern, path.read_text(encoding="utf-8")))
    return names


def schema_keywords(value: object, found: set[str]) -> None:
    if isinstance(value, dict):
        found.update(value)
        for item in value.values():
            schema_keywords(item, found)
    elif isinstance(value, list):
        for item in value:
            schema_keywords(item, found)


def main() -> int:
    spec = (ROOT / "spec" / "NCP-2.md").read_text(encoding="utf-8")
    document = json.loads((ROOT / "conformance" / "requirements.json").read_text(encoding="utf-8"))
    vectors = json.loads((ROOT / "conformance" / "vectors.json").read_text(encoding="utf-8"))
    python_tests = test_names(ROOT / "python" / "tests", r"def (test_[a-z0-9_]+)")
    rust_tests = test_names(ROOT / "rust" / "tests", r"#\[test\]\s*\n\s*fn ([a-z0-9_]+)")
    zenoh = ROOT / "bindings" / "zenoh"
    tests = {
        "python": python_tests,
        "rust": rust_tests,
        "zenoh-python": test_names(zenoh / "python" / "tests", r"def (test_[a-z0-9_]+)"),
        "zenoh-rust": test_names(zenoh / "rust" / "tests", r"#\[test\]\s*\n\s*fn ([a-z0-9_]+)"),
    }
    simulate = (ROOT / "model" / "simulate.py").read_text(encoding="utf-8")
    claims = set(re.findall(r"^def ([A-Z][A-Za-z0-9]*) : Prop", (ROOT / "formal" / "Statements.lean").read_text(
        encoding="utf-8"), re.MULTILINE))
    gate = (ROOT / "scripts" / "check_ncp2.sh").read_text(encoding="utf-8")
    keywords: set[str] = set()
    for case in vectors["schemas"]:
        schema_keywords(case["schema"], keywords)

    def exists(reference: str) -> bool:
        kind, _, rest = reference.partition(":")
        if kind == "vectors":
            part, _, name = rest.partition(":")
            if part not in vectors or not isinstance(vectors[part], list):
                return False
            if not name:
                return True
            if part == "streams":
                return any(case.get("status") == name for case in vectors[part])
            if part == "schemas":
                return name in keywords
            return any(case.get("name") == name for case in vectors[part])
        if kind == "test":
            suite, _, name = rest.partition(":")
            return name in tests.get(suite, set())
        if kind == "model":
            if rest == "conformance":
                return (ROOT / "model" / "conformance.py").is_file()
            script, _, prop = rest.partition(":")
            return script == "simulate" and re.search(rf"^\s+{re.escape(prop)} ", simulate, re.MULTILINE) is not None
        if kind == "lean":
            return rest in claims
        if kind == "fuzz":
            return (ROOT / "conformance" / "fuzz.py").is_file()
        if kind == "gate":
            return rest in gate
        return False

    failures: list[str] = []
    wanted = extract(spec)
    entries = document["requirements"]
    have = [(entry["section"], entry["text"]) for entry in entries]
    for item in wanted:
        if have.count(item) != 1:
            failures.append(f"section {item[0]}: no single entry for: {item[1][:100]}")
    for item in have:
        if item not in wanted:
            failures.append(f"section {item[0]}: an entry for a line that the specification does not have: {item[1][:100]}")
    untested = 0
    for entry in entries:
        where = f"section {entry['section']}: {entry['text'][:60]}"
        covered = entry.get("covered_by", [])
        if entry.get("untested"):
            untested += 1
            if covered:
                failures.append(f"{where}: both covered and untested")
            if "MUST" in KEYWORD.findall(entry["text"]) and "deployment" not in entry["untested"]:
                failures.append(f"{where}: a MUST that is untested and is not a rule for deployments")
        elif not covered:
            failures.append(f"{where}: no check and no reason")
        for reference in covered:
            if not exists(reference):
                failures.append(f"{where}: the reference {reference!r} does not exist")
    for failure in failures:
        print(failure, file=sys.stderr)
    if failures:
        print(f"requirements: {len(failures)} problems", file=sys.stderr)
        return 1
    references = sum(len(entry.get("covered_by", [])) for entry in entries)
    print(f"requirements: {len(entries)} requirements of spec/NCP-2.md, {references} references to checks, "
          f"{untested} untested with a reason")
    return 0


if __name__ == "__main__":
    sys.exit(main())
