#!/usr/bin/env python3
"""Fail closed when a Buf remote generator is movable or under-specified.

`buf.gen.yaml` drives preview-only generated trees, but those outputs still need a
reproducible generator identity.  A remote plugin therefore needs both an exact
semantic version in its BSR reference and a positive BSR revision.  This checker
also freezes the reviewed plugin set, revisions, and output directories.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "buf.gen.yaml"
EXPECTED_CONFIG_SHA256 = "7f690ea2319ceabab73f56a1a131c27a1d839ccbef10c601c77589b8990066ac"

EXPECTED = {
    "buf.build/community/neoeinstein-prost:v0.5.0": (1, "gen/rust", ()),
    "buf.build/protocolbuffers/python:v35.1": (1, "gen/python", ()),
    "buf.build/community/stephenh-ts-proto:v2.12.0": (
        1,
        "gen/ts",
        ("outputServices=false", "esModuleInterop=true"),
    ),
}

REMOTE = re.compile(
    r"^\s*-\s+remote:\s*(buf\.build/[a-z0-9_.-]+/[a-z0-9_.-]+:v[0-9]+(?:\.[0-9]+){1,2}(?:[-+][0-9A-Za-z.-]+)?)\s*$"
)
REVISION = re.compile(r"^\s+revision:\s*([0-9]+)\s*$")
OUT = re.compile(r"^\s+out:\s*([^#\s]+)\s*$")
PLUGIN_START = re.compile(r"^\s*-\s+(?:remote|local|protoc_builtin):")
OPTION = re.compile(r"^\s{6,}-\s+([^#\s].*?)\s*$")


class PinError(ValueError):
    """The generation configuration contains a movable or unexpected plugin."""


def parse(text: str) -> dict[str, tuple[int, str, tuple[str, ...]]]:
    lines = text.splitlines()
    found: dict[str, tuple[int, str, tuple[str, ...]]] = {}
    index = 0
    while index < len(lines):
        line = lines[index]
        remote_match = REMOTE.fullmatch(line)
        if "remote:" in line and remote_match is None:
            raise PinError(f"line {index + 1}: remote plugin must have an exact v-version")
        if PLUGIN_START.match(line) is not None and remote_match is None:
            raise PinError(
                f"line {index + 1}: only the reviewed pinned remote plugins are allowed"
            )
        if remote_match is None:
            index += 1
            continue

        remote = remote_match.group(1)
        if remote in found:
            raise PinError(f"duplicate remote plugin {remote}")
        revision: int | None = None
        out: str | None = None
        options: list[str] = []
        index += 1
        while index < len(lines) and PLUGIN_START.match(lines[index]) is None:
            revision_match = REVISION.fullmatch(lines[index])
            out_match = OUT.fullmatch(lines[index])
            option_match = OPTION.fullmatch(lines[index])
            if revision_match is not None:
                if revision is not None:
                    raise PinError(f"duplicate revision for {remote}")
                revision = int(revision_match.group(1))
            if out_match is not None:
                if out is not None:
                    raise PinError(f"duplicate output for {remote}")
                out = out_match.group(1)
            if option_match is not None:
                options.append(option_match.group(1))
            index += 1
        if revision is None or revision <= 0:
            raise PinError(f"{remote} needs a positive BSR revision")
        if out is None:
            raise PinError(f"{remote} needs an output directory")
        if len(options) != len(set(options)):
            raise PinError(f"{remote} contains a duplicate option")
        found[remote] = (revision, out, tuple(options))
    return found


def validate(text: str) -> None:
    found = parse(text)
    if found != EXPECTED:
        missing = sorted(set(EXPECTED) - set(found))
        unexpected = sorted(set(found) - set(EXPECTED))
        changed = sorted(
            remote
            for remote in set(found) & set(EXPECTED)
            if found[remote] != EXPECTED[remote]
        )
        details = []
        if missing:
            details.append("missing=" + ",".join(missing))
        if unexpected:
            details.append("unexpected=" + ",".join(unexpected))
        if changed:
            details.append("revision/output/options changed=" + ",".join(changed))
        raise PinError("remote generator set differs from the reviewed pins: " + "; ".join(details))
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if digest != EXPECTED_CONFIG_SHA256:
        raise PinError(
            "buf.gen.yaml differs from the exact reviewed generator configuration"
        )


def self_test(good: str) -> None:
    validate(good)
    hostiles = (
        good.replace(":v0.5.0", "", 1),
        good.replace("    revision: 1\n", "", 1),
        good.replace("    revision: 1", "    revision: 0", 1),
        good.replace("gen/rust", "gen/moved", 1),
        good.replace(":v35.1", ":v35.2", 1),
        good.replace("outputServices=false", "outputServices=true", 1),
        good + "\n  - local: protoc\n    out: gen/local\n",
        good.replace(
            "plugins:\n",
            'plugins:\n  - "local": protoc-gen-evil\n    out: gen/evil\n',
            1,
        ),
        good.replace("    out: gen/rust", "    include_imports: true\n    out: gen/rust", 1),
    )
    for hostile in hostiles:
        try:
            validate(hostile)
        except PinError:
            continue
        raise AssertionError("hostile Buf generator mutation passed validation")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        text = CONFIG.read_text(encoding="utf-8")
        validate(text)
        if args.self_test:
            self_test(text)
    except (OSError, UnicodeError, PinError, AssertionError) as error:
        print(f"BUF GENERATOR PIN FAILURE: {error}", file=sys.stderr)
        return 1
    print(
        f"OK Buf generator pins: {len(EXPECTED)} exact remote versions, "
        "revisions, options, and full config bytes"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
