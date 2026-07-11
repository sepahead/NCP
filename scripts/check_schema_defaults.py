#!/usr/bin/env python3
"""Schema-default safety guard for the generated NCP JSON-Schema projection.

The committed `schemas/*.schema.json` are generated from the Rust `ncp-core` serde
reference types. This focused guard regenerates them independently and compares every
retained optional-field default, producing a safety-specific diagnostic if an artifact
is stale: an omitted `CommandFrame.mode` must fail-safe to `"hold"`, never `"active"`.
It also rejects defaults on required/const fields and defaults incompatible with a
directly declared primitive type. Deserialize-only missing-field sentinels are not wire
defaults and must never leak into the published schemas. The broader fresh-schema diff
in CI remains the byte-for-byte reproducibility gate.

How: run the Rust-reference generator (`cargo run -p ncp-core --features schema --bin
gen-schemas`) to a temp dir — its output IS the Rust reference — then assert every
message's recursive `default` annotations match the committed schema's, then enforce
the safety invariants independently on both trees.

Usage: python3 scripts/check_schema_defaults.py
Exit: 0 = all defaults agree; 1 = a mismatch (a real bug); 2 = setup/tooling error.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
COMMITTED = REPO / "schemas"


def _walk(node: object, path: tuple[str, ...] = ()):
    if isinstance(node, dict):
        yield path, node
        for key, value in node.items():
            yield from _walk(value, (*path, key))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _walk(value, (*path, str(index)))


def _field_defaults(schema: dict) -> dict[tuple[str, ...], object]:
    """Every recursively declared `default`, keyed by a stable schema path."""
    return {path: node["default"] for path, node in _walk(schema) if "default" in node}


def _type_accepts(value: object, declared: str) -> bool:
    if declared == "null":
        return value is None
    if declared == "boolean":
        return isinstance(value, bool)
    if declared == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if declared == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if declared == "string":
        return isinstance(value, str)
    if declared == "array":
        return isinstance(value, list)
    if declared == "object":
        return isinstance(value, dict)
    return True


def _default_problems(schema: dict, label: str) -> list[str]:
    problems: list[str] = []
    for path, node in _walk(schema):
        shown = "/".join(path) or "$"
        if "default" in node:
            default = node["default"]
            if "const" in node:
                problems.append(f"{label}:{shown}: const/discriminator field must not advertise a default")
            declared = node.get("type")
            kinds = [declared] if isinstance(declared, str) else declared
            if isinstance(kinds, list) and not any(
                isinstance(kind, str) and _type_accepts(default, kind) for kind in kinds
            ):
                problems.append(
                    f"{label}:{shown}: default {default!r} is incompatible with declared type {declared!r}"
                )

        properties = node.get("properties")
        required = node.get("required")
        if isinstance(properties, dict) and isinstance(required, list):
            for field in required:
                spec = properties.get(field)
                if isinstance(spec, dict) and "default" in spec:
                    problems.append(
                        f"{label}:{shown}/properties/{field}: required field must not advertise a default"
                    )
    return problems


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        proc = subprocess.run(
            ["cargo", "run", "-q", "-p", "ncp-core", "--features", "schema", "--bin", "gen-schemas", "--", tmp],
            cwd=REPO,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            sys.stderr.write("ERROR: gen-schemas (the Rust reference) failed to run:\n")
            sys.stderr.write(proc.stderr[-2000:])
            return 2
        ref_dir = Path(tmp)

        problems: list[str] = []
        notes: list[str] = []
        checked = 0
        for committed_path in sorted(COMMITTED.glob("*.schema.json")):
            ref_path = ref_dir / committed_path.name
            if not ref_path.exists():
                notes.append(f"{committed_path.name}: no reference schema generated (skipped)")
                continue
            committed = json.loads(committed_path.read_text())
            reference = json.loads(ref_path.read_text())
            problems.extend(_default_problems(committed, f"committed {committed_path.name}"))
            problems.extend(_default_problems(reference, f"generated {ref_path.name}"))
            c_def = _field_defaults(committed)
            r_def = _field_defaults(reference)
            for field in sorted(set(c_def) & set(r_def)):
                checked += 1
                if c_def[field] != r_def[field]:
                    problems.append(
                        f"{committed_path.name}: field {'/'.join(field)!r} default committed={c_def[field]!r} "
                        f"!= Rust reference={r_def[field]!r}"
                    )
            for field in sorted(set(c_def) ^ set(r_def)):
                notes.append(
                    f"{committed_path.name}: field {'/'.join(field)!r} has a default on only one side"
                )

            if committed_path.name == "command_frame.schema.json":
                mode_default = committed.get("properties", {}).get("mode", {}).get("default")
                if mode_default != "hold":
                    problems.append(
                        f"{committed_path.name}: CommandFrame.mode default must be 'hold', got {mode_default!r}"
                    )

    print(f"Schema-default safety guard: compared {checked} retained defaults against the generated projection.")
    for n in notes:
        print(f"  note: {n}")
    if problems:
        sys.stderr.write("\nUNSAFE OR DRIFTED JSON-SCHEMA DEFAULT ANNOTATION:\n")
        for p in problems:
            sys.stderr.write(f"  - {p}\n")
        sys.stderr.write("\nRequired fields and const discriminators have no wire default; deserialize-only\n")
        sys.stderr.write("sentinels must not be published. Fix the generator and regenerate schemas.\n")
        return 1
    print("OK: all committed schema defaults are safe and match the generated projection.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
